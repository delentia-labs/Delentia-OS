"""
Round 68: the opt-in embedding recall (memory_embeddings.py + AgentMemory). A real HTTP server that speaks Ollama's /api/embed (its vectors are deterministic: words that mean the same fall in the same
bucket, so a paraphrase is close and an unrelated text is far), the real persistence, the real AES-GCM sealing and the real erasure. Nothing inside the memory or erasure code is mocked.
The real model's numbers are in research/recall_delentia_embed.json (22 of 30 against 7 of 30).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import hashlib
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rct_control_plane import approvals
from rct_control_plane import memory_embeddings as mx
from rct_control_plane import memory_erasure as er
from rct_control_plane import memory_eventlog as me
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.persistence import ControlPlanePersistence

GROUPS = [{"cartons", "packaging", "boxes", "box", "carton"}, {"vendor", "supplier", "company", "provider"}, {"refund", "money", "reimbursed"},
          {"landlord", "rent", "lease"}, {"night", "overnight", "evening"}, {"staffed", "covers", "shift"}]
DIM = 2048                                                                   # wide enough that two unrelated words do not share a bucket by chance
STOP = {"the", "is", "a", "an", "of", "and", "our", "what", "which", "who", "on", "in", "at", "to", "do", "i", "how", "are", "for", "it", "does", "we"}


def vector_for(text):
    v = [0.0] * DIM
    for raw in text.lower().replace("?", " ").replace(".", " ").replace(",", " ").split():
        group = next((i for i, g in enumerate(GROUPS) if raw in g), None)
        if raw in STOP:
            continue                                                         # a real embedding model does not hang its meaning on stopwords
        key = f"g{group}" if group is not None else raw
        v[int(hashlib.sha256(key.encode()).hexdigest(), 16) % DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    topic = [x / n for x in v]
    # a shared component like a real embedding model has (unrelated texts are not orthogonal): unrelated cosine ~0.43, a text that shares its topic higher
    common = 0.656 / math.sqrt(DIM)
    out = [0.755 * t + common for t in topic]
    norm = math.sqrt(sum(x * x for x in out))
    return [x / norm for x in out]


class Handler(BaseHTTPRequestHandler):
    mode = "ok"
    calls = 0

    def do_POST(self):                                                       # noqa: N802
        Handler.calls += 1
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        texts = body["input"]
        if Handler.mode == "garbage":
            payload = {"embeddings": "nope"}
        elif Handler.mode == "short":
            payload = {"embeddings": [vector_for(t) for t in texts][:-1]}
        else:
            payload = {"embeddings": [vector_for(t) for t in texts]}
        out = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


@pytest.fixture
def server(monkeypatch, tmp_path):
    Handler.mode, Handler.calls = "ok", 0
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(mx.URL_ENV, f"http://127.0.0.1:{httpd.server_address[1]}")
    monkeypatch.setenv(mx.ENV, "ollama")
    monkeypatch.delenv(mx.REMOTE_ENV, raising=False)
    monkeypatch.setenv(er.KEYS_ENV, str(tmp_path / "keys"))
    monkeypatch.delenv(me.ENABLE_ENV, raising=False)
    mx.reset_breaker()
    yield httpd
    httpd.shutdown()
    mx.reset_breaker()


def mem(tmp_path, who="alice"):
    p = ControlPlanePersistence(db_path=str(tmp_path / "m.db"))
    return AgentMemory(who, p), p


FACTS = ["Our main packaging vendor is PakWell and the backup is BoxHub.", "The refund window is 14 days.", "The office opens at nine.", "Thanakorn covers the night shift on holidays.",
         "The staging database is stg-db-1."]


async def fill(m):
    return [await m.store(f, MemoryType.FACT, importance=0.6) for f in FACTS]


def run(coro):
    return asyncio.run(coro)


def test_a_paraphrase_finds_the_memory_with_embeddings_and_not_without(server, tmp_path, monkeypatch):
    m, _ = mem(tmp_path)
    run(fill(m))
    question = "Who sells cartons?"
    on = [r["content"] for r in run(m.recall(question, limit=2))]
    assert FACTS[0] in on
    candidates = m._persistence.list_memories("alice")
    ranked = {c["id"]: (sim, lex) for sim, lex, c in m._ranked(question, candidates, 5)}
    sim, lex = ranked[next(c["id"] for c in candidates if c["content"] == FACTS[0])]
    assert sim > lex + 0.2                                                      # the similarity that found it came from meaning, not from shared words
    monkeypatch.setenv(mx.ENV, "off")
    assert m._ranked(question, candidates, 5)[0][0] == m._ranked(question, candidates, 5)[0][1]          # off: the similarity IS the lexical one (the old path)


def test_a_question_that_shares_words_still_wins_by_words(server, tmp_path):
    m, _ = mem(tmp_path)
    run(fill(m))
    assert run(m.recall("What is the refund window?", limit=1))[0]["content"] == FACTS[1]


def test_relevance_is_calibrated_so_noise_is_not_knowledge(server, tmp_path):
    m, _ = mem(tmp_path)
    run(fill(m))
    unrelated = run(m.recall_scored("How do I bake sourdough bread?", limit=1))
    assert not unrelated or unrelated[0]["relevance"] < 0.1
    related = run(m.recall_scored("Who sells cartons?", limit=1))
    assert related[0]["content"] == FACTS[0] and related[0]["relevance"] > 0.1 and (not unrelated or related[0]["relevance"] > unrelated[0]["relevance"] + 0.1)


def test_when_embeddings_are_off_nothing_is_embedded_and_no_table_is_made(tmp_path, monkeypatch):
    monkeypatch.delenv(mx.ENV, raising=False)
    monkeypatch.setenv(er.KEYS_ENV, str(tmp_path / "keys"))
    Handler.calls = 0
    m, p = mem(tmp_path)
    run(fill(m))
    run(m.recall("anything", limit=2))
    assert Handler.calls == 0
    with p._connect() as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory_vectors'").fetchone() is None


@pytest.mark.parametrize("mode", ["garbage", "short"])
def test_a_service_that_answers_nonsense_falls_back_to_the_matcher_and_never_raises(server, tmp_path, mode):
    Handler.mode = mode
    m, _ = mem(tmp_path)
    run(fill(m))
    got = run(m.recall("What is the refund window?", limit=1))
    assert got and got[0]["content"] == FACTS[1]


def test_a_service_that_is_down_falls_back_and_the_breaker_stops_the_retries(server, tmp_path):
    m, _ = mem(tmp_path)
    run(fill(m))
    server.shutdown()
    server.server_close()
    mx.reset_breaker()
    assert run(m.recall("What is the refund window?", limit=1))[0]["content"] == FACTS[1]
    started = mx._breaker_until
    assert started > 0
    assert mx.embed(["x"]) is None                                              # inside the breaker window nothing is even tried


def test_a_remote_address_is_refused_unless_allowed(server, tmp_path, monkeypatch):
    monkeypatch.setenv(mx.URL_ENV, "http://embeddings.example.com:11434")
    Handler.calls = 0
    assert mx.embed(["hello"]) is None and Handler.calls == 0
    mx.reset_breaker()
    monkeypatch.setenv(mx.REMOTE_ENV, "1")
    assert mx._address_allowed("http://embeddings.example.com:11434") is True


def test_vectors_are_sealed_and_other_people_never_see_each_others(server, tmp_path):
    p = ControlPlanePersistence(db_path=str(tmp_path / "m.db"))
    alice, bob = AgentMemory("alice", p), AgentMemory("bob", p)
    run(fill(alice))
    run(bob.store("Bob's supplier is Zeta and the rent is due monthly.", MemoryType.FACT))
    with p._connect() as conn:
        blobs = [bytes(r[0]) for r in conn.execute("SELECT vec FROM memory_vectors")]
    assert blobs and all(b.startswith(er.MAGIC) for b in blobs)                 # ciphertext, not floats
    got = [r["content"] for r in run(alice.recall("Which company supplies our cartons?", limit=5))]
    assert all("Zeta" not in g for g in got)


def test_a_revoked_memory_is_never_ranked(server, tmp_path):
    m, p = mem(tmp_path)
    ids = run(fill(m))
    assert FACTS[0] in [r["content"] for r in run(m.recall("Which company supplies our cartons?", limit=3))]
    assert p.revoke_memory(ids[0], "alice", "wrong") is True
    assert FACTS[0] not in [r["content"] for r in run(m.recall("Which company supplies our cartons?", limit=5))]


def test_erasure_zeroes_the_vectors_and_the_person_is_unsearchable_afterwards(server, tmp_path, monkeypatch):
    m, p = mem(tmp_path)
    run(fill(m))
    pem = tmp_path / "outside" / "a.pem"
    public = approvals.generate_approver_key(str(pem))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "none.json"))
    log = me.MemoryEventLog(p)
    sig = er.sign_erase(str(pem), "alice", log.head()["hash"])
    report = er.erase_person(p, "alice", "asked", sig["public_key"], sig["signature"])
    assert any(t["table"] == "memory_vectors" for t in report["other_tables_scrubbed"]) and report["not_erased"]["other_tables"] == []
    with p._connect() as conn:
        for (blob,) in conn.execute("SELECT vec FROM memory_vectors WHERE namespace = 'alice'"):
            assert set(bytes(blob)) == {0}
    assert all(r["content"] == "[erased]" for r in run(m.recall("Which company supplies our cartons?", limit=5)))


def test_the_backfill_embeds_memories_stored_before_the_setting_was_on(server, tmp_path, monkeypatch):
    monkeypatch.setenv(mx.ENV, "off")
    m, p = mem(tmp_path)
    run(fill(m))
    monkeypatch.setenv(mx.ENV, "ollama")
    assert FACTS[0] in [r["content"] for r in run(m.recall("Which company supplies our cartons?", limit=2))]
    with p._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0] == len(FACTS)
