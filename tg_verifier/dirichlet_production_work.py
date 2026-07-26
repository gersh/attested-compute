# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact work inventory for the optimized Platt Theorem 7.1 pipeline.

The counts here are scheduling facts, not evidence for GRH.  They make the
scale of every production stage reviewable without running an analytic
backend and give benchmark reports one canonical denominator.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from tg_verifier.dirichlet_allchars_stage import source_work as allchars_source_work
from tg_verifier.dirichlet_campaign import (
    FULL_SOURCE_CHARACTER_COUNT,
    _smallest_prime_factors,
    primitive_character_count,
    source_height,
)
from tg_verifier.dirichlet_lattice_stage import (
    LATTICE_ROWS,
    SOURCE_MAX_T_INDEX,
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    TAYLOR_COLUMNS,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
SMALL_Q_START = 2
SMALL_Q_STOP = 10_000
MAXIMUM_Q = 400_000
SOURCE_SAMPLE_NUMERATOR = 5
SOURCE_SAMPLE_DENOMINATOR = 64
UPSAMPLE_FACTORS = (1, 8, 32, 128, 512)

# Independently recomputed below.  Pinning them makes an accidental schedule
# change fail loudly in tests and production-planning tools.
PINNED = {
    "small_q_primitive_characters": 18_477_108,
    "large_q_primitive_characters": 29_547_446_729,
    "all_primitive_characters": 29_565_923_837,
    "small_q_modulus_ordinate_rows": 11_248_140_846,
    "large_q_modulus_ordinate_rows": 3_637_613_167,
    "small_q_primitive_character_samples": 4_729_082_453_090,
    "large_q_primitive_character_samples": 191_701_043_433_012,
    "all_primitive_character_samples": 196_430_125_886_102,
    "large_q_residue_interpolations": 266_697_737_764_848,
    "large_q_lattice_ordinates": 127_988,
    "large_q_lattice_cells": 4_193_910_784,
    "factor_8_primitive_character_samples": 1_571_337_544_104_271,
    "factor_32_primitive_character_samples": 6_285_305_857_203_567,
    "factor_128_primitive_character_samples": 25_141_179_075_390_483,
    "factor_512_primitive_character_samples": 100_564_672_017_861_490,
    "large_q_batch_64_radix2_butterflies": 15_334_965_882_246_056,
}


def _grid_samples(q: int, factor: int) -> int:
    height = source_height(q)
    last = (
        height.numerator * SOURCE_SAMPLE_DENOMINATOR * factor
        // (height.denominator * SOURCE_SAMPLE_NUMERATOR)
    )
    return last + 1


@lru_cache(maxsize=1)
def exact_work_inventory() -> dict[str, Any]:
    """Recompute every pinned scheduling count from the source formulas."""

    spf = _smallest_prime_factors(MAXIMUM_Q)
    character_counts = {"small": 0, "large": 0}
    modulus_rows = {"small": 0, "large": 0}
    samples = {
        factor: {"small": 0, "large": 0} for factor in UPSAMPLE_FACTORS
    }
    for q in range(SMALL_Q_START, MAXIMUM_Q + 1):
        region = "small" if q <= SMALL_Q_STOP else "large"
        characters = primitive_character_count(q, spf)
        character_counts[region] += characters
        # The large-q v2 transport omits precisely the empty primitive
        # character rosters.  The small-q inventory remains the historical
        # algorithm accounting.
        if region == "small" or characters != 0:
            modulus_rows[region] += _grid_samples(q, 1)
        for factor in UPSAMPLE_FACTORS:
            samples[factor][region] += characters * _grid_samples(q, factor)

    allchars = allchars_source_work(batch_size=64)
    recomputed = {
        "small_q_primitive_characters": character_counts["small"],
        "large_q_primitive_characters": character_counts["large"],
        "all_primitive_characters": sum(character_counts.values()),
        "small_q_modulus_ordinate_rows": modulus_rows["small"],
        "large_q_modulus_ordinate_rows": modulus_rows["large"],
        "small_q_primitive_character_samples": samples[1]["small"],
        "large_q_primitive_character_samples": samples[1]["large"],
        "all_primitive_character_samples": sum(samples[1].values()),
        "large_q_residue_interpolations": allchars["input_group_values"],
        "large_q_lattice_ordinates": SOURCE_MAX_T_INDEX + 1,
        "large_q_lattice_cells": (
            (SOURCE_MAX_T_INDEX + 1) * LATTICE_ROWS * TAYLOR_COLUMNS
        ),
        "factor_8_primitive_character_samples": sum(samples[8].values()),
        "factor_32_primitive_character_samples": sum(samples[32].values()),
        "factor_128_primitive_character_samples": sum(samples[128].values()),
        "factor_512_primitive_character_samples": sum(samples[512].values()),
        "large_q_batch_64_radix2_butterflies": allchars[
            "batched_radix2_butterflies"
        ],
    }
    if recomputed != PINNED:
        differing = {
            key: {"expected": PINNED.get(key), "actual": recomputed.get(key)}
            for key in sorted(set(PINNED) | set(recomputed))
            if PINNED.get(key) != recomputed.get(key)
        }
        raise RuntimeError(f"Dirichlet production work invariant changed: {differing}")
    if recomputed["all_primitive_characters"] != FULL_SOURCE_CHARACTER_COUNT:
        raise RuntimeError("production inventory differs from the source campaign")
    if allchars["modulus_ordinate_transforms"] != modulus_rows["large"]:
        raise RuntimeError("all-character and source-grid row counts differ")
    return {
        "kind": "sparkinterval.tg.dirichlet_production_work.v1",
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "source": SOURCE_URL,
        "classification": "exact_work_inventory_not_execution_or_grh_evidence",
        "cutover": {
            "small_q": [SMALL_Q_START, SMALL_Q_STOP],
            "large_q": [SOURCE_Q_START, SOURCE_Q_STOP],
            "note": "Platt reports using the small-q path through about q=10000.",
        },
        "source_grid": {
            "positive_ordinate_step": {
                "numerator": SOURCE_SAMPLE_NUMERATOR,
                "denominator": SOURCE_SAMPLE_DENOMINATOR,
            },
            "reported_routine_upsample_factor": 8,
            "reported_exception_factors": [32, 128, 512],
            "conjugate_symmetry_note": (
                "All primitive characters are present; positive ordinates for "
                "chi and conjugate chi cover the symmetric source assertion."
            ),
        },
        "counts": recomputed,
        "all_character_transform": allchars,
        "storage_warning": {
            "binary64_complex_rectangle_bytes": 32,
            "large_q_transformed_rectangles_if_materialized_bytes": (
                recomputed["large_q_residue_interpolations"] * 32
            ),
            "required_policy": (
                "Stream bounded batches into completion, zero isolation, and "
                "Merkle aggregation; never materialize the full transform."
            ),
        },
        "external_atom_discharged": False,
    }


__all__ = ["PINNED", "exact_work_inventory"]
