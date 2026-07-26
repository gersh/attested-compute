/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQModulusCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign

/-!
# Ordered-modulus raw DFT to completed-sign campaign

This is the outer finite-index layer above
`FactoredSmallQRawCompletedSignCampaign`.  The application owns an ordered
list of pairs

```
(full power-of-two DFT specification, retained source-sample specification).
```

The checker requires that list to be nonempty, have unique moduli, and satisfy
the exact modulus, roster, full-length, and retained-length equations for
every entry.  A `List.Forall₂` relation then matches one complete arithmetic
bundle to each source entry in exactly that order.  Consequently neither a
valid DFT trace nor a sign certificate for one modulus can be substituted for
another.

All non-finite mathematical inputs are carried by a second, identically
ordered `Forall₂` relation.  Gaussian bases, character values, prefactors,
postprocessing tails, raw-transform decoding, transcendental roots, scaling,
time tails, untilting, and functional-equation reality therefore remain
explicit and modulus-local.  This module does not assert that a roster is the
paper's primitive-character roster and assigns no mathematical meaning to a
byte stream, digest, compiler, CPU, GPU, or physical execution.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign
open SparkInterval.Dirichlet.FactoredSmallQRawDFT
open SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

/-! ## Source-owned ordered modulus domain -/

/-- One source modulus, with the full DFT and retained-sample domains kept as
separate named objects. -/
structure ModulusSpec where
  full : Spec
  source : SourceSampleSpec
  deriving Repr, DecidableEq, BEq

namespace ModulusSpec

/-- The exact equations required before a full line and a retained sample
line may be treated as two views of the same source modulus. -/
def WellFormed (logLength : Nat) (spec : ModulusSpec) : Prop :=
  spec.full.WellFormed ∧
    SourceDFTAgreement logLength spec.full spec.source

instance (logLength : Nat) (spec : ModulusSpec) :
    Decidable (spec.WellFormed logLength) := by
  unfold WellFormed
  infer_instance

end ModulusSpec

/-- Application-owned ordered list of all source moduli. -/
structure SourceSpec where
  moduli : List ModulusSpec
  deriving Repr, DecidableEq, BEq

namespace SourceSpec

def AllWellFormed (logLength : Nat) : List ModulusSpec → Prop
  | [] => True
  | spec :: rest =>
      spec.WellFormed logLength ∧ AllWellFormed logLength rest

instance (logLength : Nat) (specs : List ModulusSpec) :
    Decidable (AllWellFormed logLength specs) := by
  induction specs with
  | nil => exact isTrue trivial
  | cons spec rest inductionHypothesis =>
      rw [AllWellFormed]
      letI : Decidable (spec.WellFormed logLength) := inferInstance
      exact instDecidableAnd

/-- Nonvacuity, unique source modulus numbers, and every exact local domain
equation.  Uniqueness is read from the full specification; local agreement
also proves that it is the retained specification's modulus. -/
def WellFormed (logLength : Nat) (source : SourceSpec) : Prop :=
  source.moduli ≠ [] ∧
  (source.moduli.map (fun spec ↦ spec.full.q)).Nodup ∧
  AllWellFormed logLength source.moduli

instance (logLength : Nat) (source : SourceSpec) :
    Decidable (source.WellFormed logLength) := by
  unfold WellFormed
  infer_instance

end SourceSpec

/-! ## One complete finite bundle per modulus -/

/-- All finite certificate objects and exact rational disk tables for one
source modulus.  The common `logLength` reflects the production small-`q`
campaign's single guard-line length. -/
structure ModulusBundle (logLength : Nat) where
  postprocessCampaign : RawPostprocessCampaignCertificate
  naturalDisks : CellKey → ComplexDisk
  fourierDisks : CellKey → ComplexDisk
  rawTransforms : Nat → RawCertificate logLength
  bounds : Nat → Bounds
  signCampaign : SignCampaignCertificate

namespace ModulusBundle

/-- Total fallback used only to define a canonical projection from `Option`.
An accepted raw transform proves that this branch is unreachable. -/
def fallbackDecoded (logLength : Nat) : DecodedCertificate logLength := {
  inputValues := []
  twiddleValues := []
  stageValues := []
  outputValues := []
}

/-- The typed transform is not separately supplied certificate data: it is
the canonical result of decoding the literal raw transform.  This removes a
potential substitution boundary entirely. -/
def decodedTransform {logLength : Nat} (bundle : ModulusBundle logLength)
    (characterId : Nat) : DecodedCertificate logLength :=
  (bundle.rawTransforms characterId).decode.getD
    (fallbackDecoded logLength)

/-- An accepted raw check proves that canonical projection selected the
actual successful decode, never the fallback. -/
theorem raw_decode_eq {logLength : Nat} {bundle : ModulusBundle logLength}
    {characterId : Nat}
    (hcheck : (bundle.rawTransforms characterId).check
      (bundle.bounds characterId) = true) :
    (bundle.rawTransforms characterId).decode =
      some (bundle.decodedTransform characterId) := by
  rcases RawCertificate.checker_sound hcheck with
    ⟨_, decoded, hdecode, _, _, _⟩
  simp [decodedTransform, hdecode]

end ModulusBundle

/-- Exact raw-transform checks on the source-owned character roster. -/
def allRawChecks {logLength : Nat} (spec : ModulusSpec)
    (bundle : ModulusBundle logLength) : Bool :=
  spec.full.roster.all fun characterId ↦
    (bundle.rawTransforms characterId).check (bundle.bounds characterId)

theorem allRawChecks_sound {logLength : Nat} {spec : ModulusSpec}
    {bundle : ModulusBundle logLength}
    (hcheck : allRawChecks spec bundle = true) :
    ∀ characterId, characterId ∈ spec.full.roster →
      (bundle.rawTransforms characterId).check
        (bundle.bounds characterId) = true := by
  intro characterId hcharacter
  exact (List.all_eq_true.mp hcheck) characterId hcharacter

namespace ModulusBundle

/-- Human-readable proposition recovered from the local Boolean checker. -/
def Accepted {logLength : Nat} (bundle : ModulusBundle logLength)
    (spec : ModulusSpec) (termCount : CellKey → Nat)
    (oddParity negativeFrequency : CellKey → Bool) : Prop :=
  bridgeCheck spec.full spec.source bundle.fourierDisks
      bundle.decodedTransform = true ∧
  FactoredSmallQRawPostprocessCampaign.check spec.full termCount oddParity
      negativeFrequency bundle.postprocessCampaign = true ∧
  linkCheck spec.full bundle.postprocessCampaign bundle.naturalDisks
      (fun characterId ↦
        (bundle.decodedTransform characterId).certificate) = true ∧
  (∀ characterId, characterId ∈ spec.full.roster →
    (bundle.rawTransforms characterId).check
      (bundle.bounds characterId) = true) ∧
  sourceCheck spec.source (lineLength logLength) bundle.fourierDisks
      bundle.signCampaign = true

/-- Local finite replay.  Every predicate is supplied by the application or
is a checker from a lower arithmetic layer. -/
def check {logLength : Nat} (bundle : ModulusBundle logLength)
    (spec : ModulusSpec) (termCount : CellKey → Nat)
    (oddParity negativeFrequency : CellKey → Bool) : Bool :=
  bridgeCheck spec.full spec.source bundle.fourierDisks
      bundle.decodedTransform &&
  (FactoredSmallQRawPostprocessCampaign.check spec.full termCount oddParity
      negativeFrequency bundle.postprocessCampaign &&
  (linkCheck spec.full bundle.postprocessCampaign bundle.naturalDisks
      (fun characterId ↦
        (bundle.decodedTransform characterId).certificate) &&
  (allRawChecks spec bundle &&
  sourceCheck spec.source (lineLength logLength) bundle.fourierDisks
      bundle.signCampaign)))

theorem checker_sound {logLength : Nat} {bundle : ModulusBundle logLength}
    {spec : ModulusSpec} {termCount : CellKey → Nat}
    {oddParity negativeFrequency : CellKey → Bool}
    (hcheck : bundle.check spec termCount oddParity negativeFrequency =
      true) :
    bundle.Accepted spec termCount oddParity negativeFrequency := by
  simp only [check, Bool.and_eq_true] at hcheck
  exact ⟨hcheck.1, hcheck.2.1, hcheck.2.2.1,
    allRawChecks_sound hcheck.2.2.2.1, hcheck.2.2.2.2⟩

end ModulusBundle

/-- One complete finite bundle for each source modulus. -/
structure Certificate (logLength : Nat) where
  moduli : List (ModulusBundle logLength)

/-- Ordered source/bundle matching. -/
def Matched {logLength : Nat}
    (termCount : ModulusSpec → CellKey → Nat)
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool) :
    List ModulusSpec → List (ModulusBundle logLength) → Prop :=
  List.Forall₂ fun spec bundle ↦
    bundle.Accepted spec (termCount spec) (oddParity spec)
      (negativeFrequency spec)

/-- Recursive finite replay; unequal list lengths and any reordered bundle
fail closed. -/
def checkPairs {logLength : Nat}
    (termCount : ModulusSpec → CellKey → Nat)
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool) :
    List ModulusSpec → List (ModulusBundle logLength) → Bool
  | [], [] => true
  | spec :: specs, bundle :: bundles =>
      bundle.check spec (termCount spec) (oddParity spec)
          (negativeFrequency spec) &&
        checkPairs termCount oddParity negativeFrequency specs bundles
  | _, _ => false

/-- Full outer checker: exact source-domain equations, unique moduli, exact
order and length, and every local finite arithmetic check. -/
def Certificate.check {logLength : Nat} (certificate : Certificate logLength)
    (source : SourceSpec)
    (termCount : ModulusSpec → CellKey → Nat)
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool) :
    Bool :=
  decide (source.WellFormed logLength) &&
    checkPairs termCount oddParity negativeFrequency source.moduli
      certificate.moduli

theorem checkPairs_sound {logLength : Nat}
    {termCount : ModulusSpec → CellKey → Nat}
    {oddParity negativeFrequency : ModulusSpec → CellKey → Bool}
    {specs : List ModulusSpec}
    {bundles : List (ModulusBundle logLength)}
    (hcheck : checkPairs termCount oddParity negativeFrequency specs bundles =
      true) :
    Matched termCount oddParity negativeFrequency specs bundles := by
  induction specs generalizing bundles with
  | nil =>
      cases bundles with
      | nil => exact List.Forall₂.nil
      | cons bundle rest => simp [checkPairs] at hcheck
  | cons spec specs inductionHypothesis =>
      cases bundles with
      | nil => simp [checkPairs] at hcheck
      | cons bundle bundles =>
          simp only [checkPairs, Bool.and_eq_true] at hcheck
          exact List.Forall₂.cons
            (ModulusBundle.checker_sound hcheck.1)
            (inductionHypothesis hcheck.2)

/-- Outer soundness exposes both the source-owned domain equations and the
ordered relation to every finite bundle. -/
theorem Certificate.checker_sound {logLength : Nat}
    {certificate : Certificate logLength} {source : SourceSpec}
    {termCount : ModulusSpec → CellKey → Nat}
    {oddParity negativeFrequency : ModulusSpec → CellKey → Bool}
    (hcheck : certificate.check source termCount oddParity
      negativeFrequency = true) :
    source.WellFormed logLength ∧
      Matched termCount oddParity negativeFrequency source.moduli
        certificate.moduli := by
  simp only [Certificate.check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1, checkPairs_sound hcheck.2⟩

/-! ## Explicit modulus-aligned mathematical inputs -/

/-- All non-finite inputs needed by the existing raw-word-to-sign endpoint,
for one exact source/bundle pair.  Raw decoding is absent from this list:
`ModulusBundle.decodedTransform` is definitionally the canonical decode of
the raw words, and an accepted raw check proves that decoding succeeded. -/
def ApplicationInputsFor {logLength : Nat}
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool)
    (w prefactors delta : ModulusSpec → CellKey → ℂ)
    (characters : ModulusSpec → CellKey → List ℂ)
    (scale : ModulusSpec → CellKey → ℝ)
    (timeTail : ModulusSpec → CellKey → ℂ)
    (untilt : ModulusSpec → CellKey → ℝ)
    (spec : ModulusSpec) (bundle : ModulusBundle logLength) : Prop :=
  BaseDisksContain bundle.postprocessCampaign (w spec) ∧
  CharacterDisksContain bundle.postprocessCampaign (characters spec) ∧
  PrefactorDisksContain bundle.postprocessCampaign (prefactors spec) ∧
  TailPerturbationsBound bundle.postprocessCampaign (delta spec) ∧
  (∀ characterId, characterId ∈ spec.full.roster →
    TwiddlesContain (logLength := logLength)
      (bundle.decodedTransform characterId).certificate.twiddleDisks
      positiveTwiddle) ∧
  ScaleDisksContain bundle.signCampaign (scale spec) ∧
  TimeTailsBound bundle.signCampaign (timeTail spec) ∧
  UntiltDisksContain bundle.signCampaign (untilt spec) ∧
  CompletedValuesReal bundle.signCampaign
    (directFourier (logLength := logLength) (oddParity spec)
      (negativeFrequency spec) (w spec) (prefactors spec) (delta spec)
      (characters spec))
    (scale spec) (timeTail spec) (untilt spec)

/-- The same mathematical-input relation as the finite bundle relation, in
the same order and with the same list length. -/
def ApplicationInputsAligned {logLength : Nat}
    (source : SourceSpec) (certificate : Certificate logLength)
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool)
    (w prefactors delta : ModulusSpec → CellKey → ℂ)
    (characters : ModulusSpec → CellKey → List ℂ)
    (scale : ModulusSpec → CellKey → ℝ)
    (timeTail : ModulusSpec → CellKey → ℂ)
    (untilt : ModulusSpec → CellKey → ℝ) : Prop :=
  List.Forall₂
    (ApplicationInputsFor oddParity negativeFrequency w prefactors delta
      characters scale timeTail untilt)
    source.moduli certificate.moduli

private theorem exists_aligned_modulus {logLength : Nat}
    {termCount : ModulusSpec → CellKey → Nat}
    {oddParity negativeFrequency : ModulusSpec → CellKey → Bool}
    {w prefactors delta : ModulusSpec → CellKey → ℂ}
    {characters : ModulusSpec → CellKey → List ℂ}
    {scale : ModulusSpec → CellKey → ℝ}
    {timeTail : ModulusSpec → CellKey → ℂ}
    {untilt : ModulusSpec → CellKey → ℝ}
    {specs : List ModulusSpec}
    {bundles : List (ModulusBundle logLength)}
    (hmatched : Matched termCount oddParity negativeFrequency specs bundles)
    (hinputs : List.Forall₂
      (ApplicationInputsFor oddParity negativeFrequency w prefactors delta
        characters scale timeTail untilt)
      specs bundles)
    {spec : ModulusSpec} (hspec : spec ∈ specs) :
    ∃ bundle, bundle ∈ bundles ∧
      bundle.Accepted spec (termCount spec) (oddParity spec)
        (negativeFrequency spec) ∧
      ApplicationInputsFor oddParity negativeFrequency w prefactors delta
        characters scale timeTail untilt spec bundle := by
  induction hmatched with
  | nil => simp at hspec
  | @cons headSpec headBundle tailSpecs tailBundles headMatched tailMatched
      inductionHypothesis =>
      cases hinputs with
      | cons headInputs tailInputs =>
          simp only [List.mem_cons] at hspec
          rcases hspec with hspec | hspec
          · subst spec
            exact ⟨headBundle, by simp, headMatched, headInputs⟩
          · rcases inductionHypothesis tailInputs hspec with
              ⟨found, hfound, haccepted, hfoundInputs⟩
            exact ⟨found, by simp [hfound], haccepted, hfoundInputs⟩

/-! ## Requested modulus/character/sample endpoint -/

/-- Every requested source modulus, character, and retained sample returns
the actual aligned bundle, the literal raw DFT word, exact direct-DFT
containment, and the checked strict completed sign.

The theorem is conditional only on the explicitly listed analytic and exact
decode/root links.  The source-domain and bundle checks prevent any of those
premises from being transported from a different modulus. -/
theorem requested_modulus_sample_has_direct_sign
    {logLength : Nat}
    {source : SourceSpec} {certificate : Certificate logLength}
    {termCount : ModulusSpec → CellKey → Nat}
    {oddParity negativeFrequency : ModulusSpec → CellKey → Bool}
    {w prefactors delta : ModulusSpec → CellKey → ℂ}
    {characters : ModulusSpec → CellKey → List ℂ}
    {scale : ModulusSpec → CellKey → ℝ}
    {timeTail : ModulusSpec → CellKey → ℂ}
    {untilt : ModulusSpec → CellKey → ℝ}
    (hcheck : certificate.check source termCount oddParity
      negativeFrequency = true)
    (hinputs : ApplicationInputsAligned source certificate oddParity
      negativeFrequency w prefactors delta characters scale timeTail untilt)
    {spec : ModulusSpec} (hspec : spec ∈ source.moduli)
    {characterId sample : Nat}
    (hcharacter : characterId ∈ spec.source.roster)
    (hsample : sample < spec.source.sampleCount) :
    ∃ bundle, bundle ∈ certificate.moduli ∧
      sample < lineLength logLength ∧
      ∃ rawDisk : ComplexDisk.Raw,
        (bundle.rawTransforms characterId).output[sample]? = some rawDisk ∧
        rawDisk.decode =
          some (bundle.fourierDisks ⟨characterId, sample⟩) ∧
        (bundle.fourierDisks ⟨characterId, sample⟩).ContainsComplex
          (directFourier (logLength := logLength) (oddParity spec)
            (negativeFrequency spec) (w spec) (prefactors spec) (delta spec)
            (characters spec) ⟨characterId, sample⟩) ∧
        ∃ batch, batch ∈ bundle.signCampaign.batches ∧
          ∃ cell, cell ∈ batch.cells ∧
            cell.key = ⟨characterId, sample⟩ ∧
            cell.payload.sign.Holds
              (completedValue
                (directFourier (logLength := logLength) (oddParity spec)
                  (negativeFrequency spec) (w spec) (prefactors spec)
                  (delta spec) (characters spec)
                  ⟨characterId, sample⟩)
                (scale spec ⟨characterId, sample⟩)
                (timeTail spec ⟨characterId, sample⟩)
                (untilt spec ⟨characterId, sample⟩)).re := by
  have hsound := Certificate.checker_sound hcheck
  rcases exists_aligned_modulus hsound.2 hinputs hspec with
    ⟨bundle, hbundle, haccepted, hbundleInputs⟩
  rcases haccepted with
    ⟨hbridge, hpostprocess, hlinks, hrawChecks, hsignCheck⟩
  rcases hbundleInputs with
    ⟨hbases, hcharacters, hprefactors, hpostprocessTails, hroots, hscale,
      htimeTail, huntilt, hreal⟩
  rcases linkCheck_sound hlinks with ⟨houtputs, htransformInputs⟩
  have hdecodes : ∀ characterId, characterId ∈ spec.full.roster →
      (bundle.rawTransforms characterId).decode =
        some (bundle.decodedTransform characterId) := by
    intro characterId hcharacter
    exact bundle.raw_decode_eq (hrawChecks characterId hcharacter)
  have hrawLinked :
      RawTransformsLinked spec.full bundle.naturalDisks
        bundle.rawTransforms bundle.decodedTransform :=
    ⟨hdecodes, htransformInputs⟩
  have hresult := requested_source_sample_has_direct_sign
    hbridge hpostprocess hbases hcharacters hprefactors hpostprocessTails
      houtputs hrawLinked hrawChecks hroots hsignCheck hscale htimeTail
      huntilt hreal hcharacter hsample
  exact ⟨bundle, hbundle, hresult⟩

/-! ## Source-shaped headers and endpoint -/

/-- One header-wide analytic parameter set and one source-owned time-tail
function for a modulus.  Neither may vary by certificate batch.  Time itself
is not a field: `SourceParameters.t` derives it from `sample / a`. -/
structure SourceHeader where
  parameters : SourceParameters
  timeTail : CellKey → ℂ

/-- Lightweight ordered relation used to audit just the source headers and
their grid equations without inventing functional-equation reality data.
The full relation below strengthens each pair with every arithmetic and
analytic premise. -/
def SourceHeadersAligned {logLength : Nat}
    (source : SourceSpec) (certificate : Certificate logLength)
    (headers : ModulusSpec → SourceHeader) : Prop :=
  List.Forall₂
    (fun spec _bundle ↦
      (headers spec).parameters.GridValid logLength)
    source.moduli certificate.moduli

/-- Source-shaped inputs for one exact source/bundle pair.  In contrast with
`ApplicationInputsFor`, scale and untilt are not arbitrary functions: they
are definitionally `2*pi/b` and `exp(-pi*eta*(sample/a)/4)` from the one
header aligned with this modulus. -/
def SourceApplicationInputsFor {logLength : Nat}
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool)
    (w prefactors delta : ModulusSpec → CellKey → ℂ)
    (characters : ModulusSpec → CellKey → List ℂ)
    (headers : ModulusSpec → SourceHeader)
    (spec : ModulusSpec) (bundle : ModulusBundle logLength) : Prop :=
  BaseDisksContain bundle.postprocessCampaign (w spec) ∧
  CharacterDisksContain bundle.postprocessCampaign (characters spec) ∧
  PrefactorDisksContain bundle.postprocessCampaign (prefactors spec) ∧
  TailPerturbationsBound bundle.postprocessCampaign (delta spec) ∧
  (∀ characterId, characterId ∈ spec.full.roster →
    TwiddlesContain (logLength := logLength)
      (bundle.decodedTransform characterId).certificate.twiddleDisks
      positiveTwiddle) ∧
  (headers spec).parameters.GridValid logLength ∧
  ScaleDisksContain bundle.signCampaign
    (headers spec).parameters.scale ∧
  TimeTailsBound bundle.signCampaign (headers spec).timeTail ∧
  UntiltDisksContain bundle.signCampaign
    (headers spec).parameters.untilt ∧
  SourceCompletedValuesReal bundle.signCampaign
    (directFourier (logLength := logLength) (oddParity spec)
      (negativeFrequency spec) (w spec) (prefactors spec) (delta spec)
      (characters spec))
    (headers spec).parameters (headers spec).timeTail

/-- Exact ordered alignment of every source-shaped header and every premise
needed by the raw-word-to-source-sign theorem. -/
def SourceApplicationInputsAligned {logLength : Nat}
    (source : SourceSpec) (certificate : Certificate logLength)
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool)
    (w prefactors delta : ModulusSpec → CellKey → ℂ)
    (characters : ModulusSpec → CellKey → List ℂ)
    (headers : ModulusSpec → SourceHeader) : Prop :=
  List.Forall₂
    (SourceApplicationInputsFor oddParity negativeFrequency w prefactors
      delta characters headers)
    source.moduli certificate.moduli

/-- The full source-shaped relation projects to the small human-auditable
ordered list of header grid equations. -/
theorem SourceApplicationInputsAligned.headers_aligned
    {logLength : Nat}
    {source : SourceSpec} {certificate : Certificate logLength}
    {oddParity negativeFrequency : ModulusSpec → CellKey → Bool}
    {w prefactors delta : ModulusSpec → CellKey → ℂ}
    {characters : ModulusSpec → CellKey → List ℂ}
    {headers : ModulusSpec → SourceHeader}
    (hinputs : SourceApplicationInputsAligned source certificate oddParity
      negativeFrequency w prefactors delta characters headers) :
    SourceHeadersAligned source certificate headers := by
  unfold SourceApplicationInputsAligned at hinputs
  unfold SourceHeadersAligned
  exact hinputs.imp fun _spec _bundle headInputs ↦
    headInputs.2.2.2.2.2.1

private theorem exists_source_aligned_modulus {logLength : Nat}
    {termCount : ModulusSpec → CellKey → Nat}
    {oddParity negativeFrequency : ModulusSpec → CellKey → Bool}
    {w prefactors delta : ModulusSpec → CellKey → ℂ}
    {characters : ModulusSpec → CellKey → List ℂ}
    {headers : ModulusSpec → SourceHeader}
    {specs : List ModulusSpec}
    {bundles : List (ModulusBundle logLength)}
    (hmatched : Matched termCount oddParity negativeFrequency specs bundles)
    (hinputs : List.Forall₂
      (SourceApplicationInputsFor oddParity negativeFrequency w prefactors
        delta characters headers)
      specs bundles)
    {spec : ModulusSpec} (hspec : spec ∈ specs) :
    ∃ bundle, bundle ∈ bundles ∧
      bundle.Accepted spec (termCount spec) (oddParity spec)
        (negativeFrequency spec) ∧
      SourceApplicationInputsFor oddParity negativeFrequency w prefactors
        delta characters headers spec bundle := by
  induction hmatched with
  | nil => simp at hspec
  | @cons headSpec headBundle tailSpecs tailBundles headMatched tailMatched
      inductionHypothesis =>
      cases hinputs with
      | cons headInputs tailInputs =>
          simp only [List.mem_cons] at hspec
          rcases hspec with hspec | hspec
          · subst spec
            exact ⟨headBundle, by simp, headMatched, headInputs⟩
          · rcases inductionHypothesis tailInputs hspec with
              ⟨found, hfound, haccepted, hfoundInputs⟩
            exact ⟨found, by simp [hfound], haccepted, hfoundInputs⟩

/-- Source-shaped outer endpoint.  For every requested modulus, character,
and retained sample it returns:

* the positive `a` and `b` denominator guards;
* `-1 < eta < 1` and the exact grid equation `b = 2^logLength / a`;
* the literal raw DFT word and direct-DFT enclosure; and
* the strict sign of the exact source expression whose time is
  definitionally `sample / a`.

The generic arbitrary-factor theorem remains available above for reuse. -/
theorem requested_modulus_sample_has_source_sign
    {logLength : Nat}
    {source : SourceSpec} {certificate : Certificate logLength}
    {termCount : ModulusSpec → CellKey → Nat}
    {oddParity negativeFrequency : ModulusSpec → CellKey → Bool}
    {w prefactors delta : ModulusSpec → CellKey → ℂ}
    {characters : ModulusSpec → CellKey → List ℂ}
    {headers : ModulusSpec → SourceHeader}
    (hcheck : certificate.check source termCount oddParity
      negativeFrequency = true)
    (hinputs : SourceApplicationInputsAligned source certificate oddParity
      negativeFrequency w prefactors delta characters headers)
    {spec : ModulusSpec} (hspec : spec ∈ source.moduli)
    {characterId sample : Nat}
    (hcharacter : characterId ∈ spec.source.roster)
    (hsample : sample < spec.source.sampleCount) :
    ∃ bundle, bundle ∈ certificate.moduli ∧
      0 < (headers spec).parameters.a ∧
      0 < (headers spec).parameters.b ∧
      -1 < (headers spec).parameters.eta ∧
      (headers spec).parameters.eta < 1 ∧
      (headers spec).parameters.b =
        (lineLength logLength : ℝ) / (headers spec).parameters.a ∧
      sample < lineLength logLength ∧
      ∃ rawDisk : ComplexDisk.Raw,
        (bundle.rawTransforms characterId).output[sample]? = some rawDisk ∧
        rawDisk.decode =
          some (bundle.fourierDisks ⟨characterId, sample⟩) ∧
        (bundle.fourierDisks ⟨characterId, sample⟩).ContainsComplex
          (directFourier (logLength := logLength) (oddParity spec)
            (negativeFrequency spec) (w spec) (prefactors spec) (delta spec)
            (characters spec) ⟨characterId, sample⟩) ∧
        ∃ batch, batch ∈ bundle.signCampaign.batches ∧
          ∃ cell, cell ∈ batch.cells ∧
            cell.key = ⟨characterId, sample⟩ ∧
            cell.payload.sign.Holds
              (sourceCompletedValue
                (directFourier (logLength := logLength) (oddParity spec)
                  (negativeFrequency spec) (w spec) (prefactors spec)
                  (delta spec) (characters spec)
                  ⟨characterId, sample⟩)
                (headers spec).parameters.b
                (headers spec).parameters.eta
                ((headers spec).parameters.t ⟨characterId, sample⟩)
                ((headers spec).timeTail ⟨characterId, sample⟩)).re := by
  have hsound := Certificate.checker_sound hcheck
  rcases exists_source_aligned_modulus hsound.2 hinputs hspec with
    ⟨bundle, hbundle, haccepted, hbundleInputs⟩
  rcases haccepted with
    ⟨hbridge, hpostprocess, hlinks, hrawChecks, hsignCheck⟩
  rcases hbundleInputs with
    ⟨hbases, hcharacters, hprefactors, hpostprocessTails, hroots, hgrid,
      hscale, htimeTail, huntilt, hreal⟩
  rcases linkCheck_sound hlinks with ⟨houtputs, htransformInputs⟩
  have hdecodes : ∀ characterId, characterId ∈ spec.full.roster →
      (bundle.rawTransforms characterId).decode =
        some (bundle.decodedTransform characterId) := by
    intro requestedCharacter hrequestedCharacter
    exact bundle.raw_decode_eq
      (hrawChecks requestedCharacter hrequestedCharacter)
  have hrawLinked :
      RawTransformsLinked spec.full bundle.naturalDisks
        bundle.rawTransforms bundle.decodedTransform :=
    ⟨hdecodes, htransformInputs⟩
  have hresult := requested_source_sample_has_source_sign
    hbridge hpostprocess hbases hcharacters hprefactors hpostprocessTails
      houtputs hrawLinked hrawChecks hroots hsignCheck hgrid hscale htimeTail
      huntilt hreal hcharacter hsample
  exact ⟨bundle, hbundle, hresult⟩

end SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign
