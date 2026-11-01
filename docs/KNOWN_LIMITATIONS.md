# Known limitations

Status: **experimental, single-author, pre-1.0 in spirit** (the package number is 2.x for historical reasons; see [`docs/release/VERSIONING_POLICY.md`](release/VERSIONING_POLICY.md)). This page is the one place to read before you rely on Delentia OS for anything. If something here is too generous, please open an issue: we would rather correct this page than have it flatter the project.

Each line says what is **not** true yet, and what would have to happen for it to become true.

## About the evidence

| Limitation | What it means | What would change it |
|---|---|---|
| **No result with a capable model.** | Every measurement of the whole loop used a scripted model or small local models (3B to 8B on a CPU). A strong hosted model has not driven this runtime under test conditions, so there is **no evidence yet that Delentia makes a good model more reliable**. | The first paid canary on hosted models, pre-registered criteria are already in `research/PREPAID_CRITERIA_R103.md`. |
| **Small local models are weak and slow here.** | On a probe of simple goals, qwen2.5:7b completed 3 of 5 and llama3.2:3b 0 of 5; qwen3:8b completed 4 to 5 of 5 but on a harder fixed task set (DAAES TC-003, 4 tasks) it and a competing agent both scored 0 of 4. One goal takes from one to several minutes on a CPU. | A model that can use tools well; a GPU or a hosted model. |
| **Most of the author's test sets are the author's own.** | Sets written by the person who wrote the rules are regression guards, not independent evidence. The owner's own labelled holdouts exist for the clarity judge and critic (four sets). Against the pass rules written beforehand, a local 8B model met one rule, only at the edge of both of its bounds (set 3, with extra context), and did not meet the others; the follow-up set (set 4) did not reproduce that pass. | Outside testers; holdouts labelled by someone other than the author. |
| **"Passes N tests" is not "works".** | The public test count (see the README) says the code does what its tests say. It says nothing about how well any model uses it. | A pilot with a written success rule. |
| **Nothing is proven about "better than X".** | There is no head-to-head result against another agent runtime that shows an advantage. See [COMPARISON.md](COMPARISON.md). | A pre-registered ablation (the harness exists; it has not been run with a capable model). |

## About safety and the audit trail

| Limitation | What it means | What would change it |
|---|---|---|
| **Logs are tamper-evident only if you add a witness.** | Hash-chained and signed is the default. An outside witness (public git ledger, Cloudflare Worker, RFC 3161) and a separate-account notary exist but are **off until you configure them**. Without them, someone who controls the machine can rewrite history. We never say "tamper-proof". | Configure a witness; an independent review. |
| **The agent and the keys share a machine.** | The local shell is not a jail: it runs as your OS user. Commands that name key files are refused, which is a speed bump. | Keep approver keys on another device; run the notary as another OS user; use the Docker/SSH sandbox backends. |
| **Taint stops actions, not wrong answers.** | A poisoned page can still make an answer wrong. Attacks that need no tool, only words, are not addressed. | Verification against sources (a research item, not shipped). |
| **Signing on screen vs. signing the digest.** | An approval device signs the digest of the action, not the text you see. A compromised page could show you different words. | Two signers for the riskiest actions; a trusted local page (the Desk opens on `localhost`). |
| **Windows Hello was tested with a software stand-in only.** | The passkey flow was exercised against a real server with a browser-side authenticator that follows the standard. A real Windows Hello prompt (fingerprint, face or PIN) has not been tried by anyone yet. | A tester with Windows Hello, a phone passkey or a security key. |
| **Not multi-tenant.** | People are separated by a namespace column and default-deny routes. Do not put two organisations that distrust each other on one host. | A design partner who needs it. |
| **No compliance certification, no penetration test.** | Nothing here is certified for PDPA, GDPR or anything else. Per-person erasure exists and is tested, with documented leftovers (old backups, the separate skills database). | An independent assessment. |

## About the product

| Limitation | What it means | What would change it |
|---|---|---|
| **No hosted service.** | Everything runs on your machine. There is no sign-up and nothing to log in to. | Not planned before a design partner asks. |
| **The Windows installer is not code-signed.** | Windows SmartScreen will warn. Check the download against `SHA256SUMS.txt`. It has been installed on the author's machine and on a clean CI runner, **not** on a stranger's computer. | A signing certificate; a second-computer test. |
| **macOS is untested.** | Linux runs in CI; the installer is Windows-only; macOS has had no testing at all. | A macOS tester. |
| **Linux/Arm and long runs.** | The host kit was run on x86 under Windows. The longest clean run is six hours; the 72-hour and seven-day soaks are not done. | A Linux host and time. |
| **Not every Desk page is in both languages.** | The main pages are Thai and English. Some Advanced pages carry English-only sentences in the Thai interface. | Ongoing; measured by `apps/gui/scripts/a11y-e2e.mjs --th-coverage`. |
| **Accessibility is measured by a machine, not by people.** | The Desk passes an automated checker (axe, WCAG 2.2 AA rules) on every page in both languages and a keyboard walk. A real screen reader and high-contrast mode were not tested. | A tester who uses assistive technology. |
| **The 41 algorithms are mostly advisory.** | All have real logic and tests, but five act directly inside the loop; most run as optional stages. The private service layer is not part of this repository. | See `research/ALGORITHM_BEHAVIOUR_MAP.md`. |
| **RCT-7 thinking is partial.** | The parts a rule can decide (requirements read from your own words, a plan shown before the first tool, the difference report) are built and on where a person is present. The parts that need a language reader (spotting every unclear request, checking every claim) are opt-in and were only measured on small sets with small models. | A capable model and an independent holdout. |
| **Law Pack is a retrieval aid, not legal advice.** | It answers only from the statute text *you* import and labels anything else. It does not know laws that changed after the text you imported. | Always have a lawyer check. |
| **Memory by meaning needs a download.** | Without a local embedding model the default recall is lexical and misses paraphrases; the recommended model for Thai (bge-m3) is 1.16 GB. | `delentia setup` offers it. |

## About the project

* **One author, and the code is largely written with AI assistants.** Delentia is built by one person who directs AI coding assistants (Claude Code and Codex) rather than writing the code line by line. A visible share of commits carry a `Co-Authored-By` trailer. Review, testing and decisions are the author's; the history is public, so you can judge it.
* **Thin bus factor.** There is no team, no support contract and no promise of response time beyond the one in [SECURITY.md](https://github.com/delentia-labs/Delentia-OS/blob/main/SECURITY.md).
* **Names you may see in older material.** "RCT" in older file names is the project's earlier name. Withdrawn claims (a hallucination rate, a seven-model consensus, "62 microservices", an uptime figure) are listed in [`docs/distribution/CLAIM_REGISTRY.md`](distribution/CLAIM_REGISTRY.md).

If you can reproduce something here being *better* than stated, that is welcome too: open an issue with the command you ran.
