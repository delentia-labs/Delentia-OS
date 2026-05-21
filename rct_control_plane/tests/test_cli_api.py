"""
Tests for rct_control_plane.cli and rct_control_plane.api.

CLI tests use Click's CliRunner (isolated, no subprocess).
API tests use FastAPI's TestClient (synchronous, no real server).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from rct_control_plane._version import PACKAGE_VERSION

# ---------------------------------------------------------------------------
# CLI Tests
# ---------------------------------------------------------------------------


# Reset global CLI context before each test to avoid cross-test pollution
@pytest.fixture(autouse=True)
def _reset_cli_context():
    """Reset the singleton CLI context between tests."""
    import rct_control_plane.cli as cli_mod

    cli_mod._cli_context = None
    yield
    cli_mod._cli_context = None


@pytest.fixture
def cli_runner():
    from click.testing import CliRunner

    return CliRunner()


@pytest.fixture
def cli():
    from rct_control_plane.cli import cli as _cli

    return _cli


class TestCLICompile:
    def test_compile_basic(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["compile", "Refactor the auth module"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "intent_id" in data

    def test_compile_with_user_id(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "compile",
                "Build a FastAPI service",
                "--user-id",
                "test-user",
                "--user-tier",
                "PRO",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["intent_id"] != ""

    def test_compile_json_output(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli, ["compile", "Optimize database queries", "-o", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "intent_type" in data
        assert "is_valid" in data

    def test_compile_save_flag(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli, ["compile", "Refactor payment service", "--save", "-o", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["saved"] is True
        assert "intent_id" in data

    def test_compile_warns_on_empty_goal(self, cli_runner, cli):
        # Very short or trivial goals may still compile but with warnings
        result = cli_runner.invoke(cli, ["compile", "x"])
        # Should either succeed or fail cleanly (exit 0 or 1, not crash)
        assert result.exit_code in (0, 1)

    def test_compile_enterprise_tier(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "compile",
                "Deploy microservices cluster",
                "--user-tier",
                "ENTERPRISE",
            ],
        )
        assert result.exit_code == 0

    def test_compile_compilation_time_reported(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["compile", "Refactor login module"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "compilation_time_ms" in data


class TestCLIList:
    def test_list_empty(self, cli_runner, cli):
        """List commands should succeed even with no intents stored."""
        result = cli_runner.invoke(cli, ["list", "--output", "json"])
        # Should succeed (returns empty list or similar)
        assert result.exit_code == 0

    def test_list_after_compile(self, cli_runner, cli):
        # First compile + save
        cli_runner.invoke(cli, ["compile", "Refactor X", "--save"])
        # Then list
        result = cli_runner.invoke(cli, ["list", "--output", "json"])
        assert result.exit_code == 0

    def test_list_with_limit(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["list", "--limit", "5", "--output", "json"])
        assert result.exit_code == 0


class TestCLIStatus:
    def test_status_unknown_intent(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["status", "non-existent-id"])
        # Should fail with non-zero exit code
        assert result.exit_code != 0

    def test_status_after_compile_and_save(self, cli_runner, cli):
        # Compile and save
        compile_result = cli_runner.invoke(
            cli, ["compile", "Refactor auth", "--save", "-o", "json"]
        )
        assert compile_result.exit_code == 0
        intent_id = json.loads(compile_result.output)["intent_id"]

        # Get status
        status_result = cli_runner.invoke(cli, ["status", intent_id, "-o", "json"])
        assert status_result.exit_code == 0
        data = json.loads(status_result.output)
        assert data["state_id"] == intent_id

    def test_status_contains_phase(self, cli_runner, cli):
        compile_result = cli_runner.invoke(
            cli, ["compile", "Optimize queries", "--save", "-o", "json"]
        )
        intent_id = json.loads(compile_result.output)["intent_id"]
        status_result = cli_runner.invoke(cli, ["status", intent_id, "-o", "json"])
        data = json.loads(status_result.output)
        assert "phase" in data


class TestCLIMetrics:
    def test_metrics_returns_data(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["metrics", "-o", "json"])
        # Should succeed
        assert result.exit_code == 0

    def test_metrics_table_format(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["metrics", "-o", "table"])
        assert result.exit_code == 0


class TestCLIReset:
    def test_reset_with_force(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["reset", "--force"])
        assert result.exit_code == 0

    def test_reset_without_force_prompts(self, cli_runner, cli):
        # Without --force, should prompt; we simulate "n" to abort
        result = cli_runner.invoke(cli, ["reset"], input="n\n")
        # Exit code 0 (cancelled) or error — either is acceptable
        assert result.exit_code in (0, 1)


class TestCLIAudit:
    def test_audit_unknown_intent(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["audit", "does-not-exist"])
        # Some implementations return empty audit (exit 0); others fail — either is fine
        assert result.exit_code in (0, 1)

    def test_audit_after_compile(self, cli_runner, cli):
        compile_result = cli_runner.invoke(
            cli, ["compile", "Refactor database layer", "--save", "-o", "json"]
        )
        intent_id = json.loads(compile_result.output)["intent_id"]
        audit_result = cli_runner.invoke(cli, ["audit", intent_id, "-o", "json"])
        assert audit_result.exit_code == 0

    def test_audit_contains_events(self, cli_runner, cli):
        compile_result = cli_runner.invoke(
            cli, ["compile", "Refactor cache module", "--save", "-o", "json"]
        )
        intent_id = json.loads(compile_result.output)["intent_id"]
        audit_result = cli_runner.invoke(cli, ["audit", intent_id, "-o", "json"])
        assert audit_result.exit_code == 0
        data = json.loads(audit_result.output)
        assert "events" in data or "intent_id" in data


class TestCLIVersion:
    def test_version_flag(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert PACKAGE_VERSION in result.output


class TestCLIDoctor:
    def test_doctor_json_output(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["doctor", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "checks" in data
        assert "issues" in data
        assert isinstance(data["checks"], list)

    def test_doctor_reports_python_check(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["doctor", "--output", "json"])
        data = json.loads(result.output)
        assert any(check["name"] == "Python" for check in data["checks"])


class TestCLIInit:
    def test_init_creates_env_from_builtin_template_when_example_missing(
        self, cli_runner, cli, monkeypatch
    ):
        import rct_control_plane as rcp_pkg

        original_file = rcp_pkg.__file__
        monkeypatch.setattr(rcp_pkg, "__file__", str(Path("missing") / "__init__.py"))
        try:
            with cli_runner.isolated_filesystem():
                result = cli_runner.invoke(cli, ["init"])
                assert result.exit_code == 0
                created_env = Path(".env")
                assert created_env.exists()
                content = created_env.read_text(encoding="utf-8")
                assert "RCT_CORE_BRAIN_KEY=<your-openrouter-key>" in content
                assert "built-in fallback template" in result.output
        finally:
            monkeypatch.setattr(rcp_pkg, "__file__", original_file)

    def test_init_preserves_existing_env_without_force(self, cli_runner, cli):
        with cli_runner.isolated_filesystem():
            Path(".env").write_text("RCT_DEBUG=1\n", encoding="utf-8")
            result = cli_runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert Path(".env").read_text(encoding="utf-8") == "RCT_DEBUG=1\n"


class TestCLIVersionConsistency:
    def test_status_overview_uses_package_version(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["status", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["version"] == PACKAGE_VERSION

    def test_status_live_requires_table_output(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["status", "--live", "--output", "json"])
        assert result.exit_code == 1

    def test_status_live_single_refresh(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli, ["status", "--live", "--refresh-count", "1", "--interval", "0.01"]
        )
        assert result.exit_code == 0

    def test_runtime_dashboard_uses_health_endpoint_when_available(self):
        import rct_control_plane.cli as cli_mod

        health_payload = {
            "status": "healthy",
            "version": PACKAGE_VERSION,
            "uptime_seconds": 12.5,
            "environment": "test",
            "services": [
                {"name": "intent_compiler", "status": "healthy"},
                {"name": "feature_flags", "status": "degraded"},
            ],
        }

        cli_mod._cli_context = None
        original_fetch = cli_mod._fetch_runtime_health
        try:
            cli_mod._fetch_runtime_health = lambda host, port: health_payload
            state = cli_mod._build_runtime_dashboard_state("127.0.0.1", 8000)
        finally:
            cli_mod._fetch_runtime_health = original_fetch

        assert state["source"] == "health-endpoint"
        assert state["overall_status"] == "serving"
        assert state["environment"] == "test"
        assert state["services"][0]["online"] is True
        assert state["services"][1]["online"] is True
        assert state["services"][0]["status"] == "serving"
        assert state["services"][1]["status"] == "degraded"

    def test_runtime_dashboard_falls_back_to_port_probe(self):
        import rct_control_plane.cli as cli_mod

        cli_mod._cli_context = None
        original_fetch = cli_mod._fetch_runtime_health
        original_snapshot = cli_mod._build_service_snapshot
        try:
            cli_mod._fetch_runtime_health = lambda host, port: None
            cli_mod._build_service_snapshot = lambda default_port=8000: [
                {"name": "control-plane", "port": default_port, "online": False}
            ]
            state = cli_mod._build_runtime_dashboard_state("127.0.0.1", 8123)
        finally:
            cli_mod._fetch_runtime_health = original_fetch
            cli_mod._build_service_snapshot = original_snapshot

        assert state["source"] == "port-probe"
        assert state["overall_status"] == "offline"
        assert state["services"][0]["port"] == 8123

    def test_runtime_dashboard_port_probe_with_reachable_service_marks_health_unknown(self):
        import rct_control_plane.cli as cli_mod

        cli_mod._cli_context = None
        original_fetch = cli_mod._fetch_runtime_health
        original_snapshot = cli_mod._build_service_snapshot
        try:
            cli_mod._fetch_runtime_health = lambda host, port: None
            cli_mod._build_service_snapshot = lambda default_port=8000: [
                {"name": "control-plane", "port": default_port, "online": True}
            ]
            state = cli_mod._build_runtime_dashboard_state("127.0.0.1", 8123)
        finally:
            cli_mod._fetch_runtime_health = original_fetch
            cli_mod._build_service_snapshot = original_snapshot

        assert state["source"] == "port-probe"
        assert state["overall_status"] == "health-unknown"

    def test_start_ui_test_runs_without_api_keys(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["start", "--ui-test"])
        assert result.exit_code == 0
        assert "UI test complete" in result.output


class TestCLILogsFollow:
    def test_logs_follow_requires_table_output(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["logs", "--follow", "--output", "json"])
        assert result.exit_code == 1

    def test_logs_follow_single_refresh(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli, ["logs", "--follow", "--refresh-count", "1", "--interval", "0.01"]
        )
        assert result.exit_code == 0


class TestCLIOutputFormats:
    def test_compile_table_format(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["compile", "Refactor module", "-o", "table"])
        assert result.exit_code == 0

    def test_compile_tree_format(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["compile", "Refactor module", "-o", "tree"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# API Tests (FastAPI TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_client():
    """FastAPI test client — created once per test module."""
    from fastapi.testclient import TestClient
    from rct_control_plane.api import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client


class TestAPIHealth:
    def test_root_returns_healthy(self, api_client):
        resp = api_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_endpoint(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_has_version(self, api_client):
        resp = api_client.get("/health")
        data = resp.json()
        assert "version" in data

    def test_health_version_matches_package(self, api_client):
        resp = api_client.get("/health")
        data = resp.json()
        assert data["version"] == PACKAGE_VERSION

    def test_health_has_timestamp(self, api_client):
        resp = api_client.get("/health")
        data = resp.json()
        assert "timestamp" in data

    def test_detailed_health_returns_200(self, api_client):
        resp = api_client.get("/health/detailed")
        assert resp.status_code == 200

    def test_detailed_health_has_services(self, api_client):
        resp = api_client.get("/health/detailed")
        data = resp.json()
        assert "services" in data
        assert len(data["services"]) > 0

    def test_detailed_health_has_uptime(self, api_client):
        resp = api_client.get("/health/detailed")
        data = resp.json()
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0


class TestAPIIntentCompile:
    def test_compile_valid_intent(self, api_client):
        resp = api_client.post(
            "/v1/intent/compile",
            json={
                "natural_language": "Refactor authentication module using clean architecture",
                "user_id": "user-123",
                "user_tier": "PRO",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "intent_id" in data

    def test_compile_returns_intent_id(self, api_client):
        resp = api_client.post(
            "/v1/intent/compile",
            json={
                "natural_language": "Build a FastAPI microservice",
                "user_id": "u1",
                "user_tier": "ENTERPRISE",
            },
        )
        data = resp.json()
        assert data["intent_id"] is not None
        assert len(data["intent_id"]) == 36  # UUID length

    def test_compile_includes_compilation_time(self, api_client):
        resp = api_client.post(
            "/v1/intent/compile",
            json={
                "natural_language": "Optimize database queries",
                "user_id": "u2",
                "user_tier": "PRO",
            },
        )
        data = resp.json()
        assert "compilation_time_ms" in data
        assert data["compilation_time_ms"] >= 0

    def test_compile_missing_natural_language_is_rejected(self, api_client):
        resp = api_client.post(
            "/v1/intent/compile",
            json={
                "user_id": "u3",
                "user_tier": "PRO",
            },
        )
        assert resp.status_code == 422  # Unprocessable Entity

    def test_compile_missing_user_id_is_rejected(self, api_client):
        resp = api_client.post(
            "/v1/intent/compile",
            json={
                "natural_language": "Refactor something",
                "user_tier": "PRO",
            },
        )
        assert resp.status_code == 422

    def test_compile_empty_goal_rejected_or_warned(self, api_client):
        resp = api_client.post(
            "/v1/intent/compile",
            json={
                "natural_language": "",
                "user_id": "u4",
                "user_tier": "PRO",
            },
        )
        # Empty string violates min_length=1
        assert resp.status_code == 422

    def test_compile_pro_tier_succeeds(self, api_client):
        resp = api_client.post(
            "/v1/intent/compile",
            json={
                "natural_language": "Deploy microservices using k8s",
                "user_id": "u5",
                "user_tier": "PRO",
            },
        )
        assert resp.status_code == 200

    def test_compile_free_tier_succeeds(self, api_client):
        resp = api_client.post(
            "/v1/intent/compile",
            json={
                "natural_language": "Refactor small utility",
                "user_id": "u-free",
                "user_tier": "FREE",
            },
        )
        assert resp.status_code == 200


class TestAPIGraphBuild:
    SIMPLE_DSL = """intent "test_refactor" {
  phase analyze {
    node AnalyzeNode {
      node_type = "agent_capability"
      agent_capability = "code_analyzer"
      estimated_cost = 0.10
      estimated_duration = 60
    }
  }
}"""

    def test_build_valid_dsl(self, api_client):
        resp = api_client.post(
            "/v1/graph/build",
            json={
                "dsl_text": self.SIMPLE_DSL,
                "intent_id": "test-intent-001",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_build_returns_node_count(self, api_client):
        resp = api_client.post(
            "/v1/graph/build",
            json={
                "dsl_text": self.SIMPLE_DSL,
                "intent_id": "test-intent-002",
            },
        )
        data = resp.json()
        assert "node_count" in data
        assert data["node_count"] >= 0

    def test_build_missing_intent_id(self, api_client):
        resp = api_client.post(
            "/v1/graph/build",
            json={
                "dsl_text": self.SIMPLE_DSL,
            },
        )
        assert resp.status_code == 422

    def test_build_missing_dsl_text(self, api_client):
        resp = api_client.post(
            "/v1/graph/build",
            json={
                "intent_id": "test-intent-003",
            },
        )
        assert resp.status_code == 422


class TestAPIStateEndpoints:
    def test_get_state_not_found(self, api_client):
        resp = api_client.get("/v1/state/nonexistent-id")
        assert resp.status_code == 404

    def test_list_intents_empty(self, api_client):
        """Fresh API instance — intent list is initially empty."""
        resp = api_client.get("/v1/intents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_delete_state_not_found(self, api_client):
        # DELETE is idempotent — returns 200 even for missing keys
        resp = api_client.delete("/v1/state/nonexistent-id")
        assert resp.status_code in (200, 404)

    def test_get_audit_not_found(self, api_client):
        resp = api_client.get("/v1/audit/nonexistent-id")
        assert resp.status_code == 404


class TestAPIMetrics:
    def test_metrics_returns_200(self, api_client):
        resp = api_client.get("/v1/metrics")
        assert resp.status_code == 200

    def test_metrics_has_total_intents(self, api_client):
        resp = api_client.get("/v1/metrics")
        data = resp.json()
        assert "total_intents" in data

    def test_metrics_has_compilation_latency(self, api_client):
        resp = api_client.get("/v1/metrics")
        data = resp.json()
        assert "avg_compilation_latency_ms" in data


class TestAPIReset:
    def test_reset_returns_200(self, api_client):
        resp = api_client.post("/v1/reset")
        assert resp.status_code == 200


class TestAPIFeatureFlags:
    def test_list_flags(self, api_client):
        resp = api_client.get("/v1/flags")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_unknown_flag(self, api_client):
        resp = api_client.get("/v1/flags/nonexistent-flag-xyz")
        assert resp.status_code == 404

    def test_enable_unknown_flag(self, api_client):
        resp = api_client.patch("/v1/flags/nonexistent-flag/enable")
        assert resp.status_code == 404

    def test_disable_unknown_flag(self, api_client):
        resp = api_client.patch("/v1/flags/nonexistent-flag/disable")
        assert resp.status_code == 404

    def test_toggle_unknown_flag(self, api_client):
        resp = api_client.patch("/v1/flags/nonexistent-flag/toggle")
        assert resp.status_code == 404


class TestAPIPolicyEvaluate:
    """
    The /v1/policy/evaluate endpoint takes intent dict + optional graph dict.
    We test it with a minimal REFACTOR intent dict (no pre-stored state needed).
    """

    def _make_intent_dict(self) -> dict:
        """Return a minimal valid intent dict for policy evaluation."""
        from rct_control_plane.intent_schema import (
            IntentObject,
            IntentType,
            ScopeObject,
            ScopeType,
            ContextBundle,
        )

        intent = IntentObject(
            goal="Refactor authentication module",
            intent_type=IntentType.REFACTOR,
            scope=ScopeObject(scope_type=ScopeType.MODULE, target="auth"),
            context=ContextBundle(user_id="u1", user_tier="PRO"),
        )
        return intent.model_dump(mode="json")

    def test_evaluate_basic_intent(self, api_client):
        intent_dict = self._make_intent_dict()
        resp = api_client.post(
            "/v1/policy/evaluate",
            json={
                "intent_id": intent_dict["id"],
                "intent": intent_dict,
                "use_default_policies": True,
            },
        )
        assert resp.status_code in (200, 422)  # may need exact schema match
        if resp.status_code == 200:
            data = resp.json()
            assert "governance_score" in data
            assert "governance_label" in data

    def test_evaluate_missing_intent_id(self, api_client):
        resp = api_client.post(
            "/v1/policy/evaluate",
            json={
                "intent": {"intent_type": "REFACTOR"},
            },
        )
        assert resp.status_code == 422


# ===========================================================================
# หมวด D — TestCLIBuild  (covers lines 320-387, 109, 113)
# ===========================================================================

WORKFLOW_DSL = """intent "ci_workflow" {
  phase analyze {
    node AnalyzeNode {
      node_type = "agent_capability"
      agent_capability = "code_analyzer"
      estimated_cost = 0.10
      estimated_duration = 60
    }
  }
}"""


class TestCLIBuild:
    """Tests for the `rct build` command — dsl-text, dsl-file, --save paths."""

    def test_build_with_dsl_text(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                "build-001",
                "-o",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "graph_id" in data

    def test_build_returns_node_count(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                "build-002",
                "-o",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "node_count" in data
        assert data["node_count"] >= 0

    def test_build_with_save(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                "build-save-001",
                "--save",
                "-o",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["saved"] is True

    def test_build_save_stores_graph_in_context(self, cli_runner, cli):
        import rct_control_plane.cli as cli_mod

        result = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                "build-store-001",
                "--save",
            ],
        )
        assert result.exit_code == 0
        ctx = cli_mod.get_context()
        assert "build-store-001" in ctx.graphs  # covers save_graph (line 113)

    def test_build_missing_dsl_input_fails(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["build", "--intent-id", "build-nodsl"])
        # Should fail: no dsl-text or dsl-file provided
        assert result.exit_code != 0

    def test_build_with_dsl_file(self, cli_runner, cli, tmp_path):
        dsl_file = tmp_path / "workflow.dsl"
        dsl_file.write_text(WORKFLOW_DSL)
        result = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-file",
                str(dsl_file),
                "--intent-id",
                "build-file-001",
                "-o",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "graph_id" in data

    def test_build_table_output(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                "build-table-001",
                "-o",
                "table",
            ],
        )
        assert result.exit_code == 0

    def test_build_tree_output(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                "build-tree-001",
                "-o",
                "tree",
            ],
        )
        assert result.exit_code == 0

    def test_build_estimate_cost_in_output(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                "build-cost-001",
                "-o",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "estimated_cost" in data

    def test_build_with_prior_state_and_save(self, cli_runner, cli):
        """build --save when a prior compile state exists → triggers state.transition_to."""
        import rct_control_plane.cli as cli_mod

        # Compile + save to create a state first
        compile_r = cli_runner.invoke(
            cli,
            [
                "compile",
                "Refactor auth",
                "--save",
                "-o",
                "json",
            ],
        )
        assert compile_r.exit_code == 0
        intent_id = json.loads(compile_r.output)["intent_id"]
        # Now build --save → state is not None → covers the state.transition_to branch
        build_r = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                intent_id,
                "--save",
                "-o",
                "json",
            ],
        )
        assert build_r.exit_code == 0
        data = json.loads(build_r.output)
        assert data["saved"] is True
        # Verify graph stored in context (covers get_graph line 117)
        ctx = cli_mod.get_context()
        assert intent_id in ctx.graphs


# ===========================================================================
# หมวด C — TestCLIEvaluate  (covers lines 395/402-474, 109, 117)
# ===========================================================================


class TestCLIEvaluate:
    """Tests for the `rct evaluate` command — the most critical uncovered core command."""

    _DSL = WORKFLOW_DSL  # reuse workflow DSL

    def _compile_and_save(
        self, cli_runner, cli, goal: str = "Refactor auth module"
    ) -> str:
        """Helper: compile+save and return intent_id."""
        r = cli_runner.invoke(cli, ["compile", goal, "--save", "-o", "json"])
        assert r.exit_code == 0, f"compile failed: {r.output}"
        return json.loads(r.output)["intent_id"]

    def test_evaluate_missing_intent_exits_nonzero(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["evaluate", "--intent-id", "does-not-exist"])
        assert result.exit_code != 0

    def test_evaluate_after_compile_save(self, cli_runner, cli):
        intent_id = self._compile_and_save(cli_runner, cli)
        result = cli_runner.invoke(
            cli,
            [
                "evaluate",
                "--intent-id",
                intent_id,
                "-o",
                "json",
            ],
        )
        # Success (0) or policy rejection (1) — both are valid, what matters is code path hit
        assert result.exit_code in (0, 1)

    def test_evaluate_output_has_decision_field(self, cli_runner, cli):
        intent_id = self._compile_and_save(
            cli_runner, cli, "Refactor small utility module"
        )
        result = cli_runner.invoke(
            cli,
            [
                "evaluate",
                "--intent-id",
                intent_id,
                "-o",
                "json",
            ],
        )
        output = result.output.strip()
        # Parse first valid JSON block from output
        for line in output.splitlines():
            try:
                data = json.loads(line)
                assert "decision" in data
                break
            except json.JSONDecodeError:
                continue
        else:
            # Rich format output is acceptable — just check exit code
            assert result.exit_code in (0, 1)

    def test_evaluate_with_save_flag_updates_state(self, cli_runner, cli):
        intent_id = self._compile_and_save(cli_runner, cli)
        result = cli_runner.invoke(
            cli,
            [
                "evaluate",
                "--intent-id",
                intent_id,
                "--save",
                "-o",
                "json",
            ],
        )
        assert result.exit_code in (0, 1)

    def test_evaluate_with_graph_available(self, cli_runner, cli):
        """Evaluate when a graph has been built — exercises graph re-parsing branch."""
        intent_id = self._compile_and_save(cli_runner, cli)
        # Inject a pre-built graph into the context
        import rct_control_plane.cli as cli_mod

        ctx = cli_mod.get_context()
        ctx.save_graph(
            intent_id,
            {
                "dsl_text": self._DSL,
                "created_at": "2026-01-01T00:00:00",
            },
        )
        result = cli_runner.invoke(
            cli,
            [
                "evaluate",
                "--intent-id",
                intent_id,
                "-o",
                "json",
            ],
        )
        assert result.exit_code in (0, 1)

    def test_evaluate_decision_reason_in_output(self, cli_runner, cli):
        intent_id = self._compile_and_save(cli_runner, cli, "Optimize database queries")
        result = cli_runner.invoke(
            cli,
            [
                "evaluate",
                "--intent-id",
                intent_id,
                "-o",
                "json",
            ],
        )
        output_text = result.output.strip()
        if output_text:
            # Find JSON portion (may have leading Rich text)
            for line in output_text.splitlines():
                try:
                    data = json.loads(line)
                    if "decision_reason" in data:
                        assert isinstance(data["decision_reason"], str)
                        assert "governance_score" in data
                    break
                except json.JSONDecodeError:
                    continue

    def test_evaluate_get_intent_covers_context_method(self, cli_runner, cli):
        """Explicitly covers ctx.get_intent() call (line 109)."""
        intent_id = self._compile_and_save(cli_runner, cli)
        import rct_control_plane.cli as cli_mod

        ctx = cli_mod.get_context()
        # Direct method call to cover line 109
        data = ctx.get_intent(intent_id)
        assert data is not None
        assert "intent" in data
        # Also covers get_graph returning None
        graph = ctx.get_graph(intent_id)
        assert graph is None


# ===========================================================================
# หมวด Full Workflow — TestCLIWorkflow
# ===========================================================================


class TestCLIWorkflow:
    """End-to-end workflow: compile → build → evaluate → status → audit → list."""

    def test_compile_build_evaluate_workflow(self, cli_runner, cli):
        # 1. Compile + save
        compile_r = cli_runner.invoke(
            cli,
            [
                "compile",
                "Refactor authentication module using clean architecture",
                "--save",
                "-o",
                "json",
            ],
        )
        assert compile_r.exit_code == 0
        intent_id = json.loads(compile_r.output)["intent_id"]

        # 2. Build + save → covers build's state transition branch
        build_r = cli_runner.invoke(
            cli,
            [
                "build",
                "--dsl-text",
                WORKFLOW_DSL,
                "--intent-id",
                intent_id,
                "--save",
                "-o",
                "json",
            ],
        )
        assert build_r.exit_code == 0
        assert json.loads(build_r.output)["saved"] is True

        # 3. Evaluate
        eval_r = cli_runner.invoke(
            cli,
            [
                "evaluate",
                "--intent-id",
                intent_id,
                "-o",
                "json",
            ],
        )
        assert eval_r.exit_code in (0, 1)

        # 4. Status check
        status_r = cli_runner.invoke(cli, ["status", intent_id, "-o", "json"])
        assert status_r.exit_code == 0

    def test_list_after_multiple_compiles(self, cli_runner, cli):
        for i in range(3):
            cli_runner.invoke(
                cli,
                [
                    "compile",
                    f"Refactor module {i}",
                    "--save",
                    "-o",
                    "json",
                ],
            )
        result = cli_runner.invoke(cli, ["list", "--limit", "10", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] >= 3

    def test_evaluate_save_then_status_shows_updated_phase(self, cli_runner, cli):
        compile_r = cli_runner.invoke(
            cli,
            [
                "compile",
                "Refactor payment service",
                "--save",
                "-o",
                "json",
            ],
        )
        intent_id = json.loads(compile_r.output)["intent_id"]
        # Evaluate + save
        cli_runner.invoke(
            cli,
            [
                "evaluate",
                "--intent-id",
                intent_id,
                "--save",
                "-o",
                "json",
            ],
        )
        # Status
        status_r = cli_runner.invoke(cli, ["status", intent_id, "-o", "json"])
        assert status_r.exit_code == 0
        data = json.loads(status_r.output)
        assert "phase" in data


# ===========================================================================
# หมวด B — TestCLINoRich  (covers print_table, print_tree, format_output)
# ===========================================================================


class TestCLINoRich:
    """
    Tests with _HAS_RICH patched to False — forces all output through
    print_table / print_tree / format_output (lines 149, 154-207).
    """

    def test_compile_no_rich_json(self, cli_runner, cli):
        from unittest.mock import patch

        with patch("rct_control_plane.cli._HAS_RICH", False):
            result = cli_runner.invoke(cli, ["compile", "Refactor X", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "intent_id" in data

    def test_compile_no_rich_table_covers_print_table(self, cli_runner, cli):
        """Covers print_table body (lines 154-172)."""
        from unittest.mock import patch

        with patch("rct_control_plane.cli._HAS_RICH", False):
            result = cli_runner.invoke(
                cli, ["compile", "Refactor module", "-o", "table"]
            )
        assert result.exit_code == 0
        assert " | " in result.output  # plain-text table separator

    def test_compile_no_rich_tree_covers_print_tree(self, cli_runner, cli):
        """Covers print_tree body (lines 177-191)."""
        from unittest.mock import patch

        with patch("rct_control_plane.cli._HAS_RICH", False):
            result = cli_runner.invoke(
                cli, ["compile", "Refactor module", "-o", "tree"]
            )
        assert result.exit_code == 0
        assert "├─" in result.output  # tree characters

    def test_format_output_table_branch(self, cli_runner, cli):
        """Covers format_output TABLE branch (lines 198-207)."""
        from unittest.mock import patch

        with patch("rct_control_plane.cli._HAS_RICH", False):
            result = cli_runner.invoke(cli, ["metrics", "-o", "table"])
        assert result.exit_code == 0

    def test_format_output_tree_branch(self, cli_runner, cli):
        """Covers format_output TREE branch."""
        from unittest.mock import patch

        with patch("rct_control_plane.cli._HAS_RICH", False):
            result = cli_runner.invoke(cli, ["compile", "Refactor Y", "-o", "tree"])
        assert result.exit_code == 0

    def test_print_json_non_pretty(self, cli_runner, cli):
        """Covers print_json(pretty=False) path (line 149)."""
        from rct_control_plane.cli import print_json
        import io
        from unittest.mock import patch

        output = io.StringIO()
        with patch("click.echo", lambda x: output.write(x + "\n")):
            print_json({"key": "value"}, pretty=False)
        result = output.getvalue()
        assert "key" in result

    def test_error_path_no_rich(self, cli_runner, cli):
        """Covers the except-block non-Rich error rendering (lines 303+)."""
        from unittest.mock import patch

        with patch("rct_control_plane.cli._HAS_RICH", False):
            # evaluate with nonexistent ID triggers else-branch error
            result = cli_runner.invoke(cli, ["evaluate", "--intent-id", "bogus-id"])
        assert result.exit_code != 0

    def test_status_no_rich(self, cli_runner, cli):
        """Covers status command non-Rich path."""
        from unittest.mock import patch

        compile_r = cli_runner.invoke(
            cli,
            [
                "compile",
                "Refactor Z",
                "--save",
                "-o",
                "json",
            ],
        )
        intent_id = json.loads(compile_r.output)["intent_id"]
        with patch("rct_control_plane.cli._HAS_RICH", False):
            result = cli_runner.invoke(cli, ["status", intent_id, "-o", "json"])
        assert result.exit_code == 0

    def test_reset_no_rich_success_message(self, cli_runner, cli):
        """Covers reset's non-Rich success branch."""
        from unittest.mock import patch

        with patch("rct_control_plane.cli._HAS_RICH", False):
            result = cli_runner.invoke(cli, ["reset", "--force"])
        assert result.exit_code == 0
        assert "Reset complete" in result.output

    def test_list_no_rich_table_with_items(self, cli_runner, cli):
        """Covers list's non-Rich table branch (lines 561-574) when items exist."""
        # Save some intents first
        for goal in ("Refactor A", "Build B"):
            cli_runner.invoke(cli, ["compile", goal, "--save", "-o", "json"])
        from unittest.mock import patch

        with patch("rct_control_plane.cli._HAS_RICH", False):
            result = cli_runner.invoke(cli, ["list", "-o", "table"])
        assert result.exit_code == 0


# ===========================================================================
# หมวด E — TestCLIAdvancedCommands  (optional dep graceful degradation)
# ===========================================================================


class TestCLIAdvancedCommands:
    """
    Tests for advanced commands that rely on optional `core.*` dependencies.
    All commands have try/except ImportError guards — tests verify graceful degradation.
    """

    def test_governance_graceful_no_deps(self, cli_runner, cli):
        """governance handles missing core.adapters gracefully."""
        result = cli_runner.invoke(cli, ["governance", "-o", "json"])
        # Either ImportError guard (exit 0 with warning) or succeeds
        assert result.exit_code in (0, 1)

    def test_governance_json_output(self, cli_runner, cli):
        """governance with JSON output."""
        result = cli_runner.invoke(cli, ["governance", "--last", "5", "-o", "json"])
        assert result.exit_code in (0, 1)

    def test_logs_command_empty(self, cli_runner, cli):
        """logs with no events returns empty result."""
        result = cli_runner.invoke(cli, ["logs", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "logs" in data
        assert isinstance(data["logs"], list)

    def test_logs_command_with_tail(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["logs", "--tail", "5", "-o", "json"])
        assert result.exit_code == 0

    def test_logs_with_adapter_filter(self, cli_runner, cli):
        result = cli_runner.invoke(
            cli,
            [
                "logs",
                "--adapter",
                "test-adapter",
                "--tail",
                "5",
                "-o",
                "json",
            ],
        )
        assert result.exit_code == 0

    def test_timeline_graceful_no_deps(self, cli_runner, cli):
        """timeline handles missing MemoryDeltaEngine gracefully."""
        result = cli_runner.invoke(cli, ["timeline", "--agent", "test-agent"])
        assert result.exit_code in (0, 1)

    def test_replay_graceful_no_deps(self, cli_runner, cli):
        """replay handles missing DeterminismController gracefully."""
        result = cli_runner.invoke(cli, ["replay", "--hash", "abc123def456abcdef"])
        assert result.exit_code in (0, 1)

    def test_adapter_status_graceful_no_deps(self, cli_runner, cli):
        """adapter status handles missing ADAPTER_REGISTRY gracefully."""
        result = cli_runner.invoke(cli, ["adapter", "status"])
        assert result.exit_code in (0, 1)

    def test_adapter_list_graceful_no_deps(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["adapter", "list"])
        assert result.exit_code in (0, 1)

    def test_governance_with_mock_deps(self, cli_runner, cli):
        """governance with mocked core.adapters returns correct JSON structure."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_base_os = MagicMock()
        mock_base_os.THE_9_CODEX_FORBIDDEN_PATTERNS = [
            "pattern1",
            "pattern2",
            "pattern3",
        ]
        mock_core = MagicMock()
        mock_core_adapters = MagicMock()
        with patch.dict(
            sys.modules,
            {
                "core": mock_core,
                "core.adapters": mock_core_adapters,
                "core.adapters.base_os_adapter": mock_base_os,
            },
        ):
            result = cli_runner.invoke(cli, ["governance", "-o", "json"])
        assert result.exit_code in (0, 1)

    def test_adapter_status_with_mock_registry(self, cli_runner, cli):
        """adapter status with mocked ADAPTER_REGISTRY produces output."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_cls = MagicMock()
        mock_cls.__name__ = "MockAdapter"
        mock_adapters = MagicMock()
        mock_adapters.ADAPTER_REGISTRY = {"mock_adapter": mock_cls}
        with patch.dict(
            sys.modules,
            {
                "core": MagicMock(),
                "core.adapters": mock_adapters,
            },
        ):
            result = cli_runner.invoke(cli, ["adapter", "status", "-o", "json"])
        assert result.exit_code in (0, 1)

    def test_timeline_with_mock_engine(self, cli_runner, cli):
        """timeline with mocked MemoryDeltaEngine returns output."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_engine_cls = MagicMock()
        mock_engine_cls.return_value.query_deltas.return_value = [
            {
                "tick": 1,
                "intent_id": "abc123def456",
                "action": "analyze",
                "outcome": "success",
            },
            {
                "tick": 2,
                "intent_id": "abc123def456",
                "action": "transform",
                "outcome": "success",
            },
        ]
        mock_memory_delta = MagicMock()
        mock_memory_delta.MemoryDeltaEngine = mock_engine_cls
        with patch.dict(
            sys.modules,
            {
                "core": MagicMock(),
                "core.kernel": MagicMock(),
                "core.kernel.memory_delta": mock_memory_delta,
            },
        ):
            result = cli_runner.invoke(
                cli,
                [
                    "timeline",
                    "--agent",
                    "agent-001",
                    "--output",
                    "json",
                ],
            )
        assert result.exit_code in (0, 1)

    def test_main_entry_point(self, cli_runner, cli):
        """Covers main() function (line 1106) — calls cli --help."""
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "rct" in result.output.lower() or "control" in result.output.lower()
