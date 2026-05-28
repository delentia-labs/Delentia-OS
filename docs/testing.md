# Testing

## Summary

| Metric | Value |
|--------|-------|
| **Total tests** | 765 passed · 0 skipped · 0 failed |
| **Coverage** | 89%+ |
| **Python versions** | 3.10, 3.11, 3.12 |
| **Static analysis** | mypy — 32 files clean |
| **Security scan** | bandit — 0 HIGH findings |

---

## Run the Full Suite

```bash
# Quick — summary output
pytest -q

# With coverage report
pytest --cov=microservices --cov=core --cov=signedai --cov=rct_control_plane \
       --cov-report=term-missing --cov-fail-under=85

# Verbose with short tracebacks
pytest -v --tb=short
```

---

## Test Distribution

| Package | Test Files | Tests |
|---------|-----------|-------|
| `microservices/analysearch-intent/` | `test_analysearch_engine.py` | 30 |
| `microservices/intent-loop/` | `test_intent_loop.py` + `test_intent_loop_extended.py` | 36 |
| `microservices/gateway-api/` | `test_gateway_api.py` | 14 |
| `microservices/vector-search/` | `test_vector.py` + `test_vector_extended.py` | 36 |
| `microservices/crystallizer/` | `test_crystallizer.py` | 26 |
| `core/tests/` | FDIA, Delta Engine, Regional Adapter | ~220 |
| `signedai/tests/` | Registry, consensus, JITNA | ~116 |
| `rct_control_plane/tests/` | DSL, formatters, API, security | ~168 |
| `tests/security/` | `test_api_security.py` | 19 |
| **Total** | | **723** |

---

## CI Matrix

Tests are run on every push and pull request to `main` and `develop`:

```yaml
matrix:
  python-version: ["3.10", "3.11", "3.12"]
```

Coverage is uploaded to Codecov on Python 3.11.

---

## Static Analysis

```bash
# Type checking (mypy)
mypy rct_control_plane core signedai

# Security scanning (bandit)
bandit -r . -lll --exclude .venv,tests,build,dist
```

Expected output:
- **mypy:** `Success: no issues found in 32 source files`
- **bandit:** `0 issues identified (HIGH severity)`

---

## Pre-commit Hooks

```bash
# Install hooks (one-time setup)
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

Hooks: `black` (formatter), `isort` (import sorter), `bandit` (security scan), standard file checks.

---

## Full canonical testing reference

See [`docs/testing/TESTING_CANONICAL.md`](https://github.com/delentia-labs/delentia-os/blob/main/docs/testing/TESTING_CANONICAL.md) for the complete test matrix including exact test names, scopes, and edge-case coverage notes.
