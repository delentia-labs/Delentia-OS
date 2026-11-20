"""Record the 90-second evidence video (docs/demo/VIDEO_90S_SCRIPT.md) the same way every time. Windows only. Free: no model, no key, no network except pip.

What it does
  1. makes a short work folder at the drive root (no user name in any path that is shown), a clean virtual environment and installs `--package` from PyPI;
  2. opens ONE new console window titled DelentiaDemoRec and plays the shots in it (typing is simulated, every command really runs);
  3. records only that window with ffmpeg (gdigrab, window title) and scales it to 1280x720;
  4. writes English and Thai subtitles from the real time each shot started, and burns them into two extra files;
  5. scans the console transcript and the subtitles for a user name, a user path, key-looking text and e-mail addresses and writes hygiene_report.txt.

Rules it keeps: one take, no splicing; the child process gets an environment without any DELENTIA_*, OPENROUTER_* or *KEY/TOKEN/SECRET variable;
it refuses to start without --tests-line (the sentence about the public test count, copied from the latest green CI run: nothing is typed from memory);
it never touches ~/.delentia or ~/delentia-demo; it deletes nothing (a new folder per run).

Do not use the computer while it records (about two minutes): the capture takes what is on screen inside the window's rectangle, so a window dragged over it would be recorded.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent
TITLE = "DelentiaDemoRec"

# key -> (English subtitle, Thai subtitle). A subtitle stays on screen from its shot's start until the next shot starts.
CAPTIONS: Dict[str, Tuple[str, str]] = {
    "title": ("An experimental runtime that puts a gate and a signature in front of an agent's actions. No language model is used here.",
              "รันไทม์เชิงทดลองที่วางประตูและลายเซ็นไว้หน้าการกระทำของเอเจนต์ ในคลิปนี้ไม่ได้ใช้โมเดลภาษา"),
    "version": ("This is the version published on PyPI. The demo folder is made in a throw-away location.",
                "นี่คือรุ่นที่เผยแพร่บน PyPI และโฟลเดอร์เดโมถูกสร้างในที่ชั่วคราว"),
    "compare": ("A fixed program stands in for the model. The tools, the gate and the audit log are real; the five checks come from outside the agent.",
                "โปรแกรมที่กำหนดไว้ทำหน้าที่แทนโมเดล เครื่องมือ ประตู และ audit log เป็นของจริง การตรวจ 5 ข้อมาจากภายนอกเอเจนต์"),
    "edit_before": ("The quote file says what it says today.", "ไฟล์ใบเสนอราคาเป็นอย่างที่เห็นตอนนี้"),
    "edit_waits": ("The agent asks to change the file. The write is held: nothing has been written.",
                   "เอเจนต์ขอแก้ไฟล์ การเขียนถูกพักไว้ ยังไม่มีอะไรถูกเขียน"),
    "approve": ("A signed approval releases exactly that one action.", "ลายเซ็นปล่อยการกระทำนั้นเพียงหนึ่งอย่าง"),
    "chain_ok": ("Every step is in a hash chain: all rows present and signed.", "ทุกขั้นอยู่ใน hash chain: ทุกแถวอยู่ครบและมีลายเซ็น"),
    "tamper": ("On a throw-away copy, change ONE character in one stored row, then check again: it fails.",
               "บนสำเนาชั่วคราว แก้หนึ่งตัวอักษรในหนึ่งแถว แล้วตรวจอีกครั้ง: ไม่ผ่าน"),
    "card_measured": ("What is measured, and what is not yet. There are no results with a strong model yet.",
                      "สิ่งที่วัดแล้ว และสิ่งที่ยังไม่มี: ยังไม่มีผลกับโมเดลที่เก่ง"),
    "try_it": ("Run it yourself: four commands, no model and no API key.", "ลองเองได้: สี่คำสั่ง ไม่ต้องมีโมเดลหรือคีย์"),
    "end": ("", ""),
}


def die(msg: str) -> None:
    print("ERROR:", msg, file=sys.stderr)
    raise SystemExit(2)


def clean_env() -> Dict[str, str]:
    bad = re.compile(r"(DELENTIA|OPENROUTER|ANTHROPIC|OPENAI|HF_|HUGGING|GITHUB|GH_|NPM_|PYPI|AWS|AZURE).*|.*(KEY|TOKEN|SECRET|PASSWORD)", re.I)
    return {k: v for k, v in os.environ.items() if not bad.match(k)}


def srt_time(t: float) -> str:
    t = max(t, 0.0)
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path: Path, events: List[Tuple[float, str]], t0: float, total: float, lang: int) -> None:
    lines: List[str] = []
    n = 0
    for i, (ts, key) in enumerate(events):
        if key not in CAPTIONS or not CAPTIONS[key][lang]:
            continue
        end = events[i + 1][0] if i + 1 < len(events) else t0 + total
        n += 1
        lines += [str(n), f"{srt_time(ts - t0)} --> {srt_time(end - t0 - 0.05)}", CAPTIONS[key][lang], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def hygiene(work: Path, extra_files: List[Path]) -> List[str]:
    problems: List[str] = []
    user = os.environ.get("USERNAME", "").lower()
    patterns = [(r"c:\\users\\", "a user-profile path"), (r"appdata", "AppData"), (r"sk-[a-z0-9_-]{10,}", "a key-looking string"),
                (r"-----begin [a-z ]*private key", "private key text"), (r"[\w.+-]+@[\w-]+\.[\w.-]+", "an e-mail address"),
                (r"openrouter_api_key|bearer\s+[a-z0-9._-]{10,}", "a credential word")]
    if user and len(user) > 2:
        patterns.append((re.escape(user), "the Windows user name"))
    for f in [work / "transcript.txt"] + extra_files:
        if not f.exists():
            problems.append(f"{f.name}: missing (cannot scan)")
            continue
        text = f.read_text(encoding="utf-8", errors="replace").lower()
        if f.name == "transcript.txt":              # PowerShell's header (user, machine, process) is written to the file but is never on the screen: scan what is shown
            stars = "*" * 22                         # the header is fenced by two lines of stars (Start-Transcript output itself is silenced)
            first = text.find(stars)
            second = text.find(stars, first + len(stars)) if first >= 0 else -1
            if second >= 0:
                text = text[second + len(stars):]
            end = text.rfind("**********************\r\nwindows powershell transcript end")
            if end < 0:
                end = text.rfind("windows powershell transcript end")
            if end >= 0:
                text = text[:end]
        for pat, what in patterns:
            for m in re.finditer(pat, text):
                problems.append(f"{f.name}: {what}: ...{text[max(0, m.start() - 20): m.end() + 20]!r}...")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", default="delentia-os", help="what to pip install, e.g. delentia-os==2.4.5 (the video shows the version it installs)")
    ap.add_argument("--tests-line", required=True, help='exact sentence for the "measured" card, copied from the latest green CI run, e.g. "9,069 tests passed on CI (run 40989051697, main dc0b2df)"')
    ap.add_argument("--drive-root", default=os.environ.get("SystemDrive", "C:") + "\\", help="where the short work folder is made")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--dry-run", action="store_true", help="only print what would happen")
    a = ap.parse_args()
    if sys.platform != "win32":
        die("Windows only (gdigrab + a console window)")
    ffmpeg = shutil.which("ffmpeg") or die("ffmpeg not found on PATH")
    stamp = dt.datetime.now().strftime("%m%d-%H%M%S")
    root = Path(a.drive_root) / f"dvid-{stamp}"
    if root.exists():
        die(f"{root} exists")
    print(f"work folder: {root}\npackage: {a.package}\ntests line: {a.tests_line}")
    if a.dry_run:
        return
    root.mkdir(parents=True)
    # 1. clean venv + install
    py = shutil.which("py")
    cmd = [py, "-3.13", "-m", "venv", str(root / "venv")] if py else [sys.executable, "-m", "venv", str(root / "venv")]
    subprocess.run(cmd, check=True, env=clean_env())
    vpy = root / "venv" / "Scripts" / "python.exe"
    subprocess.run([str(vpy), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", a.package], check=True, env=clean_env())
    ver = subprocess.run([str(vpy), "-m", "pip", "show", "delentia-os"], capture_output=True, text=True, env=clean_env()).stdout
    version = (re.search(r"^Version:\s*(\S+)", ver, re.M) or die("delentia-os not installed")).group(1)
    shutil.copy(HERE / "alter_one_character.py", root / "alter_one_character.py")
    play = (HERE / "playback_template.ps1").read_text(encoding="utf-8")
    for k, v in {"@@ROOT@@": str(root), "@@VENV_SCRIPTS@@": str(root / "venv" / "Scripts"), "@@VERSION@@": version,
                 "@@TESTS_LINE@@": a.tests_line.replace("'", "''")}.items():
        play = play.replace(k, v)
    pfile = root / "playback.ps1"
    pfile.write_text(play, encoding="utf-8-sig")
    # 2. open the console window
    win = subprocess.Popen(["conhost.exe", "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(pfile)], env=clean_env(), creationflags=subprocess.CREATE_NEW_CONSOLE)
    t_wait = time.time()
    while not (root / "ready.flag").exists():
        if time.time() - t_wait > 60:
            win.kill()
            die("the console window did not get ready in 60 s")
        time.sleep(0.2)
    time.sleep(1.0)
    # 3. record only that window
    raw = root / "raw.mp4"
    vf = "scale=1280:624:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:0:color=black,format=yuv420p"
    ff = subprocess.Popen([ffmpeg, "-y", "-hide_banner", "-loglevel", "warning", "-f", "gdigrab", "-framerate", str(a.fps), "-draw_mouse", "0", "-i", f"title={TITLE}",
                           "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(raw)], stdin=subprocess.PIPE, stderr=subprocess.PIPE, env=clean_env())
    t_ff = time.time()
    time.sleep(2.5)
    if ff.poll() is not None:
        win.kill()
        die("ffmpeg stopped at once: " + (ff.stderr.read().decode("utf-8", "replace") if ff.stderr else ""))
    (root / "go.flag").write_text("go")
    t_go_wall = time.time()
    t_wait = time.time()
    while not (root / "done.flag").exists():
        if time.time() - t_wait > 360:
            ff.kill()
            win.kill()
            die("playback took longer than 6 minutes")
        time.sleep(0.5)
    time.sleep(1.0)
    try:                                          # gdigrab may already have stopped by itself when the window closed
        ff.stdin.write(b"q")
        ff.stdin.flush()
    except OSError:
        pass
    try:
        ff.stdin.close()
    except OSError:
        pass
    try:
        ff.wait(timeout=60)
    except subprocess.TimeoutExpired:
        ff.kill()
    total = time.time() - t_ff
    try:
        win.wait(timeout=10)
    except subprocess.TimeoutExpired:
        win.terminate()
    # 4. subtitles. The video starts when ffmpeg started (t_ff); events carry wall-clock seconds.
    events: List[Tuple[float, str]] = []
    for line in (root / "events.txt").read_text(encoding="utf-8").splitlines():
        ts, key = line.split(" ", 1)
        events.append((float(ts), key.strip()))
    go_ts = [ts for ts, k in events if k == "go"][0]
    events = [(ts, k) for ts, k in events if k != "go"]
    t0 = go_ts - (t_go_wall - t_ff)               # video time zero, in the events' clock
    for lang, name in ((0, "en"), (1, "th")):
        write_srt(root / f"captions_{name}.srt", events, t0, total, lang)
        sub = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "warning", "-i", "raw.mp4", "-vf",
                              f"subtitles=captions_{name}.srt:force_style='FontName=Leelawadee UI,FontSize=20,Outline=2,Shadow=0,Alignment=2,MarginV=16'",
                              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", f"delentia_demo_{name}.mp4"], cwd=root, capture_output=True, text=True)
        if sub.returncode != 0:
            print("subtitle burn failed for", name, sub.stderr[-400:])
    # 5. contact sheet for a human to look at before posting
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(root / "delentia_demo_en.mp4"), "-vf", "fps=1/8,scale=640:-1,tile=3x4", "-frames:v", "1", str(root / "contact_sheet.jpg")], check=False)
    problems = hygiene(root, [root / "captions_en.srt", root / "captions_th.srt"])
    report = [f"package: {a.package}", f"installed version: {version}", f"recorded length (s): {total:.1f}", f"hygiene problems: {len(problems)}"] + problems
    (root / "hygiene_report.txt").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"\nfiles in {root}: delentia_demo_en.mp4, delentia_demo_th.mp4, raw.mp4 (no subtitles), contact_sheet.jpg, transcript.txt, captions_*.srt, hygiene_report.txt")
    print("Look at contact_sheet.jpg and play the video once before posting. Nothing is uploaded by this script.")


if __name__ == "__main__":
    main()
