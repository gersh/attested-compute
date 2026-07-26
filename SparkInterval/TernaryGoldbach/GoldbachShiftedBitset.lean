/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Nat.Bitwise
import SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics
import SparkInterval.TernaryGoldbach.GoldbachSourceSemantics

/-!
# Word-wise shifted-bitset reduction for finite binary Goldbach

This file isolates the small mathematical equation used by the optimized
Goldbach GPU route.  A bit at index `j` in an odd-prime window represents

`q = qLow + 2 * j`.

For a fixed odd prime `p` and a 64-even-number output word beginning at
`evenLow`, the campaign precomputes `shift` with

`evenLow = qLow + p + 2 * shift`.

Consequently bit `i` of the prime window shifted by `shift` certifies the
Goldbach representation

`evenLow + 2 * i = p + (qLow + 2 * (shift + i))`.

The CUDA kernel may OR one such shifted 64-bit word for each small prime and
stop as soon as every live output bit is one.  The theorems below show that
this word-wise loop is a sound replacement for one-thread-per-even witness
search.  They do not assert that a GPU ran and do not trust a hash or sampled
execution.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachShiftedBitset

/-- Abstract odd-number bitset window.  Only set bits need a soundness proof;
composite bits may conservatively be cleared. -/
structure PrimeWindow where
  qLow : Nat
  bit : Nat → Bool
  setBit_prime : ∀ index, bit index = true → Nat.Prime (qLow + 2 * index)

/-- Alignment data for one small prime and one 64-even output word.  Recording
the equation directly makes the certificate boundary human-auditable and
avoids hidden subtraction or parity corner cases. -/
structure Shift (window : PrimeWindow) (evenLow : Nat) where
  prime : Nat
  offset : Nat
  prime_prime : Nat.Prime prime
  alignment : evenLow = window.qLow + prime + 2 * offset

/-- Bit `i` contributed by one shifted prime-window word. -/
def shiftedBit {window : PrimeWindow} {evenLow : Nat}
    (shift : Shift window evenLow) (i : Fin 64) : Bool :=
  window.bit (shift.offset + i)

/-- Logical value of bit `i` after OR-ing all shifted words.  `List.any` is
the Boolean counterpart of the CUDA word-level bitwise OR. -/
def coverageBit {window : PrimeWindow} {evenLow : Nat}
    (shifts : List (Shift window evenLow)) (i : Fin 64) : Bool :=
  shifts.any (fun shift => shiftedBit shift i)

/-- Pure model of the CUDA bitwise-OR fold.  Machine words are represented as
naturals here; the production refinement additionally proves that each
two-load extraction has the expected `testBit`. -/
def orWords : List Nat → Nat
  | [] => 0
  | word :: words => word ||| orWords words

/-- Packed implementation view of one coverage word. -/
def packedCoverageWord {window : PrimeWindow} {evenLow : Nat}
    (shifts : List (Shift window evenLow))
    (encode : Shift window evenLow → Nat) : Nat :=
  orWords (shifts.map encode)

/-- A tail mask selects the live even numbers in the last output word. -/
def WordCovered {window : PrimeWindow} {evenLow : Nat}
    (shifts : List (Shift window evenLow)) (live : Fin 64 → Prop) : Prop :=
  ∀ i, live i → coverageBit shifts i = true

/-- The one-line shift equation used by the CUDA implementation. -/
theorem shifted_index_equation {window : PrimeWindow} {evenLow : Nat}
    (shift : Shift window evenLow) (i : Fin 64) :
    evenLow + 2 * (i : Nat) =
      shift.prime + (window.qLow + 2 * (shift.offset + (i : Nat))) := by
  have halign := shift.alignment
  omega

/-- Bitwise OR of the packed shifted words computes the logical `List.any`
coverage bit, provided the two-load word extractor computes each source bit
correctly. -/
theorem testBit_packedCoverageWord {window : PrimeWindow} {evenLow : Nat}
    (shifts : List (Shift window evenLow))
    (encode : Shift window evenLow → Nat) (i : Fin 64)
    (hencode : ∀ shift ∈ shifts,
      Nat.testBit (encode shift) i = shiftedBit shift i) :
    Nat.testBit (packedCoverageWord shifts encode) i =
      coverageBit shifts i := by
  induction shifts with
  | nil => simp [packedCoverageWord, orWords, coverageBit]
  | cons shift shifts ih =>
      simp only [packedCoverageWord, List.map_cons, orWords,
        Nat.testBit_lor, coverageBit, List.any_cons]
      rw [hencode shift (by simp)]
      congr 1
      apply ih
      intro candidate hmem
      exact hencode candidate (by simp [hmem])

/-- One set coverage bit contains an explicit pair of primes whose sum is the
corresponding even integer. -/
theorem exists_prime_pair_of_coverageBit {window : PrimeWindow}
    {evenLow : Nat} {shifts : List (Shift window evenLow)} {i : Fin 64}
    (covered : coverageBit shifts i = true) :
    ∃ p q : Nat,
      Nat.Prime p ∧ Nat.Prime q ∧ evenLow + 2 * (i : Nat) = p + q := by
  simp only [coverageBit, List.any_eq_true, shiftedBit] at covered
  rcases covered with ⟨shift, hmem, hbit⟩
  refine ⟨shift.prime,
    window.qLow + 2 * (shift.offset + (i : Nat)),
    shift.prime_prime, window.setBit_prime _ hbit, ?_⟩
  exact shifted_index_equation shift i

/-- Direct soundness theorem for a set bit in the packed CUDA OR result. -/
theorem exists_prime_pair_of_packedBit {window : PrimeWindow}
    {evenLow : Nat} {shifts : List (Shift window evenLow)}
    {encode : Shift window evenLow → Nat} {i : Fin 64}
    (hencode : ∀ shift ∈ shifts,
      Nat.testBit (encode shift) i = shiftedBit shift i)
    (covered : Nat.testBit (packedCoverageWord shifts encode) i = true) :
    ∃ p q : Nat,
      Nat.Prime p ∧ Nat.Prime q ∧ evenLow + 2 * (i : Nat) = p + q := by
  apply exists_prime_pair_of_coverageBit
  rw [← testBit_packedCoverageWord shifts encode i hencode]
  exact covered

/-- If every live bit in an output word is set, every represented even number
has a Goldbach decomposition. -/
theorem wordCovered_sound {window : PrimeWindow} {evenLow : Nat}
    {shifts : List (Shift window evenLow)} {live : Fin 64 → Prop}
    (covered : WordCovered shifts live) :
    ∀ i, live i →
      ∃ p q : Nat,
        Nat.Prime p ∧ Nat.Prime q ∧ evenLow + 2 * (i : Nat) = p + q := by
  intro i hi
  exact exists_prime_pair_of_coverageBit (covered i hi)

/-- The full-word specialization used away from the final tail word. -/
theorem fullWordCovered_sound {window : PrimeWindow} {evenLow : Nat}
    {shifts : List (Shift window evenLow)}
    (covered : ∀ i, coverageBit shifts i = true) :
    ∀ i : Fin 64,
      ∃ p q : Nat,
        Nat.Prime p ∧ Nat.Prime q ∧ evenLow + 2 * (i : Nat) = p + q := by
  intro i
  exact wordCovered_sound
    (window := window) (evenLow := evenLow) (shifts := shifts)
    (live := fun _ => True) (fun j _ => covered j) i trivial

/-- CUDA-style extraction of 64 consecutive bits from two packed words. -/
def extractShiftedWord (low high shift : Nat) : Nat :=
  if shift = 0 then low
  else (low >>> shift) ||| (high <<< (64 - shift))

/-- The two-load CUDA expression has exactly the source bits it claims. -/
theorem testBit_extractShiftedWord
    {source : Nat → Bool} {wordIndex shift low high : Nat}
    (hshift : shift < 64)
    (hlowWidth : low < 2 ^ 64)
    (hlow : ∀ j, j < 64 →
      Nat.testBit low j = source (64 * wordIndex + j))
    (hhigh : ∀ j, j < 64 →
      Nat.testBit high j = source (64 * (wordIndex + 1) + j))
    (i : Fin 64) :
    Nat.testBit (extractShiftedWord low high shift) i =
      source (64 * wordIndex + shift + (i : Nat)) := by
  by_cases hzero : shift = 0
  · subst shift
    simpa [extractShiftedWord] using hlow (i : Nat) i.isLt
  · rw [extractShiftedWord, if_neg hzero, Nat.testBit_lor,
      Nat.testBit_shiftRight, Nat.testBit_shiftLeft]
    by_cases hfirst : shift + (i : Nat) < 64
    · have hnotHigh : ¬ (i : Nat) ≥ 64 - shift := by omega
      simp only [show decide ((i : Nat) ≥ 64 - shift) = false by
        simp [hnotHigh], Bool.false_and, Bool.or_false]
      simpa [Nat.add_assoc] using hlow _ hfirst
    · have hhighIndex : (i : Nat) - (64 - shift) < 64 := by omega
      have hlowFalse :
          Nat.testBit low (shift + (i : Nat)) = false :=
        Nat.testBit_eq_false_of_lt
          (lt_of_lt_of_le hlowWidth
            (Nat.pow_le_pow_right (by omega) (by omega)))
      have husesHigh : (i : Nat) ≥ 64 - shift := by omega
      rw [hlowFalse]
      simp only [show decide ((i : Nat) ≥ 64 - shift) = true by
        simp [husesHigh], Bool.true_and, Bool.false_or, hhigh _ hhighIndex]
      congr 1
      omega

/-- A packed view of an abstract prime window, with explicit 64-bit width. -/
structure PackedPrimeWindow (window : PrimeWindow) where
  word : Nat → Nat
  word_width : ∀ index, word index < 2 ^ 64
  word_bit : ∀ index (i : Fin 64),
    Nat.testBit (word index) i =
      window.bit (64 * index + (i : Nat))

/-- The exact two-word encoder used for one aligned small prime. -/
def encodeShift {window : PrimeWindow} (packed : PackedPrimeWindow window)
    {evenLow : Nat} (shift : Shift window evenLow) : Nat :=
  extractShiftedWord
    (packed.word (shift.offset / 64))
    (packed.word (shift.offset / 64 + 1))
    (shift.offset % 64)

/-- The concrete two-load encoder discharges the abstract packed-word premise. -/
theorem testBit_encodeShift {window : PrimeWindow}
    (packed : PackedPrimeWindow window) {evenLow : Nat}
    (shift : Shift window evenLow) (i : Fin 64) :
    Nat.testBit (encodeShift packed shift) i = shiftedBit shift i := by
  have hraw := testBit_extractShiftedWord
    (source := window.bit)
    (wordIndex := shift.offset / 64)
    (shift := shift.offset % 64)
    (low := packed.word (shift.offset / 64))
    (high := packed.word (shift.offset / 64 + 1))
    (Nat.mod_lt _ (by omega))
    (packed.word_width _)
    (fun j hj => packed.word_bit _ ⟨j, hj⟩)
    (fun j hj => packed.word_bit _ ⟨j, hj⟩)
    i
  simp only [encodeShift, shiftedBit]
  rw [hraw]
  congr 1
  have hsplit := Nat.mod_add_div shift.offset 64
  omega

/-- Concrete packed words compute the logical coverage bit with no extractor
premise left to the caller. -/
theorem testBit_packedCoverageWord_encodeShift {window : PrimeWindow}
    (packed : PackedPrimeWindow window) {evenLow : Nat}
    (shifts : List (Shift window evenLow)) (i : Fin 64) :
    Nat.testBit
        (packedCoverageWord shifts (encodeShift packed)) i =
      coverageBit shifts i :=
  testBit_packedCoverageWord shifts (encodeShift packed) i
    (fun shift _ => testBit_encodeShift packed shift i)

/-- A set bit of the concrete two-load OR contains a Goldbach witness. -/
theorem exists_prime_pair_of_concretePackedBit {window : PrimeWindow}
    (packed : PackedPrimeWindow window) {evenLow : Nat}
    {shifts : List (Shift window evenLow)} {i : Fin 64}
    (covered :
      Nat.testBit
        (packedCoverageWord shifts (encodeShift packed)) i = true) :
    ∃ p q : Nat,
      Nat.Prime p ∧ Nat.Prime q ∧
        evenLow + 2 * (i : Nat) = p + q :=
  exists_prime_pair_of_packedBit
    (fun shift _ => testBit_encodeShift packed shift i) covered

/-- Low-bit tail mask used by the final CUDA output word. -/
def liveMask (liveCount : Nat) : Nat := 2 ^ liveCount - 1

@[simp] theorem testBit_liveMask (liveCount index : Nat) :
    Nat.testBit (liveMask liveCount) index = decide (index < liveCount) :=
  Nat.testBit_two_pow_sub_one liveCount index

/-- Machine acceptance `(covered & liveMask) = liveMask` forces every live
bit to be set. -/
theorem testBit_eq_true_of_land_liveMask_eq {covered liveCount index : Nat}
    (hindex : index < liveCount)
    (hcovered :
      (covered &&& liveMask liveCount) = liveMask liveCount) :
    Nat.testBit covered index = true := by
  have hbit := congrArg (fun value => Nat.testBit value index) hcovered
  simpa [Nat.testBit_land, testBit_liveMask, hindex] using hbit

/-- The concrete CUDA mask comparison plus the two-load encoder gives a
Goldbach witness for each live lane. -/
theorem concreteMaskedWord_sound {window : PrimeWindow}
    (packed : PackedPrimeWindow window) {evenLow liveCount : Nat}
    {shifts : List (Shift window evenLow)}
    (hcovered :
      (packedCoverageWord shifts (encodeShift packed) &&&
          liveMask liveCount) = liveMask liveCount) :
    ∀ i : Fin 64, (i : Nat) < liveCount →
      ∃ p q : Nat,
        Nat.Prime p ∧ Nat.Prime q ∧
          evenLow + 2 * (i : Nat) = p + q := by
  intro i hi
  apply exists_prime_pair_of_concretePackedBit packed
  exact testBit_eq_true_of_land_liveMask_eq hi hcovered

/-- The finite missing-bit word computed by `(~covered) & liveMask`. -/
def missingLiveBits (covered liveCount : Nat) : Nat :=
  (liveMask liveCount).ldiff covered

/-- Counting no missing live bits is equivalent to the literal mask
acceptance comparison. -/
theorem missingLiveBits_eq_zero_iff {covered liveCount : Nat} :
    missingLiveBits covered liveCount = 0 ↔
      (covered &&& liveMask liveCount) = liveMask liveCount := by
  constructor
  · intro hmissing
    apply Nat.eq_of_testBit_eq
    intro index
    have hbit := congrArg
      (fun value => Nat.testBit value index) hmissing
    simp only [missingLiveBits, Nat.testBit_ldiff,
      Nat.zero_testBit] at hbit
    rw [Nat.testBit_land]
    cases hmask : Nat.testBit (liveMask liveCount) index <;>
      cases hpresent : Nat.testBit covered index <;>
      simp_all only [Bool.not_false, Bool.not_true, Bool.false_and,
        Bool.true_and]
  · intro hcovered
    apply Nat.zero_of_testBit_eq_false
    intro index
    have hbit := congrArg
      (fun value => Nat.testBit value index) hcovered
    simp only [Nat.testBit_land] at hbit
    simp only [missingLiveBits, Nat.testBit_ldiff]
    cases hmask : Nat.testBit (liveMask liveCount) index <;>
      cases hpresent : Nat.testBit covered index <;>
      simp_all only [Bool.not_false, Bool.not_true, Bool.false_and,
        Bool.true_and]

/-- Pure model of the CUDA accumulator that adds one population count for
each packed output word.  The physical `__popcll` refinement is isolated in
the single zero-reflection premise of the theorem below. -/
def missingWordCount
    (popcount : Nat → Nat) (words : List (Nat × Nat)) : Nat :=
  (words.map fun word =>
    popcount (missingLiveBits word.1 word.2)).sum

/-- If the machine population count is zero exactly on the zero word, a zero
global accumulator is equivalent to the literal tail-mask acceptance test for
every output word.  Since the CUDA host rejects segment sizes above
`UInt32.max`, the separate physical refinement must also show that its atomic
accumulator cannot wrap. -/
theorem missingWordCount_eq_zero_iff
    (popcount : Nat → Nat) (words : List (Nat × Nat))
    (hpopcount : ∀ word, popcount word = 0 ↔ word = 0) :
    missingWordCount popcount words = 0 ↔
      words.Forall (fun word =>
        (word.1 &&& liveMask word.2) = liveMask word.2) := by
  induction words with
  | nil => simp [missingWordCount]
  | cons word words ih =>
      have ih' :
          (words.map fun entry =>
              popcount (missingLiveBits entry.1 entry.2)).sum = 0 ↔
            words.Forall (fun entry =>
              (entry.1 &&& liveMask entry.2) = liveMask entry.2) := by
        simpa only [missingWordCount] using ih
      simp only [missingWordCount, List.map_cons, List.sum_cons,
        List.forall_cons]
      rw [Nat.add_eq_zero_iff, hpopcount, missingLiveBits_eq_zero_iff, ih']

/-! ## Gap-free source campaign boundary -/

/-- Number of even integers in `[4, limit]`. -/
def evenCount (limit : Nat) : Nat := (limit - 4) / 2 + 1

/-- Number of 64-even output words, including a possible masked tail. -/
def outputWordCount (limit : Nat) : Nat := (evenCount limit + 63) / 64

/-- Exact live-bit predicate for output word `word`. -/
def liveBit (limit word : Nat) (i : Fin 64) : Prop :=
  4 + 128 * word + 2 * (i : Nat) ≤ limit

/-- One checked output word, with its exact prime-window alignment and live
tail mask. -/
structure CoveredOutputWord (limit word : Nat) where
  window : PrimeWindow
  shifts : List (Shift window (4 + 128 * word))
  covered : WordCovered shifts (liveBit limit word)

/-- Gap-free output of the production coverage campaign.  A physical runner
must construct every indexed word; a sample, digest, or maximum index cannot
inhabit this structure. -/
structure CampaignEvidence (limit : Nat) where
  word : ∀ index, index < outputWordCount limit → CoveredOutputWord limit index

private theorem evenIndex_exists {e : Nat} (he : Even e) (hlower : 4 ≤ e) :
    ∃ index : Nat, e = 4 + 2 * index := by
  rcases he with ⟨half, hhalf⟩
  refine ⟨half - 2, ?_⟩
  omega

private theorem evenIndex_lt_evenCount {limit index : Nat}
    (hvalue : 4 + 2 * index ≤ limit) : index < evenCount limit := by
  simp only [evenCount]
  omega

private theorem div_lt_outputWordCount {limit index : Nat}
    (hindex : index < evenCount limit) :
    index / 64 < outputWordCount limit := by
  simp only [outputWordCount]
  omega

private theorem word_bit_value (index : Nat) :
    4 + 128 * (index / 64) + 2 * (index % 64) = 4 + 2 * index := by
  have hsplit := Nat.mod_add_div index 64
  omega

/-- Complete shifted-word evidence through an arbitrary endpoint covers every
even integer in the literal interval `[4, limit]`.  Keeping the endpoint
generic prevents a campaign for one range from being relabelled as evidence
for a larger range. -/
theorem even_prime_pair_of_campaign (limit : Nat)
    (evidence : CampaignEvidence limit) :
    ∀ e : Nat, Even e → 4 ≤ e → e ≤ limit →
      ∃ p q : Nat, p.Prime ∧ q.Prime ∧ p + q = e := by
  intro e heven hlower hupper
  obtain ⟨index, hindexValue⟩ := evenIndex_exists heven hlower
  have hindex : index < evenCount limit :=
    evenIndex_lt_evenCount (by omega)
  let word := index / 64
  have hword : word < outputWordCount limit :=
    div_lt_outputWordCount hindex
  let bit : Fin 64 := ⟨index % 64, Nat.mod_lt _ (by norm_num)⟩
  let checked := evidence.word word hword
  have hlive : liveBit limit word bit := by
    simp only [liveBit, word, bit]
    rw [word_bit_value]
    omega
  obtain ⟨p, q, hp, hq, hsum⟩ :=
    wordCovered_sound checked.covered bit hlive
  exact ⟨p, q, hp, hq, by
    simp only [word, bit] at hsum
    rw [word_bit_value] at hsum
    omega⟩

/-- Historical campaign specialization at the Helfgott--Platt binary
endpoint. -/
theorem binaryGoldbachClaim_of_campaign
    (evidence : CampaignEvidence
      GoldbachSourceSemantics.binaryLimit) :
    GoldbachSourceSemantics.BinaryGoldbachClaim :=
  even_prime_pair_of_campaign GoldbachSourceSemantics.binaryLimit evidence

/-- Exact specialization used by the optimized finite campaign below
`10^27`.  Its premise is visibly indexed by the lowered
`31_250_000_000_000_000` endpoint. -/
theorem binaryGoldbach10Pow27Claim_of_campaign
    (evidence : CampaignEvidence
      Goldbach10Pow27SourceSemantics.binaryLimit) :
    Goldbach10Pow27SourceSemantics.BinaryGoldbachClaim :=
  even_prime_pair_of_campaign
    Goldbach10Pow27SourceSemantics.binaryLimit evidence

#print axioms shifted_index_equation
#print axioms testBit_packedCoverageWord
#print axioms exists_prime_pair_of_coverageBit
#print axioms exists_prime_pair_of_packedBit
#print axioms wordCovered_sound
#print axioms fullWordCovered_sound
#print axioms testBit_extractShiftedWord
#print axioms testBit_encodeShift
#print axioms testBit_packedCoverageWord_encodeShift
#print axioms exists_prime_pair_of_concretePackedBit
#print axioms testBit_eq_true_of_land_liveMask_eq
#print axioms concreteMaskedWord_sound
#print axioms missingLiveBits_eq_zero_iff
#print axioms missingWordCount_eq_zero_iff
#print axioms even_prime_pair_of_campaign
#print axioms binaryGoldbachClaim_of_campaign
#print axioms binaryGoldbach10Pow27Claim_of_campaign

end SparkInterval.TernaryGoldbach.GoldbachShiftedBitset
