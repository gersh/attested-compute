# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Receipt-preserving TGDQORD1 producer/FFT/completed-L process graph.

This is the scheduled counterpart of ``dirichlet_largeq_pipeline``.  It
changes only cross-modulus execution order.  The manifest retains every
actual q and exact t-row count, and every process receipt binds the same
immutable manifest digest.  Bounded runs may insert two one-MiB relays to
retain exact streams for fresh producer, MPFR-transform, and Arb-consumer
replay.  Full-source runs deliberately cannot retain those streams.

Neither a successful bounded run nor this operational receipt establishes
zero completeness, a Turing count, or Platt's Theorem 7.1.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time
from typing import Any, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_allchars_q_scheduler import (
    BOUNDED_CLASSIFICATION,
    FULL_SOURCE_CLASSIFICATION,
    SCHEDULER_ALGORITHM_ID,
    ParsedScheduleManifest,
    parse_schedule_manifest,
    validate_scheduled_multiq_framed_summary,
)
from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    OUTPUT_HEADER,
    canonical_component_orders,
)
from tg_verifier.dirichlet_residue_composition import (
    FRAMED_REQUEST_SCHEMA,
    canonical_json_bytes,
    load_job,
)
from tg_verifier.dirichlet_root_catalog import (
    active_moduli,
    audit_root_catalog,
)
from tg_verifier.dirichlet_root_number_stage import ROOT_ALGORITHM_ID
from tg_verifier.dirichlet_stream_zero_consumer import (
    RAW_EVENT_STORAGE_MODE,
    validate_control,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-scheduled-largeq-persistent-pipeline-v1"
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_scheduled_largeq_pipeline.receipt.v1"
)
REPLAY_SCHEMA = (
    "sparkinterval.tg.dirichlet_scheduled_largeq_pipeline.replay.v1"
)
MAX_CONTROL_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 16 * 1024 * 1024
DEFAULT_KAT_CAPTURE_BYTES = 256 * 1024 * 1024
MAXIMUM_KAT_CAPTURE_BYTES = DEFAULT_KAT_CAPTURE_BYTES
DEFAULT_BOUNDED_PROCESS_TIMEOUT_SECONDS = 15 * 60.0
DEFAULT_REPLAY_PROCESS_TIMEOUT_SECONDS = 15 * 60.0
TEE_MAXIMUM_CHUNK_BYTES = 1024 * 1024
TEE_RECEIPT_SCHEMA = "sparkinterval.tg.bounded_stream_tee.receipt.v1"
TEE_RECEIPT_CLASSIFICATION = (
    "bounded_stream_capture_for_independent_replay_not_evidence"
)


class DirichletScheduledPipelineError(RuntimeError):
    """A scheduled control, process, receipt, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletScheduledPipelineError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _open_regular_file(path: Path, *, label: str) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletScheduledPipelineError(
            f"{label} is missing or not a safe regular file"
        ) from error
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        _fail(f"{label} is missing or not a safe regular file")
    return descriptor, metadata


def _same_open_file(
    left: os.stat_result, right: os.stat_result
) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _bounded_file_read(
    path: Path,
    maximum: int,
    *,
    label: str,
    allow_empty: bool,
) -> bytes:
    descriptor, before = _open_regular_file(path, label=label)
    try:
        if (
            before.st_size > maximum
            or (not allow_empty and before.st_size == 0)
        ):
            lower = 0 if allow_empty else 1
            _fail(f"{label} size is outside {lower}..{maximum}")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            raw = source.read(maximum + 1)
            after = os.fstat(source.fileno())
        if (
            len(raw) > maximum
            or len(raw) != before.st_size
            or not _same_open_file(before, after)
        ):
            _fail(f"{label} changed while reading")
        return raw
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _bounded_read(path: Path, maximum: int, *, label: str) -> bytes:
    return _bounded_file_read(
        path,
        maximum,
        label=label,
        allow_empty=False,
    )


def _bounded_optional_read(path: Path, maximum: int, *, label: str) -> bytes:
    return _bounded_file_read(
        path,
        maximum,
        label=label,
        allow_empty=True,
    )


def _canonical_line(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletScheduledPipelineError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not one canonical JSON line")
    return value


def _canonical_object(path: Path, *, label: str) -> dict[str, Any]:
    return _canonical_line(
        _bounded_read(path, MAX_JSON_BYTES, label=label), label=label
    )


def _self_hash(value: Mapping[str, Any], field: str, *, label: str) -> str:
    body = dict(value)
    claimed = _digest(body.pop(field, None), f"{label}.{field}")
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        _fail(f"{label} self-hash differs")
    return claimed


def _artifact_record(path: Path) -> dict[str, Any]:
    descriptor, before = _open_regular_file(
        path, label=f"artifact {path}"
    )
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            while block := source.read(1024 * 1024):
                digest.update(block)
            after = os.fstat(source.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not _same_open_file(before, after):
        _fail(f"artifact changed while hashing: {path}")
    try:
        resolved = path.resolve(strict=True)
        rebound = resolved.stat()
    except OSError as error:
        raise DirichletScheduledPipelineError(
            f"artifact path changed while resolving: {path}"
        ) from error
    if (rebound.st_dev, rebound.st_ino) != (before.st_dev, before.st_ino):
        _fail(f"artifact path changed while hashing: {path}")
    return {
        "path": str(resolved),
        "sha256": digest.hexdigest(),
        "size_bytes": before.st_size,
    }


def _invocation_artifact_record(path: Path, *, label: str) -> dict[str, Any]:
    """Bind both the invoked spelling and the regular file it resolves to.

    Python virtual-environment launchers are normally symlinks and must retain
    that invoked spelling for ``sys.prefix`` discovery.  The executable bytes
    are therefore committed at the resolved regular-file target while the
    exact invoked path and symlink status are retained separately.
    """

    invoked = path.absolute()
    if not invoked.is_file():
        _fail(f"{label} invocation artifact is missing")
    try:
        resolved = invoked.resolve(strict=True)
    except OSError as error:
        raise DirichletScheduledPipelineError(
            f"{label} invocation artifact cannot be resolved"
        ) from error
    return {
        "invoked_path": str(invoked),
        "invoked_via_symlink": invoked.is_symlink(),
        "resolved_artifact": _artifact_record(resolved),
    }


def _check_invocation_artifact_record(
    record: object, *, label: str
) -> Path:
    if not isinstance(record, dict) or set(record) != {
        "invoked_path",
        "invoked_via_symlink",
        "resolved_artifact",
    }:
        _fail(f"{label} invocation artifact record differs")
    invoked_raw = record["invoked_path"]
    via_symlink = record["invoked_via_symlink"]
    if (
        not isinstance(invoked_raw, str)
        or not invoked_raw
        or not isinstance(via_symlink, bool)
    ):
        _fail(f"{label} invocation artifact fields are malformed")
    invoked = Path(invoked_raw)
    if invoked.is_symlink() is not via_symlink or not invoked.is_file():
        _fail(f"{label} invocation path changed from its receipt")
    resolved = _check_artifact_record(
        record["resolved_artifact"], label=f"{label} resolved"
    )
    try:
        current = invoked.resolve(strict=True)
    except OSError as error:
        raise DirichletScheduledPipelineError(
            f"{label} invocation path cannot be resolved"
        ) from error
    if current != resolved:
        _fail(f"{label} invocation target changed from its receipt")
    return invoked


def _check_artifact_record(record: object, *, label: str) -> Path:
    if not isinstance(record, dict) or set(record) != {
        "path",
        "sha256",
        "size_bytes",
    }:
        _fail(f"{label} artifact record differs")
    path_value = record.get("path")
    size_value = record.get("size_bytes")
    _digest(record.get("sha256"), f"{label}.sha256")
    if (
        not isinstance(path_value, str)
        or not path_value
        or isinstance(size_value, bool)
        or not isinstance(size_value, int)
        or size_value < 0
    ):
        _fail(f"{label} artifact record differs")
    path = Path(path_value)
    rebound = _artifact_record(path)
    if rebound != record:
        _fail(f"{label} artifact changed from its receipt")
    return path


def _check_bounded_artifact_record(
    record: object, *, maximum: int, label: str
) -> tuple[Path, bytes]:
    if not isinstance(record, dict) or set(record) != {
        "path",
        "sha256",
        "size_bytes",
    }:
        _fail(f"{label} artifact record differs")
    recorded_size = record.get("size_bytes")
    path_value = record.get("path")
    _digest(record.get("sha256"), f"{label}.sha256")
    if (
        not isinstance(path_value, str)
        or not path_value
        or isinstance(recorded_size, bool)
        or not isinstance(recorded_size, int)
        or not 0 < recorded_size <= maximum
    ):
        _fail(f"{label} artifact exceeds its retained bound")
    path = Path(path_value)
    raw = _bounded_read(path, maximum, label=label)
    rebound = {
        "path": str(path.resolve()),
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
    }
    if rebound != record:
        _fail(f"{label} artifact changed from its receipt")
    return path, raw


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        _fail(f"refusing to replace immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json_bytes(dict(value)))
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _prepare_empty_output_directory(path: Path) -> None:
    if path.is_symlink():
        _fail("pipeline output directory cannot be a symlink")
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            _fail("pipeline output directory must be absent or empty")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        _fail("pipeline output directory changed while preparing it")


def _positive_timeout(
    value: float | None, *, label: str, allow_none: bool
) -> float | None:
    if value is None:
        if allow_none:
            return None
        _fail(f"{label} is required")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        _fail(f"{label} must be a positive finite number")
    return float(value)


def _merkle_receipts(receipts: Sequence[Path]) -> str:
    level: list[bytes] = []
    for index, path in enumerate(receipts):
        value = _canonical_object(path, label=f"composition receipt {index}")
        receipt_sha = _self_hash(
            value, "receipt_sha256", label=f"composition receipt {index}"
        )
        level.append(hashlib.sha256(bytes.fromhex(receipt_sha)).digest())
    if not level:
        _fail("cannot Merkle-hash no composition receipts")
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


@dataclass(frozen=True)
class ScheduledControlInventory:
    schedule: ParsedScheduleManifest
    frame_count: int
    slice_count: int
    value_count: int
    first_q: int
    last_q: int
    composition_sha256: str
    consumer_sha256: str
    composition_receipts: tuple[Path, ...]


def validate_scheduled_control_alignment(
    composition_control_path: Path,
    consumer_control_path: Path,
    *,
    schedule_manifest_path: Path,
    base: Path,
    maximum_batch_count: int,
    require_full_source: bool = False,
    allow_synthetic_kat: bool = False,
) -> ScheduledControlInventory:
    """Replay exact q/t coverage against one immutable TGDQORD1 manifest."""

    if (
        isinstance(maximum_batch_count, bool)
        or not isinstance(maximum_batch_count, int)
        or maximum_batch_count <= 0
    ):
        _fail("maximum batch count must be positive")
    try:
        schedule = parse_schedule_manifest(schedule_manifest_path)
    except RuntimeError as error:
        raise DirichletScheduledPipelineError(
            f"TGDQORD1 validation failed: {error}"
        ) from error
    if require_full_source and schedule.classification != FULL_SOURCE_CLASSIFICATION:
        _fail("production supervisor requires a full-source TGDQORD1 manifest")
    composition_raw = _bounded_read(
        composition_control_path,
        MAX_CONTROL_BYTES,
        label="composition controls",
    )
    consumer_raw = _bounded_read(
        consumer_control_path,
        MAX_CONTROL_BYTES,
        label="consumer controls",
    )
    composition_lines = composition_raw.splitlines(keepends=True)
    consumer_lines = consumer_raw.splitlines(keepends=True)
    if not composition_lines or len(composition_lines) != len(consumer_lines):
        _fail("composition and consumer control frame counts differ")

    schedule_index = 0
    current_q: int | None = None
    current_rows = 0
    current_expected_rows = 0
    next_numerator: int | None = None
    slices = 0
    values = 0
    receipt_paths: list[Path] = []
    seen_receipts: set[Path] = set()
    for index, (composition_line, consumer_line) in enumerate(
        zip(composition_lines, consumer_lines)
    ):
        request = _canonical_line(
            composition_line, label=f"composition control {index}"
        )
        if (
            set(request) != {"schema", "schema_version", "job", "receipt"}
            or request.get("schema") != FRAMED_REQUEST_SCHEMA
            or request.get("schema_version") != 1
        ):
            _fail(f"composition control {index} schema differs")
        if not isinstance(request["job"], str) or not isinstance(
            request["receipt"], str
        ):
            _fail(f"composition control {index} paths are malformed")
        job_path = Path(request["job"])
        receipt_path = Path(request["receipt"])
        if not job_path.is_absolute():
            job_path = base / job_path
        if not receipt_path.is_absolute():
            receipt_path = base / receipt_path
        receipt_path = receipt_path.resolve()
        if receipt_path in seen_receipts:
            _fail("composition receipt paths are not unique")
        seen_receipts.add(receipt_path)
        receipt_paths.append(receipt_path)
        try:
            job = load_job(
                job_path,
                allow_synthetic_kat=allow_synthetic_kat,
                max_batch_count=maximum_batch_count,
            )
            control = validate_control(
                _canonical_line(
                    consumer_line, label=f"consumer control {index}"
                ),
                expected_frame_index=index,
                expected_root_number_mode=ROOT_ALGORITHM_ID,
            )
        except RuntimeError as error:
            raise DirichletScheduledPipelineError(
                f"scheduled control {index} validation failed: {error}"
            ) from error
        identity = (
            job.q,
            len(job.frames),
            job.first_t_numerator,
            job.t_denominator,
            job.t_step_numerator,
        )
        if identity != (
            control["q"],
            control["batch_count"],
            control["first_t_numerator"],
            control["t_denominator"],
            control["t_step_numerator"],
        ):
            _fail(f"consumer control {index} differs from composition job")
        if job.q != current_q:
            if current_q is not None and current_rows != current_expected_rows:
                _fail("scheduled controls ended a q before exact coverage")
            if (
                schedule_index >= len(schedule.execution_records)
                or job.q != schedule.execution_records[schedule_index].q
            ):
                _fail("control q differs from TGDQORD1 execution order")
            if (
                job.first_t_numerator != 0
                or job.t_denominator != 64
                or job.t_step_numerator != 5
            ):
                _fail("scheduled controls do not start q on the exact 5/64 grid")
            current_q = job.q
            current_rows = 0
            current_expected_rows = schedule.execution_records[
                schedule_index
            ].t_index_count
            schedule_index += 1
        elif (
            job.first_t_numerator != next_numerator
            or job.t_denominator != 64
            or job.t_step_numerator != 5
        ):
            _fail("same-q controls are not a contiguous 5/64 progression")
        batch_count = len(job.frames)
        if (
            current_rows > current_expected_rows
            or batch_count > current_expected_rows - current_rows
        ):
            _fail("control frame exceeds scheduled q row coverage")
        current_rows += batch_count
        next_numerator = job.first_t_numerator + 5 * batch_count
        slices += batch_count
        values += batch_count * math.prod(canonical_component_orders(job.q))
    if (
        current_rows != current_expected_rows
        or schedule_index != len(schedule.execution_records)
        or slices != schedule.t_row_count
    ):
        _fail("controls do not exactly cover TGDQORD1")
    return ScheduledControlInventory(
        schedule=schedule,
        frame_count=len(composition_lines),
        slice_count=slices,
        value_count=values,
        first_q=schedule.execution_records[0].q,
        last_q=schedule.execution_records[-1].q,
        composition_sha256=sha256_bytes(composition_raw),
        consumer_sha256=sha256_bytes(consumer_raw),
        composition_receipts=tuple(receipt_paths),
    )


def _validate_root_catalog_for_schedule(
    schedule: ParsedScheduleManifest,
    *,
    root_catalog_path: Path,
    root_catalog_sha256: str,
    root_catalog_directory: Path,
    require_full_source: bool,
    revalidate_artifacts: bool = False,
) -> dict[str, Any]:
    try:
        audit = audit_root_catalog(
            root_catalog_path,
            root=root_catalog_directory,
            expected_sha256=root_catalog_sha256,
            require_full_source=require_full_source,
            revalidate_artifacts=revalidate_artifacts,
        )
    except RuntimeError as error:
        raise DirichletScheduledPipelineError(
            f"root catalog validation failed: {error}"
        ) from error
    catalog_qs = tuple(
        q
        for q, _count in active_moduli(
            audit["q_start_inclusive"], audit["q_stop_inclusive"]
        )
    )
    if catalog_qs != tuple(record.q for record in schedule.source_records):
        _fail("root catalog q roster differs from TGDQORD1")
    return audit


def _process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_process_tree(
    process: subprocess.Popen[bytes],
    signal_number: int,
    *,
    isolated_process_groups: bool,
) -> None:
    try:
        if isolated_process_groups:
            # Every supervised child is launched with start_new_session=True,
            # so its pid is also the process-group id.  Signal the group even
            # when the leader already exited: a descendant may still hold a
            # pipeline fd or continue computing.
            os.killpg(process.pid, signal_number)
        elif process.poll() is None:
            process.send_signal(signal_number)
    except ProcessLookupError:
        pass


def _terminate(
    processes: Sequence[subprocess.Popen[bytes]],
    *,
    isolated_process_groups: bool = False,
) -> None:
    for process in reversed(processes):
        _signal_process_tree(
            process,
            signal.SIGTERM,
            isolated_process_groups=isolated_process_groups,
        )
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        direct_running = any(process.poll() is None for process in processes)
        group_running = (
            isolated_process_groups
            and any(_process_group_exists(process.pid) for process in processes)
        )
        if not direct_running and not group_running:
            break
        time.sleep(0.01)
    for process in reversed(processes):
        _signal_process_tree(
            process,
            signal.SIGKILL,
            isolated_process_groups=isolated_process_groups,
        )
    for process in reversed(processes):
        if process.poll() is None:
            process.wait()


def _wait_fail_fast(
    named_processes: Sequence[tuple[str, subprocess.Popen[bytes]]],
    *,
    timeout_seconds: float | None,
    isolated_process_groups: bool = False,
) -> dict[str, int]:
    started = time.monotonic()
    while True:
        codes = {name: process.poll() for name, process in named_processes}
        failed = [name for name, code in codes.items() if code not in (None, 0)]
        if failed:
            _terminate(
                [process for _name, process in named_processes],
                isolated_process_groups=isolated_process_groups,
            )
            final = {
                name: int(process.returncode)
                for name, process in named_processes
            }
            _fail(f"scheduled pipeline process failed: {final}")
        if all(code == 0 for code in codes.values()):
            surviving_groups = [
                name
                for name, process in named_processes
                if isolated_process_groups
                and _process_group_exists(process.pid)
            ]
            if surviving_groups:
                _terminate(
                    [process for _name, process in named_processes],
                    isolated_process_groups=True,
                )
                _fail(
                    "scheduled pipeline leaders exited with surviving "
                    f"descendants: {surviving_groups}"
                )
            return {name: 0 for name, _process in named_processes}
        if (
            timeout_seconds is not None
            and time.monotonic() - started > timeout_seconds
        ):
            _terminate(
                [process for _name, process in named_processes],
                isolated_process_groups=isolated_process_groups,
            )
            _fail("scheduled pipeline exceeded its explicit process timeout")
        time.sleep(0.01)


def _run_bounded_process(
    command: Sequence[str],
    *,
    label: str,
    timeout_seconds: float,
    stdin: Any = None,
    stdout: Any = subprocess.PIPE,
    stderr: Any = subprocess.PIPE,
) -> subprocess.CompletedProcess[bytes]:
    """Run one replay process with an isolated, cancellable descendant tree."""

    process = subprocess.Popen(
        list(command),
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )
    try:
        captured_stdout, captured_stderr = process.communicate(
            timeout=timeout_seconds
        )
    except subprocess.TimeoutExpired as error:
        _terminate([process], isolated_process_groups=True)
        raise DirichletScheduledPipelineError(
            f"{label} exceeded its {timeout_seconds:g}-second timeout"
        ) from error
    except BaseException:
        _terminate([process], isolated_process_groups=True)
        raise
    if process.returncode != 0:
        _terminate([process], isolated_process_groups=True)
    elif _process_group_exists(process.pid):
        _terminate([process], isolated_process_groups=True)
        _fail(f"{label} exited with surviving descendants")
    return subprocess.CompletedProcess(
        list(command),
        int(process.returncode),
        captured_stdout,
        captured_stderr,
    )


def _schedule_binding(
    value: Mapping[str, Any], schedule: ParsedScheduleManifest, *, label: str
) -> None:
    expected = {
        "scheduler_algorithm": SCHEDULER_ALGORITHM_ID,
        "schedule_classification": schedule.classification,
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_source_roster_sha256": schedule.source_roster_sha256,
        "schedule_execution_order_sha256": schedule.execution_order_sha256,
    }
    if any(value.get(key) != item for key, item in expected.items()):
        _fail(f"{label} TGDQORD1 binding differs")


def _validate_tee_receipt(
    path: Path,
    *,
    role: str,
    schedule: ParsedScheduleManifest,
    capture: Path,
    maximum_capture_bytes: int,
) -> dict[str, Any]:
    value = _canonical_object(path, label=f"{role} tee receipt")
    _self_hash(value, "receipt_sha256", label=f"{role} tee receipt")
    required = {
        "kind",
        "classification",
        "stream_role",
        "schedule_manifest_sha256",
        "stream_sha256",
        "stream_size_bytes",
        "maximum_stream_bytes",
        "bounded_memory_bytes",
        "backpressure_preserved",
        "external_atom_discharged",
        "receipt_sha256",
    }
    capture_raw = _bounded_read(
        capture,
        maximum_capture_bytes,
        label=f"{role} capture",
    )
    capture_size = len(capture_raw)
    capture_sha256 = sha256_bytes(capture_raw)
    stream_size = value.get("stream_size_bytes")
    maximum_stream = value.get("maximum_stream_bytes")
    bounded_memory = value.get("bounded_memory_bytes")
    if (
        set(value) != required
        or value.get("kind") != TEE_RECEIPT_SCHEMA
        or value.get("classification") != TEE_RECEIPT_CLASSIFICATION
        or value.get("stream_role") != role
        or value.get("schedule_manifest_sha256") != schedule.manifest_sha256
        or value.get("stream_sha256") != capture_sha256
        or isinstance(stream_size, bool)
        or not isinstance(stream_size, int)
        or stream_size != capture_size
        or isinstance(maximum_stream, bool)
        or not isinstance(maximum_stream, int)
        or maximum_stream != maximum_capture_bytes
        or isinstance(bounded_memory, bool)
        or not isinstance(bounded_memory, int)
        or bounded_memory != TEE_MAXIMUM_CHUNK_BYTES
        or value.get("backpressure_preserved") is not True
        or value.get("external_atom_discharged") is not False
    ):
        _fail(f"{role} tee receipt differs")
    return value


def _validate_consumer_event_binding(
    consumer_receipt: Mapping[str, Any], events_path: Path
) -> dict[str, Any]:
    events = _artifact_record(events_path)
    events_size = consumer_receipt.get("events_bytes")
    if (
        consumer_receipt.get("events_sha256") != events["sha256"]
        or isinstance(events_size, bool)
        or not isinstance(events_size, int)
        or events_size != events["size_bytes"]
    ):
        _fail("consumer event digest or size differs from its receipt")
    return events


def run_scheduled_pipeline(
    *,
    composition_controls: Path,
    consumer_controls: Path,
    schedule_manifest: Path,
    control_base: Path,
    composer_python: Path,
    composer_tool: Path,
    allchars_runner: Path,
    consumer_python: Path,
    consumer_tool: Path,
    root_catalog: Path,
    root_catalog_sha256: str,
    root_catalog_directory: Path,
    output_directory: Path,
    pipeline_receipt: Path,
    maximum_batch_count: int = 64,
    device: int = 0,
    precision: int = 192,
    require_full_source: bool = False,
    allow_synthetic_kat: bool = False,
    retain_bounded_streams: bool = True,
    maximum_capture_bytes: int = DEFAULT_KAT_CAPTURE_BYTES,
    process_timeout_seconds: float | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the manifest-ordered producer/transform/consumer graph."""

    inventory = validate_scheduled_control_alignment(
        composition_controls,
        consumer_controls,
        schedule_manifest_path=schedule_manifest,
        base=control_base,
        maximum_batch_count=maximum_batch_count,
        require_full_source=require_full_source,
        allow_synthetic_kat=allow_synthetic_kat,
    )
    schedule = inventory.schedule
    effective_process_timeout = _positive_timeout(
        process_timeout_seconds,
        label="process timeout",
        allow_none=(schedule.classification == BOUNDED_CLASSIFICATION),
    )
    if effective_process_timeout is None:
        effective_process_timeout = DEFAULT_BOUNDED_PROCESS_TIMEOUT_SECONDS
    if (
        retain_bounded_streams
        and schedule.classification != BOUNDED_CLASSIFICATION
    ):
        _fail("full-source runs cannot retain the transform streams")
    if (
        isinstance(maximum_capture_bytes, bool)
        or not isinstance(maximum_capture_bytes, int)
        or maximum_capture_bytes <= 0
        or maximum_capture_bytes > MAXIMUM_KAT_CAPTURE_BYTES
    ):
        _fail(
            "maximum capture bytes must be in "
            f"1..{MAXIMUM_KAT_CAPTURE_BYTES}"
        )
    catalog_audit = _validate_root_catalog_for_schedule(
        schedule,
        root_catalog_path=root_catalog,
        root_catalog_sha256=root_catalog_sha256,
        root_catalog_directory=root_catalog_directory,
        require_full_source=require_full_source,
    )
    _prepare_empty_output_directory(output_directory)

    composer_summary_path = output_directory / "composer-summary.json"
    transform_summary_path = output_directory / "transform-summary.json"
    events_path = output_directory / "events.ndjson"
    consumer_receipt_path = output_directory / "consumer-receipt.json"
    input_capture = output_directory / "TGDAFFI1.capture.bin"
    output_capture = output_directory / "TGDAFFO1.capture.bin"
    input_tee_receipt = output_directory / "TGDAFFI1.tee.receipt.json"
    output_tee_receipt = output_directory / "TGDAFFO1.tee.receipt.json"
    tee_tool = (
        Path(__file__).resolve().parents[1]
        / "tools/tg_bounded_stream_tee.py"
    )
    stderr_paths: dict[str, Path] = {}
    component_invocations = {
        "composer_python": _invocation_artifact_record(
            composer_python, label="composer Python"
        ),
        "composer_tool": _invocation_artifact_record(
            composer_tool.resolve(), label="composer tool"
        ),
        "allchars_runner": _invocation_artifact_record(
            allchars_runner.resolve(), label="all-character runner"
        ),
        "consumer_python": _invocation_artifact_record(
            consumer_python, label="consumer Python"
        ),
        "consumer_tool": _invocation_artifact_record(
            consumer_tool.resolve(), label="consumer tool"
        ),
        "bounded_stream_tee": (
            _invocation_artifact_record(tee_tool, label="bounded stream tee")
            if retain_bounded_streams
            else None
        ),
    }

    composer_command = [
        str(composer_python.absolute()),
        str(composer_tool.resolve()),
        "--max-batch-count",
        str(maximum_batch_count),
        "framed-produce",
        str(composer_summary_path),
        "--base",
        str(control_base.resolve()),
        "--schedule-manifest",
        str(schedule_manifest.resolve()),
    ]
    if require_full_source:
        composer_command.append("--require-full-source-schedule")
    if allow_synthetic_kat:
        composer_command.append("--allow-synthetic-kat")
    transform_command = [
        str(allchars_runner.resolve()),
        (
            "--scheduled-multiq-framed-service"
            if schedule.classification == FULL_SOURCE_CLASSIFICATION
            else "--bounded-scheduled-multiq-framed-service"
        ),
        str(maximum_batch_count),
        "512",
        str(schedule_manifest.resolve()),
        str(transform_summary_path),
        str(device),
    ]
    consumer_command = [
        str(consumer_python.absolute()),
        str(consumer_tool.resolve()),
        "consume",
        str(consumer_controls.resolve()),
        "-",
        str(events_path),
        str(consumer_receipt_path),
        "--precision",
        str(precision),
        "--schedule-manifest",
        str(schedule_manifest.resolve()),
        "--root-catalog",
        str(root_catalog.resolve()),
        "--root-catalog-sha256",
        root_catalog_sha256,
        "--root-catalog-directory",
        str(root_catalog_directory.resolve()),
        "--event-storage-mode",
        RAW_EVENT_STORAGE_MODE,
    ]
    if require_full_source:
        consumer_command.append("--require-full-source-schedule")

    child_environment = dict(os.environ if environment is None else environment)
    processes: list[subprocess.Popen[bytes]] = []
    named_processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    opened: list[Any] = []
    try:
        controls = composition_controls.open("rb")
        opened.append(controls)
        consumer_stdout = (output_directory / "consumer.stdout").open("wb")
        opened.append(consumer_stdout)

        def stderr(name: str):
            path = output_directory / f"{name}.stderr"
            stderr_paths[name] = path
            handle = path.open("wb")
            opened.append(handle)
            return handle

        composer = subprocess.Popen(
            composer_command,
            stdin=controls,
            stdout=subprocess.PIPE,
            stderr=stderr("composer"),
            cwd=control_base,
            env=child_environment,
            start_new_session=True,
        )
        processes.append(composer)
        named_processes.append(("composer", composer))
        assert composer.stdout is not None
        upstream = composer.stdout

        if retain_bounded_streams:
            input_tee = subprocess.Popen(
                [
                    str(composer_python.absolute()),
                    str(tee_tool),
                    str(input_capture),
                    str(input_tee_receipt),
                    str(maximum_capture_bytes),
                    "TGDAFFI1",
                    schedule.manifest_sha256,
                ],
                stdin=upstream,
                stdout=subprocess.PIPE,
                stderr=stderr("input-tee"),
                cwd=control_base,
                env=child_environment,
                start_new_session=True,
            )
            upstream.close()
            processes.append(input_tee)
            named_processes.append(("input_tee", input_tee))
            assert input_tee.stdout is not None
            upstream = input_tee.stdout

        transform = subprocess.Popen(
            transform_command,
            stdin=upstream,
            stdout=subprocess.PIPE,
            stderr=stderr("transform"),
            cwd=control_base,
            env=child_environment,
            start_new_session=True,
        )
        upstream.close()
        processes.append(transform)
        named_processes.append(("transform", transform))
        assert transform.stdout is not None
        downstream = transform.stdout

        if retain_bounded_streams:
            output_tee = subprocess.Popen(
                [
                    str(composer_python.absolute()),
                    str(tee_tool),
                    str(output_capture),
                    str(output_tee_receipt),
                    str(maximum_capture_bytes),
                    "TGDAFFO1",
                    schedule.manifest_sha256,
                ],
                stdin=downstream,
                stdout=subprocess.PIPE,
                stderr=stderr("output-tee"),
                cwd=control_base,
                env=child_environment,
                start_new_session=True,
            )
            downstream.close()
            processes.append(output_tee)
            named_processes.append(("output_tee", output_tee))
            assert output_tee.stdout is not None
            downstream = output_tee.stdout

        consumer = subprocess.Popen(
            consumer_command,
            stdin=downstream,
            stdout=consumer_stdout,
            stderr=stderr("consumer"),
            cwd=control_base,
            env=child_environment,
            start_new_session=True,
        )
        downstream.close()
        processes.append(consumer)
        named_processes.append(("consumer", consumer))
        return_codes = _wait_fail_fast(
            named_processes,
            timeout_seconds=effective_process_timeout,
            isolated_process_groups=True,
        )
    except BaseException:
        _terminate(processes, isolated_process_groups=True)
        raise
    finally:
        for handle in reversed(opened):
            handle.close()

    for name, path in stderr_paths.items():
        _bounded_optional_read(
            path,
            MAX_DIAGNOSTIC_BYTES,
            label=f"{name} stderr",
        )
    _bounded_optional_read(
        output_directory / "consumer.stdout",
        MAX_JSON_BYTES,
        label="consumer stdout",
    )
    rebound_invocations = {
        "composer_python": _invocation_artifact_record(
            composer_python, label="composer Python"
        ),
        "composer_tool": _invocation_artifact_record(
            composer_tool.resolve(), label="composer tool"
        ),
        "allchars_runner": _invocation_artifact_record(
            allchars_runner.resolve(), label="all-character runner"
        ),
        "consumer_python": _invocation_artifact_record(
            consumer_python, label="consumer Python"
        ),
        "consumer_tool": _invocation_artifact_record(
            consumer_tool.resolve(), label="consumer tool"
        ),
        "bounded_stream_tee": (
            _invocation_artifact_record(tee_tool, label="bounded stream tee")
            if retain_bounded_streams
            else None
        ),
    }
    if rebound_invocations != component_invocations:
        _fail("component invocation artifact changed during execution")

    composer_summary = _canonical_object(
        composer_summary_path, label="scheduled composer summary"
    )
    _self_hash(
        composer_summary,
        "summary_sha256",
        label="scheduled composer summary",
    )
    _schedule_binding(composer_summary, schedule, label="composer")
    transform_summary_raw = _bounded_read(
        transform_summary_path,
        MAX_JSON_BYTES,
        label="scheduled transform summary",
    )
    try:
        transform_summary = json.loads(transform_summary_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletScheduledPipelineError(
            "invalid scheduled transform summary"
        ) from error
    if not isinstance(transform_summary, dict):
        _fail("scheduled transform summary is not an object")
    _schedule_binding(transform_summary, schedule, label="transform")
    consumer_receipt_value = _canonical_object(
        consumer_receipt_path, label="scheduled consumer receipt"
    )
    _self_hash(
        consumer_receipt_value,
        "receipt_sha256",
        label="scheduled consumer receipt",
    )
    _schedule_binding(consumer_receipt_value, schedule, label="consumer")
    events_artifact = _validate_consumer_event_binding(
        consumer_receipt_value, events_path
    )

    if (
        composer_summary.get("first_q") != inventory.first_q
        or composer_summary.get("last_q") != inventory.last_q
        or composer_summary.get("scheduled_modulus_count") != schedule.q_count
        or composer_summary.get("scheduled_t_index_rows")
        != schedule.t_row_count
        or composer_summary.get("TGDQORD1_exact_coverage") is not True
        or transform_summary.get("first_q") != inventory.first_q
        or transform_summary.get("last_q") != inventory.last_q
        or transform_summary.get("modulus_count") != schedule.q_count
        or transform_summary.get("scheduled_t_index_rows")
        != schedule.t_row_count
        or consumer_receipt_value.get("scheduled_modulus_count")
        != schedule.q_count
        or consumer_receipt_value.get("scheduled_t_index_rows")
        != schedule.t_row_count
        or consumer_receipt_value.get("TGDQORD1_exact_coverage") is not True
        or composer_summary.get("control_jsonl_sha256")
        != inventory.composition_sha256
        or consumer_receipt_value.get("control_stream_sha256")
        != inventory.consumer_sha256
        or composer_summary.get("frame_count") != inventory.frame_count
        or transform_summary.get("frame_count") != inventory.frame_count
        or consumer_receipt_value.get("frame_count") != inventory.frame_count
        or composer_summary.get("slice_count") != inventory.slice_count
        or transform_summary.get("slice_count") != inventory.slice_count
        or composer_summary.get("value_count") != inventory.value_count
        or transform_summary.get("value_count") != inventory.value_count
        or consumer_receipt_value.get("value_count") != inventory.value_count
        or composer_summary.get("composition_receipt_merkle_sha256")
        != _merkle_receipts(inventory.composition_receipts)
        or consumer_receipt_value.get("root_catalog_sha256")
        != catalog_audit["catalog"]["sha256"]
        or consumer_receipt_value.get("root_catalog_entry_chain_sha256")
        != catalog_audit["entry_chain_sha256"]
        or consumer_receipt_value.get("root_catalog_artifacts_revalidated")
        is not True
    ):
        _fail("scheduled process coverage or artifact bindings differ")
    if (
        composer_summary.get("TGDAFFI1_stream_sha256")
        != transform_summary.get("input_stream_sha256")
        or transform_summary.get("output_stream_sha256")
        != consumer_receipt_value.get("transform_stream_sha256")
    ):
        _fail("scheduled cross-stage stream hashes differ")
    if (
        consumer_receipt_value.get("external_atom_discharged") is not False
        or consumer_receipt_value.get("zero_completeness_claimed") is not False
        or consumer_receipt_value.get("root_number_artifact_supplied") is not True
        or consumer_receipt_value.get("source_performance_ready") is not True
    ):
        _fail("scheduled consumer claim boundary differs")

    captures: dict[str, Any] | None = None
    if retain_bounded_streams:
        input_tee_value = _validate_tee_receipt(
            input_tee_receipt,
            role="TGDAFFI1",
            schedule=schedule,
            capture=input_capture,
            maximum_capture_bytes=maximum_capture_bytes,
        )
        output_tee_value = _validate_tee_receipt(
            output_tee_receipt,
            role="TGDAFFO1",
            schedule=schedule,
            capture=output_capture,
            maximum_capture_bytes=maximum_capture_bytes,
        )
        if (
            input_tee_value["stream_sha256"]
            != composer_summary["TGDAFFI1_stream_sha256"]
            or output_tee_value["stream_sha256"]
            != transform_summary["output_stream_sha256"]
        ):
            _fail("bounded tee digests differ from component stream folds")
        input_capture_raw = _bounded_read(
            input_capture,
            maximum_capture_bytes,
            label="TGDAFFI1 capture",
        )
        output_capture_raw = _bounded_read(
            output_capture,
            maximum_capture_bytes,
            label="TGDAFFO1 capture",
        )
        validate_scheduled_multiq_framed_summary(
            transform_summary,
            manifest=schedule_manifest,
            input_stream=input_capture_raw,
            output_stream=output_capture_raw,
            require_full_source=False,
        )
        input_capture_artifact = _artifact_record(input_capture)
        output_capture_artifact = _artifact_record(output_capture)
        input_tee_artifact = _artifact_record(input_tee_receipt)
        output_tee_artifact = _artifact_record(output_tee_receipt)
        if (
            input_capture_artifact["sha256"]
            != input_tee_value["stream_sha256"]
            or input_capture_artifact["size_bytes"]
            != input_tee_value["stream_size_bytes"]
            or output_capture_artifact["sha256"]
            != output_tee_value["stream_sha256"]
            or output_capture_artifact["size_bytes"]
            != output_tee_value["stream_size_bytes"]
            or input_tee_artifact["sha256"]
            != sha256_bytes(canonical_json_bytes(input_tee_value))
            or output_tee_artifact["sha256"]
            != sha256_bytes(canonical_json_bytes(output_tee_value))
        ):
            _fail("bounded capture or tee receipt changed after validation")
        captures = {
            "TGDAFFI1": input_capture_artifact,
            "TGDAFFI1_tee_receipt": input_tee_artifact,
            "TGDAFFO1": output_capture_artifact,
            "TGDAFFO1_tee_receipt": output_tee_artifact,
        }

    schedule_artifact = _artifact_record(schedule_manifest)
    composition_control_artifact = _artifact_record(composition_controls)
    consumer_control_artifact = _artifact_record(consumer_controls)
    root_catalog_artifact = _artifact_record(root_catalog)
    composer_summary_artifact = _artifact_record(composer_summary_path)
    transform_summary_artifact = _artifact_record(transform_summary_path)
    consumer_receipt_artifact = _artifact_record(consumer_receipt_path)
    if (
        schedule_artifact["sha256"] != schedule.manifest_sha256
        or composition_control_artifact["sha256"]
        != inventory.composition_sha256
        or consumer_control_artifact["sha256"] != inventory.consumer_sha256
        or root_catalog_artifact["sha256"]
        != catalog_audit["catalog"]["sha256"]
        or composer_summary_artifact["sha256"]
        != sha256_bytes(canonical_json_bytes(composer_summary))
        or transform_summary_artifact["sha256"]
        != sha256_bytes(transform_summary_raw)
        or consumer_receipt_artifact["sha256"]
        != sha256_bytes(canonical_json_bytes(consumer_receipt_value))
        or _artifact_record(events_path) != events_artifact
    ):
        _fail("scheduled artifact changed after validation")

    receipt: dict[str, Any] = {
        "kind": RECEIPT_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": (
            "manifest_ordered_component_graph_not_zero_or_grh_closure"
        ),
        "scheduler_algorithm": SCHEDULER_ALGORITHM_ID,
        "schedule_classification": schedule.classification,
        "schedule_manifest": schedule_artifact,
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_source_roster_sha256": schedule.source_roster_sha256,
        "schedule_execution_order_sha256": schedule.execution_order_sha256,
        "scheduled_modulus_count": schedule.q_count,
        "scheduled_t_index_rows": schedule.t_row_count,
        "first_execution_q": inventory.first_q,
        "last_execution_q": inventory.last_q,
        "frame_count": inventory.frame_count,
        "slice_count": inventory.slice_count,
        "value_count": inventory.value_count,
        "maximum_batch_count": maximum_batch_count,
        "maximum_capture_bytes": (
            maximum_capture_bytes if retain_bounded_streams else None
        ),
        "process_timeout_seconds": effective_process_timeout,
        "process_return_codes": return_codes,
        "process_graph_backpressured": True,
        "fail_fast_sibling_cancellation": True,
        "isolated_process_groups": True,
        "bounded_streams_retained_for_replay": retain_bounded_streams,
        "captures": captures,
        "component_invocations": component_invocations,
        "controls": {
            "composition": composition_control_artifact,
            "consumer": consumer_control_artifact,
        },
        "root_catalog": root_catalog_artifact,
        "root_catalog_directory": str(root_catalog_directory.resolve()),
        "root_catalog_entry_chain_sha256": catalog_audit[
            "entry_chain_sha256"
        ],
        "summaries": {
            "composer": composer_summary_artifact,
            "transform": transform_summary_artifact,
            "consumer": consumer_receipt_artifact,
            "events": events_artifact,
        },
        "TGDQORD1_exact_coverage": True,
        "increasing_q_assumed": False,
        "independent_replay_completed": False,
        "source_scale_execution_completed": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    _atomic_json(pipeline_receipt, receipt)
    return receipt


def _mpfr_replay_transform_frames(
    input_raw: bytes,
    output_raw: bytes,
    *,
    checker: Path,
    precision: int,
    process_timeout_seconds: float,
) -> int:
    input_offset = 0
    output_offset = 0
    frames = 0
    with tempfile.TemporaryDirectory(
        prefix="tg-dirichlet-scheduled-mpfr-"
    ) as temporary:
        root = Path(temporary)
        while input_offset < len(input_raw):
            if len(input_raw) - input_offset < INPUT_HEADER.size:
                _fail("independent MPFR replay input header is truncated")
            input_header = INPUT_HEADER.unpack_from(input_raw, input_offset)
            input_size = (
                INPUT_HEADER.size + input_header[9] * COMPLEX_INTERVAL.size
            )
            if len(output_raw) - output_offset < OUTPUT_HEADER.size:
                _fail("independent MPFR replay output header is truncated")
            output_header = OUTPUT_HEADER.unpack_from(output_raw, output_offset)
            output_size = (
                OUTPUT_HEADER.size + output_header[6] * COMPLEX_INTERVAL.size
            )
            input_frame = root / "input.bin"
            output_frame = root / "output.bin"
            input_frame.write_bytes(
                input_raw[input_offset : input_offset + input_size]
            )
            output_frame.write_bytes(
                output_raw[output_offset : output_offset + output_size]
            )
            stderr_path = root / "checker.stderr"
            with stderr_path.open("wb") as checker_stderr:
                completed = _run_bounded_process(
                    [
                        str(checker.resolve()),
                        "verify",
                        str(input_frame),
                        str(output_frame),
                        str(precision),
                    ],
                    label=f"independent MPFR frame {frames}",
                    timeout_seconds=process_timeout_seconds,
                    stdout=subprocess.DEVNULL,
                    stderr=checker_stderr,
                )
            if completed.returncode != 0:
                diagnostic = _bounded_optional_read(
                    stderr_path,
                    MAX_DIAGNOSTIC_BYTES,
                    label="independent MPFR checker stderr",
                )
                _fail(
                    "independent MPFR all-character replay failed for "
                    f"frame {frames}: "
                    + diagnostic.decode("utf-8", errors="replace")
                )
            _bounded_optional_read(
                stderr_path,
                MAX_DIAGNOSTIC_BYTES,
                label="independent MPFR checker stderr",
            )
            input_offset += input_size
            output_offset += output_size
            frames += 1
    if input_offset != len(input_raw) or output_offset != len(output_raw):
        _fail("independent MPFR replay streams contain trailing bytes")
    return frames


def replay_scheduled_pipeline(
    pipeline_receipt_path: Path,
    *,
    composer_python: Path,
    composer_tool: Path,
    allchars_checker: Path,
    consumer_python: Path,
    consumer_tool: Path,
    control_base: Path,
    precision: int = 192,
    allow_synthetic_kat: bool = False,
    process_timeout_seconds: float = DEFAULT_REPLAY_PROCESS_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Freshly replay a retained bounded graph without rerunning CUDA."""

    effective_process_timeout = _positive_timeout(
        process_timeout_seconds,
        label="replay process timeout",
        allow_none=False,
    )
    assert effective_process_timeout is not None
    replay_component_invocations = {
        "composer_python": _invocation_artifact_record(
            composer_python, label="replay composer Python"
        ),
        "composer_tool": _invocation_artifact_record(
            composer_tool.resolve(), label="replay composer tool"
        ),
        "allchars_checker": _invocation_artifact_record(
            allchars_checker.resolve(), label="replay all-character checker"
        ),
        "consumer_python": _invocation_artifact_record(
            consumer_python, label="replay consumer Python"
        ),
        "consumer_tool": _invocation_artifact_record(
            consumer_tool.resolve(), label="replay consumer tool"
        ),
    }
    receipt = _canonical_object(
        pipeline_receipt_path, label="scheduled pipeline receipt"
    )
    receipt_sha = _self_hash(
        receipt, "receipt_sha256", label="scheduled pipeline receipt"
    )
    if (
        receipt.get("kind") != RECEIPT_SCHEMA
        or receipt.get("algorithm_id") != ALGORITHM_ID
        or receipt.get("bounded_streams_retained_for_replay") is not True
        or receipt.get("isolated_process_groups") is not True
        or receipt.get("independent_replay_completed") is not False
        or receipt.get("external_atom_discharged") is not False
    ):
        _fail("scheduled pipeline receipt is not replayable")
    maximum_capture_bytes = receipt.get("maximum_capture_bytes")
    if (
        isinstance(maximum_capture_bytes, bool)
        or not isinstance(maximum_capture_bytes, int)
        or maximum_capture_bytes <= 0
        or maximum_capture_bytes > MAXIMUM_KAT_CAPTURE_BYTES
    ):
        _fail("scheduled pipeline receipt has no safe capture bound")
    _positive_timeout(
        receipt.get("process_timeout_seconds"),
        label="recorded process timeout",
        allow_none=False,
    )
    component_invocations = receipt.get("component_invocations")
    required_component_invocations = {
        "composer_python",
        "composer_tool",
        "allchars_runner",
        "consumer_python",
        "consumer_tool",
        "bounded_stream_tee",
    }
    if (
        not isinstance(component_invocations, dict)
        or set(component_invocations) != required_component_invocations
        or component_invocations.get("bounded_stream_tee") is None
    ):
        _fail("scheduled pipeline component invocation map differs")
    for name in sorted(required_component_invocations):
        _check_invocation_artifact_record(
            component_invocations[name],
            label=f"recorded {name}",
        )
    schedule_path = _check_artifact_record(
        receipt.get("schedule_manifest"), label="TGDQORD1"
    )
    schedule = parse_schedule_manifest(schedule_path)
    _schedule_binding(receipt, schedule, label="pipeline")
    controls = receipt.get("controls")
    captures = receipt.get("captures")
    summaries = receipt.get("summaries")
    if not all(isinstance(value, dict) for value in (controls, captures, summaries)):
        _fail("scheduled replay artifact maps differ")
    assert isinstance(controls, dict)
    assert isinstance(captures, dict)
    assert isinstance(summaries, dict)
    composition_controls = _check_artifact_record(
        controls.get("composition"), label="composition controls"
    )
    consumer_controls = _check_artifact_record(
        controls.get("consumer"), label="consumer controls"
    )
    input_capture, input_raw = _check_bounded_artifact_record(
        captures.get("TGDAFFI1"),
        maximum=maximum_capture_bytes,
        label="TGDAFFI1 capture",
    )
    output_capture, output_raw = _check_bounded_artifact_record(
        captures.get("TGDAFFO1"),
        maximum=maximum_capture_bytes,
        label="TGDAFFO1 capture",
    )
    input_tee_receipt = _check_artifact_record(
        captures.get("TGDAFFI1_tee_receipt"),
        label="TGDAFFI1 tee receipt",
    )
    output_tee_receipt = _check_artifact_record(
        captures.get("TGDAFFO1_tee_receipt"),
        label="TGDAFFO1 tee receipt",
    )
    transform_summary_path = _check_artifact_record(
        summaries.get("transform"), label="transform summary"
    )
    events_path = _check_artifact_record(
        summaries.get("events"), label="consumer events"
    )
    consumer_receipt_path = _check_artifact_record(
        summaries.get("consumer"), label="consumer receipt"
    )
    retained_consumer_receipt = _canonical_object(
        consumer_receipt_path,
        label="retained scheduled consumer receipt",
    )
    _self_hash(
        retained_consumer_receipt,
        "receipt_sha256",
        label="retained scheduled consumer receipt",
    )
    if (
        _validate_consumer_event_binding(
            retained_consumer_receipt, events_path
        )
        != summaries.get("events")
    ):
        _fail("retained consumer event artifact binding differs")
    root_catalog_record = receipt.get("root_catalog")
    root_catalog_path = _check_artifact_record(
        root_catalog_record, label="root catalog"
    )
    root_catalog_directory_raw = receipt.get("root_catalog_directory")
    if (
        not isinstance(root_catalog_directory_raw, str)
        or not root_catalog_directory_raw
    ):
        _fail("scheduled pipeline receipt omits its root catalog directory")
    root_catalog_directory = Path(root_catalog_directory_raw)
    assert isinstance(root_catalog_record, dict)
    catalog_sha = _digest(
        root_catalog_record.get("sha256"), "root catalog.sha256"
    )

    inventory = validate_scheduled_control_alignment(
        composition_controls,
        consumer_controls,
        schedule_manifest_path=schedule_path,
        base=control_base,
        maximum_batch_count=int(receipt["maximum_batch_count"]),
        require_full_source=False,
        allow_synthetic_kat=allow_synthetic_kat,
    )
    _validate_root_catalog_for_schedule(
        inventory.schedule,
        root_catalog_path=root_catalog_path,
        root_catalog_sha256=catalog_sha,
        root_catalog_directory=root_catalog_directory,
        require_full_source=False,
    )
    _validate_tee_receipt(
        input_tee_receipt,
        role="TGDAFFI1",
        schedule=schedule,
        capture=input_capture,
        maximum_capture_bytes=maximum_capture_bytes,
    )
    _validate_tee_receipt(
        output_tee_receipt,
        role="TGDAFFO1",
        schedule=schedule,
        capture=output_capture,
        maximum_capture_bytes=maximum_capture_bytes,
    )
    try:
        transform_summary = json.loads(
            _bounded_read(
                transform_summary_path,
                MAX_JSON_BYTES,
                label="transform summary during replay",
            )
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletScheduledPipelineError(
            "invalid transform summary during replay"
        ) from error
    validate_scheduled_multiq_framed_summary(
        transform_summary,
        manifest=schedule_path,
        input_stream=input_raw,
        output_stream=output_raw,
    )

    with tempfile.TemporaryDirectory(
        prefix="tg-dirichlet-scheduled-producer-replay-"
    ) as temporary:
        replay_root = Path(temporary)
        replay_controls = replay_root / "composition.ndjson"
        replay_rows = []
        for index, raw in enumerate(
            _bounded_read(
                composition_controls,
                MAX_CONTROL_BYTES,
                label="composition controls",
            ).splitlines(keepends=True)
        ):
            request = _canonical_line(
                raw, label=f"composition replay control {index}"
            )
            request["receipt"] = str(
                replay_root / f"composition-{index}.receipt.json"
            )
            replay_rows.append(canonical_json_bytes(request))
        replay_controls.write_bytes(b"".join(replay_rows))
        replay_summary = replay_root / "summary.json"
        command = [
            str(composer_python.absolute()),
            str(composer_tool.resolve()),
            "--max-batch-count",
            str(receipt["maximum_batch_count"]),
            "framed-produce",
            str(replay_summary),
            "--base",
            str(control_base.resolve()),
            "--schedule-manifest",
            str(schedule_path.resolve()),
        ]
        if allow_synthetic_kat:
            command.append("--allow-synthetic-kat")
        replay_output = replay_root / "TGDAFFI1.replay.bin"
        replay_stderr = replay_root / "producer.stderr"
        with (
            replay_controls.open("rb") as replay_control_input,
            replay_output.open("xb") as replay_output_handle,
            replay_stderr.open("xb") as replay_stderr_handle,
        ):
            completed = _run_bounded_process(
                command,
                label="fresh scheduled producer",
                timeout_seconds=effective_process_timeout,
                stdin=replay_control_input,
                stdout=replay_output_handle,
                stderr=replay_stderr_handle,
            )
        replay_diagnostic = _bounded_optional_read(
            replay_stderr,
            MAX_DIAGNOSTIC_BYTES,
            label="fresh scheduled producer stderr",
        )
        if completed.returncode != 0:
            _fail(
                "fresh scheduled producer process failed: "
                + replay_diagnostic.decode("utf-8", errors="replace")
            )
        replay_output_raw = _bounded_read(
            replay_output,
            maximum_capture_bytes,
            label="fresh scheduled producer output",
        )
        replay_producer_summary = _canonical_object(
            replay_summary, label="replayed producer summary"
        )
        _self_hash(
            replay_producer_summary,
            "summary_sha256",
            label="replayed producer summary",
        )
        _schedule_binding(
            replay_producer_summary, schedule, label="replayed producer"
        )
        if (
            sha256_bytes(replay_output_raw) != sha256_bytes(input_raw)
            or replay_output_raw != input_raw
            or replay_producer_summary.get("TGDAFFI1_stream_sha256")
            != sha256_bytes(input_raw)
        ):
            _fail("fresh scheduled producer replay differs byte-for-byte")
    mpfr_frames = _mpfr_replay_transform_frames(
        input_raw,
        output_raw,
        checker=allchars_checker,
        precision=precision,
        process_timeout_seconds=effective_process_timeout,
    )
    with tempfile.TemporaryDirectory(
        prefix="tg-dirichlet-scheduled-consumer-replay-"
    ) as temporary:
        consumer_replay_root = Path(temporary)
        consumer_stdout = consumer_replay_root / "consumer.stdout"
        consumer_stderr = consumer_replay_root / "consumer.stderr"
        with (
            consumer_stdout.open("xb") as consumer_stdout_handle,
            consumer_stderr.open("xb") as consumer_stderr_handle,
        ):
            consumer_completed = _run_bounded_process(
                [
                    str(consumer_python.absolute()),
                    str(consumer_tool.resolve()),
                    "verify",
                    str(consumer_controls.resolve()),
                    str(output_capture.resolve()),
                    str(events_path.resolve()),
                    str(consumer_receipt_path.resolve()),
                    "--precision",
                    str(precision),
                    "--schedule-manifest",
                    str(schedule_path.resolve()),
                    "--root-catalog",
                    str(root_catalog_path.resolve()),
                    "--root-catalog-sha256",
                    catalog_sha,
                    "--root-catalog-directory",
                    str(root_catalog_directory.resolve()),
                ],
                label="fresh scheduled Arb consumer",
                timeout_seconds=effective_process_timeout,
                stdout=consumer_stdout_handle,
                stderr=consumer_stderr_handle,
            )
        consumer_stdout_raw = _bounded_optional_read(
            consumer_stdout,
            MAX_JSON_BYTES,
            label="fresh scheduled consumer stdout",
        )
        consumer_diagnostic = _bounded_optional_read(
            consumer_stderr,
            MAX_DIAGNOSTIC_BYTES,
            label="fresh scheduled consumer stderr",
        )
    if consumer_completed.returncode != 0:
        _fail(
            "fresh scheduled Arb consumer replay failed: "
            + consumer_diagnostic.decode("utf-8", errors="replace")
        )
    if not consumer_stdout_raw:
        _fail("fresh scheduled consumer replay emitted no JSON")
    consumer_replay = _canonical_line(
        consumer_stdout_raw,
        label="fresh scheduled consumer replay stdout",
    )
    if (
        not isinstance(consumer_replay, dict)
        or consumer_replay.get("accepted") is not True
    ):
        _fail("fresh scheduled consumer replay did not accept")
    rebound_replay_invocations = {
        "composer_python": _invocation_artifact_record(
            composer_python, label="replay composer Python"
        ),
        "composer_tool": _invocation_artifact_record(
            composer_tool.resolve(), label="replay composer tool"
        ),
        "allchars_checker": _invocation_artifact_record(
            allchars_checker.resolve(), label="replay all-character checker"
        ),
        "consumer_python": _invocation_artifact_record(
            consumer_python, label="replay consumer Python"
        ),
        "consumer_tool": _invocation_artifact_record(
            consumer_tool.resolve(), label="replay consumer tool"
        ),
    }
    if rebound_replay_invocations != replay_component_invocations:
        _fail("replay invocation artifact changed during execution")
    result = {
        "kind": REPLAY_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "bounded_fresh_component_replay_not_zero_or_grh_closure"
        ),
        "pipeline_receipt_sha256": receipt_sha,
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "maximum_capture_bytes": maximum_capture_bytes,
        "process_timeout_seconds": effective_process_timeout,
        "isolated_process_groups": True,
        "replay_component_invocations": replay_component_invocations,
        "producer_byte_identical": True,
        "transform_frames_independently_verified_with_MPFR": mpfr_frames,
        "consumer_fresh_Arb_replay_accepted": consumer_replay["accepted"],
        "exact_q_t_coverage_replayed": True,
        "increasing_q_assumed": False,
        "source_scale_execution_completed": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    result["replay_sha256"] = sha256_bytes(canonical_json_bytes(result))
    return result


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": (
            "receipt_preserving_schedule_integration_not_external_evidence"
        ),
        "TGDQORD1_bound_in_producer_transform_consumer_and_supervisor": True,
        "actual_q_labels_retained": True,
        "exact_q_t_coverage_required": True,
        "increasing_q_assumed": False,
        "OS_pipe_backpressure": True,
        "fail_fast_sibling_cancellation": True,
        "isolated_process_group_cancellation": True,
        "component_invocation_artifacts_bound": True,
        "consumer_event_digest_and_size_bound": True,
        "bounded_capture_limit_receipt_bound": True,
        "bounded_process_timeouts": True,
        "bounded_independent_replay": True,
        "transform_stream_materialization_required": False,
        "bounded_control_file_supervisor_implemented": True,
        "formulaic_source_control_producer_integrated": False,
        "source_scale_streaming_replay_integrated": False,
        "source_scale_execution_completed": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "DEFAULT_BOUNDED_PROCESS_TIMEOUT_SECONDS",
    "DEFAULT_KAT_CAPTURE_BYTES",
    "DEFAULT_REPLAY_PROCESS_TIMEOUT_SECONDS",
    "MAXIMUM_KAT_CAPTURE_BYTES",
    "DirichletScheduledPipelineError",
    "RECEIPT_SCHEMA",
    "REPLAY_SCHEMA",
    "ScheduledControlInventory",
    "capability",
    "replay_scheduled_pipeline",
    "run_scheduled_pipeline",
    "validate_scheduled_control_alignment",
]
