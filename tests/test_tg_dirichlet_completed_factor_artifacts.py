# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tg_verifier.dirichlet_completed_factor_artifacts import (
    CHECKPOINT_HEADER,
    DirichletCompletedFactorArtifactError,
    GAMMA_HEADER,
    STEP_HEADER,
    parse_checkpoint_artifact,
    parse_gamma_artifact,
    parse_step_artifact,
    source_storage_projection,
    write_bounded_arb_artifacts,
    write_synthetic_unit_artifacts,
)

try:
    import flint
except ImportError:
    flint = None


class DirichletCompletedFactorArtifactsTest(unittest.TestCase):
    def test_synthetic_three_file_bundle_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = write_synthetic_unit_artifacts(
                root, q=7, first_t_index=0, sample_count=8
            )
            gamma = parse_gamma_artifact(
                root / "gamma.bin",
                expected_sha256=report["gamma_sha256"],
            )
            steps = parse_step_artifact(
                root / "steps.bin",
                expected_sha256=report["step_sha256"],
            )
            checkpoints = parse_checkpoint_artifact(
                root / "checkpoints.bin",
                expected_sha256=report["checkpoint_sha256"],
            )
            self.assertEqual(gamma.sample_count, 8)
            self.assertEqual(len(gamma.disks), 16)
            self.assertEqual(len(steps.disks), 1)
            self.assertEqual(len(checkpoints.records), 1)
            self.assertEqual(checkpoints.records[0].q, 7)
            self.assertEqual(checkpoints.records[0].sample_count, 8)
            self.assertEqual(len(checkpoints.records[0].checkpoints), 1)
            self.assertEqual(
                checkpoints.gamma_artifact_sha256,
                gamma.artifact_sha256,
            )
            self.assertEqual(
                checkpoints.step_artifact_sha256,
                steps.artifact_sha256,
            )
            self.assertEqual(
                (root / "gamma.bin").stat().st_size,
                GAMMA_HEADER.size + 16 * 24,
            )
            self.assertEqual(
                (root / "steps.bin").stat().st_size,
                STEP_HEADER.size + 24,
            )
            self.assertEqual(
                (root / "checkpoints.bin").stat().st_size,
                CHECKPOINT_HEADER.size + 16 + 24,
            )
            self.assertFalse(report["source_range_qualified"])
            self.assertFalse(report["external_atom_discharged"])

    def test_mutation_and_nonfinite_disks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = write_synthetic_unit_artifacts(
                root, q=7, first_t_index=0, sample_count=8
            )
            gamma_path = root / "gamma.bin"
            raw = bytearray(gamma_path.read_bytes())
            raw[-1] ^= 1
            gamma_path.write_bytes(raw)
            with self.assertRaises(
                DirichletCompletedFactorArtifactError,
                msg="external digest must bind every disk byte",
            ):
                parse_gamma_artifact(
                    gamma_path,
                    expected_sha256=report["gamma_sha256"],
                )

            step_path = root / "steps.bin"
            step_raw = bytearray(step_path.read_bytes())
            # Radius is the third double in the first disk.
            step_raw[STEP_HEADER.size + 16 : STEP_HEADER.size + 24] = (
                (0x7FF8000000000000).to_bytes(8, "little")
            )
            step_path.write_bytes(step_raw)
            with self.assertRaises(
                DirichletCompletedFactorArtifactError,
                msg="nonfinite disk must fail even without an expected SHA",
            ):
                parse_step_artifact(step_path)

    def test_source_projection_is_compact_and_not_promoted(self) -> None:
        projection = source_storage_projection()
        self.assertEqual(projection["gamma_artifact_bytes"], 6_143_552)
        self.assertEqual(projection["step_catalog_bytes"], 7_020_144)
        self.assertEqual(
            projection["phase_checkpoint_count"], 2_351_903
        )
        self.assertEqual(
            projection["phase_checkpoint_artifact_bytes"], 88_670_664
        )
        self.assertEqual(
            projection["total_artifact_bytes"], 101_834_360
        )
        self.assertEqual(
            projection["naive_q_by_t_factor_disk_bytes"],
            174_605_432_016,
        )
        self.assertGreater(
            projection["naive_q_by_t_factor_disk_bytes"]
            // projection["total_artifact_bytes"],
            1_700,
        )
        self.assertFalse(projection["source_artifacts_generated"])
        self.assertFalse(projection["source_range_qualified"])
        self.assertFalse(projection["external_atom_discharged"])

    def test_artifacts_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_synthetic_unit_artifacts(
                root, q=7, first_t_index=0, sample_count=8
            )
            with self.assertRaises(
                DirichletCompletedFactorArtifactError,
                msg="a second producer must not replace signed inputs",
            ):
                write_synthetic_unit_artifacts(
                    root, q=7, first_t_index=0, sample_count=8
                )

    @unittest.skipUnless(
        flint is not None,
        "requires pinned python-flint 0.9.0 / FLINT 3.6.0",
    )
    def test_real_arb_bounded_producer_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = write_bounded_arb_artifacts(
                root,
                q=7,
                first_t_index=0,
                sample_count=8,
                precision=384,
                checkpoint_span=4,
            )
            gamma = parse_gamma_artifact(
                root / "gamma.bin",
                expected_sha256=report["gamma_sha256"],
            )
            steps = parse_step_artifact(
                root / "steps.bin",
                expected_sha256=report["step_sha256"],
            )
            checkpoints = parse_checkpoint_artifact(
                root / "checkpoints.bin",
                expected_sha256=report["checkpoint_sha256"],
            )
            self.assertEqual(
                gamma.producer_identity_sha256,
                report["producer_identity_sha256"],
            )
            self.assertEqual(len(gamma.disks), 16)
            self.assertEqual(len(steps.disks), 1)
            self.assertEqual(
                len(checkpoints.records[0].checkpoints), 2
            )
            self.assertEqual(
                checkpoints.gamma_artifact_sha256,
                gamma.artifact_sha256,
            )
            self.assertEqual(
                checkpoints.step_artifact_sha256,
                steps.artifact_sha256,
            )
            self.assertFalse(report["source_range_qualified"])


if __name__ == "__main__":
    unittest.main()
