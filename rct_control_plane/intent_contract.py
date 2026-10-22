"""Durable, explicit acceptance contracts; not an oracle for arbitrary intent.

The opt-in path retains plans, original intent and user-confirmed revisions.
A signature, a timeout and a model's success claim are not clarification.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List

from rct_control_plane import audit_text

# Keep the first contract release on inspectable answer/read workflows. Pending
# action approval/resume must carry the contract before enabling effect tools.
READ_ONLY_TOOLS = frozenset({"delentia_read_repo_file", "delentia_search_repo_files", "delentia_recall", "delentia_search_sessions"})


class IntentContractError(ValueError):
    pass


def validate_criteria(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise IntentContractError("acceptance_criteria must contain 1 to 20 criteria")
    out = []
    for i, item in enumerate(value):
        if not isinstance(item, dict) or set(item) - {"kind", "value"}:
            raise IntentContractError("a criterion has only kind and value")
        kind, text = item.get("kind"), item.get("value", "")
        if not isinstance(kind, str) or kind not in {"contains", "language", "json_object", "file_unchanged"}:
            raise IntentContractError("unsupported criterion kind")
        if not isinstance(text, str) or len(text) > 2000:
            raise IntentContractError("criterion value must be text of at most 2000 characters")
        if kind != "json_object" and not text.strip():
            raise IntentContractError("criterion value cannot be empty")
        if kind == "language" and text not in {"th", "en"}:
            raise IntentContractError("language checks support th and en script checks only")
        out.append({"id": f"C{i + 1}", "kind": kind, "value": text})
    return out


def _file(root: Path, relative: str) -> Path:
    from rct_control_plane.secret_paths import blocked_reason
    if not relative or Path(relative).is_absolute() or "\\" in relative or "\x00" in relative:
        raise IntentContractError("protected file must be a relative workspace path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise IntentContractError("protected file escapes the workspace")
    if blocked_reason(relative) or blocked_reason(path.relative_to(root.resolve()).as_posix()):
        raise IntentContractError("protected file is not available through the workspace read policy")
    return path


def _digest(path: Path) -> str:
    if not path.is_file():
        raise IntentContractError("a protected file must exist before the episode")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plan(goal: str, criteria: List[Dict[str, str]], root: Path) -> Dict[str, Any]:
    conditions, snapshots = [], {}
    for c in criteria:
        condition = {"criterion_id": c["id"], "kind": c["kind"], "value": c["value"],
                     "requires": "final answer" if c["kind"] != "file_unchanged" else "original workspace bytes"}
        if c["kind"] == "file_unchanged":
            snapshots[c["value"]] = _digest(_file(root, c["value"]))
        conditions.append(condition)
    return {"goal": goal, "criteria": criteria, "knowns": ["user-supplied goal", "explicit acceptance criteria"],
            "unknowns": ["whether the eventual output satisfies these criteria"],
            "components": [{"id": "produce", "output": "answer under the existing tool policy"},
                           {"id": "compare", "depends_on": ["produce"], "input": "answer and observed file bytes"}],
            "backward_chain": {"goal": goal, "necessary_conditions": conditions},
            "protected_sha256": snapshots, "workspace": str(root.resolve()),
            "limitations": "User-declared predicates, not a complete semantic decomposition. Language uses script checks."}


def compare(plan: Dict[str, Any], answer: str) -> List[Dict[str, Any]]:
    differences = []
    for c in plan["criteria"]:
        kind, expected = c["kind"], c["value"]
        if kind == "contains":
            ok = expected.casefold() in answer.casefold()
        elif kind == "json_object":
            try:
                ok = isinstance(json.loads(answer), dict)
            except (ValueError, TypeError):
                ok = False
        elif kind == "language":
            thai = len(re.findall(r"[\u0e01-\u0e5b]", answer))
            latin = len(re.findall(r"[A-Za-z]", answer))
            ok = (thai > 0 and thai >= latin / 3) if expected == "th" else (latin > 0 and thai == 0)
        else:
            try:
                ok = _digest(_file(Path(plan["workspace"]), expected)) == plan["protected_sha256"][expected]
            except (IntentContractError, OSError):
                ok = False
        if not ok:
            differences.append({"criterion_id": c["id"], "kind": kind, "expected": expected,
                                "observed": "criterion not satisfied"})
    return differences


class IntentContractStore:
    def __init__(self, persistence: Any, namespace: str):
        self.db, self.namespace = persistence, namespace
        with self.db._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS intent_contracts (id TEXT PRIMARY KEY, namespace TEXT NOT NULL, "
                         "state TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL)")

    def _encode(self, data: Dict[str, Any]) -> str:
        protected = audit_text.protect(self.namespace, {"data": data}, ("data",))
        if audit_text.sealing_on() and not audit_text.is_sealed_value(protected["data"]):
            raise IntentContractError("cannot persist intent text without its namespace key")
        return json.dumps(protected, ensure_ascii=False)

    def get(self, contract_id: str) -> Dict[str, Any]:
        with self.db._connect() as conn:
            row = conn.execute("SELECT state, version, payload FROM intent_contracts WHERE id=? AND namespace=?",
                               (contract_id, self.namespace)).fetchone()
        if row is None:
            raise IntentContractError("intent contract not found")
        try:
            data = audit_text.reveal(self.namespace, json.loads(row[2])["data"])
        except (ValueError, KeyError, TypeError) as exc:
            raise IntentContractError("intent contract text is erased or unavailable") from exc
        if not isinstance(data, dict):
            raise IntentContractError("intent contract text is erased or unavailable")
        return {**data, "id": contract_id, "state": row[0], "version": row[1]}

    def create(self, goal: str, criteria: Any, root: Path) -> Dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 20000:
            raise IntentContractError("goal must contain 1 to 20000 characters")
        plan = build_plan(goal, validate_criteria(criteria), root)
        contract_id = uuid.uuid4().hex
        data = {"original_goal": goal, "goal": goal, "plan": plan, "revisions": [], "differences": [], "safe_to_resume": True}
        with self.db._connect() as conn:
            conn.execute("INSERT INTO intent_contracts VALUES (?, ?, 'plan_ready', 1, ?)",
                         (contract_id, self.namespace, self._encode(data)))
        self.db.append_audit(entity_type="intent_contract", entity_id=contract_id, action="plan_ready", actor=self.namespace,
                             changes={"version": 1, "goal_sha256": hashlib.sha256(goal.encode()).hexdigest()})
        return self.get(contract_id)

    def transition(self, data: Dict[str, Any], state: str) -> Dict[str, Any]:
        payload = {k: v for k, v in data.items() if k not in {"id", "state", "version"}}
        with self.db._connect() as conn:
            changed = conn.execute("UPDATE intent_contracts SET state=?, version=version+1, payload=? "
                                   "WHERE id=? AND namespace=? AND version=? AND state=?",
                                   (state, self._encode(payload), data["id"], self.namespace, data["version"], data["state"])).rowcount
            if changed != 1:
                raise IntentContractError("intent contract changed; reload its current version")
        self.db.append_audit(entity_type="intent_contract", entity_id=data["id"], action=state, actor=self.namespace,
                             changes={"version": data["version"] + 1,
                                      "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()})
        return self.get(data["id"])

    def claim(self, contract_id: str, version: int, response: str = "", revised_goal: str | None = None,
              criteria: Any = None) -> Dict[str, Any]:
        if type(version) is not int or version < 1:
            raise IntentContractError("the current positive integer version is required")
        data = self.get(contract_id)
        if data["version"] != version or data["state"] not in {"plan_ready", "waiting_for_clarification"}:
            raise IntentContractError("intent contract is not ready at this version")
        if data["state"] == "waiting_for_clarification":
            if not isinstance(response, str) or not response.strip() or len(response) > 10000:
                raise IntentContractError("a nonempty user response is required before replanning")
            if not data["safe_to_resume"]:
                raise IntentContractError("prior side effects need reconciliation; automatic rerun is refused")
            goal = data["goal"] if revised_goal is None else revised_goal
            if not isinstance(goal, str) or not goal.strip() or len(goal) > 20000:
                raise IntentContractError("revised goal must contain 1 to 20000 characters")
            selected = validate_criteria(criteria) if criteria is not None else data["plan"]["criteria"]
            data["revisions"].append({"from_version": version, "goal": goal, "user_response": response, "criteria": selected})
            data["goal"] = goal
            plan = build_plan(goal, selected, Path(data["plan"]["workspace"]))
            for path, digest in data["plan"]["protected_sha256"].items():
                if path in plan["protected_sha256"]:
                    plan["protected_sha256"][path] = digest
            data["plan"], data["differences"] = plan, []
            return self.transition(data, "plan_ready")
        elif response or revised_goal is not None or criteria is not None:
            raise IntentContractError("revise only after a clarification request")
        return self.transition(data, "running")
