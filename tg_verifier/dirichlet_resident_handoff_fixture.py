# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic fixture for the resident allchars/completed-L CUDA seam.

This is a bounded synthetic arithmetic known-answer test, not a source
certificate.  It exists as a small, reusable entry point for ordinary runs
and Compute Sanitizer.  The delta input makes every primitive transform
frequency follow the same eight-sample sign pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from typing import Sequence

from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    canonical_component_orders,
)
from tg_verifier.dirichlet_completed_factor_artifacts import (
    parse_checkpoint_artifact,
    parse_gamma_artifact,
    parse_step_artifact,
    write_synthetic_unit_artifacts,
)


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "tg-dirichlet-resident-completed-sign-handoff-fixture-v1"
Q = 7
PATTERN = (-2.0, 0.0, 2.0, 2.0, 0.0, -2.0, -2.0, 2.0)
ROOT_HEADER = struct.Struct("<8sIIIIQ32s32s")
ROOT_RECORD = struct.Struct("<dddd")
FACTOR_HEADER = struct.Struct("<8sIIIIQQQQ")
DISK = struct.Struct("<ddd")
COMPACT_STATE_HEADER = struct.Struct("<8sIIIIQQQQQQQIIIIIIQQQ")
DENSE_PAGE_TOTALS = struct.Struct("<QQQQQQIIII")
TAGGED_AMBIGUITY_RANGE = struct.Struct("<QQQ")


class ResidentHandoffFixtureError(RuntimeError):
    """The bounded resident-handoff fixture or its output differed."""


@dataclass(frozen=True)
class ResidentHandoffFixture:
    directory: Path
    input_path: Path
    root_path: Path
    factor_path: Path
    gamma_path: Path
    step_path: Path
    checkpoint_path: Path
    state_path: Path
    summary_path: Path
    manifest_path: Path
    root_sha256: str
    factor_sha256: str
    gamma_sha256: str
    step_sha256: str
    checkpoint_sha256: str


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_if_different(path: Path, raw: bytes) -> None:
    if path.exists() and path.read_bytes() == raw:
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)


def _fixture_bytes() -> tuple[bytes, bytes, bytes]:
    orders = canonical_component_orders(Q)
    group_order = math.prod(orders)
    input_header = INPUT_HEADER.pack(
        b"TGDAFFI1",
        1,
        Q,
        len(orders),
        len(PATTERN),
        group_order,
        0,
        64,
        5,
        group_order * len(PATTERN),
        0,
    )
    input_values = bytearray()
    for value in PATTERN:
        input_values.extend(COMPLEX_INTERVAL.pack(value, value, 0.0, 0.0))
        for _position in range(1, group_order):
            input_values.extend(
                COMPLEX_INTERVAL.pack(0.0, 0.0, 0.0, 0.0)
            )
    primitive_count = Q - 2
    root_raw = ROOT_HEADER.pack(
        b"TGDRNRO1",
        1,
        Q,
        len(orders),
        ROOT_RECORD.size,
        primitive_count,
        bytes.fromhex("11" * 32),
        bytes.fromhex("22" * 32),
    ) + ROOT_RECORD.pack(1.0, 1.0, 0.0, 0.0) * primitive_count
    factor_raw = FACTOR_HEADER.pack(
        b"TGDCFCT1",
        1,
        Q,
        len(PATTERN),
        0,
        0,
        64,
        5,
        2 * len(PATTERN),
    ) + DISK.pack(1.0, 0.0, 0.0) * (2 * len(PATTERN))
    return input_header + bytes(input_values), root_raw, factor_raw


def prepare_fixture(directory: Path) -> ResidentHandoffFixture:
    """Create or verify the deterministic read-only fixture inputs."""

    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    input_raw, root_raw, factor_raw = _fixture_bytes()
    input_path = directory / "input.bin"
    root_path = directory / "roots.bin"
    factor_path = directory / "factors.bin"
    recurrence_directory = directory / "completed-factor-recurrence"
    gamma_path = recurrence_directory / "gamma.bin"
    step_path = recurrence_directory / "steps.bin"
    checkpoint_path = recurrence_directory / "checkpoints.bin"
    state_path = directory / "state.bin"
    summary_path = directory / "summary.json"
    manifest_path = directory / "fixture.json"
    root_sha256 = _sha256(root_raw)
    factor_sha256 = _sha256(factor_raw)
    _write_if_different(input_path, input_raw)
    _write_if_different(root_path, root_raw)
    _write_if_different(factor_path, factor_raw)
    recurrence_paths = (gamma_path, step_path, checkpoint_path)
    existing_recurrence_paths = tuple(
        path.exists() for path in recurrence_paths
    )
    if any(existing_recurrence_paths) and not all(existing_recurrence_paths):
        raise ResidentHandoffFixtureError(
            "completed-factor recurrence fixture is only partially present"
        )
    if not all(existing_recurrence_paths):
        recurrence = write_synthetic_unit_artifacts(
            recurrence_directory,
            q=Q,
            first_t_index=0,
            sample_count=len(PATTERN),
        )
        gamma_sha256 = recurrence["gamma_sha256"]
        step_sha256 = recurrence["step_sha256"]
        checkpoint_sha256 = recurrence["checkpoint_sha256"]
    else:
        gamma_sha256 = _sha256(gamma_path.read_bytes())
        step_sha256 = _sha256(step_path.read_bytes())
        checkpoint_sha256 = _sha256(checkpoint_path.read_bytes())
    gamma = parse_gamma_artifact(
        gamma_path, expected_sha256=gamma_sha256
    )
    step = parse_step_artifact(
        step_path, expected_sha256=step_sha256
    )
    checkpoints = parse_checkpoint_artifact(
        checkpoint_path, expected_sha256=checkpoint_sha256
    )
    if (
        gamma.first_t_index != 0
        or gamma.t_index_stop_exclusive != len(PATTERN)
        or len(gamma.disks) != 2 * len(PATTERN)
        or step.q_start != Q
        or step.q_stop != Q
        or len(step.disks) != 1
        or checkpoints.first_t_index != 0
        or checkpoints.t_index_stop_exclusive != len(PATTERN)
        or len(checkpoints.records) != 1
        or checkpoints.records[0].q != Q
        or checkpoints.records[0].sample_count != len(PATTERN)
        or checkpoints.gamma_artifact_sha256 != gamma_sha256
        or checkpoints.step_artifact_sha256 != step_sha256
        or checkpoints.schedule_manifest_sha256
        != step.schedule_manifest_sha256
    ):
        raise ResidentHandoffFixtureError(
            "completed-factor recurrence fixture identity changed"
        )
    manifest = {
        "algorithm": ALGORITHM_ID,
        "classification": "bounded_synthetic_kat_not_source_evidence",
        "q": Q,
        "sample_count": len(PATTERN),
        "input": input_path.name,
        "input_sha256": _sha256(input_raw),
        "roots": root_path.name,
        "root_sha256": root_sha256,
        "factors": factor_path.name,
        "factor_sha256": factor_sha256,
        "gamma": str(gamma_path.relative_to(directory)),
        "gamma_sha256": gamma_sha256,
        "steps": str(step_path.relative_to(directory)),
        "step_sha256": step_sha256,
        "checkpoints": str(checkpoint_path.relative_to(directory)),
        "checkpoint_sha256": checkpoint_sha256,
        "expected_state": state_path.name,
        "expected_summary": summary_path.name,
        "source_qualified": False,
        "external_atom_discharged": False,
    }
    _write_if_different(
        manifest_path,
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
        .encode("ascii"),
    )
    return ResidentHandoffFixture(
        directory=directory,
        input_path=input_path,
        root_path=root_path,
        factor_path=factor_path,
        gamma_path=gamma_path,
        step_path=step_path,
        checkpoint_path=checkpoint_path,
        state_path=state_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        root_sha256=root_sha256,
        factor_sha256=factor_sha256,
        gamma_sha256=gamma_sha256,
        step_sha256=step_sha256,
        checkpoint_sha256=checkpoint_sha256,
    )


def runner_argv(
    fixture: ResidentHandoffFixture,
    runner: Path,
    device: int,
) -> tuple[str, ...]:
    if device < 0:
        raise ResidentHandoffFixtureError("CUDA device must be nonnegative")
    return (
        str(runner.resolve()),
        "--bounded-resident-completed-sign-recurrence-handoff",
        str(fixture.input_path),
        str(fixture.root_path),
        fixture.root_sha256,
        str(fixture.gamma_path),
        fixture.gamma_sha256,
        str(fixture.step_path),
        fixture.step_sha256,
        str(fixture.checkpoint_path),
        fixture.checkpoint_sha256,
        str(fixture.state_path),
        str(fixture.summary_path),
        str(device),
    )


def validate_fixture_output(fixture: ResidentHandoffFixture) -> None:
    """Check the exact dense state and maximal ambiguity ranges."""

    summary = json.loads(fixture.summary_path.read_text("ascii"))
    if (
        summary["TGDAFFO1_device_to_host_bytes"] != 0
        or summary["raw_transform_stream_materialized"]
        or not summary["same_cuda_address_space_reduction"]
        or not summary["device_cub_range_scan"]
        or not summary["device_adjacent_state_merge"]
        or not summary["device_tgdcsb03_dense_pack"]
        or summary["bounded_host_range_count_copy"]
        or summary["phase_state_device_to_host_bytes"] != 0
        or summary["per_frame_count_device_to_host_bytes"] != 0
        or summary["compact_checkpoint_device_to_host_bytes"] != 3928
        or summary["dense_staging_device_to_host_bytes"] != 3584
        or summary["canonical_dense_bytes"] != 5
        or summary["dense_device_to_host_copy_count"] != 1
        or summary["raw_sparse_range_count"] != 10
        or summary["coalesced_sparse_range_count"] != 10
        or not summary["factor_checkpoint_recurrence_path"]
        or summary["conductor_step_t_numerator"] != 5
        or summary["conductor_step_t_denominator"] != 128
        or summary["conductor_step_applications_per_sample"] != 1
        or summary["factor_summary_source_status_or"] != 0
        or summary["factor_summary_reducer_error_or"] != 0
        or summary["gamma_artifact_sha256"] != fixture.gamma_sha256
        or summary["step_artifact_sha256"] != fixture.step_sha256
        or summary["checkpoint_artifact_sha256"]
        != fixture.checkpoint_sha256
        or summary["source_packed_state_path"]
        or summary["source_factor_recurrence_path"]
        or summary["source_performance_ready"]
        or summary["external_atom_discharged"]
    ):
        raise ResidentHandoffFixtureError(
            "resident handoff materialization or trust boundary changed"
        )

    state_raw = fixture.state_path.read_bytes()
    if len(state_raw) < COMPACT_STATE_HEADER.size:
        raise ResidentHandoffFixtureError("resident state header is truncated")
    (
        magic,
        version,
        state_q,
        characters,
        pages,
        samples,
        first,
        stop,
        step,
        raw_range_count,
        coalesced_range_count,
        device_to_host_bytes,
        reduction_source_status,
        reduction_error,
        pack_source_status,
        pack_error,
        page_totals_size,
        tagged_range_size,
        phase_state_device_to_host_bytes,
        per_frame_count_device_to_host_bytes,
        payload_bytes,
    ) = COMPACT_STATE_HEADER.unpack_from(state_raw)
    primitive_count = Q - 2
    if (
        magic != b"TGDCPCK1"
        or version != 1
        or state_q != Q
        or characters != primitive_count
        or pages != 1
        or samples != len(PATTERN)
        or (first, stop, step) != (0, 40, 5)
        or raw_range_count != 2 * primitive_count
        or coalesced_range_count != 2 * primitive_count
        or device_to_host_bytes != 3928
        or reduction_source_status != 0
        or reduction_error != 0
        or pack_source_status != 0
        or pack_error != 0
        or page_totals_size != DENSE_PAGE_TOTALS.size
        or tagged_range_size != TAGGED_AMBIGUITY_RANGE.size
        or phase_state_device_to_host_bytes != 0
        or per_frame_count_device_to_host_bytes != 0
        or payload_bytes != 309
        or len(state_raw)
        != COMPACT_STATE_HEADER.size + payload_bytes
    ):
        raise ResidentHandoffFixtureError(
            "resident completed-sign handoff state header differs"
        )
    position = COMPACT_STATE_HEADER.size
    page_totals = DENSE_PAGE_TOTALS.unpack_from(state_raw, position)
    position += DENSE_PAGE_TOTALS.size
    if page_totals != (
        0,
        primitive_count,
        5,
        15,
        10,
        10,
        primitive_count,
        3,
        7,
        0,
    ):
        raise ResidentHandoffFixtureError(
            "resident completed-sign dense page totals differ"
        )
    dense = state_raw[position : position + 5]
    position += 5
    if dense != bytes.fromhex("bd5eafd703"):
        raise ResidentHandoffFixtureError(
            "resident completed-sign dense page differs"
        )
    observed_ranges = tuple(
        TAGGED_AMBIGUITY_RANGE.unpack_from(
            state_raw, position + index * TAGGED_AMBIGUITY_RANGE.size
        )
        for index in range(coalesced_range_count)
    )
    expected_tagged_ranges = tuple(
        (ordinal, first_numerator, stop_numerator)
        for ordinal in range(primitive_count)
        for first_numerator, stop_numerator in ((5, 10), (20, 25))
    )
    if observed_ranges != expected_tagged_ranges:
        raise ResidentHandoffFixtureError(
            "resident completed-sign ambiguity ranges differ"
        )


def run_fixture(
    fixture: ResidentHandoffFixture,
    runner: Path,
    device: int,
    *,
    compute_sanitizer: Path | None = None,
    sanitizer_tool: str | None = None,
    extra_sanitizer_arguments: Sequence[str] = (),
) -> None:
    """Run the fixture directly, optionally under one sanitizer tool."""

    runner = runner.resolve()
    if not runner.is_file():
        raise ResidentHandoffFixtureError(f"runner does not exist: {runner}")
    for path in (fixture.state_path, fixture.summary_path):
        path.unlink(missing_ok=True)
    command = list(runner_argv(fixture, runner, device))
    if sanitizer_tool is not None:
        if sanitizer_tool not in {"memcheck", "initcheck", "racecheck", "synccheck"}:
            raise ResidentHandoffFixtureError(
                f"unsupported Compute Sanitizer tool: {sanitizer_tool}"
            )
        if compute_sanitizer is None:
            discovered = shutil.which("compute-sanitizer")
            if discovered is None:
                raise ResidentHandoffFixtureError(
                    "compute-sanitizer was not found"
                )
            compute_sanitizer = Path(discovered)
        sanitizer_log = fixture.directory / f"{sanitizer_tool}.log"
        sanitizer_log.unlink(missing_ok=True)
        command = [
            str(compute_sanitizer.resolve()),
            "--tool",
            sanitizer_tool,
            "--error-exitcode",
            "99",
            "--check-exit-code",
            "yes",
            "--log-file",
            str(sanitizer_log),
            *extra_sanitizer_arguments,
            *command,
        ]
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
    )
    if completed.stdout:
        raise ResidentHandoffFixtureError(
            "resident completed-sign handoff emitted a raw stream"
        )
    validate_fixture_output(fixture)
    if sanitizer_tool is None:
        _verify_artifact_mutation_rejection(fixture, runner, device)


def _verify_artifact_mutation_rejection(
    fixture: ResidentHandoffFixture,
    runner: Path,
    device: int,
) -> None:
    """Ensure recomputed outer hashes cannot bypass inner identity bindings."""

    attacks = (
        "gamma-convention",
        "step-convention",
        "checkpoint-gamma-binding",
        "gamma-producer-repaired-chain",
        "step-execution-order-repaired-chain",
        "joint-schedule-repaired-chain",
        "checkpoint-phase-index",
        "checkpoint-phase-schedule",
    )
    for label in attacks:
        with tempfile.TemporaryDirectory(
            prefix=f"{label}-", dir=fixture.directory
        ) as temporary:
            attack_directory = Path(temporary)
            gamma_path = attack_directory / "gamma.bin"
            step_path = attack_directory / "steps.bin"
            checkpoint_path = attack_directory / "checkpoints.bin"
            shutil.copyfile(fixture.gamma_path, gamma_path)
            shutil.copyfile(fixture.step_path, step_path)
            shutil.copyfile(fixture.checkpoint_path, checkpoint_path)
            gamma = bytearray(gamma_path.read_bytes())
            step = bytearray(step_path.read_bytes())
            checkpoint = bytearray(checkpoint_path.read_bytes())
            if label == "gamma-convention":
                gamma[64] ^= 1
            elif label == "step-convention":
                step[112] ^= 1
            elif label == "checkpoint-gamma-binding":
                checkpoint[144] ^= 1
            elif label == "gamma-producer-repaired-chain":
                gamma[96] ^= 1
                checkpoint[144:176] = bytes.fromhex(_sha256(gamma))
            elif label == "step-execution-order-repaired-chain":
                step[80] ^= 1
                checkpoint[176:208] = bytes.fromhex(_sha256(step))
            elif label == "joint-schedule-repaired-chain":
                substituted_schedule = bytearray(step[48:80])
                substituted_schedule[0] ^= 1
                step[48:80] = substituted_schedule
                checkpoint[80:112] = substituted_schedule
                checkpoint[176:208] = bytes.fromhex(_sha256(step))
            elif label == "checkpoint-phase-index":
                checkpoint[24] ^= 1
            elif label == "checkpoint-phase-schedule":
                checkpoint[112] ^= 1
            else:  # pragma: no cover - fixed attack roster
                raise AssertionError(label)
            gamma_path.write_bytes(gamma)
            step_path.write_bytes(step)
            checkpoint_path.write_bytes(checkpoint)
            gamma_sha256 = _sha256(gamma_path.read_bytes())
            step_sha256 = _sha256(step_path.read_bytes())
            checkpoint_sha256 = _sha256(checkpoint_path.read_bytes())
            command = (
                str(runner),
                "--bounded-resident-completed-sign-recurrence-handoff",
                str(fixture.input_path),
                str(fixture.root_path),
                fixture.root_sha256,
                str(gamma_path),
                gamma_sha256,
                str(step_path),
                step_sha256,
                str(checkpoint_path),
                checkpoint_sha256,
                str(attack_directory / "state.bin"),
                str(attack_directory / "summary.json"),
                str(device),
            )
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if completed.returncode == 0:
                raise ResidentHandoffFixtureError(
                    f"{label} artifact mutation was accepted"
                )
