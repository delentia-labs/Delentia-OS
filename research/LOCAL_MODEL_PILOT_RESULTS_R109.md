# Local model pilot and the iGPU test: results (Round 109, 2026-11-03)

Rules: `LOCAL_MODEL_PILOT_CRITERIA_R109.md`, committed before the first run. Raw files (not in the repository): `C:\Users\whale\daaes-results\lm_pilot\`. One machine (AMD Ryzen AI Z2 Extreme, 8 cores, 19.6 GB visible, Radeon 890M integrated), Ollama 0.40.13, five goals of `scripts/real_model_tool_probe.py`, one run per goal, the runtime's defaults for a local model. **A small sample on one machine, not a ranking.**

## 1. The probe on CPU (the pilot as registered)
| model | goals completed | time per goal | memory loaded (`ollama ps`) |
|---|---|---|---|
| qwen3:8b (reference) | 2 of 5 | 33-183 s | 5.9 GB |
| qwen3:4b | 4 of 5 | 36-441 s (one goal ended in a model error) | 3.2 GB |
| bonsai-2:4b | 4 of 5 | 35-112 s | 1.7 GB |
| bonsai-2:9b | 1 of 5 | 151-281 s, two goals ended in a model error | 3.1 GB |

Against the written rules: no model is "usable to try" (at least 4 of 5, no goal ended by the time limit, median goal under 150 s). `qwen3:4b` and `bonsai-2:4b` reach 4 of 5 but `qwen3:4b` has goals of 293 s and 441 s and its median is above 100 s; `bonsai-2:4b` has a median of 95 s and no goal ended by the time limit: **it meets the numbers of the rule** and misses only the goal that needs a tool call ("remember": it answered without calling the tool). With n = 5 and one run this is described as "mixed"; the rule's wording says differences of one goal are not called differences. `bonsai-2:9b` (1 of 5) is "not usable here" by the rule (at most 2 of 5). Nothing is ranked.

The same model moved a lot between runs: qwen3:8b completed 4 of 5 on the same goals on an earlier day and 2 of 5 today; the iGPU run below gives 2 of 5 again for it. **The completed-goal counts are not stable enough to say which model is better.**

## 2. Is the speed the hardware? (the iGPU test, approved by the owner)
Ollama found the Radeon 890M and dropped it on purpose (`dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1`, read in its own log), so everything above ran on the CPU (`100% CPU`). A second Ollama was started for the test only with `OLLAMA_IGPU_ENABLE=1` on another port (nothing permanent was changed; the owner's Ollama was not touched; the test server was stopped afterwards). Its log shows all 37 of 37 layers offloaded and `ollama ps` shows the model fully in "VRAM" (shared memory).

Direct test, the same model and a 1,700-token prompt, three rounds each, alternating, a unique first line per call (**the first version of this test reported 30,000 prompt tokens a second: Ollama's cache served the prompt; that run is kept as invalid and these are the corrected numbers**):

| model | prompt read, tokens/s | generation, tokens/s | time per request |
|---|---|---|---|
| qwen3:4b CPU only | 89-108 | 14-18 | 19-23 s |
| qwen3:4b iGPU | 667-716 | 20.6 | 5.1-5.2 s |
| qwen3:8b CPU only | 45-65 | 11 | 29-40 s |
| qwen3:8b iGPU | 354-361 | 14 | 6.5-7.2 s |

Reading the prompt is 6-8 times faster; generating is 15-40% faster (it is limited by memory bandwidth, which the iGPU shares with the CPU).

**In the real probe (the same five goals, iGPU on)** the gain is smaller than the direct test suggests: qwen3:8b took 7.0 minutes in total against 10.1 on the CPU (per goal 21-149 s against 33-183 s, about 25-45% less) and completed 2 of 5 again; qwen3:4b completed 3 of 5 (against 4 of 5) with goals of 73-331 s. Why: an episode spends most of its time generating (a qwen3 model writes a long chain of thought before it answers), and generation gained only 15-40%. The cause of the long goals (thinking tokens) was not isolated in this test.

## What this shows and does not show
* Shown (one machine): the iGPU can be used by Ollama on this chip with one setting; prompt reading is several times faster; a real episode is about a third faster; the number of goals completed did not change beyond the noise.
* Not shown: that it is stable over hours; the effect on other computers; what it does with thinking switched off (the likely next saving, not measured); whether the answers are as correct on harder tasks (only the five goals and one question were checked).
* The speed problem on this computer is mostly the hardware and a setting (the iGPU was off), and in part a software matter (thinking tokens); the wrong answers are the models' own and were not helped by speed.
* Nothing here is a recommendation of a model for Delentia. The Desk therefore recommends none.
