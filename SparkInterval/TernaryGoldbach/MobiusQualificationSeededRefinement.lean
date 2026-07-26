/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
import SparkInterval.TernaryGoldbach.MobiusResidue23571113

/-!
# End-to-end pure refinement for qualification Möbius seeds

The production packed split-square theorem starts from the exact `2·3·5`
residue seed.  This file proves the same end-to-end statement for the
qualification `2·3·5·7`, `2·3·5·7·11`, and `2·3·5·7·11·13` seeds.

For each seed, a complete prime roster and a nonpoison packed result imply
that the decoded output is Mathlib's Möbius function.  The proof composes:

* exact residue-seed arithmetic;
* the pure packed-word refinement;
* equality of the split divisor/square passes with the source prime fold; and
* the complete-roster finalization theorem.

As in the underlying packed theorem, this remains below the compiler and
runtime boundary.  It proves the mathematical algorithm, not that a
particular CUDA binary executed it.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusQualificationSeededRefinement

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization

/-- Packed split-square execution after the exact `2·3·5·7`
qualification seed. -/
def packedSplitRunResidue2357Seeded
    (number : Nat) (suffix : List Nat) : Nat :=
  packedSplitRun
    (MobiusResidue2357.residueSeed2357 number)
    (rowSplitEvents number suffix)

/-- Packed split-square execution after the exact `2·3·5·7·11`
qualification seed. -/
def packedSplitRunResidue235711Seeded
    (number : Nat) (suffix : List Nat) : Nat :=
  packedSplitRun
    (MobiusResidue235711.residueSeed235711 number)
    (rowSplitEvents number suffix)

/-- Packed split-square execution after the exact `2·3·5·7·11·13`
qualification seed. -/
def packedSplitRunResidue23571113Seeded
    (number : Nat) (suffix : List Nat) : Nat :=
  packedSplitRun
    (MobiusResidue23571113.residueSeed23571113 number)
    (rowSplitEvents number suffix)

/-- The p7-seeded nonpoison packed algorithm computes Mathlib's Möbius
function for a complete source roster. -/
theorem output_decodeWord_packedSplitRunResidue2357Seeded_eq_moebius
    {number : Nat} {suffix : List Nat}
    (roster :
      CompletePrimeRoster number
        (MobiusResidue2357.seedPrimes2357 ++ suffix))
    (notPoison :
      decodeWord
        (packedSplitRunResidue2357Seeded number suffix) ≠ .poison) :
    output number
        (decodeWord
          (packedSplitRunResidue2357Seeded number suffix)) =
      ArithmeticFunction.moebius number := by
  have decoded :
      decodeWord
          (packedSplitRunResidue2357Seeded number suffix) =
        .valid
          (splitRun
            (MobiusResidue2357.residueSeed2357 number)
            (rowSplitEvents number suffix)) := by
    simpa [packedSplitRunResidue2357Seeded] using
      (decodeWord_packedSplitRun_eq_valid_of_ne_poison
        (support := MobiusResidue2357.residueSeed2357 number)
        (rowSplitEvents number suffix)
        (MobiusResidue2357.residueSeed2357_product_lt_productRadix number)
        (MobiusResidue2357.residueSeed2357_count_lt_countRadix number)
        notPoison)
  rw [decoded, output, splitRun_eq_inlineRun,
    inlineRun_rowSplitEvents,
    ← MobiusResidue2357.fold_prefix_suffix_eq_residueSeed2357]
  exact roster.finalize_foldSupport_eq_moebius

/-- The p11-seeded nonpoison packed algorithm computes Mathlib's Möbius
function for a complete source roster. -/
theorem output_decodeWord_packedSplitRunResidue235711Seeded_eq_moebius
    {number : Nat} {suffix : List Nat}
    (roster :
      CompletePrimeRoster number
        (MobiusResidue235711.seedPrimes235711 ++ suffix))
    (notPoison :
      decodeWord
        (packedSplitRunResidue235711Seeded number suffix) ≠ .poison) :
    output number
        (decodeWord
          (packedSplitRunResidue235711Seeded number suffix)) =
      ArithmeticFunction.moebius number := by
  have decoded :
      decodeWord
          (packedSplitRunResidue235711Seeded number suffix) =
        .valid
          (splitRun
            (MobiusResidue235711.residueSeed235711 number)
            (rowSplitEvents number suffix)) := by
    simpa [packedSplitRunResidue235711Seeded] using
      (decodeWord_packedSplitRun_eq_valid_of_ne_poison
        (support := MobiusResidue235711.residueSeed235711 number)
        (rowSplitEvents number suffix)
        (MobiusResidue235711.residueSeed235711_product_lt_productRadix number)
        (MobiusResidue235711.residueSeed235711_count_lt_countRadix number)
        notPoison)
  rw [decoded, output, splitRun_eq_inlineRun,
    inlineRun_rowSplitEvents,
    ← MobiusResidue235711.fold_prefix_suffix_eq_residueSeed235711]
  exact roster.finalize_foldSupport_eq_moebius

/-- The p13-seeded nonpoison packed algorithm computes Mathlib's Möbius
function for a complete source roster. -/
theorem output_decodeWord_packedSplitRunResidue23571113Seeded_eq_moebius
    {number : Nat} {suffix : List Nat}
    (roster :
      CompletePrimeRoster number
        (MobiusResidue23571113.seedPrimes23571113 ++ suffix))
    (notPoison :
      decodeWord
        (packedSplitRunResidue23571113Seeded number suffix) ≠ .poison) :
    output number
        (decodeWord
          (packedSplitRunResidue23571113Seeded number suffix)) =
      ArithmeticFunction.moebius number := by
  have decoded :
      decodeWord
          (packedSplitRunResidue23571113Seeded number suffix) =
        .valid
          (splitRun
            (MobiusResidue23571113.residueSeed23571113 number)
            (rowSplitEvents number suffix)) := by
    simpa [packedSplitRunResidue23571113Seeded] using
      (decodeWord_packedSplitRun_eq_valid_of_ne_poison
        (support := MobiusResidue23571113.residueSeed23571113 number)
        (rowSplitEvents number suffix)
        (MobiusResidue23571113.residueSeed23571113_product_lt_productRadix
          number)
        (MobiusResidue23571113.residueSeed23571113_count_lt_countRadix
          number)
        notPoison)
  rw [decoded, output, splitRun_eq_inlineRun,
    inlineRun_rowSplitEvents,
    ←
      MobiusResidue23571113.fold_prefix_suffix_eq_residueSeed23571113]
  exact roster.finalize_foldSupport_eq_moebius

#print axioms
  output_decodeWord_packedSplitRunResidue2357Seeded_eq_moebius
#print axioms
  output_decodeWord_packedSplitRunResidue235711Seeded_eq_moebius
#print axioms
  output_decodeWord_packedSplitRunResidue23571113Seeded_eq_moebius

end SparkInterval.TernaryGoldbach.MobiusQualificationSeededRefinement
