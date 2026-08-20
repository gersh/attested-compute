# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Producer-side mirror of Lean's ``CompCertRunSpec``.

``SparkInterval/Execution/CompCertRunLedger.lean`` defines what a CompCert
artifact run is identified by, and derives the algorithm id and algorithm hash
the signed statement must carry.  An enclave has to compute the *same* strings,
byte for byte, or the signature will be over a statement Lean does not accept.

This module is that computation, in pure stdlib so it can be embedded in a
docker-compose and run inside a CVM with no network and no pip.

⚠ **This file and the Lean definition are two copies of one specification.**
The two repositories do not share a Lean/Python boundary that could enforce
agreement, so it is enforced by test instead:
``tests/test_compcert_run_spec_junction.py`` regenerates the canonical strings
from this module and compares them against the values Lean prints.  Change one
copy without the other and that test fails.  That junction is exactly where the
ψ artifact went wrong once before — it computed ψ itself while the certificate
checked a fixed-point upper bound against a slope — so it is checked, never
asserted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class CompCertRunSpec:
    """Mirror of the Lean structure of the same name."""

    program_name: str
    emitted_c_digest: str
    binary_digest: str
    toolchain: str
    accepted_value: int

    # -- mirrors of the Lean functions, in the same order ------------------

    def spec_well_formed(self) -> bool:
        """Mirror of ``CompCertRunSpec.specWellFormed``."""
        def is_digest(value: str) -> bool:
            return (len(value) == 64
                    and all(c in "0123456789abcdef" for c in value))
        return (is_digest(self.emitted_c_digest)
                and is_digest(self.binary_digest)
                and self.program_name != "" and self.toolchain != "")

    def canonical_definition(self) -> str:
        """Mirror of ``CompCertRunSpec.canonicalDefinition``.

        Field order and the trailing line are load-bearing: this string is the
        SHA-256 preimage that the signature covers.
        """
        return (
            "sparkinterval.registered-algorithm.compcert-run.v1\n"
            f"program={self.program_name}\n"
            f"emitted_c_sha256={self.emitted_c_digest}\n"
            f"binary_sha256={self.binary_digest}\n"
            f"toolchain={self.toolchain}\n"
            f"accepted_value={self.accepted_value}\n"
            "semantics=compile-the-named-c-with-the-named-toolchain-then-run-it-and-"
            "report-the-value-its-entry-point-returns"
        )

    def algorithm_id(self) -> str:
        """Mirror of ``CompCertRunSpec.algorithmId``."""
        return "compcert-run-v1:" + self.program_name

    def algorithm_hash(self) -> str:
        """Mirror of ``CompCertRunSpec.algorithmHash``."""
        return hashlib.sha256(self.canonical_definition().encode("utf-8")).hexdigest()

    def accepted_output(self) -> str:
        """Mirror of ``CompCertRunSpec.acceptedOutput``."""
        return str(self.accepted_value)

    # -- the statement fields a receipt signs ------------------------------

    def statement_identity_fields(self) -> dict[str, str]:
        """The four identity fields of the signed statement.

        ``input_hash`` commits to the artifact digest: the *input* to a
        CompCert run is which artifact was run, since the artifacts take no
        arguments on the accepting path.
        """
        if not self.spec_well_formed():
            raise ValueError(f"malformed CompCertRunSpec: {self!r}")
        return {
            "algorithm_id": self.algorithm_id(),
            "algorithm_hash": self.algorithm_hash(),
            "input_hash": hashlib.sha256(
                self.emitted_c_digest.encode("utf-8")
            ).hexdigest(),
            "result": self.accepted_output(),
            "output_hash": hashlib.sha256(
                self.accepted_output().encode("utf-8")
            ).hexdigest(),
        }


def spec_from_stamp(stamp: dict, *, program_name: str, accepted_value: int
                    ) -> CompCertRunSpec:
    """Build a spec from an ``x86cross`` build stamp.

    The stamp is what `claude_math/tools/x86cross/build.sh` writes; taking the
    digest and toolchain from it rather than from a hand-typed literal is what
    stops the spec drifting away from the artifact it names.
    """
    toolchain = stamp["toolchain"]
    return CompCertRunSpec(
        program_name=program_name,
        emitted_c_digest=stamp["c_sha256"],
        binary_digest=stamp["binary_sha256"],
        toolchain=(
            f"{toolchain['ccomp_version']} {stamp['target']} "
            f"{stamp['ccomp_flags']}".strip()
        ),
        accepted_value=accepted_value,
    )
