# CLI Reference

The `delentia` command-line tool is the primary interface to the Delentia OS
Control Plane SDK. (Corrected 2026-09-24: this page previously called the
command `rct` throughout - the real entry point registered in
`pyproject.toml` is `delentia = "rct_control_plane.cli:main"`, confirmed
against `pyproject.toml` and `python -m rct_control_plane.cli --help`'s
real output. `rct` is not an installed command.)

**Install the CLI:**

```bash
pip install -e .
delentia version
delentia start --ui-test
delentia init
delentia doctor
delentia --help
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

### `delentia version`

Print SDK version, Python version, and component status.

```bash
delentia version
```

**Output** (real, verified 2026-09-24 against `python -m rct_control_plane.cli version`):

```
                  Delentia OS — Version Info
┌─────────────┬──────────────────────────────────────────────┐
│ Field       │ Value                                        │
├─────────────┼──────────────────────────────────────────────┤
│ version     │ 2.2.6                                        │
│ package     │ delentia-os                                  │
│ name        │ delentia-os                                  │
│ description │ Constitutional AI Operating System SDK       │
│ python      │ 3.13.14                                      │
│ license     │ Apache-2.0                                   │
│ homepage    │ https://delentia.com                         │
│ repository  │ https://github.com/delentia-labs/delentia-os │
└─────────────┴──────────────────────────────────────────────┘
```

Recommended first-run order for a fresh install:

```bash
delentia version
delentia start --ui-test
delentia init
delentia doctor
delentia start
```

---

### `delentia serve`

Start the Control Plane REST API server.

```bash
delentia serve [--port PORT] [--reload] [--workers N]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | `8000` | Port to listen on |
| `--reload` | off | Auto-reload on code changes (dev mode) |
| `--workers` | `1` | Number of Uvicorn worker processes |

**Example:**

```bash
delentia serve --port 8000 --reload
# → http://localhost:8000
# → Docs: http://localhost:8000/docs
```

---

### `delentia compile`

Compile a natural language intent into an intent record.

```bash
delentia compile TEXT [--user-id USER_ID] [--context JSON]
```

| Option | Default | Description |
|--------|---------|-------------|
| `TEXT` | required | The intent text to compile |
| `--user-id` | `"anonymous"` | User identifier for audit trail |
| `--context` | `"{}"` | JSON context blob |

**Example:**

```bash
delentia compile "Refactor authentication module" --user-id alice
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

### `delentia build`

Build a DSL execution graph from a compiled intent.

```bash
delentia build --intent-id ID [--dsl-file FILE] [--output FILE]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--intent-id` | required | Intent ID from `delentia compile` |
| `--dsl-file` | auto | Path to a `.dsl` file (optional) |
| `--output` | stdout | Write graph JSON to file |

**Example:**

```bash
delentia compile "Deploy microservice to staging" --user-id devops | delentia build --intent-id -
delentia build --intent-id a1b2c3d4 --output graph.json
```

---

### `delentia evaluate`

Evaluate a compiled + built intent through policy and governance checks.

```bash
delentia evaluate --intent-id ID [--architect-score FLOAT]
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
delentia evaluate --intent-id a1b2c3d4 --architect-score 0.9
```

---

### `delentia status`

Show current state of a compiled intent.

```bash
delentia status INTENT_ID
```

**Example:**

```bash
delentia status a1b2c3d4-5678-...
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

### `delentia list`

List recent intents.

```bash
delentia list [--limit N] [--status STATUS] [--user-id USER_ID]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--limit` | `10` | Max intents to show |
| `--status` | all | Filter by state (e.g., `COMPLETED`, `FAILED`) |
| `--user-id` | all | Filter by user |

---

### `delentia audit`

Display full audit trail for an intent.

```bash
delentia audit INTENT_ID [--output json]
```

**Example:**

```bash
delentia audit a1b2c3d4 --output json
```

Outputs the complete signed audit chain including FDIA score, SignedAI consensus
tier, and policy decisions.

---

### `delentia metrics`

Display runtime metrics for the Control Plane.

```bash
delentia metrics [--output json]
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

### `delentia reset`

Reset in-memory state (development/testing only).

```bash
delentia reset [--force]
```

!!! danger "Destructive Action"
    `delentia reset` clears all in-memory intent state. Use `--force` to skip confirmation.
    Persisted audit logs are **not** deleted.

---

### `delentia workflow run`

Run a DAG workflow defined in a `.yaml` file through the real ALGO-20
`WorkflowEngine` (real `networkx` DAG scheduling, real dependency-respecting
sequential/parallel/hybrid execution) - added 2026-09-25 (Round 44 item I.1).
This command builds `WorkflowEngine` directly rather than through the full
41-algorithm kernel, so it starts immediately (no torch/FAISS import cost).

```bash
delentia workflow run path/to/workflow.yaml [--poll-interval SECONDS]
```

Schema (maps 1:1 onto the engine's existing `TaskConfig`/`WorkflowDefinition`
- no new semantics invented):

```yaml
name: demo-workflow
mode: sequential   # sequential | parallel | hybrid
tasks:
  - id: fuse1
    type: fusion    # the only task type with a real executor today - see below
    depends_on: []
    config:
      fusion_config:
        modalities: {text: [0.1, 0.2, 0.3]}
        fusion_strategy: hybrid
  - id: fuse2
    type: fusion
    depends_on: [fuse1]
    config:
      fusion_config:
        modalities: {text: [0.7, 0.8, 0.9]}
```

!!! warning "Only `type: fusion` has a real executor today"
    `WorkflowEngine._run_task_type()` has a real executor for exactly one
    task type (`"fusion"` - real ALGO-19 Data Fusion). Any other `type`
    value is refused **at load time** by this command rather than silently
    accepted and run as a no-op that the engine would otherwise still mark
    `COMPLETED` (with an honest `"simulated": true` flag in its raw output,
    but the scheduler does not distinguish it from real completion when
    resolving downstream dependencies). Widen the allowlist in
    `rct_control_plane/workflow_yaml_loader.py` only once a real executor
    exists for a new type.

The command exits `0` only if every task in the workflow reaches a real
`completed` status; it exits `1` on a YAML/validation error or if any task
fails.

---

!!! warning "Removed 2026-09-24: `delentia intent submit` and `delentia health` do not exist"
    Both sections used to appear here but describe commands that are not
    registered by the real CLI - confirmed against `python -m
    rct_control_plane.cli --help`'s real output (`Error: No such command
    'intent'`/`'health'`). `delentia status` (with no argument) and
    `delentia doctor` cover overlapping ground for now; if a real
    equivalent to either removed command is wanted, that is new feature
    work, not a documentation fix.

---

## Shell Completion

Enable tab-completion for `bash`, `zsh`, or `fish` (Click derives the
completion env var name from the real program name, `delentia`, not `rct`):

```bash
# bash
eval "$(_DELENTIA_COMPLETE=bash_source delentia)"

# zsh
eval "$(_DELENTIA_COMPLETE=zsh_source delentia)"

# fish
eval (env _DELENTIA_COMPLETE=fish_source delentia)
```

---

## Environment Variables

!!! warning "Removed 2026-09-24: this table was fabricated"
    None of `RCT_PORT`, `RCT_LOG_LEVEL`, `RCT_STATE_DIR`, or
    `RCT_ARCHITECT_SCORE` are read anywhere in `rct_control_plane/cli.py`
    (confirmed by grepping the real source for `os.environ`/`os.getenv` -
    the only real env var touched there is `DELENTIA_DAEMON_ENABLED`,
    which the `start` command *sets*, not reads as user configuration).
    Every option shown elsewhere on this page (`--port`, `--reload`, etc.)
    is a real CLI flag, not an environment variable - use those instead.
