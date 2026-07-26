# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tg_verifier.dirichlet_lattice_cache as cache  # noqa: E402
import tg_verifier.dirichlet_lattice_certificates as certificates  # noqa: E402
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    SOURCE_RESIDUE_INTERPOLATIONS,
)


class DirichletLatticeCachePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = cache.source_cache_plan()
        cls.broadcast = cache.broadcast_plan(cls.plan)

    def test_full_plan_pins_exact_t_major_geometry(self) -> None:
        self.assertEqual(
            self.plan["plan_sha256"],
            "b86872a3a389f3fb23c5ca0c82c02d0c2605726f245e309e04e3859d7319f98d",
        )
        self.assertEqual(self.plan["storage"]["shard_count"], 1_000)
        self.assertEqual(self.plan["storage"]["row_payload_bytes"], 1 << 20)
        self.assertEqual(
            self.plan["storage"]["lattice_cells"], 4_193_910_784
        )
        self.assertEqual(
            self.plan["storage"]["payload_bytes"], 134_205_145_088
        )
        self.assertEqual(
            self.plan["storage"]["artifact_bytes"], 134_214_624_224
        )
        self.assertTrue(self.plan["complete_large_q_main_grid_geometry"])
        self.assertFalse(self.plan["external_atom_discharged"])

    def test_storage_shards_are_gap_free_and_bounded(self) -> None:
        shards = self.plan["storage_shards"]
        self.assertEqual(shards[0]["t_index_start_inclusive"], 0)
        self.assertEqual(
            shards[-1]["t_index_stop_exclusive"], cache.SOURCE_T_INDEX_STOP
        )
        for left, right in zip(shards, shards[1:]):
            self.assertEqual(
                left["t_index_stop_exclusive"],
                right["t_index_start_inclusive"],
            )
        self.assertTrue(
            all(
                1 <= shard["t_index_count"] <= cache.DEFAULT_T_INDICES_PER_SHARD
                for shard in shards
            )
        )

    def test_broadcast_lanes_cover_each_storage_shard_once(self) -> None:
        lanes = self.broadcast["lanes"]
        self.assertEqual(lanes[0]["storage_shard_start_inclusive"], 0)
        self.assertEqual(
            lanes[-1]["storage_shard_stop_exclusive"],
            self.plan["storage"]["shard_count"],
        )
        for left, right in zip(lanes, lanes[1:]):
            self.assertEqual(
                left["storage_shard_stop_exclusive"],
                right["storage_shard_start_inclusive"],
            )
            self.assertEqual(
                left["t_index_stop_exclusive"],
                right["t_index_start_inclusive"],
            )
        self.assertEqual(
            self.broadcast["totals"]["cache_payload_bytes"],
            cache.SOURCE_CACHE_PAYLOAD_BYTES,
        )
        self.assertEqual(
            self.broadcast["totals"]["residue_interpolations"],
            SOURCE_RESIDUE_INTERPOLATIONS,
        )
        self.assertFalse(self.broadcast["cuda_broadcaster_integrated"])

    def test_projection_is_only_a_component_sensitivity(self) -> None:
        result = cache.projection(
            authenticated_file_bytes_per_second=2_000_000_000,
            analytic_cells_per_second=1_000,
        )
        geometry = result["source_geometry"]
        self.assertEqual(
            geometry["strict_reader_physical_bytes"],
            2 * self.plan["storage"]["artifact_bytes"],
        )
        self.assertGreater(
            geometry["lattice_payload_reduction_ratio"], 38_000
        )
        self.assertEqual(
            geometry["remaining_non_lattice_compact_input_bytes"],
            41_279_640_994_288,
        )
        self.assertEqual(
            geometry["t_major_compact_input_bytes"], 41_413_846_139_376
        )
        self.assertGreater(geometry["total_compact_input_reduction_ratio"], 125)
        self.assertFalse(result["h100_end_to_end_runtime_estimated"])
        self.assertFalse(result["external_atom_discharged"])

    def test_cli_plan_is_canonical_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/tg_dirichlet_lattice_cache.py", "plan"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        parsed = json.loads(completed.stdout)
        self.assertEqual(parsed["plan_sha256"], self.plan["plan_sha256"])


class DirichletLatticeCacheArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _single_plan(self) -> dict[str, object]:
        return cache.source_cache_plan(
            t_index_stop_exclusive=1, t_indices_per_shard=1
        )

    def _write_single(self, parent: str = "cache") -> tuple[Path, dict[str, object]]:
        plan = self._single_plan()
        root = self.root / parent
        root.mkdir()
        path = root / cache.cache_shard_filename(0)
        report = cache.write_synthetic_cache_shard(
            path, plan=plan, shard_index=0
        )
        return path, report

    def test_synthetic_shard_is_byte_deterministic_and_bounded(self) -> None:
        first, first_report = self._write_single("first")
        second, second_report = self._write_single("second")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(
            first_report["artifact"]["sha256"],
            second_report["artifact"]["sha256"],
        )
        self.assertEqual(
            first.stat().st_size,
            cache.HEADER.size
            + cache.ROW_HEADER.size
            + cache.ROW_PAYLOAD_BYTES
            + cache.FOOTER.size,
        )
        rows = list(
            cache.iter_authenticated_cache_rows(
                first,
                plan=self._single_plan(),
                shard_index=0,
                expected_sha256=first_report["artifact"]["sha256"],
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 0)
        self.assertEqual(len(rows[0][1]), 1 << 20)
        checked = cache.validate_lattice_row(rows[0][1])
        self.assertEqual(checked["lattice_cells"], 2048 * 16)

    def test_row_corruption_fails_before_the_row_is_yielded(self) -> None:
        source, _report = self._write_single()
        corrupt = self.root / "corrupt" / cache.cache_shard_filename(0)
        corrupt.parent.mkdir()
        shutil.copyfile(source, corrupt)
        with corrupt.open("r+b") as output:
            output.seek(cache.HEADER.size + cache.ROW_HEADER.size + 19)
            original = output.read(1)
            output.seek(-1, 1)
            output.write(bytes([original[0] ^ 1]))
        iterator = cache.iter_authenticated_cache_rows(
            corrupt, plan=self._single_plan(), shard_index=0
        )
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "row SHA-256"
        ):
            next(iterator)

    def test_expected_whole_file_hash_fails_before_parsing(self) -> None:
        source, report = self._write_single()
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "before parsing"
        ):
            next(
                cache.iter_authenticated_cache_rows(
                    source,
                    plan=self._single_plan(),
                    shard_index=0,
                    expected_sha256="0" * 64,
                )
            )
        self.assertNotEqual(report["artifact"]["sha256"], "0" * 64)

    def test_symbolic_link_cache_shard_is_rejected(self) -> None:
        source, _report = self._write_single()
        linked_root = self.root / "linked"
        linked_root.mkdir()
        linked = linked_root / cache.cache_shard_filename(0)
        linked.symlink_to(source)
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "without following links"
        ):
            next(
                cache.iter_authenticated_cache_rows(
                    linked, plan=self._single_plan(), shard_index=0
                )
            )

    def test_footer_corruption_fails_on_iterator_exhaustion(self) -> None:
        source, _report = self._write_single()
        corrupt = self.root / "footer" / cache.cache_shard_filename(0)
        corrupt.parent.mkdir()
        shutil.copyfile(source, corrupt)
        with corrupt.open("r+b") as output:
            output.seek(-1, 2)
            original = output.read(1)
            output.seek(-1, 1)
            output.write(bytes([original[0] ^ 1]))
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "footer or global digest"
        ):
            list(
                cache.iter_authenticated_cache_rows(
                    corrupt, plan=self._single_plan(), shard_index=0
                )
            )

    def test_header_is_bound_to_the_exact_plan(self) -> None:
        source, _report = self._write_single()
        other_plan = cache.source_cache_plan(
            t_index_stop_exclusive=2, t_indices_per_shard=1
        )
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "plan binding"
        ):
            next(
                cache.iter_authenticated_cache_rows(
                    source, plan=other_plan, shard_index=0
                )
            )

    def test_invalid_interval_is_rejected_by_bounded_decoder(self) -> None:
        payload = bytearray(cache.ROW_PAYLOAD_BYTES)
        payload[: cache.LATTICE_CELL.size] = cache.LATTICE_CELL.pack(
            1.0, -1.0, 0.0, 0.0
        )
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "malformed complex interval"
        ):
            cache.validate_lattice_row(bytes(payload))

    def test_gap_free_synthetic_catalog_and_stream_replay(self) -> None:
        plan = cache.source_cache_plan(
            t_index_stop_exclusive=3, t_indices_per_shard=1
        )
        root = self.root / "catalog-root"
        root.mkdir()
        for shard_index in range(3):
            cache.write_synthetic_cache_shard(
                root / cache.cache_shard_filename(shard_index),
                plan=plan,
                shard_index=shard_index,
            )
        catalog_path = root / "catalog.json"
        catalog = cache.build_cache_catalog(
            catalog_path,
            root,
            plan=plan,
            require_replayed_receipts=False,
        )
        self.assertFalse(
            catalog["decisions"][
                "all_shards_bind_higher_precision_replay_receipts"
            ]
        )
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertEqual(len(digest), 64)
        rows = list(cache.iter_catalog_rows(root, catalog_path))
        self.assertEqual([t_index for t_index, _payload in rows], [0, 1, 2])
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "higher-precision replay"
        ):
            next(
                cache.iter_catalog_rows(
                    root, catalog_path, require_replayed=True
                )
            )

    def test_range_stream_authenticates_complete_boundary_shards(self) -> None:
        plan = cache.source_cache_plan(
            t_index_stop_exclusive=6, t_indices_per_shard=3
        )
        root = self.root / "range-root"
        root.mkdir()
        for shard_index in range(2):
            cache.write_synthetic_cache_shard(
                root / cache.cache_shard_filename(shard_index),
                plan=plan,
                shard_index=shard_index,
            )
        catalog_path = root / "catalog.json"
        cache.build_cache_catalog(
            catalog_path,
            root,
            plan=plan,
            require_replayed_receipts=False,
        )
        catalog_file_sha256 = hashlib.sha256(
            catalog_path.read_bytes()
        ).hexdigest()
        identity: dict[str, object] = {}
        rows = list(
            cache.iter_catalog_range_rows(
                root,
                catalog_path,
                t_index_start_inclusive=2,
                t_index_stop_exclusive=4,
                expected_catalog_sha256=catalog_file_sha256,
                authenticated_identity=identity,
            )
        )
        self.assertEqual([index for index, _payload in rows], [2, 3])
        self.assertEqual(identity["selected_row_count"], 2)
        self.assertEqual(identity["authenticated_physical_row_count"], 6)
        self.assertEqual(
            identity["authenticated_unselected_boundary_row_count"], 4
        )
        self.assertEqual(
            identity["authenticated_physical_file_bytes"],
            2 * plan["storage"]["artifact_bytes"],
        )
        self.assertTrue(
            identity["full_touched_shard_footers_authenticated"]
        )
        self.assertEqual(
            [
                shard["shard_index"]
                for shard in identity["touched_shards"]
            ],
            [0, 1],
        )

    def test_range_stream_rejects_bad_pin_range_and_boundary_tamper(
        self,
    ) -> None:
        plan = cache.source_cache_plan(
            t_index_stop_exclusive=3, t_indices_per_shard=3
        )
        root = self.root / "range-attacks"
        root.mkdir()
        shard_path = root / cache.cache_shard_filename(0)
        cache.write_synthetic_cache_shard(
            shard_path, plan=plan, shard_index=0
        )
        catalog_path = root / "catalog.json"
        cache.build_cache_catalog(
            catalog_path,
            root,
            plan=plan,
            require_replayed_receipts=False,
        )
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "catalog file SHA-256"
        ):
            next(
                cache.iter_catalog_range_rows(
                    root,
                    catalog_path,
                    t_index_start_inclusive=1,
                    t_index_stop_exclusive=2,
                    expected_catalog_sha256="0" * 64,
                )
            )
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "outside its exact t coverage"
        ):
            next(
                cache.iter_catalog_range_rows(
                    root,
                    catalog_path,
                    t_index_start_inclusive=2,
                    t_index_stop_exclusive=4,
                )
            )

        # The selected row is t=1, but a mutation in the unselected t=2
        # boundary suffix must still reject the range before it can be
        # treated as a completely authenticated input.
        with shard_path.open("r+b") as output:
            offset = (
                cache.HEADER.size
                + 2 * (cache.ROW_HEADER.size + cache.ROW_PAYLOAD_BYTES)
                + cache.ROW_HEADER.size
                + 17
            )
            output.seek(offset)
            original = output.read(1)
            output.seek(-1, 1)
            output.write(bytes((original[0] ^ 1,)))
        iterator = cache.iter_catalog_range_rows(
            root,
            catalog_path,
            t_index_start_inclusive=1,
            t_index_stop_exclusive=2,
        )
        with self.assertRaisesRegex(
            cache.DirichletLatticeCacheError, "SHA-256 differs before parsing"
        ):
            next(iterator)

    def test_replayed_repacker_binds_the_complete_provenance_chain(self) -> None:
        # This is a structural unit test of the repacker/certificate plumbing.
        # The explicitly mocked replay result is not retained evidence and
        # cannot be produced by the operator CLI without running Arb replay.
        plan = self._single_plan()
        certificate_root = self.root / "certificate"
        certificate_root.mkdir()
        lattice_path = certificate_root / "lattice-input.bin"
        lattice_bytes = (
            cache.LEGACY_INPUT_HEADER.pack(
                cache.LEGACY_INPUT_MAGIC,
                1,
                cache.LATTICE_ROWS,
                cache.TAYLOR_DEGREE,
                0,
                0,
                64,
                1,
                cache.CELLS_PER_T_INDEX,
                0,
            )
            + cache._synthetic_row(0)
            + bytes(24)
        )
        lattice_path.write_bytes(lattice_bytes)
        lattice_sha = hashlib.sha256(lattice_bytes).hexdigest()
        manifest = {
            "certificate_sha256": "1" * 64,
            "artifacts": {
                "lattice-input.bin": {
                    "sha256": lattice_sha,
                    "size_bytes": len(lattice_bytes),
                }
            },
        }
        parameters = {
            "t_index": 0,
            "M": 4,
            "generation_precision_bits": 192,
            "second_generation_precision_bits": 256,
        }
        replay = {
            "certificate_sha256": "1" * 64,
            "replay_sha256": "2" * 64,
            "replay_precision_bits": 320,
            "lattice_cells_replayed": cache.CELLS_PER_T_INDEX,
            "higher_precision_arb_containment_passed": True,
        }
        output_root = self.root / "replayed"
        output_root.mkdir()
        artifact = output_root / cache.cache_shard_filename(0)
        receipt = output_root / "lattice-shard-0000.receipt.json"
        with (
            mock.patch.object(
                certificates, "_load_manifest", return_value=manifest
            ),
            mock.patch.object(
                certificates,
                "_manifest_parameters",
                return_value=parameters,
            ),
            mock.patch.object(
                certificates, "_require_artifact", return_value=lattice_path
            ),
            mock.patch.object(
                certificates, "replay_certificate", return_value=replay
            ),
        ):
            packed = cache.pack_replayed_lattice_certificates(
                artifact,
                receipt,
                plan=plan,
                shard_index=0,
                certificate_roots=[certificate_root],
            )
        self.assertTrue(
            packed["decisions"][
                "every_hurwitz_cell_higher_precision_replayed_before_pack"
            ]
        )
        catalog_path = output_root / "catalog.json"
        catalog = cache.build_cache_catalog(
            catalog_path,
            output_root,
            plan=plan,
            require_replayed_receipts=True,
        )
        self.assertTrue(
            catalog["decisions"][
                "all_shards_bind_higher_precision_replay_receipts"
            ]
        )
        self.assertFalse(
            catalog["decisions"]["replay_receipt_execution_attested"]
        )
        rows = list(
            cache.iter_catalog_rows(
                output_root, catalog_path, require_replayed=True
            )
        )
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
