# Harness fixes after the paid runs of 2026-11-12/13: criteria written BEFORE the code (batch 2)

Status: committed before any of the changes below. Same rules as `HARNESS_FIX_CRITERIA_R113.md` (batch 1): nothing registered is changed, removed or rerun; prompts, oracles, sealed labels and stage ceilings are not touched.

## S5. `require_parameters` stays off by default and its refusal says what to do (the Architect confirmed on 2026-11-14)
Evidence: with `DELENTIA_OPENROUTER_REQUIRE_PARAMETERS=1` three models (claude-haiku-5.5, nova-pro-v1, kimi-k2) were refused on every call (HTTP 404 "No endpoints found that can handle the requested parameters") and the run reported only "model endpoint answered HTTP 404"; finding the cause took half a day.
* The default does not change (the variable is read only when set to a true value).
* An HTTP 404 from the model endpoint whose body names the requested parameters is reported as one sentence that names the setting: that no endpoint supports every parameter this run sends, and that unsetting `DELENTIA_OPENROUTER_REQUIRE_PARAMETERS` (or choosing another model) lets the call through. The text never carries the request body or a header.
* Checks (must FAIL on the code before the change): a real loopback server that answers 404 with that body: the error the provider raises names the variable; a plain 404 for another reason does not mention it; the default payload has no `require_parameters`; with the variable set it has.

## H2b. The experiment gateway's budget refusal is not "busy"
Evidence: the loop treats HTTP 429 as a transient provider error and asks again three times; the gateway answered every refusal by the budget guard with 429, so a run that had reached its limit kept asking and was recorded as `llm_error` after several refused calls.
* The gateway answers a refusal by the budget guard with HTTP 402 and the same typed body (`budget_exceeded`); 402 is not in the loop's transient list and is not a rate limit.
* Checks (must fail on the code before): the gateway's refusal status is 402; the loop's transient check says a 402 is not transient and a 429 still is.

## H3. The TC-003 live arm records what happened after the signature
Evidence: `research/daaes/delentia_session.py` records the stop reason, the final answer and the steps of the FIRST part of an episode only, so every row of arm d0 says `pending_approval` with an empty answer although the signer signed and the model went on to fix and test; the false-success reading then compared an answer that was never recorded with answers that were.
* The session summary gets three NEW keys and keeps every existing key unchanged (the scripted arms and their sealed bundles do not move): `final_stopped_reason`, `final_answer_after_approval` and `steps_after_approval`, filled from the continuation(s) after each approved resume.
* Only `tc003.run_live` (the live arm) reads them: its claim is read from the final answer after approval when there is one, and its `agent` record carries the final stop reason and all steps.
* Checks (must fail on the code before): a scripted session with `continue_after=True` and one approved write: the new keys exist and hold the continuation's answer and steps while `stopped_reason` is still `pending_approval`; a session with no approval has no new keys; `run_live` with a scripted provider that fixes the file after the signature reports the claim from the final answer and the final stop reason.

## Not in this batch
H16/H17 (a new W12 goal and the raw steps of W09/W12 in the result files), S11 (the answer guard and the W03 oracle on one rule: it changes what a person sees and needs its own measurement of what it removes from ordinary answers), H4/H5/H6/H7 (the driver), H13, H14, H15.
