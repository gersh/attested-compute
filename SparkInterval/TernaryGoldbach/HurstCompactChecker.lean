/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.HurstSourceSemantics

/-!
# Compact native-checker boundary for the shared Hurst campaign

The accepted native result contains only the exact closed campaign input and
result, one arithmetic certificate, and its local replay evidence:

* primitive Möbius and directed-Q96 row deltas;
* local integer guard decisions;
* the literal source range `[1, 10^16 + 1)`; and
* the zero initial state.

In particular, acceptance does not contain either the package-local real
claim or `TGComputeContracts.HurstV2.RealSourceClaims`.  Ordinary Lean first
derives every global prefix from the checked local recurrence, then proves all
five real inequalities, and finally rewrites them into the shared
`TGComputeContracts` vocabulary.

The remaining implementation obligation is explicit:
`ArchitectureRefinesNativeChecker ... nativeChecker ...`.  A production
receipt supplies only one opaque architecture execution; it does not supply
the local Hurst evidence, the real inequalities, or an instruction trace.

This file defines no axiom and performs no production replay.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

namespace Replay

abbrev Certificate :=
  HurstAffineCertificate.Certificate

abbrev LocalSourceScaleEvidence (certificate : Certificate) :=
  HurstSourceSemantics.LocalSourceScaleEvidence certificate

end Replay

/-- Exact closed input of the shared four-residual V2 campaign. -/
def canonicalInputText : String :=
  "{\"campaign\":\"hurst-shared-four-residual-v2\"," ++
  "\"source_lower\":1," ++
  "\"source_upper_exclusive\":10000000000000001}"

/-- The successful final checker emits exactly these four bytes. -/
def canonicalResultText : String := "true"

def canonicalInputBytes : ByteArray :=
  canonicalInputText.toUTF8

def canonicalResultBytes : ByteArray :=
  canonicalResultText.toUTF8

/-- Low-level semantic acceptance of the exact shared Hurst campaign.

`LocalSourceScaleEvidence` contains local replay facts only.  Global prefix
realization and the real-valued source claims are deliberately absent. -/
def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    ∃ certificate : Replay.Certificate,
      certificate.check = true ∧
        Nonempty (Replay.LocalSourceScaleEvidence certificate)

/-- Application-neutral native checker selected for this campaign. -/
def nativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.hurst-shared-four-residual.compact.v1"
  accepts := Accepts

/-- Ordinary local-replay-to-shared-real-claims theorem. -/
theorem realClaims_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    TGComputeContracts.HurstV2.RealSourceClaims := by
  rcases accepted with
    ⟨_input, _result, certificate, hcheck, ⟨evidence⟩⟩
  exact
    HurstSourceSemantics.checked_shared_real_source_claims_of_local
      hcheck evidence

/-- Universal checker-to-mathematics field used by compact receipt
composition. -/
theorem acceptanceImpliesRealClaims (result : MeasuredBlob) :
    AcceptanceImpliesClaim nativeChecker result
      TGComputeContracts.HurstV2.RealSourceClaims := by
  intro inputBytes accepted
  exact realClaims_of_acceptance accepted

/-- Final compact composition for one shared Hurst production run.

No production input or trace is materialized.  The executable refinement is
universal in the hidden input and remains an ordinary theorem obligation. -/
theorem realClaims_of_compactRun
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
    TGComputeContracts.HurstV2.RealSourceClaims :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesRealClaims result)

end SparkInterval.TernaryGoldbach.HurstCompactChecker
