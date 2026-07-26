#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Compose certified large-q residue rectangles into TGDAFFI1 batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_residue_composition import (  # noqa: E402
    CompositionEngine,
    DEFAULT_FACTOR_PRECISION_BITS,
    DEFAULT_MAX_BATCH_COUNT,
    DirichletResidueCompositionError,
    FRAMED_REQUEST_SCHEMA,
    JOB_SCHEMA,
    SERVICE_REQUEST_SCHEMA,
    benchmark_synthetic,
    capability,
    canonical_json_bytes,
    source_work,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (  # noqa: E402
    DirichletAllCharsQSchedulerError,
    FULL_SOURCE_CLASSIFICATION,
    SCHEDULER_ALGORITHM_ID,
    parse_schedule_manifest,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _emit(value: object, *, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def _service_request(raw: bytes, *, base: Path) -> tuple[Path, Path, Path | None]:
    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DirichletResidueCompositionError(
            "persistent request is not JSON"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise DirichletResidueCompositionError(
            "persistent request is not one canonical JSON line"
        )
    if set(value) != {"schema", "schema_version", "job", "output", "receipt"}:
        raise DirichletResidueCompositionError("persistent request fields changed")
    if value.get("schema") != SERVICE_REQUEST_SCHEMA or value.get("schema_version") != 1:
        raise DirichletResidueCompositionError("persistent request schema mismatch")
    paths = []
    for name in ("job", "output"):
        raw_path = value.get(name)
        if not isinstance(raw_path, str) or not raw_path:
            raise DirichletResidueCompositionError(
                f"persistent request {name} path is invalid"
            )
        path = Path(raw_path)
        paths.append(path if path.is_absolute() else base / path)
    receipt_value = value.get("receipt")
    if receipt_value is not None and (
        not isinstance(receipt_value, str) or not receipt_value
    ):
        raise DirichletResidueCompositionError(
            "persistent request receipt path is invalid"
        )
    receipt = None if receipt_value is None else Path(receipt_value)
    if receipt is not None and not receipt.is_absolute():
        receipt = base / receipt
    return paths[0], paths[1], receipt


def _framed_request(raw: bytes, *, base: Path) -> tuple[Path, Path]:
    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DirichletResidueCompositionError(
            "framed request is not JSON"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise DirichletResidueCompositionError(
            "framed request is not one canonical JSON line"
        )
    if set(value) != {"schema", "schema_version", "job", "receipt"}:
        raise DirichletResidueCompositionError("framed request fields changed")
    if value.get("schema") != FRAMED_REQUEST_SCHEMA or value.get("schema_version") != 1:
        raise DirichletResidueCompositionError("framed request schema mismatch")
    paths = []
    for name in ("job", "receipt"):
        raw_path = value.get(name)
        if not isinstance(raw_path, str) or not raw_path:
            raise DirichletResidueCompositionError(
                f"framed request {name} path is invalid"
            )
        path = Path(raw_path)
        paths.append(path if path.is_absolute() else base / path)
    return paths[0], paths[1]


def _job_identity(path: Path) -> tuple[int, int, int, int, int]:
    try:
        raw = path.read_bytes()
        value: Any = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise DirichletResidueCompositionError(
            "cannot inspect framed composition job"
        ) from error
    if (
        not isinstance(value, dict)
        or canonical_json_bytes(value) != raw
        or value.get("schema") != JOB_SCHEMA
        or value.get("schema_version") != 1
        or type(value.get("q")) is not int
        or type(value.get("first_t_numerator")) is not int
        or type(value.get("t_denominator")) is not int
        or type(value.get("t_step_numerator")) is not int
        or not isinstance(value.get("frames"), list)
        or not value["frames"]
    ):
        raise DirichletResidueCompositionError(
            "framed composition job identity is malformed"
        )
    return (
        value["q"], value["first_t_numerator"], value["t_denominator"],
        value["t_step_numerator"], len(value["frames"]),
    )


class _AggregateWriter:
    def __init__(self, output: Any) -> None:
        self.output = output
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, raw: bytes | bytearray) -> None:
        self.output.write(raw)
        self.digest.update(raw)
        self.size += len(raw)

    def flush(self) -> None:
        self.output.flush()


def _merkle(digests: list[str]) -> str:
    if not digests:
        raise DirichletResidueCompositionError("cannot Merkle-hash no receipts")
    level = [hashlib.sha256(bytes.fromhex(value)).digest() for value in digests]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


def _write_summary(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise DirichletResidueCompositionError(
            f"refusing to replace immutable framed summary: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json_bytes(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--factor-precision-bits",
        type=_positive,
        default=DEFAULT_FACTOR_PRECISION_BITS,
    )
    parser.add_argument(
        "--max-batch-count", type=_positive, default=DEFAULT_MAX_BATCH_COUNT
    )
    parser.add_argument(
        "--backend", choices=("auto", "numpy", "scalar"), default="auto"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    work = commands.add_parser("work")
    work.add_argument("--batch-size", type=_positive, default=DEFAULT_MAX_BATCH_COUNT)

    compose = commands.add_parser("compose")
    compose.add_argument("job", type=Path)
    compose.add_argument("output", type=Path)
    compose.add_argument("--receipt", type=Path)
    compose.add_argument("--allow-synthetic-kat", action="store_true")

    serve = commands.add_parser(
        "serve",
        help=(
            "read canonical JSONL requests on stdin while retaining only one "
            "modulus plan; output paths may be named pipes"
        ),
    )
    serve.add_argument("--base", type=Path, default=Path.cwd())
    serve.add_argument("--allow-synthetic-kat", action="store_true")

    framed = commands.add_parser(
        "framed-produce",
        help=(
            "read canonical control JSONL on stdin and write only concatenated "
            "TGDAFFI1 frames on stdout for allchars --framed-service"
        ),
    )
    framed.add_argument("summary", type=Path)
    framed.add_argument("--base", type=Path, default=Path.cwd())
    framed.add_argument("--allow-synthetic-kat", action="store_true")
    framed.add_argument(
        "--schedule-manifest",
        type=Path,
        help=(
            "require jobs in the exact TGDQORD1 execution order and bind the "
            "manifest into the producer summary"
        ),
    )
    framed.add_argument(
        "--require-full-source-schedule",
        action="store_true",
        help="reject a bounded TGDQORD1 manifest",
    )

    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--q", type=_positive, default=10001)
    benchmark.add_argument("--values", type=_positive, default=100000)
    benchmark.add_argument("--repetitions", type=_positive, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "capability":
            result = capability()
        elif args.command == "work":
            result = source_work(batch_size=args.batch_size)
        elif args.command == "benchmark":
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(args.values * args.repetitions,),
            )
            result = benchmark_synthetic(
                q=args.q, values=args.values, repetitions=args.repetitions
            )
        elif args.command == "compose":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            engine = CompositionEngine(
                factor_precision_bits=args.factor_precision_bits,
                max_batch_count=args.max_batch_count,
                backend=args.backend,
            )
            result = engine.compose(
                args.job,
                args.output,
                receipt_path=args.receipt,
                allow_synthetic_kat=args.allow_synthetic_kat,
            )
        elif args.command == "serve":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            if args.pretty:
                raise DirichletResidueCompositionError(
                    "--pretty is incompatible with canonical JSONL service mode"
                )
            engine = CompositionEngine(
                factor_precision_bits=args.factor_precision_bits,
                max_batch_count=args.max_batch_count,
                backend=args.backend,
            )
            base = args.base.resolve()
            for raw in sys.stdin.buffer:
                if not raw.strip():
                    raise DirichletResidueCompositionError(
                        "blank persistent request lines are forbidden"
                    )
                job, output, receipt = _service_request(raw, base=base)
                report = engine.compose(
                    job,
                    output,
                    receipt_path=receipt,
                    allow_synthetic_kat=args.allow_synthetic_kat,
                )
                sys.stdout.buffer.write(canonical_json_bytes(report))
                sys.stdout.buffer.flush()
            return 0
        elif args.command == "framed-produce":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            if args.pretty:
                raise DirichletResidueCompositionError(
                    "--pretty is incompatible with the binary framed channel"
                )
            engine = CompositionEngine(
                factor_precision_bits=args.factor_precision_bits,
                max_batch_count=args.max_batch_count,
                backend=args.backend,
            )
            output = _AggregateWriter(sys.stdout.buffer)
            base = args.base.resolve()
            if (
                args.require_full_source_schedule
                and args.schedule_manifest is None
            ):
                raise DirichletResidueCompositionError(
                    "--require-full-source-schedule needs --schedule-manifest"
                )
            schedule = (
                None
                if args.schedule_manifest is None
                else parse_schedule_manifest(args.schedule_manifest)
            )
            if (
                args.require_full_source_schedule
                and schedule is not None
                and schedule.classification != FULL_SOURCE_CLASSIFICATION
            ):
                raise DirichletResidueCompositionError(
                    "production producer requires a full-source q-order manifest"
                )
            q: int | None = None
            first_q: int | None = None
            denominator: int | None = None
            step: int | None = None
            first_numerator: int | None = None
            next_numerator: int | None = None
            scheduled_index = 0
            scheduled_rows = 0
            scheduled_rows_for_q = 0
            frames = 0
            slices = 0
            values = 0
            receipt_digests: list[str] = []
            control_digest = hashlib.sha256()
            for raw in sys.stdin.buffer:
                if not raw.strip():
                    raise DirichletResidueCompositionError(
                        "blank framed request lines are forbidden"
                    )
                control_digest.update(raw)
                job, receipt_path = _framed_request(raw, base=base)
                identity = _job_identity(job)
                job_q, first, job_denominator, job_step, batch_count = identity
                if schedule is None:
                    if q is None:
                        q = job_q
                        first_q = job_q
                        denominator = job_denominator
                        step = job_step
                        first_numerator = first
                    elif (
                        job_q != q
                        or job_denominator != denominator
                        or job_step != step
                        or first != next_numerator
                    ):
                        raise DirichletResidueCompositionError(
                            "framed jobs are not one q and one contiguous "
                            "t progression"
                        )
                elif job_q != q:
                    if q is not None and scheduled_rows != scheduled_rows_for_q:
                        raise DirichletResidueCompositionError(
                            "scheduled producer ended a q before exact coverage"
                        )
                    if (
                        scheduled_index >= len(schedule.execution_records)
                        or job_q
                        != schedule.execution_records[scheduled_index].q
                    ):
                        raise DirichletResidueCompositionError(
                            "scheduled producer q differs from TGDQORD1"
                        )
                    if (
                        first != 0
                        or job_denominator != 64
                        or job_step != 5
                    ):
                        raise DirichletResidueCompositionError(
                            "scheduled producer requires the exact 5/64 "
                            "source progression from t=0"
                        )
                    q = job_q
                    if first_q is None:
                        first_q = job_q
                        first_numerator = first
                        denominator = job_denominator
                        step = job_step
                    scheduled_rows = 0
                    scheduled_rows_for_q = schedule.execution_records[
                        scheduled_index
                    ].t_index_count
                    scheduled_index += 1
                elif (
                    job_denominator != denominator
                    or job_step != step
                    or first != next_numerator
                ):
                    raise DirichletResidueCompositionError(
                        "scheduled same-q jobs are not one contiguous "
                        "t progression"
                    )
                if schedule is not None:
                    if (
                        scheduled_rows > scheduled_rows_for_q
                        or batch_count
                        > scheduled_rows_for_q - scheduled_rows
                    ):
                        raise DirichletResidueCompositionError(
                            "scheduled producer frame exceeds q row coverage"
                        )
                    scheduled_rows += batch_count
                next_numerator = first + batch_count * job_step
                report = engine.compose_stream(
                    job,
                    output,
                    receipt_path=receipt_path,
                    allow_synthetic_kat=args.allow_synthetic_kat,
                )
                frames += 1
                slices += report["batch_count"]
                values += report["value_count"]
                receipt_digests.append(report["receipt_sha256"])
            if frames == 0 or q is None or first_q is None:
                raise DirichletResidueCompositionError(
                    "framed producer received no control requests"
                )
            if schedule is not None and (
                scheduled_rows != scheduled_rows_for_q
                or scheduled_index != len(schedule.execution_records)
                or slices != schedule.t_row_count
            ):
                raise DirichletResidueCompositionError(
                    "scheduled producer did not exactly cover TGDQORD1"
                )
            summary: dict[str, Any] = {
                "kind": (
                    "sparkinterval.tg.dirichlet_residue_composition."
                    + (
                        "scheduled_framed_stream.v1"
                        if schedule is not None
                        else "framed_stream.v1"
                    )
                ),
                "classification": (
                    "scheduled_composition_stream_adapter_not_atom_closure"
                    if schedule is not None
                    else "composition_stream_adapter_not_atom_closure"
                ),
                "q": q if schedule is None else None,
                "first_q": first_q,
                "last_q": q,
                "maximum_batch_count": args.max_batch_count,
                "frame_count": frames,
                "slice_count": slices,
                "value_count": values,
                "first_t_numerator": first_numerator,
                "t_denominator": denominator,
                "t_step_numerator": step,
                "TGDAFFI1_stream_sha256": output.digest.hexdigest(),
                "control_jsonl_sha256": control_digest.hexdigest(),
                "stream_size_bytes": output.size,
                "composition_receipt_merkle_sha256": _merkle(receipt_digests),
                "retained_output_frames": 0,
                "persistent_allchars_framed_service_compatible": True,
                "full_source_run_completed": False,
                "external_atom_discharged": False,
            }
            if schedule is not None:
                summary.update(
                    {
                        "scheduler_algorithm": SCHEDULER_ALGORITHM_ID,
                        "schedule_classification": schedule.classification,
                        "schedule_manifest_sha256": schedule.manifest_sha256,
                        "schedule_source_roster_sha256": (
                            schedule.source_roster_sha256
                        ),
                        "schedule_execution_order_sha256": (
                            schedule.execution_order_sha256
                        ),
                        "scheduled_modulus_count": schedule.q_count,
                        "scheduled_t_index_rows": schedule.t_row_count,
                        "TGDQORD1_exact_coverage": True,
                    }
                )
            summary["summary_sha256"] = hashlib.sha256(
                canonical_json_bytes(summary)
            ).hexdigest()
            _write_summary(args.summary, summary)
            return 0
        else:  # pragma: no cover
            raise AssertionError("unknown command")
        _emit(result, pretty=args.pretty)
        return 0
    except (
        DirichletAllCharsQSchedulerError,
        DirichletResidueCompositionError,
        OSError,
        ValueError,
    ) as error:
        print(f"tg_dirichlet_residue_composition: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
