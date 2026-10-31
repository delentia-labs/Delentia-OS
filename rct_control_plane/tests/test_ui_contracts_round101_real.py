"""
Round 101C: the contracts between what the server says and what a person reads. These tests do not start anything; they read the real sources and fail when the two sides drift apart:

  * every stop reason the runtime can produce has a plain-language text (apps/gui/src/lib/reason-text.ts);
  * every daemon task has a Thai/English description (task-text.ts);
  * every (check, state) the readiness endpoint can produce has a text, and no text exists for a state that can not happen (readiness-text.ts);
  * every command and option a guide tells a person to type exists in the real command line, and each Thai guide has an English twin that names the same commands.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import glob
import itertools
import re
from pathlib import Path

import click
import pytest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "apps" / "gui" / "src" / "lib"
DEMO = ROOT / "docs" / "demo"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ stop reasons
def _runtime_stop_reasons() -> set:
    found = set()
    pattern = re.compile(r"""["']stopped_reason["']\s*:\s*["'](\w+)["']|stopped_reason\s*=\s*["'](\w+)["']""")
    for path in glob.glob(str(ROOT / "rct_control_plane" / "*.py")) + glob.glob(str(ROOT / "rct_control_plane" / "gateways" / "*.py")):
        for match in pattern.finditer(Path(path).read_text(encoding="utf-8", errors="replace")):
            found.add(next(g for g in match.groups() if g))
    return found


def test_every_stop_reason_the_runtime_names_has_a_plain_text():
    table = set(re.findall(r"^\s{2}(\w+): E\(", _read(LIB / "reason-text.ts"), re.M))
    missing = _runtime_stop_reasons() - table
    assert not missing, f"stop reasons with no text in reason-text.ts: {sorted(missing)}"


def test_a_text_without_a_runtime_source_is_one_of_the_known_indirect_ones():
    table = set(re.findall(r"^\s{2}(\w+): E\(", _read(LIB / "reason-text.ts"), re.M))
    indirect = {"budget_exceeded", "daily_budget_exhausted", "interrupted", "rate_limited", "running"}            # produced through a conditional expression or another module
    assert table - _runtime_stop_reasons() <= indirect, sorted(table - _runtime_stop_reasons() - indirect)


# ------------------------------------------------------------------ daemon tasks
def _daemon_task_names() -> set:
    names = set()
    for rel in ("autonomous_scheduler.py", "api.py", "cron_jobs.py", "scheduler.py"):
        path = ROOT / "rct_control_plane" / rel
        if path.exists():
            names |= set(re.findall(r"""name\s*=\s*["']([a-z][a-z0-9_]{5,40})["']""", _read(path)))
    return {n for n in names if n in {"audit_chain_verify", "audit_chain_anchor", "tasks_advance", "skill_curator_report", "reminder_poller", "cron_dispatcher"} or "_" in n and n.split("_")[0] in {"audit", "tasks", "skill", "reminder", "cron"}}


def test_every_daemon_task_has_a_thai_and_english_description():
    text = _read(LIB / "task-text.ts")
    keys = set(re.findall(r"^\s{2}(\w+): \{ en:", text, re.M))
    assert _daemon_task_names() <= keys, sorted(_daemon_task_names() - keys)
    for key in keys:
        entry = re.search(rf"^\s{{2}}{key}: \{{ en: \"([^\"]+)\", th: \"([^\"]+)\" \}}", text, re.M)
        assert entry and re.search(r"[฀-๿]", entry.group(2)) and not re.search(r"[฀-๿]", entry.group(1)), key


# ------------------------------------------------------------------ readiness
def test_the_readiness_states_the_server_can_produce_are_exactly_the_states_that_have_a_text():
    from rct_control_plane import readiness
    produced = set()
    grids = itertools.product(["ollama", "openrouter"], [None, [], ["qwen2.5:7b"], ["llama3.2:3b"]], [None, True, False], [0, 1], [0, 1], [0, 3])
    for provider, installed, key_present, keys, devices, episodes in grids:
        facts = {"provider": provider, "model": "qwen2.5:7b", "ollama_models": installed if provider == "ollama" else None, "key_present": key_present,
                 "needs_key": provider != "ollama", "approver_keys": keys, "approver_devices": devices, "episodes": episodes}
        for check in readiness.evaluate(facts)["checks"]:
            produced.add(f"{check['id']}:{check['state']}")
    texts = set(re.findall(r'^\s{2}"([a-z_]+:[a-z_]+)":', _read(LIB / "readiness-text.ts"), re.M))
    assert produced == texts, (sorted(produced - texts), sorted(texts - produced))


# ------------------------------------------------------------------ the guides and the command line
GUIDES = ("FIRST_APPROVER", "INSTALL_WINDOWS", "UPDATES", "APPROVE_WITH_DEVICE", "YOUR_DATA", "TESTER_FEEDBACK_FORM")


def _commands_in(text: str) -> list:
    """(tokens) for every `delentia ...` span in backticks or in a fenced block line."""
    spans = re.findall(r"`(delentia [^`\n]+)`", text) + re.findall(r"^\s*(delentia [^\n`]+)$", text, re.M) + re.findall(r"-m rct_control_plane\.cli ([^\n`\"]+)", text)
    out = []
    for span in spans:
        tokens = [t for t in span.replace("delentia ", "", 1).split() if t]
        out.append(tokens if span.startswith("delentia") else [t for t in span.split() if t])
    return out


def _resolve(tokens: list):
    from rct_control_plane import cli as cli_module
    command = cli_module.cli
    used = 0
    for token in tokens:
        if isinstance(command, click.Group) and token in command.commands:
            command = command.commands[token]
            used += 1
        else:
            break
    return command, tokens[used:]


@pytest.mark.parametrize("name", GUIDES)
@pytest.mark.parametrize("lang", ["TH", "EN"])
def test_every_command_and_option_a_guide_tells_you_to_type_exists(name, lang):
    path = DEMO / f"{name}_{lang}.md"
    assert path.is_file(), f"{path.name} is missing"
    options = set()
    for tokens in _commands_in(_read(path)):
        if not tokens or tokens[0].startswith(("<", "-", "%", "(", "[")):
            continue
        command, rest = _resolve(tokens)
        from rct_control_plane import cli as cli_module
        assert command is not cli_module.cli or tokens[0] in ("--help", "--version"), f"`delentia {' '.join(tokens)}` in {path.name}: no such command"
        known = {opt for param in command.params for opt in getattr(param, "opts", [])}
        for token in rest:
            if token.startswith("--"):
                flag = token.split("=")[0]
                assert flag in known | {"--help"}, f"`delentia {' '.join(tokens)}` in {path.name}: {flag} is not an option of `{command.name}`"
                options.add(flag)


@pytest.mark.parametrize("name", GUIDES)
def test_a_thai_guide_and_its_english_twin_name_the_same_commands(name):
    def commands(lang):
        found = set()
        for tokens in _commands_in(_read(DEMO / f"{name}_{lang}.md")):
            if tokens and not tokens[0].startswith(("<", "-", "%", "(", "[")):
                command, _ = _resolve(tokens)
                found.add(command.name)
        return found
    assert commands("TH") == commands("EN"), (sorted(commands("TH") ^ commands("EN")))


def test_the_guides_link_only_to_guides_that_exist():
    for path in DEMO.glob("*.md"):
        for target in re.findall(r"`([A-Z_]+_(?:TH|EN)\.md)`", _read(path)):
            assert (DEMO / target).is_file(), f"{path.name} points at {target}, which does not exist"


# ------------------------------------------------------------------ the Tools page in Thai (Round 101E)
def test_every_tool_the_agent_can_call_has_a_thai_line_on_the_tools_page_and_no_line_is_for_a_tool_that_does_not_exist():
    import asyncio
    from rct_control_plane.mcp_server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    lines = set(re.findall(r"^\s{2}(delentia_\w+): ", _read(LIB / "tool-text.ts"), re.M))
    assert names - lines == set(), f"tools with no Thai line (add them to apps/gui/src/lib/tool-text.ts): {sorted(names - lines)}"
    assert lines - names == set(), f"Thai lines for tools that do not exist: {sorted(lines - names)}"


def test_every_governance_control_has_a_thai_name_and_a_thai_way_to_change_it_and_none_is_for_a_control_that_does_not_exist():
    ids = set(re.findall(r'add\("(\w+)"', _read(ROOT / "rct_control_plane" / "governance_view.py")))
    table = _read(LIB / "governance-text.ts")
    entries = dict(re.findall(r'^\s{2}(\w+): \{ name: "([^"]+)"', table, re.M))
    fixes = dict(re.findall(r'^\s{2}(\w+): \{ name: "[^"]+", fix: "([^"]*)"', table, re.M))
    assert len(ids) >= 30                                                # the pattern still finds the controls
    assert ids - set(entries) == set(), f"controls with no Thai name (add them to apps/gui/src/lib/governance-text.ts): {sorted(ids - set(entries))}"
    assert set(entries) - ids == set(), f"Thai texts for controls that do not exist: {sorted(set(entries) - ids)}"
    # a control the server tells a person how to change must tell them in Thai too (and one it does not, must not invent one): compared on the real controls of an empty host
    import sqlite3
    import tempfile
    from rct_control_plane import governance_view
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn = sqlite3.connect(os.path.join(tmp, "g.db"))
        try:
            controls, _gaps = governance_view._controls(conn)
        finally:
            conn.close()
    assert len(controls) >= 28
    for c in controls:
        assert bool(c["how_to_change"]) == bool(fixes.get(c["id"])), f"{c['id']}: English way to change it {'exists' if c['how_to_change'] else 'is empty'}, Thai {'exists' if fixes.get(c['id']) else 'is empty'}"
