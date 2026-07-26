/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachAtomicClears

/-!
# Packed optimized-Goldbach output refinement

The optimized CUDA route keeps its odd-prime window and Goldbach coverage in
packed 64-bit words.  A word is accepted by the literal machine test

`(covered &&& (2^liveCount - 1)) = (2^liveCount - 1)`.

This file connects that representation directly to the existing gap-free
`CampaignEvidence` boundary.  It proves:

* the exact live-lane count for every indexed output word;
* the two-load shifted-word OR plus tail-mask test supplies every logical
  `WordCovered` bit;
* one packed row for every formulaic word supplies exact campaign evidence;
  and
* the lowered and historical binary-Goldbach propositions follow.

The `PackedPrimeWindow` premise deliberately retains the remaining source
boundary: every set sieve bit must denote a prime.  CUDA/compiler realization
of the packed words and construction of that prime-window premise are not
asserted here.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.GoldbachOptimizedSourceRefinement

open GoldbachShiftedBitset

/-! ## Complete-sieve roster to prime-window soundness -/

/-- The retained sieve roster contains every prime whose square is at most
the candidate.  This is the exact mathematical completeness condition needed
to turn a surviving bit into primality. -/
def PrimeRosterCompleteAt
    (basePrimes : List Nat) (candidate : Nat) : Prop :=
  ∀ prime, prime.Prime → prime * prime ≤ candidate →
    prime ∈ basePrimes

/-- A candidate at least two that survives a complete prime roster is prime.
Thus the optimized source does not need an unformalized probabilistic
primality premise for its packed window: it needs only exact roster
completeness and exact implementation of `ClearedBy`. -/
theorem prime_of_completeRoster_not_cleared
    {basePrimes : List Nat} {candidate : Nat}
    (htwo : 2 ≤ candidate)
    (hcomplete : PrimeRosterCompleteAt basePrimes candidate)
    (hsurvives :
      ¬ GoldbachWordOwnerSieve.ClearedBy basePrimes candidate) :
    candidate.Prime := by
  by_contra hcomposite
  have hpositive : 0 < candidate := by omega
  have hnotOne : candidate ≠ 1 := by omega
  have hfactorPrime : candidate.minFac.Prime :=
    Nat.minFac_prime hnotOne
  have hfactorSquare :
      candidate.minFac * candidate.minFac ≤ candidate := by
    simpa [pow_two] using
      Nat.minFac_sq_le_self hpositive hcomposite
  apply hsurvives
  exact ⟨candidate.minFac,
    hcomplete candidate.minFac hfactorPrime hfactorSquare,
    Nat.minFac_dvd candidate, hfactorSquare⟩

/-- Construct the abstract prime-window interface directly from exact
survival facts for a complete sieve roster. -/
def primeWindowOfCompleteSieve
    (qLow : Nat) (bit : Nat → Bool) (basePrimes : List Nat)
    (htwo : ∀ index, bit index = true →
      2 ≤ qLow + 2 * index)
    (hcomplete : ∀ index, bit index = true →
      PrimeRosterCompleteAt basePrimes (qLow + 2 * index))
    (hsurvives : ∀ index, bit index = true →
      ¬ GoldbachWordOwnerSieve.ClearedBy
        basePrimes (qLow + 2 * index)) :
    PrimeWindow where
  qLow := qLow
  bit := bit
  setBit_prime := by
    intro index hbit
    exact prime_of_completeRoster_not_cleared
      (htwo index hbit) (hcomplete index hbit)
      (hsurvives index hbit)

/-- Number of live lanes in one formulaic 64-even output word. -/
def liveCount (limit word : Nat) : Nat :=
  min 64 (evenCount limit - 64 * word)

theorem liveCount_le_64 (limit word : Nat) :
    liveCount limit word ≤ 64 := by
  simp [liveCount]

/-- The arithmetic live predicate used by the campaign is exactly the low-bit
tail mask used by CUDA. -/
theorem liveBit_iff_lt_liveCount
    {limit word : Nat} (hlimit : 4 ≤ limit) (i : Fin 64) :
    liveBit limit word i ↔ (i : Nat) < liveCount limit word := by
  simp only [liveBit, liveCount, evenCount]
  omega

/-- One literal packed output row of the optimized coverage kernel. -/
structure PackedOutputWord (limit word : Nat) where
  window : PrimeWindow
  packed : PackedPrimeWindow window
  shifts : List (Shift window (4 + 128 * word))
  coveredWord : Nat
  coveredWord_eq :
    coveredWord = packedCoverageWord shifts (encodeShift packed)
  maskAccepted :
    (coveredWord &&& liveMask (liveCount limit word)) =
      liveMask (liveCount limit word)

/-- A literal packed row refines the abstract covered output word. -/
def PackedOutputWord.toCoveredOutputWord
    {limit word : Nat} (row : PackedOutputWord limit word)
    (hlimit : 4 ≤ limit) :
    CoveredOutputWord limit word where
  window := row.window
  shifts := row.shifts
  covered := by
    intro i hlive
    have hi : (i : Nat) < liveCount limit word :=
      (liveBit_iff_lt_liveCount hlimit i).mp hlive
    have hbit :
        Nat.testBit row.coveredWord i = true :=
      testBit_eq_true_of_land_liveMask_eq hi row.maskAccepted
    rw [row.coveredWord_eq,
      testBit_packedCoverageWord_encodeShift] at hbit
    exact hbit

/-- A source-scale packed campaign has one row at every formulaic word index.
This excludes samples, endpoint-only summaries, and maximum-index claims by
construction. -/
structure PackedCampaignEvidence (limit : Nat) where
  lower : 4 ≤ limit
  word :
    ∀ index, index < outputWordCount limit →
      PackedOutputWord limit index

/-- Packed machine-shaped rows construct the existing gap-free campaign
evidence in ordinary Lean. -/
def PackedCampaignEvidence.toCampaignEvidence
    {limit : Nat} (evidence : PackedCampaignEvidence limit) :
    CampaignEvidence limit where
  word := fun index hindex =>
    (evidence.word index hindex).toCoveredOutputWord
      evidence.lower

/-- Generic exact binary-Goldbach consequence of a packed campaign. -/
theorem even_prime_pair_of_packedCampaign
    {limit : Nat} (evidence : PackedCampaignEvidence limit) :
    ∀ e : Nat, Even e → 4 ≤ e → e ≤ limit →
      ∃ p q : Nat, p.Prime ∧ q.Prime ∧ p + q = e :=
  even_prime_pair_of_campaign limit evidence.toCampaignEvidence

/-- Historical endpoint specialization. -/
theorem historicalBinaryClaim
    (evidence : PackedCampaignEvidence
      GoldbachSourceSemantics.binaryLimit) :
    GoldbachSourceSemantics.BinaryGoldbachClaim :=
  binaryGoldbachClaim_of_campaign evidence.toCampaignEvidence

/-- Lowered endpoint specialization used below `10^27`. -/
theorem binary10Pow27Claim
    (evidence : PackedCampaignEvidence
      Goldbach10Pow27SourceSemantics.binaryLimit) :
    Goldbach10Pow27SourceSemantics.BinaryGoldbachClaim :=
  binaryGoldbach10Pow27Claim_of_campaign evidence.toCampaignEvidence

/-- The checked CUDA source admits at most 200,000,000 even outputs in one
segment, hence at most 3,125,000 packed output words. -/
def maximumSegmentOutputWords : Nat := 3_125_000

/-- A 64-bit population count contributes at most 64 to the missing-bit
accumulator. -/
theorem missingWordCount_le_words_mul_64
    (popcount : Nat → Nat) (words : List (Nat × Nat))
    (hpopcount : ∀ word, popcount word ≤ 64) :
    missingWordCount popcount words ≤ 64 * words.length := by
  induction words with
  | nil => simp [missingWordCount]
  | cons word words ih =>
      simp only [missingWordCount, List.map_cons, List.sum_cons,
        List.length_cons]
      have hhead :
          popcount (missingLiveBits word.1 word.2) ≤ 64 :=
        hpopcount _
      have ih' :
          (words.map fun entry =>
            popcount (missingLiveBits entry.1 entry.2)).sum
              ≤ 64 * words.length := by
        simpa only [missingWordCount] using ih
      omega

/-- Therefore the packed missing-bit counter cannot wrap its source
`uint32_t` accumulator.  This discharges the concrete arithmetic side of the
no-wrap boundary; physical `__popcll`/`atomicAdd` realization remains a
machine-semantics obligation. -/
theorem missingWordCount_lt_uint32
    (popcount : Nat → Nat) (words : List (Nat × Nat))
    (hwords : words.length ≤ maximumSegmentOutputWords)
    (hpopcount : ∀ word, popcount word ≤ 64) :
    missingWordCount popcount words < 2 ^ 32 := by
  have hcount :=
    missingWordCount_le_words_mul_64 popcount words hpopcount
  calc
    missingWordCount popcount words
        ≤ 64 * words.length := hcount
    _ ≤ 64 * maximumSegmentOutputWords :=
      Nat.mul_le_mul_left 64 hwords
    _ < 2 ^ 32 := by
      norm_num [maximumSegmentOutputWords]

/-- The kernel's zero missing-bit accumulator supplies the mask equation for
every retained `(coveredWord, liveCount)` row.  The physical bridge must also
show that `popcount` has this zero-reflection property; the preceding theorem
supplies the concrete no-wrap arithmetic once its per-word bound is known. -/
theorem maskAccepted_of_missingWordCount_eq_zero
    (popcount : Nat → Nat) (words : List (Nat × Nat))
    (hpopcount : ∀ word, popcount word = 0 ↔ word = 0)
    (hzero : missingWordCount popcount words = 0)
    {word : Nat × Nat} (hmem : word ∈ words) :
    (word.1 &&& liveMask word.2) = liveMask word.2 := by
  have hall :=
    (missingWordCount_eq_zero_iff popcount words hpopcount).mp hzero
  have hget :
      ∀ (entries : List (Nat × Nat)) (candidate : Nat × Nat),
        entries.Forall (fun entry =>
          (entry.1 &&& liveMask entry.2) = liveMask entry.2) →
        candidate ∈ entries →
        (candidate.1 &&& liveMask candidate.2) =
          liveMask candidate.2 := by
    intro entries
    induction entries with
    | nil => simp
    | cons first rest ih =>
        intro candidate hforall hcandidate
        simp only [List.forall_cons] at hforall
        simp only [List.mem_cons] at hcandidate
        rcases hcandidate with rfl | hcandidate
        · exact hforall.1
        · exact ih candidate hforall.2 hcandidate
  exact hget words word hall hmem

#print axioms liveBit_iff_lt_liveCount
#print axioms prime_of_completeRoster_not_cleared
#print axioms primeWindowOfCompleteSieve
#print axioms PackedOutputWord.toCoveredOutputWord
#print axioms PackedCampaignEvidence.toCampaignEvidence
#print axioms even_prime_pair_of_packedCampaign
#print axioms historicalBinaryClaim
#print axioms binary10Pow27Claim
#print axioms missingWordCount_le_words_mul_64
#print axioms missingWordCount_lt_uint32
#print axioms maskAccepted_of_missingWordCount_eq_zero

end
  SparkInterval.TernaryGoldbach.GoldbachOptimizedSourceRefinement
