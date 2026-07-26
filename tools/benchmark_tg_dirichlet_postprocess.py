#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark separately the Dirichlet ordinary, exception, and Turing paths."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tg_verifier.dirichlet_postprocess as post  # noqa: E402
from tools import tg_dirichlet_flint_backend as backend  # noqa: E402


def _interval(value: int) -> dict[str, object]:
    return {
        "lower": post.fraction_json(Fraction(value)),
        "upper": post.fraction_json(Fraction(value)),
    }


def _turing_request() -> dict[str, object]:
    character = backend.dirichlet_char(3, 2)
    configuration = backend.configuration()
    t0 = Fraction(60)
    h = Fraction(100)
    stop = t0 + h
    step = Fraction(5, 64)
    brackets: list[dict[str, object]] = []
    previous = t0
    previous_sign = backend._hardy_sign(character, previous, configuration)[0]
    point = t0 + step
    while True:
        current = min(point, stop)
        sign = backend._hardy_sign(character, current, configuration)[0]
        if sign != previous_sign:
            brackets.append(
                {
                    "lower": post.fraction_json(previous),
                    "upper": post.fraction_json(current),
                    "multiplicity": 1,
                }
            )
        previous = current
        previous_sign = sign
        if current == stop:
            break
        point += step
    return {
        "kind": post.TURING_SCHEMA,
        "q": 3,
        "conrey_number": 2,
        "conjugate_conrey_number": 2,
        "parity": 1,
        "t0": post.fraction_json(t0),
        "h": post.fraction_json(h),
        "endpoints_zero_free": True,
        "window_bracket_multiplicity_lower_bounds_certified": True,
        "negative_window_reflected_to_conjugate_certified": True,
        "chi_window_zeros": brackets,
        "conjugate_window_zeros": brackets,
        "isolated_count_below_t0": 44,
        "isolated_below_t0_certified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--half-samples", type=int, default=4096)
    parser.add_argument("--turing-repeats", type=int, default=20)
    parser.add_argument("--precision", type=int, default=128)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        post.require_flint()
        if args.half_samples < 16 or args.turing_repeats < 1 or args.precision < 128:
            raise post.DirichletPostprocessError("benchmark parameters are too small")
        N = args.half_samples
        center_index = 1280
        samples = [
            {"index": index, "completed_value": _interval(1)}
            for index in range(center_index - N + 1, center_index + N + 1)
        ]
        ws_request = {
            "kind": post.UPSAMPLE_SCHEMA,
            "q": 400_000,
            "parity": 1,
            "bandwidth": post.fraction_json(Fraction(32, 5)),
            "gaussian_h": post.fraction_json(Fraction(100)),
            "target_ordinate": post.fraction_json(Fraction(10001, 100)),
            "truncation_index": N,
            "lemma_6_7_large_enough_t0_obligation_discharged": False,
            "samples": samples,
        }
        started = time.perf_counter()
        post.whittaker_shannon(ws_request, precision=args.precision)
        ws_seconds = time.perf_counter() - started

        # Exception oracle: raw completed Hardy Z, deliberately separate from
        # the ordinary interval-value reconstruction.
        character = backend.dirichlet_char(5, 2)
        configuration = backend.configuration()
        exception_repeats = 100
        started = time.perf_counter()
        for index in range(exception_repeats):
            backend._hardy_sign(
                character, Fraction(5, 4) + Fraction(index, 1024), configuration
            )
        exception_seconds = time.perf_counter() - started

        turing_request = _turing_request()
        started = time.perf_counter()
        for _ in range(args.turing_repeats):
            post.paired_turing(turing_request, precision=args.precision)
        turing_seconds = time.perf_counter() - started
        report = {
            "kind": "sparkinterval.tg.dirichlet_postprocess.benchmark.v1",
            "production_ready": False,
            "full_source_run": False,
            "precision_bits": args.precision,
            "ordinary_upsampling": {
                "work_unit": "finite completed-value interval",
                "work_units": len(samples),
                "elapsed_seconds": ws_seconds,
                "work_units_per_second": len(samples) / ws_seconds,
                "synthetic_exact_sample_intervals": True,
            },
            "exception_path": {
                "work_unit": "direct FLINT Hardy-Z sign evaluation",
                "work_units": exception_repeats,
                "elapsed_seconds": exception_seconds,
                "work_units_per_second": exception_repeats / exception_seconds,
            },
            "turing_path": {
                "work_unit": "conjugate-paired Turing window arithmetic closure",
                "work_units": args.turing_repeats,
                "window_zero_brackets_per_repeat": len(
                    turing_request["chi_window_zeros"]
                )
                + len(turing_request["conjugate_window_zeros"]),
                "elapsed_seconds": turing_seconds,
                "work_units_per_second": args.turing_repeats / turing_seconds,
            },
            "warning": (
                "rates exclude the all-character interval FFT, source interval "
                "I/O, parameter optimization, attestation, and a full campaign"
            ),
        }
        print(json.dumps(report, sort_keys=True, indent=2 if args.pretty else None))
        return 0
    except (post.DirichletPostprocessError, backend.FlintReferenceError) as error:
        print(f"benchmark_tg_dirichlet_postprocess: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
