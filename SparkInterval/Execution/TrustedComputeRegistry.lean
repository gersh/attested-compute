/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.CanonicalHex
import SparkInterval.Execution.Attestation

/-!
# Source-pinned imported trusted-compute runs

This file is generated from independently verified, signed receipts by
`tools/generate_trusted_compute_registry.py` and then reviewed like any other
change to the project's trust boundary.

Keeping admission as a closed source list lets concrete imported certificates
reduce in the Lean kernel without a signature-verification oracle or
`native_decide`.  Editing this list is security-equivalent to changing the one
trusted-execution axiom and must receive the same review.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- Exact normalized receipts admitted by the reviewed importer. -/
def importedTrustedComputeRuns : List TrustedComputeEvidence := []

/-- Lookup is keyed by the canonical receipt SHA-256.  Duplicate identifiers
are rejected by the registry generator before this source is emitted. -/
def lookupImportedTrustedComputeRun
    (receiptHash : Digest) : Option TrustedComputeEvidence :=
  importedTrustedComputeRuns.find? (fun evidence =>
    evidence.receiptHash == receiptHash)

end SparkInterval.Execution
