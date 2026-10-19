"""
Round 89: Law Pack v0 (rct_control_plane/law_pack.py). No model and no network: the checker, the splitter and the storage are tested with fixtures; the measured end-to-end run is
research/law_pack_measure_r89.py (criteria: research/law_pack_criteria_r89.md).
"""
import asyncio

import pytest

from rct_control_plane import law_pack as lp

STATUTE = """
(Unofficial Translation)
Section 1 This Act is called the Example Data Act.
(Unofficial Translation)
Section 2 The controller shall answer a request without delay, but shall not exceed thirty days from the date of receiving such request. Data referred in
Section 32 (1) is not covered here.
1
(Unofficial Translation)
Section 3 A controller who violates section 2 shall be punished with an administrative fine not exceeding Baht five hundred thousand, or imprisonment not exceeding six months.
(Unofficial Translation)
2
Section 4 The Committee may extend the period by up to seventy two hours in an emergency.
"""


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


def test_sections_start_only_at_the_beginning_of_a_line_and_page_furniture_is_dropped():
    sections = dict(lp.split_sections(STATUTE))
    assert list(sections) == ["1", "2", "3", "4"]                    # the inline 'Section 32 (1)' is a reference, not a heading
    assert "Section 32 (1) is not covered here" in sections["2"]
    assert "Unofficial Translation" not in " ".join(sections.values())
    assert not any(body.rstrip().endswith(" 1") for body in sections.values())          # the bare page number was removed


def test_long_sections_become_overlapping_windows_labelled_with_their_number():
    chunks = lp.make_chunks([("7", "word " * 600)], window=900, overlap=150)
    assert len(chunks) >= 3 and all(c["section"] == "7" for c in chunks)
    assert chunks[0]["text"][-100:] in chunks[1]["text"]                # the overlap


def test_a_pack_needs_sections_and_a_safe_name():
    with pytest.raises(ValueError):
        lp.build_pack("x", "no headings in this text at all, only prose", edition="1", jurisdiction="XX", source="t", embed=False)
    with pytest.raises(ValueError):
        lp.build_pack("../evil", STATUTE, edition="1", jurisdiction="XX", source="t", embed=False)


def test_save_load_round_trip_with_vectors():
    pack = lp.build_pack("example", STATUTE, edition="2026-10", jurisdiction="XX", source="test", embed=False)
    pack.vectors = [[0.1 * (i + 1), 0.2, 0.3] for i in range(len(pack.chunks))]
    pack.embed_model = "fake"
    path = lp.save_pack(pack)
    assert path.name == "example.json"
    again = lp.load_pack("example")
    assert again.sections == pack.sections and again.sha256 == pack.sha256
    assert again.vectors is not None and len(again.vectors) == len(pack.chunks)
    assert again.vectors[0][0] == pytest.approx(0.1, abs=1e-5)
    assert lp.list_packs()[0]["name"] == "example"
    with pytest.raises(ValueError):
        lp.load_pack("../x")
    with pytest.raises(FileNotFoundError):
        lp.load_pack("nothing")


def test_lexical_retrieval_works_without_an_embedding_and_a_named_section_goes_first():
    pack = lp.build_pack("example", STATUTE, edition="1", jurisdiction="XX", source="test", embed=False)
    hits = lp.retrieve(pack, "thirty days request", k=2, arm="A0")
    assert hits[0]["section"] == "2"
    named = lp.retrieve(pack, "what does section 4 say about days", k=3, arm="A1")
    assert named[0]["section"] == "4"                                   # the question names it
    assert lp.retrieve(pack, "what does section 99 say", k=3, arm="A1")                 # a section the pack does not have is ignored, not an error


HITS = [{"section": "2", "text": "shall not exceed thirty days from the date of receiving such request"},
        {"section": "3", "text": "administrative fine not exceeding Baht five hundred thousand, or imprisonment not exceeding six months"}]


def test_a_grounded_answer_passes_even_when_the_statute_spells_the_number_out():
    ok = lp.check_answer("ตามมาตรา 2 ต้องดำเนินการภายใน 30 วัน", HITS, "กี่วัน")
    assert ok["status"] == "grounded" and ok["grounded"]
    fine = lp.check_answer("ตามมาตรา 3 ปรับไม่เกิน 500,000 บาท หรือจำคุกไม่เกิน 6 เดือน", HITS)
    assert fine["status"] == "grounded", fine                            # 'five hundred thousand' = 500,000 and 'six months' = 6


def test_an_invented_number_is_never_passed_as_grounded():
    bad = lp.check_answer("ตามมาตรา 2 ต้องดำเนินการภายใน 45 วัน", HITS)
    assert bad["status"] == "unsupported_number" and bad["unsupported_numbers"] == [45.0] and not bad["grounded"]
    fine = lp.check_answer("ตามมาตรา 3 ปรับไม่เกิน 5,000,000 บาท", HITS)
    assert fine["status"] == "unsupported_number"                       # five million is not five hundred thousand


def test_citing_a_section_that_was_not_shown_is_refused_and_so_is_no_citation():
    assert lp.check_answer("ตามมาตรา 9 ภายใน 30 วัน", HITS)["status"] == "cites_unseen_section"
    assert lp.check_answer("ภายใน 30 วัน", HITS)["status"] == "uncited"


def test_declining_is_its_own_status_and_not_a_grounded_answer():
    out = lp.check_answer("ไม่พบในข้อความที่ให้", HITS)
    assert out["status"] == "not_found" and not out["grounded"]


def test_item_markers_and_section_numbers_are_not_counted_as_quantities():
    ok = lp.check_answer("ตามมาตรา 2 (1) ภายใน 30 วัน", HITS)
    assert ok["status"] == "grounded", ok


def test_ask_returns_the_notice_the_label_and_never_raises_for_a_model_failure():
    pack = lp.build_pack("example", STATUTE, edition="2026-10", jurisdiction="XX", source="test", embed=False)

    class Boom:
        async def complete(self, *a, **k):
            raise RuntimeError("model is down")

    result = asyncio.run(lp.ask(pack, "thirty days request", Boom(), arm="A0"))
    assert result["error"].startswith("RuntimeError") and result["from_statute"] is False and result["notice"] == lp.DISCLAIMER
    assert "example" in result["pack"] and result["answer"] == lp.NOT_FOUND

    class Says:
        async def complete(self, prompt, **k):
            assert "[Section 2]" in prompt                              # the passages are in front of the model
            return "ตามมาตรา 2 ภายใน 30 วัน"

    good = asyncio.run(lp.ask(pack, "thirty days request", Says(), arm="A0"))
    assert good["from_statute"] is True and good["check"]["status"] == "grounded"


def test_the_patterns_of_this_module_are_not_slow_on_hostile_text():
    import time
    for hostile in ("\n" * 20000, " " * 20000, "Section " * 5000, "มาตรา " * 5000, "0." * 10000):
        start = time.perf_counter()
        lp.split_sections(hostile)
        lp.check_answer(hostile, HITS, hostile)
        assert time.perf_counter() - start < 3.0


def test_the_cli_imports_lists_and_asks_and_labels_what_it_could_not_confirm(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    text_file = tmp_path / "act.txt"
    text_file.write_text(STATUTE, encoding="utf-8")
    runner = CliRunner()
    imported = runner.invoke(cli, ["law", "import", "example", str(text_file), "--edition", "2026-10", "--jurisdiction", "XX", "--no-embed"])
    assert imported.exit_code == 0, imported.output
    assert "4 sections" in imported.output and "words only" in imported.output
    assert "example" in runner.invoke(cli, ["law", "list"]).output

    class Fake:
        def __init__(self, answer):
            self.answer = answer

        async def complete(self, prompt, **kwargs):
            return self.answer

    monkeypatch.setattr("rct_control_plane.llm_provider.get_default_provider", lambda *a, **k: Fake("ตามมาตรา 2 ภายใน 30 วัน"))
    grounded = runner.invoke(cli, ["law", "ask", "example", "thirty days request", "--arm", "A0"])
    assert grounded.exit_code == 0 and "from the supplied text" in grounded.output and lp.DISCLAIMER in grounded.output
    monkeypatch.setattr("rct_control_plane.llm_provider.get_default_provider", lambda *a, **k: Fake("ตามมาตรา 2 ภายใน 45 วัน"))
    invented = runner.invoke(cli, ["law", "ask", "example", "thirty days request", "--arm", "A0"])
    assert "NOT confirmed" in invented.output and "unsupported_number" in invented.output and "45" in invented.output
    missing = runner.invoke(cli, ["law", "ask", "nothing", "x"])
    assert missing.exit_code == 1


def test_a_section_the_shown_text_refers_to_may_be_named_but_an_unrelated_one_may_not():
    hits = [{"section": "79", "text": "Any Data Controller who violates section 27 paragraph one or fails to comply with section 28 shall be punished with imprisonment not exceeding six months"}]
    ok = lp.check_answer("ตามมาตรา 79 ผู้ที่ฝ่าฝืนมาตรา 27 มีโทษจำคุกไม่เกิน 6 เดือน", hits)
    assert ok["status"] == "grounded", ok                                # 27 is mentioned by the passage, so repeating it is not an invented citation
    bad = lp.check_answer("ตามมาตรา 79 และมาตรา 55 มีโทษจำคุกไม่เกิน 6 เดือน", hits)
    assert bad["status"] == "cites_unseen_section" and bad["cites_unseen"] == ["55"]
    asked = lp.check_answer("ตามมาตรา 79 ผู้ที่ฝ่าฝืนมาตรา 23 มีโทษจำคุกไม่เกิน 6 เดือน", hits, question="ฝ่าฝืนมาตรา 23 โทษคือ")
    assert asked["status"] == "grounded", asked                           # the question itself named section 23
