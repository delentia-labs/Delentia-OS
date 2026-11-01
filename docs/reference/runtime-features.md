# Runtime features: data residency, jury, API hardening, owner policy, MCP, tokens, Tool Forge

> **Moved from the README on 2026-11-01.** The README is now a short entrance; this is the detail that used to sit in it, with the text unchanged except where a line starts with **[corrected 2026-11-01]** or **[context 2026-11-01]**. Anything here that is older than the code is history, not a description of today: the status of each capability is in [Release levels](https://github.com/delentia-labs/Delentia-OS/blob/main/../release/RELEASE_LEVELS.md) and the current test checkpoint is in [Testing](https://github.com/delentia-labs/Delentia-OS/blob/main/../testing/TESTING_CANONICAL.md).

These sections were written round by round as each feature was built. Each states what it does and what it does not; none of them is evidence that a language model drives the runtime well: no capable hosted model has done so yet.

### Regional Adapter and data sovereignty (`core/regional_adapter/`, `rct_control_plane/residency.py`)

You can do all of the following from the Desk (**Models** and **Sovereignty** pages) without the command line: pick a country, provider and model (or Other), declare where the endpoint processes data, test the connection (no prompt is sent, and an endpoint the policy would block is not contacted), and set the policy. A key typed there stays in the server's memory; only the name of its environment variable is saved.

The idea: any country or organisation plugs in its own AI, and personal data does not leave the boundary it sets.

Two parts, both real and tested:

1. **Routing** (`regional_adapter.py`): picks a model and prompt style per region and language, with compliance tags (TH PDPA, KR PIPA, CN PIPL, JP APPI, GDPR-ready for the US/EU entries) and a registry of pilot tenants.
2. **Enforcement** (`sovereignty.py`, `residency.py`, Round 52): a `SovereigntyPolicy` states the home region, the regions a call may reach, whether cross-border calls are allowed and what happens to personal data in one (`block`, `redact`, `allow`). Every model call is checked **before it is sent**:
   - an endpoint outside the allowed regions is refused (`stopped_reason=residency_blocked`, nothing leaves);
   - a permitted cross-border call that carries personal data is blocked or the data is replaced by placeholders; the scanner knows Thai national ID, Japanese My Number, Chinese resident ID and Korean RRN checksums, plus e-mail, phone and card numbers;
   - an endpoint whose location is unknown counts as cross-border (fail closed); a broken policy file raises instead of silently allowing;
   - the audit chain records the decision (kinds, counts, a hash), never the personal data.

```bash
# plug in your own AI: any OpenAI-compatible endpoint (a national provider, vLLM, llama.cpp, a gateway in your country)
delentia model set typhoon-v2-70b-instruct --provider openai-compat     --base-url https://llm.example.th/v1 --kind in_region --region TH --credential-env TYPHOON_TOKEN
delentia sovereignty set --region TH            # nothing may leave Thailand
delentia sovereignty check "Call 081-234-5678"  # would this text be sent? (nothing is sent)
```

This resembles data-localisation duties but is **not legal compliance by itself**. Thailand's PDPA does not require data to stay in Thailand; it restricts transfers abroad unless the destination has adequate protection or a basis such as consent or contract safeguards applies (s.28-29), and requires a lawful basis, purpose limits and data-subject rights. The policy therefore lets an owner choose "stay in-region" (strict) or "cross-border with redaction and a recorded legal basis". China's PIPL and Korea's PIPA are stricter about transfers. Have counsel confirm the setting for your case.

Not covered yet: egress by the crawl tool and the TypeScript MCP bridge are not checked by the policy, and the entry-point filter sees only text that goes through the model provider.

| Entry | Languages |
|-------|-----------|
| Thailand | TH, EN |
| Japan | JA, EN |
| South Korea | KO, EN |
| China | ZH, EN |
| Taiwan | ZH-TW, EN |
| Vietnam | VI, EN |
| Indonesia | ID, EN |
| US/Global | EN |

---

### API hardening (Round 53)

`delentia serve` rate-limits per caller (`DELENTIA_RATE_LIMIT`, default 600/60 s; an agent run costs 20 requests, a subagent fan-out 30). Model endpoints that keep failing are paused by a circuit breaker shared across episodes. Without `DELENTIA_API_TOKEN` the API answers only loopback clients; since Round 53 it also refuses a request whose `Origin` is a web page from another site or whose `Host` is not a loopback name (CORS used to be `*`, so any page the user opened could drive a local agent), and CORS answers only the local Desk and origins listed in `DELENTIA_CORS_ORIGINS`.

### The owner's policy for A (`rct_control_plane/fdia_policy.py`, Desk page **FDIA**, `delentia fdia`)

`F = D^I x A`: A is the accountable human. You write that responsibility down: which tools run freely, which need a human signature (from which approver role, how many distinct keys), which paths are off limits, which roles may ask, which tools are refused outright, and when a SignedAI jury must agree first (per rule, or per goal risk). Without a file only the built-in gate applies; with one, **every** tool call is judged, the most restrictive matching rule wins, a broken file refuses everything, and the policy can only tighten the built-in floor (path safety, the 0.5 threshold, repository writes always wait for a human). A signature never lifts a path or pattern you forbade.

```bash
delentia fdia template balanced --out ~/.delentia/fdia_policy.json
delentia approvals keygen --out ~/keys/sec.pem --trust alice --role Security_Admin
delentia fdia test delentia_write_repo_file --args '{"relative_path": ".env"}' --approved
```

The Desk page explains the equation with a live calculator and worked examples, edits the rules, and tests an unsaved draft. Roles come from the identity the server attached to the request, so use one API token per user if roles are to mean anything.

### Other MCP servers, web search, starter skills, three more channels

`~/.delentia/mcp_servers.json` lists MCP servers whose tools the agent may use as `mcp__<server>__<tool>`; they pass the same gate as the built-in tools (FDIA judgement, owner policy, audit), anything not declared read-only waits for a human signature, results are screened as third-party content, tool descriptions are screened against tool poisoning, and `delentia mcp inspect <server>` prints a digest you can pin. `delentia_web_search` works with a SearXNG instance or Brave (`DELENTIA_SEARCH_PROVIDER`) and says plainly when none is configured. `delentia skills starter install` adds 20 bundled playbooks (labelled as written by people, not learned). `delentia_crawl_url` now refuses cloud-metadata and this machine's own internal addresses. WhatsApp (signed webhook), Signal (through signal-cli-rest-api) and Email (IMAP/SMTP; the sender must be on the allowlist and the receiving server must have verified DKIM or SPF) join Telegram, Discord, Slack and LINE; every channel stays closed until its allowlist is set. Tested against local fakes of those services, not against the real ones. Thai prompt-injection screening: on a Thai set the rules did not see before they block about half of the attacks (15 of 31), about two thirds with a small local model's second opinion (21 of 31), with no harmless text blocked in 32; small, maintainer-written sets, indicative only.

### One token per person, signed policy changes, a second opinion for CORD

`delentia tokens create alice` prints a token once and stores only its SHA-256 in `~/.delentia/api_tokens.json`; with any entry the server is in per-user mode and the identity (namespace, memory, FDIA role) comes from the token, never from the request body. Since Round 62 a token is either a person's or an owner's (`delentia tokens create alice --owner`, `delentia tokens owner alice`): a person may talk to the agent and manage their own jobs, tasks, approvals and memory; every other route (the Desk, audit, policies, the MCP gateway) is default-denied for them. On a server with an API token, changing or turning off the owner's policy waits for an approver signature bound to that exact policy. `DELENTIA_CORD_SECOND_OPINION=flag|block` plus `delentia model set <small-model> --profile classifier` adds a small model's judgment of goals and third-party content on top of the rules (it can only add a finding and fails open); on a public labelled set the rules block 10% of attacks and rules + qwen2.5:7b 23%, with no false blocks. Tool Forge also has a Desk page (`/forge`).

### Parallel tool calls and the Tool Forge

`DELENTIA_PARALLEL_TOOLS=1` lets the model ask for several independent tool calls in one decision; they run as waves over the Execution Graph IR (`dag_executor.py`), every call is gated before any runs, and one refusal stops the batch. Measured on real tools: four independent 0.5 s waits 3.8x, a diamond 1.3x, a chain 1.0x, CPU-bound Python about 1.1x (`scripts/dag_wave_benchmark.py`).

`delentia forge` is Genesis grown into a governed loop: repeated unmet goals (`forge gaps`) lead to a proposed pure-function tool (written by the model or by you; checked statically, smoke-tested in another process), a human signs the exact code hash, and only then can the agent call it (`delentia_run_forged_tool`). Pure functions only; not a jail against someone who can also get a human to sign.
