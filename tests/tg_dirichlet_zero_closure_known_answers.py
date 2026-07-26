#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run the q=3,4,5 Arb producer/checker closure known answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_zero_closure import (  # noqa: E402
    load_canonical_json,
    make_known_answer_request,
    write_canonical_json,
)


def _run(argv: list[str]) -> None:
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{' '.join(argv)} failed: {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--producer",
        type=Path,
        default=ROOT / "tools" / "tg_dirichlet_zero_closure_producer.py",
    )
    parser.add_argument(
        "--checker",
        type=Path,
        default=ROOT / "tools" / "tg_dirichlet_zero_closure_checker.py",
    )
    args = parser.parse_args()
    probe = subprocess.run(
        [args.python, "-c", "import flint; assert flint.__version__ == '0.9.0'; assert flint.__FLINT_VERSION__ == '3.6.0'"],
        check=False,
    )
    if probe.returncode != 0:
        print("SKIP: requires pinned python-flint 0.9.0 / FLINT 3.6.0")
        return 77

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request_path = root / "request.json"
        result_path = root / "result.json"
        receipt_path = root / "receipt.json"
        write_canonical_json(request_path, make_known_answer_request())
        _run(
            [
                args.python,
                str(args.producer),
                "produce",
                "--request",
                str(request_path),
                "--output",
                str(result_path),
            ]
        )
        _run(
            [
                args.python,
                str(args.checker),
                "verify",
                "--request",
                str(request_path),
                "--result",
                str(result_path),
                "--receipt",
                str(receipt_path),
            ]
        )
        result = load_canonical_json(result_path)
        actual = {
            (row["q"], row["conrey_number"]): row[
                "multiplicity_counted_nontrivial_zeros"
            ]
            for row in result["characters"]
        }
        expected = {(3, 2): 2, (4, 3): 2, (5, 2): 4, (5, 3): 4, (5, 4): 4}
        if actual != expected:
            raise RuntimeError(f"zero-count known answers differ: {actual}")
        receipt = load_canonical_json(receipt_path)
        if receipt.get("accepted") is not True or receipt.get(
            "paper_turing_method_executed"
        ) is not False:
            raise RuntimeError("checker receipt boundary differs")
        print(
            json.dumps(
                {
                    "accepted": True,
                    "counts": [
                        {"q": q, "conrey_number": conrey, "count": count}
                        for (q, conrey), count in sorted(actual.items())
                    ],
                    "paper_turing_method_executed": False,
                    "external_atom_discharged": False,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
