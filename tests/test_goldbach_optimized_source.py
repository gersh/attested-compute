# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from tg_verifier.goldbach_optimized_source import (
    EXPECTED_GOLDBACH_SOURCE_BYTES,
    EXPECTED_GOLDBACH_SOURCE_SHA256,
    GoldbachOptimizedSourceError,
    prepare_optimized_source,
    transform_goldbach_source,
    verify_optimized_source_tree,
)


class GoldbachOptimizedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hardened = Path("/tmp/tg-goldbach-prepared-v2")
        if not cls.hardened.is_dir():
            raise unittest.SkipTest("prepared hardened GoldbachGPU is absent")

    def test_exact_transform_identity(self) -> None:
        source = (self.hardened / "src/goldbach.cu").read_text(
            encoding="utf-8"
        )
        transformed = transform_goldbach_source(source)
        self.assertEqual(
            len(transformed.encode()), EXPECTED_GOLDBACH_SOURCE_BYTES
        )
        self.assertEqual(
            hashlib.sha256(transformed.encode()).hexdigest(),
            EXPECTED_GOLDBACH_SOURCE_SHA256,
        )

    def test_materialization_is_reproducible_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-optimized-source-test-"
        ) as temporary:
            destination = Path(temporary) / "source"
            first = prepare_optimized_source(self.hardened, destination)
            second = prepare_optimized_source(self.hardened, destination)
            self.assertEqual(
                first["source_identity_sha256"],
                second["source_identity_sha256"],
            )
            self.assertFalse(first["production_identity_promoted"])
            self.assertFalse(first["target_h100_measured"])
            self.assertEqual(
                verify_optimized_source_tree(destination),
                first["source_identity_sha256"],
            )
            source = destination / "src/goldbach.cu"
            external_hardlink = Path(temporary) / "goldbach-hardlink.cu"
            os.link(source, external_hardlink)
            with self.assertRaises(GoldbachOptimizedSourceError):
                verify_optimized_source_tree(destination)
            external_hardlink.unlink()
            self.assertEqual(
                verify_optimized_source_tree(destination),
                first["source_identity_sha256"],
            )
            source.write_text(
                source.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(GoldbachOptimizedSourceError):
                prepare_optimized_source(self.hardened, destination)
            with self.assertRaises(GoldbachOptimizedSourceError):
                verify_optimized_source_tree(destination)
            linked = Path(temporary) / "linked-source"
            linked.symlink_to(destination, target_is_directory=True)
            with self.assertRaises(GoldbachOptimizedSourceError):
                prepare_optimized_source(self.hardened, linked)


if __name__ == "__main__":
    unittest.main()
