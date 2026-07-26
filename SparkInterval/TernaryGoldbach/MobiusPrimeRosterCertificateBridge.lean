/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.PrimeRoster

/-!
# Reuse the proof-carrying prime-roster checker for the Möbius campaign

The Sqrt218 V2 infrastructure already checks an indexed roster with
Lucas/Pratt prime rows and explicit composite-gap factor pairs.  Its generic
soundness theorem returns exactly all primes through an arbitrary bound.

This file converts that result to the duplicate-free list contract used by
the fused Möbius proof.  Consequently the Hurst campaign does not need a new
trusted primality/completeness format: it may authenticate the raw `u32le`
list and a corresponding V2 certificate, then use this ordinary Lean bridge.

The production `10^8` certificate is not installed here.  Importing this
module performs no large computation.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge

open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

/-- Canonical list view of the indexed certificate roster. -/
def rosterList (certificate : PrimeRosterCertificate) : List Nat :=
  List.ofFn fun index : Fin certificate.count =>
    certificate.primeAt index

/-- Total data-only equality check between the list decoded from the CUDA
`u32le` roster and the list certified by the reusable V2 checker. -/
def rosterBindingCheck
    (rawPrimes : List Nat)
    (certificate : PrimeRosterCertificate) : Bool :=
  decide (rawPrimes = rosterList certificate)

theorem rosterBindingCheck_sound
    {rawPrimes : List Nat}
    {certificate : PrimeRosterCertificate}
    (checked :
      rosterBindingCheck rawPrimes certificate = true) :
    rawPrimes = rosterList certificate := by
  simpa [rosterBindingCheck] using checked

/-- The architecture-neutral indexed roster facts imply the exact list
contract used by the fused Möbius proof. -/
theorem primeRosterThrough_of_facts
    {bound count : Nat} {primeAt : Nat → Nat}
    (facts :
      TGComputeContracts.Sqrt218.PrimeRosterFacts
        bound count primeAt) :
    PrimeRosterThrough bound
      (List.ofFn fun index : Fin count => primeAt index) := by
  refine {
    nodup := ?_
    entriesPrime := ?_
    complete := ?_
  }
  · rw [List.nodup_ofFn]
    intro first second equalValues
    apply Fin.ext
    exact facts.primeAt_injective
      first.isLt second.isLt equalValues
  · intro prime member
    obtain ⟨index, equalValue⟩ :=
      List.mem_ofFn.mp member
    rw [← equalValue]
    exact facts.prime index index.isLt
  · intro prime primePrime primeLe
    obtain ⟨index, indexLt, equalValue⟩ :=
      facts.cover prime primePrime primeLe
    exact List.mem_ofFn.mpr
      ⟨⟨index, indexLt⟩, equalValue⟩

/-- A successful generic V2 certificate check produces the Möbius roster
contract directly. -/
theorem primeRosterThrough_of_checkedCertificate
    {bound : Nat} {certificate : PrimeRosterCertificate}
    (checked :
      primeRosterCheck bound certificate = true) :
    PrimeRosterThrough bound (rosterList certificate) := by
  exact primeRosterThrough_of_facts
    (primeRosterCheck_sound checked)

/-- A Boolean V2 check plus a Boolean raw-list binding check produces the
contract for the exact list consumed by CUDA. -/
theorem primeRosterThrough_of_checkedBoundCertificate
    {bound : Nat} {rawPrimes : List Nat}
    {certificate : PrimeRosterCertificate}
    (certificateChecked :
      primeRosterCheck bound certificate = true)
    (bindingChecked :
      rosterBindingCheck rawPrimes certificate = true) :
    PrimeRosterThrough bound rawPrimes := by
  rw [rosterBindingCheck_sound bindingChecked]
  exact primeRosterThrough_of_checkedCertificate certificateChecked

/-- Specialization used by the production Hurst GPU domain. -/
theorem productionPrimeRosterThrough_of_checkedCertificate
    {certificate : PrimeRosterCertificate}
    (checked :
      primeRosterCheck productionPrimeBound certificate = true) :
    PrimeRosterThrough productionPrimeBound
      (rosterList certificate) :=
  primeRosterThrough_of_checkedCertificate checked

/-- Production specialization for the exact raw list supplied to the
persistent H100 runner. -/
theorem productionPrimeRosterThrough_of_checkedBoundCertificate
    {rawPrimes : List Nat}
    {certificate : PrimeRosterCertificate}
    (certificateChecked :
      primeRosterCheck productionPrimeBound certificate = true)
    (bindingChecked :
      rosterBindingCheck rawPrimes certificate = true) :
    PrimeRosterThrough productionPrimeBound rawPrimes :=
  primeRosterThrough_of_checkedBoundCertificate
    certificateChecked bindingChecked

#print axioms rosterBindingCheck_sound
#print axioms primeRosterThrough_of_facts
#print axioms primeRosterThrough_of_checkedCertificate
#print axioms primeRosterThrough_of_checkedBoundCertificate
#print axioms productionPrimeRosterThrough_of_checkedCertificate
#print axioms productionPrimeRosterThrough_of_checkedBoundCertificate

end SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge
