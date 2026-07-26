# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
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
except ImportError:
    jsonschema = None


REPOSITORY = Path(__file__).resolve().parents[1]
SCHEMA = REPOSITORY / "schemas/azure-cpu-production-campaign.schema.json"
EXAMPLE = (
    REPOSITORY
    / "examples/trusted-compute/azure_cpu_production_campaign.redacted.json"
)


def load_module():
    specification = importlib.util.spec_from_file_location(
        "gpu_prover_cpu_production_orchestrator",
        REPOSITORY / "azure/cpu_production_orchestrator.py",
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


operator = load_module()


def write_bytes(path: Path, content: bytes, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)
    return path


def write_json(path: Path, value: object, mode: int = 0o600) -> Path:
    return write_bytes(path, operator.canonical_json_bytes(value), mode)


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


class CampaignFixture:
    def __init__(self, root: Path):
        self.root = root
        self.inputs = root / "inputs"
        self.review = root / "review"
        self.image = (
            "Canonical:0001-com-ubuntu-confidential-vm-jammy:"
            "22_04-lts-cvm:22.04.202607010"
        )
        self.maa_url = (
            "https://fixture.eus2.attest.azure.net/attest/SevSnpVm"
            "?api-version=2022-08-01"
        )
        self.job_path = write_json(
            self.inputs / "artifact-root/job.json", {"fixture": True}
        )
        self.job_hash = file_pin(self.job_path)["sha256"]
        self.package = write_bytes(self.inputs / "workload.tar", b"package")
        self.ssh_key = write_bytes(
            self.inputs / "operator.pub", b"ssh-ed25519 fixture\n", 0o400
        )
        self.target_hash = "22" * 32
        self.trust_hash = "33" * 32

        self.runner_policy = write_json(
            self.inputs / "runner-policy.json",
            {
                "classification": "production",
                "immutable_image_reference": self.image,
                "immutable_image_reference_sha256": hashlib.sha256(
                    self.image.encode("utf-8")
                ).hexdigest(),
                "kind": "sparkinterval_measured_runner_policy",
                "policy_id": "sparkinterval.runner.azure-cpu.production.v1",
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
                "allowed_backends": [operator.BACKEND],
                "allowed_job_spec_sha256": [self.job_hash],
                "allowed_runner_policy_sha256": [file_pin(self.runner_policy)["sha256"]],
                "allowed_target_profile_sha256": [self.target_hash],
                "allowed_trust_profile_sha256": [self.trust_hash],
                "classification": "production",
                "kind": "sparkinterval_measured_runner_appraisal_policy",
                "policy_id": "sparkinterval.transcript.azure-cpu.production.v1",
                "require_authenticated_hardware_quote": True,
                "required_composite_appraiser_claims": [
                    "measured_runner_policy_valid",
                    "result_artifact_bound_to_execution",
                ],
                "schema_version": 1,
            },
        )
        self.azure_child = write_bytes(
            self.inputs / "azure-appraiser", b"#!/bin/sh\nexit 2\n", 0o500
        )
        self.azure_policy = write_json(
            self.inputs / "azure-policy.json", {"fixture": "production"}
        )
        self.composite_policy = write_json(
            self.inputs / "composite-policy.json",
            {
                "allowed_backends": [operator.BACKEND],
                "azure_appraiser": {
                    "executable_path": str(self.azure_child),
                    "executable_sha256": file_pin(self.azure_child)["sha256"],
                    "maa_accepted_audience": "fixture-audience",
                    "maa_accepted_issuer": "https://fixture.eus2.attest.azure.net",
                    "maa_accepted_provider": "maa_snp",
                    "maa_attestation_url": self.maa_url,
                    "policy_path": str(self.azure_policy),
                    "policy_sha256": file_pin(self.azure_policy)["sha256"],
                    "timeout_seconds": 300,
                },
                "kind": "sparkinterval_azure_evidence_appraisal_policy",
                "nvidia_appraiser": None,
                "schema_version": 1,
            },
        )
        self.evidence_verifier = write_bytes(
            self.inputs / "evidence-verifier", b"#!/bin/sh\nexit 2\n", 0o500
        )
        self.public_key = write_bytes(
            self.inputs / "production-public.pem", b"fixture-public-key\n", 0o400
        )
        self.key_id = "sparkinterval-azure-cpu-production-2026-07"
        self.key_manifest = write_json(
            self.inputs / "key-manifest.json",
            {
                "keys": [
                    {
                        "allowed_verifier_profiles": [
                            {
                                "backend": operator.BACKEND,
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
        worker = root / "guest"
        self.config = {
            "azure": {
                "admin_username": "sparkoperator",
                "image": self.image,
                "location": "eastus2",
                "name_prefix": "tg-cpu",
                "nodes": 1,
                "os_disk_size_gb": 256,
                "resource_group": "tg-production",
                "sku": "Standard_EC96as_v6",
                "ssh_public_key": file_pin(self.ssh_key),
                "subnet_id": (
                    "/subscriptions/sub-123/resourceGroups/network-rg/providers/"
                    "Microsoft.Network/virtualNetworks/private/subnets/cpu"
                ),
                "subscription_id": "sub-123",
                "zone": "1",
            },
            "campaign_id": "tg-cpu-production-2026-07",
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
            "kind": operator.CONFIG_KIND,
            "lean_review": {
                "namespace": "ReviewedCPUCandidate",
                "registered_invocation": "cdemTableAbelProductionV2",
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
                    self.composite_policy,
                    "sparkinterval.composite.azure-cpu.production.v1",
                ),
                "evidence_verifier": file_pin(self.evidence_verifier),
                "runner": policy_pin(
                    self.runner_policy, "sparkinterval.runner.azure-cpu.production.v1"
                ),
                "transcript_appraisal": policy_pin(
                    self.transcript_policy,
                    "sparkinterval.transcript.azure-cpu.production.v1",
                ),
            },
            "schema_version": 1,
            "worker": {
                "artifact_root": str(worker / "artifact-root"),
                "certificate_archive": str(worker / "return/certificate.tar"),
                "certificate_package": str(worker / "certificate-package"),
                "challenge": str(worker / "input/challenge.json"),
                "completion_manifest": str(worker / "return/completion.json"),
                "job_spec": str(worker / "artifact-root/job.json"),
                "maa_attestation_url": self.maa_url,
                "run_package": str(worker / "measured-run"),
                "stage_manifest": str(worker / "input/stage.json"),
                "transcript_appraisal_policy": str(
                    worker / "input/transcript-policy.json"
                ),
                "workload_package": str(worker / "input/workload.tar"),
            },
            "workload": {
                "artifact_root": str(self.job_path.parent),
                "job_spec": file_pin(self.job_path),
                "package": file_pin(self.package),
            },
        }
        self.config_path = write_json(root / "campaign.json", self.config)

    def validated_job(self) -> dict[str, object]:
        registered = operator.registered_invocation_expected(
            "cdemTableAbelProductionV2"
        )
        return {
            "algorithm": {
                "algorithm_id": registered["algorithm_id"],
                "definition_sha256": registered["algorithm_hash"],
            },
            "backend": operator.BACKEND,
            "command": {"timeout_seconds": 3600},
            "domain_coverage": {"canonical_sha256": registered["domain_hash"]},
            "gpu_pre_run_gate": None,
            "input_artifact": {"sha256": registered["input_hash"]},
            "parameters": {"canonical_sha256": registered["parameters_hash"]},
            "runner_policy": {"sha256": file_pin(self.runner_policy)["sha256"]},
            "target_profile": {
                "profile_id": operator.TARGET_PROFILE_ID,
                "sha256": self.target_hash,
            },
            "trust_profile": {
                "profile_id": operator.TRUST_PROFILE_ID,
                "sha256": self.trust_hash,
            },
        }

    def write_config(self, value: dict | None = None) -> None:
        write_json(self.config_path, self.config if value is None else value)

    def load(self):
        with mock.patch.object(
            operator, "validate_job_spec", return_value=self.validated_job()
        ):
            return operator.load_config(self.config_path)

    def deployment(self) -> dict:
        shape = operator.cpu_cvm.REVIEWED_SKUS[self.config["azure"]["sku"]]
        return {
            "accepted": True,
            "attestation_collected": False,
            "classification": "azure_cpu_confidential_vms_created_and_inspected",
            "gpus_per_vm": 0,
            "memory_gib_per_vm": shape.memory_gib,
            "preflight": {
                "accepted": True,
                "capacity_guaranteed": False,
                "classification": "azure_cpu_cvm_control_plane_preflight_passed",
                "gpus_per_node": 0,
                "location": self.config["azure"]["location"],
                "memory_gib_per_node": shape.memory_gib,
                "nodes": 1,
                "sku": self.config["azure"]["sku"],
                "subscription_id": self.config["azure"]["subscription_id"],
                "vcpus_per_node": shape.vcpus,
                "zone": self.config["azure"]["zone"],
            },
            "public_ip_addresses": False,
            "resolved_image": self.image,
            "resource_group": self.config["azure"]["resource_group"],
            "resources_proven_attested": 0,
            "sku": self.config["azure"]["sku"],
            "subnet_default_outbound_access": False,
            "subnet_id": self.config["azure"]["subnet_id"],
            "subnet_nat_gateway_id": "/subscriptions/sub-123/natGateways/private",
            "subnet_network_security_group_id": "/subscriptions/sub-123/networkSecurityGroups/private",
            "subnet_route_table_id": None,
            "vcpus_per_vm": shape.vcpus,
            "virtual_machines": [
                {
                    "id": "/subscriptions/sub-123/resourceGroups/tg/providers/Microsoft.Compute/virtualMachines/tg-cpu-000",
                    "name": "tg-cpu-000",
                    "private_ip_addresses": ["10.0.0.4"],
                    "public_ip_address": None,
                    "security_profile": {
                        "image_reference": operator.cpu_cvm._expected_image_reference(
                            self.image
                        ),
                        "network_interface_id": "/subscriptions/sub-123/networkInterfaces/tg-cpu-000",
                        "os_disk_security_encryption_type": "DiskWithVMGuestState",
                        "secure_boot": True,
                        "security_type": "ConfidentialVM",
                        "vtpm": True,
                    },
                }
            ],
        }


class CPUProductionOperatorTests(unittest.TestCase):
    def test_schema_example_help_and_docs_are_current(self) -> None:
        schema = json.loads(SCHEMA.read_bytes())
        example = json.loads(EXAMPLE.read_bytes())
        self.assertEqual(set(schema["required"]), operator.CONFIG_KEYS)
        for field, keys in (
            ("azure", operator.AZURE_KEYS),
            ("challenge", operator.CHALLENGE_SOURCE_KEYS),
            ("handoffs", operator.HANDOFF_KEYS),
            ("lean_review", operator.LEAN_REVIEW_KEYS),
            ("managed_hsm", operator.HSM_KEYS),
            ("outputs", operator.OUTPUT_KEYS),
            ("policies", operator.POLICIES_KEYS),
            ("worker", operator.WORKER_KEYS),
            ("workload", operator.WORKLOAD_KEYS),
        ):
            self.assertEqual(set(schema["properties"][field]["required"]), keys)
        self.assertEqual(set(example), operator.CONFIG_KEYS)
        self.assertNotIn("nvidia", json.dumps(example).lower())
        result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "azure/cpu_production_orchestrator.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reconcile-receipt", result.stdout)
        runbook = REPOSITORY / "docs/AZURE_CPU_PRODUCTION_OPERATOR.md"
        self.assertTrue(runbook.is_file())

    @unittest.skipIf(jsonschema is None, "jsonschema is unavailable")
    def test_example_validates_against_schema(self) -> None:
        schema = json.loads(SCHEMA.read_bytes())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(json.loads(EXAMPLE.read_bytes()))

    def test_plan_is_cpu_only_exact_and_review_candidate_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            plan = operator.command_plan(config, config_hash)
            self.assertFalse(plan["accepted"])
            serialized = json.dumps(plan).lower()
            self.assertNotIn("nvidia", serialized)
            step_ids = [step["id"] for step in plan["steps"]]
            self.assertLess(step_ids.index("challenge"), step_ids.index("stage_worker"))
            self.assertLess(step_ids.index("stage_worker"), step_ids.index("measured_runner"))
            deploy = next(x["argv"] for x in plan["steps"] if x["id"] == "deploy")
            self.assertIn("azure/cpu_cvm.py", deploy[1])
            self.assertEqual(deploy[deploy.index("--sku") + 1], "Standard_EC96as_v6")
            self.assertEqual(deploy[deploy.index("--image") + 1], fixture.image)
            collector = next(
                x["argv"]
                for x in plan["steps"]
                if x["id"] == "no_reset_cpu_evidence_collection"
            )
            self.assertEqual(collector[collector.index("--backend") + 1], operator.BACKEND)
            receipt = next(
                x["argv"] for x in plan["steps"] if x["id"] == "receipt_issue_hsm"
            )
            self.assertIn("managed_hsm_signer.py", " ".join(receipt))
            self.assertIn(config["outputs"]["replay_db"], receipt)

    def test_operational_receipt_is_signed_but_cannot_generate_a_lean_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            fixture.config["lean_review"]["registered_invocation"] = None
            fixture.write_config()
            arbitrary_operational_job = fixture.validated_job()
            arbitrary_operational_job["algorithm"] = {
                "algorithm_id": "sparkinterval.tg.psi.azure-phase.initialize."
                + "42" * 32,
                "definition_sha256": "43" * 32,
            }
            with mock.patch.object(
                operator, "validate_job_spec", return_value=arbitrary_operational_job
            ):
                config, config_hash = operator.load_config(fixture.config_path)
            plan = operator.command_plan(config, config_hash)
            by_id = {step["id"]: step for step in plan["steps"]}
            self.assertIsNone(by_id["registry_review_candidate"]["argv"])
            self.assertIsNone(by_id["lean_review_candidate"]["argv"])
            with self.assertRaisesRegex(
                operator.OrchestratorError, "operational phase receipts"
            ):
                operator.generate_review_candidates(config, config_hash)

    def test_image_sku_subnet_and_package_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            for mutate, message in (
                (
                    lambda value: value["azure"].__setitem__(
                        "image", fixture.image.rsplit(":", 1)[0] + ":latest"
                    ),
                    "not latest",
                ),
                (
                    lambda value: value["azure"].__setitem__(
                        "sku", "Standard_E96as_v6"
                    ),
                    "reviewed set",
                ),
                (
                    lambda value: value["azure"].__setitem__(
                        "subnet_id", value["azure"]["subnet_id"].replace("sub-123", "other")
                    ),
                    "selected subscription",
                ),
            ):
                changed = copy.deepcopy(fixture.config)
                mutate(changed)
                fixture.write_config(changed)
                with self.assertRaisesRegex(operator.OrchestratorError, message):
                    fixture.load()
            fixture.write_config()
            fixture.package.write_bytes(b"tampered")
            with self.assertRaisesRegex(operator.OrchestratorError, "does not match"):
                fixture.load()

    def test_backend_profile_policy_and_key_confusion_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            h100 = copy.deepcopy(fixture.config)
            h100["lean_review"]["registered_invocation"] = "h100FormalPtxConstantOneV1"
            fixture.write_config(h100)
            with self.assertRaisesRegex(operator.OrchestratorError, "CPU-backend-compatible"):
                fixture.load()

            fixture.write_config()
            wrong_job = fixture.validated_job()
            wrong_job["backend"] = "azure_ncc40ads_h100_v5"
            with mock.patch.object(operator, "validate_job_spec", return_value=wrong_job):
                with self.assertRaisesRegex(operator.OrchestratorError, "CPU-only"):
                    operator.load_config(fixture.config_path)

            wrong_job = fixture.validated_job()
            wrong_job["target_profile"]["profile_id"] = "azure_sevsnp_cpu_typo"
            with mock.patch.object(operator, "validate_job_spec", return_value=wrong_job):
                with self.assertRaisesRegex(operator.OrchestratorError, "target/trust"):
                    operator.load_config(fixture.config_path)

            composite = json.loads(fixture.composite_policy.read_bytes())
            composite["nvidia_appraiser"] = {"unexpected": True}
            write_json(fixture.composite_policy, composite)
            changed = copy.deepcopy(fixture.config)
            changed["policies"]["composite_appraisal"] = policy_pin(
                fixture.composite_policy, "sparkinterval.composite.azure-cpu.production.v1"
            )
            fixture.write_config(changed)
            with self.assertRaisesRegex(operator.OrchestratorError, "CPU-only"):
                fixture.load()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            manifest = json.loads(fixture.key_manifest.read_bytes())
            manifest["keys"][0]["allowed_verifier_profiles"][0]["backend"] = (
                "azure_ncc40ads_h100_v5"
            )
            write_json(fixture.key_manifest, manifest)
            fixture.config["managed_hsm"]["key_manifest"] = file_pin(fixture.key_manifest)
            fixture.write_config()
            with self.assertRaisesRegex(operator.OrchestratorError, "exact CPU verifier tuple"):
                fixture.load()

    def test_state_journal_is_hash_chained_idempotent_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            first = operator.initialize_state(config, config_hash)
            second = operator.initialize_state(config, config_hash)
            self.assertEqual(first, second)
            self.assertEqual(first["sequence"], 0)
            state_path = Path(config["outputs"]["state"])
            state_path.write_bytes(b"{}")
            with self.assertRaisesRegex(operator.OrchestratorError, "wrong fields"):
                operator.load_state(config, config_hash)
            recovered = operator.recover_state_head(config, config_hash)
            self.assertEqual(recovered, first)
            event = operator._event_path(config, 0)
            value = json.loads(event.read_bytes())
            value["to"] = "attacker-stage"
            write_json(event, value)
            with self.assertRaisesRegex(operator.OrchestratorError, "state chain"):
                operator.recover_state_head(config, config_hash)

    def test_deploy_is_idempotent_and_failed_side_effect_requires_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            operator.initialize_state(config, config_hash)
            calls = 0

            def success(argv, timeout):
                nonlocal calls
                calls += 1
                return subprocess.CompletedProcess(
                    argv, 0, operator.canonical_json_bytes(fixture.deployment()), b""
                )

            first = operator.deploy(config, config_hash, success)
            second = operator.deploy(config, config_hash, success)
            self.assertEqual(first, second)
            self.assertEqual(calls, 1)

        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            operator.initialize_state(config, config_hash)

            def denied(argv, timeout):
                return subprocess.CompletedProcess(argv, 2, b"", b"unknown Azure result")

            with self.assertRaises(operator.OrchestratorError):
                operator.deploy(config, config_hash, denied)
            self.assertIn(
                "manual_reconciliation_required",
                operator.load_state(config, config_hash)["stage"],
            )
            with self.assertRaisesRegex(operator.OrchestratorError, "reconcile"):
                operator.deploy(config, config_hash, denied)
            write_json(
                Path(config["outputs"]["deployment_record"]), fixture.deployment()
            )
            adopted = operator.reconcile_deployment(config, config_hash)
            self.assertTrue(adopted["accepted"])
            self.assertEqual(operator.load_state(config, config_hash)["stage"], "azure_deployed")

    def test_stage_manifest_has_no_gpu_placeholders_and_binds_exact_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            write_json(Path(config["outputs"]["deployment_record"]), fixture.deployment())
            now = operator.dt.datetime.now(operator.dt.timezone.utc).replace(microsecond=0)
            write_json(
                operator._challenge_path(config),
                {
                    "campaign_id": config["campaign_id"],
                    "expires_at_utc": (now + operator.dt.timedelta(hours=6)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "issued_at_utc": (now - operator.dt.timedelta(minutes=1)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "kind": "gpu_prover_azure_run_challenge",
                    "nonce": "42" * 32,
                    "schema_version": 1,
                    "shard_index": 0,
                },
            )
            manifest = operator._stage_manifest_expected(config, config_hash)
            self.assertNotIn("nvidia", json.dumps(manifest).lower())
            operator._validate_worker_manifest_local(manifest, config, config_hash)
            changed = copy.deepcopy(manifest)
            changed["worker_input_bindings"]["workload_package"]["sha256"] = "00" * 32
            with self.assertRaisesRegex(operator.OrchestratorError, "does not bind"):
                operator._validate_worker_manifest_local(changed, config, config_hash)

    def test_pinned_portfolio_challenge_is_adopted_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            now = operator.dt.datetime.now(operator.dt.timezone.utc).replace(
                microsecond=0
            )
            source = write_json(
                fixture.inputs / "portfolio-challenge.json",
                {
                    "campaign_id": "tgp:fixture:cdem:0",
                    "expires_at_utc": (
                        now + operator.dt.timedelta(seconds=86400)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "kind": "gpu_prover_azure_run_challenge",
                    "nonce": "42" * 32,
                    "schema_version": 1,
                    "shard_index": 0,
                },
            )
            fixture.config["campaign_id"] = "tgp:fixture:cdem:0"
            fixture.config["challenge"] = {
                "mode": "pinned_portfolio_handoff_v1",
                "pin": file_pin(source),
                "shard_index": 0,
            }
            fixture.write_config()
            config, config_hash = fixture.load()
            operator.initialize_state(config, config_hash)

            def deploy_success(argv, timeout):
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    operator.canonical_json_bytes(fixture.deployment()),
                    b"",
                )

            operator.deploy(config, config_hash, deploy_success)
            result = operator.create_challenge_step(
                config,
                config_hash,
                lambda _argv, _timeout: self.fail(
                    "pinned challenge adoption must not execute a generator"
                ),
            )
            self.assertEqual(
                result["classification"],
                "exact_pinned_portfolio_challenge_adopted_off_vm",
            )
            self.assertEqual(operator._challenge_path(config).read_bytes(), source.read_bytes())
            plan = operator.command_plan(config, config_hash)
            challenge_step = next(
                step for step in plan["steps"] if step["id"] == "challenge"
            )
            self.assertIsNone(challenge_step["argv"])
            self.assertEqual(
                challenge_step["operation"],
                "adopt_exact_pinned_portfolio_challenge",
            )

    def test_pinned_portfolio_challenge_identity_and_pin_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            now = operator.dt.datetime.now(operator.dt.timezone.utc).replace(
                microsecond=0
            )
            source = write_json(
                fixture.inputs / "portfolio-challenge.json",
                {
                    "campaign_id": "different-campaign",
                    "expires_at_utc": (
                        now + operator.dt.timedelta(seconds=86400)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "kind": "gpu_prover_azure_run_challenge",
                    "nonce": "43" * 32,
                    "schema_version": 1,
                    "shard_index": 0,
                },
            )
            fixture.config["challenge"] = {
                "mode": "pinned_portfolio_handoff_v1",
                "pin": file_pin(source),
                "shard_index": 0,
            }
            fixture.write_config()
            with self.assertRaisesRegex(
                operator.OrchestratorError, "identity differs"
            ):
                fixture.load()

            fixture.config["campaign_id"] = "different-campaign"
            fixture.config["challenge"]["pin"]["sha256"] = "00" * 32
            fixture.write_config()
            with self.assertRaisesRegex(operator.OrchestratorError, "does not match"):
                fixture.load()

    def test_identity_and_host_environment_are_not_leaked_to_appraisers(self) -> None:
        injected = {
            "AZURE_CLIENT_ID": "secret-client",
            "MSI_SECRET": "secret-msi",
            "HOME": "/secret/home",
            "NV_ATTESTATION_SERVICE_KEY": "must-not-exist",
            "PATH": "/attacker/bin",
        }
        fake = subprocess.CompletedProcess([], 0, b"{}", b"")
        with mock.patch.dict(os.environ, injected, clear=False), mock.patch.object(
            operator.subprocess, "run", return_value=fake
        ) as run:
            operator._default_run(["/reviewed/appraiser", "--evidence", "/run"], 1)
            environment = run.call_args.kwargs["env"]
            self.assertNotIn("AZURE_CLIENT_ID", environment)
            self.assertNotIn("MSI_SECRET", environment)
            self.assertNotIn("HOME", environment)
            self.assertNotIn("NV_ATTESTATION_SERVICE_KEY", environment)
            operator._default_run(
                [sys.executable, str(REPOSITORY / "azure/cpu_cvm.py"), "deploy"], 1
            )
            privileged = run.call_args.kwargs["env"]
            self.assertEqual(privileged["AZURE_CLIENT_ID"], "secret-client")
            self.assertEqual(privileged["MSI_SECRET"], "secret-msi")
            self.assertNotIn("NV_ATTESTATION_SERVICE_KEY", privileged)

    def test_live_trust_output_and_receipt_backend_or_key_confusion_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            changed = copy.deepcopy(fixture.config)
            changed["outputs"]["lean_candidate"] = str(
                REPOSITORY / "SparkInterval/Execution/TrustedComputeRegistry.lean"
            )
            fixture.write_config(changed)
            with self.assertRaisesRegex(operator.OrchestratorError, "review_root|live"):
                fixture.load()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = CampaignFixture(Path(temporary))
            config, config_hash = fixture.load()
            operator.initialize_state(config, config_hash)
            for source, target in (
                ("initialized", "azure_deployment_in_progress"),
                ("azure_deployment_in_progress", "azure_deployed"),
                ("azure_deployed", "challenge_generation_in_progress"),
                (
                    "challenge_generation_in_progress",
                    "challenge_created_awaiting_manual_worker_stage",
                ),
                (
                    "challenge_created_awaiting_manual_worker_stage",
                    "worker_stage_confirmed",
                ),
                ("worker_stage_confirmed", "certificate_ingestion_in_progress"),
                ("certificate_ingestion_in_progress", "certificate_package_verified"),
                ("certificate_package_verified", "hardware_appraisal_in_progress"),
                ("hardware_appraisal_in_progress", "hardware_appraisal_prechecked"),
                (
                    "hardware_appraisal_prechecked",
                    "receipt_issuance_in_progress_challenge_may_be_burned",
                ),
                (
                    "receipt_issuance_in_progress_challenge_may_be_burned",
                    "receipt_issuance_failed_challenge_reconciliation_required",
                ),
            ):
                operator._transition(config, config_hash, source, target)
            receipt = {
                "backend": "azure_ncc40ads_h100_v5",
                "receipt_sha256": "44" * 32,
                "verifier": {"key_id": fixture.key_id},
            }
            write_json(Path(config["outputs"]["receipt"]), receipt)

            def apparently_valid(argv, timeout):
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    operator.canonical_json_bytes(
                        {
                            "accepted_for_lean": False,
                            "backend": "azure_ncc40ads_h100_v5",
                            "receipt_sha256": "44" * 32,
                            "signature_valid": True,
                            "verifier_key_id": fixture.key_id,
                        }
                    ),
                    b"",
                )

            with self.assertRaisesRegex(operator.OrchestratorError, "CPU/key"):
                operator.reconcile_receipt(config, config_hash, apparently_valid)


if __name__ == "__main__":
    unittest.main()
