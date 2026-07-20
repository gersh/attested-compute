"""Full external FLINT/Arb replay for the CH25 Lemma A.7 boundary.

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

The structural checker in :mod:`tg_verifier.analytic` proves that the
retained dyadic leaves form a gap-free cover of all four rectangle edges.
This module additionally recomputes the zeta jet and the norm bound on every
accepted leaf with a pinned python-flint/FLINT release.  It deliberately does
not call this an ordinary-kernel Lean proof: FLINT's analytic semantics and a
bridge to Mathlib remain outside Lean's trusted kernel.
"""

from __future__ import annotations

import base64
from fractions import Fraction
import hashlib
import importlib
import json
from pathlib import Path
from time import perf_counter_ns
from typing import Any, NoReturn

from .analytic import (
    AnalyticArtifactError,
    canonical_json_bytes,
    read_analytic_artifact_bytes,
    verify_a7_boundary_bytes,
)


EXPECTED_PYTHON_FLINT = "0.9.0"
EXPECTED_FLINT = "3.6.0"
EXPECTED_FLINT_RELEASE = 30_600
SERIES_LENGTH = 2
SERIES_CAP = 4
TARGET_SQ = Fraction(121_801, 62_500)


class A7FlintReplayError(RuntimeError):
    """The external FLINT replay was unavailable or failed closed."""


def _fail(message: str) -> NoReturn:
    raise A7FlintReplayError(message)


def _load_flint() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        module = importlib.import_module("flint")
        acb = module.acb
        acb_series = module.acb_series
        arb = module.arb
        ctx = module.ctx
        fmpq = module.fmpq
    except (ImportError, AttributeError) as error:
        raise A7FlintReplayError(
            "python-flint==0.9.0 (bundling FLINT 3.6.0) is required for "
            "the full A.7 replay"
        ) from error

    python_version = str(module.__version__)
    flint_version = str(module.__FLINT_VERSION__)
    flint_release = int(module.__FLINT_RELEASE__)
    if python_version != EXPECTED_PYTHON_FLINT:
        _fail(
            "python-flint version mismatch: expected "
            f"{EXPECTED_PYTHON_FLINT}, got {python_version}"
        )
    if flint_version != EXPECTED_FLINT or flint_release != EXPECTED_FLINT_RELEASE:
        _fail(
            "FLINT version mismatch: expected 3.6.0 release 30600, got "
            f"{flint_version} release {flint_release}"
        )
    return module, acb, acb_series, arb, ctx, fmpq


def _fraction(value: Any) -> Fraction:
    return Fraction(int(value.numerator), int(value.denominator))


def _document_fraction(value: object, *, label: str) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        _fail(f"{label} is not a rational object after structural validation")
    try:
        return Fraction(int(value["numerator"]), int(value["denominator"]))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise A7FlintReplayError(f"invalid rational at {label}") from error


def _exact_arb(value: Fraction, *, label: str, arb: Any, fmpq: Any) -> Any:
    denominator = value.denominator
    if denominator <= 0 or denominator & (denominator - 1):
        _fail(f"{label} is not dyadic")
    result = arb(fmpq(value.numerator, denominator))
    if not result.is_finite() or not result.is_exact():
        _fail(f"FLINT failed to preserve exactness for {label}")
    return result


def _interval_arb(lo: Fraction, hi: Fraction, *, arb: Any, fmpq: Any) -> Any:
    if not lo < hi:
        _fail(f"invalid leaf interval [{lo}, {hi}]")
    midpoint = _exact_arb((lo + hi) / 2, label="leaf midpoint", arb=arb, fmpq=fmpq)
    radius = _exact_arb((hi - lo) / 2, label="leaf radius", arb=arb, fmpq=fmpq)
    result = arb(midpoint, radius)
    if (
        not result.is_finite()
        or not result.mid().is_exact()
        or not result.rad().is_exact()
    ):
        _fail("FLINT changed an exact dyadic leaf interval")
    return result


def _unsigned_base64url(value: int) -> str:
    if value <= 0:
        _fail("FLINT returned a nonpositive evidence endpoint")
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).decode("ascii").rstrip("=")


def _dyadic_tuple(value: Any, *, label: str) -> tuple[str, int]:
    if not value.is_finite() or not value.is_exact():
        _fail(f"{label} is not an exact finite FLINT endpoint")
    mantissa, exponent = value.man_exp()
    return _unsigned_base64url(int(mantissa)), int(exponent)


def _evaluate_leaf(
    *,
    varying_coordinate: str,
    fixed_coordinate: Fraction,
    lo: Fraction,
    hi: Fraction,
    acb: Any,
    acb_series: Any,
    arb: Any,
    fmpq: Any,
) -> tuple[Any, Any]:
    varying = _interval_arb(lo, hi, arb=arb, fmpq=fmpq)
    fixed = _exact_arb(
        fixed_coordinate, label="fixed edge coordinate", arb=arb, fmpq=fmpq
    )
    if varying_coordinate == "imag":
        s = acb(fixed, varying)
    elif varying_coordinate == "real":
        s = acb(varying, fixed)
    else:  # Structural validation should make this unreachable.
        _fail(f"unknown varying coordinate {varying_coordinate!r}")

    denominator_one = s - 1
    denominator_two = s + 2
    if not denominator_one.is_finite() or denominator_one.contains(0):
        _fail("a replayed A.7 leaf contains the pole s=1")
    if not denominator_two.is_finite() or denominator_two.contains(0):
        _fail("a replayed A.7 leaf contains the auxiliary pole s=-2")

    series_argument = acb_series([s, 1], prec=SERIES_LENGTH)
    zeta_jet = series_argument.zeta(a=1, deflate=False)
    zeta_value = zeta_jet[0]
    zeta_derivative = zeta_jet.derivative()[0]
    if not zeta_value.is_finite() or not zeta_derivative.is_finite():
        _fail("FLINT returned a nonfinite zeta jet")
    if zeta_value.contains(0):
        _fail("a replayed zeta enclosure contains zero")
    zeta_abs_lower = zeta_value.abs_lower()
    if (
        not zeta_abs_lower.is_finite()
        or not zeta_abs_lower.is_exact()
        or not fmpq(0) < zeta_abs_lower.fmpq()
    ):
        _fail("FLINT did not prove a strictly positive zeta lower bound")

    g_value = (
        -zeta_derivative / zeta_value
        - 1 / denominator_one
        + 1 / denominator_two
    )
    if not g_value.is_finite():
        _fail("FLINT returned a nonfinite regularized logarithmic derivative")
    norm_sq = g_value.real * g_value.real + g_value.imag * g_value.imag
    if not norm_sq.is_finite():
        _fail("FLINT returned a nonfinite squared norm")
    norm_sq_upper = norm_sq.upper()
    if not norm_sq_upper.is_finite() or not norm_sq_upper.is_exact():
        _fail("FLINT did not return an exact upper endpoint for the squared norm")
    if not _fraction(norm_sq_upper.fmpq()) < TARGET_SQ:
        _fail("a replayed A.7 leaf does not prove the strict squared-norm bound")
    return norm_sq_upper, zeta_abs_lower


def replay_a7_flint(
    path: str | Path, *, require_retained_identity: bool = True
) -> dict[str, Any]:
    """Recompute every accepted A.7 leaf and match its exact dyadic evidence.

    Acceptance proves the complete boundary inequality under the reviewed
    FLINT/Arb semantics.  It does not prove that those semantics realize
    Mathlib's zeta definition, so ``lean_atom_discharged`` remains false.
    """

    artifact = Path(path)
    try:
        raw = read_analytic_artifact_bytes(
            artifact, label="A7 boundary artifact"
        )
    except AnalyticArtifactError as error:
        raise A7FlintReplayError(f"cannot read A.7 artifact {artifact}: {error}") from error
    structural = verify_a7_boundary_bytes(
        raw, require_retained_identity=require_retained_identity
    )
    # Parse the exact immutable byte string whose identity, topology, and
    # arithmetic were just checked.  Never reopen `artifact` during replay:
    # path replacement must not mix structural evidence from one document
    # with FLINT evidence from another.
    try:
        document = json.loads(raw.decode("ascii"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise A7FlintReplayError(
            f"cannot parse structurally verified A.7 artifact {artifact}: {error}"
        ) from error

    module, acb, acb_series, arb, ctx, fmpq = _load_flint()
    arithmetic = document["arithmetic"]
    precision_bits = int(arithmetic["precision_bits"])
    old_precision = ctx.prec
    old_cap = ctx.cap
    old_threads = ctx.threads
    replayed_leaves: list[list[Any]] = []
    maximum = Fraction(0)
    minimum_zeta: Fraction | None = None
    started = perf_counter_ns()
    try:
        ctx.prec = precision_bits
        ctx.cap = SERIES_CAP
        ctx.threads = 1
        for position, leaf in enumerate(document["leaves"]):
            edge_id, depth, index = int(leaf[0]), int(leaf[1]), int(leaf[2])
            edge = document["edges"][edge_id]
            start = _document_fraction(edge["start"], label=f"edges[{edge_id}].start")
            end = _document_fraction(edge["end"], label=f"edges[{edge_id}].end")
            fixed = _document_fraction(
                edge["fixed_coordinate"], label=f"edges[{edge_id}].fixed_coordinate"
            )
            denominator = 1 << depth
            lo = start + (end - start) * Fraction(index, denominator)
            hi = start + (end - start) * Fraction(index + 1, denominator)
            norm_upper, zeta_lower = _evaluate_leaf(
                varying_coordinate=str(edge["varying_coordinate"]),
                fixed_coordinate=fixed,
                lo=lo,
                hi=hi,
                acb=acb,
                acb_series=acb_series,
                arb=arb,
                fmpq=fmpq,
            )
            norm_encoding = _dyadic_tuple(norm_upper, label="squared-norm upper")
            zeta_encoding = _dyadic_tuple(zeta_lower, label="zeta absolute lower")
            replayed = [
                edge_id,
                depth,
                index,
                norm_encoding[0],
                norm_encoding[1],
                zeta_encoding[0],
                zeta_encoding[1],
            ]
            if replayed != leaf:
                _fail(
                    "FLINT leaf evidence differs from the retained transcript at "
                    f"position {position} (edge={edge_id}, depth={depth}, index={index})"
                )
            replayed_leaves.append(replayed)
            norm_fraction = _fraction(norm_upper.fmpq())
            zeta_fraction = _fraction(zeta_lower.fmpq())
            maximum = max(maximum, norm_fraction)
            minimum_zeta = (
                zeta_fraction
                if minimum_zeta is None
                else min(minimum_zeta, zeta_fraction)
            )
    finally:
        ctx.prec = old_precision
        ctx.cap = old_cap
        ctx.threads = old_threads
    elapsed_ns = perf_counter_ns() - started

    replay_digest = hashlib.sha256(canonical_json_bytes(replayed_leaves)).hexdigest()
    recorded_digest = str(document["summary"]["leaves_sha256"])
    if replay_digest != recorded_digest:
        _fail("fresh FLINT leaf digest differs from the retained leaf digest")
    if minimum_zeta is None:
        _fail("A.7 replay unexpectedly contained no leaves")

    return {
        "accepted": True,
        "artifact_kind": "ch25_a7_boundary",
        "verification_class": "complete_external_flint_arb_leaf_replay",
        "artifact_sha256": structural["artifact_sha256"],
        "artifact_bytes_match_pinned_sha256": structural[
            "artifact_bytes_match_pinned_sha256"
        ],
        "python_flint_version": str(module.__version__),
        "flint_version": str(module.__FLINT_VERSION__),
        "flint_release": int(module.__FLINT_RELEASE__),
        "precision_bits": precision_bits,
        "leaf_count": len(replayed_leaves),
        "leaves_sha256": replay_digest,
        "elapsed_milliseconds": elapsed_ns // 1_000_000,
        "maximum_norm_square_upper": {
            "numerator": str(maximum.numerator),
            "denominator": str(maximum.denominator),
        },
        "minimum_zeta_abs_lower": {
            "numerator": str(minimum_zeta.numerator),
            "denominator": str(minimum_zeta.denominator),
        },
        "four_edge_dyadic_cover_verified": True,
        "every_leaf_flint_box_recomputed": True,
        "every_exact_leaf_endpoint_matched": True,
        "all_denominator_and_zeta_nonvanishing_guards_checked": True,
        "strict_norm_square_bound_verified_under_flint_semantics": True,
        "external_analytic_verification_complete": True,
        "ordinary_kernel_lean_proof": False,
        "mathlib_zeta_realization_theorem_present": False,
        "lean_atom_discharged": False,
        "remaining_trust_boundary": (
            "python-flint/FLINT analytic semantics, host toolchain, and the "
            "missing theorem relating these enclosures to Mathlib's zeta"
        ),
    }
