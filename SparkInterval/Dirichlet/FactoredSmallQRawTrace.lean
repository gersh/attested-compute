/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQTrace

/-!
# Raw binary64 certificates for factored small-`q` traces

This module is the wire-to-arithmetic bridge for the finite Gaussian
recurrence.  Every disk coordinate, radius, and multiplication bound arrives
as a raw binary64 word.  `RawTraceCertificate.decode` rejects out-of-range
words, infinities, and NaNs and otherwise constructs the typed exact-rational
certificate checked by `FactoredSmallQTrace`.

The structure begins from already-selected `Nat` words.  It is not a
little-endian byte parser.  Both binary64 signed-zero encodings intentionally
decode to the same rational zero, so preservation or canonicalization of the
original signed-zero bit pattern is also an earlier wire-format obligation.

`RawTraceCertificate.check maxSteps` fails closed on either a decoding error,
an arithmetic or link failure, or an oversized trace.  Its application
theorem consequently speaks about the exact `ExactGaussianState.after`
recurrence.  This remains an arithmetic certificate boundary: it does not
claim that a byte parser, CUDA instruction trace, or production manifest
produced the supplied raw words.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawTrace

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQSeed
open SparkInterval.Dirichlet.FactoredSmallQTrace

/-- Raw binary64 witnesses for the two products in one linked recurrence
row. -/
structure RawStepCertificate where
  zTimesRatio : ComplexDisk.RawMulCertificate
  ratioTimesSquare : ComplexDisk.RawMulCertificate
  deriving Repr, DecidableEq, BEq

namespace RawStepCertificate

/-- Total, fail-closed decoding of one recurrence row. -/
def decode (raw : RawStepCertificate) : Option StepCertificate := do
  let zTimesRatio ← raw.zTimesRatio.decode
  let ratioTimesSquare ← raw.ratioTimesSquare.decode
  pure ⟨zTimesRatio, ratioTimesSquare⟩

end RawStepCertificate

/-- Total, order-preserving decoding of all recurrence rows. -/
def decodeSteps : List RawStepCertificate → Option (List StepCertificate)
  | [] => some []
  | raw :: rest => do
      let step ← raw.decode
      let steps ← decodeSteps rest
      pure (step :: steps)

/-- Successful decoding preserves row count exactly. -/
theorem decodeSteps_length {rawSteps : List RawStepCertificate}
    {steps : List StepCertificate}
    (hdecode : decodeSteps rawSteps = some steps) :
    steps.length = rawSteps.length := by
  induction rawSteps generalizing steps with
  | nil =>
      simp [decodeSteps] at hdecode
      subst steps
      rfl
  | cons raw rest ih =>
      simp only [decodeSteps] at hdecode
      cases hstep : raw.decode with
      | none => simp [hstep] at hdecode
      | some step =>
          cases hrest : decodeSteps rest with
          | none => simp [hstep, hrest] at hdecode
          | some decoded =>
              simp [hstep, hrest] at hdecode
              subst steps
              simp [ih hrest]

/-- A raw binary64 trace.  Equality links are intentionally not duplicated
here: after exact decoding, the typed checker recomputes every link. -/
structure RawTraceCertificate where
  base : ComplexDisk.Raw
  square : ComplexDisk.RawMulCertificate
  cube : ComplexDisk.RawMulCertificate
  steps : List RawStepCertificate
  deriving Repr, DecidableEq, BEq

namespace RawTraceCertificate

/-- Decode every binary64 field to its exact rational value. -/
def decode (raw : RawTraceCertificate) : Option TraceCertificate := do
  let base ← raw.base.decode
  let square ← raw.square.decode
  let cube ← raw.cube.decode
  let steps ← decodeSteps raw.steps
  pure { base, square, cube, steps }

/-- Decoding a complete trace preserves the exact decoded base disk. -/
theorem base_decode_eq {raw : RawTraceCertificate}
    {certificate : TraceCertificate}
    (hdecode : raw.decode = some certificate) :
    raw.base.decode = some certificate.base := by
  unfold decode at hdecode
  cases hbase : raw.base.decode with
  | none => simp [hbase] at hdecode
  | some base =>
      cases hsquare : raw.square.decode with
      | none => simp [hbase, hsquare] at hdecode
      | some square =>
          cases hcube : raw.cube.decode with
          | none => simp [hbase, hsquare, hcube] at hdecode
          | some cube =>
              cases hsteps : decodeSteps raw.steps with
              | none => simp [hbase, hsquare, hcube, hsteps] at hdecode
              | some steps =>
                  simp [hbase, hsquare, hcube, hsteps] at hdecode
                  subst certificate
                  rfl

/-- Successful wire decoding cannot insert, drop, or duplicate recurrence
rows. -/
theorem steps_length_eq {raw : RawTraceCertificate}
    {certificate : TraceCertificate}
    (hdecode : raw.decode = some certificate) :
    certificate.steps.length = raw.steps.length := by
  unfold decode at hdecode
  cases hbase : raw.base.decode with
  | none => simp [hbase] at hdecode
  | some base =>
      cases hsquare : raw.square.decode with
      | none => simp [hbase, hsquare] at hdecode
      | some square =>
          cases hcube : raw.cube.decode with
          | none => simp [hbase, hsquare, hcube] at hdecode
          | some cube =>
              cases hsteps : decodeSteps raw.steps with
              | none => simp [hbase, hsquare, hcube, hsteps] at hdecode
              | some steps =>
                  simp [hbase, hsquare, hcube, hsteps] at hdecode
                  subst certificate
                  exact decodeSteps_length hsteps

/-- The proposition recovered from an accepted raw trace. -/
def Validated (raw : RawTraceCertificate) (maxSteps : ℕ) : Prop :=
  ∃ certificate : TraceCertificate,
    raw.decode = some certificate ∧ certificate.Accepted maxSteps

/-- Pre-decoding bounded wire checker.  The first conjunct prevents an
untrusted oversized list from reaching binary64 decoding; the typed checker
repeats the bound after decoding and checks all arithmetic and links. -/
def check (raw : RawTraceCertificate) (maxSteps : ℕ) : Bool :=
  decide (raw.steps.length ≤ maxSteps) &&
    match raw.decode with
    | none => false
    | some certificate => certificate.check maxSteps

/-- Source-facing wrapper for a nonempty truncation with exactly
`termCount` Gaussian terms.  The typed trace begins at the first term, so it
contains exactly `termCount - 1` recurrence updates.  The empty truncation is
rejected because this certificate shape always carries an initial term. -/
def checkForTermCount (raw : RawTraceCertificate) (maxSteps termCount : ℕ) :
    Bool :=
  decide (0 < termCount) &&
    decide (raw.steps.length = termCount - 1) && raw.check maxSteps

theorem checker_sound {raw : RawTraceCertificate} {maxSteps : ℕ}
    (hcheck : raw.check maxSteps = true) : raw.Validated maxSteps := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  rcases hcheck with ⟨_, hdecoded⟩
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hdecoded
  | some certificate =>
      refine ⟨certificate, hdecode, TraceCertificate.checker_sound ?_⟩
      simpa [hdecode] using hdecoded

theorem checkForTermCount_sound {raw : RawTraceCertificate}
    {maxSteps termCount : ℕ}
    (hcheck : raw.checkForTermCount maxSteps termCount = true) :
    0 < termCount ∧ raw.steps.length = termCount - 1 ∧
      raw.Validated maxSteps := by
  simp only [checkForTermCount, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1.1, hcheck.1.2, checker_sound hcheck.2⟩

/-- Direct application theorem for a named decoded trace.  Acceptance of the
raw words is enough to invoke the typed exact-rational recurrence theorem. -/
theorem decoded_output_contains_exact_after
    {raw : RawTraceCertificate} {certificate : TraceCertificate}
    {maxSteps : ℕ} {w : ℂ}
    (hcheck : raw.check maxSteps = true)
    (hdecode : raw.decode = some certificate)
    (hbase : certificate.base.ContainsComplex w) :
    certificate.output.z.ContainsComplex
        (ExactGaussianState.after w raw.steps.length).z ∧
      certificate.output.ratio.ContainsComplex
        (ExactGaussianState.after w raw.steps.length).ratio := by
  have htyped : certificate.check maxSteps = true := by
    have hraw := hcheck
    simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hraw
    simpa [hdecode] using hraw.2
  have hcontains := TraceCertificate.output_contains_exact_after htyped hbase
  rw [steps_length_eq hdecode] at hcontains
  exact hcontains

/-- Existential form requiring no separately supplied decode equation.  It
exposes the exact typed output and its binding to the accepted raw words. -/
theorem accepted_output_contains_exact_after
    {raw : RawTraceCertificate} {maxSteps : ℕ} {w : ℂ}
    (hcheck : raw.check maxSteps = true)
    (hbase : ∀ certificate : TraceCertificate,
      raw.decode = some certificate → certificate.base.ContainsComplex w) :
    ∃ certificate : TraceCertificate,
      raw.decode = some certificate ∧
      certificate.output.z.ContainsComplex
          (ExactGaussianState.after w raw.steps.length).z ∧
      certificate.output.ratio.ContainsComplex
          (ExactGaussianState.after w raw.steps.length).ratio := by
  rcases checker_sound hcheck with ⟨certificate, hdecode, _⟩
  exact ⟨certificate, hdecode,
    decoded_output_contains_exact_after hcheck hdecode (hbase certificate hdecode)⟩

/-- Convenient wire-level application: the caller identifies only the exact
decoding of the raw base disk, rather than the whole typed trace. -/
theorem accepted_output_contains_exact_after_of_base_decode
    {raw : RawTraceCertificate} {maxSteps : ℕ} {w : ℂ}
    {base : ComplexDisk}
    (hcheck : raw.check maxSteps = true)
    (hbaseDecode : raw.base.decode = some base)
    (hbase : base.ContainsComplex w) :
    ∃ certificate : TraceCertificate,
      raw.decode = some certificate ∧
      certificate.output.z.ContainsComplex
          (ExactGaussianState.after w raw.steps.length).z ∧
      certificate.output.ratio.ContainsComplex
          (ExactGaussianState.after w raw.steps.length).ratio := by
  apply accepted_output_contains_exact_after hcheck
  intro certificate hdecode
  have hsame := base_decode_eq hdecode
  rw [hbaseDecode] at hsame
  have : base = certificate.base := Option.some.inj hsame
  rw [← this]
  exact hbase

/-- Source-facing application theorem for a nonempty truncation.  This binds
the recurrence index to the exact requested term count, while leaving the
finite-sum accumulation and full conductor/frequency manifest as separate
coverage obligations. -/
theorem term_count_output_contains_exact_after_of_base_decode
    {raw : RawTraceCertificate} {maxSteps termCount : ℕ} {w : ℂ}
    {base : ComplexDisk}
    (hcheck : raw.checkForTermCount maxSteps termCount = true)
    (hbaseDecode : raw.base.decode = some base)
    (hbase : base.ContainsComplex w) :
    ∃ certificate : TraceCertificate,
      raw.decode = some certificate ∧
      certificate.output.z.ContainsComplex
          (ExactGaussianState.after w (termCount - 1)).z ∧
      certificate.output.ratio.ContainsComplex
          (ExactGaussianState.after w (termCount - 1)).ratio := by
  have hraw : raw.check maxSteps = true := by
    have hparts := hcheck
    simp only [checkForTermCount, Bool.and_eq_true,
      decide_eq_true_eq] at hparts
    exact hparts.2
  have hsound := checkForTermCount_sound hcheck
  rcases accepted_output_contains_exact_after_of_base_decode
      hraw hbaseDecode hbase with
    ⟨certificate, hdecode, hz, hratio⟩
  rw [hsound.2.1] at hz hratio
  exact ⟨certificate, hdecode, hz, hratio⟩

end RawTraceCertificate

end SparkInterval.Dirichlet.FactoredSmallQRawTrace
