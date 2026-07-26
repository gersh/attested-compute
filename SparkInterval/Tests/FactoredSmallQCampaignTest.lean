/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCampaign

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQCampaign

open SparkInterval.Dirichlet.FactoredSmallQCampaign

def payloadCheck (_key : CellKey) (payload : Nat) : Bool := decide (payload = 7)

def expected : Spec := {
  q := 997
  roster := [11, 13, 17]
  transformLength := 2
}

def batch0 : Batch Nat := {
  ordinal := 0
  characterStart := 0
  characters := [11, 13]
  cells := [
    ⟨⟨11, 0⟩, 7⟩, ⟨⟨11, 1⟩, 7⟩,
    ⟨⟨13, 0⟩, 7⟩, ⟨⟨13, 1⟩, 7⟩]
}

def batch1 : Batch Nat := {
  ordinal := 1
  characterStart := 2
  characters := [17]
  cells := [⟨⟨17, 0⟩, 7⟩, ⟨⟨17, 1⟩, 7⟩]
}

def good : Certificate Nat := {
  q := 997
  roster := [11, 13, 17]
  transformLength := 2
  batches := [batch0, batch1]
}

theorem good_check : good.check expected payloadCheck = true := by
  decide

def missingCell : Certificate Nat :=
  { good with batches := good.batches.modify 1 fun batch =>
      { batch with cells := [⟨⟨17, 0⟩, 7⟩] } }

theorem missing_cell_fails :
    missingCell.check expected payloadCheck = false := by
  decide

def badPayload : Certificate Nat :=
  { good with batches := good.batches.modify 0 fun batch =>
      { batch with cells := batch.cells.modify 0 fun cell =>
          { cell with payload := 8 } } }

theorem bad_payload_fails : badPayload.check expected payloadCheck = false := by
  decide

def duplicatedRoster : Certificate Nat :=
  { good with roster := [11, 13, 13] }

theorem duplicate_roster_fails :
    duplicatedRoster.check expected payloadCheck = false := by
  decide

/-- A self-consistent certificate for a different modulus cannot redefine the
application-owned source domain. -/
def wrongModulus : Certificate Nat := { good with q := 991 }

theorem wrong_modulus_fails :
    wrongModulus.check expected payloadCheck = false := by
  decide

/-- Keeping the global flattened key order while moving one cell across the
physical batch boundary still fails the per-batch product equation. -/
def wrongBatchBoundary : Certificate Nat :=
  { good with batches := [
      { batch0 with
        cells := [⟨⟨11, 0⟩, 7⟩, ⟨⟨11, 1⟩, 7⟩, ⟨⟨13, 0⟩, 7⟩] },
      { batch1 with
        cells := [⟨⟨13, 1⟩, 7⟩, ⟨⟨17, 0⟩, 7⟩, ⟨⟨17, 1⟩, 7⟩] }
    ] }

theorem wrong_batch_boundary_fails :
    wrongBatchBoundary.check expected payloadCheck = false := by
  decide

#print axioms Certificate.checker_sound
#print axioms Certificate.requested_key_mem
#print axioms Certificate.accepted_cell_count

end SparkInterval.Tests.FactoredSmallQCampaign
