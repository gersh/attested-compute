/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQTrace

/-!
# Exact finite-Gaussian sum certificates

This module adds the accumulation layer that sits above the checked Gaussian
power recurrence.  Each one-based row binds a character disk to the current
`w^(n^2)` disk, optionally multiplies by the exact disk `<n, 0, 0>` for odd
characters, and links a checked disk addition into the running sum.  Every
nonfinal row also carries the checked recurrence transition used by the next
row; the final row must carry no transition.

The checker enforces `rows.length = truncation`, rather than accepting an
arbitrary prefix below a maximum.  The application theorem leaves containment
of the exact character values as an explicit premise and proves that the
final disk contains the corresponding exact finite Gaussian sum.

This is an arithmetic certificate theorem.  It does not assert that a binary
frame was parsed, that a CUDA instruction trace produced the witnesses, or
that a source-wide conductor/frequency manifest is complete.  Prefactor
multiplication, analytic tails, the DFT, and physical execution are separate
composition edges.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQGaussianSum

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQTrace

/-- The exact zero disk used before the first Gaussian row. -/
def zeroDisk : ComplexDisk := ⟨0, 0, 0⟩

/-- The exact real point disk used for the odd-character factor `n`. -/
def ordinalDisk (ordinal : ℕ) : ComplexDisk := ⟨ordinal, 0, 0⟩

theorem zeroDisk_contains_zero : zeroDisk.ContainsComplex 0 := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : zeroDisk.center = (0 : ℂ) := by
    apply Complex.ext <;>
      norm_num [zeroDisk, ComplexDisk.center]
  rw [hcenter]
  simp [zeroDisk]

theorem ordinalDisk_contains (ordinal : ℕ) :
    (ordinalDisk ordinal).ContainsComplex (ordinal : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (ordinalDisk ordinal).center = (ordinal : ℂ) := by
    apply Complex.ext <;>
      norm_num [ordinalDisk, ComplexDisk.center]
  rw [hcenter]
  simp [ordinalDisk]

/-- Exact mathematical summand represented by a one-based row. -/
def exactTerm (oddParity : Bool) (ordinal : ℕ)
    (character w : ℂ) : ℂ :=
  (if oddParity then (ordinal : ℂ) * character else character) *
    w ^ (ordinal ^ 2)

/-- Exact suffix of the finite Gaussian sum, starting at a one-based
ordinal. -/
def exactSumFrom (oddParity : Bool) (w : ℂ) : ℕ → List ℂ → ℂ
  | _, [] => 0
  | ordinal, character :: rest =>
      exactTerm oddParity ordinal character w +
        exactSumFrom oddParity w (ordinal + 1) rest

/-- Source-facing finite Gaussian sum.  List position zero is row `n = 1`. -/
def exactFiniteSum (oddParity : Bool) (w : ℂ)
    (characters : List ℂ) : ℂ :=
  exactSumFrom oddParity w 1 characters

/-- Recurrence and sum disks immediately before a row is evaluated. -/
structure SumState where
  recurrence : DiskGaussianState
  sum : ComplexDisk
  deriving Repr, DecidableEq, BEq

/-- Arithmetic witnesses for one finite-Gaussian row.  `advance` is present
exactly when another row follows. -/
structure RowCertificate where
  ordinal : ℕ
  character : ComplexDisk
  characterTimesZ : ComplexDisk.MulCertificate
  oddScale : Option ComplexDisk.MulCertificate
  addToSum : ComplexDisk.AddCertificate
  advance : Option StepCertificate
  deriving Repr, DecidableEq, BEq

namespace RowCertificate

/-- The disk passed to the running-sum addition.  Ill-shaped parity choices
are rejected by `WeightWellFormed`. -/
def weightedOutput (oddParity : Bool) (certificate : RowCertificate) :
    ComplexDisk :=
  match oddParity, certificate.oddScale with
  | false, none => certificate.characterTimesZ.output
  | true, some scale => scale.output
  | _, _ => certificate.characterTimesZ.output

/-- For even characters no scaling record is permitted.  For odd characters
the record must be a checked multiplication by the exact point disk
`<ordinal, 0, 0>`. -/
def WeightWellFormed (certificate : RowCertificate)
    (oddParity : Bool) : Prop :=
  match oddParity, certificate.oddScale with
  | false, none => True
  | true, some scale =>
      scale.check = true ∧
      scale.left = certificate.characterTimesZ.output ∧
      scale.right = ordinalDisk certificate.ordinal
  | _, _ => False

instance instDecidableWeightWellFormed (certificate : RowCertificate)
    (oddParity : Bool) : Decidable (certificate.WeightWellFormed oddParity) := by
  cases oddParity <;> cases hscale : certificate.oddScale <;>
    simp [WeightWellFormed, hscale] <;> infer_instance

/-- Exact row ordinal, checked arithmetic, and state links. -/
def CoreWellFormed (certificate : RowCertificate) (oddParity : Bool)
    (expectedOrdinal : ℕ) (current : SumState) : Prop :=
  certificate.ordinal = expectedOrdinal ∧
  certificate.characterTimesZ.check = true ∧
  certificate.characterTimesZ.left = certificate.character ∧
  certificate.characterTimesZ.right = current.recurrence.z ∧
  certificate.WeightWellFormed oddParity ∧
  certificate.addToSum.check = true ∧
  certificate.addToSum.left = current.sum ∧
  certificate.addToSum.right = certificate.weightedOutput oddParity

instance instDecidableCoreWellFormed (certificate : RowCertificate)
    (oddParity : Bool) (expectedOrdinal : ℕ) (current : SumState) :
    Decidable (certificate.CoreWellFormed oddParity expectedOrdinal current) := by
  unfold CoreWellFormed
  infer_instance

def checkCore (certificate : RowCertificate) (oddParity : Bool)
    (expectedOrdinal : ℕ) (current : SumState) : Bool :=
  decide (certificate.CoreWellFormed oddParity expectedOrdinal current)

theorem checkCore_sound {certificate : RowCertificate} {oddParity : Bool}
    {expectedOrdinal : ℕ} {current : SumState}
    (hcheck : certificate.checkCore oddParity expectedOrdinal current = true) :
    certificate.CoreWellFormed oddParity expectedOrdinal current :=
  of_decide_eq_true hcheck

/-- A well-formed row transports exact character, power, and partial-sum
containment to its proposed output sum. -/
theorem output_contains_term {certificate : RowCertificate}
    {oddParity : Bool} {index : ℕ} {current : SumState}
    {character w accumulated : ℂ}
    (hvalid : certificate.CoreWellFormed oddParity (index + 1) current)
    (hcharacter : certificate.character.ContainsComplex character)
    (hrecurrence : current.recurrence.ContainsPowers w index)
    (hsum : current.sum.ContainsComplex accumulated) :
    certificate.addToSum.output.ContainsComplex
      (accumulated + exactTerm oddParity (index + 1) character w) := by
  rcases hvalid with
    ⟨hordinal, htermCheck, htermLeft, htermRight, hweight,
      haddCheck, haddLeft, haddRight⟩
  have htermLeftContains :
      certificate.characterTimesZ.left.ContainsComplex character := by
    rw [htermLeft]
    exact hcharacter
  have htermRightContains :
      certificate.characterTimesZ.right.ContainsComplex
        (w ^ ((index + 1) ^ 2)) := by
    rw [htermRight]
    exact hrecurrence.1
  have hterm := ComplexDisk.MulCertificate.output_contains_mul
    htermCheck htermLeftContains htermRightContains
  have hweighted :
      (certificate.weightedOutput oddParity).ContainsComplex
        (exactTerm oddParity (index + 1) character w) := by
    cases oddParity with
    | false =>
        cases hscale : certificate.oddScale with
        | none =>
            simpa [weightedOutput, exactTerm, hscale] using hterm
        | some scale =>
            simp [WeightWellFormed, hscale] at hweight
    | true =>
        cases hscale : certificate.oddScale with
        | none =>
            simp [WeightWellFormed, hscale] at hweight
        | some scale =>
            simp only [WeightWellFormed, hscale] at hweight
            rcases hweight with ⟨hscaleCheck, hscaleLeft, hscaleRight⟩
            have hscaleLeftContains :
                scale.left.ContainsComplex
                  (character * w ^ ((index + 1) ^ 2)) := by
              rw [hscaleLeft]
              exact hterm
            have hscaleRightContains :
                scale.right.ContainsComplex (index + 1 : ℂ) := by
              rw [hscaleRight, hordinal]
              simpa using ordinalDisk_contains (index + 1)
            have hscaled := ComplexDisk.MulCertificate.output_contains_mul
              hscaleCheck hscaleLeftContains hscaleRightContains
            rw [show
              (character * w ^ ((index + 1) ^ 2)) * (index + 1 : ℂ) =
                exactTerm true (index + 1) character w by
                  simp [exactTerm]
                  ring] at hscaled
            simpa [weightedOutput, hscale] using hscaled
  have haddLeftContains :
      certificate.addToSum.left.ContainsComplex accumulated := by
    rw [haddLeft]
    exact hsum
  have haddRightContains :
      certificate.addToSum.right.ContainsComplex
        (exactTerm oddParity (index + 1) character w) := by
    rw [haddRight]
    exact hweighted
  exact ComplexDisk.AddCertificate.output_contains_add
    haddCheck haddLeftContains haddRightContains

end RowCertificate

/-- Exact linked-row predicate.  Every nonfinal row must advance the Gaussian
recurrence and the final row must not, matching the source loop's
`n != truncation` guard. -/
def LinkedRows (square : ComplexDisk) (oddParity : Bool) :
    ℕ → SumState → List RowCertificate → Prop
  | _, _, [] => True
  | index, current, row :: [] =>
      row.CoreWellFormed oddParity (index + 1) current ∧
      row.advance = none
  | index, current, row :: next :: rest =>
      row.CoreWellFormed oddParity (index + 1) current ∧
      match row.advance with
      | none => False
      | some step =>
          step.WellFormed square current.recurrence ∧
          LinkedRows square oddParity (index + 1)
            ⟨step.output, row.addToSum.output⟩ (next :: rest)

/-- Boolean replay of the complete row trace. -/
def checkRows (square : ComplexDisk) (oddParity : Bool) :
    ℕ → SumState → List RowCertificate → Bool
  | _, _, [] => true
  | index, current, row :: [] =>
      row.checkCore oddParity (index + 1) current &&
        decide (row.advance = none)
  | index, current, row :: next :: rest =>
      row.checkCore oddParity (index + 1) current &&
        match row.advance with
        | none => false
        | some step =>
            step.check square current.recurrence &&
              checkRows square oddParity (index + 1)
                ⟨step.output, row.addToSum.output⟩ (next :: rest)

theorem checkRows_sound {square : ComplexDisk} {oddParity : Bool}
    {index : ℕ} {current : SumState} {rows : List RowCertificate}
    (hcheck : checkRows square oddParity index current rows = true) :
    LinkedRows square oddParity index current rows := by
  induction rows generalizing index current with
  | nil => simp [LinkedRows]
  | cons row rest ih =>
      cases rest with
      | nil =>
          simp only [checkRows, Bool.and_eq_true, decide_eq_true_eq] at hcheck
          exact ⟨RowCertificate.checkCore_sound hcheck.1, hcheck.2⟩
      | cons next rest =>
          simp only [checkRows, Bool.and_eq_true] at hcheck
          refine ⟨RowCertificate.checkCore_sound hcheck.1, ?_⟩
          cases hadvance : row.advance with
          | none => simp [hadvance] at hcheck
          | some step =>
              simp only [hadvance, Bool.and_eq_true] at hcheck
              exact ⟨StepCertificate.check_sound hcheck.2.1,
                ih hcheck.2.2⟩

/-- Replay proposed row outputs.  On an accepted trace, `advance` is present
exactly for the nonfinal rows. -/
def runRows : SumState → List RowCertificate → SumState
  | current, [] => current
  | current, row :: rest =>
      let recurrence := match row.advance with
        | none => current.recurrence
        | some step => step.output
      runRows ⟨recurrence, row.addToSum.output⟩ rest

/-- Exact characters supplied to the application theorem correspond
position-for-position to the disks carried by the certificate. -/
def ContainsCharacters (rows : List RowCertificate)
    (characters : List ℂ) : Prop :=
  List.Forall₂ (fun row character =>
    row.character.ContainsComplex character) rows characters

/-- A linked row trace transports the power and partial-sum invariants through
the exact finite Gaussian suffix. -/
theorem runRows_contains_sum {square : ComplexDisk} {oddParity : Bool}
    {index : ℕ} {current : SumState} {rows : List RowCertificate}
    {characters : List ℂ} {w accumulated : ℂ}
    (hlinked : LinkedRows square oddParity index current rows)
    (hsquare : square.ContainsComplex (w ^ 2))
    (hrecurrence : current.recurrence.ContainsPowers w index)
    (hsum : current.sum.ContainsComplex accumulated)
    (hcharacters : ContainsCharacters rows characters) :
    (runRows current rows).sum.ContainsComplex
      (accumulated + exactSumFrom oddParity w (index + 1) characters) := by
  induction rows generalizing index current characters accumulated with
  | nil =>
      cases hcharacters
      simpa [runRows, exactSumFrom] using hsum
  | cons row rest ih =>
      cases hcharacters with
      | cons hcharacter hcharacters =>
          cases rest with
          | nil =>
              simp only [LinkedRows] at hlinked
              cases hcharacters
              have hrow := RowCertificate.output_contains_term
                hlinked.1 hcharacter hrecurrence hsum
              have hnone := hlinked.2
              simp [runRows, exactSumFrom, hnone]
              simpa [add_assoc] using hrow
          | cons next rest =>
              simp only [LinkedRows] at hlinked
              have hrow := RowCertificate.output_contains_term
                hlinked.1 hcharacter hrecurrence hsum
              cases hadvance : row.advance with
              | none => simp [hadvance] at hlinked
              | some step =>
                  have htransition := hlinked.2
                  rw [hadvance] at htransition
                  have hstep :
                      step.WellFormed square current.recurrence := by
                    exact htransition.1
                  have htail :
                      LinkedRows square oddParity (index + 1)
                        ⟨step.output, row.addToSum.output⟩ (next :: rest) := by
                    exact htransition.2
                  have hnextRecurrence :=
                    StepCertificate.output_contains_powers
                      hstep hsquare hrecurrence
                  have hresult := ih htail hnextRecurrence hrow hcharacters
                  simpa [runRows, hadvance, exactSumFrom, add_assoc] using hresult

/-- Complete typed certificate for one parity and one finite truncation.  The
embedded recurrence seed is required to contain no pre-applied steps. -/
structure SumTraceCertificate where
  oddParity : Bool
  truncation : ℕ
  seed : TraceCertificate
  initialSum : ComplexDisk
  rows : List RowCertificate
  deriving Repr, DecidableEq, BEq

namespace SumTraceCertificate

def initialState (certificate : SumTraceCertificate) : SumState :=
  ⟨certificate.seed.initialState, certificate.initialSum⟩

def output (certificate : SumTraceCertificate) : ComplexDisk :=
  (runRows certificate.initialState certificate.rows).sum

/-- Exact count, bounded resource use, checked recurrence initialization, and
the linked arithmetic trace recovered from an accepted certificate. -/
def Accepted (certificate : SumTraceCertificate) (maxTerms : ℕ) : Prop :=
  certificate.rows.length = certificate.truncation ∧
  certificate.truncation ≤ maxTerms ∧
  certificate.seed.check 0 = true ∧
  certificate.initialSum = zeroDisk ∧
  LinkedRows certificate.seed.square.output certificate.oddParity 0
    certificate.initialState certificate.rows

/-- Kernel-reducible checker.  Equality with `truncation` prevents a valid
prefix from being presented as the complete requested sum. -/
def check (certificate : SumTraceCertificate) (maxTerms : ℕ) : Bool :=
  decide (certificate.rows.length = certificate.truncation) &&
  decide (certificate.truncation ≤ maxTerms) &&
  certificate.seed.check 0 &&
  decide (certificate.initialSum = zeroDisk) &&
  checkRows certificate.seed.square.output certificate.oddParity 0
    certificate.initialState certificate.rows

theorem checker_sound {certificate : SumTraceCertificate} {maxTerms : ℕ}
    (hcheck : certificate.check maxTerms = true) :
    certificate.Accepted maxTerms := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1.1.1.1, hcheck.1.1.1.2, hcheck.1.1.2,
    hcheck.1.2, checkRows_sound hcheck.2⟩

/-- Successful checking binds the semantic character list to the exact
declared truncation and proves containment of the exact finite Gaussian sum. -/
theorem output_contains_exact_finite_sum
    {certificate : SumTraceCertificate} {maxTerms : ℕ}
    {characters : List ℂ} {w : ℂ}
    (hcheck : certificate.check maxTerms = true)
    (hbase : certificate.seed.base.ContainsComplex w)
    (hcharacters : ContainsCharacters certificate.rows characters) :
    characters.length = certificate.truncation ∧
    certificate.output.ContainsComplex
      (exactFiniteSum certificate.oddParity w characters) := by
  have haccepted := checker_sound hcheck
  have hseed := TraceCertificate.checker_sound haccepted.2.2.1
  have hsquare := TraceCertificate.square_contains hseed.2.1 hbase
  have hrecurrence := TraceCertificate.initial_contains_powers
    hseed.2.1 hbase
  have hinitialSum : certificate.initialSum.ContainsComplex (0 : ℂ) := by
    rw [haccepted.2.2.2.1]
    exact zeroDisk_contains_zero
  have hsum := runRows_contains_sum haccepted.2.2.2.2 hsquare
    hrecurrence hinitialSum hcharacters
  constructor
  · rw [← haccepted.1]
    exact (List.Forall₂.length_eq hcharacters).symm
  · simpa [output, exactFiniteSum] using hsum

end SumTraceCertificate

end SparkInterval.Dirichlet.FactoredSmallQGaussianSum
