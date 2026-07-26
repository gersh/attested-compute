#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known arithmetic and failure tests for the historical summary importer."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from tg_verifier.goldbach_historical_artifact import (
    HistoricalGoldbachArtifactError,
    SummaryRow,
    PUBLIC_SUMMARY_ARCHIVE_SHA1_BASE32,
    PUBLIC_SUMMARY_GZIP_SHA256,
    PUBLIC_SUMMARY_RAW_SHA256,
    _is_prime_u64,
    audit_public_summary,
    audit_summary_rows,
)


SMALL_ROWS = (
    SummaryRow(1, 2, 4, 1, True, True),
    SummaryRow(2, 3, 6, 8, True, True),
    SummaryRow(3, 5, 12, 4, True, True),
    SummaryRow(4, 7, 30, 1, True, True),
)


class HistoricalGoldbachArtifactTests(unittest.TestCase):
    def test_reviewed_inventory_and_auditor_pins_agree(self) -> None:
        inventory_path = (
            Path(__file__).resolve().parents[1]
            / "specifications"
            / "GOLDBACH_HISTORICAL_ARTIFACTS.json"
        )
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        self.assertFalse(inventory["receipt_eligible"])
        summary = inventory["artifacts"][0]
        self.assertEqual(
            summary["archive_cdx_sha1_base32"],
            PUBLIC_SUMMARY_ARCHIVE_SHA1_BASE32,
        )
        self.assertEqual(summary["compressed_sha256"], PUBLIC_SUMMARY_GZIP_SHA256)
        self.assertEqual(summary["uncompressed_sha256"], PUBLIC_SUMMARY_RAW_SHA256)

    def test_small_complete_count_and_partition_witnesses(self) -> None:
        report = audit_summary_rows(
            SMALL_ROWS, binary_limit=30, expected_last_prime=7
        )
        self.assertEqual(report["total_partition_count"], 14)
        self.assertEqual(report["checked_partition_witnesses"], 4)
        self.assertEqual(report["largest_first_occurrence"], 30)

    def test_primality_is_exact_on_u64_edge_cases(self) -> None:
        self.assertTrue(_is_prime_u64(2))
        self.assertTrue(_is_prime_u64(18_446_744_073_709_551_557))
        self.assertFalse(_is_prime_u64(18_446_744_073_709_551_615))
        self.assertFalse(_is_prime_u64(1 << 64))

    def test_gap_wrong_count_and_nonminimal_witness_fail(self) -> None:
        mutations = (
            SMALL_ROWS[:2] + SMALL_ROWS[3:],
            SMALL_ROWS[:2] + (replace(SMALL_ROWS[2], count=3),) + SMALL_ROWS[3:],
            SMALL_ROWS[:3] + (replace(SMALL_ROWS[3], first_occurrence=14),),
        )
        for rows in mutations:
            with self.subTest(rows=rows):
                with self.assertRaises(HistoricalGoldbachArtifactError):
                    audit_summary_rows(
                        rows, binary_limit=30, expected_last_prime=7
                    )

    def test_unpinned_bytes_cannot_enter_public_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "t0.txt.gz"
            path.write_bytes(b"not the pinned historical table")
            with self.assertRaises(HistoricalGoldbachArtifactError):
                audit_public_summary(path)


if __name__ == "__main__":
    unittest.main()
