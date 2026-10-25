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


# ------------------------------------------------------------------ `approvals review`: read, then approve / reject / skip, nothing to copy
import pytest  # noqa: E402

from rct_control_plane import approvals as approvals_module, plan_approval  # noqa: E402


@pytest.fixture
def review_world(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("RCT_DB_PATH", raising=False)
    monkeypatch.delenv("RCT_AGENTIC_DB_PATH", raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.delenv(approvals_module.APPROVERS_ENV, raising=False)
    key = tmp_path / "keys" / "owner.pem"
    public = approvals_module.generate_approver_key(str(key))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "owner", "public_key_hex": public}]), encoding="utf-8")
    store = PendingActionStore(ControlPlanePersistence(db_path=agentic_db_path()))
    plan = plan_approval.build_plan("delete the old job", [{"tool_name": "delentia_cron_delete", "tool_args": {"job_id": "job-7"}}])
    a = store.create("owner", "delete the old job", plan_approval.PLAN_TOOL, {"plan": plan}, reason="a plan of 1 step(s) waits for one confirmation")
    b = store.create("owner", "write a note", "delentia_write_repo_file", {"relative_path": "docs/a.md"}, reason="needs a signature")
    c = store.create("owner", "something else", "delentia_cron_create", {"schedule": "daily"}, reason="needs a signature")
    return {"key": str(key), "store": store, "plan": a, "write": b, "cron": c}


def test_review_shows_the_plan_in_words_and_records_each_choice(review_world):
    w = review_world
    out = CliRunner().invoke(cli, ["approvals", "review", "--key", w["key"]], input="a\nr\ns\n")
    assert out.exit_code == 0, out.output
    assert "delentia_cron_delete" in out.output and "Plan:" in out.output and "job-7" in out.output       # the steps, not the first 200 characters of JSON
    statuses = {name: w["store"].get(w[name].approval_id).status for name in ("plan", "write", "cron")}
    assert statuses == {"plan": "APPROVED", "write": "REJECTED", "cron": "PENDING"}
    assert "approved 1, rejected 1, skipped 1" in out.output


def test_review_with_nothing_waiting_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("RCT_DB_PATH", raising=False)
    monkeypatch.delenv("RCT_AGENTIC_DB_PATH", raising=False)
    out = CliRunner().invoke(cli, ["approvals", "review", "--key", str(tmp_path / "none.pem")])
    assert out.exit_code == 0 and "Nothing is waiting for you" in out.output


def test_review_does_not_record_a_signature_from_a_key_nobody_trusts(review_world, tmp_path):
    stranger = tmp_path / "keys" / "stranger.pem"
    approvals_module.generate_approver_key(str(stranger))
    out = CliRunner().invoke(cli, ["approvals", "review", "--key", str(stranger)], input="a\ns\ns\n")
    assert "not recorded" in out.output and review_world["store"].get(review_world["plan"].approval_id).status == "PENDING"


def test_review_takes_the_host_database_from_the_host_folder(tmp_path, monkeypatch):
    host = tmp_path / "delentia-host"
    (host / "home").mkdir(parents=True)
    (host / "host.json").write_text("{}", encoding="utf-8")
    ControlPlanePersistence(db_path=str(host / "home" / "agentic.db"))
    from rct_control_plane.cli import _host_database
    assert _host_database(str(host)) == str(host / "home" / "agentic.db")
    assert _host_database(str(tmp_path / "missing")) is None


def test_approve_shows_a_plan_as_steps_before_signing(review_world):
    w = review_world
    out = CliRunner().invoke(cli, ["approvals", "approve", w["plan"].approval_id, "--key", w["key"]])
    assert out.exit_code == 0, out.output
    assert "Plan:" in out.output and "delentia_cron_delete" in out.output
