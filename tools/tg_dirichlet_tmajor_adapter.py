#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Audit typed FFT bundles against authenticated t-major cache rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_tmajor_adapter import (  # noqa: E402
    DirichletTMajorAdapterError,
    TMajorTypedBundleLaneAdapter,
    admit_lane_manifest,
    capability,
)


def _nonnegative(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")

    rows = commands.add_parser("audit-rows")
    rows.add_argument("contract", type=Path)
    rows.add_argument("--lane-index", type=_nonnegative, required=True)
    rows.add_argument("--expected-contract-sha256")
    rows.add_argument("--allow-structural-kat", action="store_true")

    admit = commands.add_parser("admit-lane")
    admit.add_argument("contract", type=Path)
    admit.add_argument("manifest", type=Path)
    admit.add_argument("output", type=Path)
    admit.add_argument("--lane-index", type=_nonnegative, required=True)
    admit.add_argument("--expected-manifest-sha256", required=True)
    admit.add_argument("--expected-contract-sha256")
    admit.add_argument("--allow-structural-kat", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            answer = capability()
        elif args.command == "audit-rows":
            adapter = TMajorTypedBundleLaneAdapter(
                args.contract,
                lane_index=args.lane_index,
                expected_contract_sha256=args.expected_contract_sha256,
                allow_structural_kat=args.allow_structural_kat,
            )
            answer = adapter.authenticate_all_rows()
            answer["classification"] = (
                "cache_row_schedule_audit_not_pipeline_execution"
            )
            answer["external_atom_discharged"] = False
        elif args.command == "admit-lane":
            answer = admit_lane_manifest(
                args.output,
                contract_path=args.contract,
                lane_index=args.lane_index,
                manifest_path=args.manifest,
                expected_manifest_sha256=args.expected_manifest_sha256,
                expected_contract_sha256=args.expected_contract_sha256,
                allow_structural_kat=args.allow_structural_kat,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (
        DirichletTMajorAdapterError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"Dirichlet t-major adapter error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            answer,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
