"""
SignedAI Core Models — compatibility shim
Re-exports from rct_platform/services/signedai/legacy/core/models.py

Uses importlib.util.spec_from_file_location to avoid name-clash with
the workspace-level `core/` package that lives on sys.path.
"""
import sys
import os
import importlib.util
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.path.join(_HERE, '..', '..', 'rct_platform', 'services', 'signedai', 'legacy', 'core', 'models.py'),
    os.path.join(_HERE, '..', '..', '..', 'Delentia-Private-OS', 'rct_platform', 'services', 'signedai', 'legacy', 'core', 'models.py'),
]
_LEGACY_MODELS = ""
for path in _CANDIDATES:
    norm_path = os.path.normpath(path)
    if os.path.exists(norm_path):
        _LEGACY_MODELS = norm_path
        break

if not _LEGACY_MODELS:
    _LEGACY_MODELS = os.path.normpath(_CANDIDATES[0])

_spec = importlib.util.spec_from_file_location("_signedai_legacy_core_models", _LEGACY_MODELS)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load legacy models module from spec: {_LEGACY_MODELS}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_signedai_legacy_core_models"] = _mod
_spec.loader.exec_module(_mod)


# Re-export all public names
RiskLevel = _mod.RiskLevel
TierLevel = _mod.TierLevel
Verdict = _mod.Verdict
Certification = _mod.Certification
AnalysisStatus = _mod.AnalysisStatus
JITNAPacket = _mod.JITNAPacket
AnalysisRequest = _mod.AnalysisRequest
SignerVote = _mod.SignerVote
ConsensusResult = _mod.ConsensusResult
from pydantic import Field
AnalysisJob = _mod.AnalysisJob

# Add the artifact_content field dynamically to class to prevent modifying private repository
class AnalysisJob(AnalysisJob):  # type: ignore[no-redef]
    artifact_content: Optional[str] = Field(None, description="เนื้อหาที่วิเคราะห์")


__all__ = [
    "RiskLevel",
    "TierLevel",
    "Verdict",
    "Certification",
    "AnalysisStatus",
    "JITNAPacket",
    "AnalysisRequest",
    "SignerVote",
    "ConsensusResult",
    "AnalysisJob",
]
