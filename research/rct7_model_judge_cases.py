"""DEV cases for the model-as-judge probe (criteria: research/rct7_model_judge_criteria.md). Written by the probe's author before any run: not independent evidence."""
from __future__ import annotations

from typing import List, Tuple

# (request, must_ask)
CASES: List[Tuple[str, bool]] = [
    # --- something the request does not say (should ask) -------------------------------------------------------------
    ("Send the report to the client", True),
    ("Update the pricing", True),
    ("Book the meeting for next week", True),
    ("Fix the bug in the checkout", True),
    ("Translate the document", True),
    ("สรุปประชุมเมื่อวาน", True),
    ("ลบไฟล์เก่าออกให้หน่อย", True),
    ("Compare the two vendors", True),
    ("Make it faster", True),
    ("Deploy the new version", True),
    ("Email Somchai about the invoice", True),
    ("Change the password", True),
    ("ทำรายงานยอดขายให้ลูกค้า", True),
    ("Merge the branches", True),
    ("Archive last year's tickets", True),
    ("Rewrite the intro to sound better", True),
    ("Pay the supplier", True),
    ("Check if the numbers add up", True),
    ("Schedule the backup", True),
    ("ส่งไฟล์ให้ทีม", True),
    # --- clear enough to act on (should not ask) ---------------------------------------------------------------------
    ("What is 17 x 23?", False),
    ("Read README.md and list its section headings", False),
    ("Write a haiku about autumn", False),
    ("แปลประโยค 'Good morning' เป็นภาษาไทย", False),
    ("List the three primary colours", False),
    ("Summarize this text in two sentences: The committee met on Monday and approved the budget. It then discussed the hiring plan, which was postponed to March because two candidates withdrew.", False),
    ("Convert 72 degrees Fahrenheit to Celsius", False),
    ("Create a file named notes.txt containing the word hello", False),
    ("อ่านไฟล์ pyproject.toml แล้วบอกชื่อโปรเจกต์", False),
    ("Explain what a hash chain is in one paragraph", False),
    ("Sort these numbers ascending: 5, 2, 9, 1", False),
    ("Write a Python function that returns the factorial of n", False),
    ("What is the capital of Thailand?", False),
    ("Count the words in: 'the quick brown fox'", False),
    ("Reply with exactly the word OK", False),
    ("Give 3 reasons to use version control", False),
    ("แสดงรายการ 3 ข้อดีของการออกกำลังกาย", False),
    ("Write a SQL query selecting all rows from table users", False),
    ("Translate 'thank you' into French", False),
    ("Add 2 and 3 and tell me the result", False),
]
PROMPT_VERSION = 1
SYSTEM = (
    "You review a request BEFORE any work starts. Decide whether it contains everything needed to act on it, using only the request itself. "
    "If something essential is missing or ambiguous (which item, which person, which file, which date, what exactly to change), the request is NOT clear. "
    "A request that can be answered or done from its own words and common knowledge is clear. Never guess the missing part. "
    "Reply with JSON only: {\"clear\": true or false, \"unknowns\": [short questions to ask the person]}. If clear, unknowns is []."
)
