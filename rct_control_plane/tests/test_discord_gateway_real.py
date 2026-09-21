"""
Round 37: real tests for DiscordGateway's message-handling logic.
`_dispatch_to_autonomous_loop` is monkeypatched (the same deliberate,
documented testable seam telegram_gateway.py/line_gateway.py already
established) to avoid a real LLM call, so these tests exercise the REAL
namespacing/reply logic - not a real websocket connection to Discord,
which needs a real bot token the Architect hasn't registered yet.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio


from rct_control_plane.gateways.discord_gateway import DiscordGateway


class _FakeKernel:
    class _FakePersistence:
        pass
    _persistence = _FakePersistence()


class TestHandleMessageDispatch:
    def test_a_real_human_message_dispatches_to_autonomous_loop_with_correct_namespace(self):
        gateway = DiscordGateway(kernel=_FakeKernel(), bot_token="fake-token-for-testing")
        captured = {}

        async def fake_dispatch(goal, namespace):
            captured["goal"] = goal
            captured["namespace"] = namespace
            return {"final_answer": "real reply", "stopped_reason": "llm_finished"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch

        result = asyncio.run(gateway.handle_message(
            channel_id=555, author_id=999, author_is_bot=False, content="what is the FDIA score?",
        ))

        assert captured["goal"] == "what is the FDIA score?"
        assert captured["namespace"] == "discord-555-999"
        assert result["reply_text"] == "real reply"

    def test_a_bot_authored_message_is_honestly_ignored(self):
        gateway = DiscordGateway(kernel=_FakeKernel(), bot_token="fake-token")
        called = {"n": 0}

        async def fake_dispatch(goal, namespace):
            called["n"] += 1
            return {"final_answer": "x"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch
        result = asyncio.run(gateway.handle_message(
            channel_id=1, author_id=2, author_is_bot=True, content="I am a bot",
        ))
        assert result is None
        assert called["n"] == 0

    def test_empty_content_is_honestly_ignored(self):
        gateway = DiscordGateway(kernel=_FakeKernel(), bot_token="fake-token")
        result = asyncio.run(gateway.handle_message(
            channel_id=1, author_id=2, author_is_bot=False, content="",
        ))
        assert result is None


class TestNamespaceIsolation:
    def test_two_different_authors_in_the_same_channel_get_isolated_namespaces(self):
        """A Discord channel (unlike a Telegram private chat) is often
        shared by multiple real users - namespaces must isolate per
        (channel, author), not per-channel alone."""
        gateway = DiscordGateway(kernel=_FakeKernel(), bot_token="fake-token")
        seen_namespaces = []

        async def fake_dispatch(goal, namespace):
            seen_namespaces.append(namespace)
            return {"final_answer": "ok"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch

        asyncio.run(gateway.handle_message(channel_id=100, author_id=1, author_is_bot=False, content="hi"))
        asyncio.run(gateway.handle_message(channel_id=100, author_id=2, author_is_bot=False, content="hi"))

        assert seen_namespaces == ["discord-100-1", "discord-100-2"]
        assert seen_namespaces[0] != seen_namespaces[1]

    def test_the_same_author_across_two_channels_also_gets_isolated_namespaces(self):
        gateway = DiscordGateway(kernel=_FakeKernel(), bot_token="fake-token")
        seen_namespaces = []

        async def fake_dispatch(goal, namespace):
            seen_namespaces.append(namespace)
            return {"final_answer": "ok"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch

        asyncio.run(gateway.handle_message(channel_id=1, author_id=42, author_is_bot=False, content="hi"))
        asyncio.run(gateway.handle_message(channel_id=2, author_id=42, author_is_bot=False, content="hi"))

        assert seen_namespaces == ["discord-1-42", "discord-2-42"]


class TestConfigurationHonesty:
    def test_is_configured_false_without_a_token(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        gateway = DiscordGateway(kernel=_FakeKernel(), bot_token=None)
        assert gateway.is_configured() is False

    def test_start_does_not_start_a_background_task_without_a_token(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        gateway = DiscordGateway(kernel=_FakeKernel(), bot_token=None)
        gateway.start()
        assert gateway._is_running is False
        assert gateway._bg_task is None
        assert gateway._client is None

    def test_is_configured_true_with_a_token(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-token-from-env")
        gateway = DiscordGateway(kernel=_FakeKernel())
        assert gateway.is_configured() is True
