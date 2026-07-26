/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.ArchitectureExecutionAdapter

/-!
# Exact Sqrt218 execution-closure identity

This module binds one small canonical physical-launch metadata object to:

* the execution-closure digest in the signed `RunStatement`;
* the source, compiler, formal-model, target, measured launcher, versioned
  launcher/control contract, ABI, pure-entry ELF, and entry identities
  expected by `NativeImplementationIdentity`; and
* the exact `MeasuredRun` consumed by the architecture semantics.

The complete canonical metadata bytes and the parsed metadata object are both
retained.  Nothing here parses a production archive, evaluates the Sqrt218
checker, or replays production arithmetic.

The proof establishes literal field equalities and literal SHA-256 equality.
It does not prove SHA-256 collision or second-preimage resistance.  Until a
future receipt format signs these canonical bytes directly, interpreting the
signed digest as uniquely identifying the retained bytes has that standard
cryptographic residual assumption.

Likewise, compiler correctness, loader/ABI correctness, ISA-model adequacy,
and physical CPU conformance are not consequences of metadata.  They remain
the separately visible architecture/refinement premises.

The legacy V1 projection did **not** contain a launcher/loader artifact digest
or a pure-entry launch-contract digest.  It is represented below only as an
explicitly ineligible envelope alternative.  `ExactMetadataBinding` accepts
V2 metadata, so old V1 bytes cannot silently satisfy the physical-launch
boundary.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance

open SparkInterval.Execution
open SparkInterval.Execution.Architecture
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

namespace ExecutionClosureIdentity

open ArchitectureExecutionAdapter

/-- Current schema version of
`sqrt218-compiler-evidence-manifest.schema.json`. -/
def compilerEvidenceManifestSchemaVersion : Nat := 2

/-- Only this compact identity version is eligible for a physical pure-entry
launch. -/
def physicalLaunchIdentityVersion : Nat := 2

/-- Legacy domain separator retained solely so auditors can identify an
ineligible pre-launcher projection. -/
def legacyMetadataKindV1 : String :=
  "sparkinterval.sqrt218-execution-closure-identity.v1"

/-- Domain separator for the compact Lean-side physical-launch identity.

This is a projection of the larger canonical JSON compiler-evidence manifest,
the launcher/control contract, and reviewed formal-model identities.  It is
not a replacement for those artifacts or their external validators. -/
def metadataKind : String :=
  "sparkinterval.sqrt218-execution-closure-identity.v2"

def targetName : ExecutionTarget → String
  | .dgxSparkSM121 => "dgx_spark_sm121"
  | .nvidiaH100SM90 => "nvidia_h100_sm90"
  | .azureSEVSNPCPU => "azure_sevsnp_cpu"

/-- UTF-8-byte-length framing makes concatenation of arbitrary exact strings
unambiguous without relying on newline or delimiter exclusion. -/
def frame (value : String) : String :=
  Nat.repr value.toUTF8.size ++ ":" ++ value

def field (name value : String) : String :=
  frame name ++ frame value

/-- Small canonical V2 projection of every identity needed at the Sqrt218
physical pure-entry boundary. Digest fields carry their lowercase-hex syntax
proofs through `CanonicalSHA256`. -/
structure Metadata where
  executionClosureIdentityVersion : Nat
  compilerEvidenceManifestVersion : Nat
  compilerEvidenceManifestSHA256 : CanonicalSHA256
  compilerSourceSHA256 : CanonicalSHA256
  compilerId : String
  compilerVersion : String
  compilerBinarySHA256 : CanonicalSHA256
  compilerConfigurationSHA256 : CanonicalSHA256
  formalArchitectureModelSHA256 : CanonicalSHA256
  formalELFDecoderModelSHA256 : CanonicalSHA256
  formalPureEntryABIModelSHA256 : CanonicalSHA256
  target : ExecutionTarget
  sysvABIContractSHA256 : CanonicalSHA256
  launcherArtifactSHA256 : CanonicalSHA256
  launcherArtifactByteLength : Nat
  launcherControlContractId : String
  launcherControlContractVersion : Nat
  launcherControlContractSHA256 : CanonicalSHA256
  launcherControlContractByteLength : Nat
  neutralContractId : String
  neutralContractSHA256 : CanonicalSHA256
  pureEntryELFSHA256 : CanonicalSHA256
  pureEntryELFByteLength : Nat
  pureEntryELFEntryPoint : String

namespace Metadata

/-- Exact canonical text whose UTF-8 bytes are committed by the signed
execution-closure digest. -/
def canonicalText (metadata : Metadata) : String :=
  metadataKind ++
  field "execution_closure_identity_version"
    (Nat.repr metadata.executionClosureIdentityVersion) ++
  field "compiler_evidence_manifest_version"
    (Nat.repr metadata.compilerEvidenceManifestVersion) ++
  field "compiler_evidence_manifest_sha256"
    metadata.compilerEvidenceManifestSHA256.value ++
  field "compiler_source_sha256" metadata.compilerSourceSHA256.value ++
  field "compiler_id" metadata.compilerId ++
  field "compiler_version" metadata.compilerVersion ++
  field "compiler_binary_sha256"
    metadata.compilerBinarySHA256.value ++
  field "compiler_configuration_sha256"
    metadata.compilerConfigurationSHA256.value ++
  field "formal_architecture_model_sha256"
    metadata.formalArchitectureModelSHA256.value ++
  field "formal_elf_decoder_model_sha256"
    metadata.formalELFDecoderModelSHA256.value ++
  field "formal_pure_entry_abi_model_sha256"
    metadata.formalPureEntryABIModelSHA256.value ++
  field "target" (targetName metadata.target) ++
  field "sysv_abi_contract_sha256"
    metadata.sysvABIContractSHA256.value ++
  field "launcher_artifact_sha256"
    metadata.launcherArtifactSHA256.value ++
  field "launcher_artifact_byte_length"
    (Nat.repr metadata.launcherArtifactByteLength) ++
  field "launcher_control_contract_id"
    metadata.launcherControlContractId ++
  field "launcher_control_contract_version"
    (Nat.repr metadata.launcherControlContractVersion) ++
  field "launcher_control_contract_sha256"
    metadata.launcherControlContractSHA256.value ++
  field "launcher_control_contract_byte_length"
    (Nat.repr metadata.launcherControlContractByteLength) ++
  field "neutral_contract_id" metadata.neutralContractId ++
  field "neutral_contract_sha256"
    metadata.neutralContractSHA256.value ++
  field "pure_entry_elf_sha256" metadata.pureEntryELFSHA256.value ++
  field "pure_entry_elf_byte_length"
    (Nat.repr metadata.pureEntryELFByteLength) ++
  field "pure_entry_elf_entry_point" metadata.pureEntryELFEntryPoint

def canonicalBytes (metadata : Metadata) : ByteArray :=
  metadata.canonicalText.toUTF8

/-- Version-tagged input to a future receipt importer.  The legacy branch
retains its exact bytes for audit, but there is deliberately no conversion
from that branch to `Metadata`. -/
inductive VersionedMetadataEnvelope where
  | legacyV1 (metadataBytes : ByteArray)
  | physicalLaunchV2 (metadata : Metadata)

namespace VersionedMetadataEnvelope

/-- Select metadata eligible for the physical pure-entry boundary. -/
def physicalLaunchMetadata? : VersionedMetadataEnvelope → Option Metadata
  | .legacyV1 _ => none
  | .physicalLaunchV2 metadata => some metadata

/-- Legacy V1 metadata can never be selected as physical-launch metadata,
regardless of its bytes or digest. -/
theorem legacyV1_ineligible (metadataBytes : ByteArray) :
    physicalLaunchMetadata? (.legacyV1 metadataBytes) = none :=
  rfl

/-- V2 selection retains the complete typed metadata object. -/
theorem physicalLaunchV2_selected (metadata : Metadata) :
    physicalLaunchMetadata? (.physicalLaunchV2 metadata) = some metadata :=
  rfl

end VersionedMetadataEnvelope

/-- Field-for-field agreement with the application identity selected by the
architecture and checker refinements. -/
structure MatchesIdentity
    (metadata : Metadata)
    (identity : NativeImplementationIdentity) : Prop where
  supportedIdentityVersion :
    metadata.executionClosureIdentityVersion =
      physicalLaunchIdentityVersion
  identityVersion :
    metadata.executionClosureIdentityVersion =
      identity.executionClosureIdentityVersion
  supportedManifestVersion :
    metadata.compilerEvidenceManifestVersion =
      compilerEvidenceManifestSchemaVersion
  manifestVersion :
    metadata.compilerEvidenceManifestVersion =
      identity.compilerEvidenceManifestVersion
  compilerEvidenceManifest :
    metadata.compilerEvidenceManifestSHA256.value =
      identity.compilerEvidenceManifestSHA256.value
  compilerSource :
    metadata.compilerSourceSHA256.value =
      identity.compilerSourceSHA256.value
  compilerId :
    metadata.compilerId = identity.compilerId
  compilerVersion :
    metadata.compilerVersion = identity.compilerVersion
  compilerBinary :
    metadata.compilerBinarySHA256.value =
      identity.compilerBinarySHA256.value
  compilerConfiguration :
    metadata.compilerConfigurationSHA256.value =
      identity.compilerConfigurationSHA256.value
  formalArchitectureModel :
    metadata.formalArchitectureModelSHA256.value =
      identity.formalArchitectureSemanticsSHA256.value
  formalELFDecoderModel :
    metadata.formalELFDecoderModelSHA256.value =
      identity.formalELFDecoderModelSHA256.value
  formalPureEntryABIModel :
    metadata.formalPureEntryABIModelSHA256.value =
      identity.formalPureEntryABIModelSHA256.value
  target :
    metadata.target = identity.target
  sysvABIContract :
    metadata.sysvABIContractSHA256.value =
      identity.sysvABIContractSHA256.value
  launcherArtifact :
    metadata.launcherArtifactSHA256.value =
      identity.launcherArtifactSHA256.value
  launcherArtifactByteLength :
    metadata.launcherArtifactByteLength =
      identity.launcherArtifactByteLength
  launcherControlContractId :
    metadata.launcherControlContractId =
      identity.launcherControlContractId
  launcherControlContractVersion :
    metadata.launcherControlContractVersion =
      identity.launcherControlContractVersion
  launcherControlContract :
    metadata.launcherControlContractSHA256.value =
      identity.launcherControlContractSHA256.value
  launcherControlContractByteLength :
    metadata.launcherControlContractByteLength =
      identity.launcherControlContractByteLength
  neutralContractId :
    metadata.neutralContractId = identity.neutralContractId
  neutralContract :
    metadata.neutralContractSHA256.value =
      identity.neutralContractSHA256.value
  pureEntryELF :
    metadata.pureEntryELFSHA256.value = identity.executableSHA256.value
  pureEntryELFByteLength :
    metadata.pureEntryELFByteLength = identity.executableByteLength
  pureEntryELFEntryPoint :
    metadata.pureEntryELFEntryPoint = identity.entryPoint

end Metadata

/-- Exact retained metadata object and exact retained canonical bytes.

`digest` is an equality computed by pure Lean SHA-256.  The structure does not
assert hash injectivity and does not claim that the larger external manifest
proves compiler correctness. -/
structure ExactMetadataBinding
    (identity : NativeImplementationIdentity) where
  metadata : Metadata
  metadataBytes : ByteArray
  canonicalBytes :
    metadataBytes = metadata.canonicalBytes
  identityMatch : metadata.MatchesIdentity identity
  digest :
    SparkInterval.Certificate.SHA256.digestByteArray metadataBytes =
      identity.executionClosureSHA256.value

namespace ExactMetadataBinding

/-- A V2 metadata binding forces the implementation identity itself to select
the supported physical-launch version. -/
theorem implementationVersion
    {identity : NativeImplementationIdentity}
    (binding : ExactMetadataBinding identity) :
    identity.executionClosureIdentityVersion =
      physicalLaunchIdentityVersion :=
  binding.identityMatch.identityVersion.symm.trans
    binding.identityMatch.supportedIdentityVersion

/-- The canonical V2 encoding, not merely an arbitrary retained byte array,
has the implementation's execution-closure SHA-256. -/
theorem canonicalDigest
    {identity : NativeImplementationIdentity}
    (binding : ExactMetadataBinding identity) :
    SparkInterval.Certificate.SHA256.digestByteArray
        binding.metadata.canonicalBytes =
      identity.executionClosureSHA256.value := by
  rw [← binding.canonicalBytes]
  exact binding.digest

end ExactMetadataBinding

/-- Complete local byte witnesses for the two physical-launch artifacts named
by V2 metadata.

This structure performs only pure SHA-256 and length binding.  It does not
execute the launcher, parse its control contract, or claim that attestation
measured either byte string. -/
structure ExactPhysicalLaunchArtifacts
    (identity : NativeImplementationIdentity) where
  launcherBytes : ByteArray
  launcherByteLength :
    launcherBytes.size = identity.launcherArtifactByteLength
  launcherDigest :
    SparkInterval.Certificate.SHA256.digestByteArray launcherBytes =
      identity.launcherArtifactSHA256.value
  controlContractBytes : ByteArray
  controlContractByteLength :
    controlContractBytes.size =
      identity.launcherControlContractByteLength
  controlContractDigest :
    SparkInterval.Certificate.SHA256.digestByteArray controlContractBytes =
      identity.launcherControlContractSHA256.value

namespace ExactPhysicalLaunchArtifacts

/-- Optional archival byte witnesses agree exactly with the corresponding V2
metadata fields.  Normal theorem composition does not require these full byte
arrays; a receipt/appraiser may bind the same digest/length pins externally.
-/
structure MetadataFacts
    {identity : NativeImplementationIdentity}
    (artifacts : ExactPhysicalLaunchArtifacts identity)
    (metadata : Metadata)
    (identityMatch : metadata.MatchesIdentity identity) : Prop where
  launcherDigest :
    SparkInterval.Certificate.SHA256.digestByteArray artifacts.launcherBytes =
      metadata.launcherArtifactSHA256.value
  launcherByteLength :
    artifacts.launcherBytes.size = metadata.launcherArtifactByteLength
  controlContractDigest :
    SparkInterval.Certificate.SHA256.digestByteArray
        artifacts.controlContractBytes =
      metadata.launcherControlContractSHA256.value
  controlContractByteLength :
    artifacts.controlContractBytes.size =
      metadata.launcherControlContractByteLength

/-- Pure field transitivity and SHA-256 binding for optional archival bytes.
-/
theorem metadataFacts
    {identity : NativeImplementationIdentity}
    (artifacts : ExactPhysicalLaunchArtifacts identity)
    (metadata : Metadata)
    (identityMatch : metadata.MatchesIdentity identity) :
    MetadataFacts artifacts metadata identityMatch := by
  exact {
    launcherDigest :=
      artifacts.launcherDigest.trans identityMatch.launcherArtifact.symm
    launcherByteLength :=
      artifacts.launcherByteLength.trans
        identityMatch.launcherArtifactByteLength.symm
    controlContractDigest :=
      artifacts.controlContractDigest.trans
        identityMatch.launcherControlContract.symm
    controlContractByteLength :=
      artifacts.controlContractByteLength.trans
        identityMatch.launcherControlContractByteLength.symm
  }

end ExactPhysicalLaunchArtifacts

/-- Complete signed-statement and measured-run identity package.

`architectureBinding` is the separately supplied exact formal-machine
selection, while `receiptBinding` fixes the raw 120-byte output used by that
measured run. The legacy returned token is intentionally absent so the direct
architecture path does not inherit a historical trust dependency. -/
structure Binding
    (implementation : NativeImplementation)
    (statement : RunStatement)
    (inputBytes : ByteArray)
    (resultEnvelope : String)
    (result : ArithmeticResult) where
  closure : ExactMetadataBinding implementation.identity
  statementBinding :
    ClosedStatementBinding implementation statement
      inputBytes resultEnvelope
  receiptBinding :
    ExactReceiptBinding inputBytes resultEnvelope result
  architectureBinding :
    ArchitectureExecutionAdapter.ExactArchitectureBinding implementation

namespace Binding

/-- Exact byte-level architecture run selected by the binding. -/
def measuredRun
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    MeasuredRun :=
  ArchitectureExecutionAdapter.measuredRun
    binding.architectureBinding.machine
    binding.architectureBinding.executableBytes
    implementation.identity.entryPoint
    inputBytes binding.receiptBinding.rawResultBytes

/-- Every identity equality exposed for human audit.

The compiler, measured launcher, control-contract, and formal-model fields
live in the exact canonical object whose digest equals the signed closure
field.  The run statement's host executable is the launcher, while the
architecture `MeasuredRun` executable is the distinct pure-entry ELF.  The
ELF digest, byte length, model, target, and entry point are tied to the latter.
-/
structure IdentityFacts
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    Prop where
  metadataBytes :
    binding.closure.metadataBytes =
      binding.closure.metadata.canonicalBytes
  closureDigestSigned :
    SparkInterval.Certificate.SHA256.digestByteArray
        binding.closure.metadataBytes =
      statement.artifacts.kernelManifestHash
  identityVersion :
    binding.closure.metadata.executionClosureIdentityVersion =
      physicalLaunchIdentityVersion
  identityVersionImplementation :
    binding.closure.metadata.executionClosureIdentityVersion =
      implementation.identity.executionClosureIdentityVersion
  manifestVersion :
    binding.closure.metadata.compilerEvidenceManifestVersion =
      compilerEvidenceManifestSchemaVersion
  manifestVersionIdentity :
    binding.closure.metadata.compilerEvidenceManifestVersion =
      implementation.identity.compilerEvidenceManifestVersion
  compilerEvidenceManifest :
    binding.closure.metadata.compilerEvidenceManifestSHA256.value =
      implementation.identity.compilerEvidenceManifestSHA256.value
  compilerSource :
    binding.closure.metadata.compilerSourceSHA256.value =
      implementation.identity.compilerSourceSHA256.value
  compilerId :
    binding.closure.metadata.compilerId =
      implementation.identity.compilerId
  compilerVersion :
    binding.closure.metadata.compilerVersion =
      implementation.identity.compilerVersion
  compilerBinary :
    binding.closure.metadata.compilerBinarySHA256.value =
      implementation.identity.compilerBinarySHA256.value
  compilerConfiguration :
    binding.closure.metadata.compilerConfigurationSHA256.value =
      implementation.identity.compilerConfigurationSHA256.value
  formalArchitectureModel :
    binding.closure.metadata.formalArchitectureModelSHA256.value =
      implementation.identity.formalArchitectureSemanticsSHA256.value
  formalELFDecoderModel :
    binding.closure.metadata.formalELFDecoderModelSHA256.value =
      implementation.identity.formalELFDecoderModelSHA256.value
  formalPureEntryABIModel :
    binding.closure.metadata.formalPureEntryABIModelSHA256.value =
      implementation.identity.formalPureEntryABIModelSHA256.value
  targetSigned :
    binding.closure.metadata.target = statement.target
  targetMeasured :
    binding.closure.metadata.target = binding.measuredRun.target
  sysvABIContract :
    binding.closure.metadata.sysvABIContractSHA256.value =
      implementation.identity.sysvABIContractSHA256.value
  launcherArtifactIdentity :
    binding.closure.metadata.launcherArtifactSHA256.value =
      implementation.identity.launcherArtifactSHA256.value
  launcherArtifactSigned :
    binding.closure.metadata.launcherArtifactSHA256.value =
      statement.artifacts.hostExecutableHash
  launcherArtifactByteLength :
    binding.closure.metadata.launcherArtifactByteLength =
      implementation.identity.launcherArtifactByteLength
  launcherControlContractId :
    binding.closure.metadata.launcherControlContractId =
      implementation.identity.launcherControlContractId
  launcherControlContractVersion :
    binding.closure.metadata.launcherControlContractVersion =
      implementation.identity.launcherControlContractVersion
  launcherControlContract :
    binding.closure.metadata.launcherControlContractSHA256.value =
      implementation.identity.launcherControlContractSHA256.value
  launcherControlContractByteLength :
    binding.closure.metadata.launcherControlContractByteLength =
      implementation.identity.launcherControlContractByteLength
  neutralContractId :
    binding.closure.metadata.neutralContractId =
      implementation.identity.neutralContractId
  neutralContract :
    binding.closure.metadata.neutralContractSHA256.value =
      implementation.identity.neutralContractSHA256.value
  pureEntryELFIdentity :
    binding.closure.metadata.pureEntryELFSHA256.value =
      implementation.identity.executableSHA256.value
  pureEntryELFMeasured :
    binding.closure.metadata.pureEntryELFSHA256.value =
      binding.measuredRun.executable.digest
  pureEntryELFByteLengthIdentity :
    binding.closure.metadata.pureEntryELFByteLength =
      implementation.identity.executableByteLength
  pureEntryELFByteLengthMeasured :
    binding.closure.metadata.pureEntryELFByteLength =
      binding.measuredRun.executable.byteLength
  modelMeasured :
    binding.closure.metadata.formalArchitectureModelSHA256.value =
      binding.measuredRun.semanticsId
  entryPointMeasured :
    binding.closure.metadata.pureEntryELFEntryPoint =
      binding.measuredRun.entryPoint
  exactMeasurements :
    binding.measuredRun.ExactMeasurements
      ArchitectureExecutionAdapter.sha256MeasurementScheme

/-- Construct the complete field audit by transitivity through the
application identity.  No byte parser, production input, arithmetic evaluator,
launcher execution, or machine-trace replay occurs in this proof. -/
theorem identityFacts
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    binding.IdentityFacts := by
  have identityMatch := binding.closure.identityMatch
  refine {
    metadataBytes := binding.closure.canonicalBytes
    closureDigestSigned := ?_
    identityVersion := identityMatch.supportedIdentityVersion
    identityVersionImplementation := identityMatch.identityVersion
    manifestVersion := identityMatch.supportedManifestVersion
    manifestVersionIdentity := identityMatch.manifestVersion
    compilerEvidenceManifest := identityMatch.compilerEvidenceManifest
    compilerSource := identityMatch.compilerSource
    compilerId := identityMatch.compilerId
    compilerVersion := identityMatch.compilerVersion
    compilerBinary := identityMatch.compilerBinary
    compilerConfiguration := identityMatch.compilerConfiguration
    formalArchitectureModel := identityMatch.formalArchitectureModel
    formalELFDecoderModel := identityMatch.formalELFDecoderModel
    formalPureEntryABIModel := identityMatch.formalPureEntryABIModel
    targetSigned := ?_
    targetMeasured := ?_
    sysvABIContract := identityMatch.sysvABIContract
    launcherArtifactIdentity := identityMatch.launcherArtifact
    launcherArtifactSigned := ?_
    launcherArtifactByteLength :=
      identityMatch.launcherArtifactByteLength
    launcherControlContractId := identityMatch.launcherControlContractId
    launcherControlContractVersion :=
      identityMatch.launcherControlContractVersion
    launcherControlContract := identityMatch.launcherControlContract
    launcherControlContractByteLength :=
      identityMatch.launcherControlContractByteLength
    neutralContractId := identityMatch.neutralContractId
    neutralContract := identityMatch.neutralContract
    pureEntryELFIdentity := identityMatch.pureEntryELF
    pureEntryELFMeasured := ?_
    pureEntryELFByteLengthIdentity :=
      identityMatch.pureEntryELFByteLength
    pureEntryELFByteLengthMeasured := ?_
    modelMeasured := ?_
    entryPointMeasured := ?_
    exactMeasurements := ?_
  }
  · exact binding.closure.digest.trans
      binding.statementBinding.executionClosure.symm
  · exact identityMatch.target.trans
      binding.statementBinding.target.symm
  · change
      binding.closure.metadata.target =
        binding.architectureBinding.machine.target
    exact identityMatch.target.trans
      binding.architectureBinding.targetIdentity.symm
  · exact identityMatch.launcherArtifact.trans
      binding.statementBinding.launcherExecutable.symm
  · change
      binding.closure.metadata.pureEntryELFSHA256.value =
        SparkInterval.Certificate.SHA256.digestByteArray
          binding.architectureBinding.executableBytes
    exact identityMatch.pureEntryELF.trans
      binding.architectureBinding.executableIdentity.symm
  · change
      binding.closure.metadata.pureEntryELFByteLength =
        binding.architectureBinding.executableBytes.size
    exact identityMatch.pureEntryELFByteLength.trans
      binding.architectureBinding.executableLength.symm
  · change
      binding.closure.metadata.formalArchitectureModelSHA256.value =
        binding.architectureBinding.machine.semanticsId
    exact identityMatch.formalArchitectureModel.trans
      binding.architectureBinding.semanticsIdentity.symm
  · change
      binding.closure.metadata.pureEntryELFEntryPoint =
        implementation.identity.entryPoint
    exact identityMatch.pureEntryELFEntryPoint
  · exact ArchitectureExecutionAdapter.measuredRun_exactMeasurements
      binding.architectureBinding.machine
      binding.architectureBinding.executableBytes
      implementation.identity.entryPoint inputBytes
      binding.receiptBinding.rawResultBytes

/-- Direct architecture fact for the exact measured run, assuming the
implementation-level architecture execution already supplied by the physical
boundary. -/
theorem architectureExecution_of_implementation
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result)
    (executed :
      implementation.architectureExecution
        inputBytes binding.receiptBinding.rawResultBytes) :
    ArchitectureExecution
      ArchitectureExecutionAdapter.sha256MeasurementScheme
      binding.architectureBinding.machine binding.measuredRun :=
  (binding.architectureBinding.architectureExecution
    inputBytes binding.receiptBinding.rawResultBytes).mp executed

/-- Transitional composition from the current historical signed token to the
exact formal measured run.

`HistoricalReturnedBridgesArchitecture` is deliberately an explicit
assumption.  The metadata hash does not create an architecture execution
trace, and this theorem does not claim otherwise. -/
theorem architectureExecution_of_historicalReturned
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result)
    (returned : AlgorithmReturned statement resultEnvelope)
    (historicalBridge :
      HistoricalReturnedBridgesArchitecture implementation) :
    ArchitectureExecution
      ArchitectureExecutionAdapter.sha256MeasurementScheme
      binding.architectureBinding.machine binding.measuredRun :=
  binding.architectureExecution_of_implementation
    (AttestedAcceptance.architectureExecution_of_algorithmReturned
      binding.statementBinding binding.receiptBinding
      returned historicalBridge)

end Binding

end ExecutionClosureIdentity

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
