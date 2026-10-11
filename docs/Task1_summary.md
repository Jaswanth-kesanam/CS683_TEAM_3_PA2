# Task 1: Data Prefetching

All numbers below come from ChampSim built with GCC 7.5, single core, 25M warmup and 25M
simulated instructions, LRU at the L2, on the three course traces. The baseline has no L1D
prefetcher.

## Task 1A: How the IP-stride prefetcher works

The IP-stride prefetcher keeps a small table of 24 entries. Each entry belongs to one load
instruction and stores that instruction's IP, the last cache line it touched, the last stride it
saw, and an LRU counter used for replacement. Only the lower 8 bits of the IP are stored, so two
different loads with the same lower 8 bits end up sharing an entry.

Every time the L1D is accessed, the address is first converted to a cache line number (address
shifted right by 6, since lines are 64 bytes). The prefetcher then looks for the IP in its table.
If the IP is not there, the least recently used entry is replaced and nothing is prefetched, since
one access is not enough to see a stride.

If the IP is found, the stride is the difference between the current line and the last line. A
stride of zero is ignored. Prefetching happens only when the new stride is equal to the previous
stride, that is, the same stride has been seen twice in a row. In that case it prefetches the next
three lines along the stride (the degree is fixed at 3), stopping early if a prefetch would go past
the current 4 KB page. If the L1D MSHR is more than half full, the prefetched line is brought only
into the L2 instead of the L1. Finally the entry is updated with the new line and stride.

For example, if a load touches lines 200, 203, 206 and 210, nothing happens at 200 and 203. At 206
the stride +3 has repeated, so it prefetches 209, 212 and 215. At 210 the stride changes to +4 and
it stops. In this case all three prefetches were wasted.

Some limitations I noticed while reading the code:

- There is no confidence counter, so one odd access stops prefetching and two accidental matches
  start it.
- The degree is always 3, even when most prefetches turn out to be useless.
- It can only follow a constant stride. A repeating pattern like +1, +2, +2, +2, +3 only triggers it
  during the run of +2s, and then it guesses +2 forever and gets the +3 and +1 wrong.
- ChampSim also calls the prefetcher for prefetch requests, not only for demand loads, and IP-stride
  does not check the type, so it partly trains on its own prefetches.

## Task 1B: Stride Pattern Prefetcher (SPP)

### Idea

SPP also works per load instruction, but it can handle two kinds of behaviour. If an instruction
keeps using the same stride, it is treated like IP-stride. If the strides change but follow a
repeating sequence, SPP remembers a short history of recent strides (a signature) and uses it to
look up what stride usually comes next.

### Structures

The first structure is the IP table, with 32 entries, fully associative with LRU replacement. Each
entry stores a valid bit, a 10-bit tag made by hashing the full IP (instead of keeping only 8 raw
bits), the lower 12 bits of the last line address, the last stride as a 7-bit signed number (a page
has 64 lines, so -64 to +63 is enough), a 2-bit confidence counter for the constant stride, a 12-bit
signature, and a 5-bit LRU position.

The second structure is the pattern table, with 256 entries shared by all instructions. Each entry
maps a signature to the stride that followed it, along with a 2-bit confidence counter.

The signature is updated as `(signature << 3) XOR stride`, keeping only 12 bits. Each new stride
pushes the older ones to the left and the oldest falls off after about four strides. At least three
strides of history are needed for the PDF's example pattern +1, +2, +2, +2, +3: after just
(+2, +2) the next stride could be +2 or +3, but every window of three strides has only one possible
next stride.

### How a prediction is made

On every demand load, SPP finds or allocates the instruction's entry and computes the stride. The
confidence counter goes up by one if the stride repeats and down by one if it changes. The pattern
table is trained with the old signature and the new stride, and then the signature is updated.

If the confidence is at least 2, SPP treats the stride as constant and prefetches line + stride,
line + 2 x stride and so on, up to the current degree. There is one exception: if the pattern table
confidently predicts a different stride than the current one, SPP assumes it is in the middle of a
repeating sequence (like the +2, +2, +2 just before a +3) and uses the pattern instead.

Otherwise it uses the pattern table. It looks up the predicted next stride, prefetches that line,
then updates a copy of the signature as if that stride had happened and looks up the next one. This
continues until it reaches the degree, hits a low-confidence entry, or would leave the page.

A few smaller rules: SPP only trains on demand loads, never prefetches across a 4 KB page, and uses
the same MSHR check as IP-stride to decide whether to fill into L1 or L2.

### Accuracy-based throttling

Every 256 prefetches, SPP computes the accuracy for that window as useful prefetches divided by
issued prefetches, using ChampSim's own L1D counters (the same ones it prints as ACCURACY). The
degree is then set to 4 if accuracy is 75% or more, 3 if it is between 50% and 75%, 2 if it is
between 25% and 50%, and 1 below 25%. It starts at 2.

### Storage overhead

IP table entry:
- valid: 1 bit
- IP tag: 10 bits
- last line: 12 bits
- last stride: 7 bits
- confidence: 2 bits
- signature: 12 bits
- LRU: 5 bits
- total: 49 bits per entry, 32 entries = 1568 bits

Pattern table entry:
- next stride: 7 bits
- confidence: 2 bits
- total: 9 bits per entry, 256 entries = 2304 bits

Throttling:
- current degree: 3 bits
- prefetches issued in the window: 9 bits
- useful prefetches in the window: 9 bits
- total: 21 bits

Overall: 1568 + 2304 + 21 = 3893 bits, which is about 487 bytes.

## Results

On trace1 the baseline IPC is 0.2322. IP-stride gives a speedup of 1.0047, brings the L1D load
MPKI from 10.68 to 10.12, with 53.0% accuracy and 5.25% coverage. SPP gives 1.0067, MPKI 9.85,
52.3% accuracy and 7.74% coverage.

On trace2 the baseline IPC is 0.2513. IP-stride actually slows it down slightly (0.9995), with MPKI
13.54 to 13.44, 38.0% accuracy and 0.72% coverage. SPP gives 1.0013, MPKI 13.35, 38.9% accuracy and
1.35% coverage.

On trace3 the baseline IPC is 0.3819. IP-stride gives 1.0022, MPKI 3.40 to 3.32, 15.9% accuracy and
2.49% coverage. SPP gives 1.0058, MPKI 3.20, 30.0% accuracy and 6.06% coverage.

So SPP is better than IP-stride on all three traces in speedup, MPKI and coverage, and its accuracy
is the same or better (almost double on trace3). The overall gains are still small, because coverage
stays below 8% for both prefetchers. Most of the misses in these traces do not follow any per-IP
stride, so a stride-based prefetcher cannot remove them.

The plots are in `results/plots/` and the raw numbers are in `results/summary.csv`.

## How I chose the accuracy thresholds

I split the 0 to 100% accuracy range into four equal bands at 25%, 50% and 75%, so each 25% change
in accuracy moves the degree by one step. This keeps the logic simple, just three comparisons.
Accuracy is measured over windows of 256 prefetches rather than over the whole run, so the degree
can follow changes in the program's behaviour.

## Why these degrees

When accuracy is 75% or more, almost every prefetch gets used, so going further ahead (degree 4)
hides more latency without much risk. Between 50% and 75% I use degree 3, the same as IP-stride.
Between 25% and 50% at most half the prefetches are useful, so I reduce to 2 to save bandwidth while
still meeting the requirement of a degree above 1. Below 25% most prefetches are wrong, so I drop
to 1.

I never go down to 0, because with no prefetches there is nothing to measure and the prefetcher
could never recover. I also stop at 4, because the L1D only has 16 MSHRs and a 16-entry prefetch
queue, so a larger degree mostly adds requests that get dropped or arrive late, and every wrong
prefetch evicts a useful line from the 48 KB L1D.

The throttling does change the degree during the runs. Out of the accuracy windows in each run, the
number that ended at degree 1, 2, 3 and 4 was 12, 145, 148 and 91 on trace1, 30, 49, 33 and 28 on
trace2, and 49, 82, 65 and 63 on trace3.
