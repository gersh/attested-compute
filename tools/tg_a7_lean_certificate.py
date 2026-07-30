#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the retained CH25 A.7 transcript as a literal Lean certificate.

The emitted module defines `certificate : Certificate` and closes
`certificate.check = true` with ordinary `decide` -- no `native_decide`.  It is
the reproduction recipe for the "in-Lean kernel re-checking" cost figure in
`docs/algorithms/CH25_A7_LEAN_MODEL.md`.

The generated file is intentionally *not* committed: it is about 5 MB of data
and its `decide` costs minutes and tens of gigabytes.  Whether to carry that in
the default build is an owner decision, not a default.

Usage::

    python3 tools/tg_a7_lean_certificate.py \\
      --input /path/to/a7_boundary.json \\
      --output /review/A7BoundaryProduction.lean
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.a7_lean_certificate import (  # noqa: E402
    certificate_from_transcript_file,
    render_lean_source,
)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", dir=path.parent, delete=False, mode="w",
        encoding="utf-8",
    ) as stream:
        temporary = Path(stream.name)
        stream.write(text)
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
        help="optional Lean output path (omitting it is audit-only)",
    )
    parser.add_argument(
        "--namespace",
        default="SparkInterval.Generated.A7BoundaryProduction",
        help="Lean namespace for the generated module",
    )
    arguments = parser.parse_args(argv)

    certificate = certificate_from_transcript_file(arguments.input)
    source = render_lean_source(certificate, namespace=arguments.namespace)
    if arguments.output is not None:
        _write_atomic(arguments.output, source)
    print(
        '{"accepted":true,'
        f'"leaf_count":{len(certificate.leaves)},'
        f'"lean_source_bytes":{len(source.encode("utf-8"))},'
        f'"max_depth":{certificate.max_depth},'
        f'"transcript_sha256":"{certificate.transcript_sha256}",'
        f'"transcript_size_bytes":{certificate.transcript_size_bytes},'
        '"analytic_claim_proved":false}'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
