# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Authenticated TGDLTCH1-cache to resident-q-major row admission.

This module closes one transport seam.  It derives the row artifact consumed
by the source-shaped H100 resident worker from an externally pinned cache
catalog, without reconstructing a q-major lattice stream.  Every selected
row is copied once.  Boundary storage shards are nevertheless consumed to
their authenticated footer before the derived artifact is published.

The adapter does not generate Hurwitz enclosures, factors, Taylor tails,
roots, completed-L values, sign decisions, zero brackets, or Turing counts.
It is therefore a qualification component and never discharges Platt's
Theorem 7.1.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import statistics
import time
from typing import Any, Iterator, NoReturn

from tg_verifier.dirichlet_allchars_q_scheduler import ParsedScheduleManifest
from tg_verifier.dirichlet_lattice_cache import (
    OLD_Q_MAJOR_LATTICE_BYTES,
    ROW_PAYLOAD_BYTES,
    SOURCE_CACHE_PAYLOAD_BYTES,
    canonical_json_bytes,
    iter_catalog_range_rows,
    load_cache_catalog,
)
from tg_verifier.dirichlet_resident_qmajor_stream import (
    StreamPlan,
    write_row_artifact,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-cache-to-resident-row-feed-v1"
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_cache_resident_feed.receipt.v1"
)
BENCHMARK_SCHEMA = (
    "sparkinterval.tg.dirichlet_cache_resident_feed.benchmark.v1"
)

_HEX = frozenset("0123456789abcdef")


class DirichletCacheResidentFeedError(RuntimeError):
    """A cache pin, range, order, or derived-artifact invariant failed."""


def _fail(message: str) -> NoReturn:
    raise DirichletCacheResidentFeedError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


class _ExactRangeProvider:
    """Adapt a streaming range iterator to the resident writer callback."""

    def __init__(self, rows: Iterator[tuple[int, bytes]]) -> None:
        self._rows = rows
        self._calls = 0
        self._finalized = False

    def row(self, expected_t_index: int) -> bytes:
        if self._finalized:
            _fail("cache range provider was used after finalization")
        try:
            actual_t_index, payload = next(self._rows)
        except StopIteration as error:
            raise DirichletCacheResidentFeedError(
                "cache range omitted a resident phase row"
            ) from error
        if actual_t_index != expected_t_index:
            _fail("cache and resident phase t ordering differ")
        self._calls += 1
        return payload

    def finalize(self) -> None:
        if self._finalized:
            _fail("cache range provider was finalized twice")
        # Resuming after the final selected yield drains the unselected suffix
        # of its boundary shard and authenticates that shard's footer.
        try:
            extra = next(self._rows)
        except StopIteration:
            self._finalized = True
            return
        _fail(f"cache range emitted an unexpected extra row: {extra[0]}")

    @property
    def calls(self) -> int:
        return self._calls


def materialize_resident_rows_from_cache(
    output_path: Path,
    schedule: ParsedScheduleManifest,
    resident_plan: StreamPlan,
    *,
    cache_root: Path,
    cache_catalog_path: Path,
    expected_cache_catalog_sha256: str,
    recovery_seed_sha256: str,
    source_contract_sha256: str,
    require_replayed_cache: bool = True,
) -> dict[str, Any]:
    """Create the worker's one-copy-per-row artifact from TGDLTCH1 shards."""

    catalog_pin = _digest(
        expected_cache_catalog_sha256, "cache catalog file"
    )
    seed_pin = _digest(recovery_seed_sha256, "recovery seed")
    contract_pin = _digest(source_contract_sha256, "source contract")
    if not isinstance(require_replayed_cache, bool):
        _fail("require_replayed_cache must be boolean")
    try:
        catalog, cache_plan = load_cache_catalog(
            cache_catalog_path,
            require_replayed=require_replayed_cache,
            expected_sha256=catalog_pin,
        )
    except RuntimeError as error:
        raise DirichletCacheResidentFeedError(
            f"cache catalog admission failed: {error}"
        ) from error
    cache_stop = cache_plan["parameters"]["t_index_stop_exclusive"]
    if (
        resident_plan.loaded_first_t_index < 0
        or resident_plan.loaded_t_index_stop_exclusive > cache_stop
        or resident_plan.row_count <= 0
    ):
        _fail("resident phase range is outside the cache catalog")

    range_identity: dict[str, Any] = {}
    rows = iter_catalog_range_rows(
        cache_root,
        cache_catalog_path,
        t_index_start_inclusive=resident_plan.loaded_first_t_index,
        t_index_stop_exclusive=(
            resident_plan.loaded_t_index_stop_exclusive
        ),
        require_replayed=require_replayed_cache,
        expected_catalog_sha256=catalog_pin,
        authenticated_identity=range_identity,
    )
    provider = _ExactRangeProvider(rows)
    try:
        resident_receipt = write_row_artifact(
            output_path,
            schedule,
            resident_plan,
            recovery_seed_sha256=seed_pin,
            source_contract_sha256=contract_pin,
            # Bind the actual canonical catalog file, not merely a caller
            # description of the cache source.
            lattice_source_sha256=catalog_pin,
            row_provider=provider.row,
            row_provider_finalizer=provider.finalize,
        )
    except RuntimeError as error:
        raise DirichletCacheResidentFeedError(
            f"cache-backed resident row materialization failed: {error}"
        ) from error
    if (
        provider.calls != resident_plan.row_count
        or not range_identity
        or range_identity.get("catalog_file_sha256") != catalog_pin
        or range_identity.get("selected_row_count")
        != resident_plan.row_count
        or range_identity.get("t_index_start_inclusive")
        != resident_plan.loaded_first_t_index
        or range_identity.get("t_index_stop_exclusive")
        != resident_plan.loaded_t_index_stop_exclusive
    ):
        output_path.unlink(missing_ok=True)
        _fail("cache-backed resident row accounting differs")

    selected_payload_bytes = resident_plan.row_count * ROW_PAYLOAD_BYTES
    logical_reference_bytes = (
        resident_plan.target_row_reference_count * ROW_PAYLOAD_BYTES
    )
    body: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "authenticated_cache_range_to_resident_worker_input_"
            "not_source_execution"
        ),
        "cache_catalog_file_sha256": catalog_pin,
        "cache_catalog_sha256": catalog["catalog_sha256"],
        "cache_plan_sha256": cache_plan["plan_sha256"],
        "cache_all_shards_replayed": catalog["decisions"][
            "all_shards_bind_higher_precision_replay_receipts"
        ],
        "require_replayed_cache": require_replayed_cache,
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_execution_order_sha256": (
            schedule.execution_order_sha256
        ),
        "phase_plan_sha256": resident_plan.phase_plan_sha256,
        "lane_partition_sha256": resident_plan.lane_partition_sha256,
        "first_t_index": resident_plan.loaded_first_t_index,
        "t_index_stop_exclusive": (
            resident_plan.loaded_t_index_stop_exclusive
        ),
        "unique_row_count": resident_plan.row_count,
        "target_row_reference_count": (
            resident_plan.target_row_reference_count
        ),
        "selected_cache_payload_bytes": selected_payload_bytes,
        "logical_qmajor_lattice_reference_bytes": (
            logical_reference_bytes
        ),
        "repeated_lattice_bytes_avoided_in_this_phase": (
            logical_reference_bytes - selected_payload_bytes
        ),
        "row_reuse_ratio": (
            resident_plan.target_row_reference_count
            / resident_plan.row_count
        ),
        "range_authentication": range_identity,
        "resident_row_artifact": {
            "sha256": resident_receipt["input_sha256"],
            "size_bytes": resident_receipt["input_size_bytes"],
            "row_chain_sha256": resident_receipt[
                "row_chain_sha256"
            ],
            "row_stream_sha256": resident_receipt[
                "row_stream_sha256"
            ],
        },
        "ordering_contract": {
            "cache_rows_t_major_strictly_increasing": True,
            "resident_samples_increasing_within_each_q_target": True,
            "q_order_bound_by_TGDQORD1_execution_digest": True,
            "crt_residue_order_reconstructed_by_cuda_worker": True,
            "character_frequency_order_checked_by_downstream_bluestein": False,
            "primitive_character_parity_checked_by_downstream_reducer": False,
        },
        "cache_source_generation_replayed": (
            require_replayed_cache
            and catalog["decisions"][
                "all_shards_bind_higher_precision_replay_receipts"
            ]
        ),
        "resident_cuda_executed": False,
        "all_character_dft_executed": False,
        "completed_l_sign_classifier_executed": False,
        "source_scale_run": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "dft_containment_validated": False,
        "interpolation_exception_turing_closed": False,
        "external_atom_discharged": False,
    }
    body["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return body


def benchmark_cache_range_feed(
    cache_root: Path,
    cache_catalog_path: Path,
    *,
    expected_cache_catalog_sha256: str,
    t_index_start_inclusive: int,
    t_index_stop_exclusive: int,
    repetitions: int = 3,
    require_replayed_cache: bool = False,
) -> dict[str, Any]:
    """Measure bounded authenticated range replay without a CUDA claim."""

    catalog_pin = _digest(
        expected_cache_catalog_sha256, "cache catalog file"
    )
    if (
        type(repetitions) is not int
        or not 1 <= repetitions <= 100
        or not isinstance(require_replayed_cache, bool)
    ):
        _fail("cache range benchmark configuration is invalid")
    elapsed_seconds: list[float] = []
    identities: list[dict[str, Any]] = []
    selected_digests: list[str] = []
    for _ in range(repetitions):
        identity: dict[str, Any] = {}
        selected = hashlib.sha256()
        started = time.perf_counter()
        for t_index, payload in iter_catalog_range_rows(
            cache_root,
            cache_catalog_path,
            t_index_start_inclusive=t_index_start_inclusive,
            t_index_stop_exclusive=t_index_stop_exclusive,
            require_replayed=require_replayed_cache,
            expected_catalog_sha256=catalog_pin,
            authenticated_identity=identity,
        ):
            selected.update(t_index.to_bytes(8, "little"))
            selected.update(payload)
        elapsed_seconds.append(time.perf_counter() - started)
        identities.append(identity)
        selected_digests.append(selected.hexdigest())
    if (
        any(identity != identities[0] for identity in identities[1:])
        or any(digest != selected_digests[0] for digest in selected_digests[1:])
    ):
        _fail("cache range benchmark identities changed between repetitions")
    median_elapsed = statistics.median(elapsed_seconds)
    physical_bytes = identities[0]["authenticated_physical_file_bytes"]
    selected_bytes = identities[0]["selected_payload_bytes"]
    return {
        "schema": BENCHMARK_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "bounded_local_authenticated_cache_io_not_h100_or_source_run"
        ),
        "repetitions": repetitions,
        "elapsed_seconds": elapsed_seconds,
        "median_elapsed_seconds": median_elapsed,
        "selected_payload_sha256": selected_digests[0],
        "selected_payload_bytes_per_repetition": selected_bytes,
        "authenticated_physical_file_bytes_per_repetition": physical_bytes,
        "median_selected_payload_bytes_per_second": (
            selected_bytes / median_elapsed
        ),
        "median_authenticated_physical_bytes_per_second": (
            physical_bytes / median_elapsed
        ),
        "range_authentication": identities[0],
        "source_scale_run": False,
        "h100_measured": False,
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_cache_resident_feed.capability.v1"
        ),
        "algorithm_id": ALGORITHM_ID,
        "authenticated_catalog_range_to_resident_worker_input": True,
        "boundary_storage_shards_fully_authenticated": True,
        "one_copy_per_selected_t_row": True,
        "full_qmajor_lattice_materialization_required": False,
        "source_cache_payload_bytes": SOURCE_CACHE_PAYLOAD_BYTES,
        "former_qmajor_lattice_bytes": OLD_Q_MAJOR_LATTICE_BYTES,
        "resident_cuda_execution_in_adapter": False,
        "all_character_dft_in_adapter": False,
        "TGDBSPK1_largeq_compatible": False,
        "TGDBSPK1_incompatibility": (
            "TGDBSPK1 v1 binds the factored-small-q TGDBSQP3 plan, "
            "character batches, time-tail control, and a t=0 full span; "
            "large-q must retain its distinct CRT/root/completed-factor "
            "identities instead of relabelling that wire"
        ),
        "source_scale_run": False,
        "production_run_completed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "BENCHMARK_SCHEMA",
    "DirichletCacheResidentFeedError",
    "RECEIPT_SCHEMA",
    "benchmark_cache_range_feed",
    "capability",
    "materialize_resident_rows_from_cache",
]
