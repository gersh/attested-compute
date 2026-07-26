#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Package the optimized Goldbach candidate for bounded Azure H100 timing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.azure_h100_goldbach_candidate_calibration import (  # noqa: E402
    GoldbachCalibrationMaterializationError,
    materialize_calibration_job,
)
from tg_verifier.goldbach_optimized_calibration_contract import (  # noqa: E402
    DEFAULT_SAMPLE_EVEN_LIMIT,
    DEFAULT_SAMPLE_EVEN_START,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("candidate_root", type=Path)
    result.add_argument("destination", type=Path)
    result.add_argument("--python", type=Path, required=True)
    result.add_argument("--runner-policy", type=Path, required=True)
    result.add_argument("--nvidia-policy", type=Path, required=True)
    result.add_argument(
        "--target-profile",
        type=Path,
        default=(
            ROOT / "profiles/targets/azure_ncc40ads_h100_v5.json"
        ),
    )
    result.add_argument(
        "--trust-profile",
        type=Path,
        default=(
            ROOT
            / "profiles/trust/"
            "azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json"
        ),
    )
    result.add_argument("--gpu-verifier", choices=("local", "remote"), default="remote")
    result.add_argument(
        "--nras-url", default="https://nras.attestation.nvidia.com"
    )
    result.add_argument(
        "--even-start", type=int, default=DEFAULT_SAMPLE_EVEN_START
    )
    result.add_argument(
        "--even-limit", type=int, default=DEFAULT_SAMPLE_EVEN_LIMIT
    )
    result.add_argument("--warmups", type=int, default=1)
    result.add_argument("--repetitions", type=int, default=5)
    result.add_argument("--per-run-timeout", type=int, default=3600)
    result.add_argument(
        "--allow-non-x86-test-candidate",
        action="store_true",
        help="test-only: package a non-Azure-host executable",
    )
    result.add_argument("--pretty", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        value = materialize_calibration_job(
            arguments.candidate_root,
            arguments.destination,
            python_executable=arguments.python,
            runner_policy=arguments.runner_policy,
            nvidia_policy=arguments.nvidia_policy,
            target_profile=arguments.target_profile,
            trust_profile=arguments.trust_profile,
            gpu_verifier=arguments.gpu_verifier,
            nras_url=arguments.nras_url,
            even_start=arguments.even_start,
            even_limit=arguments.even_limit,
            warmups=arguments.warmups,
            repetitions=arguments.repetitions,
            per_run_timeout=arguments.per_run_timeout,
            require_x86_64_candidate=not arguments.allow_non_x86_test_candidate,
        )
        print(
            json.dumps(
                value,
                indent=2 if arguments.pretty else None,
                separators=None if arguments.pretty else (",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except (
        GoldbachCalibrationMaterializationError,
        OSError,
        ValueError,
    ) as error:
        print(f"Goldbach H100 calibration packaging failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
