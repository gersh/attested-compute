# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed source-wide handoff for the large-q Dirichlet pipeline.

The existing persistent FFT/completed-L pipeline is q-major.  This module
binds its artifact interfaces to the authenticated t-major Hurwitz cache
without pretending that the downstream multi-q transform and zero-state
adapter already exists.  It supplies:

* an immutable contract binding the cache catalog/root, exact eight-lane
  assignment, full replayed finite-recovery seed table, and parsed,
  receipt-bound source-wide ``TGDRNRO1`` root catalog;
* separate formulaic q-tile and fixed-q/up-to-64-t FFT target descriptors, so
  no source-sized task list is materialized;
* an authenticated reader with at most one outstanding row lease per lane; and
* a structural state machine that rejects skipped/reordered tiles and binds
  every still-opaque FFT/zero/measurement digest as an unvalidated claim in
  one ordered receipt chain.

The separate ``TGDLTMB1`` component now consumes authenticated shared rows,
directly produces replayed MPFR factor/exact-rational tail sidecars, and runs
the seeded CUDA composition kernel after one lattice-block upload. Typed
fixed-q FFT receipt bundles have a fail-closed validator, and a bounded
admission adapter matches their extracted lattice payloads to this reader's
authenticated rows in deterministic target order. The remaining seam is to
connect the mixed-q ``TGDAFFI1`` output to that typed-bundle/completed-L graph
and authenticated zero-state import/export. This module does not claim those
seams were executed, that zero
isolation or Turing completeness succeeded, or that Platt's Theorem 7.1 is
discharged.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Iterator, Mapping, NoReturn

from tg_verifier.dirichlet_allchars_stage import (
    ALGORITHM_ID as ALLCHARS_ALGORITHM_ID,
    canonical_component_orders,
    modulus_butterflies,
)
from tg_verifier.dirichlet_campaign import (
    _smallest_prime_factors,
    primitive_character_count,
)
from tg_verifier.dirichlet_largeq_pipeline import (
    ALGORITHM_ID as PIPELINE_ALGORITHM_ID,
)
from tg_verifier.dirichlet_largeq_batch import (
    MAXIMUM_BATCH_COUNT as FFT_BATCH_SIZE,
)
from tg_verifier.dirichlet_lattice_cache import (
    ALGORITHM_ID as CACHE_ALGORITHM_ID,
    DEFAULT_BROADCAST_LANES,
    PRODUCER_REPLAYED_LATTICE_CERTIFICATE,
    ROW_PAYLOAD_BYTES,
    SOURCE_T_INDEX_STOP,
    broadcast_plan,
    canonical_json_bytes,
    iter_catalog_lane_rows,
    load_cache_catalog,
    sha256_bytes,
    sha256_file,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    maximum_t_index,
)
from tg_verifier.dirichlet_recovery_seeds import (
    ALGORITHM_ID as RECOVERY_ALGORITHM_ID,
    CHECKER_ID as RECOVERY_CHECKER_ID,
    HEADER as RECOVERY_HEADER,
    MANIFEST_SCHEMA as RECOVERY_MANIFEST_SCHEMA,
    MAXIMUM_ARTIFACT_BYTES as MAXIMUM_RECOVERY_ARTIFACT_BYTES,
    REPLAY_SCHEMA as RECOVERY_REPLAY_SCHEMA,
    SOURCE_X_START,
    SOURCE_X_STOP,
    read_seed_header_bytes,
    verify_seed_artifact,
)
from tg_verifier.dirichlet_root_number_stage import ROOT_ALGORITHM_ID
from tg_verifier.dirichlet_root_catalog import (
    ALGORITHM_ID as ROOT_CATALOG_ALGORITHM_ID,
    audit_root_catalog,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    ALGORITHM_ID as ZERO_CONSUMER_ALGORITHM_ID,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-source-wide-t-major-supervisor-v1"
CONTRACT_SCHEMA = "sparkinterval.tg.dirichlet_source_supervisor.contract.v1"
Q_TILE_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_source_supervisor.q_tile_receipt.v1"
)
LANE_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_source_supervisor.lane_receipt.v1"
)

SOURCE_CONTRACT_CLASSIFICATION = (
    "source_wide_handoff_plan_not_execution_or_grh_evidence"
)
STRUCTURAL_KAT_CLASSIFICATION = (
    "bounded_structural_handoff_kat_not_source_evidence"
)
CONTRACT_CLASSIFICATIONS = frozenset(
    {SOURCE_CONTRACT_CLASSIFICATION, STRUCTURAL_KAT_CLASSIFICATION}
)

DEFAULT_Q_TILE_SIZE = 4_096
MAXIMUM_Q_TILE_SIZE = 16_384
# Compatibility for the pre-hardening CLI.  Serialized contracts and all
# supervisor semantics use "q tile": an all-character FFT batch is instead a
# sequence of up to 64 ordinates for one fixed modulus.
DEFAULT_Q_BATCH_SIZE = DEFAULT_Q_TILE_SIZE
MAXIMUM_JSON_BYTES = 4 * 1024 * 1024

CLAIM_CHAIN_DOMAIN = b"sparkinterval/tg/dirichlet-source/claim-chain/v1\0"
ROW_CHAIN_DOMAIN = b"sparkinterval/tg/dirichlet-source/row-chain/v1\0"
INITIAL_CHAIN_DOMAIN = b"sparkinterval/tg/dirichlet-source/initial-chain/v1\0"

# These totals pin the exact eight-lane source assignment produced by the
# authenticated cache planner.  A future planner change must be reviewed and
# deliberately versioned rather than silently changing a production contract.
PINNED_SOURCE_LANE_TOTALS = (
    (0, 0, 896, 939_524_096, 43_549_013_602_304),
    (1, 896, 1_664, 805_306_368, 37_327_725_944_832),
    (2, 1_664, 2_560, 939_524_096, 43_549_013_602_304),
    (3, 2_560, 3_328, 805_306_368, 37_327_725_944_832),
    (4, 3_328, 4_352, 1_073_741_824, 43_862_531_226_316),
    (5, 4_352, 5_888, 1_610_612_736, 40_568_368_312_390),
    (6, 5_888, 10_240, 4_563_402_752, 39_738_638_225_670),
    (7, 10_240, 127_988, 123_467_726_848, 41_166_189_424_360),
)
PINNED_SOURCE_ROW_COUNT = 127_988
PINNED_SOURCE_CACHE_PAYLOAD_BYTES = 134_205_145_088
PINNED_SOURCE_RESIDUE_INTERPOLATIONS = 327_089_206_283_008
PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED = (
    5_460_000,
    4_680_000,
    5_460_000,
    4_680_000,
    5_947_802,
    7_181_268,
    11_189_898,
    32_171_249,
)
PINNED_SOURCE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED = 76_770_217
# Compatibility aliases for callers written before the t-major/FFT scheduling
# distinction was made explicit.  These are target-roster counts, not
# invocations executable by the current one-row t-major state machine.
PINNED_SOURCE_LANE_FFT_BATCHES = (
    PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED
)
PINNED_SOURCE_FFT_BATCHES = (
    PINNED_SOURCE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED
)


class DirichletSourceSupervisorError(RuntimeError):
    """A source contract, row lease, batch, or state handoff failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletSourceSupervisorError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _integer(
    value: object,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{label} is below {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{label} is above {maximum}")
    return value


def _safe_file(
    path: Path, *, maximum_bytes: int | None = None, retain_bytes: bool = False
) -> tuple[dict[str, Any], bytes | None]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletSourceSupervisorError(
            f"cannot open bound artifact without following links: {path}"
        ) from error
    digest = hashlib.sha256()
    size = 0
    retained = bytearray() if retain_bytes else None
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if not stat.S_ISREG(status.st_mode):
            _fail(f"bound artifact is not a regular file: {path}")
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
            if retained is not None:
                retained.extend(block)
            if maximum_bytes is not None and size > maximum_bytes:
                _fail(f"bound artifact exceeds its size limit: {path}")
    if size <= 0:
        _fail(f"bound artifact is empty: {path}")
    return (
        {
            "path": str(path.resolve()),
            "sha256": digest.hexdigest(),
            "size_bytes": size,
        },
        bytes(retained) if retained is not None else None,
    )


def _safe_file_record(path: Path, *, maximum_bytes: int | None = None) -> dict[str, Any]:
    record, _raw = _safe_file(path, maximum_bytes=maximum_bytes)
    return record


def _canonical_json(path: Path, *, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    record, raw = _safe_file(
        path, maximum_bytes=MAXIMUM_JSON_BYTES, retain_bytes=True
    )
    assert raw is not None
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletSourceSupervisorError(f"invalid {label} JSON") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value, record


def _self_hash(value: Mapping[str, Any], field: str, *, label: str) -> str:
    body = dict(value)
    claimed = _digest(body.pop(field, None), f"{label}.{field}")
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        _fail(f"{label} self-hash differs")
    return claimed


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
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
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _cache_binding(
    cache_root: Path,
    cache_catalog: Path,
    *,
    lane_count: int,
    require_replayed: bool,
    require_full_source: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if cache_root.is_symlink() or not cache_root.is_dir():
        _fail("cache root is missing, symbolic, or not a directory")
    catalog, plan = load_cache_catalog(
        cache_catalog, require_replayed=require_replayed
    )
    if require_full_source and not plan["complete_large_q_main_grid_geometry"]:
        _fail("production contract requires the complete large-q main grid")
    assignment = broadcast_plan(plan, lane_count=lane_count)
    if require_full_source and lane_count != DEFAULT_BROADCAST_LANES:
        _fail("production contract requires the canonical eight-lane assignment")
    if require_replayed and not all(
        entry["producer_kind"] == PRODUCER_REPLAYED_LATTICE_CERTIFICATE
        for entry in catalog["shards"]
    ):
        _fail("production cache catalog contains a non-replayed shard")
    catalog_file = _safe_file_record(
        cache_catalog, maximum_bytes=MAXIMUM_JSON_BYTES
    )
    return (
        {
            "algorithm_id": CACHE_ALGORITHM_ID,
            "cache_root": str(cache_root.resolve()),
            "catalog_file": catalog_file,
            "catalog_sha256": catalog["catalog_sha256"],
            "storage_plan_sha256": plan["plan_sha256"],
            "broadcast_plan_sha256": assignment["broadcast_plan_sha256"],
            "lane_count": lane_count,
            "row_payload_bytes": ROW_PAYLOAD_BYTES,
            "require_replayed_receipts": require_replayed,
            "complete_large_q_main_grid_geometry": plan[
                "complete_large_q_main_grid_geometry"
            ],
        },
        plan,
        assignment,
    )


def _recovery_binding(
    artifact_path: Path,
    manifest_path: Path,
    replay_path: Path,
    *,
    require_full_source: bool,
) -> dict[str, Any]:
    manifest, manifest_file = _canonical_json(
        manifest_path, label="recovery manifest"
    )
    manifest_sha = _self_hash(
        manifest, "manifest_sha256", label="recovery manifest"
    )
    if (
        manifest.get("kind") != RECOVERY_MANIFEST_SCHEMA
        or manifest.get("schema_version") != 1
        or manifest.get("algorithm_id") != RECOVERY_ALGORITHM_ID
        or manifest.get("atom_id") != ATOM_ID
    ):
        _fail("recovery manifest identity differs")
    artifact, artifact_raw = _safe_file(
        artifact_path,
        maximum_bytes=MAXIMUM_RECOVERY_ARTIFACT_BYTES,
        retain_bytes=True,
    )
    assert artifact_raw is not None
    manifest_artifact = manifest.get("artifact")
    if (
        not isinstance(manifest_artifact, dict)
        or manifest_artifact.get("sha256") != artifact["sha256"]
        or manifest_artifact.get("size_bytes") != artifact["size_bytes"]
    ):
        _fail("recovery artifact differs from its manifest")
    header = read_seed_header_bytes(artifact_raw[:RECOVERY_HEADER.size])
    if require_full_source and (
        not header.full_source
        or header.x_start != SOURCE_X_START
        or header.x_stop != SOURCE_X_STOP
    ):
        _fail("production contract requires the complete recovery seed range")

    replay, replay_file = _canonical_json(replay_path, label="recovery replay")
    replay_sha = _self_hash(replay, "replay_sha256", label="recovery replay")
    required = {
        "algorithm_id",
        "artifact_sha256",
        "atom_id",
        "checker_id",
        "classification",
        "external_atom_discharged",
        "full_source_seed_range",
        "higher_precision_arb_containment_passed",
        "kind",
        "manifest_sha256",
        "record_count",
        "replay_precision_bits",
        "replay_runtime",
        "schema_version",
        "replay_sha256",
    }
    if (
        set(replay) != required
        or replay.get("kind") != RECOVERY_REPLAY_SCHEMA
        or replay.get("schema_version") != 1
        or replay.get("algorithm_id") != RECOVERY_ALGORITHM_ID
        or replay.get("atom_id") != ATOM_ID
        or replay.get("checker_id") != RECOVERY_CHECKER_ID
        or replay.get("classification")
        != "complete_seed_containment_replay_not_theorem_7_1"
        or replay.get("artifact_sha256") != artifact["sha256"]
        or replay.get("manifest_sha256") != manifest_sha
        or replay.get("record_count") != header.record_count
        or replay.get("higher_precision_arb_containment_passed") is not True
        or replay.get("external_atom_discharged") is not False
    ):
        _fail("recovery replay does not bind the complete seed artifact")
    if require_full_source and replay.get("full_source_seed_range") is not True:
        _fail("production recovery replay is not full-source")
    if require_full_source:
        try:
            fresh = verify_seed_artifact(
                artifact_path,
                manifest_path,
                replay_precision_bits=_integer(
                    replay.get("replay_precision_bits"),
                    "recovery replay precision",
                    minimum=128,
                ),
            )["replay"]
        except Exception as error:
            raise DirichletSourceSupervisorError(
                f"fresh recovery seed replay failed: {error}"
            ) from error
        if fresh != replay:
            _fail("fresh recovery seed replay differs from the bound report")
        if (
            _safe_file_record(
                artifact_path,
                maximum_bytes=MAXIMUM_RECOVERY_ARTIFACT_BYTES,
            )
            != artifact
            or _safe_file_record(
                manifest_path, maximum_bytes=MAXIMUM_JSON_BYTES
            )
            != manifest_file
            or _safe_file_record(
                replay_path, maximum_bytes=MAXIMUM_JSON_BYTES
            )
            != replay_file
        ):
            _fail("recovery inputs changed during their fresh replay")
    return {
        "algorithm_id": RECOVERY_ALGORITHM_ID,
        "artifact": artifact,
        "manifest_file": manifest_file,
        "manifest_sha256": manifest_sha,
        "replay_file": replay_file,
        "replay_sha256": replay_sha,
        "full_source_seed_range": bool(header.full_source),
        "record_count": header.record_count,
        "higher_precision_arb_containment_passed": True,
        "fresh_replay_performed_during_binding": require_full_source,
        "execution_attested": False,
    }


def _structural_recovery_binding(
    *,
    artifact_sha256: str,
    replay_sha256: str,
) -> dict[str, Any]:
    """Return an explicitly non-production binding for format/state KATs."""

    return {
        "algorithm_id": RECOVERY_ALGORITHM_ID,
        "artifact": {
            "path": "<structural-kat>",
            "sha256": _digest(artifact_sha256, "KAT recovery artifact"),
            "size_bytes": 1,
        },
        "manifest_file": {
            "path": "<structural-kat>",
            "sha256": "0" * 64,
            "size_bytes": 1,
        },
        "manifest_sha256": "0" * 64,
        "replay_file": {
            "path": "<structural-kat>",
            "sha256": "0" * 64,
            "size_bytes": 1,
        },
        "replay_sha256": _digest(replay_sha256, "KAT recovery replay"),
        "full_source_seed_range": False,
        "record_count": 1,
        "higher_precision_arb_containment_passed": False,
        "fresh_replay_performed_during_binding": False,
        "execution_attested": False,
    }


def _root_catalog_binding(
    root: Path,
    catalog_path: Path,
    *,
    require_full_source: bool,
    revalidate_artifacts: bool,
) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        _fail("root-number artifact directory is missing or unsafe")
    try:
        audited = audit_root_catalog(
            catalog_path,
            root=root if revalidate_artifacts else None,
            require_full_source=require_full_source,
            revalidate_artifacts=revalidate_artifacts,
        )
    except Exception as error:
        raise DirichletSourceSupervisorError(
            f"root-number catalog validation failed: {error}"
        ) from error
    catalog_file = _safe_file_record(
        catalog_path,
        maximum_bytes=512 * 1024 * 1024,
    )
    if (
        catalog_file["sha256"] != audited["catalog"]["sha256"]
        or catalog_file["size_bytes"] != audited["catalog"]["size_bytes"]
    ):
        _fail("root-number catalog changed after its streaming audit")
    return {
        "algorithm_id": ROOT_CATALOG_ALGORITHM_ID,
        "root_directory": str(root.resolve()),
        "catalog_file": catalog_file,
        "q_start_inclusive": audited["q_start_inclusive"],
        "q_stop_inclusive": audited["q_stop_inclusive"],
        "entry_count": audited["entry_count"],
        "entries_sha256": audited["entries_sha256"],
        "entry_chain_sha256": audited["entry_chain_sha256"],
        "complete_large_q_source_range": audited[
            "complete_large_q_source_range"
        ],
        "all_TGDRNRO1_artifacts_parsed_and_receipt_bound": audited[
            "artifacts_parsed_and_receipt_bound"
        ],
        "execution_attested": False,
    }


def _structural_root_catalog_binding() -> dict[str, Any]:
    return {
        "algorithm_id": ROOT_CATALOG_ALGORITHM_ID,
        "root_directory": "<structural-kat>",
        "catalog_file": {
            "path": "<structural-kat>",
            "sha256": "0" * 64,
            "size_bytes": 1,
        },
        "q_start_inclusive": SOURCE_Q_START,
        "q_stop_inclusive": SOURCE_Q_STOP,
        "entry_count": 0,
        "entries_sha256": "0" * 64,
        "entry_chain_sha256": "0" * 64,
        "complete_large_q_source_range": False,
        "all_TGDRNRO1_artifacts_parsed_and_receipt_bound": False,
        "execution_attested": False,
    }


def _lane_inventory(
    assignment: Mapping[str, Any],
    *,
    q_start: int,
    q_stop: int,
    pin_source_totals: bool,
) -> dict[str, Any]:
    raw_lanes = assignment.get("lanes")
    if not isinstance(raw_lanes, list) or not raw_lanes:
        _fail("broadcast assignment has no lanes")
    lanes: list[dict[str, Any]] = []
    for expected_index, raw_lane in enumerate(raw_lanes):
        if not isinstance(raw_lane, dict):
            _fail("broadcast lane is malformed")
        lane = dict(raw_lane)
        if lane.get("lane_index") != expected_index:
            _fail("broadcast lanes are not in canonical order")
        t_start = _integer(
            lane.get("t_index_start_inclusive"),
            f"lane {expected_index} t start",
            minimum=0,
        )
        t_stop = _integer(
            lane.get("t_index_stop_exclusive"),
            f"lane {expected_index} t stop",
            minimum=t_start + 1,
        )
        fft_batches = 0
        for q in range(q_start, q_stop + 1):
            active_stop = min(t_stop, maximum_t_index(q) + 1)
            if active_stop > t_start:
                fft_batches += (
                    active_stop - t_start + FFT_BATCH_SIZE - 1
                ) // FFT_BATCH_SIZE
        lane["row_count"] = t_stop - t_start
        lane[
            "q_contiguous_fft_batch_invocations_if_transposed"
        ] = fft_batches
        lanes.append(lane)

    inventory = {
        "lane_count": len(lanes),
        "lanes": lanes,
        "totals": {
            "row_count": sum(lane["row_count"] for lane in lanes),
            "cache_payload_bytes": sum(
                _integer(
                    lane.get("cache_payload_bytes"),
                    f"lane {lane['lane_index']} cache payload",
                    minimum=1,
                )
                for lane in lanes
            ),
            "residue_interpolations": sum(
                _integer(
                    lane.get("residue_interpolations"),
                    f"lane {lane['lane_index']} residue interpolations",
                    minimum=0,
                )
                for lane in lanes
            ),
            "q_contiguous_fft_batch_invocations_if_transposed": sum(
                lane[
                    "q_contiguous_fft_batch_invocations_if_transposed"
                ]
                for lane in lanes
            ),
        },
        "source_eight_lane_totals_pinned": pin_source_totals,
    }
    if pin_source_totals:
        observed = tuple(
            (
                lane["lane_index"],
                lane["t_index_start_inclusive"],
                lane["t_index_stop_exclusive"],
                lane["cache_payload_bytes"],
                lane["residue_interpolations"],
            )
            for lane in lanes
        )
        if observed != PINNED_SOURCE_LANE_TOTALS:
            _fail("source eight-lane cache totals differ from the pinned inventory")
        if tuple(
            lane["q_contiguous_fft_batch_invocations_if_transposed"]
            for lane in lanes
        ) != PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED:
            _fail(
                "source eight-lane q-contiguous FFT target-roster totals "
                "differ from the pinned inventory"
            )
        if inventory["totals"] != {
            "row_count": PINNED_SOURCE_ROW_COUNT,
            "cache_payload_bytes": PINNED_SOURCE_CACHE_PAYLOAD_BYTES,
            "residue_interpolations": PINNED_SOURCE_RESIDUE_INTERPOLATIONS,
            "q_contiguous_fft_batch_invocations_if_transposed": (
                PINNED_SOURCE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED
            ),
        }:
            _fail("source lane aggregate totals differ from the pinned inventory")
    return inventory


def _contract_body(
    *,
    cache: dict[str, Any],
    plan: dict[str, Any],
    assignment: dict[str, Any],
    recovery: dict[str, Any],
    root_numbers: dict[str, Any],
    q_tile_size: int,
    structural_kat: bool,
    q_start: int,
    q_stop: int,
) -> dict[str, Any]:
    _integer(
        q_tile_size,
        "q tile size",
        minimum=1,
        maximum=MAXIMUM_Q_TILE_SIZE,
    )
    _integer(q_start, "q start", minimum=SOURCE_Q_START, maximum=SOURCE_Q_STOP)
    _integer(q_stop, "q stop", minimum=q_start, maximum=SOURCE_Q_STOP)
    if not structural_kat and (q_start, q_stop) != (
        SOURCE_Q_START,
        SOURCE_Q_STOP,
    ):
        _fail("production contract requires the complete large-q modulus range")
    full_source = (
        not structural_kat
        and q_start == SOURCE_Q_START
        and q_stop == SOURCE_Q_STOP
        and plan["complete_large_q_main_grid_geometry"]
        and cache["lane_count"] == DEFAULT_BROADCAST_LANES
        and recovery["full_source_seed_range"]
        and recovery["higher_precision_arb_containment_passed"]
        and root_numbers["complete_large_q_source_range"]
        and root_numbers[
            "all_TGDRNRO1_artifacts_parsed_and_receipt_bound"
        ]
    )
    lane_inventory = _lane_inventory(
        assignment,
        q_start=q_start,
        q_stop=q_stop,
        pin_source_totals=full_source,
    )
    body: dict[str, Any] = {
        "schema": CONTRACT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            SOURCE_CONTRACT_CLASSIFICATION
            if full_source
            else STRUCTURAL_KAT_CLASSIFICATION
        ),
        "cache": cache,
        "recovery": recovery,
        "root_numbers": root_numbers,
        "schedule": {
            "q_start_inclusive": q_start,
            "q_stop_inclusive": q_stop,
            "q_tile_size": q_tile_size,
            "q_tile_count": (q_stop - q_start + q_tile_size) // q_tile_size,
            "positive_t_step": [5, 64],
            "t_index_stop_exclusive": plan["parameters"][
                "t_index_stop_exclusive"
            ],
            "lane_count": cache["lane_count"],
            "lane_inventory": lane_inventory,
            "at_most_one_outstanding_authenticated_row_lease_per_lane": True,
            "q_tiles_formulaic_not_materialized": True,
            "q_contiguous_fft_batch_maximum_ordinates_if_transposed": (
                FFT_BATCH_SIZE
            ),
            "q_contiguous_fft_roster_requires_unimplemented_transpose_or_state_adapter": (
                True
            ),
            "skip_only_q_with_t_index_above_exact_source_height": True,
        },
        "component_interfaces": {
            "persistent_q_pipeline_algorithm_id": PIPELINE_ALGORITHM_ID,
            "all_character_fft_algorithm_id": ALLCHARS_ALGORITHM_ID,
            "root_number_algorithm_id": ROOT_ALGORITHM_ID,
            "root_catalog_algorithm_id": ROOT_CATALOG_ALGORITHM_ID,
            "zero_consumer_algorithm_id": ZERO_CONSUMER_ALGORITHM_ID,
            "root_catalog_artifacts_parsed_and_receipt_bound": root_numbers[
                "all_TGDRNRO1_artifacts_parsed_and_receipt_bound"
            ],
            "typed_bundle_cache_row_admission_adapter_implemented": True,
            "typed_bundle_lattice_payload_identity_binding_implemented": True,
            "FFT_zero_and_measurement_digests_are_claimed_not_validated": True,
            "all_claims_bound_by_one_ordered_receipt_hash_chain": True,
            "zero_consumer_claim_requires_exact_before_after_digest": True,
        },
        "remaining_kernel_seam": {
            "implemented": False,
            "current_input": (
                "q-major TGDLQB2 with batch_count repeated 1-MiB lattice rows"
            ),
            "required_input": (
                "one authenticated TGDLTCH1 t-major row resident on one lane, "
                "then exact formulaic q tiles feeding the seeded recovery, "
                "all-character FFT, root artifact, and zero-consumer pipeline"
            ),
            "maximum_outstanding_authenticated_row_leases_per_lane": 1,
        },
        "remaining_host_seams": {
            "typed_FFT_pipeline_receipt_bundle_validator_implemented": True,
            "typed_bundle_cache_row_admission_adapter_implemented": True,
            "typed_bundle_lattice_payload_identity_binding_implemented": True,
            "typed_FFT_pipeline_bundle_integrated_into_t_major_lane": False,
            "discarded_FFT_stream_arithmetic_independently_replayed": False,
            "zero_consumer_state_import_export_implemented": False,
            "t_major_to_q_contiguous_zero_schedule_implemented": False,
        },
        "decisions": {
            "source_geometry_complete": full_source,
            "cache_rows_executed": False,
            "cuda_t_major_kernel_integrated": False,
            "full_source_campaign_run": False,
            "zero_isolation_or_turing_completed": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    return body


def build_source_contract(
    output_path: Path,
    *,
    cache_root: Path,
    cache_catalog: Path,
    recovery_artifact: Path,
    recovery_manifest: Path,
    recovery_replay: Path,
    root_artifact_directory: Path,
    root_catalog: Path,
    q_tile_size: int = DEFAULT_Q_TILE_SIZE,
    q_batch_size: int | None = None,
) -> dict[str, Any]:
    """Bind all immutable source inputs required before an Azure run."""

    if q_batch_size is not None:
        if q_tile_size != DEFAULT_Q_TILE_SIZE:
            _fail("specify q_tile_size, not both q tile and legacy q batch size")
        q_tile_size = q_batch_size
    cache, plan, assignment = _cache_binding(
        cache_root,
        cache_catalog,
        lane_count=DEFAULT_BROADCAST_LANES,
        require_replayed=True,
        require_full_source=True,
    )
    recovery = _recovery_binding(
        recovery_artifact,
        recovery_manifest,
        recovery_replay,
        require_full_source=True,
    )
    root_numbers = _root_catalog_binding(
        root_artifact_directory,
        root_catalog,
        require_full_source=True,
        revalidate_artifacts=True,
    )
    contract = _contract_body(
        cache=cache,
        plan=plan,
        assignment=assignment,
        recovery=recovery,
        root_numbers=root_numbers,
        q_tile_size=q_tile_size,
        structural_kat=False,
        q_start=SOURCE_Q_START,
        q_stop=SOURCE_Q_STOP,
    )
    contract["contract_sha256"] = sha256_bytes(canonical_json_bytes(contract))
    _atomic_json(output_path, contract)
    return contract


def build_structural_kat_contract(
    output_path: Path,
    *,
    cache_root: Path,
    cache_catalog: Path,
    lane_count: int,
    recovery_artifact_sha256: str,
    recovery_replay_sha256: str,
    q_tile_size: int = DEFAULT_Q_TILE_SIZE,
    q_start: int = SOURCE_Q_START,
    q_stop: int = SOURCE_Q_STOP,
    q_batch_size: int | None = None,
) -> dict[str, Any]:
    """Bind a prefix/synthetic cache for executable protocol tests only."""

    if q_batch_size is not None:
        if q_tile_size != DEFAULT_Q_TILE_SIZE:
            _fail("specify q_tile_size, not both q tile and legacy q batch size")
        q_tile_size = q_batch_size
    cache, plan, assignment = _cache_binding(
        cache_root,
        cache_catalog,
        lane_count=lane_count,
        require_replayed=False,
        require_full_source=False,
    )
    recovery = _structural_recovery_binding(
        artifact_sha256=recovery_artifact_sha256,
        replay_sha256=recovery_replay_sha256,
    )
    root_numbers = _structural_root_catalog_binding()
    contract = _contract_body(
        cache=cache,
        plan=plan,
        assignment=assignment,
        recovery=recovery,
        root_numbers=root_numbers,
        q_tile_size=q_tile_size,
        structural_kat=True,
        q_start=q_start,
        q_stop=q_stop,
    )
    contract["contract_sha256"] = sha256_bytes(canonical_json_bytes(contract))
    _atomic_json(output_path, contract)
    return contract


def load_contract(
    path: Path,
    *,
    allow_structural_kat: bool = False,
    revalidate_files: bool = True,
    expected_contract_sha256: str | None = None,
) -> dict[str, Any]:
    if not revalidate_files:
        _fail("source contracts require file revalidation to reconstruct their body")
    contract, _record = _canonical_json(path, label="source supervisor contract")
    claimed_contract_sha256 = _self_hash(
        contract, "contract_sha256", label="source supervisor contract"
    )
    if (
        expected_contract_sha256 is not None
        and claimed_contract_sha256
        != _digest(expected_contract_sha256, "expected source contract")
    ):
        _fail("source supervisor contract differs from the externally pinned digest")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "classification",
        "cache",
        "recovery",
        "root_numbers",
        "schedule",
        "component_interfaces",
        "remaining_kernel_seam",
        "remaining_host_seams",
        "decisions",
        "contract_sha256",
    }
    if (
        set(contract) != required
        or contract.get("schema") != CONTRACT_SCHEMA
        or contract.get("schema_version") != 1
        or contract.get("author") != AUTHOR
        or contract.get("atom_id") != ATOM_ID
        or contract.get("algorithm_id") != ALGORITHM_ID
    ):
        _fail("source supervisor contract identity or fields differ")
    classification = contract.get("classification")
    if classification not in CONTRACT_CLASSIFICATIONS:
        _fail("source supervisor classification is outside the exact enum")
    structural = classification == STRUCTURAL_KAT_CLASSIFICATION
    if structural and not allow_structural_kat:
        _fail("structural KAT contract requires explicit authorization")
    if not structural and expected_contract_sha256 is None:
        _fail("production source contract requires an externally pinned digest")

    cache = contract.get("cache")
    recovery = contract.get("recovery")
    root_numbers = contract.get("root_numbers")
    schedule = contract.get("schedule")
    if not all(
        isinstance(item, dict)
        for item in (cache, recovery, root_numbers, schedule)
    ):
        _fail("source supervisor contract records are malformed")
    assert isinstance(cache, dict)
    assert isinstance(recovery, dict)
    assert isinstance(root_numbers, dict)
    assert isinstance(schedule, dict)
    lane_count = _integer(
        schedule.get("lane_count"), "lane count", minimum=1
    )
    q_tile_size = _integer(
        schedule.get("q_tile_size"),
        "q tile size",
        minimum=1,
        maximum=MAXIMUM_Q_TILE_SIZE,
    )
    q_start = _integer(
        schedule.get("q_start_inclusive"),
        "q start",
        minimum=SOURCE_Q_START,
        maximum=SOURCE_Q_STOP,
    )
    q_stop = _integer(
        schedule.get("q_stop_inclusive"),
        "q stop",
        minimum=q_start,
        maximum=SOURCE_Q_STOP,
    )
    catalog_file = cache.get("catalog_file")
    if not isinstance(catalog_file, dict):
        _fail("source supervisor cache catalog binding is malformed")
    rebound, plan, assignment = _cache_binding(
        Path(str(cache.get("cache_root"))),
        Path(str(catalog_file.get("path"))),
        lane_count=lane_count,
        require_replayed=not structural,
        require_full_source=not structural,
    )
    if structural:
        artifact = recovery.get("artifact")
        if not isinstance(artifact, dict):
            _fail("structural recovery artifact claim is malformed")
        rebound_recovery = _structural_recovery_binding(
            artifact_sha256=_digest(
                artifact.get("sha256"), "structural recovery artifact"
            ),
            replay_sha256=_digest(
                recovery.get("replay_sha256"), "structural recovery replay"
            ),
        )
        rebound_roots = _structural_root_catalog_binding()
    else:
        artifact = recovery.get("artifact")
        manifest = recovery.get("manifest_file")
        replay = recovery.get("replay_file")
        if not all(isinstance(item, dict) for item in (artifact, manifest, replay)):
            _fail("source supervisor recovery file binding is malformed")
        assert isinstance(artifact, dict)
        assert isinstance(manifest, dict)
        assert isinstance(replay, dict)
        rebound_recovery = _recovery_binding(
            Path(str(artifact.get("path"))),
            Path(str(manifest.get("path"))),
            Path(str(replay.get("path"))),
            require_full_source=True,
        )
        root_catalog_file = root_numbers.get("catalog_file")
        if not isinstance(root_catalog_file, dict):
            _fail("source supervisor root catalog file binding is malformed")
        rebound_roots = _root_catalog_binding(
            Path(str(root_numbers.get("root_directory"))),
            Path(str(root_catalog_file.get("path"))),
            require_full_source=True,
            revalidate_artifacts=True,
        )
    expected = _contract_body(
        cache=rebound,
        plan=plan,
        assignment=assignment,
        recovery=rebound_recovery,
        root_numbers=rebound_roots,
        q_tile_size=q_tile_size,
        structural_kat=structural,
        q_start=q_start,
        q_stop=q_stop,
    )
    observed = dict(contract)
    observed.pop("contract_sha256")
    if observed != expected:
        _fail("source supervisor contract differs from its reconstructed body")
    return contract


@lru_cache(maxsize=1)
def _source_spf() -> tuple[int, ...]:
    return tuple(_smallest_prime_factors(SOURCE_Q_STOP))


@lru_cache(maxsize=SOURCE_Q_STOP - SOURCE_Q_START + 1)
def _q_metrics(q: int) -> tuple[int, int, int]:
    group_values = math.prod(canonical_component_orders(q))
    primitive_values = primitive_character_count(q, _source_spf())
    butterflies = modulus_butterflies(q)
    return group_values, primitive_values, butterflies


def q_tile_descriptor(
    contract: Mapping[str, Any],
    *,
    t_index: int,
    q_tile_index: int,
) -> dict[str, Any]:
    """Describe one modulus tile scanned while one t-major row is leased."""

    schedule = contract.get("schedule")
    if not isinstance(schedule, dict):
        _fail("contract schedule is missing")
    q_tile_size = _integer(
        schedule.get("q_tile_size"),
        "q tile size",
        minimum=1,
        maximum=MAXIMUM_Q_TILE_SIZE,
    )
    t_stop = _integer(
        schedule.get("t_index_stop_exclusive"), "t stop", minimum=1
    )
    if type(t_index) is not int or not 0 <= t_index < t_stop:
        _fail("t index is outside the contract")
    count = _integer(
        schedule.get("q_tile_count"), "q tile count", minimum=1
    )
    if type(q_tile_index) is not int or not 0 <= q_tile_index < count:
        _fail("q tile index is outside the contract")
    source_q_start = _integer(
        schedule.get("q_start_inclusive"),
        "q start",
        minimum=SOURCE_Q_START,
        maximum=SOURCE_Q_STOP,
    )
    source_q_stop = _integer(
        schedule.get("q_stop_inclusive"),
        "q stop",
        minimum=source_q_start,
        maximum=SOURCE_Q_STOP,
    )
    q_start = source_q_start + q_tile_index * q_tile_size
    q_stop = min(source_q_stop + 1, q_start + q_tile_size)
    active: list[int] = []
    group_values = 0
    primitive_values = 0
    butterflies = 0
    root_moduli = 0
    for q in range(q_start, q_stop):
        if t_index > maximum_t_index(q):
            continue
        active.append(q)
        group, primitive, fft = _q_metrics(q)
        group_values += group
        primitive_values += primitive
        butterflies += fft
        root_moduli += primitive != 0
    active_digest = sha256_bytes(canonical_json_bytes(active))
    return {
        "q_tile_index": q_tile_index,
        "q_start_inclusive": q_start,
        "q_stop_exclusive": q_stop,
        "active_q_count": len(active),
        "active_q_sha256": active_digest,
        "first_active_q": active[0] if active else None,
        "last_active_q": active[-1] if active else None,
        "all_character_input_values": group_values,
        "primitive_character_values": primitive_values,
        "root_artifact_moduli": root_moduli,
        "radix2_butterflies": butterflies,
    }


def q_batch_descriptor(
    contract: Mapping[str, Any],
    *,
    t_index: int,
    q_batch_index: int,
) -> dict[str, Any]:
    """Compatibility wrapper; the object is an exact q-tile descriptor."""

    return q_tile_descriptor(
        contract, t_index=t_index, q_tile_index=q_batch_index
    )


def fft_batch_descriptor(
    contract: Mapping[str, Any],
    *,
    lane_index: int,
    q: int,
    first_t_index: int,
) -> dict[str, Any]:
    """Describe a fixed-q FFT target requiring q-contiguous input.

    This descriptor is not directly executable by the current one-row
    t-major supervisor.  A transpose/spool or authenticated state adapter must
    first make its consecutive ordinates available together.
    """

    schedule = contract.get("schedule")
    if not isinstance(schedule, dict):
        _fail("contract schedule is missing")
    inventory = schedule.get("lane_inventory")
    if not isinstance(inventory, dict):
        _fail("contract lane inventory is missing")
    lanes = inventory.get("lanes")
    if not isinstance(lanes, list):
        _fail("contract lanes are missing")
    if type(lane_index) is not int or not 0 <= lane_index < len(lanes):
        _fail("lane index is outside the contract")
    lane = lanes[lane_index]
    if not isinstance(lane, dict) or lane.get("lane_index") != lane_index:
        _fail("contract lane inventory is malformed")
    q_start = _integer(
        schedule.get("q_start_inclusive"),
        "q start",
        minimum=SOURCE_Q_START,
        maximum=SOURCE_Q_STOP,
    )
    q_stop = _integer(
        schedule.get("q_stop_inclusive"),
        "q stop",
        minimum=q_start,
        maximum=SOURCE_Q_STOP,
    )
    if type(q) is not int or not q_start <= q <= q_stop:
        _fail("FFT batch q is outside the contract")
    lane_start = _integer(
        lane.get("t_index_start_inclusive"), "lane t start", minimum=0
    )
    lane_stop = _integer(
        lane.get("t_index_stop_exclusive"),
        "lane t stop",
        minimum=lane_start + 1,
    )
    active_stop = min(lane_stop, maximum_t_index(q) + 1)
    if (
        type(first_t_index) is not int
        or first_t_index < lane_start
        or (first_t_index - lane_start) % FFT_BATCH_SIZE
        or first_t_index >= active_stop
    ):
        _fail("FFT batch first t index is not an active lane-aligned batch start")
    t_stop = min(active_stop, first_t_index + FFT_BATCH_SIZE)
    batch_count = t_stop - first_t_index
    group_values, primitive_values, _single_butterflies = _q_metrics(q)
    q_tile_size = _integer(
        schedule.get("q_tile_size"),
        "q tile size",
        minimum=1,
        maximum=MAXIMUM_Q_TILE_SIZE,
    )
    return {
        "lane_index": lane_index,
        "q": q,
        "q_tile_index": (q - q_start) // q_tile_size,
        "first_t_index": first_t_index,
        "t_index_stop_exclusive": t_stop,
        "batch_count": batch_count,
        "first_t_numerator": SOURCE_SAMPLE_NUMERATOR * first_t_index,
        "t_denominator": SOURCE_SAMPLE_DENOMINATOR,
        "t_step_numerator": SOURCE_SAMPLE_NUMERATOR,
        "component_orders": list(canonical_component_orders(q)),
        "group_order": group_values,
        "value_count": batch_count * group_values,
        "primitive_character_values": batch_count * primitive_values,
        "radix2_butterflies": modulus_butterflies(
            q, batch_count=batch_count
        ),
        "requires_q_contiguous_input": True,
        "current_t_major_lane_directly_executable": False,
    }


def _initial_chain(contract_sha256: str, lane_index: int, label: bytes) -> str:
    digest = hashlib.sha256(INITIAL_CHAIN_DOMAIN)
    digest.update(label)
    digest.update(bytes.fromhex(contract_sha256))
    digest.update(lane_index.to_bytes(4, "little"))
    return digest.hexdigest()


def _extend_chain(domain: bytes, before: str, component: str, identity: bytes) -> str:
    digest = hashlib.sha256(domain)
    digest.update(bytes.fromhex(before))
    digest.update(bytes.fromhex(component))
    digest.update(identity)
    return digest.hexdigest()


@dataclass(frozen=True)
class RowLease:
    lane_index: int
    t_index: int
    payload: bytes
    payload_sha256: str


class AuthenticatedLaneReader:
    """Issue no more than one outstanding authenticated row lease per lane."""

    def __init__(
        self,
        contract_path: Path,
        *,
        lane_index: int,
        allow_structural_kat: bool = False,
        expected_contract_sha256: str | None = None,
    ) -> None:
        self.contract = load_contract(
            contract_path,
            allow_structural_kat=allow_structural_kat,
            expected_contract_sha256=expected_contract_sha256,
        )
        schedule = self.contract["schedule"]
        lane_count = schedule["lane_count"]
        if type(lane_index) is not int or not 0 <= lane_index < lane_count:
            _fail("lane index is outside the contract")
        self.lane_index = lane_index
        cache = self.contract["cache"]
        self._rows = iter_catalog_lane_rows(
            Path(cache["cache_root"]),
            Path(cache["catalog_file"]["path"]),
            lane_index=lane_index,
            lane_count=lane_count,
            require_replayed=cache["require_replayed_receipts"],
            expected_catalog_sha256=cache["catalog_file"]["sha256"],
        )
        self._active: RowLease | None = None
        self._finished = False

    def acquire(self) -> RowLease:
        if self._active is not None:
            _fail("a lane cannot acquire a second live lattice row")
        if self._finished:
            _fail("cache lane is already exhausted")
        try:
            t_index, payload = next(self._rows)
        except StopIteration:
            self._finished = True
            raise
        lease = RowLease(
            lane_index=self.lane_index,
            t_index=t_index,
            payload=payload,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
        )
        self._active = lease
        return lease

    def release(self, lease: RowLease) -> None:
        if self._active is None or lease is not self._active:
            _fail("lattice row release does not match the live lease")
        self._active = None

    def finish(self) -> None:
        if self._active is not None:
            _fail("cannot finish a lane with a live lattice row")
        if not self._finished:
            try:
                next(self._rows)
            except StopIteration:
                self._finished = True
            else:
                _fail("cannot finish a lane before every assigned row")


def make_q_tile_receipt(
    contract: Mapping[str, Any],
    *,
    lane_index: int,
    t_index: int,
    row_payload_sha256: str,
    q_tile_index: int,
    claim_chain_before: str,
    claimed_zero_state_before_sha256: str,
    claimed_fft_pipeline_receipts_sha256: str,
    claimed_zero_consumer_receipts_sha256: str,
    claimed_zero_state_after_sha256: str,
    claimed_worker_measurement_sha256: str,
) -> dict[str, Any]:
    """Create the exact transient handoff record expected by a lane session."""

    contract_sha = _digest(contract.get("contract_sha256"), "contract digest")
    work = q_tile_descriptor(
        contract, t_index=t_index, q_tile_index=q_tile_index
    )
    claims = {
        "claimed_fft_pipeline_receipts_sha256": _digest(
            claimed_fft_pipeline_receipts_sha256,
            "claimed FFT pipeline receipt bundle",
        ),
        "claimed_zero_consumer_receipts_sha256": _digest(
            claimed_zero_consumer_receipts_sha256,
            "claimed zero-consumer receipt bundle",
        ),
        "claimed_zero_state_before_sha256": _digest(
            claimed_zero_state_before_sha256, "claimed zero state before"
        ),
        "claimed_zero_state_after_sha256": _digest(
            claimed_zero_state_after_sha256, "claimed zero state after"
        ),
        "claimed_worker_measurement_sha256": _digest(
            claimed_worker_measurement_sha256, "claimed worker measurement"
        ),
    }
    identity_record = {
        "contract_sha256": contract_sha,
        "lane_index": lane_index,
        "t_index": t_index,
        "row_payload_sha256": _digest(
            row_payload_sha256, "row payload digest"
        ),
        "work": work,
        "recovery_artifact_sha256": contract["recovery"]["artifact"]["sha256"],
        "recovery_replay_sha256": contract["recovery"]["replay_sha256"],
        "root_catalog_entry_chain_sha256": contract["root_numbers"][
            "entry_chain_sha256"
        ],
        "opaque_component_claims": claims,
    }
    identity = canonical_json_bytes(identity_record)
    claims_digest = sha256_bytes(canonical_json_bytes(claims))
    receipt: dict[str, Any] = {
        "schema": Q_TILE_RECEIPT_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "contract_sha256": contract_sha,
        "lane_index": lane_index,
        "t_index": t_index,
        "row_payload_sha256": row_payload_sha256,
        "work": work,
        "recovery_artifact_sha256": contract["recovery"]["artifact"]["sha256"],
        "recovery_replay_sha256": contract["recovery"]["replay_sha256"],
        "root_catalog_entry_chain_sha256": contract["root_numbers"][
            "entry_chain_sha256"
        ],
        "opaque_component_claims": claims,
        "claim_chain_before": _digest(
            claim_chain_before, "component claim chain before"
        ),
        "claim_chain_after": _extend_chain(
            CLAIM_CHAIN_DOMAIN, claim_chain_before, claims_digest, identity
        ),
        "decisions": {
            "at_most_one_outstanding_authenticated_row_lease": True,
            "exact_q_tile_descriptor_used": True,
            "root_catalog_parsed_and_receipt_bound_by_contract": contract[
                "root_numbers"
            ]["all_TGDRNRO1_artifacts_parsed_and_receipt_bound"],
            "FFT_zero_and_measurement_digests_claimed_not_validated": True,
            "all_claims_bound_by_ordered_receipt_chain": True,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    return receipt


class LaneHandoffSession:
    """Validate row/batch ordering and artifact-state continuity for one lane."""

    def __init__(
        self,
        contract_path: Path,
        *,
        lane_index: int,
        initial_zero_state_sha256: str,
        allow_structural_kat: bool = False,
        expected_contract_sha256: str | None = None,
    ) -> None:
        self.reader = AuthenticatedLaneReader(
            contract_path,
            lane_index=lane_index,
            allow_structural_kat=allow_structural_kat,
            expected_contract_sha256=expected_contract_sha256,
        )
        self.contract = self.reader.contract
        if self.contract["classification"] != STRUCTURAL_KAT_CLASSIFICATION:
            _fail(
                "production lane execution is disabled until typed FFT and "
                "zero-state transition validators replace opaque claims"
            )
        self.lane_index = lane_index
        contract_sha = self.contract["contract_sha256"]
        self.claim_chain = _initial_chain(contract_sha, lane_index, b"claims")
        self.row_chain = _initial_chain(contract_sha, lane_index, b"row")
        self.claimed_zero_state = _digest(
            initial_zero_state_sha256, "initial zero state"
        )
        self._lease: RowLease | None = None
        self._next_q_tile = 0
        self.rows_completed = 0
        self.q_tiles_completed = 0
        self.active_modulus_visits = 0
        self.primitive_sample_values = 0

    def begin_row(self) -> RowLease:
        if self._lease is not None:
            _fail("cannot begin a row while another row is live")
        self._lease = self.reader.acquire()
        self._next_q_tile = 0
        return self._lease

    def expected_q_tile(self) -> dict[str, Any] | None:
        if self._lease is None:
            _fail("no live lattice row")
        tile_count = self.contract["schedule"]["q_tile_count"]
        while self._next_q_tile < tile_count:
            descriptor = q_tile_descriptor(
                self.contract,
                t_index=self._lease.t_index,
                q_tile_index=self._next_q_tile,
            )
            if descriptor["active_q_count"]:
                return descriptor
            self._next_q_tile += 1
        return None

    def accept_q_tile(self, receipt: Mapping[str, Any]) -> None:
        lease = self._lease
        if lease is None:
            _fail("cannot accept a q tile without a live row")
        expected_work = self.expected_q_tile()
        if expected_work is None:
            _fail("row received a q tile after its exact work ended")
        required = {
            "schema",
            "schema_version",
            "algorithm_id",
            "contract_sha256",
            "lane_index",
            "t_index",
            "row_payload_sha256",
            "work",
            "recovery_artifact_sha256",
            "recovery_replay_sha256",
            "root_catalog_entry_chain_sha256",
            "opaque_component_claims",
            "claim_chain_before",
            "claim_chain_after",
            "decisions",
            "receipt_sha256",
        }
        if (
            not isinstance(receipt, Mapping)
            or set(receipt) != required
            or receipt.get("schema") != Q_TILE_RECEIPT_SCHEMA
            or receipt.get("schema_version") != 1
            or receipt.get("algorithm_id") != ALGORITHM_ID
            or receipt.get("contract_sha256")
            != self.contract["contract_sha256"]
            or receipt.get("lane_index") != self.lane_index
            or receipt.get("t_index") != lease.t_index
            or receipt.get("row_payload_sha256") != lease.payload_sha256
            or receipt.get("work") != expected_work
            or receipt.get("recovery_artifact_sha256")
            != self.contract["recovery"]["artifact"]["sha256"]
            or receipt.get("recovery_replay_sha256")
            != self.contract["recovery"]["replay_sha256"]
            or receipt.get("root_catalog_entry_chain_sha256")
            != self.contract["root_numbers"]["entry_chain_sha256"]
            or receipt.get("claim_chain_before") != self.claim_chain
        ):
            _fail("q-tile receipt identity, work, or input chain differs")
        claims = receipt.get("opaque_component_claims")
        required_claims = {
            "claimed_fft_pipeline_receipts_sha256",
            "claimed_zero_consumer_receipts_sha256",
            "claimed_zero_state_before_sha256",
            "claimed_zero_state_after_sha256",
            "claimed_worker_measurement_sha256",
        }
        if not isinstance(claims, dict) or set(claims) != required_claims:
            _fail("q-tile opaque component claims differ")
        if (
            claims.get("claimed_zero_state_before_sha256")
            != self.claimed_zero_state
        ):
            _fail("q-tile claimed zero-consumer input state differs")
        for name in required_claims:
            _digest(claims.get(name), f"q-tile {name}")
        decisions = receipt.get("decisions")
        if decisions != {
            "at_most_one_outstanding_authenticated_row_lease": True,
            "exact_q_tile_descriptor_used": True,
            "root_catalog_parsed_and_receipt_bound_by_contract": self.contract[
                "root_numbers"
            ]["all_TGDRNRO1_artifacts_parsed_and_receipt_bound"],
            "FFT_zero_and_measurement_digests_claimed_not_validated": True,
            "all_claims_bound_by_ordered_receipt_chain": True,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        }:
            _fail("q-tile receipt claim boundary differs")
        body = dict(receipt)
        claimed_receipt = _digest(
            body.pop("receipt_sha256", None), "batch receipt digest"
        )
        if claimed_receipt != sha256_bytes(canonical_json_bytes(body)):
            _fail("q-tile receipt self-hash differs")
        identity = canonical_json_bytes(
            {
                "contract_sha256": self.contract["contract_sha256"],
                "lane_index": self.lane_index,
                "t_index": lease.t_index,
                "row_payload_sha256": lease.payload_sha256,
                "work": expected_work,
                "recovery_artifact_sha256": self.contract["recovery"][
                    "artifact"
                ]["sha256"],
                "recovery_replay_sha256": self.contract["recovery"][
                    "replay_sha256"
                ],
                "root_catalog_entry_chain_sha256": self.contract[
                    "root_numbers"
                ]["entry_chain_sha256"],
                "opaque_component_claims": claims,
            }
        )
        claims_digest = sha256_bytes(canonical_json_bytes(claims))
        expected_claim_chain = _extend_chain(
            CLAIM_CHAIN_DOMAIN,
            self.claim_chain,
            claims_digest,
            identity,
        )
        if receipt.get("claim_chain_after") != expected_claim_chain:
            _fail("q-tile ordered component-claim chain differs")
        self.claim_chain = expected_claim_chain
        self.claimed_zero_state = claims["claimed_zero_state_after_sha256"]
        self._next_q_tile += 1
        self.q_tiles_completed += 1
        self.active_modulus_visits += expected_work["active_q_count"]
        self.primitive_sample_values += expected_work[
            "primitive_character_values"
        ]

    def finish_row(self) -> None:
        lease = self._lease
        if lease is None:
            _fail("no live row to finish")
        if self.expected_q_tile() is not None:
            _fail("cannot advance t before every active q tile is acknowledged")
        row_identity = canonical_json_bytes(
            {
                "contract_sha256": self.contract["contract_sha256"],
                "lane_index": self.lane_index,
                "t_index": lease.t_index,
                "row_payload_sha256": lease.payload_sha256,
                "component_claim_chain": self.claim_chain,
                "claimed_zero_state": self.claimed_zero_state,
            }
        )
        self.row_chain = _extend_chain(
            ROW_CHAIN_DOMAIN,
            self.row_chain,
            hashlib.sha256(row_identity).hexdigest(),
            row_identity,
        )
        self.reader.release(lease)
        self._lease = None
        self.rows_completed += 1

    def finish_lane(self) -> dict[str, Any]:
        if self._lease is not None:
            _fail("cannot finish a lane with a live row")
        self.reader.finish()
        lane = self.contract["schedule"]["lane_inventory"]["lanes"][
            self.lane_index
        ]
        if self.rows_completed != (
            lane["t_index_stop_exclusive"] - lane["t_index_start_inclusive"]
        ):
            _fail("lane completion row count differs from its assignment")
        receipt: dict[str, Any] = {
            "schema": LANE_RECEIPT_SCHEMA,
            "schema_version": 1,
            "algorithm_id": ALGORITHM_ID,
            "contract_sha256": self.contract["contract_sha256"],
            "lane_index": self.lane_index,
            "assignment": lane,
            "rows_completed": self.rows_completed,
            "q_tiles_completed": self.q_tiles_completed,
            "active_modulus_visits": self.active_modulus_visits,
            "primitive_sample_values": self.primitive_sample_values,
            "component_claim_chain_sha256": self.claim_chain,
            "claimed_zero_state_sha256": self.claimed_zero_state,
            "row_completion_chain_sha256": self.row_chain,
            "decisions": {
                "all_assigned_cache_rows_authenticated": True,
                "all_nonempty_q_tiles_acknowledged": True,
                "maximum_outstanding_authenticated_row_leases": 1,
                "root_catalog_bound_by_contract": True,
                "FFT_zero_and_measurement_digests_claimed_not_validated": True,
                "cuda_t_major_kernel_execution_attested": False,
                "zero_completeness_claimed": False,
                "external_atom_discharged": False,
            },
        }
        receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
        return receipt


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": "source_wide_supervisor_contract_not_atom_closure",
        "implemented": [
            "cache catalog/root and pinned exact eight-lane inventory binding",
            "full recovery seed manifest/artifact/replay binding",
            "exact monotone source-wide TGDRNRO1 parser/receipt catalog binding",
            "formulaic q tiles plus a non-executable q-contiguous FFT target roster",
            "typed fixed-q FFT pipeline receipt bundle validator and replay",
            (
                "separate deterministic cache-row/typed-bundle admission "
                "adapter with exact lattice-payload identity checks"
            ),
            (
                "authenticated one-copy-per-row archive and complete "
                "formulaic fixed-q run-manifest producer/replayer"
            ),
            "at most one outstanding authenticated row lease per lane",
            "one ordered hash chain binding every remaining opaque component claim",
            "claimed zero-consumer before/after state continuity",
            "fail-closed row advancement and lane completion receipts",
        ],
        "source_wide_contract_implemented": True,
        "source_wide_contract_executed": False,
        "source_performance_ready": False,
        "q_contiguous_fft_target_roster_executable": False,
        "structural_q_tile_state_machine_only": True,
        "production_lane_execution_enabled": False,
        "root_catalog_handoff_implemented": True,
        "FFT_receipt_bundle_validator_implemented": True,
        "typed_bundle_cache_row_admission_adapter_implemented": True,
        "typed_bundle_lattice_payload_identity_binding_implemented": True,
        "q_contiguous_shared_row_spool_producer_implemented": True,
        "q_contiguous_spool_pipeline_executor_integrated": False,
        "FFT_receipt_bundle_integrated_into_t_major_lane": False,
        "discarded_FFT_stream_arithmetic_independently_replayed": False,
        "zero_state_transition_validator_implemented": False,
        "cuda_t_major_kernel_adapter_implemented": True,
        "authenticated_TGDLTMB1_input_and_replay_implemented": True,
        "direct_MPFR_factor_and_exact_tail_source_implemented": True,
        "remaining_kernel_seam": (
            "connect the row-resident TGDLTMB1 CUDA output stream to a "
            "persistent multi-q all-character/completed-L worker with "
            "authenticated zero-state import/export"
        ),
        "zero_isolation_or_turing_complete": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "AuthenticatedLaneReader",
    "CONTRACT_SCHEMA",
    "CONTRACT_CLASSIFICATIONS",
    "DEFAULT_Q_BATCH_SIZE",
    "DEFAULT_Q_TILE_SIZE",
    "DirichletSourceSupervisorError",
    "FFT_BATCH_SIZE",
    "LANE_RECEIPT_SCHEMA",
    "LaneHandoffSession",
    "PINNED_SOURCE_FFT_BATCHES",
    "PINNED_SOURCE_LANE_FFT_BATCHES",
    "Q_TILE_RECEIPT_SCHEMA",
    "RowLease",
    "SOURCE_CONTRACT_CLASSIFICATION",
    "STRUCTURAL_KAT_CLASSIFICATION",
    "build_source_contract",
    "build_structural_kat_contract",
    "capability",
    "fft_batch_descriptor",
    "load_contract",
    "make_q_tile_receipt",
    "q_batch_descriptor",
    "q_tile_descriptor",
]
