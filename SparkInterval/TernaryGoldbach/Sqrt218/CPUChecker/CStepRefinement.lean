/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CArithmeticRefinement

/-!
# Source-level C scan-step refinement for the Sqrt218 checker

This module models the successful source path through
`tg_sq218_scan_step_v2`.  In particular, it covers the source spellings of:

* `tg_u64_mul_checked`;
* the binary loop in `tg_pow_u64_checked`;
* `tg_floor_sqrt_ok`;
* `tg_reciprocals`; and
* one decoded, accepted scan step.

The byte parser and record-address calculation remain separate.  A decoded
step therefore carries explicit `List.getElem?` equalities connecting the
records returned by C's accessors to the architecture-neutral `ArchiveImage`.
Likewise, unsigned C types are represented by explicit word bounds.

All results are data-independent.  This file opens no certificate and does no
closed production reduction.  It is a source-semantics layer only: compiler,
ABI, executable, loader, and processor refinement are deliberately absent.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CStepRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPrimitives
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArithmeticRefinement

def uint32Base : Nat := 2 ^ 32

private theorem optionBind_some {α β : Type}
    {first : Option α} {rest : α → Option β} {result : β}
    (hbind : first >>= rest = some result) :
    ∃ value, first = some value ∧ rest value = some result :=
  Option.bind_eq_some_iff.mp hbind

/-! ## Exact checked `uint64_t` multiplication -/

/-- Source spelling of `tg_u64_mul_checked`.

The returned product is written as a natural because the rejecting branch
rules out C wraparound.  The two explicit `< limbBase` hypotheses in the
soundness theorem are the semantic interpretation of the two `uint64_t`
parameters. -/
def cWordMulChecked (left right : Nat) : Option Nat :=
  CPrimitives.wordMulChecked left right

theorem cWordMulChecked_sound
    {left right result : Nat}
    (_hleft : left < limbBase)
    (_hright : right < limbBase)
    (hrun : cWordMulChecked left right = some result) :
    result < limbBase ∧ result = left * right :=
  CPrimitives.wordMulChecked_sound _hleft _hright hrun

/-! ## Binary checked power -/

/-- The source loop of `tg_pow_u64_checked`.

`remaining % 2` models `remaining & 1`, and division by two models the
unsigned right shift.  The squaring call is skipped after the shift reaches
zero, exactly as in the C source. -/
def cPowLoop
    (result factor remaining : Nat) : Option Nat :=
  if hzero : remaining = 0 then
    some result
  else do
    let result' ←
      if remaining % 2 ≠ 0 then
        cWordMulChecked result factor
      else
        some result
    let remaining' := remaining / 2
    let factor' ←
      if remaining' ≠ 0 then
        cWordMulChecked factor factor
      else
        some factor
    cPowLoop result' factor' remaining'
termination_by remaining
decreasing_by
  exact Nat.div_lt_self
    (Nat.zero_lt_of_ne_zero hzero) (by omega)

/-- Entry state of `tg_pow_u64_checked`. -/
def cPowChecked (base exponent : Nat) : Option Nat :=
  cPowLoop 1 base exponent

theorem cPowLoop_sound
    {result factor remaining output : Nat}
    (hresult : result < limbBase)
    (hfactor : factor < limbBase)
    (hrun : cPowLoop result factor remaining = some output) :
    output < limbBase ∧
      output = result * factor ^ remaining := by
  induction remaining using Nat.strong_induction_on generalizing
      result factor output with
  | h remaining ih =>
      rw [cPowLoop] at hrun
      by_cases hzero : remaining = 0
      · rw [dif_pos hzero] at hrun
        cases hrun
        subst remaining
        simp [hresult]
      · rw [dif_neg hzero] at hrun
        by_cases hodd : remaining % 2 ≠ 0
        · rw [if_pos hodd] at hrun
          rcases optionBind_some hrun with
            ⟨result', hresultRun, hrun⟩
          have hresultSound :=
            cWordMulChecked_sound hresult hfactor hresultRun
          let half := remaining / 2
          by_cases hhalfZero : half = 0
          · have hhalfZero' : remaining / 2 = 0 := by
              simpa only [half] using hhalfZero
            change
              (if remaining / 2 ≠ 0 then
                cWordMulChecked factor factor >>= fun factor' =>
                  cPowLoop result' factor' (remaining / 2)
              else
                cPowLoop result' factor (remaining / 2)) =
                some output at hrun
            rw [if_neg (by simpa using hhalfZero')] at hrun
            have hrun' :
                cPowLoop result' factor half = some output := by
              simpa only [half] using hrun
            have hrecursive :=
              ih half
                (Nat.div_lt_self
                  (Nat.zero_lt_of_ne_zero hzero) (by omega))
                hresultSound.1 hfactor hrun'
            have hmodOne : remaining % 2 = 1 := by
              rcases Nat.mod_two_eq_zero_or_one remaining with
                hmodZero | hmodOne
              · exact (hodd hmodZero).elim
              · exact hmodOne
            have hremaining : remaining = 1 := by
              have hdecomp := Nat.mod_add_div remaining 2
              dsimp only [half] at hhalfZero
              omega
            constructor
            · exact hrecursive.1
            · rw [hrecursive.2, hresultSound.2, hremaining]
              simp [hhalfZero]
          · have hhalfNe' : remaining / 2 ≠ 0 := by
              simpa only [half] using hhalfZero
            change
              (if remaining / 2 ≠ 0 then
                cWordMulChecked factor factor >>= fun factor' =>
                  cPowLoop result' factor' (remaining / 2)
              else
                cPowLoop result' factor (remaining / 2)) =
                some output at hrun
            rw [if_pos hhalfNe'] at hrun
            rcases optionBind_some hrun with
              ⟨factor', hfactorRun, hrun⟩
            have hfactorSound :=
              cWordMulChecked_sound hfactor hfactor hfactorRun
            have hrecursive :=
              ih half
                (Nat.div_lt_self
                  (Nat.zero_lt_of_ne_zero hzero) (by omega))
                hresultSound.1 hfactorSound.1 hrun
            have hmodOne : remaining % 2 = 1 := by
              rcases Nat.mod_two_eq_zero_or_one remaining with
                hmodZero | hmodOne
              · exact (hodd hmodZero).elim
              · exact hmodOne
            have hremaining :
                remaining = 2 * half + 1 := by
              have hdecomp := Nat.mod_add_div remaining 2
              dsimp only [half]
              omega
            constructor
            · exact hrecursive.1
            · rw [hrecursive.2, hresultSound.2,
                hfactorSound.2, hremaining, pow_add, pow_mul]
              ring
        · rw [if_neg hodd] at hrun
          let half := remaining / 2
          have hmodZero : remaining % 2 = 0 := by
            exact Nat.mod_two_not_eq_one.mp (by
              intro hmodOne
              exact hodd (by omega))
          have hhalfPos : 0 < half := by
            have hdecomp := Nat.mod_add_div remaining 2
            dsimp only [half]
            omega
          have hhalfNe :
              remaining / 2 ≠ 0 := by
            simpa only [half] using ne_of_gt hhalfPos
          change
            (if remaining / 2 ≠ 0 then
              cWordMulChecked factor factor >>= fun factor' =>
                cPowLoop result factor' (remaining / 2)
            else
              cPowLoop result factor (remaining / 2)) =
              some output at hrun
          rw [if_pos hhalfNe] at hrun
          rcases optionBind_some hrun with
            ⟨factor', hfactorRun, hrun⟩
          have hfactorSound :=
            cWordMulChecked_sound hfactor hfactor hfactorRun
          have hrecursive :=
            ih half
              (Nat.div_lt_self
                (Nat.zero_lt_of_ne_zero hzero) (by omega))
              hresult hfactorSound.1 hrun
          have hremaining : remaining = 2 * half := by
            have hdecomp := Nat.mod_add_div remaining 2
            dsimp only [half]
            omega
          constructor
          · exact hrecursive.1
          · rw [hrecursive.2, hfactorSound.2,
              hremaining, pow_mul]
            simp [pow_two]

theorem cPowChecked_value
    {base exponent output : Nat}
    (hbase : base < limbBase)
    (hrun : cPowChecked base exponent = some output) :
    output < limbBase ∧ output = base ^ exponent := by
  have hone : 1 < limbBase := by norm_num [limbBase]
  simpa [cPowChecked] using
    (cPowLoop_sound hone hbase hrun)

theorem checkedPowWord_eq_pow_of_fit
    {base exponent : Nat}
    (hbase : base < limbBase)
    (hpow : base ^ exponent < limbBase) :
    checkedPowWord base exponent = some (base ^ exponent) := by
  induction exponent with
  | zero =>
      simp [checkedPowWord, checkedWord, limbBase]
  | succ exponent ih =>
      have hprevious : base ^ exponent < limbBase := by
        by_cases hzero : base = 0
        · subst base
          cases exponent with
          | zero => norm_num [limbBase]
          | succ exponent => simp [limbBase_pos]
        · have hmono :
              base ^ exponent ≤ base ^ (exponent + 1) :=
            Nat.pow_le_pow_right
              (Nat.zero_lt_of_ne_zero hzero) (by omega)
          exact hmono.trans_lt (by
            simpa only [Nat.succ_eq_add_one] using hpow)
      have hpreviousRun := ih hprevious
      simp only [checkedPowWord, hpreviousRun]
      unfold checkedWordMul checkedWord
      have hpow' :
          base ^ exponent * base < limbBase := by
        simpa only [pow_succ] using hpow
      simp [hpow', pow_succ]

theorem cPowChecked_refines_checkedPowWord
    {base exponent output : Nat}
    (hbase : base < limbBase)
    (hrun : cPowChecked base exponent = some output) :
    checkedPowWord base exponent = some output := by
  have hsound := cPowChecked_value hbase hrun
  have hpow : base ^ exponent < limbBase := by
    rw [← hsound.2]
    exact hsound.1
  simpa only [hsound.2] using
    (checkedPowWord_eq_pow_of_fit hbase hpow)

/-! ## Exact successful square-root guard -/

/-- Successful truth value of `tg_floor_sqrt_ok`.

The `root = wordMax` rejection is retained even though, for a valid `value`,
the surrounding inequalities already make that case impossible. -/
def cFloorSqrtOK (value root : Nat) : Prop :=
  if root = 0 then
    value = 0
  else
    root ≤ value / root ∧
      root ≠ wordMax ∧
      value / (root + 1) < root + 1

theorem cFloorSqrtOK_eq_sqrt
    {value root : Nat}
    (hok : cFloorSqrtOK value root) :
    root = Nat.sqrt value := by
  unfold cFloorSqrtOK at hok
  by_cases hzero : root = 0
  · simp only [hzero, if_true] at hok
    rw [hzero, hok]
    simp
  · simp only [hzero, if_false] at hok
    have hrootPos : 0 < root := Nat.zero_lt_of_ne_zero hzero
    have hsquare : root * root ≤ value :=
      (Nat.le_div_iff_mul_le hrootPos).mp hok.1
    have hsuccessorPos : 0 < root + 1 := by omega
    have hnextSquare : value < (root + 1) * (root + 1) :=
      (Nat.div_lt_iff_lt_mul hsuccessorPos).mp hok.2.2
    have hlower : root ≤ Nat.sqrt value :=
      Nat.le_sqrt.mpr hsquare
    have hupper : Nat.sqrt value < root + 1 :=
      Nat.sqrt_lt.mpr hnextSquare
    omega

/-! ## Checked reciprocal construction -/

structure CReciprocals where
  lower : Nat
  upper : Nat
  deriving Repr, DecidableEq

/-- Source operation order in `tg_reciprocals`.

The initial null-pointer checks have no mathematical payload and are the
responsibility of the caller/ABI layer.  All arithmetic guards, including
the two nonzero denominators and the checked increment implementing ceiling
division, are retained here. -/
def cReciprocals
    (scaleWord value root : Nat) : Option CReciprocals := do
  if root = 0 then none else pure ()
  let square ← cWordMulChecked root root
  if square ≤ value then pure () else none
  let remainder := value - square
  let twiceRoot ← cWordMulChecked 2 root
  let twiceSquare ← cWordMulChecked 2 square
  let lowerNum ← cWordMulChecked scaleWord twiceRoot
  let lowerDen ← CPrimitives.wordAddChecked twiceSquare remainder
  if lowerDen = 0 then none else pure ()
  let fourSquare ← cWordMulChecked 4 square
  let upperFactor ←
    CPrimitives.wordAddChecked fourSquare remainder
  let upperNum ← cWordMulChecked scaleWord upperFactor
  let threeRemainder ← cWordMulChecked 3 remainder
  let upperDenFactor ←
    CPrimitives.wordAddChecked fourSquare threeRemainder
  let upperDen ← cWordMulChecked root upperDenFactor
  if upperDen = 0 then none else pure ()
  let lower := lowerNum / lowerDen
  let quotient := upperNum / upperDen
  let residue := upperNum % upperDen
  let upper ←
    if residue ≠ 0 then
      CPrimitives.wordAddChecked quotient 1
    else
      some quotient
  some ⟨lower, upper⟩

/-- Quotient/remainder spelling used by C equals the kernel's natural ceiling
division when the denominator is positive. -/
theorem ceilDiv_eq_quotient
    {num den : Nat} (hden : 0 < den) :
    TGComputeContracts.Sqrt218.ceilDiv num den =
      if num % den = 0 then num / den else num / den + 1 := by
  unfold TGComputeContracts.Sqrt218.ceilDiv
  have hmodLt : num % den < den := Nat.mod_lt _ hden
  have hdecomp : den * (num / den) + num % den = num :=
    Nat.div_add_mod num den
  have hdecomp' :
      (num / den) * den + num % den = num := by
    simpa only [Nat.mul_comm] using hdecomp
  have hpred : den - 1 + 1 = den := by omega
  by_cases hmod : num % den = 0
  · simp only [hmod, if_true]
    have hquotient : (num / den) * den = num := by
      omega
    apply Nat.div_eq_of_lt_le
    · rw [hquotient]
      omega
    · simp only [add_mul, one_mul]
      rw [hquotient]
      omega
  · simp only [hmod, if_false]
    have hmodPos : 0 < num % den := Nat.zero_lt_of_ne_zero hmod
    apply Nat.div_eq_of_lt_le
    · simp only [add_mul, one_mul]
      omega
    · simp only [add_mul, one_mul]
      omega

structure CReciprocalFacts
    (scaleWord value root : Nat) (result : CReciprocals) : Prop where
  lower :
    result.lower =
      scaleWord * (2 * root) /
        (2 * root ^ 2 + (value - root ^ 2))
  upper :
    result.upper =
      TGComputeContracts.Sqrt218.ceilDiv
        (scaleWord * (4 * root ^ 2 + (value - root ^ 2)))
        (root * (4 * root ^ 2 + 3 * (value - root ^ 2)))

theorem cReciprocals_facts
    {scaleWord value root : Nat} {result : CReciprocals}
    (hscale : scaleWord < limbBase)
    (hvalue : value < limbBase)
    (hroot : root < limbBase)
    (hrun : cReciprocals scaleWord value root = some result) :
    CReciprocalFacts scaleWord value root result := by
  unfold cReciprocals at hrun
  by_cases hrootZero : root = 0
  · simp only [hrootZero, if_true] at hrun
    contradiction
  · simp only [hrootZero, if_false] at hrun
    rcases optionBind_some hrun with
      ⟨square, hsquareRun, hrun⟩
    have hsquareSound :=
      cWordMulChecked_sound hroot hroot hsquareRun
    by_cases hsquareLe : square ≤ value
    · simp only [hsquareLe, if_true] at hrun
      let remainder := value - square
      have hremainderFits : remainder < limbBase := by
        dsimp only [remainder]
        omega
      rcases optionBind_some hrun with
        ⟨twiceRoot, htwiceRootRun, hrun⟩
      have htwoFits : 2 < limbBase := by norm_num [limbBase]
      have htwiceRootSound :=
        cWordMulChecked_sound htwoFits hroot htwiceRootRun
      rcases optionBind_some hrun with
        ⟨twiceSquare, htwiceSquareRun, hrun⟩
      have htwiceSquareSound :=
        cWordMulChecked_sound
          htwoFits hsquareSound.1 htwiceSquareRun
      rcases optionBind_some hrun with
        ⟨lowerNum, hlowerNumRun, hrun⟩
      have hlowerNumSound :=
        cWordMulChecked_sound
          hscale htwiceRootSound.1 hlowerNumRun
      rcases optionBind_some hrun with
        ⟨lowerDen, hlowerDenRun, hrun⟩
      have hlowerDenSound :=
        CPrimitives.wordAddChecked_sound
          htwiceSquareSound.1 hremainderFits hlowerDenRun
      by_cases hlowerDenZero : lowerDen = 0
      · simp only [hlowerDenZero, if_true] at hrun
        contradiction
      · simp only [hlowerDenZero, if_false] at hrun
        rcases optionBind_some hrun with
          ⟨fourSquare, hfourSquareRun, hrun⟩
        have hfourFits : 4 < limbBase := by norm_num [limbBase]
        have hfourSquareSound :=
          cWordMulChecked_sound
            hfourFits hsquareSound.1 hfourSquareRun
        rcases optionBind_some hrun with
          ⟨upperFactor, hupperFactorRun, hrun⟩
        have hupperFactorSound :=
          CPrimitives.wordAddChecked_sound
            hfourSquareSound.1 hremainderFits hupperFactorRun
        rcases optionBind_some hrun with
          ⟨upperNum, hupperNumRun, hrun⟩
        have hupperNumSound :=
          cWordMulChecked_sound
            hscale hupperFactorSound.1 hupperNumRun
        rcases optionBind_some hrun with
          ⟨threeRemainder, hthreeRemainderRun, hrun⟩
        have hthreeFits : 3 < limbBase := by norm_num [limbBase]
        have hthreeRemainderSound :=
          cWordMulChecked_sound
            hthreeFits hremainderFits hthreeRemainderRun
        rcases optionBind_some hrun with
          ⟨upperDenFactor, hupperDenFactorRun, hrun⟩
        have hupperDenFactorSound :=
          CPrimitives.wordAddChecked_sound
            hfourSquareSound.1 hthreeRemainderSound.1
            hupperDenFactorRun
        rcases optionBind_some hrun with
          ⟨upperDen, hupperDenRun, hrun⟩
        have hupperDenSound :=
          cWordMulChecked_sound
            hroot hupperDenFactorSound.1 hupperDenRun
        by_cases hupperDenZero : upperDen = 0
        · simp only [hupperDenZero, if_true] at hrun
          contradiction
        · simp only [hupperDenZero, if_false] at hrun
          let lower := lowerNum / lowerDen
          let quotient := upperNum / upperDen
          let residue := upperNum % upperDen
          have hquotientFits : quotient < limbBase := by
            dsimp only [quotient]
            exact
              (Nat.div_le_self upperNum upperDen).trans_lt
                hupperNumSound.1
          change
            (if residue ≠ 0 then
              CPrimitives.wordAddChecked quotient 1 >>= fun upper =>
                some ⟨lower, upper⟩
            else
              some quotient >>= fun upper =>
                some ⟨lower, upper⟩) =
                some result at hrun
          by_cases hresidueZero : residue = 0
          · rw [if_neg (by simpa using hresidueZero)] at hrun
            change some ⟨lower, quotient⟩ = some result at hrun
            have hresult :
                CReciprocals.mk lower quotient = result :=
              Option.some.inj hrun
            rw [← hresult]
            have hresidueZero' : upperNum % upperDen = 0 := by
              simpa only [residue] using hresidueZero
            have hupperCeil :
                quotient =
                  TGComputeContracts.Sqrt218.ceilDiv
                    upperNum upperDen := by
              rw [ceilDiv_eq_quotient
                (Nat.zero_lt_of_ne_zero hupperDenZero)]
              simp only [hresidueZero', if_true, quotient]
            constructor
            · dsimp only [lower]
              rw [hlowerNumSound.2, hlowerDenSound.2,
                htwiceRootSound.2, htwiceSquareSound.2,
                hsquareSound.2]
              simp only [remainder, hsquareSound.2, pow_two]
            · rw [hupperCeil, hupperNumSound.2, hupperDenSound.2,
                hupperFactorSound.2, hupperDenFactorSound.2,
                hfourSquareSound.2, hthreeRemainderSound.2,
                hsquareSound.2]
              simp only [remainder, hsquareSound.2, pow_two]
          · rw [if_pos hresidueZero] at hrun
            rcases optionBind_some hrun with
              ⟨upper, hupperRun, hrun⟩
            have honeFits : 1 < limbBase := by norm_num [limbBase]
            have hupperSound :=
              CPrimitives.wordAddChecked_sound
                hquotientFits honeFits hupperRun
            change some ⟨lower, upper⟩ = some result at hrun
            have hresult :
                CReciprocals.mk lower upper = result :=
              Option.some.inj hrun
            rw [← hresult]
            have hresidueNonzero' : upperNum % upperDen ≠ 0 := by
              simpa only [residue] using hresidueZero
            have hupperCeil :
                quotient + 1 =
                  TGComputeContracts.Sqrt218.ceilDiv
                    upperNum upperDen := by
              rw [ceilDiv_eq_quotient
                (Nat.zero_lt_of_ne_zero hupperDenZero)]
              simp only [hresidueNonzero', if_false, quotient]
            constructor
            · dsimp only [lower]
              rw [hlowerNumSound.2, hlowerDenSound.2,
                htwiceRootSound.2, htwiceSquareSound.2,
                hsquareSound.2]
              simp only [remainder, hsquareSound.2, pow_two]
            · rw [hupperSound.2, hupperCeil,
                hupperNumSound.2, hupperDenSound.2,
                hupperFactorSound.2, hupperDenFactorSound.2,
                hfourSquareSound.2, hthreeRemainderSound.2,
                hsquareSound.2]
              simp only [remainder, hsquareSound.2, pow_two]
    · simp only [hsquareLe, if_false] at hrun
      contradiction

theorem cReciprocals_upper_refines
    {value root : Nat} {result : CReciprocals}
    (hvalue : value < limbBase)
    (hroot : root < limbBase)
    (hrun :
      cReciprocals
          TGComputeContracts.Sqrt218.reciprocalScale
          value root =
        some result) :
    result.upper =
      TGComputeContracts.Sqrt218.reciprocalUpper value root := by
  have hscale :
      TGComputeContracts.Sqrt218.reciprocalScale < limbBase := by
    norm_num [TGComputeContracts.Sqrt218.reciprocalScale, limbBase]
  have hfacts :=
    cReciprocals_facts hscale hvalue hroot hrun
  rw [hfacts.upper]
  rfl

/-! ## One decoded accepted scan step -/

/-- Explicit connection between the two records returned by the C accessors
and the lists consumed by `IR.step`.  Byte-level decoding is intentionally
not smuggled into the arithmetic model. -/
structure DecodedStepRecords
    (image : ArchiveImage) (state : ScanState)
    (event : EventRecord) (prime : PrimeRecord) : Prop where
  eventAt :
    image.events[state.nextEvent]? = some event
  primeAt :
    image.primes[event.primeIndex]? = some prime

/-- Word-width facts supplied by the C record types and scan-state type. -/
structure CStepWordFacts
    (image : ArchiveImage) (state : ScanState)
    (event : EventRecord) (prime : PrimeRecord) : Prop where
  eventCount : image.header.eventCount < limbBase
  primeCount : image.header.primeCount < limbBase
  nextEvent : state.nextEvent < limbBase
  lastEventValue : state.lastEventValue < limbBase
  eventValue : event.value < limbBase
  primeIndex : event.primeIndex < limbBase
  exponent : event.exponent < uint32Base
  floorSqrt : event.floorSqrt < limbBase
  primeValue : prime.prime < limbBase
  logLower : prime.logLower < limbBase
  logUpper : prime.logUpper < limbBase
  weightedUpper : state.weightedUpper.Valid
  psiLower : state.psiLower.Valid

private instance (value root : Nat) :
    Decidable (cFloorSqrtOK value root) := by
  unfold cFloorSqrtOK
  infer_instance

/-- The exact successful path after `tg_sq218_event_at_v2` and
`tg_sq218_prime_at_v2` have returned their decoded records.

Failure statuses are collapsed to `none`; this definition is used only in the
success-to-IR direction.  Each source guard and helper call remains present
and in source order. -/
def cAcceptedScanStep
    (image : ArchiveImage) (state : ScanState)
    (event : EventRecord) (prime : PrimeRecord) :
    Option ScanState := do
  if state.nextEvent < image.header.eventCount then pure () else none
  if event.primeIndex < image.header.primeCount then pure () else none
  if event.value ≤ image.header.bound ∧
      event.exponent ≠ 0 ∧
      cFloorSqrtOK event.value event.floorSqrt ∧
      (state.nextEvent = 0 ∨
        state.lastEventValue < event.value)
    then pure ()
    else none
  let expectedPower ← cPowChecked prime.prime event.exponent
  if expectedPower = event.value then pure () else none
  let reciprocals ←
    cReciprocals image.header.reciprocalScale
      event.value event.floorSqrt
  let arithmetic ←
    cEventArithmetic
      state.weightedUpper state.psiLower
      prime.logUpper prime.logLower reciprocals.upper
      event.floorSqrt image.header.logScale
      image.header.reciprocalScale
  some {
    nextEvent := CPrimitives.wordAdd state.nextEvent 1
    lastEventValue := event.value
    weightedUpper := arithmetic.weighted
    psiLower := arithmetic.psi
  }

private theorem getD_eq_of_getElem?_eq_some
    {α : Type} [Inhabited α] {values : List α}
    {index : Nat} {value : α}
    (hget : values[index]? = some value) :
    index < values.length ∧ values.getD index default = value := by
  rcases List.getElem?_eq_some_iff.mp hget with
    ⟨hindex, hvalue⟩
  constructor
  · exact hindex
  · rw [List.getD_eq_getElem values default hindex]
    exact hvalue

private def IRStepGuard
    (image : ArchiveImage) (state : ScanState)
    (event : EventRecord) (prime : PrimeRecord) : Prop :=
  event.value < limbBase ∧
    prime.prime < limbBase ∧
    event.exponent < limbBase ∧
    0 < event.exponent ∧
    event.value ≤ image.header.bound ∧
    event.floorSqrt = Nat.sqrt event.value ∧
    (state.nextEvent = 0 ∨
      state.lastEventValue < event.value)

private def fromOptionIR {α : Type}
    (failure : Reject) : Option α → Except Reject α
  | none => .error failure
  | some value => .ok value

@[simp] private theorem exceptOk_bind
    {ε α β : Type} (value : α) (rest : α → Except ε β) :
    (Except.ok value >>= rest) = rest value := by
  rfl

private theorem exceptBind_ok_of
    {ε α β : Type} {first : Except ε α}
    {rest : α → Except ε β} {value : α} {result : β}
    (hfirst : first = .ok value)
    (hrest : rest value = .ok result) :
    first >>= rest = .ok result := by
  rw [hfirst]
  exact hrest

private def listAtIR {α : Type} [Inhabited α]
    (values : List α) (index : Nat) : Except Reject α :=
  if index < values.length then
    .ok (values.getD index default)
  else
    .error .outOfRange

/-- Tail of `IR.step` after its two list accesses have succeeded. -/
private def stepAfterRecords
    (image : ArchiveImage) (state : ScanState) :
    EventRecord → PrimeRecord → Except Reject ScanState
  | event, prime => do
  if event.value < limbBase ∧
      prime.prime < limbBase ∧
      event.exponent < limbBase ∧
      0 < event.exponent ∧
      event.value ≤ image.header.bound ∧
      event.floorSqrt = Nat.sqrt event.value ∧
      (state.nextEvent = 0 ∨
        state.lastEventValue < event.value)
    then pure ()
    else throw .arithmeticMismatch
  let expectedPower ←
    fromOptionIR .overflow
      (checkedPowWord prime.prime event.exponent)
  if expectedPower = event.value then pure ()
    else throw .arithmeticMismatch
  let upperReciprocal :=
    TGComputeContracts.Sqrt218.reciprocalUpper
      event.value event.floorSqrt
  let upperWord ←
    fromOptionIR .overflow (checkedWord upperReciprocal)
  let upperLog ←
    fromOptionIR .overflow (U128.ofWord prime.logUpper)
  let term ←
    fromOptionIR .overflow
      (U128.mulWordChecked upperLog upperWord)
  let weighted ←
    fromOptionIR .overflow
      (U128.addChecked state.weightedUpper term)
  let lowerLog ←
    fromOptionIR .overflow (U128.ofWord prime.logLower)
  let psi ←
    fromOptionIR .overflow
      (U128.addChecked state.psiLower lowerLog)
  let left ←
    fromOptionIR .overflow
      (U128.mulWordChecked weighted 1250)
  let right ← headRight image event.floorSqrt
  if left.lessThan right then
    pure {
      nextEvent := state.nextEvent + 1
      lastEventValue := event.value
      weightedUpper := weighted
      psiLower := psi
    }
  else
    throw .strictGuardFailed

/-- A successful source-level C scan step refines the mathematical event
kernel directly.

This is deliberately a semantic composition theorem rather than an equality
between the source `Option` program and the syntactic `Except` elaboration of
`IR.step`.  The latter distributes every continuation over every rejecting
branch, which is expensive for Lean to normalize and has no mathematical
content.  The theorem instead composes the already checked helper facts at
their small interfaces: decoded records, directed reciprocal, fixed-width
accumulators, and the strict head inequality. -/
theorem cAcceptedScanStep_refines_fixedEventStep
    {image : ArchiveImage} {state next : ScanState}
    {event : EventRecord} {prime : PrimeRecord}
    (hheader : headerCheck image = true)
    (hrecords : DecodedStepRecords image state event prime)
    (hwords : CStepWordFacts image state event prime)
    (hrun :
      cAcceptedScanStep image state event prime = some next) :
    TGComputeContracts.Sqrt218.fixedEventStep
        (kernelEventAt image)
        (kernelLogLowerAt image)
        (kernelLogUpperAt image)
        state.nextEvent state.toFixedState =
      some next.toFixedState := by
  simp only [headerCheck, decide_eq_true_eq] at hheader
  have hlogScale :
      image.header.logScale =
        TGComputeContracts.Sqrt218.scale := by
    calc
      image.header.logScale = logScale :=
        hheader.2.2.2.2.2.1
      _ = TGComputeContracts.Sqrt218.scale := rfl
  have hreciprocalScale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale := by
    calc
      image.header.reciprocalScale = reciprocalScale :=
        hheader.2.2.2.2.2.2.1
      _ = TGComputeContracts.Sqrt218.reciprocalScale := rfl
  have hevent :=
    getD_eq_of_getElem?_eq_some hrecords.eventAt
  have hprime :=
    getD_eq_of_getElem?_eq_some hrecords.primeAt
  unfold cAcceptedScanStep at hrun
  by_cases heventCount :
      state.nextEvent < image.header.eventCount
  · rw [if_pos heventCount] at hrun
    by_cases hprimeCount :
        event.primeIndex < image.header.primeCount
    · rw [if_pos hprimeCount] at hrun
      by_cases hguard :
          event.value ≤ image.header.bound ∧
            event.exponent ≠ 0 ∧
            cFloorSqrtOK event.value event.floorSqrt ∧
            (state.nextEvent = 0 ∨
              state.lastEventValue < event.value)
      · rw [if_pos hguard] at hrun
        rcases optionBind_some hrun with
          ⟨expectedPower, _hpower, hrun⟩
        by_cases hpowerValue : expectedPower = event.value
        · rw [if_pos hpowerValue] at hrun
          rcases optionBind_some hrun with
            ⟨reciprocals, hreciprocals, hrun⟩
          have hupper :
              reciprocals.upper =
                TGComputeContracts.Sqrt218.reciprocalUpper
                  event.value event.floorSqrt :=
            cReciprocals_upper_refines
              hwords.eventValue hwords.floorSqrt
                (by simpa only [hreciprocalScale] using hreciprocals)
          rcases optionBind_some hrun with
            ⟨arithmetic, harithmetic, hrun⟩
          have harithmeticFacts :=
            cEventArithmetic_facts
              hwords.weightedUpper hwords.psiLower harithmetic
          have hweighted :
              arithmetic.weighted.toNat =
                state.weightedUpper.toNat +
                  prime.logUpper *
                    TGComputeContracts.Sqrt218.reciprocalUpper
                      event.value event.floorSqrt := by
            simpa only [hupper] using harithmeticFacts.weighted
          have hpsi :
              arithmetic.psi.toNat =
                state.psiLower.toNat + prime.logLower :=
            harithmeticFacts.psi
          have hhead :
              TGComputeContracts.Sqrt218.headOK
                  event.value event.floorSqrt
                  arithmetic.weighted.toNat =
                true := by
            unfold TGComputeContracts.Sqrt218.headOK
            simp only [decide_eq_true_eq]
            calc
              1250 * arithmetic.weighted.toNat =
                  arithmetic.left.toNat := by
                    rw [harithmeticFacts.left]
                    exact Nat.mul_comm _ _
              _ < arithmetic.right.toNat :=
                harithmeticFacts.strict
              _ =
                  2501 * event.floorSqrt *
                    TGComputeContracts.Sqrt218.scale *
                    TGComputeContracts.Sqrt218.reciprocalScale := by
                rw [harithmeticFacts.right, hlogScale,
                  hreciprocalScale]
                ac_rfl
          have hweightedTerm :
              TGComputeContracts.Sqrt218.weightedTermUpper
                  prime.logUpper event.value event.floorSqrt =
                prime.logUpper *
                  TGComputeContracts.Sqrt218.reciprocalUpper
                    event.value event.floorSqrt := by
            by_cases hzero : prime.logUpper = 0
            · simp [TGComputeContracts.Sqrt218.weightedTermUpper,
                hzero]
            · simp [TGComputeContracts.Sqrt218.weightedTermUpper,
                hzero]
          have hnext :
              {
                nextEvent :=
                  CPrimitives.wordAdd state.nextEvent 1
                lastEventValue := event.value
                weightedUpper := arithmetic.weighted
                psiLower := arithmetic.psi
              } = next :=
            Option.some.inj hrun
          simp only [TGComputeContracts.Sqrt218.fixedEventStep,
            kernelEventAt, kernelLogLowerAt, kernelLogUpperAt,
            ScanState.toFixedState]
          rw [hevent.2, hprime.2, hweightedTerm,
            ← hweighted, ← hpsi, hhead, ← hnext]
          simp only [if_true]
        · rw [if_neg hpowerValue] at hrun
          contradiction
      · rw [if_neg hguard] at hrun
        contradiction
    · rw [if_neg hprimeCount] at hrun
      contradiction
  · rw [if_neg heventCount] at hrun
    contradiction

/-- Every accepted source step advances the `uint64_t` event cursor by
exactly one, without wraparound.

The strict pre-step comparison against a word-sized event count supplies the
missing no-wrap fact for C's unchecked `state->next_event += 1`. -/
theorem cAcceptedScanStep_nextEvent
    {image : ArchiveImage} {state next : ScanState}
    {event : EventRecord} {prime : PrimeRecord}
    (heventCountWord : image.header.eventCount < limbBase)
    (hrun :
      cAcceptedScanStep image state event prime = some next) :
    next.nextEvent = state.nextEvent + 1 := by
  unfold cAcceptedScanStep at hrun
  by_cases heventCount :
      state.nextEvent < image.header.eventCount
  · rw [if_pos heventCount] at hrun
    by_cases hprimeCount :
        event.primeIndex < image.header.primeCount
    · rw [if_pos hprimeCount] at hrun
      by_cases hguard :
          event.value ≤ image.header.bound ∧
            event.exponent ≠ 0 ∧
            cFloorSqrtOK event.value event.floorSqrt ∧
            (state.nextEvent = 0 ∨
              state.lastEventValue < event.value)
      · rw [if_pos hguard] at hrun
        rcases optionBind_some hrun with
          ⟨expectedPower, _hpower, hrun⟩
        by_cases hpowerValue : expectedPower = event.value
        · rw [if_pos hpowerValue] at hrun
          rcases optionBind_some hrun with
            ⟨_reciprocals, _hreciprocals, hrun⟩
          rcases optionBind_some hrun with
            ⟨arithmetic, _harithmetic, hrun⟩
          have hnext :
              {
                nextEvent :=
                  CPrimitives.wordAdd state.nextEvent 1
                lastEventValue := event.value
                weightedUpper := arithmetic.weighted
                psiLower := arithmetic.psi
              } = next :=
            Option.some.inj hrun
          rw [← hnext]
          change
            CPrimitives.wordAdd state.nextEvent 1 =
              state.nextEvent + 1
          unfold CPrimitives.wordAdd
          exact Nat.mod_eq_of_lt (by omega)
        · rw [if_neg hpowerValue] at hrun
          contradiction
      · rw [if_neg hguard] at hrun
        contradiction
    · rw [if_neg hprimeCount] at hrun
      contradiction
  · rw [if_neg heventCount] at hrun
    contradiction

/-
UNCOMPILED DESIGN NOTE (intentionally excluded from this module):

The experiment below spells the optimized `do` continuation as an explicit
bind tree.  Its arithmetic leaves are individually covered by the compiled
theorems above, but the equality between this tree and Lean's distributed
`do` elaboration is not yet proved.  It is retained only to identify that
single, data-independent composition boundary; it must not be treated as a
checked theorem.

/-- Unoptimized bind tree for `stepAfterRecords`.

Keeping this spelling separate prevents proof elaboration from distributing
an early rejecting branch through every later continuation. -/
def irStepAfterRecordsBind
    (image : ArchiveImage) (state : ScanState)
    (event : EventRecord) (prime : PrimeRecord) :
    Except Reject ScanState :=
  Except.bind
    (if IRStepGuard image state event prime then
      .ok ()
    else
      .error .arithmeticMismatch)
    (fun _ =>
      Except.bind
        (fromOptionIR .overflow
          (checkedPowWord prime.prime event.exponent))
        (fun expectedPower =>
          Except.bind
            (if expectedPower = event.value then
              .ok ()
            else
              .error .arithmeticMismatch)
            (fun _ =>
              Except.bind
                (fromOptionIR .overflow
                  (checkedWord
                    (TGComputeContracts.Sqrt218.reciprocalUpper
                      event.value event.floorSqrt)))
                (fun upperWord =>
                  Except.bind
                    (fromOptionIR .overflow
                      (U128.ofWord prime.logUpper))
                    (fun upperLog =>
                      Except.bind
                        (fromOptionIR .overflow
                          (U128.mulWordChecked upperLog upperWord))
                        (fun term =>
                          Except.bind
                            (fromOptionIR .overflow
                              (U128.addChecked
                                state.weightedUpper term))
                            (fun weighted =>
                              Except.bind
                                (fromOptionIR .overflow
                                  (U128.ofWord prime.logLower))
                                (fun lowerLog =>
                                  Except.bind
                                    (fromOptionIR .overflow
                                      (U128.addChecked
                                        state.psiLower lowerLog))
                                    (fun psi =>
                                      Except.bind
                                        (fromOptionIR .overflow
                                          (U128.mulWordChecked
                                            weighted 1250))
                                        (fun left =>
                                          Except.bind
                                            (headRight image
                                              event.floorSqrt)
                                            (fun right =>
                                              if left.lessThan right then
                                                .ok {
                                                  nextEvent :=
                                                    state.nextEvent + 1
                                                  lastEventValue :=
                                                    event.value
                                                  weightedUpper := weighted
                                                  psiLower := psi
                                                }
                                              else
                                                .error
                                                  .strictGuardFailed)))))))))))

/-- Public spelling of the private combinators inside `IR.step`. -/
private def stepIRSpelling
    (image : ArchiveImage) (state : ScanState) :
    Except Reject ScanState := do
  let event ← listAtIR image.events state.nextEvent
  let prime ← listAtIR image.primes event.primeIndex
  irStepAfterRecords image state event prime

private theorem step_eq_stepIRSpelling
    (image : ArchiveImage) (state : ScanState) :
    step image state = stepIRSpelling image state := by
  rfl

/-- The unoptimized bind-tree form of the successful IR tail evaluates to the
claimed next state from its individual, source-sized certificates. -/
theorem irStepAfterRecordsBind_ok
    {image : ArchiveImage} {state : ScanState}
    {event : EventRecord} {prime : PrimeRecord}
    {upperWord : Nat} {upperLog term weighted lowerLog psi left right : U128}
    (hguard : IRStepGuard image state event prime)
    (hpower :
      checkedPowWord prime.prime event.exponent =
        some event.value)
    (hupper :
      checkedWord
          (TGComputeContracts.Sqrt218.reciprocalUpper
            event.value event.floorSqrt) =
        some upperWord)
    (hupperLog : U128.ofWord prime.logUpper = some upperLog)
    (hterm : U128.mulWordChecked upperLog upperWord = some term)
    (hweighted :
      U128.addChecked state.weightedUpper term = some weighted)
    (hlowerLog : U128.ofWord prime.logLower = some lowerLog)
    (hpsi : U128.addChecked state.psiLower lowerLog = some psi)
    (hleft : U128.mulWordChecked weighted 1250 = some left)
    (hright : headRight image event.floorSqrt = .ok right)
    (hstrict : left.lessThan right = true) :
    irStepAfterRecordsBind image state event prime =
      .ok {
        nextEvent := state.nextEvent + 1
        lastEventValue := event.value
        weightedUpper := weighted
        psiLower := psi
      } := by
  unfold irStepAfterRecordsBind
  apply exceptBind_ok_of (value := ())
  · rw [if_pos hguard]
  · apply exceptBind_ok_of (value := event.value)
    · rw [hpower]
      rfl
    · apply exceptBind_ok_of (value := ())
      · simp
      · apply exceptBind_ok_of (value := upperWord)
        · rw [hupper]
          rfl
        · apply exceptBind_ok_of (value := upperLog)
          · rw [hupperLog]
            rfl
          · apply exceptBind_ok_of (value := term)
            · rw [hterm]
              rfl
            · apply exceptBind_ok_of (value := weighted)
              · rw [hweighted]
                rfl
              · apply exceptBind_ok_of (value := lowerLog)
                · rw [hlowerLog]
                  rfl
                · apply exceptBind_ok_of (value := psi)
                  · rw [hpsi]
                    rfl
                  · apply exceptBind_ok_of (value := left)
                    · rw [hleft]
                      rfl
                    · apply exceptBind_ok_of (value := right)
                      · exact hright
                      · rw [if_pos hstrict]

private theorem stepIRSpelling_ok_of_records
    {image : ArchiveImage} {state next : ScanState}
    {event : EventRecord} {prime : PrimeRecord}
    (hevent :
      listAtIR image.events state.nextEvent = .ok event)
    (hprime :
      listAtIR image.primes event.primeIndex = .ok prime)
    (htail : irStepAfterRecords image state event prime = .ok next) :
    stepIRSpelling image state = .ok next := by
  unfold stepIRSpelling
  rw [hevent]
  change
    (do
      let prime ← listAtIR image.primes event.primeIndex
      irStepAfterRecords image state event prime) =
        .ok next
  rw [hprime]
  exact htail

/-- Component-level constructor for the exact `IR.step` success path.

`htailSpelling` is the sole remaining syntactic boundary: it states that
Lean's optimized elaboration of the `do` block agrees with the explicit,
unoptimized bind tree proved by `irStepAfterRecordsBind_ok`.  Keeping this
small equality explicit avoids forcing a local build to normalize the full
distributed continuation. -/
theorem specEventArithmetic_implies_IR_step
    {image : ArchiveImage} {state next : ScanState}
    {event : EventRecord} {prime : PrimeRecord}
    {upperReciprocal : Nat}
    {arithmetic : EventArithmeticResult}
    (htailSpelling :
      irStepAfterRecords image state event prime =
        irStepAfterRecordsBind image state event prime)
    (hrecords : DecodedStepRecords image state event prime)
    (hguard : IRStepGuard image state event prime)
    (hpower :
      checkedPowWord prime.prime event.exponent =
        some event.value)
    (hupper :
      checkedWord
          (TGComputeContracts.Sqrt218.reciprocalUpper
            event.value event.floorSqrt) =
        some upperReciprocal)
    (harithmetic :
      specEventArithmetic
          state.weightedUpper state.psiLower
          prime.logUpper prime.logLower upperReciprocal
          event.floorSqrt image.header.logScale
          image.header.reciprocalScale =
        some arithmetic)
    (hnext :
      next = {
        nextEvent := state.nextEvent + 1
        lastEventValue := event.value
        weightedUpper := arithmetic.weighted
        psiLower := arithmetic.psi
      }) :
    step image state = .ok next := by
  have hevent :=
    getD_eq_of_getElem?_eq_some hrecords.eventAt
  have hprime :=
    getD_eq_of_getElem?_eq_some hrecords.primeAt
  have heventIR :
      listAtIR image.events state.nextEvent = .ok event := by
    unfold listAtIR
    rw [if_pos hevent.1]
    exact congrArg Except.ok hevent.2
  have hprimeIR :
      listAtIR image.primes event.primeIndex = .ok prime := by
    unfold listAtIR
    rw [if_pos hprime.1]
    exact congrArg Except.ok hprime.2
  unfold specEventArithmetic at harithmetic
  rcases optionBind_some harithmetic with
    ⟨upperLog, hupperLog, harithmetic⟩
  rcases optionBind_some harithmetic with
    ⟨term, hterm, harithmetic⟩
  rcases optionBind_some harithmetic with
    ⟨weighted, hweighted, harithmetic⟩
  rcases optionBind_some harithmetic with
    ⟨lowerLog, hlowerLog, harithmetic⟩
  rcases optionBind_some harithmetic with
    ⟨psi, hpsi, harithmetic⟩
  rcases optionBind_some harithmetic with
    ⟨left, hleft, harithmetic⟩
  rcases optionBind_some harithmetic with
    ⟨right, hright, harithmetic⟩
  by_cases hstrict : left.lessThan right = true
  · simp only [hstrict, if_true] at harithmetic
    have hresult :
        EventArithmeticResult.mk weighted psi left right =
          arithmetic :=
      Option.some.inj harithmetic
    have hrightIR :
        headRight image event.floorSqrt = .ok right :=
      specHeadRight_implies_IR_headRight hright
    rw [← hresult] at hnext
    unfold IRStepGuard at hguard
    have htailBind :=
      irStepAfterRecordsBind_ok hguard hpower hupper hupperLog hterm
        hweighted hlowerLog hpsi hleft hrightIR hstrict
    have htail :
        irStepAfterRecords image state event prime =
          .ok {
            nextEvent := state.nextEvent + 1
            lastEventValue := event.value
            weightedUpper := weighted
            psiLower := psi
          } :=
      htailSpelling.trans htailBind
    rw [step_eq_stepIRSpelling, hnext]
    exact stepIRSpelling_ok_of_records heventIR hprimeIR htail
  · simp only [hstrict, if_false] at harithmetic
    cases harithmetic

-/

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CStepRefinement
