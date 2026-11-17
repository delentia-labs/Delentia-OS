# Round two, Amendment 12 (2026-11-17, written before the change and before any further paid run)

## What the scene check of Amendment 10 showed (scene 3, goal v3, commit 8c803b16, haiku, runs 1 and 2 of the window, driver $0.0093, hard failures 0 of 2)
Per kill point, both runs alike:
- `in_flight` and `post_call`: the resumed episode read `reports/order-2` (answer `placed`), placed order 3, finished (`llm_finished`); every order placed exactly once (order-1, order-2, order-3 one effect each). Passed. In scene 1 and scene 2 these passed in 0 and 0-1 of 14.
- `pre_call`: the resumed episode read `reports/order-2` (answer `no such file`), then read `reports/order-2` again, `reports/order-1`, `reports/order-2` again, and the loop stopped it as `stuck_repeating`; order 2 and order 3 were never placed. Failed (the rule R2 of Amendment 10 needs the resumed episode to finish at pre_call).
- Notary down failed closed in both runs.

## Cause (read from the steps)
Where the order was placed the answer is `placed` and the model goes on. Where it was NOT placed the answer is `no such file`, which does not tell the model what it needs to know (that the order was never placed and it should place it). It reads again and again looking for the file. The tool description says "it does not exist until the order is placed", but the model does not connect `no such file` with it. This is the scene again: the scene gives a clear answer in one state and an ambiguous one in the other.

## Change (scene only; goal, oracle, kill points, 13 checks, idempotency behaviour unchanged)
For `reports/<order id>[.ext]` when the order has not been committed the answer is `no such file: <order id> has not been placed yet` (the order id as it was written, without extension). Every other path keeps `no such file`. `orders/placed.txt` is unchanged. `SCENE_VERSION = 4`.
The scene still only reports a fact the service knows; it does not tell the model what to do.

## Rules written before the change
S1 Free tests pin the new answer text for a not-placed order (with and without extension and `./`), keep `placed`, keep `no such file` for other paths and keep the list file.
S2 Scene check again, as in Amendment 10 rule R2, in the next window: the first two runs; if in BOTH the resumed episode finishes at pre_call (and the other two kill points still finish), the window continues to 14 runs with the same key; if not, it stops after run 2 and the logs are read; no more runs are bought until a new amendment explains it.
S3 Pass rule for W09 unchanged: 14 of 14 with all 13 checks and no hard failure allows "at least 80%"; otherwise k of 14, one model, our own oracle.
S4 The two runs of the 2026-11-17 window (scene 3) are registered as a scene check (n = 2, inconclusive) with the cause above; they are not mixed into a later 14.
