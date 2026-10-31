# Your data: where it is, how to back it up, how to erase it, how to uninstall

Delentia runs on your computer and keeps what it knows about you in **one folder you own**. This page says what is in it, how to copy it somewhere safe, how to erase a person from it, and what uninstalling does and does not remove. Nothing here needs the internet.

**Status, plainly:** the commands below exist and are covered by automatic tests (backup, restore, erasure). Backup and restore have been run on the author's machine and in CI; they have **not** yet been run by anyone else on their own data. The erasure leaves some things behind on purpose or by a known limit (see "Erasing a person"); read that section before you rely on it.

## Where your data is

| You installed with | Your data folder |
|---|---|
| The Windows installer, or `pip install delentia-os` | `%USERPROFILE%\.delentia` (Linux and macOS: `~/.delentia`) |
| A source checkout (developers) | the repository folder, unless `DELENTIA_HOME` names another folder |
| Any of the above with `DELENTIA_HOME` set | exactly that folder |

Inside the folder (only the parts that exist on your computer appear):

| What | What it is |
|---|---|
| `agentic.db` | the record of what the agent did (the signed, chained audit trail), approvals, and memory |
| `rct_control_plane.db` | the older control-plane tables (for example skills the agent learned) |
| `keys\` | **private keys** (the audit signing key, approver keys). Whoever holds a private key can sign as you. Never mail it; never put it in a repository. |
| `memory_keys\` | one key per person that seals that person's memory. Destroying a person's key is how they are erased. |
| `approvers.json` | the public keys of the people allowed to approve actions |
| `model.json` | which model Delentia uses (it never holds a key) |
| `law_packs\` | statutes you imported yourself |
| `logs\` and `run\` | log files and process numbers written by `delentia launch` |
| `browser_shots\` | pictures the browser tool took |

**Installing, updating and uninstalling never touch this folder.**

## Back it up

```
delentia backup create --out C:\Backups\delentia-2026-10-31.zip
delentia backup verify C:\Backups\delentia-2026-10-31.zip
```

* It copies the databases with SQLite's own online backup, so it is safe while Delentia is running, and it adds your settings (`model.json`, `approvers.json`, your policy, `AGENTS.md`/`SOUL.md` and similar). Every file is listed with its SHA-256 in a `manifest.json` inside the zip.
* **Private keys are left out** (anything under `keys\`, `.pem` files, token files), so a backup you copy to a cloud drive is not a way to lose your signing key. Add `--include-keys` only if you have decided that the zip is as sensitive as the keys, and keep it somewhere you control. Without the keys a restored copy still shows its history, but cannot sign new records as the old key, and **memory sealed per person (`memory_keys\`) cannot be read back**: keep a separate copy of `memory_keys\` with the same care as the keys if you want your memory restorable.
* A backup is never overwritten: choose a new file name each time.
* `delentia backup verify` re-checks every file against the manifest. Do it once after creating the backup and again before you rely on it.

## Restore it

```
delentia backup restore C:\Backups\delentia-2026-10-31.zip --to C:\Restore
```

* Everything is checked against the manifest **before** anything is written; one changed byte stops the whole restore.
* Files go under `C:\Restore\home` (the databases) and `C:\Restore\user` (the settings), so you can look before you copy anything over your live folder.
* If a file already exists, restore refuses; with `--force` it moves the old file aside (named `...before-restore-<time>`) and never deletes it.
* The chained audit record in a restored database still verifies: it is the same bytes. Anything written after the backup was taken is not in it.

## Erase one person

If several people use one Delentia (each has their own namespace), you can erase one of them without touching the others. This needs an **approver's signature**, because it cannot be undone.

```
delentia memory erase-request <namespace>
delentia memory erase-sign <namespace> <head_hash> --approver-key <your approver key file>
delentia memory erase <namespace> --reason "<why, without personal data>" --public-key <approver public key> --signature <signature> --confirm <namespace>
```

* `erase-request` prints what will be signed and an inventory of what holds that person's text. `erase-sign` runs on the approver's own device. `erase` destroys the person's memory key, scrubs the readable copy in the table, and compacts the database file so the text is not left in free pages.
* The signed record that the erasure happened stays (it contains no personal text). The chains keep verifying.
* **What it does NOT do (it prints this list when it finishes):** audit rows written before this feature existed are not sealed and are reported, not changed; the separate skills database is reported; other tables that carry the person's name are overwritten, but a plain-text copy elsewhere (an export you made, a screenshot) is yours to find.
* **A backup made before the erasure still contains the person's words.** Erasing from the live folder does not reach copies. Run

  ```
  delentia backup erasure-check C:\Backups
  ```

  to list which backups still hold an erased person (exit code 1 if any does). It deletes nothing; deleting or replacing old backups is your decision.

## Start over with the sample files

If you only want the demo folder back as it was:

```
delentia demo reset
```

It puts the sample quotes back as `delentia demo init` wrote them and keeps a copy of any file it changed. Nothing is deleted.

## Uninstall

* **Windows installer:** Settings → Apps → Delentia → Uninstall. It stops what is running and removes `%LOCALAPPDATA%\Programs\Delentia`. **Your data folder stays.**
* **pip:** `pip uninstall delentia-os`. Your data folder stays.
* To remove your data as well, delete the data folder yourself **after** making a backup if you might want it. Deleting `%USERPROFILE%\.delentia` removes the memory, the record, the keys and the settings for good; there is no undo, and without the keys the old audit record can no longer be shown to be yours.

## What is not here yet

There is no button in the Desk for backup or erasure; they are commands. There is no scheduled backup. Delentia does not send your data anywhere on its own: what leaves your computer is the text of a request to the model **you** chose (see the Models page), plus the once-a-day version check that sends nothing about you (`delentia update --turn-off` switches it off).
