/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDisk

/-!
# Exact double-double complex-disk multiplication certificates

This qualification-facing module checks one standalone complex-disk
multiplication certificate whose real and imaginary centres are represented
as double-double pairs.  Every limb and scalar bound is a raw IEEE-754
binary64 word represented by a natural number.

The exact rational meaning of a double-double pair is simply `hi + lo`.
Soundness does not require normalization, non-overlap, a relative limb-size
bound, or a normal-result hypothesis.  The arithmetic decoder rejects
infinities, NaNs, and words outside 64 bits.  It accepts both binary64
signed-zero words and retains their bits in the raw structures while exact
rational decoding maps either spelling to zero.  A successful check proves
the same five groups checked by the qualification C++ exact checker:

1. decoded radii and the centre-error bound are nonnegative;
2. the squared centre error is bounded;
3. the left-centre squared norm is bounded by a nonnegative bound;
4. the right-centre squared norm is bounded by a nonnegative bound; and
5. the complete output-radius inequality holds.

This is an ordinary exact-rational checker.  It contains no trusted axiom and
makes no claim that CUDA, a compiler, or a physical GPU produced the bytes.
-/

set_option autoImplicit false

namespace SparkInterval.Certified.ComplexDisk.DD

open SparkInterval.Certificate

/-! ## Exact double-double decoding -/

/-- Two raw binary64 words whose exact rational meaning is `hi + lo`. -/
structure RawDD where
  hiBits : Nat
  loBits : Nat
  deriving Repr, DecidableEq, BEq

namespace RawDD

/-- Decode both finite limbs and add their exact rational values. -/
def decode (raw : RawDD) : Option ℚ := do
  let hi ← Binary64.decodeFinite raw.hiBits
  let lo ← Binary64.decodeFinite raw.loBits
  pure (hi + lo)

end RawDD

/-- Raw double-double complex disk: two DD centre components and one
binary64 radius. -/
structure RawDisk where
  re : RawDD
  im : RawDD
  radiusBits : Nat
  deriving Repr, DecidableEq, BEq

namespace RawDisk

/-- Decode all five words to the existing exact-rational disk model. -/
def decode (raw : RawDisk) : Option ComplexDisk := do
  let re ← raw.re.decode
  let im ← raw.im.decode
  let radius ← Binary64.decodeFinite raw.radiusBits
  pure ⟨re, im, radius⟩

end RawDisk

/-- Raw words for one DD complex-disk multiplication certificate. -/
structure RawMulCertificate where
  left : RawDisk
  right : RawDisk
  output : RawDisk
  centerErrorBoundBits : Nat
  leftCenterNormBoundBits : Nat
  rightCenterNormBoundBits : Nat
  deriving Repr, DecidableEq, BEq

namespace RawMulCertificate

/-- Decode every binary64 field and construct the reusable rational
`ComplexDisk.MulCertificate`. -/
def decode (raw : RawMulCertificate) :
    Option ComplexDisk.MulCertificate := do
  let left ← raw.left.decode
  let right ← raw.right.decode
  let output ← raw.output.decode
  let centerErrorBound ←
    Binary64.decodeFinite raw.centerErrorBoundBits
  let leftCenterNormBound ←
    Binary64.decodeFinite raw.leftCenterNormBoundBits
  let rightCenterNormBound ←
    Binary64.decodeFinite raw.rightCenterNormBoundBits
  pure {
    left
    right
    output
    centerErrorBound
    leftCenterNormBound
    rightCenterNormBound
  }

end RawMulCertificate

/-! ## The five exact arithmetic obligation groups -/

/-- Nonnegativity checks grouped with decoding in the C++ checker.  The two
centre-norm bounds carry their own nonnegativity checks below. -/
def BasicBounds (certificate : ComplexDisk.MulCertificate) : Prop :=
  0 ≤ certificate.left.radius ∧
  0 ≤ certificate.right.radius ∧
  0 ≤ certificate.output.radius ∧
  0 ≤ certificate.centerErrorBound

/-- Exact squared error of the emitted centre. -/
def CenterErrorBound (certificate : ComplexDisk.MulCertificate) : Prop :=
  ComplexDisk.productCenterErrorSq certificate.left certificate.right
      certificate.output ≤ certificate.centerErrorBound ^ 2

/-- Nonnegative upper bound for the left-centre Euclidean norm. -/
def LeftCenterNormBound (certificate : ComplexDisk.MulCertificate) : Prop :=
  0 ≤ certificate.leftCenterNormBound ∧
  certificate.left.centerNormSq ≤
    certificate.leftCenterNormBound ^ 2

/-- Nonnegative upper bound for the right-centre Euclidean norm. -/
def RightCenterNormBound (certificate : ComplexDisk.MulCertificate) : Prop :=
  0 ≤ certificate.rightCenterNormBound ∧
  certificate.right.centerNormSq ≤
    certificate.rightCenterNormBound ^ 2

/-- The complete disk-product radius decomposition. -/
def RadiusBound (certificate : ComplexDisk.MulCertificate) : Prop :=
  certificate.centerErrorBound +
      certificate.leftCenterNormBound * certificate.right.radius +
      certificate.rightCenterNormBound * certificate.left.radius +
      certificate.left.radius * certificate.right.radius ≤
    certificate.output.radius

instance (certificate : ComplexDisk.MulCertificate) :
    Decidable (BasicBounds certificate) := by
  unfold BasicBounds
  infer_instance

instance (certificate : ComplexDisk.MulCertificate) :
    Decidable (CenterErrorBound certificate) := by
  unfold CenterErrorBound
  infer_instance

instance (certificate : ComplexDisk.MulCertificate) :
    Decidable (LeftCenterNormBound certificate) := by
  unfold LeftCenterNormBound
  infer_instance

instance (certificate : ComplexDisk.MulCertificate) :
    Decidable (RightCenterNormBound certificate) := by
  unfold RightCenterNormBound
  infer_instance

instance (certificate : ComplexDisk.MulCertificate) :
    Decidable (RadiusBound certificate) := by
  unfold RadiusBound
  infer_instance

/-- The five qualification-facing groups, kept named for human and automated
mutation auditing. -/
def FiveObligations (certificate : ComplexDisk.MulCertificate) : Prop :=
  BasicBounds certificate ∧
  CenterErrorBound certificate ∧
  LeftCenterNormBound certificate ∧
  RightCenterNormBound certificate ∧
  RadiusBound certificate

instance (certificate : ComplexDisk.MulCertificate) :
    Decidable (FiveObligations certificate) := by
  unfold FiveObligations BasicBounds CenterErrorBound LeftCenterNormBound
    RightCenterNormBound RadiusBound
  infer_instance

/-- Per-obligation Boolean diagnostics.  `accepted` is the conjunction used
by the raw checker. -/
structure ObligationChecks where
  basicBounds : Bool
  centerErrorBound : Bool
  leftCenterNormBound : Bool
  rightCenterNormBound : Bool
  radiusBound : Bool
  deriving Repr, DecidableEq, BEq

namespace ObligationChecks

def accepted (checks : ObligationChecks) : Bool :=
  checks.basicBounds &&
  checks.centerErrorBound &&
  checks.leftCenterNormBound &&
  checks.rightCenterNormBound &&
  checks.radiusBound

end ObligationChecks

/-- Evaluate the five groups using exact rational comparisons only. -/
def obligationChecks
    (certificate : ComplexDisk.MulCertificate) : ObligationChecks := {
  basicBounds := decide (BasicBounds certificate)
  centerErrorBound := decide (CenterErrorBound certificate)
  leftCenterNormBound := decide (LeftCenterNormBound certificate)
  rightCenterNormBound := decide (RightCenterNormBound certificate)
  radiusBound := decide (RadiusBound certificate)
}

@[simp] theorem obligationChecks_accepted_iff
    (certificate : ComplexDisk.MulCertificate) :
    (obligationChecks certificate).accepted = true ↔
      FiveObligations certificate := by
  simp [obligationChecks, ObligationChecks.accepted, FiveObligations]
  tauto

/-- The five named groups are exactly the existing semantic certificate's
well-formedness predicate. -/
theorem fiveObligations_iff_wellFormed
    (certificate : ComplexDisk.MulCertificate) :
    FiveObligations certificate ↔ certificate.WellFormed := by
  constructor
  · rintro ⟨⟨hlr, hrr, hor, hce⟩, hcenter,
      ⟨hln, hleft⟩, ⟨hrn, hright⟩, hradius⟩
    exact ⟨hlr, hrr, hor, hce, hln, hrn, hcenter, hleft, hright, hradius⟩
  · rintro ⟨hlr, hrr, hor, hce, hln, hrn,
      hcenter, hleft, hright, hradius⟩
    exact ⟨⟨hlr, hrr, hor, hce⟩, hcenter,
      ⟨hln, hleft⟩, ⟨hrn, hright⟩, hradius⟩

namespace RawMulCertificate

/-- Fail-closed exact decoder and five-obligation checker. -/
def check (raw : RawMulCertificate) : Bool :=
  match raw.decode with
  | none => false
  | some certificate => (obligationChecks certificate).accepted

/-- Typed exact-rational evidence recovered from a successful raw check. -/
def Validated (raw : RawMulCertificate) : Prop :=
  ∃ certificate : ComplexDisk.MulCertificate,
    raw.decode = some certificate ∧ FiveObligations certificate

theorem check_sound {raw : RawMulCertificate}
    (hcheck : raw.check = true) : raw.Validated := by
  unfold check at hcheck
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hcheck
  | some certificate =>
      exact ⟨certificate, hdecode,
        (obligationChecks_accepted_iff certificate).mp (by
          simpa [hdecode] using hcheck)⟩

/-- Arithmetic application theorem.  The physical producer remains outside
this theorem's scope. -/
theorem output_contains_mul
    {raw : RawMulCertificate}
    {certificate : ComplexDisk.MulCertificate}
    (hcheck : raw.check = true)
    (hdecode : raw.decode = some certificate)
    {x y : ℂ}
    (hx : certificate.left.ContainsComplex x)
    (hy : certificate.right.ContainsComplex y) :
    certificate.output.ContainsComplex (x * y) := by
  rcases check_sound hcheck with ⟨decoded, hdecoded, hfive⟩
  have heq : decoded = certificate := by
    rw [hdecode] at hdecoded
    exact Option.some.inj hdecoded.symm
  subst decoded
  have hwf : certificate.WellFormed :=
    (fiveObligations_iff_wellFormed certificate).mp hfive
  have htyped : certificate.check = true := by
    simp [ComplexDisk.MulCertificate.check, hwf]
  exact ComplexDisk.MulCertificate.output_contains_mul htyped hx hy

end RawMulCertificate

end SparkInterval.Certified.ComplexDisk.DD
