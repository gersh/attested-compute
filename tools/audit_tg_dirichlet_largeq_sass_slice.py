#!/usr/bin/env python3
"""Extract and validate one semantic SM90 addback slice from a large-q cubin.

The output is a compact restricted-IR certificate consumed by
``SparkInterval.SASS.FusedLargeQAddbackSlice``.  This tool checks instruction
operands and source attribution rather than aggregate opcode counts.  The Lean
module independently checks the resulting dataflow and proves interval-add
refinement; neither side claims a complete SASS or hardware semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


TARGET = re.compile(r"^\s*\.target\s+(sm_[0-9a-z]+)\s*$", re.MULTILINE)
FUNCTION_HEADER = re.compile(r"^//-+\s+\.text\.(\S+)\s+-+\s*$", re.MULTILINE)
INSTRUCTION = re.compile(
    r"/\*([0-9a-fA-F]+)\*/\s+(@[!A-Za-z0-9_.]+\s+)?"
    r"([A-Z][A-Z0-9_.]*)\s+(.+?)\s*;\s*$"
)
LINE_INFO = re.compile(r'^\s*//## File "([^"]+)", line ([0-9]+)(.*)$')
INLINE_LINE = re.compile(r'inlined at "([^"]+)", line ([0-9]+)')
REGISTER = re.compile(r"^R([0-9]+)(?:\.reuse)?$")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_suffix(path: str) -> str:
    return path.replace("\\", "/")


def parse_register(token: str) -> int:
    token = token.strip()
    match = REGISTER.fullmatch(token)
    if match is None:
        raise ValueError(f"unsupported DADD operand {token!r}")
    return int(match.group(1))


def parse_dadd(line: str, line_annotations: list[tuple[str, int]]) -> dict[str, Any] | None:
    match = INSTRUCTION.search(line)
    if match is None:
        return None
    offset, predicate, mnemonic, operand_text = match.groups()
    if mnemonic not in {"DADD.RM", "DADD.RP"}:
        return None
    if predicate is not None:
        return None
    operands = [item.strip() for item in operand_text.split(",")]
    if len(operands) != 3:
        return None
    try:
        destination = parse_register(operands[0])
        left = parse_register(operands[1])
        right = parse_register(operands[2])
    except ValueError:
        return None
    return {
        "offset": offset.lower(),
        "opcode": mnemonic,
        "destination": destination,
        "left": left,
        "right": right,
        "annotations": line_annotations,
        "raw": line.strip(),
    }


def function_region(text: str, required_name: str) -> str:
    headers = list(FUNCTION_HEADER.finditer(text))
    matches = [index for index, header in enumerate(headers) if required_name in header.group(1)]
    if len(matches) != 1:
        raise ValueError(
            f"expected one function containing {required_name!r}, found {len(matches)}"
        )
    index = matches[0]
    start = headers[index].start()
    end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
    return text[start:end]


def instruction_stream(region: str) -> list[dict[str, Any]]:
    """Decode every instruction while carrying the current line-info stack."""
    current_annotations: list[tuple[str, int]] = []
    stream: list[dict[str, Any]] = []
    pending_annotations = False
    for line in region.splitlines():
        line_match = LINE_INFO.match(line)
        if line_match is not None:
            if not pending_annotations:
                current_annotations = []
                pending_annotations = True
            current_annotations.append(
                (source_suffix(line_match.group(1)), int(line_match.group(2)))
            )
            for inline in INLINE_LINE.finditer(line_match.group(3)):
                current_annotations.append(
                    (source_suffix(inline.group(1)), int(inline.group(2)))
                )
            continue
        match = INSTRUCTION.search(line)
        if match is None:
            continue
        pending_annotations = False
        offset, predicate, mnemonic, operand_text = match.groups()
        record: dict[str, Any] = {
            "offset": offset.lower(),
            "predicate": None if predicate is None else predicate.strip(),
            "opcode": mnemonic,
            "operand_text": operand_text,
            "annotations": list(current_annotations),
            "raw": line.strip(),
        }
        if mnemonic in {"DADD.RM", "DADD.RP"}:
            parsed = parse_dadd(line, current_annotations)
            if parsed is not None:
                record.update(parsed)
                record["supported"] = True
            else:
                record["supported"] = False
        stream.append(record)
    return stream


def has_source_stack(
    record: dict[str, Any], source_file: str, helper: int, call: int, kernel: int
) -> bool:
    suffix = source_suffix(source_file)
    lines = {
        line
        for path, line in record["annotations"]
        if source_suffix(path).endswith(suffix)
    }
    return {helper, call, kernel}.issubset(lines)


def find_slice(
    region: str, source_file: str, helper: int, call: int, kernel: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    stream = instruction_stream(region)
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for lower, upper in zip(stream, stream[1:]):
        if lower["opcode"] != "DADD.RM" or upper["opcode"] != "DADD.RP":
            continue
        if lower.get("supported") is not True or upper.get("supported") is not True:
            continue
        if not has_source_stack(lower, source_file, helper, call, kernel):
            continue
        if not has_source_stack(upper, source_file, helper, call, kernel):
            continue
        if lower["predicate"] is not None or upper["predicate"] is not None:
            continue
        if lower["destination"] != lower["left"]:
            continue
        if upper["destination"] != upper["left"]:
            continue
        if lower["destination"] in {
            upper["destination"],
            upper["left"],
            upper["right"],
        }:
            continue
        candidates.append((lower, upper))
    if len(candidates) != 1:
        raise ValueError(f"expected one supported adjacent addback pair, found {len(candidates)}")
    return candidates[0]


def plain_instruction_at(region: str, offset: str) -> dict[str, Any]:
    matches = []
    for line in region.splitlines():
        parsed = parse_dadd(line, [])
        if parsed is not None and parsed["offset"] == offset:
            matches.append(parsed)
    if len(matches) != 1:
        raise ValueError(f"plain SASS has {len(matches)} DADD instructions at {offset}")
    return matches[0]


def line_text(source: str, number: int) -> str:
    lines = source.splitlines()
    if number <= 0 or number > len(lines):
        raise ValueError(f"source line {number} is out of range")
    return lines[number - 1].strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cubin", type=Path)
    parser.add_argument("sass", type=Path, help="plain nvdisasm --print-code output")
    parser.add_argument(
        "line_info_sass",
        type=Path,
        help="nvdisasm --print-code --print-line-info-inline output",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-file", default="gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu")
    parser.add_argument("--function", default="reconstructComposeKernel")
    parser.add_argument("--helper-line", type=int, default=54)
    parser.add_argument("--call-line", type=int, default=88)
    parser.add_argument("--kernel-line", type=int, default=158)
    args = parser.parse_args()

    try:
        cubin_raw = args.cubin.read_bytes()
        sass_raw = args.sass.read_bytes()
        line_raw = args.line_info_sass.read_bytes()
        source_raw = args.source.read_bytes()
        if not cubin_raw.startswith(b"\x7fELF"):
            raise ValueError("cubin is not an ELF image")
        sass_text = sass_raw.decode("utf-8", errors="strict")
        line_text_value = line_raw.decode("utf-8", errors="strict")
        source_text = source_raw.decode("utf-8", errors="strict")
        if sorted(set(TARGET.findall(sass_text))) != ["sm_90"]:
            raise ValueError("plain SASS is not uniquely targeted at sm_90")
        if sorted(set(TARGET.findall(line_text_value))) != ["sm_90"]:
            raise ValueError("line-info SASS is not uniquely targeted at sm_90")

        line_region = function_region(line_text_value, args.function)
        plain_region = function_region(sass_text, args.function)
        lower, upper = find_slice(
            line_region,
            args.source_file,
            args.helper_line,
            args.call_line,
            args.kernel_line,
        )
        plain_lower = plain_instruction_at(plain_region, lower["offset"])
        plain_upper = plain_instruction_at(plain_region, upper["offset"])
        semantic_keys = ("offset", "opcode", "destination", "left", "right")
        if any(plain_lower[key] != lower[key] for key in semantic_keys):
            raise ValueError("plain and line-info SASS disagree on lower instruction")
        if any(plain_upper[key] != upper[key] for key in semantic_keys):
            raise ValueError("plain and line-info SASS disagree on upper instruction")

        helper_source = line_text(source_text, args.helper_line)
        call_source = line_text(source_text, args.call_line)
        kernel_source = line_text(source_text, args.kernel_line)
        if "__dadd_rd" not in helper_source or "__dadd_ru" not in helper_source:
            raise ValueError("helper source line is not the directed interval addition")
        if "add(x.re, y.re)" not in call_source or "add(x.im, y.im)" not in call_source:
            raise ValueError("call source line is not complex interval addition")
        if "output[flat] = cadd" not in kernel_source:
            raise ValueError("kernel source line is not the final finite-recovery addback")

        canonical_excerpt = (
            f"/*{lower['offset']}*/ {lower['opcode']} R{lower['destination']}, "
            f"R{lower['left']}, R{lower['right']} ;\n"
            f"/*{upper['offset']}*/ {upper['opcode']} R{upper['destination']}, "
            f"R{upper['left']}, R{upper['right']} ;\n"
        )
        certificate = {
            "schema_version": 1,
            "audit_kind": "tg_dirichlet_largeq_sm90_addback_semantic_slice",
            "passed": True,
            "target": "sm_90",
            "source_file": args.source_file,
            "source_lines": {
                "directed_add_helper": args.helper_line,
                "complex_add_call": args.call_line,
                "kernel_addback": args.kernel_line,
            },
            "function": args.function,
            "source_sha256": sha256(source_raw),
            "cubin_sha256": sha256(cubin_raw),
            "sass_sha256": sha256(sass_raw),
            "line_info_sass_sha256": sha256(line_raw),
            "canonical_excerpt": canonical_excerpt,
            "restricted_ir": {
                "instructions": [
                    {key: lower[key] for key in semantic_keys},
                    {key: upper[key] for key in semantic_keys},
                ],
                "left": {"lo": lower["left"], "hi": upper["left"]},
                "right": {"lo": lower["right"], "hi": upper["right"]},
                "result": {
                    "lo": lower["destination"],
                    "hi": upper["destination"],
                },
                "lower_operands_swapped": False,
                "upper_operands_swapped": False,
            },
            "lean": {
                "module": "SparkInterval.SASS.FusedLargeQAddbackSlice",
                "checker": "FusedLargeQAddbackCertificate.check",
                "refinement_theorem": (
                    "SparkInterval.SASS.SM90."
                    "fusedLargeQFinalImaginaryAddback_refinesIntervalAdd"
                ),
            },
            "limitations": [
                "The restricted-IR checker covers only this unpredicated DADD.RM/DADD.RP pair.",
                "nvdisasm correctness and the relation between its text and cubin bytes are not proved in Lean.",
                "The Lean instruction model is not a complete NVIDIA SASS semantics.",
                "Reachability, register provenance, surrounding arithmetic, memory, driver, and H100 execution remain outside this slice.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(certificate, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(f"large-q SASS slice audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
