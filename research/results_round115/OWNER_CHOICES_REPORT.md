# Ranked tool menu on the Architect's ticked sentences (2026-11-16; free, offline, no model)

Script `research/tool_menu_owner_choices_r115.py` (committed before the first run), data `research/tool_menu_owner_choices_r115.json` (30 situations confirmed, 119 sentences ticked of 120). Raw report: `tool_menu_owner_choices_report.json`.

| set | sentences | all needed tools in the ranked menu | with rule R1 | mean menu |
|---|---|---|---|---|
| all | 119 | 0.0% | 0.0% | 8.18 |
| literal wording (L) | 30 | 0.0% | 0.0% | 8.77 |
| synonym wording (S) | 60 | 0.0% | 0.0% | 8.02 |
| indirect wording (I) | 29 | 0.0% | 0.0% | 7.90 |

**Pre-registered rule for R1: not met** (gain 0.0 points, needed 10). R1 is not proposed.

**What the zero means (checked with `thai_vs_english_menu_probe.py`):** every one of the 119 sentences is in Thai and the external tools are described in English. The ranker scores a tool by words shared between the goal and the tool's name and description, so a Thai goal shares none: none of the external tools reached the menu for any Thai sentence tried, while the same request in English brings the whole server in (for example 'Read the note about the budget' puts all four note tools and a mail tool in the menu; 'list my events next week' puts all four calendar tools in). The earlier 95.5% on the 44 goals I wrote came from English goals, so it hid this. Since the ranked menu became the default for every provider (2026-11-13), an external tool with an English description is not offered to the model for a Thai request.

What it does not mean: nothing here was run with a model, the tools are synthetic (English descriptions are the usual case, not the only one), and the sentences were written by the assistant (the Architect confirmed the needed actions and ticked what sounds like him). This set is now DEVELOPMENT data for any fix, because it has been seen; a fix needs a fresh set to be judged on.
