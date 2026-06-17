# Delentia OS — Notebooks

This directory contains Jupyter notebooks for the Delentia OS Interactive Showcase.

## 📓 Notebooks

### [`delentia_os_kaggle_showcase.ipynb`](./delentia_os_kaggle_showcase.ipynb) ← **MAIN NOTEBOOK**

The complete interactive whitepaper for Delentia OS.  
Upload this to Kaggle to replace the current `delentia-os-1-4-pillar-tracing-sandbox`.

**12 sections, 25 cells:**

| Section | System | Highlights |
|---------|--------|-----------|
| 1 | Environment Setup | Auto-detects Kaggle/Colab/Local, no API keys |
| 2 | Dataset Explorer | Loads 1,384 JITNA v3 scenarios + Pillar distribution chart |
| 3 | FDIA Calculator | `F = D^I × A` — 8 scenarios, A=0 guarantee, bar chart |
| 4 | TOON Benchmark | 38-50% token savings, 3 payload comparison charts |
| 5 | 1+4 Pillar Trace | OpenTelemetry-style spans for all 4 pillars |
| 6 | SignedAI Consensus | Risk tier → votes → consensus calculation |
| 7 | CORD Security | 20 constitutional articles, Thai language injection test |
| 8 | ZK-FDIA Proofs | Pedersen-style commitment, threshold verified without D,I,A |
| 9 | Helix-TTD Drift | 8D radar chart, CRITICAL drift detection |
| 10 | ED25519 Signatures | Tamper → InvalidSignature → A=0 → F=0 |
| 11 | Constitutional Challenge | 10/10 adversarial attacks blocked |
| 12 | Summary & Ecosystem | Links to GitHub, HuggingFace, delentia.com |

**Charts generated:**
- `pillar_distribution.png` — pie + horizontal bar
- `fdia_scores.png` — constitutional FDIA score bar chart
- `toon_benchmark.png` — 3-panel JSON vs TOON comparison
- `helix_radar.png` — 8D system health radar

### [`rct_playground.ipynb`](./rct_playground.ipynb)

Original development playground with 10 sections of raw module tests.  
Used for local development and module smoke-testing.

## 🚀 How to Upload to Kaggle

1. Go to https://www.kaggle.com/code
2. Click **"New Notebook"** → **"Upload Notebook"**
3. Select `delentia_os_kaggle_showcase.ipynb`
4. In **Data** panel: add `delentia-rct-intent-dataset` (Dataset ID: 10719506)
5. **Run All** → verify all 25 cells pass without error
6. Make **Public** → update Notebook title to:  
   `"Delentia OS — Interactive Enterprise Showcase"`

## 📁 Dataset Paths

| Environment | Path |
|-------------|------|
| Kaggle | `/kaggle/input/delentia-rct-intent-dataset/` |
| Local (fallback) | `../datasets/jitna-instruction-pairs-v2/` |
| Embedded | Auto-generated 25-scenario sample |

## 🔗 Links

- **Dataset:** https://www.kaggle.com/datasets/ittiritsaengow/delentia-rct-intent-dataset  
- **Notebook:** https://www.kaggle.com/code/ittiritsaengow/delentia-os-1-4-pillar-tracing-sandbox  
- **HuggingFace:** https://huggingface.co/Delentia  
- **Website:** https://delentia.com
