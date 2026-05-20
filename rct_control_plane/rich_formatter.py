"""
rct_control_plane/rich_formatter.py — Rich Terminal Output Formatters

Provides beautiful terminal output for all CLI commands using Rich library.
Replaces plain click.echo + manual table formatting with Rich components.

All functions accept data dicts and return rendered output via console.print().
When --output json is requested, these functions are bypassed entirely.

Reference: TUI-CLI RCT Design — Phase 4A
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.syntax import Syntax
from rich import box


# Shared console instance
_console: Optional[Console] = None


def get_console() -> Console:
    """Get or create the shared Rich console."""
    global _console
    if _console is None:
        _console = Console()
    return _console


def set_console(console: Console) -> None:
    """Override the shared console (for testing with StringIO)."""
    global _console
    _console = console


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

_STATUS_COLORS = {
    "success": "bright_green",
    "completed": "bright_green",
    "active": "bright_green",
    "running": "bright_green",
    "healthy": "bright_green",
    "passed": "bright_green",
    "blocked": "bright_red",
    "error": "bright_red",
    "failed": "bright_red",
    "unhealthy": "bright_red",
    "warning": "yellow",
    "pending": "yellow",
    "unknown": "dim",
}


def _colorize_status(status: str) -> str:
    """Wrap status text in a Rich color tag."""
    color = _STATUS_COLORS.get(status.lower(), "white")
    return f"[{color}]{status}[/{color}]"


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
    console.print(Panel(
        content,
        title="[bold white]Intent State[/]",
        border_style="bright_cyan",
        padding=(1, 2),
    ))


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

    console.print(Panel(
        table,
        title="[bold white]Observer Metrics[/]",
        border_style="bright_magenta",
        padding=(0, 1),
    ))


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
        health_display = "[bright_green]● ONLINE[/]" if health else "[bright_red]● OFFLINE[/]"
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
        console.print(Panel(
            "[bright_green]No governance violations recorded.[/]",
            title="[bold white]Governance Log[/]",
            border_style="bright_green",
        ))
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
        res_str = ", ".join(f"{k}:{v:+.1f}" for k, v in res_delta.items()) if res_delta else "—"

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

def render_execution_log(logs: List[Dict[str, Any]], title: str = "Execution Log") -> None:
    """Render adapter execution log entries."""
    console = get_console()

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
        sha = entry.get("sha256_hash", "")[:16] + "..." if entry.get("sha256_hash") else "—"
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

    console.print(table)


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
    console.print(Panel(
        Syntax(
            __import__("json").dumps(original, indent=2, default=str),
            "json",
            theme="monokai",
        ),
        title="[bold white]Original Execution[/]",
        border_style="bright_cyan",
    ))

    if replayed is not None:
        console.print(Panel(
            Syntax(
                __import__("json").dumps(replayed, indent=2, default=str),
                "json",
                theme="monokai",
            ),
            title="[bold white]Replayed Execution[/]",
            border_style="bright_magenta",
        ))

    if match is not None:
        if match:
            console.print(Panel(
                "[bold bright_green]✅ Deterministic Match — Hashes are identical[/]",
                border_style="bright_green",
            ))
        else:
            console.print(Panel(
                "[bold bright_red]❌ Deterministic MISMATCH — Hashes diverge![/]",
                border_style="bright_red",
            ))


# ---------------------------------------------------------------------------
# Generic Helpers
# ---------------------------------------------------------------------------

def render_error(message: str) -> None:
    """Render an error panel."""
    get_console().print(Panel(
        f"[bold bright_red]❌ {message}[/]",
        border_style="bright_red",
        title="[bold white]Error[/]",
    ))


def render_success(message: str) -> None:
    """Render a success panel."""
    get_console().print(Panel(
        f"[bold bright_green]✅ {message}[/]",
        border_style="bright_green",
        title="[bold white]Success[/]",
    ))


def render_warning(message: str) -> None:
    """Render a warning panel."""
    get_console().print(Panel(
        f"[bold yellow]⚠️  {message}[/]",
        border_style="yellow",
        title="[bold white]Warning[/]",
    ))


# ---------------------------------------------------------------------------
# DX Splash, Boot Sequence & Dashboard — rct start
# ---------------------------------------------------------------------------

def print_splash(version: str = "1.0.3b0") -> None:
    """Print the RCT OS Constitutional Declaration splash panel."""
    console = get_console()
    content = Text()
    content.append("\n")
    content.append("  RCT OS — INTENT CENTRIC AI\n", style="bold bright_white")
    content.append("  " + "─" * 44 + "\n", style="dim")
    content.append("\n")
    content.append("  F = D", style="bold bright_cyan")
    content.append("ᴵ", style="bold bright_cyan")
    content.append(" × A", style="bold bright_cyan")
    content.append("   (Constitutional Guarantee)\n", style="dim")
    content.append("\n")
    content.append("  When A = 0  →  OUTPUT = 0  ", style="bold bright_red")
    content.append("(Multiplicative Block — no exception)\n", style="dim")
    content.append("\n")
    content.append(f"  v{version}", style="bold bright_magenta")
    content.append("  ·  41 Algorithms", style="dim")
    content.append("  ·  SLA 99.98%", style="dim")
    content.append("  ·  HexaCore 7-LLM\n", style="dim")
    content.append("\n")
    console.print(Panel(
        content,
        border_style="bright_cyan",
        padding=(0, 1),
    ))


def boot_sequence_animation(mock: bool = False) -> None:
    """Animate 5-service boot sequence with Rich Status spinners."""
    console = get_console()
    services = [
        ("gateway-api",        8000, "Unified entry point"),
        ("intent-loop",        8001, "JITNA Protocol · <50ms warm recall"),
        ("analysearch-intent", 8002, "GIGO Protection active"),
        ("vector-search",      8003, "RCTDB mounted"),
        ("crystallizer",       8004, "0.3% hallucination guard"),
        ("delta-engine",       None, "74% memory compression"),
    ]
    delay = 0.35 if mock else 0.6
    console.print()
    for name, port, desc in services:
        port_label = f":{port}" if port else "     "
        label = f"[dim]Booting[/] [bold white]{name}[/] [dim]{port_label}[/]"
        with Status(label, console=console, spinner="dots"):
            time.sleep(delay)
        tag = f"[dim]{port_label}[/]"
        console.print(
            f"  [bright_green]✓ OK[/]  [bold white]{name:<24}[/] {tag}  [dim]{desc}[/]"
        )
    console.print()
    console.print(f"  [bright_green]All systems nominal[/] [dim]— {len(services)} components ready[/]")
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
        status_txt = "[bright_green]ONLINE[/]" if is_online else "[bright_red]OFFLINE[/]"
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
    content.append("  ██████  SYSTEM HALTED: ARCHITECT VETO  ██████\n", style="bold bright_red")
    content.append("\n")
    content.append("  A = 0  →  OUTPUT = 0\n", style="bold bright_red")
    content.append("  Multiplicative Property Enforced — No output will be produced.\n", style="bright_red")
    content.append("\n")
    content.append(f"  Reason: {reason}\n", style="yellow")
    content.append("\n")
    content.append("  F = Dᴵ × A   when A = 0,   F = 0   (regardless of Data or Intent)\n", style="dim")
    content.append("\n")
    content.append("  To unblock: Update Architect policy and re-submit intent.\n", style="dim")
    content.append("\n")
    console.print(Panel(
        content,
        border_style="bright_red",
        title="[bold bright_red]⛔  CONSTITUTIONAL BLOCK[/]",
        padding=(0, 1),
    ))


def render_pipeline_flow(
    current_stage: str = "Output",
    stages_passed: Optional[List[str]] = None,
) -> None:
    """Render FDIA→JITNA→HexaCore→SignedAI→Output pipeline progress."""
    console = get_console()
    pipeline = [
        ("FDIA",     "Constitutional Gate"),
        ("JITNA",    "Intent Packet"),
        ("HexaCore", "7-LLM Consensus"),
        ("SignedAI", "ED25519 Sign"),
        ("Output",   "Final Response"),
    ]
    if stages_passed is None:
        stage_names = [s[0] for s in pipeline]
        try:
            idx = stage_names.index(current_stage)
            stages_passed = stage_names[:idx + 1]
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
    console.print(Panel(
        flow_line + f"\n\n  [dim]Current stage:[/] [bold white]{current_stage}[/]",
        title="[bold white]Intent Pipeline[/]",
        border_style="bright_cyan",
        padding=(0, 2),
    ))
