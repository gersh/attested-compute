#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or audit resumable FLINT/Arb Riemann-zeta zero campaigns.

Every success remains an external-computation result, not a Lean axiom
discharge.  Run this tool with the interpreter from ``requirements-tg-flint``.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.zeta_zero_campaign import (  # noqa: E402
    MAX_BATCH_SIZE,
    MAX_PRECISION_BITS,
    MIN_PRECISION_BITS,
    PROFILES,
    FlintZetaBackend,
    ZetaCampaignError,
    finalize_campaign,
    initialize_campaign,
    replay_chunk,
    run_campaign,
    verify_campaign,
)


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _nonnegative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def _precision(text: str) -> int:
    value = _positive_int(text)
    if not MIN_PRECISION_BITS <= value <= MAX_PRECISION_BITS:
        raise argparse.ArgumentTypeError(
            f"must lie in [{MIN_PRECISION_BITS}, {MAX_PRECISION_BITS}]"
        )
    return value


def _batch_size(text: str) -> int:
    value = _positive_int(text)
    if value > MAX_BATCH_SIZE:
        raise argparse.ArgumentTypeError(f"must be at most {MAX_BATCH_SIZE}")
    return value


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _emit(value: object, *, pretty: bool) -> None:
    print(
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def command_profiles(args: argparse.Namespace) -> int:
    _emit(
        {
            "classification": "immutable_external_atom_campaign_profiles",
            "profiles": {
                name: {
                    "atom_id": profile.atom_id,
                    "lean_name": profile.lean_name,
                    "height": profile.height,
                    "expected_zero_count": profile.expected_zero_count,
                    "reciprocal_strict_upper_bound": profile.reciprocal_strict_upper_bound,
                    "source": profile.source,
                }
                for name, profile in PROFILES.items()
            },
            "lean_atom_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0


def command_count(args: argparse.Namespace) -> int:
    backend = FlintZetaBackend()
    count = backend.exact_zero_count(args.height, args.precision_bits)
    if args.expected is not None and count != args.expected:
        raise ZetaCampaignError(
            f"exact zeta_nzeros({args.height}) returned {count}, expected {args.expected}"
        )
    _emit(
        {
            "accepted": True,
            "classification": "exact_external_flint_zeta_nzeros_count",
            "height": args.height,
            "count": count,
            "expected_count_checked": args.expected,
            "counting_convention": (
                "nontrivial zeta zeros with 0 < Im(rho) <= height, "
                "counted with multiplicity"
            ),
            "versions": backend.version_record(),
            "lean_atom_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0


def command_isolate(args: argparse.Namespace) -> int:
    backend = FlintZetaBackend()
    ordinates = backend.isolate_ordinates(
        args.first_index, args.count, args.precision_bits
    )
    digest = hashlib.sha256()
    previous_upper: Fraction | None = None
    minimum_gap: Fraction | None = None
    for offset, ordinate in enumerate(ordinates):
        index = args.first_index + offset
        digest.update(
            (
                f"{index}:{ordinate.lower.numerator}/{ordinate.lower.denominator}:"
                f"{ordinate.upper.numerator}/{ordinate.upper.denominator}\n"
            ).encode("ascii")
        )
        if previous_upper is not None:
            if not previous_upper < ordinate.lower:
                raise ZetaCampaignError(
                    f"ordinate intervals {index - 1} and {index} overlap"
                )
            gap = ordinate.lower - previous_upper
            minimum_gap = gap if minimum_gap is None else min(minimum_gap, gap)
        previous_upper = ordinate.upper
    _emit(
        {
            "accepted": True,
            "classification": "fresh_external_flint_indexed_isolation_batch",
            "first_index": args.first_index,
            "last_index": args.first_index + args.count - 1,
            "record_count": len(ordinates),
            "all_real_parts_exactly_one_half": True,
            "all_ordinates_positive_and_strictly_disjoint": True,
            "first_ordinate": ordinates[0],
            "last_ordinate": ordinates[-1],
            "minimum_internal_gap": minimum_gap,
            "ordinate_intervals_sha256": digest.hexdigest(),
            "versions": backend.version_record(),
            "lean_atom_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0


def command_init(args: argparse.Namespace) -> int:
    result = initialize_campaign(
        args.directory,
        PROFILES[args.profile],
        batch_size=args.batch_size,
        precision_bits=args.precision_bits,
    )
    _emit(result, pretty=args.pretty)
    return 0


def command_run(args: argparse.Namespace) -> int:
    result = run_campaign(
        args.directory,
        max_chunks=args.max_chunks,
        replay_count=not args.skip_count_replay,
    )
    _emit(result, pretty=args.pretty)
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    _emit(finalize_campaign(args.directory), pretty=args.pretty)
    return 0


def command_verify(args: argparse.Namespace) -> int:
    _emit(
        verify_campaign(args.directory, require_complete=args.complete),
        pretty=args.pretty,
    )
    return 0


def command_replay_chunk(args: argparse.Namespace) -> int:
    _emit(replay_chunk(args.directory, args.chunk_index), pretty=args.pretty)
    return 0


def command_full(args: argparse.Namespace) -> int:
    initialized = initialize_campaign(
        args.directory,
        PROFILES[args.profile],
        batch_size=args.batch_size,
        precision_bits=args.precision_bits,
    )
    run = run_campaign(args.directory, max_chunks=None, replay_count=True)
    final = finalize_campaign(args.directory)
    _emit(
        {
            "accepted": True,
            "classification": "complete_external_flint_run_with_chunk_replay",
            "initialized": initialized,
            "run": run,
            "final": final,
            "lean_atom_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    subcommands = parser.add_subparsers(dest="command", required=True)

    profiles = subcommands.add_parser(
        "profiles", help="show the immutable named-atom source parameters"
    )
    profiles.set_defaults(handler=command_profiles)

    count = subcommands.add_parser(
        "count", help="compute exact multiplicity-counted N(height) with FLINT"
    )
    count.add_argument("--height", type=_positive_int, required=True)
    count.add_argument("--expected", type=_nonnegative_int)
    count.add_argument("--precision-bits", type=_precision, default=96)
    count.set_defaults(handler=command_count)

    isolate = subcommands.add_parser(
        "isolate", help="rigorously isolate an arbitrary consecutive index batch"
    )
    isolate.add_argument("--first-index", type=_positive_int, required=True)
    isolate.add_argument("--count", type=_batch_size, required=True)
    isolate.add_argument("--precision-bits", type=_precision, default=96)
    isolate.set_defaults(handler=command_isolate)

    initialize = subcommands.add_parser(
        "init", help="compute the exact count and initialize an immutable campaign"
    )
    initialize.add_argument("directory", type=Path)
    initialize.add_argument("--profile", choices=sorted(PROFILES), required=True)
    initialize.add_argument("--batch-size", type=_batch_size, default=4_096)
    initialize.add_argument("--precision-bits", type=_precision, default=96)
    initialize.set_defaults(handler=command_init)

    run = subcommands.add_parser(
        "run", help="resume a campaign from its first absent hash-linked chunk"
    )
    run.add_argument("directory", type=Path)
    run.add_argument(
        "--max-chunks",
        type=_nonnegative_int,
        help="stop after this many new chunks; omit to finish",
    )
    run.add_argument(
        "--skip-count-replay",
        action="store_true",
        help="skip the normally repeated exact N(height) check for this invocation",
    )
    run.set_defaults(handler=command_run)

    finalize = subcommands.add_parser(
        "finalize", help="check the complete chain and write immutable final.json"
    )
    finalize.add_argument("directory", type=Path)
    finalize.set_defaults(handler=command_finalize)

    verify = subcommands.add_parser(
        "verify", help="structurally audit a partial or complete retained campaign"
    )
    verify.add_argument("directory", type=Path)
    verify.add_argument(
        "--complete", action="store_true", help="require all chunks and final.json"
    )
    verify.set_defaults(handler=command_verify)

    replay = subcommands.add_parser(
        "replay-chunk", help="freshly recompute one retained FLINT chunk"
    )
    replay.add_argument("directory", type=Path)
    replay.add_argument("chunk_index", type=_nonnegative_int)
    replay.set_defaults(handler=command_replay_chunk)

    full = subcommands.add_parser(
        "full", help="initialize, run every batch, and finalize one named profile"
    )
    full.add_argument("directory", type=Path)
    full.add_argument("--profile", choices=sorted(PROFILES), required=True)
    full.add_argument("--batch-size", type=_batch_size, default=4_096)
    full.add_argument("--precision-bits", type=_precision, default=96)
    full.set_defaults(handler=command_full)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (ZetaCampaignError, OSError, ValueError) as error:
        _emit(
            {
                "accepted": False,
                "classification": "zeta_campaign_failed_closed",
                "error": str(error),
                "lean_atom_discharged": False,
            },
            pretty=args.pretty,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
