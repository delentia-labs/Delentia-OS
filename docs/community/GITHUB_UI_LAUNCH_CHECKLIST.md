# RCT Platform — GitHub UI Launch Checklist

These steps must be completed in the GitHub web UI because they cannot be enforced from repository files alone.

---

## 1. About Panel

Open the repository home page, then in the right-side **About** panel click the gear icon.

Set the following:

- **Description**: `Intent-Centric AI OS — Constitutional Architecture for AI Agents`
- **Website**: `https://delentia.com`
- **Topics**:
  - `ai`
  - `constitutional-ai`
  - `agentic-ai`
  - `multi-agent`
  - `signedai`
  - `fdia`
  - `intent-loop`
  - `python`
  - `fastapi`
  - `asean`

Why this matters:

- About is the first public metadata surface people see from search, shares, and profile visits
- Topics affect discoverability on GitHub
- Website bridges repo visitors into the product or documentation funnel

---

## 2. GitHub Discussions

Open **Settings** → **General** → **Features** → enable **Discussions**.

Recommended categories:

- Announcements
- Q&A
- Ideas / RFC
- Show and Tell
- Benchmarks and Results
- Integrations

After enabling Discussions, create and pin at least two starter threads:

1. `Start Here — What RCT Platform includes, what it does not include, and where to begin`
2. `Roadmap and Known Scope — public SDK priorities, milestone links, and enterprise boundary`

---

## 3. Milestones

Open **Issues** → **Milestones** and create:

1. `v1.0.3a0 — Playground Release`
2. `v1.0.0 — Stable PyPI Release`
3. `v1.1.0 — Observability + Integrations`

Each milestone should mirror `ROADMAP.md` so the roadmap becomes operational, not aspirational only.

---

## 4. Profile Pinning

Open your GitHub profile → **Customize your pins** → pin `delentia-os`.

Why this matters:

- visitors from social media often land on the maintainer profile first
- pinning establishes `delentia-os` as the flagship public artifact

---

## 5. Final UI Verification

Before launch, verify these links manually in the browser:

- repository home page loads the About description correctly
- website link opens `https://delentia.com`
- Topics are visible and relevant
- Discussions tab is visible and opens successfully
- milestone page is public and non-empty
- profile pin is visible on the maintainer profile

If the docs point to Discussions or milestones but the UI is not live, the repo is still in launch-drift.