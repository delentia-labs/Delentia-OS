"""
Round 109: what the person sees when the Windows installer finishes.

The owner asked that the program be reachable from the desktop like any other program, without hunting in the Start menu. So: the desktop icon task is ticked by default (a person can untick it), and
the last page of the installer offers "Open Delentia now" (ticked) which starts the program the same way the shortcut does. Neither may happen under a silent install, so CI and scripted installs
never start the program. These tests read the installer script the compiler is given, as the older installer tests do; the compiler itself runs in the Windows installer workflow.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pathlib import Path

ISS = (Path(__file__).resolve().parents[2] / "installer" / "windows" / "delentia.iss").read_text(encoding="utf-8")


def _section(name: str) -> str:
    body = ISS.split(f"[{name}]", 1)[1]
    return body.split("\n[", 1)[0]


def test_the_desktop_icon_is_offered_ticked_and_starts_the_program_like_the_start_menu_entry():
    task = next(line for line in _section("Tasks").splitlines() if line.startswith('Name: "desktopicon"'))
    assert "unchecked" not in task                                                          # ticked unless the person unticks it
    icons = _section("Icons")
    desktop = next(line for line in icons.splitlines() if line.startswith('Name: "{autodesktop}\\Delentia"'))
    start = next(line for line in icons.splitlines() if line.startswith('Name: "{group}\\Delentia"'))
    assert 'Tasks: desktopicon' in desktop
    for part in ('Filename: "{app}\\python\\pythonw.exe"', 'Parameters: "-m rct_control_plane.cli launch"', 'IconFilename: "{app}\\delentia.ico"'):
        assert part in desktop and part in start                                            # the same program, the same arguments, the same icon


def test_the_last_page_offers_to_open_delentia_and_never_does_so_under_a_silent_install():
    run = [line for line in _section("Run").splitlines() if line.strip() and not line.startswith(";")]
    assert len(run) == 1
    line = run[0]
    assert 'Parameters: "-m rct_control_plane.cli launch"' in line and "pythonw.exe" in line   # no black window, the same start as the shortcut
    assert "postinstall" in line and "skipifsilent" in line and "nowait" in line
    assert "unchecked" not in line                                                          # ticked by default
    assert "launch --stop" not in line


def test_the_uninstaller_still_stops_what_the_program_started_before_removing_it():
    assert "launch --stop" in _section("UninstallRun")
