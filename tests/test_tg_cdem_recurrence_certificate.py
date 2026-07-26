#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the CDEM recurrence/source-realization handoff."""

from __future__ import annotations

import math
from pathlib import Path
import re
import unittest

from tg_verifier.cdem_chunk_replay import CdemChunkRecord
from tg_verifier.cdem_recurrence_certificate import (
    CdemRecurrenceCertificateError,
    render_lean_source,
    validate_certificate,
)


ROOT = Path(__file__).resolve().parents[1]
LEAN_SOURCE = (
    ROOT
    / "SparkInterval"
    / "TernaryGoldbach"
    / "CDEMAbelRecurrenceCertificate.lean"
)
SCALE = 10**18


def mobius(n: int) -> int:
    remaining = n
    factors = 0
    prime = 2
    while prime * prime <= remaining:
        if remaining % prime == 0:
            remaining //= prime
            factors += 1
            if remaining % prime == 0:
                return 0
        prime += 1
    if remaining > 1:
        factors += 1
    return -1 if factors % 2 else 1


def floor_state(K: int, n: int) -> int:
    return sum(mobius(d) * (n // d) for d in range(1, K + 1))


def floor_jump(K: int, n: int) -> int:
    return sum(mobius(d) for d in range(1, K + 1) if n % d == 0)


def error_state(K: int, n: int) -> int:
    return 0 if n == 0 else abs(1 - floor_state(K, n))


def sqrt_weight(n: int) -> int:
    required = (SCALE * SCALE + n - 1) // n
    root = math.isqrt(required)
    return root if root * root == required else root + 1


def chunk(K: int, low: int, high: int) -> CdemChunkRecord:
    signed = 0
    absolute = 0
    variation = 0
    for n in range(low, high + 1):
        increment = error_state(K, n) - error_state(K, n - 1)
        if increment > 0:
            signed += increment * ((SCALE + n - 1) // n)
        elif increment < 0:
            signed += increment * (SCALE // n)
        weight = sqrt_weight(n)
        absolute += abs(increment) * weight
        variation += abs(increment)
        assert SCALE * SCALE <= weight * weight * n
    return CdemChunkRecord(
        low,
        high,
        floor_state(K, low - 1),
        floor_state(K, high),
        signed,
        absolute,
        variation,
    )


class CdemRecurrenceCertificateTests(unittest.TestCase):
    def test_small_recurrence_and_directed_weights(self) -> None:
        K = 12
        for n in range(1, 80):
            self.assertEqual(
                floor_state(K, n) - floor_state(K, n - 1),
                floor_jump(K, n),
            )
        records = (chunk(K, 1, 23), chunk(K, 24, 57))
        certificate = validate_certificate(
            records,
            signed_numerator=sum(row.u_increment_upper for row in records),
            absolute_numerator=sum(row.v_increment_upper for row in records),
            source_upper=57,
            transcript_sha256="ab" * 32,
        )
        self.assertEqual(certificate.chunks, records)
        self.assertEqual(certificate.chunks[0].before, 0)
        self.assertEqual(certificate.chunks[0].after, records[1].before)

    def test_topology_state_and_reduction_tampering_fail_closed(self) -> None:
        first = chunk(10, 1, 12)
        second = chunk(10, 13, 25)
        valid = (first, second)
        signed = sum(row.u_increment_upper for row in valid)
        absolute = sum(row.v_increment_upper for row in valid)
        digest = "01" * 32

        mutations = (
            (
                "range",
                (
                    first,
                    CdemChunkRecord(
                        14,
                        second.high,
                        second.before,
                        second.after,
                        second.u_increment_upper,
                        second.v_increment_upper,
                        second.variation,
                    ),
                ),
                "continue the source range",
            ),
            (
                "state",
                (
                    first,
                    CdemChunkRecord(
                        second.low,
                        second.high,
                        second.before + 1,
                        second.after,
                        second.u_increment_upper,
                        second.v_increment_upper,
                        second.variation,
                    ),
                ),
                "continue the floor state",
            ),
        )
        for label, records, message in mutations:
            with self.subTest(label=label):
                with self.assertRaisesRegex(CdemRecurrenceCertificateError, message):
                    validate_certificate(
                        records,
                        signed_numerator=signed,
                        absolute_numerator=absolute,
                        source_upper=25,
                        transcript_sha256=digest,
                    )
        with self.assertRaisesRegex(
            CdemRecurrenceCertificateError, "signed chunk reduction"
        ):
            validate_certificate(
                valid,
                signed_numerator=signed - 1,
                absolute_numerator=absolute,
                source_upper=25,
                transcript_sha256=digest,
            )
        with self.assertRaisesRegex(
            CdemRecurrenceCertificateError, "absolute chunk reduction"
        ):
            validate_certificate(
                valid,
                signed_numerator=signed,
                absolute_numerator=absolute - 1,
                source_upper=25,
                transcript_sha256=digest,
            )

    def test_renderer_emits_only_arithmetic_certificate(self) -> None:
        # The generated Lean module is source-closed at the production
        # endpoint.  The compact arithmetic checker does not claim that these
        # deliberately synthetic totals realize the source recurrence; that
        # remains the separate `LocalSourceScaleEvidence` premise.
        records = (
            CdemChunkRecord(
                1,
                2_500_000_000,
                0,
                17,
                3,
                5,
                0,
            ),
            CdemChunkRecord(
                2_500_000_001,
                5_000_000_000,
                17,
                23,
                4,
                6,
                0,
            ),
        )
        certificate = validate_certificate(
            records,
            signed_numerator=sum(row.u_increment_upper for row in records),
            absolute_numerator=sum(row.v_increment_upper for row in records),
            source_upper=5_000_000_000,
            transcript_sha256="23" * 32,
        )
        source = render_lean_source(
            certificate,
            namespace="SparkInterval.Generated.CDEMFixture",
        )
        self.assertIn("theorem certificate_check", source)
        self.assertIn("by decide", source)
        self.assertIn('def transcriptSha256 : String :=', source)
        self.assertIn("signedUpper :=", source)
        self.assertIn("absoluteUpper :=", source)
        self.assertIn("`LocalSourceScaleEvidence`", source)
        self.assertNotIn("axiom ", source)
        self.assertNotIn("native_decide", source)

    def test_renderer_rejects_nonproduction_coverage(self) -> None:
        record = chunk(5, 1, 5)
        certificate = validate_certificate(
            (record,),
            signed_numerator=record.u_increment_upper,
            absolute_numerator=record.v_increment_upper,
            source_upper=5,
            transcript_sha256="34" * 32,
        )
        with self.assertRaisesRegex(
            CdemRecurrenceCertificateError,
            "does not end immediately after the source endpoint",
        ):
            render_lean_source(certificate)

    def test_lean_source_keeps_the_physical_edge_explicit(self) -> None:
        source = LEAN_SOURCE.read_text(encoding="utf-8")
        self.assertIn("theorem floorState_jump", source)
        self.assertIn("theorem floorSum_eq_floorState_cast", source)
        self.assertIn("structure LocalSourceScaleEvidence", source)
        self.assertIn("structure SourceScaleEvidence", source)
        self.assertIn("chunk.LocallyRealizes", source)
        self.assertIn("SqrtWeightValid", source)
        self.assertIn(
            "theorem scaledOutputClaim_of_checked_local_certificate", source
        )
        self.assertIn("theorem scaledOutputClaim_of_checked_certificate", source)
        self.assertIsNone(
            re.search(r"(?m)^\s*(?:private\s+)?axiom\s+", source)
        )
        self.assertIsNone(
            re.search(r"(?m)^\s*(?:private\s+)?theorem\b.*:=\s*by\s+native_decide", source)
        )
        self.assertNotIn("False.elim", source)

    def test_renderer_rejects_namespace_injection(self) -> None:
        record = chunk(5, 1, 5)
        certificate = validate_certificate(
            (record,),
            signed_numerator=record.u_increment_upper,
            absolute_numerator=record.v_increment_upper,
            source_upper=5,
            transcript_sha256="45" * 32,
        )
        with self.assertRaisesRegex(
            CdemRecurrenceCertificateError, "namespace is malformed"
        ):
            render_lean_source(certificate, namespace="Bad; #check False")


if __name__ == "__main__":
    unittest.main()
