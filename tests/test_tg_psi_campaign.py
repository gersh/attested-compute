# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tg_verifier.psi_campaign import (
    SOURCE_EVENT_COUNT,
    PsiCampaignError,
    replay_campaign,
    run_campaign,
    verify_campaign,
)


# pi(floor((10^13)^(1/k))) for k=1..43.  The k=1 value is the published
# exact pi(10^13); every later cutoff is at most 3,162,277 and is cheaply
# reproducible with an ordinary sieve.
SOURCE_POWER_PRIME_COUNTS = (
    346_065_536_839,
    227_647, 2_417, 275, 78, 34, 20, 13, 9, 8, 6, 5, 4, 4, 4, 3,
    3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
)


class PsiCampaignTests(unittest.TestCase):
    def test_exact_source_event_count(self) -> None:
        self.assertEqual(len(SOURCE_POWER_PRIME_COUNTS), 43)
        self.assertEqual(sum(SOURCE_POWER_PRIME_COUNTS), SOURCE_EVENT_COUNT)

        # Independently reproduce every k>=2 event without relying on a
        # prime-counting package or the pi(10^13) table entry.
        limit = 3_162_277
        sieve = bytearray(b"\x01") * (limit + 1)
        sieve[:2] = b"\x00\x00"
        for prime in range(2, int(limit**0.5) + 1):
            if sieve[prime]:
                start = prime * prime
                sieve[start::prime] = b"\x00" * (((limit - start) // prime) + 1)
        higher_powers = 0
        endpoint = 10**13
        for prime, is_prime in enumerate(sieve):
            if not is_prime:
                continue
            power = prime * prime
            while power <= endpoint:
                higher_powers += 1
                power *= prime
        self.assertEqual(higher_powers, 230_567)
        self.assertEqual(346_065_536_839 + higher_powers, SOURCE_EVENT_COUNT)

    def test_run_resume_structure_and_fresh_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run_campaign(
                root,
                chunk_span=200,
                scale_bits=64,
                series_terms=32,
                segment_size=61,
                max_chunks=1,
            )
            self.assertEqual(first.completed_upper, 201)
            self.assertTrue(first.locally_supervised_execution)
            structural = verify_campaign(root)
            self.assertEqual(structural.receipts, 1)
            self.assertFalse(structural.fresh_arithmetic_replay)
            replayed = replay_campaign(root)
            self.assertTrue(replayed.fresh_arithmetic_replay)
            second = run_campaign(
                root,
                chunk_span=200,
                scale_bits=64,
                series_terms=32,
                segment_size=61,
                max_chunks=1,
            )
            self.assertEqual(second.completed_upper, 401)
            self.assertEqual(second.receipts, 2)
            prefix_replay = replay_campaign(root, max_chunks=1)
            self.assertFalse(prefix_replay.fresh_arithmetic_replay)
            complete_replay = replay_campaign(root, max_chunks=2)
            self.assertTrue(complete_replay.fresh_arithmetic_replay)

    def test_resume_rejects_changed_arithmetic_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_campaign(
                root,
                chunk_span=100,
                scale_bits=64,
                series_terms=32,
                segment_size=31,
                max_chunks=1,
            )
            with self.assertRaisesRegex(PsiCampaignError, "configuration"):
                run_campaign(
                    root,
                    chunk_span=101,
                    scale_bits=64,
                    series_terms=32,
                    segment_size=31,
                    max_chunks=1,
                )


if __name__ == "__main__":
    unittest.main()
