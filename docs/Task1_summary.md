# Task 1 — Data Prefetching (IP-stride and Stride Pattern Prefetcher)

All runs: ChampSim (PA2 repo), GCC 7.5, 1 core, 25M warm-up + 25M simulated instructions,
L2C replacement = LRU, on the three course traces. Baseline = no L1D prefetcher.

## Task 1A — How the IP-stride prefetcher works (`prefetcher/ip_stride.l1d_pref`)

- **Table:** 24 entries (`IP_TRACKER_COUNT`), fully associative with LRU replacement. Each entry holds
  the IP, the last cache-line address that IP touched, the last stride, and an LRU counter.
- **IP bits:** only the low 8 bits of the IP are kept (`MASK_IP 0xFF`), so different loads whose
  low 8 bits match share one entry (aliasing).
- **On every L1D access** the address is turned into a cache-line address (`addr >> 6`), because
  prefetching works on 64-byte lines, not bytes.
- **Table miss:** the LRU entry is replaced with this IP and its line address; no prefetch yet
  (a stride needs two accesses).
- **Table hit:** stride = current line − last line (signed). A stride of 0 is ignored.
- **When it prefetches:** only when the new stride equals the previous stride, i.e. the same stride
  seen twice in a row. There is no confidence counter, so a single mismatch stops prefetching.
- **Degree:** fixed at 3 (`PREFETCH_DEGREE`): lines +1×, +2×, +3× stride ahead.
- **Page boundary:** it stops as soon as a prefetch would leave the current 4 KB page.
- **Fill level:** into L1 if the L1D MSHR is less than half full, otherwise into L2.
- **Limitations:** 8-bit IP aliasing, no confidence, fixed degree with no throttling, it cannot
  follow repeating stride *sequences*, and it also trains on prefetch requests
  (the hook is called with `type == PREFETCH` from the prefetch queue).

## Task 1B — Stride Pattern Prefetcher (`prefetcher/spp.l1d_pref`)

### Design

1. **Per-IP table (IPT)**, 32 entries, fully associative, LRU. Tracks each load's last line,
   last stride, a 2-bit uniform-stride confidence and a 12-bit *signature* of its recent strides.
2. **Pattern table (PT)**, 256 entries, shared by all IPs: *signature → next stride* with a 2-bit
   confidence. Signature update: `sig = ((sig << 3) XOR stride) & 0xFFF` (≈ last 4 strides).
   For +1,+2,+2,+2,+3 at least 3 past strides are needed: after (+2,+2) the next stride can be
   +2 or +3, but every window of 3 strides has exactly one successor.
3. **Dual pattern classification (uniform first):**
   - *Uniform*: if confidence ≥ 2 → prefetch line + k·stride, k = 1..degree.
   - *Non-uniform*: otherwise (or if the PT confidently predicts a different stride, which means
     we are inside a repeating sequence such as +2,+2,+2 before a +3) → walk the PT ahead:
     predict a stride, update the signature as if it happened, predict the next, … up to the degree.
4. **Accuracy-based throttling:** every 256 prefetches issued, accuracy = useful / issued in that
   window (ChampSim's `pf_useful` / `pf_lower_level`, the same values it reports as ACCURACY).

   | Accuracy | Degree |
   |---|---|
   | ≥ 75 % | 4 |
   | 50–75 % | 3 |
   | 25–50 % | 2 |
   | < 25 % | 1 |

   Start degree 2. Degree never goes to 0, otherwise there is nothing left to measure and the
   prefetcher could never recover.
5. Trains only on demand loads (`type == LOAD`), never crosses a 4 KB page, and keeps IP-stride's
   MSHR rule for choosing the L1 or L2 fill level.

### Storage overhead (exact bit-level breakdown)

| Structure | Field | Bits |
|---|---|---|
| IP table entry | valid | 1 |
| | IP tag (hashed IP) | 10 |
| | last line address (low bits) | 12 |
| | last stride (signed, −64..+63) | 7 |
| | uniform confidence | 2 |
| | signature | 12 |
| | LRU position (32 entries) | 5 |
| | **per entry** | **49** |
| IP table total | 32 × 49 | **1568** |
| Pattern table entry | next stride (signed) | 7 |
| | confidence | 2 |
| | **per entry** | **9** |
| Pattern table total | 256 × 9 | **2304** |
| Throttling | current degree | 3 |
| | prefetches issued in window (0..256) | 9 |
| | useful prefetches in window (0..256) | 9 |
| | **total** | **21** |
| **SPP total** | | **3893 bits ≈ 487 bytes** |

### Results

| Trace | Config | IPC | Speedup | L1D load MPKI | Accuracy (%) | Coverage (%) |
|---|---|---|---|---|---|---|
| trace1 | baseline | 0.2322 | 1.0000 | 10.679 | – | – |
| trace1 | IP-stride | 0.2333 | 1.0047 | 10.118 | 53.0 | 5.25 |
| trace1 | **SPP** | **0.2338** | **1.0067** | **9.852** | 52.3 | **7.74** |
| trace2 | baseline | 0.2513 | 1.0000 | 13.536 | – | – |
| trace2 | IP-stride | 0.2512 | 0.9995 | 13.438 | 38.0 | 0.72 |
| trace2 | **SPP** | **0.2516** | **1.0013** | **13.354** | **38.9** | **1.35** |
| trace3 | baseline | 0.3819 | 1.0000 | 3.403 | – | – |
| trace3 | IP-stride | 0.3827 | 1.0022 | 3.319 | 15.9 | 2.49 |
| trace3 | **SPP** | **0.3841** | **1.0058** | **3.197** | **30.0** | **6.06** |

Geometric-mean speedup: IP-stride 1.0021, SPP 1.0046. SPP covers about twice as many L1D load
misses as IP-stride (mean coverage 5.05 % vs 2.82 %) at higher mean accuracy (40.4 % vs 35.6 %);
on trace3 its accuracy nearly doubles (30.0 % vs 15.9 %). IP-stride slightly slows trace2 down,
SPP does not. Absolute gains are small because these traces are dominated by misses with no
regular per-IP stride (coverage stays below 8 % for both prefetchers).

Plots: `results/plots/speedup.png`, `l1d_mpki.png`, `accuracy.png`, `coverage.png`.

### How the throttling thresholds and degrees were chosen (sensitivity sweep)

`scripts/sweep_spp.sh` rebuilds SPP with different settings; all on the same three traces.

| Variant | Accuracy bands → degrees | Geomean speedup | Mean accuracy | Mean coverage |
|---|---|---|---|---|
| **SPP (chosen)** | ≥75/50/25 % → 4/3/2, else 1 | 1.0046 | 40.4 % | 5.05 % |
| stricter thresholds | ≥90/70/40 % → 4/3/2, else 1 | 1.0045 | 40.9 % | 4.50 % |
| looser thresholds | ≥60/40/20 % → 4/3/2, else 1 | 1.0048 | 39.8 % | 5.34 % |
| more aggressive degrees | ≥75/50/25 % → 8/4/2, else 1 | 1.0048 | 40.3 % | 5.26 % |
| no throttling, degree 2 | always 2 | 1.0047 | 38.5 % | 5.04 % |
| no throttling, degree 4 | always 4 | 1.0048 | 34.9 % | 6.12 % |

- **Thresholds:** stricter bands keep a little more accuracy but lose coverage; looser bands
  gain coverage but lose accuracy. 75/50/25 % sits between them, splitting the accuracy range
  into four equal bands.
- **Degrees:** a fixed degree 4 gives the most coverage but drops accuracy to 34.9 % (29.4 % on
  trace2): many more useless prefetches for no IPC gain, i.e. wasted bandwidth and cache
  pollution. Degree 8 at high accuracy adds almost nothing over 4, because only about a quarter of
  the accuracy windows reach ≥ 75 % on these traces. So the degree is 4 only when prefetches are reliably useful, and
  shrinks towards 1 as accuracy falls, keeping accuracy close to the best variant while keeping
  most of the coverage.
- **Honest note:** on these traces all variants are within 0.03 % IPC of each other, so the choice
  is driven by accuracy and coverage (bandwidth and pollution), not by IPC.
