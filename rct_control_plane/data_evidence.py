"""
D in F = D^I x A, measured from the data this user really has (Round 51).

The Architect's definition: D is the user's own reality - what they actually
hold - and it is only useful when it is pointed by intent. Until Round 51 the
runtime's D only rated how clearly the request was worded (1.0 for any
sentence the IntentCompiler could classify), so D/I never blocked anything.
This module replaces that with evidence found in the user's own store:

  clarity    how well the request itself compiles (the old D, kept as one part)
  grounding  the things the goal points at (files) exist in the workspace, or
             for a goal that must have a target, it names one at all
  memory     stored memories in this namespace that are relevant to the goal
  skills     verified skills (that worked before) matching the goal
  record     this namespace's own track record: verified episodes for the
             same goal and overall

D is the weighted sum of those parts, in [0, 1]. Nothing is invented: every
part comes from a lookup that is returned in `parts`/`missing`, so a blocked
action can tell the user exactly which data would make it pass. A goal with
no clarity and no evidence at all scores D = 0, which the FDIA contract turns
into F = 0 (no data, no future).

Deliberately lexical (token overlap, same matcher as the rest of the runtime),
not embeddings: cheap, deterministic and testable. It is a first honest cut.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Weights sum to 1.0. Clarity and grounding are what a brand-new user can
# supply on the first request; the rest is earned by using the system.
WEIGHTS = {"clarity": 0.30, "grounding": 0.30, "memory": 0.15, "skills": 0.10, "record": 0.15}

MEMORY_RELEVANCE_FLOOR = 0.15   # same floor the VERIFY step uses for "related"
_FILE_EXTENSIONS = (
    "py|md|txt|json|toml|yaml|yml|csv|tsv|ts|tsx|js|jsx|mjs|html|css|ini|cfg|conf|log|sql|db|pdf|"
    "docx|xlsx|pptx|sh|bat|ps1|xml|rs|go|java|c|cpp|h|lock|env|ipynb|tf"
)
_PATH_RE = re.compile(
    r"(?<![\w@:/\\.-])((?:[A-Za-z]:[\\/])?(?:[\w.\-]+[\\/])*[\w.\-]+\.(?:" + _FILE_EXTENSIONS + r"))(?![\w-])",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://\S+")
_QUOTED_RE = re.compile(r"[\"'`“”‘’]([^\"'`“”‘’]{2,80})[\"'`“”‘’]")
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w.])")
_CREATE_VERBS = re.compile(r"\b(create|write|add|make|generate|scaffold|new)\b|สร้าง|เขียน|เพิ่ม", re.IGNORECASE)

# Intent types that act on something that must already exist / be named.
_NEEDS_TARGET = {"DEBUG", "REFACTOR", "TRANSFORM", "DEPLOY", "TEST", "OPTIMIZE", "MIGRATE"}


def extract_paths(goal: str) -> List[str]:
    """File-looking tokens in the goal ("pyproject.toml", "docs/a.md"). URLs
    are removed first so a domain is never mistaken for a file."""
    text = _URL_RE.sub(" ", goal)
    seen: List[str] = []
    for match in _PATH_RE.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def extract_values(goal: str) -> List[str]:
    """Explicit literal data the user typed into the goal: quoted strings,
    numbers and URLs. Data given inline is data the user really has."""
    text = goal
    values: List[str] = list(_URL_RE.findall(text))
    text = _URL_RE.sub(" ", text)
    values += [m for m in _QUOTED_RE.findall(text)]
    values += _NUMBER_RE.findall(_QUOTED_RE.sub(" ", text))
    return values


@dataclass
class DataEvidence:
    D: float
    parts: Dict[str, float]
    missing: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"D": self.D, "parts": self.parts, "missing": self.missing, "detail": self.detail}


def _resolve_inside(root: Path, raw: str) -> Optional[Path]:
    """The path under the workspace root, or None when it escapes it (a goal
    that names ../../secret is not grounded in the workspace)."""
    try:
        candidate = Path(raw)
        full = candidate if candidate.is_absolute() else root / candidate
        full = full.resolve()
        full.relative_to(root.resolve())
        return full
    except (ValueError, OSError):
        return None


def grounding_score(goal: str, intent_type: str, workspace_root: Path) -> Dict[str, Any]:
    paths = extract_paths(goal)
    values = extract_values(goal)
    creating = bool(_CREATE_VERBS.search(goal))
    detail: Dict[str, Any] = {"paths": {}, "values": len(values)}
    if paths:
        scores = []
        for raw in paths:
            full = _resolve_inside(workspace_root, raw)
            if full is not None and full.exists():
                detail["paths"][raw] = "exists"
                scores.append(1.0)
            elif full is not None and creating and full.parent.exists():
                detail["paths"][raw] = "new (parent exists)"
                scores.append(0.9)
            elif full is not None and creating:
                detail["paths"][raw] = "new (parent missing)"
                scores.append(0.4)
            else:
                detail["paths"][raw] = "missing" if full is not None else "outside the workspace"
                scores.append(0.0)
        score = sum(scores) / len(scores)
    elif intent_type in _NEEDS_TARGET:
        score = 0.35          # an action on "something" the goal never names
    else:
        score = 0.7           # asking/reading: the data lives in the user's workspace or tools, which the agent can search
    if values:
        score = min(1.0, score + 0.15 * min(len(values), 2))  # literal data typed in the goal
    return {"score": round(score, 4), **detail}


def assess(
    goal: str,
    *,
    clarity: float,
    intent_type: str = "UNKNOWN",
    workspace_root: Optional[Path] = None,
    memory_scores: Sequence[float] = (),
    skill_scores: Sequence[float] = (),
    same_goal_verified: int = 0,
    overall_verified_rate: float = 0.0,
) -> DataEvidence:
    """Compute D. `clarity` is the request's own quality from the compiler;
    the rest is looked up by the caller in the user's store."""
    root = workspace_root or Path(os.environ.get("DELENTIA_REPO_ROOT") or Path.cwd())
    grounding = grounding_score(goal, intent_type, root)

    relevant_memory = [s for s in memory_scores if s >= MEMORY_RELEVANCE_FLOOR]
    memory_part = min(1.0, max(relevant_memory, default=0.0) / 0.5) if relevant_memory else 0.0
    skills_part = min(1.0, max(skill_scores, default=0.0) / 0.5) if skill_scores else 0.0
    record_part = min(1.0, 0.5 * min(same_goal_verified / 2.0, 1.0) + 0.5 * max(0.0, min(overall_verified_rate, 1.0)))

    parts = {
        "clarity": round(max(0.0, min(1.0, clarity)), 4),
        "grounding": grounding["score"],
        "memory": round(memory_part, 4),
        "skills": round(skills_part, 4),
        "record": round(record_part, 4),
    }
    D = round(max(0.0, min(1.0, sum(WEIGHTS[k] * v for k, v in parts.items()))), 4)

    missing: List[str] = []
    missing_paths = [p for p, state in grounding["paths"].items() if state in ("missing", "outside the workspace")]
    if missing_paths:
        missing.append("files named in the goal that are not in the workspace: " + ", ".join(missing_paths))
    if not grounding["paths"] and intent_type in _NEEDS_TARGET:
        missing.append("name the file or object the action applies to")
    if parts["memory"] == 0.0:
        missing.append("no stored memory relevant to this goal (store facts about it with delentia_remember)")
    if parts["skills"] == 0.0:
        missing.append("no verified past solution for a similar goal")
    if parts["record"] == 0.0:
        missing.append("no verified track record yet for this goal")
    return DataEvidence(D=D, parts=parts, missing=missing, detail={"grounding": grounding})
