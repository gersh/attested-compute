/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker

/-!
# Lightweight tests for the Ramaré native-family compact fallback

These tests quantify over low-level fold evidence.  They do not construct or
replay the 100M/100M/140M production folds.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.RamareNativeFoldsCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture
open SparkInterval.TernaryGoldbach
open SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker

example
    (evidence : RamareNativeFoldContracts.FiniteFoldEvidence) :
    RamareNativeFoldContracts.SourceClaims :=
  RamareNativeFoldContracts.sourceClaims_of_finiteFoldEvidence evidence

example
    {inputBytes resultBytes : ByteArray}
    (input : inputBytes = canonicalInputBytes)
    (result : resultBytes = canonicalResultBytes)
    (evidence : RamareNativeFoldContracts.FiniteFoldEvidence) :
    RamareNativeFoldContracts.SourceClaims := by
  apply sourceClaims_of_acceptance
  exact ⟨input, result, ⟨evidence⟩⟩

example
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
    RamareNativeFoldContracts.SourceClaims :=
  sourceClaims_of_compactRun receipt executableRefinement

example
    {statement : RunStatement}
    {receiptHash : Digest}
    (outcome :
      RegisteredArchitectureInvocation.ramareProductionFoldsCompactV1.PhysicalOutcome
        statement receiptHash)
    (executableRefinement : ClosedExecutableRefinement) :
    RamareNativeFoldContracts.SourceClaims :=
  sourceClaims_of_registeredPhysicalOutcome
    outcome executableRefinement

#print axioms
  SparkInterval.TernaryGoldbach.RamareNativeFoldContracts.sourceClaims_of_finiteFoldEvidence
#print axioms
  SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker.sourceClaims_of_acceptance
#print axioms
  SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker.sourceClaims_of_compactRun
#print axioms
  SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker.sourceClaims_of_registeredPhysicalOutcome

end SparkInterval.Tests.RamareNativeFoldsCompactChecker
