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


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "tools", ROOT / "attestation", ROOT / "azure"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import generate_goldbach_historical_terminal_registration as registration  # noqa: E402
import generate_trusted_compute_lean as lean_generator  # noqa: E402
import tg_goldbach_historical_azure_measured_workload as measured  # noqa: E402
from tg_verifier import azure_portfolio  # noqa: E402
from tg_verifier.azure_cpu_goldbach_historical_workload_factory import (  # noqa: E402
    CAMPAIGN_ID,
    GROUP_ID,
    OWNER_ATOM_ID,
    PHASE_DEPENDENCIES,
    PHASE_ID,
    PORTFOLIO_ARGV,
    REGISTERED_INVOCATION,
    SOURCE_PATHS,
    TERMINAL_FACTORY,
    expected_registered_hashes,
    factory_for_portfolio_group,
)
from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.goldbach_historical_terminal import (  # noqa: E402
    BRANCH_SUMMARY_KIND,
    H100_PHASE,
    LADDER_PHASE,
    NOT_APPLICABLE_DIGEST,
    HistoricalGoldbachTerminalError,
    child_identity_commitment,
    expected_child_topology,
    ladder_group_identity,
)
from tg_verifier.h100_cluster import WORKLOADS  # noqa: E402


def digest(tag: str) -> str:
    return hashlib.sha256(tag.encode("utf-8")).hexdigest()


def h100_identity(index: int) -> dict:
    return {
        "algorithm_hash": digest(f"algorithm:{index}"),
        "algorithm_id": f"test.h100.{index}",
        "artifacts": {
            "device_cubin_hash": digest("cubin"),
            "host_executable_hash": digest("host"),
            "kernel_manifest_hash": digest(f"projection:{index}"),
            "source_tree_hash": digest("source"),
        },
        "auxiliary_receipt_sha256s": [],
        "backend": "azure_ncc40ads_h100_v5",
        "claim_sha256": digest(f"claim:{index}"),
        "domain_hash": digest(f"domain:{index}"),
        "group_id": f"{CAMPAIGN_ID}::{H100_PHASE}",
        "input_hash": digest(f"input:{index}"),
        "output_hash": digest(f"output:{index}"),
        "parameters_hash": digest("parameters"),
        "payload_receipt_sha256s": [
            digest(f"payload:{index}:{leaf}") for leaf in range(8)
        ],
        "phase": H100_PHASE,
        "receipt_sha256": digest(f"receipt:{index}"),
        "shard_index": index,
    }


def branch_summary() -> dict:
    return {
        "binary_aggregate_file_sha256": digest("binary-file"),
        "binary_aggregate_sha256": digest("binary"),
        "binary_plan_sha256": digest("plan"),
        "binary_receipt_merkle_root_sha256": digest("binary-merkle"),
        "kind": BRANCH_SUMMARY_KIND,
        "ladder_aggregate_file_sha256": digest("ladder-file"),
        "ladder_aggregate_sha256": digest("ladder"),
        "ladder_manifest_sha256": digest("ladder-manifest"),
        "ladder_receipt_merkle_root_sha256": digest("ladder-merkle"),
        "schema_version": 1,
    }


def terminal_group() -> dict:
    return {
        "backend_class": "cpu_exact_sidecar",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PORTFOLIO_ARGV),
        "depends_on": list(PHASE_DEPENDENCIES),
        "group_id": GROUP_ID,
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": OWNER_ATOM_ID,
        "phase_id": PHASE_ID,
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": None,
        "shard_count": 1,
        "terminal": True,
    }


class HistoricalGoldbachTerminalTests(unittest.TestCase):
    def test_registered_factory_matches_the_lean_registry(self) -> None:
        expected = lean_generator.registered_invocation_expected(
            REGISTERED_INVOCATION
        )
        self.assertEqual(
            expected,
            {
                **expected_registered_hashes(),
                "result": "true",
                "target": "azure_sevsnp_cpu",
                "trust": "azure_sevsnp_confidential_compute",
            },
        )

    def test_portfolio_terminal_uses_the_exact_measured_finalizer_contract(
        self,
    ) -> None:
        workload = next(
            row for row in WORKLOADS if row.campaign_id == CAMPAIGN_ID
        )
        phase = next(row for row in workload.phase_dag if row.phase_id == PHASE_ID)
        self.assertEqual(phase.command, PORTFOLIO_ARGV)
        group = terminal_group()
        self.assertEqual(factory_for_portfolio_group(group, 0), TERMINAL_FACTORY)
        azure_portfolio._bind_group_operator_capability(group)
        self.assertTrue(group["production_operator_available"])
        self.assertEqual(
            group["materializer_adapter"],
            "tools/tg_azure_cpu_goldbach_historical_materializer.py",
        )

    def test_terminal_factory_rejects_command_dependency_and_topology_changes(
        self,
    ) -> None:
        for field, value in (
            ("command_template", [*PORTFOLIO_ARGV, "--unsafe"]),
            ("depends_on", list(reversed(PHASE_DEPENDENCIES))),
            ("shard_count", 2),
            ("terminal", False),
        ):
            with self.subTest(field=field):
                changed = terminal_group()
                changed[field] = value
                self.assertIsNone(factory_for_portfolio_group(changed, 0))

    def test_expected_topology_has_no_gap_or_alias(self) -> None:
        topology = expected_child_topology()
        self.assertEqual(len(topology), 8_512)
        self.assertEqual(topology[0], (H100_PHASE, 0))
        self.assertEqual(topology[8_191], (H100_PHASE, 8_191))
        self.assertEqual(topology[8_192], (LADDER_PHASE, 0))
        self.assertEqual(topology[-1], (LADDER_PHASE, 319))
        self.assertEqual(len(set(topology)), len(topology))

    def test_commitment_rejects_reordering_omission_and_duplication(self) -> None:
        topology = ((H100_PHASE, 0), (H100_PHASE, 1))
        identities = [h100_identity(0), h100_identity(1)]
        with mock.patch(
            "tg_verifier.goldbach_historical_terminal.expected_child_topology",
            return_value=topology,
        ):
            good = child_identity_commitment(identities, branch_summary())
            self.assertEqual(good["child_count"], 2)
            for changed in (
                list(reversed(identities)),
                identities[:1],
                [identities[0], identities[0]],
            ):
                with self.assertRaises(HistoricalGoldbachTerminalError):
                    child_identity_commitment(changed, branch_summary())

    def test_branch_mutation_changes_the_transitive_commitment(self) -> None:
        topology = ((H100_PHASE, 0), (H100_PHASE, 1))
        identities = [h100_identity(0), h100_identity(1)]
        with mock.patch(
            "tg_verifier.goldbach_historical_terminal.expected_child_topology",
            return_value=topology,
        ):
            first = child_identity_commitment(identities, branch_summary())
            changed = branch_summary()
            changed["binary_aggregate_sha256"] = digest("substitution")
            second = child_identity_commitment(identities, changed)
        self.assertNotEqual(
            canonical_json_bytes(first), canonical_json_bytes(second)
        )

    def test_ladder_group_identity_binds_group_and_manifest(self) -> None:
        first = ladder_group_identity(
            0, ladder_manifest_sha256=digest("manifest-a")
        )
        second = ladder_group_identity(
            1, ladder_manifest_sha256=digest("manifest-a")
        )
        changed_manifest = ladder_group_identity(
            0, ladder_manifest_sha256=digest("manifest-b")
        )
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, changed_manifest)

    def test_child_index_is_canonical_and_content_addressed(self) -> None:
        topology = ((H100_PHASE, 0), (LADDER_PHASE, 0))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            h100 = root / "children/h100/receipt-00000000.json"
            ladder = root / "children/ladder/receipt-00000000.json"
            h100.parent.mkdir(parents=True)
            ladder.parent.mkdir(parents=True)
            h100.write_bytes(b"h100")
            ladder.write_bytes(b"ladder")
            with mock.patch.object(
                registration,
                "expected_child_topology",
                return_value=topology,
            ):
                value = registration.build_child_index(root)
        self.assertEqual(
            [(row["phase"], row["shard_index"]) for row in value["entries"]],
            list(topology),
        )
        self.assertEqual(
            value["entries"][0]["receipt_file_sha256"],
            hashlib.sha256(b"h100").hexdigest(),
        )

    def test_trace_binds_handoff_commitment_and_both_branch_summaries(self) -> None:
        arguments = {
            "challenge": digest("challenge"),
            "job_binding": digest("job"),
            "input_sha256": digest("input"),
            "handoff_sha256": digest("handoff"),
            "commitment_sha256": digest("commitment"),
            "summary": branch_summary(),
            "combined_sha256": digest("combined"),
            "result_sha256": digest("result"),
        }
        baseline = measured._trace_hash(**arguments)
        for field in (
            "handoff_sha256",
            "commitment_sha256",
            "combined_sha256",
        ):
            changed = copy.deepcopy(arguments)
            changed[field] = digest(f"changed:{field}")
            self.assertNotEqual(baseline, measured._trace_hash(**changed))
        changed = copy.deepcopy(arguments)
        changed["summary"]["ladder_aggregate_sha256"] = digest(
            "changed:ladder"
        )
        self.assertNotEqual(baseline, measured._trace_hash(**changed))

    def test_lean_boundary_is_fail_closed_and_has_no_native_decide(self) -> None:
        pins = (
            ROOT
            / "SparkInterval/Execution/HistoricalGoldbachTerminalPins.lean"
        ).read_text(encoding="utf-8")
        registry = (
            ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "def helfgottPlattGoldbachTerminalArtifactPins", pins
        )
        self.assertIn(
            "helfgottPlattGoldbachProductionV1_unconfigured", registry
        )
        self.assertNotIn("native_decide", pins)

    def test_schemas_are_strict_and_parseable(self) -> None:
        for name in (
            "azure-cpu-goldbach-historical-terminal-materializer-site.schema.json",
            "azure-cpu-goldbach-historical-terminal-materialization.schema.json",
        ):
            value = json.loads((ROOT / "schemas" / name).read_text())
            self.assertFalse(value["additionalProperties"])
            self.assertEqual(value["properties"]["schema_version"]["const"], 1)

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
                        / "tools/tg_goldbach_historical_azure_measured_workload.py"
                    ),
                    "--help",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_pin_candidate_covers_every_transitive_pin(self) -> None:
        pins = {field: digest(field) for field in registration.PIN_DEFINITIONS}
        source = registration.render_lean_pin_candidate(pins)
        for field, definition in registration.PIN_DEFINITIONS.items():
            self.assertIn(
                f'def {definition} : Option Digest := some "{pins[field]}"',
                source,
            )
        self.assertIn(NOT_APPLICABLE_DIGEST, (
            ROOT
            / "SparkInterval/Execution/HistoricalGoldbachTerminalPins.lean"
        ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
