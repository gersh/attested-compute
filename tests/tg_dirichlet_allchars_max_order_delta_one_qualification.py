#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Semantic maximum-order CUDA qualification using the delta-one DFT."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
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


PRODUCER_ALGORITHM = (
    "platt-dirichlet-allchars-max-order-delta-one-qualification-v1"
)
CHECKER_ALGORITHM = (
    "platt-dirichlet-allchars-mpfr-max-order-delta-one-reference-v1"
)
SEMANTIC = "positive_dft_delta_one"
Q = 399_989
ORDER = 399_988
CONVOLUTION = 1 << 20
LOG_CONVOLUTION = 20
BUTTERFLIES = 3 * (CONVOLUTION // 2) * LOG_CONVOLUTION
REQUIRED_DEVICE_BYTES = (6 * CONVOLUTION + 3 * ORDER) * COMPLEX_INTERVAL.size
DEVICE_HEADROOM_BYTES = 256 * 1024 * 1024
MAXIMUM_COMPONENT_WIDTH = math.ldexp(1.0, -16)
PRODUCER_REFERENCE_PRECISION = 320
CHECKER_PRECISION = 192
PRODUCER_FIELDS = {
    "algorithm",
    "semantic",
    "q",
    "order",
    "convolution",
    "log_convolution",
    "input_nonzero_index",
    "value_count",
    "checked_output_count",
    "semantic_reference_precision_bits",
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
    "output_artifact_sha256",
}
CHECKER_FIELDS = {
    "algorithm",
    "mode",
    "semantic",
    "q",
    "order",
    "checked_output_count",
    "precision_bits",
    "elapsed_nanoseconds",
    "maximum_component_width",
}


class QualificationError(RuntimeError):
    """The maximum-order delta-one qualification failed closed."""


def _integer(report: dict[str, object], name: str) -> int:
    value = report.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualificationError(f"{name} is not a nonnegative integer")
    return value


def _finite_number(report: dict[str, object], name: str) -> float:
    value = report.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise QualificationError(f"{name} is not finite")
    return float(value)


def _lowercase_sha256(report: dict[str, object], name: str) -> str:
    value = report.get(name)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise QualificationError(f"{name} is not lowercase SHA-256")
    return value


def _run_json(command: list[str], *, timeout: int) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise QualificationError(
            f"command exceeded its {timeout}-second timeout"
        ) from error
    lines = completed.stdout.strip().splitlines()
    if not lines:
        raise QualificationError("command emitted no JSON report")
    try:
        report = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise QualificationError("command emitted invalid JSON") from error
    if not isinstance(report, dict):
        raise QualificationError("command report is not a JSON object")
    return report


def _validate_producer(
    report: dict[str, object], *,
    device: int, maximum_seconds: int
) -> None:
    if set(report) != PRODUCER_FIELDS:
        raise QualificationError("delta-one producer report schema changed")
    if (
        report["algorithm"] != PRODUCER_ALGORITHM
        or report["semantic"] != SEMANTIC
        or _integer(report, "q") != Q
        or _integer(report, "order") != ORDER
        or _integer(report, "convolution") != CONVOLUTION
        or _integer(report, "log_convolution") != LOG_CONVOLUTION
        or _integer(report, "input_nonzero_index") != 1
        or _integer(report, "value_count") != ORDER
        or _integer(report, "checked_output_count") != ORDER
        or _integer(report, "semantic_reference_precision_bits")
        != PRODUCER_REFERENCE_PRECISION
        or _integer(report, "radix2_butterflies") != BUTTERFLIES
        or _integer(report, "device") != device
        or _integer(report, "required_device_bytes") != REQUIRED_DEVICE_BYTES
        or _integer(report, "device_headroom_bytes") != DEVICE_HEADROOM_BYTES
        or _integer(report, "maximum_seconds") != maximum_seconds
    ):
        raise QualificationError("delta-one producer identity changed")
    free_bytes = _integer(report, "free_device_bytes_before")
    total_bytes = _integer(report, "total_device_bytes")
    if (
        total_bytes < free_bytes
        or free_bytes < REQUIRED_DEVICE_BYTES + DEVICE_HEADROOM_BYTES
        or _integer(report, "device_compute_major") == 0
    ):
        raise QualificationError("delta-one CUDA preflight changed")
    _integer(report, "device_compute_minor")
    _integer(report, "preparation_nanoseconds")
    _integer(report, "transform_nanoseconds")
    _integer(report, "validation_nanoseconds")
    if (
        _integer(report, "compute_validation_nanoseconds")
        > maximum_seconds * 1_000_000_000
    ):
        raise QualificationError("delta-one runtime exceeds its guard")
    width = _finite_number(report, "maximum_component_width")
    if (
        width < 0.0
        or report["maximum_component_width_ceiling"]
        != MAXIMUM_COMPONENT_WIDTH
        or width > MAXIMUM_COMPONENT_WIDTH
    ):
        raise QualificationError("delta-one width report is invalid")
    _lowercase_sha256(report, "output_payload_sha256")
    _lowercase_sha256(report, "output_artifact_sha256")


def _validate_checker(report: dict[str, object]) -> None:
    if set(report) != CHECKER_FIELDS:
        raise QualificationError("delta-one checker report schema changed")
    if (
        report["algorithm"] != CHECKER_ALGORITHM
        or report["mode"] != "verify-max-order-delta-one"
        or report["semantic"] != SEMANTIC
        or _integer(report, "q") != Q
        or _integer(report, "order") != ORDER
        or _integer(report, "checked_output_count") != ORDER
        or _integer(report, "precision_bits") != CHECKER_PRECISION
    ):
        raise QualificationError("delta-one checker identity changed")
    _integer(report, "elapsed_nanoseconds")
    width = _finite_number(report, "maximum_component_width")
    if width < 0.0 or width > MAXIMUM_COMPONENT_WIDTH:
        raise QualificationError("delta-one checker width is invalid")


def _verify_wire(
    path: Path, report: dict[str, object]
) -> dict[str, object]:
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
        raise QualificationError("delta-one output identity changed")

    artifact_digest = hashlib.sha256()
    payload_digest = hashlib.sha256()
    checked = 0
    maximum_width = 0.0
    with path.open("rb") as source:
        header = source.read(OUTPUT_HEADER.size)
        if len(header) != OUTPUT_HEADER.size:
            raise QualificationError("truncated delta-one output header")
        artifact_digest.update(header)
        while checked < ORDER:
            count = min(16_384, ORDER - checked)
            raw = source.read(count * COMPLEX_INTERVAL.size)
            if len(raw) != count * COMPLEX_INTERVAL.size:
                raise QualificationError("truncated delta-one output payload")
            artifact_digest.update(raw)
            payload_digest.update(raw)
            for offset in range(0, len(raw), COMPLEX_INTERVAL.size):
                re_lo, re_hi, im_lo, im_hi = COMPLEX_INTERVAL.unpack_from(
                    raw, offset
                )
                if not (
                    all(
                        math.isfinite(value)
                        for value in (re_lo, re_hi, im_lo, im_hi)
                    )
                    and re_lo <= re_hi
                    and im_lo <= im_hi
                ):
                    raise QualificationError(
                        f"malformed delta-one output {checked}"
                    )
                width = max(re_hi - re_lo, im_hi - im_lo)
                if not math.isfinite(width) or width > MAXIMUM_COMPONENT_WIDTH:
                    raise QualificationError(
                        f"delta-one output {checked} exceeded width ceiling"
                    )
                maximum_width = max(maximum_width, width)
                checked += 1
        if source.read(1):
            raise QualificationError("delta-one output has trailing bytes")
    if payload_digest.hexdigest() != report["output_payload_sha256"]:
        raise QualificationError("delta-one payload digest differs")
    if artifact_digest.hexdigest() != report["output_artifact_sha256"]:
        raise QualificationError("delta-one artifact digest differs")
    if maximum_width != report["maximum_component_width"]:
        raise QualificationError("delta-one independent width differs")
    return {
        "independently_parsed_output_count": checked,
        "independent_maximum_component_width": maximum_width,
        "output_payload_sha256": payload_digest.hexdigest(),
        "output_artifact_sha256": artifact_digest.hexdigest(),
    }


def _reject(command: list[str], label: str, *, timeout: int = 30) -> None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise QualificationError(
            f"hostile {label} did not fail promptly"
        ) from error
    if completed.returncode == 0:
        raise QualificationError(f"accepted hostile {label}")


def _hostile_checker_cases(
    checker: Path, good: Path, root: Path, *, checker_timeout: int
) -> None:
    raw = good.read_bytes()
    hostile = {
        "truncated artifact": root / "truncated.out",
        "trailing artifact": root / "trailing.out",
        "finite forged output": root / "forged.out",
        "swapped output indices": root / "swapped.out",
        "conjugated output sign": root / "conjugated.out",
        "wrong header identity": root / "wrong-header.out",
    }
    hostile["truncated artifact"].write_bytes(raw[:-1])
    hostile["trailing artifact"].write_bytes(raw + b"\0")

    shutil.copyfile(good, hostile["finite forged output"])
    with hostile["finite forged output"].open("r+b") as target:
        # Output 1 should be exp(2*pi*i/N), not zero.
        target.seek(OUTPUT_HEADER.size + COMPLEX_INTERVAL.size)
        target.write(COMPLEX_INTERVAL.pack(0.0, 0.0, 0.0, 0.0))

    swapped = bytearray(raw)
    first_index = 20_000
    second_index = first_index + 1
    first_offset = OUTPUT_HEADER.size + first_index * COMPLEX_INTERVAL.size
    second_offset = OUTPUT_HEADER.size + second_index * COMPLEX_INTERVAL.size
    first_record = bytes(
        swapped[first_offset : first_offset + COMPLEX_INTERVAL.size]
    )
    swapped[first_offset : first_offset + COMPLEX_INTERVAL.size] = swapped[
        second_offset : second_offset + COMPLEX_INTERVAL.size
    ]
    swapped[second_offset : second_offset + COMPLEX_INTERVAL.size] = (
        first_record
    )
    hostile["swapped output indices"].write_bytes(swapped)

    conjugated = bytearray(raw)
    conjugated_index = 10_000
    conjugated_offset = (
        OUTPUT_HEADER.size + conjugated_index * COMPLEX_INTERVAL.size
    )
    re_lo, re_hi, im_lo, im_hi = COMPLEX_INTERVAL.unpack_from(
        conjugated, conjugated_offset
    )
    COMPLEX_INTERVAL.pack_into(
        conjugated,
        conjugated_offset,
        re_lo,
        re_hi,
        -im_hi,
        -im_lo,
    )
    hostile["conjugated output sign"].write_bytes(conjugated)

    header = list(OUTPUT_HEADER.unpack_from(raw))
    header[2] = Q - 1
    hostile["wrong header identity"].write_bytes(
        OUTPUT_HEADER.pack(*header) + raw[OUTPUT_HEADER.size :]
    )
    for label, path in hostile.items():
        _reject(
            [
                str(checker),
                "verify-max-order-delta-one",
                str(path),
                str(CHECKER_PRECISION),
            ],
            label,
            timeout=checker_timeout,
        )
    for precision in ("95", "4097", "-1"):
        _reject(
            [
                str(checker),
                "verify-max-order-delta-one",
                str(good),
                precision,
            ],
            f"checker precision {precision}",
        )


def _hostile_producer_cases(runner: Path, root: Path) -> None:
    for output, device, maximum_seconds, label in (
        ("rejected-zero-seconds.out", "0", "0", "zero runtime"),
        ("rejected-large-seconds.out", "0", "3601", "oversized runtime"),
        ("rejected-negative-device.out", "-1", "30", "negative device"),
        ("", "0", "30", "empty output"),
    ):
        _reject(
            [
                str(runner),
                "--qualification-max-order-delta-one",
                str(root / output) if output else "",
                device,
                maximum_seconds,
            ],
            label,
        )


def run(
    runner: Path,
    checker: Path,
    *,
    device: int,
    maximum_seconds: int,
    checker_timeout: int,
) -> dict[str, object]:
    if (
        device < 0
        or maximum_seconds <= 0
        or maximum_seconds > 3600
        or checker_timeout <= 0
    ):
        raise QualificationError("invalid delta-one qualification arguments")
    runner = runner.resolve()
    checker = checker.resolve()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        output = root / "maximum-order-delta-one.out"
        report = _run_json(
            [
                str(runner),
                "--qualification-max-order-delta-one",
                str(output),
                str(device),
                str(maximum_seconds),
            ],
            timeout=maximum_seconds + 5,
        )
        _validate_producer(
            report, device=device, maximum_seconds=maximum_seconds
        )
        wire = _verify_wire(output, report)
        checker_report = _run_json(
            [
                str(checker),
                "verify-max-order-delta-one",
                str(output),
                str(CHECKER_PRECISION),
            ],
            timeout=checker_timeout,
        )
        _validate_checker(checker_report)
        if (
            checker_report["maximum_component_width"]
            != wire["independent_maximum_component_width"]
        ):
            raise QualificationError(
                "MPFR checker and wire pass report different widths"
            )
        _hostile_checker_cases(
            checker, output, root, checker_timeout=checker_timeout
        )
        _hostile_producer_cases(runner, root)
        return {
            "kind": (
                "sparkinterval.tg.dirichlet_allchars."
                "max_order_delta_one_qualification.v1"
            ),
            "status": "pass",
            **report,
            **wire,
            "independent_checker_algorithm": checker_report["algorithm"],
            "independent_checker_precision_bits": checker_report[
                "precision_bits"
            ],
            "independent_checker_elapsed_nanoseconds": checker_report[
                "elapsed_nanoseconds"
            ],
            "independent_semantic_output_count": checker_report[
                "checked_output_count"
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--maximum-seconds", type=int, default=300)
    parser.add_argument("--checker-timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                run(
                    args.runner,
                    args.checker,
                    device=args.device,
                    maximum_seconds=args.maximum_seconds,
                    checker_timeout=args.checker_timeout,
                ),
                sort_keys=True,
            )
        )
        return 0
    except (
        OSError,
        QualificationError,
        subprocess.CalledProcessError,
    ) as error:
        print(
            f"maximum-order delta-one qualification failed: {error}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
