/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign
import SparkInterval.Dirichlet.FactoredSmallQDFTCorrectness
import SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition

/-!
# Raw small-q DFT words to completed strict signs

This module is the narrow arithmetic bridge between two independently checked
certificate layers:

* a full power-of-two raw DFT trace, whose literal binary64 output words decode
  to disks enclosing the direct positive-sign DFT; and
* a retained source-sample campaign, whose scaling, time-tail, untilting, and
  final disk prove a strict sign.

The bridge checks exact equality of the two layers' Fourier disks.  It also
checks, in one human-readable proposition, that the full-transform and
retained-source domains have the same modulus and character roster, that the
full transform has length `2^logLength`, and that `sampleCount` fits inside
that full line.  The completed-sign campaign separately repeats the final
fit check in its own `sourceCheck`.

The application theorem deliberately retains every analytic premise: exact
Gaussian bases and character values, prefactors, postprocessing tails,
transcendental root containment, positive scale and untilt containment, the
time-periodization tail bound, and functional-equation reality.  It assigns no
mathematical meaning to a digest, MMR receipt, compiler, or physical run.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawDFT
open SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

namespace CompletedCampaign

abbrev SourceSampleSpec :=
  FactoredSmallQCompletedSignCampaign.SourceSampleSpec

abbrev SignCampaignCertificate :=
  FactoredSmallQCompletedSignCampaign.SignCampaignCertificate

end CompletedCampaign

/-! ## Source parameters retained at every completed sample -/

/-- Header-wide source parameters for the completed-value formula.  Keeping
these fields scalar prevents a certificate from silently changing the grid or
tilt parameter between characters or samples.  Time is derived as
`sample / a`, so an arbitrary producer-supplied `t` cannot be substituted. -/
structure SourceParameters where
  a : ℝ
  b : ℝ
  eta : ℝ

namespace SourceParameters

noncomputable def scale (parameters : SourceParameters)
    (_key : CellKey) : ℝ :=
  sourceScale parameters.b

noncomputable def t (parameters : SourceParameters)
    (key : CellKey) : ℝ :=
  (key.frequency : ℝ) / parameters.a

noncomputable def untilt (parameters : SourceParameters)
    (key : CellKey) : ℝ :=
  sourceUntilt parameters.eta (parameters.t key)

/-- Explicit guards against Lean's total division at zero. -/
def PositiveDenominators (parameters : SourceParameters) : Prop :=
  0 < parameters.a ∧ 0 < parameters.b

/-- Source grid equations over the exact retained range.  The value
`b = fullDFTLength / a` is kept explicit here; a later source-realization
layer may additionally specialize `a` to the paper's constant. -/
def GridValid (parameters : SourceParameters) (logLength : Nat) : Prop :=
  parameters.PositiveDenominators ∧
  -1 < parameters.eta ∧ parameters.eta < 1 ∧
  parameters.b = (lineLength logLength : ℝ) / parameters.a

/-- The exact sampling constant fixed by the production source.  This name
does not itself prove that a physical artifact used the constant. -/
noncomputable def bookerA : ℝ := 64 / 5

theorem bookerA_pos : 0 < bookerA := by
  norm_num [bookerA]

/-- Stronger source-grid predicate exposing the production sampling constant
while retaining every generic grid guard. -/
def BookerGridValid (parameters : SourceParameters)
    (logLength : Nat) : Prop :=
  parameters.a = bookerA ∧ parameters.GridValid logLength

end SourceParameters

/-- Functional-equation reality premise with the source formula expanded at
every checked sign-campaign cell. -/
def SourceCompletedValuesReal
    (certificate : CompletedCampaign.SignCampaignCertificate)
    (fourier : CellKey → ℂ) (parameters : SourceParameters)
    (timeTail : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      (sourceCompletedValue (fourier cell.key)
        parameters.b parameters.eta
        (parameters.t cell.key) (timeTail cell.key)).im = 0

/-! ## The finite equality boundary between the two campaigns -/

/-- The compact domain equation a human needs to audit.  In particular,
`source.sampleCount` is not identified with the guard-line length: it is only
required to fit inside it. -/
def SourceDFTAgreement (logLength : Nat) (full : Spec)
    (source : CompletedCampaign.SourceSampleSpec) : Prop :=
  full.q = source.q ∧
  full.roster = source.roster ∧
  full.transformLength = lineLength logLength ∧
  source.sampleCount ≤ lineLength logLength

instance (logLength : Nat) (full : Spec)
    (source : CompletedCampaign.SourceSampleSpec) :
    Decidable (SourceDFTAgreement logLength full source) := by
  unfold SourceDFTAgreement
  infer_instance

/-- Every retained completed-sign Fourier disk is literally the corresponding
decoded raw DFT output disk.  The equality is over the source-owned roster and
half-open retained range, not over certificate-selected keys. -/
def FourierDisksLinked {logLength : Nat}
    (source : CompletedCampaign.SourceSampleSpec)
    (fourierDisks : CellKey → ComplexDisk)
    (decodedTransforms : Nat → DecodedCertificate logLength) : Prop :=
  ∀ characterId, characterId ∈ source.roster →
    ∀ sample, sample < source.sampleCount →
      fourierDisks ⟨characterId, sample⟩ =
        (decodedTransforms characterId).claimedOutput.value
          (finIndex logLength sample)

/-- Finite replay of the domain equation and every retained Fourier-disk
equality. -/
def bridgeCheck {logLength : Nat} (full : Spec)
    (source : CompletedCampaign.SourceSampleSpec)
    (fourierDisks : CellKey → ComplexDisk)
    (decodedTransforms : Nat → DecodedCertificate logLength) : Bool :=
  decide (SourceDFTAgreement logLength full source) &&
    source.roster.all fun characterId ↦
      (List.range source.sampleCount).all fun sample ↦
        decide (fourierDisks ⟨characterId, sample⟩ =
          (decodedTransforms characterId).claimedOutput.value
            (finIndex logLength sample))

theorem bridgeCheck_sound {logLength : Nat} {full : Spec}
    {source : CompletedCampaign.SourceSampleSpec}
    {fourierDisks : CellKey → ComplexDisk}
    {decodedTransforms : Nat → DecodedCertificate logLength}
    (hcheck : bridgeCheck full source fourierDisks decodedTransforms = true) :
    SourceDFTAgreement logLength full source ∧
      FourierDisksLinked source fourierDisks decodedTransforms := by
  simp only [bridgeCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  refine ⟨hcheck.1, ?_⟩
  intro characterId hcharacter sample hsample
  have hcharacterCheck :=
    (List.all_eq_true.mp hcheck.2) characterId hcharacter
  have hsampleCheck :=
    (List.all_eq_true.mp hcharacterCheck) sample
      (List.mem_range.mpr hsample)
  simpa only [decide_eq_true_eq] using hsampleCheck

/-! ## Exact direct Fourier value named by the completed-sign layer -/

/-- The direct positive-sign DFT of the exact postprocessed source line at a
source key.  `finIndex` is harmless here because the application theorem
proves the requested sample is strictly below `2^logLength`. -/
noncomputable def directFourier {logLength : Nat}
    (oddParity negativeFrequency : CellKey → Bool)
    (w prefactors delta : CellKey → ℂ)
    (characters : CellKey → List ℂ) (key : CellKey) : ℂ :=
  positiveDFT
    (exactSource logLength key.characterId
      (exactCellValue oddParity negativeFrequency w prefactors delta
        characters))
    (finIndex logLength key.frequency)

/-! ## Requested source sample: literal word, enclosure, and strict sign -/

/-- End-to-end arithmetic theorem for one retained source sample.

The conclusion exposes the literal raw output word and its exact decoded disk,
then returns the actual completed-sign campaign cell and its sign of the exact
direct DFT completed value.  `sample < lineLength logLength` is returned as a
separate fact so the source-sample/full-line boundary remains visible to every
downstream consumer. -/
theorem requested_source_sample_has_direct_sign
    {logLength : Nat}
    {fullSpec : Spec}
    {sourceSpec : CompletedCampaign.SourceSampleSpec}
    {termCount : CellKey → Nat}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {postprocessCampaign : RawPostprocessCampaignCertificate}
    {naturalDisks fourierDisks : CellKey → ComplexDisk}
    {rawTransforms : Nat → RawCertificate logLength}
    {decodedTransforms : Nat → DecodedCertificate logLength}
    {bounds : Nat → Bounds}
    {signCampaign : CompletedCampaign.SignCampaignCertificate}
    {scale : CellKey → ℝ}
    {timeTail : CellKey → ℂ}
    {untilt : CellKey → ℝ}
    (hbridge : bridgeCheck fullSpec sourceSpec fourierDisks
      decodedTransforms = true)
    (hpostprocess :
      FactoredSmallQRawPostprocessCampaign.check fullSpec termCount oddParity
        negativeFrequency postprocessCampaign = true)
    (hbases : BaseDisksContain postprocessCampaign w)
    (hcharacters : CharacterDisksContain postprocessCampaign characters)
    (hprefactors : PrefactorDisksContain postprocessCampaign prefactors)
    (hpostprocessTails : TailPerturbationsBound postprocessCampaign delta)
    (houtputs : RawOutputsDecodeTo postprocessCampaign naturalDisks)
    (hrawLinked : RawTransformsLinked fullSpec naturalDisks rawTransforms
      decodedTransforms)
    (hrawChecks : ∀ characterId, characterId ∈ fullSpec.roster →
      (rawTransforms characterId).check (bounds characterId) = true)
    (hroots : ∀ characterId, characterId ∈ fullSpec.roster →
      TwiddlesContain (logLength := logLength)
        (decodedTransforms characterId).certificate.twiddleDisks
        positiveTwiddle)
    (hsignCheck :
      FactoredSmallQCompletedSignCampaign.sourceCheck sourceSpec
        (lineLength logLength) fourierDisks signCampaign = true)
    (hscale :
      FactoredSmallQCompletedSignCampaign.ScaleDisksContain signCampaign
        scale)
    (htimeTail :
      FactoredSmallQCompletedSignCampaign.TimeTailsBound signCampaign
        timeTail)
    (huntilt :
      FactoredSmallQCompletedSignCampaign.UntiltDisksContain signCampaign
        untilt)
    (hreal :
      FactoredSmallQCompletedSignCampaign.CompletedValuesReal signCampaign
        (directFourier (logLength := logLength) oddParity negativeFrequency w
          prefactors delta characters)
        scale timeTail untilt)
    {characterId sample : Nat}
    (hcharacter : characterId ∈ sourceSpec.roster)
    (hsample : sample < sourceSpec.sampleCount) :
    sample < lineLength logLength ∧
      ∃ rawDisk : ComplexDisk.Raw,
        (rawTransforms characterId).output[sample]? = some rawDisk ∧
        rawDisk.decode = some (fourierDisks ⟨characterId, sample⟩) ∧
        (fourierDisks ⟨characterId, sample⟩).ContainsComplex
          (directFourier (logLength := logLength) oddParity
            negativeFrequency w prefactors delta characters
            ⟨characterId, sample⟩) ∧
        ∃ batch, batch ∈ signCampaign.batches ∧
          ∃ cell, cell ∈ batch.cells ∧
            cell.key = ⟨characterId, sample⟩ ∧
            cell.payload.sign.Holds
              (completedValue
                (directFourier (logLength := logLength) oddParity
                  negativeFrequency w prefactors delta characters
                  ⟨characterId, sample⟩)
                (scale ⟨characterId, sample⟩)
                (timeTail ⟨characterId, sample⟩)
                (untilt ⟨characterId, sample⟩)).re := by
  rcases bridgeCheck_sound hbridge with ⟨hdomains, hfourierLink⟩
  have hsampleLine : sample < lineLength logLength :=
    Nat.lt_of_lt_of_le hsample hdomains.2.2.2
  have hcharacterFull : characterId ∈ fullSpec.roster := by
    rw [hdomains.2.1]
    exact hcharacter
  let frequency : Fin (lineLength logLength) := finIndex logLength sample
  have hfrequencyValue : frequency.val = sample := by
    exact Nat.mod_eq_of_lt hsampleLine
  have hraw := output_words_contain_postprocessed_radix2
    hpostprocess hbases hcharacters hprefactors hpostprocessTails houtputs
      hrawLinked hrawChecks hroots hcharacterFull frequency
  rcases hraw with ⟨rawDisk, hrawWord, hrawDecode, hradixContains⟩
  let source : ExactState logLength :=
    exactSource logLength characterId
      (exactCellValue oddParity negativeFrequency w prefactors delta
        characters)
  have hdirectContains :
      ((decodedTransforms characterId).claimedOutput.value frequency).ContainsComplex
        (positiveDFT source frequency) := by
    rw [← radix2CorrectFor source frequency]
    simpa [source] using hradixContains
  have hlink := hfourierLink characterId hcharacter sample hsample
  have hfourierContains :
      (fourierDisks ⟨characterId, sample⟩).ContainsComplex
        (directFourier (logLength := logLength) oddParity negativeFrequency w
          prefactors delta characters ⟨characterId, sample⟩) := by
    rw [hlink]
    simpa [directFourier, source, frequency] using hdirectContains
  have hsignSound :=
    FactoredSmallQCompletedSignCampaign.sourceCheck_sound hsignCheck
  rcases signCampaign.exists_cell_for_requested_key
      hsignSound.2.1 hcharacter hsample with
    ⟨batch, hbatch, cell, hcell, hkey⟩
  have hpayload := hsignSound.2.2 batch hbatch cell hcell
  change cell.payload.check (fourierDisks cell.key) = true at hpayload
  have hfourierCell :
      (fourierDisks cell.key).ContainsComplex
        (directFourier (logLength := logLength) oddParity negativeFrequency w
          prefactors delta characters cell.key) := by
    rw [hkey]
    exact hfourierContains
  have hsign := FactoredSmallQCompletedSign.Certificate.accepted_sign
    hpayload hfourierCell
      (hscale batch hbatch cell hcell)
      (htimeTail batch hbatch cell hcell)
      (huntilt batch hbatch cell hcell)
      (hreal batch hbatch cell hcell)
  rw [hkey] at hsign
  refine ⟨hsampleLine, rawDisk, ?_, ?_, hfourierContains,
    batch, hbatch, cell, hcell, hkey, hsign⟩
  · simpa [hfrequencyValue] using hrawWord
  · simpa [hlink] using hrawDecode

/-! ## Source-shaped end-to-end corollary -/

/-- The same raw-word-to-sign theorem with the analytic source factors
instantiated as `2*pi/b` and `exp(-pi*eta*t/4)`.

The header-wide grid guard checks `0 < a`, `0 < b`, `-1 < eta < 1`, and
`b = fullDFTLength/a`; time at a key is definitionally `sample/a`.  These
facts are returned at the requested key. Fourier-factor disk containments,
the complex-norm time-tail bound, untilt containment, root containment, and
functional-equation reality all remain explicit premises. -/
theorem requested_source_sample_has_source_sign
    {logLength : Nat}
    {fullSpec : Spec}
    {sourceSpec : CompletedCampaign.SourceSampleSpec}
    {termCount : CellKey → Nat}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {postprocessCampaign : RawPostprocessCampaignCertificate}
    {naturalDisks fourierDisks : CellKey → ComplexDisk}
    {rawTransforms : Nat → RawCertificate logLength}
    {decodedTransforms : Nat → DecodedCertificate logLength}
    {bounds : Nat → Bounds}
    {signCampaign : CompletedCampaign.SignCampaignCertificate}
    {parameters : SourceParameters}
    {timeTail : CellKey → ℂ}
    (hbridge : bridgeCheck fullSpec sourceSpec fourierDisks
      decodedTransforms = true)
    (hpostprocess :
      FactoredSmallQRawPostprocessCampaign.check fullSpec termCount oddParity
        negativeFrequency postprocessCampaign = true)
    (hbases : BaseDisksContain postprocessCampaign w)
    (hcharacters : CharacterDisksContain postprocessCampaign characters)
    (hprefactors : PrefactorDisksContain postprocessCampaign prefactors)
    (hpostprocessTails : TailPerturbationsBound postprocessCampaign delta)
    (houtputs : RawOutputsDecodeTo postprocessCampaign naturalDisks)
    (hrawLinked : RawTransformsLinked fullSpec naturalDisks rawTransforms
      decodedTransforms)
    (hrawChecks : ∀ characterId, characterId ∈ fullSpec.roster →
      (rawTransforms characterId).check (bounds characterId) = true)
    (hroots : ∀ characterId, characterId ∈ fullSpec.roster →
      TwiddlesContain (logLength := logLength)
        (decodedTransforms characterId).certificate.twiddleDisks
        positiveTwiddle)
    (hsignCheck :
      FactoredSmallQCompletedSignCampaign.sourceCheck sourceSpec
        (lineLength logLength) fourierDisks signCampaign = true)
    (hgrid : parameters.GridValid logLength)
    (hscale :
      FactoredSmallQCompletedSignCampaign.ScaleDisksContain signCampaign
        parameters.scale)
    (htimeTail :
      FactoredSmallQCompletedSignCampaign.TimeTailsBound signCampaign
        timeTail)
    (huntilt :
      FactoredSmallQCompletedSignCampaign.UntiltDisksContain signCampaign
        parameters.untilt)
    (hreal : SourceCompletedValuesReal signCampaign
      (directFourier (logLength := logLength) oddParity negativeFrequency w
        prefactors delta characters)
      parameters timeTail)
    {characterId sample : Nat}
    (hcharacter : characterId ∈ sourceSpec.roster)
    (hsample : sample < sourceSpec.sampleCount) :
    0 < parameters.a ∧
      0 < parameters.b ∧
      -1 < parameters.eta ∧ parameters.eta < 1 ∧
      parameters.b = (lineLength logLength : ℝ) / parameters.a ∧
      sample < lineLength logLength ∧
      ∃ rawDisk : ComplexDisk.Raw,
        (rawTransforms characterId).output[sample]? = some rawDisk ∧
        rawDisk.decode = some (fourierDisks ⟨characterId, sample⟩) ∧
        (fourierDisks ⟨characterId, sample⟩).ContainsComplex
          (directFourier (logLength := logLength) oddParity
            negativeFrequency w prefactors delta characters
            ⟨characterId, sample⟩) ∧
        ∃ batch, batch ∈ signCampaign.batches ∧
          ∃ cell, cell ∈ batch.cells ∧
            cell.key = ⟨characterId, sample⟩ ∧
            cell.payload.sign.Holds
              (sourceCompletedValue
                (directFourier (logLength := logLength) oddParity
                  negativeFrequency w prefactors delta characters
                  ⟨characterId, sample⟩)
                parameters.b parameters.eta
                (parameters.t ⟨characterId, sample⟩)
                (timeTail ⟨characterId, sample⟩)).re := by
  have hrealGeneric :
      FactoredSmallQCompletedSignCampaign.CompletedValuesReal signCampaign
        (directFourier (logLength := logLength) oddParity negativeFrequency w
          prefactors delta characters)
        parameters.scale timeTail parameters.untilt := by
    intro batch hbatch cell hcell
    simpa [sourceCompletedValue, SourceParameters.scale,
      SourceParameters.untilt] using hreal batch hbatch cell hcell
  have hgeneric := requested_source_sample_has_direct_sign
    hbridge hpostprocess hbases hcharacters hprefactors hpostprocessTails
      houtputs hrawLinked hrawChecks hroots hsignCheck hscale htimeTail
      huntilt hrealGeneric hcharacter hsample
  refine ⟨hgrid.1.1, hgrid.1.2, hgrid.2.1, hgrid.2.2.1,
    hgrid.2.2.2, ?_⟩
  simpa [sourceCompletedValue, SourceParameters.scale,
    SourceParameters.untilt] using hgeneric

end SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign
