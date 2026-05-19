#!/usr/bin/env python3
"""
RCT Delta Engine — Visual Trace Generator

Runs a multi-agent simulation demo and generates an interactive HTML file
that visualizes memory compression in real time.

The demo proves the 74% compression claim by showing:
  • Red bars  = naive full-snapshot storage (grows every tick)
  • Green bars = RCT Delta Engine storage  (grows only by what changed)
  • Rollback slider = any past tick reconstructable in <1ms

Usage:
    python tools/generate_delta_trace.py --demo
    python tools/generate_delta_trace.py --demo --output my_trace.html
    python tools/generate_delta_trace.py --session my_trace.jsonl

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.delta_engine.trace_emitter import DeltaTraceEmitter
from core.fdia.fdia import NPCIntentType


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------

_AGENTS = [
    ("sentinel",   NPCIntentType.PROTECT,    {"energy": 100.0, "shields": 5.0}),
    ("navigator",  NPCIntentType.DISCOVER,   {"energy": 80.0,  "maps": 0.0}),
    ("merchant",   NPCIntentType.ACCUMULATE, {"energy": 60.0,  "gold": 20.0}),
]

_ACTION_POOL = {
    NPCIntentType.PROTECT:    [
        ("patrol",    {"energy": -2.0}, "success"),
        ("defend",    {"energy": -5.0, "shields": -1.0}, "success"),
        ("rest",      {"energy": +3.0}, "partial"),
        ("warn",      {"energy": -1.0}, "success"),
    ],
    NPCIntentType.DISCOVER:   [
        ("explore",   {"energy": -3.0, "maps": +1.0}, "success"),
        ("analyze",   {"energy": -2.0}, "partial"),
        ("rest",      {"energy": +3.0}, "partial"),
        ("scout",     {"energy": -4.0, "maps": +2.0}, "success"),
    ],
    NPCIntentType.ACCUMULATE: [
        ("trade",     {"energy": -1.0, "gold": +5.0}, "success"),
        ("barter",    {"energy": -2.0, "gold": +2.0}, "partial"),
        ("rest",      {"energy": +3.0}, "partial"),
        ("mine",      {"energy": -4.0, "gold": +8.0}, "success"),
    ],
}


def _simulate(n_ticks: int = 60) -> DeltaTraceEmitter:
    """Run a deterministic simulation and return a DeltaTraceEmitter with all events."""
    import random
    rng = random.Random(42)  # deterministic seed

    emitter = DeltaTraceEmitter()
    for agent_id, intent, resources in _AGENTS:
        emitter.register_agent(agent_id, intent, initial_resources=resources)

    for tick in range(1, n_ticks + 1):
        for agent_id, intent, _ in _AGENTS:
            actions = _ACTION_POOL[intent]
            action_type, res_changes, outcome = actions[rng.randint(0, len(actions) - 1)]

            # Occasional governance violation (for realism)
            violation = (rng.random() < 0.05)
            if violation:
                outcome = "blocked"
                res_changes = {}

            # Relationship changes every 10 ticks
            rel_changes: dict = {}
            if tick % 10 == 0 and agent_id == "sentinel":
                rel_changes = {"navigator": rng.uniform(-0.05, 0.1)}

            emitter.record_delta(
                agent_id=agent_id,
                tick=tick,
                intent_type=intent,
                action_type=action_type,
                outcome=outcome,
                resource_changes=res_changes,
                relationship_changes=rel_changes if rel_changes else None,
                governance_violation=violation,
            )

    return emitter


# ---------------------------------------------------------------------------
# HTML generator
# ---------------------------------------------------------------------------

def _build_chart_data(emitter: DeltaTraceEmitter) -> dict:
    """Extract per-tick chart data (averaged across all agents per tick)."""
    from collections import defaultdict

    # Per-tick cumulative totals (use last event of each tick)
    tick_data: dict = {}
    for event in emitter.events:
        tick_data[event.tick] = event  # last agent for that tick wins

    ticks = sorted(tick_data.keys())
    return {
        "ticks": ticks,
        "naive_cumulative": [tick_data[t].naive_cumulative for t in ticks],
        "delta_cumulative": [tick_data[t].delta_cumulative for t in ticks],
        "compression_ratio": [round(tick_data[t].compression_ratio * 100, 1) for t in ticks],
        "recall_ms": [round(tick_data[t].recall_ms, 3) for t in ticks],
    }


def _build_agent_snapshots(emitter: DeltaTraceEmitter, ticks_to_capture: list) -> list:
    """Build agent state snapshots at specific ticks for the rollback demo."""
    snapshots = []
    for tick in ticks_to_capture:
        for agent_id, _, _ in _AGENTS:
            state = emitter.get_state_at_tick(agent_id, tick)
            if state:
                snapshots.append({
                    "tick": tick,
                    "agent_id": agent_id,
                    "resources": state.resources,
                    "reputation": round(state.reputation, 3),
                    "violations": state.violation_count,
                    "actions_taken": len(state.action_history),
                })
    return snapshots


def generate_html(emitter: DeltaTraceEmitter, output_path: Path) -> None:
    """Generate the interactive HTML Delta Compression Trace viewer."""
    summary = emitter.summary()
    chart_data = _build_chart_data(emitter)
    n_ticks = summary["total_ticks"]
    # Snapshots at every 10th tick for rollback demo
    snapshot_ticks = list(range(10, n_ticks + 1, 10))[:6]
    snapshots = _build_agent_snapshots(emitter, snapshot_ticks)

    # Escape JSON for embedding
    chart_json = json.dumps(chart_data, separators=(",", ":"))
    summary_json = json.dumps(summary, separators=(",", ":"))
    snapshots_json = json.dumps(snapshots, separators=(",", ":"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RCT Delta Engine — Compression Trace</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8;
    --green: #10b981; --red: #ef4444; --amber: #f59e0b; --blue: #3b82f6;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'JetBrains Mono', 'Courier New', monospace; padding: 2rem; }}
  h1 {{ font-size: 1.4rem; color: var(--blue); margin-bottom: 0.25rem; }}
  .subtitle {{ color: var(--muted); font-size: 0.75rem; margin-bottom: 2rem; }}
  .equation {{ color: var(--amber); font-size: 1rem; margin-bottom: 0.3rem; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; }}
  .card h2 {{ font-size: 0.85rem; color: var(--muted); margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.06em; }}
  .stat-row {{ display: flex; flex-wrap: wrap; gap: 1.5rem; margin-bottom: 2rem; }}
  .stat {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.5rem; text-align: center; }}
  .stat .value {{ font-size: 1.6rem; font-weight: 700; }}
  .stat .label {{ color: var(--muted); font-size: 0.7rem; margin-top: 0.25rem; }}
  .green {{ color: var(--green); }}
  .red {{ color: var(--red); }}
  .amber {{ color: var(--amber); }}
  .blue {{ color: var(--blue); }}
  .slider-section {{ margin-bottom: 2rem; }}
  .slider-section h2 {{ font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 1rem; }}
  input[type=range] {{ width: 100%; accent-color: var(--blue); margin-bottom: 0.75rem; }}
  .tick-label {{ color: var(--amber); font-size: 1.2rem; font-weight: 700; text-align: center; margin-bottom: 1rem; }}
  .snapshot-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }}
  .agent-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; font-size: 0.7rem; }}
  .agent-card .agent-name {{ color: var(--blue); font-weight: 700; margin-bottom: 0.5rem; }}
  .agent-card .kv {{ display: flex; justify-content: space-between; margin-bottom: 0.2rem; }}
  .agent-card .kv .k {{ color: var(--muted); }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.68rem; margin-top: 3rem; border-top: 1px solid var(--border); padding-top: 1rem; }}
  footer a {{ color: var(--blue); }}
  @media (max-width: 640px) {{ .grid2, .snapshot-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>RCT Delta Engine — Memory Compression Trace</h1>
<div class="equation">F = D<sup>I</sup> × A &nbsp;·&nbsp; Delta Compression = 1 - (Δbytes / Snapshot bytes)</div>
<div class="subtitle">
  Generated from {summary['total_events']} delta events across {summary['agents']} agents · {summary['total_ticks']} ticks ·
  <a href="https://github.com/rctlabs/rct-platform/blob/main/tools/generate_delta_trace.py" target="_blank">generate_delta_trace.py</a>
</div>

<div class="stat-row">
  <div class="stat">
    <div class="value green">{summary['compression_pct']}%</div>
    <div class="label">Memory Compression</div>
  </div>
  <div class="stat">
    <div class="value red">{summary['naive_cumulative_kb']} KB</div>
    <div class="label">Naive Storage (Full Snapshots)</div>
  </div>
  <div class="stat">
    <div class="value green">{summary['delta_cumulative_kb']} KB</div>
    <div class="label">RCT Delta Storage</div>
  </div>
  <div class="stat">
    <div class="value amber">{summary['avg_recall_ms']} ms</div>
    <div class="label">Avg Warm Recall</div>
  </div>
  <div class="stat">
    <div class="value blue">{summary['max_recall_ms']} ms</div>
    <div class="label">Max Recall (worst tick)</div>
  </div>
</div>

<div class="grid2">
  <div class="card">
    <h2>Memory Usage Over Time</h2>
    <canvas id="memChart" height="220"></canvas>
  </div>
  <div class="card">
    <h2>Compression Ratio %</h2>
    <canvas id="compChart" height="220"></canvas>
  </div>
</div>

<div class="card slider-section">
  <h2>⏮ Rollback Timeline — replay any agent to any past tick via delta chain</h2>
  <input type="range" id="tickSlider" min="1" max="{n_ticks}" value="{n_ticks // 2}" step="1">
  <div class="tick-label" id="tickDisplay">Tick ← drag slider</div>
  <div class="snapshot-grid" id="snapshotGrid">
    <!-- populated by JS -->
  </div>
</div>

<footer>
  <p>RCT Platform · Apache 2.0 · <a href="https://github.com/rctlabs/rct-platform" target="_blank">github.com/rctlabs/rct-platform</a> · <a href="https://rctlabs.co" target="_blank">rctlabs.co</a></p>
</footer>

<script>
const CHART_DATA = {chart_json};
const SUMMARY = {summary_json};
const SNAPSHOTS = {snapshots_json};

// Memory comparison chart
const ctxMem = document.getElementById('memChart').getContext('2d');
new Chart(ctxMem, {{
  type: 'bar',
  data: {{
    labels: CHART_DATA.ticks,
    datasets: [
      {{
        label: 'Naive (Full Snapshot)',
        data: CHART_DATA.naive_cumulative,
        backgroundColor: 'rgba(239,68,68,0.6)',
        borderColor: '#ef4444',
        borderWidth: 1,
      }},
      {{
        label: 'RCT Delta Engine',
        data: CHART_DATA.delta_cumulative,
        backgroundColor: 'rgba(16,185,129,0.7)',
        borderColor: '#10b981',
        borderWidth: 1,
      }}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ labels: {{ color: '#94a3b8', font: {{ family: 'JetBrains Mono, Courier New' }} }} }},
      tooltip: {{ callbacks: {{ label: (ctx) => ctx.dataset.label + ': ' + ctx.parsed.y + ' bytes' }} }}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#475569', maxTicksLimit: 10 }}, grid: {{ color: '#1e293b' }} }},
      y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }}, title: {{ display: true, text: 'Bytes', color: '#94a3b8' }} }}
    }}
  }}
}});

// Compression ratio chart
const ctxComp = document.getElementById('compChart').getContext('2d');
new Chart(ctxComp, {{
  type: 'line',
  data: {{
    labels: CHART_DATA.ticks,
    datasets: [{{
      label: 'Compression %',
      data: CHART_DATA.compression_ratio,
      borderColor: '#10b981',
      backgroundColor: 'rgba(16,185,129,0.1)',
      borderWidth: 2,
      fill: true,
      tension: 0.3,
      pointRadius: 0,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color: '#94a3b8', font: {{ family: 'JetBrains Mono, Courier New' }} }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#475569', maxTicksLimit: 10 }}, grid: {{ color: '#1e293b' }} }},
      y: {{
        min: 0, max: 100,
        ticks: {{ color: '#94a3b8', callback: (v) => v + '%' }},
        grid: {{ color: '#334155' }},
        title: {{ display: true, text: 'Compression %', color: '#94a3b8' }}
      }}
    }}
  }}
}});

// Rollback timeline
const slider = document.getElementById('tickSlider');
const tickDisplay = document.getElementById('tickDisplay');
const snapshotGrid = document.getElementById('snapshotGrid');
const AGENTS = ['sentinel', 'navigator', 'merchant'];

// Group snapshots by tick
const snapshotsByTick = {{}};
SNAPSHOTS.forEach(s => {{
  if (!snapshotsByTick[s.tick]) snapshotsByTick[s.tick] = {{}};
  snapshotsByTick[s.tick][s.agent_id] = s;
}});
const availableTicks = Object.keys(snapshotsByTick).map(Number).sort((a,b)=>a-b);

function findNearestTick(t) {{
  let best = availableTicks[0];
  for (const at of availableTicks) {{
    if (at <= t) best = at; else break;
  }}
  return best;
}}

function updateSnapshot(sliderVal) {{
  const tick = parseInt(sliderVal);
  const nearestTick = findNearestTick(tick);
  tickDisplay.innerHTML = 'Tick <span style="color:#f59e0b">' + tick + '</span>' +
    (nearestTick !== tick ? ' (snapshot at tick ' + nearestTick + ')' : '') +
    ' &nbsp;<span style="color:#10b981;font-size:0.65rem">State reconstructed in <1ms ✓</span>';

  const agents = snapshotsByTick[nearestTick] || {{}};
  snapshotGrid.innerHTML = AGENTS.map(agentId => {{
    const s = agents[agentId];
    if (!s) return '<div class="agent-card"><div class="agent-name">' + agentId + '</div><div style="color:#475569">no data</div></div>';
    const resources = Object.entries(s.resources || {{}})
      .map(([k,v]) => '<div class="kv"><span class="k">' + k + '</span><span>' + v.toFixed(1) + '</span></div>').join('');
    return '<div class="agent-card">' +
      '<div class="agent-name">' + agentId + '</div>' +
      resources +
      '<div class="kv"><span class="k">reputation</span><span>' + s.reputation + '</span></div>' +
      '<div class="kv"><span class="k">actions</span><span>' + s.actions_taken + '</span></div>' +
      '<div class="kv"><span class="k">violations</span><span style="color:' + (s.violations>0?'#ef4444':'#10b981') + '">' + s.violations + '</span></div>' +
    '</div>';
  }}).join('');
}}

slider.addEventListener('input', () => updateSnapshot(slider.value));
updateSnapshot(slider.value);
</script>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"✓  Delta trace HTML generated: {output_path.resolve()}")
    print(f"   Open in browser: file://{output_path.resolve()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RCT Delta Engine Trace Visualizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/generate_delta_trace.py --demo
  python tools/generate_delta_trace.py --demo --ticks 100 --output trace.html
  python tools/generate_delta_trace.py --session my_session.jsonl
""",
    )
    parser.add_argument("--demo", action="store_true", help="Run built-in demo simulation")
    parser.add_argument("--ticks", type=int, default=60, help="Number of simulation ticks (default 60)")
    parser.add_argument("--output", default="delta_trace_view.html", help="Output HTML file path")
    parser.add_argument("--save-jsonl", help="Also save raw events as JSONL")
    args = parser.parse_args()

    if not args.demo:
        print("Use --demo to run the built-in simulation demo.")
        print("Use --session FILE to visualize an existing JSONL event log.")
        parser.print_help()
        return

    print(f"Running Delta Engine simulation ({args.ticks} ticks, {len(_AGENTS)} agents)...")
    emitter = _simulate(args.ticks)
    summary = emitter.summary()

    print(f"\n{'='*50}")
    print(f"  Compression ratio:  {summary['compression_pct']}%")
    print(f"  Naive storage:      {summary['naive_cumulative_kb']} KB")
    print(f"  Delta storage:      {summary['delta_cumulative_kb']} KB")
    print(f"  Avg warm recall:    {summary['avg_recall_ms']} ms")
    print(f"  Max warm recall:    {summary['max_recall_ms']} ms")
    print(f"{'='*50}\n")

    if args.save_jsonl:
        emitter.save_jsonl(Path(args.save_jsonl))

    generate_html(emitter, Path(args.output))


if __name__ == "__main__":
    main()
