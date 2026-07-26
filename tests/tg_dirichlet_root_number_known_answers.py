#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fresh MPFR-transform / direct-Arb KAT for Dirichlet root numbers."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flint import acb, arb, ctx, dirichlet_char  # noqa: E402

from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    primitive_frequency_records,
)
from tg_verifier.dirichlet_root_number_stage import (  # noqa: E402
    ROOT_HEADER,
    ROOT_RECORD,
    consume_transform_path,
    read_root_artifact,
    write_additive_input,
)


def binary_interval(lower: float, upper: float):
    lower_q = Fraction.from_float(lower)
    upper_q = Fraction.from_float(upper)
    midpoint = (lower_q + upper_q) / 2
    radius = (upper_q - lower_q) / 2
    return arb(
        f"{midpoint.numerator}/{midpoint.denominator}",
        f"{radius.numerator}/{radius.denominator}",
    )


def binary_rectangle(endpoints: tuple[float, float, float, float]):
    return acb(
        binary_interval(endpoints[0], endpoints[1]),
        binary_interval(endpoints[2], endpoints[3]),
    )


def direct_phase(q: int, conrey: int, parity: int, *, additive_sign: int = 1):
    character = dirichlet_char(q, conrey)
    if (
        character.number() != conrey
        or character.modulus() != q
        or character.conductor() != q
        or not character.is_primitive()
        or character.parity() != parity
    ):
        raise RuntimeError("independent FLINT character identity differs")
    group_exponent = int(character.group().exponent())
    tau = acb(0)
    for residue in range(1, q + 1):
        exponent = character.chi_exponent(residue)
        if exponent is None:
            continue
        chi = acb(0, 2 * arb.pi() * int(exponent) / group_exponent).exp()
        additive = acb(
            0, additive_sign * 2 * arb.pi() * residue / q
        ).exp()
        tau += chi * additive
    parity_phase = acb(1) if parity == 0 else acb(0, 1)
    root_number = tau / (parity_phase * arb(q).sqrt())
    return root_number.conjugate().sqrt(), tau


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--precision", type=int, default=256)
    args = parser.parse_args()
    ctx.prec = args.precision
    q_results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for q in (5, 7, 8, 15):
            input_path = work / f"q{q}.input"
            input_receipt_path = work / f"q{q}.input.json"
            transform_path = work / f"q{q}.transform"
            roots_path = work / f"q{q}.roots"
            receipt_path = work / f"q{q}.roots.json"
            additive_receipt = write_additive_input(
                input_path,
                q=q,
                precision=args.precision,
                receipt_path=input_receipt_path,
            )
            subprocess.run(
                [
                    str(args.checker.resolve()),
                    "compute",
                    str(input_path),
                    str(transform_path),
                    str(args.precision),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            receipt = consume_transform_path(
                transform_path,
                roots_path,
                receipt_path,
                q=q,
                additive_receipt=additive_receipt,
                precision=args.precision,
            )
            metadata, roots = read_root_artifact(roots_path, receipt)
            identities = primitive_frequency_records(q)
            if len(identities) != len(roots):
                raise RuntimeError("primitive root KAT count differs")
            for identity, candidate in zip(identities, roots):
                expected, _tau = direct_phase(
                    q, identity["conrey_number"], identity["parity"]
                )
                if not candidate.contains(expected):
                    raise RuntimeError(
                        "TGDAFF positive-character convention disagrees with "
                        f"direct Arb at q={q}, Conrey={identity['conrey_number']}"
                    )
            if q == 5:
                quadratic_index = next(
                    index
                    for index, row in enumerate(identities)
                    if row["conrey_number"] == 4
                )
                quadratic = dirichlet_char(5, 4)
                if quadratic.order() != 2 or quadratic.group().exponent() != 4:
                    raise RuntimeError("q=5 group-exponent regression premise changed")
                if not roots[quadratic_index].contains(acb(1)):
                    raise RuntimeError("q=5 Conrey 4 completed phase does not contain one")
                nonreal_index = next(
                    index
                    for index, row in enumerate(identities)
                    if row["conrey_number"] == 2
                )
                wrong, _ = direct_phase(5, 2, 1, additive_sign=-1)
                if roots[nonreal_index].overlaps(wrong):
                    raise RuntimeError("positive/negative additive convention KAT is vacuous")
            raw = roots_path.read_bytes()
            if len(raw) != ROOT_HEADER.size + len(roots) * ROOT_RECORD.size:
                raise RuntimeError("compact root artifact size differs")
            q_results.append(
                {
                    "q": q,
                    "primitive_character_count": len(roots),
                    "root_artifact_sha256": metadata["root_artifact_sha256"],
                }
            )
    print(
        json.dumps(
            {
                "kind": "sparkinterval.tg.dirichlet_root.known_answer.v1",
                "classification": "small_modulus_independent_kat_not_grh_evidence",
                "checker": "independent-mpfr-directed-tgdaff",
                "direct_replay": "fresh-quadratic-arb-character-gauss-sums",
                "group_exponent_regression": "q=5-conrey-4-order-2-group-exponent-4",
                "moduli": q_results,
                "status": "pass",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
