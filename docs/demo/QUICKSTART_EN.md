# Try Delentia yourself in 15 minutes (Thai-language demo)

Status: **experimental.** This demo shows one path: *give a goal in Thai → the agent uses real tools on a real folder → a result file → the answer is checked → close the program and open it again, and what you told it is still there.*
It does not show that the agent can do everything, and it is not a benchmark of any model.
(The Thai version, `QUICKSTART_TH.md`, is the source. If the two ever differ, trust the Thai one and tell us.)

## You need

- Windows, Python 3.10 or newer, and the `Delentia-OS` project with its dependencies installed.
- A model that **can really call tools** (see "Choosing a model"). A model that chats well may still be unable to use tools.

## Steps (from the `Delentia-OS` folder, or double-click `RUN_DELENTIA_DEMO.bat` in the Delentia folder)

```bash
python -m rct_control_plane.cli model show
python -m rct_control_plane.cli demo init
python -m rct_control_plane.cli demo run compare
```

1. `model show` tells you which model will be used. If it warns about a missing key, set one first (next section).
2. `demo init` creates `~/delentia-demo` with three **synthetic** vendor quotes (no personal data). It never overwrites anything.
3. `demo run compare` asks the agent: read the quotes, build a price table, say which vendors are within 15,000 baht, do not change the original files, do not send anything out.

The screen and the file `~/delentia-demo/results/<time>-compare-….md` report seven things: the status; which tools the agent called; how the FDIA safety gate decided; whether the agent read text from outside (taint); the answer;
**a check of the answer against facts known in advance** (not the agent's own verification); and whether the audit chain is intact.
If a check fails the command exits with code 1 and the result file lists what failed. The demo always reports failure honestly.

## The five cases

| command | what you should see |
|---|---|
| `demo run compare` | all three files read; Siam Air and Bangkok Technic within budget, Thai Cooling over; originals unchanged |
| `demo run edit` | **stops and waits for a signature**; the file is untouched; it prints an id, and `demo approve <id>` lets it through (once only) |
| `demo run remember`, close the window, open again, `demo run ask` | it answers that the budget approver is Mr. Somchai and that tables are sorted from lowest to highest price |
| `demo run budget` | it uses the new 12,000 baht budget, not 15,000 |
| `demo status` | model, waiting approvals, number of memories, audit chain |

The demo approver key sits on the same machine as the agent so that you can see the whole approval flow at once. **A real deployment keeps approver keys on another device** (`delentia approvals sign`).

## Choosing a model

Tried on 9 Oct 2026 with the local model qwen2.5:7b (Ollama, CPU): in some runs it read all three files, but it also used the wrong tools, answered in Chinese, or answered incompletely. It does **not** pass this demo yet.
Use a model through OpenRouter that handles tools well:

```bash
python -m rct_control_plane.cli model set <model id from openrouter.ai/models> --provider openrouter
```

Put your key in the machine's environment (`OPENROUTER_API_KEY`). **Never put a key in a file, a chat, a video or a repository.** Create a separate test key with a small spending limit (for example 2–5 US dollars) on the OpenRouter site.
The runtime also caps each episode: `DELENTIA_EPISODE_BUDGET_USD`, `DELENTIA_EPISODE_MAX_TOKENS`, steps (`--max-iterations`), time (`--max-seconds`), and it stops itself when it repeats the same step.

**Cost per call:** the full tool menu (the default) makes the prompt about 8,200 tokens for every model call (47 tools), so keep your OpenRouter limit low at first.
A smaller menu exists (`DELENTIA_TOOL_MENU=ranked`, `DELENTIA_TOOL_MENU_FORMAT=compact`, about 1,500 tokens per call) but it is **not the default yet**: with qwen2.5:7b on the same six price-comparison tasks
it let the model read the files in only 1 of 6 runs, until two reply-format problems were found and fixed (the tool name written in the `action` field; arguments sent without a tool name); after that it read them in 6 of 6, like the full menu
(and failed every answer check with either menu). One small model and six tasks are not enough to change a default; that waits for a model that is good with tools.

## If something goes wrong

| symptom | cause seen | fix |
|---|---|---|
| `llm_error` | the model did not answer | `model show`; for Ollama, check it is running and has the model |
| wrong tool / answer in another language | a small model is weak with tools | use another model; the tool correctly reports "not passed" |
| `max_iterations_reached` | the task needs more steps | `--max-iterations 12` |
| `pending_approval` | the system is waiting for a signature (correct behaviour) | `demo approve <id>` |

## Tested scope

- Tested (a model that follows a script + real tools + separate processes): init, compare, taint, edit → approve (cannot be reused), memory across a restart, the answer checker.
- Tested with the local qwen2.5:7b: it runs, it is safe, it reports truthfully, but it **does not pass** the correctness checks.
- **Not tested:** a model that is good with tools (OpenRouter); three repeated runs from a clean start; the owner running it alone; a clean-machine install.
