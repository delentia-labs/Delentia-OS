# Autonomy modes v0.1 (`strict` / `flow`) and the Desk switch (Round 117, 2026-11-27): criteria written before any code

**Purpose.** A person should be able to choose how much the agent may do on its own with one action: a word on the command line, a slash command in chat, or one press of a button in the Desk. v0.1 has two modes. `flow` (the default) is today's behaviour, unchanged. `strict` adds a layer that makes the gate ask more often. Neither mode can make the runtime ask less than it does today. The faster mode (`turbo`, a session lease, an isolated worktree merged back under a signature) is a later stage with its own criteria. It is **not** part of this file.

**Where it starts from (read from the code at `a60619d`).**
* The policy presets already exist (`fdia_policy.template`: `argaware` (the default), `careful`, `balanced`, `strict`, `planfirst`). The loop already takes the stricter of the owner's policy and the built-in floor. The Desk already saves a policy behind a signature gate (`desk_api._signature_gate`).
* Missing: a per-person mode, a way to combine two policies, a control in the Desk, `/mode`, and an audit record of the mode.
* The Desk already uses the word "mode" twice: Agent/Chat in the composer and Simple/Advanced in the sidebar. The new setting is therefore called **autonomy** in the API and the code, **Guard** in the English interface, and **การคุม** in the Thai interface. The CLI keeps `--mode` because that is the word the plan uses, with `--autonomy` as an alias.

**Standing constraints (they hold for every part below).**
* S1 A mode only tightens. In every mode, the built-in floor, the taint rule (Round 58), the answer guard, the egress rule, secret paths, forbidden patterns and Zero-Delete stay exactly as they are.
* S2 The model cannot change the mode: no tool writes it, and text the model reads cannot change it.
* S3 Research mode is not affected. With `DELENTIA_RESEARCH_MODE=1` and no explicit mode, the gate decides exactly as it does today, so no arm of a study is confounded.
* S4 Every value the Desk shows comes from the API. No mode lives only in the browser.
* S5 No sentence about speed, or about fewer approvals, is published from this stage.

---

## Decisions the Architect makes before any code (each one recorded here by a dated note)

* **M-D1: `strict` and the jury.** The `strict` template asks the tier-4 jury before a shell command. On a machine with no jury configured, `_jury_gate` refuses, so in `strict` every shell command would be refused outright.
  * **(a) Recommended:** the strict layer keeps the jury requirement only when a jury is configured. Otherwise it asks for a signature only, and the Desk says "no jury configured: signature only".
  * **(b)** As the template is: no jury means no shell in `strict`.
* **M-D2: what `flow` is.**
  * **(a) Recommended:** exactly today's effective policy (the owner's file, else the default starter, else none). Zero behaviour change.
  * **(b)** `flow` = `planfirst`. Rejected for v0.1: `small_edit_autorun` loosens `argaware`, and Round 101 makes `planfirst` something written into a signed file, never a default.
* **M-D3: who a mode belongs to.**
  * **(a) Recommended:** one stored mode per person (namespace), server-side, plus a per-run override that can only tighten.
  * **(b)** One mode for the whole host.
* **M-D4: when it reaches main.** The PL1 stop rule holds until U0b has a verdict.
  * **(a) Recommended:** the code may be written and reviewed now, and is merged after U0b's verdict. R1 below proves `flow` identical, so later PL1 stages are not changed by it.
  * **(b)** Merge as soon as R1 passes.
* **M-D5: the Thai words.** Proposed: "การคุม: เข้มงวด" and "การคุม: ลื่นไหล". The author is not a native speaker, so the Architect decides (as T5 of `DESK_THAI_SKILLS_CRITERIA_R115.md`).

---

## Part A: what a mode is (runtime)

A1 There are two values, `flow` and `strict`. `autonomy_mode` is stored per namespace in the control-plane state, with who set it (`owner`, `self`, `env`), from where (`desk`, `cli`, `chat`, `api`) and when. Unset means `flow`. `DELENTIA_AUTONOMY_MODE` sets the default for namespaces that have no stored value (jobs, cron, webhooks, subagents inherit the mode of the namespace that owns them). An unreadable value falls back to `strict`, never to `flow`.

A2 `flow`: the gate is unchanged. Same policy source, same decision, same rule id, same reason. The only additions are the mode fields of Part D.

A3 `strict`: a second policy, the *strict layer*, is evaluated next to the effective policy. It is built by `fdia_policy.template("strict", tool_names)` over the real tool names, with the jury handled as M-D1 decides. A new function `fdia_policy.combine_strictest(a, b)` returns one `Evaluation`:
* A = the minimum of the two A values;
* `needs_signature` = true if either needs one;
* `required_signatures` = the maximum;
* `approver_roles` = the union of both;
* `jury_tier` = the higher tier;
* blocked if either policy blocks;
* `rule_id` names the stricter rule, and `decided_by` is `owner_policy`, `strict_layer` or `both`.

With no effective policy (source `none`), the strict layer is combined with the built-in floor alone.

A4 In `strict`, the owner policy's `plan_first` and `small_edit_autorun` do not apply. Each action is signed on its own. This only tightens.

A5 Monotonicity. For every tool, argument set, taint state, principal and owner policy, the severity in `strict` is at least the severity in `flow`. Severity runs from ALLOW, to CONDITIONAL, to signature required, to jury required, to blocked.

A6 Timing.
* A switch to `strict` takes effect at the **next tool call** of every running episode of that namespace, because the gate reads the mode on every call.
* A switch to `flow` takes effect from the **next episode**. A running episode that has seen `strict` stays `strict` until it ends.

A7 Resume. A continuation after an approval, or after a crash, is judged under the mode in force at the time of the resume, together with A6. The signature satisfies a signature requirement. It does not satisfy a jury or a block that the strict layer adds.

A8 Research mode: see S3. An explicitly set `DELENTIA_AUTONOMY_MODE` in research mode is applied and recorded in the run's config, so it can never be silent.

---

## Part B: how a person chooses (CLI, chat, API)

B1 CLI.
* `delentia agent --mode strict|flow GOAL` applies to that one run and is not stored. `--mode flow` cannot lift a stored `strict`: the stricter mode wins, and the report says so.
* `delentia mode show` and `delentia mode set strict|flow [--namespace NS]` store the mode.
* `delentia demo run <name> --mode strict` is the same for the demo.
* `--autonomy` is an alias of `--mode`.

B2 Chat channels.
* `/mode` shows the mode and who set it.
* `/mode strict` is allowed for anyone, on their own namespace.
* `/mode flow` lifts only a `strict` the same person set (`self`). A `strict` set by the owner can be lifted only from the owner's namespaces (CLI, Desk, MCP client).
* The answer is one line in the person's language.
* `/mode` is added to `chat_commands.COMMANDS` and to `/help`.

B3 HTTP.
* `GET /v1/desk/autonomy` returns `{mode, set_by, source, at, modes: {flow: {...}, strict: {...}}}`. Each entry of `modes` lists what runs on its own, what asks for a signature and what is never allowed. These lists are taken from the rule descriptions of the policy as combined (A3), not from text written in the page.
* `PUT /v1/desk/autonomy {mode}` has the same authentication as the other Desk routes.
* The stream (`/v1/kernel/stream`) takes an optional `autonomy` per request, which may only tighten (as B1).

B4 There is no tool for the mode: a test fails if any registered tool writes `autonomy_mode`. A goal, a page or a file that contains `/mode flow` is text and changes nothing.

---

## Part C: the Desk switch (UI)

### C0 What is borrowed, and from where

| Product (standard practice) | The pattern | What Delentia takes | What it does not take |
|---|---|---|---|
| Claude Code (terminal) | The permission mode is cycled with Shift+Tab and shown on the line under the prompt the whole time | A **status chip that is always visible** next to the input, and one key that cycles the mode | Shift+Tab itself: in the browser and in the Textual TUI (`rct_control_plane/tui/chat_app.py`) it moves focus back, and taking it would break keyboard and screen-reader use |
| VS Code Copilot Chat / Cursor | The mode picker (Ask / Edit / Agent) sits **inside the composer**, where the request is typed | The control sits in the composer next to Agent/Chat, because the choice is made per request | A drop-down: two options are faster as a visible segmented control |
| OpenAI Codex CLI `/approvals` | A slash command opens a short list; each choice has one sentence on what it allows | `/mode` in chat and the CLI; **one sentence per mode** in every surface | A third level that turns approvals off: v0.1 has no such level |
| Firefox Enhanced Tracking Protection (Standard / Strict / Custom); Edge tracking prevention (Basic / Balanced / Strict) | **Radio cards**, each with a short list of what it blocks; Strict warns that some things may stop working; a shield sits where the person is working | The **settings cards** (C6), the "what will ask" list on each card, and the honest warning that `strict` asks more often | Per-site exceptions (not in v0.1) |
| Apple Lockdown Mode | The maximum-protection mode is opt-in, explained plainly, and the system says when it has limited something | When `strict` adds a signature, the approval card says **"asked because Guard is strict"** | A restart to switch (switching here is instant) |
| Apple HIG segmented control; Material 3 segmented buttons | 2 to 5 mutually exclusive choices, all visible at once, the selected one filled | The **segmented control** in the composer | Icons without text |
| WAI-ARIA APG radio group | `role="radiogroup"`, arrow keys move the choice, one tab stop | The keyboard model and the ARIA roles | – |
| WCAG 2.2 1.4.1 (use of colour), 1.4.3 (contrast) | State is never shown by colour alone | The **label and icon always appear**, colour only supports them | – |

### C1 The composer switch (the main control)

The switch is a two-segment radio group in the composer, to the left of the existing Agent/Chat choice. It is visible on every width from `lg` up.

```text
┌───────────────────────────────────────────────────────────────────────┐
│ พิมพ์คำขอ…                                                            │
├───────────────────────────────────────────────────────────────────────┤
│ การคุม  [ ~ ลื่นไหล ][ ⛨ เข้มงวด ]   เอเจนต์ ▾    ไม่เกิน 5 ขั้น   ส่ง ⏎ │
└───────────────────────────────────────────────────────────────────────┘
  พร้อม · qwen2.5:7b (ollama) · เอเจนต์ · ⛨ การคุม: เข้มงวด · F 0.91
```

* One click switches. No dialog: going from `flow` to `strict` only tightens, and going back to `flow` returns to the owner's own baseline, never below it.
* In Chat mode (no tools) the switch is shown disabled with the note "ใช้กับโหมดเอเจนต์" / "applies in Agent mode". It is not hidden, so the place does not move.
* The switch is disabled when the API cannot be reached, and the chip then shows "-" (S4).

### C2 The status chip

The status line (`statusParts` in `DeskChat.tsx`) gains `⛨ การคุม: เข้มงวด` or `~ การคุม: ลื่นไหล`. The sidebar System block shows the same chip. Both read the value from `GET /v1/desk/autonomy` and refresh when it changes, the way `useDeskMode` already refreshes.

### C3 "What does this mean?"

A small `?` next to the switch opens a popover. It shows two columns, *runs on its own* and *asks you first*, filled from `modes` in B3 (the real policy, never text written in the page), with a link to `/fdia` for the details. Its first line says: "ทั้งสองโหมด: อ่านข้อมูลภายนอกแล้ว ทุกการกระทำที่มีผลต้องมีลายเซ็นเสมอ" / "In both modes, once outside text has been read, every action with an effect needs a signature."

### C4 Feedback after a switch

An inline notice under the composer, with Undo for 10 seconds:
* To `strict`: "เข้มงวดแล้ว: มีผลตั้งแต่คำสั่งถัดไป" / "Strict: applies from the next action".
* To `flow` while an episode runs: "ลื่นไหล: มีผลตั้งแต่คำขอถัดไป งานที่กำลังทำยังเข้มงวดจนจบ" / "Flow from your next request; the current one stays strict" (A6).

The stream shows a "Guard changed" row at the point where the change happened.

### C5 Keyboard

* Alt+Shift+G toggles from anywhere in the chat (the `title` shows it, as Ctrl/Cmd+J does for the Inspector).
* Inside the group, arrow keys move the choice; the group is a single tab stop.
* No shortcut overrides a browser or screen-reader key.
* In the TUI, Ctrl+G cycles the two modes. It is added to `BINDINGS` next to Ctrl+S and Ctrl+T, and the footer shows it. Shift+Tab is left to Textual's focus movement.

### C6 Settings: the default per person and per channel

A Settings section, "การคุมเริ่มต้น / Default guard", shows two radio cards (the Firefox/Edge pattern). Each card has its one sentence and its three-line "asks you first" summary. Under them is one row per chat channel with its own default, and for every value who set it and when.

```text
( ) ~ ลื่นไหล (ค่าเริ่มต้น)            (•) ⛨ เข้มงวด
    ทำงานในโปรเจกต์ได้คล่อง               ทุกการเขียน/รันคำสั่งขออนุมัติทีละครั้ง
    ถามเมื่อเขียนไฟล์ รันคำสั่งที่ไม่ใช่การดู   รวมคำสั่ง shell แบบดูอย่างเดียว ค้นเว็บ เปิด URL
    ออกเน็ต หรือหลังอ่านข้อมูลภายนอก        อาจถามบ่อยขึ้น: เหมาะกับงานไฟล์แปลกหน้า
```

### C7 Where the mode appears afterwards

* Each approval card shows the mode the action was asked under, and "asked because Guard is strict" when the strict layer decided (`decided_by`).
* The session page and the Cycle strip show the mode at the start of the episode and every change during it.

### C8 Narrow screens (below `lg`)

The switch collapses to one button that shows the current mode. A press opens a bottom sheet with the two cards of C6. There is no sideways scroll at any width tested by `a11y-e2e.mjs`.

### C9 Colour and type

There are no new tokens.
* `strict` uses a pine (`dl-pine`) fill with a shield icon and a label.
* `flow` uses an outline with a label.
* Amber stays "waiting for a person" and rust stays "blocked or broken". Neither is used for a mode, so their meanings are kept.
* Text is Prompt for Thai and JetBrains Mono for English, as in `DESIGN.md`.
* Contrast is WCAG AA.

### C10 What the Desk does not show

* `turbo` does not appear, not even as a disabled placeholder (nothing is simulated).
* There are no per-tool toggles in v0.1; the policy editor on `/fdia` already does that.

---

## Part D: the record

D1 Every change of mode is an audit row `autonomy_mode_changed`: `{namespace, from, to, set_by, source, at}`. It sits in the hash chain like every other row.

D2 The start row of every episode has `autonomy_mode`. Every gate decision has `mode` and `decided_by`.

D3 The session report, `delentia demo status` and the Desk session page show a line with the mode.

---

## Rules, written before any code (all free: scripted models, no key)

R1 **`flow` changes nothing.**
* The whole existing test suite and `test_gate_properties_round65_real.py` pass unchanged.
* A corpus of gate decisions is recorded at `a60619d` and again at the change, and is identical in decision, rule id and reason (the new fields are ignored). The corpus covers the scripted demo (`compare`, `edit`, `approve`, `injection`), `scripts/measure_injection_defence.py` (23 scenarios, 3 multi-turn, 8 answer leaks, 4 legitimate answers, 6 legitimate workflows) and the benchmark rehearsal.

R2 **Monotonic.** A property test (hypothesis) over tools × arguments × taint × principal × owner policy (none, each starter, two hand-written files): severity in `strict` ≥ severity in `flow`, and `combine_strictest` is commutative and never returns a weaker verdict than either input.

R3 **Attacks under `strict`.** `measure_injection_defence.py` with a new option `--autonomy strict` (default `flow`, which is the run of R1):
* 0 harmful side effects in the 23 scenarios, 0 in the 3 multi-turn scenarios and 0 of the 8 answer leaks (the same as `flow`);
* the 4 legitimate answers keep their addresses;
* with the script's signer approving, the 6 legitimate workflows complete.

R4 **Friction (descriptive, not a rule, nothing claimed from it).** The number of signature stops per scenario under `flow` and under `strict` is reported in a table.

R5 **Timing (A6, A7).** Tests show that:
* a switch to `strict` in the middle of an episode makes the next risky call be judged by the strict layer;
* a switch to `flow` in the middle of an episode leaves that episode `strict`;
* a continuation after an approval is judged again under the current mode, and a signature does not satisfy a jury that the strict layer added.

R6 **Authority (B2, B3, B4).**
* A chat person cannot lift a `strict` the owner set.
* `autonomy: flow` on the stream cannot lift a stored `strict`.
* No tool writes `autonomy_mode`.
* `PUT /v1/desk/autonomy` without the Desk's authentication is refused.
* An unreadable stored value reads as `strict`.

R7 **Research mode (S3).** With `DELENTIA_RESEARCH_MODE=1` and no explicit mode, the scripted TC-003 `d0`/`b0s` arms and the rehearsal give the same results as at `a60619d`.

R8 **The record (D1, D2).** After 20 switches from four sources, every row is present and the chain verifies (`delentia demo status`: intact).

R9 **The Desk.**
* `apps/gui/scripts/a11y-e2e.mjs` in both languages and at every width: no axe violation and no sideways scroll.
* The keyboard walk reaches the switch and operates it with the arrow keys and with Alt+Shift+G.
* A Playwright test with a real `delentia serve` and a scripted model: one click on `strict`, then `GET /v1/desk/autonomy` returns `strict`, then the next risky call of a scripted episode waits for a signature with "asked because Guard is strict"; one click back gives `flow`, and an audit row exists for both changes.
* With the API stopped, the switch is disabled and the chip shows "-".
* `npm test`, `tsc --noEmit` and ESLint are clean.

R10 **Words.** The Thai and English text of C1 to C8 is listed in the pull request and is not merged until the Architect has read it (M-D5).

R11 **Claims.** README and `docs/reference/runtime-features.md` gain one paragraph:
* what the two modes do;
* that `flow` is the earlier behaviour;
* that `strict` asks more often and protects nothing that `flow` leaves open against outside text (the taint rule is the same in both).

No number about speed or approvals appears.

---

## Not in v0.1

`turbo`, a session lease, an isolated worktree merged back under a signature, `planfirst` as a mode, any mode that asks less than today, per-tool switches in the Desk, any paid run. Each needs its own criteria file, written before its code. A lease additionally needs its own entry in `research/GATE_PROPERTIES.md` and adversarial tests.

## Done when

1. M-D1 to M-D5 are recorded here by dated notes.
2. Parts A to D are implemented, and R1, R2, R3, R5 to R9 pass in CI.
3. R4's table and R10's review are in the pull request.
4. The pull request is merged no earlier than M-D4 allows.

Nothing is claimed from this stage: it produces a control, not a result.
