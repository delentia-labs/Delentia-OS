# How the system thinks: one real task, step by step (a draft for review, not yet published)

You do not need to read code for this page. It follows what Delentia does with one instruction, using a result that was **really run on 7 November 2026**, not a mock-up. You can repeat it in five minutes with no AI model and no cost:

```bash
delentia demo init --lang en
delentia demo run compare --scripted
delentia demo status
```

**Read this first:** the demo uses a *script* in place of the AI model: the order of the steps and the wording of the answer were written in advance. What is **real** is the tools, the files, the safety gate, the wait for a signature and the record you can check afterwards.
So this page teaches what the system *around* a model does. It says nothing about how clever any model is (that has not yet been measured with a strong online model).

## The task

> Read the quotes in `quotes/vendor_a.md`, `vendor_b.md`, `vendor_c.md`, build a price comparison table, then say which vendors are within the 15,000 USD budget. Do not edit the original files and do not send any data out.

Three things are mixed in one sentence: the work (read, compare, answer), a limit (the 15,000 budget) and a prohibition (do not edit, do not send out).

## The picture: every task passes these eight steps

```
check at the door -> think as a plan -> choose fast or slow path -> act (one step at a time, each through the gate)
      -> shorten long data -> check the answer against the request -> write an unalterable record -> learn only what was checked
```

### 1. Check at the door (GUARD)
Before anything happens the instruction is read for signs of a trick (for example "forget your earlier instructions"). Nothing was found here, so the task went on.

### 2. Think as a plan (THINK, RCT-7)
The instruction is split into seven steps in the RCT-7 style. The real output for this task:

| Step | What the system produced |
|---|---|
| 1 Observation | picked up the whole instruction |
| 2 Analyze | task type = look-up/read (QUERY), scope = file |
| 3 Deconstruct | found 1 constraint: `COSTLTE0.0` |
| 4 Reverse Think | risk level = SYSTEMIC |
| 5 Identify Core Intent | validation passed, no warning |
| 6 Rebuild | compiled, priority = medium |
| 7 Verify | proof code `CRYSTAL-HASH-a2d9e8cec8db102e` |

**Said plainly:** two rows are **misread or coarse**.
- Row 3: "15,000 USD budget" became the constraint `COSTLTE0.0` (cost at most 0.0), which is not what the person wrote.
- Row 4: a read-only task was classed at the highest risk level (probably because of the words "send data out" in the prohibition).

This splitter works by rules, not by a model: fast and explainable, but coarse. Nothing here made a wrong *safety* decision in this task (it erred on the careful side), but it shows that **RCT-7 as coded today is not deep reasoning**, and there is no measurement yet that it makes answers better.

### 3. Choose the fast or the slow path (ROUTE)
Simple reads get the fast path (fewer steps allowed); complicated work gets the slow one.

### 4. Act one step at a time, each through the gate (ACT)
Three steps: read file A, read file B, read file C, then answer. Every step was judged by the FDIA gate:

> `delentia_read_repo_file`: D=0.6 I=1.5 A=1.0 -> F=0.4648 (threshold 0.5) -> **passed** (a read your policy allows, so the D/I threshold is not applied to reads)

How to read it: D is the data behind the request, I is how clear and demanding the intent is, A is the human owner's permission. If A = 0 the result is 0, always (no accountable owner, nothing happens). A read is allowed outright;
an instruction to *edit* a file stops and waits for your signature (try `delentia demo run edit --scripted`).

### 5. Text from outside means be careful (TAINT)
The quote files sit in a folder declared untrusted, so the system noted:

> this task read text from outside -> from now on **anything that sends data out or changes something needs a person's signature**

This rule does not depend on whether the model is clever or fooled. If a quote contained a hidden sentence telling the model to edit a file, the model might believe it; the system would still not allow it without a signature (try `delentia demo run injection --scripted`).

### 6. Shorten long data (COMPRESS)
If a tool returns very long text (over 6,000 characters) the system shortens it to what matters for the request and keeps the original so it can be recovered. These files are short, so nothing was shortened.

### 7. Check the answer against the request (VERIFY)
The answer: a table sorted by price with the summary that Harbor HVAC (9,900 USD) is the lowest price within the budget. The demo checks it with **its own checker, not the model's**:
- passed: the table has the price of all 3 quotes
- passed: says Harbor HVAC and Northwind Cooling are within budget
- passed: does not say Polar Systems (over budget) is within budget
- passed: the original files were not changed

**One more plain statement:** the runtime's own condition reader (not the demo's) did **not** turn the sentence "do not edit the original files" into a checkable condition for this task (its list of conditions was empty). The checks above come from the demo's checker.
So a gap remains between "the person wrote a prohibition" and "the system checks that prohibition by itself every time".

### 8. Write an unalterable record (RECORD)
Every step was written to a chained, signed record: **11 rows, 11 signed, chain intact**. If someone edits an old row the chain breaks and it is detected.
(Someone holding the key who rewrites the whole chain needs an outside witness to be caught; that is configured separately.)

### 9. Learn (LEARN)
The system learns a "skill" only from tasks that were checked and never read outside text. This task read outside text, so it was **not learned from**: slow on purpose, so it cannot learn something that was planted.

## Summary for a non-coder

| The question to ask any system | What Delentia answers with | How you can check |
|---|---|---|
| What did it do? | a list of steps, tool names and the data sent | the "What the agent did" part of the result |
| Who allowed it? | the FDIA gate and your signature | the gate part, and the approvals page |
| What if it read something strange? | a signature is needed before anything changes the outside world | the injection demo |
| How do I know nobody edited the record? | the signed chain | `delentia demo status` |
| Does the answer match the request? | a checker separate from the doer | the "answer checked" part |

## What this page does **not** say
- It does not say how well any online model does this task (never measured).
- It does not say RCT-7 improves answers (no measurement yet, and the splitter today is coarse: see step 2).
- It is not a security certification. It only lets you **see** how the mechanisms work.

Every result on this page comes from one run of the demo on commit `4c1e653f` on 7 November 2026, on the developer's Windows computer.
