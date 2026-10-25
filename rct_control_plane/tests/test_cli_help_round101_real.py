"""
Round 101 (UX audit): `delentia --help` is what a new person reads first. Real click, real command table.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import re

from click.testing import CliRunner

from rct_control_plane import cli as cli_module


def _help() -> str:
    result = CliRunner().invoke(cli_module.cli, ["--help"], terminal_width=200)
    assert result.exit_code == 0
    return result.output


def test_the_help_starts_with_where_to_begin_and_names_the_product_not_a_module():
    text = _help()
    assert "Delentia" in text.splitlines()[2] and "RCT Control Plane" not in text
    assert text.index("Start here") < text.index("Everyday") < text.index("Older commands")
    for command in ("setup", "serve", "desk"):
        assert re.search(rf"^\s+{command}\s", text.split("Everyday")[0], re.MULTILINE), command


def test_every_command_is_still_listed_exactly_once_so_nothing_is_hidden_by_the_grouping():
    text = _help()
    listed = re.findall(r"^  ([a-z][a-z0-9-]*)\s{2,}\S", text, re.MULTILINE)
    commands = [n for n, c in cli_module.cli.commands.items() if not c.hidden]
    assert sorted(set(listed) & set(commands)) == sorted(commands), sorted(set(commands) - set(listed))
    assert len([n for n in listed if n in commands]) == len(commands)           # none twice


def test_no_description_carries_a_round_number():
    assert not re.search(r"\(Rounds? \d", _help())


def test_the_version_names_the_product():
    result = CliRunner().invoke(cli_module.cli, ["--version"])
    assert result.output.startswith("delentia, version")


def test_the_new_commands_exist_and_say_what_they_do():
    assert "desk" in cli_module.cli.commands and "web pages" in (cli_module.cli.commands["desk"].help or "")
