#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build compact or explicitly selected Lean modules with bounded resources.

With no arguments this builds only ``SparkIntervalCompact``.  The broad
library contains materialized production certificates and is reachable only
through the deliberately named ``--full-production-library`` option.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    PROJECT_ROOT / "SparkInterval",
    PROJECT_ROOT / "TGComputeContracts",
)
TOP_LEVEL_SOURCES = (PROJECT_ROOT / "SparkIntervalCompact.lean",)
MEMORY_RUNNER = PROJECT_ROOT / "tools" / "with_memory_limit.sh"
PLAN_LOCK = PROJECT_ROOT / ".lake" / "sparkinterval-safe-plan.lock"
SOURCE_CHANGED_EXIT = 66
IMPORT_RE = re.compile(r"^\s*(?:public\s+)?import\s+([A-Za-z_][A-Za-z0-9_'.]*)\s*(?:--.*)?$")
COMPACT_ROOT_MODULE = "SparkIntervalCompact"
COMPACT_LIBRARY_TARGET = "SparkIntervalCompact"
FULL_LIBRARY_TARGET = "SparkInterval"
# The compact root now includes the source-shaped checker-to-claim adapters
# for all ten physical ternary-Goldbach campaigns.  It still excludes every
# generated production table, receipt replay, and registered application
# execution relation.  Keep an explicit ceiling, but size it for this broader
# ordinary-proof closure rather than the former Sqrt218-only root.
COMPACT_SOURCE_BYTES_MAX = 2 * 1024 * 1024
COMPACT_SOURCE_LINES_MAX = 50000
COMPACT_FORBIDDEN_PREFIXES = (
    "SparkInterval.Execution.Registered",
    "SparkInterval.Execution.Signed",
    "SparkInterval.Execution.Trusted",
    "SparkInterval.Generated.",
)
COMPACT_FORBIDDEN_MODULES = frozenset(
    {
        "SparkInterval.Execution.Attestation",
        "SparkInterval.Execution.CompactAttestedVerifier",
        "SparkInterval.Execution.RunCertificate",
    }
)
PRODUCTION_MATERIALIZED_PREFIXES = (
    "SparkInterval.Execution.Registered",
    "SparkInterval.Generated.",
)
EXECUTABLE_ROOTS = {
    "sparkinterval-gen": "SparkInterval.GeneratePTX",
    "sparkinterval-check-certificate": "SparkInterval.Certificate.CLI",
}
BLUEPRINT_MODULE = "SparkInterval.Blueprint"
SAFE_LAKE_TASKS_MAX = "64"
BLUEPRINT_TASKS_MAX = SAFE_LAKE_TASKS_MAX
BLUEPRINT_FACETS = {
    "blueprint-json": "blueprintJson",
    "blueprint-tex": "blueprint",
}


class SourceChangedError(RuntimeError):
    """A selected Lean source changed after the serial plan was captured."""


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(PROJECT_ROOT).with_suffix("").parts)


def local_sources() -> dict[str, Path]:
    paths = [
        path
        for root in SOURCE_ROOTS
        for path in root.rglob("*.lean")
    ]
    paths.extend(path for path in TOP_LEVEL_SOURCES if path.is_file())
    return {
        module_name(path): path
        for path in sorted(paths)
    }


def read_source_contents(sources: dict[str, Path]) -> dict[str, bytes]:
    return {
        name: path.read_bytes()
        for name, path in sources.items()
    }


def local_graph_from_contents(
    contents: dict[str, bytes],
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for name, source in contents.items():
        dependencies: set[str] = set()
        for line in source.decode("utf-8").splitlines():
            match = IMPORT_RE.match(line)
            if match and match.group(1) in contents:
                dependencies.add(match.group(1))
        graph[name] = dependencies
    return graph


def local_graph() -> dict[str, set[str]]:
    sources = local_sources()
    return local_graph_from_contents(read_source_contents(sources))


def snapshot_sources(
    sources: dict[str, Path],
    contents: dict[str, bytes],
    selected: set[str],
) -> dict[str, tuple[Path, str]]:
    """Capture exact selected-source bytes used to construct a build plan."""
    return {
        name: (sources[name], hashlib.sha256(contents[name]).hexdigest())
        for name in sorted(selected)
    }


def changed_sources(snapshot: dict[str, tuple[Path, str]]) -> list[str]:
    changed: list[str] = []
    for name, (path, expected_digest) in snapshot.items():
        try:
            current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            changed.append(name)
            continue
        if current_digest != expected_digest:
            changed.append(name)
    return changed


def source_set_changes(
    expected: dict[str, Path], current: dict[str, Path],
) -> list[str]:
    changes = [f"+{name}" for name in sorted(current.keys() - expected.keys())]
    changes.extend(
        f"-{name}" for name in sorted(expected.keys() - current.keys())
    )
    changes.extend(
        name
        for name in sorted(expected.keys() & current.keys())
        if expected[name] != current[name]
    )
    return changes


def require_unchanged_sources(
    snapshot: dict[str, tuple[Path, str]],
    expected_sources: dict[str, Path],
    context: str,
) -> None:
    changed = [
        *source_set_changes(expected_sources, local_sources()),
        *changed_sources(snapshot),
    ]
    if changed:
        raise SourceChangedError(
            f"selected Lean source changed {context}: {', '.join(changed)}; "
            "restart the memory-safe plan"
        )


def requested_closure(graph: dict[str, set[str]], requested: list[str]) -> set[str]:
    if not requested:
        return set(graph)
    normalized = [
        item.removesuffix(".lean").replace("/", ".")
        for item in requested
    ]
    unknown = sorted(set(normalized) - set(graph))
    if unknown:
        raise ValueError(f"unknown local Lean module(s): {', '.join(unknown)}")
    closure: set[str] = set()

    def visit(name: str) -> None:
        if name in closure:
            return
        closure.add(name)
        for dependency in graph[name]:
            visit(dependency)

    for name in normalized:
        visit(name)
    return closure


def compact_closure(
    graph: dict[str, set[str]],
    contents: dict[str, bytes],
) -> tuple[set[str], int, int]:
    """Validate and describe the default data-independent import closure."""

    selected = requested_closure(graph, [COMPACT_ROOT_MODULE])
    forbidden = sorted(
        name
        for name in selected
        if name in COMPACT_FORBIDDEN_MODULES
        or any(name.startswith(prefix) for prefix in COMPACT_FORBIDDEN_PREFIXES)
        or any(
            component in {"Generated", "Production", "Tests"}
            for component in name.split(".")
        )
        or name.endswith(("Replay", "Trace"))
    )
    if forbidden:
        raise ValueError(
            "compact Lean closure reaches production/certificate modules: "
            + ", ".join(forbidden)
        )
    source_bytes = sum(len(contents[name]) for name in selected)
    source_lines = sum(
        len(contents[name].decode("utf-8").splitlines())
        for name in selected
    )
    if source_bytes > COMPACT_SOURCE_BYTES_MAX:
        raise ValueError(
            "compact Lean closure exceeds its source-byte budget "
            f"({source_bytes} > {COMPACT_SOURCE_BYTES_MAX})"
        )
    if source_lines > COMPACT_SOURCE_LINES_MAX:
        raise ValueError(
            "compact Lean closure exceeds its source-line budget "
            f"({source_lines} > {COMPACT_SOURCE_LINES_MAX})"
        )
    return selected, source_bytes, source_lines


def full_production_library_closure(
    graph: dict[str, set[str]],
) -> set[str]:
    """Select every module in the broad production-materialized library."""

    roots = sorted(name for name in graph if name.startswith("SparkInterval."))
    return requested_closure(graph, roots)


def production_materialization_in(
    selected: set[str],
) -> list[str]:
    """Return materialized production modules in one requested closure."""

    return sorted(
        name
        for name in selected
        if any(
            name.startswith(prefix)
            for prefix in PRODUCTION_MATERIALIZED_PREFIXES
        )
    )


def require_full_production_cloud_scope(
    environment: dict[str, str] | None = None,
) -> str:
    """Reject the materialized full build outside a measured Azure child.

    The reserved environment is an accidental-dispatch guard only.  It is not
    attestation evidence and does not authorize a theorem or receipt.
    """

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from tg_verifier.campaign_io import (  # pylint: disable=import-outside-toplevel
        require_azure_measured_worker_for_workload,
    )

    backend = require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
        environment=environment,
    )
    assert backend is not None
    return backend


def topological_order(graph: dict[str, set[str]], selected: set[str]) -> list[str]:
    order: list[str] = []
    active: set[str] = set()
    complete: set[str] = set()

    def visit(name: str) -> None:
        if name in complete:
            return
        if name in active:
            raise ValueError(f"local Lean import cycle involving {name}")
        active.add(name)
        for dependency in sorted(graph[name]):
            if dependency in selected:
                visit(dependency)
        active.remove(name)
        complete.add(name)
        order.append(name)

    for name in sorted(selected):
        visit(name)
    return order


def capped_command(*arguments: str) -> list[str]:
    return [str(MEMORY_RUNNER), *arguments]


def serial_lake_environment(
    plan_lock_fd: int, *, tasks_max: str | None = SAFE_LAKE_TASKS_MAX
) -> dict[str, str]:
    """Authorize one dependency-ordered Lake step inside the wrapper.

    The inherited descriptor is a capability tied to the planner that holds
    the complete-plan lock. An environment flag by itself is insufficient.
    """
    environment = os.environ.copy()
    environment["SPARKINTERVAL_SERIAL_LAKE_STEP"] = "1"
    environment["SPARKINTERVAL_PLAN_LOCK_FD"] = str(plan_lock_fd)
    # `-j1` in lakefile.toml constrains each Lean elaborator, but Lake is
    # itself a Lean program with a separate task pool.  This setting bounds
    # that pool.  Lake can still have several already-launched compiler
    # processes alive at once, so the safe Lake cgroup also receives bounded
    # process headroom below.
    environment["LEAN_NUM_THREADS"] = "1"
    if tasks_max is not None:
        # This changes only the cgroup task ceiling; Lean parallelism and the
        # aggregate memory limits stay fixed.  An explicit caller limit wins.
        environment.setdefault("SPARKINTERVAL_TASKS_MAX", tasks_max)
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "modules",
        nargs="*",
        help="optional local module names or paths; dependencies are included",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="print the dependency-ordered module plan without building",
    )
    parser.add_argument(
        "--full-production-library",
        action="store_true",
        help=(
            "explicitly build the broad SparkInterval library, including "
            "materialized production certificates; use the Azure "
            "qualification lane, not an ordinary local check"
        ),
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=sorted(EXECUTABLE_ROOTS),
        default=[],
        help=(
            "build an executable after serially building its local Lean "
            "dependency closure; may be repeated"
        ),
    )
    for option, facet in BLUEPRINT_FACETS.items():
        parser.add_argument(
            f"--{option}",
            action="store_true",
            help=(
                f"build the LeanArchitect {facet} facet for "
                f"{BLUEPRINT_MODULE} after its dependency closure"
            ),
        )
    args = parser.parse_args()

    requested_blueprint_facets = [
        facet
        for option, facet in BLUEPRINT_FACETS.items()
        if getattr(args, option.replace("-", "_"))
    ]
    if args.full_production_library and (
        args.modules or args.target or requested_blueprint_facets
    ):
        parser.error(
            "--full-production-library cannot be combined with modules, "
            "--target, or blueprint facets"
        )
    if args.full_production_library:
        try:
            require_full_production_cloud_scope()
        except ValueError as error:
            parser.error(str(error))
    default_compact = not (
        args.full_production_library
        or args.modules
        or args.target
        or requested_blueprint_facets
    )

    try:
        sources = local_sources()
        contents = read_source_contents(sources)
        graph = local_graph_from_contents(contents)
        requested_modules = (
            [COMPACT_ROOT_MODULE]
            if default_compact
            else [
                *args.modules,
                *(EXECUTABLE_ROOTS[target] for target in args.target),
                *([BLUEPRINT_MODULE] if requested_blueprint_facets else []),
            ]
        )
        if args.full_production_library:
            selected = full_production_library_closure(graph)
        elif default_compact:
            selected, _, _ = compact_closure(graph, contents)
        else:
            selected = requested_closure(graph, requested_modules)
        materialized = production_materialization_in(selected)
        if materialized and not args.full_production_library:
            require_full_production_cloud_scope()
        order = topological_order(graph, selected)
    except ValueError as error:
        parser.error(str(error))

    if args.plan:
        for name in order:
            print(name)
        return 0

    PLAN_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with PLAN_LOCK.open("a+b") as plan_lock:
        # Serialize complete plans as well as their individual cgroup steps.
        # This avoids several agents interleaving dependency closures and
        # spawning a queue of transient services that all wait on the step
        # lock. The lock is held by this small Python coordinator, outside the
        # transient services, so it is not the wrapper's non-reentrant lock.
        try:
            fcntl.flock(plan_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                "another memory-safe Lean plan is active; waiting for it "
                "to finish",
                flush=True,
            )
            fcntl.flock(plan_lock.fileno(), fcntl.LOCK_EX)

        # Re-read the graph after acquiring the lock. A caller may have spent
        # substantial time waiting for a previous plan, and its pre-lock graph
        # is not authoritative. Build the graph and digest snapshot from the
        # same captured source bytes.
        sources = local_sources()
        contents = read_source_contents(sources)
        graph = local_graph_from_contents(contents)
        try:
            if args.full_production_library:
                selected = full_production_library_closure(graph)
            elif default_compact:
                selected, _, _ = compact_closure(graph, contents)
            else:
                selected = requested_closure(graph, requested_modules)
            materialized = production_materialization_in(selected)
            if materialized and not args.full_production_library:
                require_full_production_cloud_scope()
            order = topological_order(graph, selected)
        except ValueError as error:
            parser.error(str(error))
        source_snapshot = snapshot_sources(sources, contents, selected)
        require_unchanged_sources(
            source_snapshot, sources, "while capturing the plan"
        )

        for index, name in enumerate(order, start=1):
            context = f"before step {index}/{len(order)} ({name})"
            require_unchanged_sources(source_snapshot, sources, context)
            print(f"safe Lean build [{index}/{len(order)}]: {name}", flush=True)
            subprocess.run(
                capped_command("lake", "build", f"+{name}"),
                cwd=PROJECT_ROOT,
                env=serial_lake_environment(plan_lock.fileno()),
                pass_fds=(plan_lock.fileno(),),
                check=True,
            )
            require_unchanged_sources(
                source_snapshot,
                sources,
                f"during step {index}/{len(order)} ({name})",
            )

        if args.target:
            targets = list(dict.fromkeys(args.target))
        elif args.full_production_library:
            targets = [FULL_LIBRARY_TARGET]
        elif default_compact:
            targets = [COMPACT_LIBRARY_TARGET]
        else:
            targets = []
        for target in targets:
            require_unchanged_sources(
                source_snapshot, sources, f"before executable target {target}"
            )
            print(f"safe Lean target: {target}", flush=True)
            subprocess.run(
                capped_command("lake", "build", target),
                cwd=PROJECT_ROOT,
                env=serial_lake_environment(plan_lock.fileno()),
                pass_fds=(plan_lock.fileno(),),
                check=True,
            )
            require_unchanged_sources(
                source_snapshot, sources, f"during executable target {target}"
            )

        for facet in requested_blueprint_facets:
            target = f"+{BLUEPRINT_MODULE}:{facet}"
            require_unchanged_sources(
                source_snapshot, sources, f"before blueprint facet {facet}"
            )
            print(f"safe Lean blueprint facet: {facet}", flush=True)
            subprocess.run(
                capped_command("lake", "build", target),
                cwd=PROJECT_ROOT,
                env=serial_lake_environment(
                    plan_lock.fileno(), tasks_max=BLUEPRINT_TASKS_MAX
                ),
                pass_fds=(plan_lock.fileno(),),
                check=True,
            )
            require_unchanged_sources(
                source_snapshot, sources, f"during blueprint facet {facet}"
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("memory-safe build interrupted", file=sys.stderr)
        raise SystemExit(130)
    except subprocess.CalledProcessError as error:
        print(
            f"memory-safe build step failed with exit status {error.returncode}",
            file=sys.stderr,
        )
        raise SystemExit(error.returncode)
    except SourceChangedError as error:
        print(f"memory-safe build aborted: {error}", file=sys.stderr)
        raise SystemExit(SOURCE_CHANGED_EXIT)
