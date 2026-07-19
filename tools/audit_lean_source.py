#!/usr/bin/env python3
"""Reject proof escapes, allowing only the disclosed execution axioms."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ALLOWED_AXIOMS = {
    Path("SparkInterval/Execution/Trusted/DGXOperatorSignature.lean"): {
        "dgx_operator_signed_run_sound"
    },
    Path("SparkInterval/Execution/Trusted/H100Attestation.lean"): {
        "h100_attested_run_sound"
    }
}
FORBIDDEN = re.compile(r"\b(sorry|admit|unsafe)\b")
AXIOM = re.compile(r"\baxiom\s+([A-Za-z_][A-Za-z0-9_']*)")


def strip_comments_and_strings(source: str) -> str:
    """Blank Lean comments/strings while retaining newlines for diagnostics."""
    output: list[str] = []
    index = 0
    block_depth = 0
    in_line_comment = False
    in_string = False
    escaped = False
    while index < len(source):
        pair = source[index : index + 2]
        char = source[index]
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                output.append(char)
            else:
                output.append(" ")
            index += 1
            continue
        if block_depth:
            if pair == "/-":
                block_depth += 1
                output.extend("  ")
                index += 2
            elif pair == "-/":
                block_depth -= 1
                output.extend("  ")
                index += 2
            else:
                output.append("\n" if char == "\n" else " ")
                index += 1
            continue
        if in_string:
            output.append("\n" if char == "\n" else " ")
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if pair == "--":
            in_line_comment = True
            output.extend("  ")
            index += 2
        elif pair == "/-":
            block_depth = 1
            output.extend("  ")
            index += 2
        elif char == '"':
            in_string = True
            output.append(" ")
            index += 1
        else:
            output.append(char)
            index += 1
    return "".join(output)


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    source_paths: list[Path] = []
    for source_root_name in ("SparkInterval", "generator"):
        source_root = project_root / source_root_name
        if source_root.is_dir():
            source_paths.extend(source_root.rglob("*.lean"))
    for source_path in sorted(source_paths):
        relative = source_path.relative_to(project_root)
        stripped = strip_comments_and_strings(source_path.read_text(encoding="utf-8"))
        for match in FORBIDDEN.finditer(stripped):
            failures.append(
                f"{relative}:{line_number(stripped, match.start())}: "
                f"forbidden Lean token '{match.group(1)}'"
            )
        for match in AXIOM.finditer(stripped):
            name = match.group(1)
            if name not in ALLOWED_AXIOMS.get(relative, set()):
                failures.append(
                    f"{relative}:{line_number(stripped, match.start())}: "
                    f"unapproved axiom '{name}'"
                )

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Lean source audit passed (only the two named execution trust axioms are permitted).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
