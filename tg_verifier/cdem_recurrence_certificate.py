"""Compact Lean-certificate materialization for the CDEM Abel transcript.

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

The production transcript contains 1,000 inclusive chunk rows.  This module
turns those rows into the literal ``Certificate`` consumed by
``CDEMAbelRecurrenceCertificate.lean``.  Lean's ordinary ``decide`` checks
coverage, incoming-state continuity, and both integer reductions.

The generated theorem deliberately does *not* construct
``LocalSourceScaleEvidence``.  Local recurrence/fold realization remains the
physical/compiler boundary that a reviewed trusted-compute invocation must
supply.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable, NoReturn

from .cdem_chunk_replay import (
    CDEM_PRODUCTION_N,
    CdemChunkRecord,
    parse_cdem_production_chunks,
)
from .evidence import CDEM_U_TARGET, CDEM_V_TARGET


class CdemRecurrenceCertificateError(RuntimeError):
    """The compact recurrence certificate was malformed or incomplete."""


def _fail(message: str) -> NoReturn:
    raise CdemRecurrenceCertificateError(message)


LEAN_NAMESPACE_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z"
)


@dataclass(frozen=True)
class CdemRecurrenceCertificate:
    """The kernel-checkable arithmetic portion of one CDEM transcript."""

    signed_numerator: int
    absolute_numerator: int
    chunks: tuple[CdemChunkRecord, ...]
    transcript_sha256: str

    @property
    def signed_total(self) -> int:
        return sum(chunk.u_increment_upper for chunk in self.chunks)

    @property
    def absolute_total(self) -> int:
        return sum(chunk.v_increment_upper for chunk in self.chunks)


def validate_certificate(
    records: Iterable[CdemChunkRecord],
    *,
    signed_numerator: int,
    absolute_numerator: int,
    source_upper: int,
    transcript_sha256: str,
) -> CdemRecurrenceCertificate:
    """Validate the same arithmetic topology checked by the Lean certificate.

    This Python pass is a generator preflight, not the proof.  The generated
    module repeats these checks with ordinary kernel reduction.
    """

    if (
        isinstance(signed_numerator, bool)
        or not isinstance(signed_numerator, int)
        or signed_numerator < 0
    ):
        _fail("signed numerator must be a natural number")
    if (
        isinstance(absolute_numerator, bool)
        or not isinstance(absolute_numerator, int)
        or absolute_numerator < 0
    ):
        _fail("absolute numerator must be a natural number")
    if (
        isinstance(source_upper, bool)
        or not isinstance(source_upper, int)
        or source_upper < 1
    ):
        _fail("source upper endpoint must be positive")
    if re.fullmatch(r"[0-9a-f]{64}", transcript_sha256) is None:
        _fail("transcript digest must be lowercase SHA-256")

    chunks = tuple(records)
    if not chunks:
        _fail("recurrence certificate must contain at least one chunk")
    next_low = 1
    next_before = 0
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, CdemChunkRecord):
            _fail(f"chunk {index} is not a CdemChunkRecord")
        fields = (
            chunk.low,
            chunk.high,
            chunk.before,
            chunk.after,
            chunk.u_increment_upper,
            chunk.v_increment_upper,
            chunk.variation,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in fields):
            _fail(f"chunk {index} contains a non-integer field")
        if chunk.low != next_low:
            _fail(f"chunk {index} does not continue the source range")
        if chunk.low > chunk.high or chunk.high > source_upper:
            _fail(f"chunk {index} has an invalid inclusive interval")
        if chunk.before != next_before:
            _fail(f"chunk {index} does not continue the floor state")
        if chunk.v_increment_upper < 0:
            _fail(f"chunk {index} has a negative absolute upper total")
        next_low = chunk.high + 1
        next_before = chunk.after
    if next_low != source_upper + 1:
        _fail("chunk chain does not end immediately after the source endpoint")

    certificate = CdemRecurrenceCertificate(
        signed_numerator=signed_numerator,
        absolute_numerator=absolute_numerator,
        chunks=chunks,
        transcript_sha256=transcript_sha256,
    )
    if certificate.signed_total > signed_numerator:
        _fail("signed chunk reduction exceeds the returned numerator")
    if certificate.absolute_total > absolute_numerator:
        _fail("absolute chunk reduction exceeds the returned numerator")
    return certificate


def certificate_from_production_transcript(
    transcript: bytes | str,
) -> CdemRecurrenceCertificate:
    """Parse the exact production transcript and construct its Lean payload."""

    if isinstance(transcript, bytes):
        raw = transcript
        try:
            text = raw.decode("ascii")
        except UnicodeError as error:
            raise CdemRecurrenceCertificateError(
                "production transcript is not ASCII"
            ) from error
    elif isinstance(transcript, str):
        text = transcript
        try:
            raw = text.encode("ascii")
        except UnicodeError as error:
            raise CdemRecurrenceCertificateError(
                "production transcript is not ASCII"
            ) from error
    else:
        _fail("production transcript must be bytes or text")

    records = parse_cdem_production_chunks(text)
    return validate_certificate(
        records,
        signed_numerator=CDEM_U_TARGET,
        absolute_numerator=CDEM_V_TARGET,
        source_upper=CDEM_PRODUCTION_N,
        transcript_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _lean_chunk(chunk: CdemChunkRecord) -> str:
    return (
        "    { low := "
        f"{chunk.low}\n"
        "      high := "
        f"{chunk.high}\n"
        "      before := "
        f"{chunk.before}\n"
        "      after := "
        f"{chunk.after}\n"
        "      signedUpper := "
        f"{chunk.u_increment_upper}\n"
        "      absoluteUpper := "
        f"{chunk.v_increment_upper} }}"
    )


def render_lean_source(
    certificate: CdemRecurrenceCertificate,
    *,
    namespace: str = "SparkInterval.Generated.CDEMAbelProduction",
) -> str:
    """Render literal chunks plus an ordinary kernel-checked arithmetic proof."""

    if LEAN_NAMESPACE_RE.fullmatch(namespace) is None:
        _fail("generated Lean namespace is malformed")
    checked = validate_certificate(
        certificate.chunks,
        signed_numerator=certificate.signed_numerator,
        absolute_numerator=certificate.absolute_numerator,
        # The imported Lean checker is intentionally source-closed at the
        # production endpoint.  Rendering a shorter fixture would emit a
        # false `certificate_check` theorem, even if that fixture were
        # internally gap-free.
        source_upper=CDEM_PRODUCTION_N,
        transcript_sha256=certificate.transcript_sha256,
    )
    chunks = ",\n".join(_lean_chunk(chunk) for chunk in checked.chunks)
    return f"""\
/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate

/-! Generated compact arithmetic certificate for the reviewed CDEM Abel
transcript.  This file proves topology and integer reduction only; the
registered physical boundary must separately supply
`LocalSourceScaleEvidence`.
Do not edit by hand. -/

namespace {namespace}

open SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate

def transcriptSha256 : String :=
  "{checked.transcript_sha256}"

set_option maxRecDepth 1000000 in
def certificate : Certificate := {{
  signedNumerator := {checked.signed_numerator}
  absoluteNumerator := {checked.absolute_numerator}
  chunks := [
{chunks}
  ]
}}

set_option maxHeartbeats 0 in
set_option maxRecDepth 1000000 in
theorem certificate_check : certificate.check = true := by decide

#print axioms certificate_check

end {namespace}
"""


__all__ = [
    "CdemRecurrenceCertificate",
    "CdemRecurrenceCertificateError",
    "certificate_from_production_transcript",
    "render_lean_source",
    "validate_certificate",
]
