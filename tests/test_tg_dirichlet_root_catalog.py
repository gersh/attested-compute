# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_allchars_stage import canonical_component_orders  # noqa: E402
from tg_verifier.dirichlet_root_catalog import (  # noqa: E402
    DirichletRootCatalogError,
    active_moduli,
    audit_root_catalog,
    build_root_catalog,
    capability,
    root_artifact_filename,
    root_receipt_filename,
    split_root_stream,
)
from tg_verifier.dirichlet_root_number_stage import (  # noqa: E402
    AUTHOR,
    ATOM_ID,
    COMPLETED_PHASE_CONVENTION,
    CONVENTION_SHA256,
    ROOT_ALGORITHM_ID,
    ROOT_RECEIPT_SCHEMA,
    TRANSFORM_CONVENTION,
    canonical_json_bytes,
    sha256_bytes,
)


class DirichletRootCatalogTest(unittest.TestCase):
    Q_START = 10_001
    Q_STOP = 10_005

    def _write_roots(self, root: Path, *, wrong_receipt_q: int | None = None) -> None:
        root.mkdir()
        for q, count in active_moduli(self.Q_START, self.Q_STOP):
            raw = f"validated-root-artifact-{q}".encode("ascii")
            artifact_sha = sha256_bytes(raw)
            transform_sha = hashlib.sha256(f"transform-{q}".encode()).hexdigest()
            receipt = {
                "additive_input_receipt_sha256": "1" * 64,
                "additive_input_sha256": "2" * 64,
                "algorithm_id": ROOT_ALGORITHM_ID,
                "all_intervals_outward": True,
                "atom_id": ATOM_ID,
                "author": AUTHOR,
                "classification": "certified_root_number_component_not_zero_or_grh_closure",
                "completed_phase_convention": COMPLETED_PHASE_CONVENTION,
                "component_orders": list(canonical_component_orders(q)),
                "convention_sha256": CONVENTION_SHA256,
                "external_atom_discharged": False,
                "format": "TGDRNRO1",
                "full_source_campaign_run": False,
                "group_order": 1,
                "kind": ROOT_RECEIPT_SCHEMA,
                "precision_bits": 192,
                "primitive_character_count": count,
                "primitive_identity_rows_sha256": "3" * 64,
                "production_accept": False,
                "q": q + 1 if wrong_receipt_q == q else q,
                "radix2_butterflies": 1,
                "root_artifact_bytes": len(raw),
                "root_artifact_sha256": artifact_sha,
                "root_record_semantics": "principal_sqrt(conj(tau(chi)/(i^parity*sqrt(q))))",
                "source_scalable_algorithm_implemented": True,
                "source_performance_ready": False,
                "source_performance_blocker": "test fixture",
                "transform_convention": TRANSFORM_CONVENTION,
                "transform_elapsed_nanoseconds_reported": 1,
                "transform_output_sha256": transform_sha,
                "zero_completeness_claimed": False,
            }
            receipt["receipt_sha256"] = sha256_bytes(
                canonical_json_bytes(receipt)
            )
            (root / root_artifact_filename(q)).write_bytes(raw)
            (root / root_receipt_filename(q)).write_bytes(
                canonical_json_bytes(receipt)
            )

    @staticmethod
    def _fake_parser(raw: bytes, receipt: dict[str, object]):
        q = int(raw.decode("ascii").rsplit("-", 1)[1])
        count = int(receipt["primitive_character_count"])
        return (
            {
                "additive_input_sha256": receipt["additive_input_sha256"],
                "component_orders": list(canonical_component_orders(q)),
                "primitive_character_count": count,
                "q": q,
                "root_artifact_bytes": len(raw),
                "root_artifact_sha256": sha256_bytes(raw),
                "transform_output_sha256": receipt["transform_output_sha256"],
            },
            tuple(range(count)),
        )

    def test_build_and_reaudit_exact_monotone_root_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "roots"
            self._write_roots(root)
            catalog = base / "catalog.ndjson"
            with patch(
                "tg_verifier.dirichlet_root_catalog.read_root_artifact_bytes",
                side_effect=self._fake_parser,
            ) as parser:
                built = build_root_catalog(
                    catalog,
                    root,
                    q_start=self.Q_START,
                    q_stop=self.Q_STOP,
                )
                audited = audit_root_catalog(
                    catalog,
                    root=root,
                    expected_sha256=built["catalog_sha256"],
                    revalidate_artifacts=True,
                )
            expected_count = len(
                list(active_moduli(self.Q_START, self.Q_STOP))
            )
            self.assertEqual(built["entry_count"], expected_count)
            self.assertEqual(audited["entry_count"], expected_count)
            self.assertEqual(parser.call_count, 2 * expected_count)
            self.assertTrue(
                audited["artifacts_parsed_and_receipt_bound"]
            )
            self.assertFalse(audited["execution_attested"])
            self.assertFalse(audited["external_atom_discharged"])

    def test_persistent_stream_is_split_atomically_into_canonical_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            self._write_roots(source)
            root_stream = base / "roots.bin"
            receipt_stream = base / "receipts.ndjson"
            root_raw = b"".join(
                (source / root_artifact_filename(q)).read_bytes()
                for q, _count in active_moduli(self.Q_START, self.Q_STOP)
            )
            receipt_raw = b"".join(
                (source / root_receipt_filename(q)).read_bytes()
                for q, _count in active_moduli(self.Q_START, self.Q_STOP)
            )
            root_stream.write_bytes(root_raw)
            receipt_stream.write_bytes(receipt_raw)
            output = base / "materialized"
            with patch(
                "tg_verifier.dirichlet_root_catalog.read_root_artifact_bytes",
                side_effect=self._fake_parser,
            ):
                result = split_root_stream(
                    root_stream,
                    receipt_stream,
                    output,
                    q_start=self.Q_START,
                    q_stop=self.Q_STOP,
                    expected_root_stream_sha256=sha256_bytes(root_raw),
                    expected_receipt_stream_sha256=sha256_bytes(receipt_raw),
                )
            self.assertTrue(output.is_dir())
            self.assertEqual(
                result["entry_count"],
                len(list(active_moduli(self.Q_START, self.Q_STOP))),
            )
            for q, _count in active_moduli(self.Q_START, self.Q_STOP):
                self.assertEqual(
                    (output / root_artifact_filename(q)).read_bytes(),
                    (source / root_artifact_filename(q)).read_bytes(),
                )

    def test_wrong_stream_digest_leaves_no_partial_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            self._write_roots(source)
            root_stream = base / "roots.bin"
            receipt_stream = base / "receipts.ndjson"
            root_stream.write_bytes(
                b"".join(
                    (source / root_artifact_filename(q)).read_bytes()
                    for q, _count in active_moduli(self.Q_START, self.Q_STOP)
                )
            )
            receipt_stream.write_bytes(
                b"".join(
                    (source / root_receipt_filename(q)).read_bytes()
                    for q, _count in active_moduli(self.Q_START, self.Q_STOP)
                )
            )
            output = base / "materialized"
            with (
                patch(
                    "tg_verifier.dirichlet_root_catalog.read_root_artifact_bytes",
                    side_effect=self._fake_parser,
                ),
                self.assertRaisesRegex(
                    DirichletRootCatalogError, "root stream SHA-256 differs"
                ),
            ):
                split_root_stream(
                    root_stream,
                    receipt_stream,
                    output,
                    q_start=self.Q_START,
                    q_stop=self.Q_STOP,
                    expected_root_stream_sha256="0" * 64,
                )
            self.assertFalse(output.exists())

    def test_missing_active_modulus_fails_before_catalog_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "roots"
            self._write_roots(root)
            missing_q = next(iter(active_moduli(self.Q_START, self.Q_STOP)))[0]
            (root / root_artifact_filename(missing_q)).unlink()
            catalog = base / "catalog.ndjson"
            with (
                patch(
                    "tg_verifier.dirichlet_root_catalog.read_root_artifact_bytes",
                    side_effect=self._fake_parser,
                ),
                self.assertRaisesRegex(
                    DirichletRootCatalogError, "cannot open.*root artifact"
                ),
            ):
                build_root_catalog(
                    catalog,
                    root,
                    q_start=self.Q_START,
                    q_stop=self.Q_STOP,
                )
            self.assertFalse(catalog.exists())

    def test_wrong_q_receipt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "roots"
            self._write_roots(root, wrong_receipt_q=10_003)
            with (
                patch(
                    "tg_verifier.dirichlet_root_catalog.read_root_artifact_bytes",
                    side_effect=self._fake_parser,
                ),
                self.assertRaisesRegex(
                    DirichletRootCatalogError, "identity.*differs"
                ),
            ):
                build_root_catalog(
                    base / "catalog.ndjson",
                    root,
                    q_start=self.Q_START,
                    q_stop=self.Q_STOP,
                )

    def test_catalog_substitution_fails_whole_file_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "roots"
            self._write_roots(root)
            catalog = base / "catalog.ndjson"
            with patch(
                "tg_verifier.dirichlet_root_catalog.read_root_artifact_bytes",
                side_effect=self._fake_parser,
            ):
                built = build_root_catalog(
                    catalog,
                    root,
                    q_start=self.Q_START,
                    q_stop=self.Q_STOP,
                )
            raw = bytearray(catalog.read_bytes())
            raw[len(raw) // 2] ^= 1
            catalog.write_bytes(raw)
            with self.assertRaisesRegex(
                DirichletRootCatalogError, "SHA-256 differs before parsing"
            ):
                audit_root_catalog(
                    catalog, expected_sha256=built["catalog_sha256"]
                )

    def test_symbolic_root_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "roots"
            self._write_roots(root)
            q = next(iter(active_moduli(self.Q_START, self.Q_STOP)))[0]
            artifact = root / root_artifact_filename(q)
            target = root / "target.bin"
            artifact.replace(target)
            artifact.symlink_to(target)
            with (
                patch(
                    "tg_verifier.dirichlet_root_catalog.read_root_artifact_bytes",
                    side_effect=self._fake_parser,
                ),
                self.assertRaisesRegex(
                    DirichletRootCatalogError, "without following links"
                ),
            ):
                build_root_catalog(
                    base / "catalog.ndjson",
                    root,
                    q_start=self.Q_START,
                    q_stop=self.Q_STOP,
                )

    def test_capability_keeps_source_execution_false(self) -> None:
        result = capability()
        self.assertEqual(result["canonical_source_entry_count"], 292_500)
        self.assertTrue(result["TGDRNRO1_parser_reused"])
        self.assertFalse(result["source_catalog_generated"])
        self.assertFalse(result["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
