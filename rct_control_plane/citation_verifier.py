"""Bounded extractive citation oracle, not an abstractive-summary truth judge.

Application code supplies required source identities and governed observations.
Matching hashes prove text consistency, not source authenticity or freshness.
Offsets are UTF-8 byte offsets, shared across Python/JavaScript consumers.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import ConfigDict, Field

from rct_control_plane.component_execution import CriterionVerification, Handler
from rct_control_plane.intent_conditions import CriterionCapability, NecessaryCondition
from rct_control_plane.rct_plan import PlanItem


class ExactText(PlanItem):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=False)


class SourceText(ExactText):
    source_id: str = Field(min_length=1, max_length=80)
    text: str = Field(max_length=200000)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class SourceBundle(PlanItem):
    sources: list[SourceText] = Field(min_length=1, max_length=16)


class Extract(ExactText):
    source_id: str = Field(min_length=1, max_length=80)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=16000)


class ExtractiveReport(PlanItem):
    schema_version: Literal['1']
    offset_encoding: Literal['utf-8-bytes']
    extracts: list[Extract] = Field(min_length=1, max_length=100)


class CitationInput(PlanItem):
    sources: SourceBundle
    report: ExtractiveReport
    criterion_id: str = Field(min_length=1, max_length=80)
    required_source_ids: list[str] = Field(min_length=1, max_length=16)


class CitationVerdict(CriterionVerification):
    verification_scope: Literal['exact_extractive_citations'] = 'exact_extractive_citations'
    reasons: list[str]


def verify_extracts(value: CitationInput) -> dict:
    """Every extract must equal its source span; all required sources must occur.

    Does not accept paraphrases, infer entailment or assess summary completeness.
    No file reads, model calls, tools or side effects.
    """
    reasons: set[str] = set()
    sources = {s.source_id: s for s in value.sources.sources}
    required = set(value.required_source_ids)
    if len(sources) != len(value.sources.sources):
        reasons.add('duplicate_source_identity')
    if len(required) != len(value.required_source_ids) or any(not s.strip() for s in required):
        reasons.add('invalid_required_sources')
    if set(sources) != required:
        reasons.add('source_set_mismatch')
    for source in sources.values():
        if hashlib.sha256(source.text.encode('utf-8')).hexdigest() != source.sha256:
            reasons.add('source_digest_mismatch')
    covered: set[str] = set()
    seen: set[tuple] = set()
    for extract in value.report.extracts:
        key = (extract.source_id, extract.start, extract.end)
        if key in seen:
            reasons.add('duplicate_extract')
        seen.add(key)
        cited_source = sources.get(extract.source_id)
        if cited_source is None:
            reasons.add('unknown_citation_source')
            continue
        raw = cited_source.text.encode('utf-8')
        if (extract.start >= extract.end or extract.end > len(raw) or not extract.text.strip()
                or raw[extract.start:extract.end] != extract.text.encode('utf-8')):
            reasons.add('citation_span_mismatch')
            continue
        covered.add(extract.source_id)
    if not required <= covered:
        reasons.add('required_source_not_cited')
    return CitationVerdict(criterion_id=value.criterion_id, satisfied=not reasons,
                           reasons=sorted(reasons)).model_dump()


class AcquisitionRequest(PlanItem):
    """Dispatcher owns acquisition and binds sources outside this pure registry."""


def citation_registry() -> dict[str, Handler]:
    return {
        'observed_texts_v1': Handler(AcquisitionRequest, SourceBundle, 'observation', None),
        'verify_extracts_v1': Handler(CitationInput, CitationVerdict, 'verify', verify_extracts),
    }


def citation_capability() -> CriterionCapability:
    return CriterionCapability(frozenset({'verify_extracts_v1'}), (
        NecessaryCondition('observed_sources', frozenset({'observed_texts_v1'})),
    ))
