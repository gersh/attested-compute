import SparkInterval.Zeta.EndpointCertificate

/-!
# One-pass endpoint-family checking

This module gives the endpoint checker a resumable, chunk-oriented execution
shape.  Its rolling state contains only the immediately preceding bracket.
Each new bracket is checked locally and compared only with that predecessor.
The state can be passed from one chunk to the next, and `runChunk_append` proves
that doing so is exactly the same logical computation as checking the
concatenated list.

For theorem-level convenience this implementation consumes a `List`.  It does
not provide a byte parser, file reader, bounded allocator, rolling digest, or
proof about an actual storage/runtime implementation.  A production streaming
parser must construct each `RationalBracket`, call the same transition, and
separately establish its resource and byte-integrity properties.

Successful one-pass checking is proved to imply every local
`RationalBracket.IsValid` condition and the existing finite family's global
all-pairs ordering.  The latter reuses
`RationalBracketFamily.isValid_iff_checkCondition`: adjacent comparisons are
linear, while local nondegeneracy and transitivity yield all-pairs separation.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

/-- Constant-size logical state carried between endpoint chunks. -/
structure EndpointStreamState where
  previous : Option RationalBracket := none
  deriving DecidableEq, Repr

namespace EndpointStreamState

/-- Propositional condition for accepting one bracket after the current state. -/
def AcceptsNext (state : EndpointStreamState)
    (current : RationalBracket) : Prop :=
  current.IsValid ∧
    match state.previous with
    | none => True
    | some previous => previous.upper < current.lower

instance (state : EndpointStreamState) (current : RationalBracket) :
    Decidable (state.AcceptsNext current) := by
  unfold AcceptsNext
  split <;> infer_instance

/-- Executable form of `AcceptsNext`. -/
def acceptsNext (state : EndpointStreamState)
    (current : RationalBracket) : Bool :=
  current.check &&
    match state.previous with
    | none => true
    | some previous => decide (previous.upper < current.lower)

@[simp] theorem acceptsNext_eq_true
    {state : EndpointStreamState} {current : RationalBracket} :
    state.acceptsNext current = true ↔ state.AcceptsNext current := by
  rcases state with ⟨previous⟩
  cases previous <;> simp [acceptsNext, AcceptsNext]

/-- Check one bracket and retain only that bracket as the next rolling state. -/
def step? (state : EndpointStreamState)
    (current : RationalBracket) : Option EndpointStreamState :=
  if state.acceptsNext current = true then
    some { previous := some current }
  else
    none

end EndpointStreamState

/-- Recursive logical meaning of accepting a remaining stream from a previous
bracket. -/
def EndpointStreamValidFrom :
    Option RationalBracket → List RationalBracket → Prop
  | _, [] => True
  | previous, current :: rest =>
      current.IsValid ∧
        (match previous with
          | none => True
          | some prior => prior.upper < current.lower) ∧
        EndpointStreamValidFrom (some current) rest

/-- Run one list chunk.  Failure is `none`; success returns the state to feed
into the next chunk. -/
def runEndpointChunk :
    EndpointStreamState → List RationalBracket → Option EndpointStreamState
  | state, [] => some state
  | state, current :: rest => do
      let next ← state.step? current
      runEndpointChunk next rest

/-- Chunk resumption is definitionally the same one-pass check as list
concatenation. -/
theorem runEndpointChunk_append (state : EndpointStreamState)
    (left right : List RationalBracket) :
    runEndpointChunk state (left ++ right) =
      (runEndpointChunk state left).bind fun next =>
        runEndpointChunk next right := by
  induction left generalizing state with
  | nil => simp [runEndpointChunk]
  | cons current rest induction =>
      simp only [List.cons_append, runEndpointChunk]
      cases hstep : state.step? current with
      | none => simp
      | some next => simp [induction]

/-- The executable chunk runner reflects exactly its recursive logical
condition. -/
theorem runEndpointChunk_isSome_iff
    (state : EndpointStreamState) (entries : List RationalBracket) :
    (runEndpointChunk state entries).isSome = true ↔
      EndpointStreamValidFrom state.previous entries := by
  induction entries generalizing state with
  | nil => simp [runEndpointChunk, EndpointStreamValidFrom]
  | cons current rest induction =>
      by_cases haccept : state.acceptsNext current = true
      · have hmeaning : state.AcceptsNext current :=
          EndpointStreamState.acceptsNext_eq_true.mp haccept
        change current.IsValid ∧
          (match state.previous with
            | none => True
            | some prior => prior.upper < current.lower) at hmeaning
        simp [runEndpointChunk, EndpointStreamState.step?, haccept,
          EndpointStreamValidFrom, induction]
        constructor
        · intro hrest
          exact ⟨hmeaning.1, hmeaning.2, hrest⟩
        · intro hall
          exact hall.2.2
      · have hmeaning : ¬state.AcceptsNext current := by
          intro h
          exact haccept (EndpointStreamState.acceptsNext_eq_true.mpr h)
        change ¬(current.IsValid ∧
          (match state.previous with
            | none => True
            | some prior => prior.upper < current.lower)) at hmeaning
        simp [runEndpointChunk, EndpointStreamState.step?, haccept,
          EndpointStreamValidFrom]
        intro hcurrent hseparated
        exact False.elim (hmeaning ⟨hcurrent, hseparated⟩)

/-- Start a fresh one-pass endpoint-family check. -/
def checkEndpointStream (entries : List RationalBracket) : Bool :=
  (runEndpointChunk {} entries).isSome

theorem checkEndpointStream_sound {entries : List RationalBracket}
    (hcheck : checkEndpointStream entries = true) :
    EndpointStreamValidFrom none entries := by
  exact (runEndpointChunk_isSome_iff {} entries).mp hcheck

namespace EndpointStreamValidFrom

/-- Every member of a successfully checked stream satisfies the local exact
rational bracket predicate. -/
theorem allLocal {previous : Option RationalBracket}
    {entries : List RationalBracket}
    (hvalid : EndpointStreamValidFrom previous entries) :
    ∀ entry ∈ entries, entry.IsValid := by
  induction entries generalizing previous with
  | nil => simp
  | cons current rest induction =>
      intro entry hmem
      rcases List.mem_cons.mp hmem with rfl | hrest
      · exact hvalid.1
      · exact induction hvalid.2.2 entry hrest

/-- The predecessor checks imply the usual adjacent-list chain. -/
theorem isChain {previous : Option RationalBracket}
    {entries : List RationalBracket}
    (hvalid : EndpointStreamValidFrom previous entries) :
    entries.IsChain (fun left right => left.upper < right.lower) := by
  induction entries generalizing previous with
  | nil => exact .nil
  | cons current rest induction =>
      cases rest with
      | nil => exact .singleton current
      | cons next tail =>
          have hrest : EndpointStreamValidFrom (some current) (next :: tail) :=
            hvalid.2.2
          exact .cons_cons hrest.2.1 (induction hrest)

end EndpointStreamValidFrom

/-- Canonical finite-family view of a checked list. -/
def endpointFamilyOfList (entries : List RationalBracket) :
    RationalBracketFamily entries.length where
  entries index := entries.get index

/-- One-pass success supplies the existing family's linear check condition. -/
theorem checkEndpointStream_checkCondition
    {entries : List RationalBracket}
    (hcheck : checkEndpointStream entries = true) :
    (endpointFamilyOfList entries).CheckCondition := by
  have hstream := checkEndpointStream_sound hcheck
  have hlocal := EndpointStreamValidFrom.allLocal hstream
  have hchain := EndpointStreamValidFrom.isChain hstream
  constructor
  · intro index
    exact hlocal _ (List.get_mem entries index)
  · cases entries with
    | nil => trivial
    | cons first rest =>
        change ∀ index : Fin rest.length,
          ((first :: rest).get index.castSucc).upper <
            ((first :: rest).get index.succ).lower
        intro index
        have hadjacent := hchain.getElem index.1 (by
          exact Nat.succ_lt_succ index.isLt)
        simpa only [List.get_eq_getElem, Fin.val_castSucc, Fin.val_succ] using
          hadjacent

/-- The existing adjacent-to-all-pairs theorem upgrades streaming success to
the full finite-family validity predicate. -/
theorem checkEndpointStream_isValid
    {entries : List RationalBracket}
    (hcheck : checkEndpointStream entries = true) :
    (endpointFamilyOfList entries).IsValid :=
  RationalBracketFamily.isValid_iff_checkCondition.mpr
    (checkEndpointStream_checkCondition hcheck)

/-- Executable family-check consequence of the one-pass stream check. -/
theorem checkEndpointStream_familyCheck
    {entries : List RationalBracket}
    (hcheck : checkEndpointStream entries = true) :
    (endpointFamilyOfList entries).check = true :=
  RationalBracketFamily.check_eq_true.mpr
    (checkEndpointStream_isValid hcheck)

/-- Explicit local-validity projection requested by downstream chunk users. -/
theorem checkEndpointStream_local
    {entries : List RationalBracket}
    (hcheck : checkEndpointStream entries = true)
    (index : Fin entries.length) :
    ((endpointFamilyOfList entries).entries index).IsValid :=
  (checkEndpointStream_isValid hcheck).1 index

/-- Explicit global all-pairs ordering obtained from only predecessor checks. -/
theorem checkEndpointStream_allPairs
    {entries : List RationalBracket}
    (hcheck : checkEndpointStream entries = true)
    {left right : Fin entries.length} (hlt : left < right) :
    ((endpointFamilyOfList entries).entries left).upper <
      ((endpointFamilyOfList entries).entries right).lower :=
  (checkEndpointStream_isValid hcheck).2 hlt

end SparkInterval.Zeta
