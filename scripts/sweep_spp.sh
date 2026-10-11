#!/bin/bash
# Sensitivity sweep for SPP's accuracy throttling (Task 1 deliverable:
# "how did you choose the thresholds and the degrees?").
# Each variant = prefetcher/spp.l1d_pref with a few #defines overridden on top.
#   usage: scripts/sweep_spp.sh [jobs] [trace-dir]
# Results land in results/spp_<variant>/ ; compare with
#   python3 scripts/parse_results.py baseline spp spp_<variant> ...
set -e
cd "$(dirname "$0")/.."
JOBS=${1:-$(nproc)}; TRACE_DIR=${2:-../traces}
declare -A V
V[t_strict]="#define ACC_HIGH 90\n#define ACC_MID 70\n#define ACC_LOW 40"      # stricter thresholds
V[t_loose]="#define ACC_HIGH 60\n#define ACC_MID 40\n#define ACC_LOW 20"       # looser thresholds
V[d_aggr]="#define DEG_HIGH 8\n#define DEG_MID 4\n#define DEG_LOW 2"           # more aggressive degrees
V[fixed2]="#define DEG_HIGH 2\n#define DEG_MID 2\n#define DEG_LOW 2\n#define DEG_MIN 2"   # no throttling, degree 2
V[fixed4]="#define DEG_HIGH 4\n#define DEG_MID 4\n#define DEG_LOW 4\n#define DEG_MIN 4\n#define START_DEGREE 4"  # no throttling, degree 4
for name in "${!V[@]}"; do
  f=prefetcher/spp_$name.l1d_pref
  { printf "%b\n" "${V[$name]}"; cat prefetcher/spp.l1d_pref; } > "$f"
  [ -x "$(ls bin/*-spp_$name 2>/dev/null | head -1)" ] || ./build_champsim.sh spp_$name lru spp_$name > /dev/null 2>&1
  rm -f "$f"
done
for name in "${!V[@]}"; do scripts/run_all.sh spp_$name "$JOBS" "$TRACE_DIR"; done
