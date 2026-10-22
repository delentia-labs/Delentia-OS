"""Source-checkout demo: SCRIPTED HTTP model, real CLI, tools and durable contracts.

No paid provider is contacted. Use a NEW --dir; key/data directories are private
runtime state and must not be included in a public recording bundle.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--pause", type=float, default=0)
    args = parser.parse_args()
    root = args.dir.resolve()
    if root.exists():
        parser.error("--dir must be new; never overwrite a previous attempt")
    (root / "workspace").mkdir(parents=True)
    (root / "workspace/source.md").write_text("Project: Delentia\nข้อมูลสังเคราะห์สำหรับสาธิต\n", encoding="utf-8")
    (root / "criteria.json").write_text(json.dumps([
        {"kind": "language", "value": "th"}, {"kind": "file_unchanged", "value": "source.md"}], ensure_ascii=False))
    os.environ.update({"DELENTIA_HOME": str(root / "data"), "DELENTIA_REPO_ROOT": str(root / "workspace"),
                       "DELENTIA_MODEL_CONFIG": str(root / "model.json"), "DELENTIA_RUN_LIVE_TESTS": "0",
                       "DELENTIA_ALGORITHM_PIPELINE": "0", "DELENTIA_WARM_RECALL": "0"})
    for name in ("DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL", "DELENTIA_FALLBACK_MODELS"):
        os.environ.pop(name, None)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rct_control_plane/tests"))
    from scripted_model import ScriptedModel, _call, _finish
    from rct_control_plane.model_config import save_model_selection
    from rct_control_plane.intent_contract import IntentContractStore
    from rct_control_plane.persistence import ControlPlanePersistence

    ledger = []
    def policy(req):
        if req.history_empty:
            return _call("delentia_read_repo_file", {"relative_path": "source.md"})
        if "User-confirmed clarification" in req.prompt:
            return _finish("อ่านข้อมูลแล้ว โครงการชื่อ Delentia โดยไม่ได้แก้ไฟล์ต้นฉบับ")
        return _finish("The project is Delentia. The source file was not changed.")

    def command(arguments, expected):
        print("\n$ delentia " + " ".join(arguments), flush=True)
        started = time.monotonic()
        result = subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *arguments], cwd=ROOT,
                                timeout=120)
        print(f"[exit {result.returncode}]", flush=True)
        ledger.append({"args": arguments, "exit_code": result.returncode, "seconds": time.monotonic() - started})
        if result.returncode != expected:
            raise RuntimeError("demo command did not have the expected outcome; keep this failed attempt")
        time.sleep(max(0, args.pause))

    print("SCRIPTED MECHANISM DEMO | experimental | no paid API", flush=True)
    print("The local HTTP script replaces the model. CLI, file reads, SQLite and criteria checks are real.", flush=True)
    before = (root / "workspace/source.md").read_bytes()
    with ScriptedModel(policy, model_id="scripted-contract-demo") as model:
        save_model_selection("openai-compat", model.model_id, path=root / "model.json", endpoint={
            "base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted-demo"})
        command(["agent", "Read source.md and answer in Thai without changing the original", "--namespace", "demo-contract",
                 "--criteria-file", str(root / "criteria.json"), "--max-iterations", "4"], 1)
        store = IntentContractStore(ControlPlanePersistence(db_path=str(root / "data/agentic.db")), "demo-contract")
        with store.db._connect() as conn:
            contract_id = conn.execute("SELECT id FROM intent_contracts WHERE namespace=?", ("demo-contract",)).fetchone()[0]
        c = store.get(contract_id)
        assert c["state"] == "waiting_for_clarification"
        print("CHECK: waiting persisted; no automatic repair; original file bytes unchanged.", flush=True)
        assert (root / "workspace/source.md").read_bytes() == before
        command(["intent-contract", "show", contract_id, "--namespace", "demo-contract"], 0)
        command(["intent-contract", "continue", contract_id, "--namespace", "demo-contract", "--version", str(c["version"])], 1)
        command(["intent-contract", "continue", contract_id, "--namespace", "demo-contract", "--version", str(c["version"]),
                 "--response", "Keep the Thai requirement; please answer in Thai"], 0)
        done = store.get(contract_id)
        assert done["state"] == "criteria_satisfied" and done["revisions"]
        assert done["original_goal"] == c["original_goal"]
        assert (root / "workspace/source.md").read_bytes() == before
        print("CHECK: original intent retained, confirmed revision stored, Thai criterion satisfied; source unchanged.", flush=True)
        (root / "result.json").write_text(json.dumps({"label": "SCRIPTED", "model_calls": model.calls,
            "commands": ledger, "contract": done, "source_unchanged": True}, ensure_ascii=False, indent=2))
    print("LIMIT: script/language checks are not semantic truth or capable-model evidence.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
