# Tester feedback form: tell us where you got stuck

Thank you for trying Delentia. This form takes about 10 minutes and is the most useful thing you can give us: **where did it stop making sense, and where did it stop working?** Being stuck is the result we want to hear about, not a mistake of yours.

**What we ask of you:** try the steps below on your own computer, in this order, and note for each one how it went. You can skip a step. You can stop at any step.

**What we do not want:**
* **No keys, passwords or tokens**, anywhere in this form. If a message on your screen contained one, write "(a key was shown)" instead of copying it.
* **No real names or private text.** Use an alias for yourself (`tester: t1` is fine).
* If you attach a file, read it first. The post-install check (`check_install_report.txt`) lists versions and folder names on your computer and no keys; you decide whether to send it.

**What we do with it:** the lines in the box below are counted by a script (`scripts/tally_tester_feedback.py`) the same way for everybody: how many testers had trouble at which step, how long each step took. The free-text notes are read by a person and never counted by the script. We report numbers as "k of n testers" with an interval, so that three testers are never presented as proof of anything.

## The steps

| # | Step | What it means |
|---|---|---|
| 1 | `download_and_install` | Get the installer (or `pip install delentia-os`) and finish installing. See `INSTALL_WINDOWS_EN.md`. |
| 2 | `first_start` | Start Delentia and see its page in your browser. |
| 3 | `first_approver` | Set up who can approve actions (a device or a key). See `FIRST_APPROVER_EN.md`. |
| 4 | `choose_model` | Choose the model Delentia will use (the Models page). A local model or a hosted one with your own key. |
| 5 | `first_request` | Ask Delentia for something small that you actually need, and read the answer. |
| 6 | `approve_something` | Ask for something that changes a file, and approve or refuse it when Delentia asks. |
| 7 | `backup` | Make a backup of your data. See `YOUR_DATA_EN.md`. |
| 8 | `uninstall` | Remove Delentia. Your data should stay. |

For each step write one line: **result | minutes | severity**.

* **result:** `done` (without needing help), `done_with_help` (you needed to ask someone, search, or try several times), `blocked` (you could not finish it), `skipped`.
* **minutes:** a whole number, roughly how long the step took including time stuck.
* **severity** of the worst thing in that step: `none`; `S3` cosmetic (it works, it looks odd); `S2` confusing (you were not sure what to do or what happened); `S1` needed a workaround (you found another way); `S0` could not go on.

## The form

Copy this box into a text file, fill in the `<...>` parts, and send the file back as it is. Keep the lines in this shape; the script only reads these.

```text
tester: <alias>
real_task: <yes or no>
help: <none, docs_only or asked_someone>
os: <Windows 11, Linux or macOS>
installed_with: <installer, pip or source>
date: <date>

1. download_and_install: <result> | <minutes> | <severity>
2. first_start: <result> | <minutes> | <severity>
3. first_approver: <result> | <minutes> | <severity>
4. choose_model: <result> | <minutes> | <severity>
5. first_request: <result> | <minutes> | <severity>
6. approve_something: <result> | <minutes> | <severity>
7. backup: <result> | <minutes> | <severity>
8. uninstall: <result> | <minutes> | <severity>
```

* `real_task`: `yes` if the request in step 5 was something you actually needed, `no` if you made it up to try.
* `help`: `none` if you used only what you were given; `docs_only` if you also searched or read the guides more than once; `asked_someone` if you asked a person.

## Then, in your own words (a person reads this, nothing counts it)

1. Where did you first think "this does not make sense"? What did you expect instead?
2. What did you try that did not work, and what did you see on the screen (the message, in words)?
3. Was there a moment you were unsure whether Delentia was safe to let do something? What would have made you sure?
4. If you could change one thing before the next person tries, what would it be?
5. Would you use it again for something real? Why, or why not?

## For whoever collects the forms

Save each filled form as its own `.md` file in one folder, then:

```
python scripts/tally_tester_feedback.py <the folder> --out report.md
```

A **friction point** is a step marked S0, S1 or S2, or one that was `blocked` or `done_with_help`. It is counted per step and per tester. A form with an unknown step, result or severity is refused by line number and never guessed at; the others are still counted. The report says "k of n" with a 95% interval and ends with the reminder that it counts what testers wrote and says nothing about people who did not try.

This is how the release gate "at least one outside person has used it for a real task and told us what broke" is checked (`docs/release/RELEASE_LEVELS.md`, gate G-people): one form with `real_task: yes` and the free-text answers is the evidence we would register for it. It does not make Delentia "usable by everyone"; it tells us where the next person will stop.
