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
import signal
import socket
import threading
import time
import textwrap
from urllib.error import URLError
from urllib.request import urlopen
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Callable, cast
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
        build_execution_log_table,
        render_execution_log,
        render_replay_result,
        render_error,
        render_governance_score,
        render_success,
        render_warning,
        render_doctor_report,
        render_layout_dashboard,
        # DX commands — rct start
        print_splash,
        boot_sequence_animation,
        render_pipeline_flow,
    )
    from rich.live import Live
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.traceback import install as install_rich_traceback

    install_rich_traceback(suppress=[click], show_locals=False)
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

from rct_control_plane.intent_compiler import IntentCompiler
from rct_control_plane.dsl_parser import DSLParser
from rct_control_plane.policy_language import PolicyEvaluator
from rct_control_plane.control_plane_state import ControlPlaneState, ControlPlanePhase
from rct_control_plane.observability import ControlPlaneObserver
from rct_control_plane._version import PACKAGE_VERSION, get_package_version

# Preserve builtin list before it gets shadowed by the CLI 'list' command
_list = list

_DEFAULT_ENV_TEMPLATE = textwrap.dedent(
    """\
    # Environment Configuration Example
    # Copy this file to .env and fill in your values.
    # NEVER commit .env to version control.

    # --- API Keys (obtain from your provider) ---
    # OpenRouter key for LLM calls
    RCT_CORE_BRAIN_KEY=<your-openrouter-key>

    # Google Gemini (optional fallback)
    GOOGLE_API_KEY=<your-google-api-key>

    # --- Service URLs ---
    # Production API base URL
    RCT_API_BASE_URL=https://api.rctlabs.co

    # --- Database (local dev only) ---
    # RCTDB connection string for local development
    RCTDB_URL=postgresql://localhost:5432/rctdb_dev

    # --- Observability ---
    # Optional: trace exporter endpoint
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

    # --- Feature Flags ---
    # Set to "1" to enable development/debug mode
    RCT_DEBUG=0
    """
)


def _configure_encoding() -> None:
    """Ensure stdout/stderr can handle Unicode on Windows consoles with legacy encodings.

    Windows terminals using Code Page 874 (Thai), 932 (Japanese), etc. cannot encode
    characters such as the right-arrow (U+2192) or check-mark (U+2713), causing
    UnicodeEncodeError before the server process even starts.  This function
    reconfigures the streams to UTF-8 with ``errors='replace'`` so unrepresentable
    characters are shown as ``?`` instead of crashing the process.

    Safe to call on all platforms; on Linux/macOS it is a no-op because
    the streams are already UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass  # read-only or already configured — ignore


def _package_version(distribution: str) -> Optional[str]:
    """Return an installed distribution version when available."""
    if distribution == "rct-platform":
        return get_package_version()
    try:
        import importlib.metadata as importlib_metadata

        return importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        return None


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
        return

    click.echo("Next steps:")
    for index, step in enumerate(steps, start=1):
        click.echo(f"  {index}. {step}")


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
        (".env", "Run rct init to generate the environment file."),
        (".env.example", "Commit or regenerate the template with rct init --force."),
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
                "hint": f"Run rct start --port {port} if this service should be available.",
            }
        )

    return checks


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
    """Build a truthful pre-launch preview state for `rct start` surfaces."""
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


def _collect_log_entries(
    ctx: "CLIContext", adapter: Optional[str], tail: int
) -> List[Dict[str, Any]]:
    """Collect adapter log entries from observer events."""
    log_entries = []
    events_list = ctx.observer.audit_trail.get_recent_events(max(tail * 5, tail))

    for event in events_list:
        data = event.data if hasattr(event, "data") else {}
        adapter_name = data.get("adapter", data.get("adapter_name"))

        if adapter and adapter_name and adapter.lower() != adapter_name.lower():
            continue

        if adapter_name or data.get("action"):
            log_entries.append(
                {
                    "packet_id": data.get("packet_id", data.get("intent_id", "N/A"))[
                        :16
                    ],
                    "action": data.get(
                        "action",
                        event.event_type.value
                        if hasattr(event, "event_type")
                        else "N/A",
                    ),
                    "status": data.get("status", "ok"),
                    "sha256": data.get("sha256", data.get("hash", ""))[:16],
                    "latency_ms": data.get("latency_ms", "N/A"),
                    "timestamp": event.timestamp.isoformat()[:19]
                    if hasattr(event, "timestamp")
                    else "N/A",
                }
            )

    return log_entries[-tail:]


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


def print_tree(node: Union[Dict[str, Any], List[Any]], indent: int = 0) -> None:
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
    _configure_encoding()


@cli.command(name="version")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
def version_cmd(output: str):
    """Show version and platform information.

    Example:
        rct version
        rct version --output json
    """
    try:
        ver = get_package_version()
    except Exception:
        ver = PACKAGE_VERSION

    info = {
        "version": ver,
        "name": "rct-platform",
        "description": "Constitutional AI Operating System SDK",
        "python": sys.version.split()[0],
        "license": "Apache-2.0",
        "homepage": "https://rctlabs.co",
        "repository": "https://github.com/rctlabs/rct-platform",
    }
    if output == "json":
        click.echo(json.dumps(info, indent=2))
    else:
        click.echo(f"rct-platform  v{info['version']}")
        click.echo(f"Python        {info['python']}")
        click.echo(f"License       {info['license']}")
        click.echo(f"Homepage      {info['homepage']}")


@cli.command(name="serve")
@click.option(
    "--port", "-p", default=8000, show_default=True, type=int, help="Port to bind on."
)
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind on.")
@click.option("--reload", is_flag=True, help="Auto-reload on code changes (dev mode).")
@click.option(
    "--workers",
    default=1,
    show_default=True,
    type=int,
    help="Number of Uvicorn worker processes.",
)
def serve(port: int, host: str, reload: bool, workers: int):
    """Start the Control Plane REST API server.

    Example:
        rct serve --port 8000 --reload
        rct serve --host 0.0.0.0 --port 8080 --workers 2
    """
    try:
        import uvicorn as _uvicorn
    except ImportError:
        click.echo(
            click.style(
                "Error: uvicorn is not installed. Run: pip install uvicorn[standard]",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    click.echo(
        click.style(
            f"  RCT Control Plane API  →  http://{host}:{port}", fg="green", bold=True
        )
    )
    click.echo(f"  Swagger docs   →  http://{host}:{port}/docs")
    click.echo(f"  Health check   →  http://{host}:{port}/health")
    if reload:
        click.echo(click.style("  Dev mode: auto-reload enabled", fg="yellow"))
    click.echo("")

    _uvicorn.run(
        "rct_control_plane.api:app",  # string form required for --reload
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,  # uvicorn forbids reload + workers>1
    )


@cli.command()
@click.argument("natural_language")
@click.option("--user-id", default="cli-user", help="User ID")
@click.option("--user-tier", default="PRO", help="User tier (FREE/PRO/ENTERPRISE)")
@click.option("--organization-id", default=None, help="Organization ID")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table", "tree"]),
    default="json",
    help="Output format",
)
@click.option("--save", "-s", is_flag=True, help="Save intent to storage")
def compile(
    natural_language: str,
    user_id: str,
    user_tier: str,
    organization_id: Optional[str],
    output: str,
    save: bool,
):
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
            organization_id=organization_id,
        )
        compilation_time = (time.time() - start_time) * 1000

        # Extract intent data (CompilationResult is a dataclass, not dict)
        intent_obj = result.intent
        validation = result.validation

        # Create state if save flag is set
        if save:
            intent_id_str = str(intent_obj.id)
            state = ControlPlaneState(
                state_id=intent_id_str, phase=ControlPlanePhase.INTENT_COMPILED
            )
            ctx.save_state(state)
            ctx.save_intent(
                intent_id_str,
                {
                    "intent": intent_obj.to_dict(),
                    "natural_language": natural_language,
                    "user_id": user_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )

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
            "saved": save,
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
                click.echo(
                    click.style("\n⚠ Intent has validation errors", fg="yellow"),
                    err=True,
                )
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
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table", "tree"]),
    default="json",
    help="Output format",
)
@click.option("--save", "-s", is_flag=True, help="Save graph to storage")
def build(
    dsl_text: Optional[str],
    dsl_file: Optional[str],
    intent_id: str,
    output: str,
    save: bool,
):
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
            click.echo(
                click.style(
                    "Error: Either --dsl-text or --dsl-file is required", fg="red"
                ),
                err=True,
            )
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
            ctx.save_graph(
                intent_id,
                {
                    "graph": graph.to_dict(),
                    "dsl_text": dsl_input,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )

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
                    "node_type": node.node_type.value
                    if hasattr(node.node_type, "value")
                    else str(node.node_type),
                    "label": getattr(node, "description", None),
                }
                for node in graph.nodes.values()
            ],
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
@click.option(
    "--use-default-policies", is_flag=True, default=True, help="Use default policies"
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table", "tree"]),
    default="json",
    help="Output format",
)
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
            click.echo(
                click.style(f"Error: Intent {intent_id} not found", fg="red"), err=True
            )
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
        decision = ctx.evaluator.evaluate_intent(intent=intent_obj, graph=graph_obj)
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
            "decision": decision.decision.value
            if hasattr(decision.decision, "value")
            else str(decision.decision),
            "decision_reason": decision.decision_reason,
            "is_approved": decision.is_approved(),
            "requires_approval": decision.requires_approval,
            "governance_score": decision.governance_score,
            "governance_label": decision.governance_label,
            "blocking_priority": decision.blocking_priority,
            "score_components": decision.score_components,
            "violations": decision.violations,
            "warnings": decision.warnings,
            "triggered_rules_count": len(decision.triggered_rules),
            "evaluation_time_ms": f"{eval_time:.2f}",
            "saved": save,
        }

        if _HAS_RICH and output == "table":
            render_governance_score(
                decision.governance_score,
                decision.governance_label,
                decision.score_components,
            )
        format_output(output_data, OutputFormat(output))

        if not decision.is_approved():
            if _HAS_RICH:
                render_warning(f"Policy evaluation: {decision.decision}")
            else:
                click.echo(
                    click.style(
                        f"\n⚠ Policy evaluation: {decision.decision}", fg="yellow"
                    ),
                    err=True,
                )
            sys.exit(1)

    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.argument("intent_id", required=False, default=None)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table", "tree"]),
    default="table",
    help="Output format",
)
@click.option(
    "--live",
    "live_status",
    is_flag=True,
    help="Render the system overview as a live dashboard",
)
@click.option(
    "--interval",
    default=1.0,
    show_default=True,
    type=float,
    help="Refresh interval in seconds for --live",
)
@click.option(
    "--refresh-count",
    default=0,
    show_default=True,
    type=int,
    help="Number of live dashboard refresh cycles to render (0 = run until Ctrl-C)",
)
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Host for live health polling",
)
@click.option(
    "--port",
    default=8000,
    show_default=True,
    type=int,
    help="Port for live health polling",
)
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
    Get current state of an intent, or show system health when called without arguments.

    Examples:
        rct status               # system overview
        rct status abc-123       # specific intent
    """
    try:
        ctx = get_context()

        # ── No intent_id → show system overview ──────────────────────────
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
                    raise SystemExit(130)
                _print_next_steps(
                    [
                        "Run [bold cyan]rct doctor[/] for dependency and port diagnostics",
                        f"Run [bold cyan]rct start --host {host} --port {port}[/] to bring the API online",
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

        # ── intent_id given → original behaviour ─────────────────────────
        state = ctx.get_state(intent_id)
        if not state:
            click.echo(
                click.style(f"Error: State for intent {intent_id} not found", fg="red"),
                err=True,
            )
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
            "requires_approval": getattr(state, "requires_approval", False),
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
@click.option(
    "--pager", is_flag=True, help="Open table output in a Rich pager when available"
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table", "tree"]),
    default="table",
    help="Output format",
)
def list(limit: int, offset: int, pager: bool, output: str):
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
        paginated = all_intents[offset : offset + limit]

        # Format output
        if output == "table" and _HAS_RICH:
            intents_for_render = []
            for intent_id, intent_data in paginated:
                state = ctx.get_state(intent_id)
                phase = state.phase.value if state else "UNKNOWN"
                intents_for_render.append(
                    {
                        "intent_id": intent_id,
                        "intent_type": intent_data["intent"]["intent_type"],
                        "scope": intent_data["intent"].get("scope", "N/A"),
                        "priority": intent_data["intent"]["priority"],
                        "is_valid": True,
                        "created_at": intent_data["created_at"][:19],
                    }
                )
            console = get_console()
            summary = (
                f"\nTotal: {len(all_intents)} intents "
                f"(showing {offset + 1}-{offset + len(paginated)})"
            )
            if pager:
                with console.pager(styles=True):
                    render_intent_table(intents_for_render)
                    console.print(summary)
            else:
                render_intent_table(intents_for_render)
                click.echo(summary)
        elif output == "table":
            headers = ["Intent ID", "Type", "Priority", "Phase", "Created At"]
            rows = []
            for intent_id, intent_data in paginated:
                state = ctx.get_state(intent_id)
                phase = state.phase.value if state else "UNKNOWN"
                rows.append(
                    [
                        intent_id[:12] + "...",
                        intent_data["intent"]["intent_type"],
                        intent_data["intent"]["priority"],
                        phase,
                        intent_data["created_at"][:19],
                    ]
                )
            print_table(headers, rows)
            click.echo(
                f"\nTotal: {len(all_intents)} intents (showing {offset + 1}-{offset + len(paginated)})"
            )
        else:
            output_data = {
                "intents": [
                    {
                        "intent_id": intent_id,
                        "intent_type": intent_data["intent"]["intent_type"],
                        "priority": intent_data["intent"]["priority"],
                        "phase": (state := ctx.get_state(intent_id))
                        and state.phase.value
                        or "UNKNOWN",
                        "created_at": intent_data["created_at"],
                    }
                    for intent_id, intent_data in paginated
                ],
                "total": len(all_intents),
                "offset": offset,
                "limit": limit,
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
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table", "tree"]),
    default="table",
    help="Output format",
)
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
            click.echo(
                click.style(
                    f"No audit trail found for intent {intent_id}", fg="yellow"
                ),
                err=True,
            )
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
                        "data": event.data,
                    }
                    for event in events
                ],
                "event_count": len(events),
                "integrity_verified": is_valid,
            }
            render_audit_tree(audit_data)
        elif output == "table":
            headers = ["Timestamp", "Event Type", "Phase", "Status"]
            rows = [
                [
                    event.timestamp.isoformat()[:19],
                    event.event_type.value,
                    event.data.get("phase", "N/A"),
                    "✓" if event.data.get("success", True) else "✗",
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
                        "data": event.data,
                    }
                    for event in events
                ],
                "event_count": len(events),
                "integrity_verified": is_valid,
            }
            format_output(output_data, OutputFormat(output))

    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table", "tree"]),
    default="json",
    help="Output format",
)
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
            click.confirm(
                "Are you sure you want to reset ALL state? This cannot be undone.",
                abort=True,
            )

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
        rct adapter status
        rct adapter list
    """
    pass


@adapter.command("status")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
def adapter_status(output: str):
    """Show health status of all registered OS Adapters."""
    try:
        from core.adapters import ADAPTER_REGISTRY

        adapters_info = []
        for name, adapter_cls in ADAPTER_REGISTRY.items():
            try:
                instance = adapter_cls.__new__(adapter_cls)
                caps = (
                    instance.capabilities()
                    if hasattr(instance, "capabilities")
                    else None
                )
                adapters_info.append(
                    {
                        "name": name,
                        "version": getattr(caps, "adapter_version", "unknown")
                        if caps
                        else "unknown",
                        "security_level": getattr(caps, "security_level", "unknown")
                        if caps
                        else "unknown",
                        "healthy": True,
                        "supported_actions": getattr(caps, "supported_actions", [])
                        if caps
                        else [],
                        "avg_latency_ms": getattr(caps, "avg_latency_ms", 0.0)
                        if caps
                        else 0.0,
                    }
                )
            except Exception:
                adapters_info.append(
                    {
                        "name": name,
                        "version": "unknown",
                        "security_level": "unknown",
                        "healthy": False,
                        "supported_actions": [],
                        "avg_latency_ms": 0.0,
                    }
                )

        if output == "json":
            print_json({"adapters": adapters_info, "total": len(adapters_info)})
        elif _HAS_RICH:
            render_adapter_status(adapters_info)
        else:
            headers = ["Adapter", "Version", "Security", "Healthy"]
            rows = [
                [
                    a["name"],
                    a["version"],
                    a["security_level"],
                    "Yes" if a["healthy"] else "No",
                ]
                for a in adapters_info
            ]
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
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
def adapter_list(output: str):
    """List all registered adapters and their capabilities."""
    try:
        from core.adapters import ADAPTER_REGISTRY

        if output == "json":
            data = {
                "adapters": [
                    {"name": n, "class": c.__name__}
                    for n, c in ADAPTER_REGISTRY.items()
                ]
            }
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
@click.option(
    "--last", "-n", default=10, type=int, help="Number of recent violations to show"
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
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

        for event_id, event in list(ctx.observer._events.items())[-last * 5 :]:
            data = event.data if hasattr(event, "data") else {}
            if data.get("violation") or data.get("blocked"):
                violations.append(
                    {
                        "timestamp": event.timestamp.isoformat()[:19]
                        if hasattr(event, "timestamp")
                        else "N/A",
                        "rule": data.get("rule", data.get("pattern", "unknown")),
                        "severity": data.get("severity", "HIGH"),
                        "description": data.get(
                            "message", data.get("reason", "Codex violation detected")
                        ),
                        "intent_id": data.get("intent_id", "N/A"),
                    }
                )

        # Also add simulated codex info if no real violations found
        if not violations:
            violations = []  # Empty — no violations is good

        violations = violations[-last:]

        if output == "json":
            print_json(
                {
                    "violations": violations,
                    "total": len(violations),
                    "codex_patterns_active": len(THE_9_CODEX_FORBIDDEN_PATTERNS),
                }
            )
        elif _HAS_RICH:
            render_governance_violations(violations)
        else:
            if not violations:
                click.echo("No governance violations found.")
            else:
                headers = ["Time", "Rule", "Severity", "Description"]
                rows = [
                    [v["timestamp"], v["rule"], v["severity"], v["description"][:50]]
                    for v in violations
                ]
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
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
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
                    [
                        str(d.get("tick", "?")),
                        d.get("intent_id", "N/A")[:12],
                        d.get("action", "N/A"),
                        d.get("outcome", "N/A"),
                    ]
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
@click.option(
    "--hash",
    "-h",
    "packet_hash",
    required=True,
    help="SHA-256 hash of JITNAPacket to replay",
)
@click.option(
    "--verify/--no-verify", default=True, help="Verify deterministic replay match"
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
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
@click.option(
    "--follow", "follow_logs", is_flag=True, help="Refresh the log view continuously"
)
@click.option(
    "--interval",
    default=1.0,
    show_default=True,
    type=float,
    help="Refresh interval in seconds for --follow",
)
@click.option(
    "--refresh-count",
    default=0,
    show_default=True,
    type=int,
    help="Number of refresh cycles to render when using --follow (0 = run until Ctrl-C)",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
def logs(
    adapter: Optional[str],
    tail: int,
    follow_logs: bool,
    interval: float,
    refresh_count: int,
    output: str,
):
    """
    View adapter execution logs.

    Example:
        rct logs --adapter openclaw --tail 50
    """
    try:
        ctx = get_context()

        if follow_logs and output == "json":
            click.echo("--follow is only supported with table output.", err=True)
            sys.exit(1)

        if follow_logs and _HAS_RICH:
            live_cycles = refresh_count if refresh_count > 0 else None
            try:
                with Live(
                    console=get_console(),
                    refresh_per_second=max(1, int(1 / interval)) if interval > 0 else 4,
                ) as live:
                    rendered_cycles = 0
                    while True:
                        live.update(
                            build_execution_log_table(
                                _collect_log_entries(ctx, adapter, tail),
                                title="Execution Log (follow)",
                            )
                        )
                        rendered_cycles += 1
                        if live_cycles is not None and rendered_cycles >= live_cycles:
                            break
                        time.sleep(max(interval, 0.05))
            except KeyboardInterrupt:
                if _HAS_RICH:
                    render_warning("Log follow stopped by Ctrl-C")
                else:
                    click.echo("Log follow stopped by Ctrl-C", err=True)
                raise SystemExit(130)
            _print_next_steps(
                [
                    "Run [bold cyan]rct status --live[/] to correlate system health with adapter activity",
                    "Run [bold cyan]rct doctor[/] if logs remain empty while services should be active",
                ]
            )
            return

        log_entries = _collect_log_entries(ctx, adapter, tail)

        if output == "json":
            print_json(
                {
                    "logs": log_entries,
                    "total": len(log_entries),
                    "filter_adapter": adapter,
                }
            )
        elif _HAS_RICH:
            render_execution_log(log_entries)
        else:
            if not log_entries:
                click.echo("No log entries found.")
            else:
                headers = ["Packet", "Action", "Status", "Latency", "Time"]
                rows = [
                    [
                        entry["packet_id"],
                        entry["action"],
                        entry["status"],
                        str(entry["latency_ms"]),
                        entry["timestamp"],
                    ]
                    for entry in log_entries
                ]
                print_table(headers, rows)
        if follow_logs and not _HAS_RICH:
            click.echo(
                "Follow mode requires Rich support; rendered a single snapshot instead.",
                err=True,
            )
    except Exception as e:
        if _HAS_RICH:
            render_error(str(e))
        else:
            click.echo(click.style(f"Error: {str(e)}", fg="red"), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# rct start — P0 DX: Constitutional Launch Dashboard
# ---------------------------------------------------------------------------


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
def start(verbose: bool, ui_test: bool, port: int, host: str):
    """Launch RCT OS — Constitutional AI Operating System.

    Renders splash screen, boot sequence, and HexaCore dashboard,
    then starts the Control Plane API server.

    Example:
        rct start                  # Full launch
        rct start --ui-test        # Test UI without starting server
        rct start --verbose        # Debug mode (raw logs)
        rct start --port 8080      # Custom port
    """
    try:
        ver = get_package_version()
    except Exception:
        ver = PACKAGE_VERSION

    if _HAS_RICH:
        preview_state = _build_launch_preview_state(host=host, port=port, ui_test=ui_test, version=ver)
        print_splash(version=ver, endpoint=f"http://{host}:{port}", mock=ui_test)
        boot_sequence_animation(mock=ui_test, overall_status=str(preview_state["overall_status"]))
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
                "Run [bold cyan]rct doctor[/] to verify the local environment"
                if _HAS_RICH
                else "Run rct doctor to verify the local environment",
                f"Run [bold cyan]rct start --port {port}[/] for a real launch"
                if _HAS_RICH
                else f"Run rct start --port {port} for a real launch",
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
        raise SystemExit(130)
    finally:
        signal.signal(signal.SIGINT, cast(signal.Handlers, original_sigint))


# ---------------------------------------------------------------------------
# rct init — P1: Environment Initializer
# ---------------------------------------------------------------------------


@cli.command(name="init")
@click.option("--force", is_flag=True, help="Overwrite existing .env file")
def init(force: bool):
    """Initialize environment — create .env from .env.example template.

    Example:
        rct init
        rct init --force   # Overwrite existing .env
    """
    env_path = Path(".env")
    example_path = Path(".env.example")
    template_source = "project template"

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

    if example_path.exists():
        import shutil

        shutil.copy(str(example_path), str(env_path))
    else:
        env_path.write_text(_DEFAULT_ENV_TEMPLATE, encoding="utf-8")
        template_source = "built-in fallback template"

    if _HAS_RICH:
        console = get_console()
        render_success(f".env created from {template_source}")
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
            "  [dim]2.[/]  Run [bold cyan]rct doctor[/] to verify the environment"
        )
        console.print("  [dim]3.[/]  Run [bold cyan]rct start[/] to launch the system")
        console.print()
    else:
        click.echo(
            f".env created from {template_source}. Fill in your API keys, then run: rct doctor, then rct start"
        )


# ---------------------------------------------------------------------------
# rct doctor — P3: Environment & Connectivity Diagnostics
# ---------------------------------------------------------------------------


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
            "Run [bold cyan]rct init[/] to create .env"
            if _HAS_RICH
            else "Run rct init to create .env"
        )
    if any(check["category"] == "connectivity" and not check["ok"] for check in checks):
        next_steps.append(
            "Run [bold cyan]rct start[/] to bring the local API online"
            if _HAS_RICH
            else "Run rct start to bring the local API online"
        )
    if not next_steps:
        next_steps.append(
            "Run [bold cyan]rct benchmark --suite fdia[/] to validate constitutional behavior"
            if _HAS_RICH
            else "Run rct benchmark --suite fdia to validate constitutional behavior"
        )
    _print_next_steps(next_steps)


# ---------------------------------------------------------------------------
# rct benchmark — P1: Constitutional Benchmark Runner
# ---------------------------------------------------------------------------


@cli.command(name="benchmark")
@click.option(
    "--suite",
    default="fdia",
    show_default=True,
    type=click.Choice(["fdia", "halueval", "truthfulqa", "all"]),
    help="Benchmark suite to run",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def benchmark_cmd(suite: str, output: str, verbose: bool):
    """Run RCT constitutional benchmark suites.

    Example:
        rct benchmark --suite fdia
        rct benchmark --suite all --output json
        rct benchmark --suite truthfulqa --verbose
    """
    import subprocess

    # Locate benchmark directory relative to installed package root
    try:
        import rct_control_plane as _rcp

        pkg_root = Path(_rcp.__file__).parent.parent
    except Exception:
        pkg_root = Path(".")

    suite_map: Dict[str, List[str]] = {
        "fdia": ["benchmark/fdia_benchmark.py"],
        "halueval": ["benchmark/industry_standard/run_halueval.py"],
        "truthfulqa": ["benchmark/industry_standard/run_truthfulqa.py"],
        "all": [
            "benchmark/fdia_benchmark.py",
            "benchmark/industry_standard/run_halueval.py",
            "benchmark/industry_standard/run_truthfulqa.py",
        ],
    }

    scripts = suite_map.get(suite, [])

    if not scripts:
        if _HAS_RICH:
            render_warning(f"No benchmark scripts found for suite: {suite}")
        else:
            click.echo(f"No scripts for suite: {suite}")
        return

    if _HAS_RICH:
        console = get_console()
        console.print(
            f"\n  [bold]Running benchmark suite:[/] [bright_cyan]{suite}[/]\n"
        )

    results: List[Dict[str, Any]] = []

    def _run_script(script_rel: str) -> Dict[str, Any]:
        script_path = pkg_root / script_rel
        if not script_path.exists():
            return {
                "script": script_rel,
                "ok": False,
                "returncode": None,
                "stdout": "",
                "stderr": "Script not found",
                "duration_ms": 0.0,
            }

        args = [sys.executable, str(script_path)]
        if output == "json":
            args.append("--json")
        if verbose:
            args.append("--verbose")

        started = time.perf_counter()
        proc = subprocess.run(
            args,
            text=True,
            cwd=str(pkg_root),
            capture_output=True,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        return {
            "script": script_rel,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": duration_ms,
        }

    if _HAS_RICH and output == "table":
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=get_console(),
        ) as progress:
            for script_rel in scripts:
                task_id = progress.add_task(f"Running {Path(script_rel).name}", total=1)
                try:
                    result = _run_script(script_rel)
                except Exception as exc:
                    result = {
                        "script": script_rel,
                        "ok": False,
                        "returncode": None,
                        "stdout": "",
                        "stderr": str(exc),
                        "duration_ms": 0.0,
                    }
                results.append(result)
                progress.update(task_id, completed=1)
    else:
        for script_rel in scripts:
            try:
                results.append(_run_script(script_rel))
            except Exception as exc:
                results.append(
                    {
                        "script": script_rel,
                        "ok": False,
                        "returncode": None,
                        "stdout": "",
                        "stderr": str(exc),
                        "duration_ms": 0.0,
                    }
                )

    if verbose:
        for result in results:
            if result["stdout"]:
                click.echo(result["stdout"])
            if result["stderr"]:
                click.echo(result["stderr"], err=True)

    passed = sum(1 for result in results if result["ok"])
    total = len(results)

    if output == "json":
        print_json(
            {
                "suite": suite,
                "passed": passed,
                "total": total,
                "results": results,
            }
        )
        return

    if _HAS_RICH:
        if passed == total:
            render_success(f"All benchmarks passed: {passed}/{total}")
        else:
            render_warning(f"Benchmarks: {passed}/{total} passed")
    else:
        click.echo(f"Benchmarks: {passed}/{total} passed")

    _print_next_steps(
        [
            "Run [bold cyan]rct doctor[/] for a full environment report"
            if _HAS_RICH
            else "Run rct doctor for a full environment report",
            "Review benchmark JSON with [bold cyan]rct benchmark --suite all --output json[/]"
            if _HAS_RICH
            else "Review benchmark JSON with rct benchmark --suite all --output json",
        ]
    )


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
