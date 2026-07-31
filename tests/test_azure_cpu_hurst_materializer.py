# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None

from attestation.measured_run_archive import create_archive
from tg_verifier import azure_cpu_hurst_materializer as materializer
from tg_verifier.azure_cpu_hurst_workload_factory import (
    CAMPAIGN_ID,
    PHASE_COMMANDS,
    PHASE_COUNTS,
    PHASE_DEPENDENCIES,
    REGISTERED_INPUT,
    SOURCE_PATHS,
    expected_registered_hashes,
    factory_for_portfolio_group,
    make_factory,
    source_reviewed_materializer_available,
)
from tests.azure_measured_worker_test_scope import measured_worker_test_scope
from tg_verifier.azure_cpu_portfolio_materializer import (
    PROFILE_PATHS,
    _artifact_record,
)
from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.hurst_candidate_artifact import (
    HurstCandidateArtifactError,
    HurstCandidateBlock,
    HurstCandidateCertificate,
    HurstCandidateGuard,
    HurstCandidateState,
    ZERO_STATE,
    encode_candidate,
)

import trusted_compute_receipt as receipt_issuer


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-cpu-hurst-portfolio-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-cpu-hurst-portfolio-materialization.schema.json"


def load_workload_module():
    specification = importlib.util.spec_from_file_location(
        "gpu_prover_hurst_azure_measured_workload",
        ROOT / "tools/tg_hurst_azure_measured_workload.py",
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
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


def runtime_identity(seed: str = "11") -> dict[str, object]:
    return {
        "runner_sha256": seed * 32,
        "runner_size_bytes": 101,
        "source_sha256": "22" * 32,
        "source_size_bytes": 202,
        "upstream_manifest_sha256": "33" * 32,
        "upstream_manifest_size_bytes": 303,
    }


def group(phase: str, *, semantic: object = None) -> dict[str, object]:
    factory = make_factory(phase, 0)
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PHASE_COMMANDS[phase]),
        "depends_on": list(PHASE_DEPENDENCIES[phase]),
        "group_id": factory.group_id,
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "mertens-hurst",
        "phase_id": phase,
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": semantic,
        "shard_count": PHASE_COUNTS[phase],
        "terminal": factory.terminal,
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


class AzureCPUHurstMaterializerTests(unittest.TestCase):
    def test_candidate_sidecar_is_manifested_and_bound_into_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            delta = HurstCandidateState(-1, 2, -3, 4)
            raw = encode_candidate(
                HurstCandidateCertificate(
                    1,
                    10_000_000_000_000_001,
                    ZERO_STATE,
                    delta,
                    (
                        HurstCandidateBlock(
                            1,
                            10_000_000_000_000_001,
                            delta,
                            HurstCandidateGuard(ZERO_STATE, ZERO_STATE),
                        ),
                    ),
                )
            )
            candidate = workload._write_candidate_after_replay(root / "work", raw)
            arguments = SimpleNamespace(
                algorithm_id="test.algorithm",
                challenge="aa" * 32,
                group_index=0,
                job_binding="bb" * 32,
                phase="semantic-replay",
                trace=root / "trace.json",
            )
            workload._write_trace(
                arguments,
                input_sha256="cc" * 32,
                identity=runtime_identity(),
                retained_sha256="dd" * 32,
                retained_tree_sha256="ee" * 32,
                result_sha256="ff" * 32,
                candidate=candidate,
            )
            trace = json.loads(arguments.trace.read_bytes())
            self.assertEqual(set(trace), workload.TRACE_FIELDS)
            bound_trace = trace["trace_sha256"]
            workload._write_trace(
                SimpleNamespace(
                    algorithm_id="test.algorithm",
                    challenge="aa" * 32,
                    group_index=0,
                    job_binding="bb" * 32,
                    phase="semantic-replay",
                    trace=root / "trace-without-candidate.json",
                ),
                input_sha256="cc" * 32,
                identity=runtime_identity(),
                retained_sha256="dd" * 32,
                retained_tree_sha256="ee" * 32,
                result_sha256="ff" * 32,
                candidate=None,
            )
            self.assertNotEqual(
                bound_trace,
                json.loads(
                    (root / "trace-without-candidate.json").read_bytes()
                )["trace_sha256"],
            )
            self.assertEqual(candidate, workload._candidate_identity(root / "work"))
            artifact = root / "work" / workload.CANDIDATE_ARTIFACT_PATH
            artifact.chmod(0o600)
            artifact.write_bytes(artifact.read_bytes() + b"\0")
            with self.assertRaises(HurstCandidateArtifactError):
                workload._candidate_identity(root / "work")

    def test_registered_identity_is_exact_and_terminal_only(self) -> None:
        self.assertEqual(
            expected_registered_hashes(),
            {
                "algorithm_hash": "d5fa24d80d95216208ff8e8bbacb42ec181966b40e6a577dae26d585c09df5aa",
                "algorithm_id": "sparkinterval.ternary-goldbach.hurst-shared-four-residual.v2",
                "domain_hash": "fbbe3abc2d158bebb2a9f9b06c0379c3fd9eff168c86c9900a7997172ec91f0a",
                "input_hash": "84cad6505119c2498b1213c73c13e379ebcc0e8bbd2d445d1539d45ec06fc5b7",
                "output_hash": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
                "parameters_hash": "78f8cf9ecdcac464c1711f877c57e31518dd66d6070882fb6de1d2a199068d1d",
            },
        )
        self.assertEqual(
            hashlib.sha256(REGISTERED_INPUT).hexdigest(),
            expected_registered_hashes()["input_hash"],
        )
        for phase, count in PHASE_COUNTS.items():
            for index in range(count):
                factory = factory_for_portfolio_group(group(phase), index)
                self.assertIsNotNone(factory)
                assert factory is not None
                self.assertEqual(factory.terminal, phase == "semantic-replay")
                self.assertEqual(
                    factory.registered_invocation,
                    "hurstSharedFourResidualProductionV2"
                    if factory.terminal
                    else None,
                )
                for argv in (factory.command_argv, factory.trace_verifier_argv):
                    self.assertIn("artifacts/tg_hurst_residual_shard", argv)
                    self.assertIn("source/reference/tg_hurst_residual_shard.cpp", argv)
                    self.assertIn(
                        "source/specifications/HURST_MERTENS_UPSTREAM.json", argv
                    )

    def test_factory_closes_all_six_groups_and_dependencies(self) -> None:
        expected = {
            "initialize": (),
            "summary-shards": ((f"{CAMPAIGN_ID}::initialize", 0),),
            "reduce-summaries": tuple(
                (f"{CAMPAIGN_ID}::summary-shards", index)
                for index in range(320)
            ),
            "verify-shards": ((f"{CAMPAIGN_ID}::reduce-summaries", 0),),
            "finalize-four-residual-certificate": (
                (f"{CAMPAIGN_ID}::reduce-summaries", 0),
                *((f"{CAMPAIGN_ID}::verify-shards", index) for index in range(320)),
            ),
            "semantic-replay": (
                (f"{CAMPAIGN_ID}::finalize-four-residual-certificate", 0),
            ),
        }
        for phase in PHASE_COUNTS:
            exact = group(phase)
            self.assertTrue(source_reviewed_materializer_available(exact))
            self.assertEqual(
                materializer._expected_predecessors(make_factory(phase, 0)),
                expected[phase],
            )
            changed = copy.deepcopy(exact)
            changed["command_template"].append("--caller-shell")
            self.assertFalse(source_reviewed_materializer_available(changed))
            changed = copy.deepcopy(exact)
            changed["depends_on"] = []
            if PHASE_DEPENDENCIES[phase]:
                self.assertFalse(source_reviewed_materializer_available(changed))
        terminal = group(
            "semantic-replay",
            semantic={
                "registered_invocation": "hurstSharedFourResidualProductionV2"
            },
        )
        self.assertTrue(source_reviewed_materializer_available(terminal))
        terminal["semantic_binding"]["registered_invocation"] = "attacker"
        self.assertFalse(source_reviewed_materializer_available(terminal))

    def test_schemas_cli_and_commands_expose_no_caller_executable(self) -> None:
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
                str(ROOT / "tools/tg_azure_cpu_hurst_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("materialize", result.stdout)
        source = (ROOT / "tools/tg_hurst_azure_measured_workload.py").read_text(
            encoding="utf-8"
        ).lower()
        for forbidden in ("shell=true", "os.system", "popen("):
            self.assertNotIn(forbidden, source)

    def test_retained_export_and_operational_result_bind_binary_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "export"
            write_bytes(export / "payload/summary/receipt-00000000.json", b"{}\n")
            identity = runtime_identity()
            manifest = workload._write_export_manifest(
                export, "summary-shards", 0, identity
            )
            archive = root / "export.tar"
            create_archive(export, archive)
            materializer._validate_retained_export(
                archive,
                phase="summary-shards",
                shard_index=0,
                tree_sha256=manifest["tree_sha256"],
                identity=identity,
            )
            changed = runtime_identity("44")
            with self.assertRaisesRegex(
                materializer.HurstMaterializerError, "tree replay"
            ):
                materializer._validate_retained_export(
                    archive,
                    phase="summary-shards",
                    shard_index=0,
                    tree_sha256=manifest["tree_sha256"],
                    identity=changed,
                )
            result = {
                "group_index": 0,
                **identity,
                "kind": materializer.OPERATIONAL_RESULT_KIND,
                "phase": "summary-shards",
                "retained_export_sha256": pin(archive)["sha256"],
                "retained_export_size_bytes": pin(archive)["size_bytes"],
                "retained_tree_sha256": manifest["tree_sha256"],
                "schema_version": 1,
            }
            raw = canonical_json_bytes(result).decode("utf-8")
            receipt = {
                "claim": {
                    "output_hash": hashlib.sha256(raw.encode()).hexdigest(),
                    "result": raw,
                }
            }
            self.assertEqual(
                materializer._operational_result(receipt, "summary-shards", 0),
                result,
            )
            artifact_root = root / "artifact-root"
            artifact_root.mkdir()
            runtime = {
                "host_executable_sha256": "66" * 32,
                "identity": identity,
                "source_tree_sha256": "77" * 32,
            }
            predecessor = {
                "group_id": f"{CAMPAIGN_ID}::summary-shards",
                "host_executable_sha256": runtime["host_executable_sha256"],
                "identity": changed,
                "phase": "summary-shards",
                "receipt_sha256": "88" * 32,
                "shard_index": 0,
                "source_path": archive,
                "source_tree_sha256": runtime["source_tree_sha256"],
                "tree_sha256": manifest["tree_sha256"],
            }
            with self.assertRaisesRegex(
                materializer.HurstMaterializerError, "source or binary"
            ):
                materializer._create_handoff(
                    artifact_root,
                    make_factory("reduce-summaries", 0),
                    [predecessor],
                    runtime,
                )

    def test_initialize_phase_and_independent_trace_replay_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = write_bytes(
                root / "artifacts/runner", b"#!/bin/sh\nexit 2\n", 0o500
            )
            source = write_bytes(
                root / "source/reference/tg_hurst_residual_shard.cpp",
                (ROOT / "reference/tg_hurst_residual_shard.cpp").read_bytes(),
            )
            upstream = write_bytes(
                root / "source/specifications/HURST_MERTENS_UPSTREAM.json",
                (ROOT / "specifications/HURST_MERTENS_UPSTREAM.json").read_bytes(),
            )
            factory = make_factory("initialize", 0)
            invocation = write_bytes(root / "input/phase.json", factory.input_bytes)
            handoff_root = root / "handoff-root"
            write_bytes(
                handoff_root / "handoff.json",
                canonical_json_bytes(
                    {
                        "entries": [],
                        "group_index": 0,
                        "kind": workload.HANDOFF_KIND,
                        "phase": "initialize",
                        "schema_version": 1,
                    }
                ),
            )
            handoff = root / "input/handoff.tar"
            create_archive(handoff_root, handoff)
            old = Path.cwd()
            os.chdir(root)
            try:
                arguments = SimpleNamespace(
                    algorithm_id=factory.algorithm_id,
                    challenge="aa" * 32,
                    group_index=0,
                    handoff=handoff.relative_to(root),
                    input=invocation.relative_to(root),
                    job_binding="bb" * 32,
                    output=Path("output/result.json"),
                    phase="initialize",
                    runner=runner.relative_to(root),
                    runner_source=source.relative_to(root),
                    trace=Path("output/trace.json"),
                    upstream_manifest=upstream.relative_to(root),
                    work=Path("work/hurst"),
                )
                with measured_worker_test_scope(arguments):
                    workload.run(arguments)
                    workload.verify_trace(arguments)
                self.assertTrue(Path("work/hurst/retained-export.tar").is_file())
                source.chmod(0o600)
                source.write_bytes(source.read_bytes() + b"// changed\n")
                with self.assertRaises(workload.HurstMeasuredWorkloadError):
                    with measured_worker_test_scope(arguments):
                        workload.verify_trace(arguments)
            finally:
                os.chdir(old)

    def test_job_specs_bind_operational_and_terminal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
            for phase in ("initialize", "semantic-replay"):
                artifact_root = root / phase
                host = write_bytes(
                    artifact_root / "artifacts/python3", b"python", 0o500
                )
                producer = write_bytes(
                    artifact_root / "artifacts/tg_hurst_residual_shard",
                    b"runner",
                    0o500,
                )
                source_tree = write_bytes(
                    artifact_root / "source/source-closure.json", b"{}\n"
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
                        role="static_hurst_four_residual_shard_producer",
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
                ]
                handoff = write_bytes(
                    artifact_root / "input/hurst-phase-handoff.tar", b"handoff"
                )
                factory = make_factory(phase, 0)
                job = materializer._job(
                    source_context(), factory, artifact_root, records, handoff, site
                )
                self.assertEqual(job["command"]["argv"], list(factory.command_argv))
                self.assertEqual(
                    job["work_trace_contract"]["verifier_argv"],
                    list(factory.trace_verifier_argv),
                )
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
                build_artifacts = [
                    {"role": row["statement_role"], "sha256": row["sha256"]}
                    for row in job["artifact_closure"]["files"]
                    if row["statement_role"] is not None
                ]
                build_artifacts.append(
                    {"role": "execution_manifest", "sha256": "11" * 32}
                )
                statement = {"build_artifacts": build_artifacts}
                self.assertEqual(
                    receipt_issuer._artifact_role(statement, "source_tree"),
                    pin(source_tree)["sha256"],
                )
                self.assertEqual(
                    receipt_issuer._artifact_role(statement, "host_executable"),
                    pin(host)["sha256"],
                )
                self.assertEqual(
                    receipt_issuer._device_hash(statement, "azure_sevsnp_cpu"),
                    receipt_issuer.NOT_APPLICABLE_DIGEST,
                )


class AzureCPUHurstSourceClosureTests(unittest.TestCase):
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
                    str(package / "tools/tg_hurst_azure_measured_workload.py"),
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
