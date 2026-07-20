#!/usr/bin/env python3
"""GRH proof-of-concept driver (arXiv:1305.3087, Platt).

Runs the rigorous GPU interval evaluator ``sparkinterval-grh-lambda`` for the
completed Dirichlet functions

    Lambda_chi(t) = eps_chi (q/pi)^{it/2} Gamma((1/2 + a_chi + it)/2)
                    exp(pi t/4) L_chi(1/2 + it)

of every character chi of one modulus q on an ordinate grid, isolates strict
sign-change brackets for each primitive character, cross-checks a sample of
GPU enclosures against high-precision mpmath recomputation, applies a
numeric (non-formal) Turing-style expected-count check, and emits a
certificate JSON whose bracket rows feed the Lean checker
``SparkInterval.Zeta.EndpointCertificate.RationalBracketFamily``.

The GPU enclosures are rigorous modulo the CUDA Math API maximum-ulp error
documentation for log/exp/sin/cos/atan (see gpu/src/grh_lambda_poc.cu).  The
Lean side re-checks bracket shape, strict signs, and ordering from the exact
binary64 data; enclosure realization for the analytic evaluator remains the
explicit `EnclosesEndpoints` premise, as for the Riemann Hardy-Z path.

Subcommands:
  run      compute Lambda enclosures, isolate zeros, write certificate JSON
  verify   recheck a certificate JSON on CPU with exact rational arithmetic
"""

import argparse
import hashlib
import json
import math
import pathlib
import struct
import subprocess
import sys
import time
from fractions import Fraction

import mpmath

INPUT_MAGIC = b"SGRHIN01"
OUTPUT_MAGIC = b"SGRHOT01"

# B_{2j} for 2j = 2..26.
BERNOULLI = {
    2: Fraction(1, 6),
    4: Fraction(-1, 30),
    6: Fraction(1, 42),
    8: Fraction(-1, 30),
    10: Fraction(5, 66),
    12: Fraction(-691, 2730),
    14: Fraction(7, 6),
    16: Fraction(-3617, 510),
    18: Fraction(43867, 798),
    20: Fraction(-174611, 330),
    22: Fraction(854513, 138),
    24: Fraction(-236364091, 2730),
    26: Fraction(8553103, 6),
}


def factorial(n):
    result = 1
    for k in range(2, n + 1):
        result *= k
    return result


def fraction_to_interval(value):
    """Outward-rounded binary64 interval containing an exact Fraction."""
    approx = float(value)
    lo, hi = approx, approx
    if Fraction(approx) > value:
        lo = math.nextafter(approx, -math.inf)
    if Fraction(approx) < value:
        hi = math.nextafter(approx, math.inf)
    return lo, hi


def mpf_to_interval(value, ulps=2):
    """Outward-rounded interval for an mpmath real of ~60-digit accuracy."""
    approx = float(value)
    lo, hi = approx, approx
    for _ in range(ulps):
        lo = math.nextafter(lo, -math.inf)
        hi = math.nextafter(hi, math.inf)
    return lo, hi


# ---------------------------------------------------------------------------
# Dirichlet characters of modulus q.
# ---------------------------------------------------------------------------


def factorize(n):
    factors = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors[d] = factors.get(d, 0) + 1
            n //= d
        d += 1
    if n > 1:
        factors[n] = factors.get(n, 0) + 1
    return factors


def primitive_root(pk, p):
    """Primitive root modulo the odd prime power pk = p^e."""
    phi = pk - pk // p
    prime_factors = list(factorize(phi))
    for g in range(2, pk):
        if math.gcd(g, pk) != 1:
            continue
        if all(pow(g, phi // f, pk) != 1 for f in prime_factors):
            return g
    raise RuntimeError(f"no primitive root modulo {pk}")


class CharacterGroup:
    """Multiplicative characters of (Z/qZ)* via CRT cyclic decomposition."""

    def __init__(self, q):
        if q < 3:
            raise ValueError("modulus must be at least 3")
        self.q = q
        self.residues = [a for a in range(1, q) if math.gcd(a, q) == 1]
        self.phi = len(self.residues)
        factors = factorize(q)
        # Cyclic components: (component modulus, generator, order).
        self.components = []
        for p, e in sorted(factors.items()):
            pk = p ** e
            if p == 2:
                if e == 1:
                    continue
                if e == 2:
                    self.components.append((pk, 3, 2))
                else:
                    self.components.append((pk, pk - 1, 2))
                    self.components.append((pk, 5, 2 ** (e - 2)))
            else:
                self.components.append((pk, primitive_root(pk, p), pk - pk // p))
        # Discrete logs of every residue in every component, via
        # baby-step-giant-step per cyclic component.
        tables = []
        for pk, g, order in self.components:
            baby_m = max(1, math.isqrt(order - 1) + 1)
            baby = {}
            value = 1
            for j in range(baby_m):
                baby.setdefault(value, j)
                value = (value * g) % pk
            giant = pow(g, -baby_m, pk)
            tables.append((baby_m, baby, giant))
        self.logs = {}
        for a in self.residues:
            entry = []
            for (pk, g, order), (baby_m, baby, giant) in zip(
                    self.components, tables):
                x = a % pk
                log = None
                for i in range((order // baby_m) + 1):
                    if x in baby:
                        log = (i * baby_m + baby[x]) % order
                        break
                    x = (x * giant) % pk
                if log is None:
                    raise RuntimeError(
                        f"discrete log failed for {a} in component {pk}")
                entry.append(log)
            self.logs[a] = entry
        self.is_prime = len(factors) == 1 and factors.get(q, 0) == 1

    def character_exponents(self):
        """All characters as exponent tuples against the components."""
        exps = [()]
        for _, _, order in self.components:
            exps = [prev + (k,) for prev in exps for k in range(order)]
        return exps

    def char_value_angle(self, exponents, a):
        """chi(a) = e(angle) with angle an exact Fraction of a turn."""
        angle = Fraction(0)
        for (pk, g, order), e, log in zip(
                self.components, exponents, self.logs[a]):
            angle += Fraction(e * log, order)
        return angle % 1

    def conductor(self, exponents):
        q = self.q
        if self.is_prime:
            return 1 if all(e == 0 for e in exponents) else q
        for d in sorted(divisors(q)):
            ok = True
            for a in self.residues:
                if a % d == 1 % d:
                    if self.char_value_angle(exponents, a) != 0:
                        ok = False
                        break
            if ok:
                return d
        return q


def divisors(n):
    result = []
    d = 1
    while d * d <= n:
        if n % d == 0:
            result.append(d)
            if d != n // d:
                result.append(n // d)
        d += 1
    return sorted(result)


# ---------------------------------------------------------------------------
# High-precision reference values (mpmath).
# ---------------------------------------------------------------------------


def char_value_mp(angle):
    return mpmath.expjpi(2 * mpmath.mpf(angle.numerator) / angle.denominator)


def lambda_reference(group, exponents, parity, eps, t):
    """Lambda_chi(t) via mpmath Hurwitz zeta at working precision."""
    q = group.q
    s = mpmath.mpf("0.5") + 1j * mpmath.mpf(t)
    total = mpmath.mpc(0)
    for a in group.residues:
        angle = group.char_value_angle(exponents, a)
        total += char_value_mp(angle) * mpmath.zeta(s, mpmath.mpf(a) / q)
    l_value = mpmath.power(q, -s) * total
    z = (mpmath.mpf("0.5") + parity + 1j * mpmath.mpf(t)) / 2
    factor = (mpmath.power(mpmath.mpf(q) / mpmath.pi, 1j * mpmath.mpf(t) / 2)
              * mpmath.gamma(z) * mpmath.exp(mpmath.pi * mpmath.mpf(t) / 4))
    return eps * factor * l_value


def compute_epsilon(group, exponents, parity):
    """Root-number factor eps with |eps| = 1 making Lambda real-valued."""
    q = group.q
    tau = mpmath.mpc(0)
    for a in group.residues:
        angle = group.char_value_angle(exponents, a)
        tau += char_value_mp(angle) * mpmath.expjpi(2 * mpmath.mpf(a) / q)
    omega = tau / (1j ** parity * mpmath.sqrt(q))
    if abs(abs(omega) - 1) > mpmath.mpf("1e-40"):
        raise RuntimeError("Gauss-sum modulus check failed")
    eps = 1 / mpmath.sqrt(omega)
    # Reality verification at two ordinates.  For very large unit groups the
    # reference evaluation is prohibitively slow on the host; the GPU-side
    # check that every Im Lambda enclosure straddles zero (isolate_zeros)
    # catches a wrong eps at every sample instead.
    if group.phi > 4096:
        return eps
    for t_test in ("0.375", "1.625"):
        value = lambda_reference(group, exponents, parity, eps, t_test)
        if abs(value.imag) > mpmath.mpf("1e-30") * (1 + abs(value)):
            raise RuntimeError(
                f"epsilon reality check failed at t={t_test}: {value}")
    return eps


# ---------------------------------------------------------------------------
# GPU job I/O.
# ---------------------------------------------------------------------------


class GPUJob:
    def __init__(self, group, characters, executable, work_dir, device=0):
        self.group = group
        self.characters = characters  # list of dicts
        self.executable = executable
        self.work_dir = pathlib.Path(work_dir)
        self.device = device
        self.gamma_jg = 8
        self.gamma_shift = 12
        self.calls = 0
        self.gpu_ms = 0.0
        self.term_evals = 0.0

    def run(self, t_values, terms_m, bern_j=10):
        """Evaluate Lambda enclosures for all characters at t_values."""
        group = self.group
        q = group.q
        lnq_pi = mpmath.log(mpmath.mpf(q) / mpmath.pi)
        lnq_pi_lo, lnq_pi_hi = mpf_to_interval(lnq_pi, ulps=2)

        two_j1 = 2 * bern_j + 1
        em_rconst = (4 / mpmath.power(2 * mpmath.pi, two_j1)
                     / (mpmath.mpf("0.5") + 2 * bern_j))
        em_rconst_hi = mpf_to_interval(em_rconst, ulps=2)[1]
        g2 = 2 * self.gamma_jg + 2
        g_rconst = (abs(BERNOULLI[g2]) / (g2 * (g2 - 1))
                    * Fraction(2 ** (self.gamma_jg + 1)))
        g_rconst_hi = fraction_to_interval(g_rconst)[1]

        header = struct.pack(
            "<8s8I4d", INPUT_MAGIC, q, group.phi, len(self.characters),
            len(t_values), terms_m, bern_j, self.gamma_jg, self.gamma_shift,
            lnq_pi_lo, lnq_pi_hi, em_rconst_hi, g_rconst_hi)

        parts = [header]
        parts.append(struct.pack(f"<{group.phi}I", *group.residues))
        parts.append(bytes(c["parity"] for c in self.characters))
        for j in range(1, bern_j + 1):
            c_j = BERNOULLI[2 * j] / factorial(2 * j)
            parts.append(struct.pack("<2d", *fraction_to_interval(c_j)))
        for j in range(1, self.gamma_jg + 1):
            c_j = BERNOULLI[2 * j] / (2 * j * (2 * j - 1))
            parts.append(struct.pack("<2d", *fraction_to_interval(c_j)))
        for c in self.characters:
            for a in group.residues:
                angle = group.char_value_angle(c["exponents"], a)
                value = char_value_mp(angle)
                re = mpf_to_interval(value.real)
                im = mpf_to_interval(value.imag)
                parts.append(struct.pack("<4d", re[0], re[1], im[0], im[1]))
        for c in self.characters:
            re = mpf_to_interval(c["eps"].real)
            im = mpf_to_interval(c["eps"].imag)
            parts.append(struct.pack("<4d", re[0], re[1], im[0], im[1]))
        parts.append(struct.pack(f"<{len(t_values)}d", *t_values))

        in_path = self.work_dir / f"job-{self.calls:04d}.bin"
        out_path = self.work_dir / f"out-{self.calls:04d}.bin"
        in_path.write_bytes(b"".join(parts))
        result = subprocess.run(
            [str(self.executable), str(in_path), str(out_path),
             str(self.device)],
            capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.calls += 1
        self.gpu_ms += report["hurwitz_ms"] + report["lambda_ms"]
        self.term_evals += report["term_evals"]
        self.last_report = report

        blob = out_path.read_bytes()
        magic, = struct.unpack_from("<8s", blob, 0)
        if magic != OUTPUT_MAGIC:
            raise RuntimeError("bad output magic")
        char_count, t_count, summary, _ = struct.unpack_from("<4I", blob, 8)
        if summary != 0:
            raise RuntimeError(f"GPU reported nonfinite status {summary}")
        # The kernel writes rectangles in [t][char] order.
        base = 24
        values = {}
        for i in range(t_count):
            for k in range(char_count):
                offset = base + 32 * (i * char_count + k)
                rect = struct.unpack_from("<4d", blob, offset)
                values.setdefault(k, {})[t_values[i]] = rect
        return values


def pick_terms_m(t_max):
    """Main-sum length for the Euler-Maclaurin truncation at |t| <= t_max."""
    return max(64, int(math.ceil(0.7 * (abs(t_max) + 30.0))))


# ---------------------------------------------------------------------------
# Zero isolation.
# ---------------------------------------------------------------------------


def sign_of(rect):
    re_lo, re_hi, _, _ = rect
    if re_lo > 0.0:
        return 1
    if re_hi < 0.0:
        return -1
    return 0


def check_reality(rect):
    _, _, im_lo, im_hi = rect
    return im_lo <= 0.0 <= im_hi


def isolate_zeros(job, characters, lo, hi, step, max_rounds=40):
    """Per character: resolved sample points, then strict brackets."""
    count = int(math.floor((hi - lo) / step)) + 1
    grid = [lo + i * step for i in range(count)]
    if grid[-1] < hi:
        grid.append(hi)
    terms_m = pick_terms_m(max(abs(lo), abs(hi)))
    values = job.run(grid, terms_m)

    reality_violations = 0
    results = {}
    for k, char in enumerate(characters):
        samples = dict(values[k])
        for rect in samples.values():
            if not check_reality(rect):
                reality_violations += 1
        # Resolve ambiguous samples by local bisection against neighbours.
        points = sorted(samples)
        resolved = [t for t in points if sign_of(samples[t]) != 0]
        ambiguous = [t for t in points if sign_of(samples[t]) == 0]
        rounds = 0
        while ambiguous and rounds < max_rounds:
            rounds += 1
            new_points = []
            for t in ambiguous:
                left = max((p for p in resolved if p < t), default=None)
                right = min((p for p in resolved if p > t), default=None)
                for neighbour in (left, right):
                    if neighbour is None:
                        continue
                    mid = 0.5 * (t + neighbour)
                    if mid not in samples:
                        new_points.append(mid)
            new_points = sorted(set(new_points))
            if not new_points:
                break
            new_values = job.run(new_points, terms_m)
            samples.update(new_values[k])
            points = sorted(samples)
            resolved = [t for t in points if sign_of(samples[t]) != 0]
            ambiguous_left = []
            for t in ambiguous:
                left = max((p for p in resolved if p < t), default=None)
                right = min((p for p in resolved if p > t), default=None)
                if left is None or right is None:
                    ambiguous_left.append(t)
                    continue
                # The ambiguous sample is now bypassed by resolved
                # neighbours; the sign pattern between them tells whether a
                # zero hides here, and the bracket scan below picks it up.
            ambiguous = ambiguous_left
        if ambiguous:
            raise RuntimeError(
                f"character {k}: unresolved ambiguous samples {ambiguous}")

        brackets = []
        last_upper = None
        for left, right in zip(resolved, resolved[1:]):
            s1 = sign_of(samples[left])
            s2 = sign_of(samples[right])
            if s1 == 0 or s2 == 0 or s1 == s2:
                continue
            bracket_left = left
            if last_upper is not None and bracket_left <= last_upper:
                # Split shared endpoints: find a fresh left endpoint strictly
                # between the previous upper endpoint and `right` that still
                # carries the sign of `left`.  Just after `last_upper` the
                # sign is s1, so probes geometrically close to it succeed.
                fresh = None
                span = right - last_upper
                for exponent in range(1, max_rounds):
                    probe = last_upper + span * 0.5 ** exponent
                    if probe <= last_upper or probe >= right:
                        break
                    if probe in samples:
                        if sign_of(samples[probe]) == s1:
                            fresh = probe
                            break
                        continue
                    probe_val = job.run([probe], terms_m)[k][probe]
                    samples[probe] = probe_val
                    if sign_of(probe_val) == s1:
                        fresh = probe
                        break
                if fresh is None:
                    raise RuntimeError(
                        f"character {k}: cannot separate brackets near "
                        f"{right}")
                bracket_left = fresh
            brackets.append({
                "lower": bracket_left,
                "upper": right,
                "lower_value": samples[bracket_left],
                "upper_value": samples[right],
            })
            last_upper = right
        results[k] = {
            "brackets": brackets,
            "samples": samples,
        }
    return results, reality_violations


# ---------------------------------------------------------------------------
# Numeric (non-formal) Turing-style completeness check.
# ---------------------------------------------------------------------------


def phi_main_term(q, parity, t):
    """(1/pi)(Im logGamma((1/2 + a + it)/2) + (t/2) log(q/pi))."""
    z = (mpmath.mpf("0.5") + parity + 1j * mpmath.mpf(t)) / 2
    return float((mpmath.loggamma(z).imag
                  + mpmath.mpf(t) / 2 * mpmath.log(mpmath.mpf(q) / mpmath.pi))
                 / mpmath.pi)


def turing_expectation(q, parity, lo, hi):
    """Main-term expected zero count on [lo, hi] and an S(t) slack using
    Trudgian's constants 2.17618 + 0.0679955 log(q t / 2 pi) (per Platt's
    production code).  Numeric sanity check only, not a formal bound."""
    main = phi_main_term(q, parity, hi) - phi_main_term(q, parity, lo)
    def s_bound(t):
        qt = q * max(abs(t), 1.0) / (2 * math.pi)
        return 2.17618 + 0.0679955 * math.log(max(qt, 1.0))
    return main, s_bound(lo) + s_bound(hi)


# ---------------------------------------------------------------------------
# Certificate emission and CPU verification.
# ---------------------------------------------------------------------------


def rect_to_json(rect):
    return {
        "re_lo": rect[0].hex(), "re_hi": rect[1].hex(),
        "im_lo": rect[2].hex(), "im_hi": rect[3].hex(),
    }


def cross_check(group, char, brackets, samples, sample_stride, precision=60,
                max_points=200):
    """Verify GPU enclosures contain mpmath reference values."""
    mpmath.mp.dps = precision
    if max_points <= 0:
        return 0
    checked = 0
    points = []
    bracket_stride = max(1, len(brackets) // 50)
    for bracket in brackets[::bracket_stride]:
        points.append((bracket["lower"], bracket["lower_value"]))
        points.append((bracket["upper"], bracket["upper_value"]))
    ordered = sorted(samples)
    points.extend((t, samples[t]) for t in ordered[::max(1, sample_stride)])
    if len(points) > max_points:
        stride = (len(points) + max_points - 1) // max_points
        points = points[::stride]
    for t, rect in points:
        reference = lambda_reference(
            group, char["exponents"], char["parity"], char["eps"], repr(t))
        re_ref, im_ref = float(reference.real), float(reference.imag)
        margin = 1e-30
        if not (rect[0] - margin <= re_ref <= rect[1] + margin):
            raise RuntimeError(
                f"cross-check failure at t={t}: re {re_ref} not in "
                f"[{rect[0]}, {rect[1]}]")
        if not (rect[2] - margin <= im_ref <= rect[3] + margin):
            raise RuntimeError(
                f"cross-check failure at t={t}: im {im_ref} not in "
                f"[{rect[2]}, {rect[3]}]")
        checked += 1
    return checked


def verify_certificate(path):
    """CPU recheck of bracket shape, strict signs, and ordering, in exact
    rational arithmetic from the serialized binary64 data."""
    payload = json.loads(pathlib.Path(path).read_text())
    for char in payload["characters"]:
        previous_upper = None
        for bracket in char["brackets"]:
            lower = Fraction(float.fromhex(bracket["lower"]))
            upper = Fraction(float.fromhex(bracket["upper"]))
            lv = bracket["lower_value"]
            uv = bracket["upper_value"]
            lv_lo = Fraction(float.fromhex(lv["re_lo"]))
            lv_hi = Fraction(float.fromhex(lv["re_hi"]))
            uv_lo = Fraction(float.fromhex(uv["re_lo"]))
            uv_hi = Fraction(float.fromhex(uv["re_hi"]))
            if not lower < upper:
                return False, f"bracket order {bracket}"
            if not (lv_lo <= lv_hi and uv_lo <= uv_hi):
                return False, f"malformed interval {bracket}"
            negative_positive = lv_hi < 0 < uv_lo
            positive_negative = uv_hi < 0 < lv_lo
            if not (negative_positive or positive_negative):
                return False, f"no strict sign change {bracket}"
            if previous_upper is not None and not previous_upper < lower:
                return False, f"family overlap at {bracket}"
            previous_upper = upper
        expected = char["bracket_count"]
        if expected != len(char["brackets"]):
            return False, "bracket count mismatch"
    return True, "certificate rechecked"


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def cmd_run(args):
    mpmath.mp.dps = 60
    started = time.time()
    group = CharacterGroup(args.q)
    exponent_list = group.character_exponents()
    characters = []
    for exponents in exponent_list:
        if all(e == 0 for e in exponents):
            continue
        conductor = group.conductor(exponents)
        if conductor != group.q and not args.include_imprimitive:
            continue
        parity_angle = group.char_value_angle(exponents, group.q - 1)
        parity = 0 if parity_angle == 0 else 1
        characters.append({
            "exponents": exponents,
            "conductor": conductor,
            "parity": parity,
        })
        if args.max_characters and len(characters) >= args.max_characters:
            break
    if not characters:
        raise SystemExit("no primitive nontrivial characters for this q")
    for char in characters:
        char["eps"] = compute_epsilon(group, char["exponents"], char["parity"])

    work_dir = pathlib.Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    job = GPUJob(group, characters, args.executable, work_dir, args.device)

    step = 5.0 / 64.0
    results, reality_violations = isolate_zeros(
        job, characters, args.t_lo, args.t_hi, step)
    if reality_violations:
        raise SystemExit(
            f"{reality_violations} samples violated Im Lambda enclosing 0")

    payload = {
        "kind": "sparkinterval_grh_poc_certificate",
        "algorithm": "sparkinterval.grh_lambda_interval_poc.v1",
        "paper": "arXiv:1305.3087v1",
        "q": group.q,
        "phi": group.phi,
        "t_lo": args.t_lo,
        "t_hi": args.t_hi,
        "grid_step": "5/64",
        "terms_m": pick_terms_m(max(abs(args.t_lo), abs(args.t_hi))),
        "gpu": job.last_report["device"],
        "characters": [],
    }
    total_zeros = 0
    for k, char in enumerate(characters):
        brackets = results[k]["brackets"]
        samples = results[k]["samples"]
        checked = cross_check(
            group, char, brackets, samples, args.cross_check_stride,
            max_points=args.max_cross_checks)
        main, slack = turing_expectation(
            group.q, char["parity"], args.t_lo, args.t_hi)
        deviation = abs(len(brackets) - main)
        char_payload = {
            "index": k,
            "exponents": list(char["exponents"]),
            "conductor": char["conductor"],
            "parity": char["parity"],
            "epsilon": {
                "re": mpmath.nstr(char["eps"].real, 30),
                "im": mpmath.nstr(char["eps"].imag, 30),
            },
            "bracket_count": len(brackets),
            "turing_main_term": main,
            "turing_s_slack": slack,
            "turing_deviation": deviation,
            "turing_consistent": bool(deviation <= slack),
            "cross_checked_points": checked,
            "samples_evaluated": len(samples),
            "brackets": [
                {
                    "lower": b["lower"].hex(),
                    "upper": b["upper"].hex(),
                    "lower_value": rect_to_json(b["lower_value"]),
                    "upper_value": rect_to_json(b["upper_value"]),
                }
                for b in brackets
            ],
        }
        payload["characters"].append(char_payload)
        total_zeros += len(brackets)
        print(f"character {k} (exponents {char['exponents']}, parity "
              f"{char['parity']}): {len(brackets)} zeros bracketed, "
              f"Turing main term {main:.3f} (slack {slack:.3f}), "
              f"{checked} enclosures cross-checked", file=sys.stderr)

    payload["total_brackets"] = total_zeros
    payload["gpu_calls"] = job.calls
    payload["gpu_ms"] = job.gpu_ms
    payload["gpu_term_evals"] = job.term_evals
    payload["wall_seconds"] = time.time() - started
    blob = json.dumps(payload, indent=1, sort_keys=True)
    payload_path = work_dir / "grh-certificate.json"
    payload_path.write_text(blob)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    print(json.dumps({
        "certificate": str(payload_path),
        "sha256": digest,
        "q": group.q,
        "characters": len(characters),
        "total_brackets": total_zeros,
        "gpu_ms": job.gpu_ms,
        "gpu_term_evals": job.term_evals,
        "wall_seconds": payload["wall_seconds"],
    }, indent=1))


def cmd_verify(args):
    ok, message = verify_certificate(args.certificate)
    print(json.dumps({"accepted": ok, "detail": message}, indent=1))
    if not ok:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--q", type=int, required=True)
    run_parser.add_argument("--t-lo", type=float, default=-1.0)
    run_parser.add_argument("--t-hi", type=float, required=True)
    run_parser.add_argument("--work-dir", required=True)
    run_parser.add_argument(
        "--executable",
        default="build/grh-dev/sparkinterval-grh-lambda")
    run_parser.add_argument("--device", type=int, default=0)
    run_parser.add_argument("--cross-check-stride", type=int, default=64)
    run_parser.add_argument("--include-imprimitive", action="store_true")
    run_parser.add_argument(
        "--max-characters", type=int, default=0,
        help="benchmark option: only process the first K primitive "
             "characters (0 = all); a full verification must cover all")
    run_parser.add_argument("--max-cross-checks", type=int, default=200)
    run_parser.set_defaults(func=cmd_run)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("certificate")
    verify_parser.set_defaults(func=cmd_verify)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
