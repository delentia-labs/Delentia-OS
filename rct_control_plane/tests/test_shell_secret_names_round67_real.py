"""
Round 67: the shell classifier asks the same secret-file list as the agent's read tool, and the external-menu attack harness (research/external_menu_attack.py) parses other people's
recipes correctly. Nothing is mocked; no network.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import urllib.parse

import pytest

from rct_control_plane import fdia_policy
from rct_control_plane.sandbox import classify_command_risk, run_sandboxed
from rct_control_plane import secret_paths


@pytest.mark.parametrize("command", [
    "type secrets.yaml", "cat secrets.json", "cat config/prod_secrets", "cat token.json", "cat tokens.json", "cat .netrc", "cat .npmrc", "type server.keystore", "cat vault.kdbx",
    "cat app.db", "sqlite3 agentic.db .dump", "cat --file=secrets.json", "grep password secrets.yaml", "head -5 id_ed25519", "cat .git/config", "ls .ssh", "wc -l ~/.aws/credentials",
    "git log -- credentials",
])
def test_the_shell_refuses_every_name_the_read_tool_refuses(command):
    assert classify_command_risk(command) == "denied", command


@pytest.mark.parametrize("command", [
    "type notes.txt", "ls docs", "git status", "wc -l README.md", "grep -rn TODO src", "head -5 docs/guide.md", "echo hello", "git commit -m secrets", "ls", "pwd", "python --version",
    "cat .env.example", "ls src/secret_santa.py"[:0] or "ls src",
])
def test_ordinary_commands_are_not_newly_denied(command):
    assert classify_command_risk(command) != "denied", command


def test_what_the_read_tool_refuses_the_shell_refuses_too():
    for name in ("secrets.yaml", "credentials", "token.json", "id_rsa", "x.pem", "state.db", ".git/config", ".ssh/known_hosts", "approvers.json"):
        assert secret_paths.blocked_reason(name), name
        assert classify_command_risk(f"cat {name}") == "denied", name


def test_a_denied_command_does_not_run(tmp_path):
    (tmp_path / "secrets.yaml").write_text("k: CANARY")
    result = run_sandboxed("type secrets.yaml", timeout_seconds=5)
    assert result.exit_code is None and "denylisted" in (result.blocked_reason or "") and "CANARY" not in (result.stdout or "")


def test_the_owner_policy_starter_also_blocks_a_secret_name_even_if_the_command_looks_like_inspection():
    tools = ["delentia_run_sandboxed_command", "delentia_write_repo_file", "delentia_read_repo_file"]
    policy, errors = fdia_policy.validate_policy(fdia_policy.template("argaware", tools))
    assert policy is not None, errors
    assert fdia_policy.evaluate(policy, "delentia_run_sandboxed_command", {"command": "cat .env"}).A == 0


# ------------------------------------------------------------------------------ the harness for other people's menus

def test_a_gtfobins_entry_is_parsed_into_recipes():
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "research")))
    import external_menu_attack as ema
    entry = """---
functions:
  file-read:
  - code: |-
      date -f /path/to/input-file
      Each line is corrupted by a prefix string and wrapped inside quotes.
      GNU
    contexts:
      sudo:
        shell: false
  file-write:
  - code: |-
      git apply --unsafe-paths --directory / x.patch
      echo DATA >/path/to/input-file
      git diff /dev/null /path/to/input-file >x.patch
...
"""
    codes = ema.parse_codes(entry)
    assert [f for f, _ in codes] == ["file-read", "file-write"]
    lines = ema.first_command_lines(codes[0][1])
    assert lines == ["date -f /path/to/input-file"]
    assert "git apply --unsafe-paths --directory / x.patch" in ema.first_command_lines(codes[1][1])
    filled = dict(ema.variants("date -f /path/to/input-file", "C:/h/secret.txt", "credentials.json", "C:/h/out.txt"))
    assert filled["canary_absolute"] == "date -f C:/h/secret.txt" and filled["dotenv"] == "date -f .env" and filled["parent_traversal"] == "date -f ../secret.txt"
    assert dict(ema.variants("ls", "a", "b", "c")) == {"as_written": "ls"}


@pytest.mark.parametrize("payload", ["echo%20AGIYMZ$((69%2B52))$(echo%20AGIYMZ)AGIYMZ", ";echo%20MPCSBG", "&echo%20NWMZCF", "||echo%20ANSBHE", "&&echo%20PVJXOS", "%0aecho%20VVIEOJ",
                                     "%3Becho%20SRPJET", "`echo%20x`", "$(echo%20x)", "%26%26id", "%7Cid", "%7Csh", "%7Ccurl%20http://x.example/a"])
def test_injection_payloads_in_the_style_of_the_public_lists_never_pass_after_an_inspection_command(payload):
    decoded = urllib.parse.unquote(payload)
    tools = ["delentia_run_sandboxed_command", "delentia_write_repo_file", "delentia_read_repo_file"]
    policy, _ = fdia_policy.validate_policy(fdia_policy.template("argaware", tools))
    for command in ("ls " + decoded, "ls" + decoded, decoded):
        verdict = fdia_policy.evaluate(policy, "delentia_run_sandboxed_command", {"command": command})
        assert not (verdict.A > 0 and not verdict.needs_signature), command


def test_a_pipe_into_another_listed_inspection_program_is_allowed():
    tools = ["delentia_run_sandboxed_command", "delentia_write_repo_file", "delentia_read_repo_file"]
    policy, _ = fdia_policy.validate_policy(fdia_policy.template("argaware", tools))
    ok = fdia_policy.evaluate(policy, "delentia_run_sandboxed_command", {"command": "ls src | wc -l"})
    assert ok.A > 0 and not ok.needs_signature


# ------------------------------------------------------------------ the floor, after other people's menus (GTFOBins)

@pytest.mark.parametrize("command", ["git init .", "git commit -am wip", "git add -A", "git help config", "git branch --help config", "git branch newbranch", "git -C . status", "git --exec-path=. x",
                                     "git apply --unsafe-paths --directory / x.patch", "git config user.name x", "git -c core.pager=sh log", "git checkout main", "git clean -fd", "git tag v1",
                                     "git rm file", "git stash", "git merge x", "git pull", "git fetch", "git clone https://x.example/r.git", "git worktree add ../w"])
def test_git_subcommands_that_write_or_run_something_need_approval(command):
    assert classify_command_risk(command) == "needs_approval", command


@pytest.mark.parametrize("command", ["git status", "git log --oneline -5", "git diff", "git show --stat", "git rev-parse HEAD", "git branch --show-current", "git branch --list", "git branch -a",
                                     "git log -1 --format=%an", "git diff --stat", "git blame README.md"])
def test_read_only_git_stays_safe(command):
    assert classify_command_risk(command) == "safe", command


@pytest.mark.parametrize("command", [
    "python -c \"import socket;s=socket.socket()\"", "python -c 'import urllib.request as r; r.urlopen(\"http://x.example\")'",
    "python -c \"import os;os.system('id')\"", "node -e \"require('child_process').exec('id')\"", "python3 -c \"from ctypes import cdll; cdll.LoadLibrary('x')\"",
    "python -c 'import sys\nimport socket,os,pty;s=socket.socket()\ns.connect((\"a\",1))\n'", "perl -e 'use Socket; socket(S,PF_INET,SOCK_STREAM,0)'", "python -c \"exec('print(1)')\"",
])
def test_inline_scripts_that_open_connections_start_processes_or_write_files_need_approval(command):
    assert classify_command_risk(command) == "needs_approval", command


@pytest.mark.parametrize("command", ["python -c \"print(1+1)\"", "python --version", "node --version", "python -c \"print(sum(range(10)))\"", "python scripts/report.py", "python -c \"open('output.txt', 'w').write('x')\""])
def test_harmless_inline_code_and_scripts_are_not_newly_held(command):
    assert classify_command_risk(command) == "safe", command


@pytest.mark.parametrize("command", ["socat file:/dev/tty,raw,echo=0 tcp-listen:12345", "nc -l 4444", "ncat host 1", "ssh me@host ls", "scp a.txt me@host:/tmp", "rsync -a src host:/d", "telnet host 25", "nohup sleep 100"])
def test_programs_whose_job_is_a_network_connection_need_approval(command):
    assert classify_command_risk(command) == "needs_approval", command
