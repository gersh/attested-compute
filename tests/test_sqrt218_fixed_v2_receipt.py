# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tg_verifier import sqrt218_fixed_v2_receipt as fixed


def u16(value: int) -> bytes:
    return value.to_bytes(2, "big")


def u32(value: int) -> bytes:
    return value.to_bytes(4, "big")


def u64(value: int) -> bytes:
    return value.to_bytes(8, "big")


def certificate_bytes() -> bytes:
    raw = bytearray(fixed.CERTIFICATE_HEADER_BYTES)
    raw[0:8] = b"SQ218V2\x00"
    raw[8:10] = u16(2)
    raw[10:12] = u16(fixed.CERTIFICATE_HEADER_BYTES)
    raw[12:16] = u32(0)
    raw[16:24] = u64(fixed.SOURCE_CUTOFF)
    raw[24:32] = u64(1_517_397)
    raw[32:40] = u64(30)
    raw[40:48] = u64(281_474_976_710_656)
    raw[48:56] = u64(1_073_741_824)
    raw[136:144] = u64(len(raw))
    return bytes(raw)


def accepted_result(certificate: bytes) -> bytes:
    raw = bytearray(fixed.NATIVE_RESULT_BYTES)
    raw[0:8] = b"SQ218R2\x00"
    raw[8:10] = u16(1)
    raw[10:12] = u16(fixed.NATIVE_RESULT_BYTES)
    raw[12:16] = u32(0)
    raw[16:24] = u64(len(certificate))
    for offset, value in zip(range(24, 88, 8), range(1, 9), strict=True):
        raw[offset : offset + 8] = u64(value)
    raw[88:120] = hashlib.sha256(certificate).digest()
    return bytes(raw)


class FixedV2ReceiptProjectionTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[dict, dict, dict[str, Path]]:
        certificate_raw = certificate_bytes()
        native_raw = accepted_result(certificate_raw)
        paths = {
            "certificate": root / "certificate.sq218v2",
            "native_result": root / "native-result.bin",
            "result_envelope": root / "result.txt",
            "checker_executable": root / "sqrt218_cpu_checker_v2",
            "execution_closure": root / "closure-manifest.json",
            "verification_report": root / "verification-report.json",
            "work_trace": root / "work-trace.json",
        }
        paths["certificate"].write_bytes(certificate_raw)
        paths["native_result"].write_bytes(native_raw)
        paths["checker_executable"].write_bytes(b"tiny checker identity")
        paths["checker_executable"].chmod(0o700)
        paths["execution_closure"].write_bytes(b'{"files":[]}')
        paths["verification_report"].write_bytes(b'{"accepted":true}')

        challenge = "11" * 32
        job_binding = "22" * 32
        preliminary, envelope_raw, trace_raw = fixed.build_projection(
            certificate=paths["certificate"],
            native_result=paths["native_result"],
            checker_executable=paths["checker_executable"],
            execution_closure=paths["execution_closure"],
            start_challenge_sha256=challenge,
            job_binding_sha256=job_binding,
            verification_report=paths["verification_report"],
            wire_statement_sha256="33" * 32,
        )
        paths["result_envelope"].write_bytes(envelope_raw)
        paths["work_trace"].write_bytes(trace_raw)
        environment_value = {
            "artifact_closure_manifest_sha256": preliminary[
                "execution_closure_sha256"
            ],
            "job_binding_sha256": job_binding,
            "work_trace_artifact_sha256": preliminary[
                "work_trace_artifact_sha256"
            ],
            "work_trace_chain_sha256": preliminary[
                "work_trace_chain_sha256"
            ],
        }
        statement = {
            "algorithm": {"algorithm_id": fixed.ALGORITHM_ID},
            "build_artifacts": [
                {
                    "role": "execution_manifest",
                    "sha256": preliminary["execution_closure_sha256"],
                },
                {
                    "role": "host_executable",
                    "sha256": preliminary["checker_executable_sha256"],
                },
            ],
            "execution_environment": {
                "canonical_sha256": fixed.sha256_bytes(
                    fixed.canonical_json_bytes(environment_value)
                ),
                "value": environment_value,
            },
            "input_artifact": {
                "sha256": preliminary["certificate_sha256"],
                "size_bytes": preliminary["certificate_size_bytes"],
            },
            "nonce": challenge,
            "output_artifact": {
                "sha256": preliminary["result_envelope_sha256"],
                "size_bytes": preliminary["result_envelope_size_bytes"],
            },
        }
        statement_sha256 = fixed.sha256_bytes(
            fixed.canonical_json_bytes(statement)
        )
        projection, final_envelope, final_trace = fixed.build_projection(
            certificate=paths["certificate"],
            native_result=paths["native_result"],
            checker_executable=paths["checker_executable"],
            execution_closure=paths["execution_closure"],
            start_challenge_sha256=challenge,
            job_binding_sha256=job_binding,
            verification_report=paths["verification_report"],
            wire_statement_sha256=statement_sha256,
        )
        self.assertEqual(final_envelope, envelope_raw)
        self.assertEqual(final_trace, trace_raw)
        claim = {
            "algorithm_hash": "aa" * 32,
            "algorithm_id": fixed.ALGORITHM_ID,
            "artifacts": {
                "device_cubin_hash": fixed.NOT_APPLICABLE_DIGEST,
                "host_executable_hash": projection[
                    "checker_executable_sha256"
                ],
                "kernel_manifest_hash": projection[
                    "execution_closure_sha256"
                ],
                "source_tree_hash": "bb" * 32,
            },
            "completion": "successful",
            "domain_hash": "cc" * 32,
            "input_hash": projection["certificate_sha256"],
            "nonce": challenge,
            "output_hash": projection["result_envelope_sha256"],
            "parameters_hash": "dd" * 32,
            "result": final_envelope.decode("ascii"),
            "target": "azure_sevsnp_cpu",
            "target_profile_hash": "ee" * 32,
            "trust": "azure_sevsnp_confidential_compute",
            "trust_profile_hash": "ff" * 32,
        }
        receipt = {
            "backend": "azure_sevsnp_cpu",
            "bindings": {
                "start_challenge_sha256": challenge,
                "wire_statement_sha256": statement_sha256,
            },
            "claim": claim,
            "receipt_sha256": "99" * 32,
            "verifier": {
                "artifact_sha256": "12" * 32,
                "key_id": "reviewed-test-key",
                "policy_sha256": "34" * 32,
            },
        }
        return projection, {"receipt": receipt, "statement": statement}, paths

    def test_exact_projection_chain_never_replays_production(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection, values, paths = self.fixture(Path(temporary))
            artifact_audit = fixed.verify_exact_artifacts(
                projection, **paths
            )
            receipt_audit = fixed.validate_receipt_projection(
                projection,
                values["receipt"],
                statement=values["statement"],
            )
            self.assertTrue(artifact_audit["artifact_bytes_verified"])
            self.assertFalse(artifact_audit["production_replay_performed"])
            self.assertTrue(receipt_audit["signed_field_projection_valid"])
            self.assertFalse(receipt_audit["production_replay_performed"])

    def test_receipt_only_path_cannot_open_certificate_or_any_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection, values, _paths = self.fixture(Path(temporary))
            pins = {
                "algorithm_hash": values["receipt"]["claim"][
                    "algorithm_hash"
                ],
                "algorithm_id": fixed.ALGORITHM_ID,
                "certificate_sha256": projection["certificate_sha256"],
                "certificate_size_bytes": projection[
                    "certificate_size_bytes"
                ],
                "checker_executable_sha256": projection[
                    "checker_executable_sha256"
                ],
                "device_cubin_sha256": fixed.NOT_APPLICABLE_DIGEST,
                "domain_hash": values["receipt"]["claim"]["domain_hash"],
                "execution_closure_sha256": projection[
                    "execution_closure_sha256"
                ],
                "kind": fixed.REVIEWED_PINS_KIND,
                "parameters_hash": values["receipt"]["claim"][
                    "parameters_hash"
                ],
                "receipt_sha256": values["receipt"]["receipt_sha256"],
                "schema_version": 1,
                "source_tree_hash": values["receipt"]["claim"]["artifacts"][
                    "source_tree_hash"
                ],
                "target_profile_hash": values["receipt"]["claim"][
                    "target_profile_hash"
                ],
                "trust_profile_hash": values["receipt"]["claim"][
                    "trust_profile_hash"
                ],
                "verifier_artifact_sha256": values["receipt"]["verifier"][
                    "artifact_sha256"
                ],
                "verifier_key_id": values["receipt"]["verifier"]["key_id"],
                "verifier_policy_sha256": values["receipt"]["verifier"][
                    "policy_sha256"
                ],
                "wire_statement_sha256": projection[
                    "wire_statement_sha256"
                ],
            }
            with mock.patch(
                "builtins.open",
                side_effect=AssertionError("receipt-only path opened a file"),
            ), mock.patch.object(
                Path,
                "open",
                side_effect=AssertionError("receipt-only path opened a Path"),
            ), mock.patch.object(
                fixed,
                "_file_pin",
                side_effect=AssertionError("receipt-only path hashed a file"),
            ):
                audit = fixed.validate_receipt_only_binding(
                    values["receipt"], pins
                )
            self.assertTrue(audit["receipt_only_binding_valid"])
            self.assertFalse(audit["certificate_artifact_opened"])
            self.assertFalse(audit["production_replay_performed"])

            impossible_pins = copy.deepcopy(pins)
            impossible_pins["certificate_size_bytes"] = (
                fixed.CERTIFICATE_HEADER_BYTES - 1
            )
            with self.assertRaisesRegex(
                fixed.FixedV2ReceiptError, "smaller than the fixed-V2 header"
            ):
                fixed.validate_reviewed_pins(impossible_pins)

    def test_envelope_is_exact_full_lowercase_native_record(self) -> None:
        raw = accepted_result(certificate_bytes())
        text = fixed.encode_result_envelope(raw)
        decoded, fields = fixed.decode_result_envelope(
            text,
            expected_input_size=len(certificate_bytes()),
            expected_input_sha256=hashlib.sha256(
                certificate_bytes()
            ).hexdigest(),
        )
        self.assertEqual(decoded, raw)
        self.assertEqual(fields["status"], 0)
        self.assertEqual(len(text.encode("ascii")), 281)
        payload = text[len(fixed.RESULT_ENVELOPE_PREFIX) :]
        letter_index = next(
            index for index, character in enumerate(payload)
            if character in "abcdef"
        )
        noncanonical = (
            fixed.RESULT_ENVELOPE_PREFIX
            + payload[:letter_index]
            + payload[letter_index].upper()
            + payload[letter_index + 1 :]
        )
        with self.assertRaises(fixed.FixedV2ReceiptError):
            fixed.decode_result_envelope(noncanonical)

    def test_embedded_input_digest_is_mandatory(self) -> None:
        certificate = certificate_bytes()
        raw = bytearray(accepted_result(certificate))
        raw[119] ^= 1
        text = fixed.RESULT_ENVELOPE_PREFIX + bytes(raw).hex()
        with self.assertRaisesRegex(
            fixed.FixedV2ReceiptError, "immutable-input digest"
        ):
            fixed.decode_result_envelope(
                text,
                expected_input_size=len(certificate),
                expected_input_sha256=hashlib.sha256(certificate).hexdigest(),
            )

    def test_report_and_trace_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection, _values, paths = self.fixture(Path(temporary))
            paths["verification_report"].write_bytes(b'{"accepted":false}')
            with self.assertRaisesRegex(
                fixed.FixedV2ReceiptError, "verification_report SHA-256"
            ):
                fixed.verify_exact_artifacts(projection, **paths)

    def test_unsigned_projection_cannot_retarget_signed_statement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection, values, _paths = self.fixture(Path(temporary))
            statement = copy.deepcopy(values["statement"])
            statement["execution_environment"]["value"][
                "job_binding_sha256"
            ] = "44" * 32
            statement["execution_environment"]["canonical_sha256"] = (
                fixed.sha256_bytes(
                    fixed.canonical_json_bytes(
                        statement["execution_environment"]["value"]
                    )
                )
            )
            with self.assertRaisesRegex(
                fixed.FixedV2ReceiptError, "signed statement hash"
            ):
                fixed.validate_wire_statement_projection(
                    projection, statement
                )

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_projection_schema_matches_runtime_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection, values, _paths = self.fixture(Path(temporary))
            schema = json.loads(
                (
                    Path(__file__).resolve().parents[1]
                    / "schemas/sqrt218-fixed-v2-receipt-projection.schema.json"
                ).read_text()
            )
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.Draft202012Validator(schema).validate(projection)

            pins = {
                "algorithm_hash": values["receipt"]["claim"][
                    "algorithm_hash"
                ],
                "algorithm_id": fixed.ALGORITHM_ID,
                "certificate_sha256": projection["certificate_sha256"],
                "certificate_size_bytes": projection[
                    "certificate_size_bytes"
                ],
                "checker_executable_sha256": projection[
                    "checker_executable_sha256"
                ],
                "device_cubin_sha256": fixed.NOT_APPLICABLE_DIGEST,
                "domain_hash": values["receipt"]["claim"]["domain_hash"],
                "execution_closure_sha256": projection[
                    "execution_closure_sha256"
                ],
                "kind": fixed.REVIEWED_PINS_KIND,
                "parameters_hash": values["receipt"]["claim"][
                    "parameters_hash"
                ],
                "receipt_sha256": values["receipt"]["receipt_sha256"],
                "schema_version": 1,
                "source_tree_hash": values["receipt"]["claim"]["artifacts"][
                    "source_tree_hash"
                ],
                "target_profile_hash": values["receipt"]["claim"][
                    "target_profile_hash"
                ],
                "trust_profile_hash": values["receipt"]["claim"][
                    "trust_profile_hash"
                ],
                "verifier_artifact_sha256": values["receipt"]["verifier"][
                    "artifact_sha256"
                ],
                "verifier_key_id": values["receipt"]["verifier"]["key_id"],
                "verifier_policy_sha256": values["receipt"]["verifier"][
                    "policy_sha256"
                ],
                "wire_statement_sha256": projection[
                    "wire_statement_sha256"
                ],
            }
            pin_schema = json.loads(
                (
                    Path(__file__).resolve().parents[1]
                    / "schemas/sqrt218-fixed-v2-reviewed-pins.schema.json"
                ).read_text()
            )
            jsonschema.Draft202012Validator.check_schema(pin_schema)
            jsonschema.Draft202012Validator(pin_schema).validate(pins)
            impossible_pins = copy.deepcopy(pins)
            impossible_pins["certificate_size_bytes"] = (
                fixed.CERTIFICATE_HEADER_BYTES - 1
            )
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(pin_schema).validate(
                    impossible_pins
                )


if __name__ == "__main__":
    unittest.main()
