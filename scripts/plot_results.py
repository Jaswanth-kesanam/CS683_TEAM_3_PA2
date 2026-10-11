#!/usr/bin/env python3
"""Make the four PA2 Task 1 plots from results/summary.csv.

usage: scripts/plot_results.py [baseline-tag] [prefetcher tags ...]   (default: baseline ipstride spp)
Writes results/plots/{speedup,l1d_mpki,accuracy,coverage}.png
"""
import csv, os, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
tags = sys.argv[1:] or ["baseline", "ipstride", "spp"]
base, pfs = tags[0], tags[1:]
rows = list(csv.DictReader(open(os.path.join(ROOT, "summary.csv"))))
traces = sorted({r["trace"] for r in rows})
val = {(r["trace"], r["config"]): r for r in rows}
COLORS = ["#4C72B0", "#8FB0D8", "#55A868", "#C44E52", "#8172B2"]
os.makedirs(os.path.join(ROOT, "plots"), exist_ok=True)

def get(t, c, k):
    v = val.get((t, c), {}).get(k)
    return float(v) if v not in (None, "", "None") else 0.0

def bars(configs, key, ylabel, title, fname, hline=None):
    n = len(configs); w = 0.8 / n
    fig, ax = plt.subplots(figsize=(max(6, 1.1 * len(traces) + 2), 4.2))
    for i, c in enumerate(configs):
        xs = [j + (i - (n - 1) / 2) * w for j in range(len(traces))]
        ax.bar(xs, [get(t, c, key) for t in traces], w, label=c, color=COLORS[i % len(COLORS)], edgecolor="#555")
    if hline is not None:
        ax.axhline(hline, color="#C44E52", ls="--", lw=1, label=base)
    ax.set_xticks(range(len(traces))); ax.set_xticklabels(traces, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(ylabel); ax.set_title(title); ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(ROOT, "plots", fname), dpi=150); plt.close(fig)

bars(pfs, "speedup", "Speedup", "Speedup of L1D prefetchers over baseline (no prefetching)", "speedup.png", hline=1.0)
bars([base] + pfs, "l1d_load_mpki", "L1D load MPKI", "L1D load MPKI", "l1d_mpki.png")
bars(pfs, "accuracy_pct", "L1D prefetch accuracy (%)", "L1D prefetch accuracy", "accuracy.png")
bars(pfs, "coverage_pct", "L1D prefetch coverage (%)", "L1D prefetch coverage", "coverage.png")
print("plots written to", os.path.join(ROOT, "plots"))
