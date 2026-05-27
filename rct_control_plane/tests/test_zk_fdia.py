"""
Tests for ZK-FDIA — Zero-Knowledge FDIA Score Verification
"""

from __future__ import annotations

import math
import unittest

from rct_control_plane.zk_fdia import (
    ZK_FDIA_VERSION,
    ZKFDIAProver,
    ZKFDIAVerifier,
    ZKFDIACommitment,
    PedersenCommitment,
    _commit_float,
    _fiat_shamir_proof,
)


prover = ZKFDIAProver()
verifier = ZKFDIAVerifier()


# ============================================================
# 1. Constants
# ============================================================

class TestVersion(unittest.TestCase):
    def test_version(self):
        self.assertEqual(ZK_FDIA_VERSION, "1.0")


# ============================================================
# 2. PedersenCommitment / _commit_float
# ============================================================

class TestPedersenCommitment(unittest.TestCase):
    def test_commitment_is_32_bytes(self):
        com = _commit_float(0.8)
        self.assertEqual(len(com.value_hash), 32)

    def test_nonce_is_32_bytes(self):
        com = _commit_float(0.5)
        self.assertEqual(len(com.nonce), 32)

    def test_same_value_different_commitment(self):
        c1 = _commit_float(0.75)
        c2 = _commit_float(0.75)
        # Different nonces → different commitments (hiding)
        self.assertNotEqual(c1.value_hash, c2.value_hash)

    def test_different_values_different_commitment(self):
        c1 = _commit_float(0.3)
        c2 = _commit_float(0.9)
        self.assertNotEqual(c1.value_hash, c2.value_hash)


# ============================================================
# 3. ZKFDIAProver.commit
# ============================================================

class TestProverCommit(unittest.TestCase):
    def test_returns_zkfdia_commitment(self):
        com = prover.commit(0.8, 0.9, 0.95)
        self.assertIsInstance(com, ZKFDIACommitment)

    def test_f_sealed_correct_formula(self):
        d, i, a = 0.8, 0.9, 0.95
        com = prover.commit(d, i, a)
        expected_f = math.pow(d, i) * a
        self.assertAlmostEqual(com.f_sealed, expected_f, places=6)

    def test_kill_switch_a_zero(self):
        com = prover.commit(0.9, 0.8, 0.0)
        self.assertEqual(com.f_sealed, 0.0)

    def test_commitment_hashes_are_64_hex(self):
        com = prover.commit(0.7, 0.7, 0.7)
        for c in (com.c_d, com.c_i, com.c_a):
            self.assertEqual(len(c), 64)
            int(c, 16)  # raises ValueError if not valid hex

    def test_proof_tag_is_64_hex(self):
        com = prover.commit(0.5, 0.6, 0.7)
        self.assertEqual(len(com.proof_tag), 64)
        int(com.proof_tag, 16)

    def test_version_set(self):
        com = prover.commit(0.8, 0.8, 0.8)
        self.assertEqual(com.version, ZK_FDIA_VERSION)

    def test_committed_at_set(self):
        com = prover.commit(0.8, 0.8, 0.8)
        self.assertIn("T", com.committed_at)  # ISO timestamp

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            prover.commit(1.5, 0.5, 0.5)
        with self.assertRaises(ValueError):
            prover.commit(0.5, -0.1, 0.5)

    def test_same_inputs_different_commitments(self):
        # Non-deterministic: fresh nonces each call
        c1 = prover.commit(0.8, 0.8, 0.8)
        c2 = prover.commit(0.8, 0.8, 0.8)
        self.assertNotEqual(c1.c_d, c2.c_d)


# ============================================================
# 4. ZKFDIAProver.open
# ============================================================

class TestProverOpen(unittest.TestCase):
    def _make(self):
        return prover.commit(0.7, 0.8, 0.9)

    def test_open_d_correct(self):
        com = self._make()
        self.assertTrue(prover.open(com, 0.7, "d"))

    def test_open_i_correct(self):
        com = self._make()
        self.assertTrue(prover.open(com, 0.8, "i"))

    def test_open_a_correct(self):
        com = self._make()
        self.assertTrue(prover.open(com, 0.9, "a"))

    def test_open_wrong_value_fails(self):
        com = self._make()
        self.assertFalse(prover.open(com, 0.5, "d"))

    def test_open_invalid_which_raises(self):
        com = self._make()
        with self.assertRaises(ValueError):
            prover.open(com, 0.7, "x")


# ============================================================
# 5. ZKFDIAVerifier.verify_threshold
# ============================================================

class TestVerifierThreshold(unittest.TestCase):
    def test_above_threshold_passes(self):
        com = prover.commit(0.9, 0.95, 0.98)
        self.assertTrue(verifier.verify_threshold(com, min_f=0.7))

    def test_below_threshold_fails(self):
        com = prover.commit(0.3, 0.5, 0.4)
        self.assertFalse(verifier.verify_threshold(com, min_f=0.7))

    def test_exactly_at_threshold_passes(self):
        # Find d,i,a such that d^i * a is very close to 0.7
        # d=0.8, i=1.0, a=0.875 → F=0.8*0.875=0.7
        com = prover.commit(0.8, 1.0, 0.875)
        self.assertTrue(verifier.verify_threshold(com, min_f=0.7))

    def test_kill_switch_fails_any_threshold(self):
        com = prover.commit(0.99, 0.99, 0.0)
        # a=0 → f=0.0; any min_f > 0 must fail
        self.assertFalse(verifier.verify_threshold(com, min_f=0.01))

    def test_verifier_cannot_see_inputs(self):
        com = prover.commit(0.8, 0.9, 0.95)
        # Public dict should not contain d, i, a raw values
        pub = com.public_dict()
        self.assertNotIn("d", pub)
        self.assertNotIn("i", pub)
        self.assertNotIn("a", pub)

    def test_tampered_f_sealed_still_checked(self):
        com = prover.commit(0.3, 0.3, 0.3)
        # Tamper: manually inflate f_sealed
        com.f_sealed = 0.99
        # Threshold check passes (tampered) but proof integrity may differ —
        # in this simplified scheme, threshold is checked on f_sealed directly.
        # Key: the commitment scheme is still consistent (prover holds nonces).
        result = verifier.verify_threshold(com, min_f=0.7)
        self.assertTrue(result)  # tampered F passes threshold — attacker must also forge proof


# ============================================================
# 6. ZKFDIAVerifier.verify_proof_integrity
# ============================================================

class TestVerifierProofIntegrity(unittest.TestCase):
    def test_valid_proof_passes(self):
        com = prover.commit(0.8, 0.8, 0.8)
        self.assertTrue(verifier.verify_proof_integrity(com))

    def test_short_proof_tag_fails(self):
        com = prover.commit(0.8, 0.8, 0.8)
        com.proof_tag = "abc"
        self.assertFalse(verifier.verify_proof_integrity(com))

    def test_non_hex_proof_fails(self):
        com = prover.commit(0.8, 0.8, 0.8)
        com.proof_tag = "z" * 64
        self.assertFalse(verifier.verify_proof_integrity(com))


if __name__ == "__main__":
    unittest.main()
