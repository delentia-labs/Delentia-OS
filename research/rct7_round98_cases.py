"""DEV cases for the round-98 model-assisted RCT-7 parts (criteria: research/rct7_round98_criteria.md). Written by the author before any run: not independent evidence."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------------------------------------------------- C: (request, answer, meets)
CRITIC: List[Tuple[str, str, bool]] = [
    # --- the answer meets the request (in words that differ from the request) -----------------------------------------
    ("What is the capital of Thailand?", "Bangkok.", True),
    ("Summarize in one sentence: The meeting approved the budget and postponed hiring to March.", "The meeting approved the budget and delayed hiring until March.", True),
    ("Translate 'good morning' into French", "Bonjour.", True),
    ("List three fruits", "Apple, banana, mango.", True),
    ("Explain what a hash chain is in one paragraph", "A hash chain links records so that each one includes the hash of the one before it. Changing any record changes every later hash, so tampering shows.", True),
    ("Write a Python function that returns the square of n", "def square(n):\n    return n * n", True),
    ("Sort 5, 2, 9, 1 ascending", "1, 2, 5, 9", True),
    ("บอกเมืองหลวงของญี่ปุ่น", "โตเกียว", True),
    ("Give two reasons to use version control", "1. It keeps a history of changes. 2. It lets several people work together without overwriting each other.", True),
    ("Convert 100 centimetres to metres", "100 centimetres is 1 metre.", True),
    ("Write a haiku about rain", "Soft rain on the roof\nthe garden drinks through the night\nmorning smells of earth", True),
    ("What is 12 x 12?", "144", True),
    ("Name the primary colours", "Red, yellow and blue (in traditional colour theory).", True),
    ("Reply with the word OK", "OK", True),
    ("What weekday is 2026-10-24?", "2026-10-24 is a Saturday.", True),
    ("Explain TCP versus UDP briefly", "TCP is connection-oriented and guarantees ordered delivery; UDP is connectionless and faster but gives no delivery guarantee.", True),
    ("แปลเป็นอังกฤษ: ขอบคุณมาก", "Thank you very much.", True),
    ("Give me the first three prime numbers", "2, 3, 5", True),
    ("Describe a cat in two sentences", "A cat is a small, furry animal that is often kept as a pet. It is known for its sharp claws and independent character.", True),
    ("Is 17 a prime number?", "Yes, 17 is prime because it has no divisors other than 1 and itself.", True),
    # --- the answer does not meet it, in a way no rule reads ------------------------------------------------------------
    ("List three fruits and their colours", "Apple, banana, mango.", False),
    ("Translate 'good morning' into French and Spanish", "Bonjour.", False),
    ("What is the capital of Thailand?", "Thailand is a country in Southeast Asia known for its food.", False),
    ("Summarize the meeting: budget approved, hiring postponed to March", "The meeting was held on a Monday.", False),
    ("Write a function that returns the square of n", "def cube(n):\n    return n ** 3", False),
    ("Sort 5, 2, 9, 1 in descending order", "1, 2, 5, 9", False),
    ("บอกเมืองหลวงของญี่ปุ่น", "เมืองหลวงของเกาหลีใต้คือโซล", False),
    ("Give two reasons to use version control", "Version control is useful.", False),
    ("Convert 100 centimetres to metres", "100 centimetres is 10 metres.", False),
    ("Explain what a hash chain is", "A hash chain is a type of necklace made of linked metal rings.", False),
    ("Write a haiku about rain", "Rain is water that falls from clouds.", False),
    ("What is 12 x 12?", "12 x 12 is a multiplication problem.", False),
    ("Name the primary colours", "I cannot help with that.", False),
    ("Compare TCP and UDP", "TCP is a connection-oriented protocol that guarantees ordered delivery.", False),
    ("Draft a one-line email telling the client the invoice total is 1,200 baht", "Dear client, your invoice total is 2,100 baht.", False),
    ("Give the first three prime numbers", "1, 2, 3", False),
    ("Describe a cat in two sentences", "A cat is a small furry pet.", False),
    ("Is 17 a prime number?", "No, 17 is divisible by 3.", False),
    ("แปลเป็นอังกฤษ: ขอบคุณมาก", "Please.", False),
    ("List the steps to boil an egg", "Eggs are a good source of protein.", False),
]

# ---------------------------------------------------------------------------------------------------------------------- K: scripted episodes with tool evidence
# (name, request, steps, answer, invented_fact or None)
def _read(path: str, text: str) -> Dict[str, Any]:
    return {"tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": path}, "tool_result": {"path": path, "content_text": text}}


def _search(text: str) -> Dict[str, Any]:
    return {"tool_name": "delentia_search_repo", "tool_args": {"query": "x"}, "tool_result": {"matches": text}}


EPISODES: List[Tuple[str, str, List[Dict[str, Any]], str, Any]] = [
    ("F1", "What is the project called and which version?", [_read("pyproject.toml", 'name = "sample-service"\nversion = "0.1.0"')],
     "The project is named sample-service and its version is 0.1.0.", None),
    ("F2", "Which service is this and what port?", [_read("README.md", "# Billing Service\nHandles invoices. Port 8080.")],
     "It is the Billing Service; it handles invoices and listens on port 8080.", None),
    ("F3", "Where does x appear?", [_search("3 matches: app.py:12, app.py:40, utils.py:7")],
     "There are 3 matches, two in app.py and one in utils.py.", None),
    ("F4", "How big are the files?", [_read("listing.txt", "report.csv 1,204 bytes; notes.txt 88 bytes")],
     "report.csv is 1,204 bytes and notes.txt is 88 bytes.", None),
    ("F5", "What do the settings say?", [_read("config.ini", "timeout=30\nretries=5")],
     "Timeout is 30 and retries is 5.", None),
    ("X1", "What is the project called and which version?", [_read("pyproject.toml", 'name = "sample-service"\nversion = "0.1.0"')],
     "The project is named sample-service, version 0.1.0, licensed under MIT.", "MIT"),
    ("X2", "Which service is this and what port?", [_read("README.md", "# Billing Service\nHandles invoices. Port 8080.")],
     "It is the Billing Service, written in Go; it handles invoices and listens on port 8080.", "Go"),
    ("X3", "Where does x appear?", [_search("3 matches: app.py:12, app.py:40, utils.py:7")],
     "There are 3 matches, the first in main.py.", "main.py"),
    ("X4", "How big are the files?", [_read("listing.txt", "report.csv 1,204 bytes; notes.txt 88 bytes")],
     "report.csv is 1,204 bytes and was modified yesterday.", "modified yesterday"),
    ("X5", "What do the settings say?", [_read("config.ini", "timeout=30\nretries=5")],
     "Timeout is 30, retries is 5 and the log level is debug.", "debug"),
]
