# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Preemption-tolerant work-unit scheduler for the Platt PT21 windowed campaign.

``platt_windowed_campaign`` fixes the mathematics: the ``1008``-height logical
block grid starting at ``10^10``, the fail-closed transcript contract, and the
telescoping Turing-count chain.  It runs one immutable ``16384``-block shard
per process invocation, which is roughly one core-day of work with no interior
checkpoint.  That is not a schedulable unit on preemptible capacity.

This module keeps every mathematical rule of that engine and replaces only the
operational layer:

* a **work unit** is a contiguous run of ``blocks_per_unit`` logical blocks,
  sized so that the fixed per-invocation start cost is amortized while the
  expected loss from one preemption stays small;
* a unit may be executed as several **segments** across process lifetimes.  A
  segment is a fresh runner invocation covering the blocks that the previous
  segments did not commit.  The source program is stateless across logical
  blocks, so segmentation is semantically invisible;
* the unit's identity is its **semantic digest**, which excludes wall time and
  segmentation.  Any re-run of a unit, whole or segmented, on any machine,
  reproduces that digest byte for byte, or the campaign fails closed;
* receipts aggregate hierarchically: units into a sealed shard, shards into one
  small campaign artifact.  No stage ever holds the whole unit set in memory.

Nothing here weakens the trust boundary.  ``source_claim_ready`` stays false:
the prefix below ``10^10`` and the Hardy-Z/Turing analytic realization are
separate obligations, and this module only records which of them are bound.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import tempfile
import time
from typing import Any, Callable, Iterator

from tg_verifier.platt_windowed_campaign import (
    FULL_BLOCK_COUNT,
    LOOKING_RE,
    MERKLE_LEAF_DOMAIN,
    MERKLE_NODE_DOMAIN,
    PRECISION_BITS,
    SOURCE_COMMIT,
    SOURCE_COUNT,
    SOURCE_HEIGHT,
    SOURCE_LOWER,
    SOURCE_LOWER_COUNT,
    SOURCE_MAXIMUM,
    SOURCE_SET_SHA256,
    STEP,
    SUCCESS_RE,
    FORBIDDEN_OUTPUT,
    parse_transcript,
)


SCHEDULE_SCHEMA = "sparkinterval.tg.platt-pt21-windowed-schedule.v1"
UNIT_SCHEMA = "sparkinterval.tg.platt-pt21-windowed-unit.v1"
SHARD_SCHEMA = "sparkinterval.tg.platt-pt21-windowed-shard-seal.v1"
CAMPAIGN_SCHEMA = "sparkinterval.tg.platt-pt21-windowed-campaign.v1"

SCHEDULE_DOMAIN = b"sparkinterval/tg/platt-pt21-windowed-schedule/v1\0"
UNIT_DOMAIN = b"sparkinterval/tg/platt-pt21-windowed-unit/v1\0"
SHARD_DOMAIN = b"sparkinterval/tg/platt-pt21-windowed-shard-seal/v1\0"
CAMPAIGN_DOMAIN = b"sparkinterval/tg/platt-pt21-windowed-campaign/v1\0"

SCHEDULE_NAME = "schedule.json"
CAMPAIGN_NAME = "campaign.json"
SHARD_NAME = "shard.json"
UNIT_DIGEST_NAME = "unit-digests.txt"

#: One unit is about three quarters of a core-hour at the measured
#: ``5.37875`` s/block source rate.  See the campaign document for the
#: start-cost/preemption trade that selects it.
DEFAULT_BLOCKS_PER_UNIT = 512
#: ``512 * 2048 == 2^20`` blocks, the shard geometry already used by the H100
#: plan, so the two schedules describe the same brackets.
DEFAULT_UNITS_PER_SHARD = 2048
DEFAULT_CHECKPOINT_BLOCKS = 32
DEFAULT_LEASE_SECONDS = 7_200
MAX_BLOCKS_PER_UNIT = 1 << 20
MAX_UNITS_PER_SHARD = 1 << 20

_HEX64 = re.compile(r"[0-9a-f]{64}")
_WORKER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")


class PlattWindowedScheduleError(RuntimeError):
    """A schedule, claim, unit execution, seal, or aggregate failed closed."""


class PlattWindowedPreempted(PlattWindowedScheduleError):
    """The worker was asked to stop; committed progress was checkpointed."""


# --------------------------------------------------------------------------
# canonical encoding helpers
# --------------------------------------------------------------------------


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical(value)).hexdigest()


def _sha256_file(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise PlattWindowedScheduleError(f"not a regular file: {path}")
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlattWindowedScheduleError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise PlattWindowedScheduleError(f"JSON object required: {path}")
    return value


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _merkle_root(leaves: list[str]) -> str:
    """Same rule as ``platt_windowed_campaign``: domain-separated leaves and
    nodes, odd levels duplicate their final entry."""

    if not leaves:
        raise PlattWindowedScheduleError("cannot aggregate an empty receipt set")
    level = [
        hashlib.sha256(MERKLE_LEAF_DOMAIN + bytes.fromhex(leaf)).digest()
        for leaf in leaves
    ]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(MERKLE_NODE_DOMAIN + level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


# --------------------------------------------------------------------------
# immutable geometry
# --------------------------------------------------------------------------


def create_schedule(
    *,
    runner_sha256: str,
    runner_size: int,
    source_manifest_sha256: str,
    source_manifest_size: int,
    blocks_per_unit: int = DEFAULT_BLOCKS_PER_UNIT,
    units_per_shard: int = DEFAULT_UNITS_PER_SHARD,
    block_count: int = FULL_BLOCK_COUNT,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    for digest in (runner_sha256, source_manifest_sha256):
        if not _HEX64.fullmatch(digest):
            raise PlattWindowedScheduleError("a pinned digest is malformed")
    if runner_size < 1 or source_manifest_size < 1:
        raise PlattWindowedScheduleError("runner and source manifest must be nonempty")
    if not 1 <= blocks_per_unit <= MAX_BLOCKS_PER_UNIT:
        raise PlattWindowedScheduleError("blocks_per_unit is outside the permitted range")
    if not 1 <= units_per_shard <= MAX_UNITS_PER_SHARD:
        raise PlattWindowedScheduleError("units_per_shard is outside the permitted range")
    if block_count < 1:
        raise PlattWindowedScheduleError("block_count must be positive")
    if block_count != FULL_BLOCK_COUNT and not allow_bounded_test:
        raise PlattWindowedScheduleError("bounded geometry requires allow_bounded_test")
    coverage_upper = SOURCE_LOWER + block_count * STEP
    if coverage_upper > SOURCE_MAXIMUM:
        raise PlattWindowedScheduleError("schedule exceeds the source parameter maximum")
    unit_count = (block_count + blocks_per_unit - 1) // blocks_per_unit
    shard_count = (unit_count + units_per_shard - 1) // units_per_shard
    schedule: dict[str, Any] = {
        "schema": SCHEDULE_SCHEMA,
        "mode": (
            "full_source_high_range"
            if block_count == FULL_BLOCK_COUNT
            else "bounded_test"
        ),
        "source": {
            "repository_commit": SOURCE_COMMIT,
            "reviewed_source_sha256": SOURCE_SET_SHA256,
            "manifest_sha256": source_manifest_sha256,
            "manifest_size_bytes": source_manifest_size,
            "license": "NOASSERTION",
            "redistribution": "not-authorized-by-this-manifest",
        },
        "runner": {"sha256": runner_sha256, "size_bytes": runner_size},
        "claim": {
            "source_height": SOURCE_HEIGHT,
            "source_multiplicity_count": SOURCE_COUNT,
            "windowed_lower": SOURCE_LOWER,
            "windowed_lower_multiplicity_count": SOURCE_LOWER_COUNT,
            "coverage_upper": coverage_upper,
            "lower_prefix_required": True,
        },
        "configuration": {
            "precision_bits": PRECISION_BITS,
            "step": STEP,
            "blocks_per_unit": blocks_per_unit,
            "units_per_shard": units_per_shard,
        },
        "geometry": {
            "block_count": block_count,
            "unit_count": unit_count,
            "shard_count": shard_count,
            "blocks_per_shard": blocks_per_unit * units_per_shard,
        },
        "allow_bounded_test": allow_bounded_test,
    }
    schedule["schedule_sha256"] = _digest(
        SCHEDULE_DOMAIN, {k: v for k, v in schedule.items()}
    )
    return schedule


def validate_schedule(schedule: dict[str, Any]) -> None:
    expected_top = {
        "allow_bounded_test",
        "claim",
        "configuration",
        "geometry",
        "mode",
        "runner",
        "schedule_sha256",
        "schema",
        "source",
    }
    if set(schedule) != expected_top or schedule.get("schema") != SCHEDULE_SCHEMA:
        raise PlattWindowedScheduleError("schedule shape changed")
    body = {k: v for k, v in schedule.items() if k != "schedule_sha256"}
    if schedule["schedule_sha256"] != _digest(SCHEDULE_DOMAIN, body):
        raise PlattWindowedScheduleError("schedule digest differs")
    rebuilt = create_schedule(
        runner_sha256=schedule["runner"]["sha256"],
        runner_size=schedule["runner"]["size_bytes"],
        source_manifest_sha256=schedule["source"]["manifest_sha256"],
        source_manifest_size=schedule["source"]["manifest_size_bytes"],
        blocks_per_unit=schedule["configuration"]["blocks_per_unit"],
        units_per_shard=schedule["configuration"]["units_per_shard"],
        block_count=schedule["geometry"]["block_count"],
        allow_bounded_test=schedule["allow_bounded_test"],
    )
    if rebuilt != schedule:
        raise PlattWindowedScheduleError("schedule values differ from fixed geometry")


def unit_block_range(schedule: dict[str, Any], unit_index: int) -> tuple[int, int]:
    """Deterministic assignment.  Depends on nothing but the immutable plan."""

    validate_schedule(schedule)
    if not isinstance(unit_index, int) or isinstance(unit_index, bool):
        raise PlattWindowedScheduleError("unit index must be an integer")
    if unit_index < 0 or unit_index >= schedule["geometry"]["unit_count"]:
        raise PlattWindowedScheduleError("unit index is outside the fixed schedule")
    span = schedule["configuration"]["blocks_per_unit"]
    first = unit_index * span
    upper = min(first + span, schedule["geometry"]["block_count"])
    return first, upper


def shard_unit_range(schedule: dict[str, Any], shard_index: int) -> tuple[int, int]:
    validate_schedule(schedule)
    if not isinstance(shard_index, int) or isinstance(shard_index, bool):
        raise PlattWindowedScheduleError("shard index must be an integer")
    if shard_index < 0 or shard_index >= schedule["geometry"]["shard_count"]:
        raise PlattWindowedScheduleError("shard index is outside the fixed schedule")
    span = schedule["configuration"]["units_per_shard"]
    first = shard_index * span
    upper = min(first + span, schedule["geometry"]["unit_count"])
    return first, upper


def shard_of_unit(schedule: dict[str, Any], unit_index: int) -> int:
    validate_schedule(schedule)
    return unit_index // schedule["configuration"]["units_per_shard"]


def height_of_block(block: int) -> int:
    return SOURCE_LOWER + block * STEP


# --------------------------------------------------------------------------
# on-disk layout
# --------------------------------------------------------------------------


def _shard_directory(directory: Path, shard_index: int) -> Path:
    return directory / "shards" / f"shard-{shard_index:06d}"


def _unit_receipt_path(directory: Path, schedule: dict[str, Any], unit: int) -> Path:
    shard = shard_of_unit(schedule, unit)
    return _shard_directory(directory, shard) / "units" / f"unit-{unit:010d}.json"


def _unit_log_path(directory: Path, schedule: dict[str, Any], unit: int) -> Path:
    shard = shard_of_unit(schedule, unit)
    return _shard_directory(directory, shard) / "logs" / f"unit-{unit:010d}.log"


def _unit_checkpoint_path(directory: Path, schedule: dict[str, Any], unit: int) -> Path:
    shard = shard_of_unit(schedule, unit)
    return _shard_directory(directory, shard) / "progress" / f"unit-{unit:010d}.json"


def _lease_path(directory: Path, unit: int) -> Path:
    return directory / "leases" / f"unit-{unit:010d}.lease"


def _shard_receipt_path(directory: Path, shard_index: int) -> Path:
    return _shard_directory(directory, shard_index) / SHARD_NAME


def initialize_schedule(
    *,
    output_directory: Path,
    runner: Path,
    source_manifest: Path,
    blocks_per_unit: int = DEFAULT_BLOCKS_PER_UNIT,
    units_per_shard: int = DEFAULT_UNITS_PER_SHARD,
    block_count: int = FULL_BLOCK_COUNT,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    mode = runner.stat().st_mode if runner.exists() else 0
    if runner.is_symlink() or not stat.S_ISREG(mode) or not os.access(runner, os.X_OK):
        raise PlattWindowedScheduleError("runner must be an executable regular file")
    manifest = _load_json(source_manifest)
    if (
        manifest.get("kind") != "sparkinterval.pinned_platt_pt21_windowed_source.v1"
        or manifest.get("commit") != SOURCE_COMMIT
        or manifest.get("reviewed_source_sha256") != SOURCE_SET_SHA256
        or manifest.get("license") != "NOASSERTION"
    ):
        raise PlattWindowedScheduleError("source manifest does not match the reviewed pin")
    runner_sha, runner_size = _sha256_file(runner)
    manifest_sha, manifest_size = _sha256_file(source_manifest)
    schedule = create_schedule(
        runner_sha256=runner_sha,
        runner_size=runner_size,
        source_manifest_sha256=manifest_sha,
        source_manifest_size=manifest_size,
        blocks_per_unit=blocks_per_unit,
        units_per_shard=units_per_shard,
        block_count=block_count,
        allow_bounded_test=allow_bounded_test,
    )
    if output_directory.exists() and any(output_directory.iterdir()):
        raise PlattWindowedScheduleError("schedule output directory must be empty")
    output_directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(output_directory / SCHEDULE_NAME, _canonical(schedule) + b"\n")
    return schedule


def load_schedule(directory: Path) -> dict[str, Any]:
    schedule = _load_json(directory / SCHEDULE_NAME)
    validate_schedule(schedule)
    return schedule


def _runner_identity(runner: Path, schedule: dict[str, Any]) -> None:
    actual = _sha256_file(runner)
    expected = (schedule["runner"]["sha256"], schedule["runner"]["size_bytes"])
    if actual != expected:
        raise PlattWindowedScheduleError("runner identity differs from the schedule")


# --------------------------------------------------------------------------
# leases: advisory only, correctness never depends on them
# --------------------------------------------------------------------------


def _now() -> float:
    return time.time()


def _validate_worker_id(worker_id: str) -> str:
    if not isinstance(worker_id, str) or not _WORKER_ID.fullmatch(worker_id):
        raise PlattWindowedScheduleError("worker identifier is malformed")
    return worker_id


def default_worker_id() -> str:
    raw = f"{socket.gethostname()}-{os.getpid()}"
    cleaned = re.sub(r"[^A-Za-z0-9._:-]", "-", raw)[:64]
    return cleaned if _WORKER_ID.fullmatch(cleaned) else f"worker-{os.getpid()}"


def _write_lease(path: Path, unit: int, worker_id: str, lease_seconds: int) -> None:
    payload = _canonical(
        {
            "unit_index": unit,
            "worker_id": worker_id,
            "pid": os.getpid(),
            "claimed_at_unix": int(_now()),
            "lease_seconds": lease_seconds,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _lease_is_live(path: Path, lease_seconds: int) -> bool:
    try:
        age = _now() - path.stat().st_mtime
    except FileNotFoundError:
        return False
    return age < lease_seconds


def claim_unit(
    directory: Path,
    schedule: dict[str, Any],
    unit: int,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    steal_expired: bool = True,
) -> bool:
    """Try to take one unit.  Returns ``False`` when another live worker holds it.

    A lease is a hint that lets independent workers avoid duplicating effort.
    It is deliberately not a lock: two workers that both run the same unit
    write the same semantic digest, and :func:`_commit_unit` rejects any
    disagreement.  Losing a lease therefore costs time, never correctness.
    """

    _validate_worker_id(worker_id)
    if lease_seconds < 1:
        raise PlattWindowedScheduleError("lease_seconds must be positive")
    unit_block_range(schedule, unit)
    if _unit_receipt_path(directory, schedule, unit).exists():
        return False
    path = _lease_path(directory, unit)
    try:
        _write_lease(path, unit, worker_id, lease_seconds)
        return True
    except FileExistsError:
        pass
    if not steal_expired or _lease_is_live(path, lease_seconds):
        return False
    # The previous holder is past its lease.  Remove and retry once; a racing
    # stealer may win, which is harmless.
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    try:
        _write_lease(path, unit, worker_id, lease_seconds)
        return True
    except FileExistsError:
        return False


def release_unit(directory: Path, unit: int) -> None:
    _lease_path(directory, unit).unlink(missing_ok=True)


def _renew_lease(directory: Path, unit: int) -> None:
    path = _lease_path(directory, unit)
    try:
        os.utime(path, None)
    except FileNotFoundError:
        pass


def next_unit(
    directory: Path,
    schedule: dict[str, Any],
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    from_shard: int = 0,
    stride: int = 1,
    offset: int = 0,
    shard_budget: int | None = None,
) -> int | None:
    """Claim the next runnable unit at or after ``from_shard``.

    Scanning is per shard, so a worker never enumerates the whole unit space.
    A sealed shard is skipped without listing its units at all: that is what
    keeps resume cost bounded once most of a multi-billion-block campaign is
    finished.  ``stride``/``offset`` give a fixed partition among cooperating
    workers; expired leases are still stolen so that a lost node's units are
    picked up by whoever reaches them.
    """

    validate_schedule(schedule)
    if stride < 1 or not 0 <= offset < stride:
        raise PlattWindowedScheduleError("stride/offset partition is malformed")
    shard_count = schedule["geometry"]["shard_count"]
    if not 0 <= from_shard < max(shard_count, 1):
        raise PlattWindowedScheduleError("from_shard is outside the fixed schedule")
    examined = 0
    for shard in range(from_shard, shard_count):
        if shard_budget is not None and examined >= shard_budget:
            return None
        examined += 1
        if _shard_receipt_path(directory, shard).exists():
            continue
        first, upper = shard_unit_range(schedule, shard)
        units_dir = _shard_directory(directory, shard) / "units"
        try:
            present = {entry.name for entry in os.scandir(units_dir)}
        except FileNotFoundError:
            present = set()
        for unit in range(first, upper):
            if unit % stride != offset:
                continue
            if f"unit-{unit:010d}.json" in present:
                continue
            if claim_unit(
                directory,
                schedule,
                unit,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            ):
                return unit
    return None


# --------------------------------------------------------------------------
# segmented, checkpointed unit execution
# --------------------------------------------------------------------------


def _validate_records(records: list[dict[str, int]], first_block: int) -> None:
    previous: int | None = None
    for offset, record in enumerate(records):
        if record["block"] != first_block + offset:
            raise PlattWindowedScheduleError("committed record grid is not contiguous")
        if previous is not None and record["count_lower"] != previous:
            raise PlattWindowedScheduleError("committed Turing counts are not contiguous")
        previous = record["count_upper"]


def _parse_committed_prefix(
    lines: list[str], *, first_block: int
) -> tuple[list[dict[str, int]], str, int]:
    """Parse the longest prefix of ``lines`` that ends at a block boundary.

    Returns the committed records, the exact committed text, and how many
    lines were consumed.  The tail after the final success line belongs to a
    block that has not finished and is discarded on checkpoint.
    """

    boundary = 0
    completed = 0
    for index, line in enumerate(lines):
        if SUCCESS_RE.fullmatch(line) is not None:
            boundary = index + 1
            completed += 1
    if completed == 0:
        return [], "", 0
    text = "".join(f"{line}\n" for line in lines[:boundary])
    parsed = parse_transcript(text, first_block=first_block, block_count=completed)
    return parsed["records"], text, boundary


def _load_checkpoint(
    path: Path, schedule: dict[str, Any], unit: int
) -> tuple[list[dict[str, int]], list[dict[str, Any]]]:
    if not path.exists():
        return [], []
    value = _load_json(path)
    first, upper = unit_block_range(schedule, unit)
    if (
        value.get("schedule_sha256") != schedule["schedule_sha256"]
        or value.get("unit_index") != unit
        or value.get("first_block") != first
        or value.get("upper_block_exclusive") != upper
    ):
        raise PlattWindowedScheduleError("retained checkpoint does not match the schedule")
    records = value.get("records")
    segments = value.get("segments")
    if not isinstance(records, list) or not isinstance(segments, list):
        raise PlattWindowedScheduleError("retained checkpoint is malformed")
    if len(records) > upper - first:
        raise PlattWindowedScheduleError("retained checkpoint overruns its unit")
    _validate_records(records, first)
    return records, segments


def _store_checkpoint(
    path: Path,
    schedule: dict[str, Any],
    unit: int,
    records: list[dict[str, int]],
    segments: list[dict[str, Any]],
) -> None:
    first, upper = unit_block_range(schedule, unit)
    _atomic_write(
        path,
        _canonical(
            {
                "schema": "sparkinterval.tg.platt-pt21-windowed-unit-progress.v1",
                "schedule_sha256": schedule["schedule_sha256"],
                "unit_index": unit,
                "first_block": first,
                "upper_block_exclusive": upper,
                "committed_blocks": len(records),
                "records": records,
                "segments": segments,
            }
        )
        + b"\n",
    )


class _StopRequest:
    """Cooperative preemption flag driven by SIGTERM/SIGINT."""

    def __init__(self) -> None:
        self.requested = False
        self._previous: list[tuple[int, Any]] = []

    def __enter__(self) -> "_StopRequest":
        def handler(signum: int, frame: Any) -> None:  # pragma: no cover - signal path
            self.requested = True

        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                self._previous.append((signum, signal.signal(signum, handler)))
            except ValueError:  # not the main thread
                pass
        return self

    def __exit__(self, *exception: object) -> None:
        for signum, previous in self._previous:
            try:
                signal.signal(signum, previous)
            except ValueError:  # pragma: no cover - not the main thread
                pass


def _run_segment(
    runner: Path,
    *,
    first_block: int,
    block_count: int,
    checkpoint_blocks: int,
    on_progress: Callable[[list[dict[str, int]], str], None],
    stop: _StopRequest,
    timeout_seconds: int | None,
) -> tuple[list[dict[str, int]], str, float]:
    """Execute one runner invocation, streaming and checkpointing as it goes."""

    command = [
        str(runner.resolve()),
        str(PRECISION_BITS),
        str(height_of_block(first_block)),
        str(block_count),
        str(STEP),
    ]
    started = time.monotonic()
    deadline = None if timeout_seconds is None else started + timeout_seconds
    lines: list[str] = []
    committed_blocks = 0
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env={**os.environ, "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
    )
    preempted = False
    try:
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip("\n")
            lowered = line.lower()
            for token in FORBIDDEN_OUTPUT:
                if token in lowered:
                    raise PlattWindowedScheduleError(
                        f"runner transcript contains failure token {token!r}"
                    )
            lines.append(line)
            if SUCCESS_RE.fullmatch(line) is not None:
                committed_blocks += 1
                if committed_blocks % checkpoint_blocks == 0:
                    records, text, _ = _parse_committed_prefix(
                        lines, first_block=first_block
                    )
                    on_progress(records, text)
            if stop.requested:
                preempted = True
                break
            if deadline is not None and time.monotonic() > deadline:
                raise PlattWindowedScheduleError("runner exceeded its timeout")
    finally:
        if preempted:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:  # pragma: no cover - hostile child
                process.kill()
                process.wait()
        else:
            process.wait()
        if process.stdout is not None:
            process.stdout.close()
    elapsed = time.monotonic() - started
    stderr = process.stderr.read() if process.stderr is not None else ""
    if process.stderr is not None:
        process.stderr.close()
    if preempted:
        records, text, _ = _parse_committed_prefix(lines, first_block=first_block)
        raise _SegmentPreempted(records, text, elapsed)
    if stderr:
        raise PlattWindowedScheduleError("windowed checker wrote to stderr")
    if process.returncode != 0:
        raise PlattWindowedScheduleError(
            f"windowed checker exited {process.returncode}"
        )
    text = "".join(f"{line}\n" for line in lines)
    parsed = parse_transcript(text, first_block=first_block, block_count=block_count)
    return parsed["records"], text, elapsed


class _SegmentPreempted(Exception):
    def __init__(
        self, records: list[dict[str, int]], text: str, elapsed: float
    ) -> None:
        super().__init__("segment preempted")
        self.records = records
        self.text = text
        self.elapsed = elapsed


def unit_semantic_digest(
    schedule: dict[str, Any],
    unit: int,
    *,
    first_count: int,
    last_count: int,
    total_zero_count: int,
    records_sha256: str,
) -> str:
    first, upper = unit_block_range(schedule, unit)
    return _digest(
        UNIT_DOMAIN,
        {
            "schedule_sha256": schedule["schedule_sha256"],
            "unit_index": unit,
            "first_block": first,
            "upper_block_exclusive": upper,
            "block_count": upper - first,
            "height_lower": height_of_block(first),
            "height_upper": height_of_block(upper),
            "first_count": first_count,
            "last_count": last_count,
            "total_zero_count": total_zero_count,
            "records_sha256": records_sha256,
            "runner_sha256": schedule["runner"]["sha256"],
            "reviewed_source_sha256": SOURCE_SET_SHA256,
            "precision_bits": PRECISION_BITS,
            "step": STEP,
        },
    )


def _build_unit_receipt(
    schedule: dict[str, Any],
    unit: int,
    records: list[dict[str, int]],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    first, upper = unit_block_range(schedule, unit)
    if len(records) != upper - first:
        raise PlattWindowedScheduleError("unit record count differs from its geometry")
    _validate_records(records, first)
    records_sha256 = hashlib.sha256(_canonical(records)).hexdigest()
    total = sum(record["zero_count"] for record in records)
    first_count = records[0]["count_lower"]
    last_count = records[-1]["count_upper"]
    if last_count - first_count != total:
        raise PlattWindowedScheduleError("unit count chain does not telescope")
    receipt: dict[str, Any] = {
        "schema": UNIT_SCHEMA,
        "schedule_sha256": schedule["schedule_sha256"],
        "unit_index": unit,
        "shard_index": shard_of_unit(schedule, unit),
        "first_block": first,
        "upper_block_exclusive": upper,
        "block_count": upper - first,
        "height_lower": height_of_block(first),
        "height_upper": height_of_block(upper),
        "first_count": first_count,
        "last_count": last_count,
        "total_zero_count": total,
        "records_sha256": records_sha256,
        "runner_sha256": schedule["runner"]["sha256"],
        "reviewed_source_sha256": SOURCE_SET_SHA256,
        "precision_bits": PRECISION_BITS,
        "step": STEP,
        "all_blocks_proved_complete": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "accepted": True,
        "unit_sha256": unit_semantic_digest(
            schedule,
            unit,
            first_count=first_count,
            last_count=last_count,
            total_zero_count=total,
            records_sha256=records_sha256,
        ),
        # Operational only.  Excluded from `unit_sha256` precisely so that a
        # unit re-run as one segment and a unit resumed across preemptions
        # agree byte for byte.
        "segments": segments,
    }
    return receipt


def validate_unit_receipt(
    receipt: dict[str, Any], schedule: dict[str, Any], unit: int
) -> None:
    first, upper = unit_block_range(schedule, unit)
    required = {
        "accepted",
        "all_blocks_proved_complete",
        "block_count",
        "execution_attested",
        "first_block",
        "first_count",
        "height_lower",
        "height_upper",
        "last_count",
        "lean_atom_discharged",
        "precision_bits",
        "records_sha256",
        "reviewed_source_sha256",
        "runner_sha256",
        "schedule_sha256",
        "schema",
        "segments",
        "shard_index",
        "step",
        "total_zero_count",
        "unit_index",
        "unit_sha256",
        "upper_block_exclusive",
    }
    if set(receipt) != required or receipt.get("schema") != UNIT_SCHEMA:
        raise PlattWindowedScheduleError("unit receipt shape changed")
    fixed = {
        "accepted": True,
        "all_blocks_proved_complete": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "schedule_sha256": schedule["schedule_sha256"],
        "precision_bits": PRECISION_BITS,
        "reviewed_source_sha256": SOURCE_SET_SHA256,
        "runner_sha256": schedule["runner"]["sha256"],
        "unit_index": unit,
        "shard_index": shard_of_unit(schedule, unit),
        "step": STEP,
        "first_block": first,
        "upper_block_exclusive": upper,
        "block_count": upper - first,
        "height_lower": height_of_block(first),
        "height_upper": height_of_block(upper),
    }
    if any(receipt.get(key) != value for key, value in fixed.items()):
        raise PlattWindowedScheduleError("unit receipt fixed fields differ")
    for key in ("first_count", "last_count", "total_zero_count"):
        value = receipt[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PlattWindowedScheduleError(f"unit receipt field is malformed: {key}")
    if receipt["last_count"] - receipt["first_count"] != receipt["total_zero_count"]:
        raise PlattWindowedScheduleError("unit receipt count does not telescope")
    for key in ("records_sha256", "unit_sha256"):
        if not isinstance(receipt[key], str) or not _HEX64.fullmatch(receipt[key]):
            raise PlattWindowedScheduleError(f"malformed unit digest: {key}")
    expected = unit_semantic_digest(
        schedule,
        unit,
        first_count=receipt["first_count"],
        last_count=receipt["last_count"],
        total_zero_count=receipt["total_zero_count"],
        records_sha256=receipt["records_sha256"],
    )
    if receipt["unit_sha256"] != expected:
        raise PlattWindowedScheduleError("unit receipt digest differs")


def _commit_unit(
    directory: Path, schedule: dict[str, Any], unit: int, receipt: dict[str, Any]
) -> dict[str, Any]:
    """Idempotent, content-checked commit.

    If a receipt already exists it must have the same ``unit_sha256``.  That
    turns an accidental duplicate execution -- a stolen lease, a retried spot
    node -- into a free cross-check instead of a corruption risk.
    """

    path = _unit_receipt_path(directory, schedule, unit)
    if path.exists():
        retained = _load_json(path)
        validate_unit_receipt(retained, schedule, unit)
        if retained["unit_sha256"] != receipt["unit_sha256"]:
            raise PlattWindowedScheduleError(
                "duplicate execution of a unit produced a different semantic digest"
            )
        return retained
    _atomic_write(path, _canonical(receipt) + b"\n")
    return receipt


def run_unit(
    directory: Path,
    runner: Path,
    unit: int,
    *,
    checkpoint_blocks: int = DEFAULT_CHECKPOINT_BLOCKS,
    retain_log: bool = False,
    timeout_seconds: int | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Run one unit to completion, resuming any checkpointed prefix.

    On SIGTERM/SIGINT the committed prefix is written to the unit's progress
    file and :class:`PlattWindowedPreempted` is raised, so a spot eviction
    costs at most ``checkpoint_blocks`` blocks of recomputation rather than the
    whole unit.
    """

    schedule = load_schedule(directory)
    _runner_identity(runner, schedule)
    if checkpoint_blocks < 1:
        raise PlattWindowedScheduleError("checkpoint_blocks must be positive")
    first, upper = unit_block_range(schedule, unit)
    existing = _unit_receipt_path(directory, schedule, unit)
    if existing.exists():
        retained = _load_json(existing)
        validate_unit_receipt(retained, schedule, unit)
        return retained
    checkpoint_path = _unit_checkpoint_path(directory, schedule, unit)
    records: list[dict[str, int]] = []
    segments: list[dict[str, Any]] = []
    if resume:
        records, segments = _load_checkpoint(checkpoint_path, schedule, unit)
    log_parts: list[str] = []
    with _StopRequest() as stop:
        while len(records) < upper - first:
            segment_first = first + len(records)
            segment_count = upper - segment_first
            base_records = list(records)
            base_segments = list(segments)

            def on_progress(
                fresh: list[dict[str, int]],
                _text: str,
                _first: int = segment_first,
                _base_records: list[dict[str, int]] = base_records,
                _base_segments: list[dict[str, Any]] = base_segments,
            ) -> None:
                merged = _base_records + fresh
                _validate_records(merged, first)
                _store_checkpoint(
                    checkpoint_path, schedule, unit, merged, _base_segments
                )
                _renew_lease(directory, unit)

            try:
                fresh, text, elapsed = _run_segment(
                    runner,
                    first_block=segment_first,
                    block_count=segment_count,
                    checkpoint_blocks=checkpoint_blocks,
                    on_progress=on_progress,
                    stop=stop,
                    timeout_seconds=timeout_seconds,
                )
            except _SegmentPreempted as preemption:
                merged = base_records + preemption.records
                _validate_records(merged, first)
                if preemption.records:
                    base_segments = base_segments + [
                        {
                            "first_block": segment_first,
                            "block_count": len(preemption.records),
                            "stdout_sha256": hashlib.sha256(
                                preemption.text.encode("utf-8")
                            ).hexdigest(),
                            "elapsed_seconds": round(preemption.elapsed, 6),
                            "terminated_by_preemption": True,
                        }
                    ]
                _store_checkpoint(
                    checkpoint_path, schedule, unit, merged, base_segments
                )
                raise PlattWindowedPreempted(
                    f"unit {unit} preempted with {len(merged)} of {upper - first} "
                    "blocks committed"
                ) from preemption
            records = base_records + fresh
            segments = base_segments + [
                {
                    "first_block": segment_first,
                    "block_count": len(fresh),
                    "stdout_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "elapsed_seconds": round(elapsed, 6),
                    "terminated_by_preemption": False,
                }
            ]
            if retain_log:
                log_parts.append(text)
            _validate_records(records, first)
    receipt = _build_unit_receipt(schedule, unit, records, segments)
    if retain_log and log_parts:
        _atomic_write(
            _unit_log_path(directory, schedule, unit),
            "".join(log_parts).encode("utf-8"),
        )
    committed = _commit_unit(directory, schedule, unit, receipt)
    checkpoint_path.unlink(missing_ok=True)
    release_unit(directory, unit)
    return committed


def replay_unit(
    directory: Path,
    runner: Path,
    unit: int,
    *,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Re-execute a retained unit in one segment and require digest equality."""

    schedule = load_schedule(directory)
    _runner_identity(runner, schedule)
    retained = _load_json(_unit_receipt_path(directory, schedule, unit))
    validate_unit_receipt(retained, schedule, unit)
    first, upper = unit_block_range(schedule, unit)
    with _StopRequest() as stop:
        records, _text, elapsed = _run_segment(
            runner,
            first_block=first,
            block_count=upper - first,
            checkpoint_blocks=upper - first,
            on_progress=lambda *_: None,
            stop=stop,
            timeout_seconds=timeout_seconds,
        )
    fresh = _build_unit_receipt(
        schedule,
        unit,
        records,
        [{"first_block": first, "block_count": upper - first}],
    )
    identical = fresh["unit_sha256"] == retained["unit_sha256"]
    if not identical:
        raise PlattWindowedScheduleError("fresh replay digest differs from the receipt")
    return {
        "accepted": True,
        "unit_index": unit,
        "semantic_replay_identical": True,
        "unit_sha256": retained["unit_sha256"],
        "records_sha256": retained["records_sha256"],
        "elapsed_seconds": round(elapsed, 6),
        "execution_attested": False,
        "lean_atom_discharged": False,
    }


# --------------------------------------------------------------------------
# hierarchical aggregation
# --------------------------------------------------------------------------


def _shard_semantic(shard: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in shard.items()
        if key not in ("shard_sha256", "sealed_at_unix")
    }


def seal_shard(
    directory: Path, shard_index: int, *, prune_units: bool = False
) -> dict[str, Any]:
    """Aggregate one shard's units into a single receipt with a Merkle root."""

    schedule = load_schedule(directory)
    path = _shard_receipt_path(directory, shard_index)
    first_unit, upper_unit = shard_unit_range(schedule, shard_index)
    leaves: list[str] = []
    first_count: int | None = None
    last_count: int | None = None
    total = 0
    previous_upper_block: int | None = None
    for unit in range(first_unit, upper_unit):
        receipt_path = _unit_receipt_path(directory, schedule, unit)
        if not receipt_path.exists():
            raise PlattWindowedScheduleError(f"missing unit receipt {unit}")
        receipt = _load_json(receipt_path)
        validate_unit_receipt(receipt, schedule, unit)
        if previous_upper_block is not None:
            if receipt["first_block"] != previous_upper_block:
                raise PlattWindowedScheduleError("shard unit grid has a gap")
            if receipt["first_count"] != last_count:
                raise PlattWindowedScheduleError("shard unit count chain breaks")
        previous_upper_block = receipt["upper_block_exclusive"]
        if first_count is None:
            first_count = receipt["first_count"]
        last_count = receipt["last_count"]
        total += receipt["total_zero_count"]
        leaves.append(receipt["unit_sha256"])
    if first_count is None or last_count is None:
        raise PlattWindowedScheduleError("shard contains no units")
    if last_count - first_count != total:
        raise PlattWindowedScheduleError("shard count chain does not telescope")
    first_block, _ = unit_block_range(schedule, first_unit)
    _, upper_block = unit_block_range(schedule, upper_unit - 1)
    shard: dict[str, Any] = {
        "schema": SHARD_SCHEMA,
        "schedule_sha256": schedule["schedule_sha256"],
        "shard_index": shard_index,
        "first_unit": first_unit,
        "upper_unit_exclusive": upper_unit,
        "unit_count": upper_unit - first_unit,
        "first_block": first_block,
        "upper_block_exclusive": upper_block,
        "block_count": upper_block - first_block,
        "height_lower": height_of_block(first_block),
        "height_upper": height_of_block(upper_block),
        "first_count": first_count,
        "last_count": last_count,
        "total_zero_count": total,
        "unit_merkle_root_sha256": _merkle_root(leaves),
        "runner_sha256": schedule["runner"]["sha256"],
        "reviewed_source_sha256": SOURCE_SET_SHA256,
        "units_pruned": bool(prune_units),
        "execution_attested": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    shard["shard_sha256"] = _digest(SHARD_DOMAIN, _shard_semantic(shard))
    if path.exists():
        retained = _load_json(path)
        validate_shard_receipt(retained, schedule, shard_index)
        if retained["shard_sha256"] != shard["shard_sha256"]:
            raise PlattWindowedScheduleError("re-sealing produced a different shard digest")
        return retained
    # The ordered unit digests stay next to the shard receipt so the Merkle
    # root remains independently recomputable after units are pruned.
    _atomic_write(
        _shard_directory(directory, shard_index) / UNIT_DIGEST_NAME,
        ("\n".join(leaves) + "\n").encode("ascii"),
    )
    _atomic_write(path, _canonical(shard) + b"\n")
    if prune_units:
        units_dir = _shard_directory(directory, shard_index) / "units"
        for unit in range(first_unit, upper_unit):
            (units_dir / f"unit-{unit:010d}.json").unlink(missing_ok=True)
    return shard


def validate_shard_receipt(
    shard: dict[str, Any], schedule: dict[str, Any], shard_index: int
) -> None:
    required = {
        "accepted",
        "block_count",
        "execution_attested",
        "first_block",
        "first_count",
        "first_unit",
        "height_lower",
        "height_upper",
        "last_count",
        "lean_atom_discharged",
        "reviewed_source_sha256",
        "runner_sha256",
        "schedule_sha256",
        "schema",
        "shard_index",
        "shard_sha256",
        "total_zero_count",
        "unit_count",
        "unit_merkle_root_sha256",
        "units_pruned",
        "upper_block_exclusive",
        "upper_unit_exclusive",
    }
    if set(shard) != required or shard.get("schema") != SHARD_SCHEMA:
        raise PlattWindowedScheduleError("shard receipt shape changed")
    first_unit, upper_unit = shard_unit_range(schedule, shard_index)
    first_block, _ = unit_block_range(schedule, first_unit)
    _, upper_block = unit_block_range(schedule, upper_unit - 1)
    fixed = {
        "accepted": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "schedule_sha256": schedule["schedule_sha256"],
        "shard_index": shard_index,
        "first_unit": first_unit,
        "upper_unit_exclusive": upper_unit,
        "unit_count": upper_unit - first_unit,
        "first_block": first_block,
        "upper_block_exclusive": upper_block,
        "block_count": upper_block - first_block,
        "height_lower": height_of_block(first_block),
        "height_upper": height_of_block(upper_block),
        "runner_sha256": schedule["runner"]["sha256"],
        "reviewed_source_sha256": SOURCE_SET_SHA256,
    }
    if any(shard.get(key) != value for key, value in fixed.items()):
        raise PlattWindowedScheduleError("shard receipt fixed fields differ")
    if shard["last_count"] - shard["first_count"] != shard["total_zero_count"]:
        raise PlattWindowedScheduleError("shard receipt count does not telescope")
    for key in ("unit_merkle_root_sha256", "shard_sha256"):
        if not isinstance(shard[key], str) or not _HEX64.fullmatch(shard[key]):
            raise PlattWindowedScheduleError(f"malformed shard digest: {key}")
    if shard["shard_sha256"] != _digest(SHARD_DOMAIN, _shard_semantic(shard)):
        raise PlattWindowedScheduleError("shard receipt digest differs")


def finalize(
    directory: Path,
    *,
    prefix_receipt: Path | None = None,
) -> dict[str, Any]:
    """Aggregate sealed shards into one small campaign artifact.

    Only ``shard_count`` receipts are read, so finalizing the full campaign
    touches 2,830 small files rather than 5.8 million.
    """

    schedule = load_schedule(directory)
    campaign_path = directory / CAMPAIGN_NAME
    if campaign_path.exists():
        raise PlattWindowedScheduleError("campaign artifact already exists")
    shard_count = schedule["geometry"]["shard_count"]
    leaves: list[str] = []
    first_count: int | None = None
    last_count: int | None = None
    total = 0
    previous_upper_block: int | None = None
    for shard_index in range(shard_count):
        path = _shard_receipt_path(directory, shard_index)
        if not path.exists():
            raise PlattWindowedScheduleError(f"missing sealed shard {shard_index}")
        shard = _load_json(path)
        validate_shard_receipt(shard, schedule, shard_index)
        if previous_upper_block is not None:
            if shard["first_block"] != previous_upper_block:
                raise PlattWindowedScheduleError("shard grid has a gap")
            if shard["first_count"] != last_count:
                raise PlattWindowedScheduleError("shard count chain breaks")
        previous_upper_block = shard["upper_block_exclusive"]
        if first_count is None:
            first_count = shard["first_count"]
        last_count = shard["last_count"]
        total += shard["total_zero_count"]
        leaves.append(shard["shard_sha256"])
    if first_count is None or last_count is None:
        raise PlattWindowedScheduleError("campaign contains no shards")
    if last_count - first_count != total:
        raise PlattWindowedScheduleError("campaign count chain does not telescope")
    full = schedule["mode"] == "full_source_high_range"
    if full and first_count != SOURCE_LOWER_COUNT:
        raise PlattWindowedScheduleError("campaign does not begin at N(10^10)")
    prefix = _prefix_binding(prefix_receipt)
    result: dict[str, Any] = {
        "schema": CAMPAIGN_SCHEMA,
        "schedule_sha256": schedule["schedule_sha256"],
        "mode": schedule["mode"],
        "shard_count": shard_count,
        "unit_count": schedule["geometry"]["unit_count"],
        "block_count": schedule["geometry"]["block_count"],
        "height_lower": SOURCE_LOWER,
        "height_upper": schedule["claim"]["coverage_upper"],
        "first_count": first_count,
        "last_count": last_count,
        "total_zero_count": total,
        "shard_merkle_root_sha256": _merkle_root(leaves),
        "runner_sha256": schedule["runner"]["sha256"],
        "reviewed_source_sha256": SOURCE_SET_SHA256,
        "all_high_range_zeros_on_critical_line": True,
        "source_height_covered": (
            schedule["claim"]["coverage_upper"] >= SOURCE_HEIGHT and full
        ),
        "prefix": prefix,
        "lower_prefix_required": True,
        # The prefix below 10^10 and the Hardy-Z/Turing realization are
        # separate obligations.  Nothing in this file can set them true.
        "source_claim_ready": False,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    result["campaign_sha256"] = _digest(
        CAMPAIGN_DOMAIN, {k: v for k, v in result.items()}
    )
    _atomic_write(campaign_path, _canonical(result) + b"\n")
    return result


def _prefix_binding(prefix_receipt: Path | None) -> dict[str, Any]:
    if prefix_receipt is None:
        return {
            "bound": False,
            "kind": None,
            "receipt_sha256": None,
            "boundary_count": SOURCE_LOWER_COUNT,
            "boundary_height": SOURCE_LOWER,
            "independently_replayed": False,
        }
    digest, _size = _sha256_file(prefix_receipt)
    value = _load_json(prefix_receipt)
    claimed = value.get("boundary_multiplicity_count")
    if claimed is not None and claimed != SOURCE_LOWER_COUNT:
        raise PlattWindowedScheduleError(
            "prefix receipt boundary count differs from N(10^10)"
        )
    return {
        "bound": True,
        "kind": value.get("kind"),
        "receipt_sha256": digest,
        "boundary_count": SOURCE_LOWER_COUNT,
        "boundary_height": SOURCE_LOWER,
        "independently_replayed": bool(
            value.get("source_turing_completeness_independently_replayed", False)
        ),
    }


def status(directory: Path, *, sample_shards: int | None = None) -> dict[str, Any]:
    """Cheap progress report.

    Sealed shards are counted by their receipt alone.  Unsealed shards are
    listed, which is bounded by ``units_per_shard`` entries each.  Passing
    ``sample_shards`` bounds even that for an operator poll on a very large
    campaign.
    """

    schedule = load_schedule(directory)
    shard_count = schedule["geometry"]["shard_count"]
    sealed = 0
    scanned = 0
    units_done = 0
    first_open: int | None = None
    for shard_index in range(shard_count):
        if _shard_receipt_path(directory, shard_index).exists():
            sealed += 1
            first_unit, upper_unit = shard_unit_range(schedule, shard_index)
            units_done += upper_unit - first_unit
            continue
        if first_open is None:
            first_open = shard_index
        if sample_shards is not None and scanned >= sample_shards:
            continue
        scanned += 1
        units_dir = _shard_directory(directory, shard_index) / "units"
        try:
            units_done += sum(1 for _ in os.scandir(units_dir))
        except FileNotFoundError:
            pass
    return {
        "accepted": True,
        "mode": schedule["mode"],
        "unit_count": schedule["geometry"]["unit_count"],
        "shard_count": shard_count,
        "sealed_shards": sealed,
        "units_committed_observed": units_done,
        "first_unsealed_shard": first_open,
        "complete": sealed == shard_count,
        "finalized": (directory / CAMPAIGN_NAME).exists(),
        "lower_prefix_required": True,
        "source_claim_ready": False,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }


__all__ = [
    "CAMPAIGN_SCHEMA",
    "DEFAULT_BLOCKS_PER_UNIT",
    "DEFAULT_CHECKPOINT_BLOCKS",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_UNITS_PER_SHARD",
    "SCHEDULE_SCHEMA",
    "SHARD_SCHEMA",
    "UNIT_SCHEMA",
    "PlattWindowedPreempted",
    "PlattWindowedScheduleError",
    "claim_unit",
    "create_schedule",
    "default_worker_id",
    "finalize",
    "height_of_block",
    "initialize_schedule",
    "load_schedule",
    "next_unit",
    "release_unit",
    "replay_unit",
    "run_unit",
    "seal_shard",
    "shard_of_unit",
    "shard_unit_range",
    "status",
    "unit_block_range",
    "unit_semantic_digest",
    "validate_schedule",
    "validate_shard_receipt",
    "validate_unit_receipt",
]
