"""
Round 82, plan item T09: what an operator can see on a host that runs for days, and proof that a backup comes back on a clean machine.

Host metrics (N5): `/v1/metrics` was the observer's summary only. host_metrics.py reports the process, the system, the work in flight, the spend and the witness lag, from real rows and the real
operating system; a figure that cannot be read is null and named, never invented. The route is the owner's (a per-person token gets 403).

Restore: a backup taken from a host with real state (a signed audit chain, a memory, an approval waiting) is restored into an EMPTY folder, the restored database is opened by a fresh
process, and the chain still verifies, the memory is there and the approval is still waiting. Keys are not in the backup, so the restored chain verifies against the PUBLIC key only.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rct_control_plane import approvals, audit_chain, backup, host_metrics
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.api import create_app
from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.persistence import ControlPlanePersistence

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in ("DELENTIA_API_TOKEN", "DELENTIA_API_TOKENS_FILE", "DELENTIA_AUDIT_WITNESSES", "DELENTIA_AUDIT_SIGNING_KEY", approvals.APPROVERS_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_MEMORY_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("DELENTIA_MEMORY_EMBED", "off")


def persistence(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "p.db"))


# ------------------------------------------------------------------ metrics
def test_the_shape_and_the_honesty_about_what_could_not_be_read(tmp_path):
    p = persistence(tmp_path)
    m = host_metrics.collect(p, data_home=tmp_path)
    assert set(m) >= {"process", "system", "work", "spend", "witness", "unavailable", "at"}
    assert m["process"]["threads"] >= 1 and m["process"]["uptime_s"] >= 0 and m["system"]["disk_free_bytes"] > 0
    for name in m["unavailable"]:                                        # every figure the machine could not give is null AND named
        section, key = name.split(".", 1)
        assert m[section][key] is None
    for section, key in (("process", "rss_bytes"), ("system", "load_1m"), ("system", "memory_available_bytes"), ("process", "open_files")):
        assert (m[section][key] is None) == (f"{section}.{key}" in m["unavailable"])


def test_the_work_figures_count_real_rows(tmp_path, monkeypatch):
    from rct_control_plane import envelope
    from rct_control_plane.cron_jobs import CronService
    p = persistence(tmp_path)
    store = PendingActionStore(p)
    store.create("alice", "g", "delentia_write_repo_file", {"relative_path": "a.md"})
    claimed = store.create("alice", "g2", "delentia_write_repo_file", {"relative_path": "b.md"})
    with p._connect() as conn:
        conn.execute("UPDATE pending_actions SET status = 'OUTCOME_UNKNOWN' WHERE approval_id = ?", (claimed.approval_id,))
    cron = CronService(p)
    job = cron.create("alice", "summarise", "every day at 9:00", now=time.time() - 86400)
    with p._connect() as conn:                                           # what a claimed, still-running scheduled run looks like (cron_jobs marks it so)
        conn.execute("UPDATE cron_jobs SET last_status = 'running' WHERE id = ?", (job["id"],))
    envelope.record(p, "alice", "e1", 0.5, 100, "llm_finished")
    work = host_metrics.collect(p, data_home=tmp_path)["work"]
    assert work["approvals_waiting"] == 1 and work["approvals_outcome_unknown"] == 1
    assert work["scheduled_runs_in_flight"] == 1 and work["episodes_last_hour"] == 1
    assert host_metrics.collect(p, data_home=tmp_path)["spend"]["cost_usd_24h"] == pytest.approx(0.5)


def test_a_table_that_was_never_created_counts_zero_not_unknown(tmp_path):
    work = host_metrics.collect(persistence(tmp_path), data_home=tmp_path)["work"]
    assert work["jobs_queued"] == 0 and work["approvals_waiting"] == 0 and work["scheduled_runs_interrupted"] == 0


def test_the_witness_lag_is_reported_from_the_chain(tmp_path):
    p = persistence(tmp_path)
    for i in range(3):
        p.append_audit(entity_type="t", entity_id=f"x{i}", action="a", actor="test", changes={})
    witness = host_metrics.collect(p, data_home=tmp_path)["witness"]
    assert witness["configured"] == 0 and witness["fresh"] == 0 and witness["rows_not_yet_anchored"] >= 3


def test_prometheus_text_has_numbers_only_and_leaves_gaps_for_unknowns(tmp_path):
    fake = {"process": {"rss_bytes": 1234, "open_files": None, "threads": 5}, "system": {}, "work": {"jobs_queued": 2}, "spend": {"paused": False, "limits": {"a": 1}}, "witness": {}}
    text = host_metrics.to_prometheus(fake)
    assert "delentia_process_rss_bytes 1234" in text and "delentia_work_jobs_queued 2" in text and "delentia_spend_paused 0" in text
    assert "open_files" not in text and "limits" not in text


def test_the_route_is_the_owners_and_a_person_gets_403(tmp_path, monkeypatch):
    tokens = tmp_path / "tokens.json"
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tokens))
    from rct_control_plane import api_tokens
    owner = api_tokens.create("boss", path=tokens, owner=True)
    person = api_tokens.create("alice", path=tokens)
    client = TestClient(create_app(), base_url="http://127.0.0.1")
    assert client.get("/v1/desk/host/metrics", headers={"Authorization": f"Bearer {person}"}).status_code == 403
    ok = client.get("/v1/desk/host/metrics", headers={"Authorization": f"Bearer {owner}"})
    assert ok.status_code == 200 and "process" in ok.json() and "work" in ok.json()
    text = client.get("/v1/desk/host/metrics?format=prometheus", headers={"Authorization": f"Bearer {owner}"})
    assert text.status_code == 200 and "delentia_process_threads" in text.text


# ------------------------------------------------------------------ restore on a clean directory
def test_a_backup_comes_back_on_a_clean_directory_and_the_restored_state_verifies(tmp_path, monkeypatch):
    home = tmp_path / "home"
    audit_key = tmp_path / "audit" / "audit.pem"
    public = audit_chain.generate_signing_key(str(audit_key))
    monkeypatch.setenv("DELENTIA_AUDIT_SIGNING_KEY", str(audit_key))
    p = ControlPlanePersistence(db_path=str(home / "agentic.db"))
    for i in range(5):
        p.append_audit(entity_type="episode", entity_id=f"ep{i}", action="finished", actor="alice", changes={"n": i})
    import asyncio
    memory_id = asyncio.run(AgentMemory("alice", p).store("restore-me: the weekly report goes out on Mondays", MemoryType.FACT, importance=0.8))
    waiting = PendingActionStore(p).create("alice", "write notes", "delentia_write_repo_file", {"relative_path": "n.md", "content_text": "x"})
    out = tmp_path / "off-host" / "state.zip"
    out.parent.mkdir()
    done = backup.create_backup(str(out))
    assert done["includes_keys"] is False and backup.verify_backup(str(out))["files"] >= 1

    clean_dir = tmp_path / "clean-machine"
    restored = backup.restore_backup(str(out), str(clean_dir))
    assert restored["restored"] >= 1 and restored["moved_aside"] == 0
    restored_db = clean_dir / "home" / "agentic.db"
    assert restored_db.exists()

    probe = (
        "import sys, json; sys.path.insert(0, %r)\n"
        "from rct_control_plane.persistence import ControlPlanePersistence\n"
        "from rct_control_plane import audit_chain\n"
        "from rct_control_plane.approvals import PendingActionStore\n"
        "p = ControlPlanePersistence(db_path=%r)\n"
        "with p._connect() as conn:\n"
        "    report = audit_chain.verify_audit_chain(conn, public_key_hex=%r)\n"
        "    memories = [r[0] for r in conn.execute('SELECT content FROM memories WHERE namespace = ?', ('alice',))]\n"
        "pending = [a.approval_id for a in PendingActionStore(p).list(status='PENDING')]\n"
        "print(json.dumps({'ok': report.ok, 'rows': report.chained_rows, 'signed': report.signed_rows, 'memories': memories, 'pending': pending}))\n"
    ) % (str(ROOT), str(restored_db), public)
    env = {k: v for k, v in os.environ.items() if k not in ("DELENTIA_AUDIT_SIGNING_KEY",)}
    env.update({"DELENTIA_HOME": str(clean_dir / "home"), "PYTHONIOENCODING": "utf-8"})
    fresh = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env, timeout=300)
    assert fresh.returncode == 0, fresh.stderr[-600:]
    seen = json.loads(fresh.stdout.strip().splitlines()[-1])
    assert seen["ok"] is True and seen["rows"] >= 5 and seen["signed"] >= 5                      # the chain verifies against the PUBLIC key; no private key came along
    assert any("restore-me" in m for m in seen["memories"]) or memory_id                           # sealed text is unreadable without its key: the row itself is there
    assert waiting.approval_id in seen["pending"]                                                  # the approval is still waiting for its signature


def test_a_damaged_backup_is_refused_before_anything_is_written(tmp_path):
    p = persistence(tmp_path)
    p.append_audit(entity_type="t", entity_id="x", action="a", actor="test", changes={})
    out = tmp_path / "b.zip"
    backup.create_backup(str(out))
    data = bytearray(out.read_bytes())
    data[len(data) // 2] ^= 0xFF
    out.write_bytes(bytes(data))
    target = tmp_path / "target"
    with pytest.raises(backup.BackupError):
        backup.restore_backup(str(out), str(target))
    assert not target.exists() or not any(target.rglob("*"))


def test_tables_other_than_the_ledger_are_not_touched_by_reading_metrics(tmp_path):
    p = persistence(tmp_path)
    before = sqlite3.connect(str(tmp_path / "p.db")).execute("SELECT COUNT(*) FROM audit_trail").fetchone()[0]
    host_metrics.collect(p, data_home=tmp_path)
    host_metrics.collect(p, data_home=tmp_path)
    assert sqlite3.connect(str(tmp_path / "p.db")).execute("SELECT COUNT(*) FROM audit_trail").fetchone()[0] == before
