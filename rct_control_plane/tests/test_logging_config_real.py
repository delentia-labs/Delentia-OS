"""
Real logging_config idempotency test — Round 28 Phase 30 Task 57.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.logging_config import configure_logging


def test_calling_configure_logging_twice_does_not_double_attach_handlers():
    logger1 = configure_logging(name="test_idempotency_logger")
    logger2 = configure_logging(name="test_idempotency_logger")

    assert logger1 is logger2
    assert len(logger1.handlers) == 1, f"expected exactly 1 handler after 2 calls; got {len(logger1.handlers)}"
