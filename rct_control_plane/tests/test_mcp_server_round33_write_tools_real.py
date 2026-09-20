"""
Real tests for Round 33's write-capable repo file MCP tools
(delentia_write_repo_file, delentia_patch_repo_file) - higher blast
radius than Round 32's read-only tools, so these tests exercise both the
happy path and every safety guard (path traversal, blocklist, ambiguous
patch) against a real throwaway file under this repo, never a real
tracked source file.
"""
import asyncio
import json
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.mcp_server import mcp, REPO_ROOT

_SCRATCH_RELATIVE = "rct_control_plane/tests/_round33_write_tool_scratch.txt"
_SCRATCH_PATH = REPO_ROOT / _SCRATCH_RELATIVE


def _call(name, args):
    result = asyncio.run(mcp.call_tool(name, args))
    return result, json.loads(result.content[0].text)


def _cleanup():
    if _SCRATCH_PATH.exists():
        _SCRATCH_PATH.unlink()


class TestWriteRepoFile:
    def teardown_method(self):
        _cleanup()

    def test_write_then_read_round_trip(self):
        _, result = _call("delentia_write_repo_file", {
            "relative_path": _SCRATCH_RELATIVE, "content_text": "real scratch content",
        })
        assert result["written_bytes"] > 0
        assert _SCRATCH_PATH.read_text(encoding="utf-8") == "real scratch content"

    def test_write_rejects_path_traversal(self):
        _, result = _call("delentia_write_repo_file", {
            "relative_path": "../../../etc/evil.txt", "content_text": "pwned",
        })
        assert "error" in result

    def test_write_rejects_env_file(self):
        _, result = _call("delentia_write_repo_file", {
            "relative_path": ".env", "content_text": "SECRET=pwned",
        })
        assert "error" in result

    def test_write_rejects_secret_pattern(self):
        _, result = _call("delentia_write_repo_file", {
            "relative_path": "rct_control_plane/my_secret_file.py", "content_text": "x = 1",
        })
        assert "error" in result

    def test_write_rejects_git_internals(self):
        _, result = _call("delentia_write_repo_file", {
            "relative_path": ".git/hooks/pre-commit", "content_text": "#!/bin/sh\necho pwned",
        })
        assert "error" in result


class TestPatchRepoFile:
    def teardown_method(self):
        _cleanup()

    def test_patch_real_unique_text_succeeds(self):
        _SCRATCH_PATH.write_text("line one\nline two\nline three\n", encoding="utf-8")
        _, result = _call("delentia_patch_repo_file", {
            "relative_path": _SCRATCH_RELATIVE, "old_text": "line two", "new_text": "PATCHED LINE",
        })
        assert result["patched"] is True
        assert _SCRATCH_PATH.read_text(encoding="utf-8") == "line one\nPATCHED LINE\nline three\n"

    def test_patch_rejects_ambiguous_match(self):
        _SCRATCH_PATH.write_text("dup\ndup\n", encoding="utf-8")
        _, result = _call("delentia_patch_repo_file", {
            "relative_path": _SCRATCH_RELATIVE, "old_text": "dup", "new_text": "x",
        })
        assert "error" in result
        assert "ambiguous" in result["error"]

    def test_patch_rejects_missing_text(self):
        _SCRATCH_PATH.write_text("real content", encoding="utf-8")
        _, result = _call("delentia_patch_repo_file", {
            "relative_path": _SCRATCH_RELATIVE, "old_text": "not present anywhere", "new_text": "x",
        })
        assert "error" in result

    def test_patch_rejects_traversal(self):
        _, result = _call("delentia_patch_repo_file", {
            "relative_path": "../../../etc/passwd", "old_text": "root", "new_text": "pwned",
        })
        assert "error" in result

    def test_patch_rejects_blocked_path(self):
        _, result = _call("delentia_patch_repo_file", {
            "relative_path": "credentials.json", "old_text": "x", "new_text": "y",
        })
        assert "error" in result
