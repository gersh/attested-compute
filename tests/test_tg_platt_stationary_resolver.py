# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

try:
    import jsonschema
except ModuleNotFoundError:  # Optional in the minimal verifier environment.
    jsonschema = None

from tg_verifier.platt_pt21_fused_artifact import (
    INTERPOLATION_PATCH_SHA256,
    TRACE_SCHEMA,
    build_block_artifact,
)
from tg_verifier.platt_required_sign_packet import (
    HEADER,
    REQUIRED_BEGIN,
    REQUIRED_COUNT,
    REQUIRED_END,
    SAMPLE,
    SOURCE_LOWER_CENTER,
    UPSTREAM_COMMIT,
)
from tg_verifier.platt_stationary_trace import (
    PT21StationaryTraceError,
    load,
    validate,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER_ENV = "TG_PLATT_STATIONARY_RESOLVER"


def _fnv1a(raw: bytes) -> int:
    value = 1_469_598_103_934_665_603
    for byte in raw:
        value ^= byte
        value = (value * 1_099_511_628_211) & ((1 << 64) - 1)
    return value


def _rational(value: int) -> dict[str, int]:
    return {"denominator": 1, "numerator": value}


def _point(value: int) -> dict[str, object]:
    return {"hi": _rational(value), "lo": _rational(value)}


def _required_packet(directory: Path) -> Path:
    samples = bytearray()
    signs = bytearray((REQUIRED_COUNT + 7) // 8)
    radius = 2.0**-80
    special = {0: 3.0, 1: 1.0, 2: 3.0, 3: -100.0}
    for index in range(REQUIRED_COUNT):
        offset = index - 12_870
        high = special.get(offset, 3.0)
        samples.extend(SAMPLE.pack(high, 0.0, radius))
        if high > 0:
            signs[index // 8] |= 1 << (index % 8)
    source = b"stationary-resolver-integration-fixture"
    header = HEADER.pack(
        b"PT21SGN1",
        1,
        HEADER.size,
        0x01020304,
        1,
        1,
        768_000,
        REQUIRED_BEGIN,
        REQUIRED_END,
        REQUIRED_COUNT,
        0,
        SOURCE_LOWER_CENTER,
        len(samples),
        len(signs),
        _fnv1a(samples),
        _fnv1a(signs),
        len(source),
        hashlib.sha256(source).hexdigest().encode(),
        UPSTREAM_COMMIT,
    )
    path = directory / "required.bin"
    path.write_bytes(header + samples + signs)
    return path


class PT21StationaryResolverTest(unittest.TestCase):
    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_wire_schema_accepts_native_trace(self) -> None:
        runner = os.environ.get(RUNNER_ENV)
        if not runner:
            self.skipTest(f"set {RUNNER_ENV} to run native schema check")
        completed = subprocess.run(
            [runner, "--mode", "valid"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        schema = json.loads(
            (
                ROOT / "schemas/platt-pt21-stationary-trace.schema.json"
            ).read_text(encoding="utf-8")
        )
        value = json.loads(completed.stdout)
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(value)

    def test_source_boundary_is_explicit_and_fail_closed(self) -> None:
        header = (
            ROOT
            / "gpu/include/sparkinterval/tg_platt_stationary_resolver.hpp"
        ).read_text(encoding="utf-8")
        source = (
            ROOT / "reference/tg_platt_stationary_resolver.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("kRequiredCount = 25'741U", header)
        self.assertIn("kSourcePointsPerSide = 70U", header)
        self.assertIn("kSourceTraceResolutionLimit = 10'000U", header)
        self.assertIn("kFailureUnrefinedAmbiguousDisk", header)
        self.assertIn("kFailureDepth", header)
        self.assertIn("arf_load_str", source)
        self.assertIn("not a subset of its DD disk", source)
        self.assertIn("arb_add_error(output, interpolation_error_", source)
        self.assertIn("higher_precision_replay", source)
        self.assertIn("finite stationary trace overclaims", (
            ROOT / "tg_verifier/platt_stationary_trace.py"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("hardy_z_endpoint_realization_proved\\\":true", source)

    def test_independent_validator_rejects_semantic_and_bracket_mutations(self) -> None:
        runner = os.environ.get(RUNNER_ENV)
        if not runner:
            self.skipTest(f"set {RUNNER_ENV} to run native mutation checks")
        completed = subprocess.run(
            [runner, "--mode", "valid"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        value = json.loads(completed.stdout)
        validate(value)

        overclaim = copy.deepcopy(value)
        overclaim["semantic_status"]["hardy_z_endpoint_realization_proved"] = True
        with self.assertRaisesRegex(PT21StationaryTraceError, "overclaims"):
            validate(overclaim)

        wrong_sign = copy.deepcopy(value)
        midpoint = wrong_sign["stationary_resolutions"][0]["midpoint_value"]
        midpoint["lo"] = {"denominator": 1, "numerator": 1}
        midpoint["hi"] = {"denominator": 1, "numerator": 2}
        with self.assertRaisesRegex(PT21StationaryTraceError, "two touching"):
            validate(wrong_sign)

        wrong_digest = copy.deepcopy(value)
        wrong_digest["resolution_sha256"] = "00" * 32
        with self.assertRaisesRegex(PT21StationaryTraceError, "digest differs"):
            validate(wrong_digest)

    def test_optional_native_success_refinement_and_failures(self) -> None:
        runner = os.environ.get(RUNNER_ENV)
        if not runner:
            self.skipTest(f"set {RUNNER_ENV} to run native resolver")

        def invoke(mode: str) -> dict[str, object]:
            completed = subprocess.run(
                [runner, "--mode", mode],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "trace.json"
                path.write_text(completed.stdout, encoding="utf-8")
                return load(path)

        first = invoke("valid")
        second = invoke("valid")
        self.assertEqual(first, second)
        self.assertTrue(first["accepted"])
        self.assertTrue(first["replay_accepted"])
        self.assertEqual(first["candidate_count"], 1)
        self.assertEqual(len(first["stationary_resolutions"]), 1)

        refined = invoke("ambiguous-refined")
        self.assertTrue(refined["accepted"])
        self.assertEqual(refined["ambiguous_input_disks"], 1)
        self.assertEqual(refined["refinements_applied"], 1)

        for mode, flag in (
            ("ambiguous", 1 << 3),
            ("bad-refinement", 1 << 6),
            ("candidate", 1 << 8),
            ("depth", 1 << 13),
        ):
            failed = invoke(mode)
            self.assertFalse(failed["accepted"])
            self.assertFalse(failed["replay_accepted"])
            self.assertEqual(failed["stationary_resolutions"], [])
            self.assertEqual(failed["failure_flags"] & flag, flag)

    def test_optional_payload_enters_existing_fused_block_finalizer(self) -> None:
        runner = os.environ.get(RUNNER_ENV)
        if not runner:
            self.skipTest(f"set {RUNNER_ENV} to run native integration")
        completed = subprocess.run(
            [runner, "--mode", "valid"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stationary = json.loads(completed.stdout)
        validate(stationary)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = _required_packet(directory)
            trace = {
                "schema": TRACE_SCHEMA,
                "upstream_commit": UPSTREAM_COMMIT.decode(),
                "interpolation_patch_sha256": INTERPOLATION_PATCH_SHA256,
                "block": 0,
                "required_sign_packet_sha256": hashlib.sha256(
                    packet.read_bytes()
                ).hexdigest(),
                "producer": {
                    "worker_sha256": "34" * 32,
                    "worker_size_bytes": 1,
                    "precision_bits": 128,
                    "all_required_samples_certified": True,
                    "all_stationary_queries_resolved": True,
                },
                "stationary_resolutions": stationary[
                    "stationary_resolutions"
                ],
                "turing_inputs": {
                    "lower": {
                        "s_bound": _point(21),
                        "log_pi": _point(0),
                        "im_gamma_integral": _point(21),
                        "pi": _point(1),
                    },
                    "upper": {
                        "s_bound": _point(21),
                        "log_pi": _point(0),
                        "im_gamma_integral": _point(63),
                        "pi": _point(1),
                    },
                },
                "semantic_status": {
                    "hardy_z_endpoint_realization_proved": False,
                    "main_multiplicity_realization_proved": False,
                    "analytic_turing_realization_proved": False,
                },
            }
            trace_path = directory / "source-trace.json"
            trace_path.write_text(
                json.dumps(trace, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            artifact = build_block_artifact(packet, trace_path)
        main = artifact["streams"]["main"]
        self.assertEqual(len(main["brackets"]), 4)
        self.assertEqual(main["brackets"][0]["resolver"], "stationary_left")
        self.assertEqual(main["brackets"][1]["resolver"], "stationary_right")
        self.assertEqual(artifact["turing"]["lower"]["count"], 1)
        self.assertEqual(artifact["turing"]["upper"]["count"], 5)

    def test_optional_gb10_cpu_fallback_benchmark(self) -> None:
        runner = os.environ.get(RUNNER_ENV)
        if not runner:
            self.skipTest(f"set {RUNNER_ENV} to run benchmark")
        completed = subprocess.run(
            [runner, "--mode", "benchmark", "--iterations", "20"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        value = json.loads(completed.stdout)
        self.assertTrue(value["accepted"])
        self.assertGreater(value["blocks_per_second"], 0)
        self.assertEqual(value["platform"], "NVIDIA GB10 host CPU")
        self.assertEqual(
            value["benchmark_scope"], "bounded_cpu_flint_fallback_only"
        )
        self.assertFalse(value["flint_to_mathlib_realization_proved"])
        self.assertFalse(value["hardy_z_endpoint_realization_proved"])


if __name__ == "__main__":
    unittest.main()
