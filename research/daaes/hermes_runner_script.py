"""
Runs ONE Hermes conversation. This file is executed by Hermes' own Python (3.14, its own virtual environment), never imported by Delentia: `python hermes_runner_script.py <config.json>`.

It exists so that the system under comparison is driven through its public entry point (`AIAgent.run_conversation`) with a model endpoint it cannot tell from a real one (the DAAES model gateway),
a workspace folder as its working directory, and only the file and terminal tools. It prints one line `HERMES_RESULT {json}` and exits; everything else goes to stderr.
"""
import json
import os
import sys


def main() -> int:
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    sys.path.insert(0, cfg["hermes_src"])
    os.environ["HERMES_HOME"] = cfg["hermes_home"]
    from run_agent import AIAgent                                    # noqa: E402 - needs the path set above

    agent = AIAgent(base_url=cfg["base_url"], api_key=cfg["api_key"], provider="custom", model=cfg["model"], enabled_toolsets=cfg.get("toolsets") or ["file", "terminal"],
                    quiet_mode=True, skip_memory=True, skip_context_files=True, max_iterations=int(cfg.get("max_iterations", 14)), save_trajectories=False, cwd=cfg["workspace"],
                    run_budget_seconds=float(cfg.get("max_seconds", 600)))
    result = agent.run_conversation(cfg["goal"])
    calls = []
    for m in result.get("messages", []):
        for c in m.get("tool_calls") or []:
            fn = c.get("function") or {}
            args = fn.get("arguments")
            try:
                parsed = json.loads(args) if isinstance(args, str) else (args or {})
            except ValueError:
                parsed = {"_unparsed": str(args)[:200]}
            calls.append({"tool": fn.get("name"), "path": parsed.get("path"), "command": str(parsed.get("command") or "")[:200]})
    out = {"final_response": result.get("final_response"), "completed": bool(result.get("completed")), "failed": bool(result.get("failed")), "api_calls": result.get("api_calls"),
           "error": str(result.get("error") or "")[:300], "tool_calls": calls}
    print("HERMES_RESULT " + json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
