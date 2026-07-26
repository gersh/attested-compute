# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Certified-box packer and exact work model for the fused large-q CUDA stage.

The CUDA runner never evaluates a transcendental function.  This module binds
its compact ``TGDLQBI1`` input to the existing Arb/FLINT lattice and finite-
recovery certificates, generates each ``q**(-s)`` rectangle with MPFR, and
reorders the source's ascending residue stream into canonical CRT order.

The emitted CUDA result is a normal ``TGDAFFI1`` frame and can be piped directly
to the persistent all-character transform.  This component remains conditional
on the upstream certificates and does not close Platt's theorem by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Any, BinaryIO, NoReturn

from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    canonical_component_orders,
    canonical_residue_order,
)
import tg_verifier.dirichlet_lattice_certificates as _lattice_certificates
from tg_verifier.dirichlet_lattice_certificates import (
    DECISIONS as LATTICE_CERTIFICATE_DECISIONS,
    MANIFEST_SCHEMA as LATTICE_MANIFEST_SCHEMA,
    RECOVERY_FORMAT_VERSION,
    RECOVERY_HEADER,
    RECOVERY_ITEM,
    RECOVERY_MAGIC,
    REPLAY_SCHEMA as LATTICE_REPLAY_SCHEMA,
    REQUEST_ENUMERATION,
    _source_record as _lattice_source_record,
    _validate_runtime_record as _validate_lattice_runtime_record,
)
from tg_verifier.dirichlet_lattice_stage import (
    FORMAT_VERSION as LATTICE_FORMAT_VERSION,
    INPUT_HEADER as LATTICE_INPUT_HEADER,
    INPUT_ITEM as LATTICE_INPUT_ITEM,
    INPUT_MAGIC as LATTICE_INPUT_MAGIC,
    LATTICE_CELL,
    LATTICE_ROWS,
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    SOURCE_Q_T_ROWS,
    SOURCE_RESIDUE_INTERPOLATIONS,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
    maximum_t_index,
)
from tg_verifier.dirichlet_residue_composition import (
    Artifact,
    MPFRFactorProvider,
    ResiduePlan,
    ResiduePlanCache,
    _artifact_from_record,
    _load_canonical_json,
    _verify_artifact,
    _verify_self_hash,
    artifact_record,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ALGORITHM_ID = "platt-dirichlet-large-q-certified-box-cuda-batch-v1"
CHECKER_ID = "mpfr-residue-composition-plus-exact-taylor-replay-v1"
JOB_SCHEMA = "sparkinterval.tg.dirichlet_largeq_batch.job.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_largeq_batch.input_receipt.v1"
CERTIFIED_CLASSIFICATION = "certified_lattice_and_recovery_box_batch"
SYNTHETIC_CLASSIFICATION = "synthetic_largeq_batch_kat_only"

FORMAT_VERSION = 1
MAXIMUM_BATCH_COUNT = 64
MAXIMUM_GROUP_ORDER = 399_988
INPUT_MAGIC = b"TGDLQBI1"
INPUT_HEADER = struct.Struct("<8sIIIIIIIIQqQQQQQ")
RESIDUE_DESCRIPTOR = struct.Struct("<II")
FRAME_FACTOR = COMPLEX_INTERVAL
CERTIFIED_RESIDUE_BOX = struct.Struct("<ddddd")

assert INPUT_HEADER.size == 96
assert RESIDUE_DESCRIPTOR.size == 8
assert FRAME_FACTOR.size == 32
assert CERTIFIED_RESIDUE_BOX.size == 40


class DirichletLargeQBatchError(RuntimeError):
    """A batch job, certificate binding, or binary frame failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletLargeQBatchError(message)


@dataclass(frozen=True)
class BatchFrame:
    lattice_input: Artifact
    finite_recovery: Artifact
    lattice_certificate: Artifact | None
    lattice_replay: Artifact | None


@dataclass(frozen=True)
class BatchJob:
    path: Path
    sha256: str
    classification: str
    q: int
    first_t_numerator: int
    t_denominator: int
    t_step_numerator: int
    frames: tuple[BatchFrame, ...]


def _artifact_record_from_unknown(
    record: object, *, base: Path, label: str
) -> Artifact:
    try:
        artifact = _artifact_from_record(record, base=base, label=label)
        _verify_artifact(artifact, label)
        return artifact
    except RuntimeError as error:
        raise DirichletLargeQBatchError(str(error)) from error


def load_job(path: Path, *, allow_synthetic_kat: bool = False) -> BatchJob:
    try:
        value, raw = _load_canonical_json(path, "large-q batch job")
    except RuntimeError as error:
        raise DirichletLargeQBatchError(str(error)) from error
    if set(value) != {
        "schema", "schema_version", "classification", "q",
        "first_t_numerator", "t_denominator", "t_step_numerator", "frames",
    }:
        _fail("large-q batch job fields changed")
    if value.get("schema") != JOB_SCHEMA or value.get("schema_version") != 1:
        _fail("large-q batch job schema mismatch")
    classification = value.get("classification")
    if classification not in {CERTIFIED_CLASSIFICATION, SYNTHETIC_CLASSIFICATION}:
        _fail("large-q batch classification mismatch")
    if classification == SYNTHETIC_CLASSIFICATION and not allow_synthetic_kat:
        _fail("synthetic large-q jobs require explicit KAT authorization")
    q = value.get("q")
    first = value.get("first_t_numerator")
    denominator = value.get("t_denominator")
    step = value.get("t_step_numerator")
    raw_frames = value.get("frames")
    if type(q) is not int or not SOURCE_Q_START <= q <= SOURCE_Q_STOP:
        _fail("large-q batch q is outside the source range")
    if (
        type(first) is not int
        or first < 0
        or first % SOURCE_SAMPLE_NUMERATOR
        or denominator != SOURCE_SAMPLE_DENOMINATOR
        or step != SOURCE_SAMPLE_NUMERATOR
    ):
        _fail("large-q batch ordinates are not the exact 5/64 source grid")
    if (
        not isinstance(raw_frames, list)
        or not raw_frames
        or len(raw_frames) > MAXIMUM_BATCH_COUNT
        or first // SOURCE_SAMPLE_NUMERATOR + len(raw_frames) - 1
        > maximum_t_index(q)
    ):
        _fail("large-q batch frame count is empty or outside the source height")
    frames: list[BatchFrame] = []
    basic = {"lattice_input", "finite_recovery"}
    certified = basic | {"lattice_certificate", "lattice_replay"}
    expected = certified if classification == CERTIFIED_CLASSIFICATION else basic
    for index, raw_frame in enumerate(raw_frames):
        label = f"frames[{index}]"
        if not isinstance(raw_frame, dict) or set(raw_frame) != expected:
            _fail(f"{label} fields do not match the job classification")
        artifacts = {
            name: _artifact_record_from_unknown(
                raw_frame[name], base=path.resolve().parent, label=f"{label}.{name}"
            )
            for name in expected
        }
        frames.append(
            BatchFrame(
                lattice_input=artifacts["lattice_input"],
                finite_recovery=artifacts["finite_recovery"],
                lattice_certificate=artifacts.get("lattice_certificate"),
                lattice_replay=artifacts.get("lattice_replay"),
            )
        )
    return BatchJob(
        path=path.resolve(),
        sha256=sha256_bytes(raw),
        classification=classification,
        q=q,
        first_t_numerator=first,
        t_denominator=denominator,
        t_step_numerator=step,
        frames=tuple(frames),
    )


def _read_exact(source: BinaryIO, size: int, label: str) -> bytes:
    raw = source.read(size)
    if len(raw) != size:
        _fail(f"short {label}")
    return raw


def _validate_certificate(
    frame: BatchFrame, *, plan: ResiduePlan, expected_t_numerator: int
) -> int:
    """Validate only the artifacts needed by the fused stage.

    Unlike the older composition adapter, this intentionally does not require
    a materialized ``TGDLATO1`` Taylor output or its receipt: Taylor evaluation
    occurs in the one fused CUDA launch.
    """

    if frame.lattice_certificate is None or frame.lattice_replay is None:
        _fail("certified frame is missing lattice certificate or replay")
    try:
        certificate, _ = _load_canonical_json(
            frame.lattice_certificate.path, "lattice certificate"
        )
    except RuntimeError as error:
        raise DirichletLargeQBatchError(str(error)) from error
    if set(certificate) != {
        "schema", "schema_version", "author", "atom_id", "algorithm_id",
        "checker_id", "classification", "source", "parameters", "requests",
        "uniform_taylor_tail", "artifacts", "generator_runtime", "decisions",
        "certificate_sha256",
    }:
        _fail("lattice certificate fields changed")
    if (
        certificate.get("schema") != LATTICE_MANIFEST_SCHEMA
        or certificate.get("schema_version") != 1
        or certificate.get("author") != AUTHOR
        or certificate.get("atom_id") != ATOM_ID
        or certificate.get("algorithm_id")
        != "platt-dirichlet-certified-lattice-input-v1"
        or certificate.get("checker_id")
        != "higher-precision-flint-plus-exact-rational-tail-v1"
        or certificate.get("classification")
        != "source_shaped_certified_analytic_batch_not_theorem_7_1"
        or certificate.get("source") != _lattice_source_record()
    ):
        _fail("lattice certificate producer identity mismatch")
    try:
        _verify_self_hash(
            certificate, field="certificate_sha256", label="lattice certificate"
        )
    except RuntimeError as error:
        raise DirichletLargeQBatchError(str(error)) from error
    parameters = certificate.get("parameters")
    requests = certificate.get("requests")
    artifacts = certificate.get("artifacts")
    if not all(isinstance(item, dict) for item in (parameters, requests, artifacts)):
        _fail("lattice certificate binding records are malformed")
    assert isinstance(parameters, dict)
    assert isinstance(requests, dict)
    assert isinstance(artifacts, dict)
    try:
        raw_t = parameters["t"]
        recorded_t = Fraction(int(raw_t["numerator"]), int(raw_t["denominator"]))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise DirichletLargeQBatchError(
            "lattice certificate exact ordinate is malformed"
        ) from error
    expected_t = Fraction(expected_t_numerator, SOURCE_SAMPLE_DENOMINATOR)
    m = parameters.get("M")
    generation_precision = parameters.get("generation_precision_bits")
    if (
        parameters.get("q_start_inclusive") != plan.q
        or parameters.get("q_stop_inclusive") != plan.q
        or parameters.get("t_index")
        != expected_t_numerator // SOURCE_SAMPLE_NUMERATOR
        or recorded_t != expected_t
        or parameters.get("D") != LATTICE_ROWS
        or parameters.get("N") != TAYLOR_DEGREE
        or parameters.get("columns") != TAYLOR_COLUMNS
        or parameters.get("max_items") is not None
        or type(m) is not int
        or m <= 0
        or type(generation_precision) is not int
        or generation_precision < 128
    ):
        _fail("lattice certificate parameters do not match the complete q/t frame")
    if (
        requests.get("count") != plan.order
        or requests.get("sha256_le_u32_q_a_row") != plan.request_sha256
        or requests.get("first")
        != {
            "q": plan.q,
            "a": plan.first_a,
            "row": canonical_lattice_row(plan.q, plan.first_a),
        }
        or requests.get("last")
        != {
            "q": plan.q,
            "a": plan.last_a,
            "row": canonical_lattice_row(plan.q, plan.last_a),
        }
        or requests.get("enumeration") != REQUEST_ENUMERATION
    ):
        _fail("lattice certificate request enumeration mismatch")
    if set(artifacts) != {
        "lattice-input.bin", "finite-recovery.bin", "producer_module"
    }:
        _fail("lattice certificate artifact closure changed")
    producer_digest, producer_size = sha256_file(
        Path(_lattice_certificates.__file__).resolve()
    )
    if artifacts.get("producer_module") != {
        "sha256": producer_digest,
        "size_bytes": producer_size,
    }:
        _fail("lattice certificate producer module changed")
    for name, expected_artifact in (
        ("lattice-input.bin", frame.lattice_input),
        ("finite-recovery.bin", frame.finite_recovery),
    ):
        record = artifacts.get(name)
        if (
            not isinstance(record, dict)
            or record.get("sha256") != expected_artifact.sha256
            or record.get("size_bytes") != expected_artifact.size_bytes
        ):
            _fail(f"lattice certificate does not bind {name}")
    if certificate.get("decisions") != LATTICE_CERTIFICATE_DECISIONS:
        _fail("lattice certificate capability flags are unsafe")
    try:
        _validate_lattice_runtime_record(
            certificate.get("generator_runtime"), "generator_runtime"
        )
    except RuntimeError as error:
        raise DirichletLargeQBatchError(
            "lattice certificate runtime identity is invalid"
        ) from error

    try:
        replay, _ = _load_canonical_json(frame.lattice_replay.path, "lattice replay")
    except RuntimeError as error:
        raise DirichletLargeQBatchError(str(error)) from error
    if set(replay) != {
        "schema", "schema_version", "classification", "certificate_sha256",
        "replay_precision_bits", "lattice_cells_replayed",
        "finite_recovery_values_replayed", "uniform_tail_replayed_exactly",
        "strict_request_geometry_replayed",
        "higher_precision_arb_containment_passed", "generator_runtime",
        "replay_runtime", "same_runtime_binary", "elapsed_seconds",
        "external_atom_discharged", "replay_sha256",
    }:
        _fail("lattice replay fields changed")
    if (
        replay.get("schema") != LATTICE_REPLAY_SCHEMA
        or replay.get("schema_version") != 1
        or replay.get("classification")
        != "complete_input_bundle_replay_not_theorem_7_1"
    ):
        _fail("lattice replay schema or classification mismatch")
    try:
        _verify_self_hash(replay, field="replay_sha256", label="lattice replay")
    except RuntimeError as error:
        raise DirichletLargeQBatchError(str(error)) from error
    if (
        replay.get("certificate_sha256") != certificate.get("certificate_sha256")
        or replay.get("generator_runtime") != certificate.get("generator_runtime")
        or type(replay.get("replay_precision_bits")) is not int
        or replay.get("replay_precision_bits", 0) < generation_precision + 64
        or replay.get("lattice_cells_replayed") != LATTICE_ROWS * TAYLOR_COLUMNS
        or replay.get("finite_recovery_values_replayed") != plan.order
        or replay.get("uniform_tail_replayed_exactly") is not True
        or replay.get("strict_request_geometry_replayed") is not True
        or replay.get("higher_precision_arb_containment_passed") is not True
        or replay.get("external_atom_discharged") is not False
    ):
        _fail("lattice replay does not close its stated box checks")
    try:
        _validate_lattice_runtime_record(
            replay.get("generator_runtime"), "generator_runtime"
        )
        _validate_lattice_runtime_record(replay.get("replay_runtime"), "replay_runtime")
    except RuntimeError as error:
        raise DirichletLargeQBatchError(
            "lattice replay runtime identity is invalid"
        ) from error
    return m


def _frame_headers(
    frame: BatchFrame, *, plan: ResiduePlan, expected_t_numerator: int
) -> tuple[int, int]:
    with frame.lattice_input.path.open("rb") as lattice:
        header = LATTICE_INPUT_HEADER.unpack(
            _read_exact(lattice, LATTICE_INPUT_HEADER.size, "TGDLATI1 header")
        )
    (
        magic, version, rows, degree, reserved0, t_numerator, denominator,
        count, lattice_count, reserved1,
    ) = header
    expected_lattice_size = (
        LATTICE_INPUT_HEADER.size
        + LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
        + plan.order * LATTICE_INPUT_ITEM.size
    )
    if (
        magic != LATTICE_INPUT_MAGIC
        or version != LATTICE_FORMAT_VERSION
        or rows != LATTICE_ROWS
        or degree != TAYLOR_DEGREE
        or reserved0
        or reserved1
        or t_numerator != expected_t_numerator
        or denominator != SOURCE_SAMPLE_DENOMINATOR
        or count != plan.order
        or lattice_count != LATTICE_ROWS * TAYLOR_COLUMNS
        or frame.lattice_input.size_bytes != expected_lattice_size
    ):
        _fail("TGDLATI1 header, count, t, or exact length mismatch")
    with frame.finite_recovery.path.open("rb") as recovery:
        recovery_header = RECOVERY_HEADER.unpack(
            _read_exact(recovery, RECOVERY_HEADER.size, "TGDLREC1 header")
        )
    (
        recovery_magic, recovery_version, m, recovery_reserved0,
        recovery_t_numerator, recovery_denominator, recovery_count,
        recovery_reserved1,
    ) = recovery_header
    if (
        recovery_magic != RECOVERY_MAGIC
        or recovery_version != RECOVERY_FORMAT_VERSION
        or type(m) is not int
        or m <= 0
        or recovery_reserved0
        or recovery_reserved1
        or recovery_t_numerator != expected_t_numerator
        or recovery_denominator != SOURCE_SAMPLE_DENOMINATOR
        or recovery_count != plan.order
        or frame.finite_recovery.size_bytes
        != RECOVERY_HEADER.size + plan.order * RECOVERY_ITEM.size
    ):
        _fail("TGDLREC1 header, count, M, t, or exact length mismatch")
    return m, lattice_count


class _HashingWriter:
    def __init__(self, output: BinaryIO) -> None:
        self.output = output
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, raw: bytes | bytearray) -> None:
        self.output.write(raw)
        self.digest.update(raw)
        self.size += len(raw)


def _copy_exact(source: BinaryIO, writer: _HashingWriter, size: int) -> None:
    remaining = size
    while remaining:
        block = source.read(min(1024 * 1024, remaining))
        if not block:
            _fail("short lattice payload")
        writer.write(block)
        remaining -= len(block)


def _frame_boxes(frame: BatchFrame, *, plan: ResiduePlan) -> bytearray:
    """Read ascending source records and return canonical CRT box order."""

    packed = bytearray(plan.order * CERTIFIED_RESIDUE_BOX.size)
    with (
        frame.lattice_input.path.open("rb") as lattice,
        frame.finite_recovery.path.open("rb") as recovery,
    ):
        lattice.seek(
            LATTICE_INPUT_HEADER.size
            + LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
        )
        recovery.seek(RECOVERY_HEADER.size)
        seen = 0
        for a in range(1, plan.q):
            position = plan.positions[a]
            if position < 0:
                continue
            request = LATTICE_INPUT_ITEM.unpack(
                _read_exact(lattice, LATTICE_INPUT_ITEM.size, "lattice request")
            )
            request_q, request_a, row, request_reserved, radius = request
            finite = RECOVERY_ITEM.unpack(
                _read_exact(recovery, RECOVERY_ITEM.size, "finite-recovery item")
            )
            recovery_q, recovery_a, reserved_a, reserved_b, *values = finite
            if (
                (request_q, request_a, row)
                != (plan.q, a, canonical_lattice_row(plan.q, a))
                or request_reserved
                or not math.isfinite(radius)
                or radius < 0
                or (recovery_q, recovery_a) != (plan.q, a)
                or reserved_a
                or reserved_b
                or not all(math.isfinite(value) for value in values)
                or values[0] > values[1]
                or values[2] > values[3]
            ):
                _fail("noncanonical or malformed lattice/recovery residue row")
            CERTIFIED_RESIDUE_BOX.pack_into(
                packed, position * CERTIFIED_RESIDUE_BOX.size, radius, *values
            )
            seen += 1
        if seen != plan.order or lattice.read(1) or recovery.read(1):
            _fail("lattice/recovery payload is truncated or has trailing bytes")
    return packed


def pack_input(
    job_path: Path,
    output_path: Path,
    *,
    receipt_path: Path | None = None,
    allow_synthetic_kat: bool = False,
    factor_precision_bits: int = 192,
) -> dict[str, Any]:
    """Validate a batch job and atomically write one ``TGDLQBI1`` frame."""

    job = load_job(job_path, allow_synthetic_kat=allow_synthetic_kat)
    plan = ResiduePlanCache().get(job.q)
    expected_m: int | None = None
    lattice_counts: list[int] = []
    for index, frame in enumerate(job.frames):
        expected_t = job.first_t_numerator + index * job.t_step_numerator
        m, lattice_count = _frame_headers(
            frame, plan=plan, expected_t_numerator=expected_t
        )
        if job.classification == CERTIFIED_CLASSIFICATION:
            certificate_m = _validate_certificate(
                frame, plan=plan, expected_t_numerator=expected_t
            )
            if certificate_m != m:
                _fail("certificate M and TGDLREC1 M differ")
        expected_m = m if expected_m is None else expected_m
        if m != expected_m:
            _fail("M changes inside a q-specific batch")
        lattice_counts.append(lattice_count)
    assert expected_m is not None
    factors = MPFRFactorProvider(factor_precision_bits)
    factor_boxes = [
        factors.factor(
            q=job.q,
            t_numerator=job.first_t_numerator + index * job.t_step_numerator,
            t_denominator=job.t_denominator,
        )
        for index in range(len(job.frames))
    ]
    orders = canonical_component_orders(job.q)
    if math.prod(orders) != plan.order:
        _fail("canonical component orders and CRT residue plan differ")
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        _fail(f"refusing to replace immutable output: {output_path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            writer = _HashingWriter(output)
            writer.write(
                INPUT_HEADER.pack(
                    INPUT_MAGIC,
                    FORMAT_VERSION,
                    job.q,
                    LATTICE_ROWS,
                    TAYLOR_DEGREE,
                    len(orders),
                    len(job.frames),
                    expected_m,
                    0,
                    plan.order,
                    job.first_t_numerator,
                    job.t_denominator,
                    job.t_step_numerator,
                    len(job.frames) * LATTICE_ROWS * TAYLOR_COLUMNS,
                    len(job.frames) * plan.order,
                    0,
                )
            )
            for a in canonical_residue_order(job.q):
                writer.write(
                    RESIDUE_DESCRIPTOR.pack(a, canonical_lattice_row(job.q, a))
                )
            for factor in factor_boxes:
                writer.write(FRAME_FACTOR.pack(*factor))
            lattice_bytes = LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
            for frame, count in zip(job.frames, lattice_counts):
                if count != LATTICE_ROWS * TAYLOR_COLUMNS:
                    _fail("lattice cell count changed after preflight")
                with frame.lattice_input.path.open("rb") as source:
                    source.seek(LATTICE_INPUT_HEADER.size)
                    _copy_exact(source, writer, lattice_bytes)
            for frame in job.frames:
                writer.write(_frame_boxes(frame, plan=plan))
            output.flush()
            os.fsync(output.fileno())
        # Close a path-replacement window after parsing every upstream byte.
        for index, frame in enumerate(job.frames):
            for name, artifact in (
                ("lattice_input", frame.lattice_input),
                ("finite_recovery", frame.finite_recovery),
                ("lattice_certificate", frame.lattice_certificate),
                ("lattice_replay", frame.lattice_replay),
            ):
                if artifact is not None:
                    try:
                        _verify_artifact(artifact, f"post-parse frames[{index}].{name}")
                    except RuntimeError as error:
                        raise DirichletLargeQBatchError(str(error)) from error
        os.replace(temporary, output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    upstream = hashlib.sha256()
    for frame in job.frames:
        for artifact in (
            frame.lattice_input,
            frame.finite_recovery,
            frame.lattice_certificate,
            frame.lattice_replay,
        ):
            if artifact is not None:
                upstream.update(bytes.fromhex(artifact.sha256))
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "checker_id": CHECKER_ID,
        "classification": (
            "certified_box_input_for_directed_cuda_batch_only"
            if job.classification == CERTIFIED_CLASSIFICATION
            else "synthetic_largeq_batch_kat_only"
        ),
        "job": {"path": str(job.path), "sha256": job.sha256},
        "q": job.q,
        "M": expected_m,
        "first_t_numerator": job.first_t_numerator,
        "t_denominator": job.t_denominator,
        "t_step_numerator": job.t_step_numerator,
        "batch_count": len(job.frames),
        "group_order": plan.order,
        "value_count": len(job.frames) * plan.order,
        "output": {
            "path": str(output_path),
            "sha256": writer.digest.hexdigest(),
            "size_bytes": writer.size,
            "magic": INPUT_MAGIC.decode("ascii"),
        },
        "upstream_artifact_digest_chain_sha256": upstream.hexdigest(),
        "q_to_the_minus_s_factors": [
            {
                "t_numerator": job.first_t_numerator
                + index * job.t_step_numerator,
                "binary64_hex": [value.hex() for value in factor],
            }
            for index, factor in enumerate(factor_boxes)
        ],
        "factor_backend": {
            "library": "MPFR",
            "version": factors.version,
            "precision_bits": factors.precision_bits,
            "device_transcendental_calls": 0,
        },
        "bounded_working_set": {
            "canonical_box_frames_resident": 1,
            "maximum_box_buffer_bytes": plan.order * CERTIFIED_RESIDUE_BOX.size,
            "batch_payload_bytes": writer.size,
        },
        "decisions": {
            "lattice_and_recovery_hashes_verified": True,
            "higher_precision_certificate_replay_verified": (
                job.classification == CERTIFIED_CLASSIFICATION
            ),
            "materialized_TGDLATO1_required": False,
            "canonical_crt_order_emitted": True,
            "cuda_transcendentals_required": False,
            "external_atom_discharged": False,
        },
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    if receipt_path is not None:
        receipt_path = receipt_path.resolve()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        if receipt_path.exists():
            _fail(f"refusing to replace immutable receipt: {receipt_path}")
        receipt_path.write_bytes(canonical_json_bytes(receipt))
    return receipt


def write_job_from_composition_job(
    composition_job_path: Path,
    output_path: Path,
    *,
    certified: bool,
) -> dict[str, Any]:
    """Create a no-Taylor-output batch job from the older job format.

    This compatibility authoring helper copies artifact records, not files.  A
    certified conversion drops ``TGDLATO1`` and its stage receipt because the
    fused runner performs that Taylor step itself.
    """

    try:
        value, _ = _load_canonical_json(composition_job_path, "composition job")
    except RuntimeError as error:
        raise DirichletLargeQBatchError(str(error)) from error
    required = {
        "schema", "schema_version", "classification", "q",
        "first_t_numerator", "t_denominator", "t_step_numerator", "frames",
    }
    if set(value) != required or not isinstance(value.get("frames"), list):
        _fail("composition job cannot be converted")
    names = {"lattice_input", "finite_recovery"}
    if certified:
        names |= {"lattice_certificate", "lattice_replay"}
    converted_frames: list[dict[str, Any]] = []
    for index, frame in enumerate(value["frames"]):
        if not isinstance(frame, dict) or not names <= set(frame):
            _fail(f"composition frames[{index}] lacks a required artifact")
        converted: dict[str, Any] = {}
        for name in sorted(names):
            record = frame[name]
            artifact_path = Path(record["path"])
            if not artifact_path.is_absolute():
                artifact_path = composition_job_path.resolve().parent / artifact_path
            converted[name] = artifact_record(
                artifact_path, relative_to=output_path.resolve().parent
            )
        converted_frames.append(converted)
    result = {
        "schema": JOB_SCHEMA,
        "schema_version": 1,
        "classification": (
            CERTIFIED_CLASSIFICATION if certified else SYNTHETIC_CLASSIFICATION
        ),
        "q": value["q"],
        "first_t_numerator": value["first_t_numerator"],
        "t_denominator": value["t_denominator"],
        "t_step_numerator": value["t_step_numerator"],
        "frames": converted_frames,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        _fail(f"refusing to replace immutable job: {output_path.resolve()}")
    output_path.write_bytes(canonical_json_bytes(result))
    return result


def _source_batch_descriptor_values(batch_size: int) -> int:
    # Each input frame repeats q's descriptor table.  This exact count is kept
    # separate from the one-time residue work to make the remaining I/O clear.
    phi = list(range(SOURCE_Q_STOP + 1))
    for prime in range(2, SOURCE_Q_STOP + 1):
        if phi[prime] != prime:
            continue
        for multiple in range(prime, SOURCE_Q_STOP + 1, prime):
            phi[multiple] -= phi[multiple] // prime
    return sum(
        ((maximum_t_index(q) + batch_size) // batch_size) * phi[q]
        for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1)
    )


def source_work(*, batch_size: int = MAXIMUM_BATCH_COUNT) -> dict[str, Any]:
    """Exact main-grid work, launch count, and certified-box I/O boundary."""

    if not 1 <= batch_size <= MAXIMUM_BATCH_COUNT:
        _fail("batch size must be in 1..64")
    batch_invocations = sum(
        (maximum_t_index(q) + batch_size) // batch_size
        for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1)
    )
    descriptor_values = _source_batch_descriptor_values(batch_size)
    lattice_cells = SOURCE_Q_T_ROWS * LATTICE_ROWS * TAYLOR_COLUMNS
    factor_bytes = SOURCE_Q_T_ROWS * FRAME_FACTOR.size
    lattice_bytes = lattice_cells * LATTICE_CELL.size
    box_bytes = SOURCE_RESIDUE_INTERPOLATIONS * CERTIFIED_RESIDUE_BOX.size
    descriptor_bytes = descriptor_values * RESIDUE_DESCRIPTOR.size
    header_bytes = batch_invocations * INPUT_HEADER.size
    total = factor_bytes + lattice_bytes + box_bytes + descriptor_bytes + header_bytes
    q_count = SOURCE_Q_STOP - SOURCE_Q_START + 1
    return {
        "kind": "sparkinterval.tg.dirichlet_largeq_batch.work.v1",
        "q_start": SOURCE_Q_START,
        "q_stop": SOURCE_Q_STOP,
        "main_positive_grid_only": True,
        "batch_size": batch_size,
        "old_one_ordinate_process_invocations": SOURCE_Q_T_ROWS,
        "q_persistent_process_invocations": q_count,
        "process_invocations_avoided": SOURCE_Q_T_ROWS - q_count,
        "old_one_ordinate_kernel_launches": SOURCE_Q_T_ROWS,
        "fused_batch_kernel_launches": batch_invocations,
        "kernel_launches_avoided": SOURCE_Q_T_ROWS - batch_invocations,
        "kernel_launch_reduction_factor": SOURCE_Q_T_ROWS / batch_invocations,
        "residue_taylor_reconstructions": SOURCE_RESIDUE_INTERPOLATIONS,
        "residue_compositions": SOURCE_RESIDUE_INTERPOLATIONS,
        "lattice_cells_transferred_with_q_outer_schedule": lattice_cells,
        "certified_residue_boxes": SOURCE_RESIDUE_INTERPOLATIONS,
        "input_bytes": {
            "headers": header_bytes,
            "repeated_canonical_descriptors": descriptor_bytes,
            "mpfr_q_minus_s_factors": factor_bytes,
            "certified_hurwitz_lattice_cells": lattice_bytes,
            "certified_tail_plus_finite_recovery_boxes": box_bytes,
            "total": total,
            "decimal_petabytes_total": total / 1e15,
        },
        "maximum_single_batch_bytes": (
            INPUT_HEADER.size
            + MAXIMUM_GROUP_ORDER * RESIDUE_DESCRIPTOR.size
            + batch_size * FRAME_FACTOR.size
            + batch_size * LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
            + batch_size * MAXIMUM_GROUP_ORDER * CERTIFIED_RESIDUE_BOX.size
        ),
        "remaining_boundary": (
            "Arb/FLINT must generate and independently replay every lattice "
            "and finite-recovery rectangle; this implementation streams those "
            "boxes and does not make CUDA libdevice transcendental claims"
        ),
    }


def capability() -> dict[str, Any]:
    try:
        factor = MPFRFactorProvider()
        mpfr_available = True
        mpfr_version = factor.version
    except RuntimeError as error:
        mpfr_available = False
        mpfr_version = None
        mpfr_error = str(error)
    else:
        mpfr_error = None
    return {
        "kind": "sparkinterval.tg.dirichlet_largeq_batch.capability.v1",
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "source": SOURCE_URL,
        "algorithm": ALGORITHM_ID,
        "checker": CHECKER_ID,
        "classification": "source_scalable_directed_cuda_box_consumer_not_atom_closure",
        "maximum_batch_count": MAXIMUM_BATCH_COUNT,
        "mpfr_factor_provider_available": mpfr_available,
        "mpfr_version": mpfr_version,
        "mpfr_error": mpfr_error,
        "persistent_q_framed_service_implemented": True,
        "one_fused_kernel_launch_per_batch": True,
        "source_performance_ready": False,
        "certified_box_producer_integrated": False,
        "source_scale_io_plan_implemented": False,
        "materialized_taylor_output_required": False,
        "cuda_transcendental_calls": 0,
        "finite_recovery_gpu_transcendental_implementation": False,
        "certified_finite_recovery_boxes_required": True,
        "seeded_recovery_alternative": {
            "algorithm": "platt-dirichlet-finite-recovery-recurrence-seeds-v1",
            "implemented": True,
            "fused_cuda_service_implemented": True,
            "device_transcendental_calls": 0,
            "old_logical_input_bytes": 18_263_933_424_590_240,
            "seeded_logical_input_bytes": 5_180_404_381_680_112,
            "t_major_cache_contract_implemented": True,
            "t_major_unique_lattice_payload_bytes": 134_205_145_088,
            "former_t_major_descriptor_repeated_input_bytes": (
                41_413_846_139_376
            ),
            "direct_t_major_cuda_input_bytes": 286_556_459_000,
            "direct_t_major_input_including_recovery_seeds": 339_564_685_336,
            "t_major_cuda_broadcast_integrated": True,
            "t_major_cuda_output_integrated_into_multi_q_fft_lane": False,
            "source_supervisor_schedule_contract_implemented": True,
            "source_root_catalog_contract_implemented": True,
            "typed_fft_receipt_bundle_implemented": True,
            "t_major_typed_bundle_admission_adapter_implemented": True,
            "typed_bundle_lattice_payload_to_cache_row_binding_implemented": True,
            "t_major_shared_row_spool_and_fixed_q_roster_implemented": True,
            "fixed_q_pipeline_executor_consumes_spool_format": False,
            "typed_fft_receipt_bundle_integrated_into_t_major_lane": False,
            "t_major_zero_state_adapter_implemented": False,
            "remaining_boundary": (
                "populate and CUDA-integrate the authenticated t-major "
                "Hurwitz cache, implement a CUDA or measured CPU consumer for "
                "the shared-row fixed-q spool and wire typed-bundle admission "
                "into execution, implement the t-major zero-state path, then "
                "close source-wide widths"
            ),
            "external_atom_discharged": False,
        },
        "directed_cuda_operations": [
            "Taylor recurrence",
            "complex q^(-s) multiplication",
            "finite-recovery addback",
        ],
        "output": "TGDAFFI1 canonical CRT residue frame",
        "full_source_run_completed": False,
        "external_atom_discharged": False,
        "production_ready_for_full_atom": False,
    }


def pretty_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


__all__ = [
    "ALGORITHM_ID",
    "ATOM_ID",
    "CERTIFIED_CLASSIFICATION",
    "CERTIFIED_RESIDUE_BOX",
    "DirichletLargeQBatchError",
    "FORMAT_VERSION",
    "FRAME_FACTOR",
    "INPUT_HEADER",
    "INPUT_MAGIC",
    "JOB_SCHEMA",
    "MAXIMUM_BATCH_COUNT",
    "RECEIPT_SCHEMA",
    "RESIDUE_DESCRIPTOR",
    "SYNTHETIC_CLASSIFICATION",
    "capability",
    "load_job",
    "pack_input",
    "pretty_json",
    "source_work",
    "write_job_from_composition_job",
]
