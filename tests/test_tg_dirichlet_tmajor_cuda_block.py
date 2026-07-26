# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import unittest

from tg_verifier.dirichlet_allchars_stage import (
    canonical_component_orders,
    canonical_residue_order,
)
from tg_verifier.dirichlet_lattice_cache import (
    _synthetic_row,
    build_cache_catalog,
    cache_shard_filename,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.dirichlet_lattice_stage import (
    LATTICE_ROWS,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
)
from tg_verifier.dirichlet_largeq_batch import (
    FRAME_FACTOR,
    RESIDUE_DESCRIPTOR,
)
from tg_verifier import dirichlet_recovery_seeds as seeds
from tg_verifier.dirichlet_source_supervisor import (
    build_structural_kat_contract,
)
from tg_verifier.dirichlet_tmajor_cuda_block import (
    DirichletTMajorCudaBlockError,
    TMajorCudaBlockBuilder,
    canonical_json_bytes,
    replay_tmajor_cuda_block,
    validate_tmajor_cuda_execution_summary,
    write_sidecar_manifest,
)
from tg_verifier.dirichlet_tmajor_cuda_arithmetic_replay import (
    DirichletTMajorCudaArithmeticReplayError,
    replay_tmajor_cuda_arithmetic_sample,
    validate_tmajor_cuda_execution_arithmetic_sample,
)
from tg_verifier import dirichlet_tmajor_cuda_block as direct_block
from tg_verifier.dirichlet_tmajor_spool import build_lane_spool


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path(
    os.environ.get(
        "TG_DIRICHLET_TMAJOR_SEEDED_BINARY",
        ROOT
        / "build/tg-production-kat/"
        "sparkinterval-tg-dirichlet-largeq-seeded",
    )
)
try:
    import flint as _flint  # type: ignore[import-not-found]

    PINNED_FLINT_AVAILABLE = (
        str(_flint.__version__) == "0.9.0"
        and str(_flint.__FLINT_VERSION__) == "3.6.0"
        and int(_flint.__FLINT_RELEASE__) == 30_600
    )
except ImportError:
    PINNED_FLINT_AVAILABLE = False


def _write_structural_seed_artifact(
    path: Path, *, q_stop: int, amplitude: float = 0.001
) -> str:
    x_stop = (seeds.SOURCE_M + 1) * q_stop - 1
    chunk_records = 4096
    record_count = x_stop
    header = seeds.HEADER.pack(
        seeds.HEADER_MAGIC,
        seeds.FORMAT_VERSION,
        seeds.SOURCE_M,
        seeds.SOURCE_MAX_Q,
        seeds.SEED_RECORD.size,
        1,
        x_stop,
        seeds.SOURCE_STEP_NUMERATOR,
        seeds.SOURCE_STEP_DENOMINATOR,
        record_count,
        192,
        256,
        chunk_records,
        0,
        0,
    )
    records_digest = hashlib.sha256()
    root_digest = hashlib.sha256(seeds.ROOT_DOMAIN)
    chunks: list[bytes] = []
    first_x = 1
    while first_x <= x_stop:
        count = min(chunk_records, x_stop - first_x + 1)
        payload = seeds.SEED_RECORD.pack(
            amplitude, amplitude, 1.0, 1.0, 0.0, 0.0
        ) * count
        chunk_digest = hashlib.sha256(
            seeds.CHUNK_DOMAIN
            + first_x.to_bytes(8, "little")
            + count.to_bytes(8, "little")
            + payload
        ).digest()
        chunks.append(
            seeds.CHUNK_HEADER.pack(
                seeds.CHUNK_MAGIC,
                seeds.FORMAT_VERSION,
                0,
                first_x,
                count,
                chunk_digest,
            )
            + payload
        )
        records_digest.update(payload)
        root_digest.update(chunk_digest)
        first_x += count
    footer = seeds.FOOTER.pack(
        seeds.FOOTER_MAGIC,
        seeds.FORMAT_VERSION,
        0,
        record_count,
        len(chunks),
        records_digest.digest(),
        root_digest.digest(),
    )
    path.write_bytes(header + b"".join(chunks) + footer)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wait_for_test_barrier(
    ready: Path, process: subprocess.Popen[bytes]
) -> None:
    deadline = time.monotonic() + 30.0
    while not ready.is_file():
        if process.poll() is not None:
            _stdout, stderr = process.communicate()
            raise AssertionError(
                "runner exited before reaching test barrier: "
                + stderr.decode(errors="replace")
            )
        if time.monotonic() >= deadline:
            process.kill()
            process.communicate()
            raise AssertionError(f"timed out waiting for {ready}")
        time.sleep(0.01)


def _write_seeded_frame(
    path: Path,
    *,
    q: int,
    t_indices: tuple[int, ...],
    substitute_last_row: bool = False,
) -> dict[str, object]:
    residues = canonical_residue_order(q)
    orders = canonical_component_orders(q)
    header = seeds.SEEDED_BATCH_HEADER.pack(
        seeds.SEEDED_BATCH_MAGIC,
        2,
        q,
        LATTICE_ROWS,
        TAYLOR_DEGREE,
        len(orders),
        len(t_indices),
        seeds.SOURCE_M,
        0,
        len(residues),
        5 * t_indices[0],
        64,
        5,
        len(t_indices) * LATTICE_ROWS * TAYLOR_COLUMNS,
        len(t_indices) * len(residues),
        0,
    )
    descriptors = b"".join(
        RESIDUE_DESCRIPTOR.pack(a, canonical_lattice_row(q, a))
        for a in residues
    )
    factor = 1.0 / math.sqrt(q)
    factors = FRAME_FACTOR.pack(factor, factor, 0.0, 0.0) * len(
        t_indices
    )
    rows = [
        _synthetic_row(t_index)
        for t_index in t_indices
    ]
    if substitute_last_row:
        changed = bytearray(rows[-1])
        changed[-1] ^= 1
        rows[-1] = bytes(changed)
    tails = struct.pack("<d", 0.0) * len(t_indices)
    raw = header + descriptors + factors + b"".join(rows) + tails
    path.write_bytes(raw)
    return {
        "q": q,
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _rehash_direct_first_sidecar_mutation(
    *,
    receipt: dict[str, object],
    artifact: Path,
    receipt_path: Path,
    mutate: object,
) -> dict[str, object]:
    """Rebind every transport hash after changing the first direct sidecar."""

    accounting = receipt["accounting"]
    assert isinstance(accounting, dict)
    raw = bytearray(artifact.read_bytes())
    target_start = (
        direct_block.BLOCK_HEADER.size
        + int(accounting["authenticated_unique_row_count"])
        * (direct_block.ROW_HEADER.size + direct_block.ROW_PAYLOAD_BYTES)
    )
    fields = list(direct_block.TARGET_HEADER.unpack_from(raw, target_start))
    factor_start = target_start + direct_block.TARGET_HEADER.size
    factor_stop = factor_start + int(fields[12])
    tail_stop = factor_stop + int(fields[13])
    factors = bytearray(raw[factor_start:factor_stop])
    tails = bytearray(raw[factor_stop:tail_stop])
    if not callable(mutate):
        raise TypeError("sidecar mutation must be callable")
    mutate(factors, tails)
    fields[14] = bytes.fromhex(
        direct_block._target_sidecar_sha256(
            q=int(fields[2]),
            batch_count=int(fields[4]),
            first_t_numerator=int(fields[8]),
            group_order=int(fields[7]),
            factors=bytes(factors),
            tails=bytes(tails),
        )
    )
    direct_block.TARGET_HEADER.pack_into(raw, target_start, *fields)
    raw[factor_start:factor_stop] = factors
    raw[factor_stop:tail_stop] = tails

    footer_start = len(raw) - direct_block.BLOCK_FOOTER.size
    target_digest = hashlib.sha256(raw[target_start:footer_start]).digest()
    sidecar_source = receipt["sidecar_source"]
    assert isinstance(sidecar_source, dict)
    recipe = sidecar_source["recipe"]
    assert isinstance(recipe, dict)
    chain = hashlib.sha256(direct_block.DIRECT_SOURCE_CHAIN_DOMAIN)
    chain.update(bytes.fromhex(str(recipe["recipe_sha256"])))
    position = target_start
    while position < footer_start:
        target = direct_block.TARGET_HEADER.unpack_from(raw, position)
        chain.update(struct.pack("<IQ", int(target[2]), int(target[11])))
        chain.update(target[14])
        position += (
            direct_block.TARGET_HEADER.size
            + int(target[12])
            + int(target[13])
        )
    if position != footer_start:
        raise AssertionError("mutated target stream lost framing")
    footer = list(direct_block.BLOCK_FOOTER.unpack_from(raw, footer_start))
    footer[10] = target_digest
    footer[11] = chain.digest()
    direct_block.BLOCK_FOOTER.pack_into(raw, footer_start, *footer)
    artifact.write_bytes(raw)

    changed = json.loads(receipt_path.read_bytes())
    changed["artifact"]["sha256"] = hashlib.sha256(raw).hexdigest()
    changed["source_seeded_input_chain_sha256"] = chain.hexdigest()
    body = dict(changed)
    body.pop("receipt_sha256")
    changed["receipt_sha256"] = hashlib.sha256(
        direct_block.canonical_json_bytes(body)
    ).hexdigest()
    receipt_path.write_bytes(direct_block.canonical_json_bytes(changed))
    return changed


class DirichletTMajorCudaBlockTest(unittest.TestCase):
    def test_primitive_only_source_projection_is_exact(self) -> None:
        projection = direct_block.source_projection()
        self.assertEqual(projection["primitive_modulus_roster_version"], 2)
        self.assertEqual(projection["active_modulus_count"], 292_500)
        self.assertEqual(
            projection["excluded_empty_primitive_roster_moduli"], 97_500
        )
        self.assertEqual(projection["active_target_count"], 56_981_100)
        self.assertEqual(
            projection["target_row_reference_count"], 3_637_613_167
        )
        self.assertEqual(
            projection["input_bytes"],
            {
                "authenticated_rows_with_headers": 134_213_336_320,
                "target_headers": 6_837_732_000,
                "directed_mpfr_factor_and_exact_tail_sidecars": (
                    145_504_526_680
                ),
                "block_headers_and_footers": 864_000,
                "total": 286_556_459_000,
            },
        )
        self.assertEqual(
            projection["total_including_recovery_seeds"], 286_652_467_016
        )

    def test_benchmark_alternates_only_over_primitive_source_moduli(
        self,
    ) -> None:
        benchmark = direct_block.benchmark_direct_sidecars(
            q=10_001,
            batch_count=1,
            repetitions=2,
        )
        self.assertEqual(
            benchmark["schema"],
            (
                "sparkinterval.tg.dirichlet_tmajor_cuda_block."
                "direct_sidecar_benchmark.v2"
            ),
        )
        self.assertEqual(benchmark["alternating_q"], 10_003)
        with self.assertRaisesRegex(
            DirichletTMajorCudaBlockError,
            "benchmark geometry differs",
        ):
            direct_block.benchmark_direct_sidecars(
                q=10_002,
                batch_count=1,
                repetitions=1,
            )

    def _fixture(
        self, root: Path
    ) -> tuple[
        Path,
        Path,
        dict[str, object],
        Path,
        str,
        list[Path],
    ]:
        seed_path = root / "seeds.bin"
        seed_sha = _write_structural_seed_artifact(
            seed_path, q_stop=10_003
        )
        cache = root / "cache"
        cache.mkdir()
        plan = source_cache_plan(
            t_index_stop_exclusive=2,
            t_indices_per_shard=2,
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
            recovery_artifact_sha256=seed_sha,
            recovery_replay_sha256="b" * 64,
            q_tile_size=1,
            q_start=10_001,
            q_stop=10_003,
        )
        spool_receipt_path = root / "spool.receipt.json"
        spool_receipt = build_lane_spool(
            root / "spool.bin",
            spool_receipt_path,
            contract_path=contract,
            lane_index=0,
            allow_structural_kat=True,
        )
        source_paths: list[Path] = []
        entries: list[dict[str, object]] = []
        for q in (10_001, 10_003):
            path = root / f"q-{q}.seeded.bin"
            source_paths.append(path)
            entries.append(
                _write_seeded_frame(
                    path, q=q, t_indices=(0, 1)
                )
            )
        manifest = root / "sidecars.ndjson"
        manifest_record = write_sidecar_manifest(manifest, entries)
        return (
            contract,
            spool_receipt_path,
            spool_receipt,
            manifest,
            manifest_record["sha256"],
            [seed_path, *source_paths],
        )

    def _build(
        self,
        root: Path,
    ) -> tuple[dict[str, object], Path, Path, list[Path]]:
        (
            contract,
            spool_receipt_path,
            spool_receipt,
            manifest,
            manifest_sha,
            sources,
        ) = self._fixture(root)
        artifact = root / "block.bin"
        receipt_path = root / "block.receipt.json"
        with TMajorCudaBlockBuilder(
            contract_path=contract,
            spool_receipt_path=spool_receipt_path,
            expected_spool_receipt_sha256=spool_receipt[
                "receipt_sha256"
            ],
            allow_structural_kat=True,
        ) as builder:
            receipt = builder.build(
                artifact,
                receipt_path,
                sidecar_manifest_path=manifest,
                expected_sidecar_manifest_sha256=manifest_sha,
                first_t_index=0,
            )
        return receipt, artifact, receipt_path, sources

    def _build_direct(
        self,
        root: Path,
    ) -> tuple[dict[str, object], Path, Path, list[Path]]:
        (
            contract,
            spool_receipt_path,
            spool_receipt,
            _manifest,
            _manifest_sha,
            sources,
        ) = self._fixture(root)
        # The direct path must not read either transitional TGDLQB2 source.
        for source in sources[1:]:
            source.unlink()
        artifact = root / "direct-block.bin"
        receipt_path = root / "direct-block.receipt.json"
        with TMajorCudaBlockBuilder(
            contract_path=contract,
            spool_receipt_path=spool_receipt_path,
            expected_spool_receipt_sha256=spool_receipt[
                "receipt_sha256"
            ],
            allow_structural_kat=True,
        ) as builder:
            receipt = builder.build(
                artifact,
                receipt_path,
                first_t_index=0,
                direct_sidecars=True,
            )
        return receipt, artifact, receipt_path, sources

    def test_authenticated_block_elides_repeated_rows_and_descriptors(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, _sources = self._build(root)
            replay = replay_tmajor_cuda_block(
                artifact,
                receipt_path,
                expected_receipt_sha256=receipt["receipt_sha256"],
            )
            self.assertEqual(replay, receipt)
            accounting = receipt["accounting"]
            self.assertEqual(accounting["authenticated_unique_row_count"], 2)
            self.assertEqual(accounting["active_target_count"], 2)
            self.assertEqual(accounting["target_row_reference_count"], 4)
            self.assertEqual(receipt["q_start_inclusive"], 10_001)
            self.assertEqual(receipt["q_stop_inclusive"], 10_003)
            self.assertEqual(
                receipt["primitive_modulus_roster"],
                "primitive-dirichlet-moduli-q-mod-4-ne-2-v2",
            )
            self.assertEqual(receipt["primitive_modulus_roster_version"], 2)
            raw = artifact.read_bytes()
            target_start = (
                direct_block.BLOCK_HEADER.size
                + 2
                * (
                    direct_block.ROW_HEADER.size
                    + direct_block.ROW_PAYLOAD_BYTES
                )
            )
            first = direct_block.TARGET_HEADER.unpack_from(raw, target_start)
            second_offset = (
                target_start
                + direct_block.TARGET_HEADER.size
                + int(first[12])
                + int(first[13])
            )
            second = direct_block.TARGET_HEADER.unpack_from(raw, second_offset)
            self.assertEqual((int(first[2]), int(second[2])), (10_001, 10_003))
            self.assertEqual(
                accounting["repeated_lattice_bytes_elided"],
                2 * 1_048_576,
            )
            self.assertGreater(
                accounting["canonical_descriptor_bytes_elided"], 0
            )
            self.assertLess(
                accounting["cuda_input_artifact_bytes"],
                accounting["source_seeded_input_bytes_consumed"],
            )
            self.assertFalse(
                receipt["decisions"][
                    "row_resident_cuda_execution_completed"
                ]
            )
            self.assertFalse(
                receipt["decisions"]["zero_completeness_claimed"]
            )

            with artifact.open("r+b") as target:
                target.seek(400)
                original = target.read(1)
                target.seek(-1, 1)
                target.write(bytes([original[0] ^ 1]))
            with self.assertRaises(DirichletTMajorCudaBlockError):
                replay_tmajor_cuda_block(
                    artifact,
                    receipt_path,
                    expected_receipt_sha256=receipt["receipt_sha256"],
                )

    def test_direct_mpfr_sidecars_remove_qmajor_source_dependency(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, sources = self._build_direct(
                root
            )
            self.assertTrue(sources[0].is_file())
            self.assertTrue(all(not source.exists() for source in sources[1:]))
            replay = replay_tmajor_cuda_block(
                artifact,
                receipt_path,
                expected_receipt_sha256=receipt["receipt_sha256"],
            )
            self.assertEqual(replay, receipt)
            self.assertEqual(receipt["sidecar_mode"], 1)
            self.assertEqual(
                receipt["accounting"][
                    "source_seeded_input_bytes_consumed"
                ],
                0,
            )
            self.assertGreater(
                receipt["accounting"][
                    "logical_qmajor_seeded_input_bytes"
                ],
                receipt["accounting"]["cuda_input_artifact_bytes"],
            )
            decisions = receipt["decisions"]
            self.assertTrue(decisions["directed_MPFR_factors_generated"])
            self.assertTrue(
                decisions[
                    "higher_precision_MPFR_factor_containment_replayed"
                ]
            )
            self.assertTrue(
                decisions["exact_rational_uniform_Taylor_tail_replayed"]
            )
            self.assertFalse(decisions["qmajor_seeded_inputs_consumed"])
            self.assertFalse(decisions["source_scale_run"])
            self.assertFalse(decisions["external_atom_discharged"])

    def test_direct_replay_rejects_rehashed_factor_substitution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, _sources = self._build_direct(
                root
            )
            raw = bytearray(artifact.read_bytes())
            target_start = (
                direct_block.BLOCK_HEADER.size
                + receipt["accounting"]["authenticated_unique_row_count"]
                * (
                    direct_block.ROW_HEADER.size
                    + direct_block.ROW_PAYLOAD_BYTES
                )
            )
            fields = list(
                direct_block.TARGET_HEADER.unpack_from(raw, target_start)
            )
            factor_start = target_start + direct_block.TARGET_HEADER.size
            factors = bytearray(
                raw[
                    factor_start
                    : factor_start + int(fields[12])
                ]
            )
            first_factor = list(
                direct_block.FRAME_FACTOR.unpack_from(factors)
            )
            first_factor[0] = math.nextafter(
                first_factor[0], -math.inf
            )
            direct_block.FRAME_FACTOR.pack_into(
                factors, 0, *first_factor
            )
            tails = bytes(
                raw[
                    factor_start + int(fields[12])
                    : factor_start + int(fields[12]) + int(fields[13])
                ]
            )
            fields[14] = bytes.fromhex(
                direct_block._target_sidecar_sha256(
                    q=int(fields[2]),
                    batch_count=int(fields[4]),
                    first_t_numerator=int(fields[8]),
                    group_order=int(fields[7]),
                    factors=bytes(factors),
                    tails=tails,
                )
            )
            direct_block.TARGET_HEADER.pack_into(
                raw, target_start, *fields
            )
            raw[
                factor_start : factor_start + len(factors)
            ] = factors

            footer_start = len(raw) - direct_block.BLOCK_FOOTER.size
            target_digest = hashlib.sha256(
                raw[target_start:footer_start]
            ).digest()
            chain = hashlib.sha256(
                direct_block.DIRECT_SOURCE_CHAIN_DOMAIN
            )
            chain.update(
                bytes.fromhex(
                    receipt["sidecar_source"]["recipe"][
                        "recipe_sha256"
                    ]
                )
            )
            position = target_start
            while position < footer_start:
                target = direct_block.TARGET_HEADER.unpack_from(
                    raw, position
                )
                chain.update(
                    struct.pack("<IQ", int(target[2]), int(target[11]))
                )
                chain.update(target[14])
                position += (
                    direct_block.TARGET_HEADER.size
                    + int(target[12])
                    + int(target[13])
                )
            self.assertEqual(position, footer_start)
            footer = list(
                direct_block.BLOCK_FOOTER.unpack_from(raw, footer_start)
            )
            footer[10] = target_digest
            footer[11] = chain.digest()
            direct_block.BLOCK_FOOTER.pack_into(
                raw, footer_start, *footer
            )
            artifact.write_bytes(raw)

            changed = json.loads(receipt_path.read_bytes())
            changed["artifact"]["sha256"] = hashlib.sha256(raw).hexdigest()
            changed["source_seeded_input_chain_sha256"] = (
                chain.hexdigest()
            )
            body = dict(changed)
            body.pop("receipt_sha256")
            changed["receipt_sha256"] = hashlib.sha256(
                direct_block.canonical_json_bytes(body)
            ).hexdigest()
            receipt_path.write_bytes(
                direct_block.canonical_json_bytes(changed)
            )
            with self.assertRaisesRegex(
                DirichletTMajorCudaBlockError,
                "direct MPFR factor or exact-rational tail replay differs",
            ):
                replay_tmajor_cuda_block(
                    artifact,
                    receipt_path,
                    expected_receipt_sha256=changed["receipt_sha256"],
                )

    def test_direct_replay_rejects_rehashed_exact_tail_substitution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, _sources = self._build_direct(
                root
            )

            def mutate_tail(
                _factors: bytearray, tails: bytearray
            ) -> None:
                (radius,) = struct.unpack_from("<d", tails)
                struct.pack_into(
                    "<d", tails, 0, math.nextafter(radius, math.inf)
                )

            changed = _rehash_direct_first_sidecar_mutation(
                receipt=receipt,
                artifact=artifact,
                receipt_path=receipt_path,
                mutate=mutate_tail,
            )
            with self.assertRaisesRegex(
                DirichletTMajorCudaBlockError,
                "direct MPFR factor or exact-rational tail replay differs",
            ):
                replay_tmajor_cuda_block(
                    artifact,
                    receipt_path,
                    expected_receipt_sha256=changed["receipt_sha256"],
                )

    def test_builder_rejects_seeded_lattice_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (
                contract,
                spool_receipt_path,
                spool_receipt,
                _manifest,
                _manifest_sha,
                sources,
            ) = self._fixture(root)
            substituted = _write_seeded_frame(
                sources[-1],
                q=10_003,
                t_indices=(0, 1),
                substitute_last_row=True,
            )
            first = {
                "q": 10_001,
                "path": str(sources[-2].resolve()),
                "sha256": hashlib.sha256(
                    sources[-2].read_bytes()
                ).hexdigest(),
                "size_bytes": sources[-2].stat().st_size,
            }
            manifest = root / "substituted.ndjson"
            manifest_record = write_sidecar_manifest(
                manifest, [first, substituted]
            )
            with TMajorCudaBlockBuilder(
                contract_path=contract,
                spool_receipt_path=spool_receipt_path,
                expected_spool_receipt_sha256=spool_receipt[
                    "receipt_sha256"
                ],
                allow_structural_kat=True,
            ) as builder:
                with self.assertRaisesRegex(
                    DirichletTMajorCudaBlockError,
                    "differs from the authenticated t-major spool",
                ):
                    builder.build(
                        root / "must-not-exist.bin",
                        root / "must-not-exist.json",
                        sidecar_manifest_path=manifest,
                        expected_sidecar_manifest_sha256=manifest_record[
                            "sha256"
                        ],
                        first_t_index=0,
                    )
            self.assertFalse((root / "must-not-exist.bin").exists())

    def test_execution_summary_rejects_boolean_integer_spoof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, _sources = self._build_direct(
                root
            )
            accounting = receipt["accounting"]
            summary = root / "boolean-summary.json"
            value = {
                "algorithm_id": direct_block.CUDA_ALGORITHM_ID,
                "all_character_fft_executed": False,
                "canonical_descriptor_input_bytes": 0,
                "classification": (
                    "row_resident_seeded_cuda_component_not_zero_or_"
                    "turing_closure"
                ),
                "completed_l_zero_state_validated": False,
                "elapsed_kernel_nanoseconds": 1,
                "external_atom_discharged": False,
                "input_artifact_sha256": receipt["artifact"]["sha256"],
                "lane_index": receipt["lane_index"],
                # bool is a Python int subclass and used to compare equal to
                # 1 before the strict receipt-typing check was added.
                "lattice_h2d_upload_count": True,
                "output_stream_sha256": "d" * 64,
                "recovery_seed_artifact_sha256": (
                    receipt["recovery_seed_artifact_sha256"]
                ),
                "row_bindings_sha256": receipt["row_bindings_sha256"],
                "row_count": accounting["authenticated_unique_row_count"],
                "row_payload_h2d_bytes": (
                    accounting["row_resident_lattice_bytes"]
                ),
                "schema": direct_block.EXECUTION_SUMMARY_SCHEMA,
                "schema_version": direct_block.FORMAT_VERSION,
                "sidecar_source_sha256": (
                    receipt["sidecar_source"]["recipe"]["recipe_sha256"]
                ),
                "source_contract_sha256": (
                    receipt["source_contract_sha256"]
                ),
                "source_scale_run": False,
                "spool_receipt_sha256": receipt["spool_receipt_sha256"],
                "target_count": accounting["active_target_count"],
                "transcendental_device_calls": 0,
                "trusted_execution_attested": False,
                "value_count": accounting["output_value_count"],
                "zero_completeness_claimed": False,
            }
            summary.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(
                DirichletTMajorCudaBlockError,
                "CUDA lattice H2D upload count",
            ):
                validate_tmajor_cuda_execution_summary(
                    summary,
                    artifact,
                    receipt_path,
                    expected_summary_sha256=hashlib.sha256(
                        summary.read_bytes()
                    ).hexdigest(),
                    expected_receipt_sha256=receipt["receipt_sha256"],
                )

    def test_direct_recipe_rejects_boolean_schema_version_spoof(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, _artifact, _receipt_path, _sources = self._build_direct(
                root
            )
            recipe = json.loads(
                json.dumps(receipt["sidecar_source"]["recipe"])
            )
            recipe["schema_version"] = True
            recipe.pop("recipe_sha256")
            recipe["recipe_sha256"] = hashlib.sha256(
                canonical_json_bytes(recipe)
            ).hexdigest()
            with self.assertRaisesRegex(
                DirichletTMajorCudaBlockError,
                "direct sidecar recipe, implementation, or MPFR version",
            ):
                direct_block._validate_direct_recipe(
                    recipe,
                    q_start=receipt["q_start_inclusive"],
                    q_stop=receipt["q_stop_inclusive"],
                    first_t_index=receipt["first_t_index"],
                    t_index_stop_exclusive=receipt[
                        "t_index_stop_exclusive"
                    ],
                )

    def test_mpfr_factor_provider_rejects_c_ulong_overflow(self) -> None:
        provider = direct_block.MPFRFactorProvider(
            direct_block.DIRECT_FACTOR_PRECISION_BITS
        )
        with self.assertRaisesRegex(
            RuntimeError, "C-ABI-overflowing"
        ):
            provider.factor(
                q=10_001,
                t_numerator=1 << 128,
                t_denominator=64,
            )
        with self.assertRaisesRegex(
            RuntimeError, "C-ABI-overflowing"
        ):
            provider.factor(
                q=10_001,
                t_numerator=0,
                t_denominator=1 << 128,
            )

    def test_replay_and_runner_reject_out_of_range_t_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, sources = self._build_direct(
                root
            )
            raw = bytearray(artifact.read_bytes())
            header = list(direct_block.BLOCK_HEADER.unpack_from(raw))
            header[9] = direct_block.SOURCE_MAX_T_INDEX + 1
            header[10] = header[9] + int(header[3])
            direct_block.BLOCK_HEADER.pack_into(raw, 0, *header)
            artifact.write_bytes(raw)
            with self.assertRaisesRegex(
                DirichletTMajorCudaBlockError,
                "header or exact geometry differs",
            ):
                replay_tmajor_cuda_block(
                    artifact,
                    receipt_path,
                    expected_receipt_sha256=receipt["receipt_sha256"],
                )
            if RUNNER.is_file():
                seed_path = sources[0]
                summary = root / "must-not-exist-range-summary.json"
                completed = subprocess.run(
                    [
                        str(RUNNER),
                        "--tmajor-block",
                        str(seed_path),
                        hashlib.sha256(seed_path.read_bytes()).hexdigest(),
                        str(artifact),
                        hashlib.sha256(raw).hexdigest(),
                        str(summary),
                        "0",
                        "--allow-prefix-kat",
                    ],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(completed.stdout, b"")
                self.assertFalse(summary.exists())

    @unittest.skipUnless(
        RUNNER.is_file(), "requires the seeded CUDA runner"
    )
    def test_runner_rejects_seed_swapped_after_prehash_before_parse(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, _receipt_path, sources = self._build_direct(
                root
            )
            seed_path = sources[0]
            seed_sha = hashlib.sha256(seed_path.read_bytes()).hexdigest()
            replacement = root / "replacement-seeds.bin"
            replacement_sha = _write_structural_seed_artifact(
                replacement, q_stop=10_003, amplitude=0.002
            )
            self.assertNotEqual(seed_sha, replacement_sha)
            summary = root / "must-not-exist-seed-race-summary.json"
            barrier = root / "seed-prehash-barrier"
            environment = os.environ.copy()
            environment[
                "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_SEED_PREHASH_BARRIER"
            ] = str(barrier)
            output = root / "seed-race-output.bin"
            with output.open("wb") as output_stream:
                process = subprocess.Popen(
                    [
                        str(RUNNER),
                        "--tmajor-block",
                        str(seed_path),
                        seed_sha,
                        str(artifact),
                        receipt["artifact"]["sha256"],
                        str(summary),
                        "0",
                        "--allow-prefix-kat",
                    ],
                    stdout=output_stream,
                    stderr=subprocess.PIPE,
                    env=environment,
                )
                try:
                    _wait_for_test_barrier(
                        Path(str(barrier) + ".ready"), process
                    )
                    os.replace(replacement, seed_path)
                    Path(str(barrier) + ".continue").write_bytes(b"go\n")
                    _stdout, stderr = process.communicate(timeout=30)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
            self.assertNotEqual(process.returncode, 0)
            self.assertIn(b"parsed artifact digest differs", stderr)
            self.assertEqual(output.read_bytes(), b"")
            self.assertFalse(summary.exists())

    @unittest.skipUnless(
        RUNNER.is_file(), "requires the seeded CUDA runner"
    )
    def test_runner_rejects_block_swapped_after_prehash_before_consumption(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, _receipt_path, sources = self._build_direct(
                root
            )
            seed_path = sources[0]
            seed_sha = hashlib.sha256(seed_path.read_bytes()).hexdigest()
            original = artifact.read_bytes()
            replacement = bytearray(original)
            first_row_payload = (
                direct_block.BLOCK_HEADER.size
                + direct_block.ROW_HEADER.size
            )
            endpoints = list(
                struct.unpack_from("<dddd", replacement, first_row_payload)
            )
            endpoints[0] += math.ldexp(1.0, -40)
            endpoints[1] += math.ldexp(1.0, -40)
            struct.pack_into(
                "<dddd", replacement, first_row_payload, *endpoints
            )
            first_row_header = list(
                direct_block.ROW_HEADER.unpack_from(
                    replacement, direct_block.BLOCK_HEADER.size
                )
            )
            payload_stop = (
                first_row_payload + direct_block.ROW_PAYLOAD_BYTES
            )
            first_row_header[5] = hashlib.sha256(
                replacement[first_row_payload:payload_stop]
            ).digest()
            direct_block.ROW_HEADER.pack_into(
                replacement,
                direct_block.BLOCK_HEADER.size,
                *first_row_header,
            )
            replacement_path = root / "replacement-block.bin"
            replacement_path.write_bytes(replacement)
            original_path = root / "original-block.bin"
            original_path.write_bytes(original)
            self.assertNotEqual(
                hashlib.sha256(replacement).hexdigest(),
                receipt["artifact"]["sha256"],
            )

            summary = root / "must-not-exist-block-race-summary.json"
            preflight_barrier = root / "block-preflight-barrier"
            consumed_barrier = root / "block-consumed-barrier"
            environment = os.environ.copy()
            environment[
                "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_TMAJOR_PREFLIGHT_BARRIER"
            ] = str(preflight_barrier)
            environment[
                "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_TMAJOR_CONSUME_BARRIER"
            ] = str(consumed_barrier)
            output = root / "block-race-output.bin"
            with output.open("wb") as output_stream:
                process = subprocess.Popen(
                    [
                        str(RUNNER),
                        "--tmajor-block",
                        str(seed_path),
                        seed_sha,
                        str(artifact),
                        receipt["artifact"]["sha256"],
                        str(summary),
                        "0",
                        "--allow-prefix-kat",
                    ],
                    stdout=output_stream,
                    stderr=subprocess.PIPE,
                    env=environment,
                )
                try:
                    _wait_for_test_barrier(
                        Path(str(preflight_barrier) + ".ready"), process
                    )
                    os.replace(replacement_path, artifact)
                    Path(
                        str(preflight_barrier) + ".continue"
                    ).write_bytes(b"go\n")
                    _wait_for_test_barrier(
                        Path(str(consumed_barrier) + ".ready"), process
                    )
                    # Restore the externally pinned bytes before releasing
                    # the runner.  A path-only end rehash would therefore
                    # accept, although the open stream consumed the changed
                    # row.  The consumed-byte digest must still reject it.
                    os.replace(original_path, artifact)
                    Path(
                        str(consumed_barrier) + ".continue"
                    ).write_bytes(b"go\n")
                    _stdout, stderr = process.communicate(timeout=30)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
            self.assertNotEqual(process.returncode, 0)
            self.assertIn(b"consumed input digest", stderr)
            self.assertGreater(len(output.read_bytes()), 0)
            self.assertFalse(summary.exists())

    @unittest.skipUnless(
        RUNNER.is_file(), "requires the seeded CUDA runner"
    )
    def test_direct_mpfr_block_executes_in_row_resident_cuda_mode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, sources = self._build_direct(
                root
            )
            seed_path = sources[0]
            seed_sha = hashlib.sha256(seed_path.read_bytes()).hexdigest()
            summary = root / "direct-summary.json"
            completed = subprocess.run(
                [
                    str(RUNNER),
                    "--tmajor-block",
                    str(seed_path),
                    seed_sha,
                    str(artifact),
                    receipt["artifact"]["sha256"],
                    str(summary),
                    "0",
                    "--allow-prefix-kat",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            value = json.loads(summary.read_bytes())
            self.assertEqual(value["lattice_h2d_upload_count"], 1)
            self.assertEqual(
                value["sidecar_source_sha256"],
                receipt["sidecar_source"]["recipe"]["recipe_sha256"],
            )
            self.assertEqual(
                value["output_stream_sha256"],
                hashlib.sha256(completed.stdout).hexdigest(),
            )
            replay = validate_tmajor_cuda_execution_summary(
                summary,
                artifact,
                receipt_path,
                expected_summary_sha256=hashlib.sha256(
                    summary.read_bytes()
                ).hexdigest(),
                expected_receipt_sha256=receipt["receipt_sha256"],
            )
            self.assertEqual(
                replay["output_stream_sha256"],
                hashlib.sha256(completed.stdout).hexdigest(),
            )
            self.assertFalse(replay["source_scale_run"])
            self.assertFalse(replay["external_atom_discharged"])

    @unittest.skipUnless(
        RUNNER.is_file(), "requires the seeded CUDA runner"
    )
    def test_bounded_exact_arithmetic_replay_rejects_rehashed_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, sources = self._build_direct(
                root
            )
            seed_path = sources[0]
            seed_sha = hashlib.sha256(seed_path.read_bytes()).hexdigest()
            summary = root / "direct-summary.json"
            completed = subprocess.run(
                [
                    str(RUNNER),
                    "--tmajor-block",
                    str(seed_path),
                    seed_sha,
                    str(artifact),
                    receipt["artifact"]["sha256"],
                    str(summary),
                    "0",
                    "--allow-prefix-kat",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            output = root / "direct-output.bin"
            output.write_bytes(completed.stdout)
            output_sha = hashlib.sha256(completed.stdout).hexdigest()
            replay = replay_tmajor_cuda_arithmetic_sample(
                artifact,
                receipt_path,
                seed_path,
                output,
                expected_receipt_sha256=receipt["receipt_sha256"],
                expected_seed_artifact_sha256=seed_sha,
                expected_output_stream_sha256=output_sha,
                maximum_targets=2,
                maximum_values_per_target=64,
            )
            self.assertEqual(replay["sampled_output_value_count"], 128)
            self.assertTrue(
                replay["directed_binary64_cuda_endpoints_matched"]
            )
            self.assertTrue(replay["complete_streams_authenticated"])
            self.assertEqual(
                replay["independent_exact_rational_global_tail_count"],
                4,
            )
            self.assertEqual(
                replay["independent_Arb_factor_containment_count"],
                0,
            )
            self.assertFalse(replay["full_output_arithmetic_replayed"])
            self.assertFalse(
                replay["recovery_seed_analytic_containment_replayed"]
            )
            self.assertFalse(replay["external_atom_discharged"])
            typed = validate_tmajor_cuda_execution_arithmetic_sample(
                summary,
                artifact,
                receipt_path,
                seed_path,
                output,
                expected_summary_sha256=hashlib.sha256(
                    summary.read_bytes()
                ).hexdigest(),
                expected_receipt_sha256=receipt["receipt_sha256"],
                expected_seed_artifact_sha256=seed_sha,
                maximum_targets=2,
                maximum_values_per_target=64,
            )
            self.assertTrue(
                typed["summary_and_arithmetic_output_identity_equal"]
            )
            self.assertEqual(typed["sampled_output_value_count"], 128)
            self.assertFalse(typed["external_atom_discharged"])

            changed = bytearray(completed.stdout)
            value_offset = struct.calcsize("<8sIIIIQqQQQQ")
            endpoints = list(
                direct_block.FRAME_FACTOR.unpack_from(changed, value_offset)
            )
            endpoints[0] = math.nextafter(endpoints[0], -math.inf)
            direct_block.FRAME_FACTOR.pack_into(
                changed, value_offset, *endpoints
            )
            output.write_bytes(changed)
            with self.assertRaisesRegex(
                DirichletTMajorCudaArithmeticReplayError,
                "exact directed arithmetic differs",
            ):
                replay_tmajor_cuda_arithmetic_sample(
                    artifact,
                    receipt_path,
                    seed_path,
                    output,
                    expected_receipt_sha256=receipt["receipt_sha256"],
                    expected_seed_artifact_sha256=seed_sha,
                    expected_output_stream_sha256=hashlib.sha256(
                        changed
                    ).hexdigest(),
                    maximum_targets=2,
                    maximum_values_per_target=64,
                )

    @unittest.skipUnless(
        RUNNER.is_file() and PINNED_FLINT_AVAILABLE,
        "requires the seeded CUDA runner and pinned python-flint",
    )
    def test_direct_factors_have_independent_arb_containment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, receipt_path, sources = self._build_direct(
                root
            )
            seed_path = sources[0]
            seed_sha = hashlib.sha256(seed_path.read_bytes()).hexdigest()
            summary = root / "direct-summary.json"
            completed = subprocess.run(
                [
                    str(RUNNER),
                    "--tmajor-block",
                    str(seed_path),
                    seed_sha,
                    str(artifact),
                    receipt["artifact"]["sha256"],
                    str(summary),
                    "0",
                    "--allow-prefix-kat",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            output = root / "direct-output.bin"
            output.write_bytes(completed.stdout)
            replay = replay_tmajor_cuda_arithmetic_sample(
                artifact,
                receipt_path,
                seed_path,
                output,
                expected_receipt_sha256=receipt["receipt_sha256"],
                expected_seed_artifact_sha256=seed_sha,
                expected_output_stream_sha256=hashlib.sha256(
                    completed.stdout
                ).hexdigest(),
                maximum_targets=2,
                maximum_values_per_target=1,
                independent_arb_factor_precision_bits=384,
            )
            self.assertEqual(
                replay["independent_Arb_factor_containment_count"],
                4,
            )
            self.assertEqual(
                replay["independent_Arb_factor_runtime"][
                    "precision_bits"
                ],
                384,
            )

    @unittest.skipUnless(
        RUNNER.is_file(), "requires the seeded CUDA runner"
    )
    def test_cuda_uploads_rows_once_and_matches_q_major_kernel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, artifact, _receipt_path, sources = self._build(root)
            seed_path, *seeded_inputs = sources
            seed_sha = hashlib.sha256(seed_path.read_bytes()).hexdigest()
            summary = root / "summary.json"
            completed = subprocess.run(
                [
                    str(RUNNER),
                    "--tmajor-block",
                    str(seed_path),
                    seed_sha,
                    str(artifact),
                    receipt["artifact"]["sha256"],
                    str(summary),
                    "0",
                    "--allow-prefix-kat",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            expected = bytearray()
            for index, source in enumerate(seeded_inputs):
                output = root / f"q-major-{index}.bin"
                subprocess.run(
                    [
                        str(RUNNER),
                        str(seed_path),
                        seed_sha,
                        str(source),
                        str(output),
                        "0",
                        "1",
                        "--allow-prefix-kat",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                expected.extend(output.read_bytes())
            self.assertEqual(completed.stdout, bytes(expected))
            value = json.loads(summary.read_bytes())
            self.assertEqual(value["lattice_h2d_upload_count"], 1)
            self.assertEqual(value["row_count"], 2)
            self.assertEqual(value["target_count"], 2)
            self.assertEqual(value["canonical_descriptor_input_bytes"], 0)
            self.assertEqual(
                value["output_stream_sha256"],
                hashlib.sha256(completed.stdout).hexdigest(),
            )
            self.assertFalse(value["zero_completeness_claimed"])
            self.assertFalse(value["trusted_execution_attested"])
            self.assertFalse(value["external_atom_discharged"])
            summary_sha = hashlib.sha256(summary.read_bytes()).hexdigest()
            replay = validate_tmajor_cuda_execution_summary(
                summary,
                artifact,
                root / "block.receipt.json",
                expected_summary_sha256=summary_sha,
                expected_receipt_sha256=receipt["receipt_sha256"],
            )
            self.assertEqual(
                replay["output_stream_sha256"],
                hashlib.sha256(completed.stdout).hexdigest(),
            )
            self.assertTrue(
                replay["summary_typed_against_fresh_input_replay"]
            )
            self.assertFalse(
                replay["discarded_cuda_arithmetic_independently_replayed"]
            )

            bad_summary = root / "must-not-exist-summary.json"
            failed = subprocess.run(
                [
                    str(RUNNER),
                    "--tmajor-block",
                    str(seed_path),
                    seed_sha,
                    str(artifact),
                    "0" * 64,
                    str(bad_summary),
                    "0",
                    "--allow-prefix-kat",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(failed.stdout, b"")
            self.assertFalse(bad_summary.exists())


if __name__ == "__main__":
    unittest.main()
