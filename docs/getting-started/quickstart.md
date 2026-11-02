# Quick start

A first run in a few minutes, without a model and without an API key. It shows the mechanism that makes Delentia OS different: the agent **stops and waits for your signature** before it changes anything, and a note hidden in a file cannot talk it into acting.

You need [an installation](installation.md) (the demo commands below need release 2.4.1 or later for `--lang en`; on 2.4.0 leave it out and the demo is in Thai).

## 1. The agent reads, answers, and is checked

```bash
delentia demo init --lang en
delentia demo run compare --scripted
```

`demo init` makes a folder with three sample vendor quotes and a demo approver key. `demo run compare` has the agent read the quotes and answer; the answer is then checked against what is known to be true.

## 2. The agent stops and waits for a signature

```bash
delentia demo run edit --scripted         # asks to change a file: the agent STOPS
delentia demo approve <id> --scripted     # you sign; only now does the file change
```

The `<id>` is printed by the previous command. Nothing has changed on disk until you sign: that is the gate working.

## 3. A hijacked model is stopped

```bash
delentia demo run injection --scripted
```

A plain-sounding note hidden in one of the quotes tells the model to cut a vendor's price. The scripted model **obeys it**, as a worst-case model would. Because the text came from outside, the episode is marked *tainted* and the change waits for a signature instead of happening. `delentia demo reject <id>` refuses it.

## 4. Look at the record

```bash
delentia demo status
```

It prints the audit chain: how many rows, how many are signed, intact or not. Each row is hash-chained to the one before it, so an edited row is found; until an outside witness exists the log is **not** tamper-proof.

## What `--scripted` means

A fixed program stands in for the **model** and nothing else: the files, the tools, the safety gate, the wait for a signature, the signature check and the audit log are real. It shows the mechanism without installing a model. It says nothing about how good any model is, and every report says so on its first line. [What a run prints](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/demo/SAMPLE_OUTPUT_EN.md).

## With a real model

```bash
delentia setup          # chooses a model that answers (a local Ollama model or any OpenAI-compatible endpoint)
delentia demo run compare        # the same command without --scripted
```

A small local model completes some simple tasks, not reliably, and can be slow on a CPU. No strong hosted model has driven the runtime yet.

## In a web page

In one window run `delentia serve`, in another `delentia desk`: it opens the Desk in your browser (what the agent did, what waits for you, memory, models). A risky action can be approved from the Desk with a device you already own (Windows Hello, a fingerprint, a phone).

## Next

- What each part is: [Reference](../reference/index.md) · [The FDIA Equation](../reference/fdia-equation.md)
- What is measured and what is not: [Home](../index.md#what-is-measured-and-what-is-not) · [Known limitations](../KNOWN_LIMITATIONS.md)
- Something went wrong, or it worked: [open an install report](https://github.com/delentia-labs/Delentia-OS/issues/new/choose)

!!! note "Older quick start"
    The previous version of this page taught the scoring functions of the older SDK (an NPC action scorer and an example vote). It is kept as [historical text](../reference/legacy-quickstart.md).
