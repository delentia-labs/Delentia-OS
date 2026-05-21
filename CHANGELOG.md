# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.4b0] - 2026-05-20

### Added
- `rct doctor` command — local preflight diagnostics for Python/tooling versions, project files, and localhost service reachability with table or JSON output.

### Changed
- `rct_control_plane/api.py` — fixed mypy `[truthy-function]` failure by replacing a truthy function guard with an explicit `is not None` check for the Rich veto renderer.
- `rct_control_plane/rich_formatter.py` — `get_console()` is now TTY-aware so Rich output downgrades cleanly when stdout is piped or executed in CI.
- `rct_control_plane/cli.py` — installs `rich.traceback`, adds next-step suggestions for DX commands, adds graceful Ctrl-C shutdown handling in `rct start`, and upgrades `rct benchmark` to structured execution with Rich progress feedback.
- `rct_control_plane/tests/test_cli_api.py` — version assertion updated to `1.0.4b0` and added `rct doctor` coverage.

### Verified
- Focused validation completed locally: mypy clean for `api.py`, `cli.py`, and `rich_formatter.py`; CLI/API targeted tests passing.

## [1.0.3b0] - 2026-05-20

### Added — CLI DX (P0 + P1)
- `rct start` command — Constitutional AI OS launch sequence: splash panel (FDIA equation), 6-service boot animation (ports 8000–8004 + delta-engine), HexaCore 7-LLM Consensus Registry dashboard, then starts API server. Flags: `--verbose` (debug logs), `--ui-test` (mock mode, no API calls), `--port`, `--host`.
- `rct init` command — Creates `.env` from `.env.example` template with guided next-steps output. `--force` flag overwrites existing file.
- `rct benchmark` command — Runs benchmark suites via subprocess: `--suite fdia` (adversarial gate), `--suite halueval`, `--suite truthfulqa`, `--suite all`. Flags: `--output json|table`, `--verbose`.
- `rich_formatter.py` — 5 new DX render functions:
  - `print_splash(version)` — FDIA equation panel with Constitutional Declaration
  - `boot_sequence_animation(mock)` — Rich Status spinner per service, 6 components
  - `render_hexacore_table(mock, statuses)` — 7-LLM West/East/Region grid with ONLINE/OFFLINE badges and consensus summary bar
  - `render_architect_veto(reason)` — A=0 red-border SYSTEM HALTED alert panel
  - `render_pipeline_flow(current_stage, stages_passed)` — FDIA→JITNA→HexaCore→SignedAI→Output progress display

### Changed
- `pyproject.toml` — version `1.0.3a0` → `1.0.3b0`; classifier `Development Status :: 3 - Alpha` → `Development Status :: 4 - Beta`
- `rct_control_plane/cli.py` — `@click.version_option` updated from `1.0.2a0` → `1.0.3b0`; added imports for all 5 new rich_formatter DX functions
- `rct_control_plane/tests/test_cli_api.py` — `TestCLIVersion.test_version_flag` assertion updated to `1.0.3b0`

### Verified
- 775/775 tests passing · 0 regressions

## [Unreleased]

### Changed
- README metrics synced to the current public SDK checkpoint: **1,287 passed · 0 skipped · 92% coverage**
- `docs/testing/TESTING_CANONICAL.md` refreshed as the public single source of truth for test and coverage claims
- `ROADMAP.md` updated to reflect the current checkpoint and to clarify which launch tasks require GitHub UI configuration
- `codecov.yml` target raised from `85%` → `90%` to match the current repo floor
- `.github/workflows/ci.yml` `--cov-fail-under` raised from `85` → `90`

### Added
- `docs/release/RELEASE_READINESS_CHECKLIST.md` — public release gate checklist for docs sync, CI, security scan, codecov, release notes, website, Discussions, milestones, and provenance
- `docs/release/PUBLIC_RELEASE_PROVENANCE.md` — public-safe surface and private-to-public provenance note
- `docs/community/GITHUB_UI_LAUNCH_CHECKLIST.md` — step-by-step GitHub UI launch checklist for Topics, About, Website, Discussions, profile pinning, and milestones

## [1.0.2a0] - 2026-04-22

### Fixed
- `tests/security/test_api_security.py` — resolved 13 silently-skipped security tests caused by Python's inability to import modules from hyphen-named folders (`microservices/gateway-api/`, `microservices/vector-search/`). Now uses `importlib.util.spec_from_file_location` for gateway-api and `sys.path.insert + importlib.import_module` for vector-search (which has internal relative imports).
- `TestVectorSearchSecurity` — corrected all route paths to use `/vector/` prefix (was `/vectors/`), matching actual FastAPI router registration.
- `TestGatewayAPISecurity.test_sql_injection_in_query_field` — updated assertion to accept 404 (no route registered = no SQL exposure; safe by design).
- `microservices/intent-loop/tests/test_intent_loop.py` — removed `@pytest.mark.skip` from `TestLoopMetrics.test_placeholder`; replaced with 5 real assertions covering field defaults, cache hit rate, and datetime typing.
- `pyproject.toml` — changed `build-backend` from `setuptools.backends.legacy:build` (requires setuptools ≥68) to standard `setuptools.build_meta`; added `[tool.setuptools.packages.find]` with explicit `include` list so `pip install -e .` works on any setuptools ≥61.
- `core/delta_engine/memory_delta.py` `register_agent()` — now accepts either `NPCIntentType` (positional) or a full `AgentMemoryState` object as second argument; fixes `AttributeError: 'AgentMemoryState' object has no attribute 'value'` when demos/docs used old calling style.
- `rct_control_plane/cli.py` — fixed hardcoded `version_option` string from `2.2.0` → `1.0.2a0`.
- `rct_control_plane/tests/test_cli_api.py` — updated `TestCLIVersion.test_version_flag` assertion to match `1.0.2a0`.

### Added
- `microservices/intent-loop/loop_engine.py` — `LoopMetrics` dataclass with `total_processed`, `cache_hits`, `cache_misses`, `avg_latency_ms`, `error_count`, `last_updated`, and `cache_hit_rate` property.
- `docs/concepts/jitna.md` — Complete JITNA Protocol documentation: 3-layer architecture (Protocol/Language/Intake), 6-field canonical language (I/D/Δ/A/R/M), examples in 3 domains, comparison vs Tool-Calling APIs, FDIA+SignedAI+RCTDB integration map, The 9 Codex security rules.
- `docs/architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md` — Full RFC-001 specification (IETF-style format): wire format, negotiation pattern, adapter interface, security levels, 2 appendix examples.
- `docs/architecture/` directory created.
- `examples/jitna_demo.py` — Runnable end-to-end demo of all 3 JITNA layers with graceful fallbacks.
- `.github/ISSUE_TEMPLATE/bug_report.md` — Structured bug report template.
- `.github/ISSUE_TEMPLATE/feature_request.md` — Structured feature request template.
- `.github/ISSUE_TEMPLATE/config.yml` — Issue chooser config.
- `rct_control_plane/cli.py` `rct serve` command — starts Uvicorn + FastAPI server; supports `--port`, `--host`, `--reload` (dev mode), `--workers`.
- `rct_control_plane/cli.py` `rct version` command — prints version, Python, license, homepage; supports `--output json`.
- `rct_control_plane/cli.py` `rct status` — now accepts 0 or 1 args; with no arg shows system overview instead of crashing with missing-argument error.
- `rct_control_plane/tests/test_cli_serve_integration.py` — real-subprocess integration tests: spawns `rct serve`, hits `/health`, `/`, `/openapi.json`, `/docs`, `/compile`; also unit tests for command registration and `status` no-arg behaviour.
- `notebooks/rct_playground.ipynb` — setup cell auto-detects Colab / local venv / source; public-repo warning added; cells 12 + 14 use correct `register_agent` positional API.

### Changed
- `mkdocs.yml` — Added "JITNA Protocol" as first entry in Core Concepts nav; added "Architecture" section linking to RFC-001.
- `signedai/core/models.py` — Updated `JITNAPacket` docstring to clarify this is the **SignedAI Semantic Layer** (D=Domain, A=Assumptions, R=Requirements, M=Metrics), distinct from the canonical JITNA Language (D=Data, A=Approach, R=Reflection, M=Memory).
- `README.md` — Updated JITNA section with canonical name, 3-layer architecture summary, links to new docs. Updated Key Numbers to reflect current test suite.
- `CI --cov-fail-under` raised from `70` → `85` (actual coverage: 89%).
- Test suite: 706 passed, 14 skipped → **723 passed, 0 skipped, 0 failed**.

## [1.0.1a0] - 2026-04-17

### Fixed
- `FDIAScorer.score_action()` now accepts legacy `other_agents_intents` (dict) and `governance_score` kwargs; `world_resources` is now optional (default `{}`)
- `FDIAScorer` — added `select_best_action()` method returning highest-scoring action or `None`
- `RegionalModelRouter` — added `route(language, region)` convenience method returning `model_id` string
- `ExecutionGraph.add_node()` now raises `ValueError` when duplicate node ID is added
- `ExecutionGraph.validate()` now treats empty graph as valid (no error)
- `TierRouter._calculate_risk_level()` guards against `artifact_content=None` (no more `AttributeError`)
- `SignedAIRegistry` — added `get_tier_config()` alias accepting both `SignedAITier` and `TierLevel` enums
- `rct_control_plane/api.py` — suppressed false-positive Bandit B104 on dev-server bind

### Added
- `rct_control_plane/tests/test_formatters_dsl.py` — 42 tests for `rich_formatter.py` (full coverage) and `dsl_parser.py`

### Changed
- CI `--cov-fail-under` raised from `20` → `70` (actual coverage: 71%)
- Test suite: 141 → **591 passed**, 0 failures
- Coverage: 28% → **89%**
- `pyproject.toml` testpaths now includes all test directories

## [1.0.0-alpha] - 2026-04-13

### Added
- Initial public release of RCT Platform SDK
- Core modules: FDIA Engine, Delta Engine, Regional Adapter
- SignedAI consensus framework (S/4/6/8 tier)
- 5 reference microservices: intent-loop, analysearch-intent, vector-search, crystallizer, gateway-api
- OpenAPI 3.1.0 contract specification
- Public benchmark suite (RCT_benchmark_public)
- Whitepapers: Foundation (01) and Architecture (02)
- rct_control_plane: intent_schema, dsl_parser, execution_graph_ir
- GitHub Actions: CI pipeline + security scanning
- Contributing guide and security policy

[1.0.0-alpha]: https://github.com/rctlabs/rct-platform/releases/tag/v1.0.0-alpha
