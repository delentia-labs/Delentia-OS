"""
Round 109: apps/browser-demo/runner.py, the part of the browser demo that runs the scripted demos on a server. The page (app.py, Gradio) only shows what this returns, so this is what is tested,
against the real demo commands (no mocks of the demo, the gate or the audit chain):
  * each scenario produces the report a person would get at the command line, with the "scripted stand-in" notice on it;
  * the injection scenario stops and waits for a signature, and refusing it leaves the quote unchanged;
  * nothing a visitor sends reaches a command: an unknown scenario or language is refused before anything runs;
  * every run uses its own folder and data home under the temp directory and removes them; this machine's real data home is never touched;
  * a run that takes too long is stopped with a message that is safe to show.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("browser_demo_runner", ROOT / "apps" / "browser-demo" / "runner.py")
runner = importlib.util.module_from_spec(spec)
sys.modules["browser_demo_runner"] = runner
spec.loader.exec_module(runner)


@pytest.fixture(autouse=True)
def child_finds_this_checkout(monkeypatch, tmp_path):
    """The runner starts `python -m rct_control_plane.cli` as a child: make it import this checkout. TMPDIR points into the test's own folder so leftovers are visible."""
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


def _leftovers(tmp_path):
    return [p.name for p in tmp_path.iterdir() if p.name.startswith("delentia-browser-demo-")]


def test_the_compare_scenario_runs_the_real_demo_and_says_the_model_is_scripted(tmp_path):
    report = runner.run_scenario("compare", "en")
    assert "SCRIPTED stand-in for the model" in report
    assert "audit chain: intact" in report
    assert "passed" in report and "failed" not in report.lower().replace("not failed", "")
    assert _leftovers(tmp_path) == []                                          # the run's folder is gone


def test_the_injection_scenario_stops_and_waits_for_a_signature(tmp_path):
    report = runner.run_scenario("injection", "en")
    assert "waiting for a person's signature" in report or "waiting for an approver's signature" in report
    assert "HIJACKED model" in report
    assert "Waiting for approval, id" in report
    assert "the quote was not changed" in report


def test_refusing_the_change_is_shown_and_leaves_the_quote_alone(tmp_path):
    report = runner.run_scenario("injection_refused", "en")
    assert "You refused the change" in report
    assert "the quote was not changed" in report
    assert _leftovers(tmp_path) == []


def test_the_thai_demo_runs_too(tmp_path):
    report = runner.run_scenario("compare", "th")
    assert "audit chain" in report.lower() or "บันทึก" in report
    assert _leftovers(tmp_path) == []


@pytest.mark.parametrize("name,lang", [("rm -rf /", "en"), ("compare; whoami", "en"), ("../compare", "en"), ("", "en"), ("compare", "fr"), ("compare", "en --dir /etc"), ("compare", "")])
def test_nothing_a_visitor_sends_reaches_a_command(name, lang, monkeypatch):
    called = []
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: called.append(a) or None)
    with pytest.raises(runner.DemoError):
        runner.run_scenario(name, lang)
    assert called == []                                                        # refused before any process started


def test_every_run_has_its_own_folder_and_none_of_the_hosts_data_is_touched(tmp_path, monkeypatch):
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setenv("DELENTIA_HOME", str(real_home))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-a-secret-that-must-not-reach-the-child")
    seen = []
    real_run = runner.subprocess.run

    def spy(args, **kwargs):
        seen.append((args, kwargs["env"], kwargs["cwd"]))
        return real_run(args, **kwargs)
    monkeypatch.setattr(runner.subprocess, "run", spy)
    runner.run_scenario("compare", "en")
    homes = {env["DELENTIA_HOME"] for _, env, _ in seen}
    assert len(homes) == 1 and str(real_home) not in homes                     # one throw-away home for the run, never the host's
    assert all("OPENROUTER_API_KEY" not in env for _, env, _ in seen)         # the host's secrets are not passed on
    assert all(cwd.startswith(str(tmp_path)) for _, _, cwd in seen)
    assert list(real_home.iterdir()) == []                                     # nothing was written to the host's data home
    seen.clear()
    runner.run_scenario("compare", "en")
    assert {env["DELENTIA_HOME"] for _, env, _ in seen} != homes               # the second run did not reuse the first run's folder


def test_a_run_that_takes_too_long_is_stopped_with_a_safe_message(tmp_path):
    with pytest.raises(runner.DemoError) as why:
        runner.run_scenario("compare", "en", time_limit_s=0.01)
    assert "too long" in str(why.value)
    assert _leftovers(tmp_path) == []                                          # even a stopped run is cleaned up


def test_a_report_is_cut_at_the_size_limit(monkeypatch):
    monkeypatch.setattr(runner, "MAX_REPORT_CHARS", 500)
    assert len(runner.run_scenario("compare", "en")) <= 500


def test_the_intro_says_what_the_visitor_is_looking_at_in_both_languages():
    assert "not a real model" in runner.intro("en")
    assert "ไม่ใช่โมเดลจริง" in runner.intro("th")


def test_the_page_defines_one_button_per_scenario_and_asks_for_no_text():
    source = (ROOT / "apps" / "browser-demo" / "app.py").read_text(encoding="utf-8")
    assert "gr.Textbox" not in source and "gr.File" not in source and "gr.Chatbot" not in source      # no free text, no upload
    assert set(runner.LABELS) == {"compare", "injection", "injection_refused"}
