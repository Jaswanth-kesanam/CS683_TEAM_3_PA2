#!/usr/bin/env python3
"""Collect IPC, speedup, L1D load MPKI, prefetch accuracy and coverage from results/.

usage: scripts/parse_results.py [baseline-tag] [other tags ...]
  default: baseline ipstride spp
Writes results/summary.csv and prints a table.
  speedup  = IPC(config) / IPC(baseline)
  coverage = (L1D load misses baseline - L1D load misses config) / L1D load misses baseline
  accuracy = the "ACCURACY" ChampSim prints for L1D (useful / issued to lower level)
"""
import csv, glob, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

def parse(path):
    txt = open(path, errors="replace").read()
    if "Region of Interest Statistics" not in txt:
        return None
    roi = txt.split("Region of Interest Statistics", 1)[1]
    d = {}
    m = re.search(r"CPU 0 cumulative IPC:\s*([\d.]+)", roi)
    d["ipc"] = float(m.group(1)) if m else float("nan")
    m = re.search(r"L1D LOAD\s+ACCESS:\s*(\d+)\s+HIT:\s*(\d+)\s+MISS:\s*(\d+).*?MPKI:\s*([\d.]+)", roi)
    if m:
        d["l1d_load_miss"] = int(m.group(3)); d["l1d_load_mpki"] = float(m.group(4))
    m = re.search(r"L1D USEFUL LOAD PREFETCHES:\s*(\d+)\s+PREFETCH ISSUED TO LOWER LEVEL:\s*(\d+)\s+ACCURACY:\s*([-\w.]+)", roi)
    if m:
        d["pf_useful"] = int(m.group(1)); d["pf_issued"] = int(m.group(2))
        d["accuracy"] = 100.0 * d["pf_useful"] / d["pf_issued"] if d["pf_issued"] else 0.0
    return d

def main():
    tags = sys.argv[1:] or ["baseline", "ipstride", "spp"]
    base_tag = tags[0]
    data = {}
    for tag in tags:
        for f in sorted(glob.glob(os.path.join(ROOT, tag, "*.txt"))):
            r = parse(f)
            if r:
                data.setdefault(os.path.basename(f)[:-4], {})[tag] = r
    rows = []
    for trace in sorted(data):
        base = data[trace].get(base_tag)
        for tag in tags:
            r = data[trace].get(tag)
            if not r:
                continue
            row = {"trace": trace, "config": tag, "ipc": r["ipc"], "l1d_load_mpki": r.get("l1d_load_mpki"),
                   "accuracy_pct": r.get("accuracy") if tag != base_tag else None}
            if base:
                row["speedup"] = r["ipc"] / base["ipc"]
                bm = base.get("l1d_load_miss")
                row["coverage_pct"] = (100.0 * (bm - r["l1d_load_miss"]) / bm) if (bm and tag != base_tag) else None
            rows.append(row)
    os.makedirs(ROOT, exist_ok=True)
    out = os.path.join(ROOT, "summary.csv")
    cols = ["trace", "config", "ipc", "speedup", "l1d_load_mpki", "accuracy_pct", "coverage_pct"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})
    fmt = lambda v: "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
    print(" | ".join(f"{c:>14}" for c in cols))
    for r in rows:
        print(" | ".join(f"{fmt(r.get(c)):>14}" for c in cols))
    print(f"\nwrote {out}")

if __name__ == "__main__":
    main()
