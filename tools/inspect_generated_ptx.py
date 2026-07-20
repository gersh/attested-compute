#!/usr/bin/env python3
"""Independent lexical audit for Lean-generated Phase 5 PTX.

The authoritative generator validation is over the typed Lean AST.  This
post-emission audit checks that the concrete text still contains only the
expected target-selected polynomial-kernel instruction vocabulary.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED = {
    "ld.param.u64",
    "mov.u16",
    "mov.u32",
    "mov.b64",
    "mul.wide.u32",
    "mul.lo.u64",
    "cvt.u64.u32",
    "cvta.to.global.u64",
    "add.u64",
    "and.b64",
    "xor.b64",
    "setp.eq.u64",
    "setp.ge.u64",
    "bra",
    "ld.global.b64",
    "st.global.b64",
    "st.global.u8",
    "add.rm.f64",
    "add.rp.f64",
    "sub.rm.f64",
    "sub.rp.f64",
    "mul.rm.f64",
    "mul.rp.f64",
    "min.f64",
    "max.f64",
    "ret",
}
FORBIDDEN_ROUNDING = re.compile(r"\.(?:rn|rz)\.f64\b")
TARGET_DIRECTIVE = re.compile(r"^\.target\s+(\S+)$", re.MULTILINE)
VERSION = re.compile(r"^\.version 9\.0$", re.MULTILINE)
ADDRESS_SIZE = re.compile(r"^\.address_size 64$", re.MULTILINE)
ENTRY = re.compile(r"^\.visible \.entry sparkinterval_generated\($", re.MULTILINE)
ABI = re.compile(
    r"^\.visible \.global \.align 4 \.u32 "
    r"sparkinterval_generated_abi_version = 1;$",
    re.MULTILINE,
)
VARIABLE_COUNT = re.compile(
    r"^\.visible \.global \.align 4 \.u32 "
    r"sparkinterval_generated_variable_count = ([0-9]+);$",
    re.MULTILINE,
)
INSTRUCTION = re.compile(
    r"^(?:@!?%[A-Za-z0-9_]+\s+)?([a-z][a-z0-9_.]*)"
    r"(?:\s+[^;]+)?;$"
)
LABEL = re.compile(r"^\$L[0-9]+:$")
REGISTER_DECLARATIONS = {
    "pred": re.compile(r"^\.reg \.pred %p<[1-9][0-9]*>;$"),
    "byte": re.compile(r"^\.reg \.b16 %rs<[1-9][0-9]*>;$"),
    "u32": re.compile(r"^\.reg \.u32 %r<[1-9][0-9]*>;$"),
    "u64": re.compile(r"^\.reg \.b64 %rd<[1-9][0-9]*>;$"),
    "f64_bits": re.compile(r"^\.reg \.b64 %fd<[1-9][0-9]*>;$"),
}
PARAMETERS = (
    ".param .u64 sparkinterval_generated_param_rows,",
    ".param .u64 sparkinterval_generated_param_outputs,",
    ".param .u64 sparkinterval_generated_param_row_count",
)
FIXED_HEADER_DIRECTIVES = {
    ".version 9.0",
    ".address_size 64",
    ".visible .global .align 4 .u32 sparkinterval_generated_abi_version = 1;",
}

LOAD_F64 = re.compile(
    r"^ld\.global\.b64 %fd([0-9]+), \[%rd([0-9]+)\+([0-9]+)\];$"
)
STORE_F64 = re.compile(
    r"^st\.global\.b64 \[%rd([0-9]+)\+([0-9]+)\], %fd([0-9]+);$"
)
MOV_F64_BITS = re.compile(r"^mov\.b64 %fd([0-9]+), 0x([0-9a-f]{16});$")
XOR_F64_SIGN = re.compile(
    r"^xor\.b64 %fd([0-9]+), %fd([0-9]+), 0x8000000000000000;$"
)
BINARY_F64 = re.compile(
    r"^(add|sub|mul)\.(rm|rp)\.f64 %fd([0-9]+), %fd([0-9]+), %fd([0-9]+);$"
)
CORNER_F64 = re.compile(
    r"^(min|max)\.f64 %fd([0-9]+), %fd([0-9]+), %fd([0-9]+);$"
)
EXPONENT_F64 = re.compile(
    r"^and\.b64 %rd[0-9]+, %fd([0-9]+), 0x7ff0000000000000;$"
)


def _canonical_pair(left: int, right: int) -> tuple[int, int]:
    """Canonicalize operands of a commutative symbolic operation."""

    return (left, right) if left <= right else (right, left)


def analyze_lowering(text: str, instruction_counts: Counter[str]) -> dict[str, Any]:
    """Predict the expected lowering counts for the generated SSA subset.

    ptxas performs dead-code elimination, common-subexpression elimination, and
    exponent-only load narrowing on this kernel family.  Raw PTX site counts are
    therefore not a sound SASS binding.  This analysis works backwards from
    output stores and nonfinite guards, then value-numbers the demanded floating
    expressions.  It intentionally accepts only the deterministic patterns
    emitted by ``sparkinterval-gen``.
    """

    # A definition is (kind, payload).  Kinds are load, const, xor, one of the
    # directed PTX opcodes, min.f64, or max.f64.
    definitions: dict[int, tuple[str, tuple[Any, ...]]] = {}
    guard_sources: list[int] = []
    store_sources: list[int] = []
    parsed_definition_counts: Counter[str] = Counter()
    parsed_exponents = 0
    parsed_stores = 0
    errors: list[str] = []

    def define(register: int, kind: str, payload: tuple[Any, ...]) -> None:
        if register in definitions:
            errors.append(f"%fd{register} has more than one definition")
            return
        definitions[register] = (kind, payload)
        parsed_definition_counts[kind] += 1

    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        if match := LOAD_F64.fullmatch(line):
            define(
                int(match.group(1)),
                "ld.global.b64",
                (int(match.group(2)), int(match.group(3))),
            )
            continue
        if match := MOV_F64_BITS.fullmatch(line):
            define(int(match.group(1)), "const", (int(match.group(2), 16),))
            continue
        if match := XOR_F64_SIGN.fullmatch(line):
            define(int(match.group(1)), "xor", (int(match.group(2)),))
            continue
        if match := BINARY_F64.fullmatch(line):
            opcode = f"{match.group(1)}.{match.group(2)}.f64"
            define(
                int(match.group(3)),
                opcode,
                (int(match.group(4)), int(match.group(5))),
            )
            continue
        if match := CORNER_F64.fullmatch(line):
            opcode = f"{match.group(1)}.f64"
            define(
                int(match.group(2)),
                opcode,
                (int(match.group(3)), int(match.group(4))),
            )
            continue
        if match := EXPONENT_F64.fullmatch(line):
            guard_sources.append(int(match.group(1)))
            parsed_exponents += 1
            continue
        if match := STORE_F64.fullmatch(line):
            store_sources.append(int(match.group(3)))
            parsed_stores += 1
            continue

        opcode_match = INSTRUCTION.fullmatch(line)
        if opcode_match is not None and opcode_match.group(1) in {
            "ld.global.b64",
            "mov.b64",
            "xor.b64",
            "add.rm.f64",
            "add.rp.f64",
            "sub.rm.f64",
            "sub.rp.f64",
            "mul.rm.f64",
            "mul.rp.f64",
            "min.f64",
            "max.f64",
            "and.b64",
            "st.global.b64",
        }:
            errors.append(f"lowering model cannot parse instruction: {line}")

    expected_definition_counts = {
        opcode: instruction_counts.get(opcode, 0)
        for opcode in (
            "ld.global.b64",
            "mov.b64",
            "xor.b64",
            "add.rm.f64",
            "add.rp.f64",
            "sub.rm.f64",
            "sub.rp.f64",
            "mul.rm.f64",
            "mul.rp.f64",
            "min.f64",
            "max.f64",
        )
    }
    # mov.b64 is represented as a symbolic constant in the model.
    actual_definition_counts = dict(parsed_definition_counts)
    actual_definition_counts["mov.b64"] = actual_definition_counts.pop("const", 0)
    actual_definition_counts["xor.b64"] = actual_definition_counts.pop("xor", 0)
    for opcode, expected_count in expected_definition_counts.items():
        if actual_definition_counts.get(opcode, 0) != expected_count:
            errors.append(
                f"lowering model parsed {actual_definition_counts.get(opcode, 0)} "
                f"{opcode} definitions, expected {expected_count}"
            )
    if parsed_exponents != instruction_counts.get("and.b64", 0):
        errors.append("lowering model did not parse every exponent extraction")
    if parsed_stores != instruction_counts.get("st.global.b64", 0):
        errors.append("lowering model did not parse every binary64 store")
    if instruction_counts.get("st.global.b64", 0) != 4:
        errors.append("generated PTX must contain the two exact binary64 output paths")
    if instruction_counts.get("st.global.u8", 0) != 16:
        errors.append("generated PTX must contain the two exact status output paths")

    # Compact hash-consing is essential here: a power expression reuses its base
    # in every multiplication, so recursively nested tuple keys grow
    # exponentially.  Each semantic node instead stores only integer child IDs.
    node_ids: dict[tuple[Any, ...], int] = {}
    node_keys: list[tuple[Any, ...]] = []
    node_depends_on_load: list[bool] = []
    value_id_cache: dict[int, int] = {}
    value_id_visiting: set[int] = set()

    def intern_node(key: tuple[Any, ...], depends_on_load: bool) -> int:
        existing = node_ids.get(key)
        if existing is not None:
            if node_depends_on_load[existing] != depends_on_load:
                errors.append("inconsistent load dependency for interned value")
            return existing
        result = len(node_keys)
        node_ids[key] = result
        node_keys.append(key)
        node_depends_on_load.append(depends_on_load)
        return result

    def value_id(register: int) -> int:
        if register in value_id_cache:
            return value_id_cache[register]
        if register in value_id_visiting:
            errors.append(f"cyclic floating definition at %fd{register}")
            return intern_node(("error", register), False)
        definition = definitions.get(register)
        if definition is None:
            errors.append(f"%fd{register} is used without a modeled definition")
            return intern_node(("undefined", register), False)
        value_id_visiting.add(register)
        kind, payload = definition
        if kind == "ld.global.b64":
            result = intern_node(("load", payload[0], payload[1]), True)
        elif kind == "const":
            result = intern_node(("const", payload[0]), False)
        elif kind == "xor":
            child = value_id(int(payload[0]))
            child_key = node_keys[child]
            if child_key[0] == "const":
                result = intern_node(
                    ("const", int(child_key[1]) ^ 0x8000000000000000), False
                )
            elif child_key[0] == "xor":
                result = int(child_key[1])
            else:
                result = intern_node(
                    ("xor", child), node_depends_on_load[child]
                )
        else:
            left = value_id(int(payload[0]))
            right = value_id(int(payload[1]))
            if kind.startswith(("add.", "mul.")) or kind in {"min.f64", "max.f64"}:
                left, right = _canonical_pair(left, right)
            if kind in {"min.f64", "max.f64"} and left == right:
                result = left
            else:
                result = intern_node(
                    (kind, left, right),
                    node_depends_on_load[left] or node_depends_on_load[right],
                )
        value_id_visiting.remove(register)
        value_id_cache[register] = result
        return result

    # Demand levels: 1 means only exponent bits are needed; 2 means the complete
    # binary64 value is needed.  Complete demand dominates exponent-only demand.
    demands: dict[int, int] = {}
    pending: list[tuple[int, int]] = []

    def add_demand(register: int, level: int) -> None:
        if demands.get(register, 0) >= level:
            return
        demands[register] = level
        pending.append((register, level))

    for register in store_sources:
        add_demand(register, 2)
    for register in guard_sources:
        add_demand(register, 1)

    while pending:
        register, level = pending.pop()
        # A later full demand supersedes an earlier queued exponent demand.
        if demands.get(register, 0) != level:
            continue
        definition = definitions.get(register)
        if definition is None:
            errors.append(f"%fd{register} demand has no modeled definition")
            continue
        kind, payload = definition
        if kind in {"ld.global.b64", "const"}:
            continue
        if kind == "xor":
            add_demand(int(payload[0]), level)
            continue
        # The exponent of an arithmetic or min/max result depends on the full
        # operands, so either result demand promotes both inputs to Full64.
        add_demand(int(payload[0]), 2)
        add_demand(int(payload[1]), 2)

    load_demands: dict[tuple[int, int], int] = {}
    demanded_value_sets: dict[str, set[int]] = {
        opcode: set()
        for opcode in (
            "add.rm.f64",
            "add.rp.f64",
            "sub.rm.f64",
            "sub.rp.f64",
            "mul.rm.f64",
            "mul.rp.f64",
            "min.f64",
            "max.f64",
        )
    }
    for register, level in demands.items():
        definition = definitions.get(register)
        if definition is None:
            continue
        kind, payload = definition
        if kind == "ld.global.b64":
            address = (int(payload[0]), int(payload[1]))
            load_demands[address] = max(load_demands.get(address, 0), level)
        elif kind in demanded_value_sets:
            left = value_id(int(payload[0]))
            right = value_id(int(payload[1]))
            if kind.startswith(("add.", "mul.")) or kind in {"min.f64", "max.f64"}:
                left, right = _canonical_pair(left, right)
            if kind in {"min.f64", "max.f64"} and left == right:
                continue
            demanded_value_sets[kind].add(value_id(register))

    # Force key validation for every root even if it did not introduce a child
    # demand (for example a direct constant store or guard).
    for register in set(store_sources + guard_sources):
        value_id(register)

    full_addresses = sorted(address for address, level in load_demands.items() if level == 2)
    exponent_addresses = sorted(
        address for address, level in load_demands.items() if level == 1
    )
    dynamic_whole_guard = any(
        node_depends_on_load[value_id(register)] for register in guard_sources
    )

    expected_sass = {
        "DADD.RM": len(demanded_value_sets["add.rm.f64"])
        + len(demanded_value_sets["sub.rm.f64"]),
        "DADD.RP": len(demanded_value_sets["add.rp.f64"])
        + len(demanded_value_sets["sub.rp.f64"]),
        "DMUL.RM": len(demanded_value_sets["mul.rm.f64"]),
        "DMUL.RP": len(demanded_value_sets["mul.rp.f64"]),
        "DSETP.MIN.AND": len(demanded_value_sets["min.f64"]),
        "DSETP.MAX.AND": len(demanded_value_sets["max.f64"]),
        "LDG.E.64": len(full_addresses),
        "LDG.E": len(exponent_addresses),
        "STG.E.64": 4 if dynamic_whole_guard else 2,
        "STG.E.U8": 16 if dynamic_whole_guard else 8,
    }
    selector_count = expected_sass["DSETP.MIN.AND"] + expected_sass["DSETP.MAX.AND"]
    expected_sass["FSEL"] = selector_count
    expected_sass["SEL"] = selector_count

    return {
        "schema_version": 1,
        "analysis_kind": "generated_ptx_demand_and_value_numbering_v1",
        "passed": not errors,
        "errors": errors,
        "guard_source_count": len(guard_sources),
        "dynamic_whole_guard": dynamic_whole_guard,
        "full_global_load_addresses": [
            {"base_register": f"%rd{base}", "offset": offset}
            for base, offset in full_addresses
        ],
        "exponent_only_global_load_addresses": [
            {"base_register": f"%rd{base}", "offset": offset}
            for base, offset in exponent_addresses
        ],
        "distinct_demanded_ptx_values": {
            opcode: len(values) for opcode, values in demanded_value_sets.items()
        },
        "expected_sass_counts": expected_sass,
    }


def parse_instructions(
    text: str, *, expected_target: str,
) -> tuple[list[str], list[str], list[str], list[str], dict[str, int]]:
    instructions: list[str] = []
    unparsed: list[str] = []
    unknown_directives: list[str] = []
    grammar_errors: list[str] = []
    state = "header"
    parameter_index = 0
    register_declarations = {name: 0 for name in REGISTER_DECLARATIONS}
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        if state == "done":
            grammar_errors.append(f"content after module close: {line}")
            continue
        if state == "parameters":
            if parameter_index < len(PARAMETERS) and line == PARAMETERS[parameter_index]:
                parameter_index += 1
            elif parameter_index == len(PARAMETERS) and line == ")":
                state = "await_body"
            else:
                grammar_errors.append(f"unexpected entry parameter line: {line}")
            continue
        if state == "await_body":
            if line == "{":
                state = "body"
            else:
                grammar_errors.append(f"expected entry body, found: {line}")
            continue
        if state == "header":
            if line in FIXED_HEADER_DIRECTIVES or line == f".target {expected_target}":
                continue
            if VARIABLE_COUNT.fullmatch(line) is not None:
                continue
            if line == ".visible .entry sparkinterval_generated(":
                state = "parameters"
                parameter_index = 0
                continue
            if line.startswith("."):
                unknown_directives.append(line)
            else:
                grammar_errors.append(f"unexpected header line: {line}")
            continue
        if state != "body":
            grammar_errors.append(f"invalid parser state at line: {line}")
            continue
        if line == "}":
            state = "done"
        elif line.startswith(".reg"):
            matched = False
            for name, pattern in REGISTER_DECLARATIONS.items():
                if pattern.fullmatch(line) is not None:
                    register_declarations[name] += 1
                    matched = True
                    break
            if not matched:
                unknown_directives.append(line)
        elif LABEL.fullmatch(line) is not None:
            continue
        elif line.startswith("."):
            unknown_directives.append(line)
        else:
            match = INSTRUCTION.fullmatch(line)
            if match is None:
                unparsed.append(line)
            else:
                instructions.append(match.group(1))
    if state != "done":
        grammar_errors.append(f"module ended in parser state {state}")
    return (
        instructions,
        unparsed,
        unknown_directives,
        grammar_errors,
        register_declarations,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--target",
        choices=("sm_121", "sm_90"),
        default="sm_121",
        help="exact PTX deployment target to require (default: sm_121)",
    )
    args = parser.parse_args()

    raw = args.input.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    (
        instructions,
        unparsed,
        unknown_directives,
        grammar_errors,
        register_declarations,
    ) = parse_instructions(text, expected_target=args.target)
    instruction_counts = Counter(instructions)
    lowering_model = analyze_lowering(text, instruction_counts)
    unexpected = sorted(set(instructions) - ALLOWED)
    variable_counts = [int(value) for value in VARIABLE_COUNT.findall(text)]
    forbidden_rounding = sorted(set(FORBIDDEN_ROUNDING.findall(text)))
    observed_targets = TARGET_DIRECTIVE.findall(text)
    passed = (
        bool(instructions)
        and len(VERSION.findall(text)) == 1
        and observed_targets == [args.target]
        and len(ADDRESS_SIZE.findall(text)) == 1
        and len(ENTRY.findall(text)) == 1
        and len(ABI.findall(text)) == 1
        and len(variable_counts) == 1
        and 0 <= variable_counts[0] <= 64
        and not unexpected
        and not unparsed
        and not unknown_directives
        and not grammar_errors
        and not forbidden_rounding
        and lowering_model["passed"]
        and all(count == 1 for count in register_declarations.values())
        and instructions[-1] == "ret"
    )
    report = {
        "schema_version": 1,
        "audit_kind": "lean_generated_polynomial_ptx_allowlist",
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "target": args.target,
        "observed_targets": observed_targets,
        "version_9_0_count": len(VERSION.findall(text)),
        "address_size_64_count": len(ADDRESS_SIZE.findall(text)),
        "variable_counts": variable_counts,
        "register_declaration_counts": register_declarations,
        "instruction_count": len(instructions),
        "instruction_counts": dict(sorted(instruction_counts.items())),
        "lowering_model": lowering_model,
        "unexpected_instructions": unexpected,
        "forbidden_rounding_tokens": forbidden_rounding,
        "unparsed_code_lines": unparsed,
        "unknown_directives": unknown_directives,
        "grammar_errors": grammar_errors,
        "passed": passed,
        "limitations": [
            "This is an independent lexical audit, not a PTX operational semantics.",
            "The typed Lean AST and validator are the primary generation boundary.",
            "ptxas/SASS preservation is checked separately.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    if not passed:
        print(f"generated PTX inspection failed; see {args.output}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
