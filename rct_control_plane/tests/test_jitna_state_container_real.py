"""
Real ALGO-06 JITNA State Container tests — Round 27 Phase 21 Task 43.

Master doc (DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md, section 3, ALGO-06)
specifies "Reflexion & JITNA State Container" - a portable state container
so a task's context isn't lost when moving to a different machine. The real
algo_06_reflexion only covers the Reflexion half. This closes the State
Container half by composing two already-real, already-tested pieces:
RCTDBFacade.restore_session_context (Round 23) and JITNA packet
signing/verification (jitna_protocol.py) - real export/import, real
cryptographic integrity, no fabrication.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_export_produces_a_real_signed_packet_with_the_real_restored_context():
    kernel = AlgorithmKernel41()
    kernel.algo_07_mee(growth_signal=0.9)  # real step, creates real "mee_growth" deltas

    exported = kernel.algo_06_jitna_export_state_container("mee_growth")

    assert exported["message_type"] == "STATE_CONTAINER"
    assert exported["signature"] is not None
    expected_context = kernel._rctdb_facade.restore_session_context("mee_growth")
    assert exported["payload"] == expected_context


def test_import_verifies_a_real_untampered_packet_and_returns_the_real_context():
    kernel = AlgorithmKernel41()
    kernel.algo_07_mee(growth_signal=0.9)
    exported = kernel.algo_06_jitna_export_state_container("mee_growth")

    imported = kernel.algo_06_jitna_import_state_container(exported)

    assert imported["verified"] is True
    assert imported["restored_context"] == exported["payload"]


def test_import_rejects_a_real_tampered_packet():
    kernel = AlgorithmKernel41()
    kernel.algo_07_mee(growth_signal=0.9)
    exported = kernel.algo_06_jitna_export_state_container("mee_growth")

    tampered = dict(exported)
    tampered["payload"] = {"fabricated": "data"}

    imported = kernel.algo_06_jitna_import_state_container(tampered)

    assert imported["verified"] is False
    assert imported["restored_context"] is None
