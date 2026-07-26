/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics

/-!
# Compact native-checker boundary for the Platt zeta head

The 22,491 literal Q128 rows are intentionally not materialized in the
compact local build.  A successful native run instead supplies one table,
its checked canonical SHA-256 commitment, strict Hardy-Z brackets, endpoint
realizations, and a multiplicity-aware Turing count.  Ordinary Lean derives
the committed-table source claim.

`CommittedSourceClaim` is deliberately weaker than naming a locally
materialized table value: it says that the table with the reviewed commitment
was checked.  Identifying it with a separately materialized caller table
requires either exact row equality or an explicit cryptographic
second-preimage assumption.  This module does not pretend SHA-256 is
injective.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.ZetaHeadCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

def expectedCommitment : String :=
  "e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7"

def allRowsDigest : String :=
  "fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca"

def canonicalInputText : String :=
  "{\"all_q128_rows_sha256\":\"" ++ allRowsDigest ++ "\"," ++
  "\"campaign\":\"platt-head-2e4\"," ++
  "\"included_q128_rows_sha256\":\"" ++ expectedCommitment ++ "\"," ++
  "\"source_height\":20000,\"source_multiplicity_count\":22491}"

def canonicalInputBytes : ByteArray := canonicalInputText.toUTF8
def canonicalResultBytes : ByteArray := "true".toUTF8

/-- Closed, table-opaque source result suitable for a compact local build. -/
def CommittedSourceClaim : Prop :=
  ∃ table : ZetaHeadSourceSemantics.Q128CellTable,
    table.commitment = expectedCommitment ∧
      ZetaHeadSourceSemantics.Q128SourceClaim table

def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    ∃ table : ZetaHeadSourceSemantics.Q128CellTable,
      Nonempty
        (ZetaHeadSourceSemantics.CheckedQ128HeadEvidence
          table expectedCommitment)

def nativeChecker : NativeCheckerSemantics where
  checkerId := "sparkinterval.ternary-goldbach.platt-head-2e4.compact.v1"
  accepts := Accepts

theorem committedSourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    CommittedSourceClaim := by
  rcases accepted.2.2 with ⟨table, ⟨evidence⟩⟩
  exact ⟨table, evidence.commitment_eq,
    ZetaHeadSourceSemantics.q128SourceClaim_of_checked_evidence evidence⟩

theorem acceptanceImpliesCommittedSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim nativeChecker result CommittedSourceClaim := by
  intro inputBytes accepted
  exact committedSourceClaim_of_acceptance accepted

theorem committedSourceClaim_of_compactRun
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    (receipt :
      CompactInputReceiptExecutionFact
        receiptHash scheme machine pins executable result)
    (executableRefinement :
      ArchitectureRefinesNativeChecker
        scheme machine nativeChecker executable pins.entryPoint) :
    CommittedSourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement
      (acceptanceImpliesCommittedSourceClaim result)

end SparkInterval.TernaryGoldbach.ZetaHeadCompactChecker

end
