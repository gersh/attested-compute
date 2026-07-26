# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from fractions import Fraction
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_certified as v2
from tg_verifier.dirichlet_booker_smallq_factored import (
    CHARACTER_HEADER,
    FactoredSmallQError,
    INPUT_HEADER,
    PARAMETER_HEADER,
    SHARED_PREFIX,
    factored_device_memory_bytes,
    factored_service_batch_plan,
    parse_factored_character_batch,
    parse_factored_shared_plan,
    parse_factored_seed_frame,
    source_work,
    verify_factored_output_kat,
    verify_factored_seed_frame,
    verify_factored_service_campaign,
    verify_factored_service_output_kat,
    write_factored_character_batch,
    write_factored_seed_frame,
    write_factored_service_campaign,
    write_factored_shared_plan,
)


def _pinned_flint_available() -> bool:
    if base.FLINT_IMPORT_ERROR is not None:
        return False
    return (
        str(base.flint.__version__),
        str(base.flint.__FLINT_VERSION__),
        int(base.flint.__FLINT_RELEASE__),
    ) == (base.EXPECTED_PYTHON_FLINT, base.EXPECTED_FLINT, base.EXPECTED_FLINT_RELEASE)


class FactoredSmallQStructuralTests(unittest.TestCase):
    def test_exact_source_cardinality_removes_character_repetition(self) -> None:
        work = source_work()
        self.assertEqual(work["primitive_characters"], 18_477_108)
        self.assertEqual(work["legacy_character_frequency_seeds"], 7_078_844_301_312)
        self.assertEqual(work["shared_frequency_records"], 16_385_441_792)
        self.assertEqual(work["legacy_v2_seed_bytes"], 622_938_298_515_456)
        self.assertEqual(work["factored_v3_minimum_logical_bytes"], 2_459_841_190_828)
        self.assertGreater(work["seed_cardinality_reduction_ratio"], 432)
        self.assertGreater(work["payload_reduction_ratio"], 253)
        self.assertTrue(work["q_persistent_service_implemented"])
        self.assertTrue(work["cuda_factored_consumer_implemented"])
        self.assertEqual(work["service_batch_count"], 8_971)
        self.assertEqual(work["service_maximum_batches_for_one_q"], 2)
        self.assertEqual(work["factored_v3_service_physical_bytes"], 2_459_842_579_084)
        self.assertEqual(work["factored_v3_service_overhead_above_minimum_bytes"], 1_388_256)
        self.assertEqual(work["factored_v3_literal_service_output_bytes"], 339_784_527_970_104)
        self.assertEqual(
            work["factored_v3_source_sample_only_service_output_bytes"],
            226_995_959_255_448,
        )
        self.assertEqual(
            work["factored_v3_source_sample_only_bytes_avoided"],
            112_788_568_714_656,
        )
        self.assertEqual(work["source_completed_lattice_output_items"], 4_729_082_453_090)
        self.assertEqual(work["source_guard_frequency_output_items"], 2_349_761_848_222)
        self.assertEqual(work["source_guard_frequency_output_bytes"], 112_788_568_714_656)
        self.assertEqual(
            work["source_two_bit_sign_payload_bytes_if_materialized"],
            1_182_270_615_343,
        )
        self.assertTrue(work["streaming_integrity_reducer_implemented"])
        self.assertEqual(work["streaming_integrity_persistent_raw_output_bytes"], 0)
        self.assertTrue(work["streaming_semantic_sign_reducer_implemented"])
        self.assertFalse(work["streaming_semantic_sign_reducer_cuda_fused"])
        self.assertEqual(
            work["semantic_time_tail_control_records"], 8_116_121_626
        )
        self.assertEqual(
            work["semantic_time_tail_control_bytes"], 129_858_785_904
        )
        self.assertEqual(
            work["semantic_two_bit_sign_artifact_bytes"], 1_182_271_755_191
        )
        self.assertFalse(
            work["streaming_semantic_sign_reducer_performs_multiplicity_inference"]
        )
        self.assertEqual(
            work[
                "streaming_source_sample_only_raw_output_bytes_cross_process_boundary"
            ],
            226_995_959_255_448,
        )
        self.assertEqual(work["service_streamed_seed_moduli"], 2)
        self.assertLessEqual(work["service_peak_explicit_device_bytes"], 80 * 1024**3)
        self.assertEqual(work["shared_seed_stream_copies_per_q"], 1)
        self.assertFalse(work["external_atom_discharged"])

    def test_memory_plan_streams_only_when_full_shared_plan_does_not_fit(self) -> None:
        low_q = factored_service_batch_plan(
            q=3,
            transform_length=1 << 29,
            character_count=1,
            usable_device_bytes=80 * 1024**3,
        )
        high_q = factored_service_batch_plan(
            q=9817,
            transform_length=1 << 18,
            character_count=9815,
            usable_device_bytes=80 * 1024**3,
        )
        self.assertFalse(low_q["shared_seeds_resident"])
        self.assertEqual(low_q["campaign_batch_count"], 1)
        self.assertTrue(high_q["shared_seeds_resident"])
        self.assertEqual(high_q["campaign_batch_count"], 2)
        exact = factored_device_memory_bytes(
            q=9817,
            transform_length=1 << 18,
            batch_count=int(high_q["maximum_batch_characters"]),
        )
        self.assertEqual(exact["explicit_allocation_total"], high_q["explicit_device_bytes"])


@unittest.skipUnless(
    _pinned_flint_available(), "requires pinned python-flint 0.9.0 / FLINT 3.6.0"
)
class FactoredSmallQArbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.parameters = base.transform_parameters(
            5,
            height=Fraction(1),
            guard_height=Fraction(4),
            transform_length=128,
            eta=Fraction(0),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_roundtrip_replays_shared_values_and_is_smaller_than_v2(self) -> None:
        factored = self.root / "factored.bin"
        legacy = self.root / "legacy.bin"
        produced = write_factored_seed_frame(
            factored,
            q=5,
            conrey_numbers=(2, 4),
            parameters=self.parameters,
        )
        v2.write_seed_frame(
            legacy,
            q=5,
            conrey_numbers=(2, 4),
            parameters=self.parameters,
        )
        frame = parse_factored_seed_frame(factored)
        self.assertEqual(len(frame.characters), 2)
        self.assertEqual(len(frame.shared_seeds), 128)
        self.assertLess(factored.stat().st_size, legacy.stat().st_size)
        self.assertGreater(produced["frequency_payload_reduction_ratio"], 1)
        replay = verify_factored_seed_frame(
            factored, parameters=self.parameters, guard_bits=64
        )
        self.assertTrue(replay["passed"])
        self.assertEqual(replay["shared_frequency_records_replayed"], 128)
        self.assertEqual(replay["legacy_character_frequency_seed_count"], 256)

    def test_epsilon_tamper_fails_independent_replay(self) -> None:
        path = self.root / "epsilon-tamper.bin"
        write_factored_seed_frame(
            path,
            q=5,
            conrey_numbers=(2, 4),
            parameters=self.parameters,
        )
        raw = bytearray(path.read_bytes())
        epsilon_real = INPUT_HEADER.size + PARAMETER_HEADER.size + 24
        original = struct.unpack_from("<d", raw, epsilon_real)[0]
        struct.pack_into("<d", raw, epsilon_real, original + 1.0)
        path.write_bytes(raw)
        with self.assertRaisesRegex(FactoredSmallQError, "epsilon disk"):
            verify_factored_seed_frame(path, parameters=self.parameters)

    def test_parity_truncation_tamper_fails_independent_replay(self) -> None:
        path = self.root / "truncation-tamper.bin"
        write_factored_seed_frame(
            path,
            q=5,
            conrey_numbers=(2, 4),
            parameters=self.parameters,
        )
        raw = bytearray(path.read_bytes())
        characters_bytes = 2 * (CHARACTER_HEADER.size + 5 * 4)
        first_truncation = (
            INPUT_HEADER.size
            + PARAMETER_HEADER.size
            + characters_bytes
            + SHARED_PREFIX.size
            + v2.DISK.size
        )
        truncation = struct.unpack_from("<I", raw, first_truncation)[0]
        struct.pack_into("<I", raw, first_truncation, truncation + 1)
        path.write_bytes(raw)
        with self.assertRaisesRegex(FactoredSmallQError, "truncation mismatch"):
            verify_factored_seed_frame(path, parameters=self.parameters)

    def test_split_service_roundtrip_replays_shared_plan_once(self) -> None:
        plan_path = self.root / "plan.bin"
        batch_dir = self.root / "batches"
        record = write_factored_service_campaign(
            plan_path,
            batch_dir,
            q=5,
            conrey_numbers=(2, 3, 4),
            parameters=self.parameters,
            maximum_batch_characters=2,
        )
        batch_paths = [Path(item["path"]) for item in record["batches"]]
        self.assertEqual(record["campaign_batch_count"], 2)
        self.assertEqual(record["shared_seed_stream_copies"], 1)
        plan = parse_factored_shared_plan(plan_path)
        first = parse_factored_character_batch(batch_paths[0], plan=plan)
        second = parse_factored_character_batch(batch_paths[1], plan=plan)
        self.assertEqual((first.character_start, len(first.characters)), (0, 2))
        self.assertEqual((second.character_start, len(second.characters)), (2, 1))
        replay = verify_factored_service_campaign(
            plan_path,
            batch_paths,
            parameters=self.parameters,
            expected_conrey_numbers=(2, 3, 4),
        )
        self.assertTrue(replay["passed"])
        self.assertEqual(replay["shared_frequency_records_replayed_once"], 128)

    def test_split_batch_plan_hash_tamper_fails_closed(self) -> None:
        plan_path = self.root / "plan.bin"
        batch_path = self.root / "batch.bin"
        write_factored_shared_plan(
            plan_path,
            q=5,
            conrey_numbers=(2, 4),
            parameters=self.parameters,
        )
        write_factored_character_batch(
            batch_path,
            plan_path=plan_path,
            conrey_numbers=(2, 4),
            character_start=0,
            batch_ordinal=0,
            campaign_batch_count=1,
        )
        raw = bytearray(batch_path.read_bytes())
        raw[INPUT_HEADER.size] ^= 1
        batch_path.write_bytes(raw)
        plan = parse_factored_shared_plan(plan_path)
        with self.assertRaisesRegex(FactoredSmallQError, "does not match"):
            parse_factored_character_batch(batch_path, plan=plan)

    def test_split_campaign_gap_fails_before_replay(self) -> None:
        plan_path = self.root / "plan.bin"
        batch_dir = self.root / "batches"
        record = write_factored_service_campaign(
            plan_path,
            batch_dir,
            q=5,
            conrey_numbers=(2, 3, 4),
            parameters=self.parameters,
            maximum_batch_characters=2,
        )
        second_path = Path(record["batches"][1]["path"])
        raw = bytearray(second_path.read_bytes())
        character_start_offset = INPUT_HEADER.size + 32
        struct.pack_into("<Q", raw, character_start_offset, 1)
        second_path.write_bytes(raw)
        with self.assertRaisesRegex(FactoredSmallQError, "contiguous"):
            verify_factored_service_campaign(
                plan_path,
                [Path(item["path"]) for item in record["batches"]],
                parameters=self.parameters,
            )

    def test_factored_cuda_and_dft_when_runner_is_supplied(self) -> None:
        runner = os.environ.get("TG_SMALLQ_CERTIFIED_RUNNER")
        if not runner:
            self.skipTest("set TG_SMALLQ_CERTIFIED_RUNNER to run the CUDA KAT")
        input_path = self.root / "factored-input.bin"
        output_path = self.root / "factored-output.bin"
        write_factored_seed_frame(
            input_path,
            q=5,
            conrey_numbers=(2, 4),
            parameters=self.parameters,
        )
        subprocess.run(
            [runner, "--iterations", "2", str(input_path), str(output_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = verify_factored_output_kat(
            input_path, output_path, parameters=self.parameters
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["independent_arb_values_checked"], 256)

    def test_factored_service_cuda_and_dft_when_runner_is_supplied(self) -> None:
        runner = os.environ.get("TG_SMALLQ_CERTIFIED_RUNNER")
        if not runner:
            self.skipTest("set TG_SMALLQ_CERTIFIED_RUNNER to run the CUDA service KAT")
        plan_path = self.root / "service-plan.bin"
        batch_dir = self.root / "service-batches"
        record = write_factored_service_campaign(
            plan_path,
            batch_dir,
            q=5,
            conrey_numbers=(2, 3, 4),
            parameters=self.parameters,
            maximum_batch_characters=2,
        )
        batch_paths = [Path(item["path"]) for item in record["batches"]]
        output_paths = [self.root / f"service-output-{index}.bin" for index in range(2)]
        command = [runner, "--iterations", "2", "--factored-service", str(plan_path)]
        for batch_path, output_path in zip(batch_paths, output_paths):
            command.extend((str(batch_path), str(output_path)))
        subprocess.run(command, check=True, capture_output=True, text=True)
        checked = 0
        for batch_path, output_path in zip(batch_paths, output_paths):
            result = verify_factored_service_output_kat(
                plan_path,
                batch_path,
                output_path,
                parameters=self.parameters,
            )
            self.assertTrue(result["passed"])
            checked += int(result["independent_arb_values_checked"])
        self.assertEqual(checked, 384)
        tampered = self.root / "service-output-tampered.bin"
        raw = bytearray(output_paths[0].read_bytes())
        raw[v2.OUTPUT_HEADER.size] ^= 1
        tampered.write_bytes(raw)
        with self.assertRaisesRegex(FactoredSmallQError, "identity/size"):
            verify_factored_service_output_kat(
                plan_path,
                batch_paths[0],
                tampered,
                parameters=self.parameters,
            )

    def test_factored_service_streaming_cuda_kat_when_forced(self) -> None:
        runner = os.environ.get("TG_SMALLQ_CERTIFIED_RUNNER")
        if not runner:
            self.skipTest("set TG_SMALLQ_CERTIFIED_RUNNER to run the streaming KAT")
        plan_path = self.root / "stream-plan.bin"
        batch_dir = self.root / "stream-batch"
        record = write_factored_service_campaign(
            plan_path,
            batch_dir,
            q=5,
            conrey_numbers=(2, 4),
            parameters=self.parameters,
            maximum_batch_characters=2,
        )
        batch_path = Path(record["batches"][0]["path"])
        output_path = self.root / "stream-output.bin"
        completed = subprocess.run(
            [
                runner,
                "--iterations",
                "2",
                "--shared-seed-chunk-records",
                "17",
                "--factored-service",
                str(plan_path),
                str(batch_path),
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn('"shared_plan_device_resident":false', completed.stdout)
        result = verify_factored_service_output_kat(
            plan_path,
            batch_path,
            output_path,
            parameters=self.parameters,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["independent_arb_values_checked"], 256)


if __name__ == "__main__":
    unittest.main()
