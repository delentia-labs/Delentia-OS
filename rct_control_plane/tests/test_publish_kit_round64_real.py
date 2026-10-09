"""
Round 64: the pieces of the publication kit that can be tested without a model or a download - the redacted trace export, the fresh-install plan, the clustered power simulation,
the programme budget and the audit of the main objects' output.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import subprocess
from pathlib import Path

import pytest

from rct_control_plane import demo
from research import budget, power

ROOT = Path(__file__).resolve().parents[2]


class TestRedaction:
    def test_keys_bearer_values_passwords_emails_and_addresses_are_removed(self, tmp_path):
        text = ("key sk-or-abcdefghijklmnop12345678 and Authorization: Bearer abcdefghijklmnop12 and password=hunter2hunter2 "
                "mail somchai@example.com host 192.168.10.7 token: abc123def456 ghp_abcdefghijklmnopqrstuvwxyz1234")
        clean, n = demo.redact(text, tmp_path)
        for leak in ("sk-or-abcdefghijklmnop", "abcdefghijklmnop12", "hunter2", "somchai@example.com", "192.168.10.7", "abc123def456", "ghp_abcdefghijklmnop"):
            assert leak not in clean, leak
        assert n >= 6

    def test_the_home_folder_the_demo_folder_and_the_user_name_never_travel(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERNAME", "somchai-the-owner")
        root = tmp_path / "delentia-demo"
        text = f"results in {root}\\results and {Path.home()}\\x by somchai-the-owner"
        clean, _ = demo.redact(text, root)
        assert str(root) not in clean and str(Path.home()) not in clean and "somchai-the-owner" not in clean and "<demo>" in clean

    def test_ordinary_thai_text_and_prices_survive(self, tmp_path):
        text = "ราคารวม: 12,500 บาท บริษัท สยามแอร์ ไม่เกินงบ 15,000 บาท"
        clean, n = demo.redact(text, tmp_path)
        assert clean == text and n == 0

    def test_export_collects_the_newest_files_with_a_header_that_says_it_is_not_a_benchmark(self, tmp_path):
        root = tmp_path / "demo"
        (root / "results").mkdir(parents=True)
        for i in range(4):
            (root / "results" / f"2026100{i}-run.md").write_text(f"run {i} sk-or-abcdefghijklmnop12345678\n", encoding="utf-8")
        out = demo.export_trace(root, last=2)
        assert out["files"] == ["20261002-run.md", "20261003-run.md"] and "sk-or-" not in out["text"]
        assert "not a benchmark" in out["text"] and "replacements made: 2" in out["text"]

    def test_export_refuses_when_there_is_nothing_to_export(self, tmp_path):
        (tmp_path / "results").mkdir()
        with pytest.raises(SystemExit):
            demo.export_trace(tmp_path)


class TestFreshInstallPlan:
    def test_the_default_run_prints_a_plan_and_changes_nothing(self):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_fresh_install.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        assert done.returncode == 0 and "nothing is run" in done.stdout and "[DOWNLOADS]" in done.stdout and "demo" in done.stdout

    def test_only_the_install_step_is_marked_as_downloading(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_fresh_install as cfi
        steps = cfi.plan(Path("work"))
        assert [s["name"].split(" ")[0] for s in steps if s["downloads"]] == ["install"]


class TestPower:
    def test_it_agrees_with_the_closed_form_where_the_formula_applies(self):
        # the protocol's rough figure: ~236 independent units for +10 points with 30% of pairs disagreeing; with clustering the simulation lands in the same region
        assert 0.75 <= power.simulate_power(236, 0.10, 0.55, 4.0, 2, sims=300, boot=300) <= 1.0

    def test_power_grows_with_units_and_with_effect_and_is_low_when_both_are_small(self):
        small = power.simulate_power(40, 0.05, 0.55, 4.0, 2, sims=200, boot=200)
        more_units = power.simulate_power(320, 0.05, 0.55, 4.0, 2, sims=200, boot=200)
        bigger_effect = power.simulate_power(40, 0.20, 0.55, 4.0, 2, sims=200, boot=200)
        assert small < 0.3 and more_units > small and bigger_effect > small

    def test_no_effect_wins_about_five_percent_of_the_time_at_most(self):
        assert power.simulate_power(120, 0.0, 0.55, 4.0, 2, sims=400, boot=300) < 0.12


class TestBudget:
    def test_the_snapshot_is_dated_and_every_model_has_tools(self):
        snap = budget.load_snapshot()
        assert snap["fetched"] == "2026-10-09" and snap["models"] and all(m["tools"] for m in snap["models"].values())

    def test_an_episode_costs_less_with_caching_and_nothing_with_a_free_model(self):
        price = budget.load_snapshot()["models"]["anthropic/claude-haiku-5.5"]
        plain = budget.episode_cost(price, calls=6, prompt_tokens=8200, completion_tokens=150, cached_share=0.0)
        cached = budget.episode_cost(price, calls=6, prompt_tokens=8200, completion_tokens=150, cached_share=0.9)
        free = budget.episode_cost(budget.load_snapshot()["models"]["nvidia/nemotron-3-super-120b-a12b:free"], calls=6, prompt_tokens=8200, completion_tokens=150, cached_share=0.0)
        assert cached < plain and free == 0.0
        assert plain == pytest.approx((6 * 8200 * 0.10 + 6 * 150 * 0.50) / 1_000_000)

    def test_the_stage_list_adds_up_to_the_number_the_report_quotes(self):
        assert sum(n for _, _, n in budget.STAGES) == 2498


class TestMainObjectsAuditFile:
    def test_the_committed_audit_says_every_object_ran(self):
        report = json.loads((ROOT / "research" / "main_objects_audit.json").read_text(encoding="utf-8"))
        assert set(report["objects"]) >= {"RCT-7 Thinking", "FDIA equation", "RCTDB", "Delta engine", "Intent Loop", "JITNA (signing)", "41 algorithms", "JITNA (spawning agents)"}
        assert all(o["RUNS"] for o in report["objects"].values())
        assert all("HELPS" in o and o["HELPS"] for o in report["objects"].values())
