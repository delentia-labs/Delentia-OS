"""
Round 112: the first run on a clean computer (criteria written first: research/FIRSTRUN_CRITERIA_R112.md).

Found by the Architect's first install of 2.4.3 on a second Windows computer with no Ollama: a question took 17 s to end in a raw 'ConnectError: All connection attempts failed',
the status page showed a model name as if it worked, and the footer counted 5,064 tokens for a call that never left. Real httpx, a real closed loopback port, the real governed loop.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import socket
import time

import httpx
import pytest

from rct_control_plane import llm_provider, readiness
from rct_control_plane.llm_provider import MeteredProvider, is_local_refusal
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]            # released again: nothing listens


class Counting(llm_provider.LLMProvider):
    """The real OpenRouterProvider aimed at a closed port (a real ConnectError), with a call counter."""

    def __init__(self, base_url):
        self.calls = 0
        os.environ["DELENTIA_OPENROUTER_BASE_URL"] = base_url
        self.inner = llm_provider.OpenRouterProvider(api_key="sk-or-test-not-real", model="vendor/model")

    @property
    def model(self):
        return "vendor/model"

    async def complete(self, *a, **k):
        self.calls += 1
        return await self.inner.complete(*a, **k)


class RemoteRefusing(llm_provider.LLMProvider):
    """A refused connection to a host that is NOT this computer: still worth another try."""

    def __init__(self):
        self.calls = 0

    @property
    def model(self):
        return "vendor/model"

    async def complete(self, *a, **k):
        self.calls += 1
        raise httpx.ConnectError("refused", request=httpx.Request("POST", "https://models.example.org/v1/chat/completions"))


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setenv("DELENTIA_LLM_RETRIES", "2")
    monkeypatch.setenv("DELENTIA_LLM_RETRY_BACKOFF", "0.02")
    monkeypatch.setenv("DELENTIA_OPENROUTER_TIMEOUT_S", "20")


def run(tmp_path, provider, name="fr"):
    loop = _loop(tmp_path, name, kernel=_FakeKernel(), mcp=_FakeMCP(), llm_provider=provider)
    started = time.perf_counter()
    result = asyncio.run(asyncio.wait_for(loop.run("What can you do?"), timeout=60))
    return result, time.perf_counter() - started


# ------------------------------------------------------------------ R1 and R2: no retry for a refused local connection, and fast
def test_a_refused_local_connection_is_one_attempt_and_ends_fast(tmp_path):
    provider = Counting(f"http://127.0.0.1:{closed_port()}/api/v1")
    result, seconds = run(tmp_path, provider)
    assert result["stopped_reason"] == "model_not_running"
    assert provider.calls == 1, "nothing is listening: trying again cannot help"
    assert seconds < 3.0


def test_a_refused_connection_to_another_host_is_still_retried(tmp_path):
    provider = RemoteRefusing()
    result, _ = run(tmp_path, provider)
    assert result["stopped_reason"] == "llm_error" and provider.calls == 3


def test_the_classifier_reads_the_host_not_the_message():
    local = httpx.ConnectError("x", request=httpx.Request("POST", "http://127.0.0.1:9/api/chat"))
    name = httpx.ConnectError("x", request=httpx.Request("POST", "http://localhost:11434/api/chat"))
    v6 = httpx.ConnectError("x", request=httpx.Request("POST", "http://[::1]:11434/api/chat"))
    remote = httpx.ConnectError("x", request=httpx.Request("POST", "https://openrouter.ai/api/v1"))
    assert is_local_refusal(local) and is_local_refusal(name) and is_local_refusal(v6)
    assert not is_local_refusal(remote)
    assert not is_local_refusal(httpx.ConnectError("no request attached"))
    assert not is_local_refusal(httpx.ReadTimeout("slow", request=httpx.Request("POST", "http://127.0.0.1:9/")))   # a timeout is not a refusal
    assert not is_local_refusal(RuntimeError("x"))


# ------------------------------------------------------------------ R3: the sentence a person reads has no raw error in it
def test_the_reason_a_person_reads_names_what_to_do_and_hides_the_raw_error(tmp_path):
    result, _ = run(tmp_path, Counting(f"http://127.0.0.1:{closed_port()}/api/v1"), name="fr3")
    reasoning = " ".join(str(step.get("llm_reasoning", "")) for step in result["steps"])
    for raw in ("WinError", "ConnectError", "errno", "Traceback", "All connection attempts failed"):
        assert raw not in reasoning, raw
    assert "not running" in reasoning and "online model" in reasoning
    technical = json.dumps([step.get("tool_result") for step in result["steps"]], default=str)
    assert "ConnectError" in technical, "the technical text stays in the record"


# ------------------------------------------------------------------ R7: a call that never left costs nothing
def test_a_refused_local_call_is_not_counted_as_spent():
    class Refuse(llm_provider.LLMProvider):
        @property
        def model(self):
            return "m"

        async def complete(self, *a, **k):
            raise httpx.ConnectError("x", request=httpx.Request("POST", "http://127.0.0.1:9/api/chat"))

    meter = MeteredProvider(Refuse())
    with pytest.raises(httpx.ConnectError):
        asyncio.run(meter.complete("a long prompt " * 500))
    assert meter.prompt_tokens == 0 and meter.completion_tokens == 0


def test_a_failure_after_the_request_may_have_left_is_still_counted():
    class Timeout(llm_provider.LLMProvider):
        @property
        def model(self):
            return "m"

        async def complete(self, *a, **k):
            raise httpx.ReadTimeout("slow", request=httpx.Request("POST", "http://127.0.0.1:9/api/chat"))

    meter = MeteredProvider(Timeout())
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(meter.complete("a long prompt " * 500))
    assert meter.prompt_tokens > 0, "a timeout may have been served: the safe reading is that it was spent"


# ------------------------------------------------------------------ R4: the model row tells the truth
def _facts(**over):
    base = {"provider": "ollama", "model": "qwen2.5:7b", "ollama_models": None, "key_present": None, "chosen": False, "ollama_installed": False,
            "approver_keys": 0, "approver_devices": 0, "episodes": 0}
    base.update(over)
    return base


def test_a_fresh_computer_with_no_ollama_is_not_ready_and_says_not_installed():
    check = next(c for c in readiness.evaluate(_facts())["checks"] if c["id"] == "model")
    assert check["state"] == "not_installed" and not check["ok"] and check["chosen"] is False


def test_an_installed_but_stopped_ollama_is_server_down_not_not_installed():
    check = next(c for c in readiness.evaluate(_facts(ollama_installed=True))["checks"] if c["id"] == "model")
    assert check["state"] == "server_down" and not check["ok"]


def test_a_running_server_with_the_model_is_ready():
    check = next(c for c in readiness.evaluate(_facts(ollama_models=["qwen2.5:7b"], chosen=True))["checks"] if c["id"] == "model")
    assert check["state"] == "ready" and check["ok"]


def test_gather_marks_the_default_model_as_not_chosen(tmp_path, monkeypatch):
    from rct_control_plane.persistence import ControlPlanePersistence
    for name in ("DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "none.json"))
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", f"http://127.0.0.1:{closed_port()}")
    facts = readiness.gather(ControlPlanePersistence(db_path=str(tmp_path / "r.db")))
    assert facts["chosen"] is False and facts["ollama_models"] is None and "ollama_installed" in facts
