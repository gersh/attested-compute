#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Adversarial tests for the reviewed Goldbach build/job admission boundary."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from tg_verifier.azure_h100_goldbach_10pow27_workload_factory import (
    _projection_job,
    expected_execution_projection_sha256,
    factory_for_portfolio_group,
    h100_expected_claim_identity,
    source_reviewed_materializer_available,
)
from tg_verifier.campaign_io import canonical_json_bytes, load_json
from tg_verifier.goldbach_build_admission import (
    GoldbachBuildAdmissionError,
    goldbach_execution_projection,
    goldbach_execution_projection_sha256,
    load_build_admission,
    runtime_image_closure_value,
)
from tools.trusted_compute_receipt import ReceiptError, claim_from_bundle


FIXTURE = ROOT / "tests/fixtures/goldbach_build_admission.test.json"


def h100_group() -> dict[str, object]:
    from tg_verifier.azure_h100_goldbach_10pow27_workload_factory import (
        CAMPAIGN_ID,
        GROUP_ID,
        PHASE_DEPENDENCIES,
        PHASE_ID,
        PORTFOLIO_ARGV,
        SHARD_COUNT,
    )

    return {
        "backend_class": "h100_cuda",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PORTFOLIO_ARGV),
        "depends_on": list(PHASE_DEPENDENCIES),
        "group_id": GROUP_ID,
        "operator_adapter": "azure/h100_production_orchestrator.py",
        "owner_atom_id": "goldbach-finite-below-10pow27",
        "phase_id": PHASE_ID,
        "receipt_backend": "azure_ncc40ads_h100_v5",
        "semantic_binding": None,
        "shard_count": SHARD_COUNT,
        "terminal": False,
    }


class GoldbachBuildAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.admission = load_build_admission(FIXTURE, allow_test_fixture=True)

    def _mutated_admission(self, mutate) -> Path:
        value = copy.deepcopy(load_json(FIXTURE, require_canonical=True))
        mutate(value)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "admission.json"
        path.write_bytes(canonical_json_bytes(value))
        return path

    def test_fixture_authority_is_explicit_and_production_is_unconfigured(self) -> None:
        with self.assertRaisesRegex(
            GoldbachBuildAdmissionError, "explicit test-only authority"
        ):
            load_build_admission(FIXTURE)
        with self.assertRaisesRegex(
            GoldbachBuildAdmissionError, "content-addressed pin"
        ):
            load_build_admission(
                FIXTURE, expected_sha256="f" * 64, allow_test_fixture=True
            )
        production = self._mutated_admission(
            lambda value: value.__setitem__(
                "classification", "reviewed-production"
            )
        )
        with self.assertRaisesRegex(
            GoldbachBuildAdmissionError, "production.*unconfigured"
        ):
            load_build_admission(production)

    def test_fixed_derivations_source_and_nonzero_digests_are_fail_closed(self) -> None:
        mutations = {
            "source": lambda value: value["core"].__setitem__(
                "source_identity_sha256", "c" * 64
            ),
            "build argv": lambda value: value["core"].__setitem__(
                "build_argv_sha256", "c" * 64
            ),
            "job derivation": lambda value: value["core"].__setitem__(
                "job_derivation_sha256", "c" * 64
            ),
            "zero executable": lambda value: value["core"][
                "executable"
            ].__setitem__("sha256", "0" * 64),
            "extra field": lambda value: value["core"].__setitem__(
                "unreviewed", True
            ),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                with self.assertRaises(GoldbachBuildAdmissionError):
                    load_build_admission(
                        self._mutated_admission(mutation),
                        allow_test_fixture=True,
                    )

    def test_factory_is_disabled_without_an_admission(self) -> None:
        group = h100_group()
        self.assertFalse(source_reviewed_materializer_available(group))
        self.assertIsNone(factory_for_portfolio_group(group, 0))
        self.assertTrue(
            source_reviewed_materializer_available(group, self.admission)
        )
        self.assertIsNotNone(
            factory_for_portfolio_group(group, 0, self.admission)
        )

    def test_execution_projection_commits_every_operational_job_boundary(self) -> None:
        job = _projection_job(7, self.admission)
        expected = goldbach_execution_projection_sha256(job)
        self.assertEqual(
            expected_execution_projection_sha256(7, self.admission), expected
        )
        mutations = {
            "command argv": lambda value: value["command"]["argv"].append(
                "--unsafe"
            ),
            "closure": lambda value: value["artifact_closure"].__setitem__(
                "manifest_sha256", "c" * 64
            ),
            "runner policy": lambda value: value["runner_policy"].__setitem__(
                "sha256", "c" * 64
            ),
            "target profile": lambda value: value["target_profile"].__setitem__(
                "sha256", "c" * 64
            ),
            "trust profile": lambda value: value["trust_profile"].__setitem__(
                "sha256", "c" * 64
            ),
            "pre-run gate": lambda value: value["gpu_pre_run_gate"].__setitem__(
                "required", False
            ),
            "input": lambda value: value["input_artifact"].__setitem__(
                "sha256", "c" * 64
            ),
            "TPM selection": lambda value: value["tpm_policy"].__setitem__(
                "pcr_selection", "sha256:23"
            ),
        }
        for name, mutation in mutations.items():
            changed = copy.deepcopy(job)
            mutation(changed)
            with self.subTest(name=name):
                self.assertNotEqual(
                    goldbach_execution_projection_sha256(changed), expected
                )

    def test_algorithm_id_is_checked_before_non_circular_normalization(self) -> None:
        job = _projection_job(2, self.admission)
        baseline = goldbach_execution_projection(job)
        changed = copy.deepcopy(job)
        changed["algorithm"]["canonical_definition"] = "separately signed"
        changed["algorithm"]["definition_sha256"] = "c" * 64
        self.assertEqual(goldbach_execution_projection(changed), baseline)

        for location in ("command", "trace"):
            changed = copy.deepcopy(job)
            argv = (
                changed["command"]["argv"]
                if location == "command"
                else changed["work_trace_contract"]["verifier_argv"]
            )
            position = argv.index("--algorithm-id") + 1
            argv[position] = "sparkinterval.tg.goldbach10pow27.h100-group." + "c" * 64
            with self.subTest(location=location):
                with self.assertRaisesRegex(
                    GoldbachBuildAdmissionError, "differs from the signed job"
                ):
                    goldbach_execution_projection(changed)

        changed = copy.deepcopy(job)
        changed["unexpected"] = "not projected"
        with self.assertRaisesRegex(GoldbachBuildAdmissionError, "wrong fields"):
            goldbach_execution_projection(changed)

    def test_admission_substitution_changes_signed_algorithm_and_input(self) -> None:
        changed_path = self._mutated_admission(
            lambda value: value["expected_artifacts"].__setitem__(
                "source_tree_hash", "c" * 64
            )
        )
        changed = load_build_admission(changed_path, allow_test_fixture=True)
        self.assertNotEqual(
            h100_expected_claim_identity(9, self.admission),
            h100_expected_claim_identity(9, changed),
        )
        self.assertNotEqual(
            expected_execution_projection_sha256(9, self.admission),
            expected_execution_projection_sha256(9, changed),
        )

    def test_dynamic_runtime_image_substitution_is_rejected_or_rebound(self) -> None:
        stale_image = self._mutated_admission(
            lambda value: value["deployment"].__setitem__(
                "immutable_image_reference",
                value["deployment"]["immutable_image_reference"].replace(
                    "1.0.0", "1.0.1"
                ),
            )
        )
        with self.assertRaisesRegex(
            GoldbachBuildAdmissionError, "image reference digest differs"
        ):
            load_build_admission(stale_image, allow_test_fixture=True)

        stale_runtime = self._mutated_admission(
            lambda value: value["deployment"].__setitem__(
                "runtime_image_closure_sha256", "c" * 64
            )
        )
        with self.assertRaisesRegex(
            GoldbachBuildAdmissionError, "runtime/image closure digest differs"
        ):
            load_build_admission(stale_runtime, allow_test_fixture=True)

        def rebind(value):
            deployment = value["deployment"]
            deployment["immutable_image_reference"] = deployment[
                "immutable_image_reference"
            ].replace("1.0.0", "1.0.1")
            deployment["immutable_image_reference_sha256"] = hashlib.sha256(
                deployment["immutable_image_reference"].encode("utf-8")
            ).hexdigest()
            deployment["runtime_image_closure_sha256"] = hashlib.sha256(
                canonical_json_bytes(runtime_image_closure_value(deployment))
            ).hexdigest()

        rebound = load_build_admission(
            self._mutated_admission(rebind), allow_test_fixture=True
        )
        self.assertNotEqual(
            h100_expected_claim_identity(11, self.admission),
            h100_expected_claim_identity(11, rebound),
        )
        self.assertNotEqual(
            expected_execution_projection_sha256(11, self.admission),
            expected_execution_projection_sha256(11, rebound),
        )

    def test_gpu_executable_role_is_the_h100_device_identity(self) -> None:
        result = b'{"status":"ok"}\n'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output.json"
            output.write_bytes(result)
            statement = {
                "algorithm": {
                    "algorithm_id": "test",
                    "definition_sha256": "1" * 64,
                },
                "build_artifacts": [
                    {"role": "source_tree", "sha256": "2" * 64},
                    {"role": "host_executable", "sha256": "3" * 64},
                    {"role": "gpu_executable", "sha256": "4" * 64},
                    {"role": "execution_manifest", "sha256": "5" * 64},
                ],
                "domain_coverage": {"canonical_sha256": "6" * 64},
                "input_artifact": {"sha256": "7" * 64},
                "nonce": "8" * 64,
                "output_artifact": {
                    "path": "output.json",
                    "sha256": hashlib.sha256(result).hexdigest(),
                    "size_bytes": len(result),
                },
                "parameters": {"canonical_sha256": "9" * 64},
                "target_profile": {
                    "profile_id": "azure_ncc40ads_h100_v5",
                    "sha256": "a" * 64,
                },
                "trust_profile": {
                    "profile_id": "azure_ncc_sevsnp_vtpm_nvidia_cc_attested",
                    "sha256": "b" * 64,
                },
            }
            claim = claim_from_bundle(
                {"statement": statement}, root, "azure_ncc40ads_h100_v5"
            )
            self.assertEqual(claim["artifacts"]["device_cubin_hash"], "4" * 64)
            statement["build_artifacts"][2]["role"] = "producer_executable"
            with self.assertRaisesRegex(
                ReceiptError, "exactly one GPU execution artifact"
            ):
                claim_from_bundle(
                    {"statement": statement},
                    root,
                    "azure_ncc40ads_h100_v5",
                )


if __name__ == "__main__":
    unittest.main()
