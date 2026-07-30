#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
"""Derive the registry pin for a leancompcert CompCert artifact.

The point of this tool is that `RegisteredAlgorithm.canonicalDefinition` for a
leancompcert campaign must be *derived from the artifact*, never typed by hand.
It reads

  * the emitted C produced by `lake exe lean-compcert emit-<name>-c`, and
  * the executable produced by `ccomp` from exactly those bytes,

and prints the canonical definition text, its SHA-256 (which becomes
`algorithmHash`), and the Lean literals to paste into the registry.

Why this replaces a prose paragraph
-----------------------------------
`RegisteredAlgorithm.canonicalDefinition .ch25A7BoundaryV1` is a paragraph
naming `tg_verifier/a7_flint.py`.  Its digest -- `algorithmHash` -- is
therefore the digest of a *description*.  Editing `a7_flint.py` does not
change it, so `algorithmHashDiagnosticCheck` cannot notice.  The definition
this tool emits names the artifact by digest instead, so editing the artifact
does change it, and the Lean-side check fails closed.

The registry already contains one algorithm that does this correctly:
`.h100FormalPtxConstantOneV1` sets `canonicalDefinition` to the generated PTX
text itself.  This tool generalises that pattern to CompCert artifacts, with
the difference that the artifact is named by digest rather than inlined --
see `--inline-c` and the size discussion in
`docs/COMPCERT_ARTIFACT_UNDER_TDX.md`.

Usage
-----
    python3 tools/tg_leancompcert_artifact_pin.py \
        --name mertens-odd-floor-sum \
        --program MertensCert.oddFloorSum \
        --emitter 'lake exe lean-compcert emit-mertens-cert-c' \
        --emitted-c build/mertens.c \
        --binary build/mertens \
        --compcert-version 3.17 \
        --target x86_64-linux \
        --link static

    # verify a previously pinned definition still matches the artifact
    python3 tools/tg_leancompcert_artifact_pin.py ... --expect-hash <64 hex>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DOMAIN = "sparkinterval.registered-algorithm.v1"
PRODUCER = "leancompcert"
SEMANTICS = "Program.evalCC_compile"
SUCCESS = "exit-status-zero"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_definition(fields: dict[str, str]) -> str:
    """The exact bytes whose SHA-256 becomes `algorithmHash`.

    Line format and field order are fixed: `name=value\\n`, one per line, no
    trailing newline after the last field, matching every other entry in
    `RegisteredAlgorithm.canonicalDefinition`.
    """
    order = [
        "name",
        "producer",
        "program",
        "emitter",
        "emitted-c-sha256",
        "emitted-c-bytes",
        "compcert-version",
        "compcert-target",
        "binary-sha256",
        "binary-bytes",
        "link",
        "semantics",
        "success",
        "output",
    ]
    missing = [key for key in order if key not in fields]
    if missing:
        raise SystemExit(f"internal error: missing canonical fields {missing}")
    body = "".join(f"{key}={fields[key]}\n" for key in order)
    return DOMAIN + "\n" + body.rstrip("\n")


def lean_string_literal(text: str, width: int = 60) -> str:
    """Render `text` as a Lean `++`-chained string literal."""
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )
    pieces: list[str] = []
    index = 0
    while index < len(escaped):
        stop = min(index + width, len(escaped))
        # never cut inside an escape sequence
        back = stop
        while back > index and escaped[back - 1] == "\\":
            back -= 1
        if (stop - back) % 2 == 1:
            stop += 1
        pieces.append(escaped[index:stop])
        index = stop
    return " ++\n      ".join('"%s"' % piece for piece in pieces)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--program", required=True,
                        help="fully qualified Lean name of the CCIR Program")
    parser.add_argument("--emitter", required=True,
                        help="exact command line that produced the C")
    parser.add_argument("--emitted-c", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--compcert-version", required=True)
    parser.add_argument("--target", required=True,
                        help="CompCert target triple, e.g. x86_64-linux")
    parser.add_argument("--link", default="static", choices=["static", "dynamic"])
    parser.add_argument("--output-language", default="false-or-true",
                        help="canonical result language of the campaign")
    parser.add_argument("--expect-hash", default=None,
                        help="fail unless algorithmHash equals this")
    parser.add_argument("--json", action="store_true",
                        help="emit a machine-readable summary instead of Lean")
    args = parser.parse_args()

    for path in (args.emitted_c, args.binary):
        if not path.is_file():
            raise SystemExit(f"not a regular file: {path}")

    c_bytes = args.emitted_c.stat().st_size
    binary_bytes = args.binary.stat().st_size
    c_digest = sha256_file(args.emitted_c)
    binary_digest = sha256_file(args.binary)

    # A leancompcert artifact must not depend on the Lean runtime.  The
    # emitter currently writes `#include <lean/lean.h>` even when the artifact
    # makes no `lean_*` call; that include is what forces the Lean headers
    # onto the build host.  Refuse silently accepting a real dependency.
    text = args.emitted_c.read_text(errors="replace")
    if "lean_" in text.replace("#include <lean/lean.h>", ""):
        raise SystemExit(
            "REFUSED: the emitted C calls the Lean runtime (`lean_*`); it is "
            "not a standalone artifact and must not be pinned as one")

    fields = {
        "name": args.name,
        "producer": PRODUCER,
        "program": args.program,
        "emitter": args.emitter,
        "emitted-c-sha256": c_digest,
        "emitted-c-bytes": str(c_bytes),
        "compcert-version": args.compcert_version,
        "compcert-target": args.target,
        "binary-sha256": binary_digest,
        "binary-bytes": str(binary_bytes),
        "link": args.link,
        "semantics": SEMANTICS,
        "success": SUCCESS,
        "output": args.output_language,
    }
    definition = canonical_definition(fields)
    algorithm_hash = hashlib.sha256(definition.encode("utf-8")).hexdigest()

    if args.expect_hash is not None and args.expect_hash != algorithm_hash:
        print(
            f"DRIFT: expected algorithmHash {args.expect_hash}\n"
            f"       derived  algorithmHash {algorithm_hash}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(
            {
                "kind": "sparkinterval.leancompcert-artifact-pin.v1",
                "algorithm_hash": algorithm_hash,
                "canonical_definition": definition,
                "canonical_definition_bytes": len(definition.encode("utf-8")),
                "fields": fields,
            },
            sort_keys=True,
            indent=2,
        ))
        return 0

    print("-- canonicalDefinition (%d bytes), algorithmHash = %s"
          % (len(definition.encode("utf-8")), algorithm_hash))
    print("--")
    for line in definition.split("\n"):
        print("--   " + line)
    print()
    print("  | .%s =>" % args.name.replace("-", ""))
    print("      %s" % lean_string_literal(definition + "\n").rstrip())
    print()
    print('  -- algorithmHash:')
    print('  | .%s =>' % args.name.replace("-", ""))
    print('      "%s"' % algorithm_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
