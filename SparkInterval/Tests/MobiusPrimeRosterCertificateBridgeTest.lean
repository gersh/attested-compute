/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusPrimeRosterCertificateBridgeTest

open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

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
#guard rosterBindingCheck [2, 3, 5, 7] tinyCertificate
#guard !(rosterBindingCheck [2, 3, 5] tinyCertificate)

example : PrimeRosterThrough 10 (rosterList tinyCertificate) :=
  primeRosterThrough_of_checkedCertificate (by decide)

example : PrimeRosterThrough 10 [2, 3, 5, 7] :=
  primeRosterThrough_of_checkedBoundCertificate
    (certificate := tinyCertificate)
    (by decide) (by decide)

#print axioms
  SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge.primeRosterThrough_of_checkedCertificate
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge.primeRosterThrough_of_checkedBoundCertificate

end SparkInterval.Tests.MobiusPrimeRosterCertificateBridgeTest
