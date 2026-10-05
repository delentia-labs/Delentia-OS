"""
Round 61: the memory nudge (the runtime asks "keep this?" about what a person said about themselves) and the skill curator (archives skills with evidence against them, never deletes).

Real SQLite, the real governed loop with a scripted model, the real chat-command and gateway reply paths, and the real CLI.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import sqlite3

import pytest
from click.testing import CliRunner

import measure_injection_defence as mid
import rct_control_plane.autonomous_loop as al
from rct_control_plane import chat_commands, memory_nudge, skill_curator
from rct_control_plane.cli import cli
from rct_control_plane.gateways.common import reply_text_for
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from test_governed_autonomous_loop_real import _FakeKernel

run = asyncio.run


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv(memory_nudge.ENV, "1")


@pytest.fixture
def persistence(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "n.db"))


# ------------------------------------------------------------------ what counts as something worth keeping

class TestExtract:
    @pytest.mark.parametrize("text,kind", [
        ("My favourite colour is green.", "preference"),
        ("my name is Ittirit and please be brief", "fact"),
        ("I live in Chiang Mai", "fact"),
        ("I prefer short answers", "preference"),
        ("Please remember that the staging database is stg-db-1", "fact"),
        ("Call me Arch", "fact"),
        ("ฉันชื่อ สมชาย", "fact"),
        ("ผมชอบกาแฟดำ", "preference"),
        ("จำไว้ว่าประชุมทุกวันจันทร์", "fact"),
        ("I'm a data engineer at a bank", "fact"),
    ])
    def test_statements_about_the_person_are_found(self, text, kind):
        found = memory_nudge.extract(text)
        assert found and found[0]["kind"] == kind

    @pytest.mark.parametrize("text", [
        "What is the capital of France?", "Read pyproject.toml and summarise it", "What is my name?", "my password is hunter22 please remember it",
        "my api key is sk-abcdefghijklmnop", "remember my card number 4111111111111111", "ช่วยสรุปไฟล์นี้หน่อย", "ฉันชื่ออะไร?", "จำรหัสผ่านของฉันไว้ว่า abc123",
    ])
    def test_questions_tasks_and_secrets_are_not(self, text):
        assert memory_nudge.extract(text) == []

    def test_at_most_two_per_message(self):
        assert len(memory_nudge.extract("My name is Ann. I live in Oslo. I prefer tea. I like cats.")) == 2


# ------------------------------------------------------------------ the candidates and the person's yes or no

class TestCandidates:
    def test_nothing_is_stored_until_the_person_says_yes(self, persistence):
        c = memory_nudge.MemoryCandidates(persistence)
        made = c.propose_from_goal("telegram-42", "My favourite colour is green.")
        assert len(made) == 1 and persistence.list_memories("telegram-42") == []
        done = c.accept(made[0]["id"], "telegram-42")
        stored = persistence.list_memories("telegram-42")
        assert len(stored) == 1 and stored[0]["content"] == "My favourite colour is green." and done["memory_id"] == stored[0]["id"]
        assert json.loads(stored[0]["context"])["provenance"] == {"tainted": False, "source_tool": "", "via": "memory_nudge"} if isinstance(stored[0]["context"], str) else stored[0]["context"]["provenance"]["via"] == "memory_nudge"

    def test_dismiss_stores_nothing_and_cannot_be_answered_twice(self, persistence):
        c = memory_nudge.MemoryCandidates(persistence)
        cid = c.propose_from_goal("telegram-42", "I live in Oslo")[0]["id"]
        c.dismiss(cid, "telegram-42")
        assert persistence.list_memories("telegram-42") == []
        for fn in (c.accept, c.dismiss):
            with pytest.raises(ValueError, match="already dismissed"):
                fn(cid, "telegram-42")

    def test_only_the_owner_of_a_suggestion_can_answer_it(self, persistence):
        c = memory_nudge.MemoryCandidates(persistence)
        cid = c.propose_from_goal("telegram-42", "I live in Oslo")[0]["id"]
        with pytest.raises(ValueError, match="no such suggestion"):
            c.accept(cid, "telegram-99")
        assert persistence.list_memories("telegram-99") == [] and c.list("telegram-42")[0]["id"] == cid

    def test_the_same_statement_is_not_offered_twice_or_when_already_remembered(self, persistence):
        c = memory_nudge.MemoryCandidates(persistence)
        assert len(c.propose_from_goal("telegram-42", "I live in Oslo")) == 1
        assert c.propose_from_goal("telegram-42", "I live in Oslo") == []
        persistence.save_memory("m1", "telegram-42", "fact", "I prefer short answers", {}, 0.5)
        assert c.propose_from_goal("telegram-42", "I prefer short answers") == []

    def test_an_episode_that_read_outside_text_proposes_nothing(self, persistence):
        c = memory_nudge.MemoryCandidates(persistence)
        assert c.propose_from_goal("telegram-42", "I live in Oslo", tainted=True) == [] and c.list("telegram-42") == []

    def test_switched_off_proposes_nothing(self, persistence, monkeypatch):
        monkeypatch.delenv(memory_nudge.ENV)
        assert memory_nudge.MemoryCandidates(persistence).propose_from_goal("telegram-42", "I live in Oslo") == []

    def test_unanswered_suggestions_expire(self, persistence):
        c = memory_nudge.MemoryCandidates(persistence)
        cid = c.propose_from_goal("telegram-42", "I live in Oslo")[0]["id"]
        with persistence._connect() as conn:
            conn.execute("UPDATE memory_candidates SET created_at = created_at - ? WHERE id = ?", (memory_nudge.EXPIRES_AFTER_S + 10, cid))
        assert c.list("telegram-42") == []
        with pytest.raises(ValueError, match="already expired"):
            c.accept(cid, "telegram-42")

    def test_a_pile_up_is_limited(self, persistence):
        c = memory_nudge.MemoryCandidates(persistence)
        for i in range(memory_nudge.MAX_PENDING_PER_USER + 5):
            c.propose_from_goal("telegram-42", f"I live in town number {i}")
        assert len(c.list("telegram-42", limit=200)) == memory_nudge.MAX_PENDING_PER_USER

    def test_the_audit_trail_has_the_events_but_not_the_text(self, persistence):
        c = memory_nudge.MemoryCandidates(persistence)
        cid = c.propose_from_goal("telegram-42", "My name is Somchai Jaidee")[0]["id"]
        c.accept(cid, "telegram-42")
        with persistence._connect() as conn:
            rows = conn.execute("SELECT action, changes FROM audit_trail WHERE entity_type = 'memory_candidate' ORDER BY rowid").fetchall()
        assert [r[0] for r in rows] == ["proposed", "accepted"] and all("Somchai" not in str(r[1]) for r in rows)


# ------------------------------------------------------------------ in the loop, in chat

def one_episode(persistence, tmp_path, monkeypatch, goal, namespace, calls=(), results=None):
    script = list(calls)

    async def model(g, history, available_tools, llm_provider=None, extra_context=""):
        i = len(history)
        if i < len(script):
            return {"action": "call_tool", "tool_name": script[i][0], "tool_args": script[i][1], "reasoning": "step"}
        return {"action": "finish", "reasoning": "done", "final_answer": "Noted, here is my answer.", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(al, "decide_next_action", model)
    mcp = mid.RecordingMCP(lambda name, args: (results or {}).get(name, json.dumps({"ok": True})))
    loop = GovernedAutonomousLoop(mcp_server=mcp, persistence=persistence, kernel=_FakeKernel(), max_iterations=4, namespace=namespace, route=False,
                                  skill_library=SkillLibrary(db_path=str(tmp_path / "sk.db")))
    return run(loop.run(goal))


class TestInTheLoop:
    def test_a_chat_message_gets_a_suggestion_in_the_result_and_under_the_answer(self, persistence, tmp_path, monkeypatch):
        out = one_episode(persistence, tmp_path, monkeypatch, "My favourite colour is green. What colour is the sky?", "telegram-42")
        assert len(out["memory_nudge"]) == 1 and out["memory_nudge"][0]["text"] == "My favourite colour is green."
        reply = reply_text_for(out)
        assert "Noted, here is my answer." in reply and f"/remember {out['memory_nudge'][0]['id']}" in reply and f"/skip {out['memory_nudge'][0]['id']}" in reply

    def test_remember_and_skip_in_chat(self, persistence, tmp_path, monkeypatch):
        out = one_episode(persistence, tmp_path, monkeypatch, "I live in Oslo. Where is Norway?", "telegram-42")
        cid = out["memory_nudge"][0]["id"]
        kernel = type("K", (), {"_persistence": persistence})()
        assert "Remembered" in chat_commands.handle(kernel, "telegram", 42, "telegram-42", f"/remember {cid}")
        assert persistence.list_memories("telegram-42")[0]["content"] == "I live in Oslo."
        assert "already accepted" in chat_commands.handle(kernel, "telegram", 42, "telegram-42", f"/remember {cid}")
        other = one_episode(persistence, tmp_path, monkeypatch, "I prefer short answers. Hi", "telegram-42")["memory_nudge"][0]["id"]
        assert "will not keep" in chat_commands.handle(kernel, "telegram", 42, "telegram-42", f"/skip {other}")
        assert len(persistence.list_memories("telegram-42")) == 1
        assert "Nothing is waiting" in chat_commands.handle(kernel, "telegram", 42, "telegram-42", "/suggestions")

    def test_someone_else_cannot_remember_for_you(self, persistence, tmp_path, monkeypatch):
        cid = one_episode(persistence, tmp_path, monkeypatch, "I live in Oslo. Hi", "telegram-42")["memory_nudge"][0]["id"]
        kernel = type("K", (), {"_persistence": persistence})()
        assert "no such suggestion" in chat_commands.handle(kernel, "telegram", 99, "telegram-99", f"/remember {cid}").lower()
        assert persistence.list_memories("telegram-99") == []

    def test_an_episode_that_read_a_page_offers_nothing(self, persistence, tmp_path, monkeypatch):
        out = one_episode(persistence, tmp_path, monkeypatch, "I live in Oslo. Please summarise the page at https://example.org/x", "telegram-42",
                          calls=[("delentia_crawl_url", {"url": "https://example.org/x"})], results={"delentia_crawl_url": json.dumps({"text": "a harmless page about gardening tips"})})
        assert out["taint"]["tainted"] is True and out["memory_nudge"] == []

    def test_only_a_persons_namespace_is_nudged(self, persistence, tmp_path, monkeypatch):
        assert one_episode(persistence, tmp_path, monkeypatch, "I live in Oslo. Hi there", "cron-owner")["memory_nudge"] == []
        assert one_episode(persistence, tmp_path, monkeypatch, "I live in Oslo. Hi there", "subagent-1")["memory_nudge"] == []

    def test_off_means_no_line_under_the_answer(self, persistence, tmp_path, monkeypatch):
        monkeypatch.delenv(memory_nudge.ENV)
        out = one_episode(persistence, tmp_path, monkeypatch, "I live in Oslo. Hi there", "telegram-42")
        assert out["memory_nudge"] == [] and "/remember" not in reply_text_for(out)


class TestCli:
    def test_candidates_accept_dismiss(self, persistence, tmp_path):
        db = str(tmp_path / "n.db")
        c = memory_nudge.MemoryCandidates(persistence)
        a = c.propose_from_goal("telegram-42", "I live in Oslo")[0]["id"]
        b = c.propose_from_goal("telegram-42", "I prefer short answers")[0]["id"]
        r = CliRunner()
        listed = r.invoke(cli, ["memory", "candidates", "--db", db]).output
        assert a in listed and b in listed
        assert "remembered" in r.invoke(cli, ["memory", "accept", a, "--db", db]).output
        assert "dismissed" in r.invoke(cli, ["memory", "dismiss", b, "--db", db]).output
        again = r.invoke(cli, ["memory", "accept", a, "--db", db])
        assert again.exit_code == 1 and "already accepted" in again.output


# ------------------------------------------------------------------ the curator

def add_skill(library, problem, solution=("step one", "step two"), keywords=None, uses=0, successes=0, session_id=None, age_days=0.0):
    import uuid
    from datetime import datetime, timedelta, timezone
    from rct_control_plane.skill_library import _tokenize
    sid = "sk-" + uuid.uuid4().hex[:6]
    when = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    with sqlite3.connect(library.db_path) as conn:
        conn.execute("INSERT INTO skills (id, problem_statement, solution, keywords, delta, resilience, g_before, g_after, growth_ratio, governance_violation, created_at, session_id, "
                     "uses, successes, failures, reinforced, archived) VALUES (?, ?, ?, ?, 0.1, 0.5, 1.0, 1.1, 1.1, 0, ?, ?, ?, ?, ?, 1, 0)",
                     (sid, problem, json.dumps(list(solution)), json.dumps(keywords if keywords is not None else sorted(set(_tokenize(problem)))), when, session_id, uses, successes, uses - successes))
    return sid


@pytest.fixture
def library(tmp_path):
    return SkillLibrary(db_path=str(tmp_path / "skills.db"))


class TestCurator:
    def test_review_changes_nothing_and_says_why(self, library):
        weak = add_skill(library, "deploy the staging service", uses=4, successes=0)
        good = add_skill(library, "summarise the weekly report", uses=4, successes=4)
        report = skill_curator.review(library)
        assert [p["id"] for p in report["proposals"]] == [weak] and report["proposals"][0]["kind"] == "weak" and "reliability" in report["proposals"][0]["reason"]
        assert {s.id for s in library.list_active()} == {weak, good}

    def test_a_refusal_learned_as_a_skill_is_found(self, library):
        refusal = add_skill(library, "read pyproject.toml", solution=("I am unable to read pyproject.toml with the tools I have",))
        assert skill_curator.review(library)["proposals"][0] == {**skill_curator.review(library)["proposals"][0], "id": refusal, "kind": "refusal"}

    def test_near_duplicates_keep_the_more_reliable_one(self, library):
        keep = add_skill(library, "convert the csv export into a json summary file", uses=5, successes=5)
        drop = add_skill(library, "convert the csv export into a json summary", uses=1, successes=1)
        proposals = skill_curator.review(library)["proposals"]
        assert len(proposals) == 1 and proposals[0]["id"] == drop and proposals[0]["kind"] == "duplicate" and proposals[0]["keep"] == keep

    def test_stale_skills_are_only_proposed_until_asked(self, library, persistence):
        old = add_skill(library, "water the office plants", age_days=200)
        add_skill(library, "brand new unused skill about invoices", age_days=1)
        report = skill_curator.review(library)
        assert [p["id"] for p in report["proposals"]] == [old] and report["proposals"][0]["kind"] == "stale"
        outcome = skill_curator.apply(library, persistence)
        assert outcome["archived"] == [] and [p["id"] for p in outcome["left_as_proposals"]] == [old] and library.get_skill(old).archived is False
        assert [p["id"] for p in skill_curator.apply(library, persistence, skill_curator.EVIDENCE_KINDS + ("stale",))["archived"]] == [old]

    def test_apply_archives_and_never_deletes_and_unarchive_brings_it_back(self, library, persistence):
        weak = add_skill(library, "deploy the staging service", uses=4, successes=0)
        before = library.count()
        outcome = skill_curator.apply(library, persistence)
        assert [p["id"] for p in outcome["archived"]] == [weak] and library.count() == before
        row = library.get_skill(weak)
        assert row.archived is True and row.solution == ["step one", "step two"] and row.uses == 4
        assert weak not in {s.id for s in library.list_active()}
        assert library.unarchive(weak) is True and weak in {s.id for s in library.list_active()} and library.unarchive(weak) is False
        with persistence._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'skill_curator' AND action = 'archived'").fetchone()[0] == 1

    def test_starter_and_imported_skills_are_never_touched(self, library, persistence):
        bundled = add_skill(library, "read a file and summarise it", solution=("I am unable to",), uses=9, successes=0, session_id="bundled:starter")
        imported = add_skill(library, "some imported skill about reports", uses=9, successes=0, session_id="imported:abc")
        assert skill_curator.review(library)["proposals"] == [] and skill_curator.review(library)["protected"] == 2
        assert library.archive(bundled) is False and library.archive(imported) is False

    def test_a_skill_is_proposed_once_under_its_strongest_reason(self, library):
        both = add_skill(library, "read config.yaml", solution=("none of the tools can do this",), uses=5, successes=0)
        proposals = skill_curator.review(library)["proposals"]
        assert [(p["id"], p["kind"]) for p in proposals] == [(both, "refusal")]

    def test_cli_review_apply_unarchive(self, library, tmp_path):
        weak = add_skill(library, "deploy the staging service", uses=4, successes=0)
        r = CliRunner()
        args = ["--skills-db", library.db_path, "--db", str(tmp_path / "audit.db")]
        shown = r.invoke(cli, ["skills", "curate", *args]).output
        assert "weak" in shown and weak in shown and library.get_skill(weak).archived is False
        applied = r.invoke(cli, ["skills", "curate", "--apply", *args]).output
        assert "archived 1 skill" in applied and library.get_skill(weak).archived is True
        assert "offered again" in r.invoke(cli, ["skills", "unarchive", weak, "--skills-db", library.db_path]).output
