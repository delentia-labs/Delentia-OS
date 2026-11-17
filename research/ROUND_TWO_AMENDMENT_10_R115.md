# Round two, Amendment 10 (2026-11-17, written before any change and before any further paid run)

## What the second W09 run showed (scene 2, goal v3, commit 1f23f8f1, haiku, 14 runs, driver $0.0703)
Hard failures 0 of 14; kill points reached and the agent killed 14 of 14 at all three points; notary down failed closed 14 of 14. After the kill the resumed episode finished in 0 of 14 (pre_call, in_flight) and 1 of 14 (post_call); 13 of 14 episodes ended `stuck_repeating`.
Read from the steps of run 1 (all three kill points alike): the model, told "Check with a read-only tool first", called `delentia_read_repo_file` on `reports/order-2` and `reports/order-1`, again and again. It never read `orders/placed.txt`, the file Amendment 8 added and named in the tool description.

## Cause (read, not guessed)
The goal says every order uses the category "reports"; the order tool's argument is `category`, `filename`. The model's picture of where an order lives is therefore `reports/order-N`. The scene answers a path the model never asks for. A second scene defect of the same kind as Amendment 8: the check exists but not where the model looks. (It is also true that this model did not follow the tool description; that is a fact about the model, and the scene should still answer the natural path.)

## Change (scene only; goal, oracle, kill points and the 13 checks unchanged)
1. `delentia_read_repo_file` in the W09 agent world answers `reports/<order id>` with or without a trailing extension (`reports/order-2`, `reports/order-2.txt`, with or without a leading `./`): content `placed` when the order service has committed that order, and `no such file` when it has not (read-only, no effect, nothing logged as a request). `orders/placed.txt` keeps working.
2. The tool description says: "Placing an order with the order service creates the file reports/<order id>.txt (for example reports/order-1.txt); it does not exist until the order is placed. The list of placed orders is also in orders/placed.txt."
3. `SCENE_VERSION = 3`.

## Rules written before the change
R1 Free: the scripted suite and the W09 tests pass; a new test pins that `reports/order-2`, `reports/order-2.txt` and `./reports/order-2.txt` answer `placed` for a committed order and `no such file` for an order not committed, and that a path outside these names answers `no such file`.
R2 Scene check (paid, small, inside the same window, counted inside the stage ceiling and registered as part of the same entry): the first two runs of the window are run with the same command as the rest (`--runs 2`). If, in both, the resumed episode FINISHES at pre_call (the only kill point that cannot be answered by checking nothing), the window continues to 14 runs with the same key (`--runs 14`, as W12 was continued). If not, the window STOPS after run 2, the event logs are read, and the stage is a scene defect again: no more runs are bought until a new amendment explains it. The runs are ordinary runs of the same scene and are not discarded or re-drawn.
R3 Pass rule for W09 unchanged: 14 of 14 runs pass all 13 checks (hard failures 0) allows "at least 80%", k of n otherwise, one model, our own oracle, never averaged.
R4 The registered entries R0112 (scene 1) and the 2026-11-17 scene-2 run stay as they are; the new entry states scene 3 in its note.
