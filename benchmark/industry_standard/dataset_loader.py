"""
Dataset Loader — Industry Standard Benchmarks

Loads TruthfulQA and HaluEval datasets for benchmark evaluation.
Uses HuggingFace datasets library when available, falls back to
direct URL downloads (no HuggingFace token required for public datasets).

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
import urllib.request

# Cache directory for downloaded datasets
_CACHE_DIR = Path(__file__).parent / ".cache"

# Public URLs for raw dataset files
_TRUTHFULQA_URL = (
    "https://raw.githubusercontent.com/sylinrl/TruthfulQA/main/TruthfulQA.csv"
)
_HALUEVAL_QA_URL = (
    "https://raw.githubusercontent.com/RUCAIBox/HaluEval/main/data/qa_data.json"
)

# RCT FDIA benchmark lives locally
_FDIA_BENCHMARK_PATH = Path(__file__).parent.parent / "fdia_benchmark.py"


# ============================================================
# Utilities
# ============================================================

def _ensure_cache() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _download_file(url: str, dest: Path, desc: str) -> bool:
    """Download a file with progress indicator. Returns True on success."""
    if dest.exists():
        return True
    print(f"⬇  Downloading {desc} → {dest.name} ...")
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"   ✓ Done ({dest.stat().st_size // 1024}KB)")
        return True
    except Exception as exc:
        print(f"   ✗ Failed: {exc}")
        return False


# ============================================================
# TruthfulQA Loader
# ============================================================

def load_truthfulqa(
    max_samples: Optional[int] = None,
    use_hf: bool = True,
) -> List[Dict[str, Any]]:
    """
    Load TruthfulQA dataset.

    Returns a list of dicts with keys:
      - question: str
      - correct_answers: list[str]
      - incorrect_answers: list[str]
      - category: str
      - source: str

    Args:
        max_samples: If set, return only the first N samples.
        use_hf:      Try HuggingFace datasets first (faster, structured).
    """
    # Option A: HuggingFace datasets library
    if use_hf:
        try:
            from datasets import load_dataset  # type: ignore
            ds = load_dataset("truthful_qa", "generation", split="validation")
            samples = []
            for row in ds:
                samples.append({
                    "question": row["question"],
                    "correct_answers": row["correct_answers"],
                    "incorrect_answers": row["incorrect_answers"],
                    "category": row.get("category", ""),
                    "source": row.get("source", ""),
                })
                if max_samples and len(samples) >= max_samples:
                    break
            print(f"✓  TruthfulQA loaded via HuggingFace: {len(samples)} samples")
            return samples
        except ImportError:
            print("   HuggingFace datasets not installed, falling back to CSV download")
        except Exception as exc:
            print(f"   HuggingFace load failed ({exc}), falling back to CSV")

    # Option B: CSV download
    _ensure_cache()
    csv_path = _CACHE_DIR / "TruthfulQA.csv"
    if not _download_file(_TRUTHFULQA_URL, csv_path, "TruthfulQA CSV"):
        return []

    import csv
    samples = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            correct = [a.strip() for a in row.get("Correct Answers", "").split(";") if a.strip()]
            incorrect = [a.strip() for a in row.get("Incorrect Answers", "").split(";") if a.strip()]
            samples.append({
                "question": row.get("Question", ""),
                "correct_answers": correct,
                "incorrect_answers": incorrect,
                "category": row.get("Category", ""),
                "source": row.get("Source", ""),
            })
            if max_samples and len(samples) >= max_samples:
                break

    print(f"✓  TruthfulQA loaded via CSV: {len(samples)} samples")
    return samples


# ============================================================
# HaluEval Loader
# ============================================================

def load_halueval_qa(
    max_samples: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Load HaluEval QA hallucination dataset.

    Returns a list of dicts with keys:
      - question: str
      - answer: str
      - hallucination: bool  (True = the answer is hallucinated)

    Note: HaluEval requires manual download for the full dataset.
    This loader uses the public QA subset.
    """
    _ensure_cache()
    json_path = _CACHE_DIR / "halueval_qa.json"
    if not _download_file(_HALUEVAL_QA_URL, json_path, "HaluEval QA"):
        # Return a small curated sample set as fallback
        print("   Using built-in HaluEval sample (10 cases)")
        return _halueval_sample()

    # HaluEval uses JSONL format: one JSON object per line.
    # Each record has: question, right_answer, hallucinated_answer, knowledge.
    # We expand each record into two samples: (right=False) and (hallucinated=True).
    samples: List[Dict[str, Any]] = []
    try:
        with json_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                q = item.get("question", "")
                right = item.get("right_answer", "")
                hallucinated = item.get("hallucinated_answer", "")
                if q and right:
                    samples.append({"question": q, "answer": right, "hallucination": False})
                if q and hallucinated:
                    samples.append({"question": q, "answer": hallucinated, "hallucination": True})
                if max_samples and len(samples) >= max_samples:
                    break
    except OSError:
        print("   HaluEval file unreadable, using built-in sample")
        return _halueval_sample()

    if not samples:
        print("   HaluEval JSONL yielded no records, using built-in sample")
        return _halueval_sample()

    print(f"✓  HaluEval QA loaded via JSONL: {len(samples)} samples")
    return samples


def _halueval_sample() -> List[Dict[str, Any]]:
    """
    Curated 30-sample HaluEval-style fallback dataset (no download required).
    15 truthful answers, 15 hallucinated answers — balanced 50/50 split.
    Hallucinated samples cover both pattern-detectable and factual-error types.
    """
    return [
        # ── Truthful ──────────────────────────────────────────────────────────
        {"question": "Who invented the telephone?",
         "answer": "Alexander Graham Bell patented the telephone in 1876.",
         "hallucination": False},
        {"question": "What is the capital of France?",
         "answer": "Paris is the capital of France.",
         "hallucination": False},
        {"question": "What is the speed of light?",
         "answer": "The speed of light is approximately 299,792 km/s in a vacuum.",
         "hallucination": False},
        {"question": "When did World War II end?",
         "answer": "World War II ended in 1945 with the surrender of Germany and Japan.",
         "hallucination": False},
        {"question": "What is DNA?",
         "answer": "DNA is a double-helix molecule that carries genetic information.",
         "hallucination": False},
        {"question": "When did humans first land on the moon?",
         "answer": "The first crewed moon landing occurred on July 20, 1969.",
         "hallucination": False},
        {"question": "At what temperature does water boil?",
         "answer": "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
         "hallucination": False},
        {"question": "Who developed the theory of evolution?",
         "answer": "Charles Darwin developed the theory of evolution by natural selection.",
         "hallucination": False},
        {"question": "Who discovered penicillin?",
         "answer": "Penicillin was discovered by Alexander Fleming in 1928.",
         "hallucination": False},
        {"question": "What is the largest ocean?",
         "answer": "The Pacific Ocean is the largest ocean on Earth by surface area.",
         "hallucination": False},
        {"question": "How many bones does the human body have?",
         "answer": "The adult human body has 206 bones.",
         "hallucination": False},
        {"question": "What is photosynthesis?",
         "answer": "Photosynthesis is the process by which plants convert sunlight and CO2 into glucose.",
         "hallucination": False},
        {"question": "Who wrote Romeo and Juliet?",
         "answer": "Romeo and Juliet was written by William Shakespeare.",
         "hallucination": False},
        {"question": "What is the chemical symbol for gold?",
         "answer": "The chemical symbol for gold is Au, from the Latin word aurum.",
         "hallucination": False},
        {"question": "What planet is closest to the sun?",
         "answer": "Mercury is the planet closest to the sun in our solar system.",
         "hallucination": False},

        # ── Hallucinated ─────────────────────────────────────────────────────
        # Pattern-detectable (trigger heuristics):
        {"question": "Who invented the telephone?",
         "answer": "Nikola Tesla invented the telephone in 1880.",   # "invented the"
         "hallucination": True},
        {"question": "What is the speed of light?",
         "answer": "As of my knowledge, the speed of light is exactly 100,000 km/s.",  # "as of my knowledge" + "exactly 100"
         "hallucination": True},
        {"question": "Do all birds fly?",
         "answer": "Studies have shown that all birds are capable of flight.",  # "studies have shown that all"
         "hallucination": True},
        {"question": "When was the internet invented?",
         "answer": "The internet was first used in 1960 by military researchers.",  # "first used in" (wrong year)
         "hallucination": True},
        {"question": "Who is Albert Einstein?",
         "answer": "It is well known that Einstein was the first person to split the atom.",  # "it is well known that"
         "hallucination": True},
        {"question": "How many species of dinosaurs existed?",
         "answer": "There are exactly 1000 known dinosaur species recorded in fossil records.",  # "there are exactly"
         "hallucination": True},

        # Factual-error hallucinations (no pattern trigger — tests recall):
        {"question": "What is the capital of France?",
         "answer": "Lyon is the capital of France.",
         "hallucination": True},
        {"question": "When did World War II end?",
         "answer": "World War II ended in 1950 after the Korean armistice.",
         "hallucination": True},
        {"question": "What is DNA?",
         "answer": "DNA is a protein that carries electrical signals between neurons.",
         "hallucination": True},
        {"question": "Who discovered penicillin?",
         "answer": "Penicillin was discovered by Louis Pasteur in 1920.",
         "hallucination": True},
        {"question": "What is the largest ocean?",
         "answer": "The Atlantic Ocean is the largest ocean on Earth.",
         "hallucination": True},
        {"question": "At what temperature does water boil?",
         "answer": "Water boils at 80 degrees Celsius at standard atmospheric pressure.",
         "hallucination": True},
        {"question": "Who wrote Romeo and Juliet?",
         "answer": "Romeo and Juliet was written by Geoffrey Chaucer.",
         "hallucination": True},
        {"question": "What is the chemical symbol for gold?",
         "answer": "The chemical symbol for gold is Gd.",
         "hallucination": True},
        {"question": "What planet is closest to the sun?",
         "answer": "Venus is the planet closest to the sun in our solar system.",
         "hallucination": True},
    ]


# ============================================================
# Summary
# ============================================================

def dataset_summary() -> None:
    """Print available datasets and cache status."""
    print("Available Benchmark Datasets:")
    print(f"  TruthfulQA : 817 questions, 38 categories")
    print(f"               https://github.com/sylinrl/TruthfulQA")
    print(f"  HaluEval   : 10K QA pairs (hallucination labels)")
    print(f"               https://github.com/RUCAIBox/HaluEval")
    print(f"  FDIA Bench : 12 classification cases (local)")
    print()
    print(f"Cache directory: {_CACHE_DIR}")
    for f in _CACHE_DIR.glob("*") if _CACHE_DIR.exists() else []:
        print(f"  {f.name} ({f.stat().st_size // 1024}KB)")
