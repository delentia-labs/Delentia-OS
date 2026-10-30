"""Durable, explicit acceptance contracts; not an oracle for arbitrary intent.

The opt-in path retains plans, original intent and user-confirmed revisions.
A signature, a timeout and a model's success claim are not clarification.
"""
from __future__ import annotations

import hashlib
import copy
import json
import re
import uuid
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

from rct_control_plane import audit_text

# Keep the first contract release on inspectable answer/read workflows. Pending
# action approval/resume must carry the contract before enabling effect tools.
READ_ONLY_TOOLS = frozenset({"delentia_read_repo_file", "delentia_search_repo_files", "delentia_recall", "delentia_search_sessions",
                             "delentia_expand_tool_output"})
SCHEMA_VERSION = 1


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
    # Lexical policy only; actual acquisition must use no-follow descriptors.
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise IntentContractError("protected file escapes the workspace or has ambiguous components")
    if blocked_reason(relative):
        raise IntentContractError("protected file is not available through the workspace read policy")
    return root.joinpath(*parts)


def _digest(root: Path, relative: str) -> str:
    """Bounded regular-file hashing, refusing symlinks at every relative level.

    Fail closed without POSIX no-follow support. This observes bytes, not an
    atomic filesystem snapshot or proof of authorship.
    """
    import os
    import stat
    from rct_control_plane.verified_budget import supports_verified_reads
    _file(root, relative)
    if not supports_verified_reads():
        raise IntentContractError("protected files require POSIX no-follow reading support")
    limit = 64 * 1024 * 1024
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            parts = relative.split("/")
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            try:
                before = os.fstat(child)
                if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                    raise IntentContractError("protected file must be regular and at most 64 MiB")
                result = hashlib.sha256()
                remaining = limit + 1
                while remaining:
                    block = os.read(child, min(remaining, 65536))
                    if not block:
                        break
                    remaining -= len(block)
                    result.update(block)
                after = os.fstat(child)
                if not remaining or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise IntentContractError("protected file changed during reading or exceeds limit")
                return result.hexdigest()
            finally:
                os.close(child)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise IntentContractError("protected file cannot be safely opened in the workspace") from exc


def build_plan(goal: str, criteria: List[Dict[str, str]], root: Path, planning_context: Any = None) -> Dict[str, Any]:
    from rct_control_plane.derived_plan import DERIVE_REQUEST, derive_context, annotate
    semantic_metadata = None
    if isinstance(planning_context, dict) and "semantic_plan" in planning_context:
        from rct_control_plane.semantic_plan import compile_request
        planning_context, semantic_metadata = compile_request(goal, criteria, planning_context)
    derived = type(planning_context) is dict and planning_context == DERIVE_REQUEST and planning_context.get("derive_from_criteria") is True
    if derived:
        planning_context = derive_context(goal, criteria)
    conditions, snapshots = [], {}
    for c in criteria:
        condition = {"criterion_id": c["id"], "kind": c["kind"], "value": c["value"],
                     "requires": "final answer" if c["kind"] != "file_unchanged" else "original workspace bytes"}
        if c["kind"] == "file_unchanged":
            snapshots[c["value"]] = _digest(root, c["value"])
        conditions.append(condition)
    plan = {"goal": goal, "criteria": criteria, "knowns": ["user-supplied goal", "explicit acceptance criteria"],
            "unknowns": ["whether the eventual output satisfies these criteria"],
            "components": [{"id": "produce", "output": "answer under the existing tool policy"},
                           {"id": "compare", "depends_on": ["produce"], "input": "answer and observed file bytes"}],
            "backward_chain": {"goal": goal, "necessary_conditions": conditions},
            "protected_sha256": snapshots, "workspace": str(root.resolve()),
            "limitations": "User-declared predicates, not a complete semantic decomposition. Language uses script checks."}
    if planning_context is not None:
        from rct_control_plane.rct_plan import validate_context, apply_context
        apply_context(plan, validate_context(planning_context, {c["id"] for c in criteria}))
        if derived:
            annotate(plan)
        if semantic_metadata is not None:
            from rct_control_plane.semantic_plan import annotate as annotate_semantic
            if "quote_evidence" in semantic_metadata:
                from rct_control_plane.verified_budget import supports_verified_reads
                if not supports_verified_reads():
                    raise IntentContractError("verified quote execution requires POSIX no-follow reading support")
                relative = semantic_metadata["quote_evidence"]["relative_path"]
                _file(root, relative)
                if ".." in Path(relative).parts:
                    raise IntentContractError("verified quote path cannot contain parent traversal")
            annotate_semantic(plan, semantic_metadata)
            if semantic_metadata.get("executor") == "verified_budget_v1":
                from rct_control_plane.budget_execution import compile_program
                plan["execution_program"] = compile_program(plan)
    return plan


def plan_digest(plan: dict) -> str:
    """Binding material for review/reconciliation; NOT a signature or permission."""
    return hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def compare(plan: Dict[str, Any], answer: str) -> List[Dict[str, Any]]:
    differences = []
    for c in plan["criteria"]:
        kind, expected = c["kind"], c["value"]
        if kind == "contains":
            # Canonically equivalent Unicode must not fail an exact-text
            # criterion. NFC preserves Thai SARA AM; NFKC changes its spelling.
            ok = unicodedata.normalize("NFC", expected).casefold() in unicodedata.normalize("NFC", answer).casefold()
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
                ok = _digest(Path(plan["workspace"]), expected) == plan["protected_sha256"][expected]
            except (IntentContractError, OSError):
                ok = False
        if not ok:
            differences.append({"criterion_id": c["id"], "kind": kind, "expected": expected,
                                "observed": "criterion not satisfied"})
    return differences


class IntentRequestConflict(IntentContractError):
    """A request key already belongs to different input in this namespace."""


class IntentContractStore:
    def __init__(self, persistence: Any, namespace: str):
        self.db, self.namespace = persistence, namespace
        with self.db._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS intent_contracts (id TEXT PRIMARY KEY, namespace TEXT NOT NULL, "
                         "state TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL)")

            conn.execute("CREATE TABLE IF NOT EXISTS intent_request_keys (namespace TEXT NOT NULL, "
                         "key_sha256 TEXT NOT NULL, request_sha256 TEXT NOT NULL, contract_id TEXT NOT NULL, "
                         "PRIMARY KEY(namespace, key_sha256))")

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
        if row[0] == "erased":
            raise IntentContractError("intent contract text is erased or unavailable")
        try:
            data = audit_text.reveal(self.namespace, json.loads(row[2])["data"])
        except (ValueError, KeyError, TypeError) as exc:
            raise IntentContractError("intent contract text is erased or unavailable") from exc
        if not isinstance(data, dict) or not isinstance(data.get("plan"), dict):
            raise IntentContractError("intent contract text is erased or unavailable")
        if "plan_sha256" in data and data["plan_sha256"] != plan_digest(data["plan"]):
            raise IntentContractError("intent plan digest mismatch; execution refused")
        from rct_control_plane.budget_execution import validate_executor
        validate_executor(data["plan"])
        if "execution_receipts" in data:
            from rct_control_plane.verified_budget import validate_receipts
            try:
                validate_receipts(data["plan"], contract_id, self.namespace, data["execution_receipts"])
            except (ValueError, TypeError, KeyError) as exc:
                raise IntentContractError("invalid stored execution receipts") from exc
        # Pre-versioned contracts from the first release are schema 1. Future
        # schemas must never silently run under older continuation semantics.
        version = data.get("schema_version", 1)
        if type(version) is not int or version != SCHEMA_VERSION:
            raise IntentContractError("unsupported intent contract schema version")
        data["schema_version"] = version
        plan_version = data["plan"].get("plan_schema_version", 1)
        if type(plan_version) is not int or plan_version not in (1, 2):
            raise IntentContractError("unsupported planning schema version")
        if plan_version == 2:
            from rct_control_plane.rct_plan import validate_context
            criteria = data["plan"].get("criteria", [])
            if not criteria or any(not isinstance(c, dict) or "id" not in c for c in criteria):
                raise IntentContractError("invalid stored planning criteria")
            validate_context(data.get("planning_context"), {c["id"] for c in criteria})
        return {**data, "id": contract_id, "state": row[0], "version": row[1]}

    def export(self, contract_id: str) -> Dict[str, Any]:
        """Explicit plaintext export for the owner; never includes keys.

        This is a portable inspection artifact, not an import/execution token.
        It contains personal text and must not be shared as a public run log.
        """
        return {"format": "delentia-intent-contract-export-1", "namespace": self.namespace,
                "contains_personal_text": True, "executable": False, "contract": self.get(contract_id)}

    def create(self, goal: str, criteria: Any, root: Path, planning_context: Any = None, *, service_binding: dict | None = None, request_id: str | None = None) -> Dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 20000:
            raise IntentContractError("goal must contain 1 to 20000 characters")
        key_hash = request_hash = None
        if request_id is not None:
            import re
            if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id):
                raise IntentContractError("request_id must be 1..128 ASCII identifier characters")
            key_hash = hashlib.sha256(request_id.encode("ascii")).hexdigest()
            request_hash = plan_digest({"goal": goal, "criteria": criteria,
                "workspace": str(root.resolve()), "planning_context": planning_context, "service_binding": service_binding})
            with self.db._connect() as conn:
                prior = conn.execute("SELECT request_sha256, contract_id FROM intent_request_keys WHERE namespace=? AND key_sha256=?",
                                     (self.namespace, key_hash)).fetchone()
            if prior is not None:
                if prior[0] != request_hash:
                    raise IntentRequestConflict("request_id already belongs to different input")
                return self.get(prior[1])
        plan = build_plan(goal, validate_criteria(criteria), root, planning_context)
        contract_id = uuid.uuid4().hex
        data = {"schema_version": SCHEMA_VERSION, "original_goal": goal, "goal": goal, "plan": plan,
                "revisions": [], "differences": [], "safe_to_resume": True, "plan_sha256": plan_digest(plan)}
        if service_binding is not None:
            data["service_binding"] = copy.deepcopy(service_binding)
        if planning_context is not None:
            from rct_control_plane.rct_plan import validate_context
            if plan.get("planning_origin") == "bounded_semantic_rules":
                from rct_control_plane.semantic_plan import context_from_plan
                data["planning_request"] = copy.deepcopy(planning_context)
                planning_context = context_from_plan(plan)
            if plan.get("planning_origin") == "criterion_derived":
                from rct_control_plane.derived_plan import derive_context
                data["planning_request"] = {"derive_from_criteria": True}
                planning_context = derive_context(goal, plan["criteria"])
            data["planning_context"] = validate_context(planning_context, {c["id"] for c in plan["criteria"]})
        state = "waiting_for_input" if plan.get("clarification_questions") else "plan_ready"
        existing_id = None
        with self.db._connect() as conn:
            # Serialize the key lookup and both INSERTs across API workers.
            # A failed transaction leaves neither an orphan key nor a plan.
            conn.execute("BEGIN IMMEDIATE")
            if key_hash is not None:
                prior = conn.execute("SELECT request_sha256, contract_id FROM intent_request_keys WHERE namespace=? AND key_sha256=?",
                                     (self.namespace, key_hash)).fetchone()
                if prior is not None:
                    if prior[0] != request_hash:
                        raise IntentRequestConflict("request_id already belongs to different input")
                    existing_id = prior[1]
            if existing_id is None:
                conn.execute("INSERT INTO intent_contracts VALUES (?, ?, ?, 1, ?)",
                             (contract_id, self.namespace, state, self._encode(data)))
                if key_hash is not None:
                    conn.execute("INSERT INTO intent_request_keys VALUES (?, ?, ?, ?)",
                                 (self.namespace, key_hash, request_hash, contract_id))
        if existing_id is not None:
            return self.get(existing_id)
        self.db.append_audit(entity_type="intent_contract", entity_id=contract_id, action=state, actor=self.namespace,
                             changes={"version": 1, "goal_sha256": hashlib.sha256(goal.encode()).hexdigest()})
        return copy.deepcopy({**data, "id": contract_id, "state": state, "version": 1})

    def transition(self, data: Dict[str, Any], state: str) -> Dict[str, Any]:
        # Freeze this writer's receipt before commit/audit. A second reader may
        # advance the row immediately after commit; returning get() could then
        # lend that later writer's running state/version to this caller.
        payload = copy.deepcopy({k: v for k, v in data.items() if k not in {"id", "state", "version"}})
        payload["plan_sha256"] = plan_digest(payload["plan"])
        with self.db._connect() as conn:
            changed = conn.execute("UPDATE intent_contracts SET state=?, version=version+1, payload=? "
                                   "WHERE id=? AND namespace=? AND version=? AND state=?",
                                   (state, self._encode(payload), data["id"], self.namespace, data["version"], data["state"])).rowcount
            if changed != 1:
                raise IntentContractError("intent contract changed; reload its current version")
        self.db.append_audit(entity_type="intent_contract", entity_id=data["id"], action=state, actor=self.namespace,
                             changes={"version": data["version"] + 1,
                                      "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()})
        return {**payload, "id": data["id"], "state": state, "version": data["version"] + 1}

    def claim(self, contract_id: str, version: int, response: str = "", revised_goal: str | None = None,
              criteria: Any = None, answers: Any = None) -> Dict[str, Any]:
        if type(version) is not int or version < 1:
            raise IntentContractError("the current positive integer version is required")
        data = self.get(contract_id)
        if data["version"] != version or data["state"] not in {"plan_ready", "waiting_for_clarification", "waiting_for_input"}:
            raise IntentContractError("intent contract is not ready at this version")
        if data["state"] == "waiting_for_input":
            questions = {q["id"] for q in data["plan"]["clarification_questions"]}
            if (not isinstance(answers, dict) or set(answers) != questions
                    or any(not isinstance(v, str) or not v.strip() or len(v) > 4000 for v in answers.values())):
                raise IntentContractError("answers must supply nonempty text for each critical unknown id")
            if revised_goal is not None or criteria is not None or response:
                raise IntentContractError("answer critical inputs before revising intent")
            if data["plan"].get("planning_origin") == "bounded_semantic_rules" and "budget" in answers:
                from rct_control_plane.semantic_plan import validate_budget
                validate_budget(answers["budget"])
            context = data["planning_context"]
            for unknown in context["unknowns"]:
                if unknown["id"] in answers:
                    unknown["answer"] = answers[unknown["id"]].strip()
            data["revisions"].append({"from_version": version, "user_answers": answers, "provenance": "confirmed_user_input"})
            for key in ("execution_receipts", "execution_report", "execution_status"):
                data.pop(key, None)
            semantic_metadata = data["plan"].get("semantic_planning")
            data["plan"] = build_plan(data["goal"], data["plan"]["criteria"], Path(data["plan"]["workspace"]), context)
            if semantic_metadata is not None:
                from rct_control_plane.semantic_plan import annotate as annotate_semantic
                annotate_semantic(data["plan"], semantic_metadata)
            # Replanning must not reset preservation baselines.
            prior = self.get(contract_id)["plan"]["protected_sha256"]
            data["plan"]["protected_sha256"].update(prior)
            return self.transition(data, "plan_ready")
        if answers is not None:
            raise IntentContractError("answers are accepted only while waiting for initial input")
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
            for key in ("execution_receipts", "execution_report", "execution_status"):
                data.pop(key, None)
            request = data.get("planning_request", data.get("planning_context"))
            plan = build_plan(goal, selected, Path(data["plan"]["workspace"]), request)
            if data.get("planning_request"):
                from rct_control_plane.rct_plan import validate_context
                if plan.get("planning_origin") == "bounded_semantic_rules":
                    from rct_control_plane.semantic_plan import context_from_plan
                    context = context_from_plan(plan)
                else:
                    from rct_control_plane.derived_plan import derive_context
                    context = derive_context(goal, selected)
                data["planning_context"] = validate_context(context, {c["id"] for c in selected})
            for path, digest in data["plan"]["protected_sha256"].items():
                if path in plan["protected_sha256"]:
                    plan["protected_sha256"][path] = digest
            data["plan"], data["differences"] = plan, []
            return self.transition(data, "waiting_for_input" if plan.get("clarification_questions") else "plan_ready")
        elif response or revised_goal is not None or criteria is not None:
            raise IntentContractError("revise only after a clarification request")
        return self.transition(data, "running")
