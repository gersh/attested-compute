#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent bounded qualification of the one-pass CH25 psi guard."""

from __future__ import annotations

import argparse
import hashlib
from math import isqrt
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.finite_campaigns import prime_power_events  # noqa: E402
from tg_verifier.psi_two_pass_qualification import (  # noqa: E402
    _CRlibmQ64,
    _lower_guard,
    _upper_guard,
)


SCALE = 1 << 64
FRACTION_BITS = 16
Q64_SHIFT = 64 - FRACTION_BITS
UPPER_NUMERATOR = 19_764_819
UPPER_DENOMINATOR = 25_000_000
SOURCE_LIMIT = 10_000_000_000_000
EVENT_DOMAIN = b"sparkinterval.tg.psi-prime-power-events.v1\0"
ROW_DOMAIN = b"sparkinterval.tg.psi-prime-power-rows.v1\0"
COMMON_FIELDS = (
    "delta",
    "event_sha256",
    "row_sha256",
    "prime_power_events",
    "prime_events",
    "higher_power_events",
)
AFFINE_WIRE_FIXTURE = {
    "delta": [
        1_734_829_787_580_318_666_752,
        1_734_829_787_580_318_957_568,
    ],
    "event_sha256": (
        "6a39e9a90d7c9bead2b83dd3b4acb890a81fc9ab4faa3728c0a065da4e9720c0"
    ),
    "row_sha256": (
        "ca6eca43ef27a1eaf09e53e91ed6e19e34f8348eb808eec28464b03f69979288"
    ),
    "prime_power_events": 35,
    "prime_events": 25,
    "higher_power_events": 10,
    "allowed_incoming_q64": {
        "lower_min": 0,
        "upper_max": 44_731_675_089_009_430_431,
        "predicate": "lower_min<=lower<=upper<=upper_max",
    },
    "guard_witnesses": {
        "lower_min": {
            "event_index": 0,
            "value": 2,
            "prefix_delta_q64": 0,
            "radius_q64": 36_893_488_147_419_103_232,
            "strict": False,
            "kind": "lower_left_limit",
        },
        "upper_max": {
            "event_index": 0,
            "value": 2,
            "prefix_delta_q64": 12_786_308_645_202_657_280,
            "radius_q64": 20_624_495_586_792_984_479,
            "kind": "upper_post_jump",
        },
    },
    "terminal_strict_lower_constrained": False,
}


def invoke(
    runner: Path,
    mode: str,
    lower: int,
    upper: int,
    incoming: tuple[int, int] | None = None,
) -> dict[str, Any]:
    command = [
        str(runner),
        "--mode",
        mode,
        "--lower",
        str(lower),
        "--upper",
        str(upper),
        "--sieve-size-kib",
        "64",
    ]
    if incoming is not None:
        command += [
            "--incoming-lower",
            str(incoming[0]),
            "--incoming-upper",
            str(incoming[1]),
        ]
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"{mode} worker failed ({completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    report = json.loads(completed.stdout)
    if not isinstance(report, dict):
        raise AssertionError(f"{mode} worker output is not an object")
    return report


def lower_radius(value: int, *, strict: bool) -> int:
    radicand = (2 * value) << (2 * FRACTION_BITS)
    root = isqrt(radicand)
    radius = root << Q64_SHIFT
    if strict and root * root == radicand:
        radius -= 1
    return radius


def upper_radius(value: int) -> int:
    root = isqrt(value << (2 * FRACTION_BITS))
    return (UPPER_NUMERATOR * root * (1 << Q64_SHIFT)) // UPPER_DENOMINATOR


def literal_affine(
    lower: int, upper: int, crlibm: _CRlibmQ64
) -> tuple[dict[str, Any], tuple[tuple[int, int, int], ...]]:
    events = prime_power_events(lower, upper + 1, segment_size=31_337)
    event_digest = hashlib.sha256(EVENT_DOMAIN)
    row_digest = hashlib.sha256(ROW_DOMAIN)
    bounds: dict[int, tuple[int, int]] = {}
    delta_lower = 0
    delta_upper = 0
    minimum_lower = 0
    maximum_upper = (1 << 128) - 1
    lower_witness: dict[str, Any] | None = None
    upper_witness: dict[str, Any] | None = None
    roster: list[tuple[int, int, int]] = []
    prime_count = 0
    higher_count = 0
    for index, event in enumerate(events):
        if event.prime not in bounds:
            bounds[event.prime] = crlibm.bounds(event.prime)
        log_lower, log_upper = bounds[event.prime]
        structural = (
            event.value.to_bytes(8, "big")
            + event.prime.to_bytes(8, "big")
            + event.exponent.to_bytes(4, "big")
        )
        event_digest.update(structural)
        row_digest.update(structural)
        row_digest.update(log_lower.to_bytes(16, "big"))
        row_digest.update(log_upper.to_bytes(16, "big"))
        radius = lower_radius(event.value, strict=False)
        required = max(
            0, event.value * SCALE - radius - delta_lower
        )
        if lower_witness is None or required > minimum_lower:
            minimum_lower = required
            lower_witness = {
                "event_index": index,
                "value": event.value,
                "prefix_delta_q64": delta_lower,
                "radius_q64": radius,
                "strict": False,
                "kind": "lower_left_limit",
            }
        delta_lower += log_lower
        delta_upper += log_upper
        radius = upper_radius(event.value)
        allowed = event.value * SCALE + radius - delta_upper
        if upper_witness is None or allowed < maximum_upper:
            maximum_upper = allowed
            upper_witness = {
                "event_index": index,
                "value": event.value,
                "prefix_delta_q64": delta_upper,
                "radius_q64": radius,
                "kind": "upper_post_jump",
            }
        if event.exponent == 1:
            prime_count += 1
        else:
            higher_count += 1
        roster.append((event.value, log_lower, log_upper))
    terminal = upper == SOURCE_LIMIT
    if terminal:
        radius = lower_radius(SOURCE_LIMIT, strict=True)
        required = max(
            0, SOURCE_LIMIT * SCALE - radius - delta_lower
        )
        if lower_witness is None or required > minimum_lower:
            minimum_lower = required
            lower_witness = {
                "event_index": len(events),
                "value": SOURCE_LIMIT,
                "prefix_delta_q64": delta_lower,
                "radius_q64": radius,
                "strict": True,
                "kind": "terminal_strict_lower",
            }
    if lower_witness is None or upper_witness is None:
        raise AssertionError("fixture shard unexpectedly contains no events")
    return (
        {
            "delta": [delta_lower, delta_upper],
            "event_sha256": event_digest.hexdigest(),
            "row_sha256": row_digest.hexdigest(),
            "prime_power_events": len(events),
            "prime_events": prime_count,
            "higher_power_events": higher_count,
            "allowed_incoming_q64": {
                "lower_min": minimum_lower,
                "upper_max": maximum_upper,
                "predicate": "lower_min<=lower<=upper<=upper_max",
            },
            "guard_witnesses": {
                "lower_min": lower_witness,
                "upper_max": upper_witness,
            },
            "terminal_strict_lower_constrained": terminal,
        },
        tuple(roster),
    )


def check_affine_report(
    report: dict[str, Any],
    expected: dict[str, Any],
    lower: int,
    upper: int,
) -> None:
    assert report["algorithm"] == "ch25-psi-prime-power-affine-guard-v1"
    assert report["mode"] == "affine"
    assert report["classification"] == "source-scale-shard-not-lean-proof"
    assert report["atom"] == "ch25-psi-1e13"
    assert report["lower"] == lower
    assert report["upper_exclusive"] == upper + 1
    assert report["work_count"] == upper - lower + 1
    assert report["scale_bits"] == 64
    assert report["sieve_size_kib"] == 64
    assert report["guard_encoding"] == (
        "independent-q64-rectangle-with-lower-le-upper-v1"
    )
    assert report["guard_derivation"] == {
        "sqrt_fraction_bits": 16,
        "lower_radius": "floor(sqrt(2*x)*2^16)*2^48",
        "upper_radius": (
            "floor(19764819*floor(sqrt(x)*2^16)*2^48/25000000)"
        ),
    }
    for field in COMMON_FIELDS + (
        "allowed_incoming_q64",
        "guard_witnesses",
        "terminal_strict_lower_constrained",
    ):
        assert report[field] == expected[field], field
    assert report["incoming_state"] is None
    assert report["outgoing_state"] is None
    assert report["accepted"] is True
    assert report["execution_attested"] is False
    assert report["lean_atom_discharged"] is False

    lower_witness = report["guard_witnesses"]["lower_min"]
    lower_radius_q64 = lower_witness["radius_q64"]
    lower_right = lower_witness["value"]
    lower_square = lower_radius_q64 * lower_radius_q64
    lower_bound = 2 * lower_right * SCALE * SCALE
    if lower_witness["strict"]:
        assert lower_square < lower_bound
    else:
        assert lower_square <= lower_bound
    assert (
        report["allowed_incoming_q64"]["lower_min"]
        + lower_witness["prefix_delta_q64"]
        + lower_radius_q64
        >= lower_right * SCALE
    )

    upper_witness = report["guard_witnesses"]["upper_max"]
    upper_radius_q64 = upper_witness["radius_q64"]
    upper_left = upper_witness["value"]
    assert (
        upper_radius_q64
        * upper_radius_q64
        * UPPER_DENOMINATOR
        * UPPER_DENOMINATOR
        <= UPPER_NUMERATOR
        * UPPER_NUMERATOR
        * upper_left
        * SCALE
        * SCALE
    )
    assert (
        report["allowed_incoming_q64"]["upper_max"]
        + upper_witness["prefix_delta_q64"]
        <= upper_left * SCALE + upper_radius_q64
    )


def check_root_chain(
    affine_runner: Path,
    two_pass_runner: Path,
    crlibm: _CRlibmQ64,
) -> None:
    ranges = ((2, 250_000), (250_001, 500_000),
              (500_001, 750_000), (750_001, 1_000_000))
    incoming = (0, 0)
    for lower, upper in ranges:
        expected, roster = literal_affine(lower, upper, crlibm)
        affine = invoke(affine_runner, "affine", lower, upper)
        check_affine_report(affine, expected, lower, upper)
        summary = invoke(two_pass_runner, "summary", lower, upper)
        verification = invoke(
            two_pass_runner, "verify", lower, upper, incoming
        )
        for field in COMMON_FIELDS:
            assert affine[field] == summary[field] == verification[field], field
        bounds = affine["allowed_incoming_q64"]
        assert bounds["lower_min"] <= incoming[0] <= incoming[1]
        assert incoming[1] <= bounds["upper_max"]
        state = incoming
        lower_fallbacks = 0
        upper_fallbacks = 0
        for value, log_lower, log_upper in roster:
            accepted, fallback = _lower_guard(value, state[0], strict=False)
            assert accepted
            lower_fallbacks += fallback
            state = (state[0] + log_lower, state[1] + log_upper)
            accepted, fallback = _upper_guard(value, state[1])
            assert accepted
            upper_fallbacks += fallback
        assert list(state) == verification["outgoing_state"]
        assert verification["exact_fallbacks"]["lower_left_limit"] == (
            lower_fallbacks
        )
        assert verification["exact_fallbacks"]["upper_post_jump"] == (
            upper_fallbacks
        )
        incoming = state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--affine-runner", required=True, type=Path)
    parser.add_argument("--two-pass-runner", required=True, type=Path)
    parser.add_argument("--crlibm-shared", type=Path)
    arguments = parser.parse_args()
    if arguments.crlibm_shared is None:
        affine = invoke(arguments.affine_runner, "affine", 2, 100)
        check_affine_report(affine, AFFINE_WIRE_FIXTURE, 2, 100)
        summary = invoke(arguments.two_pass_runner, "summary", 2, 100)
        verification = invoke(
            arguments.two_pass_runner, "verify", 2, 100, (0, 0)
        )
        for field in COMMON_FIELDS:
            assert (
                affine[field]
                == summary[field]
                == verification[field]
                == AFFINE_WIRE_FIXTURE[field]
            ), field
        print("psi affine guard binary known answers passed")
        return 0
    crlibm = _CRlibmQ64(arguments.crlibm_shared)
    try:
        expected, _ = literal_affine(2, 100, crlibm)
        fixture = invoke(arguments.affine_runner, "affine", 2, 100)
        check_affine_report(fixture, expected, 2, 100)
        assert fixture["event_sha256"] == (
            "6a39e9a90d7c9bead2b83dd3b4acb890a81fc9ab4faa3728c0a065da4e9720c0"
        )
        assert fixture["row_sha256"] == (
            "ca6eca43ef27a1eaf09e53e91ed6e19e34f8348eb808eec28464b03f69979288"
        )
        check_root_chain(
            arguments.affine_runner, arguments.two_pass_runner, crlibm
        )

        # Cover a nonzero primesieve jump and source-endpoint strict guard.
        lower = SOURCE_LIMIT - 100_000
        expected, _ = literal_affine(lower, SOURCE_LIMIT, crlibm)
        affine = invoke(
            arguments.affine_runner, "affine", lower, SOURCE_LIMIT
        )
        check_affine_report(affine, expected, lower, SOURCE_LIMIT)
        synthetic = ((lower - 1) * SCALE,) * 2
        verification = invoke(
            arguments.two_pass_runner,
            "verify",
            lower,
            SOURCE_LIMIT,
            synthetic,
        )
        for field in COMMON_FIELDS:
            assert affine[field] == verification[field], field
        bounds = affine["allowed_incoming_q64"]
        assert bounds["lower_min"] <= synthetic[0] <= synthetic[1]
        assert synthetic[1] <= bounds["upper_max"]
        assert verification["terminal_strict_lower_checked"] is True
    finally:
        crlibm.close()
    print("psi affine guard known answers passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
