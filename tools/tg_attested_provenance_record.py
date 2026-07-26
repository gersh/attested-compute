#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate an attested-provenance N-way replication record.

This is the execution-layer audit for the alternative trust model prototyped
in [docs/ATTESTED_PROVENANCE_TRUST_MODEL.md](../docs/ATTESTED_PROVENANCE_TRUST_MODEL.md).
It checks that k independently operated replicas of one campaign agree on the
same Merkle root and output digest, that each replica's binaries carry a
verified build-provenance attestation, and that the record meets its own
declared independence thresholds.

It does not replay a campaign, open a production certificate, contact
Sigstore, or produce any input to a Lean theorem.  The confidential-compute
receipt path is untouched and remains the only route to
``accepted_run_certificate_sound``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.attested_provenance import (  # noqa: E402
    AttestedProvenanceError,
    load_and_validate,
)


DEFAULT_RECORD = (
    REPOSITORY_ROOT
    / "examples"
    / "attested-provenance"
    / "replication_record.example.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check that k independent replicas of one campaign agree, and "
            "that the record meets its declared independence policy"
        )
    )
    parser.add_argument(
        "record",
        nargs="?",
        type=Path,
        default=DEFAULT_RECORD,
        help="replication record to audit (default: the checked-in example)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="indent the emitted JSON evaluation",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print a one-line human summary instead of the JSON evaluation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        evaluation = load_and_validate(arguments.record)
    except AttestedProvenanceError as error:
        print(
            f"attested-provenance record audit failed: {error}", file=sys.stderr
        )
        return 1

    if arguments.summary:
        agreement = evaluation["agreement"]
        verdict = "AGREE" if evaluation["accepted"] else "REJECTED"
        print(
            f"{verdict}: {evaluation['campaign_id']} - "
            f"{agreement['replica_count']} replicas, "
            f"{agreement['distinct_merkle_roots']} distinct Merkle root(s), "
            f"{len(agreement['distinct_implementations'])} implementation(s), "
            f"{len(agreement['distinct_operators'])} operator(s), "
            f"{len(agreement['distinct_providers'])} provider(s); "
            "no Lean authority"
        )
        for failure in evaluation["failures"]:
            print(f"  - {failure}")
    elif arguments.pretty:
        print(json.dumps(evaluation, indent=2, sort_keys=True))
    else:
        print(json.dumps(evaluation, sort_keys=True, separators=(",", ":")))
    return 0 if evaluation["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
