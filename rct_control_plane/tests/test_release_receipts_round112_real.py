"""
Round 112: the release-receipts script (DEL-PTP-03 and DEL-PTP-05). Its pure parts are tested here; the real run (pip install from PyPI, GitHub, the demos) is what the script is FOR and was tried
against the published 2.4.3 (receipt kept with the plan). A check that did not run must never read as a pass.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import release_receipts as rr


def test_the_approval_id_is_found_with_or_without_the_backticks_the_report_prints():
    assert rr.find_approval_id("- **Waiting for approval, id `8c660f8afc0b`** -> `delentia demo approve 8c660f8afc0b`") == "8c660f8afc0b"
    assert rr.find_approval_id("Waiting for approval, id 0813ebb5e05b  ->  delentia demo approve 0813ebb5e05b") == "0813ebb5e05b"
    assert rr.find_approval_id("รออนุมัติ รหัส abcdef123456  →  delentia demo approve abcdef123456") == "abcdef123456"
    assert rr.find_approval_id("nothing is waiting") is None and rr.find_approval_id("") is None and rr.find_approval_id(None) is None


def test_the_checksum_file_is_read_with_or_without_the_binary_marker():
    text = ("a" * 64 + " *Delentia-Setup-2.4.4.exe\n" + "b" * 64 + "  Delentia-Setup.exe\nnot a line\n" + "C" * 64 + " other.whl\n")
    assert rr.parse_checksums(text) == {"Delentia-Setup-2.4.4.exe": "a" * 64, "Delentia-Setup.exe": "b" * 64, "other.whl": "c" * 64}


def test_the_demo_report_checks_are_counted():
    report = "## The answer checked\n- passed: a\n- passed: b\n- FAILED: c\n- passed: d\n"
    assert rr.count_passed_checks(report) == {"passed": 3, "failed": 1}


def test_a_check_that_did_not_run_never_counts_as_a_pass():
    ok = rr.check("A", "t", "pass", "d")
    skipped = rr.check("B", "t", "not_run", "d")
    broken = rr.check("C", "t", "fail", "d")
    assert rr.verdict([ok, ok]) == "pass"
    assert rr.verdict([ok, skipped]) == "incomplete"
    assert rr.verdict([ok, skipped, broken]) == "fail"
    assert rr.verdict([]) == "incomplete"


def test_a_status_word_outside_the_three_is_refused():
    import pytest
    with pytest.raises(AssertionError):
        rr.check("A", "t", "ok", "d")


def test_sha256_of_a_file(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    assert rr.sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_the_script_only_uses_the_standard_library():
    src = open(os.path.join(os.path.dirname(rr.__file__), "release_receipts.py"), encoding="utf-8").read()
    for line in src.splitlines():
        if line.startswith(("import ", "from ")) and "__future__" not in line:
            assert line.split()[1].split(".")[0] in {"argparse", "hashlib", "json", "os", "platform", "re", "shutil", "sqlite3", "subprocess", "sys", "tempfile", "time", "urllib", "pathlib", "typing"}, line
