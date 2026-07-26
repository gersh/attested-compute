# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import unittest

from tests.test_tg_dirichlet_resident_qmajor_phase import (
    EXPECTED_OUTPUT_SHA256,
    RUNNER as SEEDED_RUNNER,
    _legacy_seeded_frame,
    _write_phase,
)
from tests.test_tg_dirichlet_tmajor_cuda_block import (
    _write_structural_seed_artifact,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
    source_schedule_records,
)
from tg_verifier.dirichlet_formulaic_qmajor_cursor import LaneRange
from tg_verifier.dirichlet_formulaic_qmajor_service import (
    replay_formulaic_service_stream,
    validate_formulaic_cuda_summary,
    write_formulaic_service_stream,
)
from tg_verifier.dirichlet_lattice_cache import _synthetic_row
from tg_verifier.dirichlet_largeq_batch import FRAME_FACTOR
from tg_verifier.dirichlet_resident_qmajor_phase import (
    replay_resident_qmajor_phase,
    validate_resident_phase_cuda_summary,
)
from tg_verifier.dirichlet_resident_qmajor_stream import (
    BOUNDED_PROJECTION_COVERAGE,
    EXACT_CANDIDATE_PHASE_COVERAGE,
    LANE_HEADER,
    MAXIMUM_PROJECTED_PHASE_OUTPUT_BYTES,
    PHASE_CUTS,
    QLane,
    ROW_ARTIFACT_HEADER,
    STREAM_HEADER,
    TARGET_HEADER,
    DirichletResidentQMajorStreamError,
    build_stream_plan,
    canonical_q_lanes,
    capability,
    compare_bounded_equivalence,
    explicit_device_memory_formula,
    explicit_executor_buffer_formula,
    lane_partition_digest,
    phase_plan_digest,
    replay_row_artifact,
    replay_sidecar_artifact,
    validate_cuda_summary,
    write_row_artifact,
    write_sidecar_artifact,
)
from tg_verifier.dirichlet_tmajor_cuda_block import ROW_HEADER


ROOT = Path(__file__).resolve().parents[1]
STREAM_RUNNER = Path(
    os.environ.get(
        "TG_DIRICHLET_RESIDENT_STREAM_BINARY",
        ROOT
        / "build/tg-production-kat/"
        "sparkinterval-tg-dirichlet-resident-qmajor-stream",
    )
)
SOURCE_QS = (10_001, 10_080, 11_088, 18_480)
EXPECTED_EXECUTION_QS = (10_080, 18_480, 11_088, 10_001)
EXPECTED_PLAN_SHA256 = (
    "cdf628fd558019d0649cd01a176dd0466"
    "e2dd98a2e31b95baa956a807fa39b7d"
)
EXPECTED_LANE_PARTITION_SHA256 = (
    "9bebed93613e99fa4af5e4cefc6f4149"
    "bb841d330aa72929594f3904e4df7e81"
)
EXPECTED_ROW_SHA256 = (
    "10ed422992a21b4f74a862cd52f809003"
    "869cecd30e6e1c75cbdd0604c10d0ac"
)
EXPECTED_SIDECAR_SHA256 = (
    "1b1dc1c3ffb0ddc67568b4d2d35b88e"
    "79e5bb5ffe2fa8533669dd9862a4d79e7"
)
EXPECTED_SOURCE_PHASE_PLANS = (
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


def _schedule(
    row_counts: tuple[int, ...] = (2, 2, 2, 2)
) -> object:
    return parse_schedule_manifest(
        build_schedule_manifest_bytes(
            tuple(
                ScheduleRecord(q, rows)
                for q, rows in zip(
                    SOURCE_QS, row_counts, strict=True
                )
            )
        )
    )


def _wide_sidecars(target: object) -> tuple[bytes, bytes]:
    batch_count = int(getattr(target, "batch_count"))
    return (
        FRAME_FACTOR.pack(-1.0, 1.0, -1.0, 1.0) * batch_count,
        struct.pack("<d", 0.0) * batch_count,
    )


def _plan(schedule: object) -> object:
    return build_stream_plan(
        schedule,
        phase_index=0,
        coverage_mode=BOUNDED_PROJECTION_COVERAGE,
        loaded_first_t_index=0,
        loaded_t_index_stop_exclusive=2,
        lanes=(QLane(0, 0, 2), QLane(1, 2, 4)),
    )


def _write_stream_inputs(
    root: Path,
    schedule: object,
    plan: object,
    *,
    recovery_seed_sha256: str,
) -> tuple[Path, dict[str, object], Path, dict[str, object]]:
    row_path = root / "resident-stream-rows.bin"
    row_receipt = write_row_artifact(
        row_path,
        schedule,
        plan,
        recovery_seed_sha256=recovery_seed_sha256,
        source_contract_sha256="b" * 64,
        lattice_source_sha256="c" * 64,
        row_provider=_synthetic_row,
    )
    sidecar_path = root / "resident-stream-sidecars.bin"
    sidecar_receipt = write_sidecar_artifact(
        sidecar_path,
        schedule,
        plan,
        row_artifact_sha256=str(row_receipt["input_sha256"]),
        recovery_seed_sha256=recovery_seed_sha256,
        source_contract_sha256="b" * 64,
        sidecar_source_sha256="d" * 64,
        sidecar_provider=_wide_sidecars,
    )
    return row_path, row_receipt, sidecar_path, sidecar_receipt


def _wait_for_barrier(
    ready: Path, process: subprocess.Popen[bytes]
) -> None:
    deadline = time.monotonic() + 15
    while not ready.exists():
        if process.poll() is not None:
            _stdout, stderr = process.communicate()
            raise AssertionError(
                f"runner exited before barrier: {stderr!r}"
            )
        if time.monotonic() >= deadline:
            raise AssertionError("timed out waiting for test barrier")
        time.sleep(0.01)


class DirichletResidentQMajorStreamStructuralTest(unittest.TestCase):
    def test_ten_exact_source_phase_plans_are_pinned(self) -> None:
        schedule = parse_schedule_manifest(
            build_schedule_manifest_bytes(
                source_schedule_records(), full_source=True
            )
        )
        lanes = canonical_q_lanes(
            0, len(schedule.execution_records)
        )
        partition = lane_partition_digest(
            schedule,
            lanes,
            start_execution_q_index=0,
            stop_execution_q_index=len(schedule.execution_records),
        )
        self.assertEqual(len(lanes), 4_571)
        self.assertEqual(
            partition,
            "a749174a3fba56bf6a255d61e2135b39"
            "97574c22f17c45589851ea8e592b554c",
        )
        observed = tuple(
            phase_plan_digest(
                schedule,
                phase_index=index,
                coverage_mode=EXACT_CANDIDATE_PHASE_COVERAGE,
                loaded_first_t_index=first,
                loaded_t_index_stop_exclusive=stop,
                start_execution_q_index=0,
                stop_execution_q_index=(
                    len(schedule.execution_records)
                ),
                lane_partition_sha256=partition,
            )
            for index, (first, stop) in enumerate(
                zip(
                    PHASE_CUTS[:-1],
                    PHASE_CUTS[1:],
                    strict=True,
                )
            )
        )
        self.assertEqual(observed, EXPECTED_SOURCE_PHASE_PLANS)
        maximum_output_phase = build_stream_plan(
            schedule,
            phase_index=5,
            coverage_mode=EXACT_CANDIDATE_PHASE_COVERAGE,
        )
        self.assertEqual(maximum_output_phase.target_count, 5_380_665)
        self.assertEqual(
            maximum_output_phase.value_count, 34_172_695_117_846
        )
        self.assertEqual(
            maximum_output_phase.target_count * 72
            + maximum_output_phase.value_count * 32,
            MAXIMUM_PROJECTED_PHASE_OUTPUT_BYTES,
        )
        maximum_row_phase = build_stream_plan(
            schedule,
            phase_index=7,
            coverage_mode=EXACT_CANDIDATE_PHASE_COVERAGE,
        )
        self.assertEqual(maximum_row_phase.row_count, 39_488)
        self.assertEqual(maximum_row_phase.active_q_count, 93_257)
        self.assertEqual(maximum_row_phase.target_count, 19_894_223)
        self.assertEqual(
            maximum_row_phase.target_row_reference_count,
            1_270_668_873,
        )
        self.assertEqual(
            maximum_row_phase.sidecar_input_size_bytes,
            53_852_286_440,
        )
        self.assertEqual(
            sum(
                lane.active_q_count == 0
                for lane in maximum_row_phase.lane_accounting
            ),
            339,
        )
        source_device = explicit_device_memory_formula(
            maximum_row_phase, seed_record_count=1_999_999
        )
        self.assertEqual(
            source_device["resident_lattice_bytes"],
            41_406_169_088,
        )
        self.assertEqual(
            source_device["known_allocation_bytes"],
            41_774_471_232,
        )
        self.assertFalse(source_device["source_h100_fit_claimed"])
        if STREAM_RUNNER.is_file():
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                seed_path = root / "seeds.bin"
                seed_sha256 = _write_structural_seed_artifact(
                    seed_path, q_stop=max(SOURCE_QS)
                )
                schedule_path = root / "source-schedule.bin"
                schedule_path.write_bytes(schedule.raw)
                output_path = root / "must-stay-empty.bin"
                summary_path = root / "must-not-exist.json"
                with output_path.open("wb") as output:
                    rejected = subprocess.run(
                        [
                            str(STREAM_RUNNER),
                            str(seed_path),
                            seed_sha256,
                            str(schedule_path),
                            observed[0],
                            str(root / "missing-rows.bin"),
                            "0" * 64,
                            str(root / "missing-sidecars.bin"),
                            "0" * 64,
                            str(summary_path),
                            "0",
                            "--allow-prefix-kat",
                        ],
                        stdout=output,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=30,
                    )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn(
                    b"requires a pipe/socket", rejected.stderr
                )
                self.assertEqual(output_path.read_bytes(), b"")
                self.assertFalse(summary_path.exists())

    def test_streaming_roundtrip_memory_formula_and_false_flags(
        self,
    ) -> None:
        schedule = _schedule()
        plan = _plan(schedule)
        self.assertEqual(
            tuple(record.q for record in schedule.execution_records),
            EXPECTED_EXECUTION_QS,
        )
        self.assertEqual(plan.phase_plan_sha256, EXPECTED_PLAN_SHA256)
        self.assertEqual(
            plan.lane_partition_sha256,
            EXPECTED_LANE_PARTITION_SHA256,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed_path = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seed_path, q_stop=max(SOURCE_QS)
            )
            rows, row_receipt, sidecars, sidecar_receipt = (
                _write_stream_inputs(
                    root,
                    schedule,
                    plan,
                    recovery_seed_sha256=seed_sha256,
                )
            )
            self.assertEqual(
                row_receipt["input_sha256"], EXPECTED_ROW_SHA256
            )
            self.assertEqual(
                sidecar_receipt["input_sha256"],
                EXPECTED_SIDECAR_SHA256,
            )
            parsed_rows = replay_row_artifact(
                rows,
                schedule,
                plan,
                expected_input_sha256=EXPECTED_ROW_SHA256,
                capture_rows=True,
            )
            parsed_sidecars = replay_sidecar_artifact(
                sidecars,
                schedule,
                plan,
                parsed_rows,
                expected_input_sha256=EXPECTED_SIDECAR_SHA256,
                capture_frames=True,
            )
            self.assertEqual(len(parsed_rows.captured_rows), 2)
            self.assertEqual(
                len(parsed_sidecars.captured_frames), 4
            )
            self.assertEqual(
                tuple(
                    frame.target.q
                    for frame in parsed_sidecars.captured_frames
                ),
                EXPECTED_EXECUTION_QS,
            )

        device = explicit_device_memory_formula(
            plan, seed_record_count=92_399
        )
        buffers = explicit_executor_buffer_formula(
            plan, seed_record_count=92_399
        )
        self.assertEqual(device["known_allocation_bytes"], 7_237_408)
        self.assertEqual(buffers["host_row_staging_bytes"], 1_048_576)
        self.assertEqual(
            buffers["host_payload_staging_bound_bytes"], 1_048_576
        )
        self.assertEqual(buffers["disk_row_artifact_bytes"], 2_097_776)
        self.assertEqual(
            buffers["disk_sidecar_artifact_bytes"], 2_264
        )
        self.assertEqual(
            buffers["projected_output_stream_bytes"], 1_204_512
        )
        self.assertEqual(
            MAXIMUM_PROJECTED_PHASE_OUTPUT_BYTES,
            1_093_526_631_178_952,
        )
        self.assertFalse(
            buffers["source_output_materialization_feasible_claimed"]
        )
        report = capability()
        self.assertTrue(
            report["bounded_projection_cuda_kat_completed"]
        )
        self.assertTrue(
            report[
                "separate_host_device_disk_buffer_formula_implemented"
            ]
        )
        for key in (
            "source_phase_execution_completed",
            "source_scale_run_completed",
            "source_h100_fit_claimed",
            "h100_source_phase_completed",
            "production_run_completed",
            "trusted_execution_attested",
            "completed_l_zero_state_validated",
            "zero_completeness_claimed",
            "external_atom_discharged",
        ):
            self.assertFalse(report[key], key)
        self.assertFalse(
            report["full_source_regular_file_output_supported"]
        )
        self.assertTrue(
            report[
                "full_source_pipe_or_socket_output_required"
            ]
        )
        self.assertFalse(
            report["full_source_semantic_sign_reducer_integrated"]
        )
        self.assertTrue(
            report[
                "stdout_backpressured_target_stream_implemented"
            ]
        )

    def test_hostile_truncation_reorder_and_substitution_rejected(
        self,
    ) -> None:
        schedule = _schedule()
        plan = _plan(schedule)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows, _row_receipt, sidecars, _sidecar_receipt = (
                _write_stream_inputs(
                    root,
                    schedule,
                    plan,
                    recovery_seed_sha256="a" * 64,
                )
            )
            original_rows = rows.read_bytes()
            original_sidecars = sidecars.read_bytes()

            row_substitution = bytearray(original_rows)
            row_substitution[
                ROW_ARTIFACT_HEADER.size + ROW_HEADER.size
            ] ^= 1
            substituted_rows = root / "row-substitution.bin"
            substituted_rows.write_bytes(row_substitution)
            with self.assertRaises(
                DirichletResidentQMajorStreamError
            ):
                replay_row_artifact(
                    substituted_rows, schedule, plan
                )

            row_stride = ROW_HEADER.size + 1_048_576
            row_reorder = bytearray(original_rows)
            first = ROW_ARTIFACT_HEADER.size
            second = first + row_stride
            row_reorder[first : first + row_stride], row_reorder[
                second : second + row_stride
            ] = (
                row_reorder[second : second + row_stride],
                row_reorder[first : first + row_stride],
            )
            reordered_rows = root / "row-reorder.bin"
            reordered_rows.write_bytes(row_reorder)
            with self.assertRaises(
                DirichletResidentQMajorStreamError
            ):
                replay_row_artifact(reordered_rows, schedule, plan)

            truncated_rows = root / "row-truncated.bin"
            truncated_rows.write_bytes(original_rows[:-1])
            with self.assertRaises(
                DirichletResidentQMajorStreamError
            ):
                replay_row_artifact(truncated_rows, schedule, plan)

            parsed_rows = replay_row_artifact(rows, schedule, plan)
            target_start = STREAM_HEADER.size + LANE_HEADER.size
            target_bytes = TARGET_HEADER.size + 2 * (
                FRAME_FACTOR.size + 8
            )
            target_reorder = bytearray(original_sidecars)
            target_reorder[
                target_start : target_start + target_bytes
            ], target_reorder[
                target_start
                + target_bytes : target_start
                + 2 * target_bytes
            ] = (
                target_reorder[
                    target_start
                    + target_bytes : target_start
                    + 2 * target_bytes
                ],
                target_reorder[
                    target_start : target_start + target_bytes
                ],
            )
            reordered_targets = root / "target-reorder.bin"
            reordered_targets.write_bytes(target_reorder)
            with self.assertRaises(
                DirichletResidentQMajorStreamError
            ):
                replay_sidecar_artifact(
                    reordered_targets,
                    schedule,
                    plan,
                    parsed_rows,
                )

            lane_bytes = plan.lane_accounting[0].lane_input_bytes
            lane_reorder = bytearray(original_sidecars)
            lane_start = STREAM_HEADER.size
            lane_reorder[
                lane_start : lane_start + lane_bytes
            ], lane_reorder[
                lane_start + lane_bytes : lane_start + 2 * lane_bytes
            ] = (
                lane_reorder[
                    lane_start
                    + lane_bytes : lane_start
                    + 2 * lane_bytes
                ],
                lane_reorder[
                    lane_start : lane_start + lane_bytes
                ],
            )
            reordered_lanes = root / "lane-reorder.bin"
            reordered_lanes.write_bytes(lane_reorder)
            with self.assertRaises(
                DirichletResidentQMajorStreamError
            ):
                replay_sidecar_artifact(
                    reordered_lanes,
                    schedule,
                    plan,
                    parsed_rows,
                )

            q_substitution = bytearray(original_sidecars)
            target = list(
                TARGET_HEADER.unpack_from(
                    q_substitution, target_start
                )
            )
            target[4] = 10_001
            TARGET_HEADER.pack_into(
                q_substitution, target_start, *target
            )
            substituted_q = root / "q-substitution.bin"
            substituted_q.write_bytes(q_substitution)
            with self.assertRaises(
                DirichletResidentQMajorStreamError
            ):
                replay_sidecar_artifact(
                    substituted_q, schedule, plan, parsed_rows
                )

            sidecar_substitution = bytearray(original_sidecars)
            sidecar_substitution[
                target_start + TARGET_HEADER.size
            ] ^= 1
            substituted_sidecar = root / "sidecar-substitution.bin"
            substituted_sidecar.write_bytes(sidecar_substitution)
            with self.assertRaises(
                DirichletResidentQMajorStreamError
            ):
                replay_sidecar_artifact(
                    substituted_sidecar,
                    schedule,
                    plan,
                    parsed_rows,
                )

            truncated_sidecar = root / "sidecar-truncated.bin"
            truncated_sidecar.write_bytes(original_sidecars[:-1])
            with self.assertRaises(
                DirichletResidentQMajorStreamError
            ):
                replay_sidecar_artifact(
                    truncated_sidecar,
                    schedule,
                    plan,
                    parsed_rows,
                )


@unittest.skipUnless(
    STREAM_RUNNER.is_file() and SEEDED_RUNNER.is_file(),
    "requires built resident-stream and seeded CUDA runners",
)
class DirichletResidentQMajorStreamCudaKat(unittest.TestCase):
    def test_descriptor_and_event_reuse_across_q_batches(
        self,
    ) -> None:
        schedule = parse_schedule_manifest(
            build_schedule_manifest_bytes(
                (ScheduleRecord(10_001, 65),)
            )
        )
        plan = build_stream_plan(
            schedule,
            phase_index=0,
            coverage_mode=BOUNDED_PROJECTION_COVERAGE,
            loaded_first_t_index=0,
            loaded_t_index_stop_exclusive=65,
            lanes=(QLane(0, 0, 1),),
        )
        self.assertEqual(plan.active_q_count, 1)
        self.assertEqual(plan.target_count, 2)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed_path = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seed_path, q_stop=10_001
            )
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(schedule.raw)
            rows, row_receipt, sidecars, sidecar_receipt = (
                _write_stream_inputs(
                    root,
                    schedule,
                    plan,
                    recovery_seed_sha256=seed_sha256,
                )
            )
            parsed_rows = replay_row_artifact(
                rows, schedule, plan
            )
            parsed_sidecars = replay_sidecar_artifact(
                sidecars, schedule, plan, parsed_rows
            )
            summary_path = root / "summary.json"
            completed = subprocess.run(
                [
                    str(STREAM_RUNNER),
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    plan.phase_plan_sha256,
                    str(rows),
                    str(row_receipt["input_sha256"]),
                    str(sidecars),
                    str(sidecar_receipt["input_sha256"]),
                    str(summary_path),
                    "0",
                    "--allow-prefix-kat",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode(errors="replace"),
            )
            output_path = root / "output.bin"
            output_path.write_bytes(completed.stdout)
            summary = validate_cuda_summary(
                summary_path,
                schedule,
                parsed_rows,
                parsed_sidecars,
                output_path,
            )
            self.assertEqual(summary["target_count"], 2)
            self.assertEqual(
                summary["descriptor_reconstruction_count"], 1
            )
            self.assertEqual(
                summary["descriptor_h2d_upload_count"], 1
            )
            self.assertEqual(summary["cuda_event_create_count"], 2)
            self.assertEqual(summary["cuda_event_reuse_count"], 2)
            self.assertEqual(
                summary["lattice_h2d_upload_call_count"], 65
            )

    def test_empty_q_lanes_remain_bounded_and_executable(self) -> None:
        schedule = _schedule((2, 1, 2, 1))
        plan = build_stream_plan(
            schedule,
            phase_index=0,
            coverage_mode=BOUNDED_PROJECTION_COVERAGE,
            loaded_first_t_index=1,
            loaded_t_index_stop_exclusive=2,
            lanes=tuple(
                QLane(index, index, index + 1)
                for index in range(4)
            ),
        )
        self.assertEqual(
            tuple(
                lane.active_q_count
                for lane in plan.lane_accounting
            ),
            (0, 0, 1, 1),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed_path = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seed_path, q_stop=max(SOURCE_QS)
            )
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(schedule.raw)
            rows, row_receipt, sidecars, sidecar_receipt = (
                _write_stream_inputs(
                    root,
                    schedule,
                    plan,
                    recovery_seed_sha256=seed_sha256,
                )
            )
            parsed_rows = replay_row_artifact(
                rows, schedule, plan
            )
            parsed_sidecars = replay_sidecar_artifact(
                sidecars, schedule, plan, parsed_rows
            )
            summary_path = root / "summary.json"
            completed = subprocess.run(
                [
                    str(STREAM_RUNNER),
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    plan.phase_plan_sha256,
                    str(rows),
                    str(row_receipt["input_sha256"]),
                    str(sidecars),
                    str(sidecar_receipt["input_sha256"]),
                    str(summary_path),
                    "0",
                    "--allow-prefix-kat",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode(errors="replace"),
            )
            output_path = root / "output.bin"
            output_path.write_bytes(completed.stdout)
            summary = validate_cuda_summary(
                summary_path,
                schedule,
                parsed_rows,
                parsed_sidecars,
                output_path,
            )
            self.assertEqual(summary["lane_count"], 4)
            self.assertEqual(summary["target_count"], 2)
            self.assertEqual(
                summary["descriptor_h2d_upload_count"], 2
            )

    def test_exact_legacy_formulaic_resident_equivalence_and_attacks(
        self,
    ) -> None:
        schedule = _schedule()
        plan = _plan(schedule)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed_path = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seed_path, q_stop=max(SOURCE_QS)
            )
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(schedule.raw)
            rows, row_receipt, sidecars, sidecar_receipt = (
                _write_stream_inputs(
                    root,
                    schedule,
                    plan,
                    recovery_seed_sha256=seed_sha256,
                )
            )
            parsed_rows = replay_row_artifact(
                rows,
                schedule,
                plan,
                expected_input_sha256=str(
                    row_receipt["input_sha256"]
                ),
                capture_rows=True,
            )
            parsed_sidecars = replay_sidecar_artifact(
                sidecars,
                schedule,
                plan,
                parsed_rows,
                expected_input_sha256=str(
                    sidecar_receipt["input_sha256"]
                ),
                capture_frames=True,
            )

            stream_summary_path = root / "stream-summary.json"
            completed = subprocess.run(
                [
                    str(STREAM_RUNNER),
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    plan.phase_plan_sha256,
                    str(rows),
                    str(row_receipt["input_sha256"]),
                    str(sidecars),
                    str(sidecar_receipt["input_sha256"]),
                    str(stream_summary_path),
                    "0",
                    "--allow-prefix-kat",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode(errors="replace"),
            )
            output_path = root / "stream-output.bin"
            output_path.write_bytes(completed.stdout)
            stream_summary = validate_cuda_summary(
                stream_summary_path,
                schedule,
                parsed_rows,
                parsed_sidecars,
                output_path,
            )
            self.assertEqual(
                stream_summary["output_sha256"],
                EXPECTED_OUTPUT_SHA256,
            )
            self.assertEqual(
                stream_summary["lattice_device_allocation_count"], 1
            )
            self.assertEqual(
                stream_summary["lattice_h2d_upload_call_count"], 2
            )
            self.assertEqual(
                stream_summary["descriptor_h2d_upload_count"], 4
            )
            self.assertEqual(
                stream_summary["cuda_event_create_count"], 2
            )
            self.assertEqual(
                stream_summary["cuda_event_reuse_count"], 4
            )

            phase_path, phase_receipt = _write_phase(
                root,
                schedule,
                recovery_seed_sha256=seed_sha256,
                first_t_index=0,
                t_index_stop_exclusive=2,
            )
            parsed_phase = replay_resident_qmajor_phase(
                phase_path,
                schedule,
                expected_input_sha256=str(
                    phase_receipt["input_sha256"]
                ),
            )
            phase_summary_path = root / "phase-summary.json"
            phase_run = subprocess.run(
                [
                    str(SEEDED_RUNNER),
                    "--resident-qmajor-phase",
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    str(phase_receipt["phase_plan_sha256"]),
                    str(phase_path),
                    str(phase_receipt["input_sha256"]),
                    str(phase_summary_path),
                    "0",
                    "--allow-prefix-kat",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            self.assertEqual(
                phase_run.returncode,
                0,
                phase_run.stderr.decode(errors="replace"),
            )
            phase_output_path = root / "phase-output.bin"
            phase_output_path.write_bytes(phase_run.stdout)
            phase_summary = validate_resident_phase_cuda_summary(
                phase_summary_path, parsed_phase, phase_output_path
            )

            formulaic_path = root / "formulaic.bin"
            formulaic_receipt = write_formulaic_service_stream(
                formulaic_path,
                schedule,
                (LaneRange(0, 0, 2),),
                recovery_seed_sha256=seed_sha256,
                source_contract_sha256="b" * 64,
                lattice_source_sha256="c" * 64,
                sidecar_source_sha256="d" * 64,
                row_provider=lambda _target, t_index: _synthetic_row(
                    t_index
                ),
                sidecar_provider=_wide_sidecars,
                maximum_batch_count=64,
            )
            parsed_formulaic = replay_formulaic_service_stream(
                formulaic_path,
                schedule,
                expected_stream_sha256=str(
                    formulaic_receipt["input_stream_sha256"]
                ),
            )
            formulaic_summary_path = root / "formulaic-summary.json"
            formulaic_run = subprocess.run(
                [
                    str(SEEDED_RUNNER),
                    "--formulaic-qmajor-service",
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    str(formulaic_receipt["plan_sha256"]),
                    str(formulaic_summary_path),
                    "0",
                    "--allow-prefix-kat",
                ],
                input=formulaic_path.read_bytes(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            self.assertEqual(
                formulaic_run.returncode,
                0,
                formulaic_run.stderr.decode(errors="replace"),
            )
            formulaic_output_path = root / "formulaic-output.bin"
            formulaic_output_path.write_bytes(formulaic_run.stdout)
            formulaic_summary = validate_formulaic_cuda_summary(
                formulaic_summary_path,
                parsed_formulaic,
                formulaic_output_path,
            )

            legacy_output = bytearray()
            for index, frame in enumerate(
                parsed_sidecars.captured_frames
            ):
                first = frame.target.first_t_index
                stop = frame.target.t_index_stop_exclusive
                legacy_input = root / f"legacy-{index}.TGDLQB2"
                legacy_capture = root / f"legacy-{index}.TGDAFFI1"
                legacy_input.write_bytes(
                    _legacy_seeded_frame(
                        q=frame.target.q,
                        first_t_index=first,
                        rows=parsed_rows.captured_rows[first:stop],
                        factors=frame.factors,
                        tails=frame.tails,
                    )
                )
                legacy_run = subprocess.run(
                    [
                        str(SEEDED_RUNNER),
                        str(seed_path),
                        seed_sha256,
                        str(legacy_input),
                        str(legacy_capture),
                        "0",
                        "1",
                        "--allow-prefix-kat",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(
                    legacy_run.returncode,
                    0,
                    legacy_run.stderr.decode(errors="replace"),
                )
                legacy_output.extend(legacy_capture.read_bytes())
            self.assertEqual(completed.stdout, phase_run.stdout)
            self.assertEqual(completed.stdout, formulaic_run.stdout)
            self.assertEqual(completed.stdout, bytes(legacy_output))

            comparison = compare_bounded_equivalence(
                plan,
                stream_summary,
                current_resident_input_bytes=int(
                    phase_receipt["input_size_bytes"]
                ),
                formulaic_input_bytes=int(
                    formulaic_receipt["input_stream_size_bytes"]
                ),
                current_resident_kernel_nanoseconds=int(
                    phase_summary["elapsed_kernel_nanoseconds"]
                ),
                formulaic_kernel_nanoseconds=int(
                    formulaic_summary["elapsed_kernel_nanoseconds"]
                ),
                expected_output_sha256=EXPECTED_OUTPUT_SHA256,
            )
            self.assertEqual(
                comparison["stream_total_input_bytes"], 2_100_040
            )
            self.assertEqual(
                comparison["current_resident_input_bytes"], 2_098_776
            )
            self.assertEqual(
                comparison["formulaic_row_repeated_input_bytes"],
                8_390_744,
            )
            self.assertEqual(
                comparison[
                    "stream_minus_current_resident_input_bytes"
                ],
                1_264,
            )
            self.assertEqual(
                comparison["bytes_saved_vs_formulaic"], 6_290_704
            )
            self.assertTrue(comparison["exact_output_bytes_equal"])

            original_rows = rows.read_bytes()
            original_sidecars = sidecars.read_bytes()

            def compiled_reject(
                name: str,
                *,
                row_raw: bytes = original_rows,
                sidecar_raw: bytes = original_sidecars,
                plan_sha256: str = plan.phase_plan_sha256,
            ) -> subprocess.CompletedProcess[bytes]:
                attack_rows = root / f"{name}-rows.bin"
                attack_sidecars = root / f"{name}-sidecars.bin"
                attack_rows.write_bytes(row_raw)
                attack_sidecars.write_bytes(sidecar_raw)
                attack_summary = root / f"{name}-summary.json"
                result = subprocess.run(
                    [
                        str(STREAM_RUNNER),
                        str(seed_path),
                        seed_sha256,
                        str(schedule_path),
                        plan_sha256,
                        str(attack_rows),
                        hashlib.sha256(row_raw).hexdigest(),
                        str(attack_sidecars),
                        hashlib.sha256(sidecar_raw).hexdigest(),
                        str(attack_summary),
                        "0",
                        "--allow-prefix-kat",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                )
                self.assertNotEqual(result.returncode, 0, name)
                self.assertEqual(result.stdout, b"", name)
                self.assertFalse(attack_summary.exists(), name)
                return result

            compiled_reject(
                "row-truncation", row_raw=original_rows[:-1]
            )
            row_substitution = bytearray(original_rows)
            row_substitution[
                ROW_ARTIFACT_HEADER.size + ROW_HEADER.size
            ] ^= 1
            compiled_reject(
                "row-substitution",
                row_raw=bytes(row_substitution),
            )
            row_stride = ROW_HEADER.size + 1_048_576
            row_reorder = bytearray(original_rows)
            first = ROW_ARTIFACT_HEADER.size
            second = first + row_stride
            row_reorder[first : first + row_stride], row_reorder[
                second : second + row_stride
            ] = (
                row_reorder[second : second + row_stride],
                row_reorder[first : first + row_stride],
            )
            compiled_reject(
                "row-reorder", row_raw=bytes(row_reorder)
            )
            compiled_reject(
                "sidecar-truncation",
                sidecar_raw=original_sidecars[:-1],
            )

            target_start = STREAM_HEADER.size + LANE_HEADER.size
            target_bytes = TARGET_HEADER.size + 2 * (
                FRAME_FACTOR.size + 8
            )
            target_reorder = bytearray(original_sidecars)
            target_reorder[
                target_start : target_start + target_bytes
            ], target_reorder[
                target_start
                + target_bytes : target_start
                + 2 * target_bytes
            ] = (
                target_reorder[
                    target_start
                    + target_bytes : target_start
                    + 2 * target_bytes
                ],
                target_reorder[
                    target_start : target_start + target_bytes
                ],
            )
            compiled_reject(
                "target-reorder",
                sidecar_raw=bytes(target_reorder),
            )

            lane_bytes = plan.lane_accounting[0].lane_input_bytes
            lane_reorder = bytearray(original_sidecars)
            lane_start = STREAM_HEADER.size
            lane_reorder[
                lane_start : lane_start + lane_bytes
            ], lane_reorder[
                lane_start + lane_bytes : lane_start + 2 * lane_bytes
            ] = (
                lane_reorder[
                    lane_start
                    + lane_bytes : lane_start
                    + 2 * lane_bytes
                ],
                lane_reorder[
                    lane_start : lane_start + lane_bytes
                ],
            )
            compiled_reject(
                "lane-reorder", sidecar_raw=bytes(lane_reorder)
            )

            q_substitution = bytearray(original_sidecars)
            target = list(
                TARGET_HEADER.unpack_from(
                    q_substitution, target_start
                )
            )
            target[4] = 10_001
            TARGET_HEADER.pack_into(
                q_substitution, target_start, *target
            )
            compiled_reject(
                "q-substitution",
                sidecar_raw=bytes(q_substitution),
            )
            sidecar_substitution = bytearray(original_sidecars)
            sidecar_substitution[
                target_start + TARGET_HEADER.size
            ] ^= 1
            compiled_reject(
                "sidecar-substitution",
                sidecar_raw=bytes(sidecar_substitution),
            )
            compiled_reject(
                "plan-substitution", plan_sha256="0" * 64
            )

    def test_second_pass_rejects_post_preflight_row_and_sidecar_swaps(
        self,
    ) -> None:
        schedule = _schedule()
        plan = _plan(schedule)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed_path = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seed_path, q_stop=max(SOURCE_QS)
            )
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(schedule.raw)
            rows, row_receipt, sidecars, sidecar_receipt = (
                _write_stream_inputs(
                    root,
                    schedule,
                    plan,
                    recovery_seed_sha256=seed_sha256,
                )
            )
            original_rows = rows.read_bytes()
            original_sidecars = sidecars.read_bytes()
            row_replacement = bytearray(original_rows)
            row_replacement[
                ROW_ARTIFACT_HEADER.size + ROW_HEADER.size
            ] ^= 1
            sidecar_replacement = bytearray(original_sidecars)
            target_start = STREAM_HEADER.size + LANE_HEADER.size
            target = list(
                TARGET_HEADER.unpack_from(
                    sidecar_replacement, target_start
                )
            )
            target[4] = 10_001
            TARGET_HEADER.pack_into(
                sidecar_replacement, target_start, *target
            )

            for name, row_raw, sidecar_raw, expected_error in (
                (
                    "row",
                    bytes(row_replacement),
                    original_sidecars,
                    b"execution row changed after preflight",
                ),
                (
                    "sidecar",
                    original_rows,
                    bytes(sidecar_replacement),
                    b"target is substituted or reordered",
                ),
            ):
                with self.subTest(name=name):
                    rows.write_bytes(original_rows)
                    sidecars.write_bytes(original_sidecars)
                    summary = root / f"{name}-must-not-exist.json"
                    barrier = root / f"{name}-preflight"
                    environment = os.environ.copy()
                    environment[
                        "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_"
                        "RESIDENT_STREAM_PREFLIGHT_BARRIER"
                    ] = str(barrier)
                    process = subprocess.Popen(
                        [
                            str(STREAM_RUNNER),
                            str(seed_path),
                            seed_sha256,
                            str(schedule_path),
                            plan.phase_plan_sha256,
                            str(rows),
                            str(row_receipt["input_sha256"]),
                            str(sidecars),
                            str(sidecar_receipt["input_sha256"]),
                            str(summary),
                            "0",
                            "--allow-prefix-kat",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=environment,
                    )
                    try:
                        _wait_for_barrier(
                            Path(str(barrier) + ".ready"), process
                        )
                        rows.write_bytes(row_raw)
                        sidecars.write_bytes(sidecar_raw)
                        Path(
                            str(barrier) + ".continue"
                        ).write_bytes(b"go\n")
                        stdout, stderr = process.communicate(
                            timeout=30
                        )
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.communicate()
                    self.assertNotEqual(process.returncode, 0)
                    self.assertIn(expected_error, stderr)
                    self.assertEqual(stdout, b"")
                    self.assertFalse(summary.exists())


if __name__ == "__main__":
    unittest.main()
