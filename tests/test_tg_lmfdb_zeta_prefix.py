#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact framing, multiplicity, boundary, and fail-closed prefix tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tg_verifier.lmfdb_zeta_prefix import (
    FILELIST_COUNT,
    FILELIST_SHA256,
    LMFDBZetaPrefixError,
    MD5_MANIFEST_SHA256,
    README_SHA256,
    SOURCE_PARSER_COMMIT,
    SOURCE_PARSER_SHA256,
    TARGET_FILE_SHA256,
    TARGET_HEIGHT,
    TARGET_MULTIPLICITY_COUNT,
    ZetaDataFileAudit,
    aggregate_file_audits,
    audit_data_file,
    parse_source_inventory,
)


def _delta(value: int) -> bytes:
    if value < 0 or value >= 1 << 104:
        raise ValueError("delta is not uint104")
    return struct.pack("<QIB", value & ((1 << 64) - 1), (value >> 64) & ((1 << 32) - 1), value >> 96)


def _file(blocks: list[tuple[int, int, int, list[int]]]) -> bytes:
    raw = bytearray(struct.pack("<Q", len(blocks)))
    for t0, t1, n0, midpoints in blocks:
        raw.extend(struct.pack("<ddQQ", t0, t1, n0, n0 + len(midpoints)))
        previous = t0 << 101
        for midpoint in midpoints:
            scaled = midpoint << 101
            raw.extend(_delta(scaled - previous))
            previous = scaled
    return bytes(raw)


def _audit(path: Path, filename: str, raw: bytes, *, target: int | None = None, count: int | None = None) -> ZetaDataFileAudit:
    path.write_bytes(raw)
    return audit_data_file(
        path,
        expected_filename=filename,
        expected_md5=hashlib.md5(raw, usedforsecurity=False).hexdigest(),
        target_height=target,
        expected_target_count=count,
    )


class LMFDBZetaPrefixTests(unittest.TestCase):
    def test_inventory_parser_rejects_reorder_and_manifest_gap(self) -> None:
        good_list = b"zeros_14.dat\nzeros_20.dat\n"
        good_md5 = b"%s *zeros_14.dat\n%s *zeros_20.dat\n" % (b"0" * 32, b"1" * 32)
        inventory = parse_source_inventory(good_list, good_md5, require_public_shape=False)
        self.assertEqual(inventory.filenames, ("zeros_14.dat", "zeros_20.dat"))
        with self.assertRaises(LMFDBZetaPrefixError):
            parse_source_inventory(
                b"zeros_20.dat\nzeros_14.dat\n", good_md5, require_public_shape=False
            )
        with self.assertRaises(LMFDBZetaPrefixError):
            parse_source_inventory(good_list, good_md5.splitlines(keepends=True)[0], require_public_shape=False)

    def test_exact_target_cut_and_multiplicity_slot_order(self) -> None:
        raw = _file(
            [
                (14, 20, 0, [15, 17, 19]),
                (20, 30, 3, [22, 22, 28]),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "zeros_14.dat"
            audit = _audit(path, path.name, raw, target=18, count=2)
        self.assertEqual(audit.encoded_multiplicity_slots, 6)
        self.assertEqual(audit.first_multiplicity_count, 0)
        self.assertEqual(audit.last_multiplicity_count, 6)
        self.assertIsNotNone(audit.target_cut)
        self.assertEqual(audit.target_cut.below_in_block, 2)  # type: ignore[union-attr]

    def test_straddling_target_truncation_and_count_gap_fail(self) -> None:
        ambiguous = _file([(14, 20, 0, [15, 18, 19])])
        discontinuous = bytearray(_file([(14, 20, 0, [15]), (20, 30, 1, [22])]))
        # Second block N0 begins after: file count + first header + first slot.
        second_header = 8 + 32 + 13
        struct.pack_into("<Q", discontinuous, second_header + 16, 2)
        cases = (
            (ambiguous, 18, 1),
            (bytes(discontinuous), None, None),
            (_file([(14, 20, 0, [15, 17])])[:-1], None, None),
        )
        for raw, target, count in cases:
            with self.subTest(target=target, size=len(raw)):
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "zeros_14.dat"
                    path.write_bytes(raw)
                    with self.assertRaises(LMFDBZetaPrefixError):
                        audit_data_file(
                            path,
                            expected_filename=path.name,
                            expected_md5=hashlib.md5(raw, usedforsecurity=False).hexdigest(),
                            target_height=target,
                            expected_target_count=count,
                        )

    def test_cross_file_continuity_and_order_are_committed(self) -> None:
        first_raw = _file([(14, 20, 0, [15, 17])])
        second_raw = _file([(20, 30, 2, [22, 28])])
        filelist = b"zeros_14.dat\nzeros_20.dat\n"
        md5 = (
            f"{hashlib.md5(first_raw, usedforsecurity=False).hexdigest()} *zeros_14.dat\n"
            f"{hashlib.md5(second_raw, usedforsecurity=False).hexdigest()} *zeros_20.dat\n"
        ).encode()
        inventory = parse_source_inventory(filelist, md5, require_public_shape=False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _audit(root / "zeros_14.dat", "zeros_14.dat", first_raw)
            second = _audit(root / "zeros_20.dat", "zeros_20.dat", second_raw)
            aggregate = aggregate_file_audits(
                [first, second], inventory=inventory, require_complete_public_prefix=False
            )
            self.assertEqual(aggregate["file_count"], 2)
            self.assertEqual(len(aggregate["aggregate_sha256"]), 64)
            with self.assertRaises(LMFDBZetaPrefixError):
                aggregate_file_audits(
                    [second, first], inventory=inventory, require_complete_public_prefix=False
                )

    def test_reviewed_spec_and_code_pins_agree(self) -> None:
        specification = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "specifications"
                / "LMFDB_ZETA_PREFIX_UPSTREAM.json"
            ).read_text(encoding="utf-8")
        )
        source = specification["source"]
        self.assertEqual(source["ordered_filelist"]["sha256"], FILELIST_SHA256)
        self.assertEqual(source["ordered_filelist"]["line_count"], FILELIST_COUNT)
        self.assertEqual(source["md5_manifest"]["sha256"], MD5_MANIFEST_SHA256)
        self.assertEqual(source["readme"]["sha256"], README_SHA256)
        self.assertEqual(source["reader"]["commit"], SOURCE_PARSER_COMMIT)
        self.assertEqual(source["reader"]["sha256"], SOURCE_PARSER_SHA256)
        self.assertEqual(specification["prefix"]["target_height"], TARGET_HEIGHT)
        self.assertEqual(
            specification["prefix"]["target_multiplicity_count"],
            TARGET_MULTIPLICITY_COUNT,
        )
        self.assertEqual(
            specification["prefix"]["terminal_file"]["sha256"], TARGET_FILE_SHA256
        )


if __name__ == "__main__":
    unittest.main()
