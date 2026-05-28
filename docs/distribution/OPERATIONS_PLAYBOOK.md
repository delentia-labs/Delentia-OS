# RCT Platform — Day 0–14 Operations Playbook

**Version:** Launch Wave 1.0  
**Created:** 2026-04-30  
**Use:** Active during the 72-hour launch window and D+14 monitoring period.

---

## Part 1: KPI Tree (3-Layer)

```
Layer 1: REACH (are people seeing it?)
├── Impressions
│   ├── X: tweet impressions (per tweet + thread total)
│   ├── HN: post position + points + comments at 2h/6h/24h
│   ├── Reddit: upvote ratio + post score + cross-posts
│   └── LinkedIn: reach + reactions
├── Repository Views
│   ├── GitHub: traffic → views (unique + total)
│   └── GitHub: referrer sources (which platform drove traffic)
└── Website Traffic
    ├── delentia.com: sessions D0–D7 vs baseline
    └── /algorithms, /benchmark, /docs: secondary page visits

Layer 2: ACTIVATION (are people engaging meaningfully?)
├── GitHub Stars (primary metric)
│   └── Target: 50 D+1 · 150 D+7 · 300 D+30
├── GitHub Forks
│   └── Target: 10 D+1 · 30 D+7
├── Colab Opens (clicks on Colab badge)
│   └── Proxy: GitHub traffic referrer from colab.research.google.com
├── pip installs (after PyPI listing)
│   └── Track via pypistats.org once listed
├── Issues opened (quality signal: questions + bugs)
│   └── Target: at least 3 substantive issues D+7
└── Discussion posts (if Discussions enabled)
    └── Target: 5 meaningful replies in Start Here thread D+7

Layer 3: RETENTION / BUSINESS SIGNAL
├── Return visits (GitHub: unique vs returning)
├── Contact form submissions (delentia.com/contact)
├── Email/LinkedIn DMs with business intent
├── PR submissions or fork+commit activity
└── Press/media mentions or secondary shares
```

---

## Part 2: Thresholds and Alert Triggers

| Metric | Green | Yellow (Monitor) | Red (Act Now) |
| --- | --- | --- | --- |
| Stars D+1 | ≥ 50 | 20–49 | < 20 |
| Stars D+7 | ≥ 150 | 75–149 | < 75 |
| HN points at 6h | ≥ 50 | 20–49 | < 20 or flagged |
| Reddit upvote ratio | ≥ 85% | 70–84% | < 70% or removed |
| Colab opens D+1 | ≥ 30 | 10–29 | < 10 |
| Website sessions D+1 | ≥ 500 | 200–499 | < 200 |
| Issues opened D+7 | ≥ 3 | 1–2 | 0 (no engagement signal) |
| CI badge status | green | — | red (credibility damage) |

---

## Part 3: 4-Hour Triage Loop (D+0 to D+2)

Run this loop every 4 hours during the first 48 hours:

```
[H+0]  Post primary wave (HN + 1 subreddit + X thread)
[H+1]  Check HN position and first comments → respond to technical questions
[H+2]  Check X engagement → if thread ≥ 20 replies, drop next thread tweet
[H+4]  TRIAGE:
  - HN: ≥ 20 pts? → hold, monitor. < 20 pts → plan fallback
  - Reddit: removed? → post to backup subreddit immediately
  - Stars: count delta vs target
[H+8]  Post secondary wave (LinkedIn + Thai communities)
[H+12] Review all threads for unanswered objections
[H+24] Daily summary: stars, forks, issues, sessions, DMs
[H+48] Go/No-Go for secondary distribution wave
```

---

## Part 4: Incident Playbooks

### Incident 1 — Demo Failure (Colab or playground not working)

**Trigger:** Reports that Colab notebook errors out or playground returns 500.

**Immediate response (< 30 min):**
1. Open the Colab link yourself in incognito mode to reproduce
2. If runtime issue: add a note to the top of the notebook cell with `# Known issue: runtime requires Python 3.10+`
3. Post pinned comment on HN/Reddit: `"Update: we identified a Colab runtime issue. Binder backup works: [link]. Fix ETA: X hours."`
4. If code issue: hotfix on main branch + re-run CI + update Colab (it auto-syncs from main)
5. If Binder also fails: provide `pip install` path with exact commands in the thread

**Post-incident:**
- Add a `KNOWN_ISSUES.md` entry
- Add a runtime compatibility note to `notebooks/rct_playground.ipynb`

---

### Incident 2 — Credibility Attack ("the numbers are fake")

**Trigger:** Someone publicly challenges the test count, coverage, or benchmark claims.

**Immediate response (< 1 hour):**
1. Do NOT respond defensively. Do NOT delete the comment.
2. Respond with: `"Fair challenge. Here's how to verify independently:"` + paste the exact commands from CLAIM_REGISTRY.md §6
3. Reference the CI badge (live, not a screenshot): link to `github.com/delentia-labs/delentia-os/actions`
4. If they challenge the 74% Delta Engine figure: acknowledge it's internal benchmark, invite them to reproduce it, mention third-party validation is on roadmap
5. If they find a genuine discrepancy: acknowledge immediately, fix the doc, post correction

**What NOT to do:**
- Do not cite secondary sources as proof
- Do not argue about numbers you can't reproduce on demand
- Do not delete critical comments (visible as cover-up)

---

### Incident 3 — Platform Content Removal (post deleted by moderators)

**Trigger:** HN post flagged/dead, Reddit post removed, LinkedIn post restricted.

**Immediate response (< 30 min):**
1. Check removal reason if available (DM mods if needed)
2. If HN: check if flagged by users (unkill if eligible) or vouch-listed via upvotes
3. If Reddit: check if spam filter triggered → request mod review via modmail
4. Activate anti-fragile routing from PLATFORM_KITS.md:
   - HN removed → route to r/MachineLearning + boost X thread
   - Reddit removed → post to r/Python or r/artificial
5. Do not immediately repost — wait for mod response or 24h cooling period

---

### Incident 4 — Founder Burnout (response quality degrading)

**Trigger:** Response time to technical questions exceeds 6h, or emotional/defensive replies appear.

**Trigger recognition signs:**
- Responding to negative comments with personal language
- Missing triage loop checkpoints
- Copy-pasting the same response to different questions

**Response:**
1. Pause all new posting for minimum 4h
2. Prepare templated responses for the top 5 most common objections (use PLATFORM_KITS.md §Objection Handling)
3. Assign a backup person for moderation if available
4. Batch replies rather than responding in real time
5. Set a personal cutoff: no social media after 22:00 local time during launch week

---

### Incident 5 — Legal or Privacy Issue

**Trigger:** Someone claims the code contains their IP, a license violation, or that user data is handled incorrectly.

**Immediate response (< 4 hours):**
1. Do NOT make public statements about the substance of the claim
2. Respond: `"Thank you for raising this. We take IP and privacy concerns seriously. We're reviewing this internally and will respond within 24 hours."`
3. If code-related: temporarily replace the relevant file with a placeholder and push to main (preserves good faith action)
4. Consult legal counsel before any further public statement
5. Document the claim, date/time, and all actions taken

---

## Part 5: Daily Review Cadence (D+3 to D+14)

| Day | Review Focus |
| --- | --- |
| D+3 | Compare stars/forks to targets; decide if secondary wave needed |
| D+7 | Mid-launch assessment: GitHub traffic referrers, top-performing channel |
| D+10 | Issue quality review: are questions substantive? Any PRs? |
| D+14 | Full KPI report: Reach→Activation→Retention metrics; decide v1.0.3a0 timeline |

---

## Part 6: Role Split (Founder-Only Mode)

If launching solo without additional team:

| Time Block | Focus |
| --- | --- |
| 08:00–10:00 | Post primary wave + monitor first hour |
| 10:00–12:00 | Reply to technical questions (quality > speed) |
| 12:00–14:00 | Check metrics, identify which channel is leading |
| 14:00–16:00 | Post secondary wave (LinkedIn + Thai) |
| 16:00–18:00 | Batch reply to all remaining threads |
| 18:00–20:00 | Stars/forks review, GitHub Issues triage |
| 20:00–22:00 | Write D+1 summary, prepare D+2 plan |
| 22:00+ | Offline. Do not engage from a degraded state. |
