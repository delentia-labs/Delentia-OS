"""
Multi-Agent Parallel Execution Engine
Executes DAG ExecutionGraph nodes concurrently using asyncio.gather.
Handles PARALLEL_FAN_OUT and PARALLEL_FAN_IN with real-time WebSocket telemetry emission.
"""

import time
import asyncio
from typing import Any, Callable, Dict, Optional, Set

from .execution_graph_ir import ExecutionGraph, ExecutionNode, NodeStatus
from .websocket_manager import WS_MANAGER


class ParallelExecutionEngine:
    """Executes execution graph DAGs concurrently with asyncio.gather."""

    def __init__(self, node_executor: Optional[Callable[[ExecutionNode], Any]] = None):
        self.node_executor = node_executor or self._default_mock_executor

    async def _default_mock_executor(self, node: ExecutionNode) -> Dict[str, Any]:
        """Default asynchronous execution handler for subagent nodes."""
        node.status = NodeStatus.RUNNING
        
        # Broadcast node running event
        await WS_MANAGER.broadcast(
            "NODE_RUNNING",
            {"node_id": node.id, "node_type": node.node_type.value, "capability": node.capability},
            intent_id="parallel_execution"
        )
        
        # Simulate sub-millisecond to realistic async execution
        await asyncio.sleep(0.05)
        
        node.status = NodeStatus.COMPLETED
        result_payload = {
            "node_id": node.id,
            "status": "COMPLETED",
            "output": f"Subagent execution completed for {node.capability or node.tool_name or node.id}"
        }

        # Broadcast node completed event
        await WS_MANAGER.broadcast(
            "NODE_COMPLETED",
            result_payload,
            intent_id="parallel_execution"
        )
        return result_payload

    async def execute_graph_parallel(self, graph: ExecutionGraph) -> Dict[str, Any]:
        """
        Traverses the DAG in topological waves, executing all independent ready nodes in parallel.
        """
        start_time = time.perf_counter()
        results: Dict[str, Any] = {}
        waves_count = 0

        completed_nodes: Set[str] = set()
        while True:
            ready_nodes = graph.get_ready_nodes(completed_nodes)
            if not ready_nodes:
                break

            waves_count += 1
            tasks = [self.node_executor(node) for node in ready_nodes]
            wave_results = await asyncio.gather(*tasks, return_exceptions=True)

            for node, res in zip(ready_nodes, wave_results):
                if isinstance(res, Exception):
                    node.status = NodeStatus.FAILED
                    results[node.id] = {"error": str(res), "status": "FAILED"}
                else:
                    results[node.id] = res
                    completed_nodes.add(node.id)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        is_all_completed = all(n.status == NodeStatus.COMPLETED for n in graph.nodes.values())

        return {
            "success": is_all_completed,
            "graph_id": graph.graph_id,
            "total_nodes": len(graph.nodes),
            "waves_count": waves_count,
            "elapsed_ms": elapsed_ms,
            "node_results": results
        }


# Global engine instance
PARALLEL_ENGINE = ParallelExecutionEngine()
