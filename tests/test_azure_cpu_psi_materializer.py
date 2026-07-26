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

try:
    import jsonschema
except ImportError:
    jsonschema = None

from attestation.measured_run_archive import create_archive, extract_archive
from tg_verifier import azure_cpu_psi_materializer as materializer
from tg_verifier.azure_cpu_portfolio_materializer import (
    PROFILE_PATHS,
    _artifact_record,
)
from tg_verifier.azure_cpu_psi_workload_factory import (
    CAMPAIGN_ID,
    PHASE_COMMANDS,
    PHASE_COUNTS,
    PHASE_DEPENDENCIES,
    REGISTERED_ALGORITHM_SHA256,
    REGISTERED_INPUT,
    REGISTERED_OUTPUT_SHA256,
    SOURCE_PATHS,
    expected_registered_hashes,
    factory_for_portfolio_group,
    make_factory,
    source_reviewed_materializer_available,
)
from tg_verifier.campaign_io import canonical_json_bytes

import trusted_compute_receipt as receipt_issuer


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-cpu-psi-portfolio-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-cpu-psi-portfolio-materialization.schema.json"


def load_workload_module():
    spec = importlib.util.spec_from_file_location(
        "gpu_prover_psi_azure_measured_workload",
        ROOT / "tools/tg_psi_azure_measured_workload.py",
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


def group(phase: str, *, semantic: object = None) -> dict[str, object]:
    factory = make_factory(phase, 0)
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PHASE_COMMANDS[phase]),
        "depends_on": list(PHASE_DEPENDENCIES[phase]),
        "group_id": factory.group_id,
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "ch25-psi-1e13",
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


class AzureCPUPsiMaterializerTests(unittest.TestCase):
    def test_registered_identity_is_exact_and_terminal_only(self) -> None:
        expected = expected_registered_hashes()
        self.assertEqual(
            expected,
            {
                "algorithm_hash": "b16368f84ca70c2a3e7b9b9814c7e098e79c0c3bb137a51b85851cfd526753b0",
                "algorithm_id": "sparkinterval.ternary-goldbach.ch25-psi-lemma-9-2.v1",
                "domain_hash": "2a19d38cb3c36f9371c741701b7046b6c99dfba94f12185bd8625fad2e8f921f",
                "input_hash": "35368234a47ea3acdac04c55453f07cc5deb051fdf2238e865d683b17b11d3d8",
                "output_hash": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
                "parameters_hash": "ddc632e84956e223e9df686d02aab167b52cd902dfcedf6ae3a7ccccdd0f6637",
            },
        )
        self.assertEqual(REGISTERED_ALGORITHM_SHA256, expected["algorithm_hash"])
        self.assertEqual(hashlib.sha256(REGISTERED_INPUT).hexdigest(), expected["input_hash"])
        self.assertEqual(REGISTERED_OUTPUT_SHA256, expected["output_hash"])
        for phase, count in PHASE_COUNTS.items():
            for index in range(count):
                factory = factory_for_portfolio_group(group(phase), index)
                self.assertIsNotNone(factory)
                assert factory is not None
                self.assertEqual(factory.terminal, phase == "semantic-replay")
                self.assertEqual(
                    factory.registered_invocation,
                    "ch25PsiLemma92ProductionV1" if factory.terminal else None,
                )

    def test_factory_fails_closed_on_command_dependency_or_semantic_drift(self) -> None:
        for phase in PHASE_COUNTS:
            exact = group(phase)
            self.assertTrue(source_reviewed_materializer_available(exact))
            changed = copy.deepcopy(exact)
            changed["command_template"].append("--caller-shell")
            self.assertFalse(source_reviewed_materializer_available(changed))
            changed = copy.deepcopy(exact)
            changed["depends_on"] = []
            if PHASE_DEPENDENCIES[phase]:
                self.assertFalse(source_reviewed_materializer_available(changed))
        terminal = group(
            "semantic-replay",
            semantic={"registered_invocation": "ch25PsiLemma92ProductionV1"},
        )
        self.assertTrue(source_reviewed_materializer_available(terminal))
        terminal["semantic_binding"]["registered_invocation"] = "attacker"
        self.assertFalse(source_reviewed_materializer_available(terminal))

    def test_schemas_cli_and_factory_expose_no_caller_executable(self) -> None:
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
                str(ROOT / "tools/tg_azure_cpu_psi_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("materialize", result.stdout)
        source = (ROOT / "tools/tg_psi_azure_measured_workload.py").read_text(
            encoding="utf-8"
        ).lower()
        for forbidden in ("shell=true", "os.system", "popen("):
            self.assertNotIn(forbidden, source)
        for phase in PHASE_COUNTS:
            factory = make_factory(phase, 0)
            self.assertEqual(factory.command_argv[:2], ("artifacts/python3", "-I"))

    def test_retained_export_is_cross_checked_by_materializer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "export"
            write_bytes(export / "payload/summary/receipt-00000000.json", b"{}\n")
            manifest = workload._write_export_manifest(export, "summary-shards", 0)
            archive = root / "export.tar"
            create_archive(export, archive)
            materializer._validate_retained_export(
                archive,
                phase="summary-shards",
                shard_index=0,
                tree_sha256=manifest["tree_sha256"],
            )
            leaf = export / "payload/summary/receipt-00000000.json"
            leaf.chmod(0o600)
            leaf.write_bytes(b"tampered\n")
            archive.unlink()
            create_archive(export, archive)
            with self.assertRaises(materializer.PsiMaterializerError):
                materializer._validate_retained_export(
                    archive,
                    phase="summary-shards",
                    shard_index=0,
                    tree_sha256=manifest["tree_sha256"],
                )

    def test_job_specs_bind_closed_operational_and_terminal_paths(self) -> None:
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
                host = write_bytes(artifact_root / "artifacts/python3", b"python", 0o500)
                producer = write_bytes(
                    artifact_root / "artifacts/tg_psi_residual_shard", b"runner", 0o500
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
                        role="static_psi_prime_power_shard_producer",
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
                    artifact_root / "input/psi-phase-handoff.tar", b"handoff"
                )
                factory = make_factory(phase, 0)
                job = materializer._job(
                    source_context(), factory, artifact_root, records, handoff, site
                )
                self.assertEqual(job["command"]["argv"], list(factory.command_argv))
                self.assertEqual(job["algorithm"]["definition_sha256"], hashlib.sha256(
                    factory.algorithm_definition.encode("utf-8")
                ).hexdigest())
                self.assertEqual(
                    job["input_artifact"]["sha256"],
                    expected_registered_hashes()["input_hash"]
                    if factory.terminal
                    else pin(handoff)["sha256"],
                )
                self.assertEqual(
                    len([
                        row for row in job["artifact_closure"]["files"]
                        if row["statement_role"] == "source_tree"
                    ]),
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
                    next(
                        row["sha256"]
                        for row in job["artifact_closure"]["files"]
                        if row["statement_role"] == "source_tree"
                    ),
                )
                self.assertEqual(
                    receipt_issuer._artifact_role(statement, "host_executable"),
                    pin(host)["sha256"],
                )
                self.assertEqual(
                    receipt_issuer._device_hash(statement, "azure_sevsnp_cpu"),
                    receipt_issuer.NOT_APPLICABLE_DIGEST,
                )


class AzureCPUPsiSourceClosureTests(unittest.TestCase):
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
                    str(package / "tools/tg_psi_azure_measured_workload.py"),
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
