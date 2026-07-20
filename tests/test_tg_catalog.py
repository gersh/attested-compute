# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tg_verifier.catalog import ATOMS, CatalogError, load_catalog


class TernaryGoldbachCatalogTests(unittest.TestCase):
    def test_catalog_has_exact_live_surface_shape(self) -> None:
        self.assertEqual(len(ATOMS), 13)
        self.assertEqual(len({atom.atom_id for atom in ATOMS}), 13)
        self.assertEqual(len({atom.lean_name for atom in ATOMS}), 13)
        self.assertTrue(all(atom.claim for atom in ATOMS))
        self.assertTrue(all(atom.completion_requirement for atom in ATOMS))

    def test_duplicate_atom_is_rejected(self) -> None:
        source = Path("specifications/TERNARY_GOLDBACH_EXTERNAL_ATOMS.json")
        value = json.loads(source.read_text(encoding="utf-8"))
        value["atoms"][1]["id"] = value["atoms"][0]["id"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(CatalogError, "duplicate atom id"):
                load_catalog(path)

    def test_wrong_count_is_rejected(self) -> None:
        source = Path("specifications/TERNARY_GOLDBACH_EXTERNAL_ATOMS.json")
        value = json.loads(source.read_text(encoding="utf-8"))
        value["atoms"].pop()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(CatalogError, "exactly thirteen"):
                load_catalog(path)

    def test_source_commit_must_be_lowercase_hexadecimal(self) -> None:
        source = Path("specifications/TERNARY_GOLDBACH_EXTERNAL_ATOMS.json")
        value = json.loads(source.read_text(encoding="utf-8"))
        value["source_commit"] = "z" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(CatalogError, "lowercase hexadecimal"):
                load_catalog(path)


if __name__ == "__main__":
    unittest.main()
