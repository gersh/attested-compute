#!/usr/bin/env python3
"""Produce a conservative machine-readable audit of an NVIDIA SASS dump."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


INSTRUCTION = re.compile(
    r"/\*[0-9a-fA-F]+\*/\s+(?:@[!A-Za-z0-9_.]+\s+)?([A-Z][A-Z0-9_.]*)\b"
)
FUNCTION = re.compile(r"^\s*Function\s*:\s*(\S+)", re.MULTILINE)
GLOBAL_FUNCTION = re.compile(r"^\s*\.global\s+(\S+)\s*$", re.MULTILINE)
TARGET = re.compile(r"^\s*\.target\s+(sm_[0-9a-z]+)\s*$", re.MULTILINE)


def base_mnemonic(mnemonic: str) -> str:
    return mnemonic.split(".", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--allow-division-lowering",
        action="store_true",
        help="allow the RCP64H/DFMA sequence used to implement precise f64 div",
    )
    args = parser.parse_args()

    raw = args.input.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    mnemonics = INSTRUCTION.findall(text)
    bases = [base_mnemonic(item) for item in mnemonics]

    tensor = sorted({m for m, b in zip(mnemonics, bases) if b in {
        "HMMA", "IMMA", "BMMA", "MMA", "WGMMA"
    }})
    atomics = sorted({m for m, b in zip(mnemonics, bases) if b in {"ATOM", "RED"}})
    synchronization = sorted({m for m, b in zip(mnemonics, bases) if b in {
        "BAR", "MEMBAR", "ERRBAR", "DEPBAR"
    }})
    approximate = sorted({m for m, b in zip(mnemonics, bases) if b == "MUFU"})
    fused = sorted({m for m, b in zip(mnemonics, bases) if b in {
        "DFMA", "FFMA", "HFMA", "HFMA2"
    }})

    permitted_lowering = []
    rejected_approximate = approximate
    rejected_fused = fused
    if args.allow_division_lowering:
        permitted_lowering = sorted(
            {m for m in approximate if m == "MUFU.RCP64H"}
            | {m for m in fused if base_mnemonic(m) in {"DFMA", "HFMA2"}}
        )
        rejected_approximate = [m for m in approximate if m != "MUFU.RCP64H"]
        rejected_fused = [
            m for m in fused if base_mnemonic(m) not in {"DFMA", "HFMA2"}
        ]

    findings = {
        "tensor_instructions": tensor,
        "atomic_instructions": atomics,
        "synchronization_instructions": synchronization,
        "unexpected_approximate_instructions": rejected_approximate,
        "unexpected_fused_instructions": rejected_fused,
    }
    passed = bool(mnemonics) and not any(findings.values())
    report = {
        "schema_version": 1,
        "audit_kind": "sass_static_inspection",
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "targets": sorted(set(TARGET.findall(text))),
        "functions": sorted(set(FUNCTION.findall(text) + GLOBAL_FUNCTION.findall(text))),
        "instruction_count": len(mnemonics),
        "mnemonics": sorted(set(mnemonics)),
        "permitted_compiler_division_lowering": permitted_lowering,
        "findings": findings,
        "passed": passed,
        "limitations": [
            "This is a lexical audit, not a proof of PTX-to-SASS equivalence.",
            "RCP64H, DFMA, and the constant-forming HFMA2 are accepted only as reviewed precise-div lowering when enabled.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    if not mnemonics:
        print("no SASS instructions found", file=sys.stderr)
    if not passed:
        print(f"SASS inspection failed; see {args.output}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
