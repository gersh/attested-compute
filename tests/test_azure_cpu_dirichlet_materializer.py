# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
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

from tg_verifier import azure_cpu_dirichlet_materializer as materializer
from tg_verifier.azure_cpu_dirichlet_workload_factory import (
    DIRICHLET_FACTORY,
    DIRICHLET_POSTCHECK_FACTORY,
    GROUP_ID,
    POSTCHECK_GROUP_ID,
    Q1_GROUP_ID,
    REGISTERED_INPUT,
    REGISTERED_OUTPUT,
    RUNTIME_WHEEL_PATH,
    SOURCE_PATHS,
    expected_registered_hashes,
    factory_for_portfolio_group,
    postcheck_materializer_blocker,
    source_reviewed_materializer_available,
)
from tg_verifier.azure_cpu_portfolio_materializer import PROFILE_PATHS, _artifact_record
from tests.azure_measured_worker_test_scope import measured_worker_test_scope


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-cpu-dirichlet-materializer-site.schema.json"
POSTCHECK_SITE_SCHEMA = ROOT / "schemas/azure-cpu-dirichlet-postcheck-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-cpu-dirichlet-materialization.schema.json"


def load_workload_module():
    spec = importlib.util.spec_from_file_location(
        "gpu_prover_dirichlet_azure_measured_workload",
        ROOT / "tools/tg_dirichlet_azure_measured_workload.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


workload = load_workload_module()


def write_bytes(path: Path, raw: bytes, mode: int = 0o400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def pin(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def source_group(*, semantic: object = None) -> dict[str, object]:
    return {
        "backend_class": "cpu_flint_sidecar",
        "campaign_id": "platt-dirichlet-theorem-7-1",
        "command_template": list(DIRICHLET_FACTORY.portfolio_argv),
        "depends_on": [Q1_GROUP_ID],
        "group_id": GROUP_ID,
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "platt-dirichlet-theorem-7-1",
        "phase_id": "single-job",
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": semantic,
        "shard_count": 1,
        "terminal": False,
    }


def postcheck_group() -> dict[str, object]:
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": "platt-dirichlet-theorem-7-1",
        "command_template": list(DIRICHLET_POSTCHECK_FACTORY.portfolio_argv),
        "depends_on": [GROUP_ID],
        "group_id": POSTCHECK_GROUP_ID,
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "platt-dirichlet-theorem-7-1",
        "phase_id": "postcheck",
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": None,
        "shard_count": 1,
        "terminal": True,
    }


def source_context() -> SimpleNamespace:
    rows = []
    for relative in PROFILE_PATHS.values():
        path = ROOT / relative
        raw = path.read_bytes()
        rows.append(
            {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
        )
    return SimpleNamespace(
        repository_root=ROOT,
        cluster_manifest={"repository_binding": {"files": rows}},
    )


class AzureCPUDirichletMaterializerTests(unittest.TestCase):
    def test_registered_identity_is_literal_and_source_wide(self) -> None:
        self.assertEqual(
            expected_registered_hashes(),
            {
                "algorithm_hash": "7b956d4a04403f9ba32fa2908a72cfa1483928991b3fa478d4bcfd79b089f33c",
                "algorithm_id": "sparkinterval.ternary-goldbach.platt-dirichlet-theorem-7-1.v1",
                "domain_hash": "9b914c30a535b241a17b3180b52f759e3e52ed4424f2a93be4481323b627f31e",
                "input_hash": "42fe4b88a40a22d854292bf030a1eff009d32cf211e47085d43d79a6f2b8c8e9",
                "output_hash": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
                "parameters_hash": "975b05caf3057f499a0d5673a438e74ff781702ceb0ffe8ca8f018f582c269f0",
            },
        )
        decoded = json.loads(REGISTERED_INPUT)
        self.assertEqual(decoded["source_modulus_lower"], 1)
        self.assertEqual(decoded["source_modulus_upper"], 400_000)
        self.assertEqual(decoded["q2_to_q400000_primitive_character_count"], 29_565_923_837)
        self.assertEqual(REGISTERED_OUTPUT, b"true")

    def test_source_and_postcheck_factories_fail_closed(self) -> None:
        exact = source_group()
        self.assertIsNotNone(factory_for_portfolio_group(exact))
        self.assertTrue(source_reviewed_materializer_available(exact))
        for key, replacement in (
            ("command_template", ["sh", "-c", "attacker"]),
            ("depends_on", []),
            ("terminal", True),
            ("shard_count", 2),
        ):
            changed = copy.deepcopy(exact)
            changed[key] = replacement
            self.assertFalse(source_reviewed_materializer_available(changed))
        enabled = source_group(
            semantic={"registered_invocation": "plattDirichletTheorem71ProductionV1"}
        )
        self.assertTrue(source_reviewed_materializer_available(enabled))
        enabled["semantic_binding"]["registered_invocation"] = "attacker"
        self.assertFalse(source_reviewed_materializer_available(enabled))
        exact_postcheck = postcheck_group()
        self.assertIs(
            factory_for_portfolio_group(exact_postcheck),
            DIRICHLET_POSTCHECK_FACTORY,
        )
        self.assertTrue(source_reviewed_materializer_available(exact_postcheck))
        self.assertIsNone(postcheck_materializer_blocker(exact_postcheck))
        changed_postcheck = postcheck_group()
        changed_postcheck["depends_on"] = []
        self.assertIsNone(factory_for_portfolio_group(changed_postcheck))
        self.assertIsNone(postcheck_materializer_blocker(changed_postcheck))

    def test_schemas_cli_and_worker_have_no_caller_executable(self) -> None:
        for path in (SITE_SCHEMA, POSTCHECK_SITE_SCHEMA, MANIFEST_SCHEMA):
            schema = json.loads(path.read_bytes())
            if jsonschema is not None:
                jsonschema.Draft202012Validator.check_schema(schema)
        serialized = SITE_SCHEMA.read_text(encoding="utf-8").lower()
        self.assertNotIn("workload_executable", serialized)
        self.assertNotIn('"shell"', serialized)
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/tg_azure_cpu_dirichlet_materializer.py"), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("materialize", result.stdout)
        source = (ROOT / "tools/tg_dirichlet_azure_measured_workload.py").read_text(
            encoding="utf-8"
        ).lower()
        for forbidden in ("shell=true", "os.system"):
            self.assertNotIn(forbidden, source)
        # The packed H100 phase deliberately streams the reviewed runner's
        # stdout directly into the fail-closed reducer.  Process creation is
        # fixed-argv and must retain the explicit no-shell boundary.
        self.assertIn("subprocess.popen(", source)
        self.assertIn("shell=false", source)
        self.assertEqual(DIRICHLET_FACTORY.command_argv[:2], ("artifacts/python3", "-I"))
        self.assertEqual(
            DIRICHLET_FACTORY.command_argv[
                DIRICHLET_FACTORY.command_argv.index("--wheel") + 1
            ],
            RUNTIME_WHEEL_PATH,
        )
        self.assertEqual(
            DIRICHLET_POSTCHECK_FACTORY.command_argv[
                DIRICHLET_POSTCHECK_FACTORY.command_argv.index(
                    "--predecessor-certificate"
                ) + 1
            ],
            "inputs/dirichlet-source-certificate.tar",
        )

    def test_job_binds_invocation_q1_dependency_and_review_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_root = root / "artifact-root"
            host = write_bytes(artifact_root / "artifacts/python3", b"python", 0o500)
            source_tree = write_bytes(artifact_root / "source/source-closure.json", b"{}\n")
            q1 = write_bytes(artifact_root / "inputs/platt-trudgian-rh-3e12.tar", b"q1")
            q1_receipt = write_bytes(
                artifact_root / "inputs/platt-trudgian-rh-3e12-receipt.json",
                b"receipt",
            )
            records = [
                _artifact_record(host, artifact_root, role="image_bound_cpython_host", statement_role="host_executable", executable=True),
                _artifact_record(source_tree, artifact_root, role="reviewed_source_closure_manifest", statement_role="source_tree", executable=False),
                _artifact_record(q1, artifact_root, role="complete_platt_trudgian_q1_campaign_dependency", statement_role=None, executable=False),
                _artifact_record(q1_receipt, artifact_root, role="production_platt_trudgian_q1_trusted_compute_receipt", statement_role=None, executable=False),
            ]
            runner = write_bytes(root / "runner-policy.json", b"{}\n")
            site = {"base": {"policies": {"runner": {**pin(runner), "classification": "production", "policy_id": "sparkinterval.runner.azure-cpu.production.v1"}}}}
            job = materializer._job(
                source_context(), DIRICHLET_FACTORY, artifact_root, records, site
            )
            self.assertEqual(job["input_artifact"]["sha256"], expected_registered_hashes()["input_hash"])
            self.assertEqual(job["work_trace_contract"]["expected_iterations"], 4)
            self.assertIn(
                "inputs/platt-trudgian-rh-3e12.tar",
                {row["path"] for row in job["artifact_closure"]["files"]},
            )

    def test_postcheck_job_binds_authenticated_predecessor_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_root = root / "artifact-root"
            host = write_bytes(artifact_root / "artifacts/python3", b"python", 0o500)
            source_tree = write_bytes(
                artifact_root / "source/source-closure.json", b"{}\n"
            )
            certificate = write_bytes(
                artifact_root / "inputs/dirichlet-source-certificate.tar", b"cert"
            )
            receipt = write_bytes(
                artifact_root / "inputs/dirichlet-source-receipt.json", b"receipt"
            )
            records = [
                _artifact_record(host, artifact_root, role="image_bound_cpython_host", statement_role="host_executable", executable=True),
                _artifact_record(source_tree, artifact_root, role="reviewed_source_closure_manifest", statement_role="source_tree", executable=False),
                _artifact_record(certificate, artifact_root, role="authenticated_dirichlet_source_certificate_archive", statement_role=None, executable=False),
                _artifact_record(receipt, artifact_root, role="production_dirichlet_source_trusted_compute_receipt", statement_role=None, executable=False),
            ]
            runner = write_bytes(root / "runner-policy.json", b"{}\n")
            site = {"base": {"policies": {"runner": {**pin(runner), "classification": "production", "policy_id": "sparkinterval.runner.azure-cpu.production.v1"}}}}
            job = materializer._job(
                source_context(),
                DIRICHLET_POSTCHECK_FACTORY,
                artifact_root,
                records,
                site,
            )
            self.assertEqual(
                job["job_id"],
                "tg-platt-dirichlet-theorem-7-1-retained-postcheck-v1",
            )
            self.assertIn(
                "production-receipt-authenticates-bundle-and-source-trace",
                job["work_trace_contract"]["trace_algorithm_definition"],
            )
            self.assertIn(
                "inputs/dirichlet-source-certificate.tar",
                {row["path"] for row in job["artifact_closure"]["files"]},
            )

    def test_postcheck_runtime_closure_copies_exact_certificate_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            certificate = write_bytes(root / "source-certificate.tar", b"certificate")
            receipt = write_bytes(root / "source-receipt.json", b"receipt")
            artifact_root = root / "artifact-root"
            artifact_root.mkdir()
            site = {
                "dirichlet": {
                    "flint_source_root": str(root),
                    "predecessor_certificate_archive": pin(certificate),
                    "predecessor_trusted_receipt": pin(receipt),
                    "python_flint_source_root": str(root),
                    "python_flint_wheel": pin(receipt),
                }
            }
            with mock.patch.object(
                materializer,
                "_build_python_flint_runtime_closure",
                return_value=([], [], {"runtime": "test"}),
            ):
                records, steps, runtime = materializer._build_runtime_closure(
                    source_context(),
                    site,
                    artifact_root,
                    DIRICHLET_POSTCHECK_FACTORY,
                )
            self.assertEqual(runtime, {"runtime": "test"})
            self.assertEqual(
                (artifact_root / "inputs/dirichlet-source-certificate.tar").read_bytes(),
                b"certificate",
            )
            self.assertEqual(
                steps[-1]["kind"],
                "pinned_authenticated_dirichlet_source_certificate",
            )
            self.assertEqual(
                {row["role"] for row in records},
                {
                    "authenticated_dirichlet_source_certificate_archive",
                    "production_dirichlet_source_trusted_compute_receipt",
                },
            )

    def test_postcheck_authenticates_predecessor_chain_and_rejects_archive_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            q1_archive = write_bytes(
                stage / "bundle-root/inputs/platt-trudgian-rh-3e12.tar", b"q1"
            )
            q1_receipt = write_bytes(
                stage / "bundle-root/inputs/platt-trudgian-rh-3e12-receipt.json",
                b"q1 receipt",
            )
            retained = write_bytes(
                stage / "bundle-root/work/platt-dirichlet-theorem-7-1/dirichlet-retained.tar",
                b"retained",
            )
            output = write_bytes(
                stage / "bundle-root/output/registered-result.txt", b"true"
            )
            q1_sha = hashlib.sha256(q1_archive.read_bytes()).hexdigest()
            q1_receipt_sha = hashlib.sha256(q1_receipt.read_bytes()).hexdigest()
            retained_sha = hashlib.sha256(retained.read_bytes()).hexdigest()
            challenge = "a" * 64
            job_binding = "b" * 64
            input_sha = hashlib.sha256(workload.REGISTERED_INPUT).hexdigest()
            result_sha = hashlib.sha256(output.read_bytes()).hexdigest()
            source_final_sha = "c" * 64
            tree_sha = "d" * 64
            trace = {
                "algorithm_id": workload.REGISTERED_ALGORITHM_ID,
                "challenge_nonce": challenge,
                "input_sha256": input_sha,
                "iteration_count": workload.TRACE_ITERATIONS,
                "job_binding_sha256": job_binding,
                "kind": workload.TRACE_KIND,
                "result_sha256": result_sha,
                "schema_version": 1,
                "trace_sha256": workload._trace_hash(
                    challenge=challenge,
                    job_binding=job_binding,
                    input_sha256=input_sha,
                    q1_archive_sha256=q1_sha,
                    q1_receipt_sha256=q1_receipt_sha,
                    retained_archive_sha256=retained_sha,
                    retained_tree_sha256=tree_sha,
                    source_final_sha256=source_final_sha,
                    result_sha256=result_sha,
                ),
            }
            trace_path = write_bytes(
                stage / "bundle-root/output/work-trace.json",
                workload.canonical_json_bytes(trace),
            )
            trace_sha = hashlib.sha256(trace_path.read_bytes()).hexdigest()
            claim = {
                "algorithm_hash": "1" * 64,
                "algorithm_id": workload.REGISTERED_ALGORITHM_ID,
                "completion": "successful",
                "domain_hash": "2" * 64,
                "input_hash": input_sha,
                "nonce": challenge,
                "output_hash": result_sha,
                "parameters_hash": "3" * 64,
                "result": "true",
                "target_profile_hash": "4" * 64,
                "trust_profile_hash": "5" * 64,
            }
            statement = {
                "algorithm": {"algorithm_id": claim["algorithm_id"], "definition_sha256": claim["algorithm_hash"]},
                "completion": {"status": "success"},
                "domain_coverage": {"canonical_sha256": claim["domain_hash"], "value": {"x": 1}},
                "execution_environment": {"canonical_sha256": "6" * 64, "value": {"job_binding_sha256": job_binding, "work_trace_artifact_sha256": trace_sha, "work_trace_chain_sha256": trace["trace_sha256"]}},
                "input_artifact": {"path": "input/registered-invocation.json", "sha256": input_sha, "size_bytes": len(workload.REGISTERED_INPUT)},
                "nonce": challenge,
                "output_artifact": {"path": "output/registered-result.txt", "sha256": result_sha, "size_bytes": 4},
                "parameters": {"canonical_sha256": claim["parameters_hash"], "value": {"x": 1}},
                "target_profile": {"profile_id": "azure", "sha256": claim["target_profile_hash"]},
                "trust_profile": {"profile_id": "snp", "sha256": claim["trust_profile_hash"]},
            }
            statement_path = write_bytes(
                stage / "bundle-root/runner/statement.json",
                workload.canonical_json_bytes(statement),
            )
            statement_sha = workload.canonical_sha256(statement)
            bundle_sha = "7" * 64
            bundle = {"statement": statement}
            write_bytes(
                stage / "bundle-root/run-bundle.json",
                workload.canonical_json_bytes(bundle),
            )
            certificate = root / "certificate.tar"
            workload.create_archive(stage, certificate)
            receipt_path = write_bytes(root / "source-receipt.json", b"receipt")
            source_receipt = {
                "bindings": {"run_bundle_sha256": bundle_sha, "wire_statement_sha256": statement_sha},
                "claim": claim,
                "receipt_sha256": "8" * 64,
            }
            checked = {
                "artifacts_verified": True,
                "bundle_sha256": bundle_sha,
                "statement_sha256": statement_sha,
            }
            with mock.patch.object(
                workload, "_verified_production_receipt", return_value=source_receipt
            ), mock.patch.object(
                workload.verify_run_bundle, "verify_bundle", return_value=checked
            ), mock.patch.object(workload, "_verify_q1_receipt", return_value={}):
                loaded = workload._load_predecessor(
                    certificate, receipt_path, root / "extracted"
                )
            self.assertEqual(loaded["retained_archive_sha256"], retained_sha)
            self.assertEqual(loaded["source_trace_sha256"], trace_sha)
            workload._source_trace_identity(
                loaded["source_trace"],
                statement=loaded["statement"],
                q1_archive_sha256=loaded["q1_archive_sha256"],
                q1_receipt_sha256=loaded["q1_receipt_sha256"],
                retained_archive_sha256=loaded["retained_archive_sha256"],
                retained_tree_sha256=tree_sha,
                source_final_sha256=source_final_sha,
            )

            retained.chmod(0o600)
            retained.write_bytes(b"tampered")
            retained.chmod(0o400)
            tampered_certificate = root / "tampered-certificate.tar"
            workload.create_archive(stage, tampered_certificate)
            with mock.patch.object(
                workload, "_verified_production_receipt", return_value=source_receipt
            ), mock.patch.object(
                workload.verify_run_bundle, "verify_bundle", return_value=checked
            ), mock.patch.object(workload, "_verify_q1_receipt", return_value={}):
                tampered = workload._load_predecessor(
                    tampered_certificate,
                    receipt_path,
                    root / "tampered-extracted",
                )
            with self.assertRaisesRegex(
                workload.DirichletMeasuredWorkloadError,
                "source trace chain differs",
            ):
                workload._source_trace_identity(
                    tampered["source_trace"],
                    statement=tampered["statement"],
                    q1_archive_sha256=tampered["q1_archive_sha256"],
                    q1_receipt_sha256=tampered["q1_receipt_sha256"],
                    retained_archive_sha256=tampered[
                        "retained_archive_sha256"
                    ],
                    retained_tree_sha256=tree_sha,
                    source_final_sha256=source_final_sha,
                )

    def test_postcheck_emits_true_only_after_replay_and_replays_again_for_trace(self) -> None:
        replay = {
            "predecessor_certificate_sha256": "1" * 64,
            "predecessor_receipt_file_sha256": "2" * 64,
            "predecessor_receipt_sha256": "3" * 64,
            "predecessor_statement_sha256": "4" * 64,
            "predecessor_source_trace_sha256": "5" * 64,
            "q1_archive_sha256": "6" * 64,
            "q1_receipt_sha256": "7" * 64,
            "retained_archive_sha256": "8" * 64,
            "retained_tree_sha256": "9" * 64,
            "source_final_sha256": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = SimpleNamespace(
                algorithm_id=workload.REGISTERED_ALGORITHM_ID,
                challenge="b" * 64,
                job_binding="c" * 64,
                input=write_bytes(root / "input.json", workload.REGISTERED_INPUT),
                output=root / "output.txt",
                trace=root / "trace.json",
                wheel=write_bytes(root / "runtime.whl", b"wheel"),
                predecessor_certificate=write_bytes(root / "certificate.tar", b"cert"),
                predecessor_receipt=write_bytes(root / "receipt.json", b"receipt"),
                work=root / "work",
            )
            with measured_worker_test_scope(args), mock.patch.object(
                workload, "verify_wheel", return_value={}
            ), mock.patch.object(
                workload, "_replay_predecessor", return_value=replay
            ) as replay_call:
                workload.postcheck(args)
                workload.verify_postcheck_trace(args)
            self.assertEqual(args.output.read_bytes(), b"true")
            self.assertEqual(replay_call.call_count, 2)

            args.output.unlink()
            args.trace.unlink()
            with measured_worker_test_scope(args), mock.patch.object(
                workload, "verify_wheel", return_value={}
            ), mock.patch.object(
                workload,
                "_replay_predecessor",
                side_effect=workload.DirichletMeasuredWorkloadError("bad replay"),
            ):
                with self.assertRaises(workload.DirichletMeasuredWorkloadError):
                    workload.postcheck(args)
            self.assertFalse(args.output.exists())
            self.assertFalse(args.trace.exists())

    def test_trace_verifier_replays_q1_q2_and_every_checker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            q1_archive = write_bytes(root / "q1.tar", b"q1 archive")
            q1_receipt_path = write_bytes(root / "q1-receipt.json", b"q1 receipt")
            retained = write_bytes(root / "work/dirichlet-retained.tar", b"q2 archive")
            args = SimpleNamespace(
                algorithm_id=workload.REGISTERED_ALGORITHM_ID,
                challenge="c" * 64,
                job_binding="d" * 64,
                input=write_bytes(root / "input.json", workload.REGISTERED_INPUT),
                output=write_bytes(root / "result.txt", b"true"),
                trace=root / "trace.json",
                wheel=write_bytes(root / "runtime.whl", b"wheel"),
                q1_archive=q1_archive,
                q1_receipt=q1_receipt_path,
                work=root / "work",
            )
            q1 = {
                "atom": "platt-trudgian-rh-3e12",
                "height": 3_000_175_332_800,
                "multiplicity_count": 12_363_153_437_138,
                "plan_sha256": "1" * 64,
                "receipt_merkle_root_sha256": "2" * 64,
                "trusted_compute": {
                    "receipt_sha256": "6" * 64,
                    "registered_invocation": "plattTrudgianFiniteRHProductionV1",
                    "verifier_key_id": "production-test-key",
                },
            }
            q2 = {
                "characters_covered": 29_565_923_837,
                "coverage_class": "full_source_external_checker_asserted",
                "schedule_sha256": "3" * 64,
                "terminal_chain_sha256": "4" * 64,
            }
            source_raw = workload.canonical_json_bytes(workload._source_final(q1, q2))
            tree_sha = "5" * 64
            input_sha = hashlib.sha256(workload.REGISTERED_INPUT).hexdigest()
            result_sha = hashlib.sha256(b"true").hexdigest()
            q1_sha = hashlib.sha256(q1_archive.read_bytes()).hexdigest()
            q1_receipt_sha = hashlib.sha256(q1_receipt_path.read_bytes()).hexdigest()
            retained_sha = hashlib.sha256(retained.read_bytes()).hexdigest()
            source_sha = hashlib.sha256(source_raw).hexdigest()
            trace = {
                "algorithm_id": workload.REGISTERED_ALGORITHM_ID,
                "challenge_nonce": args.challenge,
                "input_sha256": input_sha,
                "iteration_count": workload.TRACE_ITERATIONS,
                "job_binding_sha256": args.job_binding,
                "kind": workload.TRACE_KIND,
                "result_sha256": result_sha,
                "schema_version": 1,
                "trace_sha256": workload._trace_hash(
                    challenge=args.challenge,
                    job_binding=args.job_binding,
                    input_sha256=input_sha,
                    q1_archive_sha256=q1_sha,
                    q1_receipt_sha256=q1_receipt_sha,
                    retained_archive_sha256=retained_sha,
                    retained_tree_sha256=tree_sha,
                    source_final_sha256=source_sha,
                    result_sha256=result_sha,
                ),
            }
            args.trace.write_bytes(workload.canonical_json_bytes(trace))

            def fake_extract(_archive, destination, **_limits):
                destination.mkdir(parents=True)
                if destination.name == "q2":
                    (destination / "source-final.json").write_bytes(source_raw)

            with measured_worker_test_scope(args), mock.patch.object(
                workload, "verify_wheel", return_value={}
            ), mock.patch.object(
                workload, "_activate_runtime"
            ), mock.patch.object(workload, "extract_archive", side_effect=fake_extract), mock.patch.object(
                workload, "_verify_q1", return_value=q1
            ), mock.patch.object(
                workload,
                "_verify_q1_receipt",
                return_value=q1["trusted_compute"],
            ), mock.patch.object(
                workload, "_tree_identity", return_value={"file_count": 1, "size_bytes": 1, "tree_sha256": tree_sha}
            ), mock.patch.object(
                workload, "verify_campaign", return_value={"final_present": True}
            ), mock.patch.object(
                workload, "rerun_external_checkers"
            ) as replay, mock.patch.object(
                workload, "finalize_campaign", return_value=q2
            ):
                workload.verify_trace(args)
            replay.assert_called_once()


class AzureCPUDirichletSourceClosureTests(unittest.TestCase):
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
                    str(package / "tools/tg_dirichlet_azure_measured_workload.py"),
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
