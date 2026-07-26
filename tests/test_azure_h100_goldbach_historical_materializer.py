# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from attestation.measured_run_archive import create_archive, extract_archive
from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_goldbach_historical_operational_workload_factory import (
    OWNER_ATOM_ID,
)
from tg_verifier.azure_h100_goldbach_historical_workload_factory import (
    CAMPAIGN_ID,
    GROUP_ID,
    PHASE_DEPENDENCIES,
    PHASE_ID,
    PORTFOLIO_ARGV,
    SHARD_COUNT,
    SOURCE_PATHS,
    expected_execution_projection_sha256,
    factory_for_portfolio_group,
    h100_expected_claim_identity,
    make_factory,
    source_reviewed_materializer_available,
)
from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_build_admission import load_build_admission
from tg_verifier.goldbach_gpu_campaign import (
    PRODUCTION_GROUPS,
    make_production_plan,
    production_group_leaf_indices,
)
from tg_verifier.goldbach_historical_terminal import (
    HistoricalGoldbachTerminalError,
    _validate_h100_receipt,
)
from tools import tg_goldbach_historical_h100_measured_workload as workload
from tools.tg_goldbach_historical_operational_azure_measured_workload import (
    HistoricalGoldbachOperationalWorkloadError,
    _validate_h100_result,
)


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = (
    ROOT
    / "schemas/azure-h100-goldbach-historical-materializer-site.schema.json"
)
MANIFEST_SCHEMA = (
    ROOT
    / "schemas/azure-h100-goldbach-historical-materialization.schema.json"
)
SITE_EXAMPLE = (
    ROOT
    / "examples/trusted-compute/"
    "azure_h100_goldbach_historical_materializer_site.redacted.json"
)
ADMISSION_FIXTURE = ROOT / "tests/fixtures/goldbach_build_admission.test.json"


def digest(tag: str) -> str:
    return hashlib.sha256(tag.encode("utf-8")).hexdigest()


def group() -> dict[str, object]:
    return {
        "backend_class": "h100_cuda",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PORTFOLIO_ARGV),
        "depends_on": list(PHASE_DEPENDENCIES),
        "group_id": GROUP_ID,
        "operator_adapter": "azure/h100_production_orchestrator.py",
        "owner_atom_id": OWNER_ATOM_ID,
        "phase_id": PHASE_ID,
        "receipt_backend": "azure_ncc40ads_h100_v5",
        "semantic_binding": None,
        "shard_count": SHARD_COUNT,
        "terminal": False,
    }


def signed_result(group_index: int, admission) -> dict:
    indices = list(range(group_index, 65_536, PRODUCTION_GROUPS))
    value = {
        "all_group_receipts_valid": True,
        "execution_attested": False,
        "group_index": group_index,
        "leaf_indices": indices,
        "lean_atom_discharged": False,
        "receipts": [
            {
                "leaf_index": index,
                "receipt_sha256": digest(f"leaf:{index}"),
                "status": "completed-new-receipt",
            }
            for index in indices
        ],
        "scheduler_group_count": PRODUCTION_GROUPS,
        "schema": "sparkinterval.goldbach-gpu-run-group.v1",
    }
    text = canonical_json_bytes(value).decode("utf-8")
    return {
        "backend": "azure_ncc40ads_h100_v5",
        "claim": {
            **h100_expected_claim_identity(group_index, admission),
            "artifacts": {
                "device_cubin_hash": admission.core["executable"]["sha256"],
                "host_executable_hash": admission.core["python"]["sha256"],
                "kernel_manifest_hash": expected_execution_projection_sha256(
                    group_index, admission
                ),
                "source_tree_hash": admission.expected_artifacts[
                    "source_tree_hash"
                ],
            },
            "output_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "result": text,
            "target": "nvidia_h100_sm90",
            "target_profile_hash": admission.deployment[
                "target_profile_sha256"
            ],
            "trust": "nvidia_h100_confidential_compute",
            "trust_profile_hash": admission.deployment[
                "trust_profile_sha256"
            ],
        },
        "receipt_sha256": digest(f"signed-group:{group_index}"),
    }


class HistoricalGoldbachH100Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.admission = load_build_admission(
            ADMISSION_FIXTURE, allow_test_fixture=True
        )

    def test_exact_factory_projection_and_portfolio_route(self) -> None:
        exact = group()
        self.assertFalse(source_reviewed_materializer_available(exact))
        self.assertTrue(
            source_reviewed_materializer_available(exact, self.admission)
        )
        projections = set()
        for index in (0, 1, SHARD_COUNT - 1):
            factory = factory_for_portfolio_group(
                exact, index, self.admission
            )
            self.assertIsNotNone(factory)
            assert factory is not None
            projection = expected_execution_projection_sha256(
                index, self.admission
            )
            projections.add(projection)
            self.assertIn(
                f"execution-projection-sha256={projection}",
                factory.algorithm_definition,
            )
            self.assertEqual(
                h100_expected_claim_identity(index, self.admission),
                {
                    "algorithm_hash": hashlib.sha256(
                        factory.algorithm_definition.encode("utf-8")
                    ).hexdigest(),
                    "algorithm_id": factory.algorithm_id,
                    "domain_hash": hashlib.sha256(
                        canonical_json_bytes(factory.domain)
                    ).hexdigest(),
                    "input_hash": hashlib.sha256(factory.input_bytes).hexdigest(),
                    "parameters_hash": hashlib.sha256(
                        canonical_json_bytes(factory.parameters)
                    ).hexdigest(),
                },
            )
        self.assertEqual(len(projections), 3)

        azure_portfolio._bind_group_operator_capability(exact)
        self.assertTrue(exact["production_operator_available"])
        self.assertEqual(
            exact["materializer_adapter"],
            "tools/tg_azure_h100_goldbach_historical_materializer.py",
        )
        changed = copy.deepcopy(group())
        changed["command_template"].append("--unsafe")
        azure_portfolio._bind_group_operator_capability(changed)
        self.assertFalse(changed["production_operator_available"])
        self.assertIsNone(changed["materializer_adapter"])

    def test_signed_child_requires_independently_derived_projection(self) -> None:
        group_index = 37
        receipt = signed_result(group_index, self.admission)
        checked = _validate_h100_result(
            receipt, group_index, self.admission
        )
        self.assertEqual(len(checked["receipt_sha256s"]), 8)
        terminal_identity = _validate_h100_receipt(
            receipt, group_index, self.admission
        )
        self.assertEqual(len(terminal_identity["payload_receipt_sha256s"]), 8)
        changed = copy.deepcopy(receipt)
        changed["claim"]["artifacts"]["kernel_manifest_hash"] = digest(
            "self-consistent-substitution"
        )
        with self.assertRaisesRegex(
            HistoricalGoldbachOperationalWorkloadError,
            "exact admitted build/job/profile",
        ):
            _validate_h100_result(changed, group_index, self.admission)
        with self.assertRaisesRegex(
            HistoricalGoldbachTerminalError, "exact admitted historical group"
        ):
            _validate_h100_receipt(changed, group_index, self.admission)

    def test_group_result_and_archive_require_exact_eight_leaves(self) -> None:
        plan = make_production_plan(
            executable_sha256=self.admission.core["executable"]["sha256"]
        )
        group_index = 37
        indices = production_group_leaf_indices(plan, group_index)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            retained = root / "retained"
            receipts = retained / "payload/binary-receipts"
            receipts.mkdir(parents=True)
            for index in indices:
                (receipts / f"receipt-{index:08d}.json").write_bytes(b"{}")

            def fake_load(path: Path, *, plan):
                del plan
                index = int(path.stem.split("-")[1])
                return {"receipt_sha256": digest(f"leaf:{index}")}

            with mock.patch.object(
                workload, "load_receipt", side_effect=fake_load
            ):
                result = workload._expected_group_result(
                    plan, receipts, group_index
                )
            self.assertEqual(result["leaf_indices"], list(indices))
            manifest = workload._write_export_manifest(
                retained, group_index
            )
            archive = root / "group.tar"
            create_archive(retained, archive)
            extract_archive(archive, root / "expanded")
            self.assertEqual(
                workload._validate_export(root / "expanded", group_index),
                manifest,
            )
            (receipts / "receipt-99999999.json").write_bytes(b"{}")
            with mock.patch.object(
                workload, "load_receipt", side_effect=fake_load
            ):
                with self.assertRaisesRegex(
                    workload.HistoricalGoldbachH100MeasuredWorkloadError,
                    "exactly its eight",
                ):
                    workload._expected_group_result(
                        plan, receipts, group_index
                    )

    def test_schemas_cli_and_deterministic_archive_path(self) -> None:
        for path in (SITE_SCHEMA, MANIFEST_SCHEMA):
            schema = json.loads(path.read_bytes())
            if jsonschema is not None:
                jsonschema.Draft202012Validator.check_schema(schema)
        if jsonschema is not None:
            jsonschema.validate(
                json.loads(SITE_EXAMPLE.read_bytes()),
                json.loads(SITE_SCHEMA.read_bytes()),
            )
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    ROOT
                    / "tools/tg_azure_h100_goldbach_historical_materializer.py"
                ),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        factory = make_factory(123, self.admission)
        work = factory.command_argv[
            factory.command_argv.index("--work") + 1
        ]
        self.assertEqual(work, "work/goldbach-historical-h100-00000123")

    def test_packaged_python_closure_imports_in_isolated_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in SOURCE_PATHS:
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            for relative in (
                "tools/tg_goldbach_historical_h100_measured_workload.py",
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
