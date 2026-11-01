# How Delentia OS compares with other agent runtimes

Status: **no head-to-head result exists that shows Delentia is better at anything.** This page says what we read, what we ran, and where the designs differ, so that you can decide whether the difference matters for you. Nothing here says another project lacks governance: please check their current documentation, because everything below about other projects is a snapshot.

## What we compared against, and how

| Project | How we know about it | What we actually ran |
|---|---|---|
| **Hermes Agent** (Nous Research, MIT licence) | Its public documentation and repository, read in October 2026 (versions 0.22.x). | One fixed test: the real agent in a container, with the same local model and the same four tasks as Delentia and a plain loop (the DAAES TC-003 harness). See below. |
| Other agent frameworks and runtimes | Not evaluated. We list none of them as better or worse. | Nothing. |

If you maintain one of these projects and a sentence here is wrong, please open an issue and we will correct it.

## The one thing we measured together

Setting: `qwen3:8b` on a CPU through Ollama, four coding tasks, one run each. The three arms were a plain loop (b0), Delentia's loop (d0) and the real Hermes agent in a container (h0).

| Arm | Tasks passed | Notes |
|---|---|---|
| b0 plain loop | 0 of 4 | one answer claimed success that had not happened |
| d0 Delentia | 0 of 4 | after a fix for an unusable reply, episodes ran 7 to 13 model calls |
| h0 Hermes | 0 of 4 | two of four answers began by saying the tests failed and ended by saying they all pass, on a workspace that had not changed |

**This tells you nothing about the systems.** The model is the floor: it failed the tasks in every arm. The numbers that did differ are descriptive: Hermes' prompt was 5.0 to 9.8k tokens per call against 1.1 to 2.5k for the others, and Hermes' version at the time refused any model window under 64k tokens, so it had to be run by declaring a window the model was not actually served with (a disclosed deviation, in the run notes). Raw results and the harness are in `research/daaes/`.

## Where the designs differ (from reading the documentation)

| Question | Delentia OS | Hermes Agent (per its documentation) |
|---|---|---|
| **What is the centre of the design?** | A fixed cycle every episode passes: check the request, plan, route, judge each tool call, compress, verify, record, learn. | A capable general agent with a very wide set of tools, platforms and a large skills ecosystem. |
| **Who decides risky actions?** | An owner policy plus a built-in floor decides per call; anything that writes, sends or runs code waits for a person's **Ed25519 signature over that exact action**, single use, expiring. | Approval settings for dangerous commands. We did not find an equivalent of signed, per-action, single-use approvals in the documentation we read; check the current docs. |
| **Text from outside** | Reading outside text (a page, a file in a download folder) *taints* the episode; from then on every side-effect tool needs a signature whatever the model says. Measured against a scripted worst-case model: [threat model](security/THREAT_MODEL.md). | We did not find a rule of this kind described in the documentation we read; check the current docs. |
| **The record** | Every step is in a hash-chained, signed audit log that can be verified offline, anchored at an outside witness, and where one person's text can be erased while the chains still verify. | Session history and logs; we did not find tamper-evidence described. |
| **Platforms and tools** | Seven messaging channels, 50 tools, external MCP servers through the same gate, a Desk web page, a Windows installer. | A much wider set (about twenty messaging platforms, several terminal backends, a desktop app). **Breadth is where Hermes is ahead; Delentia does not claim parity.** |
| **Community and maturity** | One author, no outside users yet, experimental. | A large and active open-source community. |
| **Where it runs** | Your machine. No hosted service. | Self-hosted, plus a hosted offering from its company. |

## How to choose

* If you want **the widest set of integrations and a large community today**, use a mature general agent. Delentia is not that.
* If your problem is **"I let an agent act for me and I need a person to approve the risky parts, and to be able to show afterwards exactly what happened"**, Delentia is built for that, and you can check how with the commands on the [threat model](security/THREAT_MODEL.md) page. It is early, and you would be among its first users.
* The two are not exclusive: any HTTP service that publishes an OpenAPI document can be put behind Delentia's gate (`python -m rct_control_plane.openapi_mcp_bridge --help`), and Delentia can sit behind an MCP client as a tool server.

## What would change this page

A pre-registered, same-model, same-budget ablation on a model that can do the tasks, with raw outcomes published (the harness is in `research/`; the criteria for the first paid stages are in `research/PREPAID_CRITERIA_R103.md`). Until then, read this page as "different design choices", not "better".
