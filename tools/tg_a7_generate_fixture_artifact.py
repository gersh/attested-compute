#!/usr/bin/env python3
"""Generate a NON-PRODUCTION CH25 Lemma A.7 boundary fixture artifact.

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

WHAT THIS IS
------------
A developer fixture generator.  It runs the real adaptive dyadic bisection over
the four edges of the A.7 rectangle (real ``[-3, 5]``, imag ``[-4, 4]``) with
exactly the arithmetic that :func:`tg_verifier.a7_flint._evaluate_leaf` uses
(``ctx.prec = precision_bits``, ``ctx.cap = 4``, ``ctx.threads = 1``, series
length 2), and writes a canonical artifact that
:func:`tg_verifier.a7_flint.replay_a7_flint` accepts when it is invoked with
``require_retained_identity=False``.

WHAT THIS IS NOT
----------------
This is **not** the retained production A.7 artifact
(sha256 ``ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29``),
and it MUST NOT be used to manufacture, substitute for, or advertise a
production A.7 claim.  The production artifact is pinned by digest inside
:mod:`tg_verifier.analytic`; a fixture produced here will always fail
``require_retained_identity=True``, which is exactly the intended behaviour.
Its only purpose is to let a local dry run actually execute the real A.7
FLINT/Arb replay code path instead of skipping it.

The mathematics is nonetheless genuine: every emitted leaf is a box on which
FLINT proved ``upper(normSq(G(box))) < (349/250)^2`` strictly, the leaves form
a gap-free dyadic cover of all four edges, and each recorded dyadic endpoint is
the exact value FLINT returned.  What makes the output a fixture rather than a
production claim is solely that it is a freshly generated, unpinned document
(and it is typically generated at a shallower depth / coarser search budget
than the retained run).

USAGE
-----
    python3 tools/tg_a7_generate_fixture_artifact.py \
        --output /path/to/a7_fixture.json --max-depth 20

Requires python-flint 0.9.0 bundling FLINT 3.6.0 (release 30600), the same pin
the replay enforces.

DEPTH BUDGET
------------
The bound is genuinely tight, so a shallow search cannot succeed.  On the left
edge (real ``-3``) the true supremum of ``|G|`` is about ``1.395429`` at
``t = 0``, against the target ``349/250 = 1.396``; and ``|zeta(-3 + it)|``
stays near ``1/120`` there, so the ball division ``zeta'/zeta`` widens the
enclosure by roughly two orders of magnitude more than the true variation.
Depths 12 and 16 both abort with ``bound_not_strict``; depth 17 is the first
that closes every box, so ``--max-depth`` defaults to 20 with headroom.  The
resulting cover is about 16k leaves (essentially all on the left edge) and both
generation and replay finish in a few seconds.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from tg_verifier.a7_flint import (  # noqa: E402
    A7FlintReplayError,
    SERIES_CAP,
    SERIES_LENGTH,
    TARGET_SQ,
    _dyadic_tuple,
    _evaluate_leaf,
    _fraction,
    _load_flint,
)
from tg_verifier.analytic import (  # noqa: E402
    A7_SCHEMA,
    _A7_EDGE_SPECS,
    _A7_LEAF_ENCODING,
    _A7_NORM_TARGET,
    _A7_REJECTION_REASONS,
    _a7_norm_diagnostics,
    canonical_json_bytes,
)


_AUTHOR = "Gershon Bialer"

# Map the exact failure strings raised by ``_evaluate_leaf`` onto the canonical
# rejection-reason vocabulary the structural verifier accepts.  A box that hits
# any of these is subdivided rather than retained.
_REJECTION_BY_MESSAGE: tuple[tuple[str, str], ...] = (
    ("contains the pole s=1", "s_minus_one_contains_zero"),
    ("contains the auxiliary pole s=-2", "s_plus_two_contains_zero"),
    ("nonfinite zeta jet", "zeta_jet_nonfinite"),
    ("zeta enclosure contains zero", "zeta_contains_zero"),
    ("strictly positive zeta lower bound", "zeta_lower_not_positive"),
    ("nonfinite regularized logarithmic derivative", "g_nonfinite"),
    ("nonfinite squared norm", "norm_sq_nonfinite"),
    ("exact upper endpoint for the squared norm", "norm_sq_upper_nonfinite"),
    ("does not prove the strict squared-norm bound", "bound_not_strict"),
)


class FixtureGenerationError(RuntimeError):
    """The adaptive search could not certify the boundary at this budget."""


def _classify(error: A7FlintReplayError) -> str:
    message = str(error)
    for needle, reason in _REJECTION_BY_MESSAGE:
        if needle in message:
            if reason not in _A7_REJECTION_REASONS:  # pragma: no cover - guard
                raise FixtureGenerationError(f"unknown rejection reason {reason}")
            return reason
    # Anything else (non-dyadic endpoint, unknown coordinate, ...) is a defect
    # in this generator, not a legitimate "subdivide and retry" outcome.
    raise FixtureGenerationError(f"unexpected FLINT replay failure: {message}")


def _rational(value: Fraction) -> dict[str, str]:
    fraction = Fraction(value)
    return {
        "numerator": str(fraction.numerator),
        "denominator": str(fraction.denominator),
    }


def _search_edge(
    *,
    edge_id: int,
    varying: str,
    start: Fraction,
    end: Fraction,
    fixed: Fraction,
    max_depth: int,
    flint_objects: tuple[Any, Any, Any, Any],
    rejection_counts: dict[str, int],
) -> tuple[list[list[Any]], list[Fraction], list[Fraction]]:
    """Depth-first adaptive bisection of one edge, emitted in index order."""

    acb, acb_series, arb, fmpq = flint_objects
    leaves: list[list[Any]] = []
    norm_values: list[Fraction] = []
    zeta_values: list[Fraction] = []
    # Stack of (depth, index); pop order keeps emitted leaves sorted by the
    # left endpoint, which is what the structural cover check requires.
    stack: list[tuple[int, int]] = [(0, 0)]
    while stack:
        depth, index = stack.pop()
        denominator = 1 << depth
        lo = start + (end - start) * Fraction(index, denominator)
        hi = start + (end - start) * Fraction(index + 1, denominator)
        try:
            norm_upper, zeta_lower = _evaluate_leaf(
                varying_coordinate=varying,
                fixed_coordinate=fixed,
                lo=lo,
                hi=hi,
                acb=acb,
                acb_series=acb_series,
                arb=arb,
                fmpq=fmpq,
            )
        except A7FlintReplayError as error:
            reason = _classify(error)
            if depth >= max_depth:
                raise FixtureGenerationError(
                    f"edge {edge_id} box [{lo}, {hi}] (depth {depth}, index "
                    f"{index}) still fails as {reason} at the depth limit "
                    f"{max_depth}; raise --max-depth or --precision-bits"
                ) from error
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            # Push the right half first so the left half is popped first.
            stack.append((depth + 1, 2 * index + 1))
            stack.append((depth + 1, 2 * index))
            continue
        norm_mantissa, norm_exponent = _dyadic_tuple(
            norm_upper, label="squared-norm upper"
        )
        zeta_mantissa, zeta_exponent = _dyadic_tuple(
            zeta_lower, label="zeta absolute lower"
        )
        leaves.append(
            [
                edge_id,
                depth,
                index,
                norm_mantissa,
                norm_exponent,
                zeta_mantissa,
                zeta_exponent,
            ]
        )
        # Keep the exact rational endpoints beside the dyadic encodings so the
        # summary rationals cannot drift from the retained leaf array.
        norm_values.append(_fraction(norm_upper.fmpq()))
        zeta_values.append(_fraction(zeta_lower.fmpq()))
    return leaves, norm_values, zeta_values


def build_artifact(*, max_depth: int, precision_bits: int, max_work: int) -> bytes:
    """Run the adaptive search and return the canonical artifact bytes."""

    _module, acb, acb_series, arb, ctx, fmpq = _load_flint()
    rejection_counts: dict[str, int] = {}
    leaves: list[list[Any]] = []
    norm_values: list[Fraction] = []
    zeta_values: list[Fraction] = []

    old_precision, old_cap, old_threads = ctx.prec, ctx.cap, ctx.threads
    try:
        ctx.prec = precision_bits
        ctx.cap = SERIES_CAP
        ctx.threads = 1
        for edge_id, (_name, varying, start, end, fixed) in enumerate(_A7_EDGE_SPECS):
            edge_leaves, edge_norms, edge_zetas = _search_edge(
                edge_id=edge_id,
                varying=varying,
                start=start,
                end=end,
                fixed=fixed,
                max_depth=max_depth,
                flint_objects=(acb, acb_series, arb, fmpq),
                rejection_counts=rejection_counts,
            )
            leaves.extend(edge_leaves)
            norm_values.extend(edge_norms)
            zeta_values.extend(edge_zetas)
    finally:
        ctx.prec, ctx.cap, ctx.threads = old_precision, old_cap, old_threads

    leaf_count = len(leaves)
    rejected = sum(rejection_counts.values())
    if rejected != leaf_count - len(_A7_EDGE_SPECS):
        raise FixtureGenerationError(
            "internal-node bookkeeping is inconsistent with four full binary "
            f"covers: {rejected} rejections for {leaf_count} leaves"
        )
    work_count = leaf_count + rejected
    if work_count > max_work:
        raise FixtureGenerationError(
            f"work count {work_count} exceeds the recorded guard {max_work}"
        )

    deepest = max(leaf[1] for leaf in leaves)
    max_norm_sq = max(norm_values)
    min_zeta = min(zeta_values)
    if not max_norm_sq < TARGET_SQ:
        raise FixtureGenerationError("a retained leaf does not beat the target")
    first_max = norm_values.index(max_norm_sq)
    max_edge_id, max_depth_leaf, max_index = leaves[first_max][:3]
    max_name, _varying, max_start, max_end, _fixed = _A7_EDGE_SPECS[max_edge_id]
    max_denominator = 1 << max_depth_leaf
    max_lo = max_start + (max_end - max_start) * Fraction(max_index, max_denominator)
    max_hi = max_start + (max_end - max_start) * Fraction(
        max_index + 1, max_denominator
    )

    counts = {name: 0 for name, *_rest in _A7_EDGE_SPECS}
    for leaf in leaves:
        counts[_A7_EDGE_SPECS[leaf[0]][0]] += 1

    norm_decimal, margin_decimal = _a7_norm_diagnostics(max_norm_sq)

    document: dict[str, Any] = {
        "schema": A7_SCHEMA,
        "author": _AUTHOR,
        "claim": {
            "function": "-zeta'(s)/zeta(s)-1/(s-1)+1/(s+2)",
            "rectangle": {
                "real": ["-3", "5"],
                "imag": ["-4", "4"],
                "locus": "all four closed edges",
            },
            "norm_bound": _rational(_A7_NORM_TARGET),
            "norm_sq_bound": _rational(TARGET_SQ),
        },
        "arithmetic": {
            "python_flint_version": "0.9.0",
            "flint_version": "3.6.0",
            "flint_release": 30600,
            "precision_bits": precision_bits,
            "series_length": SERIES_LENGTH,
            "series_cap": SERIES_CAP,
            "threads": 1,
            "subdivision": "exact dyadic midpoint",
            "acceptance": "exact upper(normSq(G(box))) < (349/250)^2",
        },
        "guards": {"max_depth": max_depth, "max_work": max_work},
        "edges": [
            {
                "name": name,
                "varying_coordinate": varying,
                "start": _rational(start),
                "end": _rational(end),
                "fixed_coordinate": _rational(fixed),
            }
            for name, varying, start, end, fixed in _A7_EDGE_SPECS
        ],
        "leaf_encoding": dict(_A7_LEAF_ENCODING),
        "leaves": leaves,
        "summary": {
            "leaf_count": leaf_count,
            "leaf_counts_by_edge": counts,
            "work_count": work_count,
            "max_depth": deepest,
            "rejection_counts": dict(rejection_counts),
            "max_norm_sq_upper": _rational(max_norm_sq),
            "margin_norm_sq": _rational(TARGET_SQ - max_norm_sq),
            "min_zeta_abs_lower": _rational(min_zeta),
            "max_leaf": {
                "edge": max_name,
                "depth": max_depth_leaf,
                "index": max_index,
                "lo": _rational(max_lo),
                "hi": _rational(max_hi),
            },
            "max_norm_upper_decimal_outward": norm_decimal,
            "margin_norm_lower_decimal_outward": margin_decimal,
            "leaves_sha256": hashlib.sha256(
                canonical_json_bytes(leaves)
            ).hexdigest(),
        },
    }
    return canonical_json_bytes(document) + b"\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a NON-PRODUCTION CH25 Lemma A.7 boundary fixture "
            "artifact for local FLINT replay dry runs.  Never use the output "
            "as a production A.7 claim."
        )
    )
    parser.add_argument("--output", required=True, help="artifact path to write")
    parser.add_argument(
        "--max-depth",
        type=int,
        default=20,
        help=(
            "maximum dyadic subdivision depth (default: 20; depth 17 is the "
            "shallowest that actually closes every box)"
        ),
    )
    parser.add_argument(
        "--precision-bits",
        type=int,
        default=192,
        help="FLINT working precision in bits (default: 192)",
    )
    parser.add_argument(
        "--max-work",
        type=int,
        default=1_000_000,
        help="recorded work guard; the search must stay under it",
    )
    arguments = parser.parse_args(argv)

    if not 0 <= arguments.max_depth <= 64:
        parser.error("--max-depth must lie in [0, 64]")
    if not 192 <= arguments.precision_bits <= 1_000_000:
        parser.error("--precision-bits must lie in [192, 1000000]")
    if not 1 <= arguments.max_work <= 100_000_000:
        parser.error("--max-work must lie in [1, 100000000]")

    raw = build_artifact(
        max_depth=arguments.max_depth,
        precision_bits=arguments.precision_bits,
        max_work=arguments.max_work,
    )
    destination = Path(arguments.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)

    summary = json.loads(raw.decode("ascii"))["summary"]
    print(
        json.dumps(
            {
                "non_production_fixture": True,
                "output": str(destination),
                "artifact_sha256": hashlib.sha256(raw).hexdigest(),
                "leaf_count": summary["leaf_count"],
                "leaf_counts_by_edge": summary["leaf_counts_by_edge"],
                "work_count": summary["work_count"],
                "max_depth": summary["max_depth"],
                "rejection_counts": summary["rejection_counts"],
                "max_norm_upper_decimal_outward": summary[
                    "max_norm_upper_decimal_outward"
                ],
                "margin_norm_lower_decimal_outward": summary[
                    "margin_norm_lower_decimal_outward"
                ],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
