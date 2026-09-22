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
    # The "skipped" segment is optional: TESTING_CANONICAL.md's checkpoint
    # line has drifted between "N passed · N skipped · 0 failed · N%
    # coverage" and a shorter "N passed · 0 failed · N% coverage" form over
    # past updates, which silently broke this script (it always raised
    # ValueError against the shorter form, so drift-checking has not
    # actually run since whichever edit dropped that segment). Accepting
    # both forms - defaulting skipped to "0" when absent - makes this
    # script actually run against the doc's real current content instead
    # of requiring a specific historical formatting choice.
    pattern = re.compile(
        r"\*\*Authoritative checkpoint:\*\* \*\*(?P<passed>[\d,]+) passed · "
        r"(?:(?P<skipped>[\d,]+) skipped · )?0 failed · (?P<coverage>[\d]+)% coverage\*\*"
    )
    match = pattern.search(text)
    if not match:
        raise ValueError("Could not find authoritative checkpoint in TESTING_CANONICAL.md")
    return match.group("passed"), match.group("skipped") or "0", match.group("coverage")


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

    require(
        rf"{re.escape(passed)} passed .* {re.escape(skipped)} skipped .* {re.escape(coverage)}% coverage",
        readme_text,
        "README.md is missing the canonical pass/skip/coverage checkpoint",
        errors,
    )
    require(
        rf"{re.escape(passed)} passed, {re.escape(skipped)} skipped, {re.escape(coverage)}% coverage",
        roadmap_text,
        "ROADMAP.md is missing the canonical checkpoint summary",
        errors,
    )
    require(
        rf"{re.escape(passed)} passed .* {re.escape(skipped)} skipped .* {re.escape(coverage)}% coverage",
        changelog_text,
        "CHANGELOG.md Unreleased section is missing the canonical checkpoint summary",
        errors,
    )
    require(
        r"--cov-fail-under=90",
        ci_text,
        ".github/workflows/ci.yml is not enforcing the 90% coverage floor",
        errors,
    )
    require(
        r"target: 90%",
        codecov_text,
        "codecov.yml is not enforcing the 90% coverage target",
        errors,
    )

    if errors:
        print("claim-sync: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("claim-sync: OK")
    print(f"- canonical checkpoint: {passed} passed, {skipped} skipped, {coverage}% coverage")
    print("- README, ROADMAP, CHANGELOG, CI, and Codecov are aligned")
    return 0


if __name__ == "__main__":
    sys.exit(main())