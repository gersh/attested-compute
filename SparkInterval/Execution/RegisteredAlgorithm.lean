/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.Binary64
import SparkInterval.Certificate.SHA256
import SparkInterval.Dirichlet.PlattTheorem71Contract
import SparkInterval.Execution.Statement
import SparkInterval.Generated.CDEMAbelProduction
import SparkInterval.Generated.PlattHeadQ128
import SparkInterval.PTX.Generator
import SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence
import SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate
import SparkInterval.TernaryGoldbach.GoldbachSourceSemantics
import SparkInterval.TernaryGoldbach.Goldbach10Pow27CampaignSemantics
import SparkInterval.Execution.Goldbach10Pow27TerminalPins
import SparkInterval.Execution.HistoricalGoldbachTerminalPins
import SparkInterval.Execution.ProductionDeploymentPins
import SparkInterval.TernaryGoldbach.HurstSourceSemantics
import SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate
import SparkInterval.TernaryGoldbach.RamareNativeFoldContracts
import SparkInterval.TernaryGoldbach.Prop1224SourceSemantics
import SparkInterval.TernaryGoldbach.R2StarSourceSemantics
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.V2Adapter
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.Wire
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultSemantics
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Run
import SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics
import SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics
import SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics
import Mathlib.Data.Nat.Pairing
import Std.Data.String.ToNat

/-!
# Closed registry of certificate-addressable algorithm semantics

An accepted signature or hardware attestation must never be allowed to unlock
an arbitrary proposition supplied by a caller.  This module therefore uses a
closed inductive registry.  Each constructor has library-defined identity,
parsing, and mathematical execution semantics.

The first registered algorithm is an intentionally small end-to-end example:
an integer cube-accumulation loop followed by one division by three.  At its
closed registered bound, Lean proves that this machine algorithm equals the
exact rational sum

`sum (x = 0 .. upper) (x^3 / 3)`.

Adding a production algorithm requires an audited source change adding another
constructor and its fixed `Runs` equation to this closed registry.  A
certificate contains only hashes and returned bytes; a
`RegisteredInvocation` supplies their canonical preimages to Lean and checks
all of them before the trusted boundary can expose `Runs`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate
open SparkInterval.PTX

/-- Algorithms whose execution meaning is fixed by this library.

This is deliberately not a structure with a caller-provided `Prop` field.
Such a structure would let a caller choose `False` as the alleged semantics
and would make an accepted certificate logically explosive. -/
inductive RegisteredAlgorithm where
  /-- Accumulate cubes through `upper`, then divide the total by three. -/
  | cubicSumDivThreeV1
  /-- One formally generated `sm_90` PTX row returning the interval [1,1]. -/
  | h100FormalPtxConstantOneV1
  /-- Fixed-certificate CDEM replacement-table Abel recurrence scan. -/
  | cdemTableAbelExactScanV2
  /-- One shared source-scale Hurst scan for four finite residuals. -/
  | hurstSharedFourResidualV2
  /-- Two-pass prime-power/Q64 verification of CH25 Lemma 9.2. -/
  | ch25PsiLemma92V1
  /-- Gap-free Q32 verification of Ramaré--Zúñiga Lemma 6.2. -/
  | ramareZunigaLemma62V1
  /-- Directed MPFR/GMP verification of Helfgott Proposition 12.2.4. -/
  | helfgottProp1224MpfrV1
  /-- Pinned FLINT/Arb replay of the CH25 Lemma A.7 rectangle boundary. -/
  | ch25A7BoundaryV1
  /-- Exact FLINT/Q128 Platt zero head through height `20,000`. -/
  | plattHead2e4V1
  /-- Exact two-branch source contract for Platt's Dirichlet Theorem 7.1. -/
  | plattDirichletTheorem71V1
  /-- Exact Platt--Trudgian finite-RH campaign through height `3·10^12`. -/
  | plattTrudgianFiniteRHV1
  /-- Exact Helfgott--Platt binary-Goldbach plus prime-ladder campaign. -/
  | helfgottPlattGoldbachV1
  /-- Distinct finite binary-Goldbach plus n=45 ladder below `10^27`. -/
  | goldbach10Pow27V1
  /-- Exact finite head and Abel-anchor campaign for Helfgott (2.18). -/
  | helfgottSqrt218V1
  /-- Fixed-width V2 CPU certificate and exact SQ218R2 result envelope. -/
  | helfgottSqrt218FixedV2
  /-- Signed fixed-point interval folds for the three Ramaré production
  scans: the corrected first-Mertens seam and anchor through `10^8`, the four
  Ramaré--Zúñiga Lemma 7.1 rows through `10^8`, and the `m★` product through
  `1.4·10^8`. -/
  | ramareProductionFoldsV1
  /-- Per-integer leancompcert CompCert campaign for Platt's stronger
  little-Mertens range, `|Σ_{m≤n} μ(m)/m| ≤ 1/(2√(n+1))` for
  `5 ≤ n ≤ 7 727 068 586`. -/
  | plattStrongerRangeLiveV1
  deriving Repr, DecidableEq, BEq

namespace RegisteredAlgorithm

/-- Exact binary64 interval constant used by the registered H100 pilot. -/
def h100FormalPtxConstantOneInterval : IntervalBits := {
  lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
  hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
}

/-- The one-row, zero-variable batch compiled by the registered H100 pilot. -/
def h100FormalPtxConstantOneBatch : ReferenceBatch := {
  variableCount := 0
  expression := .const h100FormalPtxConstantOneInterval
  rowCount := 1
}

/-- Exact formal `sm_90` PTX emitted from the closed constant-one reference
batch.  These definition bytes are signed by the trusted-compute receipt; the
cubin remains a separate receipt-bound artifact. -/
def h100FormalPtxConstantOnePTX : String :=
  renderUncheckedFor .sm90 (buildModule h100FormalPtxConstantOneBatch)

/-- Canonical input bytes parsed by the formal PTX generator. -/
def h100FormalPtxConstantOneInput : String :=
  "{\"algorithm\":\"sparkinterval.binary64_interval_expr.v1\"," ++
  "\"expression\":{\"op\":\"const\",\"value\":{\"hi\":\"3ff0000000000000\"," ++
  "\"lo\":\"3ff0000000000000\"}},\"kind\":\"sparkinterval_reference_batch\"," ++
  "\"rows\":[[]],\"schema_version\":1,\"variable_count\":0}"

/-- Exact compact UTF-8 result manifest returned by the measured wrapper. -/
def h100FormalPtxConstantOneOutput : String :=
  "{\"format\":\"sparkinterval_h100_formal_ptx_pilot_result_v1\"," ++
  "\"hi\":\"3ff0000000000000\",\"lo\":\"3ff0000000000000\"," ++
  "\"row_count\":1,\"schema_version\":1,\"status\":0,\"target\":\"sm_90\"}"

/-- Exact closed input of the production CDEM Abel scan. -/
def cdemTableAbelInput : String :=
  "{\"K\":199330,\"N\":5000000000," ++
  "\"weight_scale\":1000000000000000000}"

/-- Compact canonical result admitted for the completed production scan.

`Nat.pair` is injective and has the kernel-proved inverse `Nat.unpair`; using
one canonical decimal natural avoids trusting a JSON parser in the theorem
bridge. -/
def cdemTableAbelProductionOutput : String :=
  toString (Nat.pair
    SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
    SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget)

/-- Exact closed input for the shared Hurst source campaign. -/
def hurstSharedFourResidualInput : String :=
  "{\"campaign\":\"hurst-shared-four-residual-v2\"," ++
  "\"source_lower\":1,\"source_upper_exclusive\":10000000000000001}"

/-- Exact closed input for the CH25 Lemma 9.2 psi campaign. -/
def ch25PsiLemma92Input : String :=
  "{\"campaign\":\"ch25-psi-lemma-9-2-v1\"," ++
  "\"source_lower\":1,\"source_upper\":10000000000000}"

/-- Exact closed input for the Ramaré--Zúñiga Lemma 6.2 campaign. -/
def ramareZunigaLemma62Input : String :=
  "{\"campaign\":\"ramare-zuniga-lemma-6-2-v1\"," ++
  "\"source_lower\":1,\"source_upper_exclusive\":21000000001}"

/-- Exact closed input for the three Ramaré production folds. -/
def ramareProductionFoldsInput : String :=
  "{\"campaign\":\"ramare-production-folds-v1\"," ++
  "\"first_mertens_limit\":100000000,\"lemma71_limit\":100000000," ++
  "\"mstar_limit\":140000000}"

/-- Exact closed input for the live leancompcert CompCert campaign covering
Platt's stronger little-Mertens range.

The campaign manifest is named by digest a second time here -- the first is
inside `canonicalDefinition`, hence inside `algorithmHash` -- so a substituted
manifest fails both the algorithm and the input binding. -/
def plattStrongerRangeLiveInput : String :=
  "{\"campaign\":\"platt-stronger-range-live-v1\"," ++
  "\"campaign_manifest_sha256\":" ++
  "\"6c67c2a900889087d3c1f88eed9caecf4e08ba0c40ab23e83ef316ff0d7ef0a9\"," ++
  "\"range_hi\":7727068586,\"range_lo\":5}"

/-- Exact closed input for Helfgott Proposition 12.2.4's source-rank scan. -/
def helfgottProp1224MpfrInput : String :=
  "{\"campaign\":\"helfgott-prop-12-2-4-mpfr-v1\"," ++
  "\"rank_lower\":0,\"rank_upper\":3389047618}"

/-- Exact closed input for the retained CH25 Lemma A.7 boundary replay. -/
def ch25A7BoundaryInput : String :=
  "{\"campaign\":\"ch25-a7-boundary-v1\"," ++
  "\"retained_artifact_sha256\":" ++
  "\"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29\"}"

/-- Exact reviewed digest of all 22,492 Q128 rows, including the sentinel
strictly above the cutoff. -/
def plattHead2e4AllQ128RowsDigest : String :=
  "fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca"

/-- Exact reviewed commitment of the 22,491 included source-table rows. -/
def plattHead2e4IncludedQ128RowsCommitment : String :=
  "e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7"

/-- Exact closed input for the height-20,000 Platt-head replay. -/
def plattHead2e4Input : String :=
  "{\"all_q128_rows_sha256\":\"" ++ plattHead2e4AllQ128RowsDigest ++ "\"," ++
  "\"campaign\":\"platt-head-2e4\"," ++
  "\"included_q128_rows_sha256\":\"" ++
    plattHead2e4IncludedQ128RowsCommitment ++ "\"," ++
  "\"source_height\":20000,\"source_multiplicity_count\":22491}"

/-- Exact closed input for the source-wide Platt Dirichlet Theorem 7.1
finalizer. The primitive-character count covers `q = 2, ..., 400000`; the
separate `q = 1` branch is supplied by the stronger zeta campaign. -/
def plattDirichletTheorem71Input : String :=
  "{\"campaign\":\"platt-dirichlet-theorem-7-1\"," ++
  "\"q1_source_campaign\":\"platt-trudgian-rh-3e12\"," ++
  "\"q2_to_q400000_primitive_character_count\":29565923837," ++
  "\"source_modulus_lower\":1,\"source_modulus_upper\":400000}"

/-- Exact source endpoint and multiplicity count for the PT21 campaign. -/
def plattTrudgianFiniteRHInput : String :=
  "{\"campaign\":\"platt-trudgian-rh-3e12\"," ++
  "\"multiplicity_count\":12363153437138," ++
  "\"source_height\":3000175332800}"

/-- Exact binary and ladder campaign/source-artifact identities for the
Helfgott--Platt finite Goldbach computation. Result-artifact digests are
created only by a future run and remain separately bound by its receipt. -/
def helfgottPlattGoldbachInput : String :=
  "{\"binary_artifact_kind\":\"sparkinterval.goldbach-gpu-aggregate.v1\"," ++
  "\"binary_campaign\":\"goldbach-gpu-hardened-production-65536-leaf-v2\"," ++
  "\"binary_source_identity_sha256\":" ++
  "\"9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55\"," ++
  "\"campaign\":\"helfgott-platt-goldbach-gpu-v1\"," ++
  "\"combined_artifact_kind\":\"tg_goldbach_gpu_plus_ladder_result_v1\"," ++
  "\"ladder_artifact_kind\":\"tg_goldbach_ladder_parallel_aggregate_v1\"," ++
  "\"ladder_campaign\":\"tg_goldbach_ladder_parallel_campaign_v1\"," ++
  "\"ladder_native_source_sha256\":" ++
  "\"02ffa92bca580146af32c176f8e6014f2e88d61a5e1a190114ea3ad5a524cbf6\"}"

/-- Exact closed input for the distinct finite campaign below `10^27`.
Run-produced aggregate digests are retained inside the measured finalizer
archive and bound by its signed statement rather than hard-coded here. -/
def goldbach10Pow27Input : String :=
  "{\"binary_artifact_kind\":\"sparkinterval.goldbach-gpu-aggregate.v1\"," ++
  "\"binary_campaign\":" ++
    "\"goldbach-gpu-analytic-10pow27-production-65536-leaf-v1\"," ++
  "\"binary_source_identity_sha256\":" ++
    "\"9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55\"," ++
  "\"campaign\":\"ternary-goldbach-finite-below-10pow27-v1\"," ++
  "\"combined_artifact_kind\":" ++
    "\"tg_goldbach_10pow27_gpu_plus_ladder_result_v1\"," ++
  "\"ladder_artifact_kind\":" ++
    "\"tg_goldbach_ladder_parallel_aggregate_v1\"," ++
  "\"ladder_campaign\":\"analytic_10pow27\"," ++
  "\"semantic_target_inclusive\":1000000000000000000000000000}"

/-! ## Exact production profile for the Sqrt218 operational checker -/

/-- Reviewed transcript summary required of the production typed archive. -/
def helfgottSqrt218ExpectedSummary :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.Summary := {
  anchorSlack :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedAnchorSlack
  finalPsiLower :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedFinalPsiLower
  finalWeightedUpper :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedFinalWeightedUpper
  fixedScanDigest :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedFixedScanDigest
  layoutDigest :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedLayoutDigest
  minimumHeadIndex :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedMinimumHeadIndex
  minimumHeadSlack :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedMinimumHeadSlack
  primePowerEventCount :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedPrimePowerEventCount
  prattDigest :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedPrattDigest
  primeCount :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedPrimeCount
  properPrimePowerEventCount :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedProperPrimePowerEventCount
  reusedPrimeCount :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedReusedPrimeCount
  tailPrimeCount :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedTailPrimeCount
}

/-- Exact, data-independent profile selected by the registered production
invocation.  No production archive is defined in Lean. -/
def helfgottSqrt218ProductionProfile :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.Profile := {
  bound :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.sourceCutoff
  reusedPrimeBound :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.reusedPrimeBound
  logSeedAt :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.logSeedCount
  logScale :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.fixedPointScale
  reciprocalScale :=
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.reciprocalScale
  expectedSummary := some helfgottSqrt218ExpectedSummary
}

/-- Exact closed input for the staged full-recomputation square-root Mangoldt
campaign.

Every transcript summary from the completed ordinary-kernel certificate is
part of the input preimage.  A future cloud receipt therefore cannot select a
different roster, fixed-point scan, or endpoint state while retaining this
invocation's mathematical meaning.  This V1 input does not pretend that a
future numeric-corpus digest already exists. -/
def helfgottSqrt218Input : String :=
  "{\"bound\":" ++
    toString SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.sourceCutoff ++
  ",\"claim_id\":\"helfgott-sqrt218-finite-v1\",\"expected\":{" ++
  "\"anchor_slack\":" ++
    toString SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedAnchorSlack ++
  ",\"final_psi_lower\":" ++
    toString SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedFinalPsiLower ++
  ",\"final_weighted_upper\":" ++
    toString
      SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedFinalWeightedUpper ++
  ",\"fixed_scan_sha256\":\"" ++
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedFixedScanDigest ++
  "\",\"layout_sha256\":\"" ++
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedLayoutDigest ++
  "\",\"minimum_head_n\":" ++
    toString
      SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedMinimumHeadIndex ++
  ",\"minimum_head_slack\":" ++
    toString
      SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedMinimumHeadSlack ++
  ",\"power_event_count\":" ++
    toString
      SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedPrimePowerEventCount ++
  ",\"pratt_sha256\":\"" ++
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedPrattDigest ++
  "\",\"prime_count\":" ++
    toString SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedPrimeCount ++
  ",\"proper_power_count\":" ++
    toString
      SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedProperPrimePowerEventCount ++
  ",\"reused_prime_count\":" ++
    toString
      SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedReusedPrimeCount ++
  ",\"tail_prime_count\":" ++
    toString SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.expectedTailPrimeCount ++
  "},\"kind\":\"sparkinterval.sqrt218-finite-run-input.v1\"," ++
  "\"lean_claim\":\"" ++
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.leanClaimName ++
  "\",\"log_depth\":" ++
    toString SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.logLadderDepth ++
  ",\"log_scale\":" ++
    toString SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.fixedPointScale ++
  ",\"reciprocal_scale\":" ++
    toString SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.reciprocalScale ++
  ",\"schema_version\":1,\"source_statement\":\"" ++
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.sourceStatement ++
  "\"}"

/-- Canonical decimal naturals have no sign, whitespace, separators, or
leading zeroes (except for the value zero itself). -/
def parseCanonicalNat (text : String) : Option Nat := do
  let value ← text.toNat?
  if text = toString value then
    some value
  else
    none

/-- Exact mathematical meaning of the example loop.  Division is in `ℚ`, and
the upper endpoint is included. -/
def cubicSumDivThree (upper : Nat) : ℚ :=
  ∑ x ∈ Finset.range (upper + 1), (x : ℚ) ^ 3 / 3

/-- Executable numerator loop.  `cubicNumeratorLoop count` performs exactly
`count` iterations, adding `x^3` for `x = 0, ..., count - 1`. -/
def cubicNumeratorLoop : Nat → Nat
  | 0 => 0
  | count + 1 => cubicNumeratorLoop count + count ^ 3

/-- Executable tutorial algorithm: accumulate integer cubes and divide once at
the end.  At the registered bound, divisibility by three is proved below, so
this natural-number division agrees with exact rational pointwise division. -/
def cubicSumDivThreeMachine (upper : Nat) : Nat :=
  cubicNumeratorLoop (upper + 1) / 3

/-- Stable protocol identifier signed in `RunStatement.algorithmId`. -/
def algorithmId : RegisteredAlgorithm → String
  | .cubicSumDivThreeV1 => "sparkinterval.example.cubic-sum-div-three.v1"
  | .h100FormalPtxConstantOneV1 =>
      "sparkinterval.pilot.h100-formal-ptx-constant-one.v1"
  | .cdemTableAbelExactScanV2 =>
      "sparkinterval.ternary-goldbach.cdem-table-abel.v2"
  | .hurstSharedFourResidualV2 =>
      "sparkinterval.ternary-goldbach.hurst-shared-four-residual.v2"
  | .ch25PsiLemma92V1 =>
      "sparkinterval.ternary-goldbach.ch25-psi-lemma-9-2.v1"
  | .ramareZunigaLemma62V1 =>
      "sparkinterval.ternary-goldbach.ramare-zuniga-lemma-6-2.v1"
  | .helfgottProp1224MpfrV1 =>
      "sparkinterval.ternary-goldbach.helfgott-proposition-12-2-4-mpfr.v1"
  | .ch25A7BoundaryV1 =>
      "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1"
  | .plattHead2e4V1 =>
      "sparkinterval.ternary-goldbach.platt-head-2e4.v1"
  | .plattDirichletTheorem71V1 =>
      "sparkinterval.ternary-goldbach.platt-dirichlet-theorem-7-1.v1"
  | .plattTrudgianFiniteRHV1 =>
      "sparkinterval.ternary-goldbach.platt-trudgian-finite-rh.v1"
  | .helfgottPlattGoldbachV1 =>
      "sparkinterval.ternary-goldbach.helfgott-platt-finite-goldbach.v1"
  | .goldbach10Pow27V1 =>
      "sparkinterval.ternary-goldbach.finite-below-10pow27.v1"
  | .helfgottSqrt218V1 =>
      "sparkinterval.ternary-goldbach.sqrt218-finite.v1"
  | .helfgottSqrt218FixedV2 =>
      "sparkinterval.ternary-goldbach.sqrt218-fixed-v2.v1"
  | .ramareProductionFoldsV1 =>
      "sparkinterval.ternary-goldbach.ramare-production-folds.v1"
  | .plattStrongerRangeLiveV1 =>
      "sparkinterval.leancompcert.platt-stronger-range-live.v1"

/-- Canonical, human-reviewable definition bytes whose digest is signed as
`RunStatement.algorithmHash`.

This text is a protocol artifact.  After the first accepted receipt, changing
any execution detail requires a new registry version and therefore a new
digest.  A staged entry with no admitted receipt may be narrowed and repinned
before release. -/
def canonicalDefinition : RegisteredAlgorithm → String
  | .cubicSumDivThreeV1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=cubic-sum-div-three\n" ++
      "input=canonical-decimal-natural-upper-inclusive\n" ++
      "output=canonical-decimal-natural\n" ++
      "arithmetic=natural-accumulator-with-u64-proof-on-registered-domain\n" ++
      "division=natural-division-by-3-after-total\n" ++
      "semantics=loop-x-from-0-through-upper-add-x-cubed-then-divide-total"
  | .h100FormalPtxConstantOneV1 => h100FormalPtxConstantOnePTX
  | .cdemTableAbelExactScanV2 =>
      "sparkinterval.registered-algorithm.v2\n" ++
      "name=ternary-goldbach-cdem-table-abel\n" ++
      "producer=reference/tg_cdem_abel_measured_workload.cpp\n" ++
      "semantics=checked-gap-free-local-floorjump-recurrence-certificate-with-local-fold-evidence\n" ++
      "certificate=SparkInterval.Generated.CDEMAbelProduction.certificate\n" ++
      "certificate-transcript-sha256=2a1d551dee2f5e8997e8e2a77a587cb6cf53b93b32854f943591163db2460123\n" ++
      "certificate-lean-source-sha256=c31fe5bdb3444d53b484dbc14592d1509f284378e75ba356a006d68b952f2ee9\n" ++
      "artifact=TG-CDEM-ABEL-ARTIFACT-V1-complete-recurrence-stream\n" ++
      "artifact-binding=trace-recomputes-artifact-after-complete-independent-replay\n" ++
      "output=false-or-canonical-decimal-nat-pair-u-v\n" ++
      "pairing=mathlib-nat-pair\n" ++
      "weight-scale=1000000000000000000\n" ++
      "signed-rounding=ceil-positive-floor-negative\n" ++
      "sqrt-rounding=least-q-with-q-squared-times-n-at-least-scale-squared"
  | .hurstSharedFourResidualV2 =>
      "sparkinterval.registered-algorithm.v2\n" ++
      "name=ternary-goldbach-hurst-shared-four-residual\n" ++
      "producer=reference/tg_hurst_residual_shard.cpp\n" ++
      "semantics=gap-free-two-pass-mobius-prefix-and-exact-directed-guard-checks\n" ++
      "evidence=local-primitive-row-deltas-plus-local-state-guard-decisions\n" ++
      "global-prefix=derived-in-lean-from-root-zero-and-row-delta-recurrence\n" ++
      "little-q96-tracking=active-through-1000000000000-zero-after\n" ++
      "source-range=[1,10000000000000001)\n" ++
      "state=mertens-squarefree-little-lower-q96-little-upper-q96\n" ++
      "hurst-guard=1000000*abs(M)^2<=571^2*n-for-n>=33\n" ++
      "squarefree-density=607927101854026628/10^18<=6/pi^2<=607927101854026629/10^18\n" ++
      "squarefree-b1=151/2000-after-9243;check-value-at-n>=9243-and-right-limit-at-n+1\n" ++
      "squarefree-b2=57/2000-after-438429;check-value-at-n>=438429-and-right-limit-at-n+1\n" ++
      "little-2-11=right*abs(q96)^2<=2*2^192-for-1<=n<=10^12\n" ++
      "little-stronger=4*right*abs(q96)^2<=2^192-for-3<=n<7727068587\n" ++
      "output=false-or-true-with-local-replay-evidence"
  | .ch25PsiLemma92V1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-ch25-psi-lemma-9-2\n" ++
      "producer=reference/tg_psi_residual_shard.cpp\n" ++
      "semantics=gap-free-two-pass-prime-power-q64-endpoint-guards\n" ++
      "source-range=[1,10000000000000]\n" ++
      "state=psi-lower-q64-psi-upper-q64\n" ++
      "output=false-or-true-with-prime-power-gap-log-and-integer-guard-evidence"
  | .ramareZunigaLemma62V1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-ramare-zuniga-lemma-6-2\n" ++
      "producer=gpu/platform/h100/h100_tg_r2star_chunk_runner.cpp\n" ++
      "semantics=gap-free-q32-r2star-prefix-enclosures-and-exact-squared-endpoint-guards\n" ++
      "source-range=[1,21000000001)\n" ++
      "coefficient=(vonMangoldt*vonMangoldt)(n)-vonMangoldt(n)*log(n)+2*eulerMascheroniConstant\n" ++
      "scale=2^32\n" ++
      "bound=(193/100)*sqrt(x)*log(x)\n" ++
      "output=false-or-true-with-full-source-evidence"
  | .helfgottProp1224MpfrV1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-helfgott-proposition-12-2-4\n" ++
      "producer=reference/tg_prop1224_mpfr_shard.cpp\n" ++
      "semantics=gap-free-independent-q-directed-mpfr-gmp-row-verification\n" ++
      "source-rank-range=[0,3389047618)\n" ++
      "source-q-range=q<3300000000-or-(210-divides-q-and-q<22000000000)\n" ++
      "source-realization=exact-lean-ramareG-cE-f1-window-and-error-claim\n" ++
      "output=false-or-true-with-full-source-evidence"
  | .ch25A7BoundaryV1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-ch25-lemma-a7-boundary\n" ++
      "producer=tg_verifier/a7_flint.py\n" ++
      "semantics=pinned-full-flint-arb-boundary-replay-with-rational-box-evidence\n" ++
      "source-rectangle=(-3,5)+i(-4,4)-frontier\n" ++
      "raw-function=-zeta-prime(s)/zeta(s)-1/(s-1)+1/(s+2)\n" ++
      "bound=349/250\n" ++
      "retained-artifact-sha256=" ++
      "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29\n" ++
      "source-realization=external-flint-arb-boxes-contain-mathlib-riemannZeta-expression\n" ++
      "output=false-or-true-with-boundary-evidence"
  | .plattHead2e4V1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-platt-head-2e4\n" ++
      "producer=tg_verifier/zeta_zero_campaign.py\n" ++
      "semantics=complete-indexed-flint-platt-head-replay-to-literal-q128-table\n" ++
      "source-height=20000\n" ++
      "source-multiplicity-count=22491\n" ++
      "all-q128-rows-sha256=" ++ plattHead2e4AllQ128RowsDigest ++ "\n" ++
      "included-q128-rows-sha256=" ++
        plattHead2e4IncludedQ128RowsCommitment ++ "\n" ++
      "source-realization=external-endpoint-enclosures-hardy-z-bridge-and-turing-count\n" ++
      "output=false-or-true-with-literal-q128-checked-head-evidence"
  | .plattDirichletTheorem71V1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-platt-dirichlet-theorem-7-1\n" ++
      "producer=tools/tg_dirichlet_campaign.py+tools/tg_dirichlet_flint_backend.py\n" ++
      "semantics=complete-source-roster-even-and-odd-grh-verification-at-platt-heights\n" ++
      "source-modulus-range=[1,400000]\n" ++
      "q2-to-q400000-primitive-character-count=29565923837\n" ++
      "q1-source-campaign=platt-trudgian-rh-3e12\n" ++
      "source-realization=external-roster-completed-l-hardy-zero-brackets-conjugation-and-total-zero-count\n" ++
      "finalizer-target=azure-sevsnp-cpu-after-h100-and-cpu-branches\n" ++
      "output=false-or-true-with-two-branch-source-evidence"
  | .plattTrudgianFiniteRHV1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-platt-trudgian-finite-rh\n" ++
      "producer=tg_verifier/platt_zeta_campaign.py\n" ++
      "semantics=fixed-index-flint-platt-turing-chunked-zero-isolation-and-global-count\n" ++
      "source-height=3000175332800\n" ++
      "source-multiplicity-count=12363153437138\n" ++
      "source-realization=external-endpoint-enclosures-hardy-z-bridge-and-turing-count\n" ++
      "output=false-or-true-with-source-evidence"
  | .helfgottPlattGoldbachV1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-helfgott-platt-finite-goldbach\n" ++
      "producer=tg_verifier/goldbach_gpu_campaign.py+tg_verifier/goldbach_native_ladder.py+tg_verifier/goldbach_campaign.py\n" ++
      "semantics=complete-binary-goldbach-plus-checked-prime-ladder-source-evidence\n" ++
      "binary-campaign=goldbach-gpu-hardened-production-65536-leaf-v2\n" ++
      "binary-artifact=sparkinterval.goldbach-gpu-aggregate.v1\n" ++
      "binary-source-identity=9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55\n" ++
      "ladder-campaign=tg_goldbach_ladder_parallel_campaign_v1\n" ++
      "ladder-artifact=tg_goldbach_ladder_parallel_aggregate_v1\n" ++
      "ladder-native-source=02ffa92bca580146af32c176f8e6014f2e88d61a5e1a190114ea3ad5a524cbf6\n" ++
      "combined-artifact=tg_goldbach_gpu_plus_ladder_result_v1\n" ++
      "finalizer-target=azure-sevsnp-cpu-after-h100-binary-and-cpu-ladder-branches\n" ++
      "source-realization=external-branch-artifacts-to-checked-source-evidence\n" ++
      "output=false-or-true-with-checked-source-evidence"
  | .goldbach10Pow27V1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-finite-below-10pow27\n" ++
      "producer=tg_verifier/goldbach_gpu_campaign.py+tg_verifier/goldbach_native_ladder.py+tg_verifier/goldbach_10pow27_campaign.py+tools/tg_goldbach_10pow27_finalizer.py\n" ++
      "semantics=complete-word-indexed-lowered-binary-goldbach-coverage-plus-checked-n45-prime-ladder-evidence\n" ++
      "binary-campaign=goldbach-gpu-analytic-10pow27-production-65536-leaf-v1\n" ++
      "binary-artifact=sparkinterval.goldbach-gpu-aggregate.v1\n" ++
      "binary-source-identity=9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55\n" ++
      "ladder-campaign=analytic_10pow27\n" ++
      "ladder-artifact=tg_goldbach_ladder_parallel_aggregate_v1\n" ++
      "combined-artifact=tg_goldbach_10pow27_gpu_plus_ladder_result_v1\n" ++
      "finalizer-target=azure-sevsnp-cpu-after-h100-binary-and-cpu-ladder-branches\n" ++
      "source-realization=external-branch-artifacts-to-exact-word-campaign-and-checked-ladder-evidence\n" ++
      "output=false-or-true-with-checked-campaign-evidence"
  | .helfgottSqrt218V1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-sqrt218-finite\n" ++
      "bound=2000000\n" ++
      "prime-roster=complete-eratosthenes-and-lucas-pratt-witnesses\n" ++
      "prime-powers=all-powers-p^k-with-k-positive-and-p^k-at-most-bound\n" ++
      "log-enclosure=scale-2^48-seed-30-rational-ladder-depth-14\n" ++
      "reciprocal-sqrt=scale-2^30-rational-lower-and-upper-bounds\n" ++
      "scan=ordered-prime-power-fixed-point-prefix-with-every-head-guard\n" ++
      "terminal=exact-final-state-and-endpoint-abel-anchor\n" ++
      "result=canonical-ascii-true-only-after-independent-full-archive-replay"
  | .helfgottSqrt218FixedV2 =>
      "sparkinterval.registered-algorithm.v2\n" ++
      "name=ternary-goldbach-sqrt218-fixed-v2\n" ++
      "input=exact-reviewed-SQ218V2-binary-certificate\n" ++
      "input-binding=statement-input-sha256-plus-reviewed-byte-length\n" ++
      "decoder=canonical-big-endian-fixed-width-exact-eof\n" ++
      "semantics=complete-V2-roster-layout-log-event-fold-and-anchor-check\n" ++
      "result=false-or-canonical-ascii-exact-hex-envelope-of-120-byte-SQ218R2-record\n" ++
      "success-binding=result-state-input-length-and-input-sha256"
  | .ramareProductionFoldsV1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=ternary-goldbach-ramare-production-folds\n" ++
      "producer=reference/tg_ramare_production_folds.cpp\n" ++
      "semantics=signed-fixed-point-interval-folds-with-exact-integer-guards\n" ++
      "first-mertens-range=[144913,100000000]\n" ++
      "lemma71-range=[1,100000000]\n" ++
      "mstar-range=[2,140000000]\n" ++
      "scales=2^48-first-mertens,2^32-lemma71,2^96-mstar-product\n" ++
      "output=false-or-true-with-finite-fold-evidence"
  | .plattStrongerRangeLiveV1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=platt-stronger-range-live\n" ++
      "producer=leancompcert\n" ++
      "program=Ports.ArraySegSieve.mobiusLiveProgram\n" ++
      "reduced-family=MathExtras.Reductions.PlattStrongerRangeNatFamily\n" ++
      "range=[5,7727068586]\n" ++
      "windows=10\n" ++
      "manifest-sha256=6c67c2a900889087d3c1f88eed9caecf4e08ba0c40ab23e83ef316ff0d7ef0a9\n" ++
      "manifest-bytes=4528\n" ++
      "compcert-version=3.17\n" ++
      "compcert-target=x86_64-linux\n" ++
      "link=static-freestanding-no-libc\n" ++
      "semantics=AProgram.evalCC_compile\n" ++
      "success=every-window-exit-status-zero\n" ++
      "output=false-or-true\n"

/-- Source-reviewed protocol digest of the fixed algorithm definition.

Keeping the literal here makes the closed invocation checker a small kernel
reduction.  The receipt importer independently recomputes the SHA-256 from
`canonicalDefinition`; that preimage binding is part of the disclosed
certificate/import trust boundary rather than a multi-gigabyte theorem proof. -/
def algorithmHash (algorithm : RegisteredAlgorithm) : Digest :=
  match algorithm with
  | .cubicSumDivThreeV1 =>
      "90b02215eb8e4d387aa7126923b4b7591ea4ed60d16fd8353028ce76994986ca"
  | .h100FormalPtxConstantOneV1 =>
      "2ee3f3045a1ff97b07a697cea602b9bc9bba3278bd5494c50684f3ed29cad582"
  | .cdemTableAbelExactScanV2 =>
      "f924a59b7569a9407b78bbbe5931c03fa76532b7dd88c64401263402ac4575b0"
  | .hurstSharedFourResidualV2 =>
      "d5fa24d80d95216208ff8e8bbacb42ec181966b40e6a577dae26d585c09df5aa"
  | .ch25PsiLemma92V1 =>
      "b16368f84ca70c2a3e7b9b9814c7e098e79c0c3bb137a51b85851cfd526753b0"
  | .ramareZunigaLemma62V1 =>
      "1c95ab10e8f25ed7f87739bc2ea13190bb32e520272f05a3611d13b95e7f9d9c"
  | .helfgottProp1224MpfrV1 =>
      "184e8f8f60f511868d39a7a1ab7599a4b725415892e99c8fd84a35f8bf6c38a1"
  | .ch25A7BoundaryV1 =>
      "340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa"
  | .plattHead2e4V1 =>
      "de33cb0d8db40a6b28c32605d9014ca8d593e446e4d1e3390402ea45c13f29ca"
  | .plattDirichletTheorem71V1 =>
      "7b956d4a04403f9ba32fa2908a72cfa1483928991b3fa478d4bcfd79b089f33c"
  | .plattTrudgianFiniteRHV1 =>
      "3f162d7b531d7bd1aca532f13ee8460c6e86cef315b38da6849b74b422906d5f"
  | .helfgottPlattGoldbachV1 =>
      "93652e39a76fff96f8463f19f000ddaa15e2fafec4e0b5ea3a9870e2be8f8832"
  | .goldbach10Pow27V1 =>
      "23ade6c8a6069feec88b20c24ad118a2ed8b93f16d673f20591caa7cbdf167c9"
  | .helfgottSqrt218V1 =>
      "cd24ed4d5f0ee907d28c27dd5aadededeb80e5497024c3e256352ea2fddfd4c5"
  | .helfgottSqrt218FixedV2 =>
      "cefa3f3eccfc3505923d1c37f600766127473a1a8a097b2e9097cede014011d6"
  | .ramareProductionFoldsV1 =>
      "9f5ffa335e068542b0838ee221626c8b4c4bb8cc0c8bb0e4b13c6c41f4fcc099"
  | .plattStrongerRangeLiveV1 =>
      "7080938bc1af83e75b1c273e6388916741250422d964ac734e5b638ab61386c2"

/-- Executable audit check for the source-reviewed algorithm digest.  The
closed invocation selector includes this check through
`sourceBindingDiagnosticCheck`. -/
def algorithmHashDiagnosticCheck (algorithm : RegisteredAlgorithm) : Bool :=
  SHA256.digestString algorithm.canonicalDefinition == algorithm.algorithmHash

/-- Canonical parameter bytes bound by the signed statement. -/
def canonicalParameters : RegisteredAlgorithm → String
  | .cubicSumDivThreeV1 =>
      "{\"accumulator\":\"u64-no-wrap\",\"divide_after_sum\":true," ++
      "\"divisor\":3,\"inclusive\":true}"
  | .h100FormalPtxConstantOneV1 =>
      "{\"result_format\":\"sparkinterval_h100_formal_ptx_pilot_result_v1\"," ++
      "\"row_count\":1,\"target\":\"sm_90\",\"variable_count\":0}"
  | .cdemTableAbelExactScanV2 =>
      "{\"a\":5000000001,\"g_zero_override\":true," ++
      "\"mobius\":\"linear-sieve-exact\"," ++
      "\"output_encoding\":\"nat_pair_decimal\"," ++
      "\"sqrt_rounding\":\"exact_square_test\"}"
  | .hurstSharedFourResidualV2 =>
      "{\"little_scale_bits\":96,\"receipt_leaves\":10000," ++
      "\"replay\":\"independent-two-pass\"," ++
      "\"row_domain\":\"sparkinterval.tg.hurst-residual-mobius-rows.v1\"," ++
      "\"squarefree_threshold_endpoints\":\"inclusive_value_and_right_limit\"}"
  | .ch25PsiLemma92V1 =>
      "{\"crlibm_commit\":\"eb3063791aa75bc9705b49283bf14250465220a7\"," ++
      "\"event_count\":346065767406," ++
      "\"primesieve_commit\":\"4f85384851da23c36c01ec01ef85b5d9d246e556\"," ++
      "\"q64_scale_bits\":64,\"replay\":\"independent-two-pass\"," ++
      "\"row_domain\":\"sparkinterval.tg.psi-prime-power-rows.v1\"}"
  | .ramareZunigaLemma62V1 =>
      "{\"chunk_span\":1000000,\"gamma_lower_q32\":2479051107," ++
      "\"gamma_upper_q32\":2479194040,\"harmonic_terms\":100000," ++
      "\"log_series_terms\":20," ++
      "\"replay\":\"independent_cpp_full_row_exact_v1\"," ++
      "\"scale_bits\":32}"
  | .helfgottProp1224MpfrV1 =>
      "{\"leaf_rows\":262144,\"mpfr_version\":\"4.2.1\"," ++
      "\"precision_bits\":192," ++
      "\"row_domain\":\"sparkinterval.tg.prop1224-mpfr-directed-rows.v1\"," ++
      "\"source_realization\":\"external-mpfr-gmp-exact-lean-row\"}"
  | .ch25A7BoundaryV1 =>
      "{\"flint_release\":30600,\"flint_version\":\"3.6.0\"," ++
      "\"leaf_count\":16191,\"python_flint_version\":\"0.9.0\"," ++
      "\"series_cap\":4,\"series_length\":2,\"threads\":1}"
  | .plattHead2e4V1 =>
      "{\"flint_release\":30600,\"flint_threads\":1," ++
      "\"flint_version\":\"3.6.0\",\"precision_bits\":96," ++
      "\"python_flint_version\":\"0.9.0\",\"q128_scale_bits\":128}"
  | .plattDirichletTheorem71V1 =>
      "{\"even_height\":\"max(10^8/q,200+7.5*10^7/q)\"," ++
      "\"odd_height\":\"max(10^8/q,200+3.75*10^7/q)\"," ++
      "\"q1_source_campaign\":\"platt-trudgian-rh-3e12\"," ++
      "\"source_evidence\":\"PlattTheorem71SourceEvidence\"}"
  | .plattTrudgianFiniteRHV1 =>
      "{\"flint_commit\":\"8d5454b96761fafe4d5a9da76a369a602f500f49\"," ++
      "\"flint_threads\":1,\"flint_version\":\"3.6.0\"," ++
      "\"micro_batch\":4096,\"precision_bits\":96," ++
      "\"shard_count\":1236316,\"shard_span\":10000000}"
  | .helfgottPlattGoldbachV1 =>
      "{\"binary_even_count\":1999999999999999999," ++
      "\"binary_leaves_per_group\":8,\"binary_shards\":65536," ++
      "\"h100_groups\":8192,\"ladder_cpu_groups\":320," ++
      "\"ladder_maximum_gap\":4000000000000000000," ++
      "\"ladder_proth_exponent\":52,\"ladder_range_count\":492700," ++
      "\"ladder_sieve_bound\":16000}"
  | .goldbach10Pow27V1 =>
      "{\"binary_even_count\":15624999999999999," ++
      "\"binary_leaves_per_group\":8,\"binary_shards\":65536," ++
      "\"h100_groups\":8192,\"ladder_maximum_gap\":31250000000000000," ++
      "\"ladder_proth_exponent\":45,\"ladder_range_count\":7106," ++
      "\"ladder_range_width\":140737488355328000000000," ++
      "\"ladder_scheduled_endpoint\":1000080592252960768000000000," ++
      "\"ladder_sieve_bound\":16000}"
  | .helfgottSqrt218V1 =>
      "{\"independent_replay\":true,\"log_depth\":14," ++
      "\"log_scale\":281474976710656,\"log_seed_count\":30," ++
      "\"reciprocal_scale\":1073741824}"
  | .helfgottSqrt218FixedV2 =>
      "{\"certificate_format\":\"SQ218V2\",\"certificate_version\":2," ++
      "\"result_bytes\":120,\"result_envelope\":\"canonical-lower-hex\"," ++
      "\"result_format\":\"SQ218R2\"}"
  | .ramareProductionFoldsV1 =>
      "{\"first_mertens_scale_bits\":48,\"lemma71_scale_bits\":32," ++
      "\"mstar_product_scale_bits\":96," ++
      "\"replay\":\"independent-two-pass\"," ++
      "\"row_domain\":\"sparkinterval.tg.ramare-production-fold-rows.v1\"}"
  | .plattStrongerRangeLiveV1 =>
      "{\"accumulator_bits\":78,\"budget\":\"ceil(n/2^17)+1\"," ++
      "\"chain\":\"two-limb-carry\",\"test\":\"every-integer\"," ++
      "\"threshold\":\"floor(2^78/ceil(sqrt(n+1)))\"}"

/-- Canonical domain bytes bound by the signed statement. -/
def canonicalDomain : RegisteredAlgorithm → String
  | .cubicSumDivThreeV1 =>
      "{\"input\":\"nat\",\"output\":\"nat\",\"range_start\":0}"
  | .h100FormalPtxConstantOneV1 =>
      "{\"expression\":\"constant_interval_one\"," ++
      "\"interval_hi_bits\":\"3ff0000000000000\"," ++
      "\"interval_lo_bits\":\"3ff0000000000000\",\"rows\":1,\"status\":0}"
  | .cdemTableAbelExactScanV2 =>
      "{\"claim\":\"two-pre-endpoint-abel-increment-upper-bounds\"," ++
      "\"index_lower\":1,\"index_upper\":5000000000," ++
      "\"prefix_upper\":199330}"
  | .hurstSharedFourResidualV2 =>
      "{\"atoms\":[\"cdem-squarefree\",\"mertens-hurst\"," ++
      "\"platt-little-mertens-2-11\"," ++
      "\"platt-little-mertens-stronger\"]," ++
      "\"source_lower\":1," ++
      "\"source_upper_exclusive\":10000000000000001," ++
      "\"squarefree_thresholds\":[9243,438429]}"
  | .ch25PsiLemma92V1 =>
      "{\"claim\":\"ch25-lemma-9-2-psi-source\"," ++
      "\"source_lower\":1,\"source_upper\":10000000000000," ++
      "\"upper_denominator\":25000000,\"upper_numerator\":19764819}"
  | .ramareZunigaLemma62V1 =>
      "{\"bound_denominator\":100,\"bound_numerator\":193," ++
      "\"claim\":\"ramare-zuniga-2024-lemma-6-2-source\"," ++
      "\"source_lower\":1,\"source_upper_exclusive\":21000000001," ++
      "\"x_lower\":3,\"x_upper\":21000000000}"
  | .helfgottProp1224MpfrV1 =>
      "{\"claim\":\"helfgott-proposition-12-2-4-finite-computation-source\"," ++
      "\"dense_q_upper_exclusive\":3300000000,\"extension_divisor\":210," ++
      "\"extension_q_upper_exclusive\":22000000000," ++
      "\"rank_lower\":0,\"rank_upper_exclusive\":3389047618}"
  | .ch25A7BoundaryV1 =>
      "{\"bound_denominator\":250,\"bound_numerator\":349," ++
      "\"claim\":\"ch25-lemma-a7-arb-boundary-source\"," ++
      "\"imag_lower\":-4,\"imag_upper\":4," ++
      "\"real_lower\":-3,\"real_upper\":5}"
  | .plattHead2e4V1 =>
      "{\"all_q128_rows_sha256\":\"" ++ plattHead2e4AllQ128RowsDigest ++ "\"," ++
      "\"claim\":\"platt-zero-enumeration-2e4-source\"," ++
      "\"imag_lower_exclusive\":0," ++
      "\"included_q128_rows_sha256\":\"" ++
        plattHead2e4IncludedQ128RowsCommitment ++ "\"," ++
      "\"multiplicity_count\":22491," ++
      "\"real_lower_exclusive\":0,\"real_upper_exclusive\":1," ++
      "\"source_height\":20000}"
  | .plattDirichletTheorem71V1 =>
      "{\"characters\":\"all-primitive-dirichlet-characters\"," ++
      "\"claim\":\"platt-theorem-7-1-dirichlet-verification\"," ++
      "\"modulus_lower\":1,\"modulus_upper\":400000," ++
      "\"parity_branches\":[\"even\",\"odd\"]," ++
      "\"zero_imag_bound\":\"absolute-source-height\"," ++
      "\"zero_real_lower_exclusive\":0,\"zero_real_upper_exclusive\":1}"
  | .plattTrudgianFiniteRHV1 =>
      "{\"claim\":\"platt-trudgian-finite-rh-source\"," ++
      "\"imag_lower_exclusive\":0," ++
      "\"multiplicity_count\":12363153437138," ++
      "\"real_lower_exclusive\":0,\"real_upper_exclusive\":1," ++
      "\"source_height\":3000175332800}"
  | .helfgottPlattGoldbachV1 =>
      "{\"binary_even_lower\":4," ++
      "\"binary_even_upper\":4000000000000000000," ++
      "\"claim\":\"helfgott-platt-theorem-4-1-source\"," ++
      "\"source_lower\":7," ++
      "\"source_upper\":8875694145621773516800000000000}"
  | .goldbach10Pow27V1 =>
      "{\"binary_even_lower\":4," ++
      "\"binary_even_upper\":31250000000000000," ++
      "\"claim\":\"ternary-goldbach-finite-below-10pow27\"," ++
      "\"source_lower\":7," ++
      "\"source_upper\":1000000000000000000000000000}"
  | .helfgottSqrt218V1 =>
      "{\"claim\":\"helfgott-2-18-finite-head-and-anchor\"," ++
      "\"head_lower\":1,\"head_upper\":2000000,\"strict\":true}"
  | .helfgottSqrt218FixedV2 =>
      "{\"claim\":\"helfgott-2-18-finite-head-and-anchor\"," ++
      "\"head_lower\":1,\"head_upper\":2000000," ++
      "\"input_identity\":\"reviewed-byte-length-and-sha256\"," ++
      "\"strict\":true}"
  | .ramareProductionFoldsV1 =>
      "{\"claim\":\"ramare-production-folds-source\"," ++
      "\"first_mertens_anchor_denominator\":10000," ++
      "\"first_mertens_anchor_numerator\":4," ++
      "\"first_mertens_lower\":144913,\"first_mertens_upper\":100000000," ++
      "\"lemma71_limits\":[462848,1000000,10000000,100000000]," ++
      "\"lemma71_numerators\":[374,422,579,762]," ++
      "\"mstar_lower\":2,\"mstar_upper\":140000000," ++
      "\"seam_denominator\":1000,\"seam_numerator\":5}"
  | .plattStrongerRangeLiveV1 =>
      "{\"claim\":\"platt-stronger-little-mertens-live\"," ++
      "\"source_lower\":5,\"source_upper\":7727068586}"

/-- Source-reviewed SHA-256 of `canonicalParameters`. -/
def canonicalParametersHash : RegisteredAlgorithm → Digest
  | .cubicSumDivThreeV1 =>
      "cedb94b600a0ee4c75b8a46454f32b0b55e47a1566a728fa9275cbbb5275a35e"
  | .h100FormalPtxConstantOneV1 =>
      "5c9c12fc89e79564c4ce70d27875d7e33d7f32e0a1ff3a0d48037c0a6b5a2b33"
  | .cdemTableAbelExactScanV2 =>
      "9c7ac1c656f2228f36b68095dba7ce1f317a024e51bfa49878434d616d97dca8"
  | .hurstSharedFourResidualV2 =>
      "78f8cf9ecdcac464c1711f877c57e31518dd66d6070882fb6de1d2a199068d1d"
  | .ch25PsiLemma92V1 =>
      "ddc632e84956e223e9df686d02aab167b52cd902dfcedf6ae3a7ccccdd0f6637"
  | .ramareZunigaLemma62V1 =>
      "515707b2ec16c0ffa90cd4b36cb64353e1da4f93a2c94dd21523fe42939407d5"
  | .helfgottProp1224MpfrV1 =>
      "fac07cd6c76a9e2caf7e475107046d76683788426b1c9e26ac8d66aed8114853"
  | .ch25A7BoundaryV1 =>
      "f377fb7b8c8d8d033083a0759841411d9bb955e919041f2a5b5be830ed69212e"
  | .plattHead2e4V1 =>
      "af039df434d373002440517fb4b4dd817a8e9fd5028116885df6f2466598986a"
  | .plattDirichletTheorem71V1 =>
      "975b05caf3057f499a0d5673a438e74ff781702ceb0ffe8ca8f018f582c269f0"
  | .plattTrudgianFiniteRHV1 =>
      "be6cf9610adc9590ec746c28a48a6a3980d40ee9da1b01885167a309b5190672"
  | .helfgottPlattGoldbachV1 =>
      "dfafec3f7ed744b1e3fbc0e5f97aec1ec5540f106c896c7481329e6371ff0607"
  | .goldbach10Pow27V1 =>
      "ee334b42905942c4d3232007e2a67c27fee4e89a8143bbf6adb0d1957b0b8cb9"
  | .helfgottSqrt218V1 =>
      "389a9a946df89008639edffb01f66f34ffdf86ace00098791bac81c774d9c502"
  | .helfgottSqrt218FixedV2 =>
      "11a8b0f784e4846b10c46669d04d349ba13640c08ba782fe0ac1450246ab379f"
  | .ramareProductionFoldsV1 =>
      "4c2bfc7fefa0e9c33c8877c52107a8f8fdcc2f1289ab0e25e8d9d6e7bdfb4481"
  | .plattStrongerRangeLiveV1 =>
      "8c8166cce5f1b071deb1ab977549fc9364d1787309055650e458e431eac8b9b0"

/-- Source-reviewed SHA-256 of `canonicalDomain`. -/
def canonicalDomainHash : RegisteredAlgorithm → Digest
  | .cubicSumDivThreeV1 =>
      "bb80edb9e456ef6b4966ae6691f0aa38191733929c7b3e30cb3c2ae0bcd9930b"
  | .h100FormalPtxConstantOneV1 =>
      "b92c8237a11dac1233796029849857aafb4966136ef24c0dde504deeab725597"
  | .cdemTableAbelExactScanV2 =>
      "298811e1d0ab933c02ff8afb71eb21d715052d414d3b400473b3f36807969a76"
  | .hurstSharedFourResidualV2 =>
      "fbbe3abc2d158bebb2a9f9b06c0379c3fd9eff168c86c9900a7997172ec91f0a"
  | .ch25PsiLemma92V1 =>
      "2a19d38cb3c36f9371c741701b7046b6c99dfba94f12185bd8625fad2e8f921f"
  | .ramareZunigaLemma62V1 =>
      "9cafd963de87e0f4f36904a616a9191b7fdf1b4ae29d05fe12a27bc60c6392f3"
  | .helfgottProp1224MpfrV1 =>
      "effa0ec90992a66d497c13fba77923a9fb96996d93be9d8d6fd54b21a09e92a3"
  | .ch25A7BoundaryV1 =>
      "629d9c7b3c084ef33f69d92abbe22b5120bac210fc963191c4b1e8289ff1dea5"
  | .plattHead2e4V1 =>
      "cfbcfeda2b76f99622befbf795d666b745ec45b82691f73bada7b04399464d11"
  | .plattDirichletTheorem71V1 =>
      "9b914c30a535b241a17b3180b52f759e3e52ed4424f2a93be4481323b627f31e"
  | .plattTrudgianFiniteRHV1 =>
      "e8d26bae0efc9c3acfa968e7b0e5a76d81902b9fb87ac7126605770f48e751fa"
  | .helfgottPlattGoldbachV1 =>
      "cf9cb3c9f1c3825c7ddfa3a91aa474f2f8cb03064570bad6d51cf7287bbdc47b"
  | .goldbach10Pow27V1 =>
      "4a01f0bc8f042f6605fc42fca28c73416a694e7541759abb5e7fec04720f9fa7"
  | .helfgottSqrt218V1 =>
      "44ba1f2b13b8cdbb3422d1ca674d95531e6c6ffe4e07652a969652d9c0ac120f"
  | .helfgottSqrt218FixedV2 =>
      "e27ff5ea0864cfbaa3a2618bcc6e79ff82ad0767c74473e8f88bef9670d6ecc9"
  | .ramareProductionFoldsV1 =>
      "e57d9903f117e68dce0db4fa223eae103a599c4ccd31735c4487ccec129fcff4"
  | .plattStrongerRangeLiveV1 =>
      "e5a470a3565f520b333f6fd7c2b400c12121fd5a17f77452dbb6efd0667410d4"

/-- Executable audit check for parameter/domain protocol digests. -/
def metadataHashesDiagnosticCheck (algorithm : RegisteredAlgorithm) : Bool :=
  SHA256.digestString algorithm.canonicalParameters ==
      algorithm.canonicalParametersHash &&
    SHA256.digestString algorithm.canonicalDomain == algorithm.canonicalDomainHash

/-- Successful branch of the fixed-width Sqrt218 V2 protocol.

The certificate itself is existentially supplied, but every accepted byte is
fixed by the reviewed byte length and the exact SHA-256 signed as
`RunStatement.inputHash`.  The native result envelope must independently
repeat that same identity and the exact arithmetic exit accepted by
`completeRun`. -/
def helfgottSqrt218FixedV2Success
    (input output : String) : Prop :=
  ∃ reviewed : ReviewedSqrt218FixedV2Deployment,
    ∃ rawCertificate image arithmeticResult rawResult nativeResult,
      helfgottSqrt218FixedV2ProductionDeployment = some reviewed ∧
      input = reviewed.certificateSHA256 ∧
      rawCertificate.size = reviewed.certificateBytes ∧
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire.decodeCanonicalArchiveBytes
          rawCertificate = .ok image ∧
      SHA256.digestByteArray rawCertificate = input ∧
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter.completeRun
          image = .ok arithmeticResult ∧
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter.completeCheck
          image arithmeticResult = true ∧
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.decodeResultEnvelope
          output = .ok (rawResult, nativeResult) ∧
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.acceptedResultCheck
          nativeResult = true ∧
      nativeResult.inputByteLength = reviewed.certificateBytes ∧
      nativeResult.inputSHA256 = input ∧
      nativeResult.arithmeticResult = arithmeticResult

/-- Fixed formal execution relation for every registered algorithm.

Both the input and output must use their canonical textual encodings.  The
relation states the complete algorithm result, not merely that some bytes
were returned. -/
def Runs : RegisteredAlgorithm → String → String → Prop
  | .cubicSumDivThreeV1, input, output =>
      ∃ upper result : Nat,
        parseCanonicalNat input = some upper ∧
        parseCanonicalNat output = some result ∧
        cubicSumDivThreeMachine upper = result
  | .h100FormalPtxConstantOneV1, input, output =>
      input = h100FormalPtxConstantOneInput ∧
        output = h100FormalPtxConstantOneOutput
  | .cdemTableAbelExactScanV2, input, output =>
      input = cdemTableAbelInput ∧
        (output = "false" ∨
          parseCanonicalNat output =
              some (Nat.pair
                SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
                SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator) ∧
            SparkInterval.Generated.CDEMAbelProduction.certificate.check =
              true ∧
            Nonempty
              (SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence
                SparkInterval.Generated.CDEMAbelProduction.certificate))
  | .hurstSharedFourResidualV2, input, output =>
      input = hurstSharedFourResidualInput ∧
        (output = "false" ∨
          output = "true" ∧
            ∃ certificate :
                SparkInterval.TernaryGoldbach.HurstAffineCertificate.Certificate,
              Nonempty (
                  SparkInterval.TernaryGoldbach.HurstSourceSemantics.LocalSourceScaleEvidence
                    certificate) ∧
                certificate.check = true)
  | .ch25PsiLemma92V1, input, output =>
      input = ch25PsiLemma92Input ∧
        (output = "false" ∨
          output = "true" ∧
            Nonempty
              SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.GapSourceScaleEvidence)
  | .ramareZunigaLemma62V1, input, output =>
      input = ramareZunigaLemma62Input ∧
        (output = "false" ∨
          output = "true" ∧
            ∃ certificate :
                SparkInterval.TernaryGoldbach.R2StarSourceSemantics.Certificate,
              Nonempty
                  (SparkInterval.TernaryGoldbach.R2StarSourceSemantics.SourceScaleEvidence
                    certificate) ∧
                certificate.check = true)
  | .helfgottProp1224MpfrV1, input, output =>
      input = helfgottProp1224MpfrInput ∧
        (output = "false" ∨
          output = "true" ∧
            ∃ certificate :
                SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.Certificate,
              Nonempty
                  (SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.SourceScaleEvidence
                    certificate) ∧
                certificate.check = true)
  | .ch25A7BoundaryV1, input, output =>
      input = ch25A7BoundaryInput ∧
        (output = "false" ∨
          output = "true" ∧
            SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence.SuccessEvidence)
  | .plattHead2e4V1, input, output =>
      input = plattHead2e4Input ∧
        (output = "false" ∨
          output = "true" ∧
            Nonempty
              (SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.CheckedQ128HeadEvidence
                SparkInterval.Generated.PlattHeadQ128.table
                plattHead2e4IncludedQ128RowsCommitment))
  | .plattDirichletTheorem71V1, input, output =>
      input = plattDirichletTheorem71Input ∧
        (output = "false" ∨
          output = "true" ∧
            Nonempty SparkInterval.Dirichlet.PlattTheorem71SourceEvidence)
  | .plattTrudgianFiniteRHV1, input, output =>
      input = plattTrudgianFiniteRHInput ∧
        (output = "false" ∨
          output = "true" ∧
            Nonempty
              SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.SourceEvidence)
  | .helfgottPlattGoldbachV1, input, output =>
      input = helfgottPlattGoldbachInput ∧
        (output = "false" ∨
          output = "true" ∧
            Nonempty
              SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.CheckedSourceEvidence)
  | .goldbach10Pow27V1, input, output =>
      input = goldbach10Pow27Input ∧
        (output = "false" ∨
          output = "true" ∧
            Nonempty
              SparkInterval.TernaryGoldbach.Goldbach10Pow27CampaignSemantics.CheckedCampaignEvidence)
  | .helfgottSqrt218V1, input, output =>
      input = helfgottSqrt218Input ∧
        (output = "false" ∨
          output = "true" ∧
            ∃ archive :
                SparkInterval.TernaryGoldbach.Sqrt218Operational.Archive,
              SparkInterval.TernaryGoldbach.Sqrt218Operational.run
                helfgottSqrt218ProductionProfile archive = true)
  | .helfgottSqrt218FixedV2, input, output =>
      output = "false" ∨
        helfgottSqrt218FixedV2Success input output
  | .ramareProductionFoldsV1, input, output =>
      input = ramareProductionFoldsInput ∧
        (output = "false" ∨
          output = "true" ∧
            Nonempty
              SparkInterval.TernaryGoldbach.RamareNativeFoldContracts.FiniteFoldEvidence)
  -- Why this case has no source-evidence conjunct, unlike every neighbouring
  -- production case.
  --
  -- Each neighbour above pairs `output = "true"` with a `Nonempty <evidence>`
  -- conjunct because its producer emits checked rows that Lean re-folds into
  -- the stated real inequality.  leancompcert emits nothing of that kind.
  -- What leancompcert proves is that *compilation* is faithful: the Lean
  -- `Program` value, the C it is lowered to, and the x86_64 the CompCert
  -- backend produces all agree.  It does not prove that
  -- `mobiusProgram`/`mobiusLiveProgram` computes `Σ_{m≤n} μ(m)/m`, nor that a
  -- zero exit status means the threshold inequality holds.  Nothing in this
  -- library establishes that denotation today.
  --
  -- Consequently a `"true"` from this campaign carries no mathematical content
  -- through `Runs`, and this relation must not quietly assert any.  The
  -- mathematical content is a separate, explicitly stated realisation premise
  -- carried on the attestation path (see the `...RealisesLittleStronger`-style
  -- hypotheses in `Execution/LeanCompCertSegCampaign.lean`), where it is a
  -- named assumption a reader can see and discharge -- not an invisible
  -- conjunct smuggled into the closed registry's execution semantics.
  | .plattStrongerRangeLiveV1, input, output =>
      input = plattStrongerRangeLiveInput ∧
        (output = "false" ∨ output = "true")

/-- Extract exact typed operational success from the successful Sqrt218 branch.

This theorem is an ordinary case split over `Runs`; it does not construct or
evaluate a production archive and has no execution-trust dependency. -/
theorem helfgottSqrt218_operationalSuccess_of_runs
    {input output : String}
    (run : RegisteredAlgorithm.helfgottSqrt218V1.Runs input output)
    (houtput : output = "true") :
    ∃ archive : SparkInterval.TernaryGoldbach.Sqrt218Operational.Archive,
      SparkInterval.TernaryGoldbach.Sqrt218Operational.run
        helfgottSqrt218ProductionProfile archive = true := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · exact hsuccess.2

/-- Both returned binary64 endpoints are the exact rational number one. -/
theorem h100FormalPtxConstantOne_decodes :
    Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) := by
  norm_num [Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem cubicSumDivThree_runs_iff {input output : String} :
    RegisteredAlgorithm.cubicSumDivThreeV1.Runs input output ↔
      ∃ upper result : Nat,
        parseCanonicalNat input = some upper ∧
        parseCanonicalNat output = some result ∧
        cubicSumDivThreeMachine upper = result := by
  rfl

/-- A successful canonical parser result exposes the exact decimal bytes. -/
theorem eq_toString_of_parseCanonicalNat_eq_some {text : String} {value : Nat}
    (hparse : parseCanonicalNat text = some value) :
    text = toString value := by
  change text.toNat?.bind (fun parsed =>
    if text = toString parsed then some parsed else none) = some value at hparse
  rw [Option.bind_eq_some_iff] at hparse
  rcases hparse with ⟨parsed, _, hresult⟩
  split at hresult
  · next heq =>
      simp only [Option.some.injEq] at hresult
      subst parsed
      exact heq
  · simp at hresult

/-- Closed form used to reason about large bounds without reducing a
twenty-thousand-step sum inside the kernel. -/
theorem sumCubes_eq_closedForm (upper : Nat) :
    (∑ x ∈ Finset.range (upper + 1), (x : ℚ) ^ 3) =
      (((upper : ℚ) * ((upper : ℚ) + 1) / 2) ^ 2) := by
  induction upper with
  | zero => norm_num
  | succ upper ih =>
      rw [show upper + 1 + 1 = (upper + 1) + 1 by omega,
        Finset.sum_range_succ, ih]
      push_cast
      ring

theorem cubicSumDivThree_eq_closedForm (upper : Nat) :
    cubicSumDivThree upper =
      (((upper : ℚ) * ((upper : ℚ) + 1) / 2) ^ 2) / 3 := by
  induction upper with
  | zero => norm_num [cubicSumDivThree]
  | succ upper ih =>
      rw [cubicSumDivThree, show upper + 1 + 1 = (upper + 1) + 1 by omega,
        Finset.sum_range_succ]
      rw [show (∑ x ∈ Finset.range (upper + 1), (x : ℚ) ^ 3 / 3) =
          cubicSumDivThree upper by rfl, ih]
      push_cast
      ring

/-- The executable accumulator refines the exact mathematical cube sum. -/
theorem cubicNumeratorLoop_cast (count : Nat) :
    (cubicNumeratorLoop count : ℚ) =
      ∑ x ∈ Finset.range count, (x : ℚ) ^ 3 := by
  induction count with
  | zero => simp [cubicNumeratorLoop]
  | succ count ih =>
      rw [cubicNumeratorLoop, Finset.sum_range_succ, Nat.cast_add,
        Nat.cast_pow, ih]

/-- Exact numerator-loop result, proved without unfolding 20,001 steps. -/
theorem cubicNumeratorLoop_20001 :
    cubicNumeratorLoop 20001 = 40004000100000000 := by
  have hsum :
      (∑ x ∈ Finset.range 20001, (x : ℚ) ^ 3) =
        (40004000100000000 : ℚ) := by
    calc
      (∑ x ∈ Finset.range 20001, (x : ℚ) ^ 3) =
          (((((20000 : Nat) : ℚ) *
            (((20000 : Nat) : ℚ) + 1) / 2) ^ 2)) := by
        simpa only [show 20000 + 1 = 20001 by norm_num] using
          sumCubes_eq_closedForm 20000
      _ = (40004000100000000 : ℚ) := by norm_num
  have hloopQ :
      (cubicNumeratorLoop 20001 : ℚ) =
        (40004000100000000 : ℚ) := by
    rw [cubicNumeratorLoop_cast, hsum]
  have hloop :
      cubicNumeratorLoop 20001 = 40004000100000000 := by
    exact_mod_cast hloopQ
  exact hloop

/-- Exact operational result, proved without unfolding 20,001 loop steps. -/
theorem cubicSumDivThreeMachine_20000 :
    cubicSumDivThreeMachine 20000 = 13334666700000000 := by
  rw [cubicSumDivThreeMachine,
    show 20000 + 1 = 20001 by norm_num, cubicNumeratorLoop_20001]

/-- The numerator accumulator is monotone in its iteration count. -/
theorem cubicNumeratorLoop_mono {left right : Nat} (hle : left ≤ right) :
    cubicNumeratorLoop left ≤ cubicNumeratorLoop right := by
  induction right generalizing left with
  | zero =>
      have : left = 0 := by omega
      subst left
      rfl
  | succ right ih =>
      by_cases heq : left = right + 1
      · subst left
        rfl
      · have hleft : left ≤ right := by omega
        exact (ih hleft).trans (by simp [cubicNumeratorLoop])

/-- Every accumulator value reached by the registered loop fits unsigned
64-bit storage. -/
theorem cubicNumeratorLoop_lt_u64 {count : Nat} (hle : count ≤ 20001) :
    cubicNumeratorLoop count < 2 ^ 64 := by
  have hbound := cubicNumeratorLoop_mono hle
  rw [cubicNumeratorLoop_20001] at hbound
  omega

/-- Every cube operand used by the registered loop fits unsigned 64-bit
storage. -/
theorem cube_lt_u64 {x : Nat} (hle : x ≤ 20000) :
    x ^ 3 < 2 ^ 64 := by
  exact (Nat.pow_le_pow_left hle 3).trans_lt (by norm_num)

/-- The intermediate square in `x * x * x` also fits unsigned 64-bit
storage. -/
theorem square_lt_u64 {x : Nat} (hle : x ≤ 20000) :
    x ^ 2 < 2 ^ 64 := by
  exact (Nat.pow_le_pow_left hle 2).trans_lt (by norm_num)

/-- Each accumulator addition in the registered loop fits unsigned 64-bit
storage, so a u64 implementation has no wraparound on this domain. -/
theorem cubicNumeratorStep_lt_u64 {x : Nat} (hle : x ≤ 20000) :
    cubicNumeratorLoop x + x ^ 3 < 2 ^ 64 := by
  have hnext : x + 1 ≤ 20001 := by omega
  simpa only [cubicNumeratorLoop] using cubicNumeratorLoop_lt_u64 hnext

/-- The final quotient also fits unsigned 64-bit storage. -/
theorem cubicSumDivThreeMachine_lt_u64 :
    cubicSumDivThreeMachine 20000 < 2 ^ 64 := by
  rw [cubicSumDivThreeMachine_20000]
  norm_num

/-- Exact result for the registered tutorial bound.  This proof is symbolic;
it does not reduce 20,001 summands and uses no `native_decide`. -/
theorem cubicSumDivThree_20000 :
    cubicSumDivThree 20000 = (13334666700000000 : ℚ) := by
  rw [cubicSumDivThree_eq_closedForm]
  norm_num

/-- At the registered bound, the executable loop implements the exact
rational expression requested by the mathematical specification. -/
theorem cubicSumDivThreeMachine_sound_20000 :
    (cubicSumDivThreeMachine 20000 : ℚ) = cubicSumDivThree 20000 := by
  rw [cubicSumDivThreeMachine_20000, cubicSumDivThree_20000]
  norm_num

end RegisteredAlgorithm

/-- Closed, versioned invocations whose complete input meaning is audited.

This is an inductive rather than a caller-populated structure.  Consequently
the trusted axiom cannot be applied to an arbitrary SHA-256 preimage chosen by
a theorem author.  Large server-side verifiers may later use a constructor
whose fixed semantics existentially quantifies streamed witness bytes, while
the small tutorial fixes its complete input literally. -/
inductive RegisteredInvocation where
  /-- `cubicSumDivThreeV1` with canonical input `"20000"`. -/
  | cubicSumDivThree20000V1
  /-- The exact one-row constant-one `sm_90` H100 pilot. -/
  | h100FormalPtxConstantOneV1
  /-- Production `K=199330`, `N=5*10^9` CDEM Abel V2 certificate. -/
  | cdemTableAbelProductionV2
  /-- Shared Hurst scan through `10^16` for four named residuals. -/
  | hurstSharedFourResidualProductionV2
  /-- CH25 Lemma 9.2 psi scan through `10^13`. -/
  | ch25PsiLemma92ProductionV1
  /-- Ramaré--Zúñiga Lemma 6.2 `R₂*` scan through `21·10^9`. -/
  | ramareZunigaLemma62ProductionV1
  /-- Helfgott Proposition 12.2.4's directed MPFR/GMP source-rank scan. -/
  | helfgottProp1224ProductionV1
  /-- Retained CH25 Lemma A.7 FLINT/Arb boundary replay. -/
  | ch25A7BoundaryProductionV1
  /-- Retained 22,491-row Platt head replay through height `20,000`. -/
  | plattHead2e4ProductionV1
  /-- CPU finalizer for Platt's exact two-branch Dirichlet Theorem 7.1 contract. -/
  | plattDirichletTheorem71ProductionV1
  /-- Platt--Trudgian finite RH through the exact source endpoint. -/
  | plattTrudgianFiniteRHProductionV1
  /-- CPU finalizer for the pinned binary-H100 plus CPU-ladder computation. -/
  | helfgottPlattGoldbachProductionV1
  /-- CPU finalizer for the distinct finite campaign below `10^27`. -/
  | goldbach10Pow27ProductionV1
  /-- Azure CPU replay of the exact finite computation behind Helfgott (2.18). -/
  | helfgottSqrt218ProductionV1
  /-- Fixed-width V2 CPU certificate with an exact SQ218R2 result record. -/
  | helfgottSqrt218FixedProductionV2
  /-- Azure CPU replay of the three Ramaré production interval folds. -/
  | ramareProductionFoldsProductionV1
  /-- Intel TDX enclave run of the live leancompcert CompCert campaign for
  Platt's stronger little-Mertens range. -/
  | plattStrongerRangeLiveProductionV1
  deriving Repr, DecidableEq, BEq

namespace RegisteredInvocation

/-- Algorithm selected by a closed invocation. -/
def algorithm : RegisteredInvocation → RegisteredAlgorithm
  | .cubicSumDivThree20000V1 => .cubicSumDivThreeV1
  | .h100FormalPtxConstantOneV1 => .h100FormalPtxConstantOneV1
  | .cdemTableAbelProductionV2 => .cdemTableAbelExactScanV2
  | .hurstSharedFourResidualProductionV2 => .hurstSharedFourResidualV2
  | .ch25PsiLemma92ProductionV1 => .ch25PsiLemma92V1
  | .ramareZunigaLemma62ProductionV1 => .ramareZunigaLemma62V1
  | .helfgottProp1224ProductionV1 => .helfgottProp1224MpfrV1
  | .ch25A7BoundaryProductionV1 => .ch25A7BoundaryV1
  | .plattHead2e4ProductionV1 => .plattHead2e4V1
  | .plattDirichletTheorem71ProductionV1 => .plattDirichletTheorem71V1
  | .plattTrudgianFiniteRHProductionV1 => .plattTrudgianFiniteRHV1
  | .helfgottPlattGoldbachProductionV1 => .helfgottPlattGoldbachV1
  | .goldbach10Pow27ProductionV1 => .goldbach10Pow27V1
  | .helfgottSqrt218ProductionV1 => .helfgottSqrt218V1
  | .helfgottSqrt218FixedProductionV2 => .helfgottSqrt218FixedV2
  | .ramareProductionFoldsProductionV1 => .ramareProductionFoldsV1
  | .plattStrongerRangeLiveProductionV1 => .plattStrongerRangeLiveV1

/-- Exact canonical input selected by a closed invocation.

For the fixed-width V2 constructor only, arbitrary binary input cannot be
represented by this historical `String` API.  Its value is therefore the
reviewed certificate digest selector itself, and `inputHashDiagnosticCheck`
does not hash this string.  The `Runs` relation hashes the existential raw
`ByteArray` and equates that digest directly with the selector. -/
def canonicalInput : RegisteredInvocation → String
  | .cubicSumDivThree20000V1 => "20000"
  | .h100FormalPtxConstantOneV1 =>
      RegisteredAlgorithm.h100FormalPtxConstantOneInput
  | .cdemTableAbelProductionV2 =>
      RegisteredAlgorithm.cdemTableAbelInput
  | .hurstSharedFourResidualProductionV2 =>
      RegisteredAlgorithm.hurstSharedFourResidualInput
  | .ch25PsiLemma92ProductionV1 =>
      RegisteredAlgorithm.ch25PsiLemma92Input
  | .ramareZunigaLemma62ProductionV1 =>
      RegisteredAlgorithm.ramareZunigaLemma62Input
  | .helfgottProp1224ProductionV1 =>
      RegisteredAlgorithm.helfgottProp1224MpfrInput
  | .ch25A7BoundaryProductionV1 =>
      RegisteredAlgorithm.ch25A7BoundaryInput
  | .plattHead2e4ProductionV1 =>
      RegisteredAlgorithm.plattHead2e4Input
  | .plattDirichletTheorem71ProductionV1 =>
      RegisteredAlgorithm.plattDirichletTheorem71Input
  | .plattTrudgianFiniteRHProductionV1 =>
      RegisteredAlgorithm.plattTrudgianFiniteRHInput
  | .helfgottPlattGoldbachProductionV1 =>
      RegisteredAlgorithm.helfgottPlattGoldbachInput
  | .goldbach10Pow27ProductionV1 =>
      RegisteredAlgorithm.goldbach10Pow27Input
  | .helfgottSqrt218ProductionV1 =>
      RegisteredAlgorithm.helfgottSqrt218Input
  | .helfgottSqrt218FixedProductionV2 =>
      match helfgottSqrt218FixedV2ProductionDeployment with
      | none => ""
      | some reviewed => reviewed.certificateSHA256
  | .ramareProductionFoldsProductionV1 =>
      RegisteredAlgorithm.ramareProductionFoldsInput
  | .plattStrongerRangeLiveProductionV1 =>
      RegisteredAlgorithm.plattStrongerRangeLiveInput

/-- Source-reviewed SHA-256 of the closed invocation input.

The fixed-width V2 value comes directly from its optional reviewed pin; it is
never the SHA-256 of a prose descriptor. -/
def canonicalInputHash : RegisteredInvocation → Digest
  | .cubicSumDivThree20000V1 =>
      "876c9b16254e157d1eb645390dcfae6f29b9d3cd394e73a91de8ee5d0e67ee43"
  | .h100FormalPtxConstantOneV1 =>
      "724d074b5818f2cb1ef81b5b73635af38c8f5309826cfa3dcc40b5729d8fbb93"
  | .cdemTableAbelProductionV2 =>
      "f14d4dd60e39b2b4f655d3b82333659167d78246de8c5aab923db8a69347742a"
  | .hurstSharedFourResidualProductionV2 =>
      "84cad6505119c2498b1213c73c13e379ebcc0e8bbd2d445d1539d45ec06fc5b7"
  | .ch25PsiLemma92ProductionV1 =>
      "35368234a47ea3acdac04c55453f07cc5deb051fdf2238e865d683b17b11d3d8"
  | .ramareZunigaLemma62ProductionV1 =>
      "386168a18f1c8639736118a2beb057efe0a1a53871561a9a7b54dafd50024c5c"
  | .helfgottProp1224ProductionV1 =>
      "ced1a63532a63b6e24290c51082ff8865ce38c75daae0d4f3439a63eef2444ec"
  | .ch25A7BoundaryProductionV1 =>
      "4e45410d2d26467dbd5f78f8ea536b1a8bbf44f1cd5248e234b985bd1f595674"
  | .plattHead2e4ProductionV1 =>
      "a2409d869f3084fec413d4e7035f17749f4d2a572cd03f6f847f3352a78aca1d"
  | .plattDirichletTheorem71ProductionV1 =>
      "42fe4b88a40a22d854292bf030a1eff009d32cf211e47085d43d79a6f2b8c8e9"
  | .plattTrudgianFiniteRHProductionV1 =>
      "0af73e082ef1673a90ca668e395b71166b0320d6e3a99b6cd2af6d09ea18adce"
  | .helfgottPlattGoldbachProductionV1 =>
      "19591d644a11591ac7aeffc9d507ded00f2f63993d68b2ceb7629c8ae62e0691"
  | .goldbach10Pow27ProductionV1 =>
      "5e34a58a14883600c91b891a78749cdcff1210ce48f64e41f7bf965f2331ad27"
  | .helfgottSqrt218ProductionV1 =>
      "17d1c5328bd05b4883670f33823cd218dd1f32e53bad51c9a5c96bec5e06d178"
  | .helfgottSqrt218FixedProductionV2 =>
      match helfgottSqrt218FixedV2ProductionDeployment with
      | none => ""
      | some reviewed => reviewed.certificateSHA256
  | .ramareProductionFoldsProductionV1 =>
      "3535d4ae8a9a1073b7aedd66c900de77abfbc0519d96fcaa89242a0bc638c629"
  | .plattStrongerRangeLiveProductionV1 =>
      "6b9fbeae694703c0fabad05eef9319ff7ef064a9832ad668cd1c4b45dac2e97a"

/-- Executable audit check for the source-reviewed input digest. -/
def inputHashDiagnosticCheck (invocation : RegisteredInvocation) : Bool :=
  match invocation with
  | .helfgottSqrt218FixedProductionV2 =>
      match helfgottSqrt218FixedV2ProductionDeployment with
      | none => false
      | some reviewed =>
          invocation.canonicalInputHash == reviewed.certificateSHA256
  | _ =>
      SHA256.digestString invocation.canonicalInput ==
        invocation.canonicalInputHash

/-- Kernel-executable guard against stale reviewed hash literals.

The external receipt importer independently performs the same preimage
checks, but the closed Lean selector also requires them.  Consequently an
edit to the canonical algorithm, input, parameter, or domain bytes cannot
silently reuse a previously admitted receipt merely because a maintainer
forgot to refresh one of the reviewed digest literals. -/
def sourceBindingDiagnosticCheck (invocation : RegisteredInvocation) : Bool :=
  invocation.algorithm.algorithmHashDiagnosticCheck &&
    invocation.inputHashDiagnosticCheck &&
    invocation.algorithm.metadataHashesDiagnosticCheck

/-- Deployment restrictions that are part of a closed invocation's identity.
The tutorial CPU loop remains target-polymorphic; the H100 pilot does not. -/
def deploymentCheck (invocation : RegisteredInvocation)
    (statement : RunStatement) : Bool :=
  match invocation with
  | .cubicSumDivThree20000V1 => true
  | .h100FormalPtxConstantOneV1 =>
      statement.target == .nvidiaH100SM90 &&
        statement.trust == .nvidiaH100ConfidentialCompute
  | .cdemTableAbelProductionV2 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .hurstSharedFourResidualProductionV2 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .ch25PsiLemma92ProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .ramareZunigaLemma62ProductionV1 =>
      statement.target == .nvidiaH100SM90 &&
        statement.trust == .nvidiaH100ConfidentialCompute
  | .helfgottProp1224ProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .ch25A7BoundaryProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .plattHead2e4ProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .plattDirichletTheorem71ProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .plattTrudgianFiniteRHProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .helfgottPlattGoldbachProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .goldbach10Pow27ProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .helfgottSqrt218ProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .helfgottSqrt218FixedProductionV2 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  | .ramareProductionFoldsProductionV1 =>
      statement.target == .azureSEVSNPCPU &&
        statement.trust == .azureSEVSNPConfidentialCompute
  -- Target-polymorphic, like `cubicSumDivThree20000V1`.
  --
  -- This invocation's real deployment restriction lives on the separate Intel
  -- TDX attestation layer, which pins the enclave image digest and does not
  -- consult `deploymentCheck` at all.  (That layer is deliberately not named
  -- here: this module must stay off its cone, and
  -- `tests/test_phala_tdx_axiom_off_cone.py` enforces that by rejecting any
  -- reference to it from this file.)  The `RunStatement` `target`/`trust`
  -- enumeration has no Intel TDX member to name, so a restriction written
  -- here would be arbitrary rather than binding.
  --
  -- Leaving it polymorphic grants nothing: `Runs` for
  -- `plattStrongerRangeLiveV1` has no mathematical conjunct, so no
  -- combination of target and trust can unlock a mathematical claim through
  -- this constructor.
  | .plattStrongerRangeLiveProductionV1 => true

/-- Bind profile and artifact hashes when a closed production invocation has
post-run reviewed pins.

Every nontrivial TG invocation is deliberately disabled while its reviewed
deployment or terminal pin bundle is `none`.  The tutorial and constant-one
pilot have independently proved outputs and remain available without a
production pin installation. -/
def artifactCheck (invocation : RegisteredInvocation)
    (statement : RunStatement) : Bool :=
  match invocation with
  | .cdemTableAbelProductionV2 =>
      reviewedProductionDeploymentCheck
        cdemTableAbelProductionDeployment statement
  | .hurstSharedFourResidualProductionV2 =>
      reviewedProductionDeploymentCheck
        hurstSharedFourResidualProductionDeployment statement
  | .ch25PsiLemma92ProductionV1 =>
      reviewedProductionDeploymentCheck
        ch25PsiLemma92ProductionDeployment statement
  | .ramareZunigaLemma62ProductionV1 =>
      reviewedProductionDeploymentCheck
        ramareZunigaLemma62ProductionDeployment statement
  | .helfgottProp1224ProductionV1 =>
      reviewedProductionDeploymentCheck
        helfgottProp1224ProductionDeployment statement
  | .ch25A7BoundaryProductionV1 =>
      reviewedProductionDeploymentCheck
        ch25A7BoundaryProductionDeployment statement
  | .plattHead2e4ProductionV1 =>
      reviewedProductionDeploymentCheck
        plattHead2e4ProductionDeployment statement
  | .plattDirichletTheorem71ProductionV1 =>
      reviewedProductionDeploymentCheck
        plattDirichletTheorem71ProductionDeployment statement
  | .plattTrudgianFiniteRHProductionV1 =>
      reviewedProductionDeploymentCheck
        plattTrudgianFiniteRHProductionDeployment statement
  | .helfgottPlattGoldbachProductionV1 =>
      reviewedProductionDeploymentCheck
          helfgottPlattGoldbachProductionDeployment statement &&
        match helfgottPlattGoldbachTerminalArtifactPins with
        | none => false
        | some expected => decide (statement.artifacts = expected)
  | .goldbach10Pow27ProductionV1 =>
      reviewedProductionDeploymentCheck
          goldbach10Pow27ProductionDeployment statement &&
        match goldbach10Pow27TerminalArtifactPins with
        | none => false
        | some expected => decide (statement.artifacts = expected)
  | .helfgottSqrt218ProductionV1 =>
      reviewedProductionDeploymentCheck
        helfgottSqrt218ProductionDeployment statement
  | .helfgottSqrt218FixedProductionV2 =>
      reviewedSqrt218FixedV2DeploymentCheck
        helfgottSqrt218FixedV2ProductionDeployment statement
  | .ramareProductionFoldsProductionV1 =>
      reviewedProductionDeploymentCheck
        ramareProductionFoldsProductionDeployment statement
  -- No reviewed `RunStatement` deployment pin exists for the leancompcert
  -- campaign, and none is needed: its artifacts are pinned by enclave image
  -- digest on the Phala TDX path, and its `Runs` has no mathematical conjunct
  -- for an unpinned statement to unlock.
  | .cubicSumDivThree20000V1
  | .h100FormalPtxConstantOneV1
  | .plattStrongerRangeLiveProductionV1 => true

/-- Bind every nontrivial production invocation to its exact reviewed
source-admitted receipt, not merely to a different receipt carrying the same
logical statement fields. -/
def receiptCheck (invocation : RegisteredInvocation)
    (attestation : Attestation) : Bool :=
  match invocation with
  | .cdemTableAbelProductionV2 =>
      reviewedProductionReceiptCheck
        cdemTableAbelProductionDeployment attestation
  | .hurstSharedFourResidualProductionV2 =>
      reviewedProductionReceiptCheck
        hurstSharedFourResidualProductionDeployment attestation
  | .ch25PsiLemma92ProductionV1 =>
      reviewedProductionReceiptCheck
        ch25PsiLemma92ProductionDeployment attestation
  | .ramareZunigaLemma62ProductionV1 =>
      reviewedProductionReceiptCheck
        ramareZunigaLemma62ProductionDeployment attestation
  | .helfgottProp1224ProductionV1 =>
      reviewedProductionReceiptCheck
        helfgottProp1224ProductionDeployment attestation
  | .ch25A7BoundaryProductionV1 =>
      reviewedProductionReceiptCheck
        ch25A7BoundaryProductionDeployment attestation
  | .plattHead2e4ProductionV1 =>
      reviewedProductionReceiptCheck
        plattHead2e4ProductionDeployment attestation
  | .plattDirichletTheorem71ProductionV1 =>
      reviewedProductionReceiptCheck
        plattDirichletTheorem71ProductionDeployment attestation
  | .plattTrudgianFiniteRHProductionV1 =>
      reviewedProductionReceiptCheck
        plattTrudgianFiniteRHProductionDeployment attestation
  | .helfgottPlattGoldbachProductionV1 =>
      reviewedProductionReceiptCheck
        helfgottPlattGoldbachProductionDeployment attestation
  | .goldbach10Pow27ProductionV1 =>
      reviewedProductionReceiptCheck
        goldbach10Pow27ProductionDeployment attestation
  | .helfgottSqrt218ProductionV1 =>
      reviewedProductionReceiptCheck
        helfgottSqrt218ProductionDeployment attestation
  | .helfgottSqrt218FixedProductionV2 =>
      reviewedSqrt218FixedV2ReceiptCheck
        helfgottSqrt218FixedV2ProductionDeployment attestation
  | .ramareProductionFoldsProductionV1 =>
      reviewedProductionReceiptCheck
        ramareProductionFoldsProductionDeployment attestation
  -- Same reason as `artifactCheck`: the binding receipt for this campaign is
  -- the Phala TDX quote, not a reviewed `Attestation` pin in this module.
  | .cubicSumDivThree20000V1
  | .h100FormalPtxConstantOneV1
  | .plattStrongerRangeLiveProductionV1 => true

/-- Parse and accept one canonical fixed-V2 native result envelope.  This is
only a result-language check; the `Runs` success branch additionally binds its
state, input length, and input digest to the complete certificate check. -/
def sqrt218FixedV2AcceptedResultCheck (output : String) : Bool :=
  match
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.decodeResultEnvelope
      output
  with
  | .error _ => false
  | .ok (_, nativeResult) =>
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.acceptedResultCheck
        nativeResult

/-- The exact result-language admitted for one closed invocation.

This is intentionally weaker than `Runs`: it checks only the canonical shape
of a result, while `Runs` fixes its mathematical meaning.  Keeping the result
language explicit prevents a source-admitted receipt with malformed bytes
from selecting an otherwise matching invocation. -/
def ResultAllowed : RegisteredInvocation → String → Prop
  | .cubicSumDivThree20000V1, output =>
      output = "13334666700000000"
  | .h100FormalPtxConstantOneV1, output =>
      output = RegisteredAlgorithm.h100FormalPtxConstantOneOutput
  | .cdemTableAbelProductionV2, output =>
      output = "false" ∨
        output =
          toString (Nat.pair
            SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
            SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator)
  | .hurstSharedFourResidualProductionV2, output
  | .ch25PsiLemma92ProductionV1, output
  | .ramareZunigaLemma62ProductionV1, output
  | .helfgottProp1224ProductionV1, output
  | .ch25A7BoundaryProductionV1, output
  | .plattHead2e4ProductionV1, output
  | .plattDirichletTheorem71ProductionV1, output
  | .plattTrudgianFiniteRHProductionV1, output
  | .helfgottPlattGoldbachProductionV1, output
  | .goldbach10Pow27ProductionV1, output =>
      output = "false" ∨ output = "true"
  | .helfgottSqrt218ProductionV1, output =>
      output = "false" ∨ output = "true"
  | .helfgottSqrt218FixedProductionV2, output =>
      output = "false" ∨
        sqrt218FixedV2AcceptedResultCheck output = true
  | .ramareProductionFoldsProductionV1, output =>
      output = "false" ∨ output = "true"
  | .plattStrongerRangeLiveProductionV1, output =>
      output = "false" ∨ output = "true"

/-- The closed result language is decidable constructor by constructor. -/
instance instDecidableResultAllowed
    (invocation : RegisteredInvocation) (output : String) :
    Decidable (invocation.ResultAllowed output) := by
  cases invocation <;> simp only [ResultAllowed] <;> infer_instance

/-- Kernel-executable result-language guard for a signed statement. -/
def resultCheck (invocation : RegisteredInvocation)
    (statement : RunStatement) : Bool :=
  decide (invocation.ResultAllowed statement.result)

/-- The executable result guard exposes its human-readable proposition. -/
theorem resultCheck_sound {invocation : RegisteredInvocation}
    {statement : RunStatement}
    (hcheck : invocation.resultCheck statement = true) :
    invocation.ResultAllowed statement.result := by
  simpa [resultCheck] using hcheck

/-- Bind a signed statement to the complete formal identity, exact input, and
canonical result language of a registered invocation. -/
def statementCheck (invocation : RegisteredInvocation)
    (statement : RunStatement) : Bool :=
  invocation.artifactCheck statement &&
    invocation.resultCheck statement &&
      (invocation.sourceBindingDiagnosticCheck &&
        decide (
          statement.algorithmId = invocation.algorithm.algorithmId ∧
          statement.algorithmHash = invocation.algorithm.algorithmHash ∧
          statement.inputHash = invocation.canonicalInputHash ∧
          statement.parametersHash =
            invocation.algorithm.canonicalParametersHash ∧
          statement.domainHash = invocation.algorithm.canonicalDomainHash ∧
          invocation.deploymentCheck statement = true))

/-- Complete selector used at the trusted-execution handoff.  Logical
statement identity, deployment artifacts, and the exact reviewed receipt are
all required. -/
def certificateBindingCheck (invocation : RegisteredInvocation)
    (statement : RunStatement) (attestation : Attestation) : Bool :=
  invocation.statementCheck statement &&
    invocation.receiptCheck attestation

/-- A missing or mismatched reviewed deployment pin prevents a statement from
selecting the invocation, independently of all logical algorithm fields. -/
theorem statementCheck_eq_false_of_artifactCheck_eq_false
    {invocation : RegisteredInvocation} {statement : RunStatement}
    (hcheck : invocation.artifactCheck statement = false) :
    invocation.statementCheck statement = false := by
  simp [statementCheck, hcheck]

/-- A malformed result cannot select an invocation even if every identity,
artifact, and deployment field otherwise matches. -/
theorem statementCheck_eq_false_of_resultCheck_eq_false
    {invocation : RegisteredInvocation} {statement : RunStatement}
    (hcheck : invocation.resultCheck statement = false) :
    invocation.statementCheck statement = false := by
  simp [statementCheck, hcheck]

/-- Stale canonical-byte/digest bindings fail closed even if every signed
statement field happens to retain an older reviewed digest. -/
theorem statementCheck_eq_false_of_sourceBindingDiagnosticCheck_eq_false
    {invocation : RegisteredInvocation} {statement : RunStatement}
    (hcheck : invocation.sourceBindingDiagnosticCheck = false) :
    invocation.statementCheck statement = false := by
  simp [statementCheck, hcheck]

/-- A statement-identical but differently admitted receipt cannot select a
production invocation. -/
theorem certificateBindingCheck_eq_false_of_receiptCheck_eq_false
    {invocation : RegisteredInvocation} {statement : RunStatement}
    {attestation : Attestation}
    (hcheck : invocation.receiptCheck attestation = false) :
    invocation.certificateBindingCheck statement attestation = false := by
  simp [certificateBindingCheck, hcheck]

/-- Propositional identity exposed by a successful invocation check. -/
def StatementBound (invocation : RegisteredInvocation)
    (statement : RunStatement) : Prop :=
  statement.algorithmId = invocation.algorithm.algorithmId ∧
  statement.algorithmHash = invocation.algorithm.algorithmHash ∧
  statement.inputHash = invocation.canonicalInputHash ∧
  statement.parametersHash = invocation.algorithm.canonicalParametersHash ∧
  statement.domainHash = invocation.algorithm.canonicalDomainHash ∧
  invocation.ResultAllowed statement.result ∧
  invocation.sourceBindingDiagnosticCheck = true ∧
  invocation.deploymentCheck statement = true ∧
  invocation.artifactCheck statement = true

/-- The complete formal execution claim unlocked for this invocation.

The closed tutorial invocation specializes the algorithm to upper bound
20,000 directly.  It therefore does not universally assign semantics to every
possible preimage of the statement's input digest. -/
def Runs : RegisteredInvocation → String → Prop
  | .cubicSumDivThree20000V1, output =>
      output = "13334666700000000" ∧
        ∃ result : Nat,
          RegisteredAlgorithm.parseCanonicalNat output = some result ∧
          RegisteredAlgorithm.cubicSumDivThreeMachine 20000 = result
  | .h100FormalPtxConstantOneV1, output =>
      RegisteredAlgorithm.h100FormalPtxConstantOneV1.Runs
        RegisteredAlgorithm.h100FormalPtxConstantOneInput output
  | .cdemTableAbelProductionV2, output =>
      RegisteredAlgorithm.cdemTableAbelExactScanV2.Runs
        RegisteredAlgorithm.cdemTableAbelInput output
  | .hurstSharedFourResidualProductionV2, output =>
      RegisteredAlgorithm.hurstSharedFourResidualV2.Runs
        RegisteredAlgorithm.hurstSharedFourResidualInput output
  | .ch25PsiLemma92ProductionV1, output =>
      RegisteredAlgorithm.ch25PsiLemma92V1.Runs
        RegisteredAlgorithm.ch25PsiLemma92Input output
  | .ramareZunigaLemma62ProductionV1, output =>
      RegisteredAlgorithm.ramareZunigaLemma62V1.Runs
        RegisteredAlgorithm.ramareZunigaLemma62Input output
  | .helfgottProp1224ProductionV1, output =>
      RegisteredAlgorithm.helfgottProp1224MpfrV1.Runs
        RegisteredAlgorithm.helfgottProp1224MpfrInput output
  | .ch25A7BoundaryProductionV1, output =>
      RegisteredAlgorithm.ch25A7BoundaryV1.Runs
        RegisteredAlgorithm.ch25A7BoundaryInput output
  | .plattHead2e4ProductionV1, output =>
      RegisteredAlgorithm.plattHead2e4V1.Runs
        RegisteredAlgorithm.plattHead2e4Input output
  | .plattDirichletTheorem71ProductionV1, output =>
      RegisteredAlgorithm.plattDirichletTheorem71V1.Runs
        RegisteredAlgorithm.plattDirichletTheorem71Input output
  | .plattTrudgianFiniteRHProductionV1, output =>
      RegisteredAlgorithm.plattTrudgianFiniteRHV1.Runs
        RegisteredAlgorithm.plattTrudgianFiniteRHInput output
  | .helfgottPlattGoldbachProductionV1, output =>
      RegisteredAlgorithm.helfgottPlattGoldbachV1.Runs
        RegisteredAlgorithm.helfgottPlattGoldbachInput output
  | .goldbach10Pow27ProductionV1, output =>
      RegisteredAlgorithm.goldbach10Pow27V1.Runs
        RegisteredAlgorithm.goldbach10Pow27Input output
  | .helfgottSqrt218ProductionV1, output =>
      RegisteredAlgorithm.helfgottSqrt218V1.Runs
        RegisteredAlgorithm.helfgottSqrt218Input output
  | .helfgottSqrt218FixedProductionV2, output =>
      RegisteredAlgorithm.helfgottSqrt218FixedV2.Runs
        RegisteredInvocation.helfgottSqrt218FixedProductionV2.canonicalInput
        output
  | .ramareProductionFoldsProductionV1, output =>
      RegisteredAlgorithm.ramareProductionFoldsV1.Runs
        RegisteredAlgorithm.ramareProductionFoldsInput output
  | .plattStrongerRangeLiveProductionV1, output =>
      RegisteredAlgorithm.plattStrongerRangeLiveV1.Runs
        RegisteredAlgorithm.plattStrongerRangeLiveInput output

/-- Every result satisfying the fixed execution relation belongs to the
invocation's canonical result language.  This theorem is axiom-free and makes
the executable guard visibly conservative rather than an ad-hoc importer
restriction. -/
theorem resultAllowed_of_runs {invocation : RegisteredInvocation}
    {output : String} (run : invocation.Runs output) :
    invocation.ResultAllowed output := by
  cases invocation with
  | cubicSumDivThree20000V1 =>
      exact run.1
  | h100FormalPtxConstantOneV1 =>
      exact run.2
  | cdemTableAbelProductionV2 =>
      rcases run.2 with hfailure | ⟨hparse, _hcheck, _hevidence⟩
      · exact Or.inl hfailure
      · exact Or.inr
          (RegisteredAlgorithm.eq_toString_of_parseCanonicalNat_eq_some hparse)
  | hurstSharedFourResidualProductionV2 =>
      exact run.2.imp id And.left
  | ch25PsiLemma92ProductionV1 =>
      exact run.2.imp id And.left
  | ramareZunigaLemma62ProductionV1 =>
      exact run.2.imp id And.left
  | helfgottProp1224ProductionV1 =>
      exact run.2.imp id And.left
  | ch25A7BoundaryProductionV1 =>
      exact run.2.imp id And.left
  | plattHead2e4ProductionV1 =>
      exact run.2.imp id And.left
  | plattDirichletTheorem71ProductionV1 =>
      exact run.2.imp id And.left
  | plattTrudgianFiniteRHProductionV1 =>
      exact run.2.imp id And.left
  | helfgottPlattGoldbachProductionV1 =>
      exact run.2.imp id And.left
  | goldbach10Pow27ProductionV1 =>
      exact run.2.imp id And.left
  | helfgottSqrt218ProductionV1 =>
      exact run.2.imp id And.left
  | helfgottSqrt218FixedProductionV2 =>
      rcases run with hfailure | hsuccess
      · exact Or.inl hfailure
      · right
        rcases hsuccess with
          ⟨reviewed, rawCertificate, image, arithmeticResult, rawResult,
            nativeResult, hpins, hinput, hbytes, hdecode, hdigest,
            hrun, hcomplete, hresult, haccepted, hresultBytes,
            hresultDigest, hresultState⟩
        simpa [sqrt218FixedV2AcceptedResultCheck, hresult] using haccepted
  | ramareProductionFoldsProductionV1 =>
      exact run.2.imp id And.left
  | plattStrongerRangeLiveProductionV1 =>
      exact run.2

theorem statementCheck_sound {invocation : RegisteredInvocation}
    {statement : RunStatement}
    (hcheck : invocation.statementCheck statement = true) :
    invocation.StatementBound statement := by
  rw [statementCheck] at hcheck
  simp only [Bool.and_eq_true] at hcheck
  rcases hcheck with ⟨⟨hartifact, hresult⟩, hsource, hidentityCheck⟩
  rcases of_decide_eq_true hidentityCheck with
    ⟨halgorithmId, halgorithmHash, hinputHash, hparametersHash, hdomainHash,
      hdeployment⟩
  exact
    ⟨halgorithmId, halgorithmHash, hinputHash, hparametersHash,
      hdomainHash, resultCheck_sound hresult, hsource, hdeployment, hartifact⟩

/-- Once reviewed post-run pins are installed, the historical invocation
accepts only the artifact tuple whose CPU closure transitively commits every
signed H100/ladder child and every retained branch receipt. -/
theorem helfgottPlattGoldbachProductionV1_artifacts
    {statement : RunStatement} {expected : ArtifactHashes}
    (hpins : helfgottPlattGoldbachTerminalArtifactPins = some expected)
    (hcheck :
      RegisteredInvocation.helfgottPlattGoldbachProductionV1.statementCheck
        statement = true) :
    statement.artifacts = expected := by
  have hbound := statementCheck_sound hcheck
  rcases hbound with ⟨_, _, _, _, _, _, _, _, hartifact⟩
  have hartifact' :
      reviewedProductionDeploymentCheck
            helfgottPlattGoldbachProductionDeployment statement = true ∧
        statement.artifacts = expected := by
    simpa [artifactCheck, hpins] using hartifact
  exact hartifact'.2

/-- Substituting the transitive child/branch closure while retaining the static
registered metadata is rejected by the historical terminal registration. -/
theorem helfgottPlattGoldbachProductionV1_rejects_childIdentityCommitmentSubstitution
    {statement : RunStatement} {expected : ArtifactHashes}
    (hpins : helfgottPlattGoldbachTerminalArtifactPins = some expected)
    (_halgorithm :
      statement.algorithmId =
        RegisteredAlgorithm.helfgottPlattGoldbachV1.algorithmId)
    (_hinput :
      statement.inputHash =
        RegisteredInvocation.helfgottPlattGoldbachProductionV1.canonicalInputHash)
    (_hhost :
      statement.artifacts.hostExecutableHash =
        expected.hostExecutableHash)
    (_hdevice :
      statement.artifacts.deviceCubinHash = expected.deviceCubinHash)
    (_hsource :
      statement.artifacts.sourceTreeHash = expected.sourceTreeHash)
    (hcommitment :
      statement.artifacts.kernelManifestHash ≠
        expected.kernelManifestHash) :
    RegisteredInvocation.helfgottPlattGoldbachProductionV1.statementCheck
      statement ≠ true := by
  intro hcheck
  have hartifacts :=
    helfgottPlattGoldbachProductionV1_artifacts hpins hcheck
  exact hcommitment (congrArg ArtifactHashes.kernelManifestHash hartifacts)

/-- Before a reviewed historical terminal bundle installs pins, production is
fail-closed. -/
theorem helfgottPlattGoldbachProductionV1_unconfigured
    (hpins : helfgottPlattGoldbachTerminalArtifactPins = none)
    (statement : RunStatement) :
    RegisteredInvocation.helfgottPlattGoldbachProductionV1.statementCheck
      statement = false := by
  simp [statementCheck, artifactCheck, hpins]

/-- Once the post-run Goldbach pins are installed, the closed invocation
accepts only the exact artifact tuple from that signed terminal statement. -/
theorem goldbach10Pow27ProductionV1_artifacts
    {statement : RunStatement} {expected : ArtifactHashes}
    (hpins : goldbach10Pow27TerminalArtifactPins = some expected)
    (hcheck :
      RegisteredInvocation.goldbach10Pow27ProductionV1.statementCheck
        statement = true) :
    statement.artifacts = expected := by
  have hbound := statementCheck_sound hcheck
  rcases hbound with ⟨_, _, _, _, _, _, _, _, hartifact⟩
  have hartifact' :
      reviewedProductionDeploymentCheck
            goldbach10Pow27ProductionDeployment statement = true ∧
        statement.artifacts = expected := by
    simpa [artifactCheck, hpins] using hartifact
  exact hartifact'.2

/-- A receipt with the right algorithm/input metadata but different terminal
source, executable, runtime/child closure, or execution manifest is rejected. -/
theorem goldbach10Pow27ProductionV1_rejects_artifact_substitution
    {statement : RunStatement} {expected : ArtifactHashes}
    (hpins : goldbach10Pow27TerminalArtifactPins = some expected)
    (hdifferent : statement.artifacts ≠ expected) :
    RegisteredInvocation.goldbach10Pow27ProductionV1.statementCheck
      statement ≠ true := by
  intro hcheck
  exact hdifferent (goldbach10Pow27ProductionV1_artifacts hpins hcheck)

/-- Even when the registered algorithm/input and the static host/GPU binary
hashes are unchanged, replacing the complete signed-child identity set changes
the post-run closure commitment and is rejected.  Candidate generation checks
that this `kernelManifestHash` commits all 8,517 child identities together with
the reviewed admission, runtimes, and terminal producer executable. -/
theorem goldbach10Pow27ProductionV1_rejects_childIdentityCommitmentSubstitution
    {statement : RunStatement} {expected : ArtifactHashes}
    (hpins : goldbach10Pow27TerminalArtifactPins = some expected)
    (_halgorithm :
      statement.algorithmId =
        RegisteredAlgorithm.goldbach10Pow27V1.algorithmId)
    (_hinput :
      statement.inputHash =
        RegisteredInvocation.goldbach10Pow27ProductionV1.canonicalInputHash)
    (_hhost :
      statement.artifacts.hostExecutableHash =
        expected.hostExecutableHash)
    (_hdevice :
      statement.artifacts.deviceCubinHash = expected.deviceCubinHash)
    (_hsource :
      statement.artifacts.sourceTreeHash = expected.sourceTreeHash)
    (hcommitment :
      statement.artifacts.kernelManifestHash ≠
        expected.kernelManifestHash) :
    RegisteredInvocation.goldbach10Pow27ProductionV1.statementCheck
      statement ≠ true := by
  intro hcheck
  have hartifacts :=
    goldbach10Pow27ProductionV1_artifacts hpins hcheck
  exact hcommitment (congrArg ArtifactHashes.kernelManifestHash hartifacts)

/-- Before a real reviewed bundle installs pins, production is fail-closed. -/
theorem goldbach10Pow27ProductionV1_unconfigured
    (hpins : goldbach10Pow27TerminalArtifactPins = none)
    (statement : RunStatement) :
    RegisteredInvocation.goldbach10Pow27ProductionV1.statementCheck
      statement = false := by
  simp [statementCheck, artifactCheck, hpins]

/-- The Sqrt218 production invocation cannot accept any statement until a
reviewed deployment and receipt replace its explicit `none` pin. -/
theorem helfgottSqrt218ProductionV1_unconfigured
    (statement : RunStatement) :
    RegisteredInvocation.helfgottSqrt218ProductionV1.statementCheck
      statement = false := by
  simp [statementCheck, artifactCheck,
    helfgottSqrt218ProductionDeployment]

/-- The distinct fixed-width V2 invocation is independently fail-closed until
its reviewed certificate byte length/digest and deployment receipt are
installed. -/
theorem helfgottSqrt218FixedProductionV2_unconfigured
    (statement : RunStatement) :
    RegisteredInvocation.helfgottSqrt218FixedProductionV2.statementCheck
      statement = false := by
  simp [statementCheck, artifactCheck,
    helfgottSqrt218FixedV2ProductionDeployment]

/-- Once a reviewed fixed-width pin is installed, every selectable statement
uses its exact certificate SHA-256 as `inputHash`; no prose descriptor digest
is involved. -/
theorem helfgottSqrt218FixedProductionV2_inputHash
    {statement : RunStatement}
    {reviewed : ReviewedSqrt218FixedV2Deployment}
    (hpins :
      helfgottSqrt218FixedV2ProductionDeployment = some reviewed)
    (hcheck :
      RegisteredInvocation.helfgottSqrt218FixedProductionV2.statementCheck
        statement = true) :
    statement.inputHash = reviewed.certificateSHA256 := by
  have hinput := (statementCheck_sound hcheck).2.2.1
  simpa [canonicalInputHash, hpins] using hinput

/-- One statement can select at most one closed registered invocation.

This proof deliberately enumerates every constructor pair.  Adding a future
invocation therefore makes this theorem fail to elaborate until the new
identity is proved disjoint from every existing identity.  In particular, an
old admitted receipt cannot silently acquire a second `Runs` interpretation
through a colliding registry extension. -/
theorem statementCheck_unique
    {first second : RegisteredInvocation} {statement : RunStatement}
    (hfirst : first.statementCheck statement = true)
    (hsecond : second.statementCheck statement = true) :
    first = second := by
  have hid := (statementCheck_sound hfirst).1.symm.trans
    (statementCheck_sound hsecond).1
  cases first <;> cases second <;>
    simp [algorithm, RegisteredAlgorithm.algorithmId] at hid ⊢

/-- Every closed registered execution relation has at least one safe output.

For the source-scale computations this theorem witnesses the explicit
`"false"` branch.  It is a fail-closed registry-maintenance obligation, but it
does not claim that a successful source-evidence branch is inhabited; that
particular-run fact remains inside the disclosed execution trust boundary. -/
theorem runs_satisfiable (invocation : RegisteredInvocation) :
    ∃ output : String, invocation.Runs output := by
  cases invocation with
  | cubicSumDivThree20000V1 =>
      refine ⟨toString (13334666700000000 : Nat), rfl,
        13334666700000000, ?_, ?_⟩
      · simp [RegisteredAlgorithm.parseCanonicalNat,
          Nat.toNat?_repr]
      · exact RegisteredAlgorithm.cubicSumDivThreeMachine_20000
  | h100FormalPtxConstantOneV1 =>
      exact ⟨RegisteredAlgorithm.h100FormalPtxConstantOneOutput, rfl, rfl⟩
  | cdemTableAbelProductionV2 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | hurstSharedFourResidualProductionV2 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | ch25PsiLemma92ProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | ramareZunigaLemma62ProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | helfgottProp1224ProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | ch25A7BoundaryProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | plattHead2e4ProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | plattDirichletTheorem71ProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | plattTrudgianFiniteRHProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | helfgottPlattGoldbachProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | goldbach10Pow27ProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | helfgottSqrt218ProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | helfgottSqrt218FixedProductionV2 =>
      exact ⟨"false", Or.inl rfl⟩
  | ramareProductionFoldsProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩
  | plattStrongerRangeLiveProductionV1 =>
      exact ⟨"false", rfl, Or.inl rfl⟩

/-- The closed tutorial invocation can return only its one exact canonical
result string. -/
theorem cubicSumDivThree20000V1_output
    {output : String}
    (run : RegisteredInvocation.cubicSumDivThree20000V1.Runs output) :
    output = "13334666700000000" := by
  exact run.1

/-- Mathematical theorem recovered from a successful registered run. -/
theorem cubicSumDivThree20000V1_result
    {output : String}
    (run : RegisteredInvocation.cubicSumDivThree20000V1.Runs output) :
    output = "13334666700000000" ∧
      RegisteredAlgorithm.cubicSumDivThree 20000 =
        (13334666700000000 : ℚ) := by
  exact ⟨cubicSumDivThree20000V1_output run,
    RegisteredAlgorithm.cubicSumDivThree_20000⟩

/-- Exact H100 pilot result bytes and their ordinary Lean binary64 meaning.
The receipt-specific cubin hash is checked by the trusted-compute statement;
it is intentionally not baked into this stable mathematical invocation. -/
theorem h100FormalPtxConstantOneV1_result
    {output : String}
    (run : RegisteredInvocation.h100FormalPtxConstantOneV1.Runs output) :
    output = RegisteredAlgorithm.h100FormalPtxConstantOneOutput ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) := by
  exact ⟨run.2, RegisteredAlgorithm.h100FormalPtxConstantOne_decodes,
    RegisteredAlgorithm.h100FormalPtxConstantOne_decodes⟩

/-- Every non-failure CDEM run exposes a checked integer recurrence
certificate, its local recurrence/fold evidence, and the exact scaled
inequalities derived from those two premises by ordinary Lean. -/
theorem cdemTableAbelProductionV2_result
    {output : String}
    (run : RegisteredInvocation.cdemTableAbelProductionV2.Runs output)
    (hsuccess : output ≠ "false") :
    output =
        toString (Nat.pair
          SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
          SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator) ∧
      SparkInterval.Generated.CDEMAbelProduction.certificate.check = true ∧
      Nonempty
        (SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence
          SparkInterval.Generated.CDEMAbelProduction.certificate) ∧
      SparkInterval.TernaryGoldbach.CDEMAbelSource.ScaledOutputClaim
        SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
        SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator := by
  rcases run.2.resolve_left hsuccess with
    ⟨hparse, _hcheck, hevidence⟩
  rcases hevidence with ⟨evidence⟩
  refine ⟨RegisteredAlgorithm.eq_toString_of_parseCanonicalNat_eq_some hparse,
    SparkInterval.Generated.CDEMAbelProduction.certificate_check,
    ⟨evidence⟩, ?_⟩
  exact
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.scaledOutputClaim_of_checked_local_certificate
      SparkInterval.Generated.CDEMAbelProduction.certificate_check evidence

/-- When the checked returned bytes are the production numerator pair, the
registered run yields the exact two-conjunct CDEM Abel source claim. -/
theorem cdemTableAbelProductionV2_sourceClaim
    {output : String}
    (run : RegisteredInvocation.cdemTableAbelProductionV2.Runs output)
    (houtput : output = RegisteredAlgorithm.cdemTableAbelProductionOutput) :
    SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim := by
  have hsuccess : output ≠ "false" := by
    intro hfailure
    have htext :
        "false" = RegisteredAlgorithm.cdemTableAbelProductionOutput :=
      hfailure.symm.trans houtput
    have hparsed := congrArg String.toNat? htext
    have hfalseParse : String.toNat? "false" = none := by
      apply String.toNat?_eq_none
      rw [Bool.eq_false_iff]
      intro hnat
      have hdigits := (String.isNat_iff.mp hnat).2.1
      have hf := hdigits 'f' (by simp)
      simp at hf
    have hproductionParse :
        String.toNat? RegisteredAlgorithm.cdemTableAbelProductionOutput =
          some (Nat.pair
            SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
            SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget) := by
      change
        (Nat.repr (Nat.pair
          SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
          SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget)).toNat? =
            some (Nat.pair
              SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
              SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget)
      exact Nat.toNat?_repr _
    rw [hfalseParse, hproductionParse] at hparsed
    cases hparsed
  rcases cdemTableAbelProductionV2_result run hsuccess with
    ⟨hencoded, _hcheck, _hevidence, hscaled⟩
  have htext :
      toString (Nat.pair
          SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
          SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator) =
        toString (Nat.pair
          SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
          SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget) :=
    hencoded.symm.trans (houtput.trans (by rfl))
  have hpair :
      Nat.pair
          SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
          SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator =
      Nat.pair
          SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
          SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget := by
    change
      Nat.repr (Nat.pair
          SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
          SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator) =
        Nat.repr (Nat.pair
          SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
          SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget) at htext
    exact Nat.repr_injective htext
  have htargets :
      SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator =
          SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget ∧
        SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator =
          SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget :=
    Nat.pair_eq_pair.mp hpair
  rcases htargets with ⟨hsigned, habsolute⟩
  rw [hsigned, habsolute] at hscaled
  exact
    SparkInterval.TernaryGoldbach.CDEMAbelSource.sourceClaim_of_scaledOutput
      hscaled

/-- A successful shared Hurst receipt yields the exact source predicate at
every natural endpoint.  No receipt can obtain this theorem from the canonical
failure output. -/
theorem hurstSharedFourResidualProductionV2_sourceClaims
    {output : String}
    (run : RegisteredInvocation.hurstSharedFourResidualProductionV2.Runs output)
    (houtput : output = "true") :
    ∀ n, 1 ≤ n →
      n ≤ SparkInterval.TernaryGoldbach.HurstSourceSemantics.sourceLimit →
      ∃ state : SparkInterval.TernaryGoldbach.HurstAffineCertificate.State,
        SparkInterval.TernaryGoldbach.HurstSourceSemantics.SourceRowPredicate
          n state := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, certificate, ⟨sourceEvidence⟩, hcheck⟩
    exact SparkInterval.TernaryGoldbach.HurstSourceSemantics.checked_full_source_claims_of_local
      hcheck sourceEvidence

/-- The same successful registered run yields the five ordinary real
inequalities constituting the four named Hurst-family source atoms. -/
theorem hurstSharedFourResidualProductionV2_realClaims
    {output : String}
    (run : RegisteredInvocation.hurstSharedFourResidualProductionV2.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.RealSourceClaims := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, certificate, ⟨sourceEvidence⟩, hcheck⟩
    exact SparkInterval.TernaryGoldbach.HurstSourceSemantics.checked_real_source_claims_of_local
      hcheck sourceEvidence

/-- Shared source-package form of the same successful Hurst result.  This is
the stable result type intended for a compatible downstream source import. -/
theorem hurstSharedFourResidualProductionV2_sharedRealClaims
    {output : String}
    (run : RegisteredInvocation.hurstSharedFourResidualProductionV2.Runs output)
    (houtput : output = "true") :
    TGComputeContracts.HurstV2.RealSourceClaims := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, certificate, ⟨sourceEvidence⟩, hcheck⟩
    exact SparkInterval.TernaryGoldbach.HurstSourceSemantics.checked_shared_real_source_claims_of_local
      hcheck sourceEvidence

/-- A successful registered CH25 psi run yields the source paper's normalized
real-variable Lemma 9.2 statement.  The canonical failure output proves
nothing and cannot enter this theorem. -/
theorem ch25PsiLemma92ProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.ch25PsiLemma92ProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.SourceClaim := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, ⟨evidence⟩⟩
    exact
      SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.sourceClaim_of_gap_evidence
        evidence

/-- A successful registered Ramaré--Zúñiga run yields the literal
real-variable Lemma 6.2 source proposition.  The success evidence retains the
explicit recurrence-to-von-Mangoldt realization obligation. -/
theorem ramareZunigaLemma62ProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.ramareZunigaLemma62ProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.R2StarSourceSemantics.SourceClaim := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, certificate, ⟨evidence⟩, hcheck⟩
    exact
      SparkInterval.TernaryGoldbach.R2StarSourceSemantics.sourceClaim_of_checked_certificate
        hcheck evidence

/-- A successful registered Proposition 12.2.4 run yields the literal
source-shaped finite-computation proposition.  The success evidence keeps the
MPFR/GMP-to-exact-real realization obligation explicit. -/
theorem helfgottProp1224ProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.helfgottProp1224ProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.SourceClaim := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, certificate, ⟨evidence⟩, hcheck⟩
    exact
      SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.sourceClaim_of_checked_certificate
        hcheck evidence

/-- A successful registered CH25 Lemma A.7 replay yields the literal
source-shaped boundary estimate. The retained evidence binds one exact
checked transcript to its FLINT/Arb-to-Mathlib analytic realization. -/
theorem ch25A7BoundaryProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.ch25A7BoundaryProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, evidence⟩
    exact
      SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence.sourceClaim_of_successEvidence
        evidence

/-- A successful registered Platt-head replay yields one literal Q128 table,
its exact reviewed row commitment, and the source-shaped multiplicity-
preserving zero enumeration. The success evidence retains the Hardy-Z
endpoint and Turing/count realization obligations. -/
theorem plattHead2e4ProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.plattHead2e4ProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.Generated.PlattHeadQ128.table.commitment =
        RegisteredAlgorithm.plattHead2e4IncludedQ128RowsCommitment ∧
      SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.Q128SourceClaim
        SparkInterval.Generated.PlattHeadQ128.table := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, ⟨evidence⟩⟩
    exact ⟨evidence.commitment_eq,
      SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.q128SourceClaim_of_checked_evidence
        evidence⟩

/-- A successful registered Dirichlet finalizer yields the exact two-branch
source proposition of Platt's Theorem 7.1. The success relation retains the
universal even- and odd-conductor verification evidence; a campaign digest or
bounded sample is not enough to inhabit it. -/
theorem plattDirichletTheorem71ProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.plattDirichletTheorem71ProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.Dirichlet.PlattTheorem71DirichletVerification := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, ⟨evidence⟩⟩
    exact SparkInterval.Dirichlet.plattTheorem71_of_source_evidence evidence

/-- A successful registered PT21 run yields the exact positive-height,
open-critical-strip finite-RH source claim. The success evidence keeps the
endpoint enclosures, Hardy-Z bridge, and global zero-count obligation explicit. -/
theorem plattTrudgianFiniteRHProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.plattTrudgianFiniteRHProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.SourceClaim := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, ⟨evidence⟩⟩
    exact
      SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.sourceClaim_of_evidence
        evidence

/-- A successful registered Helfgott--Platt finalizer yields the exact finite
three-prime source claim. The success relation retains both the binary
Goldbach premise and the checked finite prime ladder. -/
theorem helfgottPlattGoldbachProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.helfgottPlattGoldbachProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.SourceClaim := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, ⟨evidence⟩⟩
    exact
      SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.sourceClaim_of_checked_evidence
        evidence

/-- A successful lowered finalizer yields exactly the finite three-prime claim
through `10^27`, not the historical `8.875e30` source proposition. -/
theorem goldbach10Pow27ProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.goldbach10Pow27ProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics.SourceClaim := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, ⟨evidence⟩⟩
    exact
      SparkInterval.TernaryGoldbach.Goldbach10Pow27CampaignSemantics.sourceClaim
        evidence

/-- A successful registered Sqrt218 receipt exposes an exact successful run of
the typed operational checker.  The source theorem is deliberately derived in
`RegisteredSqrt218Certificate`, after importing the generic soundness proof. -/
theorem helfgottSqrt218ProductionV1_operationalSuccess
    {output : String}
    (run : RegisteredInvocation.helfgottSqrt218ProductionV1.Runs output)
    (houtput : output = "true") :
    ∃ archive : SparkInterval.TernaryGoldbach.Sqrt218Operational.Archive,
      SparkInterval.TernaryGoldbach.Sqrt218Operational.run
        RegisteredAlgorithm.helfgottSqrt218ProductionProfile archive = true :=
  RegisteredAlgorithm.helfgottSqrt218_operationalSuccess_of_runs run houtput

/-- A successful registered Ramaré production-fold run yields all three
source-shaped real claims replaced by this campaign: the corrected
first-Mertens seam and anchor through `10^8`, the four Ramaré--Zúñiga
Lemma 7.1 rows, and the `m★` product bound through `1.4·10^8`.

The success relation admits only `FiniteFoldEvidence`: signed integer interval
states and increments, exact fold recurrences, local increment realizations,
and integer guard comparisons.  It has no source-claim field, so an accepted
receipt cannot assert a real inequality directly; the three claims are derived
by ordinary Lean induction in `RamareNativeFoldContracts`. -/
theorem ramareProductionFoldsProductionV1_sourceClaims
    {output : String}
    (run : RegisteredInvocation.ramareProductionFoldsProductionV1.Runs output)
    (houtput : output = "true") :
    SparkInterval.TernaryGoldbach.RamareNativeFoldContracts.SourceClaims := by
  rcases run.2 with hfailed | hsuccess
  · rw [houtput] at hfailed
    contradiction
  · rcases hsuccess with ⟨_, ⟨evidence⟩⟩
    exact
      SparkInterval.TernaryGoldbach.RamareNativeFoldContracts.sourceClaims_of_finiteFoldEvidence
        evidence

end RegisteredInvocation

end SparkInterval.Execution
