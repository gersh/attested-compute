# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from tg_verifier.dirichlet_lattice_cache import (
    build_cache_catalog,
    cache_shard_filename,
    canonical_json_bytes,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.dirichlet_source_supervisor import (
    build_structural_kat_contract,
)
from tg_verifier.dirichlet_tblock_supervisor import (
    CHECKPOINT_CHAIN_DOMAIN,
    DirichletTBlockSupervisorError,
    PRODUCTION_WORKER_CLASSIFICATION,
    _chain,
    run_supervisor,
    validate_worker_handshake,
)
from tg_verifier.dirichlet_tblock_bundle_supervisor import (
    validate_bundle_worker_handshake,
)
from tg_verifier.dirichlet_tblock_bundle_worker import bundle_handshake
from tg_verifier.dirichlet_tblock_plan_switch_worker import native_handshake
import tg_verifier.dirichlet_tblock_plan_switch_worker as plan_switch_worker
from tg_verifier.dirichlet_tblock_worker import structural_handshake
from tg_verifier.dirichlet_tmajor_spool import build_lane_spool
from tests.azure_measured_worker_test_scope import (
    bounded_measured_worker_test_scope,
)


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "tools" / "tg_dirichlet_tblock_worker.py"


class DirichletTBlockSupervisorTest(unittest.TestCase):
    def _fixture(
        self,
        root: Path,
        *,
        t_rows: int,
        q_stop: int = 10_003,
    ) -> tuple[Path, Path, dict[str, object]]:
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
        spool = root / "lane-0.spool"
        spool_receipt = root / "lane-0.spool.receipt.json"
        receipt = build_lane_spool(
            spool,
            spool_receipt,
            contract_path=contract,
            lane_index=0,
            allow_structural_kat=True,
        )
        return contract, spool_receipt, receipt

    @staticmethod
    def _command(*extra: str) -> list[str]:
        return [sys.executable, str(WORKER), *extra]

    def _run(
        self,
        root: Path,
        *,
        contract: Path,
        spool_receipt: Path,
        receipt: dict[str, object],
        checkpoints: Path | None = None,
        output: Path | None = None,
        command: list[str] | None = None,
        expected_checkpoint_chain_sha256: str | None = None,
        stop_after_blocks: int | None = None,
    ) -> dict[str, object]:
        with bounded_measured_worker_test_scope():
            return run_supervisor(
                output or root / "supervisor.receipt.json",
                checkpoints or root / "checkpoints",
                contract_path=contract,
                spool_receipt_path=spool_receipt,
                expected_spool_receipt_sha256=str(
                    receipt["receipt_sha256"]
                ),
                worker_command=command or self._command(),
                allow_structural_kat=True,
                expected_checkpoint_chain_sha256=(
                    expected_checkpoint_chain_sha256
                ),
                stop_after_blocks=stop_after_blocks,
            )

    def test_one_block_streams_once_and_enumerates_exact_roster(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract, spool_receipt, receipt = self._fixture(
                root, t_rows=2
            )
            result = self._run(
                root,
                contract=contract,
                spool_receipt=spool_receipt,
                receipt=receipt,
            )
            self.assertTrue(result["complete"])
            self.assertEqual(result["completed_block_count"], 1)
            self.assertEqual(result["active_q_target_count"], 3)
            self.assertEqual(result["target_row_reference_count"], 6)
            self.assertTrue(
                result["decisions"]["each_new_block_streamed_once"]
            )
            self.assertFalse(
                result["decisions"]["q_major_line_manifest_materialized"]
            )
            self.assertFalse(
                result["decisions"]["external_atom_discharged"]
            )

    def test_resume_reuses_checkpoint_and_streams_only_new_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract, spool_receipt, receipt = self._fixture(
                root, t_rows=65, q_stop=10_001
            )
            partial = self._run(
                root,
                contract=contract,
                spool_receipt=spool_receipt,
                receipt=receipt,
                stop_after_blocks=1,
            )
            self.assertFalse(partial["complete"])
            self.assertEqual(partial["completed_block_count"], 1)
            self.assertFalse((root / "supervisor.receipt.json").exists())
            completed = self._run(
                root,
                contract=contract,
                spool_receipt=spool_receipt,
                receipt=receipt,
                expected_checkpoint_chain_sha256=partial[
                    "checkpoint_chain_sha256"
                ],
            )
            self.assertTrue(completed["complete"])
            self.assertEqual(completed["completed_block_count"], 2)
            self.assertEqual(completed["active_q_target_count"], 2)
            self.assertEqual(completed["target_row_reference_count"], 65)

    def test_checkpoint_replay_rejects_substitution_skip_reorder_and_truncation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            contract, spool_receipt, receipt = self._fixture(
                source, t_rows=65, q_stop=10_001
            )
            completed = self._run(
                source,
                contract=contract,
                spool_receipt=spool_receipt,
                receipt=receipt,
            )
            pinned_head = str(completed["checkpoint_chain_sha256"])
            original = source / "checkpoints"

            substituted = root / "substituted"
            shutil.copytree(original, substituted)
            first_path = substituted / "block-00000000.checkpoint.json"
            first = json.loads(first_path.read_bytes())
            first["response"]["active_q_count"] += 1
            response_body = dict(first["response"])
            response_body.pop("response_sha256")
            first["response"]["response_sha256"] = hashlib.sha256(
                canonical_json_bytes(response_body)
            ).hexdigest()
            checkpoint_body = dict(first)
            checkpoint_body.pop("checkpoint_sha256")
            checkpoint_body["checkpoint_chain_after"] = _chain(
                CHECKPOINT_CHAIN_DOMAIN,
                checkpoint_body["checkpoint_chain_before"],
                {
                    key: value
                    for key, value in checkpoint_body.items()
                    if key != "checkpoint_chain_after"
                },
            )
            first["checkpoint_chain_after"] = checkpoint_body[
                "checkpoint_chain_after"
            ]
            checkpoint_body = dict(first)
            checkpoint_body.pop("checkpoint_sha256")
            first["checkpoint_sha256"] = hashlib.sha256(
                canonical_json_bytes(checkpoint_body)
            ).hexdigest()
            first_path.write_bytes(canonical_json_bytes(first))
            with self.assertRaises(DirichletTBlockSupervisorError):
                self._run(
                    root,
                    contract=contract,
                    spool_receipt=spool_receipt,
                    receipt=receipt,
                    checkpoints=substituted,
                    output=root / "substituted.receipt.json",
                    expected_checkpoint_chain_sha256=pinned_head,
                )

            skipped = root / "skipped"
            shutil.copytree(original, skipped)
            (skipped / "block-00000000.checkpoint.json").unlink()
            with self.assertRaisesRegex(
                DirichletTBlockSupervisorError, "skip"
            ):
                self._run(
                    root,
                    contract=contract,
                    spool_receipt=spool_receipt,
                    receipt=receipt,
                    checkpoints=skipped,
                    output=root / "skipped.receipt.json",
                    expected_checkpoint_chain_sha256=pinned_head,
                )

            reordered = root / "reordered"
            shutil.copytree(original, reordered)
            zero = reordered / "block-00000000.checkpoint.json"
            one = reordered / "block-00000001.checkpoint.json"
            zero_raw, one_raw = zero.read_bytes(), one.read_bytes()
            zero.write_bytes(one_raw)
            one.write_bytes(zero_raw)
            with self.assertRaisesRegex(
                DirichletTBlockSupervisorError, "substituted|reordered"
            ):
                self._run(
                    root,
                    contract=contract,
                    spool_receipt=spool_receipt,
                    receipt=receipt,
                    checkpoints=reordered,
                    output=root / "reordered.receipt.json",
                    expected_checkpoint_chain_sha256=pinned_head,
                )

            truncated = root / "truncated"
            shutil.copytree(original, truncated)
            (truncated / "block-00000001.checkpoint.json").unlink()
            with self.assertRaisesRegex(
                DirichletTBlockSupervisorError, "external pin"
            ):
                self._run(
                    root,
                    contract=contract,
                    spool_receipt=spool_receipt,
                    receipt=receipt,
                    checkpoints=truncated,
                    output=root / "truncated.receipt.json",
                    expected_checkpoint_chain_sha256=pinned_head,
                )

    def test_downstream_failure_substitution_and_truncation_leave_no_checkpoint(
        self,
    ) -> None:
        for option in (
            "--fail-on-sequence",
            "--substitute-response-on-sequence",
            "--truncate-response-on-sequence",
        ):
            with (
                self.subTest(option=option),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                contract, spool_receipt, receipt = self._fixture(
                    root, t_rows=1, q_stop=10_001
                )
                with self.assertRaises(DirichletTBlockSupervisorError):
                    self._run(
                        root,
                        contract=contract,
                        spool_receipt=spool_receipt,
                        receipt=receipt,
                        command=self._command(option, "0"),
                    )
                checkpoints = root / "checkpoints"
                self.assertEqual(list(checkpoints.glob("*.json")), [])
                self.assertFalse((root / "supervisor.receipt.json").exists())

    def test_structural_worker_fails_production_capability_admission(self) -> None:
        handshake = structural_handshake(
            Path(
                sys.modules[
                    "tg_verifier.dirichlet_tblock_worker"
                ].__file__
            )
        )
        with self.assertRaisesRegex(
            DirichletTBlockSupervisorError,
            "production multi-q",
        ):
            validate_worker_handshake(
                handshake,
                production_contract=True,
                allow_structural_kat=False,
                expected_handshake_sha256=handshake["handshake_sha256"],
                expected_implementation_sha256=handshake[
                    "worker_implementation_sha256"
                ],
            )

    def test_all_true_self_asserted_worker_still_cannot_enter_production(
        self,
    ) -> None:
        implementation = Path(
            sys.modules[
                "tg_verifier.dirichlet_tblock_worker"
            ].__file__
        )
        handshake = structural_handshake(implementation)
        handshake["classification"] = PRODUCTION_WORKER_CLASSIFICATION
        handshake["capabilities"] = {
            key: True for key in handshake["capabilities"]
        }
        body = dict(handshake)
        body.pop("handshake_sha256")
        handshake["handshake_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        with self.assertRaisesRegex(
            DirichletTBlockSupervisorError,
            "framed typed-bundle bytes",
        ):
            validate_worker_handshake(
                handshake,
                production_contract=True,
                allow_structural_kat=False,
                expected_handshake_sha256=handshake["handshake_sha256"],
                expected_implementation_sha256=handshake[
                    "worker_implementation_sha256"
                ],
            )

    def test_v2_bundle_transport_handshake_still_fails_production(self) -> None:
        implementation = Path(
            sys.modules[
                "tg_verifier.dirichlet_tblock_bundle_worker"
            ].__file__
        )
        handshake = bundle_handshake(implementation)
        with self.assertRaisesRegex(
            DirichletTBlockSupervisorError,
            "production admission is disabled",
        ):
            validate_bundle_worker_handshake(
                handshake,
                production_contract=True,
                allow_structural_kat=False,
                expected_handshake_sha256=handshake["handshake_sha256"],
                expected_implementation_sha256=handshake[
                    "worker_implementation_sha256"
                ],
            )

    def test_native_plan_switch_requires_all_external_pins_and_stays_nonproduction(
        self,
    ) -> None:
        handshake = native_handshake(
            Path(plan_switch_worker.__file__),
            launcher_path=(
                ROOT / "tools/tg_dirichlet_tblock_plan_switch_worker.py"
            ),
            recipe={
                "recipe_sha256": "a" * 64,
                "storage_policy": {
                    "event_storage_mode": (
                        "compact_associative_mmr_summary"
                    ),
                    "maximum_event_bytes_per_target": 1024,
                    "maximum_retained_output_bytes": 2048,
                    "raw_event_streams_retained_for_typed_bundle_resume": False,
                    "compact_event_summary_replayed_on_resume": True,
                    "source_scale_storage_admitted": False,
                },
            },
            runtime_artifacts_sha256="b" * 64,
        )
        with self.assertRaisesRegex(
            DirichletTBlockSupervisorError,
            "requires external worker handshake",
        ):
            validate_bundle_worker_handshake(
                handshake,
                production_contract=False,
                allow_structural_kat=True,
                allow_native_plan_switch_kat=True,
                expected_recipe_sha256="a" * 64,
                expected_runtime_artifacts_sha256="b" * 64,
            )
        with self.assertRaisesRegex(
            DirichletTBlockSupervisorError,
            "production admission is disabled",
        ):
            validate_bundle_worker_handshake(
                handshake,
                production_contract=True,
                allow_structural_kat=False,
                allow_native_plan_switch_kat=True,
                expected_handshake_sha256=handshake[
                    "handshake_sha256"
                ],
                expected_implementation_sha256=handshake[
                    "worker_implementation_sha256"
                ],
                expected_recipe_sha256="a" * 64,
                expected_runtime_artifacts_sha256="b" * 64,
            )


if __name__ == "__main__":
    unittest.main()
