#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known-answer and fail-honesty checks for the Platt transform runner."""

from __future__ import annotations

import argparse
import json
import subprocess


def one_json(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    rows = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(rows) != 1:
        raise AssertionError(f"expected one JSON row, received {len(rows)}")
    return json.loads(rows[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True)
    parser.add_argument("--source-shape", action="store_true")
    args = parser.parse_args()

    report = one_json(
        [args.runner, "--source-shape", "--repetitions=2"]
        if args.source_shape
        else [args.runner]
    )
    assert report["schema"] == "sparkinterval.tg.platt-windowed-semantic.v1"
    assert report["claim_scope"] == (
        "source_semantic_transform_from_certified_input_boxes_not_a_zeta_certificate"
    )
    assert report["upstream_commit"] == (
        "42b21426718e542daa2b006dc05ea2d7f26426e6"
    )
    assert report["actual_zeta_inputs"] is False
    assert report["all_output_intervals_finite"] is True
    assert report["small_kat_contained"] is True
    if args.source_shape:
        assert report["source_shape"] is True
        assert report["source_error_disks"] is True
        assert report["convolution_length"] == 32_768
        assert report["taylor_terms"] == 23
        assert report["negative_G_transforms"] == 23
        assert report["positive_convolution_transforms"] == 46
        assert report["negative_inverse_transforms"] == 23
        assert report["positive_hermidft_transforms"] == 1
        assert report["butterflies_per_run"] == 23_134_208
        assert report["pointwise_products_per_run"] == 753_664
    else:
        assert report["source_shape"] is False
        assert report["source_error_disks"] is False
        assert report["convolution_length"] == 8
        assert report["taylor_terms"] == 3
        assert report["butterflies_per_run"] == 176
        assert report["pointwise_products_per_run"] == 24
        assert report["output_fnv1a64"] == "39fb9001ce31cf28"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
