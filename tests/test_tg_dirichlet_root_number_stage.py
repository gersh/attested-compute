# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from io import BytesIO
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tg_verifier.dirichlet_root_number_stage as stage  # noqa: E402
from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    canonical_residue_order,
)


PINNED_FLINT = (
    stage.FLINT_IMPORT_ERROR is None
    and stage.flint.__version__ == "0.9.0"
    and stage.flint.__FLINT_VERSION__ == "3.6.0"
)
MPFR_CHECKER = ROOT / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr"


class DirichletRootNumberStructuralTests(unittest.TestCase):
    def test_source_work_is_exact_and_bounded_per_modulus(self) -> None:
        result = stage.source_work()
        self.assertEqual(result["counts"], stage.PINNED_SOURCE_WORK)
        self.assertEqual(result["counts"]["active_moduli"], 292_500)
        self.assertEqual(
            result["counts"]["primitive_root_records"], 29_547_446_729
        )
        self.assertEqual(
            result["counts"]["radix2_butterflies"], 2_645_418_549_056
        )
        self.assertEqual(
            result["maximum_single_modulus"]["root_working_set_upper_bound_bytes"],
            stage.ROOT_HEADER.size + 399_988 * stage.ROOT_RECORD.size,
        )

    def test_capability_keeps_atom_boundary_and_gaps_explicit(self) -> None:
        result = stage.capability()
        self.assertTrue(result["source_scalable_algorithm_implemented"])
        self.assertFalse(result["source_performance_ready"])
        self.assertFalse(result["production_accept"])
        self.assertFalse(result["closes_external_atom"])
        self.assertFalse(result["full_source_campaign_run"])
        self.assertIn(
            "TGDRNRO1 artifact lookup in the completed-L stream consumer",
            result["implemented"],
        )
        self.assertNotIn(
            "integration of TGDRNRO1 lookup into the completed-L stream consumer",
            result["not_implemented"],
        )
        self.assertIn("+2*pi*i", result["transform_convention"])
        self.assertIn("i^a", result["completed_phase_convention"])

    def test_bulk_primitive_map_matches_independent_scalar_map(self) -> None:
        for q in (5, 7, 8, 12, 15, 16, 25, 40, 105):
            self.assertEqual(
                stage.primitive_frequency_records_bulk(q),
                stage.primitive_frequency_records(q),
            )


@unittest.skipUnless(PINNED_FLINT, "requires python-flint 0.9.0 / FLINT 3.6.0")
class DirichletRootNumberArbTests(unittest.TestCase):
    def test_additive_input_is_canonical_outward_and_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = stage.write_additive_input(
                root / "q5.bin",
                q=5,
                precision=192,
                receipt_path=root / "q5.json",
            )
            self.assertEqual(
                receipt["input_sha256"],
                "54ca5787f01cd5f413ef75df7fcaf2ad948f0bf413c511541c529af52c9299fd",
            )
            raw = (root / "q5.bin").read_bytes()
            self.assertEqual(canonical_residue_order(5), (1, 2, 4, 3))
            for ordinal, residue in enumerate(canonical_residue_order(5)):
                endpoints = COMPLEX_INTERVAL.unpack_from(
                    raw, INPUT_HEADER.size + ordinal * COMPLEX_INTERVAL.size
                )
                candidate = stage._binary_rectangle(endpoints)
                expected = stage.acb(
                    0, 2 * stage.arb.pi() * residue / 5
                ).exp()
                self.assertTrue(candidate.contains(expected))
            replay = stage.verify_additive_input(
                root / "q5.bin", receipt, replay_arithmetic=True
            )
            self.assertTrue(replay["accepted"])
            self.assertTrue(replay["arithmetic_replayed"])

    @unittest.skipUnless(MPFR_CHECKER.is_file(), "requires built MPFR TGDAFF checker")
    def test_mpfr_transform_direct_arb_kat_and_tamper_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            additive = stage.write_additive_input(root / "input", q=5, precision=256)
            subprocess.run(
                [
                    str(MPFR_CHECKER),
                    "compute",
                    str(root / "input"),
                    str(root / "transform"),
                    "256",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            receipt = stage.consume_transform_path(
                root / "transform",
                root / "roots",
                root / "receipt",
                q=5,
                additive_receipt=additive,
                precision=256,
            )
            replay = stage.direct_replay_artifact(
                root / "roots", receipt, precision=256
            )
            self.assertEqual(replay["character_count"], 3)
            metadata, roots = stage.read_root_artifact(root / "roots", receipt)
            identities = stage.primitive_frequency_records(5)
            quadratic = next(
                index
                for index, row in enumerate(identities)
                if row["conrey_number"] == 4
            )
            self.assertEqual(stage.dirichlet_char(5, 4).order(), 2)
            self.assertEqual(stage.dirichlet_char(5, 4).group().exponent(), 4)
            self.assertTrue(roots[quadratic].contains(stage.acb(1)))
            self.assertEqual(metadata["primitive_character_count"], 3)

            changed = bytearray((root / "roots").read_bytes())
            changed[-1] ^= 1
            (root / "tampered").write_bytes(changed)
            with self.assertRaisesRegex(
                stage.DirichletRootNumberStageError, "root receipt root_artifact_sha256"
            ):
                stage.read_root_artifact(root / "tampered", receipt)

            bad_receipt = dict(receipt)
            bad_receipt["transform_convention"] = bad_receipt[
                "transform_convention"
            ].replace("+2*pi*i", "-2*pi*i")
            with self.assertRaisesRegex(
                stage.DirichletRootNumberStageError, "receipt hash differs"
            ):
                stage.read_root_artifact(root / "roots", bad_receipt)

    @unittest.skipUnless(MPFR_CHECKER.is_file(), "requires built MPFR TGDAFF checker")
    def test_persistent_two_modulus_protocol_is_bounded_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controls = bytearray()
            transforms = bytearray()
            expected_records = 0
            for frame_index, q in enumerate((5, 7)):
                additive = stage.write_additive_input(
                    root / f"q{q}.in", q=q, precision=192
                )
                subprocess.run(
                    [
                        str(MPFR_CHECKER),
                        "compute",
                        str(root / f"q{q}.in"),
                        str(root / f"q{q}.out"),
                        "192",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                controls.extend(
                    stage.canonical_json_bytes(
                        stage.make_stream_control(
                            frame_index=frame_index, q=q, additive_receipt=additive
                        )
                    )
                )
                transforms.extend((root / f"q{q}.out").read_bytes())
                expected_records += stage.primitive_character_count(q)
            roots = BytesIO()
            receipts = BytesIO()
            summary = stage.consume_streams(
                BytesIO(controls),
                BytesIO(transforms),
                roots,
                receipts,
                root / "summary.json",
                precision=192,
            )
            self.assertEqual(summary["frame_count"], 2)
            self.assertEqual(summary["root_record_count"], expected_records)
            self.assertEqual(summary["root_stream_bytes"], len(roots.getvalue()))
            self.assertEqual(len(receipts.getvalue().splitlines()), 2)
            self.assertFalse(summary["production_accept"])

    @unittest.skipUnless(MPFR_CHECKER.is_file(), "requires built MPFR TGDAFF checker")
    def test_fresh_independent_known_answer_script(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "tests/tg_dirichlet_root_number_known_answers.py",
                "--checker",
                str(MPFR_CHECKER),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual([row["q"] for row in report["moduli"]], [5, 7, 8, 15])
        self.assertEqual(
            report["group_exponent_regression"],
            "q=5-conrey-4-order-2-group-exponent-4",
        )


if __name__ == "__main__":
    unittest.main()
