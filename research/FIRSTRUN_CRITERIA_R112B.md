# First run, part 2: install progress, ports, own window, records, CI (Round 112B, 2026-11-08)

Source: findings 1, 6, 9 and 10 of the Architect's first install of 2.4.3 on a clean second computer, plus the CI test promised in `FIRSTRUN_CRITERIA_R112.md`. Written and committed BEFORE the code.

## What was read in the code before writing the rules (facts, not results)
- The launcher takes `/health` answering 200 on port 8000 as "our agent is already running". Anything else on 8000 that answers `/health` with 200 would be adopted and the Desk pointed at it; anything that holds the port without answering makes `launch` wait 120 s and fail. Ports are fixed (agent 8000, Desk 3010).
- The Desk opens in an ordinary browser tab (`webbrowser.open`); there is no window of its own.
- The Windows installer runs the package install with `ewWaitUntilTerminated` and a caption that promises "a few minutes"; the progress bar stays at the end of the file-copy step.
- Every episode, including one that never reached a model, is listed first in Sessions.

## Rules (each is a test or a CI step; a rule that is not met is reported, never relaxed afterwards)
- **R8 Install progress.** During the package-install step the installer's progress bar is in animated (marquee) style, and the text says that this step downloads packages from the internet and that the bar is not a percentage; it does NOT promise a number of minutes (none was measured on a clean computer). Checked by a test that reads the installer script, and by the existing clean-runner install in CI. What a person sees on screen is judged on the Architect's second computer, not here.
- **R9 Ports.** (a) A program that is not Delentia and answers `/health` with 200 on the preferred agent port is NOT adopted: the launcher picks another free port and starts its own agent there. Test: a real foreign HTTP server on a real port. (b) A port held by something that does not answer is skipped, not waited on for 120 s. (c) A Delentia agent that answers (JSON with `status` healthy, a version and a timestamp) is still reused. (d) The ports chosen are remembered in the data folder and reused by the next start if still ours. (e) Nothing binds anything but 127.0.0.1.
- **R10 Own window.** On Windows the Desk opens in the installed Edge or Chrome in application mode (`--app=URL`: no tabs, own taskbar entry), using the person's normal browser profile (so a passkey or sign-in is not lost). Fallback is the default browser tab. `DELENTIA_DESK_WINDOW=tab` turns it off. Test: a pure function that returns the command it would run, for the cases Edge found, only Chrome found, nothing found, opt-out, non-Windows.
- **R11 Records.** In Sessions, episodes that ended because no model could be reached (`model_not_running`, `llm_error`) are hidden by default behind a visible count and a switch; nothing is deleted or changed in the audit record. Test: a pure function over a list; Thai and English labels.
- **R12 Package check.** In the CI job that installs the built wheel in an empty environment, a server with no model program reachable answers a goal with HTTP 502 and the plain sentence ("not running") within 5 s on a warm server (the first request is a warm-up and is not timed; the CI machine is slower than the measuring machine, where it is about 2.7 s).

## Not claimed
Nothing here says how a person experiences the install bar or the window; the second computer is the only evidence for that. R9(e) is a rule about what the code binds; it is not a security audit.
