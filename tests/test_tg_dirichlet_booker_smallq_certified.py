# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_certified as certified


@unittest.skipIf(base.FLINT_IMPORT_ERROR is not None, "python-flint unavailable")
class CertifiedSmallQTests(unittest.TestCase):
    def parameters(self):
        return base.transform_parameters(
            5,
            height=Fraction(1),
            guard_height=Fraction(4),
            transform_length=128,
            eta=Fraction(0),
        )

    def test_seed_replay_is_linear_not_term_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.bin"
            produced = certified.write_seed_frame(
                path,
                q=5,
                conrey_numbers=(2, 4),
                parameters=self.parameters(),
            )
            replay = certified.verify_seed_frame(path, parameters=self.parameters())
            self.assertEqual(replay["transcendental_seeds_replayed"], 256)
            self.assertEqual(
                replay["finite_gaussian_terms_avoided"],
                produced["finite_gaussian_terms_not_replayed_by_seed_checker"],
            )
            self.assertFalse(replay["term_by_term_arb_replay_required"])

    def test_understated_analytic_radius_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.bin"
            certified.write_seed_frame(
                path,
                q=5,
                conrey_numbers=(2,),
                parameters=self.parameters(),
            )
            raw = bytearray(path.read_bytes())
            analytic_offset = (
                certified.INPUT_HEADER.size
                + certified.PARAMETER_HEADER.size
                + certified.CHARACTER_HEADER.size
                + 5 * 4
                + certified.FREQUENCY_PREFIX.size
                + 2 * certified.DISK.size
            )
            struct.pack_into("<d", raw, analytic_offset, 0.0)
            path.write_bytes(raw)
            with self.assertRaisesRegex(
                certified.CertifiedSmallQError, "analytic tail is understated"
            ):
                certified.verify_seed_frame(path, parameters=self.parameters())

    def test_exact_parameter_relabelling_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.bin"
            certified.write_seed_frame(
                path,
                q=5,
                conrey_numbers=(2,),
                parameters=self.parameters(),
            )
            relabelled = base.transform_parameters(
                5,
                height=Fraction(1),
                guard_height=Fraction(4),
                transform_length=128,
                eta=Fraction(1, 10),
            )
            with self.assertRaisesRegex(
                certified.CertifiedSmallQError,
                "checker parameters do not match seed frame",
            ):
                certified.verify_seed_frame(path, parameters=relabelled)

    def test_cuda_disk_and_dft_end_to_end_when_runner_is_supplied(self) -> None:
        runner = os.environ.get("TG_SMALLQ_CERTIFIED_RUNNER")
        if not runner:
            self.skipTest("set TG_SMALLQ_CERTIFIED_RUNNER to run the CUDA KAT")
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.bin"
            output_path = Path(directory) / "output.bin"
            certified.write_seed_frame(
                input_path,
                q=5,
                conrey_numbers=(2, 4),
                parameters=self.parameters(),
            )
            subprocess.run(
                [runner, "--iterations", "2", str(input_path), str(output_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            result = certified.verify_output_kat(
                input_path,
                output_path,
                parameters=self.parameters(),
            )
            self.assertTrue(result["passed"])
            self.assertEqual(result["independent_arb_values_checked"], 256)


if __name__ == "__main__":
    unittest.main()
