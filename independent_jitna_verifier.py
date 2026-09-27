"""
Independent .jitna verifier — deliberately does NOT import wire_protocol.py
or anything from rct_control_plane. Only uses the standard `cryptography`
library (available in virtually every language as libsodium/Ed25519
bindings) plus stdlib json/hashlib, to prove the .jitna format is genuinely
self-describing and portable: a system that has never seen wire_protocol.py
can still correctly verify a real signed packet.
"""
import hashlib
import json
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def verify_jitna_file(path: str) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        wire = json.load(f)

    public_key_bytes = bytes.fromhex(wire["sender_public_key_hex"])
    real_fingerprint = hashlib.sha256(public_key_bytes).hexdigest()
    if wire["sender_fingerprint"] != real_fingerprint:
        print("FAIL: fingerprint does not match the provided public key")
        return False

    canonical_bytes = json.dumps(wire["packet"], sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    try:
        public_key.verify(bytes.fromhex(wire["signature"]), canonical_bytes)
    except InvalidSignature:
        print("FAIL: signature invalid")
        return False

    print("PASS: signature genuinely verified by an independent verifier")
    print(f"  intent: {wire['packet']['intent']!r}")
    print(f"  sender_fingerprint: {wire['sender_fingerprint'][:16]}...")
    return True


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "demo_intent.jitna"
    print(f"Independently verifying {path} (no wire_protocol.py import)...")
    ok = verify_jitna_file(path)

    print("\n--- Tamper test: flip one character in the intent field ---")
    with open(path, "r", encoding="utf-8") as f:
        tampered = json.load(f)
    tampered["packet"]["intent"] = tampered["packet"]["intent"].replace("production", "PRODUCTION-HACKED")
    with open("demo_intent_tampered.jitna", "w", encoding="utf-8") as f:
        json.dump(tampered, f, indent=2)
    tamper_ok = verify_jitna_file("demo_intent_tampered.jitna")

    assert ok is True, "genuine .jitna file must verify"
    assert tamper_ok is False, "tampered .jitna file must fail verification"
    print("\nALL INDEPENDENT .jitna VERIFICATION ASSERTIONS PASSED")
