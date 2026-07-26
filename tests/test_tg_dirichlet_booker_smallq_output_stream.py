# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from tests.azure_measured_worker_test_scope import (
    bounded_measured_worker_test_scope,
)

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_certified as v2
from tg_verifier.dirichlet_booker_smallq_factored import (
    BATCH_BINDING,
    BATCH_MAGIC,
    CHARACTER_HEADER,
    FORMAT_VERSION,
    INPUT_HEADER,
    PARAMETER_HEADER,
    PLAN_COMMITMENT,
    PLAN_MAGIC,
    PARITY_SEED,
    REDUCED_SERVICE_OUTPUT_MAGIC,
    SERVICE_OUTPUT_BINDING,
    SERVICE_OUTPUT_MAGIC,
    SHARED_PREFIX,
    _character_roster_digest,
)
from tg_verifier.dirichlet_booker_smallq_output_stream import (
    SmallQOutputStreamError,
    canonical_json_bytes,
    reduce_factored_service_output_stream,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_fixture(root: Path) -> tuple[Path, list[Path], bytes]:
    q = 5
    transform_length = 8
    characters = (2, 3, 4)
    plan_path = root / "plan.bin"
    plan_raw = b"".join(
        (
            INPUT_HEADER.pack(
                PLAN_MAGIC,
                FORMAT_VERSION,
                q,
                4,
                len(characters),
                transform_length,
                0,
                transform_length,
                1,
                96,
                0,
            ),
            PLAN_COMMITMENT.pack(_character_roster_digest(characters)),
            PARAMETER_HEADER.pack(0, 1, 1, 1, transform_length, 1),
            b"".join(
                SHARED_PREFIX.pack(
                    index,
                    index if index <= transform_length // 2 else index - transform_length,
                )
                + v2.DISK.pack(0.0, 0.0, 0.0)
                + PARITY_SEED.pack(0, 0, 0.0, 0.0, 0.0, 0.0)
                + PARITY_SEED.pack(0, 0, 0.0, 0.0, 0.0, 0.0)
                for index in range(transform_length)
            ),
        )
    )
    plan_path.write_bytes(plan_raw)
    plan_sha = hashlib.sha256(plan_raw).digest()

    batches: list[Path] = []
    outputs: list[bytes] = []
    partitions = ((0, (2, 3)), (2, (4,)))
    for ordinal, (start, ids) in enumerate(partitions):
        batch_path = root / f"batch-{ordinal:08d}.bin"
        pieces = [
            INPUT_HEADER.pack(
                BATCH_MAGIC,
                FORMAT_VERSION,
                q,
                4,
                len(ids),
                transform_length,
                0,
                transform_length,
                1,
                96,
                0,
            ),
            BATCH_BINDING.pack(plan_sha, start, len(characters), ordinal, 2),
        ]
        for character_id in ids:
            pieces.append(
                CHARACTER_HEADER.pack(character_id, character_id & 1, 0, 0, 1.0, 0.0, 0.0)
            )
            pieces.append(struct.pack(f"<{q}I", *(0 for _ in range(q))))
        batch_raw = b"".join(pieces)
        batch_path.write_bytes(batch_raw)
        batches.append(batch_path)
        batch_sha = hashlib.sha256(batch_raw).digest()
        butterflies = len(ids) * (transform_length // 2) * 3
        output = [
            v2.OUTPUT_HEADER.pack(
                SERVICE_OUTPUT_MAGIC,
                FORMAT_VERSION,
                q,
                len(ids),
                1,
                0,
                transform_length,
                100 + ordinal,
                butterflies,
                1000 + ordinal,
                0,
                0,
            ),
            SERVICE_OUTPUT_BINDING.pack(
                plan_sha, batch_sha, start, len(characters), ordinal, 2
            ),
        ]
        for character_id in ids:
            for index in range(transform_length):
                output.append(
                    v2.OUTPUT_ITEM.pack(
                        character_id,
                        index,
                        character_id + index / 16,
                        -index / 32,
                        0.125,
                        0,
                        0,
                    )
                )
        outputs.append(b"".join(output))
    return plan_path, batches, b"".join(outputs)


def _write_canonical_reduced_fixture(root: Path) -> tuple[Path, list[Path], bytes]:
    """One canonical q=10000 plan, whose source grid is shorter than its DFT."""

    q = 10_000
    parameters = base.transform_parameters(q)
    length = parameters.transform_length
    character_id = 1877
    plan_path = root / "source-plan.bin"
    plan_prefix = b"".join(
        (
            INPUT_HEADER.pack(
                PLAN_MAGIC,
                FORMAT_VERSION,
                q,
                2,
                1,
                length,
                0,
                length,
                1,
                96,
                0,
            ),
            PLAN_COMMITMENT.pack(_character_roster_digest((character_id,))),
            PARAMETER_HEADER.pack(
                parameters.eta.numerator,
                parameters.eta.denominator,
                parameters.a.numerator,
                parameters.a.denominator,
                parameters.b.numerator,
                parameters.b.denominator,
            ),
        )
    )
    digest = hashlib.sha256()
    with plan_path.open("wb") as output:
        output.write(plan_prefix)
        digest.update(plan_prefix)
        for index in range(length):
            signed = index if index <= length // 2 else index - length
            record = b"".join(
                (
                    SHARED_PREFIX.pack(index, signed),
                    v2.DISK.pack(0.0, 0.0, 0.0),
                    PARITY_SEED.pack(0, 0, 0.0, 0.0, 0.0, 0.0),
                    PARITY_SEED.pack(0, 0, 0.0, 0.0, 0.0, 0.0),
                )
            )
            output.write(record)
            digest.update(record)
    plan_sha = digest.digest()
    batch_path = root / "source-batch-00000000.bin"
    batch_raw = b"".join(
        (
            INPUT_HEADER.pack(
                BATCH_MAGIC,
                FORMAT_VERSION,
                q,
                2,
                1,
                length,
                0,
                length,
                1,
                96,
                0,
            ),
            BATCH_BINDING.pack(plan_sha, 0, 1, 0, 1),
            CHARACTER_HEADER.pack(character_id, 1, 0, 0, 1.0, 0.0, 0.0),
            struct.pack(f"<{q}I", *(0 for _ in range(q))),
        )
    )
    batch_path.write_bytes(batch_raw)
    batch_sha = hashlib.sha256(batch_raw).digest()
    published = parameters.sample_count
    pieces = [
        v2.OUTPUT_HEADER.pack(
            REDUCED_SERVICE_OUTPUT_MAGIC,
            FORMAT_VERSION,
            q,
            1,
            1,
            0,
            published,
            0,
            (length // 2) * (length.bit_length() - 1),
            0,
            0,
            0,
        ),
        SERVICE_OUTPUT_BINDING.pack(plan_sha, batch_sha, 0, 1, 0, 1),
    ]
    for index in range(published):
        pieces.append(v2.OUTPUT_ITEM.pack(character_id, index, 0.0, 0.0, 0.0, 0, 0))
    return plan_path, [batch_path], b"".join(pieces)


class SmallQOutputStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.plan, self.batches, self.stream = _write_fixture(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_compact_receipt_checks_complete_stream(self) -> None:
        receipt_path = self.root / "receipt.json"
        receipt = reduce_factored_service_output_stream(
            self.plan,
            self.batches,
            io.BytesIO(self.stream),
            receipt_path=receipt_path,
            chunk_items=3,
            backend="scalar",
        )
        self.assertEqual(receipt["batch_count"], 2)
        self.assertEqual(receipt["character_count"], 3)
        self.assertEqual(receipt["item_count"], 24)
        self.assertEqual(receipt["frame_mmr_leaf_count"], 2)
        self.assertEqual(receipt["persistent_raw_output_bytes_required"], 0)
        self.assertTrue(receipt["full_character_partition_checked"])
        self.assertFalse(receipt["arithmetic_containment_replayed"])
        self.assertFalse(receipt["external_atom_discharged"])
        self.assertEqual(json.loads(receipt_path.read_text()), receipt)
        self.assertLess(receipt_path.stat().st_size, 4096)
        body = dict(receipt)
        retained_self_hash = body.pop("receipt_sha256")
        self.assertEqual(
            retained_self_hash, hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        )

    def test_canonical_source_sample_only_stream_omits_guard_outputs(self) -> None:
        plan, batches, stream = _write_canonical_reduced_fixture(self.root)
        receipt = reduce_factored_service_output_stream(
            plan, batches, io.BytesIO(stream), chunk_items=1 << 15
        )
        parameters = base.transform_parameters(10_000)
        self.assertEqual(receipt["output_mode"], "source_samples_only")
        self.assertTrue(receipt["source_parameters_match"])
        self.assertEqual(receipt["item_count"], parameters.sample_count)
        self.assertLess(receipt["item_count"], parameters.transform_length)

    def test_vector_and_scalar_backends_do_not_change_commitment(self) -> None:
        scalar = reduce_factored_service_output_stream(
            self.plan,
            self.batches,
            io.BytesIO(self.stream),
            chunk_items=11,
            backend="scalar",
        )
        try:
            vector = reduce_factored_service_output_stream(
                self.plan,
                self.batches,
                io.BytesIO(self.stream),
                chunk_items=11,
                backend="numpy",
            )
        except SmallQOutputStreamError as error:
            if "unavailable" in str(error):
                self.skipTest(str(error))
            raise
        self.assertEqual(vector["output_stream_mmr_sha256"], scalar["output_stream_mmr_sha256"])
        self.assertEqual(vector["frame_mmr_sha256"], scalar["frame_mmr_sha256"])

    def test_wrong_item_identity_fails_closed(self) -> None:
        raw = bytearray(self.stream)
        first_item = v2.OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size
        struct.pack_into("<Q", raw, first_item + 8, 1)
        with self.assertRaisesRegex(SmallQOutputStreamError, "item identity"):
            reduce_factored_service_output_stream(
                self.plan, self.batches, io.BytesIO(raw), backend="scalar"
            )

    def test_nonfinite_radius_and_status_fail_closed(self) -> None:
        first_item = v2.OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size
        cases = ((first_item + 32, float("nan"), "<d"), (first_item + 40, 1, "<I"))
        for offset, value, kind in cases:
            with self.subTest(offset=offset):
                raw = bytearray(self.stream)
                struct.pack_into(kind, raw, offset, value)
                with self.assertRaisesRegex(SmallQOutputStreamError, "item identity"):
                    reduce_factored_service_output_stream(
                        self.plan, self.batches, io.BytesIO(raw), backend="scalar"
                    )

    def test_reordered_binding_and_trailing_byte_fail_closed(self) -> None:
        first_frame_size = (
            v2.OUTPUT_HEADER.size
            + SERVICE_OUTPUT_BINDING.size
            + 16 * v2.OUTPUT_ITEM.size
        )
        reordered = self.stream[first_frame_size:] + self.stream[:first_frame_size]
        with self.assertRaisesRegex(SmallQOutputStreamError, "header, binding"):
            reduce_factored_service_output_stream(
                self.plan, self.batches, io.BytesIO(reordered)
            )
        with self.assertRaisesRegex(SmallQOutputStreamError, "trailing bytes"):
            reduce_factored_service_output_stream(
                self.plan, self.batches, io.BytesIO(self.stream + b"x")
            )

    def test_reduced_magic_rejects_noncanonical_plan(self) -> None:
        raw = bytearray(self.stream)
        raw[:8] = REDUCED_SERVICE_OUTPUT_MAGIC
        with self.assertRaisesRegex(SmallQOutputStreamError, "canonical source"):
            reduce_factored_service_output_stream(
                self.plan, self.batches, io.BytesIO(raw)
            )

    def test_cli_consumes_standard_input(self) -> None:
        receipt = self.root / "cli-receipt.json"
        with bounded_measured_worker_test_scope():
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        ROOT
                        / "tools/tg_dirichlet_booker_smallq_output_stream.py"
                    ),
                    str(self.plan),
                    str(self.root),
                    str(receipt),
                    "--chunk-items",
                    "5",
                ],
                input=self.stream,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["output_stream_mmr_sha256"],
            json.loads(receipt.read_text())["output_stream_mmr_sha256"],
        )

    def test_cuda_service_can_stream_frames_to_stdout(self) -> None:
        runner = os.environ.get("TG_SMALLQ_CERTIFIED_RUNNER")
        if not runner:
            self.skipTest("set TG_SMALLQ_CERTIFIED_RUNNER to exercise CUDA stdout")
        command = [runner, "--factored-service", str(self.plan)]
        for batch in self.batches:
            command.extend((str(batch), "-"))
        completed = subprocess.run(command, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        # JSON diagnostics move to stderr so stdout remains an exact binary
        # concatenation accepted by the reducer.
        self.assertTrue(completed.stderr.startswith(b"{"))
        receipt = reduce_factored_service_output_stream(
            self.plan, self.batches, io.BytesIO(completed.stdout)
        )
        self.assertEqual(receipt["batch_count"], 2)
        self.assertEqual(receipt["item_count"], 24)

    def test_cuda_service_file_output_remains_available(self) -> None:
        runner = os.environ.get("TG_SMALLQ_CERTIFIED_RUNNER")
        if not runner:
            self.skipTest("set TG_SMALLQ_CERTIFIED_RUNNER to exercise CUDA files")
        outputs = [self.root / f"cuda-output-{index}.bin" for index in range(2)]
        command = [runner, "--factored-service", str(self.plan)]
        for batch, output in zip(self.batches, outputs):
            command.extend((str(batch), str(output)))
        completed = subprocess.run(command, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertTrue(completed.stdout.startswith(b"{"))
        raw = b"".join(output.read_bytes() for output in outputs)
        self.assertTrue(raw.startswith(SERVICE_OUTPUT_MAGIC))
        receipt = reduce_factored_service_output_stream(
            self.plan, self.batches, io.BytesIO(raw)
        )
        self.assertEqual(receipt["output_mode"], "complete_transform")

    def test_cuda_service_source_sample_only_mode(self) -> None:
        runner = os.environ.get("TG_SMALLQ_CERTIFIED_RUNNER")
        if not runner:
            self.skipTest("set TG_SMALLQ_CERTIFIED_RUNNER to exercise reduced CUDA stdout")
        rejected = [runner, "--source-samples-only", "--factored-service", str(self.plan)]
        for batch in self.batches:
            rejected.extend((str(batch), "-"))
        malformed = subprocess.run(rejected, capture_output=True, check=False)
        self.assertNotEqual(malformed.returncode, 0)
        self.assertIn(b"exact canonical source plan", malformed.stderr)
        plan, batches, _expected = _write_canonical_reduced_fixture(self.root)
        completed = subprocess.run(
            [
                runner,
                "--source-samples-only",
                "--factored-service",
                str(plan),
                str(batches[0]),
                "-",
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        receipt = reduce_factored_service_output_stream(
            plan, batches, io.BytesIO(completed.stdout)
        )
        self.assertEqual(receipt["output_mode"], "source_samples_only")
        self.assertEqual(receipt["item_count"], base.transform_parameters(10_000).sample_count)


if __name__ == "__main__":
    unittest.main()
