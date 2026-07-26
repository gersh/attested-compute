# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Authenticated t-major rows exposed as deterministic fixed-q run inputs.

The source cache stores one one-MiB Hurwitz lattice row for each ordinate.
The existing FFT pipeline instead consumes at most 64 consecutive ordinates
for one fixed modulus.  Copying every row into every fixed-q batch would
materialize several petabytes.  This module therefore writes each
authenticated lane row exactly once and emits immutable fixed-q run records
which reference contiguous spans in that shared archive.

The archive and run records are transport inputs.  They do not execute CUDA,
replay discarded composition/FFT arithmetic, update completed-L zero state,
establish Turing completeness, attest execution, or discharge an external
atom.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any, BinaryIO, Iterator, Mapping, NoReturn

from tg_verifier.dirichlet_lattice_cache import (
    ROW_PAYLOAD_BYTES,
    canonical_json_bytes,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    SOURCE_Q_T_ROWS,
    maximum_t_index,
)
from tg_verifier.dirichlet_source_supervisor import (
    FFT_BATCH_SIZE,
    PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED,
    SOURCE_CONTRACT_CLASSIFICATION,
    STRUCTURAL_KAT_CLASSIFICATION,
    AuthenticatedLaneReader,
    fft_batch_descriptor,
    load_contract,
)
from tg_verifier.dirichlet_tmajor_adapter import ROW_SCHEDULE_DOMAIN


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-t-major-q-contiguous-spool-v1"

SPOOL_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_spool.receipt.v1"
)
RUN_INPUT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_spool.run_input.v1"
)
RUN_MANIFEST_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_spool.run_manifest_receipt.v1"
)
RUN_SESSION_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_spool.run_session_receipt.v1"
)
RUN_MANIFEST_REPLAY_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_spool.run_manifest_replay.v1"
)

PRODUCTION_CLASSIFICATION = (
    "source_input_spool_not_cuda_execution_or_zero_closure"
)
STRUCTURAL_CLASSIFICATION = (
    "bounded_structural_spool_kat_not_source_evidence"
)

FORMAT_VERSION = 1
SPOOL_MAGIC = b"TGDLQSP1"
ROW_MAGIC = b"TGDLQSR1"
FOOTER_MAGIC = b"TGDLQSF1"

# magic, version, lane, payload bytes, reserved, t start, t stop, row count,
# record stride, source-contract digest, canonical lane-assignment digest.
SPOOL_HEADER = struct.Struct("<8sIIIIQQQQ32s32s")
# magic, version, reserved, t index, payload bytes, SHA256(payload).
SPOOL_ROW_HEADER = struct.Struct("<8sIIQQ32s")
# magic, version, reserved, row count, payload bytes, record-stream bytes,
# adapter-compatible row-schedule digest, SHA256(raw record stream).
SPOOL_FOOTER = struct.Struct("<8sIIQQQ32s32s")

assert SPOOL_HEADER.size == 120
assert SPOOL_ROW_HEADER.size == 64
assert SPOOL_FOOTER.size == 104

RUN_ROW_BINDING_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tmajor-spool/run-rows/v1\0"
)
BLOCK_ROW_BINDING_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tmajor-spool/block-rows/v1\0"
)
RUN_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tmajor-spool/run-chain/v1\0"
)

MAXIMUM_JSON_BYTES = 16 * 1024 * 1024
MAXIMUM_RUN_LINE_BYTES = 16 * 1024

# Independently formula-derived from the exact source lane boundaries and
# maximum_t_index.  Together these sum to SOURCE_Q_T_ROWS.
PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES = (
    349_440_000,
    299_520_000,
    349_440_000,
    299_520_000,
    379_032_643,
    456_659_698,
    712_107_460,
    2_055_331_473,
)
PINNED_SOURCE_LANE_ACTIVE_Q_COUNTS = (
    390_000,
    390_000,
    390_000,
    390_000,
    390_000,
    337_059,
    242_926,
    115_000,
)

_HEX = frozenset("0123456789abcdef")


class DirichletTMajorSpoolError(RuntimeError):
    """A shared-row archive, run input, or run roster failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTMajorSpoolError(message)


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


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON value is forbidden: {value}")


def _parse_json(raw: bytes, *, label: str, canonical: bool = True) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletTMajorSpoolError(f"invalid {label} JSON") from error
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    if canonical and canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value


def _self_hash(value: Mapping[str, Any], field: str, *, label: str) -> str:
    body = dict(value)
    claimed = _digest(body.pop(field, None), f"{label}.{field}")
    if claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest():
        _fail(f"{label} self-hash differs")
    return claimed


def _normalized_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        _fail(f"{label} is malformed")
    path = Path(value)
    if not path.is_absolute() or str(path.resolve()) != value:
        _fail(f"{label} is not an absolute normalized path")
    return path


def _open_regular(path: Path, *, label: str) -> BinaryIO:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletTMajorSpoolError(
            f"cannot open {label} without following a final symlink: {path}"
        ) from error
    source = os.fdopen(descriptor, "rb")
    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
        source.close()
        _fail(f"{label} is not a regular file")
    return source


def _read_canonical_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int = MAXIMUM_JSON_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = _open_regular(path, label=label)
    try:
        status = os.fstat(source.fileno())
        if status.st_size <= 0 or status.st_size > maximum_bytes:
            _fail(f"{label} size is outside its fixed bound")
        raw = source.read(maximum_bytes + 1)
    finally:
        source.close()
    return _parse_json(raw, label=label), {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_bytes(path, canonical_json_bytes(dict(value)))


def _atomic_bytes(path: Path, raw: bytes) -> None:
    if path.exists():
        _fail(f"refusing to replace immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _hash_open_file(source: BinaryIO) -> tuple[str, int]:
    source.seek(0)
    digest = hashlib.sha256()
    size = 0
    while block := source.read(1024 * 1024):
        digest.update(block)
        size += len(block)
    source.seek(0)
    return digest.hexdigest(), size


def _schedule_accounting(
    contract: Mapping[str, Any],
    *,
    lane_index: int,
) -> dict[str, Any]:
    schedule = contract.get("schedule")
    if not isinstance(schedule, dict):
        _fail("source contract schedule is malformed")
    inventory = schedule.get("lane_inventory")
    if not isinstance(inventory, dict):
        _fail("source contract lane inventory is malformed")
    lanes = inventory.get("lanes")
    if not isinstance(lanes, list) or not 0 <= lane_index < len(lanes):
        _fail("spool lane is outside the source contract")
    lane = lanes[lane_index]
    if not isinstance(lane, dict) or lane.get("lane_index") != lane_index:
        _fail("source contract lane assignment is malformed")
    t_start = _integer(
        lane.get("t_index_start_inclusive"), "lane t start", minimum=0
    )
    t_stop = _integer(
        lane.get("t_index_stop_exclusive"),
        "lane t stop",
        minimum=t_start + 1,
    )
    q_start = _integer(
        schedule.get("q_start_inclusive"),
        "source q start",
        minimum=SOURCE_Q_START,
        maximum=SOURCE_Q_STOP,
    )
    q_stop = _integer(
        schedule.get("q_stop_inclusive"),
        "source q stop",
        minimum=q_start,
        maximum=SOURCE_Q_STOP,
    )
    active_q_count = 0
    q_t_row_references = 0
    fixed_q_runs = 0
    for q in range(q_start, q_stop + 1):
        active_stop = min(t_stop, maximum_t_index(q) + 1)
        active_rows = max(0, active_stop - t_start)
        if not active_rows:
            continue
        active_q_count += 1
        q_t_row_references += active_rows
        fixed_q_runs += (
            active_rows + FFT_BATCH_SIZE - 1
        ) // FFT_BATCH_SIZE
    claimed_runs = _integer(
        lane.get("q_contiguous_fft_batch_invocations_if_transposed"),
        "source contract fixed-q run count",
        minimum=0,
    )
    if fixed_q_runs != claimed_runs:
        _fail("formulaic fixed-q run count differs from the source contract")

    source = contract.get("classification") == SOURCE_CONTRACT_CLASSIFICATION
    pins_matched = False
    if source:
        if (
            lane_index >= len(PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES)
            or q_start != SOURCE_Q_START
            or q_stop != SOURCE_Q_STOP
            or fixed_q_runs
            != PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED[
                lane_index
            ]
            or q_t_row_references
            != PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES[lane_index]
            or active_q_count
            != PINNED_SOURCE_LANE_ACTIVE_Q_COUNTS[lane_index]
            or sum(PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES)
            != SOURCE_Q_T_ROWS
        ):
            _fail("source-scale fixed-q schedule differs from its pinned totals")
        pins_matched = True
    return {
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "lane_t_index_start_inclusive": t_start,
        "lane_t_index_stop_exclusive": t_stop,
        "authenticated_lane_rows": t_stop - t_start,
        "active_q_count": active_q_count,
        "q_t_row_references": q_t_row_references,
        "fixed_q_run_count": fixed_q_runs,
        "maximum_ordinates_per_fixed_q_run": FFT_BATCH_SIZE,
        "shared_row_payload_bytes": (t_stop - t_start) * ROW_PAYLOAD_BYTES,
        "duplicated_q_major_row_payload_bytes_avoided": (
            q_t_row_references - (t_stop - t_start)
        )
        * ROW_PAYLOAD_BYTES,
        "source_scale_pinned_totals_matched": pins_matched,
        "source_global_q_t_row_references_if_production": (
            SOURCE_Q_T_ROWS if source else None
        ),
        "source_global_fixed_q_run_count_if_production": (
            sum(PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED)
            if source
            else None
        ),
    }


def _receipt_body(
    *,
    contract_path: Path,
    contract: Mapping[str, Any],
    lane_index: int,
    assignment: Mapping[str, Any],
    artifact: Mapping[str, Any],
    row_schedule_sha256: str,
    record_stream_sha256: str,
) -> dict[str, Any]:
    accounting = _schedule_accounting(contract, lane_index=lane_index)
    classification = (
        PRODUCTION_CLASSIFICATION
        if contract["classification"] == SOURCE_CONTRACT_CLASSIFICATION
        else STRUCTURAL_CLASSIFICATION
    )
    return {
        "schema": SPOOL_RECEIPT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": classification,
        "source_contract": {
            "path": str(contract_path.resolve()),
            "sha256": contract["contract_sha256"],
            "classification": contract["classification"],
        },
        "lane_index": lane_index,
        "assignment": dict(assignment),
        "format": {
            "magic": SPOOL_MAGIC.decode("ascii"),
            "format_version": FORMAT_VERSION,
            "header_bytes": SPOOL_HEADER.size,
            "row_header_bytes": SPOOL_ROW_HEADER.size,
            "row_payload_bytes": ROW_PAYLOAD_BYTES,
            "record_stride_bytes": SPOOL_ROW_HEADER.size + ROW_PAYLOAD_BYTES,
            "footer_bytes": SPOOL_FOOTER.size,
            "fixed_q_rows_are_shared_archive_references_not_copies": True,
        },
        "artifact": dict(artifact),
        "row_schedule_sha256": _digest(
            row_schedule_sha256, "spool row schedule"
        ),
        "record_stream_sha256": _digest(
            record_stream_sha256, "spool record stream"
        ),
        "schedule_accounting": accounting,
        "decisions": {
            "all_lane_rows_authenticated_in_t_order_before_spooling": True,
            "every_row_payload_stored_exactly_once": True,
            "fixed_q_run_targets_formulaic_and_complete": True,
            "fixed_q_run_payloads_are_contiguous_archive_spans": True,
            "source_scale_spool_or_run_roster_executed": False,
            "row_resident_cuda_kernel_executed": False,
            "fixed_q_pipeline_executor_integrated": False,
            "typed_bundle_outputs_produced": False,
            "discarded_composition_arithmetic_replayed": False,
            "discarded_fft_arithmetic_replayed": False,
            "completed_l_zero_state_validated": False,
            "turing_completeness_claimed": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }


def build_lane_spool(
    spool_path: Path,
    receipt_path: Path,
    *,
    contract_path: Path,
    lane_index: int,
    allow_structural_kat: bool = False,
    expected_contract_sha256: str | None = None,
) -> dict[str, Any]:
    """Authenticate one source lane and write one immutable shared-row archive."""

    if spool_path.exists() or receipt_path.exists():
        _fail("refusing to replace an immutable spool artifact or receipt")
    reader = AuthenticatedLaneReader(
        contract_path,
        lane_index=lane_index,
        allow_structural_kat=allow_structural_kat,
        expected_contract_sha256=expected_contract_sha256,
    )
    contract = reader.contract
    lanes = contract["schedule"]["lane_inventory"]["lanes"]
    assignment = lanes[lane_index]
    t_start = _integer(
        assignment.get("t_index_start_inclusive"),
        "lane t start",
        minimum=0,
    )
    t_stop = _integer(
        assignment.get("t_index_stop_exclusive"),
        "lane t stop",
        minimum=t_start + 1,
    )
    row_count = t_stop - t_start
    record_stride = SPOOL_ROW_HEADER.size + ROW_PAYLOAD_BYTES
    assignment_sha256 = hashlib.sha256(
        canonical_json_bytes(assignment)
    ).digest()
    contract_sha256 = bytes.fromhex(
        _digest(contract.get("contract_sha256"), "source contract")
    )
    header = SPOOL_HEADER.pack(
        SPOOL_MAGIC,
        FORMAT_VERSION,
        lane_index,
        ROW_PAYLOAD_BYTES,
        0,
        t_start,
        t_stop,
        row_count,
        record_stride,
        contract_sha256,
        assignment_sha256,
    )
    row_schedule = hashlib.sha256(ROW_SCHEDULE_DOMAIN)
    row_schedule.update(lane_index.to_bytes(4, "little"))
    record_stream = hashlib.sha256()

    spool_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{spool_path.name}.", dir=spool_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(header)
            for expected_t in range(t_start, t_stop):
                lease = reader.acquire()
                try:
                    if (
                        lease.lane_index != lane_index
                        or lease.t_index != expected_t
                        or len(lease.payload) != ROW_PAYLOAD_BYTES
                    ):
                        _fail(
                            "authenticated cache reader returned a substituted, "
                            "skipped, or reordered row"
                        )
                    payload_sha256 = hashlib.sha256(lease.payload).digest()
                    row_header = SPOOL_ROW_HEADER.pack(
                        ROW_MAGIC,
                        FORMAT_VERSION,
                        0,
                        expected_t,
                        ROW_PAYLOAD_BYTES,
                        payload_sha256,
                    )
                    output.write(row_header)
                    output.write(lease.payload)
                    record_stream.update(row_header)
                    record_stream.update(lease.payload)
                    row_schedule.update(expected_t.to_bytes(8, "little"))
                    row_schedule.update(payload_sha256)
                finally:
                    reader.release(lease)
            reader.finish()
            row_schedule_sha256 = row_schedule.digest()
            record_stream_sha256 = record_stream.digest()
            output.write(
                SPOOL_FOOTER.pack(
                    FOOTER_MAGIC,
                    FORMAT_VERSION,
                    0,
                    row_count,
                    row_count * ROW_PAYLOAD_BYTES,
                    row_count * record_stride,
                    row_schedule_sha256,
                    record_stream_sha256,
                )
            )
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, spool_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    expected_size = (
        SPOOL_HEADER.size + row_count * record_stride + SPOOL_FOOTER.size
    )
    with _open_regular(spool_path, label="written t-major spool") as source:
        artifact_sha256, artifact_size = _hash_open_file(source)
    if artifact_size != expected_size:
        spool_path.unlink(missing_ok=True)
        _fail("written t-major spool length differs from its exact geometry")
    artifact = {
        "path": str(spool_path.resolve()),
        "sha256": artifact_sha256,
        "size_bytes": artifact_size,
    }
    body = _receipt_body(
        contract_path=contract_path,
        contract=contract,
        lane_index=lane_index,
        assignment=assignment,
        artifact=artifact,
        row_schedule_sha256=row_schedule_sha256.hex(),
        record_stream_sha256=record_stream_sha256.hex(),
    )
    receipt = dict(body)
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    try:
        _atomic_json(receipt_path, receipt)
    except BaseException:
        spool_path.unlink(missing_ok=True)
        raise
    return receipt


class AuthenticatedQContiguousSpool:
    """Open one externally pinned archive and derive exact fixed-q run inputs."""

    def __init__(
        self,
        receipt_path: Path,
        *,
        contract_path: Path,
        expected_receipt_sha256: str,
        allow_structural_kat: bool = False,
        expected_contract_sha256: str | None = None,
    ) -> None:
        self.contract_path = contract_path.resolve()
        self.contract = load_contract(
            contract_path,
            allow_structural_kat=allow_structural_kat,
            expected_contract_sha256=expected_contract_sha256,
        )
        receipt, _receipt_file = _read_canonical_file(
            receipt_path, label="t-major spool receipt"
        )
        self.receipt_sha256 = _self_hash(
            receipt, "receipt_sha256", label="t-major spool receipt"
        )
        if self.receipt_sha256 != _digest(
            expected_receipt_sha256, "expected t-major spool receipt"
        ):
            _fail("t-major spool receipt differs from its external pin")
        self.receipt = receipt
        self.lane_index = _integer(
            receipt.get("lane_index"), "spool lane index", minimum=0
        )
        lanes = self.contract["schedule"]["lane_inventory"]["lanes"]
        if self.lane_index >= len(lanes):
            _fail("spool lane index is outside the source contract")
        assignment = lanes[self.lane_index]
        artifact = receipt.get("artifact")
        if (
            not isinstance(artifact, dict)
            or set(artifact) != {"path", "sha256", "size_bytes"}
        ):
            _fail("spool artifact record is malformed")
        artifact_path = _normalized_path(
            artifact.get("path"), "spool artifact path"
        )
        expected_artifact_sha256 = _digest(
            artifact.get("sha256"), "spool artifact"
        )
        expected_artifact_size = _integer(
            artifact.get("size_bytes"),
            "spool artifact size",
            minimum=1,
        )
        self._source = _open_regular(
            artifact_path, label="t-major spool artifact"
        )
        try:
            observed_sha256, observed_size = _hash_open_file(self._source)
            if (
                observed_sha256 != expected_artifact_sha256
                or observed_size != expected_artifact_size
            ):
                _fail(
                    "t-major spool artifact differs from its receipt-bound "
                    "hash or exact size"
                )
            self.artifact = {
                "path": str(artifact_path.resolve()),
                "sha256": observed_sha256,
                "size_bytes": observed_size,
            }
            self._parse_archive(assignment)
            expected_body = _receipt_body(
                contract_path=contract_path,
                contract=self.contract,
                lane_index=self.lane_index,
                assignment=assignment,
                artifact=self.artifact,
                row_schedule_sha256=self.row_schedule_sha256,
                record_stream_sha256=self.record_stream_sha256,
            )
            observed_body = dict(receipt)
            observed_body.pop("receipt_sha256")
            if observed_body != expected_body:
                _fail(
                    "t-major spool receipt differs from its reconstructed "
                    "contract, archive, or claim boundary"
                )
        except BaseException:
            self._source.close()
            raise

    def _parse_archive(self, assignment: Mapping[str, Any]) -> None:
        source = self._source
        source.seek(0)
        raw_header = source.read(SPOOL_HEADER.size)
        if len(raw_header) != SPOOL_HEADER.size:
            _fail("short t-major spool header")
        (
            magic,
            version,
            lane_index,
            payload_bytes,
            reserved,
            t_start,
            t_stop,
            row_count,
            record_stride,
            contract_sha256,
            assignment_sha256,
        ) = SPOOL_HEADER.unpack(raw_header)
        expected_start = assignment["t_index_start_inclusive"]
        expected_stop = assignment["t_index_stop_exclusive"]
        expected_count = expected_stop - expected_start
        expected_stride = SPOOL_ROW_HEADER.size + ROW_PAYLOAD_BYTES
        expected_size = (
            SPOOL_HEADER.size
            + expected_count * expected_stride
            + SPOOL_FOOTER.size
        )
        if (
            magic != SPOOL_MAGIC
            or version != FORMAT_VERSION
            or lane_index != self.lane_index
            or payload_bytes != ROW_PAYLOAD_BYTES
            or reserved != 0
            or t_start != expected_start
            or t_stop != expected_stop
            or row_count != expected_count
            or record_stride != expected_stride
            or contract_sha256
            != bytes.fromhex(self.contract["contract_sha256"])
            or assignment_sha256
            != hashlib.sha256(canonical_json_bytes(assignment)).digest()
            or self.artifact["size_bytes"] != expected_size
        ):
            _fail("t-major spool header or exact geometry differs")

        row_schedule = hashlib.sha256(ROW_SCHEDULE_DOMAIN)
        row_schedule.update(self.lane_index.to_bytes(4, "little"))
        record_stream = hashlib.sha256()
        rows: list[tuple[int, str, int]] = []
        for expected_t in range(t_start, t_stop):
            record_offset = source.tell()
            raw_row_header = source.read(SPOOL_ROW_HEADER.size)
            if len(raw_row_header) != SPOOL_ROW_HEADER.size:
                _fail("short t-major spool row header")
            (
                row_magic,
                row_version,
                row_reserved,
                t_index,
                row_payload_bytes,
                claimed_payload_sha256,
            ) = SPOOL_ROW_HEADER.unpack(raw_row_header)
            if (
                row_magic != ROW_MAGIC
                or row_version != FORMAT_VERSION
                or row_reserved != 0
                or t_index != expected_t
                or row_payload_bytes != ROW_PAYLOAD_BYTES
            ):
                _fail("t-major spool row is substituted, skipped, or reordered")
            payload = source.read(ROW_PAYLOAD_BYTES)
            if len(payload) != ROW_PAYLOAD_BYTES:
                _fail("short t-major spool row payload")
            payload_sha256 = hashlib.sha256(payload).digest()
            if payload_sha256 != claimed_payload_sha256:
                _fail("t-major spool row payload digest differs")
            record_stream.update(raw_row_header)
            record_stream.update(payload)
            row_schedule.update(t_index.to_bytes(8, "little"))
            row_schedule.update(payload_sha256)
            rows.append((t_index, payload_sha256.hex(), record_offset))

        raw_footer = source.read(SPOOL_FOOTER.size)
        trailing = source.read(1)
        if len(raw_footer) != SPOOL_FOOTER.size or trailing:
            _fail("t-major spool footer is missing or has trailing bytes")
        (
            footer_magic,
            footer_version,
            footer_reserved,
            footer_rows,
            footer_payload_bytes,
            footer_record_bytes,
            claimed_row_schedule,
            claimed_record_stream,
        ) = SPOOL_FOOTER.unpack(raw_footer)
        if (
            footer_magic != FOOTER_MAGIC
            or footer_version != FORMAT_VERSION
            or footer_reserved != 0
            or footer_rows != row_count
            or footer_payload_bytes != row_count * ROW_PAYLOAD_BYTES
            or footer_record_bytes != row_count * record_stride
            or claimed_row_schedule != row_schedule.digest()
            or claimed_record_stream != record_stream.digest()
        ):
            _fail("t-major spool footer, coverage, or digest differs")
        self.lane_start = t_start
        self.lane_stop = t_stop
        self.record_stride = record_stride
        self._rows = tuple(rows)
        self.row_schedule_sha256 = row_schedule.hexdigest()
        self.record_stream_sha256 = record_stream.hexdigest()

    def close(self) -> None:
        if not self._source.closed:
            self._source.close()

    def __enter__(self) -> "AuthenticatedQContiguousSpool":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _row_binding_sha256(self, start: int, stop: int) -> str:
        digest = hashlib.sha256(RUN_ROW_BINDING_DOMAIN)
        digest.update(bytes.fromhex(self.receipt_sha256))
        for t_index, payload_sha256, _offset in self._rows[start:stop]:
            digest.update(t_index.to_bytes(8, "little"))
            digest.update(bytes.fromhex(payload_sha256))
        return digest.hexdigest()

    def block_row_source(
        self,
        *,
        first_t_index: int,
        t_index_stop_exclusive: int,
    ) -> dict[str, Any]:
        """Describe one lane-aligned block without rereading its payloads.

        The returned list is deliberately bounded by ``FFT_BATCH_SIZE``.  It
        lets a block worker authenticate the one streamed copy of every row;
        it is not a q-major run manifest.
        """

        if (
            type(first_t_index) is not int
            or type(t_index_stop_exclusive) is not int
            or first_t_index < self.lane_start
            or (first_t_index - self.lane_start) % FFT_BATCH_SIZE
            or not first_t_index
            < t_index_stop_exclusive
            <= min(self.lane_stop, first_t_index + FFT_BATCH_SIZE)
        ):
            _fail("t-major block bounds are not a lane-aligned bounded block")
        start = first_t_index - self.lane_start
        stop = t_index_stop_exclusive - self.lane_start
        rows = [
            {"t_index": t_index, "payload_sha256": payload_sha256}
            for t_index, payload_sha256, _offset in self._rows[start:stop]
        ]
        digest = hashlib.sha256(BLOCK_ROW_BINDING_DOMAIN)
        digest.update(bytes.fromhex(self.receipt_sha256))
        for row in rows:
            digest.update(row["t_index"].to_bytes(8, "little"))
            digest.update(bytes.fromhex(row["payload_sha256"]))
        return {
            "artifact": dict(self.artifact),
            "first_record_offset_bytes": self._rows[start][2],
            "record_stride_bytes": self.record_stride,
            "row_header_bytes": SPOOL_ROW_HEADER.size,
            "row_payload_bytes": ROW_PAYLOAD_BYTES,
            "row_count": stop - start,
            "first_t_index": first_t_index,
            "t_index_stop_exclusive": t_index_stop_exclusive,
            "rows": rows,
            "row_bindings_sha256": digest.hexdigest(),
        }

    def iter_block_rows(
        self,
        *,
        first_t_index: int,
        t_index_stop_exclusive: int,
    ) -> Iterator[tuple[int, bytes]]:
        """Read, rehash, and yield each payload in one bounded t-major block."""

        source = self.block_row_source(
            first_t_index=first_t_index,
            t_index_stop_exclusive=t_index_stop_exclusive,
        )
        start = first_t_index - self.lane_start
        stop = t_index_stop_exclusive - self.lane_start
        for expected_t, expected_sha256, offset in self._rows[start:stop]:
            raw = os.pread(self._source.fileno(), self.record_stride, offset)
            if len(raw) != self.record_stride:
                _fail("t-major block row became truncated")
            raw_header = raw[: SPOOL_ROW_HEADER.size]
            payload = raw[SPOOL_ROW_HEADER.size :]
            (
                magic,
                version,
                reserved,
                t_index,
                payload_bytes,
                claimed_payload_sha256,
            ) = SPOOL_ROW_HEADER.unpack(raw_header)
            actual_payload_sha256 = hashlib.sha256(payload).hexdigest()
            if (
                magic != ROW_MAGIC
                or version != FORMAT_VERSION
                or reserved != 0
                or t_index != expected_t
                or payload_bytes != ROW_PAYLOAD_BYTES
                or claimed_payload_sha256.hex() != expected_sha256
                or actual_payload_sha256 != expected_sha256
            ):
                _fail("t-major block row changed after spool authentication")
            yield expected_t, payload
        if source["row_count"] != stop - start:  # defensive shape anchor
            _fail("t-major block row count changed during streaming")

    def run_input(self, *, q: int, first_t_index: int) -> dict[str, Any]:
        """Construct one immutable-shape fixed-q input over a contiguous span."""

        descriptor = fft_batch_descriptor(
            self.contract,
            lane_index=self.lane_index,
            q=q,
            first_t_index=first_t_index,
        )
        start = descriptor["first_t_index"] - self.lane_start
        stop = descriptor["t_index_stop_exclusive"] - self.lane_start
        if not 0 <= start < stop <= len(self._rows):
            _fail("fixed-q target row span is outside the authenticated spool")
        first_record_offset = self._rows[start][2]
        body: dict[str, Any] = {
            "schema": RUN_INPUT_SCHEMA,
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
            "spool_receipt_sha256": self.receipt_sha256,
            "lane_index": self.lane_index,
            "target": descriptor,
            "row_source": {
                "artifact": dict(self.artifact),
                "first_record_offset_bytes": first_record_offset,
                "record_stride_bytes": self.record_stride,
                "row_header_bytes": SPOOL_ROW_HEADER.size,
                "row_payload_bytes": ROW_PAYLOAD_BYTES,
                "row_count": stop - start,
                "first_t_index": descriptor["first_t_index"],
                "t_index_stop_exclusive": descriptor[
                    "t_index_stop_exclusive"
                ],
                "row_bindings_sha256": self._row_binding_sha256(start, stop),
            },
            "adapter_handoff": {
                "typed_bundle_target_must_equal_this_target": True,
                "typed_bundle_lattice_payloads_must_equal_these_rows": True,
                "adapter_bundle_manifest_schema": (
                    "sparkinterval.tg.dirichlet_tmajor_adapter."
                    "bundle_manifest.v1"
                ),
            },
            "decisions": {
                "source_contract_and_spool_revalidated": True,
                "fixed_q_target_reconstructed_formulaically": True,
                "row_span_contiguous_and_hash_bound": True,
                "row_payloads_copied_into_q_major_artifact": False,
                "row_resident_cuda_kernel_executed": False,
                "fixed_q_pipeline_executed": False,
                "typed_bundle_produced": False,
                "discarded_composition_arithmetic_replayed": False,
                "discarded_fft_arithmetic_replayed": False,
                "completed_l_zero_state_validated": False,
                "turing_completeness_claimed": False,
                "trusted_execution_attested": False,
                "external_atom_discharged": False,
            },
        }
        result = dict(body)
        result["run_input_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        return result

    def validate_run_input(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            _fail("fixed-q run input is not an object")
        body = dict(value)
        claimed = _digest(
            body.pop("run_input_sha256", None), "fixed-q run input"
        )
        if claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest():
            _fail("fixed-q run input self-hash differs")
        target = value.get("target")
        if not isinstance(target, Mapping):
            _fail("fixed-q run input target is malformed")
        expected = self.run_input(
            q=_integer(target.get("q"), "fixed-q run modulus", minimum=3),
            first_t_index=_integer(
                target.get("first_t_index"),
                "fixed-q run first t index",
                minimum=0,
            ),
        )
        if dict(value) != expected:
            _fail(
                "fixed-q run input differs from its reconstructed target or "
                "authenticated row span"
            )
        return expected

    def write_run_input(
        self,
        output_path: Path,
        *,
        q: int,
        first_t_index: int,
    ) -> dict[str, Any]:
        value = self.run_input(q=q, first_t_index=first_t_index)
        _atomic_json(output_path, value)
        return value

    def iter_run_rows(
        self, value: Mapping[str, Any]
    ) -> Iterator[tuple[int, bytes]]:
        """Yield and rehash every row named by a validated run input."""

        checked = self.validate_run_input(value)
        target = checked["target"]
        start = target["first_t_index"] - self.lane_start
        stop = target["t_index_stop_exclusive"] - self.lane_start
        for expected_t, expected_sha256, offset in self._rows[start:stop]:
            raw = os.pread(
                self._source.fileno(),
                self.record_stride,
                offset,
            )
            if len(raw) != self.record_stride:
                _fail("fixed-q run row became truncated")
            raw_header = raw[: SPOOL_ROW_HEADER.size]
            payload = raw[SPOOL_ROW_HEADER.size :]
            (
                magic,
                version,
                reserved,
                t_index,
                payload_bytes,
                claimed_payload_sha256,
            ) = SPOOL_ROW_HEADER.unpack(raw_header)
            actual_payload_sha256 = hashlib.sha256(payload).hexdigest()
            if (
                magic != ROW_MAGIC
                or version != FORMAT_VERSION
                or reserved != 0
                or t_index != expected_t
                or payload_bytes != ROW_PAYLOAD_BYTES
                or claimed_payload_sha256.hex() != expected_sha256
                or actual_payload_sha256 != expected_sha256
            ):
                _fail("fixed-q run row changed after spool authentication")
            yield expected_t, payload


class QContiguousRunCursor:
    """Fail-closed canonical ``q``, then ``first_t_index`` run ordering."""

    def __init__(self, spool: AuthenticatedQContiguousSpool) -> None:
        self.spool = spool
        schedule = spool.contract["schedule"]
        self._next_q = schedule["q_start_inclusive"]
        self._q_stop = schedule["q_stop_inclusive"]
        self._next_t = spool.lane_start
        initial = hashlib.sha256(RUN_CHAIN_DOMAIN)
        initial.update(bytes.fromhex(spool.contract["contract_sha256"]))
        initial.update(bytes.fromhex(spool.receipt_sha256))
        initial.update(spool.lane_index.to_bytes(4, "little"))
        self.run_chain_sha256 = initial.hexdigest()
        self.run_count = 0
        self.row_reference_count = 0
        self._finished = False

    def expected_target(self) -> dict[str, Any] | None:
        if self._finished:
            _fail("fixed-q run cursor is already finalized")
        while self._next_q <= self._q_stop:
            active_stop = min(
                self.spool.lane_stop,
                maximum_t_index(self._next_q) + 1,
            )
            if self._next_t < active_stop:
                return fft_batch_descriptor(
                    self.spool.contract,
                    lane_index=self.spool.lane_index,
                    q=self._next_q,
                    first_t_index=self._next_t,
                )
            self._next_q += 1
            self._next_t = self.spool.lane_start
        return None

    def accept(self, value: Mapping[str, Any]) -> None:
        checked = self.spool.validate_run_input(value)
        expected = self.expected_target()
        if expected is None:
            _fail("fixed-q run supplied after the exact roster ended")
        if checked["target"] != expected:
            _fail("fixed-q run was skipped, substituted, or reordered")
        digest = hashlib.sha256(RUN_CHAIN_DOMAIN)
        digest.update(bytes.fromhex(self.run_chain_sha256))
        digest.update(bytes.fromhex(checked["run_input_sha256"]))
        self.run_chain_sha256 = digest.hexdigest()
        self.run_count += 1
        self.row_reference_count += expected["batch_count"]
        self._next_t = expected["t_index_stop_exclusive"]

    def finish(self) -> dict[str, Any]:
        if self._finished:
            _fail("fixed-q run cursor was already finalized")
        if self.expected_target() is not None:
            _fail("fixed-q run roster is truncated")
        accounting = self.spool.receipt["schedule_accounting"]
        if (
            self.run_count != accounting["fixed_q_run_count"]
            or self.row_reference_count != accounting["q_t_row_references"]
        ):
            _fail("fixed-q run roster totals differ from exact source accounting")
        body: dict[str, Any] = {
            "schema": RUN_SESSION_RECEIPT_SCHEMA,
            "schema_version": 1,
            "algorithm_id": ALGORITHM_ID,
            "source_contract_sha256": self.spool.contract[
                "contract_sha256"
            ],
            "spool_receipt_sha256": self.spool.receipt_sha256,
            "lane_index": self.spool.lane_index,
            "run_count": self.run_count,
            "row_reference_count": self.row_reference_count,
            "run_chain_sha256": self.run_chain_sha256,
            "schedule_accounting": accounting,
            "decisions": {
                "complete_formulaic_run_roster_consumed_in_order": True,
                "run_inputs_hash_bound_to_authenticated_row_spans": True,
                "fixed_q_pipeline_executed": False,
                "typed_bundles_admitted": False,
                "completed_l_zero_state_validated": False,
                "turing_completeness_claimed": False,
                "trusted_execution_attested": False,
                "external_atom_discharged": False,
            },
        }
        result = dict(body)
        result["session_receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        self._finished = True
        return result


def build_run_manifest(
    manifest_path: Path,
    receipt_path: Path,
    *,
    spool: AuthenticatedQContiguousSpool,
) -> dict[str, Any]:
    """Stream the complete immutable fixed-q roster without retaining a list."""

    if manifest_path.exists() or receipt_path.exists():
        _fail("refusing to replace an immutable run manifest or receipt")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.", dir=manifest_path.parent
    )
    temporary = Path(temporary_name)
    cursor = QContiguousRunCursor(spool)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            while (target := cursor.expected_target()) is not None:
                value = spool.run_input(
                    q=target["q"],
                    first_t_index=target["first_t_index"],
                )
                raw = canonical_json_bytes(value)
                if len(raw) > MAXIMUM_RUN_LINE_BYTES:
                    _fail("fixed-q run manifest line exceeds its bound")
                output.write(raw)
                digest.update(raw)
                size += len(raw)
                cursor.accept(value)
            session = cursor.finish()
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, manifest_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    manifest = {
        "path": str(manifest_path.resolve()),
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }
    body: dict[str, Any] = {
        "schema": RUN_MANIFEST_RECEIPT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            PRODUCTION_CLASSIFICATION
            if spool.contract["classification"] == SOURCE_CONTRACT_CLASSIFICATION
            else STRUCTURAL_CLASSIFICATION
        ),
        "source_contract_sha256": spool.contract["contract_sha256"],
        "spool_receipt_sha256": spool.receipt_sha256,
        "lane_index": spool.lane_index,
        "manifest": manifest,
        "session": session,
        "decisions": {
            "complete_run_manifest_materialized": True,
            "manifest_streamed_without_source_sized_memory": True,
            "fixed_q_pipeline_executed": False,
            "typed_bundle_outputs_produced": False,
            "row_resident_cuda_kernel_executed": False,
            "completed_l_zero_state_validated": False,
            "turing_completeness_claimed": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    receipt = dict(body)
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    try:
        _atomic_json(receipt_path, receipt)
    except BaseException:
        manifest_path.unlink(missing_ok=True)
        raise
    return receipt


def replay_run_manifest(
    manifest_path: Path,
    receipt_path: Path,
    *,
    spool: AuthenticatedQContiguousSpool,
    expected_receipt_sha256: str,
) -> dict[str, Any]:
    """Reparse a pinned roster and reject substitutions, gaps, order, or EOF."""

    receipt, _receipt_file = _read_canonical_file(
        receipt_path, label="fixed-q run manifest receipt"
    )
    receipt_sha256 = _self_hash(
        receipt, "receipt_sha256", label="fixed-q run manifest receipt"
    )
    if receipt_sha256 != _digest(
        expected_receipt_sha256, "expected run manifest receipt"
    ):
        _fail("run manifest receipt differs from its external pin")
    manifest = receipt.get("manifest")
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"path", "sha256", "size_bytes"}
        or _normalized_path(manifest.get("path"), "run manifest path")
        != manifest_path.resolve()
    ):
        _fail("run manifest artifact record is malformed or substituted")
    expected_manifest_sha256 = _digest(
        manifest.get("sha256"), "run manifest artifact"
    )
    expected_manifest_size = _integer(
        manifest.get("size_bytes"), "run manifest size", minimum=1
    )
    source = _open_regular(manifest_path, label="fixed-q run manifest")
    cursor = QContiguousRunCursor(spool)
    digest = hashlib.sha256()
    size = 0
    try:
        status = os.fstat(source.fileno())
        if status.st_size != expected_manifest_size:
            _fail("run manifest exact size differs before replay")
        for line_index, line in enumerate(source):
            digest.update(line)
            size += len(line)
            if len(line) > MAXIMUM_RUN_LINE_BYTES:
                _fail(f"run manifest line {line_index} exceeds its bound")
            value = _parse_json(
                line, label=f"run manifest line {line_index}"
            )
            cursor.accept(value)
        session = cursor.finish()
    finally:
        source.close()
    if (
        digest.hexdigest() != expected_manifest_sha256
        or size != expected_manifest_size
    ):
        _fail("run manifest changed or differs from its receipt")

    expected_body: dict[str, Any] = {
        "schema": RUN_MANIFEST_RECEIPT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            PRODUCTION_CLASSIFICATION
            if spool.contract["classification"] == SOURCE_CONTRACT_CLASSIFICATION
            else STRUCTURAL_CLASSIFICATION
        ),
        "source_contract_sha256": spool.contract["contract_sha256"],
        "spool_receipt_sha256": spool.receipt_sha256,
        "lane_index": spool.lane_index,
        "manifest": manifest,
        "session": session,
        "decisions": {
            "complete_run_manifest_materialized": True,
            "manifest_streamed_without_source_sized_memory": True,
            "fixed_q_pipeline_executed": False,
            "typed_bundle_outputs_produced": False,
            "row_resident_cuda_kernel_executed": False,
            "completed_l_zero_state_validated": False,
            "turing_completeness_claimed": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    observed_body = dict(receipt)
    observed_body.pop("receipt_sha256")
    if observed_body != expected_body:
        _fail("run manifest receipt differs from fresh complete replay")
    return {
        "schema": RUN_MANIFEST_REPLAY_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "accepted": True,
        "source_contract_sha256": spool.contract["contract_sha256"],
        "spool_receipt_sha256": spool.receipt_sha256,
        "manifest_receipt_sha256": receipt_sha256,
        "lane_index": spool.lane_index,
        "run_count": session["run_count"],
        "row_reference_count": session["row_reference_count"],
        "run_chain_sha256": session["run_chain_sha256"],
        "fixed_q_pipeline_executed": False,
        "typed_bundles_admitted": False,
        "row_resident_cuda_kernel_executed": False,
        "completed_l_zero_state_validated": False,
        "turing_completeness_claimed": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": (
            "authenticated_shared_row_spool_and_run_roster_not_atom_closure"
        ),
        "authenticated_tmajor_lane_spool_producer_implemented": True,
        "one_copy_per_authenticated_row_archive_implemented": True,
        "formulaic_fixed_q_run_input_producer_implemented": True,
        "complete_streaming_run_manifest_and_replay_implemented": True,
        "substitution_skip_reorder_truncation_rejection_implemented": True,
        "source_scale_schedule_counts_pinned": True,
        "adapter_target_and_lattice_row_identity_compatible": True,
        "bounded_reference_known_answer_tests_implemented": True,
        "source_scale_archive_or_manifest_run_completed": False,
        "source_scale_performance_ready": False,
        "row_resident_cuda_kernel_implemented": True,
        "authenticated_spool_to_TGDLTMB1_adapter_implemented": True,
        "direct_MPFR_factor_and_exact_tail_sidecar_producer_implemented": True,
        "row_resident_cuda_component": (
            "tools/tg_dirichlet_tmajor_cuda_block.py capability"
        ),
        "fixed_q_pipeline_executor_consumes_spool_format": False,
        "typed_bundle_output_and_adapter_manifest_wired": False,
        "discarded_composition_arithmetic_independently_replayed": False,
        "discarded_fft_arithmetic_independently_replayed": False,
        "completed_l_zero_state_import_export_implemented": False,
        "zero_completeness_claimed": False,
        "turing_completeness_claimed": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "AuthenticatedQContiguousSpool",
    "DirichletTMajorSpoolError",
    "PINNED_SOURCE_LANE_ACTIVE_Q_COUNTS",
    "PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES",
    "QContiguousRunCursor",
    "RUN_INPUT_SCHEMA",
    "RUN_MANIFEST_RECEIPT_SCHEMA",
    "SPOOL_RECEIPT_SCHEMA",
    "build_lane_spool",
    "build_run_manifest",
    "capability",
    "replay_run_manifest",
]
