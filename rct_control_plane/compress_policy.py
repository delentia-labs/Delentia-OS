"""
Round 109: when is it right to filter a large tool result by the goal's words (COMPRESS), and by which words?

Measured first (research/DELTA_TOKEN_SAVINGS_RESULTS_R109.md): Delta v2's aggressive focus keeps the lines that share a word with the goal and drops the rest. That is a good deal for a LOOKUP
("where is X mentioned?": the line is kept, 16-92% of the tokens go) and a bad one for a task that needs the whole text ("summarise this": 1-50% of the lines are shown and the one asked about is
usually not among them), for a file read in order to EDIT it (the filtered view has no indentation and is not the text that has to match), and when the goal has no content word at all. It also took
generic words ("document", "points", "tell") as focus, and those match random lines.

This module is the pure decision made before COMPRESS filters anything. No model, no network, bilingual (English and Thai), fast. Any error -> do not filter: showing the text is always safe,
filtering wrongly is not. `DELENTIA_COMPRESS_POLICY=off` restores the old behaviour exactly.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List

OFF_ENV = "DELENTIA_COMPRESS_POLICY"
MAX_WHOLE_CHARS = 120_000           # about 30,000 tokens: above this, showing the text whole would fill many models' context windows, so the old filter (with the expand path) is kept

# The task needs the whole text, not a line of it.
_WHOLE_EN = re.compile(
    r"\b(summar\w*|overview|review\w*|compar\w*|analy[sz]\w*|explain\w*|describe\w*|translat\w*|proofread\w*|audit\w*|walk me through|go through|"
    r"tell me what|what(?:'s| is| does)(?: it| this \w+| this| the \w+)? (?:contain|cover)\b|what(?:'s| is| does)(?: it| this \w+| this| the \w+)? say(?! (?:about|regarding|on|for|concerning)\b)|"
    r"list (?:all|every)|every|entire|whole|all of|each (?:row|line|item|section))\b", re.IGNORECASE)
_WHOLE_TH = re.compile(r"สรุป|ภาพรวม|เปรียบเทียบ|วิเคราะห์|อธิบาย|แปล|ตรวจทาน|ตรวจสอบ|ทบทวน|ทั้งหมด|ทั้งไฟล์|ทุกบรรทัด|ทุกแถว|ทุกข้อ|มีอะไรบ้าง|เนื้อหา")
# The text itself will be changed: the lines must be the real ones.
_EDIT_EN = re.compile(r"\b(fix\w*|edit\w*|modif\w*|refactor\w*|renam\w*|implement\w*|patch\w*|replac\w*|rewrit\w*|chang\w*|updat\w*|correct\w*)\b", re.IGNORECASE)
_EDIT_TH = re.compile(r"แก้|ปรับแก้|เปลี่ยน|เขียนใหม่|อัปเดต|ปรับปรุง")

_GENERIC = frozenset(
    "summarize summarise summary summaries overview review compare comparison analyze analyse analysis explain describe translate rewrite proofread audit document documents file files text "
    "content contents read open show tell give list find look check please say says said mention mentions mentioned point points bullet bullets three four five short brief briefly detail details "
    "information info thing things something anything everything whole entire full complete data record records page section part parts line lines item items answer question help need want "
    "like know see get make use using used just only based regarding concerning relating related contain contains containing include includes including write writes".split())
_SPLIT = re.compile(r"[^\w@./-]+")
_THAI_RUN = re.compile(r"[฀-๿]+")
_STEM = re.compile(r"(ing|ed|es|s)$")


@dataclass(frozen=True)
class Decision:
    apply: bool
    reason: str
    focus: str = ""


def _whole_or_too_large(reason: str, goal: str, text: str) -> "Decision":
    """Show the text whole, unless it is too large to show: then keep the old filter (and the expand path) rather than send tens of thousands of tokens in every later call."""
    if len(text) > MAX_WHOLE_CHARS:
        return Decision(True, "too_large_to_show_whole", goal)
    return Decision(False, reason)


def _content_words(goal: str) -> List[str]:
    """The words of the goal that can pick lines out of a text: not stop words, not generic task words, not file paths, and for Thai only short runs (a whole sentence is not a word)."""
    from rct_control_plane.delta_v2 import STOPWORDS
    out: List[str] = []
    for raw in _SPLIT.split(goal.lower()):
        word = raw.strip("./-")
        if len(word) <= 2 or word in STOPWORDS or word in _GENERIC:
            continue
        if "/" in raw or re.search(r"\.[a-z0-9]{1,5}$", raw):              # a path or a file name: it names the source, not what to look for inside it
            continue
        if _THAI_RUN.search(word) and not re.search(r"[a-z0-9]", word) and len(word) > 12:
            continue                                                       # a Thai run longer than a word is a phrase: substring matching on it finds nothing real
        if word not in out:
            out.append(word)
    return out


def _in_text(word: str, lowered_text: str) -> bool:
    return word in lowered_text or _STEM.sub("", word) in lowered_text


def decide(goal: str, tool_name: str, tool_args: Dict[str, Any], text: str) -> Decision:
    """Should COMPRESS filter this result by the goal's words, and with which words as the focus."""
    if (os.getenv(OFF_ENV) or "").strip().lower() in ("off", "0", "no", "false"):
        return Decision(True, "policy_off", goal or "")
    try:
        goal = (goal or "").strip()
        if not goal:
            return Decision(False, "no_goal")
        if _WHOLE_EN.search(goal) or _WHOLE_TH.search(goal):
            return _whole_or_too_large("whole_text_goal", goal, text)
        if _EDIT_EN.search(goal) or _EDIT_TH.search(goal):
            return _whole_or_too_large("edit_goal", goal, text)
        words = _content_words(goal)
        if not words:
            return _whole_or_too_large("no_content_words", goal, text)
        lowered = text.lower()
        present = [w for w in words if _in_text(w, lowered)]
        if not present:
            return _whole_or_too_large("words_not_in_text", goal, text)
        return Decision(True, "specific_goal", " ".join(present))
    except Exception:                                                      # noqa: BLE001 - never decide to filter on an error
        return Decision(False, "policy_error")
