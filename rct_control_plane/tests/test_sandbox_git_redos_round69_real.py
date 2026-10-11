"""
Round 69: CodeQL (py/redos, py/polynomial-redos) flagged the git rule of the shell floor: "git -c ! -c ! -c ..." backtracked exponentially. The option groups are now bounded and cannot be split in several ways.
Pinned: (1) the worst-case inputs cost about nothing, (2) the same commands are judged as before, plus one hole the rewrite exposed: `-c` / `-C` after another global option (`git --no-pager -c alias.x=!sh log`)
used to be judged safe although it can run a program.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import time

import pytest

from rct_control_plane import sandbox


@pytest.mark.parametrize("command", ["git " + "-c ! " * 3000 + "commit", "git " + "-c ! " * 3000, "git " + "-C -c " * 3000 + "x", "git " + "--a=b " * 3000 + "status", "git " + "-c " * 5000])
def test_hostile_git_command_lines_cost_next_to_nothing(command):
    started = time.perf_counter()
    sandbox._GIT_MUTATING_PATTERN.match(command)
    sandbox.classify_command_risk(command)
    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize("command,expected", [
    ("git status", "safe"), ("git log -p", "safe"), ("git diff HEAD~1", "safe"), ("git branch --list", "safe"), ("git --no-pager log", "safe"), ("git show --stat", "safe"),
    ("git --no-pager commit -m x", "needs_approval"), ("git commit -m x", "needs_approval"), ("git push", "needs_approval"), ("git -c core.pager=sh log", "needs_approval"),
    ("git -C /tmp status", "needs_approval"), ("git branch newname", "needs_approval"), ("git --git-dir=x add .", "needs_approval"), ("git -c a=b -c c=d commit", "needs_approval"),
    ("git --no-pager -c core.pager=sh log", "needs_approval"), ("git --no-pager -c alias.log=!sh log", "needs_approval"), ("git --no-pager -C other status", "needs_approval"),
    ("git -p log", "needs_approval"),
])
def test_git_commands_are_judged_as_before_and_a_later_global_c_is_no_longer_safe(command, expected):
    assert sandbox.classify_command_risk(command) == expected
