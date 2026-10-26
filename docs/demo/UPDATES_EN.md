# Update notices and installing a newer version

## In short

* Delentia **checks by itself whether a newer version exists**, at most once a day, and **notifies** you on the Status page (a green banner) and under Settings → Version and updates.
* **Installing** is done only by you: Start menu → **Update Delentia**, or the command `delentia update --apply`. It always asks first.
* Your data (`%USERPROFILE%\.delentia`) is never touched.

## How the check works

* One small request to `https://pypi.org/pypi/delentia-os/json` (the public package index) to read what the newest release is.
* **None of your data is sent.** The server sees your network address and the text `delentia-os/<version> update-check` in the request header, the same as whenever anybody runs `pip install`.
* The answer is remembered for 24 hours (`update_check.json` in your data folder), so opening the page often does not repeat the request.
* With no internet, or no answer, the result is "could not be checked right now", never an error, and the last known answer is kept.
* Version numbers are compared by the program itself; pre-releases (rc, a, b) are never offered.

### Turning the check off
* Settings → Version and updates → **Turn the daily check off**, or
* `delentia update --turn-off`, or set `DELENTIA_UPDATE_CHECK=off`, or `DELENTIA_OFFLINE=1` (machines that must not use the network).
* Back on: `delentia update --turn-on`.
* While it is off, not a single request leaves (a test checks this).

## Installing a newer version

1. Stop the agent: Start menu → **Stop Delentia** (Windows can not replace files that are in use, so nothing is restarted for you).
2. Start menu → **Update Delentia** (or type `delentia update --apply`).
3. The window says which version and asks "Install now?". Answer `y`.
4. In order: it downloads only that version's file → **checks its SHA-256 against the one the package index published** → installs only if they match → if they do not, it stops at once and installs nothing.
5. Start menu → **Delentia** to start again.

Offline: `delentia update --apply --find-links <folder with .whl files>` installs from a file you obtained another way (the SHA-256 is still checked against the published value, which must have been seen once while online).

## Why there is no "Update now" button on the web page

On purpose, for three reasons:
1. An update **replaces the running program**. On Windows a file in use can not be replaced, so it must be stopped first. A web page that stops itself, updates, and starts again is risky and needs more design.
2. Running downloaded code is a "risky action" by this system's own definition. It should be confirmed by a real person at a terminal they are sitting at, not by a button another program could press.
3. The update command is blocked from the agent twice (the command refuses when it knows it was started for the agent, and the command screen refuses the text `update --apply`). An agent that is talked into updating itself can not.

On the plan (not built): a web button that creates an approval request, you confirm with Windows Hello, and a separate helper process stops the program, updates it and starts it again.

## Limits of the trust

The SHA-256 comes from the same package index as the file, so it protects against a damaged or swapped download, **not against a compromised package index**. Releases are published from CI with a token only the maintainer holds. Publishing with provenance (attestations) is a later step.

## All the commands

| Command | What it does |
|---|---|
| `delentia update` | Checks now (forced) and says whether a newer version exists |
| `delentia update --apply` | Installs the newer version (asks first) |
| `delentia update --apply --yes` | Does not ask (for your own scripts) |
| `delentia update --turn-off` / `--turn-on` | Turns the daily check off / on |
| `delentia update --apply --find-links <folder>` | Installs from files on this computer |
