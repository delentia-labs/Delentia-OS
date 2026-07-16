#!/usr/bin/env python3
"""
RCT Platform — OpenTelemetry Adapter

Reads RCT delta trace JSONL events and converts them to OTLP (OpenTelemetry
Protocol) format. Exposes:

  • Prometheus-compatible /metrics endpoint (FastAPI optional)
  • OTLP stdout exporter (for integration with Jaeger/Grafana/Tempo)
  • Standalone CLI mode (file → metrics summary)

Metrics exported:
  rct_delta_compression_ratio     GAUGE     current compression ratio (0.0–1.0)
  rct_warm_recall_ms              HISTOGRAM  state reconstruction latency (ms)
  rct_delta_bytes_total           COUNTER    cumulative delta storage bytes
  rct_naive_bytes_total           COUNTER    cumulative naive storage bytes
  rct_adversarial_block_total     COUNTER    constitutionally blocked events
  rct_agent_action_total          COUNTER    total agent actions (by agent_id, outcome)
  rct_checkpoint_total            COUNTER    number of checkpoints created

Usage:
    # CLI summary from JSONL trace
    python tools/otel_adapter.py --input tools/delta_trace.jsonl

    # Start Prometheus /metrics server
    python tools/otel_adapter.py --input tools/delta_trace.jsonl --serve --port 8000

    # Watch a live-updating JSONL file
    python tools/otel_adapter.py --watch tools/live_trace.jsonl --serve

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


# ---------------------------------------------------------------------------
# Metric stores
# ---------------------------------------------------------------------------

@dataclass
class MetricStore:
    """In-memory metric registry compatible with Prometheus text format."""

    # Gauges (last-value)
    _gauges: Dict[str, float] = field(default_factory=dict)
    # Counters (ever-increasing)
    _counters: Dict[str, float] = field(default_factory=dict)
    # Histograms (list of observed values → summary stats)
    _histograms: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))  # type: ignore

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = _label_key(name, labels)
        self._gauges[key] = value

    def counter_add(self, name: str, delta: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = _label_key(name, labels)
        self._counters[key] = self._counters.get(key, 0.0) + delta

    def histogram_observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = _label_key(name, labels)
        self._histograms[key].append(value)

    def prometheus_text(self) -> str:
        """Render all metrics as Prometheus text format."""
        lines: List[str] = []

        # Gauges
        for key, value in sorted(self._gauges.items()):
            name, lbls = _parse_key(key)
            lines.append(f"# HELP {name} RCT Platform metric")
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{lbls} {value:.6f}")

        # Counters
        for key, value in sorted(self._counters.items()):
            name, lbls = _parse_key(key)
            lines.append(f"# HELP {name}_total RCT Platform counter")
            lines.append(f"# TYPE {name}_total counter")
            lines.append(f"{name}_total{lbls} {value:.0f}")

        # Histograms (simplified: sum, count, min, max, p50, p99)
        for key, values in sorted(self._histograms.items()):
            if not values:
                continue
            name, lbls = _parse_key(key)
            srt = sorted(values)
            n = len(srt)
            total = sum(srt)
            p50 = srt[int(n * 0.5)]
            p99 = srt[int(n * 0.99)]
            lines.append(f"# HELP {name} RCT Platform histogram (ms)")
            lines.append(f"# TYPE {name} summary")
            lines.append(f'{name}{{quantile="0.5"{_strip_braces(lbls)}}} {p50:.4f}')
            lines.append(f'{name}{{quantile="0.99"{_strip_braces(lbls)}}} {p99:.4f}')
            lines.append(f"{name}_sum{lbls} {total:.4f}")
            lines.append(f"{name}_count{lbls} {n}")

        return "\n".join(lines) + "\n"

    def summary_dict(self) -> Dict[str, Any]:
        """Return a compact JSON-serialisable summary."""
        result: Dict[str, Any] = {}
        for key, value in self._gauges.items():
            result[key] = round(value, 6)
        for key, value in self._counters.items():
            result[key + "_total"] = int(value)
        for key, values in self._histograms.items():
            if not values:
                continue
            srt = sorted(values)
            n = len(srt)
            result[key + "_p50"] = round(srt[int(n * 0.5)], 4)
            result[key + "_p99"] = round(srt[int(n * 0.99)], 4)
            result[key + "_count"] = n
            result[key + "_avg"] = round(sum(srt) / n, 4)
        return result


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def _label_key(name: str, labels: Optional[Dict[str, str]]) -> str:
    if not labels:
        return name
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{label_str}}}"


def _parse_key(key: str):
    if "{" in key:
        name, rest = key.split("{", 1)
        return name, "{" + rest
    return key, ""


def _strip_braces(lbls: str) -> str:
    """Remove surrounding { } for appending additional labels."""
    if lbls.startswith("{") and lbls.endswith("}"):
        inner = lbls[1:-1].strip()
        return ("," + inner) if inner else ""
    return ""


# ---------------------------------------------------------------------------
# Event ingestion
# ---------------------------------------------------------------------------

def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield parsed events from a JSONL file. Skips malformed lines."""
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"  ⚠ Line {lineno}: JSON parse error — {exc}", file=sys.stderr)


def ingest_trace(path: Path, store: MetricStore) -> int:
    """
    Read delta trace JSONL and update MetricStore.
    Returns number of events processed.
    """
    count = 0
    for event in _iter_jsonl(path):
        count += 1
        tick = event.get("tick", 0)
        agent_id = event.get("agent_id", "unknown")
        outcome = event.get("outcome", "unknown")

        # Gauge: compression ratio (latest value wins)
        ratio = event.get("compression_ratio")
        if ratio is not None:
            store.gauge("rct_delta_compression_ratio", float(ratio))

        # Counter: bytes
        delta_bytes = event.get("delta_bytes")
        if delta_bytes is not None:
            store.counter_add("rct_delta_bytes", float(delta_bytes), {"agent": agent_id})

        naive_bytes = event.get("naive_bytes")
        if naive_bytes is not None:
            store.counter_add("rct_naive_bytes", float(naive_bytes), {"agent": agent_id})

        # Histogram: recall latency
        recall_ms = event.get("recall_ms")
        if recall_ms is not None:
            store.histogram_observe("rct_warm_recall_ms", float(recall_ms), {"agent": agent_id})

        # Counter: adversarial blocks
        if outcome == "blocked":
            store.counter_add("rct_adversarial_block", 1.0, {"agent": agent_id})

        # Counter: total actions
        action = event.get("action_type", "unknown")
        store.counter_add(
            "rct_agent_action",
            1.0,
            {"agent": agent_id, "action": action, "outcome": outcome},
        )

        # Counter: checkpoints
        if event.get("checkpoint_created"):
            store.counter_add("rct_checkpoint", 1.0, {"agent": agent_id})

    return count


# ---------------------------------------------------------------------------
# Prometheus server (optional FastAPI / http.server)
# ---------------------------------------------------------------------------

def _serve_metrics(store: MetricStore, port: int, input_path: Optional[Path], watch: bool) -> None:
    """Start a simple HTTP server on /metrics endpoint."""
    try:
        from http.server import BaseHTTPRequestHandler, HTTPServer  # stdlib

        class MetricsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/metrics":
                    if watch and input_path and input_path.exists():
                        # Re-read file on every scrape for live watching
                        fresh_store = MetricStore()
                        ingest_trace(input_path, fresh_store)
                        body = fresh_store.prometheus_text().encode("utf-8")
                    else:
                        body = store.prometheus_text().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/health":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass  # suppress access logs

        server = HTTPServer(("0.0.0.0", port), MetricsHandler)
        print(f"  ✓  Prometheus metrics: http://localhost:{port}/metrics")
        print(f"  ✓  Health check:       http://localhost:{port}/health")
        print("  Press Ctrl+C to stop.")
        server.serve_forever()

    except ImportError:
        print("  http.server not available — cannot start metrics endpoint", file=sys.stderr)


# ---------------------------------------------------------------------------
# OTLP stdout span exporter
# ---------------------------------------------------------------------------

def export_otlp_spans(store: MetricStore, events: List[Dict[str, Any]]) -> None:
    """
    Print OTLP-compatible span records to stdout.
    Format: newline-delimited JSON, each line = one span.
    """
    import uuid

    trace_id = uuid.uuid4().hex
    for i, event in enumerate(events):
        span = {
            "traceId": trace_id,
            "spanId": uuid.uuid4().hex[:16],
            "parentSpanId": None,
            "name": f"rct.delta.{event.get('action_type', 'unknown')}",
            "kind": "SPAN_KIND_INTERNAL",
            "startTimeUnixNano": int(time.time() * 1e9) + i * 1_000_000,
            "endTimeUnixNano": int(time.time() * 1e9) + i * 1_000_000 + int(event.get("recall_ms", 0) * 1e6),
            "attributes": {
                "rct.tick": event.get("tick"),
                "rct.agent_id": event.get("agent_id"),
                "rct.outcome": event.get("outcome"),
                "rct.compression_ratio": event.get("compression_ratio"),
                "rct.recall_ms": event.get("recall_ms"),
            },
            "status": {
                "code": "STATUS_CODE_OK" if event.get("outcome") != "blocked" else "STATUS_CODE_ERROR",
            },
        }
        print(json.dumps(span, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RCT OpenTelemetry Adapter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Summarize a delta trace JSONL
  python tools/otel_adapter.py --input tools/delta_trace.jsonl

  # Export as OTLP spans to stdout
  python tools/otel_adapter.py --input tools/delta_trace.jsonl --otlp

  # Serve Prometheus /metrics endpoint
  python tools/otel_adapter.py --input tools/delta_trace.jsonl --serve

  # Live-watch a JSONL file (re-reads on each scrape)
  python tools/otel_adapter.py --watch tools/live_trace.jsonl --serve
""",
    )
    parser.add_argument("--input", "-i", type=Path, help="Path to delta trace JSONL file")
    parser.add_argument("--watch", type=Path, help="Live-watch JSONL file (re-reads on scrape)")
    parser.add_argument("--serve", action="store_true", help="Start Prometheus /metrics server")
    parser.add_argument("--port", type=int, default=8000, help="HTTP server port (default 8000)")
    parser.add_argument("--otlp", action="store_true", help="Export events as OTLP spans to stdout")
    parser.add_argument("--json", action="store_true", help="Print summary as JSON")
    args = parser.parse_args()

    input_path = args.input or args.watch
    if not input_path:
        parser.error("Provide --input or --watch with a JSONL file path.")

    if not input_path.exists():
        print(f"  ✗  File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    store = MetricStore()
    n = ingest_trace(input_path, store)
    print(f"  ✓  Ingested {n} events from {input_path}")

    if args.otlp:
        events = list(_iter_jsonl(input_path))
        export_otlp_spans(store, events)
        return

    if args.json:
        print(json.dumps(store.summary_dict(), indent=2, ensure_ascii=False))
        return

    if not args.serve:
        # Default: print Prometheus text + summary
        summary = store.summary_dict()
        print("\n  --- Metric Summary ---")
        for k, v in sorted(summary.items()):
            print(f"  {k:50s} {v}")

    if args.serve:
        _serve_metrics(store, args.port, input_path, watch=args.watch is not None)


if __name__ == "__main__":
    main()
