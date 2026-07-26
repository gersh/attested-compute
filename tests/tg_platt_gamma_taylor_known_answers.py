#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known-answer checks for the compact Platt log-Gamma Taylor producer."""

from __future__ import annotations

import argparse
import json
import math
import subprocess


CASES = {
    10_000_000_504: {
        "coefficient_digest":
            "5e92008753f722f51588c4336401ff5c145b236372e908677d6f0c1c4bb3393b",
        "projection_digest":
            "94c8a78c3fabbd783db422c0d227777dfae6d8445981842adf27439f9b10fb23",
        "anchor_limbs": [
            "32e78fa208d9282f", "31fea3aef4924eb6", "c7e64ca1720e02e1"
        ],
        "step_limbs": [
            "be0f1ad116ce6d63", "4847b631c746ec93", "4aa43d8dfc8a1c3a"
        ],
    },
    3_000_175_332_296: {
        "coefficient_digest":
            "94204e9da3be26ecb7bd5aeee428f2cae8b1c1d832aa394fc166011af0525545",
        "projection_digest":
            "4867e249f1ffa5068650b541f09ea1903050854e710534c3b6665f936adeccd2",
        "anchor_limbs": [
            "b24dfc5011855392", "8a4395585fb115aa", "12586a0353606dd2"
        ],
        "step_limbs": [
            "1715a52485e840c8", "7cdc459d30363150", "5db48b238377b9bd"
        ],
    },
}


def run_case(runner: str, height: int) -> dict[str, object]:
    completed = subprocess.run(
        [
            runner,
            "--height", str(height),
            "--precision", "256",
            "--degree", "6",
            "--repeat", "1",
            "--audit-samples", "257",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AssertionError(f"expected one JSON record, got {len(lines)}")
    return json.loads(lines[0])


def check_record(record: dict[str, object], height: int) -> None:
    expected = CASES[height]
    assert record["schema"] == "sparkinterval.tg.platt-gamma-taylor.v1"
    assert record["claim_scope"] == "compact_flint_gamma_taylor_certificate"
    assert record["height"] == height
    assert record["source_radius"] == "2688"
    assert record["source_grid_step"] == "21/128"
    assert record["gaussian_h"] == "116"
    assert record["degree"] == 6
    assert record["precision_bits"] == 256
    assert record["audit_samples"] == 257
    assert record["audit_passed"] is True
    assert record["flint_version"] == "3.6.0"
    assert record["flint_commit"] == "8d5454b96761fafe4d5a9da76a369a602f500f49"
    assert record["execution_attested"] is False
    assert record["lean_atom_discharged"] is False
    assert record["coefficient_digest"] == expected["coefficient_digest"]
    assert record["projection_digest"] == expected["projection_digest"]

    coefficients = record["coefficients"]
    projected = record["binary64_coefficients"]
    assert isinstance(coefficients, list) and len(coefficients) == 6
    assert isinstance(projected, list) and len(projected) == 6
    assert [row["degree"] for row in coefficients] == list(range(6))
    assert [row["degree"] for row in projected] == list(range(6))
    for row in projected:
        for component in ("re", "im"):
            lower = float.fromhex(row[component]["lo_hex"])
            upper = float.fromhex(row[component]["hi_hex"])
            assert math.isfinite(lower) and math.isfinite(upper)
            assert lower <= upper

    anchor = record["phase_anchor_q192"]
    step = record["phase_grid_step_q192"]
    assert anchor["limbs_le"] == expected["anchor_limbs"]
    assert step["limbs_le"] == expected["step_limbs"]
    anchor_error = float.fromhex(anchor["angular_error_upper_hex"])
    step_error = float.fromhex(step["angular_error_upper_hex"])
    assert math.isfinite(anchor_error) and 0.0 <= anchor_error < 2.0**-180
    assert math.isfinite(step_error) and 0.0 <= step_error < 2.0**-180

    remainder = record["remainder_binary64"]
    remainder_lo = float.fromhex(remainder["lo_hex"])
    remainder_hi = float.fromhex(remainder["hi_hex"])
    assert 0.0 <= remainder_lo <= remainder_hi < 2.0**-90

    probes = record["source_value_probes"]
    assert [probe["index"] for probe in probes] == [0, 8192, 16384, 24576, 32767]
    for probe in probes:
        for component in ("re", "im"):
            lower = float.fromhex(probe[component]["lo_hex"])
            upper = float.fromhex(probe[component]["hi_hex"])
            assert math.isfinite(lower) and math.isfinite(upper)
            assert lower <= upper


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True)
    args = parser.parse_args()
    for height in CASES:
        check_record(run_case(args.runner, height), height)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
