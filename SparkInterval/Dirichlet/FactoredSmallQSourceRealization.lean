/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQGRHBridge
import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign

/-!
# Source realization boundary for the factored small-q verifier

The finite checker intentionally treats a character identifier as an opaque
natural number and its Gaussian-sum values as an application-supplied list.
This module states the missing semantic boundary without pretending that the
identifier is already a formal Conrey number.

`PrimitiveRosterRealization` says that one source-owned roster is in exact
bijection with the primitive Dirichlet characters of a modulus.
`CharacterInputsRealize` fixes every Gaussian row to the values of that same
character, starting at `n = 1`, and fixes its parity.  Finally,
`SourceEvaluatorRealizes` is one human-readable complex equality between the
factored/DFT source expression and a named real completed-L evaluator at every
retained grid point.

These are propositions to prove from number theory and the source formulas,
not new trust declarations.  No Conrey enumeration, analytic identity, byte
parser, or physical execution is asserted here.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.Dirichlet.FactoredSmallQSourceRealization

open DirichletCharacter
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign

abbrev ModulusSpec :=
  FactoredSmallQRawCompletedSignPayloadModulusCampaign.ModulusSpec

abbrev SourceParameters :=
  FactoredSmallQRawCompletedSignCampaign.SourceParameters

/-! ## Exact primitive-character roster -/

/-- An opaque identifier roster realizes exactly the primitive Dirichlet
characters of one modulus.  The character map has no source meaning outside
the listed identifiers. -/
structure PrimitiveRosterRealization (q : Nat) [NeZero q]
    (roster : List Nat) where
  nodup : roster.Nodup
  characterOf : Nat → DirichletCharacter ℂ q
  primitive_of_mem : ∀ id, id ∈ roster → (characterOf id).IsPrimitive
  complete_unique : ∀ χ : DirichletCharacter ℂ q, χ.IsPrimitive →
    ∃! id, id ∈ roster ∧ characterOf id = χ

namespace PrimitiveRosterRealization

variable {q : Nat} [NeZero q] {roster : List Nat}

theorem character_primitive
    (realization : PrimitiveRosterRealization q roster)
    {id : Nat} (hid : id ∈ roster) :
    (realization.characterOf id).IsPrimitive :=
  realization.primitive_of_mem id hid

theorem existsUnique_id
    (realization : PrimitiveRosterRealization q roster)
    {χ : DirichletCharacter ℂ q} (hχ : χ.IsPrimitive) :
    ∃! id, id ∈ roster ∧ realization.characterOf id = χ :=
  realization.complete_unique χ hχ

/-- If the modulus has a primitive character, exact roster realization cannot
be satisfied by an empty list. -/
theorem roster_nonempty_of_primitive
    (realization : PrimitiveRosterRealization q roster)
    (χ : DirichletCharacter ℂ q) (hχ : χ.IsPrimitive) :
    roster ≠ [] := by
  rcases realization.complete_unique χ hχ with ⟨id, hid, _⟩
  intro hnil
  have hidmem : id ∈ roster := hid.1
  simp [hnil] at hidmem

end PrimitiveRosterRealization

/-- Tie one arithmetic modulus specification to its actual modulus and one
exact primitive-character roster.  Equality of the full and retained rosters
is explicit even though an accepted finite campaign also checks it. -/
structure ModulusRosterRealization (q : Nat) [NeZero q]
    (spec : ModulusSpec) where
  modulus_eq : spec.full.q = q
  roster_eq : spec.full.roster = spec.source.roster
  primitiveRoster : PrimitiveRosterRealization q spec.source.roster

namespace ModulusRosterRealization

variable {q : Nat} [NeZero q] {spec : ModulusSpec}

theorem primitive_of_source_mem
    (realization : ModulusRosterRealization q spec)
    {id : Nat} (hid : id ∈ spec.source.roster) :
    (realization.primitiveRoster.characterOf id).IsPrimitive :=
  realization.primitiveRoster.primitive_of_mem id hid

theorem primitive_of_full_mem
    (realization : ModulusRosterRealization q spec)
    {id : Nat} (hid : id ∈ spec.full.roster) :
    (realization.primitiveRoster.characterOf id).IsPrimitive := by
  apply realization.primitive_of_source_mem
  rwa [← realization.roster_eq]

end ModulusRosterRealization

/-! ## Exact character rows and parity -/

/-- Character values consumed by `exactFiniteSum`; list position zero is the
source row `n = 1`. -/
def characterRows {q : Nat} [NeZero q]
    (χ : DirichletCharacter ℂ q) (termCount : Nat) : List ℂ :=
  (List.range termCount).map fun index =>
    χ ((index + 1 : Nat) : ZMod q)

/-- Every application-supplied Gaussian row uses the fixed character selected
by its source identifier, with no frequency-dependent character substitution.
The Boolean odd/even branch is also identified with the mathematical parity
of that same character. -/
def CharacterInputsRealize {q : Nat} [NeZero q]
    (spec : ModulusSpec) (realization : ModulusRosterRealization q spec)
    (termCount : CellKey → Nat) (oddParity : CellKey → Bool)
    (characters : CellKey → List ℂ) : Prop :=
  ∀ key, key.characterId ∈ spec.full.roster →
    key.frequency < spec.full.transformLength →
      characters key = characterRows
        (realization.primitiveRoster.characterOf key.characterId)
        (termCount key) ∧
      (if oddParity key then
        (realization.primitiveRoster.characterOf key.characterId).Odd
      else
        (realization.primitiveRoster.characterOf key.characterId).Even)

theorem CharacterInputsRealize.rows_eq {q : Nat} [NeZero q]
    {spec : ModulusSpec} {realization : ModulusRosterRealization q spec}
    {termCount : CellKey → Nat} {oddParity : CellKey → Bool}
    {characters : CellKey → List ℂ}
    (hrealizes : CharacterInputsRealize spec realization termCount oddParity
      characters)
    {key : CellKey} (hcharacter : key.characterId ∈ spec.full.roster)
    (hfrequency : key.frequency < spec.full.transformLength) :
    characters key = characterRows
      (realization.primitiveRoster.characterOf key.characterId)
      (termCount key) :=
  (hrealizes key hcharacter hfrequency).1

theorem CharacterInputsRealize.parity {q : Nat} [NeZero q]
    {spec : ModulusSpec} {realization : ModulusRosterRealization q spec}
    {termCount : CellKey → Nat} {oddParity : CellKey → Bool}
    {characters : CellKey → List ℂ}
    (hrealizes : CharacterInputsRealize spec realization termCount oddParity
      characters)
    {key : CellKey} (hcharacter : key.characterId ∈ spec.full.roster)
    (hfrequency : key.frequency < spec.full.transformLength) :
    if oddParity key then
      (realization.primitiveRoster.characterOf key.characterId).Odd
    else
      (realization.primitiveRoster.characterOf key.characterId).Even :=
  (hrealizes key hcharacter hfrequency).2

/-! ## One source-shaped evaluator equation -/

/-- Exact semantic target for one retained character line.  The equality is
complex-valued, so it simultaneously states functional-equation reality and
the real evaluator value.  The production sampling rate is part of the
proposition rather than an informal convention. -/
def SourceEvaluatorRealizes {logLength q : Nat} [NeZero q]
    (spec : ModulusSpec) (realization : ModulusRosterRealization q spec)
    (oddParity negativeFrequency : CellKey → Bool)
    (w prefactors delta : CellKey → ℂ)
    (characters : CellKey → List ℂ)
    (parameters : SourceParameters) (timeTail : CellKey → ℂ)
    (characterId : Nat) (f : ℝ → ℝ) : Prop :=
  characterId ∈ spec.source.roster ∧
  (realization.primitiveRoster.characterOf characterId).IsPrimitive ∧
  parameters.a =
    FactoredSmallQRawCompletedSignCampaign.SourceParameters.bookerA ∧
  ∀ sample, sample < spec.source.sampleCount →
    sourceCompletedValue
      (FactoredSmallQRawCompletedSignCampaign.directFourier
        (logLength := logLength) oddParity negativeFrequency w prefactors
        delta characters ⟨characterId, sample⟩)
      parameters.b parameters.eta
      (parameters.t ⟨characterId, sample⟩)
      (timeTail ⟨characterId, sample⟩) =
        (f (parameters.t ⟨characterId, sample⟩) : ℂ)

namespace SourceEvaluatorRealizes

variable {logLength q : Nat} [NeZero q]
variable {spec : ModulusSpec}
variable {realization : ModulusRosterRealization q spec}
variable {oddParity negativeFrequency : CellKey → Bool}
variable {w prefactors delta : CellKey → ℂ}
variable {characters : CellKey → List ℂ}
variable {parameters : SourceParameters} {timeTail : CellKey → ℂ}
variable {characterId : Nat} {f : ℝ → ℝ}

theorem character_mem
    (hrealizes : SourceEvaluatorRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail characterId f) :
    characterId ∈ spec.source.roster :=
  hrealizes.1

theorem character_primitive
    (hrealizes : SourceEvaluatorRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail characterId f) :
    (realization.primitiveRoster.characterOf characterId).IsPrimitive :=
  hrealizes.2.1

theorem booker_grid
    (hrealizes : SourceEvaluatorRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail characterId f) :
    parameters.a =
      FactoredSmallQRawCompletedSignCampaign.SourceParameters.bookerA :=
  hrealizes.2.2.1

theorem equation
    (hrealizes : SourceEvaluatorRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail characterId f)
    {sample : Nat} (hsample : sample < spec.source.sampleCount) :
    sourceCompletedValue
      (FactoredSmallQRawCompletedSignCampaign.directFourier
        (logLength := logLength) oddParity negativeFrequency w prefactors
        delta characters ⟨characterId, sample⟩)
      parameters.b parameters.eta
      (parameters.t ⟨characterId, sample⟩)
      (timeTail ⟨characterId, sample⟩) =
        (f (parameters.t ⟨characterId, sample⟩) : ℂ) :=
  hrealizes.2.2.2 sample hsample

/-- The single complex equation implies the explicit reality premise used by
the completed-sign checker. -/
theorem value_im_eq_zero
    (hrealizes : SourceEvaluatorRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail characterId f)
    {sample : Nat} (hsample : sample < spec.source.sampleCount) :
    (sourceCompletedValue
      (FactoredSmallQRawCompletedSignCampaign.directFourier
        (logLength := logLength) oddParity negativeFrequency w prefactors
        delta characters ⟨characterId, sample⟩)
      parameters.b parameters.eta
      (parameters.t ⟨characterId, sample⟩)
      (timeTail ⟨characterId, sample⟩)).im = 0 := by
  rw [hrealizes.equation hsample]
  simp

/-- The same equation gives the exact real endpoint identity expected by the
zero-bracket semantic bridge. -/
theorem value_re_eq_evaluator
    (hrealizes : SourceEvaluatorRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail characterId f)
    {sample : Nat} (hsample : sample < spec.source.sampleCount) :
    (sourceCompletedValue
      (FactoredSmallQRawCompletedSignCampaign.directFourier
        (logLength := logLength) oddParity negativeFrequency w prefactors
        delta characters ⟨characterId, sample⟩)
      parameters.b parameters.eta
      (parameters.t ⟨characterId, sample⟩)
      (timeTail ⟨characterId, sample⟩)).re =
        f (parameters.t ⟨characterId, sample⟩) := by
  rw [hrealizes.equation hsample]
  simp

end SourceEvaluatorRealizes

/-! ## Campaign-wide projection of the single source equation -/

/-- One source equation for every source-owned character identifier.  The
evaluator family is indexed only by the fixed roster identifier; it cannot
vary with the sample. -/
def SourceEvaluatorFamilyRealizes {logLength q : Nat} [NeZero q]
    (spec : ModulusSpec) (realization : ModulusRosterRealization q spec)
    (oddParity negativeFrequency : CellKey → Bool)
    (w prefactors delta : CellKey → ℂ)
    (characters : CellKey → List ℂ)
    (parameters : SourceParameters) (timeTail : CellKey → ℂ)
    (evaluators : Nat → ℝ → ℝ) : Prop :=
  ∀ characterId, characterId ∈ spec.source.roster →
    SourceEvaluatorRealizes (logLength := logLength) spec realization
      oddParity negativeFrequency w prefactors delta characters parameters
      timeTail characterId (evaluators characterId)

/-- Campaign acceptance supplies the source-domain membership of every cell;
the family of complex evaluator equations then discharges exactly the
functional-equation reality premise consumed by the raw sign theorem. -/
theorem SourceEvaluatorFamilyRealizes.completedValuesReal
    {logLength q : Nat} [NeZero q]
    {spec : ModulusSpec}
    {realization : ModulusRosterRealization q spec}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {parameters : SourceParameters} {timeTail : CellKey → ℂ}
    {evaluators : Nat → ℝ → ℝ}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign :
      FactoredSmallQRawCompletedSignPayloadCampaign.RawSignCampaignCertificate}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check spec.full spec.source
        rawTransforms campaign = true)
    (hrealizes : SourceEvaluatorFamilyRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail evaluators) :
    FactoredSmallQRawCompletedSignPayloadCampaign.SourceCompletedValuesReal
      (logLength := logLength) campaign oddParity negativeFrequency w
      prefactors delta characters parameters timeTail := by
  intro batch hbatch cell hcell
  have hdomain :=
    FactoredSmallQRawZeroBracketCampaign.cell_key_in_source_domain
      hcheck hbatch hcell
  exact (hrealizes cell.key.characterId hdomain.1).value_im_eq_zero hdomain.2

/-- The complete source-owned interpretation supplied to the finite
arithmetic layer: every application character row and parity branch realizes
the roster character, and the resulting source expression realizes one fixed
real evaluator for that roster identifier.  Keeping the conjunction named
prevents the numeric-character and evaluator contracts from drifting apart at
the final composition site. -/
def CharacterEvaluatorInputsRealize {logLength q : Nat} [NeZero q]
    (spec : ModulusSpec) (realization : ModulusRosterRealization q spec)
    (termCount : CellKey → Nat)
    (oddParity negativeFrequency : CellKey → Bool)
    (w prefactors delta : CellKey → ℂ)
    (characters : CellKey → List ℂ)
    (parameters : SourceParameters) (timeTail : CellKey → ℂ)
    (evaluators : Nat → ℝ → ℝ) : Prop :=
  CharacterInputsRealize spec realization termCount oddParity characters ∧
    SourceEvaluatorFamilyRealizes (logLength := logLength) spec realization
      oddParity negativeFrequency w prefactors delta characters parameters
      timeTail evaluators

/-! ## Checked raw cell to the named evaluator -/

/-- Repackage the source-wide arithmetic containments and the single complex
source equation as exactly the `SourceRealizes` proposition consumed by the
zero-bracket bridge.

The direct-Fourier containment remains an explicit argument because it is the
conclusion of the preceding raw postprocess/DFT proof.  The other three
containments are recovered from the literal raw sign cell and its
deterministic typed decode.  The equality `parameters.a = (a : ℝ)` prevents
the rational bracket time from being silently attached to a different source
grid. -/
theorem SourceEvaluatorFamilyRealizes.decodedCellAt_sourceRealizes
    {logLength q : Nat} [NeZero q]
    {spec : ModulusSpec}
    {realization : ModulusRosterRealization q spec}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {parameters : SourceParameters} {timeTail : CellKey → ℂ}
    {evaluators : Nat → ℝ → ℝ}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign :
      FactoredSmallQRawCompletedSignPayloadCampaign.RawSignCampaignCertificate}
    {a : ℚ} {key : CellKey}
    {typed : FactoredSmallQCompletedSign.Certificate}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check spec.full spec.source
        rawTransforms campaign = true)
    (hat :
      FactoredSmallQRawZeroBracketCampaign.DecodedCellAt campaign key typed)
    (hgrid : parameters.GridValid logLength)
    (ha : parameters.a = (a : ℝ))
    (hfourier :
      (FactoredSmallQRawZeroBracketCampaign.decodedOutputDisk rawTransforms
        key).ContainsComplex
        (FactoredSmallQRawCompletedSignCampaign.directFourier
          (logLength := logLength) oddParity negativeFrequency w prefactors
          delta characters key))
    (hscale :
      FactoredSmallQRawCompletedSignPayloadCampaign.ScaleDisksContain campaign
        parameters)
    (htimeTail :
      FactoredSmallQRawCompletedSignPayloadCampaign.TimeTailsBound campaign
        timeTail)
    (huntilt :
      FactoredSmallQRawCompletedSignPayloadCampaign.UntiltDisksContain campaign
        parameters)
    (hrealizes : SourceEvaluatorFamilyRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail evaluators) :
    (FactoredSmallQRawZeroBracketCampaign.mkEndpoint a key typed).SourceRealizes
      (FactoredSmallQRawZeroBracketCampaign.decodedOutputDisk rawTransforms)
      (evaluators key.characterId)
      (FactoredSmallQRawCompletedSignCampaign.directFourier
        (logLength := logLength) oddParity negativeFrequency w prefactors
        delta characters key)
      (timeTail key) parameters.b parameters.eta := by
  have hdomain := hat.key_in_source_domain hcheck
  have hsource := hrealizes key.characterId hdomain.1
  have htime :
      (((FactoredSmallQRawZeroBracketCampaign.mkEndpoint a key typed).time : ℚ) :
          ℝ) = parameters.t key := by
    simpa [FactoredSmallQRawZeroBracketCampaign.mkEndpoint] using
      FactoredSmallQRawZeroBracketCampaign.sourceTime_cast_eq_parameters_t
        a parameters key ha
  rcases hat with ⟨batch, hbatch, cell, hcell, hkey, hdecode⟩
  rcases hscale batch hbatch cell hcell with
    ⟨scaleDisk, hscaleDecode, hscaleContains⟩
  rcases htimeTail batch hbatch cell hcell with
    ⟨tailBound, htailDecode, htailBound⟩
  rcases huntilt batch hbatch cell hcell with
    ⟨untiltDisk, huntiltDecode, huntiltContains⟩
  have hscaleMul :=
    FactoredSmallQRawCompletedSign.RawCertificate.scaleTimesFourier_decode_eq
      hdecode
  have htypedScaleDecode :=
    (FactoredSmallQRawCompletedSign.rawMul_disk_decodes hscaleMul).2.1
  rw [hscaleDecode] at htypedScaleDecode
  have hscaleEq :
      scaleDisk = typed.scaleTimesFourier.right :=
    Option.some.inj htypedScaleDecode
  have htailInflation :=
    FactoredSmallQRawCompletedSign.RawCertificate.timeTailInflation_decode_eq
      hdecode
  have htypedTailDecode :=
    FactoredSmallQRawPostprocess.RawTailInflationCertificate.tailBound_decode_eq
      htailInflation
  rw [htailDecode] at htypedTailDecode
  have htailEq :
      tailBound = typed.timeTailInflation.tailBound :=
    Option.some.inj htypedTailDecode
  have huntiltMul :=
    FactoredSmallQRawCompletedSign.RawCertificate.untiltTimesPeriodized_decode_eq
      hdecode
  have htypedUntiltDecode :=
    (FactoredSmallQRawCompletedSign.rawMul_disk_decodes huntiltMul).2.1
  rw [huntiltDecode] at htypedUntiltDecode
  have huntiltEq :
      untiltDisk = typed.untiltTimesPeriodized.right :=
    Option.some.inj htypedUntiltDecode
  have hscaleTyped :
      typed.scaleTimesFourier.right.ContainsComplex
        (sourceScale parameters.b : ℂ) := by
    rw [← hscaleEq]
    exact hscaleContains
  have htailTyped :
      ‖timeTail key‖ ≤ (typed.timeTailInflation.tailBound : ℝ) := by
    rw [← htailEq, ← hkey]
    exact htailBound
  have huntiltTyped :
      typed.untiltTimesPeriodized.right.ContainsComplex
        (sourceUntilt parameters.eta
          ((FactoredSmallQRawZeroBracketCampaign.mkEndpoint a key typed).time :
            ℝ) : ℂ) := by
    rw [← huntiltEq, htime, ← hkey]
    exact huntiltContains
  have him := hsource.value_im_eq_zero hdomain.2
  have hre := hsource.value_re_eq_evaluator hdomain.2
  refine ⟨hgrid.1.2, hgrid.2.1, hgrid.2.2.1, hfourier,
    hscaleTyped, htailTyped, huntiltTyped, ?_, ?_⟩
  · simpa [sourceCompletedValue, htime] using him
  · simpa [sourceCompletedValue, htime] using hre.symm

/-- The preceding realization theorem and the finite raw endpoint check
compose without any additional analytic premise. -/
theorem SourceEvaluatorFamilyRealizes.decodedCellAt_evaluatorLink
    {logLength q : Nat} [NeZero q]
    {spec : ModulusSpec}
    {realization : ModulusRosterRealization q spec}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {parameters : SourceParameters} {timeTail : CellKey → ℂ}
    {evaluators : Nat → ℝ → ℝ}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign :
      FactoredSmallQRawCompletedSignPayloadCampaign.RawSignCampaignCertificate}
    {a : ℚ} {key : CellKey}
    {typed : FactoredSmallQCompletedSign.Certificate}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check spec.full spec.source
        rawTransforms campaign = true)
    (hat :
      FactoredSmallQRawZeroBracketCampaign.DecodedCellAt campaign key typed)
    (hgrid : parameters.GridValid logLength)
    (ha : parameters.a = (a : ℝ))
    (hfourier :
      (FactoredSmallQRawZeroBracketCampaign.decodedOutputDisk rawTransforms
        key).ContainsComplex
        (FactoredSmallQRawCompletedSignCampaign.directFourier
          (logLength := logLength) oddParity negativeFrequency w prefactors
          delta characters key))
    (hscale :
      FactoredSmallQRawCompletedSignPayloadCampaign.ScaleDisksContain campaign
        parameters)
    (htimeTail :
      FactoredSmallQRawCompletedSignPayloadCampaign.TimeTailsBound campaign
        timeTail)
    (huntilt :
      FactoredSmallQRawCompletedSignPayloadCampaign.UntiltDisksContain campaign
        parameters)
    (hrealizes : SourceEvaluatorFamilyRealizes (logLength := logLength) spec
      realization oddParity negativeFrequency w prefactors delta characters
      parameters timeTail evaluators) :
    (FactoredSmallQRawZeroBracketCampaign.mkEndpoint a key typed).EvaluatorLink
      (evaluators key.characterId) := by
  apply
    FactoredSmallQRawZeroBracketCampaign.decodedCellAt_evaluatorLink_of_sourceRealizes
      hcheck hat
  exact hrealizes.decodedCellAt_sourceRealizes hcheck hat hgrid ha hfourier
    hscale htimeTail huntilt

/-- Full character-aware endpoint handoff.  Besides the evaluator link, the
conclusion exposes the exact mathematical character row and parity used by
the finite Gaussian sum at this same source-owned cell.  This is the clean
join between opaque source identifiers, checked arithmetic, and the named
real evaluator; it still assumes the source formulas and their analytic
containments through the explicitly named realization predicates. -/
theorem CharacterEvaluatorInputsRealize.decodedCellAt_character_and_evaluator
    {logLength q : Nat} [NeZero q]
    {spec : ModulusSpec}
    {realization : ModulusRosterRealization q spec}
    {termCount : CellKey → Nat}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {parameters : SourceParameters} {timeTail : CellKey → ℂ}
    {evaluators : Nat → ℝ → ℝ}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign :
      FactoredSmallQRawCompletedSignPayloadCampaign.RawSignCampaignCertificate}
    {a : ℚ} {key : CellKey}
    {typed : FactoredSmallQCompletedSign.Certificate}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check spec.full spec.source
        rawTransforms campaign = true)
    (hat :
      FactoredSmallQRawZeroBracketCampaign.DecodedCellAt campaign key typed)
    (hgrid : parameters.GridValid logLength)
    (ha : parameters.a = (a : ℝ))
    (hfourier :
      (FactoredSmallQRawZeroBracketCampaign.decodedOutputDisk rawTransforms
        key).ContainsComplex
        (FactoredSmallQRawCompletedSignCampaign.directFourier
          (logLength := logLength) oddParity negativeFrequency w prefactors
          delta characters key))
    (hscale :
      FactoredSmallQRawCompletedSignPayloadCampaign.ScaleDisksContain campaign
        parameters)
    (htimeTail :
      FactoredSmallQRawCompletedSignPayloadCampaign.TimeTailsBound campaign
        timeTail)
    (huntilt :
      FactoredSmallQRawCompletedSignPayloadCampaign.UntiltDisksContain campaign
        parameters)
    (hrealizes : CharacterEvaluatorInputsRealize (logLength := logLength)
      spec realization termCount oddParity negativeFrequency w prefactors
      delta characters parameters timeTail evaluators) :
    characters key = characterRows
        (realization.primitiveRoster.characterOf key.characterId)
        (termCount key) ∧
      (if oddParity key then
        (realization.primitiveRoster.characterOf key.characterId).Odd
      else
        (realization.primitiveRoster.characterOf key.characterId).Even) ∧
      (FactoredSmallQRawZeroBracketCampaign.mkEndpoint a key typed).EvaluatorLink
        (evaluators key.characterId) := by
  have hdomain := hat.key_in_source_domain hcheck
  have hagreement :=
    (FactoredSmallQRawCompletedSignPayloadCampaign.checker_sound hcheck).1
  have hcharacterFull : key.characterId ∈ spec.full.roster := by
    rw [realization.roster_eq]
    exact hdomain.1
  have hfrequencyFull : key.frequency < spec.full.transformLength := by
    rw [hagreement.2.2.1]
    exact lt_of_lt_of_le hdomain.2 hagreement.2.2.2
  refine ⟨hrealizes.1.rows_eq hcharacterFull hfrequencyFull,
    hrealizes.1.parity hcharacterFull hfrequencyFull, ?_⟩
  exact hrealizes.2.decodedCellAt_evaluatorLink hcheck hat hgrid ha hfourier
    hscale htimeTail huntilt

/-- Requested-sample capstone for the small-`q` arithmetic bridge.

All finite postprocess and raw DFT hypotheses are fed to the established
raw-word theorem.  `CharacterEvaluatorInputsRealize` supplies both the exact
Dirichlet-character row/parity and the single source/evaluator equation.  The
result retains the literal output word and its direct-DFT enclosure, while the
same deterministically decoded sign cell carries an `EvaluatorLink` at the
exact rational Booker time `sample / (64/5)`.

This is still conditional on the named analytic disk/tail/root/source
containments.  It adds no execution or source-enumeration assumption. -/
theorem requested_source_sample_has_character_and_evaluator
    {logLength q : Nat} [NeZero q]
    {spec : ModulusSpec}
    {realization : ModulusRosterRealization q spec}
    {termCount : CellKey → Nat}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {postprocessCampaign :
      FactoredSmallQRawPostprocessCampaign.RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → SparkInterval.Certified.ComplexDisk}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {decodedTransforms : Nat →
      FactoredSmallQRawDFT.DecodedCertificate logLength}
    {bounds : Nat → FactoredSmallQRawDFT.Bounds}
    {signCampaign :
      FactoredSmallQRawCompletedSignPayloadCampaign.RawSignCampaignCertificate}
    {parameters : SourceParameters} {timeTail : CellKey → ℂ}
    {evaluators : Nat → ℝ → ℝ}
    (hsignCheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check spec.full spec.source
        rawTransforms signCampaign = true)
    (hpostprocess :
      FactoredSmallQRawPostprocessCampaign.check spec.full termCount oddParity
        negativeFrequency postprocessCampaign = true)
    (hbases :
      FactoredSmallQRawPostprocessCampaign.BaseDisksContain postprocessCampaign
        w)
    (hcharacters :
      FactoredSmallQRawPostprocessCampaign.CharacterDisksContain
        postprocessCampaign characters)
    (hprefactors :
      FactoredSmallQRawPostprocessCampaign.PrefactorDisksContain
        postprocessCampaign prefactors)
    (hpostprocessTails :
      FactoredSmallQRawPostprocessCampaign.TailPerturbationsBound
        postprocessCampaign delta)
    (houtputs :
      FactoredSmallQDFTComposition.RawOutputsDecodeTo postprocessCampaign
        naturalDisks)
    (hrawLinked :
      FactoredSmallQRawDFTComposition.RawTransformsLinked spec.full naturalDisks
        rawTransforms decodedTransforms)
    (hrawChecks : ∀ characterId, characterId ∈ spec.full.roster →
      (rawTransforms characterId).check (bounds characterId) = true)
    (hroots : ∀ characterId, characterId ∈ spec.full.roster →
      FactoredSmallQDFT.TwiddlesContain (logLength := logLength)
        (decodedTransforms characterId).certificate.twiddleDisks
        FactoredSmallQDFT.positiveTwiddle)
    (hgrid : parameters.GridValid logLength)
    (hscale :
      FactoredSmallQRawCompletedSignPayloadCampaign.ScaleDisksContain
        signCampaign parameters)
    (htimeTail :
      FactoredSmallQRawCompletedSignPayloadCampaign.TimeTailsBound signCampaign
        timeTail)
    (huntilt :
      FactoredSmallQRawCompletedSignPayloadCampaign.UntiltDisksContain
        signCampaign parameters)
    (hrealizes : CharacterEvaluatorInputsRealize (logLength := logLength)
      spec realization termCount oddParity negativeFrequency w prefactors
      delta characters parameters timeTail evaluators)
    {characterId sample : Nat}
    (hcharacter : characterId ∈ spec.source.roster)
    (hsample : sample < spec.source.sampleCount) :
    0 < parameters.a ∧
      0 < parameters.b ∧
      -1 < parameters.eta ∧ parameters.eta < 1 ∧
      parameters.b =
        (FactoredSmallQRawDFT.lineLength logLength : ℝ) / parameters.a ∧
      sample < FactoredSmallQRawDFT.lineLength logLength ∧
      ∃ fourierWord : SparkInterval.Certified.ComplexDisk.Raw,
        (rawTransforms characterId).output[sample]? = some fourierWord ∧
        ∃ fourierDisk : SparkInterval.Certified.ComplexDisk,
          fourierWord.decode = some fourierDisk ∧
          fourierDisk.ContainsComplex
            (FactoredSmallQRawCompletedSignCampaign.directFourier
              (logLength := logLength) oddParity negativeFrequency w
              prefactors delta characters ⟨characterId, sample⟩) ∧
          ∃ typed : FactoredSmallQCompletedSign.Certificate,
            FactoredSmallQRawZeroBracketCampaign.DecodedCellAt signCampaign
              ⟨characterId, sample⟩ typed ∧
            characters ⟨characterId, sample⟩ = characterRows
              (realization.primitiveRoster.characterOf characterId)
              (termCount ⟨characterId, sample⟩) ∧
            (if oddParity ⟨characterId, sample⟩ then
              (realization.primitiveRoster.characterOf characterId).Odd
            else
              (realization.primitiveRoster.characterOf characterId).Even) ∧
            (FactoredSmallQRawZeroBracketCampaign.mkEndpoint
              ((64 : ℚ) / 5) ⟨characterId, sample⟩ typed).EvaluatorLink
                (evaluators characterId) := by
  have hreal := hrealizes.2.completedValuesReal hsignCheck
  rcases
      FactoredSmallQRawCompletedSignPayloadCampaign.requested_source_sample_has_raw_source_sign
        hsignCheck hpostprocess hbases hcharacters hprefactors
        hpostprocessTails houtputs hrawLinked hrawChecks hroots hgrid hscale
        htimeTail huntilt hreal hcharacter hsample with
    ⟨haPos, hbPos, hetaLower, hetaUpper, hbEq, hsampleLine,
      fourierWord, hword, fourierDisk, hdecode, hfourier,
      batch, hbatch, cell, hcell, hkey, typed, _hattached, htypedDecode,
      _hsignDecode, _houtputDecode, _hguards, _hsign⟩
  have hat :
      FactoredSmallQRawZeroBracketCampaign.DecodedCellAt signCampaign
        ⟨characterId, sample⟩ typed :=
    ⟨batch, hbatch, cell, hcell, hkey, htypedDecode⟩
  have hcanonicalDisk :
      FactoredSmallQRawZeroBracketCampaign.decodedOutputDisk rawTransforms
          ⟨characterId, sample⟩ = fourierDisk :=
    FactoredSmallQRawZeroBracketCampaign.decodedOutputDisk_eq_of_output_decode
      hword hdecode
  have hcanonicalFourier :
      (FactoredSmallQRawZeroBracketCampaign.decodedOutputDisk rawTransforms
        ⟨characterId, sample⟩).ContainsComplex
          (FactoredSmallQRawCompletedSignCampaign.directFourier
            (logLength := logLength) oddParity negativeFrequency w prefactors
            delta characters ⟨characterId, sample⟩) := by
    rw [hcanonicalDisk]
    exact hfourier
  have haBooker : parameters.a = ((((64 : ℚ) / 5 : ℚ)) : ℝ) :=
    (hrealizes.2 characterId hcharacter).booker_grid.trans
      FactoredSmallQRawZeroBracketCampaign.bookerA_eq_ratCast
  have hjoined :=
    hrealizes.decodedCellAt_character_and_evaluator hsignCheck hat hgrid
      haBooker hcanonicalFourier hscale htimeTail huntilt
  exact ⟨haPos, hbPos, hetaLower, hetaUpper, hbEq, hsampleLine,
    fourierWord, hword, fourierDisk, hdecode, hfourier, typed, hat,
    hjoined.1, hjoined.2.1, hjoined.2.2⟩

end SparkInterval.Dirichlet.FactoredSmallQSourceRealization
