# Delentia Desk

The interface for the Delentia agent runtime (`rct_control_plane`, started with `delentia serve`).
Every page shows what the runtime actually recorded; when the API is unreachable a page says so
instead of showing placeholder data.

Next.js 16 (static export), Tailwind, optional Tauri shell (`src-tauri/`). Design notes: [DESIGN.md](DESIGN.md).

## Pages

| Page | Shows | Endpoint |
|---|---|---|
| Status | API, daemon, pending approvals, audit chain | `/health`, `/v1/desk/overview` |
| Chat | a goal through the governed loop, step by step | `/v1/kernel/stream` (WebSocket) |
| Sessions | every episode: cycle, D/I/F and the data behind D, plan, tool calls, the five Intent Loop pillars | `/v1/desk/sessions` |
| Subagents | work split across signed, isolated subagents | `/v1/desk/subagents` |
| Growth | MEE growth per user, "smarter, faster, cheaper" measured on repeated goals, the user's intent profile | `/v1/desk/growth` |
| Memory | what the agent knows about you (D); add facts | `/v1/desk/memories` |
| Algorithms | the 41 algorithms as pipeline stages, what each recorded | `/v1/desk/pipeline` |
| Approvals | signed human approvals that resume paused work | `/v1/agent/approvals` |
| Audit | hash chain, notary, anchoring | `/v1/desk/audit` |
| Models | provider and model | `/v1/desk/models` |
| Skills | what was learned, how reliable it has been when reused | `/v1/desk/skills` |
| Tools, Cron, Channels, Experiments | registry and gates, daemon tasks, messaging allowlists, RCTDB runs | `/v1/desk/*` |
| Settings | gateway address, API token (kept in memory only) | |

`Ctrl/Cmd+K` jumps to any page.

## Run

```bash
delentia serve                      # the API on :8000 (turns the pipeline and warm recall on)
cd apps/gui && npm ci && npm run dev -- -p 3010
npm run type-check && npm run lint && npm run build
```

Set the gateway address and, when the API is not on localhost, the token (`DELENTIA_API_TOKEN`) in Settings.
