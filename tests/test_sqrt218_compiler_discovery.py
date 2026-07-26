# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tg_verifier.campaign_io import canonical_json_bytes, sha256_bytes
from tg_verifier import sqrt218_compiler_discovery as discovery


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "proof_build/sqrt218-discovery/discovery.v1.json"
SCHEMA = ROOT / "schemas/sqrt218-compiler-discovery.schema.json"
TOOL = ROOT / "tools/tg_sqrt218_compiler_discovery.py"


def manifest() -> dict[str, object]:
    return json.loads(MANIFEST.read_text())


def reseal(value: dict[str, object]) -> None:
    body = {key: value[key] for key in sorted(discovery.BODY_KEYS)}
    value["manifest_sha256"] = sha256_bytes(canonical_json_bytes(body))


class Sqrt218CompilerDiscoveryTests(unittest.TestCase):
    def test_manifest_is_valid_unready_and_non_authorizing(self) -> None:
        checked = discovery.load_manifest(MANIFEST)
        summary = discovery.review_summary(checked)
        self.assertFalse(summary["execution_ready"])
        self.assertFalse(summary["authorizes_lean_theorem"])
        self.assertFalse(summary["authorizes_receipt"])
        self.assertFalse(summary["generated_elf_execution_allowed"])
        self.assertFalse(summary["function_entry_is_linux_process_start"])
        self.assertFalse(summary["local_tool_invocation_allowed"])
        self.assertFalse(summary["production_certificate_opened"])
        self.assertEqual(summary["retained_artifact_count"], 26)
        self.assertEqual(
            checked["inventory_contract"]["required_gap_tags"],
            [
                "operand-size-prefix-0x66",
                "imul-two-or-three-operand",
                "bswap",
                "shld",
                "sse-or-xmm",
                "rol-or-ror",
                "vex",
                "evex",
                "unknown-encoding-form",
            ],
        )
        self.assertTrue(
            checked["elf_gate"][
                "all_pt_load_rows_count_permissions_recorded"
            ]
        )

    def test_validation_reads_only_the_manifest_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory) / "discovery.json"
            isolated.write_bytes(MANIFEST.read_bytes())
            checked = discovery.load_manifest(isolated)
        self.assertEqual(checked["kind"], discovery.LANE_KIND)

    def test_authority_and_readiness_cannot_be_enabled(self) -> None:
        cases = [
            (("authority", "authorizes_lean_theorem"), True, "authority"),
            (("authority", "compiler_correctness_proved"), True, "authority"),
            (("cloud_policy", "execution_ready"), True, "readiness"),
            (
                ("cloud_policy", "local_tool_invocation_allowed"),
                True,
                "readiness",
            ),
            (
                ("cloud_policy", "generated_elf_execution_allowed"),
                True,
                "readiness",
            ),
        ]
        for path, replacement, message in cases:
            with self.subTest(path=path):
                changed = copy.deepcopy(manifest())
                changed[path[0]][path[1]] = replacement  # type: ignore[index]
                reseal(changed)
                with self.assertRaisesRegex(
                    discovery.CompilerDiscoveryError, message
                ):
                    discovery.validate_manifest(changed)

    def test_scope_inventory_and_toolchain_tampering_fail_closed(self) -> None:
        cases = [
            (
                ("scope", "function_entry_elf_classification"),
                "linux-process-start",
                "scope",
            ),
            (
                ("inventory_contract", "decoder_authoritative_for_x86_semantics"),
                True,
                "inventory",
            ),
            (
                ("toolchain", "compcert"),
                {},
                "toolchain",
            ),
        ]
        for path, replacement, message in cases:
            with self.subTest(path=path):
                changed = copy.deepcopy(manifest())
                changed[path[0]][path[1]] = replacement  # type: ignore[index]
                reseal(changed)
                with self.assertRaisesRegex(
                    discovery.CompilerDiscoveryError, message
                ):
                    discovery.validate_manifest(changed)

    def test_self_hash_and_retained_artifact_set_are_closed(self) -> None:
        changed = copy.deepcopy(manifest())
        changed["retained_artifacts"].pop()  # type: ignore[union-attr]
        reseal(changed)
        with self.assertRaisesRegex(
            discovery.CompilerDiscoveryError, "retained artifact"
        ):
            discovery.validate_manifest(changed)

        changed = copy.deepcopy(manifest())
        changed["manifest_sha256"] = "1" * 64
        with self.assertRaisesRegex(
            discovery.CompilerDiscoveryError, "self-hash"
        ):
            discovery.validate_manifest(changed)

    def test_cli_validate_and_show_plan_are_metadata_only(self) -> None:
        for command in ("validate", "show-plan"):
            result = subprocess.run(
                [sys.executable, str(TOOL), command, str(MANIFEST)],
                check=False,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            value = json.loads(result.stdout)
            if command == "validate":
                self.assertFalse(value["execution_ready"])
                self.assertFalse(value["authorizes_lean_theorem"])
            else:
                self.assertFalse(
                    value["cloud_policy"]["execution_ready"]
                )
                self.assertIn(
                    "retained/direct-cfg-instructions.ndjson",
                    value["retained_artifacts"],
                )

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_schema_accepts_manifest_and_rejects_authority(self) -> None:
        schema = json.loads(SCHEMA.read_text())
        validator = jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        value = manifest()
        validator.validate(value)
        value["authority"]["authorizes_receipt"] = True  # type: ignore[index]
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(value)


if __name__ == "__main__":
    unittest.main()
