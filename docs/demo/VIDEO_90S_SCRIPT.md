# 90-second evidence video — script and shot list

Purpose: show a stranger, in 90 seconds, something they can then reproduce themselves with one command. It uses the model-free demo, so what is shown is the gate, the signature wait and the
audit chain, **not** a language model's ability — say so on screen. Nothing in it is edited to hide a failure; record in one take, terminal only, 120×30, dark theme, font ≥ 18 pt.

## Setup (before recording)
```
pip install delentia-os        # in a fresh virtual environment; show the version line
```

## Shots

| Time | What is on screen | Spoken line (EN) | Spoken line (TH) |
|---|---|---|---|
| 0:00–0:08 | Title card: "Delentia — a governed agent runtime. Experimental." | "This is an experimental runtime that puts a gate and a signature in front of an agent's actions." | "นี่คือรันไทม์เชิงทดลองที่วางประตูและลายเซ็นไว้หน้าการกระทำของเอเจนต์" |
| 0:08–0:20 | `delentia demo run compare --scripted` finishing in ~5 s, five checks passing | "No model is used here: a fixed program stands in for it. The tools, the gate and the audit log are real." | "ไม่มีโมเดลในที่นี้: โปรแกรมที่กำหนดไว้ทำหน้าที่แทน เครื่องมือ ประตู และ audit log เป็นของจริง" |
| 0:20–0:40 | `delentia demo run edit --scripted` stops with "waiting for a signature"; `ls` shows the result file does **not** exist yet | "The write is held. Nothing was written." | "การเขียนถูกพักไว้ ยังไม่มีการเขียนอะไร" |
| 0:40–0:55 | `delentia demo approve <id> --scripted`; the file now exists | "A signed approval releases exactly that one action." | "ลายเซ็นปล่อยการกระทำนั้นเพียงหนึ่งอย่าง" |
| 0:55–1:10 | `delentia audit-chain verify` → `chain: OK … signed`; then change one character in the database copy and verify again → fails and names the row | "Every step is in a hash chain. Change one character and the check fails." | "ทุกขั้นอยู่ใน hash chain แก้หนึ่งตัวอักษรแล้วตรวจจะไม่ผ่าน" |
| 1:10–1:22 | A table card: measured / not yet. Measured: 7,820 tests on CI, gate properties, the injection measurement with a scripted hijacked model. Not yet: a capable model's results, a public host, an independent witness, any outside user | "What is measured, and what is not yet. We have no results yet with a capable model." | "สิ่งที่วัดแล้ว และสิ่งที่ยังไม่มี: ยังไม่มีผลกับโมเดลที่เก่ง" |
| 1:22–1:30 | `pip install delentia-os` and the one command, the repository address | "Run it yourself: one command, five seconds." | "ลองเองได้: คำสั่งเดียว ห้าวินาที" |

## Rules for the recording
* Show the real version number (`pip show delentia-os`) and the real date; do not splice takes.
* Do not show any key, token or personal path; use a throw-away user folder.
* Say "experimental" in the first ten seconds and show the "not yet" card; never say "secure", "certified", "tamper-proof" or "production-ready".
* Put the exact commands in the video description so they can be copied.
