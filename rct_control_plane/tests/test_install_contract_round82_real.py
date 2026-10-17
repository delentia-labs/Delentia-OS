"""
Round 82, plan item T03: the install-contract checker (scripts/check_installed_wheel.py) really checks.

The full contract is run in CI on a freshly built wheel (package-check.yml). Here the checker's own logic is tested in the development environment: the fast checks pass, and each check FAILS
when the thing it guards is broken (so a green receipt means something).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import json
from pathlib import Path

import pytest

import check_installed_wheel as contract


@pytest.fixture
def box(tmp_path, monkeypatch):
    # The checks start child processes in a temporary folder. In the development checkout (CI runs the tests from one, without installing the package) the child can
    # only import rct_control_plane if the repository is on its path; on a machine where the package is installed this changes nothing.
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(p for p in (str(Path(__file__).resolve().parents[2]), os.environ.get("PYTHONPATH", "")) if p))
    return contract.Sandbox(tmp_path / "box")


def test_the_environment_a_check_runs_in_cannot_reach_real_data(box, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("DELENTIA_API_TOKEN", "token-should-not-leak")
    env = box.env()
    assert "OPENROUTER_API_KEY" not in env and "DELENTIA_API_TOKEN" not in env
    assert env["DELENTIA_HOME"] == str(box.home) and env["HOME"] == str(box.user) and env["USERPROFILE"] == str(box.user)


def test_the_import_and_cli_checks_pass_here_and_a_failing_import_fails_the_check(box, monkeypatch):
    assert contract.check_imports(box)["ok"] and contract.check_cli(box)["ok"]
    monkeypatch.setattr(contract, "FIRST_IMPORTS", ("rct_control_plane.cli", "rct_control_plane.module_that_does_not_exist"))
    broken = contract.check_imports(box)
    assert broken["ok"] is False and "module_that_does_not_exist" in broken["detail"]


def test_a_server_that_exits_at_once_fails_the_serve_check(box, monkeypatch):
    monkeypatch.setattr(contract, "delentia_cmd", lambda *args: [contract.PY, "-c", "raise SystemExit(3)"])
    outcome = contract.check_serve(box)
    assert outcome["ok"] is False and "did not answer" in outcome["detail"]


def test_the_memory_check_fails_when_the_next_process_does_not_see_the_memory(box, monkeypatch):
    monkeypatch.setattr(contract, "delentia_cmd", lambda *args: [contract.PY, "-c", "print('nothing stored')"] if args[:1] == ("memory",) else [contract.PY, "-c", "raise SystemExit(3)"])
    outcome = contract.check_memory(box)
    assert outcome["ok"] is False and "seen_next_process=False" in outcome["detail"]


def test_the_demo_check_fails_when_the_steps_fail(box, monkeypatch):
    monkeypatch.setattr(contract, "delentia_cmd", lambda *args: [contract.PY, "-c", "raise SystemExit(2)"])
    outcome = contract.check_demo(box)
    assert outcome["ok"] is False and "failed steps" in outcome["detail"]


def test_the_readonly_check_says_when_it_is_skipped_rather_than_pretending(box, monkeypatch):
    monkeypatch.setattr(contract, "IS_POSIX", False)
    outcome = contract.check_readonly(box)
    assert outcome["ok"] is True and outcome["detail"].startswith("SKIPPED")


def test_main_writes_a_receipt_and_the_exit_code_follows_the_checks(tmp_path, monkeypatch):
    monkeypatch.setitem(contract.RUNNERS, "imports", lambda box: contract.result("imports", True, "fine"))
    monkeypatch.setitem(contract.RUNNERS, "cli", lambda box: contract.result("cli", False, "broken"))
    receipt = tmp_path / "receipt.json"
    code = contract.main(["--receipt", str(receipt), "--skip", "demo", "--skip", "serve", "--skip", "memory", "--skip", "readonly"])
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert code == 1 and data["all_passed"] is False and [c["check"] for c in data["checks"]] == ["imports", "cli"]


def test_the_workflow_runs_the_contract_on_the_built_wheel_and_checks_the_extras():
    text = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "package-check.yml").read_text(encoding="utf-8")
    assert "scripts/check_installed_wheel.py" in text and "install-receipt" in text
    for extra in ("video:cv2", "vector:faiss", "graph:networkx", "llm:openai"):
        assert extra in text
