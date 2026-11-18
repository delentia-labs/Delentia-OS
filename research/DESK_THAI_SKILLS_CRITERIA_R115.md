# Thai Desk, the Skills page (2026-11-18): criteria written before the change

## Measurement before (free, real browser, built Desk of commit e4ee857b, a real `delentia serve` on a throw-away data folder, `apps/gui/scripts/a11y-e2e.mjs --langs th --widths 1280 --th-coverage --gateway ...`)
English-only text in the Thai interface (visible text nodes with two or more English words and no Thai letter), 29 pages: **114** in total. Without a running agent 2 (the pages then show their "cannot reach the agent" states). With the agent: `/skills` 60, `/algorithms` 43, `/chat` 4, and one each on `/sovereignty`, `/learning`, `/hooks`, `/governance`, `/forge`, `/cron`, `/audit` (code samples and log lines that are meant to stay in English). 103 of the 114 (90%) are on two pages.
What the 60 of `/skills` are: for each of the 20 bundled starter skills the title (the `problem_statement` the server sends, an English sentence), the origin line "written by people and shipped with the runtime, not learned" and the statistics line "reuse: ... worked / ... did not of ... reliability ... solved ...×", the last two written in the page code, not by the server.

## Change
1. `apps/gui/src/app/skills/page.tsx`: the origin line (three variants) and the statistics line go through the page's own `L(en, th)` helper; the title goes through `serverText(...)`.
2. `apps/gui/src/lib/server-text-th.ts`: Thai text for the 20 bundled starter `problem_statement` sentences (exact match; a sentence with no entry is shown as the server wrote it, as for every other server sentence).
3. A test that reads the 20 sentences from `rct_control_plane/starter_skills.py` and fails if any lacks a Thai entry (so a new starter skill cannot ship untranslated), and that the English interface returns each sentence unchanged.
Not translated, on purpose: the 41 algorithm names and descriptions on `/algorithms` (names of methods; the page keeps them), code samples, audit log lines, model names, tool names, file names, `SKILL.md`, `TODO`, `FIXME`, `URL`, `markdown`, `json`.

## Rules, written before the change
T1 Measured again in the same way (same command, a fresh throw-away agent, the Desk rebuilt from the change): `/skills` English-only at most 5 (before: 60) and the total over 29 pages at most 55 (before: 114).
T2 Every one of the 20 starter sentences has a Thai entry (the test); the English text is returned unchanged for the English interface (the test).
T3 The axe check of the same script reports no violation and no sideways scroll for the Thai and the English interface on every page (as before the change).
T4 The node unit tests of `apps/gui` pass (`npm test`), `tsc --noEmit` and ESLint are clean.
T5 The translations are listed in the pull request and are NOT merged until the Architect (a Thai speaker; the author is not a native speaker) has read them and said so. Technical words stay in English where a Thai developer would write them in English.
T6 What the change does not claim: that the whole Desk is Thai. The measurement above says how much English-only text is left, per page.

## Not changed
No API, no server text, no behaviour; the English interface shows exactly what it showed.
