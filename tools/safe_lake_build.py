#!/usr/bin/env python3
"""Build local Lean modules serially, with an aggregate memory cap per step."""

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
SOURCE_ROOT = PROJECT_ROOT / "SparkInterval"
MEMORY_RUNNER = PROJECT_ROOT / "tools" / "with_memory_limit.sh"
PLAN_LOCK = PROJECT_ROOT / ".lake" / "sparkinterval-safe-plan.lock"
SOURCE_CHANGED_EXIT = 66
IMPORT_RE = re.compile(r"^\s*(?:public\s+)?import\s+([A-Za-z_][A-Za-z0-9_'.]*)\s*(?:--.*)?$")
EXECUTABLE_ROOTS = {
    "sparkinterval-gen": "SparkInterval.GeneratePTX",
    "sparkinterval-check-certificate": "SparkInterval.Certificate.CLI",
}
BLUEPRINT_MODULE = "SparkInterval.Blueprint"
BLUEPRINT_TASKS_MAX = "64"
BLUEPRINT_FACETS = {
    "blueprint-json": "blueprintJson",
    "blueprint-tex": "blueprint",
}


class SourceChangedError(RuntimeError):
    """A selected Lean source changed after the serial plan was captured."""


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(PROJECT_ROOT).with_suffix("").parts)


def local_sources() -> dict[str, Path]:
    return {
        module_name(path): path
        for path in sorted(SOURCE_ROOT.rglob("*.lean"))
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
    plan_lock_fd: int, *, tasks_max: str | None = None
) -> dict[str, str]:
    """Authorize one dependency-ordered Lake step inside the wrapper.

    The inherited descriptor is a capability tied to the planner that holds
    the complete-plan lock. An environment flag by itself is insufficient.
    """
    environment = os.environ.copy()
    environment["SPARKINTERVAL_SERIAL_LAKE_STEP"] = "1"
    environment["SPARKINTERVAL_PLAN_LOCK_FD"] = str(plan_lock_fd)
    if tasks_max is not None:
        # LeanArchitect's metadata loader creates more runtime support threads
        # than ordinary `-j1` elaboration.  This changes only the cgroup task
        # ceiling; Lean parallelism and aggregate memory limits stay fixed.
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

    try:
        graph = local_graph()
        requested_modules = [
            *args.modules,
            *(EXECUTABLE_ROOTS[target] for target in args.target),
            *([BLUEPRINT_MODULE] if requested_blueprint_facets else []),
        ]
        selected = requested_closure(graph, requested_modules)
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
            selected = requested_closure(graph, requested_modules)
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
                env=serial_lake_environment(
                    plan_lock.fileno(),
                    tasks_max=(
                        BLUEPRINT_TASKS_MAX
                        if name == BLUEPRINT_MODULE
                        else None
                    ),
                ),
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
        elif not args.modules and not requested_blueprint_facets:
            targets = [
                "SparkInterval",
                "sparkinterval-gen",
                "sparkinterval-check-certificate",
            ]
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
