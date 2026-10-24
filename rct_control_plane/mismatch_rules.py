"""
RCT-7 R5/R7 (creator's definition v0.3): when the result does not match what the person asked, REPORT THE DIFFERENCE, STOP AND ASK.

This module is the rule-checkable part, and only that: four kinds of requirement that can be read from the goal's words and tested without a
model, and the checks of the finished episode against them. It does not use similarity (a correct answer in other words must not be stopped), and it never
guesses: a goal that does not state a requirement yields none, and an answer too short to judge yields no verdict.

  language          "answer in Thai" / "ตอบเป็นภาษาไทย" / "in English"    -> the script of the answer's own text (code, links and paths removed)
  format            "return JSON" / "ตอบเป็น JSON"                      -> the answer parses as JSON (a ``` fence around it is allowed)
  required_artifact "save it as report.md" / "บันทึกเป็น report.md"      -> that file exists in the workspace afterwards
  forbidden_effect  "do not modify config.yaml" / "ห้ามแก้ไฟล์ x.py"     -> no write or patch to that file went through
  max_words         "in under 50 words"                                  -> the prose has no more words (not checked for Thai: it has no spaces to count)
  max_chars         "under 200 characters" / "ไม่เกิน 100 ตัวอักษร"        -> the answer is not longer
  item_count        "list 5 risks" / "สรุปเป็น 3 ข้อ" / "at most 4 items"   -> the top-level list items match (an answer without list lines gets no verdict)

Round 97 adds three more things that read the goal's own words and nothing else: parts_of (R3: explicit enumerations only), unknowns_for (R1: a named file that exists nowhere,
a reference with nothing to refer to) and the person's answer to a question overriding what the original goal required.

The functions are pure (the workspace is a parameter), so the loop calls them and tests call them the same way.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

KINDS = ("language", "format", "required_artifact", "forbidden_effect", "max_words", "max_chars", "item_count")
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
    r"|(?:สรุป|รายงาน|อธิบาย|ตอบ)\s*(?:เป็น)?\s*(ไทย|อังกฤษ)\b"                           # ตอบไทย
    r"|\b(thai|english)\s+(?:is|will be)\s+(?:fine|ok|okay)\b"                       # English is fine
    r"|(?:ภาษา)?\s*(ไทย|อังกฤษ)\s*ก็ได้",                                              # อังกฤษก็ได้
    re.IGNORECASE,
)
_JSON = re.compile(r"\b(?:as|in|return|returns|output|respond with|reply with)\s+(?:a\s+|valid\s+)*json\b|(?:เป็น|ในรูป|รูปแบบ)\s*json\b", re.IGNORECASE)
_SAVE = re.compile(r"\bsave\s+(?:it\s+|the\s+\w+\s+|this\s+)?(?:as|to|in|into)\s+" + _PATH + r"|บันทึก(?:ผล)?(?:เป็น|ลง(?:ใน)?|ไว้ที่)\s*(?:ไฟล์)?\s*" + _PATH, re.IGNORECASE)
_FORBID = re.compile(
    r"\b(?:do\s+not|don't|never)\s+(?:modify|change|edit|overwrite|touch|delete|remove)\s+(?:the\s+)?(?:file\s+)?" + _PATH
    + r"|(?:ห้าม|อย่า)\s*(?:แก้ไข|แก้|ลบ|เขียนทับ)\s*(?:ไฟล์)?\s*" + _PATH,
    re.IGNORECASE,
)


_NUM = r"(\d{1,4})"
_MAX_WORDS = re.compile(
    r"\b(?:in|within|under|below|less than|fewer than|at most|no more than|up to|maximum of|a maximum of|max|limit(?:ed)?(?: the answer)? to)\s+" + _NUM + r"\s+words?\b"
    r"|\b" + _NUM + r"\s+words?\s+or\s+(?:fewer|less)\b", re.IGNORECASE)
_MAX_CHARS = re.compile(
    r"\b(?:in|within|under|below|less than|fewer than|at most|no more than|up to|maximum of|a maximum of|max|limit(?:ed)?(?: the answer)? to|keep it (?:under|below|to))\s+" + _NUM + r"\s+(?:characters|chars)\b"
    r"|(?:ไม่เกิน|ภายใน)\s*" + _NUM + r"\s*ตัวอักษร", re.IGNORECASE)
_ITEM_NOUN = r"(?:[A-Za-z][\w-]*\s+){0,2}?(?:items?|points?|bullets?|bullet points?|reasons?|risks?|examples?|options?|ideas?|steps?|tips?|things?|ways?|names?|colou?rs?|files?)"
_ITEMS_EXACT = re.compile(
    r"\b(?:list|give|name|write|provide|show|enumerate|suggest|propose|summari[sz]e)\s+(?:me\s+)?(?:the\s+)?(?:top\s+)?(?:exactly\s+)?" + _NUM + r"\s+" + _ITEM_NOUN
    + r"|(?:สรุป|ตอบ|เขียน|บอก|ยก|แจก|ให้)(?:เป็น|ให้)?\s*" + _NUM + r"\s*ข้อ", re.IGNORECASE)
_ITEMS_MAX = re.compile(
    r"\b(?:up to|at most|no more than|a maximum of|maximum of|max)\s+" + _NUM + r"\s+" + _ITEM_NOUN
    + r"|(?:ไม่เกิน|ภายใน)\s*" + _NUM + r"\s*ข้อ", re.IGNORECASE)
_LIST_LINE = re.compile(r"^(\s*)(?:[-*•]|\d{1,2}[.)])\s+\S")


def _language_of(word: str) -> Optional[str]:
    w = word.lower()
    if w in ("ไทย", "thai"):
        return "th"
    if w in ("อังกฤษ", "english"):
        return "en"
    return None


def _clean_path(raw: str) -> str:
    return raw.replace("\\", "/").lstrip("./")


def split_updates(goal: str):
    """(the original request, [what the person answered when asked]). A goal that was never revised has no updates."""
    from rct_control_plane.clarifications import ANSWER_LABEL, UPDATE_MARK
    text = goal or ""
    if UPDATE_MARK not in text:
        return text, []
    head, *tails = text.split(UPDATE_MARK)
    answers = []
    for tail in tails:
        _, _, rest = tail.partition(ANSWER_LABEL)
        answers.append(rest.strip())
    return head.rstrip(), answers


_OVERRIDES = ("language", "format", "max_words", "max_chars", "item_count")      # what the person says when asked replaces the earlier requirement of the same kind


def derive_requirements(goal: str) -> List[Requirement]:
    """What the person's own words require, and nothing more. A goal that carries the person's answer to a question (clarifications.UPDATE_MARK) is read in two steps: the original
    request, then the answer; an answer that states a requirement of the same kind replaces the old one, so "answer in Thai" followed by the answer "in English" is an English request."""
    base, answers = split_updates(goal)
    found = _derive_one(base)
    for answer in answers:
        for req in _derive_one(answer):
            if req.kind in _OVERRIDES:
                found = [r for r in found if r.kind != req.kind]
            found.append(req)
    return found


def _derive_one(goal: str) -> List[Requirement]:
    """What one piece of text requires, and nothing more. Two different target languages in one goal ("แปลจากภาษาอังกฤษเป็นภาษาไทย" names both) is read by its
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
    if wm := _MAX_WORDS.search(text):
        out.append(Requirement("max_words", str(int(next(g for g in wm.groups() if g))), wm.group(0)))
    if cm := _MAX_CHARS.search(text):
        out.append(Requirement("max_chars", str(int(next(g for g in cm.groups() if g))), cm.group(0)))
    if im := _ITEMS_MAX.search(text):
        out.append(Requirement("item_count", "<=" + str(int(next(g for g in im.groups() if g))), im.group(0)))
    elif em := _ITEMS_EXACT.search(text):
        out.append(Requirement("item_count", "=" + str(int(next(g for g in em.groups() if g))), em.group(0)))
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
        elif req.kind == "max_words":
            if (thai_share(text) or 0.0) >= THAI_MIN_SHARE:
                continue                                         # Thai has no spaces: a word count would be a guess
            count = len([w for w in prose_of(text).split() if re.search(r"[A-Za-z0-9]", w)])
            limit = int(req.value)
            if count > limit + max(2, limit // 10):
                found.append(Difference("length", f"at most {limit} words", f"{count} words", "the answer is longer than the goal allowed (a margin of 10% or 2 words is allowed)"))
        elif req.kind == "max_chars":
            limit = int(req.value)
            size = len((text or "").strip())
            if size > limit + max(2, limit // 10):
                found.append(Difference("length", f"at most {limit} characters", f"{size} characters", "the answer is longer than the goal allowed (a margin of 10% or 2 characters is allowed)"))
        elif req.kind == "item_count":
            lines = [m for m in (_LIST_LINE.match(line) for line in text.splitlines()) if m]
            if not lines:
                continue                                         # prose with no list structure: nothing to count, no verdict
            top = min(len(m.group(1).expandtabs(4)) for m in lines)
            items = sum(1 for m in lines if len(m.group(1).expandtabs(4)) <= top + 1)
            op, n = ("<=", int(req.value[2:])) if req.value.startswith("<=") else ("=", int(req.value[1:]))
            if (op == "=" and items != n) or (op == "<=" and items > n):
                found.append(Difference("item_count", f"{'at most ' if op == '<=' else ''}{n} items", f"{items} items", "the list in the answer does not have the number of items the goal asked for"))
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


def _judgeable(req: Requirement, answer: Optional[str]) -> bool:
    """Can this requirement be judged from this answer at all? A short answer has no script to read, Thai has no words to count, prose has no list lines to count."""
    text = answer or ""
    if req.kind == "language":
        return thai_share(text) is not None
    if req.kind == "max_words":
        return (thai_share(text) or 0.0) < THAI_MIN_SHARE
    if req.kind == "item_count":
        return any(_LIST_LINE.match(line) for line in text.splitlines())
    return True


def _writes(steps: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out = []
    for index, step in enumerate(steps or []):
        if step.get("tool_name") in WRITE_TOOLS and _executed(step):
            args = step.get("tool_args") or {}
            out.append({"step": index + 1, "tool": step.get("tool_name"), "path": _clean_path(str(args.get("relative_path") or args.get("path") or ""))})
    return out


def _evidence(req: Requirement, answer: Optional[str], steps: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """What the verdict stands on, so a person can follow it back: a measured number from the answer, or the steps that wrote files. Nothing is invented: a requirement with no
    measurable basis gets an empty list."""
    text = answer or ""
    if req.kind == "language":
        share = thai_share(text)
        return [{"source": "final_answer", "measure": f"thai_letter_share={share:.2f}"}] if share is not None else []
    if req.kind == "max_words":
        return [{"source": "final_answer", "measure": f"words={len([w for w in prose_of(text).split() if re.search(r'[A-Za-z0-9]', w)])}"}]
    if req.kind == "max_chars":
        return [{"source": "final_answer", "measure": f"characters={len(text.strip())}"}]
    if req.kind == "item_count":
        lines = [m for m in (_LIST_LINE.match(line) for line in text.splitlines()) if m]
        if not lines:
            return []
        top = min(len(m.group(1).expandtabs(4)) for m in lines)
        return [{"source": "final_answer", "measure": f"top_level_items={sum(1 for m in lines if len(m.group(1).expandtabs(4)) <= top + 1)}"}]
    if req.kind == "format":
        return [{"source": "final_answer", "measure": "parses_as_json=" + str(_parses(text)).lower()}]
    if req.kind == "required_artifact":
        return [w for w in _writes(steps) if w["path"] == req.value or w["path"].endswith("/" + req.value)]
    if req.kind == "forbidden_effect":
        return _writes(steps)                              # every write that went through, so a person sees what WAS written instead
    return []


def _parses(text: str) -> bool:
    try:
        json.loads(_strip_fence(text))
        return True
    except (ValueError, TypeError):
        return False


def evaluate(requirements: Iterable[Requirement], answer: Optional[str], steps: Optional[List[Dict[str, Any]]], workspace_root: Optional[Path]) -> List[Dict[str, Any]]:
    """RCT-7 R4/R7 as evidence: for EACH requirement the request stated, what was checked and what was seen. status is met, broken, or not_judged (the answer gave the rule nothing
    to judge by; that is not a pass). Same checks as `check`; this only keeps the verdict per requirement instead of only the failures."""
    report: List[Dict[str, Any]] = []
    for req in requirements:
        differences = check([req], answer, steps, workspace_root)
        if differences:
            status, observed = "broken", differences[0].observed
        elif _judgeable(req, answer):
            status, observed = "met", ""
        else:
            status, observed = "not_judged", "the answer gave this rule nothing to judge by"
        report.append({"kind": req.kind, "value": req.value, "from": req.source, "checked_by": CHECKED_BY[req.kind], "status": status, "observed": observed,
                       "evidence": _evidence(req, answer, steps)})
    return report


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
    "max_words": "the words of the answer's own prose, counted (not checked for Thai)",
    "max_chars": "the length of the answer in characters",
    "item_count": "the top-level list items of the answer (no list lines: no verdict)",
}


def conditions_for(goal: str) -> List[Dict[str, str]]:
    """RCT-7 R4, for the part that can be checked: the conditions the wanted result must satisfy, read from the goal's own words, each with how it will be checked.
    Shown in the plan before the first tool, so the person sees what 'matches what I asked' will mean. A goal that states none gets an empty list."""
    return [{"kind": r.kind, "value": r.value, "from": r.source, "checked_by": CHECKED_BY[r.kind]} for r in derive_requirements(goal)]


# ---------------------------------------------------------------------------------------------------------------- R3: the parts the person listed
_LINE_ITEM = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+(.+?)\s*$")
_NUMBERED_INLINE = re.compile(
    r"(?:\bstep\s*(\d{1,2})\s*[:.\-–]?|ขั้นที่\s*(\d{1,2})|ข้อที่?\s*(\d{1,2})|\((\d{1,2})\)|(?<![\w.])(\d{1,2})\))\s*", re.IGNORECASE)
_SEQUENCE_SPLIT = re.compile(
    r"(?:[,.;]\s*|\s+)(?:and\s+then|then|finally|lastly|next|after\s+that|second(?:ly)?|third(?:ly)?|fourth)\b,?\s+"
    r"|\s+(?:จากนั้น|ต่อจากนั้น|หลังจากนั้น)\s*|\s+แล้ว\s+", re.IGNORECASE)
_LEAD_ORDINAL = re.compile(r"^(?:first(?:ly)?|ก่อนอื่น|เริ่มจาก|เริ่มด้วย)[,:]?\s*", re.IGNORECASE)
_CONDITION_LEAD = re.compile(r"^\s*(?:if|when|unless|whenever|หาก|ถ้า|เมื่อ)\b", re.IGNORECASE)
MAX_PARTS = 12


def _tidy_part(text: str) -> str:
    text = _LEAD_ORDINAL.sub("", text.strip())
    return text.strip(" \t\r\n.,;:").strip()


def parts_of(goal: str) -> List[str]:
    """RCT-7 R3 (deconstruct), for what the person wrote as separate steps and nothing else: a numbered or bulleted list, "Step 1 ... Step 2 ...", "first ... then ... finally",
    Thai "ขั้นที่ 1 ..." / "... แล้ว ..." / "... จากนั้น ...". Anything that is not an explicit enumeration is ONE part (the goal). Never a guess about what the steps 'really' are."""
    base, _ = split_updates(goal)
    text = (base or "").strip()
    if not text:
        return []
    items = [m.group(1) for m in (_LINE_ITEM.match(line) for line in text.splitlines()) if m]
    if len(items) >= 2:
        return [_tidy_part(i) for i in items][:MAX_PARTS]
    marks = list(_NUMBERED_INLINE.finditer(text))
    numbers = [int(next(g for g in m.groups() if g)) for m in marks]
    if len(marks) >= 2 and numbers == list(range(1, len(numbers) + 1)):
        pieces = [text[m.end(): (marks[i + 1].start() if i + 1 < len(marks) else len(text))] for i, m in enumerate(marks)]
        parts = [_tidy_part(p) for p in pieces]
        if all(parts):
            return parts[:MAX_PARTS]
    pieces = _SEQUENCE_SPLIT.split(text)
    pieces = [_tidy_part(p) for p in pieces]
    pieces = [p for p in pieces if p]
    if len(pieces) >= 2 and not _CONDITION_LEAD.match(pieces[0]):
        return pieces[:MAX_PARTS]
    return [text]


# ---------------------------------------------------------------------------------------------------------------- R1: what is not known
_PATH_TOKEN = r"((?:[\w.-]+/)*[\w][\w.-]*\.[A-Za-z][A-Za-z0-9]{0,5})(?![\w.])"        # the extension starts with a letter: not v1.2.3
_NOT_A_FILE = re.compile(r"^(?:e\.g|i\.e|etc|vs|u\.s|a\.m|p\.m)$|^[\w-]+\.(?:com|org|net|io|dev|ai|co|th|app|gov|edu|info)(?:/|$)", re.IGNORECASE)   # abbreviations and web addresses
_READ_VERB = re.compile(
    r"\b(?:read|open|edit|update|modify|change|summari[sz]e|review|check|look\s+at|analy[sz]e|refactor|fix|translate|parse|inspect|load|show\s+me|cat)\b"
    r"|(?:อ่าน|เปิด|แก้ไข|แก้|ตรวจ|สรุป|แปล|วิเคราะห์|ดู)", re.IGNORECASE)
_CREATE_VERB = re.compile(r"\b(?:creat\w*|writ\w*|sav\w*|generat\w*|produc\w*|mak\w*|output\w*|export\w*|nam\w*|call\w*)\b|(?:สร้าง|เขียน|บันทึก|ส่งออก)", re.IGNORECASE)
_NEGATED = re.compile(r"\b(?:do\s+not|don't|never)\b|(?:ห้าม|อย่า)", re.IGNORECASE)
_BARE_REFERENCE = re.compile(
    r"^(?:please\s+)?(?:fix|do|redo|repeat|continue|undo|finish|change|update|run|try)\s+(?:it|that|this|those|them|the\s+same)(?:\s+(?:again|now|too))?$"
    r"|^(?:please\s+)?(?:do|try)\s+(?:that|it|this)\s+again$"
    r"|^(?:ช่วย)?(?:แก้|ทำ|ลอง|รัน|ส่ง)\s*(?:อันนั้น|อันนี้|มัน|เหมือนเดิม|ตามนั้น|อีกครั้ง|อีกที|ใหม่|ซ้ำ)(?:\s*(?:ให้หน่อย|หน่อย|ที|นะ|ครับ|ค่ะ))?$", re.IGNORECASE)
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build"}
_WALK_LIMIT = 6000


def _names_in(workspace_root: Path) -> set:
    """Lower-cased names of the files under the workspace (bounded: a huge tree is not a reason to wait)."""
    names: set = set()
    seen = 0
    stack = [workspace_root]
    while stack and seen < _WALK_LIMIT:
        folder = stack.pop()
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS and not entry.is_symlink():
                    stack.append(entry)
            else:
                names.add(entry.name.lower())
    return names


def unknowns_for(goal: str, workspace_root: Optional[Path], has_conversation: bool = False) -> List[Dict[str, str]]:
    """RCT-7 R1 (observe, including what is NOT known), for two things a rule can see without a model:
      * missing_file: the goal tells the agent to read, edit or summarise a file whose name exists nowhere under the workspace and that no creation verb explains
        (a file in a sub-folder is found; an address, an absolute path and a file the goal says NOT to touch are not judged);
      * dangling_reference: the goal is only a reference ("fix it", "do that again", "แก้อันนั้น") and there is no earlier conversation for it to refer to.
    Everything else the person did not say stays unknown to a rule; that needs a model."""
    base, answers = split_updates(goal)
    if answers:
        return []                                                # the person was already asked and answered; the question is not asked twice
    text = " ".join((base or "").split())
    found: List[Dict[str, str]] = []
    if not has_conversation and _BARE_REFERENCE.match(text.strip(" .!?")):
        found.append({"kind": "dangling_reference", "value": "", "detail": "the request refers to something ('it', 'that') and there is nothing earlier to refer to"})
    if workspace_root is not None and text:
        names: Optional[set] = None
        no_url = _URL.sub(" ", text)
        for m in re.finditer(_PATH_TOKEN, no_url):
            raw = m.group(1).replace("\\", "/")
            if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or _NOT_A_FILE.search(raw):
                continue
            clause_start = max(no_url.rfind(c, 0, m.start()) for c in ".;:!?\n") + 1
            before = no_url[clause_start:m.start()][-60:]
            if _NEGATED.search(before) or _CREATE_VERB.search(before) or not _READ_VERB.search(before):
                continue
            if names is None:
                names = _names_in(workspace_root)
            target = _inside(workspace_root, raw)
            if target is not None and target.is_file():
                continue
            if Path(raw).name.lower() in names:
                continue
            if not any(f["value"] == raw for f in found):
                found.append({"kind": "missing_file", "value": raw, "detail": f"{raw} is named in the request but no file with that name exists under the workspace"})
    return found[:5]


def question_for_unknowns(goal: str, unknowns: List[Dict[str, str]]) -> str:
    thai = bool(_THAI.search(goal or ""))
    lines = []
    for u in unknowns:
        if u["kind"] == "missing_file":
            lines.append(f"- ไม่พบไฟล์ {u['value']} ในที่ทำงาน" if thai else f"- I cannot find a file named {u['value']} anywhere in the workspace")
        else:
            lines.append("- คำขอนี้อ้างถึงบางอย่าง แต่ไม่มีบทสนทนาก่อนหน้าให้อ้างถึง" if thai else "- The request refers to something, and there is nothing earlier to refer to")
    head = "ก่อนเริ่ม ยังมีสิ่งที่ไม่ทราบ:" if thai else "Before I start, something is not known:"
    tail = "ช่วยบอกว่าหมายถึงอะไร (ระบุชื่อ/ที่อยู่ที่ถูกต้อง หรือบอกให้สร้างใหม่) แล้วส่งคำขอเดิมอีกครั้ง" if thai else "Tell me what you mean (the right name or place, or say it should be created), then send the same request again."
    return "\n".join([head, *lines, tail])
