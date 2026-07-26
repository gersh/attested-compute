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
from tg_verifier import sqrt218_launcher_boundary as boundary


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "specifications/SQRT218_PURE_ENTRY_LAUNCHER_BOUNDARY.json"
)
SCHEMA_PATH = (
    ROOT / "schemas/sqrt218-pure-entry-launcher-boundary.schema.json"
)
TOOL_PATH = ROOT / "tools/tg_sqrt218_launcher_boundary.py"


def manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text())


def reseal(value: dict[str, object]) -> None:
    body = {
        key: item
        for key, item in value.items()
        if key != "manifest_sha256"
    }
    value["manifest_sha256"] = sha256_bytes(canonical_json_bytes(body))


class Sqrt218LauncherBoundaryTests(unittest.TestCase):
    def test_checked_in_boundary_is_valid_and_not_ready(self) -> None:
        checked = boundary.load_manifest(MANIFEST_PATH)
        summary = boundary.review_summary(checked)
        self.assertFalse(summary["execution_ready"])
        self.assertFalse(summary["production_ready"])
        self.assertFalse(summary["authorizes_lean_theorem"])
        self.assertFalse(summary["architecture_execution_proved"])
        self.assertFalse(summary["launcher_artifact_present"])
        self.assertTrue(summary["launcher_cloud_build_ready"])
        self.assertTrue(summary["launcher_prototype_present"])
        self.assertFalse(summary["measured_runner_satisfies_contract"])
        self.assertFalse(summary["entry_is_linux_process_start"])
        self.assertTrue(
            checked["formal_connection"][
                "execution_closure_identity_binds_launcher_artifact"
            ]
        )
        self.assertTrue(
            checked["formal_connection"][
                "execution_closure_identity_binds_launch_contract"
            ]
        )
        self.assertEqual(
            checked["memory"]["result"]["size_bytes"], 120
        )
        self.assertEqual(
            checked["memory"]["status"]["size_bytes"], 4
        )
        self.assertEqual(
            checked["abi"]["stack_alignment_at_function_entry"],
            {"modulus_bytes": 16, "remainder_bytes": 8},
        )
        self.assertIn(
            "no-signal-fault-or-timeout-and-exactly-one-launcher-attempt",
            checked["return_observer"]["accept_only_if"],
        )
        self.assertNotIn(
            "no-signal-fault-timeout-or-extra-entry",
            checked["return_observer"]["accept_only_if"],
        )

    def test_readiness_always_fails_closed_for_v1(self) -> None:
        with self.assertRaisesRegex(
            boundary.LauncherBoundaryError,
            "unreviewed-pure-entry-loader-launcher-prototype",
        ):
            boundary.require_execution_ready(manifest())

    def test_authority_abi_memory_and_runner_tampering_fail(self) -> None:
        cases: list[tuple[str, tuple[str, ...], object, str]] = [
            (
                "authority",
                ("authority", "authorizes_lean_theorem"),
                True,
                "authority",
            ),
            (
                "process entry",
                ("pure_entry", "entry_is_linux_process_start"),
                True,
                "pure_entry",
            ),
            (
                "execve",
                ("pure_entry", "execve_allowed"),
                True,
                "pure_entry",
            ),
            (
                "short result",
                ("memory", "result", "size_bytes"),
                119,
                "memory",
            ),
            (
                "wrong stack",
                (
                    "abi",
                    "stack_alignment_at_function_entry",
                    "remainder_bytes",
                ),
                0,
                "abi",
            ),
            (
                "claim existing runner",
                (
                    "current_implementation",
                    "measured_runner_satisfies_contract",
                ),
                True,
                "current_implementation",
            ),
            (
                "fake launcher pin",
                (
                    "current_implementation",
                    "launcher_artifact",
                    "sha256",
                ),
                "1" * 64,
                "current_implementation",
            ),
        ]
        for label, path, replacement, expected in cases:
            with self.subTest(label=label):
                changed = copy.deepcopy(manifest())
                cursor: object = changed
                for key in path[:-1]:
                    cursor = cursor[key]  # type: ignore[index]
                cursor[path[-1]] = replacement  # type: ignore[index]
                reseal(changed)
                with self.assertRaisesRegex(
                    boundary.LauncherBoundaryError, expected
                ):
                    boundary.validate_manifest(changed)

    def test_cli_is_metadata_only_and_require_ready_refuses(self) -> None:
        shown = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                str(MANIFEST_PATH),
                "--show-contract",
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(shown.returncode, 0, shown.stderr.decode())
        output = json.loads(shown.stdout)
        self.assertFalse(output["review"]["execution_ready"])
        self.assertFalse(
            output["contract"]["local_validation"]["elf_or_launcher_executed"]
        )

        refused = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                str(MANIFEST_PATH),
                "--require-ready",
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertIn(
            b"unreviewed-pure-entry-loader-launcher-prototype",
            refused.stdout,
        )

        module_source = (
            ROOT / "tg_verifier/sqrt218_launcher_boundary.py"
        ).read_text()
        self.assertNotIn("import subprocess", module_source)
        self.assertNotIn("import mmap", module_source)
        self.assertNotIn("ctypes", module_source)

    def test_repository_surfaces_the_actual_process_entry_mismatch(self) -> None:
        makefile = (ROOT / "cpu_checker/sqrt218/Makefile").read_text()
        runner = (ROOT / "azure/measured_runner.py").read_text()
        self.assertIn("not a normal process entry", makefile)
        self.assertIn("subprocess.Popen(", runner)
        self.assertIn("shell=False", runner)

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_json_schema_accepts_manifest_and_rejects_overclaim(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        value = manifest()
        validator.validate(value)

        value["pure_entry"]["entry_is_linux_process_start"] = True  # type: ignore[index]
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(value)


if __name__ == "__main__":
    unittest.main()
