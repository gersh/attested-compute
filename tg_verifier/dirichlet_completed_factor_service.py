# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resumable source-shaped service for completed Dirichlet-L factors.

The service has twelve immutable jobs:

* one full-t-range parity/gamma catalog;
* one full execution-order conductor-step catalog; and
* ten independently runnable resident-phase checkpoint catalogs.

Initialization reconstructs the exact primitive-V2 q manifest, the ten
``build_stream_plan`` results, and the corresponding
``phase_schedule_projection`` commitments.  Every output is published as an
atomic directory containing an artifact and a self-hashed receipt.  A killed
worker therefore leaves either no visible job or one complete immutable job;
unpublished staging directories are ignored and may be audited separately.

These are numerical inputs to a later measured computation.  Completing all
twelve jobs is not a Dirichlet source run, a zero-isolation or Turing
certificate, trusted execution evidence, or an external-atom discharge.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Callable, Mapping, NoReturn

from tg_verifier.dirichlet_allchars_q_scheduler import (
    FULL_SOURCE_CLASSIFICATION,
    PINNED_SOURCE_ACTIVE_MODULI,
    PINNED_SOURCE_EXECUTION_SHA256,
    PINNED_SOURCE_ROSTER_SHA256,
    ParsedScheduleManifest,
    _phase_schedule_projection_from_parsed,
    parse_schedule_manifest,
)
from tg_verifier.dirichlet_completed_factor_artifacts import (
    ALGORITHM_ID as ARTIFACT_ALGORITHM_ID,
    CHECKPOINT_HEADER,
    CHECKPOINT_RECORD,
    CLASSIFICATION_FULL_SOURCE,
    DEFAULT_CHECKPOINT_SPAN,
    DISK,
    FACTOR_CONVENTION_SHA256,
    GAMMA_HEADER,
    SOURCE_T_INDEX_STOP,
    STEP_HEADER,
    CheckpointArtifact,
    GammaArtifact,
    StepArtifact,
    arb_producer_identity,
    parse_checkpoint_artifact,
    parse_gamma_artifact,
    parse_step_artifact,
    write_arb_checkpoint_artifact,
    write_arb_gamma_artifact,
    write_arb_step_artifact,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_Q_START,
    SOURCE_Q_STOP,
)
from tg_verifier.dirichlet_resident_qmajor_stream import (
    EXACT_CANDIDATE_PHASE_COVERAGE,
    PHASE_CUTS,
    build_stream_plan,
    canonical_q_lanes,
    lane_partition_digest,
    phase_plan_digest,
)
from tg_verifier.dirichlet_resident_qmajor_plan import (
    PINNED_PHASE_ACTIVE_Q_COUNTS,
    PINNED_PHASE_ROW_COUNTS,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "tg-dirichlet-completed-factor-source-service-v1"
PLAN_SCHEMA = (
    "sparkinterval.tg.dirichlet_completed_factor_source_service.plan.v1"
)
JOB_SCHEMA = (
    "sparkinterval.tg.dirichlet_completed_factor_source_service.job.v1"
)
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_completed_factor_source_service.receipt.v1"
)
STATUS_SCHEMA = (
    "sparkinterval.tg.dirichlet_completed_factor_source_service.status.v1"
)
PLANNER_IDENTITY_SCHEMA = (
    "sparkinterval.tg.dirichlet_completed_factor_source_service."
    "planner_identity.v1"
)

PLAN_FILENAME = "source-plan.json"
SCHEDULE_FILENAME = "q-order.tgdqord1"
OUTPUT_DIRECTORY = "outputs"
STAGING_DIRECTORY = "staging"
ARTIFACT_FILENAME = "artifact.bin"
RECEIPT_FILENAME = "receipt.json"
MAXIMUM_CONTROL_BYTES = 4 * 1024 * 1024
MAXIMUM_SCHEDULE_BYTES = 4 * 1024 * 1024

# The full-source manifest bytes are canonical: the header contains no
# timestamps or paths, and the execution roster has one unique canonical
# order.  Pinning the whole file closes a gap left by pinning only its two
# internal roster commitments.
PINNED_SOURCE_MANIFEST_SHA256 = (
    "a5ae1af2e4a9e944ccef559e169a13cd74f21c220ed882950ecd4491cbf13e93"
)
PINNED_LANE_PARTITION_SHA256 = (
    "a749174a3fba56bf6a255d61e2135b3997574c22f17c45589851ea8e592b554c"
)
PINNED_PHASE_PLAN_SHA256 = (
    "ec546a536c8a448aac20b0ac2eca9cf724c1dc065bdf03377fbcb9dc112cc172",
    "1930e5681030814187525d9be7b675b35d47e07d744a9b6565175af0bc2b8efd",
    "d8a346f9c6700c21b175d990348abc5f3dc0e327edd7d3bad3a5b09864891741",
    "91dbfd1c918b9e7f1b2af069174832080b6d6fabccee9cf155098e821b1d1981",
    "515a3d978ed1c791943eab687eaa70a3b1366bd6b73db511b5c8c8fbacb895f0",
    "a645430f33096d511127c3b7a04159101d1d084740402d3aaab3cfd5a55129e3",
    "be3e1ab758f35e32c3e2e50cdb1ea7c53cea8a15d66fc75a1403f43c3d913b19",
    "2124c32310587a41c3e70d4a72e0847823234d0537a27ee8d3bc139f511ec911",
    "a4105333776217879bea40e2bc17f54afb1df12671042a7fcdae8846d98ad7e3",
    "43fde6f218fd9b4a0a105ad7ec4527dadc498656fc3efcf4153c51b9d48e473e",
)
PINNED_PHASE_SCHEDULE_SHA256 = (
    "b52506f92b9f6313486b5005203055e7e7b58edf876d2573bdafb008279e099a",
    "b95a0b877116a54f3a68ea887b16f7346c287a02efc623e126f11e7592291ae9",
    "b075d5e929597240615ed839bb13dfc836f44091976be0475acc85eccb393639",
    "b896a2c9538317bbcd7fb08bd090adc7b5c4b1885a975a065c36286327dd588a",
    "1b66b25c692e95da50d9a9cd8b5dcbf3a0d92d004e24df60b2182067af3967a5",
    "1a95a82751ec50795e15c0739797666e8953b6d3127e56d8663e6fee868d6228",
    "c72a46355a5f316b1f07735889e8fd7abc89def8fc5c6daee66f79e7777e199d",
    "77895057ab76cd2437dbed1ffe0653785e23ef056ef32ea2a2c91f8d0464ff41",
    "5b53247c4c146a59b8cd1d2e5ef8705de703161f5329aa03a6f5b849b90a4fb9",
    "22e3078577073b4c1c05a8fcebb6b96bf60613b539614ece4646953ba9f9d857",
)
PINNED_PHASE_CHECKPOINT_COUNTS = (
    292_500,
    292_500,
    292_500,
    292_500,
    292_500,
    255_543,
    187_230,
    359_018,
    71_741,
    15_871,
)

_HEX = frozenset("0123456789abcdef")


class DirichletCompletedFactorServiceError(RuntimeError):
    """A source factor plan, job, artifact, or receipt failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletCompletedFactorServiceError(message)


@dataclass(frozen=True)
class _PhaseGeometry:
    phase_index: int
    first_t_index: int
    t_index_stop_exclusive: int
    phase_plan_sha256: str
    phase_schedule_sha256: str
    active_q_count: int
    t_index_row_count: int
    checkpoint_count: int


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _integer(
    value: object,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        _fail(f"{label} is outside [{minimum},{maximum}]")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON value is forbidden: {value}")


def _read_regular(path: Path, *, label: str, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletCompletedFactorServiceError(
            f"cannot safely open {label}: {path}"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(status.st_mode)
            or not 1 <= status.st_size <= maximum
        ):
            _fail(f"{label} size is outside 1..{maximum}")
        raw = source.read(maximum + 1)
    if len(raw) > maximum:
        _fail(f"{label} exceeds its fixed size bound")
    return raw


def _read_canonical_json(
    path: Path, *, label: str
) -> dict[str, Any]:
    raw = _read_regular(path, label=label, maximum=MAXIMUM_CONTROL_BYTES)
    try:
        value = json.loads(
            raw,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletCompletedFactorServiceError(
            f"{label} is not valid JSON"
        ) from error
    if not isinstance(value, dict) or _canonical_json_bytes(value) != raw:
        _fail(f"{label} is not one canonical JSON object")
    return value


def _atomic_bytes(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        _fail(f"refusing to replace immutable file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            if output.write(raw) != len(raw):
                _fail(f"short write for immutable file: {path}")
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        temporary.unlink()
        _fsync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_bytes(path, _canonical_json_bytes(dict(value)))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_regular(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            _fail("completed-factor artifact is not a regular file")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _self_hashed(
    body: Mapping[str, Any], field: str
) -> dict[str, Any]:
    result = dict(body)
    result[field] = _sha256(_canonical_json_bytes(result))
    return result


def _job(body: Mapping[str, Any]) -> dict[str, Any]:
    return _self_hashed(body, "job_sha256")


def _receipt(body: Mapping[str, Any]) -> dict[str, Any]:
    return _self_hashed(body, "receipt_sha256")


def _job_directory_name(kind: str, phase_index: int | None = None) -> str:
    if kind == "gamma":
        return "gamma"
    if kind == "steps":
        return "steps"
    if kind == "phase-checkpoints" and phase_index is not None:
        return f"phase-{phase_index:02d}"
    _fail("completed-factor job identity differs")


@lru_cache(maxsize=4)
def _exact_schedule(raw: bytes) -> ParsedScheduleManifest:
    schedule = parse_schedule_manifest(raw)
    if (
        schedule.classification != FULL_SOURCE_CLASSIFICATION
        or schedule.manifest_sha256 != PINNED_SOURCE_MANIFEST_SHA256
        or schedule.source_roster_sha256
        != PINNED_SOURCE_ROSTER_SHA256
        or schedule.execution_order_sha256
        != PINNED_SOURCE_EXECUTION_SHA256
        or schedule.q_start != SOURCE_Q_START
        or schedule.q_stop != SOURCE_Q_STOP
        or schedule.q_count != PINNED_SOURCE_ACTIVE_MODULI
    ):
        _fail("q-order manifest is not the exact pinned full-source manifest")
    return schedule


def _validated_producer_identity(
    identity: Mapping[str, Any], *, precision: int
) -> dict[str, Any]:
    result = dict(identity)
    if (
        result.get("schema")
        != (
            "sparkinterval.tg.dirichlet_completed_factor_artifacts."
            "arb_producer_identity.v1"
        )
        or result.get("algorithm") != ARTIFACT_ALGORITHM_ID
        or result.get("factor_convention_sha256")
        != FACTOR_CONVENTION_SHA256
        or result.get("precision_bits") != precision
        or not isinstance(result.get("sources"), (list, tuple))
    ):
        _fail("Arb producer identity metadata differs")
    claimed = _digest(
        result.get("producer_identity_sha256"), "producer identity"
    )
    body = dict(result)
    del body["producer_identity_sha256"]
    if claimed != _sha256(_canonical_json_bytes(body)):
        _fail("Arb producer identity self-commitment differs")
    # JSON plans represent the source roster as a list even though the
    # in-process producer returns a tuple.
    result["sources"] = list(result["sources"])
    return result


def planner_identity() -> dict[str, Any]:
    """Hash every project source that determines the twelve-job geometry."""

    repository = Path(__file__).resolve().parents[1]
    source_paths = (
        Path(__file__).resolve(),
        repository / "tg_verifier/dirichlet_allchars_q_scheduler.py",
        repository / "tg_verifier/dirichlet_resident_qmajor_plan.py",
        repository / "tg_verifier/dirichlet_resident_qmajor_stream.py",
    )
    body = {
        "schema": PLANNER_IDENTITY_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "schedule_manifest_sha256": PINNED_SOURCE_MANIFEST_SHA256,
        "execution_order_sha256": PINNED_SOURCE_EXECUTION_SHA256,
        "lane_partition_sha256": PINNED_LANE_PARTITION_SHA256,
        "phase_plan_sha256": list(PINNED_PHASE_PLAN_SHA256),
        "phase_schedule_sha256": list(
            PINNED_PHASE_SCHEDULE_SHA256
        ),
        "sources": [
            {
                "path": str(path.relative_to(repository)),
                "sha256": _sha256(path.read_bytes()),
            }
            for path in source_paths
        ],
    }
    return _self_hashed(body, "planner_identity_sha256")


def _source_phase_projection(
    schedule: ParsedScheduleManifest,
    *,
    phase_index: int,
    phase_plan_sha256: str,
):
    return _phase_schedule_projection_from_parsed(
        schedule,
        phase_plan_sha256=phase_plan_sha256,
        first_t_index=PHASE_CUTS[phase_index],
        t_index_stop_exclusive=PHASE_CUTS[phase_index + 1],
        start_execution_q_index=0,
        stop_execution_q_index=schedule.q_count,
    )


@lru_cache(maxsize=4)
def _source_geometry(
    schedule: ParsedScheduleManifest,
    checkpoint_span: int,
    replay_phase_projections: bool,
) -> tuple[str, tuple[_PhaseGeometry, ...]]:
    """Reconstruct compact exact phase identities without retaining rosters.

    Initialization replays all ten projections.  Later commands use the
    persisted, independently pinned geometry and replay only the selected
    phase when its exact q/sample roster is needed.
    """

    lanes = canonical_q_lanes(0, schedule.q_count)
    partition_sha256 = lane_partition_digest(
        schedule,
        lanes,
        start_execution_q_index=0,
        stop_execution_q_index=schedule.q_count,
    )
    if partition_sha256 != PINNED_LANE_PARTITION_SHA256:
        _fail("source q-lane partition digest differs")
    phases: list[_PhaseGeometry] = []
    for phase_index in range(len(PHASE_CUTS) - 1):
        first = PHASE_CUTS[phase_index]
        stop = PHASE_CUTS[phase_index + 1]
        computed_plan_sha256 = phase_plan_digest(
            schedule,
            phase_index=phase_index,
            coverage_mode=EXACT_CANDIDATE_PHASE_COVERAGE,
            loaded_first_t_index=first,
            loaded_t_index_stop_exclusive=stop,
            start_execution_q_index=0,
            stop_execution_q_index=schedule.q_count,
            lane_partition_sha256=partition_sha256,
        )
        if computed_plan_sha256 != PINNED_PHASE_PLAN_SHA256[phase_index]:
            _fail(f"source phase {phase_index} plan digest differs")
        if replay_phase_projections:
            projection = _source_phase_projection(
                schedule,
                phase_index=phase_index,
                phase_plan_sha256=computed_plan_sha256,
            )
            checkpoint_count = sum(
                (
                    record.t_index_count
                    + checkpoint_span
                    - 1
                )
                // checkpoint_span
                for record in projection.active_records
            )
            phase = _PhaseGeometry(
                phase_index=phase_index,
                first_t_index=first,
                t_index_stop_exclusive=stop,
                phase_plan_sha256=computed_plan_sha256,
                phase_schedule_sha256=(
                    projection.phase_schedule_sha256
                ),
                active_q_count=projection.active_modulus_count,
                t_index_row_count=projection.t_index_row_count,
                checkpoint_count=checkpoint_count,
            )
            if (
                phase.phase_schedule_sha256
                != PINNED_PHASE_SCHEDULE_SHA256[phase_index]
                or phase.active_q_count
                != PINNED_PHASE_ACTIVE_Q_COUNTS[phase_index]
                or phase.t_index_row_count
                != PINNED_PHASE_ROW_COUNTS[phase_index]
                or phase.checkpoint_count
                != PINNED_PHASE_CHECKPOINT_COUNTS[phase_index]
            ):
                _fail(
                    f"source phase {phase_index} projection differs from pins"
                )
        else:
            phase = _PhaseGeometry(
                phase_index=phase_index,
                first_t_index=first,
                t_index_stop_exclusive=stop,
                phase_plan_sha256=computed_plan_sha256,
                phase_schedule_sha256=(
                    PINNED_PHASE_SCHEDULE_SHA256[phase_index]
                ),
                active_q_count=(
                    PINNED_PHASE_ACTIVE_Q_COUNTS[phase_index]
                ),
                t_index_row_count=PINNED_PHASE_ROW_COUNTS[phase_index],
                checkpoint_count=(
                    PINNED_PHASE_CHECKPOINT_COUNTS[phase_index]
                ),
            )
        phases.append(phase)
    return partition_sha256, tuple(phases)


def _expected_source_plan(
    schedule: ParsedScheduleManifest,
    *,
    precision: int,
    checkpoint_span: int,
    producer_identity: Mapping[str, Any],
    rebuild_stream_accounting: bool,
) -> dict[str, Any]:
    """Construct the only accepted service plan.

    ``rebuild_stream_accounting`` is true during initialization so a fresh
    ``build_stream_plan`` is authoritative.  Later job invocations use the
    independently pinned phase-plan digests plus the cheap digest
    reconstruction, avoiding repeated component-order accounting.
    """

    precision = _integer(
        precision, "Arb precision", minimum=128, maximum=4096
    )
    if checkpoint_span != DEFAULT_CHECKPOINT_SPAN:
        _fail("source checkpoint span must be the pinned value 4096")
    producer = _validated_producer_identity(
        producer_identity, precision=precision
    )
    planner = planner_identity()
    if schedule.manifest_sha256 != PINNED_SOURCE_MANIFEST_SHA256:
        _fail("source plan schedule digest differs")

    partition_sha256, phase_geometry = _source_geometry(
        schedule,
        checkpoint_span,
        rebuild_stream_accounting,
    )
    if rebuild_stream_accounting:
        for phase in phase_geometry:
            stream_plan = build_stream_plan(
                schedule,
                phase_index=phase.phase_index,
                coverage_mode=EXACT_CANDIDATE_PHASE_COVERAGE,
            )
            if (
                stream_plan.phase_plan_sha256
                != phase.phase_plan_sha256
                or stream_plan.lane_partition_sha256
                != partition_sha256
                or stream_plan.active_q_count
                != phase.active_q_count
                or stream_plan.target_row_reference_count
                != phase.t_index_row_count
            ):
                _fail(
                    f"source phase {phase.phase_index} "
                    "stream plan differs"
                )

    shared_common = {
        "schema": JOB_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "service_algorithm_id": ALGORITHM_ID,
        "artifact_algorithm_id": ARTIFACT_ALGORITHM_ID,
        "classification": (
            "full_source_shaped_factor_artifact_job_not_source_execution"
        ),
        "factor_convention_sha256": FACTOR_CONVENTION_SHA256,
        "producer_identity_sha256": producer[
            "producer_identity_sha256"
        ],
        "planner_identity_sha256": planner[
            "planner_identity_sha256"
        ],
        "precision_bits": precision,
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "execution_order_sha256": schedule.execution_order_sha256,
        "source_run_completed": False,
        "source_range_qualified": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    gamma_job = _job(
        {
            **shared_common,
            "job_kind": "gamma",
            "output_directory": _job_directory_name("gamma"),
            "first_t_index": 0,
            "t_index_stop_exclusive": SOURCE_T_INDEX_STOP,
            "sample_count": SOURCE_T_INDEX_STOP,
            "disk_count": 2 * SOURCE_T_INDEX_STOP,
            "expected_artifact_bytes": (
                GAMMA_HEADER.size
                + 2 * SOURCE_T_INDEX_STOP * DISK.size
            ),
        }
    )
    step_job = _job(
        {
            **shared_common,
            "job_kind": "steps",
            "output_directory": _job_directory_name("steps"),
            "q_start_inclusive": SOURCE_Q_START,
            "q_stop_inclusive": SOURCE_Q_STOP,
            "execution_q_count": schedule.q_count,
            "disk_count": schedule.q_count,
            "expected_artifact_bytes": (
                STEP_HEADER.size + schedule.q_count * DISK.size
            ),
        }
    )

    phase_jobs: list[dict[str, Any]] = []
    for phase in phase_geometry:
        phase_jobs.append(
            _job(
                {
                    **shared_common,
                    "job_kind": "phase-checkpoints",
                    "output_directory": _job_directory_name(
                        "phase-checkpoints", phase.phase_index
                    ),
                    "phase_index": phase.phase_index,
                    "first_t_index": phase.first_t_index,
                    "t_index_stop_exclusive": (
                        phase.t_index_stop_exclusive
                    ),
                    "checkpoint_span": checkpoint_span,
                    "phase_plan_sha256": phase.phase_plan_sha256,
                    "phase_schedule_sha256": phase.phase_schedule_sha256,
                    "lane_partition_sha256": partition_sha256,
                    "active_q_count": phase.active_q_count,
                    "t_index_row_count": phase.t_index_row_count,
                    "checkpoint_count": phase.checkpoint_count,
                    "expected_artifact_bytes": (
                        CHECKPOINT_HEADER.size
                        + phase.active_q_count * CHECKPOINT_RECORD.size
                        + phase.checkpoint_count * DISK.size
                    ),
                    "gamma_job_sha256": gamma_job["job_sha256"],
                    "step_job_sha256": step_job["job_sha256"],
                }
            )
        )

    body: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "artifact_algorithm_id": ARTIFACT_ALGORITHM_ID,
        "classification": (
            "exact_full_source_factor_artifact_plan_not_execution_or_proof"
        ),
        "schedule_filename": SCHEDULE_FILENAME,
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "source_roster_sha256": schedule.source_roster_sha256,
        "execution_order_sha256": schedule.execution_order_sha256,
        "q_start_inclusive": schedule.q_start,
        "q_stop_inclusive": schedule.q_stop,
        "execution_q_count": schedule.q_count,
        "source_t_index_stop_exclusive": SOURCE_T_INDEX_STOP,
        "phase_count": len(phase_jobs),
        "checkpoint_span": checkpoint_span,
        "precision_bits": precision,
        "factor_convention_sha256": FACTOR_CONVENTION_SHA256,
        "producer_identity": producer,
        "planner_identity": planner,
        "gamma_job": gamma_job,
        "step_job": step_job,
        "phase_jobs": phase_jobs,
        "source_artifacts_generated": False,
        "source_run_completed": False,
        "source_range_qualified": False,
        "trusted_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    return _self_hashed(body, "plan_sha256")


def _ensure_service_directory(directory: Path) -> Path:
    candidate = directory.absolute()
    if candidate.is_symlink():
        _fail("completed-factor service directory is symbolic")
    root = candidate.resolve()
    if not root.is_dir():
        _fail("completed-factor service directory is absent")
    for name in (OUTPUT_DIRECTORY, STAGING_DIRECTORY):
        child = root / name
        if child.is_symlink() or not child.is_dir():
            _fail(f"completed-factor service {name} directory differs")
    if {path.name for path in root.iterdir()} != {
        PLAN_FILENAME,
        SCHEDULE_FILENAME,
        OUTPUT_DIRECTORY,
        STAGING_DIRECTORY,
    }:
        _fail("completed-factor service root contains an unknown entry")
    return root


def initialize_source_service(
    directory: Path,
    *,
    schedule_manifest: Path,
    precision: int = 384,
    checkpoint_span: int = DEFAULT_CHECKPOINT_SPAN,
) -> dict[str, Any]:
    """Create an immutable exact-source plan without generating Arb rows."""

    destination = directory.absolute()
    if destination.exists() or destination.is_symlink():
        _fail("source factor service directory must be absent")
    schedule_raw = _read_regular(
        schedule_manifest,
        label="source q-order manifest",
        maximum=MAXIMUM_SCHEDULE_BYTES,
    )
    schedule = _exact_schedule(schedule_raw)
    producer = arb_producer_identity(precision=precision)
    plan = _expected_source_plan(
        schedule,
        precision=precision,
        checkpoint_span=checkpoint_span,
        producer_identity=producer,
        rebuild_stream_accounting=True,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.init.",
            dir=destination.parent,
        )
    )
    try:
        (temporary / OUTPUT_DIRECTORY).mkdir()
        (temporary / STAGING_DIRECTORY).mkdir()
        _atomic_bytes(temporary / SCHEDULE_FILENAME, schedule_raw)
        _atomic_json(temporary / PLAN_FILENAME, plan)
        _fsync_directory(temporary)
        try:
            os.rename(temporary, destination)
        except OSError as error:
            if error.errno in (errno.EEXIST, errno.ENOTEMPTY):
                _fail("source factor service directory appeared concurrently")
            raise
        _fsync_directory(destination.parent)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": plan["classification"],
        "directory": str(destination.resolve()),
        "plan_sha256": plan["plan_sha256"],
        "schedule_manifest_sha256": plan[
            "schedule_manifest_sha256"
        ],
        "execution_order_sha256": plan["execution_order_sha256"],
        "producer_identity_sha256": plan["producer_identity"][
            "producer_identity_sha256"
        ],
        "planner_identity_sha256": plan["planner_identity"][
            "planner_identity_sha256"
        ],
        "job_count": 2 + plan["phase_count"],
        "phase_count": plan["phase_count"],
        "arb_artifact_generation_started": False,
        "source_run_completed": False,
        "source_range_qualified": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


def _load_source_plan(
    directory: Path,
) -> tuple[Path, dict[str, Any], ParsedScheduleManifest]:
    root = _ensure_service_directory(directory)
    schedule_raw = _read_regular(
        root / SCHEDULE_FILENAME,
        label="service q-order manifest",
        maximum=MAXIMUM_SCHEDULE_BYTES,
    )
    schedule = _exact_schedule(schedule_raw)
    observed = _read_canonical_json(
        root / PLAN_FILENAME, label="source factor plan"
    )
    precision = _integer(
        observed.get("precision_bits"),
        "source plan precision",
        minimum=128,
        maximum=4096,
    )
    span = _integer(
        observed.get("checkpoint_span"),
        "source plan checkpoint span",
        minimum=1,
        maximum=SOURCE_T_INDEX_STOP,
    )
    current_producer = arb_producer_identity(precision=precision)
    expected = _expected_source_plan(
        schedule,
        precision=precision,
        checkpoint_span=span,
        producer_identity=current_producer,
        rebuild_stream_accounting=False,
    )
    if observed != expected:
        _fail(
            "source factor plan differs from exact reconstruction or "
            "current pinned producer identity"
        )
    expected_outputs = {
        expected["gamma_job"]["output_directory"],
        expected["step_job"]["output_directory"],
        *(
            job["output_directory"]
            for job in expected["phase_jobs"]
        ),
    }
    observed_outputs = {
        path.name for path in (root / OUTPUT_DIRECTORY).iterdir()
    }
    if not observed_outputs <= expected_outputs:
        _fail("completed-factor outputs contain an unknown job")
    return root, observed, schedule


def _common_receipt_body(
    plan: Mapping[str, Any],
    job: Mapping[str, Any],
    *,
    artifact_sha256: str,
    artifact_size_bytes: int,
) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "service_algorithm_id": ALGORITHM_ID,
        "artifact_algorithm_id": ARTIFACT_ALGORITHM_ID,
        "classification": (
            "completed_factor_artifact_generation_receipt_"
            "not_source_execution_or_proof"
        ),
        "job_kind": job["job_kind"],
        "plan_sha256": plan["plan_sha256"],
        "job_sha256": job["job_sha256"],
        "producer_identity_sha256": job[
            "producer_identity_sha256"
        ],
        "planner_identity_sha256": job[
            "planner_identity_sha256"
        ],
        "schedule_manifest_sha256": job[
            "schedule_manifest_sha256"
        ],
        "execution_order_sha256": job["execution_order_sha256"],
        "artifact_sha256": artifact_sha256,
        "artifact_size_bytes": artifact_size_bytes,
        "artifact_generation_completed": True,
        "source_run_completed": False,
        "source_range_qualified": False,
        "trusted_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


def _gamma_receipt(
    plan: Mapping[str, Any],
    job: Mapping[str, Any],
    artifact: GammaArtifact,
    *,
    artifact_size_bytes: int,
) -> dict[str, Any]:
    if (
        job["job_kind"] != "gamma"
        or artifact.classification != CLASSIFICATION_FULL_SOURCE
        or artifact.first_t_index != job["first_t_index"]
        or artifact.t_index_stop_exclusive
        != job["t_index_stop_exclusive"]
        or artifact.sample_count != job["sample_count"]
        or len(artifact.disks) != job["disk_count"]
        or artifact.producer_identity_sha256
        != job["producer_identity_sha256"]
        or artifact_size_bytes != job["expected_artifact_bytes"]
    ):
        _fail("full-source gamma artifact differs from its exact job")
    return _receipt(
        {
            **_common_receipt_body(
                plan,
                job,
                artifact_sha256=artifact.artifact_sha256,
                artifact_size_bytes=artifact_size_bytes,
            ),
            "first_t_index": artifact.first_t_index,
            "t_index_stop_exclusive": (
                artifact.t_index_stop_exclusive
            ),
            "sample_count": artifact.sample_count,
            "disk_count": len(artifact.disks),
        }
    )


def _step_receipt(
    plan: Mapping[str, Any],
    job: Mapping[str, Any],
    artifact: StepArtifact,
    *,
    artifact_size_bytes: int,
) -> dict[str, Any]:
    if (
        job["job_kind"] != "steps"
        or artifact.classification != CLASSIFICATION_FULL_SOURCE
        or artifact.q_start != job["q_start_inclusive"]
        or artifact.q_stop != job["q_stop_inclusive"]
        or len(artifact.disks) != job["execution_q_count"]
        or artifact.schedule_manifest_sha256
        != job["schedule_manifest_sha256"]
        or artifact.execution_order_sha256
        != job["execution_order_sha256"]
        or artifact_size_bytes != job["expected_artifact_bytes"]
    ):
        _fail("full-source step artifact differs from its exact job")
    return _receipt(
        {
            **_common_receipt_body(
                plan,
                job,
                artifact_sha256=artifact.artifact_sha256,
                artifact_size_bytes=artifact_size_bytes,
            ),
            "q_start_inclusive": artifact.q_start,
            "q_stop_inclusive": artifact.q_stop,
            "execution_q_count": len(artifact.disks),
            "disk_count": len(artifact.disks),
        }
    )


def _phase_receipt(
    plan: Mapping[str, Any],
    job: Mapping[str, Any],
    artifact: CheckpointArtifact,
    *,
    artifact_size_bytes: int,
    gamma_receipt: Mapping[str, Any],
    step_receipt: Mapping[str, Any],
    expected_q_samples: tuple[tuple[int, int], ...],
) -> dict[str, Any]:
    observed_q_samples = tuple(
        (record.q, record.sample_count) for record in artifact.records
    )
    checkpoint_count = sum(
        len(record.checkpoints) for record in artifact.records
    )
    if (
        job["job_kind"] != "phase-checkpoints"
        or artifact.classification != CLASSIFICATION_FULL_SOURCE
        or artifact.phase_index != job["phase_index"]
        or artifact.first_t_index != job["first_t_index"]
        or artifact.t_index_stop_exclusive
        != job["t_index_stop_exclusive"]
        or artifact.checkpoint_span != job["checkpoint_span"]
        or artifact.schedule_manifest_sha256
        != job["schedule_manifest_sha256"]
        or artifact.phase_schedule_sha256
        != job["phase_schedule_sha256"]
        or artifact.gamma_artifact_sha256
        != gamma_receipt["artifact_sha256"]
        or artifact.step_artifact_sha256
        != step_receipt["artifact_sha256"]
        or observed_q_samples != expected_q_samples
        or len(artifact.records) != job["active_q_count"]
        or sum(samples for _q, samples in observed_q_samples)
        != job["t_index_row_count"]
        or checkpoint_count != job["checkpoint_count"]
        or artifact_size_bytes != job["expected_artifact_bytes"]
    ):
        _fail(
            f"source phase {job['phase_index']} checkpoint artifact differs"
        )
    return _receipt(
        {
            **_common_receipt_body(
                plan,
                job,
                artifact_sha256=artifact.artifact_sha256,
                artifact_size_bytes=artifact_size_bytes,
            ),
            "phase_index": artifact.phase_index,
            "first_t_index": artifact.first_t_index,
            "t_index_stop_exclusive": (
                artifact.t_index_stop_exclusive
            ),
            "checkpoint_span": artifact.checkpoint_span,
            "phase_plan_sha256": job["phase_plan_sha256"],
            "phase_schedule_sha256": (
                artifact.phase_schedule_sha256
            ),
            "gamma_artifact_sha256": (
                artifact.gamma_artifact_sha256
            ),
            "step_artifact_sha256": artifact.step_artifact_sha256,
            "gamma_receipt_sha256": gamma_receipt["receipt_sha256"],
            "step_receipt_sha256": step_receipt["receipt_sha256"],
            "active_q_count": len(artifact.records),
            "t_index_row_count": sum(
                samples for _q, samples in observed_q_samples
            ),
            "checkpoint_count": checkpoint_count,
        }
    )


def _artifact_path(job_directory: Path) -> Path:
    return job_directory / ARTIFACT_FILENAME


def _validate_job_directory(job_directory: Path) -> None:
    if job_directory.is_symlink() or not job_directory.is_dir():
        _fail("completed-factor job output is not a real directory")
    for name in (ARTIFACT_FILENAME, RECEIPT_FILENAME):
        path = job_directory / name
        if path.is_symlink() or not path.is_file():
            _fail(f"completed-factor job {name} is absent or symbolic")
    if {path.name for path in job_directory.iterdir()} != {
        ARTIFACT_FILENAME,
        RECEIPT_FILENAME,
    }:
        _fail("completed-factor job contains an unknown entry")


def _stored_receipt(job_directory: Path) -> dict[str, Any]:
    return _read_canonical_json(
        job_directory / RECEIPT_FILENAME,
        label="completed-factor job receipt",
    )


def _verify_gamma_directory(
    job_directory: Path,
    plan: Mapping[str, Any],
) -> tuple[dict[str, Any], GammaArtifact]:
    _validate_job_directory(job_directory)
    job = plan["gamma_job"]
    path = _artifact_path(job_directory)
    observed_receipt = _stored_receipt(job_directory)
    expected_sha = _digest(
        observed_receipt.get("artifact_sha256"),
        "gamma receipt artifact",
    )
    artifact = parse_gamma_artifact(path, expected_sha256=expected_sha)
    expected_receipt = _gamma_receipt(
        plan,
        job,
        artifact,
        artifact_size_bytes=path.stat().st_size,
    )
    if observed_receipt != expected_receipt:
        _fail("gamma receipt differs from exact reconstruction")
    return observed_receipt, artifact


def _verify_step_directory(
    job_directory: Path,
    plan: Mapping[str, Any],
) -> tuple[dict[str, Any], StepArtifact]:
    _validate_job_directory(job_directory)
    job = plan["step_job"]
    path = _artifact_path(job_directory)
    observed_receipt = _stored_receipt(job_directory)
    expected_sha = _digest(
        observed_receipt.get("artifact_sha256"),
        "step receipt artifact",
    )
    artifact = parse_step_artifact(path, expected_sha256=expected_sha)
    expected_receipt = _step_receipt(
        plan,
        job,
        artifact,
        artifact_size_bytes=path.stat().st_size,
    )
    if observed_receipt != expected_receipt:
        _fail("step receipt differs from exact reconstruction")
    return observed_receipt, artifact


def _expected_q_samples(
    schedule: ParsedScheduleManifest,
    job: Mapping[str, Any],
) -> tuple[tuple[int, int], ...]:
    projection = _source_phase_projection(
        schedule,
        phase_index=job["phase_index"],
        phase_plan_sha256=job["phase_plan_sha256"],
    )
    if projection.phase_schedule_sha256 != job["phase_schedule_sha256"]:
        _fail("phase schedule differs while reconstructing q samples")
    return tuple(
        (record.q, record.t_index_count)
        for record in projection.active_records
    )


def _verify_phase_directory(
    job_directory: Path,
    plan: Mapping[str, Any],
    schedule: ParsedScheduleManifest,
    *,
    phase_index: int,
    gamma_receipt: Mapping[str, Any],
    step_receipt: Mapping[str, Any],
) -> tuple[dict[str, Any], CheckpointArtifact]:
    _validate_job_directory(job_directory)
    job = plan["phase_jobs"][phase_index]
    path = _artifact_path(job_directory)
    observed_receipt = _stored_receipt(job_directory)
    expected_sha = _digest(
        observed_receipt.get("artifact_sha256"),
        "checkpoint receipt artifact",
    )
    artifact = parse_checkpoint_artifact(
        path, expected_sha256=expected_sha
    )
    expected_receipt = _phase_receipt(
        plan,
        job,
        artifact,
        artifact_size_bytes=path.stat().st_size,
        gamma_receipt=gamma_receipt,
        step_receipt=step_receipt,
        expected_q_samples=_expected_q_samples(schedule, job),
    )
    if observed_receipt != expected_receipt:
        _fail(
            f"source phase {phase_index} receipt differs from reconstruction"
        )
    return observed_receipt, artifact


def _publish_job(
    root: Path,
    *,
    final_name: str,
    write_staging: Callable[[Path], dict[str, Any]],
    verify_final: Callable[[Path], dict[str, Any]],
    validate_dependencies: Callable[[], None] | None = None,
) -> dict[str, Any]:
    final = root / OUTPUT_DIRECTORY / final_name
    if final.exists() or final.is_symlink():
        receipt = verify_final(final)
        return {"status": "already-complete", "receipt": receipt}
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{final_name}.",
            dir=root / STAGING_DIRECTORY,
        )
    )
    try:
        receipt = write_staging(staging)
        _fsync_regular(_artifact_path(staging))
        _atomic_json(staging / RECEIPT_FILENAME, receipt)
        if validate_dependencies is not None:
            validate_dependencies()
        _fsync_directory(staging)
        try:
            os.rename(staging, final)
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            winner = verify_final(final)
            shutil.rmtree(staging)
            return {"status": "already-complete", "receipt": winner}
        _fsync_directory(final.parent)
        verified = verify_final(final)
        return {"status": "generated", "receipt": verified}
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def generate_gamma_job(directory: Path) -> dict[str, Any]:
    """Generate or idempotently validate the one shared gamma artifact."""

    root, plan, _schedule = _load_source_plan(directory)
    job = plan["gamma_job"]

    def write(staging: Path) -> dict[str, Any]:
        path = _artifact_path(staging)
        report = write_arb_gamma_artifact(
            path,
            first_t_index=job["first_t_index"],
            t_index_stop_exclusive=job["t_index_stop_exclusive"],
            precision=job["precision_bits"],
            classification=CLASSIFICATION_FULL_SOURCE,
        )
        if (
            report["producer_identity_sha256"]
            != job["producer_identity_sha256"]
        ):
            _fail("gamma generator producer identity differs")
        artifact = parse_gamma_artifact(
            path, expected_sha256=report["artifact_sha256"]
        )
        return _gamma_receipt(
            plan,
            job,
            artifact,
            artifact_size_bytes=path.stat().st_size,
        )

    def verify(path: Path) -> dict[str, Any]:
        return _verify_gamma_directory(path, plan)[0]

    return _publish_job(
        root,
        final_name=job["output_directory"],
        write_staging=write,
        verify_final=verify,
    )


def generate_step_job(directory: Path) -> dict[str, Any]:
    """Generate or idempotently validate the one execution-order step catalog."""

    root, plan, schedule = _load_source_plan(directory)
    job = plan["step_job"]
    execution_qs = tuple(record.q for record in schedule.execution_records)

    def write(staging: Path) -> dict[str, Any]:
        path = _artifact_path(staging)
        report = write_arb_step_artifact(
            path,
            execution_qs=execution_qs,
            q_start=job["q_start_inclusive"],
            q_stop=job["q_stop_inclusive"],
            schedule_manifest_sha256=job[
                "schedule_manifest_sha256"
            ],
            execution_order_sha256=job["execution_order_sha256"],
            precision=job["precision_bits"],
            classification=CLASSIFICATION_FULL_SOURCE,
        )
        if (
            report["producer_identity_sha256"]
            != job["producer_identity_sha256"]
        ):
            _fail("step generator producer identity differs")
        artifact = parse_step_artifact(
            path, expected_sha256=report["artifact_sha256"]
        )
        return _step_receipt(
            plan,
            job,
            artifact,
            artifact_size_bytes=path.stat().st_size,
        )

    def verify(path: Path) -> dict[str, Any]:
        return _verify_step_directory(path, plan)[0]

    return _publish_job(
        root,
        final_name=job["output_directory"],
        write_staging=write,
        verify_final=verify,
    )


def generate_phase_job(
    directory: Path, *, phase_index: int
) -> dict[str, Any]:
    """Generate one independent resident-phase checkpoint artifact."""

    index = _integer(
        phase_index,
        "phase index",
        minimum=0,
        maximum=len(PHASE_CUTS) - 2,
    )
    root, plan, schedule = _load_source_plan(directory)
    gamma_directory = (
        root / OUTPUT_DIRECTORY / plan["gamma_job"]["output_directory"]
    )
    step_directory = (
        root / OUTPUT_DIRECTORY / plan["step_job"]["output_directory"]
    )
    if not gamma_directory.is_dir() or not step_directory.is_dir():
        _fail("phase generation requires completed gamma and step jobs")
    gamma_receipt, _gamma = _verify_gamma_directory(
        gamma_directory, plan
    )
    step_receipt, _steps = _verify_step_directory(step_directory, plan)
    job = plan["phase_jobs"][index]
    q_sample_counts = _expected_q_samples(schedule, job)

    def validate_shared_dependencies() -> None:
        current_gamma, _gamma_artifact = _verify_gamma_directory(
            gamma_directory, plan
        )
        current_steps, _step_artifact = _verify_step_directory(
            step_directory, plan
        )
        if (
            current_gamma != gamma_receipt
            or current_steps != step_receipt
        ):
            _fail("shared factor artifacts changed during phase generation")

    def write(staging: Path) -> dict[str, Any]:
        path = _artifact_path(staging)
        report = write_arb_checkpoint_artifact(
            path,
            phase_index=index,
            first_t_index=job["first_t_index"],
            t_index_stop_exclusive=job["t_index_stop_exclusive"],
            checkpoint_span=job["checkpoint_span"],
            q_sample_counts=q_sample_counts,
            schedule_manifest_sha256=job[
                "schedule_manifest_sha256"
            ],
            phase_schedule_sha256=job["phase_schedule_sha256"],
            gamma_artifact_sha256=gamma_receipt["artifact_sha256"],
            step_artifact_sha256=step_receipt["artifact_sha256"],
            precision=job["precision_bits"],
            classification=CLASSIFICATION_FULL_SOURCE,
        )
        if (
            report["producer_identity_sha256"]
            != job["producer_identity_sha256"]
        ):
            _fail("checkpoint generator producer identity differs")
        artifact = parse_checkpoint_artifact(
            path, expected_sha256=report["artifact_sha256"]
        )
        return _phase_receipt(
            plan,
            job,
            artifact,
            artifact_size_bytes=path.stat().st_size,
            gamma_receipt=gamma_receipt,
            step_receipt=step_receipt,
            expected_q_samples=q_sample_counts,
        )

    def verify(path: Path) -> dict[str, Any]:
        validate_shared_dependencies()
        return _verify_phase_directory(
            path,
            plan,
            schedule,
            phase_index=index,
            gamma_receipt=gamma_receipt,
            step_receipt=step_receipt,
        )[0]

    return _publish_job(
        root,
        final_name=job["output_directory"],
        write_staging=write,
        verify_final=verify,
        validate_dependencies=validate_shared_dependencies,
    )


def service_status(
    directory: Path, *, require_complete: bool = False
) -> dict[str, Any]:
    """Verify every visible immutable job and report pending jobs."""

    if not isinstance(require_complete, bool):
        _fail("require-complete flag is malformed")
    root, plan, schedule = _load_source_plan(directory)
    outputs = root / OUTPUT_DIRECTORY
    gamma_path = outputs / plan["gamma_job"]["output_directory"]
    step_path = outputs / plan["step_job"]["output_directory"]
    jobs: list[dict[str, Any]] = []

    gamma_receipt: dict[str, Any] | None = None
    step_receipt: dict[str, Any] | None = None
    if gamma_path.exists() or gamma_path.is_symlink():
        gamma_receipt, _gamma = _verify_gamma_directory(gamma_path, plan)
        jobs.append(
            {
                "job_kind": "gamma",
                "status": "complete",
                "job_sha256": plan["gamma_job"]["job_sha256"],
                "receipt_sha256": gamma_receipt["receipt_sha256"],
                "artifact_sha256": gamma_receipt["artifact_sha256"],
            }
        )
    else:
        jobs.append(
            {
                "job_kind": "gamma",
                "status": "pending",
                "job_sha256": plan["gamma_job"]["job_sha256"],
            }
        )
    if step_path.exists() or step_path.is_symlink():
        step_receipt, _steps = _verify_step_directory(step_path, plan)
        jobs.append(
            {
                "job_kind": "steps",
                "status": "complete",
                "job_sha256": plan["step_job"]["job_sha256"],
                "receipt_sha256": step_receipt["receipt_sha256"],
                "artifact_sha256": step_receipt["artifact_sha256"],
            }
        )
    else:
        jobs.append(
            {
                "job_kind": "steps",
                "status": "pending",
                "job_sha256": plan["step_job"]["job_sha256"],
            }
        )

    for index, job in enumerate(plan["phase_jobs"]):
        path = outputs / job["output_directory"]
        if path.exists() or path.is_symlink():
            if gamma_receipt is None or step_receipt is None:
                _fail(
                    "published phase exists before both shared jobs"
                )
            receipt, _artifact = _verify_phase_directory(
                path,
                plan,
                schedule,
                phase_index=index,
                gamma_receipt=gamma_receipt,
                step_receipt=step_receipt,
            )
            jobs.append(
                {
                    "job_kind": "phase-checkpoints",
                    "phase_index": index,
                    "status": "complete",
                    "job_sha256": job["job_sha256"],
                    "receipt_sha256": receipt["receipt_sha256"],
                    "artifact_sha256": receipt["artifact_sha256"],
                }
            )
        else:
            jobs.append(
                {
                    "job_kind": "phase-checkpoints",
                    "phase_index": index,
                    "status": "pending",
                    "job_sha256": job["job_sha256"],
                }
            )
    complete = sum(job["status"] == "complete" for job in jobs)
    pending = len(jobs) - complete
    if require_complete and pending:
        _fail(f"source factor service still has {pending} pending jobs")
    staging_entries = sum(
        1 for _path in (root / STAGING_DIRECTORY).iterdir()
    )
    return {
        "schema": STATUS_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "factor_artifact_service_status_not_source_execution_or_proof"
        ),
        "directory": str(root),
        "plan_sha256": plan["plan_sha256"],
        "schedule_manifest_sha256": plan[
            "schedule_manifest_sha256"
        ],
        "execution_order_sha256": plan["execution_order_sha256"],
        "producer_identity_sha256": plan["producer_identity"][
            "producer_identity_sha256"
        ],
        "planner_identity_sha256": plan["planner_identity"][
            "planner_identity_sha256"
        ],
        "job_count": len(jobs),
        "complete_job_count": complete,
        "pending_job_count": pending,
        "staging_entry_count": staging_entries,
        "jobs": jobs,
        "all_factor_artifacts_generated": pending == 0,
        "source_run_completed": False,
        "source_range_qualified": False,
        "trusted_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "DirichletCompletedFactorServiceError",
    "JOB_SCHEMA",
    "PINNED_PHASE_PLAN_SHA256",
    "PINNED_PHASE_SCHEDULE_SHA256",
    "PINNED_SOURCE_MANIFEST_SHA256",
    "PLANNER_IDENTITY_SCHEMA",
    "PLAN_SCHEMA",
    "RECEIPT_SCHEMA",
    "STATUS_SCHEMA",
    "generate_gamma_job",
    "generate_phase_job",
    "generate_step_job",
    "initialize_source_service",
    "planner_identity",
    "service_status",
]
