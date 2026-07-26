/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.PrimeRoster

/-!
# Tiny executable tests for the V2 prime-roster checker

These checks stop at `10`; they are format/kernel tests, not a production
replay or evidence for the Sqrt218 cutoff.
-/

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

private def pair (left right : Nat) : FactorPair :=
  { left, right }

private def tinyCertificate : PrimeRosterCertificate := {
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
    },
    {
      prime := 7
      witness := 3
      factorRefs := [0, 1]
      gapPairs := [pair 2 3]
    }
  ]
  tailPairs := [pair 2 4, pair 3 3, pair 2 5]
}

#guard primeRosterCheck 10 tinyCertificate

private def missingTail : PrimeRosterCertificate :=
  { tinyCertificate with tailPairs := [pair 2 4, pair 3 3] }

#guard !(primeRosterCheck 10 missingTail)

private def forwardFactorReference : PrimeRosterCertificate :=
  { tinyCertificate with
    rows :=
      tinyCertificate.rows.set 2 {
        prime := 5
        witness := 2
        factorRefs := [3, 3]
        gapPairs := [pair 2 2]
      } }

#guard !(primeRosterCheck 10 forwardFactorReference)

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
