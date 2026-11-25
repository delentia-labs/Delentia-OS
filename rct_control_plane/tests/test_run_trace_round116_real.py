"""Round 116: the readable trace of a governed run (rct_control_plane/run_trace.py), printed after a run or live while it goes.

Real benchmark rehearsal (the real governed loop, real gate, real Ed25519 signer, real audit chain; the model is a scripted endpoint). What is checked: every
part of the cycle the record holds shows up in order; sealed text is opened with the key next to the database and shown as sealed without it; the trace only
reads (the database is byte-identical before and after, and the audit chain still verifies); a file's content is never printed; the benchmark prints it live
for d0 and says plainly that a plain-agent arm has no governed record; `--no-trace` prints none of it.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import hashlib
import sqlite3

import pytest

from rct_control_plane import run_trace
from research.daaes import benchmark
from research.daaes.scripted_upstream import PRICE_IN, PRICE_OUT, ScriptedUpstream


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")
    monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL", raising=False)


@pytest.fixture(scope="module")
def rehearsed(tmp_path_factory):
    """One d0 and one b0s run of seed 5000 against the scripted endpoint, with the live trace collected."""
    root = tmp_path_factory.mktemp("trace")
    os.environ["DELENTIA_HOME"] = str(root / "home")
    os.environ["DELENTIA_FDIA_POLICY_DEFAULT"] = "none"
    lines = []
    with ScriptedUpstream("perfect") as up:
        benchmark.run_matrix(root / "out", up.url, "scripted-key-not-real", "scripted/model", PRICE_IN, PRICE_OUT, ["d0", "b0s"], [5000], max_iterations=24, max_seconds=240,
                             real_model=False, before_cell=up.reset, trace=lines.append)
    return root / "out" / "runs" / "d0-5000" / "home", lines


def kinds(lines):
    return [line.split()[0] if line.startswith("──") is False else line.split()[1] for line in lines if line.strip()]


def test_the_live_trace_shows_every_part_of_the_cycle_in_order(rehearsed):
    _home, lines = rehearsed
    text = "\n".join(lines)
    for part in ("START", "GUARD", "THINK", "FDIA", "JITNA", "GATE", "ACT", "WAIT", "END", "SIGN", "EXEC", "RECORD"):
        assert part in text, part
    first = {k: text.index(k) for k in ("START", "GATE", "WAIT", "SIGN", "EXEC", "RECORD")}
    assert first["START"] < first["GATE"] < first["WAIT"] < first["SIGN"] < first["EXEC"] < first["RECORD"], "the order is the order of the record"
    assert "needs a human signature" in text and "ran exactly once" in text and "every link verified" in text
    assert "━━ seed 5000 · arm b0s" in text and "no governed record to trace" in text


def test_file_contents_are_never_printed(rehearsed):
    home, lines = rehearsed
    written = [line for line in lines if "delentia_write_repo_file {" in line]
    assert written and all("chars>" in line for line in written), "a whole-file write shows its path and its length, never the text"


def test_sealed_text_is_opened_with_the_key_beside_the_database_and_shown_sealed_without_it(rehearsed, tmp_path):
    home, _lines = rehearsed
    with_key = [line for _rid, line in run_trace.trace(home, reasoning=True)]
    assert any(line.strip().startswith("↳") and "[sealed]" not in line for line in with_key), "the model's reasoning is opened with the key"
    copy = tmp_path / "copy"
    copy.mkdir()
    src, dst = sqlite3.connect(str(home / "agentic.db")), sqlite3.connect(str(copy / "agentic.db"))     # the database (with what its WAL still holds) without its keys folder
    src.backup(dst)
    src.close()
    dst.close()
    without = [line for _rid, line in run_trace.trace(copy, reasoning=True)]
    assert any("[sealed]" in line for line in without) and not any(line.strip().startswith("↳ ") and "[sealed]" not in line for line in without)


def test_the_trace_only_reads(rehearsed):
    home, _lines = rehearsed
    db = home / "agentic.db"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    list(run_trace.trace(home, reasoning=True))
    line = run_trace.chain_line(db)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert "every link verified" in line


def test_thai_words(rehearsed):
    home, _lines = rehearsed
    th = "\n".join(line for _rid, line in run_trace.trace(home, lang="th"))
    assert "ต้องให้คนเซ็น" in th and "อนุมัติด้วยลายเซ็นที่ตรวจแล้ว" in th and "ทำงานครั้งเดียวพอดี" in th


def test_no_trace_prints_nothing_of_it(tmp_path, capsys):
    with ScriptedUpstream("perfect") as up:
        benchmark.run_matrix(tmp_path / "out", up.url, "scripted-key-not-real", "scripted/model", PRICE_IN, PRICE_OUT, ["d0"], [5000], max_iterations=24, max_seconds=240,
                             real_model=False, before_cell=up.reset)
    assert "GATE" not in capsys.readouterr().out


def test_a_missing_database_gives_no_lines(tmp_path):
    assert list(run_trace.trace(tmp_path)) == []
    assert run_trace.main([str(tmp_path / "nothing")]) == 2


def test_a_sealed_plan_is_counted_by_its_steps_and_placeholders_are_named(rehearsed):
    """PL1 Amendment 4, A6: the plan is sealed per person; the trace opens it before counting (it once printed '3 steps', the keys of the sealed value)."""
    home, _lines = rehearsed
    think = [line for _rid, line in run_trace.trace(home) if "THINK" in line]
    assert think and all("3 steps" not in line for line in think)
    assert all(("placeholders" in line) or ("none shown" in line) or ("7 steps" in line) for line in think)
