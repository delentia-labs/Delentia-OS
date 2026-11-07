# Criteria for the cut detector of `reference_analysis.py`, written 2026-11-07 BEFORE any change to the detector and before the detector was run on any clip except EP03 v2

Why this file exists. The first real clip (EP03 v2, 63.1 s) gave 26 detected cuts against 18 true cuts: 16 matched, 2 missed, 10 extra (recall 0.89, precision 0.62). Tuning the detector on that one result alone would fit the detector to what has been seen.
So the clips are split NOW, the search space is fixed NOW, and the rule for adopting a change is fixed NOW. The ground truth is the shot list in each episode's own `README.md` (written by the creator of the clips, not by the detector or by Claude).

## Ground truth
* A shot table row `| Shot | from +len | ...` gives the first frame of the shot. A cut is the start of every shot except the first, at `frame / 30` seconds (all clips are 30 fps).
* Matching: one detected cut to one true cut, nearest first, within **0.20 s (6 frames)**. Unmatched true cuts are misses, unmatched detected cuts are extras.
* Recall = matched / true cuts. Precision = matched / detected cuts. Count ratio = detected shots / true shots.
* A clip is admitted only if its duration is within 0.5 s of the length its README declares; otherwise it is excluded and the reason is reported.

## The split (fixed here)
| Set | Clip | True shots | Why |
|---|---|---|---|
| DEV | `ep03_cher_ami/EP03_The_Pigeon_That_Stopped_Its_Own_Army_v2.mp4` | 19 | its result was already seen (16 matched, 2 missed, 10 extra) |
| HOLDOUT | `ep01_elevator/EP01_The_Elevator_Button_That_Does_Nothing_v1.mp4` | 14 (S01-S14) | 58.4 s, README 58.4 s |
| HOLDOUT | `ep02_emu_war/EP02_The_War_Australia_Lost_to_Birds_v3.mp4` | 16 (s01..s13 with a/b) | 60.3 s, README about 60.2 s; v3 is the newest of three renders with the same length |
| REPORT ONLY | EP03 animatic (same edit, other render), EP04 animatic (only the count of 19 shots is stated), EP02 v1 and v2 | | not graded: the same edit twice, or no frame truth |
No detector setting is ever chosen on a HOLDOUT clip.

## The search space (fixed here; evaluated on DEV only)
The signals are computed once per clip from the video: ffmpeg's brightness scene score (threshold 0.3, as now) and, for every neighbouring pair of 16x9 thumbnails taken at 10 frames a second, (a) the mean absolute colour difference, (b) the fraction of the 144 cells whose difference is above 40, (c) whether the picture goes back (the thumbnail 3 samples later is closer to the one before the jump than to the one after it).
A candidate is one choice of:
* mode: `scene_only`, `colour_only`, `union` (as now);
* colour jump (a): 30, 45, 60 (ignored by `scene_only`);
* cell fraction (b): off, 0.5, 0.7;
* flash filter (c): off, on (a jump that goes back within 3 samples is not a cut);
* minimum gap between two cuts: 0.5 s, 1.0 s.
That is 74 candidates (2 for `scene_only`, 36 each for the other two). The current detector is the candidate `union`, 30, off, off, 0.5 s: it is the BASELINE and is always reported next to the chosen one.

## Choosing and testing
1. Run all 74 candidates on DEV. Choose the highest F1 (2 x precision x recall / (precision + recall)); a tie goes to the candidate with the fewest features switched on, then to the larger gap. Write the choice to `selection.json` with its hash BEFORE touching a HOLDOUT clip; the holdout command refuses to run without it.
2. Run the BASELINE and the CHOSEN candidate once on each HOLDOUT clip. A second run is refused unless `--again` is given and is then recorded as a repeat.
3. Report per clip and pooled over the two holdout clips: matched, missed, extra, recall, precision, count ratio, and for each miss and each extra the time and the shot it fell in.

## Pass rules
* **Useful for planning (per tool, on the pooled holdout):** recall >= 0.85 AND precision >= 0.75. No single holdout clip below recall 0.75.
* **Adopting the chosen candidate as the default instead of the baseline:** it must meet the rule above, AND its pooled holdout precision must be at least 0.05 higher than the baseline's, AND its pooled holdout recall no more than 0.03 lower than the baseline's. Otherwise the baseline stays the default and the result is recorded as a negative result.
* If neither the baseline nor the chosen candidate meets "useful for planning", the documents say so with the measured numbers and the detector is described as a rough first pass whose cuts a person must check.
* What is NOT claimed whatever the result: accuracy on footage that is not 2.5D animation with these graphics, on dissolves longer than about half a second, or on clips with fast whip pans. Two holdout clips cannot give an interval narrower than about +-0.15 on recall; the report shows how many cuts each number stands on.

## Recording
The measured numbers go into `research/RESULTS_REGISTER.jsonl` with `python -m research.results_register add` naming this file as the criteria, with the verdict `pass`, `fail` or `inconclusive` according to the rules above.
