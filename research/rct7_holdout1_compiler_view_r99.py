"""How the existing IntentCompiler (risk profile, intent type) sees the Architect's holdout set 1, next to his labels. Read-only; nothing is tuned on this.

    python -m research.rct7_holdout1_compiler_view_r99 SHEET.md

The compiler was written long before this set and is NOT changed by what this prints. Its risk profile (LOW / STRUCTURAL / SYSTEMIC) is what the loop's route and gate already use, so the question
is how far "the Architect wants a plan and a confirmation" (his A) is already predicted by "the compiler thinks it is not low risk". Reported per reason class (research/rct7_holdout1_reason_classes_r99.json).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from rct_control_plane.intent_compiler import IntentCompiler
from research import rct7_holdout


def _value(x: Any) -> Any:
    return getattr(x, "value", x)


def view(sheet: Path) -> Dict[str, Any]:
    sealed = rct7_holdout.load_sealed(sheet)
    classes = json.loads((Path(__file__).parent / "rct7_holdout1_reason_classes_r99.json").read_text(encoding="utf-8"))["A"]
    by_number: Dict[int, str] = {n: c for c, numbers in classes.items() for n in numbers}
    compiler = IntentCompiler()
    rows: List[Dict[str, Any]] = []
    for n_text, item in sorted(sealed["items_data"].items(), key=lambda kv: int(kv[0])):
        n = int(n_text)
        if item["label"] not in ("A", "B"):
            continue
        result = compiler.compile(item["request"], "holdout", "INTERNAL")
        intent = result.intent
        rows.append({"n": n, "label": item["label"], "class": by_number.get(n, "B"), "request": item["request"],
                     "compiled": bool(result.success and intent), "type": _value(getattr(intent, "intent_type", None)),
                     "risk": _value(getattr(intent, "risk_profile", None))})
    return {"rows": rows}


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def raised(r: Dict[str, Any]) -> bool:
        return r["risk"] in ("STRUCTURAL", "SYSTEMIC")
    out: Dict[str, Any] = {}
    for name in ("A", "B"):
        group = [r for r in rows if r["label"] == name]
        out[name] = {"n": len(group), "risk_raised": sum(raised(r) for r in group), "not_compiled": sum(not r["compiled"] for r in group)}
    classes: Dict[str, Dict[str, int]] = {}
    for r in rows:
        if r["label"] == "A":
            b = classes.setdefault(r["class"], {"n": 0, "risk_raised": 0})
            b["n"] += 1
            b["risk_raised"] += int(raised(r))
    out["A_by_class"] = classes
    return out


def main() -> int:
    sheet = Path(sys.argv[1])
    data = view(sheet)
    print(json.dumps(summarise(data["rows"]), ensure_ascii=False, indent=2))
    for r in data["rows"]:
        print(f"{r['n']:>3} {r['label']} {r['class']:<9} {str(r['type']):<14} {str(r['risk']):<11} {r['request'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
