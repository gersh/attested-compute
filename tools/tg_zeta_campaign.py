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
import os
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)
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
    render_head_q128_lean_module,
    retained_head_q128_cells,
    run_campaign,
    verify_campaign,
    write_once,
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


def _write_registered_result(path: Path) -> None:
    """Create the exact registered Boolean result without replacing a file."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for optional in ("O_CLOEXEC", "O_NOFOLLOW"):
        flags |= getattr(os, optional, 0)
    descriptor = os.open(path, flags, 0o400)
    try:
        raw = b"true"
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short registered-result write")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


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
    # Height is the extent of this count-from-zero workload, not merely an
    # identifying endpoint.  Counts through height 64 remain useful local KATs.
    require_azure_measured_worker_for_workload(
        exact_production=False,
        work_bounds=(args.height,),
    )
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
    # Only the first at-most-64 indexed ordinates are a local KAT.  A short
    # batch at a very high index can still require production-scale work.
    require_azure_measured_worker_for_workload(
        exact_production=args.first_index != 1,
        work_bounds=(args.count,),
    )
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
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    result = initialize_campaign(
        args.directory,
        PROFILES[args.profile],
        batch_size=args.batch_size,
        precision_bits=args.precision_bits,
    )
    _emit(result, pretty=args.pretty)
    return 0


def command_run(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    result = run_campaign(
        args.directory,
        max_chunks=args.max_chunks,
        replay_count=not args.skip_count_replay,
    )
    _emit(result, pretty=args.pretty)
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    _emit(finalize_campaign(args.directory), pretty=args.pretty)
    return 0


def command_verify(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    _emit(
        verify_campaign(args.directory, require_complete=args.complete),
        pretty=args.pretty,
    )
    return 0


def command_replay_chunk(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    _emit(replay_chunk(args.directory, args.chunk_index), pretty=args.pretty)
    return 0


def command_full(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    if (
        args.registered_result_output is not None
        and args.profile != "platt-head-2e4"
    ):
        raise ZetaCampaignError(
            "the registered result is defined only for platt-head-2e4"
        )
    initialized = initialize_campaign(
        args.directory,
        PROFILES[args.profile],
        batch_size=args.batch_size,
        precision_bits=args.precision_bits,
    )
    run = run_campaign(args.directory, max_chunks=None, replay_count=True)
    final = finalize_campaign(args.directory)
    if args.registered_result_output is not None:
        chunk_count = run.get("chunks_total")
        if (
            isinstance(chunk_count, bool)
            or not isinstance(chunk_count, int)
            or chunk_count <= 0
            or run.get("complete") is not True
        ):
            raise ZetaCampaignError(
                "registered Platt-head output requires a complete campaign"
            )
        for chunk_index in range(chunk_count):
            replay_chunk(args.directory, chunk_index)
        cells = retained_head_q128_cells(args.directory)
        # Rendering is part of the registered semantics: it rechecks the exact
        # named 22,491-row commitment even though this legacy terminal retains
        # the campaign rather than a second copy of the generated module.
        render_head_q128_lean_module(cells)
        # No registered result exists until complete execution, fresh replay,
        # final-chain validation, and both reviewed table commitments pass.
        _write_registered_result(args.registered_result_output)
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


def command_emit_lean_table(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    cells = retained_head_q128_cells(args.directory)
    source = render_head_q128_lean_module(cells, namespace=args.namespace)
    raw = source.encode("utf-8")
    write_once(args.output, raw)
    _emit(
        {
            "accepted": True,
            "classification": "complete_reviewed_platt_head_q128_lean_table",
            "output": str(args.output),
            "output_sha256": hashlib.sha256(raw).hexdigest(),
            "row_count": len(cells),
            "rows_sha256": (
                "e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7"
            ),
            "all_rows_with_sentinel_sha256": (
                "fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca"
            ),
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

    emit_lean = subcommands.add_parser(
        "emit-lean-table",
        help="generate the exact reviewed Q128 Lean table from a complete head run",
    )
    emit_lean.add_argument("directory", type=Path)
    emit_lean.add_argument("output", type=Path)
    emit_lean.add_argument(
        "--namespace",
        default="SparkInterval.Generated.PlattHeadQ128",
    )
    emit_lean.set_defaults(handler=command_emit_lean_table)

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
    full.add_argument(
        "--registered-result-output",
        type=Path,
        help=(
            "exclusively create literal `true` after the complete campaign "
            "has finalized"
        ),
    )
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
