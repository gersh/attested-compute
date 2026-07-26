#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded maximum-order CUDA qualification for the all-character transform."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    COMPLEX_INTERVAL,
    OUTPUT_HEADER,
    read_output_header,
)


ALGORITHM = (
    "platt-dirichlet-allchars-max-order-impulse-qualification-v1"
)
Q = 399_989
ORDER = 399_988
CONVOLUTION = 1 << 20
LOG_CONVOLUTION = 20
BUTTERFLIES = 3 * (CONVOLUTION // 2) * LOG_CONVOLUTION
REQUIRED_DEVICE_BYTES = (6 * CONVOLUTION + 3 * ORDER) * COMPLEX_INTERVAL.size
DEVICE_HEADROOM_BYTES = 256 * 1024 * 1024
MAXIMUM_COMPONENT_WIDTH = math.ldexp(1.0, -16)
REPORT_FIELDS = {
    "algorithm",
    "q",
    "order",
    "convolution",
    "log_convolution",
    "value_count",
    "checked_output_count",
    "radix2_butterflies",
    "device",
    "device_compute_major",
    "device_compute_minor",
    "required_device_bytes",
    "free_device_bytes_before",
    "total_device_bytes",
    "device_headroom_bytes",
    "maximum_seconds",
    "preparation_nanoseconds",
    "transform_nanoseconds",
    "validation_nanoseconds",
    "compute_validation_nanoseconds",
    "maximum_component_width",
    "maximum_component_width_ceiling",
    "output_payload_sha256",
}


class QualificationError(RuntimeError):
    """The maximum-order qualification failed closed."""


def _integer(report: dict[str, object], name: str) -> int:
    value = report.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualificationError(f"{name} is not a nonnegative integer")
    return value


def _validate_report(
    report: object, *, device: int, maximum_seconds: int
) -> dict[str, object]:
    if not isinstance(report, dict) or set(report) != REPORT_FIELDS:
        raise QualificationError("qualification report schema changed")
    if (
        report["algorithm"] != ALGORITHM
        or _integer(report, "q") != Q
        or _integer(report, "order") != ORDER
        or _integer(report, "convolution") != CONVOLUTION
        or _integer(report, "log_convolution") != LOG_CONVOLUTION
        or _integer(report, "value_count") != ORDER
        or _integer(report, "checked_output_count") != ORDER
        or _integer(report, "radix2_butterflies") != BUTTERFLIES
        or _integer(report, "device") != device
        or _integer(report, "required_device_bytes") != REQUIRED_DEVICE_BYTES
        or _integer(report, "device_headroom_bytes") != DEVICE_HEADROOM_BYTES
        or _integer(report, "maximum_seconds") != maximum_seconds
    ):
        raise QualificationError("maximum-order qualification identity changed")
    free_bytes = _integer(report, "free_device_bytes_before")
    total_bytes = _integer(report, "total_device_bytes")
    if (
        total_bytes < free_bytes
        or free_bytes < REQUIRED_DEVICE_BYTES + DEVICE_HEADROOM_BYTES
        or _integer(report, "device_compute_major") == 0
    ):
        raise QualificationError("CUDA device or memory preflight changed")
    _integer(report, "device_compute_minor")
    _integer(report, "preparation_nanoseconds")
    _integer(report, "transform_nanoseconds")
    _integer(report, "validation_nanoseconds")
    if (
        _integer(report, "compute_validation_nanoseconds")
        > maximum_seconds * 1_000_000_000
    ):
        raise QualificationError("reported runtime exceeds its guard")
    width = report.get("maximum_component_width")
    ceiling = report.get("maximum_component_width_ceiling")
    if (
        isinstance(width, bool)
        or not isinstance(width, (int, float))
        or not math.isfinite(width)
        or width < 0.0
        or ceiling != MAXIMUM_COMPONENT_WIDTH
        or width > ceiling
    ):
        raise QualificationError("maximum-order width report is invalid")
    digest = report.get("output_payload_sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise QualificationError("output payload digest is not lowercase SHA-256")
    return report


def _verify_output(path: Path, report: dict[str, object]) -> dict[str, object]:
    identity = read_output_header(path)
    if identity != {
        "q": Q,
        "component_orders": [ORDER],
        "batch_count": 1,
        "group_order": ORDER,
        "value_count": ORDER,
        "radix2_butterflies": BUTTERFLIES,
        "elapsed_nanoseconds": report["transform_nanoseconds"],
    }:
        raise QualificationError("standard output artifact identity changed")

    digest = hashlib.sha256()
    checked = 0
    maximum_width = 0.0
    with path.open("rb") as source:
        header = source.read(OUTPUT_HEADER.size)
        if len(header) != OUTPUT_HEADER.size:
            raise QualificationError("truncated qualification output header")
        while checked < ORDER:
            count = min(16_384, ORDER - checked)
            raw = source.read(count * COMPLEX_INTERVAL.size)
            if len(raw) != count * COMPLEX_INTERVAL.size:
                raise QualificationError("truncated qualification output payload")
            digest.update(raw)
            for offset in range(0, len(raw), COMPLEX_INTERVAL.size):
                re_lo, re_hi, im_lo, im_hi = COMPLEX_INTERVAL.unpack_from(
                    raw, offset
                )
                if not (
                    all(
                        math.isfinite(value)
                        for value in (re_lo, re_hi, im_lo, im_hi)
                    )
                    and re_lo <= 1.0 <= re_hi
                    and im_lo <= 0.0 <= im_hi
                ):
                    raise QualificationError(
                        f"impulse identity missed at output {checked}"
                    )
                width = max(re_hi - re_lo, im_hi - im_lo)
                if not math.isfinite(width) or width > MAXIMUM_COMPONENT_WIDTH:
                    raise QualificationError(
                        f"output {checked} exceeded the usefulness width"
                    )
                maximum_width = max(maximum_width, width)
                checked += 1
        if source.read(1):
            raise QualificationError("qualification output has trailing bytes")
    if digest.hexdigest() != report["output_payload_sha256"]:
        raise QualificationError("qualification output digest differs")
    if maximum_width != report["maximum_component_width"]:
        raise QualificationError("independent maximum width differs")
    return {
        "independently_checked_output_count": checked,
        "independent_maximum_component_width": maximum_width,
        "output_payload_sha256": digest.hexdigest(),
    }


def run(runner: Path, *, device: int, maximum_seconds: int) -> dict[str, object]:
    if device < 0 or maximum_seconds <= 0 or maximum_seconds > 3600:
        raise QualificationError("invalid qualification runtime arguments")
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "maximum-order-impulse.out"
        try:
            completed = subprocess.run(
                [
                    str(runner.resolve()),
                    "--qualification-max-order-impulse",
                    str(output),
                    str(device),
                    str(maximum_seconds),
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                timeout=maximum_seconds + 5,
            )
        except subprocess.TimeoutExpired as error:
            raise QualificationError(
                "maximum-order CUDA qualification exceeded its hard timeout"
            ) from error
        lines = completed.stdout.strip().splitlines()
        if not lines:
            raise QualificationError("qualification runner emitted no report")
        try:
            report = _validate_report(
                json.loads(lines[-1]),
                device=device,
                maximum_seconds=maximum_seconds,
            )
        except json.JSONDecodeError as error:
            raise QualificationError(
                "qualification runner emitted invalid JSON"
            ) from error
        independent = _verify_output(output, report)
        return {
            "kind": (
                "sparkinterval.tg.dirichlet_allchars."
                "max_order_impulse_qualification.v1"
            ),
            "status": "pass",
            **report,
            **independent,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--maximum-seconds", type=int, default=300)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                run(
                    args.runner,
                    device=args.device,
                    maximum_seconds=args.maximum_seconds,
                ),
                sort_keys=True,
            )
        )
        return 0
    except (OSError, QualificationError, subprocess.CalledProcessError) as error:
        print(f"maximum-order impulse qualification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
