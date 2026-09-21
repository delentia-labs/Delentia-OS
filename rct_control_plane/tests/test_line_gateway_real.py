"""
Round 36: real tests for LineGateway - real HMAC-SHA256 signature
verification (per LINE's own documented webhook security scheme) and
real webhook event-handling logic. _dispatch_to_autonomous_loop is
monkeypatched to avoid a real LLM call, same pattern as
test_telegram_gateway_real.py.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import base64
import hashlib
import hmac


from rct_control_plane.gateways.line_gateway import LineGateway


class _FakeKernel:
    class _FakePersistence:
        pass
    _persistence = _FakePersistence()


def _real_signature(secret: str, body: bytes) -> str:
    """Computed the same real way LINE itself computes it - used to
    prove verify_signature() accepts a genuinely valid signature, not
    just rejects bad ones."""
    return base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode("utf-8")


class TestSignatureVerification:
    def test_accepts_a_real_correctly_computed_signature(self):
        gateway = LineGateway(kernel=_FakeKernel(), channel_secret="real-secret", channel_access_token="token")
        body = b'{"events": []}'
        signature = _real_signature("real-secret", body)
        assert gateway.verify_signature(body, signature) is True

    def test_rejects_a_tampered_body(self):
        gateway = LineGateway(kernel=_FakeKernel(), channel_secret="real-secret", channel_access_token="token")
        body = b'{"events": []}'
        signature = _real_signature("real-secret", body)
        tampered_body = b'{"events": [{"injected": true}]}'
        assert gateway.verify_signature(tampered_body, signature) is False

    def test_rejects_a_signature_computed_with_the_wrong_secret(self):
        gateway = LineGateway(kernel=_FakeKernel(), channel_secret="real-secret", channel_access_token="token")
        body = b'{"events": []}'
        wrong_signature = _real_signature("wrong-secret", body)
        assert gateway.verify_signature(body, wrong_signature) is False

    def test_rejects_when_not_configured(self):
        gateway = LineGateway(kernel=_FakeKernel(), channel_secret=None, channel_access_token=None)
        assert gateway.verify_signature(b"anything", "anything") is False


class TestWebhookEventHandling:
    def _real_text_event(self, user_id: str, text: str, reply_token: str = "rtoken") -> dict:
        return {
            "type": "message",
            "replyToken": reply_token,
            "source": {"type": "user", "userId": user_id},
            "message": {"type": "text", "id": "1", "text": text},
        }

    def test_real_text_message_dispatches_with_correct_namespace(self):
        gateway = LineGateway(kernel=_FakeKernel(), channel_secret="s", channel_access_token="t")
        captured = {}

        async def fake_dispatch(goal, namespace):
            captured["goal"] = goal
            captured["namespace"] = namespace
            return {"final_answer": "sawasdee", "stopped_reason": "llm_finished"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch
        gateway.reply_message = lambda reply_token, text: asyncio.sleep(0)

        body = {"events": [self._real_text_event("U1234567890", "สวัสดีครับ")]}
        results = asyncio.run(gateway.handle_webhook_body(body))

        assert captured["goal"] == "สวัสดีครับ"
        assert captured["namespace"] == "line-U1234567890"
        assert results[0]["result"]["final_answer"] == "sawasdee"

    def test_two_different_users_get_isolated_namespaces(self):
        gateway = LineGateway(kernel=_FakeKernel(), channel_secret="s", channel_access_token="t")
        seen = []

        async def fake_dispatch(goal, namespace):
            seen.append(namespace)
            return {"final_answer": "ok", "stopped_reason": "llm_finished"}

        gateway._dispatch_to_autonomous_loop = fake_dispatch
        gateway.reply_message = lambda reply_token, text: asyncio.sleep(0)

        body = {"events": [self._real_text_event("Uaaa", "hi"), self._real_text_event("Ubbb", "hi")]}
        asyncio.run(gateway.handle_webhook_body(body))

        assert seen == ["line-Uaaa", "line-Ubbb"]

    def test_non_text_events_are_honestly_skipped(self):
        gateway = LineGateway(kernel=_FakeKernel(), channel_secret="s", channel_access_token="t")
        body = {"events": [{"type": "follow", "source": {"userId": "U1"}, "replyToken": "r"}]}
        results = asyncio.run(gateway.handle_webhook_body(body))
        assert results == []

    def test_is_configured_requires_both_secret_and_token(self):
        assert LineGateway(kernel=_FakeKernel(), channel_secret="s", channel_access_token=None).is_configured() is False
        assert LineGateway(kernel=_FakeKernel(), channel_secret=None, channel_access_token="t").is_configured() is False
        assert LineGateway(kernel=_FakeKernel(), channel_secret="s", channel_access_token="t").is_configured() is True
