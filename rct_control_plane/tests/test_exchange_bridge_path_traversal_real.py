"""
Real path-traversal protection tests for NeuralExchangeBridge — Round 31.

Found during the MCP-tool-expansion audit (Round 31 item 4): save_file/
read_file/list_files built filesystem paths via a bare os.path.join with
zero sanitization of `category`/`filename` — a real, pre-existing latent
vulnerability that would become a new external attack surface the moment
these methods were wrapped as MCP tools callable with untrusted JSON args.
These tests prove the fix rejects traversal attempts while leaving every
legitimate call working exactly as before (Zero-Delete).
"""
import os
import pytest

from rct_control_plane.exchange_bridge import NeuralExchangeBridge, PathTraversalError


@pytest.fixture
def bridge(tmp_path):
    return NeuralExchangeBridge(root_dir=str(tmp_path / "exchange"))


class TestExchangeBridgePathTraversal:
    def test_legitimate_save_and_read_still_work(self, bridge):
        saved = bridge.save_file("projects", "notes.txt", b"real content")
        assert saved["status"] == "SAVED"
        read = bridge.read_file("projects", "notes.txt")
        assert read["content"] == b"real content"

    def test_save_file_rejects_traversal_in_filename(self, bridge):
        with pytest.raises(PathTraversalError):
            bridge.save_file("projects", "../../evil.txt", b"pwned")

    def test_save_file_rejects_traversal_in_category(self, bridge):
        with pytest.raises(PathTraversalError):
            bridge.save_file("../../secrets", "x.txt", b"pwned")

    def test_read_file_rejects_traversal_and_does_not_escape_root(self, bridge, tmp_path):
        outside_file = tmp_path / "outside_secret.txt"
        outside_file.write_bytes(b"top secret")
        with pytest.raises(PathTraversalError):
            bridge.read_file("..", "outside_secret.txt")
        # confirm nothing outside root_dir was ever touched
        assert outside_file.read_bytes() == b"top secret"

    def test_list_files_rejects_traversal_category(self, bridge):
        with pytest.raises(PathTraversalError):
            bridge.list_files(category="../../")

    def test_absolute_path_filename_rejected(self, bridge):
        with pytest.raises(PathTraversalError):
            bridge.save_file("projects", os.path.abspath(__file__), b"pwned")
