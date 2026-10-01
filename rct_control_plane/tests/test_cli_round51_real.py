"""Round 51: the CLI commands that mirror the Desk's Growth, Memory and Algorithms pages."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

from click.testing import CliRunner

from rct_control_plane.cli import cli
from rct_control_plane.persistence import ControlPlanePersistence


def test_memory_add_and_list_round_trip(tmp_path):
    db = str(tmp_path / "m.db")
    runner = CliRunner()
    added = runner.invoke(cli, ["memory", "add", "The staging database is stg-db-1", "--namespace", "me", "--db", db])
    assert added.exit_code == 0 and "stored mem_" in added.output
    listed = runner.invoke(cli, ["memory", "list", "--namespace", "me", "--db", db])
    assert "stg-db-1" in listed.output and runner.invoke(cli, ["memory", "list", "--namespace", "other", "--db", db]).output.strip() == ""


def test_growth_show_and_evolution(tmp_path):
    db = str(tmp_path / "g.db")
    persistence = ControlPlanePersistence(db_path=db)
    runner = CliRunner()
    assert "No growth recorded yet" in runner.invoke(cli, ["growth", "show", "--db", db]).output
    persistence.save_state(state_id="x", namespace="mee_growth", key="u",
                           value={"session": {"g_current": 1.5, "resilience": 1.0}, "episodes": 4, "verified_episodes": 3})
    shown = runner.invoke(cli, ["growth", "show", "--db", db]).output
    assert "u  G=1.5" in shown and "episodes=4" in shown
    report = json.loads(runner.invoke(cli, ["growth", "evolution", "--namespace", "u", "--db", db]).output)
    assert report["goals_repeated"] == 0


def test_algorithms_lists_all_41_with_what_each_needs():
    out = CliRunner().invoke(cli, ["algorithms"]).output
    assert out.startswith("41 algorithms")
    for n in range(1, 42):
        assert f"ALGO-{n:02d}" in out
    assert "needs=model" in out and "needs=network" in out
