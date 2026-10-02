# Host runbook: from an empty server to the first outside user

Status (2026-10-02): written from the code and from measurements on the development machine. The container files in this folder have been
syntax-checked (`docker compose config`) but **not built or run**: Docker Desktop was not running when they were written. Treat the first run
on the host as the test, and fix this file with what you find.

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

## 2. Secrets (made on the host, once)

```bash
git clone <your fork of delentia-labs/Delentia-OS> && cd Delentia-OS/deploy/host
mkdir -p secrets && chmod 700 secrets
docker compose build                                   # first build is slow (torch, the 41 algorithms' dependencies)
docker compose run --rm --no-deps -v "$PWD/secrets:/out" delentia delentia audit-chain keygen --out /out/audit.pem
docker compose run --rm --no-deps -v "$PWD/secrets:/out" delentia delentia notary keygen --out /out/notary.pem
python3 -c "import secrets; print(secrets.token_urlsafe(48))" > secrets/notary_token
echo 'DELENTIA_DOMAIN=agent.example.org' > .env      # your real name
```

Write down the two public keys the keygen commands print: the audit key's goes to anyone who will verify the audit trail, the notary's
goes to the witness (`AUDIT_ANCHOR_KEYS_JSON`) when you turn on anchoring.

## 3. First start

```bash
docker compose up -d
docker compose ps                                       # delentia: healthy after about 90 s
docker compose exec delentia delentia host-check
```

`host-check` must show **no FAIL**. Expected WARNs on a first start: no per-person token yet, no approver yet, no owner policy yet, anchoring
not scheduled. Fix them in order:

1. **People:** `docker compose exec delentia delentia tokens create alice` prints alice's token once (only its hash is stored). Give it to her
   over a private channel. With any token present the server is in per-person mode: identity, memory and policy role come from the token.
2. **Approvers:** on each approver's own device run `delentia approvals keygen --out ~/approver.pem --role Security_Admin` (it prints the public key), then add the
   **public** key to `/data/home/.delentia/approvers.json` on the host:
   `docker compose exec delentia sh -c 'cat /data/home/.delentia/approvers.json'` to check. Until at least one approver exists, nothing that needs
   a signature (every write, every external tool not declared read-only) can ever run: that is the safe default, not a bug.
3. **Owner policy:** write the rules in the Desk page `/fdia` or with `delentia fdia ...`. Without a policy only the built-in floor judges tool calls.
4. **Model:** `docker compose exec delentia delentia model set <id> --provider openrouter` and put `OPENROUTER_API_KEY=...` in `secrets/runtime.env`
   (create the file; it is read by Compose and is ignored by git). Keep `EPISODE_BUDGET_USD` and `EPISODE_MAX_TOKENS` in `.env`, and set a
   **credit limit at the provider** as well: the per-episode cap does not stop a thousand episodes.
5. **Anchoring (A3):** set `DELENTIA_AUDIT_ANCHOR_URL` / `DELENTIA_AUDIT_ANCHOR_KEY_ID` for the notary and the runtime once the notary's public key is
   registered at the witness (Round 49 doc, section 5). Until then do not describe the logs as tamper-proof.

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

- **Back up** the `delentia-data` and `notary-data` volumes (SQLite: stop the stack or use `sqlite3 .backup`). The audit trail and memory live
  there. Never delete data: a hash chain with a gap is evidence of tampering, and the repository's Zero-Delete rule applies.
- **Update:** `git pull && docker compose build && docker compose up -d`; run `delentia host-check` again; run `delentia audit-chain verify`.
- **Rotate a token:** `delentia tokens revoke alice` then create a new one. **Lose an approver device:** remove its public key from `approvers.json`.
- **If something looks wrong:** `docker compose logs --tail 200 delentia`; `delentia audit-chain verify`; stop the stack first, investigate second.

## 7. Known gaps (do not promise these to a user)

Single worker only (the daemon and reminders are not coordinated across workers). One shared model endpoint. No automatic off-host backups.
The audit trail is re-verifiable (A1) and, with the notary, separated from the agent (A2); it is **not** externally anchored until step 3.5 is done (A3).
The shell sandbox is not a jail: it runs as the runtime's user inside the container. DNS rebinding is not covered by the crawler's address check.
