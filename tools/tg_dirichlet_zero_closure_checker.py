#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fresh pinned-Arb checker for a Dirichlet zero-closure result.

The checker is a separate executable and repeats every analytic evaluation.
It deliberately uses the older offset-grid closure as a second isolation path,
then independently replays the producer's exact selected source grid.  It does
not share a retained interval transcript with the producer.  Both roles still
trust the same reviewed FLINT/Arb analytic library, which receipts state.
"""

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
    CHECKER_ID,
    CHECKER_PROTOCOL,
    HEIGHT_MARGIN,
    RECEIPT_SCHEMA,
    SOURCE_SAMPLE_STEP,
    SOURCE_UPSAMPLE_FACTORS,
    DirichletZeroClosureError,
    canonical_json_bytes,
    fraction_json,
    load_canonical_json,
    sha256_bytes,
    validate_request,
    validate_result,
    write_canonical_json,
)
from tools import tg_dirichlet_flint_backend as arb_backend  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


class CheckerResolutionError(DirichletZeroClosureError):
    """Fresh checker evaluation did not produce a strict decision."""


def _fraction(value: dict[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def _arb_fraction(value: Fraction):
    return arb_backend.arb(f"{value.numerator}/{value.denominator}")


def _fresh_sign(
    character: Any,
    point: Fraction,
    initial_precision: int,
    maximum_precision: int,
) -> tuple[int, int]:
    precision = initial_precision
    while precision <= maximum_precision:
        arb_backend.ctx.prec = precision
        value = character.hardy_z(_arb_fraction(point))
        if value.is_finite():
            imag_ok = not hasattr(value, "imag") or value.imag.contains(0)
            real = value.real if hasattr(value, "real") else value
            if imag_ok and real > 0:
                return 1, precision
            if imag_ok and real < 0:
                return -1, precision
        precision *= 2
    raise CheckerResolutionError(
        f"fresh Hardy-Z sign unresolved at {point.numerator}/{point.denominator}"
    )


def _source_points(height: Fraction, step: Fraction) -> Iterator[Fraction]:
    yield -height
    first = (-height) // step + 1
    last = height // step
    for index in range(first, last + 1):
        point = index * step
        if -height < point < height:
            yield point
    yield height


def _fresh_source_digest(
    character: Any,
    height: Fraction,
    factor: int,
    initial_precision: int,
    maximum_precision: int,
) -> dict[str, Any]:
    """Independent implementation of the retained source-grid commitment."""

    step = SOURCE_SAMPLE_STEP / factor
    digest = hashlib.sha256()
    previous_point: Fraction | None = None
    previous_sign: int | None = None
    samples = 0
    brackets = 0
    maximum_used = 0

    def accept(point: Fraction, sign: int, precision: int) -> None:
        nonlocal previous_point, previous_sign, samples, brackets, maximum_used
        if previous_point is not None and point <= previous_point:
            raise CheckerResolutionError("fresh source grid is not ordered")
        samples += 1
        maximum_used = max(maximum_used, precision)
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

    for point in _source_points(height, step):
        try:
            sign, precision = _fresh_sign(
                character, point, initial_precision, maximum_precision
            )
        except CheckerResolutionError:
            if previous_point is None or point == height:
                raise
            radius = min(step / 4, (point - previous_point) / 4, (height - point) / 4)
            if radius <= 0:
                raise CheckerResolutionError("cannot split fresh unresolved point")
            for replacement in (point - radius, point + radius):
                replacement_sign, replacement_precision = _fresh_sign(
                    character,
                    replacement,
                    initial_precision,
                    maximum_precision,
                )
                accept(replacement, replacement_sign, replacement_precision)
        else:
            accept(point, sign, precision)
    return {
        "step": fraction_json(step),
        "resolved_samples": samples,
        "strict_sign_change_brackets": brackets,
        "bracket_digest_sha256": digest.hexdigest(),
        "maximum_precision_bits": maximum_used,
    }


def _alternate_configuration(request: dict[str, Any]) -> dict[str, int]:
    configuration = request["configuration"]
    # The alternate path uses the offset lattice from the established FLINT
    # reference backend and refines by powers of two.  Twenty levels cover the
    # source ladder through 512 and eight additional direct refinements.
    return {
        "initial_precision_bits": configuration["initial_precision_bits"],
        "maximum_precision_bits": configuration["maximum_precision_bits"],
        "maximum_contour_depth": configuration["maximum_contour_depth"],
        "maximum_contour_evaluations": configuration[
            "maximum_contour_evaluations"
        ],
        "maximum_grid_refinements": 20,
        "hardy_step_numerator": SOURCE_SAMPLE_STEP.numerator,
        "hardy_step_denominator": SOURCE_SAMPLE_STEP.denominator,
    }


def verify(request_path: Path, result_path: Path, receipt_path: Path) -> None:
    arb_backend._require_flint()
    request = validate_request(load_canonical_json(request_path))
    result = validate_result(request, load_canonical_json(result_path))
    if result["versions"] != arb_backend.version_record():
        raise DirichletZeroClosureError("producer and checker FLINT versions differ")
    configuration = request["configuration"]
    alternate_configuration = _alternate_configuration(request)
    checked_rows: list[dict[str, Any]] = []
    for request_row, retained in zip(request["characters"], result["characters"]):
        q = request_row["q"]
        conrey = request_row["conrey_number"]
        height = _fraction(request_row["absolute_height"])
        # First run a complete fresh alternate closure.  It has a phase-shifted
        # grid and powers-of-two refinement, so it does not consume the
        # producer's sign transcript or upsampling decision.
        fresh = arb_backend.verify_character(
            q,
            conrey,
            height,
            alternate_configuration,
        )
        if fresh["parity"] != request_row["parity"]:
            raise DirichletZeroClosureError("fresh checker parity differs")
        retained_count = retained["multiplicity_counted_nontrivial_zeros"]
        if fresh["multiplicity_counted_nontrivial_zeros"] != retained_count:
            raise DirichletZeroClosureError(
                "fresh argument-principle multiplicity count differs"
            )
        if fresh["hardy_z"]["strict_sign_change_brackets"] != retained_count:
            raise DirichletZeroClosureError("fresh alternate isolation is incomplete")
        known = request_row.get("known_answer_multiplicity_count")
        if known is not None and retained_count != known:
            raise DirichletZeroClosureError("known-answer multiplicity count differs")

        # Then freshly replay the compact producer commitment at its selected
        # source upsampling level.  This detects forged bracket counts/digests.
        selected = retained["zero_isolation"]["selected_upsample_factor"]
        maximum_selected = SOURCE_UPSAMPLE_FACTORS[-1] * (
            1
            << configuration["maximum_direct_refinements_after_512"]
        )
        if (
            isinstance(selected, bool)
            or not isinstance(selected, int)
            or selected < 1
            or selected > maximum_selected
            or (
                selected not in SOURCE_UPSAMPLE_FACTORS
                and (
                    selected < 2 * SOURCE_UPSAMPLE_FACTORS[-1]
                    or selected % SOURCE_UPSAMPLE_FACTORS[-1] != 0
                    or (selected // SOURCE_UPSAMPLE_FACTORS[-1]).bit_count() != 1
                )
            )
        ):
            raise DirichletZeroClosureError("selected upsampling factor is invalid")
        character = arb_backend.dirichlet_char(q, conrey)
        replay = _fresh_source_digest(
            character,
            height + HEIGHT_MARGIN,
            selected,
            configuration["initial_precision_bits"],
            configuration["maximum_precision_bits"],
        )
        isolation = retained["zero_isolation"]
        for key in (
            "selected_step",
            "resolved_samples",
            "strict_sign_change_brackets",
            "bracket_digest_sha256",
            "maximum_precision_bits",
        ):
            replay_key = "step" if key == "selected_step" else key
            if isolation[key] != replay[replay_key]:
                raise DirichletZeroClosureError(
                    f"fresh source-grid replay differs in {key}"
                )
        checked_rows.append(
            {
                "q": q,
                "conrey_number": conrey,
                "multiplicity_counted_nontrivial_zeros": retained_count,
                "selected_upsample_factor": selected,
                "alternate_grid_refinement": fresh["hardy_z"]["grid_refinement"],
                "source_grid_digest_sha256": replay["bracket_digest_sha256"],
            }
        )

    result_hash = sha256_bytes(canonical_json_bytes(result))
    receipt = {
        "kind": RECEIPT_SCHEMA,
        "schema_version": 1,
        "checker_id": CHECKER_ID,
        "request_sha256": request["request_sha256"],
        "result_sha256": result_hash,
        "character_count": request["character_count"],
        "checked_characters": checked_rows,
        "accepted": True,
        "fresh_analytic_evaluations": True,
        "alternate_isolation_grid_replayed": True,
        "producer_source_grid_digest_replayed": True,
        "multiplicity_preserved": True,
        "shared_flint_analytic_library": True,
        "paper_turing_method_executed": False,
        "external_atom_discharged": False,
    }
    write_canonical_json(receipt_path, receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("protocol-version")
    run = commands.add_parser("verify")
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--result", type=Path, required=True)
    run.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "protocol-version":
            arb_backend._require_flint()
            print(CHECKER_PROTOCOL)
        else:
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            verify(args.request, args.result, args.receipt)
        return 0
    except (
        DirichletZeroClosureError,
        arb_backend.FlintReferenceError,
        OSError,
        ValueError,
    ) as error:
        print(f"tg_dirichlet_zero_closure_checker: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
