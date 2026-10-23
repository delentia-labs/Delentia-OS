"""
RCT-7 R5/R7 (creator's definition v0.3): when the result does not match what the person asked, REPORT THE DIFFERENCE, STOP AND ASK.

This module is the rule-checkable part, and only that: four kinds of requirement that can be read from the goal's words and tested without a
model, and the checks of the finished episode against them. It does not use similarity (a correct answer in other words must not be stopped), and it never
guesses: a goal that does not state a requirement yields none, and an answer too short to judge yields no verdict.

  language          "answer in Thai" / "ตอบเป็นภาษาไทย" / "in English"    -> the script of the answer's own text (code, links and paths removed)
  format            "return JSON" / "ตอบเป็น JSON"                      -> the answer parses as JSON (a ``` fence around it is allowed)
  required_artifact "save it as report.md" / "บันทึกเป็น report.md"      -> that file exists in the workspace afterwards
  forbidden_effect  "do not modify config.yaml" / "ห้ามแก้ไฟล์ x.py"     -> no write or patch to that file went through

The functions are pure (the workspace is a parameter), so the loop calls them and tests call them the same way.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

KINDS = ("language", "format", "required_artifact", "forbidden_effect")
WRITE_TOOLS = ("delentia_write_repo_file", "delentia_patch_repo_file")
_PATH = r"([\w][\w./\\-]{0,120}\.[A-Za-z0-9]{1,6})"

# Thai letters U+0E01-U+0E5B; Latin letters only. Digits and punctuation do not vote.
_THAI = re.compile(r"[ก-๛]")
_LATIN = re.compile(r"[A-Za-z]")
MIN_LETTERS = 20            # fewer letters than this: the answer is too short to judge by script (a number, a name, "ok")
THAI_MIN_SHARE = 0.30       # a Thai answer may keep technical terms in Latin letters
ENGLISH_MAX_THAI_SHARE = 0.20


@dataclass(frozen=True)
class Requirement:
    kind: str
    value: str
    source: str             # the words of the goal it was read from


@dataclass(frozen=True)
class Difference:
    criterion: str
    expected: str
    observed: str
    detail: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {"criterion": self.criterion, "expected": self.expected, "observed": self.observed, "detail": self.detail}


# ---------------------------------------------------------------------------------------------------------------- reading the goal
_LANG_TARGET = re.compile(
    r"(?:เป็น|ด้วย|ใน|ตอบ|เขียน|สรุป|แปลเป็น|แปลเป็นภาษา)\s*ภาษา\s*(ไทย|อังกฤษ)"          # เป็นภาษาไทย, ด้วยภาษาอังกฤษ
    r"|ภาษา\s*(ไทย|อังกฤษ)\s*(?:เท่านั้น|ล้วน)"                                           # ภาษาไทยเท่านั้น
    r"|\b(?:in|into|to|using)\s+(thai|english)\b"                                        # in Thai, to English
    r"|\b(?:answer|reply|respond|write)\s+(?:only\s+)?(?:in\s+)?(thai|english)\b"         # answer in Thai
    r"|(?:สรุป|รายงาน|อธิบาย|ตอบ)\s*(?:เป็น)?\s*(ไทย|อังกฤษ)\b",                          # ตอบไทย
    re.IGNORECASE,
)
_JSON = re.compile(r"\b(?:as|in|return|returns|output|respond with|reply with)\s+(?:a\s+|valid\s+)*json\b|(?:เป็น|ในรูป|รูปแบบ)\s*json\b", re.IGNORECASE)
_SAVE = re.compile(r"\bsave\s+(?:it\s+|the\s+\w+\s+|this\s+)?(?:as|to|in|into)\s+" + _PATH + r"|บันทึก(?:ผล)?(?:เป็น|ลง(?:ใน)?|ไว้ที่)\s*(?:ไฟล์)?\s*" + _PATH, re.IGNORECASE)
_FORBID = re.compile(
    r"\b(?:do\s+not|don't|never)\s+(?:modify|change|edit|overwrite|touch|delete|remove)\s+(?:the\s+)?(?:file\s+)?" + _PATH
    + r"|(?:ห้าม|อย่า)\s*(?:แก้ไข|แก้|ลบ|เขียนทับ)\s*(?:ไฟล์)?\s*" + _PATH,
    re.IGNORECASE,
)


def _language_of(word: str) -> Optional[str]:
    w = word.lower()
    if w in ("ไทย", "thai"):
        return "th"
    if w in ("อังกฤษ", "english"):
        return "en"
    return None


def _clean_path(raw: str) -> str:
    return raw.replace("\\", "/").lstrip("./")


def derive_requirements(goal: str) -> List[Requirement]:
    """What the person's own words require, and nothing more. Two different target languages in one goal ("แปลจากภาษาอังกฤษเป็นภาษาไทย" names both) is read by its
    preposition: only the phrases that say what the OUTPUT should be count, and if they still disagree no language requirement is made."""
    text = goal or ""
    out: List[Requirement] = []
    targets = {}
    for m in _LANG_TARGET.finditer(text):
        lang = next((_language_of(g) for g in m.groups() if g), None)
        if lang:
            targets[lang] = m.group(0)
    if len(targets) == 1:
        (lang, words), = targets.items()
        out.append(Requirement("language", lang, words))
    if jm := _JSON.search(text):
        out.append(Requirement("format", "json", jm.group(0)))
    for m in _SAVE.finditer(text):
        path = next((g for g in m.groups() if g), None)
        if path:
            out.append(Requirement("required_artifact", _clean_path(path), m.group(0)))
    for m in _FORBID.finditer(text):
        path = next((g for g in m.groups() if g), None)
        if path:
            out.append(Requirement("forbidden_effect", _clean_path(path), m.group(0)))
    return out


# ---------------------------------------------------------------------------------------------------------------- checking the result
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"https?://\S+")
_PATHLIKE = re.compile(r"[\w./\\-]+\.[A-Za-z0-9]{1,6}\b")


def prose_of(answer: str) -> str:
    """The answer's own sentences: code blocks, inline code, links and file names removed, so a Thai report that quotes a command is still a Thai report."""
    text = _FENCE.sub(" ", answer or "")
    text = _INLINE.sub(" ", text)
    text = _URL.sub(" ", text)
    return _PATHLIKE.sub(" ", text)


def thai_share(answer: str) -> Optional[float]:
    """Thai letters / (Thai + Latin letters) in the prose, or None when there are too few letters to judge."""
    prose = prose_of(answer)
    thai, latin = len(_THAI.findall(prose)), len(_LATIN.findall(prose))
    return None if thai + latin < MIN_LETTERS else thai / (thai + latin)


def _strip_fence(answer: str) -> str:
    text = (answer or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else text


def _executed(step: Dict[str, Any]) -> bool:
    """The tool really ran: it was not blocked by a gate and not left waiting for a signature."""
    outcome = step.get("tool_result")
    if isinstance(outcome, dict) and any(outcome.get(k) for k in ("blocked", "fdia_blocked", "pending_approval", "error")):
        return False
    return True


def _inside(root: Path, relative: str) -> Optional[Path]:
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        return None
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def check(requirements: Iterable[Requirement], answer: Optional[str], steps: Optional[List[Dict[str, Any]]], workspace_root: Optional[Path]) -> List[Difference]:
    """The differences between what was required and what happened. An empty list means no requirement was broken (it does not mean the answer is right)."""
    found: List[Difference] = []
    text = answer or ""
    for req in requirements:
        if req.kind == "language":
            share = thai_share(text)
            if share is None:
                continue                                         # too short to judge: not a mismatch
            if req.value == "th" and share < THAI_MIN_SHARE:
                found.append(Difference("language", "Thai", "English" if share < 0.1 else "mostly English", f"Thai letters are {share:.0%} of the answer's letters (at least {THAI_MIN_SHARE:.0%} expected)"))
            if req.value == "en" and share > ENGLISH_MAX_THAI_SHARE:
                found.append(Difference("language", "English", "Thai" if share > 0.7 else "mixed Thai and English", f"Thai letters are {share:.0%} of the answer's letters (at most {ENGLISH_MAX_THAI_SHARE:.0%} expected)"))
        elif req.kind == "format" and req.value == "json":
            try:
                json.loads(_strip_fence(text))
            except (ValueError, TypeError):
                found.append(Difference("format", "JSON", "text that is not JSON", "the answer does not parse as JSON"))
        elif req.kind == "required_artifact":
            target = _inside(workspace_root, req.value) if workspace_root else None
            if target is None or not target.is_file():
                found.append(Difference("required_artifact", f"a file {req.value}", "no such file", "asked to save the result there; it does not exist in the workspace"))
        elif req.kind == "forbidden_effect":
            for step in steps or []:
                if step.get("tool_name") not in WRITE_TOOLS or not _executed(step):
                    continue
                args = step.get("tool_args") or {}
                path = _clean_path(str(args.get("relative_path") or args.get("path") or ""))
                if path and (path == req.value or path.endswith("/" + req.value)):
                    found.append(Difference("forbidden_effect", f"{req.value} left untouched", f"{step.get('tool_name')} changed {path}", "a write went through to a file the goal said not to change"))
                    break
    return found


def question_for(goal: str, differences: List[Difference]) -> str:
    """The question put to the person, in the language of their goal. It states the difference and asks what to do; it does not propose a silent fix."""
    thai = bool(_THAI.search(goal or ""))
    lines = []
    for d in differences:
        if thai:
            lines.append(f"- {d.criterion}: ขอ {d.expected} แต่ได้ {d.observed}")
        else:
            lines.append(f"- {d.criterion}: asked for {d.expected}, got {d.observed}")
    head = "ผลที่ได้ไม่ตรงกับที่คุณขอ:" if thai else "The result does not match what you asked:"
    tail = "ต้องการให้ทำอย่างไรต่อ (ทำใหม่ตามที่ขอ, ยอมรับผลนี้, หรือเปลี่ยนสิ่งที่ขอ)" if thai else "What should happen next: redo it as asked, accept this result, or change what you asked for?"
    return "\n".join([head, *lines, tail])

CHECKED_BY = {
    "language": "the script of the answer's own sentences (code, links and file names removed)",
    "format": "the answer parses as JSON",
    "required_artifact": "the file exists in the workspace afterwards",
    "forbidden_effect": "no write or patch to that file went through",
}


def conditions_for(goal: str) -> List[Dict[str, str]]:
    """RCT-7 R4, for the part that can be checked: the conditions the wanted result must satisfy, read from the goal's own words, each with how it will be checked.
    Shown in the plan before the first tool, so the person sees what 'matches what I asked' will mean. A goal that states none gets an empty list."""
    return [{"kind": r.kind, "value": r.value, "from": r.source, "checked_by": CHECKED_BY[r.kind]} for r in derive_requirements(goal)]
