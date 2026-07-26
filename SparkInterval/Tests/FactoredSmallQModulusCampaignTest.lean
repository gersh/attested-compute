/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQModulusCampaign

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQModulusCampaignTest

open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQModulusCampaign

private abbrev SingleSpec :=
  SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec
private abbrev SingleCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate
private abbrev ModulusCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQModulusCampaign.Certificate

private def spec3 : SingleSpec :=
  ⟨3, [2], 2⟩

private def spec4 : SingleSpec :=
  ⟨4, [3], 1⟩

private def source : SourceSpec :=
  ⟨[spec3, spec4]⟩

private def cells3 : List (Cell Nat) :=
  [⟨⟨2, 0⟩, 30⟩, ⟨⟨2, 1⟩, 31⟩]

private def cells4 : List (Cell Nat) :=
  [⟨⟨3, 0⟩, 40⟩]

private def certificate3 : SingleCertificate Nat := {
  q := 3
  roster := [2]
  transformLength := 2
  batches := [⟨0, 0, [2], cells3⟩]
}

private def certificate4 : SingleCertificate Nat := {
  q := 4
  roster := [3]
  transformLength := 1
  batches := [⟨0, 0, [3], cells4⟩]
}

private def certificate : ModulusCertificate Nat :=
  ⟨[certificate3, certificate4]⟩

private def payloadCheck (spec : SingleSpec)
    (key : CellKey) (payload : Nat) : Bool :=
  decide (payload = spec.q * 10 + key.frequency)

example : certificate.check source payloadCheck = true := by decide

example :
    ∃ modulusCertificate, modulusCertificate ∈ certificate.moduli ∧
      ∃ batch, batch ∈ modulusCertificate.batches ∧
        ∃ cell, cell ∈ batch.cells ∧
          cell.key = ⟨3, 0⟩ ∧
          payloadCheck spec4 cell.key cell.payload = true := by
  apply exists_payload_for_requested_cell
    (source := source) (certificate := certificate)
    (payloadCheck := payloadCheck)
  · decide
  · simp [source, spec3, spec4]
  · simp [spec4]
  · simp [spec4]

private def missingModulus : ModulusCertificate Nat :=
  ⟨[certificate3]⟩

private def reversedModuli : ModulusCertificate Nat :=
  ⟨[certificate4, certificate3]⟩

private def duplicateSource : SourceSpec :=
  ⟨[spec3, spec3]⟩

example : missingModulus.check source payloadCheck = false := by decide
example : reversedModuli.check source payloadCheck = false := by decide
example : certificate.check duplicateSource payloadCheck = false := by decide

#print axioms
  SparkInterval.Dirichlet.FactoredSmallQModulusCampaign.Certificate.checker_sound
#print axioms
  SparkInterval.Dirichlet.FactoredSmallQModulusCampaign.exists_payload_for_requested_cell

end SparkInterval.Tests.FactoredSmallQModulusCampaignTest
