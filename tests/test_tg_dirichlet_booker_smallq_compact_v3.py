# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from tests.azure_measured_worker_test_scope import (
    bounded_measured_worker_test_scope,
)

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_certified as v2
from tg_verifier import dirichlet_booker_smallq_compact_v3 as adapter
from tg_verifier import dirichlet_compact_state_streaming_v3 as compact
from tg_verifier.dirichlet_booker_smallq_compact_v3 import (
    PINSET_SCHEMA,
    SmallQCompactV3Error,
    SmallQCompactV3Pins,
    load_pinset,
    pinset_sha256,
    reduce_factored_service_stream_to_compact_v3,
)
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
from tg_verifier.dirichlet_booker_smallq_output_stream import (
    _preflight_batches,
)
from tg_verifier.dirichlet_booker_smallq_semantic_reducer import (
    CONTROL_ALGORITHM_ID,
    CONTROL_CHECKER_ID,
    CONTROL_FORMAT_VERSION,
    CONTROL_HEADER,
    CONTROL_ITEM,
    CONTROL_MAGIC,
    CONTROL_RECEIPT_SCHEMA,
    _batch_partition_digest,
    canonical_json_bytes,
)
from tg_verifier.dirichlet_root_number_stage import (
    primitive_frequency_records_bulk,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_fixture(
    root: Path,
) -> tuple[
    Path,
    tuple[Path, ...],
    Path,
    Path,
    bytes,
    SmallQCompactV3Pins,
    tuple[dict[str, int], ...],
]:
    """Write a full canonical q roster with a six-sample structural prefix."""

    q = 5_460
    parameters = base.transform_parameters(q)
    identities = primitive_frequency_records_bulk(q)
    conrey_numbers = tuple(
        int(identity["conrey_number"]) for identity in identities
    )
    group_exponent = 2

    plan_path = root / "plan.bin"
    plan_prefix = b"".join(
        (
            INPUT_HEADER.pack(
                PLAN_MAGIC,
                FORMAT_VERSION,
                q,
                group_exponent,
                len(identities),
                parameters.transform_length,
                0,
                parameters.transform_length,
                1,
                96,
                0,
            ),
            PLAN_COMMITMENT.pack(
                _character_roster_digest(conrey_numbers)
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
    shared_suffix = b"".join(
        (
            v2.DISK.pack(0.0, 0.0, 0.0),
            PARITY_SEED.pack(0, 0, 0.0, 0.0, 0.0, 0.0),
            PARITY_SEED.pack(0, 0, 0.0, 0.0, 0.0, 0.0),
        )
    )
    with plan_path.open("wb") as output:
        output.write(plan_prefix)
        plan_digest.update(plan_prefix)
        chunk = bytearray()
        for index in range(parameters.transform_length):
            signed = (
                index
                if index <= parameters.transform_length // 2
                else index - parameters.transform_length
            )
            chunk.extend(SHARED_PREFIX.pack(index, signed))
            chunk.extend(shared_suffix)
            if len(chunk) >= 8 * 1024 * 1024:
                output.write(chunk)
                plan_digest.update(chunk)
                chunk.clear()
        if chunk:
            output.write(chunk)
            plan_digest.update(chunk)
    plan_sha256 = plan_digest.digest()

    batch_path = root / "batch-00000000.bin"
    batch = bytearray(
        b"".join(
            (
                INPUT_HEADER.pack(
                    BATCH_MAGIC,
                    FORMAT_VERSION,
                    q,
                    group_exponent,
                    len(identities),
                    parameters.transform_length,
                    0,
                    parameters.transform_length,
                    1,
                    96,
                    0,
                ),
                BATCH_BINDING.pack(
                    plan_sha256,
                    0,
                    len(identities),
                    0,
                    1,
                ),
            )
        )
    )
    zero_exponents = bytes(4 * q)
    for identity in identities:
        batch.extend(
            CHARACTER_HEADER.pack(
                identity["conrey_number"],
                identity["parity"],
                0,
                0,
                1.0,
                0.0,
                0.0,
            )
        )
        batch.extend(zero_exponents)
    batch_path.write_bytes(batch)
    batch_sha256 = hashlib.sha256(batch).digest()

    plan, parsed_batches = _preflight_batches(plan_path, [batch_path])
    partition_sha256 = _batch_partition_digest(parsed_batches)
    parity_counts = [
        sum(identity["parity"] == parity for identity in identities)
        for parity in (0, 1)
    ]
    control_path = root / "control.bin"
    control_header = CONTROL_HEADER.pack(
        CONTROL_MAGIC,
        CONTROL_FORMAT_VERSION,
        q,
        parity_counts[0],
        parity_counts[1],
        parameters.transform_length,
        parameters.sample_count,
        192,
        0,
        plan.sha256,
        partition_sha256,
    )
    control_path.write_bytes(
        control_header
        + CONTROL_ITEM.pack(0.25, 2.0) * parameters.sample_count
    )
    control_sha256 = hashlib.sha256(control_path.read_bytes()).hexdigest()
    control_receipt = {
        "algorithm_id": CONTROL_ALGORITHM_ID,
        "all_even_and_odd_records_higher_precision_replayed": True,
        "all_source_ordinates_replayed": True,
        "atom_id": base.ATOM_ID,
        "author": "Gershon Bialer",
        "canonical_primitive_character_roster_replayed": True,
        "character_batch_partition_sha256": partition_sha256.hex(),
        "character_id_parity_mapping_replayed": True,
        "character_parity_counts": parity_counts,
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
        "transform_length": parameters.transform_length,
    }
    control_receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(control_receipt)
    ).hexdigest()
    control_receipt_path = root / "control-receipt.json"
    control_receipt_path.write_bytes(canonical_json_bytes(control_receipt))

    sample_reals = (1.0, -1.0, 0.35, 3.0, -3.0, 0.0)
    expected: list[dict[str, int]] = []
    raw_stream = bytearray(
        b"".join(
            (
                v2.OUTPUT_HEADER.pack(
                    REDUCED_SERVICE_OUTPUT_MAGIC,
                    FORMAT_VERSION,
                    q,
                    len(identities),
                    1,
                    0,
                    len(sample_reals),
                    0,
                    len(identities)
                    * (parameters.transform_length // 2)
                    * (parameters.transform_length.bit_length() - 1),
                    0,
                    0,
                    0,
                ),
                SERVICE_OUTPUT_BINDING.pack(
                    plan_sha256,
                    batch_sha256,
                    0,
                    len(identities),
                    0,
                    1,
                ),
            )
        )
    )
    for identity in identities:
        codes: list[int] = []
        threshold = 0.25 if identity["parity"] == 0 else 2.0
        boundary = threshold + 0.1
        for sample, real in enumerate(sample_reals):
            raw_stream.extend(
                v2.OUTPUT_ITEM.pack(
                    identity["conrey_number"],
                    sample,
                    real,
                    -0.125,
                    0.1,
                    0,
                    0,
                )
            )
            if real < -boundary:
                codes.append(1)
            elif real > boundary:
                codes.append(2)
            else:
                codes.append(0)
        determinate = [code for code in codes if code]
        expected.append(
            {
                "ambiguities": codes.count(0),
                "transitions": sum(
                    left != right
                    for left, right in zip(
                        determinate, determinate[1:]
                    )
                ),
            }
        )

    pins = SmallQCompactV3Pins(
        q=q,
        shared_plan_cache_sha256=plan.sha256.hex(),
        time_tail_control_sha256=control_sha256,
        time_tail_control_receipt_sha256=control_receipt[
            "receipt_sha256"
        ],
        character_batch_partition_sha256=partition_sha256.hex(),
        plan_character_roster_sha256=plan.character_roster_sha256.hex(),
        compact_complete_roster_sha256=(
            compact.complete_primitive_roster_sha256_v3(q)
        ),
        first_t_numerator=0,
        stop_t_numerator=len(sample_reals)
        * compact.SOURCE_SAMPLE_NUMERATOR,
        structural_bounded_span_kat=True,
    )
    return (
        plan_path,
        (batch_path,),
        control_path,
        control_receipt_path,
        bytes(raw_stream),
        pins,
        tuple(expected),
    )


class SmallQCompactV3Tests(unittest.TestCase):
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
            cls.pins,
            cls.expected,
        ) = _write_fixture(cls.fixture_root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_temporary.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _reduce(
        self,
        *,
        backend: str = "scalar",
        stream: bytes | None = None,
        pins: SmallQCompactV3Pins | None = None,
        plan: Path | None = None,
    ) -> tuple[dict[str, object], Path, Path]:
        state = self.root / f"state-{backend}.bin"
        receipt = self.root / f"receipt-{backend}.json"
        result = reduce_factored_service_stream_to_compact_v3(
            self.plan if plan is None else plan,
            self.batches,
            self.control,
            self.control_receipt,
            io.BytesIO(self.stream if stream is None else stream),
            state,
            pins=self.pins if pins is None else pins,
            receipt_path=receipt,
            chunk_items=37,
            backend=backend,
        )
        return result, state, receipt

    def test_typed_stream_fuses_directly_into_compact_state(self) -> None:
        result, state, receipt = self._reduce()
        replayed = compact.replay_compact_state_v3(
            state,
            expected_record=result["compact_state_artifact"],
        )
        states = list(compact.iter_compact_state_v3(state))
        self.assertEqual(len(states), len(self.expected))
        self.assertEqual(
            [row["ambiguity_count"] for row in states],
            [row["ambiguities"] for row in self.expected],
        )
        self.assertEqual(
            [row["internal_sign_change_count"] for row in states],
            [row["transitions"] for row in self.expected],
        )
        self.assertEqual(
            result["raw_disk_stream_sha256_receipt_only"],
            hashlib.sha256(self.stream).hexdigest(),
        )
        self.assertEqual(
            replayed["upstream_source_binding_sha256"],
            result["compact_source_binding_sha256"],
        )
        self.assertEqual(result["pinset_sha256"], pinset_sha256(self.pins))
        self.assertTrue(result["pinset_matches_exact_inputs"])
        self.assertFalse(result["pinset_authority_established_by_reducer"])
        self.assertTrue(result["strict_sign_codes_fed_directly_to_TGDCSB03"])
        self.assertFalse(result["raw_disk_stream_materialized"])
        self.assertFalse(result["packed_sign_artifact_materialized"])
        self.assertFalse(result["dft_arithmetic_containment_replayed"])
        self.assertFalse(result["raw_disk_stream_sha256_pinned_before_reduction"])
        self.assertTrue(
            result[
                "raw_disk_stream_integrity_requires_retained_receipt_state_pair"
            ]
        )
        self.assertTrue(
            result["character_exponent_tables_structurally_validated"]
        )
        self.assertTrue(
            result["shared_frequency_seed_records_structurally_validated"]
        )
        self.assertEqual(
            result["shared_frequency_seed_validation_chunk_records"],
            adapter.SHARED_SEED_VALIDATION_CHUNK_RECORDS,
        )
        self.assertFalse(
            result["character_exponent_tables_canonical_replayed"]
        )
        self.assertFalse(
            result[
                "shared_frequency_seed_values_higher_precision_replayed"
            ]
        )
        self.assertFalse(
            result["character_epsilon_disks_higher_precision_replayed"]
        )
        self.assertFalse(result["source_scale_storage_admitted"])
        self.assertFalse(
            result["physical_complete_roster_equivalence_realized"]
        )
        self.assertFalse(result["external_atom_discharged"])
        self.assertFalse(result["production_ready"])
        self.assertEqual(json.loads(receipt.read_text()), result)
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            ["receipt-scalar.json", "state-scalar.bin"],
        )

    def test_scalar_and_numpy_emit_identical_canonical_state(self) -> None:
        _scalar, scalar_path, _ = self._reduce(backend="scalar")
        try:
            _vector, vector_path, _ = self._reduce(backend="numpy")
        except SmallQCompactV3Error as error:
            if "unavailable" in str(error):
                self.skipTest(str(error))
            raise
        self.assertEqual(scalar_path.read_bytes(), vector_path.read_bytes())

    def test_nonzero_exact_prefix_uses_global_control_and_ordinates(self) -> None:
        sample_start = 2
        shifted = bytearray(self.stream)
        header = list(
            v2.OUTPUT_HEADER.unpack(shifted[: v2.OUTPUT_HEADER.size])
        )
        header[5] = sample_start
        shifted[: v2.OUTPUT_HEADER.size] = v2.OUTPUT_HEADER.pack(*header)
        offset = v2.OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size
        item_count = len(self.expected) * 6
        for item in range(item_count):
            struct.pack_into(
                "<Q",
                shifted,
                offset + item * v2.OUTPUT_ITEM.size + 8,
                sample_start + item % 6,
            )
        pins = replace(
            self.pins,
            first_t_numerator=(
                sample_start * compact.SOURCE_SAMPLE_NUMERATOR
            ),
            stop_t_numerator=(
                (sample_start + 6) * compact.SOURCE_SAMPLE_NUMERATOR
            ),
        )
        result, state, _receipt = self._reduce(
            stream=bytes(shifted), pins=pins
        )
        header = compact.inspect_compact_state_v3(state)
        self.assertEqual(
            header.first_t_numerator, pins.first_t_numerator
        )
        self.assertEqual(header.stop_t_numerator, pins.stop_t_numerator)
        first = next(compact.iter_compact_state_v3(state))
        self.assertGreaterEqual(
            first["first_determinate_numerator"],
            pins.first_t_numerator,
        )
        self.assertFalse(result["full_source_span"])

    def test_external_pin_and_production_span_fail_closed(self) -> None:
        for field in (
            "shared_plan_cache_sha256",
            "time_tail_control_sha256",
            "character_batch_partition_sha256",
            "plan_character_roster_sha256",
            "compact_complete_roster_sha256",
        ):
            with self.subTest(field=field):
                changed = replace(self.pins, **{field: "0" * 64})
                with self.assertRaisesRegex(
                    SmallQCompactV3Error, "external pinset"
                ):
                    self._reduce(pins=changed)
                self.assertFalse(
                    (self.root / "state-scalar.bin").exists()
                )

        production = replace(
            self.pins, structural_bounded_span_kat=False
        )
        with self.assertRaisesRegex(
            SmallQCompactV3Error, "full source span"
        ):
            self._reduce(pins=production)
        self.assertFalse((self.root / "state-scalar.bin").exists())

        off_grid = replace(
            self.pins,
            first_t_numerator=1,
            stop_t_numerator=self.pins.stop_t_numerator + 1,
        )
        with self.assertRaisesRegex(
            SmallQCompactV3Error, "exact small-q source grid"
        ):
            self._reduce(pins=off_grid)

    def test_canonical_pin_file_requires_out_of_band_digest(self) -> None:
        path = self.root / "pins.json"
        value = {
            "schema": PINSET_SCHEMA,
            "schema_version": 1,
            "pins": self.pins.record(),
            "pinset_sha256": pinset_sha256(self.pins),
        }
        path.write_bytes(canonical_json_bytes(value))
        self.assertEqual(
            load_pinset(
                path,
                expected_pinset_sha256=pinset_sha256(self.pins),
            ),
            self.pins,
        )
        with self.assertRaisesRegex(
            SmallQCompactV3Error, "external digest"
        ):
            load_pinset(path, expected_pinset_sha256="0" * 64)

    def test_cli_streams_stdin_without_raw_or_sign_artifact(self) -> None:
        pin_path = self.root / "pins.json"
        pin_value = {
            "schema": PINSET_SCHEMA,
            "schema_version": 1,
            "pins": self.pins.record(),
            "pinset_sha256": pinset_sha256(self.pins),
        }
        pin_path.write_bytes(canonical_json_bytes(pin_value))
        state = self.root / "cli-state.bin"
        receipt = self.root / "cli-receipt.json"
        with bounded_measured_worker_test_scope():
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        ROOT
                        / "tools/"
                        "tg_dirichlet_booker_smallq_semantic_reducer.py"
                    ),
                    "reduce-compact-v3",
                    str(self.plan),
                    str(self.fixture_root),
                    str(self.control),
                    str(self.control_receipt),
                    str(pin_path),
                    str(state),
                    str(receipt),
                    "--expected-pinset-sha256",
                    pinset_sha256(self.pins),
                    "--backend",
                    "scalar",
                    "--chunk-items",
                    "37",
                ],
                input=self.stream,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        report = json.loads(completed.stdout)
        self.assertTrue(state.is_file())
        self.assertTrue(receipt.is_file())
        self.assertFalse(report["raw_disk_stream_materialized"])
        self.assertFalse(report["packed_sign_artifact_materialized"])
        self.assertFalse(report["external_atom_discharged"])

    def test_item_header_truncation_and_trailing_bytes_fail_closed(self) -> None:
        first_item = v2.OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size
        changed_span = bytearray(self.stream)
        header_values = list(
            v2.OUTPUT_HEADER.unpack(
                changed_span[: v2.OUTPUT_HEADER.size]
            )
        )
        header_values[5] = 1
        changed_span[: v2.OUTPUT_HEADER.size] = v2.OUTPUT_HEADER.pack(
            *header_values
        )
        cases = (
            (
                self.stream[:first_item]
                + struct.pack("<Q", 1)
                + self.stream[first_item + 8 :],
                "item identity",
            ),
            (
                self.stream[: v2.OUTPUT_HEADER.size - 1],
                "truncated",
            ),
            (
                self.stream + b"x",
                "trailing bytes",
            ),
            (
                bytes(changed_span),
                "span",
            ),
        )
        for ordinal, (raw, message) in enumerate(cases):
            with self.subTest(ordinal=ordinal):
                with self.assertRaisesRegex(RuntimeError, message):
                    self._reduce(stream=raw)
                self.assertFalse(
                    (self.root / "state-scalar.bin").exists()
                )

    def test_raw_stream_variant_is_distinguished_only_by_receipt(self) -> None:
        changed = bytearray(self.stream)
        first_item = v2.OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size
        struct.pack_into("<d", changed, first_item + 3 * 8, -0.25)
        states: list[Path] = []
        results: list[dict[str, object]] = []
        for label, raw in (("original", self.stream), ("changed", bytes(changed))):
            directory = self.root / label
            directory.mkdir()
            state = directory / "state.bin"
            result = reduce_factored_service_stream_to_compact_v3(
                self.plan,
                self.batches,
                self.control,
                self.control_receipt,
                io.BytesIO(raw),
                state,
                pins=self.pins,
                chunk_items=37,
                backend="scalar",
            )
            states.append(state)
            results.append(result)
        self.assertEqual(states[0].read_bytes(), states[1].read_bytes())
        self.assertEqual(
            results[0]["compact_source_binding_sha256"],
            results[1]["compact_source_binding_sha256"],
        )
        self.assertNotEqual(
            results[0]["raw_disk_stream_sha256_receipt_only"],
            results[1]["raw_disk_stream_sha256_receipt_only"],
        )
        self.assertFalse(
            results[0]["compact_source_binding_includes_raw_disk_stream_sha256"]
        )
        self.assertTrue(
            results[0][
                "raw_disk_stream_integrity_requires_retained_receipt_state_pair"
            ]
        )

    def test_bound_input_mutation_before_publish_fails_closed(self) -> None:
        copied_plan = self.root / "copied-plan.bin"
        shutil.copyfile(self.plan, copied_plan)

        class MutatingStream(io.BytesIO):
            changed = False

            def read(self, size: int = -1) -> bytes:
                raw = super().read(size)
                if not self.changed:
                    self.changed = True
                    with copied_plan.open("r+b") as target:
                        target.seek(-1, 2)
                        value = target.read(1)
                        target.seek(-1, 2)
                        target.write(bytes((value[0] ^ 1,)))
                return raw

        state = self.root / "mutating-state.bin"
        with self.assertRaisesRegex(
            SmallQCompactV3Error, "bound input changed"
        ):
            reduce_factored_service_stream_to_compact_v3(
                copied_plan,
                self.batches,
                self.control,
                self.control_receipt,
                MutatingStream(self.stream),
                state,
                pins=self.pins,
                chunk_items=37,
                backend="scalar",
            )
        self.assertFalse(state.exists())

    def test_bound_input_mutation_after_final_hash_fails_closed(self) -> None:
        copied_plan = self.root / "post-hash-plan.bin"
        shutil.copyfile(self.plan, copied_plan)
        original_sha256_file = adapter.semantic._sha256_file
        plan_hashes = 0

        def mutate_after_final_hash(path: Path) -> tuple[str, int]:
            nonlocal plan_hashes
            result = original_sha256_file(path)
            if Path(path) == copied_plan:
                plan_hashes += 1
                if plan_hashes == 2:
                    with copied_plan.open("r+b") as target:
                        target.seek(-1, 2)
                        value = target.read(1)
                        target.seek(-1, 2)
                        target.write(bytes((value[0] ^ 1,)))
            return result

        state = self.root / "post-hash-state.bin"
        with mock.patch.object(
            adapter.semantic,
            "_sha256_file",
            side_effect=mutate_after_final_hash,
        ):
            with self.assertRaisesRegex(
                SmallQCompactV3Error, "bound input changed"
            ):
                reduce_factored_service_stream_to_compact_v3(
                    copied_plan,
                    self.batches,
                    self.control,
                    self.control_receipt,
                    io.BytesIO(self.stream),
                    state,
                    pins=self.pins,
                    chunk_items=37,
                    backend="scalar",
                )
        self.assertEqual(plan_hashes, 2)
        self.assertFalse(state.exists())

    def test_control_descriptor_substitution_fails_closed(self) -> None:
        substituted = self.root / "substituted-control.bin"
        raw = bytearray(self.control.read_bytes())
        first_control = adapter.semantic.CONTROL_HEADER.size
        struct.pack_into("<dd", raw, first_control, 99.0, 99.0)
        substituted.write_bytes(raw)

        original_open = Path.open
        control_opens = 0

        def substitute_fifth_control_open(
            path: Path, *args: object, **kwargs: object
        ) -> object:
            nonlocal control_opens
            if Path(path) == self.control:
                control_opens += 1
                if control_opens == 5:
                    return original_open(substituted, *args, **kwargs)
            return original_open(path, *args, **kwargs)

        state = self.root / "substituted-control-state.bin"
        with mock.patch.object(
            Path, "open", autospec=True, side_effect=substitute_fifth_control_open
        ):
            with self.assertRaisesRegex(
                SmallQCompactV3Error, "descriptor differs"
            ):
                reduce_factored_service_stream_to_compact_v3(
                    self.plan,
                    self.batches,
                    self.control,
                    self.control_receipt,
                    io.BytesIO(self.stream),
                    state,
                    pins=self.pins,
                    chunk_items=37,
                    backend="scalar",
                )
        self.assertEqual(control_opens, 5)
        self.assertFalse(state.exists())

    def test_chunk_resource_bound_fails_before_output(self) -> None:
        state = self.root / "oversized-chunk-state.bin"
        with self.assertRaisesRegex(
            SmallQCompactV3Error, "no larger"
        ):
            reduce_factored_service_stream_to_compact_v3(
                self.plan,
                self.batches,
                self.control,
                self.control_receipt,
                io.BytesIO(self.stream),
                state,
                pins=self.pins,
                chunk_items=adapter.MAXIMUM_CHUNK_ITEMS + 1,
                backend="scalar",
            )
        self.assertFalse(state.exists())

    def test_dangling_output_symlink_fails_before_streaming(self) -> None:
        target = self.root / "unexpected-target.bin"
        state = self.root / "state-link.bin"
        state.symlink_to(target)
        with self.assertRaisesRegex(
            SmallQCompactV3Error, "immutable compact v3 output"
        ):
            reduce_factored_service_stream_to_compact_v3(
                self.plan,
                self.batches,
                self.control,
                self.control_receipt,
                io.BytesIO(self.stream),
                state,
                pins=self.pins,
                chunk_items=37,
                backend="scalar",
            )
        self.assertTrue(state.is_symlink())
        self.assertFalse(target.exists())

    def test_streamed_batch_exponent_validation_fails_closed(self) -> None:
        changed_batch = self.root / "batch-00000000.bin"
        shutil.copyfile(self.batches[0], changed_batch)
        exponent_offset = (
            INPUT_HEADER.size
            + BATCH_BINDING.size
            + CHARACTER_HEADER.size
        )
        with changed_batch.open("r+b") as output:
            output.seek(exponent_offset)
            output.write(struct.pack("<I", 2))
        state = self.root / "invalid-exponent-state.bin"
        with self.assertRaisesRegex(
            SmallQCompactV3Error, "outside the group exponent"
        ):
            reduce_factored_service_stream_to_compact_v3(
                self.plan,
                [changed_batch],
                self.control,
                self.control_receipt,
                io.BytesIO(self.stream),
                state,
                pins=self.pins,
                backend="scalar",
            )
        self.assertFalse(state.exists())

    def test_wrong_character_roster_fails_before_streaming(self) -> None:
        changed_batch = self.root / "wrong-roster-batch.bin"
        shutil.copyfile(self.batches[0], changed_batch)
        character_offset = INPUT_HEADER.size + BATCH_BINDING.size
        with changed_batch.open("r+b") as output:
            output.seek(character_offset)
            (character_id,) = struct.unpack("<Q", output.read(8))
            output.seek(character_offset)
            output.write(struct.pack("<Q", character_id + 1))
        state = self.root / "wrong-roster-state.bin"
        with self.assertRaisesRegex(
            SmallQCompactV3Error, "coverage or roster differs"
        ):
            reduce_factored_service_stream_to_compact_v3(
                self.plan,
                [changed_batch],
                self.control,
                self.control_receipt,
                io.BytesIO(self.stream),
                state,
                pins=self.pins,
                backend="scalar",
            )
        self.assertFalse(state.exists())

    def test_streamed_shared_seed_structure_fails_closed(self) -> None:
        changed_plan = self.root / "invalid-shared-plan.bin"
        shutil.copyfile(self.plan, changed_plan)
        prefix_size = (
            INPUT_HEADER.size
            + PLAN_COMMITMENT.size
            + PARAMETER_HEADER.size
        )
        radius_offset = prefix_size + SHARED_PREFIX.size + 2 * 8
        with changed_plan.open("r+b") as output:
            output.seek(radius_offset)
            output.write(struct.pack("<d", -1.0))
        state = self.root / "invalid-shared-state.bin"
        with self.assertRaisesRegex(
            RuntimeError, "shared frequency identity or disk"
        ):
            reduce_factored_service_stream_to_compact_v3(
                changed_plan,
                self.batches,
                self.control,
                self.control_receipt,
                io.BytesIO(self.stream),
                state,
                pins=self.pins,
                backend="scalar",
            )
        self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
