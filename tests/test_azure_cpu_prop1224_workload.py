# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
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

from tg_verifier import azure_portfolio
from tg_verifier import azure_cpu_prop1224_materializer as materializer
from tg_verifier.azure_cpu_prop1224_workload_factory import (
    LEAF_COUNT,
    PLAN,
    PLAN_SHA256,
    REGISTERED_INPUT,
    REGISTERED_OUTPUT,
    SOURCE_PATHS,
    WORKER_GROUP_COUNT,
    expected_registered_hashes,
    factory_for_portfolio_group,
    make_factory,
    leaf_indices_for_group,
    source_reviewed_materializer_available,
)
from tg_verifier.azure_cpu_portfolio_materializer import PROFILE_PATHS, _artifact_record
from tests.azure_measured_worker_test_scope import measured_worker_test_scope


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-cpu-prop1224-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-cpu-prop1224-materialization.schema.json"
SITE_EXAMPLE = (
    ROOT
    / "examples/trusted-compute/azure_cpu_prop1224_materializer_site.redacted.json"
)


def load_workload_module():
    spec = importlib.util.spec_from_file_location(
        "gpu_prover_prop1224_azure_measured_workload",
        ROOT / "tools/tg_prop1224_azure_measured_workload.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


workload = load_workload_module()


def load_campaign_module():
    spec = importlib.util.spec_from_file_location(
        "gpu_prover_prop1224_mpfr_campaign_cli",
        ROOT / "tools/tg_prop1224_mpfr_campaign.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


campaign = load_campaign_module()


def write_bytes(path: Path, raw: bytes, mode: int = 0o400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def pin(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    import hashlib

    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def source_context() -> SimpleNamespace:
    import hashlib

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


def group(phase: str, *, semantic: object = None) -> dict[str, object]:
    factory = make_factory(phase, 0)
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": "helfgott-prop-12-2-4-mpfr-v1",
        "command_template": list(factory.portfolio_argv),
        "depends_on": ([] if phase == "mpfr-shards" else [
            "helfgott-prop-12-2-4-mpfr-v1::mpfr-shards"
        ]),
        "group_id": factory.group_id,
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "helfgott-prop-12-2-4",
        "phase_id": phase,
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": semantic,
        "shard_count": factory.shard_count,
        "terminal": factory.terminal,
    }


def args(root: Path, phase: str) -> SimpleNamespace:
    factory = make_factory(phase, 0)
    return SimpleNamespace(
        algorithm_id=factory.algorithm_id,
        challenge="c" * 64,
        handoff=write_bytes(root / "handoff.tar", b"unused"),
        input=write_bytes(root / "input.json", factory.input_bytes),
        job_binding="d" * 64,
        output=root / "output.txt",
        phase=phase,
        runner=write_bytes(root / "runner", b"runner", 0o500),
        shard_index=0,
        trace=root / "trace.json",
        work=root / "work",
    )


def fake_receipt(elapsed: int, shard_index: int = 0) -> dict[str, object]:
    return {
        "arithmetic_report": {"row_root_sha256": "a" * 64},
        "elapsed_milliseconds": elapsed,
        "plan_sha256": PLAN_SHA256,
        "receipt_hash": ("b" if elapsed == 1 else "c") * 64,
        "receipt_schema": "test",
        "runner_executable_sha256": "d" * 64,
        "runner_source_sha256": "e" * 64,
        "shard_index": shard_index,
    }


class AzureCPUProp1224WorkloadTests(unittest.TestCase):
    def test_worker_group_cli_uses_disjoint_strided_logical_leaves(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = campaign.make_mpfr_plan(
                rank_lower=3_315_093_776,
                rank_upper=3_315_093_780,
                leaf_rows=1,
            )
            invocation = SimpleNamespace(
                mpfr_version="4.2.1",
                output_dir=root / "receipts",
                precision_bits=192,
                runner=root / "runner",
                segment_size=250_000,
                worker_group_count=2,
                worker_group_index=1,
                workers=2,
            )

            def run(*, shard_index: int, **_kwargs):
                return {
                    "runner_executable_sha256": "a" * 64,
                    "shard_index": shard_index,
                }

            with mock.patch.object(
                campaign, "run_mpfr_shard", side_effect=run
            ), mock.patch.object(campaign, "validate_receipt"):
                result = campaign.run_worker_group(invocation, plan)
            self.assertEqual(result["first_shard_index"], 1)
            self.assertEqual(result["last_shard_index_inclusive"], 3)
            self.assertEqual(
                sorted(
                    path.name
                    for path in invocation.output_dir.iterdir()
                    if not path.name.startswith(".")
                ),
                ["mpfr-shard-00001.json", "mpfr-shard-00003.json"],
            )

    def test_registered_identity_and_exact_plan_are_pinned(self) -> None:
        self.assertEqual(len(PLAN.shards), LEAF_COUNT)
        groups = [list(leaf_indices_for_group(index)) for index in range(WORKER_GROUP_COUNT)]
        self.assertEqual(
            sorted(item for group_items in groups for item in group_items),
            list(range(LEAF_COUNT)),
        )
        self.assertEqual(PLAN.plan_sha256, PLAN_SHA256)
        self.assertEqual(REGISTERED_OUTPUT, b"true")
        self.assertEqual(
            json.loads(REGISTERED_INPUT),
            {
                "campaign": "helfgott-prop-12-2-4-mpfr-v1",
                "rank_lower": 0,
                "rank_upper": 3_389_047_618,
            },
        )
        self.assertEqual(
            expected_registered_hashes(),
            {
                "algorithm_hash": "184e8f8f60f511868d39a7a1ab7599a4b725415892e99c8fd84a35f8bf6c38a1",
                "algorithm_id": (
                    "sparkinterval.ternary-goldbach."
                    "helfgott-proposition-12-2-4-mpfr.v1"
                ),
                "domain_hash": "effa0ec90992a66d497c13fba77923a9fb96996d93be9d8d6fd54b21a09e92a3",
                "input_hash": "ced1a63532a63b6e24290c51082ff8865ce38c75daae0d4f3439a63eef2444ec",
                "output_hash": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
                "parameters_hash": "fac07cd6c76a9e2caf7e475107046d76683788426b1c9e26ac8d66aed8114853",
            },
        )

    def test_factory_rejects_portfolio_drift(self) -> None:
        for phase in ("mpfr-shards", "merge-and-verify"):
            exact = group(phase)
            self.assertIsNotNone(factory_for_portfolio_group(exact, 0))
            for key, replacement in (
                ("command_template", ["sh", "-c", "attacker"]),
                ("owner_atom_id", "attacker"),
                ("shard_count", 1 if phase == "mpfr-shards" else 2),
            ):
                changed = copy.deepcopy(exact)
                changed[key] = replacement
                self.assertIsNone(factory_for_portfolio_group(changed, 0))
        enabled = group(
            "merge-and-verify",
            semantic={"registered_invocation": "helfgottProp1224ProductionV1"},
        )
        self.assertIsNotNone(factory_for_portfolio_group(enabled, 0))
        enabled["semantic_binding"]["registered_invocation"] = "attacker"
        self.assertIsNone(factory_for_portfolio_group(enabled, 0))

    def test_portfolio_routes_both_phases_to_closed_materializer(self) -> None:
        for phase in ("mpfr-shards", "merge-and-verify"):
            exact = group(phase)
            self.assertTrue(source_reviewed_materializer_available(exact))
            routed = copy.deepcopy(exact)
            azure_portfolio._bind_group_operator_capability(routed)
            self.assertTrue(routed["production_operator_available"])
            self.assertEqual(
                routed["materializer_adapter"],
                "tools/tg_azure_cpu_prop1224_materializer.py",
            )

    def test_schemas_example_and_cli_are_closed(self) -> None:
        try:
            import jsonschema
        except ImportError:
            jsonschema = None
        schemas = [json.loads(path.read_bytes()) for path in (SITE_SCHEMA, MANIFEST_SCHEMA)]
        if jsonschema is not None:
            for schema in schemas:
                jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(json.loads(SITE_EXAMPLE.read_bytes()), schemas[0])
        serialized = SITE_SCHEMA.read_text(encoding="utf-8").lower()
        self.assertNotIn("workload_executable", serialized)
        self.assertNotIn('"shell"', serialized)
        import subprocess

        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/tg_azure_cpu_prop1224_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("materialize", completed.stdout)

    def test_terminal_job_binds_registered_invocation_and_source_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_root = root / "artifact-root"
            host = write_bytes(artifact_root / "artifacts/python3", b"python", 0o500)
            producer = write_bytes(
                artifact_root / "artifacts/tg_prop1224_mpfr_shard", b"runner", 0o500
            )
            source_tree = write_bytes(
                artifact_root / "source/source-closure.json", b"{}\n"
            )
            measured = write_bytes(
                artifact_root / "tools/tg_prop1224_azure_measured_workload.py",
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
                    producer,
                    artifact_root,
                    role="static_prop1224_mpfr_gmp_shard_producer",
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
                    measured,
                    artifact_root,
                    role="reviewed_project_source",
                    statement_role=None,
                    executable=True,
                ),
            ]
            handoff = write_bytes(
                artifact_root / "input/prop1224-phase-handoff.tar", b"handoff"
            )
            runner_policy = write_bytes(root / "runner-policy.json", b"{}\n")
            site = {
                "base": {
                    "policies": {
                        "runner": {
                            **pin(runner_policy),
                            "classification": "production",
                            "policy_id": "sparkinterval.runner.azure-cpu.production.v1",
                        }
                    }
                }
            }
            job = materializer._job(
                source_context(),
                make_factory("merge-and-verify", 0),
                artifact_root,
                records,
                handoff,
                site,
            )
            self.assertEqual(
                job["input_artifact"]["sha256"],
                expected_registered_hashes()["input_hash"],
            )
            self.assertEqual(job["output_contract"]["maximum_bytes"], 16)
            self.assertEqual(job["work_trace_contract"]["expected_iterations"], 2)
            self.assertEqual(
                sorted(
                    row["statement_role"]
                    for row in job["artifact_closure"]["files"]
                    if row["statement_role"] is not None
                ),
                ["host_executable", "producer_executable", "source_tree"],
            )

    def test_leaf_trace_replays_same_directed_arithmetic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            invocation = args(Path(temporary), "mpfr-shards")
            indices = range(2)
            with measured_worker_test_scope(invocation), mock.patch.object(
                workload,
                "_run_group",
                side_effect=(
                    [fake_receipt(1, index) for index in indices],
                    [fake_receipt(2, index) for index in indices],
                ),
            ) as replay, mock.patch.object(
                workload, "leaf_indices_for_group", return_value=indices
            ), mock.patch.object(workload, "validate_receipt"):
                workload.run(invocation)
                workload.verify_trace(invocation)
            self.assertEqual(replay.call_count, 2)
            self.assertNotEqual(invocation.output.read_bytes(), b"true")
            trace = json.loads(invocation.trace.read_bytes())
            self.assertEqual(trace["iteration_count"], 2)

    def test_terminal_trace_remerges_every_fixed_plan_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            invocation = args(Path(temporary), "merge-and-verify")
            report = {
                "all_fixed_plan_receipts_present": True,
                "final_state": [3_389_047_618],
                "kind": workload.REPORT_KIND,
                "leaf_count": LEAF_COUNT,
                "plan_sha256": PLAN_SHA256,
                "root_state": [0],
                "schema_version": 1,
            }
            with measured_worker_test_scope(invocation), mock.patch.object(
                workload, "_merge_handoff", side_effect=(report, report)
            ) as merge:
                workload.run(invocation)
                workload.verify_trace(invocation)
            self.assertEqual(merge.call_count, 2)
            self.assertEqual(invocation.output.read_bytes(), b"true")
            trace = json.loads(invocation.trace.read_bytes())
            self.assertEqual(trace["iteration_count"], 2)
            self.assertEqual(set(trace), workload.TRACE_FIELDS)
            extracted = Path(temporary) / "candidate-export"
            workload._extract_export(
                invocation.work / workload.RETAINED_ARCHIVE,
                extracted,
                "merge-and-verify",
                0,
            )
            self.assertEqual(
                workload._candidate_identity(extracted)["status"],
                "arithmetic-chain-only-not-semantic-closure",
            )

    def test_terminal_merge_restores_strided_groups_to_exact_leaf_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff_root = root / "expanded"
            handoff_root.mkdir()
            runner = write_bytes(root / "runner", b"runner", 0o500)
            import hashlib

            runner_sha = hashlib.sha256(b"runner").hexdigest()
            entries = [
                {
                    "path": f"exports/{index}.tar",
                    "shard_index": index,
                }
                for index in range(2)
            ]
            verification = SimpleNamespace(
                final_state=(3_389_047_618,),
                incoming_states=((0,), (1,), (2,), (3,)),
                plan_sha256=PLAN_SHA256,
                root_state=(0,),
                to_dict=lambda: {
                    "leaf_count": 4,
                    "plan_sha256": PLAN_SHA256,
                },
            )

            def indices(group_index: int) -> range:
                return range(group_index, 4, 2)

            def receipt(_expanded: Path, leaf_index: int) -> dict[str, object]:
                return {
                    "runner_executable_sha256": runner_sha,
                    "shard_index": leaf_index,
                }

            with mock.patch.object(
                workload,
                "_handoff",
                return_value=({"entries": entries}, handoff_root),
            ), mock.patch.object(workload, "_extract_export"), mock.patch.object(
                workload, "_load_leaf_receipt", side_effect=receipt
            ), mock.patch.object(
                workload, "leaf_indices_for_group", side_effect=indices
            ), mock.patch.object(workload, "LEAF_COUNT", 4), mock.patch.object(
                workload, "verify_receipts", return_value=verification
            ) as verify:
                report = workload._merge_handoff(
                    root / "handoff.tar", runner, root / "scratch"
                )
            receipts = verify.call_args.args[0]
            self.assertEqual(
                [item["shard_index"] for item in receipts], [0, 1, 2, 3]
            )
            self.assertTrue(report["all_fixed_plan_receipts_present"])

    def test_real_handoff_archive_allows_directory_plus_every_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "handoff-root"
            entries = []
            import hashlib

            for index in range(2):
                relative = f"exports/{index:05d}.tar"
                raw = f"export-{index}".encode("ascii")
                write_bytes(source / relative, raw)
                entries.append(
                    {
                        "group_id": "helfgott-prop-12-2-4-mpfr-v1::mpfr-shards",
                        "path": relative,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "shard_index": index,
                        "size_bytes": len(raw),
                    }
                )
            write_bytes(
                source / "handoff.json",
                workload.canonical_json_bytes(
                    {
                        "entries": entries,
                        "kind": workload.HANDOFF_KIND,
                        "phase": "merge-and-verify",
                        "schema_version": 1,
                        "shard_index": 0,
                    }
                ),
            )
            archive = root / "handoff.tar"
            workload.create_archive(source, archive)
            with mock.patch.object(workload, "WORKER_GROUP_COUNT", 2):
                value, expanded = workload._handoff(archive, root / "expanded")
            self.assertEqual(len(value["entries"]), 2)
            self.assertTrue((expanded / "exports/00001.tar").is_file())


class AzureCPUProp1224SourceClosureTests(unittest.TestCase):
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
                    str(package / "tools/tg_prop1224_azure_measured_workload.py"),
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
