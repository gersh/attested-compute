/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredAlgorithm
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.AttestedAcceptance

/-!
# Closed-registry adapter for fixed-width Sqrt218 attested acceptance

This is the deliberately heavyweight adapter from the existing closed
registered invocation to the small component-wise contract in
`AttestedAcceptance`.

The adapter uses
`helfgottSqrt218FixedProductionV2.statementCheck = true`; it never uses the
registered invocation's formal execution relation.  The check establishes
the fixed algorithm/input/parameter/domain/result-language, Azure deployment,
reviewed profiles, and reviewed artifact tuple.  The additional identity
record below connects those reviewed statement fields to the exact native
implementation whose architecture-refinement proof will be supplied.

This module does not change the execution axiom or any existing registered
theorem.  It may require the large generated registry import closure to be
available as `.olean`; no production replay belongs in this module.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance

open SparkInterval.Execution

/-- The one closed invocation selected by this adapter. -/
def fixedProductionInvocation : RegisteredInvocation :=
  .helfgottSqrt218FixedProductionV2

/-- Exact match between a native implementation identity and all registered
metadata/artifact fields that are independent of the per-run input and result
bytes.

Profile and artifact equalities are stated against `statement`; the
`statementCheck` premise in the bridge theorem independently proves that the
same fields equal the reviewed production pins. -/
structure FixedV2RegisteredIdentityBinding
    (implementation : NativeImplementation)
    (statement : RunStatement) : Prop where
  algorithmId :
    implementation.identity.algorithmId =
      fixedProductionInvocation.algorithm.algorithmId
  algorithmHash :
    implementation.identity.algorithmSHA256.value =
      fixedProductionInvocation.algorithm.algorithmHash
  parametersHash :
    implementation.identity.parametersSHA256.value =
      fixedProductionInvocation.algorithm.canonicalParametersHash
  domainHash :
    implementation.identity.domainSHA256.value =
      fixedProductionInvocation.algorithm.canonicalDomainHash
  target :
    implementation.identity.target = .azureSEVSNPCPU
  trust :
    implementation.identity.trust =
      .azureSEVSNPConfidentialCompute
  targetProfileHash :
    statement.targetProfileHash =
      implementation.identity.targetProfileSHA256.value
  trustProfileHash :
    statement.trustProfileHash =
      implementation.identity.trustProfileSHA256.value
  sourceTree :
    statement.artifacts.sourceTreeHash =
      implementation.identity.sourceTreeSHA256.value
  executable :
    statement.artifacts.hostExecutableHash =
      implementation.identity.executableSHA256.value
  cpuDeviceMarker :
    statement.artifacts.deviceCubinHash =
      implementation.identity.cpuDeviceMarkerSHA256.value
  executionClosure :
    statement.artifacts.kernelManifestHash =
      implementation.identity.executionClosureSHA256.value

/-- The existing closed `statementCheck`, exact retained input/result bytes,
and exact implementation pins imply the small component-wise binding.

The compiler-evidence manifest, formal architecture semantics, native entry
point, and neutral contract do not occur as separate generic `RunStatement`
fields.  They remain explicit indices of
`ArchitectureExecutionRefinesNative` and require a future verified
execution-closure membership bridge. -/
theorem closedStatementBinding_of_statementCheck
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    (checked :
      fixedProductionInvocation.statementCheck statement = true)
    (identityBound :
      FixedV2RegisteredIdentityBinding implementation statement)
    (inputDigest :
      SparkInterval.Certificate.SHA256.digestByteArray inputBytes =
        fixedProductionInvocation.canonicalInputHash)
    (resultBound : statement.result = resultEnvelope)
    (outputDigest :
      SparkInterval.Certificate.SHA256.digestString resultEnvelope =
        statement.outputHash) :
    ClosedStatementBinding implementation statement
      inputBytes resultEnvelope := by
  rcases RegisteredInvocation.statementCheck_sound checked with
    ⟨algorithmId, algorithmHash, inputHash, parametersHash, domainHash,
      _resultAllowed, _sourceBinding, deployment, _artifacts⟩
  have targetAndTrust :
      statement.target = .azureSEVSNPCPU ∧
        statement.trust = .azureSEVSNPConfidentialCompute := by
    simpa [fixedProductionInvocation,
      RegisteredInvocation.deploymentCheck] using deployment
  exact {
    algorithmId := algorithmId.trans identityBound.algorithmId.symm
    algorithmHash := algorithmHash.trans identityBound.algorithmHash.symm
    inputHash := inputHash.trans inputDigest.symm
    parametersHash :=
      parametersHash.trans identityBound.parametersHash.symm
    domainHash := domainHash.trans identityBound.domainHash.symm
    result := resultBound
    outputHash := outputDigest.symm
    target := targetAndTrust.1.trans identityBound.target.symm
    targetProfileHash := identityBound.targetProfileHash
    trust := targetAndTrust.2.trans identityBound.trust.symm
    trustProfileHash := identityBound.trustProfileHash
    sourceTree := identityBound.sourceTree
    executable := identityBound.executable
    cpuDeviceMarker := identityBound.cpuDeviceMarker
    executionClosure := identityBound.executionClosure
  }

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
