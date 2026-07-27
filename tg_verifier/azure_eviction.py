# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Eviction-aware attempt accounting for spot/low-priority campaign leaves.

The campaign layer already has the two hard properties this module needs: a
leaf receipt is written once with ``O_EXCL`` under a name derived from the leaf
index, and the aggregate refuses any receipt set that is not exact coverage.
The measured runner already stages a run package into a hidden sibling
directory and publishes it with a single ``os.replace``, so a process killed
mid-flight leaves a partial staging directory and never a partial package.

What was missing is one layer up.  Both production orchestrators are
single-shard, fail-closed state machines with no notion of "this attempt was
preempted".  Every ambiguous failure lands in a manual reconciliation stage.
That is exactly right for a run on reserved capacity, and it is unusable on
spot: one eviction in a 65,536-leaf campaign stalls the campaign.

This module adds the missing distinction without weakening anything.  It
separates the *leaf*, which has at most one receipt for all time, from the
*attempt*, of which a leaf may have many.  It classifies how an attempt ended,
and it decides whether a fresh-challenge retry is admissible.  A retry is
admissible only in the window where the attempt provably cannot have produced
an externally observable artifact that a later step could mistake for a
completed leaf.  Everything at or after package ingest keeps the existing
posture: operator reconciliation, never automatic retry.

Two invariants are enforced mechanically rather than asserted:

1.  An attempt that did not complete is *quarantined* by an atomic rename into
    a directory no ingest path reads.  Its workspace is never deleted, so the
    evidence survives, and never left in place, so it cannot be ingested.

2.  :func:`verify_leaf_receipt_coverage` proves, from the attempt ledger and
    the receipt set together, that there is exactly one receipt per leaf, that
    a retried leaf is not a duplicate, and that a leaf whose attempts were lost
    and re-run is not a gap.

Nothing here provisions, prices, or contacts anything.  It never mints a
challenge nonce itself: it reports that a fresh one is *required*, and the
existing portfolio layer remains the only thing that creates one.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from tg_verifier.campaign_io import (
    CampaignIOError,
    advisory_lock,
    load_json,
    write_immutable_json,
)


SCHEMA_VERSION = 1
ATTEMPT_KIND = "sparkinterval.azure.tg.leaf-attempt.v1"
COVERAGE_KIND = "sparkinterval.azure.tg.leaf-receipt-coverage.v1"

#: An eviction storm must not be able to burn the budget silently.
DEFAULT_MAX_ATTEMPTS_PER_LEAF = 8

_ATTEMPT_NAME_RE = re.compile(r"attempt-([0-9]{6})\.json\Z")
_TASK_ID_RE = re.compile(r"[0-9a-f]{24}-[0-9]{9}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class EvictionPolicyError(RuntimeError):
    """Attempt accounting failed closed."""


# ---------------------------------------------------------------------------
# How an attempt ended.
# ---------------------------------------------------------------------------

#: Closed vocabulary.  ``preempted`` is the spot/low-priority case; it is kept
#: distinct from ``host_failure`` because only preemption is expected, bounded,
#: and worth retrying automatically at scale.
TERMINATION_CLASSES: dict[str, str] = {
    "completed": "the measured child exited zero and published its run package",
    "preempted": (
        "the platform reclaimed the VM: an Azure Scheduled Events Preempt or "
        "Terminate notice was observed, or the node disappeared while the "
        "child was running"
    ),
    "host_failure": "an infrastructure fault that is not a reclamation",
    "workload_failure": "the measured child itself exited non-zero",
    "timeout": "the orchestrator's own per-step timeout elapsed",
    "challenge_expired": "the attestation challenge TTL elapsed before the run finished",
    "unknown": "the reason could not be determined",
}

#: Stages an attempt can be in when it dies, ordered by increasing external
#: side effect.  The names mirror the orchestrator state machines so an
#: operator reading a reconciliation stage can find the matching row here.
ATTEMPT_STAGES: tuple[str, ...] = (
    "handoff_prepared",
    "challenge_created",
    "azure_deployment_in_progress",
    "azure_deployed",
    "measured_run_in_progress",
    "returned_package_ingested",
    "appraisal_recorded",
    "receipt_issuance_in_progress",
    "verified_receipt_recorded",
)

_STAGE_INDEX = {name: index for index, name in enumerate(ATTEMPT_STAGES)}

#: The retry decision, per stage.  This is the whole safety argument, so it is
#: a table rather than control flow.
#:
#: ``retry_admissible`` is true exactly where a terminated attempt cannot have
#: left an artifact that a later step would accept as this leaf's result.  The
#: cut is at package ingest: before it, the only durable thing the attempt can
#: have produced is a run package sitting on a VM that is about to be destroyed
#: or a staging directory that the measured runner already removed.  At and
#: after it, a real attested package, an appraisal, or an HSM signature may
#: exist, and discarding one silently would be an audit hole, so those stay on
#: the existing manual path.
STAGE_POLICY: dict[str, dict[str, Any]] = {
    "handoff_prepared": {
        "decision": "retry_admissible",
        "requires_fresh_challenge": True,
        "requires_resource_teardown": False,
        "reason": (
            "only local files exist; no challenge was released and no cloud "
            "resource was created"
        ),
    },
    "challenge_created": {
        "decision": "retry_admissible",
        "requires_fresh_challenge": True,
        "requires_resource_teardown": False,
        "reason": (
            "a nonce was minted but the workload was never released. The nonce "
            "is still retired rather than reused: the operator cannot prove "
            "from outside that the VM never extended PCR23 with it, and a "
            "fresh nonce costs nothing"
        ),
    },
    "azure_deployment_in_progress": {
        "decision": "operator_reconciliation_required",
        "requires_fresh_challenge": True,
        "requires_resource_teardown": True,
        "reason": (
            "a create call may have partially succeeded, so a VM may exist and "
            "be billing. This is a resource-leak reconciliation, not a "
            "correctness one, but it is not safe to loop on automatically"
        ),
    },
    "azure_deployed": {
        "decision": "retry_admissible_after_resource_teardown",
        "requires_fresh_challenge": True,
        "requires_resource_teardown": True,
        "reason": (
            "the VM exists and is known; it must be destroyed before a retry "
            "so the campaign cannot accumulate paid idle nodes"
        ),
    },
    "measured_run_in_progress": {
        "decision": "retry_admissible",
        "requires_fresh_challenge": True,
        "requires_resource_teardown": True,
        "reason": (
            "this is where a spot eviction almost always lands, because the "
            "measured run is the long pole. The challenge is burned, so the "
            "retry needs a fresh one; the measured runner publishes its "
            "package with a single atomic rename, so a killed run leaves a "
            "staging directory and never a package that could be ingested"
        ),
    },
    "returned_package_ingested": {
        "decision": "operator_reconciliation_required",
        "requires_fresh_challenge": True,
        "requires_resource_teardown": False,
        "reason": (
            "a complete attested package may already be on disk. Retrying "
            "would silently discard a paid, attested result; the receipt path "
            "is O_EXCL so a second receipt is impossible either way, but "
            "throwing away evidence without a human deciding is not something "
            "this layer should do"
        ),
    },
    "appraisal_recorded": {
        "decision": "operator_reconciliation_required",
        "requires_fresh_challenge": True,
        "requires_resource_teardown": False,
        "reason": "as above; an appraisal of real evidence exists",
    },
    "receipt_issuance_in_progress": {
        "decision": "operator_reconciliation_required",
        "requires_fresh_challenge": True,
        "requires_resource_teardown": False,
        "reason": (
            "the Managed HSM may have signed. This row must never become "
            "automatic: a signature that exists but was not recorded is "
            "precisely the case a human has to look at"
        ),
    },
    "verified_receipt_recorded": {
        "decision": "leaf_already_complete",
        "requires_fresh_challenge": False,
        "requires_resource_teardown": False,
        "reason": "the leaf has its one receipt; there is nothing to retry",
    },
}


@dataclass(frozen=True)
class EvictionPolicy:
    """Bounds on how hard a campaign may retry."""

    max_attempts_per_leaf: int = DEFAULT_MAX_ATTEMPTS_PER_LEAF

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts_per_leaf, bool)
            or not isinstance(self.max_attempts_per_leaf, int)
            or not 1 <= self.max_attempts_per_leaf <= 1000
        ):
            raise EvictionPolicyError(
                "max_attempts_per_leaf must be an integer in 1..1000"
            )


def classify_termination(
    *,
    exit_code: int | None,
    signal_number: int | None = None,
    scheduled_event: str | None = None,
    challenge_expired: bool = False,
    timed_out: bool = False,
) -> str:
    """Map an observed child ending onto :data:`TERMINATION_CLASSES`.

    ``scheduled_event`` is the ``EventType`` an Azure Scheduled Events poller
    saw for this node, if any.  The caller supplies it; this module never polls
    anything.  The Azure documented values for reclamation are ``Preempt`` and
    ``Terminate``; ``Reboot`` and ``Redeploy`` are not reclamations but do kill
    a run, so they are reported as host failures.
    """

    if scheduled_event is not None and not isinstance(scheduled_event, str):
        raise EvictionPolicyError("scheduled_event must be a string or None")
    if scheduled_event in {"Preempt", "Terminate"}:
        return "preempted"
    if challenge_expired is True:
        return "challenge_expired"
    if scheduled_event in {"Reboot", "Redeploy", "Freeze"}:
        return "host_failure"
    if timed_out is True:
        return "timeout"
    if exit_code == 0 and signal_number is None:
        return "completed"
    if signal_number is not None:
        # A run killed by SIGTERM/SIGKILL with no scheduled-event evidence is
        # not assumed to be a preemption.  Guessing generously here would turn
        # a genuine crash loop into an automatic retry loop.
        return "unknown"
    if isinstance(exit_code, int) and exit_code != 0:
        return "workload_failure"
    return "unknown"


def retry_decision(
    *,
    stage: str,
    termination: str,
    attempt_index: int,
    policy: EvictionPolicy | None = None,
) -> dict[str, Any]:
    """Decide whether this leaf may be re-attempted, and under what conditions."""

    if stage not in STAGE_POLICY:
        raise EvictionPolicyError(f"unknown attempt stage: {stage!r}")
    if termination not in TERMINATION_CLASSES:
        raise EvictionPolicyError(f"unknown termination class: {termination!r}")
    if (
        isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or attempt_index < 0
    ):
        raise EvictionPolicyError("attempt index must be a nonnegative integer")
    bounds = policy or EvictionPolicy()
    row = STAGE_POLICY[stage]
    decision = row["decision"]
    reason = row["reason"]

    if termination == "completed":
        if stage != "verified_receipt_recorded":
            # A "completed" child that did not reach a recorded receipt is not
            # a finished leaf; fall through to the stage policy.
            pass
        else:
            decision = "leaf_already_complete"

    # Only expected, bounded reclamation is retried without a human.  A
    # workload that failed on its own will fail again, and an unexplained death
    # is exactly what fail-closed is for.
    if decision in {"retry_admissible", "retry_admissible_after_resource_teardown"}:
        if termination in {"workload_failure", "unknown"}:
            decision = "operator_reconciliation_required"
            reason = (
                f"stage {stage} would permit a retry, but the attempt ended as "
                f"{termination!r}, which is not an expected reclamation; "
                "retrying would loop on a real fault"
            )
        elif attempt_index + 1 >= bounds.max_attempts_per_leaf:
            decision = "attempt_budget_exhausted"
            reason = (
                f"this leaf has used {attempt_index + 1} of "
                f"{bounds.max_attempts_per_leaf} permitted attempts; an "
                "eviction storm must surface rather than spend"
            )

    return {
        "attempt_index": attempt_index,
        "decision": decision,
        "max_attempts_per_leaf": bounds.max_attempts_per_leaf,
        "reason": reason,
        "requires_fresh_challenge": row["requires_fresh_challenge"],
        "requires_quarantine": decision != "leaf_already_complete",
        "requires_resource_teardown": row["requires_resource_teardown"],
        "stage": stage,
        "termination": termination,
    }


# ---------------------------------------------------------------------------
# The append-only attempt ledger.
# ---------------------------------------------------------------------------


def _task_id(value: Any) -> str:
    if not isinstance(value, str) or _TASK_ID_RE.fullmatch(value) is None:
        raise EvictionPolicyError(f"malformed task id: {value!r}")
    return value


def _sha256(value: Any, what: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EvictionPolicyError(f"{what} must be a lowercase SHA-256")
    return value


def attempts_root(run_root: Path) -> Path:
    return Path(run_root) / "attempts"


def quarantine_root(run_root: Path) -> Path:
    return Path(run_root) / "quarantine"


def _leaf_dir(run_root: Path, task_id: str) -> Path:
    return attempts_root(run_root) / _task_id(task_id)


def attempt_paths(run_root: Path, task_id: str) -> list[Path]:
    """Return this leaf's attempt records in contiguous index order."""

    directory = _leaf_dir(run_root, task_id)
    if not directory.is_dir():
        return []
    by_index: dict[int, Path] = {}
    for entry in sorted(directory.iterdir()):
        if entry.name.startswith("."):
            continue
        match = _ATTEMPT_NAME_RE.fullmatch(entry.name)
        if match is None:
            raise EvictionPolicyError(
                f"unexpected file in attempt ledger: {entry}"
            )
        index = int(match.group(1))
        if index in by_index:
            raise EvictionPolicyError(f"duplicate attempt index {index} for {task_id}")
        by_index[index] = entry
    expected = set(range(len(by_index)))
    if set(by_index) != expected:
        raise EvictionPolicyError(
            f"attempt ledger for {task_id} is not contiguous from zero: "
            f"{sorted(by_index)}"
        )
    return [by_index[index] for index in sorted(by_index)]


def load_attempts(run_root: Path, task_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, path in enumerate(attempt_paths(run_root, task_id)):
        try:
            record = load_json(path, require_canonical=True)
        except CampaignIOError as error:
            raise EvictionPolicyError(f"cannot load attempt record {path}") from error
        if not isinstance(record, dict) or record.get("kind") != ATTEMPT_KIND:
            raise EvictionPolicyError(f"attempt record has the wrong kind: {path}")
        if record.get("attempt_index") != index:
            raise EvictionPolicyError(
                f"attempt record {path} disagrees with its filename index"
            )
        if record.get("task_id") != task_id:
            raise EvictionPolicyError(f"attempt record {path} names another leaf")
        records.append(record)
    return records


def record_attempt(
    run_root: Path,
    *,
    task_id: str,
    group_id: str,
    shard_index: int,
    challenge_sha256: str,
    stage: str,
    termination: str,
    quarantined_path: str | None,
    policy: EvictionPolicy | None = None,
) -> dict[str, Any]:
    """Append one immutable attempt record and return the retry decision.

    The record is content addressed and written with
    :func:`campaign_io.write_immutable_json`, so an attempt that is written
    twice with the same bytes is idempotent and an attempt that is rewritten
    with different bytes fails closed.
    """

    run_root = Path(run_root)
    task = _task_id(task_id)
    if not isinstance(group_id, str) or not group_id:
        raise EvictionPolicyError("group id must be a nonempty string")
    if (
        isinstance(shard_index, bool)
        or not isinstance(shard_index, int)
        or shard_index < 0
    ):
        raise EvictionPolicyError("shard index must be a nonnegative integer")
    _sha256(challenge_sha256, "challenge digest")
    if stage not in STAGE_POLICY:
        raise EvictionPolicyError(f"unknown attempt stage: {stage!r}")
    if termination not in TERMINATION_CLASSES:
        raise EvictionPolicyError(f"unknown termination class: {termination!r}")
    if quarantined_path is not None and not isinstance(quarantined_path, str):
        raise EvictionPolicyError("quarantined path must be a string or null")

    directory = _leaf_dir(run_root, task)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with advisory_lock(directory / ".attempts.lock"):
        existing = load_attempts(run_root, task)
        for record in existing:
            if record["challenge_sha256"] == challenge_sha256:
                raise EvictionPolicyError(
                    "an attempt with this challenge digest is already recorded; "
                    "a retry must use a fresh challenge, never a reused nonce"
                )
        completed = [
            record for record in existing if record["termination"] == "completed"
        ]
        if completed and termination == "completed":
            raise EvictionPolicyError(
                f"leaf {task} already has a completed attempt; a leaf has at "
                "most one completed attempt for all time"
            )
        index = len(existing)
        decision = retry_decision(
            stage=stage,
            termination=termination,
            attempt_index=index,
            policy=policy,
        )
        record = {
            "attempt_index": index,
            "challenge_sha256": challenge_sha256,
            "decision": decision["decision"],
            "group_id": group_id,
            "kind": ATTEMPT_KIND,
            "quarantined_path": quarantined_path,
            "schema_version": SCHEMA_VERSION,
            "shard_index": shard_index,
            "stage": stage,
            "task_id": task,
            "termination": termination,
        }
        write_immutable_json(directory / f"attempt-{index:06d}.json", record)
    return {"decision": decision, "record": record}


def quarantine_attempt(
    run_root: Path,
    *,
    task_id: str,
    attempt_index: int,
    workspace: Path,
) -> str:
    """Atomically move a dead attempt's workspace out of every ingest path.

    The workspace is never deleted: an evicted attempt is evidence about the
    campaign even though it is not evidence about the mathematics.  It is also
    never left where it was, because every ingest path in the orchestrators
    reads a fixed workspace location and would otherwise be handed a truncated
    directory on the next attempt.
    """

    run_root = Path(run_root)
    task = _task_id(task_id)
    if (
        isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or not 0 <= attempt_index <= 999_999
    ):
        raise EvictionPolicyError("attempt index must be an integer in 0..999999")
    source = Path(workspace)
    if source.is_symlink() or not source.is_dir():
        raise EvictionPolicyError(
            f"quarantine source must be a real directory: {source}"
        )
    destination_parent = quarantine_root(run_root) / task
    destination_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = destination_parent / f"attempt-{attempt_index:06d}"
    if destination.exists():
        raise EvictionPolicyError(f"quarantine destination exists: {destination}")
    try:
        os.replace(source, destination)
    except OSError as error:
        raise EvictionPolicyError(
            f"cannot quarantine {source}: {error}"
        ) from error
    return str(destination)


# ---------------------------------------------------------------------------
# The mechanical proof that receipts are per leaf, not per attempt.
# ---------------------------------------------------------------------------


def verify_leaf_receipt_coverage(
    run_root: Path,
    *,
    expected_leaves: Mapping[str, Mapping[str, Any]],
    receipts_by_task: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove exact per-leaf coverage across an arbitrary number of attempts.

    ``expected_leaves`` maps ``task_id`` to at least ``group_id`` and
    ``shard_index``; it is the plan's leaf set.  ``receipts_by_task`` maps
    ``task_id`` to whatever the caller uses to identify that leaf's single
    receipt (a digest, a path, a parsed record).  This function never parses a
    receipt: exact-coverage checking against a plan is already
    ``goldbach_gpu_campaign.aggregate_receipts``' job, and duplicating it here
    would create a second, weaker authority.  What it adds is the attempt
    dimension that the aggregate cannot see.

    The four failure modes it exists to catch:

    * a retried leaf counted twice, because two attempts each left a receipt;
    * a leaf counted as missing, because its only successful attempt was lost;
    * a receipt whose leaf never actually completed an attempt;
    * a receipt that came from a quarantined attempt.
    """

    run_root = Path(run_root)
    expected = {}
    for task_id, meta in expected_leaves.items():
        expected[_task_id(task_id)] = meta
    receipts = {_task_id(task_id): value for task_id, value in receipts_by_task.items()}

    missing_receipt = sorted(set(expected) - set(receipts))
    unexpected_receipt = sorted(set(receipts) - set(expected))

    leaves: list[dict[str, Any]] = []
    violations: list[str] = []
    total_attempts = 0
    wasted_attempts = 0

    for task_id in sorted(expected):
        records = load_attempts(run_root, task_id)
        total_attempts += len(records)
        completed = [row for row in records if row["termination"] == "completed"]
        not_completed = [row for row in records if row["termination"] != "completed"]
        wasted_attempts += len(not_completed)
        has_receipt = task_id in receipts

        if len(completed) > 1:
            violations.append(
                f"{task_id}: {len(completed)} completed attempts; a leaf may "
                "have at most one"
            )
        if has_receipt and not completed:
            violations.append(
                f"{task_id}: a receipt exists but no attempt is recorded as "
                "completed"
            )
        if completed and not has_receipt:
            violations.append(
                f"{task_id}: an attempt completed but no receipt was collected"
            )
        for row in not_completed:
            if row["quarantined_path"] is None:
                violations.append(
                    f"{task_id}: attempt {row['attempt_index']} ended as "
                    f"{row['termination']!r} but was never quarantined, so its "
                    "workspace can still be reached by an ingest path"
                )
        for row in completed:
            if row["quarantined_path"] is not None:
                violations.append(
                    f"{task_id}: the completed attempt {row['attempt_index']} "
                    "is quarantined; a quarantined attempt must never supply "
                    "a receipt"
                )
        leaves.append(
            {
                "attempt_count": len(records),
                "completed_attempts": len(completed),
                "has_receipt": has_receipt,
                "quarantined_attempts": len(not_completed),
                "task_id": task_id,
            }
        )

    for task_id in unexpected_receipt:
        violations.append(f"{task_id}: receipt for a leaf that is not in the plan")

    exact = not (missing_receipt or unexpected_receipt or violations)
    retried = [row for row in leaves if row["attempt_count"] > 1]
    return {
        "attempt_efficiency": {
            "leaves_retried": len(retried),
            "max_attempts_on_one_leaf": max(
                (row["attempt_count"] for row in leaves), default=0
            ),
            "total_attempts": total_attempts,
            "wasted_attempts": wasted_attempts,
        },
        "coverage_exact_one_receipt_per_leaf": exact,
        "expected_leaf_count": len(expected),
        "kind": COVERAGE_KIND,
        "leaves": leaves,
        "missing_receipt": missing_receipt,
        "nonclaims": [
            "Exact coverage is a structural property of the receipt set, not "
            "evidence that any receipt is attested or that any atom is "
            "discharged.",
            "This report does not parse or validate receipt contents; the "
            "campaign aggregate remains the only authority on that.",
        ],
        "receipt_count": len(receipts),
        "schema_version": SCHEMA_VERSION,
        "unexpected_receipt": unexpected_receipt,
        "violations": sorted(violations),
    }


__all__ = [
    "ATTEMPT_KIND",
    "ATTEMPT_STAGES",
    "COVERAGE_KIND",
    "DEFAULT_MAX_ATTEMPTS_PER_LEAF",
    "EvictionPolicy",
    "EvictionPolicyError",
    "SCHEMA_VERSION",
    "STAGE_POLICY",
    "TERMINATION_CLASSES",
    "attempt_paths",
    "attempts_root",
    "classify_termination",
    "load_attempts",
    "quarantine_attempt",
    "quarantine_root",
    "record_attempt",
    "retry_decision",
    "verify_leaf_receipt_coverage",
]
