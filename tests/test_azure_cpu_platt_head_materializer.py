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

from tg_verifier import azure_portfolio
from tg_verifier import azure_cpu_platt_head_materializer as materializer
from tg_verifier.azure_cpu_platt_head_workload_factory import (
    PLATT_HEAD_FACTORY,
    REGISTERED_INPUT,
    REGISTERED_OUTPUT,
    RUNTIME_WHEEL_PATH,
    SOURCE_PATHS,
    expected_registered_hashes,
    factory_for_portfolio_group,
    source_reviewed_materializer_available,
)
from tg_verifier.azure_cpu_portfolio_materializer import (
    PROFILE_PATHS,
    _artifact_record,
)
from tg_verifier.python_flint_runtime import (
    PythonFlintRuntimeError,
    load_pin as load_python_flint_pin,
    verify_wheel,
)
from tests.azure_measured_worker_test_scope import measured_worker_test_scope


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-cpu-platt-head-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-cpu-platt-head-materialization.schema.json"


def load_workload_module():
    spec = importlib.util.spec_from_file_location(
        "gpu_prover_platt_head_azure_measured_workload",
        ROOT / "tools/tg_platt_head_azure_measured_workload.py",
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
        "campaign_id": "platt-head-2e4",
        "command_template": list(PLATT_HEAD_FACTORY.portfolio_argv),
        "depends_on": [],
        "group_id": "platt-head-2e4::single-job",
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "platt-head-2e4",
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


class AzureCPUPlattHeadMaterializerTests(unittest.TestCase):
    def test_registered_identity_pins_both_q128_tables(self) -> None:
        self.assertEqual(
            expected_registered_hashes(),
            {
                "algorithm_hash": "de33cb0d8db40a6b28c32605d9014ca8d593e446e4d1e3390402ea45c13f29ca",
                "algorithm_id": "sparkinterval.ternary-goldbach.platt-head-2e4.v1",
                "domain_hash": "cfbcfeda2b76f99622befbf795d666b745ec45b82691f73bada7b04399464d11",
                "input_hash": "a2409d869f3084fec413d4e7035f17749f4d2a572cd03f6f847f3352a78aca1d",
                "output_hash": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
                "parameters_hash": "af039df434d373002440517fb4b4dd817a8e9fd5028116885df6f2466598986a",
            },
        )
        decoded = json.loads(REGISTERED_INPUT)
        self.assertEqual(
            decoded["all_q128_rows_sha256"],
            "fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca",
        )
        self.assertEqual(
            decoded["included_q128_rows_sha256"],
            "e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7",
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
            "tools/tg_azure_cpu_platt_head_materializer.py",
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
            semantic={"registered_invocation": "plattHead2e4ProductionV1"}
        )
        self.assertTrue(source_reviewed_materializer_available(enabled))
        enabled["semantic_binding"]["registered_invocation"] = "attacker"
        self.assertFalse(source_reviewed_materializer_available(enabled))

    def test_schemas_cli_and_workload_expose_no_caller_executable(self) -> None:
        for path in (SITE_SCHEMA, MANIFEST_SCHEMA):
            schema = json.loads(path.read_bytes())
            if jsonschema is not None:
                jsonschema.Draft202012Validator.check_schema(schema)
        serialized = SITE_SCHEMA.read_text(encoding="utf-8").lower()
        self.assertNotIn("workload_executable", serialized)
        self.assertNotIn('"shell"', serialized)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/tg_azure_cpu_platt_head_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("materialize", result.stdout)
        source = (ROOT / "tools/tg_platt_head_azure_measured_workload.py").read_text(
            encoding="utf-8"
        ).lower()
        for forbidden in ("shell=true", "os.system", "popen("):
            self.assertNotIn(forbidden, source)
        self.assertEqual(PLATT_HEAD_FACTORY.command_argv[:2], ("artifacts/python3", "-I"))
        self.assertEqual(
            PLATT_HEAD_FACTORY.trace_verifier_argv[:2], ("artifacts/python3", "-I")
        )
        self.assertEqual(
            PLATT_HEAD_FACTORY.command_argv[
                PLATT_HEAD_FACTORY.command_argv.index("--wheel") + 1
            ],
            RUNTIME_WHEEL_PATH,
        )

    def test_exact_runtime_pin_rejects_a_same_named_corrupt_wheel(self) -> None:
        upstream = load_python_flint_pin()
        wheel = upstream["runtime_wheel"]
        self.assertEqual(wheel["sha256"], "376b88cacd30612479e839ffdba887599d3f9c8c0e214852bf80bb2b194e4d76")
        self.assertEqual(wheel["extracted_tree_sha256"], "ebab958796d833d67b2e282611c3481a7dc624ad2b6f1aedb8d916d8ceb5f1a6")
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / wheel["filename"]
            candidate.write_bytes(b"not the reviewed wheel")
            with self.assertRaises(PythonFlintRuntimeError):
                verify_wheel(candidate, upstream)

    def test_job_binds_registered_invocation_and_review_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_root = root / "artifact-root"
            host = write_bytes(
                artifact_root / "artifacts/python3", b"python", 0o500
            )
            source_tree = write_bytes(
                artifact_root / "source/source-closure.json", b"{}\n"
            )
            workload = write_bytes(
                artifact_root / "tools/tg_platt_head_azure_measured_workload.py",
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
                    role="reviewed_source_closure_manifest",
                    statement_role="source_tree",
                    executable=False,
                ),
                _artifact_record(
                    workload,
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
                source_context(), PLATT_HEAD_FACTORY, artifact_root, records, site
            )
            self.assertEqual(job["input_artifact"]["sha256"], expected_registered_hashes()["input_hash"])
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

    def test_trace_verifier_replays_the_loaded_plan_not_a_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = SimpleNamespace(
                challenge="c" * 64,
                job_binding="d" * 64,
                input=write_bytes(root / "input.json", workload.REGISTERED_INPUT),
                output=write_bytes(root / "result.txt", b"true"),
                trace=root / "trace.json",
                wheel=write_bytes(root / "runtime.whl", b"wheel"),
                work=root / "work",
            )
            archive = write_bytes(
                args.work / "platt-head-retained.tar", b"retained archive"
            )
            wheel_sha256 = "a" * 64
            retained_tree_sha256 = "b" * 64
            table_raw = b"table"
            table_sha256 = hashlib.sha256(table_raw).hexdigest()
            replay_rows = [{"chunk_index": index} for index in range(6)]
            manifest = {
                "replay_chunks": replay_rows,
                "table_sha256": table_sha256,
                "tree_sha256": retained_tree_sha256,
            }
            input_sha256 = hashlib.sha256(workload.REGISTERED_INPUT).hexdigest()
            result_sha256 = hashlib.sha256(b"true").hexdigest()
            retained_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
            trace = {
                "algorithm_id": workload.REGISTERED_ALGORITHM_ID,
                "challenge_nonce": args.challenge,
                "input_sha256": input_sha256,
                "iteration_count": workload.TRACE_ITERATIONS,
                "job_binding_sha256": args.job_binding,
                "kind": workload.TRACE_KIND,
                "result_sha256": result_sha256,
                "schema_version": 1,
                "trace_sha256": workload._trace_hash(
                    challenge=args.challenge,
                    job_binding=args.job_binding,
                    input_sha256=input_sha256,
                    wheel_sha256=wheel_sha256,
                    retained_sha256=retained_sha256,
                    retained_tree_sha256=retained_tree_sha256,
                    table_sha256=table_sha256,
                    result_sha256=result_sha256,
                ),
            }
            args.trace.write_bytes(workload.canonical_json_bytes(trace))
            loaded_plan = {"kind": "loaded-plan"}

            def fake_extract(_archive, retained, **_limits):
                (retained / "campaign").mkdir(parents=True)
                (retained / "PlattHeadQ128.lean").write_bytes(table_raw)

            with measured_worker_test_scope(args), mock.patch.object(
                workload, "verify_wheel", return_value={"sha256": wheel_sha256}
            ), mock.patch.object(workload, "_activate_runtime"), mock.patch.object(
                workload, "extract_archive", side_effect=fake_extract
            ), mock.patch.object(
                workload, "_validate_retained", return_value=manifest
            ), mock.patch.object(
                workload, "load_plan", return_value=(loaded_plan, b"plan", "e" * 64)
            ), mock.patch.object(
                workload, "replay_plan_count", return_value=22_491
            ) as replay_count, mock.patch.object(
                workload,
                "replay_chunk",
                side_effect=lambda _campaign, index: replay_rows[index],
            ), mock.patch.object(
                workload,
                "verify_campaign",
                return_value={"complete_chain": True, "final_present": True},
            ), mock.patch.object(
                workload, "retained_head_q128_cells", return_value=[]
            ), mock.patch.object(
                workload, "render_head_q128_lean_module", return_value="table"
            ):
                workload.verify_trace(args)
            replay_count.assert_called_once_with(loaded_plan)


class AzureCPUPlattHeadSourceClosureTests(unittest.TestCase):
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
                    str(package / "tools/tg_platt_head_azure_measured_workload.py"),
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
