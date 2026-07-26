#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent known answers for the native Helfgott--Platt ladder producer."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_campaign import (
    SOURCE_ENDPOINT,
    SOURCE_MAXIMUM_GAP,
    SOURCE_PROTH_WITNESSES,
    SOURCE_RANGE_WIDTH,
)
from tg_verifier.goldbach_native_ladder import NativeRun, invoke_native_segment


COVERAGE_STEP = SOURCE_MAXIMUM_GAP - 2
SOURCE_HEIGHT_ANCHOR = 8_875_676_131_227_236_209_687_340_777_473


def jacobi_symbol(numerator: int, denominator: int) -> int:
    """Small independent Jacobi implementation used only by this KAT."""

    if denominator <= 0 or denominator % 2 == 0:
        raise ValueError("Jacobi denominator must be positive and odd")
    numerator %= denominator
    result = 1
    while numerator:
        while numerator % 2 == 0:
            numerator //= 2
            if denominator % 8 in (3, 5):
                result = -result
        numerator, denominator = denominator, numerator
        if numerator % 4 == denominator % 4 == 3:
            result = -result
        numerator %= denominator
    return result if denominator == 1 else 0


def expected_largest(
    lower: int, upper_inclusive: int, *, proth_exponent: int = 52
) -> tuple[int, int] | None:
    proth_power = 1 << proth_exponent
    maximum_k = (upper_inclusive - 1) // proth_power
    excluded_k = (lower - 1) // proth_power
    for k in range(maximum_k, excluded_k, -1):
        number = k * proth_power + 1
        for witness in SOURCE_PROTH_WITNESSES:
            if jacobi_symbol(witness, number) == -1:
                if pow(witness, (number - 1) // 2, number) == number - 1:
                    return number, witness
                break
    return None


def expected_ladder(
    anchor: int,
    target: int,
    *,
    coverage_step: int = COVERAGE_STEP,
    proth_exponent: int = 52,
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    current = anchor
    while target - current > coverage_step:
        rung = expected_largest(
            current,
            current + coverage_step,
            proth_exponent=proth_exponent,
        )
        if rung is None:
            raise AssertionError("known-answer segment unexpectedly needs a general prime")
        result.append(rung)
        current = rung[0]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    args = parser.parse_args()

    if not SOURCE_ENDPOINT - SOURCE_RANGE_WIDTH < SOURCE_HEIGHT_ANCHOR < SOURCE_ENDPOINT:
        raise AssertionError("source-height KAT anchor left the terminal source range")
    target = SOURCE_HEIGHT_ANCHOR + 256 * COVERAGE_STEP
    expected = expected_ladder(SOURCE_HEIGHT_ANCHOR, target)
    with tempfile.TemporaryDirectory() as temporary:
        parent = Path(temporary)
        with invoke_native_segment(
            args.runner,
            anchor_number=SOURCE_HEIGHT_ANCHOR,
            target_number=target,
            coverage_step=COVERAGE_STEP,
            sieve_block_candidates=131_072,
            temporary_parent=parent,
        ) as first:
            actual = [
                (rung.number, int(rung.witness or 0))
                for rung in first.checked_rungs()
            ]
            if actual != expected:
                raise AssertionError("native rung stream differs from independent search")
            first_hash = first.protocol_sha256
            protocol_copy = parent / "tampered.tgnp"
            raw = bytearray(first.path.read_bytes())
            raw[-1] ^= 1
            protocol_copy.write_bytes(raw)
            tampered = NativeRun(
                protocol_copy,
                first.header,
                first.protocol_sha256,
                first.report,
                first.runner_sha256,
            )
            try:
                list(tampered.checked_rungs())
            except Exception:
                pass
            else:
                raise AssertionError("independent replay accepted a changed witness byte")

        with invoke_native_segment(
            args.runner,
            anchor_number=SOURCE_HEIGHT_ANCHOR,
            target_number=target,
            coverage_step=COVERAGE_STEP,
            sieve_block_candidates=131_072,
            temporary_parent=parent,
        ) as second:
            list(second.checked_rungs())
            if second.protocol_sha256 != first_hash:
                raise AssertionError("deterministic native protocol changed between runs")

        # A sub-grid step contains no k*2^52+1 candidate.  The producer must
        # emit an exact general-prime obligation, not a probable-prime record.
        with invoke_native_segment(
            args.runner,
            anchor_number=SOURCE_HEIGHT_ANCHOR,
            target_number=SOURCE_HEIGHT_ANCHOR + 10,
            coverage_step=1,
            sieve_block_candidates=1024,
            temporary_parent=parent,
        ) as hole:
            if hole.header.complete or list(hole.checked_rungs()):
                raise AssertionError("native producer did not fail closed on a Proth gap")
            if (
                hole.header.hole_lower_exclusive != SOURCE_HEIGHT_ANCHOR
                or hole.header.hole_upper_inclusive != SOURCE_HEIGHT_ANCHOR + 1
            ):
                raise AssertionError("native producer reported the wrong gap obligation")

        # The lowered 10^27 campaign commits n=45.  Check the distinct wire
        # exponent and generic (non-proth52) replay at source height.
        lowered_anchor = 999_999_999_000_000_000_000_000_000
        lowered_step = 31_250_000_000_000_000 - 2
        lowered_target = lowered_anchor + 3 * lowered_step
        lowered_expected = expected_ladder(
            lowered_anchor,
            lowered_target,
            coverage_step=lowered_step,
            proth_exponent=45,
        )
        with invoke_native_segment(
            args.runner,
            anchor_number=lowered_anchor,
            target_number=lowered_target,
            coverage_step=lowered_step,
            proth_exponent=45,
            sieve_block_candidates=131_072,
            temporary_parent=parent,
        ) as lowered:
            lowered_rungs = list(lowered.checked_rungs())
            if lowered.header.proth_exponent != 45:
                raise AssertionError("native protocol did not bind n=45")
            if any(rung.certificate_kind != "proth" for rung in lowered_rungs):
                raise AssertionError("n=45 evidence was mislabeled proth52")
            if [
                (rung.number, int(rung.witness or 0)) for rung in lowered_rungs
            ] != lowered_expected:
                raise AssertionError("n=45 native stream differs from independent search")

    print(
        "native Goldbach ladder known answers passed "
        f"({len(expected)} source-height rungs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
