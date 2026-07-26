# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_tg_dirichlet_resident_qmajor_stream import (
    _write_stream_inputs,
)
from tests.test_tg_dirichlet_tmajor_cuda_block import (
    _write_structural_seed_artifact,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (
    DirichletAllCharsQSchedulerError,
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
    phase_schedule_projection,
    validate_scheduled_multiq_framed_summary_commitments,
)
from tg_verifier.dirichlet_resident_qmajor_stream import (
    BOUNDED_PROJECTION_COVERAGE,
    build_stream_plan,
    iter_stream_targets,
)
from tg_verifier.dirichlet_resident_scheduled_pipeline import (
    DirichletResidentScheduledPipelineError,
    capability,
    run_resident_scheduled_pipeline,
    validate_resident_control_alignment,
    validate_resident_multiq_phase_control_alignment,
)
from tg_verifier.dirichlet_root_catalog import (
    root_artifact_filename,
    root_receipt_filename,
)
from tg_verifier.dirichlet_root_number_stage import ROOT_ALGORITHM_ID
from tg_verifier.dirichlet_stream_zero_consumer import (
    make_control,
    validate_phase_compact_state_bundle,
)
from tg_verifier.dirichlet_residue_composition import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]
PINNED_PYTHON = Path("/tmp/tg-flint-venv/bin/python")
STREAM_RUNNER = Path(
    os.environ.get(
        "TG_DIRICHLET_RESIDENT_STREAM_BINARY",
        ROOT
        / "build/tg-production-kat/"
        "sparkinterval-tg-dirichlet-resident-qmajor-stream",
    )
)
ALLCHARS = (
    ROOT / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars"
)
MPFR_CHECKER = (
    ROOT
    / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr"
)


def _upstream() -> dict[str, str]:
    return {
        "all_character_transform_input_sha256": "1" * 64,
        "finite_addback_receipt_sha256": "2" * 64,
        "lattice_tail_receipt_sha256": "3" * 64,
        "residue_adapter_receipt_sha256": "4" * 64,
    }


def _controls(path: Path, schedule: object, plan: object) -> Path:
    rows = []
    for frame_index, target in enumerate(
        iter_stream_targets(schedule, plan)
    ):
        rows.append(
            canonical_json_bytes(
                make_control(
                    frame_index=frame_index,
                    q=target.q,
                    batch_count=target.batch_count,
                    first_t_numerator=target.first_t_index * 5,
                    t_denominator=64,
                    t_step_numerator=5,
                    upstream_receipts=_upstream(),
                    root_number_mode=ROOT_ALGORITHM_ID,
                )
            )
        )
    path.write_bytes(b"".join(rows))
    return path


def _root_catalog(
    root: Path, moduli: tuple[int, ...]
) -> tuple[Path, str, Path]:
    roots = root / "roots"
    roots.mkdir()
    root_worker = ROOT / "tests/tg_dirichlet_root_number_kat_worker.py"
    for q in moduli:
        additive = root / f"additive-{q}.bin"
        additive_receipt = root / f"additive-{q}.receipt.json"
        transform = root / f"root-transform-{q}.bin"
        subprocess.run(
            [
                str(PINNED_PYTHON),
                str(root_worker),
                "additive-input",
                str(additive),
                str(additive_receipt),
                "--q",
                str(q),
                "--precision",
                "192",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                str(MPFR_CHECKER),
                "compute",
                str(additive),
                str(transform),
                "192",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                str(PINNED_PYTHON),
                str(root_worker),
                "consume",
                str(transform),
                str(roots / root_artifact_filename(q)),
                str(roots / root_receipt_filename(q)),
                "--q",
                str(q),
                "--additive-receipt",
                str(additive_receipt),
                "--precision",
                "192",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    catalog = root / "root-catalog.ndjson"
    catalog_result = subprocess.run(
        [
            str(PINNED_PYTHON),
            str(ROOT / "tools/tg_dirichlet_root_catalog.py"),
            "build",
            str(roots),
            str(catalog),
            "--q-start",
            str(min(moduli)),
            "--q-stop",
            str(max(moduli)),
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    return (
        catalog,
        json.loads(catalog_result.stdout)["catalog_sha256"],
        roots,
    )


class DirichletResidentScheduledPipelineStructuralTest(unittest.TestCase):
    def _fixture(self, root: Path):
        schedule_path = root / "schedule.bin"
        schedule_path.write_bytes(
            build_schedule_manifest_bytes(
                (
                    ScheduleRecord(10_001, 65),
                    ScheduleRecord(10_003, 2),
                )
            )
        )
        schedule = parse_schedule_manifest(schedule_path)
        plan = build_stream_plan(
            schedule,
            phase_index=0,
            coverage_mode=BOUNDED_PROJECTION_COVERAGE,
            loaded_first_t_index=0,
            loaded_t_index_stop_exclusive=65,
        )
        controls = _controls(root / "controls.ndjson", schedule, plan)
        return schedule_path, schedule, plan, controls

    def test_exact_target_control_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule_path, schedule, plan, controls = self._fixture(root)
            inventory = validate_resident_control_alignment(
                controls,
                schedule_manifest_path=schedule_path,
                plan=plan,
            )
            self.assertEqual(inventory.schedule, schedule)
            self.assertEqual(inventory.frame_count, 3)
            self.assertEqual(inventory.slice_count, 67)
            self.assertEqual(inventory.value_count, plan.value_count)
            self.assertEqual(len(inventory.control_target_chain_sha256), 64)

    def test_reordered_substituted_and_incomplete_controls_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule_path, _schedule, plan, controls = self._fixture(root)
            original = controls.read_bytes().splitlines(keepends=True)

            reordered = []
            for index, raw in enumerate(reversed(original)):
                value = json.loads(raw)
                value["frame_index"] = index
                reordered.append(canonical_json_bytes(value))
            controls.write_bytes(b"".join(reordered))
            with self.assertRaisesRegex(
                DirichletResidentScheduledPipelineError,
                "differs from its q-major target",
            ):
                validate_resident_control_alignment(
                    controls,
                    schedule_manifest_path=schedule_path,
                    plan=plan,
                )

            controls.write_bytes(b"".join(original[:-1]))
            with self.assertRaisesRegex(
                DirichletResidentScheduledPipelineError,
                "target counts differ",
            ):
                validate_resident_control_alignment(
                    controls,
                    schedule_manifest_path=schedule_path,
                    plan=plan,
                )

            substituted = json.loads(original[0])
            substituted["batch_count"] -= 1
            controls.write_bytes(
                canonical_json_bytes(substituted) + b"".join(original[1:])
            )
            with self.assertRaisesRegex(
                DirichletResidentScheduledPipelineError,
                "differs from its q-major target",
            ):
                validate_resident_control_alignment(
                    controls,
                    schedule_manifest_path=schedule_path,
                    plan=plan,
                )

    def test_phase_not_covering_t_zero_through_schedule_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule_path, schedule, _plan, _controls_path = self._fixture(
                root
            )
            partial = build_stream_plan(
                schedule,
                phase_index=0,
                coverage_mode=BOUNDED_PROJECTION_COVERAGE,
                loaded_first_t_index=1,
                loaded_t_index_stop_exclusive=65,
            )
            partial_controls = _controls(
                root / "partial.ndjson", schedule, partial
            )
            with self.assertRaisesRegex(
                DirichletResidentScheduledPipelineError,
                "does not exactly cover",
            ):
                validate_resident_control_alignment(
                    partial_controls,
                    schedule_manifest_path=schedule_path,
                    plan=partial,
                )

    def test_multiq_phase_alignment_skips_no_active_control(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule_path, schedule, _plan, _controls_path = self._fixture(
                root
            )
            phase = build_stream_plan(
                schedule,
                phase_index=0,
                coverage_mode=BOUNDED_PROJECTION_COVERAGE,
                loaded_first_t_index=1,
                loaded_t_index_stop_exclusive=3,
            )
            phase_controls = _controls(
                root / "phase.ndjson", schedule, phase
            )
            inventory = validate_resident_multiq_phase_control_alignment(
                phase_controls,
                schedule_manifest_path=schedule_path,
                plan=phase,
            )
            self.assertEqual(inventory.frame_count, 2)
            self.assertEqual(inventory.slice_count, 3)
            self.assertEqual(inventory.first_q, 10_001)
            self.assertEqual(inventory.last_q, 10_003)

    def test_capability_keeps_source_and_trust_boundaries_false(self) -> None:
        report = capability()
        self.assertTrue(
            report[
                "resident_qmajor_to_persistent_allchars_direct_pipe"
            ]
        )
        self.assertFalse(
            report["raw_transform_stream_materialization_required"]
        )
        self.assertTrue(
            report["persistent_multiq_phase_arb_oracle_integrated"]
        )
        self.assertTrue(
            report[
                "TGDAFFO1_host_transfer_prohibited_in_source_production"
            ]
        )
        for field in (
            "phase_arb_oracle_is_source_production",
            "same_cuda_address_space_completed_l_reduction_integrated",
            "full_source_t_phase_state_carry_integrated",
            "full_source_formulaic_control_stream_integrated",
            "bounded_independent_raw_stream_replay_completed",
            "source_phase_execution_completed",
            "source_scale_run_completed",
            "production_run_completed",
            "trusted_execution_attested",
            "completed_l_zero_state_validated",
            "zero_completeness_claimed",
            "external_atom_discharged",
        ):
            self.assertFalse(report[field], field)


@unittest.skipUnless(
    PINNED_PYTHON.is_file()
    and STREAM_RUNNER.is_file()
    and ALLCHARS.is_file()
    and MPFR_CHECKER.is_file(),
    "requires pinned FLINT and built CUDA/MPFR Dirichlet runners",
)
class DirichletResidentScheduledPipelineProcessKat(unittest.TestCase):
    def test_direct_pipe_reaches_completed_l_without_materialization(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(
                build_schedule_manifest_bytes(
                    (ScheduleRecord(10_001, 1),)
                )
            )
            schedule = parse_schedule_manifest(schedule_path)
            plan = build_stream_plan(
                schedule,
                phase_index=0,
                coverage_mode=BOUNDED_PROJECTION_COVERAGE,
                loaded_first_t_index=0,
                loaded_t_index_stop_exclusive=1,
            )
            controls = _controls(
                root / "consumer.ndjson", schedule, plan
            )
            seeds = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seeds, q_stop=10_001
            )
            rows, row_receipt, sidecars, sidecar_receipt = (
                _write_stream_inputs(
                    root,
                    schedule,
                    plan,
                    recovery_seed_sha256=seed_sha256,
                )
            )

            catalog, catalog_sha256, roots = _root_catalog(
                root, (10_001,)
            )

            output = root / "pipeline"
            receipt = run_resident_scheduled_pipeline(
                consumer_controls=controls,
                schedule_manifest=schedule_path,
                plan=plan,
                recovery_seed_artifact=seeds,
                recovery_seed_sha256=seed_sha256,
                row_artifact=rows,
                row_artifact_sha256=str(
                    row_receipt["input_sha256"]
                ),
                sidecar_artifact=sidecars,
                sidecar_artifact_sha256=str(
                    sidecar_receipt["input_sha256"]
                ),
                resident_runner=STREAM_RUNNER,
                allchars_runner=ALLCHARS,
                consumer_python=PINNED_PYTHON,
                consumer_tool=(
                    ROOT
                    / "tests/tg_dirichlet_stream_consumer_kat_worker.py"
                ),
                root_catalog=catalog,
                root_catalog_sha256=catalog_sha256,
                root_catalog_directory=roots,
                output_directory=output,
                pipeline_receipt=root / "pipeline.receipt.json",
                precision=192,
                process_timeout_seconds=180,
                allow_prefix_kat=True,
            )
            self.assertTrue(receipt["TGDQORD1_exact_coverage"])
            self.assertTrue(receipt["process_graph_backpressured"])
            self.assertFalse(receipt["raw_transform_streams_materialized"])
            self.assertFalse(receipt["bounded_stream_capture_or_tee_used"])
            self.assertFalse(receipt["source_scale_run_completed"])
            self.assertFalse(receipt["zero_completeness_claimed"])
            self.assertFalse(receipt["external_atom_discharged"])
            self.assertFalse((output / "TGDAFFI1.capture.bin").exists())
            self.assertFalse((output / "TGDAFFO1.capture.bin").exists())

            transform_summary = json.loads(
                Path(
                    receipt["summaries"]["transform"]["path"]
                ).read_bytes()
            )
            validate_scheduled_multiq_framed_summary_commitments(
                transform_summary,
                manifest=schedule_path,
                maximum_batch_count=64,
                input_stream_sha256=receipt[
                    "TGDAFFI1_stream_sha256"
                ],
                output_stream_sha256=receipt[
                    "TGDAFFO1_stream_sha256"
                ],
            )
            for field in (
                "frame_count",
                "radix2_butterflies",
                "order_cache_hits",
            ):
                hostile = dict(transform_summary)
                hostile[field] += 1
                with self.assertRaises(
                    DirichletAllCharsQSchedulerError,
                    msg=field,
                ):
                    validate_scheduled_multiq_framed_summary_commitments(
                        hostile,
                        manifest=schedule_path,
                        maximum_batch_count=64,
                        input_stream_sha256=receipt[
                            "TGDAFFI1_stream_sha256"
                        ],
                        output_stream_sha256=receipt[
                            "TGDAFFO1_stream_sha256"
                        ],
                    )

    def test_positive_t_multiq_phase_emits_compact_arb_oracle_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(
                build_schedule_manifest_bytes(
                    (
                        ScheduleRecord(10_001, 2),
                        ScheduleRecord(10_003, 2),
                    )
                )
            )
            schedule = parse_schedule_manifest(schedule_path)
            plan = build_stream_plan(
                schedule,
                phase_index=0,
                coverage_mode=BOUNDED_PROJECTION_COVERAGE,
                loaded_first_t_index=1,
                loaded_t_index_stop_exclusive=2,
            )
            controls = _controls(
                root / "consumer.ndjson", schedule, plan
            )
            seeds = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seeds, q_stop=10_003
            )
            rows, row_receipt, sidecars, sidecar_receipt = (
                _write_stream_inputs(
                    root,
                    schedule,
                    plan,
                    recovery_seed_sha256=seed_sha256,
                )
            )
            catalog, catalog_sha256, roots = _root_catalog(
                root, (10_001, 10_003)
            )

            output = root / "phase-pipeline"
            receipt = run_resident_scheduled_pipeline(
                consumer_controls=controls,
                schedule_manifest=schedule_path,
                plan=plan,
                recovery_seed_artifact=seeds,
                recovery_seed_sha256=seed_sha256,
                row_artifact=rows,
                row_artifact_sha256=str(row_receipt["input_sha256"]),
                sidecar_artifact=sidecars,
                sidecar_artifact_sha256=str(
                    sidecar_receipt["input_sha256"]
                ),
                resident_runner=STREAM_RUNNER,
                allchars_runner=ALLCHARS,
                consumer_python=PINNED_PYTHON,
                consumer_tool=(
                    ROOT
                    / "tests/tg_dirichlet_stream_consumer_kat_worker.py"
                ),
                root_catalog=catalog,
                root_catalog_sha256=catalog_sha256,
                root_catalog_directory=roots,
                output_directory=output,
                pipeline_receipt=root / "phase-pipeline.receipt.json",
                precision=192,
                process_timeout_seconds=180,
                allow_prefix_kat=True,
                qualification_phase_bundle=True,
            )
            self.assertFalse(receipt["TGDQORD1_exact_coverage"])
            self.assertTrue(receipt["TGDQORD1_parent_manifest_bound"])
            self.assertTrue(receipt["phase_schedule_exact_coverage"])
            self.assertTrue(receipt["arb_differential_qualification_oracle"])
            self.assertTrue(
                receipt["phase_compact_state_bundle_validated"]
            )
            self.assertFalse(
                receipt["same_cuda_address_space_reduction"]
            )
            self.assertFalse(receipt["source_performance_ready"])
            self.assertGreater(receipt["TGDAFFO1_device_to_host_bytes"], 0)

            projection = phase_schedule_projection(
                schedule_path,
                phase_plan_sha256=plan.phase_plan_sha256,
                first_t_index=plan.loaded_first_t_index,
                t_index_stop_exclusive=(
                    plan.loaded_t_index_stop_exclusive
                ),
                start_execution_q_index=plan.start_execution_q_index,
                stop_execution_q_index=plan.stop_execution_q_index,
            )
            bundle = json.loads((output / "events.ndjson").read_bytes())
            events, signs, ambiguities = (
                validate_phase_compact_state_bundle(
                    bundle, projection=projection
                )
            )
            consumer = json.loads(
                (output / "consumer-receipt.json").read_bytes()
            )
            self.assertEqual(events, consumer["event_count"])
            self.assertEqual(signs, consumer["candidate_bracket_count"])
            self.assertEqual(
                ambiguities, consumer["indeterminate_sample_count"]
            )


if __name__ == "__main__":
    unittest.main()
