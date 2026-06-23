"""
Analysearch Phase 3 — Blueprint Generator
Converts AnalysearchResult objects into structured JSON blueprints
and Markdown documents for downstream consumption.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional


class BlueprintStyle:
    RESEARCH_PROPOSAL = "research_proposal"
    IMPLEMENTATION_PLAN = "implementation_plan"
    COMPARATIVE_ANALYSIS = "comparative_analysis"

    ALL = [RESEARCH_PROPOSAL, IMPLEMENTATION_PLAN, COMPARATIVE_ANALYSIS]


class BlueprintGenerator:
    """
    Generates structured blueprints from Analysearch results.

    Supports three output styles:
    - ``research_proposal``: Academic research framing
    - ``implementation_plan``: Engineering task breakdown
    - ``comparative_analysis``: Side-by-side evaluation
    """

    def __init__(self, author: str = "RCT Analysearch", version: str = "3.0"):
        self.author = author
        self.version = version

    # ── Public API ───────────────────────────────────────────────────────

    def generate(self, result: object, style: str = BlueprintStyle.RESEARCH_PROPOSAL) -> Dict:
        """
        Generate a blueprint dict from an AnalysearchResult.

        Args:
            result: AnalysearchResult (or any object with .query, .keywords,
                    .analysis, .synthesis, .confidence attributes).
            style: Output style — one of BlueprintStyle.ALL.

        Returns:
            Blueprint dictionary.
        """
        if style not in BlueprintStyle.ALL:
            raise ValueError(f"Unknown style '{style}'. Choose from {BlueprintStyle.ALL}")

        base = self._build_base(result)
        if style == BlueprintStyle.RESEARCH_PROPOSAL:
            return {**base, **self._research_sections(result)}
        if style == BlueprintStyle.IMPLEMENTATION_PLAN:
            return {**base, **self._implementation_sections(result)}
        # comparative_analysis
        return {**base, **self._comparative_sections(result)}

    def to_markdown(self, blueprint: Dict) -> str:
        """Render a blueprint dict as a Markdown document."""
        lines = [f"# {blueprint.get('title', 'Blueprint')}", ""]
        for key, value in blueprint.items():
            if key in ("title", "generated_at", "author", "version", "blueprint_id"):
                continue
            lines.append(f"## {key.replace('_', ' ').title()}")
            lines.append("")
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        lines.append(
                            "- " + ", ".join(f"**{k}**: {v}" for k, v in item.items())
                        )
                    else:
                        lines.append(f"- {item}")
            elif isinstance(value, dict):
                for k, v in value.items():
                    lines.append(f"- **{k}**: {v}")
            else:
                lines.append(str(value))
            lines.append("")
        return "\n".join(lines)

    def to_json(self, blueprint: Dict, indent: int = 2) -> str:
        """Serialise a blueprint dict to a JSON string."""
        return json.dumps(blueprint, ensure_ascii=False, indent=indent, default=str)

    # ── Internal builders ────────────────────────────────────────────────

    def _build_base(self, result: object) -> Dict:
        query = getattr(result, "query", "")
        confidence = getattr(result, "confidence", 0.0)
        return {
            "blueprint_id": f"bp-{abs(hash(query)) % 100000:05d}",
            "title": f"Blueprint: {query[:60]}",
            "query": query,
            "confidence": confidence,
            "author": self.author,
            "version": self.version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _research_sections(self, result: object) -> Dict:
        keywords = getattr(result, "keywords", [])
        synthesis = getattr(result, "synthesis", {})
        analysis = getattr(result, "analysis", {})
        return {
            "research_question": getattr(result, "query", ""),
            "hypotheses": [
                f"H{i+1}: {kw.get('keyword', kw) if isinstance(kw, dict) else kw} may influence the outcome"
                for i, kw in enumerate(keywords[:3])
            ],
            "methodology": {
                "approach": "Mixed methods (qualitative + quantitative)",
                "disciplines": synthesis.get("disciplines_detected", 0),
                "intersections": len(synthesis.get("intersections", [])),
            },
            "expected_outcomes": synthesis.get("insights", ["Further investigation required"]),
            "keywords": [kw.get("keyword", kw) if isinstance(kw, dict) else kw for kw in keywords[:10]],
        }

    def _implementation_sections(self, result: object) -> Dict:
        keywords = getattr(result, "keywords", [])
        analysis = getattr(result, "analysis", {})
        return {
            "objective": getattr(result, "query", ""),
            "tasks": [
                {"step": i + 1, "action": f"Implement {kw.get('keyword', kw) if isinstance(kw, dict) else kw} component"}
                for i, kw in enumerate(keywords[:5])
            ],
            "dependencies": [],
            "estimated_complexity": "medium" if len(keywords) < 8 else "high",
            "success_criteria": [
                f"All {len(keywords)} keyword domains covered",
                "Integration tests green",
                "Performance benchmarks met",
            ],
        }

    def _comparative_sections(self, result: object) -> Dict:
        keywords = getattr(result, "keywords", [])
        synthesis = getattr(result, "synthesis", {})
        disciplines = synthesis.get("disciplines", [])
        return {
            "subject": getattr(result, "query", ""),
            "dimensions": [kw.get("keyword", kw) if isinstance(kw, dict) else kw for kw in keywords[:6]],
            "alternatives": [
                {
                    "name": d.get("name", f"Option {i+1}"),
                    "strengths": d.get("key_concepts", [])[:2],
                    "score": round(d.get("relevance", 0.5), 3),
                }
                for i, d in enumerate(disciplines[:4])
            ],
            "recommendation": "Select the approach with highest cross-disciplinary synthesis score",
        }
