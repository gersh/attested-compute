#!/usr/bin/env python3
"""Reject proof escapes, allowing only the disclosed run-certificate axiom."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ALLOWED_AXIOMS = {
    Path("SparkInterval/Execution/Trusted/RunCertificate.lean"): {
        "accepted_run_certificate_sound"
    },
    # The Phala/dstack Intel TDX execution boundary.  This is a SECOND named
    # trust declaration, deliberately separate from the Azure one above so
    # that `#print axioms` distinguishes the two roots of trust.  It is not
    # reachable from any capstone; `tests/test_phala_tdx_axiom_off_cone.py`
    # asserts that, and must be edited consciously if that ever changes.
    Path("SparkInterval/Execution/PhalaTdxCampaignCertificate.lean"): {
        "phalaTdxAttestedRun_sound"
    },
}
FORBIDDEN = re.compile(r"\b(sorry|admit|unsafe)\b")
NATIVE_DECIDE = re.compile(r"\bnative_decide\b")
# `constant foo : P` and `axiom foo : P` elaborate to the same kernel
# declaration kind.  Treating only the latter spelling as a trust declaration
# would let an unreviewed project axiom evade this fast source-level check.
TRUST_DECLARATION = re.compile(
    r"\b(axiom|constant)\s+([A-Za-z_][A-Za-z0-9_']*)"
)


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
        if "Tests" not in relative.parts:
            for match in NATIVE_DECIDE.finditer(stripped):
                failures.append(
                    f"{relative}:{line_number(stripped, match.start())}: "
                    "production theorem code must use kernel-checkable "
                    "`decide` or an explicit certificate, not `native_decide`"
                )
        for match in TRUST_DECLARATION.finditer(stripped):
            kind = match.group(1)
            name = match.group(2)
            if kind != "axiom" or name not in ALLOWED_AXIOMS.get(relative, set()):
                failures.append(
                    f"{relative}:{line_number(stripped, match.start())}: "
                    f"unapproved {kind} trust declaration '{name}'"
                )

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        "Lean source audit passed (only the one named run-certificate "
        "trust declaration is permitted; `constant` aliases and production "
        "`native_decide` are rejected)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
