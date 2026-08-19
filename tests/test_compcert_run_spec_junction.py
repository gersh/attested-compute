# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""The Lean and Python copies of ``CompCertRunSpec`` must agree, byte for byte.

``SparkInterval/Execution/CompCertRunLedger.lean`` and
``tg_verifier/compcert_run_spec.py`` are two copies of one specification: Lean
decides whether a signed statement is accepted, Python computes what the
enclave signs.  If they disagree by a single character the signature is over a
statement Lean will reject — and the failure appears only after paying for a
run, in the least debuggable place available.

So the junction is *checked*.  This test asks Lean to print the canonical
definition, the algorithm id and the algorithm hash for several specs, and
compares them against the Python mirror.  Change one copy without the other
and this fails.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tg_verifier.compcert_run_spec import CompCertRunSpec  # noqa: E402

# Deliberately varied: a realistic spec, one with an empty-ish toolchain field,
# one with a large accepted value, and one whose name contains characters that
# would break a naive concatenation.
CASES = [
    CompCertRunSpec("CeUHarmonic1048576", "90e03d0676d04615adb0c23f93ad1222"
                    "d40e5dd60d74827bba8d98a04caf9c41",
                    "CompCert 3.17 x86_64-linux -O -fstruct-passing", 1),
    CompCertRunSpec("Ge3SquarefreeDeficitHead3000", "0" * 64, "ccomp", 0),
    CompCertRunSpec("Big", "f" * 64, "ccomp 3.17", 18446744073709551615),
    CompCertRunSpec("name-with_odd.chars", "0123456789abcdef" * 4,
                    "ccomp 3.17 -O2", 42),
]

LEAN_TEMPLATE = """\
import SparkInterval.Execution.CompCertRunLedger
open SparkInterval.Execution
def specs : List CompCertRunSpec := [{specs}]
def main : IO Unit := do
  for s in specs do
    IO.println s.canonicalDefinition
    IO.println "\\u0000FIELD"
    IO.println s.algorithmId
    IO.println "\\u0000FIELD"
    IO.println s.algorithmHash
    IO.println "\\u0000FIELD"
    IO.println (toString s.specWellFormed)
    IO.println "\\u0000RECORD"
"""


def _lean_literal(spec: CompCertRunSpec) -> str:
    return (f'{{ programName := {json.dumps(spec.program_name)}, '
            f'emittedCDigest := {json.dumps(spec.emitted_c_digest)}, '
            f'toolchain := {json.dumps(spec.toolchain)}, '
            f'acceptedValue := {spec.accepted_value} }}')


@pytest.mark.slow
def test_lean_and_python_specs_agree(tmp_path: pathlib.Path) -> None:
    olean = (ROOT / ".lake/build/lib/lean/SparkInterval/Execution/"
             "CompCertRunLedger.olean")
    if not olean.exists():
        pytest.skip("CompCertRunLedger not built; run `lake build "
                    "SparkInterval.Execution.CompCertRunLedger`")

    script = tmp_path / "JunctionProbe.lean"
    script.write_text(LEAN_TEMPLATE.format(
        specs=", ".join(_lean_literal(s) for s in CASES)))
    completed = subprocess.run(
        ["lake", "env", "lean", "--run", str(script)],
        cwd=ROOT, capture_output=True, text=True, timeout=1800)
    assert completed.returncode == 0, completed.stderr[-4000:]

    records = [r for r in completed.stdout.split("\x00RECORD\n") if r.strip()]
    assert len(records) == len(CASES), (
        f"Lean printed {len(records)} records for {len(CASES)} specs")

    for spec, record in zip(CASES, records):
        definition, identifier, digest, well_formed = [
            part.strip("\n") for part in record.split("\x00FIELD\n")]
        assert definition == spec.canonical_definition(), (
            "canonicalDefinition differs between Lean and Python for "
            f"{spec.program_name}")
        assert identifier == spec.algorithm_id()
        assert digest == spec.algorithm_hash(), (
            "algorithmHash differs — the enclave would sign a statement Lean "
            "rejects")
        assert well_formed == str(spec.spec_well_formed()).lower()
