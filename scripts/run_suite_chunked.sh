#!/usr/bin/env bash
# Runs the whole test suite in chunks so that one native crash (seen on this Windows machine: an access violation while importing pyarrow) loses one chunk, not the run.
# Each chunk is re-run once if its process died without a summary line. Output: $1 (default /tmp/suite_chunks.log); a one-line result per chunk at the end.
OUT="${1:-/tmp/suite_chunks.log}"
cd "$(dirname "$0")/.." || exit 1
: > "$OUT"
run_chunk() {
  local name="$1"; shift
  local tmp="$OUT.$name.tmp"
  for attempt in 1 2; do
    python -m pytest -q -p no:cacheprovider -W ignore --no-header "$@" > "$tmp" 2>&1
    if tail -n 3 "$tmp" | grep -Eq "(passed|failed|error)"; then break; fi
    echo "[$name] attempt $attempt ended without a summary (crash?)" >> "$OUT"
  done
  echo "[$name] $(tail -n 1 "$tmp")" >> "$OUT"
  grep -E "^(FAILED|ERROR) " "$tmp" >> "$OUT"
}
run_chunk core core/tests microservices signedai/tests tests
files=$(ls rct_control_plane/tests/test_*.py | sort)
n=$(echo "$files" | wc -l)
per=$(( (n + 5) / 6 ))
i=0
for part in 1 2 3 4 5 6; do
  chunk=$(echo "$files" | sed -n "$((i*per+1)),$(((i+1)*per))p")
  i=$((i+1))
  [ -z "$chunk" ] && continue
  run_chunk "rct$part" $chunk
done
echo DONE >> "$OUT"
