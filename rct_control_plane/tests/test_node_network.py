"""
Tests for Node Network — Distributed Multi-hop Broadcasting with 2/3 Consensus
"""

from __future__ import annotations

import unittest

from rct_control_plane.node_network import (
    NODE_NETWORK_VERSION,
    CONSENSUS_THRESHOLD,
    Node,
    NodeNetwork,
)
from rct_control_plane.jitna_protocol_v3 import (
    JITNAPacketV3,
    JITNAMessageTypeV3,
)


# ============================================================
# Helpers
# ============================================================

def _packet(data: str = "hello", sender: str = "s0", ttl: int = 8) -> JITNAPacketV3:
    return JITNAPacketV3(
        message_type=JITNAMessageTypeV3.INTENT_REQUEST.value,
        source_agent_id=sender,
        target_agent_id="*",
        payload={"data": data},
        ttl=ttl,
    )


def _net(*node_ids: str) -> NodeNetwork:
    return NodeNetwork([Node(n) for n in node_ids])


def _voting_net(
    n_for: int, n_against: int, n_abstain: int
) -> NodeNetwork:
    nodes = (
        [Node(f"for-{i}", vote_fn=lambda _: True) for i in range(n_for)]
        + [Node(f"against-{i}", vote_fn=lambda _: False) for i in range(n_against)]
        + [Node(f"abstain-{i}", vote_fn=lambda _: None) for i in range(n_abstain)]
    )
    return NodeNetwork(nodes)


# ============================================================
# 1. Constants
# ============================================================

class TestConstants(unittest.TestCase):
    def test_version(self):
        self.assertEqual(NODE_NETWORK_VERSION, "1.0")

    def test_consensus_threshold(self):
        self.assertAlmostEqual(CONSENSUS_THRESHOLD, 2 / 3, places=10)


# ============================================================
# 2. NodeNetwork construction
# ============================================================

class TestNodeNetworkConstruction(unittest.TestCase):
    def test_single_node(self):
        net = _net("n1")
        self.assertEqual(net.size, 1)

    def test_multiple_nodes(self):
        net = _net("a", "b", "c")
        self.assertEqual(net.size, 3)
        self.assertIn("b", net.node_ids)

    def test_empty_nodes_raises(self):
        with self.assertRaises(ValueError):
            NodeNetwork([])

    def test_add_node(self):
        net = _net("n1")
        net.add_node(Node("n2"))
        self.assertEqual(net.size, 2)

    def test_remove_node(self):
        net = _net("n1", "n2", "n3")
        net.remove_node("n2")
        self.assertEqual(net.size, 2)
        self.assertNotIn("n2", net.node_ids)


# ============================================================
# 3. Broadcast
# ============================================================

class TestBroadcast(unittest.TestCase):
    def test_broadcast_single_hop(self):
        net = _net("n1", "n2", "n3")
        result = net.broadcast(_packet(), hops=["n1"])
        self.assertTrue(result.success)
        self.assertEqual(result.hops_completed, 1)

    def test_broadcast_all_nodes(self):
        net = _net("a", "b", "c")
        result = net.broadcast(_packet())
        self.assertTrue(result.success)
        self.assertEqual(result.hops_completed, 3)

    def test_broadcast_ttl_exhausted(self):
        net = _net("a", "b", "c", "d", "e")
        # TTL=2 but we have 5 hops → TTL exhausted
        result = net.broadcast(_packet(), ttl=2)
        self.assertFalse(result.success)
        self.assertTrue(result.ttl_exhausted)
        self.assertIsNotNone(result.error)

    def test_broadcast_returns_hop_trace(self):
        net = _net("x", "y", "z")
        result = net.broadcast(_packet(), hops=["x", "y"])
        self.assertEqual(result.routed_packet.hop_trace, ["x", "y"])

    def test_broadcast_to_dict(self):
        import json
        net = _net("n1")
        result = net.broadcast(_packet(), hops=["n1"])
        d = result.to_dict()
        json.dumps(d)
        self.assertIn("hops_completed", d)

    def test_broadcast_explicit_hops_subset(self):
        net = _net("a", "b", "c", "d")
        result = net.broadcast(_packet(), hops=["b", "c"])
        self.assertTrue(result.success)
        self.assertEqual(result.routed_packet.hop_trace, ["b", "c"])


# ============================================================
# 4. Consensus — supermajority
# ============================================================

class TestConsensus(unittest.TestCase):
    def test_unanimous_for_passes(self):
        net = _voting_net(n_for=3, n_against=0, n_abstain=0)
        r = net.consensus_vote("proposal-A")
        self.assertTrue(r.passed)
        self.assertEqual(r.votes_for, 3)

    def test_exact_two_thirds_does_not_pass(self):
        """2/3 is not > 2/3 (strict supermajority)."""
        net = _voting_net(n_for=2, n_against=1, n_abstain=0)
        r = net.consensus_vote("proposal-B")
        self.assertFalse(r.passed)

    def test_above_two_thirds_passes(self):
        """4/5 > 2/3 → passes."""
        net = _voting_net(n_for=4, n_against=1, n_abstain=0)
        r = net.consensus_vote("proposal-C")
        self.assertTrue(r.passed)

    def test_minority_for_fails(self):
        net = _voting_net(n_for=1, n_against=2, n_abstain=0)
        r = net.consensus_vote("proposal-D")
        self.assertFalse(r.passed)

    def test_all_abstain_fails(self):
        net = _voting_net(n_for=0, n_against=0, n_abstain=5)
        r = net.consensus_vote("proposal-E")
        self.assertFalse(r.passed)
        self.assertAlmostEqual(r.vote_ratio, 0.0)

    def test_abstains_count_as_participants(self):
        """5 total: 4 FOR, 1 abstain → 4/5 = 0.80 > 0.667 → passes."""
        net = _voting_net(n_for=4, n_against=0, n_abstain=1)
        r = net.consensus_vote("proposal-F")
        self.assertTrue(r.passed)
        self.assertEqual(r.votes_abstain, 1)

    def test_consensus_result_to_dict(self):
        import json
        net = _voting_net(n_for=3, n_against=0, n_abstain=0)
        r = net.consensus_vote("test")
        d = r.to_dict()
        json.dumps(d)
        self.assertIn("passed", d)
        self.assertIn("vote_ratio", d)

    def test_single_node_unanimous_passes(self):
        net = NodeNetwork([Node("only", vote_fn=lambda _: True)])
        r = net.consensus_vote("single-test")
        self.assertTrue(r.passed)

    def test_single_node_against_fails(self):
        net = NodeNetwork([Node("only", vote_fn=lambda _: False)])
        r = net.consensus_vote("single-fail")
        self.assertFalse(r.passed)

    def test_vote_ratio_calculation(self):
        net = _voting_net(n_for=7, n_against=3, n_abstain=0)
        r = net.consensus_vote("ratio-test")
        self.assertAlmostEqual(r.vote_ratio, 0.7, places=5)

    def test_total_nodes_matches_network_size(self):
        net = _voting_net(n_for=2, n_against=1, n_abstain=1)
        r = net.consensus_vote("count-test")
        self.assertEqual(r.total_nodes, 4)


if __name__ == "__main__":
    unittest.main()
