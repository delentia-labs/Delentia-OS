"""
One-time setup: download and cache the NLTK data ALGO-34 (SWCAR) needs
(stopwords, punkt, punkt_tab) — run this ONCE per environment, before
ever instantiating AlgorithmKernel41.

Why this script exists instead of just `nltk.download(...)`: on this
project's Python 3.13 environment, `nltk.download()`'s own zip
extraction is rejected by Python's Zip Slip protection in the stdlib
`zipfile` module (a real incompatibility between NLTK's packaging and
newer Python's stricter extraction safety checks) — the download
succeeds but the files are never actually written, so
`nltk.data.find(...)` keeps failing and ALGO-34's constructor keeps
retrying the download on every single kernel instantiation. On this
session's dev machine, one such retry triggered a native Windows socket
access violation that crashed the whole Python process (a segfault, not
a catchable Python exception) — found and fixed 2026-09-16.

This script downloads the same real NLTK package zips directly and
extracts them with a plain `zipfile.ZipFile.extractall()` call, which
does not hit the same extraction path nltk.download() uses.

Run once per environment:
    python scripts/setup_nltk_data.py
"""
import io
import os
import zipfile

import httpx

PACKAGES = {
    "stopwords": ("corpora", "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/stopwords.zip"),
    "punkt": ("tokenizers", "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt.zip"),
    "punkt_tab": ("tokenizers", "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip"),
}


def main() -> None:
    import nltk

    nltk_data_root = os.path.expanduser(os.path.join("~", "AppData", "Roaming", "nltk_data")) if os.name == "nt" else os.path.expanduser("~/nltk_data")

    for name, (category, url) in PACKAGES.items():
        try:
            nltk.data.find(f"{category}/{name}")
            print(f"{name}: already cached, skipping")
            continue
        except LookupError:
            pass

        print(f"{name}: downloading real package from {url}")
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        target_dir = os.path.join(nltk_data_root, category)
        os.makedirs(target_dir, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(target_dir)
        print(f"{name}: extracted {len(resp.content)} real bytes to {target_dir}")

    print("\nVerifying...")
    for name, (category, _) in PACKAGES.items():
        try:
            nltk.data.find(f"{category}/{name}")
            print(f"  {name}: OK")
        except LookupError:
            print(f"  {name}: STILL MISSING — ALGO-34 will fall back to an empty stopword set")


if __name__ == "__main__":
    main()
