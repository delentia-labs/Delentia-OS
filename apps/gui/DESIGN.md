# Delentia Desk design (Round 50 redesign)

The Desk borrows the structure of Hermes Agent's dashboard (a terminal-first
chat, a left menu in uppercase mono labels, a System block, a status line) and
adds what only Delentia has: signed approvals, the audit chain, the
Constitutional Cycle per episode, and RCTDB experiments.

## Mark

`src/components/desk/mark.tsx` is drawn from the Architect's logo
(`Delentia-Website/public/DelentiaIcon.png`): a database symbol of three equal
bars with a pair of eyes on the top layer.

| Part | Colour | Where |
|---|---|---|
| Top bar and eye rings | leaf `#80C961` | active, live, primary |
| Middle bar | fern `#519037` | secondary, borders |
| Bottom bar | pine `#315721` | selected fills |
| Eyes | `#2C2525` | text on green |

- `DelentiaMark`: vector, for the sidebar and the favicon (`public/delentia-mark.svg`).
- `PixelMark`: the chat banner's pixel-art version (a symmetric 26 x 28 grid), in
  the spot where Hermes shows its ASCII art. It blinks once after load, and not
  at all under `prefers-reduced-motion`.

## Tokens

Defined in `src/app/globals.css` (`--dl-*`, with `-rgb` channels) and exposed
to Tailwind as `dl-*` (`bg-dl-panel`, `text-dl-leaf/70`, ...).

| Token | Value | Use |
|---|---|---|
| ink | `#0E1611` | page background |
| panel / panel-2 | `#142019` / `#1B2A21` | surfaces |
| rule | `#2B3F31` | borders |
| text / muted | `#E4EEDD` / `#93A88F` | copy |
| amber | `#E4B54A` | waiting for a human (approvals, pending) |
| rust | `#E2694C` | blocked or broken (FDIA block, broken chain) |

Type: IBM Plex Mono for the terminal, navigation and data; IBM Plex Sans Thai
for explanations (Thai and English). Uppercase is used only for the main
menu, as in Hermes.

## Pages

| Hermes | Delentia Desk | Data |
|---|---|---|
| Chat | `/chat` (Agent (governed) or Chat mode) | `/v1/kernel/stream` (`structured: true`) |
| Status | `/` | `/health`, `/v1/desk/overview`, `/v1/desk/sessions`, `/v1/desk/audit` |
| Sessions | `/sessions` with the cycle strip per episode | `/v1/desk/sessions[/{id}]` |
| Pairing | `/approvals` (signed Ed25519 decisions, pasted JSON) | `/v1/agent/approvals` |
| Logs | `/audit` (chain, tiers A1-A3, latest rows) | `/v1/desk/audit` |
| Models | `/llm` | `/v1/desk/models` |
| Skills | `/skills` (MEE-gated) | `/v1/desk/skills` |
| MCP | `/tools` (grouped by gate) | `/v1/desk/tools` |
| Cron | `/cron` | `/v1/daemon/status`, `/v1/desk/cron/{id}/run` |
| Channels | `/channels` (allowlist counts, never sender ids) | `/v1/desk/channels` |
| Analytics | `/experiments` (RCTDB runs, first vs last) | `/v1/desk/experiments` |

Round 51 pages: `/growth` (`/v1/desk/growth`: MEE G per user, the evolution and intent profile), `/memory` (`/v1/desk/memories`), `/algorithms` (`/v1/desk/pipeline`), `/subagents` (`/v1/desk/subagents`). The earlier "Labs" pages, the multi-theme system and the intent-chat window were deleted on 2026-10-01; git history has them.

## Rules

- Every value comes from the API. When the API cannot be reached, a page says
  so and shows `-`; nothing is simulated.
- The GUI never holds an approver key. Approvals are signed elsewhere with
  `delentia approvals sign` and the printed JSON is pasted in.
- Keys (OpenRouter and others) live in the environment of the process running
  `delentia serve`; no page can read or set them.
