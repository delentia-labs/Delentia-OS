"""
Round 68: a small recall benchmark that does not depend on any memory system.

30 facts, each with ONE answer value that appears nowhere else; 90 distractors that talk about the same kinds of things with other values; 30 questions written as paraphrases (they avoid the words of
the fact on purpose, so a system that only matches words does badly and one that understands does better). A system "hits" a question when the answer value appears in any of its top-3 results.
Written before any system was run on it; the distractors are checked by `check()` never to contain an answer value.

    python research/recall_dataset_r68.py       # prints the checks
"""
from __future__ import annotations

import random
from typing import Dict, List, Tuple

PAIRS: List[Tuple[str, str, str]] = [
    # (fact, question, answer value)
    ("Our customs liaison is Prasert and he works from the Laem Chabang office.", "Who handles import clearance for us?", "Prasert"),
    ("The warehouse closes at 17:00 on weekdays and at 12:00 on Saturdays.", "When do the storage facility doors shut on a Saturday?", "12:00"),
    ("Invoices are numbered with the prefix HB- followed by five digits.", "What does a bill number start with?", "HB-"),
    ("The refund window for online orders is 14 days from delivery.", "How long after receiving goods can a customer get their money back?", "14 days"),
    ("Our main packaging vendor is PakWell; the backup vendor is BoxHub.", "Which company supplies our cartons when the primary cannot?", "BoxHub"),
    ("The deploy window is Tuesday at 02:00 UTC and Malee approves it.", "Who signs off on releases?", "Malee"),
    ("The staging database is stg-db-1.", "What is the name of the pre-production data store?", "stg-db-1"),
    ("The monthly cloud budget is capped at 15,000 baht.", "How much may we spend each month on hosting?", "15,000"),
    ("On-call escalation happens after 20 minutes without an acknowledgement.", "How long do we wait before paging the next person?", "20 minutes"),
    ("Aisle 7 holds the refrigerated stock and needs a badge from Chaiwat.", "Who gives access to the cold-storage section?", "Chaiwat"),
    ("Backups run nightly at 03:30 and are kept for 35 days.", "For how long do we retain the copies of our data?", "35 days"),
    ("The support hotline is 02-555-0147 and is open 08:00-17:00.", "What number do customers ring for help?", "02-555-0147"),
    ("Orders over 6,500 baht ship free within Bangkok.", "Above what purchase amount is delivery at no charge in the capital?", "6,500"),
    ("The office closes on 12 August and 5 December.", "On which dates is the workplace shut for holidays?", "12 August"),
    ("Our payment provider is Omise and settlements arrive every Wednesday.", "On which weekday does money from card sales land in our bank?", "Wednesday"),
    ("The product catalogue lives in the repository folder data/catalog.", "Where in the codebase are the items we sell listed?", "data/catalog"),
    ("The retry limit for failed uploads is 9 attempts.", "How many times will a failed transfer be tried again?", "9 attempts"),
    ("Thanakorn covers the night shift on public holidays.", "Who is staffed overnight on bank holidays?", "Thanakorn"),
    ("The API rate limit is 120 requests per minute with a burst of 30.", "How many calls a minute may a client make?", "120 requests"),
    ("The primary region is ap-southeast-1 and failover goes to ap-northeast-1.", "Where does traffic go if the main data centre goes down?", "ap-northeast-1"),
    ("Customer interviews are recorded only with written consent.", "What must we have before taping a conversation with a client?", "written consent"),
    ("The sandbox password rotates every 90 days.", "How frequently do we change the test environment credentials?", "90 days"),
    ("Release notes are published in the #harbor-announce channel.", "Which chat room gets the changelog posts?", "#harbor-announce"),
    ("The courier for fragile goods is Siam Express.", "Which delivery company carries delicate items?", "Siam Express"),
    ("Pimchanok is the buddy of every new engineer for the first month.", "Who mentors newcomers during their first weeks?", "Pimchanok"),
    ("The queue holds at most 250 jobs and each job times out after 12 seconds.", "After how many seconds is a pending task abandoned?", "12 seconds"),
    ("Quarterly planning happens in the first week of January, April, July and October.", "When do we sit down to plan each three-month period?", "first week"),
    ("Our SLA promises a first reply within 4 hours.", "How fast must we first answer a ticket?", "4 hours"),
    ("Vendor contracts renew every March.", "In which month do supplier agreements come up for renewal?", "March"),
    ("ผู้อนุมัติงบประมาณของฝ่ายขายคือคุณวันดี", "ใครเป็นคนเซ็นอนุมัติเงินของทีมขาย", "วันดี"),
]

_TEMPLATES = [
    "Our {role} is {name} and works from the {place} office.", "The {thing} closes at {time} on {day}.", "The {thing} for {what} is {n} days from {start}.",
    "The main {supplier} vendor is {name}; the backup vendor is {name2}.", "The {env} database is called {db}.", "The monthly {cost} budget is capped at {amount} baht.",
    "{name} gives access to the {area} section.", "The {job} runs nightly at {time} and is kept for {n} days.", "Orders over {amount} baht ship free within {city}.",
    "The {tool} rate limit is {n} requests per minute.", "{name} is the contact for {topic}.", "The {team} meeting is held every {day} at {time}.",
]
_FILL = {
    "role": ["legal liaison", "finance contact", "security officer", "procurement lead", "facilities manager", "payroll clerk"],
    "name": ["Somsak", "Nattaya", "Kritsada", "Ploy", "Anan", "Wipa", "Surasak", "Mali", "Pichai", "Duangjai"],
    "name2": ["CartonCo", "WrapIt", "SafeBox", "ShipPack", "TapeWorks", "FoamLine"],
    "place": ["Rayong", "Chiang Mai", "Phuket", "Korat", "Hat Yai", "Ayutthaya"],
    "thing": ["loading dock", "back office", "parts store", "meeting room", "server room", "reception"],
    "time": ["18:30", "09:15", "21:00", "06:45", "13:10", "16:20"],
    "day": ["Friday", "Monday", "Sunday", "Thursday", "the last day of the month", "Tuesday"],
    "what": ["replacement parts", "in-store purchases", "wholesale orders", "gift cards", "spare cables", "repairs"],
    "n": ["7", "21", "45", "60", "3", "30"],
    "start": ["purchase", "dispatch", "the invoice date", "pickup", "signature", "installation"],
    "supplier": ["labelling", "cleaning", "printing", "catering", "uniform", "security"],
    "env": ["test", "analytics", "training", "demo", "reporting", "archive"],
    "db": ["tst-db-3", "ana-db-9", "trn-db-2", "demo-db-5", "rpt-db-4", "arc-db-8"],
    "cost": ["travel", "software", "marketing", "training", "equipment", "office"],
    "amount": ["8,200", "2,750", "40,300", "1,350", "76,400", "310"],
    "area": ["dry goods", "returns", "electronics", "chemical", "loading", "archive"],
    "job": ["database export", "log rotation", "report build", "index rebuild", "cache warmup", "mail digest"],
    "city": ["Chiang Mai", "Phuket", "Khon Kaen", "Pattaya", "Hat Yai", "Nonthaburi"],
    "tool": ["search", "billing", "export", "webhook", "upload", "login"],
    "topic": ["building access", "visa paperwork", "fleet vehicles", "uniform orders", "parking permits", "equipment loans"],
    "team": ["design", "support", "finance", "operations", "marketing", "platform"],
}


def make_distractors(n: int = 90, seed: int = 3) -> List[str]:
    rng = random.Random(seed)
    out: List[str] = []
    seen = set()
    while len(out) < n:
        t = rng.choice(_TEMPLATES)
        text = t.format(**{k: rng.choice(v) for k, v in _FILL.items()})
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def dataset() -> Dict[str, object]:
    return {"facts": [{"id": f"f{i:02d}", "text": f, "question": q, "answer": a} for i, (f, q, a) in enumerate(PAIRS)], "distractors": make_distractors()}


def check() -> Dict[str, object]:
    d = dataset()
    answers = [x["answer"] for x in d["facts"]]
    clash = [(dist, a) for dist in d["distractors"] for a in answers if a.lower() in dist.lower()]
    fact_hits = {}
    for x in d["facts"]:
        fact_hits[x["id"]] = sum(1 for y in d["facts"] if x["answer"].lower() in y["text"].lower())
    unique = all(v == 1 for v in fact_hits.values())
    shared_words = []
    for x in d["facts"]:
        q = {w.strip("?.,").lower() for w in x["question"].split() if len(w) > 3}
        f = {w.strip("?.,").lower() for w in x["text"].split() if len(w) > 3}
        shared_words.append(len(q & f))
    return {"facts": len(d["facts"]), "distractors": len(d["distractors"]), "distractors_containing_an_answer": clash, "answers_unique_to_their_fact": unique,
            "mean_words_shared_by_question_and_fact": round(sum(shared_words) / len(shared_words), 2)}


if __name__ == "__main__":
    print(check())
