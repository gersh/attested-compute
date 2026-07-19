#!/usr/bin/env python3
"""Validate the deliberately tiny directed-rounding probe PTX program."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ALLOWED = {
    "ld.param.f64",
    "ld.param.u64",
    "mov.u32",
    "mov.f64",
    "or.b32",
    "setp.ne.s32",
    "bra",
    "cvta.to.global.u64",
    "add.rm.f64",
    "add.rp.f64",
    "sub.rm.f64",
    "sub.rp.f64",
    "mul.rm.f64",
    "mul.rp.f64",
    "div.rm.f64",
    "div.rp.f64",
    "st.global.f64",
    "ret",
}
REQUIRED_ROUNDING = {
    "add.rm.f64",
    "add.rp.f64",
    "sub.rm.f64",
    "sub.rp.f64",
    "mul.rm.f64",
    "mul.rp.f64",
    "div.rm.f64",
    "div.rp.f64",
}
TARGET = re.compile(r"^\s*\.target\s+(sm_[0-9a-z]+)\s*$", re.MULTILINE)
ENTRY = re.compile(r"(?:^|\s)\.entry\s+([^\s(]+)", re.MULTILINE)
INSTRUCTION = re.compile(r"^(?:@!?%[A-Za-z0-9_]+\s+)?([a-z][a-z0-9_.]*)\b")


def instructions(text: str) -> tuple[list[str], list[str]]:
    result: list[str] = []
    unparsed: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line or line.startswith(".") or line.startswith("{") or line.startswith("}"):
            continue
        if line.endswith(":") or line.endswith("(") or line == ")":
            continue
        match = INSTRUCTION.match(line)
        if match is not None:
            result.append(match.group(1))
        else:
            unparsed.append(line)
    return result, unparsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    raw = args.input.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    parsed, unparsed = instructions(text)
    target_values = sorted(set(TARGET.findall(text)))
    entries = ENTRY.findall(text)
    unexpected = sorted(set(parsed) - ALLOWED)
    counts = {name: parsed.count(name) for name in sorted(REQUIRED_ROUNDING)}
    incorrect_counts = {name: count for name, count in counts.items() if count != 1}
    passed = (
        bool(parsed)
        and target_values == [args.target]
        and len(entries) == 1
        and not unparsed
        and not unexpected
        and not incorrect_counts
    )
    report = {
        "schema_version": 1,
        "audit_kind": "directed_rounding_probe_ptx_allowlist",
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "expected_target": args.target,
        "targets": target_values,
        "entries": entries,
        "instruction_count": len(parsed),
        "instruction_counts": {name: parsed.count(name) for name in sorted(set(parsed))},
        "required_rounding_instruction_counts": counts,
        "unexpected_instructions": unexpected,
        "unparsed_code_lines": unparsed,
        "incorrect_required_counts": incorrect_counts,
        "passed": passed,
        "limitations": [
            "This lexical validator is specific to the diagnostic probe, not a formal PTX semantics.",
            "It does not prove that ptxas preserves PTX behavior in SASS.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if not passed:
        print(f"PTX probe inspection failed; see {args.output}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
