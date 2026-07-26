# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None

from attestation.measured_run_archive import create_archive
from tg_verifier import azure_cpu_goldbach_10pow27_materializer as materializer
from tg_verifier.azure_cpu_goldbach_10pow27_materializer import (
    _expected_predecessors,
)
from tg_verifier.azure_cpu_portfolio_materializer import (
    PROFILE_PATHS,
    _artifact_record,
)
from tg_verifier.azure_cpu_goldbach_10pow27_workload_factory import (
    CAMPAIGN_ID,
    PHASE_COMMANDS,
    PHASE_COUNTS,
    PHASE_DEPENDENCIES,
    REGISTERED_ALGORITHM_DEFINITION,
    REGISTERED_INPUT,
    REGISTERED_INVOCATION,
    SOURCE_PATHS,
    expected_registered_hashes,
    factory_for_portfolio_group,
    make_factory,
    source_reviewed_materializer_available,
)
from tg_verifier.azure_h100_goldbach_10pow27_workload_factory import (
    expected_execution_projection_sha256,
)
from tg_verifier.campaign_io import canonical_json_bytes, hash_file_once
from tg_verifier.goldbach_gpu_campaign import (
    EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
)
from tg_verifier.goldbach_build_admission import load_build_admission
from tools.generate_trusted_compute_lean import registered_invocation_expected
from tools.tg_goldbach_10pow27_azure_measured_workload import (
    H100_PHASE,
    OPERATIONAL_RESULT_KIND,
    Goldbach10Pow27MeasuredWorkloadError,
    _validate_cpu_result,
    _validate_h100_result,
    _write_export_manifest,
    h100_expected_claim_identity,
    verify_retained_export_archive,
)


OWNER_ATOM_ID = "goldbach-finite-below-10pow27"
ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-cpu-goldbach10pow27-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-cpu-goldbach10pow27-materialization.schema.json"
SITE_EXAMPLE = (
    ROOT
    / "examples/trusted-compute/azure_cpu_goldbach10pow27_materializer_site.redacted.json"
)
ADMISSION_FIXTURE = ROOT / "tests/fixtures/goldbach_build_admission.test.json"


def group(phase: str, *, semantic=None) -> dict[str, object]:
    terminal = phase == "measured-finalize-lowered-source-claim"
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PHASE_COMMANDS[phase]),
        "depends_on": list(PHASE_DEPENDENCIES[phase]),
        "group_id": f"{CAMPAIGN_ID}::{phase}",
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": OWNER_ATOM_ID,
        "phase_id": phase,
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": semantic,
        "shard_count": PHASE_COUNTS[phase],
        "terminal": terminal,
    }


def write_bytes(path: Path, raw: bytes, mode: int = 0o400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def pin(path: Path) -> dict[str, object]:
    digest, size = hash_file_once(path)
    return {"path": str(path), "sha256": digest, "size_bytes": size}


def source_context() -> SimpleNamespace:
    rows = []
    for relative in PROFILE_PATHS.values():
        path = ROOT / relative
        digest, size = hash_file_once(path)
        rows.append({"path": relative, "sha256": digest, "size_bytes": size})
    return SimpleNamespace(
        repository_root=ROOT,
        cluster_manifest={"repository_binding": {"files": rows}},
    )


class Goldbach10Pow27CPUFactoryTests(unittest.TestCase):
    def test_registered_identity_binds_the_active_hardened_source(self) -> None:
        source_identity = EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256
        self.assertIn(
            f"binary-source-identity={source_identity}\n",
            REGISTERED_ALGORITHM_DEFINITION,
        )
        self.assertIn(
            f'"binary_source_identity_sha256":"{source_identity}"'.encode("ascii"),
            REGISTERED_INPUT,
        )

    def test_all_seven_cpu_phase_groups_have_exact_closed_factories(self) -> None:
        self.assertEqual(len(PHASE_COUNTS), 7)
        for phase, count in PHASE_COUNTS.items():
            exact = group(phase)
            self.assertTrue(source_reviewed_materializer_available(exact), phase)
            for index in {0, count - 1}:
                factory = factory_for_portfolio_group(exact, index)
                self.assertIsNotNone(factory, (phase, index))
                assert factory is not None
                self.assertEqual(factory.portfolio_argv, PHASE_COMMANDS[phase])
                self.assertEqual(factory.shard_count, count)
            changed = dict(exact)
            changed["command_template"] = [*exact["command_template"], "--unsafe"]
            self.assertFalse(source_reviewed_materializer_available(changed))

    def test_terminal_accepts_disabled_semantics_but_only_exact_enablement(self) -> None:
        phase = "measured-finalize-lowered-source-claim"
        disabled = group(phase)
        self.assertIsNotNone(factory_for_portfolio_group(disabled, 0))
        enabled = group(
            phase,
            semantic={"registered_invocation": REGISTERED_INVOCATION},
        )
        self.assertIsNotNone(factory_for_portfolio_group(enabled, 0))
        enabled["semantic_binding"] = {"registered_invocation": "attacker"}
        self.assertIsNone(factory_for_portfolio_group(enabled, 0))

    def test_registered_terminal_hashes_are_generator_identical(self) -> None:
        expected = registered_invocation_expected(REGISTERED_INVOCATION)
        self.assertEqual(
            expected_registered_hashes(),
            {key: expected[key] for key in expected_registered_hashes()},
        )

    def test_predecessor_cardinalities_are_explicit(self) -> None:
        expected = {
            "create-lowered-binary-plan": 0,
            "initialize-lowered-prime-ladder": 0,
            "native-lowered-prime-ladder-range-groups": 1,
            "aggregate-lowered-binary-leaves": 8_193,
            "replay-lowered-binary-aggregate": 1,
            "reduce-lowered-prime-ladder-ranges": 320,
            "measured-finalize-lowered-source-claim": 2,
        }
        for phase, count in expected.items():
            self.assertEqual(len(_expected_predecessors(make_factory(phase, 0))), count)

    def test_schemas_cli_and_factory_expose_no_caller_command(self) -> None:
        for path in (SITE_SCHEMA, MANIFEST_SCHEMA):
            schema = json.loads(path.read_bytes())
            if jsonschema is not None:
                jsonschema.Draft202012Validator.check_schema(schema)
        if jsonschema is not None:
            jsonschema.validate(
                json.loads(SITE_EXAMPLE.read_bytes()),
                json.loads(SITE_SCHEMA.read_bytes()),
            )
        site_text = SITE_SCHEMA.read_text(encoding="utf-8").lower()
        self.assertNotIn("workload_executable", site_text)
        self.assertNotIn('"shell"', site_text)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/tg_azure_cpu_goldbach_10pow27_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for phase in PHASE_COUNTS:
            self.assertEqual(
                make_factory(phase, 0).command_argv[:2],
                ("artifacts/python3", "-I"),
            )

    def test_operational_and_terminal_job_specs_bind_the_closed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner_policy = write_bytes(root / "runner-policy.json", b"{}\n")
            admission = load_build_admission(
                ADMISSION_FIXTURE, allow_test_fixture=True
            )
            site = {
                "base": {
                    "policies": {
                        "runner": {
                            **pin(runner_policy),
                            "classification": "production",
                            "policy_id": "sparkinterval.runner.azure-cpu.production.v1",
                        }
                    }
                },
                "build_admission": admission,
            }
            for phase in (
                "create-lowered-binary-plan",
                "measured-finalize-lowered-source-claim",
            ):
                artifact_root = root / phase
                host = write_bytes(
                    artifact_root / "artifacts/python3", b"python", 0o500
                )
                producer = write_bytes(
                    artifact_root / "artifacts/tg_goldbach_ladder_native",
                    b"runner",
                    0o500,
                )
                source_tree = write_bytes(
                    artifact_root / "source/source-closure.json", b"{}\n"
                )
                runtime = write_bytes(
                    artifact_root / "source/runtime-closure.json", b"{}\n"
                )
                h100_executable = write_bytes(
                    artifact_root / "artifacts/goldbach-gpu",
                    b"h100 executable",
                    0o500,
                )
                records = [
                    _artifact_record(
                        host,
                        artifact_root,
                        role="image_bound_cpython_host",
                        statement_role="host_executable",
                        executable=True,
                    ),
                    _artifact_record(
                        producer,
                        artifact_root,
                        role="static_gmp_n45_ladder_producer",
                        statement_role="producer_executable",
                        executable=True,
                    ),
                    _artifact_record(
                        source_tree,
                        artifact_root,
                        role="reviewed_source_closure_manifest",
                        statement_role="source_tree",
                        executable=False,
                    ),
                    _artifact_record(
                        runtime,
                        artifact_root,
                        role="image_runtime_closure_manifest",
                        statement_role=None,
                        executable=False,
                    ),
                    _artifact_record(
                        h100_executable,
                        artifact_root,
                        role=(
                            "h100_executable_identity_data_not_cpu_executed"
                        ),
                        statement_role=None,
                        executable=True,
                    ),
                ]
                handoff = write_bytes(
                    artifact_root / "input/goldbach10pow27-phase-handoff.tar",
                    b"handoff",
                )
                factory = make_factory(phase, 0)
                if factory.terminal:
                    child_commitment = write_bytes(
                        artifact_root / "source/child-receipt-identities.json",
                        b'{"reviewed":"test-only"}',
                    )
                    records.append(
                        _artifact_record(
                            child_commitment,
                            artifact_root,
                            role=(
                                "goldbach_child_receipt_identity_commitment"
                            ),
                            statement_role=None,
                            executable=False,
                        )
                    )
                job = materializer._job(
                    source_context(), factory, artifact_root, records, handoff, site
                )
                self.assertEqual(job["command"]["argv"], list(factory.command_argv))
                self.assertEqual(
                    job["input_artifact"]["sha256"],
                    expected_registered_hashes()["input_hash"]
                    if factory.terminal
                    else pin(handoff)["sha256"],
                )
                self.assertEqual(
                    len(
                        [
                            row
                            for row in job["artifact_closure"]["files"]
                            if row["statement_role"] == "source_tree"
                        ]
                    ),
                    1,
                )
                self.assertEqual(
                    len(
                        [
                            row
                            for row in job["artifact_closure"]["files"]
                            if row["role"]
                            == "goldbach_child_receipt_identity_commitment"
                        ]
                    ),
                    1 if factory.terminal else 0,
                )
                self.assertEqual(
                    len(
                        [
                            row
                            for row in job["artifact_closure"]["files"]
                            if row["role"]
                            == "goldbach_terminal_post_child_run_binding"
                        ]
                    ),
                    1 if factory.terminal else 0,
                )


class Goldbach10Pow27RetainedExportTests(unittest.TestCase):
    def _archive(self, root: Path, phase: str, index: int) -> tuple[Path, dict]:
        export = root / "export"
        (export / "payload").mkdir(parents=True)
        (export / "payload/value.txt").write_bytes(b"reviewed")
        manifest = _write_export_manifest(export, phase, index)
        archive = root / "export.tar"
        create_archive(export, archive)
        return archive, manifest

    def test_retained_archive_tree_is_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, manifest = self._archive(
                root, "initialize-lowered-prime-ladder", 0
            )
            self.assertEqual(
                verify_retained_export_archive(
                    archive, "initialize-lowered-prime-ladder", 0
                ),
                manifest,
            )
            with self.assertRaises(Goldbach10Pow27MeasuredWorkloadError):
                verify_retained_export_archive(
                    archive, "initialize-lowered-prime-ladder", 1
                )

    def test_cpu_result_must_pin_exact_archive_and_phase_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            phase = "initialize-lowered-prime-ladder"
            archive, manifest = self._archive(root, phase, 0)
            factory = make_factory(phase, 0)
            digest, size = hash_file_once(archive)
            result = canonical_json_bytes(
                {
                    "group_index": 0,
                    "kind": OPERATIONAL_RESULT_KIND,
                    "phase": phase,
                    "retained_export_sha256": digest,
                    "retained_export_size_bytes": size,
                    "retained_tree_sha256": manifest["tree_sha256"],
                    "schema_version": 1,
                }
            ).decode("utf-8")
            receipt = {
                "backend": "azure_sevsnp_cpu",
                "claim": {
                    "algorithm_hash": hashlib.sha256(
                        factory.algorithm_definition.encode("utf-8")
                    ).hexdigest(),
                    "algorithm_id": factory.algorithm_id,
                    "domain_hash": hashlib.sha256(
                        canonical_json_bytes(factory.domain)
                    ).hexdigest(),
                    "input_hash": "0" * 64,
                    "output_hash": hashlib.sha256(result.encode("utf-8")).hexdigest(),
                    "parameters_hash": hashlib.sha256(
                        canonical_json_bytes(factory.parameters)
                    ).hexdigest(),
                    "result": result,
                },
            }
            self.assertEqual(
                _validate_cpu_result(receipt, phase, 0, archive)[
                    "retained_tree_sha256"
                ],
                manifest["tree_sha256"],
            )
            receipt["claim"]["algorithm_id"] = "attacker"
            with self.assertRaises(Goldbach10Pow27MeasuredWorkloadError):
                _validate_cpu_result(receipt, phase, 0, archive)

    def test_h100_result_requires_exact_future_operational_identity(self) -> None:
        index = 7
        admission = load_build_admission(
            ADMISSION_FIXTURE, allow_test_fixture=True
        )
        leaves = list(range(index, 65_536, 8_192))
        rows = [
            {
                "leaf_index": leaf,
                "receipt_sha256": hashlib.sha256(str(leaf).encode()).hexdigest(),
                "status": "completed-new-receipt",
            }
            for leaf in leaves
        ]
        result = {
            "all_group_receipts_valid": True,
            "execution_attested": False,
            "group_index": index,
            "leaf_indices": leaves,
            "lean_atom_discharged": False,
            "receipts": rows,
            "scheduler_group_count": 8_192,
            "schema": "sparkinterval.goldbach-gpu-run-group.v1",
        }
        text = canonical_json_bytes(result).decode("utf-8")
        receipt = {
            "backend": "azure_ncc40ads_h100_v5",
            "claim": {
                **h100_expected_claim_identity(index, admission),
                "artifacts": {
                    "device_cubin_hash": admission.core["executable"]["sha256"],
                    "host_executable_hash": admission.core["python"]["sha256"],
                    "kernel_manifest_hash": expected_execution_projection_sha256(
                        index, admission
                    ),
                    "source_tree_hash": admission.expected_artifacts[
                        "source_tree_hash"
                    ],
                },
                "output_hash": hashlib.sha256(text.encode()).hexdigest(),
                "result": text,
                "target": "nvidia_h100_sm90",
                "target_profile_hash": admission.deployment[
                    "target_profile_sha256"
                ],
                "trust": "nvidia_h100_confidential_compute",
                "trust_profile_hash": admission.deployment[
                    "trust_profile_sha256"
                ],
            },
        }
        checked = _validate_h100_result(receipt, index, admission)
        self.assertEqual(set(checked["receipt_sha256s"]), set(leaves))
        mutations = {
            "device executable": lambda claim: claim["artifacts"].__setitem__(
                "device_cubin_hash", "c" * 64
            ),
            "host Python": lambda claim: claim["artifacts"].__setitem__(
                "host_executable_hash", "c" * 64
            ),
            "execution projection": lambda claim: claim["artifacts"].__setitem__(
                "kernel_manifest_hash", "c" * 64
            ),
            "source closure": lambda claim: claim["artifacts"].__setitem__(
                "source_tree_hash", "c" * 64
            ),
            "target profile": lambda claim: claim.__setitem__(
                "target_profile_hash", "c" * 64
            ),
            "trust profile": lambda claim: claim.__setitem__(
                "trust_profile_hash", "c" * 64
            ),
        }
        for name, mutation in mutations.items():
            changed = json.loads(json.dumps(receipt))
            mutation(changed["claim"])
            with self.subTest(name=name):
                with self.assertRaises(Goldbach10Pow27MeasuredWorkloadError):
                    _validate_h100_result(changed, index, admission)
        receipt["claim"]["algorithm_hash"] = "0" * 64
        with self.assertRaises(Goldbach10Pow27MeasuredWorkloadError):
            _validate_h100_result(receipt, index, admission)


class Goldbach10Pow27CPUSourceClosureTests(unittest.TestCase):
    def test_measured_worker_runs_from_declared_source_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in SOURCE_PATHS:
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(
                        package
                        / "tools/tg_goldbach_10pow27_azure_measured_workload.py"
                    ),
                    "--help",
                ],
                cwd=package,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
