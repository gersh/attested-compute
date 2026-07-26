# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import textwrap
import unittest

from tg_verifier.platt_zeta_campaign import (
    FLINT_COMMIT,
    PLATT_ENGINE,
    SOURCE_COUNT,
    SOURCE_SENTINEL,
    SOURCE_UPPER_EXCLUSIVE,
    PlattZetaCampaignError,
    _merkle_root,
    _parse_arf_dump,
    campaign_status,
    create_plan,
    finalize_campaign,
    initialize_campaign,
    replay_shard,
    run_shard,
    shard_range,
    validate_plan,
    validate_stream_report,
)


ROOT = Path(__file__).resolve().parents[1]
ZERO_DIGEST = "0" * 64


def bounded_plan(**changes: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "runner_sha256": ZERO_DIGEST,
        "runner_size": 1,
        "source_sha256": ZERO_DIGEST,
        "source_size": 1,
        "upstream_sha256": ZERO_DIGEST,
        "source_upper_exclusive": 10_051,
        "shard_span": 20,
        "allow_bounded_test": True,
    }
    arguments.update(changes)
    return create_plan(**arguments)  # type: ignore[arg-type]


def stream_report(first: int, last: int) -> dict[str, object]:
    return {
        "schema": "sparkinterval.tg.platt-zeta-shard.v1",
        "engine": PLATT_ENGINE,
        "first_index": first,
        "last_index": last,
        "record_count": last - first + 1,
        "micro_batch": 4096,
        "flint_calls": 1,
        "precision_bits": 96,
        "flint_threads": 1,
        "interval_encoding": "flint-3.6-dump-str",
        "interval_rows_sha256": ZERO_DIGEST,
        "first_lower": f"{2 * first:x} 0",
        "first_upper": f"{2 * first + 1:x} 0",
        "last_lower": f"{2 * last:x} 0",
        "last_upper": f"{2 * last + 1:x} 0",
        "positive_finite_disjoint_open_intervals": True,
        "critical_line_certified": True,
        "counted_with_multiplicity": True,
        "simplicity_assumed": False,
        "included_cutoff_checked": first <= SOURCE_COUNT <= last,
        "sentinel_cutoff_checked": first <= SOURCE_SENTINEL <= last,
        "flint_version": "3.6.0",
        "flint_commit": FLINT_COMMIT,
        "elapsed_milliseconds": 0,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }


class PlattPlanTests(unittest.TestCase):
    def test_full_source_formula(self) -> None:
        plan = create_plan(
            runner_sha256=ZERO_DIGEST,
            runner_size=1,
            source_sha256=ZERO_DIGEST,
            source_size=1,
            upstream_sha256=ZERO_DIGEST,
        )
        self.assertEqual(plan["mode"], "full_source")
        self.assertEqual(plan["geometry"]["shard_count"], 1_236_316)
        self.assertEqual(shard_range(plan, 0), (10_000, 10_010_000))
        self.assertEqual(
            shard_range(plan, 1_236_315),
            (12_363_150_010_000, SOURCE_UPPER_EXCLUSIVE),
        )

    def test_bounded_formula_has_no_materialized_range_table(self) -> None:
        plan = bounded_plan()
        self.assertEqual(plan["geometry"]["shard_count"], 3)
        self.assertEqual(
            [shard_range(plan, index) for index in range(3)],
            [(10_000, 10_020), (10_020, 10_040), (10_040, 10_051)],
        )
        self.assertNotIn("shards", plan)

    def test_tampered_plan_digest_fails(self) -> None:
        plan = bounded_plan()
        plan["source"]["source_upper_exclusive"] = 10_052
        with self.assertRaisesRegex(PlattZetaCampaignError, "digest"):
            validate_plan(plan)

    def test_arf_dump_is_exact_dyadic(self) -> None:
        self.assertEqual(_parse_arf_dump("3 -2", "x"), 3 / 4)
        self.assertEqual(_parse_arf_dump("a 3", "x"), 80)

    def test_multiplicity_and_simplicity_policy_is_fail_closed(self) -> None:
        report = stream_report(10_000, 10_001)
        validate_stream_report(
            report,
            engine=PLATT_ENGINE,
            first_index=10_000,
            last_index=10_001,
            micro_batch=4096,
            precision_bits=96,
            flint_threads=1,
        )
        report["simplicity_assumed"] = True
        with self.assertRaisesRegex(PlattZetaCampaignError, "multiplicity"):
            validate_stream_report(
                report,
                engine=PLATT_ENGINE,
                first_index=10_000,
                last_index=10_001,
                micro_batch=4096,
                precision_bits=96,
                flint_threads=1,
            )

    def test_merkle_tree_is_order_sensitive(self) -> None:
        a = "1" * 64
        b = "2" * 64
        self.assertNotEqual(_merkle_root([a, b]), _merkle_root([b, a]))
        self.assertEqual(_merkle_root([a]), _merkle_root([a]))


class PlattCampaignIntegrationTests(unittest.TestCase):
    def test_bounded_fake_runner_finalize_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "fake-runner"
            runner.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import hashlib, json, sys
                    args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
                    first = int(args['--first-index'])
                    count = int(args['--count'])
                    last = first + count - 1
                    report = {{
                      'schema': 'sparkinterval.tg.platt-zeta-shard.v1',
                      'engine': 'flint-platt-local-isolation-v1',
                      'first_index': first, 'last_index': last,
                      'record_count': count,
                      'micro_batch': int(args['--micro-batch']),
                      'flint_calls': 1,
                      'precision_bits': int(args['--precision']),
                      'flint_threads': int(args['--threads']),
                      'interval_encoding': 'flint-3.6-dump-str',
                      'interval_rows_sha256': '0' * 64,
                      'first_lower': format(2*first, 'x') + ' 0',
                      'first_upper': format(2*first+1, 'x') + ' 0',
                      'last_lower': format(2*last, 'x') + ' 0',
                      'last_upper': format(2*last+1, 'x') + ' 0',
                      'positive_finite_disjoint_open_intervals': True,
                      'critical_line_certified': True,
                      'counted_with_multiplicity': True,
                      'simplicity_assumed': False,
                      'included_cutoff_checked': False,
                      'sentinel_cutoff_checked': False,
                      'flint_version': '3.6.0',
                      'flint_commit': '{FLINT_COMMIT}',
                      'elapsed_milliseconds': 7,
                      'execution_attested': False,
                      'lean_atom_discharged': False,
                      'accepted': True,
                    }}
                    print(json.dumps(report, sort_keys=True, separators=(',', ':')))
                    """
                ),
                encoding="utf-8",
            )
            runner.chmod(0o755)
            campaign = root / "campaign"
            initialize_campaign(
                runner=runner,
                runner_source=ROOT / "reference" / "tg_platt_zeta_shard.cpp",
                upstream_manifest=ROOT / "specifications" / "FLINT_3_6_PLATT_UPSTREAM.json",
                output_directory=campaign,
                source_upper_exclusive=10_005,
                shard_span=2,
                allow_bounded_test=True,
            )
            for index in range(3):
                run_shard(campaign, index)
            status = finalize_campaign(campaign)
            self.assertTrue(status["complete"])
            self.assertTrue(status["final_ready"])
            self.assertRegex(status["merkle_root_sha256"], r"^[0-9a-f]{64}$")
            replay = replay_shard(campaign, 1)
            self.assertTrue(replay["accepted"])
            self.assertEqual(campaign_status(campaign), status)


if __name__ == "__main__":
    unittest.main()
