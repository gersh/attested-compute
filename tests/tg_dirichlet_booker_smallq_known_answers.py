#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Arb/CUDA known answers for Platt's q=3,4,5 small-q formulas."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_booker_smallq import (  # noqa: E402
    inspect_gpu_proposal,
    known_answer_case,
    transform_parameters,
    write_gpu_proposal_input,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("gpu_executable", type=Path)
    result.add_argument(
        "--mpfr-auditor",
        type=Path,
        help="optional independent 256-bit arithmetic auditor",
    )
    result.add_argument("--iterations", type=int, default=10)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.iterations <= 0:
        raise ValueError("iterations must be positive")
    cases = ((3, 2), (4, 3), (5, 2), (5, 3), (5, 4))
    reports = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for q, conrey in cases:
            arb_result = known_answer_case(
                root / "arb",
                q=q,
                conrey_number=conrey,
                transform_length=128,
                sample_stop=5,
            )
            parameters = transform_parameters(
                q,
                height=Fraction(1),
                guard_height=Fraction(4),
                transform_length=128,
                eta=Fraction(0),
            )
            input_path = root / f"q{q}-chi{conrey}.input.bin"
            output_path = root / f"q{q}-chi{conrey}.output.bin"
            write_gpu_proposal_input(
                input_path,
                q=q,
                conrey_number=conrey,
                parameters=parameters,
                frequency_start=0,
                frequency_stop=128,
            )
            completed = subprocess.run(
                [str(args.gpu_executable), str(input_path), str(output_path), str(args.iterations)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            gpu_stdout = json.loads(completed.stdout)
            mpfr_audit = None
            if args.mpfr_auditor is not None:
                audited = subprocess.run(
                    [str(args.mpfr_auditor), str(input_path), str(output_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                mpfr_audit = json.loads(audited.stdout)
            comparison = inspect_gpu_proposal(
                input_path,
                output_path,
                conrey_number=conrey,
                parameters=parameters,
            )
            if comparison["maximum_absolute_midpoint_error"] > 2e-13:
                raise RuntimeError("CUDA midpoint differs materially from Arb")
            if not arb_result["samples"]["direct_flint_comparison_passed"]:
                raise RuntimeError("DFT samples do not contain direct FLINT values")
            reports.append(
                {
                    "q": q,
                    "conrey_number": conrey,
                    "gpu": gpu_stdout,
                    "mpfr_audit": mpfr_audit,
                    "comparison": comparison,
                    "completed_samples": arb_result["samples"]["sample_count"],
                }
            )
    print(
        json.dumps(
            {
                "kind": "sparkinterval.tg.dirichlet_booker_smallq.gpu_kat.v1",
                "cases": reports,
                "passed": True,
                "external_atom_discharged": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
