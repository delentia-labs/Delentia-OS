"""
Round 107: the model-free demo in English (`delentia demo init --lang en`).

The first demo was Thai only, so someone who found the project from an English page ran the two-minute path and read a screen they could not read. These tests run the real CLI in
separate processes with NO model configured (the same setup as the Thai ones) and check four things:
  * the English folder works end to end: compare passes every check, edit stops for a signature and changes nothing, approve changes exactly one file, reset puts it back;
  * everything a person reads is English (no Thai characters in the report, in the notice or in the messages);
  * the Thai default is untouched: a folder made without --lang is Thai, and asking for English on a folder that already exists does not change its language;
  * the English text does not weaken the checks: a wrong English answer (a vendor over budget called "within budget") still fails.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
THAI = re.compile(r"[฀-๿]")


def cli(args, env, timeout=600):
    return subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, env=env, timeout=timeout)


def make_env(base):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "USERPROFILE": str(base / "home"), "HOME": str(base / "home"),
           "DELENTIA_MODEL_CONFIG": str(base / "no-model.json"), "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": "nothing-is-listening",
           "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_LLM_RETRIES": "0", "DELENTIA_UPDATE_CHECK": "off"}
    for name in ("DELENTIA_HOME", "DELENTIA_REPO_ROOT", "DELENTIA_UNTRUSTED_PATHS", "DELENTIA_APPROVERS_FILE", "DELENTIA_AUDIT_SIGNING_KEY", "DELENTIA_WARM_RECALL", "RCT_DB_PATH",
                 "RCT_AGENTIC_DB_PATH", "DELENTIA_API_TOKEN", "DELENTIA_OPENAI_COMPAT_BASE_URL", "DELENTIA_DEMO_LANG"):
        env.pop(name, None)
    return env


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("english_demo")
    root = base / "delentia-demo-en"
    env = make_env(base)
    init = cli(["demo", "init", "--lang", "en", "--dir", str(root)], env)
    assert init.returncode == 0, init.stderr[-600:]
    return {"root": root, "env": env, "init": init, "base": base}


@pytest.fixture(scope="module")
def compare_run(world):
    return cli(["demo", "run", "compare", "--scripted", "--dir", str(world["root"])], world["env"])


class TestEnglishFolder:
    def test_init_writes_english_quotes_and_remembers_the_language(self, world):
        root = world["root"]
        assert (root / "lang.txt").read_text(encoding="utf-8").strip() == "en"
        text = (root / "workspace" / "quotes" / "vendor_a.md").read_text(encoding="utf-8")
        assert "Total price: 12,500 USD" in text and not THAI.search(text)
        assert (root / "README_EN.md").exists() and not (root / "README_TH.md").exists()
        assert not THAI.search(world["init"].stdout), world["init"].stdout

    def test_compare_runs_without_a_model_every_check_passes_and_the_screen_is_english(self, world, compare_run):
        out = compare_run.stdout
        assert compare_run.returncode == 0, (out[-1500:], compare_run.stderr[-600:])
        assert out.count("- `delentia_read_repo_file` {") == 3
        assert "FAILED" not in out and out.count("- passed:") >= 5
        assert "audit chain: intact" in out and "Harbor HVAC" in out and "over budget" in out
        assert not THAI.search(out), "Thai text on an English screen: " + "".join(sorted(set(THAI.findall(out))))

    def test_the_report_says_the_model_is_scripted_in_english(self, world, compare_run):
        text = sorted((world["root"] / "results").glob("*compare*.md"))[-1].read_text(encoding="utf-8")
        assert "SCRIPTED stand-in for the model" in text and "says nothing about the ability of any model" in text
        assert "Model:** script (not a real model)" in text

    def test_a_read_below_the_threshold_says_why_it_passed(self, world, compare_run):
        out = compare_run.stdout
        gate = [line for line in out.splitlines() if line.startswith("- `delentia_read_repo_file`: D=")]
        assert gate
        for line in gate:
            f = float(re.search(r"F=([\d.]+)", line).group(1))
            threshold = float(re.search(r"threshold ([\d.]+)", line).group(1))
            if f < threshold:
                assert "the D/I threshold is not applied to reads" in line, line

    def test_reading_the_quotes_counts_as_reading_outside_text(self, world, compare_run):
        assert "read text from outside" in compare_run.stdout

    def test_edit_stops_for_a_signature_and_changes_nothing_until_approved(self, world, compare_run):
        root = world["root"]
        before = (root / "workspace" / "quotes" / "vendor_a.md").read_text(encoding="utf-8")
        run = cli(["demo", "run", "edit", "--scripted", "--dir", str(root)], world["env"])
        assert "pending_approval" in run.stdout and "waiting for an approver" in run.stdout, run.stdout[-1500:]
        assert (root / "workspace" / "quotes" / "vendor_a.md").read_text(encoding="utf-8") == before
        approval = re.search(r"Waiting for approval, id (\w+)\s+->\s+delentia demo approve", run.stdout)
        assert approval, run.stdout[-800:]
        assert not THAI.search(run.stdout)
        done = cli(["demo", "approve", approval.group(1), "--scripted", "--dir", str(root)], world["env"])
        assert done.returncode == 0, done.stdout[-800:] + done.stderr[-400:]
        assert "Total price: 14,000 USD" in (root / "workspace" / "quotes" / "vendor_a.md").read_text(encoding="utf-8")
        assert "quotes/vendor_a.md" in done.stdout and not THAI.search(done.stdout)
        again = cli(["demo", "approve", approval.group(1), "--scripted", "--dir", str(root)], world["env"])
        assert again.returncode != 0 and "a signature works once" in (again.stdout + again.stderr) or again.returncode != 0

    def test_a_changed_folder_is_refused_before_the_run_in_english_and_reset_puts_the_english_text_back(self, world):
        root = world["root"]
        refused = cli(["demo", "run", "compare", "--scripted", "--dir", str(root)], world["env"])
        message = refused.stdout + refused.stderr
        assert refused.returncode != 0 and "demo reset" in message and not THAI.search(message), message[-800:]
        reset = cli(["demo", "reset", "--dir", str(root)], world["env"])
        assert reset.returncode == 0 and "Sample files restored" in reset.stdout and not THAI.search(reset.stdout)
        restored = (root / "workspace" / "quotes" / "vendor_a.md").read_text(encoding="utf-8")
        assert "Total price: 12,500 USD" in restored and not THAI.search(restored)
        again = cli(["demo", "run", "compare", "--scripted", "--dir", str(root)], world["env"])
        assert again.returncode == 0 and "- passed:" in again.stdout


class TestThaiDefaultIsUntouched:
    def test_a_folder_made_without_lang_is_thai_and_has_no_lang_file(self, tmp_path):
        env = make_env(tmp_path)
        root = tmp_path / "th"
        init = cli(["demo", "init", "--dir", str(root)], env)
        assert init.returncode == 0
        assert not (root / "lang.txt").exists() and (root / "README_TH.md").exists()
        assert "ใบเสนอราคา" in (root / "workspace" / "quotes" / "vendor_a.md").read_text(encoding="utf-8")

    def test_asking_for_english_on_an_existing_thai_folder_does_not_change_it(self, tmp_path):
        env = make_env(tmp_path)
        root = tmp_path / "th"
        cli(["demo", "init", "--dir", str(root)], env)
        again = cli(["demo", "init", "--lang", "en", "--dir", str(root)], env)
        assert again.returncode == 0 and not (root / "lang.txt").exists()
        assert "ใบเสนอราคา" in (root / "workspace" / "quotes" / "vendor_a.md").read_text(encoding="utf-8")

    def test_the_environment_default_can_choose_english_for_a_new_folder_only(self, tmp_path):
        env = {**make_env(tmp_path), "DELENTIA_DEMO_LANG": "en"}
        root = tmp_path / "from-env"
        assert cli(["demo", "init", "--dir", str(root)], env).returncode == 0
        assert (root / "lang.txt").read_text(encoding="utf-8").strip() == "en"
        thai = tmp_path / "explicit-th"
        assert cli(["demo", "init", "--lang", "th", "--dir", str(thai)], env).returncode == 0
        assert not (thai / "lang.txt").exists()


class TestEnglishChecksStillCatchWrongAnswers:
    """The checker is a plain function: it must not be easier to satisfy in English than in Thai."""

    def setup_method(self):
        from rct_control_plane import demo
        self.demo = demo

    def _folder(self, tmp_path):
        self.demo.init(tmp_path, "en")
        workspace = tmp_path / "workspace"
        originals = {rel: __import__("hashlib").sha256((workspace / rel).read_bytes()).hexdigest() for rel in self.demo.QUOTES}
        return workspace, originals

    def test_a_right_answer_passes_every_check(self, tmp_path):
        from rct_control_plane import demo_scripted
        workspace, originals = self._folder(tmp_path)
        rows = demo_scripted._read_quotes(workspace, list(self.demo.QUOTES), "en")
        checks = self.demo.check_compare(demo_scripted.compare_answer(rows, 15000, "en"), workspace, originals, 15000, "en")
        assert all(c["ok"] for c in checks), checks

    def test_calling_the_vendor_that_is_over_budget_within_budget_fails(self, tmp_path):
        workspace, originals = self._folder(tmp_path)
        wrong = ("| Vendor | Price |\n|---|---|\n| Harbor HVAC | 9,900 | within budget |\n| Northwind Cooling | 12,500 | within budget |\n"
                 "| Polar Systems | 16,800 | within budget |\n")
        checks = self.demo.check_compare(wrong, workspace, originals, 15000, "en")
        assert [c for c in checks if not c["ok"]] and any("Polar Systems" in c["check"] and not c["ok"] for c in checks)

    def test_a_table_missing_a_price_fails(self, tmp_path):
        workspace, originals = self._folder(tmp_path)
        checks = self.demo.check_compare("Harbor HVAC 9,900 within budget\nNorthwind Cooling within budget\nPolar Systems over budget", workspace, originals, 15000, "en")
        assert not checks[0]["ok"]

    def test_a_changed_original_fails_the_unchanged_check(self, tmp_path):
        workspace, originals = self._folder(tmp_path)
        (workspace / "quotes" / "vendor_b.md").write_text("tampered", encoding="utf-8")
        from rct_control_plane import demo_scripted
        rows = [{"vendor": "Harbor HVAC", "price": 9900, "days": 9}, {"vendor": "Northwind Cooling", "price": 12500, "days": 5}, {"vendor": "Polar Systems", "price": 16800, "days": 3}]
        checks = self.demo.check_compare(demo_scripted.compare_answer(rows, 15000, "en"), workspace, originals, 15000, "en")
        assert not checks[-1]["ok"]
