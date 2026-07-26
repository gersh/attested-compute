# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tests.test_tg_dirichlet_resident_qmajor_stream import (
    EXPECTED_OUTPUT_SHA256,
    STREAM_RUNNER,
    _plan,
    _schedule,
    _wide_sidecars,
)
from tests.test_tg_dirichlet_tmajor_cuda_block import (
    _write_structural_seed_artifact,
)
from tg_verifier import dirichlet_lattice_cache as cache
from tg_verifier.dirichlet_cache_resident_feed import (
    DirichletCacheResidentFeedError,
    benchmark_cache_range_feed,
    capability,
    materialize_resident_rows_from_cache,
)
from tg_verifier.dirichlet_resident_qmajor_stream import (
    BOUNDED_PROJECTION_COVERAGE,
    QLane,
    build_stream_plan,
    replay_row_artifact,
    replay_sidecar_artifact,
    validate_cuda_summary,
    write_row_artifact,
    write_sidecar_artifact,
)


def _cache_catalog(
    root: Path,
    *,
    t_index_stop_exclusive: int,
    t_indices_per_shard: int,
) -> tuple[Path, str]:
    plan = cache.source_cache_plan(
        t_index_stop_exclusive=t_index_stop_exclusive,
        t_indices_per_shard=t_indices_per_shard,
    )
    for shard_index in range(plan["storage"]["shard_count"]):
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
    return (
        catalog_path,
        hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
    )


class DirichletCacheResidentFeedStructuralTest(unittest.TestCase):
    def test_cache_range_materializes_exact_resident_row_bytes(self) -> None:
        schedule = _schedule((4, 4, 4, 4))
        plan = build_stream_plan(
            schedule,
            phase_index=0,
            coverage_mode=BOUNDED_PROJECTION_COVERAGE,
            loaded_first_t_index=1,
            loaded_t_index_stop_exclusive=3,
            lanes=(QLane(0, 0, 2), QLane(1, 2, 4)),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir()
            catalog_path, catalog_file_sha256 = _cache_catalog(
                cache_root,
                t_index_stop_exclusive=4,
                t_indices_per_shard=2,
            )
            cache_rows = root / "cache-rows.bin"
            receipt = materialize_resident_rows_from_cache(
                cache_rows,
                schedule,
                plan,
                cache_root=cache_root,
                cache_catalog_path=catalog_path,
                expected_cache_catalog_sha256=catalog_file_sha256,
                recovery_seed_sha256="a" * 64,
                source_contract_sha256="b" * 64,
                require_replayed_cache=False,
            )
            direct_rows = root / "direct-rows.bin"
            direct = write_row_artifact(
                direct_rows,
                schedule,
                plan,
                recovery_seed_sha256="a" * 64,
                source_contract_sha256="b" * 64,
                lattice_source_sha256=catalog_file_sha256,
                row_provider=cache._synthetic_row,
            )
            self.assertEqual(cache_rows.read_bytes(), direct_rows.read_bytes())
            self.assertEqual(
                receipt["resident_row_artifact"]["sha256"],
                direct["input_sha256"],
            )
            self.assertEqual(receipt["unique_row_count"], 2)
            self.assertEqual(receipt["target_row_reference_count"], 8)
            self.assertEqual(receipt["row_reuse_ratio"], 4.0)
            self.assertEqual(
                receipt["range_authentication"][
                    "authenticated_physical_row_count"
                ],
                4,
            )
            self.assertEqual(
                receipt["range_authentication"][
                    "authenticated_unselected_boundary_row_count"
                ],
                2,
            )
            self.assertTrue(
                receipt["range_authentication"][
                    "full_touched_shard_footers_authenticated"
                ]
            )
            self.assertFalse(receipt["resident_cuda_executed"])
            self.assertFalse(receipt["external_atom_discharged"])
            replayed = replay_row_artifact(
                cache_rows,
                schedule,
                plan,
                expected_input_sha256=direct["input_sha256"],
                capture_rows=True,
            )
            self.assertEqual(
                replayed.captured_rows,
                (cache._synthetic_row(1), cache._synthetic_row(2)),
            )

    def test_cache_range_pin_tamper_order_and_finalize_fail_closed(
        self,
    ) -> None:
        schedule = _schedule((3, 3, 3, 3))
        plan = build_stream_plan(
            schedule,
            phase_index=0,
            coverage_mode=BOUNDED_PROJECTION_COVERAGE,
            loaded_first_t_index=1,
            loaded_t_index_stop_exclusive=2,
            lanes=(QLane(0, 0, 4),),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir()
            catalog_path, catalog_file_sha256 = _cache_catalog(
                cache_root,
                t_index_stop_exclusive=3,
                t_indices_per_shard=3,
            )
            with self.assertRaisesRegex(
                DirichletCacheResidentFeedError,
                "cache catalog file SHA-256",
            ):
                materialize_resident_rows_from_cache(
                    root / "wrong-pin.bin",
                    schedule,
                    plan,
                    cache_root=cache_root,
                    cache_catalog_path=catalog_path,
                    expected_cache_catalog_sha256="0" * 64,
                    recovery_seed_sha256="a" * 64,
                    source_contract_sha256="b" * 64,
                    require_replayed_cache=False,
                )

            def reordered_rows(*_args: object, **_kwargs: object):
                yield 2, cache._synthetic_row(2)

            with mock.patch(
                "tg_verifier.dirichlet_cache_resident_feed."
                "iter_catalog_range_rows",
                side_effect=reordered_rows,
            ):
                output = root / "reordered.bin"
                with self.assertRaisesRegex(
                    DirichletCacheResidentFeedError,
                    "t ordering differ",
                ):
                    materialize_resident_rows_from_cache(
                        output,
                        schedule,
                        plan,
                        cache_root=cache_root,
                        cache_catalog_path=catalog_path,
                        expected_cache_catalog_sha256=(
                            catalog_file_sha256
                        ),
                        recovery_seed_sha256="a" * 64,
                        source_contract_sha256="b" * 64,
                        require_replayed_cache=False,
                    )
                self.assertFalse(output.exists())

            def late_footer_failure(
                *_args: object, **_kwargs: object
            ):
                yield 1, cache._synthetic_row(1)
                raise cache.DirichletLatticeCacheError(
                    "late boundary footer rejection"
                )

            with mock.patch(
                "tg_verifier.dirichlet_cache_resident_feed."
                "iter_catalog_range_rows",
                side_effect=late_footer_failure,
            ):
                output = root / "late-footer.bin"
                with self.assertRaisesRegex(
                    DirichletCacheResidentFeedError,
                    "late boundary footer rejection",
                ):
                    materialize_resident_rows_from_cache(
                        output,
                        schedule,
                        plan,
                        cache_root=cache_root,
                        cache_catalog_path=catalog_path,
                        expected_cache_catalog_sha256=(
                            catalog_file_sha256
                        ),
                        recovery_seed_sha256="a" * 64,
                        source_contract_sha256="b" * 64,
                        require_replayed_cache=False,
                    )
                self.assertFalse(output.exists())

    def test_bounded_cache_feed_io_benchmark_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path, catalog_file_sha256 = _cache_catalog(
                root,
                t_index_stop_exclusive=4,
                t_indices_per_shard=2,
            )
            report = benchmark_cache_range_feed(
                root,
                catalog_path,
                expected_cache_catalog_sha256=catalog_file_sha256,
                t_index_start_inclusive=1,
                t_index_stop_exclusive=3,
                repetitions=2,
            )
            self.assertEqual(report["repetitions"], 2)
            self.assertEqual(
                report["selected_payload_bytes_per_repetition"],
                2 * cache.ROW_PAYLOAD_BYTES,
            )
            self.assertEqual(
                report["range_authentication"][
                    "authenticated_physical_row_count"
                ],
                4,
            )
            self.assertGreater(
                report[
                    "median_authenticated_physical_bytes_per_second"
                ],
                0,
            )
            self.assertFalse(report["h100_measured"])

    def test_capability_keeps_tgdbspk1_and_source_claims_separate(
        self,
    ) -> None:
        report = capability()
        self.assertTrue(
            report[
                "authenticated_catalog_range_to_resident_worker_input"
            ]
        )
        self.assertFalse(report["TGDBSPK1_largeq_compatible"])
        self.assertFalse(report["external_atom_discharged"])


@unittest.skipUnless(
    STREAM_RUNNER.exists() and STREAM_RUNNER.is_file(),
    "resident CUDA stream runner is not built",
)
class DirichletCacheResidentFeedCudaTest(unittest.TestCase):
    def test_cache_rows_feed_worker_with_exact_reference_output(
        self,
    ) -> None:
        schedule = _schedule()
        plan = _plan(schedule)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed_path = root / "seeds.bin"
            seed_sha256 = _write_structural_seed_artifact(
                seed_path, q_stop=18_480
            )
            schedule_path = root / "schedule.bin"
            schedule_path.write_bytes(schedule.raw)
            cache_root = root / "cache"
            cache_root.mkdir()
            catalog_path, catalog_file_sha256 = _cache_catalog(
                cache_root,
                t_index_stop_exclusive=2,
                t_indices_per_shard=1,
            )
            row_path = root / "rows.bin"
            row_receipt = materialize_resident_rows_from_cache(
                row_path,
                schedule,
                plan,
                cache_root=cache_root,
                cache_catalog_path=catalog_path,
                expected_cache_catalog_sha256=catalog_file_sha256,
                recovery_seed_sha256=seed_sha256,
                source_contract_sha256="b" * 64,
                require_replayed_cache=False,
            )
            sidecar_path = root / "sidecars.bin"
            sidecar_receipt = write_sidecar_artifact(
                sidecar_path,
                schedule,
                plan,
                row_artifact_sha256=row_receipt[
                    "resident_row_artifact"
                ]["sha256"],
                recovery_seed_sha256=seed_sha256,
                source_contract_sha256="b" * 64,
                sidecar_source_sha256="d" * 64,
                sidecar_provider=_wide_sidecars,
            )
            rows = replay_row_artifact(
                row_path,
                schedule,
                plan,
                expected_input_sha256=row_receipt[
                    "resident_row_artifact"
                ]["sha256"],
            )
            sidecars = replay_sidecar_artifact(
                sidecar_path,
                schedule,
                plan,
                rows,
                expected_input_sha256=sidecar_receipt[
                    "input_sha256"
                ],
            )
            summary_path = root / "summary.json"
            completed = subprocess.run(
                [
                    str(STREAM_RUNNER),
                    str(seed_path),
                    seed_sha256,
                    str(schedule_path),
                    plan.phase_plan_sha256,
                    str(row_path),
                    row_receipt["resident_row_artifact"]["sha256"],
                    str(sidecar_path),
                    sidecar_receipt["input_sha256"],
                    str(summary_path),
                    "0",
                    "--allow-prefix-kat",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode(errors="replace"),
            )
            output_path = root / "output.bin"
            output_path.write_bytes(completed.stdout)
            summary = validate_cuda_summary(
                summary_path,
                schedule,
                rows,
                sidecars,
                output_path,
            )
            self.assertEqual(
                summary["output_sha256"], EXPECTED_OUTPUT_SHA256
            )
            self.assertEqual(summary["lattice_h2d_upload_call_count"], 2)
            self.assertEqual(summary["target_count"], 4)
            self.assertEqual(
                summary["descriptor_h2d_upload_count"], 4
            )
            self.assertFalse(summary["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
