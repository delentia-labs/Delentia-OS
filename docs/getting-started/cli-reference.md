# CLI Reference

The `rct` command-line tool is the primary interface to the RCT Control Plane SDK.

**Install the CLI:**

```bash
pip install -e .
rct version
rct start --ui-test
rct init
rct doctor
rct --help
```

---

## Global Options

| Flag | Description |
|------|-------------|
| `--output json` | Output as JSON (default: table) |
| `--output table` | Output as rich table |
| `--output tree` | Tree view (for graph commands) |
| `--verbose` | Enable debug logging |
| `--version` | Print version and exit |
| `--help` | Show help and exit |

---

## Commands

### `rct version`

Print SDK version, Python version, and component status.

```bash
rct version
```

**Output:**

```
RCT Platform SDK v1.0.4b0
Python 3.11.x
  ✓ core.fdia          — FDIA Scorer + equation engine
  ✓ core.delta_engine  — Memory Delta Engine (74% compression)
  ✓ signedai.core      — SignedAI consensus registry
  ✓ rct_control_plane  — DSL compiler, graph builder, API server
```

Recommended first-run order for a fresh install:

```bash
rct version
rct start --ui-test
rct init
rct doctor
rct start
```

---

### `rct serve`

Start the Control Plane REST API server.

```bash
rct serve [--port PORT] [--reload] [--workers N]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | `8000` | Port to listen on |
| `--reload` | off | Auto-reload on code changes (dev mode) |
| `--workers` | `1` | Number of Uvicorn worker processes |

**Example:**

```bash
rct serve --port 8000 --reload
# → http://localhost:8000
# → Docs: http://localhost:8000/docs
```

---

### `rct compile`

Compile a natural language intent into an intent record.

```bash
rct compile TEXT [--user-id USER_ID] [--context JSON]
```

| Option | Default | Description |
|--------|---------|-------------|
| `TEXT` | required | The intent text to compile |
| `--user-id` | `"anonymous"` | User identifier for audit trail |
| `--context` | `"{}"` | JSON context blob |

**Example:**

```bash
rct compile "Refactor authentication module" --user-id alice
```

**Output (table):**

```
┌────────────┬──────────────────────────────────┐
│ Field      │ Value                            │
├────────────┼──────────────────────────────────┤
│ Intent ID  │ a1b2c3d4-...                     │
│ Status     │ compiled                         │
│ FDIA Score │ 0.8734                           │
│ Tier       │ S4                               │
└────────────┴──────────────────────────────────┘
```

---

### `rct build`

Build a DSL execution graph from a compiled intent.

```bash
rct build --intent-id ID [--dsl-file FILE] [--output FILE]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--intent-id` | required | Intent ID from `rct compile` |
| `--dsl-file` | auto | Path to a `.dsl` file (optional) |
| `--output` | stdout | Write graph JSON to file |

**Example:**

```bash
rct compile "Deploy microservice to staging" --user-id devops | rct build --intent-id -
rct build --intent-id a1b2c3d4 --output graph.json
```

---

### `rct evaluate`

Evaluate a compiled + built intent through policy and governance checks.

```bash
rct evaluate --intent-id ID [--architect-score FLOAT]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--intent-id` | required | Intent ID to evaluate |
| `--architect-score` | `1.0` | Override Architect gate (0.0–1.0) |

!!! warning "A=0 blocks output"
    Passing `--architect-score 0.0` will cause FDIA = 0 and block all output.
    This is the constitutional safety guarantee — not a bug.

**Example:**

```bash
rct evaluate --intent-id a1b2c3d4 --architect-score 0.9
```

---

### `rct status`

Show current state of a compiled intent.

```bash
rct status INTENT_ID
```

**Example:**

```bash
rct status a1b2c3d4-5678-...
```

**Output:**

```
Intent   : a1b2c3d4-5678-...
State    : COMPLETED
Created  : 2026-04-21T10:00:00+00:00
FDIA     : 0.8734
Policy   : COMPLIANT
```

---

### `rct list`

List recent intents.

```bash
rct list [--limit N] [--status STATUS] [--user-id USER_ID]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--limit` | `10` | Max intents to show |
| `--status` | all | Filter by state (e.g., `COMPLETED`, `FAILED`) |
| `--user-id` | all | Filter by user |

---

### `rct audit`

Display full audit trail for an intent.

```bash
rct audit INTENT_ID [--output json]
```

**Example:**

```bash
rct audit a1b2c3d4 --output json
```

Outputs the complete signed audit chain including FDIA score, SignedAI consensus
tier, and policy decisions.

---

### `rct metrics`

Display runtime metrics for the Control Plane.

```bash
rct metrics [--output json]
```

**Sample output:**

```
Metric                   Value
────────────────────────────────────
Intents processed        1,247
FDIA avg score           0.8734
Warm recall hits         89.3%
Consensus tier S4 calls  847
Policy violations        2
Uptime                   14d 06h
```

---

### `rct reset`

Reset in-memory state (development/testing only).

```bash
rct reset [--force]
```

!!! danger "Destructive Action"
    `rct reset` clears all in-memory intent state. Use `--force` to skip confirmation.
    Persisted audit logs are **not** deleted.

---

### `rct intent submit`

Submit an intent directly via JSON (low-level).

```bash
rct intent submit --intent TEXT --context JSON
```

**Example:**

```bash
rct intent submit \
  --intent "Analyze security posture of auth module" \
  --context '{"repo": "delentia-os", "branch": "main"}'
```

---

### `rct health`

Check Control Plane and component health.

```bash
rct health [--detailed]
```

| Flag | Description |
|------|-------------|
| *(none)* | Lightweight liveness check |
| `--detailed` | Full subsystem health (FDIA, Delta, SignedAI, compiler) |

**Example:**

```bash
rct health --detailed
```

```
Component               Status
────────────────────────────────
fdia_engine             ✓ ok
delta_engine            ✓ ok
signedai_registry       ✓ ok
intent_compiler         ✓ ok
dsl_parser              ✓ ok
policy_engine           ✓ ok
```

---

## Shell Completion

Enable tab-completion for `bash`, `zsh`, or `fish`:

```bash
# bash
eval "$(_RCT_COMPLETE=bash_source rct)"

# zsh
eval "$(_RCT_COMPLETE=zsh_source rct)"

# fish
eval (env _RCT_COMPLETE=fish_source rct)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RCT_PORT` | `8000` | Default port for `rct serve` |
| `RCT_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`) |
| `RCT_STATE_DIR` | `.rct_state/` | Directory for persisted intent state |
| `RCT_ARCHITECT_SCORE` | `1.0` | Default Architect gate value |
