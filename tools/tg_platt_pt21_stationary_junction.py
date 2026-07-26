#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect or independently replay one finite ``PT21STJ1`` record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from tg_verifier.platt_pt21_stationary_junction import (
    Candidate,
    PT21StationaryJunctionError,
    parse_record,
    replay,
)


CANDIDATE_FIELDS = {
    "certified_multiplicity_slots",
    "left_sample",
    "middle_sample",
    "multiplicity_slots_if_resolved",
    "nleft_units_per_slot",
    "nright_units_per_slot",
    "requires_adaptive_resolution",
    "right_sample",
    "source_positive",
    "stream",
    "strict_stat_pt",
}


def _load_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise PT21StationaryJunctionError(
            f"evidence is not a regular file: {path}"
        )
    def exact_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PT21StationaryJunctionError(
                    f"duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_bytes(), object_pairs_hook=exact_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21StationaryJunctionError(
            f"evidence is not strict JSON: {error}"
        ) from error


def _candidates(value: object) -> list[Candidate]:
    if not isinstance(value, list):
        raise PT21StationaryJunctionError(
            "candidate evidence is not a list"
        )
    result: list[Candidate] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != CANDIDATE_FIELDS:
            raise PT21StationaryJunctionError(
                f"candidate[{index}] fields differ"
            )
        if any(isinstance(item[key], bool) or not isinstance(item[key], int)
               for key in CANDIDATE_FIELDS):
            raise PT21StationaryJunctionError(
                f"candidate[{index}] has a noninteger field"
            )
        result.append(Candidate(**item))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    parser.add_argument("--event-record", type=Path)
    parser.add_argument("--required-samples", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--refinements", type=Path)
    parser.add_argument("--stationary-trace", type=Path)
    parser.add_argument("--resolver-sha256")
    parser.add_argument("--flint-sha256")
    arguments = parser.parse_args()
    raw = arguments.record.read_bytes()
    optional = (
        arguments.event_record,
        arguments.required_samples,
        arguments.candidates,
        arguments.refinements,
        arguments.stationary_trace,
        arguments.resolver_sha256,
        arguments.flint_sha256,
    )
    if not any(value is not None for value in optional):
        result = parse_record(raw)
    elif not all(value is not None for value in optional):
        parser.error(
            "full replay requires event record, samples, candidates, "
            "refinements, stationary trace, and both identity SHA-256 pins"
        )
    else:
        candidates = _candidates(_load_json(arguments.candidates))
        refinements = _load_json(arguments.refinements)
        trace = _load_json(arguments.stationary_trace)
        if not isinstance(refinements, list):
            raise PT21StationaryJunctionError(
                "refinement evidence is not a list"
            )
        if not isinstance(trace, dict):
            raise PT21StationaryJunctionError(
                "stationary trace is not an object"
            )
        result = replay(
            raw,
            event_record=arguments.event_record.read_bytes(),
            sample_payload=arguments.required_samples.read_bytes(),
            candidates=candidates,
            refinements=refinements,
            stationary_trace=trace,
            expected_resolver_sha256=arguments.resolver_sha256,
            expected_flint_sha256=arguments.flint_sha256,
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PT21StationaryJunctionError as error:
        print(f"tg_platt_pt21_stationary_junction: {error}", file=sys.stderr)
        raise SystemExit(1)
