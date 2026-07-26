/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CPrimitives
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.IR

/-!
# Source-level C arithmetic compositions for the Sqrt218 checker

`CPrimitives` proves the individual fixed-width C helper operations correct.
This module composes those helpers in the same order as the three arithmetic
blocks in `sqrt218_cpu_checker.c`:

* `tg_head_right`;
* the accumulator and strict-head part of `tg_sq218_scan_step_v2`; and
* the arithmetic part of `tg_sq218_anchor_v2`.

For each block, the `c...` definition uses the source-level C primitive model
and the `spec...` definition uses the architecture-neutral `U128` operations
used by `IR.lean`.  Successful C executions are proved to produce the exact
same values and guards as their specifications.

Parser, roster, reciprocal derivation, event iteration, C compiler, ABI,
machine code, loader, and CPU semantics are intentionally outside this file.
There is no closed production input and no certificate replay.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArithmeticRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPrimitives

private theorem optionBind_some {α β : Type}
    {first : Option α} {rest : α → Option β} {result : β}
    (hbind : first >>= rest = some result) :
    ∃ value, first = some value ∧ rest value = some result :=
  Option.bind_eq_some_iff.mp hbind

private theorem exceptBind_ok_of {ε α β : Type}
    {first : Except ε α} {rest : α → Except ε β}
    {value : α} {result : β}
    (hfirst : first = .ok value)
    (hrest : rest value = .ok result) :
    first >>= rest = .ok result := by
  rw [hfirst]
  exact hrest

/-! ## `tg_head_right` -/

/-- Source-level helper-call composition in `tg_head_right`.  `U128.ofWord`
models the fact that the C `root` parameter already has type `uint64_t`. -/
def cHeadRight
    (root logScaleWord reciprocalScaleWord : Nat) : Option U128 := do
  let start ← U128.ofWord root
  let withConstant ←
    CPrimitives.mulWordChecked start 2501
  let withLogScale ←
    CPrimitives.mulWordChecked withConstant logScaleWord
  CPrimitives.mulWordChecked withLogScale reciprocalScaleWord

/-- Architecture-neutral spelling of the public `IR.headRight` arithmetic. -/
def specHeadRight
    (root logScaleWord reciprocalScaleWord : Nat) : Option U128 := do
  let start ← U128.ofWord root
  let withConstant ← U128.mulWordChecked start 2501
  let withLogScale ←
    U128.mulWordChecked withConstant logScaleWord
  U128.mulWordChecked withLogScale reciprocalScaleWord

theorem cHeadRight_refines
    {root logScaleWord reciprocalScaleWord : Nat} {result : U128}
    (hrun :
      cHeadRight root logScaleWord reciprocalScaleWord = some result) :
    specHeadRight root logScaleWord reciprocalScaleWord = some result := by
  unfold cHeadRight at hrun
  rcases optionBind_some hrun with ⟨start, hstart, hrun⟩
  have hstartValid := (U128.ofWord_sound hstart).2.1
  rcases optionBind_some hrun with
    ⟨withConstant, hconstant, hrun⟩
  have hconstantSpec :
      U128.mulWordChecked start 2501 = some withConstant :=
    CPrimitives.mulWordChecked_refines hstartValid hconstant
  have hconstantValid :=
    (U128.mulWordChecked_sound hconstantSpec).2.1
  rcases optionBind_some hrun with
    ⟨withLogScale, hlogScale, hreciprocalScale⟩
  have hlogScaleSpec :
      U128.mulWordChecked withConstant logScaleWord =
        some withLogScale :=
    CPrimitives.mulWordChecked_refines
      hconstantValid hlogScale
  have hlogScaleValid :=
    (U128.mulWordChecked_sound hlogScaleSpec).2.1
  have hreciprocalScaleSpec :
      U128.mulWordChecked withLogScale reciprocalScaleWord =
        some result :=
    CPrimitives.mulWordChecked_refines
      hlogScaleValid hreciprocalScale
  unfold specHeadRight
  exact Option.bind_eq_some_iff.mpr
    ⟨start, hstart, Option.bind_eq_some_iff.mpr
      ⟨withConstant, hconstantSpec, Option.bind_eq_some_iff.mpr
        ⟨withLogScale, hlogScaleSpec, hreciprocalScaleSpec⟩⟩⟩

theorem specHeadRight_value
    {root logScaleWord reciprocalScaleWord : Nat} {result : U128}
    (hrun :
      specHeadRight root logScaleWord reciprocalScaleWord = some result) :
    result.toNat =
      root * 2501 * logScaleWord * reciprocalScaleWord := by
  unfold specHeadRight at hrun
  rcases optionBind_some hrun with ⟨start, hstart, hrun⟩
  rcases optionBind_some hrun with
    ⟨withConstant, hconstant, hrun⟩
  rcases optionBind_some hrun with
    ⟨withLogScale, hlogScale, hreciprocalScale⟩
  rw [(U128.mulWordChecked_sound hreciprocalScale).2.2,
    (U128.mulWordChecked_sound hlogScale).2.2,
    (U128.mulWordChecked_sound hconstant).2.2,
    (U128.ofWord_sound hstart).2.2]

theorem cHeadRight_value
    {root logScaleWord reciprocalScaleWord : Nat} {result : U128}
    (hrun :
      cHeadRight root logScaleWord reciprocalScaleWord = some result) :
    result.toNat =
      root * 2501 * logScaleWord * reciprocalScaleWord :=
  specHeadRight_value (cHeadRight_refines hrun)

private def fromOverflow {α : Type} : Option α → Except Reject α
  | none => .error .overflow
  | some value => .ok value

private def exceptHeadRight
    (image : ArchiveImage) (root : Nat) : Except Reject U128 := do
  let start ← fromOverflow (U128.ofWord root)
  let withConstant ←
    fromOverflow (U128.mulWordChecked start 2501)
  let withLogScale ←
    fromOverflow
      (U128.mulWordChecked withConstant image.header.logScale)
  fromOverflow
    (U128.mulWordChecked
      withLogScale image.header.reciprocalScale)

private theorem IR_headRight_eq_exceptHeadRight
    (image : ArchiveImage) (root : Nat) :
    headRight image root = exceptHeadRight image root := by
  rfl

/-- A successful architecture-neutral head composition is exactly the
successful `Except` outcome of the public IR helper.  All four IR failures in
this helper are the same `.overflow`, so the successful correspondence loses
no rejection information. -/
theorem specHeadRight_implies_IR_headRight
    {image : ArchiveImage} {root : Nat} {result : U128}
    (hrun :
      specHeadRight root image.header.logScale
          image.header.reciprocalScale =
        some result) :
    headRight image root = .ok result := by
  unfold specHeadRight at hrun
  rcases optionBind_some hrun with ⟨start, hstart, hrun⟩
  rcases optionBind_some hrun with
    ⟨withConstant, hconstant, hrun⟩
  rcases optionBind_some hrun with
    ⟨withLogScale, hlogScale, hreciprocalScale⟩
  have hstartExcept :
      fromOverflow (U128.ofWord root) = .ok start := by
    rw [hstart]
    rfl
  have hconstantExcept :
      fromOverflow (U128.mulWordChecked start 2501) =
        .ok withConstant := by
    rw [hconstant]
    rfl
  have hlogScaleExcept :
      fromOverflow
          (U128.mulWordChecked
            withConstant image.header.logScale) =
        .ok withLogScale := by
    rw [hlogScale]
    rfl
  have hreciprocalScaleExcept :
      fromOverflow
          (U128.mulWordChecked
            withLogScale image.header.reciprocalScale) =
        .ok result := by
    rw [hreciprocalScale]
    rfl
  rw [IR_headRight_eq_exceptHeadRight]
  unfold exceptHeadRight
  exact exceptBind_ok_of hstartExcept
    (exceptBind_ok_of hconstantExcept
      (exceptBind_ok_of hlogScaleExcept
        hreciprocalScaleExcept))

/-- Direct source-to-IR correspondence for `tg_head_right`. -/
theorem cHeadRight_implies_IR_headRight
    {image : ArchiveImage} {root : Nat} {result : U128}
    (hrun :
      cHeadRight root image.header.logScale
          image.header.reciprocalScale =
        some result) :
    headRight image root = .ok result :=
  specHeadRight_implies_IR_headRight
    (cHeadRight_refines hrun)

/-! ## One event's accumulator and strict-head arithmetic -/

/-- Values committed only after all one-event arithmetic calls and the strict
comparison have succeeded. -/
structure EventArithmeticResult where
  weighted : U128
  psi : U128
  left : U128
  right : U128
  deriving Repr, DecidableEq

/-- C helper-call order after reciprocal computation and event validation. -/
def cEventArithmetic
    (weightedBefore psiBefore : U128)
    (logUpper logLower upperReciprocal root
      logScaleWord reciprocalScaleWord : Nat) :
    Option EventArithmeticResult := do
  let upperLog ← U128.ofWord logUpper
  let term ←
    CPrimitives.mulWordChecked upperLog upperReciprocal
  let weighted ←
    CPrimitives.addChecked weightedBefore term
  let lowerLog ← U128.ofWord logLower
  let psi ← CPrimitives.addChecked psiBefore lowerLog
  let left ← CPrimitives.mulWordChecked weighted 1250
  let right ←
    cHeadRight root logScaleWord reciprocalScaleWord
  if CPrimitives.compare left right = .lt then
    some ⟨weighted, psi, left, right⟩
  else
    none

/-- The same composition using the architecture-neutral operations of
`IR.step`. -/
def specEventArithmetic
    (weightedBefore psiBefore : U128)
    (logUpper logLower upperReciprocal root
      logScaleWord reciprocalScaleWord : Nat) :
    Option EventArithmeticResult := do
  let upperLog ← U128.ofWord logUpper
  let term ← U128.mulWordChecked upperLog upperReciprocal
  let weighted ← U128.addChecked weightedBefore term
  let lowerLog ← U128.ofWord logLower
  let psi ← U128.addChecked psiBefore lowerLog
  let left ← U128.mulWordChecked weighted 1250
  let right ←
    specHeadRight root logScaleWord reciprocalScaleWord
  if left.lessThan right = true then
    some ⟨weighted, psi, left, right⟩
  else
    none

theorem cEventArithmetic_refines
    {weightedBefore psiBefore : U128}
    {logUpper logLower upperReciprocal root
      logScaleWord reciprocalScaleWord : Nat}
    {result : EventArithmeticResult}
    (hweightedBefore : weightedBefore.Valid)
    (hpsiBefore : psiBefore.Valid)
    (hrun :
      cEventArithmetic weightedBefore psiBefore
          logUpper logLower upperReciprocal root
          logScaleWord reciprocalScaleWord =
        some result) :
    specEventArithmetic weightedBefore psiBefore
        logUpper logLower upperReciprocal root
        logScaleWord reciprocalScaleWord =
      some result := by
  unfold cEventArithmetic at hrun
  rcases optionBind_some hrun with
    ⟨upperLog, hupperLog, hrun⟩
  have hupperLogValid := (U128.ofWord_sound hupperLog).2.1
  rcases optionBind_some hrun with ⟨term, hterm, hrun⟩
  have htermSpec :
      U128.mulWordChecked upperLog upperReciprocal = some term :=
    CPrimitives.mulWordChecked_refines hupperLogValid hterm
  have htermValid := (U128.mulWordChecked_sound htermSpec).2.1
  rcases optionBind_some hrun with
    ⟨weighted, hweighted, hrun⟩
  have hweightedSpec :
      U128.addChecked weightedBefore term = some weighted :=
    CPrimitives.addChecked_refines
      hweightedBefore htermValid hweighted
  have hweightedValid :=
    (U128.addChecked_sound hweightedSpec).1
  rcases optionBind_some hrun with
    ⟨lowerLog, hlowerLog, hrun⟩
  have hlowerLogValid := (U128.ofWord_sound hlowerLog).2.1
  rcases optionBind_some hrun with ⟨psi, hpsi, hrun⟩
  have hpsiSpec :
      U128.addChecked psiBefore lowerLog = some psi :=
    CPrimitives.addChecked_refines
      hpsiBefore hlowerLogValid hpsi
  have hpsiValid := (U128.addChecked_sound hpsiSpec).1
  rcases optionBind_some hrun with ⟨left, hleft, hrun⟩
  have hleftSpec :
      U128.mulWordChecked weighted 1250 = some left :=
    CPrimitives.mulWordChecked_refines hweightedValid hleft
  have hleftValid :=
    (U128.mulWordChecked_sound hleftSpec).2.1
  rcases optionBind_some hrun with ⟨right, hright, hstrict⟩
  have hrightSpec :
      specHeadRight root logScaleWord reciprocalScaleWord =
        some right :=
    cHeadRight_refines hright
  have hrightValid :
      right.Valid := by
    unfold specHeadRight at hrightSpec
    rcases optionBind_some hrightSpec with
      ⟨_start, _hstart, hrightSpec⟩
    rcases optionBind_some hrightSpec with
      ⟨_withConstant, _hconstant, hrightSpec⟩
    rcases optionBind_some hrightSpec with
      ⟨_withLogScale, _hlogScale, hrightSpec⟩
    exact (U128.mulWordChecked_sound hrightSpec).2.1
  by_cases hcompare : CPrimitives.compare left right = .lt
  · simp only [hcompare, if_true] at hstrict
    have hlessNat : left.toNat < right.toNat :=
      (CPrimitives.compare_eq_lt_iff hleftValid hrightValid).1
        hcompare
    have hless : left.lessThan right = true :=
      U128.lessThan_eq_true.2 hlessNat
    have htail :
        (if left.lessThan right = true then
          some ⟨weighted, psi, left, right⟩
        else
          none) = some result := by
      rw [if_pos hless]
      exact hstrict
    unfold specEventArithmetic
    exact Option.bind_eq_some_iff.mpr
      ⟨upperLog, hupperLog, Option.bind_eq_some_iff.mpr
        ⟨term, htermSpec, Option.bind_eq_some_iff.mpr
          ⟨weighted, hweightedSpec, Option.bind_eq_some_iff.mpr
            ⟨lowerLog, hlowerLog, Option.bind_eq_some_iff.mpr
              ⟨psi, hpsiSpec, Option.bind_eq_some_iff.mpr
                ⟨left, hleftSpec, Option.bind_eq_some_iff.mpr
                  ⟨right, hrightSpec, htail⟩⟩⟩⟩⟩⟩⟩
  · simp only [hcompare, if_false] at hstrict
    cases hstrict

structure EventArithmeticFacts
    (weightedBefore psiBefore : U128)
    (logUpper logLower upperReciprocal root
      logScaleWord reciprocalScaleWord : Nat)
    (result : EventArithmeticResult) : Prop where
  weighted :
    result.weighted.toNat =
      weightedBefore.toNat + logUpper * upperReciprocal
  psi :
    result.psi.toNat = psiBefore.toNat + logLower
  left :
    result.left.toNat = result.weighted.toNat * 1250
  right :
    result.right.toNat =
      root * 2501 * logScaleWord * reciprocalScaleWord
  strict : result.left.toNat < result.right.toNat

theorem specEventArithmetic_facts
    {weightedBefore psiBefore : U128}
    {logUpper logLower upperReciprocal root
      logScaleWord reciprocalScaleWord : Nat}
    {result : EventArithmeticResult}
    (hrun :
      specEventArithmetic weightedBefore psiBefore
          logUpper logLower upperReciprocal root
          logScaleWord reciprocalScaleWord =
        some result) :
    EventArithmeticFacts weightedBefore psiBefore
      logUpper logLower upperReciprocal root
      logScaleWord reciprocalScaleWord result := by
  unfold specEventArithmetic at hrun
  rcases optionBind_some hrun with
    ⟨upperLog, hupperLog, hrun⟩
  rcases optionBind_some hrun with ⟨term, hterm, hrun⟩
  rcases optionBind_some hrun with
    ⟨weighted, hweighted, hrun⟩
  rcases optionBind_some hrun with
    ⟨lowerLog, hlowerLog, hrun⟩
  rcases optionBind_some hrun with ⟨psi, hpsi, hrun⟩
  rcases optionBind_some hrun with ⟨left, hleft, hrun⟩
  rcases optionBind_some hrun with ⟨right, hright, hstrict⟩
  by_cases hless : left.lessThan right = true
  · simp only [hless, if_true] at hstrict
    have hresult :
        EventArithmeticResult.mk weighted psi left right = result :=
      Option.some.inj hstrict
    cases hresult
    exact {
      weighted := by
        rw [(U128.addChecked_sound hweighted).2,
          (U128.mulWordChecked_sound hterm).2.2,
          (U128.ofWord_sound hupperLog).2.2]
      psi := by
        rw [(U128.addChecked_sound hpsi).2,
          (U128.ofWord_sound hlowerLog).2.2]
      left := (U128.mulWordChecked_sound hleft).2.2
      right := specHeadRight_value hright
      strict := U128.lessThan_eq_true.1 hless
    }
  · simp only [hless] at hstrict
    cases hstrict

theorem cEventArithmetic_facts
    {weightedBefore psiBefore : U128}
    {logUpper logLower upperReciprocal root
      logScaleWord reciprocalScaleWord : Nat}
    {result : EventArithmeticResult}
    (hweightedBefore : weightedBefore.Valid)
    (hpsiBefore : psiBefore.Valid)
    (hrun :
      cEventArithmetic weightedBefore psiBefore
          logUpper logLower upperReciprocal root
          logScaleWord reciprocalScaleWord =
        some result) :
    EventArithmeticFacts weightedBefore psiBefore
      logUpper logLower upperReciprocal root
      logScaleWord reciprocalScaleWord result :=
  specEventArithmetic_facts
    (cEventArithmetic_refines hweightedBefore hpsiBefore hrun)

/-! ## Endpoint anchor arithmetic -/

/-- C helper-call composition in `tg_sq218_anchor_v2`, after the integer
square-root and lower-reciprocal stages have succeeded. -/
def cAnchorArithmetic
    (weighted psi : U128)
    (lowerReciprocal root logScaleWord reciprocalScaleWord : Nat) :
    Option U128 := do
  let correction ←
    CPrimitives.mulWordChecked psi lowerReciprocal
  let right ← cHeadRight root logScaleWord reciprocalScaleWord
  if CPrimitives.compare weighted correction = .lt then
    let difference ←
      CPrimitives.subChecked correction weighted
    let extra ← CPrimitives.mulWordChecked difference 2500
    CPrimitives.addChecked right extra
  else
    let difference ←
      CPrimitives.subChecked weighted correction
    let left ← CPrimitives.mulWordChecked difference 2500
    if CPrimitives.compare left right = .lt then
      CPrimitives.subChecked right left
    else
      none

/-- Architecture-neutral spelling of the public `IR.anchorSlack` arithmetic
after root and reciprocal computation. -/
def specAnchorArithmetic
    (weighted psi : U128)
    (lowerReciprocal root logScaleWord reciprocalScaleWord : Nat) :
    Option U128 := do
  let correction ← U128.mulWordChecked psi lowerReciprocal
  let right ← specHeadRight root logScaleWord reciprocalScaleWord
  if correction.toNat ≤ weighted.toNat then
    let difference ← U128.subChecked weighted correction
    let left ← U128.mulWordChecked difference 2500
    if left.lessThan right = true then
      U128.subChecked right left
    else
      none
  else
    let difference ← U128.subChecked correction weighted
    let extra ← U128.mulWordChecked difference 2500
    U128.addChecked right extra

theorem cAnchorArithmetic_refines
    {weighted psi : U128}
    {lowerReciprocal root logScaleWord reciprocalScaleWord : Nat}
    {slack : U128}
    (hweighted : weighted.Valid)
    (hpsi : psi.Valid)
    (hrun :
      cAnchorArithmetic weighted psi lowerReciprocal root
          logScaleWord reciprocalScaleWord =
        some slack) :
    specAnchorArithmetic weighted psi lowerReciprocal root
        logScaleWord reciprocalScaleWord =
      some slack := by
  unfold cAnchorArithmetic at hrun
  rcases optionBind_some hrun with
    ⟨correction, hcorrection, hrun⟩
  have hcorrectionSpec :
      U128.mulWordChecked psi lowerReciprocal = some correction :=
    CPrimitives.mulWordChecked_refines hpsi hcorrection
  have hcorrectionValid :=
    (U128.mulWordChecked_sound hcorrectionSpec).2.1
  rcases optionBind_some hrun with ⟨right, hright, hrun⟩
  have hrightSpec :
      specHeadRight root logScaleWord reciprocalScaleWord =
        some right :=
    cHeadRight_refines hright
  have hrightValid : right.Valid := by
    unfold specHeadRight at hrightSpec
    rcases optionBind_some hrightSpec with
      ⟨_start, _hstart, hrightSpec⟩
    rcases optionBind_some hrightSpec with
      ⟨_withConstant, _hconstant, hrightSpec⟩
    rcases optionBind_some hrightSpec with
      ⟨_withLogScale, _hlogScale, hrightSpec⟩
    exact (U128.mulWordChecked_sound hrightSpec).2.1
  by_cases hbranch :
      CPrimitives.compare weighted correction = .lt
  · simp only [hbranch, if_true] at hrun
    have hweightedLt : weighted.toNat < correction.toNat :=
      (CPrimitives.compare_eq_lt_iff hweighted hcorrectionValid).1
        hbranch
    have hnotBelow : ¬correction.toNat ≤ weighted.toNat :=
      Nat.not_le_of_gt hweightedLt
    rcases optionBind_some hrun with
      ⟨difference, hdifference, hrun⟩
    have hdifferenceSpec :
        U128.subChecked correction weighted = some difference :=
      CPrimitives.subChecked_refines
        hcorrectionValid hweighted hdifference
    have hdifferenceValid :=
      (U128.subChecked_sound hdifferenceSpec).1
    rcases optionBind_some hrun with ⟨extra, hextra, hslack⟩
    have hextraSpec :
        U128.mulWordChecked difference 2500 = some extra :=
      CPrimitives.mulWordChecked_refines
        hdifferenceValid hextra
    have hextraValid :=
      (U128.mulWordChecked_sound hextraSpec).2.1
    have hslackSpec :
        U128.addChecked right extra = some slack :=
      CPrimitives.addChecked_refines
        hrightValid hextraValid hslack
    have htail :
        (if correction.toNat ≤ weighted.toNat then
          do
            let difference ← U128.subChecked weighted correction
            let left ← U128.mulWordChecked difference 2500
            if left.lessThan right = true then
              U128.subChecked right left
            else
              none
        else
          do
            let difference ← U128.subChecked correction weighted
            let extra ← U128.mulWordChecked difference 2500
            U128.addChecked right extra) = some slack := by
      rw [if_neg hnotBelow]
      exact Option.bind_eq_some_iff.mpr
        ⟨difference, hdifferenceSpec, Option.bind_eq_some_iff.mpr
          ⟨extra, hextraSpec, hslackSpec⟩⟩
    unfold specAnchorArithmetic
    exact Option.bind_eq_some_iff.mpr
      ⟨correction, hcorrectionSpec, Option.bind_eq_some_iff.mpr
        ⟨right, hrightSpec, htail⟩⟩
  · have hnotLt : ¬weighted.toNat < correction.toNat := by
      intro hlt
      exact hbranch
        ((CPrimitives.compare_eq_lt_iff
          hweighted hcorrectionValid).2 hlt)
    have hbelow : correction.toNat ≤ weighted.toNat :=
      Nat.le_of_not_gt hnotLt
    simp only [hbranch, if_false] at hrun
    rcases optionBind_some hrun with
      ⟨difference, hdifference, hrun⟩
    have hdifferenceSpec :
        U128.subChecked weighted correction = some difference :=
      CPrimitives.subChecked_refines
        hweighted hcorrectionValid hdifference
    have hdifferenceValid :=
      (U128.subChecked_sound hdifferenceSpec).1
    rcases optionBind_some hrun with ⟨left, hleft, hrun⟩
    have hleftSpec :
        U128.mulWordChecked difference 2500 = some left :=
      CPrimitives.mulWordChecked_refines
        hdifferenceValid hleft
    have hleftValid :=
      (U128.mulWordChecked_sound hleftSpec).2.1
    by_cases hstrict :
        CPrimitives.compare left right = .lt
    · simp only [hstrict, if_true] at hrun
      have hleftLt : left.toNat < right.toNat :=
        (CPrimitives.compare_eq_lt_iff
          hleftValid hrightValid).1 hstrict
      have hless : left.lessThan right = true :=
        U128.lessThan_eq_true.2 hleftLt
      have hslackSpec :
          U128.subChecked right left = some slack :=
        CPrimitives.subChecked_refines
          hrightValid hleftValid hrun
      have hstrictTail :
          (if left.lessThan right = true then
            U128.subChecked right left
          else
            none) = some slack := by
        rw [if_pos hless]
        exact hslackSpec
      have htail :
          (if correction.toNat ≤ weighted.toNat then
            do
              let difference ←
                U128.subChecked weighted correction
              let left ← U128.mulWordChecked difference 2500
              if left.lessThan right = true then
                U128.subChecked right left
              else
                none
          else
            do
              let difference ←
                U128.subChecked correction weighted
              let extra ← U128.mulWordChecked difference 2500
              U128.addChecked right extra) = some slack := by
        rw [if_pos hbelow]
        exact Option.bind_eq_some_iff.mpr
          ⟨difference, hdifferenceSpec, Option.bind_eq_some_iff.mpr
            ⟨left, hleftSpec, hstrictTail⟩⟩
      unfold specAnchorArithmetic
      exact Option.bind_eq_some_iff.mpr
        ⟨correction, hcorrectionSpec, Option.bind_eq_some_iff.mpr
          ⟨right, hrightSpec, htail⟩⟩
    · simp only [hstrict] at hrun
      cases hrun

private def exceptAnchorArithmetic
    (image : ArchiveImage) (state : ScanState) :
    Except Reject U128 := do
  let root := Nat.sqrt image.header.bound
  let lowerReciprocal :=
    TGComputeContracts.Sqrt218.reciprocalLower
      image.header.bound root
  let lowerWord ←
    fromOverflow (checkedWord lowerReciprocal)
  let correction ←
    fromOverflow
      (U128.mulWordChecked state.psiLower lowerWord)
  let right ← exceptHeadRight image root
  if correction.toNat ≤ state.weightedUpper.toNat then
    let difference ←
      fromOverflow
        (U128.subChecked state.weightedUpper correction)
    let left ←
      fromOverflow (U128.mulWordChecked difference 2500)
    if left.lessThan right = true then
      fromOverflow (U128.subChecked right left)
    else
      .error .strictGuardFailed
  else
    let difference ←
      fromOverflow
        (U128.subChecked correction state.weightedUpper)
    let extra ←
      fromOverflow (U128.mulWordChecked difference 2500)
    fromOverflow (U128.addChecked right extra)

private theorem IR_anchorSlack_eq_exceptAnchorArithmetic
    (image : ArchiveImage) (state : ScanState) :
    anchorSlack image state =
      exceptAnchorArithmetic image state := by
  rfl

/-- Exact successful-outcome correspondence between the public
architecture-neutral anchor composition and `IR.anchorSlack`.

The initial `checkedWord` is recovered from success of the correction
multiplication.  In the C-negative branch,
`weighted < correction` is exactly `¬ correction ≤ weighted`, so it selects
the IR `else` branch; the other C branch selects the IR `then` branch. -/
theorem specAnchorArithmetic_implies_IR_anchorSlack
    {image : ArchiveImage} {state : ScanState} {slack : U128}
    (hrun :
      specAnchorArithmetic
          state.weightedUpper state.psiLower
          (TGComputeContracts.Sqrt218.reciprocalLower
            image.header.bound (Nat.sqrt image.header.bound))
          (Nat.sqrt image.header.bound)
          image.header.logScale image.header.reciprocalScale =
        some slack) :
    anchorSlack image state = .ok slack := by
  let root := Nat.sqrt image.header.bound
  let lowerReciprocal :=
    TGComputeContracts.Sqrt218.reciprocalLower
      image.header.bound root
  change
    specAnchorArithmetic
        state.weightedUpper state.psiLower
        lowerReciprocal root image.header.logScale
        image.header.reciprocalScale =
      some slack at hrun
  unfold specAnchorArithmetic at hrun
  rcases optionBind_some hrun with
    ⟨correction, hcorrection, hrun⟩
  rcases optionBind_some hrun with
    ⟨right, hright, hrun⟩
  have hlowerFit : lowerReciprocal < limbBase :=
    (U128.mulWordChecked_sound hcorrection).1
  have hlowerWord :
      checkedWord lowerReciprocal = some lowerReciprocal := by
    simp [checkedWord, hlowerFit]
  have hlowerExcept :
      fromOverflow (checkedWord lowerReciprocal) =
        .ok lowerReciprocal := by
    rw [hlowerWord]
    rfl
  have hcorrectionExcept :
      fromOverflow
          (U128.mulWordChecked state.psiLower lowerReciprocal) =
        .ok correction := by
    rw [hcorrection]
    rfl
  have hrightIR :
      headRight image root = .ok right :=
    specHeadRight_implies_IR_headRight hright
  have hrightExcept :
      exceptHeadRight image root = .ok right := by
    rw [← IR_headRight_eq_exceptHeadRight]
    exact hrightIR
  have htail :
      (if correction.toNat ≤ state.weightedUpper.toNat then
        do
          let difference ←
            fromOverflow
              (U128.subChecked state.weightedUpper correction)
          let left ←
            fromOverflow
              (U128.mulWordChecked difference 2500)
          if left.lessThan right = true then
            fromOverflow (U128.subChecked right left)
          else
            .error .strictGuardFailed
      else
        do
          let difference ←
            fromOverflow
              (U128.subChecked correction state.weightedUpper)
          let extra ←
            fromOverflow
              (U128.mulWordChecked difference 2500)
          fromOverflow (U128.addChecked right extra)) =
        .ok slack := by
    by_cases hbelow :
        correction.toNat ≤ state.weightedUpper.toNat
    · simp only [hbelow, if_true] at hrun ⊢
      rcases optionBind_some hrun with
        ⟨difference, hdifference, hrun⟩
      rcases optionBind_some hrun with
        ⟨left, hleft, hrun⟩
      by_cases hstrict : left.lessThan right = true
      · simp only [hstrict, if_true] at hrun
        have hdifferenceExcept :
            fromOverflow
                (U128.subChecked
                  state.weightedUpper correction) =
              .ok difference := by
          rw [hdifference]
          rfl
        have hleftExcept :
            fromOverflow
                (U128.mulWordChecked difference 2500) =
              .ok left := by
          rw [hleft]
          rfl
        have hslackExcept :
            fromOverflow (U128.subChecked right left) =
              .ok slack := by
          rw [hrun]
          rfl
        have hstrictExcept :
            (if left.lessThan right = true then
              fromOverflow (U128.subChecked right left)
            else
              .error .strictGuardFailed) =
              .ok slack := by
          rw [if_pos hstrict]
          exact hslackExcept
        exact exceptBind_ok_of hdifferenceExcept
          (exceptBind_ok_of hleftExcept hstrictExcept)
      · simp only [hstrict] at hrun
        cases hrun
    · simp only [hbelow, if_false] at hrun ⊢
      rcases optionBind_some hrun with
        ⟨difference, hdifference, hrun⟩
      rcases optionBind_some hrun with
        ⟨extra, hextra, hslack⟩
      have hdifferenceExcept :
          fromOverflow
              (U128.subChecked
                correction state.weightedUpper) =
            .ok difference := by
        rw [hdifference]
        rfl
      have hextraExcept :
          fromOverflow
              (U128.mulWordChecked difference 2500) =
            .ok extra := by
        rw [hextra]
        rfl
      have hslackExcept :
          fromOverflow (U128.addChecked right extra) =
            .ok slack := by
        rw [hslack]
        rfl
      exact exceptBind_ok_of hdifferenceExcept
        (exceptBind_ok_of hextraExcept hslackExcept)
  rw [IR_anchorSlack_eq_exceptAnchorArithmetic]
  unfold exceptAnchorArithmetic
  exact exceptBind_ok_of hlowerExcept
    (exceptBind_ok_of hcorrectionExcept
      (exceptBind_ok_of hrightExcept htail))

/-- Direct source-to-IR correspondence for the arithmetic portion of
`tg_sq218_anchor_v2`, with the exact IR root, reciprocal, and header words. -/
theorem cAnchorArithmetic_implies_IR_anchorSlack
    {image : ArchiveImage} {state : ScanState} {slack : U128}
    (hweighted : state.weightedUpper.Valid)
    (hpsi : state.psiLower.Valid)
    (hrun :
      cAnchorArithmetic
          state.weightedUpper state.psiLower
          (TGComputeContracts.Sqrt218.reciprocalLower
            image.header.bound (Nat.sqrt image.header.bound))
          (Nat.sqrt image.header.bound)
          image.header.logScale image.header.reciprocalScale =
        some slack) :
    anchorSlack image state = .ok slack :=
  specAnchorArithmetic_implies_IR_anchorSlack
    (cAnchorArithmetic_refines hweighted hpsi hrun)

/-- The strict integer inequality common to `IR.anchorSlack` and
`TGComputeContracts.Sqrt218.anchorOK`, with the reciprocal and scales left as
parameters. -/
def AnchorGuard
    (weighted psi : U128)
    (lowerReciprocal root logScaleWord reciprocalScaleWord : Nat) : Prop :=
  (2500 : Int) *
      ((weighted.toNat : Int) -
        (psi.toNat * lowerReciprocal : Nat)) <
    (root * 2501 * logScaleWord * reciprocalScaleWord : Nat)

theorem specAnchorArithmetic_guard
    {weighted psi : U128}
    {lowerReciprocal root logScaleWord reciprocalScaleWord : Nat}
    {slack : U128}
    (hrun :
      specAnchorArithmetic weighted psi lowerReciprocal root
          logScaleWord reciprocalScaleWord =
        some slack) :
    AnchorGuard weighted psi lowerReciprocal root
      logScaleWord reciprocalScaleWord := by
  unfold specAnchorArithmetic at hrun
  rcases optionBind_some hrun with
    ⟨correction, hcorrection, hrun⟩
  rcases optionBind_some hrun with ⟨right, hright, hrun⟩
  have hcorrectionNat :
      correction.toNat = psi.toNat * lowerReciprocal :=
    (U128.mulWordChecked_sound hcorrection).2.2
  have hrightNat :
      right.toNat =
        root * 2501 * logScaleWord * reciprocalScaleWord :=
    specHeadRight_value hright
  by_cases hbelow : correction.toNat ≤ weighted.toNat
  · simp only [hbelow, if_true] at hrun
    rcases optionBind_some hrun with
      ⟨difference, hdifference, hrun⟩
    rcases optionBind_some hrun with ⟨left, hleft, hrun⟩
    by_cases hstrict : left.lessThan right = true
    · simp only [hstrict, if_true] at hrun
      have hdifferenceNat :=
        (U128.subChecked_sound hdifference).2.2
      have hleftNat :=
        (U128.mulWordChecked_sound hleft).2.2
      have hleftLt : left.toNat < right.toNat :=
        U128.lessThan_eq_true.1 hstrict
      unfold AnchorGuard
      have hnat :
          2500 * (weighted.toNat - correction.toNat) <
            right.toNat := by
        calc
          2500 * (weighted.toNat - correction.toNat) =
              difference.toNat * 2500 := by
            rw [hdifferenceNat]
            omega
          _ = left.toNat := hleftNat.symm
          _ < right.toNat := hleftLt
      have hint :
          ((2500 * (weighted.toNat - correction.toNat) : Nat) : Int) <
            (right.toNat : Int) :=
        Int.ofNat_lt.2 hnat
      push_cast at hint
      rw [Int.ofNat_sub hbelow] at hint
      simpa only [hcorrectionNat, hrightNat] using hint
    · simp only [hstrict] at hrun
      cases hrun
  · have habove : weighted.toNat < correction.toNat :=
      Nat.lt_of_not_ge hbelow
    unfold AnchorGuard
    have hnegative :
        (weighted.toNat : Int) - (correction.toNat : Int) < 0 := by
      exact sub_neg.2 (Int.ofNat_lt.2 habove)
    have hrightNonnegative : (0 : Int) ≤ right.toNat :=
      Int.natCast_nonneg _
    rw [← hcorrectionNat, ← hrightNat]
    nlinarith

theorem cAnchorArithmetic_guard
    {weighted psi : U128}
    {lowerReciprocal root logScaleWord reciprocalScaleWord : Nat}
    {slack : U128}
    (hweighted : weighted.Valid)
    (hpsi : psi.Valid)
    (hrun :
      cAnchorArithmetic weighted psi lowerReciprocal root
          logScaleWord reciprocalScaleWord =
        some slack) :
    AnchorGuard weighted psi lowerReciprocal root
      logScaleWord reciprocalScaleWord :=
  specAnchorArithmetic_guard
    (cAnchorArithmetic_refines hweighted hpsi hrun)

/-- Specialization of the source-composition guard to the constants and
reciprocal used by `IR.anchorSlack`. -/
theorem cAnchorArithmetic_implies_anchorOK
    {image : ArchiveImage} {state : ScanState}
    {slack : U128}
    (hheader : headerCheck image = true)
    (hweighted : state.weightedUpper.Valid)
    (hpsi : state.psiLower.Valid)
    (hrun :
      cAnchorArithmetic
          state.weightedUpper state.psiLower
          (TGComputeContracts.Sqrt218.reciprocalLower
            image.header.bound (Nat.sqrt image.header.bound))
          (Nat.sqrt image.header.bound)
          image.header.logScale image.header.reciprocalScale =
        some slack) :
    TGComputeContracts.Sqrt218.anchorOK
        image.header.bound
        state.weightedUpper.toNat
        state.psiLower.toNat = true := by
  simp only [headerCheck, decide_eq_true_eq] at hheader
  have hlogScale :
      image.header.logScale =
        TGComputeContracts.Sqrt218.scale := by
    exact hheader.2.2.2.2.2.1.trans rfl
  have hreciprocalScale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale := by
    exact hheader.2.2.2.2.2.2.1.trans rfl
  have hguard :=
    cAnchorArithmetic_guard hweighted hpsi hrun
  unfold TGComputeContracts.Sqrt218.anchorOK
  simp only [decide_eq_true_eq]
  unfold AnchorGuard at hguard
  rw [hlogScale, hreciprocalScale] at hguard
  norm_num [Int.natCast_mul] at hguard ⊢
  simpa only [Int.natCast_mul, mul_assoc, mul_comm,
    mul_left_comm] using hguard

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArithmeticRefinement
