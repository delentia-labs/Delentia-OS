# Host runbook: from an empty server to the first outside user

Status (2026-10-02): **built and run for real** on Docker Desktop (Windows, Docker 29): image built, `bootstrap.sh`, notary + runtime healthy,
`delentia host-check` inside the container with no FAIL, a real governed episode through the container with a real local model (qwen2.5:7b,
75 s on CPU), the audit chain (35 rows, all signed) and the notary log (10 receipts) both verify, and Caddy answers over TLS with the
security headers (401 without a token, 200 with one, HTTP redirected to HTTPS). Not run: a Linux VPS, a public domain with a real certificate,
Caddy's ACME flow, WhatsApp/LINE webhooks through the proxy. Running it found eight defects, all fixed (see the Round 55 part B document); expect
the first Linux run to find a ninth and fix this file with it.

What this deploys: the runtime (`delentia serve`), a notary in a separate container with a separate OS user (audit tier A2), and Caddy for
TLS. Nothing else is published. Not covered: backups off the host, monitoring, multi-host, a database other than SQLite.

## 0. Before you rent anything (free, on your own machine)

1. `delentia host-check --local` and read every WARN. On a host, a FAIL means "do not open the port".
2. `python scripts/host_sizing.py` measures this exact runtime. On the development machine (16 threads, 15.6 GB): start-up to `/health`
   about 18-20 s, **resident memory about 650 MB idle, 770-780 MB after load**, CPU cost of a governed episode about 0.2-0.3 s with a model
   that answers instantly (after the Round 55 TLS fix; it was 0.76-1.0 s). The model's own time (seconds) is added to that and overlaps
   between users, the runtime's CPU time does not (it is serialised: about 3-4 episodes per second per core at most).
3. So: **2 vCPU and 4 GB RAM** is enough for the runtime, the notary, Caddy and a handful of users **if the model is remote**
   (OpenRouter or an in-region provider). A local 7B model needs another ~5 GB and is slow on CPU (about 20 s for a short answer), so it
   does not belong on a small VPS. No GPU is needed or used.
4. Decide who may sign. Approver keys are made **on their own devices**, never on the host.

## 1. The host

- Any Linux VPS with Docker and the Compose plugin. A domain name pointing at its address (Caddy gets the certificate by itself; ports 80
  and 443 must be reachable).
- A non-root login user in the `docker` group; SSH by key only; the firewall allows 22, 80, 443 and nothing else.

## 1b. Can the host be free? (checked 2026-10-03)

**Oracle Cloud "Always Free" can run this, with two traps.** What Oracle publishes today (its Always Free resources page, read 2026-10-03):
Ampere A1 Arm VMs with a monthly allowance of 1,500 OCPU-hours and 9,000 GB-hours, which is **2 OCPUs and 12 GB of RAM running all month** (up to
2 instances of 1 OCPU / 6 GB, or one of 2 / 12), 200 GB of block storage in total (a boot volume of at least 47 GB), 10 TB of outbound transfer a
month, and the boot images Oracle Linux and Ubuntu (Ubuntu is the one this kit was written for; check the Arm build of Docker images: the image
here is built for the machine it is built on, so **build it on the Arm VM, do not copy an x86 image**). Two AMD micro VMs (1/8 OCPU, 1 GB) also
exist but 1 GB cannot hold the runtime (about 650-780 MB resident) plus the notary and Caddy.

- **It was halved in June 2026.** Press and community reports (for example bex.co, 26 Sep 2026) say Oracle cut the A1 allowance from 4 OCPU / 24 GB
  to 2 OCPU / 12 GB on 15 June 2026 by editing the documentation, and from about 18 August began stopping instances above the new limit. 2 OCPU / 12 GB
  is still far more than this runtime needs (2 vCPU / 4 GB), but any older guide that says 4 / 24 is out of date, and Oracle can change it again.
- **Trap 1, idle reclaim.** Oracle's documentation says an Always Free instance is reclaimed (stopped) if, over 7 days, CPU (95th percentile) AND
  network are below 20% AND, for A1 shapes, memory is below 20%. This runtime idles at well under 20% on all three (about 0.8 GB of 12 GB is 7%), so
  **a quiet Always Free host would be reclaimed**, which would break exactly the "run seven days without anyone touching it" test (R57). The usual
  fix reported by users is to upgrade the account to Pay As You Go: Always Free resources stay free as long as usage stays inside their limits, and
  idle reclaim is reported not to apply to such accounts. That needs a payment card on file (it stays at 0 while inside the limits; check the card
  verification hold at sign-up, which this document cannot see). Treat "reported" as unverified until you have run it for a week.
- **Trap 2, capacity.** A1 instances are often "out of capacity" in popular regions at creation time; the home region is fixed at sign-up, so
  choose it with that in mind and expect to retry. Resources created outside the home region do not count as Always Free.
- **Free is not unconditional.** Accounts and instances have been terminated without notice in community reports. Keep the `/data` volume and the keys backed
  up off the host (see section 6).

**Alternatives, honestly:** a small paid VPS (for example Hetzner CX22, about 5 USD a month, 2 shared vCPU / 4 GB, as one source quotes; check the
current price) removes the reclaim and capacity risks at the cost of 60 USD a year. The always-free tiers of Google Cloud (e2-micro, 1 GB) and AWS
(time-limited credits) are too small or temporary for this runtime. My recommendation for R57: start on Oracle Always Free **with Pay As You Go
enabled**, because the point of R57 is to learn what breaks on a real Linux host, not to save 5 dollars; move to a paid VPS the day the free one is
reclaimed or throttled, since the kit is portable. Either way the domain is a separate need: Caddy needs a name that points at the host (a
registered domain is a few dollars a year; a free dynamic-DNS name also works for a trial but not for webhooks from LINE/WhatsApp, which require
a stable HTTPS name you control).

Not tested: any of this on Oracle. The kit has only been run on Docker Desktop (Windows). The first Linux/Arm run will find new defects.

## 2. Secrets and the first token (made on the host, once)

```bash
git clone <your fork of delentia-labs/Delentia-OS> && cd Delentia-OS/deploy/host
echo 'DELENTIA_DOMAIN=agent.example.org' > .env           # your real name
docker compose build                                       # first build is slow (torch, the 41 algorithms' dependencies); since Round 56 an edit to the source rebuilds only the last two layers (seconds)
./bootstrap.sh alice                                       # keys + the notary token + alice's API token (shown once)
```

`bootstrap.sh` exists because running the kit by hand failed in three ways (Round 55 trial, on Docker Desktop): the notary could not read a key
created by another uid; the runtime refuses to start on a public address until a token exists; and the notary's data volume was owned by root. It
creates each key as the uid that will read it (audit key 10001, notary key 10002), makes the shared notary token, and writes alice's token into the
data volume. Write down the two public keys it prints: the audit key's goes to anyone who will verify the audit trail, the notary's goes to the
witness (`AUDIT_ANCHOR_KEYS_JSON`) when you turn on anchoring. On Windows Git Bash set `MSYS_NO_PATHCONV=1` (the script does) or `/out` is rewritten.

## 3. First start

```bash
docker compose up -d
docker compose ps                                       # delentia: healthy after about 90 s
docker compose exec delentia delentia host-check
```

`host-check` must show **no FAIL**. Expected WARNs on a first start: no per-person token yet, no approver yet, no owner policy yet, anchoring
not scheduled. Fix them in order:

1. **More people:** `docker compose exec delentia delentia tokens create bob` prints a token once (only its hash is stored). Give it over a private
   channel. With any token present the server is in per-person mode: identity, memory and policy role come from the token.
2. **Approvers:** on each approver's own device run `delentia approvals keygen --out ~/approver.pem --role Security_Admin` (it prints the public key), then add the
   **public** key to `/data/home/.delentia/approvers.json` on the host:
   `docker compose exec delentia sh -c 'cat /data/home/.delentia/approvers.json'` to check. Until at least one approver exists, nothing that needs
   a signature (every write, every external tool not declared read-only) can ever run: that is the safe default, not a bug.
3. **Owner policy:** write the rules in the Desk page `/fdia` or with `delentia fdia ...`. Without a policy only the built-in floor judges tool calls.
4. **Model:** `docker compose exec delentia delentia model set <id> --provider openrouter` and put `OPENROUTER_API_KEY=...` in `secrets/runtime.env`
   (create the file; it is read by Compose and is ignored by git). Keep `EPISODE_BUDGET_USD` and `EPISODE_MAX_TOKENS` in `.env`, and set a
   **credit limit at the provider** as well: the per-episode cap does not stop a thousand episodes.
5. **Anchoring (A3), in this order** (Round 56 made it a setting instead of a rebuild):
   1. Print what the witness must learn: `docker compose exec delentia delentia audit-chain witness-entry --key-id host-1` (the runtime's audit
      key) and `docker compose exec --user 10002 notary delentia notary witness-entry --key-id host-notary-1 --key /run/secrets/notary_key` (the notary's).
      Each prints one JSON object `{"key_id": ..., "public_key_hex": ...}`.
   2. Add both objects to the witness's `AUDIT_ANCHOR_KEYS_JSON` (the fdia Worker variable in `delentia-mcp/ecosystem/packages/fdia/wrangler.jsonc`, a JSON
      array) and redeploy that Worker yourself. **Register before the first anchor or the witness refuses it.**
   3. In `.env` set `DELENTIA_AUDIT_ANCHOR_URL=<the fdia Worker's address>`, `AUDIT_ANCHOR_KEY_ID=host-1`, `NOTARY_ANCHOR_KEY_ID=host-notary-1`
      (optional `AUDIT_ANCHOR_EVERY_S`, default 900), then `docker compose up -d`. Both the runtime's chain head and the notary's log head are then published
      on that schedule. Empty values mean anchoring is off.
   4. Check it from the Desk (Audit page, "Check against the witness") or `delentia audit-chain check-anchors --url ... --key-id host-1`.
   5. **A second, independent witness (Round 58).** One witness is one operator to trust. A **git witness** appends each signed head to a file in a
      repository whose remote this host can push to but never rewrite:
      1. Create a private repository on a service you do not run on this host (any git host), and protect its main branch: no force-push, no deletion.
      2. Create a **deploy key** with write access to that repository only, keep its private half in a Docker secret, and let `git` on this host use it
         (`GIT_SSH_COMMAND` in `secrets/runtime.env`). A key that can push but not force-push is what makes the ledger append-only.
      3. `docker compose exec delentia git clone <remote> /data/witness-ledger`, then set in `.env`
         `AUDIT_WITNESSES=[{"type":"http","name":"worker","url":"<fdia Worker>","key_id":"host-1"},{"type":"git","name":"ledger","path":"/data/witness-ledger","remote":"origin","key_id":"host-1"}]`
         and `docker compose up -d`.
      4. `delentia audit-chain witness-status` says how many witnesses hold a recent head and how many rows are newer than the newest anchor (that window is
         what someone with root on this host could still rewrite); `delentia audit-chain check-witnesses` compares every witness with the chain;
         `delentia audit-chain export-proof --out proof.json` gives an auditor a bundle they verify with `scripts/verify_audit_bundle.py` without trusting this host.
      `host-check` (H07) passes only with two witnesses of different kinds.
   Until then do not describe the logs as tamper-proof. Even with two witnesses the honest wording is "tamper-evident against a compromise of this host":
   the window since the last anchor is not covered, and an attacker who controls every witness's operator is not covered either.

## 4. Smoke test (from your own machine)

```bash
curl -s https://agent.example.org/health                                                    # 200, no data
curl -s -o /dev/null -w "%{http_code}\n" https://agent.example.org/v1/desk/tools           # 401 without a token
curl -s -H "Authorization: Bearer $TOKEN" -X POST https://agent.example.org/v1/agent/run \
     -H 'content-type: application/json' -d '{"goal":"What can you do?"}'                   # an answer from the model you chose
```

Then check the three safety properties that matter, in this order: a write needs a signature (`delentia approvals list` shows it pending); a
second person's token cannot read the first person's memory; an unlisted sender gets nothing from a chat channel.

## 5. Opening a channel (one at a time)

Set the allowlist **before** the credentials: `DELENTIA_<CHANNEL>_ALLOWED_SENDERS` in the `environment:` block of `docker-compose.yml`, then the
bot credentials in `secrets/runtime.env`, then `docker compose up -d`. `host-check` flags a channel with credentials and an empty or `*` list.
Polling channels (Telegram, Signal, Email) need no inbound port. LINE and WhatsApp send webhooks to `https://<domain>/v1/gateways/<channel>/webhook`
and need their signature secrets (`LINE_CHANNEL_SECRET`, `WHATSAPP_APP_SECRET`).

## 6. Day two

Commands that read the notary's files must run as the notary's uid and, on Windows Git Bash, with `MSYS_NO_PATHCONV=1`:
`docker compose exec --user 10002 notary delentia notary head --db /notary/notary.db`, and
`delentia audit-chain verify --db /data/agentic.db` (the runtime's database is `agentic.db`; since Round 55 that is also the CLI default).


- **Back up** the `delentia-data` and `notary-data` volumes (SQLite: stop the stack or use `sqlite3 .backup`). The audit trail and memory live
  there. Never delete data: a hash chain with a gap is evidence of tampering, and the repository's Zero-Delete rule applies.
- **Update:** `git pull && docker compose build && docker compose up -d`; run `delentia host-check` again; run `delentia audit-chain verify`.
- **Rotate a token:** `delentia tokens revoke alice` then create a new one. **Lose an approver device:** remove its public key from `approvers.json`.
- **If something looks wrong:** `docker compose logs --tail 200 delentia`; `delentia audit-chain verify`; stop the stack first, investigate second.

## 7. Known gaps (do not promise these to a user)

Single worker only (the daemon and reminders are not coordinated across workers). One shared model endpoint. No automatic off-host backups.
The audit trail is re-verifiable (A1) and, with the notary, separated from the agent (A2); it is **not** externally anchored until step 3.5 is done (A3).
The shell sandbox is not a jail: it runs as the runtime's user inside the container. DNS rebinding is not covered by the crawler's address check.

