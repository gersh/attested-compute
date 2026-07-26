# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from attestation.measured_run_archive import create_archive, extract_archive
from tg_verifier.azure_h100_goldbach_10pow27_workload_factory import (
    CAMPAIGN_ID,
    GROUP_ID,
    PHASE_DEPENDENCIES,
    PHASE_ID,
    PORTFOLIO_ARGV,
    SHARD_COUNT,
    SOURCE_PATHS,
    factory_for_portfolio_group,
    h100_expected_claim_identity,
    make_factory,
    source_reviewed_materializer_available,
)
from tg_verifier.goldbach_gpu_campaign import (
    make_analytic_10pow27_production_plan,
    production_group_leaf_indices,
)
from tg_verifier.goldbach_build_admission import load_build_admission
from tools import tg_goldbach_10pow27_h100_measured_workload as workload
from tools.tg_goldbach_10pow27_azure_measured_workload import (
    h100_expected_claim_identity as consumer_identity,
)


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = ROOT / "schemas/azure-h100-goldbach10pow27-materializer-site.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas/azure-h100-goldbach10pow27-materialization.schema.json"
SITE_EXAMPLE = (
    ROOT
    / "examples/trusted-compute/azure_h100_goldbach10pow27_materializer_site.redacted.json"
)
ADMISSION_FIXTURE = ROOT / "tests/fixtures/goldbach_build_admission.test.json"


def group() -> dict[str, object]:
    return {
        "backend_class": "h100_cuda",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PORTFOLIO_ARGV),
        "depends_on": list(PHASE_DEPENDENCIES),
        "group_id": GROUP_ID,
        "operator_adapter": "azure/h100_production_orchestrator.py",
        "owner_atom_id": "goldbach-finite-below-10pow27",
        "phase_id": PHASE_ID,
        "receipt_backend": "azure_ncc40ads_h100_v5",
        "semantic_binding": None,
        "shard_count": SHARD_COUNT,
        "terminal": False,
    }


class Goldbach10Pow27H100FactoryTests(unittest.TestCase):
    def test_exact_8192_group_factory_and_consumer_identity(self) -> None:
        exact = group()
        admission = load_build_admission(
            ADMISSION_FIXTURE, allow_test_fixture=True
        )
        self.assertFalse(source_reviewed_materializer_available(exact))
        self.assertTrue(source_reviewed_materializer_available(exact, admission))
        for index in (0, 1, SHARD_COUNT - 1):
            factory = factory_for_portfolio_group(exact, index, admission)
            self.assertIsNotNone(factory)
            assert factory is not None
            self.assertIsNone(factory.registered_invocation)
            self.assertEqual(factory.shard_count, SHARD_COUNT)
            self.assertEqual(
                h100_expected_claim_identity(index, admission),
                consumer_identity(index, admission),
            )
            self.assertEqual(factory.command_argv[:2], ("artifacts/python3", "-I"))
            self.assertIn(f"{index:08d}", factory.command_argv[factory.command_argv.index("--work") + 1])
        changed = dict(exact)
        changed["command_template"] = [*PORTFOLIO_ARGV, "--unsafe"]
        self.assertFalse(
            source_reviewed_materializer_available(changed, admission)
        )

    def test_group_result_and_retained_export_require_exact_eight_leaves(self) -> None:
        plan = make_analytic_10pow27_production_plan(executable_sha256="11" * 32)
        group_index = 37
        indices = production_group_leaf_indices(plan, group_index)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipts = root / "retained/payload/binary-receipts"
            receipts.mkdir(parents=True)
            for index in indices:
                (receipts / f"receipt-{index:08d}.json").write_bytes(b"{}")

            def fake_load(path: Path, *, plan):
                del plan
                index = int(path.stem.split("-")[1])
                return {"receipt_sha256": f"{index:064x}"[-64:]}

            with mock.patch.object(workload, "load_receipt", side_effect=fake_load):
                result = workload._expected_group_result(plan, receipts, group_index)
            self.assertEqual(result["leaf_indices"], list(indices))
            self.assertEqual(len(result["receipts"]), 8)
            manifest = workload._write_export_manifest(root / "retained", group_index)
            archive = root / "group.tar"
            create_archive(root / "retained", archive)
            extract_archive(archive, root / "expanded")
            self.assertEqual(
                workload._validate_export(root / "expanded", group_index), manifest
            )
            (receipts / "receipt-99999999.json").write_bytes(b"{}")
            with mock.patch.object(workload, "load_receipt", side_effect=fake_load):
                with self.assertRaisesRegex(
                    workload.H100GoldbachMeasuredWorkloadError, "exactly its eight"
                ):
                    workload._expected_group_result(plan, receipts, group_index)

    def test_schemas_cli_and_deterministic_paths_are_current(self) -> None:
        for path in (SITE_SCHEMA, MANIFEST_SCHEMA):
            schema = json.loads(path.read_bytes())
            if jsonschema is not None:
                jsonschema.Draft202012Validator.check_schema(schema)
        if jsonschema is not None:
            jsonschema.validate(
                json.loads(SITE_EXAMPLE.read_bytes()),
                json.loads(SITE_SCHEMA.read_bytes()),
            )
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/tg_azure_h100_goldbach_10pow27_materializer.py"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("export", result.stdout)
        admission = load_build_admission(
            ADMISSION_FIXTURE, allow_test_fixture=True
        )
        factory = make_factory(123, admission)
        archive = factory.command_argv[factory.command_argv.index("--work") + 1]
        self.assertEqual(archive, "work/goldbach10pow27-h100-00000123")

    def test_packaged_python_closure_imports_in_isolated_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in SOURCE_PATHS:
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            for relative in (
                "tools/tg_goldbach_10pow27_h100_measured_workload.py",
                "tools/tg_goldbach_gpu_campaign.py",
                "attestation/azure_h100_pre_run_gate.py",
            ):
                completed = subprocess.run(
                    [sys.executable, "-I", str(package / relative), "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
