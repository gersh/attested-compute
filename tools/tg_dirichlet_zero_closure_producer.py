#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Pinned-Arb producer for one canonical Dirichlet zero-closure chunk."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
from pathlib import Path
import sys
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_zero_closure import (  # noqa: E402
    ALGORITHM_ID,
    HEIGHT_MARGIN,
    PRODUCER_PROTOCOL,
    RESULT_SCHEMA,
    SOURCE_SAMPLE_STEP,
    SOURCE_UPSAMPLE_FACTORS,
    DirichletZeroClosureError,
    fraction_json,
    load_canonical_json,
    validate_request,
    write_canonical_json,
)
from tools import tg_dirichlet_flint_backend as arb_backend  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


class GridResolutionError(DirichletZeroClosureError):
    """A Hardy-Z sign or source-grid decision did not resolve."""


def _arb_fraction(value: Fraction):
    return arb_backend.arb(f"{value.numerator}/{value.denominator}")


def _hardy_sign(
    character: Any,
    ordinate: Fraction,
    configuration: dict[str, int],
) -> tuple[int, int]:
    precision = configuration["initial_precision_bits"]
    while precision <= configuration["maximum_precision_bits"]:
        arb_backend.ctx.prec = precision
        value = character.hardy_z(_arb_fraction(ordinate))
        if value.is_finite():
            # python-flint exposes Hardy Z as a real-valued acb/arb.  For an
            # acb, FLINT constructs the imaginary part as exact zero at real t.
            imag_ok = not hasattr(value, "imag") or value.imag.contains(0)
            real = value.real if hasattr(value, "real") else value
            if imag_ok and real > 0:
                return 1, precision
            if imag_ok and real < 0:
                return -1, precision
        precision *= 2
    raise GridResolutionError(
        f"Hardy Z sign unresolved at {ordinate.numerator}/{ordinate.denominator}"
    )


def _source_grid(height: Fraction, step: Fraction) -> Iterator[Fraction]:
    """The exact 5/64 lattice clipped to a stronger symmetric height."""

    yield -height
    first = (-height) // step + 1
    last = height // step
    for index in range(first, last + 1):
        point = index * step
        if -height < point < height:
            yield point
    yield height


def _scan_source_grid(
    character: Any,
    height: Fraction,
    factor: int,
    configuration: dict[str, int],
) -> dict[str, Any]:
    """Scan one source upsampling level, splitting exact grid-point exceptions."""

    step = SOURCE_SAMPLE_STEP / factor
    digest = hashlib.sha256()
    previous_point: Fraction | None = None
    previous_sign: int | None = None
    samples = 0
    nominal_samples = 0
    brackets = 0
    precision_escalations = 0
    maximum_precision = 0
    gridpoint_splits = 0

    def accept(point: Fraction, sign: int, precision: int) -> None:
        nonlocal previous_point, previous_sign, samples, brackets
        nonlocal precision_escalations, maximum_precision
        if previous_point is not None and point <= previous_point:
            raise GridResolutionError("resolved Hardy grid is not strictly ordered")
        samples += 1
        maximum_precision = max(maximum_precision, precision)
        precision_escalations += int(precision > configuration["initial_precision_bits"])
        if previous_point is not None and previous_sign != sign:
            brackets += 1
            digest.update(
                (
                    f"{previous_point.numerator}/{previous_point.denominator}:"
                    f"{point.numerator}/{point.denominator}:"
                    f"{previous_sign}:{sign}\n"
                ).encode("ascii")
            )
        previous_point = point
        previous_sign = sign

    for point in _source_grid(height, step):
        nominal_samples += 1
        try:
            sign, precision = _hardy_sign(character, point, configuration)
        except GridResolutionError:
            # This is the source's central/grid-point indeterminacy class.  A
            # direct high-precision Arb recomputation on both sides creates a
            # strict bracket if the grid point is exactly a simple zero.  It
            # does not assume simplicity: the global multiplicity count below
            # must still equal the number of disjoint strict brackets.
            if previous_point is None or point == height:
                raise
            radius = min(step / 4, (point - previous_point) / 4, (height - point) / 4)
            if radius <= 0:
                raise GridResolutionError("cannot split an unresolved grid point")
            left = point - radius
            right = point + radius
            left_sign, left_precision = _hardy_sign(character, left, configuration)
            right_sign, right_precision = _hardy_sign(character, right, configuration)
            accept(left, left_sign, left_precision)
            accept(right, right_sign, right_precision)
            gridpoint_splits += 1
            continue
        accept(point, sign, precision)

    return {
        "upsample_factor": factor,
        "step": fraction_json(step),
        "nominal_samples": nominal_samples,
        "resolved_samples": samples,
        "strict_sign_change_brackets": brackets,
        "bracket_digest_sha256": digest.hexdigest(),
        "maximum_precision_bits": maximum_precision,
        "precision_escalated_samples": precision_escalations,
        "gridpoint_splits": gridpoint_splits,
    }


def _configuration(request: dict[str, Any]) -> dict[str, int]:
    value = request["configuration"]
    return {
        "initial_precision_bits": value["initial_precision_bits"],
        "maximum_precision_bits": value["maximum_precision_bits"],
        "maximum_contour_depth": value["maximum_contour_depth"],
        "maximum_contour_evaluations": value["maximum_contour_evaluations"],
        # Not used by the contour, but retained for compatibility with the
        # backend's explicit configuration object.
        "maximum_grid_refinements": 0,
        "hardy_step_numerator": SOURCE_SAMPLE_STEP.numerator,
        "hardy_step_denominator": SOURCE_SAMPLE_STEP.denominator,
    }


def _fraction(value: dict[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def _produce_character(
    request_row: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    q = request_row["q"]
    conrey = request_row["conrey_number"]
    height = _fraction(request_row["absolute_height"])
    stronger_height = height + HEIGHT_MARGIN
    configuration = _configuration(request)
    character = arb_backend.dirichlet_char(q, conrey)
    if (
        character.number() != conrey
        or not character.is_primitive()
        or character.conductor() != q
        or character.is_principal()
    ):
        raise DirichletZeroClosureError(
            f"q={q}, Conrey={conrey} is not a primitive nonprincipal character"
        )
    parity = int(character.parity())
    if parity != request_row["parity"]:
        raise DirichletZeroClosureError("requested parity differs from FLINT")

    contour = arb_backend.certified_winding_count(
        character, stronger_height, configuration
    )
    trivial_zeros = 1 if parity == 0 else 0
    required = contour["zero_count_with_trivial_zeros"] - trivial_zeros
    if required < 0:
        raise DirichletZeroClosureError("contour count is below the trivial correction")

    attempted: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    for factor in SOURCE_UPSAMPLE_FACTORS:
        scan = _scan_source_grid(character, stronger_height, factor, configuration)
        attempted.append(scan)
        found = scan["strict_sign_change_brackets"]
        if found > required:
            raise DirichletZeroClosureError(
                "strict sign-change count exceeds the multiplicity count"
            )
        if found == required:
            selected = scan
            break
    direct_refinements = request["configuration"][
        "maximum_direct_refinements_after_512"
    ]
    if selected is None:
        factor = SOURCE_UPSAMPLE_FACTORS[-1]
        for _ in range(direct_refinements):
            factor *= 2
            scan = _scan_source_grid(character, stronger_height, factor, configuration)
            attempted.append(scan)
            found = scan["strict_sign_change_brackets"]
            if found > required:
                raise DirichletZeroClosureError(
                    "direct exception refinement exceeds the multiplicity count"
                )
            if found == required:
                selected = scan
                break
    if selected is None:
        raise DirichletZeroClosureError(
            "source upsampling and bounded direct exception refinement did not "
            "recover the multiplicity-counted total"
        )
    known = request_row.get("known_answer_multiplicity_count")
    if known is not None and known != required:
        raise DirichletZeroClosureError("small known-answer zero count changed")

    selected_factor = selected["upsample_factor"]
    return {
        "q": q,
        "conrey_number": conrey,
        "parity": parity,
        "absolute_height": request_row["absolute_height"],
        "stronger_certified_height": fraction_json(stronger_height),
        "completed_hardy_reconstruction": {
            "flint_api": "dirichlet_char.hardy_z / acb_dirichlet_hardy_z",
            "identity": "Z_chi(t)=exp(i*theta_chi(t))*L_chi(1/2+i*t), real for real t",
            "platt_lambda_relation": "Platt Section 1 Lambda_chi is Z_chi times a nonzero real gamma-magnitude scale (up to one fixed sign)",
            "raw_l_zero_equivalence_used": True,
        },
        "multiplicity_counted_nontrivial_zeros": required,
        "argument_principle": {
            **contour,
            "known_trivial_zeros_in_contour": trivial_zeros,
            "real_interval": {
                "lower": {"numerator": -1, "denominator": 2},
                "upper": {"numerator": 3, "denominator": 2},
            },
            "orientation": "counterclockwise",
            "count_preserves_multiplicity": True,
        },
        "zero_isolation": {
            "selected_upsample_factor": selected_factor,
            "selected_step": selected["step"],
            "resolved_samples": selected["resolved_samples"],
            "strict_sign_change_brackets": selected[
                "strict_sign_change_brackets"
            ],
            "bracket_digest_sha256": selected["bracket_digest_sha256"],
            "maximum_precision_bits": selected["maximum_precision_bits"],
            "disjoint_ordered_brackets": True,
        },
        "exception_handling": {
            "attempted_levels": attempted,
            "source_ladder_exhausted": selected_factor > SOURCE_UPSAMPLE_FACTORS[-1],
            "direct_refinements_after_512": (
                0
                if selected_factor <= SOURCE_UPSAMPLE_FACTORS[-1]
                else selected_factor.bit_length()
                - SOURCE_UPSAMPLE_FACTORS[-1].bit_length()
            ),
            "method": "precision escalation, exact grid-point split, then direct Arb refinement",
            "paper_euler_maclaurin_exception_backend_used": False,
            "paper_turing_window_shift_used": False,
        },
        "all_nontrivial_zeros_on_critical_line": True,
    }


def produce(request_path: Path, output_path: Path) -> None:
    arb_backend._require_flint()
    request = validate_request(load_canonical_json(request_path))
    rows = [_produce_character(row, request) for row in request["characters"]]
    result = {
        "kind": RESULT_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "classification": "rigorous_direct_arb_reference_closure_not_platt_fast_turing_pipeline",
        "request_sha256": request["request_sha256"],
        "character_count": len(rows),
        "versions": arb_backend.version_record(),
        "characters": rows,
        "completed": True,
        "paper_turing_method_executed": False,
        "external_atom_discharged": False,
    }
    write_canonical_json(output_path, result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("protocol-version")
    run = commands.add_parser("produce")
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "protocol-version":
            arb_backend._require_flint()
            print(PRODUCER_PROTOCOL)
        else:
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            produce(args.request, args.output)
        return 0
    except (
        DirichletZeroClosureError,
        arb_backend.FlintReferenceError,
        OSError,
        ValueError,
    ) as error:
        print(f"tg_dirichlet_zero_closure_producer: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
