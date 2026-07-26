# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tg_verifier.campaign_io import canonical_json_bytes, sha256_bytes
from tg_verifier import sqrt218_proof_build as proof_build


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "proof_build/sqrt218/cloud-proof-build.v1.json"
)
SCHEMA_PATH = (
    ROOT / "schemas/sqrt218-cloud-proof-build-lane.schema.json"
)
TOOL_PATH = ROOT / "tools/tg_sqrt218_proof_build.py"
RUNNER_PATH = ROOT / "proof_build/sqrt218/run_cloud_proof_build.sh"
DOCKERFILE_PATH = ROOT / "proof_build/sqrt218/Dockerfile"


def manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text())


def reseal(value: dict[str, object]) -> dict[str, object]:
    body = {key: item for key, item in value.items() if key != "manifest_sha256"}
    value["manifest_sha256"] = sha256_bytes(canonical_json_bytes(body))
    return value


class Sqrt218ProofBuildTests(unittest.TestCase):
    def test_checked_in_lane_is_valid_but_intentionally_not_ready(self) -> None:
        checked = proof_build.load_manifest(MANIFEST_PATH)
        proof_build.validate_inputs(checked, ROOT)
        summary = proof_build.review_summary(checked)

        self.assertFalse(summary["execution_ready"])
        self.assertFalse(summary["authorizes_lean_theorem"])
        self.assertFalse(summary["architecture_execution_proved"])
        self.assertFalse(summary["production_certificate_opened"])
        self.assertEqual(
            summary["lean_checker_definition"],
            "successfulPureEntryChecker",
        )
        self.assertEqual(
            summary["lean_source_trace"], "CSuccessfulPureEntryTrace"
        )
        with self.assertRaisesRegex(
            proof_build.ProofBuildError,
            "missing-reviewed-vst-specification-and-proof-source-pins",
        ):
            proof_build.validate_inputs(
                checked,
                ROOT,
                proof_root=ROOT,
                require_ready=True,
            )

    def test_manifest_tampering_fails_closed(self) -> None:
        cases: list[tuple[str, tuple[str, ...], object, str]] = [
            (
                "mutable image tag",
                ("container", "base_image"),
                "docker.io/rocq/rocq-prover:9.1.1",
                "pinned by digest",
            ),
            (
                "false authority",
                ("authority", "authorizes_lean_theorem"),
                True,
                "authority block",
            ),
            (
                "wrong Lean checker",
                ("proof_project", "checker_definition"),
                "abstractNativeRun",
                "Lean source boundary",
            ),
            (
                "wrong target",
                ("pipeline", "target"),
                "host-default",
                "pipeline boundary",
            ),
        ]
        for label, path, replacement, message in cases:
            with self.subTest(label=label):
                changed = copy.deepcopy(manifest())
                cursor: object = changed
                for key in path[:-1]:
                    cursor = cursor[key]  # type: ignore[index]
                cursor[path[-1]] = replacement  # type: ignore[index]
                reseal(changed)
                with self.assertRaisesRegex(
                    proof_build.ProofBuildError, message
                ):
                    proof_build.validate_manifest(changed)

    def test_source_pin_and_readiness_tampering_fail_closed(self) -> None:
        changed = copy.deepcopy(manifest())
        changed["source_inputs"][0]["sha256"] = "1" * 64  # type: ignore[index]
        reseal(changed)
        checked = proof_build.validate_manifest(changed)
        with self.assertRaisesRegex(
            proof_build.ProofBuildError, "SHA-256"
        ):
            proof_build.validate_inputs(checked, ROOT)

        changed = copy.deepcopy(manifest())
        changed["proof_project"]["execution_ready"] = True  # type: ignore[index]
        changed["proof_project"]["blockers"] = []  # type: ignore[index]
        reseal(changed)
        with self.assertRaisesRegex(
            proof_build.ProofBuildError, "complete pins"
        ):
            proof_build.validate_manifest(changed)

    def test_final_image_must_be_registry_digest_pinned(self) -> None:
        with self.assertRaisesRegex(
            proof_build.ProofBuildError, "registry digest"
        ):
            proof_build.artifact_index(
                manifest(),
                ROOT,
                "example.azurecr.io/sqrt218-proof-build:latest",
            )

    def test_cli_exposes_plan_and_refuses_unready_execution(self) -> None:
        shown = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                "show-plan",
                str(MANIFEST_PATH),
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(shown.returncode, 0, shown.stderr.decode())
        plan = json.loads(shown.stdout)
        self.assertFalse(plan["proof_project"]["execution_ready"])
        self.assertFalse(plan["authority"]["authorizes_lean_theorem"])
        self.assertTrue(
            plan["container"]["base_image"].startswith(
                "docker.io/rocq/rocq-prover@sha256:"
            )
        )

        refused = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                "validate",
                str(MANIFEST_PATH),
                "--repository-root",
                str(ROOT),
                "--proof-root",
                str(ROOT),
                "--require-ready",
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertIn(
            b"missing-reviewed-vst-specification-and-proof-source-pins",
            refused.stdout,
        )

    def test_runner_and_dockerfile_are_static_cloud_scaffolding(self) -> None:
        shell = subprocess.run(
            ["bash", "-n", str(RUNNER_PATH)],
            check=False,
            capture_output=True,
        )
        self.assertEqual(shell.returncode, 0, shell.stderr.decode())

        runner = RUNNER_PATH.read_text()
        dockerfile = DOCKERFILE_PATH.read_text()
        for command in (
            "ccomp",
            "-csyntax",
            "Sqrt218CompCertC.v",
            "clightgen",
            "rocq check",
            "as --64",
            "readelf",
        ):
            self.assertIn(command, runner)
        self.assertIn(
            "ArchitectureExecutionSuppliesSuccessfulPureEntry",
            json.dumps(manifest()),
        )
        self.assertIn(
            "FROM docker.io/rocq/rocq-prover@sha256:", dockerfile
        )
        self.assertNotIn("sqrt218-finite-certificate", runner)

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_json_schema_accepts_lane_and_rejects_authority(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        value = manifest()
        validator.validate(value)

        value["authority"]["authorizes_lean_theorem"] = True  # type: ignore[index]
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(value)


if __name__ == "__main__":
    unittest.main()
