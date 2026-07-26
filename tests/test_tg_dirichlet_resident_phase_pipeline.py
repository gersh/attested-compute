# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.test_tg_dirichlet_resident_qmajor_stream import (
    _write_stream_inputs,
)
from tests.test_tg_dirichlet_resident_scheduled_pipeline import (
    _controls,
)
from tests.test_tg_dirichlet_tmajor_cuda_block import (
    _write_structural_seed_artifact,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
)
from tg_verifier.dirichlet_resident_phase_pipeline import (
    capability,
    run_resident_fixed_q_phase_pipeline,
)
from tg_verifier.dirichlet_resident_qmajor_stream import (
    BOUNDED_PROJECTION_COVERAGE,
    build_stream_plan,
)
from tg_verifier.dirichlet_root_catalog import (
    root_artifact_filename,
    root_receipt_filename,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    DirichletStreamConsumerError,
    combine_compact_state_summaries,
    validate_compact_state_summary,
)


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


@unittest.skipUnless(
    PINNED_PYTHON.is_file()
    and STREAM_RUNNER.is_file()
    and ALLCHARS.is_file()
    and MPFR_CHECKER.is_file(),
    "requires pinned FLINT and built CUDA/MPFR Dirichlet runners",
)
class DirichletResidentPhasePipelineKat(unittest.TestCase):
    def _roots(self, root: Path) -> tuple[Path, Path]:
        roots = root / "roots"
        roots.mkdir()
        worker = ROOT / "tests/tg_dirichlet_root_number_kat_worker.py"
        additive = root / "additive.bin"
        additive_receipt = root / "additive.receipt.json"
        transform = root / "root-transform.bin"
        subprocess.run(
            [
                str(PINNED_PYTHON),
                str(worker),
                "additive-input",
                str(additive),
                str(additive_receipt),
                "--q",
                "10001",
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
        artifact = roots / root_artifact_filename(10_001)
        receipt = roots / root_receipt_filename(10_001)
        subprocess.run(
            [
                str(PINNED_PYTHON),
                str(worker),
                "consume",
                str(transform),
                str(artifact),
                str(receipt),
                "--q",
                "10001",
                "--additive-receipt",
                str(additive_receipt),
                "--precision",
                "192",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return artifact, receipt

    def test_two_real_phases_merge_to_whole_phase_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(
                build_schedule_manifest_bytes(
                    (ScheduleRecord(10_001, 4),)
                )
            )
            schedule = parse_schedule_manifest(schedule_path)
            seeds = root / "seeds.bin"
            seed_sha = _write_structural_seed_artifact(
                seeds, q_stop=10_001
            )
            root_artifact, root_receipt = self._roots(root)

            def run_slice(
                label: str, first: int, stop: int
            ) -> tuple[dict[str, object], dict[str, object]]:
                work = root / label
                work.mkdir()
                plan = build_stream_plan(
                    schedule,
                    phase_index=0,
                    coverage_mode=BOUNDED_PROJECTION_COVERAGE,
                    loaded_first_t_index=first,
                    loaded_t_index_stop_exclusive=stop,
                )
                controls = _controls(
                    work / "controls.ndjson", schedule, plan
                )
                rows, row_record, sidecars, sidecar_record = (
                    _write_stream_inputs(
                        work,
                        schedule,
                        plan,
                        recovery_seed_sha256=seed_sha,
                    )
                )
                receipt = run_resident_fixed_q_phase_pipeline(
                    consumer_controls=controls,
                    schedule_manifest=schedule_path,
                    plan=plan,
                    recovery_seed_artifact=seeds,
                    recovery_seed_sha256=seed_sha,
                    row_artifact=rows,
                    row_artifact_sha256=str(
                        row_record["input_sha256"]
                    ),
                    sidecar_artifact=sidecars,
                    sidecar_artifact_sha256=str(
                        sidecar_record["input_sha256"]
                    ),
                    resident_runner=STREAM_RUNNER,
                    allchars_runner=ALLCHARS,
                    consumer_python=PINNED_PYTHON,
                    consumer_tool=(
                        ROOT
                        / "tests/tg_dirichlet_stream_consumer_kat_worker.py"
                    ),
                    root_artifact=root_artifact,
                    root_receipt=root_receipt,
                    output_directory=work / "pipeline",
                    pipeline_receipt=work / "pipeline.receipt.json",
                    process_timeout_seconds=180,
                    allow_prefix_kat=True,
                )
                state = json.loads(
                    Path(
                        receipt["summaries"]["compact_state"]["path"]
                    ).read_bytes()
                )
                validate_compact_state_summary(state)
                return receipt, state

            left_receipt, left = run_slice("left", 0, 2)
            right_receipt, right = run_slice("right", 2, 4)
            whole_receipt, whole = run_slice("whole", 0, 4)
            merged = combine_compact_state_summaries(left, right)
            validate_compact_state_summary(merged)

            self.assertEqual(
                merged["character_states"], whole["character_states"]
            )
            self.assertEqual(
                merged["sign_change_lower_bound"],
                whole["sign_change_lower_bound"],
            )
            self.assertEqual(
                merged["ambiguity_sample_count"],
                whole["ambiguity_sample_count"],
            )
            self.assertEqual(
                merged["context"]["first_t_numerator"],
                whole["context"]["first_t_numerator"],
            )
            self.assertEqual(
                merged["context"]["stop_t_numerator"],
                whole["context"]["stop_t_numerator"],
            )
            for receipt in (
                left_receipt,
                right_receipt,
                whole_receipt,
            ):
                self.assertFalse(
                    receipt["raw_transform_streams_materialized"]
                )
                self.assertFalse(
                    receipt[
                        "touching_vs_wide_unresolved_distinguished"
                    ]
                )
                self.assertFalse(receipt["turing_counts_realized"])
                self.assertFalse(
                    receipt["source_scale_run_completed"]
                )
                self.assertFalse(receipt["external_atom_discharged"])

            gapped = dict(right)
            gapped["context"] = dict(right["context"])
            gapped["context"]["first_t_numerator"] += 5
            body = dict(gapped)
            body.pop("state_sha256")
            from tg_verifier.dirichlet_stream_zero_consumer import (
                canonical_json_bytes,
            )
            import hashlib

            gapped["state_sha256"] = hashlib.sha256(
                canonical_json_bytes(body)
            ).hexdigest()
            with self.assertRaises(DirichletStreamConsumerError):
                combine_compact_state_summaries(left, gapped)

    def test_capability_keeps_unrealized_semantics_false(self) -> None:
        report = capability()
        self.assertTrue(
            report[
                "direct_resident_qmajor_to_fixed_q_fft_to_compact_state"
            ]
        )
        self.assertFalse(
            report["raw_transform_stream_materialization_required"]
        )
        for field in (
            "touching_vs_wide_unresolved_distinguished",
            "turing_counts_realized",
            "multiplicity_preserving_zero_lower_bound_realized",
            "source_phase_execution_completed",
            "source_scale_run_completed",
            "production_run_completed",
            "trusted_execution_attested",
            "zero_completeness_claimed",
            "external_atom_discharged",
        ):
            self.assertFalse(report[field], field)


if __name__ == "__main__":
    unittest.main()
