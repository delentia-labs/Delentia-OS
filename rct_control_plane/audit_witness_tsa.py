"""
Round 91: an RFC 3161 time-stamping authority as an audit witness.

The signed anchor message (`audit_chain.anchor_message`) is hashed with SHA-256 and sent to a public time-stamping authority (DigiCert, Sectigo, FreeTSA, ...). The authority
returns a token that says, under its own signature, "this digest existed at this time". Only a hash leaves the host. The host cannot forge or back-date the token, a rewritten
chain no longer hashes to what the token covers, and anyone can check a token with `openssl ts -verify`. A token proves WHEN, never what the content means, and the tokens are the
proof, so the folder that holds them should also be copied somewhere the host cannot delete (the git witness is a good place).

Configured like the other witnesses (DELENTIA_AUDIT_WITNESSES):

    {"type": "rfc3161", "name": "tsa", "url": "http://timestamp.digicert.com", "path": "~/.delentia/timestamps", "key_id": "host-1", "ca_file": ""}

`ca_file` is the CA bundle a token must chain to; the default is certifi's, which verifies the DigiCert and Sectigo tokens (measured 2026-10-19). FreeTSA's own CA is not in it:
download https://freetsa.org/files/cacert.pem and name it. Without `openssl` on the machine a token is READ (status, digest, time) but its signature is not checked, and
`fetch()` says how many tokens were left unchecked.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from rct_control_plane import audit_chain
from rct_control_plane.audit_witness import WitnessError, WitnessSpec

_SHA256_OID = bytes.fromhex("0609608648016503040201")      # DER of OID 2.16.840.1.101.3.4.2.1
TSA_MAX_BYTES = 200_000


class TsaError(WitnessError):
    pass


def _der(tag: int, body: bytes) -> bytes:
    n = len(body)
    head = bytes([n]) if n < 0x80 else (bytes([0x81, n]) if n < 0x100 else bytes([0x82, n >> 8, n & 0xFF]))
    return bytes([tag]) + head + body


def timestamp_query(digest: bytes, nonce: int) -> bytes:
    """A DER TimeStampReq (RFC 3161 section 2.4.1) for a SHA-256 digest, asking the authority to include its certificate."""
    if len(digest) != 32:
        raise ValueError("a SHA-256 digest is 32 bytes")
    imprint = _der(0x30, _der(0x30, _SHA256_OID + b"\x05\x00") + _der(0x04, digest))
    nonce_bytes = nonce.to_bytes((nonce.bit_length() + 8) // 8, "big")
    return _der(0x30, b"\x02\x01\x01" + imprint + _der(0x02, nonce_bytes) + b"\x01\x01\xff")


def _tlv(buf: bytes, pos: int) -> "tuple[int, int, int]":
    """(tag, start of content, end of content) of the element at pos; ValueError on anything that does not fit the data."""
    if pos + 2 > len(buf):
        raise ValueError("truncated")
    tag, first = buf[pos], buf[pos + 1]
    start = pos + 2
    if first < 0x80:
        length = first
    else:
        count = first & 0x7F
        if count == 0 or count > 3 or start + count > len(buf):
            raise ValueError("unsupported length")
        length = int.from_bytes(buf[start:start + count], "big")
        start += count
    if start + length > len(buf):
        raise ValueError("length beyond the data")
    return tag, start, start + length


def _children(buf: bytes, start: int, end: int) -> "List[tuple[int, int, int]]":
    out: List["tuple[int, int, int]"] = []
    pos = start
    while pos < end:
        tag, s, e = _tlv(buf, pos)
        out.append((tag, s, e))
        pos = e
    return out


def parse_timestamp_response(raw: bytes) -> Dict[str, Any]:
    """What a verifier needs from a TimeStampResp, read from the DER without a library: the PKI status, the digest the token covers, the time the authority attests and the nonce
    it echoed. It does NOT check the signature (that is `openssl ts -verify`); it only reads. ValueError / IndexError on anything malformed."""
    if len(raw) > TSA_MAX_BYTES:
        raise ValueError("the response is larger than any time-stamp token should be")
    _t, s, e = _tlv(raw, 0)
    top = _children(raw, s, e)
    status_info = _children(raw, top[0][1], top[0][2])
    status = int.from_bytes(raw[status_info[0][1]:status_info[0][2]], "big")
    out: Dict[str, Any] = {"status": status, "granted": status in (0, 1)}
    if not out["granted"] or len(top) < 2:
        return out
    content_info = _children(raw, top[1][1], top[1][2])                    # OID, [0] EXPLICIT SignedData
    signed_seq = _children(raw, content_info[1][1], content_info[1][2])[0]  # SignedData SEQUENCE
    parts = _children(raw, signed_seq[1], signed_seq[2])                    # version, digestAlgorithms, encapContentInfo, ...
    encap = _children(raw, parts[2][1], parts[2][2])                        # eContentType OID, [0] EXPLICIT OCTET STRING
    octet = _children(raw, encap[1][1], encap[1][2])[0]
    _tt, ts, te = _tlv(raw, octet[1])                                       # the TSTInfo SEQUENCE sits inside the octet string
    elems = _children(raw, ts, te)                                          # version, policy, messageImprint, serialNumber, genTime, accuracy?, ordering?, nonce?, ...
    imprint = _children(raw, elems[2][1], elems[2][2])
    out["digest"] = raw[imprint[1][1]:imprint[1][2]].hex()
    out["gen_time"] = raw[elems[4][1]:elems[4][2]].decode("ascii", "replace")
    out["nonce"] = None
    for tag, s2, e2 in elems[5:]:
        if tag == 0x02:
            out["nonce"] = int.from_bytes(raw[s2:e2], "big")
    return out


def _default_ca_file() -> str:
    try:
        import certifi
        return str(certifi.where())
    except Exception:                                               # noqa: BLE001
        return ""


class TimestampWitness:
    def __init__(self, spec: WitnessSpec):
        self.spec = spec
        self.dir = Path(spec.path).expanduser() / re.sub(r"[^A-Za-z0-9_.-]", "_", spec.key_id)

    @staticmethod
    def _digest(body: Dict[str, Any]) -> bytes:
        message = audit_chain.anchor_message(body["key_id"], int(body["entries"]), body["head"], body["signed_at"])
        return hashlib.sha256(message.encode("utf-8")).digest()

    def _stored(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if self.dir.is_dir():
            for f in self.dir.glob("*.json"):
                try:
                    rows.append(json.loads(f.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue
        return sorted(rows, key=lambda r: int(r.get("entries", 0)))

    def publish(self, body: Dict[str, Any]) -> Dict[str, Any]:
        import httpx
        stored = self._stored()
        for row in stored:
            if int(row["entries"]) == int(body["entries"]):
                if row["head"] != body["head"]:
                    raise TsaError(f"fork refused: entry {body['entries']} was already time-stamped with a different head")
                return {"entries": body["entries"], "note": "already time-stamped"}
        if stored and int(body["entries"]) < int(stored[-1]["entries"]):
            raise TsaError(f"rollback refused: the chain is at {body['entries']} but entry {stored[-1]['entries']} was already time-stamped")
        digest = self._digest(body)
        nonce = secrets.randbits(63)
        try:
            resp = httpx.post(self.spec.url, content=timestamp_query(digest, nonce), headers={"Content-Type": "application/timestamp-query"}, timeout=25.0, follow_redirects=False)
        except Exception as exc:                                    # noqa: BLE001
            raise TsaError(f"unreachable ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise TsaError(f"the authority answered {resp.status_code}")
        try:
            parsed = parse_timestamp_response(resp.content)
        except (ValueError, IndexError) as exc:
            raise TsaError(f"unreadable response ({exc})") from exc
        if not parsed["granted"]:
            raise TsaError(f"the authority refused (status {parsed['status']})")
        if parsed["digest"] != digest.hex() or parsed.get("nonce") != nonce:
            raise TsaError("the authority answered for a different digest or nonce")
        self.dir.mkdir(parents=True, exist_ok=True)
        record = {"entries": int(body["entries"]), "head": body["head"], "key_id": body["key_id"], "signed_at": body["signed_at"], "signature": body.get("signature", ""),
                  "digest": digest.hex(), "gen_time": parsed["gen_time"], "authority": self.spec.url, "tsr_b64": base64.b64encode(resp.content).decode("ascii")}
        tmp = self.dir / f"{int(body['entries'])}.json.tmp"
        tmp.write_text(json.dumps(record, sort_keys=True, indent=1), encoding="utf-8")
        tmp.replace(self.dir / f"{int(body['entries'])}.json")
        return {"entries": body["entries"], "note": f"time-stamped {parsed['gen_time']}"}

    def _verify_signature(self, tsr: bytes, digest_hex: str) -> Optional[bool]:
        """True/False from `openssl ts -verify`; None when openssl or a CA bundle is missing (the token is then read, not checked)."""
        exe = shutil.which("openssl")
        ca = self.spec.ca_file or _default_ca_file()
        if exe is None or not ca:
            return None
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "t.tsr"
            f.write_bytes(tsr)
            try:
                done = subprocess.run([exe, "ts", "-verify", "-in", str(f), "-digest", digest_hex, "-CAfile", ca], capture_output=True, text=True, timeout=30,
                                      encoding="utf-8", errors="replace")
            except (OSError, subprocess.TimeoutExpired):
                return None
        return done.returncode == 0 and "Verification: OK" in (done.stdout + done.stderr)

    def fetch(self) -> Dict[str, Any]:
        anchors: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []
        unchecked = 0
        for row in self._stored():
            n = row.get("entries")
            try:
                raw = base64.b64decode(row["tsr_b64"])
                parsed = parse_timestamp_response(raw)
                want = self._digest(row).hex()
            except Exception:                                       # noqa: BLE001
                conflicts.append({"reason": f"time-stamp token {n} cannot be read"})
                continue
            if not parsed["granted"] or parsed["digest"] != want:
                conflicts.append({"reason": f"time-stamp token {n} does not cover the anchor it is filed under"})
                continue
            verdict = self._verify_signature(raw, want)
            if verdict is False:
                conflicts.append({"reason": f"time-stamp token {n} has no valid signature from a trusted authority"})
                continue
            if verdict is None:
                unchecked += 1
            anchors.append({"key_id": row["key_id"], "entries": int(row["entries"]), "head": row["head"], "signed_at": row["signed_at"], "signature": row.get("signature", ""),
                            "received_at": parsed["gen_time"]})
        return {"anchors": anchors, "conflicts": conflicts, "unchecked_signatures": unchecked}
