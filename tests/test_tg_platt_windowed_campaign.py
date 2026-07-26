# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap
import unittest

from tg_verifier.platt_windowed_campaign import (
    FULL_BLOCK_COUNT,
    FULL_COVERAGE_UPPER,
    SOURCE_HEIGHT,
    SOURCE_LOWER,
    SOURCE_LOWER_COUNT,
    STEP,
    PlattWindowedCampaignError,
    campaign_status,
    create_plan,
    finalize_campaign,
    initialize_campaign,
    parse_transcript,
    replay_shard,
    run_shard,
    shard_block_range,
    validate_plan,
)


ROOT = Path(__file__).resolve().parents[1]
ZERO = "0" * 64


class PlattWindowedGeometryTests(unittest.TestCase):
    def test_full_geometry_strictly_covers_source_height(self) -> None:
        self.assertEqual(FULL_BLOCK_COUNT, 2_966_443_783)
        self.assertEqual(FULL_COVERAGE_UPPER, 3_000_175_333_264)
        self.assertEqual(FULL_COVERAGE_UPPER - SOURCE_HEIGHT, 464)
        plan = create_plan(
            runner_sha256=ZERO,
            runner_size=1,
            source_manifest_sha256=ZERO,
            source_manifest_size=1,
        )
        validate_plan(plan)
        self.assertEqual(plan["mode"], "full_source_high_range")
        self.assertTrue(plan["claim"]["lower_prefix_required"])

    def test_bounded_geometry_requires_explicit_test_mode(self) -> None:
        with self.assertRaisesRegex(PlattWindowedCampaignError, "bounded"):
            create_plan(
                runner_sha256=ZERO,
                runner_size=1,
                source_manifest_sha256=ZERO,
                source_manifest_size=1,
                block_count=3,
            )
        plan = create_plan(
            runner_sha256=ZERO,
            runner_size=1,
            source_manifest_sha256=ZERO,
            source_manifest_size=1,
            blocks_per_shard=2,
            block_count=3,
            allow_bounded_test=True,
        )
        self.assertEqual(shard_block_range(plan, 0), (0, 2))
        self.assertEqual(shard_block_range(plan, 1), (2, 3))

    def test_plan_tampering_fails(self) -> None:
        plan = create_plan(
            runner_sha256=ZERO,
            runner_size=1,
            source_manifest_sha256=ZERO,
            source_manifest_size=1,
        )
        plan["claim"]["coverage_upper"] += STEP
        with self.assertRaisesRegex(PlattWindowedCampaignError, "digest"):
            validate_plan(plan)


class PlattWindowedTranscriptTests(unittest.TestCase):
    def test_known_source_block(self) -> None:
        output = textwrap.dedent(
            """\
            Command line:- checker 128 10000000000 1 1008
            looking for 32130161714-32130158315=3399 zeros
            All 3399 zeros found in region 10000000000.000000 to 10000001008.000000 using stat points.
            """
        )
        parsed = parse_transcript(output, first_block=0, block_count=1)
        self.assertEqual(parsed["first_count"], SOURCE_LOWER_COUNT)
        self.assertEqual(parsed["last_count"], 32_130_161_714)

    def test_exit_zero_failure_text_is_rejected(self) -> None:
        output = textwrap.dedent(
            """\
            looking for 32130161714-32130158315=3399 zeros
            Unknown at start of data.
            Missed All/All zeros in region 10000000000.000000 to 10000001008.000000.
            """
        )
        with self.assertRaisesRegex(PlattWindowedCampaignError, "failure token"):
            parse_transcript(output, first_block=0, block_count=1)

    def test_noncontiguous_turing_chain_is_rejected(self) -> None:
        output = textwrap.dedent(
            """\
            looking for 32130158322-32130158315=7 zeros
            All 7 zeros found in region 10000000000.000000 to 10000001008.000000 using stat points.
            looking for 32130158330-32130158323=7 zeros
            All 7 zeros found in region 10000001008.000000 to 10000002016.000000 using stat points.
            """
        )
        with self.assertRaisesRegex(PlattWindowedCampaignError, "not contiguous"):
            parse_transcript(output, first_block=0, block_count=2)


class PlattWindowedIntegrationTests(unittest.TestCase):
    def test_bounded_campaign_run_replay_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "fake-windowed-checker"
            runner.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import sys
                    precision, start, iterations, step = map(int, sys.argv[1:])
                    assert precision == 128 and step == {STEP}
                    block = (start - {SOURCE_LOWER}) // step
                    count = {SOURCE_LOWER_COUNT} + 7 * block
                    for offset in range(iterations):
                        lower = start + offset * step
                        upper = lower + step
                        maximum = count + 7
                        print(f"looking for {{maximum}}-{{count}}=7 zeros")
                        print(f"All 7 zeros found in region {{lower:.6f}} to {{upper:.6f}} using stat points.")
                        count = maximum
                    """
                ),
                encoding="utf-8",
            )
            runner.chmod(0o755)
            campaign = root / "campaign"
            plan = initialize_campaign(
                output_directory=campaign,
                runner=runner,
                source_manifest=ROOT
                / "specifications"
                / "PLATT_PT21_WINDOWED_UPSTREAM.json",
                blocks_per_shard=2,
                block_count=3,
                allow_bounded_test=True,
            )
            self.assertEqual(plan["geometry"]["shard_count"], 2)
            run_shard(campaign, runner, 0)
            run_shard(campaign, runner, 1)
            replay = replay_shard(campaign, runner, 0)
            self.assertTrue(replay["semantic_replay_identical"])
            status = campaign_status(campaign)
            self.assertTrue(status["complete"])
            self.assertFalse(status["source_claim_ready"])
            final = finalize_campaign(campaign)
            self.assertTrue(final["all_high_range_zeros_on_critical_line"])
            self.assertEqual(final["last_count"], SOURCE_LOWER_COUNT + 21)
            self.assertTrue(final["lower_prefix_required"])
            self.assertFalse(final["source_claim_ready"])
            self.assertFalse(final["lean_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
