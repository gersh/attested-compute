# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tg_verifier import azure_cpu_portfolio_materializer as materializer
from tg_verifier.azure_cpu_workload_factory import (
    CDEM_FACTORY,
    factory_for_portfolio_group,
)
from tg_verifier.campaign_io import canonical_json_bytes

import trusted_compute_receipt as receipt_issuer


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/azure-cpu-portfolio-materializer-site.schema.json"
MANIFEST_SCHEMA = (
    ROOT / "schemas/azure-cpu-portfolio-materialization.schema.json"
)


def write_bytes(path: Path, raw: bytes, mode: int = 0o400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def write_json(path: Path, value: object) -> Path:
    return write_bytes(path, canonical_json_bytes(value))


def pin(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def policy_pin(path: Path, policy_id: str) -> dict[str, object]:
    return {
        **pin(path),
        "classification": "production",
        "policy_id": policy_id,
    }


def group() -> dict[str, object]:
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": "cdem-table-abel",
        "command_template": list(CDEM_FACTORY.portfolio_argv),
        "depends_on": [],
        "group_id": "cdem-table-abel::single-job",
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "cdem-table-abel",
        "phase_id": "single-job",
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": {
            "registered_invocation": "cdemTableAbelProductionV2"
        },
        "shard_count": 1,
        "terminal": True,
    }


def make_site(root: Path, *, output_root: Path | None = None) -> tuple[dict, Path]:
    image = (
        "Canonical:0001-com-ubuntu-confidential-vm-jammy:"
        "22_04-lts-cvm:22.04.202607010"
    )
    ssh = write_bytes(root / "inputs/operator.pub", b"ssh-ed25519 fixture\n")
    runner = write_json(root / "inputs/runner.json", {"fixture": "runner"})
    composite = write_json(root / "inputs/composite.json", {"fixture": "composite"})
    verifier = write_bytes(root / "inputs/verifier", b"fixture", 0o500)
    manifest = write_json(root / "inputs/keys.json", {"keys": [], "schema_version": 1})
    public = write_bytes(root / "inputs/public.pem", b"fixture public")
    site = {
        "azure": {
            "admin_username": "sparkoperator",
            "image": image,
            "location": "eastus2",
            "name_prefix": "tg-cpu",
            "nodes": 1,
            "os_disk_size_gb": 256,
            "resource_group": "tg-production",
            "sku": "Standard_EC96as_v6",
            "ssh_public_key": pin(ssh),
            "subnet_id": (
                "/subscriptions/sub-123/resourceGroups/network-rg/providers/"
                "Microsoft.Network/virtualNetworks/private/subnets/cpu"
            ),
            "subscription_id": "sub-123",
            "zone": "1",
        },
        "kind": materializer.SITE_KIND,
        "lean_namespace": "ReviewedCDEMShard",
        "managed_hsm": {
            "key_id": "sparkinterval-azure-cpu-production-2026-07",
            "key_manifest": pin(manifest),
            "key_uri": (
                "https://fixture.managedhsm.azure.net/keys/tg-production/"
                "0123456789abcdef0123456789abcdef"
            ),
            "public_key": pin(public),
        },
        "output_root": str(output_root or root / "materialized"),
        "policies": {
            "composite_appraisal": policy_pin(
                composite, "sparkinterval.composite.azure-cpu.production.v1"
            ),
            "evidence_verifier": pin(verifier),
            "runner": policy_pin(
                runner, "sparkinterval.runner.azure-cpu.production.v1"
            ),
            "transcript_policy_id": (
                "sparkinterval.transcript.cdem.azure-cpu.production.v1"
            ),
        },
        "schema_version": 1,
        "worker": {
            "guest_root": str(root / "guest"),
            "maa_attestation_url": (
                "https://fixture.eus2.attest.azure.net/attest/SevSnpVm"
                "?api-version=2022-08-01"
            ),
        },
    }
    path = write_json(root / "site.json", site)
    return site, path


def source_context() -> SimpleNamespace:
    relative = (*CDEM_FACTORY.source_paths, *materializer.PROFILE_PATHS.values())
    rows = []
    for item in relative:
        path = ROOT / item
        raw = path.read_bytes()
        rows.append(
            {
                "path": item,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        )
    return SimpleNamespace(
        repository_root=ROOT,
        cluster_manifest={"repository_binding": {"files": rows}},
    )


class AzureCPUPortfolioMaterializerTests(unittest.TestCase):
    def test_schema_cli_and_site_have_no_caller_workload_executable(self) -> None:
        schema = json.loads(SCHEMA.read_bytes())
        self.assertEqual(set(schema["required"]), materializer.SITE_FIELDS)
        serialized = json.dumps(schema)
        self.assertNotIn("workload_executable", serialized)
        self.assertNotIn("shell", serialized.lower())
        if jsonschema is not None:
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.Draft202012Validator.check_schema(
                json.loads(MANIFEST_SCHEMA.read_bytes())
            )
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/tg_azure_cpu_portfolio_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("materialize", result.stdout)

    def test_factory_is_exact_and_any_portfolio_argv_drift_disables_it(self) -> None:
        exact = group()
        self.assertEqual(factory_for_portfolio_group(exact), CDEM_FACTORY)
        for mutation in (
            lambda value: value["command_template"].append("--shell"),
            lambda value: value.__setitem__("shard_count", 2),
            lambda value: value.__setitem__("terminal", False),
            lambda value: value["semantic_binding"].__setitem__(
                "registered_invocation", "cubicSumDivThree20000V1"
            ),
        ):
            changed = copy.deepcopy(exact)
            mutation(changed)
            self.assertIsNone(factory_for_portfolio_group(changed))

    def test_site_is_canonical_fresh_and_rejects_executable_injection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site, path = make_site(root)
            self.assertEqual(materializer.load_site(path), site)
            changed = copy.deepcopy(site)
            changed["workload_executable"] = "/tmp/attacker"
            write_json(root / "changed.json", changed)
            with self.assertRaisesRegex(materializer.MaterializerError, "wrong fields"):
                materializer.load_site(root / "changed.json")
            Path(site["output_root"]).mkdir()
            with self.assertRaisesRegex(materializer.MaterializerError, "must be fresh"):
                materializer.load_site(path)

    def test_site_rejects_dangling_output_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site, path = make_site(root)
            output_root = Path(site["output_root"])
            output_root.symlink_to(root / "missing-output-target")
            with self.assertRaisesRegex(
                materializer.MaterializerError, "symbolic link"
            ):
                materializer.load_site(path)

    def test_plan_binds_registered_hashes_sources_placeholders_and_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site, _path = make_site(root)
            instant = materializer.dt.datetime.now(materializer.dt.timezone.utc).replace(
                microsecond=0
            )
            challenge = {
                "campaign_id": "tgp:fixture:cdem:0",
                "expires_at_utc": (
                    instant + materializer.dt.timedelta(hours=48)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "issued_at_utc": instant.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "kind": "gpu_prover_azure_run_challenge",
                "nonce": "42" * 32,
                "schema_version": 1,
                "shard_index": 0,
            }
            challenge_path = write_json(root / "challenge.json", challenge)
            shard = {
                "argv": list(CDEM_FACTORY.portfolio_argv),
                "required_environment": [
                    "TG_CXX",
                    "TG_PYTHON",
                    "TG_REPOSITORY",
                    "TG_RUN_ROOT",
                ],
                "semantic_binding": {
                    "registered_invocation": "cdemTableAbelProductionV2"
                },
                "task_id": "fixture-task",
            }
            shard_path = write_json(root / "shard.json", shard)
            handoff = (group(), shard, challenge, shard_path, challenge_path)
            with mock.patch.object(materializer, "_load_handoff", return_value=handoff):
                plan = materializer.plan_materialization(
                    source_context(), CDEM_FACTORY.group_id, 0, site
                )
            self.assertFalse(plan["accepted"])
            self.assertEqual(plan["factory_id"], CDEM_FACTORY.factory_id)
            self.assertEqual(
                plan["registered_invocation_hashes"]["input_hash"],
                "f14d4dd60e39b2b4f655d3b82333659167d78246de8c5aab923db8a69347742a",
            )
            self.assertEqual(len(plan["source_closure"]), 4)
            self.assertEqual(
                set(plan["portfolio_placeholder_resolution"]),
                {"TG_CXX", "TG_PYTHON", "TG_REPOSITORY", "TG_RUN_ROOT"},
            )
            self.assertEqual(plan["challenge"]["nonce"], "42" * 32)
            self.assertEqual(
                plan["build_host_supported"],
                materializer.platform.machine() == "x86_64",
            )

    def test_short_challenge_and_placeholder_drift_fail_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site, _path = make_site(root)
            now = materializer.dt.datetime.now(materializer.dt.timezone.utc).replace(
                microsecond=0
            )
            challenge = {
                "campaign_id": "tgp:fixture:cdem:0",
                "expires_at_utc": (
                    now + materializer.dt.timedelta(hours=24)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "kind": "gpu_prover_azure_run_challenge",
                "nonce": "43" * 32,
                "schema_version": 1,
                "shard_index": 0,
            }
            challenge_path = write_json(root / "challenge.json", challenge)
            shard = {
                "argv": list(CDEM_FACTORY.portfolio_argv),
                "required_environment": [
                    "TG_CXX",
                    "TG_PYTHON",
                    "TG_REPOSITORY",
                    "TG_RUN_ROOT",
                ],
                "semantic_binding": {
                    "registered_invocation": "cdemTableAbelProductionV2"
                },
                "task_id": "fixture-task",
            }
            shard_path = write_json(root / "shard.json", shard)
            handoff = (group(), shard, challenge, shard_path, challenge_path)
            with mock.patch.object(materializer, "_load_handoff", return_value=handoff):
                with self.assertRaisesRegex(
                    materializer.MaterializerError, "cannot contain"
                ):
                    materializer.plan_materialization(
                        source_context(), CDEM_FACTORY.group_id, 0, site
                    )
            challenge["expires_at_utc"] = (
                now + materializer.dt.timedelta(hours=48)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            shard["required_environment"] = ["TG_RUN_ROOT"]
            handoff = (group(), shard, challenge, shard_path, challenge_path)
            with mock.patch.object(materializer, "_load_handoff", return_value=handoff):
                with self.assertRaisesRegex(materializer.MaterializerError, "placeholders"):
                    materializer.plan_materialization(
                        source_context(), CDEM_FACTORY.group_id, 0, site
                    )

    def test_job_matches_the_closed_registered_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site, _path = make_site(root)
            artifact_root = root / "artifact-root"
            artifact_root.mkdir()
            records = [
                {
                    "executable": True,
                    "path": "artifacts/tg_cdem_abel_measured_workload",
                    "role": "closed_cdem_measured_supervisor_and_trace_verifier",
                    "sha256": "00" * 32,
                    "size_bytes": 0,
                    "statement_role": "host_executable",
                }
            ]
            job = materializer._job(
                source_context(), CDEM_FACTORY, artifact_root, records, site
            )
            expected = materializer.registered_invocation_expected(
                CDEM_FACTORY.registered_invocation
            )
            self.assertEqual(job["algorithm"]["definition_sha256"], expected["algorithm_hash"])
            self.assertEqual(job["input_artifact"]["sha256"], expected["input_hash"])
            self.assertEqual(
                job["parameters"]["canonical_sha256"], expected["parameters_hash"]
            )
            self.assertEqual(
                job["domain_coverage"]["canonical_sha256"], expected["domain_hash"]
            )
            self.assertIn("@challenge@", job["command"]["argv"])
            self.assertIn("@job_binding@", job["work_trace_contract"]["verifier_argv"])
            self.assertEqual(
                job["retained_artifact_contracts"],
                [
                    {
                        "maximum_bytes": 262_144,
                        "path": "work/cdem-abel-artifact.bin",
                        "trace_sha256_field": "artifact_sha256",
                    }
                ],
            )
            if jsonschema is not None:
                measured_job_schema = json.loads(
                    (ROOT / "schemas/measured-job.schema.json").read_bytes()
                )
                jsonschema.Draft202012Validator.check_schema(
                    measured_job_schema
                )
                jsonschema.validate(job, measured_job_schema)

    def test_materialized_roles_match_cpu_receipt_issuer_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site, _path = make_site(root)
            artifact_root = root / "artifact-root"
            artifact_root.mkdir()
            with (
                mock.patch.object(
                    materializer.platform, "machine", return_value="x86_64"
                ),
                mock.patch.object(materializer, "_require_x86_64_static_elf"),
            ):
                records, _build_steps, _compiler = (
                    materializer._build_static_closure(
                        source_context(), CDEM_FACTORY, artifact_root
                    )
                )
            materializer._job(
                source_context(), CDEM_FACTORY, artifact_root, records, site
            )
            build_artifacts = [
                {"role": record["statement_role"], "sha256": record["sha256"]}
                for record in records
                if record["statement_role"] is not None
            ]
            build_artifacts.append(
                {"role": "execution_manifest", "sha256": "11" * 32}
            )
            statement = {"build_artifacts": build_artifacts}
            source_record = next(
                record
                for record in records
                if record["statement_role"] == "source_tree"
            )
            self.assertEqual(
                receipt_issuer._artifact_role(statement, "source_tree"),
                source_record["sha256"],
            )
            self.assertEqual(
                receipt_issuer._artifact_role(statement, "host_executable"),
                next(
                    record["sha256"]
                    for record in records
                    if record["statement_role"] == "host_executable"
                ),
            )
            self.assertEqual(
                receipt_issuer._artifact_role(statement, "execution_manifest"),
                "11" * 32,
            )
            self.assertEqual(
                receipt_issuer._device_hash(statement, "azure_sevsnp_cpu"),
                receipt_issuer.NOT_APPLICABLE_DIGEST,
            )

    def test_measured_supervisor_compiles_static_and_has_no_shell_entrypoint(self) -> None:
        source_text = (
            ROOT / "reference/tg_cdem_abel_measured_workload.cpp"
        ).read_text(encoding="utf-8")
        self.assertNotIn("std::system", source_text)
        self.assertNotIn("popen(", source_text)
        self.assertIn("posix_spawn", source_text)
        self.assertIn("TG-CDEM-ABEL-ARTIFACT-V1", source_text)
        self.assertIn('"artifact_sha256=" + sha256(artifact)', source_text)
        self.assertIn("--artifact", CDEM_FACTORY.command_argv)
        self.assertIn("--artifact", CDEM_FACTORY.trace_verifier_argv)
        self.assertEqual(
            CDEM_FACTORY.command_argv[
                CDEM_FACTORY.command_argv.index("--artifact") + 1
            ],
            CDEM_FACTORY.trace_verifier_argv[
                CDEM_FACTORY.trace_verifier_argv.index("--artifact") + 1
            ],
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "cdem-measured"
            result = subprocess.run(
                [
                    "g++",
                    "-O2",
                    "-std=c++20",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-pthread",
                    "-static",
                    "-I",
                    str(ROOT / "gpu/include"),
                    str(ROOT / "reference/tg_cdem_abel_measured_workload.cpp"),
                    "-o",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(materializer._elf_has_interp(output))
            rejected = subprocess.run(
                [str(output), "--shell", "echo attacker"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("--run or --verify-trace", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
