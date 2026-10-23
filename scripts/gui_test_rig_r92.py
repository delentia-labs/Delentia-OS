"""Round 92: a throw-away backend for trying the Desk GUI without touching the real host.

    python scripts/gui_test_rig_r92.py [--port 8001] [--home DIR]

Starts (1) a scripted model that speaks the OpenAI protocol, (2) a temporary Delentia home with a tiny git repo (pyproject.toml, README.md),
a new approver key and a new audit key, and (3) `delentia serve` on 127.0.0.1:PORT pointed at all of it. Nothing of the real ~/.delentia is read or written.
The scripted model replaces ONLY the language model: the governed loop, tools, FDIA gate, approvals and audit chain are the real ones.
Prints the paths and the commands to sign an approval, then waits until it is stopped (Ctrl+C).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--home", default="")
    args = ap.parse_args()
    home = Path(args.home) if args.home else Path(tempfile.mkdtemp(prefix="delentia-gui-rig-"))
    home.mkdir(parents=True, exist_ok=True)
    repo = home / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "pyproject.toml").write_text('[project]\nname = "sample-service"\nversion = "0.1.0"\n', encoding="utf-8")
    (repo / "README.md").write_text("# Sample service\n\nA tiny fixture for the GUI test rig.\n", encoding="utf-8")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "-c", "user.name=rig", "-c", "user.email=rig@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(cmd, cwd=repo, check=False, capture_output=True)

    from rct_control_plane import approvals, audit_chain
    from rct_control_plane.model_config import save_model_selection
    import scripted_model as sm

    keys = home / "keys"
    keys.mkdir(exist_ok=True)
    approver_key = keys / "approver.pem"
    approver_pub = approvals.generate_approver_key(str(approver_key))
    audit_key = keys / "audit.pem"
    audit_chain.generate_signing_key(str(audit_key))

    with sm.ScriptedModel(sm.competent) as model:
        cfg = home / "model.json"
        save_model_selection("openai-compat", model.model_id, path=cfg, endpoint={
            "base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted-test-model"})
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DELENTIA_HOME": str(home / "data"), "DELENTIA_REPO_ROOT": str(repo),
               "DELENTIA_MODEL_CONFIG": str(cfg), "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": model.model_id,
               "DELENTIA_APPROVERS_FILE": str(home / "approvers.json"), approvals.APPROVERS_ENV: approver_pub,
               audit_chain.SIGNING_KEY_ENV: str(audit_key), "DELENTIA_DESK_NAMESPACE": "desk"}
        for name in ("DELENTIA_API_TOKEN", "DELENTIA_NOTARY_URL", "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS"):
            env.pop(name, None)
        server = subprocess.Popen([sys.executable, "-m", "rct_control_plane.cli", "serve", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT, env=env)
        url = f"http://127.0.0.1:{args.port}"
        for _ in range(120):
            try:
                urllib.request.urlopen(url + "/health", timeout=2).read()
                break
            except Exception:
                time.sleep(1)
        print(f"RIG READY  backend {url}  home {home}", flush=True)
        print(f"  approver key : {approver_key}", flush=True)
        print(f"  sign a request: python -m rct_control_plane.cli approvals sign <approval_id> --key {approver_key}", flush=True)
        print("  try goals    : 'Read the file pyproject.toml and tell me the project name'  /  'Write a note to notes/hello.md'", flush=True)
        try:
            server.wait()
        except KeyboardInterrupt:
            pass
        finally:
            server.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
