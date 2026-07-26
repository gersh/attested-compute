#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run and freshly replay Dirichlet completed-value, sinc, and Turing stages."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_postprocess import (  # noqa: E402
    COMPLETED_SCHEMA,
    TURING_SCHEMA,
    UPSAMPLE_SCHEMA,
    DirichletPostprocessError,
    canonical_json_bytes,
    capability_report,
    evaluate,
    interval_arb,
    rectangle_acb,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _load(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletPostprocessError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise DirichletPostprocessError(f"noncanonical JSON object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _contains(retained: dict[str, object], fresh: dict[str, object], field: str) -> None:
    outer = interval_arb(f"retained.{field}", retained[field])
    inner = interval_arb(f"fresh.{field}", fresh[field])
    if not outer.contains(inner):
        raise DirichletPostprocessError(f"fresh replay escaped retained {field}")


def _overlaps(retained: dict[str, object], fresh: dict[str, object], field: str) -> None:
    left = interval_arb(f"retained.{field}", retained[field])
    right = interval_arb(f"fresh.{field}", fresh[field])
    if not left.overlaps(right):
        raise DirichletPostprocessError(f"fresh replay is disjoint from retained {field}")


def verify(request: dict[str, object], retained: dict[str, object], precision: int) -> dict[str, object]:
    fresh = evaluate(request, precision=precision)
    if retained.get("kind") != fresh["kind"] or retained.get("stage") != fresh["stage"]:
        raise DirichletPostprocessError("retained postprocess stage identity differs")
    if retained.get("algorithm_id") != fresh["algorithm_id"]:
        raise DirichletPostprocessError("retained postprocess algorithm identity differs")
    if retained.get("source_mapping") != fresh["source_mapping"]:
        raise DirichletPostprocessError("retained postprocess source mapping differs")
    stage = fresh["stage"]
    if stage == "completed_value":
        _contains(retained, fresh, "completed_real")
        if retained.get("strict_sign") != fresh["strict_sign"]:
            raise DirichletPostprocessError("completed-value strict sign differs")
        # The producer consumes upstream all-character intervals.  The checker
        # independently calls FLINT's raw L and Hardy-Z APIs, making this the
        # direct Arb exception/oracle path rather than a second reconstruction
        # from the same retained rectangle.
        from fractions import Fraction
        from tg_verifier import dirichlet_postprocess as post

        post.ctx.prec = precision
        q = request["q"]
        conrey = request["conrey_number"]
        parity = request["parity"]
        ordinate_value = request["ordinate"]
        ordinate = Fraction(
            ordinate_value["numerator"], ordinate_value["denominator"]
        )
        t = post.arb(f"{ordinate.numerator}/{ordinate.denominator}")
        character = post.dirichlet_char(q, conrey)
        if (
            not character.is_primitive()
            or character.conductor() != q
            or int(character.parity()) != parity
        ):
            raise DirichletPostprocessError("fresh FLINT character identity differs")
        fresh_l = character.l_function(post.acb(post.arb("1/2"), t))
        if not rectangle_acb("request.l_value", request["l_value"]).contains(fresh_l):
            raise DirichletPostprocessError("fresh raw L escaped upstream rectangle")
        gamma_argument = post.acb(
            post.arb(f"{1 + 2 * parity}/4"), t / 2
        )
        scale = abs(gamma_argument.gamma()) * (post.arb.pi() * t / 4).exp()
        direct = character.hardy_z(t) * scale
        direct_real = direct.real if hasattr(direct, "real") else direct
        retained_real = interval_arb("retained.completed_real", retained["completed_real"])
        if not retained_real.overlaps(direct_real) and not retained_real.overlaps(
            -direct_real
        ):
            raise DirichletPostprocessError(
                "completed reconstruction does not overlap direct FLINT Hardy Z up to fixed sign"
            )
    elif stage == "whittaker_shannon_upsample":
        for field in (
            "finite_sinc_sum",
            "weiss_alias_budget",
            "truncation_budget",
            "total_enclosure",
        ):
            _overlaps(retained, fresh, field)
        if retained.get("strict_sign") != fresh["strict_sign"]:
            raise DirichletPostprocessError("upsampled strict sign differs")
        if retained.get("production_accept") != fresh["production_accept"]:
            raise DirichletPostprocessError("upsampling production decision differs")
    elif stage == "paired_turing_closure":
        for field in (
            "gamma_integral",
            "chi_staircase_integral",
            "conjugate_staircase_integral",
            "rumely_bound_per_character",
            "paired_rumely_bound_over_h",
            "phi_over_h_pi_interval",
            "paired_staircase_over_h_interval",
            "source_two_over_pi_contribution",
            "source_normalized_model_interval",
            "completion_upper_bound",
            "identity_residual_interval",
            "platt_released_code_upper_bound",
            "literal_arxiv_v1_typeset_interval",
        ):
            _overlaps(retained, fresh, field)
        if retained.get("certified_multiplicity_count_below_t0") != fresh[
            "certified_multiplicity_count_below_t0"
        ]:
            raise DirichletPostprocessError("paired Turing integer differs")
        from fractions import Fraction
        from tools import tg_dirichlet_flint_backend as backend

        configuration = backend.configuration()
        t0_value = request["t0"]
        h_value = request["h"]
        t0 = Fraction(t0_value["numerator"], t0_value["denominator"])
        h = Fraction(h_value["numerator"], h_value["denominator"])
        for character, rows in (
            (
                backend.dirichlet_char(request["q"], request["conrey_number"]),
                request["chi_window_zeros"],
            ),
            (
                backend.dirichlet_char(
                    request["q"], request["conjugate_conrey_number"]
                ),
                request["conjugate_window_zeros"],
            ),
        ):
            backend._hardy_sign(character, t0, configuration)
            backend._hardy_sign(character, t0 + h, configuration)
            for row in rows:
                if row["multiplicity"] != 1:
                    raise DirichletPostprocessError(
                        "fresh strict-sign checker only certifies multiplicity lower bound one"
                    )
                lower_value = row["lower"]
                upper_value = row["upper"]
                lower = Fraction(
                    lower_value["numerator"], lower_value["denominator"]
                )
                upper = Fraction(
                    upper_value["numerator"], upper_value["denominator"]
                )
                lower_sign = backend._hardy_sign(character, lower, configuration)[0]
                upper_sign = backend._hardy_sign(character, upper, configuration)[0]
                if lower_sign == upper_sign:
                    raise DirichletPostprocessError(
                        "fresh Turing-window bracket is not a strict sign change"
                    )
    else:  # pragma: no cover
        raise DirichletPostprocessError("unknown retained postprocess stage")
    return {
        "kind": "sparkinterval.tg.dirichlet_postprocess.checker_receipt.v2",
        "schema_version": 2,
        "stage": stage,
        "request_sha256": hashlib.sha256(canonical_json_bytes(request)).hexdigest(),
        "result_sha256": hashlib.sha256(canonical_json_bytes(retained)).hexdigest(),
        "fresh_precision_bits": precision,
        "fresh_outward_replay": True,
        "direct_flint_exception_oracle": stage == "completed_value",
        "accepted": True,
        "production_accept": fresh.get("production_accept", False),
        "external_atom_discharged": False,
    }


def _emit(value: object, pretty: bool) -> None:
    print(json.dumps(value, sort_keys=True, indent=2 if pretty else None))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    produce = commands.add_parser("produce")
    produce.add_argument("request", type=Path)
    produce.add_argument("output", type=Path)
    produce.add_argument("--precision", type=int, default=192)
    check = commands.add_parser("verify")
    check.add_argument("request", type=Path)
    check.add_argument("result", type=Path)
    check.add_argument("receipt", type=Path)
    check.add_argument("--precision", type=int, default=256)
    args = parser.parse_args()
    try:
        if args.command == "capability":
            value = capability_report()
        elif args.command == "produce":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            if args.precision < 128:
                raise DirichletPostprocessError("producer precision must be at least 128")
            request = _load(args.request)
            value = evaluate(request, precision=args.precision)
            _write(args.output, value)
        else:
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            if args.precision < 192:
                raise DirichletPostprocessError("checker precision must be at least 192")
            request = _load(args.request)
            value = verify(request, _load(args.result), args.precision)
            _write(args.receipt, value)
        _emit(value, args.pretty)
        return 0
    except (DirichletPostprocessError, OSError, ValueError) as error:
        print(f"tg_dirichlet_postprocess: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
