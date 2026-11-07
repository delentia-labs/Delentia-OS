# Round 2 criteria for the cut detector: dissolves. Written 2026-11-07 BEFORE the detector was changed for it and before it was run on the roller coaster clip

Round 1 (`REFERENCE_CUTS_CRITERIA_R111.md`) measured hard cuts in the creator's own 2.5D episodes: baseline recall 0.857, precision 0.800 on two unseen clips, and a documented failure on dissolves (the EP04 animatic, which uses dissolves of about half a second, gave 2 shots found of 19).
Round 2 asks one question: can the detector be made to find dissolves WITHOUT losing what it already does on hard cuts? A real clip with a dissolve truth exists: the creator's frame-by-frame breakdown of the reference clip "This Shape Saved Roller Coasters" (63.2 s) lists 19 shots with start and end times, and says in its own words that there is one hard cut and that every other transition is a dissolve of 5 to 8 frames.

## Ground truth
* `episodes/library/REF_BREAKDOWN_roller_coaster_TH.md`, section 3, the table `| # | Time | ...`: the start of shots 2 to 19 are the 18 cuts (1.2, 2.7, 4.0, 7.1, 10.0, 16.1, 19.0, 21.0, 22.3, 28.7, 31.7, 34.1, 35.1, 41.4, 46.2, 52.3, 56.0, 59.6 seconds). The table was made from frame sheets at 6 frames a second and the dissolves last 5 to 8 frames, so a boundary is uncertain by about 0.17 s: the tolerance for this clip is **0.30 s**, stated here and not changed.
* The other breakdowns were read and are NOT used: `REF_BREAKDOWN_second_draw_TH.md` lists beats that overlap in time (rows are not shots); `REF_BREAKDOWN_3d_zackdfilm_TH.md` describes segments from one sample a second.
* EP04 storyboard times (60.5 s) do not match the animatic (63.0 s): they are not ground truth for it. Only the README's statement of 19 shots is used, as a count.

## The split (fixed here)
| Role | Clip | What it is used for |
|---|---|---|
| DEV2 | the roller coaster reference clip (file must be 63.2 s +- 0.5 s) | the 30 candidates below are scored on it |
| GUARD (round 1 clips, hard cuts, tolerance 0.20 s as in round 1) | EP01 v1 + EP02 v3 pooled; EP03 v2 alone | a change must not hurt what already works |
| HOLDOUT2, count only | EP04 animatic (19 shots in its README) | the only dissolve clip never used for choosing |
No setting is chosen on the guard clips or on EP04.

## The search space (fixed here)
The shipped rule is the baseline: window 1, colour jump 30, gap 0.5 s, union with the brightness scene score.
A candidate is a window and two numbers: `window` in {1, 2, 3} samples (the colour difference is taken between a thumbnail and the one `window` samples later, so a dissolve that fills 2 or 3 samples at 10 samples a second shows up as one jump; the cut time is the later sample), `colour_jump` in {12, 16, 20, 25, 30}, `min_gap` in {0.5 s, 1.0 s}, always in union with the scene score; cell fraction and the flash filter stay off. 3 x 5 x 2 = 30 candidates. For `window` 1 the rule is identical to the shipped one.

## Choosing and testing
1. Score the 30 candidates on DEV2 (tolerance 0.30 s). The highest F1 wins; a tie goes to the smaller window, then the jump nearest 30, then the larger gap. The choice is written to a selection file and committed BEFORE the guard clips and EP04 are run with it.
2. Run the baseline and the chosen candidate on the guard clips and EP04, once.

## Pass rules
* **Adopting the chosen candidate as the default:** ALL of: (a) on DEV2 its F1 is at least 0.10 higher than the baseline's; (b) on the guard, pooled EP01 + EP02 recall >= 0.85 and precision >= 0.75 (the round 1 "useful for planning" bar) and EP03 F1 no more than 0.05 below the baseline's; (c) on EP04 the number of shots found is between 15 and 24 (19 +- 25%).
* If any part fails the baseline stays the default and the result is a negative result with the numbers.
* If the baseline itself is below recall 0.5 on DEV2, the documents say the detector does not find dissolves, with the measured number.
* Not claimed whatever the result: accuracy on dissolves in general (one dissolve clip with a truth, one with a count), or on footage that is not animation like this.

## Recording
The measured numbers go into the results register with this file as the criteria.
