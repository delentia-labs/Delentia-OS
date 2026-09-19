"""
Real ALGO-29 UIA retry-exhaustion bug fix test — Round 27 Phase 24 Task 49.

Verified via direct code read: `raise last_exception` at algo_29_uia.py's
REST adapter could execute with `last_exception` still None (its initial
value) when `retry_attempts == 0`, since the for-loop that sets it never
runs — producing a confusing `TypeError: exceptions must derive from
BaseException` instead of an honest, diagnostic error. Every real call
site elsewhere in this codebase uses retry_attempts >= 1, so this is the
only path this fix changes.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import pytest

from rct_control_plane.algo_29_uia import RESTAdapter


def test_zero_retry_attempts_raises_honest_runtime_error_not_typeerror():
    adapter = RESTAdapter({"base_url": "http://127.0.0.1:1", "retry_attempts": 0})

    with pytest.raises(RuntimeError, match="retry_attempts=0"):
        asyncio.run(adapter.execute_request("GET /", {}))
