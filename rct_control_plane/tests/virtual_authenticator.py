"""A software WebAuthn authenticator for tests (not shipped to users).

It does what a platform authenticator does on the wire: makes a key pair, answers a registration ceremony with an `attestationObject` (format "none"), and answers an assertion ceremony with
authenticatorData + clientDataJSON + a signature over authenticatorData || sha256(clientDataJSON). Switches let a test make it misbehave in exactly the ways the verifier must refuse.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
from typing import Any, Dict, Optional

from rct_control_plane import passkeys
from rct_control_plane.passkeys import b64u, cbor_encode, unb64u


class VirtualAuthenticator:
    def __init__(self, alg: str = "ES256", rp_id: str = "localhost", origin: str = "http://localhost:3000", user_verified: bool = True, backup_eligible: bool = False) -> None:
        from cryptography.hazmat.primitives.asymmetric import ec, rsa
        self.alg, self.rp_id, self.origin, self.uv, self.be = alg, rp_id, origin, user_verified, backup_eligible
        self.credential_id = os.urandom(32)
        self.counter = 0
        if alg == "ES256":
            self.key = ec.generate_private_key(ec.SECP256R1())
        else:
            self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # ---------------------------------------------------------------- helpers
    def _flags(self, attested: bool, uv: Optional[bool] = None) -> int:
        flags = passkeys.FLAG_UP | (passkeys.FLAG_UV if (self.uv if uv is None else uv) else 0)
        if self.be:
            flags |= passkeys.FLAG_BE
        if attested:
            flags |= passkeys.FLAG_AT
        return flags

    def cose_key(self) -> Dict[int, Any]:
        if self.alg == "ES256":
            numbers = self.key.public_key().public_numbers()
            return {1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")}
        numbers = self.key.public_key().public_numbers()
        return {1: 3, 3: -257, -1: numbers.n.to_bytes(256, "big"), -2: numbers.e.to_bytes(3, "big")}

    def _sign(self, data: bytes) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, padding
        if self.alg == "ES256":
            return self.key.sign(data, ec.ECDSA(hashes.SHA256()))
        return self.key.sign(data, padding.PKCS1v15(), hashes.SHA256())

    # ---------------------------------------------------------------- ceremonies
    def create(self, options: Dict[str, Any], *, origin: Optional[str] = None, rp_id: Optional[str] = None, challenge: Optional[str] = None, uv: Optional[bool] = None,
               ctype: str = "webauthn.create") -> Dict[str, Any]:
        client = json.dumps({"type": ctype, "challenge": challenge if challenge is not None else options["challenge"], "origin": origin or self.origin}).encode("utf-8")
        rp_hash = hashlib.sha256((rp_id or self.rp_id).encode("utf-8")).digest()
        attested = b"\x00" * 16 + struct.pack(">H", len(self.credential_id)) + self.credential_id + cbor_encode(self.cose_key())
        auth = rp_hash + bytes([self._flags(True, uv)]) + struct.pack(">I", self.counter) + attested
        attestation = cbor_encode({"fmt": "none", "attStmt": {}, "authData": auth})
        return {"id": b64u(self.credential_id), "rawId": b64u(self.credential_id), "type": "public-key",
                "response": {"clientDataJSON": b64u(client), "attestationObject": b64u(attestation)}}

    def get(self, options: Dict[str, Any], *, origin: Optional[str] = None, rp_id: Optional[str] = None, challenge: Optional[str] = None, uv: Optional[bool] = None,
            bump: bool = True, tamper: bool = False) -> Dict[str, Any]:
        if bump:
            self.counter += 1
        client = json.dumps({"type": "webauthn.get", "challenge": challenge if challenge is not None else options["challenge"], "origin": origin or self.origin}).encode("utf-8")
        rp_hash = hashlib.sha256((rp_id or self.rp_id).encode("utf-8")).digest()
        auth = rp_hash + bytes([self._flags(False, uv)]) + struct.pack(">I", self.counter)
        signature = self._sign(auth + hashlib.sha256(client).digest())
        if tamper:
            signature = signature[:-1] + bytes([signature[-1] ^ 1])
        return {"id": b64u(self.credential_id), "rawId": b64u(self.credential_id), "type": "public-key",
                "response": {"authenticatorData": b64u(auth), "clientDataJSON": b64u(client), "signature": b64u(signature), "userHandle": None}}


def decode_challenge(options: Dict[str, Any]) -> bytes:
    return unb64u(options["challenge"], 64)
