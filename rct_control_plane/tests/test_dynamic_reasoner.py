"""
Round 45 item C (group 4): real tests for dynamic_reasoner.py - 0% coverage
before this file. Confirmed genuinely used: rct_control_plane/api.py imports
both DELENTIA_CONSTITUTIONAL_PROMPT and stream_dynamic_cognition. This
module's real external boundaries - the local Ollama HTTP stream (aiohttp)
and real web scraping (web_ingestion_service) - are mocked; the module's
OWN logic (prompt construction, fallback-branch selection, event shape) runs
for real. ALGORITHM_KERNEL.process_intent_full_pipeline is also mocked here
specifically because it has a real, confirmed disk side effect (scaffolds
files under workspace_output/genesis/ on every call) that has nothing to do
with this module's own behavior under test.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import re

import pytest

import rct_control_plane.dynamic_reasoner as dynamic_reasoner


class _FakeKernel:
    def process_intent_full_pipeline(self, intent):
        return {"fdia_score": 1.0, "genesis": {"project": intent},
                "fdia_inputs": {"data_quality": 1.0, "intent_precision": 0.6, "intent_type": "query"},
                "rct7_steps": ["Step 1 (Observe): x", "Step 7 (Compare): y"]}


@pytest.fixture(autouse=True)
def patched_kernel(monkeypatch):
    monkeypatch.setattr(dynamic_reasoner, "ALGORITHM_KERNEL", _FakeKernel())


@pytest.fixture(autouse=True)
def no_real_url_in_intent(monkeypatch):
    """Most tests don't care about the web-ingestion branch - default
    extract_first_url to "no URL found" so those tests take the plain
    text path without needing their own web_ingestion_service mock."""
    import rct_control_plane.web_ingestion_service as web_ingestion_module
    monkeypatch.setattr(web_ingestion_module, "extract_first_url", lambda text: None)


class _ContentIter:
    def __init__(self, lines):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeStreamResponse:
    def __init__(self, status, lines):
        self.status = status
        self._lines = lines

    @property
    def content(self):
        return _ContentIter(self._lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakePostCM:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    last_payload = None

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, timeout=None):
        _FakeSession.last_payload = json
        return _FakePostCM(self._response)


class _RaisingSession:
    async def __aenter__(self):
        raise ConnectionError("simulated: Ollama unreachable")

    async def __aexit__(self, *a):
        return False


def _patch_ollama(monkeypatch, status=200, lines=None):
    lines = lines or []
    response = _FakeStreamResponse(status, lines)
    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: _FakeSession(response))
    return response


def _patch_ollama_unreachable(monkeypatch):
    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: _RaisingSession())


async def _collect(gen):
    return [event async for event in gen]


class TestSuccessfulStreaming:
    @pytest.mark.asyncio
    async def test_streams_real_tokens_from_ollama_and_ends_with_fdia_and_done(self, monkeypatch):
        _patch_ollama(monkeypatch, lines=[
            json.dumps({"message": {"content": "hello "}}).encode(),
            json.dumps({"message": {"content": "world"}}).encode(),
        ])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("test intent"))

        token_events = [e for e in events if e["type"] == "token"]
        assert "".join(e["data"] for e in token_events) == "hello world"
        assert events[-2]["type"] == "fdia"
        assert events[-2]["data"]["F"] == 1.0
        assert events[-1]["type"] == "done"
        # Round 50: chat mode says what it is (it runs no tools).
        assert events[-1]["data"]["hexa_role"] == "CHAT"

    @pytest.mark.asyncio
    async def test_deep_mode_prepends_a_trace_header_token(self, monkeypatch):
        _patch_ollama(monkeypatch, lines=[json.dumps({"message": {"content": "answer"}}).encode()])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("test intent", mode="deep"))

        first_token = next(e for e in events if e["type"] == "token")
        assert "RCT-7" in first_token["data"]
        assert "FDIA" in first_token["data"] and "D = 1.0" in first_token["data"]

    @pytest.mark.asyncio
    async def test_standard_mode_has_no_trace_header(self, monkeypatch):
        _patch_ollama(monkeypatch, lines=[json.dumps({"message": {"content": "answer"}}).encode()])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("test intent", mode="standard"))

        token_events = [e for e in events if e["type"] == "token"]
        assert "RCT-7" not in token_events[0]["data"]

    @pytest.mark.asyncio
    async def test_malformed_json_lines_are_skipped_without_crashing(self, monkeypatch):
        _patch_ollama(monkeypatch, lines=[
            b"not valid json at all",
            json.dumps({"message": {"content": "real token"}}).encode(),
        ])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("test intent"))
        token_events = [e for e in events if e["type"] == "token"]
        assert "".join(e["data"] for e in token_events) == "real token"

    @pytest.mark.asyncio
    async def test_empty_lines_in_the_stream_are_skipped(self, monkeypatch):
        _patch_ollama(monkeypatch, lines=[
            b"",
            json.dumps({"message": {"content": "ok"}}).encode(),
        ])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("test intent"))
        token_events = [e for e in events if e["type"] == "token"]
        assert "".join(e["data"] for e in token_events) == "ok"


class TestFallbackWhenOllamaProducesNoTokens:
    @pytest.mark.asyncio
    async def test_non_200_status_triggers_fallback(self, monkeypatch):
        _patch_ollama(monkeypatch, status=500, lines=[])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("สวัสดีครับ"))
        token_events = [e for e in events if e["type"] == "token"]
        assert token_events  # the greeting fallback branch produced real text

    @pytest.mark.asyncio
    async def test_connection_failure_triggers_fallback(self, monkeypatch):
        _patch_ollama_unreachable(monkeypatch)
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("สวัสดีครับ"))
        full_text = "".join(e["data"] for e in events if e["type"] == "token")
        assert full_text  # some fallback text was produced despite the connection error
        assert events[-1]["type"] == "done"

    @pytest.mark.asyncio
    async def test_all_malformed_lines_still_falls_back_cleanly(self, monkeypatch):
        _patch_ollama(monkeypatch, lines=[b"garbage", b"more garbage"])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("สวัสดีครับ"))
        assert any(e["type"] == "token" for e in events)
        assert events[-1]["type"] == "done"

    @pytest.mark.asyncio
    async def test_creator_question_gets_the_creator_fallback_branch(self, monkeypatch):
        _patch_ollama_unreachable(monkeypatch)
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("ใครสร้างคุณ"))
        full_text = "".join(e["data"] for e in events if e["type"] == "token")
        assert "อิทธิฤทธิ์" in full_text

    @pytest.mark.asyncio
    async def test_web_capability_question_gets_the_web_fallback_branch(self, monkeypatch):
        _patch_ollama_unreachable(monkeypatch)
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("เชื่อมต่อเว็บได้ไหม"))
        full_text = "".join(e["data"] for e in events if e["type"] == "token")
        assert "Web Scraping" not in full_text and "100%" not in full_text
        assert "Ollama" in full_text  # says the model could not be reached

    @pytest.mark.asyncio
    async def test_architecture_question_gets_the_architecture_fallback_branch(self, monkeypatch):
        _patch_ollama_unreachable(monkeypatch)
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("โครงสร้างสถาปัตยกรรมเป็นอย่างไร"))
        full_text = "".join(e["data"] for e in events if e["type"] == "token")
        assert "1+4 Model Architecture" not in full_text and "62" not in full_text
        assert "Ollama" in full_text

    @pytest.mark.asyncio
    async def test_unmatched_intent_gets_the_generic_fallback_branch(self, monkeypatch):
        _patch_ollama_unreachable(monkeypatch)
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("xyz123 completely unrelated text"))
        full_text = "".join(e["data"] for e in events if e["type"] == "token")
        # Round 50: no "I received your message and will act on it" reply
        # when nothing was processed.
        assert "ผมได้รับข้อความของคุณแล้วครับ" not in full_text
        assert "ไม่ได้" in full_text


class TestWebIngestionPipeline:
    @pytest.mark.asyncio
    async def test_url_in_intent_triggers_scraping_and_feeds_content_into_the_prompt(self, monkeypatch):
        import rct_control_plane.web_ingestion_service as web_ingestion_module
        monkeypatch.setattr(web_ingestion_module, "extract_first_url", lambda text: "https://example.com")
        monkeypatch.setattr(web_ingestion_module, "fetch_and_scrape_url", lambda url: {
            "success": True, "title": "Example Title", "total_length": 1234,
            "content_preview": "real scraped content here",
        })
        _patch_ollama(monkeypatch, lines=[json.dumps({"message": {"content": "summary"}}).encode()])

        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("summarize https://example.com"))

        token_text = "".join(e["data"] for e in events if e["type"] == "token")
        assert "Example Title" in token_text
        sent_prompt = _FakeSession.last_payload["messages"][1]["content"]
        assert "real scraped content here" in sent_prompt
        assert re.search(r"https://example\.com", sent_prompt)

    @pytest.mark.asyncio
    async def test_scrape_failure_notes_the_error_in_the_prompt_but_still_continues(self, monkeypatch):
        import rct_control_plane.web_ingestion_service as web_ingestion_module
        monkeypatch.setattr(web_ingestion_module, "extract_first_url", lambda text: "https://example.com")
        monkeypatch.setattr(web_ingestion_module, "fetch_and_scrape_url", lambda url: {
            "success": False, "error": "simulated 404",
        })
        _patch_ollama(monkeypatch, lines=[json.dumps({"message": {"content": "ok"}}).encode()])

        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("check https://example.com"))

        sent_prompt = _FakeSession.last_payload["messages"][1]["content"]
        assert "simulated 404" in sent_prompt
        assert events[-1]["type"] == "done"


class TestFdiaAndDoneEventShape:
    @pytest.mark.asyncio
    async def test_fdia_event_carries_the_real_kernel_inputs_and_no_fake_signature(self, monkeypatch):
        _patch_ollama(monkeypatch, lines=[json.dumps({"message": {"content": "x"}}).encode()])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("test"))
        fdia_event = next(e for e in events if e["type"] == "fdia")
        # Round 50: D and I come from the kernel (they were fixed 0.98/0.96),
        # and nothing is signed in chat mode (a throwaway key signed nothing).
        assert fdia_event["data"]["D"] == 1.0
        assert fdia_event["data"]["I"] == 0.6
        assert fdia_event["data"]["A"] == 1.0
        assert fdia_event["data"]["signed"] is False
        assert fdia_event["data"]["signature_hash"] == ""

    @pytest.mark.asyncio
    async def test_done_event_has_a_trace_id(self, monkeypatch):
        _patch_ollama(monkeypatch, lines=[json.dumps({"message": {"content": "x"}}).encode()])
        events = await _collect(dynamic_reasoner.stream_dynamic_cognition("test"))
        done_event = events[-1]
        assert done_event["data"]["trace_id"].startswith("trace-")
