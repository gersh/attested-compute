/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCampaign

/-!
# Exact coverage across the factored small-`q` modulus campaign

`FactoredSmallQCampaign` proves coverage of the character/frequency product
for one modulus.  This module adds the deliberately simple outer equation:
the accepted single-modulus certificates must occur in exactly the same order
as an application-owned list of single-modulus specifications.

The source list, including every modulus, primitive-character roster, and
transform length, is an argument to the checker.  An untrusted certificate
cannot add, omit, duplicate, or reorder a modulus.  Proving that the supplied
source list is the one required by a paper remains an explicit application
obligation; this structural checker does not define primitive characters or
silently claim source completeness.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQModulusCampaign

open SparkInterval.Dirichlet.FactoredSmallQCampaign

/-- Application-owned ordered list of all active single-modulus domains. -/
structure SourceSpec where
  moduli : List FactoredSmallQCampaign.Spec
  deriving Repr, DecidableEq, BEq

namespace SourceSpec

/-- Recursive finite form of "every modulus specification is well formed". -/
def AllWellFormed : List FactoredSmallQCampaign.Spec → Prop
  | [] => True
  | spec :: rest => spec.WellFormed ∧ AllWellFormed rest

instance (specs : List FactoredSmallQCampaign.Spec) :
    Decidable (AllWellFormed specs) := by
  induction specs with
  | nil => exact isTrue trivial
  | cons spec rest ih =>
      rw [AllWellFormed]
      letI : Decidable spec.WellFormed := inferInstance
      exact instDecidableAnd

/-- Each source modulus is individually well formed and occurs only once.
The nonempty condition prevents a vacuous alleged source campaign. -/
def WellFormed (source : SourceSpec) : Prop :=
  source.moduli ≠ [] ∧
  (source.moduli.map FactoredSmallQCampaign.Spec.q).Nodup ∧
  AllWellFormed source.moduli

instance (source : SourceSpec) : Decidable source.WellFormed := by
  unfold WellFormed
  infer_instance

end SourceSpec

/-- One complete single-modulus certificate for every source specification. -/
structure Certificate (Payload : Type) where
  moduli : List (FactoredSmallQCampaign.Certificate Payload)

/-- Ordered source/certificate matching, including both exact coverage and
every application-selected payload check. -/
def Matched {Payload : Type}
    (payloadCheck : FactoredSmallQCampaign.Spec → CellKey → Payload → Bool) :
    List FactoredSmallQCampaign.Spec →
      List (FactoredSmallQCampaign.Certificate Payload) → Prop :=
  List.Forall₂ fun spec certificate ↦
    certificate.CoverageValid spec ∧
      certificate.PayloadsValid (payloadCheck spec)

/-- Executable ordered replay.  Unequal list lengths fail closed. -/
def checkPairs {Payload : Type}
    (payloadCheck : FactoredSmallQCampaign.Spec → CellKey → Payload → Bool) :
    List FactoredSmallQCampaign.Spec →
      List (FactoredSmallQCampaign.Certificate Payload) → Bool
  | [], [] => true
  | spec :: specs, certificate :: certificates =>
      certificate.check spec (payloadCheck spec) &&
        checkPairs payloadCheck specs certificates
  | _, _ => false

/-- Exact outer-modulus checker.  The producer supplies data, while the
application supplies both the source domain and payload predicate. -/
def Certificate.check {Payload : Type}
    (source : SourceSpec) (certificate : Certificate Payload)
    (payloadCheck : FactoredSmallQCampaign.Spec → CellKey → Payload → Bool) :
    Bool :=
  decide source.WellFormed &&
    checkPairs payloadCheck source.moduli certificate.moduli

theorem checkPairs_sound {Payload : Type}
    {payloadCheck : FactoredSmallQCampaign.Spec → CellKey → Payload → Bool}
    {specs : List FactoredSmallQCampaign.Spec}
    {certificates : List (FactoredSmallQCampaign.Certificate Payload)}
    (hcheck : checkPairs payloadCheck specs certificates = true) :
    Matched payloadCheck specs certificates := by
  induction specs generalizing certificates with
  | nil =>
      cases certificates with
      | nil => exact List.Forall₂.nil
      | cons certificate rest => simp [checkPairs] at hcheck
  | cons spec specs ih =>
      cases certificates with
      | nil => simp [checkPairs] at hcheck
      | cons certificate certificates =>
          simp only [checkPairs, Bool.and_eq_true] at hcheck
          exact List.Forall₂.cons
            (FactoredSmallQCampaign.Certificate.checker_sound hcheck.1)
            (ih hcheck.2)

/-- Soundness exposes the human-readable source condition and exact ordered
matching of every single-modulus certificate. -/
theorem Certificate.checker_sound {Payload : Type}
    {source : SourceSpec} {certificate : Certificate Payload}
    {payloadCheck : FactoredSmallQCampaign.Spec → CellKey → Payload → Bool}
    (hcheck : certificate.check source payloadCheck = true) :
    source.WellFormed ∧
      Matched payloadCheck source.moduli certificate.moduli := by
  simp only [Certificate.check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1, checkPairs_sound hcheck.2⟩

private theorem exists_certificate_of_matched {Payload : Type}
    {payloadCheck : FactoredSmallQCampaign.Spec → CellKey → Payload → Bool}
    {specs : List FactoredSmallQCampaign.Spec}
    {certificates : List (FactoredSmallQCampaign.Certificate Payload)}
    (hmatched : Matched payloadCheck specs certificates)
    {spec : FactoredSmallQCampaign.Spec}
    (hspec : spec ∈ specs) :
    ∃ modulusCertificate, modulusCertificate ∈ certificates ∧
      modulusCertificate.CoverageValid spec ∧
      modulusCertificate.PayloadsValid (payloadCheck spec) := by
  induction hmatched with
  | nil => simp at hspec
  | @cons headSpec headCertificate specs certificates headValid tailMatched ih =>
      simp only [List.mem_cons] at hspec
      rcases hspec with hspec | hspec
      · subst spec
        exact ⟨headCertificate, by simp, headValid⟩
      · rcases ih hspec with ⟨found, hfound, hcoverage, hpayloads⟩
        exact ⟨found, by simp [hfound], hcoverage, hpayloads⟩

/-- Every application-requested modulus has the corresponding accepted
single-modulus certificate; ordered `Forall₂` matching prevents substitution. -/
theorem exists_certificate_for_source_modulus {Payload : Type}
    {source : SourceSpec} {certificate : Certificate Payload}
    {payloadCheck : FactoredSmallQCampaign.Spec → CellKey → Payload → Bool}
    (hmatched : Matched payloadCheck source.moduli certificate.moduli)
    {spec : FactoredSmallQCampaign.Spec}
    (hspec : spec ∈ source.moduli) :
    ∃ modulusCertificate, modulusCertificate ∈ certificate.moduli ∧
      modulusCertificate.CoverageValid spec ∧
      modulusCertificate.PayloadsValid (payloadCheck spec) :=
  exists_certificate_of_matched hmatched hspec

/-- Full two-level lookup: every requested source modulus, character, and
frequency has an actual accepted payload under the application predicate. -/
theorem exists_payload_for_requested_cell {Payload : Type}
    {source : SourceSpec} {certificate : Certificate Payload}
    {payloadCheck : FactoredSmallQCampaign.Spec → CellKey → Payload → Bool}
    (hcheck : certificate.check source payloadCheck = true)
    {spec : FactoredSmallQCampaign.Spec}
    (hspec : spec ∈ source.moduli)
    {characterId frequency : Nat}
    (hcharacter : characterId ∈ spec.roster)
    (hfrequency : frequency < spec.transformLength) :
    ∃ modulusCertificate, modulusCertificate ∈ certificate.moduli ∧
      ∃ batch, batch ∈ modulusCertificate.batches ∧
        ∃ cell, cell ∈ batch.cells ∧
          cell.key = ⟨characterId, frequency⟩ ∧
          payloadCheck spec cell.key cell.payload = true := by
  have hsound := Certificate.checker_sound hcheck
  rcases exists_certificate_for_source_modulus hsound.2 hspec with
    ⟨modulusCertificate, hmodulus, hcoverage, hpayloads⟩
  rcases modulusCertificate.exists_cell_for_requested_key
      hcoverage hcharacter hfrequency with
    ⟨batch, hbatch, cell, hcell, hkey⟩
  exact ⟨modulusCertificate, hmodulus, batch, hbatch, cell, hcell,
    hkey, hpayloads batch hbatch cell hcell⟩

end SparkInterval.Dirichlet.FactoredSmallQModulusCampaign
