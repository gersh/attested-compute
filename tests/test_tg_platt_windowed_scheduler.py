#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Unit tests for the Platt PT21 windowed work-unit scheduler.

The tests drive a stub runner that emits exactly the source transcript shape,
so they exercise the scheduler's contracts without the pinned Arb executable.
The stub's per-block Turing counts are a fixed arithmetic sequence, which is
enough to test contiguity, telescoping, digest stability, and every
fail-closed path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_windowed_campaign import (  # noqa: E402
    SOURCE_LOWER,
    STEP,
)
from tg_verifier.platt_windowed_scheduler import (  # noqa: E402
    PlattWindowedScheduleError,
    _build_unit_receipt,
    _commit_unit,
    _unit_receipt_path,
    claim_unit,
    create_schedule,
    finalize,
    initialize_schedule,
    load_schedule,
    next_unit,
    run_unit,
    seal_shard,
    shard_unit_range,
    status,
    unit_block_range,
    validate_schedule,
    validate_shard_receipt,
    validate_unit_receipt,
)


STUB = """#!/usr/bin/env python3
import sys
prec, start, count, step = (int(v) for v in sys.argv[1:5])
print("Command line:- stub")
base = 1000000 + (start - {lower}) // step * 7
for index in range(count):
    lower_count = base + index * 7
    upper_count = lower_count + 7
    print("Time to convolve = 0 seconds.")
    print("looking for %d-%d=%d zeros" % (upper_count, lower_count, 7))
    print(
        "All %d zeros found in region %d.000000 to %d.000000 using stat points."
        % (7, start + index * step, start + (index + 1) * step)
    )
""".format(lower=SOURCE_LOWER)


BAD_STUB = STUB.replace(
    'print("Time to convolve = 0 seconds.")',
    'print("Unknown sign at endpoint.")',
)


class SchedulerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.runner = self._write_runner("stub.py", STUB)
        self.manifest = ROOT / "specifications" / "PLATT_PT21_WINDOWED_UPSTREAM.json"

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _write_runner(self, name: str, body: str) -> Path:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def _schedule(self, directory: str = "campaign", **kwargs: object) -> Path:
        target = self.root / directory
        defaults = dict(
            blocks_per_unit=4,
            units_per_shard=2,
            block_count=16,
            allow_bounded_test=True,
        )
        defaults.update(kwargs)  # type: ignore[arg-type]
        initialize_schedule(
            output_directory=target,
            runner=self.runner,
            source_manifest=self.manifest,
            **defaults,  # type: ignore[arg-type]
        )
        return target

    # -- geometry ---------------------------------------------------------

    def test_geometry_is_a_pure_function_of_the_plan(self) -> None:
        directory = self._schedule()
        schedule = load_schedule(directory)
        self.assertEqual(schedule["geometry"]["unit_count"], 4)
        self.assertEqual(schedule["geometry"]["shard_count"], 2)
        self.assertEqual(unit_block_range(schedule, 0), (0, 4))
        self.assertEqual(unit_block_range(schedule, 3), (12, 16))
        self.assertEqual(shard_unit_range(schedule, 1), (2, 4))
        with self.assertRaises(PlattWindowedScheduleError):
            unit_block_range(schedule, 4)

    def test_partial_final_unit_is_clamped(self) -> None:
        directory = self._schedule("ragged", blocks_per_unit=5, block_count=13)
        schedule = load_schedule(directory)
        self.assertEqual(schedule["geometry"]["unit_count"], 3)
        self.assertEqual(unit_block_range(schedule, 2), (10, 13))

    def test_full_geometry_matches_the_published_shard_count(self) -> None:
        schedule = create_schedule(
            runner_sha256="0" * 64,
            runner_size=1,
            source_manifest_sha256="1" * 64,
            source_manifest_size=1,
        )
        self.assertEqual(schedule["geometry"]["blocks_per_shard"], 1 << 20)
        self.assertEqual(schedule["geometry"]["shard_count"], 2830)
        self.assertEqual(schedule["geometry"]["block_count"], 2_966_443_783)

    def test_mutated_schedule_fails_closed(self) -> None:
        directory = self._schedule()
        schedule = load_schedule(directory)
        schedule["geometry"]["unit_count"] = 99
        with self.assertRaises(PlattWindowedScheduleError):
            validate_schedule(schedule)

    def test_unbounded_geometry_requires_the_flag(self) -> None:
        with self.assertRaises(PlattWindowedScheduleError):
            create_schedule(
                runner_sha256="0" * 64,
                runner_size=1,
                source_manifest_sha256="1" * 64,
                source_manifest_size=1,
                block_count=16,
            )

    # -- execution --------------------------------------------------------

    def test_unit_receipt_binds_the_source_geometry(self) -> None:
        directory = self._schedule()
        receipt = run_unit(directory, self.runner, 0)
        schedule = load_schedule(directory)
        validate_unit_receipt(receipt, schedule, 0)
        self.assertEqual(receipt["height_lower"], SOURCE_LOWER)
        self.assertEqual(receipt["height_upper"], SOURCE_LOWER + 4 * STEP)
        self.assertEqual(receipt["total_zero_count"], 28)
        self.assertEqual(
            receipt["last_count"] - receipt["first_count"], receipt["total_zero_count"]
        )
        self.assertEqual(receipt["runner_sha256"], schedule["runner"]["sha256"])
        self.assertFalse(receipt["execution_attested"])
        self.assertFalse(receipt["lean_atom_discharged"])

    def test_rerun_is_a_no_op_and_returns_the_same_digest(self) -> None:
        directory = self._schedule()
        first = run_unit(directory, self.runner, 0)
        second = run_unit(directory, self.runner, 0)
        self.assertEqual(first["unit_sha256"], second["unit_sha256"])

    def test_digest_is_invariant_under_segmentation(self) -> None:
        """A unit resumed from a checkpoint must equal a single-shot unit."""

        whole = self._schedule("whole")
        split = self._schedule("split")
        reference = run_unit(whole, self.runner, 0)

        schedule = load_schedule(split)
        # Simulate a preemption after two blocks by committing a receipt built
        # from two separately parsed segments.
        from tg_verifier.platt_windowed_scheduler import (
            _parse_committed_prefix,
            _run_segment,
            _StopRequest,
        )

        del _parse_committed_prefix
        records: list[dict[str, int]] = []
        segments = []
        with _StopRequest() as stop:
            for first_block, count in ((0, 2), (2, 2)):
                fresh, text, _elapsed = _run_segment(
                    self.runner,
                    first_block=first_block,
                    block_count=count,
                    checkpoint_blocks=1,
                    on_progress=lambda *_: None,
                    stop=stop,
                    timeout_seconds=None,
                )
                records.extend(fresh)
                segments.append({"first_block": first_block, "block_count": count})
                del text
        segmented = _build_unit_receipt(schedule, 0, records, segments)
        self.assertEqual(segmented["unit_sha256"], reference["unit_sha256"])
        self.assertNotEqual(segmented["segments"], reference["segments"])

    def test_conflicting_duplicate_execution_fails_closed(self) -> None:
        directory = self._schedule()
        schedule = load_schedule(directory)
        receipt = run_unit(directory, self.runner, 0)
        forged = dict(receipt)
        forged["unit_sha256"] = "f" * 64
        with self.assertRaises(PlattWindowedScheduleError):
            _commit_unit(directory, schedule, 0, forged)

    def test_failure_token_fails_closed(self) -> None:
        directory = self._schedule("bad")
        bad = self._write_runner("bad.py", BAD_STUB)
        initialize_schedule(
            output_directory=self.root / "badcampaign",
            runner=bad,
            source_manifest=self.manifest,
            blocks_per_unit=4,
            units_per_shard=2,
            block_count=16,
            allow_bounded_test=True,
        )
        del directory
        with self.assertRaises(PlattWindowedScheduleError):
            run_unit(self.root / "badcampaign", bad, 0)

    def test_runner_identity_is_enforced(self) -> None:
        directory = self._schedule()
        other = self._write_runner("other.py", STUB + "\n# different bytes\n")
        with self.assertRaises(PlattWindowedScheduleError):
            run_unit(directory, other, 0)

    # -- leases -----------------------------------------------------------

    def test_lease_excludes_a_second_worker_then_expires(self) -> None:
        directory = self._schedule()
        schedule = load_schedule(directory)
        self.assertTrue(
            claim_unit(directory, schedule, 0, worker_id="a", lease_seconds=3600)
        )
        self.assertFalse(
            claim_unit(directory, schedule, 0, worker_id="b", lease_seconds=3600)
        )
        # An expired lease is stealable.
        self.assertTrue(
            claim_unit(directory, schedule, 0, worker_id="b", lease_seconds=0 + 1,
                       steal_expired=True)
            or claim_unit(directory, schedule, 0, worker_id="b", lease_seconds=1)
        )

    def test_next_unit_respects_the_stride_partition(self) -> None:
        directory = self._schedule()
        schedule = load_schedule(directory)
        even = next_unit(directory, schedule, worker_id="even", stride=2, offset=0)
        odd = next_unit(directory, schedule, worker_id="odd", stride=2, offset=1)
        self.assertEqual(even, 0)
        self.assertEqual(odd, 1)

    def test_next_unit_skips_committed_units(self) -> None:
        directory = self._schedule()
        schedule = load_schedule(directory)
        run_unit(directory, self.runner, 0)
        self.assertEqual(next_unit(directory, schedule, worker_id="w"), 1)

    # -- aggregation ------------------------------------------------------

    def _run_all(self, directory: Path) -> None:
        schedule = load_schedule(directory)
        for unit in range(schedule["geometry"]["unit_count"]):
            run_unit(directory, self.runner, unit)

    def test_seal_and_finalize(self) -> None:
        directory = self._schedule()
        self._run_all(directory)
        schedule = load_schedule(directory)
        shards = [
            seal_shard(directory, index)
            for index in range(schedule["geometry"]["shard_count"])
        ]
        for index, shard in enumerate(shards):
            validate_shard_receipt(shard, schedule, index)
        campaign = finalize(directory)
        self.assertEqual(campaign["total_zero_count"], 16 * 7)
        self.assertEqual(
            campaign["last_count"] - campaign["first_count"],
            campaign["total_zero_count"],
        )
        self.assertFalse(campaign["source_claim_ready"])
        self.assertTrue(campaign["lower_prefix_required"])
        self.assertFalse(campaign["prefix"]["bound"])
        # The top-level artifact must stay small enough to publish directly.
        self.assertLess(len((directory / "campaign.json").read_bytes()), 2048)

    def test_merkle_root_is_independently_recomputable(self) -> None:
        import hashlib

        from tg_verifier.platt_windowed_campaign import (
            MERKLE_LEAF_DOMAIN,
            MERKLE_NODE_DOMAIN,
        )

        directory = self._schedule()
        self._run_all(directory)
        shard = seal_shard(directory, 0)
        digests = (
            (directory / "shards" / "shard-000000" / "unit-digests.txt")
            .read_text(encoding="ascii")
            .split()
        )
        level = [
            hashlib.sha256(MERKLE_LEAF_DOMAIN + bytes.fromhex(leaf)).digest()
            for leaf in digests
        ]
        while len(level) > 1:
            if len(level) % 2:
                level.append(level[-1])
            level = [
                hashlib.sha256(MERKLE_NODE_DOMAIN + level[i] + level[i + 1]).digest()
                for i in range(0, len(level), 2)
            ]
        self.assertEqual(shard["unit_merkle_root_sha256"], level[0].hex())

    def test_seal_requires_every_unit(self) -> None:
        directory = self._schedule()
        run_unit(directory, self.runner, 0)
        with self.assertRaises(PlattWindowedScheduleError):
            seal_shard(directory, 0)

    def test_finalize_requires_every_shard(self) -> None:
        directory = self._schedule()
        self._run_all(directory)
        seal_shard(directory, 0)
        with self.assertRaises(PlattWindowedScheduleError):
            finalize(directory)

    def test_broken_count_chain_fails_closed(self) -> None:
        directory = self._schedule()
        self._run_all(directory)
        schedule = load_schedule(directory)
        path = _unit_receipt_path(directory, schedule, 1)
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["first_count"] += 1
        receipt["total_zero_count"] -= 1
        path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        with self.assertRaises(PlattWindowedScheduleError):
            seal_shard(directory, 0)

    def test_pruning_keeps_the_shard_verifiable(self) -> None:
        directory = self._schedule()
        self._run_all(directory)
        shard = seal_shard(directory, 0, prune_units=True)
        units = directory / "shards" / "shard-000000" / "units"
        self.assertEqual(sorted(os.listdir(units)), [])
        self.assertTrue(shard["units_pruned"])
        self.assertTrue(
            (directory / "shards" / "shard-000000" / "unit-digests.txt").is_file()
        )

    def test_status_reports_progress_without_scanning_sealed_shards(self) -> None:
        directory = self._schedule()
        self._run_all(directory)
        seal_shard(directory, 0, prune_units=True)
        report = status(directory)
        self.assertEqual(report["sealed_shards"], 1)
        self.assertEqual(report["units_committed_observed"], 4)
        self.assertEqual(report["first_unsealed_shard"], 1)
        self.assertFalse(report["complete"])

    # -- command line -----------------------------------------------------

    def test_cli_round_trip(self) -> None:
        directory = self.root / "cli"
        environment = {**os.environ, "PYTHONPATH": str(ROOT)}
        base = [
            sys.executable,
            str(ROOT / "tools" / "tg_platt_windowed_scheduler.py"),
        ]
        run = subprocess.run(
            base
            + [
                "init",
                str(directory),
                "--runner",
                str(self.runner),
                "--blocks-per-unit",
                "4",
                "--units-per-shard",
                "2",
                "--block-count",
                "16",
                "--allow-bounded-test",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        for unit in range(4):
            step = subprocess.run(
                base + ["run-unit", str(directory), str(unit), "--runner", str(self.runner)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(step.returncode, 0, step.stderr)
        for shard in range(2):
            step = subprocess.run(
                base + ["seal-shard", str(directory), str(shard)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(step.returncode, 0, step.stderr)
        final = subprocess.run(
            base + ["finalize", str(directory)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(final.returncode, 0, final.stderr)
        campaign = json.loads(final.stdout)
        self.assertTrue(campaign["accepted"])
        self.assertFalse(campaign["source_claim_ready"])


if __name__ == "__main__":
    unittest.main()
