# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Storage accounting and fail-closed primitives for Dirichlet t blocks.

The bounded native t-block KAT can deliberately produce an indeterminate
completed-L event for every primitive sample.  Retaining those verbose JSON
events is useful for an adversarial KAT, but linearly projecting that layout
to the source campaign is not a viable storage design.

This module keeps three separate facts explicit:

* exact byte accounting for a materialized campaign directory;
* a small content-addressed immutable chunk store and a bounded-memory event
  stream admission pass; and
* a production preflight that remains closed until compact event admission is
  sufficient for resume and raw event streams need not be retained.

The content-addressed store and streaming admission are real bounded
implementations.  They are not zero-completeness evidence and do not, by
themselves, discharge Platt's theorem.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, BinaryIO, Mapping, NoReturn

from tg_verifier.dirichlet_compact_state_binary import (
    AMBIGUITY_RANGE_RECORD,
    ARTIFACT_HEADER,
    BRACKET_RECORD,
    CHARACTER_RECORD,
    DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    MAXIMUM_ARTIFACT_BYTES,
)
from tg_verifier.dirichlet_fft_pipeline_bundle import _validate_events
from tg_verifier.dirichlet_lattice_cache import canonical_json_bytes


SOURCE_FIXED_Q_TARGET_COUNT = 76_770_217
SOURCE_TARGET_ROW_REFERENCE_COUNT = 4_901_051_274
SOURCE_UNIQUE_T_ROW_COUNT = 127_988
SOURCE_UNIQUE_ROW_PAYLOAD_BYTES = 134_205_145_088
SOURCE_LARGE_Q_MODULUS_COUNT = 390_000
SOURCE_LARGE_Q_PRIMITIVE_CHARACTER_STATE_COUNT = 29_547_446_729
SOURCE_TGDCSB02_FIXED_INDEX_BYTES = 3_073_003_099_816
Q10001_ALL_AMBIGUOUS_TGDCSB02_BYTES = 1_150_376

INVENTORY_SCHEMA = "sparkinterval.tg.dirichlet_tblock.storage_inventory.v1"
PROJECTION_SCHEMA = "sparkinterval.tg.dirichlet_tblock.storage_projection.v1"
EVENT_ADMISSION_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock.event_stream_admission.v1"
)
CAS_OBJECT_SCHEMA = "sparkinterval.tg.content_addressed_chunk.v1"
STORAGE_BOUNDARY_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock.storage_boundary.v1"
)
COMPACT_STATE_STORAGE_MODEL_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock.compact_state_storage_model.v1"
)

MAXIMUM_CAS_CHUNK_BYTES = 2 * 1024 * 1024 * 1024
MAXIMUM_EVENT_ADMISSION_BYTES = 2 * 1024 * 1024 * 1024


class DirichletTBlockStorageError(RuntimeError):
    """A storage artifact, bound, or source-scale precondition failed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTBlockStorageError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not a lowercase SHA-256 digest")
    return value


def _positive_integer(
    value: object,
    label: str,
    *,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{label} must be a positive integer")
    if maximum is not None and value > maximum:
        _fail(f"{label} exceeds its fixed bound")
    return value


def _self_hash(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(body)
    result[field] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return result


def _category(relative: Path) -> str:
    parts = relative.parts
    name = relative.name
    if parts and parts[0] == "cache":
        return "cache"
    if relative == Path("spool") or name == "spool.receipt.json":
        return "spool"
    if parts and parts[0] == "target-inputs":
        if len(parts) > 1 and parts[1].startswith("roots-q-"):
            return "target_roots"
        if name == "lattice-input.bin":
            return "target_lattice_inputs"
        if name == "lattice-output.bin":
            return "target_lattice_outputs"
        if name == "finite-recovery.bin":
            return "target_finite_recovery"
        return "target_controls_and_receipts"
    if parts and parts[0] == "worker-output":
        if name == "events.ndjson":
            return "worker_raw_events"
        if name == "typed-bundle.json":
            return "worker_typed_bundles"
        return "worker_pipeline_other"
    if (
        len(parts) >= 2
        and parts[0] == "checkpoints"
        and parts[1] == "typed-bundles"
    ):
        return "checkpoint_staged_typed_bundles"
    if parts and parts[0] == "checkpoints":
        return "checkpoint_records"
    return "campaign_metadata"


def _target_identity(relative: Path) -> str | None:
    parts = relative.parts
    if len(parts) < 3:
        return None
    if parts[0] not in {"target-inputs", "worker-output"}:
        return None
    if not parts[1].startswith("block-") or not parts[2].startswith("q-"):
        return None
    return f"{parts[1]}/{parts[2]}"


def inventory_campaign(root: Path) -> dict[str, Any]:
    """Return exact logical and unique-inode bytes by storage component."""

    root = root.resolve()
    if not root.is_dir() or root.is_symlink():
        _fail("campaign root is not a non-symlink directory")
    categories: dict[str, dict[str, int]] = {}
    targets: dict[str, dict[str, int]] = {}
    seen_inodes: set[tuple[int, int]] = set()
    total_logical = 0
    total_unique_inode = 0
    total_allocated = 0
    file_count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            _fail(f"campaign inventory refuses symlink: {path}")
        if not path.is_file():
            continue
        status = path.stat()
        if not stat.S_ISREG(status.st_mode):
            _fail(f"campaign inventory found a non-regular file: {path}")
        relative = path.relative_to(root)
        category = _category(relative)
        row = categories.setdefault(
            category,
            {
                "file_count": 0,
                "logical_bytes": 0,
                "allocated_bytes": 0,
                "unique_inode_bytes": 0,
            },
        )
        row["file_count"] += 1
        row["logical_bytes"] += status.st_size
        allocated = status.st_blocks * 512
        row["allocated_bytes"] += allocated
        total_allocated += allocated
        inode = (status.st_dev, status.st_ino)
        if inode not in seen_inodes:
            seen_inodes.add(inode)
            row["unique_inode_bytes"] += status.st_size
            total_unique_inode += status.st_size
        total_logical += status.st_size
        file_count += 1
        target = _target_identity(relative)
        if target is not None:
            target_row = targets.setdefault(
                target,
                {
                    "row_file_count": 0,
                    "lattice_input_bytes": 0,
                    "lattice_output_bytes": 0,
                    "finite_recovery_bytes": 0,
                    "raw_event_bytes": 0,
                    "worker_typed_bundle_bytes": 0,
                    "worker_other_bytes": 0,
                    "target_control_bytes": 0,
                },
            )
            if category == "target_lattice_inputs":
                target_row["row_file_count"] += 1
                target_row["lattice_input_bytes"] += status.st_size
            elif category == "target_lattice_outputs":
                target_row["lattice_output_bytes"] += status.st_size
            elif category == "target_finite_recovery":
                target_row["finite_recovery_bytes"] += status.st_size
            elif category == "worker_raw_events":
                target_row["raw_event_bytes"] += status.st_size
            elif category == "worker_typed_bundles":
                target_row["worker_typed_bundle_bytes"] += status.st_size
            elif category == "worker_pipeline_other":
                target_row["worker_other_bytes"] += status.st_size
            elif category == "target_controls_and_receipts":
                target_row["target_control_bytes"] += status.st_size
    body = {
        "schema": INVENTORY_SCHEMA,
        "schema_version": 1,
        "classification": (
            "exact_filesystem_inventory_not_source_runtime_or_proof_evidence"
        ),
        "root": str(root),
        "file_count": file_count,
        "logical_bytes": total_logical,
        "allocated_bytes": total_allocated,
        "unique_inode_bytes": total_unique_inode,
        "categories": dict(sorted(categories.items())),
        "targets": dict(sorted(targets.items())),
        "source_scale_run": False,
        "external_atom_discharged": False,
    }
    return _self_hash(body, "inventory_sha256")


def _scaled_bytes(
    measured_bytes: int,
    measured_units: int,
    source_units: int,
) -> int:
    if measured_bytes < 0 or measured_units <= 0 or source_units <= 0:
        _fail("projection inputs are outside their positive bounds")
    return (
        measured_bytes * source_units + measured_units - 1
    ) // measured_units


def project_source_scale(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Naively linearize one KAT inventory; never call it a production model."""

    categories = inventory.get("categories")
    targets = inventory.get("targets")
    if not isinstance(categories, dict) or not isinstance(targets, dict):
        _fail("storage projection requires one exact campaign inventory")
    target_rows = sum(
        int(row.get("row_file_count", 0))
        for row in targets.values()
        if isinstance(row, dict)
    )
    if target_rows <= 0:
        _fail("storage projection has no measured target-row references")
    event_bytes = int(
        categories.get("worker_raw_events", {}).get("logical_bytes", 0)
    )
    target_input_bytes = sum(
        int(categories.get(name, {}).get("logical_bytes", 0))
        for name in (
            "target_lattice_inputs",
            "target_lattice_outputs",
            "target_finite_recovery",
        )
    )
    typed_bundle_bytes = sum(
        int(categories.get(name, {}).get("logical_bytes", 0))
        for name in (
            "worker_typed_bundles",
            "checkpoint_staged_typed_bundles",
        )
    )
    measured_targets = sum(
        1
        for row in targets.values()
        if isinstance(row, dict)
        and int(row.get("worker_typed_bundle_bytes", 0)) > 0
    )
    if measured_targets <= 0:
        _fail("storage projection has no measured typed-bundle targets")
    positive_event_rows = sum(
        int(row.get("row_file_count", 0))
        for row in targets.values()
        if isinstance(row, dict)
        and int(row.get("raw_event_bytes", 0)) > 1024
    )
    positive_event_bytes = sum(
        int(row.get("raw_event_bytes", 0))
        for row in targets.values()
        if isinstance(row, dict)
        and int(row.get("raw_event_bytes", 0)) > 1024
    )
    average_event_projection = _scaled_bytes(
        event_bytes,
        target_rows,
        SOURCE_TARGET_ROW_REFERENCE_COUNT,
    )
    worst_observed_event_projection = (
        _scaled_bytes(
            positive_event_bytes,
            positive_event_rows,
            SOURCE_TARGET_ROW_REFERENCE_COUNT,
        )
        if positive_event_rows
        else 0
    )
    target_input_projection = _scaled_bytes(
        target_input_bytes,
        target_rows,
        SOURCE_TARGET_ROW_REFERENCE_COUNT,
    )
    typed_bundle_projection = _scaled_bytes(
        typed_bundle_bytes,
        measured_targets,
        SOURCE_FIXED_Q_TARGET_COUNT,
    )
    body = {
        "schema": PROJECTION_SCHEMA,
        "schema_version": 1,
        "classification": (
            "naive_linear_kat_projection_not_a_physical_production_estimate"
        ),
        "measured": {
            "target_count": measured_targets,
            "target_row_reference_count": target_rows,
            "positive_event_target_row_reference_count": positive_event_rows,
            "raw_event_bytes": event_bytes,
            "positive_event_bytes": positive_event_bytes,
            "per_target_input_bytes": target_input_bytes,
            "typed_bundle_and_checkpoint_bytes": typed_bundle_bytes,
        },
        "source_constants": {
            "fixed_q_target_count": SOURCE_FIXED_Q_TARGET_COUNT,
            "target_row_reference_count": SOURCE_TARGET_ROW_REFERENCE_COUNT,
            "unique_t_row_count": SOURCE_UNIQUE_T_ROW_COUNT,
            "unique_row_payload_bytes": SOURCE_UNIQUE_ROW_PAYLOAD_BYTES,
        },
        "projected_bytes": {
            "raw_events_at_all_target_average": average_event_projection,
            "raw_events_at_positive_event_target_average": (
                worst_observed_event_projection
            ),
            "per_q_copied_target_inputs": target_input_projection,
            "typed_bundles_and_checkpoint_copies": typed_bundle_projection,
            "unique_row_payload_cas": SOURCE_UNIQUE_ROW_PAYLOAD_BYTES,
            "cache_plus_duplicate_spool": (
                2 * SOURCE_UNIQUE_ROW_PAYLOAD_BYTES
            ),
            "row_transport_if_each_unique_row_sent_once": (
                SOURCE_UNIQUE_ROW_PAYLOAD_BYTES
            ),
        },
        "decisions": {
            "projection_is_source_feasibility_evidence": False,
            "per_q_row_payload_copies_permitted_at_source_scale": False,
            "raw_event_retention_permitted_at_source_scale": False,
            "content_addressed_unique_row_reuse_required": True,
            "streamed_compact_event_admission_required": True,
            "source_scale_admitted": False,
        },
    }
    return _self_hash(body, "projection_sha256")


@dataclass(frozen=True)
class ContentAddressedObject:
    """One immutable object admitted to a hash-addressed store."""

    path: Path
    sha256: str
    size_bytes: int
    reused: bool

    def record(self) -> dict[str, Any]:
        body = {
            "schema": CAS_OBJECT_SCHEMA,
            "schema_version": 1,
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "reused_existing_object": self.reused,
            "external_atom_discharged": False,
        }
        return _self_hash(body, "record_sha256")


class ContentAddressedChunkStore:
    """A bounded immutable SHA-256 object store with hard-linked references."""

    def __init__(self, root: Path, *, maximum_chunk_bytes: int = MAXIMUM_CAS_CHUNK_BYTES):
        self.root = root.resolve()
        self.maximum_chunk_bytes = _positive_integer(
            maximum_chunk_bytes,
            "maximum CAS chunk bytes",
            maximum=MAXIMUM_CAS_CHUNK_BYTES,
        )
        if self.root.exists():
            if not self.root.is_dir() or self.root.is_symlink():
                _fail("CAS root is not a non-symlink directory")
        else:
            self.root.mkdir(parents=True)
        self.objects = self.root / "objects"
        if self.objects.exists():
            if not self.objects.is_dir() or self.objects.is_symlink():
                _fail("CAS object root is not a non-symlink directory")
        else:
            self.objects.mkdir()

    def _object_path(self, sha256: str) -> Path:
        digest = _digest(sha256, "CAS object")
        bucket = self.objects / digest[:2]
        if bucket.exists():
            if not bucket.is_dir() or bucket.is_symlink():
                _fail("CAS bucket is not a non-symlink directory")
        else:
            bucket.mkdir()
        return bucket / digest

    @staticmethod
    def _validate_existing(
        path: Path,
        *,
        expected_sha256: str,
        expected_size: int,
    ) -> None:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise DirichletTBlockStorageError(
                "cannot open existing CAS object without following links"
            ) from error
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(descriptor, "rb") as source:
            status = os.fstat(source.fileno())
            if not stat.S_ISREG(status.st_mode):
                _fail("existing CAS object is not a regular file")
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        if size != expected_size or digest.hexdigest() != expected_sha256:
            _fail("existing CAS object is substituted")

    def put_stream(self, source: BinaryIO) -> ContentAddressedObject:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".incoming-", dir=self.objects
        )
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(descriptor, "wb") as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.maximum_chunk_bytes:
                        _fail("CAS input exceeds its fixed chunk bound")
                    digest.update(chunk)
                    output.write(chunk)
                if size == 0:
                    _fail("CAS refuses an empty object")
                output.flush()
                os.fsync(output.fileno())
            sha256 = digest.hexdigest()
            destination = self._object_path(sha256)
            reused = destination.exists()
            if reused:
                self._validate_existing(
                    destination,
                    expected_sha256=sha256,
                    expected_size=size,
                )
            else:
                try:
                    os.link(temporary, destination)
                except FileExistsError:
                    self._validate_existing(
                        destination,
                        expected_sha256=sha256,
                        expected_size=size,
                    )
                    reused = True
                os.chmod(destination, 0o444)
            temporary.unlink()
            return ContentAddressedObject(
                path=destination.resolve(),
                sha256=sha256,
                size_bytes=size,
                reused=reused,
            )
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def put_file(self, path: Path) -> ContentAddressedObject:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise DirichletTBlockStorageError(
                "cannot open CAS input without following links"
            ) from error
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                _fail("CAS input is not a regular file")
            return self.put_stream(source)

    def link_reference(
        self,
        sha256: str,
        destination: Path,
        *,
        expected_size: int,
    ) -> Path:
        source = self._object_path(sha256)
        self._validate_existing(
            source,
            expected_sha256=sha256,
            expected_size=_positive_integer(
                expected_size,
                "CAS reference size",
                maximum=self.maximum_chunk_bytes,
            ),
        )
        destination = destination.resolve()
        if destination.exists() or destination.is_symlink():
            _fail("refusing to replace a CAS reference")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, destination)
        return destination


def admit_event_stream(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    q: int,
    primitive_characters: int,
    frame_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
    maximum_bytes: int = MAXIMUM_EVENT_ADMISSION_BYTES,
) -> dict[str, Any]:
    """Semantically validate an event file in bounded memory.

    The returned compact receipt records the independent streaming decision,
    but current typed-bundle resume still reparses the raw file.  Consequently
    callers must retain the raw artifact and this receipt is not yet a
    deletion authorization.
    """

    size = _positive_integer(
        expected_size,
        "expected event bytes",
        maximum=_positive_integer(
            maximum_bytes,
            "maximum event admission bytes",
            maximum=MAXIMUM_EVENT_ADMISSION_BYTES,
        ),
    )
    sha256 = _digest(expected_sha256, "expected event stream")
    event_count, sign_changes, indeterminates = _validate_events(
        path,
        expected_sha256=sha256,
        expected_size=size,
        q=q,
        primitive_characters=primitive_characters,
        frame_count=frame_count,
        first_t_numerator=first_t_numerator,
        stop_t_numerator=stop_t_numerator,
    )
    body = {
        "schema": EVENT_ADMISSION_SCHEMA,
        "schema_version": 1,
        "classification": (
            "bounded_memory_semantic_event_admission_not_zero_completeness"
        ),
        "event_artifact": {
            "path": str(path.resolve()),
            "sha256": sha256,
            "size_bytes": size,
        },
        "q": q,
        "primitive_character_count": primitive_characters,
        "frame_count": frame_count,
        "first_t_numerator": first_t_numerator,
        "stop_t_numerator": stop_t_numerator,
        "event_count": event_count,
        "sign_change_count": sign_changes,
        "indeterminate_count": indeterminates,
        "bounded_memory_streaming_validation": True,
        "raw_event_artifact_still_required_for_resume": True,
        "authorizes_raw_event_deletion": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    return _self_hash(body, "admission_sha256")


def compact_state_storage_model() -> dict[str, Any]:
    """Return exact TGDCSB02 arithmetic and clearly labelled KAT timings."""

    fixed_source_bytes = (
        SOURCE_LARGE_Q_MODULUS_COUNT * ARTIFACT_HEADER.size
        + SOURCE_LARGE_Q_PRIMITIVE_CHARACTER_STATE_COUNT
        * CHARACTER_RECORD.size
    )
    q10001_all_ambiguous = (
        ARTIFACT_HEADER.size
        + 9_585 * CHARACTER_RECORD.size
        + 9_585 * AMBIGUITY_RANGE_RECORD.size
    )
    if (
        fixed_source_bytes != SOURCE_TGDCSB02_FIXED_INDEX_BYTES
        or q10001_all_ambiguous
        != Q10001_ALL_AMBIGUOUS_TGDCSB02_BYTES
    ):
        _fail("TGDCSB02 pinned storage arithmetic changed")
    body = {
        "schema": COMPACT_STATE_STORAGE_MODEL_SCHEMA,
        "schema_version": 1,
        "classification": (
            "exact_binary_layout_and_observed_kat_runtime_"
            "not_source_feasibility"
        ),
        "binary_layout": {
            "magic": "TGDCSB02",
            "header_bytes_per_q": ARTIFACT_HEADER.size,
            "character_index_bytes": CHARACTER_RECORD.size,
            "maximal_ambiguity_range_bytes": (
                AMBIGUITY_RANGE_RECORD.size
            ),
            "ordered_bracket_bytes": BRACKET_RECORD.size,
            "exact_size_equation": (
                "176 + 104*characters + 16*maximal_ambiguity_ranges "
                "+ 32*ordered_brackets"
            ),
            "default_maximum_bytes_per_q": (
                DEFAULT_MAXIMUM_ARTIFACT_BYTES
            ),
            "hard_maximum_bytes_per_q": MAXIMUM_ARTIFACT_BYTES,
        },
        "bounded_known_answers": {
            "q10001_primitive_character_count": 9_585,
            "q10001_one_range_per_character_bytes": (
                q10001_all_ambiguous
            ),
            "q10002_zero_character_bytes": ARTIFACT_HEADER.size,
            "three_lane_q10001_input_binary_bytes": (
                3 * q10001_all_ambiguous
            ),
            "three_lane_q10001_output_binary_bytes": (
                q10001_all_ambiguous
            ),
        },
        "source_fixed_index_floor": {
            "q_start": 10_001,
            "q_stop": 400_000,
            "modulus_count": SOURCE_LARGE_Q_MODULUS_COUNT,
            "primitive_character_state_count": (
                SOURCE_LARGE_Q_PRIMITIVE_CHARACTER_STATE_COUNT
            ),
            "header_plus_character_index_bytes": fixed_source_bytes,
            "includes_ambiguity_ranges": False,
            "includes_bracket_records": False,
            "fits_hard_total_finalizer_bound": False,
        },
        "illustrative_sparse_scale": {
            "label": (
                "arithmetic_at_3.8e13_brackets_not_an_exact_source_count"
            ),
            "bracket_count": 38_000_000_000_000,
            "bracket_record_bytes": 1_216_000_000_000_000,
            "source_projection_admitted": False,
        },
        "observed_2026_07_23_kats": {
            "medium_two_block_q10001_q10002": {
                "unittest_elapsed_seconds": 56.255,
                "process_wall_seconds": 56.33,
                "process_max_rss_kib": 121_628,
                "filesystem_output_counter": 1_264_448,
                "filesystem_output_counter_units": (
                    "platform_reported_blocks_not_artifact_bytes"
                ),
            },
            "three_lane_q10001_synthetic_finalizer": {
                "characters": 9_585,
                "samples_per_lane": 64,
                "lane_count": 3,
                "finalizer_elapsed_seconds": 1.427,
                "whole_process_elapsed_seconds": 2.20,
                "whole_process_max_rss_kib": 104_620,
            },
            "runtime_is_source_projection": False,
        },
        "source_scale_state_encoding": False,
        "source_scale_storage_admitted": False,
        "turing_completeness": False,
        "external_atom_discharged": False,
    }
    return _self_hash(body, "model_sha256")


def storage_boundary() -> dict[str, Any]:
    """State the implemented safeguards and the still-closed source seam."""

    body = {
        "schema": STORAGE_BOUNDARY_SCHEMA,
        "schema_version": 1,
        "classification": (
            "fail_closed_source_storage_preflight_not_execution_evidence"
        ),
        "implemented": {
            "exact_campaign_byte_inventory": True,
            "naive_projection_warning": True,
            "content_addressed_chunk_store": True,
            "bounded_memory_event_semantic_admission": True,
            "bounded_native_kat_event_output_limit": True,
            "bounded_native_kat_retained_output_limit": True,
            "bounded_compact_event_summary": True,
            "compact_event_resume_without_raw_records": True,
            "associative_per_character_cross_block_state": True,
            "canonical_bounded_q_major_binary_restart_state": True,
            "binary_state_checkpoint_and_resume_replay": True,
            "exact_maximal_ambiguity_range_retention": True,
            "ordered_exact_bracket_retention": True,
            "same_rule_cross_lane_q_state_finalizer": True,
            "canonical_sparse_offsets_and_lengths": True,
        },
        "required_for_source_scale": {
            "unique_t_row_payload_cas": True,
            "q_specific_inputs_as_bounded_sidecars_or_streamed_chunks": True,
            "event_semantics_admitted_while_streaming": True,
            "direct_binary_state_reduction_without_large_json_rosters": True,
            "exact_maximal_ambiguity_ranges_for_refinement": True,
            "upsampling_and_refinement_artifact_closure": True,
            "paired_turing_total_zero_count": True,
            "externally_pinned_campaign_storage_budget": True,
        },
        "not_yet_implemented": {
            "pipeline_reads_unique_row_cas_plus_q_sidecars": True,
            "source_scale_direct_binary_state_producer": True,
            "exception_refinement_and_upsampling": True,
            "turing_and_zero_completeness": True,
        },
        "compact_state_storage_model": compact_state_storage_model(),
        "source_scale_storage_admitted": False,
        "source_scale_run": False,
        "external_atom_discharged": False,
    }
    return _self_hash(body, "boundary_sha256")


def require_source_scale_storage_ready() -> NoReturn:
    """Unconditionally close production until every storage seam above exists."""

    _fail(
        "source-scale storage is not admitted: bounded compact-state resume "
        "is implemented, but the fixed-q pipeline does not yet consume unique "
        "t-row CAS objects plus bounded q sidecars; TGDCSB02 fixed character "
        "indexes alone project to 3,073,003,099,816 bytes before sparse "
        "records, and refinement/Turing closure artifacts remain absent"
    )


__all__ = [
    "ContentAddressedChunkStore",
    "ContentAddressedObject",
    "DirichletTBlockStorageError",
    "SOURCE_FIXED_Q_TARGET_COUNT",
    "SOURCE_LARGE_Q_MODULUS_COUNT",
    "SOURCE_LARGE_Q_PRIMITIVE_CHARACTER_STATE_COUNT",
    "SOURCE_TARGET_ROW_REFERENCE_COUNT",
    "SOURCE_TGDCSB02_FIXED_INDEX_BYTES",
    "SOURCE_UNIQUE_ROW_PAYLOAD_BYTES",
    "SOURCE_UNIQUE_T_ROW_COUNT",
    "admit_event_stream",
    "compact_state_storage_model",
    "inventory_campaign",
    "project_source_scale",
    "require_source_scale_storage_ready",
    "storage_boundary",
]
