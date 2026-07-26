# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tests.test_tg_dirichlet_booker_smallq_semantic_reducer import (
    _write_source_fixture,
)
from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier.dirichlet_booker_smallq_semantic_reducer import (
    AMBIGUOUS_CODE,
    NEGATIVE_CODE,
    POSITIVE_CODE,
    SIGN_HEADER,
    canonical_json_bytes,
    reduce_semantic_sign_stream,
    unpack_sign_codes,
)
from tg_verifier.dirichlet_booker_smallq_sign_scan import (
    AMBIGUITY_RANGE_EVENT,
    ARTIFACT_HEADER,
    CHARACTER_HEADER,
    EVENT_RECORD,
    OPPOSITE_SIGN_INTERVAL_EVENT,
    SmallQSignScanError,
    _BufferedEventWriter,
    _CharacterScan,
    _emit_ambiguity,
    _scan_numpy_chunk,
    _scan_scalar_chunk,
    inspect_sign_scan,
    materialize_sign_scan,
    verify_sign_scan,
)


class SmallQSignScanTests(unittest.TestCase):
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
            _expected_codes,
        ) = _write_source_fixture(cls.fixture_root)
        cls.source_signs = cls.fixture_root / "source-signs.bin"
        cls.source_reducer_receipt = cls.fixture_root / "source-reducer.json"
        reduce_semantic_sign_stream(
            cls.plan,
            cls.batches,
            cls.control,
            cls.control_receipt,
            io.BytesIO(cls.stream),
            cls.source_signs,
            receipt_path=cls.source_reducer_receipt,
            chunk_items=10_003,
            backend="scalar",
        )
        cls.sample_count = base.transform_parameters(10_000).sample_count

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_temporary.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @contextmanager
    def _canonical_two_character_roster(self):
        descriptors = (
            {"conrey_number": 1877, "parity": 0},
            {"conrey_number": 1879, "parity": 1},
        )

        def descriptor(q: int, ordinal: int):
            if q != 10_000 or not 0 <= ordinal < len(descriptors):
                raise RuntimeError("unexpected synthetic roster coordinate")
            return descriptors[ordinal]

        with (
            patch.object(base, "primitive_character_count", return_value=2),
            patch.object(
                base, "primitive_character_descriptor", side_effect=descriptor
            ),
        ):
            yield

    def _pattern_signs(self) -> tuple[Path, Path, bytes]:
        metadata, original = unpack_sign_codes(self.source_signs)
        self.assertEqual(len(original), 2 * self.sample_count)
        first = bytearray([POSITIVE_CODE] * self.sample_count)
        first[:7] = bytes(
            (
                POSITIVE_CODE,
                AMBIGUOUS_CODE,
                AMBIGUOUS_CODE,
                NEGATIVE_CODE,
                NEGATIVE_CODE,
                AMBIGUOUS_CODE,
                POSITIVE_CODE,
            )
        )
        second = bytearray([AMBIGUOUS_CODE] * self.sample_count)
        codes = bytes(first + second)
        payload = bytearray((len(codes) + 3) // 4)
        for index, code in enumerate(codes):
            payload[index // 4] |= code << (2 * (index % 4))
        source_raw = self.source_signs.read_bytes()
        signs = self.root / "pattern-signs.bin"
        signs.write_bytes(source_raw[: SIGN_HEADER.size] + payload)
        self.assertEqual(metadata["code_count"], len(codes))

        receipt = json.loads(self.source_reducer_receipt.read_text())
        receipt["ambiguous_samples_requiring_refinement"] = codes.count(
            AMBIGUOUS_CODE
        )
        receipt["negative_samples"] = codes.count(NEGATIVE_CODE)
        receipt["positive_samples"] = codes.count(POSITIVE_CODE)
        receipt["all_samples_strictly_signed"] = (
            receipt["ambiguous_samples_requiring_refinement"] == 0
        )
        receipt["sign_artifact_bytes"] = signs.stat().st_size
        receipt["sign_artifact_sha256"] = hashlib.sha256(
            signs.read_bytes()
        ).hexdigest()
        receipt.pop("receipt_sha256")
        receipt["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(receipt)
        ).hexdigest()
        receipt_path = self.root / "pattern-reducer.json"
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        return signs, receipt_path, codes

    def _materialize(
        self,
        signs: Path,
        reducer_receipt: Path,
        *,
        label: str,
        backend: str,
        chunk_codes: int,
    ) -> tuple[dict[str, object], Path, Path]:
        artifact = self.root / f"{label}.bin"
        receipt = self.root / f"{label}.json"
        with self._canonical_two_character_roster():
            result = materialize_sign_scan(
                self.plan,
                self.batches,
                signs,
                reducer_receipt,
                artifact,
                receipt_path=receipt,
                backend=backend,
                chunk_codes=chunk_codes,
            )
        return result, artifact, receipt

    def test_materialize_and_independently_replay_exact_events(self) -> None:
        signs, reducer_receipt, _codes = self._pattern_signs()
        producer, artifact, producer_receipt = self._materialize(
            signs,
            reducer_receipt,
            label="events",
            backend="numpy",
            chunk_codes=3,
        )
        checker_receipt = self.root / "checker.json"
        with self._canonical_two_character_roster():
            checker = verify_sign_scan(
                self.plan,
                self.batches,
                signs,
                reducer_receipt,
                artifact,
                producer_receipt,
                receipt_path=checker_receipt,
                backend="scalar",
                chunk_codes=5,
            )
        self.assertTrue(checker["passed"])
        self.assertTrue(checker["all_event_records_replayed"])
        self.assertFalse(checker["continuity_theorem_applied"])
        self.assertFalse(checker["exact_zero_multiplicity_inferred"])
        self.assertFalse(checker["external_atom_discharged"])
        self.assertFalse(checker["source_scale_measured"])
        self.assertFalse(producer["production_ready"])
        self.assertFalse(producer["source_scale_measured"])
        self.assertTrue(producer["event_storage_can_exceed_packed_sign_input"])
        self.assertEqual(producer["ambiguity_range_count"], 3)
        self.assertEqual(producer["opposite_sign_interval_count"], 2)
        self.assertEqual(producer["event_count"], 5)
        self.assertEqual(
            producer["ambiguous_sample_count"], self.sample_count + 3
        )
        self.assertEqual(producer["negative_sample_count"], 2)
        self.assertEqual(
            producer["positive_sample_count"], self.sample_count - 5
        )
        self.assertEqual(json.loads(checker_receipt.read_text()), checker)

        with artifact.open("rb") as source:
            source.read(ARTIFACT_HEADER.size)
            first_header = CHARACTER_HEADER.unpack(
                source.read(CHARACTER_HEADER.size)
            )
            self.assertEqual(first_header[0:3], (0, 1877, 0))
            self.assertEqual(first_header[-3:], (2, 2, 4))
            events = [
                EVENT_RECORD.unpack(source.read(EVENT_RECORD.size))
                for _ in range(4)
            ]
        self.assertEqual(
            events,
            [
                (AMBIGUITY_RANGE_EVENT, 0, 1, 2),
                (
                    OPPOSITE_SIGN_INTERVAL_EVENT,
                    POSITIVE_CODE | (NEGATIVE_CODE << 2),
                    0,
                    3,
                ),
                (AMBIGUITY_RANGE_EVENT, 0, 5, 5),
                (
                    OPPOSITE_SIGN_INTERVAL_EVENT,
                    NEGATIVE_CODE | (POSITIVE_CODE << 2),
                    4,
                    6,
                ),
            ],
        )

        inspection = inspect_sign_scan(artifact)
        self.assertEqual(inspection["event_count"], 5)
        self.assertTrue(inspection["structural_only_not_source_sign_replay"])

    def test_scalar_numpy_and_chunk_boundaries_are_byte_deterministic(self) -> None:
        signs, reducer_receipt, _codes = self._pattern_signs()
        _scalar, scalar_artifact, _scalar_receipt = self._materialize(
            signs,
            reducer_receipt,
            label="scalar",
            backend="scalar",
            chunk_codes=7,
        )
        try:
            _numpy, numpy_artifact, numpy_receipt = self._materialize(
                signs,
                reducer_receipt,
                label="numpy",
                backend="numpy",
                chunk_codes=11,
            )
        except SmallQSignScanError as error:
            if "unavailable" in str(error):
                self.skipTest(str(error))
            raise
        self.assertEqual(scalar_artifact.read_bytes(), numpy_artifact.read_bytes())
        with self._canonical_two_character_roster():
            verified = verify_sign_scan(
                self.plan,
                self.batches,
                signs,
                reducer_receipt,
                numpy_artifact,
                numpy_receipt,
                backend="numpy",
                chunk_codes=13,
            )
        self.assertTrue(verified["passed"])

    def test_vector_encoder_matches_scalar_on_adversarial_patterns(self) -> None:
        def encoded(
            codes: bytes, *, backend: str, chunk_codes: int
        ) -> tuple[_CharacterScan, bytes]:
            state = _CharacterScan()
            output = io.BytesIO()
            writer = _BufferedEventWriter(output)
            for start in range(0, len(codes), chunk_codes):
                chunk = codes[start : start + chunk_codes]
                if backend == "numpy":
                    _scan_numpy_chunk(
                        state,
                        np.frombuffer(chunk, dtype=np.uint8),
                        sample_start=start,
                        emit=writer.emit,
                        emit_packed=writer.emit_packed,
                    )
                else:
                    _scan_scalar_chunk(
                        state,
                        chunk,
                        sample_start=start,
                        emit=writer.emit,
                    )
            if state.ambiguous_start is not None:
                _emit_ambiguity(
                    state,
                    writer.emit,
                    state.ambiguous_start,
                    len(codes) - 1,
                )
                state.ambiguous_start = None
            writer.flush()
            return state, output.getvalue()

        patterns = [
            bytes([code] * 65)
            for code in (AMBIGUOUS_CODE, NEGATIVE_CODE, POSITIVE_CODE)
        ]
        patterns.extend(
            (
                bytes(
                    NEGATIVE_CODE if index % 2 else POSITIVE_CODE
                    for index in range(129)
                ),
                bytes(
                    AMBIGUOUS_CODE if index % 2 else POSITIVE_CODE
                    for index in range(129)
                ),
                bytes(
                    (
                        POSITIVE_CODE,
                        AMBIGUOUS_CODE,
                        NEGATIVE_CODE,
                        AMBIGUOUS_CODE,
                    )[index % 4]
                    for index in range(129)
                ),
            )
        )
        generator = random.Random(0x54474442535A5231)
        for length in (1, 2, 3, 4, 7, 8, 9, 31, 32, 33, 257, 1025):
            for _ in range(8):
                patterns.append(
                    bytes(generator.randrange(3) for _ in range(length))
                )

        for pattern in patterns:
            scalar_state, scalar_bytes = encoded(
                pattern, backend="scalar", chunk_codes=len(pattern)
            )
            for chunk_codes in (1, 2, 3, 7, 64, 257):
                with self.subTest(
                    length=len(pattern), chunk_codes=chunk_codes
                ):
                    vector_state, vector_bytes = encoded(
                        pattern,
                        backend="numpy",
                        chunk_codes=chunk_codes,
                    )
                    self.assertEqual(vector_state, scalar_state)
                    self.assertEqual(vector_bytes, scalar_bytes)

    def test_tampered_event_truncation_and_receipt_fail_closed(self) -> None:
        signs, reducer_receipt, _codes = self._pattern_signs()
        _producer, artifact, producer_receipt = self._materialize(
            signs,
            reducer_receipt,
            label="source",
            backend="scalar",
            chunk_codes=17,
        )

        raw = bytearray(artifact.read_bytes())
        event_offset = ARTIFACT_HEADER.size + CHARACTER_HEADER.size
        raw[event_offset + 8] ^= 1
        tampered_artifact = self.root / "tampered-artifact.bin"
        tampered_artifact.write_bytes(raw)
        with self._canonical_two_character_roster():
            with self.assertRaisesRegex(
                SmallQSignScanError, "event replay differs"
            ):
                verify_sign_scan(
                    self.plan,
                    self.batches,
                    signs,
                    reducer_receipt,
                    tampered_artifact,
                    producer_receipt,
                    backend="scalar",
                    chunk_codes=19,
                )

        truncated = self.root / "truncated-artifact.bin"
        truncated.write_bytes(artifact.read_bytes()[:-1])
        with self._canonical_two_character_roster():
            with self.assertRaisesRegex(SmallQSignScanError, "truncated"):
                verify_sign_scan(
                    self.plan,
                    self.batches,
                    signs,
                    reducer_receipt,
                    truncated,
                    producer_receipt,
                    backend="scalar",
                )

        receipt_value = json.loads(producer_receipt.read_text())
        receipt_value["event_count"] += 1
        bad_receipt = self.root / "bad-producer.json"
        bad_receipt.write_bytes(canonical_json_bytes(receipt_value))
        with self._canonical_two_character_roster():
            with self.assertRaisesRegex(
                SmallQSignScanError, "self-hash differs"
            ):
                verify_sign_scan(
                    self.plan,
                    self.batches,
                    signs,
                    reducer_receipt,
                    artifact,
                    bad_receipt,
                    backend="scalar",
                )

    def test_noncanonical_padding_fails_closed(self) -> None:
        signs, reducer_receipt, _codes = self._pattern_signs()
        _producer, artifact, producer_receipt = self._materialize(
            signs,
            reducer_receipt,
            label="canonical-padding",
            backend="scalar",
            chunk_codes=17,
        )

        character_raw = bytearray(artifact.read_bytes())
        character_raw[ARTIFACT_HEADER.size + 9] = 1
        character_padding = self.root / "character-padding.bin"
        character_padding.write_bytes(character_raw)
        producer_value = json.loads(producer_receipt.read_text())
        producer_value["artifact_sha256"] = hashlib.sha256(
            character_raw
        ).hexdigest()
        producer_value.pop("receipt_sha256")
        producer_value["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(producer_value)
        ).hexdigest()
        character_receipt = self.root / "character-padding.json"
        character_receipt.write_bytes(canonical_json_bytes(producer_value))
        with self._canonical_two_character_roster():
            with self.assertRaisesRegex(SmallQSignScanError, "padding"):
                verify_sign_scan(
                    self.plan,
                    self.batches,
                    signs,
                    reducer_receipt,
                    character_padding,
                    character_receipt,
                    backend="scalar",
                )
        with self.assertRaisesRegex(SmallQSignScanError, "padding"):
            inspect_sign_scan(character_padding)

        event_raw = bytearray(artifact.read_bytes())
        event_offset = ARTIFACT_HEADER.size + CHARACTER_HEADER.size
        event_raw[event_offset + 2] = 1
        event_padding = self.root / "event-padding.bin"
        event_padding.write_bytes(event_raw)
        with self.assertRaisesRegex(SmallQSignScanError, "padding"):
            inspect_sign_scan(event_padding)

    def test_output_aliases_fail_before_replacing_inputs(self) -> None:
        signs, reducer_receipt, _codes = self._pattern_signs()
        signs_before = signs.read_bytes()
        with self._canonical_two_character_roster():
            with self.assertRaisesRegex(SmallQSignScanError, "must not alias"):
                materialize_sign_scan(
                    self.plan,
                    self.batches,
                    signs,
                    reducer_receipt,
                    signs,
                    backend="scalar",
                )
        self.assertEqual(signs.read_bytes(), signs_before)

        artifact = self.root / "alias-artifact.bin"
        with self._canonical_two_character_roster():
            with self.assertRaisesRegex(SmallQSignScanError, "must not alias"):
                materialize_sign_scan(
                    self.plan,
                    self.batches,
                    signs,
                    reducer_receipt,
                    artifact,
                    receipt_path=artifact,
                    backend="scalar",
                )
        self.assertFalse(artifact.exists())

        _producer, artifact, producer_receipt = self._materialize(
            signs,
            reducer_receipt,
            label="verify-alias",
            backend="scalar",
            chunk_codes=17,
        )
        artifact_before = artifact.read_bytes()
        with self._canonical_two_character_roster():
            with self.assertRaisesRegex(SmallQSignScanError, "must not alias"):
                verify_sign_scan(
                    self.plan,
                    self.batches,
                    signs,
                    reducer_receipt,
                    artifact,
                    producer_receipt,
                    receipt_path=artifact,
                    backend="scalar",
                )
        self.assertEqual(artifact.read_bytes(), artifact_before)

    def test_reserved_code_padding_and_source_digest_fail_closed(self) -> None:
        signs, reducer_receipt, _codes = self._pattern_signs()
        for label in ("reserved", "padding"):
            with self.subTest(label=label):
                raw = bytearray(signs.read_bytes())
                if label == "reserved":
                    raw[SIGN_HEADER.size] = (
                        raw[SIGN_HEADER.size] & 0xFC
                    ) | 0x03
                    pattern = "reserved"
                else:
                    raw[-1] |= 0xC0
                    pattern = "padding"
                tampered = self.root / f"{label}-signs.bin"
                tampered.write_bytes(raw)
                with self._canonical_two_character_roster():
                    with self.assertRaisesRegex(SmallQSignScanError, pattern):
                        materialize_sign_scan(
                            self.plan,
                            self.batches,
                            tampered,
                            reducer_receipt,
                            self.root / f"{label}-events.bin",
                            backend="scalar",
                            chunk_codes=23,
                        )

        receipt_value = json.loads(reducer_receipt.read_text())
        receipt_value["sign_artifact_sha256"] = "0" * 64
        receipt_value.pop("receipt_sha256")
        receipt_value["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(receipt_value)
        ).hexdigest()
        wrong_digest_receipt = self.root / "wrong-digest-reducer.json"
        wrong_digest_receipt.write_bytes(canonical_json_bytes(receipt_value))
        with self._canonical_two_character_roster():
            with self.assertRaisesRegex(
                SmallQSignScanError, "digest differs"
            ):
                materialize_sign_scan(
                    self.plan,
                    self.batches,
                    signs,
                    wrong_digest_receipt,
                    self.root / "wrong-digest-events.bin",
                    backend="scalar",
                    chunk_codes=29,
                )

    def test_cli_help_and_inspect(self) -> None:
        # Argument construction is exercised without requiring the synthetic
        # roster patch to cross a subprocess boundary.
        from tools.tg_dirichlet_booker_smallq_sign_scan import parser

        parsed = parser().parse_args(["inspect", "artifact.bin"])
        self.assertEqual(parsed.command, "inspect")
        self.assertEqual(parsed.scan_artifact, Path("artifact.bin"))

    def test_local_file_benchmark_writes_and_hashes_canonical_events(self) -> None:
        from tools.benchmark_tg_dirichlet_booker_smallq_sign_scan import (
            benchmark,
            parser,
        )

        output = self.root / "benchmark-events.bin"
        parsed = parser().parse_args(
            [
                str(output),
                "--codes",
                "10000",
                "--chunk-codes",
                "257",
                "--ambiguity-probability",
                "0.01",
            ]
        )
        self.assertEqual(parsed.output, output)
        result = benchmark(
            output,
            codes=10_000,
            chunk_codes=257,
            transition_probability=0.2,
            ambiguity_probability=0.01,
            seed=12345,
            overwrite=False,
            remove_output=False,
        )
        raw = output.read_bytes()
        self.assertEqual(
            len(raw), result["event_count"] * EVENT_RECORD.size
        )
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(), result["output_sha256"]
        )
        self.assertTrue(
            result["projection_is_not_parallel_io_or_cloud_calibration"]
        )
        with self.assertRaisesRegex(RuntimeError, "output exists"):
            benchmark(
                output,
                codes=10,
                chunk_codes=10,
                transition_probability=0.2,
                ambiguity_probability=0.0,
                seed=1,
                overwrite=False,
                remove_output=False,
            )


if __name__ == "__main__":
    unittest.main()
