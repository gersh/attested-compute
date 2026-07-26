# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "qualify_tg_mobius_p13_seed.py"
SPEC = importlib.util.spec_from_file_location("tg_p13_qualifier", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


FALSE_CLAIMS = {
    "execution_attested": False,
    "cuda_or_cpp_compiler_refinement_proved": False,
    "lean_atom_discharged": False,
    "proves_any_external_atom": False,
}


def records(variant: str, executable_sha256: str = "2" * 64):
    p13 = variant == "p13"
    algorithm = module.P13_ALGORITHM if p13 else module.P11_ALGORITHM
    domain = module.P13_LEAF_DOMAIN if p13 else module.P11_LEAF_DOMAIN
    header = {
        "record": "header",
        "algorithm": algorithm,
        "receipt_leaf_domain": domain,
        "executable_sha256": executable_sha256,
        "prime_roster_sha256": module.common.SOURCE_ROSTER_SHA256,
        "qualification_only_not_production_admissible": True,
        "qualification_affine_block_compose": True,
        "qualification_direct_fused_support_block_compose_path": True,
        "residue_seed_prime_count": 6 if p13 else 5,
        "affine_workspace_device_bytes": 0,
        "cuda_allocation_epoch_count": 1,
        **FALSE_CLAIMS,
    }
    if p13:
        header.update(
            {
                "qualification_residue_23571113_seed": True,
                "residue_23571113_per_row_modulus": 169,
                "residue_23571113_materialized_table_rows": 0,
                "residue_23571113_suffix_minimum_prime": 17,
                "fused_multiblock_residue_23571113_minimum_safe_slots_per_prime": 61,
                "qualification_residue_23571113_split_square_support_path": True,
            }
        )
    else:
        header["qualification_residue_235711_seed"] = True
    leaf = {
        "record": "leaf",
        "algorithm": algorithm,
        "receipt_leaf_domain": domain,
        "qualification_only_not_production_admissible": True,
        "poison_count": 0,
        **FALSE_CLAIMS,
    }
    terminal = {
        "record": "terminal",
        "algorithm": algorithm,
        "receipt_leaf_domain": domain,
        "qualification_only_not_production_admissible": True,
        **FALSE_CLAIMS,
    }
    return [header, leaf, terminal]


class MobiusP13QualificationTests(unittest.TestCase):
    def test_constants_and_source_isolation(self):
        self.assertEqual(
            module.MINIMUM_ROWS,
            17 * module.common.EVENTS_PER_BLOCK + 1,
        )
        self.assertNotEqual(module.P11_ALGORITHM, module.P13_ALGORITHM)
        self.assertNotEqual(module.P11_LEAF_DOMAIN, module.P13_LEAF_DOMAIN)
        header = (ROOT / "gpu/include/tg_mobius_segment.h").read_text()
        kernel = (ROOT / "gpu/src/tg_mobius_segment_kernel.cu").read_text()
        runner = (ROOT / "gpu/src/tg_mobius_persistent_runner.cpp").read_text()
        self.assertIn("kTgMobiusResidue23571113Modulus = 13 * 13", header)
        self.assertIn("kTgMobiusResidue23571113SuffixMinimum = 17", header)
        self.assertIn("kTgMobiusResidue23571113MinimumSlotsPerPrime = 61", header)
        self.assertIn("<true, true, true>", kernel)
        self.assertIn("--qualification-residue-23571113-seed", runner)
        self.assertIn("qualification_seed_thirteen", runner)
        self.assertIn(
            "qualification_only_residue_23571113_and_affine_block_compose",
            runner,
        )
        self.assertIn(
            "const bool qualification_seed_thirteen =",
            runner,
        )
        self.assertIn(
            "options.qualification_residue_23571113_seed;",
            runner,
        )

    def test_exact_record_identities_accept(self):
        module._validate_records(
            records("p11"), variant="p11", executable_sha256="2" * 64
        )
        module._validate_records(
            records("p13"), variant="p13", executable_sha256="2" * 64
        )

    def test_identity_and_arithmetic_mutations_reject(self):
        mutations = (
            ("algorithm", module.P11_ALGORITHM),
            ("residue_23571113_per_row_modulus", 168),
            ("residue_23571113_suffix_minimum_prime", 13),
            (
                "fused_multiblock_residue_23571113_minimum_safe_slots_per_prime",
                60,
            ),
            ("qualification_residue_23571113_seed", False),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(records("p13"))
                changed[0][field] = value
                with self.assertRaises(module.QualificationError):
                    module._validate_records(
                        changed,
                        variant="p13",
                        executable_sha256="2" * 64,
                    )
        changed = copy.deepcopy(records("p13"))
        changed[1]["poison_count"] = 1
        with self.assertRaises(module.QualificationError):
            module._validate_records(
                changed, variant="p13", executable_sha256="2" * 64
            )

    def test_resource_patterns_distinguish_p11_and_p13(self):
        self.assertEqual(
            module.RESOURCE_PATTERNS["p11_initializer"],
            "initialize_fused_mobius_support_residue_235ILb1ELb1ELb0EEE",
        )
        self.assertEqual(
            module.RESOURCE_PATTERNS["p13_initializer"],
            "initialize_fused_mobius_support_residue_235ILb1ELb1ELb1EEE",
        )
        self.assertEqual(len(set(module.RESOURCE_PATTERNS.values())),
                         len(module.RESOURCE_PATTERNS))


if __name__ == "__main__":
    unittest.main()
