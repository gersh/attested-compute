import SparkInterval.Zeta.ChunkCertificate

/-! Focused tests for additive composition of contiguous zero chunks. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaChunkCertificate

open Set
open SparkInterval.Zeta
open scoped BigOperators

private def twoRootFunction (x : ℝ) : ℝ :=
  (x + 2) * (x - 2)

private theorem twoRootFunction_continuous : Continuous twoRootFunction := by
  unfold twoRootFunction
  fun_prop

private def leftBracket : Bracket := {
  lower := (-3 : ℝ)
  upper := (-1 : ℝ)
  lower_lt_upper := by norm_num
}

private def rightBracket : Bracket := {
  lower := (1 : ℝ)
  upper := (3 : ℝ)
  lower_lt_upper := by norm_num
}

private def leftCertificate : ZeroCertificate twoRootFunction 1 where
  brackets := fun _ => leftBracket
  separated := by
    intro i j hij
    omega
  signChange := fun _ => Or.inr (by norm_num [twoRootFunction, leftBracket])

private def rightCertificate : ZeroCertificate twoRootFunction 1 where
  brackets := fun _ => rightBracket
  separated := by
    intro i j hij
    omega
  signChange := fun _ => Or.inl (by norm_num [twoRootFunction, rightBracket])

private def leftSpan : Bracket := {
  lower := (-4 : ℝ)
  upper := (0 : ℝ)
  lower_lt_upper := by norm_num
}

private def rightSpan : Bracket := {
  lower := (0 : ℝ)
  upper := (4 : ℝ)
  lower_lt_upper := by norm_num
}

private def leftChunk : ZeroChunk twoRootFunction 1 where
  span := leftSpan
  certificate := leftCertificate
  bracketsInside := by
    intro i x hx
    change (-3 : ℝ) ≤ x ∧ x ≤ -1 at hx
    change (-4 : ℝ) < x ∧ x < 0
    exact ⟨by linarith [hx.1], by linarith [hx.2]⟩

private def rightChunk : ZeroChunk twoRootFunction 1 where
  span := rightSpan
  certificate := rightCertificate
  bracketsInside := by
    intro i x hx
    change (1 : ℝ) ≤ x ∧ x ≤ 3 at hx
    change (0 : ℝ) < x ∧ x < 4
    exact ⟨by linarith [hx.1], by linarith [hx.2]⟩

private def twoChunks : ChunkCertificate twoRootFunction 2 where
  counts := fun _ => 1
  chunks := ![leftChunk, rightChunk]
  orderedSpans := by
    intro left right hlt
    fin_cases left <;> fin_cases right <;>
      simp_all [leftChunk, rightChunk, leftSpan, rightSpan]
  contiguousSpans := by
    intro left right hadjacent
    fin_cases left <;> fin_cases right <;>
      simp_all [leftChunk, rightChunk, leftSpan, rightSpan]

example : twoChunks.totalCount = 2 := by
  norm_num [ChunkCertificate.totalCount, twoChunks]

example :
    (twoChunks.chunks 0).span.upper = (twoChunks.chunks 1).span.lower := by
  exact twoChunks.contiguousSpans (by decide)

private def leftIndex : twoChunks.BracketIndex :=
  ⟨(0 : Fin 2), ⟨0, by simp [twoChunks]⟩⟩

private def rightIndex : twoChunks.BracketIndex :=
  ⟨(1 : Fin 2), ⟨0, by simp [twoChunks]⟩⟩

example : Disjoint (twoChunks.bracket leftIndex).carrier
    (twoChunks.bracket rightIndex).carrier := by
  exact twoChunks.carrier_disjoint (by decide)

private theorem chunks_continuous : twoChunks.ContinuousOnChunks := by
  intro chunk index
  exact twoRootFunction_continuous.continuousOn

example : Nonempty twoChunks.RootSelection :=
  twoChunks.exists_rootSelection chunks_continuous

private def domain : Set ℝ := Set.Icc (-4 : ℝ) (4 : ℝ)

private theorem chunks_lie_in_domain : twoChunks.LiesIn domain := by
  apply twoChunks.liesIn_of_spans
  intro chunk x hx
  fin_cases chunk
  · change (-4 : ℝ) ≤ x ∧ x ≤ 0 at hx
    change (-4 : ℝ) ≤ x ∧ x ≤ 4
    exact ⟨hx.1, hx.2.trans (by norm_num)⟩
  · change (0 : ℝ) ≤ x ∧ x ≤ 4 at hx
    change (-4 : ℝ) ≤ x ∧ x ≤ 4
    exact ⟨(by linarith [hx.1]), hx.2⟩

private theorem zerosOn_twoRootFunction :
    zerosOn twoRootFunction domain = ({-2, 2} : Set ℝ) := by
  ext x
  simp only [zerosOn, Set.mem_setOf_eq, Set.mem_insert_iff,
    Set.mem_singleton_iff]
  constructor
  · rintro ⟨_hdomain, hzero⟩
    change (x + 2) * (x - 2) = 0 at hzero
    rcases mul_eq_zero.mp hzero with hleft | hright
    · exact Or.inl (add_eq_zero_iff_eq_neg.mp hleft)
    · exact Or.inr (sub_eq_zero.mp hright)
  · rintro (rfl | rfl)
    · norm_num [domain, twoRootFunction]
    · norm_num [domain, twoRootFunction]

private theorem twoRootUpperBound :
    ZeroCountUpperBound twoRootFunction domain twoChunks.totalCount := by
  have htotal : twoChunks.totalCount = 2 := by
    norm_num [ChunkCertificate.totalCount, twoChunks]
  rw [htotal]
  refine {
    finite := ?_
    count_le := ?_
  }
  · rw [zerosOn_twoRootFunction]
    simp
  · rw [zerosOn_twoRootFunction]
    exact (Set.ncard_pair (by norm_num : (-2 : ℝ) ≠ 2)).le

example : ChunkCertificate.CompleteChunkCertificate twoChunks domain := by
  exact twoChunks.complete_of_count_upperBound chunks_continuous
    chunks_lie_in_domain twoRootUpperBound

example : (∑ chunk, twoChunks.counts chunk) ≤
    (zerosOn twoRootFunction domain).ncard := by
  let selection := Classical.choice (twoChunks.exists_rootSelection chunks_continuous)
  exact selection.sum_counts_le_zerosOn chunks_lie_in_domain
    twoRootUpperBound.finite

end SparkInterval.Tests.ZetaChunkCertificate
