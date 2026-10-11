#!/bin/bash
# Run one ChampSim binary on every trace, a few at a time.
#   usage: scripts/run_all.sh <binary-tag> [parallel-jobs] [trace-dir]
#   e.g.   scripts/run_all.sh baseline 4 ../traces
# <binary-tag> is the last word you gave build_champsim.sh (baseline, ipstride, spp, ...).
# Output: results/<binary-tag>/<trace-name>.txt  (existing results are skipped)
set -e
cd "$(dirname "$0")/.."
TAG=$1; JOBS=${2:-$(nproc)}; TRACE_DIR=${3:-../traces}
WARMUP=${WARMUP:-25000000}; SIM=${SIM:-25000000}
[ -z "$TAG" ] && { echo "usage: $0 <binary-tag> [jobs] [trace-dir]"; exit 1; }
BIN=$(ls bin/*-"$TAG" 2>/dev/null | head -1)
[ -x "$BIN" ] || { echo "no binary bin/*-$TAG (build it with ./build_champsim.sh ... $TAG)"; exit 1; }
OUT=results/$TAG; mkdir -p "$OUT"
echo "binary: $BIN | traces: $TRACE_DIR | warmup=$WARMUP sim=$SIM | jobs=$JOBS"
ls "$TRACE_DIR"/*.xz | while read -r t; do
  name=$(basename "$t" .champsimtrace.xz)
  [ -s "$OUT/$name.txt" ] && grep -q "Region of Interest" "$OUT/$name.txt" && continue
  echo "$t"
done | xargs -P "$JOBS" -I{} bash -c '
  t={}; name=$(basename "$t" .champsimtrace.xz)
  echo "[start] $name"
  "'"$BIN"'" -warmup_instructions '"$WARMUP"' -simulation_instructions '"$SIM"' -traces "$t" > "'"$OUT"'/$name.txt" 2>&1 \
    && echo "[done]  $name" || echo "[FAIL]  $name (see '"$OUT"'/$name.txt)"'
