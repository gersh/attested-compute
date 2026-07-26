# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed audit of the proposed deferred ``q^-s`` optimization.

The resident large-q composer does not send ``q^-s * (zeta_M + R_M)`` to the
all-character DFT.  It sends

``q^-s * zeta_M + R_M``,

where ``R_M = sum_{n=0}^M (q*n+a)^-s`` is already in the scaled coordinates.
Consequently the factor cannot be moved across the single DFT without first
replacing every recovery enclosure by ``q^s * R_M``.

This module records an exact rational counterexample at ``t=0``.  It is a
semantic regression guard, not a floating-point experiment and not a source
execution claim.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from typing import Any


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "tg-dirichlet-deferred-q-scaling-rejection-v1"


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def _fraction(value: Fraction) -> dict[str, int]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
    }


def audit_deferred_q_scaling() -> dict[str, Any]:
    """Return an exact counterexample to naive single-DFT deferral.

    Use the source-range square conductor ``q = 101^2`` and ``t = 0``.  Then
    ``q^-s = 1/101`` exactly.  A length-one DFT is the identity, so no
    convention about Fourier signs or normalization enters the comparison.
    """

    q = 10_201
    q_to_minus_s = Fraction(1, 101)
    zeta_m = Fraction(2)
    recovery = Fraction(3)
    current = q_to_minus_s * zeta_m + recovery
    naively_deferred = q_to_minus_s * (zeta_m + recovery)
    difference = current - naively_deferred
    expected_difference = (1 - q_to_minus_s) * recovery
    if difference != expected_difference or difference == 0:
        raise AssertionError("deferred q^-s counterexample changed")

    record: dict[str, Any] = {
        "schema": (
            "sparkinterval.tg.dirichlet_deferred_q_scaling_audit.v1"
        ),
        "algorithm_id": ALGORITHM_ID,
        "author": AUTHOR,
        "classification": (
            "exact_semantic_counterexample_not_source_execution"
        ),
        "counterexample": {
            "q": q,
            "t": _fraction(Fraction(0)),
            "q_to_minus_s": _fraction(q_to_minus_s),
            "zeta_M": _fraction(zeta_m),
            "finite_recovery": _fraction(recovery),
            "current_composer_value": _fraction(current),
            "naively_deferred_value": _fraction(naively_deferred),
            "nonzero_difference": _fraction(difference),
        },
        "current_cuda_expression": "q^-s*zeta_M + R_M",
        "naive_deferred_expression": "q^-s*(zeta_M + R_M)",
        "exact_difference": "(1-q^-s)*R_M",
        "taylor_tail_scaled_with_zeta_M": True,
        "finite_recovery_already_scaled_coordinates": True,
        "uniform_common_q_to_minus_s_factor_present": False,
        "exact_single_dft_rewrite_requires_q_to_s_times_recovery": True,
        "alternative_requires_second_recovery_dft": True,
        "naive_deferred_scaling_rejected": True,
        "optimized_recovery_rewrite_implemented": False,
        "source_usefulness_established": False,
        "source_scale_run_completed": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    record["audit_sha256"] = hashlib.sha256(
        _canonical_json(record)
    ).hexdigest()
    return record


__all__ = ["ALGORITHM_ID", "audit_deferred_q_scaling"]
