"""
Node Network — Distributed Multi-hop Broadcasting with 2/3 Majority Consensus

Each node in the network can:
  - Receive JITNA v3 packets via ``broadcast(packet)``
  - Vote on proposals via ``consensus_vote(proposal)``

Consensus Model:
  - 2/3 supermajority (strict: votes_for / total_nodes > 2/3)
  - All live nodes are asked synchronously; no timeout (simulated model)
  - Abstain votes (None) count as total participants but not FOR

Routing:
  - Uses JITNA v3 ``JITNARouter`` for hop-by-hop delivery
  - TTL exhaustion → returns last partial route in the result
  - Empty node list → raises ValueError

NODE_NETWORK_VERSION = "1.0"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from rct_control_plane.jitna_protocol_v3 import (
    JITNAPacketV3,
    JITNARouter,
    TTLExpiredError,
)

NODE_NETWORK_VERSION = "1.0"


# ============================================================
# Node
# ============================================================

@dataclass
class Node:
    node_id: str
    # Callable that a node calls when it wants to vote on a proposal
    # Returns True (for), False (against), or None (abstain)
    vote_fn: Optional[Callable[[str], Optional[bool]]] = None

    def vote(self, proposal: str) -> Optional[bool]:
        if self.vote_fn is not None:
            return self.vote_fn(proposal)
        return None  # default: abstain


# ============================================================
# Broadcast Result
# ============================================================

@dataclass
class BroadcastResult:
    """Result of a multi-hop broadcast."""
    success: bool
    routed_packet: JITNAPacketV3
    hops_completed: int
    ttl_exhausted: bool
    error: Optional[str]
    broadcast_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "hops_completed": self.hops_completed,
            "ttl_exhausted": self.ttl_exhausted,
            "hop_trace": self.routed_packet.hop_trace,
            "error": self.error,
            "broadcast_at": self.broadcast_at,
        }


# ============================================================
# Consensus Result
# ============================================================

@dataclass
class ConsensusResult:
    """Result of a 2/3 supermajority consensus vote."""
    proposal: str
    total_nodes: int
    votes_for: int
    votes_against: int
    votes_abstain: int
    passed: bool
    vote_ratio: float            # votes_for / total_nodes
    voted_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "proposal": self.proposal,
            "total_nodes": self.total_nodes,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "votes_abstain": self.votes_abstain,
            "passed": self.passed,
            "vote_ratio": round(self.vote_ratio, 6),
            "voted_at": self.voted_at,
        }


# ============================================================
# NodeNetwork
# ============================================================

CONSENSUS_THRESHOLD = 2.0 / 3.0   # strict supermajority


class NodeNetwork:
    """
    A logical overlay network of named nodes.

    Args:
        nodes: list of Node objects that form the network.

    Raises:
        ValueError: if nodes list is empty.
    """

    def __init__(self, nodes: List[Node]) -> None:
        if not nodes:
            raise ValueError("NodeNetwork requires at least one node.")
        self._nodes: Dict[str, Node] = {n.node_id: n for n in nodes}
        self._router = JITNARouter()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def node_ids(self) -> List[str]:
        return list(self._nodes.keys())

    @property
    def size(self) -> int:
        return len(self._nodes)

    def add_node(self, node: Node) -> None:
        self._nodes[node.node_id] = node

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def broadcast(
        self,
        packet: JITNAPacketV3,
        hops: Optional[List[str]] = None,
        ttl: int = 8,
    ) -> BroadcastResult:
        """
        Route ``packet`` through the specified hops (or all nodes in order).

        Args:
            packet: JITNA v3 packet to deliver.
            hops:   explicit list of node IDs to traverse; defaults to all nodes.
            ttl:    time-to-live passed to JITNARouter.

        Returns:
            BroadcastResult with success status and hop trace.
        """
        route = hops if hops is not None else self.node_ids
        if not route:
            return BroadcastResult(
                success=False,
                routed_packet=packet,
                hops_completed=0,
                ttl_exhausted=False,
                error="No route specified and network is empty.",
            )
        try:
            routed = self._router.route(packet, route, ttl=ttl)
            return BroadcastResult(
                success=True,
                routed_packet=routed,
                hops_completed=len(routed.hop_trace),
                ttl_exhausted=False,
                error=None,
            )
        except TTLExpiredError as exc:
            return BroadcastResult(
                success=False,
                routed_packet=packet,
                hops_completed=len(packet.hop_trace),
                ttl_exhausted=True,
                error=str(exc),
            )
        except ValueError as exc:
            return BroadcastResult(
                success=False,
                routed_packet=packet,
                hops_completed=0,
                ttl_exhausted=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Consensus
    # ------------------------------------------------------------------

    def consensus_vote(self, proposal: str) -> ConsensusResult:
        """
        Run a 2/3 supermajority vote on ``proposal`` across all nodes.

        Node.vote() returns:
            True  → FOR
            False → AGAINST
            None  → ABSTAIN

        Consensus passes when:
            votes_for / total_nodes > 2/3
        """
        total = len(self._nodes)
        votes_for = 0
        votes_against = 0
        votes_abstain = 0

        for node in self._nodes.values():
            result = node.vote(proposal)
            if result is True:
                votes_for += 1
            elif result is False:
                votes_against += 1
            else:
                votes_abstain += 1

        vote_ratio = votes_for / total if total > 0 else 0.0
        passed = vote_ratio > CONSENSUS_THRESHOLD

        return ConsensusResult(
            proposal=proposal,
            total_nodes=total,
            votes_for=votes_for,
            votes_against=votes_against,
            votes_abstain=votes_abstain,
            passed=passed,
            vote_ratio=vote_ratio,
        )
