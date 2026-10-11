#!/usr/bin/env python3
"""Make a small synthetic ChampSim trace to sanity-check an L1D prefetcher.

Three load instructions run in a loop:
  IP_UNI  : uniform stride of +2 cache lines            (A, A+2, A+4, ...)
  IP_PAT  : repeating stride pattern +1,+2,+2,+2,+3     (the PA2 example)
  IP_RAND : random lines in a 256 KB region (noise; a good prefetcher should not chase it)
Each instruction record is the 64-byte input_instr struct from inc/instruction.h.
Usage: make_synth_trace.py OUT.champsimtrace.xz [num_loop_iterations]
"""
import lzma, random, struct, sys

LINE = 64
REG_IP, REG_FLAGS = 26, 25

def rec(ip, is_branch=0, taken=0, dregs=(0, 0), sregs=(0, 0, 0, 0), dmem=(0, 0), smem=(0, 0, 0, 0)):
    return struct.pack("<QBB2B4B2Q4Q", ip, is_branch, taken, *dregs, *sregs, *dmem, *smem)

def main():
    out = sys.argv[1]
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 400_000
    rnd = random.Random(42)
    uni = 0x10000000          # separate 256 MB regions so streams never overlap
    pat = 0x20000000
    rbase = 0x30000000
    pattern = [1, 2, 2, 2, 3]
    with lzma.open(out, "wb", preset=1) as f:
        for i in range(iters):
            f.write(rec(0x401000, dregs=(1, 0), sregs=(2, 0, 0, 0), smem=(uni, 0, 0, 0)))
            f.write(rec(0x401004, dregs=(3, 0), sregs=(1, 0, 0, 0)))                     # ALU
            f.write(rec(0x401008, dregs=(4, 0), sregs=(5, 0, 0, 0), smem=(pat, 0, 0, 0)))
            f.write(rec(0x40100c, dregs=(6, 0), sregs=(4, 3, 0, 0)))                     # ALU
            rline = rnd.randrange(1 << 12)   # 256 KB region: noise that mostly hits in L2
            f.write(rec(0x401010, dregs=(7, 0), sregs=(8, 0, 0, 0), smem=(rbase + rline * LINE, 0, 0, 0)))
            f.write(rec(0x401014, is_branch=1, taken=1, dregs=(REG_IP, 0), sregs=(REG_FLAGS, REG_IP, 0, 0)))
            uni += 2 * LINE
            pat += pattern[i % 5] * LINE

if __name__ == "__main__":
    main()
