# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Compact source-shaped artifacts for completed Dirichlet-L factors.

The completed critical-line multiplier is split as

```
Gamma((1 + 2 parity)/4 + i t/2) * exp(pi t/4)
* exp(i t/2 log(q/pi)).
```

The two parity/gamma rows are stored once for a t range.  A step catalog
stores one ``exp(i 5/128 log(q/pi))`` disk per active q, and each resident
phase stores only direct Arb conductor checkpoints every 4096 samples.  The
q-by-t factor table is never materialized.

These files are numerical inputs to a measured run, not proofs by
themselves.  Their validators bind layout, identities, and SHA-256; source
admission remains false until the producer and full range are qualified and
the resulting run is admitted through the repository's trust boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from typing import Any, NoReturn, Sequence

from tg_verifier.dirichlet_allchars_stage import (
    PRIMITIVE_MODULUS_ROSTER_VERSION,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_Q_START,
    SOURCE_Q_STOP,
)


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "tg-dirichlet-completed-factor-artifacts-v1"
FORMAT_VERSION = 1
CLASSIFICATION_BOUNDED = 0
CLASSIFICATION_FULL_SOURCE = 1
SOURCE_T_INDEX_STOP = 127_988
SOURCE_DENOMINATOR = 64
SOURCE_STEP_NUMERATOR = 5
CONDUCTOR_STEP_DENOMINATOR = 128
DEFAULT_CHECKPOINT_SPAN = 4096
DISK = struct.Struct("<ddd")

GAMMA_MAGIC = b"TGDCGAM1"
STEP_MAGIC = b"TGDCSTP1"
CHECKPOINT_MAGIC = b"TGDCCPB1"
GAMMA_HEADER = struct.Struct("<8sIIIIQQQQQ32s32s")
STEP_HEADER = struct.Struct("<8sIIIIIIQQ32s32s32s")
CHECKPOINT_HEADER = struct.Struct(
    "<8sIIIIQQQQIIQQ32s32s32s32s"
)
CHECKPOINT_RECORD = struct.Struct("<IIII")

assert GAMMA_HEADER.size == 128
assert STEP_HEADER.size == 144
assert CHECKPOINT_HEADER.size == 208
assert CHECKPOINT_RECORD.size == 16
assert DISK.size == 24

FACTOR_CONVENTION = (
    "TG_COMPLETED_FACTOR_V1|t=5j/64|"
    "gamma=Gamma((1+2a)/4+it/2)*exp(pi*t/4)|"
    "conductor=exp(i*t/2*log(q/pi))|"
    "step=exp(i*5/128*log(q/pi))|parity-major|"
    "one-conductor-step-application-per-sample"
)
FACTOR_CONVENTION_SHA256 = hashlib.sha256(
    FACTOR_CONVENTION.encode("ascii")
).hexdigest()


class DirichletCompletedFactorArtifactError(RuntimeError):
    """A completed-factor artifact failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletCompletedFactorArtifactError(message)


def _digest_bytes(value: str, *, label: str) -> bytes:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return bytes.fromhex(value)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def _disk(value: Sequence[float], *, label: str) -> tuple[float, float, float]:
    if (
        len(value) != 3
        or not all(math.isfinite(component) for component in value)
        or value[2] < 0.0
    ):
        _fail(f"{label} is not a finite nonnegative-radius disk")
    return float(value[0]), float(value[1]), float(value[2])


def _atomic_write(path: Path, raw: bytes) -> str:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _fail(f"refusing to replace immutable artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_bytes(raw)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return _sha256(raw)


def _read_bound(path: Path, maximum: int) -> bytes:
    path = path.resolve()
    size = path.stat().st_size
    if not 1 <= size <= maximum:
        _fail(f"artifact size is outside 1..{maximum}")
    return path.read_bytes()


@dataclass(frozen=True)
class GammaArtifact:
    classification: int
    first_t_index: int
    t_index_stop_exclusive: int
    producer_identity_sha256: str
    disks: tuple[tuple[float, float, float], ...]
    artifact_sha256: str

    @property
    def sample_count(self) -> int:
        return self.t_index_stop_exclusive - self.first_t_index


@dataclass(frozen=True)
class StepArtifact:
    classification: int
    q_start: int
    q_stop: int
    schedule_manifest_sha256: str
    execution_order_sha256: str
    disks: tuple[tuple[float, float, float], ...]
    artifact_sha256: str


@dataclass(frozen=True)
class CheckpointRecord:
    q: int
    sample_count: int
    checkpoints: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class CheckpointArtifact:
    classification: int
    phase_index: int
    first_t_index: int
    t_index_stop_exclusive: int
    checkpoint_span: int
    schedule_manifest_sha256: str
    phase_schedule_sha256: str
    gamma_artifact_sha256: str
    step_artifact_sha256: str
    records: tuple[CheckpointRecord, ...]
    artifact_sha256: str


def arb_producer_identity(*, precision: int) -> dict[str, Any]:
    """Bind the pinned Arb runtime and exact Python sources used for inputs."""

    if (
        isinstance(precision, bool)
        or not isinstance(precision, int)
        or not 128 <= precision <= 4096
    ):
        _fail("Arb producer precision is outside [128,4096]")
    try:
        import flint
        from tg_verifier.dirichlet_root_number_stage import require_flint
    except ImportError as error:
        raise DirichletCompletedFactorArtifactError(
            "pinned python-flint is required for Arb factor artifacts"
        ) from error
    require_flint()
    repository = Path(__file__).resolve().parents[1]
    source_paths = (
        Path(__file__).resolve(),
        repository
        / "tg_verifier/dirichlet_completed_sign_gpu_reducer.py",
        repository / "tg_verifier/dirichlet_root_number_stage.py",
        repository / "specifications/PYTHON_FLINT_0_9_UPSTREAM.json",
    )
    sources = tuple(
        {
            "path": str(path.relative_to(repository)),
            "sha256": _sha256(path.read_bytes()),
        }
        for path in source_paths
    )
    body = {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_factor_artifacts."
            "arb_producer_identity.v1"
        ),
        "algorithm": ALGORITHM_ID,
        "factor_convention_sha256": FACTOR_CONVENTION_SHA256,
        "precision_bits": precision,
        "python_flint_version": flint.__version__,
        "flint_version": flint.__FLINT_VERSION__,
        "flint_release": flint.__FLINT_RELEASE__,
        "sources": sources,
    }
    return {
        **body,
        "producer_identity_sha256": _sha256(_canonical_json(body)),
    }


def _arb_disk(value: Any) -> tuple[float, float, float]:
    from tg_verifier.dirichlet_completed_sign_gpu_reducer import (
        _binary_box,
        _box_disk,
    )

    return _box_disk(_binary_box(value))


def write_arb_gamma_artifact(
    path: Path,
    *,
    first_t_index: int,
    t_index_stop_exclusive: int,
    precision: int = 384,
    classification: int = CLASSIFICATION_BOUNDED,
) -> dict[str, Any]:
    """Generate shared parity/gamma disks directly with pinned Arb."""

    identity = arb_producer_identity(precision=precision)
    try:
        from flint import acb, arb, ctx
    except ImportError as error:
        raise DirichletCompletedFactorArtifactError(
            "pinned python-flint is required for Arb gamma artifacts"
        ) from error
    if not 0 <= first_t_index < t_index_stop_exclusive <= SOURCE_T_INDEX_STOP:
        _fail("Arb gamma range differs")
    previous_precision = ctx.prec
    try:
        ctx.prec = precision
        t_values = tuple(
            arb(SOURCE_STEP_NUMERATOR * index) / SOURCE_DENOMINATOR
            for index in range(first_t_index, t_index_stop_exclusive)
        )
        disks = tuple(
            _arb_disk(
                acb(arb(1 + 2 * parity) / 4, t / 2).gamma()
                * (arb.pi() * t / 4).exp()
            )
            for parity in (0, 1)
            for t in t_values
        )
    finally:
        ctx.prec = previous_precision
    digest = write_gamma_artifact(
        path,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
        parity_major_disks=disks,
        producer_identity_sha256=identity[
            "producer_identity_sha256"
        ],
        classification=classification,
    )
    return {
        **identity,
        "artifact_sha256": digest,
        "sample_count": t_index_stop_exclusive - first_t_index,
        "disk_count": len(disks),
        "source_range_qualified": False,
        "external_atom_discharged": False,
    }


def write_arb_step_artifact(
    path: Path,
    *,
    execution_qs: Sequence[int],
    q_start: int,
    q_stop: int,
    schedule_manifest_sha256: str,
    execution_order_sha256: str,
    precision: int = 384,
    classification: int = CLASSIFICATION_BOUNDED,
) -> dict[str, Any]:
    """Generate one exact-convention conductor step disk per execution q."""

    identity = arb_producer_identity(precision=precision)
    if (
        not execution_qs
        or len(set(execution_qs)) != len(execution_qs)
        or any(
            isinstance(q, bool)
            or not isinstance(q, int)
            or not 3 <= q <= SOURCE_Q_STOP
            for q in execution_qs
        )
        or min(execution_qs) != q_start
        or max(execution_qs) != q_stop
    ):
        _fail("Arb step execution roster differs")
    try:
        from flint import acb, arb, ctx
    except ImportError as error:
        raise DirichletCompletedFactorArtifactError(
            "pinned python-flint is required for Arb step artifacts"
        ) from error
    previous_precision = ctx.prec
    try:
        ctx.prec = precision
        disks = tuple(
            _arb_disk(
                acb(
                    0,
                    arb(SOURCE_STEP_NUMERATOR)
                    * (arb(q) / arb.pi()).log()
                    / (2 * SOURCE_DENOMINATOR),
                ).exp()
            )
            for q in execution_qs
        )
    finally:
        ctx.prec = previous_precision
    digest = write_step_artifact(
        path,
        q_start=q_start,
        q_stop=q_stop,
        execution_disks=disks,
        schedule_manifest_sha256=schedule_manifest_sha256,
        execution_order_sha256=execution_order_sha256,
        classification=classification,
    )
    return {
        **identity,
        "artifact_sha256": digest,
        "q_count": len(disks),
        "source_range_qualified": False,
        "external_atom_discharged": False,
    }


def write_arb_checkpoint_artifact(
    path: Path,
    *,
    phase_index: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
    checkpoint_span: int,
    q_sample_counts: Sequence[tuple[int, int]],
    schedule_manifest_sha256: str,
    phase_schedule_sha256: str,
    gamma_artifact_sha256: str,
    step_artifact_sha256: str,
    precision: int = 384,
    classification: int = CLASSIFICATION_BOUNDED,
) -> dict[str, Any]:
    """Generate direct Arb conductor checkpoints for one resident phase."""

    identity = arb_producer_identity(precision=precision)
    if (
        not q_sample_counts
        or len({q for q, _ in q_sample_counts}) != len(q_sample_counts)
        or not 0 <= first_t_index < t_index_stop_exclusive
        <= SOURCE_T_INDEX_STOP
        or not 1 <= checkpoint_span <= SOURCE_T_INDEX_STOP
        or any(
            isinstance(q, bool)
            or isinstance(samples, bool)
            or not isinstance(q, int)
            or not isinstance(samples, int)
            or not 3 <= q <= SOURCE_Q_STOP
            or not 1 <= samples
            <= t_index_stop_exclusive - first_t_index
            for q, samples in q_sample_counts
        )
    ):
        _fail("Arb checkpoint roster differs")
    try:
        from flint import acb, arb, ctx
    except ImportError as error:
        raise DirichletCompletedFactorArtifactError(
            "pinned python-flint is required for Arb checkpoints"
        ) from error
    previous_precision = ctx.prec
    try:
        ctx.prec = precision
        records: list[CheckpointRecord] = []
        for q, samples in q_sample_counts:
            logarithm = (arb(q) / arb.pi()).log()
            checkpoints = tuple(
                _arb_disk(
                    acb(
                        0,
                        arb(
                            SOURCE_STEP_NUMERATOR
                            * (first_t_index + sample)
                        )
                        * logarithm
                        / (2 * SOURCE_DENOMINATOR),
                    ).exp()
                )
                for sample in range(0, samples, checkpoint_span)
            )
            records.append(
                CheckpointRecord(
                    q=q,
                    sample_count=samples,
                    checkpoints=checkpoints,
                )
            )
    finally:
        ctx.prec = previous_precision
    digest = write_checkpoint_artifact(
        path,
        phase_index=phase_index,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
        checkpoint_span=checkpoint_span,
        records=records,
        schedule_manifest_sha256=schedule_manifest_sha256,
        phase_schedule_sha256=phase_schedule_sha256,
        gamma_artifact_sha256=gamma_artifact_sha256,
        step_artifact_sha256=step_artifact_sha256,
        classification=classification,
    )
    return {
        **identity,
        "artifact_sha256": digest,
        "q_count": len(records),
        "checkpoint_count": sum(
            len(record.checkpoints) for record in records
        ),
        "source_range_qualified": False,
        "external_atom_discharged": False,
    }


def write_gamma_artifact(
    path: Path,
    *,
    first_t_index: int,
    t_index_stop_exclusive: int,
    parity_major_disks: Sequence[Sequence[float]],
    producer_identity_sha256: str,
    classification: int = CLASSIFICATION_BOUNDED,
) -> str:
    rows = t_index_stop_exclusive - first_t_index
    if (
        classification not in (
            CLASSIFICATION_BOUNDED,
            CLASSIFICATION_FULL_SOURCE,
        )
        or not 0 <= first_t_index < t_index_stop_exclusive
        <= SOURCE_T_INDEX_STOP
        or len(parity_major_disks) != 2 * rows
        or (
            classification == CLASSIFICATION_FULL_SOURCE
            and (first_t_index != 0
                 or t_index_stop_exclusive != SOURCE_T_INDEX_STOP)
        )
    ):
        _fail("gamma artifact geometry differs")
    producer = _digest_bytes(
        producer_identity_sha256, label="gamma producer identity"
    )
    convention = bytes.fromhex(FACTOR_CONVENTION_SHA256)
    raw = bytearray(
        GAMMA_HEADER.pack(
            GAMMA_MAGIC,
            FORMAT_VERSION,
            classification,
            DISK.size,
            0,
            first_t_index,
            t_index_stop_exclusive,
            SOURCE_DENOMINATOR,
            SOURCE_STEP_NUMERATOR,
            len(parity_major_disks),
            convention,
            producer,
        )
    )
    for index, value in enumerate(parity_major_disks):
        raw.extend(DISK.pack(*_disk(value, label=f"gamma disk {index}")))
    return _atomic_write(path, bytes(raw))


def parse_gamma_artifact(
    path: Path, *, expected_sha256: str | None = None
) -> GammaArtifact:
    raw = _read_bound(
        path, GAMMA_HEADER.size + 2 * SOURCE_T_INDEX_STOP * DISK.size
    )
    if expected_sha256 is not None and _sha256(raw) != expected_sha256:
        _fail("gamma artifact SHA-256 differs")
    if len(raw) < GAMMA_HEADER.size:
        _fail("gamma artifact header is truncated")
    (
        magic,
        version,
        classification,
        disk_size,
        reserved,
        first,
        stop,
        denominator,
        step,
        count,
        convention,
        producer,
    ) = GAMMA_HEADER.unpack_from(raw)
    if (
        magic != GAMMA_MAGIC
        or version != FORMAT_VERSION
        or classification
        not in (CLASSIFICATION_BOUNDED, CLASSIFICATION_FULL_SOURCE)
        or disk_size != DISK.size
        or reserved != 0
        or not 0 <= first < stop <= SOURCE_T_INDEX_STOP
        or denominator != SOURCE_DENOMINATOR
        or step != SOURCE_STEP_NUMERATOR
        or count != 2 * (stop - first)
        or convention.hex() != FACTOR_CONVENTION_SHA256
        or len(raw) != GAMMA_HEADER.size + count * DISK.size
        or (
            classification == CLASSIFICATION_FULL_SOURCE
            and (first != 0 or stop != SOURCE_T_INDEX_STOP)
        )
    ):
        _fail("gamma artifact identity or size differs")
    disks = tuple(
        _disk(
            DISK.unpack_from(raw, GAMMA_HEADER.size + index * DISK.size),
            label=f"gamma disk {index}",
        )
        for index in range(count)
    )
    return GammaArtifact(
        classification=classification,
        first_t_index=first,
        t_index_stop_exclusive=stop,
        producer_identity_sha256=producer.hex(),
        disks=disks,
        artifact_sha256=_sha256(raw),
    )


def write_step_artifact(
    path: Path,
    *,
    q_start: int,
    q_stop: int,
    execution_disks: Sequence[Sequence[float]],
    schedule_manifest_sha256: str,
    execution_order_sha256: str,
    classification: int = CLASSIFICATION_BOUNDED,
) -> str:
    if (
        classification not in (
            CLASSIFICATION_BOUNDED,
            CLASSIFICATION_FULL_SOURCE,
        )
        or not 3 <= q_start <= q_stop <= SOURCE_Q_STOP
        or not execution_disks
        or len(execution_disks) > SOURCE_Q_STOP
        or (
            classification == CLASSIFICATION_FULL_SOURCE
            and (q_start != SOURCE_Q_START or q_stop != SOURCE_Q_STOP)
        )
    ):
        _fail("step artifact geometry differs")
    raw = bytearray(
        STEP_HEADER.pack(
            STEP_MAGIC,
            FORMAT_VERSION,
            classification,
            DISK.size,
            0,
            PRIMITIVE_MODULUS_ROSTER_VERSION,
            len(execution_disks),
            q_start,
            q_stop,
            _digest_bytes(
                schedule_manifest_sha256, label="schedule manifest"
            ),
            _digest_bytes(
                execution_order_sha256, label="execution order"
            ),
            bytes.fromhex(FACTOR_CONVENTION_SHA256),
        )
    )
    for index, value in enumerate(execution_disks):
        raw.extend(DISK.pack(*_disk(value, label=f"step disk {index}")))
    return _atomic_write(path, bytes(raw))


def parse_step_artifact(
    path: Path, *, expected_sha256: str | None = None
) -> StepArtifact:
    raw = _read_bound(
        path, STEP_HEADER.size + SOURCE_Q_STOP * DISK.size
    )
    if expected_sha256 is not None and _sha256(raw) != expected_sha256:
        _fail("step artifact SHA-256 differs")
    if len(raw) < STEP_HEADER.size:
        _fail("step artifact header is truncated")
    (
        magic,
        version,
        classification,
        disk_size,
        reserved,
        roster_version,
        q_count,
        q_start,
        q_stop,
        schedule,
        execution,
        convention,
    ) = STEP_HEADER.unpack_from(raw)
    if (
        magic != STEP_MAGIC
        or version != FORMAT_VERSION
        or classification
        not in (CLASSIFICATION_BOUNDED, CLASSIFICATION_FULL_SOURCE)
        or disk_size != DISK.size
        or reserved != 0
        or roster_version != PRIMITIVE_MODULUS_ROSTER_VERSION
        or q_count == 0
        or not 3 <= q_start <= q_stop <= SOURCE_Q_STOP
        or convention.hex() != FACTOR_CONVENTION_SHA256
        or len(raw) != STEP_HEADER.size + q_count * DISK.size
        or (
            classification == CLASSIFICATION_FULL_SOURCE
            and (q_start != SOURCE_Q_START or q_stop != SOURCE_Q_STOP)
        )
    ):
        _fail("step artifact identity or size differs")
    disks = tuple(
        _disk(
            DISK.unpack_from(raw, STEP_HEADER.size + index * DISK.size),
            label=f"step disk {index}",
        )
        for index in range(q_count)
    )
    return StepArtifact(
        classification=classification,
        q_start=q_start,
        q_stop=q_stop,
        schedule_manifest_sha256=schedule.hex(),
        execution_order_sha256=execution.hex(),
        disks=disks,
        artifact_sha256=_sha256(raw),
    )


def write_checkpoint_artifact(
    path: Path,
    *,
    phase_index: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
    checkpoint_span: int,
    records: Sequence[CheckpointRecord],
    schedule_manifest_sha256: str,
    phase_schedule_sha256: str,
    gamma_artifact_sha256: str,
    step_artifact_sha256: str,
    classification: int = CLASSIFICATION_BOUNDED,
) -> str:
    if (
        classification not in (
            CLASSIFICATION_BOUNDED,
            CLASSIFICATION_FULL_SOURCE,
        )
        or not 0 <= phase_index < 1_000_000
        or not 0 <= first_t_index < t_index_stop_exclusive
        <= SOURCE_T_INDEX_STOP
        or not 1 <= checkpoint_span <= SOURCE_T_INDEX_STOP
        or not records
    ):
        _fail("checkpoint artifact geometry differs")
    seen_qs: set[int] = set()
    total_checkpoints = 0
    for record in records:
        expected = (record.sample_count + checkpoint_span - 1) // checkpoint_span
        if (
            not 3 <= record.q <= SOURCE_Q_STOP
            or not 1 <= record.sample_count
            <= t_index_stop_exclusive - first_t_index
            or len(record.checkpoints) != expected
            or record.q in seen_qs
        ):
            _fail("checkpoint record geometry differs")
        seen_qs.add(record.q)
        total_checkpoints += expected
    raw = bytearray(
        CHECKPOINT_HEADER.pack(
            CHECKPOINT_MAGIC,
            FORMAT_VERSION,
            classification,
            DISK.size,
            CHECKPOINT_RECORD.size,
            phase_index,
            first_t_index,
            t_index_stop_exclusive,
            SOURCE_DENOMINATOR,
            SOURCE_STEP_NUMERATOR,
            checkpoint_span,
            len(records),
            total_checkpoints,
            _digest_bytes(
                schedule_manifest_sha256, label="schedule manifest"
            ),
            _digest_bytes(
                phase_schedule_sha256, label="phase schedule"
            ),
            _digest_bytes(
                gamma_artifact_sha256, label="gamma artifact"
            ),
            _digest_bytes(
                step_artifact_sha256, label="step artifact"
            ),
        )
    )
    for record in records:
        raw.extend(
            CHECKPOINT_RECORD.pack(
                record.q,
                record.sample_count,
                len(record.checkpoints),
                0,
            )
        )
        for index, value in enumerate(record.checkpoints):
            raw.extend(
                DISK.pack(
                    *_disk(
                        value,
                        label=f"q={record.q} checkpoint disk {index}",
                    )
                )
            )
    return _atomic_write(path, bytes(raw))


def parse_checkpoint_artifact(
    path: Path, *, expected_sha256: str | None = None
) -> CheckpointArtifact:
    # At most one checkpoint per source t row and active q is a deliberately
    # loose parser cap.  Exact file length is reconstructed below.
    raw = _read_bound(
        path,
        CHECKPOINT_HEADER.size
        + SOURCE_Q_STOP * CHECKPOINT_RECORD.size
        + 4_000_000 * DISK.size,
    )
    if expected_sha256 is not None and _sha256(raw) != expected_sha256:
        _fail("checkpoint artifact SHA-256 differs")
    if len(raw) < CHECKPOINT_HEADER.size:
        _fail("checkpoint artifact header is truncated")
    (
        magic,
        version,
        classification,
        disk_size,
        record_size,
        phase_index,
        first,
        stop,
        denominator,
        step,
        span,
        q_count,
        total_checkpoints,
        schedule,
        phase_schedule,
        gamma_sha,
        step_sha,
    ) = CHECKPOINT_HEADER.unpack_from(raw)
    if (
        magic != CHECKPOINT_MAGIC
        or version != FORMAT_VERSION
        or classification
        not in (CLASSIFICATION_BOUNDED, CLASSIFICATION_FULL_SOURCE)
        or disk_size != DISK.size
        or record_size != CHECKPOINT_RECORD.size
        or not 0 <= first < stop <= SOURCE_T_INDEX_STOP
        or denominator != SOURCE_DENOMINATOR
        or step != SOURCE_STEP_NUMERATOR
        or not 1 <= span <= SOURCE_T_INDEX_STOP
        or q_count == 0
        or total_checkpoints < q_count
    ):
        _fail("checkpoint artifact header differs")
    position = CHECKPOINT_HEADER.size
    records: list[CheckpointRecord] = []
    seen_qs: set[int] = set()
    observed_checkpoints = 0
    for record_index in range(q_count):
        if position + CHECKPOINT_RECORD.size > len(raw):
            _fail("checkpoint record header is truncated")
        q, samples, count, reserved = CHECKPOINT_RECORD.unpack_from(
            raw, position
        )
        position += CHECKPOINT_RECORD.size
        expected = (samples + span - 1) // span if samples else 0
        if (
            reserved != 0
            or not 3 <= q <= SOURCE_Q_STOP
            or not 1 <= samples <= stop - first
            or count != expected
            or q in seen_qs
        ):
            _fail("checkpoint record identity differs")
        seen_qs.add(q)
        disks: list[tuple[float, float, float]] = []
        for checkpoint in range(count):
            if position + DISK.size > len(raw):
                _fail("checkpoint disk roster is truncated")
            disks.append(
                _disk(
                    DISK.unpack_from(raw, position),
                    label=(
                        f"checkpoint record {record_index} "
                        f"disk {checkpoint}"
                    ),
                )
            )
            position += DISK.size
        observed_checkpoints += count
        records.append(
            CheckpointRecord(
                q=q,
                sample_count=samples,
                checkpoints=tuple(disks),
            )
        )
    if position != len(raw) or observed_checkpoints != total_checkpoints:
        _fail("checkpoint artifact size or total differs")
    return CheckpointArtifact(
        classification=classification,
        phase_index=phase_index,
        first_t_index=first,
        t_index_stop_exclusive=stop,
        checkpoint_span=span,
        schedule_manifest_sha256=schedule.hex(),
        phase_schedule_sha256=phase_schedule.hex(),
        gamma_artifact_sha256=gamma_sha.hex(),
        step_artifact_sha256=step_sha.hex(),
        records=tuple(records),
        artifact_sha256=_sha256(raw),
    )


def source_storage_projection(
    *,
    checkpoint_span: int = DEFAULT_CHECKPOINT_SPAN,
) -> dict[str, Any]:
    """Exact byte projection for the ten pinned resident phases."""

    if checkpoint_span != DEFAULT_CHECKPOINT_SPAN:
        _fail("source projection is pinned to checkpoint span 4096")
    from tg_verifier.dirichlet_allchars_q_scheduler import (
        source_schedule_records,
    )
    from tg_verifier.dirichlet_resident_qmajor_plan import PINNED_PHASES

    schedule = source_schedule_records()
    phase_rows: list[dict[str, int]] = []
    total_checkpoints = 0
    total_phase_records = 0
    for phase in PINNED_PHASES:
        q_count = 0
        checkpoints = 0
        for record in schedule:
            samples = max(
                0,
                min(
                    record.t_index_count,
                    phase.t_index_stop_exclusive,
                )
                - phase.first_t_index,
            )
            if samples == 0:
                continue
            q_count += 1
            checkpoints += (
                samples + checkpoint_span - 1
            ) // checkpoint_span
        bytes_ = (
            CHECKPOINT_HEADER.size
            + q_count * CHECKPOINT_RECORD.size
            + checkpoints * DISK.size
        )
        phase_rows.append(
            {
                "phase_index": phase.phase_index,
                "active_q_count": q_count,
                "checkpoint_count": checkpoints,
                "artifact_bytes": bytes_,
            }
        )
        total_checkpoints += checkpoints
        total_phase_records += q_count
    gamma_bytes = (
        GAMMA_HEADER.size + 2 * SOURCE_T_INDEX_STOP * DISK.size
    )
    step_bytes = (
        STEP_HEADER.size + len(schedule) * DISK.size
    )
    checkpoint_bytes = sum(row["artifact_bytes"] for row in phase_rows)
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_factor_artifacts."
            "source_storage_projection.v1"
        ),
        "factor_convention_sha256": FACTOR_CONVENTION_SHA256,
        "source_t_rows": SOURCE_T_INDEX_STOP,
        "source_q_count": len(schedule),
        "checkpoint_span": checkpoint_span,
        "gamma_artifact_bytes": gamma_bytes,
        "step_catalog_bytes": step_bytes,
        "phase_checkpoint_record_count": total_phase_records,
        "phase_checkpoint_count": total_checkpoints,
        "phase_checkpoint_artifact_bytes": checkpoint_bytes,
        "total_artifact_bytes": gamma_bytes + step_bytes + checkpoint_bytes,
        "naive_q_by_t_factor_disk_bytes": (
            2
            * sum(record.t_index_count for record in schedule)
            * DISK.size
        ),
        "phases": phase_rows,
        "source_artifacts_generated": False,
        "source_range_qualified": False,
        "external_atom_discharged": False,
    }


def write_synthetic_unit_artifacts(
    directory: Path,
    *,
    q: int,
    first_t_index: int,
    sample_count: int,
    checkpoint_span: int = DEFAULT_CHECKPOINT_SPAN,
) -> dict[str, Any]:
    """Write a bounded unit-disk fixture for the CUDA integration KAT."""

    if (
        not 3 <= q <= SOURCE_Q_STOP
        or not 0 <= first_t_index
        or not 1 <= sample_count <= SOURCE_T_INDEX_STOP - first_t_index
    ):
        _fail("synthetic factor fixture geometry differs")
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    unit = (1.0, 0.0, 0.0)
    schedule = hashlib.sha256(
        struct.pack("<II", q, sample_count)
    ).hexdigest()
    phase_schedule = hashlib.sha256(
        struct.pack("<III", q, first_t_index, sample_count)
    ).hexdigest()
    producer = hashlib.sha256(
        b"synthetic-unit-completed-factor-fixture-v1"
    ).hexdigest()
    gamma_path = directory / "gamma.bin"
    step_path = directory / "steps.bin"
    checkpoint_path = directory / "checkpoints.bin"
    gamma_sha = write_gamma_artifact(
        gamma_path,
        first_t_index=first_t_index,
        t_index_stop_exclusive=first_t_index + sample_count,
        parity_major_disks=(unit,) * (2 * sample_count),
        producer_identity_sha256=producer,
    )
    step_sha = write_step_artifact(
        step_path,
        q_start=q,
        q_stop=q,
        execution_disks=(unit,),
        schedule_manifest_sha256=schedule,
        execution_order_sha256=schedule,
    )
    checkpoint_count = (
        sample_count + checkpoint_span - 1
    ) // checkpoint_span
    checkpoint_sha = write_checkpoint_artifact(
        checkpoint_path,
        phase_index=0,
        first_t_index=first_t_index,
        t_index_stop_exclusive=first_t_index + sample_count,
        checkpoint_span=checkpoint_span,
        records=(
            CheckpointRecord(
                q=q,
                sample_count=sample_count,
                checkpoints=(unit,) * checkpoint_count,
            ),
        ),
        schedule_manifest_sha256=schedule,
        phase_schedule_sha256=phase_schedule,
        gamma_artifact_sha256=gamma_sha,
        step_artifact_sha256=step_sha,
    )
    return {
        "algorithm": ALGORITHM_ID,
        "classification": "bounded_synthetic_unit_fixture",
        "gamma_path": str(gamma_path),
        "gamma_sha256": gamma_sha,
        "step_path": str(step_path),
        "step_sha256": step_sha,
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": checkpoint_sha,
        "schedule_manifest_sha256": schedule,
        "phase_schedule_sha256": phase_schedule,
        "source_range_qualified": False,
        "external_atom_discharged": False,
    }


def write_bounded_arb_artifacts(
    directory: Path,
    *,
    q: int,
    first_t_index: int,
    sample_count: int,
    precision: int = 384,
    checkpoint_span: int = DEFAULT_CHECKPOINT_SPAN,
) -> dict[str, Any]:
    """Generate one small real-Arb bundle for producer qualification."""

    if (
        isinstance(q, bool)
        or isinstance(first_t_index, bool)
        or isinstance(sample_count, bool)
        or not isinstance(q, int)
        or not isinstance(first_t_index, int)
        or not isinstance(sample_count, int)
        or not 3 <= q <= SOURCE_Q_STOP
        or not 0 <= first_t_index
        or not 1 <= sample_count <= SOURCE_T_INDEX_STOP - first_t_index
    ):
        _fail("bounded Arb factor fixture geometry differs")
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    schedule = hashlib.sha256(
        struct.pack("<II", q, sample_count)
    ).hexdigest()
    phase_schedule = hashlib.sha256(
        struct.pack("<III", q, first_t_index, sample_count)
    ).hexdigest()
    gamma_path = directory / "gamma.bin"
    step_path = directory / "steps.bin"
    checkpoint_path = directory / "checkpoints.bin"
    gamma = write_arb_gamma_artifact(
        gamma_path,
        first_t_index=first_t_index,
        t_index_stop_exclusive=first_t_index + sample_count,
        precision=precision,
    )
    steps = write_arb_step_artifact(
        step_path,
        execution_qs=(q,),
        q_start=q,
        q_stop=q,
        schedule_manifest_sha256=schedule,
        execution_order_sha256=schedule,
        precision=precision,
    )
    checkpoints = write_arb_checkpoint_artifact(
        checkpoint_path,
        phase_index=0,
        first_t_index=first_t_index,
        t_index_stop_exclusive=first_t_index + sample_count,
        checkpoint_span=checkpoint_span,
        q_sample_counts=((q, sample_count),),
        schedule_manifest_sha256=schedule,
        phase_schedule_sha256=phase_schedule,
        gamma_artifact_sha256=gamma["artifact_sha256"],
        step_artifact_sha256=steps["artifact_sha256"],
        precision=precision,
    )
    return {
        "algorithm": ALGORITHM_ID,
        "classification": "bounded_real_arb_producer_qualification",
        "q": q,
        "first_t_index": first_t_index,
        "sample_count": sample_count,
        "precision_bits": precision,
        "checkpoint_span": checkpoint_span,
        "gamma_path": str(gamma_path),
        "gamma_sha256": gamma["artifact_sha256"],
        "step_path": str(step_path),
        "step_sha256": steps["artifact_sha256"],
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": checkpoints["artifact_sha256"],
        "producer_identity_sha256": gamma[
            "producer_identity_sha256"
        ],
        "schedule_manifest_sha256": schedule,
        "phase_schedule_sha256": phase_schedule,
        "source_range_qualified": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "CHECKPOINT_HEADER",
    "CHECKPOINT_MAGIC",
    "CHECKPOINT_RECORD",
    "CheckpointArtifact",
    "CheckpointRecord",
    "DEFAULT_CHECKPOINT_SPAN",
    "DirichletCompletedFactorArtifactError",
    "DISK",
    "FACTOR_CONVENTION",
    "FACTOR_CONVENTION_SHA256",
    "GAMMA_HEADER",
    "GAMMA_MAGIC",
    "GammaArtifact",
    "STEP_HEADER",
    "STEP_MAGIC",
    "StepArtifact",
    "arb_producer_identity",
    "parse_checkpoint_artifact",
    "parse_gamma_artifact",
    "parse_step_artifact",
    "source_storage_projection",
    "write_arb_checkpoint_artifact",
    "write_arb_gamma_artifact",
    "write_arb_step_artifact",
    "write_bounded_arb_artifacts",
    "write_checkpoint_artifact",
    "write_gamma_artifact",
    "write_step_artifact",
    "write_synthetic_unit_artifacts",
]
