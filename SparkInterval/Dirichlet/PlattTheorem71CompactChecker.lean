/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.PlattTheorem71Contract
import SparkInterval.Execution.CompactClaimReceipt

/-!
# Compact native-checker boundary for Platt Theorem 7.1

Acceptance carries the two parity-indexed, per-modulus GRH-verification
families.  The exact source proposition follows from the ordinary contract
theorem; it is not asserted by the receipt boundary.  Establishing acceptance
from the measured CPU/H100 program remains the universal architecture and
compiler refinement obligation.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.PlattTheorem71CompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

def canonicalInputText : String :=
  "{\"campaign\":\"platt-dirichlet-theorem-7-1\"," ++
  "\"q1_source_campaign\":\"platt-trudgian-rh-3e12\"," ++
  "\"q2_to_q400000_primitive_character_count\":29565923837," ++
  "\"source_modulus_lower\":1,\"source_modulus_upper\":400000}"

def canonicalInputBytes : ByteArray := canonicalInputText.toUTF8
def canonicalResultBytes : ByteArray := "true".toUTF8

def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    Nonempty SparkInterval.Dirichlet.PlattTheorem71SourceEvidence

def nativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.platt-dirichlet-theorem-7-1.compact.v1"
  accepts := Accepts

theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    SparkInterval.Dirichlet.PlattTheorem71DirichletVerification := by
  rcases accepted.2.2 with ⟨evidence⟩
  exact SparkInterval.Dirichlet.plattTheorem71_of_source_evidence evidence

theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim nativeChecker result
      SparkInterval.Dirichlet.PlattTheorem71DirichletVerification := by
  intro inputBytes accepted
  exact sourceClaim_of_acceptance accepted

theorem sourceClaim_of_compactRun
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
    SparkInterval.Dirichlet.PlattTheorem71DirichletVerification :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.Dirichlet.PlattTheorem71CompactChecker
