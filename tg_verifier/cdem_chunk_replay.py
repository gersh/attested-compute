"""Independent bounded-memory replay of CDEM Abel transcript chunks.

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

The supervisor pins and compiles a separate reviewed C++ implementation, then
checks its exact output against selected rows (or every row) of a production
transcript.  This is strong external evidence, but it is not a Lean-kernel
proof: the reviewed source, compiler/runtime execution, and the theorem that
connects the finite recurrence to the Lean analytic definitions remain in the
trust boundary.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from time import perf_counter_ns
from typing import Any, Iterable, NoReturn

from .evidence import (
    EvidenceError,
    parse_key_value_transcript,
    read_artifact_bytes,
    sha256_file,
    verify_cdem_abel_text,
)


class CdemChunkReplayError(RuntimeError):
    """The independent chunk replay was unavailable or failed closed."""


def _fail(message: str) -> NoReturn:
    raise CdemChunkReplayError(message)


CDEM_CHUNK_REPLAYER_SOURCE_SHA256 = (
    "00a9ef86c9fef26690b14f63af3c92f7ad9141cc3d7020d69fe4d631e7b56ad1"
)
CDEM_CHUNK_REPLAYER_DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "reference"
    / "tg_cdem_abel_chunk_replay.cpp"
)
CDEM_PRODUCTION_K = 199_330
CDEM_PRODUCTION_N = 5_000_000_000
WEIGHT_SCALE = 10**18

_UNSIGNED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SIGNED_DECIMAL = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
_OUTPUT_NAMES = {
    "SCHEMA",
    "K",
    "LOW",
    "HIGH",
    "BEFORE",
    "DELTA_SUM",
    "AFTER",
    "U_INC_UPPER_NUM",
    "V_INC_UPPER_NUM",
    "TOTAL_VARIATION",
    "WEIGHT_SCALE",
}


@dataclass(frozen=True)
class CdemChunkRecord:
    """One composable production-transcript row."""

    low: int
    high: int
    before: int
    after: int
    u_increment_upper: int
    v_increment_upper: int
    variation: int

    def canonical_csv(self) -> str:
        return ",".join(
            str(value)
            for value in (
                self.low,
                self.high,
                self.before,
                self.after,
                self.u_increment_upper,
                self.v_increment_upper,
                self.variation,
            )
        )


def _canonical_integer(text: str, *, signed: bool, label: str) -> int:
    pattern = _SIGNED_DECIMAL if signed else _UNSIGNED_DECIMAL
    if pattern.fullmatch(text) is None:
        _fail(f"{label} is not a canonical decimal integer")
    return int(text)


def _validated_record(record: CdemChunkRecord, *, label: str) -> None:
    if not isinstance(record, CdemChunkRecord):
        _fail(f"{label} is not a CdemChunkRecord")
    integer_values = (
        record.low,
        record.high,
        record.before,
        record.after,
        record.u_increment_upper,
        record.v_increment_upper,
        record.variation,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in integer_values):
        _fail(f"{label} contains a non-integer field")
    if record.low < 1 or record.high < record.low:
        _fail(f"{label} has an invalid interval")
    if record.high > (1 << 64) - 1:
        _fail(f"{label} endpoint exceeds uint64")
    if not -(1 << 63) <= record.before < (1 << 63):
        _fail(f"{label} incoming F state exceeds int64")
    if record.v_increment_upper < 0 or record.variation < 0:
        _fail(f"{label} has a negative unsigned aggregate")


def parse_cdem_production_chunks(text: str) -> tuple[CdemChunkRecord, ...]:
    """Fail closed unless ``text`` is the exact complete production shape."""

    try:
        checked = verify_cdem_abel_text(text, require_chunks=True)
        fields = parse_key_value_transcript(text)
    except EvidenceError as error:
        raise CdemChunkReplayError(
            f"production CDEM transcript failed its exact contract: {error}"
        ) from error
    try:
        chunk_count = _canonical_integer(
            fields["CHUNK_COUNT"], signed=False, label="CHUNK_COUNT"
        )
        block_size = _canonical_integer(
            fields["BLOCK_SIZE"], signed=False, label="BLOCK_SIZE"
        )
    except KeyError as error:
        raise CdemChunkReplayError(
            f"production transcript omitted {error.args[0]}"
        ) from error
    if chunk_count != checked.metrics.get("chunk_count") or chunk_count != 1_000:
        _fail("production transcript does not have exactly 1,000 checked chunks")
    if block_size != 5_000_000:
        _fail("production transcript does not use the reviewed 5,000,000 block size")

    records: list[CdemChunkRecord] = []
    for index in range(chunk_count):
        key = f"CHUNK_{index}"
        try:
            pieces = fields[key].split(",")
        except KeyError as error:
            raise CdemChunkReplayError(f"production transcript omitted {key}") from error
        if len(pieces) != 7:
            _fail(f"{key} does not have seven comma-separated fields")
        values = (
            _canonical_integer(pieces[0], signed=False, label=f"{key}.low"),
            _canonical_integer(pieces[1], signed=False, label=f"{key}.high"),
            _canonical_integer(pieces[2], signed=True, label=f"{key}.before"),
            _canonical_integer(pieces[3], signed=True, label=f"{key}.after"),
            _canonical_integer(pieces[4], signed=True, label=f"{key}.u"),
            _canonical_integer(pieces[5], signed=False, label=f"{key}.v"),
            _canonical_integer(pieces[6], signed=False, label=f"{key}.variation"),
        )
        record = CdemChunkRecord(*values)
        _validated_record(record, label=key)
        records.append(record)
    return tuple(records)


def _expected_output(K: int, record: CdemChunkRecord) -> dict[str, str]:
    return {
        "SCHEMA": "CDEM_ABEL_CHUNK_REPLAY_V1",
        "K": str(K),
        "LOW": str(record.low),
        "HIGH": str(record.high),
        "BEFORE": str(record.before),
        "DELTA_SUM": str(record.after - record.before),
        "AFTER": str(record.after),
        "U_INC_UPPER_NUM": str(record.u_increment_upper),
        "V_INC_UPPER_NUM": str(record.v_increment_upper),
        "TOTAL_VARIATION": str(record.variation),
        "WEIGHT_SCALE": str(WEIGHT_SCALE),
    }


def verify_cdem_chunk_output(
    text: str, *, K: int, expected: CdemChunkRecord
) -> str:
    """Check exact keys, canonical encoding, and all expected chunk values.

    Returns a SHA-256 digest of the canonical output bytes.
    """

    _validated_record(expected, label="expected chunk")
    try:
        fields = parse_key_value_transcript(text)
    except EvidenceError as error:
        raise CdemChunkReplayError(f"malformed chunk-replayer output: {error}") from error
    if set(fields) != _OUTPUT_NAMES:
        missing = sorted(_OUTPUT_NAMES - set(fields))
        extra = sorted(set(fields) - _OUTPUT_NAMES)
        _fail(f"chunk-replayer output keys differ (missing={missing}, extra={extra})")
    wanted = _expected_output(K, expected)
    for name, value in wanted.items():
        if fields[name] != value:
            _fail(
                f"chunk-replayer field {name} differs: expected {value}, "
                f"got {fields[name]}"
            )
    canonical = "".join(f"{name}={value}\n" for name, value in wanted.items())
    if text != canonical:
        _fail("chunk-replayer output is not in canonical field order/encoding")
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _positive_integer(name: str, value: int, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        _fail(f"{name} must be an integer in [1, {maximum}]")
    return value


def _compiler_identity(compiler: str | Path) -> tuple[Path, str, str]:
    compiler_text = str(compiler)
    found = shutil.which(compiler_text)
    compiler_path = Path(found).resolve() if found is not None else Path(compiler_text).resolve()
    if not compiler_path.is_file() or not os.access(compiler_path, os.X_OK):
        _fail(f"C++ compiler is missing or not executable: {compiler_path}")
    try:
        version = subprocess.run(
            [str(compiler_path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CdemChunkReplayError("could not execute the selected C++ compiler") from error
    if version.returncode != 0 or version.stderr or not version.stdout.splitlines():
        _fail("could not identify the selected C++ compiler without diagnostics")
    return compiler_path, sha256_file(compiler_path), version.stdout.splitlines()[0]


def _compile_replayer(
    source: Path, compiler: Path, executable: Path, *, max_seconds: int
) -> tuple[str, int]:
    started = perf_counter_ns()
    try:
        completed = subprocess.run(
            [
                str(compiler),
                "-O3",
                "-std=c++20",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(source),
                "-o",
                str(executable),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CdemChunkReplayError("chunk-replayer compilation failed to complete") from error
    elapsed_ms = (perf_counter_ns() - started) // 1_000_000
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic"
        _fail(f"chunk-replayer compilation exited {completed.returncode}: {diagnostic}")
    if completed.stdout or completed.stderr:
        _fail("chunk-replayer compilation unexpectedly emitted diagnostics")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        _fail("chunk-replayer compilation did not produce an executable")
    return sha256_file(executable), elapsed_ms


def _invoke_one(
    executable: Path,
    *,
    K: int,
    record: CdemChunkRecord,
    max_seconds: int,
) -> tuple[str, int]:
    started = perf_counter_ns()
    try:
        completed = subprocess.run(
            [
                str(executable),
                str(K),
                str(record.low),
                str(record.high),
                str(record.before),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise CdemChunkReplayError(
            f"chunk [{record.low}, {record.high}] exceeded {max_seconds} seconds"
        ) from error
    except OSError as error:
        raise CdemChunkReplayError(
            f"could not execute chunk [{record.low}, {record.high}]"
        ) from error
    elapsed_ms = (perf_counter_ns() - started) // 1_000_000
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or "no stderr diagnostic"
        _fail(
            f"chunk [{record.low}, {record.high}] exited "
            f"{completed.returncode}: {diagnostic}"
        )
    if completed.stderr:
        _fail(f"chunk [{record.low}, {record.high}] unexpectedly wrote to stderr")
    digest = verify_cdem_chunk_output(completed.stdout, K=K, expected=record)
    return digest, elapsed_ms


_PREFLIGHT_RECORDS = (
    CdemChunkRecord(1, 7, 0, 1, 0, 0, 0),
    CdemChunkRecord(
        8,
        14,
        1,
        2,
        96_403_596_403_596_406,
        846_122_684_602_802_570,
        3,
    ),
)


def build_and_replay_cdem_chunk_records(
    records: Iterable[CdemChunkRecord],
    *,
    K: int,
    source: str | Path = CDEM_CHUNK_REPLAYER_DEFAULT_SOURCE,
    compiler: str | Path = "g++",
    workers: int = 8,
    compile_max_seconds: int = 120,
    chunk_max_seconds: int = 120,
) -> dict[str, Any]:
    """Compile the pinned source and independently replay supplied records."""

    K = _positive_integer("K", K, maximum=(1 << 31) - 1)
    workers = _positive_integer("workers", workers, maximum=64)
    compile_max_seconds = _positive_integer(
        "compile_max_seconds", compile_max_seconds, maximum=3_600
    )
    chunk_max_seconds = _positive_integer(
        "chunk_max_seconds", chunk_max_seconds, maximum=86_400
    )
    record_tuple = tuple(records)
    if not record_tuple:
        _fail("at least one chunk record is required")
    for index, record in enumerate(record_tuple):
        _validated_record(record, label=f"record {index}")

    source_path = Path(source).resolve()
    if not source_path.is_file():
        _fail(f"chunk-replayer source is missing: {source_path}")
    source_bytes = read_artifact_bytes(source_path)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source_hash != CDEM_CHUNK_REPLAYER_SOURCE_SHA256:
        _fail(
            "chunk-replayer source differs from the reviewed SHA-256: "
            f"expected {CDEM_CHUNK_REPLAYER_SOURCE_SHA256}, got {source_hash}"
        )
    compiler_path, compiler_hash, compiler_version = _compiler_identity(compiler)

    with tempfile.TemporaryDirectory(prefix="sparkinterval-cdem-chunk-") as directory:
        source_copy = Path(directory) / source_path.name
        source_copy.write_bytes(source_bytes)
        executable = Path(directory) / "tg_cdem_abel_chunk_replay"
        executable_hash, compile_ms = _compile_replayer(
            source_copy,
            compiler_path,
            executable,
            max_seconds=compile_max_seconds,
        )

        # Fixed known-answer rows exercise both the Gseq(0) override and an
        # ordinary incoming-prefix transition before any requested evidence.
        for preflight in _PREFLIGHT_RECORDS:
            _invoke_one(executable, K=10, record=preflight, max_seconds=30)

        actual_workers = min(workers, len(record_tuple))
        results: dict[int, tuple[str, int]] = {}
        futures: dict[Future[tuple[str, int]], int] = {}
        with ThreadPoolExecutor(max_workers=actual_workers) as pool:
            for index, record in enumerate(record_tuple):
                future = pool.submit(
                    _invoke_one,
                    executable,
                    K=K,
                    record=record,
                    max_seconds=chunk_max_seconds,
                )
                futures[future] = index
            try:
                for future in as_completed(futures):
                    results[futures[future]] = future.result()
            except BaseException:
                for future in futures:
                    future.cancel()
                raise

        if sha256_file(executable) != executable_hash:
            _fail("compiled chunk replayer changed during execution")

    if sha256_file(source_path) != source_hash:
        _fail("chunk-replayer source changed during execution")
    if sha256_file(compiler_path) != compiler_hash:
        _fail("selected C++ compiler changed during execution")

    ordered_digests = [results[index][0] for index in range(len(record_tuple))]
    elapsed = [results[index][1] for index in range(len(record_tuple))]
    output_manifest = "".join(f"{index}:{digest}\n" for index, digest in enumerate(ordered_digests))
    record_manifest = "".join(
        f"{index}:{record.canonical_csv()}\n"
        for index, record in enumerate(record_tuple)
    )
    maximum_span = max(record.high - record.low + 1 for record in record_tuple)
    return {
        "schema_version": 1,
        "accepted": True,
        "atom_id": "cdem-table-abel",
        "verification_class": "external_selected_independent_chunk_replay",
        "reviewed_source": str(source_path),
        "reviewed_source_sha256": source_hash,
        "reviewed_source_hash_matched": True,
        "compiled_source_was_exact_captured_bytes": True,
        "source_compiled_by_supervisor": True,
        "compiler": str(compiler_path),
        "compiler_sha256": compiler_hash,
        "compiler_version": compiler_version,
        "compiled_executable_sha256": executable_hash,
        "temporary_executable_retained": False,
        "compile_elapsed_milliseconds": compile_ms,
        "fixed_known_answer_preflight": True,
        "K": K,
        "replayed_chunk_count": len(record_tuple),
        "worker_limit": workers,
        "actual_workers": actual_workers,
        "maximum_chunk_span": maximum_span,
        "principal_delta_bytes_per_worker_upper": 4 * maximum_span,
        "principal_concurrent_delta_bytes_upper": 4 * maximum_span * actual_workers,
        "record_manifest_sha256": hashlib.sha256(record_manifest.encode("ascii")).hexdigest(),
        "output_manifest_sha256": hashlib.sha256(output_manifest.encode("ascii")).hexdigest(),
        "elapsed_milliseconds_sum": sum(elapsed),
        "elapsed_milliseconds_min": min(elapsed),
        "elapsed_milliseconds_max": max(elapsed),
        "all_supplied_chunks_recomputed": True,
        "complete_range_execution_verified": False,
        "ordinary_kernel_lean_proof": False,
        "lean_atom_discharged": False,
        "remaining_trust_boundary": (
            "reviewed independent C++ source, identified compiler/runtime execution, "
            "and the missing Lean realization of the finite recurrence"
        ),
    }


def replay_cdem_production_transcript(
    transcript: str | Path,
    *,
    indices: Iterable[int] | None = None,
    source: str | Path = CDEM_CHUNK_REPLAYER_DEFAULT_SOURCE,
    compiler: str | Path = "g++",
    workers: int = 8,
    compile_max_seconds: int = 120,
    chunk_max_seconds: int = 120,
) -> dict[str, Any]:
    """Replay selected chunks or all 1,000 rows of a checked transcript.

    Passing ``indices=None`` replays the complete range.  Any explicit index
    collection is sorted and must be nonempty, duplicate-free, and in range.
    """

    if isinstance(transcript, Path):
        try:
            text = transcript.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise CdemChunkReplayError(
                f"cannot read production transcript {transcript}: {error}"
            ) from error
        transcript_path: str | None = str(transcript.resolve())
    elif isinstance(transcript, str):
        text = transcript
        transcript_path = None
    else:
        _fail("transcript must be UTF-8 text or a pathlib.Path")

    records = parse_cdem_production_chunks(text)
    if indices is None:
        selected_indices = tuple(range(len(records)))
    else:
        selected_list = list(indices)
        if not selected_list:
            _fail("an explicit chunk-index collection must be nonempty")
        if any(isinstance(index, bool) or not isinstance(index, int) for index in selected_list):
            _fail("chunk indices must be integers")
        if len(set(selected_list)) != len(selected_list):
            _fail("chunk indices must not contain duplicates")
        if any(index < 0 or index >= len(records) for index in selected_list):
            _fail("chunk index is outside [0, 999]")
        selected_indices = tuple(sorted(selected_list))

    selected = tuple(records[index] for index in selected_indices)
    receipt = build_and_replay_cdem_chunk_records(
        selected,
        K=CDEM_PRODUCTION_K,
        source=source,
        compiler=compiler,
        workers=workers,
        compile_max_seconds=compile_max_seconds,
        chunk_max_seconds=chunk_max_seconds,
    )
    full = selected_indices == tuple(range(len(records)))
    index_manifest = "".join(f"{index}\n" for index in selected_indices).encode("ascii")
    receipt.update(
        {
            "verification_class": (
                "complete_external_independent_bounded_memory_chunk_replay"
                if full
                else "external_selected_independent_bounded_memory_chunk_replay"
            ),
            "transcript": transcript_path,
            "transcript_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "production_chunk_manifest_sha256": parse_key_value_transcript(text)[
                "CHUNK_MANIFEST_SHA256"
            ],
            "selected_index_manifest_sha256": hashlib.sha256(index_manifest).hexdigest(),
            "first_selected_index": selected_indices[0],
            "last_selected_index": selected_indices[-1],
            "all_production_chunks_selected": full,
            "complete_range_execution_verified": full,
        }
    )
    return receipt


def receipt_json(receipt: dict[str, Any], *, pretty: bool = False) -> str:
    """Serialize a replay receipt canonically (or in human-readable form)."""

    return json.dumps(
        receipt,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
