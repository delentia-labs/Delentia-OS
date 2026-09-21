"""
Round 36 Task 83: real tests for TelegramGateway's message-handling logic.
`_dispatch_to_autonomous_loop` is monkeypatched (a deliberate, documented
testable seam - see telegram_gateway.py) to avoid a real LLM call, so
these tests exercise the REAL parsing/namespacing/reply logic against a
real, Telegram-shaped Update payload - not the network layer, matching
Task 83(a)'s plan exactly.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

import pytest

from rct_control_plane.gateways.telegram_gateway import TelegramGateway


class _FakeKernel:
    class _FakePersistence:
        pass
    _persistence = _FakePersistence()


def _real_update(chat_id: int, text: str, update_id: int = 1) -> dict:
    """A real, Telegram-API-shaped Update payload (matches the real
    documented getUpdates response structure)."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": 100,
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
            "date": 1234567890,
        },
    }


class TestHandleUpdateDispatch:
    def test_real_text_message_dispatches_to_autonomous_loop_with_correct_namespace(self):
        gateway = TelegramGateway(kernel=_FakeKernel(), bot_token="fake-token-for-testing")
        captured = {}

        async def fake_dispatch(goal, namespace):
            captured["goal"] = goal
            captured["namespace"] = namespace
            return {"final_answer": "real reply", "stopped_reason": "llm_finished"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch
        gateway.send_message = lambda chat_id, text: asyncio.sleep(0)  # no real network call

        update = _real_update(chat_id=12345, text="what is the FDIA score for D=0.9?")
        result = asyncio.run(gateway.handle_update(update))

        assert captured["goal"] == "what is the FDIA score for D=0.9?"
        assert captured["namespace"] == "telegram-12345"
        assert result["result"]["final_answer"] == "real reply"

    def test_update_with_no_text_message_is_honestly_ignored(self):
        gateway = TelegramGateway(kernel=_FakeKernel(), bot_token="fake-token")
        # A real sticker update has no "text" field.
        update = {"update_id": 2, "message": {"chat": {"id": 1}, "sticker": {"file_id": "abc"}}}
        result = asyncio.run(gateway.handle_update(update))
        assert result is None


class TestNamespaceIsolation:
    def test_two_different_chat_ids_get_genuinely_isolated_namespaces(self):
        """Reuses the same isolation-proof pattern Round 22's
        agent_profile.py tests already established - real, distinct
        namespaces per identity, no state bleed."""
        gateway = TelegramGateway(kernel=_FakeKernel(), bot_token="fake-token")
        seen_namespaces = []

        async def fake_dispatch(goal, namespace):
            seen_namespaces.append(namespace)
            return {"final_answer": "ok", "stopped_reason": "llm_finished"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch
        gateway.send_message = lambda chat_id, text: asyncio.sleep(0)

        asyncio.run(gateway.handle_update(_real_update(chat_id=111, text="hello", update_id=1)))
        asyncio.run(gateway.handle_update(_real_update(chat_id=222, text="hello", update_id=2)))

        assert seen_namespaces == ["telegram-111", "telegram-222"]
        assert seen_namespaces[0] != seen_namespaces[1]


class TestConfigurationHonesty:
    def test_is_configured_false_without_a_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        gateway = TelegramGateway(kernel=_FakeKernel(), bot_token=None)
        assert gateway.is_configured() is False

    def test_start_does_not_start_a_background_task_without_a_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        gateway = TelegramGateway(kernel=_FakeKernel(), bot_token=None)
        gateway.start()
        assert gateway._is_running is False
        assert gateway._bg_task is None

    def test_get_updates_raises_without_a_token_rather_than_making_a_network_call(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        gateway = TelegramGateway(kernel=_FakeKernel(), bot_token=None)
        with pytest.raises(RuntimeError):
            asyncio.run(gateway.get_updates())
