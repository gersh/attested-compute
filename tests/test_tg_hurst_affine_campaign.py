#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed tests for the one-pass Hurst affine supervisor."""

from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from tg_verifier.campaign_io import canonical_json_bytes, load_json
from tg_verifier.hurst_affine_campaign import (
    DEFAULT_WORKER_GROUPS,
    FINAL_NAME,
    HurstAffineCampaignError,
    SCAN_NAME,
    SOURCE_UPPER_EXCLUSIVE,
    UPSTREAM_COMMIT,
    command_for_shard,
    create_plan,
    finalize_campaign,
    grouped_shard_indices,
    ingest_receipt,
    initialize_campaign,
    run_shards,
    validate_affine_runner_receipt,
    verify_campaign,
)


FAKE_RUNNER = r'''#!/usr/bin/env python3
import argparse
import hashlib
import json

p = argparse.ArgumentParser()
p.add_argument("--lower", type=int, required=True)
p.add_argument("--upper", type=int, required=True)
p.add_argument("--segment-size", type=int, required=True)
p.add_argument("--mode", choices=("affine",), required=True)
a = p.parse_args()
upper_exclusive = a.upper + 1
count = upper_exclusive - a.lower
wide_i64_lo = -4000000000000000000
wide_i64_hi = 4000000000000000000
wide_i128 = 1 << 120
wide_lower = [wide_i64_lo, wide_i64_lo, -wide_i128, -wide_i128]
wide_upper = [wide_i64_hi, wide_i64_hi, wide_i128, wide_i128]

def guard(components):
    return {
        "lower": list(wide_lower),
        "upper": list(wide_upper),
        "witnesses": [
            {
                "component": component,
                "lower_n": 0,
                "lower_side": "none",
                "upper_n": 0,
                "upper_side": "none",
            }
            for component in components
        ],
    }

print(json.dumps({
    "algorithm": "hurst-segmented-mobius-two-pass-v2",
    "mode": "affine",
    "classification": "source-scale-shard-not-lean-proof",
    "upstream_commit": "fb47790c876c92690fce62990199ce961c5bdd72",
    "lower": a.lower,
    "upper_exclusive": upper_exclusive,
    "work_count": count,
    "segment_size": a.segment_size,
    "segments": (count + a.segment_size - 1) // a.segment_size,
    "row_encoding": "mu-plus-one-block-sha256-v1",
    "squarefree_threshold_endpoint_policy":
        "inclusive-value-and-right-limit-v2",
    "reduction_block_rows": 1048576,
    "row_sha256": hashlib.sha256(
        f"fake-affine-mobius-v1:{a.lower}:{upper_exclusive}".encode("ascii")
    ).hexdigest(),
    "state_components": ["M", "Q", "lm_lower_q96", "lm_upper_q96"],
    "delta": [0, count, -count, count],
    "guards": {
        "mertens-hurst": guard([0]),
        "cdem-squarefree": guard([1]),
        "platt-little-mertens-2-11": guard([2, 3]),
        "platt-little-mertens-stronger": guard([2, 3]),
    },
    "exact_fallbacks": {
        "mertens_hurst": 0,
        "squarefree": 0,
        "little_mertens_2_11": 0,
        "little_mertens_stronger": 0,
    },
    "accepted": True,
    "elapsed_seconds": 0,
    "execution_attested": False,
    "lean_atom_discharged": False,
}, sort_keys=True))
'''


class HurstAffineCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runner = self.root / "fake-affine-runner.py"
        self.runner.write_text(FAKE_RUNNER, encoding="utf-8")
        self.runner.chmod(
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        )
        self.source = self.root / "tg_hurst_residual_shard.cpp"
        self.source.write_text("// bounded fake affine source\n", encoding="utf-8")
        self.upstream = self.root / "HURST_MERTENS_UPSTREAM.json"
        self.upstream.write_bytes(
            canonical_json_bytes(
                {
                    "kind": "sparkinterval.pinned_upstream_source.v1",
                    "name": "bounded fake closure",
                    "repository": "https://example.invalid/upstream",
                    "commit": UPSTREAM_COMMIT,
                    "license": "MIT",
                    "files": [
                        {
                            "path": "sieve/SegmentedMobiusSieve.h",
                            "sha256": "1" * 64,
                            "size_bytes": 1,
                        }
                    ],
                }
            )
        )
        self.output = self.root / "affine-campaign"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initialize(
        self, *, upper: int = 50, shard_span: int = 20
    ) -> None:
        result = initialize_campaign(
            runner=self.runner,
            runner_source=self.source,
            upstream_manifest=self.upstream,
            output_directory=self.output,
            shard_span=shard_span,
            segment_size=13_860,
            domain_upper_exclusive=upper,
            allow_bounded_test=True,
        )
        self.assertEqual(result.mode, "bounded_test")

    def produce(self, index: int) -> dict:
        completed = subprocess.run(
            command_for_shard(self.output, shard_index=index),
            check=True,
            stdout=subprocess.PIPE,
        )
        return json.loads(completed.stdout)

    def ingest_report(self, index: int, report: dict) -> None:
        path = self.root / f"incoming-{index}.json"
        path.write_bytes(canonical_json_bytes(report))
        ingest_receipt(
            self.output, shard_index=index, receipt_path=path
        )

    def test_full_plan_retains_exact_ten_thousand_leaf_ranges(self) -> None:
        plan = create_plan(
            domain_upper_exclusive=SOURCE_UPPER_EXCLUSIVE,
            shard_span=10**12,
            runner_sha256="1" * 64,
            source_sha256="2" * 64,
            upstream_manifest_sha256="3" * 64,
        )
        self.assertEqual(len(plan.shards), 10_000)
        self.assertEqual(
            (plan.domain_lower, plan.domain_upper),
            (1, 10**16 + 1),
        )
        self.assertTrue(
            all(
                left.upper == right.lower
                for left, right in zip(plan.shards, plan.shards[1:])
            )
        )

    def test_one_pass_finalize_and_replay_are_explicitly_conditional(self) -> None:
        self.initialize()
        partial = run_shards(
            self.output, max_shards=1, workers=1
        )
        self.assertEqual(partial.affine_receipts, 1)
        self.assertFalse(partial.complete)
        complete_receipts = run_shards(
            self.output, workers=2, runner_threads=1
        )
        self.assertEqual(
            complete_receipts.affine_receipts,
            complete_receipts.shard_count,
        )
        result = finalize_campaign(self.output)
        replay = verify_campaign(self.output)
        self.assertEqual(result, replay)
        self.assertTrue(result.complete)
        self.assertTrue(result.all_root_derived_inputs_in_all_atom_guards)
        self.assertFalse(result.full_source_range)
        self.assertFalse(result.source_rows_replayed_independently)
        self.assertTrue(result.physical_row_realization_pending)
        self.assertFalse(result.execution_attested)
        self.assertFalse(result.lean_atoms_discharged)
        final = load_json(self.output / FINAL_NAME, require_canonical=True)
        self.assertEqual(
            final["implication_scope"],
            "conditional_on_each_retained_worker_receipt_realizing_its_"
            "committed_mobius_rows_deltas_and_exact_per_atom_guards",
        )
        self.assertFalse(final["source_rows_replayed_independently"])
        self.assertFalse(final["execution_attested"])
        self.assertFalse(final["lean_atoms_discharged"])

    def test_root_scan_rejects_one_atom_guard_even_when_others_accept(self) -> None:
        self.initialize()
        for index in range(3):
            report = self.produce(index)
            if index == 1:
                guard = report["guards"]["mertens-hurst"]
                guard["lower"][0] = 1
                guard["witnesses"][0]["lower_n"] = 33
                guard["witnesses"][0]["lower_side"] = "integer"
            self.ingest_report(index, report)
        with self.assertRaisesRegex(
            HurstAffineCampaignError,
            "violates mertens-hurst guard at shard 1",
        ):
            finalize_campaign(self.output)

    def test_missing_receipt_and_malformed_witness_fail_closed(self) -> None:
        self.initialize()
        report = self.produce(0)
        report["guards"]["mertens-hurst"]["witnesses"][0][
            "lower_n"
        ] = 7
        with self.assertRaisesRegex(
            HurstAffineCampaignError, "absent witness"
        ):
            validate_affine_runner_receipt(
                report,
                shard_lower=1,
                shard_upper=21,
                segment_size=13_860,
            )
        self.ingest_report(0, self.produce(0))
        with self.assertRaisesRegex(
            HurstAffineCampaignError, "incomplete"
        ):
            finalize_campaign(self.output)

    def test_independent_replay_detects_scan_leaf_and_receipt_tampering(self) -> None:
        self.initialize()
        run_shards(self.output, workers=1)
        finalize_campaign(self.output)

        scan_path = self.output / SCAN_NAME
        original_scan = scan_path.read_bytes()
        scan = json.loads(original_scan)
        scan["entries"][0]["outgoing"][1] += 1
        scan_path.write_bytes(canonical_json_bytes(scan))
        with self.assertRaisesRegex(
            HurstAffineCampaignError, "scan differs"
        ):
            verify_campaign(self.output)
        scan_path.write_bytes(original_scan)

        leaf_path = self.output / "affine-leaves.json"
        original_leaf = leaf_path.read_bytes()
        leaf = json.loads(original_leaf)
        leaf["leaves"][0]["row_root_sha256"] = "f" * 64
        leaf_path.write_bytes(canonical_json_bytes(leaf))
        with self.assertRaisesRegex(
            HurstAffineCampaignError, "leaf bundle differs"
        ):
            verify_campaign(self.output)
        leaf_path.write_bytes(original_leaf)

        receipt_path = (
            self.output / "affine-receipts" / "receipt-00000000.json"
        )
        receipt = json.loads(receipt_path.read_bytes())
        receipt["row_sha256"] = "e" * 64
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        with self.assertRaisesRegex(
            HurstAffineCampaignError, "differs"
        ):
            verify_campaign(self.output)

    def test_grouping_is_disjoint_and_covers_every_exact_leaf(self) -> None:
        self.initialize()
        groups = [
            grouped_shard_indices(
                self.output, group_index=index, group_count=2
            )
            for index in range(2)
        ]
        self.assertEqual(groups, [(0, 2), (1,)])
        self.assertEqual(
            sorted(index for group in groups for index in group),
            [0, 1, 2],
        )
        self.assertEqual(DEFAULT_WORKER_GROUPS, 320)


if __name__ == "__main__":
    unittest.main()
