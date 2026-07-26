#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bind and audit the source-wide t-major Dirichlet supervisor contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_source_supervisor import (  # noqa: E402
    DEFAULT_Q_BATCH_SIZE,
    DirichletSourceSupervisorError,
    build_source_contract,
    build_structural_kat_contract,
    capability,
    fft_batch_descriptor,
    load_contract,
    q_tile_descriptor,
)


def _positive(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")

    bind = commands.add_parser("bind-source")
    bind.add_argument("cache_root", type=Path)
    bind.add_argument("cache_catalog", type=Path)
    bind.add_argument("recovery_artifact", type=Path)
    bind.add_argument("recovery_manifest", type=Path)
    bind.add_argument("recovery_replay", type=Path)
    bind.add_argument("root_artifact_directory", type=Path)
    bind.add_argument("root_catalog", type=Path)
    bind.add_argument("output", type=Path)
    bind.add_argument("--q-tile-size", type=_positive, default=DEFAULT_Q_BATCH_SIZE)

    kat = commands.add_parser("bind-structural-kat")
    kat.add_argument("cache_root", type=Path)
    kat.add_argument("cache_catalog", type=Path)
    kat.add_argument("output", type=Path)
    kat.add_argument("--lanes", type=_positive, required=True)
    kat.add_argument("--recovery-artifact-sha256", required=True)
    kat.add_argument("--recovery-replay-sha256", required=True)
    kat.add_argument("--q-tile-size", type=_positive, default=DEFAULT_Q_BATCH_SIZE)
    kat.add_argument("--q-start", type=_positive, default=10_001)
    kat.add_argument("--q-stop", type=_positive, default=400_000)

    audit = commands.add_parser("audit")
    audit.add_argument("contract", type=Path)
    audit.add_argument("--allow-structural-kat", action="store_true")
    audit.add_argument("--expected-contract-sha256")

    tile = commands.add_parser("q-tile")
    tile.add_argument("contract", type=Path)
    tile.add_argument("t_index", type=int)
    tile.add_argument("q_tile_index", type=int)
    tile.add_argument("--allow-structural-kat", action="store_true")
    tile.add_argument("--expected-contract-sha256")

    fft = commands.add_parser("fft-batch")
    fft.add_argument("contract", type=Path)
    fft.add_argument("lane_index", type=int)
    fft.add_argument("q", type=int)
    fft.add_argument("first_t_index", type=int)
    fft.add_argument("--allow-structural-kat", action="store_true")
    fft.add_argument("--expected-contract-sha256")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            answer = capability()
        elif args.command == "bind-source":
            answer = build_source_contract(
                args.output,
                cache_root=args.cache_root,
                cache_catalog=args.cache_catalog,
                recovery_artifact=args.recovery_artifact,
                recovery_manifest=args.recovery_manifest,
                recovery_replay=args.recovery_replay,
                root_artifact_directory=args.root_artifact_directory,
                root_catalog=args.root_catalog,
                q_tile_size=args.q_tile_size,
            )
        elif args.command == "bind-structural-kat":
            answer = build_structural_kat_contract(
                args.output,
                cache_root=args.cache_root,
                cache_catalog=args.cache_catalog,
                lane_count=args.lanes,
                recovery_artifact_sha256=args.recovery_artifact_sha256,
                recovery_replay_sha256=args.recovery_replay_sha256,
                q_tile_size=args.q_tile_size,
                q_start=args.q_start,
                q_stop=args.q_stop,
            )
        elif args.command == "audit":
            answer = load_contract(
                args.contract,
                allow_structural_kat=args.allow_structural_kat,
                expected_contract_sha256=args.expected_contract_sha256,
            )
        elif args.command == "q-tile":
            contract = load_contract(
                args.contract,
                allow_structural_kat=args.allow_structural_kat,
                expected_contract_sha256=args.expected_contract_sha256,
            )
            answer = q_tile_descriptor(
                contract,
                t_index=args.t_index,
                q_tile_index=args.q_tile_index,
            )
        elif args.command == "fft-batch":
            contract = load_contract(
                args.contract,
                allow_structural_kat=args.allow_structural_kat,
                expected_contract_sha256=args.expected_contract_sha256,
            )
            answer = fft_batch_descriptor(
                contract,
                lane_index=args.lane_index,
                q=args.q,
                first_t_index=args.first_t_index,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (DirichletSourceSupervisorError, OSError, RuntimeError, ValueError) as error:
        print(f"Dirichlet source supervisor error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(answer, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
