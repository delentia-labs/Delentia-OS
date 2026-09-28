"""
Delta v2 context compression - Python port (Round 48, COMPRESS step).

A line-for-line port of delentia-mcp-ecosystem packages/delta/src/index.ts
`compressContext` (the version benchmarked in Round 46: ~70% fewer tokens on
real tool output/logs, and every literal-wording question still answered).
Deterministic, no LLM call. test_delta_v2_port_real.py checks that this
port produces byte-identical `compressed_delta_text` to the TypeScript
original on shared fixtures, so "Delta v2" means the same thing in both
systems.

Differences that do not affect output: no timestamp/zod/MCP wrapper.
Lengths are counted in UTF-16 code units like JavaScript (_js_len), so
character counts and token estimates match even with emoji.
JavaScript's \\p{L}\\p{N} classes are expressed as Python's Unicode
`[^\\W_]` (letters and digits).
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

STOPWORDS = frozenset(
    "a an and are as at be been before by can do does did each for from has have how i if in into is it its may "
    "me must my of on or our should so than that the their them then there these they this to two was were what "
    "when where which while who whom why will with would you your about after any all also".split(" ")
)

_SPLIT_RE = re.compile(r"[^\w@./-]+")
_EDGE_PUNCT_RE = re.compile(r"^[./-]+|[./-]+$")
_STEM_RE = re.compile(r"(ing|ed|es|s)$")
_LETTER_DIGIT_RUN_RE = re.compile(r"[^\W_]{3,}")
_CODE_OR_STATE_RE = re.compile(r"error|verdict", re.IGNORECASE)
HEADING_RE = re.compile(
    r"^(#{1,6}\s|(export\s+)?(default\s+)?(async\s+)?(function|class|interface|type|enum|const\s+[A-Z][A-Z0-9_]+\s*=)\b"
    r"|def\s|class\s|>\s\S|##\[group\]|▶|(PASS|FAIL)\s|={3,}|-{3,}\s*\S)"
)
MAX_OUTLINE_ENTRIES = 40


@dataclass
class CompressionResult:
    original_char_count: int
    compressed_char_count: int
    estimated_original_tokens: int
    estimated_compressed_tokens: int
    reduction_percentage: float
    compressed_delta_text: str
    context_hash: str


def focus_keywords(intent: str) -> List[str]:
    """Meaningful, lightly stemmed keywords (stopwords and <=2-char words dropped), in first-seen order."""
    seen: List[str] = []
    words = [_EDGE_PUNCT_RE.sub("", w) for w in _SPLIT_RE.split(intent.lower())]
    for w in words:
        if len(w) <= 2 or w in STOPWORDS:
            continue
        stemmed = _STEM_RE.sub("", w)
        if len(stemmed) > 2 and stemmed not in seen:
            seen.append(stemmed)
    return seen


def _js_len(text: str) -> int:
    """String length as JavaScript counts it (UTF-16 code units): an emoji
    or other astral character counts as 2, as in the TypeScript original."""
    return len(text.encode("utf-16-le")) // 2


def _js_prefix(text: str, units: int) -> str:
    """text.slice(0, units) in UTF-16 units. Where JS would split a surrogate
    pair, this drops the half character instead (JS would emit a lone
    surrogate); only reachable for an astral character at position 100."""
    out, used = [], 0
    for ch in text:
        width = 2 if ord(ch) > 0xFFFF else 1
        if used + width > units:
            break
        out.append(ch)
        used += width
    return "".join(out)


def _is_content_line(line: str) -> bool:
    return _js_len(line) >= 12 and bool(_LETTER_DIGIT_RUN_RE.search(line))


def _js_round_1(x: float) -> float:
    # Math.round(x * 10) / 10 - JS rounds .5 up (toward +inf), unlike Python's round().
    return math.floor(x * 10 + 0.5) / 10


def compress_context(raw_context: str, intent_focus: Optional[str] = None,
                     aggressive_mode: bool = False, outline: bool = False) -> CompressionResult:
    original_char_count = _js_len(raw_context)
    estimated_original_tokens = math.ceil(original_char_count / 3.5)

    entries: List[Tuple[str, int]] = [
        (line.strip(), i + 1) for i, line in enumerate(raw_context.split("\n")) if line.strip()
    ]
    seen = set()
    deduplicated: List[Tuple[str, int]] = []
    for text, n in entries:
        if _is_content_line(text):
            if text in seen:
                continue
            seen.add(text)
        deduplicated.append((text, n))
    lines = [t for t, _ in deduplicated]
    outline_text = ""

    key_lines = lines
    if intent_focus and aggressive_mode:
        keywords = focus_keywords(intent_focus)
        keep = [False] * len(lines)
        for i, line in enumerate(lines):
            lower = line.lower()
            has_keyword = any(k in lower for k in keywords)
            is_code_or_state = line.startswith("+") or line.startswith("-") or bool(_CODE_OR_STATE_RE.search(line))
            if has_keyword or is_code_or_state:
                for j in range(max(0, i - 1), min(len(lines) - 1, i + 1) + 1):
                    keep[j] = True
        key_lines = []
        skipped = False
        for i, line in enumerate(lines):
            if not keep[i]:
                skipped = True
                continue
            if skipped:
                key_lines.append("…")
            key_lines.append(line)
            skipped = False
        if not key_lines:
            key_lines = lines[-10:]
        if outline:
            omitted = [(t, n) for i, (t, n) in enumerate(deduplicated) if not keep[i] and HEADING_RE.search(t)]
            if omitted:
                shown = [f"L{n}: {_js_prefix(t, 100)}" for t, n in omitted[:MAX_OUTLINE_ENTRIES]]
                if len(omitted) > MAX_OUTLINE_ENTRIES:
                    shown.append(f"… {len(omitted) - MAX_OUTLINE_ENTRIES} more")
                outline_text = ("\n[Left out — section headings with their line numbers in the original; "
                                "request a line range to read one]\n" + "\n".join(shown))

    header = f'[DELENTIA-DELTA-STREAM] Intent: "{intent_focus or "General"}" | State Diffs Only:'
    compressed = f"{header}\n" + "\n".join(key_lines) + outline_text

    compressed_char_count = _js_len(compressed)
    estimated_compressed_tokens = math.ceil(compressed_char_count / 3.5)
    raw_reduction = (estimated_original_tokens - estimated_compressed_tokens) / estimated_original_tokens * 100
    return CompressionResult(
        original_char_count=original_char_count,
        compressed_char_count=compressed_char_count,
        estimated_original_tokens=estimated_original_tokens,
        estimated_compressed_tokens=estimated_compressed_tokens,
        reduction_percentage=_js_round_1(min(raw_reduction, 100)),
        compressed_delta_text=compressed,
        context_hash=hashlib.sha256(compressed.encode("utf-8")).hexdigest(),
    )
