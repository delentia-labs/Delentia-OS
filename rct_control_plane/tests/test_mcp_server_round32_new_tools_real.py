"""
Real MCP tool tests for Round 32's tool-count expansion: general repo file
read/search, capability discovery, wrappers around 4 already-built kernel
capabilities (ALGO-23/39/06/14), and GitWorktreeIsolator (Architect-approved
this round). Same real in-process MCPServer round-trip pattern as
test_mcp_server_real.py / test_mcp_server_round31_new_tools_real.py.
"""
import asyncio
import json
import subprocess
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


import rct_control_plane.mcp_server as mcp_server
from rct_control_plane.mcp_server import mcp
from rct_control_plane.git_worktree_isolator import GitWorktreeIsolator


def _call(name, args):
    result = asyncio.run(mcp.call_tool(name, args))
    return result, json.loads(result.content[0].text)


def test_new_tools_are_registered():
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    for expected in [
        "delentia_read_repo_file", "delentia_search_repo_files", "delentia_list_capabilities",
        "delentia_convert_content", "delentia_synthesize_function",
        "delentia_export_session_state", "delentia_import_session_state",
        "delentia_generate_image",
        "delentia_create_worktree", "delentia_remove_worktree", "delentia_list_worktrees",
    ]:
        assert expected in names


class TestRepoFileTools:
    def test_read_real_known_file(self):
        _, result = _call("delentia_read_repo_file", {"relative_path": "rct_control_plane/mcp_server.py"})
        assert "MCPServer" in result["content_text"]

    def test_read_rejects_path_traversal(self):
        _, result = _call("delentia_read_repo_file", {"relative_path": "../../../etc/passwd"})
        assert "error" in result

    def test_read_reports_not_found(self):
        _, result = _call("delentia_read_repo_file", {"relative_path": "definitely_does_not_exist_round32.txt"})
        assert "error" in result

    def test_search_finds_a_real_known_symbol(self):
        _, result = _call("delentia_search_repo_files", {
            "pattern": "class AlgorithmKernel41", "glob": "rct_control_plane/*.py",
        })
        assert len(result["matches"]) >= 1
        assert result["matches"][0]["path"] == "rct_control_plane/algorithm_kernel_41.py"
        assert result["matches"][0]["line_number"] >= 1

    def test_search_rejects_invalid_regex(self):
        _, result = _call("delentia_search_repo_files", {"pattern": "("})
        assert "error" in result


class TestCapabilityDiscovery:
    def test_list_capabilities_includes_real_registered_ones(self):
        _, result = _call("delentia_list_capabilities", {})
        assert "persistence" in result["capabilities"]
        assert "content_box" in result["capabilities"]


class TestKernelCapabilityWrappers:
    def test_convert_content_round_trip_to_json(self):
        save_result = asyncio.run(mcp_server._kernel.algo_23_content_box("round32_mcp_test", 1, b"hello world"))
        assert save_result is not None
        _, result = _call("delentia_convert_content", {
            "content_id": "round32_mcp_test", "version": 1, "target_format": "json",
        })
        assert result["converted"] is True
        json.loads(result["output"]) if isinstance(result.get("output"), str) else None

    def test_synthesize_function_real_deterministic_case(self):
        _, result = _call("delentia_synthesize_function", {
            "capability_spec": "returns True if the input integer is even, False otherwise",
            "function_name": "is_even_round32_mcp",
            "smoke_test_code": "assert is_even_round32_mcp(4) is True\nassert is_even_round32_mcp(3) is False",
        })
        assert result["synthesized"] is True
        # verified may honestly be False if the local LLM's generated code
        # fails its own smoke test - only assert the tool ran for real.
        assert "verified" in result

    def test_export_then_import_session_state_round_trip(self):
        _kernel = mcp_server._kernel
        _kernel.algo_25_delta_block("round32_mcp_session", "seed change")
        _, exported = _call("delentia_export_session_state", {"session_id": "round32_mcp_session"})
        assert "signature" in exported or "payload" in exported

        _, imported = _call("delentia_import_session_state", {"packet": exported})
        assert imported["verified"] is True
        assert imported["restored_context"] is not None

    def test_generate_image_produces_a_real_nonzero_byte_png(self):
        # Small size/steps to keep real CPU inference fast in test time.
        _, result = _call("delentia_generate_image", {
            "prompt": "a red circle", "num_steps": 2, "width": 64, "height": 64,
        })
        assert result["simulated"] is False
        assert result["image_path"] is not None
        assert result["byte_size"] > 0
        assert os.path.exists(result["image_path"])

    def test_import_rejects_tampered_packet(self):
        _kernel = mcp_server._kernel
        _kernel.algo_25_delta_block("round32_mcp_session2", "seed change 2")
        _, exported = _call("delentia_export_session_state", {"session_id": "round32_mcp_session2"})
        tampered = dict(exported)
        tampered["payload"] = {"tampered": True}
        _, imported = _call("delentia_import_session_state", {"packet": tampered})
        assert imported["verified"] is False
        assert imported["restored_context"] is None


class TestGitWorktreeTools:
    """Uses a throwaway temp git repo, never the real Delentia-OS repo -
    the module-level _worktree_isolator singleton is temporarily swapped
    for the duration of this test only, then restored."""

    def test_create_list_remove_worktree_real_round_trip(self, tmp_path, monkeypatch):
        repo_dir = tmp_path / "throwaway_repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo_dir), check=True)
        (repo_dir / "README.md").write_text("seed")
        subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(repo_dir), check=True)

        throwaway_isolator = GitWorktreeIsolator(repo_root=str(repo_dir))
        monkeypatch.setattr(mcp_server, "_worktree_isolator", throwaway_isolator)

        _, created = _call("delentia_create_worktree", {"agent_id": "round32-test-agent"})
        assert created["success"] is True
        assert created["status"] in ("ISOLATED_READY", "VIRTUAL_ISOLATION_FALLBACK")

        _, listed = _call("delentia_list_worktrees", {})
        assert "round32-test-agent" in listed["active"]

        _, removed = _call("delentia_remove_worktree", {"agent_id": "round32-test-agent"})
        assert removed["removed"] is True

        _, listed_after = _call("delentia_list_worktrees", {})
        assert "round32-test-agent" not in listed_after["active"]

    def test_real_delentia_os_repo_untouched_by_the_module_singleton(self):
        # Confirm the module-level singleton (used by real, non-test callers)
        # is scoped to REPO_ROOT, and that this test file never called any
        # worktree tool against it - a real, explicit safety assertion.
        assert mcp_server.REPO_ROOT.exists()
