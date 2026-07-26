# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tg_verifier.dirichlet_lattice_cache import (
    build_cache_catalog,
    cache_shard_filename,
    canonical_json_bytes,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.dirichlet_lattice_stage import SOURCE_Q_T_ROWS
from tg_verifier.dirichlet_source_supervisor import (
    PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED,
    PINNED_SOURCE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED,
    build_structural_kat_contract,
)
from tg_verifier.dirichlet_tmajor_adapter import (
    TMajorTypedBundleLaneAdapter,
)
from tg_verifier.dirichlet_tmajor_spool import (
    AuthenticatedQContiguousSpool,
    DirichletTMajorSpoolError,
    PINNED_SOURCE_LANE_ACTIVE_Q_COUNTS,
    PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES,
    QContiguousRunCursor,
    build_lane_spool,
    build_run_manifest,
    capability,
    replay_run_manifest,
)


class DirichletTMajorSpoolTest(unittest.TestCase):
    def _contract(
        self,
        root: Path,
        *,
        t_rows: int = 3,
        q_stop: int = 10_003,
    ) -> Path:
        cache = root / "cache"
        cache.mkdir()
        plan = source_cache_plan(
            t_index_stop_exclusive=t_rows,
            t_indices_per_shard=t_rows,
        )
        write_synthetic_cache_shard(
            cache / cache_shard_filename(0),
            plan=plan,
            shard_index=0,
        )
        catalog = cache / "catalog.json"
        build_cache_catalog(
            catalog,
            cache,
            plan=plan,
            require_replayed_receipts=False,
        )
        contract = root / "contract.json"
        build_structural_kat_contract(
            contract,
            cache_root=cache,
            cache_catalog=catalog,
            lane_count=1,
            recovery_artifact_sha256="a" * 64,
            recovery_replay_sha256="b" * 64,
            q_tile_size=1,
            q_start=10_001,
            q_stop=q_stop,
        )
        return contract

    def _spool(
        self,
        root: Path,
        *,
        t_rows: int = 3,
        q_stop: int = 10_003,
    ) -> tuple[Path, Path, Path, dict[str, object]]:
        contract = self._contract(root, t_rows=t_rows, q_stop=q_stop)
        spool = root / "lane-0.spool"
        receipt_path = root / "lane-0.spool.receipt.json"
        receipt = build_lane_spool(
            spool,
            receipt_path,
            contract_path=contract,
            lane_index=0,
            allow_structural_kat=True,
        )
        return contract, spool, receipt_path, receipt

    @staticmethod
    def _forge_manifest_receipt(
        original_receipt: dict[str, object],
        *,
        manifest_path: Path,
        receipt_path: Path,
    ) -> dict[str, object]:
        receipt = json.loads(json.dumps(original_receipt))
        raw = manifest_path.read_bytes()
        receipt["manifest"] = {
            "path": str(manifest_path.resolve()),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
        body = dict(receipt)
        body.pop("receipt_sha256")
        receipt["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        return receipt

    def test_bounded_spool_matches_adapter_and_replays_complete_run_roster(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract, _artifact, receipt_path, receipt = self._spool(root)
            adapter = TMajorTypedBundleLaneAdapter(
                contract,
                lane_index=0,
                allow_structural_kat=True,
            )
            adapter_rows = adapter.authenticate_all_rows()
            self.assertEqual(
                receipt["row_schedule_sha256"],
                adapter_rows["row_schedule_sha256"],
            )
            with AuthenticatedQContiguousSpool(
                receipt_path,
                contract_path=contract,
                expected_receipt_sha256=receipt["receipt_sha256"],
                allow_structural_kat=True,
            ) as spool:
                first = spool.run_input(q=10_001, first_t_index=0)
                self.assertEqual(
                    first["target"], adapter.expected_target()
                )
                rows = list(spool.iter_run_rows(first))
                self.assertEqual([row[0] for row in rows], [0, 1, 2])
                self.assertEqual(len(rows[0][1]), 1_048_576)

                manifest = root / "runs.ndjson"
                manifest_receipt_path = root / "runs.receipt.json"
                manifest_receipt = build_run_manifest(
                    manifest,
                    manifest_receipt_path,
                    spool=spool,
                )
                replay = replay_run_manifest(
                    manifest,
                    manifest_receipt_path,
                    spool=spool,
                    expected_receipt_sha256=manifest_receipt[
                        "receipt_sha256"
                    ],
                )
            self.assertEqual(replay["run_count"], 3)
            self.assertEqual(replay["row_reference_count"], 9)
            self.assertFalse(replay["row_resident_cuda_kernel_executed"])
            self.assertFalse(replay["completed_l_zero_state_validated"])
            self.assertFalse(replay["turing_completeness_claimed"])
            self.assertFalse(replay["external_atom_discharged"])

    def test_run_cursor_rejects_substitution_skip_reorder_and_truncation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract, _artifact, receipt_path, receipt = self._spool(root)
            with AuthenticatedQContiguousSpool(
                receipt_path,
                contract_path=contract,
                expected_receipt_sha256=receipt["receipt_sha256"],
                allow_structural_kat=True,
            ) as spool:
                first = spool.run_input(q=10_001, first_t_index=0)
                second = spool.run_input(q=10_002, first_t_index=0)
                third = spool.run_input(q=10_003, first_t_index=0)

                substituted = json.loads(json.dumps(first))
                substituted["row_source"]["row_bindings_sha256"] = "f" * 64
                body = dict(substituted)
                body.pop("run_input_sha256")
                substituted["run_input_sha256"] = hashlib.sha256(
                    canonical_json_bytes(body)
                ).hexdigest()
                with self.assertRaisesRegex(
                    DirichletTMajorSpoolError,
                    "reconstructed target or authenticated row span",
                ):
                    spool.validate_run_input(substituted)

                skipped = QContiguousRunCursor(spool)
                with self.assertRaisesRegex(
                    DirichletTMajorSpoolError,
                    "skipped, substituted, or reordered",
                ):
                    skipped.accept(second)

                reordered = QContiguousRunCursor(spool)
                reordered.accept(first)
                with self.assertRaisesRegex(
                    DirichletTMajorSpoolError,
                    "skipped, substituted, or reordered",
                ):
                    reordered.accept(third)

                truncated = QContiguousRunCursor(spool)
                truncated.accept(first)
                with self.assertRaisesRegex(
                    DirichletTMajorSpoolError, "roster is truncated"
                ):
                    truncated.finish()

    def test_replay_rejects_internally_rehashed_reordered_and_truncated_rosters(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract, _artifact, receipt_path, receipt = self._spool(root)
            with AuthenticatedQContiguousSpool(
                receipt_path,
                contract_path=contract,
                expected_receipt_sha256=receipt["receipt_sha256"],
                allow_structural_kat=True,
            ) as spool:
                manifest = root / "runs.ndjson"
                manifest_receipt_path = root / "runs.receipt.json"
                manifest_receipt = build_run_manifest(
                    manifest,
                    manifest_receipt_path,
                    spool=spool,
                )
                lines = manifest.read_bytes().splitlines(keepends=True)

                reordered_path = root / "runs-reordered.ndjson"
                reordered_path.write_bytes(lines[1] + lines[0] + lines[2])
                reordered_receipt_path = root / "runs-reordered.receipt.json"
                reordered_receipt = self._forge_manifest_receipt(
                    manifest_receipt,
                    manifest_path=reordered_path,
                    receipt_path=reordered_receipt_path,
                )
                with self.assertRaisesRegex(
                    DirichletTMajorSpoolError,
                    "skipped, substituted, or reordered",
                ):
                    replay_run_manifest(
                        reordered_path,
                        reordered_receipt_path,
                        spool=spool,
                        expected_receipt_sha256=reordered_receipt[
                            "receipt_sha256"
                        ],
                    )

                truncated_path = root / "runs-truncated.ndjson"
                truncated_path.write_bytes(lines[0] + lines[1])
                truncated_receipt_path = root / "runs-truncated.receipt.json"
                truncated_receipt = self._forge_manifest_receipt(
                    manifest_receipt,
                    manifest_path=truncated_path,
                    receipt_path=truncated_receipt_path,
                )
                with self.assertRaisesRegex(
                    DirichletTMajorSpoolError, "roster is truncated"
                ):
                    replay_run_manifest(
                        truncated_path,
                        truncated_receipt_path,
                        spool=spool,
                        expected_receipt_sha256=truncated_receipt[
                            "receipt_sha256"
                        ],
                    )

    def test_spool_artifact_substitution_and_truncation_fail_closed(self) -> None:
        for mode in ("substitute", "truncate"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                contract, artifact, receipt_path, receipt = self._spool(root)
                raw = bytearray(artifact.read_bytes())
                if mode == "substitute":
                    raw[200] ^= 1
                else:
                    del raw[-1]
                artifact.write_bytes(raw)
                with self.assertRaisesRegex(
                    DirichletTMajorSpoolError,
                    "differs from its receipt-bound hash or exact size",
                ):
                    AuthenticatedQContiguousSpool(
                        receipt_path,
                        contract_path=contract,
                        expected_receipt_sha256=receipt["receipt_sha256"],
                        allow_structural_kat=True,
                    )

    def test_source_scale_schedule_constants_are_exactly_accounted(self) -> None:
        self.assertEqual(
            sum(PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES),
            SOURCE_Q_T_ROWS,
        )
        self.assertEqual(
            sum(PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED),
            PINNED_SOURCE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED,
        )
        self.assertEqual(
            PINNED_SOURCE_LANE_ACTIVE_Q_COUNTS,
            (
                390_000,
                390_000,
                390_000,
                390_000,
                390_000,
                337_059,
                242_926,
                115_000,
            ),
        )

    def test_capability_preserves_open_execution_and_proof_boundaries(self) -> None:
        result = capability()
        self.assertTrue(
            result["formulaic_fixed_q_run_input_producer_implemented"]
        )
        self.assertTrue(
            result[
                "substitution_skip_reorder_truncation_rejection_implemented"
            ]
        )
        self.assertFalse(result["source_scale_performance_ready"])
        self.assertTrue(result["row_resident_cuda_kernel_implemented"])
        self.assertTrue(
            result[
                "authenticated_spool_to_TGDLTMB1_adapter_implemented"
            ]
        )
        self.assertFalse(
            result["fixed_q_pipeline_executor_consumes_spool_format"]
        )
        self.assertFalse(
            result[
                "discarded_fft_arithmetic_independently_replayed"
            ]
        )
        self.assertFalse(
            result["completed_l_zero_state_import_export_implemented"]
        )
        self.assertFalse(result["zero_completeness_claimed"])
        self.assertFalse(result["turing_completeness_claimed"])
        self.assertFalse(result["trusted_execution_attested"])
        self.assertFalse(result["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
