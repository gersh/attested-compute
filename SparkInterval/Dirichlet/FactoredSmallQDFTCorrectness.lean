/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFT

/-!
# Correctness of the small-conductor positive-sign radix-2 DFT

This module proves that the exact staged transform checked by
`FactoredSmallQDFT` is the direct positive-sign DFT.  The proof uses a
block-transform invariant, proves the precise stage-index arithmetic, and
proves that the initial bit-reversal permutation is involutive.  Thus applying
a checked disk certificate to the direct DFT requires no separate FFT
correctness assumption.
-/

set_option autoImplicit false

open scoped BigOperators

namespace SparkInterval.Dirichlet.FactoredSmallQDFT

noncomputable def blockTransform {logLength : Nat} (completedStages : Nat)
    (initial : ExactState logLength) : ExactState logLength :=
  ⟨fun index =>
    let blockLength := 2 ^ completedStages
    let block := index.val / blockLength
    let frequency := index.val % blockLength
    ∑ row ∈ Finset.range blockLength,
      initial.value (finIndex logLength
        (block * blockLength + reverseBits completedStages row)) *
      unitRoot blockLength (row * frequency)⟩

theorem finIndex_self {logLength : Nat} (index : Fin (2 ^ logLength)) :
    finIndex logLength index.val = index := by
  apply Fin.ext
  simp [finIndex, Nat.mod_eq_of_lt index.isLt]

@[simp] theorem finIndex_val_of_lt {logLength index : Nat}
    (hindex : index < 2 ^ logLength) :
    (finIndex logLength index).val = index := by
  simp [finIndex, Nat.mod_eq_of_lt hindex]

theorem blockTransform_zero {logLength : Nat}
    (initial : ExactState logLength) : blockTransform 0 initial = initial := by
  cases initial with
  | mk value =>
      apply congrArg ExactState.mk
      funext index
      simp [reverseBits, unitRoot_zero, finIndex_self]

theorem transformLength_factor {stage logLength : Nat}
    (hstage : stage < logLength) :
    2 ^ logLength = width stage * 2 ^ (logLength - stage - 1) := by
  obtain ⟨extra, hextra⟩ := Nat.exists_eq_add_of_lt hstage
  rw [hextra]
  have hexponent : stage + extra + 1 = (stage + 1) + extra := by omega
  have hsub : stage + 1 + extra - stage - 1 = extra := by omega
  rw [hexponent, pow_add, hsub]
  simp [width, halfLength, pow_succ]
  ring

theorem scheduledRight_lt_transformLength {stage logLength index : Nat}
    (hstage : stage < logLength) (hindex : index < 2 ^ logLength) :
    scheduledRight stage (groupAt stage index) (offsetAt stage index) <
      2 ^ logLength := by
  let half := halfLength stage
  let span := width stage
  let blocks := 2 ^ (logLength - stage - 1)
  have hhalf : 0 < half := by simp [half, halfLength]
  have hspanEq : span = 2 * half := by rfl
  have hspan : 0 < span := by rw [hspanEq]; omega
  have hfactor : 2 ^ logLength = span * blocks := by
    simpa [span, blocks] using transformLength_factor hstage
  have hgroup : index / span < blocks := by
    rw [Nat.div_lt_iff_lt_mul hspan]
    rw [mul_comm, ← hfactor]
    exact hindex
  have hoffset : index % half < half := Nat.mod_lt _ hhalf
  have hlocal : index % half + half < span := by
    rw [hspanEq]
    omega
  calc
    scheduledRight stage (groupAt stage index) (offsetAt stage index) =
        (index / span) * span + (index % half + half) := by
      simp [scheduledRight, scheduledLeft, groupAt, offsetAt, span, half]
      ring
    _ < (index / span) * span + span := Nat.add_lt_add_left hlocal _
    _ = (index / span + 1) * span := by ring
    _ ≤ blocks * span := Nat.mul_le_mul_right span (by omega)
    _ = 2 ^ logLength := by rw [hfactor, mul_comm]

theorem index_eq_scheduledLeft {stage index : Nat}
    (hside : index % width stage < halfLength stage) :
    index = scheduledLeft stage (groupAt stage index)
      (offsetAt stage index) := by
  have hhalf : 0 < halfLength stage := by simp [halfLength]
  have hdvd : halfLength stage ∣ width stage := by
    refine ⟨2, ?_⟩
    simp [width]
    ring
  have hmodmod := Nat.mod_mod_of_dvd index hdvd
  have hoffset : index % halfLength stage = index % width stage := by
    rw [← hmodmod, Nat.mod_eq_of_lt hside]
  rw [scheduledLeft, groupAt, offsetAt, hoffset]
  simpa [mul_comm] using (Nat.div_add_mod index (width stage)).symm

theorem index_eq_scheduledRight {stage index : Nat}
    (hside : ¬ index % width stage < halfLength stage) :
    index = scheduledRight stage (groupAt stage index)
      (offsetAt stage index) := by
  have hhalf : 0 < halfLength stage := by simp [halfLength]
  have hwidth : width stage = 2 * halfLength stage := rfl
  have hrem : index % width stage < width stage :=
    Nat.mod_lt _ (by simp [width, halfLength])
  have hremDecomp :
      index % width stage = halfLength stage +
        (index % width stage - halfLength stage) := by omega
  have htail : index % width stage - halfLength stage <
      halfLength stage := by
    rw [hwidth] at hrem ⊢
    omega
  have hdvd : halfLength stage ∣ width stage := by
    refine ⟨2, ?_⟩
    simp [width]
    ring
  have hmodmod := Nat.mod_mod_of_dvd index hdvd
  have hoffset : index % halfLength stage =
      index % width stage - halfLength stage := by
    calc
      index % halfLength stage =
          (index % width stage) % halfLength stage := hmodmod.symm
      _ = (halfLength stage +
          (index % width stage - halfLength stage)) %
            halfLength stage := congrArg
              (fun value => value % halfLength stage) hremDecomp
      _ = index % width stage - halfLength stage := by
        simp [Nat.mod_eq_of_lt htail]
  rw [scheduledRight, scheduledLeft, groupAt, offsetAt, hoffset]
  rw [show index / width stage * width stage +
      (index % width stage - halfLength stage) + halfLength stage =
      width stage * (index / width stage) + index % width stage by
        rw [mul_comm]
        omega]
  exact (Nat.div_add_mod index (width stage)).symm

theorem blockTransform_scheduledLeft {logLength stage group offset : Nat}
    (initial : ExactState logLength)
    (hoffset : offset < halfLength stage)
    (hright : scheduledRight stage group offset < 2 ^ logLength) :
    (blockTransform stage initial).value
        (finIndex logLength (scheduledLeft stage group offset)) =
      ∑ row ∈ Finset.range (halfLength stage),
        initial.value (finIndex logLength
          (group * width stage + reverseBits stage row)) *
        unitRoot (halfLength stage) (row * offset) := by
  have hhalf : 0 < halfLength stage := by simp [halfLength]
  have hleft : scheduledLeft stage group offset < 2 ^ logLength := by
    unfold scheduledRight at hright
    omega
  have hdiv :
      scheduledLeft stage group offset / halfLength stage = 2 * group := by
    rw [show scheduledLeft stage group offset =
      halfLength stage * (2 * group) + offset by
        simp [scheduledLeft, width]
        ring]
    rw [Nat.mul_add_div hhalf, Nat.div_eq_of_lt hoffset, add_zero]
  have hmod :
      scheduledLeft stage group offset % halfLength stage = offset := by
    rw [show scheduledLeft stage group offset =
      halfLength stage * (2 * group) + offset by
        simp [scheduledLeft, width]
        ring]
    rw [Nat.mul_add_mod, Nat.mod_eq_of_lt hoffset]
  change scheduledLeft stage group offset / 2 ^ stage = 2 * group at hdiv
  change scheduledLeft stage group offset % 2 ^ stage = offset at hmod
  simp only [blockTransform, finIndex_val_of_lt hleft]
  rw [hdiv, hmod]
  congr 1 with row
  congr 2
  simp [width, halfLength]
  ring_nf

theorem blockTransform_scheduledRight {logLength stage group offset : Nat}
    (initial : ExactState logLength)
    (hoffset : offset < halfLength stage)
    (hright : scheduledRight stage group offset < 2 ^ logLength) :
    (blockTransform stage initial).value
        (finIndex logLength (scheduledRight stage group offset)) =
      ∑ row ∈ Finset.range (halfLength stage),
        initial.value (finIndex logLength
          (group * width stage + halfLength stage +
            reverseBits stage row)) *
        unitRoot (halfLength stage) (row * offset) := by
  have hhalf : 0 < halfLength stage := by simp [halfLength]
  have hdiv :
      scheduledRight stage group offset / halfLength stage =
        2 * group + 1 := by
    rw [show scheduledRight stage group offset =
      halfLength stage * (2 * group + 1) + offset by
        simp [scheduledRight, scheduledLeft, width]
        ring]
    rw [Nat.mul_add_div hhalf, Nat.div_eq_of_lt hoffset, add_zero]
  have hmod :
      scheduledRight stage group offset % halfLength stage = offset := by
    rw [show scheduledRight stage group offset =
      halfLength stage * (2 * group + 1) + offset by
        simp [scheduledRight, scheduledLeft, width]
        ring]
    rw [Nat.mul_add_mod, Nat.mod_eq_of_lt hoffset]
  change scheduledRight stage group offset / 2 ^ stage =
    2 * group + 1 at hdiv
  change scheduledRight stage group offset % 2 ^ stage = offset at hmod
  simp only [blockTransform, finIndex_val_of_lt hright]
  rw [hdiv, hmod]
  congr 1 with row
  congr 2
  simp [width, halfLength]
  ring_nf

theorem blockTransform_next_scheduledLeft
    {logLength stage group offset : Nat}
    (initial : ExactState logLength)
    (hoffset : offset < halfLength stage)
    (hright : scheduledRight stage group offset < 2 ^ logLength) :
    (blockTransform (stage + 1) initial).value
        (finIndex logLength (scheduledLeft stage group offset)) =
      ButterflyCertificate.exactLeft
        ((blockTransform stage initial).value
          (finIndex logLength (scheduledLeft stage group offset)))
        ((blockTransform stage initial).value
          (finIndex logLength (scheduledRight stage group offset)))
        (unitRoot (width stage) offset) := by
  have hhalf : 0 < halfLength stage := by simp [halfLength]
  have hleft : scheduledLeft stage group offset < 2 ^ logLength := by
    unfold scheduledRight at hright
    omega
  have hpow : 2 ^ (stage + 1) = width stage := by
    simp [width, halfLength, pow_succ]
    ring
  have hdiv : scheduledLeft stage group offset / width stage = group := by
    rw [show scheduledLeft stage group offset =
      width stage * group + offset by
        simp [scheduledLeft]
        ring]
    rw [Nat.mul_add_div (by simp [width, halfLength]),
      Nat.div_eq_of_lt (lt_trans hoffset (by simp [width]; omega)), add_zero]
  have hmod : scheduledLeft stage group offset % width stage = offset := by
    rw [show scheduledLeft stage group offset =
      width stage * group + offset by
        simp [scheduledLeft]
        ring]
    rw [Nat.mul_add_mod,
      Nat.mod_eq_of_lt (lt_trans hoffset (by simp [width]; omega))]
  rw [blockTransform_scheduledLeft initial hoffset hright,
    blockTransform_scheduledRight initial hoffset hright]
  simp only [blockTransform, finIndex_val_of_lt hleft, hpow, hdiv, hmod]
  rw [show width stage = 2 * halfLength stage by rfl,
    sum_range_twice]
  simp only [reverseBits]
  have hevenDiv (row : Nat) : 2 * row / 2 = row := by omega
  have hevenMod (row : Nat) : 2 * row % 2 = 0 := by omega
  have hoddDiv (row : Nat) : (2 * row + 1) / 2 = row := by omega
  have hoddMod (row : Nat) : (2 * row + 1) % 2 = 1 := by omega
  simp_rw [hevenDiv, hevenMod, hoddDiv, hoddMod]
  simp only [zero_mul, zero_add, one_mul]
  simp_rw [unitRoot_even, unitRoot_odd]
  simp_rw [← mul_assoc]
  rw [Finset.sum_add_distrib, ← Finset.sum_mul]
  unfold ButterflyCertificate.exactLeft
  simp [halfLength, add_assoc]

theorem blockTransform_next_scheduledRight
    {logLength stage group offset : Nat}
    (initial : ExactState logLength)
    (hoffset : offset < halfLength stage)
    (hright : scheduledRight stage group offset < 2 ^ logLength) :
    (blockTransform (stage + 1) initial).value
        (finIndex logLength (scheduledRight stage group offset)) =
      ButterflyCertificate.exactRight
        ((blockTransform stage initial).value
          (finIndex logLength (scheduledLeft stage group offset)))
        ((blockTransform stage initial).value
          (finIndex logLength (scheduledRight stage group offset)))
        (unitRoot (width stage) offset) := by
  have hhalf : 0 < halfLength stage := by simp [halfLength]
  have hpow : 2 ^ (stage + 1) = width stage := by
    simp [width, halfLength, pow_succ]
    ring
  have hdiv : scheduledRight stage group offset / width stage = group := by
    rw [show scheduledRight stage group offset =
      width stage * group + (offset + halfLength stage) by
        simp [scheduledRight, scheduledLeft]
        ring]
    rw [Nat.mul_add_div (by simp [width, halfLength]),
      Nat.div_eq_of_lt (by simp [width]; omega), add_zero]
  have hmod : scheduledRight stage group offset % width stage =
      offset + halfLength stage := by
    rw [show scheduledRight stage group offset =
      width stage * group + (offset + halfLength stage) by
        simp [scheduledRight, scheduledLeft]
        ring]
    rw [Nat.mul_add_mod, Nat.mod_eq_of_lt (by simp [width]; omega)]
  rw [blockTransform_scheduledLeft initial hoffset hright,
    blockTransform_scheduledRight initial hoffset hright]
  simp only [blockTransform, finIndex_val_of_lt hright, hpow, hdiv, hmod]
  rw [show width stage = 2 * halfLength stage by rfl,
    sum_range_twice]
  simp only [reverseBits]
  have hevenDiv (row : Nat) : 2 * row / 2 = row := by omega
  have hevenMod (row : Nat) : 2 * row % 2 = 0 := by omega
  have hoddDiv (row : Nat) : (2 * row + 1) / 2 = row := by omega
  have hoddMod (row : Nat) : (2 * row + 1) % 2 = 1 := by omega
  simp_rw [hevenDiv, hevenMod, hoddDiv, hoddMod]
  simp only [zero_mul, zero_add, one_mul]
  simp_rw [unitRoot_even_shift hhalf, unitRoot_odd_shift hhalf]
  simp_rw [mul_neg, ← mul_assoc]
  rw [Finset.sum_add_distrib, Finset.sum_neg_distrib,
    ← Finset.sum_mul]
  unfold ButterflyCertificate.exactRight
  simp [halfLength, add_assoc]
  ring

/-- Human-readable stage invariant: after completing stage `stage`, each
`2^(stage+1)` block is the direct positive DFT of its two bit-reversed
`2^stage` subblocks. -/
theorem exactStage_blockTransform {logLength stage : Nat}
    (initial : ExactState logLength) (hstage : stage < logLength) :
    exactStage stage positiveTwiddle (blockTransform stage initial) =
      blockTransform (stage + 1) initial := by
  apply congrArg ExactState.mk
  funext index
  let group := groupAt stage index.val
  let offset := offsetAt stage index.val
  have hoffset : offset < halfLength stage := by
    exact Nat.mod_lt _ (by simp [halfLength])
  have hright : scheduledRight stage group offset < 2 ^ logLength := by
    exact scheduledRight_lt_transformLength hstage index.isLt
  by_cases hside : index.val % width stage < halfLength stage
  · have hbool : isLeftOutput stage index.val = true := by
      simp [isLeftOutput, hside]
    have hindexNat : index.val = scheduledLeft stage group offset :=
      index_eq_scheduledLeft hside
    have hleft : scheduledLeft stage group offset < 2 ^ logLength := by
      unfold scheduledRight at hright
      omega
    have hindexFin :
        index = finIndex logLength (scheduledLeft stage group offset) := by
      apply Fin.ext
      rw [finIndex_val_of_lt hleft]
      exact hindexNat
    have hnext := blockTransform_next_scheduledLeft
      initial hoffset hright
    simp only [hbool, if_true]
    change ButterflyCertificate.exactLeft
      ((blockTransform stage initial).value
        (finIndex logLength (scheduledLeft stage group offset)))
      ((blockTransform stage initial).value
        (finIndex logLength (scheduledRight stage group offset)))
      (unitRoot (width stage) offset) =
        (blockTransform (stage + 1) initial).value index
    rw [hindexFin]
    exact hnext.symm

  · have hbool : isLeftOutput stage index.val = false := by
      simp [isLeftOutput, hside]
    have hindexNat : index.val = scheduledRight stage group offset :=
      index_eq_scheduledRight hside
    have hindexFin :
        index = finIndex logLength (scheduledRight stage group offset) := by
      apply Fin.ext
      rw [finIndex_val_of_lt hright]
      exact hindexNat
    have hnext := blockTransform_next_scheduledRight
      initial hoffset hright
    simp only [hbool]
    change ButterflyCertificate.exactRight
      ((blockTransform stage initial).value
        (finIndex logLength (scheduledLeft stage group offset)))
      ((blockTransform stage initial).value
        (finIndex logLength (scheduledRight stage group offset)))
      (unitRoot (width stage) offset) =
        (blockTransform (stage + 1) initial).value index
    rw [hindexFin]
    exact hnext.symm

theorem runExactStages_blockTransform {logLength count stage : Nat}
    (initial : ExactState logLength) (hbound : stage + count ≤ logLength) :
    runExactStages positiveTwiddle count stage
        (blockTransform stage initial) =
      blockTransform (stage + count) initial := by
  induction count generalizing stage with
  | zero => simp [runExactStages]
  | succ count ih =>
      have hstage : stage < logLength := by omega
      rw [runExactStages, exactStage_blockTransform initial hstage]
      have htail := ih (stage := stage + 1) (by omega)
      rw [show stage + (count + 1) = (stage + 1) + count by omega]
      exact htail

theorem runExactStages_eq_blockTransform {logLength : Nat}
    (initial : ExactState logLength) :
    runExactStages positiveTwiddle logLength 0 initial =
      blockTransform logLength initial := by
  calc
    _ = runExactStages positiveTwiddle logLength 0
        (blockTransform 0 initial) := by rw [blockTransform_zero]
    _ = blockTransform (0 + logLength) initial :=
      runExactStages_blockTransform (count := logLength) (stage := 0)
        initial (by omega)
    _ = _ := by simp

theorem reverseBits_succ_double_add (bits value bit : Nat)
    (hbit : bit < 2) :
    reverseBits (bits + 1) (2 * value + bit) =
      bit * 2 ^ bits + reverseBits bits value := by
  rw [reverseBits]
  have hmod : (2 * value + bit) % 2 = bit := by omega
  have hdiv : (2 * value + bit) / 2 = value := by omega
  rw [hmod, hdiv]

theorem reverseBits_highBit (bits value bit : Nat)
    (hvalue : value < 2 ^ bits) (hbit : bit < 2) :
    reverseBits (bits + 1) (bit * 2 ^ bits + value) =
      2 * reverseBits bits value + bit := by
  induction bits generalizing value with
  | zero =>
      have hvalue0 : value = 0 := by simpa using hvalue
      subst value
      simp [reverseBits, Nat.mod_eq_of_lt hbit]
  | succ bits ih =>
      rw [reverseBits]
      have hpow : 2 ^ (bits + 1) = 2 * 2 ^ bits := by
        rw [pow_succ]
        ring
      have hvalueDiv : value / 2 < 2 ^ bits := by
        apply (Nat.div_lt_iff_lt_mul (by omega)).2
        rw [pow_succ] at hvalue
        simpa [mul_comm] using hvalue
      have hmod : (bit * 2 ^ (bits + 1) + value) % 2 = value % 2 := by
        have hfirst : bit * 2 ^ (bits + 1) % 2 = 0 := by
          rw [hpow, show bit * (2 * 2 ^ bits) =
            2 * (bit * 2 ^ bits) by ring]
          exact Nat.mul_mod_right 2 (bit * 2 ^ bits)
        rw [Nat.add_mod, hfirst, zero_add, Nat.mod_mod]
      have hdiv : (bit * 2 ^ (bits + 1) + value) / 2 =
          bit * 2 ^ bits + value / 2 := by
        rw [hpow, show bit * (2 * 2 ^ bits) =
          2 * (bit * 2 ^ bits) by ring]
        exact Nat.mul_add_div (by omega) (bit * 2 ^ bits) value
      rw [hmod, hdiv, ih (value / 2) hvalueDiv]
      rw [reverseBits]
      ring

theorem reverseBits_involutive (bits value : Nat)
    (hvalue : value < 2 ^ bits) :
    reverseBits bits (reverseBits bits value) = value := by
  induction bits generalizing value with
  | zero =>
      have : value = 0 := by simpa using hvalue
      subst value
      rfl
  | succ bits ih =>
      have hbit : value % 2 < 2 := Nat.mod_lt _ (by omega)
      have htail : value / 2 < 2 ^ bits := by
        rw [Nat.div_lt_iff_lt_mul (by omega)]
        rw [pow_succ] at hvalue
        omega
      have hrev : reverseBits (bits + 1) value =
          value % 2 * 2 ^ bits + reverseBits bits (value / 2) := by
        rw [reverseBits]
      rw [hrev, reverseBits_highBit bits (reverseBits bits (value / 2))
        (value % 2) (reverseBits_lt_two_pow _ _) hbit]
      rw [ih (value / 2) htail]
      simpa using Nat.div_add_mod value 2

theorem bitReversed_at_reverseBits {logLength : Nat}
    (source : ExactState logLength) {index : Nat}
    (hindex : index < 2 ^ logLength) :
    (bitReversed source).value
        (finIndex logLength (reverseBits logLength index)) =
      source.value (finIndex logLength index) := by
  simp only [bitReversed]
  rw [finIndex_val_of_lt (reverseBits_lt_two_pow _ _),
    reverseBits_involutive _ _ hindex]

noncomputable def directDFTState {logLength : Nat}
    (source : ExactState logLength) : ExactState logLength :=
  ⟨positiveDFT source⟩

theorem blockTransform_full_eq_directDFT {logLength : Nat}
    (source : ExactState logLength) :
    blockTransform logLength (bitReversed source) = directDFTState source := by
  apply congrArg ExactState.mk
  funext frequency
  have hlength : 0 < 2 ^ logLength := Nat.pow_pos (by omega)
  have hdiv : frequency.val / 2 ^ logLength = 0 :=
    Nat.div_eq_of_lt frequency.isLt
  have hmod : frequency.val % 2 ^ logLength = frequency.val :=
    Nat.mod_eq_of_lt frequency.isLt
  simp only [hdiv, hmod, zero_mul, zero_add, positiveDFT]
  rw [Finset.sum_range]
  apply Finset.sum_congr rfl
  intro input hinput
  rw [bitReversed_at_reverseBits source input.isLt, finIndex_self]

theorem radix2CorrectFor {logLength : Nat}
    (source : ExactState logLength) : Radix2CorrectFor source := by
  intro frequency
  have hrun := runExactStages_eq_blockTransform (bitReversed source)
  have hfull := blockTransform_full_eq_directDFT source
  change (runExactStages positiveTwiddle logLength 0
      (bitReversed source)).value frequency = positiveDFT source frequency
  rw [hrun, hfull]
  rfl

namespace Certificate

/-- A checked staged disk certificate encloses the direct positive-sign DFT.
No separate FFT-correctness premise is needed: `radix2CorrectFor` discharges
the generic bit-reversal and butterfly-network identity. -/
theorem output_contains_positiveDFT_unconditional {logLength : Nat}
    {certificate : Certificate logLength}
    {source : ExactState logLength}
    (hcheck : certificate.check = true)
    (hbitReverse : StateContains certificate.input (bitReversed source))
    (hroots : TwiddlesContain (logLength := logLength)
      certificate.twiddleDisks positiveTwiddle) :
    ∀ frequency,
      (certificate.output.value frequency).ContainsComplex
        (positiveDFT source frequency) :=
  output_contains_positiveDFT hcheck hbitReverse hroots
    (radix2CorrectFor source)

end Certificate

end SparkInterval.Dirichlet.FactoredSmallQDFT
