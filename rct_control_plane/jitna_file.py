"""
The `.jitna` file: JITNA packets (and the 6-field JITNA language) as a signed file that
can be sent over any network or carried on any medium (Round 52).

Before this module a JITNA packet existed only as an in-memory object or one JSON line
between a parent and its subagent. There was no file format, no way to hand a packet to
another system, and no way for that system to check it with nothing but a public key.

Three things, kept separate on purpose:

1. The JITNA language (layer 2): `I / D / Δ / A / R / M` as plain text,
       I: Refactor the authentication module
       D: 800-line monolith, no tests
       Δ: separate domain logic from infrastructure
   `parse_language` / `format_language`. Intent (`I`) is required: no intent, nothing to send.
2. The packet (layer 1, RFC-001 v2.0, `jitna_protocol.JITNAPacket`) carrying that language in
   `payload["language"]`, signed with Ed25519.
3. The file envelope (this module): `format`, `version`, `created`, the packets, the public
   keys of whoever signed them (`keys`, by fingerprint) and a **seal**, an Ed25519 signature by
   the packing party over the whole body.

Why a seal on top of the packet signatures: `JITNAPacket.compute_hash()` covers source, target,
message type, payload, timestamp and schema version only. `priority`, `correlation_id`,
`metadata` and `status` are outside the hash, so changing them leaves the packet signature
valid. The seal covers every byte of the body, so those fields are protected in a file.

What verification tells you, and what it does not:
- `valid`   every signature checks out and nothing was changed after signing.
- `trusted` every signing key is one the verifier chose to trust (`trusted_keys`). A file whose
            keys the verifier has never seen is `valid` but not `trusted`: anyone can generate a
            key and sign anything. Trust comes from knowing the sender's public key in advance
            (published by them, pinned by you).
It does not say the content is true, and it does not encrypt: a `.jitna` file is readable by
anyone who has it. Do not put secrets in it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from rct_control_plane.jitna_protocol import (
    JITNAMessageType,
    JITNAPacket,
    JITNAValidator,
    sign_packet,
    verify_packet,
)

FORMAT = "jitna-file"
FORMAT_VERSION = 1
EXTENSION = ".jitna"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_PACKETS = 256

LANGUAGE_FIELDS = ("I", "D", "Δ", "A", "R", "M")
_DELTA = "Δ"        # GREEK CAPITAL LETTER DELTA
_INCREMENT = "∆"    # INCREMENT, which many keyboards and fonts produce for the same symbol
_LANGUAGE_NAMES = {
    "I": "I", "INTENT": "I",
    "D": "D", "DATA": "D",
    _DELTA: _DELTA, _INCREMENT: _DELTA, "DELTA": _DELTA,
    "A": "A", "APPROACH": "A",
    "R": "R", "REFLECTION": "R",
    "M": "M", "MEMORY": "M",
}
_KEY_LINE = re.compile(r"^\s*([A-Za-z" + _DELTA + _INCREMENT + r"]{1,12})\s*[:：]\s?(.*)$")


class JitnaFileError(ValueError):
    """The file or language text is malformed (not merely unverifiable)."""


# --------------------------------------------------------------------------
# The 6-field language
# --------------------------------------------------------------------------

def parse_language(text: str) -> Dict[str, str]:
    """Text with `I:`, `D:`, `Δ:`, `A:`, `R:`, `M:` lines (long names and `Delta` accepted,
    case-insensitive; an indented line continues the previous field; `#` starts a comment
    line). Returns {"I": ..., ...} with only the fields given. `I` is required; an unknown
    field name or a repeated field is an error rather than silently dropped."""
    fields: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[:1] in (" ", "\t") and current is not None:
            fields[current].append(raw.strip())
            continue
        match = _KEY_LINE.match(raw)
        if not match:
            raise JitnaFileError(f"line {number}: expected 'I:', 'D:', 'Δ:', 'A:', 'R:' or 'M:', got {raw[:40]!r}")
        name = _LANGUAGE_NAMES.get(match.group(1).upper())
        if name is None:
            raise JitnaFileError(f"line {number}: unknown JITNA field {match.group(1)!r} (use I, D, Δ, A, R, M)")
        if name in fields:
            raise JitnaFileError(f"line {number}: field {name} given twice")
        fields[name] = [match.group(2).strip()]
        current = name
    language = {k: "\n".join(part for part in v if part != "").strip() for k, v in fields.items()}
    language = {k: v for k, v in language.items() if v}
    if "I" not in language:
        raise JitnaFileError("the JITNA language needs an Intent (I:); with no intent there is nothing to send")
    return language


def format_language(language: Dict[str, Any]) -> str:
    """The inverse of parse_language, in the canonical order I, D, Δ, A, R, M."""
    unknown = [k for k in language if k not in LANGUAGE_FIELDS]
    if unknown:
        raise JitnaFileError(f"unknown JITNA field(s): {unknown}")
    lines: List[str] = []
    for key in LANGUAGE_FIELDS:
        value = language.get(key)
        if value is None or str(value).strip() == "":
            continue
        first, *rest = str(value).strip().split("\n")
        lines.append(f"{key}: {first}")
        lines.extend(f"  {line}" for line in rest)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def generate_key_file(path: str) -> str:
    """Creates an Ed25519 key for signing .jitna files, outside the repository, mode 0600,
    never overwriting. Returns the public key hex (publish it; receivers pin it)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
    target = Path(path).expanduser()
    try:
        inside = target.resolve().is_relative_to(_repo_root())
    except (OSError, ValueError):
        inside = False
    if inside:
        raise JitnaFileError(f"refusing to store a signing key inside the repository ({_repo_root()})")
    if target.exists():
        raise JitnaFileError(f"{target} already exists; refusing to overwrite a key")
    key = Ed25519PrivateKey.generate()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return public_hex(key)


def load_key_file(path: str) -> Any:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    try:
        loaded = load_pem_private_key(Path(path).expanduser().read_bytes(), password=None)
    except (OSError, ValueError) as exc:
        raise JitnaFileError(f"cannot read signing key {path}: {exc}") from exc
    if not isinstance(loaded, Ed25519PrivateKey):
        raise JitnaFileError("the signing key must be an Ed25519 private key")
    return loaded


def public_hex(private_key: Any) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def fingerprint_of(public_key_hex: str) -> str:
    """Full SHA-256 of the raw public key: the same value JITNA packets carry as
    metadata['sender_fingerprint']."""
    return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()


class _Keypair:
    """Adapter so a loaded cryptography key can sign through jitna_protocol.sign_packet."""

    def __init__(self, private_key: Any) -> None:
        self._private_key = private_key

    def fingerprint(self) -> str:
        return fingerprint_of(public_hex(self._private_key))


# --------------------------------------------------------------------------
# Packing
# --------------------------------------------------------------------------

def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _body(envelope: Dict[str, Any]) -> Dict[str, Any]:
    return {k: envelope.get(k) for k in ("format", "version", "created", "sender", "keys", "packets")}


def make_packet(language: Dict[str, str], source: str, target: str, private_key: Any,
                message_type: str = JITNAMessageType.INTENT_REQUEST.value, correlation_id: Optional[str] = None,
                priority: int = 3, extra_payload: Optional[Dict[str, Any]] = None) -> JITNAPacket:
    """A signed packet whose payload carries the language (and anything in extra_payload)."""
    if "I" not in language or not str(language["I"]).strip():
        raise JitnaFileError("a JITNA packet needs an Intent (I)")
    packet = JITNAPacket(source_agent_id=source, target_agent_id=target, message_type=message_type,
                         payload={"language": dict(language), **(extra_payload or {})},
                         correlation_id=correlation_id, priority=priority)
    result = JITNAValidator().validate(packet)
    if not result.is_valid:
        raise JitnaFileError("; ".join(result.errors))
    return sign_packet(packet, _Keypair(private_key))  # type: ignore[arg-type]


def pack(packets: Sequence[JITNAPacket], private_key: Any, extra_keys: Optional[Dict[str, str]] = None,
         created: Optional[str] = None) -> Dict[str, Any]:
    """The file body for `packets`, sealed with `private_key`. `extra_keys` maps the public
    key hex of any other party whose signed packets are included (a request and its
    response, say) so the receiver can check them too."""
    if not packets:
        raise JitnaFileError("nothing to pack")
    if len(packets) > MAX_PACKETS:
        raise JitnaFileError(f"at most {MAX_PACKETS} packets per file")
    sender_hex = public_hex(private_key)
    keys = {fingerprint_of(sender_hex): sender_hex}
    for hex_key in (extra_keys or {}).values():
        keys[fingerprint_of(hex_key)] = hex_key
    envelope: Dict[str, Any] = {
        "format": FORMAT, "version": FORMAT_VERSION,
        "created": created or datetime.now(timezone.utc).isoformat(),
        "sender": {"public_key": sender_hex, "fingerprint": fingerprint_of(sender_hex)},
        "keys": keys,
        "packets": [p.to_dict() for p in packets],
    }
    envelope["seal"] = private_key.sign(hashlib.sha256(_canonical(_body(envelope))).digest()).hex()
    return envelope


def pack_language(language: Dict[str, str], source: str, target: str, private_key: Any, **kwargs: Any) -> Dict[str, Any]:
    return pack([make_packet(language, source, target, private_key, **kwargs)], private_key)


def dumps(envelope: Dict[str, Any]) -> str:
    return json.dumps(envelope, indent=2, ensure_ascii=False, default=str) + "\n"


def write_file(envelope: Dict[str, Any], path: str) -> Path:
    target = Path(path).expanduser()
    if target.suffix != EXTENSION:
        raise JitnaFileError(f"a JITNA file must end in {EXTENSION}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps(envelope), encoding="utf-8")
    return target


# --------------------------------------------------------------------------
# Reading and verifying
# --------------------------------------------------------------------------

def loads(text: str) -> Dict[str, Any]:
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise JitnaFileError(f"file is larger than {MAX_FILE_BYTES} bytes")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JitnaFileError(f"not a JITNA file (invalid JSON: {exc.msg})") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise JitnaFileError("not a JITNA file (missing format marker)")
    if data.get("version") != FORMAT_VERSION:
        raise JitnaFileError(f"unsupported JITNA file version {data.get('version')!r} (this reader knows {FORMAT_VERSION})")
    packets = data.get("packets")
    if not isinstance(packets, list) or not packets or len(packets) > MAX_PACKETS:
        raise JitnaFileError(f"'packets' must be a list of 1 to {MAX_PACKETS}")
    if not isinstance(data.get("sender"), dict) or not isinstance(data.get("keys"), dict) or not isinstance(data.get("seal"), str):
        raise JitnaFileError("the file lacks sender, keys or seal")
    return data


def read_file(path: str) -> Dict[str, Any]:
    p = Path(path).expanduser()
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            raise JitnaFileError(f"file is larger than {MAX_FILE_BYTES} bytes")
        return loads(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise JitnaFileError(f"cannot read {path}: {exc}") from exc


@dataclass
class PacketReport:
    packet_id: str
    source: str
    target: str
    message_type: str
    signature_valid: bool
    signer: Optional[str]          # fingerprint, when the packet names one
    language: Optional[Dict[str, str]]
    problems: List[str] = field(default_factory=list)


@dataclass
class VerifyReport:
    valid: bool
    trusted: bool
    sender_fingerprint: str
    created: Optional[str]
    packets: List[PacketReport]
    problems: List[str]
    untrusted_keys: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid, "trusted": self.trusted, "sender_fingerprint": self.sender_fingerprint,
            "created": self.created, "problems": self.problems, "untrusted_keys": self.untrusted_keys,
            "packets": [vars(p) for p in self.packets],
        }


def _norm_keys(trusted_keys: Optional[Iterable[str]]) -> set:
    return {k.strip().lower() for k in (trusted_keys or []) if k and k.strip()}


def verify(envelope: Dict[str, Any], trusted_keys: Optional[Iterable[str]] = None) -> VerifyReport:
    """Checks the seal, then every packet: its signature against the key named by its
    sender_fingerprint, that the key is the one the file declares for that fingerprint,
    and the packet's own schema. `trusted_keys` are public key hex strings (or their
    fingerprints) the verifier already trusts."""
    problems: List[str] = []
    trusted = _norm_keys(trusted_keys)
    sender = envelope.get("sender") or {}
    sender_hex = str(sender.get("public_key", ""))
    keys: Dict[str, str] = {str(k): str(v) for k, v in (envelope.get("keys") or {}).items()}

    sender_fp = ""
    try:
        sender_fp = fingerprint_of(sender_hex)
    except ValueError:
        problems.append("sender public key is not valid hex")
    if sender_fp and sender.get("fingerprint") != sender_fp:
        problems.append("sender fingerprint does not match the sender public key")

    for fp, hex_key in keys.items():
        try:
            if fingerprint_of(hex_key) != fp:
                problems.append(f"key listed under {fp[:12]}… is not the key with that fingerprint")
        except ValueError:
            problems.append(f"key listed under {fp[:12]}… is not valid hex")

    # the seal
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(sender_hex)).verify(
            bytes.fromhex(str(envelope.get("seal", ""))), hashlib.sha256(_canonical(_body(envelope))).digest())
    except (InvalidSignature, ValueError):
        problems.append("the seal does not verify: the file was changed after it was sealed, or was sealed by another key")

    reports: List[PacketReport] = []
    used: set = set()
    validator = JITNAValidator()
    for raw in envelope.get("packets") or []:
        entry_problems: List[str] = []
        try:
            packet = JITNAPacket(**raw)
        except TypeError as exc:
            reports.append(PacketReport("?", "?", "?", "?", False, None, None, [f"malformed packet: {exc}"]))
            problems.append("a packet is malformed")
            continue
        checked = validator.validate(packet)
        entry_problems.extend(checked.errors)
        signer_fp = str(packet.metadata.get("sender_fingerprint") or "") or None
        signature_ok = False
        if not packet.signature or not signer_fp:
            entry_problems.append("the packet is not signed")
        elif signer_fp not in keys:
            entry_problems.append(f"the file does not carry the key of signer {signer_fp[:12]}…")
        else:
            used.add(signer_fp)
            try:
                signature_ok = verify_packet(packet, bytes.fromhex(keys[signer_fp]))
            except ValueError:
                signature_ok = False
            if not signature_ok:
                entry_problems.append("the packet signature does not verify")
        language = packet.payload.get("language") if isinstance(packet.payload, dict) else None
        reports.append(PacketReport(packet.packet_id, packet.source_agent_id, packet.target_agent_id, packet.message_type,
                                    signature_ok, signer_fp, language if isinstance(language, dict) else None, entry_problems))
        problems.extend(f"packet {packet.packet_id[:8]}: {p}" for p in entry_problems)

    signer_keys = used | ({sender_fp} if sender_fp else set())
    untrusted = sorted(fp for fp in signer_keys if fp.lower() not in trusted and keys.get(fp, "").lower() not in trusted
                       and (fp != sender_fp or sender_hex.lower() not in trusted))
    return VerifyReport(valid=not problems, trusted=not problems and bool(trusted) and not untrusted,
                        sender_fingerprint=sender_fp, created=envelope.get("created"), packets=reports,
                        problems=problems, untrusted_keys=untrusted)


def languages(envelope: Dict[str, Any]) -> List[Tuple[str, Dict[str, str]]]:
    """(packet_id, language) for every packet that carries one. Does not verify; call
    verify() first and only act on what it accepts."""
    out: List[Tuple[str, Dict[str, str]]] = []
    for raw in envelope.get("packets") or []:
        payload = raw.get("payload") if isinstance(raw, dict) else None
        language = payload.get("language") if isinstance(payload, dict) else None
        if isinstance(language, dict):
            out.append((str(raw.get("packet_id")), {k: str(v) for k, v in language.items() if k in LANGUAGE_FIELDS}))
    return out
