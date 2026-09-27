"""
Round 48: user-selectable model (model_config.py, llm_provider.get_default_provider,
`delentia model show/list/set`). No network: OpenRouter/Ollama catalogs are
served by httpx.MockTransport, and the config file lives in tmp_path.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import httpx
import pytest
from click.testing import CliRunner

from rct_control_plane import model_config as mc
from rct_control_plane.llm_provider import OllamaProvider, OpenRouterProvider, get_default_provider


@pytest.fixture(autouse=True)
def _isolated_model_env(monkeypatch, tmp_path):
    for var in ("DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    cfg = tmp_path / "model.json"
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(cfg))
    return cfg


OPENROUTER_CATALOG = {
    "data": [
        {"id": "anthropic/claude-sonnet-5", "context_length": 200000,
         "pricing": {"prompt": "0.000003", "completion": "0.000015"},
         "supported_parameters": ["tools", "response_format", "temperature"]},
        {"id": "vendor/json-only", "context_length": 32000,
         "pricing": {"prompt": "0.0000001", "completion": "0.0000002"},
         "supported_parameters": ["structured_outputs"]},
        {"id": "vendor/plain-chat", "context_length": 8000,
         "pricing": {"prompt": "0", "completion": "0"},
         "supported_parameters": ["temperature"]},
        {"no_id": True},
    ]
}


def _openrouter_client():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(mc.OPENROUTER_MODELS_URL)
        assert "authorization" not in {k.lower() for k in request.headers}  # catalog needs no key
        return httpx.Response(200, json=OPENROUTER_CATALOG)
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestResolution:
    def test_no_env_no_config_is_the_pre_round_48_default(self):
        sel = mc.resolve_model_selection()
        assert (sel.provider, sel.model) == ("ollama", "qwen2.5:7b")
        assert (sel.provider_source, sel.model_source) == ("builtin", "builtin")

    def test_config_default_is_used(self, _isolated_model_env):
        mc.save_model_selection("openrouter", "vendor/json-only")
        sel = mc.resolve_model_selection()
        assert (sel.provider, sel.model, sel.model_source) == ("openrouter", "vendor/json-only", "config")

    def test_env_beats_config(self, monkeypatch):
        mc.save_model_selection("openrouter", "vendor/json-only")
        monkeypatch.setenv("DELENTIA_LLM_MODEL", "anthropic/claude-sonnet-5")
        sel = mc.resolve_model_selection()
        assert sel.model == "anthropic/claude-sonnet-5"
        assert sel.model_source == "env:DELENTIA_LLM_MODEL"

    def test_argument_beats_env(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openrouter")
        sel = mc.resolve_model_selection(provider="ollama", model="llama3:8b")
        assert (sel.provider, sel.model) == ("ollama", "llama3:8b")

    def test_profile_entry_beats_config_default(self):
        mc.save_model_selection("openrouter", "vendor/json-only")
        mc.save_model_selection("ollama", "llama3:8b", profile="researcher")
        sel = mc.resolve_model_selection(profile="researcher")
        assert (sel.provider, sel.model) == ("ollama", "llama3:8b")
        assert sel.model_source == "config:profiles.researcher"
        # Other profiles still get the default.
        assert mc.resolve_model_selection(profile="other").model == "vendor/json-only"

    def test_model_configured_for_another_provider_is_not_applied(self, monkeypatch):
        mc.save_model_selection("openrouter", "vendor/json-only")
        monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "ollama")
        sel = mc.resolve_model_selection()
        # An OpenRouter id is meaningless to Ollama -> builtin Ollama model.
        assert (sel.provider, sel.model, sel.model_source) == ("ollama", "qwen2.5:7b", "builtin")

    def test_unknown_provider_is_rejected(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "made-up")
        with pytest.raises(mc.ModelConfigError):
            mc.resolve_model_selection()

    def test_profile_has_model_override(self):
        assert mc.profile_has_model_override("researcher") is False
        mc.save_model_selection("ollama", "llama3:8b", profile="researcher")
        assert mc.profile_has_model_override("researcher") is True
        assert mc.profile_has_model_override(None) is False


class TestConfigFile:
    def test_save_writes_json_outside_any_key(self, _isolated_model_env):
        path = mc.save_model_selection("ollama", "llama3:8b")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"provider": "ollama", "model": "llama3:8b"}

    def test_refuses_to_persist_anything_that_looks_like_a_secret(self, _isolated_model_env):
        _isolated_model_env.write_text(json.dumps({"openrouter_api_key": "sk-or-v1-x"}), encoding="utf-8")
        with pytest.raises(mc.ModelConfigError, match="API keys belong in env vars"):
            mc.save_model_selection("ollama", "llama3:8b")

    def test_corrupt_config_is_a_clear_error(self, _isolated_model_env):
        _isolated_model_env.write_text("{not json", encoding="utf-8")
        with pytest.raises(mc.ModelConfigError):
            mc.resolve_model_selection()

    def test_empty_model_is_rejected(self):
        with pytest.raises(mc.ModelConfigError):
            mc.save_model_selection("ollama", "  ")


class TestGetDefaultProvider:
    def test_ollama_gets_the_selected_model(self):
        mc.save_model_selection("ollama", "llama3:8b")
        p = get_default_provider()
        assert isinstance(p, OllamaProvider) and p.model == "llama3:8b"

    def test_openrouter_gets_the_selected_model_when_key_is_set(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-not-real")
        mc.save_model_selection("openrouter", "vendor/json-only")
        p = get_default_provider()
        assert isinstance(p, OpenRouterProvider) and p.model == "vendor/json-only"

    def test_openrouter_without_key_falls_back_to_ollama_builtin_model(self):
        mc.save_model_selection("openrouter", "vendor/json-only")
        p = get_default_provider()
        assert isinstance(p, OllamaProvider)
        assert p.model == "qwen2.5:7b"  # never hands an OpenRouter id to Ollama

    def test_profile_argument_is_honoured(self):
        mc.save_model_selection("ollama", "llama3:8b", profile="researcher")
        assert get_default_provider(profile="researcher").model == "llama3:8b"
        assert get_default_provider().model == "qwen2.5:7b"


class TestCatalogs:
    def test_openrouter_catalog_is_parsed_with_capabilities_and_prices(self):
        models = {m.id: m for m in mc.list_openrouter_models(client=_openrouter_client())}
        assert set(models) == {"anthropic/claude-sonnet-5", "vendor/json-only", "vendor/plain-chat"}
        sonnet = models["anthropic/claude-sonnet-5"]
        assert sonnet.supports_json_mode and sonnet.supports_tools
        assert sonnet.prompt_price_per_mtok == 3.0 and sonnet.completion_price_per_mtok == 15.0
        assert models["vendor/json-only"].supports_json_mode and not models["vendor/json-only"].supports_tools
        assert not models["vendor/plain-chat"].supports_json_mode

    def test_filter_hides_models_that_cannot_drive_the_loop(self):
        models = mc.list_openrouter_models(client=_openrouter_client())
        ids = [m.id for m in mc.filter_models(models)]
        assert ids == ["anthropic/claude-sonnet-5", "vendor/json-only"]
        assert [m.id for m in mc.filter_models(models, agent_capable_only=False, search="plain")] == ["vendor/plain-chat"]

    def test_ollama_tags_are_listed(self):
        def handler(request):
            assert request.url.path == "/api/tags"
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3:8b"}]})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        ids = [m.id for m in mc.list_ollama_models(llm_url="http://ollama.test", client=client)]
        assert ids == ["qwen2.5:7b", "llama3:8b"]


class TestCli:
    @pytest.fixture
    def cli(self):
        from rct_control_plane.cli import cli
        return cli

    @pytest.fixture
    def fake_catalog(self, monkeypatch):
        monkeypatch.setattr(mc, "list_openrouter_models",
                            lambda client=None, timeout=20.0: mc.parse_openrouter_models(OPENROUTER_CATALOG))

    def test_show_reports_value_and_source(self, cli):
        result = CliRunner().invoke(cli, ["model", "show", "-o", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["provider"] == "ollama" and data["model_source"] == "builtin"
        assert data["openrouter_key_set"] is False

    def test_set_verifies_against_catalog_then_saves(self, cli, fake_catalog, _isolated_model_env):
        result = CliRunner().invoke(cli, ["model", "set", "anthropic/claude-sonnet-5", "--provider", "openrouter"])
        assert result.exit_code == 0, result.output
        assert json.loads(_isolated_model_env.read_text(encoding="utf-8"))["model"] == "anthropic/claude-sonnet-5"

    def test_set_rejects_unknown_model(self, cli, fake_catalog, _isolated_model_env):
        result = CliRunner().invoke(cli, ["model", "set", "vendor/does-not-exist", "--provider", "openrouter"])
        assert result.exit_code == 1
        assert not _isolated_model_env.exists()

    def test_set_rejects_model_without_json_mode(self, cli, fake_catalog, _isolated_model_env):
        result = CliRunner().invoke(cli, ["model", "set", "vendor/plain-chat", "--provider", "openrouter"])
        assert result.exit_code == 1
        assert "JSON mode" in result.output
        assert not _isolated_model_env.exists()

    def test_set_for_a_profile_with_no_verify(self, cli, _isolated_model_env):
        result = CliRunner().invoke(cli, ["model", "set", "llama3:8b", "--provider", "ollama",
                                          "--profile", "researcher", "--no-verify"])
        assert result.exit_code == 0, result.output
        data = json.loads(_isolated_model_env.read_text(encoding="utf-8"))
        assert data == {"profiles": {"researcher": {"provider": "ollama", "model": "llama3:8b"}}}

    def test_list_shows_only_agent_capable_models_by_default(self, cli, fake_catalog):
        result = CliRunner().invoke(cli, ["model", "list", "-o", "json"])
        assert result.exit_code == 0, result.output
        assert [m["id"] for m in json.loads(result.output)] == ["anthropic/claude-sonnet-5", "vendor/json-only"]

    def test_list_reports_network_errors_without_a_traceback(self, cli, monkeypatch):
        def boom(client=None, timeout=20.0):
            raise httpx.ConnectError("offline")
        monkeypatch.setattr(mc, "list_openrouter_models", boom)
        result = CliRunner().invoke(cli, ["model", "list"])
        assert result.exit_code == 1
        assert "could not list openrouter models" in result.output
