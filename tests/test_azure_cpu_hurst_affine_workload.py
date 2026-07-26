# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest

from attestation.measured_run_archive import create_archive
from tests.azure_measured_worker_test_scope import measured_worker_test_scope
from tg_verifier import azure_cpu_hurst_materializer as materializer
from tg_verifier.azure_cpu_hurst_affine_workload_factory import (
    CAMPAIGN_ID,
    PHASE_COMMANDS,
    PHASE_COUNTS,
    PHASE_DEPENDENCIES,
    factory_for_portfolio_group,
    make_factory,
    source_reviewed_materializer_available,
)
from tg_verifier.campaign_io import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]


def load_workload_module():
    specification = importlib.util.spec_from_file_location(
        "gpu_prover_hurst_affine_azure_measured_workload",
        ROOT / "tools/tg_hurst_affine_azure_measured_workload.py",
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


workload = load_workload_module()


def write_bytes(path: Path, raw: bytes, mode: int = 0o400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def group(phase: str, *, index: int = 0) -> dict[str, object]:
    factory = make_factory(phase, index)
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PHASE_COMMANDS[phase]),
        "depends_on": list(PHASE_DEPENDENCIES[phase]),
        "group_id": factory.group_id,
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": "mertens-hurst",
        "phase_id": phase,
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": None,
        "shard_count": PHASE_COUNTS[phase],
        "terminal": False,
    }


class AzureCPUHurstAffineWorkloadTests(unittest.TestCase):
    def test_factory_is_closed_operational_only_and_materializer_selects_it(self) -> None:
        expected = {
            "initialize-affine": (),
            "affine-shards": ((f"{CAMPAIGN_ID}::initialize-affine", 0),),
            "finalize-affine-certificate": tuple(
                (f"{CAMPAIGN_ID}::affine-shards", index)
                for index in range(320)
            ),
            "replay-affine-certificate": (
                (f"{CAMPAIGN_ID}::finalize-affine-certificate", 0),
            ),
        }
        for phase, count in PHASE_COUNTS.items():
            exact = group(phase)
            self.assertTrue(source_reviewed_materializer_available(exact))
            for index in range(count):
                factory = factory_for_portfolio_group(exact, index)
                self.assertIsNotNone(factory)
                assert factory is not None
                self.assertFalse(factory.terminal)
                self.assertIsNone(factory.registered_invocation)
                self.assertIn(
                    "not-row-realization-not-attestation-not-lean-atom",
                    factory.algorithm_definition,
                )
                self.assertEqual(
                    materializer._factory_for_portfolio_group(exact, index),
                    factory,
                )
            self.assertEqual(
                materializer._expected_predecessors(make_factory(phase, 0)),
                expected[phase],
            )
        changed = group("replay-affine-certificate")
        changed["semantic_binding"] = {"registered_invocation": "attacker"}
        self.assertFalse(source_reviewed_materializer_available(changed))

    def test_built_runner_self_check_includes_exact_affine_mode(self) -> None:
        runner = (
            ROOT
            / "build/tg-production-kat/"
            "sparkinterval-tg-hurst-residual-shard"
        )
        if not runner.is_file():
            self.skipTest("bounded Hurst runner is not built")
        result = materializer._runner_self_check(runner)
        self.assertEqual(
            set(result),
            {
                "affine_stdout_sha256",
                "lower",
                "row_sha256",
                "summary_stdout_sha256",
                "upper_inclusive",
                "verify_stdout_sha256",
            },
        )
        for field in (
            "affine_stdout_sha256",
            "row_sha256",
            "summary_stdout_sha256",
            "verify_stdout_sha256",
        ):
            self.assertEqual(len(result[field]), 64)

    def test_measured_initialize_and_trace_replay_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = write_bytes(
                root / "artifacts/runner",
                b"#!/bin/sh\nexit 2\n",
                stat.S_IRUSR | stat.S_IXUSR,
            )
            source = write_bytes(
                root / "source/reference/tg_hurst_residual_shard.cpp",
                (ROOT / "reference/tg_hurst_residual_shard.cpp").read_bytes(),
            )
            upstream = write_bytes(
                root / "source/specifications/HURST_MERTENS_UPSTREAM.json",
                (
                    ROOT / "specifications/HURST_MERTENS_UPSTREAM.json"
                ).read_bytes(),
            )
            factory = make_factory("initialize-affine", 0)
            invocation = write_bytes(
                root / "input/phase.json", factory.input_bytes
            )
            handoff_root = root / "handoff-root"
            write_bytes(
                handoff_root / "handoff.json",
                canonical_json_bytes(
                    {
                        "entries": [],
                        "group_index": 0,
                        "kind": (
                            "sparkinterval.azure.hurst-phase-handoff.v1"
                        ),
                        "phase": "initialize-affine",
                        "schema_version": 1,
                    }
                ),
            )
            handoff = root / "input/handoff.tar"
            create_archive(handoff_root, handoff)
            old = Path.cwd()
            os.chdir(root)
            try:
                arguments = SimpleNamespace(
                    algorithm_id=factory.algorithm_id,
                    challenge="aa" * 32,
                    group_index=0,
                    handoff=handoff.relative_to(root),
                    input=invocation.relative_to(root),
                    job_binding="bb" * 32,
                    output=Path("output/result.json"),
                    phase="initialize-affine",
                    runner=runner.relative_to(root),
                    runner_source=source.relative_to(root),
                    trace=Path("output/trace.json"),
                    upstream_manifest=upstream.relative_to(root),
                    work=Path("work/hurst-affine"),
                )
                with measured_worker_test_scope(arguments):
                    workload.run(arguments)
                    workload.verify_trace(arguments)
                value = json.loads(arguments.output.read_bytes())
                self.assertEqual(value["kind"], workload.OPERATIONAL_RESULT_KIND)
                self.assertEqual(value["phase"], "initialize-affine")
                self.assertTrue(
                    Path("work/hurst-affine/retained-export.tar").is_file()
                )
                source.chmod(0o600)
                source.write_bytes(source.read_bytes() + b"// changed\n")
                with self.assertRaises(workload.HurstMeasuredWorkloadError):
                    with measured_worker_test_scope(arguments):
                        workload.verify_trace(arguments)
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
