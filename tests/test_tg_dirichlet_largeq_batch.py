# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.tg_dirichlet_residue_composition_fixture import (  # noqa: E402
    write_job,
    write_structural_certified_job,
)
from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    canonical_residue_order,
)
from tg_verifier.dirichlet_largeq_batch import (  # noqa: E402
    CERTIFIED_RESIDUE_BOX,
    DirichletLargeQBatchError,
    FRAME_FACTOR,
    INPUT_HEADER,
    INPUT_MAGIC,
    RESIDUE_DESCRIPTOR,
    capability,
    pack_input,
    source_work,
    write_job_from_composition_job,
)
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    LATTICE_CELL,
    LATTICE_ROWS,
    TAYLOR_COLUMNS,
    canonical_lattice_row,
)


class DirichletLargeQBatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _synthetic_job(self) -> Path:
        composition, _ = write_job(
            self.root / "composition", t_indices=(127, 128)
        )
        job = self.root / "batch-job.json"
        write_job_from_composition_job(composition, job, certified=False)
        return job

    def test_binary_layout_and_packed_canonical_order(self) -> None:
        output = self.root / "input.bin"
        receipt = pack_input(
            self._synthetic_job(), output, allow_synthetic_kat=True
        )
        raw = output.read_bytes()
        header = INPUT_HEADER.unpack_from(raw)
        self.assertEqual(header[0], INPUT_MAGIC)
        self.assertEqual(header[2], 10_001)
        self.assertEqual(header[6], 2)
        self.assertEqual(header[9], 9792)
        self.assertEqual(header[14], 2 * 9792)
        self.assertEqual(receipt["value_count"], 19_584)
        offset = INPUT_HEADER.size
        residues = canonical_residue_order(10_001)
        for index in range(32):
            self.assertEqual(
                RESIDUE_DESCRIPTOR.unpack_from(
                    raw, offset + index * RESIDUE_DESCRIPTOR.size
                ),
                (residues[index], canonical_lattice_row(10_001, residues[index])),
            )
        expected_size = (
            INPUT_HEADER.size
            + 9792 * RESIDUE_DESCRIPTOR.size
            + 2 * FRAME_FACTOR.size
            + 2 * LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
            + 2 * 9792 * CERTIFIED_RESIDUE_BOX.size
        )
        self.assertEqual(len(raw), expected_size)
        self.assertFalse(receipt["decisions"]["cuda_transcendentals_required"])
        self.assertFalse(receipt["decisions"]["materialized_TGDLATO1_required"])

    def test_synthetic_job_requires_explicit_authorization(self) -> None:
        output = self.root / "unauthorized.bin"
        with self.assertRaisesRegex(
            DirichletLargeQBatchError, "explicit KAT authorization"
        ):
            pack_input(self._synthetic_job(), output)
        self.assertFalse(output.exists())

    def test_structural_certified_bundle_drops_taylor_output(self) -> None:
        composition, _ = write_structural_certified_job(
            self.root / "certified"
        )
        job = self.root / "certified-batch.json"
        converted = write_job_from_composition_job(
            composition, job, certified=True
        )
        self.assertNotIn("lattice_output", converted["frames"][0])
        self.assertNotIn("lattice_stage_receipt", converted["frames"][0])
        receipt = pack_input(job, self.root / "certified.bin")
        self.assertEqual(
            receipt["classification"],
            "certified_box_input_for_directed_cuda_batch_only",
        )
        self.assertTrue(
            receipt["decisions"]["higher_precision_certificate_replay_verified"]
        )

    def test_recovery_hash_tamper_fails_before_output(self) -> None:
        job = self._synthetic_job()
        value = json.loads(job.read_text("ascii"))
        recovery = job.parent / value["frames"][0]["finite_recovery"]["path"]
        with recovery.open("r+b") as target:
            target.seek(80)
            byte = target.read(1)
            target.seek(80)
            target.write(bytes([byte[0] ^ 1]))
        output = self.root / "tampered.bin"
        with self.assertRaisesRegex(DirichletLargeQBatchError, "hash or length"):
            pack_input(job, output, allow_synthetic_kat=True)
        self.assertFalse(output.exists())

    def test_capability_does_not_claim_transcendental_or_atom_closure(self) -> None:
        report = capability()
        self.assertEqual(report["cuda_transcendental_calls"], 0)
        self.assertFalse(report["finite_recovery_gpu_transcendental_implementation"])
        self.assertFalse(report["external_atom_discharged"])
        self.assertFalse(report["production_ready_for_full_atom"])

    def test_source_work_pins_launch_and_io_boundary(self) -> None:
        work = source_work(batch_size=64)
        self.assertEqual(work["fused_batch_kernel_launches"], 76_770_217)
        self.assertEqual(work["q_persistent_process_invocations"], 390_000)
        self.assertEqual(work["process_invocations_avoided"], 4_900_661_274)
        self.assertEqual(work["kernel_launches_avoided"], 4_824_281_057)
        self.assertEqual(work["residue_compositions"], 327_089_206_283_008)
        self.assertEqual(
            work["input_bytes"]["certified_hurwitz_lattice_cells"],
            5_139_124_740_685_824,
        )
        self.assertEqual(
            work["input_bytes"]["certified_tail_plus_finite_recovery_boxes"],
            13_083_568_251_320_320,
        )
        self.assertEqual(work["input_bytes"]["total"], 18_263_933_424_590_240)
        self.assertGreater(work["kernel_launch_reduction_factor"], 63.8)


if __name__ == "__main__":
    unittest.main()
