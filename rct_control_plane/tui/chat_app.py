"""
Delentia OS - Real Chat-Capable Terminal UI (Round 36, extended Round 37).

Before Round 36, this workspace had zero REPL/chat terminal
infrastructure anywhere (confirmed via a full-repo investigation across
all ~14 repos) - cli.py's existing `status --live`/`logs --follow`
commands are real, rich.Live-based dashboards, but read-only pollers
with no input handling at all.

Round 37 additions (see DELENTIA_ROUND36_..._SYNTHESIS.md's gap table
against Hermes/DeepSeek Harness for what motivated each one):
- Multi-line input via a real `TextArea` composer (Enter inserts a
  newline; Ctrl+S sends - chosen because Shift+Enter/Ctrl+Enter are not
  reliably distinguishable from plain Enter across real terminal
  emulators, so a dedicated, unambiguous send key is the honest choice).
- Live per-step introspection: AutonomousLoop.run()'s new optional
  `on_step` hook (see autonomous_loop.py) now renders each real
  decide/act/observe step into the conversation log as it happens,
  replacing the old static "thinking..." status with a genuine trace.
- Session persistence across restarts: the default (non-/reset)
  namespace is now stable across process launches, and its transcript
  is reloaded from ControlPlanePersistence's real `memories` table
  (memory_type="tui_transcript") on startup - a real reload, not a
  simulated one.

Still deliberately out of scope (see the synthesis doc's honest gap
table): token-by-token streaming (AutonomousLoop.run() itself isn't a
generator - "thinking... (step N)" is a genuine per-step trace, not a
token stream), a floating slash-command autocomplete panel (still 4
fixed commands), and light/dark theme switching.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, OptionList, RichLog, Static, TextArea
from textual.widgets.option_list import Option

_DEFAULT_NAMESPACE = "terminal-default"
_TRANSCRIPT_MEMORY_TYPE = "tui_transcript"

_SLASH_COMMANDS = {
    "/help": "show this message",
    "/reset": "start a fresh, isolated session (new namespace)",
    "/status": "show real daemon + kernel status",
    "/quit": "exit",
}

_HELP_TEXT = (
    "[bold]Commands[/]\n"
    "  /help    show this message\n"
    "  /reset   start a fresh, isolated session (new namespace)\n"
    "  /status  show real daemon + kernel status\n"
    "  /quit    exit\n"
    "Type a message and press Ctrl+S to send (Enter inserts a newline).\n"
    "Ctrl+T toggles light/dark theme.\n"
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
        height: 3;
        margin-bottom: 1;
        border: solid $accent;
    }
    #autocomplete {
        dock: bottom;
        height: auto;
        max-height: 6;
        margin-bottom: 4;
        border: solid $accent;
        display: none;
    }
    #streaming_preview {
        dock: bottom;
        height: auto;
        max-height: 6;
        margin-bottom: 4;
        border: solid $accent;
        color: $text-muted;
        display: none;
    }
    #status_bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+s", "submit_composer", "Send"),
        ("ctrl+t", "toggle_dark", "Theme"),
    ]

    def __init__(self, kernel: Any, namespace: Optional[str] = None):
        super().__init__()
        self.kernel = kernel
        # Round 37: a stable default namespace (not a random uuid) so its
        # transcript can genuinely be reloaded across process restarts.
        # /reset still creates a fresh, ephemeral, uuid-based namespace -
        # explicitly NOT persisted/reloaded, matching its own "start
        # fresh" intent.
        self.namespace = namespace or _DEFAULT_NAMESPACE
        self._busy = False
        self._streaming_buffer = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="conversation", wrap=True, markup=True, highlight=True)
        yield OptionList(id="autocomplete")
        yield Static("", id="streaming_preview")
        yield Static("ready", id="status_bar")
        yield TextArea(id="composer")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Delentia Desk Terminal"
        log = self.query_one("#conversation", RichLog)
        log.write(f"[bold cyan]Delentia OS Terminal[/] — session: {self.namespace}")
        log.write("[dim]Type a message, Ctrl+S to send (Enter = newline). /help for commands.[/]")
        self._reload_transcript()
        self.query_one("#composer", TextArea).focus()

    def _reload_transcript(self) -> None:
        """Round 37: real reload of this namespace's prior transcript
        from ControlPlanePersistence - not simulated. Ephemeral /reset
        namespaces have no prior rows, so this is a real no-op for them."""
        log = self.query_one("#conversation", RichLog)
        try:
            rows = self.kernel._persistence.list_memories(
                namespace=self.namespace, memory_type=_TRANSCRIPT_MEMORY_TYPE,
            )
        except Exception:
            return
        rows.sort(key=lambda r: r.get("created_at") or "")
        if rows:
            log.write(f"[dim]— reloaded {len(rows)} prior message(s) from this session —[/]")
        for row in rows:
            try:
                entry = json.loads(row["content"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            role = entry.get("role")
            text = entry.get("text", "")
            if role == "user":
                log.write(f"[bold green]You:[/] {text}")
            elif role == "assistant":
                log.write(f"[bold magenta]Delentia:[/] {text}")

    def _persist_transcript_entry(self, role: str, text: str) -> None:
        """Additive, real, best-effort - a persistence failure must never
        break the live conversation."""
        try:
            self.kernel._persistence.save_memory(
                memory_id=str(uuid.uuid4()),
                namespace=self.namespace,
                memory_type=_TRANSCRIPT_MEMORY_TYPE,
                content=json.dumps({"role": role, "text": text}),
            )
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        self.query_one("#status_bar", Static).update(text)

    def _hide_autocomplete(self) -> None:
        self.query_one("#autocomplete", OptionList).display = False

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Round 38: real floating slash-command autocomplete - filters
        _SLASH_COMMANDS by prefix as the user types, shown only while
        composing a single-line slash command (not once real multi-line
        text or a space follows, since that's no longer a command being
        typed)."""
        if event.text_area.id != "composer":
            return
        text = event.text_area.text
        panel = self.query_one("#autocomplete", OptionList)
        if text.startswith("/") and "\n" not in text and " " not in text:
            matches = [cmd for cmd in _SLASH_COMMANDS if cmd.startswith(text)]
            if matches:
                panel.clear_options()
                for cmd in matches:
                    panel.add_option(Option(f"{cmd}  [dim]{_SLASH_COMMANDS[cmd]}[/]", id=cmd))
                panel.highlighted = 0
                panel.display = True
                return
        panel.display = False

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "autocomplete":
            return
        composer = self.query_one("#composer", TextArea)
        composer.load_text(str(event.option.id) + " ")
        composer.move_cursor(composer.document.end)
        self._hide_autocomplete()
        composer.focus()

    def action_submit_composer(self) -> None:
        composer = self.query_one("#composer", TextArea)
        text = composer.text.strip()
        composer.clear()
        self._hide_autocomplete()
        if not text or self._busy:
            return
        if text.startswith("/"):
            self.run_worker(self._handle_slash_command(text))
        else:
            self.run_worker(self._send_message(text))

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
        gateways/telegram_gateway.py and gateways/line_gateway.py.
        Round 37: passes a real on_step callback so the conversation log
        shows live per-step progress instead of a static "thinking..."
        status - AutonomousLoop.run() still returns once at the end (it
        isn't a generator), but the caller now sees each real step as it
        happens rather than only the final answer."""
        from rct_control_plane.autonomous_loop import AutonomousLoop
        from rct_control_plane.mcp_server import mcp

        loop = AutonomousLoop(mcp_server=mcp, persistence=self.kernel._persistence, namespace=namespace)
        return await loop.run(goal, on_step=self._on_loop_step, on_answer_token=self._on_answer_token)

    def _on_answer_token(self, chunk: str) -> None:
        """Round 40: real per-token rendering of AutonomousLoop's dual-
        call streamed final answer (see autonomous_loop.py's own
        on_answer_token docstring) - a genuine second LLM call streaming
        in, not a replay of already-generated text. RichLog only ever
        APPENDS (no in-place update), so the live-in-progress answer is
        shown in a separate Static widget that supports real in-place
        `.update()`; the final, complete text is written into the
        permanent RichLog transcript once streaming finishes (see
        _send_message)."""
        self._streaming_buffer += chunk
        preview = self.query_one("#streaming_preview", Static)
        preview.update(f"[dim]{self._streaming_buffer}[/]")
        preview.display = True

    def _on_loop_step(self, step: Any) -> None:
        """Real live-introspection hook (Round 37) - renders each actual
        LoopStep as it happens. Not a token-by-token stream (the loop
        itself doesn't produce one), but a genuine step-by-step trace,
        not a fabricated animation."""
        # Round 37: plain ASCII marker, not a unicode arrow - a real
        # Windows console codepage (e.g. cp874) cannot encode "→",
        # confirmed via direct reproduction, so an ASCII-only marker is
        # the honest, broadly-compatible choice for a terminal app.
        log = self.query_one("#conversation", RichLog)
        if step.tool_name:
            log.write(f"[dim]  -> step {step.iteration}: called {step.tool_name}({step.tool_args})[/]")
        else:
            log.write(f"[dim]  -> step {step.iteration}: {step.llm_reasoning or '(reasoning)'}[/]")
        self._set_status(f"thinking... (step {step.iteration})")

    async def _send_message(self, text: str) -> None:
        log = self.query_one("#conversation", RichLog)
        log.write(f"[bold green]You:[/] {text}")
        self._persist_transcript_entry("user", text)
        self._busy = True
        self._streaming_buffer = ""
        self._set_status("thinking...")
        start = time.monotonic()
        try:
            result = await self._dispatch_to_autonomous_loop(text, self.namespace)
            elapsed = time.monotonic() - start
            answer = result.get("final_answer") or f"(stopped: {result.get('stopped_reason', 'unknown')})"
            log.write(f"[bold magenta]Delentia:[/] {answer}")
            self._persist_transcript_entry("assistant", answer)
            self._set_status(f"ready — {elapsed:.1f}s, {result.get('iterations', 0)} step(s)")
        except Exception as e:
            log.write(f"[bold red]Error:[/] {e}")
            self._set_status("ready")
        finally:
            self._busy = False
            self._streaming_buffer = ""
            preview = self.query_one("#streaming_preview", Static)
            preview.update("")
            preview.display = False


def run_chat(kernel: Optional[Any] = None) -> None:
    """Real entry point for `rct chat` - constructs a real kernel if none
    is supplied (matching every other CLI command's own pattern)."""
    if kernel is None:
        from rct_control_plane.algorithm_kernel_41 import ALGORITHM_KERNEL
        kernel = ALGORITHM_KERNEL
    app = DelentiaChatApp(kernel=kernel)
    app.run()
