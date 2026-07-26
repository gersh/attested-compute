#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from azure.measured_runner import RunnerError, validate_job_spec
from tg_verifier.azure_h100_goldbach_candidate_calibration import (
    materialize_calibration_job,
)
from tg_verifier.goldbach_optimized_calibration_contract import (
    CLASSIFICATION,
    DEFAULT_SAMPLE_EVEN_COUNT,
    DEFAULT_SAMPLE_EVEN_LIMIT,
    DEFAULT_SAMPLE_EVEN_START,
    INPUT_KIND,
    GoldbachCalibrationContractError,
    algorithm_identity,
    validate_input,
)
from tg_verifier.goldbach_optimized_projection import (
    project_from_h100_calibration,
)
from tools.tg_goldbach_optimized_h100_measured_workload import (
    GoldbachCalibrationWorkloadError,
    _parse_stdout,
    _validate_result,
)


def _input() -> dict[str, object]:
    return {
        "candidate": {
            "candidate_closure_sha256": "1" * 64,
            "candidate_manifest_sha256": "2" * 64,
            "cubin_sha256": "3" * 64,
            "executable_sha256": "4" * 64,
            "executable_size_bytes": 123,
            "ptx_sha256": "5" * 64,
            "sass_sha256": "6" * 64,
            "source_identity_sha256": "7" * 64,
        },
        "classification": CLASSIFICATION,
        "domain": {
            "even_count": DEFAULT_SAMPLE_EVEN_COUNT,
            "even_limit_inclusive": DEFAULT_SAMPLE_EVEN_LIMIT,
            "even_start_inclusive": DEFAULT_SAMPLE_EVEN_START,
        },
        "kind": INPUT_KIND,
        "repetitions": 3,
        "schema_version": 1,
        "warmups": 1,
    }


def _stdout(
    *, seconds: str = "2.326270", initialization_ms: str = "436.000"
) -> str:
    return (
        "[Hardware] GPU 0: NVIDIA H100 NVL (95830 MB VRAM)\n"
        "Building small primes bitset up to 176776697...\n"
        "Pre-generating CPU primes up to 100000000...\n"
        f"Initialization completed in {initialization_ms} ms.\n\n"
        "--- Launching Multi-GPU Verifier ---\n"
        "Checking range : "
        f"[{DEFAULT_SAMPLE_EVEN_START}, {DEFAULT_SAMPLE_EVEN_LIMIT}]\n"
        f"Total numbers  : {DEFAULT_SAMPLE_EVEN_COUNT}\n\n\n"
        "--- Verification Complete ---\n"
        "All even numbers from "
        f"{DEFAULT_SAMPLE_EVEN_START} up to {DEFAULT_SAMPLE_EVEN_LIMIT} "
        "satisfy Goldbach. ✓\n"
        f"Total computation time : {seconds} seconds\n"
        "Phase 2 fallbacks      : 0\n"
    )


def _run(seconds: str, initialization_ms: str, fixed_ns: int) -> dict[str, object]:
    raw = _stdout(
        seconds=seconds, initialization_ms=initialization_ms
    ).encode("utf-8")
    parsed = _parse_stdout(
        raw,
        start=DEFAULT_SAMPLE_EVEN_START,
        limit=DEFAULT_SAMPLE_EVEN_LIMIT,
        count=DEFAULT_SAMPLE_EVEN_COUNT,
    )
    # The test values all contain six fractional digits.
    compute_ns = int(seconds.split(".")[0]) * 1_000_000_000 + int(
        seconds.split(".")[1].ljust(9, "0")
    )
    init_ns = int(initialization_ms.split(".")[0]) * 1_000_000 + int(
        initialization_ms.split(".")[1].ljust(6, "0")
    )
    import hashlib

    return {
        "parsed": parsed,
        "reported_computation_nanoseconds": compute_ns,
        "stdout_sha256": hashlib.sha256(raw).hexdigest(),
        "stdout_utf8": raw.decode("utf-8"),
        "wall_nanoseconds": compute_ns + init_ns + fixed_ns,
    }


class GoldbachOptimizedH100CalibrationTests(unittest.TestCase):
    def test_contract_binds_candidate_range_and_repetitions(self) -> None:
        value = _input()
        self.assertEqual(validate_input(value), value)
        identity = algorithm_identity(value)
        self.assertTrue(
            identity["algorithm_id"].startswith(
                "sparkinterval.tg.goldbach-optimized-h100-calibration."
            )
        )
        changed = copy.deepcopy(value)
        changed["domain"]["even_count"] += 1
        with self.assertRaises(GoldbachCalibrationContractError):
            validate_input(changed)
        changed = copy.deepcopy(value)
        changed["repetitions"] = 2
        with self.assertRaises(GoldbachCalibrationContractError):
            validate_input(changed)

    def test_h100_stdout_parser_is_exact_and_rejects_gpu_or_fallback_attack(
        self,
    ) -> None:
        raw = _stdout().encode("utf-8")
        parsed = _parse_stdout(
            raw,
            start=DEFAULT_SAMPLE_EVEN_START,
            limit=DEFAULT_SAMPLE_EVEN_LIMIT,
            count=DEFAULT_SAMPLE_EVEN_COUNT,
        )
        self.assertEqual(parsed["phase2_fallbacks"], 0)
        self.assertEqual(parsed["gpu_name"], "NVIDIA H100 NVL")
        for changed in (
            raw.replace(b"NVIDIA H100 NVL", b"NVIDIA GB10"),
            raw.replace(b"Phase 2 fallbacks      : 0", b"Phase 2 fallbacks      : 1"),
            raw + b"trailing",
        ):
            with self.assertRaises(GoldbachCalibrationWorkloadError):
                _parse_stdout(
                    changed,
                    start=DEFAULT_SAMPLE_EVEN_START,
                    limit=DEFAULT_SAMPLE_EVEN_LIMIT,
                    count=DEFAULT_SAMPLE_EVEN_COUNT,
                )

    def test_projection_charges_maximum_initialization_and_fixed_overhead_per_leaf(
        self,
    ) -> None:
        input_value = _input()
        measured = [
            _run("2.326270", "436.000", 10_000_000),
            _run("2.300000", "427.000", 12_000_000),
            _run("2.400000", "440.000", 11_000_000),
        ]
        result = {
            "authority": {
                "confidential_attestation_completed": False,
                "lean_atom_discharged": False,
                "production_identity_promoted": False,
                "source_scale_completion": False,
                "target_h100_measurement_completed": False,
            },
            "candidate": input_value["candidate"],
            "classification": CLASSIFICATION,
            "domain": input_value["domain"],
            "kind": (
                "sparkinterval.goldbach-optimized-h100-calibration-result.v1"
            ),
            "measured_runs": measured,
            "median_reported_computation_nanoseconds": 2_326_270_000,
            "schema_version": 1,
            "warmup_runs": [_run("2.500000", "450.000", 9_000_000)],
        }
        self.assertEqual(_validate_result(result, input_value), result)
        projection = project_from_h100_calibration(result)
        self.assertEqual(
            projection["inputs"]["initialization_seconds_per_leaf"],
            "0.45",
        )
        self.assertEqual(
            projection["inputs"]["fixed_seconds_per_leaf"],
            "0.012",
        )
        self.assertNotEqual(
            projection["projection"]["repeated_fixed_overhead_wall_hours"],
            "0",
        )
        self.assertFalse(projection["production_gate_passed"])
        self.assertFalse(projection["target_h100_source_scale_measured"])

    def test_materialized_job_has_mandatory_gate_and_no_promotion(
        self,
    ) -> None:
        candidate = Path("/tmp/tg-goldbach-qualified-0725-e")
        if not candidate.is_dir():
            self.skipTest("retained local qualification package is absent")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "job"
            report = materialize_calibration_job(
                candidate,
                destination,
                python_executable=Path("/usr/bin/python3"),
                runner_policy=Path(
                    "profiles/measured_runner/"
                    "development_challenge_first_v1.json"
                ),
                nvidia_policy=Path(
                    "attestation/policies/gpu_prover_h100.rego"
                ),
                require_x86_64_candidate=False,
            )
            self.assertFalse(report["trust_status"]["target_h100_measured"])
            job = json.loads((destination / "job.json").read_bytes())
            validate_job_spec(job)
            self.assertTrue(job["gpu_pre_run_gate"]["required"])
            self.assertIn(
                "@challenge_expires_at@",
                job["gpu_pre_run_gate"]["argv"],
            )
            attacked = copy.deepcopy(job)
            attacked["gpu_pre_run_gate"] = None
            with self.assertRaises(RunnerError):
                validate_job_spec(attacked)


if __name__ == "__main__":
    unittest.main()
