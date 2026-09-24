"""
Round 43 item 5: real coverage for enterprise_hardening.py (Layer 10 JWT
RS256 + Circuit Breaker), previously untested under pytest despite already
having a real, working __main__ smoke test (see this module's own bottom
section) - that smoke test never runs under `pytest` (it only fires when
the file is executed directly), so coverage tooling never saw any of it
execute. These tests port the SAME real assertions the smoke test already
proved (no mocking - real RSA keys, real JWT signing/verification, real
wall-clock timing for expiry/recovery) into real pytest functions.
"""
import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

from rct_control_plane.enterprise_hardening import (
    RS256KeyPair, issue_jwt, verify_jwt,
    CircuitBreaker, CircuitState, CircuitOpenError,
)


class TestRS256KeyPair:
    def test_generate_produces_a_real_usable_keypair(self):
        kp = RS256KeyPair.generate(key_size=2048)
        assert b"PRIVATE KEY" in kp.private_pem()
        assert b"PUBLIC KEY" in kp.public_pem()

    def test_from_private_pem_round_trips(self):
        original = RS256KeyPair.generate()
        restored = RS256KeyPair.from_private_pem(original.private_pem())
        assert restored.public_pem() == original.public_pem()

    def test_from_private_pem_rejects_non_rsa_key(self):
        ed_key = ed25519.Ed25519PrivateKey.generate()
        pem = ed_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        with pytest.raises(ValueError):
            RS256KeyPair.from_private_pem(pem)


class TestIssueAndVerifyJWT:
    def test_real_round_trip_preserves_claims(self):
        kp = RS256KeyPair.generate()
        token = issue_jwt({"sub": "architect", "role": "owner"}, kp, expires_in_seconds=60)
        claims = verify_jwt(token, kp)
        assert claims["sub"] == "architect"
        assert claims["role"] == "owner"

    def test_iat_and_exp_are_set_from_real_time_not_caller_supplied(self):
        kp = RS256KeyPair.generate()
        before = int(time.time())
        # A caller-supplied exp/iat must be overwritten, not trusted -
        # otherwise a caller could mint a token that never expires.
        token = issue_jwt({"sub": "x", "exp": before + 999999, "iat": 0}, kp, expires_in_seconds=60)
        claims = verify_jwt(token, kp)
        assert claims["iat"] >= before
        assert claims["exp"] == claims["iat"] + 60

    def test_tampered_token_is_rejected(self):
        kp = RS256KeyPair.generate()
        token = issue_jwt({"sub": "architect"}, kp)
        tampered = token[:-4] + "abcd"
        with pytest.raises(jwt.InvalidTokenError):
            verify_jwt(tampered, kp)

    def test_verification_against_the_wrong_public_key_is_rejected(self):
        kp = RS256KeyPair.generate()
        other = RS256KeyPair.generate()
        token = issue_jwt({"sub": "architect"}, kp)
        with pytest.raises(jwt.InvalidTokenError):
            verify_jwt(token, other)

    def test_real_expiry_is_enforced(self):
        kp = RS256KeyPair.generate()
        token = issue_jwt({"sub": "architect"}, kp, expires_in_seconds=1)
        time.sleep(1.5)
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_jwt(token, kp)


class TestCircuitBreakerSyncCall:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_successful_calls_stay_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.total_successes == 1

    def test_trips_open_after_failure_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=30.0)

        def always_fails():
            raise RuntimeError("real simulated downstream failure")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(always_fails)
        assert cb.state == CircuitState.OPEN
        assert cb.stats.total_failures == 3

    def test_open_circuit_short_circuits_without_calling_the_real_function(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=30.0)
        call_count = {"n": 0}

        def always_fails():
            call_count["n"] += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            cb.call(always_fails)
        assert cb.state == CircuitState.OPEN

        calls_before = call_count["n"]
        with pytest.raises(CircuitOpenError):
            cb.call(always_fails)
        assert call_count["n"] == calls_before, "an OPEN circuit must not invoke the real function"
        assert cb.stats.total_short_circuited == 1

    def test_transitions_to_half_open_after_real_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.3)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitState.OPEN
        time.sleep(0.4)
        assert cb.state == CircuitState.HALF_OPEN

    def test_successful_half_open_probe_closes_the_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.2)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        time.sleep(0.3)
        assert cb.state == CircuitState.HALF_OPEN

        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_failed_half_open_probe_reopens_the_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.2)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        time.sleep(0.3)
        assert cb.state == CircuitState.HALF_OPEN

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("still failing")))
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerAsyncCall:
    @pytest.mark.asyncio
    async def test_full_real_lifecycle_closed_open_half_open_closed(self):
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=0.3, name="test-dependency")
        call_count = {"n": 0}

        async def flaky_dependency():
            call_count["n"] += 1
            raise RuntimeError("real simulated downstream failure")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.acall(flaky_dependency)
        assert breaker.state == CircuitState.OPEN

        calls_before = call_count["n"]
        with pytest.raises(CircuitOpenError):
            await breaker.acall(flaky_dependency)
        assert call_count["n"] == calls_before

        await asyncio.sleep(0.4)
        assert breaker.state == CircuitState.HALF_OPEN

        async def healthy_dependency():
            return "real recovered result"

        result = await breaker.acall(healthy_dependency)
        assert result == "real recovered result"
        assert breaker.state == CircuitState.CLOSED


class TestGetStats:
    def test_stats_reflect_real_call_history(self):
        cb = CircuitBreaker(failure_threshold=5, name="stats-test")
        cb.call(lambda: "ok")
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        stats = cb.get_stats()
        assert stats["name"] == "stats-test"
        assert stats["total_calls"] == 2
        assert stats["total_successes"] == 1
        assert stats["total_failures"] == 1
        assert stats["consecutive_failures"] == 1
