# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.tg_dirichlet_residue_composition_fixture import (  # noqa: E402
    rehash_job_artifact,
    write_job,
)
from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    group_order,
    modulus_butterflies,
)
from tg_verifier.dirichlet_campaign import primitive_character_count  # noqa: E402
from tg_verifier.dirichlet_fft_pipeline_bundle import (  # noqa: E402
    DirichletFFTPipelineBundleError,
    build_bundle,
    capability,
    replay_bundle,
)
from tg_verifier.dirichlet_lattice_cache import (  # noqa: E402
    _synthetic_row,
    build_cache_catalog,
    cache_shard_filename,
    canonical_json_bytes,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    INPUT_HEADER as LATTICE_INPUT_HEADER,
    LATTICE_CELL,
    LATTICE_ROWS,
    TAYLOR_COLUMNS,
)
from tg_verifier.dirichlet_residue_composition import (  # noqa: E402
    CompositionEngine,
    FRAMED_REQUEST_SCHEMA,
)
from tg_verifier.dirichlet_root_number_stage import (  # noqa: E402
    CONVENTION_SHA256,
    ROOT_ALGORITHM_ID,
)
from tg_verifier.dirichlet_source_supervisor import (  # noqa: E402
    build_structural_kat_contract,
)
from tg_verifier.dirichlet_stream_zero_consumer import (  # noqa: E402
    ALGORITHM_ID as CONSUMER_ALGORITHM_ID,
    EVENT_FILE_SCHEMA,
    RECEIPT_SCHEMA as CONSUMER_RECEIPT_SCHEMA,
    make_control,
)
from tg_verifier.dirichlet_tmajor_adapter import (  # noqa: E402
    DirichletTMajorAdapterError,
    MANIFEST_LINE_SCHEMA,
    TMajorTypedBundleLaneAdapter,
    admit_lane_manifest,
    capability as tmajor_adapter_capability,
)


def _artifact(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _self_hash(value: dict[str, object], field: str) -> None:
    body = dict(value)
    body.pop(field, None)
    value[field] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _merkle_one(receipt_sha256: str) -> str:
    return hashlib.sha256(bytes.fromhex(receipt_sha256)).hexdigest()


class DirichletFFTPipelineBundleTest(unittest.TestCase):
    def _contract(self, root: Path, *, t_rows: int = 2) -> Path:
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
            q_stop=10_001,
        )
        return contract

    def _pipeline(
        self,
        root: Path,
        *,
        t_indices: tuple[int, ...] = (0, 1),
        bind_tmajor_cache_rows: bool = False,
    ) -> tuple[Path, dict[str, object]]:
        job_path, frames = write_job(root / "job", t_indices=t_indices)
        if bind_tmajor_cache_rows:
            payload_start = LATTICE_INPUT_HEADER.size
            payload_stop = (
                payload_start
                + LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
            )
            for frame_index, (t_index, frame) in enumerate(
                zip(t_indices, frames)
            ):
                lattice_input = frame["lattice_input"]
                raw = bytearray(lattice_input.read_bytes())
                raw[payload_start:payload_stop] = _synthetic_row(t_index)
                lattice_input.write_bytes(raw)
                rehash_job_artifact(
                    job_path,
                    frame_index,
                    "lattice_input",
                )
        composition_receipt = root / "composition-receipt.json"
        stream = io.BytesIO()
        report = CompositionEngine(max_batch_count=64).compose_stream(
            job_path,
            stream,
            receipt_path=composition_receipt,
            allow_synthetic_kat=True,
        )
        input_stream = stream.getvalue()
        composition_controls = root / "composition.ndjson"
        composition_controls.write_bytes(
            canonical_json_bytes(
                {
                    "schema": FRAMED_REQUEST_SCHEMA,
                    "schema_version": 1,
                    "job": str(job_path),
                    "receipt": str(composition_receipt),
                }
            )
        )
        upstream = {
            "all_character_transform_input_sha256": "1" * 64,
            "finite_addback_receipt_sha256": "2" * 64,
            "lattice_tail_receipt_sha256": "3" * 64,
            "residue_adapter_receipt_sha256": "4" * 64,
        }
        consumer_controls = root / "consumer.ndjson"
        consumer_controls.write_bytes(
            canonical_json_bytes(
                make_control(
                    frame_index=0,
                    q=10_001,
                    batch_count=len(t_indices),
                    first_t_numerator=5 * t_indices[0],
                    t_denominator=64,
                    t_step_numerator=5,
                    upstream_receipts=upstream,
                    root_number_mode=ROOT_ALGORITHM_ID,
                )
            )
        )

        composer = {
            "kind": (
                "sparkinterval.tg.dirichlet_residue_composition."
                "framed_stream.v1"
            ),
            "classification": "composition_stream_adapter_not_atom_closure",
            "q": 10_001,
            "maximum_batch_count": 64,
            "frame_count": 1,
            "slice_count": len(t_indices),
            "value_count": len(t_indices) * group_order(10_001),
            "first_t_numerator": 5 * t_indices[0],
            "t_denominator": 64,
            "t_step_numerator": 5,
            "TGDAFFI1_stream_sha256": hashlib.sha256(input_stream).hexdigest(),
            "control_jsonl_sha256": hashlib.sha256(
                composition_controls.read_bytes()
            ).hexdigest(),
            "stream_size_bytes": (
                INPUT_HEADER.size
                + len(t_indices) * group_order(10_001) * COMPLEX_INTERVAL.size
            ),
            "composition_receipt_merkle_sha256": _merkle_one(
                report["receipt_sha256"]
            ),
            "retained_output_frames": 0,
            "persistent_allchars_framed_service_compatible": True,
            "full_source_run_completed": False,
            "external_atom_discharged": False,
        }
        _self_hash(composer, "summary_sha256")
        composer_path = root / "composer-summary.json"
        composer_path.write_bytes(canonical_json_bytes(composer))

        transform_output_sha = "d" * 64
        transform = {
            "kind": "sparkinterval.tg.dirichlet_allchars.framed_service.v1",
            "algorithm": "platt-dirichlet-allchars-bluestein-v1",
            "q": 10_001,
            "maximum_batch_count": 64,
            "frame_count": 1,
            "slice_count": len(t_indices),
            "value_count": len(t_indices) * group_order(10_001),
            "radix2_butterflies": modulus_butterflies(
                10_001, batch_count=len(t_indices)
            ),
            "preparation_nanoseconds": 1,
            "elapsed_nanoseconds": 2,
            "retained_input_frames": 0,
            "retained_output_frames": 0,
            "input_stream_sha256": hashlib.sha256(input_stream).hexdigest(),
            "output_stream_sha256": transform_output_sha,
        }
        transform_path = root / "transform-summary.json"
        transform_path.write_bytes(canonical_json_bytes(transform))

        events_path = root / "events.ndjson"
        events_path.write_bytes(
            canonical_json_bytes(
                {
                    "classification": (
                        "multiplicity-lower-bound-events-not-zero-completeness"
                    ),
                    "kind": EVENT_FILE_SCHEMA,
                    "schema_version": 1,
                }
            )
        )
        root_path = root / "roots.bin"
        root_path.write_bytes(b"typed-root-fixture")
        root_receipt = {
            "kind": "fixture-root-receipt",
            "receipt_sha256": "9" * 64,
        }
        root_receipt_path = root / "roots.json"
        root_receipt_path.write_bytes(canonical_json_bytes(root_receipt))
        root_metadata: dict[str, object] = {
            "q": 10_001,
            "primitive_character_count": primitive_character_count(10_001),
            "root_artifact_sha256": hashlib.sha256(
                root_path.read_bytes()
            ).hexdigest(),
            "transform_output_sha256": "e" * 64,
        }
        root_binding = {
            "artifact_sha256": root_metadata["root_artifact_sha256"],
            "convention_sha256": CONVENTION_SHA256,
            "primitive_character_count": root_metadata[
                "primitive_character_count"
            ],
            "q": 10_001,
            "receipt_sha256": root_receipt["receipt_sha256"],
            "transform_output_sha256": root_metadata[
                "transform_output_sha256"
            ],
        }
        primitive_samples = (
            primitive_character_count(10_001) * len(t_indices)
        )
        value_count = len(t_indices) * group_order(10_001)
        events_raw = events_path.read_bytes()
        consumer = {
            "algorithm_id": CONSUMER_ALGORITHM_ID,
            "all_frames_arithmetically_accepted": True,
            "atom_id": "platt-dirichlet-theorem-7-1",
            "author": "Gershon Bialer",
            "candidate_bracket_count": 0,
            "classification": (
                "streamed-completed-L-sign-candidates-not-zero-completeness"
            ),
            "control_stream_sha256": hashlib.sha256(
                consumer_controls.read_bytes()
            ).hexdigest(),
            "discarded_nonprimitive_value_count": value_count - primitive_samples,
            "event_count": 0,
            "event_storage_mode": "raw_ndjson",
            "events_bytes": len(events_raw),
            "events_sha256": hashlib.sha256(events_raw).hexdigest(),
            "external_atom_discharged": False,
            "frame_chain_sha256": "1" * 64,
            "frame_count": 1,
            "full_source_campaign_run": False,
            "indeterminate_sample_count": 0,
            "kind": CONSUMER_RECEIPT_SCHEMA,
            "multiplicity_lower_bound_sum": 0,
            "multiplicity_policy": (
                "one lower-bound event per strict endpoint sign change; never "
                "deduplicated or promoted to exact multiplicity"
            ),
            "ordinary_sign_scan_resolved": True,
            "precision_bits": 192,
            "primitive_sample_count": primitive_samples,
            "production_accept": False,
            "raw_event_records_retained": True,
            "root_number_artifact_chain_sha256": hashlib.sha256(
                canonical_json_bytes(root_binding)
            ).hexdigest(),
            "root_number_artifact_bindings": [root_binding],
            "root_number_artifact_supplied": True,
            "root_number_character_count": primitive_character_count(10_001),
            "root_number_mode": ROOT_ALGORITHM_ID,
            "root_number_modulus_count": 1,
            "root_number_rows_sha256": "2" * 64,
            "sign_decisions_sha256": "3" * 64,
            "source_performance_ready": True,
            "source_performance_blocker": None,
            "transform_stream_sha256": transform_output_sha,
            "upstream_semantics_replayed": False,
            "upstream_semantics_status": (
                "four required receipts are identity/hash checked, but this "
                "component does not replay lattice tails, q^-s, or finite addback"
            ),
            "value_count": value_count,
            "zero_completeness_claimed": False,
        }
        _self_hash(consumer, "receipt_sha256")
        consumer_path = root / "consumer-receipt.json"
        consumer_path.write_bytes(canonical_json_bytes(consumer))

        receipt = {
            "algorithm_id": "platt-dirichlet-largeq-persistent-pipeline-v1",
            "atom_id": "platt-dirichlet-theorem-7-1",
            "author": "Gershon Bialer",
            "classification": (
                "persistent_component_pipeline_not_zero_or_grh_closure"
            ),
            "component_processes_persistent": True,
            "external_atom_discharged": False,
            "frame_count": 1,
            "full_source_campaign_run": False,
            "kind": "sparkinterval.tg.dirichlet_largeq_pipeline.receipt.v1",
            "maximum_batch_count": 64,
            "process_return_codes": {
                "composer": 0,
                "transform": 0,
                "consumer": 0,
            },
            "q": 10_001,
            "ordinate_grid": {
                "first_t_numerator": 5 * t_indices[0],
                "stop_t_numerator_exclusive": (
                    5 * t_indices[0] + 5 * len(t_indices)
                ),
                "t_denominator": 64,
                "t_step_numerator": 5,
                "slice_count": len(t_indices),
            },
            "controls": {
                "composition": _artifact(composition_controls),
                "consumer": _artifact(consumer_controls),
            },
            "root_artifact": _artifact(root_path),
            "root_receipt": _artifact(root_receipt_path),
            "source_performance_ready_for_wired_components": True,
            "summaries": {
                "composer": _artifact(composer_path),
                "consumer": _artifact(consumer_path),
                "events": _artifact(events_path),
                "transform": _artifact(transform_path),
            },
            "stream_bindings_verified": True,
            "zero_completeness_claimed": False,
        }
        _self_hash(receipt, "receipt_sha256")
        pipeline_path = root / "pipeline-receipt.json"
        pipeline_path.write_bytes(canonical_json_bytes(receipt))
        return pipeline_path, root_metadata

    def test_build_and_fresh_replay_bind_one_exact_fft_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = self._contract(root)
            pipeline, root_metadata = self._pipeline(root)
            bundle_path = root / "typed-bundle.json"
            with patch(
                "tg_verifier.dirichlet_fft_pipeline_bundle.read_root_artifact_bytes",
                return_value=(root_metadata, ()),
            ):
                bundle = build_bundle(
                    bundle_path,
                    contract_path=contract,
                    lane_index=0,
                    q=10_001,
                    first_t_index=0,
                    pipeline_receipt_path=pipeline,
                    allow_structural_kat=True,
                )
                replay = replay_bundle(
                    bundle_path,
                    contract_path=contract,
                    allow_structural_kat=True,
                )
            self.assertTrue(replay["accepted"])
            self.assertEqual(replay["t_index_stop_exclusive"], 2)
            self.assertEqual(
                replay["lattice_cache_rows"],
                [
                    {
                        "t_index": t_index,
                        "payload_sha256": (
                            "30e14955ebf1352266dc2ff8067e68104607e750a"
                            "bb9d3b36582b8af909fcb58"
                        ),
                    }
                    for t_index in (0, 1)
                ],
            )
            self.assertTrue(
                bundle["decisions"]["composer_fft_consumer_receipts_typed"]
            )
            self.assertTrue(
                bundle["decisions"][
                    "lattice_cache_row_payload_identities_replayed"
                ]
            )
            self.assertFalse(
                bundle["decisions"][
                    "composition_jobs_and_input_certificate_chains_replayed"
                ]
            )
            self.assertFalse(
                bundle["decisions"][
                    "discarded_fft_stream_arithmetic_independently_replayed"
                ]
            )
            self.assertFalse(
                bundle["decisions"][
                    "consumer_control_upstream_semantics_replayed"
                ]
            )
            self.assertFalse(bundle["decisions"]["external_atom_discharged"])

    def test_tampered_nested_artifact_fails_before_claims_are_used(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = self._contract(root)
            pipeline, root_metadata = self._pipeline(root)
            receipt = json.loads(pipeline.read_bytes())
            transform = Path(receipt["summaries"]["transform"]["path"])
            transform.write_bytes(transform.read_bytes() + b" ")
            with patch(
                "tg_verifier.dirichlet_fft_pipeline_bundle.read_root_artifact_bytes",
                return_value=(root_metadata, ()),
            ), self.assertRaisesRegex(
                DirichletFFTPipelineBundleError, "transform summary hash"
            ):
                build_bundle(
                    root / "bundle.json",
                    contract_path=contract,
                    lane_index=0,
                    q=10_001,
                    first_t_index=0,
                    pipeline_receipt_path=pipeline,
                    allow_structural_kat=True,
                )

    def test_rehashed_transform_work_forgery_fails_independent_formula(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = self._contract(root)
            pipeline, root_metadata = self._pipeline(root)
            receipt = json.loads(pipeline.read_bytes())
            transform_path = Path(receipt["summaries"]["transform"]["path"])
            transform = json.loads(transform_path.read_bytes())
            transform["radix2_butterflies"] += 1
            transform_path.write_bytes(canonical_json_bytes(transform))
            receipt["summaries"]["transform"] = _artifact(transform_path)
            _self_hash(receipt, "receipt_sha256")
            pipeline.write_bytes(canonical_json_bytes(receipt))
            with patch(
                "tg_verifier.dirichlet_fft_pipeline_bundle.read_root_artifact_bytes",
                return_value=(root_metadata, ()),
            ), self.assertRaisesRegex(
                DirichletFFTPipelineBundleError, "transform summary identity"
            ):
                build_bundle(
                    root / "bundle.json",
                    contract_path=contract,
                    lane_index=0,
                    q=10_001,
                    first_t_index=0,
                    pipeline_receipt_path=pipeline,
                    allow_structural_kat=True,
                )

    def test_partial_pipeline_cannot_pose_as_larger_source_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = self._contract(root, t_rows=3)
            pipeline, root_metadata = self._pipeline(root)
            with patch(
                "tg_verifier.dirichlet_fft_pipeline_bundle.read_root_artifact_bytes",
                return_value=(root_metadata, ()),
            ), self.assertRaisesRegex(
                DirichletFFTPipelineBundleError, "does not exactly cover"
            ):
                build_bundle(
                    root / "bundle.json",
                    contract_path=contract,
                    lane_index=0,
                    q=10_001,
                    first_t_index=0,
                    pipeline_receipt_path=pipeline,
                    allow_structural_kat=True,
                )

    def test_tmajor_adapter_bounded_known_answer_and_manifest_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = self._contract(root)
            pipeline, root_metadata = self._pipeline(
                root,
                bind_tmajor_cache_rows=True,
            )
            bundle_path = root / "typed-bundle.json"
            receipt_path = root / "adapter-receipt.json"
            with patch(
                "tg_verifier.dirichlet_fft_pipeline_bundle.read_root_artifact_bytes",
                return_value=(root_metadata, ()),
            ):
                bundle = build_bundle(
                    bundle_path,
                    contract_path=contract,
                    lane_index=0,
                    q=10_001,
                    first_t_index=0,
                    pipeline_receipt_path=pipeline,
                    allow_structural_kat=True,
                )
                adapter = TMajorTypedBundleLaneAdapter(
                    contract,
                    lane_index=0,
                    allow_structural_kat=True,
                )
                row_audit = adapter.authenticate_all_rows()
                self.assertEqual(
                    row_audit["row_schedule_sha256"],
                    "7bd505c71879872b3c124ede718872e29c0f10e90a8d78344779597c2a15e540",
                )
                self.assertEqual(
                    (
                        adapter.expected_target()["q"],
                        adapter.expected_target()["first_t_index"],
                        adapter.expected_target()["t_index_stop_exclusive"],
                    ),
                    (10_001, 0, 2),
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "externally pinned digest",
                ):
                    adapter.accept_bundle(
                        bundle_path,
                        expected_bundle_sha256="f" * 64,
                    )
                admission = adapter.accept_bundle(
                    bundle_path,
                    expected_bundle_sha256=bundle["bundle_sha256"],
                )
                self.assertTrue(
                    admission["decisions"][
                        "lattice_payloads_equal_authenticated_cache_rows"
                    ]
                )
                direct_receipt = adapter.finish_lane()
                self.assertEqual(
                    direct_receipt["typed_bundle_admission_count"], 1
                )
                self.assertFalse(
                    direct_receipt["decisions"][
                        "row_resident_cuda_kernel_implemented"
                    ]
                )
                self.assertFalse(
                    direct_receipt["decisions"][
                        "zero_state_import_export_implemented"
                    ]
                )

                manifest = root / "bundle-manifest.ndjson"
                manifest.write_bytes(
                    canonical_json_bytes(
                        {
                            "schema": MANIFEST_LINE_SCHEMA,
                            "schema_version": 1,
                            "bundle_path": str(bundle_path.resolve()),
                            "bundle_sha256": bundle["bundle_sha256"],
                            "control_base": None,
                        }
                    )
                )
                manifest_sha256 = hashlib.sha256(
                    manifest.read_bytes()
                ).hexdigest()
                replayed_receipt = admit_lane_manifest(
                    receipt_path,
                    contract_path=contract,
                    lane_index=0,
                    manifest_path=manifest,
                    expected_manifest_sha256=manifest_sha256,
                    allow_structural_kat=True,
                )
            self.assertEqual(
                replayed_receipt["row_schedule_sha256"],
                row_audit["row_schedule_sha256"],
            )
            self.assertEqual(
                json.loads(receipt_path.read_bytes()), replayed_receipt
            )
            self.assertTrue(
                replayed_receipt["decisions"][
                    "bounded_reference_adapter_executed"
                ]
            )
            self.assertFalse(
                replayed_receipt["decisions"]["external_atom_discharged"]
            )
            adapter_capability = tmajor_adapter_capability()
            self.assertTrue(
                adapter_capability[
                    "typed_bundle_fresh_replay_at_adapter_boundary_implemented"
                ]
            )
            self.assertFalse(
                adapter_capability["row_resident_cuda_kernel_implemented"]
            )
            self.assertFalse(
                adapter_capability["zero_state_import_export_implemented"]
            )

    def test_tmajor_adapter_rejects_typed_bundle_from_different_cache_rows(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = self._contract(root)
            pipeline, root_metadata = self._pipeline(root)
            bundle_path = root / "typed-bundle.json"
            with patch(
                "tg_verifier.dirichlet_fft_pipeline_bundle.read_root_artifact_bytes",
                return_value=(root_metadata, ()),
            ):
                bundle = build_bundle(
                    bundle_path,
                    contract_path=contract,
                    lane_index=0,
                    q=10_001,
                    first_t_index=0,
                    pipeline_receipt_path=pipeline,
                    allow_structural_kat=True,
                )
                adapter = TMajorTypedBundleLaneAdapter(
                    contract,
                    lane_index=0,
                    allow_structural_kat=True,
                )
                adapter.authenticate_all_rows()
                with self.assertRaisesRegex(
                    DirichletTMajorAdapterError,
                    "differ from authenticated t-major cache rows",
                ):
                    adapter.accept_bundle(
                        bundle_path,
                        expected_bundle_sha256=bundle["bundle_sha256"],
                    )

    def test_capability_does_not_promote_typed_receipts_to_grh(self) -> None:
        result = capability()
        self.assertTrue(
            result["typed_fft_pipeline_receipt_bundle_validator_implemented"]
        )
        self.assertTrue(
            result["lattice_cache_row_payload_identity_replay_implemented"]
        )
        self.assertFalse(
            result[
                "discarded_composition_stream_arithmetic_independently_replayed"
            ]
        )
        self.assertFalse(
            result["discarded_fft_stream_arithmetic_independently_replayed"]
        )
        self.assertFalse(result["zero_completeness_claimed"])
        self.assertFalse(result["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
