"""
Round 101: approve with a passkey (WebAuthn) from the Desk: Windows Hello, a security key or a phone, instead of typing commands.

Why this exists. Until now an approval was an Ed25519 signature made with a key FILE and pasted into the page (`delentia approvals sign|approve`). That is hard for anyone who does not use a terminal, and the key
file sits on the same machine and under the same Windows user as the agent (the docs call that "a speed bump, not a wall"). A passkey keeps its private key in the device (TPM, secure enclave, security key),
never gives it out, and signs only after the person confirms with a fingerprint, face or PIN. So the signature proves "someone with this device confirmed just now", which a file can not.

What is signed. Exactly what already was: the approval message `delentia-approval:v1:<approval_id>:<action_sha256>:<DECISION>` (approvals.approval_message). The WebAuthn challenge IS sha256 of that message, so
an assertion is bound to one action and one decision; the server recomputes it, there is no server-side challenge state to lose or replay, and the same check runs again when the action is claimed for execution.

Trust. A passkey is trusted only after an EXISTING trusted approver (an Ed25519 key) signed its enrollment (a pending action `passkey_enroll` that carries the credential's public-key hash, name, role and scope). Nobody
who merely reaches the Desk can add a device. Revoking a device (a person with the owner token may; it only removes authority) makes every approval it signed that has not yet run void, like removing an Ed25519 key.

What this module does NOT do: it does not show the person the action on the authenticator (WebAuthn can not; the Desk shows it and a second channel should confirm it), it does not verify attestation (the
authenticator's maker is not part of the trust decision; the Ed25519 approver who signs the enrollment is), and it does not handle several users' devices as separate tenants (later).

Minimal CBOR/COSE is parsed by hand (definite lengths only, depth and size limits) so no new dependency is needed; `cryptography` verifies ES256 (P-256) and RS256 (what Windows Hello's TPM often uses).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import struct
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

RP_ID_ENV = "DELENTIA_PASSKEY_RP_ID"
ORIGINS_ENV = "DELENTIA_PASSKEY_ORIGINS"
SIGNER_PREFIX = "passkey:"
ENROLL_TOOL = "passkey_enroll"
ENROLLMENT_TTL_SECONDS = 600
MAX_CLIENT_DATA = 4096
MAX_AUTH_DATA = 4096
MAX_ATTESTATION = 16384
MAX_SIGNATURE = 1024
ALG_ES256, ALG_RS256 = -7, -257
FLAG_UP, FLAG_UV, FLAG_BE, FLAG_BS, FLAG_AT = 0x01, 0x04, 0x08, 0x10, 0x40

_LOCAL_ORIGIN = re.compile(r"^https?://localhost(:\d{1,5})?$")


class PasskeyError(ValueError):
    """A refusal with a reason a person can read. Never contains a key or a signature."""


# ---------------------------------------------------------------------------------------------------------------------------------- settings
def rp_id() -> str:
    return (os.environ.get(RP_ID_ENV) or "localhost").strip().lower()


def allowed_origin(origin: str) -> bool:
    configured = [o.strip() for o in (os.environ.get(ORIGINS_ENV) or "").split(",") if o.strip()]
    if configured:
        return origin in configured
    return rp_id() == "localhost" and bool(_LOCAL_ORIGIN.match(origin or ""))


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def unb64u(text: Any, limit: int) -> bytes:
    if not isinstance(text, str) or len(text) > limit * 2:
        raise PasskeyError("a field is missing or too long")
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise PasskeyError("a field is not valid base64url") from exc
    if len(raw) > limit:
        raise PasskeyError("a field is too long")
    return raw


def signer_key(credential_id: bytes) -> str:
    return SIGNER_PREFIX + hashlib.sha256(credential_id).hexdigest()


def is_passkey_signer(key: str) -> bool:
    return isinstance(key, str) and key.startswith(SIGNER_PREFIX)


# ---------------------------------------------------------------------------------------------------------------------------------- CBOR (minimal, strict)
class _Cbor:
    """Definite-length CBOR: unsigned/negative ints, byte and text strings, arrays, maps, true/false/null. Anything else, any indefinite length, and anything deeper or larger than the limits is refused."""

    MAX_DEPTH = 8
    MAX_ITEMS = 64

    def __init__(self, data: bytes) -> None:
        self.data, self.i, self.items = data, 0, 0

    def _need(self, n: int) -> bytes:
        if n < 0 or self.i + n > len(self.data):
            raise PasskeyError("the data is cut off")
        chunk = self.data[self.i:self.i + n]
        self.i += n
        return chunk

    def _length(self, info: int) -> int:
        if info < 24:
            return info
        if info == 24:
            return self._need(1)[0]
        if info == 25:
            return struct.unpack(">H", self._need(2))[0]
        if info == 26:
            return struct.unpack(">I", self._need(4))[0]
        if info == 27:
            return struct.unpack(">Q", self._need(8))[0]
        raise PasskeyError("an indefinite or reserved length is not accepted")

    def decode(self, depth: int = 0) -> Any:
        if depth > self.MAX_DEPTH:
            raise PasskeyError("the data is nested too deeply")
        self.items += 1
        if self.items > self.MAX_ITEMS * 4:
            raise PasskeyError("the data has too many items")
        head = self._need(1)[0]
        major, info = head >> 5, head & 0x1F
        if major == 0:
            return self._length(info)
        if major == 1:
            return -1 - self._length(info)
        if major in (2, 3):
            n = self._length(info)
            if n > len(self.data) - self.i:
                raise PasskeyError("a string is longer than the data")
            raw = self._need(n)
            if major == 2:
                return raw
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PasskeyError("a text field is not UTF-8") from exc
        if major == 4:
            n = self._length(info)
            if n > self.MAX_ITEMS:
                raise PasskeyError("an array is too long")
            return [self.decode(depth + 1) for _ in range(n)]
        if major == 5:
            n = self._length(info)
            if n > self.MAX_ITEMS:
                raise PasskeyError("a map is too long")
            out: Dict[Any, Any] = {}
            for _ in range(n):
                key = self.decode(depth + 1)
                if not isinstance(key, (int, str)):
                    raise PasskeyError("a map key is not an integer or text")
                out[key] = self.decode(depth + 1)
            return out
        if major == 7:
            if info == 20:
                return False
            if info == 21:
                return True
            if info == 22:
                return None
        raise PasskeyError("a CBOR type that is not accepted here")


def cbor_decode(data: bytes, *, whole: bool = True) -> Tuple[Any, int]:
    reader = _Cbor(data)
    value = reader.decode()
    if whole and reader.i != len(data):
        raise PasskeyError("there is data after the end of the item")
    return value, reader.i


def cbor_encode(value: Any) -> bytes:
    """Encoder for tests and for the software authenticator used by them (definite lengths only)."""
    def head(major: int, n: int) -> bytes:
        if n < 24:
            return bytes([major << 5 | n])
        if n < 256:
            return bytes([major << 5 | 24, n])
        if n < 65536:
            return bytes([major << 5 | 25]) + struct.pack(">H", n)
        return bytes([major << 5 | 26]) + struct.pack(">I", n)
    if value is True:
        return b"\xf5"
    if value is False:
        return b"\xf4"
    if value is None:
        return b"\xf6"
    if isinstance(value, int):
        return head(0, value) if value >= 0 else head(1, -1 - value)
    if isinstance(value, bytes):
        return head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return head(3, len(raw)) + raw
    if isinstance(value, list):
        return head(4, len(value)) + b"".join(cbor_encode(v) for v in value)
    if isinstance(value, dict):
        return head(5, len(value)) + b"".join(cbor_encode(k) + cbor_encode(v) for k, v in value.items())
    raise TypeError(type(value))


# ---------------------------------------------------------------------------------------------------------------------------------- WebAuthn parsing
@dataclass
class ParsedAuthData:
    rp_id_hash: bytes
    flags: int
    sign_count: int
    credential_id: Optional[bytes] = None
    cose_key: Optional[Dict[Any, Any]] = None


def parse_auth_data(auth: bytes, *, expect_credential: bool) -> ParsedAuthData:
    if len(auth) < 37 or len(auth) > MAX_AUTH_DATA:
        raise PasskeyError("the authenticator data has the wrong size")
    parsed = ParsedAuthData(auth[:32], auth[32], struct.unpack(">I", auth[33:37])[0])
    if expect_credential:
        if not parsed.flags & FLAG_AT:
            raise PasskeyError("the authenticator did not return a credential")
        if len(auth) < 55:
            raise PasskeyError("the credential data is cut off")
        id_len = struct.unpack(">H", auth[53:55])[0]
        if id_len < 16 or id_len > 1023 or 55 + id_len > len(auth):
            raise PasskeyError("the credential id has the wrong size")
        parsed.credential_id = auth[55:55 + id_len]
        key, _end = cbor_decode(auth[55 + id_len:], whole=False)
        if not isinstance(key, dict):
            raise PasskeyError("the public key is not a COSE key")
        parsed.cose_key = key
    return parsed


def _client_data(raw: bytes, expected_type: str) -> Dict[str, Any]:
    if len(raw) > MAX_CLIENT_DATA:
        raise PasskeyError("the client data is too long")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PasskeyError("the client data is not JSON") from exc
    if not isinstance(data, dict) or data.get("type") != expected_type:
        raise PasskeyError(f"the client data is not a {expected_type} message")
    if not isinstance(data.get("origin"), str) or not allowed_origin(data["origin"]):
        raise PasskeyError("the request came from an origin that is not allowed")
    if data.get("crossOrigin") is True:
        raise PasskeyError("a cross-origin request is not accepted")
    return data


def public_key_from_cose(key: Dict[Any, Any]) -> Dict[str, Any]:
    """The COSE key as a small JSON-able dict: {"alg": -7, "x": hex, "y": hex} or {"alg": -257, "n": hex, "e": hex}. Only ES256 (P-256) and RS256 (2048+ bits)."""
    alg = key.get(3)
    if alg == ALG_ES256:
        if key.get(1) != 2 or key.get(-1) != 1 or not isinstance(key.get(-2), bytes) or not isinstance(key.get(-3), bytes) or len(key[-2]) != 32 or len(key[-3]) != 32:
            raise PasskeyError("the P-256 public key is malformed")
        _es256_public_key(key[-2], key[-3])                    # raises if the point is not on the curve
        return {"alg": ALG_ES256, "x": key[-2].hex(), "y": key[-3].hex()}
    if alg == ALG_RS256:
        n, e = key.get(-1), key.get(-2)
        if key.get(1) != 3 or not isinstance(n, bytes) or not isinstance(e, bytes) or not (256 <= len(n) <= 1024) or not (1 <= len(e) <= 8):
            raise PasskeyError("the RSA public key is malformed")
        return {"alg": ALG_RS256, "n": n.hex(), "e": e.hex()}
    raise PasskeyError("the credential uses a signature algorithm that is not accepted (ES256 and RS256 are)")


def _es256_public_key(x: bytes, y: bytes) -> Any:
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        return ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()).public_key()
    except ValueError as exc:
        raise PasskeyError("the P-256 public key is not a point on the curve") from exc


def verify_signature(public_key: Dict[str, Any], signed: bytes, signature: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    if len(signature) > MAX_SIGNATURE:
        return False
    try:
        if public_key.get("alg") == ALG_ES256:
            _es256_public_key(bytes.fromhex(public_key["x"]), bytes.fromhex(public_key["y"])).verify(signature, signed, ec.ECDSA(hashes.SHA256()))
            return True
        if public_key.get("alg") == ALG_RS256:
            rsa.RSAPublicNumbers(int(public_key["e"], 16), int(public_key["n"], 16)).public_key().verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
            return True
    except (InvalidSignature, ValueError, KeyError, PasskeyError):
        return False
    return False


# ---------------------------------------------------------------------------------------------------------------------------------- the store
SCHEMA = """
CREATE TABLE IF NOT EXISTS approver_credentials (
    credential_id   TEXT PRIMARY KEY,
    signer_key      TEXT NOT NULL UNIQUE,
    public_key_json TEXT NOT NULL,
    sign_count      INTEGER NOT NULL DEFAULT 0,
    name            TEXT NOT NULL,
    role            TEXT,
    scope_json      TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL,
    backup_eligible INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    activated_at    REAL,
    last_used_at    REAL,
    revoked_at      REAL,
    enrollment_approval_id TEXT
);
CREATE TABLE IF NOT EXISTS passkey_enrollments (
    enrollment_id TEXT PRIMARY KEY,
    challenge     TEXT NOT NULL,
    name          TEXT NOT NULL,
    role          TEXT,
    scope_json    TEXT NOT NULL,
    created_at    REAL NOT NULL,
    used          INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class Credential:
    credential_id: str
    signer_key: str
    public_key: Dict[str, Any]
    sign_count: int
    name: str
    role: Optional[str]
    scope: Dict[str, Any]
    status: str
    backup_eligible: bool
    created_at: float
    activated_at: Optional[float]
    last_used_at: Optional[float]
    revoked_at: Optional[float]

    def summary(self) -> Dict[str, Any]:
        return {"id": self.credential_id[:16], "signer": self.signer_key[len(SIGNER_PREFIX):][:16], "name": self.name, "role": self.role, "scope": self.scope, "status": self.status,
                "alg": "ES256" if self.public_key.get("alg") == ALG_ES256 else "RS256", "backup_eligible": self.backup_eligible, "created_at": self.created_at,
                "activated_at": self.activated_at, "last_used_at": self.last_used_at, "revoked_at": self.revoked_at}


_COLUMNS = "credential_id, signer_key, public_key_json, sign_count, name, role, scope_json, status, backup_eligible, created_at, activated_at, last_used_at, revoked_at"


def _row(row: tuple) -> Credential:
    return Credential(row[0], row[1], json.loads(row[2]), int(row[3] or 0), row[4], row[5], json.loads(row[6] or "{}"), row[7], bool(row[8]), row[9], row[10], row[11], row[12])


class PasskeyStore:
    def __init__(self, persistence: Any) -> None:
        self._persistence = persistence
        with persistence._connect() as conn:
            conn.executescript(SCHEMA)

    # ---- reading
    def get_by_signer(self, key: str) -> Optional[Credential]:
        with self._persistence._connect() as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM approver_credentials WHERE signer_key = ?", (key,)).fetchone()
        return _row(row) if row else None

    def get(self, credential_id: str) -> Optional[Credential]:
        with self._persistence._connect() as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM approver_credentials WHERE credential_id = ?", (credential_id,)).fetchone()
        return _row(row) if row else None

    def list(self, status: Optional[str] = None) -> List[Credential]:
        query = f"SELECT {_COLUMNS} FROM approver_credentials"
        params: tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        with self._persistence._connect() as conn:
            rows = conn.execute(query + " ORDER BY created_at", params).fetchall()
        return [_row(r) for r in rows]

    def active(self) -> List[Credential]:
        return self.list("ACTIVE")

    # ---- enrollment: begin (challenge), finish (a PENDING credential + an approval that a trusted approver signs), activate
    def begin_registration(self, name: str, role: Optional[str] = None, scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        name = " ".join(str(name or "").split())[:60]
        if not name:
            raise PasskeyError("give the device a name (for example: my laptop)")
        scope = clean_scope(scope or {})
        enrollment_id, challenge = secrets.token_hex(12), secrets.token_bytes(32)
        with self._persistence._connect() as conn:
            conn.execute("INSERT INTO passkey_enrollments (enrollment_id, challenge, name, role, scope_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (enrollment_id, b64u(challenge), name, (str(role).strip()[:60] or None) if role else None, json.dumps(scope, sort_keys=True), time.time()))
        user_id = hashlib.sha256(f"delentia-approver:{enrollment_id}".encode("utf-8")).digest()
        return {"enrollment_id": enrollment_id, "options": {
            "rp": {"name": "Delentia", "id": rp_id()}, "user": {"id": b64u(user_id), "name": name, "displayName": name}, "challenge": b64u(challenge),
            "pubKeyCredParams": [{"type": "public-key", "alg": ALG_ES256}, {"type": "public-key", "alg": ALG_RS256}], "timeout": 120000, "attestation": "none",
            "authenticatorSelection": {"residentKey": "preferred", "userVerification": "required"}}}

    def finish_registration(self, enrollment_id: str, credential: Dict[str, Any]) -> Dict[str, Any]:
        """Validates the ceremony and stores the credential as PENDING. Returns what the enrollment approval must carry; the caller creates that pending action."""
        with self._persistence._connect() as conn:
            row = conn.execute("SELECT challenge, name, role, scope_json, created_at, used FROM passkey_enrollments WHERE enrollment_id = ?", (enrollment_id,)).fetchone()
        if row is None or row[5]:
            raise PasskeyError("this enrollment does not exist or was already used; start again")
        if time.time() - float(row[4]) > ENROLLMENT_TTL_SECONDS:
            raise PasskeyError("this enrollment took too long; start again")
        response = credential.get("response") if isinstance(credential, dict) else None
        if not isinstance(response, dict):
            raise PasskeyError("the browser sent no credential")
        client = _client_data(unb64u(response.get("clientDataJSON"), MAX_CLIENT_DATA), "webauthn.create")
        if client.get("challenge") != row[0]:
            raise PasskeyError("the challenge does not match this enrollment")
        attestation, _ = cbor_decode(unb64u(response.get("attestationObject"), MAX_ATTESTATION))
        if not isinstance(attestation, dict) or not isinstance(attestation.get("authData"), bytes):
            raise PasskeyError("the attestation object is malformed")
        auth = parse_auth_data(attestation["authData"], expect_credential=True)
        if auth.rp_id_hash != hashlib.sha256(rp_id().encode("utf-8")).digest():
            raise PasskeyError("the credential was made for another site")
        if not auth.flags & FLAG_UP or not auth.flags & FLAG_UV:
            raise PasskeyError("the device did not confirm the person (user verification is required)")
        public = public_key_from_cose(auth.cose_key or {})
        cid = b64u(auth.credential_id or b"")
        if self.get(cid) is not None:
            raise PasskeyError("this device is already registered")
        key = signer_key(auth.credential_id or b"")
        with self._persistence._connect() as conn:
            conn.execute("UPDATE passkey_enrollments SET used = 1 WHERE enrollment_id = ?", (enrollment_id,))
            conn.execute("INSERT INTO approver_credentials (credential_id, signer_key, public_key_json, sign_count, name, role, scope_json, status, backup_eligible, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)",
                         (cid, key, json.dumps(public, sort_keys=True), auth.sign_count, row[1], row[2], row[3], 1 if auth.flags & FLAG_BE else 0, time.time()))
        return {"credential_id": cid, "signer_key": key, "name": row[1], "role": row[2], "scope": json.loads(row[3]), "public_key_sha256": hashlib.sha256(json.dumps(public, sort_keys=True).encode("utf-8")).hexdigest(),
                "backup_eligible": bool(auth.flags & FLAG_BE)}

    def activate(self, credential_id: str, approval_id: str) -> Credential:
        with self._persistence._connect() as conn:
            done = conn.execute("UPDATE approver_credentials SET status = 'ACTIVE', activated_at = ?, enrollment_approval_id = ? WHERE credential_id = ? AND status = 'PENDING'",
                                (time.time(), approval_id, credential_id)).rowcount
        if done != 1:
            raise PasskeyError("this device is not waiting to be activated")
        cred = self.get(credential_id)
        assert cred is not None
        return cred

    def revoke(self, credential_id: str) -> Credential:
        with self._persistence._connect() as conn:
            done = conn.execute("UPDATE approver_credentials SET status = 'REVOKED', revoked_at = ? WHERE credential_id = ? AND status != 'REVOKED'", (time.time(), credential_id)).rowcount
        cred = self.get(credential_id)
        if cred is None or (done != 1 and cred.status != "REVOKED"):
            raise PasskeyError("no such device")
        return cred

    # ---- assertion
    def request_options(self, action_sha256: str, approval_id: str, decision: str) -> Dict[str, Any]:
        creds = self.active()
        if not creds:
            raise PasskeyError("no approval device is registered yet")
        return {"challenge": b64u(approval_challenge(approval_id, action_sha256, decision)), "rpId": rp_id(), "timeout": 120000, "userVerification": "required",
                "allowCredentials": [{"type": "public-key", "id": c.credential_id} for c in creds]}

    def verify_new(self, approval_id: str, action_sha256: str, decision: str, assertion: Dict[str, Any]) -> Tuple[Credential, str]:
        """Checks a fresh assertion, advances the signature counter and returns (credential, stored_signature) where stored_signature is what `approvals` keeps and re-checks at execution."""
        cid = assertion.get("id") if isinstance(assertion, dict) else None
        cred = self.get(str(cid)) if isinstance(cid, str) else None
        if cred is None or cred.status != "ACTIVE":
            raise PasskeyError("this device is not a trusted approver")
        response = assertion.get("response")
        if not isinstance(response, dict):
            raise PasskeyError("the browser sent no assertion")
        blob = {"credential_id": cred.credential_id, "authenticatorData": str(response.get("authenticatorData") or ""), "clientDataJSON": str(response.get("clientDataJSON") or ""),
                "signature": str(response.get("signature") or "")}
        new_count = _verify_assertion(cred, approval_challenge(approval_id, action_sha256, decision), blob, check_counter=True)
        with self._persistence._connect() as conn:
            conn.execute("UPDATE approver_credentials SET sign_count = ?, last_used_at = ? WHERE credential_id = ?", (new_count, time.time(), cred.credential_id))
        return cred, json.dumps(blob, sort_keys=True).encode("utf-8").hex()

    def verify_stored(self, key: str, approval_id: str, action_sha256: str, decision: str, stored_signature: str) -> Credential:
        """Run again at execution time: the stored assertion must still verify for this exact action, and the device must still be an ACTIVE trusted approver."""
        cred = self.get_by_signer(key)
        if cred is None or cred.status != "ACTIVE":
            raise PasskeyError("the device that approved this is no longer a trusted approver")
        try:
            blob = json.loads(bytes.fromhex(stored_signature).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PasskeyError("the stored approval is damaged") from exc
        if not isinstance(blob, dict) or blob.get("credential_id") != cred.credential_id:
            raise PasskeyError("the stored approval does not belong to this device")
        _verify_assertion(cred, approval_challenge(approval_id, action_sha256, decision), blob, check_counter=False)
        return cred


def approval_challenge(approval_id: str, action_sha256: str, decision: str) -> bytes:
    from rct_control_plane.approvals import approval_message
    return hashlib.sha256(approval_message(approval_id, action_sha256, decision)).digest()


def _verify_assertion(cred: Credential, challenge: bytes, blob: Dict[str, Any], *, check_counter: bool) -> int:
    client_raw = unb64u(blob.get("clientDataJSON"), MAX_CLIENT_DATA)
    client = _client_data(client_raw, "webauthn.get")
    if client.get("challenge") != b64u(challenge):
        raise PasskeyError("the confirmation was for a different action or a different decision")
    auth_raw = unb64u(blob.get("authenticatorData"), MAX_AUTH_DATA)
    auth = parse_auth_data(auth_raw, expect_credential=False)
    if auth.rp_id_hash != hashlib.sha256(rp_id().encode("utf-8")).digest():
        raise PasskeyError("the confirmation was made for another site")
    if not auth.flags & FLAG_UP or not auth.flags & FLAG_UV:
        raise PasskeyError("the device did not confirm the person (user verification is required)")
    signature = unb64u(blob.get("signature"), MAX_SIGNATURE)
    if not verify_signature(cred.public_key, auth_raw + hashlib.sha256(client_raw).digest(), signature):
        raise PasskeyError("the signature does not verify for this device")
    if check_counter and (cred.sign_count or auth.sign_count) and auth.sign_count <= cred.sign_count:
        raise PasskeyError("the device's signature counter did not advance: this confirmation looks replayed or the device was cloned")
    return max(auth.sign_count, cred.sign_count) if check_counter else cred.sign_count


# ---------------------------------------------------------------------------------------------------------------------------------- scope
_SCOPE_KEYS = ("kinds", "namespaces", "workspaces")


def clean_scope(scope: Dict[str, Any]) -> Dict[str, Any]:
    """Which actions this device may approve. Missing or empty = no limit on that dimension. Unknown keys are refused, not ignored."""
    if not isinstance(scope, dict):
        raise PasskeyError("the scope must be an object")
    extra = [k for k in scope if k not in _SCOPE_KEYS]
    if extra:
        raise PasskeyError(f"unknown scope field: {extra[0]}")
    out: Dict[str, Any] = {}
    for key in _SCOPE_KEYS:
        value = scope.get(key)
        if value in (None, [], ""):
            continue
        if not isinstance(value, list) or len(value) > 50 or not all(isinstance(v, str) and 0 < len(v) <= 200 for v in value):
            raise PasskeyError(f"scope.{key} must be a short list of text")
        out[key] = sorted(set(value))
    if "kinds" in out:
        from rct_control_plane import plan_approval
        bad = [k for k in out["kinds"] if k not in plan_approval.KINDS]
        if bad:
            raise PasskeyError(f"scope.kinds: {bad[0]!r} is not a kind of action")
    return out


def check_scope(cred: Credential, action: Any) -> None:
    """Raises PasskeyError when the action is outside what this device may approve."""
    scope = cred.scope or {}
    if scope.get("namespaces") and action.namespace not in scope["namespaces"]:
        raise PasskeyError(f"this device may not approve actions of {action.namespace!r}")
    if scope.get("workspaces") and (action.workspace or "") not in scope["workspaces"]:
        raise PasskeyError("this device may not approve actions in this workspace")
    if scope.get("kinds"):
        from rct_control_plane import plan_approval
        if action.tool_name == plan_approval.PLAN_TOOL:
            kinds = {str(s.get("kind") or "other") for s in ((action.tool_args or {}).get("plan") or {}).get("steps", [])}
        else:
            kinds = {plan_approval.action_kind(action.tool_name, action.tool_args) or "other"}
        outside = sorted(k for k in kinds if k not in scope["kinds"])
        if outside:
            raise PasskeyError(f"this device may not approve the kind of action {outside[0]!r}")


# ---------------------------------------------------------------------------------------------------------------------------------- enrollment as an approval
def create_enrollment_action(approvals_store: Any, info: Dict[str, Any], owner: str = "desk") -> Any:
    """The pending action that a trusted Ed25519 approver signs to let a new device approve things. The arguments carry the credential's public-key hash, so the signature covers THIS device and no other."""
    return approvals_store.create(
        namespace=owner, goal=f"Enroll an approval device: {info['name']}", tool_name=ENROLL_TOOL,
        tool_args={"credential_id": info["credential_id"], "public_key_sha256": info["public_key_sha256"], "name": info["name"], "role": info.get("role"), "scope": info.get("scope") or {},
                   "backup_eligible": bool(info.get("backup_eligible"))},
        reason="a new approval device is trusted only after an existing approver signs for it")


def activate_enrollment(approvals_store: Any, passkey_store: PasskeyStore, approval_id: str) -> Credential:
    """After a trusted approver signed the enrollment: re-verify that signature, check that the device in the database is the one that was signed for, make it ACTIVE, and use the approval up.
    Enrolling a device is a root-of-trust act, so only an Ed25519 approver may sign it: a passkey can not add another passkey."""
    from rct_control_plane.approvals import ApprovalError
    action = approvals_store.get(approval_id)
    if action is None or action.tool_name != ENROLL_TOOL:
        raise PasskeyError("this is not a device enrollment")
    with passkey_store._persistence._connect() as conn:
        signers = [r[0] for r in conn.execute("SELECT public_key FROM pending_action_signatures WHERE approval_id = ?", (approval_id,)).fetchall()]
    if not signers or any(is_passkey_signer(k) for k in signers):
        raise PasskeyError("a device can only be enrolled with the signature of an approver key, not of another device")
    cred = passkey_store.get(str(action.tool_args.get("credential_id")))
    if cred is None or cred.status != "PENDING":
        raise PasskeyError("the device that was signed for is not waiting to be activated")
    if hashlib.sha256(json.dumps(cred.public_key, sort_keys=True).encode("utf-8")).hexdigest() != action.tool_args.get("public_key_sha256"):
        raise PasskeyError("the device in the database is not the one that was signed for")
    try:
        approvals_store.claim_for_execution(approval_id)
    except ApprovalError as exc:
        raise PasskeyError(str(exc)) from exc
    activated = passkey_store.activate(cred.credential_id, approval_id)
    approvals_store.mark_executed(approval_id, {"activated": cred.credential_id[:16], "name": cred.name})
    return activated
