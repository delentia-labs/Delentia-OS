# Candidate E1 (embedding add-on) on the holdout (2026-11-16; free, local bge-m3, run once with the setting chosen on the development sentences)

Criteria: `research/THAI_TOOL_MENU_AMENDMENT_2_R115.md` (written before the run). Grid on the development sentences and the first negative set: `embed_e1_grid_development.json`. Chosen setting (rule in the amendment): m = 4, tau = 0.50 (the only setting that keeps the first negative set at 1.00 external tool per request; its development share was 39.5%). Holdout report: `embed_e1_holdout_report.json`.

| holdout (89 sentences) | today | E1 | mean menu today -> E1 |
|---|---|---|---|
| all needed tools in the menu | 0.0% | **44.9%** | 9.01 -> 11.30 |
| literal wording | 0.0% | 81.0% | |
| synonym wording | 0.0% | 39.6% | |
| indirect wording | 0.0% | 20.0% | |

Second negative set: external tools per request today 0.4, E1 1.45. Guards unchanged. Median extra time per Thai request 43 ms (tool vectors cached).

Adoption rule: share >= 70% **FAIL** (44.9%), gain >= 40 points pass, menu growth <= 3 pass (+2.29), negatives <= 1 **FAIL** (1.45), guards pass, time <= 150 ms pass. **E1 is not proposed.** Cosine between a Thai request and an English tool description does not separate 'about this server' from 'about something else' well enough: the settings that keep false additions low lose most of the true ones. It was run only as an add-on of at most 4 tools; the code is not in the runtime.

Limit stated before the run: I had read T1's list of misses on these 89 sentences; no E1 parameter was chosen from them.
