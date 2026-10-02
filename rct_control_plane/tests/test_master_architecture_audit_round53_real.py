"""
Round 53: the document-vs-code audit is itself tested, so its verdicts cannot drift from the repository. Each
assertion pins a verdict to a fact a reader can check; when the code changes (TOON gets wired, a JWT path is added),
the test fails and the audit has to be updated on purpose.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import audit_master_architecture as audit

MINI_DOC = """
1. **ALGO-01: FDIA (Fundamental Decision Intelligence Analysis)**
2. **ALGO-26: Intent Conservation (Semantic Lossless Verifier)**
3. **ALGO-21: Fast/Slow Router (Dual-System Cognitive Router)**
4. **ALGO-99: Imaginary Engine**
"""


def by_ref(findings, fragment):
    return [f for f in findings if fragment in f.claim or fragment in f.ref]


def test_every_finding_has_a_known_verdict_and_evidence():
    findings = audit.run_audit(None)
    assert len(findings) >= 15 and "CUT" in audit.VERDICTS
    for f in findings:
        assert f.verdict in audit.VERDICTS and f.evidence and f.claim and f.ref


def test_the_checks_that_run_real_calls_report_the_fdia_invariants():
    layer3 = audit.layer3()
    assert layer3.verdict == "REAL" and "F(A=0)=0.0" in layer3.evidence and "F(I=0)=0.0" in layer3.evidence


def test_known_gaps_and_decisions_are_reported_until_someone_changes_them():
    assert audit.layer7().verdict == "CUT" and "MORE tokens than compact JSON" in audit.layer7().evidence     # decided 2026-10-02, measured
    assert audit.layer4().verdict == "CUT" and "adapter weights in the repo: 0" in audit.layer4().evidence
    assert audit.layer6().verdict == "PARTIAL" and "opt-in" in audit.layer6().evidence
    assert audit.genesis().verdict == "PARTIAL" and "pure functions only" in audit.genesis().evidence
    jwt = [f for f in audit.layer10() if "JWT" in f.claim][0]
    assert jwt.verdict == "NOT_WIRED"


def test_what_round_53_built_is_reported_as_real():
    layer10 = {f.claim: f for f in audit.layer10()}
    assert layer10["Circuit breaker"].verdict == "REAL" and layer10["Rate limiting"].verdict == "REAL"
    assert audit.layer2().verdict == "REAL" and audit.layer8().verdict == "PARTIAL" and "asks it before an action" in audit.layer8().evidence
    assert audit.layer3().verdict == "REAL" and "Owner-defined policy for A" in audit.layer3().evidence
    assert "wildcard still present: False" in [f for f in audit.layer10() if f.claim == "Zero-trust delivery"][0].evidence


def test_the_documents_wrong_statements_are_flagged_as_doc_wrong():
    assert audit.layer2_range().verdict == "DOC_WRONG"
    assert audit.layer3_name().verdict == "DOC_WRONG" and "Future Design Intelligence" in audit.layer3_name().evidence
    assert audit.jitna_terms().verdict == "DOC_WRONG" and "Header says so: True" in audit.jitna_terms().evidence


def test_algorithm_count_is_checked_against_the_pipeline():
    counts = audit.counts(None)
    assert counts[0].verdict == "REAL" and counts[0].evidence.startswith("41 pipeline adapters")
    assert counts[1].verdict == "DOC_WRONG"


def test_the_name_check_finds_the_renamed_and_the_missing_algorithms():
    findings, mismatches = audit.algorithm_names(MINI_DOC)
    flagged = {m[0]: m for m in mismatches}
    assert "ALGO-26" in flagged and "ALGO-99" in flagged and flagged["ALGO-99"][2] == "(no adapter)"
    assert "ALGO-21" not in flagged and "ALGO-01" not in flagged      # FDIA / Fast-Slow Router share their names with the code
    assert findings[0].verdict == "PARTIAL"


def test_the_parser_reads_the_real_document_format():
    names = audit.doc_algorithm_names(MINI_DOC)
    assert names["ALGO-21"] == "Fast/Slow Router (Dual-System Cognitive Router)" and len(names) == 4


def test_the_real_document_when_present_parses_to_41_entries():
    if not audit.DEFAULT_DOC.exists():
        return
    names = audit.doc_algorithm_names(audit.DEFAULT_DOC.read_text(encoding="utf-8"))
    assert len(names) == 41
