"""
Round 59: resource ceilings for the local shell sandbox (resource_limits.py).

Real processes: a command that tries to take more memory than the ceiling is stopped by the operating system (a Job Object on Windows, RLIMIT_AS elsewhere); on Windows a fork bomb
hits the process ceiling and whatever a command leaves running dies with its job. This is not a jail and the tests do not claim it is: a command can still read the user's files.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import subprocess
import time

import pytest

from rct_control_plane import resource_limits, sandbox

IS_WINDOWS = sys.platform == "win32"
PY = sys.executable.replace("\\", "/")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sandbox, "_SANDBOX_SCRATCH_DIR", str(tmp_path / "scratch"))
    for name in (resource_limits.MEM_ENV, resource_limits.PROCS_ENV, "DELENTIA_SANDBOX_BACKEND"):
        monkeypatch.delenv(name, raising=False)


def py(code):
    return f'"{PY}" -c "{code}"'


def test_ordinary_commands_still_work_under_the_limits():
    r = sandbox.run_sandboxed("echo hello")
    assert r.exit_code == 0 and "hello" in r.stdout
    r = sandbox.run_sandboxed(py("print(sum(range(1000)))"))
    assert r.exit_code == 0 and r.stdout.strip() == "499500"


def hog(mb, touch=True):
    """A command that allocates `mb` megabytes and prints 'allocated' only if it got them. PowerShell on Windows: a Microsoft Store python.exe started by cmd.exe is launched outside the
    job by the Store's alias mechanism (measured), so it would not show the limit working; every other program started by the shell is in the job."""
    if IS_WINDOWS:
        return f"powershell -NoProfile -Command \"$ErrorActionPreference = 'Stop'; $b = New-Object byte[] ({mb}MB); $b[0] = 1; Write-Output allocated\""
    return py(f"x = bytearray({mb} * 1024 * 1024); print('allocated')")


def test_a_command_that_takes_more_memory_than_the_ceiling_is_stopped(monkeypatch):
    monkeypatch.setenv(resource_limits.MEM_ENV, "512")
    r = sandbox.run_sandboxed(hog(1500), timeout_seconds=60, approved=True)
    assert r.blocked_reason is None, r.blocked_reason
    assert "allocated" not in r.stdout and r.exit_code != 0, (r.exit_code, r.stdout[:100], r.stderr[-200:])


def test_the_same_allocation_succeeds_with_the_limit_off(monkeypatch):
    monkeypatch.setenv(resource_limits.MEM_ENV, "0")
    r = sandbox.run_sandboxed(hog(300), timeout_seconds=60, approved=True)
    assert r.blocked_reason is None, r.blocked_reason
    assert r.exit_code == 0 and "allocated" in r.stdout, (r.exit_code, r.stdout[:100], r.stderr[-200:])


def test_the_limits_come_from_the_owners_environment_and_junk_falls_back(monkeypatch):
    assert resource_limits.limits() == {"mem_mb": 2048, "max_procs": 64}
    monkeypatch.setenv(resource_limits.MEM_ENV, "128")
    monkeypatch.setenv(resource_limits.PROCS_ENV, "7")
    assert resource_limits.limits() == {"mem_mb": 128, "max_procs": 7}
    monkeypatch.setenv(resource_limits.MEM_ENV, "lots")
    monkeypatch.setenv(resource_limits.PROCS_ENV, "-5")
    assert resource_limits.limits() == {"mem_mb": 2048, "max_procs": 0}


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows Job Objects")
class TestWindowsJob:
    def test_a_fork_bomb_hits_the_process_ceiling(self, monkeypatch):
        monkeypatch.setenv(resource_limits.PROCS_ENV, "6")
        ps = ("$n = 0; 1..30 | ForEach-Object { try { Start-Process -FilePath ping -ArgumentList '-n','25','127.0.0.1' -WindowStyle Hidden -ErrorAction Stop; $n++ } catch { } }; "
              "Write-Output ('started ' + $n)")
        r = sandbox.run_sandboxed(f'powershell -NoProfile -Command "{ps}"', timeout_seconds=60, approved=True)
        assert "started" in r.stdout, (r.stdout, r.stderr[-300:])
        started = int(r.stdout.split("started")[-1].strip())
        assert 0 <= started < 30, started                                       # it could not start all of them

    @staticmethod
    def leftover_count(tag):
        """How many `ping -n <tag>` processes are alive (a leftover with a recognisable command line)."""
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"@(Get-CimInstance Win32_Process -Filter \"Name='PING.EXE'\" | Where-Object {{ $_.CommandLine -match '-n {tag} ' }}).Count"],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return int(out or 0)

    @staticmethod
    def kill_leftovers(tag):
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Get-CimInstance Win32_Process -Filter \"Name='PING.EXE'\" | Where-Object {{ $_.CommandLine -match '-n {tag} ' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"],
                       capture_output=True, timeout=60)

    def launch_leftover(self, tag):
        ps = f"Start-Process -FilePath ping -ArgumentList '-n','{tag}','127.0.0.1' -WindowStyle Hidden; Write-Output launched"
        r = sandbox.run_sandboxed(f'powershell -NoProfile -Command "{ps}"', timeout_seconds=30, approved=True)
        assert "launched" in r.stdout, (r.stdout, r.stderr[-300:])

    def test_what_a_command_leaves_running_dies_with_its_job(self):
        self.launch_leftover(61)
        time.sleep(2)
        try:
            assert self.leftover_count(61) == 0                              # the leftover was killed when the job closed
        finally:
            self.kill_leftovers(61)

    def test_without_the_job_the_same_leftover_survives(self, monkeypatch):
        """The control for the test above: with the job switched off the leftover is still running, so the previous test really measures the job."""
        monkeypatch.setattr(resource_limits, "windows_job", lambda: None)
        self.launch_leftover(62)
        time.sleep(2)
        try:
            assert self.leftover_count(62) == 1
        finally:
            self.kill_leftovers(62)


@pytest.mark.skipif(IS_WINDOWS, reason="POSIX resource limits")
class TestPosix:
    def test_the_children_get_their_own_session_and_the_limits(self):
        r = sandbox.run_sandboxed(py("import os, resource; print(os.getsid(0) == os.getpid(), resource.getrlimit(resource.RLIMIT_CORE)[0], resource.getrlimit(resource.RLIMIT_AS)[0])"))
        assert r.exit_code == 0
        is_leader, core, address_space = r.stdout.split()
        assert is_leader == "True" and core == "0" and int(address_space) == 2048 * 1024 * 1024

    def test_a_file_bigger_than_the_ceiling_cannot_be_written(self, monkeypatch):
        r = sandbox.run_sandboxed(py("open('big.bin', 'wb').write(b'0' * (600 * 1024 * 1024))"), timeout_seconds=60)
        assert r.exit_code != 0


def test_the_job_helpers_are_harmless_where_they_do_not_apply():
    if not IS_WINDOWS:
        assert resource_limits.windows_job() is None
    resource_limits.close_job(None)
    assert resource_limits.assign_to_job(None, subprocess.Popen([sys.executable, "-c", "pass"])) is False
