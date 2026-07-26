#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Cross-check the C++ CH25 psi shard against the exact Python model."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.finite_campaigns import fixed_log_bounds, prime_power_events


ALGORITHM = "ch25-psi-prime-power-two-pass-v1"
ROW_DOMAIN = b"sparkinterval.tg.psi-prime-power-rows.v1\0"
EVENT_DOMAIN = b"sparkinterval.tg.psi-prime-power-events.v1\0"
ROW_ENCODING = (
    "u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1"
)
LEAN_WIRE_FIXTURE = {
    "lower": 2,
    "upper": 100,
    "prime_power_events": 35,
    "prime_events": 25,
    "higher_power_events": 10,
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
}


def invoke(
    runner: Path,
    mode: str,
    lower: int,
    upper: int,
    incoming: tuple[int, int] | None = None,
    *,
    expect_success: bool = True,
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
    if not expect_success:
        if completed.returncode == 0:
            raise AssertionError("runner unexpectedly accepted an invalid request")
        return {}
    if completed.returncode != 0:
        raise AssertionError(
            f"runner failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"runner did not emit one JSON object: {exc}") from exc
    if not isinstance(report, dict):
        raise AssertionError("runner report is not an object")
    return report


def python_summary(lower: int, upper: int) -> dict[str, Any]:
    events = prime_power_events(lower, upper + 1, segment_size=31_337)
    event_digest = hashlib.sha256(EVENT_DOMAIN)
    python_row_digest = hashlib.sha256(ROW_DOMAIN)
    delta_lower = 0
    delta_upper = 0
    prime_events = 0
    higher_power_events = 0
    previous = 0
    for event in events:
        if event.value <= previous:
            raise AssertionError("Python prime-power model lost strict ordering")
        log_lower, log_upper = fixed_log_bounds(event.prime, 64, 32)
        structural_row = (
            event.value.to_bytes(8, "big")
            + event.prime.to_bytes(8, "big")
            + event.exponent.to_bytes(4, "big")
        )
        event_digest.update(structural_row)
        python_row_digest.update(structural_row)
        python_row_digest.update(log_lower.to_bytes(16, "big"))
        python_row_digest.update(log_upper.to_bytes(16, "big"))
        delta_lower += log_lower
        delta_upper += log_upper
        if event.exponent == 1:
            prime_events += 1
        else:
            higher_power_events += 1
        previous = event.value
    return {
        "events": len(events),
        "prime_events": prime_events,
        "higher_power_events": higher_power_events,
        "delta": [delta_lower, delta_upper],
        "event_sha256": event_digest.hexdigest(),
        "python_row_sha256": python_row_digest.hexdigest(),
    }


def check_common(report: dict[str, Any], lower: int, upper: int, mode: str) -> None:
    assert report["algorithm"] == ALGORITHM
    assert report["atom"] == "ch25-psi-1e13"
    assert report["mode"] == mode
    assert report["lower"] == lower
    assert report["upper_exclusive"] == upper + 1
    assert report["work_count"] == upper - lower + 1
    assert report["scale_bits"] == 64
    assert report["row_encoding"] == ROW_ENCODING
    assert report["event_encoding"] == (
        "u64be-value-u64be-prime-u32be-exponent-v1"
    )
    assert report["state_components"] == ["psi_lower_q64", "psi_upper_q64"]
    assert report["accepted"] is True
    assert report["execution_attested"] is False
    assert report["lean_atom_discharged"] is False


def check_against_python(
    runner: Path, lower: int, upper: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = python_summary(lower, upper)
    report = invoke(runner, "summary", lower, upper)
    check_common(report, lower, upper, "summary")
    assert report["prime_power_events"] == expected["events"]
    assert report["prime_events"] == expected["prime_events"]
    assert report["higher_power_events"] == expected["higher_power_events"]
    # CRlibm's binary64 interval is intentionally wider than the Python
    # rational-series Q64 interval.  It must enclose that independent exact
    # model, while the separate structural digest must agree byte-for-byte.
    assert report["delta"][0] <= expected["delta"][0]
    assert report["delta"][1] >= expected["delta"][1]
    assert report["event_sha256"] == expected["event_sha256"]
    assert len(report["row_sha256"]) == 64
    assert report["guards"] == {}
    assert report["incoming_state"] is None
    assert report["outgoing_state"] is None
    return report, expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, type=Path)
    arguments = parser.parse_args()
    runner = arguments.runner.resolve()

    # Exact bounded fixture shared with
    # SparkInterval/Tests/PsiShardReceiptWireTest.lean.  Unlike the generic
    # enclosure comparison below, this also pins the CRlibm row digest.
    wire, _ = check_against_python(
        runner, LEAN_WIRE_FIXTURE["lower"], LEAN_WIRE_FIXTURE["upper"]
    )
    for field in (
        "prime_power_events",
        "prime_events",
        "higher_power_events",
        "delta",
        "event_sha256",
        "row_sha256",
    ):
        assert wire[field] == LEAN_WIRE_FIXTURE[field]

    whole, _ = check_against_python(runner, 2, 100_000)
    first, _ = check_against_python(runner, 2, 49_999)
    second, _ = check_against_python(runner, 50_000, 100_000)
    assert [
        first["delta"][0] + second["delta"][0],
        first["delta"][1] + second["delta"][1],
    ] == whole["delta"]

    root_verify = invoke(runner, "verify", 2, 49_999)
    check_common(root_verify, 2, 49_999, "verify")
    assert root_verify["delta"] == first["delta"]
    assert root_verify["event_sha256"] == first["event_sha256"]
    assert root_verify["row_sha256"] == first["row_sha256"]
    assert root_verify["incoming_state"] == [0, 0]
    assert root_verify["outgoing_state"] == first["delta"]

    incoming = tuple(first["delta"])
    second_verify = invoke(runner, "verify", 50_000, 100_000, incoming)
    check_common(second_verify, 50_000, 100_000, "verify")
    assert second_verify["delta"] == second["delta"]
    assert second_verify["event_sha256"] == second["event_sha256"]
    assert second_verify["row_sha256"] == second["row_sha256"]
    assert second_verify["incoming_state"] == list(incoming)
    assert second_verify["outgoing_state"] == [
        incoming[0] + second["delta"][0],
        incoming[1] + second["delta"][1],
    ]
    assert second_verify["terminal_strict_lower_checked"] is False
    assert set(second_verify["guards"]) == {"ch25-psi-1e13"}

    # Exercise primesieve's nonzero jump path independently of the root shard.
    check_against_python(runner, 1_000_000_000_000, 1_000_000_100_000)

    # Exercise the strict terminal branch with an explicitly synthetic
    # bounded-test input.  This checks code coverage only; it is not the
    # root-derived state of the production campaign.
    terminal_lower = 10**13 - 100_000
    synthetic = (terminal_lower - 1) << 64
    terminal = invoke(
        runner,
        "verify",
        terminal_lower,
        10**13,
        (synthetic, synthetic),
    )
    assert terminal["terminal_strict_lower_checked"] is True

    invoke(runner, "verify", 50_000, 100_000, None, expect_success=False)
    invoke(runner, "verify", 50_000, 100_000, (2, 1), expect_success=False)
    invoke(runner, "summary", 2, 100, (0, 0), expect_success=False)

    # A full-range run is intentionally not part of a bounded known-answer
    # test; the production executable itself hard-checks the published total
    # event count when invoked on the literal source range.
    assert whole["terminal_strict_lower_checked"] is False
    print("psi residual shard known answers passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
