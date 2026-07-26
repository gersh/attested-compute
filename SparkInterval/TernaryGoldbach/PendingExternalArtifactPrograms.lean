/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.PlattTheorem71CompactChecker
import SparkInterval.Execution.CanonicalInstalledArtifactProgram
import SparkInterval.Execution.TransitiveChildManifest
import SparkInterval.TernaryGoldbach.GoldbachCompactChecker
import SparkInterval.TernaryGoldbach.R2StarCompactChecker

/-!
# Fail-closed source programs for three not-yet-installed campaigns

This module records the executable source-program boundary for:

* Ramaré--Zúñiga Lemma 6.2;
* Helfgott--Platt Theorem 4.1; and
* Platt Dirichlet Theorem 7.1.

The legacy descriptor checkers are intentionally unchanged.  Their acceptance
relations still require source-scale proposition evidence.  No retained
production artifact currently derives that evidence in Lean, so all three
installed-artifact options below are `none`.  Their source programs are total
and reject the canonical Azure invocation with `artifactAbsentCode`.

The child topology is nevertheless fixed here as data:

* R2Star has one H100 producer child before a confidential-CPU finalizer;
* historical Goldbach has 8,192 H100 binary groups followed by 320
  confidential-CPU ladder groups in the flattened coverage interval
  `[0,8512)`; and
* the current Dirichlet fallback handoff has the q=1 confidential-CPU
  dependency followed by the source-certificate confidential-CPU job before
  the retained postcheck.

`TransitiveChildManifest.check` checks framing, exact ordered topology,
gap-free coverage, nonzero artifact/result/receipt digests, and the complete
predecessor chain.  It does not authenticate signatures or prove artifact
semantics.  The exact remaining obligations are recorded in `ClosureGap`.

These values must not be inserted into the closed-program catalog as concrete
production programs: although they have ordinary (vacuous) refinement proofs,
they have no successful behavior until a complete artifact and its
nonvacuous semantic proof are source-installed.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.PendingExternalArtifactPrograms

open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open SparkInterval.Execution.Architecture.TransitiveChildManifest

/-- Machine-readable record of what prevents a structural manifest from
becoming a mathematical source program. -/
structure ClosureGap where
  completeEnvelopeParser : String
  receiptAuthentication : String
  independentReplay : String
  semanticRefinement : String
  productionArtifact : String
  deriving Repr, DecidableEq

private def rootDigest (tag : UInt8) : Digest32 where
  bytes := (List.replicate 32 tag).toByteArray

def r2StarSpec : Spec where
  campaignTag := 1
  sourceLower := 1
  sourceUpper := 21_000_000_001
  rootDigest := rootDigest 1
  expectedBackends := [.azureNCCadsH100v5]

def historicalGoldbachSpec : Spec where
  campaignTag := 2
  sourceLower := 0
  sourceUpper := 8_512
  rootDigest := rootDigest 2
  expectedBackends :=
    List.replicate 8_192 Backend.azureNCCadsH100v5 ++
      List.replicate 320 Backend.azureSEVSNPCPU

theorem historicalGoldbach_expectedBackendCount :
    historicalGoldbachSpec.expectedBackends.length = 8_512 := by
  change
    (List.replicate 8_192 Backend.azureNCCadsH100v5 ++
      List.replicate 320 Backend.azureSEVSNPCPU).length = 8_512
  rw [List.length_append, List.length_replicate, List.length_replicate]

def plattDirichletSpec : Spec where
  campaignTag := 3
  sourceLower := 0
  sourceUpper := 2
  rootDigest := rootDigest 3
  expectedBackends :=
    [.azureSEVSNPCPU, .azureSEVSNPCPU]

def r2StarManifestCheck (manifest : Manifest) : Bool :=
  check r2StarSpec manifest

def historicalGoldbachManifestCheck (manifest : Manifest) : Bool :=
  check historicalGoldbachSpec manifest

def plattDirichletManifestCheck (manifest : Manifest) : Bool :=
  check plattDirichletSpec manifest

/-! ## Pre-run installed-artifact state -/

def r2StarInstalledArtifact : Option ByteArray := none
def historicalGoldbachInstalledArtifact : Option ByteArray := none
def plattDirichletInstalledArtifact : Option ByteArray := none

/-- Exact current R2Star closure blockers. -/
def r2StarGap : ClosureGap where
  completeEnvelopeParser :=
    "Parse the complete retained H100 export and normalized child receipt, \
not only their digest-only TGCHLD01 manifest."
  receiptAuthentication :=
    "Verify the normalized H100 receipt against a source-pinned production \
verifier key and bind its claim to the retained export."
  independentReplay :=
    "Model the total confidential-CPU factor-support, directed-log, prefix, \
and endpoint replay over every n in [1,21000000001)."
  semanticRefinement :=
    "Prove that replay success constructs \
R2StarSourceSemantics.SourceScaleEvidence; in particular prove each integer \
delta encloses Mathlib r2Coeff and each directed log bound encloses Real.log."
  productionArtifact :=
    "No complete production export or accepted terminal CPU receipt is \
installed in source."

/-- Exact current historical Goldbach closure blockers. -/
def historicalGoldbachGap : ClosureGap where
  completeEnvelopeParser :=
    "Port the strict historical terminal envelope parser, including all \
8512 signed child receipts and retained binary/ladder streams, to the \
source-level certificate format."
  receiptAuthentication :=
    "Verify every child signature and exact algorithm/input/domain/result \
identity; then bind every child result hash to its raw retained branch rows."
  independentReplay :=
    "Port the complete binary aggregate replay and prime-ladder primality and \
coverage replay to a total source checker."
  semanticRefinement :=
    "Prove binary replay success yields BinaryGoldbachClaim and ladder replay \
success yields PrimeLadder.check = true; combine them into \
CheckedSourceEvidence."
  productionArtifact :=
    "No complete 8512-child production handoff or accepted terminal CPU \
receipt is installed in source."

/-- Exact current Platt Theorem 7.1 closure blockers. -/
def plattDirichletGap : ClosureGap where
  completeEnvelopeParser :=
    "Parse the complete q=1 dependency and q=2..400000 character/parity \
certificate archive, rather than the current structural packed-stream \
summary."
  receiptAuthentication :=
    "Verify the transitive q=1 and source-certificate CPU receipts and every \
admitted H100 child, binding each signed result to its retained certificate \
bytes."
  independentReplay :=
    "Complete the total Arb/FLINT-compatible endpoint, completed-sign, \
character-roster, multiplicity, and Turing-count replay for both parity \
branches."
  semanticRefinement :=
    "Construct PlattTheorem71SourceEvidence from data: prove primitive-roster \
completeness, Hardy evaluator links, endpoint containment, and total-zero \
upper bounds for every modulus and primitive character."
  productionArtifact :=
    "The packed H100 path has source_admission_enabled=false and no complete \
production source certificate or terminal CPU receipt is installed."

/-! ## Honest fail-closed program certificates

These certify only that an absent artifact cannot produce a successful output.
They do not discharge any mathematical campaign. -/

def r2StarFailClosed :
    Certificate R2StarCompactChecker.nativeChecker :=
  CanonicalInstalledArtifactProgram.certificate
    R2StarCompactChecker.nativeChecker
    R2StarCompactChecker.canonicalInputBytes
    R2StarCompactChecker.canonicalResultBytes
    r2StarInstalledArtifact decode r2StarManifestCheck
    (CanonicalInstalledArtifactProgram.none_sound
      R2StarCompactChecker.nativeChecker
      R2StarCompactChecker.canonicalInputBytes
      R2StarCompactChecker.canonicalResultBytes
      decode r2StarManifestCheck)

def historicalGoldbachFailClosed :
    Certificate GoldbachCompactChecker.nativeChecker :=
  CanonicalInstalledArtifactProgram.certificate
    GoldbachCompactChecker.nativeChecker
    GoldbachCompactChecker.canonicalInputBytes
    GoldbachCompactChecker.canonicalResultBytes
    historicalGoldbachInstalledArtifact decode historicalGoldbachManifestCheck
    (CanonicalInstalledArtifactProgram.none_sound
      GoldbachCompactChecker.nativeChecker
      GoldbachCompactChecker.canonicalInputBytes
      GoldbachCompactChecker.canonicalResultBytes
      decode historicalGoldbachManifestCheck)

def plattDirichletFailClosed :
    Certificate
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.nativeChecker :=
  CanonicalInstalledArtifactProgram.certificate
    SparkInterval.Dirichlet.PlattTheorem71CompactChecker.nativeChecker
    SparkInterval.Dirichlet.PlattTheorem71CompactChecker.canonicalInputBytes
    SparkInterval.Dirichlet.PlattTheorem71CompactChecker.canonicalResultBytes
    plattDirichletInstalledArtifact decode plattDirichletManifestCheck
    (CanonicalInstalledArtifactProgram.none_sound
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.nativeChecker
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.canonicalInputBytes
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.canonicalResultBytes
      decode plattDirichletManifestCheck)

@[simp] theorem r2Star_rejects_canonical :
    r2StarFailClosed.program.run
      R2StarCompactChecker.canonicalInputBytes =
        .rejected CanonicalInstalledArtifactProgram.artifactAbsentCode := by
  simp [r2StarFailClosed, CanonicalInstalledArtifactProgram.certificate,
    CanonicalInstalledArtifactProgram.program,
    r2StarInstalledArtifact]

@[simp] theorem historicalGoldbach_rejects_canonical :
    historicalGoldbachFailClosed.program.run
      GoldbachCompactChecker.canonicalInputBytes =
        .rejected CanonicalInstalledArtifactProgram.artifactAbsentCode := by
  simp [historicalGoldbachFailClosed,
    CanonicalInstalledArtifactProgram.certificate,
    CanonicalInstalledArtifactProgram.program,
    historicalGoldbachInstalledArtifact]

@[simp] theorem plattDirichlet_rejects_canonical :
    plattDirichletFailClosed.program.run
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.canonicalInputBytes =
        .rejected CanonicalInstalledArtifactProgram.artifactAbsentCode := by
  simp [plattDirichletFailClosed,
    CanonicalInstalledArtifactProgram.certificate,
    CanonicalInstalledArtifactProgram.program,
    plattDirichletInstalledArtifact]

end SparkInterval.TernaryGoldbach.PendingExternalArtifactPrograms
