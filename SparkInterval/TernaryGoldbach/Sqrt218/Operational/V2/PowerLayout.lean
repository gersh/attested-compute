/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.PrimeRoster

/-!
# Linear-size V2 prime-power layout certificate

The V1 operational checker reconstructs an inverse map by repeatedly scanning
the whole event list.  That is a useful specification, but it is the wrong
shape for a production checker.

V2 carries the inverse map explicitly: for each prime row it stores the event
indices for exponents `1, 2, ...` in that order.  The total number of index
references is linear in the number of events.  A native checker can therefore
validate event rows, adjacent ordering, and all inverse-map cells in linear
work without any production-sized Lean evaluation.

This file contains only the generic Boolean model and its data-independent
soundness proof.  It has no production arrays and performs no long replay when
compiled.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

open TGComputeContracts.Sqrt218

/-- Events plus one explicit exponent-to-event map per prime row. -/
structure PowerLayoutCertificate where
  events : List PowerEvent
  eventIndicesByPrime : List (List Nat)
  deriving Repr, DecidableEq, Inhabited

namespace PowerLayoutCertificate

def eventCount (certificate : PowerLayoutCertificate) : Nat :=
  certificate.events.length

def eventAt
    (certificate : PowerLayoutCertificate) (index : Nat) : PowerEvent :=
  certificate.events.getD index default

def powerIndicesAt
    (certificate : PowerLayoutCertificate) (primeIndex : Nat) : List Nat :=
  certificate.eventIndicesByPrime.getD primeIndex []

def powerCountAt
    (certificate : PowerLayoutCertificate) (primeIndex : Nat) : Nat :=
  (certificate.powerIndicesAt primeIndex).length

def canonicalIndexAt
    (certificate : PowerLayoutCertificate)
    (primeIndex exponentIndex : Nat) : Nat :=
  (certificate.powerIndicesAt primeIndex).getD exponentIndex 0

end PowerLayoutCertificate

/-! ## Executable cells -/

def powerEventCellCheck
    (bound primeCount : Nat) (primeAt : Nat → Nat)
    (certificate : PowerLayoutCertificate) (eventIndex : Nat) : Bool :=
  let event := certificate.eventAt eventIndex
  decide (
    event.value ≤ bound ∧
      event.primeIndex < primeCount ∧
      0 < event.exponent ∧
      event.value = primeAt event.primeIndex ^ event.exponent ∧
      event.floorSqrt = Nat.sqrt event.value)

def powerEventAdjacentCheck
    (certificate : PowerLayoutCertificate) (eventIndex : Nat) : Bool :=
  decide (
    (certificate.eventAt eventIndex).value <
      (certificate.eventAt (eventIndex + 1)).value)

def powerIndexCellCheck
    (certificate : PowerLayoutCertificate)
    (primeIndex exponentIndex : Nat) : Bool :=
  let eventIndex := certificate.canonicalIndexAt primeIndex exponentIndex
  let event := certificate.eventAt eventIndex
  decide (
    eventIndex < certificate.eventCount ∧
      event.primeIndex = primeIndex ∧
      event.exponent = exponentIndex + 1)

def powerIndexRowCheck
    (bound : Nat) (primeAt : Nat → Nat)
    (certificate : PowerLayoutCertificate) (primeIndex : Nat) : Bool :=
  let count := certificate.powerCountAt primeIndex
  let prime := primeAt primeIndex
  decide (
    0 < count ∧
      prime ^ count ≤ bound ∧
      bound < prime ^ (count + 1)) &&
    checkRange 0 count
      (powerIndexCellCheck certificate primeIndex)

/-- Linear-size V2 layout checker.

`eventIndicesByPrime` has exactly one row per prime.  The sum of the row
lengths, rather than `primeCount * eventCount`, controls the inverse-map work.
-/
def powerLayoutCheck
    (bound primeCount : Nat) (primeAt : Nat → Nat)
    (certificate : PowerLayoutCertificate) : Bool :=
  decide (certificate.eventIndicesByPrime.length = primeCount) &&
    (checkRange 0 certificate.eventCount
        (powerEventCellCheck bound primeCount primeAt certificate) &&
      (checkRange 0 (certificate.eventCount - 1)
          (powerEventAdjacentCheck certificate) &&
        checkRange 0 primeCount
          (powerIndexRowCheck bound primeAt certificate)))

/-! ## Soundness -/

/-- Successful checking yields the complete, sorted, unique prime-power
enumeration required by the architecture-neutral certificate kernel. -/
theorem powerLayoutCheck_sound
    {bound primeCount : Nat} {primeAt : Nat → Nat}
    {certificate : PowerLayoutCertificate}
    (hroster : PrimeRosterFacts bound primeCount primeAt)
    (hcheck :
      powerLayoutCheck bound primeCount primeAt certificate = true) :
    PrimePowerEnumerationFacts
      bound primeCount primeAt
      certificate.eventCount certificate.eventAt := by
  simp only [powerLayoutCheck, Bool.and_eq_true,
    decide_eq_true_eq] at hcheck
  have hevent :
      ∀ eventIndex, eventIndex < certificate.eventCount →
        PowerEventFacts bound primeCount primeAt
          (certificate.eventAt eventIndex) := by
    intro eventIndex hindex
    have hcell :=
      checkRange_sound hcheck.2.1 eventIndex
        (by omega) (by simpa using hindex)
    simp only [powerEventCellCheck, decide_eq_true_eq] at hcell
    exact {
      value_le := hcell.1
      primeIndex_lt := hcell.2.1
      exponent_pos := hcell.2.2.1
      value_eq := hcell.2.2.2.1
      floorSqrt_eq := hcell.2.2.2.2
    }
  have horder :
      ∀ eventIndex, eventIndex + 1 < certificate.eventCount →
        (certificate.eventAt eventIndex).value <
          (certificate.eventAt (eventIndex + 1)).value := by
    intro eventIndex hindex
    have hcell :=
      checkRange_sound hcheck.2.2.1 eventIndex
        (by omega) (by omega)
    simpa [powerEventAdjacentCheck, decide_eq_true_eq] using hcell
  have hrow :
      ∀ primeIndex, primeIndex < primeCount →
        powerIndexRowCheck bound primeAt certificate primeIndex = true := by
    intro primeIndex hindex
    exact
      checkRange_sound hcheck.2.2.2 primeIndex
        (by omega) (by simpa using hindex)
  have hcount :
      ∀ primeIndex, primeIndex < primeCount →
        0 < certificate.powerCountAt primeIndex ∧
          primeAt primeIndex ^
              certificate.powerCountAt primeIndex ≤ bound ∧
          bound <
            primeAt primeIndex ^
              (certificate.powerCountAt primeIndex + 1) := by
    intro primeIndex hindex
    have hcell := hrow primeIndex hindex
    simp only [powerIndexRowCheck, Bool.and_eq_true,
      decide_eq_true_eq] at hcell
    exact hcell.1
  have hcoverage :
      ∀ primeIndex, primeIndex < primeCount →
        ∀ exponentIndex,
          exponentIndex < certificate.powerCountAt primeIndex →
          certificate.canonicalIndexAt primeIndex exponentIndex <
              certificate.eventCount ∧
            (certificate.eventAt
                (certificate.canonicalIndexAt
                  primeIndex exponentIndex)).primeIndex = primeIndex ∧
            (certificate.eventAt
                (certificate.canonicalIndexAt
                  primeIndex exponentIndex)).exponent =
              exponentIndex + 1 := by
    intro primeIndex hprimeIndex exponentIndex hexponentIndex
    have hprimeRow := hrow primeIndex hprimeIndex
    simp only [powerIndexRowCheck, Bool.and_eq_true,
      decide_eq_true_eq] at hprimeRow
    have hcell :=
      checkRange_sound hprimeRow.2 exponentIndex
        (by omega) (by simpa using hexponentIndex)
    simpa [powerIndexCellCheck, decide_eq_true_eq] using hcell
  exact
    primePowerEnumerationFacts_of_canonical
      hroster hevent horder hcount hcoverage

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
