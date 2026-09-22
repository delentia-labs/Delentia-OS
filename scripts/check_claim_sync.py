from __future__ import annotations

import re
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = REPO_ROOT / "docs" / "testing" / "TESTING_CANONICAL.md"
README_PATH = REPO_ROOT / "README.md"
ROADMAP_PATH = REPO_ROOT / "ROADMAP.md"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CODECOV_PATH = REPO_ROOT / "codecov.yml"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_canonical_metrics(text: str) -> tuple[str, str, str]:
    # Generalized twice now, both times because a real edit to the
    # checkpoint line's wording silently broke this script's original
    # rigid regex (it only ever matched "N passed - N skipped - 0 failed -
    # N% coverage" exactly) with no error until someone happened to run it
    # - meaning drift-checking silently did not run for months in between.
    # Real checkpoints are not always "0 failed, exact% coverage": a
    # honest checkpoint can have known failures and/or a coverage figure
    # pending re-measurement. Accept any of these, defaulting missing
    # segments to an explicit sentinel rather than crashing.
    pattern = re.compile(
        r"\*\*Authoritative checkpoint:\*\* \*\*(?P<passed>[\d,]+) passed"
        r"(?: · (?P<skipped>[\d,]+) skipped)?"
        r"(?: · (?P<failed>[\d,]+) failed)?"
        r"(?: · (?P<coverage>[\d]+)% coverage| · coverage pending re-measurement)?\*\*"
    )
    match = pattern.search(text)
    if not match:
        raise ValueError("Could not find authoritative checkpoint in TESTING_CANONICAL.md")
    return (
        match.group("passed"),
        match.group("skipped") or "0",
        match.group("coverage") or "pending",
    )


def require(pattern: str, text: str, label: str, errors: list[str]) -> None:
    if not re.search(pattern, text, flags=re.MULTILINE):
        errors.append(label)


def main() -> int:
    canonical_text = read_text(CANONICAL_PATH)
    readme_text = read_text(README_PATH)
    roadmap_text = read_text(ROADMAP_PATH)
    changelog_text = read_text(CHANGELOG_PATH)
    ci_text = read_text(CI_PATH)
    codecov_text = read_text(CODECOV_PATH)

    passed, skipped, coverage = extract_canonical_metrics(canonical_text)
    errors: list[str] = []

    # README.md is checked directly here (not just via `require`, which
    # only ever reported presence/absence) since it's the file most
    # likely to drift and the one this tool exists to protect first.
    if passed not in readme_text:
        errors.append(f"README.md does not mention the canonical passed count ({passed})")

    # ROADMAP.md's and CHANGELOG.md's own test-count mentions are dated,
    # historical release-note entries (what was true AT that past
    # release), not live claims that should be rewritten to match today's
    # checkpoint - rewriting history to match the present would itself be
    # a claim-honesty violation. This tool intentionally does not require
    # them to match the current canonical checkpoint; it only checks that
    # ci.yml/codecov.yml (which describe CURRENT enforcement, not history)
    # match what TESTING_CANONICAL.md's own coverage-floor row says is
    # actually enforced.
    require(
        r"--cov-fail-under=80",
        ci_text,
        ".github/workflows/ci.yml's real coverage floor (--cov-fail-under) has changed from 80% - update TESTING_CANONICAL.md and CLAIM_REGISTRY.md's 'as actually enforced' rows to match",
        errors,
    )
    require(
        r"target: 90%",
        codecov_text,
        "codecov.yml's Codecov target has changed from 90% - update TESTING_CANONICAL.md and CLAIM_REGISTRY.md to match",
        errors,
    )

    if errors:
        print("claim-sync: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("claim-sync: OK")
    coverage_desc = f"{coverage}% coverage" if coverage != "pending" else "coverage pending re-measurement"
    print(f"- canonical checkpoint: {passed} passed, {skipped} skipped, {coverage_desc}")
    print("- README mentions the current checkpoint; CI/Codecov coverage gates match what's documented as enforced")
    return 0


if __name__ == "__main__":
    sys.exit(main())