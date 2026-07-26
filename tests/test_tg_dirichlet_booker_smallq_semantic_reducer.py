# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import io
import json
import math
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
    PARITY_SEED,
    PLAN_COMMITMENT,
    PLAN_MAGIC,
    REDUCED_SERVICE_OUTPUT_MAGIC,
    SERVICE_OUTPUT_BINDING,
    SHARED_PREFIX,
    _character_roster_digest,
)
from tg_verifier.dirichlet_booker_smallq_output_stream import _preflight_batches
from tg_verifier.dirichlet_booker_smallq_semantic_reducer import (
    AMBIGUOUS_CODE,
    CONTROL_ALGORITHM_ID,
    CONTROL_CHECKER_ID,
    CONTROL_FORMAT_VERSION,
    CONTROL_HEADER,
    CONTROL_ITEM,
    CONTROL_MAGIC,
    CONTROL_RECEIPT_SCHEMA,
    NEGATIVE_CODE,
    POSITIVE_CODE,
    SIGN_HEADER,
    SmallQSemanticReducerError,
    _batch_partition_digest,
    canonical_json_bytes,
    reduce_semantic_sign_stream,
    inspect_sign_artifact,
    unpack_sign_codes,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_source_fixture(
    root: Path,
) -> tuple[Path, list[Path], Path, Path, bytes, bytes]:
    """Write one exact q=10000 source plan with one character of each parity."""

    q = 10_000
    parameters = base.transform_parameters(q)
    length = parameters.transform_length
    characters = ((1877, 0), (1879, 1))
    plan_path = root / "plan.bin"
    prefix = b"".join(
        (
            INPUT_HEADER.pack(
                PLAN_MAGIC,
                FORMAT_VERSION,
                q,
                2,
                len(characters),
                length,
                0,
                length,
                1,
                96,
                0,
            ),
            PLAN_COMMITMENT.pack(
                _character_roster_digest(tuple(value[0] for value in characters))
            ),
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
    plan_digest = hashlib.sha256()
    with plan_path.open("wb") as output:
        output.write(prefix)
        plan_digest.update(prefix)
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
            plan_digest.update(record)
    plan_sha256 = plan_digest.digest()

    batches: list[Path] = []
    frame_parts: list[bytes] = []
    expected_codes = bytearray()
    for ordinal, (character_id, parity) in enumerate(characters):
        batch_path = root / f"batch-{ordinal:08d}.bin"
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
                BATCH_BINDING.pack(
                    plan_sha256, ordinal, len(characters), ordinal, len(characters)
                ),
                CHARACTER_HEADER.pack(
                    character_id, parity, 0, 0, 1.0, 0.0, 0.0
                ),
                struct.pack(f"<{q}I", *(0 for _ in range(q))),
            )
        )
        batch_path.write_bytes(batch_raw)
        batches.append(batch_path)
        batch_sha256 = hashlib.sha256(batch_raw).digest()
        frame_parts.extend(
            (
                v2.OUTPUT_HEADER.pack(
                    REDUCED_SERVICE_OUTPUT_MAGIC,
                    FORMAT_VERSION,
                    q,
                    1,
                    1,
                    0,
                    parameters.sample_count,
                    0,
                    (length // 2) * (length.bit_length() - 1),
                    0,
                    0,
                    0,
                ),
                SERVICE_OUTPUT_BINDING.pack(
                    plan_sha256,
                    batch_sha256,
                    ordinal,
                    len(characters),
                    ordinal,
                    len(characters),
                ),
            )
        )
        for sample in range(parameters.sample_count):
            selector = sample % 4
            # Even threshold is 0.25 and odd threshold is 2.0.  The first
            # three values certify +, -, ambiguous for even but only the
            # fourth value certifies + for odd.  This catches parity swaps.
            if selector == 0:
                real = 1.0
                code = POSITIVE_CODE if parity == 0 else AMBIGUOUS_CODE
            elif selector == 1:
                real = -1.0
                code = NEGATIVE_CODE if parity == 0 else AMBIGUOUS_CODE
            elif selector == 2:
                real = 0.35
                code = AMBIGUOUS_CODE
            else:
                real = 3.0
                code = POSITIVE_CODE
            frame_parts.append(
                v2.OUTPUT_ITEM.pack(
                    character_id, sample, real, -0.125, 0.1, 0, 0
                )
            )
            expected_codes.append(code)
    stream = b"".join(frame_parts)

    plan, parsed_batches = _preflight_batches(plan_path, batches)
    partition_sha256 = _batch_partition_digest(parsed_batches)
    control_path = root / "control.bin"
    control_header = CONTROL_HEADER.pack(
        CONTROL_MAGIC,
        CONTROL_FORMAT_VERSION,
        q,
        1,
        1,
        length,
        parameters.sample_count,
        192,
        0,
        plan.sha256,
        partition_sha256,
    )
    with control_path.open("wb") as output:
        output.write(control_header)
        record = CONTROL_ITEM.pack(0.25, 2.0)
        for _ in range(parameters.sample_count):
            output.write(record)
    control_sha256 = hashlib.sha256(control_path.read_bytes()).hexdigest()
    receipt = {
        "algorithm_id": CONTROL_ALGORITHM_ID,
        "all_even_and_odd_records_higher_precision_replayed": True,
        "all_source_ordinates_replayed": True,
        "atom_id": base.ATOM_ID,
        "author": "Gershon Bialer",
        "canonical_primitive_character_roster_replayed": True,
        "character_batch_partition_sha256": partition_sha256.hex(),
        "character_id_parity_mapping_replayed": True,
        "character_parity_counts": [1, 1],
        "checker_id": CONTROL_CHECKER_ID,
        "classification": (
            "exact_time_tail_control_replay_not_grh_or_execution_evidence"
        ),
        "control_sha256": control_sha256,
        "control_size_bytes": control_path.stat().st_size,
        "elapsed_nanoseconds": 0,
        "external_atom_discharged": False,
        "guard_bits": 64,
        "kind": CONTROL_RECEIPT_SCHEMA,
        "passed": True,
        "plan_sha256": plan.sha256.hex(),
        "producer_precision_bits": 192,
        "q": q,
        "sample_count": parameters.sample_count,
        "source_parameters_exact": True,
        "transform_length": length,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    receipt_path = root / "control-receipt.json"
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    return (
        plan_path,
        batches,
        control_path,
        receipt_path,
        stream,
        bytes(expected_codes),
    )


class SmallQSemanticReducerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_temporary = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.fixture_temporary.name)
        (
            cls.plan,
            cls.batches,
            cls.control,
            cls.control_receipt,
            cls.stream,
            cls.expected_codes,
        ) = _write_source_fixture(cls.fixture_root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_temporary.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _reduce(
        self, *, backend: str = "auto", stream: bytes | None = None
    ) -> tuple[dict[str, object], Path, Path]:
        signs = self.root / f"signs-{backend}.bin"
        receipt = self.root / f"receipt-{backend}.json"
        result = reduce_semantic_sign_stream(
            self.plan,
            self.batches,
            self.control,
            self.control_receipt,
            io.BytesIO(self.stream if stream is None else stream),
            signs,
            receipt_path=receipt,
            chunk_items=10_003,
            backend=backend,
        )
        return result, signs, receipt

    def test_complete_ordered_reduction_preserves_parity_and_ambiguity(self) -> None:
        result, signs, receipt_path = self._reduce()
        metadata, codes = unpack_sign_codes(signs)
        self.assertEqual(codes, self.expected_codes)
        self.assertEqual(metadata["character_count"], 2)
        self.assertEqual(
            metadata["sample_count"], base.transform_parameters(10_000).sample_count
        )
        self.assertEqual(
            result["ambiguous_samples_requiring_refinement"],
            self.expected_codes.count(AMBIGUOUS_CODE),
        )
        self.assertEqual(
            result["negative_samples"], self.expected_codes.count(NEGATIVE_CODE)
        )
        self.assertEqual(
            result["positive_samples"], self.expected_codes.count(POSITIVE_CODE)
        )
        self.assertTrue(
            result["all_sample_codes_retained_in_exact_character_major_order"]
        )
        self.assertFalse(result["multiplicity_inference_performed"])
        self.assertFalse(result["zero_completeness_claimed"])
        self.assertFalse(result["external_atom_discharged"])
        self.assertEqual(json.loads(receipt_path.read_text()), result)

    def test_scalar_and_numpy_emit_identical_exact_sign_artifact(self) -> None:
        scalar, scalar_path, _ = self._reduce(backend="scalar")
        try:
            vector, vector_path, _ = self._reduce(backend="numpy")
        except SmallQSemanticReducerError as error:
            if "unavailable" in str(error):
                self.skipTest(str(error))
            raise
        self.assertEqual(scalar_path.read_bytes(), vector_path.read_bytes())
        self.assertEqual(
            scalar["sign_artifact_sha256"], vector["sign_artifact_sha256"]
        )

    def test_reserved_code_and_nonzero_padding_fail_closed(self) -> None:
        _result, signs, _receipt = self._reduce()
        for label in ("reserved", "padding"):
            with self.subTest(label=label):
                raw = bytearray(signs.read_bytes())
                if label == "reserved":
                    raw[SIGN_HEADER.size] = (
                        raw[SIGN_HEADER.size] & 0xFC
                    ) | 0x03
                else:
                    raw[-1] |= 0xC0
                tampered = self.root / f"{label}.bin"
                tampered.write_bytes(raw)
                with self.assertRaisesRegex(
                    SmallQSemanticReducerError, "reserved|padding"
                ):
                    inspect_sign_artifact(tampered)

    def test_control_receipt_and_batch_parity_binding_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            (SmallQSemanticReducerError, RuntimeError),
            "coverage is incomplete|batch count is incomplete",
        ):
            reduce_semantic_sign_stream(
                self.plan,
                self.batches[:1],
                self.control,
                self.control_receipt,
                io.BytesIO(self.stream),
                self.root / "incomplete-roster.bin",
            )

        value = json.loads(self.control_receipt.read_text())
        value["character_parity_counts"] = [2, 0]
        tampered_receipt = self.root / "tampered-receipt.json"
        tampered_receipt.write_bytes(canonical_json_bytes(value))
        with self.assertRaisesRegex(
            SmallQSemanticReducerError, "self-hash differs"
        ):
            reduce_semantic_sign_stream(
                self.plan,
                self.batches,
                self.control,
                tampered_receipt,
                io.BytesIO(self.stream),
                self.root / "rejected.bin",
            )

        # Changing one character parity keeps the aggregate [1,1] counts but
        # changes the ordered batch-partition commitment.
        changed = bytearray(self.batches[0].read_bytes())
        changed_second = bytearray(self.batches[1].read_bytes())
        parity_offset = INPUT_HEADER.size + BATCH_BINDING.size + 8
        struct.pack_into("<I", changed, parity_offset, 1)
        struct.pack_into("<I", changed_second, parity_offset, 0)
        batch0 = self.root / "batch-00000000.bin"
        batch1 = self.root / "batch-00000001.bin"
        batch0.write_bytes(changed)
        batch1.write_bytes(changed_second)
        with self.assertRaisesRegex(
            SmallQSemanticReducerError, "parity roster"
        ):
            reduce_semantic_sign_stream(
                self.plan,
                [batch0, batch1],
                self.control,
                self.control_receipt,
                io.BytesIO(self.stream),
                self.root / "parity-rejected.bin",
            )

    def test_item_identity_status_and_trailing_bytes_fail_closed(self) -> None:
        first_item = v2.OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size
        cases = [
            (first_item + 8, "<Q", 1, "item identity"),
            (first_item + 40, "<I", 1, "item identity"),
            (first_item + 32, "<d", math.nan, "item identity"),
        ]
        for offset, kind, value, message in cases:
            with self.subTest(offset=offset):
                raw = bytearray(self.stream)
                struct.pack_into(kind, raw, offset, value)
                with self.assertRaisesRegex(SmallQSemanticReducerError, message):
                    self._reduce(stream=bytes(raw))
        with self.assertRaisesRegex(SmallQSemanticReducerError, "trailing bytes"):
            self._reduce(stream=self.stream + b"x")

    def test_cli_reduces_stdin_and_inspects_without_zero_claim(self) -> None:
        signs = self.root / "cli-signs.bin"
        receipt = self.root / "cli-receipt.json"
        with bounded_measured_worker_test_scope():
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        ROOT
                        / "tools/tg_dirichlet_booker_smallq_semantic_reducer.py"
                    ),
                    "reduce",
                    str(self.plan),
                    str(self.fixture_root),
                    str(self.control),
                    str(self.control_receipt),
                    str(signs),
                    str(receipt),
                    "--backend",
                    "numpy",
                ],
                input=self.stream,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        reduced = json.loads(completed.stdout)
        self.assertFalse(reduced["production_ready"])
        inspected = subprocess.run(
            [
                sys.executable,
                str(
                    ROOT
                    / "tools/tg_dirichlet_booker_smallq_semantic_reducer.py"
                ),
                "inspect-signs",
                str(signs),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        report = json.loads(inspected.stdout)
        self.assertFalse(report["multiplicity_inference_performed"])
        self.assertFalse(report["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
