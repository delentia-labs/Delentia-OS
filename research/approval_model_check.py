"""
Bounded model check of the approval flow (Protocol section 13: "state machine / model checking for the approval flow", added Round 66).

The REAL code is run - `PendingActionStore`, `GovernedAutonomousLoop.resume`, Ed25519 signatures, the trusted-approver file, the approval clock, the pause switch - on every
sequence of up to LEN_EXHAUSTIVE events from an alphabet of hostile and ordinary events, plus a seeded sample of longer ones. After every `resume` the outcome is compared with
a small written SPECIFICATION of when an approved action may run. A difference is a bug in the code or in the spec; both are worth knowing. The safety properties checked are:

  I1  the tool runs only while a trusted, unrevoked key holds a valid signature over the CURRENT stored action
  I2  it runs at most once, whatever else happens (including a resume that was cancelled midway)
  I3  it never runs while the agent is paused, and a refused resume does not use the approval up
  I4  it never runs after the request was rejected or after either time window has passed
  I5  editing the stored row (arguments, or the status flag) never makes an unsigned action runnable

This is a bounded check (sequences up to the stated length, and a random sample beyond it), not a proof; the spec describes what SHOULD happen, and the alphabet is the events I
could name. It is about the flow of approvals, not about the model, the tools or a stolen key.

    python research/approval_model_check.py [--exhaustive 4] [--sample 20000] [--max-len 10] [--seed 20261010]
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))

EVENTS = ["sign1", "sign2", "sign_bad", "reject1", "revoke1", "wait_short", "wait_long", "pause", "unpause", "resume", "resume_cancelled", "edit_args", "edit_status_approved"]
WRITE = ("delentia_write_repo_file", {"relative_path": "docs/notes.md", "content_text": "hello"})
SHORT, LONG = 3600.0, 8 * 24 * 3600.0         # one hour (inside both windows) and eight days (outside both)


class Spec:
    """What should happen, written without looking at the implementation."""

    def __init__(self, dttl: float, ettl: float) -> None:
        self.dttl, self.ettl = dttl, ettl
        self.now = 0.0
        self.created = 0.0
        self.status = "PENDING"
        self.decided: Optional[float] = None
        self.real_signers: set = set()
        self.revoked: set = set()
        self.edited = False
        self.paused = False
        self.runs = 0

    def _expire(self) -> None:
        if self.status == "PENDING" and self.now - self.created > self.dttl:
            self.status = "EXPIRED"
        if self.status == "APPROVED" and self.decided is not None and self.now - self.decided > self.ettl:
            self.status = "EXPIRED"

    def apply(self, event: str) -> Optional[bool]:
        """Returns None for events with no run, otherwise whether the tool must have run."""
        self._expire()
        if event in ("wait_short", "wait_long"):
            self.now += SHORT if event == "wait_short" else LONG
            self._expire()
        elif event in ("sign1", "sign2"):
            key = event[-1]
            if self.status == "PENDING" and key not in self.revoked and not self.edited:
                self.real_signers.add(key)
                self.status, self.decided = "APPROVED", self.now
        elif event == "reject1":
            if self.status == "PENDING" and "1" not in self.revoked and not self.edited:
                self.status = "REJECTED"
        elif event == "revoke1":
            self.revoked.add("1")
        elif event == "pause":
            self.paused = True
        elif event == "unpause":
            self.paused = False
        elif event == "edit_args":
            self.edited = True
        elif event == "edit_status_approved":
            if self.status in ("PENDING", "REJECTED", "EXPIRED"):
                self.status = "APPROVED"           # the row says APPROVED; whether it can run depends on real signatures
                if self.decided is None:
                    self.decided = self.now
        elif event in ("resume", "resume_cancelled"):
            if self.paused:
                return False
            valid = {k for k in self.real_signers if k not in self.revoked}
            will_run = self.status == "APPROVED" and bool(valid) and not self.edited and self.runs == 0
            if will_run:
                self.runs += 1
                self.status = "EXECUTING" if event == "resume_cancelled" else "EXECUTED"
            return will_run
        return None


class Rig:
    def __init__(self, work: Path) -> None:
        from rct_control_plane import approvals
        from rct_control_plane.persistence import ControlPlanePersistence
        from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
        from rct_control_plane.skill_library import SkillLibrary
        from test_governed_autonomous_loop_real import _FakeKernel
        self.approvals, self.work = approvals, work
        self.keys: Dict[str, Tuple[str, str]] = {}
        for name in ("1", "2", "x"):
            path = work / "keys" / f"k{name}.pem"
            self.keys[name] = (str(path), approvals.generate_approver_key(str(path)))
        self.persistence = ControlPlanePersistence(db_path=str(work / "mc.db"))
        original_connect = self.persistence._connect

        def fast_connect():                                       # durability settings only: the rig does not test crash safety of SQLite, it tests the approval logic (about 140 sequences a minute otherwise)
            conn = original_connect()
            conn.execute("PRAGMA synchronous=OFF")
            return conn
        self.persistence._connect = fast_connect
        self.dispatched: List[Any] = []
        outer = self

        class Tools:
            async def list_tools(self):
                return [type("T", (), {"name": WRITE[0], "description": "write", "input_schema": {}})()]

            async def call_tool(self, name, args):
                outer.dispatched.append((name, dict(args)))
                if outer.hold is not None:
                    outer.hold.set()
                    await asyncio.sleep(30)               # a slow tool: cancelled by the 'resume_cancelled' event
                return type("R", (), {"content": [type("C", (), {"text": json.dumps({"ok": True})})()]})()

        self.hold: Optional[asyncio.Event] = None
        self.loop_obj = GovernedAutonomousLoop(mcp_server=Tools(), persistence=self.persistence, kernel=_FakeKernel(), max_iterations=3, namespace="mc",
                                               skill_library=SkillLibrary(db_path=str(work / "sk.db")))
        self.store = self.loop_obj._pending_actions()
        self.clock = 1_000_000.0
        approvals._now = lambda: self.clock                     # the approval clock is injected; nothing else reads it

    def trust(self, names: List[str]) -> None:
        (self.work / "approvers.json").write_text(json.dumps([{"name": n, "public_key_hex": self.keys[n][1]} for n in names]), encoding="utf-8")

    async def run(self, events: List[str], dttl: float, ettl: float) -> Optional[str]:
        """Runs one sequence; returns a description of the first disagreement with the spec or a violated invariant, or None."""
        from rct_control_plane import approvals, envelope
        self.dispatched.clear()
        self.clock += 1000.0
        start = self.clock
        os.environ[approvals.DECISION_TTL_ENV], os.environ[approvals.EXECUTION_TTL_ENV] = str(dttl), str(ettl)
        os.environ.pop(envelope.PAUSED_ENV, None)
        self.trust(["1", "2"])
        action = self.store.create("mc", "write notes", WRITE[0], dict(WRITE[1]))
        spec = Spec(dttl, ettl)
        spec.now = spec.created = 0.0
        paused = False
        history: List[str] = []
        for event in events:
            history.append(event)
            self.clock = start + spec.now
            try:
                expected = None
                if event in ("sign1", "sign2", "sign_bad", "reject1"):
                    key = "1" if event in ("sign1", "reject1", "sign_bad") else "2"
                    decision = "REJECTED" if event == "reject1" else "APPROVED"
                    current = self.store.get(action.approval_id)
                    if event == "sign_bad":
                        signed = approvals.sign_decision(self.keys["x"][0], action.approval_id, action.action_sha256, decision)     # a key nobody trusts
                        pub, sig = signed["public_key_hex"], signed["signature_hex"]
                    else:
                        signed = approvals.sign_decision(self.keys[key][0], action.approval_id, action.action_sha256, decision)
                        pub, sig = signed["public_key_hex"], signed["signature_hex"]
                    try:
                        self.store.decide(action.approval_id, decision, pub, sig)
                    except approvals.ApprovalError:
                        pass
                    if event != "sign_bad":                          # a signature from a key nobody trusts changes nothing in the spec
                        spec.apply(event)
                elif event == "revoke1":
                    self.trust(["2"])
                    spec.apply(event)
                elif event == "pause":
                    os.environ[envelope.PAUSED_ENV] = "1"
                    paused = True
                    spec.apply(event)
                elif event == "unpause":
                    os.environ.pop(envelope.PAUSED_ENV, None)
                    paused = False
                    spec.apply(event)
                elif event in ("wait_short", "wait_long"):
                    spec.apply(event)
                    self.clock = start + spec.now
                elif event == "edit_args":
                    with self.persistence._connect() as conn:
                        conn.execute("UPDATE pending_actions SET tool_args_json = ? WHERE approval_id = ?",
                                     (json.dumps({"relative_path": "docs/other.md", "content_text": "x"}), action.approval_id))
                    spec.apply(event)
                elif event == "edit_status_approved":
                    with self.persistence._connect() as conn:
                        conn.execute("UPDATE pending_actions SET status = 'APPROVED' WHERE approval_id = ? AND status IN ('PENDING','REJECTED','EXPIRED')", (action.approval_id,))
                    spec.apply(event)
                elif event in ("resume", "resume_cancelled"):
                    expected = spec.apply(event)
                    before = len(self.dispatched)
                    if event == "resume":
                        self.hold = None
                        try:
                            await self.loop_obj.resume(action.approval_id, continue_episode=False)
                        except approvals.ApprovalError:
                            pass
                        except Exception as exc:                       # noqa: BLE001
                            return f"{history}: resume raised {type(exc).__name__}: {exc}"
                    else:
                        self.hold = asyncio.Event()
                        task = asyncio.ensure_future(self.loop_obj.resume(action.approval_id, continue_episode=False))
                        try:
                            await asyncio.wait_for(self.hold.wait(), timeout=2.0)
                        except asyncio.TimeoutError:
                            pass
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, approvals.ApprovalError):
                            pass
                        except Exception as exc:                       # noqa: BLE001
                            return f"{history}: cancelled resume raised {type(exc).__name__}: {exc}"
                        self.hold = None
                    ran = len(self.dispatched) > before
                    if paused and ran:
                        return f"{history}: I3 the tool ran while paused"
                    if ran and self.dispatched[-1][1] != WRITE[1]:
                        return f"{history}: I5 the tool ran with arguments that were not the approved ones: {self.dispatched[-1]}"
                    if bool(expected) != ran:
                        return f"{history}: spec says run={bool(expected)} but the tool {'ran' if ran else 'did not run'} (status now {self.store.get(action.approval_id).status})"
                    if len(self.dispatched) > 1:
                        return f"{history}: I2 the tool ran {len(self.dispatched)} times"
            except Exception as exc:                                   # noqa: BLE001
                return f"{history}: harness error {type(exc).__name__}: {exc}"
        return None


def sequences(exhaustive: int, sample: int, max_len: int, seed: int):
    for n in range(1, exhaustive + 1):
        for combo in itertools.product(EVENTS, repeat=n):
            yield list(combo)
    rng = random.Random(seed)
    for _ in range(sample):
        n = rng.randint(exhaustive + 1, max_len)
        yield [rng.choice(EVENTS) for _ in range(n)]


async def main_async(args: argparse.Namespace) -> int:
    work = Path(tempfile.mkdtemp(prefix="delentia-mc-"))
    (work / "home").mkdir()
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_APPROVERS_FILE": str(work / "approvers.json")})
    for name in ("DELENTIA_APPROVER_PUBKEYS", "DELENTIA_FDIA_POLICY", "DELENTIA_NOTARY_URL"):
        os.environ.pop(name, None)
    import logging
    previous_disable = logging.root.manager.disable
    logging.disable(logging.WARNING)
    try:
        return await _check(args, work)
    finally:
        logging.disable(previous_disable)


async def _check(args: argparse.Namespace, work: Path) -> int:
    rig = Rig(work)
    failures: List[str] = []
    count = 0
    started = time.time()
    for seq in sequences(args.exhaustive, args.sample, args.max_len, args.seed):
        problem = await rig.run(seq, dttl=7 * 24 * 3600.0, ettl=24 * 3600.0)
        count += 1
        if problem:
            failures.append(problem)
            if len(failures) >= args.stop_after:
                break
        if count % 5000 == 0:
            print(f"  {count} sequences, {len(failures)} disagreements, {time.time() - started:.0f}s", flush=True)
    exhaustive_total = sum(len(EVENTS) ** n for n in range(1, args.exhaustive + 1))
    report = {"events": EVENTS, "exhaustive_up_to": args.exhaustive, "exhaustive_sequences": exhaustive_total, "random_sample": args.sample, "max_len": args.max_len,
              "sequences_run": count, "disagreements": len(failures), "first_disagreements": failures[:20], "seconds": round(time.time() - started, 1)}
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{count} sequences run ({exhaustive_total} exhaustive up to length {args.exhaustive} + {args.sample} random up to length {args.max_len}); {len(failures)} disagreements with the spec")
    for f in failures[:10]:
        print("  ", f[:400])
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exhaustive", type=int, default=4)
    parser.add_argument("--sample", type=int, default=20000)
    parser.add_argument("--max-len", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261010)
    parser.add_argument("--stop-after", type=int, default=50)
    parser.add_argument("--out", default=str(ROOT / "research" / "approval_model_check.json"))
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
