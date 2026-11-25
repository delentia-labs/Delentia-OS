"""
Round 116: a readable trace of what the governed loop did, built from the record it already writes.

Every governed episode leaves rows in its audit trail (`agentic.db`, table `audit_trail`): the start (GUARD verdict, FDIA D and I, the RCT-7 plan, the JITNA
signature check), one gate row per tool call the model asked for (D, I, A, F, the owner-policy rule and its decision), the model's step with its reasoning, a
pending action when a signature is needed, the signature that approved it, the action that then ran exactly once, the end (stop reason, VERIFY, MEE, cost)
and the Intent Loop's pillars. This module reads those rows and prints them one line each, in order, in plain words:

    python -m rct_control_plane.run_trace <home or agentic.db> [--follow] [--reasoning] [--lang th]

`--follow` keeps printing new rows as a running server or test writes them (it polls the database; it never writes to it). The research benchmark prints the
same trace live for every d0 run (`research.daaes benchmark`, on unless `--no-trace`).

Only reads. It needs nothing the run did not already record, it changes nothing a model is shown, and it costs nothing. Text fields that the runtime seals
per person (the goal, the model's reasoning) are opened with that person's key from the folder next to the database when it is there, and shown as
"[sealed]" when it is not. Never shown: tool arguments longer than a short preview, file contents, keys.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

PREVIEW = 90
KINDS = ("governed_loop_guard", "governed_loop_episode_start", "governed_loop_fdia_gate", "autonomous_loop_step", "pending_action_created",
         "pending_action_decided", "pending_action_executed", "governed_loop_episode_end", "intent_loop_pillars", "governed_loop_plan",
         "algorithm_pipeline", "small_edit_autorun", "governed_loop_envelope", "cron_job")

WORDS = {
    "en": {"guard_clean": "goal screened by CORD: clean", "guard_block": "goal BLOCKED by CORD", "plan": "RCT-7 plan", "steps": "steps",
           "missing": "missing data", "jitna_ok": "episode packet signed (JITNA, Ed25519) and verified", "jitna_bad": "episode packet NOT verified",
           "allow": "allowed", "ask": "needs a human signature: the episode stops and waits", "block": "BLOCKED", "rule": "rule",
           "waiting": "waiting for a person", "signatures": "signature(s) needed", "approved": "approved with a verified signature", "rejected": "rejected by a person",
           "ran_once": "ran exactly once", "stopped": "stopped", "calls": "model calls", "verify": "VERIFY", "skill": "skill learned", "cost": "cost",
           "pillars": "Intent Loop", "memories": "memories recalled", "skills_used": "skills used", "pipeline": "algorithm pipeline", "ok": "ok",
           "errors": "errors", "autorun": "small edit ran under the owner's rule", "envelope": "safety envelope", "chain": "audit chain",
           "chain_ok": "rows, hash-chained, every link verified", "chain_bad": "DOES NOT VERIFY", "model": "model", "sealed": "[sealed]", "plan_card": "plan proposed", "answer": "the model gave its final answer"},
    "th": {"guard_clean": "ตรวจเป้าหมายด้วย CORD: ผ่าน", "guard_block": "CORD บล็อกเป้าหมาย", "plan": "แผน RCT-7", "steps": "ขั้น",
           "missing": "ข้อมูลที่ยังขาด", "jitna_ok": "แพ็กเก็ตของตอนนี้เซ็น (JITNA, Ed25519) และตรวจผ่าน", "jitna_bad": "แพ็กเก็ตของตอนนี้ตรวจไม่ผ่าน",
           "allow": "อนุญาต", "ask": "ต้องให้คนเซ็น: ตอนนี้หยุดรอ", "block": "บล็อก", "rule": "กฎ",
           "waiting": "รอคนตัดสิน", "signatures": "ลายเซ็นที่ต้องใช้", "approved": "อนุมัติด้วยลายเซ็นที่ตรวจแล้ว", "rejected": "คนปฏิเสธ",
           "ran_once": "ทำงานครั้งเดียวพอดี", "stopped": "จบด้วย", "calls": "ครั้งที่เรียกโมเดล", "verify": "VERIFY", "skill": "เรียนรู้เป็นทักษะ", "cost": "ค่าใช้จ่าย",
           "pillars": "Intent Loop", "memories": "ความจำที่ดึงมาใช้", "skills_used": "ทักษะที่ใช้", "pipeline": "pipeline อัลกอริทึม", "ok": "สำเร็จ",
           "errors": "ผิดพลาด", "autorun": "แก้ไฟล์เล็กตามกฎของเจ้าของ", "envelope": "safety envelope", "chain": "audit chain",
           "chain_ok": "แถว เชื่อมด้วย hash ตรวจครบทุกข้อต่อ", "chain_bad": "ตรวจไม่ผ่าน", "model": "โมเดล", "sealed": "[ปิดผนึก]", "plan_card": "เสนอแผน", "answer": "โมเดลให้คำตอบสุดท้าย"},
}


def _db_path(target: Path) -> Path:
    target = Path(target)
    return target / "agentic.db" if target.is_dir() else target


def _keys_dir(db: Path) -> Optional[Path]:
    for name in ("memkeys", "memory_keys"):
        candidate = db.parent / name
        if candidate.is_dir():
            return candidate
    return None


class Opener:
    """Opens values the runtime sealed per person, with the key file next to the database. Reads the key file only; never touches the environment of
    the process that is running (a trace can run inside the same process as the episode it follows)."""

    def __init__(self, keys_dir: Optional[Path]):
        self.keys_dir = keys_dir
        self._keys: Dict[str, Optional[bytes]] = {}

    def _key(self, namespace: str) -> Optional[bytes]:
        if namespace not in self._keys:
            key = None
            if self.keys_dir is not None:
                path = self.keys_dir / (hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:40] + ".key")
                try:
                    key = bytes.fromhex(path.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    key = None
            self._keys[namespace] = key
        return self._keys[namespace]

    def open(self, namespace: str, value: Any) -> Any:
        if not (isinstance(value, dict) and {"sealed", "sha256"} <= set(value)):
            return value
        key = self._key(namespace)
        if key is None:
            return None
        try:
            from rct_control_plane.memory_erasure import _aead, fingerprint
            data = json.loads(value["sealed"])
            if fingerprint(key) != data.get("kid"):
                return None
            blob = base64.b64decode(data["enc"])
            return json.loads(_aead(key).decrypt(blob[:12], blob[12:], namespace.encode("utf-8")).decode("utf-8")).get("v")
        except Exception:                                                       # noqa: BLE001 - an unopenable value is shown as sealed, never guessed
            return None


def read_rows(db: Path, after_id: int = 0) -> List[Tuple[int, str, str, str, Dict[str, Any], str]]:
    """(id, entity_type, action, actor, changes, created_at) of the rows this trace shows, after `after_id`. A database that is being written is read
    with a short timeout and an empty list on a lock (the next poll gets them)."""
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return []
    try:
        marks = ",".join("?" for _ in KINDS)
        rows = conn.execute(f"SELECT id, entity_type, action, actor, changes, created_at FROM audit_trail WHERE id > ? AND entity_type IN ({marks}) ORDER BY id",
                            (after_id, *KINDS)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    out = []
    for rid, et, action, actor, changes, created in rows:
        try:
            data = json.loads(changes or "{}")
        except ValueError:
            data = {}
        out.append((int(rid), et, action or "", actor or "", data if isinstance(data, dict) else {}, created or ""))
    return out


def _short(value: Any, n: int = PREVIEW) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _args(args: Any) -> str:
    """Short arguments of a tool call: a long text is replaced by its length (file contents are never printed)."""
    if not isinstance(args, dict):
        return _short(args, 60)
    shown = {k: (f"<{len(v)} chars>" if isinstance(v, str) and len(v) > 60 else v) for k, v in args.items()}
    return _short(shown, 80)


def render_row(row: Tuple[int, str, str, str, Dict[str, Any], str], opener: Opener, *, lang: str = "en", reasoning: bool = False) -> List[str]:
    """The line(s) one audit row becomes. Pure apart from opening sealed text."""
    w = WORDS.get(lang, WORDS["en"])
    _rid, et, action, actor, c, _created = row
    ns = str(c.get("namespace") or actor or "")
    if et == "governed_loop_episode_start":
        goal = opener.open(ns, c.get("goal"))
        lines = [f"── START  {_short(goal) if goal is not None else w['sealed']}"]
        guard = c.get("guard") or {}
        verdict = str(guard.get("verdict") or guard.get("status") or ("clean" if not guard.get("rejected") else "blocked")) if isinstance(guard, dict) else str(guard)
        lines.append(f"   GUARD  {w['guard_clean'] if 'block' not in verdict.lower() and 'reject' not in verdict.lower() else w['guard_block']}")
        steps = c.get("rct7_steps") or []
        intent = c.get("intent") or {}
        itype = intent.get("intent_type") if isinstance(intent, dict) else None
        lines.append(f"   THINK  {w['plan']}: {len(steps)} {w['steps']}" + (f" · intent {itype}" if itype else ""))
        evidence = c.get("data_evidence") or {}
        missing = evidence.get("missing") or [] if isinstance(evidence, dict) else []
        lines.append(f"   FDIA   D={float(c.get('D') or 0):.2f}  I={float(c.get('I') or 0):.2f}" + (f"  · {w['missing']}: {len(missing)}" if missing else ""))
        if "jitna_verified" in c:
            lines.append(f"   JITNA  {w['jitna_ok'] if c.get('jitna_verified') else w['jitna_bad']}")
        route = c.get("route") or {}
        if isinstance(route, dict) and route.get("path"):
            lines.append(f"   ROUTE  {route.get('path')} (max {route.get('max_iterations')})")
        return lines
    if et == "governed_loop_fdia_gate":
        pol = c.get("policy") or {}
        action_type = str(pol.get("action_type") or "")
        if c.get("blocked"):
            verdict = w["block"]
        elif pol.get("needs_signature") or action_type == "REQUIRE_HUMAN_SIGNATURE":
            verdict = w["ask"]
        else:
            verdict = w["allow"]
        rule = pol.get("rule_id") or ""
        return [f"   GATE   {c.get('tool_name')}: {verdict} · {w['rule']} {rule or '-'} · F={float(c.get('F') or 0):.2f} (D^I×A, ≥{float(c.get('threshold') or 0):.2f})"]
    if et == "autonomous_loop_step" and not c.get("tool_name"):
        lines = [f"   ANSWER {w['answer']}"]
        if reasoning:
            text = opener.open(ns, c.get("reasoning"))
            lines.append(f"          ↳ {_short(text, 140) if text is not None else w['sealed']}")
        return lines
    if et == "autonomous_loop_step":
        tool_args = opener.open(ns, c.get("tool_args"))
        line = f"   ACT    {c.get('tool_name')} {_args(tool_args) if tool_args is not None else w['sealed']}"
        lines = [line]
        if reasoning:
            text = opener.open(ns, c.get("reasoning"))
            lines.append(f"          ↳ {_short(text, 140) if text is not None else w['sealed']}")
        return lines
    if et == "pending_action_created":
        return [f"   WAIT   {c.get('tool_name')}: {w['waiting']} · {c.get('required_signatures') or 1} {w['signatures']} · {w['rule']} {c.get('policy_rule') or '-'} · digest {str(c.get('action_sha256'))[:12]}…"]
    if et == "pending_action_decided":
        ok = action == "approved"
        scheme = c.get("scheme") or "ed25519"
        return [f"   SIGN   {w['approved'] if ok else w['rejected']} ({scheme}, key {str(c.get('approver_public_key'))[:12]}…, digest {str(c.get('action_sha256'))[:12]}…)"]
    if et == "pending_action_executed":
        return [f"   EXEC   {c.get('tool_name')}: {w['ran_once']} → {_short(c.get('result'), 60)}"]
    if et == "small_edit_autorun":
        return [f"   EXEC   {c.get('tool_name') or ''}: {w['autorun']}"]
    if et == "governed_loop_plan":
        return [f"   PLAN   {w['plan_card']}: {action} · {_short(c, 80)}"]
    if et == "algorithm_pipeline":
        return [f"   ALGO   {w['pipeline']}: {c.get('algorithms', '?')} algorithms · {w['ok']} {c.get('ok', '?')} · {w['errors']} {c.get('errors', '?')} · {c.get('total_ms', '?')} ms"]
    if et == "governed_loop_envelope":
        return [f"   STOP   {w['envelope']}: {action}"]
    if et == "governed_loop_episode_end":
        cost = c.get("cost") or {}
        iv = c.get("intent_verification") or {}
        verify = "aligned" if iv.get("aligned") else ("n/a" if not iv.get("applicable") else "not aligned")
        usd = cost.get("cost_usd")
        return [f"── END    {w['stopped']}: {c.get('stopped_reason')} · {cost.get('calls', '?')} {w['calls']} · {w['verify']}: {verify} · MEE G={c.get('mee_g')} · "
                f"{w['skill']}: {'yes' if c.get('skill_extracted') else 'no'}" + (f" · {w['cost']} ${float(usd):.4f}" if usd is not None else "")]
    if et == "intent_loop_pillars":
        mem = c.get("memory") or {}
        return [f"   LOOP   {w['pillars']}: {w['memories']} {mem.get('memories_recalled', 0)} · {w['skills_used']} {mem.get('skills_injected', 0)}"]
    if et == "cron_job":
        return [f"   CRON   {c.get('name')}: {action}" + (f" → {c.get('stopped_reason')}" if c.get("stopped_reason") else "")]
    return []


def chain_line(db: Path, lang: str = "en") -> str:
    """One line saying whether the audit chain of this database verifies (hash links and, where present, signatures)."""
    w = WORDS.get(lang, WORDS["en"])
    try:
        from rct_control_plane.audit_chain import verify_audit_chain
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5.0)
        try:
            report = verify_audit_chain(conn)
        finally:
            conn.close()
        ok = bool(getattr(report, "ok", False))
        n = getattr(report, "chained_rows", None)
        signed = getattr(report, "signed_rows", 0) or 0
        extra = f" ({signed} signed)" if signed else ""
        reason = "" if ok else f": {getattr(report, 'reason', '')}"
        return f"   RECORD {w['chain']}: {n if n is not None else '?'} {w['chain_ok'] if ok else w['chain_bad']}{extra}{reason}"
    except Exception as exc:                                                    # noqa: BLE001 - the trace never fails because a check could not run
        return f"   RECORD {w['chain']}: could not be checked ({type(exc).__name__})"


def trace(target: Path, *, lang: str = "en", reasoning: bool = False, after_id: int = 0) -> Iterator[Tuple[int, str]]:
    """(row id, line) for every row after `after_id`."""
    db = _db_path(target)
    opener = Opener(_keys_dir(db))
    for row in read_rows(db, after_id):
        for line in render_row(row, opener, lang=lang, reasoning=reasoning):
            yield row[0], line


class Follower:
    """Prints the trace of a database while something else writes it. `start()` runs a polling thread; `stop()` prints what is left and ends it."""

    def __init__(self, target: Path, emit: Callable[[str], None] = print, *, lang: str = "en", reasoning: bool = False, interval: float = 0.5):
        self.target, self.emit, self.lang, self.reasoning, self.interval = Path(target), emit, lang, reasoning, interval
        self.last_id = 0
        import threading
        self._stop: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None

    def poll(self) -> int:
        n = 0
        for rid, line in trace(self.target, lang=self.lang, reasoning=self.reasoning, after_id=self.last_id):
            self.emit(line)
            self.last_id = max(self.last_id, rid)
            n += 1
        return n

    def start(self) -> "Follower":
        import threading
        stop = threading.Event()
        self._stop = stop

        def loop() -> None:
            while not stop.is_set():
                try:
                    self.poll()
                except Exception:                                               # noqa: BLE001 - a display problem never touches the run
                    pass
                stop.wait(self.interval)
        thread = threading.Thread(target=loop, daemon=True, name="run-trace")
        self._thread = thread
        thread.start()
        return self

    def stop(self, chain: bool = True) -> None:
        if self._stop is not None and self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=5)
        self.poll()
        if chain and _db_path(self.target).exists():
            self.emit(chain_line(_db_path(self.target), self.lang))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="a data home folder (with agentic.db) or the path of an agentic.db")
    ap.add_argument("--follow", action="store_true", help="keep printing new rows until Ctrl+C")
    ap.add_argument("--reasoning", action="store_true", help="also print the model's reasoning for each step (opened with the person's key when it is next to the database)")
    ap.add_argument("--lang", choices=sorted(WORDS), default="en")
    args = ap.parse_args(argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    db = _db_path(Path(args.target))
    if not db.exists() and not args.follow:
        print(f"no database at {db}", file=sys.stderr)
        return 2
    f = Follower(db, lang=args.lang, reasoning=args.reasoning)
    if not args.follow:
        f.stop()
        return 0
    try:
        while True:
            f.poll()
            time.sleep(1.0)
    except KeyboardInterrupt:
        f.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
