"""
Industry Standard Benchmarks — RCT Platform

Compares RCT FDIA constitutional AI against industry baselines:
  - TruthfulQA: Factual accuracy under adversarial questioning
  - HaluEval: Hallucination detection
  - FDIA Benchmark: Our own constitutional scoring accuracy

Each benchmark:
  1. Loads the dataset (downloads once, caches locally)
  2. Runs RCT scoring or pattern matching
  3. Computes metrics vs. published baselines
  4. Writes results to benchmark/industry_standard/results/

Apache 2.0 — Delentia Labs (https://delentia.com)
"""
