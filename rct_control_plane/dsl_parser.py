"""
Execution DSL Parser

Parses Domain-Specific Language (DSL) text into ExecutionGraph intermediate representation.
The DSL provides a human-readable way to define execution graphs with nodes, dependencies,
and resource requirements.

DSL Grammar (simplified):
    intent <id> {
        [metadata_key = value]*
        
        [phase <name> {
            node <NodeId> {
                node_type = "agent_capability" | "tool_call" | ...
                [capability = "string"]
                [tool_name = "string"]
                [cost = decimal]
                [timeout = integer"s"]
                [depends_on = [NodeId, ...]]
                [produces_artifacts = [string, ...]]
                [requires_artifacts = [string, ...]]
                [parameters { key = value, ... }]
            }
        }]*
    }

Example:
    >>> dsl_text = '''
    ... intent "refactor_module" {
    ...     phase analyze {
    ...         node AnalyzeNode {
    ...             agent_capability = "code_analysis"
    ...             cost = 0.50
    ...             timeout = 60s
    ...         }
    ...     }
    ... }
    ... '''
    >>> parser = DSLParser()
    >>> graph = parser.parse(dsl_text, intent_id="abc123")
    >>> assert len(graph.nodes) == 1
"""

import re
from decimal import Decimal
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from .execution_graph_ir import (
    DependencyEdge,
    DependencyType,
    ExecutionGraph,
    ExecutionNode,
    NodeType,
    ResourceRequirement,
)


class DSLParseError(Exception):
    """Raised when DSL parsing fails"""
    def __init__(self, message: str, line: int = 0, column: int = 0):
        self.line = line
        self.column = column
        super().__init__(f"Line {line}, Col {column}: {message}" if line else message)


class DSLParser:
    """
    Parser for Execution DSL.
    
    Converts DSL text into ExecutionGraph IR.
    """
    
    # Regex patterns
    INTENT_PATTERN = r'intent\s+"([^"]+)"\s*\{'
    PHASE_PATTERN = r'phase\s+(\w+)\s*\{'
    NODE_PATTERN = r'node\s+(\w+)\s*\{'
    PARAMETER_PATTERN = r'(\w+)\s*=\s*(.+?)(?:,|\n|$)'
    ARRAY_PATTERN = r'\[([^\]]*)\]'
    STRING_PATTERN = r'"([^"]*)"'
    NUMBER_PATTERN = r'(\d+\.?\d*)'
    DURATION_PATTERN = r'(\d+)s'
    
    def __init__(self, observer: Optional['ControlPlaneObserver'] = None):
        """Initialize parser
        
        Args:
            observer: Optional ControlPlaneObserver for event tracking
        """
        self.current_line = 0
        self.errors: List[str] = []
        self.observer = observer
    
    def parse(self, dsl_text: str, intent_id: str) -> ExecutionGraph:
        """
        Parse DSL text into ExecutionGraph.
        
        Args:
            dsl_text: DSL source text
            intent_id: Intent ID to associate with graph
            
        Returns:
            Parsed ExecutionGraph
            
        Raises:
            DSLParseError: If parsing fails
        """
        graph = ExecutionGraph(intent_id=intent_id)
        self.errors = []
        
        # Extract intent block
        intent_match = re.search(self.INTENT_PATTERN, dsl_text, re.MULTILINE)
        if not intent_match:
            raise DSLParseError("No intent block found")
        
        intent_name = intent_match.group(1)
        graph.metadata["intent_name"] = intent_name
        
        # Extract intent body (everything between outer { })
        start_idx = intent_match.end()
        intent_body = self._extract_block(dsl_text, start_idx)
        
        # Parse phases and nodes
        self._parse_intent_body(intent_body, graph)
        
        # Validate graph
        validation_errors = graph.validate()
        if validation_errors:
            raise DSLParseError(
                f"Graph validation failed: {'; '.join(validation_errors)}"
            )
        
        # Calculate graph metrics
        self._calculate_graph_metrics(graph)
        
        # Emit event: GRAPH_BUILT
        if self.observer:
            from .observability import ControlPlaneEventType
            self.observer.observe_event(
                event_type=ControlPlaneEventType.GRAPH_BUILT,
                intent_id=intent_id,
                graph_id=graph.graph_id,
                data={
                    "node_count": len(graph.nodes),
                    "edge_count": len(graph.edges),
                    "estimated_cost": float(graph.total_estimated_cost),
                    "estimated_duration_seconds": graph.total_estimated_duration_seconds,
                    "intent_name": intent_name
                },
                success=True
            )
        
        return graph
    
    def _extract_block(self, text: str, start_idx: int) -> str:
        """
        Extract content between matching braces starting at start_idx.
        
        Args:
            text: Full text
            start_idx: Index of opening brace
            
        Returns:
            Content between braces (excluding braces)
        """
        depth = 1
        i = start_idx
        
        while i < len(text) and depth > 0:
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
            i += 1
        
        if depth != 0:
            raise DSLParseError("Unmatched braces")
        
        return text[start_idx:i-1]
    
    def _parse_intent_body(self, body: str, graph: ExecutionGraph) -> None:
        """Parse intent body for phases and nodes"""
        # Find all phase blocks
        phase_matches = list(re.finditer(self.PHASE_PATTERN, body, re.MULTILINE))
        
        if not phase_matches:
            # No phases - try parsing nodes directly
            self._parse_nodes(body, graph, phase_name=None)
            return
        
        for phase_match in phase_matches:
            phase_name = phase_match.group(1)
            
            # Extract phase body
            phase_start = phase_match.end()
            phase_body = self._extract_block(body, phase_start)
            
            # Parse nodes in this phase
            self._parse_nodes(phase_body, graph, phase_name=phase_name)
    
    def _parse_nodes(self, text: str, graph: ExecutionGraph, phase_name: Optional[str]) -> None:
        """Parse node definitions in the given text"""
        node_matches = list(re.finditer(self.NODE_PATTERN, text, re.MULTILINE))
        
        for node_match in node_matches:
            node_id = node_match.group(1)
            
            # Extract node body
            node_start = node_match.end()
            node_body = self._extract_block(text, node_start)
            
            # Parse node definition
            node = self._parse_node_definition(node_id, node_body, phase_name)
            graph.add_node(node)
    
    def _parse_node_definition(
        self,
        node_id: str,
        body: str,
        phase_name: Optional[str]
    ) -> ExecutionNode:
        """Parse a single node definition"""
        node_data: Dict[str, Any] = {
            "id": node_id,
            "node_type": NodeType.AGENT_CAPABILITY,  # Default
            "metadata": {},
            "parameters": {},
        }
        
        if phase_name:
            node_data["metadata"]["phase"] = phase_name
        
        # Check for parameters block
        params_match = re.search(r'parameters\s*\{([^}]*)\}', body, re.DOTALL)
        if params_match:
            params_body = params_match.group(1)
            node_data["parameters"] = self._parse_parameters_block(params_body)
        
        # Parse other parameters
        for line in body.split('\n'):
            line = line.strip()
            if not line or line.startswith('//') or 'parameters' in line:
                continue
            
            param_match = re.match(r'(\w+)\s*=\s*(.+)', line)
            if param_match:
                key = param_match.group(1)
                value_str = param_match.group(2).rstrip(',').strip()
                
                self._parse_node_parameter(key, value_str, node_data)
        
        # Build ExecutionNode
        return self._build_execution_node(node_data)
    
    def _parse_node_parameter(self, key: str, value_str: str, node_data: Dict[str, Any]) -> None:
        """Parse a single node parameter"""
        # Agent capability
        if key == "agent_capability":
            node_data["node_type"] = NodeType.AGENT_CAPABILITY
            node_data["capability"] = self._parse_string(value_str)
        
        # Tool call
        elif key == "tool_name":
            node_data["node_type"] = NodeType.TOOL_CALL
            node_data["tool_name"] = self._parse_string(value_str)
        
        # Node type
        elif key == "node_type":
            node_data["node_type"] = NodeType(self._parse_string(value_str))
        
        # Cost
        elif key == "cost":
            node_data["estimated_cost"] = Decimal(self._parse_number(value_str))
        
        # Timeout/Duration
        elif key in ("timeout", "duration"):
            node_data["estimated_duration_seconds"] = self._parse_duration(value_str)
        
        # Dependencies
        elif key == "depends_on":
            node_data["dependencies"] = self._parse_array(value_str)
        
        # Artifacts
        elif key == "produces_artifacts":
            node_data["produces_outputs"] = self._parse_array(value_str)
        
        elif key == "requires_artifacts":
            node_data["required_inputs"] = self._parse_array(value_str)
        
        # Description
        elif key == "description":
            node_data["description"] = self._parse_string(value_str)
        
        # Max retries
        elif key == "max_retries":
            node_data["max_retries"] = int(self._parse_number(value_str))
        
        # Parameters block
        elif key == "parameters":
            # Parameters block should be on next lines, not inline
            # Just mark that we should look for parameters in the body
            pass
        
        # Resource constraints
        elif key in ("max_memory_mb", "max_cpu_cores", "max_tokens"):
            if "resources" not in node_data:
                node_data["resources"] = {}
            if key == "max_cpu_cores":
                node_data["resources"][key] = float(self._parse_number(value_str))
            else:
                node_data["resources"][key] = int(self._parse_number(value_str))
        
        elif key == "requires_gpu":
            if "resources" not in node_data:
                node_data["resources"] = {}
            node_data["resources"]["requires_gpu"] = value_str.lower() == "true"
        
        # Anything else goes to metadata
        else:
            node_data["metadata"][key] = value_str
    
    def _parse_string(self, value_str: str) -> str:
        """Parse a quoted string"""
        match = re.match(self.STRING_PATTERN, value_str)
        if match:
            return match.group(1)
        # If not quoted, return as-is (lenient parsing)
        return value_str.strip()
    
    def _parse_number(self, value_str: str) -> str:
        """Parse a number"""
        match = re.match(self.NUMBER_PATTERN, value_str)
        if match:
            return match.group(1)
        raise DSLParseError(f"Invalid number: {value_str}")
    
    def _parse_duration(self, value_str: str) -> int:
        """Parse duration (e.g., '60s', '120s')"""
        match = re.match(self.DURATION_PATTERN, value_str)
        if match:
            return int(match.group(1))
        # Try parsing as plain number
        return int(self._parse_number(value_str))
    
    def _parse_array(self, value_str: str) -> List[str]:
        """Parse an array literal [item1, item2, ...]"""
        match = re.match(self.ARRAY_PATTERN, value_str)
        if not match:
            return []
        
        content = match.group(1)
        if not content.strip():
            return []
        
        # Split by comma and clean up
        items = []
        for item in content.split(','):
            item = item.strip()
            # Remove quotes if present
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            if item:
                items.append(item)
        
        return items
    
    def _parse_parameters_block(self, body: str) -> Dict[str, Any]:
        """Parse a parameters { } block"""
        params = {}
        
        for line in body.split('\n'):
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            
            param_match = re.match(r'(\w+)\s*=\s*(.+)', line)
            if param_match:
                key = param_match.group(1)
                value_str = param_match.group(2).rstrip(',').strip()
                
                # Try to parse as different types
                if value_str.startswith('"'):
                    params[key] = self._parse_string(value_str)
                elif value_str.startswith('['):
                    params[key] = self._parse_array(value_str)
                elif value_str.lower() in ('true', 'false'):
                    params[key] = value_str.lower() == 'true'
                elif '.' in value_str:
                    params[key] = float(value_str)
                else:
                    try:
                        params[key] = int(value_str)
                    except ValueError:
                        params[key] = value_str
        
        return params
    
    def _build_execution_node(self, node_data: Dict[str, Any]) -> ExecutionNode:
        """Build ExecutionNode from parsed data"""
        # Extract resources
        resources = ResourceRequirement()
        if "resources" in node_data:
            res_data = node_data.pop("resources")
            for key, value in res_data.items():
                setattr(resources, key, value)
        
        # Extract dependencies (will be added as edges separately)
        dependencies = node_data.pop("dependencies", [])
        
        # Build node
        node = ExecutionNode(
            id=node_data.get("id"),
            node_type=node_data.get("node_type", NodeType.AGENT_CAPABILITY),
            capability=node_data.get("capability"),
            tool_name=node_data.get("tool_name"),
            parameters=node_data.get("parameters", {}),
            required_inputs=node_data.get("required_inputs", []),
            produces_outputs=node_data.get("produces_outputs", []),
            resources=resources,
            estimated_cost=node_data.get("estimated_cost", Decimal("0.0")),
            estimated_duration_seconds=node_data.get("estimated_duration_seconds", 0),
            description=node_data.get("description", ""),
            max_retries=node_data.get("max_retries", 3),
            metadata=node_data.get("metadata", {}),
        )
        
        # Store dependencies in metadata for post-processing
        if dependencies:
            node.metadata["_dependencies"] = dependencies
        
        return node
    
    def _calculate_graph_metrics(self, graph: ExecutionGraph) -> None:
        """Calculate total cost, duration, and critical path"""
        # Process dependencies stored in metadata
        for node in graph.nodes.values():
            if "_dependencies" in node.metadata:
                dependencies = node.metadata.pop("_dependencies")
                for dep_id in dependencies:
                    # Check if dependency exists
                    if dep_id not in graph.nodes:
                        raise DSLParseError(f"Node {node.id} depends on non-existent node {dep_id}")
                    
                    edge = DependencyEdge(
                        from_node=dep_id,
                        to_node=node.id,
                        dependency_type=DependencyType.SEQUENTIAL
                    )
                    try:
                        graph.add_edge(edge)
                    except ValueError as e:
                        # Cycle detected
                        raise DSLParseError(str(e))
        
        # Calculate total cost
        total_cost = Decimal("0.0")
        for node in graph.nodes.values():
            total_cost += node.estimated_cost
        graph.total_estimated_cost = total_cost
        
        # Calculate critical path
        try:
            graph.critical_path_duration_seconds = graph.calculate_critical_path()
            graph.total_estimated_duration_seconds = graph.critical_path_duration_seconds
        except ValueError:
            # Cycle detected, use sum of all durations as fallback
            graph.total_estimated_duration_seconds = sum(
                node.estimated_duration_seconds for node in graph.nodes.values()
            )
    
    def format_graph(self, graph: ExecutionGraph) -> str:
        """
        Convert ExecutionGraph back to DSL format.
        
        Args:
            graph: ExecutionGraph to format
            
        Returns:
            DSL text representation
        """
        lines = []
        
        intent_name = graph.metadata.get("intent_name", graph.intent_id)
        lines.append(f'intent "{intent_name}" {{')
        
        # Group nodes by phase
        phases: Dict[str, List[ExecutionNode]] = {}
        for node in graph.nodes.values():
            phase = node.metadata.get("phase", "main")
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(node)
        
        # Output phases
        for phase_name, nodes in phases.items():
            lines.append(f'  phase {phase_name} {{')
            
            for node in nodes:
                lines.append(f'    node {node.id} {{')
                
                # Node type
                if node.node_type == NodeType.AGENT_CAPABILITY and node.capability:
                    lines.append(f'      agent_capability = "{node.capability}"')
                elif node.node_type == NodeType.TOOL_CALL and node.tool_name:
                    lines.append(f'      tool_name = "{node.tool_name}"')
                else:
                    lines.append(f'      node_type = "{node.node_type.value}"')
                
                # Cost and duration
                if node.estimated_cost > 0:
                    lines.append(f'      cost = {node.estimated_cost}')
                if node.estimated_duration_seconds > 0:
                    lines.append(f'      timeout = {node.estimated_duration_seconds}s')
                
                # Dependencies
                dependencies = graph.get_dependencies(node.id)
                if dependencies:
                    deps_str = ", ".join(dependencies)
                    lines.append(f'      depends_on = [{deps_str}]')
                
                # Artifacts
                if node.produces_outputs:
                    artifacts_str = ", ".join(f'"{a}"' for a in node.produces_outputs)
                    lines.append(f'      produces_artifacts = [{artifacts_str}]')
                
                if node.required_inputs:
                    artifacts_str = ", ".join(f'"{a}"' for a in node.required_inputs)
                    lines.append(f'      requires_artifacts = [{artifacts_str}]')
                
                # Description
                if node.description:
                    lines.append(f'      description = "{node.description}"')
                
                lines.append('    }')
            
            lines.append('  }')
        
        lines.append('}')
        
        return '\n'.join(lines)


def quick_parse(dsl_text: str, intent_id: str) -> ExecutionGraph:
    """
    Convenience function to quickly parse DSL text.
    
    Args:
        dsl_text: DSL source text
        intent_id: Intent ID
        
    Returns:
        Parsed ExecutionGraph
    """
    parser = DSLParser()
    return parser.parse(dsl_text, intent_id)
