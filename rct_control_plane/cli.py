#!/usr/bin/env python3
"""
RCT Control Plane CLI

Command-line interface for Control Plane operations.
Provides commands for intent compilation, graph building, policy evaluation,
state management, audit trails, and metrics access.

Usage:
    delentia compile "Refactor authentication module" --user-id user-123
    delentia build --dsl-file workflow.dsl --intent-id abc-123
    delentia evaluate --intent-id abc-123
    delentia status abc-123
    delentia list --limit 20
    delentia audit abc-123
    delentia metrics
    delentia reset --force

Output Formats:
    --output json   : JSON output
    --output table  : Table format (default)
    --output tree   : Tree view (for graphs)
"""

import os
import sys
import json
import time
import signal
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, cast
from urllib.request import urlopen
from urllib.error import URLError
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
        print_splash,
        boot_sequence_animation,
        render_layout_dashboard,
        render_pipeline_flow,
        render_doctor_report,
    )
    from rct_control_plane._version import PACKAGE_VERSION, get_package_version
    _HAS_RICH = True
except ImportError:
    from rct_control_plane._version import PACKAGE_VERSION, get_package_version
    _HAS_RICH = False
    # Placeholders for monkeypatching compatibility
    get_console = None
    print_splash = None
    boot_sequence_animation = None
    render_layout_dashboard = None
    render_pipeline_flow = None
    render_doctor_report = None

from rct_control_plane.intent_compiler import IntentCompiler
from rct_control_plane.dsl_parser import DSLParser
from rct_control_plane.policy_language import PolicyEvaluator
from rct_control_plane.control_plane_state import ControlPlaneState, ControlPlanePhase
from rct_control_plane.observability import ControlPlaneObserver

# Preserve builtin list before it gets shadowed by the CLI 'list' command
_list = list


def _configure_encoding() -> None:
    """Configure stdout and stderr to use UTF-8 encoding.

    On Windows, the default encoding may be CP874 or similar which can cause
    UnicodeEncodeError when printing non-ASCII characters. This function
    safely reconfigures the streams to UTF-8, silently skipping streams
    that don't support the reconfigure() method.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            # Stream doesn't have reconfigure or is read-only (e.g., MagicMock, StringIO)
            pass



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
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths, strict=True))
    click.echo(header_line)
    click.echo("-" * len(header_line))
    
    # Print rows
    for row in rows:
        # strict=False (not True like the header above): a data row's real
        # length isn't guaranteed to match col_widths the way the header
        # row is by construction - tolerating a short/long row here
        # preserves this table renderer's existing lenient behavior.
        row_line = " | ".join(str(cell).ljust(w) for cell, w in zip(row, col_widths, strict=False))
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
@click.version_option(version=PACKAGE_VERSION, prog_name="rct")
def cli():
    """
    RCT Control Plane CLI
    
    Command-line interface for Control Plane operations.
    """
    # _configure_encoding() already existed, already had 3 passing unit tests
    # (TestConfigureEncoding in tests/test_cli_coverage_gaps.py), but was never
    # actually called from anywhere in the real program — found by running
    # `delentia compile` end-to-end on this machine (Windows, Thai-locale cp874
    # console codepage) and hitting `UnicodeEncodeError: 'charmap' codec can't
    # encode character '❌'` inside render_error(), which this function
    # exists specifically to prevent. Wiring it into the group callback (runs
    # before every subcommand, via both `delentia ...` and CliRunner-based tests)
    # makes the existing fix actually take effect instead of being dead code.
    _configure_encoding()


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
        delentia compile "Refactor authentication module" --user-id user-123
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

        # `compile()` legitimately returns intent=None when it cannot classify
        # the input into any known IntentType (e.g. it recognizes refactor/
        # build/deploy/etc. task language, not arbitrary free text) — that is
        # correct, honest behavior from the compiler itself. This command was
        # missing the corresponding check and crashed with an unhandled
        # `AttributeError: 'NoneType' object has no attribute 'id'` on any
        # such input instead of surfacing the real reason. Found by actually
        # running `delentia compile` against varied real intents, not by reading
        # the code or unit tests alone.
        if intent_obj is None:
            error_detail = "; ".join(result.errors) if result.errors else "Could not determine intent type"
            if _HAS_RICH:
                render_error(f"Compilation failed: {error_detail}")
            else:
                click.echo(click.style(f"Error: Compilation failed: {error_detail}", fg="red"), err=True)
            sys.exit(1)

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
        delentia build --dsl-file workflow.dsl --intent-id abc-123 --save
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
        delentia evaluate --intent-id abc-123 --save
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
@click.argument("intent_id", required=False, default=None)
@click.option("--output", "-o", type=click.Choice(["json", "table", "tree"]), default="table", help="Output format")
@click.option("--live", "live_status", is_flag=True, default=False, help="Render live status dashboard.")
@click.option("--interval", default=1.0, show_default=True, type=float, help="Refresh interval in seconds.")
@click.option("--refresh-count", default=0, show_default=True, type=int, help="Max refresh cycles (0 for infinite).")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host for API checks.")
@click.option("--port", "-p", default=8000, show_default=True, type=int, help="Bind port for API checks.")
def status(
    intent_id: Optional[str],
    output: str,
    live_status: bool,
    interval: float,
    refresh_count: int,
    host: str,
    port: int,
):
    """
    Get current state of an intent, or show system overview when called without arguments.

    Example:
        delentia status abc-123
        delentia status
    """
    try:
        ctx = get_context()

        # No intent_id → show system overview
        if intent_id is None:
            recent_ids = _list(ctx.intents.keys())[-3:]
            overview = {
                "status": "healthy",
                "version": PACKAGE_VERSION,
                "recent_intents": len(ctx.intents),
                "states_tracked": len(ctx.states),
                "intents_sample": recent_ids,
            }
            if live_status:
                if not _HAS_RICH:
                    click.echo("Live dashboard requires Rich support.", err=True)
                    sys.exit(1)
                if output == "json":
                    click.echo("--live is only supported with table output.", err=True)
                    sys.exit(1)

                from rich.live import Live
                live_cycles = refresh_count if refresh_count > 0 else None
                try:
                    with Live(
                        console=get_console(),
                        refresh_per_second=max(1, int(1 / interval)) if interval > 0 else 4,
                    ) as live:
                        rendered_cycles = 0
                        while True:
                            runtime_state = _build_runtime_dashboard_state(host, port)
                            live.update(
                                render_layout_dashboard(
                                    services=runtime_state["services"],
                                    endpoint=runtime_state["endpoint"],
                                    version=str(runtime_state["version"]),
                                    overall_status=str(runtime_state["overall_status"]),
                                    source=str(runtime_state["source"]),
                                    uptime_seconds=cast(Optional[float], runtime_state["uptime_seconds"]),
                                    environment=cast(Optional[str], runtime_state["environment"]),
                                )
                            )
                            rendered_cycles += 1
                            if live_cycles is not None and rendered_cycles >= live_cycles:
                                break
                            time.sleep(max(interval, 0.05))
                except KeyboardInterrupt:
                    if _HAS_RICH:
                        render_warning("Live dashboard stopped by Ctrl-C")
                    else:
                        click.echo("Live dashboard stopped by Ctrl-C", err=True)
                    raise SystemExit(130) from None
                _print_next_steps(
                    [
                        "Run [bold cyan]delentia doctor[/] for dependency and port diagnostics",
                        f"Run [bold cyan]delentia start --host {host} --port {port}[/] to bring the API online",
                    ]
                )
                return

            if output == "json":
                print_json(overview)
            elif _HAS_RICH:
                render_state_panel(overview)
            else:
                click.echo(f"Status: {overview['status']}")
                click.echo(f"Version: {overview['version']}")
                click.echo(f"Recent intents: {overview['recent_intents']}")
            return

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
        delentia list --limit 20
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
        delentia audit abc-123
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
        delentia metrics
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
        delentia reset --force
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
            click.echo(click.style("✓ Reset complete", fg="green"))
            click.echo(f"  - Deleted {intent_count} intents")
            click.echo(f"  - Deleted {state_count} states")
            click.echo(f"  - Deleted {graph_count} graphs")
            click.echo("  - Reset all metrics")
        
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
        delentia adapter status
        delentia adapter list
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
        delentia governance --last 20
    """
    try:
        from core.adapters.base_os_adapter import THE_9_CODEX_FORBIDDEN_PATTERNS
        
        # Collect violations from observer events
        ctx = get_context()
        violations = []
        
        for _event_id, event in list(ctx.observer._events.items())[-last * 5:]:
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
        delentia timeline --agent agent-001 --from-tick 10 --limit 50
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
        delentia replay --hash abc123def456 --verify
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


def _package_version(distribution: str) -> Optional[str]:
    """Return an installed distribution version when available."""
    if distribution == "rct-platform":
        return get_package_version()
    try:
        import importlib.metadata as importlib_metadata

        return importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        return None


def _run_doctor_checks() -> List[Dict[str, Any]]:
    """Collect environment, project, and local connectivity diagnostics."""
    checks: List[Dict[str, Any]] = []

    checks.append(
        {
            "category": "environment",
            "name": "Python",
            "ok": sys.version_info >= (3, 10),
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "hint": "Use Python 3.10 or newer.",
        }
    )

    for package_name, distribution in [
        ("click", "click"),
        ("rich", "rich"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("pydantic", "pydantic"),
    ]:
        version = _package_version(distribution)
        checks.append(
            {
                "category": "environment",
                "name": package_name,
                "ok": version is not None,
                "detail": version or "not installed",
                "hint": f"Install with: pip install {distribution}",
            }
        )

    for file_name, hint in [
        (".env", "Run delentia init to generate the environment file."),
        (".env.example", "Commit or regenerate the template with delentia init --force."),
        ("pyproject.toml", "Run from the project root or restore pyproject.toml."),
    ]:
        path = Path(file_name)
        is_readable = path.exists() and path.is_file()
        checks.append(
            {
                "category": "project",
                "name": file_name,
                "ok": is_readable,
                "detail": "readable" if is_readable else "missing",
                "hint": hint,
            }
        )

    for port in range(8000, 8005):
        started = time.perf_counter()
        is_online = False
        latency_ms: Optional[float] = None
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                is_online = True
                latency_ms = (time.perf_counter() - started) * 1000
        except OSError:
            is_online = False

        detail = f"online ({latency_ms:.1f}ms)" if latency_ms is not None else "offline"
        checks.append(
            {
                "category": "connectivity",
                "name": f"127.0.0.1:{port}",
                "ok": is_online,
                "detail": detail,
                "hint": f"Run delentia start --port {port} if this service should be available.",
            }
        )

    return checks


def _collect_log_entries(ctx, adapter: Optional[str], tail: int) -> List[Dict[str, Any]]:
    log_entries = []
    events_list = list(ctx.observer._events.values()) if hasattr(ctx.observer, '_events') else []
    for event in events_list:
        data = event.data if hasattr(event, 'data') else {}
        adapter_name = data.get("adapter", data.get("adapter_name"))
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
    return log_entries[-tail:]


@cli.command(name="init")
@click.option("--force", is_flag=True, help="Overwrite existing .env file")
def init(force: bool):
    """Initialize environment — create .env from .env.example template.

    Example:
        delentia init
        delentia init --force   # Overwrite existing .env
    """
    env_path = Path(".env")
    example_path = Path(".env.example")

    # Search for .env.example relative to package root if not found locally
    if not example_path.exists():
        try:
            import rct_control_plane as _rcp

            pkg_root = Path(_rcp.__file__).parent.parent
            example_path = pkg_root / ".env.example"
        except Exception:
            pass

    if env_path.exists() and not force:
        if _HAS_RICH:
            render_warning(".env already exists. Use --force to overwrite.")
        else:
            click.echo(
                click.style(
                    "Warning: .env already exists. Use --force to overwrite.",
                    fg="yellow",
                )
            )
        return

    if not example_path.exists():
        # Built-in fallback template when example is missing
        env_content = (
            "# Built-in fallback template\n"
            "RCT_CORE_BRAIN_KEY=<your-openrouter-key>\n"
            "GOOGLE_API_KEY=<your-gemini-key>\n"
            "RCTDB_URL=postgresql://localhost:5432/rctdb_dev\n"
        )
        env_path.write_text(env_content, encoding="utf-8")
        click.echo("Created .env file using built-in fallback template")
        return

    import shutil

    shutil.copy(str(example_path), str(env_path))

    if _HAS_RICH:
        console = get_console()
        render_success(".env created from .env.example template")
        console.print()
        console.print("  [bold]Next steps:[/]")
        console.print(
            "  [dim]1.[/]  Open [bold cyan].env[/] and fill in your API keys:"
        )
        console.print("       [dim]RCT_CORE_BRAIN_KEY=<openrouter-key>[/]")
        console.print("       [dim]GOOGLE_API_KEY=<google-gemini-key>  (optional)[/]")
        console.print("       [dim]RCTDB_URL=postgresql://localhost:5432/rctdb_dev[/]")
        console.print()
        console.print(
            "  [dim]2.[/]  Run [bold cyan]delentia doctor[/] to verify the environment"
        )
        console.print("  [dim]3.[/]  Run [bold cyan]delentia start[/] to launch the system")
        console.print()
    else:
        click.echo(
            ".env created. Fill in your API keys, then run: delentia doctor, then delentia start"
        )


@cli.command(name="doctor")
@click.option(
    "--output",
    "output",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
def doctor_cmd(output: str):
    """Run local preflight checks for the RCT development environment."""
    checks = _run_doctor_checks()
    issues = sum(1 for check in checks if not check["ok"])
    summary = {
        "issues": issues,
        "ok": issues == 0,
        "checks": checks,
    }

    if output == "json":
        print_json(summary)
        return

    if _HAS_RICH:
        render_doctor_report(checks, issues)
    else:
        print_table(
            ["Category", "Check", "Status", "Detail", "Hint"],
            [
                [
                    str(check["category"]),
                    str(check["name"]),
                    "OK" if check["ok"] else "FAIL",
                    str(check["detail"]),
                    str(check["hint"] if not check["ok"] else "—"),
                ]
                for check in checks
            ],
        )
        click.echo(
            f"Doctor summary: {'healthy' if issues == 0 else f'{issues} issue(s) found'}"
        )

    next_steps: List[str] = []
    if any(check["name"] == ".env" and not check["ok"] for check in checks):
        next_steps.append(
            "Run [bold cyan]delentia init[/] to create .env"
            if _HAS_RICH
            else "Run delentia init to create .env"
        )
    if any(check["category"] == "connectivity" and not check["ok"] for check in checks):
        next_steps.append(
            "Run [bold cyan]delentia start[/] to bring the local API online"
            if _HAS_RICH
            else "Run delentia start to bring the local API online"
        )
    if not next_steps:
        next_steps.append(
            "Run [bold cyan]delentia benchmark --suite fdia[/] to validate constitutional behavior"
            if _HAS_RICH
            else "Run delentia benchmark --suite fdia to validate constitutional behavior"
        )
    _print_next_steps(next_steps)


@cli.command()
@click.option("--adapter", "-a", default=None, help="Filter logs by adapter name")
@click.option("--tail", "-n", default=25, type=int, help="Number of recent log entries")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
@click.option("--follow", "-f", "follow_logs", is_flag=True, default=False, help="Follow log stream in real time.")
@click.option("--interval", default=1.0, show_default=True, type=float, help="Refresh interval in seconds.")
@click.option("--refresh-count", default=0, show_default=True, type=int, help="Max refresh cycles (0 for infinite).")
def logs(
    adapter: Optional[str],
    tail: int,
    output: str,
    follow_logs: bool,
    interval: float,
    refresh_count: int,
):
    """
    View adapter execution logs.

    Example:
        delentia logs --adapter openclaw --tail 50
    """
    try:
        ctx = get_context()

        if follow_logs:
            if output == "json":
                click.echo("Follow mode is only supported with table output.", err=True)
                sys.exit(1)

            if not _HAS_RICH:
                click.echo("Follow mode requires Rich support.", err=True)
                sys.exit(1)

            from rich.live import Live
            live_cycles = refresh_count if refresh_count > 0 else None
            rendered_cycles = 0
            try:
                with Live(console=get_console(), refresh_per_second=max(1, int(1 / interval)) if interval > 0 else 4) as live:
                    while True:
                        current_logs = _collect_log_entries(ctx, adapter, tail)
                        live.update(render_execution_log(current_logs))
                        rendered_cycles += 1
                        if live_cycles is not None and rendered_cycles >= live_cycles:
                            break
                        time.sleep(max(interval, 0.05))
            except KeyboardInterrupt:
                pass
            return

        log_entries = _collect_log_entries(ctx, adapter, tail)

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
                    [entry["packet_id"], entry["action"], entry["status"],
                     str(entry["latency_ms"]), entry["timestamp"]]
                    for entry in log_entries
                ]
                print_table(headers, rows)
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)



# ─── version command ──────────────────────────────────────────────────────────


@cli.command("version")
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format.",
)
def version_command(output: str) -> None:
    """Show Delentia OS version information."""
    import importlib.metadata as _meta

    try:
        pkg_ver = _meta.version("delentia-os")
    except _meta.PackageNotFoundError:
        from rct_control_plane._version import PACKAGE_VERSION
        pkg_ver = PACKAGE_VERSION

    try:
        python_ver = sys.version.split()[0]
    except Exception:
        python_ver = "unknown"

    data = {
        "version": pkg_ver,
        "package": "delentia-os",
        "name": "delentia-os",
        "description": "Constitutional AI Operating System SDK",
        "python": python_ver,
        "license": "Apache-2.0",
        "homepage": "https://delentia.com",
        "repository": "https://github.com/delentia-labs/delentia-os",
    }

    if output == "json":
        print_json(data)
    elif _HAS_RICH:
        from rich.table import Table
        table = Table(title="Delentia OS — Version Info")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        for k, v in data.items():
            table.add_row(k, v)
        get_console().print(table)
    else:
        click.echo(f"delentia-os  v{data['version']}")
        click.echo(f"Python        {data['python']}")
        click.echo(f"License       {data['license']}")
        click.echo(f"Homepage      {data['homepage']}")


# ─── serve command ────────────────────────────────────────────────────────────


@cli.group("model")
def model_group():
    """
    Choose which LLM drives the agent (Round 48, bring-your-own-model).

    Provider/model resolve from: env DELENTIA_LLM_PROVIDER / DELENTIA_LLM_MODEL,
    then ~/.delentia/model.json (profile entry, then default), then built-ins.
    API keys are never stored in the config - set OPENROUTER_API_KEY in env.

    Examples:
        delentia model show
        delentia model list --provider openrouter --search claude
        delentia model set anthropic/claude-sonnet-5 --provider openrouter
        delentia model set qwen2.5:7b --provider ollama --profile researcher
    """
    pass


@model_group.command("show")
@click.option("--profile", default=None, help="Show the selection for this agent profile.")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def model_show(profile: Optional[str], output: str) -> None:
    """Show the active provider/model and where each value came from."""
    from rct_control_plane.model_config import ModelConfigError, config_path, resolve_model_selection
    try:
        sel = resolve_model_selection(profile=profile)
    except ModelConfigError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    data = {**sel.to_dict(), "config_file": str(config_path()),
            "openrouter_key_set": bool(os.getenv("OPENROUTER_API_KEY"))}
    if output == "json":
        click.echo(json.dumps(data, indent=2))
        return
    click.echo(f"provider : {sel.provider}  ({sel.provider_source})")
    click.echo(f"model    : {sel.model}  ({sel.model_source})")
    click.echo(f"config   : {data['config_file']}")
    if sel.provider == "openrouter" and not data["openrouter_key_set"]:
        click.echo(click.style("warning  : OPENROUTER_API_KEY is not set - the agent will fall back to Ollama",
                               fg="yellow"))


@model_group.command("list")
@click.option("--provider", type=click.Choice(["openrouter", "ollama"]), default="openrouter", show_default=True)
@click.option("--search", default=None, help="Only models whose id contains this text.")
@click.option("--all", "show_all", is_flag=True, default=False,
              help="Include models without JSON-mode support (they cannot drive the agent loop).")
@click.option("--limit", default=50, show_default=True, type=int)
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def model_list(provider: str, search: Optional[str], show_all: bool, limit: int, output: str) -> None:
    """List models the agent can use. OpenRouter's catalog needs no API key."""
    from rct_control_plane.model_config import filter_models, list_ollama_models, list_openrouter_models
    try:
        models = list_openrouter_models() if provider == "openrouter" else list_ollama_models()
    except Exception as exc:  # network/HTTP errors are reported, not raised
        click.echo(click.style(f"Error: could not list {provider} models: {exc}", fg="red"), err=True)
        sys.exit(1)
    shown = filter_models(models, agent_capable_only=not show_all, search=search)[: max(limit, 0)]
    if output == "json":
        click.echo(json.dumps([m.to_dict() for m in shown], indent=2))
        return
    if not shown:
        click.echo("No matching models.")
        return
    click.echo(f"{'model':<52} {'context':>9} {'$/Mtok in':>10} {'$/Mtok out':>11} tools")
    for m in shown:
        ctx = f"{m.context_length:,}" if m.context_length else "-"
        pin = f"{m.prompt_price_per_mtok:g}" if m.prompt_price_per_mtok is not None else "-"
        pout = f"{m.completion_price_per_mtok:g}" if m.completion_price_per_mtok is not None else "-"
        click.echo(f"{m.id:<52} {ctx:>9} {pin:>10} {pout:>11} {'yes' if m.supports_tools else 'no'}")
    click.echo(f"\n{len(shown)} shown. Selecting a model changes how capable the agent is, not how safe:"
               " FDIA gating and approvals are enforced in code.")


@model_group.command("set")
@click.argument("model_id")
@click.option("--provider", type=click.Choice(["openrouter", "ollama"]), required=True)
@click.option("--profile", default=None, help="Set the model for one agent profile only.")
@click.option("--verify/--no-verify", default=True, show_default=True,
              help="Check the model exists in the provider's catalog before saving.")
def model_set(model_id: str, provider: str, profile: Optional[str], verify: bool) -> None:
    """Save the model the agent uses (writes ~/.delentia/model.json)."""
    from rct_control_plane.model_config import (
        ModelConfigError, list_ollama_models, list_openrouter_models, save_model_selection,
    )
    if verify:
        try:
            catalog = list_openrouter_models() if provider == "openrouter" else list_ollama_models()
        except Exception as exc:
            click.echo(click.style(f"Error: could not verify against the {provider} catalog ({exc}); "
                                   "retry, or pass --no-verify", fg="red"), err=True)
            sys.exit(1)
        match = next((m for m in catalog if m.id == model_id), None)
        if match is None:
            click.echo(click.style(f"Error: '{model_id}' is not in the {provider} catalog "
                                   f"(see `delentia model list --provider {provider}`)", fg="red"), err=True)
            sys.exit(1)
        if not match.supports_json_mode:
            click.echo(click.style(f"Error: '{model_id}' does not support JSON mode, which the agent loop "
                                   "needs to choose tools", fg="red"), err=True)
            sys.exit(1)
    try:
        path = save_model_selection(provider, model_id, profile=profile)
    except ModelConfigError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    scope = f"profile '{profile}'" if profile else "default"
    click.echo(f"Saved {provider}:{model_id} as the {scope} model in {path}")
    if os.getenv("DELENTIA_LLM_MODEL") or os.getenv("DELENTIA_LLM_PROVIDER"):
        click.echo(click.style("note: DELENTIA_LLM_PROVIDER/DELENTIA_LLM_MODEL env vars are set and take "
                               "precedence over this config", fg="yellow"))


@cli.group("approvals")
def approvals_group():
    """
    Human approval for paused agent actions (Round 48).

    The agent pauses repo writes and medium-risk commands. A trusted
    approver signs the exact action with an Ed25519 key kept outside the
    repository - ideally on another device, since the agent's shell sandbox
    runs as the same OS user and is not a jail (`sign` works offline).

    Examples:
        delentia approvals keygen --out ~/.delentia/keys/architect.pem --trust Architect
        delentia approvals list
        delentia approvals approve <id> --key ~/.delentia/keys/architect.pem
        delentia approvals sign <id> --digest <sha256> --key <pem>   (offline, for a remote host)
    """
    pass


def _approval_store(db: Optional[str]):
    from rct_control_plane.approvals import PendingActionStore
    from rct_control_plane.persistence import ControlPlanePersistence
    return PendingActionStore(ControlPlanePersistence(db_path=db) if db else ControlPlanePersistence())


@approvals_group.command("keygen")
@click.option("--out", "out_path", required=True, help="Where to write the private key (outside the repo).")
@click.option("--trust", "trust_name", default=None,
              help="Also add the public key to ~/.delentia/approvers.json under this name.")
def approvals_keygen(out_path: str, trust_name: Optional[str]) -> None:
    """Create an approver key pair."""
    from rct_control_plane.approvals import ApprovalError, _approvers_file, generate_approver_key
    try:
        public_hex = generate_approver_key(out_path)
    except ApprovalError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    click.echo(f"private key : {Path(out_path).expanduser()}  (keep it off the agent host if you can)")
    click.echo(f"public key  : {public_hex}")
    if trust_name:
        path = _approvers_file()
        entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        entries.append({"name": trust_name, "public_key_hex": public_hex})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        click.echo(f"trusted as '{trust_name}' in {path}")
    else:
        click.echo("To trust it on the agent host, add it to DELENTIA_APPROVER_PUBKEYS or ~/.delentia/approvers.json")


@approvals_group.command("list")
@click.option("--status", default="PENDING", show_default=True,
              type=click.Choice(["PENDING", "APPROVED", "REJECTED", "EXECUTING", "EXECUTED", "ALL"],
                                case_sensitive=False))
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def approvals_list(status: str, db: Optional[str], output: str) -> None:
    """List paused actions."""
    store = _approval_store(db)
    actions = store.list(status=None if status.upper() == "ALL" else status)
    if output == "json":
        click.echo(json.dumps([a.to_dict() for a in actions], indent=2, default=str))
        return
    if not actions:
        click.echo(f"No {status.lower()} actions.")
        return
    for a in actions:
        click.echo(f"{a.approval_id}  {a.status:<9} {a.namespace}  {a.tool_name} {json.dumps(a.tool_args)[:80]}")
        click.echo(f"    goal   : {a.goal[:100]}")
        click.echo(f"    digest : {a.action_sha256}")


@approvals_group.command("sign")
@click.argument("approval_id")
@click.option("--digest", required=True, help="The action_sha256 shown by `list` or the API.")
@click.option("--key", "key_path", required=True, help="Approver private key (PEM).")
@click.option("--decision", type=click.Choice(["approve", "reject"]), default="approve", show_default=True)
def approvals_sign(approval_id: str, digest: str, key_path: str, decision: str) -> None:
    """Sign a decision offline; prints the JSON body for the decision API."""
    from rct_control_plane.approvals import sign_decision
    signed = sign_decision(key_path, approval_id, digest, "APPROVED" if decision == "approve" else "REJECTED")
    click.echo(json.dumps(signed, indent=2))


def _decide_locally(approval_id: str, key_path: str, decision: str, db: Optional[str]) -> None:
    from rct_control_plane.approvals import ApprovalError, sign_decision
    store = _approval_store(db)
    action = store.get(approval_id)
    if action is None:
        click.echo(click.style(f"Error: no pending action {approval_id!r}", fg="red"), err=True)
        sys.exit(1)
    click.echo(f"{decision.lower()}: {action.tool_name} {json.dumps(action.tool_args)[:200]}")
    try:
        signed = sign_decision(key_path, approval_id, action.action_sha256, decision)
        decided = store.decide(approval_id, decision, signed["public_key_hex"], signed["signature_hex"])
    except ApprovalError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    click.echo(f"{approval_id} is now {decided.status}")
    if decided.status == "APPROVED":
        click.echo(f"Resume it with: POST /v1/agent/approvals/{approval_id}/resume")


@approvals_group.command("approve")
@click.argument("approval_id")
@click.option("--key", "key_path", required=True, help="Approver private key (PEM).")
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
def approvals_approve(approval_id: str, key_path: str, db: Optional[str]) -> None:
    """Sign and record approval of one paused action (local DB)."""
    _decide_locally(approval_id, key_path, "APPROVED", db)


@approvals_group.command("reject")
@click.argument("approval_id")
@click.option("--key", "key_path", required=True, help="Approver private key (PEM).")
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
def approvals_reject(approval_id: str, key_path: str, db: Optional[str]) -> None:
    """Sign and record rejection of one paused action (local DB)."""
    _decide_locally(approval_id, key_path, "REJECTED", db)


@approvals_group.command("architect-token")
@click.option("--key", "key_path", required=True, help="Approver private key (PEM).")
@click.option("--key-id", required=True, help="The key_id listed in the Worker's FDIA_ARCHITECT_KEYS_JSON.")
@click.option("--action", "action_name", required=True, help="Exact action_name the caller will evaluate.")
@click.option("--payload", default="", help="Exact target_payload (or caller_context) the caller will send.")
@click.option("--ttl", default=900, show_default=True, type=int, help="Seconds until it expires (max 86400).")
def approvals_architect_token(key_path: str, key_id: str, action_name: str, payload: str, ttl: int) -> None:
    """Sign an Architect token for evaluate_fdia (delentia-mcp-ecosystem)."""
    from rct_control_plane.approvals import sign_architect_token
    click.echo(sign_architect_token(key_path, key_id, action_name, payload, ttl))


@approvals_group.command("architect-key-entry")
@click.option("--key", "key_path", required=True, help="Approver private key (PEM).")
@click.option("--key-id", required=True)
@click.option("--role", default="Chief_Architect", show_default=True)
def approvals_architect_key_entry(key_path: str, key_id: str, role: str) -> None:
    """Print the public-key entry for the Worker's FDIA_ARCHITECT_KEYS_JSON."""
    from rct_control_plane.approvals import architect_key_entry
    click.echo(json.dumps(architect_key_entry(key_path, key_id, role)))


@cli.group("experiments")
def experiments_group():
    """
    RCTDB experiments: every governed agent episode is recorded as a run
    (Round 48), grouped by goal, so repeated attempts can be compared.

    Examples:
        delentia experiments list
        delentia experiments compare governed-loop:<hash>
    """
    pass


@experiments_group.command("list")
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
@click.option("--limit", default=20, show_default=True, type=int)
def experiments_list(db: Optional[str], limit: int) -> None:
    """Experiments with their run counts, most recent first."""
    persistence = _audit_db(db)
    with persistence._connect() as conn:
        rows = conn.execute(
            "SELECT e.id, e.name, COUNT(r.id), MAX(r.timestamp) FROM experiments e "
            "LEFT JOIN experiment_runs r ON r.experiment_id = e.id GROUP BY e.id "
            "ORDER BY MAX(r.timestamp) DESC LIMIT ?", (limit,),
        ).fetchall()
    if not rows:
        click.echo("No experiments recorded yet.")
        return
    for exp_id, name, runs, last in rows:
        click.echo(f"{exp_id}  runs={runs}  last={last}  {name[:70]}")


@experiments_group.command("compare")
@click.argument("experiment_id")
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
def experiments_compare(experiment_id: str, db: Optional[str]) -> None:
    """First run vs latest run for every numeric metric (JSON)."""
    persistence = _audit_db(db)
    runs = persistence.get_experiment_runs(experiment_id)
    click.echo(json.dumps({"experiment_id": experiment_id, "runs": len(runs),
                           "first_vs_last": persistence.compare_experiment_runs(experiment_id)}, indent=2))


@cli.group("audit-chain")
def audit_chain_group():
    """
    Tamper-evident audit trail (Round 48, tier A1).

    Every audit_trail row is hash-chained; with DELENTIA_AUDIT_SIGNING_KEY set
    each link is also Ed25519-signed. `verify` recomputes the whole chain.
    (`delentia audit <intent_id>` is the older per-intent audit viewer.)

    Examples:
        delentia audit-chain verify
        delentia audit-chain verify --pubkey <hex>
        delentia audit-chain head          (value to publish outside the host)
        delentia audit-chain keygen --out ~/.delentia/keys/audit-signer.pem
        delentia audit-chain anchor --url <witness> --key-id <id>         (tier A3)
        delentia audit-chain check-anchors --url <witness> --key-id <id>
    """
    pass


def _audit_db(db: Optional[str]):
    from rct_control_plane.persistence import ControlPlanePersistence
    return ControlPlanePersistence(db_path=db) if db else ControlPlanePersistence()


@audit_chain_group.command("verify")
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
@click.option("--pubkey", default=None, help="Expected signer public key hex (or DELENTIA_AUDIT_PUBKEY).")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table", help="Output format")
def audit_chain_verify(db: Optional[str], pubkey: Optional[str], output: str) -> None:
    """Recompute every link; exit 1 on the first break."""
    from rct_control_plane import audit_chain
    persistence = _audit_db(db)
    with persistence._connect() as conn:
        report = audit_chain.verify_audit_chain(conn, public_key_hex=pubkey)
    if output == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
    else:
        status = click.style("OK", fg="green") if report.ok else click.style("BROKEN", fg="red")
        click.echo(f"chain      : {status}")
        click.echo(f"rows       : {report.chained_rows} chained, {report.signed_rows} signed, "
                   f"{report.legacy_unchained_rows} legacy (written before the chain existed)")
        click.echo(f"head       : seq={report.head_seq} hash={report.head_hash}")
        if not report.ok:
            click.echo(f"first break: seq={report.first_bad_seq} - {report.reason}")
    if not report.ok:
        sys.exit(1)


@audit_chain_group.command("head")
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
def audit_chain_head(db: Optional[str]) -> None:
    """Print the latest chain position and hash (JSON)."""
    from rct_control_plane import audit_chain
    persistence = _audit_db(db)
    with persistence._connect() as conn:
        click.echo(json.dumps(audit_chain.chain_head(conn)))


@audit_chain_group.command("keygen")
@click.option("--out", "out_path", required=True, help="Where to write the signing key (outside the repo).")
def audit_chain_keygen(out_path: str) -> None:
    """Create the audit signing key; then set DELENTIA_AUDIT_SIGNING_KEY to its path."""
    from rct_control_plane import audit_chain
    try:
        public_hex = audit_chain.generate_signing_key(out_path)
    except ValueError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    click.echo(f"private key : {Path(out_path).expanduser()}")
    click.echo(f"public key  : {public_hex}  (publish this; verifiers pass it as --pubkey)")
    click.echo(f"then set {audit_chain.SIGNING_KEY_ENV}={Path(out_path).expanduser()} for the API process")


@audit_chain_group.command("anchor")
@click.option("--url", required=True, help="Witness base URL (the fdia Worker), e.g. https://delentia-fdia-mcp.<account>.workers.dev")
@click.option("--key-id", required=True, help="Key id the witness knows the public key under (AUDIT_ANCHOR_KEYS_JSON).")
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
def audit_chain_anchor(url: str, key_id: str, db: Optional[str]) -> None:
    """Sign the current chain head and publish it to the outside witness (tier A3)."""
    import httpx
    from rct_control_plane import audit_chain
    persistence = _audit_db(db)
    try:
        with persistence._connect() as conn:
            body = audit_chain.sign_anchor(conn, key_id)
    except ValueError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    resp = httpx.post(f"{url.rstrip('/')}/v1/audit/anchor", json=body, timeout=20.0)
    click.echo(json.dumps({"status": resp.status_code, **resp.json()}))
    if resp.status_code not in (200, 201):
        sys.exit(1)


@audit_chain_group.command("check-anchors")
@click.option("--url", required=True, help="Witness base URL.")
@click.option("--key-id", required=True, help="Key id to check.")
@click.option("--db", default=None, help="Persistence DB (default: the kernel's).")
def audit_chain_check_anchors(url: str, key_id: str, db: Optional[str]) -> None:
    """Check every head anchored at the witness against this chain; exit 1 on any mismatch."""
    import httpx
    from rct_control_plane import audit_chain
    resp = httpx.get(f"{url.rstrip('/')}/v1/audit/anchor/{key_id}", params={"limit": 1000}, timeout=20.0)
    if resp.status_code != 200:
        click.echo(json.dumps({"ok": False, "status": resp.status_code, **resp.json()}))
        sys.exit(1)
    persistence = _audit_db(db)
    with persistence._connect() as conn:
        report = audit_chain.check_anchors(conn, resp.json())
    click.echo(json.dumps(report))
    if not report["ok"]:
        sys.exit(1)


@cli.group("notary")
def notary_group():
    """
    Audit notary: a separate process that holds the signing key (Round 50, tier A2).

    Run it as a different OS user from the agent (or on another machine) so
    the agent can append records but never read the key or rewrite the log.
    The agent's API process finds it through DELENTIA_NOTARY_URL (and
    DELENTIA_NOTARY_TOKEN); every tool call is then recorded before it runs,
    and refused if the notary cannot record it.

    Examples:
        delentia notary keygen --out ~/.delentia-notary/notary.pem
        DELENTIA_NOTARY_KEY=... delentia notary serve --port 8765
        delentia notary verify --pubkey <hex>
        delentia notary head
        delentia notary anchor --url <witness> --key-id delentia-notary-1   (tier A3)
    """
    pass


_DEFAULT_NOTARY_DB = "~/.delentia-notary/notary.db"


def _notary_key(key_path: Optional[str]):
    from rct_control_plane import notary
    path = key_path or os.getenv(notary.NOTARY_KEY_ENV)
    if not path:
        click.echo(click.style(f"Error: pass --key or set {notary.NOTARY_KEY_ENV}", fg="red"), err=True)
        sys.exit(1)
    try:
        return notary.load_key(path)
    except (ValueError, OSError) as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)


@notary_group.command("keygen")
@click.option("--out", "out_path", required=True, help="Where to write the notary key (outside the repo).")
def notary_keygen(out_path: str) -> None:
    """Create the notary's Ed25519 key."""
    from rct_control_plane import notary
    try:
        public_hex = notary.generate_key(out_path)
    except ValueError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    click.echo(f"private key : {Path(out_path).expanduser()}  (restrict it to the notary's OS user; on Windows use icacls)")
    click.echo(f"public key  : {public_hex}  (publish this; verifiers pass it as --pubkey)")


@notary_group.command("serve")
@click.option("--db", default=_DEFAULT_NOTARY_DB, show_default=True, help="The notary's own log.")
@click.option("--key", "key_path", default=None, help="Notary key (or DELENTIA_NOTARY_KEY).")
@click.option("--key-id", default="delentia-notary-1", show_default=True, help="Key id written into receipts.")
@click.option("--port", default=8765, show_default=True, type=int, help="Loopback port.")
@click.option("--anchor-url", default=None, help="Witness base URL: anchor the log head on a schedule (tier A3).")
@click.option("--anchor-key-id", default=None, help="Key id the witness knows this notary's public key under.")
@click.option("--anchor-every", default=3600.0, show_default=True, type=float, help="Seconds between anchors.")
def notary_serve(db: str, key_path: Optional[str], key_id: str, port: int, anchor_url: Optional[str] = None,
                 anchor_key_id: Optional[str] = None, anchor_every: float = 3600.0) -> None:
    """Serve POST /append and GET /head on 127.0.0.1 (token: DELENTIA_NOTARY_TOKEN)."""
    from rct_control_plane import notary
    key = _notary_key(key_path)
    store = notary.NotaryStore(db, key, key_id)
    server = notary.make_server(store, port=port, token=os.getenv(notary.NOTARY_TOKEN_ENV))
    click.echo(f"notary      : http://127.0.0.1:{port}  key_id={key_id}  pubkey={notary.public_hex(key)}")
    click.echo(f"log         : {store.db_path}")
    click.echo(f"agent side  : set {notary.NOTARY_URL_ENV}=http://127.0.0.1:{port} "
               f"(and {notary.NOTARY_TOKEN_ENV} if set here)")
    stop_anchoring = None
    if anchor_url:
        if not anchor_key_id:
            click.echo(click.style("Error: --anchor-url needs --anchor-key-id", fg="red"), err=True)
            sys.exit(1)
        click.echo(f"anchoring   : every {anchor_every:.0f}s to {anchor_url} as {anchor_key_id}")
        stop_anchoring = notary.start_anchor_loop(
            store.db_path, anchor_key_id, key, anchor_url, anchor_every,
            on_result=lambda r: click.echo(f"anchor      : {json.dumps(r)}"),
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if stop_anchoring is not None:
            stop_anchoring.set()
        server.server_close()


@notary_group.command("verify")
@click.option("--db", default=_DEFAULT_NOTARY_DB, show_default=True, help="The notary's log.")
@click.option("--pubkey", required=True, help="The notary's public key hex.")
def notary_verify(db: str, pubkey: str) -> None:
    """Recompute every entry and signature; exit 1 on the first break."""
    from rct_control_plane import notary
    report = notary.verify_log(db, pubkey)
    click.echo(json.dumps(report.to_dict(), indent=2))
    if not report.ok:
        sys.exit(1)


@notary_group.command("head")
@click.option("--db", default=_DEFAULT_NOTARY_DB, show_default=True, help="The notary's log.")
def notary_head(db: str) -> None:
    """Print the latest entry position and hash (JSON)."""
    import sqlite3
    with sqlite3.connect(str(Path(db).expanduser())) as conn:
        row = conn.execute("SELECT seq, hash FROM notary_log ORDER BY seq DESC LIMIT 1").fetchone()
    click.echo(json.dumps({"seq": row[0], "row_hash": row[1]} if row else None))


@notary_group.command("anchor")
@click.option("--url", required=True, help="Witness base URL (the fdia Worker).")
@click.option("--key-id", required=True, help="Key id the witness knows the notary's public key under.")
@click.option("--db", default=_DEFAULT_NOTARY_DB, show_default=True, help="The notary's log.")
@click.option("--key", "key_path", default=None, help="Notary key (or DELENTIA_NOTARY_KEY).")
def notary_anchor(url: str, key_id: str, db: str, key_path: Optional[str]) -> None:
    """Sign the notary log's head and publish it to the outside witness (tier A3)."""
    import httpx
    from rct_control_plane import notary
    try:
        body = notary.sign_anchor(db, key_id, _notary_key(key_path))
    except ValueError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    resp = httpx.post(f"{url.rstrip('/')}/v1/audit/anchor", json=body, timeout=20.0)
    click.echo(json.dumps({"status": resp.status_code, **resp.json()}))
    if resp.status_code not in (200, 201):
        sys.exit(1)


@notary_group.command("check-anchors")
@click.option("--url", required=True, help="Witness base URL.")
@click.option("--key-id", required=True, help="Key id to check.")
@click.option("--db", default=_DEFAULT_NOTARY_DB, show_default=True, help="The notary's log.")
def notary_check_anchors(url: str, key_id: str, db: str) -> None:
    """Check every head anchored at the witness against the notary log; exit 1 on any mismatch."""
    import httpx
    from rct_control_plane import notary
    resp = httpx.get(f"{url.rstrip('/')}/v1/audit/anchor/{key_id}", params={"limit": 1000}, timeout=20.0)
    if resp.status_code != 200:
        click.echo(json.dumps({"ok": False, "status": resp.status_code, **resp.json()}))
        sys.exit(1)
    report = notary.check_anchors(db, resp.json())
    click.echo(json.dumps(report))
    if not report["ok"]:
        sys.exit(1)


@cli.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host.")
@click.option("--port", "-p", default=8000, show_default=True, type=int, help="Bind port.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (dev mode).")
@click.option("--workers", default=1, show_default=True, type=int, help="Number of worker processes.")
@click.option("--allow-no-auth", is_flag=True, default=False,
              help="Bind a non-loopback host without DELENTIA_API_TOKEN (not recommended).")
def serve_command(host: str, port: int, reload: bool, workers: int, allow_no_auth: bool = False) -> None:
    """Start the Delentia OS API server (requires uvicorn)."""
    from rct_control_plane.api_auth import TOKEN_ENV, bind_is_loopback
    if not bind_is_loopback(host) and not os.getenv(TOKEN_ENV) and not allow_no_auth:
        click.echo(click.style(
            f"Error: refusing to serve the agent API on {host} without {TOKEN_ENV}. "
            f"Set {TOKEN_ENV} to a long random value (clients send it as 'Authorization: Bearer ...'), "
            "or bind 127.0.0.1.", fg="red"), err=True)
        sys.exit(1)
    try:
        import uvicorn  # type: ignore
    except ImportError:
        msg = (
            "uvicorn is not installed. "
            "Install it with: pip install uvicorn[standard]"
        )
        if _HAS_RICH:
            render_error(msg)
        else:
            click.echo(click.style(f"Error: {msg}", fg="red"), err=True)
        sys.exit(1)

    if reload:
        click.echo(
            click.style("Dev mode: auto-reload enabled. Workers forced to 1.", fg="yellow")
        )
        workers = 1

    click.echo(f"Starting Delentia OS API on {host}:{port} (workers={workers})")
    click.echo(f"  Listening  →  http://{host}:{port}")
    click.echo(f"  Swagger: http://{host}:{port}/docs")
    click.echo(f"  Health: http://{host}:{port}/health")
    click.echo("  Daemon: reminder polling + gateways active (GET /v1/daemon/status)")

    # Round 36: real uvicorn serving is the only path that enables the
    # background AutonomousScheduler daemon (see api.py's _lifespan) -
    # deliberately not on by default, since FastAPI's TestClient also
    # triggers lifespan events and this codebase's test suite has many
    # tests that spin one up just to hit an unrelated endpoint. Note:
    # with workers>1, each worker process gets its own daemon instance
    # polling the same shared reminders table - fine for this engagement's
    # real single-worker dev/local deployment; multi-worker coordination
    # (avoiding duplicate fires across workers) is a real, honestly
    # undeferred limitation, not solved this round.
    os.environ["DELENTIA_DAEMON_ENABLED"] = "1"

    uvicorn.run(
        "rct_control_plane.api:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


# ─── chat command ─────────────────────────────────────────────────────────


@cli.command("chat")
def chat_command() -> None:
    """Launch the real, interactive Delentia Terminal UI (Round 36)."""
    try:
        from rct_control_plane.tui.chat_app import run_chat
    except ImportError:
        msg = "textual is not installed. Install it with: pip install textual"
        if _HAS_RICH:
            render_error(msg)
        else:
            click.echo(click.style(f"Error: {msg}", fg="red"), err=True)
        sys.exit(1)
    run_chat()


def _print_next_steps(steps: List[str]) -> None:
    """Render concise follow-up guidance after successful CLI workflows."""
    if not steps:
        return

    if _HAS_RICH:
        console = get_console()
        console.print()
        console.print("  [bold]Next steps:[/]")
        for index, step in enumerate(steps, start=1):
            console.print(f"  [dim]{index}.[/]  {step}")
        console.print()
    else:
        click.echo()
        click.echo("Next steps:")
        for index, step in enumerate(steps, start=1):
            click.echo(f"  {index}. {step}")
        click.echo()


def _build_service_snapshot(default_port: int = 8000) -> List[Dict[str, Any]]:
    """Probe the local service surface for dashboard rendering."""
    services = [
        ("gateway-api", default_port),
        ("intent-loop", 8001),
        ("analysearch-intent", 8002),
        ("vector-search", 8003),
        ("crystallizer", 8004),
        ("delta-engine", "—"),
    ]

    snapshot: List[Dict[str, Any]] = []
    for name, port in services:
        is_online = False
        if isinstance(port, int):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                    is_online = True
            except OSError:
                is_online = False
        snapshot.append({"name": name, "port": port, "online": is_online})
    return snapshot


def _fetch_runtime_health(host: str, port: int) -> Optional[Dict[str, Any]]:
    """Fetch detailed health from a running Control Plane server when available."""
    url = f"http://{host}:{port}/health/detailed"
    try:
        with urlopen(url, timeout=0.4) as response:
            if response.status != 200:
                return None
            return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))
    except (OSError, TimeoutError, ValueError, URLError):
        return None


def _normalize_runtime_overall_status(
    raw_status: Optional[str],
    services: List[Dict[str, Any]],
    source: str,
) -> str:
    """Map raw runtime signals into truthful CLI-facing status buckets."""
    normalized = str(raw_status or "").strip().lower()

    if source == "health-endpoint":
        if normalized in {"healthy", "running", "active", "serving"}:
            return "serving"
        if normalized == "degraded":
            return "degraded"
        if normalized in {"offline", "unhealthy", "failed", "error"}:
            return "offline"

    if any(bool(service.get("online", False)) for service in services):
        return "health-unknown"
    return "offline"


def _build_runtime_dashboard_state(host: str, port: int) -> Dict[str, Any]:
    """Build dashboard state from live health data with a port-probe fallback."""
    endpoint = f"http://{host}:{port}"
    health = _fetch_runtime_health(host, port)

    if health is not None:
        port_map = {
            "intent_compiler": port,
            "dsl_parser": 8001,
            "policy_evaluator": 8002,
            "observer": 8003,
            "finance_layer": 8004,
            "feature_flags": "—",
        }
        services = []
        for service in health.get("services", []):
            service_name = str(service.get("name", "—"))
            service_status = str(service.get("status", "unknown"))
            services.append(
                {
                    "name": service_name,
                    "port": port_map.get(service_name, "—"),
                    "online": service_status in {"healthy", "degraded"},
                    "status": (
                        "serving"
                        if service_status == "healthy"
                        else "degraded"
                        if service_status == "degraded"
                        else "offline"
                    ),
                }
            )
        return {
            "services": services,
            "endpoint": endpoint,
            "overall_status": _normalize_runtime_overall_status(
                raw_status=str(health.get("status", "unknown")),
                services=services,
                source="health-endpoint",
            ),
            "source": "health-endpoint",
            "uptime_seconds": float(health.get("uptime_seconds", 0.0)),
            "environment": str(health.get("environment", "development")),
            "version": str(health.get("version", PACKAGE_VERSION)),
        }

    services = _build_service_snapshot(default_port=port)
    return {
        "services": services,
        "endpoint": endpoint,
        "overall_status": _normalize_runtime_overall_status(
            raw_status=None,
            services=services,
            source="port-probe",
        ),
        "source": "port-probe",
        "uptime_seconds": None,
        "environment": None,
        "version": PACKAGE_VERSION,
    }


def _build_launch_preview_state(
    host: str,
    port: int,
    ui_test: bool,
    version: str,
) -> Dict[str, Any]:
    """Build a truthful pre-launch preview state for `delentia start` surfaces."""
    preview_status = "preview" if ui_test else "starting"
    services = [
        {"name": "gateway-api", "port": port, "online": False, "status": preview_status},
        {"name": "intent-loop", "port": 8001, "online": False, "status": preview_status},
        {"name": "analysearch-intent", "port": 8002, "online": False, "status": preview_status},
        {"name": "vector-search", "port": 8003, "online": False, "status": preview_status},
        {"name": "crystallizer", "port": 8004, "online": False, "status": preview_status},
        {"name": "delta-engine", "port": "—", "online": False, "status": preview_status},
    ]
    return {
        "services": services,
        "endpoint": f"http://{host}:{port}",
        "overall_status": "ui-test" if ui_test else "launching",
        "source": "ui-preview" if ui_test else "boot-preview",
        "uptime_seconds": None,
        "environment": "preview",
        "version": version,
    }


def _render_runtime_dashboard_snapshot(host: str, port: int) -> None:
    """Render a post-bind runtime dashboard snapshot after the server starts."""
    if not _HAS_RICH:
        return

    runtime_state = _build_runtime_dashboard_state(host, port)
    get_console().print(
        render_layout_dashboard(
            services=cast(List[Dict[str, Any]], runtime_state["services"]),
            endpoint=str(runtime_state["endpoint"]),
            version=str(runtime_state["version"]),
            overall_status=str(runtime_state["overall_status"]),
            source=str(runtime_state["source"]),
            uptime_seconds=cast(Optional[float], runtime_state["uptime_seconds"]),
            environment=cast(Optional[str], runtime_state["environment"]),
        )
    )


def _schedule_startup_refresh(
    on_started: Callable[[], None],
    delay_seconds: float = 0.2,
) -> None:
    """Run a startup callback off the event loop once the server has bound."""

    def _worker() -> None:
        time.sleep(delay_seconds)
        on_started()

    threading.Thread(
        target=_worker,
        name="rct-startup-refresh",
        daemon=True,
    ).start()


def _run_uvicorn_server(
    uvicorn_module: Any,
    host: str,
    port: int,
    verbose: bool,
    on_started: Optional[Callable[[], None]] = None,
) -> None:
    """Run uvicorn with an optional callback once startup reaches a bound socket."""

    config = uvicorn_module.Config(
        "rct_control_plane.api:app",
        host=host,
        port=port,
        reload=False,
        log_level="debug" if verbose else "info",
        workers=1,
    )

    class _StartupRefreshServer(uvicorn_module.Server):
        def __init__(self, config: Any, startup_callback: Optional[Callable[[], None]]) -> None:
            super().__init__(config)
            self._startup_callback = startup_callback

        async def startup(self, sockets: Optional[List[socket.socket]] = None) -> None:
            await super().startup(sockets=sockets)
            if (
                self._startup_callback is not None
                and not self.should_exit
                and getattr(self, "started", False)
            ):
                _schedule_startup_refresh(self._startup_callback)

    _StartupRefreshServer(config, on_started).run()


@cli.command(name="start")
@click.option(
    "--verbose", "-v", is_flag=True, help="Show raw JITNA packet logs (debug mode)"
)
@click.option(
    "--ui-test",
    "ui_test",
    is_flag=True,
    help="Mock mode — renders UI without starting API server",
)
@click.option(
    "--port", "-p", default=8000, show_default=True, type=int, help="Port to bind on"
)
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind on")
@click.option(
    "--no-animation",
    "no_animation",
    is_flag=True,
    help="Disable CLI letter reveal animation",
)
def start(verbose: bool, ui_test: bool, port: int, host: str, no_animation: bool):
    """Launch RCT OS — Constitutional AI Operating System.

    Renders splash screen, boot sequence, and HexaCore dashboard,
    then starts the Control Plane API server.

    Example:
        delentia start                  # Full launch
        delentia start --ui-test        # Test UI without starting server
        delentia start --verbose        # Debug mode (raw logs)
        delentia start --port 8080      # Custom port
    """
    try:
        ver = get_package_version()
    except Exception:
        ver = PACKAGE_VERSION

    if _HAS_RICH:
        preview_state = _build_launch_preview_state(host=host, port=port, ui_test=ui_test, version=ver)
        print_splash(version=ver, endpoint=f"http://{host}:{port}", mock=ui_test, no_animation=no_animation)
        boot_sequence_animation(mock=ui_test, overall_status=str(preview_state["overall_status"]), no_animation=no_animation)
        get_console().print(
            render_layout_dashboard(
                services=cast(List[Dict[str, Any]], preview_state["services"]),
                endpoint=str(preview_state["endpoint"]),
                version=str(preview_state["version"]),
                overall_status=str(preview_state["overall_status"]),
                source=str(preview_state["source"]),
                uptime_seconds=cast(Optional[float], preview_state["uptime_seconds"]),
                environment=cast(Optional[str], preview_state["environment"]),
            )
        )
        if verbose:
            render_pipeline_flow(current_stage="Output")
    else:
        click.echo(click.style(f"RCT OS v{ver} — Launching...", fg="cyan", bold=True))

    if ui_test:
        if _HAS_RICH:
            render_success("UI test complete — all components rendered successfully")
        else:
            click.echo("UI test complete.")
        _print_next_steps(
            [
                "Run [bold cyan]delentia doctor[/] to verify the local environment"
                if _HAS_RICH
                else "Run delentia doctor to verify the local environment",
                f"Run [bold cyan]delentia start --port {port}[/] for a real launch"
                if _HAS_RICH
                else f"Run delentia start --port {port} for a real launch",
            ]
        )
        return

    # Start the actual API server
    try:
        import uvicorn as _uvicorn
    except ImportError:
        if _HAS_RICH:
            render_error("uvicorn is not installed. Run: pip install uvicorn[standard]")
        else:
            click.echo(
                click.style("Error: uvicorn is not installed.", fg="red"), err=True
            )
        sys.exit(1)

    if _HAS_RICH:
        console = get_console()
        console.print(
            f"  [bright_green]Listening[/]  →  [bold]http://{host}:{port}[/]"
            f"  [dim]|  Swagger: http://{host}:{port}/docs[/]"
        )
        console.print()
    else:
        click.echo(click.style(f"  Listening  →  http://{host}:{port}", fg="green"))

    original_sigint = signal.getsignal(signal.SIGINT)

    def _handle_sigint(signum: int, frame: Optional[object]) -> None:
        del signum, frame
        if _HAS_RICH:
            render_warning("RCT OS shutting down on Ctrl-C")
        else:
            click.echo("RCT OS shutting down on Ctrl-C", err=True)
        raise SystemExit(130)

    signal.signal(signal.SIGINT, _handle_sigint)
    try:
        _run_uvicorn_server(
            _uvicorn,
            host=host,
            port=port,
            verbose=verbose,
            on_started=(
                (lambda: _render_runtime_dashboard_snapshot(host, port))
                if _HAS_RICH
                else None
            ),
        )
    except KeyboardInterrupt:
        if _HAS_RICH:
            render_warning("RCT OS interrupted during shutdown")
        else:
            click.echo("RCT OS interrupted during shutdown", err=True)
        raise SystemExit(130) from None
    finally:
        signal.signal(signal.SIGINT, cast(signal.Handlers, original_sigint))


@cli.group()
def workflow():
    """DAG-workflow-YAML commands (Round 44 item I.1) - run a workflow
    defined in a .yaml file through the real ALGO-20 WorkflowEngine
    (real networkx DAG scheduling), without touching the heavier
    41-algorithm kernel (no torch/FAISS import cost for this command)."""


@workflow.command("run")
@click.argument("yaml_path", type=click.Path(exists=True))
@click.option("--poll-interval", default=0.2, show_default=True, help="Seconds between execution-status polls.")
def workflow_run(yaml_path: str, poll_interval: float) -> None:
    """Run the DAG workflow defined in YAML_PATH."""
    import asyncio

    from rct_control_plane.algo_19_fusion import FusionEngine
    from rct_control_plane.algo_20_workflow_orchestrator import (
        ExecutionMode, IntegrationManager, WorkflowEngine, WorkflowStatus,
    )
    from rct_control_plane.workflow_yaml_loader import WorkflowYamlError, load_workflow_yaml

    try:
        name, tasks, mode = load_workflow_yaml(yaml_path)
    except WorkflowYamlError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        raise SystemExit(1) from exc

    async def _run() -> bool:
        # Real WorkflowEngine + real FusionEngine, built directly rather
        # than through AlgorithmKernel41 - the kernel's own capability
        # registry wires WorkflowEngine the same way (hrm_scheduler=None,
        # real FusionEngine), but importing the full kernel here would
        # pull in torch/FAISS/diffusion/Whisper for algorithms this
        # command never touches, turning a YAML-workflow run into a
        # 20+ second cold start for no reason.
        engine = WorkflowEngine(integration_manager=IntegrationManager(fusion_engine=FusionEngine()))
        workflow_def = await engine.create_workflow(name=name, description=name, tasks=tasks)
        execution = await engine.start_execution(workflow_def.id, mode=ExecutionMode(mode))

        terminal = (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED)
        while execution.status not in terminal:
            await asyncio.sleep(poll_interval)

        click.echo(f"Workflow '{name}' ({execution.execution_id}): {execution.status.value}")
        for task_id, task_exec in execution.task_executions.items():
            output = task_exec.output or {}
            suffix = " [simulated]" if output.get("simulated") else ""
            line = f"  - {task_id}: {task_exec.status.value}{suffix}"
            if task_exec.error:
                line += f"  error={task_exec.error}"
            click.echo(line)

        return execution.status == WorkflowStatus.COMPLETED

    succeeded = asyncio.run(_run())
    if not succeeded:
        raise SystemExit(1)


@cli.command("agent")
@click.argument("goal")
@click.option("--max-iterations", default=5, show_default=True, help="Episode iteration cap.")
@click.option("--max-seconds", default=120.0, show_default=True, help="Episode wall-clock budget in seconds.")
@click.option("--namespace", default=None, help="Persistence/JITNA namespace (defaults to a fresh id per run).")
def agent_command(goal: str, max_iterations: int, max_seconds: float, namespace: Optional[str]) -> None:
    """Run GOAL through the real, governed autonomous agent loop (Round 44
    Phase J.3) - FDIA gate, JITNA signing, RCT-7 decomposition, Delta
    persistence, and Skill Library retrieval/extraction all wired in
    (GovernedAutonomousLoop, items J.1/J.2/I.2). Reuses the same real
    kernel and MCP tool registry mcp_server.py's own delentia_autonomous_loop/
    delentia_delegate tools already share (agent_profile.py's
    delegate_to_profile established this exact reuse pattern first) -
    not a second, independent kernel instance."""
    import asyncio
    import uuid

    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    from rct_control_plane.mcp_server import _kernel, mcp

    ns = namespace or f"cli-agent-{uuid.uuid4().hex[:8]}"

    async def _run() -> dict:
        loop = GovernedAutonomousLoop(
            mcp_server=mcp, persistence=_kernel._persistence, kernel=_kernel,
            max_iterations=max_iterations, max_seconds=max_seconds, namespace=ns,
        )
        return await loop.run(goal)

    result = asyncio.run(_run())

    click.echo(f"namespace: {ns}")
    click.echo(f"stopped_reason: {result['stopped_reason']}")
    click.echo(f"iterations: {result['iterations']}")
    for step in result["steps"]:
        if step.get("tool_name"):
            suffix = ""
            tool_result = step.get("tool_result") or {}
            if isinstance(tool_result, dict) and tool_result.get("fdia_blocked"):
                suffix = "  [FDIA BLOCKED]"
            click.echo(f"  - {step['tool_name']}({step['tool_args']}) -> {tool_result}{suffix}")
    if result.get("final_answer"):
        click.echo(f"\nfinal_answer:\n{result['final_answer']}")

    if result["stopped_reason"] == "fdia_blocked":
        raise SystemExit(1)


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
