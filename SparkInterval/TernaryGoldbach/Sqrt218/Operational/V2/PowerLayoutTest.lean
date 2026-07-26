/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.PowerLayout

/-!
# Tiny V2 prime-power layout tests

These guards cover only the primes and prime powers through `10`.  They test
the certificate shape and tamper rejection; they are not a production replay.
-/

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

open TGComputeContracts.Sqrt218

private def tinyPrimeAt : Nat → Nat
  | 0 => 2
  | 1 => 3
  | 2 => 5
  | 3 => 7
  | _ => 0

private def event
    (value primeIndex exponent floorSqrt : Nat) : PowerEvent := {
  value
  primeIndex
  exponent
  floorSqrt
}

private def tinyLayout : PowerLayoutCertificate := {
  events := [
    event 2 0 1 1,
    event 3 1 1 1,
    event 4 0 2 2,
    event 5 2 1 2,
    event 7 3 1 2,
    event 8 0 3 2,
    event 9 1 2 3
  ]
  eventIndicesByPrime := [
    [0, 2, 5],
    [1, 6],
    [3],
    [4]
  ]
}

#guard powerLayoutCheck 10 4 tinyPrimeAt tinyLayout

private def missingEight : PowerLayoutCertificate :=
  { tinyLayout with eventIndicesByPrime :=
      [[0, 2], [1, 6], [3], [4]] }

#guard !(powerLayoutCheck 10 4 tinyPrimeAt missingEight)

private def duplicateFour : PowerLayoutCertificate :=
  { tinyLayout with events :=
      tinyLayout.events.set 3 (event 4 0 2 2) }

#guard !(powerLayoutCheck 10 4 tinyPrimeAt duplicateFour)

private def wrongExponentReference : PowerLayoutCertificate :=
  { tinyLayout with eventIndicesByPrime :=
      [[0, 5, 2], [1, 6], [3], [4]] }

#guard !(powerLayoutCheck 10 4 tinyPrimeAt wrongExponentReference)

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
