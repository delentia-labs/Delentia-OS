"""
Verify a Delentia audit bundle WITHOUT the database and WITHOUT any Delentia code. Needs only Python 3 and the `cryptography` package.

    python verify_audit_bundle.py bundle.json [--pubkey <hex>] [--json]

The bundle comes from `delentia audit-chain export-proof`. This file is deliberately self-contained (copy it to the auditor's machine): it re-computes every row's hash from the
recorded fields, checks that each row points at the one before it, checks every Ed25519 signature with the signer's public key, and checks every witness anchor in the bundle:
its own signature and that the row it names really has the head it claims. Pass --pubkey to demand a particular signer (the one published out of band), otherwise the key in the
bundle is used and the report says so: a bundle cannot vouch for its own key.

What a pass means, exactly: the rows listed are internally consistent, were signed by the stated key, and (when anchors are present) agree with what the witnesses were given.
What it does not mean: that the host did not choose NOT to record something in the first place, or that the key was not misused by someone who held it.

Exit code 0 only when nothing is wrong. Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PREFIX = "delentia-audit-anchor:v1"


def row_hash(prev_hash: str, audit_id: int, entity_type: Any, entity_id: Any, action: Any, actor: Any, changes_json: Any, created_at: Any) -> str:
    canonical = json.dumps([prev_hash, audit_id, entity_type, entity_id, action, actor, changes_json, created_at], separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint(public_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(public_hex)).hexdigest()[:16]


def verify(bundle: Dict[str, Any], pubkey: Optional[str] = None) -> Dict[str, Any]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    problems: List[str] = []
    notes: List[str] = []
    if bundle.get("format") != "delentia-audit-bundle:v1":
        return {"ok": False, "problems": ["not a delentia-audit-bundle:v1 file"], "notes": [], "rows_checked": 0}
    bundle_key = (bundle.get("signer_public_key") or "").strip().lower() or None
    wanted = (pubkey or "").strip().lower() or None
    if wanted and bundle_key and wanted != bundle_key:
        problems.append("the bundle names a different signer key than the one you asked for")
    public = wanted or bundle_key
    verifier = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)) if public else None
    if verifier is None:
        notes.append("no public key: signatures were NOT checked")
    elif not wanted:
        notes.append("signatures were checked against the key INSIDE the bundle; pass --pubkey with the key published out of band to rule out a swapped key")
    rows = bundle.get("rows") or []
    content = bool(bundle.get("content_included"))
    genesis = bundle.get("genesis_hash") or "0" * 64
    by_seq: Dict[int, str] = {}
    prev: Optional[str] = None
    signed = 0
    for index, row in enumerate(rows):
        seq = row.get("seq")
        if prev is None:
            expected_prev = genesis if seq == 1 else row.get("prev_hash")
            if seq != 1:
                notes.append(f"the bundle starts at row {seq}: what came before it is not covered, the link into row {seq} is taken as given")
        else:
            expected_prev = prev
            if row.get("seq") != rows[index - 1].get("seq") + 1:
                problems.append(f"row {seq}: not the row after {rows[index - 1].get('seq')} (a row is missing from the bundle)")
        if row.get("prev_hash") != expected_prev:
            problems.append(f"row {seq}: prev_hash does not match the previous row")
        if content:
            recomputed = row_hash(row["prev_hash"], row["audit_id"], row["entity_type"], row["entity_id"], row["action"], row["actor"], row["changes"], row["created_at"])
            if recomputed != row.get("row_hash"):
                problems.append(f"row {seq}: its recorded content does not hash to its row_hash (the content was changed)")
        sig = row.get("signature_hex")
        if sig:
            signed += 1
            if verifier is not None:
                try:
                    verifier.verify(bytes.fromhex(sig), bytes.fromhex(row["row_hash"]))
                except Exception:                                    # noqa: BLE001
                    problems.append(f"row {seq}: the signature does not verify")
                if public and row.get("signer_fingerprint") not in (None, fingerprint(public)):
                    problems.append(f"row {seq}: signed by a different key ({row.get('signer_fingerprint')})")
        elif verifier is not None:
            problems.append(f"row {seq}: unsigned although a signer key is in play")
        by_seq[int(seq)] = row["row_hash"]
        prev = row["row_hash"]
    head = bundle.get("head") or {}
    if rows and (head.get("seq") != rows[-1].get("seq") or head.get("row_hash") != rows[-1].get("row_hash")):
        if int(bundle.get("to_seq", 0)) == int(head.get("seq", -1)):
            problems.append("the bundle's head does not match its last row")
        else:
            notes.append("the bundle stops before the chain's head (a partial export)")
    if not content:
        notes.append("content was not included: links and signatures were checked, but the recorded events themselves were not bound to the hashes")
    anchors_checked = 0
    for witness in bundle.get("witnesses") or []:
        for anchor in witness.get("anchors") or []:
            anchors_checked += 1
            label = f"anchor at {witness.get('name', '?')} (entries {anchor.get('entries')})"
            if verifier is not None and anchor.get("signature"):
                try:
                    message = f"{PREFIX}|{anchor['key_id']}|{int(anchor['entries'])}|{anchor['head']}|{anchor['signed_at']}"
                    verifier.verify(bytes.fromhex(anchor["signature"]), message.encode("utf-8"))
                except Exception:                                    # noqa: BLE001
                    problems.append(f"{label}: its signature does not verify")
            seq = int(anchor["entries"])
            if seq in by_seq and by_seq[seq] != anchor["head"]:
                problems.append(f"{label}: the witness holds head {anchor['head'][:12]}... but row {seq} in the bundle hashes to {by_seq[seq][:12]}... (the log was rewritten after it was anchored)")
            elif seq not in by_seq:
                notes.append(f"{label}: row {seq} is outside this bundle, so it could not be compared")
    return {"ok": not problems, "problems": problems, "notes": notes, "rows_checked": len(rows), "rows_signed": signed, "anchors_checked": anchors_checked,
            "signer": public, "key_source": "argument" if wanted else "bundle"}


def git_ledger(source: str, branch: str = "main", key_id: str = "", pin: str = "") -> Dict[str, Any]:
    """Round 82 (plan item T01): read a git witness's ledger from ANOTHER machine, in full, and report everything an ordinary commit took out of it.

    The ledger is cloned fresh into a temporary folder (so nothing on the audited host is trusted), with its whole history. A ledger may only grow: a removed or changed line,
    a deleted or renamed file anywhere under anchors/ is a problem, and so is a pinned commit (written down earlier, out of band) that is no longer an ancestor of the branch (a
    force-push or a reset). Every anchor ever added to anchors/<key_id>.jsonl is returned so the bundle's rows can be compared with ALL of them, not only the newest.
    """
    import re
    import subprocess
    import tempfile
    problems: List[str] = []
    notes: List[str] = []
    anchors: List[Dict[str, Any]] = []
    if pin and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pin):
        return {"anchors": [], "problems": ["--pin must be a full commit hash"], "notes": []}
    with tempfile.TemporaryDirectory(prefix="delentia-ledger-") as tmp:
        def git(*args: str, check: bool = True) -> "subprocess.CompletedProcess[str]":
            done = subprocess.run(["git", "-C", tmp, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            if check and done.returncode != 0:
                raise RuntimeError((done.stderr or done.stdout).strip()[:200])
            return done
        try:
            subprocess.run(["git", "clone", "--quiet", "--no-tags", "--branch", branch, source, tmp], capture_output=True, text=True, timeout=300, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            return {"anchors": [], "problems": [f"the git ledger could not be read ({str(detail).strip()[:160]}): nothing was verified against it"], "notes": []}
        if git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            return {"anchors": [], "problems": ["the ledger copy is shallow: its history cannot be checked"], "notes": []}
        tip = git("rev-parse", "HEAD").stdout.strip()
        if pin:
            if git("merge-base", "--is-ancestor", pin, tip, check=False).returncode != 0:
                problems.append(f"force-push or branch reset: the pinned commit {pin[:12]} is not an ancestor of the ledger's branch ({tip[:12]})")
            else:
                notes.append(f"the pinned commit {pin[:12]} is still an ancestor of the ledger's branch")
        else:
            notes.append(f"no --pin: a force-push that replaced the whole history could not be told from a normal one; write down the tip ({tip}) and pass it next time")
        log = git("log", "--first-parent", "--diff-merges=first-parent", "--reverse", "-p", "--no-color", "--no-ext-diff", "--format=@@commit %H", "HEAD", "--", "anchors/", check=False).stdout
        own = f"anchors/{re.sub(r'[^A-Za-z0-9_.-]', '_', key_id)}.jsonl" if key_id else ""
        seen = set()
        touched: Dict[tuple, int] = {}
        commit = path = ""
        in_hunk = False
        for line in log.splitlines():
            if line.startswith("@@commit "):
                commit, path, in_hunk = line.split(" ", 1)[1].strip(), "", False
            elif line.startswith("diff --git "):
                in_hunk = False
                path = line.rsplit(" b/", 1)[-1]
            elif not in_hunk and line.startswith(("deleted file mode", "rename from ", "rename to ")):
                touched[(commit, path, "deleted or renamed")] = touched.get((commit, path, "deleted or renamed"), 0) + 1
            elif line.startswith("@@"):
                in_hunk = True
            elif in_hunk and line.startswith("-"):
                touched[(commit, path, "removed or changed")] = touched.get((commit, path, "removed or changed"), 0) + 1
            elif in_hunk and line.startswith("+") and (not own or path == own):
                try:
                    row = json.loads(line[1:])
                except ValueError:
                    problems.append(f"{path}: an unreadable line was added in commit {commit[:12]}")
                    continue
                key = (row.get("key_id"), row.get("entries"), row.get("head"), row.get("signature"))
                if key not in seen:
                    seen.add(key)
                    anchors.append(row)
        for (sha, file_path, kind), count in touched.items():
            problems.append(f"{file_path}: {count} anchor line(s) {kind} by an ordinary commit {sha[:12]}: a ledger may only be appended to")
        if not key_id:
            notes.append("no --git-key-id: the anchors of every key in the ledger were compared with this bundle")
        notes.append(f"the ledger was read in full: {len(anchors)} anchor(s) ever added, branch tip {tip[:12]}")
    return {"anchors": anchors, "problems": problems, "notes": notes, "tip": tip}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle")
    parser.add_argument("--pubkey", default=None, help="the signer's public key hex, published out of band")
    parser.add_argument("--git-ledger", default=None, help="a git witness's repository (an address or a path), read in full from THIS machine")
    parser.add_argument("--git-branch", default="main")
    parser.add_argument("--git-key-id", default="", help="only the ledger file of this key (anchors/<key id>.jsonl) is compared with the bundle")
    parser.add_argument("--pin", default="", help="a commit of the ledger written down out of band earlier: it must still be an ancestor of the branch")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read the bundle: {exc}", file=sys.stderr)
        return 2
    extra_problems: List[str] = []
    extra_notes: List[str] = []
    if args.git_ledger:
        ledger = git_ledger(args.git_ledger, args.git_branch, args.git_key_id, args.pin)
        extra_problems, extra_notes = ledger["problems"], ledger["notes"]
        bundle = {**bundle, "witnesses": [*(bundle.get("witnesses") or []), {"name": "git ledger read by this verifier", "anchors": ledger["anchors"]}]}
    report = verify(bundle, args.pubkey)
    if extra_problems or extra_notes:
        report = {**report, "ok": report["ok"] and not extra_problems, "problems": [*report["problems"], *extra_problems], "notes": [*report["notes"], *extra_notes]}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'VERIFIED' if report['ok'] else 'NOT VERIFIED'}: {report['rows_checked']} rows ({report['rows_signed']} signed), {report['anchors_checked']} witness anchor(s); key from the {report['key_source']}")
        for note in report["notes"]:
            print(f"  note: {note}")
        for problem in report["problems"]:
            print(f"  PROBLEM: {problem}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
