"""
Round 84: this machine as the first test host (no rented server yet).

    python scripts/local_host.py init   [--dir DIR] [--provider ollama --model qwen3:8b] [--audit-key PEM] [--witness-url URL --witness-key-id host-1]
    python scripts/local_host.py start  [--port 8000]       # starts a supervisor in the background; it starts `delentia serve` and restarts it if it dies
    python scripts/local_host.py status [--json]
    python scripts/local_host.py stop
    python scripts/local_host.py env                         # the non-secret settings as PowerShell lines

What it sets up, all under one folder (default %USERPROFILE%\\delentia-host, nothing is written outside it except what you point it at):
  home/            DELENTIA_HOME: the host's databases, memory keys, audit chain. A clean home, separate from the development one, so what is anchored at the witness is the host's own history.
  api_token.txt    a random token (the server refuses to listen beyond loopback without one, and checks it on every call)
  host.json        the settings that are not secret: provider, model, ports, limits, key PATHS (never key material)
  logs/            server.log, supervisor.log, restarts.jsonl (one line per start of the server: why the last one ended, how long it lived)

What it is NOT: it does not turn this machine into a safe place for a real model to run commands (the local shell sandbox is a classifier plus ceilings, not a jail), it does not stop Windows from restarting
for an update or the machine from sleeping on battery (the host-check lists those), it does not create a second operating-system user for the notary (the owner does), and it never reads or writes a key.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = Path(os.environ.get("USERPROFILE") or Path.home()) / "delentia-host"


def paths(host_dir: Path) -> Dict[str, Path]:
    return {"dir": host_dir, "home": host_dir / "home", "logs": host_dir / "logs", "token": host_dir / "api_token.txt", "config": host_dir / "host.json", "server_pid": host_dir / "server.pid",
            "supervisor_pid": host_dir / "supervisor.pid", "restarts": host_dir / "logs" / "restarts.jsonl", "stop": host_dir / "STOP"}


def load_config(host_dir: Path) -> Dict[str, Any]:
    cfg = paths(host_dir)["config"]
    if not cfg.exists():
        raise SystemExit(f"{host_dir} is not initialised: run `python scripts/local_host.py init` first")
    return json.loads(cfg.read_text(encoding="utf-8"))


def init(host_dir: Path, provider: str, model: str, audit_key: Optional[str], witness_url: Optional[str], witness_key_id: Optional[str], port: int, episode_budget_usd: float,
         daily_usd: float, daily_tokens: int) -> Dict[str, Any]:
    p = paths(host_dir)
    for key in ("home", "logs"):
        p[key].mkdir(parents=True, exist_ok=True)
    if not p["token"].exists():
        p["token"].write_text(secrets.token_urlsafe(32), encoding="utf-8")
    if witness_url and not audit_key:
        raise SystemExit("anchoring needs an audit signing key (--audit-key): the witness only accepts signed heads")
    if audit_key and not Path(audit_key).exists():
        raise SystemExit(f"the audit key {audit_key} does not exist: create it with `delentia audit-chain keygen --out <path>` (outside every repository)")
    if audit_key and ROOT in Path(audit_key).resolve().parents:
        raise SystemExit("an audit key inside the repository would be committed: choose a folder outside it")
    cfg = {"dir": str(host_dir), "port": port, "provider": provider, "model": model, "audit_key_path": audit_key, "witness_url": witness_url, "witness_key_id": witness_key_id,
           "episode_budget_usd": episode_budget_usd, "daily_usd": daily_usd, "daily_tokens": daily_tokens, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "python": sys.executable}
    p["config"].write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def server_env(cfg: Dict[str, Any]) -> Dict[str, str]:
    p = paths(Path(cfg["dir"]))
    env = {k: v for k, v in os.environ.items() if not k.startswith("DELENTIA_") and k not in ("OPENROUTER_API_KEY",)}
    env.update({"DELENTIA_HOME": str(p["home"]), "DELENTIA_API_TOKEN": p["token"].read_text(encoding="utf-8").strip(), "DELENTIA_LLM_PROVIDER": cfg["provider"], "DELENTIA_LLM_MODEL": cfg["model"],
                "DELENTIA_OLLAMA_URL": os.environ.get("DELENTIA_OLLAMA_URL", "http://127.0.0.1:11434"), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    if float(cfg.get("episode_budget_usd") or 0) > 0:        # 0 means "no limit" here; the loop refuses a literal 0 (found by the first real episode on this host: every run was an HTTP 500)
        env["DELENTIA_EPISODE_BUDGET_USD"] = str(cfg["episode_budget_usd"])
    if cfg.get("daily_usd"):
        env["DELENTIA_DAILY_BUDGET_USD"] = str(cfg["daily_usd"])
    if cfg.get("daily_tokens"):
        env["DELENTIA_DAILY_MAX_TOKENS"] = str(cfg["daily_tokens"])
    if cfg.get("audit_key_path"):
        env["DELENTIA_AUDIT_SIGNING_KEY"] = cfg["audit_key_path"]
    if cfg.get("witness_url") and cfg.get("witness_key_id"):
        env["DELENTIA_AUDIT_ANCHOR_URL"] = cfg["witness_url"]
        env["DELENTIA_AUDIT_ANCHOR_KEY_ID"] = cfg["witness_key_id"]
    if cfg.get("provider") == "openrouter" and os.environ.get("OPENROUTER_API_KEY"):
        env["OPENROUTER_API_KEY"] = os.environ["OPENROUTER_API_KEY"]            # passed on from the person's own environment, never stored by this script
    return env


def server_command(cfg: Dict[str, Any]) -> List[str]:
    override = os.environ.get("DELENTIA_HOST_SERVER_CMD")                         # tests substitute a stand-in server
    if override:
        return json.loads(override)
    return [cfg.get("python") or sys.executable, "-m", "rct_control_plane.cli", "serve", "--host", "127.0.0.1", "--port", str(cfg["port"])]


def _write_atomic(path: Path, text: str) -> None:
    """A reader (status) must never see an empty pid file between the truncate and the write."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.02)


def _read_pid(path: Path) -> int:
    for _ in range(10):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            return 0
        if text:
            return int(text)
        time.sleep(0.02)
    return 0


def _pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:                                                              # noqa: BLE001
        return False


def supervise(host_dir: Path, backoff_max: float = 30.0) -> int:
    """Run in the background: start the server, wait for it, record how it ended, start it again. A file named STOP in the host folder ends the loop."""
    cfg = load_config(host_dir)
    p = paths(host_dir)
    _write_atomic(p["supervisor_pid"], str(os.getpid()))
    delay = 1.0
    log = open(p["logs"] / "server.log", "ab")
    try:
        while not p["stop"].exists():
            started = time.time()
            proc = subprocess.Popen(server_command(cfg), cwd=str(ROOT), env=server_env(cfg), stdout=log, stderr=subprocess.STDOUT)
            _write_atomic(p["server_pid"], str(proc.pid))
            while proc.poll() is None and not p["stop"].exists():
                time.sleep(0.5)
            if proc.poll() is None:                                                # told to stop
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
            lived = time.time() - started
            with open(p["restarts"], "a", encoding="utf-8") as f:
                f.write(json.dumps({"started_at": started, "lived_seconds": round(lived, 1), "exit_code": proc.returncode, "stopped_by_owner": p["stop"].exists()}) + "\n")
            if p["stop"].exists():
                break
            delay = 1.0 if lived > 60 else min(backoff_max, delay * 2)             # a server that lives a minute resets the wait; one that dies at once waits longer each time
            time.sleep(delay)
    finally:
        log.close()
        for name in ("server_pid", "supervisor_pid"):
            try:
                p[name].unlink()
            except OSError:
                pass
    return 0


def start(host_dir: Path) -> Dict[str, Any]:
    cfg = load_config(host_dir)
    p = paths(host_dir)
    if p["supervisor_pid"].exists() and _pid_alive(_read_pid(p["supervisor_pid"])):
        return {"started": False, "reason": "already running", "supervisor_pid": _read_pid(p["supervisor_pid"])}
    try:
        p["stop"].unlink()
    except OSError:
        pass
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = open(p["logs"] / "supervisor.log", "ab")
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_supervise", "--dir", str(host_dir)], cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, creationflags=flags, close_fds=True)
    return {"started": True, "supervisor_pid": proc.pid, "port": cfg["port"]}


def stop(host_dir: Path, wait: float = 60.0) -> Dict[str, Any]:
    p = paths(host_dir)
    p["stop"].write_text(str(time.time()), encoding="utf-8")
    deadline = time.time() + wait
    while time.time() < deadline and p["supervisor_pid"].exists():
        time.sleep(0.5)
    still = p["supervisor_pid"].exists()
    return {"stopped": not still}


def status(host_dir: Path) -> Dict[str, Any]:
    cfg = load_config(host_dir)
    p = paths(host_dir)
    out: Dict[str, Any] = {"dir": str(host_dir), "port": cfg["port"]}
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{cfg['port']}/health", headers={"Authorization": "Bearer " + p["token"].read_text(encoding="utf-8").strip()})
        with urllib.request.urlopen(req, timeout=5) as r:
            out["health"] = json.loads(r.read().decode("utf-8", "replace"))
            out["healthy"] = r.status == 200
    except Exception as exc:                                                       # noqa: BLE001
        out["healthy"] = False
        out["health_error"] = type(exc).__name__
    sup, srv = _read_pid(p["supervisor_pid"]), _read_pid(p["server_pid"])          # read AFTER the probe: a server that just answered has had its pid file written
    out.update({"supervisor_alive": bool(sup and _pid_alive(sup)), "server_pid": srv, "server_alive": bool(srv and _pid_alive(srv))})
    try:
        import psutil
        if out["server_alive"]:
            proc = psutil.Process(srv)
            out["server_rss_mb"] = round(proc.memory_info().rss / 1e6, 1)
            out["server_uptime_s"] = round(time.time() - proc.create_time(), 1)
            out["server_threads"] = proc.num_threads()
        out["system_free_ram_gb"] = round(psutil.virtual_memory().available / 1e9, 1)
        out["cpu_percent"] = psutil.cpu_percent(interval=0.3)
        battery = psutil.sensors_battery()
        out["on_battery"] = bool(battery and not battery.power_plugged)
        out["battery_percent"] = battery.percent if battery else None
    except Exception:                                                              # noqa: BLE001
        pass
    restarts = []
    if p["restarts"].exists():
        restarts = [json.loads(line) for line in p["restarts"].read_text(encoding="utf-8").splitlines() if line.strip()]
    out["server_starts"] = len(restarts)
    out["unplanned_restarts"] = sum(1 for r in restarts if not r.get("stopped_by_owner"))
    out["last_exit"] = restarts[-1] if restarts else None
    return out


def env_lines(host_dir: Path) -> str:
    cfg = load_config(host_dir)
    env = server_env(cfg)
    shown = {k: v for k, v in env.items() if k.startswith("DELENTIA_") and k != "DELENTIA_API_TOKEN"}
    shown["DELENTIA_API_TOKEN"] = "(in " + str(paths(host_dir)["token"]) + ")"
    return "\n".join(f"$env:{k} = '{v}'" for k, v in sorted(shown.items()))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("init", "start", "status", "stop", "env", "_supervise"):
        sp = sub.add_parser(name)
        sp.add_argument("--dir", default=str(DEFAULT_DIR))
        if name == "init":
            sp.add_argument("--provider", default="ollama", choices=("ollama", "openrouter"))
            sp.add_argument("--model", default="qwen3:8b")
            sp.add_argument("--audit-key", default=None)
            sp.add_argument("--witness-url", default=None)
            sp.add_argument("--witness-key-id", default=None)
            sp.add_argument("--port", type=int, default=8000)
            sp.add_argument("--episode-budget-usd", type=float, default=0.0)
            sp.add_argument("--daily-usd", type=float, default=0.0)
            sp.add_argument("--daily-tokens", type=int, default=0)
        if name == "status":
            sp.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    host_dir = Path(args.dir)
    if args.cmd == "init":
        print(json.dumps(init(host_dir, args.provider, args.model, args.audit_key, args.witness_url, args.witness_key_id, args.port, args.episode_budget_usd, args.daily_usd, args.daily_tokens), indent=2))
    elif args.cmd == "start":
        print(json.dumps(start(host_dir)))
    elif args.cmd == "stop":
        print(json.dumps(stop(host_dir)))
    elif args.cmd == "status":
        s = status(host_dir)
        print(json.dumps(s, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in s.items()))
    elif args.cmd == "env":
        print(env_lines(host_dir))
    elif args.cmd == "_supervise":
        return supervise(host_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
