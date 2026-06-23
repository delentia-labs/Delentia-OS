"""Intent Loop Engine: Evolutionary Compound Intelligence"""

__version__ = "1.0.0"

try:
    from .loop_engine import (
        IntentLoopEngine,
        JITNAPacket,
        IntentResult,
        IntentState,
        FDIAGatekeeper,
        MemoryLayer,
        SpecialistExecutor,
        SignedAIVerifier,
        EvolutionCommitter,
        SecurityViolation
    )
except ImportError:
    from loop_engine import (
        IntentLoopEngine,
        JITNAPacket,
        IntentResult,
        IntentState,
        FDIAGatekeeper,
        MemoryLayer,
        SpecialistExecutor,
        SignedAIVerifier,
        EvolutionCommitter,
        SecurityViolation
    )

__all__ = [
    "IntentLoopEngine",
    "JITNAPacket",
    "IntentResult",
    "IntentState",
    "FDIAGatekeeper",
    "MemoryLayer",
    "SpecialistExecutor",
    "SignedAIVerifier",
    "EvolutionCommitter",
    "SecurityViolation"
]
