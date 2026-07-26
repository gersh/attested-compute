#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Focused protocol tests for the two-pass Hurst residual campaign."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import unittest

from tg_verifier.campaign_io import canonical_json_bytes, load_json
from tg_verifier.hurst_residual_campaign import (
    ATOM_PROFILES,
    DEFAULT_SHARD_SPAN,
    DEFAULT_WORKER_GROUPS,
    HurstResidualCampaignError,
    REGISTERED_RESULT_SHA256,
    SOURCE_UPPER_EXCLUSIVE,
    UPSTREAM_COMMIT,
    command_for_shard,
    create_plan,
    finalize_campaign,
    grouped_shard_indices,
    ingest_receipt,
    initialize_campaign,
    reduce_summaries,
    run_phase,
    validate_runner_receipt,
    verify_campaign,
    write_registered_result,
)


FAKE_RUNNER = r'''#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

p = argparse.ArgumentParser()
p.add_argument("--lower", type=int, required=True)
p.add_argument("--upper", type=int, required=True)
p.add_argument("--segment-size", type=int, required=True)
p.add_argument("--mode", choices=("summary", "verify"), required=True)
p.add_argument("--incoming-mertens", type=int, default=0)
p.add_argument("--incoming-squarefree", type=int, default=0)
p.add_argument("--incoming-little-lower", type=int, default=0)
p.add_argument("--incoming-little-upper", type=int, default=0)
a = p.parse_args()
if os.environ.get("TG_HURST_TEST_OVERSIZED_STDOUT"):
    sys.stdout.buffer.write(b"x" * ((4 << 20) + 1))
    raise SystemExit(0)
if os.environ.get("TG_HURST_TEST_CANCEL_SIBLING"):
    if a.lower == 1:
        raise SystemExit("intentional first-child failure")
    time.sleep(5)
barrier = os.environ.get("TG_HURST_TEST_BARRIER")
if barrier:
    directory = Path(barrier)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"started-{a.lower}").touch()
    deadline = time.monotonic() + 5
    while len(list(directory.glob("started-*"))) < 2:
        if time.monotonic() >= deadline:
            raise SystemExit("campaign lock was held across runner execution")
        time.sleep(0.01)
thread_capture = os.environ.get("TG_HURST_THREAD_CAPTURE")
if thread_capture:
    directory = Path(thread_capture)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"threads-{a.lower}").write_text(
        ":".join(
            (
                os.environ.get("OMP_DYNAMIC", ""),
                os.environ.get("OMP_NUM_THREADS", ""),
                os.environ.get("OMP_PROC_BIND", ""),
                os.environ.get("OMP_PLACES", ""),
            )
        ),
        encoding="ascii",
    )
upper_exclusive = a.upper + 1
count = upper_exclusive - a.lower
delta = [((a.lower + count) % 3) - 1, count, -3 * count, 2 * count]
row_sha = hashlib.sha256(
    f"fake-mobius-v1:{a.lower}:{upper_exclusive}".encode("ascii")
).hexdigest()
incoming = [
    a.incoming_mertens,
    a.incoming_squarefree,
    a.incoming_little_lower,
    a.incoming_little_upper,
]
guards = {}
if a.mode == "verify":
    guards = {
        atom: {"lower": incoming, "upper": incoming, "witnesses": []}
        for atom in (
            "mertens-hurst",
            "cdem-squarefree",
            "platt-little-mertens-2-11",
            "platt-little-mertens-stronger",
        )
    }
print(json.dumps({
    "algorithm": "hurst-segmented-mobius-two-pass-v2",
    "mode": a.mode,
    "classification": "source-scale-shard-not-lean-proof",
    "upstream_commit": "fb47790c876c92690fce62990199ce961c5bdd72",
    "lower": a.lower,
    "upper_exclusive": upper_exclusive,
    "work_count": count,
    "segment_size": a.segment_size,
    "segments": (count + a.segment_size - 1) // a.segment_size,
    "row_encoding": "mu-plus-one-block-sha256-v1",
    "squarefree_threshold_endpoint_policy": "inclusive-value-and-right-limit-v2",
    "reduction_block_rows": 1048576,
    "row_sha256": row_sha,
    "state_components": ["M", "Q", "lm_lower_q96", "lm_upper_q96"],
    "delta": delta,
    "guards": guards,
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


class HurstResidualCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runner = self.root / "fake-runner.py"
        self.runner.write_text(FAKE_RUNNER, encoding="utf-8")
        self.runner.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.source = self.root / "tg_hurst_residual_shard.cpp"
        self.source.write_text("// bounded fake adapter source\n", encoding="utf-8")
        self.upstream = self.root / "HURST_MERTENS_UPSTREAM.json"
        self.upstream.write_text(
            json.dumps(
                {
                    "kind": "sparkinterval.pinned_upstream_source.v1",
                    "name": "test pinned closure",
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
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.output = self.root / "campaign"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initialize(self) -> None:
        result = initialize_campaign(
            runner=self.runner,
            runner_source=self.source,
            upstream_manifest=self.upstream,
            output_directory=self.output,
            shard_span=4,
            segment_size=13_860,
            domain_upper_exclusive=10,
            allow_bounded_test=True,
        )
        self.assertEqual((result.shard_count, result.mode), (3, "bounded_test"))

    def test_full_plan_is_exactly_ten_thousand_checkpoint_leaves(self) -> None:
        plan = create_plan(
            domain_upper_exclusive=SOURCE_UPPER_EXCLUSIVE,
            shard_span=DEFAULT_SHARD_SPAN,
            runner_sha256="1" * 64,
            source_sha256="2" * 64,
            upstream_manifest_sha256="3" * 64,
        )
        self.assertEqual(len(plan.shards), 10_000)
        self.assertEqual((plan.domain_lower, plan.domain_upper), (1, 10**16 + 1))
        self.assertEqual((plan.shards[0].lower, plan.shards[-1].upper), (1, 10**16 + 1))
        for left, right in zip(plan.shards, plan.shards[1:], strict=False):
            self.assertEqual(left.upper, right.lower)

    def test_bounded_plan_requires_an_explicit_nonproduction_flag(self) -> None:
        with self.assertRaisesRegex(HurstResidualCampaignError, "explicit"):
            create_plan(
                domain_upper_exclusive=10,
                shard_span=4,
                runner_sha256="1" * 64,
                source_sha256="2" * 64,
                upstream_manifest_sha256="3" * 64,
            )

    def test_production_supervisor_rejects_affine_prototype_receipts(self) -> None:
        import subprocess

        self.initialize()
        command = command_for_shard(self.output, phase="summary", shard_index=0)
        report = json.loads(
            subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
        )
        report["mode"] = "affine"
        with self.assertRaisesRegex(HurstResidualCampaignError, "wrong phase"):
            validate_runner_receipt(
                report,
                phase="summary",
                shard_lower=1,
                shard_upper=5,
                segment_size=13_860,
            )

    def test_worker_groups_partition_the_fixed_leaf_plan(self) -> None:
        self.initialize()
        groups = [
            grouped_shard_indices(
                self.output,
                group_index=index,
                group_count=2,
            )
            for index in range(2)
        ]
        self.assertEqual(groups, [(0, 2), (1,)])
        self.assertEqual(
            sorted(index for group in groups for index in group),
            [0, 1, 2],
        )
        self.assertEqual(DEFAULT_WORKER_GROUPS, 320)
        with self.assertRaisesRegex(HurstResidualCampaignError, "outside"):
            grouped_shard_indices(self.output, group_index=2, group_count=2)

    def test_supervisor_rejects_pre_v2_squarefree_threshold_semantics(self) -> None:
        import subprocess

        self.initialize()
        command = command_for_shard(self.output, phase="summary", shard_index=0)
        report = json.loads(
            subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
        )
        report["squarefree_threshold_endpoint_policy"] = "right-limit-only-v1"
        with self.assertRaisesRegex(
            HurstResidualCampaignError, "threshold endpoint policy"
        ):
            validate_runner_receipt(
                report,
                phase="summary",
                shard_lower=1,
                shard_upper=5,
                segment_size=13_860,
            )

    def test_two_pass_campaign_derives_inputs_and_builds_merkle_certificate(self) -> None:
        self.initialize()
        summary_result = run_phase(self.output, phase="summary")
        self.assertEqual(summary_result.summaries, 3)
        derived = reduce_summaries(self.output)
        self.assertEqual(derived["root_state"], [0, 0, 0, 0])
        self.assertEqual(
            derived["entries"][1]["incoming"], derived["entries"][0]["outgoing"]
        )
        verify_command = command_for_shard(self.output, phase="verify", shard_index=1)
        self.assertIn("--incoming-mertens", verify_command)
        verify_result = run_phase(self.output, phase="verify")
        self.assertEqual(verify_result.verifications, 3)
        final = finalize_campaign(self.output)
        self.assertTrue(final.complete)
        self.assertFalse(final.full_source_range)
        self.assertFalse(final.source_residuals_replayed)
        self.assertIsNotNone(final.certificate_root_sha256)
        self.assertEqual(len(list((self.output / "affine-leaves").glob("leaf-*.json"))), 3)
        certificate = load_json(self.output / "certificate.json", require_canonical=True)
        self.assertEqual(certificate["atom_profiles"], list(ATOM_PROFILES))
        self.assertFalse(certificate["full_source_range"])
        self.assertFalse(certificate["lean_atoms_discharged"])
        self.assertEqual(verify_campaign(self.output), final)

    def test_bounded_campaign_cannot_emit_registered_success(self) -> None:
        self.initialize()
        run_phase(self.output, phase="summary")
        reduce_summaries(self.output)
        run_phase(self.output, phase="verify")
        finalize_campaign(self.output)
        registered = self.root / "registered-result.txt"
        with self.assertRaisesRegex(HurstResidualCampaignError, "full-source"):
            write_registered_result(self.output, registered)
        self.assertFalse(registered.exists())

    def test_registered_result_constants_are_literal_true(self) -> None:
        self.assertEqual(
            REGISTERED_RESULT_SHA256,
            hashlib.sha256(b"true").hexdigest(),
        )

    def test_reducer_and_finalizer_reject_missing_leaves(self) -> None:
        self.initialize()
        run_phase(self.output, phase="summary", max_shards=2)
        with self.assertRaisesRegex(HurstResidualCampaignError, "incomplete"):
            reduce_summaries(self.output)
        run_phase(self.output, phase="summary")
        reduce_summaries(self.output)
        run_phase(self.output, phase="verify", max_shards=2)
        with self.assertRaisesRegex(HurstResidualCampaignError, "incomplete"):
            finalize_campaign(self.output)

    def test_disjoint_cluster_workers_run_outside_the_campaign_lock(self) -> None:
        self.initialize()
        barrier = self.root / "runner-barrier"
        with patch.dict(os.environ, {"TG_HURST_TEST_BARRIER": str(barrier)}):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        run_phase,
                        self.output,
                        phase="summary",
                        shard_indices=[index],
                    )
                    for index in (0, 1)
                ]
                for future in futures:
                    future.result(timeout=10)
        self.assertEqual(
            sorted(path.name for path in (self.output / "summary").glob("*.json")),
            ["receipt-00000000.json", "receipt-00000001.json"],
        )

    def test_local_worker_pool_is_parallel_and_bounds_openmp_threads(self) -> None:
        self.initialize()
        barrier = self.root / "pool-barrier"
        capture = self.root / "thread-capture"
        with patch.dict(
            os.environ,
            {
                "TG_HURST_TEST_BARRIER": str(barrier),
                "TG_HURST_THREAD_CAPTURE": str(capture),
                "OMP_NUM_THREADS": "99",
            },
        ):
            result = run_phase(
                self.output,
                phase="summary",
                workers=3,
                runner_threads=2,
            )
        self.assertEqual(result.summaries, 3)
        captures = sorted(capture.glob("threads-*"))
        self.assertEqual(len(captures), 3)
        values = [
            path.read_text(encoding="ascii").split(":")
            for path in captures
        ]
        self.assertEqual(
            [(dynamic, threads, binding) for dynamic, threads, binding, _ in values],
            [("FALSE", "2", "close")] * 3,
        )
        places = [
            set(int(item.strip("{}")) for item in placement.split(","))
            for _, _, _, placement in values
        ]
        self.assertEqual([len(value) for value in places], [2, 2, 2])
        self.assertEqual(len(set.union(*places)), 6)

    def test_parallel_schedule_preserves_both_passes_and_final_root(self) -> None:
        self.initialize()
        parallel = self.root / "parallel-campaign"
        initialize_campaign(
            runner=self.runner,
            runner_source=self.source,
            upstream_manifest=self.upstream,
            output_directory=parallel,
            shard_span=4,
            segment_size=13_860,
            domain_upper_exclusive=10,
            allow_bounded_test=True,
        )

        run_phase(self.output, phase="summary")
        run_phase(
            parallel,
            phase="summary",
            workers=3,
            runner_threads=1,
        )
        serial_summaries = sorted(
            path.read_bytes()
            for path in (self.output / "summary").glob("receipt-*.json")
        )
        parallel_summaries = sorted(
            path.read_bytes()
            for path in (parallel / "summary").glob("receipt-*.json")
        )
        self.assertEqual(serial_summaries, parallel_summaries)

        reduce_summaries(self.output)
        reduce_summaries(parallel)
        run_phase(self.output, phase="verify")
        run_phase(
            parallel,
            phase="verify",
            workers=3,
            runner_threads=1,
        )
        serial_verifications = sorted(
            path.read_bytes()
            for path in (self.output / "verify").glob("receipt-*.json")
        )
        parallel_verifications = sorted(
            path.read_bytes()
            for path in (parallel / "verify").glob("receipt-*.json")
        )
        self.assertEqual(serial_verifications, parallel_verifications)
        self.assertEqual(
            finalize_campaign(self.output).certificate_root_sha256,
            finalize_campaign(parallel).certificate_root_sha256,
        )

    def test_local_worker_counts_fail_closed(self) -> None:
        self.initialize()
        for value in (0, True):
            with self.subTest(workers=value):
                with self.assertRaisesRegex(
                    HurstResidualCampaignError, "workers"
                ):
                    run_phase(self.output, phase="summary", workers=value)
        for value in (0, True):
            with self.subTest(runner_threads=value):
                with self.assertRaisesRegex(
                    HurstResidualCampaignError, "runner threads"
                ):
                    run_phase(
                        self.output,
                        phase="summary",
                        runner_threads=value,
                    )

    def test_parallel_worker_pool_rejects_cpu_oversubscription(self) -> None:
        self.initialize()
        with patch(
            "tg_verifier.hurst_residual_campaign.os.sched_getaffinity",
            return_value={0, 1},
        ):
            for workers, runner_threads in ((3, 1), (1, 3)):
                with self.subTest(
                    workers=workers, runner_threads=runner_threads
                ):
                    with self.assertRaisesRegex(
                        HurstResidualCampaignError,
                        "available CPU affinity",
                    ):
                        run_phase(
                            self.output,
                            phase="summary",
                            workers=workers,
                            runner_threads=runner_threads,
                        )

    def test_completed_phase_does_not_require_worker_affinity(self) -> None:
        self.initialize()
        expected = run_phase(self.output, phase="summary")
        with patch(
            "tg_verifier.hurst_residual_campaign.os.sched_getaffinity",
            side_effect=OSError("affinity unavailable"),
        ):
            actual = run_phase(
                self.output,
                phase="summary",
                workers=2,
                runner_threads=20,
            )
        self.assertEqual(actual, expected)

    def test_runner_stdout_is_rejected_at_the_receipt_limit(self) -> None:
        self.initialize()
        with patch.dict(
            os.environ, {"TG_HURST_TEST_OVERSIZED_STDOUT": "1"}
        ):
            with self.assertRaisesRegex(
                HurstResidualCampaignError, "oversized receipt"
            ):
                run_phase(
                    self.output,
                    phase="summary",
                    shard_indices=[0],
                )
        self.assertFalse((self.output / "summary").exists())

    def test_failed_child_promptly_cancels_running_siblings(self) -> None:
        self.initialize()
        started = time.monotonic()
        with patch.dict(
            os.environ, {"TG_HURST_TEST_CANCEL_SIBLING": "1"}
        ):
            with self.assertRaisesRegex(
                HurstResidualCampaignError, "runner returned"
            ):
                run_phase(
                    self.output,
                    phase="summary",
                    shard_indices=[0, 1],
                    workers=2,
                    runner_threads=1,
                )
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse((self.output / "summary").exists())

    def test_verify_row_digest_must_match_its_summary(self) -> None:
        self.initialize()
        run_phase(self.output, phase="summary")
        reduce_summaries(self.output)
        command = command_for_shard(self.output, phase="verify", shard_index=0)
        import subprocess

        raw = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
        report = json.loads(raw)
        report["row_sha256"] = "f" * 64
        changed = self.root / "changed.json"
        changed.write_bytes((json.dumps(report, sort_keys=True) + "\n").encode("utf-8"))
        with self.assertRaisesRegex(HurstResidualCampaignError, "row SHA"):
            ingest_receipt(
                self.output,
                phase="verify",
                shard_index=0,
                receipt_path=changed,
            )

    def test_captured_source_and_runner_are_rechecked(self) -> None:
        self.initialize()
        captured = self.output / "captured-hurst-residual-shard.cpp"
        captured.write_text("// tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(HurstResidualCampaignError, "identity changed"):
            verify_campaign(self.output)

    def test_root_derived_singleton_guard_cannot_be_substituted(self) -> None:
        self.initialize()
        run_phase(self.output, phase="summary")
        reduce_summaries(self.output)
        command = command_for_shard(self.output, phase="verify", shard_index=1)
        import subprocess

        raw = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
        report = json.loads(raw)
        report["guards"][ATOM_PROFILES[0]]["lower"][0] += 1
        changed = self.root / "wrong-guard.json"
        changed.write_bytes(canonical_json_bytes(report))
        with self.assertRaisesRegex(HurstResidualCampaignError, "root-derived"):
            ingest_receipt(
                self.output,
                phase="verify",
                shard_index=1,
                receipt_path=changed,
            )


if __name__ == "__main__":
    unittest.main()
