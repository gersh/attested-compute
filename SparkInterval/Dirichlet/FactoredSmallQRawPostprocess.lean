/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQPostprocess
import SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum

/-!
# Raw binary64 certificates for factored small-`q` postprocessing

This module is the exact raw-word wrapper around
`FactoredSmallQPostprocess.Certificate`.  The finite Gaussian trace,
prefactor disk, multiplication witness, analytic-tail bound, and final output
disk are all decoded from finite binary64 words to exact rationals.  A single
typed certificate is then passed to the existing postprocessing checker.

The raw finite-sum object is embedded directly rather than replaced by a
detached typed claim.  The decoding lemmas below retain its row list, parity,
truncation, and output link.  Consequently a postprocessing witness cannot be
attached to a different finite sum after either object has been checked.

The checker proves arithmetic containment only.  It does not prove that a
byte parser, compiler, CPU, GPU, or physical execution produced the words,
and the analytic base, character, prefactor, and tail premises remain
explicit in the application theorem.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawPostprocess

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess

/-! ## Raw tail inflation -/

/-- Raw binary64 form of the radius-only analytic-tail update. -/
structure RawTailInflationCertificate where
  input : ComplexDisk.Raw
  tailBoundBits : Nat
  output : ComplexDisk.Raw
  deriving Repr, DecidableEq, BEq

namespace RawTailInflationCertificate

/-- Decode every field of a tail update to exact rationals. -/
def decode (raw : RawTailInflationCertificate) :
    Option TailInflationCertificate := do
  let input ← raw.input.decode
  let tailBound ← Binary64.decodeFinite raw.tailBoundBits
  let output ← raw.output.decode
  pure { input, tailBound, output }

/-- Successful decoding retains the exact input disk. -/
theorem input_decode_eq {raw : RawTailInflationCertificate}
    {certificate : TailInflationCertificate}
    (hdecode : raw.decode = some certificate) :
    raw.input.decode = some certificate.input := by
  unfold decode at hdecode
  cases hinput : raw.input.decode with
  | none => simp [hinput] at hdecode
  | some input =>
      cases htail : Binary64.decodeFinite raw.tailBoundBits with
      | none => simp [hinput, htail] at hdecode
      | some tailBound =>
          cases houtput : raw.output.decode with
          | none => simp [hinput, htail, houtput] at hdecode
          | some output =>
              simp [hinput, htail, houtput] at hdecode
              subst certificate
              rfl

/-- Successful decoding retains the exact rational tail bound. -/
theorem tailBound_decode_eq {raw : RawTailInflationCertificate}
    {certificate : TailInflationCertificate}
    (hdecode : raw.decode = some certificate) :
    Binary64.decodeFinite raw.tailBoundBits =
      some certificate.tailBound := by
  unfold decode at hdecode
  cases hinput : raw.input.decode with
  | none => simp [hinput] at hdecode
  | some input =>
      cases htail : Binary64.decodeFinite raw.tailBoundBits with
      | none => simp [hinput, htail] at hdecode
      | some tailBound =>
          cases houtput : raw.output.decode with
          | none => simp [hinput, htail, houtput] at hdecode
          | some output =>
              simp [hinput, htail, houtput] at hdecode
              subst certificate
              rfl

/-- Successful decoding retains the exact final output disk. -/
theorem output_decode_eq {raw : RawTailInflationCertificate}
    {certificate : TailInflationCertificate}
    (hdecode : raw.decode = some certificate) :
    raw.output.decode = some certificate.output := by
  unfold decode at hdecode
  cases hinput : raw.input.decode with
  | none => simp [hinput] at hdecode
  | some input =>
      cases htail : Binary64.decodeFinite raw.tailBoundBits with
      | none => simp [hinput, htail] at hdecode
      | some tailBound =>
          cases houtput : raw.output.decode with
          | none => simp [hinput, htail, houtput] at hdecode
          | some output =>
              simp [hinput, htail, houtput] at hdecode
              subst certificate
              rfl

end RawTailInflationCertificate

/-! ## Complete raw postprocessing certificate -/

/-- Raw binary64 form of the linked finite-sum and postprocessing witness. -/
structure RawCertificate where
  finiteSum : RawSumTraceCertificate
  prefactor : ComplexDisk.Raw
  prefactorTimesSum : ComplexDisk.RawMulCertificate
  negativeFrequency : Bool
  tailInflation : RawTailInflationCertificate
  deriving Repr, DecidableEq, BEq

namespace RawCertificate

/-- Decode all raw words and construct the one typed certificate that will be
checked. -/
def decode (raw : RawCertificate) : Option Certificate := do
  let finiteSum ← raw.finiteSum.decode
  let prefactor ← raw.prefactor.decode
  let prefactorTimesSum ← raw.prefactorTimesSum.decode
  let tailInflation ← raw.tailInflation.decode
  pure {
    finiteSum
    prefactor
    prefactorTimesSum
    negativeFrequency := raw.negativeFrequency
    tailInflation
  }

/-- A successfully decoded postprocessing witness contains exactly the
decoded finite-sum trace supplied by the raw object. -/
theorem finiteSum_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    raw.finiteSum.decode = some certificate.finiteSum := by
  unfold decode at hdecode
  cases hsum : raw.finiteSum.decode with
  | none => simp [hsum] at hdecode
  | some finiteSum =>
      cases hprefactor : raw.prefactor.decode with
      | none => simp [hsum, hprefactor] at hdecode
      | some prefactor =>
          cases hmul : raw.prefactorTimesSum.decode with
          | none => simp [hsum, hprefactor, hmul] at hdecode
          | some prefactorTimesSum =>
              cases htail : raw.tailInflation.decode with
              | none => simp [hsum, hprefactor, hmul, htail] at hdecode
              | some tailInflation =>
                  simp [hsum, hprefactor, hmul, htail] at hdecode
                  subst certificate
                  rfl

/-- Complete postprocessing decoding inserts, removes, and reorders no
finite-sum rows. -/
theorem rows_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    decodeRows raw.finiteSum.rows = some certificate.finiteSum.rows :=
  RawSumTraceCertificate.rows_decode_eq (finiteSum_decode_eq hdecode)

/-- The exact source truncation remains the one checked by the embedded
finite-sum certificate. -/
theorem truncation_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    certificate.finiteSum.truncation = raw.finiteSum.truncation :=
  RawSumTraceCertificate.truncation_eq (finiteSum_decode_eq hdecode)

/-- The exact source parity remains the one checked by the embedded
finite-sum certificate. -/
theorem oddParity_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    certificate.finiteSum.oddParity = raw.finiteSum.oddParity :=
  RawSumTraceCertificate.oddParity_eq (finiteSum_decode_eq hdecode)

/-- Successful complete decoding retains the exact decoded prefactor. -/
theorem prefactor_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    raw.prefactor.decode = some certificate.prefactor := by
  unfold decode at hdecode
  cases hsum : raw.finiteSum.decode with
  | none => simp [hsum] at hdecode
  | some finiteSum =>
      cases hprefactor : raw.prefactor.decode with
      | none => simp [hsum, hprefactor] at hdecode
      | some prefactor =>
          cases hmul : raw.prefactorTimesSum.decode with
          | none => simp [hsum, hprefactor, hmul] at hdecode
          | some prefactorTimesSum =>
              cases htail : raw.tailInflation.decode with
              | none => simp [hsum, hprefactor, hmul, htail] at hdecode
              | some tailInflation =>
                  simp [hsum, hprefactor, hmul, htail] at hdecode
                  subst certificate
                  rfl

/-- Successful complete decoding retains the exact tail update. -/
theorem tailInflation_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    raw.tailInflation.decode = some certificate.tailInflation := by
  unfold decode at hdecode
  cases hsum : raw.finiteSum.decode with
  | none => simp [hsum] at hdecode
  | some finiteSum =>
      cases hprefactor : raw.prefactor.decode with
      | none => simp [hsum, hprefactor] at hdecode
      | some prefactor =>
          cases hmul : raw.prefactorTimesSum.decode with
          | none => simp [hsum, hprefactor, hmul] at hdecode
          | some prefactorTimesSum =>
              cases htail : raw.tailInflation.decode with
              | none => simp [hsum, hprefactor, hmul, htail] at hdecode
              | some tailInflation =>
                  simp [hsum, hprefactor, hmul, htail] at hdecode
                  subst certificate
                  rfl

/-- The source-owned sign selector is data, not a separately decoded or
replaceable claim. -/
theorem negativeFrequency_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    certificate.negativeFrequency = raw.negativeFrequency := by
  unfold decode at hdecode
  cases hsum : raw.finiteSum.decode with
  | none => simp [hsum] at hdecode
  | some finiteSum =>
      cases hprefactor : raw.prefactor.decode with
      | none => simp [hsum, hprefactor] at hdecode
      | some prefactor =>
          cases hmul : raw.prefactorTimesSum.decode with
          | none => simp [hsum, hprefactor, hmul] at hdecode
          | some prefactorTimesSum =>
              cases htail : raw.tailInflation.decode with
              | none => simp [hsum, hprefactor, hmul, htail] at hdecode
              | some tailInflation =>
                  simp [hsum, hprefactor, hmul, htail] at hdecode
                  subst certificate
                  rfl

/-- Successful decoding exposes the exact final raw disk as the typed
certificate's output. -/
theorem output_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    raw.tailInflation.output.decode = some certificate.output := by
  exact RawTailInflationCertificate.output_decode_eq
    (tailInflation_decode_eq hdecode)

/-- Proposition recovered from an accepted raw postprocessing certificate. -/
def Validated (raw : RawCertificate) (maxTerms : ℕ) : Prop :=
  ∃ certificate : Certificate,
    raw.decode = some certificate ∧ certificate.Accepted maxTerms

/-- Fail-closed checker for the complete raw witness.  The raw row bound is
tested before any nested binary64 decoding; the typed checker repeats the
finite-sum count and every arithmetic/link obligation after decoding. -/
def check (raw : RawCertificate) (maxTerms : ℕ) : Bool :=
  decide (raw.finiteSum.rows.length ≤ maxTerms) &&
    match raw.decode with
    | none => false
    | some certificate => certificate.check maxTerms

theorem checker_sound {raw : RawCertificate} {maxTerms : ℕ}
    (hcheck : raw.check maxTerms = true) : raw.Validated maxTerms := by
  unfold check at hcheck
  simp only [Bool.and_eq_true, decide_eq_true_eq] at hcheck
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hcheck
  | some certificate =>
      refine ⟨certificate, hdecode, Certificate.checker_sound ?_⟩
      simpa [hdecode] using hcheck.2

/-- End-to-end raw arithmetic theorem.  Its conclusion is stated using the
raw finite-sum parity/truncation and also returns the exact decode equalities
for the finite-sum and final-output disks.  This keeps both source rows and
the claimed result visibly tied to the one accepted raw object.

The remaining premises are the intended analytic boundary: containment of
the exponential base, all character values, the prefactor, and the additive
tail perturbation. -/
theorem accepted_output_contains_exact_finite_sum
    {raw : RawCertificate} {maxTerms : ℕ}
    {characters : List ℂ} {w prefactor delta : ℂ}
    {baseDisk prefactorDisk : ComplexDisk} {tailBound : ℚ}
    (hcheck : raw.check maxTerms = true)
    (hbaseDecode : raw.finiteSum.seed.base.decode = some baseDisk)
    (hbase : baseDisk.ContainsComplex w)
    (hcharacters : RawContainsCharacters raw.finiteSum.rows characters)
    (hprefactorDecode : raw.prefactor.decode = some prefactorDisk)
    (hprefactor : prefactorDisk.ContainsComplex prefactor)
    (htailDecode : Binary64.decodeFinite
      raw.tailInflation.tailBoundBits = some tailBound)
    (hdelta : ‖delta‖ ≤ (tailBound : ℝ)) :
    ∃ certificate : Certificate,
      raw.decode = some certificate ∧
      raw.finiteSum.decode = some certificate.finiteSum ∧
      raw.tailInflation.output.decode = some certificate.output ∧
      characters.length = raw.finiteSum.truncation ∧
      certificate.output.ContainsComplex
        (applyFrequencySignValue raw.negativeFrequency
            (prefactor * exactFiniteSum raw.finiteSum.oddParity
              w characters) + delta) := by
  rcases checker_sound hcheck with ⟨certificate, hdecode, haccepted⟩
  have hfiniteDecode := finiteSum_decode_eq hdecode
  have htypedBaseDecode :=
    RawSumTraceCertificate.seed_base_decode_eq hfiniteDecode
  rw [hbaseDecode] at htypedBaseDecode
  have hbaseEq : baseDisk = certificate.finiteSum.seed.base :=
    Option.some.inj htypedBaseDecode
  have htypedBase :
      certificate.finiteSum.seed.base.ContainsComplex w := by
    rw [← hbaseEq]
    exact hbase
  have htypedCharacters :
      ContainsCharacters certificate.finiteSum.rows characters :=
    decodeRows_containsCharacters
      (RawSumTraceCertificate.rows_decode_eq hfiniteDecode) hcharacters
  have htypedPrefactorDecode := prefactor_decode_eq hdecode
  rw [hprefactorDecode] at htypedPrefactorDecode
  have hprefactorEq : prefactorDisk = certificate.prefactor :=
    Option.some.inj htypedPrefactorDecode
  have htypedPrefactor : certificate.prefactor.ContainsComplex prefactor := by
    rw [← hprefactorEq]
    exact hprefactor
  have htailInflationDecode := tailInflation_decode_eq hdecode
  have htypedTailDecode :=
    RawTailInflationCertificate.tailBound_decode_eq htailInflationDecode
  rw [htailDecode] at htypedTailDecode
  have htailEq : tailBound = certificate.tailInflation.tailBound :=
    Option.some.inj htypedTailDecode
  have htypedDelta :
      ‖delta‖ ≤ (certificate.tailInflation.tailBound : ℝ) := by
    rw [← htailEq]
    exact hdelta
  have hresult := Certificate.output_contains_exact_finite_sum
    (certificate := certificate)
    (maxTerms := maxTerms)
    (characters := characters)
    (w := w)
    (prefactor := prefactor)
    (delta := delta)
    (by simpa [Certificate.check] using haccepted)
    htypedBase htypedCharacters htypedPrefactor htypedDelta
  have hparity := RawSumTraceCertificate.oddParity_eq hfiniteDecode
  have htruncation := RawSumTraceCertificate.truncation_eq hfiniteDecode
  have hsign := negativeFrequency_eq hdecode
  refine ⟨certificate, hdecode, hfiniteDecode, output_decode_eq hdecode, ?_, ?_⟩
  · rw [← htruncation]
    exact hresult.1
  · rw [← hsign, ← hparity]
    exact hresult.2

end RawCertificate

end SparkInterval.Dirichlet.FactoredSmallQRawPostprocess
