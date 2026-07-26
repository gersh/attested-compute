#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build, inspect, or size completed-factor recurrence artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_completed_factor_artifacts import (  # noqa: E402
    DirichletCompletedFactorArtifactError,
    parse_checkpoint_artifact,
    parse_gamma_artifact,
    parse_step_artifact,
    source_storage_projection,
    write_bounded_arb_artifacts,
    write_synthetic_unit_artifacts,
)


def _report(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("source-projection")
    synthetic = subparsers.add_parser("synthetic")
    synthetic.add_argument("directory", type=Path)
    synthetic.add_argument("--q", type=int, default=7)
    synthetic.add_argument("--first-t-index", type=int, default=0)
    synthetic.add_argument("--sample-count", type=int, default=8)
    synthetic.add_argument("--checkpoint-span", type=int, default=4096)
    arb_bounded = subparsers.add_parser("arb-bounded")
    arb_bounded.add_argument("directory", type=Path)
    arb_bounded.add_argument("--q", type=int, default=7)
    arb_bounded.add_argument("--first-t-index", type=int, default=0)
    arb_bounded.add_argument("--sample-count", type=int, default=8)
    arb_bounded.add_argument("--precision", type=int, default=384)
    arb_bounded.add_argument("--checkpoint-span", type=int, default=4096)
    verify = subparsers.add_parser("verify")
    verify.add_argument("gamma", type=Path)
    verify.add_argument("steps", type=Path)
    verify.add_argument("checkpoints", type=Path)
    verify.add_argument("--gamma-sha256")
    verify.add_argument("--step-sha256")
    verify.add_argument("--checkpoint-sha256")
    arguments = parser.parse_args()
    try:
        if arguments.command == "source-projection":
            answer = source_storage_projection()
        elif arguments.command == "synthetic":
            answer = write_synthetic_unit_artifacts(
                arguments.directory,
                q=arguments.q,
                first_t_index=arguments.first_t_index,
                sample_count=arguments.sample_count,
                checkpoint_span=arguments.checkpoint_span,
            )
        elif arguments.command == "arb-bounded":
            answer = write_bounded_arb_artifacts(
                arguments.directory,
                q=arguments.q,
                first_t_index=arguments.first_t_index,
                sample_count=arguments.sample_count,
                precision=arguments.precision,
                checkpoint_span=arguments.checkpoint_span,
            )
        else:
            gamma = parse_gamma_artifact(
                arguments.gamma,
                expected_sha256=arguments.gamma_sha256,
            )
            steps = parse_step_artifact(
                arguments.steps,
                expected_sha256=arguments.step_sha256,
            )
            checkpoints = parse_checkpoint_artifact(
                arguments.checkpoints,
                expected_sha256=arguments.checkpoint_sha256,
            )
            if (
                checkpoints.gamma_artifact_sha256
                != gamma.artifact_sha256
                or checkpoints.step_artifact_sha256
                != steps.artifact_sha256
            ):
                raise DirichletCompletedFactorArtifactError(
                    "checkpoint bundle does not bind supplied gamma/steps"
                )
            answer = {
                "algorithm": (
                    "tg-dirichlet-completed-factor-artifact-verify-v1"
                ),
                "gamma_sha256": gamma.artifact_sha256,
                "step_sha256": steps.artifact_sha256,
                "checkpoint_sha256": checkpoints.artifact_sha256,
                "sample_count": gamma.sample_count,
                "q_count": len(checkpoints.records),
                "source_range_qualified": False,
                "external_atom_discharged": False,
            }
    except (DirichletCompletedFactorArtifactError, OSError) as error:
        parser.error(str(error))
    _report(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
