# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Cross-layer audit of the Azure TG terminal semantic inventory."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import generate_trusted_compute_lean as lean_generator  # noqa: E402

from tg_verifier.h100_cluster import WORKLOADS  # noqa: E402


BINDINGS = ROOT / "specifications/TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
REGISTERED_ALGORITHM = ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"

STAGED_BINDINGS = {
    "cdem-table-abel": {
        "enabled": True,
        "lean_theorem": (
            "SparkInterval.Execution.SignedResultCertificate."
            "certifyCDEMTableAbel"
        ),
        "realization_id": "cdemTableAbelReceiptSourceClaimV2",
        "registered_invocation": "cdemTableAbelProductionV2",
        "result_path": "${TG_RUN_ROOT}/cdem-table-abel/registered-result.txt",
        "writer": ("tools/tg_verify.py", "def _write_cdem_registered_result"),
    },
    "ch25-a7-boundary": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "ch25A7BoundaryProductionV1_sourceClaim"
        ),
        "realization_id": "ch25A7BoundarySourceClaimV1",
        "registered_invocation": "ch25A7BoundaryProductionV1",
        "result_path": (
            "${TG_RUN_ROOT}/ch25-a7-boundary/registered-result.txt"
        ),
        "writer": (
            "tools/tg_verify.py",
            "def _write_a7_registered_result",
        ),
    },
    "ch25-psi-two-pass-v1": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "ch25PsiLemma92ProductionV1_sourceClaim"
        ),
        "realization_id": "ch25PsiLemma92SourceClaimV1",
        "registered_invocation": "ch25PsiLemma92ProductionV1",
        "result_path": "${TG_RUN_ROOT}/ch25-psi-1e13/registered-result.txt",
        "writer": (
            "tg_verifier/psi_residual_campaign.py",
            "def write_registered_result",
        ),
    },
    "helfgott-prop-12-2-4-mpfr-v1": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "helfgottProp1224ProductionV1_sourceClaim"
        ),
        "realization_id": "helfgottProp1224SourceClaimV1",
        "registered_invocation": "helfgottProp1224ProductionV1",
        "result_path": (
            "${TG_RUN_ROOT}/helfgott-prop-12-2-4/registered-result.txt"
        ),
        "writer": (
            "tools/tg_prop1224_mpfr_campaign.py",
            "def write_registered_result",
        ),
    },
    "helfgott-platt-goldbach-gpu-v1": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "helfgottPlattGoldbachProductionV1_sourceClaim"
        ),
        "realization_id": "helfgottPlattGoldbachSourceClaimV1",
        "registered_invocation": "helfgottPlattGoldbachProductionV1",
        "result_path": (
            "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/"
            "registered-result.txt"
        ),
        "writer": (
            "tools/tg_goldbach_historical_finalizer.py",
            "def write_registered_result",
        ),
    },
    "hurst-four-residuals-v1": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "hurstSharedFourResidualProductionV2_realClaims"
        ),
        "realization_id": "hurstSharedFourResidualRealClaimsV2",
        "registered_invocation": "hurstSharedFourResidualProductionV2",
        "result_path": "${TG_RUN_ROOT}/mertens-hurst/registered-result.txt",
        "writer": (
            "tg_verifier/hurst_residual_campaign.py",
            "def write_registered_result",
        ),
    },
    "platt-dirichlet-theorem-7-1": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "plattDirichletTheorem71ProductionV1_sourceClaim"
        ),
        "realization_id": "plattDirichletTheorem71SourceClaimV1",
        "registered_invocation": "plattDirichletTheorem71ProductionV1",
        "result_path": (
            "${TG_RUN_ROOT}/platt-dirichlet-theorem-7-1/"
            "registered-result.txt"
        ),
        "writer": (
            "tools/tg_dirichlet_campaign.py",
            "def _write_registered_result",
        ),
    },
    "platt-head-2e4": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "plattHead2e4ProductionV1_sourceClaim"
        ),
        "realization_id": "plattHead2e4SourceClaimV1",
        "registered_invocation": "plattHead2e4ProductionV1",
        "result_path": (
            "${TG_RUN_ROOT}/platt-head-2e4/registered-result.txt"
        ),
        "writer": (
            "tools/tg_zeta_campaign.py",
            "def _write_registered_result",
        ),
    },
    "platt-trudgian-rh-3e12": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "plattTrudgianFiniteRHProductionV1_sourceClaim"
        ),
        "realization_id": "plattTrudgianFiniteRHSourceClaimV1",
        "registered_invocation": "plattTrudgianFiniteRHProductionV1",
        "result_path": (
            "${TG_RUN_ROOT}/platt-trudgian-rh-3e12/"
            "registered-result.txt"
        ),
        "writer": (
            "tools/tg_platt_zeta_campaign.py",
            "def _write_registered_result",
        ),
    },
    "ramare-zuniga-lemma-6-2": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "ramareZunigaLemma62ProductionV1_sourceClaim"
        ),
        "realization_id": "ramareZunigaLemma62SourceClaimV1",
        "registered_invocation": "ramareZunigaLemma62ProductionV1",
        "result_path": (
            "${TG_RUN_ROOT}/ramare-zuniga-lemma-6-2/registered-result.txt"
        ),
        "writer": (
            "tg_verifier/r2star_campaign.py",
            "def write_registered_result",
        ),
    },
    "ternary-goldbach-finite-below-10pow27-v1": {
        "enabled": False,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "goldbach10Pow27ProductionV1_sourceClaim"
        ),
        "realization_id": "goldbach10Pow27SourceClaimV1",
        "registered_invocation": "goldbach10Pow27ProductionV1",
        "result_path": (
            "${TG_RUN_ROOT}/goldbach-finite-below-10pow27/registered-result.txt"
        ),
        "writer": (
            "tools/tg_goldbach_10pow27_finalizer.py",
            "def write_registered_result",
        ),
    },
}

NULL_BINDINGS: set[str] = set()


def lean_registered_invocations() -> set[str]:
    source = REGISTERED_ALGORITHM.read_text(encoding="utf-8")
    block = source.split("inductive RegisteredInvocation where", 1)[1]
    block = block.split("deriving Repr, DecidableEq, BEq", 1)[0]
    return set(
        re.findall(r"^\s*\|\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", block, re.MULTILINE)
    )


def physical_campaign_terminal_commands() -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for workload in WORKLOADS:
        if workload.shared_owner_atom is not None:
            continue
        if workload.campaign_id in result:
            raise AssertionError(f"duplicate physical owner: {workload.campaign_id}")
        if workload.postcheck:
            result[workload.campaign_id] = workload.postcheck
        elif workload.execution_mode == "manual_phase_dag":
            result[workload.campaign_id] = workload.phase_dag[-1].command
        else:
            result[workload.campaign_id] = workload.command
    return result


class TGSemanticBindingsTests(unittest.TestCase):
    def test_inventory_matches_registered_terminal_sources(self) -> None:
        document = json.loads(BINDINGS.read_text(encoding="utf-8"))
        rows = {row["campaign_id"]: row for row in document["bindings"]}
        commands = physical_campaign_terminal_commands()

        self.assertEqual(set(rows), set(commands))
        self.assertEqual(set(rows), set(STAGED_BINDINGS) | NULL_BINDINGS)

        lean_invocations = lean_registered_invocations()
        importer_invocations = set(lean_generator.REGISTERED_INVOCATIONS)
        for campaign_id, expected in STAGED_BINDINGS.items():
            with self.subTest(campaign_id=campaign_id):
                row = rows[campaign_id]
                self.assertEqual(
                    row,
                    {
                        "campaign_id": campaign_id,
                        "enabled": expected["enabled"],
                        "lean_theorem": expected["lean_theorem"],
                        "realization_id": expected["realization_id"],
                        "registered_invocation": expected["registered_invocation"],
                    },
                )
                invocation = expected["registered_invocation"]
                self.assertIn(invocation, lean_invocations)
                self.assertIn(invocation, importer_invocations)
                theorem_name = expected["lean_theorem"].rsplit(".", 1)[1]
                theorem_source = (
                    ROOT / "SparkInterval/Execution/RegisteredCDEMAbelCertificate.lean"
                    if campaign_id == "cdem-table-abel"
                    else REGISTERED_ALGORITHM
                ).read_text(encoding="utf-8")
                self.assertRegex(
                    theorem_source,
                    rf"\btheorem\s+{re.escape(theorem_name)}\b",
                )

                command = commands[campaign_id]
                positions = [
                    index
                    for index, value in enumerate(command)
                    if value == "--registered-result-output"
                ]
                self.assertEqual(len(positions), 1)
                self.assertLess(positions[0] + 1, len(command))
                self.assertEqual(command[positions[0] + 1], expected["result_path"])

                writer_path, writer_marker = expected["writer"]
                self.assertIn(
                    writer_marker,
                    (ROOT / writer_path).read_text(encoding="utf-8"),
                )

        for campaign_id in NULL_BINDINGS:
            with self.subTest(campaign_id=campaign_id):
                row = rows[campaign_id]
                self.assertFalse(row["enabled"])
                self.assertIsNone(row["lean_theorem"])
                self.assertIsNone(row["realization_id"])
                self.assertIsNone(row["registered_invocation"])
                self.assertNotIn(
                    "--registered-result-output", commands[campaign_id]
                )

        commands_with_registered_results = {
            campaign_id
            for campaign_id, command in commands.items()
            if "--registered-result-output" in command
        }
        self.assertEqual(commands_with_registered_results, set(STAGED_BINDINGS))


if __name__ == "__main__":
    unittest.main()
