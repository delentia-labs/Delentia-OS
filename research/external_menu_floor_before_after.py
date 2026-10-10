"""
Round 67: the same other-people's recipes (GTFOBins, see external_menu_attack.py) classified by the shell floor as it stood at the end of Round 66 (read from git, `HEAD` of the branch this
round started from) and as it stands now. Classification only; nothing is executed.

    python research/external_menu_floor_before_after.py --gtfobins <dir> --before-ref <git ref>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))


def load_old_sandbox(ref: str):
    text = subprocess.run(["git", "show", f"{ref}:rct_control_plane/sandbox.py"], cwd=ROOT, capture_output=True, text=True, check=True, encoding="utf-8").stdout
    path = Path(tempfile.mkdtemp(prefix="delentia-oldfloor-")) / "sandbox_before.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("sandbox_before", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sandbox_before"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gtfobins", required=True)
    ap.add_argument("--before-ref", default="HEAD")
    ap.add_argument("--commix", default=None, help="SecLists Fuzzing/command-injection-commix.txt: classified only, as `payload`, `ls payload` and `lspayload`")
    ap.add_argument("--out", default=str(ROOT / "research" / "external_menu_floor_before_after.json"))
    args = ap.parse_args()
    import external_menu_attack as ema
    from rct_control_plane import sandbox as new
    old = load_old_sandbox(args.before_ref)
    canary, rel, out = "C:/h/secret.txt", "credentials.json", "C:/h/out.txt"
    rows = []
    for entry in sorted(Path(args.gtfobins).glob("*.txt")):
        program = entry.stem.replace("_entry", "")
        if program == "commix":
            continue
        for function, block in ema.parse_codes(entry.read_text(encoding="utf-8")):
            for line in ema.first_command_lines(block):
                for how, command in ema.variants(line, canary, rel, out):
                    rows.append({"program": program, "function": function, "variant": how, "command": command[:140], "before": old.classify_command_risk(command), "after": new.classify_command_risk(command)})
    def count(key, value):
        return sum(1 for r in rows if r[key] == value)
    summary = {"recipes": len(rows), "before": {v: count("before", v) for v in ("safe", "needs_approval", "denied")}, "after": {v: count("after", v) for v in ("safe", "needs_approval", "denied")},
               "safe_before_by_function": {}, "still_safe_after": [r for r in rows if r["after"] == "safe"]}
    for r in rows:
        if r["before"] == "safe":
            summary["safe_before_by_function"][r["function"]] = summary["safe_before_by_function"].get(r["function"], 0) + 1
    if args.commix and Path(args.commix).exists():
        import urllib.parse
        payloads = sorted({urllib.parse.unquote(line.strip()) for line in Path(args.commix).read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()})
        shapes = {"alone": lambda x: x, "after_ls": lambda x: "ls " + x, "after_ls_nospace": lambda x: "ls" + x}
        summary["commix"] = {"payloads": len(payloads), **{name: {"floor_safe_before": sum(1 for x in payloads if old.classify_command_risk(f(x)) == "safe"),
                                                                 "floor_safe_after": sum(1 for x in payloads if new.classify_command_risk(f(x)) == "safe")} for name, f in shapes.items()}}
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "still_safe_after"}, indent=2))
    for r in summary["still_safe_after"]:
        print("  still safe:", r["program"], r["function"], r["command"][:80].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
