# Thai table T1 on the holdout (2026-11-16; free, offline, run once on the frozen table)

Script `research/tool_menu_thai_eval_r115.py --holdout research/tool_menu_owner_holdout_r115.json`; table frozen at commit d18ab572; raw report `thai_table_t1_holdout_report.json`.

| set | sentences | all needed tools in the menu: today | T1 | mean menu today -> T1 |
|---|---|---|---|---|
| development (seen) | 119 | 0.0% | 67.2% | 8.18 -> 10.23 |
| HOLDOUT | 89 | 0.0% | 66.3% | 9.01 -> 10.61 |
| holdout, literal wording | 21 | 0.0% | 95.2% | |
| holdout, synonym wording | 48 | 0.0% | 68.8% | |
| holdout, indirect wording | 20 | 0.0% | 30.0% | |

Second negative set (20 Thai requests that need no external tool): external tools in the menu per request, today 0.4, T1 1.65.
Guards: 44 English external goals 95.5% -> 95.5%; built-in dev 100% -> 100%; built-in holdout 96.8% -> 96.8%.

Adoption rule (written before the run): share >= 70% **FAIL** (66.3%), gain >= 40 points pass (+66.3), menu growth <= 3 pass (+1.6), negatives <= 1 external **FAIL** (1.65), guards pass. **T1 is not proposed for adoption.** It stays in the code behind `DELENTIA_TOOL_MENU_THAI`, off.
