# What the model-free demo prints in English (a real run)

Produced by `delentia demo init --lang en`, `delentia demo run compare --scripted`, `delentia demo run edit --scripted` and `delentia demo approve <id> --scripted` on a machine with no model installed. `--scripted` replaces only the model; the files, tools, safety gate, signature check and audit log in these outputs are real. The dates and the approval id change on every run. The Thai version of the same run is [SAMPLE_OUTPUT.md](SAMPLE_OUTPUT.md).

## 1. `delentia demo init --lang en`

```text
Demo folder: ~/delentia-demo
Created: lang.txt, quotes/vendor_a.md, quotes/vendor_b.md, quotes/vendor_c.md, README_EN.md, keys/demo-approver.pem, keys/audit.pem, data/originals.json
Next: delentia demo run compare --scripted   (no model needed)   or   delentia model show, then   delentia demo run compare
```

## 2. `delentia demo run compare --scripted`

```text
# Run result <date time>
> This run uses a SCRIPTED stand-in for the model (not a real model): the order of the steps and the wording of the answer were written in advance. What is real is the tools, the files, the safety gate, the wait for a signature and the audit chain. This result says nothing about the ability of any model.

**Goal:** Read the quotes in the files quotes/vendor_a.md, quotes/vendor_b.md, quotes/vendor_c.md, build a price comparison table, then say which vendors are within the 15,000 USD budget. Do not edit the original files and do not send any data out.
**Model:** script (not a real model)
**Status:** llm_finished - finished by itself: the model answered the question
**Steps:** 4 - time 0.8 s


## What the agent did
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_a.md"} -> got a result of 228 characters
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_b.md"} -> got a result of 224 characters
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_c.md"} -> got a result of 221 characters
- (answered the question)

## How the safety gate (FDIA) judged each step
- `delentia_read_repo_file`: D=0.6 I=1.5 A=1.0 -> F=0.4648 (threshold 0.5) -> passed (a read your policy allows: the D/I threshold is not applied to reads)
- `delentia_read_repo_file`: D=0.6 I=1.5 A=1.0 -> F=0.4648 (threshold 0.5) -> passed (a read your policy allows: the D/I threshold is not applied to reads)
- `delentia_read_repo_file`: D=0.6 I=1.5 A=1.0 -> F=0.4648 (threshold 0.5) -> passed (a read your policy allows: the D/I threshold is not applied to reads)

## Text from outside (taint)
- This episode read text from outside: delentia_read_repo_file (quotes/vendor_a.md is in a folder declared untrusted) -> anything that could send data out or change something now needs a person to sign

## Answer
Quote comparison table (sorted by price, low to high; budget 15,000 USD)

| Vendor | Price (USD) | Duration (days) | Against the budget |
|---|---|---|---|
| Harbor HVAC | 9,900 | 9 | within budget |
| Northwind Cooling | 12,500 | 5 | within budget |
| Polar Systems | 16,800 | 3 | over budget |

Summary: the lowest price within the budget is Harbor HVAC at 9,900 USD (9 days)

## The answer checked against what is known to be true (not the agent's own check)
- passed: the table has the price of all 3 quotes
- passed: says that Harbor HVAC is within the 15,000 USD budget
- passed: says that Northwind Cooling is within the 15,000 USD budget
- passed: does not say that Polar Systems (over budget) is within the budget
- passed: the original files were not changed

## Look-back record
- audit chain: intact - 11 rows - 11 signed
- 'not changed' only means the hashes of the original files still match those taken at init. It is not a statement that the data inside the quotes is true.

Result file: ~/delentia-demo\results/<time>-compare-5147.md
```

## 3. `delentia demo run edit --scripted` (it stops: nothing was written)

```text
# Run result <date time>
> This run uses a SCRIPTED stand-in for the model (not a real model): the order of the steps and the wording of the answer were written in advance. What is real is the tools, the files, the safety gate, the wait for a signature and the audit chain. This result says nothing about the ability of any model.

**Goal:** Change the total price in quotes/vendor_a.md to 14,000 USD
**Model:** script (not a real model)
**Status:** pending_approval - stopped and is waiting for a person: this step needs an approver's signature before it runs
**Steps:** 2 - time 1.0 s


## What the agent did
- `delentia_read_repo_file` {"relative_path": "quotes/vendor_a.md"} -> got a result of 228 characters
- `delentia_patch_repo_file` {"relative_path": "quotes/vendor_a.md", "old_text": "Total price: 12,500 USD", "new_text": "Total price: 14,000 USD"} -> waiting for an approver's signature
- **Waiting for approval, id `f483af2136b0`** -> `delentia demo approve f483af2136b0`

## How the safety gate (FDIA) judged each step
- `delentia_read_repo_file`: D=0.675 I=1.1 A=1.0 -> F=0.649 (threshold 0.5) -> passed

## Text from outside (taint)
- This episode read text from outside: delentia_read_repo_file (quotes/vendor_a.md is in a folder declared untrusted) -> anything that could send data out or change something now needs a person to sign

## The answer checked against what is known to be true (not the agent's own check)
- passed: the original files were not changed before the signature

## Look-back record
- audit chain: intact - 20 rows - 20 signed
- 'not changed' only means the hashes of the original files still match those taken at init. It is not a statement that the data inside the quotes is true.

Result file: ~/delentia-demo\results/<time>-edit-c29b.md
Waiting for approval, id f483af2136b0  ->  delentia demo approve f483af2136b0 --scripted
```

## 4. `delentia demo approve f483af2136b0 --scripted` (you sign; only now does the file change)

```text
# Run result <date time>

**Goal:** Change the total price in quotes/vendor_a.md to 14,000 USD
**Model:** script (not a real model)
**Status:** llm_finished - finished by itself: the model answered the question
**Steps:** 1 - time 0.9 s

**Cost:** prompt 831 - completion 46 - no money charged (no model that bills)

## What the agent did
- (answered the question)

## Text from outside (taint)
- This episode has not read text from outside

## Answer
Changed the total price in quotes/vendor_a.md to 14,000 USD, as approved.

## The answer checked against what is known to be true (not the agent's own check)
- passed: after approval, the files that changed are: quotes/vendor_a.md

## Look-back record
- audit chain: intact - 26 rows - 26 signed
- 'not changed' only means the hashes of the original files still match those taken at init. It is not a statement that the data inside the quotes is true.

> This signature used the demo key, which sits on the same machine as the agent, only so that you can see the whole flow. A real approval is signed from another device (`delentia approvals sign`).

> The sample file was changed (as approved). Before you run another demo that uses the quotes, run `delentia demo reset` (it keeps a copy of the changed file in results/ and deletes nothing).

Result file: ~/delentia-demo\results/<time>-approve-f483af2136b0.md
```

