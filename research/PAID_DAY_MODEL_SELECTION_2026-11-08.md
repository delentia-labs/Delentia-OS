# Paid day: vision model for stage PR, chosen before any spending (2026-11-08)

Chosen by the Architect, in chat, on 2026-11-08: **`anthropic/claude-haiku-5.5`**, one model only.

- Estimate for stage PR (57,000 prompt + 21,000 completion tokens, 1.5x margin, live public prices on 2026-11-08: $0.10 in / $0.50 out per million tokens): about $0.024, against the stage ceiling of $0.75.
- Command when the key is set: `python scripts/paid_day.py stage3 --vision-models anthropic/claude-haiku-5.5`
- Not yet checked: that this model has an endpoint under `DELENTIA_OPENROUTER_DATA_COLLECTION=deny`. Stage P0 tests it; if it cannot be served under that setting, the stage is `not_run` and the choice is made again, in writing, before any retry.
- Reading rules are those of `research/PREPAID_CRITERIA_R103.md` section PR (descriptive only: no claim about vision understanding or RCT-7 benefit comes from one model).
- One model means differences between vendors cannot be seen in this run; that limit is stated in the result.
