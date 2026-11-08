"""
Round 112B (criteria R8): the installer's package step looked frozen on a clean computer. These checks read the installer script; the compile, the silent install, the check and the uninstall run on a
clean Windows runner in CI (windows-installer.yml), and what a person SEES is judged on the Architect's second computer.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import re
from pathlib import Path

ISS = Path(__file__).resolve().parents[2] / "installer" / "windows" / "delentia.iss"


def script() -> str:
    return ISS.read_text(encoding="utf-8-sig")


def test_the_bar_is_animated_during_the_package_step_and_back_to_normal_after():
    s = script()
    start = s.index("ssPostInstall")
    step = s[start:]
    assert step.index("npbstMarquee") < step.index("Exec(ExpandConstant('{cmd}')"), "the animation starts BEFORE the long step"
    assert step.rindex("npbstNormal") > step.index("Exec(ExpandConstant('{cmd}')"), "and is put back afterwards"


def test_the_text_says_it_is_not_a_percentage_and_needs_the_internet():
    s = script()
    caption = re.search(r"StatusLabel\.Caption := '([^']+)'", s).group(1)
    assert "not a percentage" in caption and "internet" in caption


def test_no_number_of_minutes_is_promised_because_none_was_measured_on_a_clean_computer():
    s = script()
    caption = re.search(r"StatusLabel\.Caption := '([^']+)'", s).group(1)
    assert not re.search(r"\d+\s*(minutes|min)\b", caption) and "few minutes" not in caption


def test_a_silent_install_still_ends_with_the_exit_code_and_shows_no_box():
    s = script()
    assert "ExitProcess(RuntimeCode)" in s and "if not IsSilentRun then" in s
