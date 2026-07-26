#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run the bounded Arb/FLINT oracle for the resident CUDA sign reducer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_completed_sign_gpu_reducer import (  # noqa: E402
    DirichletCompletedSignReducerError,
    run_arb_differential_qualification,
    validate_qualification_result,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--q", type=int, default=5)
    parser.add_argument("--first-t-index", type=int, default=0)
    parser.add_argument("--t-index-stop-exclusive", type=int, default=512)
    parser.add_argument("--precision", type=int, default=256)
    parser.add_argument("--factor-reseed-span", type=int, default=4096)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        record = run_arb_differential_qualification(
            arguments.runner,
            q=arguments.q,
            first_t_index=arguments.first_t_index,
            t_index_stop_exclusive=(
                arguments.t_index_stop_exclusive
            ),
            precision=arguments.precision,
            factor_reseed_span=arguments.factor_reseed_span,
        )
        validate_qualification_result(record)
        raw = (
            json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        )
        if arguments.output is not None:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = arguments.output.with_name(
                arguments.output.name + ".tmp"
            )
            temporary.write_text(raw, encoding="ascii")
            temporary.replace(arguments.output)
        sys.stdout.write(raw)
        return 0
    except (DirichletCompletedSignReducerError, OSError) as error:
        print(
            f"qualify_tg_dirichlet_completed_sign_gpu_reducer: {error}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
