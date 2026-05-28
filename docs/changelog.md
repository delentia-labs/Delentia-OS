# Changelog

All notable changes to RCT Platform are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.0.2a0] — 2026-04-22

### Added
- `docs/algorithms/overview.md` — public reference for all 41 algorithms (Tier 1–9) with scores, formulas, and use cases
- `docs/algorithms/tier9-autonomy.md` — Tier 9 Autonomous Pipeline showcase
- `docs/concepts/jitna.md` — Complete JITNA Protocol documentation: 3-layer architecture, 6-field canonical language, The 9 Codex security rules
- `docs/architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md` — Full RFC-001 specification (IETF-style)
- `rct_control_plane/tests/test_security_extended.py` — 11 security boundary tests
- `tests/security/test_api_security.py` — 19 API security tests
- `docs/use-cases/` — 5 pages: DevOps, Finance, Game AI, Healthcare, Supply Chain
- MkDocs navigation: **Algorithms** tab, **Use Cases** tab, Governance added to Core Concepts
- `rct_control_plane/cli.py` `rct serve` command — starts Uvicorn + FastAPI server; `--port`, `--host`, `--reload`, `--workers`
- `rct_control_plane/cli.py` `rct version` command — prints version, Python, license, homepage; `--output json`
- `rct_control_plane/cli.py` `rct status` — now accepts 0 or 1 args (no-arg shows system overview)
- `notebooks/rct_playground.ipynb` — runnable Colab notebook with FDIA + SignedAI + Delta demos
- `rct_control_plane/tests/test_cli_coverage_gaps.py` — 18 targeted tests for CLI coverage
- `rct_control_plane/tests/test_cli_serve_integration.py` — subprocess integration tests
- `.github/ISSUE_TEMPLATE/` — bug_report.md, feature_request.md, config.yml

### Removed
- `docs/MASTER_36_ALGORITHMS_MAPPING_TABLE_2026_01_18.md` — internal audit document; superseded by `docs/algorithms/overview.md`

### Fixed
- `rct_control_plane/cli.py` — fixed hardcoded `version_option` string `2.2.0` → `1.0.2a0`
- `rct_control_plane/cli.py` — `_configure_encoding()`: UTF-8 stdout/stderr on Windows CP874/CP932 consoles (was causing 6 skipped tests)
- `core/delta_engine/memory_delta.py` `register_agent()` — accepts `NPCIntentType` or `AgentMemoryState` (fixes `AttributeError`)
- `pyproject.toml` — `build-backend` to standard `setuptools.build_meta` + explicit `packages.find`
- 19 broken documentation links across 7 files
- 14 previously skipped tests resolved (0 skipped, all 765 pass)
- MkDocs builds with **0 warnings**

### Changed
- Test suite: 591 passed · 14 skipped → **765 passed · 0 skipped · 0 failed**
- Coverage: 89%+ (measured across 9,382+ statements)
- CI `--cov-fail-under` raised: 70 → **85**
- Algorithm reference: 36 (stale) → **41** (complete, Tier 1–9)

---

## [1.0.1a0] — 2026-04-17

### Fixed
- `FDIAScorer.score_action()` — accepts legacy `other_agents_intents` and `governance_score` kwargs; `world_resources` is now optional (default `{}`)
- `FDIAScorer.select_best_action()` — new method returning highest-scoring action or `None`
- `RegionalModelRouter.route(language, region)` — new convenience method returning `model_id`
- `ExecutionGraph.add_node()` — raises `ValueError` on duplicate node ID
- `ExecutionGraph.validate()` — empty graph is now valid
- `TierRouter._calculate_risk_level()` — guards against `artifact_content=None`
- `SignedAIRegistry.get_tier_config()` — accepts both `SignedAITier` and `TierLevel` enums
- `rct_control_plane/api.py` — suppressed false-positive Bandit B104 on dev-server bind
- **Python 3.12:** `datetime.utcnow()` → `datetime.now(timezone.utc)` across all modules
- **Pydantic v2:** `class Config` → `model_config = ConfigDict(...)` in all API models
- **Security:** `python-multipart` in `vector-search` bumped to `>=0.0.24` (CVE HIGH fix)

### Added
- `rct_control_plane/tests/test_formatters_dsl.py` — 42 tests for `rich_formatter.py` and `dsl_parser.py`
- `.github/workflows/release.yml` — automated GitHub Releases + PyPI publishing via OIDC
- `CODE_OF_CONDUCT.md` — Contributor Covenant
- `.github/PULL_REQUEST_TEMPLATE.md`
- `CITATION.cff`
- `.pre-commit-config.yaml`

### Changed
- CI `--cov-fail-under` raised: 20 → 70 (actual: 89%)
- Test suite: 141 → **591 passed**, 0 failures
- Coverage: 28% → **89%**
- `fastapi` bumped to `>=0.136.0`, `pydantic` to `>=2.13.1`

---

## [1.0.0-alpha] — 2026-04-13

### Added
- Initial public release of RCT Platform SDK under Apache 2.0
- Core modules: FDIA Engine, Delta Engine, Regional Adapter
- SignedAI consensus framework (S/4/6/8 tier)
- 5 reference microservices: intent-loop, analysearch-intent, vector-search, crystallizer, gateway-api
- OpenAPI 3.1.0 contract specification
- Public benchmark suite (RCT_benchmark_public)
- Whitepapers: Foundation (01) and Architecture (02)
- `rct_control_plane`: intent_schema, dsl_parser, execution_graph_ir (15 modules total)
- GitHub Actions: CI pipeline + security scanning
- CONTRIBUTING.md, SECURITY.md

---

[1.0.2a0]: https://github.com/delentia-labs/delentia-os/compare/v1.0.1a0...v1.0.2a0
[1.0.1a0]: https://github.com/delentia-labs/delentia-os/compare/v1.0.0-alpha...v1.0.1a0
[1.0.0-alpha]: https://github.com/delentia-labs/delentia-os/releases/tag/v1.0.0-alpha
