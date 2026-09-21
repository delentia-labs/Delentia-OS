"""
Round 38: real tests for SlackGateway's message-handling logic.
`_dispatch_to_autonomous_loop` is monkeypatched (the same testable seam
telegram_gateway.py/discord_gateway.py/line_gateway.py established) to
avoid a real LLM call - these tests exercise the REAL namespacing/reply
logic, not a real Socket Mode connection, which needs real
SLACK_BOT_TOKEN/SLACK_APP_TOKEN the Architect hasn't registered yet.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.gateways.slack_gateway import SlackGateway


class _FakeKernel:
    class _FakePersistence:
        pass
    _persistence = _FakePersistence()


class TestHandleMessageDispatch:
    def test_a_real_human_message_dispatches_with_correct_namespace(self):
        gateway = SlackGateway(kernel=_FakeKernel(), bot_token="xoxb-fake", app_token="xapp-fake")
        captured = {}

        async def fake_dispatch(goal, namespace):
            captured["goal"] = goal
            captured["namespace"] = namespace
            return {"final_answer": "real reply", "stopped_reason": "llm_finished"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch

        result = asyncio.run(gateway.handle_message(
            channel_id="C123", user_id="U999", bot_id=None, text="what is the FDIA score?",
        ))

        assert captured["goal"] == "what is the FDIA score?"
        assert captured["namespace"] == "slack-C123-U999"
        assert result["reply_text"] == "real reply"

    def test_a_bot_authored_message_is_honestly_ignored(self):
        gateway = SlackGateway(kernel=_FakeKernel(), bot_token="xoxb-fake", app_token="xapp-fake")
        called = {"n": 0}

        async def fake_dispatch(goal, namespace):
            called["n"] += 1
            return {"final_answer": "x"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch
        result = asyncio.run(gateway.handle_message(
            channel_id="C1", user_id="U1", bot_id="B123", text="I am a bot",
        ))
        assert result is None
        assert called["n"] == 0

    def test_a_system_message_with_no_user_id_is_honestly_ignored(self):
        gateway = SlackGateway(kernel=_FakeKernel(), bot_token="xoxb-fake", app_token="xapp-fake")
        result = asyncio.run(gateway.handle_message(
            channel_id="C1", user_id=None, bot_id=None, text="someone joined the channel",
        ))
        assert result is None

    def test_empty_text_is_honestly_ignored(self):
        gateway = SlackGateway(kernel=_FakeKernel(), bot_token="xoxb-fake", app_token="xapp-fake")
        result = asyncio.run(gateway.handle_message(
            channel_id="C1", user_id="U1", bot_id=None, text="",
        ))
        assert result is None


class TestNamespaceIsolation:
    def test_two_different_users_in_the_same_channel_get_isolated_namespaces(self):
        gateway = SlackGateway(kernel=_FakeKernel(), bot_token="xoxb-fake", app_token="xapp-fake")
        seen_namespaces = []

        async def fake_dispatch(goal, namespace):
            seen_namespaces.append(namespace)
            return {"final_answer": "ok"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch

        asyncio.run(gateway.handle_message(channel_id="C1", user_id="U1", bot_id=None, text="hi"))
        asyncio.run(gateway.handle_message(channel_id="C1", user_id="U2", bot_id=None, text="hi"))

        assert seen_namespaces == ["slack-C1-U1", "slack-C1-U2"]


class TestConfigurationHonesty:
    def test_is_configured_false_with_no_tokens(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
        gateway = SlackGateway(kernel=_FakeKernel())
        assert gateway.is_configured() is False

    def test_is_configured_false_with_only_one_token(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
        monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
        gateway = SlackGateway(kernel=_FakeKernel())
        assert gateway.is_configured() is False

    def test_is_configured_true_with_both_tokens(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-fake")
        gateway = SlackGateway(kernel=_FakeKernel())
        assert gateway.is_configured() is True

    def test_start_does_not_start_a_background_task_without_tokens(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
        gateway = SlackGateway(kernel=_FakeKernel())
        gateway.start()
        assert gateway._is_running is False
        assert gateway._bg_task is None
        assert gateway._handler is None
