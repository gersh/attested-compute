# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""The Phala/dstack TDX axiom must stay off the live cone.

Two independent checks:

1. **Import reachability.**  Walk the Lean import graph from every capstone
   and from the compact default root, and assert that no reachable module is
   one of the Phala TDX modules.  This is a pure source check and needs no
   build.
2. **`#print axioms`.**  Elaborate a probe that prints the axioms of each
   capstone theorem and assert `phalaTdxAttestedRun_sound` never appears.
   This is skipped when the Lean build artifacts are absent.

Azure remains the only path that can discharge an atom.  If a future change
deliberately puts the TDX axiom on the cone, this test is the place that must
be edited, consciously.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
IMPORT_RE = re.compile(
    r"^\s*(?:public\s+)?import\s+([A-Za-z_][A-Za-z0-9_'.]*)\s*(?:--.*)?$"
)

PHALA_MODULES = frozenset(
    {
        "SparkInterval.Execution.PhalaTdxAttestation",
        "SparkInterval.Execution.PhalaTdxOperationalAttestation",
        "SparkInterval.Execution.PhalaTdxCampaignCertificate",
        "SparkInterval.Execution.PhalaTdxA7BoundaryCertificate",
        "SparkInterval.Execution.PhalaTdxProd5Evidence",
        "SparkInterval.Tests.PhalaTdxDryRunTest",
        "SparkInterval.Tests.PhalaTdxProd5RunTest",
    }
)

TDX_AXIOM = "phalaTdxAttestedRun_sound"
TDX_OPERATIONAL_AXIOM = "phalaTdxAttestedEmission_sound"

# The supported A.7 TDX campaign theorem and the axioms it may and may not
# use.  `phalaTdxAttestedEmission_sound` is purely operational; the legacy
# `phalaTdxAttestedRun_sound` asserts the campaign's mathematics and must not
# be reachable from the supported path.
SUPPORTED_A7_TDX_THEOREM = (
    "SparkInterval.Execution.certifyCH25A7BoundaryPhalaTdxFromModel"
)
AXIOM_FREE_A7_MODEL_THEOREMS = (
    "SparkInterval.TernaryGoldbach.A7BoundaryWireEvidence."
    "successEvidence_of_modelOutput",
    "SparkInterval.TernaryGoldbach.A7BoundaryWireEvidence."
    "sourceClaim_of_modelOutput",
    "SparkInterval.Execution.ch25A7BoundaryRuns_of_modelOutput",
)

CAPSTONE_ROOTS = (
    "SparkIntervalCompact",
    "SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone",
    "SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone",
    "SparkInterval.TernaryGoldbach.NativeFamilyAggregateCapstone",
)

CAPSTONE_THEOREMS = (
    "SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone."
    "checkerDerivedClaim_of_canonicalAcceptances",
    "SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone."
    "exactTableDownstreamClaim_of_checkerDerivedClaim",
    "SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone."
    "exactTableDownstreamClaim_of_canonicalAcceptances",
    "SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone."
    "checkerDerivedClaim_of_registeredPhysicalOutcomes",
    "SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone."
    "exactTableDownstreamClaim_of_registeredPhysicalOutcomes",
    "SparkInterval.TernaryGoldbach.NativeFamilyAggregateCapstone."
    "claim_of_physicalOutcome",
    "SparkInterval.Execution.SignedResultCertificate.certifyCH25A7Boundary",
    "SparkInterval.Execution.SignedResultCertificate.certifyRun",
)


def module_source(module: str) -> Path | None:
    candidate = ROOT / (module.replace(".", "/") + ".lean")
    return candidate if candidate.is_file() else None


def imports_of(module: str) -> list[str]:
    source = module_source(module)
    if source is None:
        return []
    found = []
    for line in source.read_text(encoding="utf-8").splitlines():
        match = IMPORT_RE.match(line)
        if match:
            found.append(match.group(1))
    return found


def reachable_from(roots: tuple[str, ...]) -> set[str]:
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        stack.extend(imports_of(module))
    return seen


class PhalaTdxOffConeTests(unittest.TestCase):
    def test_phala_modules_exist(self) -> None:
        for module in PHALA_MODULES:
            self.assertIsNotNone(
                module_source(module), f"missing Lean module {module}"
            )

    def test_no_capstone_imports_a_phala_module(self) -> None:
        reachable = reachable_from(CAPSTONE_ROOTS)
        intersection = sorted(reachable & PHALA_MODULES)
        self.assertEqual(
            intersection,
            [],
            "a capstone now transitively imports the Phala TDX layer: "
            + ", ".join(intersection),
        )

    def test_phala_layer_does_not_import_itself_into_shared_modules(
        self,
    ) -> None:
        """No shared Execution module may import the TDX layer.

        The dependency must point one way only: TDX modules import the shared
        registry, never the reverse.
        """

        for source in (ROOT / "SparkInterval").rglob("*.lean"):
            module = (
                source.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")
            )
            if module in PHALA_MODULES:
                continue
            offenders = sorted(set(imports_of(module)) & PHALA_MODULES)
            self.assertEqual(
                offenders,
                [],
                f"{module} imports the Phala TDX layer: "
                + ", ".join(offenders),
            )

    def test_azure_files_are_not_modified_by_the_tdx_layer(self) -> None:
        """The Azure acceptance functions must not mention the TDX layer."""

        for name in (
            "SparkInterval/Execution/TrustedComputePolicy.lean",
            "SparkInterval/Execution/TrustedComputeRegistry.lean",
            "SparkInterval/Execution/TrustedComputeKey.lean",
            "SparkInterval/Execution/ProductionDeploymentPins.lean",
            "SparkInterval/Execution/Attestation.lean",
            "SparkInterval/Execution/RegisteredAlgorithm.lean",
            "SparkInterval/Execution/RegisteredCampaignCertificate.lean",
        ):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("PhalaTdx", text, f"{name} references the TDX layer")
            self.assertNotIn(TDX_AXIOM, text, f"{name} references the TDX axiom")

    def test_capstone_print_axioms_omits_the_tdx_axiom(self) -> None:
        if os.environ.get("SPARKINTERVAL_SKIP_LEAN_PROBE") == "1":
            self.skipTest("Lean probe disabled by environment")
        if shutil.which("lake") is None:
            self.skipTest("lake is not available")
        if not (ROOT / ".lake/build/lib/lean").is_dir():
            self.skipTest("no Lean build artifacts")

        probe = ROOT / ".lake" / "phala-tdx-off-cone-probe.lean"
        lines = [
            "import SparkIntervalCompact",
            "import SparkInterval.Execution.RegisteredA7BoundaryCertificate",
        ]
        lines += [f"#print axioms {name}" for name in CAPSTONE_THEOREMS]
        probe.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            completed = subprocess.run(
                ["lake", "env", "lean", "-j1", "-M8192", str(probe)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=3600,
                env={**os.environ, "LEAN_NUM_THREADS": "1"},
            )
        finally:
            probe.unlink(missing_ok=True)
        output = completed.stdout + completed.stderr
        self.assertEqual(
            completed.returncode, 0, f"probe failed to elaborate:\n{output}"
        )
        for name in CAPSTONE_THEOREMS:
            self.assertIn(
                name.rsplit(".", 1)[-1],
                output,
                f"probe did not report axioms for {name}",
            )
        self.assertNotIn(
            TDX_AXIOM,
            output,
            "the Phala TDX axiom appears in a capstone's axiom set",
        )
        self.assertNotIn(
            TDX_OPERATIONAL_AXIOM,
            output,
            "the Phala TDX operational axiom appears in a capstone's axiom set",
        )
        self.assertNotIn(
            "PhalaTdx", output, "a capstone now depends on the TDX layer"
        )

    def test_supported_a7_path_avoids_the_mathematical_axiom(self) -> None:
        """The supported A.7 TDX theorem must use only the operational axiom.

        `phalaTdxAttestedRun_sound` concludes `invocation.Runs`, which for this
        invocation contains a Lean existential over certificates and an
        analytic statement about Mathlib's zeta function.  Attestation cannot
        establish either, so the supported path must not reach it.  The three
        model theorems below must additionally be free of *every* project
        axiom.
        """

        if os.environ.get("SPARKINTERVAL_SKIP_LEAN_PROBE") == "1":
            self.skipTest("Lean probe disabled by environment")
        if shutil.which("lake") is None:
            self.skipTest("lake is not available")
        if not (ROOT / ".lake/build/lib/lean").is_dir():
            self.skipTest("no Lean build artifacts")

        probe = ROOT / ".lake" / "phala-tdx-supported-path-probe.lean"
        names = (SUPPORTED_A7_TDX_THEOREM,) + AXIOM_FREE_A7_MODEL_THEOREMS
        lines = ["import SparkInterval.Execution.PhalaTdxA7BoundaryCertificate"]
        lines += [f"#print axioms {name}" for name in names]
        probe.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            completed = subprocess.run(
                ["lake", "env", "lean", "-j1", "-M8192", str(probe)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=3600,
                env={**os.environ, "LEAN_NUM_THREADS": "1"},
            )
        finally:
            probe.unlink(missing_ok=True)
        output = completed.stdout + completed.stderr
        self.assertEqual(
            completed.returncode, 0, f"probe failed to elaborate:\n{output}"
        )
        # One report per requested name; `#print axioms` wraps long lists.
        reports = {}
        normalized = " ".join(output.split())
        for name in names:
            marker = f"'{name}' depends on axioms:"
            self.assertIn(marker, normalized, f"no axiom report for {name}")
            tail = normalized.split(marker, 1)[1]
            reports[name] = tail.split("]", 1)[0]
        self.assertNotIn(
            TDX_AXIOM,
            reports[SUPPORTED_A7_TDX_THEOREM],
            "the supported A.7 TDX theorem reaches the legacy mathematical "
            "axiom",
        )
        self.assertIn(
            TDX_OPERATIONAL_AXIOM,
            reports[SUPPORTED_A7_TDX_THEOREM],
            "the supported A.7 TDX theorem no longer records the operational "
            "trust boundary",
        )
        for name in AXIOM_FREE_A7_MODEL_THEOREMS:
            for forbidden in (
                TDX_AXIOM,
                TDX_OPERATIONAL_AXIOM,
                "accepted_run_certificate_sound",
                "ofReduceBool",
                "sorryAx",
            ):
                self.assertNotIn(
                    forbidden,
                    reports[name],
                    f"{name} unexpectedly depends on {forbidden}",
                )


if __name__ == "__main__":
    unittest.main()
