# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tg_verifier.evidence import (
    CDEM_REQUIRED_FIELDS,
    CDEM_U_TARGET,
    CDEM_V_TARGET,
    EvidenceError,
    compare_claude_math_inventory,
    verify_cdem_abel_transcript,
    verify_cdem_abel_text,
    verify_ramare_zuniga_report,
)


class ImportedEvidenceTests(unittest.TestCase):
    def test_cdem_exact_transcript_and_tamper_rejection(self) -> None:
        fields = dict(CDEM_REQUIRED_FIELDS)
        fields["U_INC_UPPER_NUM"] = CDEM_U_TARGET
        fields["V_INC_UPPER_NUM"] = CDEM_V_TARGET
        transcript = "".join(f"{key}={value}\n" for key, value in fields.items())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cdem.txt"
            path.write_text(transcript, encoding="utf-8")
            checked = verify_cdem_abel_transcript(path)
            self.assertTrue(checked.accepted)
            self.assertFalse(checked.proves_lean_claim)
            path.write_text(transcript.replace("FINAL_G=111", "FINAL_G=112"), encoding="utf-8")
            with self.assertRaisesRegex(EvidenceError, "FINAL_G"):
                verify_cdem_abel_transcript(path)

            fields = dict(CDEM_REQUIRED_FIELDS)
            fields["U_INC_UPPER_NUM"] = -10**100
            fields["V_INC_UPPER_NUM"] = -10**100
            path.write_text(
                "".join(f"{key}={value}\n" for key, value in fields.items()),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(EvidenceError, "signed Abel output"):
                verify_cdem_abel_transcript(path)

    def test_ramare_exact_decimal_budget_and_raw_hash(self) -> None:
        raw = b"retained raw report fixture"
        raw_hash = hashlib.sha256(raw).hexdigest()
        value = {
            "status": "PASS",
            "certified_worst_ratio_upper_bound": "1.4521",
            "source_report_sha256": raw_hash,
            "finite_sweep": {
                "limit": 21_000_000_000,
                "elapsed_seconds": 10.5,
                "R2star_sqrt_log": {
                    "intended_full_range_end": 21_000_000_000,
                    "real_range_start": 3,
                    "status": "PASS",
                    "last_bad_integer": None,
                    "bound": 1.93,
                    "float64_outward_error_budget_at_worst": 0.0001,
                    "worst_ratio_abs_R2_over_sqrt_n_log_n": {
                        "n": 101,
                        "value": 1.452,
                    },
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            focused = root / "focused.json"
            raw_path = root / "raw.json"
            focused.write_text(json.dumps(value), encoding="utf-8")
            raw_path.write_bytes(raw)
            checked = verify_ramare_zuniga_report(focused, raw_path)
            self.assertEqual(
                checked.classification,
                "summary_structure_and_internal_arithmetic_only",
            )
            self.assertEqual(
                checked.metrics["certified_worst_ratio_upper"],
                str(Decimal("1.4521")),
            )
            with self.assertRaisesRegex(EvidenceError, "focused R2Star"):
                verify_ramare_zuniga_report(
                    focused,
                    raw_path,
                    expected_focused_sha256="0" * 64,
                )
            value["finite_sweep"]["R2star_sqrt_log"][
                "float64_outward_error_budget_at_worst"
            ] = 0.6
            focused.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(EvidenceError, "does not close"):
                verify_ramare_zuniga_report(focused, raw_path)

            r2 = value["finite_sweep"]["R2star_sqrt_log"]
            r2["bound"] = 999.0
            r2["float64_outward_error_budget_at_worst"] = 0.5
            r2["worst_ratio_abs_R2_over_sqrt_n_log_n"]["value"] = 998.0
            value["certified_worst_ratio_upper_bound"] = "998.5"
            focused.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(EvidenceError, "source bound"):
                verify_ramare_zuniga_report(focused, raw_path)

    def test_ramare_pinned_identity_and_fields_use_one_focused_read(self) -> None:
        raw_report = b"retained raw report fixture"
        raw_hash = hashlib.sha256(raw_report).hexdigest()
        focused_raw = json.dumps(
            {
                "status": "PASS",
                "certified_worst_ratio_upper_bound": "1.4521",
                "source_report_sha256": raw_hash,
                "finite_sweep": {
                    "limit": 21_000_000_000,
                    "elapsed_seconds": 10.5,
                    "R2star_sqrt_log": {
                        "intended_full_range_end": 21_000_000_000,
                        "real_range_start": 3,
                        "status": "PASS",
                        "last_bad_integer": None,
                        "bound": 1.93,
                        "float64_outward_error_budget_at_worst": 0.0001,
                        "worst_ratio_abs_R2_over_sqrt_n_log_n": {
                            "n": 101,
                            "value": 1.452,
                        },
                    },
                },
            }
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            raw_path = Path(directory) / "raw.json"
            raw_path.write_bytes(raw_report)
            with mock.patch.object(
                Path, "read_bytes", side_effect=[focused_raw, b"replaced"]
            ) as reader:
                checked = verify_ramare_zuniga_report(
                    Path(directory) / "replaceable-focused.json",
                    raw_path,
                    expected_focused_sha256=hashlib.sha256(focused_raw).hexdigest(),
                )
        self.assertTrue(checked.accepted)
        reader.assert_called_once_with()

    def test_cdem_chunk_manifest_composes_and_rejects_tampering(self) -> None:
        fields = dict(CDEM_REQUIRED_FIELDS)
        fields["U_INC_UPPER_NUM"] = CDEM_U_TARGET
        fields["V_INC_UPPER_NUM"] = CDEM_V_TARGET
        fields["BLOCK_SIZE"] = 5_000_000_000
        chunk = (
            "1,5000000000,0,112,"
            f"{CDEM_U_TARGET},{CDEM_V_TARGET},"
            f"{CDEM_REQUIRED_FIELDS['TOTAL_VARIATION']}"
        )
        manifest = f"CHUNK_0={chunk}\n"
        fields["CHUNK_COUNT"] = 1
        fields["CHUNK_MANIFEST_SHA256"] = hashlib.sha256(
            manifest.encode("ascii")
        ).hexdigest()
        fields["CHUNK_0"] = chunk
        transcript = "".join(f"{key}={value}\n" for key, value in fields.items())
        checked = verify_cdem_abel_text(transcript, require_chunks=True)
        self.assertEqual(checked.metrics["chunk_count"], 1)
        tampered = transcript.replace(",0,112,", ",1,112,")
        with self.assertRaisesRegex(EvidenceError, "prefix state"):
            verify_cdem_abel_text(tampered, require_chunks=True)
        oversized = transcript.replace(",0,112,", ",0,9223372036854775808,")
        with self.assertRaisesRegex(EvidenceError, "int64 range"):
            verify_cdem_abel_text(oversized, require_chunks=True)

    def test_inventory_comparison_rejects_missing_name(self) -> None:
        from tg_verifier.catalog import ATOMS

        from tg_verifier.evidence import EXPECTED_INVENTORY_CARDS

        inventory = {
            "declaration": "Math.Problems.TernaryGoldbach.ternary_goldbach",
            "status": "test fixture",
            "entries": [
                {
                    "axiom": atom.lean_name,
                    "card": EXPECTED_INVENTORY_CARDS[atom.lean_name],
                    "source_kind": "test source",
                    "trust_class": "external_finite_computation",
                    "source_locators": ["https://example.test/source"],
                }
                for atom in ATOMS
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps(inventory), encoding="utf-8")
            self.assertTrue(compare_claude_math_inventory(path).accepted)
            inventory["entries"].pop()
            path.write_text(json.dumps(inventory), encoding="utf-8")
            with self.assertRaisesRegex(EvidenceError, "13 names"):
                compare_claude_math_inventory(path)


if __name__ == "__main__":
    unittest.main()
