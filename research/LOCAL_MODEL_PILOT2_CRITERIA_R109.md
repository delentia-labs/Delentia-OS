# Local model pilot 2 (Round 109): thinking off, three rounds, and a stability run; the rules, written before the first run

Follows `LOCAL_MODEL_PILOT_RESULTS_R109.md`. Questions: (1) with the iGPU on, does switching the model's thinking off (`DELENTIA_OLLAMA_THINK=off`) cut the time of the five-goal probe, and what happens to the number of goals completed? (2) how much do the completed counts move between rounds of the same model and setting? (3) is the iGPU stable over a longer run?

Design, fixed here. Machine and Ollama as in pilot 1; a second Ollama with `OLLAMA_IGPU_ENABLE=1` on port 11435 for every run (the owner's Ollama is not used and not changed); one probe run = the five goals of `scripts/real_model_tool_probe.py`, `--max-iterations 4 --max-seconds 300`; models `qwen3:4b`, `qwen3:8b`, `bonsai-2:4b` (`bonsai-2:9b` is left out: 1 of 5 in pilot 1 and the slowest); two settings (thinking at the model's default, thinking off); three rounds; order: round by round, inside a round model by model, inside a model default then off, so that drift of the machine is spread across the settings. Nothing else heavy runs on the machine meanwhile.

Stability run: 40 sequential requests of `qwen3:8b` with unique prompts (about 1,700 tokens, 48 tokens generated) on the iGPU Ollama, thinking off, about 25 minutes.

Reported, never averaged into one score: per run the goals completed and the seconds per goal; per model and setting the three counts, the median of the 15 goal times and the number of goals that ended by a model error or the time limit.

Rules, fixed now:
* "Thinking off cuts the time" only if, for a model, the median goal time with thinking off is at least 25% below the median with thinking at the default, over the three rounds together.
* "Thinking off costs correctness" only if the sum of completed goals over the three rounds falls by at least 3 of 15 for that model. Anything less is within the noise of five goals and is reported as "no difference shown".
* The spread between rounds is the range of the three counts for one model and setting; if it is 2 or more goals for a model, no difference smaller than that is reported for that model.
* The iGPU is "stable in this run" only if all 40 requests answered, the generation speed of the last 10 is within 20% of the first 10, and the server log shows no GPU error, device loss or restart. One failed request, a drift beyond 20% or a log error = "not stable", and nothing is recommended.
* A change of the model's behaviour that makes the probe's own check impossible (e.g. thinking off makes a model refuse the JSON format) = `not_run` for that cell with the reason.

What this does not say: anything about other computers, hours of use, harder tasks, Thai, or which model is better.
