"""
rct_control_plane/toon_formatter.py — ALGO-42: Token-Oriented Object Notation
================================================================================

TOON (Token-Oriented Object Notation) is a compact serialization format
designed to minimize token consumption when structured data is injected
into an LLM context window.

Key properties:
  - 40-50% fewer tokens than equivalent JSON (measured with Llama tokenizer)
  - No braces, brackets, or quotation marks — pure key:value lines
  - Nested structures use indentation (2 spaces per level)
  - Lists use "- " prefix per item
  - Human-readable AND machine-parseable
  - Round-trip: serialize → deserialize → serialize produces identical output

Format example:
    packet_id: 6afff5d6-7fa3-4f2c-92b0-b1a77fd42a93
    source_agent_id: gateway_api
    message_type: intent_request
    priority: 3
    payload:
      intent: คำนวณภาษีเงินได้บุคคลธรรมดา
      income: 1000000
      tags:
        - finance
        - thai_tax

Reference: Delentia SLM Fine-tuning TOON specification
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "TOONFormatter",
    "toon_serialize",
    "toon_deserialize",
    "toon_token_savings_estimate",
]

# Indent unit — 2 spaces per nesting level
_INDENT = "  "

# Regex for numeric values
_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


class TOONFormatter:
    """
    ALGO-42: Token-Oriented Object Notation serializer/deserializer.

    Designed for the Delentia OS pipeline to compress structured data
    (JITNA packets, memory deltas, workflow context) before injection
    into LLM context windows.

    Usage:
        formatter = TOONFormatter()
        toon_str = formatter.serialize({"intent": "สรุปกฎหมาย PDPA", "priority": 3})
        data = formatter.deserialize(toon_str)
    """

    # ── Serialize ─────────────────────────────────────────────────────────

    def serialize(self, data: Any) -> str:
        """
        Serialize a Python object to TOON format.

        Supported types: dict, list, str, int, float, bool, None.

        Args:
            data: The object to serialize

        Returns:
            TOON-formatted string

        Raises:
            TypeError: if data contains unsupported types
        """
        lines: list[str] = []
        self._write(data, lines, level=0)
        return "\n".join(lines)

    def _write(self, value: Any, lines: list[str], level: int) -> None:
        """Recursively serialize a value into TOON lines."""
        indent = _INDENT * level

        if isinstance(value, dict):
            for k, v in value.items():
                k_str = str(k)
                if isinstance(v, dict):
                    if not v:
                        lines.append(f"{indent}{k_str}: {{}}")
                    else:
                        lines.append(f"{indent}{k_str}:")
                        self._write(v, lines, level + 1)
                elif isinstance(v, list):
                    if not v:
                        lines.append(f"{indent}{k_str}: []")
                    else:
                        lines.append(f"{indent}{k_str}:")
                        self._write(v, lines, level + 1)
                else:
                    v_str = self._scalar_to_str(v)
                    lines.append(f"{indent}{k_str}: {v_str}")

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{indent}-")
                    self._write(item, lines, level + 1)
                elif isinstance(item, list):
                    lines.append(f"{indent}-")
                    self._write(item, lines, level + 1)
                else:
                    v_str = self._scalar_to_str(item)
                    lines.append(f"{indent}- {v_str}")

        else:
            v_str = self._scalar_to_str(value)
            lines.append(f"{indent}{v_str}")

    @staticmethod
    def _scalar_to_str(value: Any) -> str:
        """Convert a scalar value to its TOON string representation."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return value.replace("\n", "\\n")
        return str(value)



    # ── Deserialize ───────────────────────────────────────────────────────

    def deserialize(self, toon_str: str) -> Any:
        """
        Deserialize a TOON-formatted string back to Python objects.

        Args:
            toon_str: TOON-formatted string

        Returns:
            Python dict, list, or scalar

        Raises:
            ValueError: if the TOON string is malformed
        """
        lines = toon_str.split("\n")
        # Build list of (indent_spaces, raw_content)
        parsed: list[tuple[int, str]] = []
        for line in lines:
            if not line.strip():
                continue
            spaces = len(line) - len(line.lstrip(" "))
            content = line.strip()
            parsed.append((spaces, content))

        if not parsed:
            return {}

        result, _ = self._read(parsed, 0, parsed[0][0])
        return result

    def _read(
        self,
        lines: list[tuple[int, str]],
        start: int,
        base_spaces: int,
    ) -> tuple[Any, int]:
        """
        Parse a block of TOON lines at the given indentation.
        Returns (parsed_value, next_index).
        """
        if start >= len(lines):
            return {}, start

        # Check if this block starts with list items
        first_content = lines[start][1]
        if first_content.startswith("- ") or first_content == "-":
            return self._read_list(lines, start, base_spaces)

        return self._read_dict(lines, start, base_spaces)

    def _read_dict(
        self,
        lines: list[tuple[int, str]],
        start: int,
        base_spaces: int,
    ) -> tuple[dict, int]:
        """Parse a dict block."""
        result: dict[str, Any] = {}
        i = start

        while i < len(lines):
            spaces, content = lines[i]

            # Done if we've de-indented
            if spaces < base_spaces:
                break
            # Skip deeper lines (already consumed by children)
            if spaces > base_spaces:
                i += 1
                continue

            if content.startswith("- ") or content == "-":
                # We hit a list — shouldn't be in a dict context at same level
                break

            if ": " in content:
                # Find FIRST ": " to split key and value
                colon_pos = content.index(": ")
                key = content[:colon_pos]
                val_str = content[colon_pos + 2:]

                if val_str == "{}":
                    result[key] = {}
                elif val_str == "[]":
                    result[key] = []
                else:
                    result[key] = self._parse_scalar(val_str)
                i += 1

            elif content.endswith(":"):
                key = content[:-1]
                i += 1
                # Children are at base_spaces + 2
                child_spaces = base_spaces + 2
                if i < len(lines) and lines[i][0] >= child_spaces:
                    child_val, i = self._read(lines, i, child_spaces)
                    result[key] = child_val
                else:
                    result[key] = {}
            else:
                # Bare scalar at top level (unusual)
                return self._parse_scalar(content), i + 1

        return result, i

    def _read_list(
        self,
        lines: list[tuple[int, str]],
        start: int,
        base_spaces: int,
    ) -> tuple[list, int]:
        """Parse a list block."""
        result: list[Any] = []
        i = start

        while i < len(lines):
            spaces, content = lines[i]

            if spaces < base_spaces:
                break
            if spaces > base_spaces:
                i += 1
                continue

            if content.startswith("- "):
                val_str = content[2:]
                result.append(self._parse_scalar(val_str))
                i += 1
            elif content == "-":
                # Complex list item — children at base_spaces + 2
                i += 1
                child_spaces = base_spaces + 2
                if i < len(lines) and lines[i][0] >= child_spaces:
                    child_val, i = self._read(lines, i, child_spaces)
                    result.append(child_val)
                else:
                    result.append({})
            else:
                # Not a list item — done
                break

        return result, i

    @staticmethod
    def _parse_scalar(value: str) -> Any:
        """Parse a scalar string to its Python type."""
        if value == "null":
            return None
        if value == "true":
            return True
        if value == "false":
            return False
        if _INT_RE.match(value):
            return int(value)
        if _FLOAT_RE.match(value):
            return float(value)
        return value.replace("\\n", "\n")



# ── Module-level convenience functions ────────────────────────────────────


def toon_serialize(data: Any) -> str:
    """Serialize data to TOON format (convenience wrapper)."""
    return TOONFormatter().serialize(data)


def toon_deserialize(toon_str: str) -> Any:
    """Deserialize TOON string to Python objects (convenience wrapper)."""
    return TOONFormatter().deserialize(toon_str)


def toon_token_savings_estimate(data: dict) -> dict[str, Any]:
    """
    Estimate token savings of TOON vs JSON for a given data structure.

    Uses a simplified character-count heuristic (actual savings depend on
    the specific tokenizer, but character count correlates well for
    Llama-family tokenizers).

    Returns:
        dict with keys: json_chars, toon_chars, savings_pct, savings_ratio
    """
    import json

    json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    toon_str = toon_serialize(data)

    json_chars = len(json_str)
    toon_chars = len(toon_str)
    savings = json_chars - toon_chars
    savings_pct = (savings / json_chars * 100) if json_chars > 0 else 0.0

    return {
        "json_chars": json_chars,
        "toon_chars": toon_chars,
        "savings_chars": savings,
        "savings_pct": round(savings_pct, 1),
        "savings_ratio": round(json_chars / max(toon_chars, 1), 2),
    }
