# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed cache-row admission for typed t-major FFT bundles.

This adapter closes one narrow identity and ordering seam.  It authenticates
the exact cache rows assigned to one source-supervisor lane, then admits every
fixed-q FFT bundle in deterministic ``(q, first_t_index)`` order only after a
fresh typed-bundle replay proves that its ``TGDLATI1`` lattice payloads are
byte-for-byte the authenticated cache rows for that target.

It is not the row-resident CUDA kernel, a source-scale transpose, or a
zero-state import/export implementation.  The adapter receipt therefore binds
transport identity and typed component receipts while keeping all CUDA,
zero-completeness, Turing, attestation, and external-atom decisions false.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, BinaryIO, Mapping, NoReturn

from tg_verifier.dirichlet_fft_pipeline_bundle import replay_bundle
from tg_verifier.dirichlet_lattice_cache import canonical_json_bytes
from tg_verifier.dirichlet_lattice_stage import maximum_t_index
from tg_verifier.dirichlet_source_supervisor import (
    FFT_BATCH_SIZE,
    SOURCE_CONTRACT_CLASSIFICATION,
    STRUCTURAL_KAT_CLASSIFICATION,
    AuthenticatedLaneReader,
    fft_batch_descriptor,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-t-major-typed-bundle-adapter-v1"
ADMISSION_SCHEMA = "sparkinterval.tg.dirichlet_tmajor_adapter.admission.v1"
LANE_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_adapter.lane_receipt.v1"
)
PRODUCTION_CLASSIFICATION = (
    "production_input_admission_not_cuda_or_zero_closure"
)
STRUCTURAL_CLASSIFICATION = (
    "bounded_structural_adapter_kat_not_cuda_or_zero_closure"
)
MANIFEST_LINE_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_adapter.bundle_manifest.v1"
)
MAXIMUM_MANIFEST_LINE_BYTES = 16 * 1024
Q_MAJOR_TARGET_ORDER = "q_major_then_t_block"
BLOCK_MAJOR_TARGET_ORDER = "t_block_major_then_q"

ROW_SCHEDULE_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tmajor-adapter/row-schedule/v1\0"
)
ADMISSION_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tmajor-adapter/admission-chain/v1\0"
)

_HEX = frozenset("0123456789abcdef")


class DirichletTMajorAdapterError(RuntimeError):
    """A cache row, typed bundle, schedule, or manifest failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTMajorAdapterError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(f"{label} is not a lowercase SHA-256 digest")
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


def _extend_chain(before: str, record: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(ADMISSION_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(before))
    digest.update(hashlib.sha256(canonical_json_bytes(dict(record))).digest())
    return digest.hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        _fail(f"refusing to replace immutable adapter receipt: {path}")
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


def _normalized_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        _fail(f"{label} is malformed")
    path = Path(value)
    if not path.is_absolute() or str(path.resolve()) != value:
        _fail(f"{label} is not an absolute normalized path")
    return path


def _open_pinned_manifest(
    path: Path,
    *,
    expected_sha256: str,
) -> tuple[BinaryIO, dict[str, Any]]:
    expected_sha256 = _digest(expected_sha256, "expected bundle manifest")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletTMajorAdapterError(
            f"cannot open bundle manifest without following links: {path}"
        ) from error
    source = os.fdopen(descriptor, "rb")
    try:
        status = os.fstat(source.fileno())
        if not stat.S_ISREG(status.st_mode) or status.st_size <= 0:
            _fail("bundle manifest is empty or not a regular file")
        digest = hashlib.sha256()
        size = 0
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
        if digest.hexdigest() != expected_sha256:
            _fail("bundle manifest differs from its externally pinned digest")
        source.seek(0)
        return source, {
            "path": str(path.resolve()),
            "sha256": expected_sha256,
            "size_bytes": size,
        }
    except BaseException:
        source.close()
        raise


class TMajorTypedBundleLaneAdapter:
    """Authenticate one lane, then admit its complete typed FFT roster."""

    def __init__(
        self,
        contract_path: Path,
        *,
        lane_index: int,
        allow_structural_kat: bool = False,
        expected_contract_sha256: str | None = None,
        target_order: str = Q_MAJOR_TARGET_ORDER,
    ) -> None:
        if target_order not in {
            Q_MAJOR_TARGET_ORDER,
            BLOCK_MAJOR_TARGET_ORDER,
        }:
            _fail("typed-bundle target order is unsupported")
        self.reader = AuthenticatedLaneReader(
            contract_path,
            lane_index=lane_index,
            allow_structural_kat=allow_structural_kat,
            expected_contract_sha256=expected_contract_sha256,
        )
        self.contract_path = contract_path.resolve()
        self.contract = self.reader.contract
        self.lane_index = lane_index
        self.allow_structural_kat = allow_structural_kat
        self.expected_contract_sha256 = expected_contract_sha256
        self.target_order = target_order
        lane = self.contract["schedule"]["lane_inventory"]["lanes"][lane_index]
        self.lane_start = _integer(
            lane.get("t_index_start_inclusive"),
            "lane t start",
            minimum=0,
        )
        self.lane_stop = _integer(
            lane.get("t_index_stop_exclusive"),
            "lane t stop",
            minimum=self.lane_start + 1,
        )
        self._expected_row_count = self.lane_stop - self.lane_start
        self._row_payload_sha256: list[str] = []
        self._row_hasher = hashlib.sha256(ROW_SCHEDULE_DOMAIN)
        self._row_hasher.update(lane_index.to_bytes(4, "little"))
        self._rows_finished = False
        self._row_schedule_sha256: str | None = None
        self._q_start = _integer(
            self.contract["schedule"].get("q_start_inclusive"),
            "q start",
            minimum=10_001,
        )
        self._next_q = self._q_start
        self._q_stop = _integer(
            self.contract["schedule"].get("q_stop_inclusive"),
            "q stop",
            minimum=self._q_start,
        )
        self._next_t = self.lane_start
        self._next_block_start = self.lane_start
        self._next_block_q = self._q_start
        self._admission_chain: str | None = None
        self._admission_count = 0
        self._finished = False

    def authenticate_next_row(self) -> dict[str, Any]:
        """Authenticate and release exactly the next deterministic cache row."""

        if self._rows_finished:
            _fail("all assigned cache rows are already authenticated")
        lease = self.reader.acquire()
        expected_t = self.lane_start + len(self._row_payload_sha256)
        if lease.lane_index != self.lane_index or lease.t_index != expected_t:
            _fail("cache reader returned a row outside deterministic lane order")
        payload_sha256 = _digest(
            lease.payload_sha256, "authenticated cache-row payload"
        )
        self._row_hasher.update(lease.t_index.to_bytes(8, "little"))
        self._row_hasher.update(bytes.fromhex(payload_sha256))
        self._row_payload_sha256.append(payload_sha256)
        self.reader.release(lease)
        return {
            "lane_index": self.lane_index,
            "t_index": lease.t_index,
            "payload_sha256": payload_sha256,
        }

    def authenticate_all_rows(self) -> dict[str, Any]:
        if self._rows_finished:
            _fail("assigned cache-row schedule was already finalized")
        while len(self._row_payload_sha256) < self._expected_row_count:
            self.authenticate_next_row()
        self.reader.finish()
        self._rows_finished = True
        self._row_schedule_sha256 = self._row_hasher.hexdigest()
        initial = hashlib.sha256(ADMISSION_CHAIN_DOMAIN)
        initial.update(
            bytes.fromhex(
                _digest(
                    self.contract.get("contract_sha256"),
                    "source contract",
                )
            )
        )
        initial.update(self.lane_index.to_bytes(4, "little"))
        initial.update(bytes.fromhex(self._row_schedule_sha256))
        initial.update(self.target_order.encode("ascii") + b"\0")
        self._admission_chain = initial.hexdigest()
        return {
            "lane_index": self.lane_index,
            "t_index_start_inclusive": self.lane_start,
            "t_index_stop_exclusive": self.lane_stop,
            "row_count": len(self._row_payload_sha256),
            "row_schedule_sha256": self._row_schedule_sha256,
            "target_order": self.target_order,
        }

    def expected_target(self) -> dict[str, Any] | None:
        if not self._rows_finished:
            _fail("typed bundles cannot be admitted before every row is authenticated")
        if self.target_order == Q_MAJOR_TARGET_ORDER:
            while self._next_q <= self._q_stop:
                active_stop = min(
                    self.lane_stop,
                    maximum_t_index(self._next_q) + 1,
                )
                if self._next_t < active_stop:
                    return fft_batch_descriptor(
                        self.contract,
                        lane_index=self.lane_index,
                        q=self._next_q,
                        first_t_index=self._next_t,
                    )
                self._next_q += 1
                self._next_t = self.lane_start
            return None
        while self._next_block_start < self.lane_stop:
            while self._next_block_q <= self._q_stop:
                q = self._next_block_q
                if self._next_block_start <= maximum_t_index(q):
                    return fft_batch_descriptor(
                        self.contract,
                        lane_index=self.lane_index,
                        q=q,
                        first_t_index=self._next_block_start,
                    )
                self._next_block_q += 1
            self._next_block_start += FFT_BATCH_SIZE
            self._next_block_q = self._q_start
        return None

    def accept_bundle(
        self,
        bundle_path: Path,
        *,
        expected_bundle_sha256: str,
        control_base: Path | None = None,
    ) -> dict[str, Any]:
        """Freshly replay and admit exactly the next fixed-q typed bundle."""

        if self._finished:
            _fail("adapter lane is already finished")
        descriptor = self.expected_target()
        if descriptor is None:
            _fail("bundle supplied after the exact lane roster ended")
        expected_bundle_sha256 = _digest(
            expected_bundle_sha256, "expected typed bundle"
        )
        replay = replay_bundle(
            bundle_path,
            contract_path=self.contract_path,
            control_base=control_base,
            allow_structural_kat=self.allow_structural_kat,
            expected_bundle_sha256=expected_bundle_sha256,
            expected_contract_sha256=self.expected_contract_sha256,
            _validated_contract=self.contract,
        )
        if (
            replay.get("accepted") is not True
            or replay.get("source_contract_sha256")
            != self.contract["contract_sha256"]
            or replay.get("q") != descriptor["q"]
            or replay.get("first_t_index") != descriptor["first_t_index"]
            or replay.get("t_index_stop_exclusive")
            != descriptor["t_index_stop_exclusive"]
        ):
            _fail("typed bundle does not cover the next deterministic target")
        if (
            self.contract["classification"] == SOURCE_CONTRACT_CLASSIFICATION
            and replay.get("all_composition_inputs_certified") is not True
        ):
            _fail("production adapter requires certified composition inputs")
        start = descriptor["first_t_index"] - self.lane_start
        stop = descriptor["t_index_stop_exclusive"] - self.lane_start
        expected_rows = [
            {
                "t_index": self.lane_start + offset,
                "payload_sha256": self._row_payload_sha256[offset],
            }
            for offset in range(start, stop)
        ]
        if replay.get("lattice_cache_rows") != expected_rows:
            _fail(
                "typed bundle lattice payloads differ from authenticated "
                "t-major cache rows"
            )
        identity = {
            "source_contract_sha256": self.contract["contract_sha256"],
            "lane_index": self.lane_index,
            "target_order": self.target_order,
            "target": descriptor,
            "lattice_cache_rows_sha256": hashlib.sha256(
                canonical_json_bytes(expected_rows)
            ).hexdigest(),
            "typed_bundle_sha256": replay["bundle_sha256"],
            "typed_bundle_file_sha256": replay["bundle_file_sha256"],
            "pipeline_receipt_sha256": replay["pipeline_receipt_sha256"],
        }
        assert self._admission_chain is not None
        chain_before = self._admission_chain
        self._admission_chain = _extend_chain(chain_before, identity)
        admission: dict[str, Any] = {
            "schema": ADMISSION_SCHEMA,
            "schema_version": 1,
            "algorithm_id": ALGORITHM_ID,
            **identity,
            "admission_chain_before": chain_before,
            "admission_chain_after": self._admission_chain,
            "decisions": {
                "typed_bundle_fresh_replay_accepted": True,
                "exact_deterministic_target_accepted": True,
                "lattice_payloads_equal_authenticated_cache_rows": True,
                "discarded_fft_arithmetic_independently_replayed": False,
                "cuda_t_major_kernel_execution_attested": False,
                "zero_state_transition_validated": False,
                "external_atom_discharged": False,
            },
        }
        admission["admission_sha256"] = hashlib.sha256(
            canonical_json_bytes(admission)
        ).hexdigest()
        self._admission_count += 1
        if self.target_order == Q_MAJOR_TARGET_ORDER:
            self._next_t = descriptor["t_index_stop_exclusive"]
        else:
            self._next_block_q = descriptor["q"] + 1
        return admission

    def finish_lane(
        self,
        *,
        manifest_file: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._finished:
            _fail("adapter lane receipt was already finalized")
        if not self._rows_finished:
            _fail("cannot finish before every cache row is authenticated")
        if self.expected_target() is not None:
            _fail("cannot finish before every typed FFT target is admitted")
        lane = self.contract["schedule"]["lane_inventory"]["lanes"][
            self.lane_index
        ]
        expected_admissions = _integer(
            lane.get("q_contiguous_fft_batch_invocations_if_transposed"),
            "lane FFT target count",
            minimum=0,
        )
        if self._admission_count != expected_admissions:
            _fail("typed bundle admission count differs from the exact lane roster")
        assert self._row_schedule_sha256 is not None
        assert self._admission_chain is not None
        receipt: dict[str, Any] = {
            "schema": LANE_RECEIPT_SCHEMA,
            "schema_version": 1,
            "author": AUTHOR,
            "atom_id": ATOM_ID,
            "algorithm_id": ALGORITHM_ID,
            "classification": (
                PRODUCTION_CLASSIFICATION
                if self.contract["classification"]
                == SOURCE_CONTRACT_CLASSIFICATION
                else STRUCTURAL_CLASSIFICATION
            ),
            "source_contract_sha256": self.contract["contract_sha256"],
            "lane_index": self.lane_index,
            "target_order": self.target_order,
            "assignment": lane,
            "authenticated_row_count": len(self._row_payload_sha256),
            "row_schedule_sha256": self._row_schedule_sha256,
            "typed_bundle_admission_count": self._admission_count,
            "typed_bundle_admission_chain_sha256": self._admission_chain,
            "bundle_manifest_file": (
                dict(manifest_file) if manifest_file is not None else None
            ),
            "decisions": {
                "all_assigned_cache_rows_authenticated_in_order": True,
                "all_fixed_q_targets_admitted_in_deterministic_order": True,
                "q_major_target_order": (
                    self.target_order == Q_MAJOR_TARGET_ORDER
                ),
                "block_major_target_order": (
                    self.target_order == BLOCK_MAJOR_TARGET_ORDER
                ),
                "all_typed_bundles_freshly_replayed": True,
                "all_lattice_payloads_equal_authenticated_cache_rows": True,
                "bounded_reference_adapter_executed": (
                    self.contract["classification"]
                    == STRUCTURAL_KAT_CLASSIFICATION
                ),
                "source_scale_adapter_run_completed": False,
                "row_resident_cuda_kernel_implemented": False,
                "discarded_fft_arithmetic_independently_replayed": False,
                "zero_state_import_export_implemented": False,
                "zero_completeness_claimed": False,
                "trusted_execution_attested": False,
                "external_atom_discharged": False,
            },
        }
        receipt["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(receipt)
        ).hexdigest()
        self._finished = True
        return receipt


def admit_lane_manifest(
    output_path: Path,
    *,
    contract_path: Path,
    lane_index: int,
    manifest_path: Path,
    expected_manifest_sha256: str,
    allow_structural_kat: bool = False,
    expected_contract_sha256: str | None = None,
) -> dict[str, Any]:
    """Execute one complete lane admission from a pinned canonical manifest."""

    adapter = TMajorTypedBundleLaneAdapter(
        contract_path,
        lane_index=lane_index,
        allow_structural_kat=allow_structural_kat,
        expected_contract_sha256=expected_contract_sha256,
    )
    adapter.authenticate_all_rows()
    source, manifest_file = _open_pinned_manifest(
        manifest_path,
        expected_sha256=expected_manifest_sha256,
    )
    replay_digest = hashlib.sha256()
    replay_size = 0
    try:
        for line_index, line in enumerate(source):
            replay_digest.update(line)
            replay_size += len(line)
            if len(line) > MAXIMUM_MANIFEST_LINE_BYTES:
                _fail(f"bundle manifest line {line_index} exceeds its bound")
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise DirichletTMajorAdapterError(
                    f"invalid bundle manifest line {line_index}"
                ) from error
            if (
                not isinstance(value, dict)
                or canonical_json_bytes(value) != line
                or set(value)
                != {
                    "schema",
                    "schema_version",
                    "bundle_path",
                    "bundle_sha256",
                    "control_base",
                }
                or value.get("schema") != MANIFEST_LINE_SCHEMA
                or value.get("schema_version") != 1
            ):
                _fail(f"bundle manifest line {line_index} fields differ")
            bundle_path = _normalized_path(
                value.get("bundle_path"),
                f"bundle manifest line {line_index} path",
            )
            control_value = value.get("control_base")
            control_base = (
                None
                if control_value is None
                else _normalized_path(
                    control_value,
                    f"bundle manifest line {line_index} control base",
                )
            )
            adapter.accept_bundle(
                bundle_path,
                expected_bundle_sha256=_digest(
                    value.get("bundle_sha256"),
                    f"bundle manifest line {line_index} digest",
                ),
                control_base=control_base,
            )
    finally:
        source.close()
    if (
        replay_digest.hexdigest() != manifest_file["sha256"]
        or replay_size != manifest_file["size_bytes"]
    ):
        _fail("bundle manifest changed during its admission replay")
    receipt = adapter.finish_lane(manifest_file=manifest_file)
    _atomic_json(output_path, receipt)
    return receipt


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": "typed_cache_row_admission_component_not_atom_closure",
        "authenticated_lane_row_schedule_implemented": True,
        "deterministic_fixed_q_bundle_roster_implemented": True,
        "q_major_target_order_implemented": True,
        "block_major_t_then_q_target_order_implemented": True,
        "typed_bundle_fresh_replay_at_adapter_boundary_implemented": True,
        "typed_bundle_lattice_payload_to_cache_row_binding_implemented": True,
        "bounded_reference_adapter_known_answer_test_implemented": True,
        "production_contract_compatible": True,
        "source_contract_revalidated_once_per_lane_session": True,
        "source_scale_performance_ready": False,
        "row_resident_cuda_kernel_implemented": False,
        "t_major_to_q_contiguous_shared_row_spool_producer_implemented": True,
        "t_major_to_q_contiguous_spool_implemented": True,
        "fixed_q_pipeline_executor_consumes_spool_format": False,
        "typed_bundle_integrated_into_executing_cuda_lane": False,
        "zero_state_import_export_implemented": False,
        "discarded_fft_arithmetic_independently_replayed": False,
        "zero_completeness_claimed": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ADMISSION_SCHEMA",
    "ALGORITHM_ID",
    "DirichletTMajorAdapterError",
    "LANE_RECEIPT_SCHEMA",
    "MANIFEST_LINE_SCHEMA",
    "BLOCK_MAJOR_TARGET_ORDER",
    "Q_MAJOR_TARGET_ORDER",
    "TMajorTypedBundleLaneAdapter",
    "admit_lane_manifest",
    "capability",
]
