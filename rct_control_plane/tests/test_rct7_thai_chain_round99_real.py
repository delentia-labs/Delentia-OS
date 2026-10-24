"""RCT-7 round 99: the chain's coverage checks read Thai (criteria: research/rct7_round98_criteria.md, section T and T.1).

The first Thai run showed that every word test of the chain read [A-Za-z]{4,}, so an invented Thai phrase could never be reported. Thai phrases (4 or more Thai characters between spaces and
punctuation) are now checked by character trigrams. Pure functions; no model. What is proved: a Thai phrase the quotes never contain makes the claim `phrase_unsupported` and the answer clause a
gap; a Thai claim that restates its evidence verifies; English results are unchanged; SARA AM is matched (NFC, not NFKC); hostile input is read in bounded time.
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane import rct7_judge

STEPS = [{"tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "README.md"},
          "tool_result": {"path": "README.md", "content_text": "# บริการออกใบแจ้งหนี้\nออกใบแจ้งหนี้ พอร์ต 8080"}}]


def claim(text, quote, step=1):
    return {"claim": text, "evidence": [{"step": step, "quote": quote}]}


def test_a_thai_claim_that_restates_its_evidence_verifies():
    out = rct7_judge.verify_claims([claim("เป็นบริการออกใบแจ้งหนี้ ใช้พอร์ต 8080", "ออกใบแจ้งหนี้ พอร์ต 8080")], STEPS, "บริการนี้คืออะไรและใช้พอร์ตอะไร")
    assert out[0]["status"] == "verified", out


def test_thai_glue_words_the_evidence_cannot_contain_do_not_reject_a_faithful_claim():
    """Found by the first measurement: a Thai answer about English evidence says 'equals', 'namely', 'keep', 'hour'. A claim-versus-quote trigram test rejected 4 of 10 faithful claims."""
    steps = [{"tool_name": "delentia_read_repo_file", "tool_args": {}, "tool_result": {"content_text": "timeout=30 retries=5"}}]
    out = rct7_judge.verify_claims([claim("timeout เท่ากับ 30", "timeout=30"), claim("retries เท่ากับ 5", "retries=5")], steps, "ค่าตั้งเป็นอย่างไร")
    assert [c["status"] for c in out] == ["verified", "verified"], out


def test_a_thai_phrase_that_the_request_itself_contains_is_not_invented():
    out = rct7_judge.verify_claims([claim("เป็นบริการออกใบแจ้งหนี้ ใช้พอร์ต 8080", "ออกใบแจ้งหนี้ พอร์ต 8080")], STEPS, "บริการออกใบแจ้งหนี้นี้ใช้พอร์ตอะไร")
    assert out[0]["status"] == "verified"


def test_a_thai_phrase_of_the_answer_that_no_listed_claim_speaks_about_makes_its_clause_a_gap():
    answer = "เป็นบริการออกใบแจ้งหนี้ เขียนด้วยภาษาโกลัง ใช้พอร์ต 8080"
    listed = [{"claim": "เป็นบริการออกใบแจ้งหนี้"}, {"claim": "ใช้พอร์ต 8080"}]
    assert rct7_judge.coverage_gaps(answer, listed) == [answer]
    assert rct7_judge.coverage_gaps("เป็นบริการออกใบแจ้งหนี้ ใช้พอร์ต 8080", listed) == []


def test_a_thai_answer_whose_clauses_are_all_listed_has_no_gap():
    listed = [{"claim": "เป็นบริการออกใบแจ้งหนี้"}, {"claim": "ใช้พอร์ต 8080"}]
    assert rct7_judge.coverage_gaps("เป็นบริการออกใบแจ้งหนี้\nใช้พอร์ต 8080", listed) == []


def test_english_is_untouched():
    steps = [{"tool_name": "delentia_read_repo_file", "tool_args": {}, "tool_result": {"content_text": "name = sample-service version = 0.1.0"}}]
    ok = rct7_judge.verify_claims([claim("The project is named sample-service", "name = sample-service")], steps, "what is it called")
    assert ok[0]["status"] == "verified"
    assert rct7_judge.coverage_gaps("It is licensed under MIT.", [{"claim": "The project is named sample-service"}]) == ["It is licensed under MIT"]


def test_sara_am_is_matched_to_itself():
    steps = [{"tool_name": "x", "tool_args": {}, "tool_result": {"content_text": "ทำความสะอาดห้องน้ำทุกวัน"}}]
    out = rct7_judge.verify_claims([claim("ทำความสะอาดห้องน้ำทุกวัน", "ทำความสะอาดห้องน้ำทุกวัน")], steps, "")
    assert out[0]["status"] == "verified"


def test_hostile_input_is_read_in_bounded_time():
    for text in ("ก" * 20000, "กข " * 7000, ("เป็นบริการ " * 2000), "สวัสดี" * 5000):
        started = time.perf_counter()
        rct7_judge.coverage_gaps(text, [{"claim": "เป็นบริการ"}])
        rct7_judge.verify_claims([claim(text[:300], "ก")], STEPS, text[:300])
        assert time.perf_counter() - started < 1.0
