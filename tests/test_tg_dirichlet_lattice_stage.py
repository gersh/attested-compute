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

from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    SOURCE_MAX_T_INDEX,
    SOURCE_Q_T_ROWS,
    SOURCE_RESIDUE_INTERPOLATIONS,
    SOURCE_TAYLOR_TERMS,
    DirichletLatticeStageError,
    benchmark_projection,
    canonical_lattice_row,
    inspect_input,
    maximum_t_index,
    source_plan,
    write_synthetic_input,
)


class DirichletLatticeStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = source_plan()

    def test_paper_parameters_and_exact_work_counts(self) -> None:
        parameters = self.plan["paper_parameters"]
        self.assertEqual(parameters["hurwitz_lattice_rows_D"], 2048)
        self.assertEqual(parameters["taylor_degree_N"], 15)
        self.assertEqual(parameters["taylor_columns_c_0_through_N"], 16)
        work = self.plan["work"]
        self.assertEqual(work["positive_t_indices"], SOURCE_MAX_T_INDEX + 1)
        self.assertEqual(work["q_t_rows"], SOURCE_Q_T_ROWS)
        self.assertEqual(
            work["residue_interpolations"], SOURCE_RESIDUE_INTERPOLATIONS
        )
        self.assertEqual(work["taylor_complex_terms"], SOURCE_TAYLOR_TERMS)
        self.assertFalse(self.plan["atom_discharged"])
        self.assertFalse(self.plan["production_ready_for_full_atom"])

    def test_fixed_eight_shards_are_disjoint_complete_and_balanced(self) -> None:
        shards = self.plan["fixed_shards"]
        self.assertEqual(len(shards), 8)
        self.assertEqual(shards[0]["t_index_start_inclusive"], 0)
        self.assertEqual(
            shards[-1]["t_index_stop_exclusive"], SOURCE_MAX_T_INDEX + 1
        )
        for left, right in zip(shards, shards[1:]):
            self.assertEqual(
                left["t_index_stop_exclusive"],
                right["t_index_start_inclusive"],
            )
        counts = [shard["residue_interpolations"] for shard in shards]
        self.assertEqual(sum(counts), SOURCE_RESIDUE_INTERPOLATIONS)
        self.assertLess(max(counts) - min(counts), 100_000_000_000)

    def test_canonical_nearest_row_and_source_grid_endpoint(self) -> None:
        self.assertEqual(canonical_lattice_row(400_000, 1), 1)
        self.assertEqual(canonical_lattice_row(10_001, 10_000), 2048)
        self.assertEqual(maximum_t_index(10_001), SOURCE_MAX_T_INDEX)

    def test_synthetic_input_is_explicit_and_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.bin"
            written = write_synthetic_input(
                path,
                q_start=10_001,
                q_stop=10_002,
                t_index=17,
                max_items=25,
            )
            inspected = inspect_input(path)
            self.assertEqual(written["item_count"], 25)
            self.assertIn("synthetic", written["classification"])
            self.assertEqual(inspected["item_count"], 25)
            self.assertEqual(inspected["t"], {"numerator": 85, "denominator": 64})
            with path.open("ab") as output:
                output.write(b"x")
            with self.assertRaises(DirichletLatticeStageError):
                inspect_input(path)

    def test_projection_refuses_to_call_stage_time_full_atom_time(self) -> None:
        projection = benchmark_projection(items_per_second=76_226_770.0)
        self.assertFalse(projection["external_atom_runtime_estimated"])
        self.assertLess(projection["projected_hours_range"][0],
                        projection["projected_hours_range"][1])

    def test_cli_plan_is_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/tg_dirichlet_lattice_stage.py", "plan"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        value = json.loads(completed.stdout)
        self.assertEqual(value["plan_sha256"], self.plan["plan_sha256"])


if __name__ == "__main__":
    unittest.main()
