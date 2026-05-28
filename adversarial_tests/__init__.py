"""
RCT Platform — Adversarial Tests: Constitutional A=0 Challenge Suite

Public verification suite that proves the FDIA Constitution cannot be bypassed.

    F = D^I × A

When A = 0 (Architect withholds approval), F = 0 regardless of input quality.
This is enforced by mathematics, not configuration — and this test suite proves it.

Run:
    pytest adversarial_tests/ -v
    python adversarial_tests/run_challenge.py

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from .fdia_gatekeeper import FDIAConstitution, GatekeeperResult
from .jailbreak_corpus import load_corpus, JailbreakCase

__all__ = ["FDIAConstitution", "GatekeeperResult", "load_corpus", "JailbreakCase"]
