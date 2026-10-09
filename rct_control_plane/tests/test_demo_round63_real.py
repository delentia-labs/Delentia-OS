"""
Round 63: `delentia demo` end to end, in separate real processes - the way a person would use it: init, run, stop, run again.

The model is a real HTTP server that follows a script (it is plugged in like any OpenAI-compatible model); everything else is
real: the CLI, the governed loop, the real tools confined to the demo folder, SQLite, Ed25519 approvals, the signed audit chain.
What this proves is the path (init -> Thai goal -> tools -> result file -> checks -> approval -> a new process still remembers);
it does not say how well any language model would do it.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import re
import subprocess
from pathlib import Path

import pytest

import scripted_model as sm
from research.policy_models import QuotePolicy
from rct_control_plane import demo
from rct_control_plane.model_config import save_model_selection

ROOT = Path(__file__).resolve().parents[2]


class DemoPolicy:
    """The scripted stand-in for the model: remembers when told to, answers from recalled memories, otherwise reads the quotes."""

    def __init__(self, workspace: Path) -> None:
        self.quotes = QuotePolicy(workspace, "diligent")

    def __call__(self, req):
        goal = req.goal
        if goal.startswith("จำไว้ว่า:"):
            if req.history_empty:
                return sm._call("delentia_remember", {"content": goal.split(":", 1)[1].strip()}, "store the standing preference")
            return sm._finish("จำไว้แล้ว")
        if "ผู้อนุมัติงบคือใคร" in goal:
            return sm._finish("จากที่คุณเคยบอก: " + (req.memories[0] if req.memories else "ฉันยังไม่มีข้อมูลนี้"))
        return self.quotes(req)


def cli(args, env, timeout=600):
    done = subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=ROOT, env=env, timeout=timeout)
    return done


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("demo_world")
    root = base / "delentia-demo"
    with sm.ScriptedModel(DemoPolicy(root / "workspace")) as model:
        config = base / "model.json"
        save_model_selection("openai-compat", model.model_id, path=config, endpoint={"base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted-test-model"})
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DELENTIA_MODEL_CONFIG": str(config), "DELENTIA_LLM_PROVIDER": "openai-compat",
               "DELENTIA_LLM_MODEL": model.model_id, "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "USERPROFILE": str(base / "home"), "HOME": str(base / "home")}
        for name in ("DELENTIA_HOME", "DELENTIA_REPO_ROOT", "DELENTIA_UNTRUSTED_PATHS", "DELENTIA_APPROVERS_FILE", "DELENTIA_AUDIT_SIGNING_KEY", "DELENTIA_WARM_RECALL",
                     "RCT_DB_PATH", "RCT_AGENTIC_DB_PATH", "DELENTIA_API_TOKEN"):
            env.pop(name, None)
        init = cli(["demo", "init", "--dir", str(root)], env)
        yield {"root": root, "env": env, "init": init, "model": model}


@pytest.fixture(scope="module")
def compare_run(world):
    """`demo run compare` once; several tests read what it left behind (they must not depend on running after each other: the suite is run shuffled)."""
    return cli(["demo", "run", "compare", "--dir", str(world["root"])], world["env"])


@pytest.fixture(scope="module")
def told(world):
    """`demo run remember` once, in its own process."""
    return cli(["demo", "run", "remember", "--dir", str(world["root"])], world["env"])


class TestDemoPath:
    def test_init_makes_the_folder_and_never_overwrites(self, world):
        root, env = world["root"], world["env"]
        assert world["init"].returncode == 0, world["init"].stderr[-800:]
        for rel in ("workspace/quotes/vendor_a.md", "workspace/quotes/vendor_b.md", "workspace/quotes/vendor_c.md", "keys/demo-approver.pem", "keys/audit.pem", "README_TH.md"):
            assert (root / rel).exists(), rel
        original = (root / "workspace/quotes/vendor_a.md").read_text(encoding="utf-8")
        try:
            (root / "workspace/quotes/vendor_a.md").write_text("แก้โดยผู้ใช้\n", encoding="utf-8")
            again = cli(["demo", "init", "--dir", str(root)], env)
            assert again.returncode == 0 and (root / "workspace/quotes/vendor_a.md").read_text(encoding="utf-8") == "แก้โดยผู้ใช้\n"
        finally:
            (root / "workspace/quotes/vendor_a.md").write_text(original, encoding="utf-8")

    def test_the_demo_approver_key_is_outside_the_workspace_the_agent_can_read(self, world):
        assert not list((world["root"] / "workspace").rglob("*.pem"))

    def test_compare_reads_the_quotes_answers_correctly_and_changes_nothing(self, world, compare_run):
        out = compare_run.stdout
        assert compare_run.returncode == 0, (out[-1500:], compare_run.stderr[-800:])
        assert "จบเอง" in out and "สยามแอร์" in out and "บางกอกเทคนิค" in out
        assert out.count("`delentia_read_repo_file`") == 3
        assert "ไม่ผ่าน" not in out and "ผ่าน: ไฟล์ต้นฉบับไม่ถูกแก้" in out
        assert "ครบสมบูรณ์" in out
        results = sorted((world["root"] / "results").glob("*compare*.md"))
        assert results and "คำตอบ" in results[-1].read_text(encoding="utf-8")

    def test_reading_the_quotes_is_reading_outside_text(self, world, compare_run):
        text = sorted((world["root"] / "results").glob("*compare*.md"))[-1].read_text(encoding="utf-8")
        assert "อ่านข้อความจากภายนอก" in text and "quotes/vendor_" in text

    def test_edit_stops_for_a_signature_then_the_demo_key_lets_it_through(self, world):
        root, env = world["root"], world["env"]
        original = (root / "workspace/quotes/vendor_a.md").read_text(encoding="utf-8")
        try:
            done = cli(["demo", "run", "edit", "--dir", str(root)], env)
            assert "pending_approval" in done.stdout and "รออนุมัติ รหัส" in done.stdout, done.stdout[-1200:]
            assert (root / "workspace/quotes/vendor_a.md").read_text(encoding="utf-8") == original, "nothing may change before a signature"
            approval_id = re.search(r"delentia demo approve ([0-9a-f]{12})", done.stdout).group(1)
            approved = cli(["demo", "approve", approval_id, "--dir", str(root)], env)
            assert approved.returncode == 0, (approved.stdout[-1200:], approved.stderr[-800:])
            assert "14,000" in (root / "workspace/quotes/vendor_a.md").read_text(encoding="utf-8") or "14,000" in approved.stdout
            again = cli(["demo", "approve", approval_id, "--dir", str(root)], env)
            assert again.returncode != 0, "an approval is used at most once"
        finally:
            (root / "workspace/quotes/vendor_a.md").write_text(original, encoding="utf-8")

    def test_what_it_was_told_is_still_there_after_the_program_was_closed_and_opened_again(self, world, told):
        assert told.returncode == 0 and "delentia_remember" in told.stdout, told.stdout[-1200:]
        asked = cli(["demo", "run", "ask", "--dir", str(world["root"])], world["env"])        # a new process: nothing is in memory except what was stored
        assert "สมชาย" in asked.stdout, asked.stdout[-1500:]

    def test_status_reports_memories_and_an_intact_chain(self, world, told):
        done = cli(["demo", "status", "--dir", str(world["root"])], world["env"])
        info = json.loads(done.stdout[done.stdout.index("{"):])
        assert info["audit"]["ok"] and info["audit"]["rows"] > 0 and info["memories"] >= 1
        assert info["untrusted_paths"] == "quotes/"


class TestDemoChecker:
    """The checker that grades the demo's answer against what is known to be true (found wrong by a real run: 'ไม่เกินงบ' was read as 'เกินงบ')."""

    def intact(self, tmp_path):
        ws = tmp_path / "workspace"
        for rel, (vendor, price, days) in demo.QUOTES.items():
            (ws / rel).parent.mkdir(parents=True, exist_ok=True)
            (ws / rel).write_text(demo._quote_text(vendor, price, days), encoding="utf-8")
        return ws, demo._hashes(ws)

    def table(self):
        return "| สยามแอร์ | 12,500 | | ไทยคูลลิ่ง | 16,800 | | บางกอกเทคนิค | 9,900 |\n"

    def test_a_correct_thai_answer_passes_every_check(self, tmp_path):
        ws, originals = self.intact(tmp_path)
        answer = self.table() + "ในงบ: สยามแอร์, บางกอกเทคนิค"
        assert all(c["ok"] for c in demo.check_compare(answer, ws, originals))

    def test_mai_koen_ngop_is_not_read_as_over_budget(self, tmp_path):
        ws, originals = self.intact(tmp_path)
        answer = self.table() + "บริษัท สยามแอร์ ราคาไม่เกินงบ 15,000 บาท\nบริษัท บางกอกเทคนิค ราคาไม่เกินงบ 15,000 บาท\nบริษัท ไทยคูลลิ่ง เกินงบ"
        assert all(c["ok"] for c in demo.check_compare(answer, ws, originals))

    def test_listing_the_over_budget_vendor_as_fine_fails(self, tmp_path):
        ws, originals = self.intact(tmp_path)
        answer = self.table() + "ในงบ: สยามแอร์, ไทยคูลลิ่ง, บางกอกเทคนิค"
        failed = [c["check"] for c in demo.check_compare(answer, ws, originals) if not c["ok"]]
        assert any("ไทยคูลลิ่ง" in c for c in failed)

    def test_a_missing_vendor_and_missing_prices_fail(self, tmp_path):
        ws, originals = self.intact(tmp_path)
        failed = [c["check"] for c in demo.check_compare("บริษัท บางกอกเทคนิค ราคาไม่เกินงบ 15,000 บาท", ws, originals) if not c["ok"]]
        assert any("ตาราง" in c for c in failed) and any("สยามแอร์" in c for c in failed)

    def test_a_changed_original_fails(self, tmp_path):
        ws, originals = self.intact(tmp_path)
        (ws / "quotes/vendor_a.md").write_text("changed\n", encoding="utf-8")
        checks = demo.check_compare(self.table() + "ในงบ: สยามแอร์, บางกอกเทคนิค", ws, originals)
        assert not [c for c in checks if c["check"] == "ไฟล์ต้นฉบับไม่ถูกแก้"][0]["ok"]
