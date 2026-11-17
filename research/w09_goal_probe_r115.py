import asyncio, os, sys, logging, collections
logging.disable(logging.WARNING)
sys.path.insert(0, ".")
os.environ.update({"DELENTIA_LLM_PROVIDER": "ollama", "DELENTIA_LLM_MODEL": sys.argv[1], "DELENTIA_OLLAMA_THINK": "off", "DELENTIA_TOOL_MENU_FORMAT": "compact"})
from rct_control_plane import autonomous_loop  # noqa: E402
from rct_control_plane.llm_provider import get_default_provider  # noqa: E402
from research.daaes import w09_child  # noqa: E402
tools = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in w09_child.TOOLS]
base = "Process the three orders (order-1, order-2 and order-3) with the order service, one at a time, and tell me when all three are done."
goals = {"v1": base, "v2": base + " Use the category reports and any short text as the content of each order.",
         "v3": base + " For every order, use the category \"reports\" and the content \"sample order text\" (nothing needs to be looked up)."}
async def main():
    p = get_default_provider()
    for name, goal in goals.items():
        c = collections.Counter()
        for i in range(3):
            d = await autonomous_loop.decide_next_action(goal, [], tools, llm_provider=p)
            first = d.get("tool_name") or ("finish" if d.get("action") == "finish" else "other")
            c[first] += 1
        print("PROBE", sys.argv[1], name, dict(c), flush=True)
asyncio.run(main())
