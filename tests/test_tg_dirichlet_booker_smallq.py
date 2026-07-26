# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_booker_smallq import (  # noqa: E402
    DECISIONS,
    MANIFEST_NAME,
    VALUES_NAME,
    DirichletBookerSmallQError,
    benchmark,
    canonical_json_bytes,
    capability,
    known_answer_case,
    replay_frequency_chunk,
    sha256_file,
    source_campaign_plan,
    source_chunk_request,
    transform_parameters,
)


CAPABILITY = capability()
PINNED_FLINT_AVAILABLE = CAPABILITY["pinned_flint_available"]


class DirichletBookerSmallQStructuralTests(unittest.TestCase):
    def test_capability_states_exact_boundary_and_missing_closure(self) -> None:
        self.assertEqual(CAPABILITY["source_domain"], {"q_start": 2, "q_stop": 10_000})
        self.assertEqual(
            CAPABILITY["sample_step"], {"numerator": "5", "denominator": "64"}
        )
        self.assertTrue(CAPABILITY["full_source_plan_available"])
        self.assertFalse(CAPABILITY["source_parameter_status"]["production_b_published"])
        self.assertFalse(CAPABILITY["source_parameter_status"]["production_eta_published"])
        self.assertFalse(CAPABILITY["production_ready"])
        self.assertFalse(CAPABILITY["external_atom_discharged"])

    def test_source_parameters_cover_terminal_height_on_five_over_64_grid(self) -> None:
        parameters = transform_parameters(3)
        self.assertEqual(parameters.a, Fraction(64, 5))
        self.assertEqual(parameters.b * parameters.a, parameters.transform_length)
        self.assertEqual(parameters.transform_length, 1 << 29)
        self.assertGreaterEqual(parameters.b - parameters.height, 64)
        self.assertEqual(parameters.sample_count, 426_666_667)

    def test_compact_plan_covers_all_primitive_characters_for_small_fixture(self) -> None:
        plan = source_campaign_plan(q_start=2, q_stop=5, include_moduli=True)
        self.assertEqual(plan["total_primitive_characters"], 5)
        self.assertEqual(
            [row["primitive_characters"] for row in plan["moduli"]], [0, 1, 1, 3]
        )
        self.assertTrue(plan["planning_estimate_is_not_a_runtime_measurement"])
        self.assertEqual(plan["decisions"], DECISIONS)

    def test_source_request_uses_existing_exact_character_unranking(self) -> None:
        request = source_chunk_request(
            q=5,
            character_ordinal=1,
            frequency_chunk_index=0,
            frequency_chunk_size=1024,
        )
        self.assertEqual(request["conrey_number"], 4)
        self.assertEqual(request["parity"], 0)
        self.assertEqual((request["frequency_start"], request["frequency_stop"]), (0, 1024))

    def test_cli_capability_without_flint_remains_machine_readable(self) -> None:
        # The in-process structural command is deliberately usable even when
        # the pinned analytic runtime is absent.
        self.assertIn("pinned_flint_available", CAPABILITY)


@unittest.skipUnless(
    PINNED_FLINT_AVAILABLE,
    "requires pinned python-flint 0.9.0 / FLINT 3.6.0",
)
class DirichletBookerSmallQArbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.results = {}
        for q, conrey in ((3, 2), (4, 3), (5, 2), (5, 3), (5, 4)):
            cls.results[(q, conrey)] = known_answer_case(
                cls.root,
                q=q,
                conrey_number=conrey,
                transform_length=128,
                sample_stop=5,
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_q3_q4_q5_dft_enclosures_contain_direct_completed_values(self) -> None:
        for result in self.results.values():
            self.assertTrue(result["replay"]["higher_precision_containment_passed"])
            self.assertTrue(result["samples"]["direct_flint_comparison_passed"])
            self.assertEqual(result["samples"]["sample_count"], 5)
            self.assertFalse(result["samples"]["decisions"]["external_atom_discharged"])

    def test_manifest_hash_rejects_frequency_corruption(self) -> None:
        source = self.root / "q3-chi2"
        forged = self.root / "forged-frequency"
        shutil.copytree(source, forged)
        path = forged / VALUES_NAME
        raw = bytearray(path.read_bytes())
        raw[len(raw) // 2] ^= 1
        path.write_bytes(raw)
        with self.assertRaisesRegex(DirichletBookerSmallQError, "hash/size mismatch"):
            replay_frequency_chunk(forged)

    def test_rehashed_trust_boundary_mutation_is_rejected(self) -> None:
        source = self.root / "q4-chi3"
        forged = self.root / "forged-decisions"
        shutil.copytree(source, forged)
        manifest_path = forged / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        manifest["decisions"]["external_atom_discharged"] = True
        # Artifact hashes remain intact; only the supposedly semantic flag is
        # changed, so replay must compare it with the compiled boundary.
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        with self.assertRaisesRegex(DirichletBookerSmallQError, "trust-boundary"):
            replay_frequency_chunk(forged)

    def test_local_benchmark_counts_actual_gaussian_terms(self) -> None:
        report = benchmark(q=5, conrey_number=2, frequency_count=128)
        self.assertEqual(report["frequency_count"], 128)
        self.assertGreater(report["finite_gaussian_terms"], 0)
        self.assertGreater(report["elapsed_nanoseconds"], 0)


if __name__ == "__main__":
    unittest.main()
