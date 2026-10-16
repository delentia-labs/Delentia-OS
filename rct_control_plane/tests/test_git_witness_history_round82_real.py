"""
Round 82, plan item T01: the Git witness must not be fooled by a NORMAL commit.

Found by the Architect's research plan of 2026-10-15 and reproduced here: with only a Git witness, an attacker who controls the host, its audit signing key and the push
credential of the ledger can rewrite the audit chain, sign the new head and replace the ledger with an ordinary fast-forward commit. `GitWitness.fetch()` used to read only
the newest version of the ledger file, so the witness answered PASS although a signed, different head was still in the remote's history.

Real SQLite audit chain, real Ed25519 signatures, a real git repository with a real bare "remote", and an attacker who pushes. Nothing is mocked except the one mutation test,
which switches the new check off on purpose to prove the tests can tell the difference.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import shutil
import sqlite3
import subprocess

import pytest

from rct_control_plane import audit_chain, audit_witness as aw
from rct_control_plane.persistence import ControlPlanePersistence

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(*args, cwd=None):
    return subprocess.run(["git", "-c", "user.name=x", "-c", "user.email=x@x", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def world(tmp_path, monkeypatch):
    for name in (aw.WITNESSES_ENV, aw.URL_ENV, aw.KEY_ID_ENV, aw.INTERVAL_ENV, audit_chain.PUBKEY_ENV):
        monkeypatch.delenv(name, raising=False)
    key = tmp_path / "audit.pem"
    public = audit_chain.generate_signing_key(str(key))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(key))
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "chain.db"))
    bare = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(bare))
    anchors = tmp_path / "anchors"
    anchors.mkdir()
    git("init", "-q", "-b", "main", cwd=str(anchors))
    git("remote", "add", "origin", str(bare), cwd=str(anchors))
    config = [{"type": "git", "name": "git-mirror", "path": str(anchors), "remote": "origin", "branch": "main", "key_id": "host-1"}]
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps(config))
    return persistence, bare, tmp_path, public, config


def add_rows(persistence, n, label="event"):
    for i in range(n):
        persistence.append_audit(entity_type="governed_loop_episode_start", entity_id=f"{label}-{i}", action="episode_start", actor="alice", changes={"goal": f"{label} {i}"})


def connect(persistence):
    return persistence._connect()


def rewrite_history(persistence):
    """What someone with the host's root can do: change an old row, recompute every hash after it and sign it all again with the key that is on the host."""
    with sqlite3.connect(str(persistence.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT c.seq, c.audit_id, t.entity_type, t.entity_id, t.action, t.actor, t.changes, t.created_at FROM audit_chain c JOIN audit_trail t ON t.id = c.audit_id ORDER BY c.seq").fetchall()
        signer = audit_chain.load_signing_key()
        prev = audit_chain.GENESIS_HASH
        for r in rows:
            changes = '{"goal": "nothing happened here"}' if r["seq"] == 2 else r["changes"]
            if r["seq"] == 2:
                conn.execute("UPDATE audit_trail SET changes = ? WHERE id = ?", (changes, r["audit_id"]))
            h = audit_chain.row_hash(prev, r["audit_id"], r["entity_type"], r["entity_id"], r["action"], r["actor"], changes, r["created_at"])
            conn.execute("UPDATE audit_chain SET prev_hash = ?, row_hash = ?, signature_hex = ? WHERE seq = ?", (prev, h, signer.sign(bytes.fromhex(h)).hex(), r["seq"]))
            prev = h


def check(persistence):
    with connect(persistence) as conn:
        return aw.check_witnesses(conn)[0]


def attacker_clone(bare, tmp_path, name="attacker"):
    clone = tmp_path / name
    git("clone", "-q", str(bare), str(clone))
    return clone


def push_ordinary_commit(clone, text, message="tidy", path="anchors/host-1.jsonl"):
    target = clone / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git("add", "-A", cwd=str(clone))
    git("commit", "-q", "-m", message, cwd=str(clone))
    git("push", "-q", "origin", "main", cwd=str(clone))                                         # fast-forward: no --force


def signed_line(persistence, key_id="host-1"):
    with connect(persistence) as conn:
        return json.dumps(audit_chain.sign_anchor(conn, key_id), sort_keys=True, separators=(",", ":")) + "\n"


# ------------------------------------------------------------------ what must keep working

def test_a_normal_append_passes_and_grows_the_history(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 4)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    add_rows(persistence, 3, "more")
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    report = check(persistence)
    assert report["ok"] is True and report["problems"] == [] and report["highest_anchored"] == 7


def test_a_rewrite_of_the_database_alone_is_caught(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 6)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    rewrite_history(persistence)
    assert check(persistence)["ok"] is False


# ------------------------------------------------------------------ the finding (T01)

def rewrite_and_replace_the_ledger(persistence, bare, tmp_path):
    rewrite_history(persistence)
    clone = attacker_clone(bare, tmp_path)
    push_ordinary_commit(clone, signed_line(persistence))                                       # the ledger now holds ONE line: the rewritten chain's head, correctly signed


def test_a_rewrite_plus_a_normal_commit_that_replaces_the_ledger_is_caught(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 6)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    rewrite_and_replace_the_ledger(persistence, bare, tmp_path)
    report = check(persistence)
    assert report["ok"] is False
    assert any("rewritten" in p for p in report["problems"])                                    # the OLD anchor, still in the history, no longer matches the chain
    assert any("removed or changed" in p for p in report["problems"])                           # and the commit that took it out of the ledger is named


def test_deleting_an_old_anchor_line_by_a_normal_commit_is_caught_even_when_the_chain_is_honest(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 4)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    add_rows(persistence, 3, "more")
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    clone = attacker_clone(bare, tmp_path)
    path = clone / "anchors" / "host-1.jsonl"
    last_only = path.read_text(encoding="utf-8").splitlines()[-1] + "\n"
    push_ordinary_commit(clone, last_only, "drop the first anchor")
    report = check(persistence)
    assert report["ok"] is False and any("removed or changed" in p for p in report["problems"])


def test_editing_an_old_anchor_line_by_a_normal_commit_is_caught(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 4)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    add_rows(persistence, 3, "more")
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    clone = attacker_clone(bare, tmp_path)
    lines = (clone / "anchors" / "host-1.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["head"] = "b" * 64
    push_ordinary_commit(clone, "\n".join([json.dumps(first, sort_keys=True, separators=(",", ":")), *lines[1:]]) + "\n", "fix a typo")
    report = check(persistence)
    assert report["ok"] is False and any("removed or changed" in p for p in report["problems"])


def force_push_rewritten_history(persistence, bare, tmp_path):
    clone = attacker_clone(bare, tmp_path)
    git("checkout", "-q", "--orphan", "fresh", cwd=str(clone))                                  # a history that never contained the old anchors
    git("rm", "-rfq", ".", cwd=str(clone))
    target = clone / "anchors" / "host-1.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(signed_line(persistence), encoding="utf-8")
    git("add", "-A", cwd=str(clone))
    git("commit", "-q", "-m", "start over", cwd=str(clone))
    git("push", "-q", "--force", "origin", "fresh:main", cwd=str(clone))


def test_a_force_push_that_starts_the_ledger_over_is_caught_by_the_tip_seen_at_the_last_check(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 6)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    assert check(persistence)["ok"] is True                                                     # an honest check records the tip it saw
    rewrite_history(persistence)
    force_push_rewritten_history(persistence, bare, tmp_path)
    report = check(persistence)
    assert report["ok"] is False and any("force-push or branch reset" in p for p in report["problems"])


def test_a_force_push_is_caught_by_a_pinned_commit_even_with_no_earlier_check(world, monkeypatch):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 6)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    pinned = git("rev-parse", "main", cwd=str(bare)).strip()                                   # what an independent verifier wrote down earlier
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([{**config[0], "pin": pinned}]))
    rewrite_history(persistence)
    force_push_rewritten_history(persistence, bare, tmp_path)
    report = check(persistence)
    assert report["ok"] is False and any("pinned commit" in p for p in report["problems"])


def test_a_pin_that_is_not_a_commit_hash_is_refused_at_configuration_time(world, monkeypatch):
    persistence, bare, tmp_path, public, config = world
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([{**config[0], "pin": "main"}]))
    with pytest.raises(aw.WitnessError, match="pin"):
        aw.specs_from_env()


# ------------------------------------------------------------------ a witness that cannot see the whole history must not pass

def test_a_shallow_copy_of_the_ledger_is_an_error_not_a_pass(world, tmp_path, monkeypatch):
    persistence, bare, _, public, config = world
    add_rows(persistence, 4)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    add_rows(persistence, 3, "more")
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", bare.as_uri(), str(shallow)], check=True, capture_output=True)
    git("remote", "set-url", "origin", bare.as_uri(), cwd=str(shallow))
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([{**config[0], "path": str(shallow)}]))
    report = check(persistence)
    assert report["ok"] is False and any("shallow" in p for p in report["problems"])


def test_a_fresh_clone_with_no_earlier_state_verifies_an_honest_ledger(world, tmp_path, monkeypatch):
    persistence, bare, _, public, config = world
    add_rows(persistence, 4)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    add_rows(persistence, 3, "more")
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    fresh = tmp_path / "fresh-verifier"                                                         # an independent machine: an empty folder and the remote's address
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([{**config[0], "path": str(fresh), "remote": bare.as_uri()}]))
    report = check(persistence)
    assert report["ok"] is True and report["highest_anchored"] == 7


def test_an_unreachable_remote_is_not_a_pass(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 3)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    bare.rename(tmp_path / "gone.git")                                                            # the remote is not there any more (rename: Windows cannot delete git's read-only objects)
    report = check(persistence)
    assert report["ok"] is False


def test_removing_the_ledger_of_a_rotated_out_key_is_caught(world, monkeypatch):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 4)
    with connect(persistence) as conn:
        aw.anchor_all(conn)                                                                       # key host-1 anchors
    monkeypatch.setenv(aw.WITNESSES_ENV, json.dumps([{**config[0], "key_id": "host-2"}]))        # the key is rotated: the new key has its own file
    add_rows(persistence, 2, "after")
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    assert check(persistence)["ok"] is True
    clone = attacker_clone(bare, tmp_path)
    git("rm", "-q", "anchors/host-1.jsonl", cwd=str(clone))                                     # the old key's anchors are removed by an ordinary commit
    git("commit", "-q", "-m", "clean up the old key", cwd=str(clone))
    git("push", "-q", "origin", "main", cwd=str(clone))
    report = check(persistence)
    assert report["ok"] is False and any("removed or changed" in p for p in report["problems"])


# ------------------------------------------------------------------ the negative control

def test_with_the_history_check_switched_off_the_attack_passes_again(world, monkeypatch):
    """If this test still passes after the check is removed, the other tests prove nothing. Here the history is replaced by the old behaviour (the newest file only)."""
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 6)
    with connect(persistence) as conn:
        aw.anchor_all(conn)

    def newest_file_only(self, ref):
        text = self._git("show", f"{ref}:{self.file.as_posix()}", check=False)
        return [json.loads(line) for line in text.splitlines() if line.strip()], []

    monkeypatch.setattr(aw.GitWitness, "_history", newest_file_only)
    rewrite_and_replace_the_ledger(persistence, bare, tmp_path)
    assert check(persistence)["ok"] is True                                                     # exactly the hole the plan described


# ------------------------------------------------------------------ the independent verifier (another machine, no Delentia code)

VERIFIER = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "verify_audit_bundle.py")


def export_bundle(persistence, tmp_path):
    with connect(persistence) as conn:
        bundle = aw.export_proof(conn)
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


def run_verifier(path, *args):
    done = subprocess.run([sys.executable, VERIFIER, str(path), "--json", *args], capture_output=True, text=True, cwd=str(path.parent))
    return done.returncode, json.loads(done.stdout) if done.stdout.strip() else {}


def test_the_independent_verifier_accepts_an_honest_ledger(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 4)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    add_rows(persistence, 3, "more")
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    pinned = git("rev-parse", "main", cwd=str(bare)).strip()
    code, report = run_verifier(export_bundle(persistence, tmp_path), "--pubkey", public, "--git-ledger", bare.as_uri(), "--git-key-id", "host-1", "--pin", pinned)
    assert code == 0 and report["ok"] and report["anchors_checked"] == 2


def test_the_independent_verifier_catches_the_replacement_of_the_ledger_by_a_normal_commit(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 6)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    old_tip = git("rev-parse", "main", cwd=str(bare)).strip()
    rewrite_and_replace_the_ledger(persistence, bare, tmp_path)
    path = export_bundle(persistence, tmp_path)                                                 # the bundle of the REWRITTEN chain: internally consistent, correctly signed
    code, report = run_verifier(path, "--pubkey", public)
    assert code == 0                                                                            # alone, the bundle is consistent: this is exactly why a witness is needed
    code, report = run_verifier(path, "--pubkey", public, "--git-ledger", bare.as_uri(), "--git-key-id", "host-1", "--pin", old_tip)
    assert code == 1 and report["ok"] is False
    text = " | ".join(report["problems"])
    assert "removed or changed" in text and "rewritten" in text


def test_the_independent_verifier_catches_a_force_push_with_a_pin_and_says_what_a_missing_pin_cannot_tell(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 6)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    pinned = git("rev-parse", "main", cwd=str(bare)).strip()
    rewrite_history(persistence)
    force_push_rewritten_history(persistence, bare, tmp_path)
    path = export_bundle(persistence, tmp_path)
    code, report = run_verifier(path, "--pubkey", public, "--git-ledger", bare.as_uri(), "--git-key-id", "host-1", "--pin", pinned)
    assert code == 1 and any("pinned commit" in p for p in report["problems"])
    code, report = run_verifier(path, "--pubkey", public, "--git-ledger", bare.as_uri(), "--git-key-id", "host-1")
    assert code == 0 and any("no --pin" in n for n in report["notes"])                          # without a pin the verifier says it cannot tell: it does not claim a pass it cannot earn


def test_the_independent_verifier_fails_when_the_ledger_cannot_be_read(world):
    persistence, bare, tmp_path, public, config = world
    add_rows(persistence, 3)
    with connect(persistence) as conn:
        aw.anchor_all(conn)
    code, report = run_verifier(export_bundle(persistence, tmp_path), "--pubkey", public, "--git-ledger", (tmp_path / "does-not-exist.git").as_uri(), "--git-key-id", "host-1")
    assert code == 1 and any("could not be read" in p for p in report["problems"])
