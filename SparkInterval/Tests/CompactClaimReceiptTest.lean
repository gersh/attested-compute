/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt

/-!
# Symbolic compact-claim composition test

This file elaborates only the generic theorem shape.  It contains no concrete
artifact, input, native execution, or architecture trace.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CompactClaimReceipt

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

example
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    {Claim : Prop}
    (receipt :
      CompactInputReceiptExecutionFact
        receiptHash scheme machine pins executable result)
    (executableRefinement :
      ArchitectureRefinesNativeChecker
        scheme machine checker executable pins.entryPoint)
    (claimSoundness :
      AcceptanceImpliesClaim checker result Claim) :
    Claim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement claimSoundness

#print axioms claim_of_compactInputReceipt
#print axioms claim_of_compactInputReceipt'

end SparkInterval.Tests.CompactClaimReceipt
