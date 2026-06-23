"""
Execution Graph Intermediate Representation (IR)

This module defines the IR for execution graphs that serve as the bridge between
high-level intents and low-level execution. The ExecutionGraph is a DAG (Directed
Acyclic Graph) where nodes represent execution units and edges represent dependencies.

Key Components:
- ExecutionNode: Single unit of execution (tool call, agent capability, checkpoint)
- DependencyEdge: Dependency relationship between nodes
- ExecutionGraph: Complete execution plan as DAG

Example:
    >>> graph = ExecutionGraph(intent_id="abc123")
    >>> node1 = ExecutionNode(
    ...     id="analyze_1",
    ...     node_type=NodeType.AGENT_CAPABILITY,
    ...     capability="code_analysis"
    ... )
    >>> node2 = ExecutionNode(
    ...     id="refactor_1",
    ...     node_type=NodeType.AGENT_CAPABILITY,
    ...     capability="code_transformation"
    ... )
    >>> graph.add_node(node1)
    >>> graph.add_node(node2)
    >>> graph.add_edge(DependencyEdge(from_node="analyze_1", to_node="refactor_1"))
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4


# ============================================================================
# ENUMS
# ============================================================================

class NodeType(str, Enum):
    """Types of execution nodes"""
    AGENT_CAPABILITY = "agent_capability"  # LLM-based capability (e.g., code_analysis)
    TOOL_CALL = "tool_call"               # Direct tool invocation
    CHECKPOINT = "checkpoint"             # State snapshot for rollback
    APPROVAL_GATE = "approval_gate"       # Human approval required
    PARALLEL_FAN_OUT = "parallel_fan_out" # Start parallel execution
    PARALLEL_FAN_IN = "parallel_fan_in"   # Wait for parallel completion
    CONDITIONAL = "conditional"           # Branch based on condition
    LOOP = "loop"                        # Iterate until condition


class DependencyType(str, Enum):
    """Types of dependencies between nodes"""
    SEQUENTIAL = "sequential"     # Node B must wait for Node A to complete
    DATA_FLOW = "data_flow"       # Node B consumes output of Node A
    CONTROL_FLOW = "control_flow" # Node B executes based on Node A's result
    RESOURCE = "resource"         # Node B needs resources from Node A


class NodeStatus(str, Enum):
    """Execution status of a node"""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ResourceRequirement:
    """Resource requirements for node execution"""
    max_cost_usd: Optional[Decimal] = None
    max_time: Optional[timedelta] = None
    max_memory_mb: Optional[int] = None
    max_cpu_cores: Optional[float] = None
    max_tokens: Optional[int] = None
    requires_gpu: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_cost_usd": str(self.max_cost_usd) if self.max_cost_usd else None,
            "max_time": self.max_time.total_seconds() if self.max_time else None,
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_cores": self.max_cpu_cores,
            "max_tokens": self.max_tokens,
            "requires_gpu": self.requires_gpu,
        }


@dataclass
class ExecutionNode:
    """
    A single node in the execution graph.
    
    Represents an atomic unit of execution such as:
    - Agent capability invocation (code_analysis, code_transformation)
    - Tool call (file_read, git_commit)
    - Checkpoint (state snapshot)
    - Control flow (approval gate, conditional, loop)
    """
    id: str                                    # Unique node identifier
    node_type: NodeType
    
    # Execution details
    capability: Optional[str] = None           # Agent capability name
    tool_name: Optional[str] = None            # Tool name for TOOL_CALL
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Input/Output
    required_inputs: List[str] = field(default_factory=list)  # Input keys needed
    produces_outputs: List[str] = field(default_factory=list) # Output keys produced
    
    # Resource management
    resources: ResourceRequirement = field(default_factory=ResourceRequirement)
    estimated_cost: Decimal = Decimal("0.0")
    estimated_duration_seconds: int = 0
    
    # Execution state
    status: NodeStatus = NodeStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    
    # Metadata
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_ready(self, completed_nodes: Set[str], graph: 'ExecutionGraph') -> bool:
        """Check if node is ready to execute based on dependencies"""
        if self.status != NodeStatus.PENDING:
            return False
        
        # Get all dependencies for this node
        dependencies = graph.get_dependencies(self.id)
        
        # If no dependencies, node is ready
        if not dependencies:
            return True
        
        # All dependencies must be completed
        for dep in dependencies:
            if dep not in completed_nodes:
                return False
        
        return True
    
    def can_retry(self) -> bool:
        """Check if node can be retried after failure"""
        return self.status == NodeStatus.FAILED and self.retry_count < self.max_retries
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "capability": self.capability,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "required_inputs": self.required_inputs,
            "produces_outputs": self.produces_outputs,
            "resources": self.resources.to_dict(),
            "estimated_cost": str(self.estimated_cost),
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass
class DependencyEdge:
    """
    Dependency between two nodes in the execution graph.
    
    Represents a directed edge from one node to another, indicating
    that the target node depends on the source node.
    """
    from_node: str                             # Source node ID
    to_node: str                               # Target node ID
    dependency_type: DependencyType = DependencyType.SEQUENTIAL
    
    # Data flow
    data_mapping: Dict[str, str] = field(default_factory=dict)  # {from_output: to_input}
    
    # Conditional execution
    condition: Optional[str] = None            # Condition expression (e.g., "status == 'success'")
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "dependency_type": self.dependency_type.value,
            "data_mapping": self.data_mapping,
            "condition": self.condition,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionGraph:
    """
    Complete execution plan represented as a Directed Acyclic Graph (DAG).
    
    The graph is the intermediate representation between high-level intents
    and low-level execution. It can be:
    1. Generated from IntentObject via templates
    2. Parsed from DSL text
    3. Optimized by ALGO-38 (CSP-based optimization)
    4. Executed by the execution engine
    """
    intent_id: str                             # Associated intent ID
    graph_id: str = field(default_factory=lambda: str(uuid4()))
    
    # Graph structure
    nodes: Dict[str, ExecutionNode] = field(default_factory=dict)
    edges: List[DependencyEdge] = field(default_factory=list)
    
    # Entry/Exit points
    entry_nodes: List[str] = field(default_factory=list)  # Nodes with no dependencies
    exit_nodes: List[str] = field(default_factory=list)   # Nodes with no dependents
    
    # Resource estimates
    total_estimated_cost: Decimal = Decimal("0.0")
    total_estimated_duration_seconds: int = 0
    critical_path_duration_seconds: int = 0    # Longest path through graph
    
    # Metadata
    created_at: Optional[str] = None
    optimized: bool = False                    # Whether graph has been optimized
    optimization_metadata: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_node(self, node: ExecutionNode) -> None:
        """Add a node to the graph"""
        self.nodes[node.id] = node
        self._update_entry_exit_nodes()
    
    def add_edge(self, edge: DependencyEdge) -> None:
        """Add a dependency edge to the graph"""
        # Validate nodes exist
        if edge.from_node not in self.nodes:
            raise ValueError(f"Source node {edge.from_node} not found in graph")
        if edge.to_node not in self.nodes:
            raise ValueError(f"Target node {edge.to_node} not found in graph")
        
        self.edges.append(edge)
        self._update_entry_exit_nodes()
        
        # Check for cycles
        if self._has_cycle():
            # Remove the edge that created the cycle
            self.edges.remove(edge)
            raise ValueError(f"Adding edge {edge.from_node} -> {edge.to_node} would create a cycle")
    
    def get_node(self, node_id: str) -> Optional[ExecutionNode]:
        """Get node by ID"""
        return self.nodes.get(node_id)
    
    def get_dependencies(self, node_id: str) -> List[str]:
        """Get all nodes that the given node depends on"""
        return [edge.from_node for edge in self.edges if edge.to_node == node_id]
    
    def get_dependents(self, node_id: str) -> List[str]:
        """Get all nodes that depend on the given node"""
        return [edge.to_node for edge in self.edges if edge.from_node == node_id]
    
    def get_ready_nodes(self, completed_nodes: Set[str]) -> List[ExecutionNode]:
        """Get all nodes that are ready to execute"""
        ready = []
        for node in self.nodes.values():
            if node.id not in completed_nodes and node.is_ready(completed_nodes, self):
                ready.append(node)
        return ready
    
    def topological_sort(self) -> List[str]:
        """
        Return nodes in topological order (respecting dependencies).
        
        Returns:
            List of node IDs in execution order
            
        Raises:
            ValueError: If graph contains a cycle
        """
        # Kahn's algorithm
        in_degree = {node_id: 0 for node_id in self.nodes}
        
        for edge in self.edges:
            in_degree[edge.to_node] += 1
        
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node_id = queue.pop(0)
            result.append(node_id)
            
            for edge in self.edges:
                if edge.from_node == node_id:
                    in_degree[edge.to_node] -= 1
                    if in_degree[edge.to_node] == 0:
                        queue.append(edge.to_node)
        
        if len(result) != len(self.nodes):
            raise ValueError("Graph contains a cycle")
        
        return result
    
    def calculate_critical_path(self) -> int:
        """
        Calculate the critical path (longest path) through the graph.
        
        Returns:
            Duration in seconds of the critical path
        """
        # Use dynamic programming to find longest path
        topo_order = self.topological_sort()
        
        # Initialize distances
        distances = {node_id: 0 for node_id in self.nodes}
        
        # Calculate longest path
        for node_id in topo_order:
            node = self.nodes[node_id]
            node_duration = node.estimated_duration_seconds
            
            for edge in self.edges:
                if edge.from_node == node_id:
                    distances[edge.to_node] = max(
                        distances[edge.to_node],
                        distances[node_id] + node_duration
                    )
        
        # Find maximum distance (adding last node's duration)
        max_distance = 0
        for node_id in self.exit_nodes:
            node = self.nodes[node_id]
            max_distance = max(max_distance, distances[node_id] + node.estimated_duration_seconds)
        
        return max_distance
    
    def validate(self) -> List[str]:
        """
        Validate the graph structure and return list of errors.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Check for empty graph
        if not self.nodes:
            errors.append("Graph has no nodes")
            return errors
        
        # Check for cycles
        try:
            self.topological_sort()
        except ValueError as e:
            errors.append(str(e))
        
        # Check all edges reference valid nodes
        for edge in self.edges:
            if edge.from_node not in self.nodes:
                errors.append(f"Edge references non-existent source node: {edge.from_node}")
            if edge.to_node not in self.nodes:
                errors.append(f"Edge references non-existent target node: {edge.to_node}")
        
        # Check for unreachable nodes (except entry nodes)
        reachable = set(self.entry_nodes)
        for node_id in self.topological_sort():
            if node_id in reachable or node_id in self.entry_nodes:
                reachable.add(node_id)
                reachable.update(self.get_dependents(node_id))
        
        unreachable = set(self.nodes.keys()) - reachable
        if unreachable:
            errors.append(f"Unreachable nodes detected: {unreachable}")
        
        # Validate data flow
        for edge in self.edges:
            if edge.dependency_type == DependencyType.DATA_FLOW:
                from_node = self.nodes[edge.from_node]
                to_node = self.nodes[edge.to_node]
                
                for from_output, to_input in edge.data_mapping.items():
                    if from_output not in from_node.produces_outputs:
                        errors.append(
                            f"Data flow edge {edge.from_node} -> {edge.to_node}: "
                            f"source doesn't produce '{from_output}'"
                        )
                    if to_input not in to_node.required_inputs:
                        errors.append(
                            f"Data flow edge {edge.from_node} -> {edge.to_node}: "
                            f"target doesn't require '{to_input}'"
                        )
        
        return errors
    
    def _update_entry_exit_nodes(self) -> None:
        """Update entry and exit node lists"""
        # Entry nodes: nodes with no incoming edges
        nodes_with_incoming = {edge.to_node for edge in self.edges}
        self.entry_nodes = [
            node_id for node_id in self.nodes
            if node_id not in nodes_with_incoming
        ]
        
        # Exit nodes: nodes with no outgoing edges
        nodes_with_outgoing = {edge.from_node for edge in self.edges}
        self.exit_nodes = [
            node_id for node_id in self.nodes
            if node_id not in nodes_with_outgoing
        ]
    
    def _has_cycle(self) -> bool:
        """Check if graph contains a cycle using DFS"""
        visited = set()
        rec_stack = set()
        
        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            
            for edge in self.edges:
                if edge.from_node == node_id:
                    neighbor = edge.to_node
                    if neighbor not in visited:
                        if dfs(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True
            
            rec_stack.remove(node_id)
            return False
        
        for node_id in self.nodes:
            if node_id not in visited:
                if dfs(node_id):
                    return True
        
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "intent_id": self.intent_id,
            "graph_id": self.graph_id,
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
            "entry_nodes": self.entry_nodes,
            "exit_nodes": self.exit_nodes,
            "total_estimated_cost": str(self.total_estimated_cost),
            "total_estimated_duration_seconds": self.total_estimated_duration_seconds,
            "critical_path_duration_seconds": self.critical_path_duration_seconds,
            "created_at": self.created_at,
            "optimized": self.optimized,
            "optimization_metadata": self.optimization_metadata,
            "metadata": self.metadata,
        }
