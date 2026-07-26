#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the finite Eq. (13.15) cell replay and give a linear estimator.

This command intentionally benchmarks only the bounded-w rational reference.
It never emits a registered result, deployment pin, realization, receipt, or
production-success claim.
"""

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

from tg_verifier.eq1315_coupled_cap import (  # noqa: E402
    EvalConfig,
    capability_report,
    exact_totient_ratio_upper,
    geometric_panels,
    global_u_domain,
    issue_truncated_certificate,
    make_cell_box,
    verify_truncated_certificate,
)
from tg_verifier.prop1224_directed import RationalInterval  # noqa: E402


def _representative_boxes(config: EvalConfig):
    domain = global_u_domain(config)
    width = Fraction(1, 1 << 50)
    lower_u = RationalInterval(domain.lower, domain.lower + width)
    upper_u = RationalInterval(domain.upper - width, domain.upper)
    cases = (
        (lower_u, Fraction(0), Fraction(0), 510_510, "even"),
        (lower_u, Fraction(1, 2), Fraction(1, 2) + Fraction(1, 1 << 20), 510_511, "odd"),
        (lower_u, Fraction(63, 64), Fraction(1), 2_000_000, "even"),
        (upper_u, Fraction(63, 64), Fraction(1), 20_000_001, "odd"),
    )
    return tuple(
        make_cell_box(
            u=u,
            t=RationalInterval(t_lower, t_upper),
            q_lower=q,
            q_upper=q,
            parity=parity,
            config=config,
        )
        for u, t_lower, t_upper, q, parity in cases
    )


def benchmark(args: argparse.Namespace) -> dict[str, object]:
    config = EvalConfig(bits=args.bits, terms=args.terms)
    config.validate()
    boxes = _representative_boxes(config)
    selected = tuple(boxes[index % len(boxes)] for index in range(args.cells))
    panel_total = 0
    crossing_total = 0
    bounded_passes = 0

    started = time.perf_counter()
    for box in selected:
        panels = geometric_panels(
            box,
            stop=Fraction(args.stop),
            subdivisions=args.subdivisions,
        )
        certificate = issue_truncated_certificate(
            box, panels, config=config
        )
        result = verify_truncated_certificate(certificate)
        panel_total += result.panel_count
        crossing_total += result.selector_crossing_panels
        bounded_passes += int(result.bounded_w_inequality_holds)
    elapsed = time.perf_counter() - started

    cells_per_second = len(selected) / elapsed
    panels_per_second = panel_total / elapsed
    full_cells = (
        args.u_cells * args.v_cells * args.t_cells * 2
    )
    average_panels = panel_total / len(selected)
    full_panel_evaluations = int(round(full_cells * average_panels))
    projected_seconds = full_cells / cells_per_second

    totient_started = time.perf_counter()
    totient_stop = args.totient_start + args.totient_rows - 1
    exact_totient_ratio_upper(
        args.totient_start, totient_stop, "even"
    )
    exact_totient_ratio_upper(
        args.totient_start, totient_stop, "odd"
    )
    totient_elapsed = time.perf_counter() - totient_started
    totient_rows_per_second = args.totient_rows / totient_elapsed
    q_upper_safe = capability_report(config)["q_upper_safe"]
    full_totient_rows = q_upper_safe - 150_000

    report: dict[str, object] = {
        "kind": "sparkinterval.tg.eq1315-coupled-cap.benchmark.v1",
        "scope": "finite-w-directed-rational-reference-only",
        "production_accepted": False,
        "config": {"bits": args.bits, "terms": args.terms},
        "sample": {
            "cells": len(selected),
            "panels": panel_total,
            "stop_w": args.stop,
            "subdivisions_per_anchor_span": args.subdivisions,
            "elapsed_seconds": elapsed,
            "cells_per_second": cells_per_second,
            "panel_evaluations_per_second": panels_per_second,
            "selector_crossing_panels": crossing_total,
            "bounded_w_inequality_passes": bounded_passes,
        },
        "illustrative_full_grid": {
            "u_cells": args.u_cells,
            "v_cells": args.v_cells,
            "t_cells": args.t_cells,
            "parity_lanes": 2,
            "cells": full_cells,
            "estimated_panel_evaluations": full_panel_evaluations,
            "reference_python_single_core_hours": projected_seconds / 3600,
            "warning": (
                "linear projection of this Fraction-based reference only; "
                "adaptive refinement and the missing tail witness can change "
                "the final grid"
            ),
        },
        "totient_prepass": {
            "integer_q_upper_safe": q_upper_safe,
            "strategy": (
                "one exact segmented q/phi pass cached by v block and shared "
                "across u, t, and parity cell evaluation"
            ),
            "sample_q_lower": args.totient_start,
            "sample_q_upper": totient_stop,
            "sample_rows": args.totient_rows,
            "sample_elapsed_seconds": totient_elapsed,
            "sample_rows_per_second": totient_rows_per_second,
            "full_safe_roster_rows": full_totient_rows,
            "reference_python_single_core_seconds": (
                full_totient_rows / totient_rows_per_second
            ),
            "warning": (
                "linear segmented-phi projection only; cell partitioning "
                "and cache behavior determine the realized prepass cost"
            ),
        },
        "accelerator_projection": {
            "h100_seconds": None,
            "cpu_seconds": None,
            "reason": (
                "no compiled interval-cell kernel or device measurement exists; "
                "the Python rate is not used as an invented H100 multiplier"
            ),
        },
        "blocking_soundness_boundaries": [
            "reviewed infinite Gaussian-tail witness around the remote log singularity",
            "Lean realization of the odd-parity theorem-level upper model",
            "complete adaptive (u,v,t) coverage artifact",
        ],
    }
    if args.assumed_cells_per_second is not None:
        report["explicit_throughput_scenario"] = {
            "assumed_cells_per_second": args.assumed_cells_per_second,
            "estimated_seconds": full_cells / args.assumed_cells_per_second,
            "user_supplied_not_measured": True,
        }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells", type=int, default=4)
    parser.add_argument("--bits", type=int, default=144)
    parser.add_argument("--terms", type=int, default=32)
    parser.add_argument("--stop", type=int, default=2)
    parser.add_argument("--subdivisions", type=int, default=1)
    parser.add_argument("--u-cells", type=int, default=64)
    parser.add_argument("--v-cells", type=int, default=512)
    parser.add_argument("--t-cells", type=int, default=64)
    parser.add_argument("--totient-start", type=int, default=100_000_000)
    parser.add_argument("--totient-rows", type=int, default=100_000)
    parser.add_argument("--assumed-cells-per-second", type=float)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    for field in (
        "cells",
        "bits",
        "terms",
        "stop",
        "subdivisions",
        "u_cells",
        "v_cells",
        "t_cells",
        "totient_start",
        "totient_rows",
    ):
        if getattr(args, field) <= 0:
            parser.error(f"--{field.replace('_', '-')} must be positive")
    if args.totient_rows > 1_000_000:
        parser.error("--totient-rows must not exceed 1000000")
    if (
        args.assumed_cells_per_second is not None
        and args.assumed_cells_per_second <= 0
    ):
        parser.error("--assumed-cells-per-second must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = benchmark(args)
    print(
        json.dumps(
            report,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
