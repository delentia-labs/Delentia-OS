"""
Round 92: open the Delentia Desk with one command (or a double click on OPEN_DESK.bat).

    python scripts/open_desk.py [--host-dir DIR] [--port 3010] [--no-browser] [--build]

What it does, in order, and says what it is doing:
  1. looks for the host (default %USERPROFILE%\\delentia-host, made by scripts/local_host.py) and starts it if it is not answering;
  2. makes sure the Desk has been built (apps/gui/out); builds it with `npm run build` when it is missing or when you pass --build (a few minutes the first time);
  3. serves the built Desk on http://127.0.0.1:PORT and hands the host's address and the owner's token to the page (see rct_control_plane/desk_launcher.py: the token is not put in the address);
  4. opens your browser. Close this window (or press Ctrl+C) to stop the Desk page; the host keeps running.
It never prints the token, never writes it anywhere, and listens on 127.0.0.1 only.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rct_control_plane import desk_launcher  # noqa: E402


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
            return json.loads(r.read()).get("status") == "healthy"
    except Exception:                                                     # noqa: BLE001
        return False


def say(text: str) -> None:
    print(text, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Open the Delentia Desk with one command.")
    ap.add_argument("--host-dir", default=str(Path.home() / "delentia-host"))
    ap.add_argument("--port", type=int, default=3010, help="where the Desk page is served (127.0.0.1 only)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--build", action="store_true", help="rebuild the Desk even if apps/gui/out exists")
    args = ap.parse_args()

    host_dir = Path(args.host_dir)
    cfg_path = host_dir / "host.json"
    if not cfg_path.is_file():
        say(f"No host found at {host_dir}. Make one first:  python scripts/local_host.py init   (then start it with:  python scripts/local_host.py start)")
        return 2
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    api_port = int(cfg.get("port") or 8000)
    token_file = host_dir / "api_token.txt"

    say("1/3  The host (the agent's server)")
    if healthy(api_port):
        say(f"     already running on port {api_port}")
    else:
        say(f"     not answering on port {api_port}: starting it (about 20 seconds)...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "local_host.py"), "start", "--dir", str(host_dir)], check=False, capture_output=True, text=True)
        for _ in range(60):
            if healthy(api_port):
                break
            time.sleep(1)
        if not healthy(api_port):
            say("     the host did not come up. Look at:  " + str(host_dir / "logs" / "server.log"))
            return 3
        say("     started")

    say("2/3  The Desk (the web pages)")
    gui = ROOT / "apps" / "gui"
    out = gui / "out"
    if args.build or not (out / "index.html").is_file():
        npm = shutil.which("npm")
        if not npm:
            say("     the Desk has not been built and `npm` (Node.js) was not found. Install Node.js 20 or newer from nodejs.org, then run this again.")
            return 4
        say("     building it now (first time: a few minutes; later runs skip this)...")
        built = subprocess.run([npm, "run", "build"], cwd=str(gui), check=False)
        if built.returncode != 0 or not (out / "index.html").is_file():
            say("     the build failed (the lines above say why). Nothing was changed on the host.")
            return 5
    else:
        say("     already built (use --build after you update the code)")

    say("3/3  Opening")

    def read_token() -> str:
        return token_file.read_text(encoding="utf-8").strip() if token_file.is_file() else ""

    try:
        server = desk_launcher.make_server(out, args.port, f"http://127.0.0.1:{api_port}", read_token)
    except OSError as exc:
        say(f"     port {args.port} is busy ({exc}). Close the other Desk window or use --port 3011.")
        return 6
    thread, url = desk_launcher.serve_in_background(server)
    say(f"     the Desk is at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    say("")
    say("Leave this window open while you use the Desk. Close it (or press Ctrl+C) to stop the Desk page. The host keeps running.")
    try:
        while thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
