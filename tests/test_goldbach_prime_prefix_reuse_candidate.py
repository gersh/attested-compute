# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from pathlib import Path
import shutil
import tempfile
import unittest

from tg_verifier.goldbach_prime_prefix_reuse_candidate import (
    EXPECTED_CROSSCHECK_SOURCE_BYTES,
    EXPECTED_CROSSCHECK_SOURCE_SHA256,
    EXPECTED_GOLDBACH_SOURCE_BYTES,
    EXPECTED_GOLDBACH_SOURCE_SHA256,
    GoldbachPrimePrefixCandidateError,
    prepare_prime_prefix_reuse_crosscheck_source,
    prepare_prime_prefix_reuse_source,
)


class GoldbachPrimePrefixReuseCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v1 = Path("/tmp/tg-goldbach-qualified-0725-e/source")
        if not cls.v1.is_dir():
            raise unittest.SkipTest("qualified Goldbach v1 source is absent")

    def test_materialization_is_exact_and_conservative(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-prime-prefix-candidate-test-"
        ) as temporary:
            destination = Path(temporary) / "source"
            first = prepare_prime_prefix_reuse_source(
                self.v1, destination
            )
            second = prepare_prime_prefix_reuse_source(
                self.v1, destination
            )
            self.assertEqual(
                first["source_identity_sha256"],
                second["source_identity_sha256"],
            )
            self.assertEqual(
                first["files"], second["files"]
            )
            source = destination / "src/goldbach.cu"
            self.assertEqual(
                source.stat().st_size, EXPECTED_GOLDBACH_SOURCE_BYTES
            )
            import hashlib

            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(),
                EXPECTED_GOLDBACH_SOURCE_SHA256,
            )
            for field in (
                "confidential_attestation_completed",
                "lean_atom_discharged",
                "production_identity_promoted",
                "source_scale_completion",
                "target_h100_measured",
            ):
                self.assertFalse(first[field])

    def test_rejects_mutated_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-prime-prefix-candidate-test-"
        ) as temporary:
            destination = Path(temporary) / "source"
            prepare_prime_prefix_reuse_source(self.v1, destination)
            source = destination / "src/goldbach.cu"
            source.write_text(
                source.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(GoldbachPrimePrefixCandidateError):
                prepare_prime_prefix_reuse_source(self.v1, destination)

    def test_crosscheck_source_is_exact_and_never_reused(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-prime-prefix-crosscheck-test-"
        ) as temporary:
            destination = Path(temporary) / "source"
            result = prepare_prime_prefix_reuse_crosscheck_source(
                self.v1, destination
            )
            self.assertEqual(
                result["goldbach_source"],
                {
                    "sha256": EXPECTED_CROSSCHECK_SOURCE_SHA256,
                    "size_bytes": EXPECTED_CROSSCHECK_SOURCE_BYTES,
                },
            )
            with self.assertRaises(GoldbachPrimePrefixCandidateError):
                prepare_prime_prefix_reuse_crosscheck_source(
                    self.v1, destination
                )

    def test_rejects_mutated_v1_helper_closure(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-prime-prefix-v1-attack-test-"
        ) as temporary:
            root = Path(temporary)
            mutated = root / "mutated-v1"
            shutil.copytree(self.v1, mutated)
            helper = mutated / "src/prime_bitset.cpp"
            helper.write_text(
                helper.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(GoldbachPrimePrefixCandidateError):
                prepare_prime_prefix_reuse_source(
                    mutated, root / "productive"
                )
            with self.assertRaises(GoldbachPrimePrefixCandidateError):
                prepare_prime_prefix_reuse_crosscheck_source(
                    mutated, root / "crosscheck"
                )


if __name__ == "__main__":
    unittest.main()
