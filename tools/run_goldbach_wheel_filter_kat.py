#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build, run, and strictly validate the Goldbach wheel-filter CUDA KAT."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "gpu/platform/h100/h100_tg_goldbach_wheel_filter_kat.cu"
)
RESULT_KIND = "sparkinterval.goldbach-wheel-filter-kat.v1"


class KATError(RuntimeError):
    """The wheel-filter KAT did not satisfy its exact contract."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_result(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise KATError("KAT result must be an object")
    required = {
        "accepted",
        "cofactor_filter_limit",
        "compute_capability",
        "kind",
        "odd_count_per_window",
        "prime_limit",
        "tail_prime_count",
        "warp_parallel_cutoff",
        "warp_prime_count",
        "wheel_modulus",
        "window_count",
        "windows",
        "word_owner_cutoff",
    }
    if set(value) != required:
        raise KATError("KAT result has wrong fields")
    if value["accepted"] is not True or value["kind"] != RESULT_KIND:
        raise KATError("KAT did not report exact acceptance")
    if (
        value["odd_count_per_window"] != 1 << 18
        or value["cofactor_filter_limit"] != 47
        or value["prime_limit"] != 131_071
        or value["warp_parallel_cutoff"] != 32_749
        or value["wheel_modulus"] != 15_015
        or value["word_owner_cutoff"] != 2_039
        or value["window_count"] != 4
    ):
        raise KATError("KAT geometry or constants differ")
    if not isinstance(value["compute_capability"], str) or not re.fullmatch(
        r"[0-9]{1,2}\.[0-9]", value["compute_capability"]
    ):
        raise KATError("compute capability is malformed")
    if (
        not isinstance(value["warp_prime_count"], int)
        or not isinstance(value["tail_prime_count"], int)
        or not 0
        < value["warp_prime_count"]
        < value["tail_prime_count"]
    ):
        raise KATError("prime partition is malformed")
    windows = value["windows"]
    if not isinstance(windows, list) or len(windows) != 4:
        raise KATError("KAT must contain four windows")
    for index, row in enumerate(windows):
        if not isinstance(row, dict) or set(row) != {
            "fnv1a64",
            "q_high",
            "q_low",
            "set_bits",
        }:
            raise KATError(f"window {index} has wrong fields")
        if (
            not isinstance(row["q_low"], str)
            or not isinstance(row["q_high"], str)
            or not row["q_low"].isdigit()
            or not row["q_high"].isdigit()
            or int(row["q_low"]) % 2 != 1
            or int(row["q_high"]) - int(row["q_low"])
            != 2 * ((1 << 18) - 1)
        ):
            raise KATError(f"window {index} has wrong geometry")
        if not isinstance(row["fnv1a64"], str) or not re.fullmatch(
            r"[0-9a-f]{16}", row["fnv1a64"]
        ):
            raise KATError(f"window {index} digest is malformed")
        if (
            not isinstance(row["set_bits"], int)
            or not 0 <= row["set_bits"] <= 1 << 18
        ):
            raise KATError(f"window {index} bit count is malformed")
    if int(windows[-1]["q_high"]) != (1 << 64) - 1:
        raise KATError("last KAT window does not end at UINT64_MAX")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc")
    )
    parser.add_argument("--arch", default="native")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    if not re.fullmatch(r"(?:native|sm_[0-9]{2,3})", arguments.arch):
        print("architecture must be native or sm_NN", file=sys.stderr)
        return 2
    try:
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-wheel-filter-kat-"
        ) as temporary:
            executable = Path(temporary) / "kat"
            build_argv = [
                str(arguments.nvcc),
                "-O3",
                "-std=c++20",
                f"-arch={arguments.arch}",
                str(SOURCE),
                "-o",
                str(executable),
            ]
            built = subprocess.run(
                build_argv,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=arguments.timeout,
                check=False,
            )
            if built.returncode != 0:
                raise KATError(
                    "KAT compilation failed: "
                    + (built.stderr.strip() or built.stdout.strip())
                )
            ran = subprocess.run(
                [str(executable)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=arguments.timeout,
                check=False,
            )
            if ran.returncode != 0:
                raise KATError(
                    "KAT execution failed: "
                    + (ran.stderr.strip() or ran.stdout.strip())
                )
            try:
                result = validate_result(json.loads(ran.stdout))
            except json.JSONDecodeError as error:
                raise KATError("KAT stdout is not one JSON value") from error
            report = {
                "accepted": True,
                "arch": arguments.arch,
                "classification": (
                    "bounded-regression-not-production-evidence"
                ),
                "executable_sha256": sha256(executable),
                "kind": (
                    "sparkinterval.goldbach-wheel-filter-kat-report.v1"
                ),
                "nvcc_sha256": sha256(arguments.nvcc),
                "result": result,
                "source_sha256": sha256(SOURCE),
            }
        encoded = (
            json.dumps(report, indent=2, sort_keys=True) + "\n"
            if arguments.pretty
            else json.dumps(
                report, separators=(",", ":"), sort_keys=True
            )
            + "\n"
        )
        if arguments.out is not None:
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            arguments.out.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
    except (KATError, OSError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
