"""
Build the Windows installer (Delentia-Setup-<version>.exe): stage the files, then call the Inno Setup compiler.

    python installer/windows/build_installer.py --python-embed <python-3.12.x-embed-amd64.zip> --get-pip <get-pip.py> [--wheel <delentia_os-*.whl>] [--iscc <ISCC.exe>] [--offline-wheels] [--stage-only]

Nothing is downloaded by this script. You give it the three things it needs and it says what it used (SHA-256 of each, written to the staged SOURCES.json and shown at the end), so you can compare them with
the values python.org and pypa.io publish:

  * the "embeddable package" of Python 3.12 for Windows 64-bit (python.org/downloads/windows, "Windows embeddable package (64-bit)")
  * get-pip.py (https://bootstrap.pypa.io/get-pip.py)
  * the Inno Setup compiler (https://jrsoftware.org/isinfo.php), only needed for the last step; `--stage-only` stops before it
  * the Delentia wheel: built here if you do not give one (this runs scripts/package_desk.py first, so the wheel carries the Desk; needs Node.js)

`--offline-wheels` also puts every dependency wheel for Windows / Python 3.12 into the installer (`pip download`, needs the internet now, makes the installer work without it later and much larger).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PYTHON_TAG = "312"

INSTALL_RUNTIME = r"""@echo off
rem Written by build_installer.py. Run by the installer after the files are copied: prepares pip and installs the Delentia wheel (and what it needs).
setlocal
set "APP=%~dp0"
set "LOG=%APP%install.log"
set "PY=%APP%python\python.exe"
set OFFLINE=
if exist "%APP%wheels" set OFFLINE=--no-index --find-links "%APP%wheels"
echo [%date% %time%] preparing pip > "%LOG%"
"%PY%" "%APP%get-pip.py" --no-warn-script-location --no-cache-dir %OFFLINE% >> "%LOG%" 2>&1
if errorlevel 1 exit /b 11
rem Some dependencies are published as source only. pip builds those in an isolated environment, and the embeddable Python (which ignores the paths pip hands to the build step) can not use it:
rem "Cannot import setuptools.build_meta". So the build tools go in first and the build uses them (--no-build-isolation).
echo [%date% %time%] installing the build tools >> "%LOG%"
"%PY%" -m pip install --no-warn-script-location --disable-pip-version-check --no-cache-dir %OFFLINE% setuptools wheel >> "%LOG%" 2>&1
if errorlevel 1 exit /b 14
echo [%date% %time%] installing %1 >> "%LOG%"
"%PY%" -m pip install --no-warn-script-location --disable-pip-version-check --no-cache-dir --no-build-isolation %OFFLINE% "%APP%wheel\%~1" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 12
"%PY%" -c "import rct_control_plane.cli" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 13
echo [%date% %time%] done >> "%LOG%"
exit /b 0
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def wheel_version(wheel: Path) -> str:
    parts = wheel.name.split("-")
    if len(parts) < 5 or not wheel.name.endswith(".whl") or not wheel.name.startswith("delentia_os-"):
        raise SystemExit(f"{wheel.name} is not a delentia_os wheel")
    return parts[1]


def file_version(version: str, revision: int = 0) -> str:
    """The four-number Windows file version: the runtime's X.Y.Z (a pre-release suffix such as rc1 is dropped) and the installer revision."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not m:
        raise SystemExit(f"{version!r} does not start with X.Y.Z")
    if not 0 <= revision <= 65535:
        raise SystemExit("the installer revision must be between 0 and 65535")
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}.{revision}"


def find_iscc(given: Optional[str]) -> Optional[Path]:
    candidates = [given] if given else []
    candidates += [shutil.which("ISCC"), shutil.which("iscc"), r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe",
                   str(Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe")]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    return None


def build_wheel(out_dir: Path) -> Path:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "package_desk.py")], check=True, cwd=str(ROOT))
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)], check=True, cwd=str(ROOT))
    wheels = sorted(out_dir.glob("delentia_os-*.whl"), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise SystemExit("the wheel was not built")
    return wheels[-1]


def stage(python_embed: Path, get_pip: Path, wheel: Path, stage_dir: Path, offline: bool = False) -> Dict[str, Any]:
    """Lay out everything the installer packs. Returns what was used (names and SHA-256)."""
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    (stage_dir / "python").mkdir(parents=True)
    (stage_dir / "wheel").mkdir()
    with zipfile.ZipFile(python_embed) as z:
        z.extractall(stage_dir / "python")
    pth = stage_dir / "python" / f"python{PYTHON_TAG}._pth"
    if not pth.is_file():
        raise SystemExit(f"{python_embed.name} does not look like the Python {PYTHON_TAG[0]}.{PYTHON_TAG[1:]} embeddable package (no {pth.name})")
    # The embeddable Python ignores site-packages and pip until its ._pth says otherwise.
    pth.write_text("\n".join([f"python{PYTHON_TAG}.zip", ".", "Lib\\site-packages", "", "import site", ""]), encoding="ascii")
    (stage_dir / "python" / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_pip, stage_dir / "get-pip.py")
    shutil.copy2(wheel, stage_dir / "wheel" / wheel.name)
    (stage_dir / "install_runtime.cmd").write_text(INSTALL_RUNTIME.replace("\n", "\r\n"), encoding="ascii")
    used: Dict[str, Any] = {
        "python_embed": {"file": python_embed.name, "sha256": sha256(python_embed)},
        "get_pip": {"file": get_pip.name, "sha256": sha256(get_pip)},
        "wheel": {"file": wheel.name, "sha256": sha256(wheel)},
        "offline_wheels": False,
    }
    if offline:
        wheels_dir = stage_dir / "wheels"
        wheels_dir.mkdir()
        cmd: List[str] = [sys.executable, "-m", "pip", "download", "--dest", str(wheels_dir), "--only-binary=:all:", "--platform", "win_amd64", "--python-version", f"{PYTHON_TAG[0]}.{PYTHON_TAG[1:]}",
                          "--implementation", "cp", str(wheel), "pip", "setuptools", "wheel"]
        subprocess.run(cmd, check=True)
        used["offline_wheels"] = True
        used["offline_count"] = len(list(wheels_dir.glob("*.whl")))
    (stage_dir / "SOURCES.json").write_text(json.dumps(used, indent=2), encoding="utf-8")
    return used


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python-embed", required=True, type=Path)
    ap.add_argument("--get-pip", required=True, type=Path)
    ap.add_argument("--wheel", type=Path, default=None)
    ap.add_argument("--iscc", default=None)
    ap.add_argument("--stage-dir", type=Path, default=HERE / "stage")
    ap.add_argument("--out", type=Path, default=HERE / "output")
    ap.add_argument("--offline-wheels", action="store_true")
    ap.add_argument("--stage-only", action="store_true")
    ap.add_argument("--installer-revision", type=int, default=0, help="the fourth number of the Windows file version: 0, or higher when the installer was rebuilt without a runtime change")
    args = ap.parse_args()
    for label, p in (("--python-embed", args.python_embed), ("--get-pip", args.get_pip)):
        if not p.is_file():
            print(f"{label} {p} does not exist", file=sys.stderr)
            return 2
    wheel = args.wheel or build_wheel(HERE / "wheel_build")
    version = wheel_version(wheel)
    used = stage(args.python_embed, args.get_pip, wheel, args.stage_dir, args.offline_wheels)
    print(f"staged {args.stage_dir} for Delentia {version}")
    for k in ("python_embed", "get_pip", "wheel"):
        print(f"  {k}: {used[k]['file']}  sha256 {used[k]['sha256']}")
    if args.stage_only:
        return 0
    iscc = find_iscc(args.iscc)
    if iscc is None:
        print("The Inno Setup compiler (ISCC.exe) was not found. Install Inno Setup 6 (jrsoftware.org/isinfo.php) or pass --iscc <path>. The files are staged; nothing else was done.", file=sys.stderr)
        return 3
    args.out.mkdir(parents=True, exist_ok=True)
    cmd = [str(iscc), f"/DAppVersion={version}", f"/DFileVersion={file_version(version, args.installer_revision)}", f"/DWheelName={wheel.name}", f"/DStageDir={args.stage_dir}", f"/O{args.out}", str(HERE / "delentia.iss")]
    subprocess.run(cmd, check=True, cwd=str(HERE))
    exe = args.out / f"Delentia-Setup-{version}.exe"
    if not exe.is_file():
        print("the compiler finished but the installer is not where it should be", file=sys.stderr)
        return 4
    # the same file under a fixed name, so that a link which never changes (releases/latest/download/Delentia-Setup.exe) always reaches the newest installer, and the checksums of both
    alias = args.out / "Delentia-Setup.exe"
    shutil.copyfile(exe, alias)
    digest = sha256(exe)
    sums = [f"{digest}  {exe.name}", f"{sha256(alias)}  {alias.name}"]
    (args.out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    print(f"built {exe}  ({exe.stat().st_size / 1e6:.1f} MB)  sha256 {digest}")
    print(f"      and {alias.name} (same file, fixed name) and SHA256SUMS.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
