#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded before/after timing for the PT21 v2 artifact construction.

This measures one repeated synthetic block-zero fixture on one host.  It is a
component timing, not a source-scale rate, and it must not be extrapolated
into a campaign ETA: the packet is resident and repeated, and no source
transform or source-sized input/output is measured.

Every measured fast-path result is byte-compared against the Python reference
before it is timed, so a reported speedup always refers to identical bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_fused_artifact import (  # noqa: E402
    build_block_artifact,
)
from tg_verifier.platt_pt21_native_artifact_fastpath import (  # noqa: E402
    NativeArtifactSession,
    build_block_artifact_native,
)
from tg_verifier.platt_pt21_native_record_adapter import (  # noqa: E402
    adapt_block,
    adapt_block_native_artifact_fastpath,
    adapt_block_native_artifact_session,
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )


def _median(samples: list[float]) -> float:
    return statistics.median(samples)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--required-sign-packet", type=Path, required=True)
    parser.add_argument("--source-trace", type=Path, required=True)
    parser.add_argument("--stationary-trace", type=Path, required=True)
    parser.add_argument("--turing-inputs", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--native-builder", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=9)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    if arguments.runs < 3:
        raise SystemExit("at least three runs are required for a median")

    builder = arguments.native_builder.resolve()
    builder_sha256 = hashlib.sha256(builder.read_bytes()).hexdigest()

    reference_artifact = _canonical(
        build_block_artifact(
            arguments.required_sign_packet, arguments.source_trace
        )
    )
    reference_record = adapt_block(
        required_sign_packet=arguments.required_sign_packet,
        stationary_trace=arguments.stationary_trace,
        turing_inputs=arguments.turing_inputs,
        worker=arguments.worker,
    )

    python_builder: list[float] = []
    native_builder_one_shot: list[float] = []
    python_adapter: list[float] = []
    native_adapter_one_shot: list[float] = []
    native_adapter_session: list[float] = []

    for _index in range(arguments.runs):
        started = time.perf_counter()
        value = build_block_artifact(
            arguments.required_sign_packet, arguments.source_trace
        )
        raw = _canonical(value)
        python_builder.append(time.perf_counter() - started)
        if raw != reference_artifact:
            raise SystemExit("reference builder is not deterministic")

        started = time.perf_counter()
        produced = build_block_artifact_native(
            required_sign_packet=arguments.required_sign_packet,
            source_trace=arguments.source_trace,
            builder=builder,
            expected_builder_sha256=builder_sha256,
        )
        native_builder_one_shot.append(time.perf_counter() - started)
        if produced.raw != reference_artifact:
            raise SystemExit("native builder bytes differ from the reference")

        started = time.perf_counter()
        adapted = adapt_block(
            required_sign_packet=arguments.required_sign_packet,
            stationary_trace=arguments.stationary_trace,
            turing_inputs=arguments.turing_inputs,
            worker=arguments.worker,
        )
        python_adapter.append(time.perf_counter() - started)
        if adapted.record != reference_record.record:
            raise SystemExit("reference adapter is not deterministic")

        started = time.perf_counter()
        fast = adapt_block_native_artifact_fastpath(
            required_sign_packet=arguments.required_sign_packet,
            stationary_trace=arguments.stationary_trace,
            turing_inputs=arguments.turing_inputs,
            worker=arguments.worker,
            native_builder=builder,
            expected_native_builder_sha256=builder_sha256,
        )
        native_adapter_one_shot.append(time.perf_counter() - started)
        if fast.record != reference_record.record:
            raise SystemExit("native one-shot record differs from reference")

    with NativeArtifactSession(
        builder=builder, expected_builder_sha256=builder_sha256
    ) as session:
        for _index in range(arguments.runs):
            started = time.perf_counter()
            streamed = adapt_block_native_artifact_session(
                required_sign_packet=arguments.required_sign_packet,
                stationary_trace=arguments.stationary_trace,
                turing_inputs=arguments.turing_inputs,
                worker=arguments.worker,
                session=session,
            )
            native_adapter_session.append(time.perf_counter() - started)
            if streamed.record != reference_record.record:
                raise SystemExit(
                    "native session record differs from the reference"
                )

    report = {
        "schema": "sparkinterval.tg.platt-pt21-native-artifact-benchmark.v1",
        "runs": arguments.runs,
        "block": reference_record.block,
        "block_artifact_bytes": len(reference_artifact),
        "block_artifact_sha256": hashlib.sha256(
            reference_artifact
        ).hexdigest(),
        "block_record_sha256": reference_record.record_sha256,
        "native_builder_sha256": builder_sha256,
        "python_builder_median_seconds": _median(python_builder),
        "native_builder_one_shot_median_seconds": _median(
            native_builder_one_shot
        ),
        "python_adapter_median_seconds": _median(python_adapter),
        "native_adapter_one_shot_median_seconds": _median(
            native_adapter_one_shot
        ),
        "native_adapter_session_median_seconds": _median(
            native_adapter_session
        ),
        "adapter_session_speedup": (
            _median(python_adapter) / _median(native_adapter_session)
        ),
        "all_fast_path_bytes_identical_to_reference": True,
        "bounded_repeated_fixture": True,
        "source_scale_rate_measured": False,
        "campaign_eta_supported": False,
        "external_atom_discharged": False,
        "source_claim_ready": False,
    }
    print(
        json.dumps(
            report, sort_keys=True, indent=2 if arguments.pretty else None
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
