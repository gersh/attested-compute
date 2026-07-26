#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build, inspect, replay, and benchmark Dirichlet root-number artifacts."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_root_number_stage import (  # noqa: E402
    capability,
    consume_streams,
    consume_transform_path,
    direct_replay_artifact,
    read_root_artifact,
    source_work,
    verify_additive_input,
    write_additive_input,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} is not a JSON object")
    return value


def _input_stream(path: str):
    if path == "-":
        return nullcontext(sys.stdin.buffer)
    return Path(path).open("rb")


def _output_stream(path: str):
    if path == "-":
        return nullcontext(sys.stdout.buffer)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.open("wb")


def _run_transform(
    executable: Path,
    *,
    kind: str,
    input_path: Path,
    output_path: Path,
    precision: int,
    device: int,
) -> dict[str, object]:
    if kind == "mpfr":
        command = [
            str(executable.resolve()),
            "compute",
            str(input_path),
            str(output_path),
            str(precision),
        ]
    else:
        command = [
            str(executable.resolve()),
            str(input_path),
            str(output_path),
            str(device),
            "1",
        ]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    lines = completed.stdout.strip().splitlines()
    return json.loads(lines[-1]) if lines else {"command": command}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    commands.add_parser("source-work")

    additive = commands.add_parser("additive-input")
    additive.add_argument("input", type=Path)
    additive.add_argument("receipt", type=Path)
    additive.add_argument("--q", type=int, required=True)
    additive.add_argument("--precision", type=int, default=192)

    verify_additive = commands.add_parser("verify-additive")
    verify_additive.add_argument("input", type=Path)
    verify_additive.add_argument("receipt", type=Path)
    verify_additive.add_argument("--replay-arithmetic", action="store_true")

    consume = commands.add_parser("consume")
    consume.add_argument("transform", type=Path)
    consume.add_argument("root", type=Path)
    consume.add_argument("root_receipt", type=Path)
    consume.add_argument("--q", type=int, required=True)
    consume.add_argument("--additive-receipt", type=Path, required=True)
    consume.add_argument("--precision", type=int, default=192)

    inspect = commands.add_parser("inspect-root")
    inspect.add_argument("root", type=Path)
    inspect.add_argument("--receipt", type=Path)

    direct = commands.add_parser("direct-replay")
    direct.add_argument("root", type=Path)
    direct.add_argument("receipt", type=Path)
    direct.add_argument("--precision", type=int, default=256)

    stream = commands.add_parser("consume-stream")
    stream.add_argument("control")
    stream.add_argument("transforms")
    stream.add_argument("roots")
    stream.add_argument("receipts")
    stream.add_argument("summary", type=Path)
    stream.add_argument("--precision", type=int, default=192)

    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--runner", type=Path, required=True)
    benchmark.add_argument("--runner-kind", choices=("cuda", "mpfr"), required=True)
    benchmark.add_argument("--q", type=int, default=10_007)
    benchmark.add_argument("--precision", type=int, default=192)
    benchmark.add_argument("--device", type=int, default=0)
    args = parser.parse_args()

    try:
        if args.command in {"additive-input", "consume", "benchmark"}:
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(args.q * max(0, args.q - 1),),
            )
        elif args.command == "verify-additive" and args.replay_arithmetic:
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
        elif args.command in {"direct-replay", "consume-stream"}:
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
    except MeasuredWorkerScopeError as error:
        print(f"Dirichlet root-number stage error: {error}", file=sys.stderr)
        return 2

    if args.command == "capability":
        result = capability()
    elif args.command == "source-work":
        result = source_work()
    elif args.command == "additive-input":
        result = write_additive_input(
            args.input,
            q=args.q,
            precision=args.precision,
            receipt_path=args.receipt,
        )
    elif args.command == "verify-additive":
        result = verify_additive_input(
            args.input,
            _read_json(args.receipt),
            replay_arithmetic=args.replay_arithmetic,
        )
    elif args.command == "consume":
        result = consume_transform_path(
            args.transform,
            args.root,
            args.root_receipt,
            q=args.q,
            additive_receipt=_read_json(args.additive_receipt),
            precision=args.precision,
        )
    elif args.command == "inspect-root":
        receipt = _read_json(args.receipt) if args.receipt else None
        result, _roots = read_root_artifact(args.root, receipt)
    elif args.command == "direct-replay":
        result = direct_replay_artifact(
            args.root,
            _read_json(args.receipt),
            precision=args.precision,
        )
    elif args.command == "consume-stream":
        with (
            _input_stream(args.control) as controls,
            _input_stream(args.transforms) as transforms,
            _output_stream(args.roots) as roots,
            _output_stream(args.receipts) as receipts,
        ):
            result = consume_streams(
                controls,
                transforms,
                roots,
                receipts,
                args.summary,
                precision=args.precision,
            )
        if args.roots == "-" or args.receipts == "-":
            print(
                json.dumps(result, sort_keys=True, indent=2 if args.pretty else None),
                file=sys.stderr,
            )
            return 0
    else:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "additive.bin"
            input_receipt_path = root / "additive.json"
            transform_path = root / "transform.bin"
            root_path = root / "roots.bin"
            root_receipt_path = root / "roots.json"
            start = time.perf_counter_ns()
            additive_receipt = write_additive_input(
                input_path,
                q=args.q,
                precision=args.precision,
                receipt_path=input_receipt_path,
            )
            input_stop = time.perf_counter_ns()
            runner = _run_transform(
                args.runner,
                kind=args.runner_kind,
                input_path=input_path,
                output_path=transform_path,
                precision=args.precision,
                device=args.device,
            )
            transform_stop = time.perf_counter_ns()
            receipt = consume_transform_path(
                transform_path,
                root_path,
                root_receipt_path,
                q=args.q,
                additive_receipt=additive_receipt,
                precision=args.precision,
            )
            end = time.perf_counter_ns()
            input_seconds = (input_stop - start) / 1_000_000_000
            invocation_seconds = (transform_stop - input_stop) / 1_000_000_000
            normalization_seconds = (end - transform_stop) / 1_000_000_000
            result = {
                "kind": "sparkinterval.tg.dirichlet_root.benchmark.v1",
                "classification": "local_component_measurement_not_h100_projection_or_grh_evidence",
                "q": args.q,
                "runner_kind": args.runner_kind,
                "precision_bits": args.precision,
                "group_order": receipt["group_order"],
                "primitive_character_count": receipt["primitive_character_count"],
                "radix2_butterflies": receipt["radix2_butterflies"],
                "additive_input_seconds": input_seconds,
                "transform_process_wall_seconds": invocation_seconds,
                "root_normalization_seconds": normalization_seconds,
                "total_seconds": (end - start) / 1_000_000_000,
                "additive_group_values_per_second": receipt["group_order"] / input_seconds,
                "primitive_roots_per_second": receipt["primitive_character_count"] / normalization_seconds,
                "runner_report": runner,
                "full_source_campaign_run": False,
                "external_atom_discharged": False,
            }

    print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
