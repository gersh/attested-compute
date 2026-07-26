# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded persistent-process witness for the finite PT21 block pipeline.

The CUDA/FLINT junction and directed-Arb producer expose fixed-width request
frames in their persistent modes.  This module keeps both measured
executables alive, feeds a bounded number of block-zero requests, runs the
existing exact-rational/native adapter, and finalizes one retained bounded
shard.  Every retained output is required to be byte-identical to the
ordinary one-shot chain.

The repeated block-zero fixture is intentionally synthetic.  Repetition is
useful for measuring startup and IPC costs, but it is not a gap-free source
campaign and is never presented to the native finalizer as multiple blocks.
All analytic, source-realization, production, and attestation flags remain
false.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import select
import stat
import struct
import subprocess
import tempfile
import time
from typing import BinaryIO

from tg_verifier.platt_pt21_bounded_block_chain import (
    BLOCK,
    MAIN_SLOTS,
    MAXIMUM_FINALIZER_STDOUT,
    PLAN_DOMAIN,
    PREFIX_DOMAIN,
    PT21BoundedBlockChainError,
    SHARD_SUMMARY_SCHEMA,
    STATIONARY_CANDIDATES,
    _adapter_source_identity,
    _bound_block_record,
    _canonical,
    _chain_commitment,
    _regular_identity,
    _require_flint_loader_alias,
    _run,
    _strict_json,
    _validate_multiplicity,
    run_bounded_block_chain,
    synthetic_candidates,
    synthetic_samples,
    verify_retained_chain,
)
from tg_verifier.platt_pt21_native_finalizer import (
    PT21NativeFinalizerError,
    replay_shard,
)
from tg_verifier.platt_pt21_native_record_adapter import (
    PT21NativeRecordAdapterError,
    adapt_block,
    worker_identity,
    write_exclusive,
)
from tg_verifier.platt_pt21_stationary_junction import (
    PT21StationaryJunctionError,
    replay as replay_junction,
)
from tg_verifier.platt_pt21_turing_inputs import (
    MAX_BYTES as TURING_MAXIMUM_BYTES,
    PT21TuringInputsError,
    validate as validate_turing_inputs,
)
from tg_verifier.platt_required_sign_packet import (
    load_required_sign_packet,
)
from tg_verifier.platt_stationary_trace import (
    MAXIMUM_BYTES as STATIONARY_MAXIMUM_BYTES,
    PT21StationaryTraceError,
    validate as validate_stationary_trace,
)


SCHEMA = "sparkinterval.tg.platt-pt21-persistent-worker-benchmark.v1"
MAXIMUM_REQUESTS = 16
PROCESS_TIMEOUT_SECONDS = 30.0
MAXIMUM_PROCESS_STDERR = 64 * 1024

JUNCTION_REQUEST = struct.Struct("<8sIIQ")
JUNCTION_REQUEST_MAGIC = b"PT21JRQ1"
JUNCTION_RESPONSE = struct.Struct("<8sIIQIIII")
JUNCTION_RESPONSE_MAGIC = b"PT21JRS1"
JUNCTION_EVENT_BYTES = 192
JUNCTION_RECORD_BYTES = 400
JUNCTION_MAXIMUM_FRAME = (
    JUNCTION_RESPONSE.size
    + JUNCTION_EVENT_BYTES
    + JUNCTION_RECORD_BYTES
    + STATIONARY_MAXIMUM_BYTES
)

TURING_REQUEST = struct.Struct("<8sIIQ32s")
TURING_REQUEST_MAGIC = b"PT21TRQ1"
TURING_RESPONSE = struct.Struct("<8sII")
TURING_RESPONSE_MAGIC = b"PT21TRS1"
VERSION = 1


class PT21PersistentWorkerError(RuntimeError):
    """A persistent frame, process, byte comparison, or replay failed."""


@dataclass(frozen=True)
class JunctionResponse:
    event_record: bytes
    junction_record: bytes
    stationary_trace: bytes


@dataclass(frozen=True)
class PersistentBatch:
    report: dict[str, object]
    event_record: bytes
    stationary_junction_record: bytes
    turing_inputs: bytes
    source_trace: bytes
    block_artifact: bytes
    block_record: bytes
    shard_archive: bytes


def junction_request(block: int) -> bytes:
    if isinstance(block, bool) or not 0 <= block < 2_966_443_783:
        raise PT21PersistentWorkerError(
            "junction request block leaves the PT21 campaign"
        )
    return JUNCTION_REQUEST.pack(
        JUNCTION_REQUEST_MAGIC, VERSION, JUNCTION_REQUEST.size, block
    )


def turing_request(block: int, packet_sha256: str) -> bytes:
    if isinstance(block, bool) or not 0 <= block < 2_966_443_783:
        raise PT21PersistentWorkerError(
            "Turing request block leaves the PT21 campaign"
        )
    if (
        not isinstance(packet_sha256, str)
        or len(packet_sha256) != 64
        or any(character not in "0123456789abcdef" for character in packet_sha256)
    ):
        raise PT21PersistentWorkerError(
            "Turing request packet identity is not lowercase SHA-256"
        )
    return TURING_REQUEST.pack(
        TURING_REQUEST_MAGIC,
        VERSION,
        TURING_REQUEST.size,
        block,
        bytes.fromhex(packet_sha256),
    )


def _read_exact(
    stream: BinaryIO,
    size: int,
    *,
    deadline: float,
    label: str,
) -> bytes:
    result = bytearray()
    descriptor = stream.fileno()
    while len(result) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PT21PersistentWorkerError(f"{label} timed out")
        readable, _, _ = select.select([descriptor], [], [], remaining)
        if not readable:
            raise PT21PersistentWorkerError(f"{label} timed out")
        chunk = os.read(descriptor, size - len(result))
        if not chunk:
            raise PT21PersistentWorkerError(f"{label} is truncated")
        result.extend(chunk)
    return bytes(result)


def _write_all(stream: BinaryIO, raw: bytes, *, label: str) -> None:
    descriptor = stream.fileno()
    position = 0
    while position < len(raw):
        try:
            wrote = os.write(descriptor, raw[position:])
        except OSError as error:
            raise PT21PersistentWorkerError(
                f"cannot write {label}: {error}"
            ) from error
        if wrote <= 0:
            raise PT21PersistentWorkerError(f"cannot write {label}")
        position += wrote


def _decode_junction_response(
    stream: BinaryIO, *, expected_block: int
) -> JunctionResponse:
    deadline = time.monotonic() + PROCESS_TIMEOUT_SECONDS
    header = _read_exact(
        stream,
        JUNCTION_RESPONSE.size,
        deadline=deadline,
        label="persistent junction response header",
    )
    (
        magic,
        version,
        frame_bytes,
        block,
        event_bytes,
        junction_bytes,
        trace_bytes,
        failure_flags,
    ) = JUNCTION_RESPONSE.unpack(header)
    if (
        magic != JUNCTION_RESPONSE_MAGIC
        or version != VERSION
        or block != expected_block
        or event_bytes != JUNCTION_EVENT_BYTES
        or junction_bytes != JUNCTION_RECORD_BYTES
        or not 0 < trace_bytes <= STATIONARY_MAXIMUM_BYTES
        or failure_flags != 0
        or frame_bytes
        != JUNCTION_RESPONSE.size
        + event_bytes
        + junction_bytes
        + trace_bytes
        or frame_bytes > JUNCTION_MAXIMUM_FRAME
    ):
        raise PT21PersistentWorkerError(
            "persistent junction response fields differ"
        )
    body = _read_exact(
        stream,
        frame_bytes - JUNCTION_RESPONSE.size,
        deadline=deadline,
        label="persistent junction response payload",
    )
    event_end = event_bytes
    junction_end = event_end + junction_bytes
    return JunctionResponse(
        event_record=body[:event_end],
        junction_record=body[event_end:junction_end],
        stationary_trace=body[junction_end:],
    )


def _decode_turing_response(stream: BinaryIO) -> bytes:
    deadline = time.monotonic() + PROCESS_TIMEOUT_SECONDS
    header = _read_exact(
        stream,
        TURING_RESPONSE.size,
        deadline=deadline,
        label="persistent Turing response header",
    )
    magic, version, frame_bytes = TURING_RESPONSE.unpack(header)
    if (
        magic != TURING_RESPONSE_MAGIC
        or version != VERSION
        or frame_bytes <= TURING_RESPONSE.size
        or frame_bytes > TURING_RESPONSE.size + TURING_MAXIMUM_BYTES
    ):
        raise PT21PersistentWorkerError(
            "persistent Turing response fields differ"
        )
    return _read_exact(
        stream,
        frame_bytes - TURING_RESPONSE.size,
        deadline=deadline,
        label="persistent Turing response artifact",
    )


class _PinnedProcess:
    def __init__(
        self,
        *,
        executable: Path,
        expected_sha256: str,
        arguments: list[str],
        environment: dict[str, str],
        label: str,
    ) -> None:
        self.label = label
        self.stderr = tempfile.TemporaryFile()
        descriptor = -1
        try:
            descriptor = os.open(
                executable,
                os.O_RDONLY
                | os.O_CLOEXEC
                | getattr(os, "O_NOFOLLOW", 0),
            )
            metadata = os.fstat(descriptor)
            digest = hashlib.sha256()
            consumed = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                consumed += len(chunk)
            final = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size < 1
                or metadata.st_mode & 0o111 == 0
                or consumed != metadata.st_size
                or final.st_size != metadata.st_size
                or digest.hexdigest() != expected_sha256
            ):
                raise PT21PersistentWorkerError(
                    f"{label} differs from its selected executable identity"
                )
            os.lseek(descriptor, 0, os.SEEK_SET)
            pinned = f"/proc/self/fd/{descriptor}"
            self.process = subprocess.Popen(
                [pinned, *arguments],
                executable=pinned,
                pass_fds=(descriptor,),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                env=environment,
                bufsize=0,
            )
        except PT21PersistentWorkerError:
            self.stderr.close()
            raise
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.stderr.close()
            raise PT21PersistentWorkerError(
                f"cannot start pinned {label}: {error}"
            ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if self.process.stdin is None or self.process.stdout is None:
            self.abort()
            raise PT21PersistentWorkerError(
                f"{label} did not expose both persistent pipes"
            )

    @property
    def input(self) -> BinaryIO:
        assert self.process.stdin is not None
        return self.process.stdin

    @property
    def output(self) -> BinaryIO:
        assert self.process.stdout is not None
        return self.process.stdout

    def finish(self) -> None:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            returncode = self.process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            self.abort()
            raise PT21PersistentWorkerError(
                f"{self.label} did not terminate after its bounded request count"
            ) from error
        if self.process.stdout is not None:
            trailing = self.process.stdout.read(1)
            self.process.stdout.close()
        else:
            trailing = b""
        self.stderr.seek(0)
        diagnostic = self.stderr.read(MAXIMUM_PROCESS_STDERR + 1)
        self.stderr.close()
        if (
            returncode != 0
            or trailing
            or diagnostic
            or len(diagnostic) > MAXIMUM_PROCESS_STDERR
        ):
            message = diagnostic.decode(errors="replace").strip()
            raise PT21PersistentWorkerError(
                f"{self.label} failed closed"
                + (f": {message}" if message else "")
            )

    def abort(self) -> None:
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None:
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()
        stderr = getattr(self, "stderr", None)
        if stderr is not None and not stderr.closed:
            stderr.close()


def _positive_finite(values: list[float], label: str) -> None:
    if not values or any(not math.isfinite(value) or value <= 0 for value in values):
        raise PT21PersistentWorkerError(
            f"{label} does not contain only positive finite measurements"
        )


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def run_persistent_bounded_batch(
    *,
    junction_executable: Path,
    turing_executable: Path,
    flint_library: Path,
    finalizer_executable: Path,
    output_directory: Path,
    request_count: int,
) -> PersistentBatch:
    """Run a bounded persistent batch and compare it with one-shot bytes."""

    if (
        isinstance(request_count, bool)
        or not 1 <= request_count <= MAXIMUM_REQUESTS
    ):
        raise PT21PersistentWorkerError(
            f"request count is outside 1..{MAXIMUM_REQUESTS}"
        )
    if output_directory.exists():
        if (
            output_directory.is_symlink()
            or not output_directory.is_dir()
            or any(output_directory.iterdir())
        ):
            raise PT21PersistentWorkerError(
                "output directory must be an existing empty directory"
            )
    else:
        output_directory.mkdir(parents=True)
    reference_directory = output_directory / "one-shot-reference"
    persistent_directory = output_directory / "persistent"
    persistent_directory.mkdir()

    reference_started = time.monotonic()
    try:
        reference = run_bounded_block_chain(
            junction_executable=junction_executable,
            turing_executable=turing_executable,
            flint_library=flint_library,
            finalizer_executable=finalizer_executable,
            output_directory=reference_directory,
        )
    except PT21BoundedBlockChainError as error:
        raise PT21PersistentWorkerError(
            f"one-shot reference chain failed: {error}"
        ) from error
    reference_seconds = time.monotonic() - reference_started

    try:
        junction_identity = worker_identity(junction_executable)
        turing_identity = worker_identity(turing_executable)
        finalizer_identity = worker_identity(finalizer_executable)
    except PT21NativeRecordAdapterError as error:
        raise PT21PersistentWorkerError(
            f"persistent executable identity failed: {error}"
        ) from error
    flint_sha256, flint_size = _regular_identity(
        flint_library, "persistent FLINT shared library"
    )
    _require_flint_loader_alias(flint_library)
    environment = dict(os.environ)
    inherited_library_path = environment.get("LD_LIBRARY_PATH")
    environment["LD_LIBRARY_PATH"] = str(flint_library.parent) + (
        ":" + inherited_library_path if inherited_library_path else ""
    )

    required_path = persistent_directory / "synthetic-required-sign-packet.bin"
    write_exclusive(required_path, reference.required_packet)
    packet = load_required_sign_packet(required_path)
    if packet.sha256 != hashlib.sha256(reference.required_packet).hexdigest():
        raise PT21PersistentWorkerError(
            "persistent packet differs from the one-shot reference"
        )
    # Resolve the Python-side implementation identity before either native
    # process is started.  Failure here must not strand a worker waiting for
    # framed input on an inherited pipe.
    adapter_sha256 = _adapter_source_identity()

    junction = _PinnedProcess(
        executable=junction_executable,
        expected_sha256=junction_identity.sha256,
        arguments=[
            "--mode",
            "valid",
            "--fixture",
            "turing-closure",
            "--persistent-requests",
            str(request_count),
            "--resolver-sha256",
            junction_identity.sha256,
            "--flint-sha256",
            flint_sha256,
        ],
        environment=environment,
        label="persistent CUDA/FLINT junction",
    )
    try:
        turing = _PinnedProcess(
            executable=turing_executable,
            expected_sha256=turing_identity.sha256,
            arguments=["--persistent-requests", str(request_count)],
            environment=environment,
            label="persistent directed-Arb producer",
        )
    except Exception:
        # Do not leave a GPU process blocked on stdin if the second worker
        # cannot be started or its selected identity fails validation.
        junction.abort()
        raise

    junction_seconds: list[float] = []
    turing_seconds: list[float] = []
    adapter_seconds: list[float] = []
    accepted_bytes: (
        tuple[bytes, bytes, bytes, bytes, bytes, bytes, bytes] | None
    ) = None
    overall_started = time.monotonic()
    try:
        for request_index in range(request_count):
            started = time.monotonic()
            _write_all(
                junction.input,
                junction_request(BLOCK),
                label="persistent junction request",
            )
            response = _decode_junction_response(
                junction.output, expected_block=BLOCK
            )
            junction_seconds.append(time.monotonic() - started)

            stationary_value = _strict_json(
                response.stationary_trace,
                maximum=STATIONARY_MAXIMUM_BYTES,
                label="persistent stationary trace",
            )
            if response.stationary_trace != _canonical(stationary_value) + b"\n":
                raise PT21PersistentWorkerError(
                    "persistent stationary trace is not canonical"
                )
            try:
                stationary = validate_stationary_trace(stationary_value)
                samples, _signs = synthetic_samples()
                replay_junction(
                    response.junction_record,
                    event_record=response.event_record,
                    sample_payload=samples,
                    candidates=synthetic_candidates(),
                    refinements=[],
                    stationary_trace=stationary,
                    expected_resolver_sha256=junction_identity.sha256,
                    expected_flint_sha256=flint_sha256,
                )
            except (
                PT21StationaryTraceError,
                PT21StationaryJunctionError,
            ) as error:
                raise PT21PersistentWorkerError(
                    f"persistent stationary replay failed: {error}"
                ) from error

            started = time.monotonic()
            _write_all(
                turing.input,
                turing_request(BLOCK, packet.sha256),
                label="persistent Turing request",
            )
            turing_inputs = _decode_turing_response(turing.output)
            turing_seconds.append(time.monotonic() - started)
            turing_value = _strict_json(
                turing_inputs,
                maximum=TURING_MAXIMUM_BYTES,
                label="persistent Turing artifact",
            )
            if turing_inputs != _canonical(turing_value) + b"\n":
                raise PT21PersistentWorkerError(
                    "persistent Turing artifact is not canonical"
                )
            try:
                validate_turing_inputs(
                    turing_value,
                    expected_block=BLOCK,
                    expected_packet_sha256=packet.sha256,
                )
            except PT21TuringInputsError as error:
                raise PT21PersistentWorkerError(
                    f"persistent Turing artifact failed: {error}"
                ) from error

            stationary_path = persistent_directory / "stationary-trace.json"
            turing_path = persistent_directory / "turing-inputs.json"
            if request_index == 0:
                write_exclusive(stationary_path, response.stationary_trace)
                write_exclusive(turing_path, turing_inputs)
            elif (
                stationary_path.read_bytes() != response.stationary_trace
                or turing_path.read_bytes() != turing_inputs
            ):
                raise PT21PersistentWorkerError(
                    "repeated persistent sidecars are not byte-identical"
                )

            started = time.monotonic()
            try:
                adapted = adapt_block(
                    required_sign_packet=required_path,
                    stationary_trace=stationary_path,
                    turing_inputs=turing_path,
                    worker=junction_identity,
                )
            except PT21NativeRecordAdapterError as error:
                raise PT21PersistentWorkerError(
                    f"persistent native adapter failed: {error}"
                ) from error
            chain_commitment = _chain_commitment(
                event_record=response.event_record,
                junction_record=response.junction_record,
                required_packet=reference.required_packet,
                stationary_trace=response.stationary_trace,
                turing_inputs=turing_inputs,
                junction_executable_sha256=junction_identity.sha256,
                turing_executable_sha256=turing_identity.sha256,
                flint_sha256=flint_sha256,
                adapter_sources_sha256=adapter_sha256,
                finalizer_sha256=finalizer_identity.sha256,
            )
            block_record = _bound_block_record(
                adapted, chain_commitment_sha256=chain_commitment
            )
            _validate_multiplicity(
                junction_record=response.junction_record,
                block_record=block_record,
                block_artifact=adapted.block_artifact,
                stationary_trace=response.stationary_trace,
            )
            adapter_seconds.append(time.monotonic() - started)
            candidate = (
                response.event_record,
                response.junction_record,
                response.stationary_trace,
                turing_inputs,
                adapted.source_trace,
                adapted.block_artifact,
                block_record,
            )
            expected = (
                reference.event_record,
                reference.stationary_junction_record,
                reference.stationary_trace,
                reference.turing_inputs,
                reference.source_trace,
                reference.block_artifact,
                reference.block_record,
            )
            if candidate != expected:
                labels = (
                    "PT21EVT1",
                    "PT21STJ1",
                    "stationary trace",
                    "Turing artifact",
                    "source trace",
                    "block artifact",
                    "PT21BLK1",
                )
                changed = [
                    label
                    for label, actual, wanted in zip(labels, candidate, expected)
                    if actual != wanted
                ]
                raise PT21PersistentWorkerError(
                    "persistent output differs byte-for-byte from one-shot: "
                    + ", ".join(changed)
                )
            accepted_bytes = candidate
        junction.finish()
        turing.finish()
    except Exception:
        junction.abort()
        turing.abort()
        raise
    producer_adapter_seconds = time.monotonic() - overall_started
    assert accepted_bytes is not None
    (
        event_record,
        junction_record,
        stationary_trace,
        turing_inputs,
        source_trace,
        block_artifact,
        block_record,
    ) = accepted_bytes

    replay_started = time.monotonic()
    replayed = verify_retained_chain(
        event_record=event_record,
        junction_record=junction_record,
        required_packet=reference.required_packet,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        source_trace=source_trace,
        block_artifact=block_artifact,
        block_record=block_record,
        junction_executable_sha256=junction_identity.sha256,
        turing_executable_sha256=turing_identity.sha256,
        flint_sha256=flint_sha256,
        adapter_sources_sha256=adapter_sha256,
        finalizer_sha256=finalizer_identity.sha256,
    )
    replay_seconds = time.monotonic() - replay_started
    chain_commitment = str(replayed["chain_commitment_sha256"])

    retained = (
        ("event-record.pt21evt1", event_record),
        ("stationary-junction.pt21stj1", junction_record),
        ("source-trace.json", source_trace),
        ("block-artifact.json", block_artifact),
        ("block.pt21blk1", block_record),
        ("records.bin", block_record),
    )
    for name, raw in retained:
        path = persistent_directory / name
        if not path.exists():
            write_exclusive(path, raw)
    records_path = persistent_directory / "records.bin"
    shard_path = persistent_directory / "bounded-shard.bin"
    plan_sha256 = hashlib.sha256(
        PLAN_DOMAIN + bytes.fromhex(chain_commitment)
    ).hexdigest()
    prefix_sha256 = hashlib.sha256(
        PREFIX_DOMAIN + bytes.fromhex(chain_commitment)
    ).hexdigest()
    finalizer_started = time.monotonic()
    finalizer_stdout = _run(
        finalizer_executable,
        [
            "shard",
            "--input",
            str(records_path),
            "--output",
            str(shard_path),
            "--first-block",
            str(BLOCK),
            "--block-count",
            "1",
            "--worker-sha256",
            chain_commitment,
            "--plan-sha256",
            plan_sha256,
            "--prefix-evidence-sha256",
            prefix_sha256,
            "--bounded-test",
        ],
        maximum_stdout=MAXIMUM_FINALIZER_STDOUT,
        expected_sha256=finalizer_identity.sha256,
        environment=environment,
        label="persistent-output native PT21 shard finalizer",
    )
    finalizer_seconds = time.monotonic() - finalizer_started
    finalizer_summary = _strict_json(
        finalizer_stdout,
        maximum=MAXIMUM_FINALIZER_STDOUT,
        label="persistent-output native finalizer summary",
    )
    shard_archive = shard_path.read_bytes()
    if (
        finalizer_stdout != _canonical(finalizer_summary) + b"\n"
        or finalizer_summary.get("schema") != SHARD_SUMMARY_SCHEMA
        or finalizer_summary.get("source_claim_ready") is not False
        or finalizer_summary.get("block_count") != 1
        or finalizer_summary.get("total_main_slots") != MAIN_SLOTS
        or finalizer_summary.get("total_stationary_resolutions")
        != STATIONARY_CANDIDATES
        or finalizer_summary.get("archive_sha256")
        != hashlib.sha256(shard_archive).hexdigest()
        or shard_archive != reference.shard_archive
    ):
        raise PT21PersistentWorkerError(
            "persistent-output finalizer differs from one-shot bytes"
        )
    try:
        replay_shard(
            shard_path,
            expected_worker_sha256=chain_commitment,
            expected_plan_sha256=plan_sha256,
            expected_prefix_sha256=prefix_sha256,
            allow_bounded_test=True,
        )
    except PT21NativeFinalizerError as error:
        raise PT21PersistentWorkerError(
            f"persistent-output shard replay failed: {error}"
        ) from error
    final_flint_sha256, final_flint_size = _regular_identity(
        flint_library, "persistent FLINT shared library after execution"
    )
    if (
        final_flint_sha256 != flint_sha256
        or final_flint_size != flint_size
    ):
        raise PT21PersistentWorkerError(
            "FLINT shared-library identity changed during persistent execution"
        )

    _positive_finite(junction_seconds, "junction timings")
    _positive_finite(turing_seconds, "Turing timings")
    _positive_finite(adapter_seconds, "adapter timings")
    warm_junction = junction_seconds[1:] or junction_seconds
    warm_turing = turing_seconds[1:] or turing_seconds
    report: dict[str, object] = {
        "schema": SCHEMA,
        "accepted": True,
        "bounded_test": True,
        "synthetic_finite_values": True,
        "request_count": request_count,
        "repeated_block": BLOCK,
        "byte_identical_pt21evt1_count": request_count,
        "byte_identical_pt21stj1_count": request_count,
        "byte_identical_pt21blk1_count": request_count,
        "one_shot_reference_seconds": reference_seconds,
        "persistent_producer_adapter_seconds": producer_adapter_seconds,
        "persistent_seconds_per_request": (
            producer_adapter_seconds / request_count
        ),
        "junction_first_response_seconds": junction_seconds[0],
        "junction_warm_response_median_seconds": _median(warm_junction),
        "turing_first_response_seconds": turing_seconds[0],
        "turing_warm_response_median_seconds": _median(warm_turing),
        "exact_adapter_median_seconds": _median(adapter_seconds),
        "independent_replay_seconds": replay_seconds,
        "native_finalizer_seconds": finalizer_seconds,
        "persistent_process_count": 2,
        "per_request_native_process_start_count": 0,
        "native_finalizer_invocations": 1,
        "one_shot_reference_replayed": True,
        "persistent_output_independently_replayed": True,
        "persistent_output_native_shard_replayed": True,
        "event_record_sha256": hashlib.sha256(event_record).hexdigest(),
        "stationary_junction_record_sha256": hashlib.sha256(
            junction_record
        ).hexdigest(),
        "stationary_trace_sha256": hashlib.sha256(
            stationary_trace
        ).hexdigest(),
        "turing_inputs_sha256": hashlib.sha256(turing_inputs).hexdigest(),
        "block_record_sha256": hashlib.sha256(block_record).hexdigest(),
        "shard_archive_sha256": hashlib.sha256(shard_archive).hexdigest(),
        "chain_commitment_sha256": chain_commitment,
        "junction_executable_sha256": junction_identity.sha256,
        "turing_executable_sha256": turing_identity.sha256,
        "native_finalizer_sha256": finalizer_identity.sha256,
        "flint_library_sha256": flint_sha256,
        "flint_library_size_bytes": flint_size,
        "adapter_sources_sha256": adapter_sha256,
        "performance_bottleneck": "python_exact_rational_artifact_replay",
        "source_work_count_measured": False,
        "source_eta_claimed": False,
        "hardy_z_endpoint_realization_proved": False,
        "flint_to_mathlib_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "azure_attestation_verified": False,
        "production_ready": False,
        "source_claim_ready": False,
    }
    return PersistentBatch(
        report=report,
        event_record=event_record,
        stationary_junction_record=junction_record,
        turing_inputs=turing_inputs,
        source_trace=source_trace,
        block_artifact=block_artifact,
        block_record=block_record,
        shard_archive=shard_archive,
    )


__all__ = [
    "JUNCTION_REQUEST",
    "JUNCTION_REQUEST_MAGIC",
    "JUNCTION_RESPONSE",
    "JUNCTION_RESPONSE_MAGIC",
    "MAXIMUM_REQUESTS",
    "PT21PersistentWorkerError",
    "PersistentBatch",
    "SCHEMA",
    "TURING_REQUEST",
    "TURING_REQUEST_MAGIC",
    "TURING_RESPONSE",
    "TURING_RESPONSE_MAGIC",
    "junction_request",
    "run_persistent_bounded_batch",
    "turing_request",
]
