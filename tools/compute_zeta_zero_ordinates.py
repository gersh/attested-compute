"""Cache the zeta zero ordinates gamma_1 .. gamma_M with gamma_M > TMAX.

Uses mpmath.zetazero, which uses Gram/Rosser block logic and does not assume
Rosser's rule, so the enumeration is complete (no zeros skipped).  Output: one
decimal ordinate per line, ascending.  Parallel over indices.
"""
import sys
from multiprocessing import Pool
from mpmath import mp


def one(n):
    mp.dps = 25
    return mp.nstr(mp.im(mp.zetazero(n)), 22)


if __name__ == "__main__":
    mp.dps = 25
    TMAX = mp.mpf(sys.argv[1]) if len(sys.argv) > 1 else mp.mpf(10600)
    out = sys.argv[2] if len(sys.argv) > 2 else "zeros.txt"
    M = int(mp.nzeros(TMAX))
    print(f"nzeros({TMAX}) = {M}", file=sys.stderr)
    with Pool(20) as p:
        vals = p.map(one, range(1, M + 1), chunksize=8)
    with open(out, "w") as f:
        f.write("\n".join(vals) + "\n")
    print("done", file=sys.stderr)
