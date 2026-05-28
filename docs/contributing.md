# Contributing

Thank you for your interest in contributing to RCT Platform!

---

## Quick Start

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/delentia-os.git
cd delentia-os

python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1

pip install -e .
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install
```

---

## Development Workflow

1. **Create a branch** — `git checkout -b feat/my-feature`
2. **Write tests first** — target coverage must remain ≥ 70%
3. **Run the full suite** — `pytest -q` — must show 0 failures
4. **Run pre-commit** — `pre-commit run --all-files`
5. **Open a PR** — fill in the PR template

---

## Code Standards

| Tool | Command | Requirement |
|------|---------|-------------|
| black | `black .` | Auto-formatter (enforced) |
| isort | `isort .` | Import sorter (enforced) |
| mypy | `mypy rct_control_plane core signedai` | No new type errors |
| bandit | `bandit -r . -lll` | 0 HIGH findings |
| pytest | `pytest --cov-fail-under=70` | ≥ 70% coverage |

---

## Commit Message Format

```
type(scope): short summary

Optional longer description.
```

Types: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`

Examples:
- `feat(fdia): add select_best_action method`
- `fix(api): resolve datetime.utcnow deprecation`
- `docs: add quickstart guide`

---

## Areas Welcoming Contributions

- New regional adapters (language pairs not yet supported)
- Additional vector backends beyond FAISS and Qdrant
- New tier configurations for SignedAI
- MkDocs documentation improvements
- Benchmark additions

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://github.com/delentia-labs/delentia-os/blob/main/CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

---

## Security

To report a security vulnerability, please follow the process in [SECURITY.md](https://github.com/delentia-labs/delentia-os/blob/main/SECURITY.md). Do **not** open a public issue for security vulnerabilities.
