"""
Round 104: a demo folder whose sample quotes an earlier run changed (an approved `edit` demo changes vendor_a on purpose) used to make a later `compare` report two failed checks that were not a
fault of the system. Now the run says so BEFORE it starts and `delentia demo reset` puts the files back without deleting anything.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import subprocess
from pathlib import Path

import pytest

from rct_control_plane import demo

ROOT = Path(__file__).resolve().parents[2]
CHANGED_TEXT = "# ใบเสนอราคา แก้โดยเดโม edit\nราคารวม: 14,000 บาท\n"


def cli(args, env, timeout=600):
    return subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, env=env, timeout=timeout)


@pytest.fixture()
def folder(tmp_path):
    root = tmp_path / "delentia-demo"
    demo.init(root)
    return root


# ------------------------------------------------------------------ the functions
def test_a_fresh_folder_has_nothing_changed(folder):
    assert demo.changed_originals(folder) == []


def test_a_changed_or_missing_sample_file_is_reported(folder):
    (folder / "workspace" / "quotes" / "vendor_a.md").write_text(CHANGED_TEXT, encoding="utf-8")
    (folder / "workspace" / "quotes" / "vendor_c.md").unlink()
    assert demo.changed_originals(folder) == ["quotes/vendor_a.md", "quotes/vendor_c.md"]


def test_a_folder_without_a_baseline_is_not_called_changed(tmp_path):
    root = tmp_path / "d"
    demo.init(root)
    (root / "data" / "originals.json").unlink()
    (root / "workspace" / "quotes" / "vendor_a.md").write_text(CHANGED_TEXT, encoding="utf-8")
    assert demo.changed_originals(root) == []                      # nothing to compare with; init writes the baseline, a missing one is not evidence of change


def test_reset_restores_the_files_keeps_a_copy_and_deletes_nothing(folder):
    a = folder / "workspace" / "quotes" / "vendor_a.md"
    a.write_text(CHANGED_TEXT, encoding="utf-8")
    result_file = folder / "results" / "earlier-run.md"
    result_file.write_text("an earlier result", encoding="utf-8")
    out = demo.reset(folder)
    assert out["restored"] == ["quotes/vendor_a.md"] and "12,500" in a.read_text(encoding="utf-8")
    backup = Path(out["backup"])
    assert (backup / "quotes" / "vendor_a.md").read_text(encoding="utf-8") == CHANGED_TEXT and (backup / "originals.json").is_file()
    assert result_file.read_text(encoding="utf-8") == "an earlier result"
    assert demo.changed_originals(folder) == []
    again = demo.reset(folder)
    assert again["restored"] == [] and again["backup"] is None     # nothing to do, nothing created


def test_refuse_if_changed_applies_to_the_goals_that_check_the_originals_only(folder):
    (folder / "workspace" / "quotes" / "vendor_a.md").write_text(CHANGED_TEXT, encoding="utf-8")
    for key in ("compare", "budget", "edit"):
        with pytest.raises(SystemExit) as exc:
            demo.refuse_if_changed(folder, key, demo.resolve_goal(key))
        text = str(exc.value)
        assert "demo reset" in text and "vendor_a.md" in text and "Run `delentia demo reset`" in text
    with pytest.raises(SystemExit):
        demo.refuse_if_changed(folder, "your own sentence", "อ่าน quotes/vendor_a.md แล้วสรุป")
    demo.refuse_if_changed(folder, "remember", demo.resolve_goal("remember"))
    demo.refuse_if_changed(folder, "ask", demo.resolve_goal("ask"))


# ------------------------------------------------------------------ the command line, in separate processes
@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("demo_reset")
    root = base / "delentia-demo"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "USERPROFILE": str(base / "home"), "HOME": str(base / "home"),
           "DELENTIA_MODEL_CONFIG": str(base / "no-model.json"), "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": "nothing-is-listening",
           "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_LLM_RETRIES": "0", "DELENTIA_UPDATE_CHECK": "off"}
    for name in ("DELENTIA_HOME", "DELENTIA_REPO_ROOT", "DELENTIA_UNTRUSTED_PATHS", "DELENTIA_APPROVERS_FILE", "DELENTIA_AUDIT_SIGNING_KEY", "DELENTIA_WARM_RECALL", "RCT_DB_PATH",
                 "RCT_AGENTIC_DB_PATH", "DELENTIA_API_TOKEN", "DELENTIA_OPENAI_COMPAT_BASE_URL"):
        env.pop(name, None)
    assert cli(["demo", "init", "--dir", str(root)], env).returncode == 0
    return {"root": root, "env": env}


def test_a_changed_folder_stops_the_run_before_it_starts_and_reset_makes_the_same_run_pass(world):
    root, env = world["root"], world["env"]
    (root / "workspace" / "quotes" / "vendor_a.md").write_text(CHANGED_TEXT, encoding="utf-8")
    before = sorted(p.name for p in (root / "results").glob("*"))
    refused = cli(["demo", "run", "compare", "--scripted", "--dir", str(root)], env)
    assert refused.returncode != 0 and "demo reset" in (refused.stdout + refused.stderr)
    assert sorted(p.name for p in (root / "results").glob("*")) == before            # no run happened, no result file, no failed report
    reset = cli(["demo", "reset", "--dir", str(root)], env)
    assert reset.returncode == 0 and "quotes/vendor_a.md" in reset.stdout
    ok = cli(["demo", "run", "compare", "--scripted", "--dir", str(root)], env)
    assert ok.returncode == 0 and "ไม่ผ่าน" not in ok.stdout, ok.stdout[-1200:]
    nothing = cli(["demo", "reset", "--dir", str(root)], env)
    assert nothing.returncode == 0 and "ไม่ต้องทำอะไร" in nothing.stdout
    json.loads((root / "data" / "originals.json").read_text(encoding="utf-8"))
