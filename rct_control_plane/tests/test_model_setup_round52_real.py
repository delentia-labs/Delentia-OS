"""
Round 52: the Desk's model-setup page. Real HTTP (a local server plays the provider), the real
FastAPI app, real files. The thing under test is what must hold when an operator types a provider's
address and a key into a web page: the key is never written down, a policy-blocked endpoint is
never contacted, and nothing a stranger types can change a setting that is not a credential.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from core.regional_adapter.sovereignty import SovereigntyPolicy
from rct_control_plane import model_config, model_setup, provider_presets, residency
from rct_control_plane.api import create_app
from scripted_model import ScriptedModel, competent

SECRET = "sk-test-0123456789-abcdef-NOT-A-REAL-KEY"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
    monkeypatch.setenv(residency.CONFIG_ENV, str(tmp_path / "sovereignty.json"))
    for name in ("DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL", residency.HOME_REGION_ENV, "OPENROUTER_API_KEY", "ROUND52_PROVIDER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


class _Keyed(BaseHTTPRequestHandler):
    seen_auth: list = []
    hits = 0

    def do_GET(self):
        type(self).hits += 1
        type(self).seen_auth.append(self.headers.get("Authorization"))
        if self.headers.get("Authorization") != f"Bearer {SECRET}":
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        raw = json.dumps({"data": [{"id": "model-b"}, {"id": "model-a"}, {"id": "model-a"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


@pytest.fixture
def keyed_server():
    _Keyed.seen_auth, _Keyed.hits = [], 0
    server = HTTPServer(("127.0.0.1", 0), _Keyed)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1", _Keyed
    server.shutdown()
    server.server_close()


def endpoint(url, **kw):
    return {"base_url": url, "kind": "local", "region": "", "operator": "test", **kw}


# ------------------------------------------------------------------ the key's environment name

@pytest.mark.parametrize("name", ["TYPHOON_API_KEY", "MY_PROVIDER_TOKEN", "ACME_SECRET", "OPENROUTER_API_KEY", "A1_KEY"])
def test_credential_looking_names_are_accepted(name):
    assert model_setup.check_key_env_name(name) == name


@pytest.mark.parametrize("name", ["PATH", "PYTHONPATH", "DELENTIA_API_TOKEN", "DELENTIA_APPROVER_PUBKEYS", "HOME", "lowercase_key",
                                  "1_KEY", "", "X" * 70 + "_KEY", "BAD NAME_KEY", "OK;rm_KEY"])
def test_anything_that_is_not_a_credential_name_is_refused(name):
    with pytest.raises(model_setup.SetupError):
        model_setup.check_key_env_name(name)


def test_a_key_with_a_line_break_or_nothing_is_refused():
    for bad in ("", "a\nb", "a\rb", "x" * 5000):
        with pytest.raises(model_setup.SetupError):
            model_setup.set_session_key("ROUND52_PROVIDER_API_KEY", bad)
    assert "ROUND52_PROVIDER_API_KEY" not in os.environ


# ------------------------------------------------------------------ saving

def test_the_key_goes_to_memory_and_never_to_a_file(isolated):
    view = model_setup.apply_selection("openai-compat", "model-a", endpoint=endpoint(
        "http://localhost:8000/v1", credential_env="ROUND52_PROVIDER_API_KEY"), api_key=SECRET)
    try:
        assert os.environ["ROUND52_PROVIDER_API_KEY"] == SECRET
        assert view["credential_present"] and view["credential_env"] == "ROUND52_PROVIDER_API_KEY" and view["key_kept_in_memory"]
        assert SECRET not in json.dumps(view)
        for path in isolated.iterdir():
            assert SECRET not in path.read_text(encoding="utf-8", errors="replace")
        assert "ROUND52_PROVIDER_API_KEY" in (isolated / "model.json").read_text(encoding="utf-8")     # the NAME is stored
    finally:
        os.environ.pop("ROUND52_PROVIDER_API_KEY", None)


def test_a_key_for_a_name_that_is_not_a_credential_is_refused_before_anything_is_saved(isolated):
    path_before = os.environ.get("PATH")
    with pytest.raises(model_setup.SetupError):
        model_setup.apply_selection("openai-compat", "m", endpoint=endpoint("http://localhost:1/v1", credential_env="PATH"), api_key=SECRET)
    assert os.environ.get("PATH") == path_before
    assert not (isolated / "model.json").exists()


def test_a_key_with_a_credential_shaped_name_that_is_protected_is_refused(isolated):
    with pytest.raises(model_setup.SetupError):
        model_setup.apply_selection("openai-compat", "m", endpoint=endpoint("http://localhost:1/v1", credential_env="DELENTIA_API_TOKEN"),
                                    api_key=SECRET)
    assert os.environ.get("DELENTIA_API_TOKEN") != SECRET
    assert not (isolated / "model.json").exists()


def test_a_key_with_no_variable_name_to_hold_it_is_refused(isolated):
    with pytest.raises(model_setup.SetupError, match="no environment variable"):
        model_setup.apply_selection("openai-compat", "m", endpoint=endpoint("http://localhost:1/v1"), api_key=SECRET)


def test_openrouter_keeps_its_key_under_the_standard_name(isolated):
    try:
        view = model_setup.apply_selection("openrouter", "some/model", api_key=SECRET)
        assert os.environ["OPENROUTER_API_KEY"] == SECRET and view["openrouter_key_present"]
        assert SECRET not in (isolated / "model.json").read_text(encoding="utf-8")
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_a_per_profile_choice_leaves_the_default_alone(isolated):
    model_setup.apply_selection("ollama", "qwen2.5:7b")
    view = model_setup.apply_selection("ollama", "llama3.2:3b", profile="researcher")
    assert view["selection"]["model"] == "qwen2.5:7b" and view["profiles"]["researcher"]["model"] == "llama3.2:3b"


def test_an_openai_compat_choice_needs_its_endpoint(isolated):
    with pytest.raises(model_setup.SetupError, match="endpoint"):
        model_setup.apply_selection("openai-compat", "m")
    with pytest.raises(model_config.ModelConfigError):
        model_setup.apply_selection("openai-compat", "m", endpoint=endpoint("ftp://x/v1"))
    with pytest.raises(model_config.ModelConfigError):
        model_setup.apply_selection("openai-compat", "m", endpoint={**endpoint("http://x/v1"), "kind": "in_region", "region": ""})


def test_the_view_says_whether_the_saved_endpoint_would_be_allowed(isolated):
    model_setup.apply_selection("openai-compat", "m", endpoint={"base_url": "https://api.example.com/v1", "kind": "cross_border",
                                                                  "region": "", "operator": "x"})
    assert model_setup.current_view()["endpoint_verdict"]["allowed"] is None          # no policy: nothing restricts
    residency.save_policy(SovereigntyPolicy(home_region="TH", allowed_regions=["TH"], allow_cross_border=False))
    view = model_setup.current_view()
    assert view["endpoint_verdict"]["enforced"] is True and view["endpoint_verdict"]["allowed"] is False
    model_setup.apply_selection("openai-compat", "m", endpoint={"base_url": "https://llm.example.th/v1", "kind": "in_region",
                                                                  "region": "TH", "operator": "x"})
    assert model_setup.current_view()["endpoint_verdict"]["allowed"] is True


# ------------------------------------------------------------------ testing an endpoint

def run(coro):
    return asyncio.run(coro)


def test_the_probe_lists_the_models_the_endpoint_really_serves(keyed_server):
    url, server = keyed_server
    result = run(model_setup.probe_endpoint(endpoint(url), SECRET))
    assert result["reachable"] and result["models"] == ["model-a", "model-b"] and result["key_sent"] and result["error"] is None
    assert server.seen_auth == [f"Bearer {SECRET}"]
    assert SECRET not in json.dumps(result)


def test_a_missing_or_wrong_key_is_reported_without_echoing_either(keyed_server):
    url, _ = keyed_server
    none = run(model_setup.probe_endpoint(endpoint(url)))
    assert none["reachable"] and "requires a key" in none["error"] and none["models"] == []
    wrong = run(model_setup.probe_endpoint(endpoint(url), "sk-wrong-key-value"))
    assert "refused the key" in wrong["error"] and "sk-wrong" not in json.dumps(wrong)


def test_the_probe_uses_the_key_from_the_named_variable(keyed_server, monkeypatch):
    url, _ = keyed_server
    monkeypatch.setenv("ROUND52_PROVIDER_API_KEY", SECRET)
    result = run(model_setup.probe_endpoint(endpoint(url, credential_env="ROUND52_PROVIDER_API_KEY")))
    assert result["models"] == ["model-a", "model-b"]


def test_a_blocked_endpoint_is_not_contacted_at_all(keyed_server):
    url, server = keyed_server
    residency.save_policy(SovereigntyPolicy(home_region="TH", allowed_regions=["TH"], allow_cross_border=False))
    result = run(model_setup.probe_endpoint({**endpoint(url), "kind": "cross_border"}, SECRET))
    assert result["contacted"] is False and "Not contacted" in result["error"] and result["verdict"]["allowed"] is False
    assert server.hits == 0
    local = run(model_setup.probe_endpoint(endpoint(url), SECRET))        # declared local: allowed
    assert local["contacted"] and server.hits == 1


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/v1", "http://169.254.169.254/latest/meta-data", "http://[fe80::1]/v1",
                                 "http://metadata.google.internal/computeMetadata", "not a url", ""])
def test_dangerous_or_malformed_addresses_are_not_probed(url):
    result = run(model_setup.probe_endpoint({"base_url": url, "kind": "local", "region": ""}))
    assert result["contacted"] is False and result["reachable"] is False and result["error"]


def test_an_unreachable_endpoint_reports_the_kind_of_failure_not_the_address():
    result = run(model_setup.probe_endpoint(endpoint("http://127.0.0.1:9/v1?token=hunter2"), SECRET))
    assert result["contacted"] and not result["reachable"] and result["error"].startswith("could not connect")
    assert "hunter2" not in json.dumps(result) and SECRET not in json.dumps(result)


def test_a_server_that_is_not_openai_shaped_is_said_so():
    class Odd(BaseHTTPRequestHandler):
        def do_GET(self):
            raw = b"<html>hello</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass
    server = HTTPServer(("127.0.0.1", 0), Odd)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = run(model_setup.probe_endpoint(endpoint(f"http://127.0.0.1:{server.server_port}/v1")))
        assert result["reachable"] and result["models"] == [] and "OpenAI-style" in result["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_the_probe_works_against_the_scripted_model_used_by_the_pipeline_tests():
    with ScriptedModel(competent, model_id="scripted-9") as model:
        result = run(model_setup.probe_endpoint(endpoint(model.base_url)))
        assert result["models"] == ["scripted-9"] and model.calls == 0     # no prompt was sent


# ------------------------------------------------------------------ the presets

def test_presets_are_well_formed():
    catalog = provider_presets.catalog()
    ids = [p["id"] for p in catalog["providers"]]
    assert len(ids) == len(set(ids))
    codes = {c["code"] for c in catalog["countries"]}
    for p in catalog["providers"]:
        assert p["base_url"].startswith(("http://", "https://")) and not p["base_url"].endswith("/")
        assert p["country"] in codes
        if p["credential_env"]:
            model_setup.check_key_env_name(p["credential_env"])      # a preset can never suggest a name the page would refuse
        model_config.validate_endpoint({"base_url": p["base_url"], "kind": p["suggested_data_location"], "region": "",
                                        "credential_env": p["credential_env"]})
    assert "My own machine" in " ".join(c["name"] for c in catalog["countries"])


def test_no_preset_claims_to_process_data_in_a_country():
    for p in provider_presets.PRESETS:
        assert p["suggested_data_location"] in ("local", "cross_border"), p["id"]
        assert (p["suggested_data_location"] == "local") == (p["country"] == provider_presets.LOCAL), p["id"]


def test_every_local_preset_points_at_this_machine():
    for p in provider_presets.PRESETS:
        if p["country"] == provider_presets.LOCAL:
            assert "://localhost" in p["base_url"] or "://127.0.0.1" in p["base_url"], p["id"]


# ------------------------------------------------------------------ the Desk API

@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_api_setup_returns_state_and_presets(client):
    data = client.get("/v1/desk/models/setup").json()
    assert data["selection"]["provider"] and data["presets"]["providers"] and "credential_present" in data


def test_api_save_endpoint_then_read_it_back_without_the_key(client, isolated):
    body = {"provider": "openai-compat", "model": "typhoon-v2.5-30b-a3b-instruct", "api_key": SECRET,
            "endpoint": {"base_url": "https://api.opentyphoon.ai/v1", "kind": "cross_border", "region": "", "operator": "OpenTyphoon",
                         "credential_env": "ROUND52_PROVIDER_API_KEY"}}
    try:
        saved = client.post("/v1/desk/models", json=body)
        assert saved.status_code == 200 and saved.json()["key_kept_in_memory"]
        assert SECRET not in saved.text
        again = client.get("/v1/desk/models/setup")
        assert SECRET not in again.text
        assert again.json()["selection"]["provider"] == "openai-compat" and again.json()["credential_present"]
        assert again.json()["endpoint"]["base_url"] == "https://api.opentyphoon.ai/v1"
        assert SECRET not in (isolated / "model.json").read_text(encoding="utf-8")
    finally:
        os.environ.pop("ROUND52_PROVIDER_API_KEY", None)


@pytest.mark.parametrize("body", [
    {"provider": "nope", "model": "x"},
    {"provider": "openai-compat", "model": "x"},
    {"provider": "openai-compat", "model": "x", "endpoint": "not a dict"},
    {"provider": "openai-compat", "model": "x", "endpoint": {"base_url": "gopher://x", "kind": "local"}},
    {"provider": "openai-compat", "model": "x", "api_key": "k", "endpoint": {"base_url": "http://x/v1", "kind": "local", "credential_env": "PATH"}},
    {"provider": "ollama", "model": ""},
])
def test_api_rejects_bad_choices_with_400_and_leaks_nothing(client, body):
    response = client.post("/v1/desk/models", json=body)
    assert response.status_code == 400 and "Traceback" not in response.text


def test_api_test_endpoint_lists_models_and_hides_the_key(client, keyed_server):
    url, _ = keyed_server
    response = client.post("/v1/desk/models/test", json={"endpoint": endpoint(url), "api_key": SECRET})
    assert response.status_code == 200 and response.json()["models"] == ["model-a", "model-b"]
    assert SECRET not in response.text
    assert client.post("/v1/desk/models/test", json={"endpoint": "x"}).status_code == 400
    assert client.post("/v1/desk/models/test", json={"endpoint": endpoint(url), "api_key": 5}).status_code == 400


def test_api_sovereignty_edit_writes_the_policy_and_describes_it(client, isolated):
    response = client.post("/v1/desk/sovereignty", json={"home_region": "th", "allowed_regions": ["JP"], "allow_cross_border": False,
                                                         "pii_policy": "redact", "legal_basis": "test"})
    assert response.status_code == 200 and response.json()["policy"]["allowed_regions"] == ["TH", "JP"]
    assert residency.load_policy().home_region == "TH"
    assert client.post("/v1/desk/sovereignty", json={"home_region": "THAILAND"}).status_code == 400
    assert client.post("/v1/desk/sovereignty", json={"home_region": "TH", "pii_policy": "whatever"}).status_code == 400


def test_api_sovereignty_edit_is_refused_while_the_environment_sets_the_policy(client, monkeypatch):
    monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
    response = client.post("/v1/desk/sovereignty", json={"home_region": "JP"})
    assert response.status_code == 409 and residency.HOME_REGION_ENV in response.json()["detail"]


# ------------------------------------------------------------------ the shell the agent runs commands in

def test_sandboxed_commands_do_not_inherit_credentials(monkeypatch):
    from rct_control_plane.sandbox import run_sandboxed, scrubbed_environment
    monkeypatch.setenv("ROUND52_PROVIDER_API_KEY", SECRET)
    monkeypatch.setenv("DELENTIA_AUDIT_SIGNING_KEY", "/some/path/key.pem")
    monkeypatch.setenv("ROUND52_HARMLESS_SETTING", "visible")
    env = scrubbed_environment()
    assert "ROUND52_PROVIDER_API_KEY" not in env and "DELENTIA_AUDIT_SIGNING_KEY" not in env
    assert env["ROUND52_HARMLESS_SETTING"] == "visible" and "PATH" in {k.upper() for k in env}
    command = "echo %ROUND52_PROVIDER_API_KEY%" if os.name == "nt" else "echo $ROUND52_PROVIDER_API_KEY"
    result = run_sandboxed(command, approved=True)      # Round 66: any command that reads an environment variable now needs approval; this test is about what the shell INHERITS
    assert result.blocked_reason is None
    assert SECRET not in result.stdout
