# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:  # The repository has no mandatory third-party Python test dependency.
    jsonschema = None


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_SCHEMA = REPOSITORY_ROOT / "schemas/azure-h100-production-campaign.schema.json"
REDACTED_CAMPAIGN = (
    REPOSITORY_ROOT
    / "examples/trusted-compute/azure_h100_production_campaign.redacted.json"
)


def load_module():
    specification = importlib.util.spec_from_file_location(
        "gpu_prover_h100_production_orchestrator",
        REPOSITORY_ROOT / "azure/h100_production_orchestrator.py",
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


orchestrator = load_module()


def write_bytes(path: Path, content: bytes, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)
    return path


def write_json(path: Path, value: object, mode: int = 0o600) -> Path:
    return write_bytes(path, orchestrator.canonical_json_bytes(value), mode)


def file_pin(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def policy_pin(path: Path, policy_id: str) -> dict[str, object]:
    return {
        **file_pin(path),
        "classification": "production",
        "policy_id": policy_id,
    }


def valid_deployment(config: dict[str, object]) -> dict[str, object]:
    azure = config["azure"]
    assert isinstance(azure, dict)
    return {
        "accepted": True,
        "attestation_collected": False,
        "classification": "azure_ncc_h100_vms_created",
        "public_ip_addresses": False,
        "resolved_image": azure["image"],
        "resource_group": azure["resource_group"],
        "resources_proven_attested": 0,
        "subnet_default_outbound_access": False,
        "subnet_id": azure["subnet_id"],
        "virtual_machines": [
            {
                "id": (
                    "/subscriptions/sub-123/resourceGroups/tg-production/"
                    "providers/Microsoft.Compute/virtualMachines/tg-h100-0"
                ),
                "image": azure["image"],
                "private_ip_address": "10.0.0.4",
                "provisioning_state": "Succeeded",
                "public_ip_address_resource_id": None,
                "secure_boot_enabled": True,
                "security_type": "ConfidentialVM",
                "sku": orchestrator.VM_SIZE,
                "vtpm_enabled": True,
            }
        ],
    }


class CampaignFixture:
    def __init__(self, root: Path):
        self.root = root
        self.inputs = root / "inputs"
        self.review = root / "review"
        self.image = (
            "/subscriptions/sub-123/resourceGroups/image-rg/providers/"
            "Microsoft.Compute/galleries/secure/images/ncc-h100/versions/1.2.3"
        )
        self.maa_url = (
            "https://fixture.eus2.attest.azure.net/attest/SevSnpVm"
            "?api-version=2022-08-01"
        )
        self.job_path = write_json(self.inputs / "artifact-root/job.json", {"fixture": True})
        self.job_hash = file_pin(self.job_path)["sha256"]
        self.package_path = write_bytes(self.inputs / "workload.tar", b"immutable-package")
        self.ssh_key = write_bytes(self.inputs / "operator.pub", b"ssh-ed25519 fixture\n", 0o400)

        self.runner_policy = write_json(
            self.inputs / "runner-policy.json",
            {
                "classification": "production",
                "immutable_image_reference": self.image,
                "immutable_image_reference_sha256": hashlib.sha256(
                    self.image.encode("utf-8")
                ).hexdigest(),
                "kind": "sparkinterval_measured_runner_policy",
                "policy_id": "sparkinterval.runner.azure-h100.production.v1",
                "production_ready": True,
                "required_claims": [
                    "challenge_received_before_pcr_start",
                    "ordered_pcr23_start_and_result_extensions",
                    "exact_argv_without_shell",
                    "challenge_dependent_work_trace",
                    "fresh_exclusive_output",
                    "retained_off_vm_challenge_match",
                    "immutable_image_and_runtime_closure",
                ],
                "schema_version": 1,
            },
        )
        self.transcript_policy = write_json(
            self.inputs / "transcript-policy.json",
            {
                "allowed_backends": [orchestrator.BACKEND],
                "allowed_job_spec_sha256": [self.job_hash],
                "allowed_runner_policy_sha256": [file_pin(self.runner_policy)["sha256"]],
                "allowed_target_profile_sha256": ["22" * 32],
                "allowed_trust_profile_sha256": ["33" * 32],
                "classification": "production",
                "kind": "sparkinterval_measured_runner_appraisal_policy",
                "policy_id": "sparkinterval.transcript.azure-h100.production.v1",
                "require_authenticated_hardware_quote": True,
                "required_composite_appraiser_claims": [
                    "measured_runner_policy_valid",
                    "result_artifact_bound_to_execution",
                ],
                "schema_version": 1,
            },
        )
        self.nvidia_policy = write_bytes(
            self.inputs / "nvidia-production.rego",
            b"package gpu_prover\n\ndefault nv_match := false\n",
        )
        self.azure_child = write_bytes(
            self.inputs / "azure-appraiser", b"#!/bin/sh\nexit 2\n", 0o500
        )
        self.nvidia_child = write_bytes(
            self.inputs / "nvidia-appraiser", b"#!/bin/sh\nexit 2\n", 0o500
        )
        self.azure_child_policy = write_json(
            self.inputs / "azure-child-policy.json", {"fixture": "production"}
        )
        self.nvidia_child_policy = write_json(
            self.inputs / "nvidia-child-policy.json", {"fixture": "production"}
        )
        self.composite_policy = write_json(
            self.inputs / "composite-policy.json",
            {
                "allowed_backends": [orchestrator.BACKEND],
                "azure_appraiser": {
                    "executable_path": str(self.azure_child),
                    "executable_sha256": file_pin(self.azure_child)["sha256"],
                    "maa_accepted_audience": "fixture-audience",
                    "maa_accepted_issuer": "https://fixture.eus2.attest.azure.net",
                    "maa_accepted_provider": "maa_snp",
                    "maa_attestation_url": self.maa_url,
                    "policy_path": str(self.azure_child_policy),
                    "policy_sha256": file_pin(self.azure_child_policy)["sha256"],
                    "timeout_seconds": 300,
                },
                "kind": "sparkinterval_azure_evidence_appraisal_policy",
                "nvidia_appraiser": {
                    "executable_path": str(self.nvidia_child),
                    "executable_sha256": file_pin(self.nvidia_child)["sha256"],
                    "nras_url": "https://nras.attestation.nvidia.com",
                    "policy_path": str(self.nvidia_child_policy),
                    "policy_sha256": file_pin(self.nvidia_child_policy)["sha256"],
                    "timeout_seconds": 300,
                    "verifier": "remote",
                },
                "schema_version": 1,
            },
        )
        self.evidence_verifier = write_bytes(
            self.inputs / "evidence-verifier", b"#!/bin/sh\nexit 2\n", 0o500
        )
        self.public_key = write_bytes(
            self.inputs / "production-public.pem", b"production-public-key-fixture\n", 0o400
        )
        self.target_hash = "22" * 32
        self.trust_hash = "33" * 32
        self.key_id = "sparkinterval-azure-h100-production-2026-07"
        self.key_manifest = write_json(
            self.inputs / "key-manifest.json",
            {
                "keys": [
                    {
                        "allowed_verifier_profiles": [
                            {
                                "backend": orchestrator.BACKEND,
                                "target_profile_sha256": self.target_hash,
                                "trust_profile_sha256": self.trust_hash,
                                "verifier_artifact_sha256": file_pin(
                                    self.evidence_verifier
                                )["sha256"],
                                "verifier_policy_sha256": file_pin(
                                    self.composite_policy
                                )["sha256"],
                            }
                        ],
                        "classification": "production",
                        "key_id": self.key_id,
                        "public_key_path": self.public_key.name,
                        "public_key_sha256": file_pin(self.public_key)["sha256"],
                    }
                ],
                "schema_version": 1,
            },
        )
        worker_root = root / "guest"
        self.config = {
            "azure": {
                "admin_username": "sparkoperator",
                "image": self.image,
                "location": "eastus2",
                "name_prefix": "tg-h100",
                "nodes": 1,
                "os_disk_size_gb": 256,
                "resource_group": "tg-production",
                "ssh_public_key": file_pin(self.ssh_key),
                "subnet_id": (
                    "/subscriptions/sub-123/resourceGroups/network-rg/providers/"
                    "Microsoft.Network/virtualNetworks/private-vnet/subnets/h100"
                ),
                "subscription_id": "sub-123",
                "vm_size": orchestrator.VM_SIZE,
                "zone": "1",
            },
            "campaign_id": "tg-h100-production-2026-07",
            "challenge": {
                "mode": "operator_generated_fresh_v1",
                "pin": None,
                "shard_index": 0,
            },
            "challenge_ttl_seconds": 86400,
            "handoffs": {
                "returned_certificate_archive": str(root / "handoff/returned.tar"),
                "returned_worker_completion": str(root / "handoff/completion.json"),
                "worker_stage_manifest": str(root / "handoff/stage.json"),
            },
            "kind": orchestrator.CONFIG_KIND,
            "lean_review": {
                "namespace": "ReviewedH100Candidate",
                "registered_invocation": "h100FormalPtxConstantOneV1",
            },
            "managed_hsm": {
                "key_id": self.key_id,
                "key_manifest": file_pin(self.key_manifest),
                "key_uri": (
                    "https://fixture.managedhsm.azure.net/keys/tg-production/"
                    "0123456789abcdef0123456789abcdef"
                ),
                "public_key": file_pin(self.public_key),
            },
            "outputs": {
                "appraisal_report": str(self.review / "reports/appraisal.json"),
                "challenge_dir": str(self.review / "challenge"),
                "deployment_record": str(self.review / "deployment.json"),
                "extracted_certificate_package": str(self.review / "returned"),
                "lean_candidate": str(self.review / "candidates/Certificate.lean"),
                "receipt": str(self.review / "receipt.json"),
                "registry_candidate": str(
                    self.review / "candidates/TrustedComputeRegistry.lean"
                ),
                "replay_db": str(self.review / "replay/receipts.sqlite3"),
                "review_root": str(self.review),
                "state": str(self.review / "operator-state.json"),
                "transcript_report": str(self.review / "reports/transcript.json"),
            },
            "policies": {
                "composite_appraisal": policy_pin(
                    self.composite_policy, "sparkinterval.composite.azure-h100.production.v1"
                ),
                "evidence_verifier": file_pin(self.evidence_verifier),
                "nvidia": policy_pin(
                    self.nvidia_policy, "sparkinterval.nvidia.h100.production.v1"
                ),
                "runner": policy_pin(
                    self.runner_policy, "sparkinterval.runner.azure-h100.production.v1"
                ),
                "transcript_appraisal": policy_pin(
                    self.transcript_policy,
                    "sparkinterval.transcript.azure-h100.production.v1",
                ),
            },
            "schema_version": 1,
            "worker": {
                "artifact_root": str(worker_root / "artifact-root"),
                "certificate_archive": str(worker_root / "certificate.tar"),
                "certificate_package": str(worker_root / "certificate-package"),
                "challenge": str(worker_root / "challenge.json"),
                "completion_manifest": str(worker_root / "completion.json"),
                "gpu_verifier": "remote",
                "job_spec": str(worker_root / "artifact-root/job.json"),
                "maa_attestation_url": self.maa_url,
                "nras_url": "https://nras.attestation.nvidia.com",
                "nvidia_policy": str(worker_root / "policies/nvidia.rego"),
                "run_package": str(worker_root / "measured-run"),
                "stage_manifest": str(worker_root / "stage.json"),
                "transcript_appraisal_policy": str(
                    worker_root / "policies/transcript.json"
                ),
                "workload_package": str(worker_root / "workload.tar"),
            },
            "workload": {
                "artifact_root": str(self.job_path.parent),
                "job_spec": file_pin(self.job_path),
                "package": file_pin(self.package_path),
            },
        }
        self.config_path = write_json(root / "campaign.json", self.config)

    def validated_job(self) -> dict[str, object]:
        registered = orchestrator.registered_invocation_expected(
            "h100FormalPtxConstantOneV1"
        )
        return {
            "algorithm": {
                "algorithm_id": registered["algorithm_id"],
                "definition_sha256": registered["algorithm_hash"],
            },
            "backend": orchestrator.BACKEND,
            "command": {"timeout_seconds": 3600},
            "domain_coverage": {"canonical_sha256": registered["domain_hash"]},
            "gpu_pre_run_gate": {"timeout_seconds": 600},
            "input_artifact": {"sha256": registered["input_hash"]},
            "parameters": {"canonical_sha256": registered["parameters_hash"]},
            "runner_policy": {"sha256": file_pin(self.runner_policy)["sha256"]},
            "target_profile": {
                "profile_id": orchestrator.TARGET_PROFILE_ID,
                "sha256": self.target_hash,
            },
            "trust_profile": {
                "profile_id": orchestrator.TRUST_PROFILE_ID,
                "sha256": self.trust_hash,
            },
        }

    def write_config(self, value: dict[str, object] | None = None) -> None:
        write_json(self.config_path, self.config if value is None else value)

    def load(self):
        with mock.patch.object(
            orchestrator, "validate_job_spec", return_value=self.validated_job()
        ):
            return orchestrator.load_config(self.config_path)


class H100ProductionOrchestratorTests(unittest.TestCase):
    def test_redacted_example_and_cli_help_are_current(self):
        schema = json.loads(CAMPAIGN_SCHEMA.read_bytes())
        example_bytes = REDACTED_CAMPAIGN.read_bytes()
        example = json.loads(example_bytes)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), orchestrator.CONFIG_KEYS)
        for field, expected in (
            ("azure", orchestrator.AZURE_KEYS),
            ("handoffs", orchestrator.HANDOFF_KEYS),
            ("lean_review", orchestrator.LEAN_REVIEW_KEYS),
            ("managed_hsm", orchestrator.HSM_KEYS),
            ("outputs", orchestrator.OUTPUT_KEYS),
            ("policies", orchestrator.POLICIES_KEYS),
            ("worker", orchestrator.WORKER_KEYS),
            ("workload", orchestrator.WORKLOAD_KEYS),
        ):
            self.assertEqual(set(schema["properties"][field]["required"]), expected)
        self.assertIn(
            example_bytes,
            (
                orchestrator.canonical_json_bytes(example),
                orchestrator.canonical_json_bytes(example) + b"\n",
            ),
        )
        self.assertEqual(set(example), orchestrator.CONFIG_KEYS)
        self.assertNotIn("NV_ATTESTATION_SERVICE_KEY", example_bytes.decode("utf-8"))
        help_result = subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / "azure/h100_production_orchestrator.py"), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("record-worker-stage-handoff", help_result.stdout)
        self.assertIn("generate-review-candidates", help_result.stdout)
        runbook = REPOSITORY_ROOT / "docs/AZURE_H100_PRODUCTION_OPERATOR.md"
        self.assertTrue(runbook.is_file())
        self.assertIn(
            "AZURE_H100_PRODUCTION_OPERATOR.md",
            (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8"),
        )
        runbook_text = runbook.read_text(encoding="utf-8")
        self.assertIn("azure-h100-production-campaign.schema.json", runbook_text)
        self.assertIn("azure_h100_production_campaign.redacted.json", runbook_text)
        self.assertIn("sudo -E", runbook_text)
        self.assertIn("Do not use", runbook_text[runbook_text.index("sudo -E") - 20 :])

    @unittest.skipIf(jsonschema is None, "optional jsonschema package is unavailable")
    def test_redacted_example_validates_against_campaign_schema(self):
        schema = json.loads(CAMPAIGN_SCHEMA.read_bytes())
        example = json.loads(REDACTED_CAMPAIGN.read_bytes())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(example)

    def test_valid_campaign_plan_keeps_guest_collectors_and_operator_appraisers_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            plan = orchestrator.command_plan(config, config_hash)
            self.assertFalse(plan["accepted"])
            self.assertEqual(
                plan["classification"], "reviewable_dry_run_no_commands_executed"
            )
            self.assertEqual(len(plan["manual_security_boundaries"]), 3)
            collector = next(
                step["argv"]
                for step in plan["steps"]
                if step["id"] == "no_reset_evidence_collection"
            )
            self.assertNotIn("--maa-command", collector)
            self.assertNotIn("--nvattest", collector)
            self.assertNotIn(str(fixture.azure_child), collector)
            self.assertNotIn(str(fixture.nvidia_child), collector)
            self.assertIn(config["worker"]["nvidia_policy"], collector)
            appraisal = next(
                step["argv"]
                for step in plan["steps"]
                if step["id"] == "hardware_appraise"
            )
            self.assertEqual(appraisal[0], str(fixture.evidence_verifier))
            receipt = next(
                step["argv"]
                for step in plan["steps"]
                if step["id"] == "receipt_issue_hsm"
            )
            self.assertIn(config["outputs"]["replay_db"], receipt)
            verifier_flag = receipt.index("--evidence-verifier")
            self.assertEqual(
                receipt[verifier_flag + 1], config["policies"]["evidence_verifier"]["path"]
            )
            self.assertEqual(receipt.count(config["policies"]["evidence_verifier"]["path"]), 1)
            self.assertEqual(receipt[verifier_flag + 2], "--evidence-policy")
            challenge_argv = next(
                step["argv"] for step in plan["steps"] if step["id"] == "challenge"
            )
            ttl_flag = challenge_argv.index("--ttl-seconds")
            self.assertEqual(challenge_argv[ttl_flag + 1], "86400")
            serialized = json.dumps(plan)
            self.assertNotIn("NV_ATTESTATION_SERVICE_KEY", serialized)
            for step in plan["steps"]:
                self.assertTrue(step["argv"] is None or isinstance(step["argv"], list))

    def test_latest_image_cross_subscription_and_tampered_pin_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            latest = copy.deepcopy(fixture.config)
            latest["azure"]["image"] = latest["azure"]["image"].rsplit("/", 1)[0] + "/latest"
            fixture.write_config(latest)
            with self.assertRaisesRegex(orchestrator.OrchestratorError, "exact versioned"):
                fixture.load()

            cross_subscription = copy.deepcopy(fixture.config)
            cross_subscription["azure"]["subnet_id"] = cross_subscription["azure"][
                "subnet_id"
            ].replace("sub-123", "other-sub")
            fixture.write_config(cross_subscription)
            with self.assertRaisesRegex(orchestrator.OrchestratorError, "selected Azure subscription"):
                fixture.load()

            fixture.write_config()
            fixture.package_path.write_bytes(b"tampered-package")
            with self.assertRaisesRegex(orchestrator.OrchestratorError, "does not match"):
                fixture.load()

    def test_challenge_ttl_must_cover_one_complete_measured_shard(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            too_short = copy.deepcopy(fixture.config)
            too_short["challenge_ttl_seconds"] = (
                3600 + 600 + orchestrator.EVIDENCE_COLLECTION_MARGIN_SECONDS
            )
            fixture.write_config(too_short)
            with self.assertRaisesRegex(orchestrator.OrchestratorError, "one shard must fit"):
                fixture.load()

    def test_selected_closed_invocation_must_be_h100_compatible_and_match_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            cpu_invocation = copy.deepcopy(fixture.config)
            cpu_invocation["lean_review"]["registered_invocation"] = (
                "cubicSumDivThree20000V1"
            )
            fixture.write_config(cpu_invocation)
            with self.assertRaisesRegex(orchestrator.OrchestratorError, "H100-backend-compatible"):
                fixture.load()

            unknown = copy.deepcopy(fixture.config)
            unknown["lean_review"]["registered_invocation"] = "notRegisteredV1"
            fixture.write_config(unknown)
            with self.assertRaisesRegex(orchestrator.OrchestratorError, "not source-supported"):
                fixture.load()

            fixture.write_config()
            mismatched_job = copy.deepcopy(fixture.validated_job())
            mismatched_job["algorithm"]["definition_sha256"] = "ff" * 32
            with mock.patch.object(
                orchestrator, "validate_job_spec", return_value=mismatched_job
            ):
                with self.assertRaisesRegex(
                    orchestrator.OrchestratorError, "selected closed H100 invocation"
                ):
                    orchestrator.load_config(fixture.config_path)

    def test_operational_h100_receipt_has_no_direct_lean_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            operational = copy.deepcopy(fixture.config)
            operational["lean_review"]["registered_invocation"] = None
            fixture.write_config(operational)
            config, config_hash = fixture.load()
            plan = orchestrator.command_plan(config, config_hash)
            self.assertIsNone(
                next(
                    step["argv"] for step in plan["steps"]
                    if step["id"] == "registry_review_candidate"
                )
            )
            self.assertIsNone(
                next(
                    step["argv"] for step in plan["steps"]
                    if step["id"] == "lean_review_candidate"
                )
            )
            with self.assertRaisesRegex(
                orchestrator.OrchestratorError, "operational phase receipts"
            ):
                orchestrator.generate_review_candidates(config, config_hash)

    def test_exact_portfolio_challenge_can_be_adopted_without_regeneration(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            challenge = write_json(
                fixture.root / "portfolio/challenge.json",
                {
                    "campaign_id": fixture.config["campaign_id"],
                    "expires_at_utc": (now + dt.timedelta(hours=24)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "kind": "gpu_prover_azure_run_challenge",
                    "nonce": "5a" * 32,
                    "schema_version": 1,
                    "shard_index": 17,
                },
            )
            pinned = copy.deepcopy(fixture.config)
            pinned["challenge"] = {
                "mode": "pinned_portfolio_handoff_v1",
                "pin": file_pin(challenge),
                "shard_index": 17,
            }
            fixture.write_config(pinned)
            config, config_hash = fixture.load()
            self.assertIsNone(
                next(
                    step["argv"] for step in orchestrator.command_plan(
                        config, config_hash
                    )["steps"] if step["id"] == "challenge"
                )
            )
            orchestrator.initialize_state(config, config_hash)
            deployment = write_json(
                Path(config["outputs"]["deployment_record"]),
                valid_deployment(config),
            )
            orchestrator._transition(
                config, config_hash, "initialized", "azure_deployed",
                record_name="deployment_record_sha256",
                record_sha256=file_pin(deployment)["sha256"],
            )
            result = orchestrator.create_challenge_step(config, config_hash)
            self.assertEqual(result["nonce"], "5a" * 32)
            self.assertEqual(
                orchestrator._challenge_path(config).read_bytes(), challenge.read_bytes()
            )

    def test_failed_deploy_enters_manual_reconciliation_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            orchestrator.initialize_state(config, config_hash)

            def denied(argv, timeout):
                del timeout
                return subprocess.CompletedProcess(argv, 2, b"", b"capacity denied")

            with self.assertRaisesRegex(orchestrator.OrchestratorError, "child command failed"):
                orchestrator.deploy(config, config_hash, denied)
            state = orchestrator.load_state(config, config_hash)
            self.assertFalse(state["accepted"])
            self.assertEqual(
                state["stage"],
                "azure_deployment_failed_or_unknown_manual_reconciliation_required",
            )
            deployment_path = Path(config["outputs"]["deployment_record"])
            write_json(deployment_path, valid_deployment(config))
            adopted = orchestrator.reconcile_deployment(config, config_hash)
            self.assertEqual(adopted, valid_deployment(config))
            self.assertEqual(
                orchestrator.load_state(config, config_hash)["stage"],
                "azure_deployed",
            )
            self.assertEqual(
                orchestrator.deploy(config, config_hash),
                valid_deployment(config),
            )

    def test_init_and_reconciliation_commands_are_explicitly_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            first = orchestrator.initialize_state(config, config_hash)
            second = orchestrator.initialize_state(config, config_hash)
            self.assertEqual(first, second)
            help_text = orchestrator.build_parser().format_help()
            for command in (
                "reconcile-deployment",
                "reconcile-challenge",
                "reconcile-receipt",
            ):
                self.assertIn(command, help_text)

    def test_manual_stage_manifest_binds_guest_policy_bytes_and_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            write_json(
                Path(config["outputs"]["deployment_record"]),
                {
                    "virtual_machines": [
                        {
                            "id": "/subscriptions/sub-123/resourceGroups/tg/providers/"
                            "Microsoft.Compute/virtualMachines/tg-h100-0",
                            "private_ip_address": "10.0.0.4",
                            "sku": orchestrator.VM_SIZE,
                        }
                    ]
                },
            )
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            write_json(
                orchestrator._challenge_path(config),
                {
                    "campaign_id": config["campaign_id"],
                    "expires_at_utc": (now + dt.timedelta(hours=1)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "issued_at_utc": (now - dt.timedelta(minutes=1)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "kind": "gpu_prover_azure_run_challenge",
                    "nonce": "42" * 32,
                    "schema_version": 1,
                    "shard_index": 0,
                },
            )
            expected = orchestrator._stage_manifest_expected(config, config_hash)
            self.assertEqual(
                expected["worker_input_bindings"]["nvidia_policy"]["path"],
                config["worker"]["nvidia_policy"],
            )
            self.assertEqual(
                expected["worker_input_bindings"]["nvidia_policy"]["sha256"],
                config["policies"]["nvidia"]["sha256"],
            )
            orchestrator._validate_worker_manifest_local(expected, config, config_hash)
            changed = copy.deepcopy(expected)
            changed["worker_input_bindings"]["nvidia_policy"]["sha256"] = "00" * 32
            with self.assertRaisesRegex(orchestrator.OrchestratorError, "input bindings"):
                orchestrator._validate_worker_manifest_local(changed, config, config_hash)
            orchestrator.initialize_state(config, config_hash)
            deployment_hash = orchestrator._sha256_file(
                Path(config["outputs"]["deployment_record"])
            )[0]
            challenge_hash = orchestrator._sha256_file(
                orchestrator._challenge_path(config)
            )[0]
            orchestrator._transition(
                config,
                config_hash,
                "initialized",
                "azure_deployed",
                record_name="deployment_record_sha256",
                record_sha256=deployment_hash,
            )
            orchestrator._transition(
                config,
                config_hash,
                "azure_deployed",
                "challenge_created_awaiting_manual_worker_stage",
                record_name="retained_challenge_sha256",
                record_sha256=challenge_hash,
            )
            recorded = orchestrator.record_worker_stage_handoff(
                config, config_hash, confirmed=True
            )
            self.assertFalse(recorded["accepted"])
            self.assertEqual(
                json.loads(Path(recorded["manifest_path"]).read_bytes()), expected
            )
            orchestrator.acknowledge_worker_stage(config, config_hash)
            self.assertEqual(orchestrator.load_state(config, config_hash)["stage"], "worker_stage_confirmed")

    def test_worker_validation_does_not_dereference_operator_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            fixture.load()
            fixture.runner_policy.unlink()
            fixture.composite_policy.unlink()
            fixture.evidence_verifier.unlink()
            config, config_hash = orchestrator.load_worker_config(fixture.config_path)
            self.assertEqual(config["campaign_id"], fixture.config["campaign_id"])
            self.assertRegex(config_hash, r"^[0-9a-f]{64}$")

    def test_nvidia_service_key_is_forwarded_only_to_remote_guest_collector(self):
        with mock.patch.dict(
            os.environ, {"NV_ATTESTATION_SERVICE_KEY": "secret-fixture"}, clear=False
        ):
            self.assertNotIn("NV_ATTESTATION_SERVICE_KEY", orchestrator._environment())
            self.assertEqual(
                orchestrator._environment(include_nvidia_service_key=True)[
                    "NV_ATTESTATION_SERVICE_KEY"
                ],
                "secret-fixture",
            )
            fake = subprocess.CompletedProcess([], 0, b"{}", b"")
            with mock.patch.object(orchestrator.subprocess, "run", return_value=fake) as run:
                orchestrator._default_run(
                    [
                        sys.executable,
                        str(REPOSITORY_ROOT / "azure/measured_runner.py"),
                        "--job-spec",
                        "/guest/job.json",
                    ],
                    1,
                )
                self.assertEqual(
                    run.call_args.kwargs["env"]["NV_ATTESTATION_SERVICE_KEY"],
                    "secret-fixture",
                )

    def test_azure_identity_is_not_forwarded_to_independent_appraiser(self):
        injected = {
            "AZURE_CLIENT_ID": "secret-client-id",
            "AZURE_CONFIG_DIR": "/secret/azure-config",
            "HOME": "/secret/home",
            "MSI_ENDPOINT": "http://169.254.169.254/metadata/identity",
            "MSI_SECRET": "secret-msi-token",
            "PATH": "/attacker/bin",
        }
        fake = subprocess.CompletedProcess([], 0, b"{}", b"")
        with mock.patch.dict(os.environ, injected, clear=False), mock.patch.object(
            orchestrator.subprocess, "run", return_value=fake
        ) as run:
            orchestrator._default_run(
                ["/opt/reviewed/azure-sevsnp-appraiser", "--evidence", "/run/evidence"],
                1,
            )
            appraiser_env = run.call_args.kwargs["env"]
            for name in (
                "AZURE_CLIENT_ID",
                "AZURE_CONFIG_DIR",
                "HOME",
                "MSI_ENDPOINT",
                "MSI_SECRET",
            ):
                self.assertNotIn(name, appraiser_env)
            self.assertEqual(
                appraiser_env["PATH"],
                "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            )

            orchestrator._default_run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "azure/ncc_h100.py"),
                    "deploy",
                ],
                1,
            )
            deploy_env = run.call_args.kwargs["env"]
            self.assertEqual(deploy_env["MSI_SECRET"], "secret-msi-token")
            self.assertEqual(deploy_env["AZURE_CONFIG_DIR"], "/secret/azure-config")
            self.assertEqual(deploy_env["AZURE_CLIENT_ID"], "secret-client-id")


if __name__ == "__main__":
    unittest.main()
