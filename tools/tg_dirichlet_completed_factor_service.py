#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan, run, resume, and verify completed-factor source artifact jobs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_completed_factor_service import (  # noqa: E402
    DirichletCompletedFactorServiceError,
    generate_gamma_job,
    generate_phase_job,
    generate_step_job,
    initialize_source_service,
    service_status,
)


def _require_execution_acknowledgement(arguments: argparse.Namespace) -> None:
    if not arguments.execute_full_source_artifact_job:
        raise DirichletCompletedFactorServiceError(
            "full-source artifact generation is potentially expensive; "
            "pass --execute-full-source-artifact-job"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser(
        "init",
        help="construct the exact twelve-job plan without running Arb",
    )
    initialize.add_argument("directory", type=Path)
    initialize.add_argument(
        "--schedule-manifest", type=Path, required=True
    )
    initialize.add_argument("--precision", type=int, default=384)
    initialize.add_argument("--checkpoint-span", type=int, default=4096)

    status = commands.add_parser(
        "status", help="verify visible jobs and report resumable progress"
    )
    status.add_argument("directory", type=Path)
    status.add_argument("--require-complete", action="store_true")

    gamma = commands.add_parser(
        "run-gamma", help="generate the one shared full-range gamma catalog"
    )
    gamma.add_argument("directory", type=Path)
    gamma.add_argument(
        "--execute-full-source-artifact-job", action="store_true"
    )

    steps = commands.add_parser(
        "run-steps",
        help="generate the one shared execution-order conductor-step catalog",
    )
    steps.add_argument("directory", type=Path)
    steps.add_argument(
        "--execute-full-source-artifact-job", action="store_true"
    )

    phase = commands.add_parser(
        "run-phase",
        help="generate one independently resumable phase checkpoint catalog",
    )
    phase.add_argument("directory", type=Path)
    phase.add_argument("--phase-index", type=int, required=True)
    phase.add_argument(
        "--execute-full-source-artifact-job", action="store_true"
    )

    arguments = parser.parse_args()
    try:
        if arguments.command == "init":
            answer = initialize_source_service(
                arguments.directory,
                schedule_manifest=arguments.schedule_manifest,
                precision=arguments.precision,
                checkpoint_span=arguments.checkpoint_span,
            )
        elif arguments.command == "status":
            answer = service_status(
                arguments.directory,
                require_complete=arguments.require_complete,
            )
        elif arguments.command == "run-gamma":
            _require_execution_acknowledgement(arguments)
            answer = generate_gamma_job(arguments.directory)
        elif arguments.command == "run-steps":
            _require_execution_acknowledgement(arguments)
            answer = generate_step_job(arguments.directory)
        else:
            _require_execution_acknowledgement(arguments)
            answer = generate_phase_job(
                arguments.directory,
                phase_index=arguments.phase_index,
            )
    except (RuntimeError, OSError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            answer,
            sort_keys=True,
            indent=2 if arguments.pretty else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
