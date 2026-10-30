"""
Round 106: every Governance control has a Thai detail, in the default state and in the states that switch a control the other way.

The Desk showed the control NAMES in Thai and the detail lines (the sentences that say what is on, what is off and why it matters) in English, because the server built them. A control whose detail
has no Thai letter would be an English line in the Thai interface again, so this test fails for it, whichever branch of the control's own condition is taken.
"""
import re
import sqlite3
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import governance_view

THAI = re.compile("[฀-๿]")


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("CREATE TABLE audit_trail(id INTEGER PRIMARY KEY, entity_type TEXT, entity_id TEXT, action TEXT, actor TEXT, changes TEXT, created_at TEXT);")
    return c


def _without_thai(monkeypatch, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    controls, _gaps = governance_view._controls(_conn())
    return [c["id"] for c in controls if not THAI.search(c.get("detail_th") or "")], controls


def test_every_control_has_a_thai_detail_in_the_default_state(monkeypatch):
    missing, controls = _without_thai(monkeypatch, {})
    assert len(controls) >= 28
    assert missing == [], f"controls whose detail has no Thai: {missing}"


@pytest.mark.parametrize("env", [
    {"DELENTIA_MEMORY_EVENTLOG": "off"},
    {"DELENTIA_MEMORY_SEAL": "off"},
    {"DELENTIA_EPISODE_JOURNAL": "off"},
    {"DELENTIA_AUDIT_TEXT": "plain"},
    {"DELENTIA_UNTRUSTED_PATHS": "none"},
    {"DELENTIA_OWNER_TOOLS_FOR_CHANNELS": "1"},
    {"DELENTIA_POLICY_CHANGE_REQUIRES_SIGNATURE": "1"},
    {"DELENTIA_VERIFY_GROUNDING": "off"},
    {"DELENTIA_TAINT_GATE": "off"},
    {"DELENTIA_NOTARY_URL": "http://127.0.0.1:1"},
    {"DELENTIA_MEMORY_NUDGE": "0"},
])
def test_the_other_branch_of_a_control_has_a_thai_detail_too(monkeypatch, env):
    missing, _controls = _without_thai(monkeypatch, env)
    assert missing == [], f"with {env}: {missing}"


def test_every_sentence_the_desk_translates_is_still_one_the_server_builds():
    """lib/server-text-th.ts maps exact English sentences to Thai. If the server's sentence changes, the Thai line silently stops being used: this fails instead."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    ts = (root / "apps" / "gui" / "src" / "lib" / "server-text-th.ts").read_text(encoding="utf-8")
    exact_block = ts.split("const EXACT", 1)[1].split("const PATTERNS", 1)[0]
    keys = re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', exact_block, flags=re.MULTILINE)
    assert len(keys) >= 10
    source = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (root / "rct_control_plane").glob("*.py"))
    source = re.sub(r'"\s*\n\s*"', "", source)             # a sentence the server writes as two adjacent string literals is one sentence
    missing = [k for k in keys if k.replace("\\'", "'") not in source and k not in ("one shared token", "per-person tokens")]
    assert missing == [], f"sentences the Desk translates that no server module builds any more: {missing}"


def test_the_english_detail_is_still_there(monkeypatch):
    """The Thai line is an addition: scripts and the English interface keep reading `detail`."""
    _missing, controls = _without_thai(monkeypatch, {})
    assert all((c["detail"] or "").strip() for c in controls)
