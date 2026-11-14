"""
The 'Tested models' page (docs/public/TESTED_MODELS.md) is generated from research/RESULTS_REGISTER.jsonl and nothing else. These tests pin: it matches the register, it names no ranking or praise,
models are in alphabetical order inside each table, every register id it cites exists, and a result the register marks as replaced is shown as corrected, not hidden.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import render_tested_models as page

BANNED = ("best", "top", "leader", "leading", "recommended", "reliable", "state of the art", "outperform", "superior")


def text():
    return page.PAGE.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_page_on_disk_is_what_the_register_gives():
    assert text() == page.render(page.read()), "run: python scripts/render_tested_models.py"


def test_the_page_contains_no_ranking_and_no_praise():
    body = re.sub(r"`[^`]*`", "", text()).lower()
    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", body), word


def test_every_register_id_the_page_cites_exists():
    ids = {e["id"] for e in page.read()}
    cited = set(re.findall(r"\bR\d{4}\b", text()))
    assert cited and cited <= ids, sorted(cited - ids)


def test_models_are_alphabetical_inside_the_screen_tables():
    body = text()
    for heading in ("### Met the rule", "### Did not meet the rule"):
        block = body.split(heading, 1)[1].split("\n\n", 2)[1]
        names = [row.split("|")[1].strip() for row in block.splitlines()[2:]]
        assert names == sorted(names), heading


def test_the_first_llama_run_is_not_counted_and_the_page_says_why():
    body = text()
    assert "R0015 is not counted" in body
    rows = [line for line in body.splitlines() if line.startswith("| meta-llama/llama-3.1-8b-instruct |") and "K.1.5" not in line]
    assert not any("R0015" in r for r in rows)


def test_a_corrected_entry_is_shown_as_corrected_with_its_new_verdict():
    entries = page.read()
    corrections = [e for e in entries if e.get("replaces")]
    rendered = page.render(entries)
    for c in corrections:
        assert f"corrected in {c['id']}" in rendered, c["id"]
        assert not any(line.endswith(f"| {c['id']} |") for line in rendered.splitlines())         # the correcting row itself is not listed twice


def test_the_two_request_settings_are_never_combined_in_one_row():
    body = text()
    assert "never combined" in body
    for line in body.splitlines():
        if line.startswith("| ") and "deny + require_parameters" in line:
            assert "| deny |" not in line
