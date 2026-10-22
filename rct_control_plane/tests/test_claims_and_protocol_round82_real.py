"""
Round 82, plan item T04: the public wording, the protocol and the claim ledger must say what the evidence says.

Found by the Architect's research plan of 2026-10-15 and confirmed in the files (each check below failed before the corrections):
  * the README said "STABLE SDK", that "Enterprise ... runs at delentia.com", that A = 0 is a "Constitutional AI guarantee" and that "the system never acts without human approval",
    and five documents described the exponent I as "amplifying" although with D in [0, 1] a larger I LOWERS F (the page's own table shows it);
  * the public docs still showed the withdrawn "0.92 versus industry 0.65" and the 0.3% hallucination rate as headline numbers;
  * research/analyze.py labelled A111 - G as PRIMARY while the protocol says the primary comparison is the generic plan-act-check + generic retrieval baseline (GP), and the
    protocol text still said GP was not built;
  * the claim ledger had no scope, command, artifact or recorded commit.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import csv
import re
from pathlib import Path

from research import analyze

ROOT = Path(__file__).resolve().parent.parent.parent


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ------------------------------------------------------------------ wording

def test_the_readme_does_not_promise_what_the_evidence_does_not_show():
    readme = text("README.md")
    assert "STABLE%20SDK" not in readme and "status-experimental" in readme
    assert "runs at [delentia.com]" not in readme
    assert "experimental, self-hosted AI agent runtime" in readme
    assert "external pilot" in readme and "remain separate work" in readme
    assert "Constitutional AI guarantee" not in readme and "The system never acts without human approval" not in readme
    assert "higher = amplifies" not in readme and "even moderate Data quality produces excellent results" not in readme
    assert "increasing I lowers the score when 0 < D < 1" in readme
    assert "increases it when D > 1" in readme
    assert "Preventing a protected effect additionally requires the execution path to enforce its decision" in readme
    assert "A passing score cannot replace a required signature" in readme
    assert "41 Production Algorithms" not in readme


def test_no_document_still_says_a_higher_intent_exponent_amplifies_the_score():
    for rel in ("docs/index.md", "docs/concepts/fdia.md", "docs/concepts/rct-7-thinking.md", "docs/concepts/architecture.md", "docs/algorithms/overview.md"):
        body = text(rel)
        assert not re.search(r"higher\s*=\s*amplif", body, re.I), rel
        assert "Amplify intent influence" not in body, rel
        assert "even moderate **D** produces excellent results" not in body, rel
    assert "a larger **I** makes **F** smaller" in text("docs/index.md")


def test_the_withdrawn_accuracy_and_hallucination_figures_are_not_shown_as_results():
    for rel in ("docs/index.md", "docs/concepts/fdia.md", "docs/concepts/architecture.md"):
        body = text(rel)
        assert not re.search(r"0\.92\s*(vs|versus)\s*industry", body, re.I), rel
        assert "industry baseline ~0.65" not in body and "| Industry baseline | ~0.65 |" not in body, rel
    methodology = text("docs/benchmark/methodology.md")
    assert "Corrected 2026-10-16" in methodology and "| Hallucination Rate | **0.3%**" not in methodology
    assert "Withdrawn" in methodology


def test_the_gate_properties_page_names_the_route_outside_the_governed_loop():
    page = text("research/GATE_PROPERTIES.md")
    assert "/mcp" in page and "OUTSIDE the governed loop" in page


# ------------------------------------------------------------------ protocol and primary contrast

def test_the_primary_contrast_is_the_generic_plan_act_check_baseline_and_there_is_only_one():
    primaries = {name: weights for name, weights in analyze.CONTRASTS.items() if name.startswith("PRIMARY")}
    assert list(primaries.values()) == [{"A111": 1, "GP": -1}]
    assert analyze.CONTRASTS["secondary: full vs raw-history baseline (A111 - G)"] == {"A111": 1, "G": -1}


def test_the_protocol_version_is_the_same_in_the_analysis_the_config_and_the_protocol_text():
    version = analyze.PROTOCOL_VERSION
    assert re.search(rf"^protocol_version:\s*{re.escape(version)}\s*$", text("research/config.yaml"), re.M)
    assert f"({version.replace('delentia-core-', '')})" in text("research/PROTOCOL.md").splitlines()[0]
    assert re.search(r"^primary_comparison:\s*A111_vs_GP\b", text("research/config.yaml"), re.M)


def test_the_protocol_no_longer_says_the_generic_baseline_is_not_built():
    protocol = text("research/PROTOCOL.md")
    assert "ยังไม่ได้สร้าง** ในรุ่น pilot ใช้ A000 แทน" not in protocol
    assert "A111 − GP" in protocol and "ประวัติการแก้โปรโตคอล" in protocol


# ------------------------------------------------------------------ claim ledger

REQUIRED = ["claim_id", "claim", "evidence", "commit_or_round", "status", "limitation", "scope", "command", "artifact", "recorded_in_sha", "last_verified"]
# Claims that name no file in the repository as evidence (their evidence is a measurement described in words, or an absence). The list may only SHRINK: a new claim must name its artifact.
KNOWN_WITHOUT_ARTIFACT = {"CL-002", "CL-003", "CL-005", "CL-006", "CL-007", "CL-008", "CL-010", "CL-011", "CL-012", "CL-013", "CL-014", "CL-016", "CL-017", "CL-018", "CL-020", "CL-021",
                          "CL-022", "CL-029", "CL-033"}


def ledger():
    with (ROOT / "research" / "claims.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_every_claim_has_a_scope_a_command_an_artifact_a_commit_and_says_when_it_was_last_checked():
    rows = ledger()
    assert rows and set(REQUIRED) <= set(rows[0].keys())
    for row in rows:
        for column in REQUIRED:
            assert (row[column] or "").strip(), f"{row['claim_id']}: empty {column}"
        assert row["last_verified"].startswith("NOT RE-RUN") or re.match(r"\d{4}-\d{2}-\d{2}", row["last_verified"]), row["claim_id"]


def test_every_named_artifact_exists_and_a_command_is_either_runnable_text_or_says_it_is_not_recorded():
    for row in ledger():
        if row["artifact"] != "NONE RECORDED":
            for rel in row["artifact"].split(";"):
                assert (ROOT / rel).is_file(), f"{row['claim_id']}: {rel} does not exist"
        assert row["command"] == "NOT RECORDED" or row["command"].startswith("python "), row["claim_id"]


def test_the_list_of_claims_without_an_artifact_never_grows():
    without = {row["claim_id"] for row in ledger() if row["artifact"] == "NONE RECORDED"}
    assert without <= KNOWN_WITHOUT_ARTIFACT, f"new claims without an artifact: {sorted(without - KNOWN_WITHOUT_ARTIFACT)}"


def test_the_ledger_ids_are_unique_and_the_recorded_commit_is_a_hash_or_unknown():
    rows = ledger()
    assert len({r["claim_id"] for r in rows}) == len(rows)
    for row in rows:
        assert row["recorded_in_sha"] == "unknown" or re.fullmatch(r"[0-9a-f]{40}", row["recorded_in_sha"]), row["claim_id"]
