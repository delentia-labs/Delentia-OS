"""
RCT Intent Loop — public interface stub

The intent loop orchestrates the full lifecycle of an intent: compilation,
policy evaluation, graph construction, execution, and replay.

Full implementation lives in the private microservices layer;
this stub documents the public surface.

**Reference implementation (included in this public SDK):**
  ``microservices/intent-loop/loop_engine.py``

The reference service demonstrates all major intent-loop components:
- IntentState enum and JITNAPacket protocol
- FDIA-gated execution (FDIAGatekeeper)
- In-memory cache layer (use Redis in production)
- MemoryLayer with SHA-256 content addressing
- SpecialistExecutor routing table
- IntentLoopEngine with full async lifecycle

To run the reference service::

    cd microservices/intent-loop
    uvicorn loop_api:app --reload
"""

__version__ = "1.1.0"

from .models import IntentBlueprint, FarmResult  # noqa: F401
from .intent_farmer import IntentFarmer  # noqa: F401

__all__ = [
    "IntentFarmer",
    "IntentBlueprint",
    "FarmResult",
]
