# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""The Lean seg-run evidence literals are the committed evidence files.

`SparkInterval/Tests/PhalaTdxSegEvidenceTest.lean` carries `statement.json`
and `tdx-quote.bin` as packed big-endian naturals so that the Lean kernel can
hash and parse them.  A packed literal is unreadable, so nothing may depend on
a human having compared it with the file.  This test does the comparison.

It also re-derives, with the standard library's SHA-256 rather than the
repository's, every digest the Lean module claims.
"""

from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path


sys.set_int_max_str_digits(1_000_000)

REPOSITORY = Path(__file__).resolve().parents[1]
EVIDENCE = REPOSITORY / "tests" / "data" / "phala_tdx_seg"
LEAN_MODULE = (REPOSITORY / "SparkInterval" / "Tests"
               / "PhalaTdxSegEvidenceTest.lean")

DOMAIN_PREFIX = b"phala-tdx-bound-computation.v1\x00"

TD_REPORT_OFFSET = 48
TD_REPORT_SIZE = 584
MR_CONFIG_ID_OFFSET = TD_REPORT_OFFSET + 184
REPORT_DATA_OFFSET = TD_REPORT_OFFSET + 520


def lean_source() -> str:
    return LEAN_MODULE.read_text()


def packed_literal(source: str, definition: str) -> bytes:
    """Recover the bytes a `packedByteSource`/`PackedBytes` literal names."""
    pattern = re.compile(
        definition + r"[^=]*:=\s*(?:packedByteSource\s+0x([0-9a-f]+)\s+(\d+)"
        r"|⟨0x([0-9a-f]+),\s*(\d+)⟩)")
    match = pattern.search(source)
    assert match is not None, f"no packed literal for {definition}"
    digits = match.group(1) or match.group(3)
    count = int(match.group(2) or match.group(4))
    value = int(digits, 16)
    return value.to_bytes(count, "big")


class SegEvidenceLiteralTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = lean_source()
        self.statement = (EVIDENCE / "statement.json").read_bytes()
        self.quote = (EVIDENCE / "tdx-quote.bin").read_bytes()

    def test_domain_prefix_literal(self) -> None:
        self.assertEqual(
            packed_literal(self.source, "segDomainPrefix"), DOMAIN_PREFIX)

    def test_statement_literal(self) -> None:
        self.assertEqual(
            packed_literal(self.source, "segStatementBytes"), self.statement)

    def test_quote_literal(self) -> None:
        self.assertEqual(packed_literal(self.source, "segQuote"), self.quote)

    def test_statement_digest_claim(self) -> None:
        digest = hashlib.sha256(DOMAIN_PREFIX + self.statement).hexdigest()
        self.assertIn(f'"{digest}"', self.source)
        self.assertEqual(
            digest,
            "53e584409d7572f87f1e00cd8441a35774d697af216021be2cdf8f9fc7233f5d")

    def test_quote_digest_claim(self) -> None:
        digest = hashlib.sha256(self.quote).hexdigest()
        self.assertIn(f'"{digest}"', self.source)

    def test_report_data_is_the_statement_digest(self) -> None:
        report_data = self.quote[REPORT_DATA_OFFSET:REPORT_DATA_OFFSET + 64]
        self.assertEqual(
            report_data[:32],
            hashlib.sha256(DOMAIN_PREFIX + self.statement).digest())
        self.assertEqual(report_data[32:], b"\x00" * 32)

    def test_mr_config_id_is_the_compose_hash(self) -> None:
        import json

        statement = json.loads(self.statement)
        compose_hash = statement["compose_hash"]
        measured = self.quote[MR_CONFIG_ID_OFFSET:MR_CONFIG_ID_OFFSET + 48]
        self.assertEqual(measured[0], 0x01)
        self.assertEqual(measured[1:33].hex(), compose_hash)
        self.assertEqual(measured[33:], b"\x00" * 15)
        self.assertIn(f'"{compose_hash}"', self.source)

    def test_quote_header_is_v4_tdx(self) -> None:
        self.assertEqual(int.from_bytes(self.quote[0:2], "little"), 4)
        self.assertEqual(int.from_bytes(self.quote[4:8], "little"), 0x81)
        self.assertGreaterEqual(
            len(self.quote), TD_REPORT_OFFSET + TD_REPORT_SIZE)

    def test_external_appraisal_agrees(self) -> None:
        """`dcap-qvl` and the Lean parser read the same two fields."""
        import json

        appraisal = json.loads(
            (EVIDENCE / "dcap-qvl-verify.stdout").read_text())
        report = appraisal["report"]["TD10"]
        self.assertEqual(appraisal["status"], "UpToDate")
        self.assertEqual(
            report["report_data"],
            self.quote[REPORT_DATA_OFFSET:REPORT_DATA_OFFSET + 64].hex())
        self.assertEqual(
            report["mr_config_id"],
            self.quote[MR_CONFIG_ID_OFFSET:MR_CONFIG_ID_OFFSET + 48].hex())


class ChunkWitnessTest(unittest.TestCase):
    """The chunk witnesses in Lean are the real intermediate SHA-256 states."""

    def test_witness_tool_reproduces_the_lean_states(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "tg_sha256_chunk_witnesses",
            REPOSITORY / "tools" / "tg_sha256_chunk_witnesses.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        source = lean_source()
        statement = (EVIDENCE / "statement.json").read_bytes()
        padded = module.pad(DOMAIN_PREFIX + statement)
        state = list(module.INITIAL)
        for index in range(len(padded) // 64):
            state = module.compress(
                state, padded[index * 64:(index + 1) * 64])
            if (index + 1) % 6 == 0 or index + 1 == len(padded) // 64:
                self.assertIn(module.state_literal(state), source)

        final = "".join(f"{word:08x}" for word in state)
        self.assertEqual(
            final, hashlib.sha256(DOMAIN_PREFIX + statement).hexdigest())


if __name__ == "__main__":
    unittest.main()
