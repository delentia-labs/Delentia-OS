# Local trial of the audit tiers (real processes, one machine)

Run 2026-10-09 19:05 by `scripts/trial_notary_witness_local.py`. 11/11 checks passed.

| check | result | detail |
|---|---|---|
| the notary and the host have different signing keys | pass | a34403943d63.. vs 7a00a38ae547.. |
| the notary is its own process and answers on loopback | pass | pid 26232, port 52466 |
| every tool call was recorded by the notary | pass | {"enabled": true, "url": "http://127.0.0.1:52466", "episode_id": "a9d9514415b648bbb267af12e21dda7e", "receipts": 4, "last": {"kind": "episod |
| audit-chain verify passes against the host's public key | pass | head       : seq=27 hash=e1025f2db44ed4d20ea95bbb1fa460aed8a3f6b27d423125d6de6d4e6c93fb66 |
| notary verify passes against the notary's public key | pass | } |
| before any anchor the status says the log is not yet held by a witness | pass | {   "configured": 1,   "problem": "",   "fresh_witnesses": 0,   "witnesses": [     {       "name": "git-mirror",       "type": "git",       "last_anchored_entri |
| anchor-all publishes the signed head to the git witness | pass | ok   git-mirror: anchored |
| check-witnesses finds the witness consistent with the chain | pass | [   {     "witness": "git-mirror",     "reachable": true,     "ok": true,     "checked": 1,     "problems": [],     "highest_anchored": 27   } ] |
| the standalone verifier (no Delentia code) accepts the exported proof | pass | VERIFIED: 27 rows (27 signed), 1 witness anchor(s); key from the argument |
| with the notary down a tool call does not run (fail closed) | pass | notary_unavailable |
| an edited notary database fails notary verify (with a verification message, not a usage error) | pass | } |

## What this does not show

- The notary ran as the **same operating-system user** as the agent. Separation of duties (tier A2) needs another OS user or machine: an account the Architect creates; this script creates none.
- The witness is a bare git repository **on the same disk**. An independent witness (tier A3) is another machine, a protected branch of a hosted repository, or the deployed Worker.
- Nothing here defends against someone with root on this machine, and no claim of tamper-resistance follows from it. The accurate sentence is: the log is hash-chained and signed, and the mechanism for external anchoring works end to end when a witness the host cannot rewrite is configured.
