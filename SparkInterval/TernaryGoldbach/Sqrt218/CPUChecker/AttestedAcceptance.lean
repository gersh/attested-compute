/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.CanonicalHex
import SparkInterval.Certificate.SHA256
import SparkInterval.Execution.Statement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.IR
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultSemantics

/-!
# Low-level attested-execution contract for fixed-width Sqrt218

This small module states the inexpensive part of the fixed-width Sqrt218
handoff.  It deliberately does not import the closed registered-algorithm
catalog or the complete V2 checker.

Three facts are kept distinct:

1. `AlgorithmReturned statement resultEnvelope` is only the historical
   physical token exposed by the current execution axiom.  It contains no
   machine trace or execution semantics.
2. `implementation.architectureExecution inputBytes rawResultBytes` is the
   explicit low-level architecture-execution fact that a future trusted
   execution boundary should expose directly.
3. `implementation.run inputBytes = .accepted result` is a mathematical
   statement about the native checker's abstract model.

`HistoricalReturnedBridgesArchitecture` is a separately named transitional
trust obligation from (1) to (2).  It must not be described as a compiler or
ISA proof.  `ArchitectureExecutionRefinesNative` is the actual
compiler/linker/ELF/ISA refinement obligation from (2) to (3).

`ClosedStatementBinding` gives a complete component-wise binding for the
algorithm, exact input and result, parameters, domain, target, trust profile,
and every generic artifact field.  A separate heavyweight adapter connects
the existing closed production `statementCheck` to this record.

`ExactReceiptBinding` retains the complete input bytes, exact result-envelope
string, all 120 native result bytes, and the complete decoded result state.
It contains neither a complete V2 check nor a source claim.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.Execution
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

/-- A SHA-256 identity together with its kernel-checked canonical lowercase
hexadecimal syntax. -/
abbrev CanonicalSHA256 := SparkInterval.Certificate.CanonicalLowerHex 64

/-- Exact identities of the native implementation, its registered metadata,
measured artifacts, and its refinement evidence.

All digest fields carry canonical-syntax proofs.  The compiler-evidence,
formal-architecture-semantics, entry-point, and neutral-contract identities
index `ArchitectureExecutionRefinesNative`.  The current generic
`RunStatement` has no separate field for those refinement pins;
`ExecutionClosureIdentity` connects their exact canonical V2 metadata bytes
to the signed execution-closure digest.  V2 keeps the pure-entry ELF separate
from the measured launcher: the former is the code interpreted by the
architecture model, while the latter maps it, constructs the formal ABI
initial state, and observes the return. -/
structure NativeImplementationIdentity where
  algorithmId : String
  algorithmIdPresent : algorithmId ≠ ""
  algorithmSHA256 : CanonicalSHA256
  parametersSHA256 : CanonicalSHA256
  domainSHA256 : CanonicalSHA256
  target : ExecutionTarget
  targetProfileSHA256 : CanonicalSHA256
  trust : TrustProfile
  trustProfileSHA256 : CanonicalSHA256
  sourceTreeSHA256 : CanonicalSHA256
  executableSHA256 : CanonicalSHA256
  cpuDeviceMarkerSHA256 : CanonicalSHA256
  executionClosureSHA256 : CanonicalSHA256
  /-- Version of the compact execution-closure identity itself.  Physical
  pure-entry launch admission supports V2 only; the legacy V1 projection did
  not identify a launcher. -/
  executionClosureIdentityVersion : Nat
  /-- Schema version of the canonical compiler-evidence manifest retained by
  the execution closure. -/
  compilerEvidenceManifestVersion : Nat
  compilerEvidenceManifestSHA256 : CanonicalSHA256
  /-- Exact canonical compiler identifier and version spellings from the
  reviewed compiler-evidence manifest. -/
  compilerId : String
  compilerIdPresent : compilerId ≠ ""
  compilerVersion : String
  compilerVersionPresent : compilerVersion ≠ ""
  compilerSourceSHA256 : CanonicalSHA256
  compilerBinarySHA256 : CanonicalSHA256
  compilerConfigurationSHA256 : CanonicalSHA256
  formalArchitectureSemanticsSHA256 : CanonicalSHA256
  /-- Exact formal ELF decoder/loader model used to turn the retained
  pure-entry ELF bytes into loadable segments and a selected entry. -/
  formalELFDecoderModelSHA256 : CanonicalSHA256
  /-- Exact formal initializer/observer model for the guarded SysV pure-entry
  call.  This is distinct from the prose-level SysV contract. -/
  formalPureEntryABIModelSHA256 : CanonicalSHA256
  sysvABIContractSHA256 : CanonicalSHA256
  /-- Concrete measured launcher artifact.  Its digest is not interchangeable
  with either the pure-entry ELF digest or the ABI-model digest. -/
  launcherArtifactSHA256 : CanonicalSHA256
  launcherArtifactByteLength : Nat
  launcherArtifactNonempty : 0 < launcherArtifactByteLength
  /-- Versioned bytes defining the launcher's accepted control file,
  mapping/guard rules, entry protocol, and retained observation. -/
  launcherControlContractId : String
  launcherControlContractIdPresent : launcherControlContractId ≠ ""
  launcherControlContractVersion : Nat
  launcherControlContractVersionPositive : 0 < launcherControlContractVersion
  launcherControlContractSHA256 : CanonicalSHA256
  launcherControlContractByteLength : Nat
  launcherControlContractNonempty : 0 < launcherControlContractByteLength
  /-- Digest and exact byte length of the architecture-modeled pure-entry ELF
  selected by `entryPoint`.  This is deliberately distinct from the signed
  run statement's host executable, which is the measured launcher. -/
  executableByteLength : Nat
  executableNonempty : 0 < executableByteLength
  entryPoint : String
  entryPointPresent : entryPoint ≠ ""
  neutralContractId : String
  neutralContractIdPresent : neutralContractId ≠ ""
  neutralContractSHA256 : CanonicalSHA256

/-- A low-level architecture relation and abstract native checker model,
paired with the exact identities for which their refinement is claimed.

`architectureExecution input output` is intentionally not defined in terms
of `run`.  It is the future trace/ISA-level execution proposition for the
exact input and raw output bytes. -/
structure NativeImplementation where
  identity : NativeImplementationIdentity
  architectureExecution : ByteArray → ByteArray → Prop
  run : ByteArray → NativeOutcome

/-- Complete component-wise binding between an exact signed statement and
one exact implementation/input/result tuple.

The challenge nonce remains part of the exact `RunStatement` indexed by the
physical token.  It has no mathematical role in the checker refinement; its
freshness and receipt binding remain responsibilities of trusted-compute
admission. -/
structure ClosedStatementBinding
    (implementation : NativeImplementation)
    (statement : RunStatement)
    (inputBytes : ByteArray)
    (resultEnvelope : String) : Prop where
  algorithmId :
    statement.algorithmId = implementation.identity.algorithmId
  algorithmHash :
    statement.algorithmHash = implementation.identity.algorithmSHA256.value
  inputHash :
    statement.inputHash =
      SparkInterval.Certificate.SHA256.digestByteArray inputBytes
  parametersHash :
    statement.parametersHash =
      implementation.identity.parametersSHA256.value
  domainHash :
    statement.domainHash = implementation.identity.domainSHA256.value
  result :
    statement.result = resultEnvelope
  outputHash :
    statement.outputHash =
      SparkInterval.Certificate.SHA256.digestString resultEnvelope
  target :
    statement.target = implementation.identity.target
  targetProfileHash :
    statement.targetProfileHash =
      implementation.identity.targetProfileSHA256.value
  trust :
    statement.trust = implementation.identity.trust
  trustProfileHash :
    statement.trustProfileHash =
      implementation.identity.trustProfileSHA256.value
  sourceTree :
    statement.artifacts.sourceTreeHash =
      implementation.identity.sourceTreeSHA256.value
  launcherExecutable :
    statement.artifacts.hostExecutableHash =
      implementation.identity.launcherArtifactSHA256.value
  cpuDeviceMarker :
    statement.artifacts.deviceCubinHash =
      implementation.identity.cpuDeviceMarkerSHA256.value
  executionClosure :
    statement.artifacts.kernelManifestHash =
      implementation.identity.executionClosureSHA256.value

/-- Pure, exact binding between complete checker input and the complete
fixed-width result.

The result envelope is decoded by the strict `ResultWire` parser.  Its typed
record is interpreted by `ResultSemantics.arithmeticResult`, so `result`
includes every `ScanState` limb and the anchor slack.  Strict decoding fixes
the result byte width and canonical envelope spelling. -/
structure ExactReceiptBinding
    (inputBytes : ByteArray)
    (resultEnvelope : String)
    (result : ArithmeticResult) where
  rawResultBytes : ByteArray
  nativeResult : NativeResultRecord
  decodedResult :
    decodeResultEnvelope resultEnvelope =
      .ok (rawResultBytes, nativeResult)
  acceptedStatus :
    acceptedResultCheck nativeResult = true
  wrapperInputLength :
    nativeResult.inputByteLength = inputBytes.size
  wrapperInputDigest :
    nativeResult.inputSHA256 =
      SparkInterval.Certificate.SHA256.digestByteArray inputBytes
  resultSemantics :
    nativeResult.arithmeticResult = result

/-- Transitional trust obligation for the current historical execution token.

`AlgorithmReturned` has no trace semantics, so this implication is not a
compiler, ELF, or ISA correctness theorem.  It is isolated under a name that
makes the extra trust explicit.  A future execution axiom should return
`architectureExecution` directly, making this bridge unnecessary. -/
def HistoricalReturnedBridgesArchitecture
    (implementation : NativeImplementation) : Prop :=
  ∀ {statement : RunStatement}
      {inputBytes : ByteArray}
      {resultEnvelope : String}
      {result : ArithmeticResult}
      (_statementBound :
        ClosedStatementBinding implementation statement
          inputBytes resultEnvelope)
      (receiptBound :
        ExactReceiptBinding inputBytes resultEnvelope result),
    AlgorithmReturned statement resultEnvelope →
      implementation.architectureExecution
        inputBytes receiptBound.rawResultBytes

/-- Actual low-level implementation-refinement obligation.

For the exact executable, compiler-evidence manifest, formal architecture
semantics, entry point, neutral contract, statement, input, and raw output
named by the indices, an architecture-level execution must imply acceptance
by the abstract native model with the exact decoded arithmetic result.  No
theorem in this module manufactures this premise. -/
def ArchitectureExecutionRefinesNative
    (implementation : NativeImplementation) : Prop :=
  ∀ {statement : RunStatement}
      {inputBytes : ByteArray}
      {resultEnvelope : String}
      {result : ArithmeticResult}
      (_statementBound :
        ClosedStatementBinding implementation statement
          inputBytes resultEnvelope)
      (receiptBound :
        ExactReceiptBinding inputBytes resultEnvelope result),
    implementation.architectureExecution
        inputBytes receiptBound.rawResultBytes →
      implementation.run inputBytes = .accepted result

/-- Transitional step from the current historical physical token to the
explicit low-level architecture-execution fact. -/
theorem architectureExecution_of_algorithmReturned
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (statementBound :
      ClosedStatementBinding implementation statement
        inputBytes resultEnvelope)
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope result)
    (returned :
      AlgorithmReturned statement resultEnvelope)
    (historicalBridge :
      HistoricalReturnedBridgesArchitecture implementation) :
    implementation.architectureExecution
      inputBytes receiptBound.rawResultBytes :=
  historicalBridge statementBound receiptBound returned

/-- Compiler/ELF/ISA refinement step from an exact architecture execution to
native-model acceptance. -/
theorem nativeAcceptance_of_architectureExecution
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (statementBound :
      ClosedStatementBinding implementation statement
        inputBytes resultEnvelope)
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope result)
    (architectureExecuted :
      implementation.architectureExecution
        inputBytes receiptBound.rawResultBytes)
    (architectureRefinement :
      ArchitectureExecutionRefinesNative implementation) :
    implementation.run inputBytes = .accepted result :=
  architectureRefinement statementBound receiptBound architectureExecuted

/-- Explicit composition for the current historical token.

The two premises remain visible: `historicalBridge` is transitional physical
trust, while `architectureRefinement` is the implementation-correctness
theorem. -/
theorem nativeAcceptance_of_algorithmReturned
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (statementBound :
      ClosedStatementBinding implementation statement
        inputBytes resultEnvelope)
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope result)
    (returned :
      AlgorithmReturned statement resultEnvelope)
    (historicalBridge :
      HistoricalReturnedBridgesArchitecture implementation)
    (architectureRefinement :
      ArchitectureExecutionRefinesNative implementation) :
    implementation.run inputBytes = .accepted result :=
  nativeAcceptance_of_architectureExecution
    statementBound receiptBound
    (architectureExecution_of_algorithmReturned
      statementBound receiptBound returned historicalBridge)
    architectureRefinement

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
