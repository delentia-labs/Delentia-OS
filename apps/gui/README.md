# Delentia Desk

[![Release](https://img.shields.io/github/v/tag/delentia-labs/delentia-gui?label=Release&color=blue)](https://github.com/delentia-labs/delentia-gui/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/delentia-labs/delentia-gui/ci.yml?branch=main&label=CI)](https://github.com/delentia-labs/delentia-gui/actions/workflows/ci.yml)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)](https://github.com/delentia-labs/delentia-gui/releases)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)

**Delentia Desk** is the official desktop application for [Delentia OS](https://github.com/delentia-labs/delentia-os) — a visual control surface for intent-centric constitutional AI.

Built with **Tauri v2** (3 MB binary, native WebView security) + **Next.js 15** + **Tailwind CSS** + **Recharts**.

---

## Downloads

| Platform | Installer | Notes |
|---|---|---|
| Windows 10/11 | `.msi` or `.exe` | x64 only |
| macOS 13+ | `.dmg` | Apple Silicon (arm64) |
| Linux | `.AppImage` or `.deb` | Ubuntu 22.04+ |

> Download the latest release from [GitHub Releases](https://github.com/delentia-labs/delentia-gui/releases).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Delentia Desk (Tauri v2)               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Next.js 15 (static export)  — src/app/             │    │
│  │  ├── / (Dashboard) — live system stats + health     │    │
│  │  ├── /chat — FDIA-scored intent chat                │    │
│  │  ├── /memory — Delta Engine timeline + rollback     │    │
│  │  └── /settings — gateway URL + API key + HexaCore  │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │ Tauri IPC                         │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │  Rust backend (src-tauri/)                           │    │
│  │  ├── execute_intent()     → POST /v1/kernel/execute │    │
│  │  ├── get_system_stats()   → GET  /delentia/system/stats│ │
│  │  ├── health_check()       → GET  /health             │    │
│  │  └── get_memory_history() → GET  /v1/memory/history │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │ reqwest (HTTPS)                   │
└─────────────────────────┼───────────────────────────────────┘
                          ▼
          Delentia OS Gateway  (localhost:8000)
          ├── RCT v5 — 9 HexaCore models
          ├── FDIA scoring engine
          ├── JITNA v3 packet routing
          └── Delta Engine (memory timeline)
```

---

## Features

| Feature | Description |
|---|---|
| **Intent Chat** | FDIA score badge + SignedAI tick + HexaCore role on every reply |
| **FDIA Visualizer** | Formula D^I × A, Recharts radar, color-coded levels |
| **Memory Timeline** | Delta Engine audit log — filter by agent/outcome/violation |
| **Memory Rollback** | Roll back system state to any tick with confirm dialog |
| **System Dashboard** | Live stats: 4,849 tests, 62 microservices, 9 HexaCore models |
| **Health Monitor** | 30-second polling of `/health` endpoint with status dot |
| **HexaCore Selector** | Configure preferred model tier with full cost/context details |
| **3 MB binary** | Tauri v2 vs 150 MB Electron — native WebView, no bundled Chromium |

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Node.js | ≥ 20 | `nvm install 20` |
| Rust | stable | `rustup install stable` |
| Tauri CLI | v2 | installed via `npm install` |
| Delentia OS | ≥ 2.0.0 | must be running at localhost:8000 |

### Windows extra dependency
WebView2 Runtime is required on Windows 10/11 (pre-installed on Windows 11):
```powershell
# Install WebView2 if not present (Windows 10 only)
winget install Microsoft.EdgeWebView2Runtime
```

### Linux extra dependencies
```bash
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev libgtk-3-dev \
  libayatana-appindicator3-dev librsvg2-dev
```

---

## Development

```bash
# 1. Clone
git clone https://github.com/delentia-labs/delentia-gui
cd delentia-gui

# 2. Configure environment
cp .env.example .env.local
# Edit .env.local — set NEXT_PUBLIC_GATEWAY and NEXT_PUBLIC_API_KEY

# 3. Install dependencies
npm install

# 4. Run in development (Tauri + Next.js HMR)
npm run tauri:dev

# 5. Type check + lint
npm run type-check
npm run lint
```

---

## Build

```bash
# Build for current platform
npm run tauri:build

# Outputs: src-tauri/target/release/bundle/
#   Windows: .msi + .exe
#   macOS:   .dmg + .app
#   Linux:   .AppImage + .deb
```

---

## Security

- All `/v1/*` API calls require `Authorization: Bearer <token>` (never sent to other origins)
- Tauri CSP restricts `connect-src` to `localhost:8000–8004` only
- API key is masked in the Settings UI — never logged
- Rollback actions require explicit user confirmation
- No telemetry, no analytics, no third-party SDK calls

---

## Related Repositories

| Repo | Purpose |
|---|---|
| [delentia-os](https://github.com/delentia-labs/delentia-os) | Core SDK (Apache 2.0) |
| [delentia-ai](https://github.com/delentia-labs/delentia-ai) | SLM fine-tuning factory |
| [delentia-ecosystem](https://github.com/delentia-labs/delentia-ecosystem) | Plugin & adapter registry |
| [delentia-infra-public](https://github.com/delentia-labs/delentia-infra-public) | Community deployment |
| [delentia-infra-enterprise](https://github.com/delentia-labs/delentia-infra-enterprise) | Enterprise infra |

---

## License

Apache 2.0 — © 2026 Delentia Labs  
See [LICENSE](LICENSE) for details.
