# RCT Platform — Public Release Readiness Checklist

Use this checklist before any public launch, social media campaign, GitHub Release, or PyPI tag.

---

## 1. Single-Truth Metrics

- [x] `docs/testing/TESTING_CANONICAL.md` reflects the latest verified checkpoint
- [x] `README.md` matches the canonical test, skip, and coverage numbers exactly
- [x] `ROADMAP.md` matches the current checkpoint summary exactly
- [x] `CHANGELOG.md` includes an `[Unreleased]` summary for the current quality or launch work
- [x] Any draft release notes or social launch copy use the same numbers as the canonical doc

## 2. CI and Security Gates

- [x] `.github/workflows/ci.yml` is green on the current default branch
- [x] `.github/workflows/security-scan.yml` is green on the current default branch
- [x] `codecov.yml` target matches the intended coverage floor
- [x] No known secret exposure or credential leak is present in the working tree
- [x] Dependency CVE scan output has been reviewed

## 3. GitHub UI Configuration

- [x] About description is set
- [x] Website is set to `https://rctlabs.co`
- [x] Topics are configured for discovery
- [x] GitHub Discussions is enabled if the repo links to Discussions anywhere in docs or issue templates
- [x] GitHub Milestones exist for roadmap items referenced in `ROADMAP.md`
- [x] The repo is pinned on the maintainer profile if it is the launch focal point

See [`../community/GITHUB_UI_LAUNCH_CHECKLIST.md`](../community/GITHUB_UI_LAUNCH_CHECKLIST.md).

## 4. Community Funnel

- [x] A new visitor can find a 5-minute demo path in `README.md`
- [x] A new visitor can tell what is open-source vs enterprise-only in under 60 seconds
- [x] A new visitor can find where to ask questions
- [x] A new visitor can find how to verify claims
- [x] A pinned “Start Here” discussion draft is ready if Discussions is enabled

## 5. Release Narrative

- [x] GitHub Release notes have been drafted from `CHANGELOG.md`
- [x] Release notes match the current repo state, not an older checkpoint
- [x] Public-safe provenance is documented
- [x] Any benchmark or architecture claims link to a reproducible or documented source

See [`PUBLIC_RELEASE_PROVENANCE.md`](PUBLIC_RELEASE_PROVENANCE.md).

## 6. Final Validation Commands

```bash
python scripts/check_claim_sync.py
python -m pytest -q --no-header
python -m pytest --cov=microservices --cov=core --cov=signedai --cov=rct_control_plane --cov-report=term --cov-config=pyproject.toml -q --no-header
python -m pytest microservices -q --no-header
ruff check core/ signedai/ rct_control_plane/ microservices/
```

If any of these commands fail, the launch is not release-ready.