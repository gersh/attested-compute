/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQGaussianSum
import SparkInterval.Dirichlet.FactoredSmallQRawTrace

/-!
# Raw binary64 certificates for finite Gaussian sums

This module is the exact wire-to-arithmetic bridge for
`FactoredSmallQGaussianSum`.  Every complex disk and every arithmetic bound is
supplied as a raw binary64 word and decoded to an exact rational before the
typed checker is invoked.  Decoding is total and fail-closed: an out-of-range
word, infinity, NaN, or malformed nested witness returns `none`.

The row-count bound is checked before decoding the row list.  Successful
decoding preserves the row count and order exactly, so a producer cannot hide
missing or extra summands behind the decoding boundary.  The final application
theorem exposes the remaining analytic inputs honestly: the caller must prove
that the decoded base disk contains `w` and that each decoded character disk
contains the corresponding exact character value.

This file proves an arithmetic postcondition only.  It does not claim that a
byte parser, compiler, CPU, GPU, or physical execution produced the raw words.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQTrace
open SparkInterval.Dirichlet.FactoredSmallQRawTrace
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum

/-- Decode an optional raw multiplication witness without changing whether
the optional field was present. -/
def decodeOptionalMul : Option ComplexDisk.RawMulCertificate →
    Option (Option ComplexDisk.MulCertificate)
  | none => some none
  | some raw => do
      let certificate ← raw.decode
      pure (some certificate)

/-- Decode an optional raw recurrence step without changing whether the
optional field was present. -/
def decodeOptionalStep : Option RawStepCertificate →
    Option (Option StepCertificate)
  | none => some none
  | some raw => do
      let certificate ← raw.decode
      pure (some certificate)

/-- Raw binary64 form of one finite-Gaussian row. -/
structure RawRowCertificate where
  ordinal : ℕ
  character : ComplexDisk.Raw
  characterTimesZ : ComplexDisk.RawMulCertificate
  oddScale : Option ComplexDisk.RawMulCertificate
  addToSum : ComplexDisk.RawAddCertificate
  advance : Option RawStepCertificate
  deriving Repr, DecidableEq, BEq

namespace RawRowCertificate

/-- Total, fail-closed decoding of one sum row. -/
def decode (raw : RawRowCertificate) : Option RowCertificate := do
  let character ← raw.character.decode
  let characterTimesZ ← raw.characterTimesZ.decode
  let oddScale ← decodeOptionalMul raw.oddScale
  let addToSum ← raw.addToSum.decode
  let advance ← decodeOptionalStep raw.advance
  pure {
    ordinal := raw.ordinal
    character := character
    characterTimesZ := characterTimesZ
    oddScale := oddScale
    addToSum := addToSum
    advance := advance
  }

/-- A successfully decoded row retains exactly the decoded character disk. -/
theorem character_decode_eq {raw : RawRowCertificate}
    {certificate : RowCertificate}
    (hdecode : raw.decode = some certificate) :
    raw.character.decode = some certificate.character := by
  unfold decode at hdecode
  cases hcharacter : raw.character.decode with
  | none => simp [hcharacter] at hdecode
  | some character =>
      cases hterm : raw.characterTimesZ.decode with
      | none => simp [hcharacter, hterm] at hdecode
      | some term =>
          cases hscale : decodeOptionalMul raw.oddScale with
          | none => simp [hcharacter, hterm, hscale] at hdecode
          | some scale =>
              cases hadd : raw.addToSum.decode with
              | none => simp [hcharacter, hterm, hscale, hadd] at hdecode
              | some add =>
                  cases hadvance : decodeOptionalStep raw.advance with
                  | none =>
                      simp [hcharacter, hterm, hscale, hadd, hadvance] at hdecode
                  | some advance =>
                      simp [hcharacter, hterm, hscale, hadd, hadvance] at hdecode
                      subst certificate
                      rfl

end RawRowCertificate

/-- Total, order-preserving decoding of all finite-sum rows. -/
def decodeRows : List RawRowCertificate → Option (List RowCertificate)
  | [] => some []
  | raw :: rest => do
      let row ← raw.decode
      let rows ← decodeRows rest
      pure (row :: rows)

/-- Successful decoding inserts, removes, and reorders no rows. -/
theorem decodeRows_length {rawRows : List RawRowCertificate}
    {rows : List RowCertificate}
    (hdecode : decodeRows rawRows = some rows) :
    rows.length = rawRows.length := by
  induction rawRows generalizing rows with
  | nil =>
      simp [decodeRows] at hdecode
      subst rows
      rfl
  | cons raw rest ih =>
      simp only [decodeRows] at hdecode
      cases hrow : raw.decode with
      | none => simp [hrow] at hdecode
      | some row =>
          cases hrest : decodeRows rest with
          | none => simp [hrow, hrest] at hdecode
          | some decoded =>
              simp [hrow, hrest] at hdecode
              subst rows
              simp [ih hrest]

/-- Wire-level character containment, stated directly against each raw row's
decoded character disk. -/
def RawContainsCharacters (rawRows : List RawRowCertificate)
    (characters : List ℂ) : Prop :=
  List.Forall₂ (fun raw character =>
    ∃ disk : ComplexDisk,
      raw.character.decode = some disk ∧ disk.ContainsComplex character)
    rawRows characters

/-- Raw character containment transports through successful row decoding. -/
theorem decodeRows_containsCharacters
    {rawRows : List RawRowCertificate} {rows : List RowCertificate}
    {characters : List ℂ}
    (hdecode : decodeRows rawRows = some rows)
    (hcontains : RawContainsCharacters rawRows characters) :
    ContainsCharacters rows characters := by
  induction rawRows generalizing rows characters with
  | nil =>
      simp [decodeRows] at hdecode
      subst rows
      cases hcontains
      simp [ContainsCharacters]
  | cons raw rest ih =>
      cases hcontains with
      | cons hcharacter hcharacters =>
          simp only [decodeRows] at hdecode
          cases hrow : raw.decode with
          | none => simp [hrow] at hdecode
          | some row =>
              cases hrest : decodeRows rest with
              | none => simp [hrow, hrest] at hdecode
              | some decoded =>
                  simp [hrow, hrest] at hdecode
                  subst rows
                  rcases hcharacter with ⟨disk, hdisk, hdiskContains⟩
                  have hsame := RawRowCertificate.character_decode_eq hrow
                  rw [hdisk] at hsame
                  have hdiskEq : disk = row.character := Option.some.inj hsame
                  subst disk
                  exact List.Forall₂.cons hdiskContains
                    (ih hrest hcharacters)

/-- Raw binary64 form of a complete finite-Gaussian sum trace. -/
structure RawSumTraceCertificate where
  oddParity : Bool
  truncation : ℕ
  seed : RawTraceCertificate
  initialSum : ComplexDisk.Raw
  rows : List RawRowCertificate
  deriving Repr, DecidableEq, BEq

namespace RawSumTraceCertificate

/-- Decode every binary64 field to an exact rational typed certificate. -/
def decode (raw : RawSumTraceCertificate) : Option SumTraceCertificate := do
  let seed ← raw.seed.decode
  let initialSum ← raw.initialSum.decode
  let rows ← decodeRows raw.rows
  pure {
    oddParity := raw.oddParity
    truncation := raw.truncation
    seed := seed
    initialSum := initialSum
    rows := rows
  }

/-- Complete decoding retains the exact decoded recurrence base. -/
theorem seed_base_decode_eq {raw : RawSumTraceCertificate}
    {certificate : SumTraceCertificate}
    (hdecode : raw.decode = some certificate) :
    raw.seed.base.decode = some certificate.seed.base := by
  unfold decode at hdecode
  cases hseed : raw.seed.decode with
  | none => simp [hseed] at hdecode
  | some seed =>
      cases hinitial : raw.initialSum.decode with
      | none => simp [hseed, hinitial] at hdecode
      | some initialSum =>
          cases hrows : decodeRows raw.rows with
          | none => simp [hseed, hinitial, hrows] at hdecode
          | some rows =>
              simp [hseed, hinitial, hrows] at hdecode
              subst certificate
              exact RawTraceCertificate.base_decode_eq hseed

/-- Complete decoding preserves the raw/typed row correspondence. -/
theorem rows_decode_eq {raw : RawSumTraceCertificate}
    {certificate : SumTraceCertificate}
    (hdecode : raw.decode = some certificate) :
    decodeRows raw.rows = some certificate.rows := by
  unfold decode at hdecode
  cases hseed : raw.seed.decode with
  | none => simp [hseed] at hdecode
  | some seed =>
      cases hinitial : raw.initialSum.decode with
      | none => simp [hseed, hinitial] at hdecode
      | some initialSum =>
          cases hrows : decodeRows raw.rows with
          | none => simp [hseed, hinitial, hrows] at hdecode
          | some rows =>
              simp [hseed, hinitial, hrows] at hdecode
              subst certificate
              rfl

/-- Successful complete decoding preserves the raw row count. -/
theorem rows_length_eq {raw : RawSumTraceCertificate}
    {certificate : SumTraceCertificate}
    (hdecode : raw.decode = some certificate) :
    certificate.rows.length = raw.rows.length :=
  decodeRows_length (rows_decode_eq hdecode)

theorem oddParity_eq {raw : RawSumTraceCertificate}
    {certificate : SumTraceCertificate}
    (hdecode : raw.decode = some certificate) :
    certificate.oddParity = raw.oddParity := by
  unfold decode at hdecode
  cases hseed : raw.seed.decode with
  | none => simp [hseed] at hdecode
  | some seed =>
      cases hinitial : raw.initialSum.decode with
      | none => simp [hseed, hinitial] at hdecode
      | some initialSum =>
          cases hrows : decodeRows raw.rows with
          | none => simp [hseed, hinitial, hrows] at hdecode
          | some rows =>
              simp [hseed, hinitial, hrows] at hdecode
              subst certificate
              rfl

theorem truncation_eq {raw : RawSumTraceCertificate}
    {certificate : SumTraceCertificate}
    (hdecode : raw.decode = some certificate) :
    certificate.truncation = raw.truncation := by
  unfold decode at hdecode
  cases hseed : raw.seed.decode with
  | none => simp [hseed] at hdecode
  | some seed =>
      cases hinitial : raw.initialSum.decode with
      | none => simp [hseed, hinitial] at hdecode
      | some initialSum =>
          cases hrows : decodeRows raw.rows with
          | none => simp [hseed, hinitial, hrows] at hdecode
          | some rows =>
              simp [hseed, hinitial, hrows] at hdecode
              subst certificate
              rfl

/-- Proposition recovered from an accepted raw sum certificate. -/
def Validated (raw : RawSumTraceCertificate) (maxTerms : ℕ) : Prop :=
  ∃ certificate : SumTraceCertificate,
    raw.decode = some certificate ∧ certificate.Accepted maxTerms

/-- Fail-closed wire checker.  The raw row bound is deliberately the first
operation, so an oversized untrusted list is rejected before its binary64
fields are decoded.  The typed checker repeats all count and arithmetic
obligations after decoding. -/
def check (raw : RawSumTraceCertificate) (maxTerms : ℕ) : Bool :=
  decide (raw.rows.length ≤ maxTerms) &&
    match raw.decode with
    | none => false
    | some certificate => certificate.check maxTerms

theorem checker_sound {raw : RawSumTraceCertificate} {maxTerms : ℕ}
    (hcheck : raw.check maxTerms = true) : raw.Validated maxTerms := by
  unfold check at hcheck
  simp only [Bool.and_eq_true, decide_eq_true_eq] at hcheck
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hcheck
  | some certificate =>
      refine ⟨certificate, hdecode, SumTraceCertificate.checker_sound ?_⟩
      simpa [hdecode] using hcheck.2

/-- Typed application form for a specifically named decoding. -/
theorem decoded_output_contains_exact_finite_sum
    {raw : RawSumTraceCertificate} {certificate : SumTraceCertificate}
    {maxTerms : ℕ} {characters : List ℂ} {w : ℂ}
    {base : ComplexDisk}
    (hcheck : raw.check maxTerms = true)
    (hdecode : raw.decode = some certificate)
    (hbaseDecode : raw.seed.base.decode = some base)
    (hbase : base.ContainsComplex w)
    (hcharacters : RawContainsCharacters raw.rows characters) :
    characters.length = raw.truncation ∧
      certificate.output.ContainsComplex
        (exactFiniteSum raw.oddParity w characters) := by
  have htypedCheck : certificate.check maxTerms = true := by
    unfold check at hcheck
    simp only [Bool.and_eq_true, decide_eq_true_eq] at hcheck
    simpa [hdecode] using hcheck.2
  have hbaseSame := seed_base_decode_eq hdecode
  rw [hbaseDecode] at hbaseSame
  have hbaseEq : base = certificate.seed.base := Option.some.inj hbaseSame
  have htypedBase : certificate.seed.base.ContainsComplex w := by
    rw [← hbaseEq]
    exact hbase
  have htypedCharacters : ContainsCharacters certificate.rows characters :=
    decodeRows_containsCharacters (rows_decode_eq hdecode) hcharacters
  have hresult := SumTraceCertificate.output_contains_exact_finite_sum
    htypedCheck htypedBase htypedCharacters
  constructor
  · rw [← truncation_eq hdecode]
    exact hresult.1
  · rw [← oddParity_eq hdecode]
    exact hresult.2

/-- Pure wire-level application theorem.  Acceptance constructs the unique
typed exact-rational certificate and proves its output encloses the complete
finite Gaussian sum named by the raw parity and truncation fields. -/
theorem accepted_output_contains_exact_finite_sum_of_base_decode
    {raw : RawSumTraceCertificate} {maxTerms : ℕ}
    {characters : List ℂ} {w : ℂ} {base : ComplexDisk}
    (hcheck : raw.check maxTerms = true)
    (hbaseDecode : raw.seed.base.decode = some base)
    (hbase : base.ContainsComplex w)
    (hcharacters : RawContainsCharacters raw.rows characters) :
    ∃ certificate : SumTraceCertificate,
      raw.decode = some certificate ∧
      characters.length = raw.truncation ∧
      certificate.output.ContainsComplex
        (exactFiniteSum raw.oddParity w characters) := by
  rcases checker_sound hcheck with ⟨certificate, hdecode, _⟩
  have hresult := decoded_output_contains_exact_finite_sum
    hcheck hdecode hbaseDecode hbase hcharacters
  exact ⟨certificate, hdecode, hresult⟩

end RawSumTraceCertificate

end SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum
