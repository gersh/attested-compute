# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Eviction-aware leaf-attempt accounting."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.azure_eviction import (  # noqa: E402
    STAGE_POLICY,
    EvictionPolicy,
    EvictionPolicyError,
    classify_termination,
    load_attempts,
    quarantine_attempt,
    record_attempt,
    retry_decision,
    verify_leaf_receipt_coverage,
)


TASK_A = "0123456789abcdef01234567-000000000"
TASK_B = "0123456789abcdef01234567-000000001"


def digest(seed: int) -> str:
    return f"{seed:064x}"


class ClassifyTerminationTest(unittest.TestCase):
    def test_preempt_and_terminate_are_reclamation(self) -> None:
        for event in ("Preempt", "Terminate"):
            self.assertEqual(
                classify_termination(exit_code=None, scheduled_event=event),
                "preempted",
            )

    def test_reboot_and_redeploy_are_not_reclamation(self) -> None:
        for event in ("Reboot", "Redeploy", "Freeze"):
            self.assertEqual(
                classify_termination(exit_code=None, scheduled_event=event),
                "host_failure",
            )

    def test_clean_exit_is_completed(self) -> None:
        self.assertEqual(classify_termination(exit_code=0), "completed")

    def test_nonzero_exit_is_workload_failure(self) -> None:
        self.assertEqual(classify_termination(exit_code=3), "workload_failure")

    def test_signal_without_scheduled_event_is_not_assumed_preemption(self) -> None:
        # Guessing generously here would convert a crash loop into a retry loop.
        self.assertEqual(
            classify_termination(exit_code=None, signal_number=15), "unknown"
        )

    def test_expired_challenge_outranks_a_clean_exit_code(self) -> None:
        self.assertEqual(
            classify_termination(exit_code=0, challenge_expired=True),
            "challenge_expired",
        )

    def test_timeout(self) -> None:
        self.assertEqual(
            classify_termination(exit_code=None, timed_out=True), "timeout"
        )


class RetryDecisionTest(unittest.TestCase):
    def test_preemption_during_the_measured_run_is_retryable(self) -> None:
        decision = retry_decision(
            stage="measured_run_in_progress",
            termination="preempted",
            attempt_index=0,
        )
        self.assertEqual(decision["decision"], "retry_admissible")
        self.assertTrue(decision["requires_fresh_challenge"])
        self.assertTrue(decision["requires_resource_teardown"])
        self.assertTrue(decision["requires_quarantine"])

    def test_receipt_issuance_is_never_automatic(self) -> None:
        for termination in ("preempted", "host_failure", "timeout", "unknown"):
            decision = retry_decision(
                stage="receipt_issuance_in_progress",
                termination=termination,
                attempt_index=0,
            )
            self.assertEqual(
                decision["decision"], "operator_reconciliation_required", termination
            )

    def test_ingested_package_is_never_automatic(self) -> None:
        for stage in ("returned_package_ingested", "appraisal_recorded"):
            decision = retry_decision(
                stage=stage, termination="preempted", attempt_index=0
            )
            self.assertEqual(
                decision["decision"], "operator_reconciliation_required", stage
            )

    def test_workload_failure_is_not_retried_even_in_a_retryable_stage(self) -> None:
        decision = retry_decision(
            stage="measured_run_in_progress",
            termination="workload_failure",
            attempt_index=0,
        )
        self.assertEqual(decision["decision"], "operator_reconciliation_required")

    def test_every_retryable_stage_demands_a_fresh_challenge(self) -> None:
        for stage, row in STAGE_POLICY.items():
            if row["decision"].startswith("retry_admissible"):
                self.assertTrue(row["requires_fresh_challenge"], stage)

    def test_attempt_budget_is_enforced(self) -> None:
        policy = EvictionPolicy(max_attempts_per_leaf=3)
        self.assertEqual(
            retry_decision(
                stage="measured_run_in_progress",
                termination="preempted",
                attempt_index=1,
                policy=policy,
            )["decision"],
            "retry_admissible",
        )
        self.assertEqual(
            retry_decision(
                stage="measured_run_in_progress",
                termination="preempted",
                attempt_index=2,
                policy=policy,
            )["decision"],
            "attempt_budget_exhausted",
        )

    def test_unknown_stage_and_termination_fail_closed(self) -> None:
        with self.assertRaises(EvictionPolicyError):
            retry_decision(stage="nope", termination="preempted", attempt_index=0)
        with self.assertRaises(EvictionPolicyError):
            retry_decision(
                stage="measured_run_in_progress", termination="nope", attempt_index=0
            )


class AttemptLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.run_root = Path(self._temporary.name)
        self.addCleanup(self._temporary.cleanup)

    def append(
        self,
        *,
        task_id: str = TASK_A,
        shard_index: int = 0,
        seed: int,
        stage: str = "measured_run_in_progress",
        termination: str = "preempted",
        quarantined: str | None = "/quarantine/x",
    ) -> dict:
        return record_attempt(
            self.run_root,
            task_id=task_id,
            group_id="cdem-table-abel::single-job",
            shard_index=shard_index,
            challenge_sha256=digest(seed),
            stage=stage,
            termination=termination,
            quarantined_path=quarantined,
        )

    def test_attempts_are_contiguous_and_immutable(self) -> None:
        self.append(seed=1)
        self.append(seed=2)
        result = self.append(
            seed=3, stage="verified_receipt_recorded",
            termination="completed", quarantined=None,
        )
        self.assertEqual(result["record"]["attempt_index"], 2)
        records = load_attempts(self.run_root, TASK_A)
        self.assertEqual([row["attempt_index"] for row in records], [0, 1, 2])
        self.assertEqual(
            [row["termination"] for row in records],
            ["preempted", "preempted", "completed"],
        )

    def test_a_reused_challenge_nonce_is_refused(self) -> None:
        self.append(seed=7)
        with self.assertRaises(EvictionPolicyError) as caught:
            self.append(seed=7)
        self.assertIn("fresh challenge", str(caught.exception))

    def test_a_leaf_cannot_have_two_completed_attempts(self) -> None:
        self.append(
            seed=1, stage="verified_receipt_recorded",
            termination="completed", quarantined=None,
        )
        with self.assertRaises(EvictionPolicyError) as caught:
            self.append(
                seed=2, stage="verified_receipt_recorded",
                termination="completed", quarantined=None,
            )
        self.assertIn("at most one completed attempt", str(caught.exception))

    def test_quarantine_moves_the_workspace_atomically(self) -> None:
        workspace = self.run_root / "shards" / "w"
        (workspace / "partial").mkdir(parents=True)
        (workspace / "partial" / "half.bin").write_bytes(b"truncated")
        destination = quarantine_attempt(
            self.run_root, task_id=TASK_A, attempt_index=0, workspace=workspace
        )
        self.assertFalse(workspace.exists())
        moved = Path(destination)
        self.assertTrue((moved / "partial" / "half.bin").is_file())

    def test_quarantine_never_overwrites(self) -> None:
        for name in ("a", "b"):
            (self.run_root / name).mkdir()
        quarantine_attempt(
            self.run_root, task_id=TASK_A, attempt_index=0,
            workspace=self.run_root / "a",
        )
        with self.assertRaises(EvictionPolicyError):
            quarantine_attempt(
                self.run_root, task_id=TASK_A, attempt_index=0,
                workspace=self.run_root / "b",
            )


class CoverageTest(unittest.TestCase):
    """Receipts are per completed leaf, never per attempt."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.run_root = Path(self._temporary.name)
        self.addCleanup(self._temporary.cleanup)
        self.leaves = {
            TASK_A: {"group_id": "g", "shard_index": 0},
            TASK_B: {"group_id": "g", "shard_index": 1},
        }

    def append(self, task_id, seed, termination, quarantined, shard_index) -> None:
        record_attempt(
            self.run_root,
            task_id=task_id,
            group_id="g",
            shard_index=shard_index,
            challenge_sha256=digest(seed),
            stage=(
                "verified_receipt_recorded"
                if termination == "completed"
                else "measured_run_in_progress"
            ),
            termination=termination,
            quarantined_path=quarantined,
        )

    def test_three_attempts_one_success_is_exact_coverage(self) -> None:
        # Leaf A is evicted twice and succeeds on the third attempt.  Leaf B
        # succeeds first time.  Two leaves, four attempts, two receipts.
        self.append(TASK_A, 1, "preempted", "/q/0", 0)
        self.append(TASK_A, 2, "preempted", "/q/1", 0)
        self.append(TASK_A, 3, "completed", None, 0)
        self.append(TASK_B, 4, "completed", None, 1)
        report = verify_leaf_receipt_coverage(
            self.run_root,
            expected_leaves=self.leaves,
            receipts_by_task={TASK_A: digest(101), TASK_B: digest(102)},
        )
        self.assertTrue(report["coverage_exact_one_receipt_per_leaf"])
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["attempt_efficiency"]["total_attempts"], 4)
        self.assertEqual(report["attempt_efficiency"]["wasted_attempts"], 2)
        self.assertEqual(report["attempt_efficiency"]["leaves_retried"], 1)
        self.assertEqual(report["attempt_efficiency"]["max_attempts_on_one_leaf"], 3)

    def test_a_retry_is_not_counted_as_a_duplicate(self) -> None:
        self.append(TASK_A, 1, "preempted", "/q/0", 0)
        self.append(TASK_A, 2, "completed", None, 0)
        self.append(TASK_B, 3, "completed", None, 1)
        report = verify_leaf_receipt_coverage(
            self.run_root,
            expected_leaves=self.leaves,
            receipts_by_task={TASK_A: "r", TASK_B: "r"},
        )
        self.assertTrue(report["coverage_exact_one_receipt_per_leaf"])
        self.assertEqual(report["receipt_count"], 2)

    def test_a_lost_attempt_is_not_counted_as_a_gap(self) -> None:
        # Leaf B is evicted and has not yet been re-attempted: that is a real
        # missing receipt, and it must be reported as missing rather than
        # silently tolerated.
        self.append(TASK_A, 1, "completed", None, 0)
        self.append(TASK_B, 2, "preempted", "/q/0", 1)
        report = verify_leaf_receipt_coverage(
            self.run_root,
            expected_leaves=self.leaves,
            receipts_by_task={TASK_A: "r"},
        )
        self.assertFalse(report["coverage_exact_one_receipt_per_leaf"])
        self.assertEqual(report["missing_receipt"], [TASK_B])
        self.assertEqual(report["violations"], [])

    def test_a_receipt_without_a_completed_attempt_is_a_violation(self) -> None:
        self.append(TASK_A, 1, "completed", None, 0)
        self.append(TASK_B, 2, "preempted", "/q/0", 1)
        report = verify_leaf_receipt_coverage(
            self.run_root,
            expected_leaves=self.leaves,
            receipts_by_task={TASK_A: "r", TASK_B: "r"},
        )
        self.assertFalse(report["coverage_exact_one_receipt_per_leaf"])
        self.assertTrue(
            any("no attempt is recorded as completed" in row
                for row in report["violations"])
        )

    def test_an_unquarantined_dead_attempt_is_a_violation(self) -> None:
        self.append(TASK_A, 1, "preempted", None, 0)
        self.append(TASK_A, 2, "completed", None, 0)
        self.append(TASK_B, 3, "completed", None, 1)
        report = verify_leaf_receipt_coverage(
            self.run_root,
            expected_leaves=self.leaves,
            receipts_by_task={TASK_A: "r", TASK_B: "r"},
        )
        self.assertFalse(report["coverage_exact_one_receipt_per_leaf"])
        self.assertTrue(
            any("never quarantined" in row for row in report["violations"])
        )

    def test_a_receipt_outside_the_plan_is_a_violation(self) -> None:
        self.append(TASK_A, 1, "completed", None, 0)
        self.append(TASK_B, 2, "completed", None, 1)
        stray = "ffffffffffffffffffffffff-000000009"
        report = verify_leaf_receipt_coverage(
            self.run_root,
            expected_leaves=self.leaves,
            receipts_by_task={TASK_A: "r", TASK_B: "r", stray: "r"},
        )
        self.assertFalse(report["coverage_exact_one_receipt_per_leaf"])
        self.assertEqual(report["unexpected_receipt"], [stray])


if __name__ == "__main__":
    unittest.main()
