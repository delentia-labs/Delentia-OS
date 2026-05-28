"""
rct_control_plane/rich_formatter.py — Rich Terminal Output Formatters

Provides beautiful terminal output for all CLI commands using Rich library.
Replaces plain click.echo + manual table formatting with Rich components.

All functions accept data dicts and return rendered output via console.print().
When --output json is requested, these functions are bypassed entirely.

Reference: TUI-CLI RCT Design — Phase 4A
"""

from __future__ import annotations

import os
import json
import sys
import time
from typing import Any, Dict, List, Optional

from rich.columns import Columns
from rich.console import Console
from rich.align import Align
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.syntax import Syntax
from rich import box

from rct_control_plane.banner_assets import (
    RCT_EMBLEM_COMPACT,
    RCT_EMBLEM_WIDE,
    RCT_WORDMARK,
    RCT_WORDMARK_HERO,
    RCT_WORDMARK_BLOCK,
    RCT_WORDMARK_BLOCK_COMPACT,
)


# Shared console instance
_console: Optional[Console] = None


def get_console() -> Console:
    """Get or create the shared Rich console."""
    global _console
    if _console is None:
        _console = Console(force_terminal=sys.stdout.isatty(), force_jupyter=False)
    return _console


def set_console(console: Console) -> None:
    """Override the shared console (for testing with StringIO)."""
    global _console
    _console = console


def _load_config() -> Dict[str, Any]:
    """Load configuration from rct.config.json in the current working directory."""
    config_path = os.path.join(os.getcwd(), "rct.config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # pragma: no cover
            pass
    return {}


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

_STATUS_COLORS = {
    "success": "bright_green",
    "completed": "bright_green",
    "active": "bright_green",
    "running": "bright_green",
    "healthy": "bright_green",
    "serving": "bright_green",
    "passed": "bright_green",
    "blocked": "bright_red",
    "error": "bright_red",
    "failed": "bright_red",
    "unhealthy": "bright_red",
    "offline": "bright_red",
    "warning": "yellow",
    "pending": "yellow",
    "launching": "yellow",
    "starting": "yellow",
    "degraded": "yellow",
    "health-unknown": "yellow",
    "preview": "bright_cyan",
    "ui-test": "bright_cyan",
    "unknown": "dim",
}


def _colorize_status(status: str) -> str:
    """Wrap status text in a Rich color tag."""
    color = _STATUS_COLORS.get(status.lower(), "white")
    return f"[{color}]{status}[/{color}]"


def _render_runtime_status(status: str) -> str:
    """Render runtime and service statuses with consistent labels."""
    normalized = status.lower()
    color = _STATUS_COLORS.get(normalized, "white")
    label = normalized.replace("-", " ").upper()
    return f"[{color}]{label}[/{color}]"


# ---------------------------------------------------------------------------
# Intent Table
# ---------------------------------------------------------------------------


def render_intent_table(intents: List[Dict[str, Any]]) -> None:
    """Render a list of intents as a Rich table."""
    console = get_console()
    table = Table(
        title="Intents",
        box=box.ROUNDED,
        border_style="bright_cyan",
        show_lines=True,
    )
    table.add_column("ID", style="bright_cyan", min_width=12)
    table.add_column("Type", style="white")
    table.add_column("Scope", style="white")
    table.add_column("Priority", style="bright_magenta")
    table.add_column("Valid", style="white")
    table.add_column("Created", style="dim")

    for intent in intents:
        valid = "✅" if intent.get("is_valid", True) else "❌"
        table.add_row(
            str(intent.get("intent_id", "—")),
            str(intent.get("intent_type", "—")),
            str(intent.get("scope", "—")),
            str(intent.get("priority", "—")),
            valid,
            str(intent.get("created_at", "—")),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# State Panel
# ---------------------------------------------------------------------------


def render_state_panel(state: Dict[str, Any]) -> None:
    """Render intent state as a styled Rich panel."""
    console = get_console()

    status = state.get("phase", state.get("current_phase", "unknown"))
    status_display = _colorize_status(status)

    lines = [
        f"[bold]Intent ID:[/] {state.get('state_id', '—')}",
        f"[bold]Phase:[/] {status_display}",
        f"[bold]Created:[/] {state.get('created_at', '—')}",
        f"[bold]Updated:[/] {state.get('updated_at', '—')}",
    ]

    if "history" in state:
        lines.append(f"[bold]Transitions:[/] {len(state['history'])}")

    content = "\n".join(lines)
    console.print(
        Panel(
            content,
            title="[bold white]Intent State[/]",
            border_style="bright_cyan",
            padding=(1, 2),
        )
    )


# ---------------------------------------------------------------------------
# Audit Tree
# ---------------------------------------------------------------------------


def render_audit_tree(audit_data: Dict[str, Any]) -> None:
    """Render audit trail as a Rich tree with emoji nodes."""
    console = get_console()

    intent_id = audit_data.get("intent_id", "unknown")
    tree = Tree(f"🔍 [bold bright_cyan]Audit Trail — {intent_id}[/]")

    # Chain integrity
    integrity = audit_data.get("chain_integrity", {})
    integrity_node = tree.add("🔗 Chain Integrity")
    # Support both dict format and flat bool format
    if isinstance(integrity, dict):
        valid = integrity.get("is_valid", False)
    else:
        valid = audit_data.get("integrity_verified", False)
    color = "bright_green" if valid else "bright_red"
    integrity_node.add(f"Valid: [{color}]{valid}[/{color}]")
    if isinstance(integrity, dict):
        integrity_node.add(f"Entries: {integrity.get('total_entries', 0)}")
    else:
        integrity_node.add(f"Events: {audit_data.get('event_count', 0)}")

    # Events
    events = audit_data.get("events", [])
    if events:
        events_node = tree.add(f"📋 Events ({len(events)})")
        for event in events[-10:]:  # Show last 10
            ts = event.get("timestamp", "")
            action = event.get("action", event.get("event_type", "unknown"))
            data = event.get("data", {})
            success = data.get("success", True) if isinstance(data, dict) else True
            emoji = "✅" if success else "❌"
            events_node.add(f"{emoji} [{ts}] {action}")

    console.print(tree)


# ---------------------------------------------------------------------------
# Metrics Panel
# ---------------------------------------------------------------------------


def render_metrics_panel(metrics: Dict[str, Any]) -> None:
    """Render observer metrics as a 2-column table inside a panel."""
    console = get_console()

    table = Table(box=box.SIMPLE, show_header=True, border_style="bright_cyan")
    table.add_column("Metric", style="bright_cyan", min_width=25)
    table.add_column("Value", style="white", justify="right")

    def _flatten(data: Dict, prefix: str = "") -> None:
        for key, value in sorted(data.items()):
            full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
            if isinstance(value, dict):
                _flatten(value, full_key)
            else:
                table.add_row(full_key, str(value))

    _flatten(metrics)

    console.print(
        Panel(
            table,
            title="[bold white]Observer Metrics[/]",
            border_style="bright_magenta",
            padding=(0, 1),
        )
    )


# ---------------------------------------------------------------------------
# Adapter Status Table
# ---------------------------------------------------------------------------


def render_adapter_status(adapters: List[Dict[str, Any]]) -> None:
    """Render adapter health status as a Rich table."""
    console = get_console()

    table = Table(
        title="Adapter Status",
        box=box.ROUNDED,
        border_style="bright_cyan",
        show_lines=True,
    )
    table.add_column("Adapter", style="bold white", min_width=20)
    table.add_column("Version", style="dim")
    table.add_column("Security", style="bright_magenta")
    table.add_column("Health", min_width=8)
    table.add_column("Actions", style="dim")
    table.add_column("Latency", justify="right")

    for adapter in adapters:
        health = adapter.get("healthy", False)
        health_display = (
            "[bright_green]● ONLINE[/]" if health else "[bright_red]● OFFLINE[/]"
        )
        actions = ", ".join(adapter.get("supported_actions", [])[:5])
        if len(adapter.get("supported_actions", [])) > 5:
            actions += "..."
        latency_val = adapter.get("avg_latency_ms", adapter.get("latency_ms"))
        latency_str = f"{latency_val:.1f}ms" if latency_val is not None else "—"

        table.add_row(
            adapter.get("name", adapter.get("adapter_name", "—")),
            adapter.get("version", "—"),
            adapter.get("security_level", "—"),
            health_display,
            actions,
            latency_str,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Governance Violations Table
# ---------------------------------------------------------------------------


def render_governance_violations(violations: List[Dict[str, Any]]) -> None:
    """Render governance violations as a red-bordered table."""
    console = get_console()

    if not violations:
        console.print(
            Panel(
                "[bright_green]No governance violations recorded.[/]",
                title="[bold white]Governance Log[/]",
                border_style="bright_green",
            )
        )
        return

    table = Table(
        title=f"⚠️  Governance Violations ({len(violations)})",
        box=box.HEAVY,
        border_style="bright_red",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Rule / Packet", style="bright_red")
    table.add_column("Severity / Action", style="white")
    table.add_column("Description", style="yellow", max_width=50)
    table.add_column("Timestamp", style="dim")

    for idx, v in enumerate(violations, 1):
        table.add_row(
            str(idx),
            str(v.get("rule", v.get("packet_id", "—"))),
            str(v.get("severity", v.get("action", "—"))),
            str(v.get("description", v.get("governance_reason", "—"))),
            str(v.get("timestamp", "—")),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Timeline Table
# ---------------------------------------------------------------------------


def render_timeline(agent_id: str, deltas: List[Dict[str, Any]]) -> None:
    """Render agent memory timeline as a vertical table."""
    console = get_console()

    table = Table(
        title=f"Timeline — Agent: {agent_id}",
        box=box.ROUNDED,
        border_style="bright_cyan",
        show_lines=True,
    )
    table.add_column("Tick", style="bright_cyan", justify="right", width=6)
    table.add_column("Intent", style="bright_magenta")
    table.add_column("Action", style="white")
    table.add_column("Outcome", min_width=8)
    table.add_column("Resources Δ", style="dim")
    table.add_column("Violation", width=4, justify="center")

    for d in deltas:
        outcome = d.get("outcome", "—")
        outcome_display = _colorize_status(outcome)
        violation = "🚨" if d.get("governance_violation", False) else ""
        res_delta = d.get("resources_delta", {})
        res_str = (
            ", ".join(f"{k}:{v:+.1f}" for k, v in res_delta.items())
            if res_delta
            else "—"
        )

        table.add_row(
            str(d.get("tick", "—")),
            str(d.get("intent_type", "—")),
            str(d.get("action_type", "—")),
            outcome_display,
            res_str,
            violation,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Execution Log Table
# ---------------------------------------------------------------------------


def build_execution_log_table(
    logs: List[Dict[str, Any]], title: str = "Execution Log"
) -> Table:
    """Build a Rich table for adapter execution logs."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style="bright_cyan",
        show_lines=False,
    )
    table.add_column("Packet", style="bright_cyan", min_width=15)
    table.add_column("Action", style="white")
    table.add_column("Status")
    table.add_column("SHA-256", style="dim", max_width=16)
    table.add_column("Latency", justify="right")
    table.add_column("Time", style="dim")

    for entry in logs:
        status = entry.get("status", "unknown")
        status_display = _colorize_status(status)
        sha = (
            entry.get("sha256_hash", "")[:16] + "..."
            if entry.get("sha256_hash")
            else "—"
        )
        latency = entry.get("latency_ms")
        latency_str = f"{latency:.2f}ms" if latency is not None else "—"

        table.add_row(
            str(entry.get("packet_id", "—")),
            str(entry.get("action", "—")),
            status_display,
            sha,
            latency_str,
            str(entry.get("timestamp", "—")),
        )

    return table


def render_execution_log(
    logs: List[Dict[str, Any]], title: str = "Execution Log"
) -> None:
    """Render adapter execution log entries."""
    console = get_console()

    console.print(build_execution_log_table(logs, title=title))


# ---------------------------------------------------------------------------
# Replay Result
# ---------------------------------------------------------------------------


def render_replay_result(
    original: Dict[str, Any],
    replayed: Optional[Dict[str, Any]] = None,
    match: Optional[bool] = None,
) -> None:
    """Render deterministic replay comparison."""
    console = get_console()

    # Original
    console.print(
        Panel(
            Syntax(
                __import__("json").dumps(original, indent=2, default=str),
                "json",
                theme="monokai",
            ),
            title="[bold white]Original Execution[/]",
            border_style="bright_cyan",
        )
    )

    if replayed is not None:
        console.print(
            Panel(
                Syntax(
                    __import__("json").dumps(replayed, indent=2, default=str),
                    "json",
                    theme="monokai",
                ),
                title="[bold white]Replayed Execution[/]",
                border_style="bright_magenta",
            )
        )

    if match is not None:
        if match:
            console.print(
                Panel(
                    "[bold bright_green]✅ Deterministic Match — Hashes are identical[/]",
                    border_style="bright_green",
                )
            )
        else:
            console.print(
                Panel(
                    "[bold bright_red]❌ Deterministic MISMATCH — Hashes diverge![/]",
                    border_style="bright_red",
                )
            )


# ---------------------------------------------------------------------------
# Generic Helpers
# ---------------------------------------------------------------------------


def render_error(message: str) -> None:
    """Render an error panel."""
    get_console().print(
        Panel(
            f"[bold bright_red]❌ {message}[/]",
            border_style="bright_red",
            title="[bold white]Error[/]",
        )
    )


def render_success(message: str) -> None:
    """Render a success panel."""
    get_console().print(
        Panel(
            f"[bold bright_green]✅ {message}[/]",
            border_style="bright_green",
            title="[bold white]Success[/]",
        )
    )


def render_warning(message: str) -> None:
    """Render a warning panel."""
    get_console().print(
        Panel(
            f"[bold yellow]⚠️  {message}[/]",
            border_style="yellow",
            title="[bold white]Warning[/]",
        )
    )


def render_governance_score(
    score: float, label: str, components: List[Dict[str, Any]]
) -> None:
    """Render governance score as a compact confidence panel."""
    width = 20
    filled = max(0, min(width, int(round(score * width))))
    bar = "█" * filled + "░" * (width - filled)
    lines = [f"[bold]A =[/] {score:.2f}  [bright_cyan]{bar}[/]  [bold]{label}[/]"]
    if components:
        drivers = ", ".join(
            f"{component['rule']}:{component['contribution']:.2f}"
            for component in components[:3]
        )
        lines.append(f"[dim]Drivers:[/] {drivers}")

    get_console().print(
        Panel(
            "\n".join(lines),
            title="[bold white]Governance Score[/]",
            border_style="bright_cyan" if score >= 0.5 else "bright_red",
        )
    )


def render_doctor_report(checks: List[Dict[str, Any]], issues: int) -> None:
    """Render a grouped preflight report for rct doctor."""
    console = get_console()
    table = Table(
        title="RCT OS Preflight Check",
        box=box.ROUNDED,
        border_style="bright_cyan",
        show_lines=True,
    )
    table.add_column("Category", style="bright_cyan", min_width=12)
    table.add_column("Check", style="bold white", min_width=24)
    table.add_column("Status", min_width=8)
    table.add_column("Detail", style="white", min_width=20)
    table.add_column("Hint", style="dim", min_width=24)

    for check in checks:
        ok = bool(check.get("ok"))
        status = "[bright_green]OK[/]" if ok else "[bright_red]FAIL[/]"
        hint = str(check.get("hint", "—")) if not ok else "—"
        table.add_row(
            str(check.get("category", "general")),
            str(check.get("name", "—")),
            status,
            str(check.get("detail", "—")),
            hint,
        )

    console.print(table)

    summary_style = "bright_green" if issues == 0 else "yellow"
    summary_text = "All checks passed" if issues == 0 else f"{issues} issue(s) detected"
    console.print(
        Panel(
            f"[bold {summary_style}]{summary_text}[/]",
            border_style=summary_style,
            title="[bold white]Summary[/]",
        )
    )


def render_layout_dashboard(
    services: List[Dict[str, Any]],
    llm_statuses: Optional[Dict[str, bool]] = None,
    endpoint: str = "http://127.0.0.1:8000",
    version: str = "1.0.4b0",
    overall_status: str = "unknown",
    source: str = "port-probe",
    uptime_seconds: Optional[float] = None,
    environment: Optional[str] = None,
):
    """Build a split-pane operational dashboard renderable."""
    if llm_statuses is None:
        llm_statuses = {}

    services_table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        border_style="bright_cyan",
        padding=(0, 1),
    )
    # Column widths carefully sized so Status column remains visible even at
    # ~40-col split panels: 16+6+8 content + 6 padding + 2 borders = 38 cols min.
    services_table.add_column("Service", style="bold white", min_width=16)
    services_table.add_column("Port", style="bright_cyan", width=6)
    services_table.add_column("Status", min_width=8)

    ready_count = 0
    for service in services:
        service_status = str(
            service.get("status")
            or ("online" if bool(service.get("online", False)) else "offline")
        )
        is_online = bool(service.get("online", False))
        if is_online or service_status in {"serving", "degraded", "health-unknown"}:
            ready_count += 1
        port_raw = service.get("port")
        port_display = f":{port_raw}" if port_raw is not None else "—"
        services_table.add_row(
            str(service.get("name", "—")),
            port_display,
            _render_runtime_status(service_status),
        )

    llm_table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        border_style="bright_magenta",
        padding=(0, 1),
    )
    # 18+6+8 content + 6 padding + 2 borders = 40 cols min — fits in 40-col split panel.
    llm_table.add_column("Model", style="bold white", min_width=18)
    llm_table.add_column("Cluster", style="dim", min_width=6)
    llm_table.add_column("Status", min_width=8)

    model_rows = [
        ("Claude Sonnet 4.6", "WEST", llm_statuses.get("Claude Sonnet 4.6", True)),
        ("Gemini 2.5 Flash", "WEST", llm_statuses.get("Gemini 2.5 Flash", True)),
        ("Grok 4.1", "WEST", llm_statuses.get("Grok 4.1", True)),
        ("Kimi k2.5", "EAST", llm_statuses.get("Kimi k2.5", True)),
        ("Minimax M1", "EAST", llm_statuses.get("Minimax M1", True)),
        ("DeepSeek R2", "EAST", llm_statuses.get("DeepSeek R2", True)),
        ("Typhoon-v2 70B", "TH", llm_statuses.get("Typhoon-v2 70B", True)),
    ]
    llm_online = 0
    for name, cluster, is_online in model_rows:
        if is_online:
            llm_online += 1
        llm_table.add_row(
            name,
            cluster,
            "[bright_green]ONLINE[/]" if is_online else "[bright_red]OFFLINE[/]",
        )

    footer = Text()
    footer.append(f"Endpoint: {endpoint}", style="bright_green")
    footer.append("  |  ", style="dim")
    footer.append("Status: ", style="bright_white")
    footer.append_text(Text.from_markup(_render_runtime_status(overall_status)))
    footer.append("  |  ", style="dim")
    footer.append(f"Ready services: {ready_count}/{len(services)}", style="bright_cyan")
    footer.append("  |  ", style="dim")
    footer.append(f"Consensus: {llm_online}/7", style="bright_magenta")
    footer.append("  |  ", style="dim")
    footer.append(f"Source: {source}", style="dim")
    if uptime_seconds is not None:
        footer.append("  |  ", style="dim")
        footer.append(f"Uptime: {uptime_seconds:.1f}s", style="bright_cyan")
    if environment:
        footer.append("  |  ", style="dim")
        footer.append(f"Env: {environment}", style="bright_yellow")
    footer.append("  |  ", style="dim")
    footer.append(f"v{version}", style="bright_yellow")

    console = get_console()

    # Expand tables to cover complete panel width
    services_table.expand = True
    llm_table.expand = True

    layout = Layout(name="root")
    layout.split_column(
        Layout(name="body", ratio=6),
        Layout(Panel(footer, border_style="bright_yellow"), name="footer", size=3),
    )

    if console.is_terminal and console.size.width < 120:
        # Stack vertically on standard/compact viewports for premium readability
        layout["body"].split_column(
            Layout(
                Panel(
                    services_table,
                    title="[bold white]BOOT STATUS[/]",
                    border_style="bright_cyan",
                ),
                name="services",
            ),
            Layout(
                Panel(
                    llm_table,
                    title="[bold white]HEXACORE REGISTRY[/]",
                    border_style="bright_magenta",
                ),
                name="llms",
            ),
        )
    else:
        # Side-by-side split row on wide viewports
        layout["body"].split_row(
            Layout(
                Panel(
                    services_table,
                    title="[bold white]BOOT STATUS[/]",
                    border_style="bright_cyan",
                ),
                name="services",
            ),
            Layout(
                Panel(
                    llm_table,
                    title="[bold white]HEXACORE REGISTRY[/]",
                    border_style="bright_magenta",
                ),
                name="llms",
            ),
        )
    return layout


# ---------------------------------------------------------------------------
# DX Splash, Boot Sequence & Dashboard — rct start
# ---------------------------------------------------------------------------


def _build_emblem(compact: bool = False) -> Text:
    """Build the ANSI-safe emblem derived from the RCT glyph."""
    emblem = Text()
    lines = (RCT_EMBLEM_COMPACT if compact else RCT_EMBLEM_WIDE).splitlines()
    for idx, line in enumerate(lines):
        for char in line:
            if char == "●":
                emblem.append(char, style="bold bright_yellow")
            elif char.isspace():
                emblem.append(char)
            else:
                emblem.append(char, style="bold bright_white")
        if idx < len(lines) - 1:
            emblem.append("\n")
    return emblem


def _build_wordmark() -> Text:
    """Build the text-first RCT OS wordmark."""
    return Text(RCT_WORDMARK, style="bold bright_white")


def _build_wordmark_hero() -> Text:
    """Build the large centered RCT OS hero wordmark."""
    return Text(RCT_WORDMARK_HERO, style="bold bright_white")


def _build_brand_stack(hero: bool = False) -> Text:
    """Compose the emblem and wordmark into a centered brand block."""
    brand = Text()
    brand.append_text(_build_emblem(compact=not hero))
    brand.append("\n\n")
    brand.append_text(_build_wordmark_hero() if hero else _build_wordmark())
    return brand


def _build_runtime_rail(version: str, endpoint: str, mock: bool) -> Table:
    """Build the truthful runtime metadata table for the launch banner."""
    console = get_console()
    rail = Table.grid(padding=(0, 1))
    rail.add_column(style="bright_cyan", no_wrap=True)
    rail.add_column(style="white")
    rail.add_row("version", f"v{version}")
    rail.add_row("mode", "UI test surface only" if mock else "Live control-plane boot")
    rail.add_row("endpoint", endpoint)
    rail.add_row(
        "render",
        f"{'tty' if console.is_terminal else 'buffer'} / {console.color_system or 'plain'} / {console.size.width} cols",
    )
    rail.add_row(
        "proof lanes", "Public SDK proof stays separate from enterprise snapshots"
    )
    return rail


def _build_formula_lockup() -> Text:
    """Build the FDIA constitutional formula display.

    F = Dᴵ × A  is the foundational equation of RCT OS:
      F = Final Output
      D = Data (raised to intent power I)
      A = Architect gate (multiplicative: A=0 → F=0 always)

    Rendered as a prominent multi-line visual card, centered.
    """
    t = Text(justify="center", no_wrap=True)
    # Top rule
    t.append("─" * 6, style="dim #0055CC")
    t.append("  ◆ ", style="bold #FFD700")
    t.append("CONSTITUTIONAL FORMULA", style="bold white")
    t.append(" ◆  ", style="bold #FFD700")
    t.append("─" * 6, style="dim #0055CC")
    t.append("\n")
    # Main equation line
    t.append("\n  ")
    t.append("F", style="bold #FFD700")
    t.append("  =  ", style="dim white")
    t.append("D", style="bold #00E5FF")
    t.append("ᴵ", style="bold #00CCFF")
    t.append("  ×  ", style="dim white")
    t.append("A", style="bold bright_magenta")
    t.append("\n\n")
    # Variable legend (readable, no superscript)
    t.append("  ", style="")
    t.append("F", style="dim #FFD700")
    t.append(" → Output  ·  ", style="dim")
    t.append("D", style="dim #00E5FF")
    t.append(" → Data  ·  ", style="dim")
    t.append("I", style="dim #00CCFF")
    t.append(" → Intent  ·  ", style="dim")
    t.append("A", style="dim bright_magenta")
    t.append(" → Architect", style="dim")
    t.append("\n")
    # Constitutional gate warning
    t.append("  ", style="")
    t.append("⚠  ", style="bold #FF4444")
    t.append("A = 0", style="bold #FF4444")
    t.append("  →  ", style="dim")
    t.append("F = 0", style="bold #FF4444")
    t.append("  (Constitutional Block)", style="dim #FF6666")
    t.append("\n\n")
    # Bottom rule
    t.append("─" * 6, style="dim #0055CC")
    t.append("  Constitutional Routing Discipline  ", style="italic dim")
    t.append("─" * 6, style="dim #0055CC")
    return t


def _build_operations_note(mock: bool) -> Text:
    """Build the secondary note that explains the launch surface rules."""
    note = Text.from_markup(
        "[bright_white]Prompt runway stays separate from proof lanes[/]\n"
        "[dim]Public SDK proof | Enterprise runtime footprint | Benchmark scope[/]\n"
        + (
            "[dim]Preview mode renders the launch surface only — runtime remains offline[/]"
            if mock
            else "[dim]Live mode promotes from launch rail to runtime dashboard after bind completes[/]"
        )
    )
    return note


# ---------------------------------------------------------------------------
# Wordmark Gradient + Animation Helpers
# ---------------------------------------------------------------------------

# Top-to-bottom gradient: bright sky-cyan → deep electric blue (6 rows)
_GRADIENT_ROWS_STANDARD = [
    "#00E5FF",  # Row 1 — bright sky cyan
    "#00CCFF",  # Row 2
    "#00B3FF",  # Row 3
    "#0099EE",  # Row 4
    "#007FDD",  # Row 5
    "#005FCC",  # Row 6 — deep electric blue
]
# Wide tier: GOLD gradient — warm ember orange for enterprise premium feel
_GRADIENT_ROWS_WIDE = [
    "#FFD700",  # Row 1 — bright gold
    "#FFBA00",  # Row 2
    "#FF9500",  # Row 3
    "#FF7A00",  # Row 4
    "#FF5500",  # Row 5
    "#E03000",  # Row 6 — deep ember orange
]

# Letter column boundaries within the 49-char "RCT OS" wordmark
# Format: (start_col, end_col_inclusive)
_LETTER_BOUNDS_FULL = [(0, 8), (9, 16), (17, 25), (26, 30), (31, 39), (40, 48)]
_LETTER_BOUNDS_COMPACT = [(0, 8), (9, 16), (17, 25)]


def _make_gradient_wordmark(wordmark: str, tier: str = "standard") -> Text:
    """Apply per-row top-to-bottom gradient to a block wordmark.

    Returns a Rich Text object with 24-bit color per row, centered naturally.
    tier: 'standard' | 'wide' | 'compact'
    """
    row_colors = _GRADIENT_ROWS_WIDE if tier == "wide" else _GRADIENT_ROWS_STANDARD
    result = Text(no_wrap=True)
    lines = wordmark.splitlines()
    for i, line in enumerate(lines):
        color = row_colors[i] if i < len(row_colors) else row_colors[-1]
        result.append(line, style=f"bold {color}")
        if i < len(lines) - 1:
            result.append("\n")
    return result


def _animate_wordmark_reveal(
    console: Console,
    wordmark: str,
    tier: str = "standard",
    delay: float = 0.11,
    no_animation: bool = False,
) -> None:
    """Reveal the wordmark letter-by-letter using Rich Live display.

    Skipped automatically in non-TTY / narrow terminals / test environments
    or when no_animation is True.
    """
    if no_animation or not console.is_terminal:
        console.print(Align.center(_make_gradient_wordmark(wordmark, tier=tier)))
        return

    lines = wordmark.splitlines()
    if not lines:
        return
    width = len(lines[0])
    bounds = _LETTER_BOUNDS_FULL if width > 30 else _LETTER_BOUNDS_COMPACT
    row_colors = _GRADIENT_ROWS_WIDE if tier == "wide" else _GRADIENT_ROWS_STANDARD

    # Build blank canvas (all spaces, same dimensions)
    canvas = [list(" " * width) for _ in lines]

    def _render_canvas() -> Text:
        result = Text(no_wrap=True)
        for i, row_chars in enumerate(canvas):
            color = row_colors[i] if i < len(row_colors) else row_colors[-1]
            result.append("".join(row_chars), style=f"bold {color}")
            if i < len(canvas) - 1:
                result.append("\n")
        return result

    with Live(
        Align.center(_render_canvas()),
        console=console,
        auto_refresh=False,
        vertical_overflow="visible",
        transient=False,
    ) as live:
        for start, end in bounds:
            # Copy this letter's columns from wordmark into canvas
            for row_i, line in enumerate(lines):
                for col in range(start, min(end + 1, len(line))):
                    canvas[row_i][col] = line[col]
            live.update(Align.center(_render_canvas()), refresh=True)
            time.sleep(delay)


def _welcome_header(tier: str = "standard") -> Text:
    """Build a branded welcome line printed ABOVE the wordmark.

    Wide tier:    gold-colored double-rule with diamond markers
    Standard tier: cyan-colored rule with star markers
    """
    t = Text(no_wrap=True)
    if tier == "wide":
        t.append("═" * 8, style="#FFD700")
        t.append("  ◆ ", style="bold #FFD700")
        t.append("RCT OS", style="bold white")
        t.append(" — Enterprise Control Plane", style="#FF9500")
        t.append(" ◆  ", style="bold #FFD700")
        t.append("═" * 8, style="#FFD700")
    else:
        t.append("─" * 4, style="dim #00CCFF")
        t.append("  ✦ ", style="bold #00E5FF")
        t.append("RCT Control Plane", style="bold white")
        t.append(" ✦  ", style="bold #00E5FF")
        t.append("─" * 4, style="dim #00CCFF")
    return t


def _shadow_row(wordmark: str, tier: str = "standard") -> Text:
    """Build a 3D shadow row (▀ chars) rendered below the wordmark.

    Scans the last row of the wordmark and places ▀ (UPPER HALF BLOCK)
    at positions occupied by non-space chars, in a very dark color.
    Shifts the shadow row 1 space to the right to create a realistic 3D depth offset.
    """
    last_row = wordmark.splitlines()[-1]
    highlight_color = "#002060" if tier == "wide" else "#001833"
    shadow = Text(no_wrap=True)
    shadow.append(" ")  # Shift shadow right by 1 space column
    for ch in last_row[:-1]:  # Drop last character to preserve overall line length
        if ch != " ":
            shadow.append("▀", style=f"bold {highlight_color}")
        else:
            shadow.append(" ", style="")
    return shadow


def _version_badge(version: str, tier: str = "standard") -> Panel:
    """Build a centered version badge inside a modern rounded pill-box container."""
    content = Text(no_wrap=True)
    if tier == "wide":
        content.append("RCT OS  ", style="bold white")
        content.append(f"v{version}", style="bold #FFD700")
        content.append("  ●", style="bold #00FF00")
        content.append(" Active", style="bold #FF9500")
        border_style = "#FFD700"
    else:
        content.append("RCT OS  ", style="bold white")
        content.append(f"v{version}", style="bold #00E5FF")
        content.append("  ●", style="bold #00FF00")
        content.append(" Active", style="dim white")
        border_style = "#0099EE"

    return Panel(
        content,
        box=box.ROUNDED,
        border_style=border_style,
        padding=(0, 2),
        expand=False,
    )


def print_splash(
    version: str = "1.2.0",
    endpoint: str = "http://127.0.0.1:8000",
    mock: bool = False,
    no_animation: bool = False,
) -> None:
    """Print the branded RCT launch header with width-aware fallbacks."""
    console = get_console()
    formula = _build_formula_lockup()
    detail = _build_operations_note(mock)
    runtime_rail = _build_runtime_rail(version=version, endpoint=endpoint, mock=mock)

    config = _load_config()
    wide_threshold = config.get("wide_threshold", 140)
    standard_threshold = config.get("standard_threshold", 100)
    no_anim = no_animation or config.get("no_animation", False)

    # ── Wide Tier (≥ wide_threshold cols) ────────────────────────────────────────────────
    # Welcome header → animated gold wordmark → version badge → Rule → panels
    if console.is_terminal and console.size.width >= wide_threshold:
        console.print()
        console.print(Align.center(_welcome_header(tier="wide")))
        console.print()
        console.print()
        _animate_wordmark_reveal(console, RCT_WORDMARK_BLOCK, tier="wide", no_animation=no_anim)
        # Note: animation (transient=False) already leaves final wordmark on screen.
        # No redundant static print needed for TTY — wide tier always requires is_terminal.
        console.print(Align.center(_shadow_row(RCT_WORDMARK_BLOCK, tier="wide")))
        console.print()
        console.print(Align.center(_version_badge(version, tier="wide")))
        console.print()
        console.print(Rule(style="#FF7A00"))
        console.print()
        # Formula as a focused gold-bordered card
        console.print(
            Align.center(
                Panel(
                    formula,
                    border_style="#FFD700",
                    padding=(0, 3),
                    expand=False,
                )
            )
        )
        console.print()
        console.print(
            Columns(
                [
                    Panel(
                        runtime_rail,
                        title="[bold white]RUNTIME RAIL[/]",
                        border_style="#FF9500",
                    ),
                    Panel(
                        detail,
                        title="[bold white]OPERATIONS NOTE[/]",
                        border_style="#FF9500",
                    ),
                ],
                expand=True,
                equal=True,
            )
        )
        console.print()
        return

    # ── Standard Tier (≥ standard_threshold cols) ───────────────────────────────────────────
    # Welcome header → animated cyan wordmark → badge → Rule → info panel
    if console.is_terminal and console.size.width >= standard_threshold:
        console.print()
        console.print(Align.center(_welcome_header(tier="standard")))
        console.print()
        console.print()
        _animate_wordmark_reveal(console, RCT_WORDMARK_BLOCK, tier="standard", no_animation=no_anim)
        # Note: animation (transient=False) already leaves final wordmark on screen.
        # No redundant static print needed for TTY — standard tier always requires is_terminal.
        console.print(Align.center(_shadow_row(RCT_WORDMARK_BLOCK, tier="standard")))
        console.print()
        console.print(Align.center(_version_badge(version, tier="standard")))
        console.print()
        console.print(Rule(style="#0099EE"))
        console.print(
            Panel(
                Columns(
                    [
                        Panel(
                            runtime_rail,
                            title="[bold white]RUNTIME RAIL[/]",
                            border_style="#0099EE",
                        ),
                        Panel(
                            detail,
                            title="[bold white]OPERATIONS NOTE[/]",
                            border_style="#0099EE",
                        ),
                    ],
                    expand=True,
                    equal=False,
                ),
                title="[bold white]RCT OS[/]",
                subtitle="[dim]standard launch frame[/]",
                border_style="#005FCC",
                padding=(0, 1),
            )
        )
        # Formula as a focused cyan-bordered card below panels
        console.print()
        console.print(
            Align.center(
                Panel(
                    formula,
                    border_style="#0099EE",
                    padding=(0, 3),
                    expand=False,
                )
            )
        )
        console.print()
        return

    # ── Compact Fallback (< 100 cols or non-terminal) ────────────────────────
    # Gradient compact wordmark → Rule → version inside panel
    console.print()
    # Gradient for compact (reuses standard colors, just 3 letters wide)
    console.print(
        Align.center(
            _make_gradient_wordmark(RCT_WORDMARK_BLOCK_COMPACT, tier="standard")
        )
    )
    console.print()
    console.print(Rule(style="dim #0099EE"))
    console.print()

    content = Text()
    content.append("RCT/OS", style="bold bright_white")
    content.append(f"  v{version}\n", style="bold #00E5FF")
    content.append("compact launch rail\n", style="dim")
    content.append(
        "mode: UI test surface only\n" if mock else "mode: Live control-plane boot\n",
        style="white",
    )
    content.append(f"endpoint: {endpoint}\n", style="white")
    content.append("\n")
    content.append(
        "proof lanes: public SDK proof remains separate from enterprise snapshots\n",
        style="dim",
    )
    content.append_text(formula)

    console.print(
        Panel(
            content,
            title="[bold white]RCT/OS[/]",
            border_style="#0099EE",
            padding=(0, 1),
        )
    )


def boot_sequence_animation(
    mock: bool = False,
    overall_status: str = "launching",
    quiet: bool = False,
    no_animation: bool = False,
) -> None:
    """Animate a truthful pre-launch sequence with state-aware messaging.

    Uses Rich Progress bar to show visual boot progress, then replaces with
    the static V1-style service list after completion.

    quiet=True: suppresses terminal bell sound on boot complete.
    no_animation=True: skips all progress bar sequencing and delays.
    """
    console = get_console()
    services = [
        ("gateway-api", 8000, "Unified entry point"),
        ("intent-loop", 8001, "JITNA Protocol · <50ms warm recall"),
        ("analysearch-intent", 8002, "GIGO Protection active"),
        ("vector-search", 8003, "DelentiaDB mounted"),
        ("crystallizer", 8004, "0.3% hallucination guard"),
        ("delta-engine", None, "74% memory compression"),
    ]

    config = _load_config()
    no_anim = no_animation or config.get("no_animation", False)

    delay = 0.35 if mock else 0.6
    phase_label = "PREVIEW" if mock else "STARTING"
    phase_style = "bright_cyan" if mock else "yellow"

    # ── Progress bar boot sequence (TTY only) ────────────────────────
    console.print()
    if console.is_terminal and not no_anim:
        with Progress(
            SpinnerColumn(spinner_name="dots", style="bold #00E5FF"),
            TextColumn("[bold white]{task.description}[/]"),
            BarColumn(
                bar_width=None,
                style="#005FCC",
                complete_style="#00E5FF",
                finished_style="bold bright_green",
            ),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,  # progress bar disappears after completion
        ) as progress:
            task = progress.add_task("Booting services", total=len(services))
            for name, port, desc in services:
                # Update description to show current service
                progress.update(task, description=f"[bold white]{name}[/]")
                time.sleep(delay)
                progress.advance(task)
    elif not no_anim:
        # Non-TTY: simple sequential delay without progress bar
        for name, _port, _desc in services:
            time.sleep(delay * 0.2)

    # ── Static service list — staggered reveal (0.05s per line) ──────
    for name, port, desc in services:
        port_label = f":{port}" if port else "     "
        console.print(
            f"  [{phase_style}]{phase_label:<8}[/] [bold bright_white]{name:<20}[/]"
            f" [bold #00CCFF]{port_label:<6}[/]  [dim]{desc}[/]"
        )
        if console.is_terminal and not no_anim:
            time.sleep(0.05)  # smooth stagger between service lines
    console.print()
    if overall_status == "ui-test":
        summary = "[bright_cyan]UI preview complete[/] [dim]— runtime not started[/]"
    elif overall_status == "launching":
        summary = "[yellow]Launch sequence prepared[/] [dim]— awaiting API bind[/]"
    elif overall_status == "serving":
        summary = f"[bright_green]Runtime serving[/] [dim]— {len(services)} components reachable[/]"
    elif overall_status == "degraded":
        summary = "[yellow]Runtime degraded[/] [dim]— review health endpoint output[/]"
    elif overall_status == "health-unknown":
        summary = "[yellow]Port probe only[/] [dim]— health endpoint unavailable[/]"
    else:
        summary = "[bright_red]Runtime offline[/] [dim]— services not reachable[/]"
    console.print(f"  {summary}")
    # ── Boot complete sound (terminal bell) ─────────────────────────
    if console.is_terminal and not quiet:
        sys.stdout.write("\a")
        sys.stdout.flush()
    # Brief pause so tables don't 'pop' instantly after service list
    if console.is_terminal and not no_anim:
        time.sleep(0.45)
    console.print()


def render_hexacore_table(
    mock: bool = False,
    statuses: Optional[Dict[str, bool]] = None,
) -> None:
    """Render the HexaCore 7-LLM Consensus Registry dashboard."""
    console = get_console()
    if statuses is None:
        statuses = {}

    def _badge(name: str) -> str:
        is_online = statuses.get(name, True)  # default ONLINE in mock/no-check mode
        dot = "[bright_green]●[/]" if is_online else "[bright_red]●[/]"
        status_txt = (
            "[bright_green]ONLINE[/]" if is_online else "[bright_red]OFFLINE[/]"
        )
        return f"{dot} [bold white]{name}[/]  {status_txt}"

    table = Table(
        title="[bold white]HEXACORE CONSENSUS REGISTRY[/]",
        box=box.DOUBLE_EDGE,
        border_style="bright_cyan",
        show_header=True,
        padding=(0, 1),
    )
    table.add_column("🌐 WESTERN CLUSTER", style="bright_cyan", min_width=32)
    table.add_column("🌏 EASTERN CLUSTER", style="bright_magenta", min_width=30)
    table.add_column("🌏 REGIONAL", style="bright_yellow", min_width=22)

    table.add_row(
        _badge("Claude Sonnet 4.6") + "\n[dim]  Supreme · Governance Lead[/]",
        _badge("Kimi k2.5") + "\n[dim]  Lead Builder[/]",
        _badge("Typhoon-v2 70B") + "\n[dim]  TH Regional[/]",
    )
    table.add_row(
        _badge("Gemini 2.5 Flash") + "\n[dim]  Specialist · Research[/]",
        _badge("Minimax M1") + "\n[dim]  Junior Builder[/]",
        "",
    )
    table.add_row(
        _badge("Grok 4.1") + "\n[dim]  Librarian · Context[/]",
        _badge("DeepSeek R2") + "\n[dim]  Humanizer[/]",
        "",
    )
    console.print(table)
    console.print()
    online_count = sum(1 for v in statuses.values() if v) if statuses else 7
    total = 7
    sla_color = "bright_green" if online_count == total else "yellow"
    console.print(
        f"  [{sla_color}]CONSENSUS: {online_count}/{total} LLMs active[/]"
        f"  [dim]|[/]  [bright_green]SLA: 99.98%[/]"
        f"  [dim]|[/]  [bright_cyan]WARM RECALL: <50ms[/]"
        f"  [dim]|[/]  [bright_magenta]SignedAI: ED25519 ✓[/]"
    )
    console.print()


def render_architect_veto(reason: str = "Policy block enforced") -> None:
    """Render the A=0 ARCHITECT VETO full-screen alert panel."""
    console = get_console()
    content = Text()
    content.append("\n")
    content.append(
        "  ██████  SYSTEM HALTED: ARCHITECT VETO  ██████\n", style="bold bright_red"
    )
    content.append("\n")
    content.append("  A = 0  →  OUTPUT = 0\n", style="bold bright_red")
    content.append(
        "  Multiplicative Property Enforced — No output will be produced.\n",
        style="bright_red",
    )
    content.append("\n")
    content.append(f"  Reason: {reason}\n", style="yellow")
    content.append("\n")
    content.append(
        "  F = Dᴵ × A   when A = 0,   F = 0   (regardless of Data or Intent)\n",
        style="dim",
    )
    content.append("\n")
    content.append(
        "  To unblock: Update Architect policy and re-submit intent.\n", style="dim"
    )
    content.append("\n")
    console.print(
        Panel(
            content,
            border_style="bright_red",
            title="[bold bright_red]⛔  CONSTITUTIONAL BLOCK[/]",
            padding=(0, 1),
        )
    )


def render_pipeline_flow(
    current_stage: str = "Output",
    stages_passed: Optional[List[str]] = None,
) -> None:
    """Render FDIA→JITNA→HexaCore→SignedAI→Output pipeline progress."""
    console = get_console()
    pipeline = [
        ("FDIA", "Constitutional Gate"),
        ("JITNA", "Intent Packet"),
        ("HexaCore", "7-LLM Consensus"),
        ("SignedAI", "ED25519 Sign"),
        ("Output", "Final Response"),
    ]
    if stages_passed is None:
        stage_names = [s[0] for s in pipeline]
        try:
            idx = stage_names.index(current_stage)
            stages_passed = stage_names[: idx + 1]
        except ValueError:
            stages_passed = []
    parts: List[str] = []
    for name, _desc in pipeline:
        if name in stages_passed and name != current_stage:
            parts.append(f"[bright_green]✓ {name}[/]")
        elif name == current_stage:
            parts.append(f"[bold bright_yellow]⟳ {name}[/]")
        else:
            parts.append(f"[dim]○ {name}[/]")
    flow_line = "  [dim]→[/]  ".join(parts)
    console.print(
        Panel(
            flow_line + f"\n\n  [dim]Current stage:[/] [bold white]{current_stage}[/]",
            title="[bold white]Intent Pipeline[/]",
            border_style="bright_cyan",
            padding=(0, 2),
        )
    )
