#!/usr/bin/env python3
"""
RCT Control Plane CLI

Command-line interface for Control Plane operations.
Provides commands for intent compilation, graph building, policy evaluation,
state management, audit trails, and metrics access.

Usage:
    rct compile "Refactor authentication module" --user-id user-123
    rct build --dsl-file workflow.dsl --intent-id abc-123
    rct evaluate --intent-id abc-123
    rct status abc-123
    rct list --limit 20
    rct audit abc-123
    rct metrics
    rct reset --force

Output Formats:
    --output json   : JSON output
    --output table  : Table format (default)
    --output tree   : Tree view (for graphs)
"""

import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

try:
    import click
except ImportError:
    print("Error: Click is required. Install with: pip install click", file=sys.stderr)
    sys.exit(1)

try:
    from rct_control_plane.rich_formatter import (
        get_console,
        render_intent_table,
        render_state_panel,
        render_audit_tree,
        render_metrics_panel,
        render_adapter_status,
        render_governance_violations,
        render_timeline,
        render_execution_log,
        render_replay_result,
        render_error,
        render_success,
        render_warning,
    )
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

from rct_control_plane.intent_compiler import IntentCompiler
from rct_control_plane.dsl_parser import DSLParser
from rct_control_plane.policy_language import PolicyEvaluator
from rct_control_plane.control_plane_state import ControlPlaneState, ControlPlanePhase
from rct_control_plane.observability import ControlPlaneObserver

# Preserve builtin list before it gets shadowed by the CLI 'list' command
_list = list


class OutputFormat(str, Enum):
    """Output format options."""
    JSON = "json"
    TABLE = "table"
    TREE = "tree"


class CLIContext:
    """
    CLI context holding shared components.
    
    This is created once and reused across commands.
    """
    
    def __init__(self):
        """Initialize CLI context with Control Plane components."""
        self.observer = ControlPlaneObserver()
        self.compiler = IntentCompiler(observer=self.observer)
        self.parser = DSLParser(observer=self.observer)
        self.evaluator = PolicyEvaluator(observer=self.observer)
        
        # In-memory storage (production would use database)
        self.states: Dict[str, ControlPlaneState] = {}
        self.intents: Dict[str, Dict[str, Any]] = {}
        self.graphs: Dict[str, Dict[str, Any]] = {}
    
    def save_state(self, state: ControlPlaneState) -> None:
        """Save state to storage."""
        self.states[state.state_id] = state
    
    def get_state(self, intent_id: str) -> Optional[ControlPlaneState]:
        """Get state by intent ID."""
        return self.states.get(intent_id)
    
    def save_intent(self, intent_id: str, intent_data: Dict[str, Any]) -> None:
        """Save intent to storage."""
        self.intents[intent_id] = intent_data
    
    def get_intent(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """Get intent by ID."""
        return self.intents.get(intent_id)
    
    def save_graph(self, intent_id: str, graph_data: Dict[str, Any]) -> None:
        """Save graph to storage."""
        self.graphs[intent_id] = graph_data
    
    def get_graph(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """Get graph by intent ID."""
        return self.graphs.get(intent_id)
    
    def reset_all(self) -> None:
        """Reset all state and metrics."""
        self.states.clear()
        self.intents.clear()
        self.graphs.clear()
        self.observer = ControlPlaneObserver()
        self.compiler.observer = self.observer
        self.parser.observer = self.observer
        self.evaluator.observer = self.observer


# Global CLI context
_cli_context: Optional[CLIContext] = None


def get_context() -> CLIContext:
    """Get or create CLI context."""
    global _cli_context
    if _cli_context is None:
        _cli_context = CLIContext()
    return _cli_context


# Output formatting functions

def print_json(data: Any, pretty: bool = True) -> None:
    """Print data as JSON."""
    if pretty:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        click.echo(json.dumps(data, default=str))


def print_table(headers: List[str], rows: List[List[str]]) -> None:
    """Print data as table."""
    if not rows:
        click.echo("No data to display")
        return
    
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Print header
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    click.echo(header_line)
    click.echo("-" * len(header_line))
    
    # Print rows
    for row in rows:
        row_line = " | ".join(str(cell).ljust(w) for cell, w in zip(row, col_widths))
        click.echo(row_line)


def print_tree(node: Dict[str, Any], indent: int = 0) -> None:
    """Print data as tree."""
    prefix = "  " * indent
    
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, _list)):
                click.echo(f"{prefix}├─ {key}:")
                print_tree(value, indent + 1)
            else:
                click.echo(f"{prefix}├─ {key}: {value}")
    elif isinstance(node, _list):
        for i, item in enumerate(node):
            click.echo(f"{prefix}├─ [{i}]:")
            print_tree(item, indent + 1)
    else:
        click.echo(f"{prefix}└─ {node}")


def format_output(data: Any, format: OutputFormat) -> None:
    """Format and print output based on format type."""
    if format == OutputFormat.JSON:
        print_json(data)
    elif format == OutputFormat.TABLE and isinstance(data, dict):
        # Convert dict to table
        headers = ["Key", "Value"]
        rows = [[str(k), str(v)] for k, v in data.items()]
        print_table(headers, rows)
    elif format == OutputFormat.TREE:
        print_tree(data)
    else:
        # Fallback to JSON
        print_json(data)


# CLI Commands

@click.group()
@click.version_option(version="2.2.0", prog_name="rct")
def cli():
    """
    RCT Control Plane CLI
    
    Command-line interface for Control Plane operations.
    """
    pass


@cli.command()
@click.argument("natural_language")
@click.option("--user-id", default="cli-user", help="User ID")
@click.option("--user-tier", default="PRO", help="User tier (FREE/PRO/ENTERPRISE)")
@click.option("--organization-id", default=None, help="Organization ID")
@click.option("--output", "-o", type=click.Choice(["json", "table", "tree"]), default="json", help="Output format")
@click.option("--save", "-s", is_flag=True, help="Save intent to storage")
def compile(natural_language: str, user_id: str, user_tier: str, organization_id: Optional[str], output: str, save: bool):
    """
    Compile natural language intent.
    
    Example:
        rct compile "Refactor authentication module" --user-id user-123
    """
    try:
        ctx = get_context()
        
        # Compile intent
        start_time = time.time()
        result = ctx.compiler.compile(
            natural_language=natural_language,
            user_id=user_id,
            user_tier=user_tier,
            organization_id=organization_id
        )
        compilation_time = (time.time() - start_time) * 1000
        
        # Extract intent data (CompilationResult is a dataclass, not dict)
        intent_obj = result.intent
        validation = result.validation
        
        # Create state if save flag is set
        if save:
            intent_id_str = str(intent_obj.id)
            state = ControlPlaneState(
                state_id=intent_id_str,
                phase=ControlPlanePhase.INTENT_COMPILED
            )
            ctx.save_state(state)
            ctx.save_intent(intent_id_str, {
                "intent": intent_obj.to_dict(),
                "natural_language": natural_language,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        
        # Format output
        output_data = {
            "intent_id": str(intent_obj.id),
            "intent_type": intent_obj.intent_type,
            "scope": str(intent_obj.scope),
            "priority": intent_obj.priority,
            "is_valid": validation.is_valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "compilation_time_ms": f"{compilation_time:.2f}",
            "saved": save
        }
        
        if _HAS_RICH and output != "json":
            from rich.table import Table
            t = Table(title="Compiled Intent", border_style="cyan")
            for k in output_data:
                t.add_column(k, style="bold" if k == "intent_id" else None)
            t.add_row(*[str(v) for v in output_data.values()])
            get_console().print(t)
        else:
            format_output(output_data, OutputFormat(output))
        
        if not validation.is_valid:
            if _HAS_RICH:
                render_warning("Intent has validation errors")
            else:
                click.echo(click.style("\n⚠ Intent has validation errors", fg="yellow"), err=True)
            sys.exit(1)
        
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--dsl-text", help="DSL text directly")
@click.option("--dsl-file", type=click.Path(exists=True), help="Path to DSL file")
@click.option("--intent-id", required=True, help="Intent ID to associate with graph")
@click.option("--output", "-o", type=click.Choice(["json", "table", "tree"]), default="json", help="Output format")
@click.option("--save", "-s", is_flag=True, help="Save graph to storage")
def build(dsl_text: Optional[str], dsl_file: Optional[str], intent_id: str, output: str, save: bool):
    """
    Build execution graph from DSL.
    
    Example:
        rct build --dsl-file workflow.dsl --intent-id abc-123 --save
    """
    try:
        ctx = get_context()
        
        # Get DSL input
        if dsl_file:
            dsl_input = Path(dsl_file).read_text()
        elif dsl_text:
            dsl_input = dsl_text
        else:
            click.echo(click.style("Error: Either --dsl-text or --dsl-file is required", fg="red"), err=True)
            sys.exit(1)
        
        # Parse DSL (returns ExecutionGraph directly)
        start_time = time.time()
        graph = ctx.parser.parse(dsl_input, intent_id)
        parse_time = (time.time() - start_time) * 1000
        
        # Update state if exists
        state = ctx.get_state(intent_id)
        if state and save:
            state.transition_to(ControlPlanePhase.GRAPH_BUILT)
            state.graph_snapshot = graph
            ctx.save_state(state)
        
        # Save graph
        if save:
            ctx.save_graph(intent_id, {
                "graph": graph.to_dict(),
                "dsl_text": dsl_input,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        
        # Format output
        output_data = {
            "graph_id": graph.graph_id,
            "intent_id": intent_id,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "estimated_cost": float(graph.total_estimated_cost),
            "estimated_duration": graph.total_estimated_duration_seconds,
            "parse_time_ms": f"{parse_time:.2f}",
            "saved": save,
            "nodes": [
                {
                    "node_id": node.id,
                    "node_type": node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type),
                    "label": getattr(node, 'description', None)
                }
                for node in graph.nodes.values()
            ]
        }
        
        if _HAS_RICH and output != "json":
            from rich.table import Table
            t = Table(title="Execution Graph", border_style="cyan")
            for k in output_data:
                t.add_column(k)
            t.add_row(*[str(v) for v in output_data.values()])
            get_console().print(t)
        else:
            format_output(output_data, OutputFormat(output))
        
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--intent-id", required=True, help="Intent ID")
@click.option("--use-default-policies", is_flag=True, default=True, help="Use default policies")
@click.option("--output", "-o", type=click.Choice(["json", "table", "tree"]), default="json", help="Output format")
@click.option("--save", "-s", is_flag=True, help="Update state with evaluation result")
def evaluate(intent_id: str, use_default_policies: bool, output: str, save: bool):
    """
    Evaluate policies against intent and graph.
    
    Example:
        rct evaluate --intent-id abc-123 --save
    """
    try:
        ctx = get_context()
        
        # Get intent and graph
        intent_data = ctx.get_intent(intent_id)
        graph_data = ctx.get_graph(intent_id)
        
        if not intent_data:
            click.echo(click.style(f"Error: Intent {intent_id} not found", fg="red"), err=True)
            sys.exit(1)
        
        # Reconstruct objects
        from rct_control_plane.intent_schema import IntentObject
        intent_obj = IntentObject(**intent_data["intent"])
        
        graph_obj = None
        if graph_data:
            if "dsl_text" in graph_data:
                # Re-parse DSL to reconstruct ExecutionGraph
                graph_obj = ctx.parser.parse(graph_data["dsl_text"], intent_id)
            # Otherwise evaluate without graph (policy check on intent only)
        
        # Load default policies if requested
        if use_default_policies:
            from rct_control_plane.default_policies import get_default_policies
            ctx.evaluator.clear_rules()
            for policy in get_default_policies():
                ctx.evaluator.add_rule(policy)
        
        # Evaluate policies
        start_time = time.time()
        decision = ctx.evaluator.evaluate_intent(
            intent=intent_obj,
            graph=graph_obj
        )
        eval_time = (time.time() - start_time) * 1000
        
        # Update state
        state = ctx.get_state(intent_id)
        if state and save:
            state.transition_to(ControlPlanePhase.POLICY_CHECKED)
            state.requires_approval = decision.requires_approval
            ctx.save_state(state)
        
        # Format output
        output_data = {
            "intent_id": intent_id,
            "decision": decision.decision.value if hasattr(decision.decision, 'value') else str(decision.decision),
            "decision_reason": decision.decision_reason,
            "is_approved": decision.is_approved(),
            "requires_approval": decision.requires_approval,
            "violations": decision.violations,
            "warnings": decision.warnings,
            "triggered_rules_count": len(decision.triggered_rules),
            "evaluation_time_ms": f"{eval_time:.2f}",
            "saved": save
        }
        
        format_output(output_data, OutputFormat(output))
        
        if not decision.is_approved():
            if _HAS_RICH:
                render_warning(f"Policy evaluation: {decision.decision}")
            else:
                click.echo(click.style(f"\n⚠ Policy evaluation: {decision.decision}", fg="yellow"), err=True)
            sys.exit(1)
        
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.argument("intent_id")
@click.option("--output", "-o", type=click.Choice(["json", "table", "tree"]), default="table", help="Output format")
def status(intent_id: str, output: str):
    """
    Get current state of an intent.
    
    Example:
        rct status abc-123
    """
    try:
        ctx = get_context()
        
        state = ctx.get_state(intent_id)
        if not state:
            click.echo(click.style(f"Error: State for intent {intent_id} not found", fg="red"), err=True)
            sys.exit(1)
        
        # Format output
        output_data = {
            "state_id": state.state_id,
            "phase": state.phase.value,
            "version": state.version,
            "is_terminal": state.is_terminal(),
            "is_completed": state.is_completed(),
            "is_failed": state.is_failed(),
            "created_at": state.started_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "cost_incurred": float(state.actual_cost_usd),
            "cost_projected": float(state.estimated_cost_usd),
            "transitions_count": len(state.transitions),
            "requires_approval": getattr(state, 'requires_approval', False)
        }
        
        if _HAS_RICH and output != "json":
            render_state_panel(output_data)
        else:
            format_output(output_data, OutputFormat(output))
        
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--limit", default=10, type=int, help="Maximum number of intents to list")
@click.option("--offset", default=0, type=int, help="Offset for pagination")
@click.option("--output", "-o", type=click.Choice(["json", "table", "tree"]), default="table", help="Output format")
def list(limit: int, offset: int, output: str):
    """
    List all intents.
    
    Example:
        rct list --limit 20
    """
    try:
        ctx = get_context()
        
        # Get all intents (avoid shadowing builtins.list)
        all_intents = [*ctx.intents.items()]
        
        # Apply pagination
        paginated = all_intents[offset:offset + limit]
        
        # Format output
        if output == "table" and _HAS_RICH:
            intents_for_render = []
            for intent_id, intent_data in paginated:
                state = ctx.get_state(intent_id)
                phase = state.phase.value if state else "UNKNOWN"
                intents_for_render.append({
                    "intent_id": intent_id,
                    "intent_type": intent_data["intent"]["intent_type"],
                    "scope": intent_data["intent"].get("scope", "N/A"),
                    "priority": intent_data["intent"]["priority"],
                    "is_valid": True,
                    "created_at": intent_data["created_at"][:19],
                })
            render_intent_table(intents_for_render)
            click.echo(f"\nTotal: {len(all_intents)} intents (showing {offset + 1}-{offset + len(paginated)})")
        elif output == "table":
            headers = ["Intent ID", "Type", "Priority", "Phase", "Created At"]
            rows = []
            for intent_id, intent_data in paginated:
                state = ctx.get_state(intent_id)
                phase = state.phase.value if state else "UNKNOWN"
                rows.append([
                    intent_id[:12] + "...",
                    intent_data["intent"]["intent_type"],
                    intent_data["intent"]["priority"],
                    phase,
                    intent_data["created_at"][:19]
                ])
            print_table(headers, rows)
            click.echo(f"\nTotal: {len(all_intents)} intents (showing {offset + 1}-{offset + len(paginated)})")
        else:
            output_data = {
                "intents": [
                    {
                        "intent_id": intent_id,
                        "intent_type": intent_data["intent"]["intent_type"],
                        "priority": intent_data["intent"]["priority"],
                        "phase": ctx.get_state(intent_id).phase.value if ctx.get_state(intent_id) else "UNKNOWN",
                        "created_at": intent_data["created_at"]
                    }
                    for intent_id, intent_data in paginated
                ],
                "total": len(all_intents),
                "offset": offset,
                "limit": limit
            }
            format_output(output_data, OutputFormat(output))
        
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.argument("intent_id")
@click.option("--output", "-o", type=click.Choice(["json", "table", "tree"]), default="table", help="Output format")
def audit(intent_id: str, output: str):
    """
    Get audit trail for an intent.
    
    Example:
        rct audit abc-123
    """
    try:
        ctx = get_context()
        
        # Get events from observer
        events = ctx.observer.get_intent_timeline(intent_id)
        
        if not events:
            click.echo(click.style(f"No audit trail found for intent {intent_id}", fg="yellow"), err=True)
            sys.exit(0)
        
        # Verify integrity
        is_valid = ctx.observer.verify_audit_integrity()
        
        # Format output
        if _HAS_RICH and output != "json":
            audit_data = {
                "intent_id": intent_id,
                "events": [
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type.value,
                        "timestamp": event.timestamp.isoformat(),
                        "data": event.data
                    }
                    for event in events
                ],
                "event_count": len(events),
                "integrity_verified": is_valid
            }
            render_audit_tree(audit_data)
        elif output == "table":
            headers = ["Timestamp", "Event Type", "Phase", "Status"]
            rows = [
                [
                    event.timestamp.isoformat()[:19],
                    event.event_type.value,
                    event.data.get("phase", "N/A"),
                    "✓" if event.data.get("success", True) else "✗"
                ]
                for event in events
            ]
            print_table(headers, rows)
            click.echo(f"\nTotal events: {len(events)}")
            click.echo(f"Chain integrity: {'✓ Valid' if is_valid else '✗ Invalid'}")
        else:
            output_data = {
                "intent_id": intent_id,
                "events": [
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type.value,
                        "timestamp": event.timestamp.isoformat(),
                        "data": event.data
                    }
                    for event in events
                ],
                "event_count": len(events),
                "integrity_verified": is_valid
            }
            format_output(output_data, OutputFormat(output))
        
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--output", "-o", type=click.Choice(["json", "table", "tree"]), default="json", help="Output format")
def metrics(output: str):
    """
    Get metrics summary.
    
    Example:
        rct metrics
    """
    try:
        ctx = get_context()
        
        # Get all metrics
        metrics_data = ctx.observer.get_metrics_summary()
        
        # Format output
        if _HAS_RICH and output != "json":
            render_metrics_panel(metrics_data)
        elif output == "table":
            headers = ["Metric", "Value"]
            rows = []
            for category, values in metrics_data.items():
                rows.append([f"=== {category.upper()} ===", ""])
                if isinstance(values, dict):
                    for key, val in values.items():
                        rows.append([f"  {key}", str(val)])
                else:
                    rows.append([category, str(values)])
            print_table(headers, rows)
        else:
            format_output(metrics_data, OutputFormat(output))
        
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--force", "-f", is_flag=True, help="Force reset without confirmation")
def reset(force: bool):
    """
    Reset all state and metrics.
    
    WARNING: This will delete all intents, graphs, states, and metrics.
    
    Example:
        rct reset --force
    """
    try:
        if not force:
            click.confirm("Are you sure you want to reset ALL state? This cannot be undone.", abort=True)
        
        ctx = get_context()
        
        # Count items before reset
        intent_count = len(ctx.intents)
        state_count = len(ctx.states)
        graph_count = len(ctx.graphs)
        
        # Reset
        ctx.reset_all()
        
        if _HAS_RICH:
            render_success(
                f"Reset complete: {intent_count} intents, {state_count} states, "
                f"{graph_count} graphs deleted. All metrics reset."
            )
        else:
            click.echo(click.style(f"✓ Reset complete", fg="green"))
            click.echo(f"  - Deleted {intent_count} intents")
            click.echo(f"  - Deleted {state_count} states")
            click.echo(f"  - Deleted {graph_count} graphs")
            click.echo(f"  - Reset all metrics")
        
    except click.Abort:
        click.echo("Reset cancelled")
        sys.exit(0)
    except Exception as e:
        click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


# ─── New CLI Commands (TUI-CLI Phase 4) ──────────────────────────────


@cli.group()
def adapter():
    """
    OS Adapter management commands.
    
    Examples:
        rct adapter status
        rct adapter list
    """
    pass


@adapter.command("status")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def adapter_status(output: str):
    """Show health status of all registered OS Adapters."""
    try:
        from core.adapters import ADAPTER_REGISTRY
        
        adapters_info = []
        for name, adapter_cls in ADAPTER_REGISTRY.items():
            try:
                instance = adapter_cls.__new__(adapter_cls)
                caps = instance.capabilities() if hasattr(instance, 'capabilities') else None
                adapters_info.append({
                    "name": name,
                    "version": getattr(caps, 'adapter_version', 'unknown') if caps else 'unknown',
                    "security_level": getattr(caps, 'security_level', 'unknown') if caps else 'unknown',
                    "healthy": True,
                    "supported_actions": getattr(caps, 'supported_actions', []) if caps else [],
                    "avg_latency_ms": getattr(caps, 'avg_latency_ms', 0.0) if caps else 0.0,
                })
            except Exception:
                adapters_info.append({
                    "name": name,
                    "version": "unknown",
                    "security_level": "unknown",
                    "healthy": False,
                    "supported_actions": [],
                    "avg_latency_ms": 0.0,
                })
        
        if output == "json":
            print_json({"adapters": adapters_info, "total": len(adapters_info)})
        elif _HAS_RICH:
            render_adapter_status(adapters_info)
        else:
            headers = ["Adapter", "Version", "Security", "Healthy"]
            rows = [[a["name"], a["version"], a["security_level"], "Yes" if a["healthy"] else "No"] for a in adapters_info]
            print_table(headers, rows)
    except ImportError:
        msg = "Adapter registry not available. Ensure core.adapters is installed."
        if _HAS_RICH:
            render_warning(msg)
        else:
            click.echo(click.style(msg, fg="yellow"), err=True)
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@adapter.command("list")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def adapter_list(output: str):
    """List all registered adapters and their capabilities."""
    try:
        from core.adapters import ADAPTER_REGISTRY
        
        if output == "json":
            data = {"adapters": [{"name": n, "class": c.__name__} for n, c in ADAPTER_REGISTRY.items()]}
            print_json(data)
        elif _HAS_RICH:
            from rich.table import Table as RichTable
            t = RichTable(title="Registered Adapters", border_style="cyan")
            t.add_column("Name", style="bold cyan")
            t.add_column("Class")
            t.add_column("Module")
            for name, cls in ADAPTER_REGISTRY.items():
                t.add_row(name, cls.__name__, cls.__module__)
            get_console().print(t)
        else:
            headers = ["Name", "Class"]
            rows = [[n, c.__name__] for n, c in ADAPTER_REGISTRY.items()]
            print_table(headers, rows)
    except ImportError:
        msg = "Adapter registry not available."
        if _HAS_RICH:
            render_warning(msg)
        else:
            click.echo(click.style(msg, fg="yellow"), err=True)
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--last", "-n", default=10, type=int, help="Number of recent violations to show")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def governance(last: int, output: str):
    """
    Show governance violations from the codex security layer.
    
    Example:
        rct governance --last 20
    """
    try:
        from core.adapters.base_os_adapter import THE_9_CODEX_FORBIDDEN_PATTERNS
        
        # Collect violations from observer events
        ctx = get_context()
        violations = []
        
        for event_id, event in list(ctx.observer._events.items())[-last * 5:]:
            data = event.data if hasattr(event, 'data') else {}
            if data.get("violation") or data.get("blocked"):
                violations.append({
                    "timestamp": event.timestamp.isoformat()[:19] if hasattr(event, 'timestamp') else "N/A",
                    "rule": data.get("rule", data.get("pattern", "unknown")),
                    "severity": data.get("severity", "HIGH"),
                    "description": data.get("message", data.get("reason", "Codex violation detected")),
                    "intent_id": data.get("intent_id", "N/A"),
                })
        
        # Also add simulated codex info if no real violations found
        if not violations:
            violations = []  # Empty — no violations is good
        
        violations = violations[-last:]
        
        if output == "json":
            print_json({
                "violations": violations,
                "total": len(violations),
                "codex_patterns_active": len(THE_9_CODEX_FORBIDDEN_PATTERNS),
            })
        elif _HAS_RICH:
            render_governance_violations(violations)
        else:
            if not violations:
                click.echo("No governance violations found.")
            else:
                headers = ["Time", "Rule", "Severity", "Description"]
                rows = [[v["timestamp"], v["rule"], v["severity"], v["description"][:50]] for v in violations]
                print_table(headers, rows)
    except ImportError:
        msg = "Governance module not available. Ensure core.adapters is installed."
        if _HAS_RICH:
            render_warning(msg)
        else:
            click.echo(click.style(msg, fg="yellow"), err=True)
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--agent", "-a", required=True, help="Agent ID to view timeline for")
@click.option("--from-tick", default=0, type=int, help="Start from tick number")
@click.option("--limit", "-n", default=20, type=int, help="Max deltas to show")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def timeline(agent: str, from_tick: int, limit: int, output: str):
    """
    View agent memory delta timeline.
    
    Shows the temporal sequence of actions, outcomes, and resource
    changes for a given agent.
    
    Example:
        rct timeline --agent agent-001 --from-tick 10 --limit 50
    """
    try:
        from core.kernel.memory_delta import MemoryDeltaEngine
        
        engine = MemoryDeltaEngine()
        
        # Query deltas for this agent
        all_deltas = engine.query_deltas(agent_id=agent)
        
        # Filter by tick range and limit
        filtered = [d for d in all_deltas if d.get("tick", 0) >= from_tick][:limit]
        
        if output == "json":
            print_json({"agent_id": agent, "deltas": filtered, "total": len(filtered)})
        elif _HAS_RICH:
            render_timeline(agent, filtered)
        else:
            if not filtered:
                click.echo(f"No deltas found for agent {agent}")
            else:
                headers = ["Tick", "Intent", "Action", "Outcome"]
                rows = [
                    [str(d.get("tick", "?")), d.get("intent_id", "N/A")[:12],
                     d.get("action", "N/A"), d.get("outcome", "N/A")]
                    for d in filtered
                ]
                print_table(headers, rows)
    except ImportError:
        msg = "MemoryDeltaEngine not available. Ensure core.kernel is installed."
        if _HAS_RICH:
            render_warning(msg)
        else:
            click.echo(click.style(msg, fg="yellow"), err=True)
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--hash", "-h", "packet_hash", required=True, help="SHA-256 hash of JITNAPacket to replay")
@click.option("--verify/--no-verify", default=True, help="Verify deterministic replay match")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def replay(packet_hash: str, verify: bool, output: str):
    """
    Deterministic replay of a JITNA packet execution.
    
    Replays a recorded execution and verifies deterministic
    consistency with the original run.
    
    Example:
        rct replay --hash abc123def456 --verify
    """
    try:
        from core.adapters.determinism_controller import DeterminismController
        
        controller = DeterminismController()
        
        # Attempt to look up and replay
        result = controller.replay(packet_hash=packet_hash)
        
        if result is None:
            msg = f"No recorded execution found for hash {packet_hash[:16]}..."
            if _HAS_RICH:
                render_warning(msg)
            else:
                click.echo(click.style(msg, fg="yellow"), err=True)
            sys.exit(1)
        
        original = result.get("original", {})
        replayed = result.get("replayed", {})
        match = result.get("match", False)
        
        if output == "json":
            print_json(result)
        elif _HAS_RICH:
            render_replay_result(original, replayed, match)
        else:
            click.echo(f"Replay result: {'MATCH' if match else 'MISMATCH'}")
            click.echo(f"Original hash: {original.get('hash', 'N/A')}")
            click.echo(f"Replayed hash: {replayed.get('hash', 'N/A')}")
    except ImportError:
        msg = "DeterminismController not available. Ensure core.adapters is installed."
        if _HAS_RICH:
            render_warning(msg)
        else:
            click.echo(click.style(msg, fg="yellow"), err=True)
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--adapter", "-a", default=None, help="Filter logs by adapter name")
@click.option("--tail", "-n", default=25, type=int, help="Number of recent log entries")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def logs(adapter: Optional[str], tail: int, output: str):
    """
    View adapter execution logs.
    
    Example:
        rct logs --adapter openclaw --tail 50
    """
    try:
        ctx = get_context()
        
        # Gather log entries from observer events
        log_entries = []
        events_list = list(ctx.observer._events.values()) if hasattr(ctx.observer, '_events') else []
        
        for event in events_list:
            data = event.data if hasattr(event, 'data') else {}
            adapter_name = data.get("adapter", data.get("adapter_name"))
            
            # Filter by adapter if specified
            if adapter and adapter_name and adapter.lower() != adapter_name.lower():
                continue
            
            if adapter_name or data.get("action"):
                log_entries.append({
                    "packet_id": data.get("packet_id", data.get("intent_id", "N/A"))[:16],
                    "action": data.get("action", event.event_type.value if hasattr(event, 'event_type') else "N/A"),
                    "status": data.get("status", "ok"),
                    "sha256": data.get("sha256", data.get("hash", ""))[:16],
                    "latency_ms": data.get("latency_ms", "N/A"),
                    "timestamp": event.timestamp.isoformat()[:19] if hasattr(event, 'timestamp') else "N/A",
                })
        
        log_entries = log_entries[-tail:]
        
        if output == "json":
            print_json({"logs": log_entries, "total": len(log_entries), "filter_adapter": adapter})
        elif _HAS_RICH:
            render_execution_log(log_entries)
        else:
            if not log_entries:
                click.echo("No log entries found.")
            else:
                headers = ["Packet", "Action", "Status", "Latency", "Time"]
                rows = [
                    [l["packet_id"], l["action"], l["status"],
                     str(l["latency_ms"]), l["timestamp"]]
                    for l in log_entries
                ]
                print_table(headers, rows)
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
