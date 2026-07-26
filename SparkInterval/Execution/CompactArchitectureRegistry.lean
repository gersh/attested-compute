/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.Execution.CompactArchitectureReceipt

/-!
# Closed architecture invocations for the ternary-Goldbach residuals

This is the lightweight, production-data-free registry used by the compact
architecture-receipt boundary.  It deliberately does not import
`RegisteredAlgorithm`, any generated certificate table, or any
application-level analytic proposition.

There are thirteen named external atoms, but only ten distinct physical
external campaigns: the squarefree, Mertens, and two little-Mertens atoms
share one four-coordinate Hurst run.  Two further invocations are kept out of
that external catalog:

* one aggregate CPU-finalizer campaign for all 15 historically
  native-generated ternary-Goldbach families; and
* one separately classified compact fallback for the three
  `TGNativeCertificates.Ramare` production folds.

The aggregate campaign is only a closed execution identity.  Each downstream
family adapter must still fix its own exact decision bundle and prove both
architecture-to-checker refinement and checker-to-proposition soundness.
Its existence therefore does not turn the 1,371 historical generated roots
into caller-selectable propositions.  All sets are closed.  A receipt caller
cannot choose a new claim tag, computation, target, formal machine,
measurement scheme, entry point, or compact pin bundle.

Every installed `ReviewedArchitectureRun` contains compact identity
information, the small exact executable/result artifacts, and one exact
formal `ArchitectureSemantics`; the potentially huge input and the complete
machine trace remain existential inside
`CompactInputReceiptExecutionFact`.  Installations are closed source
definitions and currently fail closed as `none`.  Replacing one `none` by
`some reviewed` is a trust-boundary review event and is permitted only after:

* the exact formal CPU or H100 model exists;
* the executable-to-checker refinement has been proved;
* the signed receipt, launcher, closure metadata, executable, input, and
  result pins have been jointly reviewed; and
* the corresponding source-level invocation adapter has been checked.

This file defines no axiom.  `RegisteredArchitectureOutcomes` is the exact
closed projection that the existing single certificate axiom can eventually
return.  Its public constructor is harmless: ordinary Lean code can construct
it only by supplying each requested exact architecture execution.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture

/-! ## Closed mathematical atom catalog -/

/-- Every external/source atom currently named by the ternary-Goldbach
dependency catalog.

This is an identity tag, not a caller-populated proposition.  The separate
application adapter is responsible for mapping each constructor to its exact
Lean claim. -/
inductive TernaryGoldbachExternalAtom where
  | ch25A7Boundary
  | ch25Psi1e13
  | plattHead2e4
  | plattTrudgianRH3e12
  | helfgottProp1224
  | cdemSquarefree
  | cdemTableAbel
  | mertensHurst
  | ramareZunigaLemma62
  | helfgottPlattTheorem41
  | plattDirichletTheorem71
  | plattLittleMertens211
  | plattLittleMertensStronger
  deriving Repr, DecidableEq, BEq

namespace TernaryGoldbachExternalAtom

/-- Stable catalog identifier used by the human-facing external-atom
inventory. -/
def catalogId : TernaryGoldbachExternalAtom → String
  | .ch25A7Boundary => "ch25-a7-boundary"
  | .ch25Psi1e13 => "ch25-psi-1e13"
  | .plattHead2e4 => "platt-head-2e4"
  | .plattTrudgianRH3e12 => "platt-trudgian-rh-3e12"
  | .helfgottProp1224 => "helfgott-prop-12-2-4"
  | .cdemSquarefree => "cdem-squarefree"
  | .cdemTableAbel => "cdem-table-abel"
  | .mertensHurst => "mertens-hurst"
  | .ramareZunigaLemma62 => "ramare-zuniga-lemma-6-2"
  | .helfgottPlattTheorem41 => "helfgott-platt-theorem-4-1"
  | .plattDirichletTheorem71 => "platt-dirichlet-theorem-7-1"
  | .plattLittleMertens211 => "platt-little-mertens-2-11"
  | .plattLittleMertensStronger => "platt-little-mertens-stronger"

/-- Exact declaration name expected on the `claude_math` side.

These strings are audit metadata only.  The eventual application adapter
must prove the constructor-by-constructor proposition mapping; string
equality never creates a theorem. -/
def leanDeclaration : TernaryGoldbachExternalAtom → String
  | .ch25A7Boundary =>
      "AnalyticNT.ChebyshevPsi.finite_check_ch25_lemA7_arb_boundary_source"
  | .ch25Psi1e13 =>
      "AnalyticNT.ChebyshevPsi.finite_check_ch25_lemma_9_2_psi_source"
  | .plattHead2e4 =>
      "AnalyticNT.ChebyshevPsi.finite_check_platt_zero_enumeration_2e4_source"
  | .plattTrudgianRH3e12 =>
      "AnalyticNT.ChebyshevPsi.finite_check_platt_trudgian_rh_zeta_3e12"
  | .helfgottProp1224 =>
      "AnalyticNT.LargeSieve.finite_check_helfgott_prop_12_2_4_computation_source"
  | .cdemSquarefree =>
      "MathExtras.CohenDressElMarraki.reproducibleSquarefree_verifier_output"
  | .cdemTableAbel =>
      "MathExtras.CohenDressElMarraki.reproducibleTable_abel_verifier_output"
  | .mertensHurst =>
      "MathExtras.EffectiveMertensDecay.mertensM_hurst_sqrt_source"
  | .ramareZunigaLemma62 =>
      "MathExtras.RamareMertens2025.ramare_zuniga_2024_lemma_6_2_source"
  | .helfgottPlattTheorem41 =>
      "Math.Problems.TernaryGoldbach.helfgott_platt_theorem_4_1_source"
  | .plattDirichletTheorem71 =>
      "MathExtras.Helfgott.MajorArcsStart.platt_theorem_7_1_dirichlet_verification_source"
  | .plattLittleMertens211 =>
      "MathExtras.Helfgott.Section24.residual_platt_2_11"
  | .plattLittleMertensStronger =>
      "MathExtras.Helfgott.Section24.residual_platt_stronger_range"

/-- The complete closed atom roster, in the same order as
`TERNARY_GOLDBACH_EXTERNAL_ATOMS.json`. -/
def all : List TernaryGoldbachExternalAtom :=
  [.ch25A7Boundary, .ch25Psi1e13, .plattHead2e4,
    .plattTrudgianRH3e12, .helfgottProp1224, .cdemSquarefree,
    .cdemTableAbel, .mertensHurst, .ramareZunigaLemma62,
    .helfgottPlattTheorem41, .plattDirichletTheorem71,
    .plattLittleMertens211, .plattLittleMertensStronger]

end TernaryGoldbachExternalAtom

/-! ## Closed physical campaign catalog -/

/-- Distinct terminal computations whose receipts can discharge the thirteen
atom tags.

The terminal CPU finalizers for the two hybrid campaigns must verify their
complete child-receipt DAG.  Merely running the finalizer without that
ordinary checker/refinement theorem is insufficient. -/
inductive RegisteredArchitectureInvocation where
  | ch25A7BoundaryProductionV1
  | ch25PsiLemma92ProductionV1
  | plattHead2e4ProductionV1
  | plattTrudgianFiniteRHProductionV1
  | helfgottProp1224ProductionV1
  | hurstSharedFourResidualProductionV2
  | cdemTableAbelProductionV2
  | ramareZunigaLemma62ProductionV1
  | helfgottPlattGoldbachProductionV1
  | plattDirichletTheorem71ProductionV1
  | nativeGeneratedAggregateProductionV1
  | ramareProductionFoldsCompactV1
  deriving Repr, DecidableEq, BEq

/-- Classification of a physical invocation's mathematical role.

The native-family fallback is kept out of the thirteen-source-atom catalog
even though it reuses the same physical-outcome projection and sole trust
boundary. -/
inductive RegisteredArchitectureClaimKind where
  | externalAtomCampaign
  | nativeGeneratedAggregate
  | nativeFamilyFallback
  deriving Repr, DecidableEq, BEq

/-- Physical placement of the complete campaign.

For a hybrid campaign the compact architecture fact below is the Azure CPU
terminal execution.  The registered terminal checker must authenticate and
verify every H100 child receipt before accepting. -/
inductive ExecutionPlacement where
  | azureConfidentialCPU
  | h100ConfidentialGPU
  | h100ProducersAzureCPUFinalizer
  deriving Repr, DecidableEq, BEq

namespace RegisteredArchitectureInvocation

/-- The ten campaigns which discharge the thirteen external/source atoms. -/
def externalCampaigns : List RegisteredArchitectureInvocation :=
  [.ch25A7BoundaryProductionV1, .ch25PsiLemma92ProductionV1,
    .plattHead2e4ProductionV1, .plattTrudgianFiniteRHProductionV1,
    .helfgottProp1224ProductionV1,
    .hurstSharedFourResidualProductionV2, .cdemTableAbelProductionV2,
    .ramareZunigaLemma62ProductionV1,
    .helfgottPlattGoldbachProductionV1,
    .plattDirichletTheorem71ProductionV1]

/-- One closed aggregate CPU-finalizer campaign for the 15 native-generated
families in the authoritative ternary-Goldbach trust-boundary snapshot.

The terminal executable may validate signed CPU/H100 child results, but its
ordinary refinement theorem must establish the exact fixed family decision
bundle.  This list is separate from both named external campaigns and the
specialized long-fold fallback. -/
def nativeAggregateCampaigns : List RegisteredArchitectureInvocation :=
  [.nativeGeneratedAggregateProductionV1]

/-- Compact fallbacks for otherwise routine native-generated leaves.

This list has no external-atom constructors.  Adding a second member is an
explicit trust-policy change, not an incidental extension of the external
catalog. -/
def nativeFamilyFallbacks : List RegisteredArchitectureInvocation :=
  [.ramareProductionFoldsCompactV1]

/-- Complete closed physical roster: ten external campaigns, one aggregate
native-generated campaign, and one specialized native-family fallback. -/
def all : List RegisteredArchitectureInvocation :=
  externalCampaigns ++ nativeAggregateCampaigns ++ nativeFamilyFallbacks

/-- Closed mathematical role of each physical invocation. -/
def claimKind :
    RegisteredArchitectureInvocation → RegisteredArchitectureClaimKind
  | .nativeGeneratedAggregateProductionV1 => .nativeGeneratedAggregate
  | .ramareProductionFoldsCompactV1 => .nativeFamilyFallback
  | _ => .externalAtomCampaign

/-- Stable architecture-invocation identifier.  This is intentionally
separate from a mathematical proposition. -/
def invocationId : RegisteredArchitectureInvocation → String
  | .ch25A7BoundaryProductionV1 => "ch25-a7-boundary-production-v1"
  | .ch25PsiLemma92ProductionV1 => "ch25-psi-lemma-9-2-production-v1"
  | .plattHead2e4ProductionV1 => "platt-head-2e4-production-v1"
  | .plattTrudgianFiniteRHProductionV1 =>
      "platt-trudgian-finite-rh-production-v1"
  | .helfgottProp1224ProductionV1 =>
      "helfgott-prop-12-2-4-production-v1"
  | .hurstSharedFourResidualProductionV2 =>
      "hurst-shared-four-residual-production-v2"
  | .cdemTableAbelProductionV2 => "cdem-table-abel-production-v2"
  | .ramareZunigaLemma62ProductionV1 =>
      "ramare-zuniga-lemma-6-2-production-v1"
  | .helfgottPlattGoldbachProductionV1 =>
      "helfgott-platt-theorem-4-1-production-v1"
  | .plattDirichletTheorem71ProductionV1 =>
      "platt-dirichlet-theorem-7-1-production-v1"
  | .nativeGeneratedAggregateProductionV1 =>
      "ternary-goldbach-native-generated-aggregate-production-v1"
  | .ramareProductionFoldsCompactV1 =>
      "ramare-production-folds-compact-v1"

/-- Stable invocation identifiers are pairwise distinct.

This theorem is part of the statement-selection firewall: a single accepted
statement cannot be installed under two mathematical invocation tags. -/
theorem invocationId_injective :
    Function.Injective invocationId := by
  intro left right equal
  cases left <;> cases right <;>
    simp [invocationId] at equal ⊢

/-- Closed producer/finalizer placement.

Every proof-authorizing terminal is an Azure confidential CPU.  Campaigns
which benefit from H100 throughput use the GPU only as a child producer; the
measured CPU finalizer authenticates and checks every child artifact before
returning the fixed result. -/
def placement : RegisteredArchitectureInvocation → ExecutionPlacement
  | .ramareZunigaLemma62ProductionV1
  | .helfgottPlattGoldbachProductionV1
  | .plattDirichletTheorem71ProductionV1
  | .nativeGeneratedAggregateProductionV1 =>
      .h100ProducersAzureCPUFinalizer
  | _ => .azureConfidentialCPU

/-- Formal architecture target of the terminal receipt.

The hybrid campaigns end in a measured CPU verifier.  Their H100 children
remain separately signed inputs to that verifier rather than being silently
identified with the CPU trace. -/
def terminalTarget :
    RegisteredArchitectureInvocation → ExecutionTarget :=
  fun _ => .azureSEVSNPCPU

/-- Confidential-compute policy required by the terminal target. -/
def terminalTrust :
    RegisteredArchitectureInvocation → TrustProfile :=
  fun _ => .azureSEVSNPConfidentialCompute

/-- Every closed ternary-Goldbach invocation has the common formal CPU
terminal.  Heavy GPU work is represented only in child artifacts checked by
that terminal. -/
@[simp] theorem terminalTarget_eq_azureSEVSNPCPU
    (invocation : RegisteredArchitectureInvocation) :
    invocation.terminalTarget = .azureSEVSNPCPU :=
  rfl

/-- Every closed invocation uses the matching Azure confidential-compute
terminal policy. -/
@[simp] theorem terminalTrust_eq_azureSEVSNP
    (invocation : RegisteredArchitectureInvocation) :
    invocation.terminalTrust = .azureSEVSNPConfidentialCompute :=
  rfl

/-- The atom tags discharged by one successful, semantically refined
physical campaign.  No theorem follows from this list alone. -/
def claims :
    RegisteredArchitectureInvocation → List TernaryGoldbachExternalAtom
  | .ch25A7BoundaryProductionV1 => [.ch25A7Boundary]
  | .ch25PsiLemma92ProductionV1 => [.ch25Psi1e13]
  | .plattHead2e4ProductionV1 => [.plattHead2e4]
  | .plattTrudgianFiniteRHProductionV1 => [.plattTrudgianRH3e12]
  | .helfgottProp1224ProductionV1 => [.helfgottProp1224]
  | .hurstSharedFourResidualProductionV2 =>
      [.cdemSquarefree, .mertensHurst, .plattLittleMertens211,
        .plattLittleMertensStronger]
  | .cdemTableAbelProductionV2 => [.cdemTableAbel]
  | .ramareZunigaLemma62ProductionV1 => [.ramareZunigaLemma62]
  | .helfgottPlattGoldbachProductionV1 =>
      [.helfgottPlattTheorem41]
  | .plattDirichletTheorem71ProductionV1 =>
      [.plattDirichletTheorem71]
  | .nativeGeneratedAggregateProductionV1 => []
  | .ramareProductionFoldsCompactV1 => []

end RegisteredArchitectureInvocation

namespace TernaryGoldbachExternalAtom

/-- Closed atom-to-physical-campaign selection.  In particular, the four
Hurst claims cannot be redirected to four caller-chosen computations. -/
def physicalInvocation :
    TernaryGoldbachExternalAtom → RegisteredArchitectureInvocation
  | .ch25A7Boundary => .ch25A7BoundaryProductionV1
  | .ch25Psi1e13 => .ch25PsiLemma92ProductionV1
  | .plattHead2e4 => .plattHead2e4ProductionV1
  | .plattTrudgianRH3e12 => .plattTrudgianFiniteRHProductionV1
  | .helfgottProp1224 => .helfgottProp1224ProductionV1
  | .cdemSquarefree
  | .mertensHurst
  | .plattLittleMertens211
  | .plattLittleMertensStronger =>
      .hurstSharedFourResidualProductionV2
  | .cdemTableAbel => .cdemTableAbelProductionV2
  | .ramareZunigaLemma62 =>
      .ramareZunigaLemma62ProductionV1
  | .helfgottPlattTheorem41 =>
      .helfgottPlattGoldbachProductionV1
  | .plattDirichletTheorem71 =>
      .plattDirichletTheorem71ProductionV1

/-- Every atom occurs in the closed claim roster of its selected physical
invocation. -/
theorem mem_claims_physicalInvocation
    (atom : TernaryGoldbachExternalAtom) :
    atom ∈ atom.physicalInvocation.claims := by
  cases atom <;> simp [physicalInvocation,
    RegisteredArchitectureInvocation.claims]

/-- Conversely, a claim roster cannot redirect an atom to a different
physical invocation. -/
theorem physicalInvocation_eq_of_mem_claims
    {atom : TernaryGoldbachExternalAtom}
    {invocation : RegisteredArchitectureInvocation}
    (member : atom ∈ invocation.claims) :
    atom.physicalInvocation = invocation := by
  cases invocation <;> cases atom <;>
    simp [RegisteredArchitectureInvocation.claims,
      physicalInvocation] at member ⊢

end TernaryGoldbachExternalAtom

/-! ## Reviewed compact registrations -/

/-- The one measurement function permitted by this catalog.

The pure Lean SHA-256 implementation gives exact agreement between retained
bytes and digest strings.  Cryptographic collision/second-preimage resistance
for an external digest remains part of receipt admission, as documented by
`CompactArchitectureReceipt`. -/
def registeredSHA256MeasurementScheme : MeasurementScheme where
  schemeId := "sparkinterval.sha256-byte-array.v1"
  digestBytes := SparkInterval.Certificate.SHA256.digestByteArray

/-- Closed, review-installed physical identity for one invocation.

`machine` is a complete exact formal semantics, not just a caller-provided
semantics identifier.  The dependent target equality prevents an x86 receipt
from selecting an H100 invocation (or conversely).  The signed closure pin
binds the formal-model identity and the distinct modeled executable where the
historical `RunStatement` has no dedicated fields for them.

Only the small reviewed executable and native result are retained exactly.
The public identity remains their compact length/digest pins.  No production
input, state, or instruction trace is a field. -/
structure ReviewedArchitectureRun
    (invocation : RegisteredArchitectureInvocation) where
  receiptHash : Digest
  algorithmId : String
  algorithmIdMatchesInvocation :
    algorithmId = invocation.invocationId
  algorithmHash : Digest
  parametersHash : Digest
  domainHash : Digest
  statementResult : String
  nonce : String
  targetProfileHash : Digest
  trustProfileHash : Digest
  artifacts : ArtifactHashes
  executionClosure : CompactBlobPin
  launcher : CompactBlobPin
  machine : ArchitectureSemantics
  machineTarget :
    machine.target = invocation.terminalTarget
  entryPoint : String
  executablePin : CompactBlobPin
  inputPin : CompactBlobPin
  resultPin : CompactBlobPin
  executableArtifact : MeasuredBlob
  resultArtifact : MeasuredBlob
  receiptHashPresent : receiptHash ≠ ""
  algorithmIdPresent : algorithmId ≠ ""
  algorithmHashPresent : algorithmHash ≠ ""
  parametersHashPresent : parametersHash ≠ ""
  domainHashPresent : domainHash ≠ ""
  statementResultPresent : statementResult ≠ ""
  noncePresent : nonce ≠ ""
  targetProfileHashPresent : targetProfileHash ≠ ""
  trustProfileHashPresent : trustProfileHash ≠ ""
  executionClosurePresent : executionClosure.digest ≠ ""
  launcherPresent : launcher.digest ≠ ""
  semanticsPresent : machine.semanticsId ≠ ""
  entryPointPresent : entryPoint ≠ ""
  executablePresent : executablePin.digest ≠ ""
  inputPresent : inputPin.digest ≠ ""
  resultPresent : resultPin.digest ≠ ""
  executionClosureNonempty : 0 < executionClosure.byteLength
  launcherNonempty : 0 < launcher.byteLength
  executableNonempty : 0 < executablePin.byteLength
  inputNonempty : 0 < inputPin.byteLength
  resultNonempty : 0 < resultPin.byteLength
  executableExact :
    executableArtifact.Exact registeredSHA256MeasurementScheme
  executableLength :
    executableArtifact.byteLength = executablePin.byteLength
  executableDigest :
    executableArtifact.digest = executablePin.digest
  resultExact :
    resultArtifact.Exact registeredSHA256MeasurementScheme
  resultLength :
    resultArtifact.byteLength = resultPin.byteLength
  resultDigest :
    resultArtifact.digest = resultPin.digest
  resultEncoding :
    resultArtifact.bytes = statementResult.toUTF8
  closureArtifact :
    executionClosure.digest = artifacts.kernelManifestHash
  launcherArtifact :
    launcher.digest = artifacts.hostExecutableHash
  h100ExecutableArtifact :
    invocation.terminalTarget = .nvidiaH100SM90 →
      executablePin.digest = artifacts.deviceCubinHash

namespace ReviewedArchitectureRun

/-- Compact run identity selected by the closed registration. -/
def compactPins
    {invocation : RegisteredArchitectureInvocation}
    (reviewed : ReviewedArchitectureRun invocation) : CompactRunPins where
  measurementSchemeId := registeredSHA256MeasurementScheme.schemeId
  semanticsId := reviewed.machine.semanticsId
  target := reviewed.machine.target
  entryPoint := reviewed.entryPoint
  executable := reviewed.executablePin
  input := reviewed.inputPin
  result := reviewed.resultPin

/-- The measurement function cannot be selected by a receipt caller. -/
@[simp] theorem compactPins_measurementSchemeId
    {invocation : RegisteredArchitectureInvocation}
    (reviewed : ReviewedArchitectureRun invocation) :
    reviewed.compactPins.measurementSchemeId =
      registeredSHA256MeasurementScheme.schemeId :=
  rfl

/-- The formal semantics identifier comes from the exact closed machine, not
from signed free-form metadata. -/
@[simp] theorem compactPins_semanticsId
    {invocation : RegisteredArchitectureInvocation}
    (reviewed : ReviewedArchitectureRun invocation) :
    reviewed.compactPins.semanticsId = reviewed.machine.semanticsId :=
  rfl

/-- The modeled run target is exactly the target of the closed invocation. -/
theorem compactPins_target
    {invocation : RegisteredArchitectureInvocation}
    (reviewed : ReviewedArchitectureRun invocation) :
    reviewed.compactPins.target = invocation.terminalTarget :=
  reviewed.machineTarget

/-- Exact local validation of the retained static executable and result
against their compact public pins. -/
theorem staticArtifactsPinned
    {invocation : RegisteredArchitectureInvocation}
    (reviewed : ReviewedArchitectureRun invocation) :
    StaticArtifactsPinned registeredSHA256MeasurementScheme
      reviewed.compactPins reviewed.executableArtifact
      reviewed.resultArtifact := by
  exact {
    executableExact := reviewed.executableExact
    executableLength := reviewed.executableLength
    executableDigest := reviewed.executableDigest
    resultExact := reviewed.resultExact
    resultLength := reviewed.resultLength
    resultDigest := reviewed.resultDigest
  }

/-- Exact signed-statement fields required to select this physical run.

The modeled CPU pure-entry ELF may differ from the measured launcher in
`artifacts.hostExecutableHash`; the signed execution-closure artifact binds
that relationship.  On H100, the modeled executable is additionally required
to be the exact signed cubin. -/
structure StatementBound
    {invocation : RegisteredArchitectureInvocation}
    (reviewed : ReviewedArchitectureRun invocation)
    (statement : RunStatement) : Prop where
  algorithmId : statement.algorithmId = reviewed.algorithmId
  algorithmHash : statement.algorithmHash = reviewed.algorithmHash
  inputHash : statement.inputHash = reviewed.inputPin.digest
  parametersHash : statement.parametersHash = reviewed.parametersHash
  domainHash : statement.domainHash = reviewed.domainHash
  result : statement.result = reviewed.statementResult
  outputHash : statement.outputHash = reviewed.resultPin.digest
  nonce : statement.nonce = reviewed.nonce
  target : statement.target = invocation.terminalTarget
  targetProfile : statement.targetProfileHash = reviewed.targetProfileHash
  trust : statement.trust = invocation.terminalTrust
  trustProfile : statement.trustProfileHash = reviewed.trustProfileHash
  artifacts : statement.artifacts = reviewed.artifacts

end ReviewedArchitectureRun

namespace RegisteredArchitectureInvocation

/-- Review-installed architecture closure.

Every branch is intentionally `none` until an exact machine model, proof
closure, and successful appraised production receipt are available.  Keeping
the selector closed is essential: replacing it with a function argument would
let a caller choose permissive semantics or unrelated pins. -/
def reviewedRun :
    (invocation : RegisteredArchitectureInvocation) →
      Option (ReviewedArchitectureRun invocation)
  | .ch25A7BoundaryProductionV1 => none
  | .ch25PsiLemma92ProductionV1 => none
  | .plattHead2e4ProductionV1 => none
  | .plattTrudgianFiniteRHProductionV1 => none
  | .helfgottProp1224ProductionV1 => none
  | .hurstSharedFourResidualProductionV2 => none
  | .cdemTableAbelProductionV2 => none
  | .ramareZunigaLemma62ProductionV1 => none
  | .helfgottPlattGoldbachProductionV1 => none
  | .plattDirichletTheorem71ProductionV1 => none
  | .nativeGeneratedAggregateProductionV1 => none
  | .ramareProductionFoldsCompactV1 => none

/-- The complete closed selector is presently fail closed.

This theorem is intentionally universal over the constructor type, rather
than being inferred by a text audit which counts `none` branches.  Installing
the first reviewed production run must invalidate this theorem and advance
the corresponding receipt/refinement status in the trust-boundary catalog. -/
theorem reviewedRun_currently_none
    (invocation : RegisteredArchitectureInvocation) :
    invocation.reviewedRun = none := by
  cases invocation <;> rfl

/-- Closed statement/receipt selector used at the sole trusted handoff. -/
def ReceiptSelected
    (invocation : RegisteredArchitectureInvocation)
    (statement : RunStatement)
    (receiptHash : Digest) : Prop :=
  ∃ reviewed : ReviewedArchitectureRun invocation,
    invocation.reviewedRun = some reviewed ∧
      receiptHash = reviewed.receiptHash ∧
      reviewed.StatementBound statement

/-- One accepted statement cannot select two different closed invocations.

The reviewed algorithm identifier is tied to the constructor's injective
`invocationId`, rather than being unconstrained source metadata.  This closes
the cross-invocation aliasing route while still allowing different receipts
for different statements. -/
theorem invocation_eq_of_receiptSelected
    {left right : RegisteredArchitectureInvocation}
    {statement : RunStatement}
    {leftHash rightHash : Digest}
    (leftSelected : left.ReceiptSelected statement leftHash)
    (rightSelected : right.ReceiptSelected statement rightHash) :
    left = right := by
  rcases leftSelected with
    ⟨leftReviewed, _leftInstalled, _leftReceipt, leftBound⟩
  rcases rightSelected with
    ⟨rightReviewed, _rightInstalled, _rightReceipt, rightBound⟩
  apply invocationId_injective
  exact
    leftReviewed.algorithmIdMatchesInvocation.symm.trans <|
      leftBound.algorithmId.symm.trans <|
        rightBound.algorithmId.trans
          rightReviewed.algorithmIdMatchesInvocation

/-- Exact low-level result of one selected physical run.

The only large object is existentially hidden inside
`CompactInputReceiptExecutionFact`: neither constructing this proposition
from the future receipt axiom nor consuming it traverses production input or
trace bytes locally. -/
def PhysicalOutcome
    (invocation : RegisteredArchitectureInvocation)
    (statement : RunStatement)
    (receiptHash : Digest) : Prop :=
  ∃ reviewed : ReviewedArchitectureRun invocation,
    invocation.reviewedRun = some reviewed ∧
      receiptHash = reviewed.receiptHash ∧
      reviewed.StatementBound statement ∧
      CompactInputReceiptExecutionFact receiptHash
        registeredSHA256MeasurementScheme reviewed.machine
        reviewed.compactPins reviewed.executableArtifact
        reviewed.resultArtifact

/-- A physical outcome always carries the exact closed selector that made it
eligible. -/
theorem receiptSelected_of_physicalOutcome
    {invocation : RegisteredArchitectureInvocation}
    {statement : RunStatement}
    {receiptHash : Digest}
    (outcome : invocation.PhysicalOutcome statement receiptHash) :
    invocation.ReceiptSelected statement receiptHash := by
  rcases outcome with
    ⟨reviewed, selected, receipt, statementBound, _execution⟩
  exact ⟨reviewed, selected, receipt, statementBound⟩

/-- Fail closed before any reviewed architecture registration is installed.
-/
theorem not_receiptSelected_of_reviewedRun_eq_none
    {invocation : RegisteredArchitectureInvocation}
    {statement : RunStatement}
    {receiptHash : Digest}
    (unavailable : invocation.reviewedRun = none) :
    ¬ invocation.ReceiptSelected statement receiptHash := by
  intro selected
  rcases selected with ⟨reviewed, installed, _receipt, _statement⟩
  rw [unavailable] at installed
  contradiction

/-- Consequently a missing registration cannot produce an architecture
execution fact, regardless of statement or receipt data. -/
theorem not_physicalOutcome_of_reviewedRun_eq_none
    {invocation : RegisteredArchitectureInvocation}
    {statement : RunStatement}
    {receiptHash : Digest}
    (unavailable : invocation.reviewedRun = none) :
    ¬ invocation.PhysicalOutcome statement receiptHash := by
  intro outcome
  exact not_receiptSelected_of_reviewedRun_eq_none unavailable
    (receiptSelected_of_physicalOutcome outcome)

end RegisteredArchitectureInvocation

/-- Axiom-free shape of the closed registered projection for one accepted
certificate.

The future single trust axiom may return this structure in addition to (or,
after migration, instead of) the historical application-level projection.
It must instantiate `statement` and `receiptHash` from the already accepted
certificate.  Callers may quantify over the closed invocation type, but they
cannot add a constructor or install a machine/pin bundle. -/
structure RegisteredArchitectureOutcomes
    (statement : RunStatement)
    (receiptHash : Digest) : Prop where
  registered :
    ∀ invocation : RegisteredArchitectureInvocation,
      invocation.ReceiptSelected statement receiptHash →
        invocation.PhysicalOutcome statement receiptHash

namespace RegisteredArchitectureOutcomes

/-- Select one exact physical fact from the universal closed projection. -/
theorem physicalOutcome
    {statement : RunStatement}
    {receiptHash : Digest}
    (outcomes : RegisteredArchitectureOutcomes statement receiptHash)
    (invocation : RegisteredArchitectureInvocation)
    (selected : invocation.ReceiptSelected statement receiptHash) :
    invocation.PhysicalOutcome statement receiptHash :=
  outcomes.registered invocation selected

end RegisteredArchitectureOutcomes

namespace TernaryGoldbachExternalAtom

/-- Physical outcome required for one named atom.  The atom fixes the
invocation; the caller supplies neither a machine nor a claim proposition. -/
def PhysicalOutcome
    (atom : TernaryGoldbachExternalAtom)
    (statement : RunStatement)
    (receiptHash : Digest) : Prop :=
  atom.physicalInvocation.PhysicalOutcome statement receiptHash

end TernaryGoldbachExternalAtom

end SparkInterval.Execution.Architecture
