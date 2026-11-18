"""Thai Desk, Skills page (research/DESK_THAI_SKILLS_CRITERIA_R115.md rule T2): every bundled starter skill title has a Thai text, so a new starter skill cannot ship untranslated."""
import json
import re
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pathlib import Path

from rct_control_plane import starter_skills

ROOT = Path(__file__).resolve().parents[2]
SERVER_TEXT = (ROOT / "apps/gui/src/lib/server-text-th.ts").read_text(encoding="utf-8")
SKILLS_PAGE = (ROOT / "apps/gui/src/app/skills/page.tsx").read_text(encoding="utf-8")


def thai_keys():
    return set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', SERVER_TEXT, flags=re.MULTILINE))


def test_every_bundled_starter_title_has_a_thai_entry():
    missing = [s["problem_statement"] for s in starter_skills.STARTER_SKILLS if json.loads('"' + s["problem_statement"].replace('"', '\\"') + '"') not in thai_keys()]
    assert not missing, f"starter skills with no Thai title: {missing}"


def test_each_thai_text_is_thai_and_keeps_the_technical_words():
    entries = dict(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":\s*"((?:[^"\\]|\\.)+)",?\s*$', SERVER_TEXT, flags=re.MULTILINE))
    for s in starter_skills.STARTER_SKILLS:
        thai = entries[s["problem_statement"]]
        assert re.search(r"[฀-๿]", thai), s["problem_statement"]
    todo = entries["list the TODO and FIXME comments in the code"]
    assert "TODO" in todo and "FIXME" in todo
    assert "URL" in entries["read a web page at a given url and summarize it"]
    assert "markdown" in entries["convert stored content to another format such as markdown or json"] and "json" in entries["convert stored content to another format such as markdown or json"]


def test_the_skills_page_sends_the_title_and_the_fixed_lines_through_the_language_helpers():
    assert 'title={serverText(s.problem_statement, lang === "th")}' in SKILLS_PAGE
    assert 'L("written by people and shipped with the runtime, not learned"' in SKILLS_PAGE
    assert "ใช้ซ้ำ: สำเร็จ" in SKILLS_PAGE and "reuse: {s.successes} worked" in SKILLS_PAGE          # both languages are there
