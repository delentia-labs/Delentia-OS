"""
Round 61: trajectories - what an episode actually did, kept as data a person can evaluate with (and later train with), strictly opt-in.

Hermes can generate and compress batches of trajectories for training tool-calling models. The runtime already records WHAT happened to each episode (the audit trail and the experiment runs hold hashes,
counts and verdicts) but not the steps themselves: the arguments and results are deliberately not stored, because they may hold personal data or text from a page. For measuring a model, or building a
labelled set like the one VERIFY was measured on, the steps are exactly what is missing. So this module writes them - but only when the owner switches it on (`DELENTIA_RECORD_TRAJECTORIES=1`), only to a file
inside the data home (nothing leaves the machine), with secrets and contact details redacted, every text clipped, the person's namespace stored as a hash, and every episode that read outside text marked
`tainted` so an export can leave it out.

  record(result, namespace, model)   called by the governed loop at the end of an episode (never raises)
  export(path, ...)                  JSON Lines for the owner: filters for verified-only and untainted-only
  stats()                            how many, how many verified / tainted, which tools

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

ENV = "DELENTIA_RECORD_TRAJECTORIES"
MAX_TEXT = 2000
MAX_STEPS = 40

_SECRETS = re.compile(
    r"sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)|"
    r"(?i:bearer)\s+[A-Za-z0-9._~+/=-]{16,}|(?i:(?:api[_-]?key|token|secret|password|passwd|pwd)\"?\s*[:=]\s*\"?)[^\s\"',;]{6,}", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_LONG_NUMBER = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w.])")


def enabled() -> bool:
    return (os.environ.get(ENV) or "").strip().lower() in ("1", "on", "true", "yes")


def redact(text: Any, limit: int = MAX_TEXT) -> str:
    """Secrets, e-mail addresses and long digit sequences (phone, card, ID numbers) replaced by markers; clipped."""
    value = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    value = value[: max(limit * 4, 8000)]                                  # patterns run only on what will be kept (and never on unbounded input)
    value = _SECRETS.sub("[secret]", value)
    value = _EMAIL.sub("[email]", value)
    value = _LONG_NUMBER.sub("[number]", value)
    return value if len(value) <= limit else value[:limit] + f"...[cut, {len(value) - limit} more characters]"


def directory() -> Path:
    from rct_control_plane import data_home
    home = data_home.data_home()
    base = home if home is not None else Path.home() / ".delentia"
    target = base / "trajectories"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _person(namespace: str) -> str:
    return "p-" + hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:12]


def build(result: Dict[str, Any], namespace: str, model: str = "") -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    for s in (result.get("steps") or [])[:MAX_STEPS]:
        if not s.get("tool_name"):
            continue
        steps.append({"tool": s["tool_name"], "args": redact(s.get("tool_args") or {}, 600), "result": redact(s.get("tool_result"), MAX_TEXT)})
    verification = result.get("intent_verification") or {}
    return {
        "id": "traj-" + hashlib.sha256(f"{namespace}{time.time()}{result.get('goal')}".encode("utf-8")).hexdigest()[:12],
        "at": time.time(), "person": _person(namespace), "model": model,
        "goal": redact(result.get("goal") or ""), "steps": steps, "answer": redact(result.get("final_answer") or ""),
        "stopped_reason": result.get("stopped_reason"), "iterations": result.get("iterations"),
        "verified": bool(verification.get("aligned_with_intent")), "verification": {k: verification.get(k) for k in ("similarity_score", "declined", "grounding") if k in verification},
        "tainted": bool((result.get("taint") or {}).get("tainted")), "route": (result.get("route") or {}).get("path"),
        "cost_usd": (result.get("cost") or {}).get("cost_usd"), "tokens": (result.get("cost") or {}).get("total_tokens"),
    }


def record(result: Dict[str, Any], namespace: str, model: str = "") -> Optional[str]:
    """Append one episode to today's file. Returns the trajectory id, or None when recording is off or failed (it never raises)."""
    if not enabled():
        return None
    try:
        row = build(result, namespace, model)
        path = directory() / (time.strftime("%Y-%m-%d", time.gmtime()) + ".jsonl")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row["id"]
    except Exception:                                                  # noqa: BLE001
        return None


def _rows(folder: Optional[Path] = None) -> Iterator[Dict[str, Any]]:
    for path in sorted((folder or directory()).glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def export(out_path: str, *, verified_only: bool = False, exclude_tainted: bool = False, since: Optional[float] = None, folder: Optional[Path] = None) -> Dict[str, Any]:
    """Write the recorded trajectories to `out_path` as JSON Lines (refuses to overwrite an existing file: nothing is deleted or replaced)."""
    target = Path(out_path)
    if target.exists():
        raise FileExistsError(f"{target} already exists; choose a new file name")
    kept = skipped = 0
    with target.open("w", encoding="utf-8") as handle:
        for row in _rows(folder):
            if (verified_only and not row.get("verified")) or (exclude_tainted and row.get("tainted")) or (since is not None and float(row.get("at") or 0) < since):
                skipped += 1
                continue
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            kept += 1
    return {"written": kept, "skipped": skipped, "path": str(target)}


def stats(folder: Optional[Path] = None) -> Dict[str, Any]:
    total = verified = tainted = 0
    tools: Dict[str, int] = {}
    stops: Dict[str, int] = {}
    for row in _rows(folder):
        total += 1
        verified += bool(row.get("verified"))
        tainted += bool(row.get("tainted"))
        stops[str(row.get("stopped_reason"))] = stops.get(str(row.get("stopped_reason")), 0) + 1
        for s in row.get("steps", []):
            tools[s["tool"]] = tools.get(s["tool"], 0) + 1
    return {"episodes": total, "verified": verified, "tainted": tainted, "stopped": stops, "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1]))}
