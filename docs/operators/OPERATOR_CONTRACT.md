# Operator contract

What a person who runs Delentia for someone is promised, what they are not, and what to do when something is wrong. Written in plain terms, for the operator, not for a regulator.
**This is not a compliance statement.** Nothing here is a claim of PDPA, GDPR, SOC 2 or any other conformity. Delentia is an experimental agent runtime; the sections below say what it does today and what it does not.

## 1. Who this is for

One owner who runs the agent on their own machine or on a host they control, and who may let named people use it through a chat channel or a personal API token. A person who is not the owner can ask the agent to do things; they cannot see what others asked, change settings, approve their own requests, or reach the raw tool gateway.

## 2. What it is meant for

- Reading, summarising and comparing documents in a folder the owner chose (quotes, tickets, notes).
- Drafting changes to those files, **which a person signs before they are written**.
- Looking things up (web search, a page) with the result treated as untrusted text.
- Scheduled reports and reminders, delivered only to people the owner named for that channel.
- Helping with the owner's own repository.

## 3. What it is not for

- Moving money, paying, trading, or anything the owner could not undo.
- Deploying to production, changing access rights, deleting data.
- Decisions about a person (hiring, credit, health, legal advice) or anything regulated.
- Running unattended for days **without** the operator watching `delentia host-metrics` and the approvals queue: no host has run it that way yet (see section 12).
- Holding other people's secrets. Secret-looking files (`.env`, `*.pem`, key files) are refused by name, but that is a name check, not a guarantee.

## 4. Limits that are always on

| Limit | Default | How to see or change it |
|---|---|---|
| Steps per episode | 5 (the agent stops and says so) | per entry point |
| Time per scheduled run | 300 s | `DELENTIA_CRON_MAX_SECONDS` |
| Scheduled runs per hour | 60 | `DELENTIA_CRON_MAX_RUNS_PER_HOUR` |
| Scheduled jobs per person | 20 | fixed |
| A pending request waits for a decision | 7 days, then it expires and never runs | `DELENTIA_APPROVAL_DECISION_TTL_SECONDS` |
| An approved request may be used | 24 hours, then it expires | `DELENTIA_APPROVAL_EXECUTION_TTL_SECONDS` |
| The same step repeated | 3 times, then the episode stops (`stuck_repeating`) | `delentia limits` |
| Daily money and tokens, per person and in total | none until you set them | `delentia limits`, `DELENTIA_DAILY_BUDGET_USD` and the others it lists |

Limits that you set are reserved before an episode runs (Round 82): episodes started together cannot be given the same remainder.

## 5. What will wait for a person (expected pending approvals)

Writing or patching a repository file; running a shell command the classifier does not call safe; creating a scheduled job; starting sub-agents; any call that reaches outside this machine when the owner's policy says so; and **every** side effect or data-moving call in an episode that has read text from outside (a web page, a dropped file, an image, a transcript). Expect a few a day during normal use; a long list that nobody reads is a sign the policy needs tightening, not a reason to approve faster. Approvals are signed with a key kept on another device (`delentia approvals sign`); the agent host never holds it.

A request that a hard rule refuses (a secret file name, a path the owner forbade) is refused immediately: nobody is asked to sign it.

## 6. How to stop it

| What | Command |
|---|---|
| Stop everything now (also stops an episode already running before its next tool) | `delentia pause --reason "reason"` |
| Start again (needs a signature when an approver key exists) | `delentia resume` |
| Cut one person off | `delentia tokens revoke <name>` |
| Stop the process | stop `delentia serve` (the service or container) |

An action that was approved but not yet run stays approved while paused and runs only after `resume`.

## 7. Seeing what it did

`delentia audit-chain verify` checks the hash chain and signatures; `delentia audit-chain witness-status` says how many rows no independent witness holds yet; `delentia approvals list --status ALL`; the Desk pages Governance, Signatures, People and Audit; `delentia host-metrics` for the host. A scheduled run that was cut off by a restart shows as `interrupted`; an approved action whose result was never recorded shows as `OUTCOME_UNKNOWN` and is never run again (`delentia approvals reconcile`, then `resolve` after you have looked).

## 8. What leaves the machine

Prompts, memories recalled into a prompt, and tool results go to **the model provider you configured**. With a local model (Ollama) nothing leaves. With a hosted model the provider receives them. `delentia sovereignty` sets a policy that checks every model call before it is sent (country and provider rules, personal-data handling). The agent never sends the contents of key files, tokens or `.env` by design, but a person's own words in a goal are theirs to protect: do not paste secrets into goals.

## 9. What is kept, and where

Everything lives under the data home (`DELENTIA_HOME`, or the working folder when unset): the SQLite databases (audit chain, approvals, memories, jobs, ledgers), per-person memory keys, the owner's policy and the approver public keys. Memories are sealed per person; the audit chain stores goals, reasoning and tool arguments sealed under the same key. Keys are **outside** the repository and outside backups unless you ask (`--include-keys`). Nothing is uploaded unless you configure a witness, a webhook or a gateway.

## 10. Export, revoke, erase

- Export a person's memories: `delentia memory list --namespace <person>`; a whole backup: `delentia backup create --out <zip>`.
- Revoke a memory (kept in history, never recalled again): `delentia memory revoke <id> --reason "..."`.
- Erase a person (their sealed text becomes unreadable and is removed from the database file): `delentia memory erase-request`, then `erase-sign` with an approver key, then `erase`. Old audit rows written before text was sealed, and the separate skills database, are reported as **not** erased.

## 11. Backup and restore

`delentia backup create --out <zip>` (never overwrites; keys left out), `delentia backup verify <zip>`, `delentia backup restore <zip> --to <empty folder>` (never overwrites; checked against its manifest before the first byte is written). A restore was exercised on a clean folder with a fresh process (the chain verifies against the public key, the memory and the waiting approval are there). Keep a copy **off the host**; the restore is only as good as the copy.

## 12. What has not been proven

- No capable hosted model has driven the loop for long; local 7B models pick tools correctly on about 3 of 5 simple goals.
- No host has run it for days; no soak test exists yet.
- No independent witness is configured by default, so "tamper-evident against a compromise of the host" may be claimed only after a witness is configured and fresh. The word "tamper-proof" is never right.
- No outside user has used it. There is no support organisation.

## 13. If something goes wrong

1. `delentia pause --reason "incident"`.
2. Change nothing in the databases. Copy them: `delentia backup create --out incident.zip`.
3. `delentia audit-chain verify`, then `delentia audit-chain check-witnesses` if you configured any.
4. `delentia approvals list --status ALL` and the Audit page: what ran, who signed.
5. Rotate whatever might have been exposed: the person's token (`tokens revoke`), a model key, an approver key (add the new key, remove the old).
6. `delentia resume` only when you understand what happened.

## 14. Contact

Open an issue at <https://github.com/delentia-labs/Delentia-OS/issues>. There is no support level agreement; for a security problem, say "security" in the title and do not paste secrets.
