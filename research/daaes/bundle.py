"""
The evidence bundle of one run (specification section XI) and its seal.

    results/{date}/{case_id}/{arm}/{seed}/
        manifest.json  run_manifest.json  fixture.sha256  events.jsonl  operation_receipts.jsonl  checkpoints/  agent_result.json  oracle_result.json  score.json  replay_report.json  environment.json  SEAL.json

`seal` hashes every file and the manifest of hashes; with a key kept OUTSIDE the results folder it also signs that hash (Ed25519), so a later reader can tell a rewritten bundle from the one the run
produced. `verify_bundle` is stdlib-plus-cryptography and imports nothing from Delentia: it re-hashes, checks the event chain, checks the seal, and applies the specification's validity rule:

    a run result is INVALID if the oracle, the hidden tests or the fixture were altered, or if observability is too thin to tell failure from success.

Concretely a bundle is invalid when: a file listed in the seal is missing or changed; the event log does not verify; there is no `oracle.evaluated` event; the score file does not match the oracle result;
or the fixture hash recorded in the manifest is not the one in fixture.sha256.
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from research.daaes import events as ev
from research.daaes import run_manifest
from research.daaes.core import canonical, sha256_file

ROOT = Path(__file__).resolve().parents[2]


def git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, timeout=20).stdout.strip() or None
    except Exception:                                               # noqa: BLE001
        return None


def environment() -> Dict[str, Any]:
    return {"python": platform.python_version(), "platform": platform.platform(), "commit": git_commit(), "argv": sys.argv[1:], "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str), encoding="utf-8")


def write_bundle(folder: Path, *, case_id: str, arm: str, seed: int, fixture_sha256: str, events_path: Optional[Path], agent_result: Dict[str, Any], oracle_result: Dict[str, Any],
                 score: Dict[str, Any], replay_report: Optional[Dict[str, Any]] = None, receipts: Optional[List[Dict[str, Any]]] = None, checkpoints: Optional[Dict[str, Any]] = None,
                 extra_manifest: Optional[Dict[str, Any]] = None, run_manifest_data: Optional[Dict[str, Any]] = None) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "fixture.sha256").write_text(fixture_sha256 + "\n", encoding="utf-8")
    if events_path is not None and Path(events_path).exists():
        (folder / "events.jsonl").write_bytes(Path(events_path).read_bytes())
    else:
        (folder / "events.jsonl").write_bytes(b"")
    with open(folder / "operation_receipts.jsonl", "w", encoding="utf-8") as f:
        for r in receipts or []:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
    for name, obj in (checkpoints or {}).items():
        write_json(folder / "checkpoints" / f"{name}.json", obj)
    write_json(folder / "agent_result.json", agent_result)
    write_json(folder / "oracle_result.json", oracle_result)
    write_json(folder / "score.json", score)
    write_json(folder / "replay_report.json", replay_report or {"mode": "not_evaluated"})
    write_json(folder / "environment.json", environment())
    if run_manifest_data is not None:                              # the twelve experiment controls (run_manifest.py); a bundle without them is invalid when verified
        write_json(folder / "run_manifest.json", run_manifest_data)
    write_json(folder / "manifest.json", {"case_id": case_id, "arm": arm, "seed": seed, "fixture_sha256": fixture_sha256, "oracle_score": score.get("score"), "passed": score.get("passed"),
                                          "hard_failures": score.get("hard_failures"), **(extra_manifest or {})})
    return folder


def seal(folder: Path, key_path: Optional[Path] = None) -> Dict[str, Any]:
    folder = Path(folder)
    files = {str(p.relative_to(folder)).replace("\\", "/"): sha256_file(p) for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "SEAL.json"}
    record: Dict[str, Any] = {"files": files, "bundle_sha256": __import__("hashlib").sha256(canonical(files)).hexdigest(), "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if key_path is not None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key_path = Path(key_path)
        if key_path.exists():
            private = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        else:
            private = Ed25519PrivateKey.generate()
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        record["signature"] = private.sign(bytes.fromhex(record["bundle_sha256"])).hex()                      # type: ignore[union-attr]
        record["public_key"] = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()      # type: ignore[union-attr]
    write_json(folder / "SEAL.json", record)
    return record


def verify_bundle(folder: Path, expected_public_key: Optional[str] = None) -> Dict[str, Any]:
    folder = Path(folder)
    problems: List[str] = []
    try:
        record = json.loads((folder / "SEAL.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"valid": False, "problems": ["no readable SEAL.json: the bundle was never sealed"]}
    for rel, expected in record["files"].items():
        got = sha256_file(folder / rel)
        if got is None:
            problems.append(f"missing: {rel}")
        elif got != expected:
            problems.append(f"changed after sealing: {rel}")
    present = {str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*") if p.is_file() and p.name != "SEAL.json"}
    for extra in sorted(present - set(record["files"])):
        problems.append(f"not in the seal: {extra}")
    if __import__("hashlib").sha256(canonical(record["files"])).hexdigest() != record["bundle_sha256"]:
        problems.append("the seal's own hash does not match its file list")
    if "signature" in record:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(record["public_key"])).verify(bytes.fromhex(record["signature"]), bytes.fromhex(record["bundle_sha256"]))
        except (InvalidSignature, ValueError):
            problems.append("the seal's signature does not verify")
        if expected_public_key and record["public_key"] != expected_public_key:
            problems.append("the seal was signed by a different key than the one expected")
    elif expected_public_key:
        problems.append("a signature was expected and the seal has none")
    # the validity rule of the specification
    events = ev.load(folder / "events.jsonl") if (folder / "events.jsonl").exists() else []
    chain = ev.verify(events) if events else {"ok": False, "reason": "no events"}
    if not chain["ok"]:
        problems.append(f"observability: the event log is {'empty' if not events else 'damaged'} ({chain.get('reason')})")
    elif not any(e["kind"] == "oracle.evaluated" for e in events):
        problems.append("observability: the event log has no oracle.evaluated event")
    try:
        controls = json.loads((folder / "run_manifest.json").read_text(encoding="utf-8"))
        problems.extend(run_manifest.validate(controls))
    except (OSError, ValueError):
        controls = None
        problems.append("run manifest: run_manifest.json is missing or unreadable (the experiment conditions are not written down)")
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if controls and (controls.get("fixture_hash") != manifest.get("fixture_sha256") or controls.get("seed") != manifest.get("seed")):
            problems.append("run manifest: its fixture hash or seed differs from manifest.json")
        if (folder / "fixture.sha256").read_text(encoding="utf-8").strip() != manifest.get("fixture_sha256"):
            problems.append("the fixture hash in the manifest is not the one recorded in fixture.sha256")
        score = json.loads((folder / "score.json").read_text(encoding="utf-8"))
        oracle = json.loads((folder / "oracle_result.json").read_text(encoding="utf-8"))
        if score.get("score") != oracle.get("score") or score.get("passed") != oracle.get("passed"):
            problems.append("score.json does not match oracle_result.json")
    except (OSError, ValueError):
        problems.append("manifest, score or oracle result unreadable")
    return {"valid": not problems, "problems": problems, "files": len(record["files"]), "bundle_sha256": record.get("bundle_sha256")}
