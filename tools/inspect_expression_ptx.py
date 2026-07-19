#!/usr/bin/env python3
"""Strict lexical audit for the Phase 4 interval-expression CUDA PTX.

This is intentionally narrower than a general PTX validator.  It binds the
current readable CUDA prototype to its reviewed directed-rounding sites and
rejects any other floating arithmetic, fused/approximate operation, or GPU
coordination primitive.  It is still a lexical audit, not a proof that ptxas
or SASS preserves PTX semantics.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


TARGET = re.compile(r"^\s*\.target\s+(sm_[0-9a-z]+)\s*$", re.MULTILINE)
ENTRY = re.compile(r"(?:^|\s)\.entry\s+([^\s(]+)", re.MULTILINE)
INSTRUCTION = re.compile(r"^(?:@!?%[A-Za-z0-9_]+\s+)?([a-z][a-z0-9_.]*)\b")
LOCAL_BYTES = re.compile(r"\.local\s+\.align\s+\d+\s+\.b8\s+\S+\[(\d+)\]")

EXPECTED_DIRECTED_COUNTS = {
    "add.rm.f64": 1,
    "add.rp.f64": 1,
    "sub.rm.f64": 1,
    "sub.rp.f64": 1,
    # One four-corner site in pow_nat and one in the ordinary mul opcode.
    "mul.rm.f64": 8,
    "mul.rp.f64": 8,
    "div.rm.f64": 4,
    "div.rp.f64": 4,
}
PERMITTED_F64_INSTRUCTIONS = set(EXPECTED_DIRECTED_COUNTS) | {"setp.eq.f64"}
FORBIDDEN_BASES = {
    "atom",
    "bar",
    "brkpt",
    "call",
    "cluster",
    "cp",
    "elect",
    "getctarank",
    "griddepcontrol",
    "ldmatrix",
    "mapa",
    "match",
    "mbarrier",
    "membar",
    "mma",
    "multimem",
    "red",
    "redux",
    "shfl",
    "stacksave",
    "stackrestore",
    "tcgen05",
    "vote",
    "wmma",
    "wgmma",
}
APPROXIMATE_OR_TRANSCENDENTAL_BASES = {
    "cos",
    "ex2",
    "lg2",
    "rcp",
    "rsqrt",
    "sin",
    "sqrt",
    "tanh",
}
FLOAT_TYPE_MARKERS = (".f64", ".f32", ".f16", ".f16x2", ".bf16", ".tf32")


def parsed_instructions(text: str) -> tuple[list[str], list[str]]:
    instructions: list[str] = []
    unparsed_code: list[str] = []
    in_body = False
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        if line == "{":
            in_body = True
            continue
        if line == "}":
            in_body = False
            continue
        if not in_body or line.startswith(".") or line.endswith(":"):
            continue
        if line.endswith("(") or line == ")":
            continue
        match = INSTRUCTION.match(line)
        if match is None:
            unparsed_code.append(line)
        else:
            instructions.append(match.group(1))
    return instructions, unparsed_code


def audit_ptx(raw: bytes, *, expected_target: str = "sm_121") -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return {
            "schema_version": 1,
            "audit_kind": "expression_ptx_strict_allowlist",
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "expected_target": expected_target,
            "passed": False,
            "decode_error": str(exc),
        }

    instructions, unparsed_code = parsed_instructions(text)
    counts = Counter(instructions)
    targets = sorted(set(TARGET.findall(text)))
    entries = ENTRY.findall(text)
    actual_directed_counts = {
        name: counts[name] for name in EXPECTED_DIRECTED_COUNTS
    }
    incorrect_directed_counts = {
        name: {"expected": expected, "actual": counts[name]}
        for name, expected in EXPECTED_DIRECTED_COUNTS.items()
        if counts[name] != expected
    }
    unexpected_floating = sorted(
        {
            instruction
            for instruction in instructions
            if any(marker in instruction for marker in FLOAT_TYPE_MARKERS)
            and instruction not in PERMITTED_F64_INSTRUCTIONS
        }
    )
    forbidden_coordination = sorted(
        {
            instruction
            for instruction in instructions
            if instruction.split(".", 1)[0] in FORBIDDEN_BASES
            or instruction.startswith("activemask")
            or ".shared" in instruction
        }
    )
    forbidden_math = sorted(
        {
            instruction
            for instruction in instructions
            if instruction.split(".", 1)[0]
            in APPROXIMATE_OR_TRANSCENDENTAL_BASES
            or instruction.split(".", 1)[0] in {"fma", "madc"}
            or instruction.startswith("mad.")
            and any(marker in instruction for marker in FLOAT_TYPE_MARKERS)
        }
    )
    shared_declarations = len(
        re.findall(r"(?m)^\s*(?:\.extern\s+)?\.shared\b", text)
    )
    local_stack_bytes = [int(value) for value in LOCAL_BYTES.findall(text)]
    entry_ok = len(entries) == 1 and "expression_batch_kernel" in entries[0]
    passed = (
        bool(instructions)
        and targets == [expected_target]
        and entry_ok
        and not unparsed_code
        and not incorrect_directed_counts
        and not unexpected_floating
        and not forbidden_coordination
        and not forbidden_math
        and shared_declarations == 0
        and local_stack_bytes == [512]
    )
    return {
        "schema_version": 1,
        "audit_kind": "expression_ptx_strict_allowlist",
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "expected_target": expected_target,
        "targets": targets,
        "entries": entries,
        "instruction_count": len(instructions),
        "required_directed_rounding_counts": actual_directed_counts,
        "incorrect_directed_rounding_counts": incorrect_directed_counts,
        "unexpected_floating_instructions": unexpected_floating,
        "forbidden_coordination_instructions": forbidden_coordination,
        "forbidden_math_instructions": forbidden_math,
        "shared_declaration_count": shared_declarations,
        "local_stack_bytes": local_stack_bytes,
        "unparsed_code_lines": unparsed_code,
        "passed": passed,
        "limitations": [
            "This is a lexical audit of compiler-emitted PTX, not a formal PTX semantics.",
            "It does not prove PTX-to-SASS equivalence or physical GPU execution.",
            "Exact instruction counts intentionally bind this audit to the reviewed Phase 4 prototype.",
        ],
    }


def extract_ptx(binary: Path, *, cuobjdump: str = "cuobjdump") -> bytes:
    completed = subprocess.run(
        [cuobjdump, "--dump-ptx", str(binary)],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"cuobjdump --dump-ptx failed with exit {completed.returncode}: {message}"
        )
    if not completed.stdout:
        raise RuntimeError("cuobjdump --dump-ptx produced no PTX")
    return completed.stdout


def audit_binary(
    binary: Path, *, expected_target: str = "sm_121", cuobjdump: str = "cuobjdump"
) -> dict[str, Any]:
    binary_raw = binary.read_bytes()
    ptx_raw = extract_ptx(binary, cuobjdump=cuobjdump)
    report = audit_ptx(ptx_raw, expected_target=expected_target)
    report["source_kind"] = "cuda_binary_extracted_with_cuobjdump"
    report["binary_sha256"] = hashlib.sha256(binary_raw).hexdigest()
    report["binary_path"] = str(binary.resolve())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target", default="sm_121")
    parser.add_argument(
        "--binary",
        action="store_true",
        help="extract PTX from a CUDA ELF/fatbin with cuobjdump",
    )
    parser.add_argument("--cuobjdump", default="cuobjdump")
    args = parser.parse_args(argv)

    try:
        report = (
            audit_binary(
                args.input, expected_target=args.target, cuobjdump=args.cuobjdump
            )
            if args.binary
            else audit_ptx(args.input.read_bytes(), expected_target=args.target)
        )
    except (OSError, RuntimeError) as exc:
        print(f"expression PTX audit failed: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    if not report["passed"]:
        print(f"expression PTX audit failed; see {args.output}", file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
