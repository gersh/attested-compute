#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the literal deterministic binary-Goldbach replay."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tg_verifier import binary_goldbach_campaign as bg
from tg_verifier.goldbach import is_prime_bounded


class WitnessTests(unittest.TestCase):
    def test_every_small_even_has_an_exact_pair(self) -> None:
        for even in range(4, 10_002, 2):
            left, right = bg.find_witness(even)
            self.assertEqual(left + right, even)
            self.assertTrue(is_prime_bounded(left))
            self.assertTrue(is_prime_bounded(right))

    def test_domain_fails_closed(self) -> None:
        for bad in (2, 5, True, 1 << 64):
            with self.subTest(bad=bad), self.assertRaises(bg.BinaryGoldbachError):
                bg.find_witness(bad)  # type: ignore[arg-type]


class ResumableCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.parameters = bg.Parameters(
            first_even=4,
            last_even=200,
            evens_per_chunk=17,
            mode="bounded_test",
        )
        bg.initialize(self.directory, self.parameters)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _finish(self) -> bg.State:
        state = bg.replay(self.directory)
        while state.completed_chunks < state.parameters.chunk_count:
            state = bg.produce_next(self.directory, state)
        return state

    def test_chunk_chain_replays_every_witness(self) -> None:
        state = self._finish()
        replayed = bg.replay(self.directory)
        self.assertEqual(replayed, state)
        self.assertEqual(replayed.checked_evens, self.parameters.even_count)

    def test_changed_transcript_fails_replay(self) -> None:
        self._finish()
        path = self.directory / "chunks" / bg.chunk_filename(0)
        path.write_bytes(path.read_bytes().replace(b'"transcript_sha256":"', b'"transcript_sha256":"0', 1))
        with self.assertRaises(bg.BinaryGoldbachError):
            bg.replay(self.directory)

    def test_changed_implementation_identity_fails_replay(self) -> None:
        manifest = self.directory / "manifest.json"
        value = json.loads(manifest.read_bytes())
        value["implementation_sha256"] = "0" * 64
        manifest.write_bytes(bg._canonical(value))
        with self.assertRaisesRegex(bg.BinaryGoldbachError, "source identity"):
            bg.replay(self.directory)

    def test_bounded_run_cannot_be_promoted(self) -> None:
        self._finish()
        with self.assertRaisesRegex(bg.BinaryGoldbachError, "bounded test"):
            bg.verify_complete(self.directory)


if __name__ == "__main__":
    unittest.main()
