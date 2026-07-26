#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Produce/replay small-q time-tail controls or reduce TGDBSQR3 to signs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_booker_smallq_factored import (  # noqa: E402
    FactoredSmallQError,
)
from tg_verifier.dirichlet_booker_smallq import (  # noqa: E402
    DirichletBookerSmallQError,
)
from tg_verifier.dirichlet_booker_smallq_compact_v3 import (  # noqa: E402
    SmallQCompactV3Error,
    load_pinset,
    reduce_factored_service_stream_to_compact_v3,
)
from tg_verifier.dirichlet_booker_smallq_semantic_reducer import (  # noqa: E402
    DEFAULT_CHUNK_ITEMS,
    SmallQSemanticReducerError,
    inspect_sign_artifact,
    reduce_semantic_sign_stream,
    verify_time_tail_control,
    write_time_tail_control,
)
from tg_verifier.dirichlet_booker_smallq_packed_stream_v1 import (  # noqa: E402
    SmallQPackedStreamV1Error,
    reduce_packed_stream_to_compact_v3,
)
from tg_verifier.dirichlet_compact_state_streaming_v3 import (  # noqa: E402
    DirichletCompactStateV3Error,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def _batches(directory: Path) -> list[Path]:
    return sorted(directory.glob("batch-*.bin"))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    produce = commands.add_parser(
        "produce-control",
        help="materialize untrusted even/odd time-tail-over-scale controls",
    )
    produce.add_argument("plan", type=Path)
    produce.add_argument("batch_directory", type=Path)
    produce.add_argument("control", type=Path)
    produce.add_argument("--precision-bits", type=_positive, default=192)

    verify = commands.add_parser(
        "verify-control",
        help="higher-precision replay every time-tail control record",
    )
    verify.add_argument("plan", type=Path)
    verify.add_argument("batch_directory", type=Path)
    verify.add_argument("control", type=Path)
    verify.add_argument("receipt", type=Path)
    verify.add_argument("--guard-bits", type=_positive, default=64)

    reduce = commands.add_parser(
        "reduce",
        help="consume a complete TGDBSQR3 stream and emit two-bit signs",
    )
    reduce.add_argument("plan", type=Path)
    reduce.add_argument("batch_directory", type=Path)
    reduce.add_argument("control", type=Path)
    reduce.add_argument("control_receipt", type=Path)
    reduce.add_argument("sign_artifact", type=Path)
    reduce.add_argument("receipt", type=Path)
    reduce.add_argument(
        "--input",
        type=Path,
        help="concatenated TGDBSQR3 path/FIFO; omit to read standard input",
    )
    reduce.add_argument("--chunk-items", type=_positive, default=DEFAULT_CHUNK_ITEMS)
    reduce.add_argument("--backend", choices=("auto", "numpy", "scalar"), default="auto")

    compact = commands.add_parser(
        "reduce-compact-v3",
        help=(
            "consume TGDBSQR3 directly into TGDCSB03 under an externally "
            "pinned canonical pinset"
        ),
    )
    compact.add_argument("plan", type=Path)
    compact.add_argument("batch_directory", type=Path)
    compact.add_argument("control", type=Path)
    compact.add_argument("control_receipt", type=Path)
    compact.add_argument("pinset", type=Path)
    compact.add_argument("state_artifact", type=Path)
    compact.add_argument("receipt", type=Path)
    compact.add_argument(
        "--expected-pinset-sha256",
        required=True,
        help="out-of-band lowercase SHA-256 of the typed pinset",
    )
    compact.add_argument(
        "--input",
        type=Path,
        help="concatenated TGDBSQR3 path/FIFO; omit to read standard input",
    )
    compact.add_argument(
        "--chunk-items", type=_positive, default=DEFAULT_CHUNK_ITEMS
    )
    compact.add_argument(
        "--backend", choices=("auto", "numpy", "scalar"), default="auto"
    )

    packed_compact = commands.add_parser(
        "reduce-packed-compact-v3",
        help=(
            "consume a terminally sealed TGDBSPK1 runner stream directly "
            "into TGDCSB03 under an externally pinned canonical pinset"
        ),
    )
    packed_compact.add_argument("plan", type=Path)
    packed_compact.add_argument("batch_directory", type=Path)
    packed_compact.add_argument("control", type=Path)
    packed_compact.add_argument("control_receipt", type=Path)
    packed_compact.add_argument("pinset", type=Path)
    packed_compact.add_argument("state_artifact", type=Path)
    packed_compact.add_argument("receipt", type=Path)
    packed_compact.add_argument(
        "--expected-pinset-sha256",
        required=True,
        help="out-of-band lowercase SHA-256 of the typed pinset",
    )
    packed_compact.add_argument(
        "--input",
        type=Path,
        help="TGDBSPK1 path/FIFO; omit to read standard input",
    )
    packed_compact.add_argument(
        "--chunk-items", type=_positive, default=DEFAULT_CHUNK_ITEMS
    )
    packed_compact.add_argument(
        "--expected-packing-location",
        choices=("host", "device"),
        default="host",
        help=(
            "pin the TGDBSPK1 classifier location; host and device frame "
            "identities are not interchangeable"
        ),
    )

    inspect = commands.add_parser(
        "inspect-signs", help="structurally inspect a bounded TGDBSSG1 artifact"
    )
    inspect.add_argument("sign_artifact", type=Path)

    result.add_argument("--pretty", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command != "inspect-signs":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
        if args.command == "produce-control":
            value = write_time_tail_control(
                args.control,
                args.plan,
                _batches(args.batch_directory),
                precision_bits=args.precision_bits,
            )
        elif args.command == "verify-control":
            value = verify_time_tail_control(
                args.control,
                args.plan,
                _batches(args.batch_directory),
                guard_bits=args.guard_bits,
                receipt_path=args.receipt,
            )
        elif args.command == "reduce":
            batches = _batches(args.batch_directory)
            if args.input is None:
                value = reduce_semantic_sign_stream(
                    args.plan,
                    batches,
                    args.control,
                    args.control_receipt,
                    sys.stdin.buffer,
                    args.sign_artifact,
                    receipt_path=args.receipt,
                    chunk_items=args.chunk_items,
                    backend=args.backend,
                )
            else:
                with args.input.open("rb", buffering=0) as stream:
                    value = reduce_semantic_sign_stream(
                        args.plan,
                        batches,
                        args.control,
                        args.control_receipt,
                        stream,
                        args.sign_artifact,
                        receipt_path=args.receipt,
                        chunk_items=args.chunk_items,
                        backend=args.backend,
                    )
        elif args.command == "reduce-compact-v3":
            batches = _batches(args.batch_directory)
            pins = load_pinset(
                args.pinset,
                expected_pinset_sha256=args.expected_pinset_sha256,
            )
            if args.input is None:
                value = reduce_factored_service_stream_to_compact_v3(
                    args.plan,
                    batches,
                    args.control,
                    args.control_receipt,
                    sys.stdin.buffer,
                    args.state_artifact,
                    pins=pins,
                    receipt_path=args.receipt,
                    chunk_items=args.chunk_items,
                    backend=args.backend,
                )
            else:
                with args.input.open("rb", buffering=0) as stream:
                    value = reduce_factored_service_stream_to_compact_v3(
                        args.plan,
                        batches,
                        args.control,
                        args.control_receipt,
                        stream,
                        args.state_artifact,
                        pins=pins,
                        receipt_path=args.receipt,
                        chunk_items=args.chunk_items,
                        backend=args.backend,
                    )
        elif args.command == "reduce-packed-compact-v3":
            batches = _batches(args.batch_directory)
            pins = load_pinset(
                args.pinset,
                expected_pinset_sha256=args.expected_pinset_sha256,
            )
            if args.input is None:
                value = reduce_packed_stream_to_compact_v3(
                    args.plan,
                    batches,
                    args.control,
                    args.control_receipt,
                    sys.stdin.buffer,
                    args.state_artifact,
                    pins=pins,
                    receipt_path=args.receipt,
                    chunk_items=args.chunk_items,
                    expected_packing_location=args.expected_packing_location,
                )
            else:
                with args.input.open("rb", buffering=0) as stream:
                    value = reduce_packed_stream_to_compact_v3(
                        args.plan,
                        batches,
                        args.control,
                        args.control_receipt,
                        stream,
                        args.state_artifact,
                        pins=pins,
                        receipt_path=args.receipt,
                        chunk_items=args.chunk_items,
                        expected_packing_location=args.expected_packing_location,
                    )
        else:
            value = {
                "kind": (
                    "sparkinterval.tg.dirichlet_booker_smallq."
                    "semantic_sign_inspection.v1"
                ),
                **inspect_sign_artifact(args.sign_artifact),
            }
    except (
        OSError,
        DirichletBookerSmallQError,
        DirichletCompactStateV3Error,
        FactoredSmallQError,
        SmallQCompactV3Error,
        SmallQPackedStreamV1Error,
        SmallQSemanticReducerError,
        MeasuredWorkerScopeError,
    ) as error:
        print(
            f"tg_dirichlet_booker_smallq_semantic_reducer: {error}",
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            value,
            indent=2 if args.pretty else None,
            sort_keys=True,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
