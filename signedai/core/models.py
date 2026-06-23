"""
SignedAI Core Models — compatibility shim
Re-exports from rct_platform/services/signedai/legacy/core/models.py

Uses importlib.util.spec_from_file_location to avoid name-clash with
the workspace-level `core/` package that lives on sys.path.
"""
import sys
import os
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_LEGACY_MODELS = os.path.normpath(
    os.path.join(_HERE, '..', '..', 'rct_platform', 'services', 'signedai', 'legacy', 'core', 'models.py')
)

# Load the legacy models.py under a unique module name to avoid conflicts
_spec = importlib.util.spec_from_file_location("_signedai_legacy_core_models", _LEGACY_MODELS)
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
AnalysisJob = _mod.AnalysisJob

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
