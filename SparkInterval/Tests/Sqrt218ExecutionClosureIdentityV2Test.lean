/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.ExecutionClosureIdentity

/-!
# Tiny symbolic checks for the Sqrt218 physical-launch identity

These tests elaborate field projections and equality composition only.  They
do not retain a production artifact, run a launcher, invoke a compiler, or
replay a machine trace.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.Sqrt218ExecutionClosureIdentityV2

open SparkInterval.Execution
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance.ExecutionClosureIdentity

example (legacyBytes : ByteArray) :
    Metadata.VersionedMetadataEnvelope.physicalLaunchMetadata?
        (.legacyV1 legacyBytes) =
      none :=
  Metadata.VersionedMetadataEnvelope.legacyV1_ineligible legacyBytes

example (metadata : Metadata) :
    Metadata.VersionedMetadataEnvelope.physicalLaunchMetadata?
        (.physicalLaunchV2 metadata) =
      some metadata :=
  Metadata.VersionedMetadataEnvelope.physicalLaunchV2_selected metadata

example
    {identity : NativeImplementationIdentity}
    (closure : ExactMetadataBinding identity) :
    SparkInterval.Certificate.SHA256.digestByteArray
        closure.metadata.canonicalBytes =
      identity.executionClosureSHA256.value :=
  closure.canonicalDigest

example
    {identity : NativeImplementationIdentity}
    (closure : ExactMetadataBinding identity) :
    identity.executionClosureIdentityVersion =
      physicalLaunchIdentityVersion :=
  closure.implementationVersion

example
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    binding.IdentityFacts :=
  binding.identityFacts

example
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    SparkInterval.Certificate.SHA256.digestByteArray
        binding.closure.metadataBytes =
      statement.artifacts.kernelManifestHash :=
  (binding.identityFacts).closureDigestSigned

example
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    binding.closure.metadata.launcherArtifactSHA256.value =
      statement.artifacts.hostExecutableHash :=
  (binding.identityFacts).launcherArtifactSigned

example
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    binding.closure.metadata.pureEntryELFSHA256.value =
      binding.measuredRun.executable.digest :=
  (binding.identityFacts).pureEntryELFMeasured

example
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    binding.closure.metadata.pureEntryELFByteLength =
      binding.measuredRun.executable.byteLength :=
  (binding.identityFacts).pureEntryELFByteLengthMeasured

example
    {implementation : NativeImplementation}
    {statement : RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding :
      Binding implementation statement inputBytes resultEnvelope result) :
    implementation.identity.executionClosureIdentityVersion =
      physicalLaunchIdentityVersion :=
  (binding.identityFacts).identityVersionImplementation.symm.trans
    (binding.identityFacts).identityVersion

example
    {identity : NativeImplementationIdentity}
    (artifacts : ExactPhysicalLaunchArtifacts identity)
    (metadata : Metadata)
    (identityMatch : metadata.MatchesIdentity identity) :
    SparkInterval.Certificate.SHA256.digestByteArray
        artifacts.launcherBytes =
      metadata.launcherArtifactSHA256.value :=
  (ExactPhysicalLaunchArtifacts.metadataFacts
    artifacts metadata identityMatch).launcherDigest

example
    {identity : NativeImplementationIdentity}
    (artifacts : ExactPhysicalLaunchArtifacts identity)
    (metadata : Metadata)
    (identityMatch : metadata.MatchesIdentity identity) :
    SparkInterval.Certificate.SHA256.digestByteArray
        artifacts.controlContractBytes =
      metadata.launcherControlContractSHA256.value :=
  (ExactPhysicalLaunchArtifacts.metadataFacts
    artifacts metadata identityMatch).controlContractDigest

end SparkInterval.Tests.Sqrt218ExecutionClosureIdentityV2
