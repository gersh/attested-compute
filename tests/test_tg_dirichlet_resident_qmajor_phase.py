# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tests.test_tg_dirichlet_tmajor_cuda_block import (
    _write_structural_seed_artifact,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
)
from tg_verifier.dirichlet_allchars_stage import (
    canonical_component_orders,
    canonical_residue_order,
)
from tg_verifier.dirichlet_formulaic_qmajor_cursor import LaneRange
from tg_verifier.dirichlet_formulaic_qmajor_service import (
    replay_formulaic_service_stream,
    validate_formulaic_cuda_summary,
    write_formulaic_service_stream,
)
from tg_verifier.dirichlet_lattice_cache import _synthetic_row
from tg_verifier.dirichlet_lattice_stage import (
    LATTICE_ROWS,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
)
from tg_verifier.dirichlet_largeq_batch import (
    FRAME_FACTOR,
    RESIDUE_DESCRIPTOR,
)
from tg_verifier.dirichlet_recovery_seeds import (
    SEEDED_BATCH_HEADER,
    SEEDED_BATCH_MAGIC,
    SOURCE_M,
    SOURCE_STEP_DENOMINATOR,
    SOURCE_STEP_NUMERATOR,
)
from tg_verifier.dirichlet_resident_qmajor_phase import (
    PHASE_HEADER,
    PHASE_TARGET,
    DirichletResidentQMajorPhaseError,
    active_phase_targets,
    capability,
    compare_with_row_repeated_baseline,
    replay_resident_qmajor_phase,
    validate_resident_phase_cuda_summary,
    write_resident_qmajor_phase,
)
from tg_verifier.dirichlet_tmajor_cuda_block import ROW_HEADER


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path(
    os.environ.get(
        "TG_DIRICHLET_TMAJOR_SEEDED_BINARY",
        ROOT
        / "build/tg-production-kat/"
        "sparkinterval-tg-dirichlet-largeq-seeded",
    )
)
SOURCE_QS = (10_001, 10_080, 11_088, 18_480)
EXPECTED_EXECUTION_QS = (10_080, 18_480, 11_088, 10_001)
EXPECTED_PHASE_PLAN_SHA256 = (
    "408b16760a74a8e95e1021e2a3758cbe"
    "1d2370865b7c6e3d8b4912b870140fed"
)
EXPECTED_PHASE_INPUT_SHA256 = (
    "1e476abf96895db74abf6c04f9b70cc8"
    "491c605215320f1ef2c1040a6df5c2aa"
)
EXPECTED_OUTPUT_SHA256 = (
    "deb868eb9f3ced5e5275df24ca40bd015"
    "8e3b7b860c6165d5b4f3935ad6a041e"
)


def _schedule(row_counts: tuple[int, ...]) -> object:
    return parse_schedule_manifest(
        build_schedule_manifest_bytes(
            tuple(
                ScheduleRecord(q, rows)
                for q, rows in zip(SOURCE_QS, row_counts, strict=True)
            )
        )
    )


def _wide_sidecars(target: object) -> tuple[bytes, bytes]:
    batch_count = int(getattr(target, "batch_count"))
    factors = FRAME_FACTOR.pack(-1.0, 1.0, -1.0, 1.0) * batch_count
    tails = struct.pack("<d", 0.0) * batch_count
    return factors, tails


def _write_phase(
    root: Path,
    schedule: object,
    *,
    recovery_seed_sha256: str,
    first_t_index: int,
    t_index_stop_exclusive: int,
) -> tuple[Path, dict[str, object]]:
    path = root / "resident-phase.bin"
    receipt = write_resident_qmajor_phase(
        path,
        schedule,
        phase_index=7,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
        recovery_seed_sha256=recovery_seed_sha256,
        source_contract_sha256="b" * 64,
        lattice_source_sha256="c" * 64,
        sidecar_source_sha256="d" * 64,
        row_provider=_synthetic_row,
        sidecar_provider=_wide_sidecars,
    )
    return path, receipt


def _legacy_seeded_frame(
    *,
    q: int,
    first_t_index: int,
    rows: tuple[bytes, ...],
    factors: bytes,
    tails: bytes,
) -> bytes:
    residues = canonical_residue_order(q)
    orders = canonical_component_orders(q)
    batch_count = len(rows)
    header = SEEDED_BATCH_HEADER.pack(
        SEEDED_BATCH_MAGIC,
        2,
        q,
        LATTICE_ROWS,
        TAYLOR_DEGREE,
        len(orders),
        batch_count,
        SOURCE_M,
        0,
        len(residues),
        first_t_index * SOURCE_STEP_NUMERATOR,
        SOURCE_STEP_DENOMINATOR,
        SOURCE_STEP_NUMERATOR,
        batch_count * LATTICE_ROWS * TAYLOR_COLUMNS,
        batch_count * len(residues),
        0,
    )
    descriptors = b"".join(
        RESIDUE_DESCRIPTOR.pack(a, canonical_lattice_row(q, a))
        for a in residues
    )
    return header + descriptors + factors + b"".join(rows) + tails


class DirichletResidentQMajorPhaseStructuralTest(unittest.TestCase):
    def test_active_q_clipping_and_independent_replay(self) -> None:
        schedule = _schedule((1, 4, 3, 4))
        targets = active_phase_targets(
            schedule,
            start_execution_q_index=0,
            stop_execution_q_index=4,
            phase_index=7,
            first_t_index=2,
            t_index_stop_exclusive=4,
        )
        self.assertEqual(
            tuple(
                (
                    target.q,
                    target.first_t_index,
                    target.t_index_stop_exclusive,
                )
                for target in targets
            ),
            (
                (10_080, 2, 4),
                (18_480, 2, 4),
                (11_088, 2, 3),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, receipt = _write_phase(
                root,
                schedule,
                recovery_seed_sha256="a" * 64,
                first_t_index=2,
                t_index_stop_exclusive=4,
            )
            parsed = replay_resident_qmajor_phase(
                path,
                schedule,
                expected_input_sha256=str(receipt["input_sha256"]),
            )
            self.assertEqual(len(parsed.rows), 2)
            self.assertEqual(len(parsed.frames), 3)
            self.assertEqual(parsed.target_row_reference_count, 5)
            self.assertEqual(
                tuple(frame.target.q for frame in parsed.frames),
                (10_080, 18_480, 11_088),
            )
            self.assertFalse(receipt["source_scale_run"])
            self.assertFalse(receipt["h100_source_phase_completed"])
            self.assertFalse(receipt["production_run_completed"])
            self.assertFalse(receipt["trusted_execution_attested"])
            self.assertFalse(receipt["zero_completeness_claimed"])
            self.assertFalse(receipt["external_atom_discharged"])

    def test_mutation_truncation_q_and_plan_attacks_rejected(self) -> None:
        schedule = _schedule((2, 2, 2, 2))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, _receipt = _write_phase(
                root,
                schedule,
                recovery_seed_sha256="a" * 64,
                first_t_index=0,
                t_index_stop_exclusive=2,
            )
            original = path.read_bytes()

            mutated = bytearray(original)
            mutated[PHASE_HEADER.size + ROW_HEADER.size] ^= 1
            mutated_path = root / "mutated.bin"
            mutated_path.write_bytes(mutated)
            with self.assertRaisesRegex(
                DirichletResidentQMajorPhaseError,
                "row is substituted",
            ):
                replay_resident_qmajor_phase(mutated_path, schedule)

            truncated_path = root / "truncated.bin"
            truncated_path.write_bytes(original[:-1])
            with self.assertRaisesRegex(
                DirichletResidentQMajorPhaseError,
                "header|footer",
            ):
                replay_resident_qmajor_phase(truncated_path, schedule)

            first_target = (
                PHASE_HEADER.size
                + 2 * (ROW_HEADER.size + 1_048_576)
            )
            substituted = bytearray(original)
            fields = list(PHASE_TARGET.unpack_from(substituted, first_target))
            fields[4] = 10_001
            PHASE_TARGET.pack_into(substituted, first_target, *fields)
            substituted_path = root / "q-substituted.bin"
            substituted_path.write_bytes(substituted)
            with self.assertRaisesRegex(
                DirichletResidentQMajorPhaseError,
                "target 0 is substituted",
            ):
                replay_resident_qmajor_phase(substituted_path, schedule)

            changed_plan = bytearray(original)
            header = list(PHASE_HEADER.unpack_from(changed_plan))
            header[5] = 8
            PHASE_HEADER.pack_into(changed_plan, 0, *header)
            changed_plan_path = root / "changed-plan.bin"
            changed_plan_path.write_bytes(changed_plan)
            with self.assertRaisesRegex(
                DirichletResidentQMajorPhaseError,
                "plan digest differs",
            ):
                replay_resident_qmajor_phase(changed_plan_path, schedule)

    def test_capability_keeps_all_completion_claims_false(self) -> None:
        report = capability()
        self.assertTrue(
            report["bounded_resident_qmajor_phase_implemented"]
        )
        self.assertTrue(report["bounded_real_cuda_kat_implemented"])
        self.assertFalse(report["bounded_real_cuda_kat_completed"])
        self.assertEqual(report["maximum_output_bytes"], 536_875_520)
        self.assertTrue(
            report["lattice_rows_serialized_and_uploaded_once"]
        )
        self.assertTrue(report["fail_closed_device_memory_preflight"])
        self.assertEqual(
            report["candidate_resident_t_shard_cuts"],
            [
                0,
                768,
                1_600,
                2_368,
                3_200,
                4_032,
                5_568,
                9_600,
                49_088,
                88_512,
                127_988,
            ],
        )
        self.assertEqual(
            report["candidate_resident_t_shard_phase_count"], 10
        )
        self.assertEqual(
            report["candidate_resident_t_shard_maximum_rows"], 39_488
        )
        self.assertEqual(
            report["candidate_resident_t_shard_report_sha256"],
            "eae086771356cc3e2cc26780012686f"
            "dbc3a8097aa76a3417056fe74f5a32eb6",
        )
        self.assertFalse(
            report[
                "candidate_source_resident_phase_executor_implemented"
            ]
        )
        self.assertFalse(
            report["candidate_source_resident_phase_fit_claimed"]
        )
        self.assertFalse(report["source_schedule_accepted"])
        self.assertFalse(report["source_scale_run_completed"])
        self.assertFalse(report["h100_source_phase_completed"])
        self.assertFalse(report["production_run_completed"])
        self.assertFalse(report["trusted_execution_attested"])
        self.assertFalse(report["zero_completeness_claimed"])
        self.assertFalse(report["external_atom_discharged"])


@unittest.skipUnless(RUNNER.is_file(), "requires built seeded CUDA runner")
class DirichletResidentQMajorPhaseCudaKat(unittest.TestCase):
    def test_exact_equivalence_attacks_and_measured_comparison(self) -> None:
        schedule = _schedule((2, 2, 2, 2))
        self.assertEqual(
            tuple(record.q for record in schedule.execution_records),
            EXPECTED_EXECUTION_QS,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed_path = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seed_path, q_stop=max(SOURCE_QS)
            )
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(schedule.raw)

            phase_path, phase_receipt = _write_phase(
                root,
                schedule,
                recovery_seed_sha256=seed_sha256,
                first_t_index=0,
                t_index_stop_exclusive=2,
            )
            self.assertEqual(
                phase_receipt["phase_plan_sha256"],
                EXPECTED_PHASE_PLAN_SHA256,
            )
            self.assertEqual(
                phase_receipt["input_sha256"],
                EXPECTED_PHASE_INPUT_SHA256,
            )
            parsed_phase = replay_resident_qmajor_phase(
                phase_path,
                schedule,
                expected_input_sha256=str(phase_receipt["input_sha256"]),
            )
            phase_summary_path = root / "phase-summary.json"
            phase_output_path = root / "phase-output.bin"
            phase = subprocess.run(
                [
                    str(RUNNER),
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
                phase.returncode,
                0,
                phase.stderr.decode(errors="replace"),
            )
            phase_output_path.write_bytes(phase.stdout)
            phase_summary = validate_resident_phase_cuda_summary(
                phase_summary_path, parsed_phase, phase_output_path
            )
            self.assertEqual(phase_summary["lattice_h2d_upload_count"], 1)
            self.assertEqual(
                phase_summary["descriptor_h2d_upload_count"], 4
            )
            self.assertEqual(
                phase_summary["output_sha256"], EXPECTED_OUTPUT_SHA256
            )
            self.assertTrue(
                phase_summary["device_memory_preflight_passed"]
            )

            baseline_path = root / "row-repeated.bin"
            baseline_receipt = write_formulaic_service_stream(
                baseline_path,
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
            parsed_baseline = replay_formulaic_service_stream(
                baseline_path,
                schedule,
                expected_stream_sha256=str(
                    baseline_receipt["input_stream_sha256"]
                ),
            )
            baseline_summary_path = root / "baseline-summary.json"
            baseline_output_path = root / "baseline-output.bin"
            baseline = subprocess.run(
                [
                    str(RUNNER),
                    "--formulaic-qmajor-service",
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    str(baseline_receipt["plan_sha256"]),
                    str(baseline_summary_path),
                    "0",
                    "--allow-prefix-kat",
                ],
                input=baseline_path.read_bytes(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            self.assertEqual(
                baseline.returncode,
                0,
                baseline.stderr.decode(errors="replace"),
            )
            baseline_output_path.write_bytes(baseline.stdout)
            baseline_summary = validate_formulaic_cuda_summary(
                baseline_summary_path,
                parsed_baseline,
                baseline_output_path,
            )
            self.assertEqual(phase.stdout, baseline.stdout)

            legacy_output = bytearray()
            for index, frame in enumerate(parsed_phase.frames):
                row_offset = (
                    frame.target.first_t_index
                    - parsed_phase.first_t_index
                )
                rows = parsed_phase.rows[
                    row_offset : row_offset + frame.target.batch_count
                ]
                legacy_input = root / f"legacy-{index}.TGDLQB2"
                legacy_capture = root / f"legacy-{index}.TGDAFFI1"
                legacy_input.write_bytes(
                    _legacy_seeded_frame(
                        q=frame.target.q,
                        first_t_index=frame.target.first_t_index,
                        rows=rows,
                        factors=frame.factors,
                        tails=frame.tails,
                    )
                )
                completed = subprocess.run(
                    [
                        str(RUNNER),
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
                    completed.returncode,
                    0,
                    completed.stderr.decode(errors="replace"),
                )
                legacy_output.extend(legacy_capture.read_bytes())
            self.assertEqual(bytes(legacy_output), phase.stdout)

            comparison = compare_with_row_repeated_baseline(
                parsed_phase,
                phase_summary,
                baseline_input_size_bytes=int(
                    baseline_receipt["input_stream_size_bytes"]
                ),
                baseline_kernel_nanoseconds=int(
                    baseline_summary["elapsed_kernel_nanoseconds"]
                ),
                baseline_output_sha256=str(
                    baseline_summary["output_stream_sha256"]
                ),
            )
            self.assertEqual(
                comparison["resident_input_size_bytes"], 2_098_776
            )
            self.assertEqual(
                comparison["row_repeated_input_size_bytes"], 8_390_744
            )
            self.assertEqual(comparison["input_bytes_saved"], 6_291_968)
            self.assertTrue(comparison["exact_output_bytes_equal"])
            self.assertFalse(comparison["source_scale_run"])
            self.assertFalse(comparison["h100_source_phase_completed"])
            self.assertFalse(comparison["production_run_completed"])
            self.assertFalse(comparison["trusted_execution_attested"])
            self.assertFalse(comparison["zero_completeness_claimed"])
            self.assertFalse(comparison["external_atom_discharged"])

            original = phase_path.read_bytes()

            def compiled_reject(
                name: str, raw: bytes, plan_sha256: str
            ) -> subprocess.CompletedProcess[bytes]:
                attack_path = root / f"{name}.bin"
                attack_path.write_bytes(raw)
                attack_summary = root / f"{name}.json"
                result = subprocess.run(
                    [
                        str(RUNNER),
                        "--resident-qmajor-phase",
                        str(seed_path),
                        seed_sha256,
                        str(schedule_path),
                        plan_sha256,
                        str(attack_path),
                        hashlib.sha256(raw).hexdigest(),
                        str(attack_summary),
                        "0",
                        "--allow-prefix-kat",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertFalse(attack_summary.exists())
                return result

            mutation = bytearray(original)
            mutation[PHASE_HEADER.size + ROW_HEADER.size] ^= 1
            compiled_reject(
                "row-mutation",
                bytes(mutation),
                str(phase_receipt["phase_plan_sha256"]),
            )

            compiled_reject(
                "truncation",
                original[:-1],
                str(phase_receipt["phase_plan_sha256"]),
            )

            target_offset = (
                PHASE_HEADER.size
                + 2 * (ROW_HEADER.size + 1_048_576)
            )
            q_attack = bytearray(original)
            target_fields = list(
                PHASE_TARGET.unpack_from(q_attack, target_offset)
            )
            target_fields[4] = 10_001
            PHASE_TARGET.pack_into(
                q_attack, target_offset, *target_fields
            )
            compiled_reject(
                "q-substitution",
                bytes(q_attack),
                str(phase_receipt["phase_plan_sha256"]),
            )

            plan_attack = bytearray(original)
            header_fields = list(PHASE_HEADER.unpack_from(plan_attack))
            header_fields[5] = 8
            PHASE_HEADER.pack_into(plan_attack, 0, *header_fields)
            rejected_plan = compiled_reject(
                "phase-plan",
                bytes(plan_attack),
                str(phase_receipt["phase_plan_sha256"]),
            )
            self.assertIn(
                b"canonical phase plan digest differs",
                rejected_plan.stderr,
            )


if __name__ == "__main__":
    unittest.main()
