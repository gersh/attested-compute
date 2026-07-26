#!/usr/bin/env python3

# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import fcntl
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SAFE_LAKE_BUILD = ROOT / "tools" / "safe_lake_build.py"
MEMORY_RUNNER = ROOT / "tools" / "with_memory_limit.sh"
SAFE_LEAN = ROOT / "tools" / "safe_lean.sh"
AXIOM_AUDIT = ROOT / "tools" / "audit_axioms.sh"
PLAN_LOCK = ROOT / ".lake" / "sparkinterval-safe-plan.lock"

SAFE_BUILD_SPEC = importlib.util.spec_from_file_location(
    "sparkinterval_safe_lake_build", SAFE_LAKE_BUILD
)
assert SAFE_BUILD_SPEC is not None
assert SAFE_BUILD_SPEC.loader is not None
safe_build = importlib.util.module_from_spec(SAFE_BUILD_SPEC)
SAFE_BUILD_SPEC.loader.exec_module(safe_build)


class MemorySafeBuildTest(unittest.TestCase):
    def test_default_plan_is_compact_and_excludes_production_materialization(
        self,
    ) -> None:
        completed = subprocess.run(
            [str(SAFE_LAKE_BUILD), "--plan"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        modules = completed.stdout.splitlines()
        self.assertEqual(modules[-1], safe_build.COMPACT_ROOT_MODULE)
        self.assertEqual(len(modules), 123)
        for forbidden in (
            "SparkInterval.Execution.RegisteredAlgorithm",
            "SparkInterval.Execution.RunCertificate",
            "SparkInterval.Generated.CDEMAbelProduction",
            "SparkInterval.Generated.PlattHeadQ128",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, modules)

    def test_compact_closure_guard_rejects_generated_or_registered_import(
        self,
    ) -> None:
        sources = safe_build.local_sources()
        contents = safe_build.read_source_contents(sources)
        original = safe_build.local_graph_from_contents(contents)
        for injected in (
            "SparkInterval.Execution.RegisteredAlgorithm",
            "SparkInterval.Generated.PlattHeadQ128",
        ):
            with self.subTest(injected=injected):
                graph = {
                    name: set(dependencies)
                    for name, dependencies in original.items()
                }
                graph[safe_build.COMPACT_ROOT_MODULE].add(injected)
                with self.assertRaisesRegex(
                    ValueError, "compact Lean closure reaches production"
                ):
                    safe_build.compact_closure(graph, contents)

    def test_full_production_library_requires_explicit_option(self) -> None:
        sources = safe_build.local_sources()
        contents = safe_build.read_source_contents(sources)
        graph = safe_build.local_graph_from_contents(contents)
        modules = safe_build.full_production_library_closure(graph)
        self.assertIn(
            "SparkInterval.Generated.CDEMAbelProduction", modules
        )
        self.assertIn("SparkInterval.Generated.PlattHeadQ128", modules)
        self.assertIn("SparkInterval.Execution.RegisteredAlgorithm", modules)

    def test_full_production_library_refuses_local_scope_before_planning(
        self,
    ) -> None:
        clean_environment = dict(os.environ)
        for key in (
            "SPARKINTERVAL_MEASURED_WORKER_SCOPE",
            "SPARKINTERVAL_MEASURED_WORKER_BACKEND",
            "SPARKINTERVAL_MEASURED_WORKER_CHALLENGE_NONCE",
            "SPARKINTERVAL_MEASURED_WORKER_JOB_BINDING_SHA256",
        ):
            clean_environment.pop(key, None)
        with (
            mock.patch.object(
                sys,
                "argv",
                [str(SAFE_LAKE_BUILD), "--full-production-library", "--plan"],
            ),
            mock.patch.dict(os.environ, clean_environment, clear=True),
            mock.patch.object(
                safe_build,
                "local_sources",
                side_effect=AssertionError("source planning was reached"),
            ),
            mock.patch("sys.stderr", new=io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            safe_build.main()
        self.assertEqual(raised.exception.code, 2)

    def test_full_production_library_plan_is_not_the_default(self) -> None:
        completed = subprocess.run(
            [
                str(SAFE_LAKE_BUILD),
                "--plan",
                "--full-production-library",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("cloud-only", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_explicit_aggregate_import_cannot_materialize_locally(self) -> None:
        environment = dict(os.environ)
        for key in (
            "SPARKINTERVAL_MEASURED_WORKER_SCOPE",
            "SPARKINTERVAL_MEASURED_WORKER_BACKEND",
            "SPARKINTERVAL_MEASURED_WORKER_CHALLENGE_NONCE",
            "SPARKINTERVAL_MEASURED_WORKER_JOB_BINDING_SHA256",
        ):
            environment.pop(key, None)
        completed = subprocess.run(
            [str(SAFE_LAKE_BUILD), "--plan", "SparkInterval.Execution"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("cloud-only", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_full_axiom_audit_refuses_local_scope_before_source_work(
        self,
    ) -> None:
        environment = dict(os.environ)
        for key in (
            "SPARKINTERVAL_MEASURED_WORKER_SCOPE",
            "SPARKINTERVAL_MEASURED_WORKER_BACKEND",
            "SPARKINTERVAL_MEASURED_WORKER_CHALLENGE_NONCE",
            "SPARKINTERVAL_MEASURED_WORKER_JOB_BINDING_SHA256",
        ):
            environment.pop(key, None)
        completed = subprocess.run(
            [str(AXIOM_AUDIT)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("cloud-only", completed.stderr)
        self.assertNotIn("safe Lean build", completed.stdout)

    def test_local_graph_tracks_contract_and_compact_roots(self) -> None:
        sources = safe_build.local_sources()
        self.assertIn("TGComputeContracts.Sqrt218.Sound", sources)
        self.assertIn(safe_build.COMPACT_ROOT_MODULE, sources)

    def test_planner_orders_each_local_dependency_once(self) -> None:
        completed = subprocess.run(
            [
                str(SAFE_LAKE_BUILD),
                "--plan",
                "SparkInterval.PTX.CompilerEpilogueRefinement",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        modules = completed.stdout.splitlines()
        self.assertEqual(len(modules), len(set(modules)))
        self.assertEqual(
            modules[-1], "SparkInterval.PTX.CompilerEpilogueRefinement"
        )
        self.assertLess(
            modules.index("SparkInterval.PTX.CompilerOutputRefinement"),
            modules.index("SparkInterval.PTX.CompilerEpilogueRefinement"),
        )

    def test_planner_rejects_unknown_module_before_building(self) -> None:
        completed = subprocess.run(
            [str(SAFE_LAKE_BUILD), "--plan", "SparkInterval.DoesNotExist"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("unknown local Lean module", completed.stderr)

    def test_blueprint_facet_is_explicitly_production_materialized(self) -> None:
        sources = safe_build.local_sources()
        contents = safe_build.read_source_contents(sources)
        graph = safe_build.local_graph_from_contents(contents)
        modules = safe_build.requested_closure(
            graph, [safe_build.BLUEPRINT_MODULE]
        )
        self.assertIn("SparkInterval.PTX.GeneratedKernelRunRefinement", modules)
        self.assertIn("SparkInterval.Execution.Trusted.RunCertificate", modules)
        self.assertIn("SparkInterval.Generated.PlattHeadQ128", modules)

        completed = subprocess.run(
            [str(SAFE_LAKE_BUILD), "--plan", "--blueprint-json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("cloud-only", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_second_planner_waits_before_starting_a_build(self) -> None:
        PLAN_LOCK.parent.mkdir(parents=True, exist_ok=True)
        with PLAN_LOCK.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            process = subprocess.Popen(
                [str(SAFE_LAKE_BUILD), "SparkInterval.Basic"],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate(timeout=5)
            else:
                stdout, stderr = process.communicate()
                self.fail(
                    "second planner exited instead of waiting for the plan "
                    f"lock (stdout={stdout!r}, stderr={stderr!r})"
                )
        self.assertIn("another memory-safe Lean plan is active", stdout)

    def test_memory_runner_rejects_direct_lake_build(self) -> None:
        environment = os.environ.copy()
        environment.pop("SPARKINTERVAL_SERIAL_LAKE_STEP", None)
        environment.pop("SPARKINTERVAL_PLAN_LOCK_FD", None)
        environment.pop("SPARKINTERVAL_MEMORY_WRAPPER_ACTIVE", None)
        completed = subprocess.run(
            [str(MEMORY_RUNNER), "lake", "build", "+SparkInterval.Basic"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("build-producing commands can schedule", completed.stderr)
        self.assertIn("safe_lake_build.py", completed.stderr)

    def test_memory_runner_rejects_option_prefixed_lake_build(self) -> None:
        environment = os.environ.copy()
        environment.pop("SPARKINTERVAL_SERIAL_LAKE_STEP", None)
        environment.pop("SPARKINTERVAL_PLAN_LOCK_FD", None)
        environment.pop("SPARKINTERVAL_MEMORY_WRAPPER_ACTIVE", None)
        completed = subprocess.run(
            [
                str(MEMORY_RUNNER),
                "lake",
                "--quiet",
                "build",
                "+SparkInterval.Basic",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("build-producing commands can schedule", completed.stderr)

    def test_memory_runner_rejects_direct_lake_query(self) -> None:
        environment = os.environ.copy()
        environment.pop("SPARKINTERVAL_SERIAL_LAKE_STEP", None)
        environment.pop("SPARKINTERVAL_PLAN_LOCK_FD", None)
        environment.pop("SPARKINTERVAL_MEMORY_WRAPPER_ACTIVE", None)
        completed = subprocess.run(
            [str(MEMORY_RUNNER), "lake", "query", "+SparkInterval.Basic"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("build-producing commands can schedule", completed.stderr)

    def test_memory_runner_rejects_forged_serial_step_environment(self) -> None:
        environment = os.environ.copy()
        environment["SPARKINTERVAL_SERIAL_LAKE_STEP"] = "1"
        environment["SPARKINTERVAL_PLAN_LOCK_FD"] = "999999"
        environment.pop("SPARKINTERVAL_MEMORY_WRAPPER_ACTIVE", None)
        completed = subprocess.run(
            [str(MEMORY_RUNNER), "lake", "build", "+SparkInterval.Basic"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("inherited complete-plan lock", completed.stderr)

    def test_safe_lean_rejects_resource_option_overrides(self) -> None:
        for option in ("-j8", "-M16384"):
            with self.subTest(option=option):
                completed = subprocess.run(
                    [str(SAFE_LEAN), option, "Scratch.lean"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertIn("owns Lean's -j and -M", completed.stderr)

    def test_selected_source_snapshot_detects_content_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "A.lean"
            source.write_text("def value := 1\n", encoding="utf-8")
            sources = {"SparkInterval.A": source}
            contents = safe_build.read_source_contents(sources)
            snapshot = safe_build.snapshot_sources(
                sources, contents, set(sources)
            )
            self.assertEqual(safe_build.changed_sources(snapshot), [])
            source.write_text("def value := 2\n", encoding="utf-8")
            self.assertEqual(
                safe_build.changed_sources(snapshot), ["SparkInterval.A"]
            )

    def test_source_set_snapshot_detects_added_and_removed_modules(self) -> None:
        expected = {
            "SparkInterval.A": Path("SparkInterval/A.lean"),
            "SparkInterval.B": Path("SparkInterval/B.lean"),
        }
        current = {
            "SparkInterval.B": Path("SparkInterval/B.lean"),
            "SparkInterval.C": Path("SparkInterval/C.lean"),
        }
        self.assertEqual(
            safe_build.source_set_changes(expected, current),
            ["+SparkInterval.C", "-SparkInterval.A"],
        )

    def test_require_unchanged_sources_raises_on_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "A.lean"
            source.write_text("def value := 1\n", encoding="utf-8")
            sources = {"SparkInterval.A": source}
            snapshot = safe_build.snapshot_sources(
                sources,
                safe_build.read_source_contents(sources),
                set(sources),
            )
            with mock.patch.object(
                safe_build, "local_sources", return_value=sources
            ):
                safe_build.require_unchanged_sources(
                    snapshot, sources, "before test step"
                )
                source.write_text("def value := 2\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    safe_build.SourceChangedError,
                    r"before test step: SparkInterval\.A; restart",
                ):
                    safe_build.require_unchanged_sources(
                        snapshot, sources, "before test step"
                    )

    def test_require_unchanged_sources_raises_on_module_set_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_a = Path(directory) / "A.lean"
            source_b = Path(directory) / "B.lean"
            source_a.write_text("def a := 1\n", encoding="utf-8")
            source_b.write_text("def b := 2\n", encoding="utf-8")
            expected = {"SparkInterval.A": source_a}
            current = {**expected, "SparkInterval.B": source_b}
            snapshot = safe_build.snapshot_sources(
                expected,
                safe_build.read_source_contents(expected),
                set(expected),
            )
            with mock.patch.object(
                safe_build, "local_sources", return_value=current
            ):
                with self.assertRaisesRegex(
                    safe_build.SourceChangedError,
                    r"while testing module set: \+SparkInterval\.B; restart",
                ):
                    safe_build.require_unchanged_sources(
                        snapshot, expected, "while testing module set"
                    )

    def test_source_changed_exit_status_is_stable(self) -> None:
        self.assertEqual(safe_build.SOURCE_CHANGED_EXIT, 66)

    def test_blueprint_step_has_bounded_runtime_thread_headroom(self) -> None:
        environment = safe_build.serial_lake_environment(
            123, tasks_max=safe_build.BLUEPRINT_TASKS_MAX
        )
        self.assertEqual(environment["SPARKINTERVAL_TASKS_MAX"], "64")
        self.assertEqual(environment["SPARKINTERVAL_SERIAL_LAKE_STEP"], "1")
        self.assertEqual(environment["LEAN_NUM_THREADS"], "1")

    def test_ordinary_lake_step_has_bounded_process_headroom(self) -> None:
        environment = safe_build.serial_lake_environment(123)
        self.assertEqual(environment["SPARKINTERVAL_TASKS_MAX"], "64")

    def test_lake_runtime_task_pool_is_forced_to_one(self) -> None:
        with mock.patch.dict(
            os.environ, {"LEAN_NUM_THREADS": "96"}, clear=False
        ):
            environment = safe_build.serial_lake_environment(123)
        self.assertEqual(environment["LEAN_NUM_THREADS"], "1")

    def test_explicit_task_limit_overrides_blueprint_default(self) -> None:
        with mock.patch.dict(
            os.environ, {"SPARKINTERVAL_TASKS_MAX": "96"}, clear=False
        ):
            environment = safe_build.serial_lake_environment(
                123, tasks_max=safe_build.BLUEPRINT_TASKS_MAX
            )
        self.assertEqual(environment["SPARKINTERVAL_TASKS_MAX"], "96")

    def test_memory_runner_rejects_nested_wrapper_before_execution(self) -> None:
        environment = os.environ.copy()
        environment["SPARKINTERVAL_MEMORY_WRAPPER_ACTIVE"] = "test-parent"
        marker = ROOT / ".lake" / "nested-wrapper-test-marker"
        marker.unlink(missing_ok=True)
        self.addCleanup(marker.unlink, missing_ok=True)
        completed = subprocess.run(
            [str(MEMORY_RUNNER), "touch", str(marker)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 75)
        self.assertIn("nested memory wrappers", completed.stderr)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
