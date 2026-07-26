# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the attested-provenance prototype.

These cover the three prototype pieces that can be checked without a network,
a cloud account, or a workflow run:

- the N-way replication record validator and its rejection paths;
- the build-manifest cross-check in ``tools/verify_build_provenance.py``; and
- the structural guarantees of the provenance workflow, in particular that it
  cannot be triggered by a push and that its signing job is separated from its
  build steps.

They also assert the containment property that matters most: the new backend
must remain invisible to the confidential-compute receipt path.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.attested_provenance import (  # noqa: E402
    AttestedProvenanceError,
    validate_record,
)

EXAMPLE = (
    ROOT / "examples" / "attested-provenance" / "replication_record.example.json"
)


def _example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


class ReplicationRecordTest(unittest.TestCase):
    def test_example_record_is_accepted(self) -> None:
        evaluation = validate_record(_example())
        self.assertTrue(evaluation["accepted"], evaluation["failures"])
        self.assertEqual(evaluation["agreement"]["distinct_merkle_roots"], 1)
        self.assertEqual(evaluation["agreement"]["replica_count"], 3)

    def test_example_record_claims_no_authority(self) -> None:
        evaluation = validate_record(_example())
        for key, value in evaluation["authority"].items():
            self.assertFalse(value, f"{key} must stay false")

    def test_disagreeing_merkle_root_is_rejected(self) -> None:
        record = _example()
        record["replicas"][1]["execution"]["merkle_root"] = "f" * 64
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any("Merkle root" in failure for failure in evaluation["failures"]),
            evaluation["failures"],
        )

    def test_disagreeing_output_hash_is_rejected(self) -> None:
        record = _example()
        record["replicas"][0]["execution"]["output_hash"] = "a" * 64
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any("output digest" in failure for failure in evaluation["failures"]),
            evaluation["failures"],
        )

    def test_missing_third_party_replica_is_rejected(self) -> None:
        record = _example()
        for replica in record["replicas"]:
            replica["operator_is_third_party"] = False
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any("third party" in failure for failure in evaluation["failures"]),
            evaluation["failures"],
        )

    def test_single_implementation_is_rejected(self) -> None:
        record = _example()
        record["replicas"][1]["implementation_id"] = "cuda_word_owner_v3"
        record["replicas"][1]["build_provenance"]["artifacts"] = copy.deepcopy(
            record["replicas"][0]["build_provenance"]["artifacts"]
        )
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any(
                "distinct implementations" in failure
                for failure in evaluation["failures"]
            ),
            evaluation["failures"],
        )

    def test_same_implementation_with_different_bytes_is_rejected(self) -> None:
        record = _example()
        record["replicas"][2]["build_provenance"]["artifacts"][0]["sha256"] = "b" * 64
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any(
                "different artifact sets" in failure
                for failure in evaluation["failures"]
            ),
            evaluation["failures"],
        )

    def test_unverified_build_provenance_is_rejected(self) -> None:
        record = _example()
        record["replicas"][0]["build_provenance"]["verification"]["accepted"] = False
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any(
                "build provenance was not verified" in failure
                for failure in evaluation["failures"]
            ),
            evaluation["failures"],
        )

    def test_missing_transparency_log_is_rejected(self) -> None:
        record = _example()
        del record["replicas"][1]["build_provenance"]["transparency_log"]
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any(
                "transparency-log" in failure for failure in evaluation["failures"]
            ),
            evaluation["failures"],
        )

    def test_self_hosted_build_provenance_is_rejected(self) -> None:
        record = _example()
        record["replicas"][0]["build_provenance"][
            "runner_environment"
        ] = "self-hosted"
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any("self-hosted runner" in f for f in evaluation["failures"]),
            evaluation["failures"],
        )
        self.assertEqual(
            evaluation["build_provenance"]["self_hosted_build_replicas"],
            ["replica-a-cuda"],
        )

    def test_undeclared_runner_environment_is_rejected(self) -> None:
        record = _example()
        del record["replicas"][2]["build_provenance"]["runner_environment"]
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any("runner environment" in f for f in evaluation["failures"]),
            evaluation["failures"],
        )

    def test_self_hosted_build_is_allowed_when_policy_does_not_require_it(
        self,
    ) -> None:
        record = _example()
        record["policy"]["require_github_hosted_build_provenance"] = False
        record["replicas"][0]["build_provenance"][
            "runner_environment"
        ] = "self-hosted"
        evaluation = validate_record(record)
        self.assertTrue(evaluation["accepted"], evaluation["failures"])
        # The weakness is still reported even when it is tolerated.
        self.assertEqual(
            evaluation["build_provenance"]["self_hosted_build_replicas"],
            ["replica-a-cuda"],
        )

    def test_slsa_l3_claim_is_rejected(self) -> None:
        record = _example()
        record["replicas"][0]["build_provenance"]["slsa_build_level"] = "L3"
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any("Build L3" in failure for failure in evaluation["failures"]),
            evaluation["failures"],
        )

    def test_authority_claim_is_rejected_by_the_schema(self) -> None:
        record = _example()
        record["authority"]["authorizes_lean_theorem"] = True
        with self.assertRaises(AttestedProvenanceError):
            validate_record(record)

    def test_confidential_backend_identifier_is_rejected(self) -> None:
        record = _example()
        record["backend"] = "azure_sevsnp_cpu"
        with self.assertRaises(AttestedProvenanceError):
            validate_record(record)

    def test_duplicate_replica_ids_are_rejected(self) -> None:
        record = _example()
        record["replicas"][2]["replica_id"] = record["replicas"][0]["replica_id"]
        evaluation = validate_record(record)
        self.assertFalse(evaluation["accepted"])
        self.assertTrue(
            any("duplicate replica_id" in f for f in evaluation["failures"]),
            evaluation["failures"],
        )


class ConfidentialComputePathUntouchedTest(unittest.TestCase):
    """The prototype must not become reachable from the trusted receipt path."""

    def test_receipt_schema_backend_enum_excludes_the_new_backend(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "trusted-compute-receipt.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            schema["properties"]["backend"]["enum"],
            ["azure_sevsnp_cpu", "azure_ncc40ads_h100_v5"],
        )

    def test_receipt_tool_backends_exclude_the_new_backend(self) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        import trusted_compute_receipt  # noqa: PLC0415

        self.assertNotIn(
            "attested_provenance_replicated", trusted_compute_receipt.BACKENDS
        )
        self.assertEqual(
            trusted_compute_receipt.BACKENDS,
            ("azure_sevsnp_cpu", "azure_ncc40ads_h100_v5"),
        )

    def test_new_trust_profile_is_not_hardware_evidence(self) -> None:
        profile = json.loads(
            (
                ROOT / "profiles" / "trust" / "attested_provenance_replicated.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(profile["evidence_class"], "local_unattested")
        self.assertFalse(profile["production_hardware_evidence"])
        self.assertFalse(profile["requires_hardware_attestation"])


class BuildManifestCheckTest(unittest.TestCase):
    TOOL = ROOT / "tools" / "verify_build_provenance.py"

    def _run(self, *argv: str) -> tuple[int, dict]:
        completed = subprocess.run(
            [sys.executable, str(self.TOOL), *argv],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.returncode, json.loads(completed.stdout)

    def test_manifest_matching_bytes_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "artifacts").mkdir()
            payload = b"deterministic bytes\n"
            (root / "artifacts" / "example.bin").write_bytes(payload)
            import hashlib

            manifest = {
                "artifacts": [
                    {
                        "name": "example.bin",
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "size_bytes": len(payload),
                    }
                ],
                "commit": "0" * 40,
                "kind": "sparkinterval.attested-provenance-build-manifest.v1",
                "schema_version": 1,
            }
            (root / "build-manifest.json").write_text(json.dumps(manifest))
            code, record = self._run(
                "check-manifest", str(root / "build-manifest.json")
            )
            self.assertEqual(code, 0, record)
            self.assertTrue(record["accepted"])
            self.assertEqual(record["status"], "manifest_matches_bytes")

    def test_tampered_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "artifacts").mkdir()
            (root / "artifacts" / "example.bin").write_bytes(b"tampered\n")
            manifest = {
                "artifacts": [
                    {"name": "example.bin", "sha256": "c" * 64, "size_bytes": 9}
                ],
                "commit": "0" * 40,
                "kind": "sparkinterval.attested-provenance-build-manifest.v1",
                "schema_version": 1,
            }
            (root / "build-manifest.json").write_text(json.dumps(manifest))
            code, record = self._run(
                "check-manifest", str(root / "build-manifest.json")
            )
            self.assertEqual(code, 1)
            self.assertFalse(record["accepted"])
            self.assertEqual(record["status"], "manifest_mismatch")

    def test_verification_record_disclaims_execution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "artifacts").mkdir()
            (root / "build-manifest.json").write_text("{}")
            _, record = self._run(
                "check-manifest", str(root / "build-manifest.json")
            )
            self.assertFalse(record["authority"]["attests_that_a_computation_ran"])
            self.assertFalse(record["authority"]["replaces_execution_evidence"])
            self.assertFalse(record["authority"]["authorizes_lean_theorem"])


class ProvenanceWorkflowTest(unittest.TestCase):
    WORKFLOW = ROOT / ".github" / "workflows" / "build-provenance.yml"

    def setUp(self) -> None:
        try:
            import yaml  # noqa: PLC0415
        except ImportError:  # pragma: no cover
            self.skipTest("PyYAML is not installed")
        self.document = yaml.safe_load(
            self.WORKFLOW.read_text(encoding="utf-8")
        )
        # PyYAML resolves the bare `on:` key to the boolean True.
        self.triggers = self.document.get("on", self.document.get(True))

    def test_workflow_cannot_be_triggered_by_a_push(self) -> None:
        self.assertEqual(list(self.triggers), ["workflow_dispatch"])

    def test_default_permissions_are_empty(self) -> None:
        self.assertEqual(self.document["permissions"], {})

    def test_only_the_attest_job_can_sign(self) -> None:
        jobs = self.document["jobs"]
        for name, job in jobs.items():
            permissions = job.get("permissions", {})
            if name == "attest":
                self.assertEqual(permissions.get("id-token"), "write")
                self.assertEqual(permissions.get("attestations"), "write")
            else:
                self.assertNotIn("id-token", permissions)
                self.assertNotIn("attestations", permissions)

    def test_signing_job_runs_no_repository_build_step(self) -> None:
        steps = self.document["jobs"]["attest"]["steps"]
        uses = [step.get("uses", "") for step in steps]
        self.assertTrue(
            any(u.startswith("actions/attest-build-provenance@") for u in uses)
        )
        for step in steps:
            run = step.get("run", "")
            self.assertNotIn("reproduce_attested_build.sh", run)
            self.assertNotIn("make ", run)

    def test_every_action_is_pinned_to_a_commit_sha(self) -> None:
        for job in self.document["jobs"].values():
            for step in job["steps"]:
                uses = step.get("uses")
                if uses is None:
                    continue
                _, _, reference = uses.partition("@")
                self.assertEqual(
                    len(reference),
                    40,
                    f"{uses} must be pinned to a full commit SHA",
                )
                int(reference, 16)

    def test_container_images_are_digest_pinned(self) -> None:
        for name, job in self.document["jobs"].items():
            container = job.get("container")
            if container is None:
                continue
            image = container["image"] if isinstance(container, dict) else container
            self.assertIn("@sha256:", image, f"job {name} image must be pinned")

    def test_reproducible_rebuild_job_exists(self) -> None:
        self.assertIn("independent-rebuild", self.document["jobs"])

    def test_every_job_refuses_a_self_hosted_runner(self) -> None:
        for name, job in self.document["jobs"].items():
            first = job["steps"][0]
            self.assertEqual(
                first["name"],
                "Require a GitHub-hosted runner",
                f"job {name} must assert its runner class first",
            )
            self.assertIn("RUNNER_ENVIRONMENT", first["run"])
            self.assertIn("github-hosted", first["run"])

    def test_no_job_targets_a_self_hosted_runner_label(self) -> None:
        for name, job in self.document["jobs"].items():
            runs_on = job["runs-on"]
            labels = runs_on if isinstance(runs_on, list) else [runs_on]
            self.assertNotIn("self-hosted", labels, f"job {name}")
            for label in labels:
                self.assertTrue(
                    str(label).startswith("ubuntu-"),
                    f"job {name} must use a GitHub-hosted Ubuntu runner",
                )


if __name__ == "__main__":
    unittest.main()
