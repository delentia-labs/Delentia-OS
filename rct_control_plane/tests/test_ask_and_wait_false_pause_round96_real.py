"""P6 of the ask-and-wait design (B2-0): how often the rule layer stops when it should not, and fails to stop when it should.

PASS RULE, written in the design before any run (DELENTIA_ROUND92_B2_0..., section 7):
  - 40 tasks that must NOT stop (Thai and English): at most 2 false stops;
  - 20 tasks that MUST stop: at least 17 stopped.
Honest limit: the 60 cases below were written by the same author as the rules, after reading them (a model was not asked to write them), so they are a regression guard and a rough rate on
the author's idea of normal and abnormal, not independent evidence. The cases include deliberately awkward ones (Thai text with quoted code, English with a Thai name, goals that mention
both languages but ask for neither). The check runs the pure rule functions on (goal, answer, steps, workspace); the loop wiring has its own tests."""
import json

from rct_control_plane import mismatch_rules as mr

TH_REPORT_A = "ผลการทดสอบทั้งหมดผ่านแล้ว ไม่พบข้อผิดพลาดในระบบ และเวลาที่ใช้ลดลงจากเดิมประมาณครึ่งหนึ่ง จึงแนะนำให้ใช้ค่านี้ต่อไป"
TH_REPORT_B = "รายงานประจำเดือนนี้ยอดขายรวมเพิ่มขึ้นร้อยละสิบสองเมื่อเทียบกับเดือนก่อน โดยกลุ่มลูกค้าองค์กรเติบโตเร็วที่สุด ส่วนต้นทุนการขนส่งลดลงเล็กน้อย"
TH_WITH_CODE = "ผมแก้ปัญหาแล้วโดยรันคำสั่งด้านล่างและทุกอย่างทำงานปกติ\n```bash\nnpm install --save-dev typescript && npm run build -- --watch false\n```\nหลังจากนั้นระบบสร้างไฟล์ dist/index.js ให้เรียบร้อยตามที่ต้องการ"
TH_TERMS = "ระบบ FDIA gate ปฏิเสธการเขียนไฟล์ เพราะค่า F ต่ำกว่า threshold ที่ตั้งไว้ จึงต้องรอการอนุมัติด้วยลายเซ็น Ed25519 จากเจ้าของระบบก่อนจึงจะทำต่อได้"
TH_LINKS = "ดูรายละเอียดเพิ่มเติมได้ที่ https://example.com/docs/guide และไฟล์ README.md ซึ่งอธิบายขั้นตอนติดตั้งทั้งหมดไว้อย่างชัดเจนสำหรับผู้เริ่มต้นใช้งาน"
EN_REPORT_A = "All of the tests passed and no errors were found in the system, and the time taken fell by about half, so this setting is recommended."
EN_REPORT_B = "Monthly sales rose twelve percent compared with last month, led by corporate customers, while shipping costs fell slightly across all regions."
EN_WITH_THAI_NAME = "The capital city is Bangkok (กรุงเทพมหานคร), which is also the largest city, and it hosts most of the national government offices and ministries."
EN_CODE = "I fixed it by running the command below and everything works now.\n```bash\nnpm install\n```\nThe build output is in the dist folder as expected."


def step(path, **outcome):
    return {"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": path, "content_text": "x"}, "tool_result": dict(outcome)}


def build_cases(root):
    (root / "report.md").write_text("x", encoding="utf-8")
    (root / "out").mkdir()
    (root / "out" / "result.txt").write_text("x", encoding="utf-8")
    ok = []        # (goal, answer, steps)  -> must NOT stop
    for answer in (TH_REPORT_A, TH_REPORT_B, TH_WITH_CODE, TH_TERMS, TH_LINKS):
        ok.append(("สรุปผลให้หน่อยเป็นภาษาไทย", answer, []))
    for answer in ("391", "391 ครับ", "ใช่", "ok"):
        ok.append(("ตอบเป็นภาษาไทย 17 x 23 เท่าไร", answer, []))
    for answer in (EN_REPORT_A, EN_REPORT_B, EN_CODE):
        ok.append(("Please answer in English: summarize the results", answer, []))
    ok.append(("Answer in English. Who is the prime minister?", "Anutin Charnvirakul.", []))
    ok.append(("Write the capital city in English", EN_WITH_THAI_NAME, []))
    ok.append(("answer in English", "Bangkok, which the Thai call กรุงเทพ.", []))
    ok.append(("Respond in English: is the system healthy?", "yes", []))
    ok.append(("Respond in English: what changed?", EN_REPORT_B + " " + EN_REPORT_A, []))
    for answer in ('{"total": 12500, "currency": "THB"}', '```json\n{"ok": true}\n```', '[1, 2, 3]', '{"ชื่อ": "สมชาย", "ยอด": 100}'):
        ok.append(("Return the result as JSON", answer, []))
    ok.append(("save it as report.md", "I saved the summary.", []))
    ok.append(("บันทึกเป็น report.md", "บันทึกเรียบร้อยแล้ว", []))
    ok.append(("save the result to out/result.txt", "done", []))
    ok.append(("บันทึกลง out/result.txt", "เสร็จแล้ว", []))
    ok.append(("do not modify config.yaml", "I changed nothing.", []))
    ok.append(("ห้ามแก้ไฟล์ config.yaml", "ไม่ได้แก้ไฟล์นี้", [step("notes.md", ok=True)]))
    ok.append(("do not modify config.yaml, just report", "report", [step("config.yaml", blocked=True)]))
    ok.append(("do not edit settings.ini", "waiting for approval", [step("settings.ini", pending_approval=True)]))
    for goal in ("Compare Thai and English tourism numbers", "Translate between Thai and English", "เปรียบเทียบยอดขายภาษาไทยและภาษาอังกฤษของเว็บไซต์", "What does JSON stand for?",
                 "อธิบายว่า JSON คืออะไร", "สรุปข่าววันนี้", "Explain how to save a file in Python", "How do I make a file read-only?"):
        ok.append((goal, EN_REPORT_A, []))
    ok.append(("สรุปเป็นภาษาไทย", "| รายการ | ยอด |\n|---|---|\n| ค่าขนส่ง | 1,200 |\n| ค่าสินค้า | 8,400 |\nรวมทั้งหมดเก้าพันหกร้อยบาทตามใบเสนอราคาที่ได้รับ", []))
    ok.append(("Answer in English", "| item | total |\n|---|---|\n| shipping | 1,200 |\n| goods | 8,400 |\nThe total is 9,600 baht according to the quote.", []))
    ok.append(("Return as JSON", '```json\n[{"a": 1}, {"a": 2}]\n```', []))
    assert len(ok) == 40, len(ok)

    stop = []      # must stop
    for answer in (EN_REPORT_A, EN_REPORT_B, EN_CODE, "The test results are all positive and the system is healthy and ready for use in production.", "I have summarized the monthly report and everything looks fine this time around."):
        stop.append(("สรุปผลให้หน่อยเป็นภาษาไทย", answer, []))
    for answer in (TH_REPORT_A, TH_REPORT_B, TH_TERMS):
        stop.append(("Please answer in English: summarize the results", answer, []))
    for answer in ("The total is 12,500 baht in the quote.", "Sure! Here is the result: total 12500", "ยอดรวมคือ 12,500 บาท"):
        stop.append(("Return the result as JSON", answer, []))
    for answer in ('{"total": 1,', "{'total': 1}", 'Here is the JSON: {"a": 1}'):
        stop.append(("ตอบเป็น JSON", answer, []))
    stop.append(("save it as summary.md", "I saved the summary.", []))
    stop.append(("บันทึกเป็น missing/summary.md", "บันทึกแล้ว", []))
    stop.append(("save the result to out/absent.txt", "done", []))
    stop.append(("do not modify config.yaml", "I updated the configuration.", [step("config.yaml", ok=True)]))
    stop.append(("ห้ามแก้ไฟล์ settings.ini", "แก้ไขเรียบร้อย", [step("deploy/settings.ini", written=True)]))
    stop.append(("never overwrite data.csv", "done", [step("data.csv", ok=True)]))
    assert len(stop) == 20, len(stop)
    return ok, stop


def stops(case, root):
    goal, answer, steps = case
    return bool(mr.check(mr.derive_requirements(goal), answer, steps, root))


def test_P6_false_pause_rate_meets_the_rule_written_before_the_run(tmp_path):
    ok, must = build_cases(tmp_path)
    false_stops = [c[:2] for c in ok if stops(c, tmp_path)]
    missed = [c[:2] for c in must if not stops(c, tmp_path)]
    report = {"should_not_stop": len(ok), "false_stops": len(false_stops), "should_stop": len(must), "stopped": len(must) - len(missed),
              "false_stop_cases": [[g, a[:60]] for g, a in false_stops], "missed_cases": [[g, a[:60]] for g, a in missed]}
    print(json.dumps(report, ensure_ascii=False))
    assert len(false_stops) <= 2, report
    assert len(must) - len(missed) >= 17, report
