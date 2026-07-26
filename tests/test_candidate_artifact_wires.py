# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded Python/Lean known answers for the two candidate artifact wires."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from tg_verifier.affine_guard_certificate import FixedShardPlan
from tg_verifier.campaign_io import atomic_write_json
from tg_verifier.hurst_candidate_artifact import (
    ARTIFACT_HEADER as HURST_HEADER,
    HurstCandidateArtifactError,
    HurstCandidateBlock,
    HurstCandidateCertificate,
    HurstCandidateGuard,
    HurstCandidateState,
    ZERO_STATE,
    arithmetic_check as hurst_arithmetic_check,
    candidate_from_replayed_campaign,
    candidate_manifest as hurst_manifest,
    decode_candidate as decode_hurst,
    encode_candidate as encode_hurst,
    require_semantic_realization as require_hurst_realization,
)
from tg_verifier.prop1224_candidate_artifact import (
    ARTIFACT_HEADER as PROP1224_HEADER,
    Prop1224CandidateArtifactError,
    Prop1224CandidateCertificate,
    Prop1224CandidateShard,
    arithmetic_check as prop1224_arithmetic_check,
    candidate_from_verified_report,
    candidate_manifest as prop1224_manifest,
    decode_candidate as decode_prop1224,
    encode_candidate as encode_prop1224,
    require_semantic_realization as require_prop1224_realization,
)


PROP1224_KAT_SHA256 = (
    "9507c40bd8e61773be8a5e0ce88daece4b560a67fce8502070d1e7f2ba30b064"
)
HURST_KAT_SHA256 = (
    "23b334b8eb33b33618417781a11fea97d2bb4cf8678517d5bc7218aa0b2f4b37"
)


class Prop1224CandidateWireTest(unittest.TestCase):
    def certificate(self) -> Prop1224CandidateCertificate:
        return Prop1224CandidateCertificate(
            0,
            3_389_047_618,
            (Prop1224CandidateShard(0, 3_389_047_618),),
        )

    def test_cross_language_known_answer_and_round_trip(self) -> None:
        raw = encode_prop1224(self.certificate())
        self.assertTrue(raw.startswith(PROP1224_HEADER))
        self.assertEqual(len(raw), 317)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), PROP1224_KAT_SHA256)
        self.assertEqual(decode_prop1224(raw), self.certificate())
        self.assertTrue(prop1224_arithmetic_check(decode_prop1224(raw)))

    def test_strict_frame_and_count(self) -> None:
        raw = encode_prop1224(self.certificate())
        with self.assertRaises(Prop1224CandidateArtifactError):
            decode_prop1224(raw + b"\0")
        count_offset = len(PROP1224_HEADER) + 64
        hostile = (
            raw[:count_offset]
            + (1_000_001).to_bytes(4, "little")
            + raw[count_offset + 4 :]
        )
        with self.assertRaises(Prop1224CandidateArtifactError):
            decode_prop1224(hostile)

    def test_verified_fixed_plan_conversion(self) -> None:
        plan = FixedShardPlan.from_ranges(
            algorithm="bounded-wire-test",
            state_dimension=1,
            ranges=((0, 100), (100, 3_389_047_618)),
        )
        report = {
            "all_fixed_plan_receipts_present": True,
            "final_state": [3_389_047_618],
            "kind": "sparkinterval.azure.prop1224-full-merge-report.v1",
            "leaf_count": 2,
            "plan_sha256": plan.plan_sha256,
            "root_state": [0],
            "schema_version": 1,
        }
        certificate = candidate_from_verified_report(report, plan=plan)
        self.assertTrue(prop1224_arithmetic_check(certificate))
        self.assertEqual(
            [(item.lower, item.upper) for item in certificate.shards],
            [(0, 100), (100, 3_389_047_618)],
        )

    def test_manifest_is_explicitly_nonsemantic(self) -> None:
        raw = encode_prop1224(self.certificate())
        manifest = prop1224_manifest("candidate/prop1224.bin", raw)
        self.assertFalse(manifest["semantic_closure"])
        self.assertEqual(manifest["artifact"]["sha256"], hashlib.sha256(raw).hexdigest())
        with self.assertRaisesRegex(
            Prop1224CandidateArtifactError, "factorization"
        ):
            require_prop1224_realization(raw)


class HurstCandidateWireTest(unittest.TestCase):
    def certificate(self) -> HurstCandidateCertificate:
        delta = HurstCandidateState(-1, 2, -3, 4)
        return HurstCandidateCertificate(
            1,
            10_000_000_000_000_001,
            ZERO_STATE,
            delta,
            (
                HurstCandidateBlock(
                    1,
                    10_000_000_000_000_001,
                    delta,
                    HurstCandidateGuard(ZERO_STATE, ZERO_STATE),
                ),
            ),
        )

    def test_cross_language_known_answer_and_round_trip(self) -> None:
        raw = encode_hurst(self.certificate())
        self.assertTrue(raw.startswith(HURST_HEADER))
        self.assertEqual(len(raw), 1009)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), HURST_KAT_SHA256)
        self.assertEqual(decode_hurst(raw), self.certificate())
        self.assertTrue(hurst_arithmetic_check(decode_hurst(raw)))

    def test_rejects_negative_zero_unknown_sign_and_suffix(self) -> None:
        raw = bytearray(encode_hurst(self.certificate()))
        root_offset = len(HURST_HEADER) + 64
        raw[root_offset] = 1
        with self.assertRaises(HurstCandidateArtifactError):
            decode_hurst(bytes(raw))
        raw[root_offset] = 2
        with self.assertRaises(HurstCandidateArtifactError):
            decode_hurst(bytes(raw))
        with self.assertRaises(HurstCandidateArtifactError):
            decode_hurst(encode_hurst(self.certificate()) + b"\0")

    def test_conversion_uses_replayed_plan_and_derived_chain(self) -> None:
        plan = FixedShardPlan.from_ranges(
            algorithm="bounded-wire-test",
            state_dimension=4,
            ranges=((1, 100), (100, 10_000_000_000_000_001)),
        )
        first_delta = [1, 50, -7, 9]
        second_delta = [-2, 70, -3, 8]
        final_state = (-1, 120, -10, 17)
        derived = {
            "entries": [
                {
                    "delta": first_delta,
                    "incoming": [0, 0, 0, 0],
                    "index": 0,
                    "lower": 1,
                    "outgoing": first_delta,
                    "upper": 100,
                },
                {
                    "delta": second_delta,
                    "incoming": first_delta,
                    "index": 1,
                    "lower": 100,
                    "outgoing": list(final_state),
                    "upper": 10_000_000_000_000_001,
                },
            ],
            "final_state": list(final_state),
            "plan_sha256": plan.plan_sha256,
            "root_state": [0, 0, 0, 0],
        }
        checked = SimpleNamespace(
            mode="full_source",
            complete=True,
            full_source_range=True,
            source_residuals_replayed=True,
            final_state=final_state,
            certificate_root_sha256="a" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            atomic_write_json(campaign / "shard-plan.json", plan.to_dict())
            atomic_write_json(campaign / "derived-inputs.json", derived)
            with mock.patch(
                "tg_verifier.hurst_candidate_artifact.verify_campaign",
                return_value=checked,
            ):
                certificate = candidate_from_replayed_campaign(campaign)
        self.assertTrue(hurst_arithmetic_check(certificate))
        self.assertEqual(certificate.final_state, HurstCandidateState(*final_state))

    def test_manifest_is_explicitly_nonsemantic(self) -> None:
        raw = encode_hurst(self.certificate())
        manifest = hurst_manifest("candidate/hurst.bin", raw)
        self.assertFalse(manifest["semantic_closure"])
        self.assertEqual(manifest["artifact"]["sha256"], hashlib.sha256(raw).hexdigest())
        with self.assertRaisesRegex(HurstCandidateArtifactError, "Möbius"):
            require_hurst_realization(raw)


if __name__ == "__main__":
    unittest.main()
