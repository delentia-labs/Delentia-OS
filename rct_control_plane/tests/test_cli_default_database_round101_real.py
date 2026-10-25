"""Round 101: `delentia approvals ...` and `delentia host-metrics` must look in the database the server writes to.

Found while writing the owner's guide to signing a policy change: the server and the loops keep pending actions (and the spend ledger) in agentic.db, the CLI opened control_plane.db unless --db was
given, so on a real host `delentia approvals list` said "No pending actions" while one was waiting.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

from click.testing import CliRunner

from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.cli import cli
from rct_control_plane.data_home import agentic_db_path, control_plane_db_path
from rct_control_plane.persistence import ControlPlanePersistence


def test_approvals_list_sees_an_action_the_server_wrote(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path))
    monkeypatch.delenv("RCT_DB_PATH", raising=False)
    monkeypatch.delenv("RCT_AGENTIC_DB_PATH", raising=False)
    assert agentic_db_path() != control_plane_db_path()
    created = PendingActionStore(ControlPlanePersistence(db_path=agentic_db_path())).create("ns", "a goal", "delentia_write_repo_file", {"relative_path": "x.md"})
    out = CliRunner().invoke(cli, ["approvals", "list", "--status", "ALL", "-o", "json"])
    assert out.exit_code == 0, out.output
    assert created.approval_id in [a["approval_id"] for a in json.loads(out.output[out.output.index("["):])]


def test_host_metrics_reads_the_database_the_agent_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path))
    monkeypatch.delenv("RCT_DB_PATH", raising=False)
    monkeypatch.delenv("RCT_AGENTIC_DB_PATH", raising=False)
    from rct_control_plane import envelope
    persistence = ControlPlanePersistence(db_path=agentic_db_path())
    envelope.record(persistence, "ns", "ep1", 0.0123, 456, "llm_finished")
    out = CliRunner().invoke(cli, ["host-metrics", "--format", "json"])
    assert out.exit_code == 0, out.output
    assert "0.0123" in out.output
