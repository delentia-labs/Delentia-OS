"""
Round 108: how the paid-day checks ask the provider about the key (its credit limit, the dollars used, what is left).

The code asked `/auth/key`. OpenRouter's documentation names `/key`; on 2026-11-02 both answered HTTP 401 without a credential (so both exist), but the paid-day preflight must not stand on an
alias the documentation does not mention. `llm_provider.openrouter_key_info` asks `/key` first and `/auth/key` only when `/key` answers 404. These tests run it against the fake provider
in the three shapes the real service could take: both paths, only the documented one, only the older one. Nothing here reaches the network beyond loopback.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import fake_openrouter  # noqa: E402

spec = importlib.util.spec_from_file_location("paid_day_key_info", ROOT / "scripts" / "paid_day.py")
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)

from rct_control_plane.llm_provider import openrouter_key_info  # noqa: E402

PRICES = {"m/x": {"in": 1.0, "out": 1.0}}


@pytest.mark.parametrize("paths", [("/key", "/auth/key"), ("/key",), ("/auth/key",)], ids=["both", "documented only", "older only"])
def test_the_key_check_works_whichever_path_the_provider_answers(paths):
    with fake_openrouter.FakeOpenRouter(PRICES, limit=12.10, key_paths=paths) as fake:
        reply = openrouter_key_info(fake.key, fake.base_url)
        assert reply.status_code == 200
        data = reply.json()["data"]
        assert data["limit"] == 12.10 and data["limit_remaining"] == 12.10 and data["usage"] == 0
        info = pd.key_info(fake.key, fake.base_url)
        assert info == {"usage": 0.0, "limit": 12.10, "limit_remaining": 12.10}


def test_the_documented_path_is_asked_first(monkeypatch):
    asked = []
    real_get = openrouter_key_info.__globals__["httpx"].get

    def spy(url, **kw):
        asked.append(url.rsplit("/api/v1", 1)[-1])
        return real_get(url, **kw)
    monkeypatch.setattr(openrouter_key_info.__globals__["httpx"], "get", spy)
    with fake_openrouter.FakeOpenRouter(PRICES, key_paths=("/key", "/auth/key")) as fake:
        openrouter_key_info(fake.key, fake.base_url)
    assert asked == ["/key"], asked                                         # one request: no fallback when the documented path answers


def test_a_wrong_key_is_refused_without_the_key_in_the_message():
    with fake_openrouter.FakeOpenRouter(PRICES, limit=12.10) as fake:
        secret = "sk-or-v1-this-is-not-the-fake-key-0123456789"
        with pytest.raises(pd.Refused) as why:
            pd.key_info(secret, fake.base_url)
    assert "401" in str(why.value) and secret not in str(why.value)


def test_no_path_answering_at_all_is_a_refusal_not_a_crash_with_a_made_up_limit():
    with fake_openrouter.FakeOpenRouter(PRICES, limit=12.10, key_paths=()) as fake:
        with pytest.raises(pd.Refused) as why:
            pd.key_info(fake.key, fake.base_url)
    assert "404" in str(why.value)
