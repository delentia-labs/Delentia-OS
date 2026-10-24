"""Round 92 (P1 of the ask-and-wait design): the store for a question put to a person and the wait for the answer.

Real SQLite, real AES-GCM sealing under a per-person key, the real audit trail. Nothing is mocked except the clock where a test needs time to pass.
What is pinned: the wait survives a restart and runs nothing; only the person it belongs to (or an owner for them) can answer; an answer is accepted once; waiting is not agreement (expiry);
the person's words are not in the database file in the clear; every change is an audit row; erasing the person erases the text; the original goal is kept and the answer is a new version.
"""
import sqlite3
from pathlib import Path

import pytest

from rct_control_plane import clarifications as cl
from rct_control_plane import memory_erasure as er
from rct_control_plane.persistence import ControlPlanePersistence

ALICE = "alice-r92"
BOB = "bob-r92"
GOAL = "ALICEGOAL write the Thai summary report for the new staff from notes A and B and do not touch the originals"
QUESTION = "ALICEQUESTION who is the report for, and how long should it be?"


@pytest.fixture
def db(tmp_path):
    return tmp_path / "control_plane.db"


@pytest.fixture
def store(db):
    return cl.ClarificationStore(ControlPlanePersistence(str(db)))


def _ask(store, namespace=ALICE, **kw):
    args = dict(kind="before_act", criterion="unclear_intent", question=QUESTION, original_goal=GOAL, expected="a reader and a length", observed="neither is stated",
                episode_id="ep-1")
    args.update(kw)
    return store.create(namespace, **args)


def test_a_question_is_stored_with_everything_needed_to_answer_it(store):
    q = _ask(store)
    assert q.status == "PENDING" and q.intent_version == 1 and q.new_intent_version is None
    got = store.get(q.clarification_id)
    assert (got.question, got.original_goal, got.expected, got.observed, got.episode_id) == (QUESTION, GOAL, "a reader and a length", "neither is stated", "ep-1")
    assert got.kind == "before_act" and got.criterion == "unclear_intent"


def test_the_wait_survives_a_restart_and_runs_nothing(db):
    first = cl.ClarificationStore(ControlPlanePersistence(str(db)))
    q = _ask(first)
    second = cl.ClarificationStore(ControlPlanePersistence(str(db)))                      # a new process opens the same file
    again = second.get(q.clarification_id)
    assert again is not None and again.status == "PENDING" and again.question == QUESTION
    assert [c.clarification_id for c in second.waiting_for(ALICE)] == [q.clarification_id]


def test_only_the_person_it_belongs_to_can_answer_or_an_owner_for_them(store):
    q = _ask(store)
    with pytest.raises(cl.ClarificationError, match="someone else"):
        store.answer(q.clarification_id, BOB, "for new staff, one page")
    assert store.get(q.clarification_id).status == "PENDING"
    with pytest.raises(cl.ClarificationError, match="empty"):
        store.answer(q.clarification_id, ALICE, "   ")
    done = store.answer(q.clarification_id, "the-owner", "for new staff, one page", as_owner=True)
    assert done.status == "ANSWERED" and done.answered_by == "the-owner"


def test_an_answer_is_accepted_once_and_is_a_new_version_that_keeps_the_original(store):
    q = _ask(store)
    done = store.answer(q.clarification_id, ALICE, "ALICEANSWER for new staff, one page")
    assert done.status == "ANSWERED" and done.intent_version == 1 and done.new_intent_version == 2
    assert done.original_goal == GOAL and done.answer.startswith("ALICEANSWER")                 # the original is not overwritten
    revised = done.revised_goal()
    assert GOAL in revised and "ALICEANSWER" in revised and "intent version 2" in revised and QUESTION in revised
    with pytest.raises(cl.ClarificationError, match="ANSWERED"):
        store.answer(q.clarification_id, ALICE, "a second answer")
    with pytest.raises(cl.ClarificationError, match="ANSWERED"):
        store.cancel(q.clarification_id, ALICE)
    with pytest.raises(cl.ClarificationError, match="only an answered"):
        _ask(store).revised_goal()


def test_a_cancelled_question_cannot_be_answered(store):
    q = _ask(store)
    assert store.cancel(q.clarification_id, ALICE).status == "CANCELLED"
    with pytest.raises(cl.ClarificationError, match="CANCELLED"):
        store.answer(q.clarification_id, ALICE, "too late")


def test_waiting_is_not_agreement_the_question_expires_and_runs_nothing(store, monkeypatch):
    q = _ask(store)
    monkeypatch.setattr(cl, "_now", lambda: q.expires_at + 1)
    assert store.get(q.clarification_id).status == "EXPIRED"
    with pytest.raises(cl.ClarificationError, match="EXPIRED"):
        store.answer(q.clarification_id, ALICE, "an answer after the deadline")
    assert store.waiting_for(ALICE) == []


def test_the_time_to_live_is_configurable(store, monkeypatch):
    monkeypatch.setenv(cl.TTL_ENV, "60")
    q = _ask(store)
    assert 59 <= q.expires_at - q.created_at <= 61


def test_a_person_sees_only_their_own_questions(store):
    a, b = _ask(store, ALICE), _ask(store, BOB, question="BOBQUESTION which supplier?")
    assert [c.clarification_id for c in store.list(namespace=ALICE)] == [a.clarification_id]
    assert [c.clarification_id for c in store.list(namespace=BOB)] == [b.clarification_id]
    assert store.get(a.clarification_id, namespace=BOB) is None
    assert {c.clarification_id for c in store.list(namespace=None)} == {a.clarification_id, b.clarification_id}


def test_the_persons_words_are_not_in_the_database_file_in_the_clear(store, db):
    q = _ask(store)
    store.answer(q.clarification_id, ALICE, "ALICEANSWER one page for new staff")
    # SQLite may keep pages in the write-ahead log; read the main file and the log
    raw = b"".join(p.read_bytes() for p in (db, Path(str(db) + "-wal")) if p.exists())
    for marker in (b"ALICEGOAL", b"ALICEQUESTION", b"ALICEANSWER"):
        assert marker not in raw, marker
    assert store.get(q.clarification_id).question == QUESTION                                    # and still readable by the person who holds the key


def test_every_change_of_state_is_an_audit_row_without_the_words_in_the_clear(store, db, monkeypatch):
    q = _ask(store)
    store.answer(q.clarification_id, ALICE, "ALICEANSWER one page")
    q2 = _ask(store, question="ALICEQUESTION second?")
    store.cancel(q2.clarification_id, ALICE)
    q3 = _ask(store, question="ALICEQUESTION third?")
    monkeypatch.setattr(cl, "_now", lambda: q3.expires_at + 1)
    store.get(q3.clarification_id)
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute("SELECT action, changes FROM audit_trail WHERE entity_type = 'clarification' ORDER BY id").fetchall()
    assert [r[0] for r in rows] == ["asked", "answered", "asked", "cancelled", "asked", "expired"]
    blob = " ".join(r[1] for r in rows)
    assert "ALICEQUESTION" not in blob and "ALICEANSWER" not in blob


def test_erasing_the_person_erases_the_text_and_keeps_the_other_person(store, db):
    a, b = _ask(store, ALICE), _ask(store, BOB, question="BOBQUESTION which supplier?", original_goal="BOBGOAL pick a supplier")
    er._destroy_key(ALICE)
    gone = store.get(a.clarification_id)
    assert gone.question == "[erased]" and gone.original_goal == "[erased]"                      # the key is gone: the sealed text cannot be read
    assert store.get(b.clarification_id).question == "BOBQUESTION which supplier?"
    with sqlite3.connect(str(db)) as conn:                                                      # a plain-text install (sealing off) is scrubbed by the table sweep
        report = er.scrub_tables(conn, BOB)
    assert any(t["table"] == "clarifications" for t in report["tables"])
    assert store.get(b.clarification_id).question == ""


def test_kind_and_criterion_are_from_a_fixed_list_and_a_question_is_required(store):
    with pytest.raises(cl.ClarificationError, match="kind"):
        _ask(store, kind="whenever")
    with pytest.raises(cl.ClarificationError, match="criterion"):
        _ask(store, criterion="vibes")
    with pytest.raises(cl.ClarificationError, match="question"):
        _ask(store, question="  ")


def test_the_store_is_not_reachable_by_the_model(tmp_path):
    """No MCP tool can ask or answer: a model that could answer its own question would turn the wait into nothing."""
    from rct_control_plane.mcp_server import mcp
    import asyncio
    names = [t.name for t in asyncio.run(mcp.list_tools())]
    assert not [n for n in names if "clarif" in n.lower()]
