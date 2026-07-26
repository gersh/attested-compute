#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""CLI for the persistent TGDAFFO1 completed-L/sign consumer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_stream_zero_consumer import (
    COMPACT_EVENT_STORAGE_MODE,
    DirichletStreamConsumerError,
    PHASE_COMPACT_BUNDLE_STORAGE_MODE,
    RAW_EVENT_STORAGE_MODE,
    benchmark,
    capability,
    canonical_json_bytes,
    consume_paths,
    consume_streams,
    direct_root_source_work,
    root_number_inventory,
    verify_paths,
    write_known_answer_bundle,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _print(value: object, *, pretty: bool) -> None:
    if pretty:
        sys.stdout.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.buffer.write(canonical_json_bytes(value))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    subcommands = result.add_subparsers(dest="command", required=True)

    subcommands.add_parser("capability")

    roots = subcommands.add_parser("root-inventory")
    roots.add_argument("q", type=int)
    roots.add_argument("--precision", type=int, default=192)

    subcommands.add_parser("root-work")

    consume = subcommands.add_parser("consume")
    consume.add_argument("control", type=Path)
    consume.add_argument(
        "frames",
        help="concatenated TGDAFFO1 file, or '-' for a persistent stdin pipe",
    )
    consume.add_argument("events", type=Path)
    consume.add_argument("receipt", type=Path)
    consume.add_argument("--precision", type=int, default=192)
    consume.add_argument("--root-artifact", type=Path)
    consume.add_argument("--root-receipt", type=Path)
    consume.add_argument("--schedule-manifest", type=Path)
    consume.add_argument("--require-full-source-schedule", action="store_true")
    consume.add_argument("--phase-plan-sha256")
    consume.add_argument("--phase-first-t-index", type=int)
    consume.add_argument("--phase-stop-t-index-exclusive", type=int)
    consume.add_argument("--phase-execution-q-start-index", type=int)
    consume.add_argument("--phase-execution-q-stop-index", type=int)
    consume.add_argument("--root-catalog", type=Path)
    consume.add_argument("--root-catalog-sha256")
    consume.add_argument("--root-catalog-directory", type=Path)
    consume.add_argument(
        "--maximum-event-bytes",
        type=int,
        help="fail before the retained event stream exceeds this byte budget",
    )
    consume.add_argument(
        "--event-storage-mode",
        choices=(
            RAW_EVENT_STORAGE_MODE,
            COMPACT_EVENT_STORAGE_MODE,
            PHASE_COMPACT_BUNDLE_STORAGE_MODE,
        ),
        default=RAW_EVENT_STORAGE_MODE,
    )
    consume.add_argument(
        "--timing-output",
        type=Path,
        help="optional bounded diagnostic wall-time record (not proof evidence)",
    )

    verify = subcommands.add_parser("verify")
    verify.add_argument("control", type=Path)
    verify.add_argument("frames", type=Path)
    verify.add_argument("events", type=Path)
    verify.add_argument("receipt", type=Path)
    verify.add_argument("--precision", type=int, default=192)
    verify.add_argument("--root-artifact", type=Path)
    verify.add_argument("--root-receipt", type=Path)
    verify.add_argument("--schedule-manifest", type=Path)
    verify.add_argument("--require-full-source-schedule", action="store_true")
    verify.add_argument("--root-catalog", type=Path)
    verify.add_argument("--root-catalog-sha256")
    verify.add_argument("--root-catalog-directory", type=Path)

    known = subcommands.add_parser("known-answer")
    known.add_argument("output_directory", type=Path)

    timing = subcommands.add_parser("benchmark")
    timing.add_argument("--q", type=int, default=29)
    timing.add_argument("--batch-count", type=int, default=64)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    started = time.perf_counter()
    try:
        if args.command == "capability":
            answer = capability()
        elif args.command == "root-inventory":
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(args.q * max(0, args.q - 1),),
            )
            answer = root_number_inventory(args.q, precision=args.precision)
        elif args.command == "root-work":
            answer = direct_root_source_work()
        elif args.command == "consume":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            if args.frames == "-":
                with args.control.open("rb") as control:
                    answer = consume_streams(
                        control,
                        sys.stdin.buffer,
                        args.events,
                        args.receipt,
                        precision=args.precision,
                        root_artifact_path=args.root_artifact,
                        root_receipt_path=args.root_receipt,
                        schedule_manifest_path=args.schedule_manifest,
                        require_full_source_schedule=(
                            args.require_full_source_schedule
                        ),
                        root_catalog_path=args.root_catalog,
                        root_catalog_sha256=args.root_catalog_sha256,
                        root_catalog_directory=args.root_catalog_directory,
                        maximum_event_bytes=args.maximum_event_bytes,
                        event_storage_mode=args.event_storage_mode,
                        phase_plan_sha256=args.phase_plan_sha256,
                        phase_first_t_index=args.phase_first_t_index,
                        phase_stop_t_index_exclusive=(
                            args.phase_stop_t_index_exclusive
                        ),
                        phase_execution_q_start_index=(
                            args.phase_execution_q_start_index
                        ),
                        phase_execution_q_stop_index=(
                            args.phase_execution_q_stop_index
                        ),
                    )
            else:
                answer = consume_paths(
                    args.control,
                    Path(args.frames),
                    args.events,
                    args.receipt,
                    precision=args.precision,
                    root_artifact_path=args.root_artifact,
                    root_receipt_path=args.root_receipt,
                    schedule_manifest_path=args.schedule_manifest,
                    require_full_source_schedule=(
                        args.require_full_source_schedule
                    ),
                    root_catalog_path=args.root_catalog,
                    root_catalog_sha256=args.root_catalog_sha256,
                    root_catalog_directory=args.root_catalog_directory,
                    maximum_event_bytes=args.maximum_event_bytes,
                    event_storage_mode=args.event_storage_mode,
                    phase_plan_sha256=args.phase_plan_sha256,
                    phase_first_t_index=args.phase_first_t_index,
                    phase_stop_t_index_exclusive=(
                        args.phase_stop_t_index_exclusive
                    ),
                    phase_execution_q_start_index=(
                        args.phase_execution_q_start_index
                    ),
                    phase_execution_q_stop_index=(
                        args.phase_execution_q_stop_index
                    ),
                )
        elif args.command == "verify":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            answer = verify_paths(
                args.control,
                args.frames,
                args.events,
                args.receipt,
                precision=args.precision,
                root_artifact_path=args.root_artifact,
                root_receipt_path=args.root_receipt,
                schedule_manifest_path=args.schedule_manifest,
                require_full_source_schedule=(
                    args.require_full_source_schedule
                ),
                root_catalog_path=args.root_catalog,
                root_catalog_sha256=args.root_catalog_sha256,
                root_catalog_directory=args.root_catalog_directory,
            )
        elif args.command == "known-answer":
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(1,),
            )
            answer = write_known_answer_bundle(args.output_directory)
        elif args.command == "benchmark":
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(
                    (args.q + args.batch_count)
                    * max(0, args.q - 1),
                ),
            )
            answer = benchmark(q=args.q, batch_count=args.batch_count)
        else:  # pragma: no cover - argparse enforces a command
            raise AssertionError(args.command)
    except (DirichletStreamConsumerError, OSError, ValueError) as error:
        print(f"Dirichlet stream consumer error: {error}", file=sys.stderr)
        return 2
    timing_output = getattr(args, "timing_output", None)
    if timing_output is not None:
        if timing_output.exists():
            print(
                "Dirichlet stream consumer error: refusing to replace "
                "timing output",
                file=sys.stderr,
            )
            return 2
        timing = {
            "schema": (
                "sparkinterval.tg.dirichlet_stream_consumer.timing.v1"
            ),
            "classification": "diagnostic_wall_time_not_proof_evidence",
            "elapsed_seconds": time.perf_counter() - started,
            "receipt_sha256": (
                answer.get("receipt_sha256")
                if isinstance(answer, dict)
                else None
            ),
            "zero_completeness_claimed": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        }
        timing["timing_sha256"] = hashlib.sha256(
            canonical_json_bytes(timing)
        ).hexdigest()
        timing_output.parent.mkdir(parents=True, exist_ok=True)
        timing_output.write_bytes(canonical_json_bytes(timing))
    _print(answer, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
