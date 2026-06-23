# Analysearch Intent Service

**Analysis + Research + Intent Engine for RCT Ecosystem v13.0**

## Features

- **Mirror Mode**: PROPOSE → COUNTER → REFINE iterative refinement loop
- **Cross-Disciplinary Synthesis**: Find connections across domains
- **Golden Keyword Extraction**: ALGO-41 inspired crystallization
- **GIGO Protection**: Entropy-based input validation
- **Intent Conservation**: Preserve original intent throughout pipeline

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8020 --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/analysearch/analyze` | Main analysis endpoint |
| POST | `/analysearch/validate` | GIGO input validation |
| POST | `/analysearch/crystallize` | Keyword extraction |
| POST | `/analysearch/synthesize` | Cross-disciplinary synthesis |
| GET | `/analysearch/sessions/{id}` | Get Mirror Mode session |
| GET | `/analysearch/stats` | Engine statistics |
| GET | `/analysearch/health` | Health check |

## Modes

- `quick` — Fast lookup, minimal analysis
- `standard` — Standard analysis + research
- `deep` — Deep analysis with Mirror Mode
- `mirror` — Full Mirror Mode (PROPOSE → COUNTER → REFINE)

## Tests

```bash
cd analysearch-intent
pytest tests/ -v
```
