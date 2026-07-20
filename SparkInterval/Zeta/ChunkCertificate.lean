import SparkInterval.Zeta.ZeroCertificate

/-!
# Chunked composition of real zero certificates

This module composes independently checkable groups of ordered zero brackets.
Chunk spans are ordered and adjacent spans are required to meet exactly.  Each
closed zero bracket lies strictly inside its chunk span, so roots selected from
different chunks remain distinct even where the spans share a boundary.

The total isolated-root lower bound is the sum of the chunk counts.  A later
Turing-style theorem can supply `ZeroCountUpperBound` with that same total;
the resulting theorem gives an exact distinct-zero count and coverage by the
chunked brackets.

This is theorem-level chunk composition.  It does not define or claim an
executable streaming parser, bounded-memory checker, wire compression, or a
Riemann-zeta/Turing theorem.  As in `ZeroCertificate`, zeros are distinct real
points and do not carry analytic multiplicity.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set
open scoped BigOperators

/-- One chunk consists of a span and an ordered sign-change certificate whose
closed brackets lie strictly inside that span. -/
structure ZeroChunk (f : ℝ → ℝ) (count : Nat) where
  span : Bracket
  certificate : ZeroCertificate f count
  bracketsInside : ∀ i,
    (certificate.brackets i).carrier ⊆ Set.Ioo span.lower span.upper

namespace ZeroChunk

theorem bracket_lower_gt_span_lower {f : ℝ → ℝ} {count : Nat}
    (chunk : ZeroChunk f count) (i : Fin count) :
    chunk.span.lower < (chunk.certificate.brackets i).lower := by
  let bracket := chunk.certificate.brackets i
  have hmem : bracket.lower ∈ bracket.carrier := by
    exact ⟨le_rfl, bracket.lower_lt_upper.le⟩
  exact ((chunk.bracketsInside i) hmem).1

theorem bracket_upper_lt_span_upper {f : ℝ → ℝ} {count : Nat}
    (chunk : ZeroChunk f count) (i : Fin count) :
    (chunk.certificate.brackets i).upper < chunk.span.upper := by
  let bracket := chunk.certificate.brackets i
  have hmem : bracket.upper ∈ bracket.carrier := by
    exact ⟨bracket.lower_lt_upper.le, le_rfl⟩
  exact ((chunk.bracketsInside i) hmem).2

end ZeroChunk

/-- A finite sequence of chunks.  `orderedSpans` is the all-pairs invariant
used by proofs; `contiguousSpans` records the stronger adjacent-boundary
equality expected from a gap-free chunking of a height interval. -/
structure ChunkCertificate (f : ℝ → ℝ) (chunkCount : Nat) where
  counts : Fin chunkCount → Nat
  chunks : ∀ chunk, ZeroChunk f (counts chunk)
  orderedSpans : ∀ {left right : Fin chunkCount}, left < right →
    (chunks left).span.upper ≤ (chunks right).span.lower
  contiguousSpans : ∀ {left right : Fin chunkCount},
    left.val + 1 = right.val →
      (chunks left).span.upper = (chunks right).span.lower

namespace ChunkCertificate

/-- The additive count recorded by all chunks. -/
def totalCount {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) : Nat :=
  ∑ chunk, certificate.counts chunk

/-- A bracket is addressed by its chunk index and its local index. -/
abbrev BracketIndex {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) :=
  Σ chunk, Fin (certificate.counts chunk)

/-- Recover the bracket named by a chunk/local index pair. -/
def bracket {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount)
    (index : certificate.BracketIndex) : Bracket :=
  (certificate.chunks index.1).certificate.brackets index.2

@[simp] theorem card_bracketIndex {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) :
    Fintype.card certificate.BracketIndex = certificate.totalCount := by
  simp [BracketIndex, totalCount, Fintype.card_sigma]

/-- Brackets from an earlier chunk are strictly left of brackets from a later
chunk.  Strict containment in each span turns weak span ordering into strict
bracket ordering. -/
theorem bracket_separated_of_chunk_lt {f : ℝ → ℝ}
    {chunkCount : Nat} (certificate : ChunkCertificate f chunkCount)
    {left right : Fin chunkCount} (hchunks : left < right)
    (i : Fin (certificate.counts left))
    (j : Fin (certificate.counts right)) :
    ((certificate.chunks left).certificate.brackets i).upper <
      ((certificate.chunks right).certificate.brackets j).lower := by
  have hupper := (certificate.chunks left).bracket_upper_lt_span_upper i
  have hlower := (certificate.chunks right).bracket_lower_gt_span_lower j
  exact (hupper.trans_le (certificate.orderedSpans hchunks)).trans hlower

private theorem carriers_disjoint_of_upper_lt_lower
    {left right : Bracket} (hseparated : left.upper < right.lower) :
    Disjoint left.carrier right.carrier := by
  rw [Set.disjoint_left]
  intro x hxleft hxright
  exact (not_lt_of_ge hxright.1) (hxleft.2.trans_lt hseparated)

/-- Every two distinct chunk/local indices name disjoint closed brackets. -/
theorem carrier_disjoint {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount)
    {left right : certificate.BracketIndex} (hne : left ≠ right) :
    Disjoint (certificate.bracket left).carrier
      (certificate.bracket right).carrier := by
  rcases left with ⟨leftChunk, leftIndex⟩
  rcases right with ⟨rightChunk, rightIndex⟩
  by_cases hchunk : leftChunk = rightChunk
  · subst rightChunk
    have hindex : leftIndex ≠ rightIndex := by
      intro heq
      subst rightIndex
      exact hne rfl
    exact (certificate.chunks leftChunk).certificate.toOrderedBrackets.carrier_disjoint
      hindex
  · rcases lt_or_gt_of_ne hchunk with hlt | hgt
    · exact carriers_disjoint_of_upper_lt_lower
        (certificate.bracket_separated_of_chunk_lt hlt leftIndex rightIndex)
    · exact (carriers_disjoint_of_upper_lt_lower
        (certificate.bracket_separated_of_chunk_lt hgt rightIndex leftIndex)).symm

/-- Continuity is required on every local bracket in every chunk. -/
def ContinuousOnChunks {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) : Prop :=
  ∀ chunk, (certificate.chunks chunk).certificate.ContinuousOnBrackets

/-- Every local bracket lies in the application domain. -/
def LiesIn {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) (domain : Set ℝ) : Prop :=
  ∀ index : certificate.BracketIndex,
    (certificate.bracket index).carrier ⊆ domain

/-- It is enough to prove that every chunk span lies in the application
domain; strict bracket containment then supplies `LiesIn`. -/
theorem liesIn_of_spans {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) {domain : Set ℝ}
    (hspans : ∀ chunk, (certificate.chunks chunk).span.carrier ⊆ domain) :
    certificate.LiesIn domain := by
  rintro ⟨chunk, index⟩ x hx
  apply hspans chunk
  have hinside := (certificate.chunks chunk).bracketsInside index hx
  exact ⟨hinside.1.le, hinside.2.le⟩

/-- Every zero in the application domain belongs to one chunk bracket. -/
def CompleteIn {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) (domain : Set ℝ) : Prop :=
  ∀ x : ℝ, x ∈ domain → f x = 0 →
    ∃ index : certificate.BracketIndex,
      x ∈ (certificate.bracket index).carrier

/-- One selected zero for every local bracket across all chunks. -/
structure RootSelection {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) where
  point : certificate.BracketIndex → ℝ
  mem_carrier : ∀ index,
    point index ∈ (certificate.bracket index).carrier
  is_zero : ∀ index, f (point index) = 0
  injective : Function.Injective point

/-- Local continuity and sign changes select a globally injective family of
roots because all local and cross-chunk brackets are disjoint. -/
theorem exists_rootSelection {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount)
    (hcontinuous : certificate.ContinuousOnChunks) :
    Nonempty certificate.RootSelection := by
  classical
  have hexists : ∀ index : certificate.BracketIndex,
      ∃ x ∈ (certificate.bracket index).carrier, f x = 0 := by
    rintro ⟨chunk, index⟩
    exact Bracket.exists_zero (hcontinuous chunk index)
      ((certificate.chunks chunk).certificate.signChange index)
  choose point hmem hzero using hexists
  refine ⟨{
    point := point
    mem_carrier := hmem
    is_zero := hzero
    injective := ?_
  }⟩
  intro left right heq
  by_contra hne
  have hdisjoint := certificate.carrier_disjoint hne
  apply (Set.disjoint_left.mp hdisjoint) (hmem left)
  rw [heq]
  exact hmem right

namespace RootSelection

/-- View each selected root as an element of the application's zero set. -/
def asZeroPoint {f : ℝ → ℝ} {chunkCount : Nat}
    {certificate : ChunkCertificate f chunkCount}
    (selection : certificate.RootSelection) (domain : Set ℝ)
    (hlies : certificate.LiesIn domain) :
    certificate.BracketIndex → zerosOn f domain :=
  fun index =>
    ⟨selection.point index, hlies index (selection.mem_carrier index),
      selection.is_zero index⟩

theorem asZeroPoint_injective {f : ℝ → ℝ} {chunkCount : Nat}
    {certificate : ChunkCertificate f chunkCount}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain) :
    Function.Injective (selection.asZeroPoint domain hlies) := by
  intro left right heq
  apply selection.injective
  exact congrArg Subtype.val heq

/-- The total isolated-root lower bound is the sum of all local chunk counts. -/
theorem count_le_zerosOn {f : ℝ → ℝ} {chunkCount : Nat}
    {certificate : ChunkCertificate f chunkCount}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain)
    (hfinite : (zerosOn f domain).Finite) :
    certificate.totalCount ≤ (zerosOn f domain).ncard := by
  letI := hfinite.fintype
  have hcard := Fintype.card_le_of_injective
    (selection.asZeroPoint domain hlies)
    (selection.asZeroPoint_injective hlies)
  rw [certificate.card_bracketIndex] at hcard
  simpa using hcard

/-- The same lower bound with its additive chunk sum exposed in the statement. -/
theorem sum_counts_le_zerosOn {f : ℝ → ℝ} {chunkCount : Nat}
    {certificate : ChunkCertificate f chunkCount}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain)
    (hfinite : (zerosOn f domain).Finite) :
    (∑ chunk, certificate.counts chunk) ≤ (zerosOn f domain).ncard := by
  exact selection.count_le_zerosOn hlies hfinite

/-- A matching global count upper bound fixes the exact additive count. -/
theorem exact_count_of_upperBound {f : ℝ → ℝ} {chunkCount : Nat}
    {certificate : ChunkCertificate f chunkCount}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain)
    (hupper : ZeroCountUpperBound f domain certificate.totalCount) :
    (zerosOn f domain).ncard = certificate.totalCount := by
  exact Nat.le_antisymm hupper.count_le
    (selection.count_le_zerosOn hlies hupper.finite)

/-- Equality of the global upper bound and the additive lower bound makes the
selected chunk roots exhaustive. -/
theorem complete_of_upperBound {f : ℝ → ℝ} {chunkCount : Nat}
    {certificate : ChunkCertificate f chunkCount}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain)
    (hupper : ZeroCountUpperBound f domain certificate.totalCount) :
    certificate.CompleteIn domain := by
  letI := hupper.finite.fintype
  let roots := selection.asZeroPoint domain hlies
  have hcard : Fintype.card certificate.BracketIndex =
      Fintype.card (zerosOn f domain) := by
    rw [certificate.card_bracketIndex, Set.fintypeCard_eq_ncard]
    exact (selection.exact_count_of_upperBound hlies hupper).symm
  have hsurjective : Function.Surjective roots :=
    ((Fintype.bijective_iff_injective_and_card roots).2
      ⟨selection.asZeroPoint_injective hlies, hcard⟩).2
  intro x hdomain hzero
  obtain ⟨index, hindex⟩ := hsurjective ⟨x, hdomain, hzero⟩
  refine ⟨index, ?_⟩
  have hpoint : selection.point index = x := congrArg Subtype.val hindex
  rw [← hpoint]
  exact selection.mem_carrier index

end RootSelection

/-- Final theorem-level result of chunk composition and a matching external
zero-count upper bound. -/
structure CompleteChunkCertificate {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) (domain : Set ℝ) : Prop where
  finiteZeros : (zerosOn f domain).Finite
  exactCount : (zerosOn f domain).ncard = certificate.totalCount
  complete : certificate.CompleteIn domain

/-- The integration point for a later Turing theorem: local bracket
continuity supplies the additive lower bound, and `ZeroCountUpperBound`
supplies the matching global upper bound. -/
theorem complete_of_count_upperBound {f : ℝ → ℝ} {chunkCount : Nat}
    (certificate : ChunkCertificate f chunkCount) {domain : Set ℝ}
    (hcontinuous : certificate.ContinuousOnChunks)
    (hlies : certificate.LiesIn domain)
    (hupper : ZeroCountUpperBound f domain certificate.totalCount) :
    CompleteChunkCertificate certificate domain := by
  let selection := Classical.choice (certificate.exists_rootSelection hcontinuous)
  exact {
    finiteZeros := hupper.finite
    exactCount := selection.exact_count_of_upperBound hlies hupper
    complete := selection.complete_of_upperBound hlies hupper
  }

end ChunkCertificate

end SparkInterval.Zeta
