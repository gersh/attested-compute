/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCompletedSign
import SparkInterval.Dirichlet.FactoredSmallQRawPostprocess

/-!
# Raw binary64 certificates for completed small-q signs

This is the finite wire wrapper around
`FactoredSmallQCompletedSign.Certificate`.  The two multiplications and the
time-tail inflation are decoded from literal binary64 words.  The sign uses
the producer's signed convention (`-1 = negative`, `+1 = positive`); zero and
every other value are rejected.  The caller also supplies the raw Fourier disk separately, and the
checker requires literal equality with the multiplication's raw left operand
before decoding.  Thus a valid arithmetic trace cannot be attached to a
different Fourier word triple that merely happens to decode to a convenient
rational disk.

The checker is fail-closed for non-finite or out-of-range binary64 words,
negative radii, detached state links, nonpositive scale/untilt factors, and a
final disk that does not certify the selected strict sign.  The record has
fixed size, so no separate list/resource bound is necessary: `decodeFinite`
already checks every `Nat` word is below `2^64`, and the two-value sign decoder
checks its own bound.

The final source-shaped theorem expands the exact `2*pi/b` scale and
`exp(-pi*eta*t/4)` untilt.  Containment of those transcendental values, the
complex-norm time-tail bound, and functional-equation reality remain explicit
analytic premises.  This module gives no meaning to bytes, a compiler, or a
physical CPU/GPU execution.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocess

/-! ## Deterministic sign discriminant -/

/-- Source-shaped signed discriminant for strict nonzero signs. -/
def decodeStrictSign : Int → Option StrictSign
  | -1 => some .negative
  | 1 => some .positive
  | _ => none

@[simp] theorem decodeStrictSign_negative_one :
    decodeStrictSign (-1) = some .negative := rfl

@[simp] theorem decodeStrictSign_one :
    decodeStrictSign 1 = some .positive := rfl

@[simp] theorem decodeStrictSign_zero :
    decodeStrictSign 0 = none := rfl

/-! ## Raw multiplication field retention -/

/-- Successful raw multiplication decoding retains all three disk words.
This reusable lemma prevents an application theorem from naming detached
factor or output disks after the arithmetic certificate has been checked. -/
theorem rawMul_disk_decodes
    {raw : ComplexDisk.RawMulCertificate}
    {certificate : ComplexDisk.MulCertificate}
    (hdecode : raw.decode = some certificate) :
    raw.left.decode = some certificate.left ∧
      raw.right.decode = some certificate.right ∧
      raw.output.decode = some certificate.output := by
  unfold ComplexDisk.RawMulCertificate.decode at hdecode
  cases hleft : raw.left.decode with
  | none => simp [hleft] at hdecode
  | some left =>
      cases hright : raw.right.decode with
      | none => simp [hleft, hright] at hdecode
      | some right =>
          cases houtput : raw.output.decode with
          | none => simp [hleft, hright, houtput] at hdecode
          | some output =>
              cases herror : Binary64.decodeFinite
                  raw.centerErrorBoundBits with
              | none => simp [hleft, hright, houtput, herror] at hdecode
              | some error =>
                  cases hleftNorm : Binary64.decodeFinite
                      raw.leftCenterNormBoundBits with
                  | none =>
                      simp [hleft, hright, houtput, herror, hleftNorm] at hdecode
                  | some leftNorm =>
                      cases hrightNorm : Binary64.decodeFinite
                          raw.rightCenterNormBoundBits with
                      | none =>
                          simp [hleft, hright, houtput, herror, hleftNorm,
                            hrightNorm] at hdecode
                      | some rightNorm =>
                          simp [hleft, hright, houtput, herror, hleftNorm,
                            hrightNorm] at hdecode
                          subst certificate
                          exact ⟨rfl, rfl, rfl⟩

/-! ## Complete raw certificate -/

/-- Fixed-size raw form of scaling, time-tail inflation, untilting, and the
strict-sign selector. -/
structure RawCertificate where
  scaleTimesFourier : ComplexDisk.RawMulCertificate
  timeTailInflation : RawTailInflationCertificate
  untiltTimesPeriodized : ComplexDisk.RawMulCertificate
  signCode : Int
  deriving Repr, DecidableEq, BEq

namespace RawCertificate

/-- Decode every finite word and construct the only typed certificate that
the checker may accept. -/
def decode (raw : RawCertificate) : Option Certificate := do
  let scaleTimesFourier ← raw.scaleTimesFourier.decode
  let timeTailInflation ← raw.timeTailInflation.decode
  let untiltTimesPeriodized ← raw.untiltTimesPeriodized.decode
  let sign ← decodeStrictSign raw.signCode
  pure {
    scaleTimesFourier
    timeTailInflation
    untiltTimesPeriodized
    sign
  }

theorem scaleTimesFourier_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    raw.scaleTimesFourier.decode =
      some certificate.scaleTimesFourier := by
  unfold decode at hdecode
  cases hscale : raw.scaleTimesFourier.decode with
  | none => simp [hscale] at hdecode
  | some scale =>
      cases htail : raw.timeTailInflation.decode with
      | none => simp [hscale, htail] at hdecode
      | some tail =>
          cases huntilt : raw.untiltTimesPeriodized.decode with
          | none => simp [hscale, htail, huntilt] at hdecode
          | some untilt =>
              cases hsign : decodeStrictSign raw.signCode with
              | none => simp [hscale, htail, huntilt, hsign] at hdecode
              | some sign =>
                  simp [hscale, htail, huntilt, hsign] at hdecode
                  subst certificate
                  rfl

theorem timeTailInflation_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    raw.timeTailInflation.decode =
      some certificate.timeTailInflation := by
  unfold decode at hdecode
  cases hscale : raw.scaleTimesFourier.decode with
  | none => simp [hscale] at hdecode
  | some scale =>
      cases htail : raw.timeTailInflation.decode with
      | none => simp [hscale, htail] at hdecode
      | some tail =>
          cases huntilt : raw.untiltTimesPeriodized.decode with
          | none => simp [hscale, htail, huntilt] at hdecode
          | some untilt =>
              cases hsign : decodeStrictSign raw.signCode with
              | none => simp [hscale, htail, huntilt, hsign] at hdecode
              | some sign =>
                  simp [hscale, htail, huntilt, hsign] at hdecode
                  subst certificate
                  rfl

theorem untiltTimesPeriodized_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    raw.untiltTimesPeriodized.decode =
      some certificate.untiltTimesPeriodized := by
  unfold decode at hdecode
  cases hscale : raw.scaleTimesFourier.decode with
  | none => simp [hscale] at hdecode
  | some scale =>
      cases htail : raw.timeTailInflation.decode with
      | none => simp [hscale, htail] at hdecode
      | some tail =>
          cases huntilt : raw.untiltTimesPeriodized.decode with
          | none => simp [hscale, htail, huntilt] at hdecode
          | some untilt =>
              cases hsign : decodeStrictSign raw.signCode with
              | none => simp [hscale, htail, huntilt, hsign] at hdecode
              | some sign =>
                  simp [hscale, htail, huntilt, hsign] at hdecode
                  subst certificate
                  rfl

theorem sign_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    decodeStrictSign raw.signCode = some certificate.sign := by
  unfold decode at hdecode
  cases hscale : raw.scaleTimesFourier.decode with
  | none => simp [hscale] at hdecode
  | some scale =>
      cases htail : raw.timeTailInflation.decode with
      | none => simp [hscale, htail] at hdecode
      | some tail =>
          cases huntilt : raw.untiltTimesPeriodized.decode with
          | none => simp [hscale, htail, huntilt] at hdecode
          | some untilt =>
              cases hsign : decodeStrictSign raw.signCode with
              | none => simp [hscale, htail, huntilt, hsign] at hdecode
              | some sign =>
                  simp [hscale, htail, huntilt, hsign] at hdecode
                  subst certificate
                  rfl

/-- The last literal raw disk is exactly the output disk used to prove the
strict sign. -/
theorem output_decode_eq {raw : RawCertificate}
    {certificate : Certificate}
    (hdecode : raw.decode = some certificate) :
    raw.untiltTimesPeriodized.output.decode = some certificate.output := by
  have huntilt := untiltTimesPeriodized_decode_eq hdecode
  exact (rawMul_disk_decodes huntilt).2.2

/-- Typed arithmetic evidence recovered from a raw completed-sign object and
its separately named raw Fourier input. -/
def Validated (raw : RawCertificate) (fourier : ComplexDisk.Raw) : Prop :=
  raw.scaleTimesFourier.left = fourier ∧
  ∃ fourierDisk : ComplexDisk, ∃ certificate : Certificate,
    fourier.decode = some fourierDisk ∧
    raw.decode = some certificate ∧
    certificate.Accepted fourierDisk

/-- Fixed-size fail-closed checker.  Literal raw Fourier equality is checked
before either nested decode; successful typed checking repeats every
arithmetic, positivity, state-link, radius, and strict-sign obligation. -/
def check (raw : RawCertificate) (fourier : ComplexDisk.Raw) : Bool :=
  decide (raw.scaleTimesFourier.left = fourier) &&
    match fourier.decode with
    | none => false
    | some fourierDisk =>
        match raw.decode with
        | none => false
        | some certificate => certificate.check fourierDisk

theorem checker_sound {raw : RawCertificate} {fourier : ComplexDisk.Raw}
    (hcheck : raw.check fourier = true) : raw.Validated fourier := by
  unfold check at hcheck
  simp only [Bool.and_eq_true, decide_eq_true_eq] at hcheck
  refine ⟨hcheck.1, ?_⟩
  cases hfourier : fourier.decode with
  | none => simp [hfourier] at hcheck
  | some fourierDisk =>
      cases hdecode : raw.decode with
      | none => simp [hfourier, hdecode] at hcheck
      | some certificate =>
          refine ⟨fourierDisk, certificate, rfl, rfl, ?_⟩
          exact Certificate.checker_sound (by
            simpa [hfourier, hdecode] using hcheck.2)

/-! ## Source-shaped raw application theorem -/

/-- Human-readable source guards that prevent total-division or out-of-source
parameter regimes from being hidden in an arithmetic certificate. -/
def SourceGuards (b eta t : ℝ) : Prop :=
  0 < b ∧ -1 < eta ∧ eta < 1 ∧ 0 ≤ t

/-- Exact raw-word-to-source-sign theorem.

The conclusion retains the literal raw Fourier attachment, deterministic sign
decode, and final raw-output decode.  The analytic premises identify the raw
factor disks with `2*pi/b` and `exp(-pi*eta*t/4)` and bound the omitted complex
time tail in norm. -/
theorem accepted_source_sign
    {raw : RawCertificate} {fourierRaw : ComplexDisk.Raw}
    {fourierDisk scaleDisk untiltDisk : ComplexDisk}
    {fourier timeTail : ℂ} {tailBound : ℚ}
    {b eta t : ℝ}
    (hguards : SourceGuards b eta t)
    (hcheck : raw.check fourierRaw = true)
    (hfourierDecode : fourierRaw.decode = some fourierDisk)
    (hfourier : fourierDisk.ContainsComplex fourier)
    (hscaleDecode : raw.scaleTimesFourier.right.decode = some scaleDisk)
    (hscale : scaleDisk.ContainsComplex (sourceScale b : ℂ))
    (htailDecode : Binary64.decodeFinite
      raw.timeTailInflation.tailBoundBits = some tailBound)
    (htimeTail : ‖timeTail‖ ≤ (tailBound : ℝ))
    (huntiltDecode : raw.untiltTimesPeriodized.right.decode =
      some untiltDisk)
    (huntilt : untiltDisk.ContainsComplex (sourceUntilt eta t : ℂ))
    (hreal : (sourceCompletedValue fourier b eta t timeTail).im = 0) :
    ∃ certificate : Certificate,
      raw.scaleTimesFourier.left = fourierRaw ∧
      raw.decode = some certificate ∧
      decodeStrictSign raw.signCode = some certificate.sign ∧
      raw.untiltTimesPeriodized.output.decode = some certificate.output ∧
      SourceGuards b eta t ∧
      certificate.sign.Holds
        (sourceCompletedValue fourier b eta t timeTail).re := by
  rcases checker_sound hcheck with
    ⟨hattached, decodedFourier, certificate, hdecodedFourier,
      hdecode, haccepted⟩
  rw [hfourierDecode] at hdecodedFourier
  have hfourierEq : fourierDisk = decodedFourier :=
    Option.some.inj hdecodedFourier
  have hscaleMul := scaleTimesFourier_decode_eq hdecode
  have htypedScaleDecode := (rawMul_disk_decodes hscaleMul).2.1
  rw [hscaleDecode] at htypedScaleDecode
  have hscaleEq : scaleDisk = certificate.scaleTimesFourier.right :=
    Option.some.inj htypedScaleDecode
  have htailInflation := timeTailInflation_decode_eq hdecode
  have htypedTailDecode :=
    RawTailInflationCertificate.tailBound_decode_eq htailInflation
  rw [htailDecode] at htypedTailDecode
  have htailEq : tailBound = certificate.timeTailInflation.tailBound :=
    Option.some.inj htypedTailDecode
  have huntiltMul := untiltTimesPeriodized_decode_eq hdecode
  have htypedUntiltDecode := (rawMul_disk_decodes huntiltMul).2.1
  rw [huntiltDecode] at htypedUntiltDecode
  have huntiltEq : untiltDisk = certificate.untiltTimesPeriodized.right :=
    Option.some.inj htypedUntiltDecode
  have htypedFourier : decodedFourier.ContainsComplex fourier := by
    rw [← hfourierEq]
    exact hfourier
  have htypedScale :
      certificate.scaleTimesFourier.right.ContainsComplex
        (sourceScale b : ℂ) := by
    rw [← hscaleEq]
    exact hscale
  have htypedTail :
      ‖timeTail‖ ≤
        (certificate.timeTailInflation.tailBound : ℝ) := by
    rw [← htailEq]
    exact htimeTail
  have htypedUntilt :
      certificate.untiltTimesPeriodized.right.ContainsComplex
        (sourceUntilt eta t : ℂ) := by
    rw [← huntiltEq]
    exact huntilt
  have htypedCheck : certificate.check decodedFourier = true := by
    exact decide_eq_true_eq.mpr haccepted
  have hsign := Certificate.accepted_source_sign hguards.1 htypedCheck
    htypedFourier htypedScale htypedTail htypedUntilt hreal
  exact ⟨certificate, hattached, hdecode, sign_decode_eq hdecode,
    output_decode_eq hdecode, hguards, hsign.2⟩

end RawCertificate

end SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign
