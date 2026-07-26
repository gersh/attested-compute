/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign

/-!
# Ordered moduli with raw DFT-owned completed-sign payloads

This is the ordered outer layer for
`FactoredSmallQRawCompletedSignPayloadCampaign`.  A finite bundle contains the
literal raw DFT transforms and a campaign of raw completed-sign payloads.  It
does not contain a separately supplied typed Fourier table or decoded
transform: `ModulusBundle.decodedTransform` is the canonical projection of
the raw certificate's decoder.

The application owns a nonempty ordered list of source moduli with unique
modulus numbers.  Exact `List.Forall₂` relations align that list first with
the finite bundles and then with every analytic/source-header premise.  Thus
neither a raw transform, a sign payload, nor an analytic premise can be
silently reused at another list position.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

abbrev SourceSampleSpec :=
  FactoredSmallQCompletedSignCampaign.SourceSampleSpec

abbrev SourceParameters :=
  FactoredSmallQRawCompletedSignCampaign.SourceParameters

abbrev RawSignCampaignCertificate :=
  FactoredSmallQRawCompletedSignPayloadCampaign.RawSignCampaignCertificate

/-! ## Source-owned ordered modulus domain -/

/-- One source modulus, with the full DFT and retained source ranges named
separately. -/
structure ModulusSpec where
  full : Spec
  source : SourceSampleSpec
  deriving Repr, DecidableEq, BEq

namespace ModulusSpec

/-- Exact local equations joining the full DFT line to its retained source
range. -/
def WellFormed (logLength : Nat) (spec : ModulusSpec) : Prop :=
  spec.full.WellFormed ∧
    FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement
      logLength spec.full spec.source

instance (logLength : Nat) (spec : ModulusSpec) :
    Decidable (spec.WellFormed logLength) := by
  unfold WellFormed
  infer_instance

end ModulusSpec

/-- Application-owned ordered list of source moduli. -/
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

/-- The outer source is nonempty, has no duplicate modulus number, and every
local full/source pair satisfies the exact DFT-range equations. -/
def WellFormed (logLength : Nat) (source : SourceSpec) : Prop :=
  source.moduli ≠ [] ∧
    (source.moduli.map (fun spec ↦ spec.full.q)).Nodup ∧
    AllWellFormed logLength source.moduli

instance (logLength : Nat) (source : SourceSpec) :
    Decidable (source.WellFormed logLength) := by
  unfold WellFormed
  infer_instance

end SourceSpec

/-! ## One raw finite bundle per modulus -/

/-- The complete finite data for one source modulus.  Both the raw DFT words
and the raw sign payloads live in this bundle. -/
structure ModulusBundle (logLength : Nat) where
  postprocessCampaign : RawPostprocessCampaignCertificate
  naturalDisks : CellKey → ComplexDisk
  rawTransforms : Nat → FactoredSmallQRawDFT.RawCertificate logLength
  bounds : Nat → FactoredSmallQRawDFT.Bounds
  signCampaign : RawSignCampaignCertificate

namespace ModulusBundle

/-- Total fallback used only to make the decoder projection total.  An
accepted raw check proves that this value was not selected. -/
def fallbackDecoded (logLength : Nat) :
    FactoredSmallQRawDFT.DecodedCertificate logLength := {
  inputValues := []
  twiddleValues := []
  stageValues := []
  outputValues := []
}

/-- The sole typed transform associated with a bundle is obtained by
decoding its literal raw transform. -/
def decodedTransform {logLength : Nat} (bundle : ModulusBundle logLength)
    (characterId : Nat) : FactoredSmallQRawDFT.DecodedCertificate logLength :=
  (bundle.rawTransforms characterId).decode.getD
    (fallbackDecoded logLength)

theorem raw_decode_eq {logLength : Nat} {bundle : ModulusBundle logLength}
    {characterId : Nat}
    (hcheck : (bundle.rawTransforms characterId).check
      (bundle.bounds characterId) = true) :
    (bundle.rawTransforms characterId).decode =
      some (bundle.decodedTransform characterId) := by
  rcases FactoredSmallQRawDFT.RawCertificate.checker_sound hcheck with
    ⟨_, decoded, hdecode, _, _, _⟩
  simp [decodedTransform, hdecode]

end ModulusBundle

/-- Replay every raw transform named by the source-owned character roster. -/
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

/-- Human-readable local finite acceptance proposition. -/
def Accepted {logLength : Nat} (bundle : ModulusBundle logLength)
    (spec : ModulusSpec) (termCount : CellKey → Nat)
    (oddParity negativeFrequency : CellKey → Bool) : Prop :=
  FactoredSmallQRawCompletedSignPayloadCampaign.check spec.full spec.source
      bundle.rawTransforms bundle.signCampaign = true ∧
    FactoredSmallQRawPostprocessCampaign.check spec.full termCount oddParity
      negativeFrequency bundle.postprocessCampaign = true ∧
    linkCheck spec.full bundle.postprocessCampaign bundle.naturalDisks
      (fun characterId ↦
        (bundle.decodedTransform characterId).certificate) = true ∧
    (∀ characterId, characterId ∈ spec.full.roster →
      (bundle.rawTransforms characterId).check
        (bundle.bounds characterId) = true)

/-- Local executable replay. -/
def check {logLength : Nat} (bundle : ModulusBundle logLength)
    (spec : ModulusSpec) (termCount : CellKey → Nat)
    (oddParity negativeFrequency : CellKey → Bool) : Bool :=
  FactoredSmallQRawCompletedSignPayloadCampaign.check spec.full spec.source
      bundle.rawTransforms bundle.signCampaign &&
    (FactoredSmallQRawPostprocessCampaign.check spec.full termCount oddParity
      negativeFrequency bundle.postprocessCampaign &&
    (linkCheck spec.full bundle.postprocessCampaign bundle.naturalDisks
      (fun characterId ↦
        (bundle.decodedTransform characterId).certificate) &&
    allRawChecks spec bundle))

theorem checker_sound {logLength : Nat} {bundle : ModulusBundle logLength}
    {spec : ModulusSpec} {termCount : CellKey → Nat}
    {oddParity negativeFrequency : CellKey → Bool}
    (hcheck : bundle.check spec termCount oddParity negativeFrequency = true) :
    bundle.Accepted spec termCount oddParity negativeFrequency := by
  simp only [check, Bool.and_eq_true] at hcheck
  exact ⟨hcheck.1, hcheck.2.1, hcheck.2.2.1,
    allRawChecks_sound hcheck.2.2.2⟩

end ModulusBundle

/-! ## Exact ordered finite alignment -/

structure Certificate (logLength : Nat) where
  moduli : List (ModulusBundle logLength)

def Matched {logLength : Nat}
    (termCount : ModulusSpec → CellKey → Nat)
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool) :
    List ModulusSpec → List (ModulusBundle logLength) → Prop :=
  List.Forall₂ fun spec bundle ↦
    bundle.Accepted spec (termCount spec) (oddParity spec)
      (negativeFrequency spec)

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

def Certificate.check {logLength : Nat} (certificate : Certificate logLength)
    (source : SourceSpec)
    (termCount : ModulusSpec → CellKey → Nat)
    (oddParity negativeFrequency : ModulusSpec → CellKey → Bool) : Bool :=
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

/-! ## Exact ordered analytic and source-header alignment -/

/-- One modulus-wide source parameter triple and source-owned time-tail
function.  Time is derived from the retained sample index and `a`. -/
structure SourceHeader where
  parameters : SourceParameters
  timeTail : CellKey → ℂ

/-- The complete analytic premises for one exact source/bundle pair. -/
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
    FactoredSmallQRawCompletedSignPayloadCampaign.ScaleDisksContain
      bundle.signCampaign (headers spec).parameters ∧
    FactoredSmallQRawCompletedSignPayloadCampaign.TimeTailsBound
      bundle.signCampaign (headers spec).timeTail ∧
    FactoredSmallQRawCompletedSignPayloadCampaign.UntiltDisksContain
      bundle.signCampaign (headers spec).parameters ∧
    FactoredSmallQRawCompletedSignPayloadCampaign.SourceCompletedValuesReal
      (logLength := logLength) bundle.signCampaign (oddParity spec)
      (negativeFrequency spec) (w spec) (prefactors spec) (delta spec)
      (characters spec) (headers spec).parameters (headers spec).timeTail

/-- One exact ordered `Forall₂` relates every source header and analytic
premise to the same bundle position as the finite checker. -/
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

/-- A lightweight projection for auditing source-header order without
manufacturing functional-equation reality fixtures. -/
def SourceHeadersAligned {logLength : Nat}
    (source : SourceSpec) (certificate : Certificate logLength)
    (headers : ModulusSpec → SourceHeader) : Prop :=
  List.Forall₂
    (fun spec _bundle ↦ (headers spec).parameters.GridValid logLength)
    source.moduli certificate.moduli

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

/-! ## Requested modulus/character/sample endpoint -/

/-- Every requested source cell returns the aligned bundle, exact literal raw
DFT word, raw completed-sign payload attached to that word, its typed decode,
the explicit source guards, and the strict sign of the source formula. -/
theorem requested_modulus_sample_has_raw_source_sign
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
        (FactoredSmallQRawDFT.lineLength logLength : ℝ) /
          (headers spec).parameters.a ∧
      sample < FactoredSmallQRawDFT.lineLength logLength ∧
      ∃ fourierWord : ComplexDisk.Raw,
        (bundle.rawTransforms characterId).output[sample]? =
          some fourierWord ∧
        ∃ fourierDisk : ComplexDisk,
          fourierWord.decode = some fourierDisk ∧
          fourierDisk.ContainsComplex
            (FactoredSmallQRawCompletedSignCampaign.directFourier
              (logLength := logLength) (oddParity spec)
              (negativeFrequency spec) (w spec) (prefactors spec)
              (delta spec) (characters spec) ⟨characterId, sample⟩) ∧
          ∃ batch, batch ∈ bundle.signCampaign.batches ∧
            ∃ cell, cell ∈ batch.cells ∧
              cell.key = ⟨characterId, sample⟩ ∧
              ∃ typed : FactoredSmallQCompletedSign.Certificate,
                cell.payload.scaleTimesFourier.left = fourierWord ∧
                cell.payload.decode = some typed ∧
                FactoredSmallQRawCompletedSign.decodeStrictSign
                    cell.payload.signCode = some typed.sign ∧
                cell.payload.untiltTimesPeriodized.output.decode =
                  some typed.output ∧
                FactoredSmallQRawCompletedSign.RawCertificate.SourceGuards
                  (headers spec).parameters.b
                  (headers spec).parameters.eta
                  ((headers spec).parameters.t ⟨characterId, sample⟩) ∧
                typed.sign.Holds
                  (sourceCompletedValue
                    (FactoredSmallQRawCompletedSignCampaign.directFourier
                      (logLength := logLength) (oddParity spec)
                      (negativeFrequency spec) (w spec) (prefactors spec)
                      (delta spec) (characters spec)
                      ⟨characterId, sample⟩)
                    (headers spec).parameters.b
                    (headers spec).parameters.eta
                    ((headers spec).parameters.t ⟨characterId, sample⟩)
                    ((headers spec).timeTail
                      ⟨characterId, sample⟩)).re := by
  have hsound := Certificate.checker_sound hcheck
  rcases exists_source_aligned_modulus hsound.2 hinputs hspec with
    ⟨bundle, hbundle, haccepted, hbundleInputs⟩
  rcases haccepted with
    ⟨hsignCheck, hpostprocess, hlinks, hrawChecks⟩
  rcases hbundleInputs with
    ⟨hbases, hcharacters, hprefactors, hpostprocessTails, hroots, hgrid,
      hscale, htimeTail, huntilt, hreal⟩
  rcases linkCheck_sound hlinks with ⟨houtputs, htransformInputs⟩
  have hdecodes : ∀ requestedCharacter,
      requestedCharacter ∈ spec.full.roster →
      (bundle.rawTransforms requestedCharacter).decode =
        some (bundle.decodedTransform requestedCharacter) := by
    intro requestedCharacter hrequestedCharacter
    exact bundle.raw_decode_eq
      (hrawChecks requestedCharacter hrequestedCharacter)
  have hrawLinked :
      RawTransformsLinked spec.full bundle.naturalDisks bundle.rawTransforms
        bundle.decodedTransform :=
    ⟨hdecodes, htransformInputs⟩
  have hresult :=
    FactoredSmallQRawCompletedSignPayloadCampaign.requested_source_sample_has_raw_source_sign
      hsignCheck hpostprocess hbases hcharacters hprefactors
      hpostprocessTails houtputs hrawLinked hrawChecks hroots hgrid hscale
      htimeTail huntilt hreal hcharacter hsample
  exact ⟨bundle, hbundle, hresult⟩

end SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign
