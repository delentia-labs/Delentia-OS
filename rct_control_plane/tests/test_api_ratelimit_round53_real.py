"""
Round 53: rate limiting for the kernel API. The token bucket is tested with an injected clock; the middleware
is exercised through the real FastAPI app (starlette's in-process client) with a tiny limit.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from fastapi.testclient import TestClient

from rct_control_plane import api_ratelimit as rl
from rct_control_plane.api import create_app


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# ------------------------------------------------------------------ parsing and costs

@pytest.mark.parametrize("raw,expected", [
    ("600/60", (600, 60.0)), (" 10/1 ", (10, 1.0)), ("5/0.5", (5, 0.5)),
    (None, None), ("", None), ("0", None), ("off", None), ("abc", None), ("10", None), ("0/60", None), ("10/0", None), ("-5/60", None), ("1/2/3", None),
])
def test_parse_limit(raw, expected):
    assert rl.parse_limit(raw) == expected


def test_costs_follow_path_prefixes_and_never_match_a_lookalike():
    assert rl.cost_of("/v1/agent/run") == 20
    assert rl.cost_of("/v1/agent/approvals/abc/decision") == 2
    assert rl.cost_of("/mcp") == 3 and rl.cost_of("/mcp/tools") == 3
    assert rl.cost_of("/v1/agent/running-late") == 1
    assert rl.cost_of("/v1/desk/status") == 1


# ------------------------------------------------------------------ the bucket

def test_a_caller_can_burst_up_to_the_capacity_then_waits_for_refill():
    clock = Clock()
    buckets = rl.TokenBuckets(10, 10.0, clock)                      # 1 token per second
    assert all(buckets.take("a", 1) == 0 for _ in range(10))
    wait = buckets.take("a", 1)
    assert 0.9 < wait <= 1.0
    clock.now += 1.0
    assert buckets.take("a", 1) == 0
    assert buckets.take("a", 1) > 0


def test_callers_do_not_share_a_bucket():
    buckets = rl.TokenBuckets(2, 60.0, Clock())
    assert buckets.take("a", 2) == 0 and buckets.take("a", 1) > 0
    assert buckets.take("b", 2) == 0


def test_an_expensive_request_drains_more_and_a_full_bucket_is_needed_for_one_dearer_than_it():
    clock = Clock()
    buckets = rl.TokenBuckets(30, 60.0, clock)
    assert buckets.take("a", 20) == 0
    assert buckets.take("a", 20) > 0                                # 10 left, 20 needed
    assert buckets.take("b", 999) == 0                              # capped at the capacity, a full bucket suffices once


def test_refill_never_exceeds_the_capacity():
    clock = Clock()
    buckets = rl.TokenBuckets(5, 5.0, clock)
    buckets.take("a", 5)
    clock.now += 10_000
    assert all(buckets.take("a", 1) == 0 for _ in range(5)) and buckets.take("a", 1) > 0


def test_memory_is_bounded(monkeypatch):
    monkeypatch.setattr(rl, "MAX_CALLERS", 50)
    buckets = rl.TokenBuckets(5, 5.0, Clock())
    for i in range(500):
        buckets.take(f"caller-{i}", 1)
    assert len(buckets._buckets) == 50


def test_caller_identity_prefers_the_token_hash_and_never_the_forwarded_header():
    scope = {"headers": [(b"authorization", b"Bearer secret-token-1"), (b"x-forwarded-for", b"9.9.9.9")], "client": ("1.2.3.4", 5)}
    ident = rl.caller_id(scope)
    assert ident.startswith("token:") and "secret" not in ident
    assert rl.caller_id({"headers": [(b"x-forwarded-for", b"9.9.9.9")], "client": ("1.2.3.4", 5)}) == "ip:1.2.3.4"
    assert rl.caller_id({"headers": [(b"x-delentia-token", b"abc")], "client": ("1.2.3.4", 5)}).startswith("token:")


def test_by_ip_overrides_the_token(monkeypatch):
    monkeypatch.setenv(rl.BY_ENV, "ip")
    assert rl.caller_id({"headers": [(b"authorization", b"Bearer t")], "client": ("1.2.3.4", 5)}) == "ip:1.2.3.4"


# ------------------------------------------------------------------ through the real app

@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    with TestClient(create_app()) as c:
        yield c


def test_off_by_default_nothing_is_limited(client, monkeypatch):
    monkeypatch.delenv(rl.RATE_ENV, raising=False)
    assert all(client.get("/v1/desk/status").status_code != 429 for _ in range(30))


def test_over_the_limit_gets_429_with_retry_after_and_health_stays_open(client, monkeypatch):
    monkeypatch.setenv(rl.RATE_ENV, "5/60")
    seen = [client.get("/v1/desk/models/setup").status_code for _ in range(8)]
    assert seen[:5] == [200] * 5 and seen[5:] == [429] * 3
    limited = client.get("/v1/desk/models/setup")
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
    assert limited.json()["retry_after_seconds"] >= 1
    assert client.get("/health").status_code == 200 and client.get("/").status_code == 200


def test_an_expensive_endpoint_runs_out_far_sooner(client, monkeypatch):
    monkeypatch.setenv(rl.RATE_ENV, "30/60")
    first = client.post("/v1/agent/run", json={"goal": ""})                 # a bad request still costs 20 tokens
    second = client.post("/v1/agent/run", json={"goal": ""})
    assert first.status_code != 429 and second.status_code == 429


def test_two_tokens_two_buckets(monkeypatch):
    monkeypatch.setenv("DELENTIA_API_TOKEN", "alpha")
    monkeypatch.setenv(rl.RATE_ENV, "2/60")
    with TestClient(create_app()) as c:
        a = {"Authorization": "Bearer alpha"}
        assert [c.get("/v1/desk/models/setup", headers=a).status_code for _ in range(3)] == [200, 200, 429]
        assert c.get("/v1/desk/models/setup").status_code == 401            # authentication still comes first


def test_serve_turns_it_on_by_default():
    from rct_control_plane.cli import cli
    import inspect
    source = inspect.getsource(cli.commands["serve"].callback)
    assert "DEFAULT_SERVE_LIMIT" in source and "setdefault" in source
    assert rl.parse_limit(rl.DEFAULT_SERVE_LIMIT) == (600, 60.0)
