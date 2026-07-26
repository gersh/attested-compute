#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed qualification for the native Lean FFT-root table wrapper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile


ROOT = struct.Struct("<dddd")


class QualificationError(RuntimeError):
    """The native Lean FFT-root wrapper did not fail closed."""


def _run(checker: Path, path: Path, length: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(checker), str(path), str(length), "192", "128"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _reject(
    checker: Path, path: Path, length: int, label: str
) -> None:
    completed = _run(checker, path, length)
    if completed.returncode == 0:
        raise QualificationError(f"accepted hostile {label}")


def run(checker: Path) -> dict[str, object]:
    checker = checker.resolve()
    if not checker.is_file():
        raise QualificationError(f"checker is not a file: {checker}")

    # L=4: stage/exponent rows are (2,0), (4,0), and (4,1).
    valid = (
        ROOT.pack(1.0, 1.0, 0.0, 0.0)
        + ROOT.pack(1.0, 1.0, 0.0, 0.0)
        + ROOT.pack(0.0, 0.0, 1.0, 1.0)
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        paths = {
            "valid": root / "valid.bin",
            "truncated": root / "truncated.bin",
            "trailing": root / "trailing.bin",
            "nonfinite": root / "nonfinite.bin",
            "reversed": root / "reversed.bin",
            "wrong_finite": root / "wrong-finite.bin",
        }
        paths["valid"].write_bytes(valid)
        paths["truncated"].write_bytes(valid[:-1])
        paths["trailing"].write_bytes(valid + b"\0")
        paths["nonfinite"].write_bytes(
            ROOT.pack(float("inf"), float("inf"), 0.0, 0.0)
            + valid[ROOT.size:]
        )
        paths["reversed"].write_bytes(
            ROOT.pack(1.0, 0.0, 0.0, 0.0) + valid[ROOT.size:]
        )
        paths["wrong_finite"].write_bytes(
            ROOT.pack(0.0, 0.0, 1.0, 1.0) + valid[ROOT.size:]
        )

        accepted = _run(checker, paths["valid"], 4)
        if accepted.returncode != 0:
            raise QualificationError(
                f"valid fixture rejected: {accepted.stderr.strip()}"
            )
        try:
            report = json.loads(accepted.stdout)
        except json.JSONDecodeError as error:
            raise QualificationError(
                "accepted run emitted invalid JSON"
            ) from error
        expected = {
            "accepted": True,
            "assurance": "lean_source_checker_result_unattested",
            "checker": "sparkinterval.dirichlet_positive_fft_root_table.v1",
            "external_atom_discharged": False,
            "length": 4,
            "output_precision": 128,
            "root_count": 3,
            "trusted_execution_attested": False,
            "work_precision": 192,
        }
        if report != expected:
            raise QualificationError("accepted report schema or labels changed")

        for label in (
            "truncated",
            "trailing",
            "nonfinite",
            "reversed",
            "wrong_finite",
        ):
            _reject(checker, paths[label], 4, label)
        _reject(checker, paths["valid"], 12, "unsupported geometry")

    return {
        "kind": "sparkinterval.dirichlet.lean_fft_root_cli_qualification.v1",
        "status": "pass",
        "accepted_fixture_rows": 3,
        "hostile_cases_rejected": 6,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checker", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.checker)
    except (OSError, QualificationError) as error:
        print(f"certified FFT-root CLI qualification failed: {error}")
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
