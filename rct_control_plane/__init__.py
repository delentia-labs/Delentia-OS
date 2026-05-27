"""
RCT Control Plane — public API

Exports all public symbols from the three core modules that are present
in this repository. Additional modules (jitna_protocol, intent_compiler, etc.)
will be added in future releases.

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from ._version import PACKAGE_VERSION

__version__ = PACKAGE_VERSION

from .intent_schema import (
    IntentType,
    IntentPriority,
    RiskProfile,
    ScopeType,
    ConstraintType,
    IntentObject,
    ScopeObject,
    BudgetSpec,
    IntentConstraint,
    ContextBundle,
    IntentGrammar,
    ValidationResult,
)
from .execution_graph_ir import (
    NodeType,
    DependencyType,
    NodeStatus,
    ResourceRequirement,
    ExecutionNode,
    DependencyEdge,
    ExecutionGraph,
)
from .dsl_parser import (
    DSLParser,
    DSLParseError,
)
from .cord_security import (
    CORDEngine,
    CORDResult,
    CORDVerdict,
    CORDFinding,
    CORDCheckType,
    cord_check,
)
from .mee_engine import (
    MEEEngine,
    MEESession,
    MEEStepRecord,
    MEE_VERSION,
)
from .governance_gate import (
    GovernanceGate,
    GovernanceVerdict,
    GovernanceOutcome,
    GovernancePolicy,
    GovernanceError,
    PolicyFlag,
    GOVERNANCE_GATE_VERSION,
)
from .persistence_pg import (
    PostgresPersistence,
    get_persistence,
    POSTGRES_PERSISTENCE_VERSION,
)
from .jitna_protocol_v3 import (
    JITNAPacketV3,
    JITNAMessageTypeV3,
    JITNARouter,
    TTLExpiredError,
    JITNA_V3_SCHEMA_VERSION,
    stream as jitna_stream,
    pack_compressed,
    unpack_compressed,
)
from .zk_fdia import (
    ZKFDIAProver,
    ZKFDIAVerifier,
    ZKFDIACommitment,
    ZK_FDIA_VERSION,
)
from .helix_ttd import (
    HelixStateVector,
    TopologicalDriftDetector,
    HelixHistory,
    DriftAlert,
    drift_velocity,
    HELIX_TTD_VERSION,
    HELIX_STATE_DIM,
)
from .payment_engine import (
    PaymentEngine,
    SubscriptionTier,
    TierPolicy,
    TIER_POLICIES,
    BillingRecord,
    BillingError,
    FDIAGateError,
    DailyLimitExceededError,
    StripeEventError,
    PAYMENT_ENGINE_VERSION,
)
from .node_network import (
    Node,
    NodeNetwork,
    BroadcastResult,
    ConsensusResult,
    NODE_NETWORK_VERSION,
    CONSENSUS_THRESHOLD,
)

__all__ = [
    "__version__",
    # intent_schema
    "IntentType",
    "IntentPriority",
    "RiskProfile",
    "ScopeType",
    "ConstraintType",
    "IntentObject",
    "ScopeObject",
    "BudgetSpec",
    "IntentConstraint",
    "ContextBundle",
    "IntentGrammar",
    "ValidationResult",
    # execution_graph_ir
    "NodeType",
    "DependencyType",
    "NodeStatus",
    "ResourceRequirement",
    "ExecutionNode",
    "DependencyEdge",
    "ExecutionGraph",
    # dsl_parser
    "DSLParser",
    "DSLParseError",
    # cord_security
    "CORDEngine",
    "CORDResult",
    "CORDVerdict",
    "CORDFinding",
    "CORDCheckType",
    "cord_check",
    # mee_engine
    "MEEEngine",
    "MEESession",
    "MEEStepRecord",
    "MEE_VERSION",
    # governance_gate
    "GovernanceGate",
    "GovernanceVerdict",
    "GovernanceOutcome",
    "GovernancePolicy",
    "GovernanceError",
    "PolicyFlag",
    "GOVERNANCE_GATE_VERSION",
    # persistence_pg
    "PostgresPersistence",
    "get_persistence",
    "POSTGRES_PERSISTENCE_VERSION",
    # jitna_protocol_v3
    "JITNAPacketV3",
    "JITNAMessageTypeV3",
    "JITNARouter",
    "TTLExpiredError",
    "JITNA_V3_SCHEMA_VERSION",
    "jitna_stream",
    "pack_compressed",
    "unpack_compressed",
    # zk_fdia
    "ZKFDIAProver",
    "ZKFDIAVerifier",
    "ZKFDIACommitment",
    "ZK_FDIA_VERSION",
    # helix_ttd
    "HelixStateVector",
    "TopologicalDriftDetector",
    "HelixHistory",
    "DriftAlert",
    "drift_velocity",
    "HELIX_TTD_VERSION",
    "HELIX_STATE_DIM",
    # payment_engine
    "PaymentEngine",
    "SubscriptionTier",
    "TierPolicy",
    "TIER_POLICIES",
    "BillingRecord",
    "BillingError",
    "FDIAGateError",
    "DailyLimitExceededError",
    "StripeEventError",
    "PAYMENT_ENGINE_VERSION",
    # node_network
    "Node",
    "NodeNetwork",
    "BroadcastResult",
    "ConsensusResult",
    "NODE_NETWORK_VERSION",
    "CONSENSUS_THRESHOLD",
]
