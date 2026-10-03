"""
Round 57: backup models (provider_fallback.py) with real HTTP: a loopback server that speaks the OpenRouter protocol and fails on demand, and one that speaks
Ollama's. The safety rules (a backup may not expose data more than the primary, may not cost more than the budget allows, may not bypass the sovereignty policy)
are tested as behaviour, through a real governed episode.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from rct_control_plane import provider_fallback as pf
from rct_control_plane.llm_provider import OllamaProvider, OpenRouterProvider
from test_governed_autonomous_loop_real import _FakeMCP, _loop

FINISH = json.dumps({"action": "finish", "reasoning": "done", "final_answer": "Completed the goal: fallback test"})


class Server:
    """kind='openrouter' speaks /chat/completions, kind='ollama' speaks /api/generate. `status` != 200 makes it fail."""

    def __init__(self, kind, status=200, answer=FINISH):
        self.kind, self.status, self.answer, self.calls = kind, status, answer, 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.calls += 1
                if outer.status != 200:
                    body = json.dumps({"error": "down"}).encode()
                    self.send_response(outer.status)
                else:
                    if outer.kind == "openrouter":
                        payload = {"choices": [{"message": {"content": outer.answer}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0}}
                    else:
                        payload = {"response": outer.answer, "done": True, "prompt_eval_count": 10, "eval_count": 5}
                    body = json.dumps(payload).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.http.server_port}"

    def stop(self):
        self.http.shutdown()


@pytest.fixture
def world(monkeypatch, tmp_path):
    for name in ("DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL", pf.FALLBACK_ENV, "DELENTIA_HOME_REGION", "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_SOVEREIGNTY_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_SOVEREIGNTY_CONFIG", str(tmp_path / "none.json"))
    monkeypatch.setenv("DELENTIA_LLM_BREAKER", "0")                   # keep the circuit breaker out of the way: its own tests cover it
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    servers = []

    def make(kind, **kw):
        s = Server(kind, **kw)
        servers.append(s)
        return s
    yield make, monkeypatch
    for s in servers:
        s.stop()


def episode(tmp_path, monkeypatch, primary_provider="openrouter", model="primary/model", **loop_kwargs):
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", primary_provider)
    monkeypatch.setenv("DELENTIA_LLM_MODEL", model)
    loop = _loop(tmp_path, "fb", mcp=_FakeMCP(), **loop_kwargs)
    result = asyncio.run(loop.run("fallback test"))
    return result, loop


def audit(loop, entity_type):
    with loop._persistence._connect() as conn:
        return [json.loads(r[0]) for r in conn.execute("SELECT changes FROM audit_trail WHERE entity_type = ?", (entity_type,))]


# ------------------------------------------------------------------ the provider itself

def test_nothing_changes_without_a_configured_fallback(world):
    make, monkeypatch = world
    primary = OpenRouterProvider(model="a/b")
    provider, prices, notes = pf.chain(primary, primary)
    assert provider is primary and prices is None and notes == []


def test_a_failing_primary_hands_the_call_to_the_backup_and_the_next_call_goes_straight_to_the_one_that_worked(world):
    make, monkeypatch = world
    dead, alive = make("openrouter", status=503), make("ollama")
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", dead.url)
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", alive.url)
    monkeypatch.setenv(pf.FALLBACK_ENV, "ollama:backup-model")
    switches = []
    primary = OpenRouterProvider(model="primary/model")
    provider = pf.FallbackProvider([primary, OllamaProvider(model="backup-model")], on_switch=lambda a, b, r: switches.append((a, b, r)))
    assert asyncio.run(provider.complete("hello")) == FINISH
    assert switches and switches[0][:2] == ("primary/model", "backup-model") and "503" in switches[0][2]
    assert provider.model == "backup-model" and dead.calls >= 1
    before = dead.calls
    asyncio.run(provider.complete("again"))
    assert dead.calls == before and alive.calls == 2                  # it does not retry the dead endpoint on every call


def test_a_bad_request_is_not_a_reason_to_ask_another_model(world):
    make, monkeypatch = world
    bad, alive = make("openrouter", status=400), make("ollama")
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", bad.url)
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", alive.url)
    provider = pf.FallbackProvider([OpenRouterProvider(model="p/m"), OllamaProvider(model="b")])
    with pytest.raises(Exception):
        asyncio.run(provider.complete("hello"))
    assert alive.calls == 0


def test_the_last_error_is_raised_when_every_model_fails(world):
    make, monkeypatch = world
    a, b = make("openrouter", status=500), make("ollama", status=502)
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", a.url)
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", b.url)
    provider = pf.FallbackProvider([OpenRouterProvider(model="p/m"), OllamaProvider(model="b")])
    with pytest.raises(Exception) as info:
        asyncio.run(provider.complete("hello"))
    assert "502" in str(info.value) and a.calls >= 1 and b.calls >= 1


@pytest.mark.parametrize("status,switches", [(500, True), (503, True), (429, True), (408, True), (400, False), (401, False), (404, False)])
def test_which_failures_switch(world, status, switches):
    import httpx
    exc = httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://x"), response=httpx.Response(status))
    assert pf.switchable(exc) is switches
    assert pf.switchable(httpx.ConnectError("refused")) is True and pf.switchable(asyncio.TimeoutError()) is True and pf.switchable(ValueError("bad")) is False


def test_malformed_configuration_is_ignored_not_fatal(world, monkeypatch):
    make, _ = world
    monkeypatch.setenv(pf.FALLBACK_ENV, "nonsense, :x, ollama:, gemini:foo, ollama:ok-model ,  ")
    assert pf.configured() == [("ollama", "ok-model")]


# ------------------------------------------------------------------ the safety rules, through a real governed episode

def test_a_real_episode_survives_a_dead_primary_and_records_the_switch(world, tmp_path):
    make, monkeypatch = world
    dead, alive = make("openrouter", status=503), make("ollama")
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", dead.url)
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", alive.url)
    monkeypatch.setenv(pf.FALLBACK_ENV, "ollama:backup-model")
    result, loop = episode(tmp_path, monkeypatch)
    assert result["stopped_reason"] == "llm_finished" and "Completed the goal" in result["final_answer"]
    rows = audit(loop, "model_fallback")
    assert rows and rows[0]["from"] == "primary/model" and rows[0]["to"] == "backup-model"


def test_without_a_backup_the_same_failure_ends_the_episode_as_before(world, tmp_path):
    make, monkeypatch = world
    dead = make("openrouter", status=503)
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", dead.url)
    result, loop = episode(tmp_path, monkeypatch)
    assert result["stopped_reason"] == "llm_error" and audit(loop, "model_fallback") == []


def test_a_backup_that_would_expose_data_more_than_the_primary_is_dropped(world):
    make, monkeypatch = world
    alive = make("openrouter")
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", alive.url)
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv(pf.FALLBACK_ENV, "openrouter:cloud/backup")
    local_primary = OllamaProvider(model="local")
    provider, _, notes = pf.chain(local_primary, local_primary)
    assert provider is local_primary and any("expose data more than the primary" in n for n in notes)       # local primary: a cloud backup is refused


def test_a_local_backup_for_a_cloud_primary_is_allowed(world):
    make, monkeypatch = world
    monkeypatch.setenv(pf.FALLBACK_ENV, "ollama:qwen2.5:7b")
    cloud = OpenRouterProvider(model="p/m")
    provider, _, notes = pf.chain(cloud, cloud)
    assert isinstance(provider, pf.FallbackProvider) and provider.inner is cloud and notes == []
    assert [type(m).__name__ for m in provider._members] == ["OpenRouterProvider", "OllamaProvider"] and provider._members[1].model == "qwen2.5:7b"


def test_a_backup_the_sovereignty_policy_does_not_allow_is_dropped(world, tmp_path):
    make, monkeypatch = world
    monkeypatch.setenv("DELENTIA_HOME_REGION", "TH")
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", "http://ollama.example.com:11434")            # not a private address and no region declared: cross-border
    monkeypatch.setenv(pf.FALLBACK_ENV, "ollama:remote-model")
    cloud = OpenRouterProvider(model="p/m")
    provider, _, notes = pf.chain(cloud, cloud)
    assert provider is cloud and any("sovereignty policy does not allow it" in n for n in notes)


def test_an_openrouter_backup_without_a_key_is_not_used(world, monkeypatch):
    make, _ = world
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setenv(pf.FALLBACK_ENV, "openrouter:x/y")
    primary = OllamaProvider(model="m")
    provider, _, notes = pf.chain(primary, primary)
    assert provider is primary and any("no API key" in n for n in notes)


def test_with_a_cost_budget_a_backup_of_unknown_price_is_dropped_and_the_meter_uses_the_dearest_price(world):
    make, monkeypatch = world
    monkeypatch.setenv(pf.FALLBACK_ENV, "openrouter:cheap/one,openrouter:unknown/two")
    prices = {"p/m": (1.0, 2.0), "cheap/one": (0.1, 0.2), "dear/primary": (5.0, 9.0)}

    def price_of(provider):
        if isinstance(provider, OllamaProvider):
            return (0.0, 0.0)
        return prices.get(provider.model)
    primary = OpenRouterProvider(model="p/m")
    provider, worst, notes = pf.chain(primary, primary, cost_budget_set=True, price_of=price_of)
    assert isinstance(provider, pf.FallbackProvider) and len(provider._members) == 2 and worst == (1.0, 2.0)       # the dearer of primary and backup
    assert any("unknown/two: dropped, its price is unknown" in n for n in notes)
    dear = OpenRouterProvider(model="dear/primary")
    _, worst2, _ = pf.chain(dear, dear, cost_budget_set=True, price_of=price_of)
    assert worst2 == (5.0, 9.0)                                                                                   # a cheaper backup never lowers the price used


def test_the_meter_charges_the_dearest_model_in_the_chain_in_a_real_episode(world, tmp_path):
    make, monkeypatch = world
    alive = make("openrouter")
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", alive.url)
    monkeypatch.setenv(pf.FALLBACK_ENV, "ollama:backup-model")
    import rct_control_plane.model_config as mc
    monkeypatch.setattr(mc, "lookup_openrouter_prices", lambda model, client=None: (3.0, 6.0))
    result, loop = episode(tmp_path, monkeypatch, max_episode_cost_usd=1.0)
    assert result["stopped_reason"] == "llm_finished"
    assert loop._meter.prompt_price_per_mtok == 3.0 and loop._meter.completion_price_per_mtok == 6.0
