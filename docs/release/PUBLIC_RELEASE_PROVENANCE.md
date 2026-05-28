# RCT Platform — Public Release Provenance

This document explains how the public SDK relates to the larger private RCT Ecosystem and what “public-safe” means for this repository.

---

## 1. Public Repository Purpose

`delentia-os` is the **open SDK layer** of the broader RCT Ecosystem. Its job is to publish the reusable constitutional AI primitives, reference microservices, and developer-facing documentation that can be shared safely under Apache 2.0.

Included in the public repository:

- Core constitutional primitives (`core/`)
- SignedAI consensus and routing (`signedai/`)
- RCT control plane (`rct_control_plane/`)
- 5 reference microservices (`microservices/`)
- Public docs, benchmarks, examples, and notebooks

Not included in the public repository:

- Internal production orchestration and private infrastructure
- Full enterprise runtime and 62-service deployment surface
- Proprietary dashboards, ops tooling, or commercial-only features

---

## 2. Provenance Model

The private ecosystem can evolve ahead of the public SDK, but public publication must satisfy a stricter public-safe filter:

1. Security review — no secrets, tokens, or internal-only URLs
2. Scope review — only SDK-safe or reference-safe surfaces may be exported
3. Documentation review — public claims must match the exported code, not private capability
4. Quality review — tests, coverage, and release notes must reflect the public repo itself

This means the public repo is not a mirror of the private monorepo. It is a curated export surface with its own evidence, docs, and release discipline.

---

## 3. How to Talk About Private vs Public Scope

Use these rules in README, releases, and social copy:

- Say **“open SDK layer”** when referring to `delentia-os`
- Say **“enterprise runtime”** or **“private production ecosystem”** when referring to non-public surfaces
- Never quote private test counts, service counts, or operational claims as if they belong to the public repository
- If a capability exists only in private infrastructure, describe it as enterprise-only or out of scope for the OSS repo

---

## 4. Evidence Hierarchy for Public Claims

When a public claim is made, it should be backed by one of these:

1. Code in this repository
2. Tests and metrics in [`../testing/TESTING_CANONICAL.md`](../testing/TESTING_CANONICAL.md)
3. Public docs in this repository
4. Public website pages that correspond to the open-source scope

Claims about private infrastructure must not be used as evidence for public SDK quality.

---

## 5. Release Rule

Before a public release or social launch, confirm:

- the exported/public surface is the one being described
- the metrics come from this repository
- the docs do not imply that private-only functionality is open-source
- the GitHub UI configuration matches the docs

If any one of those fails, the release is not provenance-clean.