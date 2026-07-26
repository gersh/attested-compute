#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Offline checks for H100-native build artifacts and fail-closed CLIs.

The test intentionally invokes only argument paths that return before CUDA
device discovery. It therefore validates build/target wiring on a host with no
H100 while making no execution or attestation claim.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def require_success(command: list[str], expected_stdout: tuple[str, ...]) -> None:
    completed = run(command)
    if completed.returncode != 0:
        raise AssertionError(
            f"{command!r} returned {completed.returncode}: {completed.stderr.strip()}"
        )
    for text in expected_stdout:
        if text not in completed.stdout:
            raise AssertionError(f"{command!r} stdout is missing {text!r}")


def require_failure(
    command: list[str], expected_code: int, expected_stderr: str
) -> None:
    completed = run(command)
    if completed.returncode != expected_code:
        raise AssertionError(
            f"{command!r} returned {completed.returncode}, expected {expected_code}; "
            f"stderr={completed.stderr.strip()!r}"
        )
    if expected_stderr not in completed.stderr:
        raise AssertionError(
            f"{command!r} stderr is missing {expected_stderr!r}: "
            f"{completed.stderr.strip()!r}"
        )


def require_sm90(cuobjdump: Path, artifact: Path) -> None:
    if not artifact.is_file():
        raise AssertionError(f"missing H100 build artifact: {artifact}")
    completed = run([str(cuobjdump), "--list-elf", str(artifact)])
    if completed.returncode != 0:
        raise AssertionError(
            f"cuobjdump rejected {artifact}: {completed.stderr.strip()}"
        )
    if re.search(r"\.sm_90\.cubin(?:\s|$)", completed.stdout) is None:
        raise AssertionError(
            f"{artifact} does not contain a listed sm_90 device image: "
            f"{completed.stdout.strip()!r}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--primitive", type=Path, required=True)
    parser.add_argument("--expression", type=Path, required=True)
    parser.add_argument("--grh-lambda", type=Path, required=True)
    parser.add_argument("--factor-support", type=Path, required=True)
    parser.add_argument("--r2star-chunk", type=Path, required=True)
    parser.add_argument("--mobius-segment", type=Path, required=True)
    parser.add_argument("--mobius-persistent", type=Path, required=True)
    parser.add_argument("--probe-cubin", type=Path, required=True)
    parser.add_argument("--cuobjdump", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for executable in (
        args.probe,
        args.primitive,
        args.expression,
        args.grh_lambda,
        args.factor_support,
        args.r2star_chunk,
        args.mobius_segment,
        args.mobius_persistent,
    ):
        if not executable.is_file():
            raise AssertionError(f"missing H100 executable: {executable}")

    require_success([str(args.probe), "--help"], ("usage:", "H100"))
    require_success(
        [str(args.primitive), "--help"],
        ("sparkinterval-h100-interval-batch", "H100", "overrides are disabled"),
    )
    require_success(
        [str(args.expression), "--help"],
        ("sparkinterval-h100-expression-batch", "H100", "overrides are disabled"),
    )
    require_failure(
        [str(args.grh_lambda)],
        1,
        "usage:",
    )
    require_success(
        [str(args.factor_support), "--help"],
        (
            "sparkinterval-h100-tg-r2star-factor-support",
            "H100",
            "distinct-prime-factor support segment",
        ),
    )
    require_success(
        [str(args.r2star_chunk), "--help"],
        (
            "sparkinterval-h100-tg-r2star-chunk",
            "H100",
            "exact rational host arithmetic",
        ),
    )
    require_success(
        [str(args.mobius_segment), "--help"],
        (
            "sparkinterval-h100-tg-mobius-segment",
            "H100",
            "Moebius/squarefree state transition",
        ),
    )
    require_success(
        [str(args.mobius_persistent), "--help"],
        (
            "sparkinterval-h100-tg-mobius-persistent",
            "nvidia-h100-sm90",
            "not attestation",
        ),
    )

    for executable in (
        args.primitive,
        args.expression,
        args.factor_support,
        args.r2star_chunk,
        args.mobius_segment,
    ):
        require_failure(
            [str(executable), "--allow-other-device"],
            4,
            "--allow-other-device is disabled by the H100 runner",
        )
        require_failure(
            [str(executable), "--device", "not-a-device"],
            2,
            "--device must be a nonnegative integer",
        )
        require_failure(
            [str(executable), "--unknown-option"],
            2,
            "unknown argument: --unknown-option",
        )

    require_failure(
        [str(args.probe), "--unknown-option"],
        64,
        "unknown or incomplete argument: --unknown-option",
    )
    require_failure(
        [str(args.mobius_persistent), "--allow-other-device"],
        4,
        "--allow-other-device is disabled by the H100 runner",
    )
    require_failure(
        [str(args.mobius_persistent)],
        4,
        "requires --require-device-class nvidia-h100-sm90",
    )
    require_failure(
        [
            str(args.mobius_persistent),
            "--require-device-class",
            "gb10",
        ],
        4,
        "must be exactly nvidia-h100-sm90",
    )
    require_failure(
        [
            str(args.mobius_persistent),
            "--require-device-class",
            "nvidia-h100-sm90",
            "--device",
            "not-a-device",
        ],
        2,
        "--device must be a nonnegative integer",
    )

    require_sm90(args.cuobjdump, args.probe_cubin)
    require_sm90(args.cuobjdump, args.primitive)
    require_sm90(args.cuobjdump, args.expression)
    require_sm90(args.cuobjdump, args.grh_lambda)
    require_sm90(args.cuobjdump, args.factor_support)
    require_sm90(args.cuobjdump, args.mobius_segment)
    require_sm90(args.cuobjdump, args.mobius_persistent)
    require_sm90(args.cuobjdump, args.r2star_chunk)
    print("H100 native build and fail-closed CLI checks passed without GPU execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
