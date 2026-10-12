"""
Round 72: labelled sentences for the user model (rct_control_plane/user_model.py), written BEFORE the detector. DEV (24) is what the detector's rules were tuned on; HOLDOUT (40) is frozen by SHA-256 and measured once.
Each item: (text, expected) where expected is None (the sentence states no standing preference: it is a task, a question, a one-off instruction) or (facet, value).
The labels are the author's; the sentences are written by the author too, so this measures whether the rules do what they were meant to do on phrasings they were not tuned on, not how real people write.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional, Tuple

Item = Tuple[str, Optional[Tuple[str, str]]]

DEV: List[Item] = [
    ("Please always answer in Thai.", ("language", "th")),
    ("ตอบเป็นภาษาไทยเสมอนะ", ("language", "th")),
    ("From now on reply in English.", ("language", "en")),
    ("Keep your answers short.", ("answer_length", "short")),
    ("ตอบสั้นๆ พอ", ("answer_length", "short")),
    ("I prefer detailed explanations.", ("answer_length", "detailed")),
    ("ขอคำอธิบายละเอียดทุกครั้ง", ("answer_length", "detailed")),
    ("Use bullet points when you answer.", ("format", "bullets")),
    ("ตอบเป็นข้อๆ ให้หน่อย", ("format", "bullets")),
    ("My timezone is Asia/Bangkok.", ("timezone", "Asia/Bangkok")),
    ("เขตเวลาของฉันคือ UTC+7", ("timezone", "UTC+7")),
    ("Always give me a table for comparisons.", ("format", "table")),
    ("Write a short story about a cat.", None),
    ("Translate this sentence to Thai: good morning.", None),
    ("Summarise the report in three bullet points.", None),
    ("What is the timezone of Tokyo?", None),
    ("แปลเป็นภาษาอังกฤษให้หน่อย", None),
    ("Read the file report.txt and tell me the total.", None),
    ("Is a detailed budget required for the grant?", None),
    ("ช่วยสรุปเป็นข้อๆ ให้หน่อย", None),
    ("Reply to the customer in English and apologise.", None),
    ("Make the table in the spreadsheet wider.", None),
    ("ตอนนี้เวลากี่โมงที่โตเกียว", None),
    ("The answer in the document is short.", None),
]

HOLDOUT: List[Item] = [
    ("Please respond in Thai from now on.", ("language", "th")),
    ("ต่อไปนี้ช่วยตอบเป็นภาษาไทยนะ", ("language", "th")),
    ("By default, answer me in English.", ("language", "en")),
    ("I want your replies to be brief.", ("answer_length", "short")),
    ("ตอบให้กระชับทุกครั้งนะ", ("answer_length", "short")),
    ("Please keep responses concise.", ("answer_length", "short")),
    ("Always explain things in detail.", ("answer_length", "detailed")),
    ("ฉันชอบคำตอบที่ละเอียด", ("answer_length", "detailed")),
    ("Give me your answers as bullet points, please.", ("format", "bullets")),
    ("ขอให้ตอบเป็นข้อๆ ทุกครั้ง", ("format", "bullets")),
    ("When you compare things, put them in a table.", ("format", "table")),
    ("ตอบเป็นตารางเสมอเวลาเปรียบเทียบ", ("format", "table")),
    ("My time zone is Europe/London.", ("timezone", "Europe/London")),
    ("เขตเวลาของผมคือ Asia/Bangkok", ("timezone", "Asia/Bangkok")),
    ("I'm in UTC-5, so schedule things for that time zone.", ("timezone", "UTC-5")),
    ("Please reply in Japanese from now on.", ("language", "ja")),
    ("ฉันอยากให้ตอบสั้นๆ เสมอ", ("answer_length", "short")),
    ("Please do not use tables in your answers; bullets are better.", ("format", "bullets")),
    ("I prefer short answers.", ("answer_length", "short")),
    ("ตอบเป็นภาษาอังกฤษนะ ตั้งแต่นี้ไป", ("language", "en")),
    ("Translate the contract into Thai.", None),
    ("Write a detailed report on last quarter's sales.", None),
    ("ช่วยเขียนอีเมลสั้นๆ ถึงลูกค้า", None),
    ("What time zone is Berlin in?", None),
    ("Put the figures from the file into a table.", None),
    ("สรุปเป็นข้อๆ ว่าไฟล์นี้พูดถึงอะไร", None),
    ("Is the answer to question 3 short or long?", None),
    ("Answer the customer's email in English.", None),
    ("My name is Somchai and I live in Chiang Mai.", None),
    ("Explain how bullet points work in Markdown.", None),
    ("เขียนบทความภาษาไทยเกี่ยวกับกาแฟ", None),
    ("Give me a short summary of this paragraph: the meeting moved to Friday.", None),
    ("The deadline is 17:00 UTC+7 on Friday.", None),
    ("Can you reply in English to this message from my boss?", None),
    ("ตารางนี้กว้างเกินไป ช่วยปรับหน่อย", None),
    ("How long should a detailed project plan be?", None),
    ("Remember that the invoice folder is invoices/2026.", None),
    ("ตอบคำถามข้อ 2 ให้หน่อย", None),
    ("Convert this list to bullet points: apples, pears, plums.", None),
    ("Always back up the files before you edit them.", None),
]


def frozen_digest() -> str:
    return hashlib.sha256(json.dumps({"dev": DEV, "holdout": HOLDOUT}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


FROZEN_FILE = Path(__file__).with_name("user_model_dataset_r72.sha256")


def verify_frozen() -> None:
    if not FROZEN_FILE.exists():
        raise SystemExit("the dataset has not been frozen yet")
    if FROZEN_FILE.read_text(encoding="ascii").strip() != frozen_digest():
        raise SystemExit("the dataset changed after it was frozen")
