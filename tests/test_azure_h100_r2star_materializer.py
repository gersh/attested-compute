# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tg_verifier.azure_cpu_portfolio_materializer import _artifact_record
from tg_verifier.azure_h100_r2star_materializer import (
    BUILD_FIELDS,
    SOURCE_CLOSURE_KIND,
    _job,
)
from tg_verifier.azure_h100_r2star_workload_factory import (
    CAMPAIGN_ID,
    EXPECTED_IDENTITY,
    GROUP_ID,
    PHASE_DEPENDENCIES,
    PHASE_ID,
    PORTFOLIO_ARGV,
    REGISTERED_ALGORITHM_ID,
    REGISTERED_INPUT,
    REGISTERED_INVOCATION,
    SOURCE_PATHS,
    TRACE_DEFINITION,
    factory_for_portfolio_group,
    make_factory,
    registered_identity,
    source_reviewed_materializer_available,
)
from tests.azure_measured_worker_test_scope import measured_worker_test_scope
from tg_verifier.campaign_io import canonical_json_bytes
from tools.generate_trusted_compute_lean import registered_invocation_expected
from tools import tg_r2star_azure_measured_workload as workload


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-h100-r2star-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-h100-r2star-materialization.schema.json"
SITE_EXAMPLE = (
    ROOT
    / "examples/trusted-compute/azure_h100_r2star_materializer_site.redacted.json"
)


def group() -> dict[str, object]:
    return {
        "backend_class": "h100_cuda",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PORTFOLIO_ARGV),
        "depends_on": list(PHASE_DEPENDENCIES),
        "group_id": GROUP_ID,
        "operator_adapter": "azure/h100_production_orchestrator.py",
        "owner_atom_id": CAMPAIGN_ID,
        "phase_id": PHASE_ID,
        "receipt_backend": "azure_ncc40ads_h100_v5",
        "semantic_binding": None,
        "shard_count": 1,
        "terminal": True,
    }


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def source_fixture(root: Path) -> None:
    python = root / workload.FIXED_PYTHON
    python.parent.mkdir(parents=True)
    shutil.copyfile(Path(sys.executable).resolve(), python)
    python.chmod(0o700)
    python_sha = hashlib.sha256(python.read_bytes()).hexdigest()
    runner = root / workload.FIXED_RUNNER
    runner.write_bytes(b"reviewed-r2star-runner")
    runner.chmod(0o700)
    runner_sha = hashlib.sha256(runner.read_bytes()).hexdigest()
    arithmetic_replayer = root / workload.FIXED_ARITHMETIC_REPLAYER
    arithmetic_replayer.write_bytes(b"reviewed-r2star-arithmetic-replayer")
    arithmetic_replayer.chmod(0o700)
    arithmetic_replayer_sha = hashlib.sha256(
        arithmetic_replayer.read_bytes()
    ).hexdigest()
    manifest = {
        "build": {},
        "files": [],
        "kind": SOURCE_CLOSURE_KIND,
        "runtime": {
            "arithmetic_replayer": {
                "path": workload.FIXED_ARITHMETIC_REPLAYER.as_posix(),
                "sha256": arithmetic_replayer_sha,
                "size_bytes": arithmetic_replayer.stat().st_size,
            },
            "dynamic_runtime_boundary": "test immutable image",
            "python": {
                "path": workload.FIXED_PYTHON.as_posix(),
                "sha256": python_sha,
                "size_bytes": python.stat().st_size,
            },
            "runner": {
                "path": workload.FIXED_RUNNER.as_posix(),
                "sha256": runner_sha,
                "size_bytes": runner.stat().st_size,
            },
        },
        "schema_version": 1,
    }
    path = root / workload.FIXED_SOURCE_CLOSURE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(manifest))


def args(root: Path) -> argparse.Namespace:
    input_path = root / "input/range.json"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_bytes(REGISTERED_INPUT)
    return argparse.Namespace(
        algorithm_id=REGISTERED_ALGORITHM_ID,
        challenge="2" * 64,
        job_binding="3" * 64,
        input=Path("input/range.json"),
        output=Path("output/result.txt"),
        trace=Path("output/work-trace.json"),
    )


class R2StarH100FactoryTests(unittest.TestCase):
    def test_exact_terminal_factory_and_lean_identity(self) -> None:
        exact = group()
        self.assertTrue(source_reviewed_materializer_available(exact))
        factory = factory_for_portfolio_group(exact, 0)
        self.assertIsNotNone(factory)
        assert factory is not None
        self.assertTrue(factory.terminal)
        self.assertEqual(factory.registered_invocation, REGISTERED_INVOCATION)
        self.assertEqual(registered_identity(), EXPECTED_IDENTITY)
        generated = registered_invocation_expected(REGISTERED_INVOCATION)
        for field, value in EXPECTED_IDENTITY.items():
            self.assertEqual(generated[field], value)
        self.assertNotIn("--runner", factory.command_argv)
        self.assertNotIn("--output-dir", factory.command_argv)
        self.assertNotIn("resume", " ".join(factory.command_argv).lower())
        self.assertEqual(factory.output_maximum_bytes, 4)
        self.assertIn(
            "reference/tg_r2star_arithmetic_replay.cpp", SOURCE_PATHS
        )
        self.assertIn(
            "gpu/include/sparkinterval/measured_worker_scope.hpp",
            SOURCE_PATHS,
        )
        self.assertIn(
            "gpu/include/sparkinterval/tg_r2star_replay_segments.hpp",
            SOURCE_PATHS,
        )
        self.assertIn("cpu-row-arithmetic-replay", TRACE_DEFINITION)
        self.assertIn("input-python-runner-arithmetic-replayer", TRACE_DEFINITION)
        with self.assertRaises(ValueError):
            make_factory(1)

        exact["semantic_binding"] = {
            "registered_invocation": REGISTERED_INVOCATION,
        }
        self.assertTrue(source_reviewed_materializer_available(exact))

    def test_predicate_rejects_any_portfolio_shape_drift(self) -> None:
        for field, value in (
            ("terminal", False),
            ("shard_count", 2),
            ("semantic_binding", {"unsafe": True}),
            ("depends_on", ["unreviewed::state"]),
            ("receipt_backend", "local_unattested"),
        ):
            changed = dict(group())
            changed[field] = value
            self.assertFalse(source_reviewed_materializer_available(changed), field)
        changed = dict(group())
        changed["command_template"] = [*PORTFOLIO_ARGV, "--unsafe"]
        self.assertFalse(source_reviewed_materializer_available(changed))


class R2StarMeasuredWorkerTests(unittest.TestCase):
    def test_runtime_and_artifact_path_aliases_fail_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_fixture(root)
            arguments = args(root)
            arguments.output = workload.FIXED_RUNNER
            with working_directory(root), measured_worker_test_scope(
                arguments, backend="azure_ncc40ads_h100_v5"
            ), mock.patch.object(
                workload, "run_campaign"
            ) as execute:
                with self.assertRaisesRegex(
                    workload.R2StarAzureMeasuredWorkloadError,
                    "overlaps a fixed runtime",
                ):
                    workload.run(arguments)
            execute.assert_not_called()
            self.assertEqual(
                (root / workload.FIXED_RUNNER).read_bytes(),
                b"reviewed-r2star-runner",
            )

    def test_python_runtime_pin_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_fixture(root)
            manifest_path = root / workload.FIXED_SOURCE_CLOSURE
            manifest = json.loads(manifest_path.read_bytes())
            manifest["runtime"]["python"]["sha256"] = "0" * 64
            manifest_path.write_bytes(canonical_json_bytes(manifest))
            with working_directory(root):
                with self.assertRaisesRegex(
                    workload.R2StarAzureMeasuredWorkloadError,
                    "Python runtime differs",
                ):
                    workload._source_identity()

    def test_nonexecutable_replayer_fails_before_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_fixture(root)
            (root / workload.FIXED_ARITHMETIC_REPLAYER).chmod(0o600)
            arguments = args(root)
            with working_directory(root), measured_worker_test_scope(
                arguments, backend="azure_ncc40ads_h100_v5"
            ), mock.patch.object(
                workload, "run_campaign"
            ) as execute:
                with self.assertRaisesRegex(
                    workload.R2StarAzureMeasuredWorkloadError,
                    "must be one executable",
                ):
                    workload.run(arguments)
            execute.assert_not_called()

    def test_prepopulated_workspace_is_rejected_before_any_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_fixture(root)
            arguments = args(root)
            (root / workload.FIXED_WORK).mkdir(parents=True)
            with working_directory(root), measured_worker_test_scope(
                arguments, backend="azure_ncc40ads_h100_v5"
            ), mock.patch.object(
                workload, "run_campaign"
            ) as execute:
                with self.assertRaisesRegex(
                    workload.R2StarAzureMeasuredWorkloadError,
                    "resume/import is forbidden",
                ):
                    workload.run(arguments)
            execute.assert_not_called()
            self.assertTrue((root / workload.FIXED_WORK).is_dir())

    def test_fresh_export_roundtrip_and_archive_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_fixture(root)
            arguments = args(root)
            arithmetic_replayer_sha256 = hashlib.sha256(
                (root / workload.FIXED_ARITHMETIC_REPLAYER).read_bytes()
            ).hexdigest()
            result = argparse.Namespace(
                endpoint=21_000_000_000,
                completed_upper=21_000_000_000,
                complete=True,
                receipts=21_000,
                final_record_hash="4" * 64,
                minimum_squared_slack=1,
                minimum_slack_index=3,
                independent_rows_replayed=True,
                arithmetic_replayer_sha256=arithmetic_replayer_sha256,
            )

            def fake_run(**keywords):
                campaign = keywords["output_directory"]
                campaign.mkdir(parents=True)
                (campaign / "campaign-config.json").write_bytes(b"{}\n")
                (campaign / "campaign-manifest.json").write_bytes(b"{}\n")
                (campaign / "receipt-00000000.json").write_bytes(b"{}\n")
                return result

            def fake_registered(campaign, output, **_keywords):
                del campaign
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"true")
                return result, {}

            with working_directory(root), measured_worker_test_scope(
                arguments, backend="azure_ncc40ads_h100_v5"
            ), mock.patch.object(
                workload, "run_campaign", side_effect=fake_run
            ), mock.patch.object(
                workload, "write_registered_result", side_effect=fake_registered
            ), mock.patch.object(
                workload, "verify_campaign_arithmetic", return_value=result
            ):
                workload.run(arguments)
                self.assertEqual(arguments.output.read_bytes(), b"true")
                self.assertTrue(workload._archive_path().is_file())
                self.assertFalse((workload.FIXED_WORK / "retained").exists())
                workload.verify_trace(arguments)
                archive = workload._archive_path()
                archive.chmod(0o600)
                with archive.open("ab") as destination:
                    destination.write(b"tamper")
                with self.assertRaisesRegex(
                    workload.R2StarAzureMeasuredWorkloadError,
                    "trace differs",
                ):
                    workload.verify_trace(arguments)


class R2StarMaterializerSurfaceTests(unittest.TestCase):
    def test_schemas_cli_and_site_exclude_predecessor_state(self) -> None:
        for path in (SITE_SCHEMA, MANIFEST_SCHEMA):
            schema = json.loads(path.read_bytes())
            if jsonschema is not None:
                jsonschema.Draft202012Validator.check_schema(schema)
        if jsonschema is not None:
            jsonschema.validate(
                json.loads(SITE_EXAMPLE.read_bytes()),
                json.loads(SITE_SCHEMA.read_bytes()),
            )
        self.assertEqual(BUILD_FIELDS, {"boost_include_root", "host_cxx", "nvcc", "python"})
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/tg_azure_h100_r2star_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("export", result.stdout)

    def test_job_is_terminal_registered_and_has_one_gpu_binary_role(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)
            paths = {
                "python": artifact_root / "artifacts/python3",
                "runner": artifact_root / "artifacts/r2star-h100",
                "replayer": artifact_root / "artifacts/r2star-arithmetic-replay",
                "nvidia": artifact_root / "profiles/nvidia-gpu.rego",
                "source": artifact_root / "source/source-closure.json",
            }
            for path in paths.values():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(path.name.encode("ascii"))
            records = [
                _artifact_record(
                    paths["python"], artifact_root,
                    role="host", statement_role="host_executable", executable=True,
                ),
                _artifact_record(
                    paths["runner"], artifact_root,
                    role="runner", statement_role="gpu_executable", executable=True,
                ),
                _artifact_record(
                    paths["replayer"], artifact_root,
                    role="replayer", statement_role="checker_executable", executable=True,
                ),
                _artifact_record(
                    paths["nvidia"], artifact_root,
                    role="policy", statement_role="gpu_attestation_policy", executable=False,
                ),
                _artifact_record(
                    paths["source"], artifact_root,
                    role="source", statement_role="source_tree", executable=False,
                ),
            ]
            profiles = {
                "target": {
                    "path": "profiles/target.json",
                    "profile_id": "azure_ncc40ads_h100_v5",
                    "sha256": "5" * 64,
                },
                "trust": {
                    "path": "profiles/trust.json",
                    "profile_id": "azure_ncc_sevsnp_vtpm_nvidia_cc_attested",
                    "sha256": "6" * 64,
                },
            }
            runner_policy = {
                "path": "profiles/runner-policy.json",
                "policy_id": "production-runner",
                "sha256": "7" * 64,
            }
            site = {
                "template": {
                    "worker": {
                        "gpu_verifier": "/usr/bin/true",
                        "nras_url": "https://nras.attestation.nvidia.com",
                    }
                }
            }
            with mock.patch(
                "tg_verifier.azure_h100_r2star_materializer._profiles_and_runner",
                return_value=(profiles, runner_policy),
            ):
                job = _job(None, site, make_factory(0), artifact_root, records)
            self.assertEqual(job["algorithm"]["algorithm_id"], REGISTERED_ALGORITHM_ID)
            self.assertEqual(job["input_artifact"]["sha256"], EXPECTED_IDENTITY["input_hash"])
            self.assertEqual(job["output_contract"]["maximum_bytes"], 4)
            roles = [row["statement_role"] for row in records]
            self.assertEqual(roles.count("gpu_executable"), 1)
            self.assertEqual(roles.count("checker_executable"), 1)
            self.assertNotIn("--runner", job["command"]["argv"])


class R2StarH100SourceClosureTests(unittest.TestCase):
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
                    str(package / "tools/tg_r2star_azure_measured_workload.py"),
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
