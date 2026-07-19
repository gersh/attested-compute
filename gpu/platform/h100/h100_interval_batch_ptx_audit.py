#!/usr/bin/env python3
"""Conservative lexical audit for the H100 interval-batch PTX artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


REQUIRED_DIRECTED = (
    "add.rm.f64",
    "add.rp.f64",
    "sub.rm.f64",
    "sub.rp.f64",
    "mul.rm.f64",
    "mul.rp.f64",
    "div.rm.f64",
    "div.rp.f64",
)
TARGET = re.compile(r"^\s*\.target\s+(sm_[0-9a-z]+)\s*$", re.MULTILINE)
ENTRY = re.compile(r"(?:^|\s)\.entry\s+([^\s(]+)", re.MULTILINE)
INSTRUCTION = re.compile(
    r"^(?:@!?%[A-Za-z0-9_]+\s+)?([a-z][a-z0-9_.]*)\b"
)


def parse_instructions(text: str) -> list[str]:
    parsed: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line or line.startswith((".", "{", "}")) or line.endswith(":"):
            continue
        match = INSTRUCTION.match(line)
        if match is not None:
            parsed.append(match.group(1))
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target", default="sm_90")
    args = parser.parse_args()

    raw = args.input.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    instructions = parse_instructions(text)
    entries = ENTRY.findall(text)
    targets = sorted(set(TARGET.findall(text)))
    directed_counts = {
        name: instructions.count(name) for name in REQUIRED_DIRECTED
    }
    incorrect_directed_counts = {
        name: count for name, count in directed_counts.items() if count != 1
    }

    # Any alternate floating implementation of these arithmetic operations is
    # suspicious.  Integer/pointer add, multiply, and fused integer addressing
    # remain outside this check.
    arithmetic_f64 = sorted(
        {
            instruction
            for instruction in instructions
            if instruction.endswith(".f64")
            and instruction.split(".", 1)[0]
            in {"add", "sub", "mul", "div", "mad", "fma"}
        }
    )
    unexpected_f64_arithmetic = sorted(
        set(arithmetic_f64) - set(REQUIRED_DIRECTED)
    )
    interval_entries = [name for name in entries if "interval_batch_kernel" in name]
    passed = (
        targets == [args.target]
        and len(entries) == 1
        and len(interval_entries) == 1
        and not incorrect_directed_counts
        and not unexpected_f64_arithmetic
    )
    report = {
        "schema_version": 1,
        "audit_kind": "h100_interval_batch_directed_ptx",
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "expected_target": args.target,
        "targets": targets,
        "entries": entries,
        "interval_batch_entries": interval_entries,
        "instruction_count": len(instructions),
        "required_directed_instruction_counts": directed_counts,
        "incorrect_directed_instruction_counts": incorrect_directed_counts,
        "floating_arithmetic_instructions": arithmetic_f64,
        "unexpected_f64_arithmetic": unexpected_f64_arithmetic,
        "passed": passed,
        "limitations": [
            "This is a lexical PTX audit, not a formal PTX semantics.",
            "It does not prove that ptxas preserves PTX behavior in SASS.",
            "It does not establish execution on an H100 or hardware attestation.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not passed:
        print(f"H100 interval-batch PTX audit failed; see {args.output}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
