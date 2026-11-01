# The FDIA Equation: framework, computation, enforcement

> **Moved from the README on 2026-11-01.** The README is now a short entrance; this is the detail that used to sit in it, with the text unchanged except where a line starts with **[corrected 2026-11-01]** or **[context 2026-11-01]**. Anything here that is older than the code is history, not a description of today: the status of each capability is in [Release levels](https://github.com/delentia-labs/Delentia-OS/blob/main/../release/RELEASE_LEVELS.md) and the current test checkpoint is in [Testing](https://github.com/delentia-labs/Delentia-OS/blob/main/../testing/TESTING_CANONICAL.md).

## The FDIA Equation

$$F = D^I \times A$$

The equation has three layers that should not be mixed up: the **framework** (a way of thinking about the future), a **computational model** (an action score with defined ranges), and the **enforcement** (policy and signed approvals that the execution path actually checks). The first column is what the creator means; the second is what the runtime computes.

| Symbol | Meaning in the framework | What the runtime computes |
|--------|---------|---------|
| **F** | **Future**: the outcome that actually happens, not a prediction | An action-admissibility score. It is not the future and not a calibrated probability |
| **D** | **Data**: reality and experience, good and bad, constraints | A data-evidence score in [0, 1] built from the person's own files, memory, verified skills, track record and the clarity of the request |
| **I** | **Intent**: the exponent that gives the data direction | A strictness value, about 0.5 to 2, from the kind and risk of the goal. With D in [0, 1] a larger I makes F *smaller* for the same D |
| **A** | **Architect**: the human who designs, decides and answers for the outcome | The owner's policy plus a verifiable Ed25519 signature for protected actions |

> **Because D is in [0, 1], raising I lowers F for the same D** (0.8^2 = 0.64 < 0.8^1 = 0.8): a clearer, more demanding intent needs better data to pass. This is a property of that range; for D > 1 the exponent amplifies instead, and for D = 1 it has no effect. If D > 0 and I = 0 the raw arithmetic gives D^0 = 1, so the runtime returns 0 for D ≤ 0 or I ≤ 0 as an added rule, not as a consequence of the exponent.  
> **When A = 0, the formula gives F = 0 and the gate refuses — on every code path that applies the gate** (the paths and the tests that pin them are listed in [research/GATE_PROPERTIES.md](https://github.com/delentia-labs/Delentia-OS/blob/main/research/GATE_PROPERTIES.md)). This is an invariant of those paths, not a guarantee about every path or about what a model writes; maintenance routes that are not part of the governed loop are listed there too.

---
