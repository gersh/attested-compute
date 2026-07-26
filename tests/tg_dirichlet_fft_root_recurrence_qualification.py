#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Qualify periodic-anchor MPFR radix-2 FFT roots over the source catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


ROOT_RECORD = struct.Struct("<dddd")
LENGTHS = tuple(1 << exponent for exponent in range(2, 21))
ANCHOR_CADENCE = 256
RECURRENCE_PRECISION = 256
DIRECT_PRECISION = 320
CHECKER_PRECISION = 192
WIDTH_CEILING = math.ldexp(1.0, -48)
PRODUCER_ALGORITHM = "platt-dirichlet-fft-root-periodic-anchor-v1"
CHECKER_ALGORITHM = "platt-dirichlet-allchars-mpfr-fft-root-reference-v1"
PRODUCER_FIELDS = {
    "algorithm",
    "mode",
    "length",
    "sign",
    "precision_bits",
    "anchor_cadence",
    "stages",
    "anchors",
    "recurrence_updates",
    "generation_nanoseconds",
    "maximum_internal_mpfr_component_width",
    "maximum_binary64_component_width",
    "maximum_binary64_component_width_ceiling",
    "root_count",
    "root_record_bytes",
    "root_sha256",
}
CHECKER_FIELDS = {
    "algorithm",
    "mode",
    "length",
    "sign",
    "root_count",
    "precision_bits",
    "elapsed_nanoseconds",
}


class QualificationError(RuntimeError):
    """The FFT-root recurrence qualification failed closed."""


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
        value = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise QualificationError("command emitted invalid JSON") from error
    if not isinstance(value, dict):
        raise QualificationError("command report is not a JSON object")
    return value


def _integer(report: dict[str, object], key: str) -> int:
    value = report.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualificationError(f"{key} is not a nonnegative integer")
    return value


def _finite_number(report: dict[str, object], key: str) -> float:
    value = report.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise QualificationError(f"{key} is not finite")
    return float(value)


def _anchors(length: int) -> int:
    answer = 0
    stage = 2
    while stage <= length:
        half = stage // 2
        answer += (half + ANCHOR_CADENCE - 1) // ANCHOR_CADENCE
        stage *= 2
    return answer


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _validate_producer(
    report: dict[str, object], path: Path, *,
    mode: str, length: int, sign: int
) -> None:
    if set(report) != PRODUCER_FIELDS:
        raise QualificationError("FFT-root producer report schema changed")
    root_count = length - 1
    recurrence = mode in {"recurrence", "conjugate"}
    expected_anchors = _anchors(length) if recurrence else root_count
    expected_updates = root_count - expected_anchors if recurrence else 0
    if (
        report["algorithm"] != PRODUCER_ALGORITHM
        or report["mode"] != mode
        or _integer(report, "length") != length
        or report["sign"] != sign
        or _integer(report, "precision_bits")
        != (RECURRENCE_PRECISION if recurrence else DIRECT_PRECISION)
        or _integer(report, "anchor_cadence") != ANCHOR_CADENCE
        or _integer(report, "stages") != length.bit_length() - 1
        or _integer(report, "anchors") != expected_anchors
        or _integer(report, "recurrence_updates") != expected_updates
        or _integer(report, "root_count") != root_count
        or _integer(report, "root_record_bytes") != ROOT_RECORD.size
        or path.stat().st_size != root_count * ROOT_RECORD.size
    ):
        raise QualificationError("FFT-root producer identity changed")
    _integer(report, "generation_nanoseconds")
    internal_width = _finite_number(
        report, "maximum_internal_mpfr_component_width"
    )
    binary_width = _finite_number(
        report, "maximum_binary64_component_width"
    )
    if (
        internal_width < 0.0
        or binary_width < 0.0
        or report["maximum_binary64_component_width_ceiling"] != WIDTH_CEILING
        or binary_width > WIDTH_CEILING
    ):
        raise QualificationError("FFT-root producer width guard changed")
    digest = report.get("root_sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or digest != _sha256(path)
    ):
        raise QualificationError("FFT-root producer digest differs")


def _validate_checker(
    report: dict[str, object], *, length: int, sign: int
) -> None:
    if (
        set(report) != CHECKER_FIELDS
        or report["algorithm"] != CHECKER_ALGORITHM
        or report["mode"] != "verify-fft-roots"
        or _integer(report, "length") != length
        or report["sign"] != sign
        or _integer(report, "root_count") != length - 1
        or _integer(report, "precision_bits") != CHECKER_PRECISION
    ):
        raise QualificationError("FFT-root checker identity changed")
    _integer(report, "elapsed_nanoseconds")


def _compare_containment(
    candidate_path: Path, direct_path: Path, root_count: int
) -> int:
    byte_identical = 0
    with candidate_path.open("rb") as candidate, direct_path.open("rb") as direct:
        for index in range(root_count):
            candidate_raw = candidate.read(ROOT_RECORD.size)
            direct_raw = direct.read(ROOT_RECORD.size)
            if (
                len(candidate_raw) != ROOT_RECORD.size
                or len(direct_raw) != ROOT_RECORD.size
            ):
                raise QualificationError("truncated FFT-root comparison")
            candidate_box = ROOT_RECORD.unpack(candidate_raw)
            direct_box = ROOT_RECORD.unpack(direct_raw)
            for component in (0, 2):
                if not (
                    candidate_box[component]
                    <= direct_box[component]
                    <= direct_box[component + 1]
                    <= candidate_box[component + 1]
                ):
                    raise QualificationError(
                        f"recurrence missed direct root {index}"
                    )
            byte_identical += candidate_raw == direct_raw
        if candidate.read(1) or direct.read(1):
            raise QualificationError("FFT-root comparison has trailing bytes")
    return byte_identical


def _reject(command: list[str], label: str) -> None:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode == 0:
        raise QualificationError(f"accepted hostile {label}")


def run(
    runner: Path, checker: Path, *, command_timeout: int
) -> dict[str, object]:
    runner = runner.resolve()
    checker = checker.resolve()
    if command_timeout <= 0:
        raise QualificationError("command timeout must be positive")
    total_roots = 0
    positive_identical = 0
    negative_identical = 0
    production_nanoseconds = 0
    direct_nanoseconds = 0
    recurrence_nanoseconds = 0
    checker_nanoseconds = 0
    maximum_internal_width = 0.0
    maximum_binary64_width = 0.0
    maximum_report: dict[str, object] | None = None

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        paths = {
            "recurrence": root / "recurrence-positive.bin",
            "conjugate": root / "conjugate-negative.bin",
            "direct-positive": root / "direct-positive.bin",
            "direct-negative": root / "direct-negative.bin",
        }
        for length in LENGTHS:
            modes = (
                ("recurrence", 1, paths["recurrence"]),
                ("conjugate", -1, paths["conjugate"]),
                ("direct", 1, paths["direct-positive"]),
                ("direct", -1, paths["direct-negative"]),
            )
            reports: dict[tuple[str, int], dict[str, object]] = {}
            for mode, sign, path in modes:
                report = _run_json(
                    [
                        str(runner),
                        "--dump-fft-roots",
                        mode,
                        str(length),
                        str(sign),
                        str(path),
                    ],
                    timeout=command_timeout,
                )
                _validate_producer(
                    report, path, mode=mode, length=length, sign=sign
                )
                reports[(mode, sign)] = report
                checked = _run_json(
                    [
                        str(checker),
                        "verify-fft-roots",
                        str(length),
                        str(sign),
                        str(path),
                        str(CHECKER_PRECISION),
                    ],
                    timeout=command_timeout,
                )
                _validate_checker(checked, length=length, sign=sign)
                checker_nanoseconds += _integer(
                    checked, "elapsed_nanoseconds"
                )

            root_count = length - 1
            positive_identical += _compare_containment(
                paths["recurrence"], paths["direct-positive"], root_count
            )
            negative_identical += _compare_containment(
                paths["conjugate"], paths["direct-negative"], root_count
            )
            total_roots += root_count
            recurrence_nanoseconds += _integer(
                reports[("recurrence", 1)], "generation_nanoseconds"
            )
            production_nanoseconds += _integer(
                reports[("conjugate", -1)], "generation_nanoseconds"
            )
            direct_nanoseconds += sum(
                _integer(reports[("direct", sign)], "generation_nanoseconds")
                for sign in (1, -1)
            )
            maximum_internal_width = max(
                maximum_internal_width,
                _finite_number(
                    reports[("recurrence", 1)],
                    "maximum_internal_mpfr_component_width",
                ),
            )
            maximum_binary64_width = max(
                maximum_binary64_width,
                _finite_number(
                    reports[("recurrence", 1)],
                    "maximum_binary64_component_width",
                ),
            )
            if length == LENGTHS[-1]:
                maximum_report = reports[("recurrence", 1)]

        # Exercise malformed wire data independently of the large tables.
        small = root / "small.bin"
        _run_json(
            [
                str(runner),
                "--dump-fft-roots",
                "recurrence",
                "4",
                "1",
                str(small),
            ],
            timeout=command_timeout,
        )
        raw = small.read_bytes()
        hostile_paths = {
            "truncated dump": root / "truncated.bin",
            "trailing dump": root / "trailing.bin",
            "finite forged dump": root / "forged.bin",
        }
        hostile_paths["truncated dump"].write_bytes(raw[:-1])
        hostile_paths["trailing dump"].write_bytes(raw + b"\0")
        forged = bytearray(raw)
        forged[:16] = struct.pack("<dd", 0.0, 0.0)
        hostile_paths["finite forged dump"].write_bytes(forged)
        for label, path in hostile_paths.items():
            _reject(
                [
                    str(checker),
                    "verify-fft-roots",
                    "4",
                    "1",
                    str(path),
                    str(CHECKER_PRECISION),
                ],
                label,
            )
        _reject(
            [
                str(checker),
                "verify-fft-roots",
                "12",
                "1",
                str(small),
                str(CHECKER_PRECISION),
            ],
            "checker geometry",
        )
        for mode, length, sign in (
            ("recurrence", "0", "1"),
            ("recurrence", "2", "1"),
            ("recurrence", "12", "1"),
            ("recurrence", str(1 << 21), "1"),
            ("recurrence", "4", "0"),
            ("conjugate", "4", "1"),
            ("unknown", "4", "1"),
        ):
            _reject(
                [
                    str(runner),
                    "--dump-fft-roots",
                    mode,
                    length,
                    sign,
                    str(root / "rejected.bin"),
                ],
                "producer geometry or mode",
            )

    if maximum_report is None or production_nanoseconds == 0:
        raise QualificationError("source root catalog was not exercised")
    return {
        "kind": (
            "sparkinterval.tg.dirichlet_allchars."
            "fft_root_recurrence_qualification.v1"
        ),
        "status": "pass",
        "lengths": list(LENGTHS),
        "length_count": len(LENGTHS),
        "anchor_cadence": ANCHOR_CADENCE,
        "recurrence_precision_bits": RECURRENCE_PRECISION,
        "direct_precision_bits": DIRECT_PRECISION,
        "checker_precision_bits": CHECKER_PRECISION,
        "root_count_per_sign": total_roots,
        "independently_checked_root_rectangles": 4 * total_roots,
        "positive_byte_identical_direct_roots": positive_identical,
        "negative_byte_identical_direct_roots": negative_identical,
        "positive_strictly_wider_roots": total_roots - positive_identical,
        "negative_strictly_wider_roots": total_roots - negative_identical,
        "maximum_internal_mpfr_component_width": maximum_internal_width,
        "maximum_binary64_component_width": maximum_binary64_width,
        "maximum_binary64_component_width_ceiling": WIDTH_CEILING,
        "recurrence_positive_generation_nanoseconds": recurrence_nanoseconds,
        "production_positive_plus_conjugate_nanoseconds": production_nanoseconds,
        "direct_two_sign_generation_nanoseconds": direct_nanoseconds,
        "direct_over_production_speedup": (
            direct_nanoseconds / production_nanoseconds
        ),
        "independent_checker_nanoseconds": checker_nanoseconds,
        "maximum_length_root_sha256": maximum_report["root_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--command-timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                run(
                    args.runner,
                    args.checker,
                    command_timeout=args.command_timeout,
                ),
                sort_keys=True,
            )
        )
        return 0
    except (OSError, QualificationError, subprocess.CalledProcessError) as error:
        print(f"FFT-root recurrence qualification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
