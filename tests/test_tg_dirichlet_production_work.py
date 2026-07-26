# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_production_work import (  # noqa: E402
    PINNED,
    exact_work_inventory,
)


class DirichletProductionWorkTests(unittest.TestCase):
    def test_exact_source_counts_and_streaming_boundary(self) -> None:
        report = exact_work_inventory()
        self.assertEqual(report["counts"], PINNED)
        self.assertEqual(report["counts"]["all_primitive_characters"],
                         29_565_923_837)
        self.assertEqual(report["counts"]["large_q_lattice_cells"],
                         4_193_910_784)
        self.assertEqual(
            report["storage_warning"][
                "large_q_transformed_rectangles_if_materialized_bytes"
            ],
            8_534_327_608_475_136,
        )
        self.assertFalse(report["external_atom_discharged"])

    def test_cli_is_machine_readable(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/tg_dirichlet_production_work.py"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout)["counts"], PINNED)


if __name__ == "__main__":
    unittest.main()
