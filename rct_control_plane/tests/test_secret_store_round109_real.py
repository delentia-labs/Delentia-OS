"""
Round 109: a model key typed into the Desk is kept on this computer (secret_store) so it does not have to be typed again after the program is closed.

The owner's decision: keep keys permanently; when a key expires is the person's own business. What these tests pin is that "kept" does not mean "lying about":
  * the key survives a restart (a fresh process environment gets it back) and an environment variable that is already set always wins;
  * at rest on Windows the file does not contain the key (DPAPI, the real thing, no mock); elsewhere it is a file only the owner can read, and `scheme()` says which;
  * nothing a page or a command can ask for ever contains the key: status shows the name, the date and the last four characters only; the audit row names the variable, never the value;
  * the saved file is inside the places the agent may not read, and is left out of a backup even with --include-keys;
  * the Desk route is owner-only, a person's token is refused; `remember: false` keeps the old memory-only behaviour; forgetting removes both copies;
  * an unreadable or foreign file is treated as "no key saved", never as a crash and never as a guess.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import sqlite3

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import api_auth, api_tokens, backup, secret_store, secret_paths
from rct_control_plane.api import create_app
from rct_control_plane.cli import cli
from rct_control_plane.persistence import ControlPlanePersistence

KEY = "sk-or-v1-0123456789abcdef-THIS-IS-A-TEST-KEY-9z8y"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DELENTIA_SECRET_STORE", raising=False)
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    monkeypatch.delenv("DELENTIA_API_TOKENS_FILE", raising=False)


class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def desk(tmp_path, monkeypatch):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    with TestClient(create_app()) as client:
        yield client, persistence


def test_a_saved_key_comes_back_after_a_restart_and_the_environment_wins(monkeypatch):
    secret_store.save("OPENROUTER_API_KEY", KEY)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)                         # a new process: nothing in the environment
    assert secret_store.apply_to_environment() == ["OPENROUTER_API_KEY"] and os.environ["OPENROUTER_API_KEY"] == KEY
    monkeypatch.setenv("OPENROUTER_API_KEY", "set-by-the-person-in-the-environment")
    assert secret_store.apply_to_environment() == []                                # already set: left alone
    assert os.environ["OPENROUTER_API_KEY"] == "set-by-the-person-in-the-environment"


def test_what_is_on_disk_is_not_the_key_on_windows_and_is_owner_only_elsewhere():
    secret_store.save("OPENROUTER_API_KEY", KEY)
    raw = secret_store.store_path().read_bytes()
    if sys.platform == "win32":
        assert secret_store.scheme() == "windows-dpapi"
        assert KEY.encode() not in raw and b"OPENROUTER_API_KEY" not in raw          # encrypted for this Windows account: the name is hidden too
    else:
        assert secret_store.scheme() == "file-0600"
        assert (secret_store.store_path().stat().st_mode & 0o777) == 0o600


def test_status_never_shows_the_key_only_name_date_and_last_four():
    assert secret_store.status() == []
    secret_store.save("OPENROUTER_API_KEY", KEY)
    secret_store.save("TYPHOON_API_KEY", "short")                                       # too short to show any part of
    shown = {e["env"]: e for e in secret_store.status()}
    assert shown["OPENROUTER_API_KEY"]["last4"] == KEY[-4:] and shown["OPENROUTER_API_KEY"]["saved_at"] > 0
    assert shown["TYPHOON_API_KEY"]["last4"] == ""
    text = json.dumps(secret_store.status_view())
    assert KEY not in text and "short" not in text.replace("shortcut", "")


def test_forgetting_removes_the_saved_copy_and_the_file_when_it_is_the_last():
    secret_store.save("OPENROUTER_API_KEY", KEY)
    assert secret_store.forget("OPENROUTER_API_KEY") is True
    assert secret_store.status() == [] and not secret_store.store_path().exists()
    assert secret_store.forget("OPENROUTER_API_KEY") is False                           # nothing left to forget


def test_a_damaged_or_foreign_file_means_no_key_saved_not_a_crash():
    secret_store.save("OPENROUTER_API_KEY", KEY)
    secret_store.store_path().write_bytes(b"not what this version wrote")
    assert secret_store.status() == [] and secret_store.apply_to_environment() == []
    secret_store.store_path().write_bytes(secret_store._MAGIC_PLAIN + b"{not json")
    assert secret_store.status() == []


def test_a_file_encrypted_for_windows_is_refused_elsewhere_with_a_clear_reason(monkeypatch):
    with pytest.raises(secret_store.SecretStoreError):
        monkeypatch.setattr(sys, "platform", "linux")
        secret_store._unseal(secret_store._MAGIC_DPAPI + b"xxxx")


def test_switching_it_off_keeps_nothing_and_loads_nothing(monkeypatch):
    secret_store.save("OPENROUTER_API_KEY", KEY)
    monkeypatch.setenv("DELENTIA_SECRET_STORE", "off")
    assert secret_store.apply_to_environment() == [] and secret_store.status_view() == {"enabled": False, "scheme": secret_store.scheme(), "saved": []}
    with pytest.raises(secret_store.SecretStoreError):
        secret_store.save("OPENROUTER_API_KEY", KEY)


@pytest.mark.parametrize("name", ["openrouter_api_key", "DELENTIA_API_KEY", "PATH", "OPENROUTER", "A" * 80 + "_API_KEY", ""])
def test_only_credential_looking_names_can_be_saved(name):
    with pytest.raises(secret_store.SecretStoreError):
        secret_store.save(name, KEY)


@pytest.mark.parametrize("value", ["", "x" * 5000, "line\nbreak", "nul\x00byte"])
def test_unusable_values_are_refused(value):
    with pytest.raises(secret_store.SecretStoreError):
        secret_store.save("OPENROUTER_API_KEY", value)


def test_the_saved_file_is_somewhere_the_agent_may_not_read_and_a_backup_leaves_it_out(tmp_path, monkeypatch):
    for name in ("HOME", "USERPROFILE"):                                                # the backup also reads the user's own ~/.delentia: keep this machine's real one out of the test
        monkeypatch.setenv(name, str(tmp_path / "userhome"))
    secret_store.save("OPENROUTER_API_KEY", KEY)
    ControlPlanePersistence(db_path=str(tmp_path / "home" / "agentic.db"))              # a backup needs something to back up (a fresh CI runner has no data of its own)
    assert secret_paths.blocked_reason(str(secret_store.store_path())) is not None
    out = tmp_path / "backup.zip"
    backup.create_backup(str(out), include_keys=True)                                   # even when the person asks for keys, a device-bound file would be useless and is not copied
    import zipfile
    with zipfile.ZipFile(out) as archive:
        assert not [n for n in archive.namelist() if "model_keys" in n]
        assert all(KEY.encode() not in archive.read(n) for n in archive.namelist())


def test_the_shell_the_agent_runs_commands_in_never_receives_a_saved_key(monkeypatch):
    from rct_control_plane import sandbox
    secret_store.save("OPENROUTER_API_KEY", KEY)
    secret_store.apply_to_environment()
    env = sandbox.scrubbed_environment()
    assert "OPENROUTER_API_KEY" not in env and KEY not in json.dumps(env)


def test_the_desk_keeps_a_typed_key_by_default_and_never_sends_it_back(desk, monkeypatch):
    client, persistence = desk
    answer = client.post("/v1/desk/models", json={"provider": "openrouter", "model": "anthropic/claude-haiku-5.5", "api_key": KEY}).json()
    assert answer["key_saved_on_computer"] is True and answer["key_kept_in_memory"] is True
    assert [e["env"] for e in answer["key_store"]["saved"]] == ["OPENROUTER_API_KEY"]
    assert KEY not in json.dumps(answer) and KEY not in client.get("/v1/desk/models/setup").text
    assert secret_store.status()[0]["last4"] == KEY[-4:]
    with sqlite3.connect(persistence.db_path) as conn:
        rows = conn.execute("SELECT entity_type, entity_id, action, changes FROM audit_trail WHERE entity_type='model_key'").fetchall()
    assert rows and rows[-1][2] == "kept_on_computer" and rows[-1][1] == "OPENROUTER_API_KEY"
    assert all(KEY not in str(cell) and KEY[-4:] not in str(cell) for row in rows for cell in row)      # the audit names the variable: not the key, not even a part of it


def test_unticking_remember_keeps_the_old_memory_only_behaviour(desk):
    client, _ = desk
    answer = client.post("/v1/desk/models", json={"provider": "openrouter", "model": "anthropic/claude-haiku-5.5", "api_key": KEY, "remember": False}).json()
    assert answer["key_saved_on_computer"] is False and answer["key_kept_in_memory"] is True
    assert secret_store.status() == [] and "memory only" in answer["key_note"]


def test_forgetting_from_the_desk_clears_both_copies_and_is_audited(desk):
    client, persistence = desk
    client.post("/v1/desk/models", json={"provider": "openrouter", "model": "anthropic/claude-haiku-5.5", "api_key": KEY})
    assert os.environ.get("OPENROUTER_API_KEY") == KEY
    answer = client.post("/v1/desk/models/key/forget", json={"env": "OPENROUTER_API_KEY"}).json()
    assert answer["forgot_saved_copy"] is True and answer["cleared_from_this_process"] is True
    assert "OPENROUTER_API_KEY" not in os.environ and secret_store.status() == []
    assert client.post("/v1/desk/models/key/forget", json={"env": "not a name"}).status_code == 400
    with sqlite3.connect(persistence.db_path) as conn:
        assert conn.execute("SELECT count(*) FROM audit_trail WHERE entity_type='model_key' AND action='forgotten'").fetchone()[0] == 1


def test_a_person_with_their_own_token_cannot_save_or_forget_a_key(tmp_path, monkeypatch):
    path = tmp_path / "tokens.json"
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(path))
    alice = api_tokens.create("alice", path)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    assert "/v1/desk/models" not in api_auth.PERSON_ROUTES
    with TestClient(create_app()) as client:
        headers = {"Authorization": f"Bearer {alice}"}
        assert client.post("/v1/desk/models", json={"provider": "openrouter", "model": "m", "api_key": KEY}, headers=headers).status_code == 403
        assert client.post("/v1/desk/models/key/forget", json={"env": "OPENROUTER_API_KEY"}, headers=headers).status_code == 403
    assert secret_store.status() == []


def test_the_command_line_asks_for_the_key_hidden_and_never_prints_it():
    runner = CliRunner()
    done = runner.invoke(cli, ["model", "key", "set", "OPENROUTER_API_KEY"], input=KEY + "\n")
    assert done.exit_code == 0 and KEY not in done.output
    shown = runner.invoke(cli, ["model", "key", "status"])
    assert "OPENROUTER_API_KEY" in shown.output and KEY not in shown.output and KEY[-4:] in shown.output
    gone = runner.invoke(cli, ["model", "key", "forget", "OPENROUTER_API_KEY"])
    assert gone.exit_code == 0 and "Forgot" in gone.output and secret_store.status() == []


def test_every_command_loads_the_kept_key_so_a_restarted_program_just_works(monkeypatch):
    secret_store.save("OPENROUTER_API_KEY", KEY)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = CliRunner().invoke(cli, ["model", "key", "status"])
    assert result.exit_code == 0 and os.environ.get("OPENROUTER_API_KEY") == KEY
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
