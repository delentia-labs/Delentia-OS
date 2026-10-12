# Round 72 criteria (written BEFORE research/replaces_r72.py was run)

## 1. `replaces` (the person names the memory a new one replaces) and the hint that proposes it
Data: set H3 of research/recall_dataset_r69.py (20 old/new pairs; the new text announces the change), the 160 distractors of H1 and the 40 facts of H1 (all frozen, SHA-256 in recall_dataset_r69.sha256).
Real objects: AgentMemory + ControlPlanePersistence in a temporary home, recall without embeddings (the lexical path, which needs no model). `--embed` repeats it with the local embedding model when Ollama is up.

A. Staleness. Store the 20 old texts, the distractors, then the 20 new texts (a) as plain stores, (b) with `replace`. For each question ("What is the current X?") report: top-1 is the newer value, the older value is in the top 3.
   Pass for (b): the older value is in the top 3 for 0 of 20 questions (it is retired), and the newer value is top-1 for at least as many questions as in (a). This is a property check, not a recall gain: the report says so.
B. The hint. For each new text, before it is stored, `likely_replaced` is asked; "hit" = the old memory is among the 3 hints. For each of the 40 H1 facts (a fresh statement with NO predecessor) "false hint" = any hint is produced.
   Threshold: chosen among {0.20, 0.30, 0.40, 0.50} on DEV = pairs 0-9 and facts 0-19: the highest hit count whose false-hint rate on dev facts is at most 30%; ties -> the higher threshold.
   HOLDOUT = pairs 10-19 and facts 20-39, measured ONCE with that threshold. Pass: hits >= 8 of 10 and false hints <= 6 of 20 (30%).
   If it does not pass the hint stays in the product as a hint (it changes nothing by itself) and the number is reported as it is; the threshold in memory_replace.HINT_THRESHOLD is set to the chosen dev value.
Wilson 95% intervals are reported; with n = 10 and 20 a difference of one item is noise.

## 2. Credential pool (credential_pool.py)
Not a measurement: properties pinned by tests (names only, no value anywhere, rotation on 401/402/403/429, nothing moves on 5xx, audited by label, hidden from the shell). A mutation check (rotation disabled) must fail the rotation tests: done, 7 of 25 fail.

## 3. The user model (rct_control_plane/user_model.py), written BEFORE the detector
What it is: a person's standing preferences about HOW to answer (language, answer length, format, timezone), taken only from the person's own message, proposed as a suggestion and kept only when the person accepts;
once accepted it is shown to every episode as "what this person asked for about how to answer" (never a permission). Nothing is learned from a tool result, a page, a file or an episode that read outside text.
Data: research/user_model_dataset_r72.py, DEV 24 sentences (12 state a preference, 12 do not: tasks, questions, one-off instructions), HOLDOUT 40 (20 / 20), frozen by SHA-256. Labels and sentences are the author's.
Rules were written against DEV only. HOLDOUT is measured ONCE. Pass on HOLDOUT: precision (detections that are right: the facet AND the value) >= 0.90 and recall >= 0.70 on the 20 positives; zero detections on at least 18 of the 20 negatives.
Reported with Wilson 95% intervals; n = 20 means one sentence moves a rate by 5 points.
Not measured here (needs a capable model and users): whether answering in the person's language / length / format makes the person's work better. The test is only that the right statement becomes the right suggestion.
Properties pinned by tests: an episode that read outside text proposes nothing; a sentence that looks like a secret proposes nothing; a facet is a memory of the person (sealed, revocable, replaceable, erased with the person); the rendered block is at most 500 characters
and only the fixed vocabulary reaches the prompt (a facet value is never free text, except `name`, which is not a facet here).
