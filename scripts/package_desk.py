"""
Round 101 (UX audit): build the Desk (apps/gui) and put the result inside the Python package, so `pip install delentia-os` brings the web pages with it and `delentia desk` can open them.

    python scripts/package_desk.py            # builds the two SDK packages the Desk needs, then the Desk, then copies apps/gui/out -> rct_control_plane/desk_ui
    python scripts/package_desk.py --skip-build   # only copy an existing apps/gui/out

Run it before `python -m build` (the release workflow and the package check do). The copied folder is not committed (see .gitignore). Needs Node.js 20 or newer.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUI = ROOT / "apps" / "gui"
DEST = ROOT / "rct_control_plane" / "desk_ui"


def run(cmd: list, cwd: Path, env: dict | None = None) -> None:
    print("+", " ".join(cmd), f"(in {cwd.relative_to(ROOT)})", flush=True)
    subprocess.run(cmd, cwd=str(cwd), check=True, env={**os.environ, **(env or {})})


def run_retrying(cmd: list, cwd: Path, env: dict | None = None, attempts: int = 3, delay: float = 30.0, runner=run, sleep=time.sleep) -> None:
    """The Desk build downloads its three Google fonts while it builds (next/font/google), and Turbopack reports a failed download as a plain "module not found". A network blip must not fail a release or a
    package check, so the build is tried again; any other failure fails again the same way each time and is still reported after the last attempt."""
    for attempt in range(1, attempts + 1):
        try:
            runner(cmd, cwd, env)
            return
        except subprocess.CalledProcessError:
            if attempt == attempts:
                raise
            print(f"the build failed (attempt {attempt} of {attempts}); trying again in {int(delay)} seconds (it downloads fonts while it builds)", flush=True)
            sleep(delay)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-build", action="store_true", help="copy apps/gui/out as it is")
    args = ap.parse_args()
    npm = shutil.which("npm")
    if not args.skip_build:
        if not npm:
            print("npm (Node.js 20 or newer) was not found.", file=sys.stderr)
            return 4
        for package in ("fdia-wasm", "rct-edge"):
            folder = ROOT / "sdk-typescript" / "packages" / package
            run([npm, "ci", "--ignore-scripts"], folder)
            run([npm, "run", "build"], folder)
        run([npm, "ci"], GUI)
        # The page asks the API where it is at run time (the launcher hands it over); this is only the fallback when nothing does.
        run_retrying([npm, "run", "build"], GUI, {"NEXT_PUBLIC_GATEWAY": "http://localhost:8000"})
    out = GUI / "out"
    if not (out / "index.html").is_file():
        print(f"{out} has no index.html: the build did not produce the Desk.", file=sys.stderr)
        return 5
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(out, DEST)
    files = sum(1 for p in DEST.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
    print(f"copied the Desk into {DEST.relative_to(ROOT)}: {files} files, {size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
