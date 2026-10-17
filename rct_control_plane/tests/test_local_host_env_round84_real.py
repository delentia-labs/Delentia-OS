"""
Round 84: the first real episode on this machine's host returned HTTP 500 for every run, because the host's default 'no budget' was written as DELENTIA_EPISODE_BUDGET_USD=0.0 and the governed loop
refuses a literal 0. The environment the supervisor gives the server must let a governed loop be built.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import json

import local_host as lh


def test_a_host_with_no_budget_sets_no_budget_variable_and_a_loop_can_be_built(tmp_path, monkeypatch):
    host = tmp_path / "host"
    lh.init(host, "ollama", "qwen3:8b", None, None, None, 8000, 0.0, 0.0, 0)
    cfg = json.loads((host / "host.json").read_text(encoding="utf-8"))
    env = lh.server_env(cfg)
    assert "DELENTIA_EPISODE_BUDGET_USD" not in env and "DELENTIA_DAILY_BUDGET_USD" not in env
    for key in [k for k in os.environ if k.startswith("DELENTIA_")]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if key.startswith("DELENTIA_"):
            monkeypatch.setenv(key, value)
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence
    loop = build_governed_loop(object(), "host-test", persistence=ControlPlanePersistence(str(tmp_path / "x.db")), mcp_server=object())
    assert loop is not None


def test_a_positive_budget_is_passed_on(tmp_path):
    host = tmp_path / "host"
    lh.init(host, "openrouter", "m", None, None, None, 8000, 0.25, 0.0, 0)
    env = lh.server_env(json.loads((host / "host.json").read_text(encoding="utf-8")))
    assert env["DELENTIA_EPISODE_BUDGET_USD"] == "0.25"


def test_a_notary_is_passed_on_as_a_url_and_a_token_file_path_never_the_token(tmp_path):
    host = tmp_path / "host"
    lh.init(host, "ollama", "qwen3:8b", None, None, None, 8000, 0.0, 0.0, 0)
    token = tmp_path / "notary_token.txt"
    token.write_text("a" * 64, encoding="ascii")
    out = lh.set_notary(host, "http://127.0.0.1:8765", str(token))
    assert out["restart_needed"] is True
    env = lh.server_env(json.loads((host / "host.json").read_text(encoding="utf-8")))
    assert env["DELENTIA_NOTARY_URL"] == "http://127.0.0.1:8765" and env["DELENTIA_NOTARY_TOKEN_FILE"] == str(token)
    assert "a" * 64 not in json.dumps(env) and "a" * 64 not in (host / "host.json").read_text(encoding="utf-8")
    lh.set_notary(host, None, None)
    assert "DELENTIA_NOTARY_URL" not in lh.server_env(json.loads((host / "host.json").read_text(encoding="utf-8")))


def test_an_empty_or_missing_token_file_is_refused(tmp_path):
    import pytest
    host = tmp_path / "host"
    lh.init(host, "ollama", "qwen3:8b", None, None, None, 8000, 0.0, 0.0, 0)
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="ascii")
    for path in (str(empty), str(tmp_path / "missing.txt")):
        with pytest.raises(SystemExit):
            lh.set_notary(host, "http://127.0.0.1:8765", path)


def test_a_local_model_gets_a_long_call_timeout_and_a_remote_one_does_not(tmp_path):
    local = tmp_path / "local"
    lh.init(local, "ollama", "qwen3:8b", None, None, None, 8000, 0.0, 0.0, 0)
    assert lh.server_env(json.loads((local / "host.json").read_text(encoding="utf-8")))["DELENTIA_OLLAMA_TIMEOUT_S"] == "600"
    remote = tmp_path / "remote"
    lh.init(remote, "openrouter", "m", None, None, None, 8000, 0.25, 0.0, 0)
    assert "DELENTIA_OLLAMA_TIMEOUT_S" not in lh.server_env(json.loads((remote / "host.json").read_text(encoding="utf-8")))
