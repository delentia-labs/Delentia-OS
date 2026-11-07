"""
Round 111: measure the cut detector of `reference_analysis.py` against the shot lists in the creator's own episode READMEs.

Criteria (written and committed before any change to the detector): research/REFERENCE_CUTS_CRITERIA_R111.md.

    python -m research.reference_cuts_eval signals  --set dev                # decode the DEV clip once and keep its signals
    python -m research.reference_cuts_eval dev-grid                          # the 74 candidates on DEV only; writes selection.json (the choice, fixed before any holdout run)
    python -m research.reference_cuts_eval holdout                           # baseline and chosen candidate, once, on the two HOLDOUT clips; refuses without selection.json
    python -m research.reference_cuts_eval report-only                       # the clips that are not graded (same edit twice, count only)

Everything is kept under `--out` (default ~/daaes-results/ref_cuts); nothing is written into the repository except what you copy by hand. The holdout command refuses a second run unless `--again` is given.
Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FPS = 30.0
TOLERANCE_S = 0.20
ROOT = Path(r"C:\Users\whale\Desktop\test motion grapihc\episodes")
CRITERIA = Path(__file__).resolve().parent / "REFERENCE_CUTS_CRITERIA_R111.md"
BASELINE = {"mode": "union", "colour_jump": 30.0, "cell_fraction": 0.0, "flash_filter": False, "min_gap": 0.5}

# name -> (video, readme, declared length in seconds, set). The split is the one in the criteria file.
CLIPS: Dict[str, Dict[str, Any]] = {
    "ep03_v2": {"video": "ep03_cher_ami/EP03_The_Pigeon_That_Stopped_Its_Own_Army_v2.mp4", "readme": "ep03_cher_ami/README.md", "declared_s": 63.0, "set": "dev"},
    "ep01_v1": {"video": "ep01_elevator/EP01_The_Elevator_Button_That_Does_Nothing_v1.mp4", "readme": "ep01_elevator/README.md", "declared_s": 58.4, "set": "holdout"},
    "ep02_v3": {"video": "ep02_emu_war/EP02_The_War_Australia_Lost_to_Birds_v3.mp4", "readme": "ep02_emu_war/README.md", "declared_s": 60.2, "set": "holdout"},
    "ep03_animatic": {"video": "ep03_cher_ami/EP03_animatic_v1.mp4", "readme": "ep03_cher_ami/README.md", "declared_s": 63.0, "set": "report"},
    "ep02_v1": {"video": "ep02_emu_war/EP02_The_War_Australia_Lost_to_Birds_v1.mp4", "readme": "ep02_emu_war/README.md", "declared_s": 60.2, "set": "report"},
    "ep02_v2": {"video": "ep02_emu_war/EP02_The_War_Australia_Lost_to_Birds_v2.mp4", "readme": "ep02_emu_war/README.md", "declared_s": 60.2, "set": "report"},
}
COUNT_ONLY = {"ep04_animatic": {"video": "ep04_manhole/EP04_animatic_v1.mp4", "shots": 19}}
# Round 2 (criteria: REFERENCE_CUTS_CRITERIA_R111_ROUND2.md): a real reference clip whose breakdown lists every shot, with dissolves of 5-8 frames
ROUND2 = {"rollercoaster": {"video": "../reference ai clip for analysis/This Shape Saved Roller Coasters.mp4", "readme": "library/REF_BREAKDOWN_roller_coaster_TH.md", "declared_s": 63.2}}
TOLERANCE_R2_S = 0.30


# ------------------------------------------------------------------------------------------------ ground truth
_ROW = re.compile(r"^\|\s*([A-Za-z][A-Za-z0-9]*)\s*\|\s*(\d+)\s*\+\s*(\d+)\s*\|")


def shot_starts(readme: Path) -> List[Tuple[str, int]]:
    """(shot name, first frame) for every row of the 'Shot list' table of an episode README."""
    out: List[Tuple[str, int]] = []
    inside = False
    for line in readme.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            inside = "shot list" in line.lower()
            continue
        if inside:
            m = _ROW.match(line)
            if m:
                out.append((m.group(1), int(m.group(2))))
    return out


def truth_cuts(readme: Path) -> List[float]:
    starts = shot_starts(readme)
    return [round(f / FPS, 3) for _, f in starts[1:]]


# ------------------------------------------------------------------------------------------------ matching and scoring
def match(detected: List[float], truth: List[float], tol: float = TOLERANCE_S) -> Dict[str, Any]:
    """One detected cut to one true cut, nearest pairs first, within `tol` seconds."""
    pairs = sorted(((abs(d - t), di, ti) for di, d in enumerate(detected) for ti, t in enumerate(truth) if abs(d - t) <= tol))
    used_d, used_t, matched = set(), set(), []
    for _dist, di, ti in pairs:
        if di in used_d or ti in used_t:
            continue
        used_d.add(di)
        used_t.add(ti)
        matched.append((detected[di], truth[ti]))
    return {"matched": matched, "missed": [t for i, t in enumerate(truth) if i not in used_t], "extra": [d for i, d in enumerate(detected) if i not in used_d]}


def score(m: Dict[str, Any], n_detected: int, n_truth: int) -> Dict[str, Any]:
    k = len(m["matched"])
    recall = k / n_truth if n_truth else 0.0
    precision = k / n_detected if n_detected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"true_cuts": n_truth, "detected_cuts": n_detected, "matched": k, "missed": len(m["missed"]), "extra": len(m["extra"]), "recall": round(recall, 3), "precision": round(precision, 3),
            "f1": round(f1, 3), "count_ratio": round((n_detected + 1) / (n_truth + 1), 3)}


def pooled(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    t, d, k = sum(r["true_cuts"] for r in rows), sum(r["detected_cuts"] for r in rows), sum(r["matched"] for r in rows)
    recall, precision = (k / t if t else 0.0), (k / d if d else 0.0)
    return {"true_cuts": t, "detected_cuts": d, "matched": k, "recall": round(recall, 3), "precision": round(precision, 3),
            "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0}


# ------------------------------------------------------------------------------------------------ the search space
def candidates() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = [{"mode": "scene_only", "colour_jump": 30.0, "cell_fraction": 0.0, "flash_filter": False, "min_gap": g} for g in (0.5, 1.0)]
    for mode in ("colour_only", "union"):
        for jump in (30.0, 45.0, 60.0):
            for frac in (0.0, 0.5, 0.7):
                for flash in (False, True):
                    for gap in (0.5, 1.0):
                        out.append({"mode": mode, "colour_jump": jump, "cell_fraction": frac, "flash_filter": flash, "min_gap": gap})
    return out


def simplicity(c: Dict[str, Any]) -> int:
    """Features switched on (a tie goes to the fewest, then to the larger gap)."""
    return int(c["cell_fraction"] > 0) + int(c["flash_filter"]) + int(c["colour_jump"] != 30.0)


def label(c: Dict[str, Any]) -> str:
    return f"{c['mode']} jump={c['colour_jump']:g} cells>={c['cell_fraction']:g} flash={'on' if c['flash_filter'] else 'off'} gap={c['min_gap']:g}"


# ------------------------------------------------------------------------------------------------ signals
def clip_signals(name: str, out: Path) -> Dict[str, Any]:
    from rct_control_plane import reference_analysis as ra
    cache = out / "signals" / f"{name}.json"
    if cache.is_file():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if "diffw" in cached:                                  # signals made before round 2 lack the windowed differences: they are made again
            return cached
    meta = {**CLIPS, **COUNT_ONLY, **ROUND2}[name]
    video = ROOT / meta["video"]
    facts = ra.probe(ra._safe_path(str(video)))
    declared = meta.get("declared_s")
    if declared is not None and abs(facts["duration_s"] - declared) > 0.5:
        raise SystemExit(f"{name}: the clip is {facts['duration_s']} s and its README declares {declared} s: excluded by the criteria")
    sig = ra.cut_signals(video)
    sig["duration_s"] = facts["duration_s"]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(sig), encoding="utf-8")
    return sig


_TIME_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*[\u2013\u2014-]\s*([0-9]+(?:\.[0-9]+)?)\s*\|")


def breakdown_cuts(path: Path) -> List[float]:
    """Cuts from a breakdown table `| # | start-end | ...`: the start of every shot but the first. Only the table under the heading that mentions 'Shot-by-shot' is read."""
    starts: List[float] = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            inside = "shot-by-shot" in line.lower()
            continue
        if inside:
            m = _TIME_ROW.match(line)
            if m:
                starts.append(float(m.group(2)))
    return starts[1:]


def evaluate_clip(name: str, rule: Dict[str, Any], out: Path) -> Dict[str, Any]:
    from rct_control_plane import reference_analysis as ra
    sig = clip_signals(name, out)
    if name in ROUND2:
        truth, tol = breakdown_cuts(ROOT / ROUND2[name]["readme"]), TOLERANCE_R2_S
    else:
        truth, tol = truth_cuts(ROOT / CLIPS[name]["readme"]), TOLERANCE_S
    detected = ra.cuts_from_signals(sig, **rule)
    m = match(detected, truth, tol)
    return {"clip": name, **score(m, len(detected), len(truth)), "missed_at_s": m["missed"], "extra_at_s": m["extra"]}


# ------------------------------------------------------------------------------------------------ commands
def cmd_signals(args: argparse.Namespace) -> int:
    if args.set != "dev":
        print("only the DEV clip is decoded here; the holdout command decodes its clips itself, after selection.json exists")
        return 2
    for name, meta in CLIPS.items():
        if meta["set"] == "dev":
            sig = clip_signals(name, Path(args.out))
            print(f"{name}: {len(sig['diff'])} samples, {len(sig['scene'])} brightness cuts")
    return 0


def cmd_dev_grid(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in candidates():
        r = evaluate_clip("ep03_v2", c, out)
        rows.append({"candidate": c, "label": label(c), **{k: r[k] for k in ("true_cuts", "detected_cuts", "matched", "recall", "precision", "f1")}})
    rows.sort(key=lambda r: (-r["f1"], simplicity(r["candidate"]), -r["candidate"]["min_gap"]))
    chosen = rows[0]
    base = next(r for r in rows if r["candidate"] == BASELINE)
    selection = {"chosen": chosen["candidate"], "chosen_label": chosen["label"], "dev_result": {k: chosen[k] for k in ("matched", "recall", "precision", "f1")},
                 "baseline_dev_result": {k: base[k] for k in ("matched", "recall", "precision", "f1")}, "criteria_sha256": hashlib.sha256(CRITERIA.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                 "candidates_evaluated": len(rows)}
    selection["selection_sha256"] = hashlib.sha256(json.dumps({k: v for k, v in selection.items() if k != "selection_sha256"}, sort_keys=True).encode()).hexdigest()
    (out / "dev_grid.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    (out / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    print("top 8 on DEV (EP03 v2):")
    for r in rows[:8]:
        print(f"  F1 {r['f1']:.3f} recall {r['recall']:.3f} precision {r['precision']:.3f}  {r['label']}")
    print(f"baseline: F1 {base['f1']:.3f} recall {base['recall']:.3f} precision {base['precision']:.3f}")
    print(f"CHOSEN (written to selection.json before any holdout run): {chosen['label']}")
    return 0


def verdict(base: Dict[str, Any], chosen: Dict[str, Any], base_rows: List[Dict[str, Any]], chosen_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def useful(p: Dict[str, Any], rows: List[Dict[str, Any]]) -> bool:
        return p["recall"] >= 0.85 and p["precision"] >= 0.75 and all(r["recall"] >= 0.75 for r in rows)
    adopt = useful(chosen, chosen_rows) and chosen["precision"] >= base["precision"] + 0.05 and chosen["recall"] >= base["recall"] - 0.03
    return {"baseline_useful_for_planning": useful(base, base_rows), "chosen_useful_for_planning": useful(chosen, chosen_rows), "adopt_chosen_as_default": adopt}


def cmd_holdout(args: argparse.Namespace) -> int:
    out = Path(args.out)
    sel_file, res_file = out / "selection.json", out / "holdout_results.json"
    if not sel_file.is_file():
        print("refused: selection.json does not exist. Run dev-grid first: the choice is fixed before any holdout clip is looked at.")
        return 2
    if res_file.is_file() and not args.again:
        print(f"refused: {res_file} exists. The holdout is run once; --again records a repeat.")
        return 2
    selection = json.loads(sel_file.read_text(encoding="utf-8"))
    chosen = selection["chosen"]
    names = [n for n, m in CLIPS.items() if m["set"] == "holdout"]
    base_rows = [evaluate_clip(n, BASELINE, out) for n in names]
    chosen_rows = [evaluate_clip(n, chosen, out) for n in names]
    pb, pc = pooled(base_rows), pooled(chosen_rows)
    result = {"selection_sha256": selection["selection_sha256"], "repeat": bool(res_file.is_file()), "tolerance_s": TOLERANCE_S, "baseline": {"rule": BASELINE, "clips": base_rows, "pooled": pb},
              "chosen": {"rule": chosen, "label": selection["chosen_label"], "clips": chosen_rows, "pooled": pc}, "verdict": verdict(pb, pc, base_rows, chosen_rows)}
    res_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for tag, rows, p in (("BASELINE", base_rows, pb), ("CHOSEN", chosen_rows, pc)):
        print(f"{tag}")
        for r in rows:
            print(f"  {r['clip']}: matched {r['matched']}/{r['true_cuts']} true, {r['detected_cuts']} detected, recall {r['recall']:.3f} precision {r['precision']:.3f}  missed at {r['missed_at_s']}  extra {r['extra']} ")
        print(f"  pooled: matched {p['matched']}/{p['true_cuts']} true, {p['detected_cuts']} detected, recall {p['recall']:.3f} precision {p['precision']:.3f}")
    print("VERDICT", result["verdict"])
    return 0


def cmd_report_only(args: argparse.Namespace) -> int:
    out = Path(args.out)
    sel = json.loads((out / "selection.json").read_text(encoding="utf-8")) if (out / "selection.json").is_file() else None
    for name in [n for n, m in CLIPS.items() if m["set"] == "report"]:
        for tag, rule in (("baseline", BASELINE), *((("chosen", sel["chosen"]),) if sel else ())):
            r = evaluate_clip(name, rule, out)
            print(f"{name} {tag}: matched {r['matched']}/{r['true_cuts']} true, {r['detected_cuts']} detected, recall {r['recall']:.3f} precision {r['precision']:.3f}")
    from rct_control_plane import reference_analysis as ra
    sig = clip_signals("ep04_animatic", out)
    for tag, rule in (("baseline", BASELINE), *((("chosen", sel["chosen"]),) if sel else ())):
        n = len(ra.cuts_from_signals(sig, **rule)) + 1
        print(f"ep04_animatic {tag}: {n} shots detected, the README says {COUNT_ONLY['ep04_animatic']['shots']} (count only, dissolves of about half a second)")
    return 0


# ------------------------------------------------------------------------------------------------ round 2: dissolves
def candidates2() -> List[Dict[str, Any]]:
    return [{"mode": "union", "colour_jump": float(j), "cell_fraction": 0.0, "flash_filter": False, "min_gap": g, "window": w} for w in (1, 2, 3) for j in (12, 16, 20, 25, 30) for g in (0.5, 1.0)]


def simplicity2(c: Dict[str, Any]) -> Tuple[int, float, float]:
    return (int(c["window"]) - 1, abs(c["colour_jump"] - 30.0), -c["min_gap"])


def label2(c: Dict[str, Any]) -> str:
    return f"window={c['window']} jump={c['colour_jump']:g} gap={c['min_gap']:g}"


BASELINE2 = {**BASELINE, "window": 1}
CRITERIA2 = Path(__file__).resolve().parent / "REFERENCE_CUTS_CRITERIA_R111_ROUND2.md"


def cmd_r2_dev(args: argparse.Namespace) -> int:
    out = Path(args.out)
    rows = []
    for c in candidates2():
        r = evaluate_clip("rollercoaster", c, out)
        rows.append({"candidate": c, "label": label2(c), **{k: r[k] for k in ("true_cuts", "detected_cuts", "matched", "recall", "precision", "f1")}})
    rows.sort(key=lambda r: (-r["f1"], simplicity2(r["candidate"])))
    base = next(r for r in rows if r["candidate"] == BASELINE2)
    chosen = rows[0]
    selection = {"chosen": chosen["candidate"], "chosen_label": chosen["label"], "dev2_result": {k: chosen[k] for k in ("matched", "recall", "precision", "f1")},
                 "baseline_dev2_result": {k: base[k] for k in ("matched", "recall", "precision", "f1")}, "criteria_sha256": hashlib.sha256(CRITERIA2.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                 "candidates_evaluated": len(rows)}
    selection["selection_sha256"] = hashlib.sha256(json.dumps({k: v for k, v in selection.items() if k != "selection_sha256"}, sort_keys=True).encode()).hexdigest()
    (out / "r2_dev_grid.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    (out / "r2_selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    print("top 8 on DEV2 (roller coaster, tolerance 0.30 s):")
    for r in rows[:8]:
        print(f"  F1 {r['f1']:.3f} recall {r['recall']:.3f} precision {r['precision']:.3f}  {r['label']}")
    print(f"baseline: matched {base['matched']}/{base['true_cuts']}, {base['detected_cuts']} detected, F1 {base['f1']:.3f} recall {base['recall']:.3f} precision {base['precision']:.3f}")
    print(f"CHOSEN (written to r2_selection.json before any guard run): {chosen['label']}")
    return 0


def verdict2(base_dev: Dict[str, Any], chosen_dev: Dict[str, Any], base_guard: Dict[str, Any], chosen_guard: Dict[str, Any], ep03_base: Dict[str, Any], ep03_chosen: Dict[str, Any],
             ep04_shots: int) -> Dict[str, Any]:
    a = chosen_dev["f1"] >= base_dev["f1"] + 0.10
    b = chosen_guard["recall"] >= 0.85 and chosen_guard["precision"] >= 0.75 and ep03_chosen["f1"] >= ep03_base["f1"] - 0.05
    c = 15 <= ep04_shots <= 24
    return {"a_dev2_f1_gain_at_least_0.10": a, "b_guard_holds": b, "c_ep04_count_15_to_24": c, "adopt_chosen_as_default": bool(a and b and c),
            "baseline_finds_dissolves": base_dev["recall"] >= 0.5}


def cmd_r2_guard(args: argparse.Namespace) -> int:
    out = Path(args.out)
    sel_file, res_file = out / "r2_selection.json", out / "r2_guard_results.json"
    if not sel_file.is_file():
        print("refused: r2_selection.json does not exist. Run r2-dev first: the choice is fixed before the guard clips and EP04 are run with it.")
        return 2
    if res_file.is_file() and not args.again:
        print(f"refused: {res_file} exists. The guard is run once; --again records a repeat.")
        return 2
    from rct_control_plane import reference_analysis as ra
    sel = json.loads(sel_file.read_text(encoding="utf-8"))
    chosen = sel["chosen"]
    result: Dict[str, Any] = {"selection_sha256": sel["selection_sha256"], "repeat": bool(res_file.is_file())}
    guard_names = ["ep01_v1", "ep02_v3"]
    for tag, rule in (("baseline", BASELINE2), ("chosen", chosen)):
        rows = [evaluate_clip(n, rule, out) for n in guard_names]
        ep03 = evaluate_clip("ep03_v2", rule, out)
        n4 = len(ra.cuts_from_signals(clip_signals("ep04_animatic", out), **rule)) + 1
        result[tag] = {"rule": rule, "guard_clips": rows, "guard_pooled": pooled(rows), "ep03": {k: ep03[k] for k in ("matched", "true_cuts", "detected_cuts", "recall", "precision", "f1")}, "ep04_shots": n4}
    dev_base, dev_chosen = sel["baseline_dev2_result"], sel["dev2_result"]
    result["verdict"] = verdict2(dev_base, dev_chosen, result["baseline"]["guard_pooled"], result["chosen"]["guard_pooled"], result["baseline"]["ep03"], result["chosen"]["ep03"], result["chosen"]["ep04_shots"])
    res_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for tag in ("baseline", "chosen"):
        r = result[tag]
        print(f"{tag.upper()}: guard pooled recall {r['guard_pooled']['recall']:.3f} precision {r['guard_pooled']['precision']:.3f}; EP03 F1 {r['ep03']['f1']:.3f}; EP04 shots {r['ep04_shots']} (README 19)")
    print("DEV2: baseline", dev_base, "chosen", dev_chosen)
    print("VERDICT", result["verdict"])
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path.home() / "daaes-results" / "ref_cuts"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("signals")
    s.add_argument("--set", default="dev")
    sub.add_parser("dev-grid")
    h = sub.add_parser("holdout")
    h.add_argument("--again", action="store_true")
    sub.add_parser("report-only")
    sub.add_parser("r2-dev")
    g = sub.add_parser("r2-guard")
    g.add_argument("--again", action="store_true")
    args = ap.parse_args(argv)
    return {"signals": cmd_signals, "dev-grid": cmd_dev_grid, "holdout": cmd_holdout, "report-only": cmd_report_only, "r2-dev": cmd_r2_dev, "r2-guard": cmd_r2_guard}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
