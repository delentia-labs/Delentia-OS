# Contributing to RCT Platform

Thank you for your interest in contributing to the RCT Platform!

## Code of Conduct

By participating in this project, you agree to follow the standards in
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/delentia-labs/delentia-os/issues) first.
2. Open a new issue with a clear title and description.
3. Include steps to reproduce, expected behavior, and actual behavior.
4. Include your Python version and OS.

### Suggesting Features

1. Open an issue with the `[Feature Request]` prefix.
2. Describe the problem you're solving and why it belongs in the core SDK.
3. Include examples of how the feature would be used.

### Submitting Pull Requests

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes.
4. Ensure all tests pass: `python -m pytest`
5. Ensure no new security issues: `bandit -r .`
6. Submit a pull request against `main`.

#### PR Checklist

- [ ] Tests added/updated for new behavior
- [ ] No hardcoded credentials, API keys, or internal server URLs
- [ ] Import paths use the `delentia-os` package structure (not `rct-ecosystem-private`)
- [ ] Code follows existing style (PEP 8, type hints where applicable)
- [ ] Docstrings updated if public API changed

## Development Setup

```bash
# Clone the repository
git clone https://github.com/delentia-labs/delentia-os.git
cd delentia-os

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest

# Run security scan
bandit -r core/ signedai/ rct_control_plane/ microservices/
```

## Security

For security vulnerabilities, please see [SECURITY.md](SECURITY.md).
Do **not** open a public issue for security findings.

## License

By contributing, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).

---

## How to Add a New Algorithm

RCT Platform contains 41 reference algorithm implementations in `core/`. Here's how to add a new one.

### Step 1 — Decide the algorithm tier

| Tier | Description | Example |
|------|-------------|---------|
| Tier 1–3 | Foundational scoring / filtering | FDIA, JITNA |
| Tier 4–6 | Composite / multi-step reasoning | Delta Engine, SignedAI |
| Tier 7–8 | Autonomous orchestration | Intent Loop, Crystallizer |
| Tier 9 | Full autonomous pipeline | Tier9 coordinator |

Describe the new algorithm's tier in its docstring.

### Step 2 — Create the module

```
core/
└── my_algorithm/
    ├── __init__.py
    └── my_algorithm.py
```

**Module template:**

```python
"""
My Algorithm — brief description.

Tier: X
Input: describe inputs
Output: describe outputs
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class MyAlgorithmConfig:
    """Configuration for MyAlgorithm."""
    threshold: float = 0.5


class MyAlgorithm:
    """One-line description.

    Example:
        algo = MyAlgorithm(config=MyAlgorithmConfig())
        result = algo.run(input_data)
    """

    def __init__(self, config: MyAlgorithmConfig | None = None) -> None:
        self.config = config or MyAlgorithmConfig()

    def run(self, input_data: Any) -> float:
        """Run the algorithm. Returns score in [0.0, 1.0]."""
        raise NotImplementedError
```

### Step 3 — Write tests

```
core/tests/
└── test_my_algorithm.py
```

**Test template:**

```python
"""Tests for MyAlgorithm."""
import pytest
from core.my_algorithm.my_algorithm import MyAlgorithm, MyAlgorithmConfig


class TestMyAlgorithm:
    def setup_method(self):
        self.algo = MyAlgorithm(config=MyAlgorithmConfig(threshold=0.5))

    def test_basic_output_in_range(self):
        result = self.algo.run(input_data={"value": 0.8})
        assert 0.0 <= result <= 1.0

    def test_below_threshold_blocked(self):
        result = self.algo.run(input_data={"value": 0.1})
        assert result < self.algo.config.threshold

    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="input_data"):
            self.algo.run(input_data=None)
```

### Step 4 — Add a demo script

```
examples/algorithm_demos/
└── my_algorithm_demo.py
```

Use `examples/algorithm_demos/fdia_scoring_demo.py` as a template.

### Step 5 — Update docs

1. Add the algorithm to `docs/algorithms/overview.md` (41 → 42 count).
2. Add a demo example to the relevant concept page.

### Step 6 — Open a PR

Run the full check before submitting:

```bash
pytest --tb=short -q
bandit -r core/ -q
```

---

## How to Add a New Microservice

The `microservices/` directory contains 5 reference services. New services follow this structure:

### Directory Layout

```
microservices/
└── my-service/
    ├── __init__.py
    ├── app.py          ← FastAPI application
    ├── Dockerfile
    ├── tests/
    │   ├── __init__.py
    │   └── test_my_service.py
    └── conftest.py
```

### FastAPI Service Template

```python
"""My Service — brief description."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone

app = FastAPI(title="my-service", version="1.0.2a0")


class IntentRequest(BaseModel):
    intent_id: str
    payload: dict


class ServiceResponse(BaseModel):
    service: str = "my-service"
    intent_id: str
    result: dict
    timestamp: str


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/process", response_model=ServiceResponse)
async def process(request: IntentRequest) -> ServiceResponse:
    # TODO: implement service logic
    return ServiceResponse(
        intent_id=request.intent_id,
        result={"status": "processed"},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
```

### Dockerfile Template

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/my-service/ ./microservices/my-service/
COPY core/ ./core/

CMD ["uvicorn", "microservices.my_service.app:app", "--host", "0.0.0.0", "--port", "8005"]
```

### Test Template

```python
"""Tests for my-service."""
import pytest
from fastapi.testclient import TestClient
from microservices.my_service.app import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_process_valid_intent():
    response = client.post("/process", json={
        "intent_id": "test-001",
        "payload": {"action": "test"},
    })
    assert response.status_code == 200
    assert response.json()["intent_id"] == "test-001"
```

### Add to docker-compose.dev.yml

```yaml
  my-service:
    build:
      context: .
      dockerfile: microservices/my-service/Dockerfile
    ports:
      - "8005:8005"
    environment:
      - RCT_LOG_LEVEL=DEBUG
```

### Service Scope Requirements

- Must not import from `rct-ecosystem-private`
- Must have `GET /health` endpoint returning `{"status": "healthy"}`
- Must include test coverage ≥85% for the new service
- Must add a healthcheck to docker-compose.dev.yml

---

## Running the Full Integration Stack Locally

### Prerequisites

- Docker Desktop 4.x+
- Python 3.10+
- 8GB+ RAM recommended

### Option A — Python-only (fastest)

```bash
# Clone and install
git clone https://github.com/delentia-labs/delentia-os.git
cd delentia-os
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows

pip install -e .
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest --tb=short -q
# → 765 passed

# Start Control Plane API
rct serve --port 8000 --reload
```

### Option B — Docker dev stack

```bash
# Start all 5 microservices
docker compose -f docker-compose.dev.yml up --build

# Services available at:
# http://localhost:8000  — Gateway API
# http://localhost:8001  — Intent Loop
# http://localhost:8002  — Analysearch
# http://localhost:8003  — Vector Search
# http://localhost:8004  — Crystallizer
```

### Option C — GitHub Codespaces

Click the **"Open in Codespaces"** button on GitHub — the `.devcontainer/devcontainer.json`
configuration auto-installs all dependencies and opens VS Code with the correct extensions.

### Running Demos

```bash
# All algorithm demos are offline (no API keys)
python examples/quickdemo.py
python examples/algorithm_demos/fdia_scoring_demo.py
python examples/algorithm_demos/delta_engine_demo.py
python examples/algorithm_demos/signedai_consensus_demo.py
python examples/algorithm_demos/tier9_pipeline_demo.py
```

### Running Docs Locally

```bash
pip install mkdocs-material
mkdocs serve --dev-addr 0.0.0.0:8080
# → http://localhost:8080
```

---

## Scope: What Belongs in This SDK vs Enterprise

This repository is the **public SDK layer** of the RCT Ecosystem. Understanding the scope boundary helps you decide where a contribution belongs.

### In scope for this repo (welcome PRs)

- Core algorithm libraries: `core/fdia/`, `core/delta_engine/`, `core/regional_adapter/`
- SignedAI consensus framework: `signedai/core/`
- RCT Control Plane SDK: `rct_control_plane/`
- Reference microservices: `microservices/` (5 services)
- Examples and demos: `examples/`
- Docs and whitepapers: `docs/`
- Test coverage for any of the above
- New regional adapters, new LLM integrations, new SDK utilities

### Not in scope for this repo (enterprise only)

| Feature | Why not here |
|---------|--------------|
| Genome / Creator Profile full API | Proprietary enterprise data model |
| Full 62-microservice stack | Production infrastructure (not open-source) |
| Enterprise dashboard | Proprietary UI |
| Private test suite (4,849 tests) | Covers proprietary modules |
| `rct-ecosystem-private` content | Internal enterprise codebase |

If you're unsure whether your contribution fits the SDK scope, open an issue with the `[Scope Question]` prefix before investing time in a PR.

### Guidance: do not reference private modules

Contributions must not import from `rct-ecosystem-private` or reference internal paths like `delentia_engine/`, `farmer/`, `gateway/` (private). Use only what's in this repository.
