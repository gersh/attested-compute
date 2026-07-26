# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Transcript-faithful CH25 A.7 literals for the Lean finite checker.

The retained A.7 artifact stores each leaf as exactly seven JSON fields::

    [edge_id, depth, index,
     norm_sq_upper_mantissa_base64url, norm_sq_upper_exponent,
     zeta_abs_lower_mantissa_base64url, zeta_abs_lower_exponent]

This module first delegates *all* artifact validation to the authoritative
structural parser in :mod:`tg_verifier.analytic`.  It then captures those same
bytes as immutable Python records and renders deterministic Lean literals.
Every rendered dyadic retains the source mantissa/exponent pair exactly.  The
Python record also exposes its canonical reduced ``Fraction``, while Lean's
``dyadicValue`` independently decodes the rendered pair to ``ℚ``.

This is deliberately not a FLINT replay and does not assert that a recorded
bound encloses zeta, its derivative, or the regularized logarithmic
derivative.  The production transcript is not read unless an explicit caller
supplies it.

The generated source uses the checked module
``SparkInterval.TernaryGoldbach.A7BoundaryCertificate`` and its exact literal
interface::

    structure DyadicLeaf where
      edgeId : Nat
      depth : Nat
      index : Nat
      normSqUpperMantissa : Nat
      normSqUpperExponent : Int
      zetaAbsLowerMantissa : Nat
      zetaAbsLowerExponent : Int

    structure Certificate where
      maxDepth : Nat
      leaves : List DyadicLeaf

    def Certificate.check (certificate : Certificate) : Bool

``Certificate.check`` rechecks exact dyadic-to-rational decoding, four-edge
gap-free coverage, positivity, and the strict ``(349 / 250)^2`` squared-norm
bound.  The generated transcript and leaf digests remain separate binding
constants for the signed execution boundary; a literal-only checker cannot
rediscover the omitted JSON bytes.

For a total byte-level Lean parser instead of generated source literals, see
``tg_verifier.a7_boundary_wire`` and
``SparkInterval.TernaryGoldbach.A7BoundaryWire``.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from typing import NoReturn

from .analytic import (
    A7_SCHEMA,
    AnalyticArtifactError,
    canonical_json_bytes,
    read_analytic_artifact_bytes,
    verify_a7_boundary_bytes,
)


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_LEAN_NAMESPACE_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z"
)
_BASE64URL_RE = re.compile(r"[A-Za-z0-9_-]+\Z")
_TARGET_SQ = Fraction(121_801, 62_500)
_EDGE_COUNT = 4
_MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
_MAX_LEAVES = 2_000_000
_MAX_DEPTH = 64
_MAX_DYADIC_BITS = 16_384
_MAX_DYADIC_EXPONENT = 16_384


class A7LeanCertificateError(ValueError):
    """An A.7 transcript cannot be represented by the Lean literal format."""


def _fail(message: str) -> NoReturn:
    raise A7LeanCertificateError(message)


def _exact_int(value: object, *, label: str, minimum: int | None = None) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{label} must be at least {minimum}")
    return value


def _decode_mantissa(value: object, *, label: str) -> tuple[str, int]:
    if type(value) is not str or _BASE64URL_RE.fullmatch(value) is None:
        _fail(f"{label} must be nonempty unpadded base64url")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as error:
        raise A7LeanCertificateError(
            f"{label} is not valid unpadded base64url"
        ) from error
    if not decoded or decoded[0] == 0:
        _fail(f"{label} is not a minimal positive big-endian integer")
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if canonical != value:
        _fail(f"{label} is not canonically encoded")
    mantissa = int.from_bytes(decoded, "big")
    if mantissa <= 0 or mantissa.bit_length() > _MAX_DYADIC_BITS:
        _fail(f"{label} must encode a bounded positive integer")
    return value, mantissa


def _dyadic_value(mantissa: int, exponent: int) -> Fraction:
    if exponent >= 0:
        return Fraction(mantissa << exponent, 1)
    return Fraction(mantissa, 1 << -exponent)


@dataclass(frozen=True)
class ExactDyadic:
    """One raw transcript dyadic and its canonical exact-rational meaning."""

    encoded_mantissa: str
    mantissa: int
    exponent: int
    value: Fraction


@dataclass(frozen=True)
class A7LeanLeaf:
    """One authoritative seven-field A.7 leaf."""

    edge_id: int
    depth: int
    index: int
    norm_sq_upper: ExactDyadic
    zeta_abs_lower: ExactDyadic


@dataclass(frozen=True)
class A7LeanCertificate:
    """Literal A.7 payload plus exact source-byte commitments."""

    transcript_sha256: str
    transcript_size_bytes: int
    leaves_sha256: str
    max_depth: int
    leaves: tuple[A7LeanLeaf, ...]


def _decode_dyadic(
    mantissa_value: object,
    exponent_value: object,
    *,
    label: str,
) -> ExactDyadic:
    encoded, mantissa = _decode_mantissa(
        mantissa_value, label=f"{label}.mantissa"
    )
    exponent = _exact_int(exponent_value, label=f"{label}.exponent")
    if not -_MAX_DYADIC_EXPONENT <= exponent <= _MAX_DYADIC_EXPONENT:
        _fail(f"{label}.exponent is outside the supported range")
    return ExactDyadic(
        encoded_mantissa=encoded,
        mantissa=mantissa,
        exponent=exponent,
        value=_dyadic_value(mantissa, exponent),
    )


def _decode_leaf(value: object, *, position: int) -> A7LeanLeaf:
    label = f"leaves[{position}]"
    if type(value) is not list or len(value) != 7:
        _fail(f"{label} must contain exactly the authoritative seven fields")
    edge_id = _exact_int(value[0], label=f"{label}.edge_id", minimum=0)
    if edge_id >= _EDGE_COUNT:
        _fail(f"{label}.edge_id must be between 0 and 3")
    depth = _exact_int(value[1], label=f"{label}.depth", minimum=0)
    index = _exact_int(value[2], label=f"{label}.index", minimum=0)
    if index >= 1 << depth:
        _fail(f"{label}.index is outside its dyadic depth")
    norm_sq_upper = _decode_dyadic(
        value[3], value[4], label=f"{label}.norm_sq_upper"
    )
    zeta_abs_lower = _decode_dyadic(
        value[5], value[6], label=f"{label}.zeta_abs_lower"
    )
    if not Fraction(0) < norm_sq_upper.value < _TARGET_SQ:
        _fail(f"{label}.norm_sq_upper is outside the strict accepted range")
    if zeta_abs_lower.value <= 0:
        _fail(f"{label}.zeta_abs_lower must be strictly positive")
    return A7LeanLeaf(
        edge_id=edge_id,
        depth=depth,
        index=index,
        norm_sq_upper=norm_sq_upper,
        zeta_abs_lower=zeta_abs_lower,
    )


def _raw_leaf(leaf: A7LeanLeaf) -> list[object]:
    return [
        leaf.edge_id,
        leaf.depth,
        leaf.index,
        leaf.norm_sq_upper.encoded_mantissa,
        leaf.norm_sq_upper.exponent,
        leaf.zeta_abs_lower.encoded_mantissa,
        leaf.zeta_abs_lower.exponent,
    ]


def _validate_dyadic(value: object, *, label: str) -> ExactDyadic:
    if not isinstance(value, ExactDyadic):
        _fail(f"{label} must be an ExactDyadic")
    checked = _decode_dyadic(
        value.encoded_mantissa, value.exponent, label=label
    )
    if type(value.mantissa) is not int or value.mantissa != checked.mantissa:
        _fail(f"{label}.mantissa differs from its source encoding")
    if not isinstance(value.value, Fraction) or value.value != checked.value:
        _fail(f"{label}.value differs from its exact dyadic decoding")
    return checked


def _validate_certificate(certificate: object) -> A7LeanCertificate:
    """Revalidate manually constructed or replaced records before rendering."""

    if not isinstance(certificate, A7LeanCertificate):
        _fail("certificate must be an A7LeanCertificate")
    if (
        type(certificate.transcript_sha256) is not str
        or _SHA256_RE.fullmatch(certificate.transcript_sha256) is None
    ):
        _fail("transcript_sha256 must be lowercase SHA-256 hex")
    _exact_int(
        certificate.transcript_size_bytes,
        label="transcript_size_bytes",
        minimum=1,
    )
    if certificate.transcript_size_bytes > _MAX_TRANSCRIPT_BYTES:
        _fail("transcript_size_bytes exceeds the format limit")
    if (
        type(certificate.leaves_sha256) is not str
        or _SHA256_RE.fullmatch(certificate.leaves_sha256) is None
    ):
        _fail("leaves_sha256 must be lowercase SHA-256 hex")
    max_depth = _exact_int(
        certificate.max_depth, label="max_depth", minimum=0
    )
    if max_depth > _MAX_DEPTH:
        _fail("max_depth exceeds the format limit")
    if (
        type(certificate.leaves) is not tuple
        or not 4 <= len(certificate.leaves) <= _MAX_LEAVES
    ):
        _fail("leaves must be a tuple covering all four edges")

    checked_leaves: list[A7LeanLeaf] = []
    keys: list[tuple[int, Fraction, Fraction]] = []
    for position, leaf in enumerate(certificate.leaves):
        label = f"leaves[{position}]"
        if not isinstance(leaf, A7LeanLeaf):
            _fail(f"{label} must be an A7LeanLeaf")
        edge_id = _exact_int(leaf.edge_id, label=f"{label}.edge_id", minimum=0)
        if edge_id >= _EDGE_COUNT:
            _fail(f"{label}.edge_id must be between 0 and 3")
        depth = _exact_int(leaf.depth, label=f"{label}.depth", minimum=0)
        if depth > max_depth:
            _fail(f"{label}.depth exceeds max_depth")
        index = _exact_int(leaf.index, label=f"{label}.index", minimum=0)
        if index >= 1 << depth:
            _fail(f"{label}.index is outside its dyadic depth")
        norm = _validate_dyadic(
            leaf.norm_sq_upper, label=f"{label}.norm_sq_upper"
        )
        zeta = _validate_dyadic(
            leaf.zeta_abs_lower, label=f"{label}.zeta_abs_lower"
        )
        if not Fraction(0) < norm.value < _TARGET_SQ:
            _fail(f"{label}.norm_sq_upper is outside the strict accepted range")
        if zeta.value <= 0:
            _fail(f"{label}.zeta_abs_lower must be strictly positive")
        checked = A7LeanLeaf(edge_id, depth, index, norm, zeta)
        checked_leaves.append(checked)
        denominator = 1 << depth
        keys.append(
            (
                edge_id,
                Fraction(index, denominator),
                Fraction(index + 1, denominator),
            )
        )

    if keys != sorted(keys):
        _fail("leaves are not in canonical edge/coordinate order")
    for edge_id in range(_EDGE_COUNT):
        cursor = Fraction(0)
        found = False
        for key_edge, lower, upper in keys:
            if key_edge != edge_id:
                continue
            found = True
            if lower != cursor:
                relation = "overlap" if lower < cursor else "gap"
                _fail(f"edge {edge_id} has a dyadic {relation} at {cursor}")
            cursor = upper
        if not found or cursor != 1:
            _fail(f"edge {edge_id} is not completely covered")

    raw_leaves = [_raw_leaf(leaf) for leaf in checked_leaves]
    digest = hashlib.sha256(canonical_json_bytes(raw_leaves)).hexdigest()
    if digest != certificate.leaves_sha256:
        _fail("leaves_sha256 differs from the seven-field literal leaves")
    return A7LeanCertificate(
        transcript_sha256=certificate.transcript_sha256,
        transcript_size_bytes=certificate.transcript_size_bytes,
        leaves_sha256=certificate.leaves_sha256,
        max_depth=max_depth,
        leaves=tuple(checked_leaves),
    )


def validate_certificate(certificate: object) -> A7LeanCertificate:
    """Public fail-closed validation for downstream literal/wire encoders."""

    return _validate_certificate(certificate)


def certificate_from_transcript_bytes(
    raw: bytes,
    *,
    require_retained_identity: bool = True,
) -> A7LeanCertificate:
    """Validate one immutable transcript snapshot and capture its Lean payload.

    Production callers should retain the safe default.  Tiny known-answer
    tests may explicitly pass ``require_retained_identity=False``.
    """

    try:
        receipt = verify_a7_boundary_bytes(
            raw, require_retained_identity=require_retained_identity
        )
    except AnalyticArtifactError as error:
        raise A7LeanCertificateError(
            f"A.7 transcript failed authoritative validation: {error}"
        ) from error
    try:
        document = json.loads(raw.decode("ascii"))
    except (AttributeError, UnicodeError, json.JSONDecodeError) as error:
        # The authoritative parser should make this branch unreachable, but
        # keep the conversion API fail-closed if that implementation changes.
        raise A7LeanCertificateError(
            "authoritatively accepted A.7 bytes could not be decoded"
        ) from error
    if type(document) is not dict or document.get("schema") != A7_SCHEMA:
        _fail("authoritatively accepted A.7 document has the wrong schema")
    raw_leaves = document.get("leaves")
    if type(raw_leaves) is not list:
        _fail("authoritatively accepted A.7 document has no leaf list")
    leaves = tuple(
        _decode_leaf(value, position=position)
        for position, value in enumerate(raw_leaves)
    )
    if receipt.get("accepted") is not True:
        _fail("authoritative A.7 validator did not return acceptance")
    if receipt.get("leaf_count") != len(leaves):
        _fail("authoritative A.7 leaf count differs during literal capture")
    leaves_sha256 = hashlib.sha256(canonical_json_bytes(raw_leaves)).hexdigest()
    if receipt.get("leaves_sha256") != leaves_sha256:
        _fail("authoritative A.7 leaf digest differs during literal capture")
    transcript_sha256 = hashlib.sha256(raw).hexdigest()
    if receipt.get("artifact_sha256") != transcript_sha256:
        _fail("authoritative A.7 transcript digest differs during literal capture")
    certificate = A7LeanCertificate(
        transcript_sha256=transcript_sha256,
        transcript_size_bytes=len(raw),
        leaves_sha256=leaves_sha256,
        max_depth=document["guards"]["max_depth"],
        leaves=leaves,
    )
    return _validate_certificate(certificate)


def certificate_from_transcript_file(
    path: str | Path,
    *,
    require_retained_identity: bool = True,
) -> A7LeanCertificate:
    """Read one bounded snapshot and convert it without reopening the path."""

    try:
        raw = read_analytic_artifact_bytes(path, label="A7 boundary artifact")
    except AnalyticArtifactError as error:
        raise A7LeanCertificateError(f"cannot read A.7 transcript: {error}") from error
    return certificate_from_transcript_bytes(
        raw, require_retained_identity=require_retained_identity
    )


def _lean_int(value: int) -> str:
    return str(value) if value >= 0 else f"({value})"


def _render_leaf(leaf: A7LeanLeaf) -> str:
    return (
        "    { edgeId := "
        f"{leaf.edge_id}\n"
        "      depth := "
        f"{leaf.depth}\n"
        "      index := "
        f"{leaf.index}\n"
        "      normSqUpperMantissa := "
        f"{leaf.norm_sq_upper.mantissa}\n"
        "      normSqUpperExponent := "
        f"{_lean_int(leaf.norm_sq_upper.exponent)}\n"
        "      zetaAbsLowerMantissa := "
        f"{leaf.zeta_abs_lower.mantissa}\n"
        "      zetaAbsLowerExponent := "
        f"{_lean_int(leaf.zeta_abs_lower.exponent)} }}"
    )


def render_lean_source(
    certificate: A7LeanCertificate,
    *,
    namespace: str = "SparkInterval.Generated.A7BoundaryProduction",
) -> str:
    """Render deterministic literal data and an ordinary ``decide`` theorem."""

    if (
        type(namespace) is not str
        or _LEAN_NAMESPACE_RE.fullmatch(namespace) is None
    ):
        _fail("generated Lean namespace is malformed")
    checked = _validate_certificate(certificate)
    leaves = ",\n".join(_render_leaf(leaf) for leaf in checked.leaves)
    return f"""\
/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

Generated from an authoritatively validated CH25 A.7 seven-field transcript.
This literal certificate checks finite dyadic coverage and stored rational
guards only; it does not claim FLINT-to-Mathlib analytic realization.
-/

import SparkInterval.TernaryGoldbach.A7BoundaryCertificate

namespace {namespace}

open SparkInterval.TernaryGoldbach.A7BoundaryCertificate

def transcriptSha256 : String :=
  "{checked.transcript_sha256}"

def transcriptSizeBytes : Nat :=
  {checked.transcript_size_bytes}

def leavesSha256 : String :=
  "{checked.leaves_sha256}"

set_option maxRecDepth 1000000 in
def certificate : Certificate := {{
  maxDepth := {checked.max_depth}
  leaves := [
{leaves}
  ]
}}

set_option maxHeartbeats 0 in
set_option maxRecDepth 1000000 in
theorem certificate_check : certificate.check = true := by decide

#print axioms certificate_check

end {namespace}
"""


__all__ = [
    "A7LeanCertificate",
    "A7LeanCertificateError",
    "A7LeanLeaf",
    "ExactDyadic",
    "certificate_from_transcript_bytes",
    "certificate_from_transcript_file",
    "render_lean_source",
    "validate_certificate",
]
