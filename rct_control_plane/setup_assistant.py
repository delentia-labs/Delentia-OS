"""
Round 106: the Setup assistant. Everything a person has to do once to trust Delentia, answered and done INSIDE the Desk instead of in a terminal and a manual.

Three pieces, none of which changes a rule by itself:

  * `checkup()`      real checks, bounded and read-only, in plain words (both languages, built here so a test can see that none lacks Thai): is the record of what the system did intact, is
                     the memory history intact, are the state logs intact, can a model answer, can anyone approve, how careful is the policy, is there room on the disk, is there a recent backup.
  * `backup_now()`   one backup of the system's own data into a `backups` folder inside the data folder. Keys stay out (backup.py), a file is never overwritten, and the time is remembered.
  * `practice_start()`  a harmless action that WAITS for approval, so a person can rehearse the whole path (see it, confirm it with their device, watch it run once, find it in the record)
                     before anything real depends on it. The action only writes a short note into the exchange folder's `projects` area.

Nothing here approves anything, creates an approver, edits the policy or reads a private key. The person's confirmation (a device, or an approver key file used in their own browser) is what turns
a waiting action into a decision, exactly as for any other waiting action.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

LAST_BACKUP_FILE = "last_backup.json"
BACKUP_STALE_DAYS = 30
DISK_WARN_BYTES = 2 * 1024 ** 3
DISK_FAIL_BYTES = 512 * 1024 ** 2
PRACTICE_TOOL = "delentia_save_exchange_file"
PRACTICE_GOAL = "Practice approval (a harmless rehearsal; nothing important happens)"
PRACTICE_ARGS = {"category": "projects", "filename": "practice-approval.txt",
                 "content_text": "This note was written by the Delentia setup practice. If you can read it, an approval you confirmed was carried out exactly once. You can delete it.\n"}


def home_dir() -> Path:
    """Where this system keeps what is its own: DELENTIA_HOME, else ~/.delentia."""
    from rct_control_plane.data_home import data_home
    return data_home() or (Path.home() / ".delentia")


def _check(check_id: str, level: str, en: str, th: str, detail_en: str = "", detail_th: str = "", fix_en: str = "", fix_th: str = "") -> Dict[str, Any]:
    return {"id": check_id, "level": level, "en": en, "th": th, "detail_en": detail_en, "detail_th": detail_th, "fix_en": fix_en, "fix_th": fix_th}


CHECK_IDS = ("audit_chain", "memory_log", "state_log", "model", "approver", "policy", "disk", "backup")


# ---------------------------------------------------------------------------------------------------------------------------------- pure judgements (each is a test)
def judge_audit(report: Optional[Dict[str, Any]], error: str = "") -> Dict[str, Any]:
    if report is None:
        return _check("audit_chain", "warn", "Could not check the record of what the system did", "ตรวจบันทึกการทำงานของระบบไม่ได้", error[:160], error[:160])
    if report.get("ok"):
        n = int(report.get("chained_rows") or 0)
        return _check("audit_chain", "ok", "The record of what the system did is intact", "บันทึกการทำงานของระบบครบถ้วน ไม่ถูกแก้",
                      f"{n} entries checked, linked one to the next" + (f", {report.get('signed_rows')} signed" if report.get("signed_rows") else ", not signed (no signing key is set)"),
                      f"ตรวจ {n} รายการ เชื่อมกันครบ" + (f" และลงนามแล้ว {report.get('signed_rows')} รายการ" if report.get("signed_rows") else " ยังไม่ได้ลงนาม (ยังไม่ได้ตั้งกุญแจลงนาม)"))
    where = report.get("first_bad_seq")
    return _check("audit_chain", "fail", "The record of what the system did does not add up", "บันทึกการทำงานของระบบไม่ตรงกัน",
                  f"first problem at entry {where}: {report.get('reason')}", f"พบปัญหาครั้งแรกที่รายการ {where}: {report.get('reason')}",
                  "Do not rely on this record. Make a backup now, then ask whoever looks after this computer to look at it.", "อย่าเชื่อถือบันทึกนี้ ทำสำรองข้อมูลตอนนี้ แล้วให้คนดูแลเครื่องตรวจ")


def judge_memory(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if report is None:
        return _check("memory_log", "warn", "Could not check the memory history", "ตรวจประวัติความจำไม่ได้")
    if report.get("ok"):
        return _check("memory_log", "ok", "The history of what it remembers is intact", "ประวัติสิ่งที่ระบบจำครบถ้วน", f"{report.get('events', 0)} events checked", f"ตรวจ {report.get('events', 0)} เหตุการณ์")
    first = (report.get("problems") or ["?"])[0]
    return _check("memory_log", "fail", "The history of what it remembers does not add up", "ประวัติสิ่งที่ระบบจำไม่ตรงกัน", str(first)[:200], str(first)[:200],
                  "Make a backup now and ask whoever looks after this computer to look at it.", "ทำสำรองข้อมูลตอนนี้ แล้วให้คนดูแลเครื่องตรวจ")


def judge_state_logs(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return _check("state_log", "ok", "No state history yet (it starts with the first request)", "ยังไม่มีประวัติสถานะ (เริ่มเมื่อมีคำขอแรก)")
    bad = [r for r in results if not r.get("ok")]
    if bad:
        return _check("state_log", "fail", "The state history does not add up", "ประวัติสถานะไม่ตรงกัน", f"{len(bad)} of {len(results)} logs", f"{len(bad)} จาก {len(results)} ชุด",
                      "Make a backup now and ask whoever looks after this computer to look at it.", "ทำสำรองข้อมูลตอนนี้ แล้วให้คนดูแลเครื่องตรวจ")
    return _check("state_log", "ok", "The state history is intact", "ประวัติสถานะครบถ้วน", f"{len(results)} log(s) checked", f"ตรวจ {len(results)} ชุด")


def judge_model(model: Dict[str, Any]) -> Dict[str, Any]:
    state, name = model.get("state"), f"{model.get('provider')}: {model.get('model')}"
    if model.get("ok"):
        return _check("model", "ok", "A model is ready to answer", "มีโมเดลพร้อมตอบ", name, name)
    why = {"server_down": ("The local model program is not running", "โปรแกรมโมเดลในเครื่องยังไม่ทำงาน", "Start Ollama, or choose another model on the Models page.", "เปิด Ollama หรือเลือกโมเดลอื่นในหน้า Models"),
           "model_missing": ("The chosen model is not installed", "ยังไม่ได้ติดตั้งโมเดลที่เลือก", "Install it, or choose another model on the Models page.", "ติดตั้งโมเดลนั้น หรือเลือกโมเดลอื่นในหน้า Models"),
           "no_key": ("The chosen model needs a key", "โมเดลที่เลือกต้องใช้คีย์", "Add the key on the Models page.", "ใส่คีย์ในหน้า Models")}.get(
        str(state), ("The model is not ready", "โมเดลยังไม่พร้อม", "Open the Models page.", "เปิดหน้า Models"))
    return _check("model", "fail", why[0], why[1], name, name, why[2], why[3])


def judge_approver(keys: int, devices: int) -> Dict[str, Any]:
    if keys + devices > 0:
        return _check("approver", "ok", "Someone can approve risky work", "มีผู้อนุมัติงานเสี่ยงได้แล้ว",
                      f"{devices} device(s), {keys} key(s)", f"อุปกรณ์ {devices} เครื่อง กุญแจ {keys} ดอก")
    return _check("approver", "fail", "Nobody can approve yet, so risky work would wait forever", "ยังไม่มีผู้อนุมัติ งานเสี่ยงจะรอไปเรื่อย ๆ",
                  fix_en="Add this computer as your approver in the Setup assistant (step 2).", fix_th="เพิ่มเครื่องนี้เป็นผู้อนุมัติในตัวช่วยตั้งค่า (ขั้นที่ 2)")


def policy_level(source: str, plan_first: bool, rules: int) -> str:
    """'standard' (the built-in starter), 'plan_first' (the owner's file with plan-first on), 'custom' (any other file of the owner's), 'floor' (no policy at all)."""
    if source == "default":
        return "standard"
    if source == "file":
        return "plan_first" if plan_first else "custom"
    return "floor"


def judge_policy(level: str) -> Dict[str, Any]:
    words = {"standard": ("Standard protection: risky work asks you first", "การป้องกันมาตรฐาน: งานเสี่ยงถามคุณก่อน"),
             "plan_first": ("Plan-first protection: risky work is shown as a plan you confirm once", "การป้องกันแบบแผนก่อน: งานเสี่ยงแสดงเป็นแผนให้ยืนยันครั้งเดียว"),
             "custom": ("Your own rules are in use", "ใช้กฎที่คุณเขียนเอง"),
             "floor": ("Only the built-in safety floor is in use (no policy)", "ใช้เฉพาะพื้นความปลอดภัยในตัว (ไม่มีนโยบาย)")}[level]
    return _check("policy", "warn" if level == "floor" else "ok", words[0], words[1], fix_en="Choose how careful it should be in the Setup assistant (step 3)." if level == "floor" else "",
                  fix_th="เลือกระดับความระวังในตัวช่วยตั้งค่า (ขั้นที่ 3)" if level == "floor" else "")


def judge_disk(free_bytes: Optional[int]) -> Dict[str, Any]:
    if free_bytes is None:
        return _check("disk", "warn", "Could not read the free space on the disk", "อ่านพื้นที่ว่างในดิสก์ไม่ได้")
    gb = free_bytes / 1024 ** 3
    if free_bytes < DISK_FAIL_BYTES:
        return _check("disk", "fail", "The disk is almost full", "ดิสก์เกือบเต็ม", f"{gb:.1f} GB free", f"ว่าง {gb:.1f} GB", "Free some space; the system writes its record to this disk.", "เคลียร์พื้นที่ ระบบเขียนบันทึกลงดิสก์นี้")
    if free_bytes < DISK_WARN_BYTES:
        return _check("disk", "warn", "The disk is getting full", "ดิสก์เริ่มเต็ม", f"{gb:.1f} GB free", f"ว่าง {gb:.1f} GB")
    return _check("disk", "ok", "There is room on the disk", "พื้นที่ดิสก์พอ", f"{gb:.1f} GB free", f"ว่าง {gb:.1f} GB")


def judge_backup(last: Optional[Dict[str, Any]], now: Optional[float] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    if not last or not isinstance(last.get("at"), (int, float)):
        return _check("backup", "warn", "No backup has been made from here yet", "ยังไม่เคยสำรองข้อมูลจากที่นี่",
                      fix_en="Press “Back up now”.", fix_th="กด “สำรองข้อมูลตอนนี้”")
    days = (now - float(last["at"])) / 86400.0
    if days > BACKUP_STALE_DAYS:
        return _check("backup", "warn", "The last backup is old", "สำรองข้อมูลครั้งล่าสุดนานแล้ว", f"{days:.0f} days ago", f"{days:.0f} วันก่อน", "Press “Back up now”.", "กด “สำรองข้อมูลตอนนี้”")
    return _check("backup", "ok", "A recent backup exists", "มีสำรองข้อมูลล่าสุด", f"{days:.0f} day(s) ago", f"{days:.0f} วันก่อน")


# ---------------------------------------------------------------------------------------------------------------------------------- the reads
def last_backup() -> Optional[Dict[str, Any]]:
    try:
        return json.loads((home_dir() / LAST_BACKUP_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def checkup(persistence: Any, now: Optional[float] = None) -> Dict[str, Any]:
    """Runs every check once. Each is bounded and read-only; one that fails to run is reported as such and never stops the others."""
    checks: List[Dict[str, Any]] = []

    try:
        from rct_control_plane import audit_chain
        with persistence._connect() as conn:
            checks.append(judge_audit(audit_chain.verify_audit_chain(conn).to_dict()))
    except Exception as exc:                                       # noqa: BLE001
        checks.append(judge_audit(None, f"{type(exc).__name__}: {exc}"))

    try:
        from rct_control_plane import memory_eventlog
        checks.append(judge_memory(memory_eventlog.MemoryEventLog(persistence).verify()))
    except Exception:                                              # noqa: BLE001
        checks.append(judge_memory(None))

    results: List[Dict[str, Any]] = []
    try:
        from rct_control_plane import agent_state_log
        for entry in agent_state_log.list_logs(persistence):
            if entry.get("error"):
                results.append({"name": entry.get("name"), "ok": False})
                continue
            try:
                base = agent_state_log.base_dir_for(persistence)
                if base is None:
                    continue
                log = agent_state_log.AgentStateLog(base / f"{entry['name']}.db", str(entry["name"]))
                try:
                    report = log.verify(persistence)
                finally:
                    log.close()
                results.append({"name": entry.get("name"), "ok": bool(report.get("ok", True))})
            except Exception:                                      # noqa: BLE001
                results.append({"name": entry.get("name"), "ok": False})
    except Exception:                                              # noqa: BLE001
        pass
    checks.append(judge_state_logs(results))

    try:
        from rct_control_plane import readiness
        facts = readiness.gather(persistence)
        evaluated = readiness.evaluate(facts)
        model = next(c for c in evaluated["checks"] if c["id"] == "model")
        checks.append(judge_model(model))
        checks.append(judge_approver(int(facts.get("approver_keys") or 0), int(facts.get("approver_devices") or 0)))
    except Exception:                                              # noqa: BLE001
        checks.append(_check("model", "warn", "Could not check the model", "ตรวจโมเดลไม่ได้"))
        checks.append(_check("approver", "warn", "Could not check who can approve", "ตรวจผู้อนุมัติไม่ได้"))

    try:
        from rct_control_plane import fdia_policy
        policy, source = fdia_policy.effective_policy()
        checks.append(judge_policy(policy_level(source, bool(getattr(policy, "plan_first", None)), len(getattr(policy, "rules", []) or []))))
    except Exception as exc:                                       # noqa: BLE001
        checks.append(_check("policy", "fail", "The policy file can not be read, so every risky action is refused", "อ่านไฟล์นโยบายไม่ได้ ระบบจึงปฏิเสธงานเสี่ยงทั้งหมด", str(exc)[:160], str(exc)[:160],
                             "Open FDIA / Policy and fix or disable the file.", "เปิด FDIA / Policy แล้วแก้หรือปิดไฟล์นั้น"))

    try:
        target = home_dir()
        target.mkdir(parents=True, exist_ok=True)
        checks.append(judge_disk(shutil.disk_usage(str(target)).free))
    except OSError:
        checks.append(judge_disk(None))
    checks.append(judge_backup(last_backup(), now))

    order = {c: i for i, c in enumerate(CHECK_IDS)}
    checks.sort(key=lambda c: order.get(c["id"], 99))
    worst = "fail" if any(c["level"] == "fail" for c in checks) else "warn" if any(c["level"] == "warn" for c in checks) else "ok"
    return {"overall": worst, "checks": checks, "at": time.time() if now is None else now}


# ---------------------------------------------------------------------------------------------------------------------------------- the two actions
def backup_now() -> Dict[str, Any]:
    """One backup into <data folder>/backups/, named by the time, never over another file. Private keys stay out. Remembers the time."""
    from rct_control_plane import backup
    folder = home_dir() / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = folder / f"delentia-{stamp}.zip"
    n = 1
    while target.exists():
        n += 1
        target = folder / f"delentia-{stamp}-{n}.zip"
    done = backup.create_backup(str(target), include_keys=False)
    backup.verify_backup(str(target))
    marker = {"at": time.time(), "path": str(target), "files": done["files"], "bytes": done["bytes"]}
    (home_dir() / LAST_BACKUP_FILE).write_text(json.dumps(marker), encoding="utf-8")
    return {**marker, "keys_note": done.get("keys_note")}


_LAST_CODE_WINDOW = [0.0]
CODE_WINDOW_MIN_SECONDS = 30.0


def open_code_window(persistence: Any, *, popen: Any = None, platform: Optional[str] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """Opens a window on the person's screen that shows the one-time code for the FIRST approval device, so the Desk can offer a button instead of a terminal and a command.
    The code is printed by the ordinary `approvals first-device-code --hold` command in that window: it never travels through this call's answer. Only while nobody can approve yet; at most
    once every 30 seconds (every window mints a new code); on a system without a window to open the answer says what to type instead."""
    import subprocess
    import sys
    from rct_control_plane import first_device
    now = time.time() if now is None else now
    if not first_device.nobody_can_approve(persistence):
        return {"opened": False, "reason": "someone_can_approve", "how": "Someone can already approve here, so no code is needed. Add the next device and let an approver vouch for it."}
    if now - _LAST_CODE_WINDOW[0] < CODE_WINDOW_MIN_SECONDS:
        return {"opened": False, "reason": "too_soon", "how": "A window was opened a moment ago. Look for it on your screen (it may be behind this one)."}
    command = [sys.executable, "-m", "rct_control_plane.cli", "approvals", "first-device-code", "--hold", "--db", str(getattr(persistence, "db_path", ""))]
    how = "Open a terminal on this computer and type:  delentia approvals first-device-code"
    if (platform or sys.platform) != "win32":
        return {"opened": False, "reason": "no_window", "how": how}
    try:
        (popen or subprocess.Popen)(command, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0), close_fds=True)
    except OSError as exc:
        return {"opened": False, "reason": "failed", "how": how, "detail": str(exc)[:120]}
    _LAST_CODE_WINDOW[0] = now
    return {"opened": True, "how": "A small window opened with your code. Type the code here, then press Add this device."}


def practice_start(persistence: Any, owner: str) -> Dict[str, Any]:
    """Puts one harmless action in front of the person: it waits for an approval like any real one. If one is already waiting for this person it is returned instead of making a second."""
    from rct_control_plane.approvals import PendingActionStore
    store = PendingActionStore(persistence)
    for action in store.list(status="PENDING", limit=200):
        if action.namespace == owner and action.goal == PRACTICE_GOAL:
            return {"approval_id": action.approval_id, "action_sha256": action.action_sha256, "reused": True}
    from rct_control_plane import mcp_server
    record = store.create(namespace=owner, goal=PRACTICE_GOAL, tool_name=PRACTICE_TOOL, tool_args=dict(PRACTICE_ARGS),
                          reason="a practice action: confirm it to see how approving works", workspace=str(Path(mcp_server.REPO_ROOT).resolve()))
    return {"approval_id": record.approval_id, "action_sha256": record.action_sha256, "reused": False}
