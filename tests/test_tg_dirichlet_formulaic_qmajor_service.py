# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from tests.test_tg_dirichlet_tmajor_cuda_block import (
    _write_structural_seed_artifact,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
    validate_scheduled_multiq_framed_summary,
)
from tg_verifier.dirichlet_allchars_stage import (
    canonical_component_orders,
    canonical_residue_order,
)
from tg_verifier.dirichlet_formulaic_qmajor_cursor import LaneRange
from tg_verifier.dirichlet_formulaic_qmajor_service import (
    FRAME_HEADER,
    LANE_RECORD,
    ROW_BINDING_DOMAIN,
    SERVICE_HEADER,
    SIDECAR_DOMAIN,
    DirichletFormulaicQMajorServiceError,
    capability,
    replay_formulaic_cuda_arithmetic,
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
from tg_verifier import dirichlet_recovery_seeds as seeds
from tg_verifier.dirichlet_scheduled_largeq_pipeline import (
    _mpfr_replay_transform_frames,
)


ROOT = Path(__file__).resolve().parents[1]
SEEDED_RUNNER = Path(
    os.environ.get(
        "TG_DIRICHLET_TMAJOR_SEEDED_BINARY",
        ROOT
        / "build/tg-production-kat/"
        "sparkinterval-tg-dirichlet-largeq-seeded",
    )
)
ALLCHARS_RUNNER = Path(
    os.environ.get(
        "TG_DIRICHLET_ALLCHARS_BINARY",
        ROOT / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars",
    )
)
MPFR_CHECKER = Path(
    os.environ.get(
        "TG_DIRICHLET_ALLCHARS_MPFR_BINARY",
        ROOT
        / "build/tg-production-kat/"
        "sparkinterval-tg-dirichlet-allchars-mpfr",
    )
)

try:
    import flint as _flint  # type: ignore[import-not-found]

    PINNED_FLINT_AVAILABLE = (
        str(_flint.__version__) == "0.9.0"
        and str(_flint.__FLINT_VERSION__) == "3.6.0"
        and int(_flint.__FLINT_RELEASE__) == 30_600
    )
except ImportError:
    PINNED_FLINT_AVAILABLE = False


SOURCE_QS = (10_001, 10_080, 11_088, 18_480)
EXPECTED_EXECUTION_QS = (10_080, 18_480, 11_088, 10_001)


def _schedule() -> object:
    return parse_schedule_manifest(
        build_schedule_manifest_bytes(
            tuple(ScheduleRecord(q, 2) for q in SOURCE_QS)
        )
    )


def _wide_sidecars(target: object) -> tuple[bytes, bytes]:
    batch_count = int(getattr(target, "batch_count"))
    factors = FRAME_FACTOR.pack(-1.0, 1.0, -1.0, 1.0) * batch_count
    tails = struct.pack("<d", 0.0) * batch_count
    return factors, tails


def _build_stream(
    root: Path, *, recovery_seed_sha256: str
) -> tuple[object, Path, dict[str, object]]:
    schedule = _schedule()
    path = root / "formulaic.bin"
    receipt = write_formulaic_service_stream(
        path,
        schedule,
        (LaneRange(0, 0, 2),),
        recovery_seed_sha256=recovery_seed_sha256,
        source_contract_sha256="b" * 64,
        lattice_source_sha256="c" * 64,
        sidecar_source_sha256="d" * 64,
        row_provider=lambda _target, t_index: _synthetic_row(t_index),
        sidecar_provider=_wide_sidecars,
        maximum_batch_count=1,
    )
    return schedule, path, receipt


def _legacy_seeded_frame_bytes(frame: object) -> bytes:
    target = getattr(frame, "target")
    q = int(target.q)
    rows = tuple(getattr(frame, "rows"))
    factors = bytes(getattr(frame, "factors"))
    tails = bytes(getattr(frame, "tails"))
    residues = canonical_residue_order(q)
    orders = canonical_component_orders(q)
    header = seeds.SEEDED_BATCH_HEADER.pack(
        seeds.SEEDED_BATCH_MAGIC,
        2,
        q,
        LATTICE_ROWS,
        TAYLOR_DEGREE,
        len(orders),
        int(target.batch_count),
        seeds.SOURCE_M,
        0,
        len(residues),
        int(target.first_t_index) * seeds.SOURCE_STEP_NUMERATOR,
        seeds.SOURCE_STEP_DENOMINATOR,
        seeds.SOURCE_STEP_NUMERATOR,
        int(target.batch_count) * LATTICE_ROWS * TAYLOR_COLUMNS,
        int(target.batch_count) * len(residues),
        0,
    )
    descriptors = b"".join(
        RESIDUE_DESCRIPTOR.pack(a, canonical_lattice_row(q, a))
        for a in residues
    )
    return header + descriptors + factors + b"".join(rows) + tails


class DirichletFormulaicQMajorServiceStructuralTest(unittest.TestCase):
    def test_descriptor_free_stream_replays_exact_nonmonotone_cursor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule, path, receipt = _build_stream(
                root, recovery_seed_sha256="a" * 64
            )
            parsed = replay_formulaic_service_stream(
                path,
                schedule,
                expected_stream_sha256=receipt["input_stream_sha256"],
            )
            observed_qs = tuple(
                frame.target.q for frame in parsed.frames
            )
            self.assertEqual(
                observed_qs,
                tuple(
                    q
                    for q in EXPECTED_EXECUTION_QS
                    for _target in range(2)
                ),
            )
            self.assertEqual(len(parsed.frames), 8)
            self.assertEqual(parsed.row_reference_count, 8)
            self.assertEqual(parsed.descriptor_reconstruction_count, 4)
            self.assertEqual(receipt["canonical_descriptor_input_bytes"], 0)
            self.assertEqual(receipt["serialized_control_records_required"], 0)
            self.assertNotEqual(
                receipt["input_stream_sha256"],
                receipt["frame_stream_sha256"],
            )
            self.assertTrue(ROW_BINDING_DOMAIN.endswith(b"\0"))
            self.assertTrue(SIDECAR_DOMAIN.endswith(b"\0"))
            self.assertFalse(receipt["production_run_completed"])
            self.assertFalse(receipt["source_scale_run"])
            self.assertFalse(receipt["external_atom_discharged"])

    def test_cursor_substitution_truncation_and_external_pin_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule, path, receipt = _build_stream(
                root, recovery_seed_sha256="a" * 64
            )
            original = path.read_bytes()
            first_frame = SERVICE_HEADER.size + LANE_RECORD.size

            substituted = bytearray(original)
            fields = list(FRAME_HEADER.unpack_from(substituted, first_frame))
            fields[4] = 10_001
            FRAME_HEADER.pack_into(substituted, first_frame, *fields)
            substituted_path = root / "substituted.bin"
            substituted_path.write_bytes(substituted)
            with self.assertRaisesRegex(
                DirichletFormulaicQMajorServiceError,
                "substituted or malformed",
            ):
                replay_formulaic_service_stream(
                    substituted_path, schedule
                )

            truncated = root / "truncated.bin"
            truncated.write_bytes(original[:-1])
            with self.assertRaisesRegex(
                DirichletFormulaicQMajorServiceError,
                "footer",
            ):
                replay_formulaic_service_stream(truncated, schedule)

            rebound = bytearray(original)
            row_payload = first_frame + FRAME_HEADER.size + 64
            rebound[row_payload] ^= 1
            rebound_path = root / "rebound.bin"
            rebound_path.write_bytes(rebound)
            with self.assertRaisesRegex(
                DirichletFormulaicQMajorServiceError,
                "external pin",
            ):
                replay_formulaic_service_stream(
                    rebound_path,
                    schedule,
                    expected_stream_sha256=receipt[
                        "input_stream_sha256"
                    ],
                )

    def test_capability_keeps_source_and_completion_false(self) -> None:
        report = capability()
        self.assertTrue(
            report["descriptor_free_formulaic_binary_service_implemented"]
        )
        self.assertTrue(report["bounded_real_cuda_kat_implemented"])
        self.assertFalse(report["bounded_real_cuda_kat_completed"])
        self.assertEqual(
            report[
                "source_formulaic_lattice_rows_reread_and_uploaded_if_executed"
            ],
            3_637_613_167,
        )
        self.assertEqual(
            report[
                "source_formulaic_raw_lattice_transfer_bytes_if_executed"
            ],
            3_814_313_864_200_192,
        )
        self.assertFalse(
            report["preserves_tmajor_one_upload_per_physical_row"]
        )
        self.assertFalse(report["economical_production_storage_solution"])
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
            report["candidate_resident_t_shard_executor_implemented"]
        )
        self.assertFalse(report["production_run_completed"])
        self.assertFalse(report["full_source_schedule_accepted"])
        self.assertFalse(report["source_scale_run_completed"])
        self.assertFalse(report["trusted_execution_attested"])
        self.assertFalse(report["zero_completeness_claimed"])
        self.assertFalse(report["external_atom_discharged"])


@unittest.skipUnless(
    SEEDED_RUNNER.is_file()
    and ALLCHARS_RUNNER.is_file()
    and MPFR_CHECKER.is_file(),
    "requires built seeded CUDA, all-character CUDA, and MPFR runners",
)
class DirichletFormulaicQMajorServiceCudaKat(unittest.TestCase):
    def test_real_cuda_pipe_independent_replay_and_attacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed_path = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seed_path, q_stop=max(SOURCE_QS)
            )
            schedule, input_path, receipt = _build_stream(
                root, recovery_seed_sha256=seed_sha256
            )
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(schedule.raw)
            cuda_summary = root / "cuda-summary.json"
            transform_summary = root / "transform-summary.json"
            input_capture = root / "TGDAFFI1.capture.bin"
            tee_receipt = root / "TGDAFFI1.tee.receipt.json"
            transform_output = root / "TGDAFFO1.capture.bin"
            service_stderr = root / "service.stderr"
            tee_stderr = root / "tee.stderr"
            transform_stderr = root / "transform.stderr"

            with (
                input_path.open("rb") as formulaic_input,
                service_stderr.open("wb") as service_error,
                tee_stderr.open("wb") as tee_error,
                transform_stderr.open("wb") as transform_error,
                transform_output.open("wb") as transform_output_handle,
            ):
                service = subprocess.Popen(
                    [
                        str(SEEDED_RUNNER),
                        "--formulaic-qmajor-service",
                        str(seed_path),
                        seed_sha256,
                        str(schedule_path),
                        str(receipt["plan_sha256"]),
                        str(cuda_summary),
                        "0",
                        "--allow-prefix-kat",
                    ],
                    stdin=formulaic_input,
                    stdout=subprocess.PIPE,
                    stderr=service_error,
                )
                assert service.stdout is not None
                tee = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "tools/tg_bounded_stream_tee.py"),
                        str(input_capture),
                        str(tee_receipt),
                        str(64 * 1024 * 1024),
                        "TGDAFFI1",
                        schedule.manifest_sha256,
                    ],
                    stdin=service.stdout,
                    stdout=subprocess.PIPE,
                    stderr=tee_error,
                )
                service.stdout.close()
                assert tee.stdout is not None
                transform = subprocess.Popen(
                    [
                        str(ALLCHARS_RUNNER),
                        "--bounded-scheduled-multiq-framed-service",
                        "1",
                        "512",
                        str(schedule_path),
                        str(transform_summary),
                        "0",
                    ],
                    stdin=tee.stdout,
                    stdout=transform_output_handle,
                    stderr=transform_error,
                )
                tee.stdout.close()
                transform_code = transform.wait(timeout=120)
                tee_code = tee.wait(timeout=30)
                service_code = service.wait(timeout=30)
            diagnostics = (
                service_stderr.read_text(errors="replace")
                + tee_stderr.read_text(errors="replace")
                + transform_stderr.read_text(errors="replace")
            )
            self.assertEqual(
                (service_code, tee_code, transform_code),
                (0, 0, 0),
                diagnostics,
            )

            parsed = replay_formulaic_service_stream(
                input_path,
                schedule,
                expected_stream_sha256=receipt["input_stream_sha256"],
            )
            summary = validate_formulaic_cuda_summary(
                cuda_summary, parsed, input_capture
            )
            self.assertEqual(summary["descriptor_reconstruction_count"], 4)
            self.assertEqual(summary["descriptor_h2d_upload_count"], 4)
            self.assertEqual(summary["lattice_h2d_upload_count"], 8)
            self.assertEqual(summary["plan_sha256"], receipt["plan_sha256"])
            self.assertEqual(
                summary["input_stream_sha256"],
                receipt["input_stream_sha256"],
            )

            legacy_capture = bytearray()
            for frame_index, frame in enumerate(parsed.frames):
                legacy_input = root / f"legacy-{frame_index}.TGDLQB2"
                legacy_output = root / f"legacy-{frame_index}.TGDAFFI1"
                legacy_input.write_bytes(_legacy_seeded_frame_bytes(frame))
                legacy = subprocess.run(
                    [
                        str(SEEDED_RUNNER),
                        str(seed_path),
                        seed_sha256,
                        str(legacy_input),
                        str(legacy_output),
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
                    legacy.returncode,
                    0,
                    legacy.stderr.decode(errors="replace"),
                )
                legacy_capture.extend(legacy_output.read_bytes())
            self.assertEqual(
                bytes(legacy_capture),
                input_capture.read_bytes(),
                "formulaic cached service changed the legacy seeded CUDA bytes",
            )

            arithmetic_replay = replay_formulaic_cuda_arithmetic(
                parsed,
                seed_path,
                input_capture,
                expected_output_sha256=summary["output_stream_sha256"],
                maximum_values_per_frame=2,
                independent_arb_factor_precision_bits=(
                    320 if PINNED_FLINT_AVAILABLE else None
                ),
            )
            self.assertTrue(
                arithmetic_replay[
                    "directed_binary64_cuda_endpoints_matched"
                ]
            )
            self.assertEqual(
                arithmetic_replay["sampled_output_value_count"], 16
            )
            self.assertFalse(arithmetic_replay["source_scale_run"])
            self.assertFalse(
                arithmetic_replay["external_atom_discharged"]
            )
            self.assertFalse(
                arithmetic_replay["production_run_completed"]
            )

            input_raw = input_capture.read_bytes()
            output_raw = transform_output.read_bytes()
            transform_value = json.loads(transform_summary.read_bytes())
            validate_scheduled_multiq_framed_summary(
                transform_value,
                manifest=schedule_path,
                input_stream=input_raw,
                output_stream=output_raw,
            )
            self.assertEqual(
                _mpfr_replay_transform_frames(
                    input_raw,
                    output_raw,
                    checker=MPFR_CHECKER,
                    precision=192,
                    process_timeout_seconds=60,
                ),
                8,
            )

            malformed = bytearray(input_path.read_bytes())
            first_frame = SERVICE_HEADER.size + LANE_RECORD.size
            fields = list(FRAME_HEADER.unpack_from(malformed, first_frame))
            fields[4] = 10_001
            FRAME_HEADER.pack_into(malformed, first_frame, *fields)
            malformed_path = root / "malformed.bin"
            malformed_path.write_bytes(malformed)
            rejected_summary = root / "rejected-summary.json"
            rejected = subprocess.run(
                [
                    str(SEEDED_RUNNER),
                    "--formulaic-qmajor-service",
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    str(receipt["plan_sha256"]),
                    str(rejected_summary),
                    "0",
                    "--allow-prefix-kat",
                ],
                input=malformed,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, b"")
            self.assertFalse(rejected_summary.exists())

            alternate_path = root / "alternate-plan.bin"
            write_formulaic_service_stream(
                alternate_path,
                schedule,
                (LaneRange(0, 0, 1), LaneRange(1, 1, 2)),
                recovery_seed_sha256=seed_sha256,
                source_contract_sha256="b" * 64,
                lattice_source_sha256="c" * 64,
                sidecar_source_sha256="d" * 64,
                row_provider=lambda _target, t_index: _synthetic_row(
                    t_index
                ),
                sidecar_provider=_wide_sidecars,
                maximum_batch_count=1,
            )
            alternate = bytearray(alternate_path.read_bytes())
            alternate_header = list(SERVICE_HEADER.unpack_from(alternate))
            alternate_header[15] = bytes.fromhex(
                str(receipt["plan_sha256"])
            )
            SERVICE_HEADER.pack_into(alternate, 0, *alternate_header)
            plan_rejected_summary = root / "plan-rejected-summary.json"
            plan_rejected = subprocess.run(
                [
                    str(SEEDED_RUNNER),
                    "--formulaic-qmajor-service",
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    str(receipt["plan_sha256"]),
                    str(plan_rejected_summary),
                    "0",
                    "--allow-prefix-kat",
                ],
                input=alternate,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(plan_rejected.returncode, 0)
            self.assertIn(
                b"canonical Python plan digest differs",
                plan_rejected.stderr,
            )
            self.assertEqual(plan_rejected.stdout, b"")
            self.assertFalse(plan_rejected_summary.exists())


if __name__ == "__main__":
    unittest.main()
