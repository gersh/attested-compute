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
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from attestation.measured_run_archive import create_archive
from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_goldbach_historical_operational_materializer import (
    _expected_predecessors,
)
from tg_verifier.azure_cpu_goldbach_historical_operational_workload_factory import (
    CAMPAIGN_ID,
    OPERATIONAL_RESULT_KIND,
    OWNER_ATOM_ID,
    PHASE_COMMANDS,
    PHASE_COUNTS,
    PHASE_DEPENDENCIES,
    SOURCE_PATHS,
    expected_claim_identity,
    factory_for_portfolio_group,
    make_factory,
    source_reviewed_materializer_available,
)
from tg_verifier.campaign_io import canonical_json_bytes, hash_file_once
from tg_verifier.goldbach_campaign import (
    CampaignParameters,
    independent_group_bounds,
)
from tg_verifier.goldbach_historical_terminal import (
    LADDER_PHASE,
    NOT_APPLICABLE_DIGEST,
    HistoricalGoldbachTerminalError,
    _validate_ladder_receipt,
)
from tg_verifier.goldbach_native_ladder import (
    NATIVE_GROUP_KIND,
    NATIVE_SCHEMA,
)
from tg_verifier.h100_cluster import WORKLOADS
from tools.tg_goldbach_historical_operational_azure_measured_workload import (
    HistoricalGoldbachOperationalWorkloadError,
    _validate_cpu_result,
    _write_export_manifest,
)
from tools import generate_goldbach_historical_terminal_registration as registration


ROOT = Path(__file__).resolve().parents[1]
SITE_SCHEMA = (
    ROOT
    / "schemas/azure-cpu-goldbach-historical-operational-materializer-site.schema.json"
)
MANIFEST_SCHEMA = (
    ROOT
    / "schemas/azure-cpu-goldbach-historical-operational-materialization.schema.json"
)
SITE_EXAMPLE = (
    ROOT
    / "examples/trusted-compute/"
    "azure_cpu_goldbach_historical_operational_materializer_site.redacted.json"
)


def digest(tag: str) -> str:
    return hashlib.sha256(tag.encode("utf-8")).hexdigest()


def group(phase: str) -> dict[str, object]:
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PHASE_COMMANDS[phase]),
        "depends_on": list(PHASE_DEPENDENCIES[phase]),
        "group_id": f"{CAMPAIGN_ID}::{phase}",
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": OWNER_ATOM_ID,
        "phase_id": phase,
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": None,
        "shard_count": PHASE_COUNTS[phase],
        "terminal": False,
    }


def native_result(index: int) -> dict[str, object]:
    lower, upper = independent_group_bounds(
        CampaignParameters().range_count, index, 320
    )
    return {
        "classification": "full_source",
        "first_range_index": lower,
        "group_count": 320,
        "group_index": index,
        "kind": NATIVE_GROUP_KIND,
        "last_range_index": upper - 1,
        "local_workers": 40,
        "native_receipt_sha256s": [
            digest(f"native:{value}") for value in range(lower, upper)
        ],
        "range_count": upper - lower,
        "range_receipt_sha256s": [
            digest(f"ordinary:{value}") for value in range(lower, upper)
        ],
        "schema": NATIVE_SCHEMA,
    }


def operational_receipt(index: int, result: dict[str, object]) -> dict:
    text = canonical_json_bytes(result).decode("utf-8")
    return {
        "backend": "azure_sevsnp_cpu",
        "claim": {
            **expected_claim_identity(LADDER_PHASE, index),
            "artifacts": {
                "device_cubin_hash": NOT_APPLICABLE_DIGEST,
                "host_executable_hash": digest("python"),
                "kernel_manifest_hash": digest("job"),
                "source_tree_hash": digest("source"),
            },
            "input_hash": digest("handoff"),
            "output_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "result": text,
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        },
        "receipt_sha256": digest("signed-receipt"),
    }


class HistoricalGoldbachOperationalTests(unittest.TestCase):
    def test_all_six_phase_types_match_the_portfolio_dag(self) -> None:
        workload = next(
            row for row in WORKLOADS if row.campaign_id == CAMPAIGN_ID
        )
        by_phase = {row.phase_id: row for row in workload.phase_dag}
        self.assertEqual(len(PHASE_COUNTS), 6)
        for phase, count in PHASE_COUNTS.items():
            with self.subTest(phase=phase):
                exact = group(phase)
                self.assertEqual(by_phase[phase].command, PHASE_COMMANDS[phase])
                self.assertTrue(source_reviewed_materializer_available(exact))
                for index in {0, count - 1}:
                    factory = factory_for_portfolio_group(exact, index)
                    self.assertIsNotNone(factory)
                    assert factory is not None
                    self.assertFalse(factory.terminal)
                    self.assertIsNone(factory.registered_invocation)
                changed = copy.deepcopy(exact)
                changed["command_template"].append("--unsafe")
                self.assertFalse(
                    source_reviewed_materializer_available(changed)
                )

    def test_predecessor_cardinalities_are_closed(self) -> None:
        counts = {
            "create-production-plan": 0,
            "initialize-prime-ladder": 0,
            "native-prime-ladder-range-groups": 1,
            "aggregate": 8193,
            "binary-semantic-replay": 1,
            "reduce-prime-ladder-ranges": 320,
        }
        for phase, expected in counts.items():
            self.assertEqual(
                len(_expected_predecessors(make_factory(phase, 0))),
                expected,
            )

    def test_portfolio_routes_every_operational_cpu_phase(self) -> None:
        for phase in PHASE_COUNTS:
            exact = group(phase)
            azure_portfolio._bind_group_operator_capability(exact)
            self.assertTrue(exact["production_operator_available"])
            self.assertEqual(
                exact["materializer_adapter"],
                "tools/tg_azure_cpu_goldbach_historical_operational_materializer.py",
            )

    def test_native_signed_result_is_terminal_compatible(self) -> None:
        index = 7
        phase_result = native_result(index)
        result = {
            "group_index": index,
            "kind": OPERATIONAL_RESULT_KIND,
            "phase": LADDER_PHASE,
            "phase_result": phase_result,
            "retained_export_sha256": digest("archive"),
            "retained_export_size_bytes": 123,
            "retained_tree_sha256": digest("tree"),
            "schema_version": 1,
        }
        identity = _validate_ladder_receipt(
            operational_receipt(index, result),
            index,
            ladder_manifest_sha256=digest("final-ladder-manifest"),
        )
        self.assertEqual(
            identity["payload_receipt_sha256s"],
            phase_result["range_receipt_sha256s"],
        )
        self.assertEqual(
            identity["auxiliary_receipt_sha256s"],
            phase_result["native_receipt_sha256s"],
        )
        changed = copy.deepcopy(result)
        changed["phase_result"]["range_receipt_sha256s"].pop()
        with self.assertRaises(HistoricalGoldbachTerminalError):
            _validate_ladder_receipt(
                operational_receipt(index, changed),
                index,
                ladder_manifest_sha256=digest("final-ladder-manifest"),
            )

    def test_signed_cpu_result_pins_the_exact_retained_archive(self) -> None:
        phase = "initialize-prime-ladder"
        factory = make_factory(phase, 0)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "export"
            (export / "payload").mkdir(parents=True)
            (export / "payload/value").write_bytes(b"historical")
            manifest = _write_export_manifest(export, phase, 0)
            archive = root / "export.tar"
            create_archive(export, archive)
            archive_sha256, archive_size = hash_file_once(archive)
            value = {
                "group_index": 0,
                "kind": OPERATIONAL_RESULT_KIND,
                "phase": phase,
                "phase_result": None,
                "retained_export_sha256": archive_sha256,
                "retained_export_size_bytes": archive_size,
                "retained_tree_sha256": manifest["tree_sha256"],
                "schema_version": 1,
            }
            text = canonical_json_bytes(value).decode("utf-8")
            receipt = {
                "backend": "azure_sevsnp_cpu",
                "claim": {
                    **expected_claim_identity(phase, 0),
                    "input_hash": digest("input"),
                    "output_hash": hashlib.sha256(
                        text.encode("utf-8")
                    ).hexdigest(),
                    "result": text,
                },
            }
            self.assertEqual(
                _validate_cpu_result(receipt, phase, 0, archive),
                value,
            )
            value["retained_tree_sha256"] = digest("substitution")
            text = canonical_json_bytes(value).decode("utf-8")
            receipt["claim"]["result"] = text
            receipt["claim"]["output_hash"] = hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest()
            with self.assertRaises(
                HistoricalGoldbachOperationalWorkloadError
            ):
                _validate_cpu_result(receipt, phase, 0, archive)

    def test_schemas_and_cli_are_parseable(self) -> None:
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
                    / "tools/tg_azure_cpu_goldbach_historical_operational_materializer.py"
                ),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_packaged_python_closure_imports_in_isolated_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in SOURCE_PATHS:
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(
                        package
                        / "tools/"
                        "tg_goldbach_historical_operational_azure_measured_workload.py"
                    ),
                    "--help",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_assembler_maps_final_exports_to_the_terminal_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "binary-export"
            binary_payload = binary / "payload"
            (binary_payload / "binary-receipts").mkdir(parents=True)
            (binary_payload / "binary-plan.json").write_bytes(b"plan")
            (binary_payload / "binary-aggregate.json").write_bytes(
                b"aggregate"
            )
            _write_export_manifest(binary, "binary-semantic-replay", 0)
            binary_archive = root / "binary.tar"
            create_archive(binary, binary_archive)

            ladder = root / "ladder-export"
            ladder_campaign = ladder / "payload/prime-ladder"
            ladder_campaign.mkdir(parents=True)
            (ladder_campaign / "manifest.json").write_bytes(b"manifest")
            (ladder_campaign / "ladder-aggregate.json").write_bytes(
                b"ladder aggregate"
            )
            _write_export_manifest(
                ladder, "reduce-prime-ladder-ranges", 0
            )
            ladder_archive = root / "ladder.tar"
            create_archive(ladder, ladder_archive)

            handoff = root / "terminal-handoff"
            commitment = root / "commitment.json"
            archive = root / "terminal.tar"
            arguments = SimpleNamespace(
                allow_development_key=False,
                allow_test_fixture=False,
                archive_output=archive,
                binary_replay_export=binary_archive,
                build_admission=root / "admission.json",
                commitment_output=commitment,
                h100_receipts_root=root / "h100",
                handoff_root=handoff,
                key_manifest=root / "keys.json",
                ladder_receipts_root=root / "ladder-receipts",
                ladder_reduce_export=ladder_archive,
            )

            def fake_receipts(
                _source, destination, *, count, what,
            ) -> None:
                self.assertIn((count, what), {(8_192, "H100"), (320, "ladder")})
                destination.mkdir(parents=True)

            fake_commitment = {
                "child_identities_sha256": digest("children")
            }
            with (
                mock.patch.object(
                    registration,
                    "_copy_receipt_family",
                    side_effect=fake_receipts,
                ),
                mock.patch.object(
                    registration,
                    "build_child_index",
                    return_value={
                        "entries": [],
                        "kind": "test-index",
                        "schema_version": 1,
                    },
                ),
                mock.patch.object(
                    registration,
                    "load_build_admission",
                    return_value=object(),
                ),
                mock.patch.object(
                    registration,
                    "prepare_terminal_handoff_commitment",
                    return_value=(fake_commitment, [object()] * 8_512),
                ),
            ):
                result = registration.assemble_handoff(arguments)

            self.assertEqual(result["child_count"], 8_512)
            self.assertEqual(
                (handoff / "binary/plan.json").read_bytes(), b"plan"
            )
            self.assertEqual(
                (handoff / "binary/aggregate.json").read_bytes(),
                b"aggregate",
            )
            self.assertEqual(
                (handoff / "ladder/campaign/manifest.json").read_bytes(),
                b"manifest",
            )
            self.assertEqual(
                (handoff / "ladder/aggregate.json").read_bytes(),
                b"ladder aggregate",
            )
            self.assertTrue(commitment.is_file())
            self.assertTrue(archive.is_file())


if __name__ == "__main__":
    unittest.main()
