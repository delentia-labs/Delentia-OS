"""
Round 109: the Desk's button "Show the code in a small window" (setup_assistant.open_code_window) in the installed program.

The Windows installer starts Delentia with pythonw.exe (no black window), and the agent it starts inherits that interpreter. A new console opened for pythonw.exe is invisible, so the button
answered "a window opened" and showed nothing, and the person never saw the one-time code. Found by measuring: a child of pythonw.exe started with CREATE_NEW_CONSOLE has no console window, a
child of python.exe has one. The window must be started with the python.exe that sits next to pythonw.exe.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import subprocess
from pathlib import Path

import pytest

from rct_control_plane import approvals, setup_assistant as sa
from rct_control_plane.tests.test_setup_assistant_round106_real import _FakePopen, make_persistence


@pytest.fixture(autouse=True)
def nobody_can_approve_yet(tmp_path, monkeypatch):
    """The button only works while nobody can approve: keep this machine's real approver key and data home out of the test."""
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)


def test_pythonw_is_replaced_by_the_python_exe_beside_it(tmp_path):
    (tmp_path / "python.exe").write_bytes(b"")
    (tmp_path / "pythonw.exe").write_bytes(b"")
    assert sa.console_interpreter(str(tmp_path / "pythonw.exe")) == str(tmp_path / "python.exe")
    assert sa.console_interpreter(str(tmp_path / "PYTHONW.EXE")) == str(tmp_path / "python.exe")      # Windows file names do not care about case
    assert sa.console_interpreter(str(tmp_path / "python.exe")) == str(tmp_path / "python.exe")        # an interpreter with a console is left alone
    assert sa.console_interpreter("/usr/bin/python3") == "/usr/bin/python3"


def test_without_a_python_exe_beside_pythonw_no_window_is_claimed(tmp_path, monkeypatch):
    (tmp_path / "pythonw.exe").write_bytes(b"")                                       # no python.exe next to it
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    monkeypatch.setattr(sa, "_LAST_CODE_WINDOW", [0.0])
    fake = _FakePopen()
    answer = sa.open_code_window(make_persistence(tmp_path), popen=fake, platform="win32", now=1000.0)
    assert answer["opened"] is False and answer["reason"] == "no_window" and "first-device-code" in answer["how"]
    assert fake.calls == []                                                           # nothing was started that the person could not see


def test_the_window_command_uses_the_console_interpreter_when_the_agent_runs_under_pythonw(tmp_path, monkeypatch):
    (tmp_path / "python.exe").write_bytes(b"")
    (tmp_path / "pythonw.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    monkeypatch.setattr(sa, "_LAST_CODE_WINDOW", [0.0])
    fake = _FakePopen()
    answer = sa.open_code_window(make_persistence(tmp_path), popen=fake, platform="win32", now=1000.0)
    assert answer["opened"] is True
    command, _ = fake.calls[0]
    assert command[0] == str(tmp_path / "python.exe") and command[1:5] == ["-m", "rct_control_plane.cli", "approvals", "first-device-code"]


@pytest.mark.skipif(sys.platform != "win32", reason="consoles exist only on Windows")
def test_on_windows_the_interpreter_chosen_really_gets_a_console_window(tmp_path):
    """The real thing, no mock: a child of the chosen interpreter, started the way the button starts it, has a console window; one of pythonw.exe does not."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file() or not Path(sys.executable).with_name("python.exe").is_file():
        pytest.skip("this Python has no pythonw.exe / python.exe pair")
    probe = "import ctypes,sys;open(sys.argv[1],'w').write('1' if ctypes.windll.kernel32.GetConsoleWindow() else '0')"

    def has_window(interpreter: str, name: str) -> str:
        out = tmp_path / name
        subprocess.Popen([interpreter, "-c", probe, str(out)], creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True).wait(30)
        return out.read_text()

    assert has_window(str(pythonw), "pythonw.txt") == "0"                              # the defect: nothing to see
    assert has_window(sa.console_interpreter(str(pythonw)), "chosen.txt") == "1"       # the fix: a window
