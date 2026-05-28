# RCT Platform — Launch Evidence Pack & Go/No-Go Rubric

**Version:** 1.0.4b0 Launch Gate  
**Created:** 2026-04-30  
**Policy:** Do NOT execute primary distribution wave until all HARD GATE items are checked.

---

## Go/No-Go Summary

| Gate | Category | Status | Required |
| --- | --- | --- | --- |
| A1 | CI green on main | ☐ Verify | HARD GATE |
| A2 | Test count matches TESTING_CANONICAL | ☐ Verify | HARD GATE |
| A3 | Coverage ≥ 90% CI enforced | ☐ Verify | HARD GATE |
| A4 | delentia-os repo is PUBLIC | ☐ Verify | HARD GATE |
| A5 | Colab opens anonymously | ☐ Verify | HARD GATE |
| B1 | rctlabs-website build passes | ☐ Verify | HARD GATE |
| B2 | Smoke pages green | ☐ Verify | HARD GATE |
| B3 | Website loads on production URL | ☐ Verify | HARD GATE |
| C1 | GitHub About/Topics/Website set | ☐ Verify | HARD GATE |
| C2 | GitHub Discussions enabled | ☐ Verify | HARD GATE |
| C3 | Milestones created | ☐ Soft Gate |
| D1 | Platform kits claim-checked | ☐ Verify | HARD GATE |
| D2 | Sitemap lastmod updated | ☐ Verify | Soft Gate |
| E1 | Monitoring active (Vercel Analytics) | ☐ Verify | Soft Gate |

**Go threshold:** All HARD GATE items ✅ → Green Light to post  
**Soft gates:** Should be complete but do not block the launch

---

## Part A — Repository & SDK Hard Gates

### A1: CI Status (Live Badge)
- [ ] Open: https://github.com/delentia-labs/delentia-os/actions/workflows/ci.yml
- [ ] Verify: latest run on `main` branch = **green checkmark**
- [ ] If red: do NOT post. Fix CI first.
- **Evidence:** Screenshot of CI page URL + green badge ← attach here

### A2: Test Count Match
- [ ] Run locally: `python -m pytest -q --no-header`
- [ ] Output must match EXACTLY: `1287 passed` (or equivalent zero-warning output)
- [ ] Compare to TESTING_CANONICAL.md §1: **1,287 passed · 0 skipped · 0 failed**
- [ ] If counts differ: update TESTING_CANONICAL.md before posting
- **Evidence:** Terminal output paste ← attach here

### A3: Coverage Gate
- [ ] Run: `python -m pytest --cov=microservices --cov=core --cov=signedai --cov=rct_control_plane --cov-report=term --cov-config=pyproject.toml -q --no-header`
- [ ] Output must show ≥ 90% (CI gate) and **92%** (public claim)
- [ ] Codecov badge live: https://app.codecov.io/gh/rctlabs/delentia-os
- **Evidence:** Coverage report summary ← attach here

### A4: Repo Visibility
- [ ] Open https://github.com/delentia-labs/delentia-os in **incognito mode** (logged out)
- [ ] Verify: repo loads, code is visible, README renders
- [ ] Verify: no "This repository is private" message
- **Evidence:** Incognito URL screenshot ← attach here

### A5: Colab Anonymous Run
- [ ] Open https://colab.research.google.com/github/rctlabs/delentia-os/blob/main/notebooks/rct_playground.ipynb in **incognito mode** (not logged into Google)
- [ ] Click "Open in Colab" or load directly
- [ ] Verify: notebook opens without requiring login
- [ ] Click "Runtime → Run All" and verify it completes without auth errors
- [ ] Verify: FDIA demo output visible
- **Evidence:** Screenshot of completed Colab run ← attach here

---

## Part B — Website & Build Hard Gates

### B1: Production Build Pass
- [x] `npm run build` → exit code 0 ✅ (verified 2026-04-30, 149 pages, 0 TypeScript errors)
- [x] Compiled: 7.8s · TypeScript: 17.3s
- **Evidence:** Terminal output in conversation 2026-04-30

### B2: Smoke Pages
- [ ] Run: `npm run smoke:pages`
- [ ] All critical routes return 200 (home, /en, /th, /studio, /algorithms, /solutions, /pricing, /contact)
- [ ] No 404 or 500 errors on any smoke route
- **Evidence:** Smoke test output ← attach here

### B3: Production URL
- [ ] Open https://delentia.com in browser (not localhost)
- [ ] Hero loads with correct text
- [ ] /en and /th routes work
- [ ] /studio redirects to signin if not logged in
- [ ] /algorithms page loads
- [ ] Contact form visible
- **Evidence:** Browser URL bar screenshots ← attach here

### B4: SEO Basics
- [ ] https://delentia.com/sitemap.xml loads and lists pages
- [ ] https://delentia.com/robots.txt loads correctly
- [ ] OG image: test with https://www.opengraph.xyz/?url=https://delentia.com
- **Evidence:** URL screenshots ← attach here

---

## Part C — GitHub UI Hard Gates

### C1: About Panel
- [ ] Go to https://github.com/delentia-labs/delentia-os
- [ ] About section (right sidebar) shows:
  - Description: `Intent-Centric AI OS — Constitutional Architecture for AI Agents`
  - Website: `https://delentia.com`
  - Topics: ai, constitutional-ai, agentic-ai, multi-agent, signedai, fdia, intent-loop, python, fastapi, asean
- **Evidence:** Screenshot of repo sidebar ← attach here

### C2: GitHub Discussions
- [ ] Go to https://github.com/delentia-labs/delentia-os/discussions
- [ ] Discussions tab is visible and accessible (not 404)
- [ ] "Start Here" pinned thread exists OR draft is ready to post
- **Evidence:** Screenshot of Discussions tab ← attach here

### C3: Milestones (Soft Gate)
- [ ] Go to https://github.com/delentia-labs/delentia-os/milestones
- [ ] Milestones exist: v1.0.3a0 · v1.0.0 · v1.1.0
- [ ] Each milestone has description matching ROADMAP.md
- **Evidence:** Screenshot of milestones page ← attach here

---

## Part D — Distribution Readiness

### D1: Platform Kits Claim Check
- [ ] Open PLATFORM_KITS.md
- [ ] Search for every number: "1,287", "92%", "74%", "Apache 2.0", "v1.0.4b0"
- [ ] Verify each matches CLAIM_REGISTRY.md
- [ ] Verify "74% compression" has "(internal benchmark)" qualifier in every occurrence
- **Evidence:** Checked manually ← sign-off here

### D2: Sitemap Deploy Date
- [x] `SITE_LAST_DEPLOY` in `app/sitemap.ts` updated to "2026-04-30" ✅

### D3: Vercel Environment Variables (Manual Check)
- [ ] Open Vercel Dashboard → rctlabs-website → Settings → Environment Variables
- [ ] Verify Production has: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- [ ] Verify: `GOOGLE_SITE_VERIFICATION` (if GSC verified)
- **Evidence:** Vercel dashboard screenshot ← attach here

---

## Part E — Monitoring

### E1: Analytics Active
- [ ] Open Vercel Dashboard → rctlabs-website → Analytics
- [ ] At least 1 data point visible (confirms tracking is live)
- **Evidence:** Analytics dashboard screenshot ← attach here

---

## Final Go/No-Go Scoring

Rate each dimension 1–5:

| Dimension | Score | Weight | Weighted |
| --- | --- | --- | --- |
| Technical proof (CI, tests, coverage) | /5 | ×3 | /15 |
| Repository access (public, Colab works) | /5 | ×3 | /15 |
| Website live (build, smoke, prod URL) | /5 | ×2 | /10 |
| GitHub UI (About, Discussions, Milestones) | /5 | ×2 | /10 |
| Distribution kits (claim-checked, ready) | /5 | ×2 | /10 |
| Monitoring (analytics, uptime) | /5 | ×1 | /5 |

**Maximum score: 65**  
**Launch threshold: ≥ 52 (80%)** with all HARD GATE items checked

Current pre-launch score estimate: __/65

---

## Launch Authorization

When all HARD GATES are checked and score ≥ 52:

```
Launch Wave Authorization
Date: ___________
Authorized by: ___________
Score: ___/65
Hard gates passed: ___/9
Soft gates passed: ___/5

Primary Wave Start Time: ___________
HN post time: ___________
Reddit post time: ___________
X thread time: ___________
LinkedIn post time: ___________
Thai community time: ___________
```

---

*This Evidence Pack supersedes verbal confirmation. No launch without artifact links.*
