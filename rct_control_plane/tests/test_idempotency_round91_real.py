"""
Round 91: idempotency keys, so continuing a crashed episode cannot do a side effect twice at a service that honours them (idempotency.py).

Real governed loop with a scripted model, the real journal and the real resume; the "service" is a real HTTP server that performs an order once per Idempotency-Key and counts what it received.
"The process dies" is a BaseException raised from inside the tool AFTER the service did its work (the worst moment: the effect happened, the result was never recorded).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from research.daaes import delentia_session as ds
from rct_control_plane import episode_journal, idempotency
from rct_control_plane.agent_factory import build_governed_loop
from rct_control_plane.persistence import ControlPlanePersistence
from test_episode_journal_round84_real import Crash, FINISH, GOAL, call


class Service:
    """Performs an order once per Idempotency-Key (when one is sent) and records every request it received."""

    def __init__(self):
        self.performed, self.received, self.seen_keys = [], [], set()
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                key = self.headers.get("Idempotency-Key")
                outer.received.append((body["order"], key))
                if key is None or key not in outer.seen_keys:
                    outer.performed.append(body["order"])
                    if key:
                        outer.seen_keys.add(key)
                raw = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.http.server_port}/orders"

    def stop(self):
        self.http.shutdown()


class World:
    """save_exchange_file stands in for any tool that talks to an outside service: it sends the order with the key the loop issued for the call (idempotency.current_key)."""

    def __init__(self, service, crash_on=None):
        self.service, self.crash_on, self.calls, self.keys = service, crash_on, 0, []

    async def list_tools(self):
        return [ds._Tool("delentia_read_repo_file"), ds._Tool("delentia_save_exchange_file")]

    async def call_tool(self, name, args):
        if name != "delentia_save_exchange_file":
            return ds._Result({"ok": True, "content": "contents"})
        self.calls += 1
        key = idempotency.current_key.get()
        self.keys.append(key)
        headers = {"Content-Type": "application/json", **({"Idempotency-Key": key} if key else {})}
        urllib.request.urlopen(urllib.request.Request(self.service.url, data=json.dumps({"order": args["filename"]}).encode(), headers=headers, method="POST"), timeout=10).read()
        if self.crash_on == self.calls:
            raise Crash()                                              # the effect happened; the process dies before the result is recorded
        return ds._Result({"ok": True})


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")
    monkeypatch.delenv("DELENTIA_EPISODE_JOURNAL", raising=False)
    monkeypatch.delenv(idempotency.ENV, raising=False)
    home = tmp_path / "home"
    ctx = ds.data_home(home)
    ctx.__enter__()
    persistence = ControlPlanePersistence(db_path=str(home / "agentic.db"))
    service = Service()
    yield persistence, service
    service.stop()
    ctx.__exit__(None, None, None)


def make_loop(persistence, world):
    loop = build_governed_loop(ds.NullKernel(), namespace="alice", max_iterations=12, persistence=persistence, mcp_server=world, conversation_turns=0)
    loop._route_enabled = False                                           # type: ignore[attr-defined]
    return loop


def save(n):
    return call("delentia_save_exchange_file", {"category": "reports", "filename": f"order-{n}.txt", "content": "x"})


def run(persistence, world, decisions):
    loop = make_loop(persistence, world)
    with ds.scripted_model(decisions):
        try:
            return loop, asyncio.run(loop.run(GOAL))
        except Crash:
            return loop, None


def resume(persistence, world, episode_id, decisions):
    loop = make_loop(persistence, world)
    with ds.scripted_model(decisions):
        try:
            return loop, asyncio.run(loop.resume_interrupted(episode_id, allow_unknown=True))
        except Crash:
            return loop, None


# ------------------------------------------------------------------ the key itself

def test_a_key_depends_on_what_the_call_is_not_on_who_makes_it():
    a = idempotency.key_for("root-1", "tool", idempotency.args_sha({"x": 1}), 0)
    assert a == idempotency.key_for("root-1", "tool", idempotency.args_sha({"x": 1}), 0) and idempotency.valid(a)
    assert idempotency.args_sha({"a": 1, "b": 2}) == idempotency.args_sha({"b": 2, "a": 1})
    others = {idempotency.key_for("root-2", "tool", idempotency.args_sha({"x": 1}), 0), idempotency.key_for("root-1", "other", idempotency.args_sha({"x": 1}), 0),
              idempotency.key_for("root-1", "tool", idempotency.args_sha({"x": 2}), 0), idempotency.key_for("root-1", "tool", idempotency.args_sha({"x": 1}), 1)}
    assert a not in others and len(others) == 4
    assert not idempotency.valid("not-a-key") and not idempotency.valid("dl-ZZ" + "0" * 30) and not idempotency.valid(None)


def test_two_deliberate_identical_calls_get_different_keys_and_a_retry_gets_the_old_one():
    issuer = idempotency.KeyIssuer("r")
    first, second = issuer.issue("t", {"a": 1}), issuer.issue("t", {"a": 1})
    assert first != second
    retry = idempotency.KeyIssuer("r", base_counts={f"t|{idempotency.args_sha({'a': 1})}": 2}, inherited={f"t|{idempotency.args_sha({'a': 1})}": second})
    assert retry.issue("t", {"a": 1}) == second                          # the retry of the interrupted call
    assert retry.issue("t", {"a": 1}) not in (first, second)             # a later identical call is a new one


# ------------------------------------------------------------------ the whole chain: a crash after the effect, then a resume

def test_a_crash_after_the_effect_and_a_resume_perform_the_order_once(env):
    persistence, service = env
    first = World(service, crash_on=2)
    loop, result = run(persistence, first, [save(1), save(2), save(3), FINISH])
    assert result is None and service.performed == ["order-1.txt", "order-2.txt"], "the second order took effect before the crash"
    second = World(service)
    _, out = resume(persistence, second, loop._episode_id, [save(2), save(3), FINISH])
    assert out["resumed"] is True and out["stopped_reason"] == "llm_finished"
    assert service.performed == ["order-1.txt", "order-2.txt", "order-3.txt"], "the retried order must not be performed twice"
    assert len(service.received) == 4, "the service did receive the retry; it recognised it by its key"
    assert first.keys[1] == second.keys[0], "the retry carries the key of the call it retries"
    assert len({k for _o, k in service.received if k}) == 3


def test_without_keys_the_same_crash_performs_the_order_twice(env, monkeypatch):
    monkeypatch.setenv(idempotency.ENV, "off")                           # the negative control: this is what keys prevent
    persistence, service = env
    loop, _ = run(persistence, World(service, crash_on=2), [save(1), save(2), save(3), FINISH])
    resume(persistence, World(service), loop._episode_id, [save(2), save(3), FINISH])
    assert service.performed.count("order-2.txt") == 2
    assert all(k is None for _o, k in service.received)


def test_a_chain_of_two_crashes_still_performs_every_order_exactly_once(env):
    persistence, service = env
    loop1, _ = run(persistence, World(service, crash_on=2), [save(1), save(2), save(3), FINISH])
    w2 = World(service, crash_on=2)                                      # the resumed episode retries order 2, then dies after order 3
    loop2, r2 = resume(persistence, w2, loop1._episode_id, [save(2), save(3), FINISH])
    assert r2 is None
    w3 = World(service)
    loop3, out = resume(persistence, w3, loop2._episode_id, [save(3), FINISH])
    assert out["resumed"] is True
    assert service.performed == ["order-1.txt", "order-2.txt", "order-3.txt"]
    journal = episode_journal.EpisodeJournal(persistence)
    assert journal.load(loop3._episode_id).root == loop1._episode_id, "one root for the whole chain of resumes"


def test_two_deliberate_identical_saves_are_both_performed(env):
    persistence, service = env
    world = World(service)
    run(persistence, world, [save(1), save(1), FINISH])
    assert service.performed == ["order-1.txt", "order-1.txt"] and len({k for _o, k in service.received}) == 2


def test_the_journal_remembers_the_key_of_each_call_and_the_resume_note_says_what_it_means(env):
    persistence, service = env
    loop, _ = run(persistence, World(service, crash_on=2), [save(1), save(2), save(3), FINISH])
    ep = episode_journal.EpisodeJournal(persistence).load(loop._episode_id)
    assert [bool(s.idem) and idempotency.valid(s.idem) for s in ep.steps] == [True, True] and ep.steps[1].state == "dangling"
    note = episode_journal.note_for(ep, frozenset({"delentia_save_exchange_file"}), True)
    assert "same idempotency key" in note and ep.steps[1].idem not in note, "the key itself is not put in front of the model"
