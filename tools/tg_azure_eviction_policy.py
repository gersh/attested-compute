#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect and exercise the eviction-aware leaf-attempt policy.

This CLI is read-only with respect to Azure.  ``verify-coverage`` reads an
existing attempt ledger; nothing here provisions, prices, or contacts anything.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.azure_eviction import (  # noqa: E402
    ATTEMPT_STAGES,
    STAGE_POLICY,
    TERMINATION_CLASSES,
    EvictionPolicy,
    EvictionPolicyError,
    classify_termination,
    retry_decision,
    verify_leaf_receipt_coverage,
)
from tg_verifier.campaign_io import CampaignIOError, load_json  # noqa: E402


def _emit(value: object, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def _policy_table() -> dict:
    return {
        "accepted": False,
        "attempt_stages": list(ATTEMPT_STAGES),
        "classification": "read_only_retry_admissibility_table",
        "nonclaims": [
            "A retry decision is a scheduling judgement, not attestation "
            "evidence and not theorem authority.",
            "Every row marked operator_reconciliation_required preserves the "
            "existing fail-closed posture of both production orchestrators.",
        ],
        "stage_policy": STAGE_POLICY,
        "termination_classes": TERMINATION_CLASSES,
    }


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pretty", action="store_true")
    parser = argparse.ArgumentParser(description=__doc__, parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "policy-table",
        parents=[common],
        help="print the full retry-admissibility table",
    )

    classify = sub.add_parser(
        "classify",
        parents=[common],
        help="classify one attempt ending and print the retry decision",
    )
    classify.add_argument("--stage", choices=sorted(STAGE_POLICY), required=True)
    classify.add_argument("--exit-code", type=int, default=None)
    classify.add_argument("--signal", type=int, default=None)
    classify.add_argument(
        "--scheduled-event",
        default=None,
        help="Azure Scheduled Events EventType observed for this node",
    )
    classify.add_argument("--challenge-expired", action="store_true")
    classify.add_argument("--timed-out", action="store_true")
    classify.add_argument("--attempt-index", type=int, default=0)
    classify.add_argument("--max-attempts-per-leaf", type=int, default=None)

    coverage = sub.add_parser(
        "verify-coverage",
        parents=[common],
        help="prove exact one-receipt-per-leaf coverage across all attempts",
    )
    coverage.add_argument("run_root", type=Path)
    coverage.add_argument(
        "--leaves",
        type=Path,
        required=True,
        help="JSON object mapping task_id to {group_id, shard_index}",
    )
    coverage.add_argument(
        "--receipts",
        type=Path,
        required=True,
        help="JSON object mapping task_id to a receipt identifier",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "policy-table":
            _emit(_policy_table(), args.pretty)
            return 0
        if args.command == "classify":
            termination = classify_termination(
                exit_code=args.exit_code,
                signal_number=args.signal,
                scheduled_event=args.scheduled_event,
                challenge_expired=args.challenge_expired,
                timed_out=args.timed_out,
            )
            policy = (
                EvictionPolicy(max_attempts_per_leaf=args.max_attempts_per_leaf)
                if args.max_attempts_per_leaf is not None
                else EvictionPolicy()
            )
            decision = retry_decision(
                stage=args.stage,
                termination=termination,
                attempt_index=args.attempt_index,
                policy=policy,
            )
            _emit({"accepted": False, **decision}, args.pretty)
            return 0
        leaves = load_json(args.leaves)
        receipts = load_json(args.receipts)
        if not isinstance(leaves, dict) or not isinstance(receipts, dict):
            raise EvictionPolicyError("leaves and receipts must be JSON objects")
        report = verify_leaf_receipt_coverage(
            args.run_root,
            expected_leaves=leaves,
            receipts_by_task=receipts,
        )
        _emit({"accepted": False, **report}, args.pretty)
        return 0 if report["coverage_exact_one_receipt_per_leaf"] else 2
    except (EvictionPolicyError, CampaignIOError, OSError, ValueError) as error:
        _emit(
            {
                "accepted": False,
                "classification": "azure_eviction_policy_failed_closed",
                "error": str(error),
            },
            args.pretty,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
