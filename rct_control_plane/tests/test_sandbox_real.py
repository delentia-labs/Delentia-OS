"""
Real local-process sandbox tests — Round 21 Phase 2 Task 5.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.sandbox import run_sandboxed


def test_real_command_executes_and_returns_real_output():
    result = run_sandboxed("echo hello-from-sandbox")
    assert "hello-from-sandbox" in result.stdout
    assert result.exit_code == 0
    assert result.blocked_reason is None


def test_real_timeout_is_enforced():
    result = run_sandboxed("python -c \"import time; time.sleep(30)\"", timeout_seconds=1.0)
    assert result.timed_out is True


def test_denylisted_command_prefix_is_blocked_before_execution():
    result = run_sandboxed("rm -rf /")
    assert result.blocked_reason is not None
    assert result.exit_code is None  # never actually ran


def test_docker_backend_runs_real_command_or_honestly_reports_unavailable():
    from rct_control_plane.sandbox import _docker_available

    result = run_sandboxed("echo hello-from-docker", backend="docker")

    if _docker_available():
        assert "hello-from-docker" in result.stdout
        assert result.exit_code == 0
    else:
        assert result.blocked_reason == "docker not available on this host"
