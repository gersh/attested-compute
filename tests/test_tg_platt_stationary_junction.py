# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest

from tg_verifier.platt_pt21_event_record import RECORD as EVENT_RECORD
from tg_verifier.platt_pt21_stationary_junction import (
    Candidate,
    CANDIDATE,
    FLINT_RELEASE,
    MAGIC,
    PREFIX,
    PT21StationaryJunctionError,
    RECORD_BYTES,
    RECORD_DIGEST_OFFSET,
    RECORD_DOMAIN,
    SAMPLE,
    candidate_list_sha256,
    parse_record,
    refinement_trace_sha256,
    replay,
    resolver_input_sha256,
)
from tg_verifier.platt_stationary_trace import (
    INTERPOLATION_PATCH_SHA256,
    RESOLUTION_DOMAIN,
    SCHEMA as TRACE_SCHEMA,
    UPSTREAM_COMMIT,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER_ENV = "TG_PLATT_STATIONARY_JUNCTION"
EVENT_RECORD_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-event-record/v1\0"
)
CPP_FIXTURE_HEX = (
    "5054323153544a3101000000900100000657d0b00000000000000000000000000200000002000000000000000000000004000000800000004000000040000000887700000000000001000000010000005f38f41feb45e8d4cb9ff031a5a8f7b5be3a729a2929cf2a0331b73330550be37c5f8e2911ac4cc35b2600cc18e21b1fb4d5d19cb9fe720eecaf9126cce4831e09c1d4a305c3f981bdc61b022614684b11187a0af28ac8233f438c6af4e810e181a331f7f29f17de65d41e95ed9a988ead3f561fa32117917139be441227b1b573c724c1b5a02c77da7a1fcb5bfa3e1361c3e50678fff5988c9766b1dbddb66db982a4c4aa0b34a0c902c09086f8ec88e0dfebaf91c844b7d29cd412a2cb1139a65c2326941852bb130e19b349e47f6302faa1c0f37eb4debf1e0cbb9d60e688a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a55a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a4ec4e772a9019a1b44237f464cd85cf6b04b1f05e76be43316f62a18d41e2678"
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _point(value: int) -> dict[str, object]:
    rational = {"denominator": 1, "numerator": value}
    return {"hi": rational, "lo": rational}


def _resolution(left: int) -> dict[str, object]:
    return {
        "lower_offset": {"denominator": 1, "numerator": left},
        "lower_value": _point(3),
        "midpoint_offset": {"denominator": 1, "numerator": left + 1},
        "midpoint_value": _point(-1),
        "outer_left_sample": left,
        "outer_right_sample": left + 2,
        "stream": "main",
        "upper_offset": {"denominator": 1, "numerator": left + 2},
        "upper_value": _point(3),
    }


def _candidate(left: int) -> Candidate:
    lower, upper = (-12_288, 12_288)
    edge = left - lower
    return Candidate(
        stream=1,
        left_sample=left,
        middle_sample=left + 1,
        right_sample=left + 2,
        nleft_units_per_slot=-edge,
        nright_units_per_slot=upper - lower - edge - 2,
        source_positive=1,
        strict_stat_pt=1,
        requires_adaptive_resolution=1,
        certified_multiplicity_slots=0,
        multiplicity_slots_if_resolved=2,
    )


def _sample_payload() -> bytes:
    radius = 2.0**-80
    values = [[3.0, 0.0, radius] for _ in range(25_741)]
    for left in (0, 10):
        base = left + 12_870
        values[base] = [3.0, 0.0, radius]
        values[base + 1] = [1.0, 0.0, radius]
        values[base + 2] = [3.0, 0.0, radius]
        values[base + 3] = [-100.0, 0.0, radius]
    return b"".join(SAMPLE.pack(*value) for value in values)


def _event_record(block: int, root: bytes) -> bytes:
    prefix = EVENT_RECORD.pack(
        b"PT21EVT1",
        1,
        EVENT_RECORD.size,
        block,
        0,
        25_741,
        1,
        0,
        0,
        2,
        0,
        0,
        2,
        0,
        0,
        2,
        0,
        2,
        0,
        0,
        0,
        0,
        0,
        0,
        root,
        bytes(32),
    )
    return (
        prefix[:160]
        + hashlib.sha256(EVENT_RECORD_DOMAIN + prefix[:160]).digest()
    )


def _evidence() -> tuple[
    bytes,
    bytes,
    bytes,
    list[Candidate],
    list[dict[str, object]],
    dict[str, object],
]:
    block = 17
    candidates = [_candidate(0), _candidate(10)]
    refinements: list[dict[str, object]] = []
    samples = _sample_payload()
    input_sha256 = resolver_input_sha256(
        samples, candidates, refinements
    ).hex()
    resolutions = [_resolution(0), _resolution(10)]
    resolution_sha256 = hashlib.sha256(
        RESOLUTION_DOMAIN + _canonical(resolutions)
    ).hexdigest()
    trace: dict[str, object] = {
        "accepted": True,
        "ambiguous_input_disks": 0,
        "candidate_count": 2,
        "error": "",
        "failure_flags": 0,
        "input_sha256": input_sha256,
        "interpolation_evaluations": 2,
        "interpolation_patch_sha256": INTERPOLATION_PATCH_SHA256,
        "maximum_depth": 64,
        "precision_bits": 128,
        "refinements_applied": 0,
        "replay_accepted": True,
        "required_sample_count": 25_741,
        "resolution_sha256": resolution_sha256,
        "schema": TRACE_SCHEMA,
        "semantic_status": {
            "analytic_turing_realization_proved": False,
            "flint_to_mathlib_realization_proved": False,
            "hardy_z_endpoint_realization_proved": False,
        },
        "stationary_resolutions": resolutions,
        "upstream_commit": UPSTREAM_COMMIT,
    }
    root = bytes.fromhex("31" * 32)
    event = _event_record(block, root)
    digests = (
        event[160:192],
        root,
        candidate_list_sha256(candidates),
        bytes.fromhex(input_sha256),
        refinement_trace_sha256(refinements),
        bytes.fromhex(resolution_sha256),
        hashlib.sha256(_canonical(trace) + b"\n").digest(),
        bytes.fromhex("a5" * 32),
        bytes.fromhex("5a" * 32),
    )
    prefix = PREFIX.pack(
        MAGIC,
        1,
        RECORD_BYTES,
        block,
        0,
        2,
        2,
        0,
        0,
        4,
        128,
        64,
        64,
        FLINT_RELEASE,
        0,
        1,
        1,
    )
    body = prefix + b"".join(digests)
    record = body + hashlib.sha256(RECORD_DOMAIN + body).digest()
    return record, event, samples, candidates, refinements, trace


class PT21StationaryJunctionTest(unittest.TestCase):
    def test_cpp_record_is_accepted_and_multiplicity_is_explicit(self) -> None:
        record = parse_record(bytes.fromhex(CPP_FIXTURE_HEX))
        self.assertEqual(record["block"], 2_966_443_782)
        self.assertEqual(record["candidate_count"], 2)
        self.assertEqual(record["resolution_count"], 2)
        self.assertEqual(record["resolved_multiplicity_slots"], 4)

    def test_independent_evidence_replay_and_mutations(self) -> None:
        record, event, samples, candidates, refinements, trace = _evidence()
        report = replay(
            record,
            event_record=event,
            sample_payload=samples,
            candidates=candidates,
            refinements=refinements,
            stationary_trace=trace,
            expected_resolver_sha256="a5" * 32,
            expected_flint_sha256="5a" * 32,
        )
        self.assertTrue(report["accepted"])
        self.assertEqual(report["resolved_multiplicity_slots"], 4)
        self.assertFalse(report["source_claim_ready"])

        changed_samples = bytearray(samples)
        changed_samples[0] ^= 1
        with self.assertRaisesRegex(
            PT21StationaryJunctionError, "resolver_input_sha256 differs"
        ):
            replay(
                record,
                event_record=event,
                sample_payload=bytes(changed_samples),
                candidates=candidates,
                refinements=refinements,
                stationary_trace=trace,
                expected_resolver_sha256="a5" * 32,
                expected_flint_sha256="5a" * 32,
            )

        with self.assertRaisesRegex(
            PT21StationaryJunctionError, "not canonical"
        ):
            replay(
                record,
                event_record=event,
                sample_payload=samples,
                candidates=list(reversed(candidates)),
                refinements=refinements,
                stationary_trace=trace,
                expected_resolver_sha256="a5" * 32,
                expected_flint_sha256="5a" * 32,
            )

        with self.assertRaisesRegex(
            PT21StationaryJunctionError, "event-scan rerun support"
        ):
            replay(
                record,
                event_record=event,
                sample_payload=samples,
                candidates=candidates,
                refinements=[
                    {
                        "sample_offset": 1,
                        "lower_arf_dump": "1 0",
                        "upper_arf_dump": "1 0",
                    }
                ],
                stationary_trace=trace,
                expected_resolver_sha256="a5" * 32,
                expected_flint_sha256="5a" * 32,
            )

        changed_event = _event_record(17, bytes.fromhex("32" * 32))
        with self.assertRaisesRegex(
            PT21StationaryJunctionError, "event_record_sha256 differs"
        ):
            replay(
                record,
                event_record=changed_event,
                sample_payload=samples,
                candidates=candidates,
                refinements=refinements,
                stationary_trace=trace,
                expected_resolver_sha256="a5" * 32,
                expected_flint_sha256="5a" * 32,
            )

        overclaim = copy.deepcopy(trace)
        overclaim["semantic_status"][
            "hardy_z_endpoint_realization_proved"
        ] = True
        with self.assertRaisesRegex(
            PT21StationaryJunctionError, "overclaims"
        ):
            replay(
                record,
                event_record=event,
                sample_payload=samples,
                candidates=candidates,
                refinements=refinements,
                stationary_trace=overclaim,
                expected_resolver_sha256="a5" * 32,
                expected_flint_sha256="5a" * 32,
            )

    def test_record_field_and_digest_mutations_fail_closed(self) -> None:
        record, *_ = _evidence()
        for offset in (0, 36, 48, 68, 112, 399):
            changed = bytearray(record)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(
                PT21StationaryJunctionError
            ):
                parse_record(bytes(changed))
        for offset, value in ((36, 1), (68, 1), (72, 0), (76, 0)):
            changed = bytearray(record)
            struct.pack_into("<I", changed, offset, value)
            changed[RECORD_DIGEST_OFFSET:] = hashlib.sha256(
                RECORD_DOMAIN + changed[:RECORD_DIGEST_OFFSET]
            ).digest()
            with self.subTest(forged_offset=offset), self.assertRaisesRegex(
                PT21StationaryJunctionError, "finite fields differ"
            ):
                parse_record(bytes(changed))

    def test_source_has_replay_seal_and_no_semantic_promotion(self) -> None:
        header = (
            ROOT
            / "gpu/include/sparkinterval/tg_platt_stationary_junction.hpp"
        ).read_text(encoding="utf-8")
        source = (
            ROOT / "reference/tg_platt_stationary_junction.cpp"
        ).read_text(encoding="utf-8")
        scanner = (
            ROOT / "gpu/platform/h100/h100_tg_platt_event_scan.cu"
        ).read_text(encoding="utf-8")
        self.assertIn("stationary_payload_sha256", scanner)
        self.assertIn("zero_merkle_levels", scanner)
        self.assertIn("next = zero_levels[level + 1U]", scanner)
        self.assertIn("payload_seal != replay.stationary_payload_sha256", source)
        self.assertIn("resolved_multiplicity_slots", header)
        self.assertIn("semantic_realization_flags", header)
        self.assertIn("resolver_replay_accepted", header)
        self.assertIn("higher_precision_containment_complete", header)
        self.assertNotIn("hardy_z_endpoint_realization_proved = true", source)

    def test_optional_cuda_flint_junction_and_mutations(self) -> None:
        runner_text = os.environ.get(RUNNER_ENV)
        default = (
            ROOT
            / "build/pt21-junction/"
            "sparkinterval-tg-platt-stationary-junction-benchmark"
        )
        runner = Path(runner_text) if runner_text else default
        if not runner.is_file():
            self.skipTest(f"junction runner is missing: {runner}")
        environment = {**os.environ}
        environment["LD_LIBRARY_PATH"] = (
            "/tmp/flint-3.6-install/lib:"
            + environment.get("LD_LIBRARY_PATH", "")
        )
        for mode in (
            "valid",
            "mutate-sample",
            "mutate-candidate-order",
            "mutate-root",
            "mutate-refinement",
        ):
            completed = subprocess.run(
                [str(runner), "--mode", mode, "--iterations", "1"],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            value = json.loads(completed.stdout)
            self.assertTrue(value["test_success"])
            self.assertFalse(value["hardy_z_endpoint_realization_proved"])
            self.assertFalse(value["analytic_turing_realization_proved"])
            if mode == "valid":
                self.assertEqual(value["accepted_records"], 3)
                self.assertGreater(value["junctions_per_second"], 0)
                self.assertGreater(value["cold_scanner_replay_seconds"], 0)
                self.assertGreater(value["warm_scanner_replay_seconds"], 0)
                self.assertEqual(value["record_hex"], CPP_FIXTURE_HEX)
                self.assertEqual(
                    value["first_interior_terminal_blocks"],
                    [0, 1_483_221_891, 2_966_443_782],
                )
            else:
                self.assertEqual(value["accepted_records"], 0)


if __name__ == "__main__":
    unittest.main()
