#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize or audit the compact finite CH25 A.7 Lean wire."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.a7_boundary_wire import (  # noqa: E402
    decode_a7_boundary_wire,
    wire_from_transcript_bytes,
)
from tg_verifier.analytic import read_analytic_artifact_bytes  # noqa: E402


def _write_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
    try:
        temporary.chmod(0o644)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="authoritative retained a7_boundary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional TGA7WIR1 output path (omitting it is audit-only)",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="allow a non-retained tiny test transcript",
    )
    arguments = parser.parse_args(argv)
    require_retained = not arguments.allow_synthetic
    source = read_analytic_artifact_bytes(
        arguments.input, label="A7 boundary artifact"
    )
    wire = wire_from_transcript_bytes(
        source, require_retained_identity=require_retained
    )
    checked = decode_a7_boundary_wire(
        wire, require_retained_identity=require_retained
    )
    if arguments.output is not None:
        _write_atomic(arguments.output, wire)
    print(
        json.dumps(
            {
                "accepted": True,
                "classification": (
                    "finite-transcript-wire-only-no-analytic-realization"
                ),
                "input": str(arguments.input),
                "output": (
                    None if arguments.output is None else str(arguments.output)
                ),
                "wire_bytes": len(wire),
                "wire_sha256": checked.wire_sha256,
                "payload_sha256": checked.payload_sha256,
                "transcript_sha256": checked.transcript_sha256,
                "leaves_sha256": checked.leaves_sha256,
                "leaf_count": len(checked.leaves),
                "max_depth": checked.max_depth,
                "maximum_norm_mantissa_bits": max(
                    leaf.norm_sq_upper_mantissa.bit_length()
                    for leaf in checked.leaves
                ),
                "maximum_zeta_mantissa_bits": max(
                    leaf.zeta_abs_lower_mantissa.bit_length()
                    for leaf in checked.leaves
                ),
                "norm_exponent_range": [
                    min(
                        leaf.norm_sq_upper_exponent
                        for leaf in checked.leaves
                    ),
                    max(
                        leaf.norm_sq_upper_exponent
                        for leaf in checked.leaves
                    ),
                ],
                "zeta_exponent_range": [
                    min(
                        leaf.zeta_abs_lower_exponent
                        for leaf in checked.leaves
                    ),
                    max(
                        leaf.zeta_abs_lower_exponent
                        for leaf in checked.leaves
                    ),
                ],
                "finite_transcript_check_complete": True,
                "flint_to_mathlib_realization_verified": False,
                "analytic_claim_proved": False,
                "production_execution_verified": False,
                "attestation_verified": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
