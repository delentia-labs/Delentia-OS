# Which local model? (an honest guide, checked 2026-11-03)

Delentia can use a model that runs on your own computer through [Ollama](https://ollama.com). This page says what is known and what is not. **Every local model below is for trying Delentia.** Small models on an ordinary computer are slow (often a minute or more per request) and often choose the wrong tool; for real work an online model is usually needed. Delentia itself has not yet been measured with a strong online model.

## Do it from the Desk, no terminal
Open the Desk, then **Setup assistant** (or **Models**) and the box **On this computer**:
1. It shows how much memory your computer has.
2. If Ollama is not installed, a button opens Ollama's official download page. Delentia does **not** download or run an installer by itself. Install it, come back, press **Check again**.
3. If Ollama is installed but not running, press **Start Ollama**.
4. Pick a model from the short list and press **Download**. It shows the size, asks you to confirm, and shows a progress bar. You can cancel. Then press **Use this model**.

The Desk checks that there is enough free disk space first, and only downloads models from its own list.

## The list, and how much is known about each
The sizes, tools support and licences were read from each model's own Ollama page on 2026-11-03. "Estimated memory" is a **planning estimate** (the download size × 1.25 + 1.5 GB), not a measurement: the computer should have about 1.4 times that much memory in total, because the system and your browser need room too.

| Model (Ollama tag) | Download | Estimated memory | Measured by this project? |
|---|---|---|---|
| `qwen3:1.7b` | 1.4 GB | 3.2 GB | No |
| `qwen3:4b` | 2.5 GB | 4.6 GB | No |
| `qwen3:8b` | 5.2 GB | 8.0 GB | **Yes, one machine, one run each:** 4 of 5 simple goals completed; on the harder fixed task set 0 of 4 in every arm; about 13 tokens a second on a CPU |
| `qwen3:14b` | 9.3 GB | 13.1 GB | No |
| `bonsai-2:4b` | 1.6 GB | 3.5 GB | No. The maker says its ternary weights give quality close to full precision at about half the size of a 4-bit model; this project has not checked that claim |
| `bonsai-2:9b` | 3.2 GB | 5.5 GB | No (same claim by the maker) |
| `lfm3:1.7b` | 1.1 GB | 2.9 GB | No. Its own page says it is not meant for complex multi-step work. Licence: LFM Open License v1.0, read it before commercial use |

What this means in practice:
- **8 GB of memory:** `qwen3:4b` or smaller can probably be held. Expect it to be limited.
- **16 GB:** `qwen3:8b` can probably be held, and it is the one this project has tried most. "Tried most" does not mean good: it did not pass the harder task set.
- **32 GB or more:** `qwen3:14b` can probably be held. Not measured by this project.
- **Under about 6 GB:** local models are unlikely to be practical; use an online model.

The models above are not ranked and none is called "best". Two earlier results from this project for reference: `qwen2.5:7b` completed 3 of 5 simple goals and `llama3.2:3b` 0 of 5 (one run each).

## Other programs (LM Studio, llama.cpp, vLLM…)
Programs that offer an OpenAI-style address can be used from the **Models** page ("your own address"). Delentia has only been tried with Ollama, so the Desk does not offer the others.

## What we are going to measure
A benchmark of local models on Delentia's own tasks and on computers of different sizes is planned after the first outside users; until it exists, the table above says "not measured" and means it.
