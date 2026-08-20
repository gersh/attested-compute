# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""The Lean and Python copies of ``CompCertRunSpec`` must agree, byte for byte.

``SparkInterval/Execution/CompCertRunLedger.lean`` decides whether a signed
statement is accepted; ``tg_verifier/compcert_run_spec.py`` computes what the
enclave signs.  They are two copies of one specification with no shared
boundary to enforce agreement, so it is enforced here instead: Lean prints the
canonical definition, the algorithm id, the algorithm hash and the
well-formedness flag for several specs, and this test compares each against the
Python mirror.

A disagreement of one character means the enclave signs a statement Lean
rejects — discovered only after paying for an attested run.  That is why the
junction is checked rather than asserted.

Skipped, loudly, when the Lean module has not been built: the check needs
``lake build SparkInterval.Execution.CompCertRunLedger`` first.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tg_verifier.compcert_run_spec import CompCertRunSpec  # noqa: E402

OLEAN = (ROOT / ".lake/build/lib/lean/SparkInterval/Execution"
         / "CompCertRunLedger.olean")

# Deliberately varied: a realistic spec, an all-zero digest, a value at the
# 64-bit boundary, and a name with characters a naive concatenation would break.
CASES = [
    CompCertRunSpec(
        "CeUHarmonic1048576",
        "90e03d0676d04615adb0c23f93ad1222d40e5dd60d74827bba8d98a04caf9c41",
        "7983a8777e79a59b0df5a7c4d40bc217badf5ecec1beaa706e03b6ed2572b516",
        "CompCert 3.17 x86_64-linux -O -fstruct-passing", 1),
    CompCertRunSpec("Ge3SquarefreeDeficitHead3000", "0" * 64, "1" * 64,
                    "ccomp", 0),
    CompCertRunSpec("Big", "f" * 64, "e" * 64, "ccomp 3.17",
                    18446744073709551615),
    CompCertRunSpec("name-with_odd.chars", "0123456789abcdef" * 4,
                    "fedcba9876543210" * 4, "ccomp 3.17 -O2", 42),
]

SEPARATOR = "==RECORD=="


def _lean_literal(spec: CompCertRunSpec) -> str:
    def quoted(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return ("{ programName := " + quoted(spec.program_name) +
            ", emittedCDigest := " + quoted(spec.emitted_c_digest) +
            ", binaryDigest := " + quoted(spec.binary_digest) +
            ", toolchain := " + quoted(spec.toolchain) +
            ", acceptedValue := " + str(spec.accepted_value) + " }")


class CompCertRunSpecJunctionTests(unittest.TestCase):
    def test_lean_and_python_agree_on_every_field(self) -> None:
        if not OLEAN.exists():
            self.skipTest(
                "CompCertRunLedger is not built; run "
                "`lake build SparkInterval.Execution.CompCertRunLedger`")

        probe = ROOT / ".lake" / "compcert_run_spec_junction_probe.lean"
        probe.write_text(
            "import SparkInterval.Execution.CompCertRunLedger\n"
            "open SparkInterval.Execution\n"
            "def specs : List CompCertRunSpec :=\n  [ " +
            ",\n    ".join(_lean_literal(s) for s in CASES) + " ]\n"
            "def main : IO Unit := do\n"
            "  for s in specs do\n"
            "    IO.println s.algorithmId\n"
            "    IO.println s.algorithmHash\n"
            "    IO.println (toString s.specWellFormed)\n"
            "    IO.println s.canonicalDefinition\n"
            f"    IO.println \"{SEPARATOR}\"\n")
        try:
            completed = subprocess.run(
                ["lake", "env", "lean", "--run", str(probe)],
                cwd=ROOT, capture_output=True, text=True, timeout=1800)
        finally:
            probe.unlink(missing_ok=True)
        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])

        records = [r for r in completed.stdout.split(SEPARATOR + "\n")
                   if r.strip()]
        self.assertEqual(len(records), len(CASES),
                         f"Lean printed {len(records)} records for "
                         f"{len(CASES)} specs")

        for spec, record in zip(CASES, records):
            lines = record.split("\n")
            with self.subTest(program=spec.program_name):
                self.assertEqual(lines[0], spec.algorithm_id())
                self.assertEqual(
                    lines[1], spec.algorithm_hash(),
                    "algorithmHash differs — the enclave would sign a "
                    "statement Lean rejects")
                self.assertEqual(lines[2],
                                 str(spec.spec_well_formed()).lower())
                self.assertEqual("\n".join(lines[3:]).rstrip("\n"),
                                 spec.canonical_definition())


if __name__ == "__main__":
    unittest.main()
