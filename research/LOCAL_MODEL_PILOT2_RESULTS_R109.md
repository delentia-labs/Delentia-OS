# Local model pilot 2: results (Round 109, 2026-11-03)

Rules: `LOCAL_MODEL_PILOT2_CRITERIA_R109.md`, committed before the first run. Raw files (not in the repository): `C:\Users\whale\daaes-results\lm_pilot\p2\`. One machine (Ryzen AI Z2 Extreme, Radeon 890M iGPU on through a second Ollama on port 11435), five goals of `scripts/real_model_tool_probe.py`, three rounds per model and setting, 18 probe runs, then a 40-request stability run. **A small sample on one machine.**

## Goals passed (of 5) per round, and median seconds per goal
| model | thinking default | thinking off |
|---|---|---|
| qwen3:4b | 3, 3, 3 (9/15) · median 97-120 s | 1, 1, 1 (3/15) · 20-22 s |
| qwen3:8b | 4, 2, 2 (8/15) · 57-99 s | 1, 1, 1 (3/15) · 16-28 s |
| bonsai-2:4b | 5, 4, 5 (14/15) · 23-27 s | 3, 4, 3 (10/15) · 7-18 s |

## Against the written rules
* Time: thinking off cuts the median goal time by far more than 25% for all three models (about 75-80% for qwen3, about 40-70% for bonsai-2:4b). Rule met.
* Correctness: thinking off lost 6 (qwen3:4b), 5 (qwen3:8b) and 4 (bonsai-2:4b) of 15 goals; the rule's limit is 3. **It costs correctness for all three.** bonsai-2:4b is the smallest loss but still over the limit.
* Therefore thinking-off is NOT adopted as a default and is not advised for qwen3. It stays an option (`DELENTIA_OLLAMA_THINK=off`) for someone who prefers speed.
* qwen3:8b in the default mode was not stable (4, 2, 2): the goal count moves by two between identical runs, so no ranking of models is made.
* bonsai-2:4b with thinking default had the best counts (14/15) at the shortest time; one goal in round 3 took 119 s. Described as "the best of this small sample", not as a recommendation.

## Stability (qwen3:8b, iGPU, thinking off, 40 different prompts one after another)
All 40 answered. Prompt reading averaged 415 tokens/s in the first ten and 407 in the last ten; generation 15.5 and 15.4 tokens/s; wall time 6.0 s and 6.4 s (within 7%, rule: 20%). The server log shows no GPU error (the CUDA lines only say there is no NVIDIA card; "waiting for llama-server" lines are model loads). Rule met: the iGPU setting was stable over this run (about 4 minutes, not hours).

## What this shows and does not show
Shown (one machine): the iGPU path stays stable for 40 requests; thinking is where most of the time and most of the correct tool use of qwen3 comes from. Not shown: stability over hours, other computers, harder tasks, any quality ranking. The Desk keeps recommending no model.
