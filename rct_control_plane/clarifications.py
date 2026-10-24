"""
Round 92 (P1 of DELENTIA_ROUND92_B2_0_ASK_AND_WAIT_AND_PLAN_FIRST_DESIGN.md): a question the system puts to a person, and the wait for the answer.

RCT-7 as the creator defines it (R5 and R7): when the intent is not clear enough to act, or when the result does not match the intent, the work STOPS, the difference is reported, the person is asked,
and nothing runs on its own until the person answers. The answer is a new VERSION of the intent; the original is kept (RC08). This module is the store for that wait. It does not decide when to ask
(the loop will, behind a flag, in P3/P4) and it changes nothing about how the gate judges a tool call.

What it guarantees
  * a question survives a restart and never runs anything by itself (RC10);
  * only the person the question belongs to (or an owner acting for them) can answer; a model, a tool result or another person cannot;
  * an answer is accepted once; a question that is answered, cancelled or expired cannot be answered again;
  * waiting for a long time is not agreement: after `DELENTIA_CLARIFICATION_TTL_SECONDS` (default 7 days) the row becomes EXPIRED and nothing runs;
  * the person's words (the original goal, the question, what was expected and observed, the answer) are sealed under the person's own key, so erasing the person erases them (the audit chain
    holds ciphertext and hashes, like every other row that carries personal text);
  * every change of state is an audit row.
A clarification is NOT an approval: an answer never lifts a policy decision, a forbidden path or a signature requirement for what is done afterwards.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rct_control_plane import audit_text
from rct_control_plane.persistence import ControlPlanePersistence

TTL_ENV = "DELENTIA_CLARIFICATION_TTL_SECONDS"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600

KINDS = ("before_act", "mismatch")                       # R5: not clear enough to act / R7: the result does not match the intent
CRITERIA = ("unclear_intent", "language", "format", "forbidden_effect", "required_artifact", "length", "item_count", "model_unclear", "semantic", "agent_question")
STATUSES = ("PENDING", "ANSWERED", "CANCELLED", "EXPIRED")
SEALED_FIELDS = ("original_goal", "question", "expected", "observed", "answer")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clarifications (
    clarification_id   TEXT PRIMARY KEY,
    namespace          TEXT NOT NULL,
    episode_id         TEXT,
    kind               TEXT NOT NULL,
    criterion          TEXT NOT NULL,
    intent_version     INTEGER NOT NULL,
    new_intent_version INTEGER,
    status             TEXT NOT NULL,
    fields_json        TEXT NOT NULL,
    answered_by        TEXT,
    created_at         REAL NOT NULL,
    answered_at        REAL,
    expires_at         REAL NOT NULL,
    continued_at       REAL,
    continued_as       TEXT
);
CREATE INDEX IF NOT EXISTS idx_clarifications_ns_status ON clarifications(namespace, status, created_at);
"""


# The revised goal carries the person's answer under this marker, so a rule that reads requirements from words can tell the original request from the update.
UPDATE_MARK = "--- Update from the person (intent version "
ANSWER_LABEL = "Person's answer: "


class ClarificationError(ValueError):
    pass


def ttl_seconds() -> float:
    try:
        return float(os.environ.get(TTL_ENV, DEFAULT_TTL_SECONDS))
    except ValueError:
        return float(DEFAULT_TTL_SECONDS)


def _now() -> float:
    return time.time()


@dataclass
class Clarification:
    clarification_id: str
    namespace: str
    kind: str
    criterion: str
    intent_version: int
    status: str
    created_at: float
    expires_at: float
    episode_id: Optional[str] = None
    new_intent_version: Optional[int] = None
    answered_by: Optional[str] = None
    answered_at: Optional[float] = None
    original_goal: str = ""
    question: str = ""
    expected: str = ""
    observed: str = ""
    answer: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clarification_id": self.clarification_id, "namespace": self.namespace, "episode_id": self.episode_id, "kind": self.kind, "criterion": self.criterion,
            "intent_version": self.intent_version, "new_intent_version": self.new_intent_version, "status": self.status, "question": self.question,
            "expected": self.expected, "observed": self.observed, "answer": self.answer, "original_goal": self.original_goal,
            "answered_by": self.answered_by, "created_at": self.created_at, "answered_at": self.answered_at, "expires_at": self.expires_at,
            "continued_as": self.extra.get("continued_as"), "continued_at": self.extra.get("continued_at"),
        }

    def revised_goal(self) -> str:
        """The goal for the NEXT episode: the original words, then what the person said when asked. The original is never overwritten; this is a new version that cites it."""
        if self.status != "ANSWERED":
            raise ClarificationError("only an answered clarification has a revised goal")
        return (f"{self.original_goal}\n\n{UPDATE_MARK}{self.new_intent_version}) ---\n"
                f"Question asked: {self.question}\n{ANSWER_LABEL}{self.answer}")


class ClarificationStore:
    def __init__(self, persistence: ControlPlanePersistence):
        self._persistence = persistence
        with self._persistence._connect() as conn:
            conn.executescript(_SCHEMA)
            have = {r[1] for r in conn.execute("PRAGMA table_info(clarifications)").fetchall()}
            for column, kind in (("continued_at", "REAL"), ("continued_as", "TEXT")):
                if column not in have:                                # a store created before round 97
                    conn.execute(f"ALTER TABLE clarifications ADD COLUMN {column} {kind}")

    # ------------------------------------------------------------------ writing
    def create(self, namespace: str, kind: str, criterion: str, question: str, *, original_goal: str = "", expected: str = "", observed: str = "",
               episode_id: Optional[str] = None, intent_version: int = 1) -> Clarification:
        if kind not in KINDS:
            raise ClarificationError(f"kind must be one of {KINDS}")
        if criterion not in CRITERIA:
            raise ClarificationError(f"criterion must be one of {CRITERIA}")
        if not str(question or "").strip():
            raise ClarificationError("a question is required")
        cid = uuid.uuid4().hex[:12]
        now = _now()
        ttl = ttl_seconds()
        plain = {"original_goal": original_goal, "question": question, "expected": expected, "observed": observed, "answer": ""}
        sealed = audit_text.protect(namespace, plain, SEALED_FIELDS)
        with self._persistence._connect() as conn:
            conn.execute(
                "INSERT INTO clarifications (clarification_id, namespace, episode_id, kind, criterion, intent_version, status, fields_json, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)",
                (cid, namespace, episode_id, kind, criterion, int(intent_version), json.dumps(sealed, ensure_ascii=False), now, now + (ttl if ttl > 0 else 10 ** 10)))
        self._audit(namespace, cid, "asked", {"kind": kind, "criterion": criterion, "episode_id": episode_id, "intent_version": int(intent_version),
                                              "question": question, "expected": expected, "observed": observed})
        return self.get(cid)                                          # type: ignore[return-value]

    def answer(self, clarification_id: str, caller: str, text: str, *, as_owner: bool = False) -> Clarification:
        """Record the person's answer. `caller` is who is answering; it must be the person the question belongs to unless an owner answers for them (`as_owner`)."""
        text = str(text or "").strip()
        if not text:
            raise ClarificationError("an empty answer is not an answer")
        self._expire_stale()
        row = self._row(clarification_id)
        if row is None:
            raise ClarificationError("no such question")
        if caller != row["namespace"] and not as_owner:
            raise ClarificationError("this question belongs to someone else")
        if row["status"] != "PENDING":
            raise ClarificationError(f"this question is {row['status']}; only a waiting question can be answered")
        ns = row["namespace"]
        fields = self._open(ns, row["fields_json"])
        fields["answer"] = text
        sealed = audit_text.protect(ns, fields, SEALED_FIELDS)
        new_version = int(row["intent_version"]) + 1
        now = _now()
        with self._persistence._connect() as conn:
            changed = conn.execute(
                "UPDATE clarifications SET status = 'ANSWERED', fields_json = ?, answered_by = ?, answered_at = ?, new_intent_version = ? "
                "WHERE clarification_id = ? AND status = 'PENDING'",
                (json.dumps(sealed, ensure_ascii=False), caller, now, new_version, clarification_id)).rowcount
        if changed != 1:                                              # someone answered or cancelled in between: the first writer wins
            raise ClarificationError("this question was just closed by someone else")
        self._audit(ns, clarification_id, "answered", {"answered_by": caller, "new_intent_version": new_version, "answer": text})
        return self.get(clarification_id)                             # type: ignore[return-value]

    def accept(self, clarification_id: str, caller: str, *, as_owner: bool = False) -> Clarification:
        """The person closes an ANSWERED question without running anything again: the result stays as it was and the answer is not used for a later request."""
        row = self._row(clarification_id)
        if row is None:
            raise ClarificationError("no such question")
        if caller != row["namespace"] and not as_owner:
            raise ClarificationError("this question belongs to someone else")
        with self._persistence._connect() as conn:
            changed = conn.execute("UPDATE clarifications SET continued_at = ?, continued_as = 'accepted' "
                                   "WHERE clarification_id = ? AND status IN ('ANSWERED', 'PENDING') AND continued_at IS NULL", (_now(), clarification_id)).rowcount
            if changed == 1 and row["status"] == "PENDING":
                conn.execute("UPDATE clarifications SET status = 'ANSWERED', answered_by = ?, answered_at = ?, new_intent_version = ? WHERE clarification_id = ?",
                             (caller, _now(), int(row["intent_version"]) + 1, clarification_id))
        if changed != 1:
            raise ClarificationError(f"this question is {row['status']} and was already used or closed; it cannot be accepted again")
        self._audit(row["namespace"], clarification_id, "accepted", {"accepted_by": caller, "note": "the result was accepted as it is; nothing was run again"})
        return self.get(clarification_id)                             # type: ignore[return-value]

    def claim_for_goal(self, namespace: str, goal: str) -> Optional[Clarification]:
        """An answered question sticks to the exact request it was asked about. When the SAME person sends that request again, the episode runs on the revised intent
        (the original words plus the person's answer) and the answer is used once. Exact match after whitespace is normalised: never similarity, so a different request is never
        changed by an old answer. Returns the claimed question, or None."""
        wanted = " ".join(str(goal or "").split())
        if not wanted:
            return None
        wanted = " ".join(wanted.split(UPDATE_MARK.strip())[0].split())          # the person sends the plain request; the stored one may already carry earlier answers
        self._expire_stale()
        with self._persistence._connect() as conn:
            conn.row_factory = _dict_row
            rows = conn.execute("SELECT * FROM clarifications WHERE namespace = ? AND status = 'ANSWERED' AND continued_at IS NULL ORDER BY answered_at DESC LIMIT 20",
                                (namespace,)).fetchall()
        for row in rows:
            obj = self._to_obj(row)
            if " ".join(obj.original_goal.split(UPDATE_MARK.strip())[0].split()) != wanted:
                continue
            with self._persistence._connect() as conn:
                changed = conn.execute("UPDATE clarifications SET continued_at = ?, continued_as = 'rerun' "
                                       "WHERE clarification_id = ? AND status = 'ANSWERED' AND continued_at IS NULL", (_now(), obj.clarification_id)).rowcount
            if changed == 1:                                          # the first run to claim it wins; a second one starts from the plain goal
                self._audit(namespace, obj.clarification_id, "continued", {"note": "the person sent the same request again; the episode runs on the revised intent"})
                return obj
        return None

    def release(self, clarification_id: str) -> None:
        """Give an answer back when the episode that claimed it ended for a reason that is not the person's (the model was unreachable): they should not have to answer again."""
        with self._persistence._connect() as conn:
            conn.execute("UPDATE clarifications SET continued_at = NULL, continued_as = NULL WHERE clarification_id = ? AND continued_as = 'rerun'", (clarification_id,))
        row = self._row(clarification_id)
        if row is not None:
            self._audit(row["namespace"], clarification_id, "released", {"note": "the episode ended before it could use the answer; the answer is available again"})

    def cancel(self, clarification_id: str, caller: str, *, as_owner: bool = False) -> Clarification:
        row = self._row(clarification_id)
        if row is None:
            raise ClarificationError("no such question")
        if caller != row["namespace"] and not as_owner:
            raise ClarificationError("this question belongs to someone else")
        if row["status"] != "PENDING":
            raise ClarificationError(f"this question is {row['status']}; only a waiting question can be cancelled")
        with self._persistence._connect() as conn:
            conn.execute("UPDATE clarifications SET status = 'CANCELLED', answered_by = ?, answered_at = ? WHERE clarification_id = ? AND status = 'PENDING'",
                         (caller, _now(), clarification_id))
        self._audit(row["namespace"], clarification_id, "cancelled", {"cancelled_by": caller})
        return self.get(clarification_id)                             # type: ignore[return-value]

    # ------------------------------------------------------------------ reading
    def get(self, clarification_id: str, namespace: Optional[str] = None) -> Optional[Clarification]:
        self._expire_stale()
        row = self._row(clarification_id)
        if row is None or (namespace is not None and row["namespace"] != namespace):
            return None
        return self._to_obj(row)

    def list(self, namespace: Optional[str] = None, status: Optional[str] = "PENDING", limit: int = 50) -> List[Clarification]:
        self._expire_stale()
        sql = "SELECT * FROM clarifications"
        args: List[Any] = []
        where = []
        if namespace is not None:
            where.append("namespace = ?")
            args.append(namespace)
        if status and status.upper() != "ALL":
            where.append("status = ?")
            args.append(status.upper())
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(int(limit))
        with self._persistence._connect() as conn:
            conn.row_factory = _dict_row
            rows = conn.execute(sql, args).fetchall()
        return [self._to_obj(r) for r in rows]

    def waiting_for(self, namespace: str) -> List[Clarification]:
        return self.list(namespace=namespace, status="PENDING", limit=100)

    # ------------------------------------------------------------------ internals
    def _row(self, clarification_id: str) -> Optional[Dict[str, Any]]:
        with self._persistence._connect() as conn:
            conn.row_factory = _dict_row
            return conn.execute("SELECT * FROM clarifications WHERE clarification_id = ?", (clarification_id,)).fetchone()

    def _expire_stale(self) -> None:
        now = _now()
        with self._persistence._connect() as conn:
            rows = conn.execute("SELECT clarification_id, namespace FROM clarifications WHERE status = 'PENDING' AND expires_at < ?", (now,)).fetchall()
            for cid, _ns in rows:
                conn.execute("UPDATE clarifications SET status = 'EXPIRED' WHERE clarification_id = ? AND status = 'PENDING'", (cid,))
        for cid, ns in rows:
            self._audit(ns, cid, "expired", {"note": "no answer in time; nothing was run"})

    @staticmethod
    def _open(namespace: str, fields_json: str) -> Dict[str, Any]:
        raw = json.loads(fields_json)
        return {k: audit_text.reveal(namespace, v) for k, v in raw.items()}

    def _to_obj(self, row: Dict[str, Any]) -> Clarification:
        fields = self._open(row["namespace"], row["fields_json"])
        return Clarification(
            clarification_id=row["clarification_id"], namespace=row["namespace"], kind=row["kind"], criterion=row["criterion"], intent_version=int(row["intent_version"]),
            status=row["status"], created_at=row["created_at"], expires_at=row["expires_at"], episode_id=row["episode_id"], new_intent_version=row["new_intent_version"],
            answered_by=row["answered_by"], answered_at=row["answered_at"], original_goal=str(fields.get("original_goal") or ""), question=str(fields.get("question") or ""),
            expected=str(fields.get("expected") or ""), observed=str(fields.get("observed") or ""), answer=str(fields.get("answer") or ""),
            extra={"continued_as": row.get("continued_as"), "continued_at": row.get("continued_at")})

    def _audit(self, namespace: str, clarification_id: str, action: str, changes: Dict[str, Any]) -> None:
        try:
            self._persistence.append_audit(entity_type="clarification", entity_id=clarification_id, action=action, actor=namespace,
                                           changes=audit_text.protect(namespace, changes, ("question", "expected", "observed", "answer")))
        except Exception:                                             # an audit problem must not decide whether a person can be asked or can answer
            pass


def _dict_row(cursor: Any, row: Any) -> Dict[str, Any]:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}
