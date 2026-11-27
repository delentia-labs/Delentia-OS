"""RCT-7 stage R-1: 80 work requests with their intent type and stated constraints (research/RCT7_R1_CRITERIA_R116.md).

Written by the assistant (Claude) on 2026-11-25 before any measurement. Labels are the assistant's, not independent. The split (60 development, 20 held
out) is fixed by a hash of each id; the held-out ids and the digest of their content are pinned below so a later edit shows.

Constraint kinds: language, format, max_words, max_chars, item_count, required_artifact, forbidden_effect, preserve_interface, budget, deadline.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def G(gid: str, lang: str, intent: str, goal: str, *constraints: str) -> Dict[str, Any]:
    return {"id": gid, "lang": lang, "intent": intent, "goal": goal, "constraints": sorted(set(constraints))}


GOALS: List[Dict[str, Any]] = [
    # DEBUG (fix something that is broken)
    G("g01", "en", "DEBUG", "Fix the failing tests in the ledgercalc package. Preserve all public function signatures and do not modify the tests.", "preserve_interface", "forbidden_effect"),
    G("g02", "en", "DEBUG", "The invoice total is off by one cent when a discount applies. Find the bug in pricing.py and fix it.", ),
    G("g03", "en", "DEBUG", "Repair the crash in export.py that happens when the customer list is empty. Leave config.yaml alone.", "forbidden_effect"),
    G("g04", "en", "DEBUG", "Debug why the nightly job stops after the first record and correct it without changing the job's public API.", "preserve_interface"),
    G("g05", "th", "DEBUG", "แก้บั๊กใน pricing.py ที่ทำให้ยอดรวมผิด ห้ามแก้ไฟล์เทสต์", "forbidden_effect"),
    G("g06", "th", "DEBUG", "ช่วยหาสาเหตุที่สคริปต์ backup.py ล้มเหลวเมื่อโฟลเดอร์ว่าง แล้วแก้ให้ถูกต้อง", ),
    G("g07", "en", "DEBUG", "The login page throws a 500 error after the last update. Fix it and keep the function names unchanged.", "preserve_interface"),
    G("g08", "th", "DEBUG", "แก้ข้อผิดพลาดใน report.py ให้เทสต์ผ่านทั้งหมด โดยไม่เปลี่ยนชื่อฟังก์ชันสาธารณะ", "preserve_interface"),
    # REFACTOR
    G("g09", "en", "REFACTOR", "Refactor utils.py into smaller functions without changing its public interface.", "preserve_interface"),
    G("g10", "en", "REFACTOR", "Clean up the duplicated code in the three report modules; do not touch the tests folder.", "forbidden_effect"),
    G("g11", "th", "REFACTOR", "ปรับโครงสร้างโค้ดใน billing.py ให้อ่านง่ายขึ้น โดยห้ามเปลี่ยน signature ของฟังก์ชัน", "preserve_interface"),
    G("g12", "en", "REFACTOR", "Rename the internal helper _calc to _compute_total across the module and keep behaviour identical.", ),
    G("g13", "en", "REFACTOR", "Restructure the settings loader so it reads one file instead of three.", ),
    # BUILD_APP (create something new)
    G("g14", "en", "BUILD_APP", "Create a small command-line tool that converts CSV invoices to JSON and save it as tools/csv2json.py.", "required_artifact"),
    G("g15", "en", "BUILD_APP", "Build a simple web page that lists the open orders from orders.json.", ),
    G("g16", "th", "BUILD_APP", "สร้างสคริปต์ใหม่สำหรับส่งออกรายงานยอดขายรายเดือน บันทึกเป็น scripts/monthly_report.py", "required_artifact"),
    G("g17", "en", "BUILD_APP", "Write a new module that validates Thai national ID numbers, with a budget of no more than $2 of model calls.", "budget"),
    G("g18", "th", "BUILD_APP", "สร้างหน้าเว็บสำหรับกรอกข้อมูลลูกค้าใหม่ ภายในวันศุกร์นี้", "deadline"),
    # DOCUMENT
    G("g19", "en", "DOCUMENT", "Write a README for the ledgercalc package in English, at most 300 words.", "language", "max_words"),
    G("g20", "en", "DOCUMENT", "Document every public function in api.py with a docstring; do not change any code.", "forbidden_effect"),
    G("g21", "th", "DOCUMENT", "เขียนคู่มือการติดตั้งเป็นภาษาไทย บันทึกเป็นไฟล์ docs/install_th.md", "language", "required_artifact"),
    G("g22", "en", "DOCUMENT", "Update the changelog with the three fixes from this week as a bulleted list of exactly three items.", "item_count"),
    G("g23", "th", "DOCUMENT", "สรุปการเปลี่ยนแปลงของเวอร์ชันนี้เป็นเอกสารภาษาอังกฤษ ไม่เกิน 200 คำ", "language", "max_words"),
    # QUERY (read, search, answer; no change wanted)
    G("g24", "en", "QUERY", "What is the quarterly total in report.txt?", ),
    G("g25", "en", "QUERY", "Which functions in pricing.py call validate_rate?", ),
    G("g26", "th", "QUERY", "ยอดรวมของไตรมาสนี้ในไฟล์ report.txt คือเท่าไร", ),
    G("g27", "en", "QUERY", "Summarise the meeting notes in notes/2026-11.md in Thai, in at most 120 words.", "language", "max_words"),
    G("g28", "en", "QUERY", "List the five largest invoices in invoices.csv as JSON.", "format", "item_count"),
    G("g29", "th", "QUERY", "ช่วยอ่าน contract.md แล้วบอกว่าวันหมดสัญญาคือวันไหน", ),
    G("g30", "en", "QUERY", "How many orders were placed in October according to orders.json?", ),
    G("g31", "en", "QUERY", "Search the repository for any place that still uses the old API key name and tell me the files.", ),
    G("g32", "th", "QUERY", "มีไฟล์ไหนบ้างที่ยังเรียกใช้ฟังก์ชัน old_total", ),
    G("g33", "en", "QUERY", "Explain in one paragraph what the refund_amount function does.", ),
    # TEST
    G("g34", "en", "TEST", "Write unit tests for the refund_amount function in tests/test_refunds_extra.py; do not change refunds.py.", "required_artifact", "forbidden_effect"),
    G("g35", "en", "TEST", "Run the visible test suite and tell me how many tests fail.", ),
    G("g36", "th", "TEST", "เขียนเทสต์เพิ่มสำหรับฟังก์ชัน line_total ให้ครอบคลุมกรณีส่วนลดเป็นศูนย์", ),
    G("g37", "en", "TEST", "Add tests that check the export handles an empty list; keep the existing tests untouched.", "forbidden_effect"),
    # DEPLOY
    G("g38", "en", "DEPLOY", "Deploy the website to the staging server.", ),
    G("g39", "en", "DEPLOY", "Release version 2.4.6 to PyPI after the tests pass, before 5 pm today.", "deadline"),
    G("g40", "th", "DEPLOY", "นำเวอร์ชันใหม่ขึ้นเซิร์ฟเวอร์ทดสอบ", ),
    G("g41", "en", "DEPLOY", "Roll out the new configuration to production without restarting the database.", "forbidden_effect"),
    # OPTIMIZE
    G("g42", "en", "OPTIMIZE", "Speed up the report generation; it currently takes 40 seconds.", ),
    G("g43", "en", "OPTIMIZE", "Reduce the memory use of the import job without changing its output format.", "preserve_interface"),
    G("g44", "th", "OPTIMIZE", "ทำให้หน้ารายการสินค้าโหลดเร็วขึ้น", ),
    G("g45", "en", "OPTIMIZE", "Make the search endpoint faster while keeping the response schema the same.", "preserve_interface"),
    # TRANSFORM
    G("g46", "en", "TRANSFORM", "Convert customers.csv to JSON and save it as customers.json.", "format", "required_artifact"),
    G("g47", "th", "TRANSFORM", "แปลงไฟล์ orders.xlsx เป็น CSV", "format"),
    G("g48", "en", "TRANSFORM", "Translate the user guide into Thai and save it as docs/guide_th.md.", "language", "required_artifact"),
    G("g49", "en", "TRANSFORM", "Merge the three monthly CSV files into one file sorted by date.", ),
    # STRATEGY
    G("g50", "en", "STRATEGY", "Plan the migration of our data store from SQLite to Postgres in five steps.", "item_count"),
    G("g51", "th", "STRATEGY", "วางแผนการเปิดตัวผลิตภัณฑ์ใหม่ภายในงบ 50,000 บาท", "budget"),
    G("g52", "en", "STRATEGY", "Propose a roadmap for the next quarter, at most 10 bullet points.", "item_count"),
    G("g53", "en", "STRATEGY", "Outline how we should move the team to weekly releases by the end of the month.", "deadline"),
    # ANALYZE_RISK
    G("g54", "en", "ANALYZE_RISK", "Assess the security risks of exposing the API on a public host.", ),
    G("g55", "th", "ANALYZE_RISK", "ประเมินความเสี่ยงของการย้ายฐานข้อมูลไปคลาวด์", ),
    G("g56", "en", "ANALYZE_RISK", "Review the deployment script for anything that could delete data, and report it as a table.", "format"),
    G("g57", "en", "ANALYZE_RISK", "Evaluate the risks of upgrading the payment library; do not change any file.", "forbidden_effect"),
    # mixed and harder phrasings
    G("g58", "en", "DEBUG", "Something is wrong with the totals again, can you sort it out? Don't touch the tests.", "forbidden_effect"),
    G("g59", "en", "QUERY", "Is the refund rule in refunds.py the same as the one described in policy.md?", ),
    G("g60", "th", "DEBUG", "ระบบคำนวณภาษีผิดอีกแล้ว ช่วยดูและแก้ให้หน่อย อย่าแก้ไฟล์ config", "forbidden_effect"),
    G("g61", "en", "BUILD_APP", "Add a new endpoint /v1/refunds that returns the refund history, keeping all existing endpoints unchanged.", "preserve_interface"),
    G("g62", "en", "DOCUMENT", "Write release notes in Thai for version 2.4.5 as a markdown file named RELEASE_TH.md.", "language", "required_artifact"),
    G("g63", "th", "QUERY", "ช่วยสรุปไฟล์ notes.md เป็นภาษาอังกฤษไม่เกิน 5 ข้อ", "language", "item_count"),
    G("g64", "en", "REFACTOR", "Split the 900-line main.py into modules; the command-line flags must stay the same.", "preserve_interface"),
    G("g65", "en", "TEST", "Make the flaky test in test_export.py reliable without changing export.py.", "forbidden_effect"),
    G("g66", "th", "TRANSFORM", "แปลงรายงานเป็น JSON แล้วบันทึกเป็น report.json", "format", "required_artifact"),
    G("g67", "en", "OPTIMIZE", "Cut the cloud bill of the nightly job; keep it under $30 a month.", "budget"),
    G("g68", "en", "QUERY", "Give me the three most common error messages in app.log, as a numbered list.", "item_count", "format"),
    G("g69", "th", "DOCUMENT", "เขียนคำอธิบายฟังก์ชัน refund_amount เป็นภาษาไทยสั้นๆ ไม่เกิน 50 คำ", "language", "max_words"),
    G("g70", "en", "DEBUG", "Correct the off-by-one error in the pagination code and verify with the visible tests.", ),
    G("g71", "en", "DEPLOY", "Publish the documentation site; do not change the DNS settings.", "forbidden_effect"),
    G("g72", "th", "STRATEGY", "ช่วยวางแผนการทดสอบระบบกับผู้ใช้ภายนอก 5 คน ภายในสองสัปดาห์", "deadline"),
    G("g73", "en", "ANALYZE_RISK", "What could go wrong if we turn off the approval step for small edits?", ),
    G("g74", "en", "BUILD_APP", "Create a Thai-language landing page and save it as site/index_th.html.", "language", "required_artifact"),
    G("g75", "en", "QUERY", "Does the test suite cover the case where the discount is larger than the price?", ),
    G("g76", "th", "REFACTOR", "จัดระเบียบโฟลเดอร์ scripts ใหม่ โดยห้ามเปลี่ยนชื่อคำสั่งที่ผู้ใช้เรียก", "preserve_interface"),
    G("g77", "en", "TRANSFORM", "Normalise all dates in orders.csv to ISO 8601 and write the result to orders_iso.csv.", "required_artifact"),
    G("g78", "en", "DEBUG", "The test suite fails on Python 3.10 only. Fix it so it passes on 3.10, 3.11 and 3.12 without changing the tests.", "forbidden_effect"),
    G("g79", "th", "TEST", "รันเทสต์ทั้งหมดแล้วรายงานผลเป็นตาราง", "format"),
    G("g80", "en", "DOCUMENT", "Write a one-page summary of the PL1 results for the website, no more than 400 words, in English.", "language", "max_words"),
]


def split(goal_id: str) -> str:
    """Fixed before any measurement: a goal is held out when the first byte of the SHA-256 of its id is below 64 (about a quarter)."""
    return "holdout" if hashlib.sha256(goal_id.encode("utf-8")).digest()[0] < 64 else "dev"


def digest(goals: List[Dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(goals, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def dev() -> List[Dict[str, Any]]:
    return [g for g in GOALS if split(g["id"]) == "dev"]


def holdout() -> List[Dict[str, Any]]:
    return [g for g in GOALS if split(g["id"]) == "holdout"]


# Pinned before any measurement: the 20 held-out requests and their content. A test fails if either changes.
HOLDOUT_IDS = ["g01", "g03", "g11", "g14", "g21", "g26", "g28", "g33", "g36", "g38", "g40", "g45", "g48", "g53", "g57", "g58", "g62", "g71", "g72", "g79"]
HOLDOUT_DIGEST = "66b4dd03bf8b7f527c709225ce582f991ab88cfe6480b288b0b53639308d6174"
