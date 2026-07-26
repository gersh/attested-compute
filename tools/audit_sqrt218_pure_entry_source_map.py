#!/usr/bin/env python3
"""Audit the documented Sqrt218 pure-entry accepting call graph.

This script performs source-text analysis only.  It never opens, parses, or
validates a Sqrt218 certificate.  Starting at ``tg_sq218_verify_snapshot_v2``,
it extracts locally defined ``tg_*`` C functions, follows calls between them,
and requires an exact match with the first column of the human source map.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
C_SOURCES = (
    REPOSITORY_ROOT / "cpu_checker/sqrt218/sqrt218_cpu_checker.c",
    REPOSITORY_ROOT / "cpu_checker/sqrt218/sqrt218_cpu_command.c",
)
SOURCE_MAP = (
    REPOSITORY_ROOT
    / "docs/algorithms/SQRT218_PURE_ENTRY_SOURCE_REFINEMENT_MAP.md"
)
PURE_ENTRY = "tg_sq218_verify_snapshot_v2"

FUNCTION_DEFINITION = re.compile(
    r"(?m)^(?:static\s+)?"
    r"[A-Za-z_][A-Za-z0-9_]*(?:\s+|\s*\*\s*)+"
    r"(?P<name>tg_[A-Za-z0-9_]+)\s*\("
)
FUNCTION_CALL = re.compile(r"\b(tg_[A-Za-z0-9_]+)\s*\(")
MAPPED_TABLE_ROW = re.compile(
    r"(?m)^\|\s*`(?P<name>tg_[A-Za-z0-9_]+)`\s*\|"
)


@dataclass(frozen=True)
class CFunction:
    source: Path
    calls: frozenset[str]


def _blank(match: re.Match[str]) -> str:
    """Preserve offsets and newlines while removing lexical distractions."""

    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def strip_comments_and_literals(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", _blank, source, flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", _blank, source)
    source = re.sub(r'"(?:\\.|[^"\\])*"', _blank, source)
    source = re.sub(r"'(?:\\.|[^'\\])*'", _blank, source)
    return source


def _matching_brace(source: str, opening: int) -> int:
    depth = 1
    cursor = opening + 1
    while cursor < len(source) and depth:
        if source[cursor] == "{":
            depth += 1
        elif source[cursor] == "}":
            depth -= 1
        cursor += 1
    if depth:
        raise ValueError(f"unclosed function body at byte offset {opening}")
    return cursor - 1


def extract_functions(paths: tuple[Path, ...] = C_SOURCES) -> dict[str, CFunction]:
    functions: dict[str, CFunction] = {}
    for path in paths:
        source = strip_comments_and_literals(path.read_text(encoding="utf-8"))
        for match in FUNCTION_DEFINITION.finditer(source):
            name = match.group("name")
            opening = source.find("{", match.end())
            if opening < 0:
                raise ValueError(f"{path}: no body found for {name}")
            semicolon = source.find(";", match.end(), opening)
            if semicolon >= 0:
                # A column-zero prototype, if one is ever added.
                continue
            closing = _matching_brace(source, opening)
            body = source[opening + 1 : closing]
            if name in functions:
                raise ValueError(f"duplicate C function definition: {name}")
            functions[name] = CFunction(
                source=path,
                calls=frozenset(FUNCTION_CALL.findall(body)),
            )
    return functions


def accepting_reachable(functions: dict[str, CFunction]) -> set[str]:
    if PURE_ENTRY not in functions:
        raise ValueError(f"pure entry definition disappeared: {PURE_ENTRY}")
    reachable: set[str] = set()
    pending = [PURE_ENTRY]
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        local_calls = functions[name].calls.intersection(functions)
        pending.extend(sorted(local_calls - reachable))
    return reachable


def documented_functions(path: Path = SOURCE_MAP) -> list[str]:
    names = [
        match.group("name")
        for match in MAPPED_TABLE_ROW.finditer(path.read_text(encoding="utf-8"))
    ]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(
            "duplicate mapped C function rows: " + ", ".join(duplicates)
        )
    return names


def audit() -> tuple[int, int]:
    functions = extract_functions()
    reachable = accepting_reachable(functions)
    documented = set(documented_functions())

    missing_from_map = sorted(reachable - documented)
    stale_or_unreachable = sorted(documented - reachable)
    if missing_from_map or stale_or_unreachable:
        messages = []
        if missing_from_map:
            messages.append(
                "reachable but not mapped: " + ", ".join(missing_from_map)
            )
        if stale_or_unreachable:
            messages.append(
                "mapped but absent/unreachable: "
                + ", ".join(stale_or_unreachable)
            )
        raise ValueError("; ".join(messages))

    return len(reachable), len(functions)


def main() -> int:
    try:
        reachable_count, definition_count = audit()
    except (OSError, ValueError) as error:
        print(f"sqrt218 pure-entry source-map audit failed: {error}", file=sys.stderr)
        return 1
    print(
        "sqrt218 pure-entry source-map audit passed: "
        f"{reachable_count} accepting-path functions mapped "
        f"({definition_count} local tg_* definitions scanned)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
