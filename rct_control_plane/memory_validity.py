"""
Valid-from / valid-to for a memory (DAAES memory case, Round 84).

Some things are true only for a while: a price until the end of the quarter, a rule from the first of next month, a contact who has left. Revoking is for what was WRONG; a validity window is for what was
right and stopped being (or is not yet) right. The window is written by the person, never guessed by the system.

How: two optional ISO-8601 bounds in the memory's `context` (`valid_from`, inclusive; `valid_to`, exclusive; a date alone means 00:00 UTC; a time without a zone is read as UTC). Nothing is deleted or
rewritten: a memory outside its window is simply not returned by the readers that serve the model (they all come through `Persistence.list_memories` / `pinned_memories`); the audit view
(`include_revoked=True`) still shows it. The bounds travel in the memory's event in the event log, so "what did the agent believe on the 3rd" is answerable from the log as before.

What it does not do: it does not parse "until Friday" from the text of a memory, and it does not make the system notice that a memory has become stale by itself; only a bound the person set counts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

FROM_KEY, TO_KEY = "valid_from", "valid_to"


def parse_bound(value: Any) -> Optional[float]:
    """Epoch seconds for a bound, or None when there is none. Raises ValueError for text that is not a date, so a typo is refused at write time rather than silently ignored."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{text!r} is not an ISO date or time (for example 2026-12-31 or 2026-12-31T17:00:00+07:00)") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def window(context: Any) -> Tuple[Optional[float], Optional[float]]:
    """(valid_from, valid_to) of a memory's context; an unreadable stored bound counts as no bound (it was validated when written)."""
    if not isinstance(context, dict):
        return None, None
    out = []
    for key in (FROM_KEY, TO_KEY):
        try:
            out.append(parse_bound(context.get(key)))
        except ValueError:
            out.append(None)
    return out[0], out[1]


def is_valid_at(memory: Dict[str, Any], now: Optional[float] = None) -> bool:
    start, end = window(memory.get("context"))
    at = datetime.now(timezone.utc).timestamp() if now is None else now
    return (start is None or at >= start) and (end is None or at < end)


def with_bounds(context: Optional[Dict[str, Any]], valid_from: Any = None, valid_to: Any = None) -> Dict[str, Any]:
    """The context with the bounds written in (validated; an empty window is refused). Returns a new dictionary."""
    start, end = parse_bound(valid_from), parse_bound(valid_to)
    if start is not None and end is not None and end <= start:
        raise ValueError("valid_to must be later than valid_from")
    merged = dict(context or {})
    if valid_from not in (None, ""):
        merged[FROM_KEY] = str(valid_from)
    if valid_to not in (None, ""):
        merged[TO_KEY] = str(valid_to)
    return merged


def describe(memory: Dict[str, Any], now: Optional[float] = None) -> str:
    """'' for a memory with no window, otherwise a short phrase for lists: 'valid until ...', 'valid from ...', or 'EXPIRED'/'NOT YET VALID'."""
    start, end = window(memory.get("context"))
    if start is None and end is None:
        return ""
    at = datetime.now(timezone.utc).timestamp() if now is None else now
    if end is not None and at >= end:
        return "EXPIRED " + datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d")
    if start is not None and at < start:
        return "NOT YET VALID until " + datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%d")
    parts = []
    if start is not None:
        parts.append("from " + datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%d"))
    if end is not None:
        parts.append("until " + datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d"))
    return "valid " + " ".join(parts)
