#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Audit the pinned LMFDB zeta-prefix inventory and exact 10^10 cut."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.lmfdb_zeta_prefix import (  # noqa: E402
    LMFDBZetaPrefixError,
    TARGET_FILE,
    audit_public_target_file,
    load_source_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filelist", type=Path)
    parser.add_argument("md5_manifest", type=Path)
    parser.add_argument(
        "--target-file",
        type=Path,
        help=f"also stream and verify the reviewed {TARGET_FILE}",
    )
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.target_file is not None:
            # The optional data-file route streams the reviewed production
            # target.  Fail before even opening the inventory metadata.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
        inventory = load_source_inventory(arguments.filelist, arguments.md5_manifest)
        report: dict[str, object] = {
            "accepted": True,
            "classification": "pinned_lmfdb_source_inventory_only",
            "file_count": len(inventory.filenames),
            "prefix_file_count": len(inventory.prefix_filenames),
            "prefix_terminal_file": inventory.prefix_filenames[-1],
            "source_turing_completeness_independently_replayed": False,
            "source_claim_ready": False,
            "receipt_eligible_without_realization": False,
        }
        if arguments.target_file is not None:
            audit = audit_public_target_file(arguments.target_file, inventory)
            report["classification"] = (
                "pinned_lmfdb_inventory_and_exact_target_file_internal_audit"
            )
            report["target_file"] = audit.as_json()
    except (LMFDBZetaPrefixError, MeasuredWorkerScopeError, OSError) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2 if arguments.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
