/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCampaign
import SparkInterval.Dirichlet.FactoredSmallQCompletedSign
import SparkInterval.Zeta.EndpointCertificate

/-!
# Completed small-q signs as rational zero brackets

`FactoredSmallQCompletedSign.Certificate` proves that a rational complex disk
lies strictly on one side of the imaginary axis.  This module turns a pair of
such checked disks into the existing `SparkInterval.Zeta.RationalBracket`
interface.

The bridge retains the source grid data rather than accepting arbitrary
endpoint labels.  Each endpoint has a `CellKey` and an exact rational time;
the checker requires one positive shared `a`, the exact equations
`time = sample / a`, a common character, increasing samples and times, and
opposite checked strict signs.  Each arithmetic certificate is checked
against the Fourier disk selected by its own key.

The checker alone does not identify a completed disk with an analytic
evaluator.  `EvaluatorLink` and `Realizes` keep, respectively, the endpoint
equality/containment premise and the complete post-DFT analytic premises
explicit.  Once those are supplied, the resulting rational bracket satisfies
`EnclosesEndpoints`.  The family wrapper additionally checks the global
strict ordering required by `RationalBracketFamily` and feeds its existing
`exists_zeroCertificate` theorem.

All executable decisions use exact rational arithmetic and ordinary
`decide`; this module uses neither `native_decide` nor a project axiom.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQZeroBracket

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Zeta

/-! ## Exact real projection of a complex disk -/

/-- The exact rational projection of a complex disk onto the real axis. -/
def realProjection (disk : ComplexDisk) : RatInterval :=
  ⟨disk.re - disk.radius, disk.re + disk.radius⟩

@[simp] theorem realProjection_lo (disk : ComplexDisk) :
    (realProjection disk).lo = disk.re - disk.radius := rfl

@[simp] theorem realProjection_hi (disk : ComplexDisk) :
    (realProjection disk).hi = disk.re + disk.radius := rfl

/-- A nonnegative disk radius makes its exact real projection well formed. -/
theorem realProjection_isValid {disk : ComplexDisk}
    (hradius : 0 ≤ disk.radius) : (realProjection disk).IsValid := by
  simp only [RatInterval.IsValid, realProjection_lo, realProjection_hi]
  linarith

/-- The exact real projection contains the real part of every complex value
in the disk. -/
theorem realProjection_contains_re {disk : ComplexDisk} {value : ℂ}
    (hcontains : disk.ContainsComplex value) :
    (realProjection disk).ContainsReal value.re := by
  have hreNorm := Complex.abs_re_le_norm (value - disk.center)
  have hre : |value.re - (disk.re : ℝ)| ≤ (disk.radius : ℝ) := by
    simpa only [Complex.sub_re, ComplexDisk.center_re] using
      hreNorm.trans hcontains
  have hbounds := abs_le.mp hre
  constructor
  · change ((disk.re - disk.radius : ℚ) : ℝ) ≤ value.re
    norm_num only [Rat.cast_sub]
    linarith
  · change value.re ≤ ((disk.re + disk.radius : ℚ) : ℝ)
    norm_num only [Rat.cast_add]
    linarith

/-- Specialization to a contained real complex value. -/
theorem realProjection_contains_real {disk : ComplexDisk} {value : ℝ}
    (hcontains : disk.ContainsComplex (value : ℂ)) :
    (realProjection disk).ContainsReal value := by
  simpa using realProjection_contains_re hcontains

/-! ## One checked pair -/

/-- One completed-sign endpoint, retaining both its campaign key and its
exact rational source time. -/
structure SignedEndpoint where
  key : CellKey
  time : ℚ
  certificate : FactoredSmallQCompletedSign.Certificate
  deriving Repr, DecidableEq, BEq

namespace SignedEndpoint

/-- Source-grid time attached to a key: `sample / a`. -/
def sourceTime (a : ℚ) (key : CellKey) : ℚ :=
  (key.frequency : ℚ) / a

/-- Casting the exact rational grid to the analytic real grid preserves the
source formula.  A caller whose header stores a real-valued `a` need only
supply the explicit equality between that header field and `(a : ℝ)`. -/
theorem sourceTime_cast (a : ℚ) (key : CellKey) :
    ((sourceTime a key : ℚ) : ℝ) =
      (key.frequency : ℝ) / (a : ℝ) := by
  simp [sourceTime]

/-- Check the completed arithmetic against the Fourier disk selected by the
endpoint's own key. -/
def check (endpoint : SignedEndpoint)
    (fourierDisks : CellKey → ComplexDisk) : Bool :=
  endpoint.certificate.check (fourierDisks endpoint.key)

/-- A checked endpoint's final disk certifies the sign stored in that same
endpoint. -/
theorem output_certifiedBy {endpoint : SignedEndpoint}
    {fourierDisks : CellKey → ComplexDisk}
    (hcheck : endpoint.check fourierDisks = true) :
    endpoint.certificate.sign.CertifiedBy endpoint.certificate.output := by
  exact (FactoredSmallQCompletedSign.Certificate.checker_sound hcheck).2.2.2.2.2.2.2.2

/-- In particular, an endpoint accepted by the completed-sign checker has a
nonnegative final radius. -/
theorem output_radius_nonneg {endpoint : SignedEndpoint}
    {fourierDisks : CellKey → ComplexDisk}
    (hcheck : endpoint.check fourierDisks = true) :
    0 ≤ endpoint.certificate.output.radius := by
  have hcertified := output_certifiedBy hcheck
  cases hsign : endpoint.certificate.sign <;>
    simp only [hsign, StrictSign.CertifiedBy] at hcertified <;>
    exact hcertified.1

/-- Explicit semantic link between a checked output disk and a named real
evaluator at this endpoint.  Reality and the evaluator equality are separate
premises; disk containment alone does not supply either statement. -/
def EvaluatorLink (endpoint : SignedEndpoint) (f : ℝ → ℝ) : Prop :=
  ∃ value : ℂ,
    endpoint.certificate.output.ContainsComplex value ∧
    value.im = 0 ∧
    f (endpoint.time : ℝ) = value.re

/-- Complete generic post-DFT premises identifying an endpoint with the
named evaluator. -/
def Realizes (endpoint : SignedEndpoint)
    (fourierDisks : CellKey → ComplexDisk) (f : ℝ → ℝ)
    (fourier : ℂ) (scale : ℝ) (timeTail : ℂ) (untilt : ℝ) : Prop :=
  (fourierDisks endpoint.key).ContainsComplex fourier ∧
  endpoint.certificate.scaleTimesFourier.right.ContainsComplex
    (scale : ℂ) ∧
  ‖timeTail‖ ≤
    (endpoint.certificate.timeTailInflation.tailBound : ℝ) ∧
  endpoint.certificate.untiltTimesPeriodized.right.ContainsComplex
    (untilt : ℂ) ∧
  (completedValue fourier scale timeTail untilt).im = 0 ∧
  f (endpoint.time : ℝ) =
    (completedValue fourier scale timeTail untilt).re

/-- The checked disk-arithmetic theorem discharges `EvaluatorLink` from the
fully explicit analytic/model premises in `Realizes`. -/
theorem evaluatorLink_of_realizes
    {endpoint : SignedEndpoint}
    {fourierDisks : CellKey → ComplexDisk} {f : ℝ → ℝ}
    {fourier : ℂ} {scale untilt : ℝ} {timeTail : ℂ}
    (hcheck : endpoint.check fourierDisks = true)
    (hrealizes : endpoint.Realizes fourierDisks f fourier scale
      timeTail untilt) : endpoint.EvaluatorLink f := by
  rcases hrealizes with
    ⟨hfourier, hscale, htimeTail, huntilt, hreal, hevaluator⟩
  refine ⟨completedValue fourier scale timeTail untilt, ?_, hreal,
    hevaluator⟩
  exact FactoredSmallQCompletedSign.Certificate.output_contains_completedValue
    hcheck hfourier hscale htimeTail huntilt

/-- Source-shaped realization predicate.  The scale and untilt are exactly
`2*pi/b` and `exp(-pi*eta*t/4)` at this endpoint's checked rational time.
The source denominator and eta-range guards remain explicit conjuncts. -/
def SourceRealizes (endpoint : SignedEndpoint)
    (fourierDisks : CellKey → ComplexDisk) (f : ℝ → ℝ)
    (fourier timeTail : ℂ) (b eta : ℝ) : Prop :=
  0 < b ∧ -1 < eta ∧ eta < 1 ∧
  endpoint.Realizes fourierDisks f fourier (sourceScale b) timeTail
    (sourceUntilt eta (endpoint.time : ℝ))

theorem evaluatorLink_of_sourceRealizes
    {endpoint : SignedEndpoint}
    {fourierDisks : CellKey → ComplexDisk} {f : ℝ → ℝ}
    {fourier timeTail : ℂ} {b eta : ℝ}
    (hcheck : endpoint.check fourierDisks = true)
    (hrealizes : endpoint.SourceRealizes fourierDisks f fourier timeTail
      b eta) : endpoint.EvaluatorLink f :=
  evaluatorLink_of_realizes hcheck hrealizes.2.2.2

end SignedEndpoint

/-- A pair of completed-sign endpoints intended to isolate one zero.  The
shared rational `a` is the source sampling rate. -/
structure CompletedSignBracket where
  a : ℚ
  lower : SignedEndpoint
  upper : SignedEndpoint
  deriving Repr, DecidableEq, BEq

namespace CompletedSignBracket

/-- Exact two-case meaning of opposite stored signs. -/
def OppositeSigns (lower upper : StrictSign) : Prop :=
  (lower = .negative ∧ upper = .positive) ∨
  (lower = .positive ∧ upper = .negative)

instance (lower upper : StrictSign) : Decidable (OppositeSigns lower upper) := by
  unfold OppositeSigns
  infer_instance

/-- Every finite condition checked before a pair is exposed as a rational
bracket.  Both the sample order and the rational-time order are checked, even
though the exact positive-`a` grid equations make the latter redundant. -/
def IsValid (bracket : CompletedSignBracket)
    (fourierDisks : CellKey → ComplexDisk) : Prop :=
  0 < bracket.a ∧
  bracket.lower.key.characterId = bracket.upper.key.characterId ∧
  bracket.lower.key.frequency < bracket.upper.key.frequency ∧
  bracket.lower.time = SignedEndpoint.sourceTime bracket.a bracket.lower.key ∧
  bracket.upper.time = SignedEndpoint.sourceTime bracket.a bracket.upper.key ∧
  bracket.lower.time < bracket.upper.time ∧
  bracket.lower.check fourierDisks = true ∧
  bracket.upper.check fourierDisks = true ∧
  OppositeSigns bracket.lower.certificate.sign
    bracket.upper.certificate.sign

instance (bracket : CompletedSignBracket)
    (fourierDisks : CellKey → ComplexDisk) :
    Decidable (bracket.IsValid fourierDisks) := by
  unfold IsValid
  infer_instance

/-- Exact-rational, fail-closed checker for one pair. -/
def check (bracket : CompletedSignBracket)
    (fourierDisks : CellKey → ComplexDisk) : Bool :=
  decide (bracket.IsValid fourierDisks)

@[simp] theorem check_eq_true {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk} :
    bracket.check fourierDisks = true ↔ bracket.IsValid fourierDisks := by
  simp [check]

@[simp] theorem check_eq_false {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk} :
    bracket.check fourierDisks = false ↔
      ¬ bracket.IsValid fourierDisks := by
  simp [check]

/-- Canonical projection to the established zero-isolation wire interface. -/
def toRationalBracket (bracket : CompletedSignBracket) : RationalBracket := {
  lower := bracket.lower.time
  upper := bracket.upper.time
  lowerValue := realProjection bracket.lower.certificate.output
  upperValue := realProjection bracket.upper.certificate.output
}

/-- A valid lower endpoint has exactly the source real time
`lowerSample / a`. -/
theorem lower_time_cast_eq_source
    {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk}
    (hvalid : bracket.IsValid fourierDisks) :
    (bracket.lower.time : ℝ) =
      (bracket.lower.key.frequency : ℝ) / (bracket.a : ℝ) := by
  rw [hvalid.2.2.2.1]
  exact SignedEndpoint.sourceTime_cast _ _

/-- A valid upper endpoint has exactly the source real time
`upperSample / a`. -/
theorem upper_time_cast_eq_source
    {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk}
    (hvalid : bracket.IsValid fourierDisks) :
    (bracket.upper.time : ℝ) =
      (bracket.upper.key.frequency : ℝ) / (bracket.a : ℝ) := by
  rw [hvalid.2.2.2.2.1]
  exact SignedEndpoint.sourceTime_cast _ _

/-- All local `RationalBracket` conditions follow from the paired
completed-sign check. -/
theorem toRationalBracket_isValid
    {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk}
    (hvalid : bracket.IsValid fourierDisks) :
    bracket.toRationalBracket.IsValid := by
  rcases hvalid with
    ⟨_aPositive, _sameCharacter, _samplesIncrease, _lowerGrid,
      _upperGrid, htimes, hlowerCheck, hupperCheck, hopposite⟩
  have hlowerCertified := SignedEndpoint.output_certifiedBy hlowerCheck
  have hupperCertified := SignedEndpoint.output_certifiedBy hupperCheck
  refine ⟨htimes,
    realProjection_isValid
      (SignedEndpoint.output_radius_nonneg hlowerCheck),
    realProjection_isValid
      (SignedEndpoint.output_radius_nonneg hupperCheck), ?_⟩
  rcases hopposite with
    ⟨hlowerSign, hupperSign⟩ | ⟨hlowerSign, hupperSign⟩
  · left
    rw [hlowerSign] at hlowerCertified
    rw [hupperSign] at hupperCertified
    simp only [StrictSign.CertifiedBy] at hlowerCertified hupperCertified
    constructor <;> simp only [toRationalBracket, realProjection_hi,
      realProjection_lo]
    · linarith [hlowerCertified.2]
    · linarith [hupperCertified.2]
  · right
    rw [hlowerSign] at hlowerCertified
    rw [hupperSign] at hupperCertified
    simp only [StrictSign.CertifiedBy] at hlowerCertified hupperCertified
    constructor <;> simp only [toRationalBracket, realProjection_hi,
      realProjection_lo]
    · linarith [hupperCertified.2]
    · linarith [hlowerCertified.2]

/-- Successful pair checking produces a successfully checked
`RationalBracket`; no evaluator premise is needed for this arithmetic step. -/
theorem toRationalBracket_check
    {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk}
    (hcheck : bracket.check fourierDisks = true) :
    bracket.toRationalBracket.check = true :=
  RationalBracket.check_eq_true.mpr
    (toRationalBracket_isValid (check_eq_true.mp hcheck))

/-- Explicit endpoint links make the projected rational intervals sound for
the named evaluator. -/
theorem toRationalBracket_enclosesEndpoints
    {bracket : CompletedSignBracket} {f : ℝ → ℝ}
    (hlower : bracket.lower.EvaluatorLink f)
    (hupper : bracket.upper.EvaluatorLink f) :
    bracket.toRationalBracket.EnclosesEndpoints f := by
  rcases hlower with ⟨lowerValue, hlowerContains, hlowerReal, hlowerEq⟩
  rcases hupper with ⟨upperValue, hupperContains, hupperReal, hupperEq⟩
  constructor
  · change (realProjection bracket.lower.certificate.output).ContainsReal
      (f (bracket.lower.time : ℝ))
    rw [hlowerEq]
    apply realProjection_contains_real
    have heq : ((lowerValue.re : ℝ) : ℂ) = lowerValue := by
      apply Complex.ext
      · simp
      · simpa using hlowerReal.symm
    rwa [heq]
  · change (realProjection bracket.upper.certificate.output).ContainsReal
      (f (bracket.upper.time : ℝ))
    rw [hupperEq]
    apply realProjection_contains_real
    have heq : ((upperValue.re : ℝ) : ℂ) = upperValue := by
      apply Complex.ext
      · simp
      · simpa using hupperReal.symm
    rwa [heq]

/-- The complete one-bracket handoff: an executable checked rational bracket
and evaluator-specific endpoint enclosures. -/
theorem checkedRationalBracket
    {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk} {f : ℝ → ℝ}
    (hcheck : bracket.check fourierDisks = true)
    (hlower : bracket.lower.EvaluatorLink f)
    (hupper : bracket.upper.EvaluatorLink f) :
    bracket.toRationalBracket.check = true ∧
      bracket.toRationalBracket.EnclosesEndpoints f :=
  ⟨toRationalBracket_check hcheck,
    toRationalBracket_enclosesEndpoints hlower hupper⟩

/-- A convenience handoff retaining all post-DFT analytic premises rather
than assuming final-output containment directly. -/
theorem checkedRationalBracket_of_realizes
    {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk} {f : ℝ → ℝ}
    {lowerFourier upperFourier lowerTail upperTail : ℂ}
    {lowerScale upperScale lowerUntilt upperUntilt : ℝ}
    (hcheck : bracket.check fourierDisks = true)
    (hlower : bracket.lower.Realizes fourierDisks f lowerFourier lowerScale
      lowerTail lowerUntilt)
    (hupper : bracket.upper.Realizes fourierDisks f upperFourier upperScale
      upperTail upperUntilt) :
    bracket.toRationalBracket.check = true ∧
      bracket.toRationalBracket.EnclosesEndpoints f := by
  have hvalid := check_eq_true.mp hcheck
  exact checkedRationalBracket hcheck
    (SignedEndpoint.evaluatorLink_of_realizes hvalid.2.2.2.2.2.2.1 hlower)
    (SignedEndpoint.evaluatorLink_of_realizes
      hvalid.2.2.2.2.2.2.2.1 hupper)

/-- Source-shaped handoff using one common `b` and `eta` at the two exact
rational source times.  In particular, the caller cannot substitute generic
scale or untilt functions for the source formulas. -/
theorem checkedRationalBracket_of_sourceRealizes
    {bracket : CompletedSignBracket}
    {fourierDisks : CellKey → ComplexDisk} {f : ℝ → ℝ}
    {lowerFourier upperFourier lowerTail upperTail : ℂ}
    {b eta : ℝ}
    (hcheck : bracket.check fourierDisks = true)
    (hlower : bracket.lower.SourceRealizes fourierDisks f lowerFourier
      lowerTail b eta)
    (hupper : bracket.upper.SourceRealizes fourierDisks f upperFourier
      upperTail b eta) :
    bracket.toRationalBracket.check = true ∧
      bracket.toRationalBracket.EnclosesEndpoints f := by
  have hvalid := check_eq_true.mp hcheck
  exact checkedRationalBracket hcheck
    (SignedEndpoint.evaluatorLink_of_sourceRealizes
      hvalid.2.2.2.2.2.2.1 hlower)
    (SignedEndpoint.evaluatorLink_of_sourceRealizes
      hvalid.2.2.2.2.2.2.2.1 hupper)

end CompletedSignBracket

/-! ## Ordered families -/

/-- A fixed-size family of checked completed-sign pairs for one character and
one source sampling rate.  Storing the header once prevents a family for one
real evaluator from silently combining different characters or grids. -/
structure CompletedSignBracketFamily (count : Nat) where
  a : ℚ
  characterId : Nat
  entries : Fin count → CompletedSignBracket

namespace CompletedSignBracketFamily

/-- Pointwise canonical projection to the established rational family. -/
def toRationalBracketFamily {count : Nat}
    (family : CompletedSignBracketFamily count) :
    RationalBracketFamily count :=
  ⟨fun i ↦ (family.entries i).toRationalBracket⟩

/-- Exact family acceptance: the shared source header is positive, every
source-keyed pair is attached to that same grid and character, and the
projected rational family has the required all-pairs strict separation. -/
def IsValid {count : Nat} (family : CompletedSignBracketFamily count)
    (fourierDisks : CellKey → ComplexDisk) : Prop :=
  0 < family.a ∧
  (∀ i, (family.entries i).a = family.a ∧
    (family.entries i).lower.key.characterId = family.characterId ∧
    (family.entries i).IsValid fourierDisks) ∧
  family.toRationalBracketFamily.IsValid

instance {count : Nat} (family : CompletedSignBracketFamily count)
    (fourierDisks : CellKey → ComplexDisk) :
    Decidable (family.IsValid fourierDisks) := by
  unfold IsValid
  infer_instance

/-- Executable exact-rational check for the keyed pairs and their global
ordering. -/
def check {count : Nat} (family : CompletedSignBracketFamily count)
    (fourierDisks : CellKey → ComplexDisk) : Bool :=
  decide (family.IsValid fourierDisks)

@[simp] theorem check_eq_true {count : Nat}
    {family : CompletedSignBracketFamily count}
    {fourierDisks : CellKey → ComplexDisk} :
    family.check fourierDisks = true ↔ family.IsValid fourierDisks := by
  simp [check]

@[simp] theorem check_eq_false {count : Nat}
    {family : CompletedSignBracketFamily count}
    {fourierDisks : CellKey → ComplexDisk} :
    family.check fourierDisks = false ↔
      ¬ family.IsValid fourierDisks := by
  simp [check]

/-- A checked bridge family is accepted verbatim by the existing rational
family checker. -/
theorem toRationalBracketFamily_check {count : Nat}
    {family : CompletedSignBracketFamily count}
    {fourierDisks : CellKey → ComplexDisk}
    (hcheck : family.check fourierDisks = true) :
    family.toRationalBracketFamily.check = true :=
  RationalBracketFamily.check_eq_true.mpr (check_eq_true.mp hcheck).2.2

/-- Family-level bridge into the existing generic zero-certificate theorem. -/
theorem exists_zeroCertificate {count : Nat}
    (family : CompletedSignBracketFamily count)
    {fourierDisks : CellKey → ComplexDisk} {f : ℝ → ℝ}
    (hcheck : family.check fourierDisks = true)
    (hlinks : ∀ i,
      (family.entries i).lower.EvaluatorLink f ∧
      (family.entries i).upper.EvaluatorLink f) :
    ∃ certificate : ZeroCertificate f count,
      ∀ i,
        (certificate.brackets i).lower =
            (family.entries i).lower.time ∧
        (certificate.brackets i).upper =
            (family.entries i).upper.time := by
  apply RationalBracketFamily.exists_zeroCertificate
    family.toRationalBracketFamily
    (toRationalBracketFamily_check hcheck)
  intro i
  exact CompletedSignBracket.toRationalBracket_enclosesEndpoints
    (hlinks i).1 (hlinks i).2

end CompletedSignBracketFamily

end SparkInterval.Dirichlet.FactoredSmallQZeroBracket
