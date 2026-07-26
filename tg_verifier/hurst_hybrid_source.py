# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed CPU/H100 source-range handoff for the shared Hurst campaign.

The production geometry is deliberately literal:

* the reviewed CPU/Hurst shard runner covers ``[1, 10^12 + 1)``;
* the persistent CUDA runner covers ``[10^12 + 1, 10^16 + 1)``.

The CPU runner is executed in both summary and verify modes.  The two exact
row commitments and four-coordinate deltas must agree.  A canonical handoff
then binds the CPU receipts and state.  Its digest is supplied as the initial
``previous_leaf_sha256`` of the existing persistent CUDA runner.  Every CUDA
leaf digest is independently reconstructed here, ranges and M/Q states must
be contiguous, and the terminal global affine extrema are recomputed from
the leaf stream.

The production plan defaults to 100-million-row H100 super-shards.  That
choice is a GB10-informed starting point, not an H100 performance claim.
Before a source-scale H100 launch, benchmark 100-, 200-, and
400-million-row super-shards on the exact deployment image and device, then
materialize a plan with the measured winner.

This module materializes and replays finite-computation machinery.  It never
claims source semantics, attestation, compiler refinement, Lean discharge, or
proof of an external atom.  Production execution is guarded by the existing
Azure measured-worker scope.  An explicitly marked bounded-test geometry of
at most 64 total rows exists solely for mock-runner tests.
"""

from __future__ import annotations

from array import array
from bisect import bisect_right
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, BinaryIO, Mapping, Sequence

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    parse_json_bytes,
    require_azure_measured_worker_for_workload,
    sha256_bytes,
)
from .evidence import EvidenceError, load_decimal_json_bytes
from .hurst_residual_campaign import (
    ATOM_PROFILES,
    HurstResidualCampaignError,
    MAX_RECEIPT_BYTES,
    MAX_SEGMENT_SIZE,
    MIN_SEGMENT_SIZE,
    RUNNER_ALGORITHM as CPU_RUNNER_ALGORITHM,
    RUNNER_CLASSIFICATION as CPU_RUNNER_CLASSIFICATION,
    STATE_COMPONENTS,
    UPSTREAM_COMMIT,
    _validate_upstream_manifest as validate_upstream_manifest,
    validate_runner_receipt,
)


SCHEMA_VERSION = 1
PLAN_KIND = "sparkinterval.tg.hurst-cpu-h100-hybrid-plan.v1"
MATERIALIZATION_KIND = (
    "sparkinterval.tg.hurst-cpu-h100-hybrid-materialization.v1"
)
CPU_HANDOFF_KIND = "sparkinterval.tg.hurst-cpu-h100-handoff.v1"
RESULT_KIND = "sparkinterval.tg.hurst-cpu-h100-hybrid-result.v1"

SOURCE_LOWER = 1
CPU_UPPER_EXCLUSIVE = 1_000_000_000_001
H100_LOWER = CPU_UPPER_EXCLUSIVE
SOURCE_UPPER_EXCLUSIVE = 10_000_000_000_000_001

DEFAULT_CPU_SEGMENT_ROWS = 110_880_000
DEFAULT_H100_LEAF_ROWS = 100_000_000
DEFAULT_H100_SUPER_SHARD_ROWS = 100_000_000
MAX_H100_LEAF_ROWS = 100_000_000
MAX_H100_SUPER_SHARD_ROWS = 1_000_000_000
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 4 * 1024 * 1024
MAX_JSONL_LINE_BYTES = 64 * 1024
MAX_INPUT_BYTES = 1 << 30

GPU_SCHEMA = "sparkinterval.tg.mobius-persistent-jsonl.v1"
GPU_ALGORITHM = "tg_mobius_fused_affine_persistent_v1"
GPU_CLASSIFICATION = (
    "source_shaped_persistent_leaf_chain_not_source_evidence_"
    "attestation_compiler_refinement_or_lean_proof"
)
GPU_LEAF_DOMAIN = b"sparkinterval.tg.mobius-persistent-leaf.v1"
HANDOFF_DOMAIN = b"sparkinterval/tg/hurst-cpu-h100-handoff/v1\0"
RESULT_DOMAIN = b"sparkinterval/tg/hurst-cpu-h100-result/v1\0"
ZERO_SHA256 = "0" * 64
SOURCE_PRIME_ROSTER_COUNT = 5_761_455
SOURCE_PRIME_ROSTER_BYTES = SOURCE_PRIME_ROSTER_COUNT * 4
SOURCE_PRIME_ROSTER_SHA256 = (
    "0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5"
)
PLAN_CLASSIFICATION = (
    "immutable_hybrid_plan_not_execution_attestation_"
    "semantic_evidence_or_lean_proof"
)
MATERIALIZATION_CLASSIFICATION = (
    "source_identity_capture_not_transitive_source_closure_"
    "execution_evidence_or_semantic_proof"
)

PLAN_FIELDS = {
    "classification",
    "cpu",
    "h100",
    "inputs",
    "kind",
    "mode",
    "schema_version",
    "semantic_flags",
    "source_geometry",
    "source_pins",
}
CPU_PLAN_FIELDS = {
    "algorithm",
    "classification",
    "segment_rows",
    "state_components",
    "two_pass",
    "upstream_commit",
}
H100_PLAN_FIELDS = {
    "algorithm",
    "classification",
    "external_cross_device_override_allowed",
    "expected_leaf_count",
    "leaf_rows",
    "required_device_class",
    "super_shard_rows",
}
INPUT_NAMES = {"cpu_runner", "h100_runner", "prime_roster"}
SOURCE_PIN_NAMES = {
    "cpu_runner_source",
    "h100_kernel_source",
    "h100_persistent_source",
    "h100_runner_source",
    "h100_runtime_policy",
    "persistent_kernel_source",
    "upstream_manifest",
}
MATERIALIZATION_FIELDS = {
    "accepted",
    "classification",
    "execution_completed",
    "kind",
    "lean_theorem_produced",
    "plan",
    "schema_version",
    "semantic_flags",
    "source_run_receipt_produced",
}
PIN_FIELDS = {"path", "sha256", "size_bytes"}
GEOMETRY_FIELDS = {
    "cpu",
    "gap_free",
    "h100",
    "source_lower",
    "source_upper_exclusive",
    "split",
}
RANGE_FIELDS = {"count", "lower", "upper_exclusive"}
SEMANTIC_FLAGS = {
    "cuda_or_cpp_compiler_refinement_proved": False,
    "execution_attested": False,
    "full_source_semantics_verified": False,
    "lean_atom_discharged": False,
    "primitive_mobius_realization_proved": False,
    "proves_any_external_atom": False,
    "source_rows_replayed_independently": False,
}

GPU_HEADER_FIELDS = {
    "record",
    "schema",
    "algorithm",
    "classification",
    "lower",
    "upper_exclusive",
    "count",
    "shard_rows",
    "super_shard_rows",
    "prime_roster_sha256",
    "executable_sha256",
    "prime_roster_load_count",
    "prime_roster_upload_count",
    "cuda_allocation_epoch_count",
    "cuda_event_set_count",
    "fused_support_load_balanced_dense_schedule",
    "fused_support_residue_235_initializer",
    "residue_235_initializer_table_rows",
    "residue_235_initializer_table_bytes",
    "residue_235_table_storage",
    "residue_235_table_materialization_scope",
    "residue_235_explicit_h2d_upload_bytes_per_sieve",
    "fused_multiblock_dense_prime_limit",
    "fused_multiblock_slots_per_prime",
    "fused_multiblock_unseeded_slots_per_prime",
    "fused_multiblock_residue_235_slots_per_prime",
    "fused_multiblock_residue_235_minimum_safe_slots_per_prime",
    "fused_multiblock_iterations_per_thread",
    "split_square_dense_prime_limit",
    "affine_candidates_transferred_per_leaf",
    "affine_candidate_bytes_per_leaf",
    "affine_prefix_device_bytes",
    "affine_workspace_device_bytes",
    "fused_support_device_bytes",
    "mobius_device_bytes",
    "persistent_device_allocation_bytes",
    "device_free_bytes_before_allocation",
    "device_total_bytes",
    "production_device_to_host_bytes_per_leaf",
    "production_mu_rows_transferred",
    "production_mu_rows_hashed",
    "production_fused_prefix_input_path",
    "production_split_square_support_path",
    "inline_square_modulo_reference_path",
    "distinct_factor_events_compute_square_modulo",
    "separate_square_strike_pass",
    "split_square_dense_prime_limit",
    "split_square_operation_order",
    "intermediate_mobius_device_rows_materialized",
    "leaf_chain_binds_compact_gpu_summary",
    "mu_row_commitment_present_in_production",
    "host_rechecks_final_squarefree_winners",
    "little_mertens_deltas_are_exact_zero",
    "qualification_mu_output",
    "source_rows_replayed_independently",
    "full_source_range",
    "execution_attested",
    "cuda_or_cpp_compiler_refinement_proved",
    "primitive_mobius_realization_proved",
    "lean_atom_discharged",
    "proves_any_external_atom",
    "roster_load_milliseconds",
    "allocation_milliseconds",
    "roster_upload_milliseconds",
}

GPU_LEAF_FIELDS = {
    "record",
    "index",
    "lower",
    "upper_exclusive",
    "count",
    "previous_leaf_sha256",
    "leaf_sha256",
    "qualification_mu_plus_one_sha256",
    "incoming_mertens",
    "outgoing_mertens",
    "delta_mertens",
    "incoming_squarefree",
    "outgoing_squarefree",
    "delta_squarefree",
    "hurst_lower",
    "hurst_upper",
    "squarefree_lower",
    "squarefree_upper",
    "source_prime_fast_path",
    "selected_prime_count",
    "dense_prime_count",
    "super_shard_index",
    "super_shard_leaf_index",
    "super_shard_lower",
    "super_shard_upper_exclusive",
    "super_shard_count",
    "active_prime_filter_milliseconds",
    "active_prime_upload_milliseconds",
    "kernel_milliseconds",
    "super_shard_sieve_kernel_milliseconds",
    "affine_milliseconds",
    "transfer_milliseconds",
    "control_loop_milliseconds",
    "affine_candidate_bytes_transferred",
    "poison_count",
    "production_device_to_host_bytes",
    "qualification_device_to_host_mu_bytes",
    "mu_row_commitment_present",
    "source_rows_replayed_independently",
    "execution_attested",
    "cuda_or_cpp_compiler_refinement_proved",
    "lean_atom_discharged",
    "proves_any_external_atom",
}

GPU_TERMINAL_FIELDS = {
    "record",
    "algorithm",
    "classification",
    "lower",
    "upper_exclusive",
    "count",
    "leaf_count",
    "final_leaf_sha256",
    "production_mu_row_commitment_present",
    "incoming_mertens",
    "outgoing_mertens",
    "delta_mertens",
    "incoming_squarefree",
    "outgoing_squarefree",
    "delta_squarefree",
    "global_hurst_lower",
    "global_hurst_upper",
    "global_squarefree_lower",
    "global_squarefree_upper",
    "source_fast_path_leaf_count",
    "source_fast_path_super_shard_count",
    "super_shard_count",
    "sieve_launch_count",
    "receipt_leaf_count",
    "sieve_launches_saved_vs_leaf_schedule",
    "super_shard_rows",
    "active_filter_milliseconds",
    "active_prime_upload_milliseconds",
    "kernel_milliseconds",
    "affine_milliseconds",
    "transfer_milliseconds",
    "control_loop_milliseconds",
    "roster_load_count",
    "roster_upload_count",
    "allocation_epoch_count",
    "event_set_count",
    "buffers_reused_across_all_leaves",
    "affine_candidates_transferred_per_leaf",
    "affine_candidate_bytes_per_leaf",
    "production_device_to_host_bytes_per_leaf",
    "production_mu_rows_transferred",
    "production_mu_rows_hashed",
    "leaf_chain_binds_compact_gpu_summary",
    "host_rechecks_final_squarefree_winners",
    "checkpoint_restart_fields_emitted_per_leaf",
    "little_mertens_lower_delta",
    "little_mertens_upper_delta",
    "source_rows_replayed_independently",
    "full_source_range",
    "execution_attested",
    "cuda_or_cpp_compiler_refinement_proved",
    "primitive_mobius_realization_proved",
    "lean_atom_discharged",
    "proves_any_external_atom",
    "process_milliseconds",
}

GPU_HEADER_INTEGER_FIELDS = {
    "lower",
    "upper_exclusive",
    "count",
    "shard_rows",
    "super_shard_rows",
    "prime_roster_load_count",
    "prime_roster_upload_count",
    "cuda_allocation_epoch_count",
    "cuda_event_set_count",
    "residue_235_initializer_table_rows",
    "residue_235_initializer_table_bytes",
    "residue_235_explicit_h2d_upload_bytes_per_sieve",
    "fused_multiblock_dense_prime_limit",
    "fused_multiblock_slots_per_prime",
    "fused_multiblock_unseeded_slots_per_prime",
    "fused_multiblock_residue_235_slots_per_prime",
    "fused_multiblock_residue_235_minimum_safe_slots_per_prime",
    "fused_multiblock_iterations_per_thread",
    "affine_candidates_transferred_per_leaf",
    "affine_candidate_bytes_per_leaf",
    "affine_prefix_device_bytes",
    "affine_workspace_device_bytes",
    "fused_support_device_bytes",
    "mobius_device_bytes",
    "persistent_device_allocation_bytes",
    "device_free_bytes_before_allocation",
    "device_total_bytes",
    "production_device_to_host_bytes_per_leaf",
}

GPU_LEAF_INTEGER_FIELDS = {
    "index",
    "lower",
    "upper_exclusive",
    "count",
    "incoming_mertens",
    "outgoing_mertens",
    "delta_mertens",
    "incoming_squarefree",
    "outgoing_squarefree",
    "delta_squarefree",
    "selected_prime_count",
    "dense_prime_count",
    "super_shard_index",
    "super_shard_leaf_index",
    "super_shard_lower",
    "super_shard_upper_exclusive",
    "super_shard_count",
    "affine_candidate_bytes_transferred",
    "poison_count",
    "production_device_to_host_bytes",
    "qualification_device_to_host_mu_bytes",
}

GPU_TERMINAL_INTEGER_FIELDS = {
    "lower",
    "upper_exclusive",
    "count",
    "leaf_count",
    "incoming_mertens",
    "outgoing_mertens",
    "delta_mertens",
    "incoming_squarefree",
    "outgoing_squarefree",
    "delta_squarefree",
    "source_fast_path_leaf_count",
    "source_fast_path_super_shard_count",
    "super_shard_count",
    "sieve_launch_count",
    "receipt_leaf_count",
    "sieve_launches_saved_vs_leaf_schedule",
    "super_shard_rows",
    "roster_load_count",
    "roster_upload_count",
    "allocation_epoch_count",
    "event_set_count",
    "affine_candidates_transferred_per_leaf",
    "affine_candidate_bytes_per_leaf",
    "production_device_to_host_bytes_per_leaf",
    "little_mertens_lower_delta",
    "little_mertens_upper_delta",
}


class HurstHybridSourceError(RuntimeError):
    """A geometry, identity, subprocess, receipt, or publication check failed."""


def _exact(value: Any, fields: set[str], what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise HurstHybridSourceError(
            f"{what} fields differ "
            f"(missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)})"
        )
    return value


def _plain_int(
    value: Any, what: str, *, minimum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HurstHybridSourceError(f"{what} must be an integer")
    if minimum is not None and value < minimum:
        raise HurstHybridSourceError(f"{what} must be at least {minimum}")
    return value


def _require_integer_fields(
    record: Mapping[str, Any],
    fields: set[str],
    what: str,
) -> None:
    for name in fields:
        _plain_int(record[name], f"{what}.{name}")


def _signed_64(value: Any, what: str) -> int:
    parsed = _plain_int(value, what)
    if parsed < -(1 << 63) or parsed > (1 << 63) - 1:
        raise HurstHybridSourceError(f"{what} exceeds signed 64-bit range")
    return parsed


def _unsigned_64(value: Any, what: str) -> int:
    parsed = _plain_int(value, what, minimum=0)
    if parsed > (1 << 64) - 1:
        raise HurstHybridSourceError(f"{what} exceeds unsigned 64-bit range")
    return parsed


def _digest(value: Any, what: str, *, nonzero: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        or (nonzero and value == ZERO_SHA256)
    ):
        raise HurstHybridSourceError(f"{what} must be lowercase SHA-256")
    return value


def _nonnegative_decimal_text(value: Any, what: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise HurstHybridSourceError(f"{what} must be decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise HurstHybridSourceError(
            f"{what} must be decimal text"
        ) from error
    if not parsed.is_finite() or parsed < 0:
        raise HurstHybridSourceError(
            f"{what} must be finite and nonnegative"
        )
    return parsed


def _validate_upstream(raw: bytes) -> None:
    try:
        validate_upstream_manifest(raw)
    except HurstResidualCampaignError as error:
        raise HurstHybridSourceError(
            f"captured upstream manifest is invalid: {error}"
        ) from error


def _safe_regular(
    path: Path,
    what: str,
    *,
    executable: bool,
    maximum_bytes: int = MAX_INPUT_BYTES,
) -> tuple[bytes, dict[str, Any]]:
    maximum = _plain_int(
        maximum_bytes, f"{what} byte limit", minimum=1
    )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise HurstHybridSourceError(f"cannot open {what}: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise HurstHybridSourceError(
                f"{what} must be one unlinked regular file"
            )
        if executable and not metadata.st_mode & (
            stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        ):
            raise HurstHybridSourceError(f"{what} is not executable")
        if metadata.st_size <= 0 or metadata.st_size > maximum:
            raise HurstHybridSourceError(f"{what} has an invalid size")
        chunks: list[bytes] = []
        total = 0
        while total <= maximum:
            chunk = os.read(
                descriptor, min(1 << 20, maximum + 1 - total)
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        raw = b"".join(chunks)
        final_metadata = os.fstat(descriptor)
    except OSError as error:
        raise HurstHybridSourceError(f"cannot read {what}: {error}") from error
    finally:
        os.close(descriptor)
    if (
        len(raw) != metadata.st_size
        or len(raw) > maximum
        or final_metadata.st_size != metadata.st_size
        or final_metadata.st_mtime_ns != metadata.st_mtime_ns
        or final_metadata.st_ctime_ns != metadata.st_ctime_ns
    ):
        raise HurstHybridSourceError(f"{what} changed while being read")
    return raw, {
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
    }


def _open_pinned_fd(
    path: Path,
    pin: Mapping[str, Any],
    what: str,
    *,
    executable: bool,
) -> int:
    if not hasattr(os, "memfd_create") or not hasattr(os, "MFD_ALLOW_SEALING"):
        raise HurstHybridSourceError(
            "sealed in-memory execution files require Linux memfd support"
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    source_descriptor: int | None = None
    staging_descriptor: int | None = None
    try:
        source_descriptor = os.open(path, flags)
        metadata = os.fstat(source_descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise HurstHybridSourceError(
                f"{what} must be one unlinked regular file"
            )
        if executable and not metadata.st_mode & (
            stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        ):
            raise HurstHybridSourceError(f"{what} is not executable")
        staging_descriptor = os.memfd_create(
            f"sparkinterval-{what.replace(' ', '-')}",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(source_descriptor, 1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise HurstHybridSourceError(
                    f"{what} exceeds the input byte limit"
                )
            digest.update(chunk)
            pending = memoryview(chunk)
            while pending:
                written = os.write(staging_descriptor, pending)
                if written <= 0:
                    raise HurstHybridSourceError(
                        f"could not copy {what} into sealed memory"
                    )
                pending = pending[written:]
        final_metadata = os.fstat(source_descriptor)
        if (
            final_metadata.st_size != metadata.st_size
            or final_metadata.st_mtime_ns != metadata.st_mtime_ns
            or final_metadata.st_ctime_ns != metadata.st_ctime_ns
            or digest.hexdigest() != pin["sha256"]
            or total != pin["size_bytes"]
        ):
            raise HurstHybridSourceError(f"{what} identity changed")
        os.fchmod(staging_descriptor, 0o500 if executable else 0o400)
        seals = (
            fcntl.F_SEAL_WRITE
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_SEAL
        )
        fcntl.fcntl(staging_descriptor, fcntl.F_ADD_SEALS, seals)
        readonly_descriptor = os.open(
            f"/proc/self/fd/{staging_descriptor}", os.O_RDONLY
        )
        result = readonly_descriptor
        return result
    except (OSError, KeyError) as error:
        raise HurstHybridSourceError(
            f"cannot pin {what}: {error}"
        ) from error
    finally:
        if source_descriptor is not None:
            os.close(source_descriptor)
        if staging_descriptor is not None:
            os.close(staging_descriptor)


def _read_open_fd(
    descriptor: int, *, maximum_bytes: int, what: str
) -> bytes:
    maximum = _plain_int(maximum_bytes, f"{what} byte limit", minimum=1)
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        total = 0
        while total <= maximum:
            chunk = os.read(
                descriptor, min(1 << 20, maximum + 1 - total)
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        os.lseek(descriptor, 0, os.SEEK_SET)
    except OSError as error:
        raise HurstHybridSourceError(
            f"cannot read pinned {what}: {error}"
        ) from error
    if total > maximum:
        raise HurstHybridSourceError(
            f"pinned {what} exceeds the byte limit"
        )
    return b"".join(chunks)


def _range(lower: int, upper_exclusive: int) -> dict[str, int]:
    return {
        "count": upper_exclusive - lower,
        "lower": lower,
        "upper_exclusive": upper_exclusive,
    }


def source_geometry(
    *,
    split: int = H100_LOWER,
    upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    lower = SOURCE_LOWER
    split = _plain_int(split, "split", minimum=2)
    upper = _plain_int(upper_exclusive, "source upper", minimum=3)
    if not lower < split < upper <= SOURCE_UPPER_EXCLUSIVE:
        raise HurstHybridSourceError("hybrid source ranges are reversed")
    production = split == H100_LOWER and upper == SOURCE_UPPER_EXCLUSIVE
    if not production:
        if not allow_bounded_test:
            raise HurstHybridSourceError(
                "non-production geometry requires allow_bounded_test=True"
            )
        if upper - lower > 64:
            raise HurstHybridSourceError(
                "local bounded-test geometry may cover at most 64 rows"
            )
    elif allow_bounded_test:
        raise HurstHybridSourceError(
            "production geometry cannot be labelled bounded-test"
        )
    return {
        "cpu": _range(lower, split),
        "gap_free": True,
        "h100": _range(split, upper),
        "source_lower": lower,
        "source_upper_exclusive": upper,
        "split": split,
    }


def _copy_captured(
    destination: Path,
    raw: bytes,
    *,
    executable: bool,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o700 if executable else 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            descriptor = -1
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return {
        "path": destination.as_posix(),
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
    }


def _readonly_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file():
            mode = path.stat().st_mode
            os.chmod(path, 0o555 if mode & stat.S_IXUSR else 0o444)
        elif path.is_dir():
            os.chmod(path, 0o555)
    os.chmod(root, 0o555)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def materialize(
    *,
    cpu_runner: Path,
    h100_runner: Path,
    prime_roster: Path,
    output_directory: Path,
    cpu_segment_rows: int = DEFAULT_CPU_SEGMENT_ROWS,
    h100_leaf_rows: int = DEFAULT_H100_LEAF_ROWS,
    h100_super_shard_rows: int = DEFAULT_H100_SUPER_SHARD_ROWS,
    split: int = H100_LOWER,
    upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    """Capture runner identities and atomically publish an immutable plan."""

    geometry = source_geometry(
        split=split,
        upper_exclusive=upper_exclusive,
        allow_bounded_test=allow_bounded_test,
    )
    cpu_segment = _plain_int(
        cpu_segment_rows, "CPU segment rows", minimum=1
    )
    leaf_rows = _plain_int(h100_leaf_rows, "H100 leaf rows", minimum=1)
    super_rows = _plain_int(
        h100_super_shard_rows, "H100 super-shard rows", minimum=1
    )
    if leaf_rows > MAX_H100_LEAF_ROWS:
        raise HurstHybridSourceError("H100 leaf rows exceed runner limit")
    if cpu_segment > MAX_SEGMENT_SIZE:
        raise HurstHybridSourceError("CPU segment rows exceed runner limit")
    if (
        super_rows < leaf_rows
        or super_rows > MAX_H100_SUPER_SHARD_ROWS
        or super_rows % leaf_rows != 0
    ):
        raise HurstHybridSourceError(
            "H100 super-shard rows must be an integral leaf multiple"
        )
    if cpu_segment < MIN_SEGMENT_SIZE:
        raise HurstHybridSourceError(
            "CPU segment rows are below the reviewed runner minimum"
        )

    inputs = (
        ("cpu_runner", cpu_runner, True, "inputs/cpu-hurst-runner"),
        ("h100_runner", h100_runner, True, "inputs/h100-persistent-runner"),
        ("prime_roster", prime_roster, False, "inputs/source-prime-roster.bin"),
    )
    captured: dict[str, tuple[bytes, dict[str, Any], str, bool]] = {}
    for name, path, executable, relative in inputs:
        raw, pin = _safe_regular(path, name.replace("_", " "), executable=executable)
        captured[name] = (raw, pin, relative, executable)
    if not allow_bounded_test:
        roster_pin = captured["prime_roster"][1]
        if (
            roster_pin["sha256"] != SOURCE_PRIME_ROSTER_SHA256
            or roster_pin["size_bytes"] != SOURCE_PRIME_ROSTER_BYTES
        ):
            raise HurstHybridSourceError(
                "production requires the compiled canonical source-prime roster"
            )

    repository_root = Path(__file__).resolve().parents[1]
    source_paths = {
        "cpu_runner_source": repository_root
        / "reference/tg_hurst_residual_shard.cpp",
        "h100_runner_source": repository_root
        / "gpu/platform/h100/h100_tg_mobius_persistent_runner.cpp",
        "h100_persistent_source": repository_root
        / "gpu/src/tg_mobius_persistent_runner.cpp",
        "h100_runtime_policy": repository_root
        / "gpu/platform/h100/h100_runtime_policy.h",
        "h100_kernel_source": repository_root
        / "gpu/platform/h100/h100_tg_mobius_segment_kernel.cu",
        "persistent_kernel_source": repository_root
        / "gpu/src/tg_mobius_segment_kernel.cu",
        "upstream_manifest": repository_root
        / "specifications/HURST_MERTENS_UPSTREAM.json",
    }
    source_captures: dict[str, tuple[bytes, dict[str, Any], str]] = {}
    for name, path in source_paths.items():
        raw, pin = _safe_regular(
            path,
            name.replace("_", " "),
            executable=False,
            maximum_bytes=MAX_CAPTURE_BYTES,
        )
        if name == "upstream_manifest":
            _validate_upstream(raw)
        source_captures[name] = (
            raw,
            pin,
            f"source/{path.name}",
        )

    if output_directory.exists() or output_directory.is_symlink():
        raise HurstHybridSourceError("materialization output already exists")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.materializing-",
            dir=output_directory.parent,
        )
    )
    published = False
    try:
        input_pins: dict[str, Any] = {}
        for name, (raw, expected, relative, executable) in captured.items():
            destination = stage / relative
            copied = _copy_captured(destination, raw, executable=executable)
            copied["path"] = relative
            if {key: copied[key] for key in ("sha256", "size_bytes")} != expected:
                raise HurstHybridSourceError("captured input pin changed")
            input_pins[name] = copied
        source_pins: dict[str, Any] = {}
        for name, (raw, expected, relative) in source_captures.items():
            copied = _copy_captured(stage / relative, raw, executable=False)
            copied["path"] = relative
            if {key: copied[key] for key in ("sha256", "size_bytes")} != expected:
                raise HurstHybridSourceError("captured source pin changed")
            source_pins[name] = copied

        plan = {
            "classification": PLAN_CLASSIFICATION,
            "cpu": {
                "algorithm": CPU_RUNNER_ALGORITHM,
                "classification": CPU_RUNNER_CLASSIFICATION,
                "segment_rows": cpu_segment,
                "state_components": list(STATE_COMPONENTS),
                "two_pass": True,
                "upstream_commit": UPSTREAM_COMMIT,
            },
            "h100": {
                "algorithm": GPU_ALGORITHM,
                "classification": GPU_CLASSIFICATION,
                "external_cross_device_override_allowed": False,
                "expected_leaf_count": (
                    geometry["h100"]["count"] + leaf_rows - 1
                )
                // leaf_rows,
                "leaf_rows": leaf_rows,
                "required_device_class": "nvidia-h100-sm90",
                "super_shard_rows": super_rows,
            },
            "inputs": input_pins,
            "kind": PLAN_KIND,
            "mode": "bounded_test" if allow_bounded_test else "production",
            "schema_version": SCHEMA_VERSION,
            "semantic_flags": dict(SEMANTIC_FLAGS),
            "source_geometry": geometry,
            "source_pins": source_pins,
        }
        plan_raw = canonical_json_bytes(plan)
        _copy_captured(stage / "hybrid-plan.json", plan_raw, executable=False)
        plan_pin = {
            "path": "hybrid-plan.json",
            "sha256": sha256_bytes(plan_raw),
            "size_bytes": len(plan_raw),
        }
        manifest = {
            "accepted": False,
            "classification": MATERIALIZATION_CLASSIFICATION,
            "execution_completed": False,
            "kind": MATERIALIZATION_KIND,
            "lean_theorem_produced": False,
            "plan": plan_pin,
            "schema_version": SCHEMA_VERSION,
            "semantic_flags": dict(SEMANTIC_FLAGS),
            "source_run_receipt_produced": False,
        }
        manifest_raw = canonical_json_bytes(manifest)
        _copy_captured(
            stage / "materialization-manifest.json",
            manifest_raw,
            executable=False,
        )
        _fsync_directory(stage)
        _readonly_tree(stage)
        os.replace(stage, output_directory)
        published = True
        _fsync_directory(output_directory.parent)
        return {
            **manifest,
            "manifest": str(
                output_directory / "materialization-manifest.json"
            ),
            "output_directory": str(output_directory),
            "plan": {
                **plan_pin,
                "path": str(output_directory / "hybrid-plan.json"),
            },
        }
    except (CampaignIOError, OSError, ValueError) as error:
        raise HurstHybridSourceError(
            f"hybrid materialization failed closed: {error}"
        ) from error
    finally:
        if not published and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def _load_plan(root: Path) -> tuple[dict[str, Any], str]:
    if root.is_symlink() or not root.is_dir():
        raise HurstHybridSourceError(
            "materialization root must be a non-symlink directory"
    )
    plan_path = root / "hybrid-plan.json"
    manifest_path = root / "materialization-manifest.json"
    plan_raw, _ = _safe_regular(
        plan_path,
        "hybrid plan",
        executable=False,
        maximum_bytes=MAX_CAPTURE_BYTES,
    )
    manifest_raw, _ = _safe_regular(
        manifest_path,
        "materialization manifest",
        executable=False,
        maximum_bytes=MAX_CAPTURE_BYTES,
    )
    try:
        plan = parse_json_bytes(plan_raw, label="hybrid plan")
        manifest = parse_json_bytes(
            manifest_raw, label="materialization manifest"
        )
    except (CampaignIOError, OSError, ValueError) as error:
        raise HurstHybridSourceError(f"cannot load hybrid plan: {error}") from error
    if (
        plan_raw != canonical_json_bytes(plan)
        or manifest_raw != canonical_json_bytes(manifest)
    ):
        raise HurstHybridSourceError(
            "hybrid plan/materialization manifest is not canonical JSON"
        )
    _exact(plan, PLAN_FIELDS, "hybrid plan")
    _exact(manifest, MATERIALIZATION_FIELDS, "materialization manifest")
    _plain_int(plan["schema_version"], "hybrid plan schema_version")
    _plain_int(
        manifest["schema_version"],
        "materialization manifest schema_version",
    )
    if (
        plan["kind"] != PLAN_KIND
        or plan["schema_version"] != SCHEMA_VERSION
        or plan["classification"] != PLAN_CLASSIFICATION
    ):
        raise HurstHybridSourceError("hybrid plan kind/version changed")
    if plan["semantic_flags"] != SEMANTIC_FLAGS:
        raise HurstHybridSourceError("hybrid plan semantic flags changed")
    if (
        manifest["kind"] != MATERIALIZATION_KIND
        or manifest["schema_version"] != SCHEMA_VERSION
        or manifest["classification"] != MATERIALIZATION_CLASSIFICATION
        or manifest["semantic_flags"] != SEMANTIC_FLAGS
        or manifest["accepted"] is not False
        or manifest["execution_completed"] is not False
        or manifest["lean_theorem_produced"] is not False
        or manifest["source_run_receipt_produced"] is not False
    ):
        raise HurstHybridSourceError(
            "materialization manifest made an unsafe or unknown claim"
        )
    cpu_plan = _exact(plan["cpu"], CPU_PLAN_FIELDS, "CPU plan")
    h100_plan = _exact(plan["h100"], H100_PLAN_FIELDS, "H100 plan")
    if (
        cpu_plan["algorithm"] != CPU_RUNNER_ALGORITHM
        or cpu_plan["classification"] != CPU_RUNNER_CLASSIFICATION
        or cpu_plan["state_components"] != list(STATE_COMPONENTS)
        or cpu_plan["two_pass"] is not True
        or cpu_plan["upstream_commit"] != UPSTREAM_COMMIT
    ):
        raise HurstHybridSourceError("CPU plan identity changed")
    cpu_segment_rows = _plain_int(
        cpu_plan["segment_rows"], "CPU plan segment rows", minimum=1
    )
    leaf_rows = _plain_int(
        h100_plan["leaf_rows"], "H100 plan leaf rows", minimum=1
    )
    super_rows = _plain_int(
        h100_plan["super_shard_rows"],
        "H100 plan super-shard rows",
        minimum=1,
    )
    if (
        h100_plan["algorithm"] != GPU_ALGORITHM
        or h100_plan["classification"] != GPU_CLASSIFICATION
        or h100_plan["required_device_class"] != "nvidia-h100-sm90"
        or h100_plan["external_cross_device_override_allowed"] is not False
        or leaf_rows > MAX_H100_LEAF_ROWS
        or super_rows < leaf_rows
        or super_rows > MAX_H100_SUPER_SHARD_ROWS
        or super_rows % leaf_rows != 0
    ):
        raise HurstHybridSourceError("H100 plan identity/geometry changed")
    geometry = _exact(
        plan["source_geometry"], GEOMETRY_FIELDS, "source geometry"
    )
    for name in ("source_lower", "source_upper_exclusive", "split"):
        _plain_int(geometry[name], f"source geometry.{name}")
    cpu = _exact(geometry["cpu"], RANGE_FIELDS, "CPU range")
    gpu = _exact(geometry["h100"], RANGE_FIELDS, "H100 range")
    for row, what in ((cpu, "CPU"), (gpu, "H100")):
        lower = _plain_int(row["lower"], f"{what} lower", minimum=1)
        upper = _plain_int(
            row["upper_exclusive"], f"{what} upper", minimum=2
        )
        count = _plain_int(row["count"], f"{what} count", minimum=1)
        if count != upper - lower or upper <= lower:
            raise HurstHybridSourceError(f"{what} range count changed")
    if (
        cpu["lower"] != SOURCE_LOWER
        or geometry["source_lower"] != cpu["lower"]
        or geometry["split"] != cpu["upper_exclusive"]
        or geometry["split"] != gpu["lower"]
        or geometry["source_upper_exclusive"] != gpu["upper_exclusive"]
        or geometry["gap_free"] is not True
    ):
        raise HurstHybridSourceError("hybrid geometry has a gap or overlap")
    production = (
        cpu["lower"] == SOURCE_LOWER
        and cpu["upper_exclusive"] == CPU_UPPER_EXCLUSIVE
        and gpu["lower"] == H100_LOWER
        and gpu["upper_exclusive"] == SOURCE_UPPER_EXCLUSIVE
    )
    if (plan["mode"] == "production") != production:
        raise HurstHybridSourceError("hybrid plan mode/geometry disagree")
    if plan["mode"] not in ("production", "bounded_test"):
        raise HurstHybridSourceError("hybrid plan mode changed")
    if not production and gpu["upper_exclusive"] - cpu["lower"] > 64:
        raise HurstHybridSourceError("bounded-test geometry exceeds 64 rows")
    if cpu_segment_rows > MAX_SEGMENT_SIZE:
        raise HurstHybridSourceError(
            "CPU plan segment rows exceed the runner limit"
        )
    if cpu_segment_rows < MIN_SEGMENT_SIZE:
        raise HurstHybridSourceError(
            "CPU plan segment rows are below the reviewed runner minimum"
        )
    expected_leaves = (gpu["count"] + leaf_rows - 1) // leaf_rows
    if (
        _plain_int(
            h100_plan["expected_leaf_count"],
            "H100 expected leaf count",
            minimum=1,
        )
        != expected_leaves
    ):
        raise HurstHybridSourceError("H100 expected leaf count changed")

    expected_names = {
        "inputs": INPUT_NAMES,
        "source_pins": SOURCE_PIN_NAMES,
    }
    expected_paths = {
        "inputs": {
            "cpu_runner": "inputs/cpu-hurst-runner",
            "h100_runner": "inputs/h100-persistent-runner",
            "prime_roster": "inputs/source-prime-roster.bin",
        },
        "source_pins": {
            "cpu_runner_source": "source/tg_hurst_residual_shard.cpp",
            "h100_kernel_source":
                "source/h100_tg_mobius_segment_kernel.cu",
            "h100_persistent_source":
                "source/tg_mobius_persistent_runner.cpp",
            "h100_runner_source":
                "source/h100_tg_mobius_persistent_runner.cpp",
            "h100_runtime_policy": "source/h100_runtime_policy.h",
            "persistent_kernel_source":
                "source/tg_mobius_segment_kernel.cu",
            "upstream_manifest": "source/HURST_MERTENS_UPSTREAM.json",
        },
    }
    for section in ("inputs", "source_pins"):
        if (
            not isinstance(plan[section], dict)
            or set(plan[section]) != expected_names[section]
        ):
            raise HurstHybridSourceError(f"{section} is malformed")
        for name, raw_pin in plan[section].items():
            pin = _exact(raw_pin, PIN_FIELDS, f"{section}.{name}")
            if pin["path"] != expected_paths[section][name]:
                raise HurstHybridSourceError(
                    f"captured path changed: {section}.{name}"
                )
            _digest(pin["sha256"], f"{section}.{name}.sha256", nonzero=True)
            _plain_int(
                pin["size_bytes"],
                f"{section}.{name}.size_bytes",
                minimum=1,
            )
            relative = Path(pin["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise HurstHybridSourceError("captured path escapes root")
            path = root / relative
            try:
                metadata = path.lstat()
            except OSError as error:
                raise HurstHybridSourceError(
                    f"cannot inspect captured identity: {section}.{name}"
                ) from error
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                raise HurstHybridSourceError(
                    "captured identity is not one unlinked regular file: "
                    f"{section}.{name}"
                )
            if (
                section == "inputs"
                and name in ("cpu_runner", "h100_runner")
                and not metadata.st_mode & stat.S_IXUSR
            ):
                raise HurstHybridSourceError(
                    f"captured runner is not executable: {name}"
                )
            try:
                digest, size = hash_file_once(path, limit=MAX_INPUT_BYTES)
            except CampaignIOError as error:
                raise HurstHybridSourceError(str(error)) from error
            if (digest, size) != (pin["sha256"], pin["size_bytes"]):
                raise HurstHybridSourceError(
                    f"captured identity changed: {section}.{name}"
                )
    if production:
        roster_pin = plan["inputs"]["prime_roster"]
        if (
            roster_pin["sha256"] != SOURCE_PRIME_ROSTER_SHA256
            or roster_pin["size_bytes"] != SOURCE_PRIME_ROSTER_BYTES
        ):
            raise HurstHybridSourceError(
                "production plan lost the canonical source-prime roster"
            )
    plan_pin = _exact(manifest["plan"], PIN_FIELDS, "manifest plan pin")
    if (
        plan_pin["path"] != "hybrid-plan.json"
        or plan_pin["sha256"] != sha256_bytes(plan_raw)
        or plan_pin["size_bytes"] != len(plan_raw)
    ):
        raise HurstHybridSourceError("materialization manifest plan pin changed")
    upstream_relative = Path(
        plan["source_pins"]["upstream_manifest"]["path"]
    )
    upstream_raw, _ = _safe_regular(
        root / upstream_relative,
        "captured upstream manifest",
        executable=False,
        maximum_bytes=MAX_CAPTURE_BYTES,
    )
    _validate_upstream(upstream_raw)
    return dict(plan), sha256_bytes(plan_raw)


def _fixed_environment() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/local/cuda/bin:/usr/bin:/bin",
        "TZ": "UTC",
    }


def _prime_roster_values(
    *,
    raw: bytes | None,
    expected_sha256: str,
    source_upper_exclusive: int,
    production: bool,
) -> Sequence[int]:
    if production:
        if raw is None:
            raise HurstHybridSourceError(
                "canonical source-prime roster bytes are unavailable"
            )
        if (
            sha256_bytes(raw) != expected_sha256
            or expected_sha256 != SOURCE_PRIME_ROSTER_SHA256
            or len(raw) != SOURCE_PRIME_ROSTER_BYTES
            or array("I").itemsize != 4
        ):
            raise HurstHybridSourceError(
                "canonical source-prime roster identity changed"
            )
        values = array("I")
        values.frombytes(raw)
        if sys.byteorder != "little":
            values.byteswap()
        if (
            len(values) != SOURCE_PRIME_ROSTER_COUNT
            or values[0] != 2
            or values[-1] != 99_999_989
        ):
            raise HurstHybridSourceError(
                "canonical source-prime roster shape changed"
            )
        return values

    limit = math.isqrt(source_upper_exclusive - 1)
    values: list[int] = []
    for candidate in range(2, limit + 1):
        if all(candidate % prime for prime in values if prime * prime <= candidate):
            values.append(candidate)
    return values


def _expected_selected_prime_counts(
    primes: Sequence[int],
    *,
    super_lower: int,
    super_count: int,
    source_fast_path: bool,
) -> tuple[int, int]:
    super_upper = super_lower + super_count
    prime_end = bisect_right(primes, math.isqrt(super_upper - 1))
    dense_limit = 1 + (super_count - 1) // 256
    if source_fast_path:
        return (
            prime_end,
            bisect_right(primes, dense_limit, 0, prime_end),
        )
    selected: list[int] = []
    for index in range(prime_end):
        prime = primes[index]
        first_offset = (-super_lower) % prime
        if index < 3 or first_offset < super_count:
            selected.append(prime)
    return len(selected), bisect_right(selected, dense_limit)


def _run_cpu(
    argv: Sequence[str],
    *,
    timeout_seconds: int,
    pass_fds: Sequence[int] = (),
) -> tuple[dict[str, Any], bytes, bytes]:
    timeout = _plain_int(
        timeout_seconds, "CPU timeout seconds", minimum=1
    )
    try:
        completed = subprocess.run(
            list(argv),
            env=_fixed_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            pass_fds=tuple(pass_fds),
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HurstHybridSourceError(f"CPU runner failed: {error}") from error
    if (
        len(completed.stdout) > MAX_RECEIPT_BYTES
        or len(completed.stderr) > MAX_STDERR_BYTES
    ):
        raise HurstHybridSourceError("CPU runner output exceeds capture limit")
    if completed.returncode != 0:
        raise HurstHybridSourceError(
            f"CPU runner exited {completed.returncode}"
        )
    try:
        report = load_decimal_json_bytes(
            completed.stdout, label="CPU Hurst receipt"
        )
    except EvidenceError as error:
        raise HurstHybridSourceError(str(error)) from error
    if not isinstance(report, dict):
        raise HurstHybridSourceError("CPU runner did not emit one JSON object")
    return report, completed.stdout, completed.stderr


def _cpu_command(
    runner: Path,
    *,
    phase: str,
    lower: int,
    upper_exclusive: int,
    segment_rows: int,
    incoming: Sequence[int] | None,
) -> tuple[str, ...]:
    command = [
        str(runner),
        "--lower",
        str(lower),
        "--upper",
        str(upper_exclusive - 1),
        "--segment-size",
        str(segment_rows),
        "--mode",
        phase,
    ]
    if phase == "verify":
        if incoming is None or len(incoming) != 4:
            raise HurstHybridSourceError(
                "CPU verify command requires four incoming coordinates"
            )
        for flag, value in zip(
            (
                "--incoming-mertens",
                "--incoming-squarefree",
                "--incoming-little-lower",
                "--incoming-little-upper",
            ),
            incoming,
            strict=True,
        ):
            command.extend((flag, str(value)))
    return tuple(command)


def _validate_cpu_numeric_types(
    report: Mapping[str, Any], what: str
) -> None:
    for name in (
        "lower",
        "upper_exclusive",
        "work_count",
        "segment_size",
        "segments",
        "reduction_block_rows",
    ):
        if name not in report:
            raise HurstHybridSourceError(
                f"{what} is missing numeric field {name}"
            )
        _plain_int(report[name], f"{what}.{name}")
    fallbacks = report.get("exact_fallbacks")
    if isinstance(fallbacks, Mapping):
        for name, value in fallbacks.items():
            _plain_int(value, f"{what}.exact_fallbacks.{name}")


def _cpu_handoff(
    *,
    plan_sha256: str,
    geometry: Mapping[str, Any],
    runner_sha256: str,
    summary_raw: bytes,
    verify_raw: bytes,
    report: Mapping[str, Any],
    outgoing: Sequence[int],
) -> dict[str, Any]:
    payload = {
        "classification": (
            "cpu_arithmetic_handoff_not_attestation_semantic_evidence_"
            "or_lean_proof"
        ),
        "cpu_range": dict(geometry["cpu"]),
        "kind": CPU_HANDOFF_KIND,
        "outgoing_state": list(outgoing),
        "plan_sha256": plan_sha256,
        "row_sha256": report["row_sha256"],
        "runner_sha256": runner_sha256,
        "schema_version": SCHEMA_VERSION,
        "semantic_flags": dict(SEMANTIC_FLAGS),
        "state_components": list(STATE_COMPONENTS),
        "summary_receipt_sha256": sha256_bytes(summary_raw),
        "verify_receipt_sha256": sha256_bytes(verify_raw),
    }
    chain = hashlib.sha256(HANDOFF_DOMAIN + canonical_json_bytes(payload)).hexdigest()
    return {**payload, "receipt_chain_sha256": chain}


def _json_line(raw: bytes, what: str) -> dict[str, Any]:
    if not raw or len(raw) > MAX_JSONL_LINE_BYTES or not raw.endswith(b"\n"):
        raise HurstHybridSourceError(f"{what} line framing is malformed")
    try:
        text = raw.decode("utf-8")

        def reject_duplicates(
            pairs: list[tuple[str, Any]],
        ) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key {key!r}")
                result[key] = value
            return result

        value = json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_float=Decimal,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"forbidden constant {token}")
            ),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise HurstHybridSourceError(f"{what} is not strict JSON") from error
    if not isinstance(value, dict):
        raise HurstHybridSourceError(f"{what} is not an object")
    return value


def _false_flags(record: Mapping[str, Any], *, primitive: bool) -> None:
    fields = {
        "source_rows_replayed_independently": False,
        "execution_attested": False,
        "cuda_or_cpp_compiler_refinement_proved": False,
        "lean_atom_discharged": False,
        "proves_any_external_atom": False,
    }
    if primitive:
        fields["primitive_mobius_realization_proved"] = False
    for name, expected in fields.items():
        if record.get(name) is not expected:
            raise HurstHybridSourceError(
                f"GPU receipt made an unsafe claim in {name}"
            )


def _leaf_bound(
    value: Any,
    *,
    lower: int,
    upper_exclusive: int,
    endpoint_side: bool,
    what: str,
) -> tuple[int, int, str]:
    fields = {"value", "witness_y", "side"} if endpoint_side else {
        "value",
        "witness_y",
    }
    row = _exact(value, fields, what)
    bound = _signed_64(row["value"], f"{what}.value")
    witness = _unsigned_64(row["witness_y"], f"{what}.witness_y")
    if witness < lower:
        raise HurstHybridSourceError(
            f"{what}.witness_y must be at least {lower}"
        )
    side = "integer"
    if endpoint_side:
        side = row["side"]
        if side not in ("integer", "right_limit"):
            raise HurstHybridSourceError(f"{what} side is malformed")
    if (
        (side == "integer" and witness >= upper_exclusive)
        or (side == "right_limit"
            and (witness <= lower or witness > upper_exclusive))
    ):
        raise HurstHybridSourceError(f"{what} witness escapes its leaf")
    return bound, witness, side


def _leaf_digest(
    record: Mapping[str, Any],
    *,
    executable_sha256: str,
    roster_sha256: str,
) -> str:
    square_lower_order = 2 * (
        record["squarefree_lower"]["witness_y"] - record["lower"]
    ) - (record["squarefree_lower"]["side"] == "right_limit")
    square_upper_order = 2 * (
        record["squarefree_upper"]["witness_y"] - record["lower"]
    ) - (record["squarefree_upper"]["side"] == "right_limit")
    text = (
        "domain=sparkinterval.tg.mobius-persistent-leaf.v1\n"
        f"algorithm={GPU_ALGORITHM}\n"
        f"executable_sha256={executable_sha256}\n"
        f"prime_roster_sha256={roster_sha256}\n"
        f"previous={record['previous_leaf_sha256']}\n"
        f"lower={record['lower']}\n"
        f"upper_exclusive={record['upper_exclusive']}\n"
        "poison_count=0\n"
        f"incoming_mertens={record['incoming_mertens']}\n"
        f"outgoing_mertens={record['outgoing_mertens']}\n"
        f"delta_mertens={record['delta_mertens']}\n"
        f"incoming_squarefree={record['incoming_squarefree']}\n"
        f"outgoing_squarefree={record['outgoing_squarefree']}\n"
        f"delta_squarefree={record['delta_squarefree']}\n"
        f"hurst_lower={record['hurst_lower']['value']}\n"
        f"hurst_lower_y={record['hurst_lower']['witness_y']}\n"
        f"hurst_upper={record['hurst_upper']['value']}\n"
        f"hurst_upper_y={record['hurst_upper']['witness_y']}\n"
        f"squarefree_lower={record['squarefree_lower']['value']}\n"
        f"squarefree_lower_y={record['squarefree_lower']['witness_y']}\n"
        f"squarefree_lower_order={square_lower_order}\n"
        f"squarefree_upper={record['squarefree_upper']['value']}\n"
        f"squarefree_upper_y={record['squarefree_upper']['witness_y']}\n"
        f"squarefree_upper_order={square_upper_order}\n"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _select_extreme(
    current: tuple[int, int, int, str] | None,
    candidate: tuple[int, int, int, str],
    *,
    maximum: bool,
) -> tuple[int, int, int, str]:
    if current is None:
        return candidate
    current_key = (
        -current[0] if maximum else current[0],
        current[2],
    )
    candidate_key = (
        -candidate[0] if maximum else candidate[0],
        candidate[2],
    )
    return candidate if candidate_key < current_key else current


def _global_bound(
    value: Any,
    *,
    endpoint_side: bool,
    what: str,
) -> tuple[int, int, int, str]:
    fields = (
        {"value", "witness_y", "source_order", "side"}
        if endpoint_side
        else {"value", "witness_y", "source_order"}
    )
    row = _exact(value, fields, what)
    side = row.get("side", "integer")
    if side not in ("integer", "right_limit"):
        raise HurstHybridSourceError(f"{what} side changed")
    return (
        _signed_64(row["value"], f"{what}.value"),
        _unsigned_64(row["witness_y"], f"{what}.witness_y"),
        _unsigned_64(row["source_order"], f"{what}.source_order"),
        side,
    )


def _validate_header(
    header: Mapping[str, Any],
    *,
    gpu_range: Mapping[str, Any],
    leaf_rows: int,
    super_rows: int,
    runner_sha256: str,
    roster_sha256: str,
    roster_device_bytes: int,
) -> None:
    _exact(header, GPU_HEADER_FIELDS, "GPU header")
    _require_integer_fields(
        header, GPU_HEADER_INTEGER_FIELDS, "GPU header"
    )
    _digest(
        header["executable_sha256"],
        "GPU header executable_sha256",
        nonzero=True,
    )
    _digest(
        header["prime_roster_sha256"],
        "GPU header prime_roster_sha256",
        nonzero=True,
    )
    if (
        header["record"] != "header"
        or header["schema"] != GPU_SCHEMA
        or header["algorithm"] != GPU_ALGORITHM
        or header["classification"] != GPU_CLASSIFICATION
        or (header["lower"], header["upper_exclusive"], header["count"])
        != (
            gpu_range["lower"],
            gpu_range["upper_exclusive"],
            gpu_range["count"],
        )
        or header["shard_rows"] != leaf_rows
        or header["super_shard_rows"] != super_rows
        or header["executable_sha256"] != runner_sha256
        or header["prime_roster_sha256"] != roster_sha256
    ):
        raise HurstHybridSourceError("GPU header identity/geometry changed")
    required_true = (
        "fused_support_load_balanced_dense_schedule",
        "fused_support_residue_235_initializer",
        "leaf_chain_binds_compact_gpu_summary",
        "host_rechecks_final_squarefree_winners",
        "little_mertens_deltas_are_exact_zero",
        "production_fused_prefix_input_path",
        "production_split_square_support_path",
        "separate_square_strike_pass",
    )
    if any(header[name] is not True for name in required_true):
        raise HurstHybridSourceError("GPU header lost a required invariant")
    required_false = (
        "production_mu_rows_transferred",
        "production_mu_rows_hashed",
        "inline_square_modulo_reference_path",
        "distinct_factor_events_compute_square_modulo",
        "intermediate_mobius_device_rows_materialized",
        "mu_row_commitment_present_in_production",
        "qualification_mu_output",
        "full_source_range",
    )
    if any(header[name] is not False for name in required_false):
        raise HurstHybridSourceError("GPU header entered qualification/claim mode")
    if (
        header["split_square_dense_prime_limit"] != 200
        or header["split_square_operation_order"]
        != "initialize_then_distinct_then_square_then_finalize"
    ):
        raise HurstHybridSourceError(
            "GPU split-square schedule identity changed"
        )
    if any(
        header[name] != 1
        for name in (
            "prime_roster_load_count",
            "prime_roster_upload_count",
            "cuda_allocation_epoch_count",
            "cuda_event_set_count",
        )
    ):
        raise HurstHybridSourceError("GPU persistent resource identity changed")
    fixed_geometry = {
        "residue_235_initializer_table_rows": 900,
        "residue_235_initializer_table_bytes": 7_200,
        "residue_235_explicit_h2d_upload_bytes_per_sieve": 0,
        "fused_multiblock_dense_prime_limit": 200,
        "fused_multiblock_slots_per_prime": 512,
        "fused_multiblock_unseeded_slots_per_prime": 512,
        "fused_multiblock_residue_235_slots_per_prime": 512,
        "fused_multiblock_residue_235_minimum_safe_slots_per_prime": 147,
        "fused_multiblock_iterations_per_thread": 4_096,
        "affine_candidates_transferred_per_leaf": 1,
        "affine_candidate_bytes_per_leaf": 64,
        "production_device_to_host_bytes_per_leaf": 76,
        "production_mu_rows_transferred": False,
        "production_mu_rows_hashed": False,
    }
    if any(header[name] != value for name, value in fixed_geometry.items()):
        raise HurstHybridSourceError("GPU header fixed geometry changed")
    if (
        header["residue_235_table_storage"]
        != "fatbinary_device_global_init"
        or header["residue_235_table_materialization_scope"]
        != "cuda_module_context_load"
    ):
        raise HurstHybridSourceError(
            "GPU residue-235 materialization identity changed"
        )
    for name in (
        "affine_prefix_device_bytes",
        "affine_workspace_device_bytes",
        "fused_support_device_bytes",
        "mobius_device_bytes",
        "persistent_device_allocation_bytes",
        "device_free_bytes_before_allocation",
        "device_total_bytes",
    ):
        _plain_int(header[name], f"GPU header {name}", minimum=0)
    if (
        header["affine_prefix_device_bytes"]
        != min(gpu_range["count"], leaf_rows) * 8
        or header["fused_support_device_bytes"]
        != min(gpu_range["count"], super_rows) * 8
        or header["mobius_device_bytes"] != 0
        or header["persistent_device_allocation_bytes"]
        > header["device_total_bytes"]
        or header["persistent_device_allocation_bytes"]
        > header["device_free_bytes_before_allocation"]
        or header["device_free_bytes_before_allocation"]
        > header["device_total_bytes"]
    ):
        raise HurstHybridSourceError("GPU header allocation geometry changed")
    expected_allocation = (
        2 * roster_device_bytes
        + header["fused_support_device_bytes"]
        + header["mobius_device_bytes"]
        + header["affine_prefix_device_bytes"]
        + 64
        + 4
        + header["affine_workspace_device_bytes"]
    )
    if (
        header["affine_workspace_device_bytes"] <= 0
        or header["persistent_device_allocation_bytes"]
        != expected_allocation
        or header["persistent_device_allocation_bytes"] <= 0
    ):
        raise HurstHybridSourceError(
            "GPU header persistent allocation does not replay"
        )
    for name in (
        "roster_load_milliseconds",
        "allocation_milliseconds",
        "roster_upload_milliseconds",
    ):
        _nonnegative_decimal_text(header[name], f"GPU header {name}")
    _false_flags(header, primitive=True)


def _validate_leaf(
    leaf: Mapping[str, Any],
    *,
    index: int,
    expected_lower: int,
    expected_previous: str,
    expected_mertens: int,
    expected_squarefree: int,
    root_mertens: int,
    root_squarefree: int,
    source_lower: int,
    leaf_rows: int,
    super_rows: int,
    source_upper: int,
    executable_sha256: str,
    roster_sha256: str,
    expected_selected_prime_count: int,
    expected_dense_prime_count: int,
) -> tuple[
    int,
    int,
    str,
    dict[str, tuple[int, int, int, str]],
    bool,
    int,
]:
    _exact(leaf, GPU_LEAF_FIELDS, f"GPU leaf {index}")
    _require_integer_fields(
        leaf, GPU_LEAF_INTEGER_FIELDS, f"GPU leaf {index}"
    )
    _digest(
        leaf["previous_leaf_sha256"],
        f"GPU leaf {index} previous_leaf_sha256",
        nonzero=True,
    )
    _digest(
        leaf["leaf_sha256"],
        f"GPU leaf {index} leaf_sha256",
        nonzero=True,
    )
    count = min(leaf_rows, source_upper - expected_lower)
    upper = expected_lower + count
    super_index = (expected_lower - source_lower) // super_rows
    super_lower = source_lower + super_index * super_rows
    super_upper = min(source_upper, super_lower + super_rows)
    super_count = super_upper - super_lower
    super_leaf_index = (expected_lower - super_lower) // leaf_rows
    source_fast_path = super_count >= math.isqrt(super_upper - 1)
    if (
        leaf["record"] != "leaf"
        or leaf["index"] != index
        or leaf["lower"] != expected_lower
        or leaf["upper_exclusive"] != upper
        or leaf["count"] != count
        or leaf["previous_leaf_sha256"] != expected_previous
        or leaf["incoming_mertens"] != expected_mertens
        or leaf["incoming_squarefree"] != expected_squarefree
    ):
        raise HurstHybridSourceError("GPU leaf chain geometry/state changed")
    for name in (
        "incoming_mertens",
        "outgoing_mertens",
        "delta_mertens",
    ):
        _signed_64(leaf[name], f"GPU leaf {index} {name}")
    for name in (
        "incoming_squarefree",
        "outgoing_squarefree",
        "delta_squarefree",
    ):
        _unsigned_64(leaf[name], f"GPU leaf {index} {name}")
    if (
        leaf["outgoing_mertens"]
        != leaf["incoming_mertens"] + leaf["delta_mertens"]
        or leaf["outgoing_squarefree"]
        != leaf["incoming_squarefree"] + leaf["delta_squarefree"]
        or not -count <= leaf["delta_mertens"] <= count
        or not 0 <= leaf["delta_squarefree"] <= count
        or not -(expected_lower - 1)
        <= leaf["incoming_mertens"]
        <= expected_lower - 1
        or leaf["incoming_squarefree"] > expected_lower - 1
        or not -(upper - 1)
        <= leaf["outgoing_mertens"]
        <= upper - 1
        or leaf["outgoing_squarefree"] > upper - 1
    ):
        raise HurstHybridSourceError("GPU leaf state recurrence changed")
    if (
        leaf["qualification_mu_plus_one_sha256"] is not None
        or leaf["qualification_device_to_host_mu_bytes"] != 0
        or leaf["mu_row_commitment_present"] is not False
        or leaf["poison_count"] != 0
        or leaf["production_device_to_host_bytes"] != 76
    ):
        raise HurstHybridSourceError("GPU leaf entered qualification/poison mode")
    if (
        leaf["source_prime_fast_path"] is not source_fast_path
        or leaf["super_shard_index"] != super_index
        or leaf["super_shard_leaf_index"] != super_leaf_index
        or leaf["super_shard_lower"] != super_lower
        or leaf["super_shard_upper_exclusive"] != super_upper
        or leaf["super_shard_count"] != super_count
        or leaf["affine_candidate_bytes_transferred"] != 64
    ):
        raise HurstHybridSourceError("GPU leaf super-shard geometry changed")
    selected_primes = _plain_int(
        leaf["selected_prime_count"],
        f"GPU leaf {index} selected_prime_count",
        minimum=3,
    )
    dense_primes = _plain_int(
        leaf["dense_prime_count"],
        f"GPU leaf {index} dense_prime_count",
        minimum=0,
    )
    if (
        selected_primes != expected_selected_prime_count
        or dense_primes != expected_dense_prime_count
        or dense_primes > selected_primes
    ):
        raise HurstHybridSourceError(
            "GPU leaf selected/dense-prime counts changed"
        )
    for name in (
        "active_prime_filter_milliseconds",
        "active_prime_upload_milliseconds",
        "kernel_milliseconds",
        "super_shard_sieve_kernel_milliseconds",
        "affine_milliseconds",
        "transfer_milliseconds",
        "control_loop_milliseconds",
    ):
        _nonnegative_decimal_text(
            leaf[name], f"GPU leaf {index} {name}"
        )
    _false_flags(leaf, primitive=False)
    bounds = {
        "hurst_lower": _leaf_bound(
            leaf["hurst_lower"],
            lower=expected_lower,
            upper_exclusive=upper,
            endpoint_side=False,
            what=f"GPU leaf {index} hurst_lower",
        ),
        "hurst_upper": _leaf_bound(
            leaf["hurst_upper"],
            lower=expected_lower,
            upper_exclusive=upper,
            endpoint_side=False,
            what=f"GPU leaf {index} hurst_upper",
        ),
        "squarefree_lower": _leaf_bound(
            leaf["squarefree_lower"],
            lower=expected_lower,
            upper_exclusive=upper,
            endpoint_side=True,
            what=f"GPU leaf {index} squarefree_lower",
        ),
        "squarefree_upper": _leaf_bound(
            leaf["squarefree_upper"],
            lower=expected_lower,
            upper_exclusive=upper,
            endpoint_side=True,
            what=f"GPU leaf {index} squarefree_upper",
        ),
    }
    for name, (value, witness, side) in tuple(bounds.items()):
        relative = (
            leaf["incoming_mertens"] - root_mertens
            if name.startswith("hurst")
            else leaf["incoming_squarefree"] - root_squarefree
        )
        order = (
            2 * (witness - source_lower)
            - (side == "right_limit")
        )
        bounds[name] = (value - relative, witness, order, side)
    expected_digest = _leaf_digest(
        leaf,
        executable_sha256=executable_sha256,
        roster_sha256=roster_sha256,
    )
    if leaf["leaf_sha256"] != expected_digest:
        raise HurstHybridSourceError("GPU leaf digest does not replay")
    return (
        leaf["outgoing_mertens"],
        leaf["outgoing_squarefree"],
        expected_digest,
        bounds,
        source_fast_path,
        super_index,
    )


def _validate_terminal(
    terminal: Mapping[str, Any],
    *,
    gpu_range: Mapping[str, Any],
    leaf_rows: int,
    super_rows: int,
    leaf_count: int,
    first_mertens: int,
    first_squarefree: int,
    final_mertens: int,
    final_squarefree: int,
    final_leaf: str,
    extrema: Mapping[str, tuple[int, int, int, str] | None],
    source_fast_leaf_count: int,
    source_fast_super_shard_count: int,
) -> None:
    _exact(terminal, GPU_TERMINAL_FIELDS, "GPU terminal")
    _require_integer_fields(
        terminal, GPU_TERMINAL_INTEGER_FIELDS, "GPU terminal"
    )
    _digest(
        terminal["final_leaf_sha256"],
        "GPU terminal final_leaf_sha256",
        nonzero=True,
    )
    expected_super_shards = (
        gpu_range["count"] + super_rows - 1
    ) // super_rows
    if (
        terminal["record"] != "terminal"
        or terminal["algorithm"] != GPU_ALGORITHM
        or terminal["classification"] != GPU_CLASSIFICATION
        or (terminal["lower"], terminal["upper_exclusive"], terminal["count"])
        != (
            gpu_range["lower"],
            gpu_range["upper_exclusive"],
            gpu_range["count"],
        )
        or terminal["leaf_count"] != leaf_count
        or terminal["receipt_leaf_count"] != leaf_count
        or terminal["final_leaf_sha256"] != final_leaf
        or terminal["incoming_mertens"] != first_mertens
        or terminal["incoming_squarefree"] != first_squarefree
        or terminal["outgoing_mertens"] != final_mertens
        or terminal["outgoing_squarefree"] != final_squarefree
        or terminal["delta_mertens"] != final_mertens - first_mertens
        or terminal["delta_squarefree"]
        != final_squarefree - first_squarefree
        or terminal["super_shard_rows"] != super_rows
        or terminal["source_fast_path_leaf_count"]
        != source_fast_leaf_count
        or terminal["source_fast_path_super_shard_count"]
        != source_fast_super_shard_count
        or terminal["super_shard_count"] != expected_super_shards
        or terminal["sieve_launch_count"] != expected_super_shards
        or terminal["sieve_launches_saved_vs_leaf_schedule"]
        != leaf_count - expected_super_shards
    ):
        raise HurstHybridSourceError("GPU terminal geometry/state changed")
    if (
        terminal["little_mertens_lower_delta"] != 0
        or terminal["little_mertens_upper_delta"] != 0
        or terminal["production_mu_row_commitment_present"] is not False
        or terminal["production_mu_rows_transferred"] is not False
        or terminal["production_mu_rows_hashed"] is not False
        or terminal["full_source_range"] is not False
        or terminal["checkpoint_restart_fields_emitted_per_leaf"] is not True
        or terminal["buffers_reused_across_all_leaves"] is not True
        or terminal["leaf_chain_binds_compact_gpu_summary"] is not True
        or terminal["host_rechecks_final_squarefree_winners"] is not True
        or terminal["roster_load_count"] != 1
        or terminal["roster_upload_count"] != 1
        or terminal["allocation_epoch_count"] != 1
        or terminal["event_set_count"] != 1
        or terminal["affine_candidates_transferred_per_leaf"] != 1
        or terminal["affine_candidate_bytes_per_leaf"] != 64
        or terminal["production_device_to_host_bytes_per_leaf"] != 76
    ):
        raise HurstHybridSourceError("GPU terminal invariant changed")
    for name in (
        "active_filter_milliseconds",
        "active_prime_upload_milliseconds",
        "kernel_milliseconds",
        "affine_milliseconds",
        "transfer_milliseconds",
        "control_loop_milliseconds",
        "process_milliseconds",
    ):
        _nonnegative_decimal_text(
            terminal[name], f"GPU terminal {name}"
        )
    _false_flags(terminal, primitive=True)
    if (
        extrema["hurst_lower"] is None
        or extrema["hurst_upper"] is None
        or extrema["squarefree_lower"] is None
        or extrema["squarefree_upper"] is None
        or not (
            extrema["hurst_lower"][0]
            <= first_mertens
            <= extrema["hurst_upper"][0]
        )
        or not (
            extrema["squarefree_lower"][0]
            <= first_squarefree
            <= extrema["squarefree_upper"][0]
        )
    ):
        raise HurstHybridSourceError(
            "CPU handoff state is outside the replayed GPU affine guards"
        )
    for name in (
        "hurst_lower",
        "hurst_upper",
        "squarefree_lower",
        "squarefree_upper",
    ):
        expected = extrema[name]
        if expected is None:
            raise HurstHybridSourceError("GPU terminal omitted an extremum")
        actual = _global_bound(
            terminal[f"global_{name}"],
            endpoint_side=name.startswith("squarefree"),
            what=f"GPU terminal global_{name}",
        )
        if actual != expected:
            raise HurstHybridSourceError(
                f"GPU terminal global_{name} does not replay"
            )


def _run_h100(
    argv: Sequence[str],
    *,
    output: BinaryIO,
    stderr_path: Path,
    gpu_range: Mapping[str, Any],
    leaf_rows: int,
    super_rows: int,
    initial_digest: str,
    initial_state: Sequence[int],
    runner_sha256: str,
    roster_sha256: str,
    prime_roster: Sequence[int],
    timeout_seconds: int,
    pass_fds: Sequence[int] = (),
) -> tuple[dict[str, Any], int]:
    timeout = _plain_int(
        timeout_seconds, "H100 timeout seconds", minimum=1
    )
    stderr_file = stderr_path.open("w+b")
    process: subprocess.Popen[bytes] | None = None
    try:
        try:
            process = subprocess.Popen(
                list(argv),
                env=_fixed_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                pass_fds=tuple(pass_fds),
            )
        except OSError as error:
            raise HurstHybridSourceError(
                f"cannot launch H100 runner: {error}"
            ) from error
        if process.stdout is None:
            process.kill()
            process.wait()
            raise HurstHybridSourceError("H100 runner stdout is unavailable")

        deadline = time.monotonic() + timeout
        digest = hashlib.sha256()
        expected_lower = gpu_range["lower"]
        previous = initial_digest
        current_mertens = initial_state[0]
        current_squarefree = initial_state[1]
        header: dict[str, Any] | None = None
        terminal: dict[str, Any] | None = None
        leaf_count = 0
        source_fast_leaf_count = 0
        source_fast_super_shard_count = 0
        last_source_fast_super: int | None = None
        prime_count_super_index: int | None = None
        expected_selected_prime_count = 0
        expected_dense_prime_count = 0
        roster_device_bytes = (
            bisect_right(
                prime_roster,
                math.isqrt(gpu_range["upper_exclusive"] - 1),
            )
            * 4
        )
        extrema: dict[str, tuple[int, int, int, str] | None] = {
            "hurst_lower": None,
            "hurst_upper": None,
            "squarefree_lower": None,
            "squarefree_upper": None,
        }

        def consume_line(raw: bytes) -> None:
            nonlocal current_mertens
            nonlocal current_squarefree
            nonlocal expected_lower
            nonlocal header
            nonlocal last_source_fast_super
            nonlocal leaf_count
            nonlocal previous
            nonlocal prime_count_super_index
            nonlocal expected_dense_prime_count
            nonlocal expected_selected_prime_count
            nonlocal source_fast_leaf_count
            nonlocal source_fast_super_shard_count
            nonlocal terminal

            if len(raw) > MAX_JSONL_LINE_BYTES:
                raise HurstHybridSourceError(
                    "H100 JSONL line is oversized"
                )
            output.write(raw)
            digest.update(raw)
            record = _json_line(raw, "H100 receipt")
            kind = record.get("record")
            if header is None:
                if kind != "header":
                    raise HurstHybridSourceError("H100 header is missing")
                header = record
                _validate_header(
                    header,
                    gpu_range=gpu_range,
                    leaf_rows=leaf_rows,
                    super_rows=super_rows,
                    runner_sha256=runner_sha256,
                    roster_sha256=roster_sha256,
                    roster_device_bytes=roster_device_bytes,
                )
                return
            if kind == "terminal":
                if terminal is not None:
                    raise HurstHybridSourceError(
                        "duplicate H100 terminal"
                    )
                terminal = record
                return
            if terminal is not None or kind != "leaf":
                raise HurstHybridSourceError(
                    "H100 records after terminal or unknown record kind"
                )
            candidate_super_index = (
                expected_lower - gpu_range["lower"]
            ) // super_rows
            if candidate_super_index != prime_count_super_index:
                candidate_super_lower = (
                    gpu_range["lower"]
                    + candidate_super_index * super_rows
                )
                candidate_super_count = min(
                    super_rows,
                    gpu_range["upper_exclusive"]
                    - candidate_super_lower,
                )
                candidate_fast_path = (
                    candidate_super_count
                    >= math.isqrt(
                        candidate_super_lower
                        + candidate_super_count
                        - 1
                    )
                )
                (
                    expected_selected_prime_count,
                    expected_dense_prime_count,
                ) = _expected_selected_prime_counts(
                    prime_roster,
                    super_lower=candidate_super_lower,
                    super_count=candidate_super_count,
                    source_fast_path=candidate_fast_path,
                )
                prime_count_super_index = candidate_super_index
            (
                current_mertens,
                current_squarefree,
                previous,
                bounds,
                source_fast_path,
                super_index,
            ) = _validate_leaf(
                record,
                index=leaf_count,
                expected_lower=expected_lower,
                expected_previous=previous,
                expected_mertens=current_mertens,
                expected_squarefree=current_squarefree,
                root_mertens=initial_state[0],
                root_squarefree=initial_state[1],
                source_lower=gpu_range["lower"],
                leaf_rows=leaf_rows,
                super_rows=super_rows,
                source_upper=gpu_range["upper_exclusive"],
                executable_sha256=runner_sha256,
                roster_sha256=roster_sha256,
                expected_selected_prime_count=(
                    expected_selected_prime_count
                ),
                expected_dense_prime_count=expected_dense_prime_count,
            )
            expected_lower = record["upper_exclusive"]
            for name, candidate in bounds.items():
                extrema[name] = _select_extreme(
                    extrema[name],
                    candidate,
                    maximum=name.endswith("lower"),
                )
            if source_fast_path:
                source_fast_leaf_count += 1
                if super_index != last_source_fast_super:
                    source_fast_super_shard_count += 1
                    last_source_fast_super = super_index
            leaf_count += 1

        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        pending = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(descriptor, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HurstHybridSourceError("H100 runner timed out")
                if not selector.select(remaining):
                    raise HurstHybridSourceError("H100 runner timed out")
                try:
                    chunk = os.read(descriptor, 64 * 1024)
                except BlockingIOError:
                    continue
                if not chunk:
                    if pending:
                        raise HurstHybridSourceError(
                            "H100 JSONL ended with a partial line"
                        )
                    break
                pending.extend(chunk)
                while True:
                    newline = pending.find(b"\n")
                    if newline < 0:
                        break
                    line_size = newline + 1
                    if line_size > MAX_JSONL_LINE_BYTES:
                        raise HurstHybridSourceError(
                            "H100 JSONL line is oversized"
                        )
                    raw = bytes(pending[:line_size])
                    del pending[:line_size]
                    consume_line(raw)
                if len(pending) > MAX_JSONL_LINE_BYTES:
                    raise HurstHybridSourceError(
                        "H100 JSONL line is oversized"
                    )

        try:
            remaining = max(0.0, deadline - time.monotonic())
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise HurstHybridSourceError("H100 runner timed out") from error
        stderr_file.flush()
        if stderr_file.tell() > MAX_STDERR_BYTES:
            raise HurstHybridSourceError("H100 stderr exceeds capture limit")
        if return_code != 0:
            raise HurstHybridSourceError(
                f"H100 runner exited {return_code}"
            )
        if (
            header is None
            or terminal is None
            or expected_lower != gpu_range["upper_exclusive"]
        ):
            raise HurstHybridSourceError("H100 stream is incomplete")
        expected_leaves = (gpu_range["count"] + leaf_rows - 1) // leaf_rows
        if leaf_count != expected_leaves:
            raise HurstHybridSourceError("H100 leaf count changed")
        _validate_terminal(
            terminal,
            gpu_range=gpu_range,
            leaf_rows=leaf_rows,
            super_rows=super_rows,
            leaf_count=leaf_count,
            first_mertens=initial_state[0],
            first_squarefree=initial_state[1],
            final_mertens=current_mertens,
            final_squarefree=current_squarefree,
            final_leaf=previous,
            extrema=extrema,
            source_fast_leaf_count=source_fast_leaf_count,
            source_fast_super_shard_count=source_fast_super_shard_count,
        )
        _digest(digest.hexdigest(), "H100 stream SHA-256", nonzero=True)
        return terminal, leaf_count
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None and process.stdout is not None:
            process.stdout.close()
        stderr_file.close()


def run(
    *,
    materialization_directory: Path,
    output_directory: Path,
    cpu_timeout_seconds: int = 7 * 24 * 3600,
    h100_timeout_seconds: int = 7 * 24 * 3600,
    h100_device: int = 0,
    allow_other_device: bool = False,
) -> dict[str, Any]:
    """Run the captured two-stage arithmetic and atomically publish receipts."""

    plan, plan_sha256 = _load_plan(materialization_directory)
    geometry = plan["source_geometry"]
    cpu_range = geometry["cpu"]
    gpu_range = geometry["h100"]
    exact_production = plan["mode"] == "production"
    try:
        backend = require_azure_measured_worker_for_workload(
            exact_production=exact_production,
            work_bounds=(cpu_range["count"], gpu_range["count"]),
        )
    except CampaignIOError as error:
        raise HurstHybridSourceError(str(error)) from error
    if exact_production and backend != "azure_ncc40ads_h100_v5":
        raise HurstHybridSourceError(
            "production hybrid run requires the Azure H100 measured worker"
        )
    if allow_other_device:
        raise HurstHybridSourceError(
            "the strict H100 stage forbids external cross-device overrides"
        )

    if output_directory.exists() or output_directory.is_symlink():
        raise HurstHybridSourceError("hybrid execution output already exists")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.running-",
            dir=output_directory.parent,
        )
    )
    published = False
    pinned_descriptors: list[int] = []
    try:
        cpu_runner_path = (
            materialization_directory
            / plan["inputs"]["cpu_runner"]["path"]
        )
        h100_runner_path = (
            materialization_directory / plan["inputs"]["h100_runner"]["path"]
        )
        roster_path = (
            materialization_directory / plan["inputs"]["prime_roster"]["path"]
        )
        cpu_runner_fd = _open_pinned_fd(
            cpu_runner_path,
            plan["inputs"]["cpu_runner"],
            "CPU runner",
            executable=True,
        )
        pinned_descriptors.append(cpu_runner_fd)
        h100_runner_fd = _open_pinned_fd(
            h100_runner_path,
            plan["inputs"]["h100_runner"],
            "H100 runner",
            executable=True,
        )
        pinned_descriptors.append(h100_runner_fd)
        roster_fd = _open_pinned_fd(
            roster_path,
            plan["inputs"]["prime_roster"],
            "source-prime roster",
            executable=False,
        )
        pinned_descriptors.append(roster_fd)
        cpu_runner = Path(f"/proc/self/fd/{cpu_runner_fd}")
        h100_runner = Path(f"/proc/self/fd/{h100_runner_fd}")
        roster = Path(f"/proc/self/fd/{roster_fd}")
        roster_raw = (
            _read_open_fd(
                roster_fd,
                maximum_bytes=SOURCE_PRIME_ROSTER_BYTES,
                what="canonical source-prime roster",
            )
            if exact_production
            else None
        )
        prime_roster_values = _prime_roster_values(
            raw=roster_raw,
            expected_sha256=plan["inputs"]["prime_roster"]["sha256"],
            source_upper_exclusive=gpu_range["upper_exclusive"],
            production=exact_production,
        )
        cpu_incoming = (0, 0, 0, 0)
        summary_command = _cpu_command(
            cpu_runner,
            phase="summary",
            lower=cpu_range["lower"],
            upper_exclusive=cpu_range["upper_exclusive"],
            segment_rows=plan["cpu"]["segment_rows"],
            incoming=None,
        )
        summary, summary_raw, summary_stderr = _run_cpu(
            summary_command,
            timeout_seconds=cpu_timeout_seconds,
            pass_fds=(cpu_runner_fd,),
        )
        _validate_cpu_numeric_types(summary, "CPU summary receipt")
        summary_delta = validate_runner_receipt(
            summary,
            phase="summary",
            shard_lower=cpu_range["lower"],
            shard_upper=cpu_range["upper_exclusive"],
            segment_size=plan["cpu"]["segment_rows"],
        )
        verify_command = _cpu_command(
            cpu_runner,
            phase="verify",
            lower=cpu_range["lower"],
            upper_exclusive=cpu_range["upper_exclusive"],
            segment_rows=plan["cpu"]["segment_rows"],
            incoming=cpu_incoming,
        )
        verify, verify_raw, verify_stderr = _run_cpu(
            verify_command,
            timeout_seconds=cpu_timeout_seconds,
            pass_fds=(cpu_runner_fd,),
        )
        _validate_cpu_numeric_types(verify, "CPU verify receipt")
        verify_delta = validate_runner_receipt(
            verify,
            phase="verify",
            shard_lower=cpu_range["lower"],
            shard_upper=cpu_range["upper_exclusive"],
            segment_size=plan["cpu"]["segment_rows"],
            expected_incoming=cpu_incoming,
        )
        if (
            summary_delta != verify_delta
            or summary["row_sha256"] != verify["row_sha256"]
        ):
            raise HurstHybridSourceError(
                "CPU summary/verify row commitment or delta differs"
            )
        cpu_state = tuple(
            left + right
            for left, right in zip(cpu_incoming, verify_delta, strict=True)
        )
        if (
            not -cpu_range["count"] <= cpu_state[0] <= cpu_range["count"]
            or not 0 <= cpu_state[1] <= cpu_range["count"]
            or cpu_state[2] > cpu_state[3]
        ):
            raise HurstHybridSourceError("CPU outgoing state is impossible")
        handoff = _cpu_handoff(
            plan_sha256=plan_sha256,
            geometry=geometry,
            runner_sha256=plan["inputs"]["cpu_runner"]["sha256"],
            summary_raw=summary_raw,
            verify_raw=verify_raw,
            report=verify,
            outgoing=cpu_state,
        )

        outputs = {
            "hybrid-plan.json": canonical_json_bytes(plan),
            "cpu-summary.json": summary_raw,
            "cpu-summary.stderr": summary_stderr,
            "cpu-verify.json": verify_raw,
            "cpu-verify.stderr": verify_stderr,
            "cpu-handoff.json": canonical_json_bytes(handoff),
        }
        for name, raw in outputs.items():
            _copy_captured(stage / name, raw or b"", executable=False)

        leaf_rows = plan["h100"]["leaf_rows"]
        super_rows = plan["h100"]["super_shard_rows"]
        h100_command = [
            str(h100_runner),
            "--lower",
            str(gpu_range["lower"]),
            "--count",
            str(gpu_range["count"]),
            "--shard-rows",
            str(leaf_rows),
            "--super-shard-rows",
            str(super_rows),
            "--incoming-mertens",
            str(cpu_state[0]),
            "--incoming-squarefree",
            str(cpu_state[1]),
            "--previous-leaf-sha256",
            handoff["receipt_chain_sha256"],
            "--source-prime-roster",
            str(roster),
            "--require-device-class",
            plan["h100"]["required_device_class"],
            "--device",
            str(_plain_int(h100_device, "H100 device", minimum=0)),
        ]
        h100_receipts_path = stage / "h100-receipts.jsonl"
        with h100_receipts_path.open("x+b") as h100_output:
            terminal, leaf_count = _run_h100(
                h100_command,
                output=h100_output,
                stderr_path=stage / "h100.stderr",
                gpu_range=gpu_range,
                leaf_rows=leaf_rows,
                super_rows=super_rows,
                initial_digest=handoff["receipt_chain_sha256"],
                initial_state=cpu_state,
                runner_sha256=plan["inputs"]["h100_runner"]["sha256"],
                roster_sha256=plan["inputs"]["prime_roster"]["sha256"],
                prime_roster=prime_roster_values,
                timeout_seconds=h100_timeout_seconds,
                pass_fds=(h100_runner_fd, roster_fd),
            )
            h100_output.flush()
            os.fsync(h100_output.fileno())

        final_state = [
            terminal["outgoing_mertens"],
            terminal["outgoing_squarefree"],
            cpu_state[2],
            cpu_state[3],
        ]
        receipt_pins: dict[str, Any] = {}
        for name in (
            "cpu-summary.json",
            "cpu-verify.json",
            "cpu-handoff.json",
            "h100-receipts.jsonl",
        ):
            digest, size = hash_file_once(stage / name)
            receipt_pins[name] = {"sha256": digest, "size_bytes": size}
        result_payload = {
            "accepted": False,
            "arithmetic_execution_completed": True,
            "classification": (
                "hybrid_arithmetic_receipt_chain_not_attestation_"
                "semantic_evidence_or_lean_proof"
            ),
            "cpu_handoff_sha256": handoff["receipt_chain_sha256"],
            "final_leaf_sha256": terminal["final_leaf_sha256"],
            "final_state": final_state,
            "h100_leaf_count": leaf_count,
            "kind": RESULT_KIND,
            "mode": plan["mode"],
            "plan_artifact": {
                "path": "hybrid-plan.json",
                "sha256": plan_sha256,
                "size_bytes": len(canonical_json_bytes(plan)),
            },
            "plan_sha256": plan_sha256,
            "receipt_artifacts": receipt_pins,
            "schema_version": SCHEMA_VERSION,
            "semantic_flags": dict(SEMANTIC_FLAGS),
            "source_geometry": geometry,
            "source_run_receipt_produced": False,
        }
        receipt_chain = hashlib.sha256(
            RESULT_DOMAIN + canonical_json_bytes(result_payload)
        ).hexdigest()
        result = {
            **result_payload,
            "hybrid_receipt_chain_sha256": receipt_chain,
        }
        result_raw = canonical_json_bytes(result)
        _copy_captured(
            stage / "hybrid-result.json", result_raw, executable=False
        )
        _fsync_directory(stage)
        _readonly_tree(stage)
        os.replace(stage, output_directory)
        published = True
        _fsync_directory(output_directory.parent)
        return {
            **result,
            "output_directory": str(output_directory),
            "result": str(output_directory / "hybrid-result.json"),
        }
    except (
        CampaignIOError,
        EvidenceError,
        HurstResidualCampaignError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        if isinstance(error, HurstHybridSourceError):
            raise
        raise HurstHybridSourceError(
            f"hybrid execution failed closed: {error}"
        ) from error
    finally:
        for descriptor in pinned_descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if not published and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


__all__ = [
    "CPU_UPPER_EXCLUSIVE",
    "GPU_ALGORITHM",
    "GPU_CLASSIFICATION",
    "GPU_HEADER_FIELDS",
    "GPU_LEAF_FIELDS",
    "GPU_SCHEMA",
    "GPU_TERMINAL_FIELDS",
    "H100_LOWER",
    "HurstHybridSourceError",
    "SEMANTIC_FLAGS",
    "SOURCE_LOWER",
    "SOURCE_UPPER_EXCLUSIVE",
    "materialize",
    "run",
    "source_geometry",
]
