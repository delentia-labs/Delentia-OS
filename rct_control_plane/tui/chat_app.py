"""
Delentia OS - Real Chat-Capable Terminal UI (Round 36).

Before this round, this workspace had zero REPL/chat terminal
infrastructure anywhere (confirmed via a full-repo investigation across
all ~14 repos) - cli.py's existing `status --live`/`logs --follow`
commands are real, rich.Live-based dashboards, but read-only pollers
with no input handling at all. This is the first real interactive
terminal surface: type a message, it dispatches directly to a real
AutonomousLoop.run() call (in-process, no HTTP round-trip needed since
this runs alongside rct_control_plane), and the real result streams
back into a scrolling conversation view.

Deliberately scoped v1 (see the Round 36 synthesis doc for the full
Hermes-TUI feature enumeration this was informed by, and what's
consciously deferred): single-line input (not full multi-line
$EDITOR-style composition), no streaming token-by-token rendering
(AutonomousLoop.run() itself isn't a generator - it returns one final
result after the whole decide/act/observe loop finishes; a "thinking..."
status is shown while the real call is in flight), 4 real slash
commands (not a floating autocomplete panel). Real, useful, and honest
about what it isn't yet - not a shrunken imitation dressed up as parity.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

_HELP_TEXT = (
    "[bold]Commands[/]\n"
    "  /help    show this message\n"
    "  /reset   start a fresh, isolated session (new namespace)\n"
    "  /status  show real daemon + kernel status\n"
    "  /quit    exit\n"
    "Anything else is sent to Delentia as a real goal."
)


class DelentiaChatApp(App):
    """Real, minimal chat TUI. `kernel` is required for real dispatch;
    tests may pass a fake with a `._persistence` attribute and monkeypatch
    `_dispatch_to_autonomous_loop` to avoid a real LLM call (same
    testable-seam pattern the Round 36 gateways already established)."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #conversation {
        height: 1fr;
        border: solid $accent;
    }
    #composer {
        dock: bottom;
        margin-bottom: 1;
    }
    #status_bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
    }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self, kernel: Any, namespace: Optional[str] = None):
        super().__init__()
        self.kernel = kernel
        self.namespace = namespace or f"terminal-{uuid.uuid4().hex[:8]}"
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="conversation", wrap=True, markup=True, highlight=True)
        yield Static("ready", id="status_bar")
        yield Input(placeholder="Type a message, or /help for commands...", id="composer")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Delentia Desk Terminal"
        log = self.query_one("#conversation", RichLog)
        log.write(f"[bold cyan]Delentia OS Terminal[/] — session: {self.namespace}")
        log.write("[dim]Type a message and press Enter. /help for commands.[/]")
        self.query_one("#composer", Input).focus()

    def _set_status(self, text: str) -> None:
        self.query_one("#status_bar", Static).update(text)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text or self._busy:
            return
        if text.startswith("/"):
            await self._handle_slash_command(text)
        else:
            await self._send_message(text)

    async def _handle_slash_command(self, text: str) -> None:
        log = self.query_one("#conversation", RichLog)
        command = text.split()[0].lower()
        if command == "/help":
            log.write(_HELP_TEXT)
        elif command == "/reset":
            self.namespace = f"terminal-{uuid.uuid4().hex[:8]}"
            log.write(f"[yellow]New session started: {self.namespace}[/]")
        elif command == "/status":
            status = await self._get_status()
            log.write(f"[dim]{status}[/]")
        elif command == "/quit":
            self.exit()
        else:
            log.write(f"[red]Unknown command: {command}[/] (try /help)")

    async def _get_status(self) -> str:
        """Real status - split out so tests can monkeypatch it without
        needing the daemon actually running."""
        try:
            from rct_control_plane import api as api_module
            running = api_module._DAEMON_SCHEDULER is not None and api_module._DAEMON_SCHEDULER._is_running
            return f"daemon running: {running}, session: {self.namespace}"
        except Exception as e:
            return f"status unavailable: {e}"

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        """Real dispatch - deliberate testable seam, same pattern as
        gateways/telegram_gateway.py and gateways/line_gateway.py."""
        from rct_control_plane.autonomous_loop import AutonomousLoop
        from rct_control_plane.mcp_server import mcp

        loop = AutonomousLoop(mcp_server=mcp, persistence=self.kernel._persistence, namespace=namespace)
        return await loop.run(goal)

    async def _send_message(self, text: str) -> None:
        log = self.query_one("#conversation", RichLog)
        log.write(f"[bold green]You:[/] {text}")
        self._busy = True
        self._set_status("thinking...")
        start = time.monotonic()
        try:
            result = await self._dispatch_to_autonomous_loop(text, self.namespace)
            elapsed = time.monotonic() - start
            answer = result.get("final_answer") or f"(stopped: {result.get('stopped_reason', 'unknown')})"
            log.write(f"[bold magenta]Delentia:[/] {answer}")
            self._set_status(f"ready — {elapsed:.1f}s, {result.get('iterations', 0)} step(s)")
        except Exception as e:
            log.write(f"[bold red]Error:[/] {e}")
            self._set_status("ready")
        finally:
            self._busy = False


def run_chat(kernel: Optional[Any] = None) -> None:
    """Real entry point for `rct chat` - constructs a real kernel if none
    is supplied (matching every other CLI command's own pattern)."""
    if kernel is None:
        from rct_control_plane.algorithm_kernel_41 import ALGORITHM_KERNEL
        kernel = ALGORITHM_KERNEL
    app = DelentiaChatApp(kernel=kernel)
    app.run()
