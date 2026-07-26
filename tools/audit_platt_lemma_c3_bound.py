#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""High-precision diagnostic for Platt's published Lemma C.3 bound.

This deliberately emits ``proof_status = diagnostic_only``.  mpmath is useful
for catching symbol-map and exponent mistakes, but it is not directed interval
arithmetic and cannot discharge either the analytic lemma or its uniform
parameter inequality in Lean.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
import math
from typing import Any

import mpmath


SOURCE_A = Fraction(512, 21)
SOURCE_H = Fraction(13, 64)
SOURCE_NS = 70
EXACT_BUDGET = Fraction(245, 10**42)
SOURCE_HEIGHT = 3_000_175_332_800
PARAMETER_MAXIMUM = 3_010_000_000_000


def _mp(value: int | Fraction | str) -> mpmath.mpf:
    if isinstance(value, Fraction):
        return mpmath.mpf(value.numerator) / value.denominator
    return mpmath.mpf(value)


def published_bound(t0_value: int | str) -> dict[str, mpmath.mpf]:
    """Evaluate the corrected displayed C.3 right-hand side."""

    t0 = _mp(t0_value)
    A = _mp(SOURCE_A)
    H = _mp(SOURCE_H)
    Ns = _mp(SOURCE_NS)
    beta = mpmath.mpf(1) / 6 + mpmath.log(mpmath.log(t0)) / mpmath.log(t0)
    q = Ns**2 / (2 * A**2 * H**2)
    x = (t0 + Ns / A) ** beta * mpmath.exp(-q)
    y = (
        2 ** ((2 * beta - 1) / 2)
        * t0**beta
        * A
        * H
        * mpmath.gammainc(mpmath.mpf(1) / 2, q, mpmath.inf)
    )
    z_argument = t0**2 / (2 * H**2)
    z = (
        2 ** ((3 * beta - 1) / 2)
        * A
        * H ** (beta + 1)
        * mpmath.gammainc((beta + 1) / 2, z_argument, mpmath.inf)
    )
    bound = 6 * A / (mpmath.pi * Ns) * (x + y + z)
    return {"beta": beta, "q": q, "X": x, "Y": y, "Z": z, "bound": bound}


def report(targets: list[int], digits: int) -> dict[str, Any]:
    mpmath.mp.dps = digits
    budget = _mp(EXACT_BUDGET)
    rows = []
    for target in targets:
        values = published_bound(target)
        rows.append(
            {
                "t0": target,
                **{name: mpmath.nstr(value, digits) for name, value in values.items()},
                "ratio_to_exact_budget": mpmath.nstr(values["bound"] / budget, digits),
            }
        )
    source_float = float("2.45e-40")
    upward_float = math.nextafter(source_float, math.inf)
    source_fraction = Fraction.from_float(source_float)
    upward_fraction = Fraction.from_float(upward_float)
    return {
        "kind": "sparkinterval.platt_lemma_c3_mpmath_diagnostic.v1",
        "proof_status": "diagnostic_only",
        "warning": (
            "mpmath is not directed interval arithmetic; these values do not "
            "prove the analytic lemma or a uniform range bound"
        ),
        "precision_decimal_digits": digits,
        "parameters": {
            "A": f"{SOURCE_A.numerator}/{SOURCE_A.denominator}",
            "H": f"{SOURCE_H.numerator}/{SOURCE_H.denominator}",
            "Ns": SOURCE_NS,
            "exact_budget": f"{EXACT_BUDGET.numerator}/{EXACT_BUDGET.denominator}",
        },
        "binary64_audit": {
            "source_decimal_hex": source_float.hex(),
            "source_decimal_exact_fraction":
                f"{source_fraction.numerator}/{source_fraction.denominator}",
            "source_decimal_at_least_exact_budget": source_fraction >= EXACT_BUDGET,
            "patched_upward_hex": upward_float.hex(),
            "patched_upward_exact_fraction":
                f"{upward_fraction.numerator}/{upward_fraction.denominator}",
            "patched_upward_at_least_exact_budget": upward_fraction >= EXACT_BUDGET,
        },
        "targets": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        action="append",
        type=int,
        dest="targets",
        help="positive interpolation target; may be repeated",
    )
    parser.add_argument("--digits", type=int, default=80)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    targets = args.targets or [10_000_000_000, SOURCE_HEIGHT, PARAMETER_MAXIMUM]
    if args.digits < 40:
        parser.error("--digits must be at least 40")
    if any(target <= math.ceil(math.e**math.e) for target in targets):
        parser.error("every --target must exceed exp(e)")
    print(json.dumps(report(targets, args.digits), sort_keys=True,
        indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
