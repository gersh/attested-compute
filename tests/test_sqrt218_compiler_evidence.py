# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier import sqrt218_compiler_evidence as evidence


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def artifact(label: str) -> dict[str, object]:
    return {
        "artifact_id": label,
        "sha256": digest(label),
        "size_bytes": len(label) + 1,
    }


def body() -> dict[str, object]:
    neutral_id = "sparkinterval.sqrt218.fixed-v2.neutral-contract.v1"
    neutral_hash = digest("neutral-contract")
    assembly = artifact("compcert-textual-assembly")
    object_file = artifact("sqrt218-object")
    link_map = artifact("sqrt218-link-map")
    elf_file = artifact("sqrt218-static-elf")
    residual = [
        {
            "boundary_id": boundary_id,
            "note": f"Explicit test-only residual boundary: {boundary_id}.",
            "status": "unproved",
        }
        for boundary_id in sorted(evidence.REQUIRED_RESIDUAL_TRUST)
    ]
    return {
        "authority": dict(evidence.AUTHORITY_BLOCK),
        "build_chain": {
            "assembler": {
                "command_sha256": digest("assembler-command"),
                "executable": artifact("assembler-executable"),
                "exit_code": 0,
                "input_assembly_sha256": assembly["sha256"],
                "output_object": object_file,
                "tool_id": "gnu-as",
                "version": "GNU assembler test fixture",
            },
            "c_translation": {
                "clight_ast": artifact("clight-ast"),
                "compcert_c_ast": artifact("compcert-c-ast"),
                "preprocessed_source": artifact("preprocessed-c"),
                "source": artifact("sqrt218-pure-c-source"),
            },
            "compcert": {
                "abstract_assembly": artifact("compcert-abstract-assembly"),
                "clight_ast_sha256": digest("clight-ast"),
                "command_sha256": digest("compcert-command"),
                "compcert_c_ast_sha256": digest("compcert-c-ast"),
                "compiler_id": "compcert-x86_64",
                "configuration": artifact("compcert-configuration"),
                "executable": artifact("compcert-executable"),
                "exit_code": 0,
                "preprocessed_input_sha256": digest("preprocessed-c"),
                "source_revision": "1234567890abcdef",
                "textual_assembly": assembly,
                "version": "3.test",
            },
            "elf": {
                "architecture": "x86_64",
                "dependencies_report_sha256": digest("dependency-audit"),
                "elf_class": "ELF64",
                "elf_header_sha256": digest("elf-header"),
                "endianness": "little",
                "entry_symbol": "_start",
                "entry_virtual_address_hex": "0000000000401000",
                "file": elf_file,
                "file_type": "ET_EXEC",
                "has_writable_executable_segment": False,
                "interpreter_present": False,
                "link_map_sha256": link_map["sha256"],
                "needed_libraries": [],
                "nx_stack": True,
                "pie": False,
                "program_headers_sha256": digest("program-headers"),
                "section_headers_sha256": digest("section-headers"),
                "static_linked": True,
                "symbols_sha256": digest("symbols"),
            },
            "formal_architecture": {
                "architecture": "x86_64",
                "entry_symbol": "_start",
                "entry_virtual_address_hex": "0000000000401000",
                "lean_model_declaration_id": (
                    "SparkInterval.Execution.Architecture.X86ELF."
                    "ProductionModel"
                ),
                "model_id": "sparkinterval.x86_64-pure-entry-semantics.v1",
                "model_sha256": digest("formal-architecture-model"),
                "sysv_abi_contract_sha256": digest("sysv-abi-contract"),
            },
            "linker": {
                "command_sha256": digest("linker-command"),
                "executable": artifact("linker-executable"),
                "exit_code": 0,
                "input_objects": [object_file, artifact("crt-object")],
                "link_map": link_map,
                "output_elf_sha256": elf_file["sha256"],
                "tool_id": "gnu-ld",
                "version": "GNU linker test fixture",
            },
            "valex": {
                "command_sha256": digest("valex-command"),
                "exit_code": 0,
                "report": artifact("valex-report"),
                "status": "passed",
                "tool": artifact("valex-executable"),
                "validated_assembly_sha256": assembly["sha256"],
                "version": "test fixture",
            },
            "vst": {
                "assumptions_report": artifact("vst-assumptions-report"),
                "proof_bundle": artifact("vst-proof-bundle"),
                "rocqchk": {
                    "command_sha256": digest("rocqchk-command"),
                    "executable": artifact("rocqchk-executable"),
                    "exit_code": 0,
                    "status": "passed",
                    "stderr": artifact("rocqchk-stderr"),
                    "stdout": artifact("rocqchk-stdout"),
                    "version": "Rocq test fixture",
                },
                "specification_id": "sqrt218_vst_spec",
                "verification_theorem_id": "body_tg_sq218_verify_snapshot_v2",
                "verified_function_id": "tg_sq218_verify_snapshot_v2",
            },
        },
        "contracts": {
            "cross_prover_map": {
                "mapping_id": "sqrt218-lean-rocq-map.v1",
                "mapping_sha256": digest("cross-prover-map"),
                "status": "reviewed_not_machine_checked",
            },
            "lean": {
                "declaration_id": (
                    "SparkInterval.TernaryGoldbach.Sqrt218CPUChecker."
                    "V2Adapter.NativeAcceptanceRefinesV2"
                ),
                "neutral_contract_id": neutral_id,
                "neutral_contract_sha256": neutral_hash,
                "source_sha256": digest("lean-source"),
                "statement_sha256": digest("lean-statement"),
            },
            "neutral": {
                "contract_id": neutral_id,
                "contract_sha256": neutral_hash,
                "format": "canonical-utf8-contract-v1",
            },
            "rocq": {
                "neutral_contract_id": neutral_id,
                "neutral_contract_sha256": neutral_hash,
                "source_sha256": digest("rocq-source"),
                "statement_sha256": digest("rocq-statement"),
                "theorem_id": "Sqrt218.vst.body_tg_sq218_verify_snapshot_v2",
            },
        },
        "kind": evidence.MANIFEST_KIND,
        "residual_trust": residual,
        "schema_version": evidence.SCHEMA_VERSION,
    }


class CompilerEvidenceManifestTests(unittest.TestCase):
    def test_valid_manifest_is_only_a_non_authorizing_index(self) -> None:
        manifest = evidence.seal_manifest(body())
        encoded = canonical_json_bytes(manifest)
        checked = evidence.validate_manifest_bytes(encoded)
        summary = evidence.validation_summary(checked)

        self.assertTrue(summary["compiler_evidence_manifest_valid"])
        self.assertTrue(summary["identity_bindings_checked"])
        self.assertFalse(summary["artifact_bytes_read"])
        self.assertFalse(summary["production_replay_performed"])
        self.assertFalse(summary["authorizes_lean_theorem"])
        self.assertFalse(summary["authorizes_receipt"])
        self.assertFalse(summary["machine_code_refinement_proven_by_validation"])
        self.assertEqual(
            summary["formal_architecture_entry_symbol"], "_start"
        )
        self.assertEqual(
            summary["formal_architecture_model_sha256"],
            digest("formal-architecture-model"),
        )
        self.assertTrue(summary["execution_closure_projection_checked"])
        self.assertEqual(
            summary["execution_closure_sha256"],
            evidence.execution_closure_projection(manifest)[
                "execution_closure_sha256"
            ],
        )

    def test_execution_closure_projection_matches_lean_framing(self) -> None:
        manifest = evidence.seal_manifest(body())
        metadata = evidence.derive_execution_closure_metadata(manifest)
        self.assertEqual(
            metadata,
            {
                "compiler_evidence_manifest_version": evidence.SCHEMA_VERSION,
                "compiler_evidence_manifest_sha256": manifest[
                    "manifest_sha256"
                ],
                "compiler_source_sha256": digest(
                    "sqrt218-pure-c-source"
                ),
                "compiler_id": "compcert-x86_64",
                "compiler_version": "3.test",
                "compiler_binary_sha256": digest("compcert-executable"),
                "compiler_configuration_sha256": digest(
                    "compcert-configuration"
                ),
                "formal_architecture_model_sha256": digest(
                    "formal-architecture-model"
                ),
                "target": "azure_sevsnp_cpu",
                "sysv_abi_contract_sha256": digest("sysv-abi-contract"),
                "neutral_contract_id": (
                    "sparkinterval.sqrt218.fixed-v2.neutral-contract.v1"
                ),
                "neutral_contract_sha256": digest("neutral-contract"),
                "elf_sha256": digest("sqrt218-static-elf"),
                "entry_point": "_start",
            },
        )

        def frame(value: str) -> bytes:
            raw = value.encode("utf-8")
            return str(len(raw)).encode("ascii") + b":" + raw

        expected = bytearray(
            evidence.EXECUTION_CLOSURE_METADATA_KIND.encode("utf-8")
        )
        for field_name in evidence.EXECUTION_CLOSURE_METADATA_FIELDS:
            expected.extend(frame(field_name))
            expected.extend(frame(str(metadata[field_name])))
        expected_bytes = bytes(expected)
        projection = evidence.execution_closure_projection(manifest)

        self.assertEqual(
            evidence.encode_execution_closure_metadata(metadata),
            expected_bytes,
        )
        self.assertEqual(projection["canonical_metadata_size_bytes"], 1029)
        self.assertEqual(
            projection["canonical_metadata_text"],
            expected_bytes.decode("utf-8"),
        )
        self.assertEqual(
            projection["canonical_metadata_utf8_hex"], expected_bytes.hex()
        )
        self.assertEqual(
            projection["execution_closure_sha256"],
            "c529a022c5014bf2810ab856182003fc"
            "05714035217ef8561cdc4f032a32a15a",
        )
        evidence.validate_execution_closure_projection(
            projection, manifest=manifest
        )

    def test_execution_closure_projection_tampering_fails_closed(self) -> None:
        manifest = evidence.seal_manifest(body())
        projection = evidence.execution_closure_projection(manifest)

        changed = copy.deepcopy(projection)
        changed["metadata"]["compiler_binary_sha256"] = digest(
            "different-compiler"
        )
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError,
            "does not match compiler manifest",
        ):
            evidence.validate_execution_closure_projection(
                changed, manifest=manifest
            )

        changed = copy.deepcopy(projection)
        changed["canonical_metadata_utf8_hex"] = (
            "00" + changed["canonical_metadata_utf8_hex"][2:]
        )
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "byte mismatch"
        ):
            evidence.validate_execution_closure_projection(changed)

        changed = copy.deepcopy(projection)
        changed["execution_closure_sha256"] = digest(
            "different-execution-closure"
        )
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "SHA-256 mismatch"
        ):
            evidence.validate_execution_closure_projection(changed)

        for field_name in (
            "authorizes_lean_theorem",
            "authorizes_receipt",
            "sha256_uniqueness_proven",
        ):
            with self.subTest(field_name=field_name):
                changed = copy.deepcopy(projection)
                changed[field_name] = True
                with self.assertRaisesRegex(
                    evidence.CompilerEvidenceError, "must be false"
                ):
                    evidence.validate_execution_closure_projection(changed)

        changed = copy.deepcopy(projection)
        changed["schema_version"] = True
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "schema_version"
        ):
            evidence.validate_execution_closure_projection(changed)

    def test_projection_cli_reads_only_the_synthetic_manifest(self) -> None:
        raw = canonical_json_bytes(evidence.seal_manifest(body()))
        tool = (
            Path(__file__).resolve().parents[1]
            / "tools/tg_sqrt218_compiler_evidence.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "compiler-evidence.json"
            manifest_path.write_bytes(raw)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(tool),
                    "--execution-closure-projection",
                    str(manifest_path),
                ],
                check=False,
                capture_output=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        projection = json.loads(completed.stdout)
        self.assertEqual(
            projection["kind"],
            evidence.EXECUTION_CLOSURE_PROJECTION_KIND,
        )
        self.assertFalse(projection["artifact_bytes_read"])
        self.assertFalse(projection["production_replay_performed"])
        self.assertFalse(projection["authorizes_lean_theorem"])
        self.assertEqual(
            projection["execution_closure_sha256"],
            "c529a022c5014bf2810ab856182003fc"
            "05714035217ef8561cdc4f032a32a15a",
        )

    def test_loader_reads_only_the_compact_manifest(self) -> None:
        raw = canonical_json_bytes(evidence.seal_manifest(body()))
        manifest_path = Path("/not-opened/compiler-evidence.json")
        with mock.patch.object(
            evidence, "read_bytes_once", return_value=raw
        ) as read:
            checked = evidence.load_manifest(manifest_path)
        read.assert_called_once_with(
            manifest_path, limit=evidence.MAX_MANIFEST_BYTES
        )
        self.assertEqual(
            checked["authority"]["production_execution_performed"], False
        )

    def test_noncanonical_and_duplicate_json_fail_closed(self) -> None:
        manifest = evidence.seal_manifest(body())
        noncanonical = json.dumps(manifest, indent=2).encode("utf-8")
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "not canonical"
        ):
            evidence.validate_manifest_bytes(noncanonical)
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "duplicate JSON key"
        ):
            evidence.validate_manifest_bytes(
                b'{"schema_version":1,"schema_version":1}\n'
            )

    def test_self_hash_and_authority_tampering_fail_closed(self) -> None:
        manifest = evidence.seal_manifest(body())
        changed = copy.deepcopy(manifest)
        changed["manifest_sha256"] = digest("wrong-self-hash")
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "manifest_sha256"
        ):
            evidence.validate_manifest(changed)

        changed = copy.deepcopy(manifest)
        changed["authority"]["authorizes_lean_theorem"] = True
        changed.pop("manifest_sha256")
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "authority block"
        ):
            evidence.seal_manifest(changed)

        changed = copy.deepcopy(body())
        changed["authority"]["authorizes_receipt"] = 0  # type: ignore[index]
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "authority block"
        ):
            evidence.seal_manifest(changed)

        changed = copy.deepcopy(body())
        changed["schema_version"] = True
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "schema_version"
        ):
            evidence.seal_manifest(changed)

    def test_contract_and_build_chain_tampering_fail_closed(self) -> None:
        cases: list[tuple[str, tuple[object, ...], object, str]] = [
            (
                "Lean neutral digest",
                ("contracts", "lean", "neutral_contract_sha256"),
                digest("different-neutral"),
                "Lean contract",
            ),
            (
                "CompCert preprocessed input",
                ("build_chain", "compcert", "preprocessed_input_sha256"),
                digest("different-preprocessed"),
                "preprocessed_input_sha256",
            ),
            (
                "assembler input",
                ("build_chain", "assembler", "input_assembly_sha256"),
                digest("different-assembly"),
                "assembler input",
            ),
            (
                "ELF output",
                ("build_chain", "elf", "file", "sha256"),
                digest("different-elf"),
                "ELF file",
            ),
            (
                "link map",
                ("build_chain", "elf", "link_map_sha256"),
                digest("different-link-map"),
                "link map",
            ),
            (
                "formal architecture entry",
                ("build_chain", "formal_architecture", "entry_symbol"),
                "different_entry",
                "formal architecture entry symbol",
            ),
            (
                "formal architecture entry address",
                (
                    "build_chain",
                    "formal_architecture",
                    "entry_virtual_address_hex",
                ),
                "0000000000402000",
                "formal architecture entry address",
            ),
            (
                "Valex subject",
                (
                    "build_chain",
                    "valex",
                    "validated_assembly_sha256",
                ),
                digest("different-valex-subject"),
                "Valex evidence",
            ),
        ]
        for label, path, replacement, message in cases:
            with self.subTest(label=label):
                changed = copy.deepcopy(body())
                cursor: object = changed
                for key in path[:-1]:
                    cursor = cursor[key]  # type: ignore[index]
                cursor[path[-1]] = replacement  # type: ignore[index]
                with self.assertRaisesRegex(
                    evidence.CompilerEvidenceError, message
                ):
                    evidence.seal_manifest(changed)

        changed = copy.deepcopy(body())
        changed["build_chain"]["linker"]["input_objects"] = [  # type: ignore[index]
            artifact("unrelated-object")
        ]
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "omit"
        ):
            evidence.seal_manifest(changed)

    def test_residual_trust_cannot_be_omitted_or_renamed(self) -> None:
        changed = copy.deepcopy(body())
        changed["residual_trust"].pop()  # type: ignore[union-attr]
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "every current residual"
        ):
            evidence.seal_manifest(changed)

        changed = copy.deepcopy(body())
        changed["residual_trust"][0][  # type: ignore[index]
            "boundary_id"
        ] = "everything_is_proved"
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "incomplete or unknown"
        ):
            evidence.seal_manifest(changed)

    def test_rocqchk_and_valex_status_must_match_exit_code(self) -> None:
        changed = copy.deepcopy(body())
        changed["build_chain"]["vst"]["rocqchk"]["exit_code"] = 9  # type: ignore[index]
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "rocqchk status"
        ):
            evidence.seal_manifest(changed)

        changed = copy.deepcopy(body())
        changed["build_chain"]["valex"]["exit_code"] = 2  # type: ignore[index]
        with self.assertRaisesRegex(
            evidence.CompilerEvidenceError, "Valex status"
        ):
            evidence.seal_manifest(changed)

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_json_schema_accepts_runtime_fixture_and_rejects_authority(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas/sqrt218-compiler-evidence-manifest.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        validator = jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        manifest = evidence.seal_manifest(body())
        validator.validate(manifest)

        changed = copy.deepcopy(manifest)
        changed["authority"]["authorizes_receipt"] = True
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(changed)


if __name__ == "__main__":
    unittest.main()
