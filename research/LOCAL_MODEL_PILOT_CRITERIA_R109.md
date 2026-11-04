# Local model pilot (Round 109): what is measured and the rules, written before the first run

Question: of three small models that have not been measured here (`qwen3:4b`, `bonsai-2:4b`, `bonsai-2:9b`), with `qwen3:8b` re-run as the reference on the same day and settings, can any of them drive Delentia's governed loop on the five simple goals of `scripts/real_model_tool_probe.py` (read a file, read another, search, remember, an impossible goal that must call nothing), and at what speed and memory?

Settings, fixed here: the runtime's defaults for a local model (ranked compact tool menu), thinking left at the model's default, one run per goal, `--max-iterations 4`, `--max-seconds 300`, models run one at a time on one machine (Ryzen AI Z2 Extreme, 19.6 GB, CPU through Ollama), nothing else heavy running, the same Ollama version for all.

What is recorded per model: goals completed (the probe's own check), the time of each goal, whether the episode ended by finishing or by a limit, Ollama's reported size in memory while loaded (`ollama ps`), the download size. Nothing is averaged across goals into one score.

Rules, fixed now:
* A model "completed" a goal only if the probe says so (the expected token is in the answer, or for the impossible goal nothing was called). I do not re-grade by reading.
* "Usable to try" = at least 4 of 5, no goal ending by the time limit, and a median goal under 150 seconds. "Not usable here" = at most 2 of 5. Between is "mixed".
* n is 5 goals and one run: an interval is wide (4 of 5 has a 95% interval of about 38%-96%). The result is described as one small sample on one machine, never as a ranking, and differences of one goal are not called differences.
* If the models' own settings make a fair comparison impossible (a model refuses the JSON mode, a context that does not fit), the model is recorded `not_run` with the reason, not run under other settings.
* The result is registered in the results register as a pilot, with the commit of this file as its rule.

What this does not say: anything about quality beyond these five goals, other computers, Thai, the harder task sets, or a model's answers to anything but this probe.
