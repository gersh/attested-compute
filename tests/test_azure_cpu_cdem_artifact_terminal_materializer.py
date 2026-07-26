# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import platform

try:
    import jsonschema
except ImportError:
    jsonschema = None

from attestation.measured_run_archive import create_archive
from azure.measured_runner import _elf_has_interp
from tg_verifier import (
    azure_cpu_cdem_artifact_terminal_materializer as materializer,
)
from tg_verifier.azure_cpu_cdem_artifact_terminal_workload_factory import (
    ALGORITHM_ID,
    CDEM_ARTIFACT_TERMINAL_FACTORY,
    INPUT_PATH,
    REPLAYER_PATH,
    TERMINAL_PATH,
)
from tg_verifier.azure_cpu_portfolio_materializer import PROFILE_PATHS
from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.cdem_abel_artifact import ARTIFACT_HEADER


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "schemas/azure-cpu-cdem-artifact-terminal-materializer-site.schema.json"
)
MANIFEST_SCHEMA = (
    ROOT
    / "schemas/azure-cpu-cdem-artifact-terminal-materialization.schema.json"
)
EXAMPLE = (
    ROOT
    / "examples/trusted-compute/"
    "azure_cpu_cdem_artifact_terminal_materializer_site.redacted.json"
)
SIGNED_TARGET = 324_880_457_633_740
ABSOLUTE_TARGET = 48_710_223_109_607_260_068_028


def _natural(value: int) -> bytes:
    return value.to_bytes(32, "little")


def _integer(value: int) -> bytes:
    return bytes((1 if value < 0 else 0,)) + _natural(abs(value))


def synthetic_production_shape_artifact() -> bytes:
    """A framing fixture only; the terminal test supplies the fake replayer."""

    output = bytearray(ARTIFACT_HEADER)
    output.extend(_natural(SIGNED_TARGET))
    output.extend(_natural(ABSOLUTE_TARGET))
    output.extend((1_000).to_bytes(4, "little"))
    for index in range(1_000):
        low = index * 5_000_000 + 1
        high = (index + 1) * 5_000_000
        output.extend(_natural(low))
        output.extend(_natural(high))
        output.extend(_integer(0))
        output.extend(_integer(112 if index == 999 else 0))
        output.extend(_integer(SIGNED_TARGET if index == 0 else 0))
        output.extend(_natural(ABSOLUTE_TARGET if index == 0 else 0))
    return bytes(output)


def _write(path: Path, raw: bytes, mode: int = 0o400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def _pin(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def source_context() -> SimpleNamespace:
    relative = (
        *CDEM_ARTIFACT_TERMINAL_FACTORY.source_paths,
        *PROFILE_PATHS.values(),
    )
    rows = []
    for item in relative:
        raw = (ROOT / item).read_bytes()
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


def certificate_archive(
    root: Path,
    *,
    artifact: bytes,
    artifact_sha256: str | None = None,
    statement_sha256: str = "a" * 64,
    bundle_sha256: str = "f" * 64,
    retained: list[dict[str, str]] | None = None,
) -> tuple[Path, dict, dict]:
    package = root / "certificate-package"
    bundle_root = package / "bundle-root"
    artifact_path = bundle_root / materializer.PRODUCER_ARTIFACT_PATH
    _write(artifact_path, artifact)
    if retained is None:
        retained = [
            {
                "path": materializer.PRODUCER_ARTIFACT_PATH,
                "sha256": artifact_sha256
                or hashlib.sha256(artifact).hexdigest(),
            }
        ]
    statement = {
        "execution_environment": {
            "canonical_sha256": "b" * 64,
            "value": {"retained_artifacts": retained},
        }
    }
    bundle = {
        "bundle_sha256": bundle_sha256,
        "statement": statement,
        "statement_sha256": statement_sha256,
    }
    _write(
        bundle_root / "run-bundle.json",
        canonical_json_bytes(bundle),
    )
    archive = root / "producer-certificate.tar"
    create_archive(package, archive)
    claim = {
        "algorithm_hash": "1" * 64,
        "algorithm_id": "sparkinterval.ternary-goldbach.cdem-table-abel.v2",
        "input_hash": "2" * 64,
        "nonce": "3" * 64,
    }
    receipt = {
        "bindings": {
            "run_bundle_sha256": bundle_sha256,
            "wire_statement_sha256": statement_sha256,
        },
        "claim": claim,
        "receipt_sha256": "4" * 64,
    }
    return archive, receipt, bundle


class CdemArtifactTerminalMaterializerTest(unittest.TestCase):
    def test_schema_example_and_cli_are_additive_and_closed(self) -> None:
        schema = json.loads(SCHEMA.read_bytes())
        example = json.loads(EXAMPLE.read_bytes())
        self.assertEqual(set(schema["required"]), materializer.SITE_FIELDS)
        self.assertEqual(example["kind"], materializer.SITE_KIND)
        serialized = json.dumps(schema)
        self.assertNotIn("workload_executable", serialized)
        self.assertNotIn("registered_invocation", serialized)
        if jsonschema is not None:
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.Draft202012Validator.check_schema(
                json.loads(MANIFEST_SCHEMA.read_bytes())
            )
            jsonschema.validate(example, schema)
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    ROOT
                    / "tools/tg_azure_cpu_cdem_artifact_terminal_materializer.py"
                ),
                "--help",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("materialize", completed.stdout)

    def test_certificate_audit_recovers_only_signed_retained_artifact(
        self,
    ) -> None:
        artifact = synthetic_production_shape_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, receipt, _bundle = certificate_archive(
                root, artifact=artifact
            )
            with (
                mock.patch.object(
                    materializer.verify_run_bundle,
                    "verify_bundle",
                    return_value={
                        "accepted": True,
                        "artifacts_verified": True,
                        "bundle_sha256": "f" * 64,
                        "statement_sha256": "a" * 64,
                    },
                ),
                mock.patch.object(
                    materializer.receipt_issuer,
                    "claim_from_bundle",
                    return_value=receipt["claim"],
                ),
            ):
                recovered, binding = materializer._inspect_producer_certificate(
                    archive, receipt
                )
            self.assertEqual(recovered, artifact)
            self.assertEqual(
                binding["artifact_sha256"], hashlib.sha256(artifact).hexdigest()
            )
            self.assertEqual(binding["chunk_count"], 1_000)
            self.assertEqual(
                binding["producer_wire_statement_sha256"], "a" * 64
            )

    def test_certificate_audit_rejects_wire_and_artifact_substitution(
        self,
    ) -> None:
        artifact = synthetic_production_shape_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, receipt, _bundle = certificate_archive(
                root,
                artifact=artifact,
                artifact_sha256="c" * 64,
            )
            verified = {
                "accepted": True,
                "artifacts_verified": True,
                "bundle_sha256": "f" * 64,
                "statement_sha256": "a" * 64,
            }
            with (
                mock.patch.object(
                    materializer.verify_run_bundle,
                    "verify_bundle",
                    return_value=verified,
                ),
                mock.patch.object(
                    materializer.receipt_issuer,
                    "claim_from_bundle",
                    return_value=receipt["claim"],
                ),
                self.assertRaisesRegex(
                    materializer.CdemArtifactTerminalMaterializerError,
                    "differs from the signed statement digest",
                ),
            ):
                materializer._inspect_producer_certificate(archive, receipt)

            archive2, receipt2, _bundle2 = certificate_archive(
                root / "second", artifact=artifact
            )
            receipt2["bindings"]["wire_statement_sha256"] = "d" * 64
            with (
                mock.patch.object(
                    materializer.verify_run_bundle,
                    "verify_bundle",
                    return_value=verified,
                ),
                self.assertRaisesRegex(
                    materializer.CdemArtifactTerminalMaterializerError,
                    "signed run bundle",
                ),
            ):
                materializer._inspect_producer_certificate(archive2, receipt2)

    @unittest.skipUnless(
        shutil.which("g++") and platform.machine() == "x86_64",
        "an x86_64 g++ build host is required",
    )
    def test_static_terminal_closure_builds_two_pinned_elfs(self) -> None:
        context = source_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_root = root / "artifact-root"
            artifact_root.mkdir()
            records, steps, compiler = materializer._build_static_closure(
                context, artifact_root
            )
            self.assertEqual(len(steps), 2)
            self.assertTrue(compiler["sha256"])
            terminal = artifact_root / TERMINAL_PATH
            replayer = artifact_root / REPLAYER_PATH
            for executable in (terminal, replayer):
                self.assertTrue(executable.is_file())
                self.assertFalse(_elf_has_interp(executable))

    def test_job_uses_complete_artifact_as_measured_input(self) -> None:
        context = source_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_root = root / "artifact-root"
            artifact_root.mkdir()
            terminal = _write(artifact_root / TERMINAL_PATH, b"terminal", 0o500)
            replayer = _write(artifact_root / REPLAYER_PATH, b"replayer", 0o500)
            source_tree = _write(
                artifact_root / "source/source-closure.json", b"{}", 0o400
            )
            records = [
                materializer._artifact_record(
                    terminal,
                    artifact_root,
                    role="closed_cdem_artifact_terminal_and_trace_verifier",
                    statement_role="host_executable",
                    executable=True,
                ),
                materializer._artifact_record(
                    replayer,
                    artifact_root,
                    role="cdem_independent_chunk_replayer",
                    statement_role="checker_executable",
                    executable=True,
                ),
                materializer._artifact_record(
                    source_tree,
                    artifact_root,
                    role="reviewed_source_closure_manifest",
                    statement_role="source_tree",
                    executable=False,
                ),
            ]
            artifact = synthetic_production_shape_artifact()
            input_path = artifact_root / INPUT_PATH
            _write(input_path, artifact)
            runner = _write(root / "runner-policy.json", b"{}")
            site = {
                "base": {
                    "policies": {
                        "runner": {
                            **_pin(runner),
                            "classification": "production",
                            "policy_id": "fixture.runner.production.v1",
                        }
                    }
                }
            }
            job = materializer._job(
                context,
                CDEM_ARTIFACT_TERMINAL_FACTORY,
                artifact_root,
                records,
                input_path,
                site,
            )
            self.assertEqual(job["algorithm"]["algorithm_id"], ALGORITHM_ID)
            self.assertEqual(job["input_artifact"]["path"], INPUT_PATH)
            self.assertEqual(
                job["input_artifact"]["sha256"],
                hashlib.sha256(artifact).hexdigest(),
            )
            replayer_sha256 = hashlib.sha256(replayer.read_bytes()).hexdigest()
            self.assertIn(replayer_sha256, job["command"]["argv"])
            self.assertIn(
                replayer_sha256,
                job["work_trace_contract"]["verifier_argv"],
            )
            self.assertNotEqual(
                job["input_artifact"]["sha256"],
                hashlib.sha256(
                    b'{"K":199330,"N":5000000000,'
                    b'"weight_scale":1000000000000000000}'
                ).hexdigest(),
            )

    def test_factory_has_no_registered_invocation_or_producer_binary(self) -> None:
        factory = CDEM_ARTIFACT_TERMINAL_FACTORY
        self.assertNotIn("tg_cdem_abel_measured_workload.cpp", factory.source_paths)
        self.assertNotIn("reference/tg_cdem_abel.cpp", factory.source_paths)
        self.assertIn(
            "reference/tg_cdem_abel_artifact_terminal.cpp",
            factory.source_paths,
        )
        argv = factory.command_argv("e" * 64)
        self.assertEqual(argv[0], TERMINAL_PATH)
        self.assertIn("@input@", argv)
        self.assertNotIn("run-cdem-abel-full", argv)


if __name__ == "__main__":
    unittest.main()
