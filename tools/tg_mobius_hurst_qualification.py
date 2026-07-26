#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Qualify the bounded CUDA Möbius/Hurst implementation.

For identical low and near-10^16 ranges this harness compares:

* full 24-byte support with active and complete device-prime rosters;
* an independently generated prime roster and the authenticated cached roster;
* the 16-byte compact-support kernel in full-field qualification mode;
* the guarded 8-byte fused-support prototype against that 16-byte oracle;
* both compact kernels' one-byte production-transfer shapes; and
* the pinned Hurst CPU adapter, including exact terminal affine M/Q guards.

It also requires deliberate prime omission and corrupted-roster attacks to
fail closed.  The emitted artifact is bounded differential and performance
evidence.  It is not source-range evidence, execution attestation, compiler
refinement, a full-support receipt chain, or a Lean theorem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.hurst_residual_campaign import UPSTREAM_COMMIT
from tg_verifier.mobius_cuda import (
    SOURCE_LIMIT,
    _canonical_transition,
    verify_mobius_receipt,
)


SCHEMA = "sparkinterval.tg.mobius-hurst-bounded-qualification.v2"
ALGORITHM = "cuda-compact-support-exact-affine-versus-hurst-v2"
CLASSIFICATION = (
    "bounded_differential_and_performance_evidence_not_source_evidence_"
    "attestation_compiler_refinement_full_receipt_chain_or_lean_proof"
)
ZERO_DIGEST = "0" * 64
NONROOT_TEST_DIGEST = "1" * 64
SOURCE_ROSTER_COUNT = 5_761_455
SOURCE_ROSTER_BYTES = SOURCE_ROSTER_COUNT * 4
SOURCE_ROSTER_SHA256 = (
    "0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5"
)
SOURCE_ROSTER_LAST = 99_999_989
LITTLE_MERTENS_ACTIVE_CUTOFF = 1_000_000_000_000
LITTLE_MERTENS_STRONGER_CUTOFF = 7_727_068_587
DEFAULT_AZURE_PRICE_SNAPSHOT_DATE = "2026-07-21"
DEFAULT_AZURE_REGION = "eastus2"
DEFAULT_H100_NODE_HOURLY_ON_DEMAND_USD = 6.98
DEFAULT_H100_NODE_HOURLY_SPOT_USD = 1.419034
FULL_ALGORITHM = "tg_mobius_segment_v2"
COMPACT_ALGORITHM = "tg_mobius_compact_mu_qualification_v1"
COMPACT_CLASSIFICATION = (
    "bounded_compact_mu_transition_not_full_support_receipt_or_proof"
)

_FALSE_EXTERNAL_CLAIMS = (
    "single_receipt_covers_full_1e16_range",
    "single_receipt_covers_full_little_mertens_2_11_range",
    "single_receipt_covers_full_little_mertens_stronger_range",
    "has_complete_1e16_receipt_chain",
    "has_complete_little_mertens_2_11_receipt_chain",
    "has_complete_little_mertens_stronger_receipt_chain",
    "proves_mertens_hurst_external_atom",
    "proves_cdem_squarefree_external_atom",
    "proves_little_mertens_2_11_external_atom",
    "proves_little_mertens_stronger_external_atom",
    "proves_any_external_atom",
)
_TIMING_FIELDS = (
    "prime_generation_milliseconds",
    "prime_roster_load_and_authenticate_milliseconds",
    "active_prime_filter_milliseconds",
    "device_allocation_milliseconds",
    "host_to_device_transfer_milliseconds",
    "kernel_milliseconds",
    "compact_pack_milliseconds",
    "affine_mq_scan_reduction_milliseconds",
    "device_to_host_transfer_milliseconds",
    "affine_mq_summary_transfer_milliseconds",
    "affine_mq_host_exact_finalize_milliseconds",
    "independent_cpu_sieve_milliseconds",
    "record_comparison_and_hash_milliseconds",
    "guard_fold_milliseconds",
    "independent_cpu_check_and_exact_bounds_milliseconds",
    "process_milliseconds_before_json_render",
)
_CUDA_HURST_DELTA_FIELDS = (
    "delta_mertens",
    "segment_squarefree_count",
    "little_mertens_lower_delta",
    "little_mertens_upper_delta",
)
_CUDA_CROSS_MODE_FIELDS = (
    "lower",
    "upper",
    "record_count",
    "incoming_mertens",
    "outgoing_mertens",
    "delta_mertens",
    "incoming_squarefree",
    "outgoing_squarefree",
    "segment_squarefree_count",
    "incoming_little_mertens_lower",
    "incoming_little_mertens_upper",
    "outgoing_little_mertens_lower",
    "outgoing_little_mertens_upper",
    "little_mertens_lower_delta",
    "little_mertens_upper_delta",
    "gpu_record_sha256_le_v1",
    "cpu_record_sha256_le_v1",
    "gpu_mu_hurst_block_sha256_v1",
    "mobius_histogram",
)


class QualificationError(RuntimeError):
    """The bounded CUDA/Hurst qualification failed closed."""


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1 << 20):
            hasher.update(chunk)
    return hasher.hexdigest()


def _decimal_text(value: float) -> str:
    if value < 0 or value == float("inf") or value != value:
        raise QualificationError("timing value is not finite and nonnegative")
    return format(value, ".17g")


def _wire(value: Any) -> Any:
    if isinstance(value, float):
        return _decimal_text(value)
    if isinstance(value, dict):
        return {str(name): _wire(member) for name, member in value.items()}
    if isinstance(value, list):
        return [_wire(member) for member in value]
    return value


def _run_json(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    expected_returncode: int = 0,
) -> tuple[dict[str, Any], float]:
    started = time.monotonic_ns()
    result = subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=None if environment is None else dict(environment),
    )
    wall_seconds = (time.monotonic_ns() - started) / 1_000_000_000
    if result.returncode != expected_returncode:
        raise QualificationError(
            f"{list(command)!r} returned {result.returncode}, expected "
            f"{expected_returncode}: {result.stderr.decode(errors='replace')!r}"
        )
    try:
        report = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"{list(command)!r} emitted invalid JSON") from exc
    if not isinstance(report, dict):
        raise QualificationError(f"{list(command)!r} did not emit a JSON object")
    return report, wall_seconds


def _run_rejected(
    command: Sequence[str],
    *,
    expected_returncode: int,
    expected_stderr: str,
) -> dict[str, Any]:
    result = subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stderr = result.stderr.decode(errors="replace")
    if result.returncode != expected_returncode:
        raise QualificationError(
            f"{list(command)!r} returned {result.returncode}, expected "
            f"{expected_returncode}: {stderr!r}"
        )
    if result.stdout.strip():
        raise QualificationError("rejected roster unexpectedly emitted JSON")
    if expected_stderr not in stderr:
        raise QualificationError(
            f"rejected roster stderr did not contain {expected_stderr!r}"
        )
    return {
        "exit_code": result.returncode,
        "required_stderr_substring": expected_stderr,
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
    }


def _gpu_command(
    runner: Path,
    roster: Path | None,
    *,
    lower: int,
    count: int,
    mode: str,
    omitted_prime: int | None = None,
) -> list[str]:
    command = [
        str(runner.resolve()),
        "--lower",
        str(lower),
        "--count",
        str(count),
        "--allow-other-device",
    ]
    if lower != 1:
        command.extend(
            [
                "--incoming-mertens",
                "0",
                "--incoming-squarefree",
                "0",
                "--incoming-little-mertens-lower",
                "0",
                "--incoming-little-mertens-upper",
                "0",
                "--previous-receipt-sha256",
                NONROOT_TEST_DIGEST,
            ]
        )
    if roster is not None:
        command.extend(["--source-prime-roster", str(roster.resolve())])
    if mode == "full_all_primes":
        command.append("--qualification-use-all-device-primes")
    elif mode in ("compact_qualification", "compact_performance"):
        command.extend(["--compact-mu-output", "--compact-support-kernel"])
        if mode == "compact_qualification":
            command.append("--qualification-transfer-compact-support")
        if lower > 1_000_000_000_000:
            command.append("--affine-mq-gpu-prototype")
    elif mode in ("fused_qualification", "fused_performance"):
        command.extend(["--compact-mu-output", "--fused-support-kernel"])
        if mode == "fused_qualification":
            command.append("--qualification-transfer-fused-support")
        if lower > 1_000_000_000_000:
            command.append("--affine-mq-gpu-prototype")
    elif mode != "full_active":
        raise QualificationError(f"unknown GPU qualification mode: {mode}")
    if omitted_prime is not None:
        command.extend(["--qualification-omit-device-prime", str(omitted_prime)])
    return command


def _hurst_command(
    runner: Path, *, lower: int, count: int, affine: bool
) -> list[str]:
    return [
        str(runner.resolve()),
        "--mode",
        "affine" if affine else "summary",
        "--lower",
        str(lower),
        "--upper",
        str(lower + count - 1),
        "--segment-size",
        str(count),
    ]


def _integer(report: Mapping[str, Any], name: str) -> int:
    value = report.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise QualificationError(f"{name} must be an integer")
    return value


def _digest(report: Mapping[str, Any], name: str, *, nonzero: bool) -> str:
    value = report.get(name)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        or (nonzero and value == ZERO_DIGEST)
    ):
        raise QualificationError(f"{name} is not a valid expected digest")
    return value


def _require_fields_equal(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    fields: Iterable[str],
    *,
    description: str,
) -> None:
    for field in fields:
        if left.get(field) != right.get(field):
            raise QualificationError(
                f"{description}: {field} differs: "
                f"{left.get(field)!r} != {right.get(field)!r}"
            )


def _require_false_external_claims(report: Mapping[str, Any]) -> None:
    for field in _FALSE_EXTERNAL_CLAIMS:
        if report.get(field) is not False:
            raise QualificationError(f"{field} must remain false")
    for field in (
        "affine_mq_prototype_covers_little_mertens",
        "affine_mq_prototype_full_source_range",
        "affine_mq_prototype_execution_attested",
        "affine_mq_prototype_lean_atom_discharged",
    ):
        if report.get(field) is not False:
            raise QualificationError(f"{field} must remain false")
    if report.get("affine_mq_fixed_top_k_used_for_acceptance") is not False:
        raise QualificationError(
            "a fixed-width candidate set must not be used for acceptance"
        )


def _validate_roster_report(report: Mapping[str, Any], *, cached: bool) -> None:
    if cached:
        expected = {
            "base_prime_generation": "authenticated_canonical_u32le_roster",
            "base_prime_source": "compiled_sha256_pinned_source_roster",
            "source_prime_roster_sha256": SOURCE_ROSTER_SHA256,
        }
    else:
        expected = {
            "base_prime_generation": "exact_host_eratosthenes_sieve",
            "base_prime_source": "per_process_exact_eratosthenes",
            "source_prime_roster_sha256": ZERO_DIGEST,
        }
    for field, value in expected.items():
        if report.get(field) != value:
            raise QualificationError(
                f"{field} is {report.get(field)!r}, expected {value!r}"
            )


def _validate_active_prime_filter(
    report: Mapping[str, Any], *, lower: int, count: int
) -> None:
    base_prime_limit = math.isqrt(lower + count - 1)
    skipped = count >= base_prime_limit
    expected_filter = (
        "all_primes_hit_by_interval_length"
        if skipped
        else "exact_first-multiple-in-half-open-segment"
    )
    if report.get("device_prime_filter") != expected_filter:
        raise QualificationError("active-prime filter mode is inconsistent")
    if report.get("active_prime_filter_skipped_by_interval_length") is not skipped:
        raise QualificationError("active-prime length proof flag is inconsistent")


def _validate_full(
    report: Mapping[str, Any],
    *,
    lower: int,
    count: int,
    all_primes: bool,
    cached_roster: bool,
) -> None:
    verify_mobius_receipt(report)
    expected = {
        "schema_version": 2,
        "algorithm": FULL_ALGORITHM,
        "classification": "bounded_exact_transition_not_external_atom_proof",
        "lower": lower,
        "upper": lower + count - 1,
        "record_count": count,
        "full_support_commitment_present": True,
        "all_records_compared_with_independent_cpu_segmented_sieve": True,
        "all_gpu_mu_values_compared_with_independent_cpu_segmented_sieve": True,
        "mismatch_count": 0,
        "first_mismatch_number": None,
        "device_base_prime_selection": (
            "qualification_all_primes"
            if all_primes
            else "active_primes_hitting_segment"
        ),
        "full_support_device_to_host_transfer": True,
        "device_to_host_bytes": 24 * count,
        "device_to_host_bytes_per_row": 24,
        "device_support_bytes_per_row": 24,
        "compact_support_kernel": False,
        "compact_support_fieldwise_qualification_transfer": False,
        "fused_support_kernel": False,
        "fused_support_fieldwise_qualification_transfer": False,
    }
    for field, value in expected.items():
        if report.get(field) != value:
            raise QualificationError(
                f"full-support {field} is {report.get(field)!r}, expected {value!r}"
            )
    if report.get("compact_pack_milliseconds") != 0:
        raise QualificationError("unused compact-pack phase must report zero")
    if report.get("affine_mq_scan_reduction_milliseconds") != 0:
        raise QualificationError("unused affine phase must report zero")
    if all_primes:
        if report.get("device_base_prime_count") != report.get("base_prime_count"):
            raise QualificationError("all-prime device count is incomplete")
    elif report.get("device_base_prime_count") != report.get(
        "active_base_prime_count"
    ):
        raise QualificationError("active device-prime count is inconsistent")
    _digest(report, "gpu_record_sha256_le_v1", nonzero=True)
    _digest(report, "hurst_single_segment_mu_row_sha256_v1", nonzero=True)
    _validate_roster_report(report, cached=cached_roster)
    _validate_active_prime_filter(report, lower=lower, count=count)
    _require_false_external_claims(report)


def _validate_compact(
    report: Mapping[str, Any],
    *,
    lower: int,
    count: int,
    qualification_transfer: bool,
) -> None:
    expected = {
        "schema_version": 0,
        "algorithm": COMPACT_ALGORITHM,
        "classification": COMPACT_CLASSIFICATION,
        "lower": lower,
        "upper": lower + count - 1,
        "record_count": count,
        "full_support_commitment_present": qualification_transfer,
        "all_records_compared_with_independent_cpu_segmented_sieve": (
            qualification_transfer
        ),
        "all_gpu_mu_values_compared_with_independent_cpu_segmented_sieve": True,
        "mismatch_count": 0,
        "first_mismatch_number": None,
        "device_base_prime_selection": "active_primes_hitting_segment",
        "full_support_device_to_host_transfer": qualification_transfer,
        "device_to_host_bytes": count * (17 if qualification_transfer else 1),
        "device_to_host_bytes_per_row": 17 if qualification_transfer else 1,
        "device_support_bytes_per_row": 16,
        "compact_support_kernel": True,
        "compact_support_fieldwise_qualification_transfer": (
            qualification_transfer
        ),
        "fused_support_kernel": False,
        "fused_support_fieldwise_qualification_transfer": False,
        "compact_pack_milliseconds": 0,
    }
    for field, value in expected.items():
        if report.get(field) != value:
            raise QualificationError(
                f"compact {field} is {report.get(field)!r}, expected {value!r}"
            )
    if qualification_transfer:
        gpu_digest = _digest(report, "gpu_record_sha256_le_v1", nonzero=True)
        cpu_digest = _digest(report, "cpu_record_sha256_le_v1", nonzero=True)
        if gpu_digest != cpu_digest:
            raise QualificationError("compact fieldwise support digests differ")
    else:
        if (
            report.get("gpu_record_sha256_le_v1") != ZERO_DIGEST
            or report.get("cpu_record_sha256_le_v1") != ZERO_DIGEST
        ):
            raise QualificationError(
                "performance-shaped compact output claimed full support bytes"
            )
    _digest(report, "hurst_single_segment_mu_row_sha256_v1", nonzero=True)
    _validate_roster_report(report, cached=True)
    _validate_active_prime_filter(report, lower=lower, count=count)
    _require_false_external_claims(report)
    if lower > 1_000_000_000_000:
        if (
            _integer(report, "little_mertens_lower_delta") != 0
            or _integer(report, "little_mertens_upper_delta") != 0
        ):
            raise QualificationError(
                "terminal compact run changed little-Mertens state"
            )
        expected_exact_fields = {
            "affine_mq_squarefree_endpoint_arithmetic": (
                "exact_u128_sqrt_bracket_then_u256_boundary_"
                "q_minus_1_q_plus_1_before_reduction"
            ),
            "affine_mq_exact_corrects_every_squarefree_endpoint": True,
            "affine_mq_u256_used_only_in_exact_boundary_strip": True,
            "affine_mq_conservative_interval_arithmetic": (
                "exact_source_shaped_u128_numerators_"
                "two_divisions_per_endpoint"
            ),
            "affine_mq_host_rechecks_all_thread_squarefree_extrema": True,
            "affine_mq_prefix_mertens_bits": 32,
            "affine_mq_prefix_squarefree_bits": 32,
            "affine_mq_prefix_maximum_rows": 100_000_000,
            "affine_mq_thread_extrema_per_record": 4,
            "affine_mq_candidate_local_squarefree_bits": 32,
            "affine_mq_candidate_order_bits": 32,
            "affine_mq_candidate_witness_derived_from_lower_and_order": True,
        }
        for field, value in expected_exact_fields.items():
            if report.get(field) != value:
                raise QualificationError(
                    f"terminal compact {field} is not {value!r}"
                )
        for field in (
            "affine_mq_delta_mertens",
            "affine_mq_delta_squarefree",
            "affine_mq_hurst_guard",
            "affine_mq_squarefree_guard",
        ):
            if report.get(field) is None:
                raise QualificationError(f"terminal compact run omitted {field}")
    elif report.get("affine_mq_hurst_guard") is not None:
        raise QualificationError("low compact run unexpectedly used affine MQ")


def _validate_fused(
    report: Mapping[str, Any],
    *,
    lower: int,
    count: int,
    qualification_transfer: bool,
) -> None:
    expected = {
        "schema_version": 0,
        "algorithm": COMPACT_ALGORITHM,
        "classification": COMPACT_CLASSIFICATION,
        "lower": lower,
        "upper": lower + count - 1,
        "record_count": count,
        "full_support_commitment_present": qualification_transfer,
        "all_records_compared_with_independent_cpu_segmented_sieve": (
            qualification_transfer
        ),
        "all_gpu_mu_values_compared_with_independent_cpu_segmented_sieve": True,
        "mismatch_count": 0,
        "first_mismatch_number": None,
        "device_base_prime_selection": "active_primes_hitting_segment",
        "full_support_device_to_host_transfer": qualification_transfer,
        "device_to_host_bytes": count * (9 if qualification_transfer else 1),
        "device_to_host_bytes_per_row": 9 if qualification_transfer else 1,
        "device_support_bytes_per_row": 8,
        "device_support_layout": (
            "fused_product54_count5_squareful1_reserved3_poison1_u64"
        ),
        "compact_support_kernel": False,
        "compact_support_fieldwise_qualification_transfer": False,
        "fused_support_kernel": True,
        "fused_support_fieldwise_qualification_transfer": (
            qualification_transfer
        ),
        "fused_support_product_bits": 54,
        "fused_support_count_bits": 5,
        "fused_support_maximum_distinct_primes": 13,
        "fused_support_primorial_14": 13_082_761_331_670_030,
        "fused_support_source_limit": SOURCE_LIMIT,
        "fused_support_runtime_product_count_reserved_guards": True,
        "fused_support_poison_count": 0,
        "fused_support_lean_arithmetic_contract": (
            "SparkInterval.TernaryGoldbach.MobiusFusedSupport"
        ),
        "compact_pack_milliseconds": 0,
    }
    for field, value in expected.items():
        if report.get(field) != value:
            raise QualificationError(
                f"fused {field} is {report.get(field)!r}, expected {value!r}"
            )
    if qualification_transfer:
        gpu_digest = _digest(report, "gpu_record_sha256_le_v1", nonzero=True)
        cpu_digest = _digest(report, "cpu_record_sha256_le_v1", nonzero=True)
        if gpu_digest != cpu_digest:
            raise QualificationError("fused fieldwise support digests differ")
    else:
        if (
            report.get("gpu_record_sha256_le_v1") != ZERO_DIGEST
            or report.get("cpu_record_sha256_le_v1") != ZERO_DIGEST
        ):
            raise QualificationError(
                "performance-shaped fused output claimed full support bytes"
            )
    _digest(report, "hurst_single_segment_mu_row_sha256_v1", nonzero=True)
    _validate_roster_report(report, cached=True)
    _validate_active_prime_filter(report, lower=lower, count=count)
    _require_false_external_claims(report)
    if lower > 1_000_000_000_000:
        if (
            _integer(report, "little_mertens_lower_delta") != 0
            or _integer(report, "little_mertens_upper_delta") != 0
        ):
            raise QualificationError(
                "terminal fused run changed little-Mertens state"
            )
        expected_exact_fields = {
            "affine_mq_squarefree_endpoint_arithmetic": (
                "exact_u128_sqrt_bracket_then_u256_boundary_"
                "q_minus_1_q_plus_1_before_reduction"
            ),
            "affine_mq_exact_corrects_every_squarefree_endpoint": True,
            "affine_mq_u256_used_only_in_exact_boundary_strip": True,
            "affine_mq_conservative_interval_arithmetic": (
                "exact_source_shaped_u128_numerators_"
                "two_divisions_per_endpoint"
            ),
            "affine_mq_host_rechecks_all_thread_squarefree_extrema": True,
            "affine_mq_prefix_mertens_bits": 32,
            "affine_mq_prefix_squarefree_bits": 32,
            "affine_mq_prefix_maximum_rows": 100_000_000,
            "affine_mq_thread_extrema_per_record": 4,
            "affine_mq_candidate_local_squarefree_bits": 32,
            "affine_mq_candidate_order_bits": 32,
            "affine_mq_candidate_witness_derived_from_lower_and_order": True,
        }
        for field, value in expected_exact_fields.items():
            if report.get(field) != value:
                raise QualificationError(
                    f"terminal fused {field} is not {value!r}"
                )
        for field in (
            "affine_mq_delta_mertens",
            "affine_mq_delta_squarefree",
            "affine_mq_hurst_guard",
            "affine_mq_squarefree_guard",
        ):
            if report.get(field) is None:
                raise QualificationError(f"terminal fused run omitted {field}")
    elif report.get("affine_mq_hurst_guard") is not None:
        raise QualificationError("low fused run unexpectedly used affine MQ")


def _validate_hurst(
    report: Mapping[str, Any],
    *,
    lower: int,
    count: int,
    affine: bool,
) -> None:
    expected = {
        "algorithm": "hurst-segmented-mobius-two-pass-v2",
        "mode": "affine" if affine else "summary",
        "classification": "source-scale-shard-not-lean-proof",
        "upstream_commit": UPSTREAM_COMMIT,
        "lower": lower,
        "upper_exclusive": lower + count,
        "work_count": count,
        "segment_size": count,
        "segments": 1,
        "row_encoding": "mu-plus-one-block-sha256-v1",
        "accepted": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }
    for field, value in expected.items():
        if report.get(field) != value:
            raise QualificationError(
                f"Hurst {field} is {report.get(field)!r}, expected {value!r}"
            )
    _digest(report, "row_sha256", nonzero=True)
    delta = report.get("delta")
    if (
        not isinstance(delta, list)
        or len(delta) != 4
        or any(isinstance(value, bool) or not isinstance(value, int) for value in delta)
    ):
        raise QualificationError("Hurst additive delta is malformed")
    elapsed = report.get("elapsed_seconds")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or elapsed < 0
    ):
        raise QualificationError("Hurst elapsed time is malformed")
    if affine:
        if not isinstance(report.get("guards"), dict):
            raise QualificationError("affine Hurst report omitted exact guards")
        exact_fallbacks = report.get("exact_fallbacks")
        if not isinstance(exact_fallbacks, dict):
            raise QualificationError("affine Hurst report omitted fallback counts")


def _cuda_delta(report: Mapping[str, Any]) -> list[int]:
    return [_integer(report, field) for field in _CUDA_HURST_DELTA_FIELDS]


def _compare_hurst(
    cuda: Mapping[str, Any],
    hurst: Mapping[str, Any],
    *,
    affine: bool,
) -> None:
    if cuda.get("hurst_single_segment_mu_row_sha256_v1") != hurst.get(
        "row_sha256"
    ):
        raise QualificationError("CUDA and Hurst ordered Möbius bytes differ")
    if _cuda_delta(cuda) != hurst.get("delta"):
        raise QualificationError("CUDA and Hurst additive deltas differ")
    if not affine:
        return
    guards = hurst.get("guards")
    if not isinstance(guards, Mapping):
        raise QualificationError("Hurst guards are malformed")
    mertens = guards.get("mertens-hurst")
    squarefree = guards.get("cdem-squarefree")
    if not isinstance(mertens, Mapping) or not isinstance(squarefree, Mapping):
        raise QualificationError("Hurst M/Q guards are missing")
    mertens_witnesses = mertens.get("witnesses")
    squarefree_witnesses = squarefree.get("witnesses")
    if (
        not isinstance(mertens_witnesses, list)
        or len(mertens_witnesses) != 1
        or not isinstance(mertens_witnesses[0], Mapping)
        or not isinstance(squarefree_witnesses, list)
        or len(squarefree_witnesses) != 1
        or not isinstance(squarefree_witnesses[0], Mapping)
    ):
        raise QualificationError("Hurst M/Q witnesses are malformed")
    h_m = mertens_witnesses[0]
    h_q = squarefree_witnesses[0]
    h_lower = mertens.get("lower")
    h_upper = mertens.get("upper")
    q_lower = squarefree.get("lower")
    q_upper = squarefree.get("upper")
    if not all(
        isinstance(value, list) and len(value) == 4
        for value in (h_lower, h_upper, q_lower, q_upper)
    ):
        raise QualificationError("Hurst guard vectors are malformed")
    expected_mertens = {
        "lower": h_lower[0],
        "lower_witness": h_m.get("lower_n"),
        "upper": h_upper[0],
        "upper_witness": h_m.get("upper_n"),
    }
    expected_squarefree = {
        "lower": q_lower[1],
        "lower_witness": h_q.get("lower_n"),
        "lower_side": h_q.get("lower_side"),
        "upper": q_upper[1],
        "upper_witness": h_q.get("upper_n"),
        "upper_side": h_q.get("upper_side"),
    }
    if cuda.get("affine_mq_hurst_guard") != expected_mertens:
        raise QualificationError("CUDA and Hurst exact Mertens guards differ")
    if cuda.get("affine_mq_squarefree_guard") != expected_squarefree:
        raise QualificationError("CUDA and Hurst exact squarefree guards differ")
    if cuda.get("affine_mq_delta_mertens") != hurst["delta"][0]:
        raise QualificationError("device affine Mertens scan delta differs")
    if cuda.get("affine_mq_delta_squarefree") != hurst["delta"][1]:
        raise QualificationError("device affine squarefree scan delta differs")


def _compare_full_modes(
    active: Mapping[str, Any], complete: Mapping[str, Any]
) -> None:
    if _canonical_transition(active) != _canonical_transition(complete):
        raise QualificationError(
            "active/all-prime canonical full transitions differ"
        )
    if active.get("receipt_chain_sha256") != complete.get(
        "receipt_chain_sha256"
    ):
        raise QualificationError("active/all-prime receipt digests differ")
    _require_fields_equal(
        active,
        complete,
        _CUDA_CROSS_MODE_FIELDS,
        description="active versus all-prime full support",
    )


def _compare_generated_roster(
    cached: Mapping[str, Any], generated: Mapping[str, Any]
) -> None:
    if _canonical_transition(cached) != _canonical_transition(generated):
        raise QualificationError(
            "cached/generated prime rosters changed the canonical transition"
        )
    _require_fields_equal(
        cached,
        generated,
        _CUDA_CROSS_MODE_FIELDS,
        description="cached versus generated prime roster",
    )


def _compare_support_modes(
    full: Mapping[str, Any],
    compact_qualification: Mapping[str, Any],
    compact_performance: Mapping[str, Any],
    fused_qualification: Mapping[str, Any],
    fused_performance: Mapping[str, Any],
) -> None:
    _require_fields_equal(
        full,
        compact_qualification,
        _CUDA_CROSS_MODE_FIELDS,
        description="full versus compact-support qualification",
    )
    performance_fields = tuple(
        field
        for field in _CUDA_CROSS_MODE_FIELDS
        if field not in ("gpu_record_sha256_le_v1", "cpu_record_sha256_le_v1")
    )
    _require_fields_equal(
        compact_qualification,
        compact_performance,
        performance_fields,
        description="compact qualification versus performance shape",
    )
    for field in (
        "affine_mq_delta_mertens",
        "affine_mq_delta_squarefree",
        "affine_mq_hurst_guard",
        "affine_mq_squarefree_guard",
    ):
        if compact_qualification.get(field) != compact_performance.get(field):
            raise QualificationError(f"compact modes disagree on {field}")
    _require_fields_equal(
        compact_qualification,
        fused_qualification,
        _CUDA_CROSS_MODE_FIELDS,
        description="16-byte versus fused 8-byte support qualification",
    )
    _require_fields_equal(
        fused_qualification,
        fused_performance,
        performance_fields,
        description="fused qualification versus performance shape",
    )
    for field in (
        "affine_mq_delta_mertens",
        "affine_mq_delta_squarefree",
        "affine_mq_hurst_guard",
        "affine_mq_squarefree_guard",
    ):
        if fused_qualification.get(field) != fused_performance.get(field):
            raise QualificationError(f"fused modes disagree on {field}")
        if compact_qualification.get(field) != fused_qualification.get(field):
            raise QualificationError(
                f"16-byte and fused support modes disagree on {field}"
            )


def _median(values: Sequence[float]) -> float:
    if not values:
        raise QualificationError("cannot summarize an empty timing series")
    return float(statistics.median(values))


def _timing_summary(
    runs: Sequence[Mapping[str, Any]],
    *,
    count: int,
    h100_sensitivity: float,
    h100_count: int,
    h100_on_demand_usd_per_node_hour: float,
    h100_spot_usd_per_node_hour: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {"rows": count, "modes": {}}
    for mode in (
        "full_active",
        "full_all_primes",
        "compact_qualification",
        "compact_performance",
        "fused_qualification",
        "fused_performance",
    ):
        mode_summary: dict[str, Any] = {}
        for field in _TIMING_FIELDS:
            values = [
                float(run[mode]["report"][field])  # type: ignore[index]
                for run in runs
            ]
            mode_summary[f"{field}_median"] = _decimal_text(_median(values))
        mode_summary["process_wall_seconds_median"] = _decimal_text(
            _median(
                [
                    float(run[mode]["process_wall_seconds"])  # type: ignore[index]
                    for run in runs
                ]
            )
        )
        result["modes"][mode] = mode_summary
    result["hurst"] = {
        "runner_elapsed_seconds_median": _decimal_text(
            _median(
                [
                    float(run["hurst"]["report"]["elapsed_seconds"])  # type: ignore[index]
                    for run in runs
                ]
            )
        ),
        "process_wall_seconds_median": _decimal_text(
            _median(
                [
                    float(run["hurst"]["process_wall_seconds"])  # type: ignore[index]
                    for run in runs
                ]
            )
        ),
    }
    fused = result["modes"]["fused_performance"]
    device_ms = float(fused["kernel_milliseconds_median"]) + float(
        fused["affine_mq_scan_reduction_milliseconds_median"]
    )
    measured_rows_per_second = (
        count * 1000.0 / device_ms if device_ms > 0 else 0.0
    )
    projected_h100_rows_per_second = measured_rows_per_second * h100_sensitivity
    terminal_rows = SOURCE_LIMIT - LITTLE_MERTENS_ACTIVE_CUTOFF
    required_per_h100 = terminal_rows / (h100_count * 7 * 86_400)
    projected_days = (
        terminal_rows
        / (projected_h100_rows_per_second * h100_count * 86_400)
        if projected_h100_rows_per_second > 0
        else float("inf")
    )
    device_arithmetic = {
        "measured_device": runs[0]["fused_performance"]["report"]["device_name"],
        "bounded_rows_per_second": _decimal_text(measured_rows_per_second),
    }
    if (
        runs[0]["fused_performance"]["report"].get("affine_mq_hurst_guard")
        is None
    ):
        result["bounded_device_arithmetic"] = device_arithmetic
        return result
    device_arithmetic.update({
        "source_terminal_lower": LITTLE_MERTENS_ACTIVE_CUTOFF + 1,
        "source_terminal_upper": SOURCE_LIMIT,
        "source_terminal_rows": terminal_rows,
        "required_rows_per_second_per_h100_for_7_days": _decimal_text(
            required_per_h100
        ),
        "h100_over_measured_device_sensitivity_factor": _decimal_text(
            h100_sensitivity
        ),
        "sensitivity_projected_rows_per_second_per_h100": _decimal_text(
            projected_h100_rows_per_second
        ),
        "sensitivity_projected_days_for_source_terminal_rows": _decimal_text(
            projected_days
        ),
        "h100_count": h100_count,
        "sensitivity_projected_azure_on_demand_usd": _decimal_text(
            projected_days
            * 24
            * h100_count
            * h100_on_demand_usd_per_node_hour
        ),
        "sensitivity_projected_azure_spot_usd": _decimal_text(
            projected_days
            * 24
            * h100_count
            * h100_spot_usd_per_node_hour
        ),
        "azure_price_snapshot_date": DEFAULT_AZURE_PRICE_SNAPSHOT_DATE,
        "azure_price_region": DEFAULT_AZURE_REGION,
        "azure_h100_node_hourly_on_demand_usd": _decimal_text(
            h100_on_demand_usd_per_node_hour
        ),
        "azure_h100_node_hourly_spot_usd": _decimal_text(
            h100_spot_usd_per_node_hour
        ),
        "azure_prices_refreshed_by_this_harness": False,
        "h100_measured": False,
        "includes_process_startup": False,
        "includes_roster_authentication": False,
        "includes_host_oracle": False,
        "includes_attestation_or_checkpointing": False,
    })
    result["terminal_device_arithmetic"] = device_arithmetic
    return result


def _validate_source_roster(path: Path) -> None:
    if not path.is_file():
        raise QualificationError(f"prime roster is missing: {path}")
    if path.stat().st_size != SOURCE_ROSTER_BYTES:
        raise QualificationError("prime roster has the wrong byte length")
    if _sha256_file(path) != SOURCE_ROSTER_SHA256:
        raise QualificationError("prime roster does not match the canonical pin")
    with path.open("rb") as source:
        first = int.from_bytes(source.read(4), "little")
        source.seek(-4, os.SEEK_END)
        last = int.from_bytes(source.read(4), "little")
    if first != 2 or last != SOURCE_ROSTER_LAST:
        raise QualificationError("prime roster endpoints are malformed")


def _negative_controls(
    runner: Path, roster: Path
) -> dict[str, Any]:
    omit_report, _ = _run_json(
        _gpu_command(
            runner,
            roster,
            lower=1,
            count=512,
            mode="full_active",
            omitted_prime=2,
        ),
        expected_returncode=5,
    )
    if (
        omit_report.get("mismatch_count") != 256
        or omit_report.get("first_mismatch_number") != 2
        or omit_report.get(
            "all_records_compared_with_independent_cpu_segmented_sieve"
        )
        is not False
        or omit_report.get("gpu_record_sha256_le_v1")
        == omit_report.get("cpu_record_sha256_le_v1")
    ):
        raise QualificationError("prime-omission attack did not fail closed")

    raw = roster.read_bytes()
    with tempfile.TemporaryDirectory(prefix="tg-mobius-roster-attacks-") as root:
        directory = Path(root)
        mutated = directory / "mutated.u32le"
        changed = bytearray(raw)
        changed[len(changed) // 2] ^= 1
        mutated.write_bytes(changed)
        mutated_result = _run_rejected(
            _gpu_command(
                runner,
                mutated,
                lower=1,
                count=13_860,
                mode="full_active",
            ),
            expected_returncode=2,
            expected_stderr="SHA-256 does not match the compiled pin",
        )
        truncated = directory / "truncated.u32le"
        truncated.write_bytes(raw[:-4])
        truncated_result = _run_rejected(
            _gpu_command(
                runner,
                truncated,
                lower=1,
                count=13_860,
                mode="full_active",
            ),
            expected_returncode=2,
            expected_stderr="wrong byte length",
        )
    return {
        "omitted_prime_2": {
            "range": [1, 512],
            "expected_exit_code": 5,
            "mismatch_count": omit_report["mismatch_count"],
            "first_mismatch_number": omit_report["first_mismatch_number"],
            "gpu_record_sha256_le_v1": omit_report[
                "gpu_record_sha256_le_v1"
            ],
            "cpu_record_sha256_le_v1": omit_report[
                "cpu_record_sha256_le_v1"
            ],
        },
        "mutated_same_size_roster": mutated_result,
        "truncated_roster": truncated_result,
    }


def _little_mertens_calibration(
    *,
    hurst_runner: Path,
    environment: Mapping[str, str],
    count: int,
    repeats: int,
) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    walls: list[float] = []
    for _ in range(repeats):
        report, wall = _run_json(
            _hurst_command(
                hurst_runner, lower=1, count=count, affine=True
            ),
            environment=environment,
        )
        _validate_hurst(report, lower=1, count=count, affine=True)
        reports.append(report)
        walls.append(wall)
    reference = reports[0]
    for report in reports[1:]:
        _require_fields_equal(
            reference,
            report,
            (
                "row_sha256",
                "delta",
                "guards",
                "exact_fallbacks",
                "accepted",
            ),
            description="repeated little-Mertens CPU calibration",
        )
    elapsed_median = _median(
        [float(report["elapsed_seconds"]) for report in reports]
    )
    rows_per_second = count / elapsed_median
    cutoff_seconds = LITTLE_MERTENS_ACTIVE_CUTOFF / rows_per_second
    stronger_seconds = LITTLE_MERTENS_STRONGER_CUTOFF / rows_per_second
    return {
        "lower": 1,
        "upper": count,
        "rows": count,
        "repeats": repeats,
        "mode": "affine",
        "reports": [_wire(report) for report in reports],
        "runner_elapsed_seconds_median": _decimal_text(elapsed_median),
        "process_wall_seconds_median": _decimal_text(_median(walls)),
        "bounded_rows_per_second": _decimal_text(rows_per_second),
        "linear_projection_through_1e12_seconds": _decimal_text(
            cutoff_seconds
        ),
        "linear_projection_through_1e12_hours": _decimal_text(
            cutoff_seconds / 3_600
        ),
        "linear_projection_through_7727068587_seconds": _decimal_text(
            stronger_seconds
        ),
        "projection_is_source_run": False,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }


def qualify(
    *,
    gpu_runner: Path,
    hurst_runner: Path,
    prime_roster: Path,
    output: Path,
    count: int,
    repeats: int,
    hurst_threads: int,
    h100_sensitivity: float,
    h100_count: int,
    h100_on_demand_usd_per_node_hour: float,
    h100_spot_usd_per_node_hour: float,
    little_calibration_count: int,
    little_calibration_repeats: int,
) -> dict[str, Any]:
    for label, path in (
        ("CUDA runner", gpu_runner),
        ("Hurst runner", hurst_runner),
    ):
        if not path.is_file():
            raise QualificationError(f"{label} is missing: {path}")
    _validate_source_roster(prime_roster)
    if count < 13_860 or count > 100_000_000:
        raise QualificationError("count must lie in [13860, 100000000]")
    if repeats < 1:
        raise QualificationError("repeats must be positive")
    if hurst_threads < 1:
        raise QualificationError("Hurst thread count must be positive")
    if h100_sensitivity <= 0:
        raise QualificationError("H100 sensitivity factor must be positive")
    if h100_count < 1:
        raise QualificationError("H100 count must be positive")
    if h100_on_demand_usd_per_node_hour < 0:
        raise QualificationError("H100 on-demand price must be nonnegative")
    if h100_spot_usd_per_node_hour < 0:
        raise QualificationError("H100 spot price must be nonnegative")
    if little_calibration_count < 13_860 or little_calibration_count > 2_000_000_000:
        raise QualificationError(
            "little-Mertens calibration count must lie in [13860, 2000000000]"
        )
    if little_calibration_repeats < 1:
        raise QualificationError(
            "little-Mertens calibration repeats must be positive"
        )

    environment = dict(os.environ)
    environment["OMP_NUM_THREADS"] = str(hurst_threads)
    ranges = (
        ("low", 1, False),
        ("near_source_endpoint", SOURCE_LIMIT - count + 1, True),
    )
    range_artifacts: list[dict[str, Any]] = []
    for range_name, lower, affine in ranges:
        generated_report, generated_wall = _run_json(
            _gpu_command(
                gpu_runner,
                None,
                lower=lower,
                count=count,
                mode="full_active",
            )
        )
        _validate_full(
            generated_report,
            lower=lower,
            count=count,
            all_primes=False,
            cached_roster=False,
        )
        runs: list[dict[str, Any]] = []
        modes = (
            "full_active",
            "full_all_primes",
            "compact_qualification",
            "compact_performance",
            "fused_qualification",
            "fused_performance",
        )
        for repeat in range(repeats):
            order = modes if repeat % 2 == 0 else tuple(reversed(modes))
            reports: dict[str, tuple[dict[str, Any], float]] = {}
            for mode in order:
                reports[mode] = _run_json(
                    _gpu_command(
                        gpu_runner,
                        prime_roster,
                        lower=lower,
                        count=count,
                        mode=mode,
                    )
                )
            hurst_report, hurst_wall = _run_json(
                _hurst_command(
                    hurst_runner, lower=lower, count=count, affine=affine
                ),
                environment=environment,
            )
            full_active = reports["full_active"][0]
            full_all = reports["full_all_primes"][0]
            compact_qualification = reports["compact_qualification"][0]
            compact_performance = reports["compact_performance"][0]
            fused_qualification = reports["fused_qualification"][0]
            fused_performance = reports["fused_performance"][0]
            _validate_full(
                full_active,
                lower=lower,
                count=count,
                all_primes=False,
                cached_roster=True,
            )
            _validate_full(
                full_all,
                lower=lower,
                count=count,
                all_primes=True,
                cached_roster=True,
            )
            _validate_compact(
                compact_qualification,
                lower=lower,
                count=count,
                qualification_transfer=True,
            )
            _validate_compact(
                compact_performance,
                lower=lower,
                count=count,
                qualification_transfer=False,
            )
            _validate_fused(
                fused_qualification,
                lower=lower,
                count=count,
                qualification_transfer=True,
            )
            _validate_fused(
                fused_performance,
                lower=lower,
                count=count,
                qualification_transfer=False,
            )
            _validate_hurst(
                hurst_report, lower=lower, count=count, affine=affine
            )
            _compare_full_modes(full_active, full_all)
            _compare_generated_roster(full_active, generated_report)
            _compare_support_modes(
                full_active,
                compact_qualification,
                compact_performance,
                fused_qualification,
                fused_performance,
            )
            _compare_hurst(
                fused_performance, hurst_report, affine=affine
            )
            run: dict[str, Any] = {
                "repeat": repeat,
                "execution_order": list(order) + ["hurst"],
            }
            for mode in modes:
                report, wall = reports[mode]
                run[mode] = {
                    "process_wall_seconds": _decimal_text(wall),
                    "report": _wire(report),
                }
            run["hurst"] = {
                "process_wall_seconds": _decimal_text(hurst_wall),
                "report": _wire(hurst_report),
            }
            runs.append(run)
        range_artifacts.append(
            {
                "name": range_name,
                "lower": lower,
                "upper": lower + count - 1,
                "generated_roster_baseline": {
                    "process_wall_seconds": _decimal_text(generated_wall),
                    "report": _wire(generated_report),
                },
                "runs": runs,
                "timing": _timing_summary(
                    runs,
                    count=count,
                    h100_sensitivity=h100_sensitivity,
                    h100_count=h100_count,
                    h100_on_demand_usd_per_node_hour=(
                        h100_on_demand_usd_per_node_hour
                    ),
                    h100_spot_usd_per_node_hour=(
                        h100_spot_usd_per_node_hour
                    ),
                ),
            }
        )

    little_calibration = _little_mertens_calibration(
        hurst_runner=hurst_runner,
        environment=environment,
        count=little_calibration_count,
        repeats=little_calibration_repeats,
    )
    negative_controls = _negative_controls(gpu_runner, prime_roster)
    terminal_projection = range_artifacts[1]["timing"][
        "terminal_device_arithmetic"
    ]
    mixed_execution_plan = {
        "classification": (
            "source_shaped_workload_split_not_source_execution_or_attestation"
        ),
        "source_lower": 1,
        "source_upper": SOURCE_LIMIT,
        "cpu_four_coordinate_lower": 1,
        "cpu_four_coordinate_upper": LITTLE_MERTENS_ACTIVE_CUTOFF,
        "cpu_four_coordinate_rows": LITTLE_MERTENS_ACTIVE_CUTOFF,
        "gpu_exact_mq_lower": LITTLE_MERTENS_ACTIVE_CUTOFF + 1,
        "gpu_exact_mq_upper": SOURCE_LIMIT,
        "gpu_exact_mq_rows": SOURCE_LIMIT - LITTLE_MERTENS_ACTIVE_CUTOFF,
        "state_components": ["M", "Q", "lm_lower_q96", "lm_upper_q96"],
        "gpu_little_mertens_deltas_above_cutoff": [0, 0],
        "common_ordered_mu_commitment": (
            "mu-plus-one-block-sha256-v1"
        ),
        "common_additive_delta_order": [
            "M",
            "Q",
            "lm_lower_q96",
            "lm_upper_q96",
        ],
        "four_external_atoms_remain_individually_auditable": True,
        "cpu_little_mertens_linear_projection_hours": (
            little_calibration["linear_projection_through_1e12_hours"]
        ),
        "gpu_terminal_sensitivity_projected_days": (
            terminal_projection[
                "sensitivity_projected_days_for_source_terminal_rows"
            ]
        ),
        "gpu_terminal_sensitivity_projected_azure_on_demand_usd": (
            terminal_projection[
                "sensitivity_projected_azure_on_demand_usd"
            ]
        ),
        "gpu_terminal_sensitivity_projected_azure_spot_usd": (
            terminal_projection[
                "sensitivity_projected_azure_spot_usd"
            ]
        ),
        "full_source_run_completed": False,
        "execution_attested": False,
        "lean_atoms_discharged": False,
    }
    artifact = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "classification": CLASSIFICATION,
        "identity": {
            "qualification_harness_sha256": _sha256_file(Path(__file__)),
            "gpu_runner_sha256": _sha256_file(gpu_runner),
            "hurst_runner_sha256": _sha256_file(hurst_runner),
            "hurst_upstream_commit": UPSTREAM_COMMIT,
            "prime_roster_sha256": SOURCE_ROSTER_SHA256,
            "prime_roster_bytes": SOURCE_ROSTER_BYTES,
            "prime_roster_count": SOURCE_ROSTER_COUNT,
            "prime_roster_last": SOURCE_ROSTER_LAST,
        },
        "configuration": {
            "row_count_per_range": count,
            "repeats": repeats,
            "hurst_threads": hurst_threads,
            "h100_over_measured_device_sensitivity_factor": _decimal_text(
                h100_sensitivity
            ),
            "h100_count": h100_count,
            "h100_node_hourly_on_demand_usd": _decimal_text(
                h100_on_demand_usd_per_node_hour
            ),
            "h100_node_hourly_spot_usd": _decimal_text(
                h100_spot_usd_per_node_hour
            ),
            "little_mertens_calibration_count": little_calibration_count,
            "little_mertens_calibration_repeats": (
                little_calibration_repeats
            ),
        },
        "ranges": range_artifacts,
        "little_mertens_cpu_calibration": little_calibration,
        "source_shaped_mixed_execution_plan": mixed_execution_plan,
        "negative_controls": negative_controls,
        "checks": {
            "active_equals_all_prime_full_support_bytes": True,
            "active_equals_all_prime_canonical_transition_bytes": True,
            "cached_roster_equals_generated_roster": True,
            "compact_support_fields_equal_full_support_fields": True,
            "compact_one_byte_output_equals_qualified_compact_output": True,
            "fused_support_fields_equal_compact_support_fields": True,
            "fused_one_byte_output_equals_qualified_fused_output": True,
            "fused_product_count_reserved_guards_active": True,
            "fused_poison_sentinel_compared_by_independent_cpu_oracle": True,
            "cuda_equals_hurst_ordered_mu_bytes": True,
            "cuda_equals_hurst_additive_state": True,
            "terminal_cuda_equals_hurst_exact_mertens_guard": True,
            "terminal_cuda_equals_hurst_exact_squarefree_guard": True,
            "prime_omission_attack_rejected": True,
            "mutated_roster_attack_rejected": True,
            "truncated_roster_attack_rejected": True,
            "unused_device_phases_report_zero": True,
            "little_mertens_cpu_affine_calibration_repeatable": True,
            "mixed_cpu_gpu_workload_split_is_exact": True,
        },
        "capabilities": {
            "bounded_qualification_complete": True,
            "full_source_range": False,
            "source_rows_replayed_independently": False,
            "full_support_receipt_chain_complete": False,
            "primitive_mobius_realization_proved": False,
            "cuda_or_cpp_compiler_refinement_proved": False,
            "execution_attested": False,
            "h100_measured": False,
            "lean_atom_discharged": False,
            "any_external_atom_discharged": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(artifact))
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu-runner", type=Path, required=True)
    parser.add_argument("--hurst-runner", type=Path, required=True)
    parser.add_argument("--prime-roster", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1_000_000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--hurst-threads", type=int, default=8)
    parser.add_argument(
        "--h100-over-measured-device-sensitivity",
        type=float,
        default=12.3,
        help="explicit sensitivity factor, not an H100 measurement",
    )
    parser.add_argument("--h100-count", type=int, default=8)
    parser.add_argument(
        "--h100-node-hourly-on-demand-usd",
        type=float,
        default=DEFAULT_H100_NODE_HOURLY_ON_DEMAND_USD,
        help="checked planning snapshot; this harness does not refresh prices",
    )
    parser.add_argument(
        "--h100-node-hourly-spot-usd",
        type=float,
        default=DEFAULT_H100_NODE_HOURLY_SPOT_USD,
        help="checked planning snapshot; spot availability is not promised",
    )
    parser.add_argument(
        "--little-mertens-calibration-count",
        type=int,
        default=100_000_000,
    )
    parser.add_argument(
        "--little-mertens-calibration-repeats",
        type=int,
        default=3,
    )
    arguments = parser.parse_args()
    artifact = qualify(
        gpu_runner=arguments.gpu_runner,
        hurst_runner=arguments.hurst_runner,
        prime_roster=arguments.prime_roster,
        output=arguments.output,
        count=arguments.count,
        repeats=arguments.repeats,
        hurst_threads=arguments.hurst_threads,
        h100_sensitivity=arguments.h100_over_measured_device_sensitivity,
        h100_count=arguments.h100_count,
        h100_on_demand_usd_per_node_hour=(
            arguments.h100_node_hourly_on_demand_usd
        ),
        h100_spot_usd_per_node_hour=(
            arguments.h100_node_hourly_spot_usd
        ),
        little_calibration_count=(
            arguments.little_mertens_calibration_count
        ),
        little_calibration_repeats=(
            arguments.little_mertens_calibration_repeats
        ),
    )
    summary = {
        "schema": artifact["schema"],
        "checks": artifact["checks"],
        "capabilities": artifact["capabilities"],
        "timing": {
            item["name"]: item["timing"] for item in artifact["ranges"]
        },
        "output": str(arguments.output),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
