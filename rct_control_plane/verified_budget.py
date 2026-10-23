"""Read-only, dependency-enforced quote verifier. Document bytes are not vendor truth.

Receipts are local hash-linked working state, not signatures or off-host witnesses.
Only the governed read callback can supply evidence; generation is unnecessary.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from decimal import Decimal, Context, localcontext
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from rct_control_plane.rct_plan import PlanItem

MAX_BYTES = 20000


def supports_verified_reads() -> bool:
    return os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")


class QuoteEvidence(PlanItem):
    relative_path: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Quote(PlanItem):
    schema_version: Literal[1]
    total: str = Field(max_length=20, pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$")
    currency: Literal["THB", "USD", "EUR"]
    total_is_final: bool


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("non-finite JSON constant")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def current_bytes(root: Path, relative: str) -> bytes:
    """Bounded POSIX read, refusing symlink components and non-regular files."""
    from rct_control_plane.intent_contract import _file
    _file(root, relative)  # workspace/secret-path policy, without reading contents
    parts = Path(relative).parts
    if any(part in {".", ".."} for part in parts) or not supports_verified_reads():
        raise ValueError("quote path/platform unavailable for verified reading")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor);descriptor = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        try:
            if not stat.S_ISREG(os.fstat(child).st_mode):
                raise ValueError("quote must be a regular file")
            with os.fdopen(child, "rb", closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("quote exceeds verified input limit")
            return raw
        finally:
            os.close(child)
    finally:
        os.close(descriptor)


def validate_receipts(plan, contract_id, namespace, receipts):
    from rct_control_plane.intent_contract import IntentContractError, plan_digest
    if not isinstance(receipts, list) or len(receipts) > 50:
        raise IntentContractError("invalid execution receipt list")
    import re
    graph = {node["id"]: node for node in plan["components"]}
    completed = set();previous = "0" * 64;run_version = None
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise IntentContractError("invalid execution receipt")
        data = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        node = graph.get(data.get("component_id"))
        if (node is None or node["id"] in completed or set(node["depends_on"]) - completed
                or data.get("contract_id") != contract_id or data.get("namespace") != namespace
                or data.get("plan_sha256") != plan_digest(plan) or data.get("previous_sha256") != previous
                or data.get("ordinal") != len(completed) + 1 or receipt.get("receipt_sha256") != digest(data)
                or type(data.get("run_version")) is not int or data["run_version"] < 1
                or type(data.get("ordinal")) is not int or type(data.get("recorded_ns")) is not int
                or data["recorded_ns"] < 1 or not isinstance(data.get("output_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", data["output_sha256"])
                or not isinstance(data.get("output"), dict) or data["output_sha256"] != digest(data["output"])):
            raise IntentContractError("execution receipt binding or dependency mismatch")
        if run_version is not None and data["run_version"] != run_version:
            raise IntentContractError("execution receipts belong to different claims")
        run_version = data["run_version"]
        completed.add(node["id"]);previous = receipt["receipt_sha256"]


class BudgetPipeline:
    def __init__(self, contract, namespace):
        self.contract = contract;self.namespace = namespace
        self.plan = contract["plan"];self.binding = self.plan["semantic_planning"]["quote_evidence"]
        self.receipts = [];self.report = None;self.error = None

    def complete(self, node_id, output):
        graph = {node["id"]: node for node in self.plan["components"]}
        done = {r["component_id"] for r in self.receipts}
        node = graph[node_id]
        if node_id in done or set(node["depends_on"]) - done:
            raise ValueError("component prerequisites not completed")
        answers = {u["id"]: u["answer"] for u in self.plan["unknowns"]}
        if any(not answers.get(key) for key in node["requires"]):
            raise ValueError("component critical input unavailable")
        receipt = {"component_id": node_id, "contract_id": self.contract["id"], "namespace": self.namespace,
            "run_version": self.contract["version"], "plan_sha256": self.contract["plan_sha256"],
            "ordinal": len(self.receipts) + 1, "previous_sha256": self.receipts[-1]["receipt_sha256"] if self.receipts else "0" * 64,
            "output": output, "output_sha256": digest(output), "recorded_ns": time.time_ns()}
        receipt["receipt_sha256"] = digest(receipt)
        self.receipts.append(receipt)

    def observe(self, tool, arguments, result):
        if tool != "delentia_read_repo_file" or arguments.get("relative_path") != self.binding["relative_path"]:
            self.error = "unexpected evidence operation";return
        try:
            if not isinstance(result, dict) or result.get("truncated") is not False or result.get("path") != self.binding["relative_path"]:
                raise ValueError("missing, withheld or truncated source")
            raw = result["content_text"].encode("utf-8")
            if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != self.binding["sha256"]:
                raise ValueError("observed source hash differs from plan")
            value = strict_json(raw.decode("utf-8"))
            if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
                raise ValueError("invalid quote version")
            quote = Quote.model_validate(value)
            if quote.total_is_final is not True or Decimal(quote.total) > Decimal("1e15"):
                raise ValueError("quote total/scope unresolved")
            self.complete("inspect_sources", {"evidence_status": "observed_bytes", "relative_path": result["path"],
                "sha256": self.binding["sha256"], "tool_result_sha256": digest(result)})
            from rct_control_plane.semantic_plan import validate_budget
            budget = next(u["answer"] for u in self.plan["unknowns"] if u["id"] == "budget")
            validate_budget(budget)
            import re
            currency = re.search(r"THB|USD|EUR|บาท", budget, re.I)[0].upper().replace("บาท", "THB")
            limit = Decimal(re.sub(r"THB|USD|EUR|บาท", "", budget, flags=re.I).strip().replace(",", ""))
            if quote.currency != currency:
                raise ValueError("currency mismatch; no implicit FX conversion")
            total = Decimal(quote.total)
            # Other application code may change Decimal's ambient precision,
            # exponent limits or traps. Our bounded monetary subtraction must
            # not inherit those settings or silently round a remaining amount.
            with localcontext(Context(prec=40)):
                self.report = {"quote_total": format(total, ".2f"), "budget_limit": format(limit, ".2f"),
                    "currency": currency, "remaining": format(limit - total, ".2f"), "within_budget": total <= limit,
                    "source": result["path"], "evidence_sha256": self.binding["sha256"]}
            self.complete("compare_budget", self.report)
        except (ValueError, TypeError, KeyError, StopIteration, ValidationError) as exc:
            self.error = str(exc)[:500]

    def decision(self):
        if not self.receipts and self.error is None:
            return {"action": "call_tool", "tool_name": "delentia_read_repo_file",
                "tool_args": {"relative_path": self.binding["relative_path"], "max_bytes": MAX_BYTES},
                "reasoning": "Read the pinned quote through the governed tool before dependent computation."}
        return {"action": "finish", "final_answer": json.dumps(self.report if self.error is None else {"unresolved": self.error}, ensure_ascii=False, sort_keys=True),
                "reasoning": "Deterministic decimal verification; no model generation.", "tool_name": None, "tool_args": {}}

    def finish(self, answer, differences):
        if self.error or self.report is None:
            return [{"kind": "verified_budget", "observed": self.error or "missing governed source receipt"}]
        try:
            raw = current_bytes(Path(self.plan["workspace"]), self.binding["relative_path"])
            if hashlib.sha256(raw).hexdigest() != self.binding["sha256"]:
                raise ValueError("source changed after observation")
            if digest(strict_json(answer)) != digest(self.report):
                raise ValueError("answer differs from the verified arithmetic report")
            self.complete("compose_answer", self.report)
            for node in self.plan["components"]:
                if node["id"].startswith("prepare_"):
                    self.complete(node["id"], self.report)
                elif node["id"].startswith("check_"):
                    cid = node["id"].removeprefix("check_")
                    if not any(d.get("criterion_id") == cid for d in differences):
                        self.complete(node["id"], {"criterion_id": cid, "satisfied": True})
            validate_receipts(self.plan, self.contract["id"], self.namespace, self.receipts)
            if len(self.receipts) != len(self.plan["components"]):
                raise ValueError("not all planned components completed")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return [{"kind": "verified_budget", "observed": str(exc)[:500]}]
        return []
