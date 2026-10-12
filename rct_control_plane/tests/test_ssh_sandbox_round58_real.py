"""
Round 58: the SSH sandbox backend.

No SSH server is available on this machine, so the connection itself is NOT tested (said in sandbox.py). What is tested for real:
  * the exact command line is accepted by the real OpenSSH client and, asked to print its effective configuration (`ssh -G`), reports the strict settings we asked for;
  * a stand-in `ssh` program (a script that records its argv and its environment) shows what this process would run: no shell, no secrets in the environment, the remote command quoted
    so it arrives byte for byte;
  * every refusal: not configured, a host that would become an ssh option, a missing known-hosts file, the denylist and the risk gate first, an unknown backend, a timeout;
  * above all, that a selected-but-broken SSH backend never falls back to running the command on this machine.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import shlex
import shutil
import subprocess
import textwrap

import pytest

from rct_control_plane import sandbox

FAKE = textwrap.dedent('''
    import json, os, sys, time
    mode = os.environ.get("FAKE_SSH_MODE", "ok")
    record = {"argv": sys.argv[1:], "env": sorted(os.environ)}
    open(os.environ["FAKE_SSH_LOG"], "w").write(json.dumps(record))
    if mode == "sleep":
        time.sleep(30)
    if mode == "fail":
        sys.stderr.write("Host key verification failed.\\n"); sys.exit(255)
    sys.stdout.write("remote output\\n")
''')


@pytest.fixture
def ssh(tmp_path, monkeypatch):
    key, known = tmp_path / "id_test", tmp_path / "known_hosts"
    key.write_text("not a real key")
    known.write_text("box.example ssh-ed25519 AAAA\n")
    script = tmp_path / "fake_ssh.py"
    script.write_text(FAKE)
    if os.name == "nt":
        wrapper = tmp_path / "fake_ssh.bat"
        wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    else:
        wrapper = tmp_path / "fake_ssh"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        wrapper.chmod(0o755)
    log = tmp_path / "ssh_call.json"
    for name, value in {"DELENTIA_SSH_HOST": "agent@box.example", "DELENTIA_SSH_KEY": str(key), "DELENTIA_SSH_KNOWN_HOSTS": str(known),
                        "DELENTIA_SSH_BIN": str(wrapper), "FAKE_SSH_LOG": str(log)}.items():
        monkeypatch.setenv(name, value)
    for name in ("DELENTIA_SSH_PORT", "DELENTIA_SSH_WORKDIR", "DELENTIA_SANDBOX_BACKEND", "FAKE_SSH_MODE"):
        monkeypatch.delenv(name, raising=False)

    class Handle:
        def call(self):
            return json.loads(log.read_text())

        @property
        def called(self):
            return log.exists()
    return Handle()


# ------------------------------------------------------------------ the command line

class TestCommandLine:
    @pytest.mark.skipif(shutil.which("ssh") is None, reason="no OpenSSH client on this machine")
    def test_real_openssh_accepts_every_option_and_reports_the_strict_settings(self, ssh, tmp_path):
        settings = sandbox.ssh_settings()
        argv = sandbox.ssh_command_line({**settings, "bin": "ssh"}, "echo hi", 10)
        shown = subprocess.run([argv[0], "-G"] + argv[1:-1], capture_output=True, text=True, timeout=30)
        assert shown.returncode == 0, shown.stderr
        config = dict(line.split(" ", 1) for line in shown.stdout.splitlines() if " " in line)
        assert config["stricthostkeychecking"] == "true" and config["batchmode"] == "yes" and config["forwardagent"] == "no"
        assert config["clearallforwardings"] == "yes" and config["identitiesonly"] == "yes" and config["passwordauthentication"] == "no"
        assert config["permitlocalcommand"] == "no" and config["identityagent"] == "none" and config["globalknownhostsfile"] == "none"
        assert config["hostname"] == "box.example" and config["user"] == "agent" and config["connecttimeout"] == "10"
        assert config["userknownhostsfile"] == settings["known_hosts"]

    def test_the_remote_command_arrives_byte_for_byte(self, ssh):
        settings = sandbox.ssh_settings()
        for command in ["echo hi", "echo 'it''s' \"quoted\" $HOME `id` $(whoami); ls | wc -l", "printf '%s\\n' a b\nsecond line", "echo é ไทย"]:
            remote = sandbox.ssh_command_line(settings, command, 10)[-1]
            words = shlex.split(remote.split("then ", 1)[1].split("; else", 1)[0])       # timeout -k 2 11 sh -c '<command>'
            assert words[:5] == ["timeout", "-k", "2", "11", "sh"] and words[5] == "-c" and words[6] == command

    def test_the_host_comes_after_a_double_dash_so_it_can_never_be_an_option(self, ssh):
        argv = sandbox.ssh_command_line(sandbox.ssh_settings(), "ls", 5)
        assert argv[-3] == "--" and argv[-2] == "agent@box.example"

    def test_a_workdir_with_a_home_prefix_keeps_it_and_others_are_quoted(self, ssh, monkeypatch):
        monkeypatch.setenv("DELENTIA_SSH_WORKDIR", "~/agent-work")
        assert "mkdir -p ~/agent-work && cd ~/agent-work" in sandbox.ssh_command_line(sandbox.ssh_settings(), "ls", 5)[-1]


# ------------------------------------------------------------------ running

class TestRunning:
    def test_it_runs_through_the_client_with_no_shell_and_no_secrets_in_the_environment(self, ssh, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-value")
        monkeypatch.setenv("DELENTIA_AUDIT_SIGNING_KEY", "/keys/audit.pem")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
        r = sandbox.run_sandboxed("ls -la", backend="ssh")
        assert r.blocked_reason is None and r.exit_code == 0 and r.stdout.strip() == "remote output"
        call = ssh.call()
        assert "-i" in call["argv"] and call["argv"][-2] == "agent@box.example"
        leaked = [n for n in call["env"] if any(part in n.upper() for part in ("KEY", "TOKEN", "SECRET", "SIGNING"))]
        assert leaked == [] or leaked == ["FAKE_SSH_LOG"] or all(n.startswith("FAKE_") for n in leaked), leaked

    def test_the_owners_environment_can_choose_the_backend_for_every_command(self, ssh, monkeypatch):
        monkeypatch.setenv("DELENTIA_SANDBOX_BACKEND", "ssh")
        r = sandbox.run_sandboxed("ls")
        assert r.stdout.strip() == "remote output" and ssh.call()["argv"]

    def test_a_failing_connection_is_reported_with_its_exit_code(self, ssh, monkeypatch):
        monkeypatch.setenv("FAKE_SSH_MODE", "fail")
        r = sandbox.run_sandboxed("ls", backend="ssh")
        assert r.exit_code == 255 and "Host key verification failed" in r.stderr

    def test_a_command_that_never_ends_is_cut_off(self, ssh, monkeypatch):
        monkeypatch.setenv("FAKE_SSH_MODE", "sleep")
        monkeypatch.setattr(sandbox, "_kill_process_tree", lambda p: p.kill())
        import time
        original = subprocess.Popen.communicate
        started = time.monotonic()

        def quick(self, input=None, timeout=None):          # the real backstop is timeout + 12 s; do not make the suite wait for it
            return original(self, input, timeout=min(timeout, 1.5) if timeout else timeout)
        monkeypatch.setattr(subprocess.Popen, "communicate", quick)
        r = sandbox.run_sandboxed("sleep 100", timeout_seconds=1, backend="ssh")
        assert r.timed_out and time.monotonic() - started < 15


# ------------------------------------------------------------------ refusals

class TestRefusals:
    @pytest.mark.parametrize("missing", ["DELENTIA_SSH_HOST", "DELENTIA_SSH_KEY", "DELENTIA_SSH_KNOWN_HOSTS"])
    def test_a_missing_setting_refuses_and_names_it(self, ssh, monkeypatch, missing):
        monkeypatch.delenv(missing)
        r = sandbox.run_sandboxed("ls", backend="ssh")
        assert r.exit_code is None and missing in r.blocked_reason

    def test_a_selected_but_broken_ssh_backend_never_runs_the_command_here(self, ssh, monkeypatch, tmp_path):
        """The most important property: 'ssh' selected + broken must not quietly become 'local'."""
        monkeypatch.setenv("DELENTIA_SANDBOX_BACKEND", "ssh")
        monkeypatch.delenv("DELENTIA_SSH_HOST")
        monkeypatch.chdir(tmp_path)
        marker = tmp_path / "ran_locally.txt"
        r = sandbox.run_sandboxed(f'python -c "open(r\'{marker}\', \'w\').write(\'x\')"', approved=True)    # Round 65: the marker path is a drive path (needs approval); the point is that the backend refuses first
        assert r.blocked_reason and "not configured" in r.blocked_reason and not marker.exists()

    @pytest.mark.parametrize("host", ["-oProxyCommand=evil@x", "evil", "a b@host", "@host", "user@", "user@-oProxyCommand=x", "us er@host", "user@ho;st", "user@host name"])
    def test_a_host_that_could_become_an_option_or_a_command_is_refused(self, ssh, monkeypatch, host):
        monkeypatch.setenv("DELENTIA_SSH_HOST", host)
        r = sandbox.run_sandboxed("ls", backend="ssh")
        assert r.exit_code is None and "user@host" in r.blocked_reason

    def test_without_a_known_hosts_file_it_will_not_trust_a_key_on_first_use(self, ssh, monkeypatch, tmp_path):
        monkeypatch.setenv("DELENTIA_SSH_KNOWN_HOSTS", str(tmp_path / "does-not-exist"))
        r = sandbox.run_sandboxed("ls", backend="ssh")
        assert "never accepts a key on first use" in r.blocked_reason

    @pytest.mark.parametrize("port", ["0", "70000", "22; id", "abc"])
    def test_a_bad_port_is_refused(self, ssh, monkeypatch, port):
        monkeypatch.setenv("DELENTIA_SSH_PORT", port)
        assert "port number" in sandbox.run_sandboxed("ls", backend="ssh").blocked_reason

    @pytest.mark.parametrize("workdir", ["../escape", "a b", "x;y", "$(id)"])
    def test_a_bad_workdir_is_refused(self, ssh, monkeypatch, workdir):
        monkeypatch.setenv("DELENTIA_SSH_WORKDIR", workdir)
        assert "WORKDIR" in sandbox.run_sandboxed("ls", backend="ssh").blocked_reason

    def test_the_denylist_and_the_risk_gate_come_first(self, ssh):
        assert "denylisted" in sandbox.run_sandboxed("rm -rf /", backend="ssh").blocked_reason
        assert "needs approval" in sandbox.run_sandboxed("git push origin main", backend="ssh").blocked_reason
        assert not ssh.called                                  # ssh was never even started

    def test_an_unknown_backend_runs_nothing(self, ssh):
        r = sandbox.run_sandboxed("ls", backend="telnet")
        assert "unknown sandbox backend" in r.blocked_reason and r.exit_code is None

    def test_a_missing_client_is_said_plainly(self, ssh, monkeypatch, tmp_path):
        monkeypatch.setenv("DELENTIA_SSH_BIN", str(tmp_path / "no-such-ssh"))
        assert "not installed" in sandbox.run_sandboxed("ls", backend="ssh").blocked_reason

    def test_the_default_is_still_the_local_backend(self, ssh, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = sandbox.run_sandboxed("echo local")
        assert r.stdout.strip() == "local"
