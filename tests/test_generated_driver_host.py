#!/usr/bin/env python3
"""Host-only checks for generated-driver reports and pre-CUDA rejection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile


def run_rejection(driver: Path, arguments: list[str], expected: str) -> None:
    completed = subprocess.run(
        [str(driver), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 2:
        raise AssertionError(
            f"expected host-side exit 2, got {completed.returncode}: "
            f"{completed.stderr}"
        )
    if expected not in completed.stderr:
        raise AssertionError(
            f"expected {expected!r} in driver error: {completed.stderr!r}"
        )
    if "CUDA" in completed.stderr and "SHA-256" not in completed.stderr:
        raise AssertionError(f"driver unexpectedly reached CUDA: {completed.stderr!r}")


def check_report(report_fixture: Path) -> None:
    completed = subprocess.run(
        [str(report_fixture), "--emit-json"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    if report["kind"] != "sparkinterval_generated_driver_run":
        raise AssertionError("wrong generated-driver report kind")
    if report["challenge_nonce"] != "ab" * 32:
        raise AssertionError("challenge nonce was not preserved")
    for field, expected in {
        "input_payload_size_bytes": 32,
        "module_size_bytes": 128,
        "output_file_size_bytes": 48,
        "row_count": 1,
    }.items():
        if type(report[field]) is not int or report[field] != expected:
            raise AssertionError(f"{field} is not the expected JSON integer")
    if report["device_name"] != 'DGX "Spark"\nGPU\\0':
        raise AssertionError("JSON string escaping did not round-trip")


def check_pre_cuda_rejections(driver: Path) -> None:
    with tempfile.TemporaryDirectory() as raw_directory:
        directory = Path(raw_directory)
        cubin = directory / "kernel.cubin"
        rows = directory / "rows.bin"
        output = directory / "results.bin"
        cubin_bytes = b"\x7fELFhost-only-fixture"
        row_payload = struct.pack("<QQ", 0, 0)
        rows_bytes = b"SIG64I01" + struct.pack("<IIQ", 1, 1, 1) + row_payload
        cubin.write_bytes(cubin_bytes)
        rows.write_bytes(rows_bytes)
        base = [
            "--cubin",
            str(cubin),
            "--input",
            str(rows),
            "--output",
            str(output),
        ]

        run_rejection(
            driver,
            base,
            "--cubin acceptance requires --expected-module-sha256 and "
            "--expected-input-sha256",
        )
        run_rejection(
            driver,
            [*base, "--expected-module-sha256", "ABC"],
            "expected module SHA-256 must be 64 lowercase hex characters",
        )
        run_rejection(
            driver,
            [
                *base,
                "--expected-module-sha256",
                "0" * 64,
                "--expected-input-sha256",
                hashlib.sha256(row_payload).hexdigest(),
            ],
            "in-memory CUDA module SHA-256 does not match expected value",
        )
        run_rejection(
            driver,
            [
                *base,
                "--expected-module-sha256",
                hashlib.sha256(cubin_bytes).hexdigest(),
                "--expected-input-sha256",
                "0" * 64,
            ],
            "in-memory GPU input payload SHA-256 does not match expected value",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-fixture", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    arguments = parser.parse_args()
    check_report(arguments.report_fixture)
    check_pre_cuda_rejections(arguments.driver)


if __name__ == "__main__":
    main()
