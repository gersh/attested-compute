# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np

from tg_verifier.mobius_segmented_sieve_roster import (
    U16_LE,
    generate,
    verify,
)


class MobiusSegmentedSieveRosterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.codes = root / "factors.u16le"
        self.roster = root / "primes.u32le"
        self.report = generate(30, self.codes, self.roster, chunk_rows=7)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_known_roster_and_shape(self) -> None:
        self.assertEqual(self.report.base_prime_count, 3)
        self.assertEqual(self.report.factor_code_count, 29)
        self.assertEqual(self.report.factor_code_bytes, 58)
        self.assertEqual(self.report.roster_count, 10)
        values = np.fromfile(self.roster, dtype="<u4").tolist()
        self.assertEqual(
            values, [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        )

    def test_missing_composite_strike_is_rejected(self) -> None:
        codes = np.memmap(self.codes, dtype=U16_LE, mode="r+")
        codes[9 - 2] = 0
        codes.flush()
        del codes
        with self.assertRaisesRegex(ValueError, "roster|strike"):
            verify(30, self.codes, self.roster, chunk_rows=7)

    def test_false_prime_mark_is_rejected(self) -> None:
        codes = np.memmap(self.codes, dtype=U16_LE, mode="r+")
        codes[7 - 2] = 2
        codes.flush()
        del codes
        with self.assertRaisesRegex(ValueError, "does not divide"):
            verify(30, self.codes, self.roster, chunk_rows=7)

    def test_wrong_factor_is_rejected(self) -> None:
        codes = np.memmap(self.codes, dtype=U16_LE, mode="r+")
        codes[9 - 2] = 2
        codes.flush()
        del codes
        with self.assertRaisesRegex(ValueError, "does not divide"):
            verify(30, self.codes, self.roster, chunk_rows=7)

    def test_truncation_is_rejected(self) -> None:
        self.codes.write_bytes(self.codes.read_bytes()[:-2])
        with self.assertRaisesRegex(ValueError, "wrong byte length"):
            verify(30, self.codes, self.roster, chunk_rows=7)

    def test_roster_mutation_is_rejected(self) -> None:
        roster = np.memmap(self.roster, dtype="<u4", mode="r+")
        roster[-1] = 23
        roster.flush()
        del roster
        with self.assertRaisesRegex(ValueError, "survivor list"):
            verify(30, self.codes, self.roster, chunk_rows=7)


if __name__ == "__main__":
    unittest.main()
