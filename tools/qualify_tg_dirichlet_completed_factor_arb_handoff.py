#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run the bounded real-Arb completed-factor resident CUDA qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_completed_factor_arb_handoff import (  # noqa: E402
    DirichletCompletedFactorArbHandoffError,
    run_bounded_arb_handoff_qualification,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--first-t-index", type=int, default=0)
    parser.add_argument("--sample-count", type=int, default=8)
    parser.add_argument("--precision", type=int, default=384)
    parser.add_argument("--checkpoint-span", type=int, default=4)
    arguments = parser.parse_args()
    try:
        answer = run_bounded_arb_handoff_qualification(
            directory=arguments.directory,
            runner=arguments.runner,
            device=arguments.device,
            first_t_index=arguments.first_t_index,
            sample_count=arguments.sample_count,
            precision=arguments.precision,
            checkpoint_span=arguments.checkpoint_span,
        )
    except (
        DirichletCompletedFactorArbHandoffError,
        OSError,
    ) as error:
        parser.error(str(error))
    print(json.dumps(answer, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
