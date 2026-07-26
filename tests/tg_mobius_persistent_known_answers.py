#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Metamorphic qualification for the persistent Möbius/Hurst worker.

This registered CTest intentionally qualifies the default 256-row/thread
block-compose identity.  Geometry-sweep binaries use the CUDA KAT instead.
"""

from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tg_verifier.hurst_hybrid_source as strict_hurst  # noqa: E402

NONROOT_DIGEST = "1" * 64
PRODUCTION_PERSISTENT_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_v1"
)
PRODUCTION_PERSISTENT_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-leaf.v1"
)
SEED7_QUALIFICATION_PERSISTENT_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_residue_2357_qualification_v1"
)
SEED7_QUALIFICATION_PERSISTENT_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-residue-2357-"
    "qualification-leaf.v1"
)
SEED11_QUALIFICATION_ONE_SHOT_ALGORITHM = (
    "tg_mobius_compact_mu_residue_235711_qualification_v1"
)
SEED11_RECT_COUNT_EXACT_ONE_SHOT_ALGORITHM = (
    "tg_mobius_compact_mu_residue_235711_"
    "rect2dCountExact_qualification_v1"
)
SEED235_RECT_POWER_ONE_SHOT_ALGORITHM = (
    "tg_mobius_compact_mu_residue_235_"
    "rect2dPower_qualification_v1"
)
SEED235_RECT_POWER_ONE_SHOT_DOMAIN = (
    "sparkinterval.tg.mobius-one-shot-residue-235-"
    "rect2dPower-qualification.v1"
)
SEED11_QUALIFICATION_PERSISTENT_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_residue_235711_qualification_v1"
)
SEED11_QUALIFICATION_PERSISTENT_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-residue-235711-"
    "qualification-leaf.v1"
)
SEED11_RECT_COUNT_EXACT_PERSISTENT_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_residue_235711_"
    "rect2dCountExact_qualification_v1"
)
SEED11_RECT_COUNT_EXACT_PERSISTENT_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-residue_235711_"
    "rect2dCountExact-qualification-leaf.v1"
)
BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_block_compose_"
    "rpt256_rpb65536_qualification_v1"
)
BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-affine-block-compose-"
    "rpt256-rpb65536-qualification-leaf.v1"
)
SEED7_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_residue_2357_block_compose_"
    "rpt256_rpb65536_qualification_v1"
)
SEED7_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-residue-2357-affine-"
    "block-compose-rpt256-rpb65536-qualification-leaf.v1"
)
SEED11_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_residue_235711_block_compose_"
    "rpt256_rpb65536_qualification_v1"
)
SEED11_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-residue-235711-affine-"
    "block-compose-rpt256-rpb65536-qualification-leaf.v1"
)
SEED11_RECT_COUNT_EXACT_BLOCK_COMPOSE_PERSISTENT_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_residue_235711_"
    "rect2dCountExact_block_compose_"
    "rpt256_rpb65536_qualification_v1"
)
SEED11_RECT_COUNT_EXACT_BLOCK_COMPOSE_PERSISTENT_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-residue_235711_"
    "rect2dCountExact-affine-block-compose-"
    "rpt256-rpb65536-qualification-leaf.v1"
)


class KatError(RuntimeError):
    pass


ONE_SHOT_RECTANGULAR_GEOMETRY_FIELDS = (
    (
        "qualification_domain",
        ("qualification_receipt_domain",),
    ),
    (
        "residue_seed",
        ("qualification_rectangular_seed",),
    ),
    (
        "rectangular_mode",
        ("qualification_rectangular_mode",),
    ),
    (
        "rectangular_slots_per_prime",
        ("qualification_rectangular_slots_per_prime",),
    ),
    (
        "rectangular_required_slots_per_prime",
        ("qualification_rectangular_required_slots_per_prime",),
    ),
    (
        "rectangular_events_per_block",
        ("qualification_rectangular_events_per_block",),
    ),
    (
        "rectangular_grid_x",
        ("qualification_rectangular_grid", "x"),
    ),
    (
        "rectangular_grid_y",
        ("qualification_rectangular_grid", "y"),
    ),
    (
        "rectangular_grid_z",
        ("qualification_rectangular_grid", "z"),
    ),
    (
        "rectangular_threads_per_block",
        ("qualification_rectangular_threads_per_block",),
    ),
    (
        "enclosing_super_shard_lower",
        ("qualification_rectangular_enclosing_super_shard_lower",),
    ),
    (
        "enclosing_super_shard_count",
        ("qualification_rectangular_enclosing_super_shard_count",),
    ),
)


def run_json(command: Sequence[str]) -> dict[str, Any]:
    result = subprocess.run(
        list(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise KatError(
            f"{list(command)!r} failed with {result.returncode}: "
            f"{result.stderr.decode(errors='replace')}"
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise KatError(f"{list(command)!r} emitted invalid JSON") from exc
    if not isinstance(value, dict):
        raise KatError("one-shot runner did not emit a JSON object")
    return value


def nested_value(
    report: dict[str, Any], path: Sequence[str],
) -> Any:
    value: Any = report
    for component in path:
        if not isinstance(value, dict) or component not in value:
            raise KatError(
                "one-shot receipt report omitted "
                + ".".join(path)
            )
        value = value[component]
    return value


def set_nested_value(
    report: dict[str, Any], path: Sequence[str], value: Any,
) -> None:
    parent: Any = report
    for component in path[:-1]:
        if not isinstance(parent, dict) or component not in parent:
            raise KatError(
                "one-shot receipt report omitted "
                + ".".join(path)
            )
        parent = parent[component]
    if not isinstance(parent, dict) or path[-1] not in parent:
        raise KatError(
            "one-shot receipt report omitted " + ".".join(path)
        )
    parent[path[-1]] = value


def one_shot_rectangular_canonical_preimage(
    report: dict[str, Any],
    *,
    geometry_order: Sequence[str] | None = None,
    omitted_geometry: frozenset[str] = frozenset(),
) -> str:
    """Independently encode the runner's complete one-shot receipt preimage."""
    if (
        report.get("qualification_residue_rectangular") is not True
        or int(report.get("schema_version", -1)) != 0
        or int(report.get("qualification_mu_bytes_written", -1))
            != int(report["record_count"])
    ):
        raise KatError(
            "one-shot rectangular receipt reconstruction requires a "
            "compact qualification report with complete mu output"
        )

    fields_by_name = dict(ONE_SHOT_RECTANGULAR_GEOMETRY_FIELDS)
    order = (
        tuple(fields_by_name)
        if geometry_order is None
        else tuple(geometry_order)
    )
    if (
        len(order) != len(set(order))
        or any(name not in fields_by_name for name in order)
    ):
        raise KatError("invalid one-shot rectangular geometry field order")

    lines = [f"algorithm={report['algorithm']}\n"]
    for name in order:
        if name in omitted_geometry:
            continue
        lines.append(
            f"{name}={nested_value(report, fields_by_name[name])}\n"
        )

    b1_problem = report["cdem_b1_first_not_proved_safe"]
    b2_problem = report["cdem_b2_first_not_proved_safe"]
    little_211_problem = report[
        "little_mertens_2_11_first_not_proved_safe"
    ]
    little_stronger_problem = report[
        "little_mertens_stronger_first_not_proved_safe"
    ]
    hurst_checks = int(report["hurst_integer_checks"])
    hurst_first_failure = report["hurst_first_failure"]
    hurst_minimum_slack = report["hurst_minimum_squared_slack"]
    hurst_minimum_at = report["hurst_minimum_squared_slack_at"]
    little_211_checks = int(
        report["little_mertens_2_11_real_slab_checks"]
    )
    little_stronger_checks = int(
        report["little_mertens_stronger_real_slab_checks"]
    )

    def problem_value(
        problem: Any, field: str, default: Any,
    ) -> Any:
        if problem is None:
            return default
        if not isinstance(problem, dict) or field not in problem:
            raise KatError(
                f"one-shot receipt problem object omitted {field}"
            )
        return problem[field]

    def zero_when_null(value: Any) -> Any:
        return 0 if value is None else value

    def null_when_no_checks(value: Any, checks: int) -> Any:
        return "null" if checks == 0 else value

    histogram = report["mobius_histogram"]
    lines.extend(
        (
            f"previous={report['previous_receipt_sha256']}\n",
            f"lower={report['lower']}\n",
            f"upper={report['upper']}\n",
            f"incoming_mertens={report['incoming_mertens']}\n",
            f"outgoing_mertens={report['outgoing_mertens']}\n",
            f"incoming_squarefree={report['incoming_squarefree']}\n",
            f"outgoing_squarefree={report['outgoing_squarefree']}\n",
            "little_mertens_scale_bits="
            f"{report['little_mertens_fixed_point_scale_bits']}\n",
            "incoming_little_mertens_lower="
            f"{report['incoming_little_mertens_lower']}\n",
            "incoming_little_mertens_upper="
            f"{report['incoming_little_mertens_upper']}\n",
            "outgoing_little_mertens_lower="
            f"{report['outgoing_little_mertens_lower']}\n",
            "outgoing_little_mertens_upper="
            f"{report['outgoing_little_mertens_upper']}\n",
            "little_mertens_lower_delta="
            f"{report['little_mertens_lower_delta']}\n",
            "little_mertens_upper_delta="
            f"{report['little_mertens_upper_delta']}\n",
            "record_sha256="
            f"{report['gpu_mu_hurst_block_sha256_v1']}\n",
            f"executable_sha256={report['executable_sha256']}\n",
            "density_interval="
            f"{report['squarefree_density_interval_id']}\n",
            f"mu_negative={histogram['-1']}\n",
            f"mu_zero={histogram['0']}\n",
            f"mu_positive={histogram['1']}\n",
            f"hurst_checks={hurst_checks}\n",
            "hurst_first_failure="
            f"{zero_when_null(hurst_first_failure)}\n",
            "hurst_minimum_slack="
            f"{null_when_no_checks(hurst_minimum_slack, hurst_checks)}\n",
            "hurst_minimum_at="
            f"{zero_when_null(hurst_minimum_at)}\n",
            f"b1_checks={report['cdem_b1_endpoint_checks']}\n",
            "b1_problem_n="
            f"{problem_value(b1_problem, 'interval_n', 0)}\n",
            "b1_problem_side="
            f"{problem_value(b1_problem, 'side', 'none')}\n",
            "b1_problem_y="
            f"{problem_value(b1_problem, 'y', 0)}\n",
            f"b2_checks={report['cdem_b2_endpoint_checks']}\n",
            "b2_problem_n="
            f"{problem_value(b2_problem, 'interval_n', 0)}\n",
            "b2_problem_side="
            f"{problem_value(b2_problem, 'side', 'none')}\n",
            "b2_problem_y="
            f"{problem_value(b2_problem, 'y', 0)}\n",
            f"little_mertens_211_checks={little_211_checks}\n",
            "little_mertens_211_problem_n="
            f"{problem_value(little_211_problem, 'interval_floor', 0)}\n",
            "little_mertens_211_problem_right="
            f"{problem_value(little_211_problem, 'right_endpoint', 0)}\n",
            "little_mertens_211_maximum_absolute="
            f"{null_when_no_checks(report[
                'little_mertens_2_11_maximum_interval_absolute_numerator'
            ], little_211_checks)}\n",
            "little_mertens_211_maximum_at="
            f"{zero_when_null(report[
                'little_mertens_2_11_maximum_interval_absolute_at'
            ])}\n",
            "little_mertens_211_maximum_right="
            f"{zero_when_null(report[
                'little_mertens_2_11_maximum_interval_absolute_right_endpoint'
            ])}\n",
            f"little_mertens_stronger_checks={little_stronger_checks}\n",
            "little_mertens_stronger_problem_n="
            f"{problem_value(
                little_stronger_problem, 'interval_floor', 0
            )}\n",
            "little_mertens_stronger_problem_right="
            f"{problem_value(
                little_stronger_problem, 'right_endpoint', 0
            )}\n",
            "little_mertens_stronger_maximum_absolute="
            f"{null_when_no_checks(report[
                'little_mertens_stronger_maximum_interval_absolute_numerator'
            ], little_stronger_checks)}\n",
            "little_mertens_stronger_maximum_at="
            f"{zero_when_null(report[
                'little_mertens_stronger_maximum_interval_absolute_at'
            ])}\n",
            "little_mertens_stronger_maximum_right="
            f"{zero_when_null(report[
                'little_mertens_stronger_maximum_interval_absolute_right_endpoint'
            ])}\n",
        )
    )
    return "".join(lines)


def one_shot_rectangular_receipt_digest(
    report: dict[str, Any],
    *,
    geometry_order: Sequence[str] | None = None,
    omitted_geometry: frozenset[str] = frozenset(),
) -> str:
    preimage = one_shot_rectangular_canonical_preimage(
        report,
        geometry_order=geometry_order,
        omitted_geometry=omitted_geometry,
    )
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def check_one_shot_rectangular_receipt_binding(
    report: dict[str, Any],
) -> None:
    """Check exact reconstruction plus every geometry-field attack."""
    receipt = str(report["receipt_chain_sha256"])
    if one_shot_rectangular_receipt_digest(report) != receipt:
        raise KatError(
            "independent one-shot rectangular canonical receipt "
            "reconstruction failed"
        )

    field_names = tuple(
        name for name, _ in ONE_SHOT_RECTANGULAR_GEOMETRY_FIELDS
    )
    for index, (name, path) in enumerate(
        ONE_SHOT_RECTANGULAR_GEOMETRY_FIELDS
    ):
        mutated = copy.deepcopy(report)
        old_value = nested_value(mutated, path)
        mutation = (
            old_value + 1
            if isinstance(old_value, int)
            else f"{old_value}-tampered"
        )
        set_nested_value(mutated, path, mutation)
        if one_shot_rectangular_receipt_digest(mutated) == receipt:
            raise KatError(
                f"one-shot receipt did not bind mutated {name}"
            )

        if (
            one_shot_rectangular_receipt_digest(
                report, omitted_geometry=frozenset((name,))
            )
            == receipt
        ):
            raise KatError(
                f"one-shot receipt did not bind omitted {name}"
            )

        reordered = list(field_names)
        neighbor = index + 1 if index + 1 < len(reordered) else index - 1
        reordered[index], reordered[neighbor] = (
            reordered[neighbor], reordered[index]
        )
        if (
            one_shot_rectangular_receipt_digest(
                report, geometry_order=reordered
            )
            == receipt
        ):
            raise KatError(
                f"one-shot receipt did not bind the order of {name}"
            )


def run_jsonl(command: Sequence[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        list(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise KatError(
            f"{list(command)!r} failed with {result.returncode}: "
            f"{result.stderr.decode(errors='replace')}"
        )
    records: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise KatError(
                f"{list(command)!r} emitted invalid JSONL"
            ) from exc
        if not isinstance(value, dict):
            raise KatError("persistent runner emitted a non-object record")
        records.append(value)
    if (
        len(records) < 3
        or records[0].get("record") != "header"
        or records[-1].get("record") != "terminal"
        or any(record.get("record") != "leaf" for record in records[1:-1])
    ):
        raise KatError("persistent runner emitted a malformed record sequence")
    return records


def one_shot_command(
    runner: Path,
    roster: Path,
    output: Path,
    *,
    lower: int,
    count: int,
    incoming_mertens: int,
    incoming_squarefree: int,
    incoming_little_lower: int = 0,
    incoming_little_upper: int = 0,
    previous: str = NONROOT_DIGEST,
    affine: bool,
    legacy_one_block_dense: bool = False,
    unseeded_fused_initializer: bool = False,
    residue_2357_seed: bool = False,
    residue_235711_seed: bool = False,
    rectangular_mode: str | None = None,
    transfer_fused_support: bool = False,
) -> list[str]:
    command = [
        str(runner),
        "--lower", str(lower),
        "--count", str(count),
        "--incoming-mertens", str(incoming_mertens),
        "--incoming-squarefree", str(incoming_squarefree),
        "--incoming-little-mertens-lower", str(incoming_little_lower),
        "--incoming-little-mertens-upper", str(incoming_little_upper),
        "--previous-receipt-sha256", previous,
        "--source-prime-roster", str(roster),
        "--compact-mu-output",
        "--fused-support-kernel",
        "--qualification-write-mu", str(output),
        "--allow-other-device",
    ]
    if affine:
        command.append("--affine-mq-gpu-prototype")
    if legacy_one_block_dense:
        command.append("--qualification-legacy-one-block-dense")
    if unseeded_fused_initializer:
        command.append(
            "--qualification-unseeded-fused-initializer"
        )
    if residue_2357_seed:
        command.append("--qualification-residue-2357-seed")
    if residue_235711_seed:
        command.append("--qualification-residue-235711-seed")
    if rectangular_mode is not None:
        command.extend(
            ["--qualification-residue-rectangular", rectangular_mode]
        )
    if transfer_fused_support:
        command.append("--qualification-transfer-fused-support")
    return command


def persistent_command(
    runner: Path,
    roster: Path,
    output: Path | None,
    *,
    lower: int,
    count: int,
    shard_rows: int,
    incoming_mertens: int,
    incoming_squarefree: int,
    previous: str,
    super_shard_rows: int | None = None,
    residue_2357_seed: bool = False,
    residue_235711_seed: bool = False,
    rectangular_mode: str | None = None,
    affine_block_compose: bool = False,
) -> list[str]:
    command = [
        str(runner),
        "--lower", str(lower),
        "--count", str(count),
        "--shard-rows", str(shard_rows),
        "--incoming-mertens", str(incoming_mertens),
        "--incoming-squarefree", str(incoming_squarefree),
        "--previous-leaf-sha256", previous,
        "--source-prime-roster", str(roster),
        "--allow-other-device",
    ]
    if output is not None:
        command.extend(["--qualification-write-mu", str(output)])
    if residue_2357_seed:
        command.append("--qualification-residue-2357-seed")
    if residue_235711_seed:
        command.append("--qualification-residue-235711-seed")
    if rectangular_mode is not None:
        command.extend(
            ["--qualification-residue-rectangular", rectangular_mode]
        )
    if affine_block_compose:
        command.append("--qualification-affine-block-compose")
    if super_shard_rows is not None:
        command.extend(
            ["--super-shard-rows", str(super_shard_rows)]
        )
    return command


def check_affine_summary_crossover(
    persistent: Path,
    roster: Path,
) -> None:
    """Exercise the 256/257 summary boundary through the real support producer."""
    rows_per_block = 65_536
    count = 256 * rows_per_block + 1
    lower = 10_000_000_000_000_000 - count + 1
    common = {
        "lower": lower,
        "count": count,
        "shard_rows": count,
        "super_shard_rows": count,
        "incoming_mertens": 0,
        "incoming_squarefree": 0,
        "previous": NONROOT_DIGEST,
    }
    scan = run_jsonl(
        persistent_command(
            persistent, roster, None, **common,
        )
    )
    compose = run_jsonl(
        persistent_command(
            persistent, roster, None,
            affine_block_compose=True, **common,
        )
    )
    scan_leaf = scan[1]
    compose_header = compose[0]
    compose_leaf = compose[1]
    exact_fields = (
        "delta_mertens",
        "delta_squarefree",
        "hurst_lower",
        "hurst_upper",
        "squarefree_lower",
        "squarefree_upper",
        "poison_count",
    )
    if (
        int(compose_header["affine_block_summary_rows"]) != rows_per_block
        or int(compose_header["affine_block_summary_count"]) != 257
        or any(scan_leaf[field] != compose_leaf[field]
               for field in exact_fields)
    ):
        raise KatError(
            "actual-support 257-summary affine crossover changed semantics"
        )


def endpoint_order(lower: int, witness: int, side: str) -> int:
    return 2 * (witness - lower) - (side == "right_limit")


def combine_affine_reports(
    lower: int,
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    delta_m = int(left["affine_mq_delta_mertens"])
    delta_q = int(left["affine_mq_delta_squarefree"])

    def choose(
        family: str, bound: str, maximum: bool
    ) -> tuple[int, int, str]:
        field = (
            "affine_mq_hurst_guard"
            if family == "hurst"
            else "affine_mq_squarefree_guard"
        )
        witness_field = f"{bound}_witness"
        side_field = f"{bound}_side"
        first = left[field]
        second = right[field]
        shift = delta_m if family == "hurst" else delta_q
        first_value = int(first[bound])
        second_value = int(second[bound]) - shift
        first_side = (
            "integer" if family == "hurst" else str(first[side_field])
        )
        second_side = (
            "integer" if family == "hurst" else str(second[side_field])
        )
        first_order = endpoint_order(
            lower, int(first[witness_field]), first_side
        )
        second_order = endpoint_order(
            lower, int(second[witness_field]), second_side
        )
        first_key = (
            -first_value if maximum else first_value,
            first_order,
        )
        second_key = (
            -second_value if maximum else second_value,
            second_order,
        )
        if second_key < first_key:
            return second_value, int(second[witness_field]), second_side
        return first_value, int(first[witness_field]), first_side

    hl = choose("hurst", "lower", True)
    hu = choose("hurst", "upper", False)
    ql = choose("squarefree", "lower", True)
    qu = choose("squarefree", "upper", False)
    return {
        "m_lower": hl,
        "m_upper": hu,
        "q_lower": ql,
        "q_upper": qu,
    }


def affine_from_one_shot(report: dict[str, Any]) -> dict[str, Any]:
    m = report["affine_mq_hurst_guard"]
    q = report["affine_mq_squarefree_guard"]
    return {
        "m_lower": (
            int(m["lower"]), int(m["lower_witness"]), "integer"
        ),
        "m_upper": (
            int(m["upper"]), int(m["upper_witness"]), "integer"
        ),
        "q_lower": (
            int(q["lower"]), int(q["lower_witness"]),
            str(q["lower_side"]),
        ),
        "q_upper": (
            int(q["upper"]), int(q["upper_witness"]),
            str(q["upper_side"]),
        ),
    }


def check_adjacent_split(
    one_shot: Path,
    roster: Path,
    temporary: Path,
    *,
    name: str,
    lower: int,
    count: int,
    left_count: int,
    affine: bool,
) -> None:
    whole_mu = temporary / f"{name}-whole.mu"
    left_mu = temporary / f"{name}-left.mu"
    right_mu = temporary / f"{name}-right.mu"
    whole = run_json(
        one_shot_command(
            one_shot, roster, whole_mu, lower=lower, count=count,
            incoming_mertens=0, incoming_squarefree=0, affine=affine,
        )
    )
    left = run_json(
        one_shot_command(
            one_shot, roster, left_mu, lower=lower, count=left_count,
            incoming_mertens=0, incoming_squarefree=0, affine=affine,
        )
    )
    right = run_json(
        one_shot_command(
            one_shot, roster, right_mu,
            lower=lower + left_count, count=count - left_count,
            incoming_mertens=int(left["outgoing_mertens"]),
            incoming_squarefree=int(left["outgoing_squarefree"]),
            incoming_little_lower=int(left["outgoing_little_mertens_lower"]),
            incoming_little_upper=int(left["outgoing_little_mertens_upper"]),
            previous=str(left["receipt_chain_sha256"]), affine=affine,
        )
    )
    if whole_mu.read_bytes() != left_mu.read_bytes() + right_mu.read_bytes():
        raise KatError(f"{name}: whole and adjacent-split mu bytes differ")
    if (
        int(whole["delta_mertens"])
        != int(left["delta_mertens"]) + int(right["delta_mertens"])
        or int(whole["segment_squarefree_count"])
        != int(left["segment_squarefree_count"])
        + int(right["segment_squarefree_count"])
    ):
        raise KatError(f"{name}: additive M/Q deltas do not compose")
    if affine:
        combined = combine_affine_reports(lower, left, right)
        if combined != affine_from_one_shot(whole):
            raise KatError(
                f"{name}: translated affine extrema do not compose: "
                f"{combined!r} != {affine_from_one_shot(whole)!r}"
            )


def persistent_terminal_affine(
    terminal: dict[str, Any]
) -> dict[str, Any]:
    def item(name: str, default_side: str) -> tuple[int, int, str]:
        value = terminal[name]
        return (
            int(value["value"]), int(value["witness_y"]),
            str(value.get("side", default_side)),
        )

    return {
        "m_lower": item("global_hurst_lower", "integer"),
        "m_upper": item("global_hurst_upper", "integer"),
        "q_lower": item("global_squarefree_lower", "integer"),
        "q_upper": item("global_squarefree_upper", "integer"),
    }


def persistent_leaf_affine(
    leaf: dict[str, Any]
) -> dict[str, Any]:
    def item(name: str, default_side: str) -> tuple[int, int, str]:
        value = leaf[name]
        return (
            int(value["value"]), int(value["witness_y"]),
            str(value.get("side", default_side)),
        )

    return {
        "m_lower": item("hurst_lower", "integer"),
        "m_upper": item("hurst_upper", "integer"),
        "q_lower": item("squarefree_lower", "integer"),
        "q_upper": item("squarefree_upper", "integer"),
    }


def persistent_leaf_digest(
    leaf: dict[str, Any],
    *,
    executable_sha256: str,
    roster_sha256: str,
    algorithm: str,
    domain: str,
) -> str:
    squarefree_lower_order = 2 * (
        int(leaf["squarefree_lower"]["witness_y"])
        - int(leaf["lower"])
    ) - (
        leaf["squarefree_lower"].get("side", "integer")
        == "right_limit"
    )
    squarefree_upper_order = 2 * (
        int(leaf["squarefree_upper"]["witness_y"])
        - int(leaf["lower"])
    ) - (
        leaf["squarefree_upper"].get("side", "integer")
        == "right_limit"
    )
    canonical = (
        f"domain={domain}\n"
        f"algorithm={algorithm}\n"
    )
    if "qualification_rectangular_mode" in leaf:
        canonical += (
            f"residue_seed={leaf['qualification_rectangular_seed']}\n"
            f"rectangular_mode="
            f"{leaf['qualification_rectangular_mode']}\n"
            f"rectangular_slots_per_prime="
            f"{leaf['qualification_rectangular_slots_per_prime']}\n"
            f"rectangular_required_slots_per_prime="
            f"{leaf['qualification_rectangular_required_slots_per_prime']}\n"
            f"rectangular_events_per_block="
            f"{leaf['qualification_rectangular_events_per_block']}\n"
            f"rectangular_multiblock_prime_count="
            f"{leaf['qualification_rectangular_multiblock_prime_count']}\n"
            f"rectangular_grid_x="
            f"{leaf['qualification_rectangular_grid_x']}\n"
            f"rectangular_grid_y="
            f"{leaf['qualification_rectangular_grid_y']}\n"
            f"rectangular_grid_z="
            f"{leaf['qualification_rectangular_grid_z']}\n"
            f"rectangular_threads_per_block="
            f"{leaf['qualification_rectangular_threads_per_block']}\n"
            f"enclosing_super_shard_lower="
            f"{leaf['qualification_rectangular_enclosing_super_shard_lower']}\n"
            f"enclosing_super_shard_count="
            f"{leaf['qualification_rectangular_enclosing_super_shard_count']}\n"
        )
    canonical += (
        f"executable_sha256={executable_sha256}\n"
        f"prime_roster_sha256={roster_sha256}\n"
        f"previous={leaf['previous_leaf_sha256']}\n"
        f"lower={leaf['lower']}\n"
        f"upper_exclusive={leaf['upper_exclusive']}\n"
        "poison_count=0\n"
        f"incoming_mertens={leaf['incoming_mertens']}\n"
        f"outgoing_mertens={leaf['outgoing_mertens']}\n"
        f"delta_mertens={leaf['delta_mertens']}\n"
        f"incoming_squarefree={leaf['incoming_squarefree']}\n"
        f"outgoing_squarefree={leaf['outgoing_squarefree']}\n"
        f"delta_squarefree={leaf['delta_squarefree']}\n"
        f"hurst_lower={leaf['hurst_lower']['value']}\n"
        f"hurst_lower_y={leaf['hurst_lower']['witness_y']}\n"
        f"hurst_upper={leaf['hurst_upper']['value']}\n"
        f"hurst_upper_y={leaf['hurst_upper']['witness_y']}\n"
        f"squarefree_lower={leaf['squarefree_lower']['value']}\n"
        f"squarefree_lower_y={leaf['squarefree_lower']['witness_y']}\n"
        f"squarefree_lower_order={squarefree_lower_order}\n"
        f"squarefree_upper={leaf['squarefree_upper']['value']}\n"
        f"squarefree_upper_y={leaf['squarefree_upper']['witness_y']}\n"
        f"squarefree_upper_order={squarefree_upper_order}\n"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_strict_production_receipt(
    records: Sequence[dict[str, Any]],
    *,
    runner: Path,
    roster: Path,
    lower: int,
    count: int,
    incoming_mertens: int,
    incoming_squarefree: int,
) -> None:
    if len(records) != 3:
        raise KatError("strict production receipt KAT expected one leaf")
    header, leaf, terminal = records
    upper_exclusive = lower + count
    roster_values = array("I")
    roster_size = roster.stat().st_size
    if roster_size % roster_values.itemsize != 0:
        raise KatError("production roster size is not a u32 array")
    with roster.open("rb") as stream:
        roster_values.fromfile(
            stream, roster_size // roster_values.itemsize
        )
    if sys.byteorder != "little":
        roster_values.byteswap()
    with runner.open("rb") as stream:
        runner_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    with roster.open("rb") as stream:
        roster_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    gpu_range = {
        "lower": lower,
        "upper_exclusive": upper_exclusive,
        "count": count,
    }
    roster_device_bytes = 4 * bisect_right(
        roster_values, math.isqrt(upper_exclusive - 1)
    )
    try:
        strict_hurst._validate_header(
            header,
            gpu_range=gpu_range,
            leaf_rows=count,
            super_rows=count,
            runner_sha256=runner_sha256,
            roster_sha256=roster_sha256,
            roster_device_bytes=roster_device_bytes,
        )
        expected_selected, expected_dense = (
            strict_hurst._expected_selected_prime_counts(
                roster_values,
                super_lower=lower,
                super_count=count,
                source_fast_path=False,
            )
        )
        (
            final_mertens,
            final_squarefree,
            final_leaf,
            extrema,
            source_fast_path,
            super_index,
        ) = strict_hurst._validate_leaf(
            leaf,
            index=0,
            expected_lower=lower,
            expected_previous=NONROOT_DIGEST,
            expected_mertens=incoming_mertens,
            expected_squarefree=incoming_squarefree,
            root_mertens=incoming_mertens,
            root_squarefree=incoming_squarefree,
            source_lower=lower,
            leaf_rows=count,
            super_rows=count,
            source_upper=upper_exclusive,
            executable_sha256=runner_sha256,
            roster_sha256=roster_sha256,
            expected_selected_prime_count=expected_selected,
            expected_dense_prime_count=expected_dense,
        )
        strict_hurst._validate_terminal(
            terminal,
            gpu_range=gpu_range,
            leaf_rows=count,
            super_rows=count,
            leaf_count=1,
            first_mertens=incoming_mertens,
            first_squarefree=incoming_squarefree,
            final_mertens=final_mertens,
            final_squarefree=final_squarefree,
            final_leaf=final_leaf,
            extrema=extrema,
            source_fast_leaf_count=int(source_fast_path),
            source_fast_super_shard_count=int(source_fast_path),
        )
    except strict_hurst.HurstHybridSourceError as exc:
        raise KatError(
            f"actual production runner receipt failed strict verification: {exc}"
        ) from exc
    if (
        super_index != 0
        or expected_dense <= bisect_right(roster_values, 7)
        or int(leaf["dense_prime_count"]) != expected_dense
    ):
        raise KatError(
            "strict production receipt did not place p=11 in the dense suffix"
        )


def check_persistent(
    one_shot: Path,
    persistent: Path,
    roster: Path,
    temporary: Path,
) -> None:
    lower = 10_000_000_000_000_000 - 8_192 + 1
    count = 8_192
    shard_rows = 2_048
    persistent_mu = temporary / "persistent-whole.mu"
    records = run_jsonl(
        persistent_command(
            persistent, roster, persistent_mu, lower=lower, count=count,
            shard_rows=shard_rows, incoming_mertens=0,
            incoming_squarefree=0, previous=NONROOT_DIGEST,
        )
    )
    header, terminal = records[0], records[-1]
    leaves = records[1:-1]
    false_fields = (
        "source_rows_replayed_independently",
        "full_source_range",
        "execution_attested",
        "cuda_or_cpp_compiler_refinement_proved",
        "primitive_mobius_realization_proved",
        "lean_atom_discharged",
        "proves_any_external_atom",
    )
    if any(header.get(field) is not False for field in false_fields):
        raise KatError("persistent header overclaims its trust boundary")
    if (
        header.get("algorithm") != PRODUCTION_PERSISTENT_ALGORITHM
        or "receipt_leaf_domain" in header
        or "qualification_only_not_production_admissible" in header
        or header.get("fused_support_residue_235_initializer") is not True
        or int(header["residue_235_initializer_table_rows"]) != 900
        or int(header["residue_235_initializer_table_bytes"]) != 7_200
        or int(header["fused_multiblock_slots_per_prime"]) != 512
        or int(
            header["fused_multiblock_unseeded_slots_per_prime"]
        ) != 512
        or int(
            header["fused_multiblock_residue_235_slots_per_prime"]
        ) != 512
        or int(
            header[
                "fused_multiblock_residue_235_minimum_safe_slots_per_prime"
            ]
        ) != 147
        or header["residue_235_table_storage"]
        != "fatbinary_device_global_init"
        or int(
            header[
                "residue_235_explicit_h2d_upload_bytes_per_sieve"
            ]
        ) != 0
    ):
        raise KatError(
            "persistent header did not pin the residue-235 initializer"
        )
    if any(leaf.get("affine_candidate_bytes_transferred") != 64
           for leaf in leaves):
        raise KatError("persistent leaf did not transfer one 64-byte candidate")
    if terminal.get("buffers_reused_across_all_leaves") is not True:
        raise KatError("persistent terminal did not report buffer reuse")
    if (
        int(terminal["sieve_launch_count"]) != len(leaves)
        or int(terminal["super_shard_count"]) != len(leaves)
    ):
        raise KatError(
            "default persistent schedule did not use one sieve per leaf"
        )

    # Scheduling is not part of the receipt equation.  One sieve over four
    # leaves must reproduce exactly the same row stream, leaf summaries,
    # digest chain, and terminal state as four independent sieve launches.
    grouped_mu = temporary / "persistent-super-shard.mu"
    grouped_records = run_jsonl(
        persistent_command(
            persistent, roster, grouped_mu,
            lower=lower, count=count, shard_rows=shard_rows,
            super_shard_rows=count, incoming_mertens=0,
            incoming_squarefree=0, previous=NONROOT_DIGEST,
        )
    )
    grouped_leaves = grouped_records[1:-1]
    grouped_terminal = grouped_records[-1]
    if grouped_mu.read_bytes() != persistent_mu.read_bytes():
        raise KatError(
            "one-super-shard and one-sieve-per-leaf mu bytes differ"
        )
    leaf_semantic_fields = (
        "lower",
        "upper_exclusive",
        "count",
        "previous_leaf_sha256",
        "leaf_sha256",
        "qualification_mu_plus_one_sha256",
        "incoming_mertens",
        "outgoing_mertens",
        "delta_mertens",
        "incoming_squarefree",
        "outgoing_squarefree",
        "delta_squarefree",
        "hurst_lower",
        "hurst_upper",
        "squarefree_lower",
        "squarefree_upper",
        "poison_count",
    )
    if len(grouped_leaves) != len(leaves) or any(
        {field: grouped[field] for field in leaf_semantic_fields}
        != {field: plain[field] for field in leaf_semantic_fields}
        for grouped, plain in zip(grouped_leaves, leaves, strict=True)
    ):
        raise KatError(
            "super-shard scheduling changed a receipt leaf summary"
        )
    terminal_semantic_fields = (
        "lower",
        "upper_exclusive",
        "count",
        "leaf_count",
        "final_leaf_sha256",
        "incoming_mertens",
        "outgoing_mertens",
        "delta_mertens",
        "incoming_squarefree",
        "outgoing_squarefree",
        "delta_squarefree",
        "global_hurst_lower",
        "global_hurst_upper",
        "global_squarefree_lower",
        "global_squarefree_upper",
    )
    if {
        field: grouped_terminal[field]
        for field in terminal_semantic_fields
    } != {
        field: terminal[field]
        for field in terminal_semantic_fields
    }:
        raise KatError(
            "super-shard scheduling changed terminal semantics"
        )

    # The optimized production path finalizes each packed support row
    # directly to the exact {mu, mu != 0} scan input.  It must reproduce the
    # qualification byte path's complete receipt semantics while allocating
    # no intermediate device Möbius array.
    production_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=shard_rows,
            incoming_mertens=0, incoming_squarefree=0,
            previous=NONROOT_DIGEST,
        )
    )
    production_header = production_records[0]
    production_leaves = production_records[1:-1]
    production_terminal = production_records[-1]
    if (
        production_header.get("production_fused_prefix_input_path")
        is not True
        or production_header.get("production_split_square_support_path")
        is not True
        or production_header.get("inline_square_modulo_reference_path")
        is not False
        or production_header.get(
            "distinct_factor_events_compute_square_modulo"
        ) is not False
        or production_header.get("separate_square_strike_pass") is not True
        or int(production_header["split_square_dense_prime_limit"]) != 200
        or production_header.get("split_square_operation_order")
        != "initialize_then_distinct_then_square_then_finalize"
        or production_header.get(
            "intermediate_mobius_device_rows_materialized"
        ) is not False
        or int(production_header["mobius_device_bytes"]) != 0
        or header.get("production_fused_prefix_input_path") is not False
        or header.get("production_split_square_support_path") is not False
        or header.get("inline_square_modulo_reference_path") is not True
        or header.get(
            "distinct_factor_events_compute_square_modulo"
        ) is not True
        or header.get("separate_square_strike_pass") is not False
        or header.get(
            "intermediate_mobius_device_rows_materialized"
        ) is not True
    ):
        raise KatError(
            "persistent fused prefix/split-square mode was not pinned"
        )
    production_leaf_fields = tuple(
        field for field in leaf_semantic_fields
        if field != "qualification_mu_plus_one_sha256"
    )
    if len(production_leaves) != len(leaves) or any(
        {field: production[field] for field in production_leaf_fields}
        != {field: qualified[field] for field in production_leaf_fields}
        for production, qualified
        in zip(production_leaves, leaves, strict=True)
    ):
        raise KatError(
            "fused prefix-input path changed a receipt leaf summary"
        )
    if any(
        leaf["qualification_mu_plus_one_sha256"] is not None
        for leaf in production_leaves
    ):
        raise KatError(
            "production fused prefix-input path emitted a row commitment"
        )
    if {
        field: production_terminal[field]
        for field in terminal_semantic_fields
    } != {
        field: terminal[field]
        for field in terminal_semantic_fields
    }:
        raise KatError(
            "fused prefix-input path changed terminal semantics"
        )
    if (
        int(grouped_terminal["sieve_launch_count"]) != 1
        or int(grouped_terminal["super_shard_count"]) != 1
        or int(grouped_terminal[
            "sieve_launches_saved_vs_leaf_schedule"
        ]) != len(leaves) - 1
    ):
        raise KatError(
            "grouped persistent schedule did not report one sieve"
        )

    one_shot_mu = temporary / "persistent-fresh-whole.mu"
    whole = run_json(
        one_shot_command(
            one_shot, roster, one_shot_mu, lower=lower, count=count,
            incoming_mertens=0, incoming_squarefree=0, affine=True,
        )
    )
    if persistent_mu.read_bytes() != one_shot_mu.read_bytes():
        raise KatError("persistent reused buffers differ from fresh one-shot mu")
    if (
        int(terminal["delta_mertens"])
        != int(whole["affine_mq_delta_mertens"])
        or int(terminal["delta_squarefree"])
        != int(whole["affine_mq_delta_squarefree"])
        or persistent_terminal_affine(terminal)
        != affine_from_one_shot(whole)
    ):
        raise KatError("persistent terminal differs from fresh one-shot affine")

    whole_mu = persistent_mu.read_bytes()
    for index, leaf in enumerate(leaves):
        fresh_mu = temporary / f"persistent-fresh-leaf-{index}.mu"
        fresh = run_json(
            one_shot_command(
                one_shot, roster, fresh_mu,
                lower=int(leaf["lower"]), count=int(leaf["count"]),
                incoming_mertens=int(leaf["incoming_mertens"]),
                incoming_squarefree=int(leaf["incoming_squarefree"]),
                affine=True,
            )
        )
        start = int(leaf["lower"]) - lower
        stop = start + int(leaf["count"])
        if fresh_mu.read_bytes() != whole_mu[start:stop]:
            raise KatError(f"fresh leaf {index} differs from persistent mu")
        if (
            int(fresh["affine_mq_delta_mertens"])
            != int(leaf["delta_mertens"])
            or int(fresh["affine_mq_delta_squarefree"])
            != int(leaf["delta_squarefree"])
            or affine_from_one_shot(fresh)
            != persistent_leaf_affine(leaf)
        ):
            raise KatError(f"fresh leaf {index} delta/affine summary differs")

    # Every completed leaf is a restart checkpoint.  Starting at each
    # boundary must reproduce all subsequent leaf digests and row bytes.
    for boundary in range(1, len(leaves)):
        prior = leaves[boundary - 1]
        suffix_mu = temporary / f"persistent-restart-{boundary}.mu"
        suffix_lower = int(leaves[boundary]["lower"])
        suffix_count = lower + count - suffix_lower
        suffix_records = run_jsonl(
            persistent_command(
                persistent, roster, suffix_mu,
                lower=suffix_lower, count=suffix_count,
                shard_rows=shard_rows,
                incoming_mertens=int(prior["outgoing_mertens"]),
                incoming_squarefree=int(prior["outgoing_squarefree"]),
                previous=str(prior["leaf_sha256"]),
            )
        )
        suffix_leaves = suffix_records[1:-1]
        if [item["leaf_sha256"] for item in suffix_leaves] != [
            item["leaf_sha256"] for item in leaves[boundary:]
        ]:
            raise KatError(
                f"restart at boundary {boundary} changed the leaf chain"
            )
        offset = suffix_lower - lower
        if suffix_mu.read_bytes() != whole_mu[offset:]:
            raise KatError(
                f"restart at boundary {boundary} changed mu bytes"
            )
        if (
            suffix_records[-1]["outgoing_mertens"]
            != terminal["outgoing_mertens"]
            or suffix_records[-1]["outgoing_squarefree"]
            != terminal["outgoing_squarefree"]
            or suffix_records[-1]["final_leaf_sha256"]
            != terminal["final_leaf_sha256"]
        ):
            raise KatError(
                f"restart at boundary {boundary} changed terminal state"
            )


def check_balanced_vs_legacy(
    one_shot: Path,
    roster: Path,
    temporary: Path,
) -> None:
    # A block owns 256*4096 = 1,048,576 multiple ordinals.  This odd count
    # starts at an even lower bound, so p=2 has 1,048,577 multiples and the
    # test necessarily exercises block ordinal one, not merely empty fixed
    # slots behind the first block.
    count = 2 * 1_048_576 + 1
    lower = 10_000_000_000_000_000 - count + 1
    balanced_mu = temporary / "balanced-high.mu"
    unseeded_mu = temporary / "unseeded-high.mu"
    legacy_mu = temporary / "legacy-high.mu"
    seed7_mu = temporary / "seed7-high.mu"
    balanced = run_json(
        one_shot_command(
            one_shot, roster, balanced_mu,
            lower=lower, count=count, incoming_mertens=0,
            incoming_squarefree=0, affine=True,
            transfer_fused_support=True,
        )
    )
    unseeded = run_json(
        one_shot_command(
            one_shot, roster, unseeded_mu,
            lower=lower, count=count, incoming_mertens=0,
            incoming_squarefree=0, affine=True,
            unseeded_fused_initializer=True,
            transfer_fused_support=True,
        )
    )
    legacy = run_json(
        one_shot_command(
            one_shot, roster, legacy_mu,
            lower=lower, count=count, incoming_mertens=0,
            incoming_squarefree=0, affine=True,
            legacy_one_block_dense=True,
            transfer_fused_support=True,
        )
    )
    seed7 = run_json(
        one_shot_command(
            one_shot, roster, seed7_mu,
            lower=lower, count=count, incoming_mertens=0,
            incoming_squarefree=0, affine=True,
            residue_2357_seed=True,
            transfer_fused_support=True,
        )
    )
    if (
        balanced_mu.read_bytes() != unseeded_mu.read_bytes()
        or balanced_mu.read_bytes() != legacy_mu.read_bytes()
        or balanced_mu.read_bytes() != seed7_mu.read_bytes()
    ):
        raise KatError(
            "residue-235, unseeded, and legacy high-range mu bytes differ"
        )
    exact_fields = (
        "gpu_record_sha256_le_v1",
        "gpu_mu_hurst_block_sha256_v1",
        "delta_mertens",
        "segment_squarefree_count",
        "mobius_histogram",
        "affine_mq_delta_mertens",
        "affine_mq_delta_squarefree",
        "affine_mq_hurst_guard",
        "affine_mq_squarefree_guard",
        "receipt_chain_sha256",
        "mismatch_count",
        "fused_support_poison_count",
    )
    if any(
        balanced[field] != unseeded[field]
        or balanced[field] != legacy[field]
        or balanced[field] != seed7[field]
        for field in exact_fields
    ):
        raise KatError(
            "residue-235, unseeded, and legacy high-range "
            "full outputs differ"
        )
    if (
        balanced[
            "fused_support_load_balanced_dense_schedule"
        ] is not True
        or balanced[
            "fused_support_residue_235_initializer"
        ] is not True
        or balanced[
            "qualification_legacy_one_block_dense"
        ] is not False
        or unseeded[
            "fused_support_load_balanced_dense_schedule"
        ] is not True
        or unseeded[
            "fused_support_residue_235_initializer"
        ] is not False
        or unseeded[
            "qualification_unseeded_fused_initializer"
        ] is not True
        or legacy[
            "fused_support_load_balanced_dense_schedule"
        ] is not False
        or legacy[
            "fused_support_residue_235_initializer"
        ] is not False
        or legacy[
            "qualification_legacy_one_block_dense"
        ] is not True
        or int(balanced[
            "fused_multiblock_dense_prime_limit"
        ]) != 200
        or int(balanced[
            "fused_multiblock_slots_per_prime"
        ]) != 512
        or int(balanced[
            "fused_multiblock_unseeded_slots_per_prime"
        ]) != 512
        or int(balanced[
            "fused_multiblock_residue_235_slots_per_prime"
        ]) != 512
        or int(balanced[
            "fused_multiblock_residue_235_minimum_safe_slots_per_prime"
        ]) != 147
        or seed7["qualification_residue_2357_seed"] is not True
        or seed7["residue_2357_initializer_uses_residue_235_table"]
            is not True
        or int(seed7["residue_2357_per_row_modulus"]) != 49
        or int(seed7["residue_2357_materialized_table_rows"]) != 0
        or int(seed7[
            "fused_multiblock_residue_2357_minimum_safe_slots_per_prime"
        ]) != 94
        or int(seed7[
            "fused_multiblock_residue_2357_slots_per_prime"
        ]) < 94
        or int(seed7["fused_multiblock_slots_per_prime"]) != int(
            seed7["fused_multiblock_residue_2357_slots_per_prime"]
        )
        or int(unseeded[
            "fused_multiblock_slots_per_prime"
        ]) != 512
        or int(balanced[
            "fused_multiblock_iterations_per_thread"
        ]) != 4_096
        or balanced[
            "all_records_compared_with_independent_cpu_segmented_sieve"
        ] is not True
        or legacy[
            "all_records_compared_with_independent_cpu_segmented_sieve"
        ] is not True
    ):
        raise KatError(
            "balanced/legacy qualification-mode flags are wrong"
        )


def check_residue_2357_235711_multislot_persistent(
    one_shot: Path,
    persistent: Path,
    roster: Path,
    temporary: Path,
) -> None:
    events_per_block = 256 * 4_096
    count = 13 * events_per_block + 1
    lower = 9_999_999_986_368_392
    incoming_mertens = 0
    incoming_squarefree = 6_079_271_010_000_000
    if (
        count <= 13_631_488
        or lower % 11 != 0
        or lower % 13 != 0
        or 1 + (count - 1) // 13 != events_per_block + 1
        or 1 + (count - 1) // 11 <= events_per_block
    ):
        raise KatError(
            "seed7/seed11 multi-slot p=11/p=13 KAT parameters are invalid"
        )

    production_mu = temporary / "seed7-multislot-production.mu"
    seed7_mu = temporary / "seed7-multislot-candidate.mu"
    seed11_mu = temporary / "seed11-multislot-candidate.mu"
    seed11_rect_mu = (
        temporary / "seed11-rect-count-exact-multislot-candidate.mu"
    )
    production = run_json(
        one_shot_command(
            one_shot, roster, production_mu,
            lower=lower, count=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            affine=True, transfer_fused_support=True,
        )
    )
    seed7 = run_json(
        one_shot_command(
            one_shot, roster, seed7_mu,
            lower=lower, count=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            affine=True, residue_2357_seed=True,
            transfer_fused_support=True,
        )
    )
    seed11 = run_json(
        one_shot_command(
            one_shot, roster, seed11_mu,
            lower=lower, count=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            affine=True, residue_235711_seed=True,
            transfer_fused_support=True,
        )
    )
    seed11_rect = run_json(
        one_shot_command(
            one_shot, roster, seed11_rect_mu,
            lower=lower, count=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            affine=True, residue_235711_seed=True,
            rectangular_mode="rect2dCountExact",
            transfer_fused_support=True,
        )
    )
    check_one_shot_rectangular_receipt_binding(seed11_rect)
    if (
        production_mu.read_bytes() != seed7_mu.read_bytes()
        or production_mu.read_bytes() != seed11_mu.read_bytes()
        or production_mu.read_bytes() != seed11_rect_mu.read_bytes()
    ):
        raise KatError(
            "multi-slot p=11/p=13 seed7, seed11, and production mu "
            "bytes differ"
        )
    one_shot_exact_fields = (
        "gpu_record_sha256_le_v1",
        "gpu_mu_hurst_block_sha256_v1",
        "delta_mertens",
        "segment_squarefree_count",
        "mobius_histogram",
        "affine_mq_delta_mertens",
        "affine_mq_delta_squarefree",
        "affine_mq_hurst_guard",
        "affine_mq_squarefree_guard",
        "receipt_chain_sha256",
        "mismatch_count",
        "fused_support_poison_count",
    )
    if any(
        production[field] != seed7[field]
        for field in one_shot_exact_fields
    ):
        raise KatError(
            "multi-slot p=11 seed7 and production exact reports differ"
        )
    seed11_semantic_fields = tuple(
        field for field in one_shot_exact_fields
        if field != "receipt_chain_sha256"
    )
    if any(
        production[field] != seed11[field]
        for field in seed11_semantic_fields
    ):
        raise KatError(
            "multi-slot p=13 seed11 and production exact semantics differ"
        )
    if any(
        production[field] != seed11_rect[field]
        for field in seed11_semantic_fields
    ):
        raise KatError(
            "live second-slot p13 rectangular and production semantics differ"
        )
    for name, report in (
        ("production", production),
        ("seed7", seed7),
        ("seed11", seed11),
        ("seed11-rect-count-exact", seed11_rect),
    ):
        if (
            report[
                "all_records_compared_with_independent_cpu_segmented_sieve"
            ] is not True
            or report[
                "all_gpu_mu_values_compared_with_independent_cpu_segmented_sieve"
            ] is not True
            or int(report["mismatch_count"]) != 0
            or int(report["fused_support_poison_count"]) != 0
        ):
            raise KatError(
                f"multi-slot p=11 {name} run did not pass its CPU oracle"
            )
    if (
        production["qualification_residue_2357_seed"] is not False
        or seed7["qualification_residue_2357_seed"] is not True
        or seed11["algorithm"]
            != SEED11_QUALIFICATION_ONE_SHOT_ALGORITHM
        or seed11["qualification_residue_235711_seed"] is not True
        or int(seed11["residue_seed_prime_count"]) != 5
        or int(seed11["residue_235711_per_row_modulus"]) != 121
        or int(seed11[
            "fused_multiblock_residue_235711_minimum_safe_slots_per_prime"
        ]) != 79
        or int(seed11[
            "fused_multiblock_residue_235711_slots_per_prime"
        ]) != 512
        or seed11["receipt_chain_sha256"]
            == production["receipt_chain_sha256"]
        or seed11_rect["algorithm"]
            != SEED11_RECT_COUNT_EXACT_ONE_SHOT_ALGORITHM
        or seed11_rect["qualification_residue_rectangular"] is not True
        or seed11_rect["qualification_rectangular_seed"] != "235711"
        or seed11_rect["qualification_rectangular_mode"]
            != "rect2dCountExact"
        or int(seed11_rect[
            "qualification_rectangular_required_slots_per_prime"
        ]) != 2
        or int(seed11_rect[
            "qualification_rectangular_slots_per_prime"
        ]) != 2
        or int(seed11_rect[
            "qualification_rectangular_events_per_block"
        ]) != events_per_block
        or int(seed11_rect[
            "qualification_rectangular_multiblock_prime_count"
        ]) <= 0
        or int(seed11_rect[
            "qualification_rectangular_grid"
        ]["x"]) != 2
        or int(seed11_rect[
            "qualification_rectangular_grid"
        ]["y"]) <= 0
        or seed11_rect["receipt_chain_sha256"]
            in {
                production["receipt_chain_sha256"],
                seed11["receipt_chain_sha256"],
            }
        or int(production["dense_prime_count"]) < 5
        or int(seed7["dense_prime_count"]) < 5
        or int(seed11["dense_prime_count"]) < 6
        or int(seed11_rect["dense_prime_count"]) < 6
    ):
        raise KatError(
            "multi-slot p=11/p=13 one-shot route identity/coverage changed"
        )

    production_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=count,
            super_shard_rows=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            previous=NONROOT_DIGEST,
        )
    )
    seed7_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=count,
            super_shard_rows=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            previous=NONROOT_DIGEST,
            residue_2357_seed=True,
        )
    )
    seed11_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=count,
            super_shard_rows=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            previous=NONROOT_DIGEST,
            residue_235711_seed=True,
        )
    )
    seed11_rect_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=count,
            super_shard_rows=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            previous=NONROOT_DIGEST,
            residue_235711_seed=True,
            rectangular_mode="rect2dCountExact",
        )
    )
    block_compose_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=count,
            super_shard_rows=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            previous=NONROOT_DIGEST,
            affine_block_compose=True,
        )
    )
    seed7_block_compose_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=count,
            super_shard_rows=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            previous=NONROOT_DIGEST,
            residue_2357_seed=True,
            affine_block_compose=True,
        )
    )
    seed11_block_compose_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=count,
            super_shard_rows=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            previous=NONROOT_DIGEST,
            residue_235711_seed=True,
            affine_block_compose=True,
        )
    )
    seed11_rect_block_compose_records = run_jsonl(
        persistent_command(
            persistent, roster, None,
            lower=lower, count=count, shard_rows=count,
            super_shard_rows=count,
            incoming_mertens=incoming_mertens,
            incoming_squarefree=incoming_squarefree,
            previous=NONROOT_DIGEST,
            residue_235711_seed=True,
            rectangular_mode="rect2dCountExact",
            affine_block_compose=True,
        )
    )
    production_header = production_records[0]
    seed7_header = seed7_records[0]
    seed11_header = seed11_records[0]
    seed11_rect_header = seed11_rect_records[0]
    block_compose_header = block_compose_records[0]
    seed7_block_compose_header = seed7_block_compose_records[0]
    seed11_block_compose_header = seed11_block_compose_records[0]
    seed11_rect_block_compose_header = (
        seed11_rect_block_compose_records[0]
    )
    production_leaf = production_records[1]
    seed7_leaf = seed7_records[1]
    seed11_leaf = seed11_records[1]
    seed11_rect_leaf = seed11_rect_records[1]
    block_compose_leaf = block_compose_records[1]
    seed7_block_compose_leaf = seed7_block_compose_records[1]
    seed11_block_compose_leaf = seed11_block_compose_records[1]
    seed11_rect_block_compose_leaf = (
        seed11_rect_block_compose_records[1]
    )
    production_terminal = production_records[2]
    seed7_terminal = seed7_records[2]
    seed11_terminal = seed11_records[2]
    seed11_rect_terminal = seed11_rect_records[2]
    block_compose_terminal = block_compose_records[2]
    seed7_block_compose_terminal = seed7_block_compose_records[2]
    seed11_block_compose_terminal = seed11_block_compose_records[2]
    seed11_rect_block_compose_terminal = (
        seed11_rect_block_compose_records[2]
    )
    check_strict_production_receipt(
        production_records,
        runner=persistent,
        roster=roster,
        lower=lower,
        count=count,
        incoming_mertens=incoming_mertens,
        incoming_squarefree=incoming_squarefree,
    )

    if (
        production_header["algorithm"]
        != PRODUCTION_PERSISTENT_ALGORITHM
        or "receipt_leaf_domain" in production_header
        or "qualification_only_not_production_admissible"
        in production_header
        or seed7_header["algorithm"]
        != SEED7_QUALIFICATION_PERSISTENT_ALGORITHM
        or seed7_header["receipt_leaf_domain"]
        != SEED7_QUALIFICATION_PERSISTENT_LEAF_DOMAIN
        or seed7_header[
            "qualification_only_not_production_admissible"
        ] is not True
        or seed7_header["qualification_residue_2357_seed"] is not True
    ):
        raise KatError(
            "persistent seed7 qualification identity is not fail-closed"
        )
    if (
        seed11_header["algorithm"]
            != SEED11_QUALIFICATION_PERSISTENT_ALGORITHM
        or seed11_header["receipt_leaf_domain"]
            != SEED11_QUALIFICATION_PERSISTENT_LEAF_DOMAIN
        or seed11_header[
            "qualification_only_not_production_admissible"
        ] is not True
        or seed11_header["qualification_residue_235711_seed"] is not True
        or int(seed11_header["residue_seed_prime_count"]) != 5
        or int(seed11_header["residue_235711_per_row_modulus"]) != 121
        or int(seed11_header[
            "fused_multiblock_residue_235711_minimum_safe_slots_per_prime"
        ]) != 79
        or int(seed11_header[
            "fused_multiblock_residue_235711_slots_per_prime"
        ]) != 512
    ):
        raise KatError(
            "persistent seed11 qualification identity is not fail-closed"
        )
    if (
        seed11_rect_header["algorithm"]
            != SEED11_RECT_COUNT_EXACT_PERSISTENT_ALGORITHM
        or seed11_rect_header["receipt_leaf_domain"]
            != SEED11_RECT_COUNT_EXACT_PERSISTENT_LEAF_DOMAIN
        or seed11_rect_header[
            "qualification_only_not_production_admissible"
        ] is not True
        or seed11_rect_header[
            "qualification_residue_rectangular"
        ] is not True
        or seed11_rect_header["qualification_rectangular_seed"]
            != "235711"
        or seed11_rect_header["qualification_rectangular_mode"]
            != "rect2dCountExact"
        or int(seed11_rect_header[
            "qualification_rectangular_header_required_slots_per_prime"
        ]) != 2
        or int(seed11_rect_header[
            "qualification_rectangular_header_slots_per_prime"
        ]) != 2
    ):
        raise KatError(
            "persistent rectangular qualification header is not bound"
        )
    if (
        "algorithm" in production_leaf
        or "receipt_leaf_domain" in production_leaf
        or "qualification_only_not_production_admissible"
        in production_leaf
        or production_terminal.get("algorithm")
        != PRODUCTION_PERSISTENT_ALGORITHM
        or "receipt_leaf_domain" in production_terminal
        or "qualification_only_not_production_admissible"
        in production_terminal
    ):
        raise KatError("production persistent identity changed")
    for record in (seed7_leaf, seed7_terminal):
        if (
            record["algorithm"]
            != SEED7_QUALIFICATION_PERSISTENT_ALGORITHM
            or record["receipt_leaf_domain"]
            != SEED7_QUALIFICATION_PERSISTENT_LEAF_DOMAIN
            or record[
                "qualification_only_not_production_admissible"
            ] is not True
        ):
            raise KatError(
                "seed7 leaf/terminal omitted the qualification identity"
            )
    for record in (seed11_leaf, seed11_terminal):
        if (
            record["algorithm"]
            != SEED11_QUALIFICATION_PERSISTENT_ALGORITHM
            or record["receipt_leaf_domain"]
            != SEED11_QUALIFICATION_PERSISTENT_LEAF_DOMAIN
            or record[
                "qualification_only_not_production_admissible"
            ] is not True
        ):
            raise KatError(
                "seed11 leaf/terminal omitted the qualification identity"
            )
    for record in (seed11_rect_leaf, seed11_rect_terminal):
        if (
            record["algorithm"]
            != SEED11_RECT_COUNT_EXACT_PERSISTENT_ALGORITHM
            or record["receipt_leaf_domain"]
            != SEED11_RECT_COUNT_EXACT_PERSISTENT_LEAF_DOMAIN
            or record[
                "qualification_only_not_production_admissible"
            ] is not True
        ):
            raise KatError(
                "rectangular leaf/terminal omitted its qualification identity"
            )
    if (
        seed11_rect_leaf["qualification_rectangular_seed"] != "235711"
        or seed11_rect_leaf["qualification_rectangular_mode"]
            != "rect2dCountExact"
        or int(seed11_rect_leaf[
            "qualification_rectangular_required_slots_per_prime"
        ]) != 2
        or int(seed11_rect_leaf[
            "qualification_rectangular_slots_per_prime"
        ]) != 2
        or int(seed11_rect_leaf[
            "qualification_rectangular_events_per_block"
        ]) != events_per_block
        or int(seed11_rect_leaf[
            "qualification_rectangular_multiblock_prime_count"
        ]) <= 0
        or int(seed11_rect_leaf[
            "qualification_rectangular_grid_x"
        ]) != 2
        or int(seed11_rect_leaf[
            "qualification_rectangular_grid_y"
        ]) <= 0
        or int(seed11_rect_leaf[
            "qualification_rectangular_enclosing_super_shard_lower"
        ]) != lower
        or int(seed11_rect_leaf[
            "qualification_rectangular_enclosing_super_shard_count"
        ]) != count
    ):
        raise KatError(
            "persistent live second-slot p13 geometry is not inspectable"
        )
    for name, header, leaf, terminal, algorithm, domain in (
        (
            "block-compose", block_compose_header,
            block_compose_leaf, block_compose_terminal,
            BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM,
            BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed7-block-compose", seed7_block_compose_header,
            seed7_block_compose_leaf, seed7_block_compose_terminal,
            SEED7_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM,
            SEED7_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed11-block-compose", seed11_block_compose_header,
            seed11_block_compose_leaf, seed11_block_compose_terminal,
            SEED11_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM,
            SEED11_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed11-rect-count-exact-block-compose",
            seed11_rect_block_compose_header,
            seed11_rect_block_compose_leaf,
            seed11_rect_block_compose_terminal,
            SEED11_RECT_COUNT_EXACT_BLOCK_COMPOSE_PERSISTENT_ALGORITHM,
            SEED11_RECT_COUNT_EXACT_BLOCK_COMPOSE_PERSISTENT_LEAF_DOMAIN,
        ),
    ):
        if (
            header["algorithm"] != algorithm
            or header["receipt_leaf_domain"] != domain
            or header[
                "qualification_only_not_production_admissible"
            ] is not True
            or header["qualification_affine_block_compose"] is not True
            or header["production_fused_prefix_input_path"] is not False
            or header["qualification_fused_prefix_input_path"] is not False
            or header[
                "qualification_direct_fused_support_block_compose_path"
            ] is not True
            or leaf["algorithm"] != algorithm
            or leaf["receipt_leaf_domain"] != domain
            or leaf[
                "qualification_only_not_production_admissible"
            ] is not True
            or terminal["algorithm"] != algorithm
            or terminal["receipt_leaf_domain"] != domain
            or terminal[
                "qualification_only_not_production_admissible"
            ] is not True
        ):
            raise KatError(
                f"{name} qualification identity is not fail-closed"
            )

    leaf_semantic_fields = (
        "lower",
        "upper_exclusive",
        "count",
        "previous_leaf_sha256",
        "incoming_mertens",
        "outgoing_mertens",
        "delta_mertens",
        "incoming_squarefree",
        "outgoing_squarefree",
        "delta_squarefree",
        "hurst_lower",
        "hurst_upper",
        "squarefree_lower",
        "squarefree_upper",
        "poison_count",
    )
    if any(
        production_leaf[field] != seed7_leaf[field]
        for field in leaf_semantic_fields
    ):
        raise KatError(
            "persistent multi-slot seed7 leaf semantics differ from production"
        )
    if any(
        production_leaf[field] != seed11_leaf[field]
        for field in leaf_semantic_fields
    ):
        raise KatError(
            "persistent multi-slot seed11 leaf semantics differ from "
            "production"
        )
    if any(
        production_leaf[field] != seed11_rect_leaf[field]
        for field in leaf_semantic_fields
    ):
        raise KatError(
            "persistent rectangular leaf semantics differ from production"
        )
    for name, leaf in (
        ("block-compose", block_compose_leaf),
        ("seed7-block-compose", seed7_block_compose_leaf),
        ("seed11-block-compose", seed11_block_compose_leaf),
        (
            "seed11-rect-count-exact-block-compose",
            seed11_rect_block_compose_leaf,
        ),
    ):
        if any(
            production_leaf[field] != leaf[field]
            for field in leaf_semantic_fields
        ):
            raise KatError(
                f"persistent multi-slot {name} leaf semantics "
                "differ from production"
            )
    terminal_semantic_fields = (
        "lower",
        "upper_exclusive",
        "count",
        "leaf_count",
        "incoming_mertens",
        "outgoing_mertens",
        "delta_mertens",
        "incoming_squarefree",
        "outgoing_squarefree",
        "delta_squarefree",
        "global_hurst_lower",
        "global_hurst_upper",
        "global_squarefree_lower",
        "global_squarefree_upper",
    )
    if any(
        production_terminal[field] != seed7_terminal[field]
        for field in terminal_semantic_fields
    ):
        raise KatError(
            "persistent multi-slot seed7 terminal differs from production"
        )
    if any(
        production_terminal[field] != seed11_terminal[field]
        for field in terminal_semantic_fields
    ):
        raise KatError(
            "persistent multi-slot seed11 terminal differs from production"
        )
    if any(
        production_terminal[field] != seed11_rect_terminal[field]
        for field in terminal_semantic_fields
    ):
        raise KatError(
            "persistent rectangular terminal differs from production"
        )
    for name, terminal in (
        ("block-compose", block_compose_terminal),
        ("seed7-block-compose", seed7_block_compose_terminal),
        ("seed11-block-compose", seed11_block_compose_terminal),
        (
            "seed11-rect-count-exact-block-compose",
            seed11_rect_block_compose_terminal,
        ),
    ):
        if any(
            production_terminal[field] != terminal[field]
            for field in terminal_semantic_fields
        ):
            raise KatError(
                f"persistent multi-slot {name} terminal differs "
                "from production"
            )
    if (
        production_leaf["leaf_sha256"] == seed7_leaf["leaf_sha256"]
        or production_terminal["final_leaf_sha256"]
        == seed7_terminal["final_leaf_sha256"]
    ):
        raise KatError(
            "seed7 qualification receipt domain collided with production"
        )
    distinct_leaf_digests = {
        production_leaf["leaf_sha256"],
        seed7_leaf["leaf_sha256"],
        seed11_leaf["leaf_sha256"],
        seed11_rect_leaf["leaf_sha256"],
        block_compose_leaf["leaf_sha256"],
        seed7_block_compose_leaf["leaf_sha256"],
        seed11_block_compose_leaf["leaf_sha256"],
        seed11_rect_block_compose_leaf["leaf_sha256"],
    }
    if len(distinct_leaf_digests) != 8:
        raise KatError(
            "the eight persistent production/qualification identities "
            "collided"
        )
    for name, header, leaf, terminal, algorithm, domain in (
        (
            "production", production_header, production_leaf,
            production_terminal, PRODUCTION_PERSISTENT_ALGORITHM,
            PRODUCTION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed7", seed7_header, seed7_leaf, seed7_terminal,
            SEED7_QUALIFICATION_PERSISTENT_ALGORITHM,
            SEED7_QUALIFICATION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed11", seed11_header, seed11_leaf, seed11_terminal,
            SEED11_QUALIFICATION_PERSISTENT_ALGORITHM,
            SEED11_QUALIFICATION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed11-rect-count-exact",
            seed11_rect_header, seed11_rect_leaf,
            seed11_rect_terminal,
            SEED11_RECT_COUNT_EXACT_PERSISTENT_ALGORITHM,
            SEED11_RECT_COUNT_EXACT_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "block-compose", block_compose_header,
            block_compose_leaf, block_compose_terminal,
            BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM,
            BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed7-block-compose", seed7_block_compose_header,
            seed7_block_compose_leaf, seed7_block_compose_terminal,
            SEED7_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM,
            SEED7_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed11-block-compose", seed11_block_compose_header,
            seed11_block_compose_leaf, seed11_block_compose_terminal,
            SEED11_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_ALGORITHM,
            SEED11_BLOCK_COMPOSE_QUALIFICATION_PERSISTENT_LEAF_DOMAIN,
        ),
        (
            "seed11-rect-count-exact-block-compose",
            seed11_rect_block_compose_header,
            seed11_rect_block_compose_leaf,
            seed11_rect_block_compose_terminal,
            SEED11_RECT_COUNT_EXACT_BLOCK_COMPOSE_PERSISTENT_ALGORITHM,
            SEED11_RECT_COUNT_EXACT_BLOCK_COMPOSE_PERSISTENT_LEAF_DOMAIN,
        ),
    ):
        if (
            leaf["leaf_sha256"]
            != persistent_leaf_digest(
                leaf,
                executable_sha256=str(header["executable_sha256"]),
                roster_sha256=str(header["prime_roster_sha256"]),
                algorithm=algorithm,
                domain=domain,
            )
            or terminal["final_leaf_sha256"] != leaf["leaf_sha256"]
            or int(leaf["selected_prime_count"]) < 5
            or int(leaf["dense_prime_count"]) < 5
        ):
            raise KatError(
                f"multi-slot p=11 {name} leaf commitment/coverage changed"
            )
    scan_allocation = int(
        production_header["persistent_device_allocation_bytes"]
    )
    compose_allocation = int(
        block_compose_header["persistent_device_allocation_bytes"]
    )
    exact_saved = (
        int(production_header["affine_prefix_device_bytes"])
        + int(production_header["affine_workspace_device_bytes"])
        - int(block_compose_header["affine_prefix_device_bytes"])
        - int(block_compose_header[
            "affine_block_summary_device_bytes"
        ])
    )
    # Fail closed before applying the default identity and byte-accounting
    # expectations below.  The runner reports the kernel's queried geometry.
    if (
        int(block_compose_header[
            "affine_block_summary_rows_per_thread"
        ]) != 256
        or int(block_compose_header[
            "affine_block_summary_rows"
        ]) != 65_536
        or int(block_compose_header[
            "affine_scan_prefix_reference_device_bytes"
        ]) != int(production_header["affine_prefix_device_bytes"])
        or block_compose_header[
            "affine_block_compose_scan_workspace_omitted"
        ] is not True
        or int(block_compose_header[
            "affine_workspace_device_bytes"
        ]) != 0
        or scan_allocation - compose_allocation != exact_saved
        or int(block_compose_header[
            "affine_block_compose_net_device_bytes_vs_scan_"
            "excluding_scan_workspace"
        ]) != (
            int(block_compose_header["affine_prefix_device_bytes"])
            + int(block_compose_header[
                "affine_block_summary_device_bytes"
            ])
            - int(production_header["affine_prefix_device_bytes"])
        )
    ):
        raise KatError(
            "block-compose allocation accounting is not exact"
        )
    if (
        int(production_terminal["delta_mertens"])
        != int(production["affine_mq_delta_mertens"])
        or int(seed7_terminal["delta_mertens"])
        != int(seed7["affine_mq_delta_mertens"])
        or int(seed11_terminal["delta_mertens"])
        != int(seed11["affine_mq_delta_mertens"])
        or int(seed11_rect_terminal["delta_mertens"])
        != int(seed11_rect["affine_mq_delta_mertens"])
        or int(production_terminal["delta_squarefree"])
        != int(production["affine_mq_delta_squarefree"])
        or int(seed7_terminal["delta_squarefree"])
        != int(seed7["affine_mq_delta_squarefree"])
        or int(seed11_terminal["delta_squarefree"])
        != int(seed11["affine_mq_delta_squarefree"])
        or int(seed11_rect_terminal["delta_squarefree"])
        != int(seed11_rect["affine_mq_delta_squarefree"])
        or persistent_terminal_affine(production_terminal)
        != affine_from_one_shot(production)
        or persistent_terminal_affine(seed7_terminal)
        != affine_from_one_shot(seed7)
        or persistent_terminal_affine(seed11_terminal)
        != affine_from_one_shot(seed11)
        or persistent_terminal_affine(seed11_rect_terminal)
        != affine_from_one_shot(seed11_rect)
    ):
        raise KatError(
            "persistent multi-slot guards differ from CPU-qualified one-shot"
        )


def files_identical(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as left_stream, right.open("rb") as right_stream:
        while True:
            left_chunk = left_stream.read(1 << 20)
            right_chunk = right_stream.read(1 << 20)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def check_residue_235_rect_power_nonpower_width(
    one_shot: Path,
    roster: Path,
    temporary: Path,
) -> None:
    """Exercise a live ninth p=7 slot rounded to sixteen grid columns."""
    events_per_block = 256 * 4_096
    required_slots = 9
    selected_slots = 16
    count = 8 * 7 * events_per_block + 1
    lower = 10_000_000_000_000_000 - count + 1
    lower -= lower % 7
    if (
        lower <= 0
        or lower % 7 != 0
        or lower + count - 1 > 10_000_000_000_000_000
        or 1 + ((count - 1) // 7) // events_per_block
            != required_slots
        or 1 + (count - 1) // 7 != 8 * events_per_block + 1
    ):
        raise KatError(
            "rect2dPower live ninth-slot KAT parameters are invalid"
        )

    flat_mu = temporary / "seed235-power-width-flat.mu"
    rectangular_mu = temporary / "seed235-power-width-rect.mu"
    flat = run_json(
        one_shot_command(
            one_shot, roster, flat_mu,
            lower=lower, count=count,
            incoming_mertens=0, incoming_squarefree=0,
            affine=False,
        )
    )
    rectangular = run_json(
        one_shot_command(
            one_shot, roster, rectangular_mu,
            lower=lower, count=count,
            incoming_mertens=0, incoming_squarefree=0,
            affine=False,
            rectangular_mode="rect2dPower",
        )
    )
    if not files_identical(flat_mu, rectangular_mu):
        raise KatError(
            "live ninth-slot rect2dPower mu bytes differ from the flat path"
        )

    semantic_fields = (
        "gpu_record_sha256_le_v1",
        "gpu_mu_hurst_block_sha256_v1",
        "delta_mertens",
        "segment_squarefree_count",
        "mobius_histogram",
        "mismatch_count",
        "fused_support_poison_count",
    )
    if any(
        flat[field] != rectangular[field]
        for field in semantic_fields
    ):
        raise KatError(
            "live ninth-slot rect2dPower report differs from flat semantics"
    )
    for name, report in (("flat", flat), ("rect2dPower", rectangular)):
        if (
            report[
                "all_gpu_mu_values_compared_with_independent_cpu_segmented_sieve"
            ] is not True
            or int(report["mismatch_count"]) != 0
            or int(report["fused_support_poison_count"]) != 0
            or int(report["qualification_mu_bytes_written"]) != count
        ):
            raise KatError(
                f"live ninth-slot {name} run did not pass its CPU oracle"
            )

    grid = rectangular["qualification_rectangular_grid"]
    if (
        rectangular["algorithm"]
            != SEED235_RECT_POWER_ONE_SHOT_ALGORITHM
        or rectangular["qualification_receipt_domain"]
            != SEED235_RECT_POWER_ONE_SHOT_DOMAIN
        or rectangular["qualification_residue_rectangular"] is not True
        or rectangular["qualification_rectangular_seed"] != "235"
        or rectangular["qualification_rectangular_mode"] != "rect2dPower"
        or int(rectangular[
            "qualification_rectangular_required_slots_per_prime"
        ]) != required_slots
        or int(rectangular[
            "qualification_rectangular_slots_per_prime"
        ]) != selected_slots
        or int(rectangular[
            "qualification_rectangular_events_per_block"
        ]) != events_per_block
        or int(rectangular[
            "qualification_rectangular_multiblock_prime_count"
        ]) <= 0
        or int(grid["x"]) != selected_slots
        or int(grid["y"]) != int(rectangular[
            "qualification_rectangular_multiblock_prime_count"
        ])
        or int(grid["y"]) <= 0
        or int(grid["z"]) != 1
        or int(rectangular[
            "qualification_rectangular_threads_per_block"
        ]) != 256
        or int(rectangular[
            "qualification_rectangular_enclosing_super_shard_lower"
        ]) != lower
        or int(rectangular[
            "qualification_rectangular_enclosing_super_shard_count"
        ]) != count
        or int(rectangular["fused_multiblock_slots_per_prime"])
            != selected_slots
        or rectangular["receipt_chain_sha256"]
            == flat["receipt_chain_sha256"]
    ):
        raise KatError(
            "live required-9/selected-16 rect2dPower geometry or "
            "identity changed"
        )
    check_one_shot_rectangular_receipt_binding(rectangular)


def check_residue_235_prefix_attack(
    one_shot: Path,
    roster: Path,
    temporary: Path,
) -> None:
    command = one_shot_command(
        one_shot, roster, temporary / "bad-prefix.mu",
        lower=10_000_000_000_000_000 - 8_192 + 1,
        count=8_192, incoming_mertens=0,
        incoming_squarefree=0, affine=True,
    )
    command.extend(
        ["--qualification-omit-device-prime", "2"]
    )
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if (
        result.returncode == 0
        or b"prime roster to begin exactly [2,3,5]"
        not in result.stderr
    ):
        raise KatError(
            "residue-235 selected-roster prefix attack did not fail closed"
        )


def check_residue_2357_prefix_attack(
    one_shot: Path,
    roster: Path,
    temporary: Path,
) -> None:
    command = one_shot_command(
        one_shot, roster, temporary / "bad-seed7-prefix.mu",
        lower=10_000_000_000_000_000 - 8_192 + 1,
        count=8_192, incoming_mertens=0,
        incoming_squarefree=0, affine=True,
        residue_2357_seed=True,
    )
    command.extend(
        ["--qualification-omit-device-prime", "7"]
    )
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if (
        result.returncode == 0
        or b"prime roster to begin exactly [2,3,5,7]"
        not in result.stderr
    ):
        raise KatError(
            "residue-2357 selected-roster prefix attack did not fail closed"
        )


def check_residue_235711_prefix_attack(
    one_shot: Path,
    roster: Path,
    temporary: Path,
) -> None:
    command = one_shot_command(
        one_shot, roster, temporary / "bad-seed11-prefix.mu",
        lower=10_000_000_000_000_000 - 8_192 + 1,
        count=8_192, incoming_mertens=0,
        incoming_squarefree=0, affine=True,
        residue_235711_seed=True,
    )
    command.extend(
        ["--qualification-omit-device-prime", "11"]
    )
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if (
        result.returncode == 0
        or b"prime roster to begin exactly [2,3,5,7,11]"
        not in result.stderr
    ):
        raise KatError(
            "residue-235711 selected-roster prefix attack did not fail closed"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--one-shot", required=True, type=Path)
    parser.add_argument("--persistent", required=True, type=Path)
    parser.add_argument("--prime-roster", type=Path)
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(
        prefix="tg-mobius-persistent-kat-"
    ) as temporary_text:
        temporary = Path(temporary_text)
        roster = arguments.prime_roster
        if roster is None:
            roster = temporary / "primes-through-1e8.u32le"
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "tools" / "tg_mobius_prime_roster.py"),
                    str(roster),
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            if result.returncode != 0:
                raise KatError(
                    "could not generate qualification prime roster: "
                    + result.stderr.decode(errors="replace")
                )

        check_adjacent_split(
            arguments.one_shot, roster, temporary,
            name="n33", lower=25, count=17, left_count=8, affine=False,
        )
        check_adjacent_split(
            arguments.one_shot, roster, temporary,
            name="n438429", lower=438_420, count=20,
            left_count=9, affine=False,
        )
        square = 99_999_937**2
        check_adjacent_split(
            arguments.one_shot, roster, temporary,
            name="perfect-square", lower=square - 2_048, count=4_097,
            left_count=2_048, affine=True,
        )
        check_adjacent_split(
            arguments.one_shot, roster, temporary,
            name="near-source-endpoint",
            lower=10_000_000_000_000_000 - 8_192 + 1,
            count=8_192, left_count=4_095, affine=True,
        )
        check_balanced_vs_legacy(
            arguments.one_shot, roster, temporary,
        )
        check_residue_2357_235711_multislot_persistent(
            arguments.one_shot, arguments.persistent,
            roster, temporary,
        )
        check_residue_235_rect_power_nonpower_width(
            arguments.one_shot, roster, temporary,
        )
        check_residue_235_prefix_attack(
            arguments.one_shot, roster, temporary,
        )
        check_residue_2357_prefix_attack(
            arguments.one_shot, roster, temporary,
        )
        check_residue_235711_prefix_attack(
            arguments.one_shot, roster, temporary,
        )
        check_affine_summary_crossover(
            arguments.persistent, roster,
        )
        check_persistent(
            arguments.one_shot, arguments.persistent,
            roster, temporary,
        )
    print(
        "persistent Möbius whole/split, fresh/reused, and every-boundary "
        "restart KAT passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
