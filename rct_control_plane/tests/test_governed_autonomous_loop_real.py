"""
Round 44 item J.4.1: unit-level tests for GovernedAutonomousLoop's
governance-hook wiring - the ONE place this session's "real, not mocked"
discipline accepts mocking (see governed_autonomous_loop.py's own module
docstring and the Round 44 plan doc's J.4.1). What's mocked here is the
LLM decision (decide_next_action, same monkeypatch pattern already
established in test_autonomous_loop_on_step_callback_real.py) and, for
most tests, a fake AlgorithmKernel41 stand-in - because these tests verify
"is governance-hook logic called at the right time with the right data",
not "does the model answer correctly" or "is the FDIA formula correct".
The formula itself IS verified for real in TestFdiaScoreMatchesKernel
below, which uses the genuine AlgorithmKernel41.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.governed_autonomous_loop import (
    GovernedAutonomousLoop, RISKY_TOOLS, fdia_score, _write_path_is_safe,
)
from rct_control_plane.persistence import ControlPlanePersistence


class _FakeToolResult:
    def __init__(self, text: str):
        self.content = [type("C", (), {"text": text})()]


class _FakeMCP:
    def __init__(self):
        self.dispatched = []

    async def list_tools(self):
        return [
            type("T", (), {"name": "delentia_write_repo_file", "description": "write a file to the repo", "input_schema": {}})(),
            type("T", (), {"name": "delentia_run_sandboxed_command", "description": "run a shell command in a sandbox", "input_schema": {}})(),
            type("T", (), {"name": "delentia_recall", "description": "recall a memory", "input_schema": {}})(),
        ]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        return _FakeToolResult('{"ok": true}')


class _FakeKernel:
    """Deterministic stand-in for AlgorithmKernel41 - only the 2 methods
    GovernedAutonomousLoop actually calls."""

    def __init__(self, D=1.0, I=1.0):
        self.D, self.I = D, I
        self.synthesize_calls = 0
        self.rct7_calls = 0

    def synthesize_fdia_inputs(self, intent_text):
        self.synthesize_calls += 1
        return self.D, self.I, None

    def algo_04_rct7(self, intent):
        self.rct7_calls += 1
        return [f"Step {i} for {intent[:10]}" for i in range(1, 8)]


def _scripted_decide(sequence):
    """Returns a decide_next_action replacement that yields each dict in
    sequence in order, then repeats 'finish' forever (safety net)."""
    calls = {"n": 0}

    async def _fake(goal, history, available_tools, llm_provider=None):
        i = calls["n"]
        calls["n"] += 1
        if i < len(sequence):
            return sequence[i]
        return {"action": "finish", "reasoning": "done", "final_answer": "done",
                "tool_name": None, "tool_args": {}}
    return _fake, calls


_FINISH_ONLY = [
    {"action": "finish", "reasoning": "done", "final_answer": "done", "tool_name": None, "tool_args": {}},
]


@pytest.fixture
def decide_sequence(monkeypatch):
    """Call decide_sequence([...]) at the top of a test body to script
    decide_next_action's return values in order (repeats a trailing
    'finish' once the scripted sequence is exhausted)."""
    def _apply(sequence):
        fake, calls = _scripted_decide(sequence)
        monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
        return calls
    return _apply


def _loop(tmp_path, name, kernel=None, mcp=None):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / f"{name}.db"))
    return GovernedAutonomousLoop(
        mcp_server=mcp or _FakeMCP(), persistence=persistence,
        kernel=kernel or _FakeKernel(), max_iterations=5, namespace=name,
    )


class TestEpisodeStartHook:
    def test_rct7_and_synthesize_called_exactly_once_per_episode(self, tmp_path, decide_sequence):
        decide_sequence([
            {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {}, "reasoning": "r1", "final_answer": None},
            {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {}, "reasoning": "r2", "final_answer": None},
            {"action": "finish", "reasoning": "done", "final_answer": "done", "tool_name": None, "tool_args": {}},
        ])
        kernel = _FakeKernel()
        loop = _loop(tmp_path, "episode_start", kernel=kernel)
        asyncio.run(loop.run("do a multi-step thing"))

        assert kernel.synthesize_calls == 1, "must run once at episode start, not once per iteration"
        assert kernel.rct7_calls == 1

    def test_jitna_packet_is_signed_and_verified_at_episode_start(self, tmp_path, decide_sequence):
        decide_sequence(_FINISH_ONLY)
        kernel = _FakeKernel()
        loop = _loop(tmp_path, "jitna_start", kernel=kernel)
        asyncio.run(loop.run("a real goal"))

        assert loop._episode_jitna_verified is True
        assert len(loop._episode_rct7_steps) == 7


class TestFdiaGate:
    def test_safe_sandboxed_command_is_not_blocked(self, tmp_path, decide_sequence):
        decide_sequence([
            {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command",
             "tool_args": {"command": "ls -la"}, "reasoning": "list files", "final_answer": None},
            {"action": "finish", "reasoning": "done", "final_answer": "done", "tool_name": None, "tool_args": {}},
        ])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "safe_cmd", mcp=mcp)
        result = asyncio.run(loop.run("list files safely"))

        assert result["stopped_reason"] == "llm_finished"
        assert ("delentia_run_sandboxed_command", {"command": "ls -la"}) in mcp.dispatched

    def test_denied_sandboxed_command_is_blocked_by_fdia_not_by_the_base_gate(self, tmp_path, decide_sequence):
        # Round 44 finding: AutonomousLoop's OWN existing gate only checks
        # risk == "needs_approval", never "denied" - a denied command falls
        # through to real dispatch there (unchanged, see autonomous_loop.py).
        # This proves GovernedAutonomousLoop's FDIA gate closes that gap.
        decide_sequence([
            {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command",
             "tool_args": {"command": "rm -rf /"}, "reasoning": "dangerous", "final_answer": None},
        ])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "denied_cmd", mcp=mcp)
        result = asyncio.run(loop.run("do something dangerous"))

        assert result["stopped_reason"] == "fdia_blocked"
        assert mcp.dispatched == [], "the denied command must never actually be dispatched"
        assert result["steps"][-1]["tool_result"]["fdia_blocked"] is True

    def test_safe_repo_write_path_is_not_blocked(self, tmp_path, decide_sequence):
        decide_sequence([
            {"action": "call_tool", "tool_name": "delentia_write_repo_file",
             "tool_args": {"relative_path": "workspace_output/note.txt", "content_text": "hi"},
             "reasoning": "write a note", "final_answer": None},
            {"action": "finish", "reasoning": "done", "final_answer": "done", "tool_name": None, "tool_args": {}},
        ])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "safe_write", mcp=mcp)
        result = asyncio.run(loop.run("write a scratch note"))

        assert result["stopped_reason"] == "llm_finished"
        assert len(mcp.dispatched) == 1

    def test_blocked_repo_write_path_is_blocked_by_fdia(self, tmp_path, decide_sequence):
        decide_sequence([
            {"action": "call_tool", "tool_name": "delentia_write_repo_file",
             "tool_args": {"relative_path": ".env", "content_text": "SECRET=1"},
             "reasoning": "write env", "final_answer": None},
        ])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "blocked_write", mcp=mcp)
        result = asyncio.run(loop.run("overwrite the env file"))

        assert result["stopped_reason"] == "fdia_blocked"
        assert mcp.dispatched == []

    def test_non_risky_tool_bypasses_the_gate_entirely(self, tmp_path, decide_sequence):
        decide_sequence([
            {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "x"},
             "reasoning": "recall", "final_answer": None},
            {"action": "finish", "reasoning": "done", "final_answer": "done", "tool_name": None, "tool_args": {}},
        ])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "non_risky", mcp=mcp)
        result = asyncio.run(loop.run("recall something"))

        assert result["stopped_reason"] == "llm_finished"
        assert ("delentia_recall", {"query": "x"}) in mcp.dispatched

    def test_low_D_I_can_block_a_risky_tool_even_with_full_authorization(self, tmp_path, decide_sequence):
        # A defaults to 1.0 for tools without a per-tool signal, but F is
        # still driven by the real episode D/I - drive D low enough that
        # F collapses to 0 even at A=1.0 (0.01 ** 10 rounds to 0.0000,
        # which rounds to 0.0 at fdia_score's 4-decimal precision).
        kernel = _FakeKernel(D=0.01, I=10.0)
        decide_sequence([
            {"action": "call_tool", "tool_name": "delentia_crawl_url",
             "tool_args": {"url": "https://example.com"}, "reasoning": "crawl", "final_answer": None},
        ])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "low_di", kernel=kernel, mcp=mcp)
        # delentia_crawl_url isn't in _FakeMCP's tool list, but the gate
        # runs before dispatch regardless of whether list_tools() knows
        # about it, so this still exercises the gate correctly.
        result = asyncio.run(loop.run("crawl an arbitrary url"))
        assert result["stopped_reason"] == "fdia_blocked"


class TestToolFilter:
    def test_filters_to_keyword_overlapping_tools_when_enough_overlap_exists(self, tmp_path):
        loop = _loop(tmp_path, "filter_overlap")
        tools = [
            {"name": "delentia_write_repo_file", "description": "write a file to the repository"},
            {"name": "delentia_crawl_url", "description": "crawl a web page url"},
            {"name": "delentia_recall", "description": "recall a stored memory"},
        ]
        filtered = loop._tool_filter("write a file called notes.txt to the repository", tools)
        names = {t["name"] for t in filtered}
        assert "delentia_write_repo_file" in names

    def test_falls_back_to_full_menu_when_too_few_tools_overlap(self, tmp_path):
        loop = _loop(tmp_path, "filter_fallback")
        tools = [
            {"name": "delentia_write_repo_file", "description": "write a file to the repository"},
        ]
        filtered = loop._tool_filter("zzz qqq xyzzy plugh", tools)
        assert filtered == tools  # fewer than 2 would survive -> fallback to full menu


class TestEpisodeEndHook:
    def test_delta_block_is_persisted_exactly_once_per_episode(self, tmp_path, decide_sequence):
        decide_sequence(_FINISH_ONLY)
        loop = _loop(tmp_path, "delta_end")
        stats_before = loop._delta_engine.get_stats()
        asyncio.run(loop.run("a real goal"))
        stats_after = loop._delta_engine.get_stats()

        assert stats_after["total_deltas"] == stats_before["total_deltas"] + 1


class TestFdiaScoreMatchesKernel:
    """Real characterization test (no mocking) - proves fdia_score()'s
    local copy of the formula stays byte-for-byte identical to
    AlgorithmKernel41.algo_01_fdia. If this ever fails, the two have
    drifted and fdia_score() must be updated to match (see
    governed_autonomous_loop.py's module docstring point 4)."""

    @pytest.mark.parametrize("D,I,A", [
        (1.0, 1.0, 1.0), (0.5, 2.0, 1.0), (0.01, 10.0, 1.0),
        (100.0, 0.01, 0.5), (1.0, 1.0, 0.0), (2.5, 3.7, 0.83),
    ])
    def test_matches_real_kernel_for_varied_inputs(self, D, I, A):
        from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
        kernel = AlgorithmKernel41()
        assert fdia_score(D, I, A) == kernel.algo_01_fdia(D, I, A)


class TestRiskyToolAllowlist:
    def test_sandboxed_command_and_repo_writes_are_risky(self):
        assert "delentia_run_sandboxed_command" in RISKY_TOOLS
        assert "delentia_write_repo_file" in RISKY_TOOLS
        assert "delentia_patch_repo_file" in RISKY_TOOLS

    def test_pure_reads_are_not_risky(self):
        assert "delentia_recall" not in RISKY_TOOLS
        assert "delentia_query_audit_log" not in RISKY_TOOLS
        assert "delentia_list_capabilities" not in RISKY_TOOLS


class TestWritePathSafety:
    def test_repo_relative_path_is_safe(self):
        assert _write_path_is_safe("rct_control_plane/foo.py") is True

    def test_env_file_is_blocked(self):
        assert _write_path_is_safe(".env") is False
        assert _write_path_is_safe("config/.env.production") is False

    def test_secret_pattern_is_blocked(self):
        assert _write_path_is_safe("my_secret_key.txt") is False

    def test_credentials_json_is_blocked(self):
        assert _write_path_is_safe("app/credentials.json") is False

    def test_path_traversal_is_blocked(self):
        assert _write_path_is_safe("../../etc/passwd") is False

    def test_git_internals_are_blocked(self):
        assert _write_path_is_safe(".git/config") is False

    def test_empty_path_is_blocked(self):
        assert _write_path_is_safe("") is False
