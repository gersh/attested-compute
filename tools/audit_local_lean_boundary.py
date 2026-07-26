#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Audit that the default Lean build cannot reach production materialization."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import safe_lake_build as safe_build  # noqa: E402


REQUIRED_EXPLICIT_ONLY = frozenset(
    {
        "SparkInterval.Execution.RegisteredAlgorithm",
        "SparkInterval.Execution.RunCertificate",
        "SparkInterval.Generated.CDEMAbelProduction",
        "SparkInterval.Generated.PlattHeadQ128",
    }
)


def audit() -> dict[str, object]:
    lake = tomllib.loads((ROOT / "lakefile.toml").read_text(encoding="utf-8"))
    if lake.get("defaultTargets") != [safe_build.COMPACT_LIBRARY_TARGET]:
        raise ValueError(
            "lakefile defaultTargets must contain only SparkIntervalCompact"
        )
    compact_libraries = [
        item
        for item in lake.get("lean_lib", [])
        if item.get("name") == safe_build.COMPACT_LIBRARY_TARGET
    ]
    if compact_libraries != [
        {
            "name": safe_build.COMPACT_LIBRARY_TARGET,
            "roots": [safe_build.COMPACT_ROOT_MODULE],
            "precompileModules": False,
        }
    ]:
        raise ValueError(
            "SparkIntervalCompact must be a root-only library with no broad glob"
        )

    sources = safe_build.local_sources()
    contents = safe_build.read_source_contents(sources)
    graph = safe_build.local_graph_from_contents(contents)
    selected, source_bytes, source_lines = safe_build.compact_closure(
        graph, contents
    )
    broad = safe_build.full_production_library_closure(graph)
    leaked = sorted(REQUIRED_EXPLICIT_ONLY & selected)
    if leaked:
        raise ValueError(
            "production-only modules leaked into compact closure: "
            + ", ".join(leaked)
        )
    missing = sorted(REQUIRED_EXPLICIT_ONLY - broad)
    if missing:
        raise ValueError(
            "explicit production library no longer contains expected boundary "
            "modules: " + ", ".join(missing)
        )
    return {
        "compact_root": safe_build.COMPACT_ROOT_MODULE,
        "default_target": safe_build.COMPACT_LIBRARY_TARGET,
        "explicit_production_target": safe_build.FULL_LIBRARY_TARGET,
        "module_count": len(selected),
        "production_modules_excluded": sorted(REQUIRED_EXPLICIT_ONLY),
        "source_bytes": source_bytes,
        "source_bytes_max": safe_build.COMPACT_SOURCE_BYTES_MAX,
        "source_lines": source_lines,
        "source_lines_max": safe_build.COMPACT_SOURCE_LINES_MAX,
    }


def main() -> int:
    try:
        print(json.dumps(audit(), sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"local Lean boundary audit failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
