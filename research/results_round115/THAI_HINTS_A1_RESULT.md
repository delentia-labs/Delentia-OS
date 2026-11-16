# Candidate A1 (Thai hints for external tools, written once by a local model) (2026-11-16; free, offline once the hints exist)

Criteria: `research/THAI_TOOL_MENU_AMENDMENT_3_R115.md` and its note 1. Hints: `research/tool_hints_th_synthetic_r115.json` (prompt v2, qwen3:8b, thinking off, temperature 0, output cap 400 tokens; slowest tool 12.3 s, median 8.6 s, so rule 6 holds; prompt v1 hints are kept in `..._prompt_v1.json`). Reports: `thai_hints_a1_prompt_v2_report.json` (v2) and the v1 run printed in the amendment note.

| | all needed tools in the menu: today | A1 prompt v1 | A1 prompt v2 | external tools pulled into a Thai request that needs none (rule: at most 1) |
|---|---|---|---|---|
| development (119, seen) | 0.0% | 42.9% | **41.2%** | v1 3.4 / v2 3.15 (first negative set) |
| second form (89, seen by T1 and E1) | 0.0% | 47.2% | **43.8%** | v1 3.2 / v2 **3.15** (third negative set) |

Guards unchanged (44 English goals 95.5%, built-in dev 100%, built-in holdout 96.8%).

**Stop rule (written before the regeneration): build the third form only if the second form reaches 60% and the third negative set pulls at most 1.5 external tools per request. Neither holds (43.8%, 3.15), so the third form was not built and A1 is not proposed.** The one allowed prompt change did not help (v2 slightly lower than v1 on both sets).

Reading: the hints themselves are sensible (for example read_note gets 'อ่านโน้ตชื่อโน้ต ...', delete_note 'ลบโน้ตชื่อนี้ ...') but the model translates 'event' literally ('เหตุการณ์'), 'ticket' as 'บัตร' or 'ตั๋ว' or 'ตั๊กเก็ต' and spreads each tool over several near-synonyms, and the Thai trigram score used for built-in hints has no IDF, so common trigrams of those hints score for many tools at once. A different score (word level with IDF) would be a different candidate with its own criteria and a fresh holdout.
