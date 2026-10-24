"""Labelled cases for the round-97 RCT-7 rules (criteria: research/rct7_round97_criteria.md).

Written BEFORE the rules they test, by the person who then wrote the rules: a pass is a regression guard, not independent evidence. A case added or changed after a failure is
marked ADDED_AFTER at the bottom of its list (none yet).
"""
from __future__ import annotations

from typing import List, Tuple

_WORDS = ("system report value check result file plan step agent user policy window record error stable signal review option change small large quick careful "
          "memory budget answer detail source table model gate cycle order light north river stone paper garden market ticket bridge engine").split()


def words(n: int) -> str:
    """n plain words, no digits, no list markers."""
    return " ".join(_WORDS[i % len(_WORDS)] for i in range(n)) + "."


def bullets(n: int, numbered: bool = False) -> str:
    return "\n".join((f"{i + 1}. item {_WORDS[i]}" if numbered else f"- item {_WORDS[i]}") for i in range(n))


# ----------------------------------------------------------------------------------------------------------------------------- W5: (goal, answer, must_stop)
W5: List[Tuple[str, str, bool]] = [
    # --- must pass (the answer keeps what the goal asked) -------------------------------------------------------------------
    ("Summarize this in at most 50 words", words(30), False),
    ("Explain the gate in under 40 words", words(39), False),
    ("Describe the result in no more than 25 words", words(25), False),
    ("List 5 risks of the plan", "Here are the risks:\n" + bullets(5), False),
    ("Give me 3 bullet points about the budget", bullets(3), False),
    ("สรุปเป็น 3 ข้อ", "1. ข้อแรกคือเรื่องงบ\n2. ข้อสองคือเรื่องเวลา\n3. ข้อสามคือเรื่องคน", False),
    ("List up to 4 options", bullets(3), False),
    ("Answer in under 200 characters", "The tests pass and nothing else changed.", False),
    ("ตอบไม่เกิน 100 ตัวอักษร", "ผ่านทั้งหมด ไม่พบข้อผิดพลาด", False),
    ("Summarize the file", words(400), False),                                              # no requirement stated: never checked
    ("Summarize in 3 sentences", words(120), False),                                        # sentences are not a checked kind
    ("List the 5 largest files", "Largest files:\n" + bullets(5, numbered=True), False),    # header line plus 5 items
    ("Give 2 examples", "For instance a table and a chart.", False),                        # prose with no list structure: no verdict
    ("What is 17 x 23? answer in under 10 words", "391", False),
    ("Write 3 bullet points in Thai", "- หนึ่ง\n- สอง\n- สาม", False),
    ("Explain in at most 30 words", words(10), False),
    ("Name 2 colours", "red\nblue", False),                                                 # two lines but no markers: no verdict
    ("I have 5 files and 3 folders. Summarize them.", words(80), False),                    # numbers that are not requirements
    ("Reply in at least 3 words", words(8), False),                                         # a lower bound is not a checked kind
    ("List 2 items", "- item a\n- item b", False),
    # --- must stop (the answer breaks what the goal asked) ------------------------------------------------------------------
    ("Summarize this in at most 20 words", words(45), True),
    ("Explain the gate in under 30 words", words(60), True),
    ("Describe the result in no more than 10 words", words(25), True),
    ("Answer in 15 words or fewer", words(40), True),
    ("List 5 risks of the plan", "Risks:\n" + bullets(3), True),
    ("List 3 items", bullets(6), True),
    ("Give me 4 bullet points", bullets(2), True),
    ("สรุปเป็น 3 ข้อ", "1. ข้อแรก\n2. ข้อสอง\n3. ข้อสาม\n4. ข้อสี่\n5. ข้อห้า", True),
    ("สรุป 2 ข้อ", "1. ข้อแรกคือเรื่องงบประมาณ\n2. ข้อสองคือเรื่องเวลา\n3. ข้อสามคือเรื่องคน", True),
    ("List up to 3 options", bullets(6), True),
    ("List at most 2 items", bullets(4, numbered=True), True),
    ("Answer in under 100 characters", words(60), True),
    ("Keep it under 50 characters", "The tests pass and nothing else changed anywhere in the repository today.", True),
    ("ตอบไม่เกิน 50 ตัวอักษร", "ผลการทดสอบทั้งหมดผ่านแล้ว ไม่พบข้อผิดพลาดในระบบ และเวลาที่ใช้ลดลงจากเดิมประมาณครึ่งหนึ่ง จึงแนะนำให้ใช้ค่านี้ต่อไป", True),
    ("Write exactly 5 bullet points", bullets(3), True),
    ("Summarize in a maximum of 12 words", words(30), True),
    ("List 4 reasons", "Reasons:\n" + bullets(5, numbered=True), True),
    ("Respond in at most 8 words", words(20), True),
    ("Give 3 examples as a list", bullets(5), True),
    ("Limit the answer to 25 words", words(70), True),
]

# ----------------------------------------------------------------------------------------------------------------------------- W3: (goal, expected parts)
# Expected parts are compared lower-cased, without leading ordinal words ("first", "then", "finally", "step 2:") and without trailing punctuation.
W3_SPLIT: List[Tuple[str, List[str]]] = [
    ("1. Read README.md\n2. Summarize it\n3. Save as s.md", ["read readme.md", "summarize it", "save as s.md"]),
    ("First read a.txt, then summarize it, finally save to b.md", ["read a.txt", "summarize it", "save to b.md"]),
    ("- fetch the page\n- extract the title\n- write it down", ["fetch the page", "extract the title", "write it down"]),
    ("ก่อนอื่นอ่านไฟล์ a.txt แล้ว สรุป แล้ว บันทึกเป็น b.md", ["อ่านไฟล์ a.txt", "สรุป", "บันทึกเป็น b.md"]),
    ("(1) list files (2) count them (3) report", ["list files", "count them", "report"]),
    ("Step 1: install deps. Step 2: run tests. Step 3: report.", ["install deps", "run tests", "report"]),
    ("1) back up the db 2) migrate 3) verify", ["back up the db", "migrate", "verify"]),
    ("1. Do A\n2. Do B", ["do a", "do b"]),
    ("* one\n* two", ["one", "two"]),
    ("First, open the file. Second, fix the typo. Third, save it.", ["open the file", "fix the typo", "save it"]),
    ("1. อ่านไฟล์\n2. สรุป\n3. ส่งอีเมล", ["อ่านไฟล์", "สรุป", "ส่งอีเมล"]),
    ("ขั้นที่ 1 อ่านไฟล์ ขั้นที่ 2 สรุป", ["อ่านไฟล์", "สรุป"]),
    ("Read a.txt and then summarize it", ["read a.txt", "summarize it"]),
    ("Open the page, then copy the table, then paste it in notes.md", ["open the page", "copy the table", "paste it in notes.md"]),
    ("  1. trim\n  2. sort\n  3. dedupe", ["trim", "sort", "dedupe"]),
    ("• check logs\n• restart service", ["check logs", "restart service"]),
    ("Step 1 - export. Step 2 - compress.", ["export", "compress"]),
    ("1. Plan\n2. Build\n3. Test\n4. Ship", ["plan", "build", "test", "ship"]),
    ("First list the files, then pick the biggest, then print its size", ["list the files", "pick the biggest", "print its size"]),
    ("อ่านข้อมูล จากนั้น สรุป จากนั้น แปลเป็นอังกฤษ", ["อ่านข้อมูล", "สรุป", "แปลเป็นอังกฤษ"]),
]
W3_ONE: List[str] = [
    "Summarize the history of Rome in 3 sentences",
    "Read a.txt and b.txt",
    "Compare Python and Go",
    "List 5 items",
    "Fix the bug in line 1. 2 tests fail.",
    "Write a poem about spring",
    "ตอบเป็นภาษาไทย 17 x 23 เท่าไร",
    "First of all, what is a monad?",
    "Then what happened to the project?",
    "Step by step, explain how TLS works",
    "งานเสร็จแล้ว ช่วยสรุปให้หน่อย",
]

# ----------------------------------------------------------------------------------------------------------------------------- W2: (goal, workspace files, has conversation, expected unknowns)
# Each expected unknown is (kind, value): ("missing_file", name) or ("dangling_reference", "").
W2: List[Tuple[str, List[str], bool, List[Tuple[str, str]]]] = [
    # --- real unknowns -----------------------------------------------------------------------------------------------------
    ("Read config.yaml and tell me the port", [], False, [("missing_file", "config.yaml")]),
    ("Summarize docs/guide.md in three bullets", ["README.md"], False, [("missing_file", "docs/guide.md")]),
    ("Edit settings.json to set debug true", ["app/main.py"], False, [("missing_file", "settings.json")]),
    ("Open the file notes.txt", [], False, [("missing_file", "notes.txt")]),
    ("แก้ไฟล์ server.py ให้ใช้พอร์ต 9000", ["app.py"], False, [("missing_file", "server.py")]),
    ("อ่านไฟล์ report.csv แล้วสรุป", [], False, [("missing_file", "report.csv")]),
    ("Update the version in package.json", [], False, [("missing_file", "package.json")]),
    ("Summarise README.rst", ["README.md"], False, [("missing_file", "README.rst")]),
    ("Fix it", [], False, [("dangling_reference", "")]),
    ("Do that again", [], False, [("dangling_reference", "")]),
    ("แก้อันนั้น", [], False, [("dangling_reference", "")]),
    ("ทำอีกครั้ง", [], False, [("dangling_reference", "")]),
    ("Look at data/input.csv and plot it", ["data/other.csv"], False, [("missing_file", "data/input.csv")]),
    ("Refactor utils.py", ["src/helpers.py"], False, [("missing_file", "utils.py")]),
    ("Check the logs in app.log", [], False, [("missing_file", "app.log")]),
    ("ตรวจ config.toml", [], False, [("missing_file", "config.toml")]),
    ("Review the diff in changes.patch", [], False, [("missing_file", "changes.patch")]),
    ("Translate spec.docx to Thai", [], False, [("missing_file", "spec.docx")]),
    ("Edit main.rs", ["Cargo.toml"], False, [("missing_file", "main.rs")]),
    ("Open schema.sql", ["migrations/001.sql"], False, [("missing_file", "schema.sql")]),
    # --- look similar, are fine ----------------------------------------------------------------------------------------------
    ("Read config.yaml", ["app/config.yaml"], False, []),                       # the name exists in a sub-folder
    ("Create report.md summarising the logs", [], False, []),                   # a file to be created
    ("Save the result as out.json", [], False, []),
    ("Write a file named plan.txt", [], False, []),
    ("Edit notes.txt", ["notes.txt"], False, []),
    ("Fix it", [], True, []),                                                   # there is a conversation to refer to
    ("Do that again", [], True, []),
    ("What is a config.yaml file?", [], False, []),                             # a question about the concept
    ("Explain how Dockerfile.dev differs from compose.yaml in general", [], False, []),
    ("Rename old.txt to new.txt", ["old.txt"], False, []),
    ("Copy a.txt to b.txt", ["a.txt"], False, []),
    ("Convert data.csv to data.json", ["data.csv"], False, []),
    ("Do not modify config.yaml, just read app.py", ["app.py", "config.yaml"], False, []),
    ("Read https://example.com/index.html", [], False, []),                     # an address, not a workspace file
    ("Summarize the report", [], False, []),                                    # names no file
    ("อ่านไฟล์ readme.md", ["README.md"], False, []),                           # case differs
    ("Update setup.py then run tests", ["packaging/setup.py"], False, []),
    ("Look at the package.json of the project", ["frontend/package.json"], False, []),
    ("Fix the bug in main.py", ["main.py"], False, []),
    ("Fix the bug", [], False, []),                                             # not a bare reference
]
ADDED_AFTER: List[str] = []

# Added after the first run, from probing the rules by hand (the first run passed everything; these look for brittleness). They are part of the measured sets from now on.
W2 += [
    ("Look at v1.2.3 release notes", [], False, []),                       # a version number is not a file
    ("Fix the typo in the e.g. section of the docs", [], False, []),       # an abbreviation is not a file
    ("Review the diff, i.e. changes.patch", ["changes.patch"], False, []),
    ("Open the page example.com/index.html and read it", [], False, []),   # a web address without a scheme
    ("Check that the output is saved to results.json", [], False, []),     # saved, not read
    ("Edit the function in utils.py then save it as utils2.py", ["utils.py"], False, []),
]
W3_ONE += ["If the tests fail then stop and report", "If it is raining, then bring an umbrella"]
ADDED_AFTER += [g for g, *_ in W2[-6:]] + W3_ONE[-2:]
