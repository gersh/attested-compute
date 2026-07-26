# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_fused_stage import (  # noqa: E402
    DirichletFusedStageError,
    canonical_group_model,
    capability_report,
    group_order,
    inspect_compact_input,
    source_direct_all_character_group_points,
    write_synthetic_compact_input,
)


class DirichletFusedStageTests(unittest.TestCase):
    def test_canonical_crt_models(self) -> None:
        q8 = canonical_group_model(8)
        self.assertEqual(q8[0].modulus, 8)
        self.assertEqual(
            [(value.generator, value.order) for value in q8[0].components],
            [(7, 2), (5, 2)],
        )
        q15 = canonical_group_model(15)
        self.assertEqual([factor.modulus for factor in q15], [3, 5])
        self.assertEqual(group_order(q15), 8)
        q400k = canonical_group_model(400_000)
        self.assertEqual([factor.modulus for factor in q400k], [128, 3125])
        self.assertEqual(group_order(q400k), 160_000)

    def test_compact_batch_has_no_per_residue_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "compact.bin"
            report = write_synthetic_compact_input(
                path,
                q_values=[10_001, 400_000],
                t_index=13,
                characters_per_q=3,
            )
            inspected = inspect_compact_input(path)
            self.assertEqual(inspected["task_count"], 2)
            self.assertEqual(inspected["selected_character_count"], 6)
            self.assertFalse(inspected["per_residue_payload_present"])
            self.assertGreater(report["old_explicit_request_bytes_for_one_slice"],
                               report["size_bytes"])
            self.assertGreater(report["old_explicit_result_bytes_for_one_slice"],
                               report["size_bytes"])
            with path.open("ab") as output:
                output.write(b"x")
            with self.assertRaises(DirichletFusedStageError):
                inspect_compact_input(path)

    def test_capability_is_explicitly_not_an_fft_or_atom_proof(self) -> None:
        report = capability_report()
        self.assertFalse(report["external_atom_discharged"])
        self.assertIn("quadratic", report["complexity"]["all_phi_characters_if_misused"])
        self.assertIn(
            "source-faithful all-character CRT/Bluestein interval FFT",
            report["still_absent"],
        )

    def test_quadratic_source_work_count_is_reproducible(self) -> None:
        self.assertEqual(
            source_direct_all_character_group_points(),
            47_631_269_684_196_653_160,
        )

    def test_cli_capability(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/tg_dirichlet_fused_stage.py", "capability"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        value = json.loads(completed.stdout)
        self.assertEqual(value["algorithm_id"],
                         "platt-dirichlet-fused-character-block-v1")


if __name__ == "__main__":
    unittest.main()
