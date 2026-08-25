"""
Unit Tests for Phase 1: Autonomous Multi-Agent Swarm Engine
Tests Thai Unicode Normalizer, Git Worktree Isolator, and Back-Edge Daemon.
"""

from rct_control_plane.thai_normalizer import normalize_thai_text, format_thai_terminal
from rct_control_plane.git_worktree_isolator import GitWorktreeIsolator
from rct_control_plane.autonomous_backedge_daemon import AutonomousBackEdgeDaemon


def test_thai_unicode_normalizer():
    # Test 1: Combining character reordering & cleanup
    raw_thai = "กิ่"  # Consonant + vowel + tone
    norm = normalize_thai_text(raw_thai)
    assert len(norm) > 0

    # Test 2: Terminal formatting
    lines = format_thai_terminal("ทดสอบข้อความภาษาไทยสำหรับ Delentia OS", width=20)
    assert len(lines) >= 1
    assert "ทดสอบ" in lines[0]


def test_git_worktree_isolator(tmp_path):
    isolator = GitWorktreeIsolator(repo_root=str(tmp_path))
    res = isolator.create_worktree("agent_researcher_01")
    assert res["success"] is True
    assert "agent_researcher_01" in res["agent_id"]

    active = isolator.list_active()
    assert "agent_researcher_01" in active

    removed = isolator.remove_worktree("agent_researcher_01")
    assert removed is True


def test_autonomous_backedge_daemon(tmp_path):
    daemon = AutonomousBackEdgeDaemon(data_dir=str(tmp_path))
    
    # 1. Execute safe step
    step1 = daemon.execute_autonomous_step("task_001", "Build web interface")
    assert step1["success"] is True

    # 2. Record a failure into an Invariant
    inv = daemon.record_backedge_failure(
        task_name="deploy_task",
        error_message="TypeError: Cannot read property of undefined",
        proposed_rule="FORBID_UNDEFINED_PROP_ACCESS"
    )
    assert inv["status"] == "ENFORCED"
    assert len(daemon.list_invariants()) == 1

    # 3. Pre-execution Invariant Block
    step2 = daemon.execute_autonomous_step("task_002", "Execute with FORBID_UNDEFINED_PROP_ACCESS")
    assert step2["success"] is False
    assert step2["status"] == "BLOCKED_BY_BACKEDGE_INVARIANT"
