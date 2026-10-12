"""
Round 72: the credential pool (credential_pool.py) with real HTTP: a loopback server that speaks the OpenRouter protocol and answers each KEY with a programmed
status. What is checked is behaviour: which key signed which call, what a refusal moves, what is written to the audit trail, and that no key value ever appears in
a status page, an audit row, an exception or a repr.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
import httpx
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from rct_control_plane import credential_pool as cp
from rct_control_plane import sandbox
from rct_control_plane.llm_provider import OpenAICompatibleProvider, OpenRouterProvider, get_default_provider
from rct_control_plane.persistence import ControlPlanePersistence

VALUES = {"OPENROUTER_API_KEY": "alpha-secret-value-1", "OPENROUTER_API_KEY_B": "bravo-secret-value-2", "OPENROUTER_API_KEY_C": "charlie-secret-value-3"}
ANSWER = "pool answer"


class Server:
    """plan[key value] = list of statuses answered in order (then 200). Records which key signed each call."""

    def __init__(self, plan=None, stream=False):
        self.plan, self.signed, outer = dict(plan or {}), [], self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body_in = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                key = (self.headers.get("Authorization") or "").replace("Bearer ", "")
                outer.signed.append(key)
                queue = outer.plan.get(key) or []
                status = queue.pop(0) if queue else 200
                if status != 200:
                    body = json.dumps({"error": {"message": "refused"}}).encode()
                    self.send_response(status)
                    if status == 429:
                        self.send_header("Retry-After", "1")
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if json.loads(body_in or b"{}").get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for piece in ("pool ", "stream"):
                        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}) + "\n\n").encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                body = json.dumps({"choices": [{"message": {"content": ANSWER}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.http.server_port}"

    def stop(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    cp.reset()
    cp._sink = None
    for name in list(os.environ):
        if name.startswith(cp.SHORTHAND_PREFIX) or name in VALUES:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(cp.POOL_FILE_ENV, str(tmp_path / "pool.json"))
    yield
    cp.reset()
    cp._sink = None


def _keys(monkeypatch, *names):
    for n in names:
        monkeypatch.setenv(n, VALUES[n])


def _pool(path_env_value, **providers):
    with open(path_env_value, "w", encoding="utf-8") as f:
        json.dump(providers, f)


def _server(monkeypatch, **kw):
    s = Server(**kw)
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", s.url)
    return s


def _ask(provider):
    return asyncio.run(provider.complete("hi", max_tokens=16))


# ---- the file holds names, never keys ---------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("entry", ["sk-or-v1-abcdef0123456789abcdef0123456789", "openrouter_api_key", "MY_PLAIN_NAME", "OPENROUTER_API_KEY=abc", "", 5, None])
def test_an_entry_that_is_not_a_secret_variable_name_is_refused_and_not_repeated(entry):
    with pytest.raises(cp.PoolConfigError) as err:
        cp._clean("openrouter", {"keys": ["OPENROUTER_API_KEY", entry]})
    assert "entry #2" in str(err.value)
    if isinstance(entry, str) and entry:
        assert entry not in str(err.value)                    # a key pasted by mistake must not be echoed back into a log


def test_the_pool_has_limits_and_known_strategies():
    with pytest.raises(cp.PoolConfigError):
        cp._clean("openrouter", {"keys": []})
    with pytest.raises(cp.PoolConfigError):
        cp._clean("openrouter", {"keys": [f"SOME_KEY_{i}" for i in range(cp.MAX_KEYS_PER_PROVIDER + 1)]})
    with pytest.raises(cp.PoolConfigError):
        cp._clean("openrouter", {"keys": ["A_KEY", "A_KEY"]})
    with pytest.raises(cp.PoolConfigError):
        cp._clean("openrouter", {"keys": ["A_KEY"], "strategy": "random_walk"})
    with pytest.raises(cp.PoolConfigError):
        cp._clean("anthropic", {"keys": ["A_KEY"]})


def test_a_broken_pool_file_is_an_error_and_never_a_silent_fallback_to_some_other_key(monkeypatch, tmp_path):
    (tmp_path / "pool.json").write_text("{not json", encoding="utf-8")
    _keys(monkeypatch, "OPENROUTER_API_KEY")
    with pytest.raises(cp.PoolConfigError):
        cp.load_config()
    assert cp.configured("openrouter") is True and cp.available("openrouter", "OPENROUTER_API_KEY") is False


def test_every_name_the_pool_accepts_is_one_the_shell_sandbox_hides_from_the_agent(monkeypatch):
    for name in ("OPENROUTER_API_KEY_B", "MY_PROVIDER_TOKEN", "TEAM_SECRET_1", "BACKUP_CREDENTIAL"):
        assert cp.valid_name(name)
        monkeypatch.setenv(name, "value-that-must-not-reach-the-agent-shell")
        assert name not in sandbox.scrubbed_environment()


def test_save_config_keeps_other_providers_and_writes_names_only(monkeypatch, tmp_path):
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"])
    cp.save_config("openai-compat", ["NATIONAL_AI_TOKEN"], strategy="round_robin")
    raw = (tmp_path / "pool.json").read_text(encoding="utf-8")
    assert set(json.loads(raw)) == {"openrouter", "openai-compat"} and json.loads(raw)["openai-compat"]["strategy"] == "round_robin"
    assert "secret" not in raw.lower() or "SECRET" not in raw


# ---- rotation, with real HTTP ----------------------------------------------------------------------------------------------------------------------------------

def test_without_a_pool_one_key_signs_as_before(monkeypatch):
    _keys(monkeypatch, "OPENROUTER_API_KEY")
    srv = _server(monkeypatch)
    try:
        assert _ask(OpenRouterProvider(model="v/m")) == ANSWER
        assert srv.signed == [VALUES["OPENROUTER_API_KEY"]]
    finally:
        srv.stop()


def test_a_rate_limited_key_hands_the_call_to_the_next_and_is_skipped_until_it_cools(monkeypatch, tmp_path):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"])
    srv = _server(monkeypatch, plan={VALUES["OPENROUTER_API_KEY"]: [429]})
    try:
        provider = OpenRouterProvider(model="v/m")
        assert _ask(provider) == ANSWER
        assert srv.signed == [VALUES["OPENROUTER_API_KEY"], VALUES["OPENROUTER_API_KEY_B"]]              # first refused (429), second answered
        assert _ask(provider) == ANSWER
        assert srv.signed[-1] == VALUES["OPENROUTER_API_KEY_B"]                                          # the cooling key was not tried again
        state = {k["label"]: k for k in cp.status()["providers"]["openrouter"]["keys"]}
        assert state["OPENROUTER_API_KEY"]["state"] == "cooling" and 0 < state["OPENROUTER_API_KEY"]["cooldown_seconds"] <= 1.01      # the server's Retry-After: 1
        assert state["OPENROUTER_API_KEY_B"]["uses"] == 2
    finally:
        srv.stop()


def test_after_the_cooldown_the_first_key_is_used_again(monkeypatch, tmp_path):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"])
    srv = _server(monkeypatch, plan={VALUES["OPENROUTER_API_KEY"]: [429]})
    try:
        provider = OpenRouterProvider(model="v/m")
        _ask(provider)
        cp._state[("openrouter", "OPENROUTER_API_KEY")]["cooldown_until"] = 0.0           # the time has passed
        _ask(provider)
        assert srv.signed[-1] == VALUES["OPENROUTER_API_KEY"]
    finally:
        srv.stop()


def test_a_revoked_key_is_dead_for_the_process_and_out_of_credit_is_a_day(monkeypatch):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B", "OPENROUTER_API_KEY_C")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B", "OPENROUTER_API_KEY_C"])
    srv = _server(monkeypatch, plan={VALUES["OPENROUTER_API_KEY"]: [401], VALUES["OPENROUTER_API_KEY_B"]: [402]})
    try:
        assert _ask(OpenRouterProvider(model="v/m")) == ANSWER
        assert srv.signed == [VALUES["OPENROUTER_API_KEY"], VALUES["OPENROUTER_API_KEY_B"], VALUES["OPENROUTER_API_KEY_C"]]
        state = {k["label"]: k for k in cp.status()["providers"]["openrouter"]["keys"]}
        assert state["OPENROUTER_API_KEY"]["state"] == "disabled"
        assert state["OPENROUTER_API_KEY_B"]["state"] == "cooling" and state["OPENROUTER_API_KEY_B"]["cooldown_seconds"] > 23 * 3600
    finally:
        srv.stop()


def test_a_server_error_says_nothing_about_a_key_and_moves_nothing(monkeypatch):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"])
    srv = _server(monkeypatch, plan={VALUES["OPENROUTER_API_KEY"]: [503]})
    try:
        with pytest.raises(Exception) as err:
            _ask(OpenRouterProvider(model="v/m"))
        assert "503" in str(err.value)
        assert srv.signed == [VALUES["OPENROUTER_API_KEY"]]                          # no second key was tried, and nothing is cooling
        assert all(k["state"] == "ready" for k in cp.status()["providers"]["openrouter"]["keys"])
    finally:
        srv.stop()


def test_when_every_key_is_unavailable_the_error_names_labels_and_never_a_value(monkeypatch):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"])
    srv = _server(monkeypatch, plan={VALUES["OPENROUTER_API_KEY"]: [401], VALUES["OPENROUTER_API_KEY_B"]: [429]})
    try:
        provider = OpenRouterProvider(model="v/m")
        with pytest.raises(httpx.HTTPStatusError):
            _ask(provider)                                                      # the last refusal is raised as a normal HTTP error
        with pytest.raises(cp.NoCredentialAvailable) as err:
            _ask(provider)
        text = str(err.value)
        assert "OPENROUTER_API_KEY: disabled" in text and "OPENROUTER_API_KEY_B: cooling" in text and "ready again in" in text
        assert not any(v in text for v in VALUES.values())
    finally:
        srv.stop()


def test_round_robin_and_least_used_spread_the_calls(monkeypatch):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B", "OPENROUTER_API_KEY_C")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B", "OPENROUTER_API_KEY_C"], strategy="round_robin")
    srv = _server(monkeypatch)
    try:
        provider = OpenRouterProvider(model="v/m")
        for _ in range(6):
            _ask(provider)
        assert sorted(set(srv.signed)) == sorted(VALUES.values()) and all(srv.signed.count(v) == 2 for v in VALUES.values())
        cp.reset()
        cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B", "OPENROUTER_API_KEY_C"], strategy="least_used")
        cp._slot("openrouter", "OPENROUTER_API_KEY")["uses"] = 5
        cp._slot("openrouter", "OPENROUTER_API_KEY_B")["uses"] = 1
        srv.signed.clear()
        _ask(provider)
        assert srv.signed == [VALUES["OPENROUTER_API_KEY_C"]]                    # 0 uses beats 1 and 5
    finally:
        srv.stop()


def test_an_explicit_key_is_never_replaced_by_the_pool(monkeypatch):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"])
    srv = _server(monkeypatch)
    try:
        assert _ask(OpenRouterProvider(api_key="explicit-given-key", model="v/m")) == ANSWER
        assert srv.signed == ["explicit-given-key"]
    finally:
        srv.stop()


def test_a_stream_rotates_before_the_first_piece_of_text(monkeypatch):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"])
    srv = _server(monkeypatch, plan={VALUES["OPENROUTER_API_KEY"]: [429]})
    try:
        async def collect():
            return "".join([p async for p in OpenRouterProvider(model="v/m").stream_complete("hi")])
        assert asyncio.run(collect()) == "pool stream"
        assert srv.signed == [VALUES["OPENROUTER_API_KEY"], VALUES["OPENROUTER_API_KEY_B"]]
    finally:
        srv.stop()


def test_the_default_provider_works_with_only_pool_keys_and_not_the_usual_variable(monkeypatch):
    _keys(monkeypatch, "OPENROUTER_API_KEY_B")
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("DELENTIA_LLM_MODEL", "v/m")
    assert not isinstance(get_default_provider(), OpenRouterProvider)                   # no pool, no OPENROUTER_API_KEY: falls back to Ollama as before
    cp.save_config("openrouter", ["OPENROUTER_API_KEY_B"])
    provider = get_default_provider()
    assert isinstance(provider, OpenRouterProvider)
    srv = _server(monkeypatch)
    try:
        assert _ask(provider) == ANSWER and srv.signed == [VALUES["OPENROUTER_API_KEY_B"]]
    finally:
        srv.stop()


def test_the_openai_compatible_provider_rotates_too(monkeypatch):
    monkeypatch.setenv("NATIONAL_AI_TOKEN", "nat-one")
    monkeypatch.setenv("NATIONAL_AI_TOKEN_2", "nat-two")
    cp.save_config("openai-compat", ["NATIONAL_AI_TOKEN", "NATIONAL_AI_TOKEN_2"])
    srv = Server(plan={"nat-one": [429]})
    try:
        provider = OpenAICompatibleProvider(base_url=srv.url, model="m", credential_env="NATIONAL_AI_TOKEN", kind="local")
        assert _ask(provider) == ANSWER
        assert srv.signed == ["nat-one", "nat-two"]
    finally:
        srv.stop()


# ---- the audit trail and what must never be shown ---------------------------------------------------------------------------------------------------------------

def test_moves_are_audited_by_label_and_no_key_value_appears_anywhere(monkeypatch, tmp_path):
    _keys(monkeypatch, "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B")
    cp.save_config("openrouter", ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"])
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "a.db"))
    cp.bind_audit(persistence, "alice")
    srv = _server(monkeypatch, plan={VALUES["OPENROUTER_API_KEY"]: [429]})
    try:
        provider = OpenRouterProvider(model="v/m")
        _ask(provider)
        import sqlite3
        with sqlite3.connect(str(tmp_path / "a.db")) as conn:
            rows = conn.execute("SELECT entity_type, entity_id, action, changes FROM audit_trail WHERE entity_type = 'credential_pool'").fetchall()
        assert len(rows) == 1 and rows[0][1] == "openrouter-OPENROUTER_API_KEY" and rows[0][2] == "cooldown"
        dump = json.dumps(rows) + json.dumps(cp.status()) + repr(cp.acquire("openrouter")) + str(cp._events)
        assert not any(v in dump for v in VALUES.values())
        assert json.loads(rows[0][3])["status"] == 429
    finally:
        srv.stop()


def test_clear_moves_the_entry_aside_and_the_pool_is_not_broken_by_it(monkeypatch, tmp_path):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    runner = CliRunner()
    assert runner.invoke(cli, ["credentials", "set", "openrouter", "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_B"]).exit_code == 0
    assert set(cp.load_config()) == {"openrouter"}
    assert runner.invoke(cli, ["credentials", "clear", "openrouter"]).exit_code == 0
    assert cp.load_config() == {}                                                                     # switched off, and the file still loads
    assert "openrouter.cleared" in json.loads((tmp_path / "pool.json").read_text(encoding="utf-8"))     # kept, not deleted
    shown = runner.invoke(cli, ["credentials", "status"])
    assert shown.exit_code == 0 and "no pool configured" in shown.output


def test_the_cli_refuses_a_pasted_key_without_echoing_it(monkeypatch):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    pasted = "sk-or-v1-0123456789abcdef0123456789abcdef"
    result = CliRunner().invoke(cli, ["credentials", "set", "openrouter", pasted])
    assert result.exit_code == 1 and pasted not in result.output and "never keys" in result.output
