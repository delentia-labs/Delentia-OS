"""
Jailbreak Corpus Loader

Loads all JSONL case files from adversarial_tests/cases/ and exposes them
as a unified list of JailbreakCase objects for pytest parametrization.

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

# All JSONL corpus files
_CORPUS_DIR = Path(__file__).parent / "cases"
_CASE_FILES = [
    "dan_prompts.jsonl",
    "developer_mode.jsonl",
    "override_instructions.jsonl",
    "thai_jailbreak.jsonl",
    "role_escalation.jsonl",
]


@dataclass(frozen=True)
class JailbreakCase:
    """A single adversarial test case."""
    id: str                    # Unique case ID (e.g. "dan-001")
    category: str              # Category grouping
    prompt: str                # The adversarial prompt text
    expected_block: bool       # True = must be blocked by FDIA Constitution
    article: Optional[str]     # Expected constitutional article to trigger


def _load_file(path: Path) -> Iterator[JailbreakCase]:
    """Yield JailbreakCase objects from a single JSONL file."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
                yield JailbreakCase(
                    id=obj["id"],
                    category=obj["category"],
                    prompt=obj["prompt"],
                    expected_block=obj["expected_block"],
                    article=obj.get("article"),
                )
            except (json.JSONDecodeError, KeyError) as exc:
                raise ValueError(f"Malformed JSONL line in {path}: {line!r}") from exc


def load_corpus(categories: Optional[List[str]] = None) -> List[JailbreakCase]:
    """
    Load all adversarial test cases.

    Args:
        categories: Optional list of category names to filter.
                    If None, all categories are loaded.

    Returns:
        List of JailbreakCase sorted by case ID.
    """
    cases: List[JailbreakCase] = []
    for filename in _CASE_FILES:
        path = _CORPUS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Corpus file not found: {path}\n"
                f"Ensure you are running from the rct-platform root directory."
            )
        for case in _load_file(path):
            if categories is None or case.category in categories:
                cases.append(case)

    # Sort by ID for deterministic ordering
    cases.sort(key=lambda c: c.id)
    return cases


def load_all_cases() -> List[JailbreakCase]:
    """Load all cases. Alias for load_corpus() with no filter."""
    return load_corpus()


def stats(cases: Optional[List[JailbreakCase]] = None) -> dict:
    """Return statistics about the corpus."""
    if cases is None:
        cases = load_corpus()

    by_category: dict = {}
    for case in cases:
        by_category[case.category] = by_category.get(case.category, 0) + 1

    return {
        "total": len(cases),
        "must_block": sum(1 for c in cases if c.expected_block),
        "by_category": by_category,
    }
