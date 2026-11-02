---
title: Delentia scripted demo
emoji: 🌿
colorFrom: green
colorTo: green
sdk: gradio
app_file: app.py
pinned: false
license: apache-2.0
short_description: Scripted safety demo in your browser, no model needed
---

# Delentia: the scripted safety demo, in a browser

A web page that runs [Delentia](https://github.com/delentia-labs/Delentia-OS)'s scripted demos on the server, in a fresh throw-away folder, and shows the report. No sign-in, no key, no model, and the visitor types nothing that reaches a command.

**What it shows:** a risky change waits for a person's signature; a note hidden in a vendor quote cannot make the agent change a price without one; every step is written into a hash-chained, signed log.
**What it does not show:** anything about how well a language model uses it. A fixed program stands in for the model, and the report says so on its first lines.

## Run it yourself
```
pip install -r requirements.txt
python app.py
```

## Put it on Hugging Face (the owner's steps)
1. huggingface.co → New Space → SDK: Gradio, free CPU, name it `delentia-demo`, owner: the Delentia organisation.
2. Upload the four files of this folder (`app.py`, `runner.py`, `requirements.txt`, this `README.md`): `git clone` the Space and copy them in, or use the "Files" tab.
3. The Space builds by itself. Open it, press **Compare three vendor quotes**: a report with "passed" lines and an "audit chain: intact" line must appear. Press the third button and check the report ends with the refusal.
4. When `delentia-os` has a newer release, change the pinned version in `requirements.txt` (the Space then runs exactly what a person would install).

The code is in the public repository under `apps/browser-demo/`; the Space is a copy of it, so the repository stays the source of truth.
