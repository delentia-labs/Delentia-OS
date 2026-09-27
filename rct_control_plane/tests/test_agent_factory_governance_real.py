"""
Round 48 R0.1: every agent entry point is governed, and chat gateways are
fail-closed on unknown senders.

Before this round, the 4 chat gateways, the scheduler's reminders, the TUI,
`delegate_to_profile`, the JITNA sub-agent runner and the
`delentia_autonomous_loop` MCP tool all built a plain AutonomousLoop,
skipping the FDIA gate, write/patch approval and JITNA signing that
GovernedAutonomousLoop adds.

GovernedAutonomousLoop is replaced by a recording fake so no LLM or heavy
kernel is involved, and `rct_control_plane.mcp_server` is stubbed where an
entry point would import it (importing the real one builds AlgorithmKernel41).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import pathlib
import re
import types

import pytest

import rct_control_plane.governed_autonomous_loop as governed_module
from rct_control_plane import agent_factory
from rct_control_plane.persistence import ControlPlanePersistence

CHANNELS = ("telegram", "discord", "slack", "line")


class _RecordingLoop:
    instances: list = []

    def __init__(self, mcp_server, persistence, kernel=None, max_iterations=5, max_seconds=120.0,
                 namespace="kernel_default", llm_provider=None, **_):
        self.mcp_server = mcp_server
        self.persistence = persistence
        self.kernel = kernel
        self.max_iterations = max_iterations
        self.namespace = namespace
        self.llm_provider = llm_provider
        _RecordingLoop.instances.append(self)

    async def run(self, goal, **_):
        return {"final_answer": f"governed:{goal}", "stopped_reason": "llm_finished", "iterations": 1}


class _FakeMee:
    def get_or_create(self, key):
        return key


@pytest.fixture
def kernel(tmp_path):
    k = types.SimpleNamespace()
    k._persistence = ControlPlanePersistence(db_path=str(tmp_path / "gov.db"))
    k._mee_engine = _FakeMee()
    return k


@pytest.fixture(autouse=True)
def _governed_fake_and_stub_mcp(monkeypatch, tmp_path):
    _RecordingLoop.instances = []
    monkeypatch.setattr(governed_module, "GovernedAutonomousLoop", _RecordingLoop)
    stub = types.ModuleType("rct_control_plane.mcp_server")
    stub.mcp = object()
    stub._kernel = types.SimpleNamespace(_persistence=None)
    monkeypatch.setitem(sys.modules, "rct_control_plane.mcp_server", stub)
    for ch in CHANNELS:
        monkeypatch.delenv(agent_factory.SENDER_ALLOWLIST_ENV[ch], raising=False)
    for var in ("DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
    return stub


def _audit_rows(kernel, entity_type):
    with kernel._persistence._connect() as conn:
        rows = conn.execute(
            "SELECT entity_type, actor FROM audit_trail WHERE entity_type = ?", (entity_type,)
        ).fetchall()
    return rows


# ---------------------------------------------------------------- allowlist

class TestSenderAllowlist:
    def test_unset_allowlist_rejects_everyone(self):
        for ch in CHANNELS:
            assert agent_factory.sender_allowed(ch, "123") is False

    def test_listed_sender_is_allowed_and_others_are_not(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_TELEGRAM_ALLOWED_SENDERS", " 111, 222 ")
        assert agent_factory.sender_allowed("telegram", 111) is True
        assert agent_factory.sender_allowed("telegram", "222") is True
        assert agent_factory.sender_allowed("telegram", 333) is False
        assert agent_factory.sender_allowed("telegram", None) is False

    def test_star_is_an_explicit_opt_in_to_everyone(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_SLACK_ALLOWED_SENDERS", "*")
        assert agent_factory.sender_allowed("slack", "U999") is True

    def test_blank_value_is_still_closed(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_DISCORD_ALLOWED_SENDERS", "  ,  ")
        assert agent_factory.sender_allowed("discord", "1") is False


# ------------------------------------------------------ gateways, end to end

def _telegram(kernel):
    from rct_control_plane.gateways.telegram_gateway import TelegramGateway
    gw = TelegramGateway(kernel=kernel, bot_token=None)
    update = {"message": {"chat": {"id": 42}, "from": {"id": 7}, "text": "delete the repo"}}
    return lambda: gw.handle_update(update), "7", "telegram-42"


def _discord(kernel):
    from rct_control_plane.gateways.discord_gateway import DiscordGateway
    gw = DiscordGateway(kernel=kernel, bot_token="fake")
    return (lambda: gw.handle_message(channel_id=5, author_id=7, author_is_bot=False,
                                      content="delete the repo")), "7", "discord-5-7"


def _slack(kernel):
    from rct_control_plane.gateways.slack_gateway import SlackGateway
    gw = SlackGateway(kernel=kernel, bot_token="fake", app_token="fake")
    return (lambda: gw.handle_message(channel_id="C1", user_id="7", bot_id=None,
                                      text="delete the repo")), "7", "slack-C1-7"


def _line(kernel):
    from rct_control_plane.gateways.line_gateway import LineGateway
    gw = LineGateway(kernel=kernel, channel_secret="s", channel_access_token=None)
    body = {"events": [{"type": "message", "message": {"type": "text", "text": "delete the repo"},
                        "source": {"userId": "7"}}]}
    return lambda: gw.handle_webhook_body(body), "7", "line-7"


GATEWAYS = {"telegram": _telegram, "discord": _discord, "slack": _slack, "line": _line}


@pytest.mark.parametrize("channel", CHANNELS)
def test_unknown_sender_never_starts_a_loop_and_is_audited(channel, kernel):
    call, sender, namespace = GATEWAYS[channel](kernel)
    result = asyncio.run(call())
    result = result[0] if isinstance(result, list) else result
    assert result["rejected"] is True
    assert _RecordingLoop.instances == []
    rows = _audit_rows(kernel, "gateway_sender_rejected")
    assert rows and rows[-1][1] == f"{channel}:{sender}"


@pytest.mark.parametrize("channel", CHANNELS)
def test_allowlisted_sender_runs_the_governed_loop(channel, kernel, monkeypatch):
    monkeypatch.setenv(agent_factory.SENDER_ALLOWLIST_ENV[channel], "7")
    call, _, namespace = GATEWAYS[channel](kernel)
    result = asyncio.run(call())
    result = result[0] if isinstance(result, list) else result
    assert result["result"]["final_answer"] == "governed:delete the repo"
    (loop,) = _RecordingLoop.instances
    assert loop.namespace == namespace
    assert loop.kernel is kernel  # governed against the gateway's own kernel


# --------------------------------------------------- other entry points

def test_scheduler_reminders_run_the_governed_loop(kernel):
    from rct_control_plane.scheduler import check_and_fire_due_reminders
    due = [{"id": "r1", "goal": "summarise the audit log", "namespace": "reminder-ns"}]
    kernel._persistence.get_due_reminders = lambda now, namespace=None: due
    fired = []
    kernel._persistence.mark_reminder_fired = fired.append
    results = asyncio.run(check_and_fire_due_reminders(kernel))
    assert results[0]["final_answer"] == "governed:summarise the audit log"
    assert fired == ["r1"]
    assert _RecordingLoop.instances[0].namespace == "reminder-ns"


def test_delegate_to_profile_runs_governed_with_profile_model(kernel):
    from rct_control_plane import model_config
    from rct_control_plane.agent_profile import delegate_to_profile
    model_config.save_model_selection("ollama", "llama3:8b", profile="researcher")

    result = asyncio.run(delegate_to_profile(kernel, "researcher", "find prior art", max_iterations=2))
    assert result["final_answer"] == "governed:find prior art"
    (loop,) = _RecordingLoop.instances
    assert loop.namespace == "profile:researcher"
    assert loop.max_iterations == 2
    assert loop.llm_provider is not None and loop.llm_provider.model == "llama3:8b"


def test_profile_without_override_keeps_default_resolution(kernel):
    from rct_control_plane.agent_profile import delegate_to_profile
    asyncio.run(delegate_to_profile(kernel, "plain", "x"))
    assert _RecordingLoop.instances[0].llm_provider is None


def test_build_governed_loop_uses_given_persistence_over_kernel(kernel, tmp_path):
    other = ControlPlanePersistence(db_path=str(tmp_path / "other.db"))
    loop = agent_factory.build_governed_loop(kernel, namespace="n", persistence=other, mcp_server="m")
    assert loop.persistence is other and loop.mcp_server == "m"


# ------------------------------------------------ no ungoverned entry left

def test_no_production_module_constructs_a_plain_autonomous_loop():
    """Regression guard: only autonomous_loop.py itself (the base class and
    its docs) may call AutonomousLoop(...). Every other entry point must go
    through agent_factory.build_governed_loop()."""
    root = pathlib.Path(__file__).resolve().parents[1]
    pattern = re.compile(r"(?<![A-Za-z_])AutonomousLoop\(")
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("tests/") or rel == "autonomous_loop.py" or "/worktrees/" in rel:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            code = line.split("#", 1)[0]
            if pattern.search(code) and "class " not in code and '"""' not in code:
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert offenders == [], "ungoverned AutonomousLoop construction:\n" + "\n".join(offenders)
