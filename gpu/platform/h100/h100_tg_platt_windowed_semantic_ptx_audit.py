#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed PTX arithmetic audit for the Platt semantic transform stage."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re


OPCODE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_.]*\.f64)(?![A-Za-z0-9_])")
DIRECTED = {f"{op}.{rounding}.f64" for op in ("add", "sub", "mul") for rounding in ("rm", "rp")}
BENIGN_EXACT = {"mov.f64", "neg.f64", "selp.f64", "min.f64", "max.f64"}
FORBIDDEN_BASES = {"div", "fma", "rcp", "sqrt", "sin", "cos", "ex2", "lg2", "rem"}


def audit_text(text: str) -> dict[str, object]:
    counts = Counter(OPCODE.findall(text))
    unexpected: dict[str, int] = {}
    forbidden: dict[str, int] = {}
    for opcode, count in sorted(counts.items()):
        base = opcode.split(".", 1)[0]
        if base in FORBIDDEN_BASES:
            forbidden[opcode] = count
        if (
            opcode not in DIRECTED
            and opcode not in BENIGN_EXACT
            and not opcode.startswith("ld.")
            and not opcode.startswith("st.")
        ):
            unexpected[opcode] = count
    asymmetric = {
        op: {"rm": counts[f"{op}.rm.f64"], "rp": counts[f"{op}.rp.f64"]}
        for op in ("add", "sub", "mul")
        if counts[f"{op}.rm.f64"] != counts[f"{op}.rp.f64"]
        or counts[f"{op}.rm.f64"] == 0
    }
    passed = not forbidden and not unexpected and not asymmetric
    return {
        "schema": "sparkinterval.tg.platt-windowed-semantic-ptx-audit.v1",
        "passed": passed,
        "directed_counts": {
            opcode: counts[opcode] for opcode in sorted(DIRECTED)
        },
        "min_count": counts["min.f64"],
        "max_count": counts["max.f64"],
        "forbidden_f64_opcodes": forbidden,
        "unexpected_f64_opcodes": unexpected,
        "asymmetric_or_missing_directed_pairs": asymmetric,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ptx", type=Path, required=True)
    args = parser.parse_args()
    report = audit_text(args.ptx.read_text(encoding="utf-8"))
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
