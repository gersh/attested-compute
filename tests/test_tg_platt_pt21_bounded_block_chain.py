# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from tg_verifier.platt_pt21_bounded_block_chain import (
    DIRECT_MAIN_EVENTS,
    MAIN_SLOTS,
    PT21BoundedBlockChainError,
    RESOLVED_MULTIPLICITY_SLOTS,
    STATIONARY_CANDIDATES,
    run_bounded_block_chain,
    synthetic_candidates,
    synthetic_required_packet,
    synthetic_samples,
    verify_predecessor_commitment,
    verify_retained_chain,
)
from tg_verifier.platt_pt21_native_finalizer import (
    PT21NativeFinalizerError,
    encode_block_record,
    parse_block_record,
)
from tg_verifier.platt_required_sign_packet import (
    HEADER,
    REQUIRED_COUNT,
    SAMPLE,
)


ROOT = Path(__file__).resolve().parents[1]


class PT21BoundedBlockChainPureTest(unittest.TestCase):
    def test_synthetic_wire_is_explicit_stable_and_has_two_candidates(
        self,
    ) -> None:
        samples, signs = synthetic_samples()
        packet = synthetic_required_packet()
        self.assertEqual(len(samples), REQUIRED_COUNT * SAMPLE.size)
        self.assertEqual(
            hashlib.sha256(samples).hexdigest(),
            "fb4b0b0a510b9061fd4e0ee942d20f58e3956b6b12770205e1eeb7489d3c84b0",
        )
        self.assertEqual(
            packet[HEADER.size : HEADER.size + len(samples)], samples
        )
        self.assertEqual(
            packet[HEADER.size + len(samples) :],
            signs,
        )
        candidates = synthetic_candidates()
        self.assertEqual(len(candidates), STATIONARY_CANDIDATES)
        self.assertEqual(
            sum(candidate.multiplicity_slots_if_resolved for candidate in candidates),
            RESOLVED_MULTIPLICITY_SLOTS,
        )
        self.assertEqual(
            MAIN_SLOTS,
            DIRECT_MAIN_EVENTS + RESOLVED_MULTIPLICITY_SLOTS,
        )


class PT21BoundedBlockChainNativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="pt21-bounded-chain-test-"
        )
        build = ROOT / "build"
        cls.junction = Path(
            os.environ.get(
                "TG_PLATT_STATIONARY_JUNCTION",
                build
                / "pt21-junction"
                / "sparkinterval-tg-platt-stationary-junction-benchmark",
            )
        )
        cls.turing = Path(
            os.environ.get(
                "TG_PLATT_PT21_TURING_INPUTS",
                build
                / "tg-production-kat"
                / "sparkinterval-tg-platt-pt21-turing-inputs",
            )
        )
        cls.finalizer = Path(
            os.environ.get(
                "TG_PLATT_PT21_NATIVE_FINALIZER",
                build
                / "platt-fused"
                / "sparkinterval-tg-platt-pt21-native-finalizer",
            )
        )
        supplied_flint = os.environ.get("TG_PLATT_FLINT_LIBRARY")
        if supplied_flint:
            cls.flint = Path(supplied_flint).resolve()
        else:
            candidates = sorted(
                Path("/tmp/flint-3.6-install/lib").glob(
                    "libflint.so.*.*.*"
                )
            )
            cls.flint = candidates[-1] if candidates else Path("/missing")
        missing = [
            path
            for path in (
                cls.junction,
                cls.turing,
                cls.finalizer,
                cls.flint,
            )
            if not path.is_file()
        ]
        if missing:
            cls.temporary.cleanup()
            raise unittest.SkipTest(
                "bounded CUDA/FLINT chain executables are missing: "
                + ", ".join(map(str, missing))
            )
        cls.chain = run_bounded_block_chain(
            junction_executable=cls.junction,
            turing_executable=cls.turing,
            flint_library=cls.flint,
            finalizer_executable=cls.finalizer,
            output_directory=Path(cls.temporary.name),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def identities(self) -> dict[str, str]:
        report = self.chain.report
        return {
            "junction_executable_sha256": str(
                report["junction_executable_sha256"]
            ),
            "turing_executable_sha256": str(
                report["turing_executable_sha256"]
            ),
            "flint_sha256": str(report["flint_library_sha256"]),
            "adapter_sources_sha256": str(
                report["adapter_sources_sha256"]
            ),
            "finalizer_sha256": str(report["native_finalizer_sha256"]),
        }

    def verify(self, **changes: bytes) -> dict[str, int | str | bool]:
        values = {
            "event_record": self.chain.event_record,
            "junction_record": self.chain.stationary_junction_record,
            "required_packet": self.chain.required_packet,
            "stationary_trace": self.chain.stationary_trace,
            "turing_inputs": self.chain.turing_inputs,
            "source_trace": self.chain.source_trace,
            "block_artifact": self.chain.block_artifact,
            "block_record": self.chain.block_record,
            **changes,
            **self.identities(),
        }
        return verify_retained_chain(**values)

    def test_real_cuda_flint_turing_and_native_chain_closes(self) -> None:
        report = self.chain.report
        self.assertTrue(report["accepted"])
        self.assertTrue(report["synthetic_finite_values"])
        self.assertTrue(report["cuda_event_scanner_executed"])
        self.assertTrue(report["flint_stationary_resolver_executed"])
        self.assertTrue(report["arb_interval_arithmetic_executed"])
        self.assertTrue(report["native_finalizer_replayed"])
        self.assertEqual(report["direct_main_events"], DIRECT_MAIN_EVENTS)
        self.assertEqual(
            report["resolved_stationary_multiplicity_slots"],
            RESOLVED_MULTIPLICITY_SLOTS,
        )
        self.assertEqual(report["main_slots"], MAIN_SLOTS)
        self.assertEqual(report["count_gap"], MAIN_SLOTS)
        self.assertFalse(report["hardy_z_endpoint_realization_proved"])
        self.assertFalse(report["flint_to_mathlib_realization_proved"])
        self.assertFalse(report["main_multiplicity_realization_proved"])
        self.assertFalse(report["analytic_turing_realization_proved"])
        self.assertFalse(report["source_claim_ready"])
        replayed = self.verify()
        self.assertTrue(replayed["accepted"])
        self.assertEqual(replayed["main_slots"], MAIN_SLOTS)

    def test_every_predecessor_commitment_mutation_fails(self) -> None:
        fields = {
            "event_record": "event_record",
            "junction_record": "stationary_junction_record",
            "required_packet": "required_packet",
            "stationary_trace": "stationary_trace",
            "turing_inputs": "turing_inputs",
        }
        for field, attribute in fields.items():
            raw = bytearray(getattr(self.chain, attribute))
            raw[len(raw) // 2] ^= 1
            arguments = {
                "block_record": self.chain.block_record,
                "event_record": self.chain.event_record,
                "junction_record": self.chain.stationary_junction_record,
                "required_packet": self.chain.required_packet,
                "stationary_trace": self.chain.stationary_trace,
                "turing_inputs": self.chain.turing_inputs,
                **self.identities(),
            }
            arguments[field] = bytes(raw)
            with self.subTest(field=field), self.assertRaisesRegex(
                PT21BoundedBlockChainError,
                "predecessor commitment differs",
            ):
                verify_predecessor_commitment(**arguments)

        for identity in self.identities():
            arguments = {
                "block_record": self.chain.block_record,
                "event_record": self.chain.event_record,
                "junction_record": self.chain.stationary_junction_record,
                "required_packet": self.chain.required_packet,
                "stationary_trace": self.chain.stationary_trace,
                "turing_inputs": self.chain.turing_inputs,
                **self.identities(),
            }
            arguments[identity] = "01" * 32
            with self.subTest(identity=identity), self.assertRaisesRegex(
                PT21BoundedBlockChainError,
                "predecessor commitment differs",
            ):
                verify_predecessor_commitment(**arguments)

    def test_stationary_turing_artifact_and_block_mutations_fail(self) -> None:
        changed_event = bytearray(self.chain.event_record)
        changed_event[24] ^= 1
        with self.assertRaises(PT21BoundedBlockChainError):
            self.verify(event_record=bytes(changed_event))

        changed_junction = bytearray(self.chain.stationary_junction_record)
        changed_junction[48] ^= 1
        with self.assertRaises(PT21BoundedBlockChainError):
            self.verify(junction_record=bytes(changed_junction))

        turing = json.loads(self.chain.turing_inputs)
        turing["required_sign_packet_sha256"] = "01" * 32
        changed_turing = (
            json.dumps(turing, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
        )
        with self.assertRaises(PT21BoundedBlockChainError):
            self.verify(turing_inputs=changed_turing)

        changed_artifact = bytearray(self.chain.block_artifact)
        changed_artifact[len(changed_artifact) // 2] ^= 1
        with self.assertRaises(PT21BoundedBlockChainError):
            self.verify(block_artifact=bytes(changed_artifact))

        changed_record = bytearray(self.chain.block_record)
        changed_record[-1] ^= 1
        with self.assertRaises(PT21BoundedBlockChainError):
            self.verify(block_record=bytes(changed_record))

    def test_forged_stationary_count_cannot_break_multiplicity_link(self) -> None:
        parsed = parse_block_record(self.chain.block_record, expected_block=0)
        forged = encode_block_record(
            block=parsed.block,
            lower_count=parsed.lower_count,
            upper_count=parsed.upper_count,
            main_slots=parsed.main_slots,
            stationary_resolution_count=1,
            sparse_refinement_count=parsed.sparse_refinement_count,
            initial_ambiguous_count=parsed.initial_ambiguous_count,
            invalid_disk_count=parsed.invalid_disk_count,
            unresolved_disk_count=parsed.unresolved_disk_count,
            unresolved_stationary_count=parsed.unresolved_stationary_count,
            turing_failure_count=parsed.turing_failure_count,
            replay_failure_count=parsed.replay_failure_count,
            source_height_count=parsed.source_height_count,
            source_height_slots_from_lower=parsed.source_height_slots_from_lower,
            required_packet_sha256=parsed.required_packet_sha256,
            source_trace_sha256=parsed.source_trace_sha256,
            block_artifact_sha256=parsed.block_artifact_sha256,
            stationary_trace_sha256=parsed.stationary_trace_sha256,
            sparse_refinement_sha256=None,
            producer_commitment_sha256=parsed.producer_commitment_sha256,
        )
        with self.assertRaisesRegex(
            PT21BoundedBlockChainError,
            "stationary multiplicity",
        ):
            self.verify(block_record=forged)

    def test_native_shard_archive_mutation_fails_replay(self) -> None:
        archive = bytearray(self.chain.shard_archive)
        archive[len(archive) // 2] ^= 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changed.bin"
            path.write_bytes(archive)
            report = self.chain.report
            with self.assertRaises(PT21NativeFinalizerError):
                from tg_verifier.platt_pt21_native_finalizer import replay_shard

                replay_shard(
                    path,
                    expected_worker_sha256=str(
                        report["chain_commitment_sha256"]
                    ),
                    expected_plan_sha256=None,
                    expected_prefix_sha256=None,
                    allow_bounded_test=True,
                )


if __name__ == "__main__":
    unittest.main()
