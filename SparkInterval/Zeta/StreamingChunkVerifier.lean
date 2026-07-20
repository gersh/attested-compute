import SparkInterval.Zeta.HardyZContract
import SparkInterval.Zeta.StreamingEndpointCertificate

/-!
# Streaming composition of endpoint chunks

This module bridges the executable one-pass endpoint checker to the existing
`ChunkCertificate` and finite-height zeta verifier.  A producer may split its
endpoint brackets into independently checked chunks.  The rolling state passed
between chunks is only the preceding rational span endpoint; each chunk's
endpoint checker separately retains only the preceding bracket.

Successful checking proves, without `native_decide` or a new axiom, that:

* every chunk is a valid ordered endpoint family;
* every endpoint bracket lies strictly inside its advertised chunk span;
* adjacent chunk spans meet exactly; and
* transitivity upgrades adjacent span checks to the all-pairs ordering required
  by `ChunkCertificate`.

The conversion to `ChunkCertificate` consumes an evaluator-specific enclosure
theorem for each endpoint.  A `HardyZModel` and matching total-count upper bound
then give the existing finite-height zeta conclusion.

The `List` values below are theorem-level inputs.  This file does not implement
a byte parser, file I/O, a rolling file digest, a signed chunk manifest, or a
bounded allocator, and it does not prove a physical RAM bound for a Lean
runtime.  The transition itself is resumable and has constant-size boundary
state, but an actual bounded-memory verifier must feed and discard parsed
chunks and separately bind their bytes/order to an authenticated manifest.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set
open scoped BigOperators

/-- Untrusted rational data for one independently checkable endpoint chunk. -/
structure RationalEndpointChunk where
  spanLower : ℚ
  spanUpper : ℚ
  entries : List RationalBracket
  deriving DecidableEq, Repr

namespace RationalEndpointChunk

/-- Exact proposition checked for one chunk.  Empty endpoint chunks are
allowed; the span itself must still be nondegenerate. -/
def IsValid (chunk : RationalEndpointChunk) : Prop :=
  chunk.spanLower < chunk.spanUpper ∧
    checkEndpointStream chunk.entries = true ∧
    ∀ entry ∈ chunk.entries,
      chunk.spanLower < entry.lower ∧ entry.upper < chunk.spanUpper

instance (chunk : RationalEndpointChunk) : Decidable chunk.IsValid := by
  unfold IsValid
  infer_instance

/-- Executable, exact-rational local chunk check. -/
def check (chunk : RationalEndpointChunk) : Bool :=
  decide chunk.IsValid

@[simp] theorem check_eq_true {chunk : RationalEndpointChunk} :
    chunk.check = true ↔ chunk.IsValid := by
  simp [check]

/-- The fixed-size family represented by this chunk's list. -/
def family (chunk : RationalEndpointChunk) :
    RationalBracketFamily chunk.entries.length :=
  endpointFamilyOfList chunk.entries

/-- A checked rational chunk and proved endpoint enclosures produce one
generic real zero chunk with the same span. -/
theorem exists_zeroChunk
    (chunk : RationalEndpointChunk) {f : ℝ → ℝ}
    (hvalid : chunk.IsValid)
    (hencloses : ∀ i, (chunk.family.entries i).EnclosesEndpoints f) :
    ∃ zeroChunk : ZeroChunk f chunk.entries.length,
      zeroChunk.span.lower = (chunk.spanLower : ℝ) ∧
      zeroChunk.span.upper = (chunk.spanUpper : ℝ) := by
  obtain ⟨certificate, hendpoints⟩ :=
    chunk.family.exists_zeroCertificate
      (checkEndpointStream_familyCheck hvalid.2.1) hencloses
  let span : Bracket := {
    lower := (chunk.spanLower : ℝ)
    upper := (chunk.spanUpper : ℝ)
    lower_lt_upper := by exact_mod_cast hvalid.1
  }
  refine ⟨{
    span := span
    certificate := certificate
    bracketsInside := ?_
  }, rfl, rfl⟩
  intro i x hx
  have hentry : chunk.family.entries i ∈ chunk.entries := by
    exact List.get_mem chunk.entries i
  have hinside := hvalid.2.2 _ hentry
  have hlower : (chunk.spanLower : ℝ) <
      ((chunk.family.entries i).lower : ℝ) := by
    exact_mod_cast hinside.1
  have hupper : ((chunk.family.entries i).upper : ℝ) <
      (chunk.spanUpper : ℝ) := by
    exact_mod_cast hinside.2
  constructor
  · calc
      span.lower = (chunk.spanLower : ℝ) := rfl
      _ < ((chunk.family.entries i).lower : ℝ) := hlower
      _ = (certificate.brackets i).lower := (hendpoints i).1.symm
      _ ≤ x := hx.1
  · calc
      x ≤ (certificate.brackets i).upper := hx.2
      _ = ((chunk.family.entries i).upper : ℝ) := (hendpoints i).2
      _ < (chunk.spanUpper : ℝ) := hupper
      _ = span.upper := rfl

end RationalEndpointChunk

/-- Constant-size logical state carried between independently parsed chunks. -/
structure EndpointChunkStreamState where
  previousUpper : Option ℚ := none
  deriving DecidableEq, Repr

namespace EndpointChunkStreamState

/-- Propositional condition for accepting one chunk after the current state. -/
def AcceptsNext (state : EndpointChunkStreamState)
    (current : RationalEndpointChunk) : Prop :=
  current.IsValid ∧
    match state.previousUpper with
    | none => True
    | some previous => previous = current.spanLower

instance (state : EndpointChunkStreamState)
    (current : RationalEndpointChunk) : Decidable (state.AcceptsNext current) := by
  unfold AcceptsNext
  split <;> infer_instance

/-- Executable exact-rational form of `AcceptsNext`. -/
def acceptsNext (state : EndpointChunkStreamState)
    (current : RationalEndpointChunk) : Bool :=
  decide (state.AcceptsNext current)

@[simp] theorem acceptsNext_eq_true
    {state : EndpointChunkStreamState} {current : RationalEndpointChunk} :
    state.acceptsNext current = true ↔ state.AcceptsNext current := by
  simp [acceptsNext]

/-- Check one chunk, retaining only its upper span boundary. -/
def step? (state : EndpointChunkStreamState)
    (current : RationalEndpointChunk) : Option EndpointChunkStreamState :=
  if state.acceptsNext current = true then
    some { previousUpper := some current.spanUpper }
  else
    none

end EndpointChunkStreamState

/-- Recursive logical meaning of accepting a remaining sequence of chunks. -/
def EndpointChunkStreamValidFrom :
    Option ℚ → List RationalEndpointChunk → Prop
  | _, [] => True
  | previous, current :: rest =>
      current.IsValid ∧
        (match previous with
          | none => True
          | some prior => prior = current.spanLower) ∧
        EndpointChunkStreamValidFrom (some current.spanUpper) rest

/-- Run one list of chunks.  The returned state can be resumed on the next
list without retaining an earlier chunk. -/
def runEndpointChunkStream :
    EndpointChunkStreamState →
      List RationalEndpointChunk → Option EndpointChunkStreamState
  | state, [] => some state
  | state, current :: rest => do
      let next ← state.step? current
      runEndpointChunkStream next rest

/-- Resuming on a second list is exactly checking the concatenated sequence. -/
theorem runEndpointChunkStream_append (state : EndpointChunkStreamState)
    (left right : List RationalEndpointChunk) :
    runEndpointChunkStream state (left ++ right) =
      (runEndpointChunkStream state left).bind fun next =>
        runEndpointChunkStream next right := by
  induction left generalizing state with
  | nil => simp [runEndpointChunkStream]
  | cons current rest induction =>
      simp only [List.cons_append, runEndpointChunkStream]
      cases hstep : state.step? current with
      | none => simp
      | some next => simp [induction]

/-- The executable chunk runner reflects exactly its recursive logical
condition. -/
theorem runEndpointChunkStream_isSome_iff
    (state : EndpointChunkStreamState)
    (chunks : List RationalEndpointChunk) :
    (runEndpointChunkStream state chunks).isSome = true ↔
      EndpointChunkStreamValidFrom state.previousUpper chunks := by
  induction chunks generalizing state with
  | nil => simp [runEndpointChunkStream, EndpointChunkStreamValidFrom]
  | cons current rest induction =>
      by_cases haccept : state.acceptsNext current = true
      · have hmeaning : state.AcceptsNext current :=
          EndpointChunkStreamState.acceptsNext_eq_true.mp haccept
        change current.IsValid ∧
          (match state.previousUpper with
            | none => True
            | some prior => prior = current.spanLower) at hmeaning
        simp [runEndpointChunkStream, EndpointChunkStreamState.step?, haccept,
          EndpointChunkStreamValidFrom, induction]
        constructor
        · intro hrest
          exact ⟨hmeaning.1, hmeaning.2, hrest⟩
        · intro hall
          exact hall.2.2
      · have hmeaning : ¬state.AcceptsNext current := by
          intro h
          exact haccept
            (EndpointChunkStreamState.acceptsNext_eq_true.mpr h)
        change ¬(current.IsValid ∧
          (match state.previousUpper with
            | none => True
            | some prior => prior = current.spanLower)) at hmeaning
        simp [runEndpointChunkStream, EndpointChunkStreamState.step?, haccept,
          EndpointChunkStreamValidFrom]
        intro hcurrent hboundary
        exact False.elim (hmeaning ⟨hcurrent, hboundary⟩)

/-- Start a fresh one-pass check of a chunk sequence. -/
def checkEndpointChunkStream
    (chunks : List RationalEndpointChunk) : Bool :=
  (runEndpointChunkStream {} chunks).isSome

theorem checkEndpointChunkStream_sound
    {chunks : List RationalEndpointChunk}
    (hcheck : checkEndpointChunkStream chunks = true) :
    EndpointChunkStreamValidFrom none chunks := by
  exact (runEndpointChunkStream_isSome_iff {} chunks).mp hcheck

namespace EndpointChunkStreamValidFrom

/-- Every member of a successfully checked sequence is locally valid. -/
theorem allLocal {previous : Option ℚ}
    {chunks : List RationalEndpointChunk}
    (hvalid : EndpointChunkStreamValidFrom previous chunks) :
    ∀ chunk ∈ chunks, chunk.IsValid := by
  induction chunks generalizing previous with
  | nil => simp
  | cons current rest induction =>
      intro chunk hmem
      rcases List.mem_cons.mp hmem with rfl | hrest
      · exact hvalid.1
      · exact induction hvalid.2.2 chunk hrest

/-- The boundary checks imply the adjacent span-contiguity chain. -/
theorem isChain {previous : Option ℚ}
    {chunks : List RationalEndpointChunk}
    (hvalid : EndpointChunkStreamValidFrom previous chunks) :
    chunks.IsChain
      (fun left right => left.spanUpper = right.spanLower) := by
  induction chunks generalizing previous with
  | nil => exact .nil
  | cons current rest induction =>
      cases rest with
      | nil => exact .singleton current
      | cons next tail =>
          have hrest : EndpointChunkStreamValidFrom
              (some current.spanUpper) (next :: tail) := hvalid.2.2
          exact .cons_cons hrest.2.1 (induction hrest)

private def SpanBefore
    (left right : RationalEndpointChunk) : Prop :=
  left.spanUpper ≤ right.spanLower ∧
    right.spanLower < right.spanUpper

private instance : Trans SpanBefore SpanBefore SpanBefore where
  trans hab hbc :=
    ⟨hab.1.trans (hab.2.le.trans hbc.1), hbc.2⟩

/-- Adjacent equality plus nondegenerate spans implies all-pairs weak span
ordering. -/
theorem orderedSpans {previous : Option ℚ}
    {chunks : List RationalEndpointChunk}
    (hvalid : EndpointChunkStreamValidFrom previous chunks)
    {left right : Fin chunks.length} (hlt : left < right) :
    (chunks.get left).spanUpper ≤ (chunks.get right).spanLower := by
  have hlocal := hvalid.allLocal
  have hchain := hvalid.isChain
  have hbefore : chunks.IsChain SpanBefore :=
    hchain.imp_of_mem_imp fun a b _ha hb hab =>
      ⟨hab.le, (hlocal b hb).1⟩
  exact ((List.pairwise_iff_get.mp hbefore.pairwise) left right hlt).1

/-- The original exact adjacent-boundary equality is available by finite
indices for construction of `ChunkCertificate`. -/
theorem contiguousSpans {previous : Option ℚ}
    {chunks : List RationalEndpointChunk}
    (hvalid : EndpointChunkStreamValidFrom previous chunks)
    {left right : Fin chunks.length}
    (hadjacent : left.val + 1 = right.val) :
    (chunks.get left).spanUpper = (chunks.get right).spanLower := by
  have hbound : left.val + 1 < chunks.length := by
    rw [hadjacent]
    exact right.isLt
  have hchain := hvalid.isChain.getElem left.val hbound
  simpa only [List.get_eq_getElem, hadjacent] using hchain

end EndpointChunkStreamValidFrom

/-- Sum of the independently sized endpoint chunks. -/
def endpointChunkTotalCount
    (chunks : List RationalEndpointChunk) : Nat :=
  ∑ chunk : Fin chunks.length, (chunks.get chunk).entries.length

/-- A constructed generic chunk certificate together with the exact mapping
of its count and span metadata back to the checked rational input. -/
structure CheckedEndpointChunkCertificate
    (f : ℝ → ℝ) (source : List RationalEndpointChunk) where
  certificate : ChunkCertificate f source.length
  count_eq : ∀ chunk,
    certificate.counts chunk = (source.get chunk).entries.length
  spanLower_eq : ∀ chunk,
    (certificate.chunks chunk).span.lower =
      ((source.get chunk).spanLower : ℝ)
  spanUpper_eq : ∀ chunk,
    (certificate.chunks chunk).span.upper =
      ((source.get chunk).spanUpper : ℝ)

namespace CheckedEndpointChunkCertificate

/-- The abstract chunk total is exactly the sum of the source list lengths. -/
theorem totalCount_eq {f : ℝ → ℝ}
    {source : List RationalEndpointChunk}
    (checked : CheckedEndpointChunkCertificate f source) :
    checked.certificate.totalCount = endpointChunkTotalCount source := by
  simp only [ChunkCertificate.totalCount, endpointChunkTotalCount]
  apply Finset.sum_congr rfl
  intro chunk _hmem
  exact checked.count_eq chunk

/-- A global continuity theorem discharges every constructed local bracket. -/
theorem continuousOnChunks {f : ℝ → ℝ}
    {source : List RationalEndpointChunk}
    (checked : CheckedEndpointChunkCertificate f source)
    (hcontinuous : Continuous f) :
    checked.certificate.ContinuousOnChunks := by
  intro _chunk _index
  exact hcontinuous.continuousOn

/-- Bounds on each compact span imply that every local bracket lies in the
finite-height domain. -/
theorem liesInHeight {f : ℝ → ℝ} {height : ℝ}
    {source : List RationalEndpointChunk}
    (checked : CheckedEndpointChunkCertificate f source)
    (hlower : ∀ chunk : Fin source.length,
      -height ≤ ((source.get chunk).spanLower : ℝ))
    (hupper : ∀ chunk : Fin source.length,
      ((source.get chunk).spanUpper : ℝ) ≤ height) :
    checked.certificate.LiesIn (heightDomain height) := by
  apply checked.certificate.liesIn_of_spans
  intro chunk x hx
  change (checked.certificate.chunks chunk).span.lower ≤ x ∧
    x ≤ (checked.certificate.chunks chunk).span.upper at hx
  change -height ≤ x ∧ x ≤ height
  rw [checked.spanLower_eq chunk, checked.spanUpper_eq chunk] at hx
  exact ⟨(hlower chunk).trans hx.1, hx.2.trans (hupper chunk)⟩

/-- Package a constructed streaming certificate with the analytic inputs used
by the existing chunked finite-height verifier. -/
def toVerifierEvidence {f : ℝ → ℝ} {height : ℝ}
    {source : List RationalEndpointChunk}
    (checked : CheckedEndpointChunkCertificate f source)
    (model : HardyZModel f height)
    (hlower : ∀ chunk : Fin source.length,
      -height ≤ ((source.get chunk).spanLower : ℝ))
    (hupper : ∀ chunk : Fin source.length,
      ((source.get chunk).spanUpper : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height
      (endpointChunkTotalCount source)) :
    ChunkedZetaVerifierEvidence f height source.length where
  chunks := checked.certificate
  continuous := checked.continuousOnChunks model.continuous
  liesIn := checked.liesInHeight hlower hupper
  bridge := model.criticalLineZeroBridge
  totalUpper := by
    simpa only [checked.totalCount_eq] using totalUpper

end CheckedEndpointChunkCertificate

/-- Main pure composition theorem.  Every local endpoint family is converted
independently; only checked rational count/span summaries are composed. -/
theorem exists_checkedEndpointChunkCertificate
    {f : ℝ → ℝ} {source : List RationalEndpointChunk}
    (hcheck : checkEndpointChunkStream source = true)
    (hencloses : ∀ (chunk : Fin source.length)
      (entry : Fin (source.get chunk).entries.length),
      ((source.get chunk).family.entries entry).EnclosesEndpoints f) :
    Nonempty (CheckedEndpointChunkCertificate f source) := by
  classical
  have hvalid := checkEndpointChunkStream_sound hcheck
  have hlocal := hvalid.allLocal
  have hexists : ∀ chunk : Fin source.length,
      ∃ zeroChunk : ZeroChunk f (source.get chunk).entries.length,
        zeroChunk.span.lower = ((source.get chunk).spanLower : ℝ) ∧
        zeroChunk.span.upper = ((source.get chunk).spanUpper : ℝ) := by
    intro chunk
    exact (source.get chunk).exists_zeroChunk
      (hlocal _ (List.get_mem source chunk)) (hencloses chunk)
  choose zeroChunks hspans using hexists
  let certificate : ChunkCertificate f source.length := {
    counts := fun chunk => (source.get chunk).entries.length
    chunks := zeroChunks
    orderedSpans := by
      intro left right hlt
      rw [(hspans left).2, (hspans right).1]
      exact_mod_cast hvalid.orderedSpans hlt
    contiguousSpans := by
      intro left right hadjacent
      rw [(hspans left).2, (hspans right).1]
      exact_mod_cast hvalid.contiguousSpans hadjacent
  }
  refine ⟨{
    certificate := certificate
    count_eq := ?_
    spanLower_eq := ?_
    spanUpper_eq := ?_
  }⟩
  · intro chunk
    rfl
  · intro chunk
    exact (hspans chunk).1
  · intro chunk
    exact (hspans chunk).2

/-- End-to-end chunked endpoint theorem.  The result uses only ordinary Lean
proofs after the caller supplies its evaluator enclosures, Hardy-Z model, and
matching analytic total-count upper bound. -/
theorem verifyEndpointChunkStream
    {f : ℝ → ℝ} {height : ℝ}
    {source : List RationalEndpointChunk}
    (hcheck : checkEndpointChunkStream source = true)
    (hencloses : ∀ (chunk : Fin source.length)
      (entry : Fin (source.get chunk).entries.length),
      ((source.get chunk).family.entries entry).EnclosesEndpoints f)
    (model : HardyZModel f height)
    (hlower : ∀ chunk : Fin source.length,
      -height ≤ ((source.get chunk).spanLower : ℝ))
    (hupper : ∀ chunk : Fin source.length,
      ((source.get chunk).spanUpper : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height
      (endpointChunkTotalCount source)) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 := by
  obtain ⟨checked⟩ :=
    exists_checkedEndpointChunkCertificate hcheck hencloses
  exact ChunkedZetaVerifierEvidence.all_zeros_on_criticalLine
    (checked.toVerifierEvidence model hlower hupper totalUpper)

end SparkInterval.Zeta
