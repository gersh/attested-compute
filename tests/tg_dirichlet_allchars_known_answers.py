#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""CUDA/MPFR known-answer tests for the all-character Bluestein stage."""

from __future__ import annotations

import argparse
import cmath
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
    DirichletAllCharsStageError,
    INPUT_HEADER,
    OUTPUT_HEADER,
    canonical_component_orders,
    read_output_header,
    validate_multiq_framed_summary,
    write_synthetic_input,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (  # noqa: E402
    DirichletAllCharsQSchedulerError,
    ScheduleRecord,
    parse_schedule_manifest,
    phase_schedule_projection,
    validate_phase_scheduled_multiq_framed_summary_commitments,
    validate_scheduled_multiq_framed_summary,
    write_bounded_schedule_manifest,
)
from tg_verifier.dirichlet_resident_handoff_fixture import (  # noqa: E402
    prepare_fixture,
    run_fixture,
)

CHIRP_STATE_RECORD = struct.Struct("<dddddddd")
CHIRP_PRODUCER_ALGORITHM = "platt-dirichlet-chirp-periodic-anchor-v1"
CHIRP_CHECKER_ALGORITHM = (
    "platt-dirichlet-allchars-mpfr-chirp-reference-v1"
)
CHIRP_ANCHOR_CADENCE = 256
CHIRP_RECURRENCE_PRECISION = 256
CHIRP_DIRECT_PRECISION = 320
CHIRP_CHECKER_PRECISION = 192
CHIRP_WIDTH_CEILING = math.ldexp(1.0, -48)
CHIRP_PRODUCER_FIELDS = {
    "algorithm",
    "mode",
    "length",
    "sign",
    "precision_bits",
    "anchor_cadence",
    "anchors",
    "recurrence_updates",
    "generation_nanoseconds",
    "maximum_internal_mpfr_component_width",
    "maximum_binary64_component_width",
    "maximum_binary64_component_width_ceiling",
    "state_count",
    "state_record_bytes",
    "state_sha256",
}
CHIRP_CHECKER_FIELDS = {
    "algorithm",
    "mode",
    "length",
    "sign",
    "state_count",
    "rectangle_count",
    "precision_bits",
    "elapsed_nanoseconds",
}


def _coordinates(ordinal: int, orders: tuple[int, ...]) -> tuple[int, ...]:
    answer = []
    for order in orders:
        ordinal, digit = divmod(ordinal, order)
        answer.append(digit)
    if ordinal:
        raise RuntimeError("coordinate overflow")
    return tuple(answer)


def _check_positive_character_convention(input_path: Path, output_path: Path,
                                         q: int) -> None:
    orders = canonical_component_orders(q)
    total = math.prod(orders)
    input_raw = input_path.read_bytes()
    output_raw = output_path.read_bytes()
    values: list[complex] = []
    for index in range(total):
        re_lo, re_hi, im_lo, im_hi = COMPLEX_INTERVAL.unpack_from(
            input_raw, INPUT_HEADER.size + index * COMPLEX_INTERVAL.size
        )
        values.append(complex((re_lo + re_hi) / 2, (im_lo + im_hi) / 2))
    for frequency_id in range(total):
        frequencies = _coordinates(frequency_id, orders)
        expected = 0j
        for group_id, value in enumerate(values):
            exponents = _coordinates(group_id, orders)
            phase = sum(
                exponent * frequency / order
                for exponent, frequency, order in zip(
                    exponents, frequencies, orders
                )
            )
            expected += value * cmath.exp(2j * math.pi * phase)
        re_lo, re_hi, im_lo, im_hi = COMPLEX_INTERVAL.unpack_from(
            output_raw,
            OUTPUT_HEADER.size + frequency_id * COMPLEX_INTERVAL.size,
        )
        tolerance = 5e-13 * max(1.0, abs(expected))
        if not (re_lo - tolerance <= expected.real <= re_hi + tolerance and
                im_lo - tolerance <= expected.imag <= im_hi + tolerance):
            raise RuntimeError(
                "output does not use the documented positive character DFT"
            )


def _run_json(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _nonnegative_integer(report: dict[str, object], name: str) -> int:
    value = report.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"{name} is not a nonnegative integer")
    return value


def _finite_number(report: dict[str, object], name: str) -> float:
    value = report.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise RuntimeError(f"{name} is not finite")
    return float(value)


def _validate_chirp_producer_report(
    report: dict[str, object],
    path: Path,
    *,
    mode: str,
    length: int,
    sign: int,
) -> None:
    if set(report) != CHIRP_PRODUCER_FIELDS:
        raise RuntimeError("chirp producer report schema changed")
    recurrence = mode in {"recurrence", "conjugate"}
    expected_anchors = (
        (length + CHIRP_ANCHOR_CADENCE - 1) // CHIRP_ANCHOR_CADENCE
        if recurrence
        else length
    )
    expected_updates = length - expected_anchors if recurrence else 0
    if (
        report["algorithm"] != CHIRP_PRODUCER_ALGORITHM
        or report["mode"] != mode
        or _nonnegative_integer(report, "length") != length
        or report["sign"] != sign
        or _nonnegative_integer(report, "precision_bits")
        != (
            CHIRP_RECURRENCE_PRECISION
            if recurrence
            else CHIRP_DIRECT_PRECISION
        )
        or _nonnegative_integer(report, "anchor_cadence")
        != CHIRP_ANCHOR_CADENCE
        or _nonnegative_integer(report, "anchors") != expected_anchors
        or _nonnegative_integer(report, "recurrence_updates")
        != expected_updates
        or _nonnegative_integer(report, "state_count") != length
        or _nonnegative_integer(report, "state_record_bytes")
        != CHIRP_STATE_RECORD.size
        or path.stat().st_size != length * CHIRP_STATE_RECORD.size
    ):
        raise RuntimeError("chirp producer identity changed")
    _nonnegative_integer(report, "generation_nanoseconds")
    internal_width = _finite_number(
        report, "maximum_internal_mpfr_component_width"
    )
    binary_width = _finite_number(
        report, "maximum_binary64_component_width"
    )
    if (
        internal_width < 0.0
        or binary_width < 0.0
        or report["maximum_binary64_component_width_ceiling"]
        != CHIRP_WIDTH_CEILING
        or binary_width > CHIRP_WIDTH_CEILING
    ):
        raise RuntimeError("chirp producer width guard changed")
    digest = report.get("state_sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or digest != hashlib.sha256(path.read_bytes()).hexdigest()
    ):
        raise RuntimeError("chirp producer digest differs")


def _validate_chirp_checker_report(
    report: dict[str, object], *, length: int, sign: int
) -> None:
    if (
        set(report) != CHIRP_CHECKER_FIELDS
        or report["algorithm"] != CHIRP_CHECKER_ALGORITHM
        or report["mode"] != "verify-chirp"
        or _nonnegative_integer(report, "length") != length
        or report["sign"] != sign
        or _nonnegative_integer(report, "state_count") != length
        or _nonnegative_integer(report, "rectangle_count") != 2 * length
        or _nonnegative_integer(report, "precision_bits")
        != CHIRP_CHECKER_PRECISION
    ):
        raise RuntimeError("chirp checker identity changed")
    _nonnegative_integer(report, "elapsed_nanoseconds")


def _compare_chirp_state_dumps(recurrence_path: Path,
                               direct_path: Path,
                               length: int) -> int:
    # The recurrence state remains at 256-bit MPFR precision; these binary64
    # rectangles are only outward-facing copies and are never fed back into
    # the recurrence.  Consequently the next row need not contain the
    # (strictly wider) exact product hull of the previous binary64 row.  The
    # sound check at this boundary is that every exposed recurrence rectangle
    # contains the independently generated direct-root rectangle.
    byte_identical = 0
    with (
        recurrence_path.open("rb") as recurrence,
        direct_path.open("rb") as direct,
    ):
        for index in range(length):
            recurrence_raw = recurrence.read(CHIRP_STATE_RECORD.size)
            direct_raw = direct.read(CHIRP_STATE_RECORD.size)
            if (
                len(recurrence_raw) != CHIRP_STATE_RECORD.size
                or len(direct_raw) != CHIRP_STATE_RECORD.size
            ):
                raise RuntimeError("truncated chirp state comparison")
            recurrence_state = CHIRP_STATE_RECORD.unpack(recurrence_raw)
            direct_state = CHIRP_STATE_RECORD.unpack(direct_raw)
            for component in range(0, len(recurrence_state), 2):
                if not (
                    recurrence_state[component]
                    <= direct_state[component]
                    <= direct_state[component + 1]
                    <= recurrence_state[component + 1]
                ):
                    raise RuntimeError(
                        "periodic recurrence did not contain the direct "
                        f"binary64 enclosure at entry {index}"
                    )
            byte_identical += recurrence_raw == direct_raw
        if recurrence.read(1) or direct.read(1):
            raise RuntimeError("trailing chirp state comparison bytes")
    return byte_identical


def _check_periodic_chirp_generation(runner: Path, checker: Path,
                                     root: Path) -> None:
    # Lengths 1 and 2 cover recurrence boundaries; 9 is an odd composite.
    # The q-shaped cases benchmark the 72 x 136 and 2 x 8 x 2500 plans.
    # q=399989 is prime, so 399988 is the maximum cyclic component order in
    # the complete q <= 400000 source range.
    lengths = (1, 2, 8, 9, 72, 136, 2500, 399_988)
    q_orders = {
        10_001: set(canonical_component_orders(10_001)),
        100_000: set(canonical_component_orders(100_000)),
    }
    reports: dict[tuple[int, int, str], dict[str, object]] = {}
    byte_identical_records = 0
    production_byte_identical_records = 0
    state_records = 0
    for length in lengths:
        for sign in (-1, 1):
            recurrence_path = root / f"chirp-{length}-{sign}-recurrence.bin"
            direct_path = root / f"chirp-{length}-{sign}-direct.bin"
            recurrence_report = _run_json(
                [
                    str(runner),
                    "--dump-chirp",
                    "recurrence",
                    str(length),
                    str(sign),
                    str(recurrence_path),
                ]
            )
            _validate_chirp_producer_report(
                recurrence_report,
                recurrence_path,
                mode="recurrence",
                length=length,
                sign=sign,
            )
            direct_report = _run_json(
                [
                    str(runner),
                    "--dump-chirp",
                    "direct",
                    str(length),
                    str(sign),
                    str(direct_path),
                ]
            )
            _validate_chirp_producer_report(
                direct_report,
                direct_path,
                mode="direct",
                length=length,
                sign=sign,
            )
            production_path = recurrence_path
            production_report = recurrence_report
            if sign == -1:
                production_path = root / f"chirp-{length}-{sign}-conjugate.bin"
                production_report = _run_json(
                    [
                        str(runner),
                        "--dump-chirp",
                        "conjugate",
                        str(length),
                        str(sign),
                        str(production_path),
                    ]
                )
                _validate_chirp_producer_report(
                    production_report,
                    production_path,
                    mode="conjugate",
                    length=length,
                    sign=sign,
                )
            for path in {recurrence_path, direct_path, production_path}:
                checker_report = _run_json(
                    [
                        str(checker),
                        "verify-chirp",
                        str(length),
                        str(sign),
                        str(path),
                        str(CHIRP_CHECKER_PRECISION),
                    ]
                )
                _validate_chirp_checker_report(
                    checker_report, length=length, sign=sign
                )
            reports[(length, sign, "recurrence")] = recurrence_report
            reports[(length, sign, "direct")] = direct_report
            if sign == -1:
                reports[(length, sign, "conjugate")] = production_report
            byte_identical_records += _compare_chirp_state_dumps(
                recurrence_path, direct_path, length
            )
            production_byte_identical_records += (
                _compare_chirp_state_dumps(
                    production_path, direct_path, length
                )
            )
            state_records += length

    reference_state = root / "chirp-9-1-recurrence.bin"
    truncated_state = root / "chirp-truncated.bin"
    truncated_state.write_bytes(reference_state.read_bytes()[:-1])
    trailing_state = root / "chirp-trailing.bin"
    trailing_state.write_bytes(reference_state.read_bytes() + b"\0")
    forged_state = root / "chirp-forged.bin"
    shutil.copyfile(reference_state, forged_state)
    with forged_state.open("r+b") as state:
        # The exact first chirp is 1+0i.  This remains a finite, ordered
        # rectangle but deliberately excludes that direct MPFR value.
        state.write(struct.pack("<dd", 0.0, 0.0))
    for hostile in (truncated_state, trailing_state, forged_state):
        rejected = subprocess.run(
            [
                str(checker),
                "verify-chirp",
                "9",
                "1",
                str(hostile),
                "192",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected.returncode == 0:
            raise RuntimeError("MPFR checker accepted a hostile chirp dump")
    for bad_mode, bad_length, bad_sign in (
        ("recurrence", "0", "1"),
        ("recurrence", "400001", "1"),
        ("recurrence", "9", "0"),
        ("conjugate", "9", "1"),
    ):
        rejected = subprocess.run(
            [
                str(runner),
                "--dump-chirp",
                bad_mode,
                bad_length,
                bad_sign,
                str(root / "rejected-chirp.bin"),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected.returncode == 0:
            raise RuntimeError("chirp producer accepted invalid geometry")

    benchmark: dict[str, object] = {}
    for q, orders in q_orders.items():
        diagnostic_recurrence_ns = sum(
            int(reports[(length, sign, "recurrence")][
                "generation_nanoseconds"
            ])
            for length in orders
            for sign in (-1, 1)
        )
        production_ns = sum(
            # The conjugate diagnostic times one positive recurrence plus
            # construction of its negative array, exactly as production does.
            int(reports[(length, -1, "conjugate")][
                "generation_nanoseconds"
            ])
            for length in orders
        )
        direct_ns = sum(
            int(reports[(length, sign, "direct")]["generation_nanoseconds"])
            for length in orders
            for sign in (-1, 1)
        )
        benchmark[str(q)] = {
            "orders": sorted(orders),
            "diagnostic_two_sign_recurrence_nanoseconds": (
                diagnostic_recurrence_ns
            ),
            "production_positive_plus_conjugate_nanoseconds": production_ns,
            "direct_generation_nanoseconds": direct_ns,
            "direct_over_production_speedup": direct_ns / production_ns,
        }
    maximum_width = max(
        float(report["maximum_binary64_component_width"])
        for (length, sign, mode), report in reports.items()
        if mode == "recurrence"
    )
    maximum_mpfr_width = max(
        float(report["maximum_internal_mpfr_component_width"])
        for (length, sign, mode), report in reports.items()
        if mode == "recurrence"
    )
    print(
        json.dumps(
            {
                "kind": (
                    "sparkinterval.tg.dirichlet_allchars."
                    "periodic_chirp_qualification.v1"
                ),
                "status": "pass",
                "anchor_cadence": CHIRP_ANCHOR_CADENCE,
                "precision_bits": reports[(1, 1, "recurrence")][
                    "precision_bits"
                ],
                "direct_mpfr_reference_precision_bits": CHIRP_CHECKER_PRECISION,
                "lengths": list(lengths),
                "signs": [-1, 1],
                "state_records": state_records,
                "byte_identical_direct_records": byte_identical_records,
                "production_byte_identical_direct_records": (
                    production_byte_identical_records
                ),
                "maximum_internal_mpfr_component_width": maximum_mpfr_width,
                "maximum_binary64_component_width": maximum_width,
                "maximum_binary64_component_width_ceiling": (
                    CHIRP_WIDTH_CEILING
                ),
                "benchmarks": benchmark,
            },
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()
    runner = args.runner.resolve()
    checker = args.checker.resolve()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        _check_periodic_chirp_generation(runner, checker, root)
        # q=7 forces a length-six arbitrary DFT (Bluestein length 16).
        # q=8 exercises C2 x C2, q=15 exercises a CRT C2 x C4 product,
        # and the larger primes exercise the shared-memory prefix at and
        # beyond its 256/512/1024 transform boundaries.
        for q in (5, 7, 8, 15, 257, 509, 1031):
            input_path = root / f"q{q}.in"
            gpu_path = root / f"q{q}.gpu"
            cpu_path = root / f"q{q}.cpu"
            write_synthetic_input(input_path, q=q, t_index=127)
            subprocess.run(
                [str(runner), str(input_path), str(gpu_path), str(args.device), "1"],
                check=True,
            )
            subprocess.run(
                [str(checker), "verify", str(input_path), str(gpu_path), "192"],
                check=True,
            )
            subprocess.run(
                [str(checker), "compute", str(input_path), str(cpu_path), "192"],
                check=True,
            )
            subprocess.run(
                [str(checker), "verify", str(input_path), str(cpu_path), "192"],
                check=True,
            )
            self_report = read_output_header(gpu_path)
            if self_report["q"] != q:
                raise RuntimeError("output identity changed")
            _check_positive_character_convention(input_path, gpu_path, q)

        # Source-shaped component-order edges are large enough that the
        # quadratic direct-sum convention check above would be inappropriate.
        # The independent MPFR verifier still reconstructs the group, roots,
        # and complete transform and checks every CUDA rectangle.  q=10001
        # covers a moderate two-factor transform; q=100000 exercises the
        # 2 x 8 x 2500 decomposition and global stages after the shared prefix.
        for q in (10_001, 100_000):
            input_path = root / f"q{q}-source-edge.in"
            gpu_path = root / f"q{q}-source-edge.gpu"
            write_synthetic_input(input_path, q=q, t_index=127)
            subprocess.run(
                [str(runner), str(input_path), str(gpu_path), str(args.device), "1"],
                check=True,
            )
            subprocess.run(
                [str(checker), "verify", str(input_path), str(gpu_path), "192"],
                check=True,
            )

        # Sign-quadrant edges, exact zeros, signed zero, and subnormal-width
        # boxes are replayed by the independent 192-bit MPFR checker.  This
        # directly exercises every branch of the directed multiplication
        # fast path rather than relying only on the pseudorandom fixture.
        sign_input = root / "q17-sign-edges.in"
        sign_gpu = root / "q17-sign-edges.gpu"
        write_synthetic_input(sign_input, q=17, t_index=0)
        sign_cases = (
            (1.0, 2.0, 3.0, 4.0),
            (1.0, 2.0, -3.0, 4.0),
            (-2.0, -1.0, 3.0, 4.0),
            (1.0, 2.0, -4.0, -3.0),
            (-2.0, -1.0, -4.0, -3.0),
            (-1.0, 2.0, 3.0, 4.0),
            (-1.0, 2.0, -4.0, -3.0),
            (-2.0, -1.0, -3.0, 4.0),
            (-1.0, 2.0, -3.0, 4.0),
            (-0.0, 0.0, -0.0, 0.0),
            (
                -math.ldexp(1.0, -1074),
                math.ldexp(1.0, -1074),
                -math.ldexp(1.0, -1022),
                math.ldexp(1.0, -1022),
            ),
        )
        with sign_input.open("r+b") as target:
            for index in range(16):
                target.seek(INPUT_HEADER.size + index * COMPLEX_INTERVAL.size)
                target.write(COMPLEX_INTERVAL.pack(*sign_cases[index % len(sign_cases)]))
        subprocess.run(
            [str(runner), str(sign_input), str(sign_gpu), str(args.device), "1"],
            check=True,
        )
        subprocess.run(
            [str(checker), "verify", str(sign_input), str(sign_gpu), "192"],
            check=True,
        )

        malformed_input = root / "q17-reversed.in"
        shutil.copyfile(sign_input, malformed_input)
        with malformed_input.open("r+b") as target:
            target.seek(INPUT_HEADER.size)
            target.write(struct.pack("<dd", 2.0, 1.0))
        rejected_input = subprocess.run(
            [
                str(runner),
                str(malformed_input),
                str(root / "q17-reversed.gpu"),
                str(args.device),
                "1",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected_input.returncode == 0:
            raise RuntimeError("CUDA runner accepted a reversed input interval")

        # Finite input endpoints can still overflow during a transform.  The
        # ordinary file-output path must fail before atomically publishing any
        # non-finite or reversed result.
        overflow_input = root / "q5-overflow.in"
        overflow_output = root / "q5-overflow.gpu"
        write_synthetic_input(overflow_input, q=5, t_index=0)
        maximum = sys.float_info.max
        with overflow_input.open("r+b") as target:
            for index in range(4):
                target.seek(
                    INPUT_HEADER.size + index * COMPLEX_INTERVAL.size
                )
                target.write(
                    COMPLEX_INTERVAL.pack(
                        maximum, maximum, maximum, maximum
                    )
                )
        rejected_overflow = subprocess.run(
            [
                str(runner),
                str(overflow_input),
                str(overflow_output),
                str(args.device),
                "1",
            ],
            check=False,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if (
            rejected_overflow.returncode == 0
            or overflow_output.exists()
            or "malformed interval" not in rejected_overflow.stderr
        ):
            raise RuntimeError(
                "ordinary CUDA output did not fail closed on overflow"
            )

        # Reuse the small standalone fixture so this exact seam can also be
        # invoked directly under Compute Sanitizer without running the rest of
        # this comparatively large allchars test.
        handoff_fixture = prepare_fixture(root / "resident-handoff")
        run_fixture(handoff_fixture, runner, args.device)

        # Persistent per-q mode prepares chirps/twiddles once, streams two
        # batches directly into a consumer, and retains only compact receipts.
        stream_root = root / "stream"
        stream_root.mkdir()
        write_synthetic_input(stream_root / "a.in", q=7, t_index=0,
                              batch_count=3)
        write_synthetic_input(stream_root / "b.in", q=7, t_index=3,
                              batch_count=2)
        (stream_root / "manifest.tsv").write_text(
            "TGDAFF_STREAM_V1\n"
            "a.in\treceipts/a.json\n"
            "b.in\treceipts/b.json\n",
            encoding="ascii",
        )
        consumer = ROOT / "tests" / "tg_dirichlet_allchars_stream_consumer.py"
        subprocess.run(
            [
                str(runner),
                "--stream",
                str(stream_root / "manifest.tsv"),
                str(consumer),
                str(stream_root / "summary.json"),
                str(args.device),
            ],
            check=True,
        )
        summary = json.loads((stream_root / "summary.json").read_text("ascii"))
        if summary["batch_files"] != 2 or summary["value_count"] != 30:
            raise RuntimeError("persistent stream coverage changed")
        leaf_a = hashlib.sha256(
            (stream_root / "receipts" / "a.json").read_bytes()
        ).digest()
        leaf_b = hashlib.sha256(
            (stream_root / "receipts" / "b.json").read_bytes()
        ).digest()
        if summary["receipt_merkle_sha256"] != hashlib.sha256(
            leaf_a + leaf_b
        ).hexdigest():
            raise RuntimeError("persistent stream receipt Merkle root changed")
        if list(stream_root.glob("*.out")):
            raise RuntimeError("persistent stream materialized transformed output")

        # Rolling mode also bounds the input side: a producer creates one
        # reusable batch, the runner deletes it after loading, and consumer
        # receipts are folded into the Merkle root and removed immediately.
        rolling_root = root / "rolling"
        rolling_root.mkdir()
        (rolling_root / "plan.tsv").write_text(
            "TGDAFF_ROLLING_V1\n7\t0\t64\t5\t7\t3\n",
            encoding="ascii",
        )
        producer = ROOT / "tests" / "tg_dirichlet_allchars_rolling_producer.py"
        subprocess.run(
            [
                str(runner),
                "--rolling",
                str(rolling_root / "plan.tsv"),
                str(producer),
                str(consumer),
                str(rolling_root / "work"),
                str(rolling_root / "summary.json"),
                str(args.device),
            ],
            check=True,
        )
        rolling = json.loads((rolling_root / "summary.json").read_text("ascii"))
        if (
            rolling["batches"] != 3
            or rolling["slices"] != 7
            or rolling["value_count"] != 42
            or rolling["radix2_butterflies"] != 544
            or rolling["retained_input_batches"] != 0
            or rolling["retained_output_batches"] != 0
            or rolling["retained_consumer_receipts"] != 0
        ):
            raise RuntimeError("rolling bounded-storage coverage changed")
        if list((rolling_root / "work").iterdir()):
            raise RuntimeError("rolling mode retained a transient artifact")

        # Source-scale framing keeps the producer, one q-specific CUDA plan,
        # and the downstream consumer alive.  It accepts concatenated
        # self-delimiting frames on stdin and emits only concatenated output
        # frames on stdout, so there is no per-batch fork or retained payload.
        framed_root = root / "framed"
        framed_root.mkdir()
        framed_a = framed_root / "a.in"
        framed_b = framed_root / "b.in"
        write_synthetic_input(framed_a, q=7, t_index=0, batch_count=3)
        write_synthetic_input(framed_b, q=7, t_index=3, batch_count=2)
        framed_input = framed_a.read_bytes() + framed_b.read_bytes()
        completed = subprocess.run(
            [
                str(runner),
                "--framed-service",
                "7",
                "3",
                str(framed_root / "summary.json"),
                str(args.device),
            ],
            input=framed_input,
            stdout=subprocess.PIPE,
            check=True,
        )
        framed_summary = json.loads(
            (framed_root / "summary.json").read_text("ascii")
        )
        if (
            framed_summary["frame_count"] != 2
            or framed_summary["slice_count"] != 5
            or framed_summary["value_count"] != 30
            or framed_summary["retained_input_frames"] != 0
            or framed_summary["retained_output_frames"] != 0
            or framed_summary["input_stream_sha256"]
            != hashlib.sha256(framed_input).hexdigest()
            or framed_summary["output_stream_sha256"]
            != hashlib.sha256(completed.stdout).hexdigest()
        ):
            raise RuntimeError("persistent framed-service coverage changed")
        offset = 0
        for index, input_path in enumerate((framed_a, framed_b)):
            header = OUTPUT_HEADER.unpack_from(completed.stdout, offset)
            frame_size = OUTPUT_HEADER.size + header[6] * COMPLEX_INTERVAL.size
            frame_path = framed_root / f"{index}.out"
            frame_path.write_bytes(completed.stdout[offset : offset + frame_size])
            subprocess.run(
                [str(checker), "verify", str(input_path), str(frame_path), "192"],
                check=True,
            )
            offset += frame_size
        if offset != len(completed.stdout):
            raise RuntimeError("framed service emitted trailing bytes")

        # Cross-q mode releases q-specific workspaces while retaining an
        # immutable convolution-root pool and a separate order-specific
        # chirp/kernel LRU inside one exact 512-MiB budget.  The cached payload
        # must be byte-identical to the ordinary one-q runner, then
        # independently contained by MPFR.
        multiq_root = root / "multiq"
        multiq_root.mkdir()
        multiq_inputs = [root / f"q{q}.in" for q in (5, 7, 8, 15)]
        multiq_input = b"".join(path.read_bytes() for path in multiq_inputs)
        multiq_summary_path = multiq_root / "summary.json"
        multiq_completed = subprocess.run(
            [
                str(runner),
                "--multiq-framed-service",
                "1",
                "512",
                str(multiq_summary_path),
                str(args.device),
            ],
            input=multiq_input,
            stdout=subprocess.PIPE,
            check=True,
        )
        multiq_summary = json.loads(
            multiq_summary_path.read_text("ascii")
        )
        validate_multiq_framed_summary(
            multiq_summary,
            input_stream=multiq_input,
            output_stream=multiq_completed.stdout,
        )
        if (
            multiq_summary["modulus_count"] != 4
            or multiq_summary["cache_capacity_bytes"] != 536_870_912
            or multiq_summary["root_pool_reserved_bytes"] != 134_216_256
            or multiq_summary["order_cache_capacity_bytes"] != 402_654_656
            or multiq_summary["root_pool_catalog_sha256"]
            != (
                "1bc2d74e4a76b5981a8b56c9b3c8ac5"
                "17931a952c8c2166dcfbcad1c9373b728"
            )
            or multiq_summary["order_cache_accesses"] != 6
            or multiq_summary["order_cache_hits"] != 3
            or multiq_summary["order_cache_misses"] != 3
            or multiq_summary["order_cache_uncached_misses"] != 0
            or multiq_summary["root_pool_accesses"] != 3
            or multiq_summary["root_pool_hits"] != 0
            or multiq_summary["root_pool_misses"] != 3
            or multiq_summary["root_pool_retained_bytes"] != 1_600
            or multiq_summary["root_pool_prepared_enclosures"] != 50
            or multiq_summary["order_cache_retained_bytes"] != 1_280
            or multiq_summary["order_cache_prepared_enclosures"] != 24
            or multiq_summary["total_prepared_enclosures"] != 74
        ):
            raise RuntimeError("cross-q split-cache KAT counters changed")
        offset = 0
        for q, input_path in zip((5, 7, 8, 15), multiq_inputs):
            header = OUTPUT_HEADER.unpack_from(multiq_completed.stdout, offset)
            frame_size = OUTPUT_HEADER.size + header[6] * COMPLEX_INTERVAL.size
            raw = multiq_completed.stdout[offset : offset + frame_size]
            cached_path = multiq_root / f"q{q}.cached"
            cached_path.write_bytes(raw)
            subprocess.run(
                [str(checker), "verify", str(input_path), str(cached_path), "192"],
                check=True,
            )
            ordinary = (root / f"q{q}.gpu").read_bytes()
            if raw[OUTPUT_HEADER.size :] != ordinary[OUTPUT_HEADER.size :]:
                raise RuntimeError(
                    "cached and uncached directed interval payloads differ"
                )
            offset += frame_size
        if offset != len(multiq_completed.stdout):
            raise RuntimeError("multi-q service emitted trailing bytes")

        tampered_summary = dict(multiq_summary)
        tampered_summary["order_cache_hits"] += 1
        try:
            validate_multiq_framed_summary(
                tampered_summary,
                input_stream=multiq_input,
                output_stream=multiq_completed.stdout,
            )
        except DirichletAllCharsStageError:
            pass
        else:
            raise RuntimeError(
                "independent split-cache replay accepted tampered order stats"
            )
        tampered_root_summary = dict(multiq_summary)
        tampered_root_summary["root_pool_prepared_enclosures"] += 1
        try:
            validate_multiq_framed_summary(
                tampered_root_summary,
                input_stream=multiq_input,
                output_stream=multiq_completed.stdout,
            )
        except DirichletAllCharsStageError:
            pass
        else:
            raise RuntimeError(
                "independent split-cache replay accepted tampered root stats"
            )
        tampered_catalog_summary = dict(multiq_summary)
        tampered_catalog_summary["root_pool_catalog_sha256"] = "0" * 64
        try:
            validate_multiq_framed_summary(
                tampered_catalog_summary,
                input_stream=multiq_input,
                output_stream=multiq_completed.stdout,
            )
        except DirichletAllCharsStageError:
            pass
        else:
            raise RuntimeError(
                "independent split-cache replay accepted tampered root catalog"
            )

        rejected_multiq = subprocess.run(
            [
                str(runner),
                "--multiq-framed-service",
                "1",
                "512",
                str(multiq_root / "rejected.json"),
                str(args.device),
            ],
            input=(root / "q7.in").read_bytes()
            + (root / "q5.in").read_bytes(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if rejected_multiq.returncode == 0:
            raise RuntimeError("multi-q cache accepted a decreasing q roster")
        wrong_budget = subprocess.run(
            [
                str(runner),
                "--multiq-framed-service",
                "1",
                "511",
                str(multiq_root / "wrong-budget.json"),
                str(args.device),
            ],
            input=(root / "q5.in").read_bytes(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if wrong_budget.returncode == 0:
            raise RuntimeError("multi-q split cache accepted a non-512-MiB cap")

        # The optimized primitive-V2 service deliberately gives up monotone q
        # traversal only through an explicit TGDQORD1 manifest.  Its
        # component-signature permutation must be checked independently,
        # cover every listed row exactly, and produce the same interval bytes
        # as the ordinary one-q runner.
        scheduled_root = root / "scheduled-multiq"
        scheduled_root.mkdir()
        source_qs = (10_001, 10_080, 11_088, 18_480)
        scheduled_inputs: dict[int, Path] = {}
        ordinary_outputs: dict[int, Path] = {}
        for q in source_qs:
            input_path = scheduled_root / f"q{q}.in"
            ordinary_path = scheduled_root / f"q{q}.ordinary"
            write_synthetic_input(
                input_path, q=q, t_index=0, batch_count=1
            )
            subprocess.run(
                [
                    str(runner),
                    str(input_path),
                    str(ordinary_path),
                    str(args.device),
                    "1",
                ],
                check=True,
            )
            subprocess.run(
                [
                    str(checker),
                    "verify",
                    str(input_path),
                    str(ordinary_path),
                    "192",
                ],
                check=True,
            )
            scheduled_inputs[q] = input_path
            ordinary_outputs[q] = ordinary_path
        schedule_path = scheduled_root / "schedule.bin"
        write_bounded_schedule_manifest(
            schedule_path,
            tuple(ScheduleRecord(q, 1) for q in source_qs),
        )
        schedule = parse_schedule_manifest(schedule_path)
        execution_qs = tuple(
            record.q for record in schedule.execution_records
        )
        if execution_qs != (10_080, 18_480, 11_088, 10_001):
            raise RuntimeError("bounded q-order KAT permutation changed")
        scheduled_input = b"".join(
            scheduled_inputs[q].read_bytes() for q in execution_qs
        )
        scheduled_summary_path = scheduled_root / "summary.json"
        scheduled_completed = subprocess.run(
            [
                str(runner),
                "--bounded-scheduled-multiq-framed-service",
                "1",
                "512",
                str(schedule_path),
                str(scheduled_summary_path),
                str(args.device),
            ],
            input=scheduled_input,
            stdout=subprocess.PIPE,
            check=True,
        )
        scheduled_summary = json.loads(
            scheduled_summary_path.read_text("ascii")
        )
        validate_scheduled_multiq_framed_summary(
            scheduled_summary,
            manifest=schedule_path,
            input_stream=scheduled_input,
            output_stream=scheduled_completed.stdout,
        )
        production_with_bounded_manifest = subprocess.run(
            [
                str(runner),
                "--scheduled-multiq-framed-service",
                "1",
                "512",
                str(schedule_path),
                str(scheduled_root / "wrong-class-summary.json"),
                str(args.device),
            ],
            input=scheduled_input,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if production_with_bounded_manifest.returncode == 0:
            raise RuntimeError(
                "production scheduled mode accepted a bounded KAT manifest"
            )
        offset = 0
        for q in execution_qs:
            header = OUTPUT_HEADER.unpack_from(
                scheduled_completed.stdout, offset
            )
            frame_size = (
                OUTPUT_HEADER.size + header[6] * COMPLEX_INTERVAL.size
            )
            raw = scheduled_completed.stdout[offset : offset + frame_size]
            cached_path = scheduled_root / f"q{q}.scheduled"
            cached_path.write_bytes(raw)
            subprocess.run(
                [
                    str(checker),
                    "verify",
                    str(scheduled_inputs[q]),
                    str(cached_path),
                    "192",
                ],
                check=True,
            )
            if (
                raw[OUTPUT_HEADER.size :]
                != ordinary_outputs[q].read_bytes()[OUTPUT_HEADER.size :]
            ):
                raise RuntimeError(
                    "scheduled and ordinary directed payloads differ"
                )
            offset += frame_size
        if offset != len(scheduled_completed.stdout):
            raise RuntimeError("scheduled service emitted trailing bytes")

        wrong_order = subprocess.run(
            [
                str(runner),
                "--bounded-scheduled-multiq-framed-service",
                "1",
                "512",
                str(schedule_path),
                str(scheduled_root / "wrong-order-summary.json"),
                str(args.device),
            ],
            input=b"".join(
                scheduled_inputs[q].read_bytes() for q in source_qs
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if wrong_order.returncode == 0:
            raise RuntimeError(
                "scheduled service accepted source-order input"
            )
        incomplete_schedule_path = (
            scheduled_root / "incomplete-schedule.bin"
        )
        write_bounded_schedule_manifest(
            incomplete_schedule_path,
            tuple(
                ScheduleRecord(q, 2 if q == 10_080 else 1)
                for q in source_qs
            ),
        )
        incomplete_result = subprocess.run(
            [
                str(runner),
                "--bounded-scheduled-multiq-framed-service",
                "1",
                "512",
                str(incomplete_schedule_path),
                str(scheduled_root / "incomplete-summary.json"),
                str(args.device),
            ],
            input=scheduled_input,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if incomplete_result.returncode == 0:
            raise RuntimeError(
                "scheduled service accepted incomplete q row coverage"
            )
        forged_schedule = scheduled_root / "forged-schedule.bin"
        forged_raw = bytearray(schedule_path.read_bytes())
        forged_raw[-1] ^= 1
        forged_schedule.write_bytes(forged_raw)
        forged_result = subprocess.run(
            [
                str(runner),
                "--bounded-scheduled-multiq-framed-service",
                "1",
                "512",
                str(forged_schedule),
                str(scheduled_root / "forged-summary.json"),
                str(args.device),
            ],
            input=scheduled_input,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if forged_result.returncode == 0:
            raise RuntimeError(
                "scheduled service accepted a tampered q-order manifest"
            )
        tampered_scheduled_summary = dict(scheduled_summary)
        tampered_scheduled_summary["schedule_execution_order_sha256"] = (
            "0" * 64
        )
        try:
            validate_scheduled_multiq_framed_summary(
                tampered_scheduled_summary,
                manifest=schedule_path,
                input_stream=scheduled_input,
                output_stream=scheduled_completed.stdout,
            )
        except DirichletAllCharsQSchedulerError:
            pass
        else:
            raise RuntimeError(
                "scheduled replay accepted a forged permutation digest"
            )

        # A source phase is a partial t intersection of the same immutable
        # TGDQORD1, not a second roster.  The persistent phase service skips
        # inactive q values, retains the parent's execution permutation, and
        # requires the exact positive t offset for every active q.
        phase_root = scheduled_root / "phase"
        phase_root.mkdir()
        phase_counts = {
            10_001: 3,
            10_080: 5,
            11_088: 4,
            18_480: 2,
        }
        phase_schedule_path = phase_root / "schedule.bin"
        write_bounded_schedule_manifest(
            phase_schedule_path,
            tuple(
                ScheduleRecord(q, phase_counts[q])
                for q in source_qs
            ),
        )
        phase_schedule = parse_schedule_manifest(phase_schedule_path)
        phase_plan_sha256 = "12" * 32
        projection = phase_schedule_projection(
            phase_schedule_path,
            phase_plan_sha256=phase_plan_sha256,
            first_t_index=2,
            t_index_stop_exclusive=5,
        )
        if [
            (record.q, record.t_index_count)
            for record in projection.active_records
        ] != [(10_080, 3), (11_088, 2), (10_001, 1)]:
            raise RuntimeError("phase active-q projection changed")
        phase_inputs: dict[int, Path] = {}
        phase_ordinary: dict[int, Path] = {}
        for record in projection.active_records:
            input_path = phase_root / f"q{record.q}.in"
            ordinary_path = phase_root / f"q{record.q}.ordinary"
            write_synthetic_input(
                input_path,
                q=record.q,
                t_index=record.first_t_index,
                batch_count=record.t_index_count,
            )
            subprocess.run(
                [
                    str(runner),
                    str(input_path),
                    str(ordinary_path),
                    str(args.device),
                    "1",
                ],
                check=True,
            )
            phase_inputs[record.q] = input_path
            phase_ordinary[record.q] = ordinary_path
        phase_input = b"".join(
            phase_inputs[record.q].read_bytes()
            for record in projection.active_records
        )
        phase_summary_path = phase_root / "summary.json"
        phase_completed = subprocess.run(
            [
                str(runner),
                "--bounded-phase-scheduled-multiq-framed-service",
                "3",
                "512",
                str(phase_schedule_path),
                phase_plan_sha256,
                "2",
                "5",
                "0",
                str(phase_schedule.q_count),
                str(phase_summary_path),
                str(args.device),
            ],
            input=phase_input,
            stdout=subprocess.PIPE,
            check=True,
        )
        phase_summary = json.loads(phase_summary_path.read_text("ascii"))
        validate_phase_scheduled_multiq_framed_summary_commitments(
            phase_summary,
            projection=projection,
            maximum_batch_count=3,
            input_stream_sha256=hashlib.sha256(phase_input).hexdigest(),
            output_stream_sha256=hashlib.sha256(
                phase_completed.stdout
            ).hexdigest(),
        )
        offset = 0
        for record in projection.active_records:
            header = OUTPUT_HEADER.unpack_from(phase_completed.stdout, offset)
            frame_size = (
                OUTPUT_HEADER.size + header[6] * COMPLEX_INTERVAL.size
            )
            raw = phase_completed.stdout[offset : offset + frame_size]
            if (
                raw[OUTPUT_HEADER.size :]
                != phase_ordinary[record.q].read_bytes()[OUTPUT_HEADER.size :]
            ):
                raise RuntimeError(
                    "phase scheduled and ordinary directed payloads differ"
                )
            offset += frame_size
        if offset != len(phase_completed.stdout):
            raise RuntimeError("phase scheduled service emitted trailing bytes")

        inactive_q_input = (
            phase_inputs[10_080].read_bytes()
            + scheduled_inputs[18_480].read_bytes()
            + phase_inputs[11_088].read_bytes()
            + phase_inputs[10_001].read_bytes()
        )
        inactive_q_result = subprocess.run(
            [
                str(runner),
                "--bounded-phase-scheduled-multiq-framed-service",
                "3",
                "512",
                str(phase_schedule_path),
                phase_plan_sha256,
                "2",
                "5",
                "0",
                str(phase_schedule.q_count),
                str(phase_root / "inactive-q-summary.json"),
                str(args.device),
            ],
            input=inactive_q_input,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if inactive_q_result.returncode == 0:
            raise RuntimeError(
                "phase scheduled service accepted an inactive modulus"
            )

        wrong_first_result = subprocess.run(
            [
                str(runner),
                "--bounded-phase-scheduled-multiq-framed-service",
                "3",
                "512",
                str(phase_schedule_path),
                phase_plan_sha256,
                "2",
                "5",
                "0",
                str(phase_schedule.q_count),
                str(phase_root / "wrong-first-summary.json"),
                str(args.device),
            ],
            input=(
                scheduled_inputs[10_080].read_bytes()
                + phase_inputs[11_088].read_bytes()
                + phase_inputs[10_001].read_bytes()
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if wrong_first_result.returncode == 0:
            raise RuntimeError(
                "phase scheduled service accepted a t=0 phase substitution"
            )
        hostile_phase_summary = dict(phase_summary)
        hostile_phase_summary["phase_schedule_sha256"] = "0" * 64
        try:
            validate_phase_scheduled_multiq_framed_summary_commitments(
                hostile_phase_summary,
                projection=projection,
                maximum_batch_count=3,
                input_stream_sha256=hashlib.sha256(phase_input).hexdigest(),
                output_stream_sha256=hashlib.sha256(
                    phase_completed.stdout
                ).hexdigest(),
            )
        except DirichletAllCharsQSchedulerError:
            pass
        else:
            raise RuntimeError(
                "phase scheduled replay accepted a forged phase commitment"
            )

        discontinuous = framed_a.read_bytes() + (
            root / "q7.in"
        ).read_bytes()
        rejected_framing = subprocess.run(
            [
                str(runner),
                "--framed-service",
                "7",
                "3",
                str(framed_root / "rejected-summary.json"),
                str(args.device),
            ],
            input=discontinuous,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if rejected_framing.returncode == 0:
            raise RuntimeError("framed service accepted a discontinuous stream")

        forged = root / "forged.bin"
        shutil.copyfile(root / "q7.gpu", forged)
        with forged.open("r+b") as output:
            # Shrink the lower bound of coefficient zero upward to +infinity.
            output.seek(OUTPUT_HEADER.size)
            output.write(struct.pack("<d", math.inf))
        rejected = subprocess.run(
            [str(checker), "verify", str(root / "q7.in"), str(forged), "192"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected.returncode == 0:
            raise RuntimeError("MPFR checker accepted a forged output")
        if COMPLEX_INTERVAL.size != 32:
            raise RuntimeError("interval encoding changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
