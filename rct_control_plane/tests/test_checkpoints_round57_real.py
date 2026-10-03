"""
Round 57: checkpoints (checkpoints.py) with real files on disk, real SQLite, the real MCP file tools and the real FastAPI app and CLI.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import hashlib
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
import rct_control_plane.mcp_server as mcp_server
from rct_control_plane import checkpoints as cps
from rct_control_plane.api import create_app
from rct_control_plane.checkpoints import CheckpointError, CheckpointStore
from rct_control_plane.cli import cli
from rct_control_plane.persistence import ControlPlanePersistence


class Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.delenv(cps.ENABLED_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))            # the checkpoint blobs of one test are not another's
    repo = tmp_path / "repo"
    repo.mkdir()
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "cp.db"))
    monkeypatch.setattr(mcp_server, "REPO_ROOT", repo)
    monkeypatch.setattr(mcp_server, "_kernel", Kernel(persistence))
    return repo, persistence, CheckpointStore(persistence, tmp_path / "blobs")


def sha_of_file(path):
    """The hash of the bytes actually on disk (Windows turns \n into \r\n when a text file is written, so a literal string would hash differently)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, text):
    return asyncio.run(mcp_server.delentia_write_repo_file(path, text))


def patch(path, old, new):
    return asyncio.run(mcp_server.delentia_patch_repo_file(path, old, new))


def test_a_write_over_an_existing_file_can_be_rolled_back_to_exactly_the_earlier_bytes(world):
    repo, persistence, _ = world
    (repo / "notes.md").write_text("version one\nline two\n", encoding="utf-8")
    original_bytes = (repo / "notes.md").read_bytes()
    result = write("notes.md", "version TWO\n")
    assert result["checkpoint"] and (repo / "notes.md").read_text(encoding="utf-8") == "version TWO\n"
    store = CheckpointStore(persistence)
    cp = store.get(result["checkpoint"])
    assert cp["existed_before"] == 1 and cp["tool"] == "delentia_write_repo_file" and cp["before_sha"] and cp["after_sha"] == sha_of_file(repo / "notes.md")
    assert "-version one" in store.diff(result["checkpoint"]) and "+version TWO" in store.diff(result["checkpoint"])
    out = store.rollback(result["checkpoint"])
    assert (repo / "notes.md").read_bytes() == original_bytes and "restored" in out["result"]


def test_a_patch_is_checkpointed_too(world):
    repo, persistence, _ = world
    (repo / "config.py").write_text("PORT = 8000\n", encoding="utf-8")
    result = patch("config.py", "8000", "8080")
    assert result["patched"] is True and result["checkpoint"]
    assert (repo / "config.py").read_text(encoding="utf-8") == "PORT = 8080\n"
    CheckpointStore(persistence).rollback(result["checkpoint"])
    assert (repo / "config.py").read_text(encoding="utf-8") == "PORT = 8000\n"


def test_a_file_the_agent_created_is_moved_out_of_the_way_on_rollback_and_its_content_is_kept(world):
    repo, persistence, _ = world
    result = write("docs/new.md", "created by the agent\n")
    store = CheckpointStore(persistence)
    assert store.get(result["checkpoint"])["existed_before"] == 0
    out = store.rollback(result["checkpoint"])
    assert not (repo / "docs" / "new.md").exists() and "removed the file the agent created" in out["result"]
    undo = store.get(out["undo_checkpoint"])                                  # nothing was lost: the content is held by the undo checkpoint
    assert undo["rollback_of"] == result["checkpoint"] and undo["before_sha"] == store.get(result["checkpoint"])["after_sha"]
    store.rollback(out["undo_checkpoint"])
    assert (repo / "docs" / "new.md").read_text(encoding="utf-8") == "created by the agent\n"      # the rollback itself was undone


def test_a_later_edit_by_a_person_is_never_overwritten_unless_forced(world):
    repo, persistence, _ = world
    (repo / "a.txt").write_text("original\n", encoding="utf-8")
    result = write("a.txt", "agent wrote this\n")
    (repo / "a.txt").write_text("agent wrote this\nplus my own careful edit\n", encoding="utf-8")
    edited_sha = sha_of_file(repo / "a.txt")
    store = CheckpointStore(persistence)
    with pytest.raises(CheckpointError, match="no longer holds what the agent wrote"):
        store.rollback(result["checkpoint"])
    assert "my own careful edit" in (repo / "a.txt").read_text(encoding="utf-8")
    out = store.rollback(result["checkpoint"], force=True)
    assert (repo / "a.txt").read_text(encoding="utf-8") == "original\n"
    assert store.get(out["undo_checkpoint"])["before_sha"] == edited_sha                  # the person's edit is kept


def test_a_checkpoint_is_rolled_back_once_and_only_from_intact_stored_content(world, tmp_path):
    repo, persistence, _ = world
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    result = write("a.txt", "two\n")
    store = CheckpointStore(persistence)
    store.rollback(result["checkpoint"])
    with pytest.raises(CheckpointError, match="already rolled back"):
        store.rollback(result["checkpoint"])
    with pytest.raises(CheckpointError, match="no checkpoint 999"):
        store.rollback(999)
    # a stored blob that was tampered with is refused, not restored
    (repo / "b.txt").write_text("keep me\n", encoding="utf-8")
    second = write("b.txt", "changed\n")
    blob_dir = CheckpointStore(persistence)._blobs
    blob = blob_dir / CheckpointStore(persistence).get(second["checkpoint"])["before_sha"]
    blob.write_bytes(b"something else entirely")
    with pytest.raises(CheckpointError, match="no longer matches its hash"):
        CheckpointStore(persistence).rollback(second["checkpoint"])
    assert (repo / "b.txt").read_text(encoding="utf-8") == "changed\n"


def test_identical_content_is_stored_once(world):
    repo, persistence, _ = world
    for name in ("x.txt", "y.txt", "z.txt"):
        (repo / name).write_text("same text\n", encoding="utf-8")
        write(name, f"new {name}\n")
    blobs = [f for f in CheckpointStore(persistence)._blobs.iterdir() if len(f.name) == 64]
    assert len(blobs) == 1


def test_a_file_over_the_size_limit_is_written_but_listed_as_unprotected(world, monkeypatch):
    repo, persistence, _ = world
    monkeypatch.setattr(cps, "MAX_FILE_BYTES", 100)
    (repo / "big.txt").write_text("x" * 500, encoding="utf-8")
    result = write("big.txt", "small now\n")
    store = CheckpointStore(persistence)
    cp = store.get(result["checkpoint"])
    assert cp["protected"] == 0 and "UNPROTECTED" in cp["note"] and (repo / "big.txt").read_text(encoding="utf-8") == "small now\n"
    with pytest.raises(CheckpointError, match="cannot be rolled back"):
        store.rollback(result["checkpoint"])
    assert store.status()["unprotected"] == 1


def test_switching_checkpoints_off_leaves_the_write_untouched(world, monkeypatch):
    repo, persistence, _ = world
    monkeypatch.setenv(cps.ENABLED_ENV, "0")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    result = write("a.txt", "two\n")
    assert "checkpoint" not in result and (repo / "a.txt").read_text(encoding="utf-8") == "two\n"
    assert CheckpointStore(persistence).list() == []


def test_a_checkpoint_problem_never_blocks_the_write_a_human_signed_for(world, monkeypatch):
    repo, _, _ = world
    monkeypatch.setattr(cps.CheckpointStore, "begin", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    result = write("a.txt", "still written\n")
    assert result["written_bytes"] and (repo / "a.txt").read_text(encoding="utf-8") == "still written\n" and "checkpoint" not in result


def test_blocked_and_escaping_paths_are_refused_before_any_checkpoint_exists(world):
    repo, persistence, _ = world
    assert "error" in write("../outside.txt", "x")
    assert "error" in write(".env", "SECRET=1")
    assert CheckpointStore(persistence).list() == []


def test_nothing_is_ever_deleted_by_the_runtime(world):
    repo, persistence, store = world
    for i in range(5):
        write("a.txt", f"version {i}\n")
    assert not hasattr(CheckpointStore, "prune")
    with sqlite3.connect(str(persistence.db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM repo_checkpoints").fetchone()[0] == 5


# ------------------------------------------------------------------ the Desk and the CLI

def test_the_desk_lists_diffs_and_rolls_back(world, monkeypatch):
    repo, persistence, _ = world
    monkeypatch.setattr(desk_api, "_kernel", lambda: Kernel(persistence))
    (repo / "notes.md").write_text("before\n", encoding="utf-8")
    cp = write("notes.md", "after\n")["checkpoint"]
    with TestClient(create_app()) as client:
        listing = client.get("/v1/desk/checkpoints").json()
        assert listing["checkpoints"][0]["id"] == cp and listing["status"]["checkpoints"] == 1 and len(listing["checkpoints"][0]["before_sha"]) == 16
        assert "-before" in client.get(f"/v1/desk/checkpoints/{cp}/diff").json()["diff"]
        assert client.get("/v1/desk/checkpoints/999/diff").status_code == 404
        (repo / "notes.md").write_text("after\nedited by a person\n", encoding="utf-8")
        refused = client.post(f"/v1/desk/checkpoints/{cp}/rollback", json={})
        assert refused.status_code == 409 and "no longer holds" in refused.json()["detail"]
        assert client.post(f"/v1/desk/checkpoints/{cp}/rollback", json={"force": True}).json()["result"].startswith("restored")
        assert (repo / "notes.md").read_text(encoding="utf-8") == "before\n"
        events = client.get("/v1/desk/governance/events", params={"category": "checkpoints"}).json()["events"]
        assert events and "rollback of notes.md" in events[0]["summary"] and "(forced)" in events[0]["summary"]


def test_the_cli_lists_diffs_rolls_back_and_reports_status(tmp_path, monkeypatch):
    from rct_control_plane.data_home import agentic_db_path
    for name in (cps.ENABLED_ENV,):
        monkeypatch.delenv(name, raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    persistence = ControlPlanePersistence(db_path=agentic_db_path())
    monkeypatch.setattr(mcp_server, "REPO_ROOT", repo)
    monkeypatch.setattr(mcp_server, "_kernel", Kernel(persistence))
    (repo / "notes.md").write_text("before\n", encoding="utf-8")
    cp = write("notes.md", "after\n")["checkpoint"]
    runner = CliRunner()
    assert "notes.md" in runner.invoke(cli, ["checkpoints", "list"]).output
    assert "+after" in runner.invoke(cli, ["checkpoints", "diff", str(cp)]).output
    rolled = runner.invoke(cli, ["checkpoints", "rollback", str(cp)])
    assert rolled.exit_code == 0 and "undo with" in rolled.output and (repo / "notes.md").read_text(encoding="utf-8") == "before\n"
    assert runner.invoke(cli, ["checkpoints", "rollback", str(cp)]).exit_code == 1
    assert '"checkpoints": 2' in runner.invoke(cli, ["checkpoints", "status"]).output
