# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import mpmath

from tg_verifier.platt_pt21_turing_inputs import (
    PT21TuringInputsError,
    SOURCE_BLOCK_COUNT,
    SOURCE_LOWER,
    SOURCE_STEP,
    load,
    validate,
)
from tg_verifier.platt_pt21_fused_artifact import (
    INTERPOLATION_PATCH_SHA256,
    TRACE_SCHEMA,
    UPSTREAM_COMMIT,
    _parse_trace,
)


RUNNER_ENV = "TG_PLATT_PT21_TURING_INPUTS"
PACKET_SHA256 = hashlib.sha256(b"canonical-required-sign-packet").hexdigest()


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )


def as_fraction(value: dict[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def as_interval(value: dict[str, dict[str, int]]) -> tuple[Fraction, Fraction]:
    return as_fraction(value["lo"]), as_fraction(value["hi"])


def contains_mpf(interval: tuple[Fraction, Fraction], value: mpmath.mpf) -> bool:
    lower = mpmath.mpf(interval[0].numerator) / interval[0].denominator
    upper = mpmath.mpf(interval[1].numerator) / interval[1].denominator
    return lower <= value <= upper


def im_int1(t: mpmath.mpf) -> mpmath.mpf:
    square = t * t
    return (
        -t * mpmath.atan(4 * t) / 4
        - 3 * square / 4
        + mpmath.log(1 + 16 * square) / 32
        - mpmath.mpf(1) / 64
        + (square + mpmath.mpf(1) / 16)
        * mpmath.log(square + mpmath.mpf(1) / 16)
        / 4
    )


class PT21TuringInputsNativeTest(unittest.TestCase):
    def run_producer(self, block: int) -> tuple[dict[str, object], bytes]:
        runner = os.environ.get(RUNNER_ENV)
        if not runner:
            self.skipTest(f"set {RUNNER_ENV} to run native producer tests")
        completed = subprocess.run(
            [
                runner,
                "--block",
                str(block),
                "--required-sign-packet-sha256",
                PACKET_SHA256,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        self.assertEqual(completed.stderr, b"")
        value = json.loads(completed.stdout)
        self.assertEqual(completed.stdout, canonical(value))
        return value, completed.stdout

    def test_first_and_final_block_have_exact_source_geometry(self) -> None:
        for block in (0, SOURCE_BLOCK_COUNT - 1):
            with self.subTest(block=block):
                value, raw = self.run_producer(block)
                validated = validate(
                    value,
                    expected_block=block,
                    expected_packet_sha256=PACKET_SHA256,
                )
                a = SOURCE_LOWER + block * SOURCE_STEP
                b = a + SOURCE_STEP
                self.assertEqual(value["inputs"]["lower"]["interval"], {
                    "a": a - 21,
                    "b": a,
                })
                self.assertEqual(value["inputs"]["upper"]["interval"], {
                    "a": b,
                    "b": b + 21,
                })
                self.assertEqual(
                    set(validated["turing_inputs"]), {"lower", "upper"}
                )
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "inputs.json"
                    path.write_bytes(raw)
                    loaded = load(
                        path,
                        expected_block=block,
                        expected_packet_sha256=PACKET_SHA256,
                    )
                self.assertEqual(
                    loaded["artifact_sha256"], hashlib.sha256(raw).hexdigest()
                )

    def test_rational_intervals_contain_independent_high_precision_values(self) -> None:
        value, _ = self.run_producer(SOURCE_BLOCK_COUNT - 1)
        mpmath.mp.dps = 110
        for side_name in ("lower", "upper"):
            side = value["inputs"][side_name]
            a = mpmath.mpf(side["interval"]["a"])
            b = mpmath.mpf(side["interval"]["b"])
            values = side["values"]
            expected = {
                "pi": mpmath.pi,
                "log_pi": mpmath.log(mpmath.pi),
                "s_bound": mpmath.mpf(59) * mpmath.log(b) / 1000
                + mpmath.mpf(2067) / 1000,
                "im_gamma_integral": 2 * (im_int1(b / 2) - im_int1(a / 2)),
            }
            for name, target in expected.items():
                self.assertTrue(
                    contains_mpf(as_interval(values[name]), target),
                    f"{side_name}.{name} misses independent 110-digit value",
                )

    def test_extracted_payload_is_accepted_by_existing_fused_trace_decoder(
        self,
    ) -> None:
        value, _ = self.run_producer(0)
        validated = validate(
            value,
            expected_block=0,
            expected_packet_sha256=PACKET_SHA256,
        )
        trace = {
            "schema": TRACE_SCHEMA,
            "upstream_commit": UPSTREAM_COMMIT,
            "interpolation_patch_sha256": INTERPOLATION_PATCH_SHA256,
            "block": 0,
            "required_sign_packet_sha256": PACKET_SHA256,
            "producer": {
                "worker_sha256": "12" * 32,
                "worker_size_bytes": 1,
                "precision_bits": 128,
                "all_required_samples_certified": True,
                "all_stationary_queries_resolved": True,
            },
            "stationary_resolutions": [],
            "turing_inputs": validated["turing_inputs"],
            "semantic_status": {
                "hardy_z_endpoint_realization_proved": False,
                "main_multiplicity_realization_proved": False,
                "analytic_turing_realization_proved": False,
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.json"
            path.write_bytes(canonical(trace))
            parsed, digest = _parse_trace(
                path, packet_sha256=PACKET_SHA256, block=0
            )
        self.assertEqual(len(digest), 64)
        self.assertGreater(parsed["turing_inputs"]["lower"]["pi"][0], 3)
        self.assertLess(parsed["turing_inputs"]["upper"]["pi"][1], 4)

    def test_native_cli_rejects_incomplete_ambiguous_or_duplicate_identity(self) -> None:
        runner = os.environ.get(RUNNER_ENV)
        if not runner:
            self.skipTest(f"set {RUNNER_ENV} to run native producer tests")
        cases = (
            (),
            ("--block", "0"),
            (
                "--block",
                "0",
                "--block",
                "1",
                "--required-sign-packet-sha256",
                PACKET_SHA256,
            ),
            (
                "--block",
                str(SOURCE_BLOCK_COUNT),
                "--required-sign-packet-sha256",
                PACKET_SHA256,
            ),
            (
                "--block",
                "0",
                "--required-sign-packet-sha256",
                "A" * 64,
            ),
            (
                "--block",
                "0",
                "--required-sign-packet-sha256",
                PACKET_SHA256,
                "--unknown",
            ),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [runner, *arguments],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, b"")
                self.assertIn(b"tg_platt_pt21_turing_inputs:", completed.stderr)

    def test_validator_rejects_splicing_nondyadic_and_semantic_overclaim(self) -> None:
        value, _ = self.run_producer(0)
        mutations: list[tuple[str, dict[str, object]]] = []

        changed = deepcopy(value)
        changed["block"] = 1
        mutations.append(("block splice", changed))

        changed = deepcopy(value)
        changed["required_sign_packet_sha256"] = "00" * 32
        mutations.append(("packet splice", changed))

        changed = deepcopy(value)
        changed["source_identity"]["source_turing_c_sha256"] = "00" * 32
        mutations.append(("source splice", changed))

        changed = deepcopy(value)
        changed["inputs"]["lower"]["interval"]["a"] += 1
        mutations.append(("wrong lower interval", changed))

        changed = deepcopy(value)
        changed["inputs"]["upper"]["function"] = "turing_min"
        mutations.append(("wrong upper function", changed))

        changed = deepcopy(value)
        changed["inputs"]["lower"]["values"]["pi"]["lo"] = {
            "numerator": 1,
            "denominator": 3,
        }
        mutations.append(("non-dyadic endpoint", changed))

        changed = deepcopy(value)
        changed["inputs"]["lower"]["values"]["pi"]["lo"] = deepcopy(
            changed["inputs"]["lower"]["values"]["pi"]["hi"]
        )
        changed["inputs"]["lower"]["values"]["pi"]["hi"] = {
            "numerator": 1,
            "denominator": 1,
        }
        mutations.append(("reversed interval", changed))

        changed = deepcopy(value)
        changed["semantic_status"]["analytic_turing_realization_proved"] = True
        mutations.append(("analytic overclaim", changed))

        changed = deepcopy(value)
        del changed["inputs"]["lower"]["values"]["s_bound"]
        mutations.append(("partial side", changed))

        for label, changed in mutations:
            with self.subTest(label=label):
                with self.assertRaises(PT21TuringInputsError):
                    validate(
                        changed,
                        expected_block=0,
                        expected_packet_sha256=PACKET_SHA256,
                    )

    def test_loader_rejects_noncanonical_duplicate_and_symlink_inputs(self) -> None:
        value, raw = self.run_producer(0)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            noncanonical = directory / "pretty.json"
            noncanonical.write_text(json.dumps(value, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(
                PT21TuringInputsError, "not canonical JSON"
            ):
                load(
                    noncanonical,
                    expected_block=0,
                    expected_packet_sha256=PACKET_SHA256,
                )

            duplicate = directory / "duplicate.json"
            duplicate.write_bytes(raw.replace(b'{"algorithm":', b'{"block":0,"algorithm":', 1))
            with self.assertRaisesRegex(PT21TuringInputsError, "duplicate JSON key"):
                load(
                    duplicate,
                    expected_block=0,
                    expected_packet_sha256=PACKET_SHA256,
                )

            valid = directory / "valid.json"
            valid.write_bytes(raw)
            symlink = directory / "link.json"
            symlink.symlink_to(valid)
            with self.assertRaisesRegex(PT21TuringInputsError, "regular file"):
                load(
                    symlink,
                    expected_block=0,
                    expected_packet_sha256=PACKET_SHA256,
                )


if __name__ == "__main__":
    unittest.main()
