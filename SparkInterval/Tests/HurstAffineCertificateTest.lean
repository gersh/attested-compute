/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstAffineCertificate

/-! Axiom-audit regression for the small Hurst affine arithmetic checker. -/

set_option autoImplicit false

namespace SparkInterval.Tests.HurstAffineCertificate

open SparkInterval.TernaryGoldbach.HurstAffineCertificate

def broadGuard : Guard := {
  lower := ⟨-10, 0, -100, -100⟩
  upper := ⟨10, 10, 100, 100⟩
}

def firstBlock : Block := {
  lower := 1
  upper := 3
  delta := ⟨1, 2, -3, -2⟩
  guard := broadGuard
}

def secondBlock : Block := {
  lower := 3
  upper := 5
  delta := ⟨-1, 1, 1, 2⟩
  guard := broadGuard
}

def exampleCertificate : Certificate := {
  sourceLower := 1
  sourceUpper := 5
  rootState := State.zero
  finalState := ⟨0, 3, -2, 0⟩
  blocks := [firstBlock, secondBlock]
}

theorem exampleCertificate_check : exampleCertificate.check = true := by
  decide

theorem exampleCertificate_valid : exampleCertificate.ArithmeticValid :=
  Certificate.checker_sound exampleCertificate_check

example : ({ exampleCertificate with finalState := State.zero }).check = false := by
  decide

example :
    ({ exampleCertificate with
      blocks := [firstBlock, { secondBlock with lower := 4 }] }).check = false := by
  decide

example :
    ({ exampleCertificate with
      blocks := [firstBlock,
        { secondBlock with
          guard := { broadGuard with lower := ⟨2, 0, -100, -100⟩ } }] }).check =
      false := by
  decide

example : foldState exampleCertificate.rootState exampleCertificate.blocks =
    exampleCertificate.finalState :=
  exampleCertificate_valid.2.2

example :
    foldState State.zero ([firstBlock] ++ [secondBlock]) =
      foldState (foldState State.zero [firstBlock]) [secondBlock] := by
  exact foldState_append State.zero [firstBlock] [secondBlock]

example (left right : List Block)
    (hdeltas : left.map Block.delta = right.map Block.delta) :
    foldState State.zero left = foldState State.zero right :=
  foldState_eq_of_map_delta_eq State.zero hdeltas

example : ¬exampleCertificate.FullSourceRange := by
  decide

#print axioms foldState_append
#print axioms foldState_eq_of_map_delta_eq
#print axioms Certificate.checker_sound
#print axioms checked_physical_run_sound
#print axioms checked_source_scale_sound
#print axioms checked_source_rows_sound
#print axioms checked_full_source_rows_sound
#print axioms exampleCertificate_valid

#check ReplayBlockRealization
#check ReplaySourceScaleEvidence

end SparkInterval.Tests.HurstAffineCertificate
