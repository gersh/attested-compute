# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from tg_verifier import dirichlet_compact_state_streaming_v3 as v3
from tg_verifier.dirichlet_campaign import (
    _smallest_prime_factors,
    primitive_character_count,
)
from tg_verifier.dirichlet_lattice_stage import maximum_t_index
from tg_verifier.dirichlet_root_number_stage import (
    primitive_frequency_records_bulk,
)
from tg_verifier.dirichlet_source_supervisor import PINNED_SOURCE_LANE_TOTALS


def _binding(digit: str) -> str:
    return digit * 64


class DirichletCompactStateStreamingV3Test(unittest.TestCase):
    def _write(
        self,
        path: Path,
        codes: list[int],
        *,
        first: int = 0,
        stop: int = 20,
        binding: str = "1",
    ) -> dict:
        return v3.write_flat_sign_codes_v3(
            path,
            q=5,
            frame_count=1,
            first_t_numerator=first,
            stop_t_numerator=stop,
            code_chunks=[codes],
            source_binding_sha256=_binding(binding),
        )

    def test_producer_binary_replay_round_trip_without_sign_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.bin"
            record = self._write(
                path,
                [
                    1,
                    1,
                    2,
                    2,
                    0,
                    0,
                    2,
                    2,
                    1,
                    0,
                    0,
                    2,
                ],
            )
            self.assertEqual(v3.replay_compact_state_v3(path), record)
            states = list(v3.iter_compact_state_v3(path))
            self.assertEqual(len(states), 3)
            self.assertEqual(
                [state["internal_sign_change_count"] for state in states],
                [1, 0, 1],
            )
            self.assertEqual(
                [state["ambiguity_count"] for state in states],
                [0, 2, 2],
            )
            self.assertFalse(record["producer_fused_with_arithmetic"])
            self.assertFalse(record["source_scale_storage_admitted"])
            self.assertFalse(record["external_atom_discharged"])
            self.assertFalse((path.parent / "signs.bin").exists())

    def test_completed_real_disk_stream_fuses_strict_signs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.bin"
            centers = (
                -2.0,
                -2.0,
                2.0,
                2.0,
                0.0,
                0.0,
                2.0,
                2.0,
                -2.0,
                0.0,
                0.0,
                2.0,
            )
            rows = [(center, 0.125, 0.125) for center in centers]
            record = v3.write_completed_real_disk_stream_v3(
                path,
                q=5,
                frame_count=1,
                first_t_numerator=0,
                stop_t_numerator=20,
                disk_chunks=[rows[:5], rows[5:]],
                source_binding_sha256=_binding("a"),
            )
            self.assertEqual(record["transition_count"], 2)
            self.assertEqual(record["ambiguity_sample_count"], 4)
            self.assertEqual(v3.replay_compact_state_v3(path), record)

    def test_padding_tamper_rejected_even_with_recomputed_page_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.bin"
            self._write(
                path,
                [1, 1, 1, 1, 2, 2, 2, 2, 1, 1, 1, 1],
            )
            raw = bytearray(path.read_bytes())
            page_offset = v3.ARTIFACT_HEADER.size
            values = list(
                v3.PAGE_HEADER.unpack(
                    raw[page_offset : page_offset + v3.PAGE_HEADER.size]
                )
            )
            payload_offset = page_offset + v3.PAGE_HEADER.size
            # q=5 has three characters, four samples and a six-bit record.
            # Only two bits of the third packed byte are used.
            raw[payload_offset + 2] |= 0x80
            payload_bytes = values[3]
            payload = bytes(
                raw[payload_offset : payload_offset + payload_bytes]
            )
            prefix = v3.PAGE_PREFIX.pack(*values[:8])
            values[8] = hashlib.sha256(
                v3.PAGE_DOMAIN + prefix + payload
            ).digest()
            raw[
                page_offset : page_offset + v3.PAGE_HEADER.size
            ] = v3.PAGE_HEADER.pack(*values)
            path.write_bytes(raw)
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error, "padding"
            ):
                v3.replay_compact_state_v3(path)

    def test_transition_count_overflow_and_noncanonical_range_split_rejected(
        self,
    ) -> None:
        identities = primitive_frequency_records_bulk(5)
        span = {
            "sample_count": 4,
            "first_determinate_numerator": 15,
            "first_sign": 1,
            "last_determinate_numerator": 15,
            "last_sign": 1,
            "leading_ambiguity_count": 3,
            "trailing_ambiguity_count": 0,
            "ambiguity_count": 3,
            "internal_sign_change_count": 1,
            "ambiguity_ranges": [
                {"first_t_numerator": 0, "stop_t_numerator": 15}
            ],
            "bracket_records": [],
        }
        states = [
            {
                "conrey_number": identity["conrey_number"],
                "primitive_ordinal": identity["primitive_ordinal"],
                "parity": identity["parity"],
                **span,
            }
            for identity in identities
        ]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error,
                "transition count",
            ):
                v3.write_compact_state_v3(
                    Path(temporary) / "overflow.bin",
                    q=5,
                    frame_count=1,
                    first_t_numerator=0,
                    stop_t_numerator=20,
                    states=states,
                    source_binding_sha256=_binding("2"),
                )
            split = [dict(state) for state in states]
            split[0] = dict(split[0])
            split[0]["internal_sign_change_count"] = 0
            split[0]["ambiguity_ranges"] = [
                {"first_t_numerator": 0, "stop_t_numerator": 5},
                {"first_t_numerator": 5, "stop_t_numerator": 15},
            ]
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error,
                "maximal",
            ):
                v3.write_compact_state_v3(
                    Path(temporary) / "split.bin",
                    q=5,
                    frame_count=1,
                    first_t_numerator=0,
                    stop_t_numerator=20,
                    states=split,
                    source_binding_sha256=_binding("3"),
                )

    def test_lane_merge_uses_full_span_width_and_inserts_boundary_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "left.bin"
            right = root / "right.bin"
            output = root / "output.bin"
            # Every character changes once inside each two-sample lane, and
            # the left last sign differs from the right first sign.
            left_record = self._write(
                left,
                [1, 2, 1, 2, 1, 2],
                first=0,
                stop=10,
                binding="4",
            )
            right_record = self._write(
                right,
                [1, 2, 1, 2, 1, 2],
                first=10,
                stop=20,
                binding="5",
            )
            receipt = v3.finalize_compact_state_v3_lanes(
                [left, right],
                output,
                expected_records=[left_record, right_record],
                turing_total=9,
            )
            header = v3.inspect_compact_state_v3(output)
            self.assertEqual(left_record["transition_count_width_bits"], 1)
            self.assertEqual(header.count_width, 2)
            self.assertEqual(receipt["lane_internal_transition_sum"], 6)
            self.assertEqual(receipt["cross_lane_transition_count"], 3)
            self.assertEqual(receipt["q_transition_count"], 9)
            self.assertTrue(receipt["q_aggregate_counts_equal"])
            self.assertFalse(receipt["aggregate_turing_closure_admitted"])

    def test_three_lane_merge_is_semantically_associative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / f"lane-{index}.bin" for index in range(3)]
            records = [
                self._write(
                    paths[0],
                    [1, 1, 2, 0, 0, 1],
                    first=0,
                    stop=10,
                    binding="6",
                ),
                self._write(
                    paths[1],
                    [2, 2, 0, 2, 2, 2],
                    first=10,
                    stop=20,
                    binding="7",
                ),
                self._write(
                    paths[2],
                    [2, 1, 2, 2, 2, 1],
                    first=20,
                    stop=30,
                    binding="8",
                ),
            ]
            direct = root / "direct.bin"
            v3.finalize_compact_state_v3_lanes(
                paths,
                direct,
                expected_records=records,
            )
            first_two = root / "first-two.bin"
            first_receipt = v3.finalize_compact_state_v3_lanes(
                paths[:2],
                first_two,
                expected_records=records[:2],
            )
            grouped = root / "grouped.bin"
            v3.finalize_compact_state_v3_lanes(
                [first_two, paths[2]],
                grouped,
                expected_records=[
                    first_receipt["output_artifact"],
                    records[2],
                ],
            )
            direct_header = v3.inspect_compact_state_v3(direct)
            grouped_header = v3.inspect_compact_state_v3(grouped)
            self.assertEqual(
                direct_header.transition_count,
                grouped_header.transition_count,
            )
            self.assertEqual(
                direct_header.ambiguity_sample_count,
                grouped_header.ambiguity_sample_count,
            )
            self.assertEqual(
                list(v3.iter_compact_state_v3(direct)),
                list(v3.iter_compact_state_v3(grouped)),
            )
            self.assertEqual(direct.read_bytes(), grouped.read_bytes())

    def test_finalizer_receipt_uses_the_semantically_replayed_lane_pass(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "left.bin"
            right = root / "right.bin"
            output = root / "output.bin"
            records = [
                self._write(
                    left,
                    [1, 2, 1, 2, 1, 2],
                    first=0,
                    stop=10,
                    binding="9",
                ),
                self._write(
                    right,
                    [2, 1, 2, 1, 2, 1],
                    first=10,
                    stop=20,
                    binding="a",
                ),
            ]
            original = v3.replay_compact_state_v3
            replayed_paths: list[Path] = []

            def output_only_replay(path: Path, **kwargs: object) -> dict:
                resolved = path.resolve()
                replayed_paths.append(resolved)
                if resolved in {left.resolve(), right.resolve()}:
                    raise AssertionError("lane was replayed a second time")
                return original(path, **kwargs)

            with mock.patch.object(
                v3,
                "replay_compact_state_v3",
                side_effect=output_only_replay,
            ):
                receipt = v3.finalize_compact_state_v3_lanes(
                    [left, right],
                    output,
                    expected_records=records,
                )
            self.assertEqual(replayed_paths, [output.resolve()])
            self.assertEqual(
                receipt["lane_artifact_sha256"],
                [record["artifact_sha256"] for record in records],
            )

    def test_debug_brackets_never_enable_source_admission(self) -> None:
        identities = primitive_frequency_records_bulk(5)
        rows = []
        patterns = (
            {
                "first_determinate_numerator": 0,
                "first_sign": -1,
                "last_determinate_numerator": 15,
                "last_sign": 1,
                "leading_ambiguity_count": 0,
                "trailing_ambiguity_count": 0,
                "ambiguity_count": 0,
                "internal_sign_change_count": 1,
                "ambiguity_ranges": [],
                "bracket_records": [
                    {
                        "lower_t_numerator": 5,
                        "upper_t_numerator": 10,
                        "lower_sign": -1,
                        "upper_sign": 1,
                        "intervening_ambiguity_count": 0,
                    }
                ],
            },
            {
                "first_determinate_numerator": 0,
                "first_sign": 1,
                "last_determinate_numerator": 15,
                "last_sign": 1,
                "leading_ambiguity_count": 0,
                "trailing_ambiguity_count": 0,
                "ambiguity_count": 0,
                "internal_sign_change_count": 0,
                "ambiguity_ranges": [],
                "bracket_records": [],
            },
            {
                "first_determinate_numerator": None,
                "first_sign": 0,
                "last_determinate_numerator": None,
                "last_sign": 0,
                "leading_ambiguity_count": 4,
                "trailing_ambiguity_count": 4,
                "ambiguity_count": 4,
                "internal_sign_change_count": 0,
                "ambiguity_ranges": [
                    {"first_t_numerator": 0, "stop_t_numerator": 20}
                ],
                "bracket_records": [],
            },
        )
        for identity, pattern in zip(identities, patterns):
            rows.append(
                {
                    "conrey_number": identity["conrey_number"],
                    "primitive_ordinal": identity["primitive_ordinal"],
                    "parity": identity["parity"],
                    "sample_count": 4,
                    **pattern,
                }
            )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "debug.bin"
            record = v3.write_compact_state_v3(
                path,
                q=5,
                frame_count=1,
                first_t_numerator=0,
                stop_t_numerator=20,
                states=rows,
                source_binding_sha256=_binding("9"),
                debug_brackets=True,
            )
            self.assertTrue(
                record["exact_bracket_coordinates_retained_for_debug_only"]
            )
            self.assertFalse(record["source_scale_layout"])
            self.assertFalse(record["source_scale_storage_admitted"])
            with self.assertRaises(v3.DirichletCompactStateV3Error):
                v3.require_source_admission_v3()

    def test_roster_and_source_span_substitution_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "state.bin"
            record = self._write(
                path,
                [1, 1, 1, 1, 2, 2, 2, 2, 1, 1, 1, 1],
            )
            changed = dict(record)
            changed["complete_primitive_roster_sha256"] = "0" * 64
            body = dict(changed)
            body.pop("record_sha256")
            changed["record_sha256"] = hashlib.sha256(
                v3.canonical_json_bytes(body)
            ).hexdigest()
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error, "expected record"
            ):
                v3.replay_compact_state_v3(path, expected_record=changed)

            raw = bytearray(path.read_bytes())
            values = list(
                v3.ARTIFACT_HEADER.unpack(
                    raw[: v3.ARTIFACT_HEADER.size]
                )
            )
            # stop_t_numerator field
            values[10] += 1
            raw[: v3.ARTIFACT_HEADER.size] = v3.ARTIFACT_HEADER.pack(*values)
            path.write_bytes(raw)
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error, "grid"
            ):
                v3.replay_compact_state_v3(path)

    def test_exception_mmr_summary_and_dense_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state.bin"
            record = self._write(
                state,
                [
                    1,
                    1,
                    2,
                    2,
                    0,
                    0,
                    2,
                    2,
                    1,
                    0,
                    0,
                    2,
                ],
            )
            exception = root / "exceptions.bin"
            summary = root / "summary.json"
            result = v3.retire_compact_state_v3(
                state,
                exception,
                summary,
                expected_state_record=record,
                turing_total=2,
                discard_dense_state=True,
            )
            self.assertFalse(state.exists())
            self.assertTrue(exception.is_file())
            self.assertTrue(summary.is_file())
            self.assertTrue(result["q_aggregate_counts_equal"])
            self.assertTrue(
                result[
                    "dense_state_retirement_authorized_after_durable_summary"
                ]
            )
            self.assertFalse(result["aggregate_turing_closure_admitted"])
            replay = v3.replay_exception_artifact_v3(
                exception,
                expected_record=result["exception_artifact"],
            )
            self.assertEqual(replay["ambiguity_range_count"], 2)
            self.assertEqual(replay["ambiguity_sample_count"], 4)

            raw = bytearray(exception.read_bytes())
            raw[-1] ^= 1
            exception.write_bytes(raw)
            with self.assertRaises(v3.DirichletCompactStateV3Error):
                v3.replay_exception_artifact_v3(exception)

    def test_exception_replay_rejects_post_read_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state.bin"
            record = self._write(
                state,
                [1, 1, 0, 2, 1, 0, 2, 2, 1, 1, 0, 2],
            )
            exception = root / "exceptions.bin"
            expected = v3.write_exception_artifact_v3(
                state,
                exception,
                expected_state_record=record,
            )
            original_read_exact = v3._read_exact
            changed = False

            def mutate_consumed_range(
                source: object, count: int, *, label: str
            ) -> bytes:
                nonlocal changed
                raw = original_read_exact(source, count, label=label)
                if label == "v3 exception range" and not changed:
                    changed = True
                    position = source.tell() - 1
                    with exception.open("r+b") as target:
                        target.seek(position)
                        value = target.read(1)
                        target.seek(position)
                        target.write(bytes((value[0] ^ 1,)))
                return raw

            with mock.patch.object(
                v3, "_read_exact", side_effect=mutate_consumed_range
            ):
                with self.assertRaisesRegex(
                    v3.DirichletCompactStateV3Error,
                    "changed while it was replayed",
                ):
                    v3.replay_exception_artifact_v3(
                        exception, expected_record=expected
                    )
            self.assertTrue(changed)

    def test_retirement_is_fail_closed_and_summary_precedes_unlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state.bin"
            record = self._write(
                state,
                [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2],
            )

            mismatch_exception = root / "mismatch-exceptions.bin"
            mismatch_summary = root / "mismatch-summary.json"
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error,
                "matches the supplied Turing total",
            ):
                v3.retire_compact_state_v3(
                    state,
                    mismatch_exception,
                    mismatch_summary,
                    expected_state_record=record,
                    turing_total=0,
                    discard_dense_state=True,
                )
            self.assertTrue(state.is_file())
            self.assertFalse(mismatch_exception.exists())
            self.assertFalse(mismatch_summary.exists())

            exception = root / "exceptions.bin"
            summary = root / "summary.json"
            with mock.patch.object(
                v3,
                "_unlink_dense_state",
                side_effect=OSError("injected unlink failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected unlink"):
                    v3.retire_compact_state_v3(
                        state,
                        exception,
                        summary,
                        expected_state_record=record,
                        turing_total=9,
                        discard_dense_state=True,
                    )
            self.assertTrue(state.is_file())
            self.assertTrue(exception.is_file())
            self.assertTrue(summary.is_file())

            second_exception = root / "second-exceptions.bin"
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error,
                "immutable v3 retained q summary",
            ):
                v3.retire_compact_state_v3(
                    state,
                    second_exception,
                    summary,
                    expected_state_record=record,
                    turing_total=9,
                    discard_dense_state=True,
                )
            self.assertTrue(state.is_file())
            self.assertFalse(second_exception.exists())

    def test_replay_returns_record_from_single_semantic_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.bin"
            expected = self._write(
                path,
                [1, 2, 0, 2, 1, 2, 1, 1, 2, 2, 1, 2],
            )
            with mock.patch.object(
                v3,
                "inspect_compact_state_v3",
                side_effect=AssertionError("unexpected second header pass"),
            ):
                replayed = v3.replay_compact_state_v3(
                    path, expected_record=expected
                )
            self.assertEqual(replayed, expected)
            self.assertEqual(
                replayed["artifact_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )

    def test_symbolic_inputs_and_dangling_outputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state.bin"
            record = self._write(
                state,
                [1, 2, 0, 2, 1, 2, 1, 1, 2, 2, 1, 2],
            )
            state_link = root / "state-link.bin"
            state_link.symlink_to(state)
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error, "artifact type"
            ):
                v3.replay_compact_state_v3(
                    state_link, expected_record=record
                )

            exception = root / "exceptions.bin"
            exception_record = v3.write_exception_artifact_v3(
                state,
                exception,
                expected_state_record=record,
            )
            exception_link = root / "exception-link.bin"
            exception_link.symlink_to(exception)
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error,
                "exception artifact type",
            ):
                v3.replay_exception_artifact_v3(
                    exception_link,
                    expected_record=exception_record,
                )

            dangling_target = root / "unexpected-state.bin"
            dangling_output = root / "dangling-state.bin"
            dangling_output.symlink_to(dangling_target)
            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error,
                "immutable v3 artifact",
            ):
                self._write(
                    dangling_output,
                    [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2],
                )
            self.assertTrue(dangling_output.is_symlink())
            self.assertFalse(dangling_target.exists())

            with self.assertRaisesRegex(
                v3.DirichletCompactStateV3Error, "artifact type"
            ):
                v3.retire_compact_state_v3(
                    state_link,
                    root / "retired-exceptions.bin",
                    root / "summary.json",
                    expected_state_record=record,
                    turing_total=record["transition_count"],
                    discard_dense_state=True,
                )
            self.assertTrue(state.is_file())

    def test_source_projection_recomputes_reviewed_final_floor(self) -> None:
        projection = v3.source_storage_projection_v3()
        self.assertEqual(projection["primitive_character_count"], 29_547_446_729)
        self.assertEqual(
            projection["final_dense_byte_floor_without_q_or_page_padding"],
            62_259_950_420,
        )
        self.assertFalse(projection["ambiguity_density_measured"])
        self.assertFalse(projection["source_scale_storage_admitted"])

    def test_transition_width_power_of_two_capacity_boundaries(self) -> None:
        self.assertEqual(
            [
                v3.transition_count_width(samples)
                for samples in (1, 2, 3, 4, 5, 8, 9)
            ],
            [1, 1, 2, 2, 3, 3, 4],
        )
        for samples in (1, 2, 3, 4, 5, 8, 9, 64, 65):
            width = v3.transition_count_width(samples)
            maximum_transition_count = samples - 1
            self.assertLess(maximum_transition_count, 1 << width)
            if samples > 1:
                self.assertGreaterEqual(
                    maximum_transition_count,
                    1 << (width - 1),
                )

    def test_independent_eight_lane_dense_projection(self) -> None:
        spf = _smallest_prime_factors(400_000)
        final_bits = 0
        lane_bits = [0] * 8
        width_histogram: dict[int, int] = {}
        characters = 0
        for q in range(10_001, 400_001):
            count = primitive_character_count(q, spf)
            if count == 0:
                continue
            samples = maximum_t_index(q) + 1
            width = max(1, (samples - 1).bit_length())
            characters += count
            final_bits += count * (4 + width)
            width_histogram[width] = (
                width_histogram.get(width, 0) + count
            )
            for lane, (
                _index,
                lane_start,
                lane_stop,
                _payload,
                _work,
            ) in enumerate(PINNED_SOURCE_LANE_TOTALS):
                lane_samples = max(
                    0, min(lane_stop, samples) - lane_start
                )
                if lane_samples:
                    lane_width = max(
                        1, (lane_samples - 1).bit_length()
                    )
                    lane_bits[lane] += count * (4 + lane_width)
        self.assertEqual(characters, 29_547_446_729)
        self.assertEqual((final_bits + 7) // 8, 62_259_950_420)
        self.assertEqual(
            width_histogram,
            {
                12: 10_240_064_835,
                13: 14_719_219_258,
                14: 3_478_761_803,
                15: 845_913_314,
                16: 211_464_707,
                17: 52_022_812,
            },
        )
        self.assertEqual(
            [(bits + 7) // 8 for bits in lane_bits],
            [
                51_708_031_776,
                51_708_031_776,
                51_708_031_776,
                51_708_031_776,
                51_310_245_185,
                31_294_728_250,
                17_936_334_940,
                5_860_572_012,
            ],
        )


if __name__ == "__main__":
    unittest.main()
