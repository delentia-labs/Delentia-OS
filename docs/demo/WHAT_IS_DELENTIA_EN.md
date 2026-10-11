# What Delentia is (one page, no jargon)

Status: **experimental**. Written only from what was measured; every number has its source file under `research/`.

## The problem
When an AI moves from answering to acting (reading files, editing them, opening web pages, sending messages) you need more than an answer that sounds clever. You need to know what it understood as the goal,
what it is allowed to do, whether it remembers what you told it, and, when it goes wrong, whether you can trace what happened.

## Delentia is a control layer around an agent, not an operating system
"OS" does not mean Windows or Linux. It is a program that runs an AI agent and **wraps it in a safety layer** on your own machine (the model can be local or a hosted service).

## What it gives you (and how to check it yourself)
| You get | How | Check it |
|---|---|---|
| **It asks before anything that matters** | Editing a file, running a command that is not read-only, opening an address you did not type: all wait for **your signature** (the key is yours, not the agent's) | `demo run edit` stops; the file is unchanged |
| **It is not steered by text from the web or from files it receives** | Once the agent has read outside text, anything with a side effect needs your signature whatever the model "decides" | Against a scripted model that obeys every instruction: side effects that ran 18 -> 0 of 23 cases |
| **It remembers your rules** | `delentia memory add --pin "never edit the originals"`: the rule is shown to the agent on **every** task, whatever the task | `delentia memory list` |
| **A record you can check** | Every action sits in a hash-chained, signed log | `delentia audit-chain verify` |
| **It can forget a person for real** | Erasing destroys the key that seals their text; none of their words remain in any byte of the database (text written after sealing was on; older plain rows and the separate skills database are not erased, and the report says so) | `delentia memory erase-request` |
| **Thai** | Meaning-based recall in Thai with a multilingual model (bge-m3): 38 of 40 paraphrased questions found | `delentia memory calibrate --model bge-m3` |

## What it cannot do yet (plainly)
- **It has never been run with a model strong enough to use tools well.** The local models tried still pick the wrong tool often, so the safety results come mostly from scripted stand-in models.
- **No outside users yet**, and no public server.
- The log is **tamper-evident, not tamper-proof**: someone who controls the whole machine can rewrite it until an independent witness exists.
- Pinned rules: at most 5 are shown per task. Rules that are not pinned rely on similarity search, which showed the agent only 29 of 40 relevant rules in the measurement.
- On English, bge-m3 scores slightly below nomic-embed-text (33 vs 37 of 40).

## Try it (15 minutes)
See `docs/demo/QUICKSTART_EN.md`. The demo does not touch your real data.
