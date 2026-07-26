# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_cache import (  # noqa: E402
    broadcast_plan,
    build_cache_catalog,
    cache_shard_filename,
    canonical_json_bytes,
    iter_catalog_lane_rows,
    sha256_bytes,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.dirichlet_source_supervisor import (  # noqa: E402
    AuthenticatedLaneReader,
    DirichletSourceSupervisorError,
    LaneHandoffSession,
    PINNED_SOURCE_FFT_BATCHES,
    PINNED_SOURCE_LANE_FFT_BATCHES,
    SOURCE_CONTRACT_CLASSIFICATION,
    STRUCTURAL_KAT_CLASSIFICATION,
    _lane_inventory,
    build_source_contract,
    build_structural_kat_contract,
    capability,
    fft_batch_descriptor,
    load_contract,
    make_q_tile_receipt,
    q_tile_descriptor,
)
from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    group_order,
    modulus_butterflies,
)


class DirichletSourceSupervisorTest(unittest.TestCase):
    def _contract(self, root: Path, *, t_rows: int = 2, lanes: int = 2) -> Path:
        cache = root / "cache"
        cache.mkdir()
        plan = source_cache_plan(
            t_index_stop_exclusive=t_rows,
            t_indices_per_shard=1,
        )
        for shard_index in range(t_rows):
            write_synthetic_cache_shard(
                cache / cache_shard_filename(shard_index),
                plan=plan,
                shard_index=shard_index,
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
            lane_count=lanes,
            recovery_artifact_sha256="a" * 64,
            recovery_replay_sha256="b" * 64,
            q_tile_size=2,
            q_start=10_001,
            q_stop=10_005,
        )
        return contract

    def _accept_all_q_tiles(self, session: LaneHandoffSession) -> None:
        assert session._lease is not None
        ordinal = 0
        while session.expected_q_tile() is not None:
            receipt = make_q_tile_receipt(
                session.contract,
                lane_index=session.lane_index,
                t_index=session._lease.t_index,
                row_payload_sha256=session._lease.payload_sha256,
                q_tile_index=session.expected_q_tile()["q_tile_index"],
                claim_chain_before=session.claim_chain,
                claimed_zero_state_before_sha256=session.claimed_zero_state,
                claimed_fft_pipeline_receipts_sha256=f"{ordinal + 11:064x}",
                claimed_zero_consumer_receipts_sha256=f"{ordinal + 21:064x}",
                claimed_zero_state_after_sha256=f"{ordinal + 31:064x}",
                claimed_worker_measurement_sha256="f" * 64,
            )
            session.accept_q_tile(receipt)
            ordinal += 1

    def test_contract_is_explicitly_nonproduction_and_formulaic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contract_path = self._contract(Path(temporary))
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "explicit authorization"
            ):
                load_contract(contract_path)
            contract = load_contract(
                contract_path, allow_structural_kat=True
            )
            self.assertFalse(contract["decisions"]["source_geometry_complete"])
            self.assertFalse(
                contract["decisions"]["cuda_t_major_kernel_integrated"]
            )
            self.assertEqual(
                contract["classification"], STRUCTURAL_KAT_CLASSIFICATION
            )
            self.assertEqual(contract["schedule"]["q_tile_count"], 3)
            self.assertTrue(
                contract["schedule"][
                    "at_most_one_outstanding_authenticated_row_lease_per_lane"
                ]
            )
            self.assertNotIn(
                "one_authenticated_lattice_row_resident_per_lane",
                contract["schedule"],
            )
            first = q_tile_descriptor(
                contract, t_index=0, q_tile_index=0
            )
            self.assertEqual(
                (first["q_start_inclusive"], first["q_stop_exclusive"]),
                (10_001, 10_003),
            )
            self.assertEqual(first["active_q_count"], 2)

    def test_fft_target_descriptor_is_fixed_q_and_requires_transpose(self) -> None:
        contract = {
            "schedule": {
                "q_start_inclusive": 10_001,
                "q_stop_inclusive": 10_005,
                "q_tile_size": 2,
                "lane_inventory": {
                    "lanes": [
                        {
                            "lane_index": 0,
                            "t_index_start_inclusive": 0,
                            "t_index_stop_exclusive": 130,
                        }
                    ]
                },
            }
        }
        descriptor = fft_batch_descriptor(
            contract, lane_index=0, q=10_001, first_t_index=64
        )
        self.assertEqual(descriptor["batch_count"], 64)
        self.assertEqual(descriptor["t_index_stop_exclusive"], 128)
        self.assertEqual(
            descriptor["value_count"], 64 * group_order(10_001)
        )
        self.assertEqual(
            descriptor["radix2_butterflies"],
            modulus_butterflies(10_001, batch_count=64),
        )
        self.assertTrue(descriptor["requires_q_contiguous_input"])
        self.assertFalse(
            descriptor["current_t_major_lane_directly_executable"]
        )
        with self.assertRaisesRegex(
            DirichletSourceSupervisorError, "lane-aligned"
        ):
            fft_batch_descriptor(
                contract, lane_index=0, q=10_001, first_t_index=1
            )

    def test_source_q_contiguous_fft_target_roster_matches_pinned_totals(
        self,
    ) -> None:
        plan = source_cache_plan()
        assignment = broadcast_plan(plan, lane_count=8)
        inventory = _lane_inventory(
            assignment,
            q_start=10_001,
            q_stop=400_000,
            pin_source_totals=True,
        )
        self.assertEqual(
            tuple(
                lane[
                    "q_contiguous_fft_batch_invocations_if_transposed"
                ]
                for lane in inventory["lanes"]
            ),
            PINNED_SOURCE_LANE_FFT_BATCHES,
        )
        self.assertEqual(
            inventory["totals"][
                "q_contiguous_fft_batch_invocations_if_transposed"
            ],
            PINNED_SOURCE_FFT_BATCHES,
        )

    def test_load_reconstructs_exact_body_and_rejects_unknown_classification(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contract_path = self._contract(Path(temporary))
            value = json.loads(contract_path.read_bytes())
            value["component_interfaces"][
                "FFT_zero_and_measurement_digests_are_claimed_not_validated"
            ] = False
            body = dict(value)
            body.pop("contract_sha256")
            value["contract_sha256"] = sha256_bytes(canonical_json_bytes(body))
            contract_path.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "reconstructed body"
            ):
                load_contract(contract_path, allow_structural_kat=True)

        with tempfile.TemporaryDirectory() as temporary:
            contract_path = self._contract(Path(temporary))
            value = json.loads(contract_path.read_bytes())
            value["classification"] = "similar_but_unrecognized"
            body = dict(value)
            body.pop("contract_sha256")
            value["contract_sha256"] = sha256_bytes(canonical_json_bytes(body))
            contract_path.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "exact enum"
            ):
                load_contract(contract_path, allow_structural_kat=True)

    def test_reader_forbids_two_outstanding_leases_and_reads_only_its_shard(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract_path = self._contract(root, t_rows=4, lanes=2)
            contract = load_contract(
                contract_path, allow_structural_kat=True
            )
            # Lane zero owns shard zero.  Damage lane one's artifact after the
            # immutable contract is bound; lane zero must not traverse it.
            other_index = contract["schedule"]["lane_inventory"]["lanes"][1][
                "storage_shard_start_inclusive"
            ]
            other = root / "cache" / cache_shard_filename(other_index)
            raw = bytearray(other.read_bytes())
            raw[200] ^= 1
            other.write_bytes(raw)

            reader = AuthenticatedLaneReader(
                contract_path,
                lane_index=0,
                allow_structural_kat=True,
            )
            lease = reader.acquire()
            self.assertEqual(lease.t_index, 0)
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "second live"
            ):
                reader.acquire()
            saved_payload = lease.payload
            reader.release(lease)
            next_lease = reader.acquire()
            self.assertNotEqual(next_lease.t_index, lease.t_index)
            reader.release(next_lease)
            reader.finish()
            # The supervisor controls outstanding leases, not references
            # retained by arbitrary caller code.
            self.assertEqual(saved_payload, lease.payload)

            damaged = AuthenticatedLaneReader(
                contract_path,
                lane_index=1,
                allow_structural_kat=True,
            )
            with self.assertRaisesRegex(Exception, "SHA-256 differs"):
                damaged.acquire()

    def test_reader_pins_catalog_between_contract_load_and_lazy_iteration(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract_path = self._contract(root, t_rows=2, lanes=2)
            reader = AuthenticatedLaneReader(
                contract_path,
                lane_index=0,
                allow_structural_kat=True,
            )
            catalog_path = Path(
                reader.contract["cache"]["catalog_file"]["path"]
            )
            replacement = json.loads(catalog_path.read_bytes())
            replacement["shards"][0]["sha256"] = "f" * 64
            body = dict(replacement)
            body.pop("catalog_sha256")
            replacement["catalog_sha256"] = sha256_bytes(
                canonical_json_bytes(body)
            )
            catalog_path.write_bytes(canonical_json_bytes(replacement))
            with self.assertRaisesRegex(
                Exception, "cache catalog file SHA-256 differs"
            ):
                reader.acquire()

    def test_load_can_require_an_external_contract_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contract_path = self._contract(Path(temporary))
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "externally pinned digest"
            ):
                load_contract(
                    contract_path,
                    allow_structural_kat=True,
                    expected_contract_sha256="f" * 64,
                )
            contract = load_contract(
                contract_path, allow_structural_kat=True
            )
            rebound = load_contract(
                contract_path,
                allow_structural_kat=True,
                expected_contract_sha256=contract["contract_sha256"],
            )
            self.assertEqual(
                rebound["contract_sha256"], contract["contract_sha256"]
            )

    def test_lane_session_binds_batches_and_zero_state_before_advancing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contract_path = self._contract(Path(temporary))
            session = LaneHandoffSession(
                contract_path,
                lane_index=0,
                initial_zero_state_sha256="c" * 64,
                allow_structural_kat=True,
            )
            lease = session.begin_row()
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "every active q tile"
            ):
                session.finish_row()

            receipt = make_q_tile_receipt(
                session.contract,
                lane_index=0,
                t_index=lease.t_index,
                row_payload_sha256=lease.payload_sha256,
                q_tile_index=0,
                claim_chain_before=session.claim_chain,
                claimed_zero_state_before_sha256=session.claimed_zero_state,
                claimed_fft_pipeline_receipts_sha256="2" * 64,
                claimed_zero_consumer_receipts_sha256="3" * 64,
                claimed_zero_state_after_sha256="4" * 64,
                claimed_worker_measurement_sha256="5" * 64,
            )
            changed = json.loads(json.dumps(receipt))
            changed["opaque_component_claims"][
                "claimed_zero_state_before_sha256"
            ] = "9" * 64
            body = dict(changed)
            body.pop("receipt_sha256")
            changed["receipt_sha256"] = sha256_bytes(
                canonical_json_bytes(body)
            )
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "input state differs"
            ):
                session.accept_q_tile(changed)

            session.accept_q_tile(receipt)
            self._accept_all_q_tiles(session)
            session.finish_row()
            lane_receipt = session.finish_lane()
            self.assertEqual(lane_receipt["rows_completed"], 1)
            self.assertEqual(
                lane_receipt["decisions"][
                    "maximum_outstanding_authenticated_row_leases"
                ],
                1,
            )
            self.assertIn(
                "component_claim_chain_sha256", lane_receipt
            )
            self.assertNotIn("root_artifact_chain_sha256", lane_receipt)
            self.assertFalse(
                lane_receipt["decisions"][
                    "cuda_t_major_kernel_execution_attested"
                ]
            )

    def test_skipped_or_substituted_q_tile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contract_path = self._contract(Path(temporary))
            session = LaneHandoffSession(
                contract_path,
                lane_index=0,
                initial_zero_state_sha256="c" * 64,
                allow_structural_kat=True,
            )
            lease = session.begin_row()
            skipped = make_q_tile_receipt(
                session.contract,
                lane_index=0,
                t_index=lease.t_index,
                row_payload_sha256=lease.payload_sha256,
                q_tile_index=1,
                claim_chain_before=session.claim_chain,
                claimed_zero_state_before_sha256=session.claimed_zero_state,
                claimed_fft_pipeline_receipts_sha256="2" * 64,
                claimed_zero_consumer_receipts_sha256="3" * 64,
                claimed_zero_state_after_sha256="4" * 64,
                claimed_worker_measurement_sha256="5" * 64,
            )
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "work.*differs"
            ):
                session.accept_q_tile(skipped)

    def test_unified_receipt_chain_covers_every_opaque_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contract_path = self._contract(Path(temporary))
            session = LaneHandoffSession(
                contract_path,
                lane_index=0,
                initial_zero_state_sha256="c" * 64,
                allow_structural_kat=True,
            )
            lease = session.begin_row()
            receipt = make_q_tile_receipt(
                session.contract,
                lane_index=0,
                t_index=lease.t_index,
                row_payload_sha256=lease.payload_sha256,
                q_tile_index=0,
                claim_chain_before=session.claim_chain,
                claimed_zero_state_before_sha256=session.claimed_zero_state,
                claimed_fft_pipeline_receipts_sha256="2" * 64,
                claimed_zero_consumer_receipts_sha256="3" * 64,
                claimed_zero_state_after_sha256="4" * 64,
                claimed_worker_measurement_sha256="5" * 64,
            )
            changed = json.loads(json.dumps(receipt))
            changed["opaque_component_claims"][
                "claimed_worker_measurement_sha256"
            ] = "6" * 64
            body = dict(changed)
            body.pop("receipt_sha256")
            changed["receipt_sha256"] = sha256_bytes(
                canonical_json_bytes(body)
            )
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError, "claim chain differs"
            ):
                session.accept_q_tile(changed)

    def test_production_lane_rejects_invented_component_claims(self) -> None:
        with patch(
            "tg_verifier.dirichlet_source_supervisor.AuthenticatedLaneReader"
        ) as reader:
            reader.return_value.contract = {
                "classification": SOURCE_CONTRACT_CLASSIFICATION
            }
            with self.assertRaisesRegex(
                DirichletSourceSupervisorError,
                "production lane execution is disabled",
            ):
                LaneHandoffSession(
                    Path("/not-opened"),
                    lane_index=0,
                    initial_zero_state_sha256="c" * 64,
                )

    def test_production_builder_rejects_synthetic_cache_before_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract_path = self._contract(root)
            structural = load_contract(
                contract_path, allow_structural_kat=True
            )
            with self.assertRaisesRegex(
                Exception, "higher-precision replay receipts"
            ):
                build_source_contract(
                    root / "production.json",
                    cache_root=root / "cache",
                    cache_catalog=Path(
                        structural["cache"]["catalog_file"]["path"]
                    ),
                    recovery_artifact=root / "missing.bin",
                    recovery_manifest=root / "missing.json",
                    recovery_replay=root / "missing-replay.json",
                    root_artifact_directory=root / "missing-roots",
                    root_catalog=root / "missing-root-catalog.ndjson",
                )

    def test_lane_iterator_rejects_bad_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract_path = self._contract(root)
            contract = load_contract(
                contract_path, allow_structural_kat=True
            )
            with self.assertRaisesRegex(Exception, "outside the plan"):
                next(
                    iter_catalog_lane_rows(
                        root / "cache",
                        Path(contract["cache"]["catalog_file"]["path"]),
                        lane_index=2,
                        lane_count=2,
                    )
                )

    def test_capability_names_the_unimplemented_kernel_seam(self) -> None:
        result = capability()
        self.assertTrue(result["source_wide_contract_implemented"])
        self.assertTrue(result["FFT_receipt_bundle_validator_implemented"])
        self.assertTrue(
            result["typed_bundle_cache_row_admission_adapter_implemented"]
        )
        self.assertTrue(
            result[
                "typed_bundle_lattice_payload_identity_binding_implemented"
            ]
        )
        self.assertFalse(
            result["FFT_receipt_bundle_integrated_into_t_major_lane"]
        )
        self.assertTrue(result["cuda_t_major_kernel_adapter_implemented"])
        self.assertTrue(
            result[
                "authenticated_TGDLTMB1_input_and_replay_implemented"
            ]
        )
        self.assertFalse(result["source_performance_ready"])
        self.assertFalse(result["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
