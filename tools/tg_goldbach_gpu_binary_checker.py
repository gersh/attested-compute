#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Adapt a hardened GoldbachGPU aggregate to the ladder checker protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.goldbach_gpu_campaign import (  # noqa: E402
    GoldbachGPUCampaignError,
    OPTIMIZED_PRODUCTION_ALGORITHM,
    PRODUCTION_ALGORITHM,
    PRODUCTION_EVEN_LIMIT,
    PRODUCTION_EVEN_START,
    load_plan,
    load_receipt,
    make_optimized_production_plan,
    make_production_plan,
    receipt_paths,
    validate_aggregate,
)


REQUEST_KIND = "tg_binary_goldbach_request_v1"
RESULT_KIND = "tg_binary_goldbach_result_v1"


class BinaryCheckerError(RuntimeError):
    """The request, production plan, receipts, or aggregate failed closed."""


def _load_request(path: Path) -> dict[str, object]:
    value = load_json(path, require_canonical=True)
    if not isinstance(value, dict):
        raise BinaryCheckerError("request must be a canonical JSON object")
    expected_fields = {
        "artifact_sha256",
        "every_even",
        "first_even",
        "kind",
        "last_even",
    }
    if set(value) != expected_fields:
        raise BinaryCheckerError("request fields differ from the checker protocol")
    if value["kind"] != REQUEST_KIND or value["every_even"] is not True:
        raise BinaryCheckerError("request does not ask for every even integer")
    if value["first_even"] != str(PRODUCTION_EVEN_START):
        raise BinaryCheckerError("request has the wrong first even integer")
    if value["last_even"] != str(PRODUCTION_EVEN_LIMIT):
        raise BinaryCheckerError("request has the wrong last even integer")
    digest = value["artifact_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise BinaryCheckerError("request artifact SHA-256 is malformed")
    return value


def verify_request(request_path: Path, artifact_path: Path) -> dict[str, object]:
    request = _load_request(request_path)
    artifact_path = artifact_path.resolve()
    artifact_sha256, _ = hash_file_once(artifact_path)
    if artifact_sha256 != request["artifact_sha256"]:
        raise BinaryCheckerError("aggregate bytes do not match the requested SHA-256")

    workspace = artifact_path.parent
    plan = load_plan(workspace / "plan.json")
    if plan.algorithm == PRODUCTION_ALGORITHM:
        expected_plan = make_production_plan(
            executable_sha256=plan.executable_sha256
        )
    elif plan.algorithm == OPTIMIZED_PRODUCTION_ALGORITHM:
        expected_plan = make_optimized_production_plan(
            executable_sha256=plan.executable_sha256
        )
    else:
        raise BinaryCheckerError(
            "binary prerequisite requires an exact historical-domain "
            "production algorithm"
        )
    if plan != expected_plan or (
        plan.even_start,
        plan.even_limit,
    ) != (PRODUCTION_EVEN_START, PRODUCTION_EVEN_LIMIT):
        raise BinaryCheckerError(
            "binary plan is not the exact historical prerequisite"
        )
    paths = receipt_paths(workspace / "receipts")
    receipts = [load_receipt(path, plan=plan) for path in paths]
    aggregate = load_json(artifact_path, require_canonical=True)
    validate_aggregate(aggregate, plan=plan, receipts=receipts)

    checker_sha256 = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
    return {
        "artifact_sha256": artifact_sha256,
        "checker_sha256": checker_sha256,
        "every_even": True,
        "first_even": str(PRODUCTION_EVEN_START),
        "kind": RESULT_KIND,
        "last_even": str(PRODUCTION_EVEN_LIMIT),
        "verified": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        # The request is fixed to the complete production range.  Guard
        # before opening either the request or the aggregate/receipt tree.
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
        result = verify_request(args.request, args.artifact)
    except (BinaryCheckerError, CampaignIOError, GoldbachGPUCampaignError, OSError) as exc:
        print(f"GoldbachGPU binary checker error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
