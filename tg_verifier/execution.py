"""Fail-closed supervisors for complete ternary-Goldbach replay programs.

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from time import perf_counter_ns
from typing import Any, NoReturn

from .evidence import (
    CDEM_REQUIRED_FIELDS,
    EvidenceError,
    parse_key_value_transcript,
    read_artifact_bytes,
    sha256_file,
    verify_cdem_abel_text,
)


class ExecutionReplayError(RuntimeError):
    """A supervised external replay was unavailable or failed closed."""


def _fail(message: str) -> NoReturn:
    raise ExecutionReplayError(message)


CDEM_REVIEWED_SOURCE_SHA256 = (
    "188e4dc7f3a17ffe336827b11289a6b23cd81284479c39f462a019d33eee1195"
)
CDEM_REVIEWED_SHA256_HEADER_SHA256 = (
    "2caa8055f0ed3d924dec6d0602d6b8ebbe798d10cdf28044d7c909f5e17f26b1"
)

CDEM_SMALL_PREFLIGHT_FIELDS: dict[str, int] = {
    "K": 10,
    "N": 40,
    "A": 41,
    "MOBIUS_M": -1,
    "MOBIUS_Q": 7,
    "COEFF_SCALE": 10**30,
    "S_LOWER_NUM": 90_476_190_476_190_476_190_476_190_474,
    "S_UPPER_NUM": 90_476_190_476_190_476_190_476_190_477,
    "FINAL_F": 4,
    "FINAL_G": 3,
    "TOTAL_VARIATION": 13,
    "WEIGHT_SCALE": 10**18,
    "U_INC_UPPER_NUM": 166_533_387_224_711_899,
    "V_INC_UPPER_NUM": 2_890_717_952_509_426_565,
    "ENDPOINT_RSQRT_UPPER_NUM": 156_173_761_888_606_066,
}


def _positive_integer(name: str, value: int, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        _fail(f"{name} must be an integer in [1, {maximum}]")
    return value


def _proof_fields(transcript: str) -> dict[str, int]:
    fields = parse_key_value_transcript(transcript)
    names = tuple(CDEM_REQUIRED_FIELDS) + (
        "U_INC_UPPER_NUM",
        "V_INC_UPPER_NUM",
    )
    result: dict[str, int] = {}
    for name in names:
        try:
            result[name] = int(fields[name])
        except (KeyError, ValueError) as error:
            raise ExecutionReplayError(
                f"CDEM producer omitted or malformed proof field {name}"
            ) from error
    return result


def _canonical_proof_digest(fields: dict[str, int]) -> str:
    encoded = json.dumps(
        fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _run_checked_process(
    command: list[str], *, environment: dict[str, str], max_seconds: int, label: str
) -> tuple[str, int]:
    started = perf_counter_ns()
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max_seconds,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise ExecutionReplayError(
            f"{label} exceeded {max_seconds} seconds"
        ) from error
    elapsed = (perf_counter_ns() - started) // 1_000_000
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or "no stderr diagnostic"
        _fail(f"{label} exited {completed.returncode}: {diagnostic}")
    if completed.stderr:
        _fail(f"{label} unexpectedly wrote to stderr")
    return completed.stdout, elapsed


def run_cdem_abel(
    executable: str | Path,
    *,
    source: str | Path | None = None,
    block_size: int = 5_000_000,
    threads: int = 8,
    max_seconds: int = 900,
    repeats: int = 1,
) -> tuple[dict[str, Any], str]:
    """Check output from a caller-supplied CDEM-like executable.

    This lower-level function cannot prove that an arbitrary executable did
    the advertised work.  Its receipt therefore records only a producer
    output-contract check.  Use :func:`build_and_run_cdem_abel` for the
    reviewed-source full external replay.
    """

    block_size = _positive_integer("block_size", block_size, maximum=5_000_000_000)
    threads = _positive_integer("threads", threads, maximum=1_024)
    max_seconds = _positive_integer("max_seconds", max_seconds, maximum=86_400)
    repeats = _positive_integer("repeats", repeats, maximum=10)
    program = Path(executable).resolve()
    if not program.is_file() or not os.access(program, os.X_OK):
        _fail(f"CDEM executable is missing or not executable: {program}")
    source_path = None if source is None else Path(source).resolve()
    if source_path is not None and not source_path.is_file():
        _fail(f"CDEM source is missing: {source_path}")

    binary_hash_before = sha256_file(program)
    source_hash = None if source_path is None else sha256_file(source_path)
    environment = os.environ.copy()
    environment["OMP_DYNAMIC"] = "FALSE"
    environment["OMP_NUM_THREADS"] = str(threads)
    command = [
        str(program),
        "199330",
        "5000000000",
        str(block_size),
    ]
    transcripts: list[str] = []
    proof_runs: list[dict[str, int]] = []
    elapsed_runs: list[int] = []
    for run_index in range(repeats):
        stdout, elapsed = _run_checked_process(
            command,
            environment=environment,
            max_seconds=max_seconds,
            label=f"CDEM producer invocation {run_index + 1}",
        )
        elapsed_runs.append(elapsed)
        try:
            checked = verify_cdem_abel_text(stdout)
        except EvidenceError as error:
            raise ExecutionReplayError(
                f"CDEM replay {run_index + 1} failed its exact output contract: {error}"
            ) from error
        if not checked.accepted:
            _fail(f"CDEM replay {run_index + 1} was not accepted")
        transcripts.append(stdout)
        proof_runs.append(_proof_fields(stdout))

    if any(fields != proof_runs[0] for fields in proof_runs[1:]):
        _fail("CDEM mathematical output fields differ across repeated executions")
    binary_hash_after = sha256_file(program)
    if binary_hash_after != binary_hash_before:
        _fail("CDEM executable changed while the supervised replay was running")
    if source_path is not None and sha256_file(source_path) != source_hash:
        _fail("CDEM source changed while the supervised replay was running")

    transcript_hashes = [
        hashlib.sha256(value.encode("utf-8")).hexdigest() for value in transcripts
    ]
    fields = proof_runs[0]
    return (
        {
            "schema_version": 1,
            "accepted": True,
            "atom_id": "cdem-table-abel",
            "verification_class": "producer_output_contract_only",
            "command_parameters": {
                "K": 199_330,
                "N": 5_000_000_000,
                "block_size": block_size,
                "threads": threads,
                "repeats": repeats,
            },
            "executable": str(program),
            "executable_sha256": binary_hash_before,
            "source": None if source_path is None else str(source_path),
            "source_sha256": source_hash,
            "transcript_sha256": transcript_hashes,
            "proof_fields_sha256": _canonical_proof_digest(fields),
            "elapsed_milliseconds": elapsed_runs,
            "producer_reported_full_parameters": True,
            "complete_range_execution_verified": False,
            "source_supplied_for_audit": source_path is not None,
            "all_expected_terminal_fields_matched": True,
            "stored_directed_abel_bound_fields_matched": True,
            "cross_run_mathematical_fields_identical": repeats > 1,
            "ordinary_kernel_lean_proof": False,
            "lean_atom_discharged": False,
            "remaining_trust_boundary": (
                "the supplied executable may merely print these constants; "
                "use build_and_run_cdem_abel to bind execution to reviewed source"
            ),
        },
        transcripts[0],
    )


def build_and_run_cdem_abel(
    source: str | Path,
    *,
    compiler: str | Path = "g++",
    block_size: int = 5_000_000,
    threads: int = 8,
    max_seconds: int = 900,
    repeats: int = 1,
) -> tuple[dict[str, Any], str]:
    """Compile the pinned reviewed source, preflight it, and run full replay."""

    source_path = Path(source).resolve()
    if not source_path.is_file():
        _fail(f"CDEM source is missing: {source_path}")
    source_bytes = read_artifact_bytes(source_path)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source_hash != CDEM_REVIEWED_SOURCE_SHA256:
        _fail(
            "CDEM source does not match the reviewed SHA-256: expected "
            f"{CDEM_REVIEWED_SOURCE_SHA256}, got {source_hash}"
        )
    header_path = (
        source_path.parent.parent / "gpu" / "include" / "sparkinterval" / "sha256.hpp"
    )
    header_bytes = read_artifact_bytes(header_path)
    header_hash = hashlib.sha256(header_bytes).hexdigest()
    if header_hash != CDEM_REVIEWED_SHA256_HEADER_SHA256:
        _fail(
            "CDEM SHA-256 header does not match the reviewed SHA-256: expected "
            f"{CDEM_REVIEWED_SHA256_HEADER_SHA256}, got {header_hash}"
        )
    compiler_text = str(compiler)
    compiler_found = shutil.which(compiler_text)
    compiler_path = (
        Path(compiler_found).resolve()
        if compiler_found is not None
        else Path(compiler_text).resolve()
    )
    if not compiler_path.is_file() or not os.access(compiler_path, os.X_OK):
        _fail(f"C++ compiler is missing or not executable: {compiler_path}")
    compiler_hash = sha256_file(compiler_path)
    version = subprocess.run(
        [str(compiler_path), "--version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if version.returncode != 0 or not version.stdout.splitlines():
        _fail("could not identify the selected C++ compiler")
    compiler_version = version.stdout.splitlines()[0]

    with tempfile.TemporaryDirectory(prefix="sparkinterval-cdem-") as directory:
        source_copy = Path(directory) / source_path.name
        source_copy.write_bytes(source_bytes)
        include_root = Path(directory) / "include"
        header_copy = include_root / "sparkinterval" / "sha256.hpp"
        header_copy.parent.mkdir(parents=True)
        header_copy.write_bytes(header_bytes)
        executable = Path(directory) / "tg_cdem_abel"
        compile_command = [
            str(compiler_path),
            "-O3",
            "-std=c++20",
            "-fopenmp",
            "-I",
            str(include_root),
            str(source_copy),
            "-o",
            str(executable),
        ]
        compile_environment = os.environ.copy()
        _stdout, compile_ms = _run_checked_process(
            compile_command,
            environment=compile_environment,
            max_seconds=120,
            label="CDEM reviewed-source compilation",
        )
        executable_hash = sha256_file(executable)

        preflight_environment = os.environ.copy()
        preflight_environment["OMP_DYNAMIC"] = "FALSE"
        preflight_environment["OMP_NUM_THREADS"] = "2"
        preflight_stdout, preflight_ms = _run_checked_process(
            [str(executable), "10", "40", "7"],
            environment=preflight_environment,
            max_seconds=30,
            label="CDEM independent small recurrence preflight",
        )
        preflight_fields = parse_key_value_transcript(preflight_stdout)
        for name, expected in CDEM_SMALL_PREFLIGHT_FIELDS.items():
            try:
                actual = int(preflight_fields[name])
            except (KeyError, ValueError) as error:
                raise ExecutionReplayError(
                    f"CDEM preflight omitted or malformed field {name}"
                ) from error
            if actual != expected:
                _fail(
                    f"CDEM preflight field {name} differs: expected {expected}, "
                    f"got {actual}"
                )

        receipt, transcript = run_cdem_abel(
            executable,
            source=source_copy,
            block_size=block_size,
            threads=threads,
            max_seconds=max_seconds,
            repeats=repeats,
        )
        chunk_check = verify_cdem_abel_text(transcript, require_chunks=True)

    if sha256_file(source_path) != source_hash:
        _fail("reviewed CDEM source changed during supervised compilation or replay")
    if sha256_file(header_path) != header_hash:
        _fail("reviewed CDEM SHA-256 header changed during compilation or replay")
    if sha256_file(compiler_path) != compiler_hash:
        _fail("selected C++ compiler changed during compilation or replay")

    receipt.update(
        {
            "verification_class": "complete_external_reviewed_source_replay",
            "reviewed_source_sha256": source_hash,
            "reviewed_source_hash_matched": True,
            "compiled_source_was_exact_captured_bytes": True,
            "reviewed_sha256_header_sha256": header_hash,
            "reviewed_sha256_header_hash_matched": True,
            "compiled_header_was_exact_captured_bytes": True,
            "source_compiled_by_supervisor": True,
            "source": str(source_path),
            "source_sha256": source_hash,
            "compiler": str(compiler_path),
            "compiler_sha256": compiler_hash,
            "compiler_version": compiler_version,
            "compiled_executable_sha256": executable_hash,
            "executable": None,
            "temporary_executable_retained": False,
            "compile_elapsed_milliseconds": compile_ms,
            "independent_small_recurrence_preflight": True,
            "preflight_elapsed_milliseconds": preflight_ms,
            "producer_reported_full_parameters": True,
            "complete_range_execution_verified": True,
            "both_directed_abel_bounds_closed": True,
            "chunk_state_composition_verified": True,
            "chunk_count": chunk_check.metrics["chunk_count"],
            "chunk_manifest_sha256": chunk_check.metrics[
                "chunk_manifest_sha256"
            ],
            "remaining_trust_boundary": (
                "reviewed C++ source, identified compiler/runtime execution, "
                "and the missing Lean realization of the finite recurrence"
            ),
        }
    )
    return receipt, transcript
