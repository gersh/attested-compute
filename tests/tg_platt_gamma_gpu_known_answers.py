#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Cross-check the H100 Gamma synthesis probes against fresh FLINT values."""

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
    parser.add_argument("--gpu-runner", required=True)
    parser.add_argument("--gamma-runner", required=True)
    args = parser.parse_args()

    gpu = one_json([
        args.gpu_runner,
        "--terms=256",
        "--stages=2",
        "--blocks=1",
        "--repetitions=1",
        "--reanchor-blocks=1",
        "--fft-passes=0",
        "--source-geometry",
        "--gamma-synthesis",
    ])
    arb = one_json([
        args.gamma_runner,
        "--height", "10000000504",
        "--precision", "256",
        "--degree", "6",
        "--repeat", "1",
        "--audit-samples", "17",
    ])
    assert gpu["gamma_taylor_synthesis"] is True
    assert gpu["gamma_packet_scope"] == (
        "first_source_window_kat_reused_for_work_shape"
    )
    assert gpu["gamma_output_fnv1a64"] == "541307d064454b08"
    gpu_probes = gpu["gamma_probes"]
    arb_probes = arb["source_value_probes"]
    assert len(gpu_probes) == len(arb_probes) == 5
    for gpu_probe, arb_probe in zip(gpu_probes, arb_probes, strict=True):
        assert gpu_probe["index"] == arb_probe["index"]
        for component in ("re", "im"):
            gpu_lower = float.fromhex(gpu_probe[f"{component}_lo_hex"])
            gpu_upper = float.fromhex(gpu_probe[f"{component}_hi_hex"])
            arb_lower = float.fromhex(arb_probe[component]["lo_hex"])
            arb_upper = float.fromhex(arb_probe[component]["hi_hex"])
            assert gpu_lower <= arb_lower <= arb_upper <= gpu_upper
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
