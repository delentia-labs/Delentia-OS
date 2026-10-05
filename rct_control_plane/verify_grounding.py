"""
Round 61: a second look at an episode's final answer, from the EVIDENCE, not from word overlap.

RCT-7 step 7 in the loop used to be one test: is the answer lexically similar to the goal, and does it not decline? Two ways that is wrong, both seen: a refusal repeats the goal's words
(fixed in Round 50 by a decline pattern), and a confident answer that invented its facts also repeats the goal's words. VERIFY decides what the agent LEARNS (a skill is saved only from an
aligned episode), so the mistakes that matter are the answers that look right and are not.

Three checks, all deterministic, none uses a model:

  * `ungrounded_values` - the answer states a number, an address, a file path or an e-mail that appears nowhere in the evidence (the goal, the earlier turns of the conversation, every
    tool argument and every tool result). Numbers a goal's own arithmetic produces are allowed ("what is 17 times 23" -> 391).
  * `claims_action_without_effect` - the goal asked for an action (create, save, delete, send, schedule, remember ...), the answer says it was done, and no tool that can do it ran
    without an error.
  * `claims_success_after_error` - every tool result of the episode was an error and the answer reports success anyway.

A flag means "do not learn this as a skill and do not warm-reuse it"; it never hides the answer from the person. The measurement that justifies each check, and its false rejects, is in
scripts/measure_verify.py (a labelled set, a development half used to tune and a holdout half used once).

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Set

ENV = "DELENTIA_VERIFY_GROUNDING"

_URL = re.compile(r"https?://[^\s)>\]\"']+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_PATH = re.compile(r"(?<![\w/])(?:[\w.-]+[/\\])+[\w.-]+\.\w{1,6}\b|(?<![\w/.])[\w-]+\.(?:py|md|txt|json|toml|yaml|yml|db|ts|tsx|js|log|csv|sh|ini|cfg)\b")
_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")
_ARITH_WORDS = re.compile(r"\d\s*(?:[-+*/x×÷^]|plus|minus|times|divided|multiplied|squared|%)\s*\d|\b(?:sum|total|average|mean|product|difference|percent|how many|how much|count)\b|บวก|ลบ|คูณ|หาร|รวม|เฉลี่ย|กี่|จำนวน", re.IGNORECASE)

_ACTION_GOAL = re.compile(
    r"\b(create|make|write|save|store|delete|remove|erase|send|post|run|execute|schedule|remind|remember|patch|edit|update|rename|move|copy|install|deploy|add)\b|"
    r"สร้าง|เขียน|บันทึก|ลบ|ส่ง|รัน|ตั้งเตือน|เตือน|จำ|แก้|ย้าย|คัดลอก|เพิ่ม", re.IGNORECASE)
_SUCCESS_CLAIM = re.compile(
    r"\b(done|created|saved|written|wrote|deleted|removed|sent|scheduled|updated|completed|stored|remembered|added|renamed|moved|copied|patched|successfully|i have (?:created|saved|written|deleted|sent|scheduled|added))\b|"
    r"เรียบร้อย|สำเร็จ|แล้ว", re.IGNORECASE)
# tools whose successful run IS the effect a goal like that asks for
EFFECT_TOOLS = frozenset({
    "delentia_write_repo_file", "delentia_patch_repo_file", "delentia_save_exchange_file", "delentia_remember", "delentia_schedule_reminder",
    "delentia_cron_create", "delentia_cron_delete", "delentia_run_sandboxed_command", "delentia_create_worktree", "delentia_remove_worktree",
    "delentia_export_session_state", "delentia_spawn_subagents", "delentia_delegate", "delentia_run_forged_tool", "delentia_speak", "delentia_generate_image",
})
_ERROR_KEYS = ("error", "errors", "blocked", "refused", "pending_approval", "fdia_blocked", "paused", "stuck")
_MAX_EVIDENCE = 400_000


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).lower().replace("\\", "/")


def _num_key(raw: str) -> str:
    raw = raw.replace(",", "")
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw


def _is_error(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if any(result.get(k) for k in _ERROR_KEYS):
        return True
    return result.get("success") is False or result.get("ok") is False or result.get("status") in ("error", "failed")


def _evidence(goal: str, steps: Iterable[Dict[str, Any]], conversation: str) -> str:
    parts: List[str] = [goal or "", conversation or ""]
    for step in steps or []:
        for key in ("tool_args", "tool_result"):
            value = step.get(key)
            if value is None:
                continue
            try:
                parts.append(json.dumps(value, ensure_ascii=False, default=str))
            except Exception:                                      # noqa: BLE001
                parts.append(str(value))
    return _norm(" ".join(parts))[:_MAX_EVIDENCE]


def _arithmetic_results(goal: str) -> Set[str]:
    """Numbers a goal's own arithmetic can produce (a model that answers '391' to '17 times 23' invented nothing)."""
    nums = [float(n.replace(",", "")) for n in _NUMBER.findall(goal or "")][:8]
    out: Set[str] = set()

    def add(x: float) -> None:
        if abs(x) < 1e15:
            out.add(_num_key(("%.6f" % x)))
            out.add(_num_key(str(int(round(x)))) if abs(x - round(x)) < 1e-9 else _num_key("%.2f" % x))
    for i, a in enumerate(nums):
        for b in nums[i + 1:]:
            for value in (a + b, a - b, b - a, a * b, a ** 2, b ** 2):
                add(value)
            if b:
                add(a / b)
            if a:
                add(b / a)
    if nums:
        add(sum(nums))
        prod = 1.0
        for n in nums:
            prod *= n
        add(prod)
        add(sum(nums) / len(nums))
        for n in nums:
            add(n ** 2)
    return out


def ungrounded_values(goal: str, answer: str, steps: Iterable[Dict[str, Any]], conversation: str = "") -> List[str]:
    """Values the answer states that nothing in the evidence contains."""
    evidence = _evidence(goal, steps, conversation)
    text = str(answer or "")
    found: List[str] = []
    for url in _URL.findall(text):
        url = url.rstrip(".,;:!?")
        if _norm(url) not in evidence:
            found.append(url)
    stripped = _URL.sub(" ", text)
    for mail in _EMAIL.findall(stripped):
        if _norm(mail) not in evidence:
            found.append(mail)
    stripped = _EMAIL.sub(" ", stripped)
    for path in _PATH.findall(stripped):
        if _norm(path) not in evidence:
            found.append(path)
    stripped = _PATH.sub(" ", stripped)
    allowed = _arithmetic_results(goal)
    ev_numbers = {_num_key(n) for n in _NUMBER.findall(evidence)}
    for raw in _NUMBER.findall(stripped):
        key = _num_key(raw)
        if len(key.replace(".", "")) < 2:                           # a single digit is a count or a list marker, not a fact worth checking
            continue
        if key in ev_numbers or key in allowed:
            continue
        found.append(raw)
    unique: List[str] = []
    for value in found:
        if value not in unique:
            unique.append(value)
    return unique[:20]


def _effect_ran(steps: Iterable[Dict[str, Any]]) -> bool:
    return any(s.get("tool_name") in EFFECT_TOOLS and not _is_error(s.get("tool_result")) and s.get("tool_result") is not None for s in steps or [])


_WORD = re.compile(r"[a-z][a-z0-9_-]{3,}|\d+(?:\.\d+)+")
_STOP = frozenset("that this with from have been were will would there their about which when what your says said they them then than also into over some more most such only does file files tool tools result results".split())


def evidence_support(answer: str, steps: Iterable[Dict[str, Any]]) -> bool:
    """True when the answer reuses at least two distinct content words (or a dotted number such as a version) that a SUCCESSFUL tool result contains. Similarity to the goal is a poor
    test for a short, correct answer ("It says to water plants early"); sharing the tool's own words is a better one. An answer with no tool behind it can never be supported."""
    texts = []
    for step in steps or []:
        result = step.get("tool_result")
        if result is not None and not _is_error(result):
            try:
                texts.append(json.dumps(result, ensure_ascii=False, default=str))
            except Exception:                                      # noqa: BLE001
                texts.append(str(result))
    if not texts:
        return False
    evidence = _norm(" ".join(texts))
    shared = {w for w in _WORD.findall(str(answer or "").lower()) if w not in _STOP and w in evidence}
    return len(shared) >= 2 or any("." in w and w in evidence for w in shared)


def check(goal: str, answer: Optional[str], steps: Optional[List[Dict[str, Any]]] = None, conversation: str = "") -> Dict[str, Any]:
    """The grounding verdict. `grounded` is False when any flag is raised; `supported` says the answer reuses a successful tool result's own words."""
    steps = [s for s in (steps or []) if isinstance(s, dict)]
    text = str(answer or "").strip()
    flags: List[str] = []
    detail: Dict[str, Any] = {}
    if len(text) < 2:
        flags.append("empty_answer")
    bad = ungrounded_values(goal, text, steps, conversation)
    if bad:
        flags.append("ungrounded_values")
        detail["ungrounded_values"] = bad[:10]
    if _ACTION_GOAL.search(goal or "") and _SUCCESS_CLAIM.search(text) and not _effect_ran(steps):
        flags.append("claims_action_without_effect")
    results = [s.get("tool_result") for s in steps if s.get("tool_result") is not None]
    if results and all(_is_error(r) for r in results) and _SUCCESS_CLAIM.search(text):
        flags.append("claims_success_after_error")
    return {"grounded": not flags, "flags": flags, "supported": evidence_support(text, steps), **detail}
