# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import json
import math
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_certificates import (  # noqa: E402
    DECISIONS,
    LATTICE_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA,
    RECOVERY_FORMAT_VERSION,
    RECOVERY_HEADER,
    RECOVERY_ITEM,
    RECOVERY_MAGIC,
    REPLAY_SCHEMA,
    DirichletLatticeCertificateError,
    canonical_json_bytes,
    capability,
    derive_uniform_tail_bound,
    generate_certificate,
    iter_requests,
    replay_certificate,
    sha256_bytes,
    sha256_file,
)


CAPABILITY = capability()
PINNED_FLINT_AVAILABLE = CAPABILITY["pinned_flint_available"]


class DirichletLatticeCertificateStructuralTests(unittest.TestCase):
    def test_capability_is_explicit_about_component_and_full_pipeline(self) -> None:
        self.assertEqual(
            CAPABILITY["retained_artifact_schema"]["manifest"], MANIFEST_SCHEMA
        )
        self.assertEqual(
            CAPABILITY["retained_artifact_schema"]["semantic_replay"],
            REPLAY_SCHEMA,
        )
        self.assertFalse(CAPABILITY["production_ready"])
        self.assertFalse(CAPABILITY["full_source"])
        self.assertFalse(CAPABILITY["external_atom_discharged"])

    def test_uniform_tail_formula_is_exact_and_upward_rounded(self) -> None:
        delta = Fraction(1, 4096)
        result = derive_uniform_tail_bound(
            t_index=0, m=1, maximum_abs_delta=delta
        )
        k = 16
        expected_zeta = Fraction(1, 2**k) + Fraction(2, 31 * 2**15)
        expected_pochhammer = math.prod(
            Fraction(2 * j + 1, 2) for j in range(k)
        )
        expected_first = (
            delta**k * expected_pochhammer * expected_zeta / math.factorial(k)
        )
        expected_ratio = delta / 2
        expected_remainder = expected_first / (1 - expected_ratio)
        self.assertEqual(
            Fraction(
                int(result["zeta_tail_majorant"]["numerator"]),
                int(result["zeta_tail_majorant"]["denominator"]),
            ),
            expected_zeta,
        )
        self.assertEqual(
            Fraction(
                int(result["remainder_majorant"]["numerator"]),
                int(result["remainder_majorant"]["denominator"]),
            ),
            expected_remainder,
        )
        self.assertGreaterEqual(
            Fraction.from_float(float.fromhex(result["binary64_radius_hex"])),
            expected_remainder,
        )
        self.assertEqual(
            Fraction(
                int(result["geometric_ratio_majorant"]["numerator"]),
                int(result["geometric_ratio_majorant"]["denominator"]),
            ),
            expected_ratio,
        )

    def test_clipped_left_edge_is_strictly_inside_lemma_domain(self) -> None:
        request = next(
            iter_requests(q_start=10_001, q_stop=10_001, t_index=0, max_items=1)
        )
        self.assertEqual((request.q, request.a, request.row), (10_001, 1, 1))
        delta = abs(Fraction(request.a, request.q) - Fraction(request.row, 2048))
        self.assertGreater(delta, Fraction(1, 4096))
        self.assertLess(delta, Fraction(request.row, 2048))
        result = derive_uniform_tail_bound(
            t_index=0, m=1, maximum_abs_delta=delta
        )
        self.assertIn("project_derived", result["classification"])

    def test_recovery_binary_layout_is_fixed(self) -> None:
        self.assertEqual(RECOVERY_MAGIC, b"TGDLREC1")
        self.assertEqual(RECOVERY_FORMAT_VERSION, 1)
        self.assertEqual(RECOVERY_HEADER.size, 52)
        self.assertEqual(RECOVERY_ITEM.size, 48)

    def test_cli_capability_is_machine_readable_even_without_flint(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "tools/tg_dirichlet_lattice_certificates.py",
                "capability",
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        parsed = json.loads(completed.stdout)
        self.assertEqual(parsed["algorithm_id"], CAPABILITY["algorithm_id"])
        self.assertFalse(parsed["production_ready"])


@unittest.skipUnless(
    PINNED_FLINT_AVAILABLE,
    "requires pinned python-flint 0.9.0 / FLINT 3.6.0",
)
class DirichletLatticeCertificateFlintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "certificate"
        cls.manifest = generate_certificate(
            cls.root,
            q_start=10_001,
            q_stop=10_001,
            t_index=127,
            m=4,
            precision_bits=128,
            max_items=3,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _copy(self, name: str) -> Path:
        destination = Path(self.temporary.name) / name
        shutil.copytree(self.root, destination)
        return destination

    def _rehash_artifact_and_manifest(self, root: Path, artifact_name: str) -> None:
        manifest_path = root / MANIFEST_FILENAME
        manifest_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        value = json.loads(manifest_path.read_text(encoding="ascii"))
        digest, size = sha256_file(root / artifact_name)
        value["artifacts"][artifact_name]["sha256"] = digest
        value["artifacts"][artifact_name]["size_bytes"] = size
        value.pop("certificate_sha256")
        value["certificate_sha256"] = sha256_bytes(canonical_json_bytes(value))
        manifest_path.write_bytes(canonical_json_bytes(value))

    def test_higher_precision_replay_checks_every_analytic_value(self) -> None:
        report = replay_certificate(self.root, replay_precision_bits=256)
        self.assertEqual(report["lattice_cells_replayed"], 2048 * 16)
        self.assertEqual(report["finite_recovery_values_replayed"], 3)
        self.assertTrue(report["higher_precision_arb_containment_passed"])
        self.assertTrue(report["uniform_tail_replayed_exactly"])
        self.assertFalse(report["external_atom_discharged"])

    def test_trust_boundary_cannot_be_relabelled(self) -> None:
        root = self._copy("forged-decisions")
        path = root / MANIFEST_FILENAME
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        value = json.loads(path.read_text(encoding="ascii"))
        value["decisions"] = dict(DECISIONS)
        value["decisions"]["external_atom_discharged"] = True
        value.pop("certificate_sha256")
        value["certificate_sha256"] = sha256_bytes(canonical_json_bytes(value))
        path.write_bytes(canonical_json_bytes(value))
        with self.assertRaisesRegex(
            DirichletLatticeCertificateError, "trust-boundary decisions"
        ):
            replay_certificate(root, replay_precision_bits=256)

    def test_bound_input_tamper_fails_before_semantic_replay(self) -> None:
        root = self._copy("forged-input")
        path = root / LATTICE_FILENAME
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        with path.open("r+b") as output:
            output.seek(80)
            byte = output.read(1)
            output.seek(80)
            output.write(bytes([byte[0] ^ 1]))
        with self.assertRaisesRegex(
            DirichletLatticeCertificateError, "artifact mismatch"
        ):
            replay_certificate(root, replay_precision_bits=256)

    def test_rehashed_synthetic_seed_fails_semantic_replay(self) -> None:
        root = self._copy("forged-semantic-seed")
        path = root / LATTICE_FILENAME
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        with path.open("r+b") as output:
            output.seek(64)
            output.write(bytes(32))
        self._rehash_artifact_and_manifest(root, LATTICE_FILENAME)
        with self.assertRaisesRegex(
            DirichletLatticeCertificateError,
            "does not contain higher-precision Arb replay at row=1, column=0",
        ):
            replay_certificate(root, replay_precision_bits=256)


if __name__ == "__main__":
    unittest.main()
