# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    DirichletAllCharsStageError,
    INPUT_HEADER,
    bounded_twiddle_cache_inventory,
    canonical_component_orders,
    canonical_residue_order,
    capability,
    group_order,
    has_primitive_character_modulus,
    modulus_butterflies,
    preparation_inventory,
    primitive_frequency_records,
    read_input_header,
    source_work,
    write_residue_batches_input,
    write_synthetic_input,
)
from tg_verifier.dirichlet_campaign import primitive_character_count  # noqa: E402


class DirichletAllCharsStageTest(unittest.TestCase):
    def test_canonical_decompositions_match_platt_cases(self) -> None:
        self.assertEqual(canonical_component_orders(5), (4,))
        self.assertEqual(canonical_component_orders(6), (2,))
        self.assertEqual(canonical_component_orders(12), (2, 2))
        self.assertEqual(canonical_component_orders(8), (2, 2))
        self.assertEqual(canonical_component_orders(16), (2, 4))
        self.assertEqual(canonical_component_orders(15), (2, 4))
        self.assertEqual(canonical_component_orders(400_000), (2, 32, 2500))
        self.assertEqual(group_order(400_000), 160_000)

    def test_crt_residue_and_primitive_conrey_adapters(self) -> None:
        self.assertEqual(canonical_residue_order(5), (1, 2, 4, 3))
        self.assertEqual(canonical_residue_order(8), (1, 7, 5, 3))
        self.assertEqual(canonical_residue_order(15), (1, 11, 7, 2, 4, 14, 13, 8))
        self.assertEqual(
            primitive_frequency_records(5),
            (
                {"primitive_ordinal": 0, "frequency_id": 1,
                 "conrey_number": 2, "parity": 1},
                {"primitive_ordinal": 1, "frequency_id": 2,
                 "conrey_number": 4, "parity": 0},
                {"primitive_ordinal": 2, "frequency_id": 3,
                 "conrey_number": 3, "parity": 1},
            ),
        )
        self.assertEqual(
            [record["frequency_id"] for record in primitive_frequency_records(8)],
            [2, 3],
        )

    def test_butterfly_counts_include_kernel_and_all_lines(self) -> None:
        self.assertEqual(modulus_butterflies(5), 36)
        self.assertEqual(modulus_butterflies(7), 96)
        self.assertEqual(modulus_butterflies(8), 40)
        self.assertEqual(modulus_butterflies(400_000), 9_429_188)

    def test_source_work_is_exact_formulaic_domain(self) -> None:
        self.assertEqual(
            source_work(),
            {
                "q_start": 10_001,
                "q_stop": 400_000,
                "primitive_modulus_roster_version": 2,
                "primitive_modulus_roster": (
                    "primitive-dirichlet-moduli-q-mod-4-ne-2-v2"
                ),
                "active_moduli": 292_500,
                "excluded_empty_primitive_roster_moduli": 97_500,
                "modulus_ordinate_transforms": 3_637_613_167,
                "input_group_values": 266_697_737_764_848,
                "unbatched_radix2_butterflies": 16_899_137_523_971_596,
                "production_batch_size": 64,
                "batch_invocations": 56_981_100,
                "batched_radix2_butterflies": 15_334_965_882_246_056,
            },
        )

    def test_primitive_modulus_roster_boundary(self) -> None:
        self.assertTrue(has_primitive_character_modulus(10_001))
        self.assertFalse(has_primitive_character_modulus(10_002))
        self.assertTrue(has_primitive_character_modulus(10_003))
        self.assertTrue(has_primitive_character_modulus(400_000))
        for q in range(3, 501):
            self.assertEqual(
                has_primitive_character_modulus(q),
                primitive_character_count(q) != 0,
                f"primitive roster criterion differs at q={q}",
            )

    def test_preparation_inventory_is_exact_and_cacheable(self) -> None:
        inventory = preparation_inventory()
        self.assertEqual(inventory["distinct_q_component_plans"], 219_015)
        self.assertEqual(inventory["component_dimensions_across_q"], 816_177)
        self.assertEqual(inventory["distinct_component_orders"], 34_000)
        self.assertEqual(
            inventory["current_per_q_complex_twiddle_enclosures"],
            71_135_060_058,
        )
        self.assertEqual(
            inventory["cross_q_cacheable_complex_twiddle_enclosures"],
            12_952_682_706,
        )
        self.assertEqual(
            inventory["radix2_convolution_lengths"],
            [1 << exponent for exponent in range(2, 21)],
        )

    def test_bounded_cross_q_cache_projection_matches_implementation(self) -> None:
        self.assertEqual(
            bounded_twiddle_cache_inventory(512 * 1024 * 1024),
            {
                "capacity_bytes": 536_870_912,
                "primitive_modulus_roster_version": 2,
                "active_moduli": 292_500,
                "root_pool_catalog_entries": 19,
                "root_pool_reserved_bytes": 134_216_256,
                "root_pool_accesses": 283_566,
                "root_pool_hits": 283_547,
                "root_pool_misses": 19,
                "root_pool_retained_entries": 19,
                "root_pool_retained_bytes": 134_216_256,
                "root_pool_prepared_enclosures": 4_194_258,
                "order_cache_capacity_bytes": 402_654_656,
                "order_cache_accesses": 816_177,
                "order_cache_hits": 532_611,
                "order_cache_misses": 283_566,
                "order_cache_evictions": 283_494,
                "order_cache_uncached_misses": 0,
                "order_cache_retained_entries": 72,
                "order_cache_retained_bytes": 381_904_256,
                "order_cache_peak_retained_bytes": 402_654_656,
                "order_cache_prepared_enclosures": 18_102_127_240,
                "total_prepared_enclosures": 18_106_321_498,
                "cache_peak_total_retained_bytes": 536_870_848,
            },
        )
        with self.assertRaisesRegex(
            DirichletAllCharsStageError,
            "exact 512 MiB",
        ):
            bounded_twiddle_cache_inventory(511 * 1024 * 1024)

    def test_synthetic_input_is_self_identifying_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "q15.bin"
            report = write_synthetic_input(
                path, q=15, t_index=127, batch_count=3
            )
            self.assertEqual(report["component_orders"], [2, 4])
            self.assertEqual(report["group_order"], 8)
            self.assertEqual(report["batch_count"], 3)
            parsed = read_input_header(path)
            self.assertEqual(parsed["t_numerator"], 635)
            raw = bytearray(path.read_bytes())
            # group_order begins at byte 24; changing it must not be accepted.
            raw[24] ^= 1
            path.write_bytes(raw)
            with self.assertRaises(DirichletAllCharsStageError):
                read_input_header(path)

    def test_residue_adapter_reorders_actual_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "adapter.bin"
            batch = {
                a: (float(a), float(a), -float(a), -float(a))
                for a in (1, 2, 4, 7, 8, 11, 13, 14)
            }
            report = write_residue_batches_input(
                path,
                q=15,
                residue_batches=[batch, batch],
                first_t_numerator=0,
                t_denominator=64,
                t_step_numerator=5,
            )
            self.assertEqual(report["batch_count"], 2)
            parsed = read_input_header(path)
            self.assertEqual(parsed["value_count"], 16)
            raw = path.read_bytes()[INPUT_HEADER.size :]
            first_batch_reals = [
                struct.unpack_from("<d", raw, index * 32)[0]
                for index in range(8)
            ]
            self.assertEqual(first_batch_reals, [1.0, 11.0, 7.0, 2.0,
                                                  4.0, 14.0, 13.0, 8.0])

    def test_capability_keeps_atom_boundary_explicit(self) -> None:
        result = capability()
        self.assertFalse(result["closes_external_atom"])
        self.assertFalse(result["production_ready"])
        self.assertTrue(result["transform_component_production_ready"])
        self.assertTrue(result["persistent_framed_transform_service_ready"])
        self.assertFalse(result["streaming_supervisor_performance_ready"])
        self.assertFalse(result["full_source"])
        self.assertIn("Turing completeness closure", result["not_implemented"])
        self.assertEqual(
            result["classification"],
            "source_scalable_transform_component_not_atom_closure",
        )

    def test_cli_capability_and_small_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "q7.bin"
            subprocess.run(
                [
                    sys.executable,
                    "tools/tg_dirichlet_allchars_stage.py",
                    "synthetic-input",
                    str(path),
                    "--q",
                    "7",
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            self.assertEqual(path.stat().st_size, INPUT_HEADER.size + 6 * 32)
            subprocess.run(
                [
                    sys.executable,
                    "tools/tg_dirichlet_allchars_stage.py",
                    "capability",
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    unittest.main()
