# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import contextlib
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

from tg_verifier import azure_portfolio
from tg_verifier import azure_cpu_a7_materializer as materializer
from tg_verifier.azure_cpu_a7_workload_factory import (
    A7_FACTORY,
    REGISTERED_INPUT,
    REGISTERED_OUTPUT,
    RETAINED_ARTIFACT_SHA256,
    SOURCE_PATHS,
    expected_registered_hashes,
    factory_for_portfolio_group,
    source_reviewed_materializer_available,
)
from tg_verifier.azure_cpu_platt_head_workload_factory import RUNTIME_WHEEL_PATH
from tg_verifier.azure_cpu_portfolio_materializer import (
    PROFILE_PATHS,
    _artifact_record,
)
from tools import tg_verify as tg_verify_cli
from tests.azure_measured_worker_test_scope import measured_worker_test_scope


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-cpu-a7-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-cpu-a7-materialization.schema.json"
SITE_EXAMPLE = (
    ROOT / "examples/trusted-compute/azure_cpu_a7_materializer_site.redacted.json"
)


def load_workload_module():
    spec = importlib.util.spec_from_file_location(
        "gpu_prover_a7_azure_measured_workload",
        ROOT / "tools/tg_a7_azure_measured_workload.py",
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


def group(*, semantic: object = None) -> dict[str, object]:
    return {
        "backend_class": "cpu_flint_sidecar",
        "campaign_id": "ch25-a7-boundary",
        "command_template": list(A7_FACTORY.portfolio_argv),
        "depends_on": [],
        "group_id": "ch25-a7-boundary::single-job",
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "ch25-a7-boundary",
        "phase_id": "single-job",
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": semantic,
        "shard_count": 1,
        "terminal": True,
    }


def source_context() -> SimpleNamespace:
    rows = []
    for relative in PROFILE_PATHS.values():
        path = ROOT / relative
        raw = path.read_bytes()
        rows.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        )
    return SimpleNamespace(
        repository_root=ROOT,
        cluster_manifest={"repository_binding": {"files": rows}},
    )


def replay_report(*, elapsed: int) -> dict[str, object]:
    return {
        "accepted": True,
        "artifact_kind": "ch25_a7_boundary",
        "verification_class": "complete_external_flint_arb_leaf_replay",
        "artifact_sha256": RETAINED_ARTIFACT_SHA256,
        "artifact_bytes_match_pinned_sha256": True,
        "python_flint_version": "0.9.0",
        "flint_version": "3.6.0",
        "flint_release": 30_600,
        "leaf_count": 16_191,
        "elapsed_milliseconds": elapsed,
        "four_edge_dyadic_cover_verified": True,
        "every_leaf_flint_box_recomputed": True,
        "every_exact_leaf_endpoint_matched": True,
        "all_denominator_and_zeta_nonvanishing_guards_checked": True,
        "strict_norm_square_bound_verified_under_flint_semantics": True,
        "external_analytic_verification_complete": True,
        "ordinary_kernel_lean_proof": False,
        "mathlib_zeta_realization_theorem_present": False,
        "lean_atom_discharged": False,
    }


class AzureCPUA7MaterializerTests(unittest.TestCase):
    def test_registered_identity_is_exact(self) -> None:
        self.assertEqual(
            expected_registered_hashes(),
            {
                "algorithm_hash": "340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa",
                "algorithm_id": "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1",
                "domain_hash": "629d9c7b3c084ef33f69d92abbe22b5120bac210fc963191c4b1e8289ff1dea5",
                "input_hash": "4e45410d2d26467dbd5f78f8ea536b1a8bbf44f1cd5248e234b985bd1f595674",
                "output_hash": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
                "parameters_hash": "f377fb7b8c8d8d033083a0759841411d9bb955e919041f2a5b5be830ed69212e",
            },
        )
        self.assertEqual(
            json.loads(REGISTERED_INPUT),
            {
                "campaign": "ch25-a7-boundary-v1",
                "retained_artifact_sha256": RETAINED_ARTIFACT_SHA256,
            },
        )
        self.assertEqual(REGISTERED_OUTPUT, b"true")

    def test_factory_and_portfolio_route_fail_closed_on_drift(self) -> None:
        exact = group()
        self.assertIsNotNone(factory_for_portfolio_group(exact))
        self.assertTrue(source_reviewed_materializer_available(exact))
        routed = copy.deepcopy(exact)
        azure_portfolio._bind_group_operator_capability(routed)
        self.assertTrue(routed["production_operator_available"])
        self.assertEqual(
            routed["materializer_adapter"],
            "tools/tg_azure_cpu_a7_materializer.py",
        )
        for key, replacement in (
            ("command_template", ["sh", "-c", "attacker"]),
            ("phase_id", "attacker"),
            ("shard_count", 2),
        ):
            changed = copy.deepcopy(exact)
            changed[key] = replacement
            self.assertFalse(source_reviewed_materializer_available(changed))
        enabled = group(
            semantic={"registered_invocation": "ch25A7BoundaryProductionV1"}
        )
        self.assertTrue(source_reviewed_materializer_available(enabled))
        enabled["semantic_binding"]["registered_invocation"] = "attacker"
        self.assertFalse(source_reviewed_materializer_available(enabled))

    def test_schemas_example_cli_and_workload_have_no_caller_executable(self) -> None:
        schemas = [json.loads(path.read_bytes()) for path in (SITE_SCHEMA, MANIFEST_SCHEMA)]
        if jsonschema is not None:
            for schema in schemas:
                jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(json.loads(SITE_EXAMPLE.read_bytes()), schemas[0])
        serialized = SITE_SCHEMA.read_text(encoding="utf-8").lower()
        self.assertNotIn("workload_executable", serialized)
        self.assertNotIn('"shell"', serialized)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/tg_azure_cpu_a7_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("materialize", result.stdout)
        source = (ROOT / "tools/tg_a7_azure_measured_workload.py").read_text(
            encoding="utf-8"
        ).lower()
        for forbidden in ("shell=true", "os.system", "popen("):
            self.assertNotIn(forbidden, source)
        self.assertEqual(A7_FACTORY.command_argv[:2], ("artifacts/python3", "-I"))
        self.assertEqual(
            A7_FACTORY.trace_verifier_argv[:2], ("artifacts/python3", "-I")
        )
        self.assertEqual(
            A7_FACTORY.command_argv[A7_FACTORY.command_argv.index("--wheel") + 1],
            RUNTIME_WHEEL_PATH,
        )

    def test_corrupt_retained_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "a7_boundary.json"
            candidate.write_bytes(b"{}")
            with self.assertRaises(materializer.A7MaterializerError):
                materializer._artifact_identity(candidate)

    def test_job_binds_registered_invocation_and_review_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_root = root / "artifact-root"
            host = write_bytes(artifact_root / "artifacts/python3", b"python", 0o500)
            source_tree = write_bytes(
                artifact_root / "source/a7-source-envelope.json", b"{}\n"
            )
            measured = write_bytes(
                artifact_root / "tools/tg_a7_azure_measured_workload.py",
                b"# measured workload\n",
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
                    source_tree,
                    artifact_root,
                    role="reviewed_a7_source_envelope",
                    statement_role="source_tree",
                    executable=False,
                ),
                _artifact_record(
                    measured,
                    artifact_root,
                    role="reviewed_project_source",
                    statement_role=None,
                    executable=True,
                ),
            ]
            runner = write_bytes(root / "runner-policy.json", b"{}\n")
            site = {
                "base": {
                    "policies": {
                        "runner": {
                            **pin(runner),
                            "classification": "production",
                            "policy_id": "sparkinterval.runner.azure-cpu.production.v1",
                        }
                    }
                }
            }
            job = materializer._job(
                source_context(), A7_FACTORY, artifact_root, records, site
            )
            self.assertEqual(
                job["input_artifact"]["sha256"],
                expected_registered_hashes()["input_hash"],
            )
            self.assertEqual(job["output_contract"]["maximum_bytes"], 16)
            self.assertEqual(job["work_trace_contract"]["expected_iterations"], 3)
            self.assertEqual(
                [
                    row["statement_role"]
                    for row in job["artifact_closure"]["files"]
                    if row["statement_role"] is not None
                ],
                ["host_executable", "source_tree"],
            )

    def test_trace_verifier_performs_a_second_complete_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = write_bytes(root / "a7_boundary.json", b"retained")
            wheel = write_bytes(root / "runtime.whl", b"wheel")
            args = SimpleNamespace(
                challenge="c" * 64,
                job_binding="d" * 64,
                input=write_bytes(root / "input.json", workload.REGISTERED_INPUT),
                output=root / "result.txt",
                trace=root / "trace.json",
                artifact=artifact,
                wheel=wheel,
                work=root / "work",
            )
            real_hash_file_once = workload.hash_file_once

            def fake_hash_file_once(path):
                if Path(path) == artifact:
                    return RETAINED_ARTIFACT_SHA256, len(b"retained")
                return real_hash_file_once(path)

            with measured_worker_test_scope(args), mock.patch.object(
                workload, "hash_file_once", side_effect=fake_hash_file_once
            ), mock.patch.object(
                workload, "verify_wheel", return_value={"sha256": "a" * 64}
            ), mock.patch.object(workload, "_activate_runtime"), mock.patch.object(
                workload,
                "replay_a7_flint",
                side_effect=(replay_report(elapsed=1), replay_report(elapsed=2)),
            ) as replay:
                workload.run(args)
                workload.verify_trace(args)
            self.assertEqual(replay.call_count, 2)
            for call in replay.call_args_list:
                self.assertEqual(call.args, (artifact,))
                self.assertEqual(call.kwargs, {"require_retained_identity": True})
            self.assertEqual(args.output.read_bytes(), b"true")
            retained = json.loads((args.work / workload.REPORT_PATH).read_bytes())
            self.assertNotIn("elapsed_milliseconds", retained)

    def test_materialized_job_hands_exact_a7_result_to_registered_writer(self) -> None:
        """Exercise the materializer/job/worker/result seam without FLINT."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_root = root / "artifact-root"
            host = write_bytes(
                artifact_root / "artifacts/python3", b"python", 0o500
            )
            source_tree = write_bytes(
                artifact_root / "source/a7-source-envelope.json", b"{}\n"
            )
            measured = write_bytes(
                artifact_root / "tools/tg_a7_azure_measured_workload.py",
                b"# measured workload\n",
                0o500,
            )
            artifact = write_bytes(
                artifact_root / "artifacts/a7_boundary.json", b"retained"
            )
            wheel = write_bytes(
                artifact_root / RUNTIME_WHEEL_PATH, b"wheel"
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
                    source_tree,
                    artifact_root,
                    role="reviewed_a7_source_envelope",
                    statement_role="source_tree",
                    executable=False,
                ),
                _artifact_record(
                    measured,
                    artifact_root,
                    role="reviewed_project_source",
                    statement_role=None,
                    executable=True,
                ),
                _artifact_record(
                    artifact,
                    artifact_root,
                    role="reviewed_retained_a7_boundary_transcript",
                    statement_role=None,
                    executable=False,
                ),
                _artifact_record(
                    wheel,
                    artifact_root,
                    role="reviewed_python_flint_runtime_wheel",
                    statement_role=None,
                    executable=False,
                ),
            ]
            runner = write_bytes(root / "runner-policy.json", b"{}\n")
            site = {
                "base": {
                    "policies": {
                        "runner": {
                            **pin(runner),
                            "classification": "production",
                            "policy_id": (
                                "sparkinterval.runner.azure-cpu.production.v1"
                            ),
                        }
                    }
                }
            }
            job = materializer._job(
                source_context(), A7_FACTORY, artifact_root, records, site
            )
            self.assertEqual(
                job["command"]["argv"], list(A7_FACTORY.command_argv)
            )
            self.assertEqual(
                job["input_artifact"]["path"],
                "input/registered-invocation.json",
            )
            self.assertEqual(
                job["output_contract"]["path"],
                "output/registered-result.txt",
            )

            substitutions = {
                "@challenge@": "c" * 64,
                "@job_binding@": "d" * 64,
                "@input@": job["input_artifact"]["path"],
                "@output@": job["output_contract"]["path"],
                "@trace@": job["work_trace_contract"]["path"],
            }
            command = [
                substitutions.get(argument, argument)
                for argument in job["command"]["argv"]
            ]
            self.assertEqual(
                command[:3],
                [
                    "artifacts/python3",
                    "-I",
                    "tools/tg_a7_azure_measured_workload.py",
                ],
            )
            arguments = workload.parser().parse_args(command[3:])
            workload._validate_args(arguments)

            report = replay_report(elapsed=1)
            real_hash_file_once = workload.hash_file_once

            def fake_hash_file_once(path):
                if Path(path) == Path("artifacts/a7_boundary.json"):
                    return RETAINED_ARTIFACT_SHA256, len(b"retained")
                return real_hash_file_once(path)

            with contextlib.chdir(artifact_root), measured_worker_test_scope(
                arguments
            ), mock.patch.object(
                workload, "hash_file_once", side_effect=fake_hash_file_once
            ), mock.patch.object(
                workload, "verify_wheel", return_value={"sha256": "a" * 64}
            ), mock.patch.object(workload, "_activate_runtime"), mock.patch.object(
                workload, "replay_a7_flint", return_value=report
            ) as replay:
                workload.run(arguments)

            replay.assert_called_once_with(
                Path("artifacts/a7_boundary.json"),
                require_retained_identity=True,
            )
            measured_result = artifact_root / job["output_contract"]["path"]
            self.assertEqual(measured_result.read_bytes(), REGISTERED_OUTPUT)
            self.assertEqual(
                hashlib.sha256(measured_result.read_bytes()).hexdigest(),
                expected_registered_hashes()["output_hash"],
            )

            portfolio_result = root / "portfolio/registered-result.txt"
            portfolio_substitutions = {
                "${TG_PYTHON}": sys.executable,
                "${TG_REPOSITORY}/tools/tg_verify.py": str(
                    ROOT / "tools/tg_verify.py"
                ),
                "${TG_A7_TRANSCRIPT}": str(artifact),
                (
                    "${TG_RUN_ROOT}/ch25-a7-boundary/"
                    "registered-result.txt"
                ): str(portfolio_result),
            }
            portfolio_command = [
                portfolio_substitutions.get(argument, argument)
                for argument in A7_FACTORY.portfolio_argv
            ]
            cli_args = tg_verify_cli.build_parser().parse_args(
                portfolio_command[2:]
            )
            with measured_worker_test_scope(arguments), mock.patch.object(
                tg_verify_cli, "replay_a7_flint", return_value=report
            ) as portfolio_replay, mock.patch.object(
                tg_verify_cli, "_emit"
            ) as emit:
                self.assertEqual(cli_args.handler(cli_args), 0)
            portfolio_replay.assert_called_once_with(
                artifact, require_retained_identity=True
            )
            emitted = emit.call_args.args[0]
            metadata = emitted["registered_result_artifact"]
            self.assertEqual(
                portfolio_result.read_bytes(), measured_result.read_bytes()
            )
            self.assertEqual(
                metadata["sha256"], expected_registered_hashes()["output_hash"]
            )


class AzureCPUA7SourceClosureTests(unittest.TestCase):
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
                    str(package / "tools/tg_a7_azure_measured_workload.py"),
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
