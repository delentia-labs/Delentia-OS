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


def progress_text():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_installer_r112", ISS.parent / "build_installer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_takes_its_caption_from_the_include_and_has_an_english_fallback():
    s = script()
    assert "{#ProgressStatusEN}" in s and "{#ProgressStatusTH}" in s and "{#ProgressDetailEN}" in s and "{#ProgressDetailTH}" in s
    assert 'AddBackslash(StageDir) + "progress.iss"' in s and "#ifndef ProgressStatusEN" in s


def test_the_text_says_it_is_not_a_percentage_and_needs_the_internet():
    t = progress_text().PROGRESS_TEXT
    assert "not a percentage" in t["en_status"] and "internet" in t["en_status"] and "internet" in t["en_detail"]


def test_no_number_of_minutes_is_promised_because_none_was_measured_on_a_clean_computer():
    t = progress_text().PROGRESS_TEXT
    for key in ("en_status", "en_detail", "th_status", "th_detail"):
        assert not re.search(r"\d+\s*(minutes|min|นาที)", t[key]) and "few minutes" not in t[key], key


def test_the_thai_text_says_the_same_things_point_for_point():
    t = progress_text().PROGRESS_TEXT
    assert re.search(r"[\u0E00-\u0E7F]", t["th_status"]) and re.search(r"[\u0E00-\u0E7F]", t["th_detail"])
    for point in ("ขั้นที่ 2 จาก 2", "อินเทอร์เน็ต", "ไม่ใช่เปอร์เซ็นต์", "อย่าปิดหน้าต่าง"):          # step 2 of 2, internet, not a percentage, do not close
        assert point in t["th_status"], point
    assert "install.log" in t["th_detail"] and "อินเทอร์เน็ต" in t["th_detail"]


def test_the_include_is_written_with_a_byte_order_mark_and_all_four_names(tmp_path):
    module = progress_text()
    module.write_progress_text(tmp_path)
    raw = (tmp_path / "progress.iss").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "without the mark the compiler would read the Thai as something else"
    text = raw.decode("utf-8-sig")
    for name in ("ProgressStatusEN", "ProgressStatusTH", "ProgressDetailEN", "ProgressDetailTH"):
        assert f"#define {name} " in text
    assert "ขั้นที่ 2 จาก 2" in text


def test_the_build_script_writes_it_next_to_the_stage_label():
    src = (ISS.parent / "build_installer.py").read_text(encoding="utf-8")
    assert "write_progress_text(args.stage_dir)" in src


def test_a_silent_install_still_ends_with_the_exit_code_and_shows_no_box():
    s = script()
    assert "ExitProcess(RuntimeCode)" in s and "if not IsSilentRun then" in s
