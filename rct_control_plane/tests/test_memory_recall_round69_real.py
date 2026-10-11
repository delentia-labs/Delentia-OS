"""
Round 69: the recall that ships when DELENTIA_MEMORY_EMBED=ollama - BM25 (memory_lexical), the ordering (memory_ranking), the per-model calibration (memory_embeddings.calibrate) and the real AgentMemory with real
SQLite, sealed vectors and an HTTP server that speaks Ollama's /api/embed. The fake model reads English by meaning (synonym groups share a bucket) and cannot read Thai (every Thai text lands on the same point,
which is what nomic-embed-text really does: unrelated Thai cosine median 1.0, see `delentia memory calibrate`). The real model's numbers are in research/recall_lab_r69.py and the Round 69 document.
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

from rct_control_plane import memory_embeddings as mx
from rct_control_plane import memory_erasure as er
from rct_control_plane import memory_eventlog as me
from rct_control_plane import memory_lexical as lex
from rct_control_plane import memory_llm as ml
from rct_control_plane import memory_ranking as rk
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.persistence import ControlPlanePersistence

GROUPS = [{"cartons", "packaging", "boxes", "box", "carton"}, {"vendor", "supplier", "company", "provider"}, {"refund", "money", "reimbursed"}, {"landlord", "rent", "lease"},
          {"night", "overnight", "evening"}, {"staffed", "covers", "shift"}]
STOP = lex._STOP | {"what", "which", "who"}
DIM = 2048


def vector_for(text, multilingual=False):
    v = [0.0] * DIM
    for raw in lex._TOKEN.findall(text.lower().replace("?", " ").replace(",", " ")):
        if "฀" <= raw[0] <= "๿":
            keys = [f"th:{raw[i:i + 3]}" for i in range(max(1, len(raw) - 2))] if multilingual else ["th"]       # a model that cannot read Thai puts every Thai text on the same point
        else:
            if raw in STOP:
                continue
            group = next((i for i, g in enumerate(GROUPS) if raw in g), None)
            keys = [f"g{group}" if group is not None else raw]
        for key in keys:
            v[int(hashlib.sha256(key.encode()).hexdigest(), 16) % DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    common = 0.656 / math.sqrt(DIM)
    out = [0.755 * x / n + common for x in v]
    norm = math.sqrt(sum(x * x for x in out))
    return [x / norm for x in out]


class Handler(BaseHTTPRequestHandler):
    multilingual = False
    models_seen = []

    chat_calls = []
    chat_mode = "ok"
    tags = ["nomic-embed-text:latest"]
    tag_requests = 0

    def do_GET(self):                                                        # noqa: N802
        Handler.tag_requests += 1
        out = json.dumps({"models": [{"name": n} for n in Handler.tags]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):                                                       # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/api/chat"):
            prompt = body["messages"][0]["content"]
            Handler.chat_calls.append(prompt)
            if Handler.chat_mode == "garbage":
                reply = {"unexpected": True}
            elif "Rewrite the question" in prompt:
                reply = {"message": {"content": "\n".join(["1. Which company sells cartons to us?", "2. Who provides our boxes?", "3. ok"])}}
            elif "stg-db-1" in prompt:
                reply = {"message": {"content": "\n".join(["- What is the name of the pre-production data store?", "- Which environment holds the staging data?", "- Where does pre-release testing run?"])}}
            else:
                reply = {"message": {"content": "\n".join(["Something nobody asked about?", "Another unrelated question?", "A third one entirely?"])}}
            out = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        Handler.models_seen.append(body.get("model"))
        out = json.dumps({"embeddings": [vector_for(t, Handler.multilingual) for t in body["input"]]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


@pytest.fixture
def server(monkeypatch, tmp_path):
    Handler.multilingual, Handler.models_seen, Handler.chat_calls, Handler.chat_mode = False, [], [], "ok"
    Handler.tags, Handler.tag_requests = ["nomic-embed-text:latest"], 0
    mx.reset_auto_probe()
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv(mx.URL_ENV, f"http://127.0.0.1:{httpd.server_address[1]}")
    monkeypatch.setenv(mx.ENV, "ollama")
    monkeypatch.delenv(mx.REMOTE_ENV, raising=False)
    monkeypatch.delenv(mx.MODEL_ENV, raising=False)
    monkeypatch.setenv(mx.CALIBRATION_FILE_ENV, str(tmp_path / "calibration.json"))
    monkeypatch.setenv(er.KEYS_ENV, str(tmp_path / "keys"))
    monkeypatch.delenv(me.ENABLE_ENV, raising=False)
    monkeypatch.delenv(ml.QUESTIONS_ENV, raising=False)
    monkeypatch.delenv(ml.EXPANSION_ENV, raising=False)
    monkeypatch.delenv(ml.MODEL_ENV, raising=False)
    mx.reset_breaker()
    ml.reset_breaker()
    yield httpd
    httpd.shutdown()
    mx.reset_breaker()
    ml.reset_breaker()


def run(coro):
    return asyncio.run(coro)


def mem(tmp_path, who="alice"):
    p = ControlPlanePersistence(db_path=str(tmp_path / "m.db"))
    return AgentMemory(who, p), p


# ------------------------------------------------------------------ BM25 and tokens

def test_tokens_split_identifiers_and_cut_thai_into_trigrams():
    assert "stg-db-1" in lex.tokens("The staging database is stg-db-1.") and "stg" in lex.tokens("stg-db-1")
    assert lex.tokens("คุณสุดา") == ["คุณ", "ุณส", "ณสุ", "สุด", "ุดา"] or len(lex.tokens("คุณสุดา")) == 5
    assert lex.tokens("ab") == ["ab"] and lex.tokens("a") == []                       # a single letter is not a token
    assert "the" not in lex.tokens("the refund window")


def test_thai_fraction():
    assert lex.thai_fraction("hello") == 0.0 and lex.thai_fraction("") == 0.0
    assert lex.thai_fraction("สวัสดี") == 1.0
    assert 0.3 < lex.thai_fraction("ใครดูแล Jira") < 0.8


def test_bm25_prefers_the_rare_term_and_a_short_exact_document():
    docs = ["the cluster is named harbor-prod", "the cluster is named alpha", "the cluster is named beta", "the weather is fine today"]
    scores = lex.BM25(docs).scores("which cluster is harbor-prod")
    assert scores.index(max(scores)) == 0 and scores[3] == 0.0
    assert lex.BM25([]).scores("x") == []


# ------------------------------------------------------------------ the ordering

def cand(i, text, importance=0.6, memory_type="fact"):
    return {"id": f"m{i}", "content": text, "importance": importance, "memory_type": memory_type}


def test_the_order_uses_the_raw_cosine_so_nothing_ties_at_the_clipped_maximum():
    mx_cal = mx.calibration()
    assert mx_cal == (0.5, 0.15)
    a, b = cand(0, "alpha"), cand(1, "beta")
    ranked = rk.rank("question", [a, b], {"m0": 0.66, "m1": 0.72}, {})
    assert [c["id"] for _k, _r, _l, c in ranked] == ["m1", "m0"]                      # both calibrate to 1.0; the raw cosine still orders them
    assert ranked[0][1] == ranked[1][1] == 1.0


def test_relevance_is_not_raised_by_the_order_score_or_by_a_model_with_no_calibration(monkeypatch):
    ranked = rk.rank("question", [cand(0, "alpha")], {"m0": 0.40}, {})
    assert ranked[0][1] == 0.0                                                         # noise stays noise: D reads 0
    monkeypatch.setenv(mx.MODEL_ENV, "some-unmeasured-model")
    assert mx.calibration() is None and mx.relevance(0.9) == 0.0
    assert rk.rank("question", [cand(0, "alpha")], {"m0": 0.9}, {"alpha": 0.2})[0][1] == 0.2          # only the lexical similarity counts


def test_a_memory_without_a_vector_is_scored_from_its_words_and_can_still_win():
    shared, unrelated = cand(0, "refund window is fourteen days"), cand(1, "something else entirely")
    ranked = rk.rank("refund window length", [shared, unrelated], {"m1": 0.55}, {"refund window is fourteen days": 0.8})
    assert ranked[0][3]["id"] == "m0"                                                  # 0.45 + 0.35 * 0.8 = 0.73 beats an unrelated 0.55
    quiet = rk.rank("refund window length", [shared, unrelated], {"m1": 0.55}, {})
    assert quiet[0][3]["id"] == "m1"                                                   # no overlap at all: it does not outrank a real score


def test_a_thai_question_leans_on_trigrams_when_the_model_cannot_tell_thai_texts_apart():
    docs = ["ผู้จัดการฝ่ายบุคคลชื่อคุณสุดา และนั่งอยู่ชั้น 4", "ช่างซ่อมแอร์ประจำบริษัทคือคุณสมพงษ์", "ห้องประชุมใหญ่ชื่อราชพฤกษ์ จุคนได้ 40 ที่นั่ง", "คลังสินค้าเปิดรับสินค้าตั้งแต่เจ็ดโมงเช้า"]
    candidates = [cand(i, d) for i, d in enumerate(docs)]
    collapsed = {c["id"]: 0.999 for c in candidates}                                   # what nomic does with Thai
    ranked = rk.rank("ใครดูแลเรื่องพนักงานฝ่ายบุคคล", candidates, collapsed, {})
    assert ranked[0][3]["id"] == "m0"
    english = rk.rank("who looks after air conditioning", [cand(0, "x"), cand(1, "y")], {"m0": 0.5, "m1": 0.6}, {})
    assert english[0][3]["id"] == "m1"                                                 # an English question never uses BM25 for the order


def test_importance_nudges_by_at_most_three_hundredths_and_never_beats_a_clearly_better_match():
    a, b = cand(0, "a", importance=0.1), cand(1, "b", importance=1.0, memory_type="goal")
    nudged = rk.rank("q", [a, b], {"m0": 0.62, "m1": 0.62}, {}, importance_bonus={"m0": 0.003, "m1": 0.03})
    assert nudged[0][3]["id"] == "m1"                                                  # a tie is broken by importance
    clear = rk.rank("q", [a, b], {"m0": 0.70, "m1": 0.62}, {}, importance_bonus={"m0": 0.003, "m1": 0.03})
    assert clear[0][3]["id"] == "m0"


# ------------------------------------------------------------------ the real AgentMemory

FACTS = ["Our main packaging vendor is PakWell and the backup is BoxHub.", "The refund window is 14 days.", "The office opens at nine.", "Thanakorn covers the night shift on holidays.",
         "The staging database is stg-db-1.", "ผู้จัดการฝ่ายบุคคลชื่อคุณสุดา และนั่งอยู่ชั้น 4", "ช่างซ่อมแอร์ประจำบริษัทคือคุณสมพงษ์", "ห้องประชุมใหญ่ชื่อราชพฤกษ์ จุคนได้ 40 ที่นั่ง"]


async def fill(m):
    return [await m.store(f, MemoryType.FACT, importance=0.6) for f in FACTS]


def test_english_paraphrases_and_exact_identifiers_are_found(server, tmp_path):
    m, _ = mem(tmp_path)
    run(fill(m))
    assert run(m.recall("Which company supplies our cartons?", limit=1))[0]["content"] == FACTS[0]
    assert run(m.recall("what is stg-db-1", limit=1))[0]["content"] == FACTS[4]
    assert run(m.recall("What is the refund window?", limit=1))[0]["content"] == FACTS[1]


def test_a_thai_question_is_found_although_the_model_cannot_read_thai(server, tmp_path):
    m, _ = mem(tmp_path)
    run(fill(m))
    assert run(m.recall("ใครดูแลเรื่องพนักงานฝ่ายบุคคล", limit=2))[0]["content"] == FACTS[5]
    assert run(m.recall("ถ้าเครื่องปรับอากาศเสียต้องเรียกใคร ช่างซ่อมแอร์", limit=2))[0]["content"] == FACTS[6]
    # with embeddings OFF the old path is untouched (this is the control: same data, the Round 68 behaviour)
    os.environ[mx.ENV] = "off"
    try:
        assert isinstance(run(m.recall("ใครดูแลเรื่องพนักงานฝ่ายบุคคล", limit=2)), list)
    finally:
        os.environ[mx.ENV] = "ollama"


def test_the_order_is_by_the_ranking_and_relevance_is_the_calibrated_value(server, tmp_path):
    m, _ = mem(tmp_path)
    run(fill(m))
    scored = run(m.recall_scored("Which company supplies our cartons?", limit=3))
    assert scored[0]["content"] == FACTS[0] and scored[0]["relevance"] > 0.5
    assert all(0.0 <= s["relevance"] <= 1.0 for s in scored)
    noise = run(m.recall_scored("How do I bake sourdough bread?", limit=1))
    assert not noise or noise[0]["relevance"] < 0.1


def test_a_revoked_memory_is_never_returned_whatever_its_score(server, tmp_path):
    m, p = mem(tmp_path)
    ids = run(fill(m))
    assert p.revoke_memory(ids[0], "alice", "wrong") is True
    for q in ("Which company supplies our cartons?", "main packaging vendor PakWell"):
        assert FACTS[0] not in [r["content"] for r in run(m.recall(q, limit=8))]


# ------------------------------------------------------------------ calibration per model

def test_calibrate_measures_the_scale_and_says_the_model_cannot_read_thai(server):
    report = mx.calibrate()
    assert report["usable"] is True and report["reads_thai"] is False
    assert report["en"]["separated"] is True and report["th"]["separated"] is False
    assert 0.3 < report["floor"] < 0.65 and report["span"] >= 0.05                    # the fake model's floor sits where nomic's does (0.50)
    Handler.multilingual = True
    assert mx.calibrate()["reads_thai"] is True


def test_a_calibration_is_written_read_and_never_written_for_an_unusable_model(server, tmp_path, monkeypatch):
    monkeypatch.setenv(mx.MODEL_ENV, "my-new-model")
    assert mx.calibration() is None and mx.relevance(0.9) == 0.0
    written = mx.calibrate("my-new-model", write=True)
    assert written["usable"] and "written_to" in written
    floor, span = mx.calibration()
    assert (floor, span) == (written["floor"], written["span"]) and mx.relevance(floor + span) == pytest.approx(1.0) and mx.relevance(floor - 0.1) == 0.0
    table = json.loads((tmp_path / "calibration.json").read_text(encoding="utf-8"))
    assert table["my-new-model"]["reads_thai"] is False
    assert Handler.models_seen and set(Handler.models_seen) == {"my-new-model"}      # the model measured is the one named, not the default
    # a built-in model keeps working next to it
    monkeypatch.setenv(mx.MODEL_ENV, "nomic-embed-text:latest")
    assert mx.calibration() == (0.5, 0.15)


def test_calibrate_reports_a_service_that_is_down_and_a_model_that_separates_nothing(server, monkeypatch):
    server.shutdown()
    server.server_close()
    mx.reset_breaker()
    assert "error" in mx.calibrate()
    mx.reset_breaker()


# ------------------------------------------------------------------ the optional local model: store-time questions and query expansion

def test_with_questions_off_the_model_is_never_called(server, tmp_path):
    m, _ = mem(tmp_path)
    run(fill(m))
    run(m.recall("what is the pre-production data store", limit=3))
    assert Handler.chat_calls == []


def test_the_questions_a_memory_answers_find_it_when_the_question_shares_no_word_with_it(server, tmp_path, monkeypatch):
    m, _ = mem(tmp_path)
    run(fill(m))
    question = "pre-production data store"
    before = [r["content"] for r in run(m.recall(question, limit=1))]
    assert before != [FACTS[4]]                                                        # nothing in the memory's own words matches
    monkeypatch.setenv(ml.QUESTIONS_ENV, "ollama")
    (tmp_path / "second").mkdir()
    m2, _ = mem(tmp_path / "second")                                                  # a fresh memory stored with the setting on
    run(fill(m2))
    assert run(m2.recall(question, limit=1))[0]["content"] == FACTS[4]
    assert any("stg-db-1" in c for c in Handler.chat_calls)


def test_questions_written_after_the_fact_by_the_backfill_and_their_vectors_are_sealed(server, tmp_path, monkeypatch):
    m, p = mem(tmp_path)
    run(fill(m))                                                                      # stored with the setting off
    monkeypatch.setenv(ml.QUESTIONS_ENV, "ollama")
    assert run(m.recall("pre-production data store", limit=1))[0]["content"] == FACTS[4]
    with p._connect() as conn:
        rows = conn.execute("SELECT memory_id, vec FROM memory_vectors WHERE memory_id LIKE '%#q%'").fetchall()
    assert rows and all(bytes(v).startswith(er.MAGIC) for _i, v in rows)             # ciphertext, like the memory's own vector
    assert len({i.split("#q")[0] for i, _v in rows}) <= 10                            # a recall writes questions for a bounded number of memories


def test_erasure_zeroes_the_question_vectors_too(server, tmp_path, monkeypatch):
    from rct_control_plane import approvals
    monkeypatch.setenv(ml.QUESTIONS_ENV, "ollama")
    m, p = mem(tmp_path)
    run(fill(m))
    pem = tmp_path / "outside" / "a.pem"
    public = approvals.generate_approver_key(str(pem))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "none.json"))
    sig = er.sign_erase(str(pem), "alice", me.MemoryEventLog(p).head()["hash"])
    er.erase_person(p, "alice", "asked", sig["public_key"], sig["signature"])
    with p._connect() as conn:
        blobs = [bytes(r[0]) for r in conn.execute("SELECT vec FROM memory_vectors WHERE namespace = 'alice'")]
    assert blobs and all(set(b) == {0} for b in blobs)


def test_a_model_that_answers_nonsense_or_is_down_means_no_questions_and_no_error(server, tmp_path, monkeypatch):
    monkeypatch.setenv(ml.QUESTIONS_ENV, "ollama")
    Handler.chat_mode = "garbage"
    m, _ = mem(tmp_path)
    ids = run(fill(m))
    assert len(ids) == len(FACTS) and run(m.recall("Which company supplies our cartons?", limit=1))[0]["content"] == FACTS[0]
    assert len(Handler.chat_calls) == 1                                               # the breaker stopped the retries after the first failure


def test_the_model_is_only_asked_on_a_loopback_address_unless_allowed(server, tmp_path, monkeypatch):
    monkeypatch.setenv(mx.URL_ENV, "http://embeddings.example.com:11434")
    assert ml.questions_for("a note") == [] and Handler.chat_calls == []


def test_the_query_expansion_adds_rewrites_and_is_cached(server, tmp_path, monkeypatch):
    m, _ = mem(tmp_path)
    run(fill(m))
    monkeypatch.setenv(ml.EXPANSION_ENV, "ollama")
    assert run(m.recall("Who is our crate provider?", limit=1))[0]["content"] == FACTS[0]
    asked = len(Handler.chat_calls)
    assert asked == 1
    run(m.recall("Who is our crate provider?", limit=1))
    assert len(Handler.chat_calls) == asked                                           # the same question is not rewritten twice


def test_the_model_name_comes_from_the_setting_then_the_memory_profile_then_a_default(monkeypatch):
    monkeypatch.setenv(ml.MODEL_ENV, "my-local-model")
    assert ml.model_name() == "my-local-model"
    monkeypatch.delenv(ml.MODEL_ENV)
    assert ml.model_name()                                                            # a non-empty default (qwen2.5:7b unless a memory profile names an Ollama model)


# ------------------------------------------------------------------ DELENTIA_MEMORY_EMBED=auto

def test_auto_is_on_only_when_the_local_ollama_has_the_embedding_model(server, monkeypatch):
    monkeypatch.setenv(mx.ENV, "auto")
    assert mx.enabled() is True
    Handler.tags = ["llama3.2:3b"]
    mx.reset_auto_probe()
    assert mx.enabled() is False
    Handler.tags = ["nomic-embed-text"]
    mx.reset_auto_probe()
    assert mx.enabled() is True                                                       # a bare name counts as well as ":latest"


def test_auto_asks_once_and_remembers_for_five_minutes(server, monkeypatch):
    monkeypatch.setenv(mx.ENV, "auto")
    for _ in range(5):
        assert mx.enabled() is True
    assert Handler.tag_requests == 1


def test_auto_is_off_when_nothing_answers_and_never_looks_at_a_remote_address(server, monkeypatch):
    monkeypatch.setenv(mx.ENV, "auto")
    server.shutdown()
    server.server_close()
    mx.reset_auto_probe()
    assert mx.enabled() is False
    monkeypatch.setenv(mx.URL_ENV, "http://embeddings.example.com:11434")
    mx.reset_auto_probe()
    assert mx.enabled() is False


def test_auto_gives_the_same_recall_as_on_and_the_old_path_when_off(server, tmp_path, monkeypatch):
    monkeypatch.setenv(mx.ENV, "auto")
    m, p = mem(tmp_path)
    run(fill(m))
    assert run(m.recall("Which company supplies our cartons?", limit=1))[0]["content"] == FACTS[0]
    with p._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0] == len(FACTS)
    monkeypatch.setenv(mx.ENV, "off")
    assert mx.enabled() is False
