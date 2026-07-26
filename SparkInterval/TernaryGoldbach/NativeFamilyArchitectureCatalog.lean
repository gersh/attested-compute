/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureRegistry

/-!
# Closed architecture catalog for every native-generated dependency family

The last fresh `#print axioms` for
`Math.Problems.TernaryGoldbach.ternary_goldbach` contained 1,371
compiler-generated native roots.  They came from 1,214 source decisions in
the 15 closed families below.  This module records that grouping in Lean and
binds every family to the one fixed aggregate architecture invocation.

This is routing metadata, not a proof that any decision is true.  The
aggregate invocation is currently fail closed.  A family-specific downstream
adapter must additionally provide:

* its exact, closed decision bundle;
* checker acceptance implies every source proposition;
* executable/compiler/loader/ISA refinement to that exact checker; and
* an installed reviewed run and accepted confidential-compute receipt.

For compact ordinary certificates, none of those architecture assumptions is
needed: an untrusted generator may produce an artifact which Lean checks
locally.  The aggregate route exists for the cases where even replaying the
checker would be prohibitively expensive.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.NativeFamilyArchitectureCatalog

open SparkInterval.Execution.Architecture

/-- The 15 native-generated families in the pinned capstone trust snapshot.

The constructors are mathematical/computational family identities.  They are
not propositions and cannot be extended by a receipt caller. -/
inductive NativeFamily where
  | analyticNTChebyshev
  | analyticNTLargeSieve
  | helfgottCertificates
  | ternaryGoldbachArithmetic
  | chapter14MinorArcs
  | meanValueFloorGrid
  | littleMertensLiouville
  | helfgottAnalyticIntervals
  | helfgottSection24Head
  | chirreHelfgottA6
  | ramareLittleMertens
  | vinogradovFiniteIntervals
  | rosserSchoenfeld
  | standaloneTGNative
  | ramareProductionFolds
  deriving Repr, DecidableEq, BEq

namespace NativeFamily

/-- Complete constructor roster, in the same order as the pinned JSON
family catalog. -/
def all : List NativeFamily :=
  [.analyticNTChebyshev, .analyticNTLargeSieve, .helfgottCertificates,
    .ternaryGoldbachArithmetic, .chapter14MinorArcs,
    .meanValueFloorGrid, .littleMertensLiouville,
    .helfgottAnalyticIntervals, .helfgottSection24Head,
    .chirreHelfgottA6, .ramareLittleMertens,
    .vinogradovFiniteIntervals, .rosserSchoenfeld,
    .standaloneTGNative, .ramareProductionFolds]

/-- Stable human/tool-facing family identifier. -/
def catalogId : NativeFamily → String
  | .analyticNTChebyshev => "analyticnt-chebyshev"
  | .analyticNTLargeSieve => "analyticnt-large-sieve"
  | .helfgottCertificates => "helfgott-certificates"
  | .ternaryGoldbachArithmetic => "ternary-goldbach-arithmetic-certs"
  | .chapter14MinorArcs => "chapter14-minor-arcs"
  | .meanValueFloorGrid => "mean-value-floor-grid"
  | .littleMertensLiouville => "little-mertens-liouville"
  | .helfgottAnalyticIntervals => "helfgott-analytic-intervals"
  | .helfgottSection24Head => "helfgott-section24-head"
  | .chirreHelfgottA6 => "chirre-helfgott-a6"
  | .ramareLittleMertens => "ramare-little-mertens"
  | .vinogradovFiniteIntervals => "vinogradov-finite-intervals"
  | .rosserSchoenfeld => "rosser-schoenfeld"
  | .standaloneTGNative => "standalone-tg-native"
  | .ramareProductionFolds => "ramare-production-folds"

/-- Compiler-generated roots in the last fresh capstone axiom print. -/
def generatedRootCount : NativeFamily → Nat
  | .analyticNTChebyshev => 3
  | .analyticNTLargeSieve => 18
  | .helfgottCertificates => 4
  | .ternaryGoldbachArithmetic => 7
  | .chapter14MinorArcs => 34
  | .meanValueFloorGrid => 3
  | .littleMertensLiouville => 2
  | .helfgottAnalyticIntervals => 202
  | .helfgottSection24Head => 1
  | .chirreHelfgottA6 => 2
  | .ramareLittleMertens => 1
  | .vinogradovFiniteIntervals => 55
  | .rosserSchoenfeld => 1025
  | .standaloneTGNative => 11
  | .ramareProductionFolds => 3

/-- Source decisions which produced those generated roots.

Several source decisions elaborate to more than one compiler-generated
native axiom.  Discharging the source proposition retires all such generated
children together. -/
def sourceDecisionCount : NativeFamily → Nat
  | .analyticNTChebyshev => 3
  | .analyticNTLargeSieve => 18
  | .helfgottCertificates => 4
  | .ternaryGoldbachArithmetic => 7
  | .chapter14MinorArcs => 19
  | .meanValueFloorGrid => 3
  | .littleMertensLiouville => 2
  | .helfgottAnalyticIntervals => 60
  | .helfgottSection24Head => 1
  | .chirreHelfgottA6 => 2
  | .ramareLittleMertens => 1
  | .vinogradovFiniteIntervals => 55
  | .rosserSchoenfeld => 1025
  | .standaloneTGNative => 11
  | .ramareProductionFolds => 3

/-- Every family uses the same closed aggregate physical identity.

This does not identify their checkers or propositions.  Those remain fixed
by separate family adapters above this registry. -/
def aggregateInvocation (_family : NativeFamily) :
    RegisteredArchitectureInvocation :=
  .nativeGeneratedAggregateProductionV1

/-- Ordinary certificate replay is the preferred trust-minimizing route for
all families except the three measured 100M/140M Ramaré folds. -/
def ordinaryCertificatePreferred : NativeFamily → Bool
  | .ramareProductionFolds => false
  | _ => true

/-- The long Ramaré family also retains a separately reviewed physical
invocation so it can be deployed independently of the aggregate portfolio. -/
def specializedInvocation :
    NativeFamily → Option RegisteredArchitectureInvocation
  | .ramareProductionFolds => some .ramareProductionFoldsCompactV1
  | _ => none

/-- The pinned catalog contains exactly 15 families. -/
theorem all_length : all.length = 15 := by
  rfl

/-- The family counts cover every one of the 1,371 generated roots. -/
theorem generatedRootCount_sum :
    (all.map generatedRootCount).sum = 1371 := by
  rfl

/-- The generated roots arise from exactly 1,214 source decisions. -/
theorem sourceDecisionCount_sum :
    (all.map sourceDecisionCount).sum = 1214 := by
  rfl

/-- No family can redirect the aggregate route to an external-atom
campaign. -/
theorem aggregateInvocation_claimKind (family : NativeFamily) :
    family.aggregateInvocation.claimKind =
      .nativeGeneratedAggregate := by
  cases family <;> rfl

/-- The aggregate invocation itself carries no application proposition or
external-atom tag. -/
theorem aggregateInvocation_claims (family : NativeFamily) :
    family.aggregateInvocation.claims = [] := by
  cases family <;> rfl

/-- The aggregate terminal process is the confidential CPU finalizer which
must verify its complete signed CPU/GPU child-receipt graph. -/
theorem aggregateInvocation_placement (family : NativeFamily) :
    family.aggregateInvocation.placement =
      .h100ProducersAzureCPUFinalizer := by
  cases family <;> rfl

/-- The reviewed aggregate branch is deliberately unavailable until the
fixed executable, formal refinement, and production receipt are installed. -/
theorem aggregateInvocation_currently_uninstalled (family : NativeFamily) :
    family.aggregateInvocation.reviewedRun = none := by
  cases family <;> rfl

end NativeFamily

end SparkInterval.TernaryGoldbach.NativeFamilyArchitectureCatalog
