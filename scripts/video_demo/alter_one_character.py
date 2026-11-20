"""Change ONE character in one stored audit row of a COPY of the demo folder (used only in the evidence video, to show that the check fails).

Usage: python alter_one_character.py <path to the copy's data/agentic.db> [audit row id, default 3]
It refuses a path that is not inside a folder whose name ends in "_copy", so it cannot be pointed at a real database by mistake.
"""
import sqlite3
import sys
from pathlib import Path

db = Path(sys.argv[1]).resolve()
row = int(sys.argv[2]) if len(sys.argv) > 2 else 3
if not any(part.endswith("_copy") for part in db.parts):
    raise SystemExit("refused: this helper only changes a database inside a folder named ..._copy")
c = sqlite3.connect(str(db))
found = c.execute("select changes from audit_trail where id=?", (row,)).fetchone()
if not found:
    raise SystemExit(f"no audit row {row}")
text = found[0]
i = text.index("tainted") if "tainted" in text else 2
new = text[:i] + ("X" if text[i] != "X" else "Y") + text[i + 1:]
c.execute("update audit_trail set changes=? where id=?", (new, row))
c.commit()
print(f"changed 1 character in audit row {row}")
