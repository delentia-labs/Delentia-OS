"""
Round 84, DAAES model gateway: one place on the wire where the budget guard stands for BOTH systems under test (Delentia in this process, Hermes in another Python).

The independent witness is the fake upstream's own counters: a call the gateway refuses must never be seen by it, the real key must reach it and the gateway token must not, a streamed answer must
arrive complete, and what the gateway wrote in its ledger and its call log must agree with what the upstream says it served and charged.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import http.client
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from research.daaes.budget_guard import BudgetExceeded, BudgetPolicy, ExperimentLedger
from research.daaes.model_gateway import ModelGateway

REAL_KEY = "upstream-key-the-agent-must-never-see"
PRICES = {"vendor/model": (0.2, 0.8)}


class Upstream:
    """A stand-in for OpenRouter that can answer plain and streamed, charges in its own counter, and records every Authorization header it sees."""

    def __init__(self, fail_with=None, base="/api/v1"):
        self.calls = 0
        self.spent = 0.0
        self.auth = []
        self.requests = []
        self.fail_with = fail_with
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.auth.append(self.headers.get("Authorization"))
                raw = json.dumps({"data": [{"id": "vendor/model"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.auth.append(self.headers.get("Authorization"))
                outer.requests.append((self.path, body))
                if outer.fail_with:
                    raw = json.dumps({"error": "boom"}).encode()
                    self.send_response(outer.fail_with)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                outer.calls += 1
                p, c = 120, 30
                cost = p * 0.2 / 1e6 + c * 0.8 / 1e6
                outer.spent += cost
                usage = {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c, "cost": cost}
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    for piece in ("hel", "lo ", "there"):
                        chunk = {"id": "s", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                        self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                        self.wfile.flush()
                    last = {"id": "s", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage}
                    self.wfile.write(b"data: " + json.dumps(last).encode() + b"\n\ndata: [DONE]\n\n")
                    self.close_connection = True
                    return
                raw = json.dumps({"id": "x", "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello there"}, "finish_reason": "stop"}], "usage": usage}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.base = base

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}{self.base}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()


def post(gw, body, token=None, path="/chat/completions"):
    conn = http.client.HTTPConnection("127.0.0.1", int(gw.base_url.rsplit(":", 1)[1].split("/")[0]), timeout=30)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token if token is not None else gw.token}"}
    conn.request("POST", "/v1" + path, body=json.dumps(body), headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def make(tmp_path, up, policy=None, price=PRICES["vendor/model"], **kw):
    policy = policy or BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.5)
    return ModelGateway(up.url, tmp_path / "ledger.json", policy, "run-1", price[0], price[1], upstream_key=REAL_KEY, calls_path=tmp_path / "calls.jsonl", **kw)


MSG = {"model": "vendor/model", "messages": [{"role": "user", "content": "hi"}]}


def test_a_plain_call_is_forwarded_with_the_real_key_and_the_ledger_matches_the_upstream(tmp_path):
    with Upstream() as up, make(tmp_path, up) as gw:
        status, data = post(gw, MSG)
        assert status == 200 and json.loads(data)["choices"][0]["message"]["content"] == "hello there"
        assert up.calls == 1 and up.auth == [f"Bearer {REAL_KEY}"], "the upstream must see the real key and never the gateway token"
        assert gw.token not in str(up.auth) and REAL_KEY not in data.decode()
        led = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
        assert led["spent_usd"] == pytest.approx(up.spent, rel=1e-6) and led["reserved_usd"] == pytest.approx(0.0, abs=1e-12)
        assert up.requests[0][0] == "/api/v1/chat/completions", "the gateway's /v1 maps onto the upstream's own prefix"


def test_a_streamed_call_arrives_complete_and_its_usage_is_counted(tmp_path):
    with Upstream() as up, make(tmp_path, up) as gw:
        status, data = post(gw, {**MSG, "stream": True, "stream_options": {"include_usage": True}})
        text = data.decode()
        assert status == 200 and text.count("data:") >= 5 and "[DONE]" in text
        pieces = "".join(json.loads(line[5:])["choices"][0]["delta"].get("content", "") for line in text.splitlines() if line.startswith("data:") and "[DONE]" not in line and json.loads(line[5:]).get("choices"))
        assert pieces == "hello there"
        calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        assert calls[0]["stream"] is True and calls[0]["completion_tokens"] == 30 and calls[0]["usage_from_endpoint"] is True
        assert json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["spent_usd"] == pytest.approx(up.spent, rel=1e-6)


def test_a_call_without_the_gateway_token_is_refused_and_never_forwarded(tmp_path):
    with Upstream() as up, make(tmp_path, up) as gw:
        assert post(gw, MSG, token="wrong")[0] == 401
        assert post(gw, MSG, token="")[0] == 401
        assert up.calls == 0 and not up.requests


@pytest.mark.parametrize("case", ["unknown_price", "over_run_cost", "call_limit", "model_not_allowed", "token_limit"])
def test_every_budget_refusal_happens_before_the_call_and_the_upstream_never_sees_it(tmp_path, case):
    policy = BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.5)
    kwargs = {}
    price = PRICES["vendor/model"]
    body = dict(MSG)
    if case == "unknown_price":
        price = (None, None)
    elif case == "over_run_cost":
        policy = BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.0000001)
    elif case == "call_limit":
        policy = BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.5, max_llm_calls_per_run=1)
    elif case == "model_not_allowed":
        kwargs["allowed_models"] = {"vendor/other"}
    elif case == "token_limit":
        policy = BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.5, max_output_tokens_per_run=10)
    with Upstream() as up, make(tmp_path, up, policy=policy, price=price, **kwargs) as gw:
        first = post(gw, body)
        if case == "call_limit":
            assert first[0] == 200 and up.calls == 1
            second = post(gw, body)
            assert second[0] == 429 and up.calls == 1
        else:
            assert first[0] in (403, 429) and up.calls == 0 and not up.requests, (case, first)
        assert gw.stats["refused"] >= 1
        rows = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        assert any(r.get("refused") for r in rows)


def test_an_upstream_error_releases_the_reservation_and_charges_nothing(tmp_path):
    with Upstream(fail_with=500) as up, make(tmp_path, up) as gw:
        status, _ = post(gw, MSG)
        assert status == 500
        led = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
        assert led["spent_usd"] == 0 and led["reserved_usd"] == pytest.approx(0.0, abs=1e-12)


def test_an_unreachable_upstream_is_a_502_and_the_reservation_stays_counted(tmp_path):
    up = Upstream()
    url = up.url                                     # never started: nothing listens
    gw = ModelGateway(url, tmp_path / "ledger.json", BudgetPolicy(), "run-x", 0.2, 0.8, upstream_key=REAL_KEY, calls_path=tmp_path / "calls.jsonl", timeout=3)
    with gw:
        status, _ = post(gw, MSG)
        assert status == 502
        assert json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["reserved_usd"] > 0


def test_a_plain_http_upstream_off_loopback_is_refused_because_the_key_would_cross_a_network_unencrypted(tmp_path):
    with pytest.raises(ValueError):
        ModelGateway("http://example.org/v1", tmp_path / "l.json", BudgetPolicy(), "r", 0.1, 0.1, upstream_key=REAL_KEY)
    with pytest.raises(ValueError):
        ModelGateway("ftp://127.0.0.1/v1", tmp_path / "l.json", BudgetPolicy(), "r", 0.1, 0.1)


def test_the_model_list_and_native_metadata_probes_are_relayed_but_nothing_else(tmp_path):
    with Upstream() as up, make(tmp_path, up) as gw:
        req = urllib.request.Request(gw.base_url + "/models", headers={"Authorization": f"Bearer {gw.token}"})
        assert json.loads(urllib.request.urlopen(req, timeout=10).read())["data"][0]["id"] == "vendor/model"
        bad = urllib.request.Request(gw.base_url + "/files", headers={"Authorization": f"Bearer {gw.token}"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad, timeout=10)
        assert e.value.code == 404
        assert post(gw, {}, path="/embeddings")[0] == 404


def test_two_runs_share_one_ledger_and_the_experiment_total_stops_the_second(tmp_path):
    policy = BudgetPolicy(total_usd=0.004, warning_usd=0.001, stop_new_runs_usd=0.003, reserve_usd=0.0005, max_cost_per_run_usd=0.003)
    with Upstream() as up:
        total = 0
        with ModelGateway(up.url, tmp_path / "ledger.json", policy, "arm-A", 0.2, 0.8, upstream_key=REAL_KEY) as a:
            for _ in range(40):
                s, _ = post(a, {**MSG, "max_tokens": 200})
                if s != 200:
                    break
                total += 1
        with pytest.raises(BudgetExceeded):                               # the next run cannot even start: its worst case does not fit under the total
            ModelGateway(up.url, tmp_path / "ledger.json", policy, "arm-B", 0.2, 0.8, upstream_key=REAL_KEY)
            ExperimentLedger(tmp_path / "ledger.json", policy).start_run("arm-C")
        assert total >= 1 and ExperimentLedger(tmp_path / "ledger.json", policy).committed <= policy.total_usd - policy.reserve_usd + 1e-9


def test_delentia_runs_a_live_tc003_episode_through_the_gateway_and_the_oracle_decides(tmp_path, monkeypatch):
    """The same wire both systems use: Delentia's own OpenRouter provider pointed at the gateway (loopback), the key it holds is the gateway token, the upstream is a scripted fake."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    sys.path.insert(0, os.path.dirname(__file__))
    import scripted_model as sm
    from fake_openrouter import FakeOpenRouter

    from research.daaes import tc003
    from research.daaes.live_adapter import guarded, openrouter_provider

    decisions = tc003.decisions_for("perfect")
    state = {"i": 0}

    def policy(req):
        i = state["i"]
        state["i"] += 1
        d = decisions[min(i, len(decisions) - 1)]
        if d.get("action") == "finish":
            return sm._finish("All tests pass: I fixed the defects in ledgercalc and ran the visible tests.")
        return sm._call(d["tool_name"], d["tool_args"], d.get("reasoning", "step"))

    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    with FakeOpenRouter({"rehearsal/model": {"in": 0.2, "out": 0.8}}, policy=policy) as upstream:
        with ModelGateway(upstream.base_url, tmp_path / "ledger.json", BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=1.0, max_llm_calls_per_run=60), "d0", 0.2, 0.8,
                          upstream_key=upstream.key, calls_path=tmp_path / "calls.jsonl") as gw:
            monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", gw.base_url)
            provider = openrouter_provider("rehearsal/model", api_key=gw.token)
            guard = guarded(provider, tmp_path / "inner.json", BudgetPolicy(), "inner", 0.2, 0.8)
            result = tc003.run_live(guard, tmp_path / "work", max_iterations=24)
            assert result["passed"] is True and result["score"] >= 85 and not result["hard_failures"]
            assert upstream.calls >= 6 and gw.stats["forwarded"] == upstream.calls
            led = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
            assert led["spent_usd"] == pytest.approx(upstream.spent, rel=0.02, abs=1e-7)
            assert Path(tmp_path / "calls.jsonl").read_text(encoding="utf-8").count("\n") == upstream.calls
