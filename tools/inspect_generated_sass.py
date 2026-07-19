#!/usr/bin/env python3
"""Bind generated polynomial PTX directed sites to the assembled sm_121 SASS."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys


INSTRUCTION = re.compile(
    r"/\*[0-9a-fA-F]+\*/\s+(?:@[!A-Za-z0-9_.]+\s+)?([A-Z][A-Z0-9_.]*)\b"
)
TARGET = re.compile(r"^\s*\.target\s+(sm_[0-9a-z]+)\s*$", re.MULTILINE)
FUNCTION = re.compile(r"^\s*\.global\s+(sparkinterval_generated)\s*$", re.MULTILINE)
FORBIDDEN_BASES = {
    "ATOM",
    "BAR",
    "BMMA",
    "DEPBAR",
    "DFMA",
    "ERRBAR",
    "FFMA",
    "HFMA",
    "HMMA",
    "IMMA",
    "MEMBAR",
    "MMA",
    "MUFU",
    "RED",
    "WGMMA",
}
SAFE_HFMA2 = re.compile(
    r"/\*[0-9a-fA-F]+\*/\s+HFMA2\s+R[0-9]+,\s+-RZ,\s+RZ,\s+0,\s+"
    r"(?:0|1\.1920928955078125e-07)\s*;"
)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sass", type=Path)
    parser.add_argument("ptx_audit", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cubin", type=Path)
    args = parser.parse_args()

    sass_raw = args.sass.read_bytes()
    sass_text = sass_raw.decode("utf-8", errors="strict")
    ptx_audit_raw = args.ptx_audit.read_bytes()
    ptx_audit = json.loads(ptx_audit_raw)
    ptx_counts = ptx_audit.get("instruction_counts", {})
    raw_directed_from_ptx = {
        "DADD.RM": ptx_counts.get("add.rm.f64", 0)
        + ptx_counts.get("sub.rm.f64", 0),
        "DADD.RP": ptx_counts.get("add.rp.f64", 0)
        + ptx_counts.get("sub.rp.f64", 0),
        "DMUL.RM": ptx_counts.get("mul.rm.f64", 0),
        "DMUL.RP": ptx_counts.get("mul.rp.f64", 0),
    }
    raw_memory_from_ptx = {
        "LDG.E.64": ptx_counts.get("ld.global.b64", 0),
        "STG.E.64": ptx_counts.get("st.global.b64", 0),
        "STG.E.U8": ptx_counts.get("st.global.u8", 0),
    }
    raw_corner_selection_from_ptx = {
        "DSETP.MIN.AND": ptx_counts.get("min.f64", 0),
        "DSETP.MAX.AND": ptx_counts.get("max.f64", 0),
    }
    lowering_model = ptx_audit.get("lowering_model", {})
    expected_keys = {
        "DADD.RM",
        "DADD.RP",
        "DMUL.RM",
        "DMUL.RP",
        "DSETP.MIN.AND",
        "DSETP.MAX.AND",
        "FSEL",
        "SEL",
        "LDG.E.64",
        "LDG.E",
        "STG.E.64",
        "STG.E.U8",
    }
    raw_modeled_counts = lowering_model.get("expected_sass_counts", {})
    modeled_counts = raw_modeled_counts if isinstance(raw_modeled_counts, dict) else {}
    lowering_model_valid = (
        lowering_model.get("schema_version") == 1
        and lowering_model.get("analysis_kind")
        == "generated_ptx_demand_and_value_numbering_v1"
        and lowering_model.get("passed") is True
        and lowering_model.get("errors") == []
        and set(modeled_counts) == expected_keys
        and all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in modeled_counts.values()
        )
    )
    expected = {
        name: modeled_counts.get(name, -1)
        for name in ("DADD.RM", "DADD.RP", "DMUL.RM", "DMUL.RP")
    }
    expected_memory = {
        name: modeled_counts.get(name, -1)
        for name in ("LDG.E.64", "LDG.E", "STG.E.64", "STG.E.U8")
    }
    expected_corner_selection = {
        name: modeled_counts.get(name, -1)
        for name in ("DSETP.MIN.AND", "DSETP.MAX.AND")
    }
    mnemonics = INSTRUCTION.findall(sass_text)
    counts = Counter(mnemonics)
    actual = {name: counts[name] for name in expected}
    incorrect = {
        name: {"expected": count, "actual": actual[name]}
        for name, count in expected.items()
        if actual[name] != count
    }
    eliminated = {
        name: raw_directed_from_ptx[name] - actual[name]
        for name in ("DMUL.RM", "DMUL.RP")
    }
    actual_corner_selection = {
        name: counts[name] for name in expected_corner_selection
    }
    eliminated_corner_selection = {
        name: raw_corner_selection_from_ptx[name] - actual_corner_selection[name]
        for name in expected_corner_selection
    }
    incorrect_corner_selection: dict[str, object] = {
        name: {"expected": expected_count, "actual": actual_corner_selection[name]}
        for name, expected_count in expected_corner_selection.items()
        if actual_corner_selection[name] != expected_count
    }
    actual_selectors = {"FSEL": counts["FSEL"], "SEL": counts["SEL"]}
    expected_selectors = {
        "FSEL": modeled_counts.get("FSEL", -1),
        "SEL": modeled_counts.get("SEL", -1),
    }
    if any(
        actual_selectors[name] != expected_count
        for name, expected_count in expected_selectors.items()
    ):
        incorrect_corner_selection["corner selectors"] = {
            "expected": expected_selectors,
            "actual_sass": actual_selectors,
        }
    unexpected_corner_selection = sorted(
        {
            mnemonic
            for mnemonic in mnemonics
            if mnemonic.startswith(("DSETP.MIN", "DSETP.MAX", "FSEL", "SEL"))
            and mnemonic
            not in {"DSETP.MIN.AND", "DSETP.MAX.AND", "FSEL", "SEL"}
        }
    )
    forbidden = sorted(
        {
            mnemonic
            for mnemonic in mnemonics
            if mnemonic.split(".", 1)[0] in FORBIDDEN_BASES
        }
    )
    unexpected_double_arithmetic = sorted(
        {
            mnemonic
            for mnemonic in mnemonics
            if mnemonic.startswith(("DADD", "DMUL", "DFMA"))
            and mnemonic not in expected
        }
    )
    hfma2_count = counts["HFMA2"]
    safe_hfma2_count = len(SAFE_HFMA2.findall(sass_text))
    unsafe_hfma2_count = hfma2_count - safe_hfma2_count
    actual_memory = {name: counts[name] for name in expected_memory}
    incorrect_memory = {
        name: {"expected": expected_count, "actual": actual_memory[name]}
        for name, expected_count in expected_memory.items()
        if actual_memory[name] != expected_count
    }
    unexpected_global_memory = sorted(
        {
            mnemonic
            for mnemonic in mnemonics
            if mnemonic.startswith(("LDG", "STG"))
            and mnemonic not in expected_memory
        }
    )
    reconvergence = {
        "BSSY.RECONVERGENT": counts["BSSY.RECONVERGENT"],
        "BSYNC.RECONVERGENT": counts["BSYNC.RECONVERGENT"],
    }
    unexpected_reconvergence = sorted(
        {
            mnemonic
            for mnemonic in mnemonics
            if mnemonic.startswith(("BSSY", "BSYNC"))
            and mnemonic not in reconvergence
        }
    )
    reconvergence_balanced = (
        reconvergence["BSSY.RECONVERGENT"]
        == reconvergence["BSYNC.RECONVERGENT"]
    )
    targets = sorted(set(TARGET.findall(sass_text)))
    functions = sorted(set(FUNCTION.findall(sass_text)))
    passed = (
        ptx_audit.get("passed") is True
        and lowering_model_valid
        and bool(mnemonics)
        and targets == ["sm_121"]
        and functions == ["sparkinterval_generated"]
        and not incorrect
        and not forbidden
        and not unexpected_double_arithmetic
        and not incorrect_corner_selection
        and not unexpected_corner_selection
        and unsafe_hfma2_count == 0
        and not incorrect_memory
        and not unexpected_global_memory
        and reconvergence_balanced
        and not unexpected_reconvergence
    )
    report = {
        "schema_version": 1,
        "audit_kind": "lean_generated_polynomial_sass_binding",
        "sass_sha256": digest(sass_raw),
        "ptx_audit_sha256": digest(ptx_audit_raw),
        "ptx_sha256": ptx_audit.get("input_sha256"),
        "targets": targets,
        "functions": functions,
        "instruction_count": len(mnemonics),
        "mnemonic_counts": dict(sorted(counts.items())),
        "required_directed_sass_counts": actual,
        "expected_from_ptx_counts": raw_directed_from_ptx,
        "expected_directed_sass_counts_from_lowering_model": expected,
        "incorrect_directed_counts": incorrect,
        "balanced_duplicate_dmul_sites_eliminated_by_ptxas": eliminated,
        "expected_corner_selection_counts_from_ptx": raw_corner_selection_from_ptx,
        "expected_corner_selection_counts_from_lowering_model": expected_corner_selection,
        "actual_corner_selection_counts": actual_corner_selection,
        "balanced_duplicate_corner_sites_eliminated_by_ptxas": eliminated_corner_selection,
        "actual_corner_selector_counts": actual_selectors,
        "incorrect_corner_selection": incorrect_corner_selection,
        "unexpected_corner_selection_instructions": unexpected_corner_selection,
        "constant_forming_hfma2": {
            "total": hfma2_count,
            "reviewed_source_independent_patterns": safe_hfma2_count,
            "unsafe": unsafe_hfma2_count,
        },
        "forbidden_instructions": forbidden,
        "unexpected_double_arithmetic": unexpected_double_arithmetic,
        "expected_global_memory_counts_from_ptx": raw_memory_from_ptx,
        "expected_global_memory_counts_from_lowering_model": expected_memory,
        "actual_global_memory_counts": actual_memory,
        "incorrect_global_memory_counts": incorrect_memory,
        "unexpected_global_memory_instructions": unexpected_global_memory,
        "compiler_reconvergence_controls": reconvergence,
        "compiler_reconvergence_balanced": reconvergence_balanced,
        "unexpected_reconvergence_controls": unexpected_reconvergence,
        "lowering_model_valid": lowering_model_valid,
        "lowering_model_sha256": digest(
            json.dumps(lowering_model, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ),
        "passed": passed,
        "limitations": [
            "This is a lexical PTX-to-SASS site-count binding, not a semantics proof.",
            "It binds the current ptxas artifact and rejects fused or approximate lowering.",
            "Balanced BSSY/BSYNC.RECONVERGENT are compiler warp control-flow machinery, not an application memory barrier.",
        ],
    }
    if args.cubin is not None:
        cubin_raw = args.cubin.read_bytes()
        report["cubin_sha256"] = digest(cubin_raw)
        report["cubin_path"] = str(args.cubin.resolve())
        if not cubin_raw.startswith(b"\x7fELF"):
            report["passed"] = False
            report["cubin_error"] = "cubin is not an ELF image"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not report["passed"]:
        print(f"generated SASS inspection failed; see {args.output}", file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
