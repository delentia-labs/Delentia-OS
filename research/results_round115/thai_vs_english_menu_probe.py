import asyncio, json, logging
logging.disable(logging.WARNING)
from rct_control_plane import tool_menu
from research import tool_menu_siblings_r114 as sib
spec = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
every = asyncio.run(sib.builtin_tools()) + sib.synthetic_tools(spec["servers"])
for g in ["อ่านโน้ตเรื่องงบให้หน่อย", "Read the note about the budget", "ดูตั๋วหมายเลข 4412", "ค้นหาข้อความจากสมชาย", "list my events next week"]:
    scores = tool_menu.score_tools(g, every)
    shown = tool_menu.rank_tools(g, every, 10)
    ext = [t["name"] for t in shown if t["name"].startswith("mcp__")]
    print(repr(g), "| menu", len(shown), "| external in menu:", ext, "| nonzero scores:", sum(1 for s in scores if s > 0))
