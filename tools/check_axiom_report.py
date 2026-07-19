#!/usr/bin/env python3
"""Fail unless every printed Lean axiom dependency is explicitly allowed."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


DEPENDENCIES = re.compile(r"depends on axioms:\s*\[([^\]]*)\]", re.DOTALL)
NO_DEPENDENCIES = re.compile(r"does not depend on any axioms")


def parse_reports(text: str) -> list[set[str]]:
    reports = [
        {name.strip() for name in match.group(1).split(",") if name.strip()}
        for match in DEPENDENCIES.finditer(text)
    ]
    reports.extend(set() for _ in NO_DEPENDENCIES.finditer(text))
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--allow", action="append", default=[])
    args = parser.parse_args()

    text = args.report.read_text(encoding="utf-8")
    reports = parse_reports(text)
    if len(reports) != args.expected_count:
        print(
            "axiom report count mismatch: "
            f"expected {args.expected_count}, found {len(reports)}",
            file=sys.stderr,
        )
        return 1

    allowed = set(args.allow)
    unexpected = sorted(set().union(*reports) - allowed) if reports else []
    if unexpected:
        print(
            "unapproved theorem dependencies: " + ", ".join(unexpected),
            file=sys.stderr,
        )
        return 1

    print(
        f"Axiom report passed: {len(reports)} declarations, "
        f"allowed dependencies only ({', '.join(sorted(allowed)) or 'none'})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
