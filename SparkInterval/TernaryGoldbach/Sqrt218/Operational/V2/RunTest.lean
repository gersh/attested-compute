/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.Run

/-!
# Tiny end-to-end V2 Sqrt218 checker test

This file exercises every architecture-independent V2 pass through the
inclusive bound `5`: the Pratt roster, complete prime-power layout, directed
log rows, fixed-point event fold, and unchanged Abel anchor.  It mirrors the
bounded C checker KAT and is deliberately not evidence for the production
cutoff `2,000,000`.
-/

namespace SparkInterval.Tests.Sqrt218V2Run

open TGComputeContracts.Sqrt218
open SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

private def pair (left right : Nat) : FactorPair :=
  { left, right }

private def roster : PrimeRosterCertificate := {
  rows := [
    {
      prime := 2
      witness := 0
      factorRefs := []
      gapPairs := []
    },
    {
      prime := 3
      witness := 2
      factorRefs := [0]
      gapPairs := []
    },
    {
      prime := 5
      witness := 2
      factorRefs := [0, 0]
      gapPairs := [pair 2 2]
    }
  ]
  tailPairs := []
}

private def event
    (value primeIndex exponent floorSqrt : Nat) : PowerEvent := {
  value
  primeIndex
  exponent
  floorSqrt
}

private def layout : PowerLayoutCertificate := {
  events := [
    event 2 0 1 1,
    event 3 1 1 1,
    event 4 0 2 2,
    event 5 2 1 2
  ]
  eventIndicesByPrime := [
    [0, 2],
    [1],
    [3]
  ]
}

private def logRow (prime : Nat) : LogRows.Row := {
  prime
  lower := (seed prime).lower
  upper := (seed prime).upper
}

private def logs : LogRows.Certificate := {
  rows := [logRow 2, logRow 3, logRow 5]
}

/-- Exact four-event exit, independently reproducible from the fixed-point
equations in `TGComputeContracts.Sqrt218.Kernel`. -/
private def claimedExit : FixedState := {
  weightedUpper := 671_213_081_909_496_578_337_591
  psiLower := 1_152_455_539_665_769
}

private def archive : Archive := {
  kind := certificateKind
  schemaVersion := 2
  bound := 5
  logSeedAt := seedAt
  logScale := scale
  reciprocalScale := reciprocalScale
  roster
  layout
  logs
  claimedExit
}

/- Full bounded composition.  In particular this includes the original
`anchorOK 5` guard; no production condition is disabled or weakened. -/
#guard runAt 5 archive

/- The same tiny artifact cannot enter the production checker. -/
#guard !(run archive)

end SparkInterval.Tests.Sqrt218V2Run
