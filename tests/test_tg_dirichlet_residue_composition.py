# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest

import mpmath


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.tg_dirichlet_residue_composition_fixture import (  # type: ignore  # noqa: E402
    _recovery_box,
    _zeta_box,
    rehash_job_artifact,
    write_job,
    write_structural_certified_job,
)
from tests.azure_measured_worker_test_scope import (
    bounded_measured_worker_test_scope,
)
from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    canonical_residue_order,
    read_input_header,
)
from tg_verifier.dirichlet_lattice_certificates import (  # noqa: E402
    RECOVERY_HEADER,
)
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    OUTPUT_HEADER as LATTICE_OUTPUT_HEADER,
    OUTPUT_ITEM as LATTICE_OUTPUT_ITEM,
)
from tg_verifier.dirichlet_residue_composition import (  # noqa: E402
    CompositionEngine,
    DirichletResidueCompositionError,
    MPFRFactorProvider,
    FRAMED_REQUEST_SCHEMA,
    SERVICE_REQUEST_SCHEMA,
    benchmark_synthetic,
    capability,
    canonical_json_bytes,
    compose_interval,
    source_work,
)


class DirichletResidueCompositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "fixture"
        cls.job, cls.frames = write_job(cls.root, t_indices=(127, 128))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _copy_fixture(self, name: str) -> tuple[Path, list[dict[str, Path]]]:
        destination = Path(self.temporary.name) / name
        shutil.copytree(self.root, destination)
        job = destination / "job.json"
        value = json.loads(job.read_text("ascii"))
        frames: list[dict[str, Path]] = []
        for frame in value["frames"]:
            frames.append(
                {
                    artifact_name: destination / record["path"]
                    for artifact_name, record in frame.items()
                }
            )
        return job, frames

    def test_mpfr_factor_contains_high_precision_value(self) -> None:
        factor = MPFRFactorProvider(192).factor(
            q=10_001, t_numerator=635, t_denominator=64
        )
        with mpmath.workdps(100):
            s = mpmath.mpf("0.5") + 1j * mpmath.mpf(635) / 64
            value = mpmath.power(10_001, -s)
            self.assertLessEqual(mpmath.mpf(factor[0]), value.real)
            self.assertGreaterEqual(mpmath.mpf(factor[1]), value.real)
            self.assertLessEqual(mpmath.mpf(factor[2]), value.imag)
            self.assertGreaterEqual(mpmath.mpf(factor[3]), value.imag)

    def test_mpfr_factor_reuses_workspace_without_changing_bytes(self) -> None:
        expected = (
            "0x1.1e9bc76ae620fp-9",
            "0x1.1e9bc76ae6210p-9",
            "-0x1.3fbbbd2fb36adp-7",
            "-0x1.3fbbbd2fb36acp-7",
        )
        provider = MPFRFactorProvider(192)
        first = provider.factor(
            q=10_001, t_numerator=315, t_denominator=64
        )
        self.assertEqual(tuple(value.hex() for value in first), expected)
        extreme = provider.factor(
            q=400_000, t_numerator=6_400_000, t_denominator=64
        )
        self.assertEqual(
            tuple(value.hex() for value in extreme),
            (
                "-0x1.914ac7a31e754p-10",
                "-0x1.914ac7a31e753p-10",
                "-0x1.9efc694d7cc28p-12",
                "-0x1.9efc694d7cc27p-12",
            ),
        )
        repeated = provider.factor(
            q=10_001, t_numerator=315, t_denominator=64
        )
        self.assertEqual(tuple(value.hex() for value in repeated), expected)
        provider.close()
        with self.assertRaisesRegex(
            DirichletResidueCompositionError, "provider is closed"
        ):
            provider.factor(
                q=10_001, t_numerator=315, t_denominator=64
            )

    def test_batched_output_is_canonical_and_hash_committed(self) -> None:
        output = Path(self.temporary.name) / "composed.bin"
        receipt_path = Path(self.temporary.name) / "composition-receipt.json"
        engine = CompositionEngine()
        receipt = engine.compose(
            self.job,
            output,
            receipt_path=receipt_path,
            allow_synthetic_kat=True,
        )
        parsed = read_input_header(output)
        self.assertEqual(parsed["q"], 10_001)
        self.assertEqual(parsed["batch_count"], 2)
        self.assertEqual(parsed["group_order"], 9792)
        self.assertEqual(parsed["t_numerator"], 635)
        self.assertEqual(receipt["value_count"], 19_584)
        self.assertEqual(receipt["M"], 4)
        self.assertTrue(receipt["decisions"]["canonical_crt_residue_order_emitted"])
        self.assertFalse(receipt["decisions"]["external_atom_discharged"])
        stored = json.loads(receipt_path.read_text("ascii"))
        self.assertEqual(stored["receipt_sha256"], receipt["receipt_sha256"])

        factor = engine.factor_provider.factor(
            q=10_001, t_numerator=635, t_denominator=64
        )
        raw = output.read_bytes()
        for position, residue in enumerate(canonical_residue_order(10_001)[:16]):
            actual = COMPLEX_INTERVAL.unpack_from(
                raw, INPUT_HEADER.size + position * COMPLEX_INTERVAL.size
            )
            expected = compose_interval(
                _zeta_box(residue, 127), factor, _recovery_box(residue, 127)
            )
            self.assertEqual(actual, expected)

    def test_synthetic_mode_requires_explicit_authorization(self) -> None:
        output = Path(self.temporary.name) / "unauthorized.bin"
        with self.assertRaisesRegex(
            DirichletResidueCompositionError, "explicit KAT authorization"
        ):
            CompositionEngine().compose(self.job, output)
        self.assertFalse(output.exists())

    def test_certified_metadata_hash_chain_is_required_and_reported(self) -> None:
        root = Path(self.temporary.name) / "certified-contract"
        job, _frames = write_structural_certified_job(root)
        output = Path(self.temporary.name) / "certified-contract.bin"
        receipt = CompositionEngine().compose(job, output)
        self.assertEqual(
            receipt["classification"], "certified_residue_composition_adapter_only"
        )
        self.assertTrue(
            receipt["decisions"]["certificate_and_replay_chain_verified"]
        )
        self.assertFalse(receipt["decisions"]["external_atom_discharged"])

    def test_scalar_and_vector_backends_are_byte_identical(self) -> None:
        vector = Path(self.temporary.name) / "vector.bin"
        scalar = Path(self.temporary.name) / "scalar.bin"
        CompositionEngine(backend="numpy").compose(
            self.job, vector, allow_synthetic_kat=True
        )
        CompositionEngine(backend="scalar").compose(
            self.job, scalar, allow_synthetic_kat=True
        )
        self.assertEqual(vector.read_bytes(), scalar.read_bytes())

    def test_named_pipe_output_retains_no_campaign_file(self) -> None:
        fifo = Path(self.temporary.name) / "composed.fifo"
        fifo.unlink(missing_ok=True)
        fifo.parent.mkdir(parents=True, exist_ok=True)
        import os

        os.mkfifo(fifo)
        captured = bytearray()

        def consume() -> None:
            with fifo.open("rb", buffering=0) as source:
                while block := source.read(1024 * 1024):
                    captured.extend(block)

        reader = threading.Thread(target=consume)
        reader.start()
        receipt = CompositionEngine().compose(
            self.job, fifo, allow_synthetic_kat=True
        )
        reader.join(timeout=10)
        self.assertFalse(reader.is_alive())
        self.assertTrue(receipt["output"]["streamed_fifo"])
        self.assertFalse(
            receipt["bounded_working_set"]["campaign_outputs_retained"]
        )
        self.assertEqual(len(captured), INPUT_HEADER.size + 2 * 9792 * 32)
        self.assertEqual(captured[:8], b"TGDAFFI1")

    def test_artifact_hash_tamper_fails_before_output(self) -> None:
        job, frames = self._copy_fixture("hash-tamper")
        recovery = frames[0]["finite_recovery"]
        with recovery.open("r+b") as target:
            target.seek(RECOVERY_HEADER.size + 23)
            byte = target.read(1)
            target.seek(RECOVERY_HEADER.size + 23)
            target.write(bytes([byte[0] ^ 1]))
        output = Path(self.temporary.name) / "hash-tamper.bin"
        with self.assertRaisesRegex(
            DirichletResidueCompositionError, "hash or length mismatch"
        ):
            CompositionEngine().compose(job, output, allow_synthetic_kat=True)
        self.assertFalse(output.exists())

    def test_rehashed_t_mismatch_fails_closed(self) -> None:
        job, frames = self._copy_fixture("t-tamper")
        recovery = frames[1]["finite_recovery"]
        with recovery.open("r+b") as target:
            header = list(RECOVERY_HEADER.unpack(target.read(RECOVERY_HEADER.size)))
            header[4] += 5
            target.seek(0)
            target.write(RECOVERY_HEADER.pack(*header))
        rehash_job_artifact(job, 1, "finite_recovery")
        output = Path(self.temporary.name) / "t-tamper.bin"
        with self.assertRaisesRegex(
            DirichletResidueCompositionError, "TGDLREC1 header"
        ):
            CompositionEngine().compose(job, output, allow_synthetic_kat=True)
        self.assertFalse(output.exists())

    def test_batch_cannot_extend_past_modulus_height(self) -> None:
        job, _frames = self._copy_fixture("height-tamper")
        value = json.loads(job.read_text("ascii"))
        value["first_t_numerator"] = 5 * 127_988
        job.write_bytes(canonical_json_bytes(value))
        output = Path(self.temporary.name) / "height-tamper.bin"
        with self.assertRaisesRegex(
            DirichletResidueCompositionError, "source height"
        ):
            CompositionEngine().compose(job, output, allow_synthetic_kat=True)
        self.assertFalse(output.exists())

    def test_rehashed_M_change_between_frames_fails_closed(self) -> None:
        job, frames = self._copy_fixture("m-tamper")
        recovery = frames[1]["finite_recovery"]
        with recovery.open("r+b") as target:
            header = list(RECOVERY_HEADER.unpack(target.read(RECOVERY_HEADER.size)))
            header[2] += 1
            target.seek(0)
            target.write(RECOVERY_HEADER.pack(*header))
        rehash_job_artifact(job, 1, "finite_recovery")
        output = Path(self.temporary.name) / "m-tamper.bin"
        with self.assertRaisesRegex(
            DirichletResidueCompositionError, "TGDLREC1 header"
        ):
            CompositionEngine().compose(job, output, allow_synthetic_kat=True)
        self.assertFalse(output.exists())

    def test_rehashed_request_permutation_fails_closed(self) -> None:
        job, frames = self._copy_fixture("order-tamper")
        taylor = frames[0]["lattice_output"]
        with taylor.open("r+b") as target:
            target.seek(LATTICE_OUTPUT_HEADER.size)
            first = target.read(LATTICE_OUTPUT_ITEM.size)
            second = target.read(LATTICE_OUTPUT_ITEM.size)
            target.seek(LATTICE_OUTPUT_HEADER.size)
            target.write(second)
            target.write(first)
        rehash_job_artifact(job, 0, "lattice_output")
        output = Path(self.temporary.name) / "order-tamper.bin"
        with self.assertRaisesRegex(
            DirichletResidueCompositionError, "ordering or interval validity differs"
        ):
            CompositionEngine().compose(job, output, allow_synthetic_kat=True)
        self.assertFalse(output.exists())

    def test_persistent_jsonl_service_reuses_bounded_interface(self) -> None:
        output = Path(self.temporary.name) / "service-output.bin"
        receipt = Path(self.temporary.name) / "service-receipt.json"
        request = {
            "schema": SERVICE_REQUEST_SCHEMA,
            "schema_version": 1,
            "job": str(self.job),
            "output": str(output),
            "receipt": str(receipt),
        }
        with bounded_measured_worker_test_scope():
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/tg_dirichlet_residue_composition.py",
                    "--max-batch-count",
                    "2",
                    "serve",
                    "--allow-synthetic-kat",
                ],
                cwd=ROOT,
                input=canonical_json_bytes(request),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        report = json.loads(completed.stdout)
        self.assertEqual(report["batch_count"], 2)
        self.assertEqual(
            report["bounded_working_set"]["binary_interval_payload_bytes"],
            9792 * 32,
        )
        self.assertTrue(output.is_file())
        self.assertTrue(receipt.is_file())

    def test_framed_producer_stdout_is_pure_contiguous_TGDAFFI1(self) -> None:
        second_root = Path(self.temporary.name) / "framed-second"
        second_job, _frames = write_job(second_root, t_indices=(129, 130))
        summary = Path(self.temporary.name) / "framed-summary.json"
        requests = []
        for index, job in enumerate((self.job, second_job)):
            requests.append(
                canonical_json_bytes(
                    {
                        "schema": FRAMED_REQUEST_SCHEMA,
                        "schema_version": 1,
                        "job": str(job),
                        "receipt": str(
                            Path(self.temporary.name) / f"framed-{index}.json"
                        ),
                    }
                )
            )
        with bounded_measured_worker_test_scope():
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/tg_dirichlet_residue_composition.py",
                    "--max-batch-count",
                    "2",
                    "framed-produce",
                    str(summary),
                    "--allow-synthetic-kat",
                ],
                cwd=ROOT,
                input=b"".join(requests),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        offset = 0
        for expected_first in (635, 645):
            header = INPUT_HEADER.unpack_from(completed.stdout, offset)
            self.assertEqual(header[0], b"TGDAFFI1")
            self.assertEqual(header[6], expected_first)
            self.assertEqual(header[4], 2)
            offset += INPUT_HEADER.size + header[9] * COMPLEX_INTERVAL.size
        self.assertEqual(offset, len(completed.stdout))
        report = json.loads(summary.read_text("ascii"))
        self.assertEqual(report["frame_count"], 2)
        self.assertEqual(report["slice_count"], 4)
        self.assertEqual(report["retained_output_frames"], 0)
        self.assertEqual(
            report["TGDAFFI1_stream_sha256"],
            hashlib.sha256(completed.stdout).hexdigest(),
        )
        self.assertEqual(
            report["control_jsonl_sha256"],
            hashlib.sha256(b"".join(requests)).hexdigest(),
        )

    def test_capability_and_exact_work_keep_boundary_honest(self) -> None:
        result = capability()
        self.assertTrue(result["component_ready"])
        self.assertTrue(result["closes_composition_adapter"])
        self.assertFalse(result["closes_external_atom"])
        self.assertFalse(result["production_ready_for_full_atom"])
        self.assertTrue(result["source_scale_storage_bounded"])
        self.assertTrue(result["persistent_framed_producer_ready"])
        self.assertTrue(result["persistent_allchars_framed_service_compatible"])
        self.assertFalse(result["production_supervisor_wired"])
        self.assertFalse(result["source_scale_performance_validated"])
        self.assertIn("Turing completeness", " ".join(result["not_implemented"]))
        work = source_work(batch_size=64)
        self.assertEqual(work["modulus_ordinate_factors"], 4_901_051_274)
        self.assertEqual(work["residue_compositions"], 327_089_206_283_008)
        self.assertEqual(work["batch_invocations"], 76_770_217)
        self.assertEqual(
            work["bytes_if_all_TGDAFFI1_values_were_retained"],
            10_466_854_601_056_256,
        )
        self.assertEqual(work["maximum_live_interval_payload_bytes"], 12_799_616)

    def test_benchmark_is_explicitly_synthetic(self) -> None:
        report = benchmark_synthetic(q=10_001, values=100, repetitions=2)
        self.assertEqual(report["compositions"], 200)
        self.assertIn("synthetic", report["classification"])
        self.assertGreater(report["compositions_per_second"], 0)


if __name__ == "__main__":
    unittest.main()
