# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from tg_verifier.dirichlet_fft_pipeline_bundle import (
    EVENT_FILE_SCHEMA,
)
from tg_verifier.dirichlet_compact_state_binary import (
    AMBIGUITY_RANGE_RECORD,
    ARTIFACT_HEADER,
    BRACKET_RECORD,
    CHARACTER_RECORD,
    DirichletCompactStateBinaryError,
    read_compact_state_binary,
    write_compact_state_binary,
)
from tg_verifier.dirichlet_compact_state_finalizer import (
    DirichletCompactStateFinalizerError,
    finalize_compact_state_lanes,
)
from tg_verifier.dirichlet_lattice_cache import canonical_json_bytes
from tg_verifier.dirichlet_tblock_storage import (
    ContentAddressedChunkStore,
    DirichletTBlockStorageError,
    admit_event_stream,
    compact_state_storage_model,
    inventory_campaign,
    project_source_scale,
    require_source_scale_storage_ready,
    storage_boundary,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    COMPACT_EVENT_STORAGE_MODE,
    DirichletStreamConsumerError,
    MAX_EVENT_COUNT,
    _CharacterChunkState,
    _EventWriter,
    combine_character_chunk_states,
    combine_compact_state_summaries,
    compact_state_from_event_summary,
    validate_compact_event_summary,
    validate_compact_state_summary,
)
from tg_verifier.dirichlet_root_number_stage import (
    primitive_frequency_records_bulk,
)
from tg_verifier.dirichlet_tblock_bundle_supervisor import (
    ALGORITHM_ID as TBLOCK_ALGORITHM_ID,
    ATOM_ID as TBLOCK_ATOM_ID,
    AUTHOR as TBLOCK_AUTHOR,
    NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION,
    RECEIPT_CLASSIFICATION as TBLOCK_RECEIPT_CLASSIFICATION,
    RECEIPT_SCHEMA as TBLOCK_RECEIPT_SCHEMA,
)


class DirichletTBlockStorageTest(unittest.TestCase):
    def test_content_addressed_chunks_are_reused_and_hard_linked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ContentAddressedChunkStore(root / "cas")
            first = store.put_stream(BytesIO(b"one authenticated row"))
            second = store.put_stream(BytesIO(b"one authenticated row"))
            self.assertFalse(first.reused)
            self.assertTrue(second.reused)
            self.assertEqual(first.path, second.path)
            reference = store.link_reference(
                first.sha256,
                root / "references" / "row-000001.bin",
                expected_size=first.size_bytes,
            )
            self.assertEqual(reference.read_bytes(), b"one authenticated row")
            self.assertEqual(first.path.stat().st_ino, reference.stat().st_ino)

    def test_event_admission_is_streaming_but_not_deletion_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.ndjson"
            raw = canonical_json_bytes(
                {
                    "classification": (
                        "multiplicity-lower-bound-events-not-zero-completeness"
                    ),
                    "kind": EVENT_FILE_SCHEMA,
                    "schema_version": 1,
                }
            )
            path.write_bytes(raw)
            receipt = admit_event_stream(
                path,
                expected_sha256=hashlib.sha256(raw).hexdigest(),
                expected_size=len(raw),
                q=10_001,
                primitive_characters=1,
                frame_count=1,
                first_t_numerator=0,
                stop_t_numerator=5,
                maximum_bytes=1024,
            )
            self.assertTrue(receipt["bounded_memory_streaming_validation"])
            self.assertTrue(
                receipt["raw_event_artifact_still_required_for_resume"]
            )
            self.assertFalse(receipt["authorizes_raw_event_deletion"])

    def test_event_writer_fails_before_crossing_retained_byte_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.ndjson"
            writer = _EventWriter(path, maximum_bytes=256)
            with self.assertRaisesRegex(
                DirichletStreamConsumerError,
                "retained-byte budget",
            ):
                writer.event({"payload": "x" * 1024})
            writer.abort()
            self.assertFalse(path.exists())
            self.assertFalse(path.with_name("events.ndjson.tmp").exists())

    @staticmethod
    def _compact_fixture(
        root: Path,
        *,
        event_order: tuple[int, ...] = (0, 1, 2),
        substitute: bool = False,
    ) -> dict[str, object]:
        identities = primitive_frequency_records_bulk(5)
        states = [
            _CharacterChunkState(
                conrey_number=row["conrey_number"],
                primitive_ordinal=row["primitive_ordinal"],
                parity=row["parity"],
            )
            for row in identities
        ]
        states[0].observe(0, 1)
        states[0].observe(5, -1)
        states[1].observe(0, 1)
        states[1].observe(5, 1)
        states[2].observe(0, 0)
        states[2].observe(5, 0)
        events = (
            {"event": "sign_change_candidate", "marker": "a"},
            {
                "event": "indeterminate_completed_value",
                "marker": "substituted" if substitute else "b",
            },
            {"event": "indeterminate_completed_value", "marker": "c"},
        )
        path = root / (
            "summary-"
            + "".join(map(str, event_order))
            + ("-substituted" if substitute else "")
            + ".json"
        )
        writer = _EventWriter(
            path,
            storage_mode=COMPACT_EVENT_STORAGE_MODE,
            maximum_bytes=1024 * 1024,
        )
        for index in event_order:
            writer.event(events[index])
        writer.publish(
            compact_context={
                "q": 5,
                "primitive_character_count": 3,
                "frame_count": 1,
                "first_t_numerator": 0,
                "stop_t_numerator": 10,
                "t_denominator": 64,
                "t_step_numerator": 5,
            },
            character_states=[state.record() for state in states],
        )
        return json.loads(path.read_bytes())

    def test_compact_summary_binds_order_substitution_and_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ordered = self._compact_fixture(root)
            reversed_events = self._compact_fixture(
                root, event_order=(2, 1, 0)
            )
            substituted = self._compact_fixture(root, substitute=True)
            self.assertNotEqual(
                ordered["ordered_mmr_root_sha256"],
                reversed_events["ordered_mmr_root_sha256"],
            )
            self.assertNotEqual(
                ordered["ordered_mmr_root_sha256"],
                substituted["ordered_mmr_root_sha256"],
            )
            self.assertNotEqual(
                ordered["associative_polynomial_commitment"]["value_hex"],
                reversed_events["associative_polynomial_commitment"][
                    "value_hex"
                ],
            )
            self.assertEqual(
                validate_compact_event_summary(
                    ordered,
                    q=5,
                    primitive_characters=3,
                    frame_count=1,
                    first_t_numerator=0,
                    stop_t_numerator=10,
                ),
                (3, 1, 2),
            )
            truncated = dict(ordered)
            truncated["event_count"] = 2
            body = dict(truncated)
            body.pop("summary_sha256")
            truncated["summary_sha256"] = hashlib.sha256(
                canonical_json_bytes(body)
            ).hexdigest()
            with self.assertRaisesRegex(
                DirichletStreamConsumerError,
                "counters differ|peaks",
            ):
                validate_compact_event_summary(
                    truncated,
                    q=5,
                    primitive_characters=3,
                    frame_count=1,
                    first_t_numerator=0,
                    stop_t_numerator=10,
                )
            overflow = _EventWriter(
                root / "overflow.json",
                storage_mode=COMPACT_EVENT_STORAGE_MODE,
                maximum_event_count=1,
            )
            overflow.event({"event": "sign_change_candidate"})
            with self.assertRaisesRegex(
                DirichletStreamConsumerError,
                "event count",
            ):
                overflow.event({"event": "sign_change_candidate"})
            overflow.abort()

    def test_character_boundary_state_merge_is_associative(self) -> None:
        identity = {
            "conrey_number": 2,
            "primitive_ordinal": 0,
            "parity": 1,
        }

        def chunk(start: int, signs: tuple[int, ...]) -> dict[str, object]:
            state = _CharacterChunkState(**identity)
            for offset, sign in enumerate(signs):
                state.observe(start + 5 * offset, sign)
            return state.record()

        first = chunk(0, (1, 0))
        second = chunk(10, (0, -1))
        third = chunk(20, (-1, 1))
        left = combine_character_chunk_states(
            combine_character_chunk_states(first, second),
            third,
        )
        right = combine_character_chunk_states(
            first,
            combine_character_chunk_states(second, third),
        )
        self.assertEqual(left, right)
        self.assertEqual(left["sample_count"], 6)
        self.assertEqual(left["ambiguity_count"], 2)
        self.assertEqual(left["bracket_count"], 2)

        saturated = _CharacterChunkState(**identity)
        saturated.sample_count = MAX_EVENT_COUNT
        with self.assertRaisesRegex(
            DirichletStreamConsumerError,
            "overflows uint64",
        ):
            saturated.observe(0, 0)

    @staticmethod
    def _compact_state_fixture(
        root: Path,
        *,
        label: str,
        first_t_numerator: int,
        signs: tuple[tuple[int, ...], ...],
    ) -> dict[str, object]:
        identities = primitive_frequency_records_bulk(5)
        if len(signs) != len(identities):
            raise AssertionError("test sign roster differs")
        states = [
            _CharacterChunkState(
                conrey_number=row["conrey_number"],
                primitive_ordinal=row["primitive_ordinal"],
                parity=row["parity"],
            )
            for row in identities
        ]
        sample_count = len(signs[0])
        if any(len(row) != sample_count for row in signs):
            raise AssertionError("test sample roster differs")
        for state, row in zip(states, signs):
            for offset, sign in enumerate(row):
                state.observe(first_t_numerator + 5 * offset, sign)
        path = root / f"compact-state-leaf-{label}.json"
        writer = _EventWriter(
            path,
            storage_mode=COMPACT_EVENT_STORAGE_MODE,
            maximum_bytes=1024 * 1024,
        )
        for state in states:
            for index in range(state.bracket_count):
                writer.event(
                    {
                        "event": "sign_change_candidate",
                        "character": state.primitive_ordinal,
                        "index": index,
                    }
                )
            for index in range(state.ambiguity_count):
                writer.event(
                    {
                        "event": "indeterminate_completed_value",
                        "character": state.primitive_ordinal,
                        "index": index,
                    }
                )
        stop_t_numerator = first_t_numerator + 5 * sample_count
        writer.publish(
            compact_context={
                "q": 5,
                "primitive_character_count": len(states),
                "frame_count": 1,
                "first_t_numerator": first_t_numerator,
                "stop_t_numerator": stop_t_numerator,
                "t_denominator": 64,
                "t_step_numerator": 5,
            },
            character_states=[state.record() for state in states],
        )
        return compact_state_from_event_summary(json.loads(path.read_bytes()))

    def test_compact_state_merge_catches_cross_block_sign_and_attacks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._compact_state_fixture(
                root,
                label="first",
                first_t_numerator=0,
                signs=((1, 1), (1, 1), (0, 0)),
            )
            second = self._compact_state_fixture(
                root,
                label="second",
                first_t_numerator=10,
                signs=((-1, -1), (1, -1), (0, 0)),
            )
            third = self._compact_state_fixture(
                root,
                label="third",
                first_t_numerator=20,
                signs=((-1, 1), (-1, -1), (0, 0)),
            )
            merged = combine_compact_state_summaries(first, second)
            self.assertEqual(
                validate_compact_state_summary(merged),
                (5, 2, 4, 2),
            )
            self.assertEqual(merged["internal_sign_change_count"], 1)
            self.assertEqual(merged["cross_boundary_sign_change_count"], 1)
            self.assertEqual(
                combine_compact_state_summaries(merged, third),
                combine_compact_state_summaries(
                    first,
                    combine_compact_state_summaries(second, third),
                ),
            )

            gap = self._compact_state_fixture(
                root,
                label="gap",
                first_t_numerator=15,
                signs=((-1, -1), (-1, -1), (0, 0)),
            )
            with self.assertRaisesRegex(
                DirichletStreamConsumerError,
                "not adjacent",
            ):
                combine_compact_state_summaries(first, gap)

            reordered = dict(second)
            reordered["character_states"] = list(
                reversed(second["character_states"])
            )
            body = dict(reordered)
            body.pop("state_sha256")
            reordered["state_sha256"] = hashlib.sha256(
                canonical_json_bytes(body)
            ).hexdigest()
            with self.assertRaisesRegex(
                DirichletStreamConsumerError,
                "identity",
            ):
                validate_compact_state_summary(reordered)

            substituted = dict(second)
            substituted["sign_change_lower_bound"] = 2
            body = dict(substituted)
            body.pop("state_sha256")
            substituted["state_sha256"] = hashlib.sha256(
                canonical_json_bytes(body)
            ).hexdigest()
            with self.assertRaisesRegex(
                DirichletStreamConsumerError,
                "totals differ",
            ):
                validate_compact_state_summary(substituted)

    def test_compact_state_binary_roundtrip_and_attacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._compact_state_fixture(
                root,
                label="binary-first",
                first_t_numerator=0,
                signs=((1, 0), (1, -1), (0, 0)),
            )
            second = self._compact_state_fixture(
                root,
                label="binary-second",
                first_t_numerator=10,
                signs=((-1, -1), (-1, 1), (0, 1)),
            )
            state = combine_compact_state_summaries(first, second)
            path = root / "q-000005.state.bin"
            record = write_compact_state_binary(path, state)
            self.assertEqual(
                read_compact_state_binary(path, expected_record=record),
                state,
            )
            self.assertEqual(
                record["size_bytes"],
                record["header_bytes"]
                + 3 * CHARACTER_RECORD.size
                + record["ambiguity_range_record_count"]
                * AMBIGUITY_RANGE_RECORD.size
                + record["bracket_record_count"]
                * BRACKET_RECORD.size,
            )
            self.assertEqual(record["header_bytes"], ARTIFACT_HEADER.size)
            self.assertTrue(record["exact_ambiguity_ranges_retained"])
            self.assertTrue(record["ordered_bracket_records_retained"])

            original = path.read_bytes()
            path.write_bytes(original[:-1])
            with self.assertRaisesRegex(
                DirichletCompactStateBinaryError,
                "size differs|identity or arithmetic|truncated",
            ):
                read_compact_state_binary(path, expected_record=record)
            path.write_bytes(original)

            changed = bytearray(original)
            changed[-CHARACTER_RECORD.size] ^= 1
            path.write_bytes(changed)
            with self.assertRaisesRegex(
                DirichletCompactStateBinaryError,
                "digest differs|state",
            ):
                read_compact_state_binary(path, expected_record=record)
            path.write_bytes(original)

            reordered = (
                original[: record["header_bytes"]]
                + original[
                    record["header_bytes"] + CHARACTER_RECORD.size :
                    record["header_bytes"] + 2 * CHARACTER_RECORD.size
                ]
                + original[
                    record["header_bytes"] :
                    record["header_bytes"] + CHARACTER_RECORD.size
                ]
                + original[
                    record["header_bytes"] + 2 * CHARACTER_RECORD.size :
                ]
            )
            path.write_bytes(reordered)
            with self.assertRaises(
                (DirichletCompactStateBinaryError, DirichletStreamConsumerError)
            ):
                read_compact_state_binary(path, expected_record=record)
            path.write_bytes(original)

            duplicate_path = root / "q-000005.state-copy.bin"
            duplicate_record = write_compact_state_binary(
                duplicate_path, state
            )
            self.assertEqual(
                duplicate_path.read_bytes(),
                original,
            )
            self.assertNotEqual(
                duplicate_record["record_sha256"],
                record["record_sha256"],
            )

            first_record_offset = record["header_bytes"]
            first_record = list(
                CHARACTER_RECORD.unpack(
                    original[
                        first_record_offset :
                        first_record_offset + CHARACTER_RECORD.size
                    ]
                )
            )
            first_record[8] += AMBIGUITY_RANGE_RECORD.size
            gap_offset = bytearray(original)
            gap_offset[
                first_record_offset :
                first_record_offset + CHARACTER_RECORD.size
            ] = CHARACTER_RECORD.pack(*first_record)
            path.write_bytes(gap_offset)
            with self.assertRaisesRegex(
                DirichletCompactStateBinaryError,
                "offsets|coverage",
            ):
                read_compact_state_binary(path)

            nonzero_character_padding = bytearray(original)
            nonzero_character_padding[
                first_record_offset + CHARACTER_RECORD.size - 1
            ] = 1
            path.write_bytes(nonzero_character_padding)
            with self.assertRaisesRegex(
                DirichletCompactStateBinaryError,
                "nonzero padding",
            ):
                read_compact_state_binary(path)

            ambiguity_base = (
                record["header_bytes"]
                + record["character_record_count"] * CHARACTER_RECORD.size
            )
            if record["ambiguity_range_record_count"] >= 2:
                reordered_ranges = bytearray(original)
                first_range = bytes(
                    reordered_ranges[
                        ambiguity_base :
                        ambiguity_base + AMBIGUITY_RANGE_RECORD.size
                    ]
                )
                second_range = bytes(
                    reordered_ranges[
                        ambiguity_base + AMBIGUITY_RANGE_RECORD.size :
                        ambiguity_base + 2 * AMBIGUITY_RANGE_RECORD.size
                    ]
                )
                reordered_ranges[
                    ambiguity_base :
                    ambiguity_base + AMBIGUITY_RANGE_RECORD.size
                ] = second_range
                reordered_ranges[
                    ambiguity_base + AMBIGUITY_RANGE_RECORD.size :
                    ambiguity_base + 2 * AMBIGUITY_RANGE_RECORD.size
                ] = first_range
                path.write_bytes(reordered_ranges)
                with self.assertRaises(
                    (
                        DirichletCompactStateBinaryError,
                        DirichletStreamConsumerError,
                    )
                ):
                    read_compact_state_binary(path)

            bracket_base = (
                ambiguity_base
                + record["ambiguity_range_record_count"]
                * AMBIGUITY_RANGE_RECORD.size
            )
            nonzero_bracket_padding = bytearray(original)
            nonzero_bracket_padding[bracket_base + 18] = 1
            path.write_bytes(nonzero_bracket_padding)
            with self.assertRaisesRegex(
                DirichletCompactStateBinaryError,
                "nonzero padding",
            ):
                read_compact_state_binary(path)

            overflow_offset = bytearray(original)
            overflow_record = list(
                CHARACTER_RECORD.unpack(
                    original[
                        first_record_offset :
                        first_record_offset + CHARACTER_RECORD.size
                    ]
                )
            )
            overflow_record[8] = MAX_EVENT_COUNT
            overflow_offset[
                first_record_offset :
                first_record_offset + CHARACTER_RECORD.size
            ] = CHARACTER_RECORD.pack(*overflow_record)
            path.write_bytes(overflow_offset)
            with self.assertRaisesRegex(
                DirichletCompactStateBinaryError,
                "offsets|coverage",
            ):
                read_compact_state_binary(path)

    @staticmethod
    def _lane_receipt_fixture(
        root: Path,
        *,
        label: str,
        lane_index: int,
        t_start: int,
        t_stop: int,
        state: dict[str, object] | None,
    ) -> tuple[Path, str]:
        contract_sha256 = "ab" * 32
        heads: list[dict[str, object]] = []
        if state is not None:
            state_path = root / f"{label}-q-000005.bin"
            record = write_compact_state_binary(state_path, state)
            context = state["context"]
            heads.append(
                {
                    "q": context["q"],
                    "state_sha256": state["state_sha256"],
                    "first_t_numerator": context["first_t_numerator"],
                    "stop_t_numerator": context["stop_t_numerator"],
                    "primitive_character_count": context[
                        "primitive_character_count"
                    ],
                    "leaf_event_summary_count": state[
                        "leaf_event_summary_count"
                    ],
                    "sign_change_lower_bound": state[
                        "sign_change_lower_bound"
                    ],
                    "ambiguity_sample_count": state[
                        "ambiguity_sample_count"
                    ],
                    "state_after_binary": record,
                    "exact_ambiguity_ranges_retained": True,
                    "ordered_bracket_records_retained": True,
                    "turing_completeness": False,
                    "external_atom_discharged": False,
                }
            )
        adapter_body: dict[str, object] = {
            "schema": "synthetic-adapter-receipt-for-finalizer-kat",
            "lane_index": lane_index,
            "source_contract_sha256": contract_sha256,
            "assignment": {
                "lane_index": lane_index,
                "t_index_start_inclusive": t_start,
                "t_index_stop_exclusive": t_stop,
            },
        }
        adapter = dict(adapter_body)
        adapter["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(adapter_body)
        ).hexdigest()
        body: dict[str, object] = {
            "schema": TBLOCK_RECEIPT_SCHEMA,
            "schema_version": 2,
            "author": TBLOCK_AUTHOR,
            "atom_id": TBLOCK_ATOM_ID,
            "algorithm_id": TBLOCK_ALGORITHM_ID,
            "classification": TBLOCK_RECEIPT_CLASSIFICATION,
            "worker_classification": (
                NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
            ),
            "source_contract_sha256": contract_sha256,
            "lane_index": lane_index,
            "adapter_lane_receipt": adapter,
            "compact_state_q_count": len(heads),
            "compact_state_heads": heads,
            "complete": True,
            "decisions": {
                "all_artifact_hashes_computed_by_supervisor": True,
                "all_typed_bundles_freshly_replayed": True,
                "all_typed_bundles_admitted_by_existing_tmajor_adapter": True,
                "streamed_compact_event_resume_integrated": True,
                "compact_q_state_binary_checkpoint_resume_integrated": True,
                "compact_q_state_exact_roster_grid_adjacency_validated": True,
                "exact_ambiguity_ranges_retained": True,
                "ordered_bracket_records_retained": True,
                "refinement_artifacts_complete": False,
                "turing_completeness_claimed": False,
                "external_atom_discharged": False,
            },
        }
        receipt = dict(body)
        receipt["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        path = root / f"{label}-lane-receipt.json"
        path.write_bytes(canonical_json_bytes(receipt))
        return path, receipt["receipt_sha256"]

    @staticmethod
    def _mutate_receipt(
        source: Path,
        destination: Path,
        mutate,
    ) -> tuple[Path, str]:
        value = json.loads(source.read_bytes())
        mutate(value)
        value.pop("receipt_sha256")
        value["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(value)
        ).hexdigest()
        destination.write_bytes(canonical_json_bytes(value))
        return destination, value["receipt_sha256"]

    def test_cross_lane_finalizer_associativity_and_attacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._compact_state_fixture(
                root,
                label="lane-first",
                first_t_numerator=0,
                signs=((1, 0), (1, 1), (0, 0)),
            )
            second = self._compact_state_fixture(
                root,
                label="lane-second",
                first_t_numerator=10,
                signs=((0, -1), (-1, -1), (0, 1)),
            )
            third = self._compact_state_fixture(
                root,
                label="lane-third",
                first_t_numerator=20,
                signs=((-1, 1), (-1, 1), (1, 0)),
            )
            lane0, sha0 = self._lane_receipt_fixture(
                root,
                label="lane0",
                lane_index=0,
                t_start=0,
                t_stop=2,
                state=first,
            )
            lane1, sha1 = self._lane_receipt_fixture(
                root,
                label="lane1",
                lane_index=1,
                t_start=2,
                t_stop=4,
                state=second,
            )
            lane2, sha2 = self._lane_receipt_fixture(
                root,
                label="lane2",
                lane_index=2,
                t_start=4,
                t_stop=6,
                state=third,
            )
            expected_left = combine_compact_state_summaries(
                combine_compact_state_summaries(first, second),
                third,
            )
            expected_right = combine_compact_state_summaries(
                first,
                combine_compact_state_summaries(second, third),
            )
            self.assertEqual(expected_left, expected_right)
            receipt = finalize_compact_state_lanes(
                root / "final-receipt.json",
                root / "final-states",
                lane_receipt_paths=(lane0, lane1, lane2),
                expected_lane_receipt_sha256s=(sha0, sha1, sha2),
                expected_lane_count=3,
                expected_t_index_stop_exclusive=6,
                expected_source_contract_sha256="ab" * 32,
            )
            final_record = receipt["q_state_heads"][0]["state_binary"]
            self.assertEqual(
                read_compact_state_binary(
                    Path(final_record["path"]),
                    expected_record=final_record,
                ),
                expected_left,
            )
            expected_inserted = (
                expected_left["sign_change_lower_bound"]
                - first["sign_change_lower_bound"]
                - second["sign_change_lower_bound"]
                - third["sign_change_lower_bound"]
            )
            self.assertEqual(
                receipt["cross_lane_sign_changes_inserted"],
                expected_inserted,
            )
            self.assertFalse(
                receipt["decisions"]["turing_completeness"]
            )
            self.assertFalse(
                receipt["decisions"]["external_atom_discharged"]
            )

            with self.assertRaisesRegex(
                DirichletCompactStateFinalizerError,
                "identity|ordering",
            ):
                finalize_compact_state_lanes(
                    root / "reordered-lanes.json",
                    root / "reordered-lane-states",
                    lane_receipt_paths=(lane1, lane0),
                    expected_lane_receipt_sha256s=(sha1, sha0),
                    expected_lane_count=2,
                    expected_t_index_stop_exclusive=4,
                )

            duplicate, duplicate_sha = self._mutate_receipt(
                lane0,
                root / "duplicate-q-head.json",
                lambda value: (
                    value["compact_state_heads"].append(
                        dict(value["compact_state_heads"][0])
                    ),
                    value.__setitem__("compact_state_q_count", 2),
                ),
            )
            with self.assertRaisesRegex(
                DirichletCompactStateFinalizerError,
                "reordered",
            ):
                finalize_compact_state_lanes(
                    root / "duplicate-q.json",
                    root / "duplicate-q-states",
                    lane_receipt_paths=(duplicate,),
                    expected_lane_receipt_sha256s=(duplicate_sha,),
                    expected_lane_count=1,
                    expected_t_index_stop_exclusive=2,
                )

            gap = self._compact_state_fixture(
                root,
                label="lane-gap",
                first_t_numerator=15,
                signs=((0, -1), (-1, -1), (0, 1)),
            )
            gap_lane, gap_sha = self._lane_receipt_fixture(
                root,
                label="gap-lane1",
                lane_index=1,
                t_start=2,
                t_stop=4,
                state=gap,
            )
            with self.assertRaisesRegex(
                DirichletCompactStateFinalizerError,
                "head differs|not adjacent|merge failed",
            ):
                finalize_compact_state_lanes(
                    root / "gap.json",
                    root / "gap-states",
                    lane_receipt_paths=(lane0, gap_lane),
                    expected_lane_receipt_sha256s=(sha0, gap_sha),
                    expected_lane_count=2,
                    expected_t_index_stop_exclusive=4,
                )

            overlap = self._compact_state_fixture(
                root,
                label="lane-overlap",
                first_t_numerator=5,
                signs=((0, -1), (-1, -1), (0, 1)),
            )
            overlap_lane, overlap_sha = self._lane_receipt_fixture(
                root,
                label="overlap-lane1",
                lane_index=1,
                t_start=2,
                t_stop=4,
                state=overlap,
            )
            with self.assertRaisesRegex(
                DirichletCompactStateFinalizerError,
                "head differs|not adjacent|merge failed",
            ):
                finalize_compact_state_lanes(
                    root / "overlap.json",
                    root / "overlap-states",
                    lane_receipt_paths=(lane0, overlap_lane),
                    expected_lane_receipt_sha256s=(sha0, overlap_sha),
                    expected_lane_count=2,
                    expected_t_index_stop_exclusive=4,
                )

            empty_lane, empty_sha = self._lane_receipt_fixture(
                root,
                label="empty-lane1",
                lane_index=1,
                t_start=2,
                t_stop=4,
                state=None,
            )
            with self.assertRaisesRegex(
                DirichletCompactStateFinalizerError,
                "appears|reappears",
            ):
                finalize_compact_state_lanes(
                    root / "reappeared.json",
                    root / "reappeared-states",
                    lane_receipt_paths=(lane0, empty_lane, lane2),
                    expected_lane_receipt_sha256s=(
                        sha0,
                        empty_sha,
                        sha2,
                    ),
                    expected_lane_count=3,
                    expected_t_index_stop_exclusive=6,
                )

            with self.assertRaisesRegex(
                DirichletCompactStateFinalizerError,
                "total output byte bound",
            ):
                finalize_compact_state_lanes(
                    root / "bounded.json",
                    root / "bounded-states",
                    lane_receipt_paths=(lane0,),
                    expected_lane_receipt_sha256s=(sha0,),
                    expected_lane_count=1,
                    expected_t_index_stop_exclusive=2,
                    maximum_total_output_bytes=1,
                )

    def test_inventory_projection_is_explicitly_not_feasibility(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target_input = (
                root
                / "target-inputs/block-00000000/q-010001/job/frame-0"
            )
            target_input.mkdir(parents=True)
            (target_input / "lattice-input.bin").write_bytes(b"x" * 20)
            (target_input / "lattice-output.bin").write_bytes(b"y" * 4)
            (target_input / "finite-recovery.bin").write_bytes(b"z" * 4)
            worker = root / "worker-output/block-00000000/q-010001"
            (worker / "pipeline").mkdir(parents=True)
            (worker / "pipeline/events.ndjson").write_bytes(b"e" * 2048)
            (worker / "typed-bundle.json").write_bytes(b"{}")
            staged = root / "checkpoints/typed-bundles"
            staged.mkdir(parents=True)
            (staged / "block-00000000-bundle-00000000.json").write_bytes(
                b"{}"
            )
            inventory = inventory_campaign(root)
            projection = project_source_scale(inventory)
            self.assertEqual(inventory["file_count"], 6)
            self.assertFalse(
                projection["decisions"][
                    "projection_is_source_feasibility_evidence"
                ]
            )
            self.assertFalse(
                projection["decisions"]["source_scale_admitted"]
            )

    def test_source_scale_preflight_stays_closed(self) -> None:
        boundary = storage_boundary()
        self.assertTrue(
            boundary["implemented"]["content_addressed_chunk_store"]
        )
        self.assertTrue(
            boundary["implemented"][
                "exact_maximal_ambiguity_range_retention"
            ]
        )
        self.assertTrue(
            boundary["implemented"]["same_rule_cross_lane_q_state_finalizer"]
        )
        model = compact_state_storage_model()
        self.assertEqual(
            model["binary_layout"]["exact_size_equation"],
            "176 + 104*characters + 16*maximal_ambiguity_ranges "
            "+ 32*ordered_brackets",
        )
        self.assertEqual(
            model["source_fixed_index_floor"][
                "header_plus_character_index_bytes"
            ],
            3_073_003_099_816,
        )
        self.assertFalse(boundary["source_scale_storage_admitted"])
        with self.assertRaisesRegex(
            DirichletTBlockStorageError,
            "source-scale storage is not admitted",
        ):
            require_source_scale_storage_ready()


if __name__ == "__main__":
    unittest.main()
