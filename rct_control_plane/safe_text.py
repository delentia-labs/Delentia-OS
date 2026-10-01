"""
Linear-time versions of a few text scans that used regular expressions CodeQL (py/polynomial-redos)
flags: each pattern could take quadratic time on a long string of repeated characters, and these
run on text a user controls (a goal, a pasted DSL file, a shell command, a model reply).

Every function here returns exactly what the regular expression it replaces returned. The test
module compares them against the original patterns on thousands of random and adversarial strings
(rct_control_plane/tests/test_safe_text_real.py), and the originals are kept there as the oracle.
Nothing in this module uses a quantified group or a pattern whose repeated part can be re-entered.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from typing import List, Optional, Tuple

_IDENT_RUN = re.compile(r"[a-z0-9_]+")
_PATH_RUN = re.compile(r"[a-z0-9_./]+")
_FILE_EXTENSIONS = ("py", "js", "ts", "java", "cpp", "go", "rs", "rb")
_WORD = re.compile(r"\w+")


def json_object_span(text: str) -> Optional[str]:
    """What re.search(r"\\{.*\\}", text, re.DOTALL).group(0) returned: from the first '{' to the last '}'."""
    start = text.find("{")
    end = text.rfind("}")
    return text[start:end + 1] if start >= 0 and end > start else None


def substitutions(command: str) -> List[str]:
    """The inner text of every `$( ... )` and backtick substitution, in order, non-overlapping: the
    group(1)/group(2) values of re.finditer(r"\\$\\(([^)]*)\\)|`([^`]*)`", command) (an empty inner
    text is returned as an empty string, as the caller filters those)."""
    parens = [i for i, ch in enumerate(command) if ch == ")"]
    ticks = [i for i, ch in enumerate(command) if ch == "`"]
    out: List[str] = []
    pos = 0
    n = len(command)
    while pos < n:
        dollar = command.find("$(", pos)
        tick = ticks[bisect_left(ticks, pos)] if bisect_left(ticks, pos) < len(ticks) else -1
        candidates = [c for c in (dollar, tick) if c >= 0]
        if not candidates:
            break
        start = min(candidates)
        if start == dollar:
            k = bisect_left(parens, start + 2)
            if k < len(parens):
                out.append(command[start + 2:parens[k]])
                pos = parens[k] + 1
                continue
            # no ')' anywhere after: this `$(` cannot match; a backtick starting inside it still can
            pos = start + 1
            continue
        k = bisect_left(ticks, start + 1)
        if k < len(ticks):
            out.append(command[start + 1:ticks[k]])
            pos = ticks[k] + 1
        else:
            pos = start + 1  # an unpaired backtick: no later backtick exists, but a later `$(` still can match
    return out


def filename_matches(text: str) -> List[Tuple[str, str]]:
    """re.findall(r"([a-z_][a-z0-9_]*\\.(py|js|ts|java|cpp|go|rs|rb))", text)"""
    out: List[Tuple[str, str]] = []
    pos = 0
    for run in _IDENT_RUN.finditer(text):
        s, e = max(run.start(), pos), run.end()
        if s >= e or e >= len(text) or text[e] != ".":
            continue
        ext = next((x for x in _FILE_EXTENSIONS if text.startswith(x, e + 1)), None)
        if ext is None:
            continue
        # the identifier must begin with a letter or underscore: skip leading digits
        while s < e and text[s].isdigit():
            s += 1
        if s >= e:
            continue
        out.append((text[s:e + 1 + len(ext)], ext))
        pos = e + 1 + len(ext)
    return out


def path_matches(text: str) -> List[str]:
    """re.findall(r"([a-z_./][a-z0-9_./]*[a-z0-9_])", text)"""
    out: List[str] = []
    for run in _PATH_RUN.finditer(text):
        piece = run.group(0)
        first = next((i for i, ch in enumerate(piece) if not ch.isdigit()), -1)      # first char of [a-z_./]
        stripped = piece.rstrip("./")                                               # ends at the last [a-z0-9_]
        if first >= 0 and stripped and len(stripped) - 1 > first:
            out.append(piece[first:len(stripped)])
    return out


def token_counts(text: str) -> List[str]:
    """re.findall(r"(\\d+)\\s*tokens?", text)"""
    out: List[str] = []
    for m in re.finditer(r"(?<!\d)\d+", text):            # only a run's first digit can start a match
        j = m.end()
        while j < len(text) and text[j].isspace():
            j += 1
        if text.startswith("token", j):
            out.append(m.group(0))
    return out


def parameters_block(body: str) -> Optional[str]:
    """re.search(r"parameters\\s*\\{([^}]*)\\}", body, re.DOTALL).group(1)"""
    start = 0
    while True:
        i = body.find("parameters", start)
        if i < 0:
            return None
        j = i + len("parameters")
        while j < len(body) and body[j].isspace():
            j += 1
        if j < len(body) and body[j] == "{":
            k = body.find("}", j + 1)
            return None if k < 0 else body[j + 1:k]
        start = i + 1


def assignment(line: str) -> Optional[Tuple[str, str]]:
    """(group(1), group(2)) of re.match(r"(\\w+)\\s*=\\s*(.+)", line) for a line with no newline, or None."""
    idx = line.find("=")
    if idx <= 0:
        return None
    key = line[:idx].rstrip()
    if not key or not _WORD.fullmatch(key):
        return None
    value = line[idx + 1:].lstrip()
    if value:
        return key, value
    rest = line[idx + 1:]
    # `\s*` gives back one character so `.+` can match (never a newline: `.` does not match one)
    return (key, rest[-1]) if rest and rest[-1] != "\n" else None
