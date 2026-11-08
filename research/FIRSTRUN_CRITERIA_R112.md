# First run on a clean computer: pass rules written before the code (Round 112, 2026-11-08)

Source: the Architect's first install of 2.4.3 on a second, clean Windows computer (no Ollama, no model). Findings 3, 4, 5, 7 of that session. Written and committed BEFORE the fixes.

## Measured before any change (this machine, Ollama address pointed at a closed port, a fresh data folder)
- One question ("What can you do?") ended `llm_error` after **11.5 s** with the default retries (2); with retries off **2.7 s**. On the clean computer the screenshot showed 17 s. So the retries cost about 8.8 s, more than their back-off (3 s): every attempt also rebuilds the prompt.

## Rules (each is a test; a rule that is not met is reported, never relaxed afterwards)
- **R1 No retry on a refused local connection.** A connection refused by an address on this computer (127.0.0.1, localhost, ::1) is not transient: the episode makes exactly ONE attempt. A connection error to any other host still retries as before. Test: a real closed loopback port counts attempts; a fake remote error still gets 3.
- **R2 Fast.** The same question against a closed loopback port ends `llm_error` in 3.0 s or less on this machine (measured before: 2.7 s with one attempt). If the machine is slower the number is reported as it is.
- **R3 No raw error in the sentence a person reads.** For a refused local model the text the Desk shows names what to do (start the model program, or choose an online model) and contains none of `WinError`, `ConnectError`, `errno`, `Traceback`. The technical text stays in the audit record.
- **R4 The model row tells the truth.** The status 'Is it working?' row for the model shows the readiness state (ready / server not running / model not downloaded / no key / not chosen yet), not only the name in the configuration. A fresh data folder with no model chosen and no Ollama is `not_chosen` or `server_down`, never plain ready.
- **R5 First-run guidance.** On a computer where the local model server is not reachable, the Models page shows, without scrolling past an error: (a) an online-model path with the place to type a key, (b) a link to ollama.com with the words 'download and install it yourself' and a note that small local models are slow, (c) the organisation-AI path. Test: a pure function maps (server state, installed models, key present) to the three actions and the link; every state has a Thai and an English sentence.
- **R6 Three clicks.** From the Models page of that computer, the online-model path or the install link is reachable in at most 3 clicks (counted in the page's own link structure).
- **R7 No tokens for a call that never left.** A failed model call that was never delivered reports 0 tokens in the Desk's footer, not an estimate of the prompt.

## Not claimed
Nothing here says anything about model quality. A real clean-computer retest (the Architect's second computer) is the evidence for R5/R6 as a person experiences them; the unit tests only pin the logic.

## Amendment of 2026-11-08, written after seeing the numbers (the rules above are NOT changed)
R2 says 'ends in 3.0 s or less on this machine (measured before: 2.7 s)'. That 2.7 s was a warm call (the kernel already imported). Measured after the change: warm 2.68 s (script, full kernel) and 2.3 s (real
`delentia serve` over HTTP, second request); but the FIRST call in a fresh process took 3.24 s in the test and the FIRST request to a fresh server took 8.2 s, because it pays for importing the kernel. R2 is met
for a warm call. It is NOT met for the first question after the program starts: that one is slower, and the Architect's 17 s was probably this cold start plus the retries. The timing test therefore times the second call
and reports the first; a cold-start improvement (warming the kernel when the server starts) is a separate item, not claimed here.
