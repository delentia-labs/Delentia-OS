# Trading Agent Architecture — Institutional AI Trading on delentia-os

> For the full architectural article with code examples, see:  
> [delentia.com/en/blog/institutional-grade-ai-trading-delentia-os](https://delentia.com/en/blog/institutional-grade-ai-trading-delentia-os)

---

## Overview

This document describes the architectural blueprint for applying `delentia-os` SDK modules to institutional-grade algorithmic trading. It maps the 7-state IntentLoop to a complete news-driven trading pipeline.

**Important:** `delentia-os` v1.0.2a0 is a developer SDK — the algorithmic building blocks. A production trading deployment requires additional extensions described in [What You Need to Build](#what-you-need-to-build).

---

## IntentLoop → Trading Pipeline Mapping

| IntentLoop State | Trading Stage | SDK Module |
|---|---|---|
| `RECEIVED` | Data Ingestion (news + price WebSocket) | `IntentSignal` |
| `MEMORY_CHECK` | Delta Engine warm recall (prior analysis + portfolio state) | `core/delta_engine/` |
| `VALIDATED` | FDIA Constitutional Scoring (A=0 kill switch) | `core/fdia/` |
| `COMPUTING` | Multi-model Analysis (HexaCore 7-model ensemble) | `signedai/` |
| `VERIFYING` | SignedAI Risk Gating (TIER_S / TIER_4 / TIER_6 / TIER_8) | `signedai/` |
| `COMMITTING` | DelentiaDB Trade Outcome Logging | `core/delta_engine/` |

---

## FDIA as Signal Scorer

The FDIA equation (`F = D^I × A`) maps directly to trading signal evaluation:

- **D (Desirability)** — How aligned is acting on this signal with the portfolio's investment mandate?
- **I (Intent)** — Signal intent classification: `ACCUMULATE` / `PROTECT` / `DISCOVER`
- **A (Authorization)** — Is the current portfolio state authorized to act on this signal type?

When `A=0` (e.g., portfolio already at maximum sector allocation), `F=0` regardless of signal quality. This is the constitutional kill switch — no LLM analysis can override it.

**Key advantage for finance: backtestability.** The FDIA Scorer is a pure function with no LLM calls. Every historical decision can be replayed with the same inputs to produce the same F score — a reproducible, mathematically-verified decision trace.

```python
from core.fdia import FDIAScorer

scorer = FDIAScorer(
    world_resources={
        "available_liquidity": 0.18,
        "current_sector_exposure": {"semiconductor": 0.24},
        "max_sector_allocation": 0.30
    },
    intent_classification="PROTECT",
    action_threshold=0.80
)

result = scorer.evaluate(signal)
# result.f_score: float
# result.components: {d, i, a}
# result.reasoning_trace: list[str]  # audit log
```

---

## SignedAI as Risk Gatekeeper

After multi-model analysis, outputs pass through the SignedAI verification pipeline:

| F Score | Risk Level | SignedAI Tier | Consensus Required | Approx. Cost |
|---|---|---|---|---|
| 0.90–1.00 | Low | TIER_S | Single model | ~$0.10 |
| 0.75–0.89 | Medium | TIER_4 | 50% (2 of 4) | ~$0.80 |
| 0.60–0.74 | High | TIER_6 | 67% (4 of 6) | ~$2.00 |
| < 0.60 | Very High | TIER_8 or block | 75% (6 of 8) | ~$5.00 |

Each model that agrees signs with Ed25519. The cryptographic attestation is permanently auditable — for regulatory review, you can show exactly which models evaluated a trade, what each concluded, whether consensus was reached, and the FDIA score at time of decision.

---

## Sector Balance = Geopolitical Balance

The HexaCore 7-model roster is structured to prevent single-region analytical bias:

- **Western models** (GPT-4o, Claude, Gemini) — English-language tech analyst reports
- **Eastern models** (Qwen, DeepSeek) — APAC supplier relationship context
- **Regional model** (Typhoon-2) — Thai/ASEAN market context

For a Taiwan Strait supply chain disruption, all three perspectives are needed. The consensus is not just "most models agree" — it is "models representing different geopolitical contexts agree."

---

## Just-In-Time Processing

The IntentLoop's standby mode reduces inference cost:

- Delta Engine warm recall runs first (no LLM call needed)
- Full multi-model analysis only for novel signals or constitutional domains
- In practice: 70–80% of routine signals handled without full LLM analysis

---

## What You Need to Build

`delentia-os` provides the algorithmic core. Production deployment requires:

### 1. Market Data Adapters

```python
class MarketDataAdapter:
    async def stream_news(self) -> AsyncIterator[NewsEvent]: ...
    async def stream_prices(self, symbols: list[str]) -> AsyncIterator[PriceEvent]: ...
    async def submit_order(self, order: OrderRequest) -> OrderResponse: ...
```

Tested adapter libraries: `ib_insync` (Interactive Brokers), `alpaca-py` (Alpaca), `python-binance` (Binance).

### 2. Financial Intent Dictionary

Extend the JITNA intent vocabulary with financial event classifications:

```python
FINANCIAL_INTENTS = {
    "EARNINGS_BEAT": {"default_i": 0.85, "default_d": 0.7},
    "EARNINGS_MISS": {"default_i": 0.75, "default_d": 0.3},
    "SUPPLY_CHAIN_DISRUPTION": {"default_i": 0.9, "default_d": 0.2},
    "REGULATORY_ACTION": {"default_i": 0.95, "default_d": 0.1},
    # ... ~40 categories
}
```

### 3. Position Sizing Algorithm

FDIA F score → position size mapping (example: Kelly Criterion variant):

```python
def compute_position_size(
    f_score: float, 
    kelly_fraction: float, 
    available_capital: float
) -> float:
    # Conservative: 50% Kelly × FDIA weight
    return f_score * (kelly_fraction * 0.5) * available_capital
```

---

## Audit Artifacts (Auto-generated)

For MiFID II, SEC, SET, CFTC compliance:

1. **FDIA Decision Trace** — D/I/A components, resulting F score, constitutional rule applied
2. **SignedAI Consensus Record** — Ed25519-signed multi-model agreement, model identities, timestamp
3. **Delta Engine Recall Log** — prior decisions informing warm recall, compression ratio
4. **DelentiaDB Outcome Log** — post-trade PnL, loop duration, G7 adaptation signals

---

## Quick Start

```bash
git clone https://github.com/delentia-labs/delentia-os.git
cd delentia-os
pip install -e ".[dev]"
# See notebooks/rct_playground.ipynb for FDIA + SignedAI live demo
```

---

## Related Docs

- [FDIA Equation](../concepts/fdia.md)
- [SignedAI](../concepts/signedai.md)
- [Intent Loop](../concepts/intent-loop.md)
- [Genome System](../concepts/genome-system.md)
- [Finance Use Case](../use-cases/finance.md)

---

*Full article with extended code: [delentia.com/en/blog/institutional-grade-ai-trading-delentia-os](https://delentia.com/en/blog/institutional-grade-ai-trading-delentia-os)*
