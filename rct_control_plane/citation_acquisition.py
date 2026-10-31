"""Bounded source acquisition for an already-authorized application context.

No client-supplied source text is accepted. The service owns authorization and
supplies a durable receipt callback. Hashes are not signatures/source truth.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Callable

from pydantic import Field

from rct_control_plane.citation_verifier import SourceBundle, SourceText
from rct_control_plane.intent_review import ReviewBinding
from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.verified_budget import QuoteEvidence, current_bytes, digest


class AcquisitionContext(PlanItem):
    binding: ReviewBinding
    contract_id: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=1)
    plan_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def acquire_citation_sources(
    root: Path, requested: dict[str, dict], allowed_paths: set[str],
    context: AcquisitionContext, on_receipt: Callable[[dict], None],
) -> SourceBundle:
    """Read at most 16 files, each using the existing 20 KB no-follow reader.

    All lexical/allowlist checks precede reads. Publish a single batch receipt
    before returning any bundle; a failed persistence callback propagates.
    Caller must not schedule observations before this function returns.
    This is not an atomic multi-file snapshot or an authorization endpoint.
    """
    from rct_control_plane.intent_contract import _file
    context = AcquisitionContext.model_validate(context.model_dump())
    if context.binding.workspace_root != str(root.resolve()):
        raise ValueError('acquisition workspace binding mismatch')
    if not 1 <= len(requested) <= 16:
        raise ValueError('acquisition requires 1..16 sources')
    specs = {key: QuoteEvidence.model_validate(copy.deepcopy(value)) for key, value in requested.items()}
    paths = []
    for key, spec in specs.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 80:
            raise ValueError('invalid source identity')
        if spec.relative_path not in allowed_paths:
            raise ValueError('citation source is not authorized')
        _file(root, spec.relative_path)
        paths.append(spec.relative_path)
    if len(set(paths)) != len(paths):
        raise ValueError('duplicate source path')
    sources = []
    observations = []
    for key, spec in specs.items():
        raw = current_bytes(root, spec.relative_path)
        actual = hashlib.sha256(raw).hexdigest()
        if actual != spec.sha256:
            raise ValueError('citation source changed since plan review')
        sources.append(SourceText(source_id=key, text=raw.decode('utf-8', errors='strict'), sha256=actual))
        observations.append({'source_id': key, 'relative_path': spec.relative_path, 'sha256': actual,
                             'byte_length': len(raw)})
    bundle = SourceBundle(sources=sources)
    payload = {'schema_version': 1, 'kind': 'citation_acquisition',
               'context': context.model_dump(), 'observations': observations,
               'source_bundle_sha256': digest(bundle.model_dump())}
    on_receipt(copy.deepcopy({**payload, 'receipt_sha256': digest(payload)}))
    return bundle
