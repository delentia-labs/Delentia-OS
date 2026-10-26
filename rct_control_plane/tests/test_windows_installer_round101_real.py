"""
Round 101C: the Windows installer's inputs. The Inno Setup compiler is not part of the test run (it is a separate program), so what is checked here is everything the compiler is given: the staged files built from a
real wheel and a stand-in for Python's embeddable zip, the script's promises (per-user, no start-up entry, the three shortcuts, the logo), and that the pictures are the sizes the compiler requires.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import hashlib
import importlib.util
import json
import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WIN = ROOT / "installer" / "windows"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_installer", WIN / "build_installer.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_installer"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _load_builder()


def _embed_zip(tmp_path, with_pth=True):
    path = tmp_path / "python-3.12.9-embed-amd64.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("python.exe", b"MZ stand-in")
        z.writestr("pythonw.exe", b"MZ stand-in")
        z.writestr("python312.dll", b"dll")
        z.writestr("python312.zip", b"stdlib")
        if with_pth:
            z.writestr("python312._pth", "python312.zip\n.\n\n# Uncomment to run site.main() automatically\n#import site\n")
    return path


def _wheel(tmp_path, version="9.9.9"):
    path = tmp_path / f"delentia_os-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"delentia_os-{version}.dist-info/METADATA", f"Metadata-Version: 2.1\nName: delentia-os\nVersion: {version}\n")
    return path


def _stage(builder, tmp_path):
    get_pip = tmp_path / "get-pip.py"
    get_pip.write_text("print('get-pip stand-in')\n", encoding="utf-8")
    wheel = _wheel(tmp_path)
    stage_dir = tmp_path / "stage"
    used = builder.stage(_embed_zip(tmp_path), get_pip, wheel, stage_dir)
    return stage_dir, used, wheel, get_pip


def test_staging_lays_out_python_the_wheel_pip_and_the_runtime_script(builder, tmp_path):
    stage_dir, used, wheel, get_pip = _stage(builder, tmp_path)
    for relative in ("python/python.exe", "python/pythonw.exe", "wheel/" + wheel.name, "get-pip.py", "install_runtime.cmd", "SOURCES.json"):
        assert (stage_dir / relative).is_file(), relative
    assert (stage_dir / "python" / "Lib" / "site-packages").is_dir()


def test_the_embeddable_python_is_told_to_use_site_packages_and_pip(builder, tmp_path):
    stage_dir, *_ = _stage(builder, tmp_path)
    pth = (stage_dir / "python" / "python312._pth").read_text(encoding="ascii").splitlines()
    assert "import site" in pth and "#import site" not in pth                               # without this line pip and every installed package are invisible
    assert "Lib\\site-packages" in pth and "python312.zip" in pth and "." in pth


def test_what_was_used_is_recorded_with_checksums_that_match_the_files(builder, tmp_path):
    stage_dir, used, wheel, get_pip = _stage(builder, tmp_path)
    recorded = json.loads((stage_dir / "SOURCES.json").read_text(encoding="utf-8"))
    assert recorded["wheel"]["sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert recorded["get_pip"]["sha256"] == hashlib.sha256(get_pip.read_bytes()).hexdigest()
    assert recorded["python_embed"]["file"].endswith("embed-amd64.zip") and recorded["offline_wheels"] is False


def test_the_runtime_script_logs_stops_at_the_first_failure_and_checks_the_import(builder, tmp_path):
    stage_dir, *_ = _stage(builder, tmp_path)
    raw = (stage_dir / "install_runtime.cmd").read_bytes()
    text = raw.decode("ascii")
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")                       # a batch file with bare line feeds misbehaves
    assert "get-pip.py" in text and "pip install" in text and "install.log" in text
    assert all(f"exit /b {code}" in text for code in (11, 12, 13)) and "import rct_control_plane.cli" in text
    assert "wheels" in text and "--no-index" in text                                         # the offline folder is used when the installer carries one


def test_a_zip_that_is_not_the_embeddable_python_is_refused(builder, tmp_path):
    get_pip = tmp_path / "get-pip.py"
    get_pip.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="embeddable package"):
        builder.stage(_embed_zip(tmp_path, with_pth=False), get_pip, _wheel(tmp_path), tmp_path / "stage")


def test_only_a_delentia_wheel_is_accepted(builder, tmp_path):
    assert builder.wheel_version(Path("delentia_os-2.3.1-py3-none-any.whl")) == "2.3.1"
    for bad in ("evil-1.0-py3-none-any.whl", "delentia_os-2.3.1.tar.gz", "delentia_os.whl"):
        with pytest.raises(SystemExit):
            builder.wheel_version(Path(bad))


def test_a_missing_compiler_is_reported_not_guessed(builder, tmp_path, monkeypatch):
    monkeypatch.setattr(builder.shutil, "which", lambda name: None)
    assert builder.find_iscc(str(tmp_path / "nope.exe")) != tmp_path / "nope.exe"          # a path that does not exist is never returned
    fake = tmp_path / "ISCC.exe"
    fake.write_bytes(b"x")
    assert builder.find_iscc(str(fake)) == fake


# ------------------------------------------------------------------ the script's promises
@pytest.fixture(scope="module")
def iss():
    return (WIN / "delentia.iss").read_text(encoding="utf-8")


def test_it_installs_for_the_current_person_only_with_no_administrator_rights(iss):
    assert "PrivilegesRequired=lowest" in iss and "{localappdata}\\Programs\\Delentia" in iss
    assert "{pf}" not in iss and "{commonpf" not in iss and "{sys}" not in iss


def test_nothing_runs_by_itself_after_installing(iss):
    for forbidden in ("[Registry]", "{userstartup}", "{commonstartup}", "{autostartup}", "HKLM", "Run\\", "schtasks", "sc create", "[Services]"):
        assert forbidden not in iss, forbidden


def test_the_three_shortcuts_exist_and_the_main_one_has_no_console_window(iss):
    icons = iss.split("[Icons]", 1)[1].split("[UninstallRun]", 1)[0]
    main = next(line for line in icons.splitlines() if line.startswith('Name: "{group}\\Delentia"'))
    assert "pythonw.exe" in main and "cli launch" in main and "delentia.ico" in main
    assert 'Name: "{group}\\Stop Delentia"' in icons and "launch --stop" in icons
    update = next(line for line in icons.splitlines() if line.startswith('Name: "{group}\\Update Delentia"'))
    assert "python.exe" in update and "pythonw" not in update and "update --apply" in update       # the update asks a question, so it needs a console window


def test_your_own_data_is_never_touched_by_install_or_uninstall(iss):
    assert ".delentia" not in iss.replace("%USERPROFILE%\\.delentia", "")                      # only mentioned in a comment
    delete = iss.split("[UninstallDelete]", 1)[1].split("[Code]", 1)[0]
    assert "{app}" in delete and "USERPROFILE" not in delete and "userdocs" not in delete


def test_a_failed_install_of_the_parts_is_said_in_a_window_not_hidden(iss):
    code = iss.split("[Code]", 1)[1]
    assert "MsgBox" in code and "install.log" in code and "ResultCode <> 0" in code and "internet" in code


def test_the_files_the_script_packs_are_the_files_staging_makes(iss, builder, tmp_path):
    stage_dir, *_ = _stage(builder, tmp_path)
    files = iss.split("[Files]", 1)[1].split("[Icons]", 1)[0]
    for source in re.findall(r'Source: "\{#StageDir\}\\([^\\"*]+)', files):
        optional = source == "wheels"
        assert optional or (stage_dir / source).exists(), source


def test_the_logo_files_exist_with_the_sizes_the_compiler_requires(iss):
    from PIL import Image
    for name in ("delentia.ico", "wizard.bmp", "wizard_small.bmp", "DelentiaIcon.png"):
        assert (WIN / name).is_file(), name
        assert name.split(".")[0] in iss or name == "DelentiaIcon.png"
    assert Image.open(WIN / "wizard.bmp").size == (164, 314) and Image.open(WIN / "wizard_small.bmp").size == (55, 58)
    ico = Image.open(WIN / "delentia.ico")
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(ico.info.get("sizes", set()))


def test_the_app_id_is_a_guid_and_the_version_comes_from_the_build(iss):
    assert re.search(r"AppId=\{\{[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}\}", iss)
    assert "AppVersion={#AppVersion}" in iss and "OutputBaseFilename=Delentia-Setup-{#AppVersion}" in iss


# ------------------------------------------------------------------ Round 101E: what the first real build and install showed
def test_source_only_dependencies_build_with_the_build_tools_installed_first_because_the_embeddable_python_cannot_isolate_a_build(builder, tmp_path):
    """Measured on the first real install: robotexclusionrulesparser is published as source only, pip's isolated build fails in the embeddable Python ("Cannot import setuptools.build_meta")."""
    stage_dir, *_ = _stage(builder, tmp_path)
    text = (stage_dir / "install_runtime.cmd").read_text(encoding="ascii")
    tools = text.index("setuptools wheel")
    main = text.rindex("--no-build-isolation")                 # the last mention is the install itself; the first is the comment
    assert tools < main and "exit /b 14" in text and "Cannot import setuptools.build_meta" in text
    assert text.count("--no-cache-dir") == 3                    # get-pip, the tools, the wheel: an unwritable pip cache must never stop an install


def test_a_silent_install_that_could_not_install_its_parts_does_not_end_with_exit_code_zero(iss):
    """Measured with the real compiler: RaiseException and Abort both leave exit code 0; only ExitProcess from DeinitializeSetup gives a non-zero code, with the uninstaller still in place."""
    code = iss.split("[Code]", 1)[1]
    assert "ExitProcess@kernel32.dll" in code and "procedure DeinitializeSetup" in code and "ExitProcess(RuntimeCode)" in code
    assert "ParamStr" in code and "/VERYSILENT" in code and "WizardSilent" not in code.replace("WizardSilent is false", "")      # WizardSilent is false under /VERYSILENT in Inno 6.7
    assert "RuntimeCode := ResultCode" in code and "RuntimeCode = 0 then RuntimeCode := 10" in code


def test_the_check_script_is_packed_and_has_a_shortcut(iss):
    assert 'Source: "check_install.py"' in iss
    icons = iss.split("[Icons]", 1)[1].split("[UninstallRun]", 1)[0]
    line = next(entry for entry in icons.splitlines() if "Check Delentia installation" in entry)
    assert "python.exe" in line and "pythonw" not in line and "check_install.py" in line and "--pause" in line      # it shows its result, so it needs a console window


def _fake_installed_app(tmp_path, log_tail="done"):
    app = tmp_path / "app"
    (app / "wheel").mkdir(parents=True)
    from rct_control_plane._version import PACKAGE_VERSION
    # the version of the code under test, so the check "installed version = the installer's wheel" never depends on a hard-coded number
    (app / "wheel" / f"delentia_os-{PACKAGE_VERSION}-py3-none-any.whl").write_bytes(b"x")
    (app / "install.log").write_text(f"preparing pip\ninstalling\n[date] {log_tail}\n", encoding="utf-8")
    return app


def _run_check(tmp_path, app, *extra):
    import subprocess
    env = {**os.environ, "PYTHONPATH": str(ROOT), "DELENTIA_DESK_DIR": str(tmp_path / "desk")}
    (tmp_path / "desk").mkdir(exist_ok=True)
    (tmp_path / "desk" / "index.html").write_text("<html><title>Delentia Desk</title></html>", encoding="utf-8")
    return subprocess.run([sys.executable, str(WIN / "check_install.py"), "--app-dir", str(app), "--python", sys.executable, *extra],
                          env=env, capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")


def test_the_check_script_says_fail_and_exits_non_zero_when_the_installers_log_does_not_end_with_done(tmp_path):
    result = _run_check(tmp_path, _fake_installed_app(tmp_path, log_tail="ERROR: Could not install packages"), "--no-start")
    assert result.returncode == 1 and "FAIL  1" in result.stdout and "does not end with 'done'" in result.stdout
    assert "Result: 1 FAILED" in result.stdout and (tmp_path / "app" / "check_install_report.txt").is_file()


def test_the_check_script_starts_the_program_on_free_ports_answers_and_stops_everything(tmp_path):
    app = _fake_installed_app(tmp_path)
    result = _run_check(tmp_path, app)
    assert result.returncode == 0, result.stdout + result.stderr
    for number in "123456":
        assert f"PASS  {number}" in result.stdout, result.stdout
    assert "Result: ALL PASSED" in result.stdout and "ผลการตรวจ: ผ่านทั้งหมด" in (app / "check_install_report.txt").read_text(encoding="utf-8")


# ------------------------------------------------------------------ Round 102: the installer has the runtime's number, plus a revision
@pytest.mark.parametrize("version,revision,expected", [("2.4.0", 0, "2.4.0.0"), ("2.4.0", 3, "2.4.0.3"), ("2.4.0rc1", 0, "2.4.0.0"), ("10.20.30", 65535, "10.20.30.65535")])
def test_the_windows_file_version_is_the_runtime_version_and_an_installer_revision(builder, version, revision, expected):
    assert builder.file_version(version, revision) == expected


@pytest.mark.parametrize("bad", ["garbage", "2.4", ""])
def test_a_version_that_is_not_x_y_z_is_refused(builder, bad):
    with pytest.raises(SystemExit):
        builder.file_version(bad)


def test_an_installer_revision_out_of_the_windows_range_is_refused(builder):
    for bad in (-1, 65536):
        with pytest.raises(SystemExit):
            builder.file_version("2.4.0", bad)


def test_the_script_gives_the_file_a_version_a_product_name_and_never_the_name_of_a_milestone(iss):
    setup = iss.split("[Setup]", 1)[1].split("[Languages]", 1)[0]
    for line in ("VersionInfoVersion={#FileVersion}", "VersionInfoProductVersion={#AppVersion}", "VersionInfoProductName=Delentia", "AppVersion={#AppVersion}"):
        assert line in setup, line
    assert "Preview" not in setup and "0.1" not in setup.replace("0.0.0", "")


def test_a_build_also_makes_the_fixed_name_copy_and_the_checksums_the_readme_links_to(builder, tmp_path, monkeypatch):
    import subprocess
    get_pip = tmp_path / "get-pip.py"
    get_pip.write_text("x", encoding="utf-8")
    wheel = _wheel(tmp_path, "9.9.9")
    out = tmp_path / "out"
    fake_iscc = tmp_path / "ISCC.exe"
    fake_iscc.write_bytes(b"x")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        out.mkdir(exist_ok=True)
        (out / "Delentia-Setup-9.9.9.exe").write_bytes(b"installer bytes")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(builder.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["build_installer.py", "--python-embed", str(_embed_zip(tmp_path)), "--get-pip", str(get_pip), "--wheel", str(wheel), "--iscc", str(fake_iscc),
                                      "--stage-dir", str(tmp_path / "stage"), "--out", str(out), "--installer-revision", "2"])
    assert builder.main() == 0
    assert "/DFileVersion=9.9.9.2" in seen["cmd"] and "/DAppVersion=9.9.9" in seen["cmd"]
    assert (out / "Delentia-Setup.exe").read_bytes() == b"installer bytes"
    sums = (out / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    digest = hashlib.sha256(b"installer bytes").hexdigest()
    assert sums == [f"{digest}  Delentia-Setup-9.9.9.exe", f"{digest}  Delentia-Setup.exe"]
