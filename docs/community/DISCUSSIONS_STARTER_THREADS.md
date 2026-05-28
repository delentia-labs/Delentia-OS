# RCT Platform — Starter Discussions

Use these drafts when GitHub Discussions is enabled and you need the first two pinned threads.

---

## 1. Start Here

**Title**

`Start Here — what RCT Platform includes, what it does not include, and where to begin`

**Body**

Welcome to `delentia-os`, the open SDK layer of the broader RCT Ecosystem.

If you are new here, use this order:

1. Read `README.md` for the high-level architecture and product context
2. Run `python examples/quickdemo.py` or open `notebooks/rct_playground.ipynb`
3. Verify current quality claims in `docs/testing/TESTING_CANONICAL.md`
4. Read `docs/release/PUBLIC_RELEASE_PROVENANCE.md` to understand public SDK vs enterprise scope
5. Ask questions in this Discussions space instead of opening issues for general usage questions

What this repository includes:

- constitutional AI primitives under `core/`
- SignedAI consensus and routing under `signedai/`
- control-plane and JITNA components under `rct_control_plane/`
- 5 reference microservices under `microservices/`

What this repository does not include:

- the full enterprise runtime
- private infrastructure, dashboards, and internal orchestration layers
- the full 62-service production deployment surface

If you are here from a social post and want the fastest possible proof path, start with the 5-minute demo and then read the testing canonical doc.

---

## 2. Roadmap and Known Scope

**Title**

`Roadmap and Known Scope — public SDK priorities, milestone links, and enterprise boundary`

**Body**

This thread tracks the public roadmap and clarifies what belongs in the open SDK versus the private production ecosystem.

Current roadmap anchors:

1. `v1.0.3a0 — Playground Release`
2. `v1.0.0 — Stable PyPI Release`
3. `v1.1.0 — Observability + Integrations`

Before opening a feature request, please check:

- does the request belong in the public SDK?
- can it be demonstrated with public code, tests, and docs?
- does it fit the current milestone sequence in `ROADMAP.md`?

Out of scope for the public SDK:

- internal enterprise-only services
- hosted SaaS or proprietary control surfaces
- private deployment and operations tooling

If you want to propose an SDK-safe addition, include:

- use case
- expected public API surface
- how it should be tested
- whether it needs docs, examples, or benchmark coverage