/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign
import SparkInterval.Dirichlet.FactoredSmallQZeroBracket

/-!
# Raw completed-sign campaigns as checked zero brackets

This module is the finite arithmetic link between literal raw DFT output words
and `FactoredSmallQZeroBracket`.  A decoded typed completed-sign certificate is
accepted only when it is the decode of an actual campaign cell.  The campaign
checker in turn checks that cell against the literal raw word at the same
source-owned `(character, sample)` key.

`decodedOutputDisk` is total only so it can serve as the disk table expected by
the typed endpoint checker.  Its fallback is proved unreachable whenever a
literal output word decodes successfully; `decodedCellAt_endpoint_check` proves
that this is the case for every accepted decoded campaign cell.

The final pair theorem checks only exact finite facts: source coverage, raw-word
attachment and decoding, rational grid order, and opposite strict disk signs.
It deliberately does not manufacture an evaluator interpretation.  The
`EvaluatorLink` premises in `FactoredSmallQZeroBracket` remain necessary before
the checked sign pair can imply the existence of a zero of a named function.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQZeroBracket

abbrev SourceSampleSpec :=
  FactoredSmallQRawCompletedSignPayloadCampaign.SourceSampleSpec

abbrev SourceParameters :=
  FactoredSmallQRawCompletedSignPayloadCampaign.SourceParameters

abbrev RawSignCampaignCertificate :=
  FactoredSmallQRawCompletedSignPayloadCampaign.RawSignCampaignCertificate

/-! ## Canonical literal-output disk table -/

/-- Decode exactly the literal raw DFT output word selected by a source key.
The fallback merely makes the function total; accepted endpoint proofs below
show that it is unreachable at every campaign cell they expose. -/
def decodedOutputDisk {logLength : Nat}
    (rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength)
    (key : CellKey) : ComplexDisk :=
  match (rawTransforms key.characterId).output[key.frequency]? with
  | none => FactoredSmallQRawDFT.fallbackDisk
  | some raw => raw.decode.getD FactoredSmallQRawDFT.fallbackDisk

/-- A successful literal-word lookup and decode makes both fallback branches
of `decodedOutputDisk` unreachable. -/
theorem decodedOutputDisk_eq_of_output_decode
    {logLength : Nat}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {key : CellKey} {raw : ComplexDisk.Raw} {disk : ComplexDisk}
    (hword :
      (rawTransforms key.characterId).output[key.frequency]? = some raw)
    (hdecode : raw.decode = some disk) :
    decodedOutputDisk rawTransforms key = disk := by
  simp [decodedOutputDisk, hword, hdecode]

/-! ## Exact typed decode of a campaign cell -/

/-- A typed certificate occurs at a key only when it is the deterministic
decode of the raw payload of an actual cell in the checked campaign. -/
def DecodedCellAt (campaign : RawSignCampaignCertificate)
    (key : CellKey) (typed : Certificate) : Prop :=
  ∃ batch, batch ∈ campaign.batches ∧
    ∃ cell, cell ∈ batch.cells ∧
      cell.key = key ∧ cell.payload.decode = some typed

/-- Every actual cell of an accepted campaign lies in the source-owned
character/sample product, independently of how its payload is decoded. -/
theorem cell_key_in_source_domain
    {logLength : Nat} {fullSpec : Spec} {sourceSpec : SourceSampleSpec}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign : RawSignCampaignCertificate}
    {batch : Batch FactoredSmallQRawCompletedSign.RawCertificate}
    {cell : Cell FactoredSmallQRawCompletedSign.RawCertificate}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
        rawTransforms campaign = true)
    (hbatch : batch ∈ campaign.batches) (hcell : cell ∈ batch.cells) :
    cell.key.characterId ∈ sourceSpec.roster ∧
      cell.key.frequency < sourceSpec.sampleCount := by
  have hsound :=
    FactoredSmallQRawCompletedSignPayloadCampaign.checker_sound hcheck
  have hkeyMem :
      cell.key ∈ campaign.batches.flatMap
        (fun acceptedBatch => acceptedBatch.cells.map Cell.key) := by
    apply List.mem_flatMap.mpr
    refine ⟨batch, hbatch, ?_⟩
    apply List.mem_map.mpr
    exact ⟨cell, hcell, rfl⟩
  rw [hsound.2.1.2.2.2.2.2.2.2] at hkeyMem
  simp only [expectedKeys, List.mem_flatMap, List.mem_map,
    List.mem_range,
    FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec]
      at hkeyMem
  rcases hkeyMem with
    ⟨characterId, hcharacter, frequency, hfrequency, hkeyEq⟩
  rw [← hkeyEq]
  exact ⟨hcharacter, hfrequency⟩

/-- An exposed decoded cell of an accepted campaign lies in the complete
source-owned Cartesian-product domain. -/
theorem DecodedCellAt.key_in_source_domain
    {logLength : Nat} {fullSpec : Spec} {sourceSpec : SourceSampleSpec}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign : RawSignCampaignCertificate}
    {key : CellKey} {typed : Certificate}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
        rawTransforms campaign = true)
    (hat : DecodedCellAt campaign key typed) :
    key.characterId ∈ sourceSpec.roster ∧
      key.frequency < sourceSpec.sampleCount := by
  rcases hat with ⟨batch, hbatch, cell, hcell, hkey, _hdecode⟩
  rw [← hkey]
  exact cell_key_in_source_domain hcheck hbatch hcell

/-- Canonical typed endpoint at the exact rational source-grid time. -/
def mkEndpoint (a : ℚ) (key : CellKey) (typed : Certificate) :
    SignedEndpoint := {
  key
  time := SignedEndpoint.sourceTime a key
  certificate := typed
}

/-- The raw campaign check proves the typed endpoint checker against the disk
decoded from the literal raw DFT word at the same key.  No analytic containment,
reality, or evaluator premise is used. -/
theorem decodedCellAt_endpoint_check
    {logLength : Nat} {fullSpec : Spec} {sourceSpec : SourceSampleSpec}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign : RawSignCampaignCertificate}
    {a : ℚ} {key : CellKey} {typed : Certificate}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
        rawTransforms campaign = true)
    (hat : DecodedCellAt campaign key typed) :
    (mkEndpoint a key typed).check (decodedOutputDisk rawTransforms) = true := by
  have hsound :=
    FactoredSmallQRawCompletedSignPayloadCampaign.checker_sound hcheck
  rcases hat with ⟨batch, hbatch, cell, hcell, hkey, htypedDecode⟩
  have hpayload := hsound.2.2 batch hbatch cell hcell
  change FactoredSmallQRawCompletedSignPayloadCampaign.payloadCheck
    rawTransforms cell.key cell.payload = true at hpayload
  rw [hkey] at hpayload
  unfold FactoredSmallQRawCompletedSignPayloadCampaign.payloadCheck at hpayload
  cases hword :
      (rawTransforms key.characterId).output[key.frequency]? with
  | none => simp [hword] at hpayload
  | some raw =>
      have hrawCheck : cell.payload.check raw = true := by
        simpa [hword] using hpayload
      rcases FactoredSmallQRawCompletedSign.RawCertificate.checker_sound
          hrawCheck with
        ⟨_hattached, disk, decoded, hrawDecode, hdecodedCertificate,
          haccepted⟩
      rw [htypedDecode] at hdecodedCertificate
      have htypedEq : typed = decoded :=
        Option.some.inj hdecodedCertificate
      subst decoded
      change typed.check (decodedOutputDisk rawTransforms key) = true
      rw [decodedOutputDisk_eq_of_output_decode hword hrawDecode]
      exact decide_eq_true_eq.mpr haccepted

/-- Semantic endpoint handoff with a deliberately explicit source-realization
premise.  The raw campaign discharges only the finite endpoint check; every
analytic containment, tail, reality, and evaluator-equality fact remains inside
`SourceRealizes`. -/
theorem decodedCellAt_evaluatorLink_of_sourceRealizes
    {logLength : Nat} {fullSpec : Spec} {sourceSpec : SourceSampleSpec}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign : RawSignCampaignCertificate}
    {a : ℚ} {key : CellKey} {typed : Certificate}
    {f : ℝ → ℝ} {fourier timeTail : ℂ} {b eta : ℝ}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
        rawTransforms campaign = true)
    (hat : DecodedCellAt campaign key typed)
    (hrealizes :
      (mkEndpoint a key typed).SourceRealizes
        (decodedOutputDisk rawTransforms) f fourier timeTail b eta) :
    (mkEndpoint a key typed).EvaluatorLink f :=
  SignedEndpoint.evaluatorLink_of_sourceRealizes
    (decodedCellAt_endpoint_check hcheck hat) hrealizes

/-! ## Exact rational/real grid handoff -/

/-- The rational time stored in a zero-bracket endpoint is exactly the real
time used by `SourceParameters` when the two sampling-rate headers agree. -/
theorem sourceTime_cast_eq_parameters_t
    (a : ℚ) (parameters : SourceParameters) (key : CellKey)
    (ha : parameters.a = (a : ℝ)) :
    ((SignedEndpoint.sourceTime a key : ℚ) : ℝ) = parameters.t key := by
  rw [SignedEndpoint.sourceTime_cast]
  unfold FactoredSmallQRawCompletedSignCampaign.SourceParameters.t
  rw [ha]

/-- The production Booker sampling rate has the exact rational spelling
`64 / 5`; this is an equality, not a floating-point approximation. -/
theorem bookerA_eq_ratCast :
    FactoredSmallQRawCompletedSignCampaign.SourceParameters.bookerA =
      (((64 : ℚ) / 5 : ℚ) : ℝ) := by
  norm_num [FactoredSmallQRawCompletedSignCampaign.SourceParameters.bookerA]

/-- Booker-specialized source-time alignment. -/
theorem booker_sourceTime_cast_eq_parameters_t
    (parameters : SourceParameters) (key : CellKey)
    (ha : parameters.a =
      FactoredSmallQRawCompletedSignCampaign.SourceParameters.bookerA) :
    ((SignedEndpoint.sourceTime ((64 : ℚ) / 5) key : ℚ) : ℝ) =
      parameters.t key := by
  apply sourceTime_cast_eq_parameters_t
  rw [ha, bookerA_eq_ratCast]

/-! ## Two decoded cells as one checked bracket -/

/-- Pair two typed decodes while retaining their exact source keys and the one
shared rational sampling-rate header. -/
def mkBracket (a : ℚ)
    (lowerKey : CellKey) (lowerTyped : Certificate)
    (upperKey : CellKey) (upperTyped : Certificate) :
    CompletedSignBracket := {
  a
  lower := mkEndpoint a lowerKey lowerTyped
  upper := mkEndpoint a upperKey upperTyped
}

/-- Literal raw words, their deterministic typed decodes, and exact rational
ordering produce a checked completed-sign bracket.  This is the complete
finite-arithmetic handoff; evaluator links remain explicit downstream. -/
theorem decodedCells_bracket_check
    {logLength : Nat} {fullSpec : Spec} {sourceSpec : SourceSampleSpec}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign : RawSignCampaignCertificate}
    {a : ℚ} {lowerKey upperKey : CellKey}
    {lowerTyped upperTyped : Certificate}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
        rawTransforms campaign = true)
    (hlower : DecodedCellAt campaign lowerKey lowerTyped)
    (hupper : DecodedCellAt campaign upperKey upperTyped)
    (ha : 0 < a)
    (hcharacter : lowerKey.characterId = upperKey.characterId)
    (hfrequency : lowerKey.frequency < upperKey.frequency)
    (hopposite : CompletedSignBracket.OppositeSigns lowerTyped.sign
      upperTyped.sign) :
    (mkBracket a lowerKey lowerTyped upperKey upperTyped).check
      (decodedOutputDisk rawTransforms) = true := by
  apply CompletedSignBracket.check_eq_true.mpr
  refine ⟨ha, hcharacter, hfrequency, rfl, rfl, ?_, ?_, ?_, hopposite⟩
  · have hfrequencyRat :
        (lowerKey.frequency : ℚ) < (upperKey.frequency : ℚ) := by
      exact_mod_cast hfrequency
    exact (div_lt_div_iff_of_pos_right ha).2 hfrequencyRat
  · exact decodedCellAt_endpoint_check hcheck hlower
  · exact decodedCellAt_endpoint_check hcheck hupper

/-- Clean semantic composition for one raw-word-backed pair.  The finite raw
campaign proves the rational bracket check, while the two explicit
`SourceRealizes` premises prove that its endpoint intervals enclose the named
real evaluator.  No analytic fact is inferred from the raw arithmetic. -/
theorem decodedCells_checkedRationalBracket_of_sourceRealizes
    {logLength : Nat} {fullSpec : Spec} {sourceSpec : SourceSampleSpec}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {campaign : RawSignCampaignCertificate}
    {a : ℚ} {lowerKey upperKey : CellKey}
    {lowerTyped upperTyped : Certificate}
    {f : ℝ → ℝ}
    {lowerFourier upperFourier lowerTail upperTail : ℂ}
    {b eta : ℝ}
    (hcheck :
      FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
        rawTransforms campaign = true)
    (hlower : DecodedCellAt campaign lowerKey lowerTyped)
    (hupper : DecodedCellAt campaign upperKey upperTyped)
    (ha : 0 < a)
    (hcharacter : lowerKey.characterId = upperKey.characterId)
    (hfrequency : lowerKey.frequency < upperKey.frequency)
    (hopposite : CompletedSignBracket.OppositeSigns lowerTyped.sign
      upperTyped.sign)
    (hlowerRealizes :
      (mkEndpoint a lowerKey lowerTyped).SourceRealizes
        (decodedOutputDisk rawTransforms) f lowerFourier lowerTail b eta)
    (hupperRealizes :
      (mkEndpoint a upperKey upperTyped).SourceRealizes
        (decodedOutputDisk rawTransforms) f upperFourier upperTail b eta) :
    (mkBracket a lowerKey lowerTyped upperKey upperTyped).toRationalBracket.check =
        true ∧
      (mkBracket a lowerKey lowerTyped upperKey upperTyped).toRationalBracket.EnclosesEndpoints
        f := by
  apply CompletedSignBracket.checkedRationalBracket_of_sourceRealizes
    (decodedCells_bracket_check hcheck hlower hupper ha hcharacter hfrequency
      hopposite)
  · simpa [mkBracket] using hlowerRealizes
  · simpa [mkBracket] using hupperRealizes

end SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign
