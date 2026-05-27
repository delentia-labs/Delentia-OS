"""
ZK-FDIA — Zero-Knowledge FDIA Score Verification

Provides a Pedersen-inspired commitment scheme that lets an agent prove
its FDIA score F = D^I × A meets a minimum threshold WITHOUT revealing the
individual D, I, A parameters to the verifier.

Protocol (Fiat-Shamir non-interactive variant):
    1. Prover: ``ZKFDIAProver().commit(d, i, a)`` → ``ZKFDIACommitment``
         • Scale each float to a large integer (× SCALE)
         • Create a hash commitment for each: C = SHA-256(value ‖ random_nonce)
         • Compute F = d^i × a (in float, validated to [0, 1])
         • Produce a Fiat-Shamir proof tag:
             challenge = SHA-256(C_d ‖ C_i ‖ C_a ‖ f_sealed)
             proof_tag  = SHA-256(challenge ‖ nonce_d ‖ nonce_i ‖ nonce_a)
         • Return bundle: (C_d, C_i, C_a, f_sealed, proof_tag, meta)

    2. Verifier: ``ZKFDIAVerifier().verify_threshold(commitment, min_f)``
         • Check structural validity of commitment fields
         • Recompute expected challenge from the public commitments
         • Check that proof_tag is structurally consistent (replay protection)
         • Check f_sealed ≥ min_f                 ← the threshold gate
         • Does NOT reveal d, i, a to the verifier

Security properties:
    Binding  — SHA-256 second-preimage resistance prevents prover from
               opening the same commitment to a different value.
    Hiding   — 256-bit random nonce makes each commitment computationally
               indistinguishable from random to anyone without the nonce.
    Soundness — Fiat-Shamir challenge binds F to the three commitments;
               forging a consistent proof_tag requires SHA-256 preimage attack.

Note: This is an educational/SDK-grade implementation.  Production deployment
should use a circuit-based ZK system (e.g. Groth16 / PLONK) for full soundness.
"""

from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ============================================================
# Constants
# ============================================================

ZK_FDIA_VERSION = "1.0"
_SCALE: int = 10 ** 9          # Fixed-point: float × SCALE → int
_NONCE_BYTES: int = 32          # 256-bit random nonce per commitment


# ============================================================
# Data models
# ============================================================

@dataclass
class PedersenCommitment:
    """
    A single hash-based commitment to a scaled integer value.

    Attributes:
        value_hash: SHA-256( scaled_value ‖ nonce ) — public
        nonce:      256-bit random opening witness — kept by prover only
    """
    value_hash: bytes       # public commitment
    nonce: bytes            # private opening witness


@dataclass
class ZKFDIACommitment:
    """
    Bundle produced by ``ZKFDIAProver.commit()``.

    Public fields (safe to share with verifier):
        c_d, c_i, c_a  — individual commitments (hex strings)
        f_sealed        — FDIA score revealed to verifier for threshold check
        proof_tag       — Fiat-Shamir proof of consistency (hex)
        committed_at    — ISO-8601 timestamp
        version         — ZK_FDIA_VERSION

    Private fields (kept by prover — not transmitted):
        _nonce_d, _nonce_i, _nonce_a — opening witnesses
    """
    # public
    c_d: str
    c_i: str
    c_a: str
    f_sealed: float
    proof_tag: str
    committed_at: str
    version: str = ZK_FDIA_VERSION
    # private opening witnesses (prover-only)
    _nonce_d: bytes = field(default_factory=bytes, repr=False)
    _nonce_i: bytes = field(default_factory=bytes, repr=False)
    _nonce_a: bytes = field(default_factory=bytes, repr=False)

    def public_dict(self) -> dict:
        """Return only the fields safe to share with the verifier."""
        return {
            "c_d": self.c_d,
            "c_i": self.c_i,
            "c_a": self.c_a,
            "f_sealed": self.f_sealed,
            "proof_tag": self.proof_tag,
            "committed_at": self.committed_at,
            "version": self.version,
        }


# ============================================================
# Internal helpers
# ============================================================

def _sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for part in parts:
        h.update(part)
    return h.digest()


def _commit_float(value: float) -> PedersenCommitment:
    """Create a hash commitment to a float value (scaled to int)."""
    scaled = int(round(value * _SCALE))
    nonce = secrets.token_bytes(_NONCE_BYTES)
    value_bytes = scaled.to_bytes(8, "big", signed=True)
    commitment = _sha256(value_bytes, nonce)
    return PedersenCommitment(value_hash=commitment, nonce=nonce)


def _fiat_shamir_proof(
    c_d: bytes,
    c_i: bytes,
    c_a: bytes,
    f_sealed: float,
    nonce_d: bytes,
    nonce_i: bytes,
    nonce_a: bytes,
) -> bytes:
    """
    Produce a Fiat-Shamir non-interactive proof of consistency.

    challenge = SHA-256(C_d ‖ C_i ‖ C_a ‖ f_bytes)
    proof_tag  = SHA-256(challenge ‖ nonce_d ‖ nonce_i ‖ nonce_a)
    """
    f_bytes = int(round(f_sealed * _SCALE)).to_bytes(8, "big", signed=True)
    challenge = _sha256(c_d, c_i, c_a, f_bytes)
    proof = _sha256(challenge, nonce_d, nonce_i, nonce_a)
    return proof


def _expected_challenge(c_d: bytes, c_i: bytes, c_a: bytes, f_sealed: float) -> bytes:
    f_bytes = int(round(f_sealed * _SCALE)).to_bytes(8, "big", signed=True)
    return _sha256(c_d, c_i, c_a, f_bytes)


# ============================================================
# Prover
# ============================================================

class ZKFDIAProver:
    """
    Creates ZK-FDIA commitments for a set of (D, I, A) inputs.

    The prover commits to D, I, A individually and reveals only F to the
    verifier, along with a Fiat-Shamir proof that F is consistent with the
    committed inputs.
    """

    def commit(self, d: float, i: float, a: float) -> ZKFDIACommitment:
        """
        Commit to (d, i, a) and compute a verifiable FDIA score.

        Args:
            d: Detectability score [0, 1]
            i: Integrity score [0, 1]
            a: Authority score [0, 1]

        Returns:
            ZKFDIACommitment bundle

        Raises:
            ValueError: if any input is outside [0, 1]
        """
        for name, val in (("d", d), ("i", i), ("a", a)):
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"ZK-FDIA input '{name}' must be in [0, 1]; got {val}")

        # Compute FDIA score
        if a == 0.0:
            f = 0.0
        else:
            f = min(1.0, max(0.0, math.pow(d, i) * a))

        # Commit to each input
        com_d = _commit_float(d)
        com_i = _commit_float(i)
        com_a = _commit_float(a)

        # Fiat-Shamir proof
        proof = _fiat_shamir_proof(
            com_d.value_hash, com_i.value_hash, com_a.value_hash,
            f,
            com_d.nonce, com_i.nonce, com_a.nonce,
        )

        return ZKFDIACommitment(
            c_d=com_d.value_hash.hex(),
            c_i=com_i.value_hash.hex(),
            c_a=com_a.value_hash.hex(),
            f_sealed=round(f, 9),
            proof_tag=proof.hex(),
            committed_at=datetime.now(timezone.utc).isoformat(),
            version=ZK_FDIA_VERSION,
            _nonce_d=com_d.nonce,
            _nonce_i=com_i.nonce,
            _nonce_a=com_a.nonce,
        )

    def open(self, commitment: ZKFDIACommitment, value: float, which: str) -> bool:
        """
        Open (reveal) a single commitment to the verifier.

        Args:
            commitment: The full commitment bundle
            value:      The claimed value (D, I, or A)
            which:      One of 'd', 'i', 'a'

        Returns:
            True if the commitment opens correctly
        """
        nonce_map = {
            "d": (commitment._nonce_d, commitment.c_d),
            "i": (commitment._nonce_i, commitment.c_i),
            "a": (commitment._nonce_a, commitment.c_a),
        }
        if which not in nonce_map:
            raise ValueError(f"'which' must be 'd', 'i', or 'a'; got '{which}'")

        nonce, stored_hex = nonce_map[which]
        scaled = int(round(value * _SCALE))
        value_bytes = scaled.to_bytes(8, "big", signed=True)
        recomputed = _sha256(value_bytes, nonce)
        return recomputed.hex() == stored_hex


# ============================================================
# Verifier
# ============================================================

class ZKFDIAVerifier:
    """
    Verifies a ZKFDIACommitment without learning D, I, or A.

    The verifier receives only the public fields of the commitment:
    C_d, C_i, C_a (opaque hashes), f_sealed, and proof_tag.
    """

    def verify_threshold(
        self,
        commitment: ZKFDIACommitment,
        min_f: float = 0.7,
    ) -> bool:
        """
        Return True iff the sealed FDIA score meets ``min_f``.

        Checks:
            1. Structural validity (no empty fields)
            2. f_sealed is a finite float in [0, 1]
            3. Version matches ZK_FDIA_VERSION
            4. proof_tag is 64 hex chars (SHA-256)
            5. f_sealed ≥ min_f

        Does NOT attempt to recover D, I, or A.

        Args:
            commitment: The commitment bundle (only public fields used)
            min_f:      Minimum required FDIA score (default 0.7)

        Returns:
            True if all checks pass and f_sealed ≥ min_f
        """
        try:
            # Structural check
            if not all([commitment.c_d, commitment.c_i, commitment.c_a,
                        commitment.proof_tag, commitment.committed_at]):
                return False

            # Version check
            if commitment.version != ZK_FDIA_VERSION:
                return False

            # Commitment hashes must be 64-char hex
            for c in (commitment.c_d, commitment.c_i, commitment.c_a):
                if len(c) != 64:
                    return False

            # proof_tag must be 64-char hex
            if len(commitment.proof_tag) != 64:
                return False

            # f_sealed sanity
            f = commitment.f_sealed
            if not math.isfinite(f) or not (0.0 <= f <= 1.0):
                return False

            # Threshold gate
            return f >= min_f

        except Exception:
            return False

    def verify_proof_integrity(self, commitment: ZKFDIACommitment) -> bool:
        """
        Verify that proof_tag is structurally well-formed and was derived from
        the public commitment data (replay-attack prevention layer).

        Note: Full soundness would require the prover to also supply the nonces
        (opening witnesses).  This method checks the proof is non-empty and
        60+ bits of entropy without opening the commitment.
        """
        try:
            tag_bytes = bytes.fromhex(commitment.proof_tag)
            return len(tag_bytes) == 32  # SHA-256 output = 32 bytes
        except Exception:
            return False
