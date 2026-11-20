# 90-second evidence video — script and shot list

Purpose: show a stranger, in about 90 seconds, something they can then reproduce themselves with a few commands. It uses the model-free demo, so what is shown is the gate, the signature wait and the
audit chain, **not** a language model's ability — the video says so on screen.

## How it is made (since 2026-11-20)

The video is **recorded by a script, not by hand**: `scripts/video_demo/record_demo_video.py`. It makes a short work folder at a drive root, creates a fresh virtual environment, installs the
published package into it, opens one console window, types the commands below at human speed (the typing is simulated; **every command is executed for real**) and records only that window
with ffmpeg. It writes English and Thai subtitles (`.srt`), burns each into an `.mp4`, a contact sheet, and a hygiene report that scans the transcript for the user name, `C:\Users`,
AppData, key-like strings and e-mail addresses. The environment it runs in has every `DELENTIA`, `OPENROUTER`, `*KEY`, `*TOKEN` and `*SECRET` variable removed.

```
py -3.13 scripts\video_demo\record_demo_video.py --package delentia-os==<version on PyPI> --tests-line "<the line from the latest green CI run on main>"
```
`--tests-line` is required on purpose: the "measured" card must quote the test count of an actual CI run, never a number remembered from an older round. Record only a version that is on PyPI,
and read the contact sheet and `hygiene_report.txt` before anything is posted.

## Shots (what the script plays)

| Shot | What is on screen | Subtitle (EN) | Subtitle (TH) |
|---|---|---|---|
| title card | "Delentia OS <version> — a governed agent runtime — EXPERIMENTAL"; "No language model is used in this recording" | An experimental runtime that puts a gate and a signature in front of an agent's actions. No language model is used here. | รันไทม์เชิงทดลองที่วางประตูและลายเซ็นไว้หน้าการกระทำของเอเจนต์ ในคลิปนี้ไม่ได้ใช้โมเดลภาษา |
| version | `pip show delentia-os \| Select-String Version`, then `delentia demo init --lang en --dir demo` | The version published on PyPI; the demo folder is made in a throw-away location. | รุ่นที่เผยแพร่บน PyPI โฟลเดอร์เดโมสร้างในที่ชั่วคราว |
| compare | `delentia demo run compare --scripted --dir demo` (last 16 lines), five checks | A fixed program stands in for the model. The tools, the gate and the audit log are real; the five checks come from outside the agent. | โปรแกรมที่กำหนดไว้ทำหน้าที่แทนโมเดล เครื่องมือ ประตู และ audit log เป็นของจริง การตรวจ 5 ข้อมาจากภายนอกเอเจนต์ |
| edit (before) | `Select-String "Total price"` on the quote file | The quote file says what it says today. | ไฟล์ใบเสนอราคาเป็นอย่างที่เห็นตอนนี้ |
| edit (waits) | `delentia demo run edit --scripted`, stops at "waiting for a signature"; the same `Select-String` shows the file is unchanged | The write is held: nothing has been written. | การเขียนถูกพักไว้ ยังไม่มีอะไรถูกเขียน |
| approve | `delentia demo approve <id> --scripted` (the id is read from the previous output); the line now shows the new total | A signed approval releases exactly that one action. | ลายเซ็นปล่อยการกระทำนั้นเพียงหนึ่งอย่าง |
| chain ok | `delentia demo status` (first 9 lines): chain intact, rows signed | Every step is in a hash chain: all rows present and signed. | ทุกขั้นอยู่ใน hash chain: ทุกแถวอยู่ครบและมีลายเซ็น |
| tamper | on a **throw-away copy** (`demo_copy`), `alter_one_character.py` changes one character in one stored row of the audit table, then `delentia demo status --dir demo_copy` | Change ONE character in one stored row, then check again: it fails. | แก้หนึ่งตัวอักษรในหนึ่งแถว แล้วตรวจอีกครั้ง: ไม่ผ่าน |
| measured / not yet | a card: the CI test count (from `--tests-line`); "0 of 23 side effects ran with the taint rule on" (a scripted, hijacked model); the cost meter agreed with the provider's own figure within 10%. NOT YET: results with a strong model on long tasks; any outside user; an independent witness; RCT-7 and FDIA D^I have no measured benefit yet; the Windows installer is not code-signed | What is measured, and what is not yet. There are no results with a strong model yet. | สิ่งที่วัดแล้ว และสิ่งที่ยังไม่มี: ยังไม่มีผลกับโมเดลที่เก่ง |
| try it | `pip install delentia-os`, `delentia demo init --lang en`, `delentia demo run compare --scripted`, `delentia demo run edit --scripted`, the repository address | Run it yourself: four commands, no model and no API key. | ลองเองได้: สี่คำสั่ง ไม่ต้องมีโมเดลหรือคีย์ |

### Corrections to the earlier version of this script
* It said the tamper check "names the row". The real `demo status` output says only that the chain is **not** intact; it does not print which row. The video shows exactly what the command prints.
* It quoted 7,820 tests. The number now comes from the `--tests-line` argument (the latest green CI run on main); the repository's own checkpoint is in `docs/testing/TESTING_CANONICAL.md`.
* It said `delentia demo init`; the English recording needs `--lang en` (the default is Thai).
* It set a terminal of 120x30 at 18 pt by hand; the recorder sets a 100x28 console with an in-process 22 pt Consolas font, for 1280x720 output.

## Rules for the recording
* Show the real version number (`pip show delentia-os`) and the real date; the video is one take, nothing is spliced.
* No key, token or personal path appears; the work folder is at a drive root and the environment is cleaned (the hygiene report must be empty before posting).
* Say "experimental" in the first ten seconds and show the "not yet" card; never say "secure", "certified", "tamper-proof" or "production-ready".
* Put the exact commands in the video description so they can be copied.
* The owner chooses: subtitles only, or his own voice over the same video. A synthetic voice is not used.
