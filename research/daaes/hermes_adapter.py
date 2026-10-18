"""
The H0 arm: Hermes Agent (NousResearch/hermes-agent) as a comparison system, behind the same model gateway and judged by the same oracle as Delentia's D0.

Pinned: tag v0.22.2, commit d923a5eb487a17c0a68801bba9ef0f56c81040a8, cloned shallow into `Delentia/_external/hermes-agent-v0.22.2` (outside every repository) and installed editable into its own Python 3.14
virtual environment (`C:\\Users\\whale\\hermes_env`; Hermes needs 3.14, the rest of this repository runs on 3.13). Nothing of Hermes is imported into Delentia's process.

What a run is: a child process (Hermes' Python) is started with a minimal environment (no DELENTIA_* variables, no provider key: the only credential it holds is the gateway's token), the workspace as its
working directory, Hermes' own HERMES_HOME in a temporary folder (so it cannot read or change the owner's real Hermes state) and the `file` and `terminal` toolsets. Every model call goes through
`model_gateway.ModelGateway`, so the budget guard and the call log are the same instrument for both systems.

What it does NOT give, stated: Hermes has no counterpart of the FDIA gate, the taint rule or the signed approvals, so any difference in what an unsafe model could do is a difference of design, not a defect of
this adapter; its terminal tool runs commands as the person who started it. With a scripted model that is harmless; with a real model it must run inside a container or a throw-away user account, and this
module refuses to start a real-model run unless the caller says the shell is sandboxed (`sandboxed=True`). Capability not present (the fault injection F1-F3, which Delentia's runner tool carries) is reported
`not_evaluated`, never as a failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

PINNED_TAG = "v0.22.2"
PINNED_SHA = "d923a5eb487a17c0a68801bba9ef0f56c81040a8"
SCRIPT = Path(__file__).with_name("hermes_runner_script.py")


def hermes_python() -> Path:
    return Path(os.environ.get("DELENTIA_HERMES_PYTHON") or r"C:\Users\whale\hermes_env\Scripts\python.exe")


def hermes_src() -> Path:
    return Path(os.environ.get("DELENTIA_HERMES_SRC") or r"C:\Users\whale\Delentia\_external\hermes-agent-v0.22.2")


def available() -> bool:
    return hermes_python().exists() and (hermes_src() / "run_agent.py").exists()


def installed_sha() -> Optional[str]:
    try:
        return subprocess.run(["git", "-C", str(hermes_src()), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20).stdout.strip() or None
    except Exception:                                               # noqa: BLE001
        return None


CONTAINER_HERMES_SRC = "/home/hermes/.hermes/hermes-agent"
CONTAINER_PYTHON = "/home/hermes/venv/bin/python"
CONTAINER_HOME = "/home/hermes/run_home"        # a tmpfs inside the container: Hermes writes thousands of small files on first start, which over a Windows bind mount took minutes


def container_image() -> Optional[str]:
    """The image name when the caller wants Hermes run inside a container (`DELENTIA_HERMES_CONTAINER`, e.g. daaes-hermes:r86; built from research/daaes/hermes_arm/Dockerfile)."""
    return (os.environ.get("DELENTIA_HERMES_CONTAINER") or "").strip() or None


def container_pinned_sha(image: str) -> Optional[str]:
    try:
        done = subprocess.run(["docker", "run", "--rm", "--entrypoint", "git", image, "-C", CONTAINER_HERMES_SRC, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=120)
        return done.stdout.strip() or None
    except Exception:                                               # noqa: BLE001
        return None


def _run_in_container(image: str, goal: str, workspace: Path, base_url: str, token: str, model: str, workdir: Path, *, max_iterations: int, max_seconds: float, toolsets: Optional[list]) -> Dict[str, Any]:
    """Hermes inside a throw-away container: only the case workspace (/work) and this run's folder (/run) are mounted; the model gateway is reached through host.docker.internal; no environment variable
    of ours is passed; all capabilities dropped, no new privileges, memory/CPU/process ceilings. The container is removed afterwards even if it hung."""
    import re
    import time
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    runner = workdir / "hermes_runner_script.py"
    runner.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    inside_url = re.sub(r"^(https?://)(127\.0\.0\.1|localhost)", r"\1host.docker.internal", base_url)
    cfg = {"hermes_src": CONTAINER_HERMES_SRC, "hermes_home": CONTAINER_HOME, "workspace": "/work", "base_url": inside_url, "api_key": token, "model": model, "goal": goal,
           "max_iterations": max_iterations, "max_seconds": max_seconds, "toolsets": toolsets or ["file", "terminal"]}
    (workdir / "hermes_run.json").write_text(json.dumps(cfg), encoding="utf-8")
    name = f"daaes-h0-{time.time_ns()}"
    argv = ["docker", "run", "--rm", "--name", name, "--memory", "3g", "--cpus", "2", "--pids-limit", "512", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--add-host", "host.docker.internal:host-gateway", "--tmpfs", f"{CONTAINER_HOME}:rw,exec,size=768m,uid=1500,gid=1500", "-v", f"{workspace}:/work", "-v", f"{workdir}:/run", "-w", "/work", "-e", f"HERMES_HOME={CONTAINER_HOME}",
            "-e", "PYTHONIOENCODING=utf-8", "-e", "PYTHONUTF8=1", "-e", f"HOME={CONTAINER_HOME}", "--entrypoint", CONTAINER_PYTHON, image, "/run/hermes_runner_script.py", "/run/hermes_run.json"]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=max_seconds + 120)
        code, out, err = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as exc:
        code, out, err = -1, (exc.stdout or "") if isinstance(exc.stdout, str) else "", "timed out"
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)
    parsed: Dict[str, Any] = {}
    for line in out.splitlines():
        if line.startswith("HERMES_RESULT "):
            try:
                parsed = json.loads(line[len("HERMES_RESULT "):])
            except ValueError:
                pass
    return {"available": True, "exit_code": code, "result": parsed, "stderr_tail": err[-600:], "pinned_ok": container_pinned_sha(image) == PINNED_SHA, "tag": PINNED_TAG, "container": image}


def run_goal(goal: str, workspace: Path, base_url: str, token: str, model: str, workdir: Path, *, max_iterations: int = 14, max_seconds: float = 600.0, toolsets: Optional[list] = None,
             real_model: bool = False, sandboxed: bool = False) -> Dict[str, Any]:
    """One Hermes conversation in `workspace`. `base_url`/`token` are the gateway's. Returns the parsed result plus how the process ended.
    With `DELENTIA_HERMES_CONTAINER=<image>` the run happens inside that container (which also counts as the sandbox a real model requires)."""
    image = container_image()
    if image:
        return _run_in_container(image, goal, Path(workspace), base_url, token, model, workdir, max_iterations=max_iterations, max_seconds=max_seconds, toolsets=toolsets)
    if real_model and not sandboxed:
        raise PermissionError("Hermes' terminal tool runs commands as this user: a run with a real model needs a container or a throw-away account (sandboxed=True), not the owner's own session")
    if not available():
        return {"available": False, "note": "Hermes is not installed here (see hermes_adapter.py for the pinned release and where it is expected)"}
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    home = workdir / "hermes_home"
    home.mkdir(parents=True, exist_ok=True)
    cfg = {"hermes_src": str(hermes_src()), "hermes_home": str(home), "workspace": str(workspace), "base_url": base_url, "api_key": token, "model": model, "goal": goal,
           "max_iterations": max_iterations, "max_seconds": max_seconds, "toolsets": toolsets or ["file", "terminal"]}
    cfg_path = workdir / "hermes_run.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k.upper() in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "COMSPEC", "PATHEXT", "WINDIR", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "APPDATA")}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "HERMES_HOME": str(home)})
    try:
        done = subprocess.run([str(hermes_python()), str(SCRIPT), str(cfg_path)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(workspace),
                              timeout=max_seconds + 60)
        code, out, err = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as exc:
        code, out, err = -1, (exc.stdout or "") if isinstance(exc.stdout, str) else "", "timed out"
    parsed: Dict[str, Any] = {}
    for line in out.splitlines():
        if line.startswith("HERMES_RESULT "):
            try:
                parsed = json.loads(line[len("HERMES_RESULT "):])
            except ValueError:
                pass
    return {"available": True, "exit_code": code, "result": parsed, "stderr_tail": err[-600:], "pinned_ok": installed_sha() == PINNED_SHA, "tag": PINNED_TAG}


def new_temp(prefix: str = "hermes-run-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))
