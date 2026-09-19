# rct_control_plane

The 41-algorithm kernel and supporting engines for Delentia OS's Constitutional AI runtime.

## What this package is

`AlgorithmKernel41` (`algorithm_kernel_41.py`) is the central class: it constructs and wires together the real engines behind each of the 41 master algorithms (Tiers 1-9, per the Architect's master architecture doc), plus supporting infrastructure — persistence (`persistence.py`), the JITNA v3 wire protocol (`jitna_protocol.py`), the CORD Shannon-entropy security engine (`cord_security.py`), the sandbox (`sandbox.py`), and a scoped, additive dependency-injection layer (`capability_registry.py`, since Round 27) that resolves the kernel's ~40 engines instead of constructing them all directly in `__init__`.

`process_intent_deep_pipeline()` is the main entry point: it runs a natural-language intent through the FDIA safety gate (`F = (D^I) * A`), RCT-7 decomposition, Fast/Slow routing, and (on the SLOW path) a universal quality/semantic gate plus selective algorithm dispatch.

## Running the tests

```bash
pytest rct_control_plane/
```

The full suite (1400+ real tests as of Round 28) instantiates real engines — no network calls are mocked away for the algorithms that make real local-Ollama or sandboxed-execution calls, matching this project's "real, tested code only" discipline. A few tests are environment-dependent (e.g. Docker sandbox backend) and honestly skip/report when the resource isn't available, rather than fabricating a pass.

Never run two full-suite passes concurrently — they share `rct_control_plane_agentic.db` and will produce false-positive failures from write contention.

## Where the real documentation lives

**Each `algo_XX_*` method's docstring is the primary, authoritative source of truth** for what that algorithm actually does — not a separate doc that can drift out of sync with the code. `docs/algorithms/` (repo root) currently covers only 4 of the 41 algorithms and should not be treated as complete.

For architectural context:
- The Architect's master specification: `DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md` (external reference doc, not checked into this repo).
- This session's per-round synthesis documents at the workspace root (`DELENTIA_ROUND*_SYNTHESIS.md`) — each one documents what was verified real vs. what was found to be a gap/drift at that point in time, with file:line evidence. Treat them as historical snapshots, not live documentation — always verify against the current code before relying on a claim from an older round.
- `capability_registry.py`'s module docstring explains the kernel's dependency-injection design and its deliberate scope (Round 27 migrated engine *construction* onto it; it did not become the primary way new code looks up dependencies — most kernel methods still use `self._xxx` directly).
