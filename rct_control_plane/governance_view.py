"""
Round 56: one place that answers "how well is this runtime governed, and can I check it myself?".

Everything the Desk's governance pages show comes from here, and everything here is read from the runtime's own stores
(the audit trail and its hash chain, pending_actions and their signatures, the owner's policy file, the approver and token
files, the sovereignty policy, the jury file, the environment). Nothing is invented and nothing is a percentage: a control is
either on or off, with the reason and the command that changes it. Nothing here can change a setting or approve anything;
those stay behind signatures (approvals.py, the signed policy endpoints).

The functions take a sqlite3 connection (or a persistence object) so tests can drive them with a temporary home.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

# What a viewer can filter on, and the audit entity types behind each category.
CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "blocked": ("governed_loop_guard",),
    "screening": ("governed_loop_tool_result_screen", "governed_loop_second_opinion"),
    "gate": ("governed_loop_fdia_gate",),
    "jury": ("governed_loop_jury",),
    "approvals": ("pending_action_created", "pending_action_decided", "pending_action_executed"),
    "policy": ("fdia_policy",),
    "sovereignty": ("residency_decision",),
    "notary": ("notary_receipt", "notary_gap"),
    "identity": ("identity",),
    "episodes": ("governed_loop_episode_start", "governed_loop_episode_end"),
    "steps": ("autonomous_loop_step", "autonomous_loop_batch", "intent_loop_pillars", "algorithm_pipeline"),
    "cron": ("cron_job",),
    "checkpoints": ("repo_checkpoint",),
    "models": ("model_fallback",),
    # Round 61
    "hooks": ("agent_hook",),
    "memory": ("memory_candidate", "skill_curator", "memory_log", "memory_revoked"),
    "tasks": ("agent_task",),
    "scope": ("governed_loop_scope", "governed_loop_taint", "governed_loop_envelope"),
}
CATEGORY_OF = {entity: name for name, entities in CATEGORIES.items() for entity in entities}
# "attention" is the default view: what a person responsible for the system should look at. It leaves out the routine
# rows (every allowed tool call, every notary receipt, episode start and end).
ATTENTION_SQL = (
    "(t.entity_type IN ('governed_loop_guard','governed_loop_tool_result_screen','governed_loop_jury','pending_action_created',"
    "'pending_action_decided','pending_action_executed','fdia_policy','identity','notary_gap','repo_checkpoint','model_fallback')"
    " OR (t.entity_type = 'cron_job' AND t.action IN ('created','deleted','switched_off','throttled','delivery_failed'))"
    " OR (t.entity_type = 'agent_hook' AND t.action NOT IN ('transform_applied'))"
    " OR (t.entity_type = 'governed_loop_scope')"
    " OR (t.entity_type = 'skill_curator')"
    " OR (t.entity_type = 'residency_decision' AND t.action != 'allow')"
    " OR (t.entity_type = 'governed_loop_second_opinion' AND t.action = 'attack')"
    " OR (t.entity_type = 'governed_loop_fdia_gate' AND t.changes LIKE '%\"blocked\": true%'))")


WITNESSES_ENV_NAME = "DELENTIA_AUDIT_WITNESSES"


def _loads(value: Any) -> Any:
    if isinstance(value, (dict, list)) or value is None:
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _short(text: Any, n: int = 90) -> str:
    s = " ".join(str(text if text is not None else "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def fingerprint(public_key_hex: str) -> str:
    try:
        return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()[:16]
    except ValueError:
        return "invalid"


# ------------------------------------------------------------------ events

def summarise(entity_type: str, action: str, changes: Dict[str, Any]) -> str:
    """One readable line per audit row, built from fields the loop really records."""
    c = changes if isinstance(changes, dict) else {}
    if entity_type == "governed_loop_guard":
        if action == "goal_refused_by_jury":
            return f"goal refused by the {c.get('tier')} jury (risk {c.get('risk')}); verdict {_short(c.get('verdict_digest'), 14)}"
        found = [f for f in (c.get("findings") or []) if isinstance(f, dict)]
        ids = ", ".join(str(f.get("pattern_id")) for f in found[:4]) or ", ".join(str(f.get("pattern_id")) for f in (c.get("cord_findings") or [])[:4] if isinstance(f, dict))
        what = _short(found[0].get("detail"), 80) if found else ""
        return f"goal blocked by CORD ({c.get('cord_verdict') or c.get('verdict') or 'rejected'}): {ids or 'no rule recorded'}" + (f" - {what}" if what else "")
    if entity_type == "governed_loop_tool_result_screen":
        return f"{c.get('tool_name')}: result {'withheld from the model' if action == 'withheld' else 'passed with a warning'} ({', '.join(map(str, (c.get('rules') or [])[:4]))})"
    if entity_type == "governed_loop_second_opinion":
        verdict = {"attack": "judged an attack", "benign": "judged harmless", "no_opinion": "gave no opinion"}.get(action, action)
        return f"small model {verdict} about {c.get('about')}"
    if entity_type == "governed_loop_fdia_gate":
        policy = c.get("policy") or {}
        tail = f", rule {policy.get('rule_id')}" if isinstance(policy, dict) and policy.get("rule_id") else ""
        return f"{c.get('tool_name')}: F={c.get('F')} (D={c.get('D')}, I={c.get('I')}, A={c.get('A')}) {'BLOCKED' if c.get('blocked') else 'allowed'}{tail}"
    if entity_type == "governed_loop_jury":
        jv: Any = c.get("verdict") or {}
        return f"jury {'agreed' if action == 'jury_agreed' else 'refused'} on {c.get('tool_name')} ({c.get('rule_id')}); verdict {_short(jv.get('digest') if isinstance(jv, dict) else '', 14)}"
    if entity_type == "pending_action_created":
        return f"{c.get('tool_name')} is waiting for {c.get('required_signatures', 1)} signature(s)" + (f" ({c.get('policy_rule')})" if c.get("policy_rule") else "")
    if entity_type == "pending_action_decided":
        return f"{c.get('tool_name')} {action} by {c.get('approver_role') or 'a trusted'} key {fingerprint(str(c.get('approver_public_key') or ''))}"
    if entity_type == "pending_action_executed":
        return f"{c.get('tool_name')} ran once after approval"
    if entity_type == "fdia_policy":
        return f"owner policy {action.replace('policy_', '')}: {_short(c.get('digest_before'), 10) or 'none'} -> {_short(c.get('digest_after') or c.get('archived_as'), 24)}"
    if entity_type == "residency_decision":
        return f"model call {action}: {_short(c.get('reason'), 110)}"
    if entity_type == "notary_receipt":
        return f"notary receipt #{(c.get('receipt') or {}).get('seq')} for {action}"
    if entity_type == "notary_gap":
        return f"the notary could not record {action}; kept as a visible gap"
    if entity_type == "model_fallback":
        return f"the model {c.get('from')} failed ({_short(c.get('reason'), 70)}); this call went to {c.get('to')}"
    if entity_type == "repo_checkpoint":
        return f"rollback of {_short(c.get('path'), 60)}: {c.get('result')}" + (" (forced)" if c.get("forced") else "")
    if entity_type == "cron_job":
        extra = f" ({c.get('reason')})" if c.get("reason") else (f" ended {c.get('stopped_reason')}" if c.get("stopped_reason") else "")
        return f"cron job {action}: {_short(c.get('name'), 50)} [{c.get('schedule')}]{extra}"
    if entity_type == "identity":
        return f"{action}: {c.get('name')}"
    if entity_type == "agent_hook":
        verb = {"pre_tool_call_block": "refused a call to", "pre_tool_call_require_signature": "asked for a signature on a call to", "transform_applied": "edited a result of",
                "transform_refused": "returned an invalid edit for", "hash_mismatch_refused": "no longer matches its signed code (asked for a signature on)"}.get(action, "")
        return (f"hook {verb} {c.get('tool_name')}" + (f": {_short(c.get('reason'), 80)}" if c.get("reason") else "")) if verb else f"hook {action}"
    if entity_type == "governed_loop_scope":
        return f"{c.get('tool_name')} refused for a chat person: it shows what every person asked (owner-only tool)"
    if entity_type == "memory_log" and action == "memory_log_anchor":
        return f"memory log head #{c.get('head_seq')} written into the audit chain ({_short(c.get('head_hash'), 12)}, {c.get('events_since_last_anchor')} event(s) since the last)"
    if entity_type == "memory_log" and action == "memory_erased":
        return f"memory of {_short(c.get('namespace'), 40)} erased by destroying its key ({c.get('events')} event(s), {c.get('plaintext_events')} left readable): {_short(c.get('reason'), 80)}"
    if entity_type == "memory_revoked":
        return f"a memory was revoked ({c.get('reason_chars', 0)} characters of reason kept as a hash)"
    if entity_type == "skill_curator":
        return f"skill {action} by the curator ({c.get('kind')}): {_short(c.get('reason'), 90)}"
    if entity_type == "memory_candidate":
        return f"memory suggestion {action}"
    if entity_type == "agent_task":
        return f"task {action} ({c.get('status')}, {c.get('steps')} step(s))"
    if entity_type == "autonomous_loop_step":
        return f"step: {_short(c.get('action') or c.get('tool_name') or action, 100)}"
    if entity_type == "intent_loop_pillars":
        return "the Intent Loop's five pillars were measured for this episode"
    if entity_type == "algorithm_pipeline":
        return "the 41-algorithm pipeline ran for this episode"
    if entity_type == "governed_loop_episode_start":
        return f"episode started: {_short(c.get('goal'), 90)}"
    if entity_type == "governed_loop_episode_end":
        return f"episode ended: {c.get('stopped_reason')} after {c.get('iterations')} step(s)"
    return _short(f"{entity_type} {action}", 110)


def _where(category: Optional[str], query: Optional[str]) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    args: List[Any] = []
    if category == "attention":
        clauses.append(ATTENTION_SQL)
    elif category and category != "all":
        entities = CATEGORIES.get(category)
        if not entities:
            raise ValueError(f"unknown category {category!r}")
        clauses.append("t.entity_type IN (" + ",".join("?" for _ in entities) + ")")
        args += list(entities)
    if query:
        like = f"%{query.strip()[:80]}%"
        clauses.append("(t.entity_id LIKE ? OR t.action LIKE ? OR t.actor LIKE ? OR t.changes LIKE ?)")
        args += [like] * 4
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def events(conn: sqlite3.Connection, category: Optional[str] = "attention", query: Optional[str] = None,
           limit: int = 50, before_id: Optional[int] = None) -> Dict[str, Any]:
    """Audit rows, newest first, with the chain link of each (sequence number, row hash, whether it is signed)."""
    conn.row_factory = sqlite3.Row
    where, args = _where(category, query)
    if before_id is not None:
        where += (" AND " if where else " WHERE ") + "t.id < ?"
        args.append(int(before_id))
    sql = ("SELECT t.id, t.entity_type, t.entity_id, t.action, t.actor, t.changes, t.created_at, "
           "c.seq AS chain_seq, c.row_hash AS row_hash, c.signature_hex AS sig FROM audit_trail t "
           "LEFT JOIN audit_chain c ON c.audit_id = t.id" + where + " ORDER BY t.id DESC LIMIT ?")
    rows = conn.execute(sql, [*args, max(1, min(int(limit), 300))]).fetchall()
    out = []
    for r in rows:
        from rct_control_plane import audit_text
        changes = audit_text.reveal_changes(r["actor"], _loads(r["changes"]) or {})
        out.append({"id": r["id"], "category": CATEGORY_OF.get(r["entity_type"], "other"), "entity_type": r["entity_type"],
                    "entity_id": r["entity_id"], "action": r["action"], "actor": r["actor"], "at": r["created_at"],
                    "summary": summarise(r["entity_type"], r["action"], changes),
                    "chain_seq": r["chain_seq"], "row_hash": (r["row_hash"] or "")[:16] or None, "signed": bool(r["sig"])})
    return {"category": category or "all", "events": out, "next_before_id": out[-1]["id"] if len(out) == min(int(limit), 300) else None}


def event_detail(conn: sqlite3.Connection, audit_id: int) -> Optional[Dict[str, Any]]:
    """One row in full, with its place in the chain and a recomputation of its own hash."""
    from rct_control_plane import audit_chain
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM audit_trail WHERE id = ?", (audit_id,)).fetchone()
    if row is None:
        return None
    link = conn.execute("SELECT seq, prev_hash, row_hash, signature_hex, signer_fingerprint FROM audit_chain WHERE audit_id = ?", (audit_id,)).fetchone()
    from rct_control_plane import audit_text
    shown = audit_text.reveal_changes(row["actor"], _loads(row["changes"]) or {})
    detail: Dict[str, Any] = {"id": row["id"], "entity_type": row["entity_type"], "entity_id": row["entity_id"], "action": row["action"],
                              "actor": row["actor"], "at": row["created_at"], "changes": shown,
                              "summary": summarise(row["entity_type"], row["action"], shown), "chain": None}
    if link is not None:
        recomputed = audit_chain.row_hash(link["prev_hash"], row["id"], row["entity_type"], row["entity_id"], row["action"],
                                          row["actor"], row["changes"], row["created_at"])
        detail["chain"] = {"seq": link["seq"], "prev_hash": link["prev_hash"], "row_hash": link["row_hash"],
                           "recomputed_matches": recomputed == link["row_hash"], "signed": bool(link["signature_hex"]),
                           "signer_fingerprint": link["signer_fingerprint"], "signature_hex": link["signature_hex"]}
    related = conn.execute("SELECT id, entity_type, action, created_at FROM audit_trail WHERE entity_id = ? AND id != ? ORDER BY id LIMIT 20",
                           (row["entity_id"], audit_id)).fetchall() if row["entity_id"] else []
    detail["related"] = [{"id": r["id"], "entity_type": r["entity_type"], "action": r["action"], "at": r["created_at"]} for r in related]
    return detail


def counts(conn: sqlite3.Connection) -> Dict[str, Any]:
    """What the controls have actually done, from the audit trail (all time)."""
    rows = conn.execute("SELECT entity_type, action, COUNT(*) FROM audit_trail GROUP BY entity_type, action").fetchall()
    by: Dict[Tuple[str, str], int] = {(r[0], r[1]): int(r[2]) for r in rows}

    def total(entity: str, *actions: str) -> int:
        return sum(n for (e, a), n in by.items() if e == entity and (not actions or a in actions))

    blocked_gate = conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'governed_loop_fdia_gate' AND changes LIKE '%\"blocked\": true%'").fetchone()[0]
    pending = conn.execute("SELECT status, COUNT(*) FROM pending_actions GROUP BY status").fetchall() if _has_table(conn, "pending_actions") else []
    return {
        "goals_blocked": total("governed_loop_guard", "goal_blocked"), "goals_refused_by_jury": total("governed_loop_guard", "goal_refused_by_jury"),
        "tool_calls_judged": total("governed_loop_fdia_gate"), "tool_calls_blocked": int(blocked_gate),
        "tool_results_withheld": total("governed_loop_tool_result_screen", "withheld"), "tool_results_warned": total("governed_loop_tool_result_screen", "warned"),
        "second_opinion_attacks": total("governed_loop_second_opinion", "attack"),
        "jury_agreed": total("governed_loop_jury", "jury_agreed"), "jury_refused": total("governed_loop_jury", "jury_refused"),
        "approvals_by_status": {str(r[0]): int(r[1]) for r in pending},
        "policy_changes": total("fdia_policy"), "model_calls_blocked": total("residency_decision", "block"), "model_calls_redacted": total("residency_decision", "redact"),
        "model_calls_allowed": total("residency_decision", "allow"), "notary_gaps": total("notary_gap"), "episodes": total("governed_loop_episode_start"),
    }


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


# ------------------------------------------------------------------ signatures and approver keys

def _approvers() -> Tuple[Dict[str, str], Dict[str, str], str]:
    """(keys, roles, problem). An approvers file that cannot be read means nobody can approve: shown as a finding, not a crash."""
    from rct_control_plane import approvals
    try:
        return approvals.trusted_approver_keys(), approvals.trusted_approver_roles(), ""
    except approvals.ApprovalError:
        return {}, {}, "the approvers file exists but cannot be read, so nobody can approve anything (check it on the host)"


def approver_keys(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Who may sign (public keys only), the role each holds, and what each has signed so far."""
    from rct_control_plane import approvals
    keys, roles, problem = _approvers()
    used: Dict[str, Tuple[int, Optional[float]]] = {}
    if _has_table(conn, "pending_action_signatures"):
        for pk, n, last in conn.execute("SELECT public_key, COUNT(*), MAX(decided_at) FROM pending_action_signatures GROUP BY public_key"):
            used[pk] = (int(n), last)
    rejected: Dict[str, int] = {}
    if _has_table(conn, "pending_actions"):
        for pk, n in conn.execute("SELECT approver_public_key, COUNT(*) FROM pending_actions WHERE status = 'REJECTED' GROUP BY approver_public_key"):
            rejected[pk] = int(n)
    listed = [{"name": name, "role": roles.get(pk), "public_key": pk, "fingerprint": fingerprint(pk),
               "approvals_signed": used.get(pk, (0, None))[0], "last_signed": used.get(pk, (0, None))[1],
               "rejections_signed": rejected.get(pk, 0)} for pk, name in keys.items()]
    return {"file": str(approvals._approvers_file()), "problem": problem, "keys": listed,
            "roles_held": sorted({k["role"] for k in listed if k["role"]})}


def signature_ledger(persistence: Any, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """Every action that needed a human, with each signature on it re-verified now against the action's digest."""
    from rct_control_plane import approvals
    store = approvals.PendingActionStore(persistence)
    keys, roles, _problem = _approvers()
    out: List[Dict[str, Any]] = []
    with persistence._connect() as conn:
        for action in store.list(status=status, limit=limit):
            sigs = conn.execute("SELECT public_key, signature_hex, decided_at FROM pending_action_signatures WHERE approval_id = ? ORDER BY decided_at", (action.approval_id,)).fetchall()
            decision = "APPROVED"
            if action.status == "REJECTED" and action.approver_public_key:
                sigs = [(action.approver_public_key, action.signature_hex, action.decided_at)]
                decision = "REJECTED"
            signers = []
            for pk, sig, when in sigs:
                try:
                    ok = approvals.verify_signature(pk, approvals.approval_message(action.approval_id, action.action_sha256, decision), sig or "")
                except Exception:           # noqa: BLE001 - a broken row is shown as not verified
                    ok = False
                signers.append({"name": keys.get(pk), "role": roles.get(pk), "key_fingerprint": fingerprint(pk), "at": when,
                                "signature_prefix": (sig or "")[:16], "verifies_now": ok, "key_still_trusted": pk in keys, "decision": decision})
            needed_roles = list(action.approver_roles or [])
            covered = {s["role"] for s in signers if s["verifies_now"] and decision == "APPROVED"}
            out.append({"approval_id": action.approval_id, "tool_name": action.tool_name, "goal": _short(action.goal, 140), "namespace": action.namespace,
                        "status": action.status, "reason": action.reason, "created_at": action.created_at, "decided_at": action.decided_at,
                        "executed_at": action.executed_at, "action_sha256": action.action_sha256, "policy_rule": action.policy_rule,
                        "required_signatures": action.required_signatures, "signatures_collected": action.signatures_collected,
                        "roles_required": needed_roles, "roles_missing": [r for r in needed_roles if r not in covered] if action.status == "PENDING" else [],
                        "signers": signers})
    return {"approvals": out, "all_signatures_verify": all(s["verifies_now"] for a in out for s in a["signers"])}


# ------------------------------------------------------------------ identities

def identities() -> Dict[str, Any]:
    """Who can reach the API (names, never tokens or hashes) and the role the owner's policy gives each."""
    from rct_control_plane import api_tokens, fdia_policy
    problem = ""
    try:
        entries = api_tokens.load_entries()
    except api_tokens.TokenFileError:
        entries, problem = [], "the tokens file exists but cannot be used, so nobody can get in (run `delentia tokens list` on the host)"
    principals: Dict[str, str] = {}
    default_role = None
    try:
        policy = fdia_policy.load_policy()
        if policy is not None:
            roles_block = policy.to_dict().get("roles") or {}
            principals, default_role = dict(roles_block.get("principals") or {}), roles_block.get("default_role")
    except ValueError:
        pass
    users = [{"name": e["name"], "disabled": bool(e.get("disabled")), "created_at": e.get("created_at"), "disabled_at": e.get("disabled_at"),
              "role": principals.get(e["name"], default_role), "role_is_default": e["name"] not in principals, "owner": bool(e.get("owner"))} for e in entries]
    shared = bool(os.environ.get("DELENTIA_API_TOKEN"))
    mode = ("per-person tokens" if api_tokens.per_user_mode() else "one shared token" if shared else "no token (loopback clients only)")
    return {"mode": mode, "file": str(api_tokens.tokens_path()), "shared_token_set": shared, "users": users, "problem": problem,
            "default_role": default_role, "note": "A token is shown once when created and only its SHA-256 is stored, so this page can list people but never show or recover a token."}


# ------------------------------------------------------------------ audit verification

def verify_deep(conn: sqlite3.Connection, episode_limit: int = 500) -> Dict[str, Any]:
    """The hash chain with signatures checked against this host's own key when it is known, plus every episode's JITNA
    signature re-verified from the stored public key, plus a cross-check of notary receipts held locally."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from rct_control_plane import audit_chain
    public_hex = (os.getenv(audit_chain.PUBKEY_ENV) or "").strip().lower() or None
    source = "DELENTIA_AUDIT_PUBKEY" if public_hex else None
    if public_hex is None:
        try:
            key = audit_chain.load_signing_key()
            if key is not None:
                public_hex, source = audit_chain._public_hex(key), "the signing key on this host"
        except Exception:                   # noqa: BLE001 - an unreadable key is reported as "not checked"
            public_hex = None
    try:
        chain = audit_chain.verify_audit_chain(conn, public_key_hex=public_hex).to_dict()
        signature_check = (f"signatures verified with {source} (fingerprint {audit_chain.fingerprint(public_hex)})" if public_hex
                           else "NOT checked: the chain's hashes are verified, but no public key is known here to check the signatures against")
    except Exception as exc:                # noqa: BLE001 - a bad configured key must not hide the hash check
        chain = audit_chain.verify_audit_chain(conn).to_dict()
        signature_check = f"NOT checked ({type(exc).__name__}: the configured public key could not be used)"

    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, changes FROM audit_trail WHERE entity_type = 'governed_loop_episode_start' ORDER BY id DESC LIMIT ?", (episode_limit,)).fetchall()
    ok = bad = persistent = unsigned = 0
    bad_ids: List[int] = []
    for r in rows:
        c = _loads(r["changes"]) or {}
        sig, pub, digest = c.get("jitna_signature"), c.get("jitna_public_key"), c.get("jitna_content_hash")
        if not (sig and pub and digest):
            unsigned += 1
            continue
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub)).verify(bytes.fromhex(sig), str(digest).encode("utf-8"))
            ok += 1
            persistent += 1 if c.get("jitna_key_persistent") else 0
        except Exception:                   # noqa: BLE001
            bad += 1
            bad_ids.append(int(r["id"]))
    receipts = conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'notary_receipt'").fetchone()[0]
    gaps = conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'notary_gap'").fetchone()[0]
    return {"chain": chain, "signature_check": signature_check,
            "episodes": {"checked": len(rows), "signature_ok": ok, "signature_bad": bad, "bad_audit_ids": bad_ids[:20], "unsigned": unsigned,
                         "signed_with_a_persistent_key": persistent,
                         "note": "re-verifies the Ed25519 signature over each episode's recorded content hash with the public key stored beside it; "
                                 "a key that is not persistent is per-process, so it proves integrity, not which host wrote it"},
            "notary": {"receipts_in_local_trail": int(receipts), "gaps": int(gaps)}}


def check_witness(conn: sqlite3.Connection, witness_json: Dict[str, Any]) -> Dict[str, Any]:
    from rct_control_plane import audit_chain
    return audit_chain.check_anchors(conn, witness_json)


# ------------------------------------------------------------------ the overview

class _PersistenceShim:
    """Just enough of a persistence object (`_connect`) for the registries that only need a connection."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def _connect(self) -> Any:
        return _Reuse(self._conn)


class _Reuse:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, *exc: Any) -> None:
        return None


def _controls(conn: sqlite3.Connection) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    from rct_control_plane import audit_chain, fdia_policy, injection_classifier, residency, signedai_jury
    from rct_control_plane.governed_autonomous_loop import TOOL_RESULT_SCREEN_ENV
    from rct_control_plane.notary import NOTARY_URL_ENV

    controls: List[Dict[str, Any]] = []
    gaps: List[Dict[str, str]] = []

    def add(cid: str, name: str, on: bool, detail: str, fix: str, severity: str = "warn", always: bool = False, applicable: bool = True) -> None:
        controls.append({"id": cid, "name": name, "on": on, "detail": detail, "how_to_change": fix, "always_on": always, "applicable": applicable})
        if not on and applicable:
            gaps.append({"control": cid, "severity": severity, "text": f"{name}: {detail}", "fix": fix})

    # owner policy
    policy, policy_problem = None, ""
    try:
        policy = fdia_policy.load_policy()
    except ValueError:
        policy_problem = "the policy file cannot be read or is invalid, so every tool call is refused (fail closed)"
    add("owner_policy", "Owner policy for A", policy is not None,
        (f"{len(policy.rules)} rule(s), digest {policy.digest()[:12]}" if policy is not None else policy_problem or "no policy file: only the built-in floor applies (risky tools need F >= 0.5; repo writes need a signature)"),
        "Desk > FDIA policy (start from 'argument-aware': harmless inspection runs, everything else asks), or `delentia fdia template argaware`", "bad" if policy_problem else "warn")
    # signatures
    keys, key_roles, key_problem = _approvers()
    add("approver_keys", "Approver keys (who may sign)", bool(keys),
        (f"{len(keys)} key(s), roles: {', '.join(sorted({r for r in key_roles.values() if r})) or 'none named'}" if keys
         else key_problem or "no approver key is configured, so nothing that needs a human can ever be approved (it fails closed, but also never runs)"),
        "`delentia approvals keygen` on YOUR device, then add the public key to approvers.json", "bad")
    if policy is not None and keys:
        held = set(key_roles.values())
        needed = {role for rule in policy.rules for role in rule.human_approver_role}
        missing = sorted(needed - held)
        add("approver_roles", "Every role the policy asks for is held by a key", not missing,
            "all roles covered" if not missing else f"the policy asks for {', '.join(missing)} but no approver key holds it, so those actions can never be approved",
            "add a key with that role to approvers.json, or change the rule", "bad")
    # identity
    from rct_control_plane import api_tokens
    per_user = api_tokens.per_user_mode()
    add("per_person_tokens", "A token per person (identity comes from the server)", per_user,
        "per-person tokens are on" if per_user else "one shared token or none: every caller is the same identity, so roles in the policy are labels, not controls",
        "`delentia tokens create <name>`")
    # audit
    signing = bool(os.getenv(audit_chain.SIGNING_KEY_ENV))
    add("audit_signed", "Audit chain signed on this host (A1)", signing, "every row is hash-chained" + (" and Ed25519-signed" if signing else " but NOT signed"),
        "`delentia audit-chain keygen`, then set DELENTIA_AUDIT_SIGNING_KEY")
    add("audit_notary", "Separate notary process (A2)", bool(os.getenv(NOTARY_URL_ENV)),
        "tool calls are recorded by another process before they run" if os.getenv(NOTARY_URL_ENV) else "off: a compromised agent process could rewrite its own history",
        "run `delentia notary serve` as another OS user and set DELENTIA_NOTARY_URL")
    from rct_control_plane import audit_witness
    witness = audit_witness.status(conn)
    add("audit_anchor", "Chain head held by an outside witness (A3)", bool(witness["tamper_evident_against_host_compromise"]),
        witness["plain"] if witness["configured"] else "off: " + witness["plain"],
        f"set {WITNESSES_ENV_NAME} (an http witness and a git witness are better than one), then `delentia audit-chain anchor-all`")
    if witness["configured"]:
        add("audit_second_witness", "A second, independent witness", witness["independent_witnesses"] >= 2,
            f"{witness['independent_witnesses']} witness(es) hold a recent head" if witness["independent_witnesses"] >= 2 else
            "one witness is a single party to trust: with a second one an attacker must defeat both",
            f"add a git witness to {WITNESSES_ENV_NAME}", severity="info")
    # Round 67: the memory event log, its anchors in the audit chain, and sealing (what makes erasure possible)
    from rct_control_plane import memory_erasure, memory_eventlog

    class _ConnShim:
        def __init__(self, c: sqlite3.Connection) -> None:
            self._c = c

        def _connect(self) -> sqlite3.Connection:
            return self._c

    log_on = memory_eventlog.enabled()
    anchor_report: Dict[str, Any] = {}
    if log_on:
        try:
            anchor_report = memory_eventlog.MemoryEventLog(_ConnShim(conn)).verify_anchors()
        except sqlite3.Error:
            anchor_report = {}
    if log_on and anchor_report:
        add("memory_log", "Memory history is chained and anchored in the audit chain", bool(anchor_report.get("ok")),
            (f"{anchor_report.get('anchors', 0)} anchor(s) match the log; {anchor_report.get('unanchored_events', 0)} event(s) since the last one are not yet anchored" if anchor_report.get("ok")
             else "; ".join(anchor_report.get("problems", [])[:2]) or "an anchored head no longer matches the log"),
            "`delentia memory log verify` names the broken link; DELENTIA_MEMORY_ANCHOR_EVERY sets how often a head is anchored", "bad")
    else:
        add("memory_log", "Memory history is chained and anchored in the audit chain", False, "the memory event log is off: revocation is a column, not a recorded fact, and nothing can be replayed",
            "unset DELENTIA_MEMORY_EVENTLOG=off")
    add("memory_sealing", "A person's memory text can be erased (sealed with their own key)", bool(log_on and memory_erasure.sealing_enabled()),
        "event payloads and checkpoints are sealed per person; `delentia memory erase` destroys the key with an approver's signature" if log_on and memory_erasure.sealing_enabled()
        else "off: the log holds readable text, so a person's data can be revoked but not erased", "unset DELENTIA_MEMORY_SEAL=off (events written before it was on stay readable)")
    from rct_control_plane import audit_text
    add("audit_text_sealed", "A person's words are sealed in the audit chain (so they can be erased)", audit_text.sealing_on(),
        "the goal, the model's reasoning and tool arguments are written under the person's own key; the chain holds ciphertext and hashes" if audit_text.sealing_on()
        else "off: those words sit in the chain in the clear and a person's erasure cannot remove them", "unset DELENTIA_AUDIT_TEXT=plain (rows written before it was on stay readable)")
    # sovereignty
    info = residency.describe()
    add("sovereignty", "Data-residency policy", bool(info.get("enforced")),
        (f"home region {(info.get('policy') or {}).get('home_region')}" if info.get("enforced") else "off: model calls are not checked for where the data goes"),
        "Desk > Sovereignty, or `delentia sovereignty set`")
    # screening
    mode = (os.environ.get(TOOL_RESULT_SCREEN_ENV) or "block").strip().lower()
    add("injection_screen", "Injection screen on what tools bring back", mode != "off", f"mode: {mode}", f"set {TOOL_RESULT_SCREEN_ENV}=block", "bad", always=False)
    second = injection_classifier.mode()
    add("second_opinion", "Small-model second opinion on suspect text", second != "off", f"mode: {second}",
        "`delentia model set <model> --profile classifier`, then DELENTIA_CORD_SECOND_OPINION=flag|block", "info")
    # jury
    jury_path = signedai_jury.config_path()
    needs_jury = bool(policy is not None and (policy.jury_by_risk or any(rule.jury_tier for rule in policy.rules)))
    add("jury", "Multi-model jury", jury_path.exists(),
        ("configured" if jury_path.exists() else "not used: the owner's policy asks for no jury" if not needs_jury else "the policy asks for a jury but no jury file exists, so those actions are refused"),
        "write ~/.delentia/jury.json (members name environment variables, never keys; see `delentia jury run --help`)", "bad", applicable=needs_jury or jury_path.exists())
    # policy changes need a signature
    signed_changes = per_user or os.environ.get("DELENTIA_POLICY_CHANGE_REQUIRES_SIGNATURE", "").strip().lower() in ("1", "true", "yes")
    add("policy_change_signed", "Changing the policy needs a signature", signed_changes,
        "a policy change waits for an approver's signature" if signed_changes else "anyone who can reach the API can change the owner's policy",
        "DELENTIA_POLICY_CHANGE_REQUIRES_SIGNATURE=1 (automatic once per-person tokens exist)")
    # Round 58-61
    from rct_control_plane.governed_autonomous_loop import TAINT_ENV
    taint_mode = (os.environ.get(TAINT_ENV) or "on").strip().lower()
    add("taint_gate", "Taint gate: after outside text, side effects need a signature", taint_mode not in ("off", "0", "false", "no"),
        "on: once an episode has read a page, file or search result, nothing that changes or sends anything runs without a person" if taint_mode not in ("off", "0", "false", "no")
        else "OFF: a hijacked model could act on instructions hidden in text it read", f"unset {TAINT_ENV} (it is on by default)", "bad")
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    untrusted = GovernedAutonomousLoop._untrusted_prefixes()
    add("untrusted_folders", "Folders that hold other people's documents count as outside text", bool(untrusted),
        ("reading a file under " + ", ".join(untrusted) + " taints the episode like a web page") if untrusted
        else "switched off (DELENTIA_UNTRUSTED_PATHS=none): a file in the workspace is treated as the owner's own text, so a note hidden in a vendor's quote is not marked as foreign",
        "DELENTIA_UNTRUSTED_PATHS=quotes/,inbox/ (comma-separated folders relative to the workspace; unset = inbox/, downloads/, attachments/, incoming/; none = off)", "info")
    from rct_control_plane import envelope
    lim = envelope.limits()
    has_daily = any(lim.get(k) for k in ("daily_usd", "daily_tokens", "user_daily_usd", "user_daily_tokens"))
    add("spending_limits", "A daily spending or token limit", has_daily,
        "a daily limit is set" if has_daily else "none: nothing but the per-episode budget stops a busy day from costing more than you expect",
        "`delentia limits` or DELENTIA_DAILY_BUDGET_USD / DELENTIA_DAILY_MAX_TOKENS")
    from rct_control_plane import approvals as _approvals
    decision_ttl, execution_ttl = _approvals.decision_ttl_seconds(), _approvals.execution_ttl_seconds()
    windows_on = decision_ttl > 0 and execution_ttl > 0
    add("approval_windows", "An approval has a time limit", windows_on,
        f"a request nobody decides within {decision_ttl / 3600:.0f} h expires, and an approval not used within {execution_ttl / 3600:.0f} h never runs (rows stay on disk)" if windows_on
        else "at least one window is switched off (0): an old approval can still be used long after the situation it was given for has changed",
        f"{_approvals.DECISION_TTL_ENV} / {_approvals.EXECUTION_TTL_ENV} (seconds; 0 = no limit)", "info")
    from rct_control_plane import verify_grounding
    verify_on = (os.environ.get(verify_grounding.ENV) or "on").strip().lower() not in ("off", "0", "false")
    add("verify_grounding", "VERIFY checks the answer against the evidence", verify_on,
        "an answer with an invented fact, an action no tool did, or success after an error is never learned as a skill" if verify_on else "off: only word overlap decides what is learned",
        f"unset {verify_grounding.ENV}", "info")
    from rct_control_plane import hooks as hooks_module
    try:
        registry = hooks_module.HookRegistry(_PersistenceShim(conn))
        listed = registry.list()
        active_hooks = [h for h in listed if h["status"] == "ACTIVE"]
    except Exception:                                      # noqa: BLE001
        listed, active_hooks = [], []
    add("hooks", "Hooks (signed code that can only tighten)", bool(active_hooks),
        (f"{len(active_hooks)} active: " + ", ".join(h["name"] for h in active_hooks)) if active_hooks else "none active", "`delentia hooks propose` (every hook needs a signature)",
        "info", applicable=bool(listed))
    from rct_control_plane import memory_nudge
    add("memory_nudge", "Memory suggestions (asks before remembering)", memory_nudge.enabled(),
        "on: what a person says about themselves is offered back; nothing is stored until they say yes" if memory_nudge.enabled() else "off",
        f"set {memory_nudge.ENV}=1 (`delentia serve` does)", "info")
    owner_tools_open = (os.environ.get("DELENTIA_OWNER_TOOLS_FOR_CHANNELS") or "").strip().lower() in ("1", "true", "yes")
    add("owner_only_tools", "Chat people cannot read other people's requests through the agent", not owner_tools_open,
        "the audit-log, intents and reminder-firing tools are refused on chat channels and the HTTP agent API" if not owner_tools_open else "OFF: DELENTIA_OWNER_TOOLS_FOR_CHANNELS lets them through (a single-user host only)",
        "unset DELENTIA_OWNER_TOOLS_FOR_CHANNELS", "bad")
    add("secret_files", "The agent cannot read credential files", True, "always on: .env, keys, credentials and the runtime's own databases are refused by the read and search tools and @file", "", always=True)
    add("cord_goal_screen", "CORD screens every goal before the model sees it", True, "always on in the governed loop", "", always=True)
    add("fdia_floor", "FDIA gate with the built-in floor", True, "always on: a policy can tighten it, never loosen it", "", always=True)
    return controls, gaps


def overview(conn: sqlite3.Connection) -> Dict[str, Any]:
    controls, gaps = _controls(conn)
    active = sum(1 for c in controls if c["on"])
    applicable = sum(1 for c in controls if c["applicable"])
    order = {"bad": 0, "warn": 1, "info": 2}
    last_policy = conn.execute("SELECT created_at, actor, changes FROM audit_trail WHERE entity_type = 'fdia_policy' ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "controls": controls, "on": active, "total": applicable,
        "gaps": sorted(gaps, key=lambda g: order.get(g["severity"], 3)),
        "activity": counts(conn),
        "last_policy_change": ({"at": last_policy[0], "by": last_policy[1], "changes": _loads(last_policy[2])} if last_policy else None),
        "generated_at": time.time(),
        "reading_this": "A control is on or off; there is no score. 'On' means configured on this host now, not that it has been attacked and held.",
    }
