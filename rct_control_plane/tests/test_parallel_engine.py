"""
Unit Tests for Multi-Agent Parallel Execution Engine.
"""

import pytest
from rct_control_plane.execution_graph_ir import ExecutionGraph, ExecutionNode, DependencyEdge, NodeType, NodeStatus
from rct_control_plane.parallel_engine import ParallelExecutionEngine


@pytest.mark.asyncio
async def test_parallel_fan_out_execution():
    """Test parallel fan-out where multiple subagents execute concurrently in 1 wave."""
    engine = ParallelExecutionEngine()
    graph = ExecutionGraph(intent_id="intent_parallel_001")

    # Node 1: Entry / Master Planner
    node_plan = ExecutionNode(id="planner", node_type=NodeType.AGENT_CAPABILITY, capability="intent_planning")
    
    # Node 2a & 2b: Parallel Subagents (Researcher & Coder)
    node_sub1 = ExecutionNode(id="researcher", node_type=NodeType.AGENT_CAPABILITY, capability="context_retrieval")
    node_sub2 = ExecutionNode(id="coder", node_type=NodeType.AGENT_CAPABILITY, capability="code_generation")
    
    # Node 3: Aggregator / Reviewer
    node_review = ExecutionNode(id="reviewer", node_type=NodeType.AGENT_CAPABILITY, capability="safety_review")

    graph.add_node(node_plan)
    graph.add_node(node_sub1)
    graph.add_node(node_sub2)
    graph.add_node(node_review)

    # Dependencies: planner -> [researcher, coder] -> reviewer
    graph.add_edge(DependencyEdge(from_node="planner", to_node="researcher"))
    graph.add_edge(DependencyEdge(from_node="planner", to_node="coder"))
    graph.add_edge(DependencyEdge(from_node="researcher", to_node="reviewer"))
    graph.add_edge(DependencyEdge(from_node="coder", to_node="reviewer"))

    # Execute graph
    res = await engine.execute_graph_parallel(graph)

    assert res["success"] is True
    assert res["total_nodes"] == 4
    assert res["waves_count"] == 3  # Wave 1: planner, Wave 2: [researcher, coder] parallel, Wave 3: reviewer
    assert all(n.status == NodeStatus.COMPLETED for n in graph.nodes.values())
