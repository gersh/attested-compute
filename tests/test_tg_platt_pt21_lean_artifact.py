#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Callable
import unittest

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional validation dependency
    jsonschema = None

from tg_verifier.platt_pt21_lean_artifact import (
    PT21LeanArtifactError,
    SCHEMA,
    UPSTREAM_COMMIT,
    inspect,
    load,
    render_lean_source,
)
from tests.test_tg_platt_required_sign_packet import build_packet


ROOT = Path(__file__).resolve().parents[1]


def rational(numerator: int, denominator: int = 1) -> dict[str, int]:
    return {"numerator": numerator, "denominator": denominator}


def interval(value: int) -> dict[str, object]:
    return {"lo": rational(value), "hi": rational(value)}


def endpoint(value: int) -> dict[str, object]:
    return {"enclosure": interval(value), "positive": value > 0}


def stream(
    left: int,
    right: int,
    brackets: list[dict[str, object]],
    events: list[dict[str, int]],
) -> dict[str, object]:
    return {
        "left_boundary": endpoint(left),
        "right_boundary": endpoint(right),
        "brackets": brackets,
        "events": events,
    }


def bracket(
    lower_sample: int,
    upper_sample: int,
    lower_value: int,
    upper_value: int,
    resolver: str,
) -> dict[str, object]:
    return {
        "lower_offset": rational(lower_sample),
        "upper_offset": rational(upper_sample),
        "lower_value": endpoint(lower_value),
        "upper_value": endpoint(upper_value),
        "resolver": resolver,
        "fallback_receipt_sha256": None,
    }


def artifact() -> dict[str, object]:
    main = stream(
        -1,
        -1,
        [
            bracket(-1, 0, -1, 1, "stationary_left"),
            bracket(0, 1, 1, -1, "stationary_right"),
        ],
        [{"left_sample": -1, "right_sample": 1, "multiplicity": 2}],
    )
    empty = stream(-1, -1, [], [])
    return {
        "schema": SCHEMA,
        "upstream_commit": UPSTREAM_COMMIT,
        "block": 0,
        "height_lower": 10_000_000_000,
        "height_upper": 10_000_001_008,
        "window_center": 10_000_000_504,
        "required_sign_packet_sha256": "ab" * 32,
        "source_trace_sha256": "cd" * 32,
        "streams": {
            "main": main,
            "left_flank": deepcopy(empty),
            "right_flank": deepcopy(empty),
        },
        "turing": {
            "lower": {
                "s_bound": interval(21),
                "log_pi": interval(0),
                "im_gamma_integral": interval(21),
                "pi": interval(1),
                "quotient": interval(0),
                "count": 1,
            },
            "upper": {
                "s_bound": interval(21),
                "log_pi": interval(0),
                "im_gamma_integral": interval(21),
                "pi": interval(1),
                "quotient": interval(2),
                "count": 3,
            },
        },
    }


class PT21LeanArtifactTests(unittest.TestCase):
    def write(self, value: object) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "block.json"
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        return path

    def test_valid_artifact_reaches_only_finite_lean_contract(self) -> None:
        path = self.write(artifact())
        value = load(path)
        self.assertEqual(value["block"], 0)
        result = inspect(path)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["fixed_lattice_geometry_recomputed"])
        self.assertTrue(result["exact_rational_turing_recomputed"])
        self.assertTrue(result["finite_lean_contract_ready"])
        self.assertFalse(result["hardy_z_endpoint_realization_proved"])
        self.assertFalse(result["main_multiplicity_realization_proved"])
        self.assertFalse(result["analytic_turing_bounds_proved"])
        self.assertFalse(result["lean_source_claim_ready"])

    def test_lean_emission_targets_kernel_checker(self) -> None:
        source = render_lean_source(self.write(artifact()), "fixturePT21Block")
        self.assertIn("import SparkInterval.Zeta.PT21ArtifactBinding", source)
        self.assertIn("def fixturePT21Block : BlockArtifact", source)
        self.assertIn("#guard fixturePT21Block.check", source)
        self.assertIn(".stationaryLeft, none⟩", source)
        with self.assertRaisesRegex(PT21LeanArtifactError, "name"):
            render_lean_source(self.write(artifact()), "bad.name; #eval 1")

    def test_optional_source_packet_chain_is_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, source = build_packet(Path(temporary))
            value = artifact()
            value["required_sign_packet_sha256"] = hashlib.sha256(
                packet.read_bytes()
            ).hexdigest()
            path = self.write(value)
            result = inspect(
                path, required_sign_packet=packet, source_packet=source
            )
            self.assertTrue(result["required_sign_packet_rechecked"])
            self.assertTrue(result["source_transform_packet_rechecked"])
            value["required_sign_packet_sha256"] = "00" * 32
            with self.assertRaisesRegex(PT21LeanArtifactError, "digest differs"):
                load(self.write(value), required_sign_packet=packet)

    def test_geometry_and_turing_decisions_fail_closed(self) -> None:
        cases: list[tuple[str, Callable[[dict[str, object]], None]]] = [
            ("geometry", lambda value: value.__setitem__("window_center", 1)),
            (
                "quotient",
                lambda value: value["turing"]["upper"].__setitem__("quotient", interval(1)),
            ),
            ("closure", lambda value: value["turing"]["upper"].__setitem__("count", 4)),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                value = artifact()
                mutate(value)
                with self.assertRaises(PT21LeanArtifactError):
                    load(self.write(value))

    def test_touching_endpoint_and_stationary_pair_fail_closed(self) -> None:
        value = artifact()
        second = value["streams"]["main"]["brackets"][1]
        second["lower_value"] = endpoint(-1)
        second["upper_value"] = endpoint(1)
        with self.assertRaisesRegex(PT21LeanArtifactError, "touching endpoint"):
            load(self.write(value))

        value = artifact()
        value["streams"]["main"]["brackets"][1]["resolver"] = "direct"
        with self.assertRaisesRegex(PT21LeanArtifactError, "stationary resolver"):
            load(self.write(value))

        value = artifact()
        value["streams"]["main"]["events"][0]["multiplicity"] = 1
        with self.assertRaisesRegex(PT21LeanArtifactError, "direct bracket binding"):
            load(self.write(value))

    def test_stationary_dyadic_brackets_use_one_multiplicity_two_cell(self) -> None:
        value = artifact()
        first, second = value["streams"]["main"]["brackets"]
        first["upper_offset"] = rational(1, 2)
        second["lower_offset"] = rational(1, 2)
        checked = load(self.write(value))
        self.assertEqual(
            checked["streams"]["main"]["brackets"][0]["upper_offset"],
            Fraction(1, 2),
        )
        self.assertEqual(
            checked["streams"]["main"]["events"],
            [{"left_sample": -1, "right_sample": 1, "multiplicity": 2}],
        )

    def test_fallback_receipt_and_canonical_rationals_are_mandatory(self) -> None:
        value = artifact()
        first = value["streams"]["main"]["brackets"][0]
        first["resolver"] = "pinned_arb_fallback"
        value["streams"]["main"]["brackets"][1]["resolver"] = "direct"
        with self.assertRaisesRegex(PT21LeanArtifactError, "SHA-256"):
            load(self.write(value))

        value = artifact()
        value["turing"]["lower"]["pi"]["lo"] = rational(2, 2)
        with self.assertRaisesRegex(PT21LeanArtifactError, "lowest terms"):
            load(self.write(value))

    def test_duplicate_json_keys_are_rejected(self) -> None:
        path = self.write(artifact())
        path.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
        with self.assertRaisesRegex(PT21LeanArtifactError, "duplicate"):
            load(path)

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_schema_accepts_the_fixed_fixture(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "platt-pt21-lean-block-artifact.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(artifact())


if __name__ == "__main__":
    unittest.main()
