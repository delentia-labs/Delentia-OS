"""
Round 84, DAAES TC-010 beyond the approval: an agent EPISODE is killed for real (the process is terminated, not interrupted by an exception) and a NEW process continues it.

The independent witness is the receipts file the "side-effect" tool appends to on disk: the parent reads what really happened, not what the agent says. Four kill points:
  read tool running        the process dies inside a read-only tool: continue without asking
  before an effect         dies inside a tool that changes something, before it changed anything: a person must say to go on
  after an effect          dies inside it AFTER the change (the receipt is on disk) but before the result was recorded: same, and the continuation must not do it again
  between two steps        dies while the model is deciding, every tool call finished: continue without asking, nothing unknown
In all four the final receipts are exactly order-1, order-2, order-3 once each.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import subprocess
import time
from pathlib import Path

import pytest

from rct_control_plane import episode_journal
from rct_control_plane.persistence import ControlPlanePersistence

ROOT = Path(__file__).resolve().parents[2]


def child(mode, home, world, *extra, timeout=240):
    env = {**os.environ, "DELENTIA_HOME": str(home), "PYTHONIOENCODING": "utf-8", "DELENTIA_MEMORY_EMBED": "off", "DELENTIA_MEMORY_KEYS_DIR": str(Path(home) / "memkeys")}
    for name in ("DELENTIA_FDIA_POLICY", "DELENTIA_APPROVER_PUBKEYS", "DELENTIA_EPISODE_JOURNAL"):
        env.pop(name, None)
    cmd = [sys.executable, "-m", "research.daaes.episode_child", mode, "--home", str(home), "--world", str(world), *extra]
    return subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")


def result_line(proc, timeout=240):
    out, err = proc.communicate(timeout=timeout)
    for line in out.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    raise AssertionError(f"no result from the child (exit {proc.returncode}):\n{out[-800:]}\n{err[-800:]}")


def kill_at(tmp_path, *args):
    home, world = tmp_path / "home", tmp_path / "world"
    proc = child("run", home, world, *args)
    flag = world / "hang.flag"
    deadline = time.time() + 180
    while not flag.exists():
        assert proc.poll() is None, f"the child ended before reaching the kill point: {proc.communicate()}"
        assert time.time() < deadline, "the child never reached the kill point"
        time.sleep(0.2)
    proc.kill()                                                       # TerminateProcess: no cleanup, no atexit, nothing after the hang line runs
    proc.wait(timeout=30)
    persistence = ControlPlanePersistence(db_path=str(home / "agentic.db"))
    os.environ["DELENTIA_MEMORY_KEYS_DIR"] = str(home / "memkeys")
    journal = episode_journal.EpisodeJournal(persistence)
    cut = journal.interrupted("alice")
    assert len(cut) == 1, "the killed episode must be the one interrupted episode"
    return home, world, cut[0], journal


def effects(world):
    path = Path(world) / "receipts.jsonl"
    return [json.loads(line)["op"] for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


@pytest.fixture(autouse=True)
def keep_env(monkeypatch):
    monkeypatch.setenv("DELENTIA_MEMORY_KEYS_DIR", os.environ.get("DELENTIA_MEMORY_KEYS_DIR", ""))


def test_killed_inside_a_read_only_tool_the_next_process_continues_without_asking(tmp_path):
    home, world, ep, journal = kill_at(tmp_path, "--hang-at", "1")
    assert [s.state for s in ep.steps] == ["dangling"] and not ep.ended and not ep.resumed_by
    out = result_line(child("resume", home, world, "--episode-id", ep.episode_id))
    assert out["resumed"] is True and out["stopped_reason"] == "llm_finished"
    assert effects(world) == ["order-1.txt", "order-2.txt", "order-3.txt"]
    assert journal.load(ep.episode_id).resumed_by and journal.interrupted("alice") == []


def test_killed_before_an_effect_a_person_must_say_to_go_on_and_then_it_is_done_once(tmp_path):
    home, world, ep, journal = kill_at(tmp_path, "--hang-at", "3")           # read, save 1, then save 2 dies BEFORE writing its receipt
    assert effects(world) == ["order-1.txt"]
    refused = result_line(child("resume", home, world, "--episode-id", ep.episode_id))
    assert refused["resumed"] is False and "unknown outcome" in refused["reason"] and effects(world) == ["order-1.txt"], "nothing may run on its own"
    assert journal.load(ep.episode_id).resumed_by is None, "a refusal does not use up the resume"
    done = result_line(child("resume", home, world, "--episode-id", ep.episode_id, "--allow-unknown"))
    assert done["resumed"] is True
    assert effects(world) == ["order-1.txt", "order-2.txt", "order-3.txt"]


def test_killed_after_an_effect_the_receipt_is_on_disk_and_the_continuation_does_not_do_it_again(tmp_path):
    home, world, ep, journal = kill_at(tmp_path, "--hang-at", "3", "--after-effect")
    assert effects(world) == ["order-1.txt", "order-2.txt"], "the change really happened; the agent never recorded that it did"
    assert [s.state for s in ep.steps] == ["done", "done", "dangling"]
    refused = result_line(child("resume", home, world, "--episode-id", ep.episode_id))
    assert refused["resumed"] is False
    assert [u["tool"] for u in refused["unknown"]] == ["delentia_save_exchange_file"]
    done = result_line(child("resume", home, world, "--episode-id", ep.episode_id, "--allow-unknown"))
    assert done["resumed"] is True
    assert effects(world) == ["order-1.txt", "order-2.txt", "order-3.txt"], "each order exactly once"


def test_killed_between_two_steps_every_tool_call_is_known_and_the_continuation_needs_no_permission(tmp_path):
    home, world, ep, journal = kill_at(tmp_path, "--hang-before-decision", "4")   # read, save 1, save 2 finished; the model is deciding about save 3
    assert effects(world) == ["order-1.txt", "order-2.txt"] and [s.state for s in ep.steps] == ["done", "done", "done"]
    out = result_line(child("resume", home, world, "--episode-id", ep.episode_id))
    assert out["resumed"] is True and effects(world) == ["order-1.txt", "order-2.txt", "order-3.txt"]


def test_two_continuations_at_once_only_one_wins(tmp_path):
    home, world, ep, journal = kill_at(tmp_path, "--hang-before-decision", "4")
    a = child("resume", home, world, "--episode-id", ep.episode_id)
    b = child("resume", home, world, "--episode-id", ep.episode_id)
    ra, rb = result_line(a), result_line(b)
    assert sorted([ra["resumed"], rb["resumed"]]) == [False, True], (ra, rb)
    assert effects(world) == ["order-1.txt", "order-2.txt", "order-3.txt"], "and the one effect was done once"
