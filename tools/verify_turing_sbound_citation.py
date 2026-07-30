"""Numerical verification of the cited averaged bound on S(t) for zeta.

Statement under test -- Trudgian, "Improvements to Turing's method",
Math. Comp. 80 (2011), no. 276, 2259-2279, **Theorem 2.2**, p. 2261:

    If  t2 > t1 > 168*pi   then   | int_{t1}^{t2} S(t) dt |  <=  2.067 + 0.059 log t2.

Source conventions (Trudgian (1.1), (1.2), p. 2260):

    S(T) = pi^{-1} arg zeta(1/2 + iT)      (continuous variation 2 -> 2+iT -> 1/2+iT)

and equivalently, exactly,

    S(t) = N(t) - theta(t)/pi - 1,

with theta the *continuous* Riemann-Siegel theta function (mpmath `siegeltheta`)
and N(t) the ONE-SIDED count of nontrivial zeros rho with 0 < Im rho <= t,
with multiplicity.  (Trudgian's prose says "|t| <= T" but his displayed formula
(1.2) carries the constant 7/8, which is the one-sided normalisation; the
two-sided one would carry 7/4.  The sanity check below settles it.)

Method.  Write A(t) = int_0^t S.  Then int_{t1}^{t2} S = A(t2) - A(t1), and

    A(t) = sum_{gamma_k <= t} (t - gamma_k)  -  Theta(t)/pi  -  t,

where the first term is the EXACT antiderivative of the staircase N (closed
form, evaluated by prefix sums), and Theta(t) = int_0^t theta is done by
mpmath quadrature on unit panels (cumulative table) plus one short panel.

Zero ordinates come from mpmath `zetazero` (Gram/Rosser block enumeration; it
does not assume Rosser's rule, so no zero is skipped).

Also checked, for the same inequality shape |int S| <= a + b log t2 valid for
t2 > t1 > t0, the weaker historical triples recorded in Trudgian sec 2.1/2.3:
    Turing 1953        (2.07,  0.128,  168 pi)
    Lehman 1970        (1.7,   0.114,  168 pi)
    Trudgian c=5/4 d=1 (1.61,  0.0914, 168 pi)
"""

import bisect
import sys
from multiprocessing import Pool

from mpmath import mp

DPS = 25
mp.dps = DPS

ZFILE = sys.argv[1] if len(sys.argv) > 1 else "tools/zeta_zero_ordinates_10600.txt"
TMAX = mp.mpf(10500)

with open(ZFILE) as f:
    ZEROS = [mp.mpf(line.strip()) for line in f if line.strip()]

# prefix sums of the ordinates, for the exact staircase antiderivative
PREF = [mp.mpf(0)]
for g in ZEROS:
    PREF.append(PREF[-1] + g)

TOP = ZEROS[-1]
T0MIN = 168 * mp.pi  # 527.78757...
NPANEL = int(mp.floor(TMAX)) + 2

CANDIDATES = [
    ("Trudgian 2011 Thm 2.2", mp.mpf("2.067"), mp.mpf("0.059")),
    ("Turing 1953 (per Trudgian 2.1)", mp.mpf("2.07"), mp.mpf("0.128")),
    ("Lehman 1970 (per Trudgian 2.1)", mp.mpf("1.7"), mp.mpf("0.114")),
    ("Trudgian sec 2.3, c=5/4 d=1", mp.mpf("1.61"), mp.mpf("0.0914")),
]


def _panel(k):
    mp.dps = DPS
    return mp.nstr(mp.quad(mp.siegeltheta, [mp.mpf(k), mp.mpf(k + 1)]), 22)


def build_theta_table():
    with Pool(20) as p:
        vals = p.map(_panel, range(0, NPANEL), chunksize=32)
    tab = [mp.mpf(0)]
    for v in vals:
        tab.append(tab[-1] + mp.mpf(v))
    return tab


THETA_CUM = None  # THETA_CUM[k] = int_0^k theta


def Theta(t):
    """int_0^t theta(u) du."""
    k = int(mp.floor(t))
    rem = t - k
    base = THETA_CUM[k]
    if rem == 0:
        return base
    return base + mp.quad(mp.siegeltheta, [mp.mpf(k), t])


def ncount(t):
    """N(t) = #{ n : 0 < gamma_n <= t }."""
    return bisect.bisect_right(ZEROS, t)


def A(t):
    """int_0^t S(u) du."""
    i = bisect.bisect_right(ZEROS, t)
    stair = mp.mpf(i) * t - PREF[i]
    return stair - Theta(t) / mp.pi - t


def _A_str(t_str):
    mp.dps = DPS
    return mp.nstr(A(mp.mpf(t_str)), 22)


def S_pointwise(t):
    return mp.mpf(ncount(t)) - mp.siegeltheta(t) / mp.pi - 1


def S_two_sided(t):
    """What S would be under a two-sided reading of N (the wrong convention)."""
    return mp.mpf(2 * ncount(t)) - mp.siegeltheta(t) / mp.pi - 1


def S_direct(t):
    """pi^{-1} arg zeta(1/2+it), principal branch (valid when |S| < 1/2)."""
    return mp.arg(mp.zeta(mp.mpf(1) / 2 + 1j * t)) / mp.pi


def sanity_check():
    print("=" * 92)
    print("SANITY 1: which counting convention reproduces pi^-1 arg zeta(1/2+it)?")
    print("  one-sided:  S = N(t) - theta/pi - 1   with N = #{0 < gamma <= t}")
    print("  two-sided:  S = 2N(t) - theta/pi - 1")
    print("-" * 92)
    print(f"{'t':>11} {'one-sided S':>15} {'two-sided S':>15} "
          f"{'pi^-1 arg zeta':>16}   verdict")
    bad = 0
    for t in ["12.3", "20.7", "50.4", "100.3", "530.1", "1000.7", "2500.25",
              "5000.5", "9999.9"]:
        t = mp.mpf(t)
        a1, a2, b = S_pointwise(t), S_two_sided(t), S_direct(t)
        ok1 = abs(a1 - b) < mp.mpf("1e-15")
        verdict = "one-sided matches" if ok1 else "*** NEITHER ***"
        if not ok1:
            bad += 1
        print(f"{float(t):>11.4f} {float(a1):>+15.10f} {float(a2):>+15.10f} "
              f"{float(b):>+16.10f}   {verdict}")
    print(f"  one-sided mismatches: {bad}   (expected 0)")
    print()
    print("=" * 92)
    print("SANITY 2: A(t) = int_0^t S  vs  direct quadrature of S on a few windows")
    print("-" * 92)
    for t1, t2 in [("600.0", "601.0"), ("1000.0", "1005.0"),
                   ("3000.0", "3002.5")]:
        t1, t2 = mp.mpf(t1), mp.mpf(t2)
        exact = A(t2) - A(t1)
        # direct: integrate the staircase-minus-smooth function, splitting at
        # every zero ordinate inside the window
        pts = [t1] + [g for g in ZEROS if t1 < g < t2] + [t2]
        direct = mp.quad(S_pointwise, pts)
        print(f"  [{float(t1):.2f}, {float(t2):.2f}]  closed form "
              f"{float(exact):+.12f}   quadrature {float(direct):+.12f}   "
              f"diff {float(abs(exact - direct)):.2e}")
    print()


def table(Acache):
    t1s = [10, 50, 100, 500, 1000, 5000, 10000]
    hs = [1, 5, 20, 100, 500]
    a, b = CANDIDATES[0][1], CANDIDATES[0][2]
    print("=" * 92)
    print("TASK GRID -- bound = 2.067 + 0.059*log(t2)   (Trudgian 2011 Thm 2.2)")
    print("theorem hypothesis: t1 > 168*pi = %.5f" % float(T0MIN))
    print("-" * 92)
    print(f"{'t1':>7} {'h':>5} {'t2':>8} {'int S':>14} {'bound':>10} "
          f"{'|intS|/bound':>13}  status")
    worst = None
    for t1 in t1s:
        for h in hs:
            t1m, t2m = mp.mpf(t1), mp.mpf(t1 + h)
            v = Acache[t2m] - Acache[t1m]
            bd = a + b * mp.log(t2m)
            ratio = abs(v) / bd
            inr = t1m > T0MIN
            if inr and (worst is None or ratio > worst[0]):
                worst = (ratio, t1, h, v, bd)
            st = ("holds" if ratio <= 1 else "*** VIOLATED ***") if inr \
                else ("holds anyway" if ratio <= 1 else "fails (outside hyp.)")
            print(f"{t1:>7} {h:>5} {t1 + h:>8} {float(v):>+14.6f} "
                  f"{float(bd):>10.6f} {float(ratio):>13.6f}  "
                  f"{st}{'' if inr else '  [t1 < 168pi: OUTSIDE HYPOTHESIS]'}")
    print("-" * 92)
    if worst:
        print(">>> WORST in-hypothesis case on this grid: ratio = %.6f  at "
              "t1=%s h=%s  (int S = %+.6f, bound = %.6f)"
              % (float(worst[0]), worst[1], worst[2], float(worst[3]),
                 float(worst[4])))
    print()


def scan(Acache, lefts, hs):
    print("=" * 92)
    print("ADVERSARIAL SCAN over t1 in (168pi, 10500), many widths")
    print("-" * 92)
    results = {name: None for name, _, _ in CANDIDATES}
    probe_max = (mp.mpf(0), None, None)
    probe_a = (mp.mpf(-99), None, None)
    nwin = 0
    for t1 in lefts:
        if t1 <= T0MIN:
            continue
        a1 = Acache[t1]
        for h in hs:
            t2 = t1 + h
            if t2 > TMAX:
                continue
            nwin += 1
            v = Acache[t2] - a1
            av = abs(v)
            if av > probe_max[0]:
                probe_max = (av, t1, h)
            need = av - mp.mpf("0.059") * mp.log(t2)
            if need > probe_a[0]:
                probe_a = (need, t1, h)
            for name, a, b in CANDIDATES:
                r = av / (a + b * mp.log(t2))
                cur = results[name]
                if cur is None or r > cur[0]:
                    results[name] = (r, t1, h, v, a + b * mp.log(t2))
    print(f"  windows examined: {nwin}")
    print()
    print(f"{'triple (a, b)':<34} {'max |intS|/bound':>17} {'t1':>10} {'h':>8} "
          f"{'int S':>11} {'bound':>9}  status")
    ok = True
    for name, a, b in CANDIDATES:
        r, t1, h, v, bd = results[name]
        status = "SURVIVES" if r <= 1 else "*** VIOLATED ***"
        if r > 1:
            ok = False
        print(f"{name:<34} {float(r):>17.6f} {float(t1):>10.4f} "
              f"{float(h):>8.2f} {float(v):>+11.6f} {float(bd):>9.6f}  {status}")
    print()
    ma, mt1, mh = probe_max
    na, nt1, nh = probe_a
    print(f"  tightness: max |int S| over all scanned windows = {float(ma):.6f} "
          f"(t1={float(mt1):.5f}, h={float(mh):.3f})")
    print(f"  tightness: smallest `a` compatible with b = 0.059 on this data = "
          f"{float(na):.6f}")
    print(f"             (t1={float(nt1):.5f}, h={float(nh):.3f});  printed a = 2.067")
    print()
    print("RESULT: " + ("ALL CITED TRIPLES SURVIVED THE SCAN"
                        if ok else "*** SOME CITED TRIPLE VIOLATED ***"))
    print()
    return results


def repo_scaling(results):
    r, t1, h, v, bd = results["Trudgian 2011 Thm 2.2"]
    print("=" * 92)
    print("REPO CONVENTION: zetaMultCount counts |Im rho| <= t, i.e. TWO-SIDED,")
    print("so the repo-side error term is 2S and the usable bound is 2*(a+b log t2).")
    print("-" * 92)
    print(f"  worst scanned window t1={float(t1):.5f}, h={float(h):.3f}:")
    print(f"    one-sided  int S     = {float(v):+.6f}   bound {float(bd):.6f}")
    print(f"    two-sided  int (2S)  = {float(2 * v):+.6f}   bound "
          f"{float(2 * bd):.6f}")
    print("  (the ratio is scale invariant, so the factor 2 changes nothing)")
    print()


if __name__ == "__main__":
    print(f"zeros loaded: {len(ZEROS)}, last gamma = {float(TOP):.6f}")
    print(f"168*pi = {float(T0MIN):.6f},  mp.dps = {DPS}")
    print()
    print("building cumulative int theta table ...", flush=True)
    THETA_CUM = build_theta_table()
    globals()["THETA_CUM"] = THETA_CUM

    hs = [mp.mpf(x) for x in ["0.25", "0.5", "1", "2", "3", "5", "8", "13",
                              "21", "50", "100", "300", "1000"]]
    lefts = []
    x = mp.mpf("527.79")
    while x < TMAX:
        lefts.append(x)
        x += mp.mpf("2.13")
    for g in ZEROS:
        if T0MIN < g < TMAX:
            lefts.append(g + mp.mpf("1e-9"))
            lefts.append(g - mp.mpf("1e-9"))
    lefts = sorted(set(lefts))

    pts = set()
    for t1 in [mp.mpf(x) for x in [10, 50, 100, 500, 1000, 5000, 10000]]:
        for h in [1, 5, 20, 100, 500]:
            pts.add(t1)
            pts.add(t1 + h)
    for t1 in lefts:
        pts.add(t1)
        for h in hs:
            if t1 + h <= TMAX:
                pts.add(t1 + h)
    pts = sorted(pts)
    print(f"evaluating A(t) at {len(pts)} points ...", flush=True)
    strs = [mp.nstr(t, 25) for t in pts]
    with Pool(20) as p:
        vals = p.map(_A_str, strs, chunksize=64)
    Acache = {t: mp.mpf(v) for t, v in zip(pts, vals)}
    print("done.")
    print()

    sanity_check()
    table(Acache)
    res = scan(Acache, lefts, hs)
    repo_scaling(res)
