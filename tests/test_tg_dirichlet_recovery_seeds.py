# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tg_verifier.dirichlet_recovery_seeds as seeds  # noqa: E402
from tg_verifier.dirichlet_lattice_certificates import _contains_arb  # noqa: E402
from tests.tg_dirichlet_residue_composition_fixture import write_job  # noqa: E402
from tg_verifier.dirichlet_largeq_batch import (  # noqa: E402
    CERTIFIED_RESIDUE_BOX,
    FRAME_FACTOR,
    INPUT_HEADER as LARGEQ_INPUT_HEADER,
    RESIDUE_DESCRIPTOR,
    pack_input,
    write_job_from_composition_job,
)
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    LATTICE_CELL,
    LATTICE_ROWS,
    TAYLOR_COLUMNS,
)


try:
    FLINT = seeds._load_flint()
except seeds.DirichletRecoverySeedError:
    FLINT = None


class DirichletRecoverySeedStructuralTests(unittest.TestCase):
    def test_format_and_source_identity_are_pinned(self) -> None:
        self.assertEqual(seeds.HEADER.size, 96)
        self.assertEqual(seeds.CHUNK_HEADER.size, 64)
        self.assertEqual(seeds.SEED_RECORD.size, 48)
        self.assertEqual(seeds.FOOTER.size, 96)
        self.assertEqual(seeds.SOURCE_M, 4)
        self.assertEqual(seeds.SOURCE_X_STOP, 1_999_999)
        report = seeds.capability()
        self.assertEqual(report["full_artifact_payload_bytes"], 95_999_952)
        self.assertEqual(
            report["logical_per_value_recovery_bytes_replaced"],
            13_083_568_251_320_320,
        )
        self.assertTrue(report["standalone_seeded_cuda_expansion_implemented"])
        self.assertTrue(report["gpu_expansion_integrated_with_fused_largeq_kernel"])
        self.assertFalse(report["shared_cmake_target_integrated"])
        self.assertFalse(report["external_atom_discharged"])


@unittest.skipUnless(FLINT is not None, "requires pinned python-flint 0.9.0")
class DirichletRecoverySeedArbTests(unittest.TestCase):
    def test_sample_artifact_is_deterministic_and_fully_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = []
            manifests = []
            for index in range(2):
                artifact = root / f"seeds-{index}.bin"
                manifest = root / f"manifest-{index}.json"
                result = seeds.generate_seed_artifact(
                    artifact,
                    manifest,
                    sample_x_stop=31,
                    chunk_records=7,
                )
                self.assertFalse(
                    result["manifest"]["geometry"]["full_source_seed_range"]
                )
                artifacts.append(artifact)
                manifests.append(manifest)
            self.assertEqual(artifacts[0].read_bytes(), artifacts[1].read_bytes())
            self.assertEqual(manifests[0].read_bytes(), manifests[1].read_bytes())
            replay = seeds.verify_seed_artifact(artifacts[0], manifests[0])
            self.assertEqual(replay["replay"]["record_count"], 31)
            self.assertTrue(
                replay["replay"]["higher_precision_arb_containment_passed"]
            )
            self.assertFalse(replay["replay"]["external_atom_discharged"])

    def test_payload_corruption_fails_before_a_chunk_is_yielded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "seeds.bin"
            manifest = root / "manifest.json"
            seeds.generate_seed_artifact(
                artifact, manifest, sample_x_stop=9, chunk_records=9
            )
            corrupt = root / "corrupt.bin"
            shutil.copyfile(artifact, corrupt)
            with corrupt.open("r+b") as target:
                target.seek(seeds.HEADER.size + seeds.CHUNK_HEADER.size + 3)
                original = target.read(1)
                target.seek(-1, 1)
                target.write(bytes([original[0] ^ 1]))
            iterator = seeds.iter_authenticated_seed_chunks(corrupt)
            with self.assertRaisesRegex(
                seeds.DirichletRecoverySeedError, "chunk SHA-256"
            ):
                next(iterator)

    def test_footer_corruption_fails_after_authenticated_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "seeds.bin"
            manifest = root / "manifest.json"
            seeds.generate_seed_artifact(
                artifact, manifest, sample_x_stop=9, chunk_records=9
            )
            corrupt = root / "footer-corrupt.bin"
            shutil.copyfile(artifact, corrupt)
            with corrupt.open("r+b") as target:
                target.seek(-1, 2)
                original = target.read(1)
                target.seek(-1, 1)
                target.write(bytes([original[0] ^ 1]))
            with self.assertRaisesRegex(
                seeds.DirichletRecoverySeedError, "footer or global digest"
            ):
                list(seeds.iter_authenticated_seed_chunks(corrupt))

    def test_maximum_grid_recurrence_contains_direct_arb_sum(self) -> None:
        assert FLINT is not None
        q = 10_001
        a = 1
        t_index = 127_987
        lookup = {
            q * n + a: seeds._generated_seed(FLINT, q * n + a, 192)
            for n in range(seeds.SOURCE_M + 1)
        }
        box = seeds.recovery_box_from_seed_lookup(q, a, t_index, lookup)
        with FLINT.ctx.workprec(384):
            s = FLINT.acb(
                FLINT.arb(1) / 2,
                FLINT.arb(seeds.SOURCE_STEP_NUMERATOR * t_index)
                / seeds.SOURCE_STEP_DENOMINATOR,
            )
            direct = FLINT.acb(0)
            for n in range(seeds.SOURCE_M + 1):
                direct += FLINT.acb(q * n + a) ** (-s)
        flat = (box[0][0], box[0][1], box[1][0], box[1][1])
        self.assertTrue(_contains_arb(flat, direct))
        self.assertLess(box[0][1] - box[0][0], 2e-10)
        self.assertLess(box[1][1] - box[1][0], 2e-10)

    def test_artifact_hash_is_bound_before_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "seeds.bin"
            manifest = root / "manifest.json"
            seeds.generate_seed_artifact(
                artifact, manifest, sample_x_stop=5, chunk_records=5
            )
            before = hashlib.sha256(artifact.read_bytes()).hexdigest()
            with artifact.open("r+b") as target:
                target.seek(seeds.HEADER.size + seeds.CHUNK_HEADER.size)
                original = target.read(1)
                target.seek(-1, 1)
                target.write(bytes([original[0] ^ 1]))
            self.assertNotEqual(before, hashlib.sha256(artifact.read_bytes()).hexdigest())
            with self.assertRaisesRegex(
                seeds.DirichletRecoverySeedError, "hash or size"
            ):
                seeds.verify_seed_artifact(artifact, manifest)

    def test_manifest_stream_digests_are_bound_to_authenticated_footer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "seeds.bin"
            manifest = root / "manifest.json"
            seeds.generate_seed_artifact(
                artifact, manifest, sample_x_stop=5, chunk_records=5
            )
            value = json.loads(manifest.read_bytes())
            value["artifact"]["records_sha256"] = "0" * 64
            body = dict(value)
            body.pop("manifest_sha256")
            value["manifest_sha256"] = seeds.sha256_bytes(
                seeds.canonical_json_bytes(body)
            )
            altered = root / "altered-manifest.json"
            altered.write_bytes(seeds.canonical_json_bytes(value))
            with self.assertRaisesRegex(
                seeds.DirichletRecoverySeedError,
                "manifest stream digests differ",
            ):
                seeds.verify_seed_artifact(artifact, altered)

    def test_v1_to_seeded_v2_removes_every_recovery_rectangle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            composition, _ = write_job(root / "source", t_indices=(127, 128))
            job = root / "job.json"
            write_job_from_composition_job(composition, job, certified=False)
            source = root / "v1.bin"
            packed = pack_input(job, source, allow_synthetic_kat=True)
            output = root / "v2.bin"
            receipt = seeds.convert_largeq_v1_to_seeded_v2(
                source,
                output,
                expected_source_sha256=packed["output"]["sha256"],
                seed_artifact_sha256="1" * 64,
                seed_replay_sha256="2" * 64,
            )
            self.assertEqual(output.read_bytes()[:8], seeds.SEEDED_BATCH_MAGIC)
            self.assertEqual(receipt["logical_recovery_rectangles_removed"], 19_584)
            self.assertEqual(receipt["logical_recovery_bytes_removed"], 626_688)
            self.assertEqual(receipt["output"]["size_bytes"], 2_175_664)
            self.assertFalse(receipt["decisions"]["external_atom_discharged"])

    def test_v1_to_seeded_v2_rejects_nonuniform_tail_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            composition, _ = write_job(root / "source", t_indices=(127,))
            job = root / "job.json"
            write_job_from_composition_job(composition, job, certified=False)
            source = root / "v1.bin"
            pack_input(job, source, allow_synthetic_kat=True)
            header = LARGEQ_INPUT_HEADER.unpack_from(source.read_bytes())
            group_order = header[9]
            lattice_count = header[13]
            certified_offset = (
                LARGEQ_INPUT_HEADER.size
                + group_order * RESIDUE_DESCRIPTOR.size
                + header[6] * FRAME_FACTOR.size
                + lattice_count * LATTICE_CELL.size
            )
            with source.open("r+b") as target:
                target.seek(certified_offset + CERTIFIED_RESIDUE_BOX.size)
                radius = struct.unpack("<d", target.read(8))[0]
                target.seek(-8, 1)
                target.write(struct.pack("<d", math.nextafter(radius, math.inf)))
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            output = root / "must-not-exist.bin"
            with self.assertRaisesRegex(
                seeds.DirichletRecoverySeedError, "not uniform"
            ):
                seeds.convert_largeq_v1_to_seeded_v2(
                    source,
                    output,
                    expected_source_sha256=digest,
                    seed_artifact_sha256="1" * 64,
                    seed_replay_sha256="2" * 64,
                )
            self.assertFalse(output.exists())


CUDA_RUNNER = Path(
    os.environ.get("TG_DIRICHLET_RECOVERY_SEEDED_BINARY", "/nonexistent")
)
SEEDED_FUSED_RUNNER = Path(
    os.environ.get("TG_DIRICHLET_LARGEQ_SEEDED_BINARY", "/nonexistent")
)


@unittest.skipUnless(
    FLINT is not None and CUDA_RUNNER.is_file(),
    "requires pinned python-flint and the seeded CUDA runner",
)
class DirichletRecoverySeedCudaTests(unittest.TestCase):
    def test_cuda_recurrence_has_no_transcendentals_and_contains_arb(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "seeds.bin"
            manifest = root / "manifest.json"
            generated = seeds.generate_seed_artifact(
                artifact,
                manifest,
                sample_x_stop=50_004,
                chunk_records=4_096,
            )
            digest = generated["manifest"]["artifact"]["sha256"]
            output = root / "recovery.bin"
            completed = subprocess.run(
                [
                    str(CUDA_RUNNER),
                    str(artifact),
                    digest,
                    "10001",
                    "127986",
                    "2",
                    str(output),
                    "0",
                    "1",
                    "--allow-prefix-kat",
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn('"transcendental_device_calls":0', completed.stdout)
            report = seeds.verify_cuda_output(
                artifact,
                digest,
                output,
                maximum_values=32,
            )
            self.assertTrue(report["cpu_directed_recurrence_encloses_cuda"])
            self.assertTrue(report["direct_higher_precision_arb_values_contained"])
            self.assertFalse(report["complete_frame_replayed"])
            self.assertFalse(report["external_atom_discharged"])

    def test_cuda_runner_rejects_wrong_artifact_digest_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "seeds.bin"
            manifest = root / "manifest.json"
            seeds.generate_seed_artifact(
                artifact, manifest, sample_x_stop=50_004, chunk_records=4_096
            )
            output = root / "must-not-exist.bin"
            completed = subprocess.run(
                [
                    str(CUDA_RUNNER),
                    str(artifact),
                    "0" * 64,
                    "10001",
                    "0",
                    "1",
                    str(output),
                    "0",
                    "1",
                    "--allow-prefix-kat",
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("SHA-256 differs before parsing", completed.stderr)
            self.assertFalse(output.exists())


@unittest.skipUnless(
    FLINT is not None and SEEDED_FUSED_RUNNER.is_file(),
    "requires pinned python-flint and the seeded fused CUDA runner",
)
class DirichletRecoverySeededFusedCudaTests(unittest.TestCase):
    def test_compact_fused_output_contains_direct_recovery_values(self) -> None:
        from tg_verifier.dirichlet_allchars_stage import (
            INPUT_HEADER as ALLCHARS_HEADER,
            canonical_residue_order,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "seeds.bin"
            manifest = root / "manifest.json"
            generated = seeds.generate_seed_artifact(
                artifact, manifest, sample_x_stop=50_004, chunk_records=4_096
            )
            seed_sha = generated["manifest"]["artifact"]["sha256"]
            composition, _ = write_job(root / "source", t_indices=(127, 128))
            job = root / "job.json"
            write_job_from_composition_job(composition, job, certified=False)
            v1 = root / "v1.bin"
            packed = pack_input(job, v1, allow_synthetic_kat=True)
            v2 = root / "v2.bin"
            seeds.convert_largeq_v1_to_seeded_v2(
                v1,
                v2,
                expected_source_sha256=packed["output"]["sha256"],
                seed_artifact_sha256=seed_sha,
                seed_replay_sha256="2" * 64,
            )
            output = root / "output.bin"
            completed = subprocess.run(
                [
                    str(SEEDED_FUSED_RUNNER),
                    str(artifact),
                    seed_sha,
                    str(v2),
                    str(output),
                    "0",
                    "1",
                    "--allow-prefix-kat",
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn('"recovery_rectangles_streamed":0', completed.stdout)
            raw = output.read_bytes()
            header = ALLCHARS_HEADER.unpack_from(raw)
            self.assertEqual(header[0], b"TGDAFFI1")
            q = header[2]
            group_order = header[5]
            values = header[9]
            residues = canonical_residue_order(q)
            for index in seeds._sample_indices(values, 32):
                frame = index // group_order
                a = residues[index % group_order]
                box = struct.unpack_from("<dddd", raw, ALLCHARS_HEADER.size + index * 32)
                with FLINT.ctx.workprec(384):
                    s = FLINT.acb(
                        FLINT.arb(1) / 2,
                        FLINT.arb(header[6] + frame * header[8]) / header[7],
                    )
                    direct = FLINT.acb(0)
                    for n in range(seeds.SOURCE_M + 1):
                        direct += FLINT.acb(q * n + a) ** (-s)
                self.assertTrue(_contains_arb(box, direct))


if __name__ == "__main__":
    unittest.main()
