"""
Round 50: signedai.api, the module gateway_main.py has always tried to mount
at /signedai but that never existed. Real FastAPI app, real signedai.core
logic; no endpoint may reach a model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from fastapi.testclient import TestClient

from signedai.api import app, router
from signedai.core.registry import SignedAIRegistry, SignedAITier

client = TestClient(app)


def test_health_says_no_model_calls():
    assert client.get("/health").json() == {"status": "ok", "calls_models": False}


def test_tiers_match_the_registry():
    tiers = {t["tier"]: t for t in client.get("/tiers").json()}
    assert set(tiers) == {t.value for t in SignedAIRegistry.TIERS}
    assert tiers["tier_6"]["required_votes"] == 4
    assert tiers["tier_6"]["consensus_threshold"] == round(4 / 6, 4)
    assert tiers["tier_8"]["chairman_veto"] is True


def test_roster_is_public_metadata_only():
    rows = client.get("/roster").json()
    assert rows and {"role", "model_id", "provider", "country"} <= set(rows[0])
    assert not any("key" in field.lower() for row in rows for field in row)


@pytest.mark.parametrize("body,tier", [
    ({"intent": "rename a variable in a unit test"}, "tier-s"),
    ({"intent": "add an api endpoint implementation"}, "tier-4"),
    ({"intent": "run a database migration"}, "tier-6"),
    ({"intent": "fix an authentication vulnerability"}, "tier-8"),
    ({"intent": "tidy docs", "tags": {"environment": "production", "criticality": "high"}}, "tier-8"),
])
def test_route_picks_the_tier_the_router_rules_give(body, tier):
    assert client.post("/route", json=body).json()["tier"] == tier


def test_consensus_uses_count_and_ratio():
    ok = client.post("/consensus", json={"tier": "tier_6", "votes_for": 4, "votes_against": 2}).json()
    assert ok["consensus_reached"] is True
    no = client.post("/consensus", json={"tier": "tier_7_regional", "votes_for": 5, "votes_against": 2}).json()
    assert no["consensus_reached"] is False  # needs 6 votes and 75%
    veto = client.post("/consensus", json={"tier": "tier_8", "votes_for": 6, "votes_against": 0,
                                           "chairman_override": False}).json()
    assert veto["consensus_reached"] is False


def test_more_votes_than_signers_is_rejected():
    r = client.post("/consensus", json={"tier": "tier_4", "votes_for": 4, "votes_against": 1})
    assert r.status_code == 422


def test_estimate_adds_up_the_roster_prices():
    body = client.post("/estimate", json={"tier": "tier_4", "input_tokens": 1_000_000, "output_tokens": 0}).json()
    total, _ = SignedAIRegistry.estimate_tier_cost(SignedAITier.TIER_4, 1_000_000, 0)
    assert body["total_usd"] == round(total, 6)
    assert len(body["by_model"]) >= 1


def test_no_endpoint_reaches_a_model(monkeypatch):
    import signedai.core.openrouter_adapter as ora

    def _boom(*a, **k):
        raise AssertionError("a model was called")
    monkeypatch.setattr(ora.OpenRouterAdapter, "generate", _boom)
    monkeypatch.setattr(ora, "call_hexacore_role", _boom)
    for path in ("/health", "/tiers", "/roster"):
        assert client.get(path).status_code == 200
    assert client.post("/route", json={"intent": "deploy to production"}).status_code == 200
    assert client.post("/consensus", json={"tier": "tier_s", "votes_for": 1, "votes_against": 0}).status_code == 200
    assert client.post("/estimate", json={"tier": "tier_s", "input_tokens": 10, "output_tokens": 10}).status_code == 200


def test_the_gateway_can_mount_the_router():
    from fastapi import FastAPI
    gw = FastAPI()
    gw.include_router(router, prefix="/signedai")
    assert TestClient(gw).get("/signedai/health").status_code == 200
