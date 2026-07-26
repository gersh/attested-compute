/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.DeterministicFinalizerIR
import SparkInterval.Execution.StaticCPUExecutableCertificate

/-!
# Static-CPU certificate tied to an exact deterministic source program

`StaticCPUExecutableCertificate.Certificate` deliberately permits an
arbitrary intermediate source behavior.  This module closes that parameter
for production campaign work: the compiler target must refine the
`successBehavior` of one concrete `DeterministicFinalizerIR.Certificate`, and
the latter's proved refinement supplies the final checker relation.

The resulting chain is:

```text
exact ELF / formal CPU trace
  -> linked-image behavior
  -> compiler target behavior
  -> exact deterministic source program
  -> fixed native checker
```

There is no application proposition, run result, receipt, signature, or
trusted theorem field.  In particular, an executable certificate cannot
silently replace the reviewed source program with `checker.accepts` itself.

This is still a certificate *shape*.  An inhabitant must provide exact ELF
validation, instruction/block semantics, assembler/linker validation, and a
compiler theorem for the selected program.  No such production inhabitant is
declared here.
-/

set_option autoImplicit false

namespace
  SparkInterval.Execution.Architecture.DeterministicProgramStaticCPUCertificate

open X86ELF

/-- Complete static-CPU refinement whose source endpoint is one exact
deterministic-program certificate. -/
structure Certificate
    (invocation : RegisteredArchitectureInvocation)
    (reviewed : ReviewedArchitectureRun invocation)
    (checker : NativeCheckerSemantics)
    (sourceProgram :
      DeterministicFinalizerIR.Certificate checker) : Type 1 where
  cpuTarget :
    invocation.terminalTarget = .azureSEVSNPCPU
  model : X86ELF.PureEntryModel
  machineIdentity :
    reviewed.machine = model.toArchitectureSemantics
  decoder : X86StaticBinaryCertificate.InstructionDecoder
  staticBinary : X86StaticBinaryCertificate.Certificate
  linkedImageBehavior : X86ELF.IOBehavior
  compilerTargetBehavior : X86ELF.IOBehavior
  pureEntry :
    StaticCPUExecutableCertificate.StaticPureEntryRefinement
      registeredSHA256MeasurementScheme model
      reviewed.compactPins.entryPoint decoder
      reviewed.executableArtifact staticBinary linkedImageBehavior
  assemblerLinker :
    X86ELF.BehaviorRefines
      linkedImageBehavior compilerTargetBehavior
  compilerToExactProgram :
    X86ELF.BehaviorRefines
      compilerTargetBehavior sourceProgram.program.successBehavior

namespace Certificate

/-- Forget only the explicit source-program parameter, obtaining the generic
static-CPU certificate.  Its source behavior is definitionally the selected
program, and its final theorem is the program certificate's ordinary
checker-refinement proof. -/
def toStaticCPU
    {invocation : RegisteredArchitectureInvocation}
    {reviewed : ReviewedArchitectureRun invocation}
    {checker : NativeCheckerSemantics}
    {sourceProgram :
      DeterministicFinalizerIR.Certificate checker}
    (certificate :
      Certificate invocation reviewed checker sourceProgram) :
    StaticCPUExecutableCertificate.Certificate
      invocation reviewed checker where
  cpuTarget := certificate.cpuTarget
  model := certificate.model
  machineIdentity := certificate.machineIdentity
  decoder := certificate.decoder
  staticBinary := certificate.staticBinary
  linkedImageBehavior := certificate.linkedImageBehavior
  compilerTargetBehavior := certificate.compilerTargetBehavior
  sourceBehavior := sourceProgram.program.successBehavior
  pureEntry := certificate.pureEntry
  assemblerLinker := certificate.assemblerLinker
  compiler := certificate.compilerToExactProgram
  sourceToChecker := sourceProgram.sourceToChecker

/-- Exact deterministic-program static-CPU evidence yields the universal
architecture-to-checker refinement required by a compact receipt. -/
theorem architectureRefinement
    {invocation : RegisteredArchitectureInvocation}
    {reviewed : ReviewedArchitectureRun invocation}
    {checker : NativeCheckerSemantics}
    {sourceProgram :
      DeterministicFinalizerIR.Certificate checker}
    (certificate :
      Certificate invocation reviewed checker sourceProgram) :
    ArchitectureRefinesNativeChecker
      registeredSHA256MeasurementScheme reviewed.machine checker
      reviewed.executableArtifact reviewed.compactPins.entryPoint :=
  certificate.toStaticCPU.architectureRefinement

end Certificate

/-- Non-vacuous source-program-backed certificate for the exact value
installed in one closed registry branch. -/
structure InstalledCertificate
    (invocation : RegisteredArchitectureInvocation)
    (checker : NativeCheckerSemantics)
    (sourceProgram :
      DeterministicFinalizerIR.Certificate checker) : Type 1 where
  reviewed : ReviewedArchitectureRun invocation
  installed : invocation.reviewedRun = some reviewed
  certificate :
    Certificate invocation reviewed checker sourceProgram

namespace InstalledCertificate

/-- An installed source-program-backed certificate supplies the universal
closed-refinement shape used by the compact capstones. -/
theorem closedRefinement
    {invocation : RegisteredArchitectureInvocation}
    {checker : NativeCheckerSemantics}
    {sourceProgram :
      DeterministicFinalizerIR.Certificate checker}
    (certificate :
      InstalledCertificate invocation checker sourceProgram) :
    ∀ reviewed : ReviewedArchitectureRun invocation,
      invocation.reviewedRun = some reviewed →
        ArchitectureRefinesNativeChecker
          registeredSHA256MeasurementScheme reviewed.machine checker
          reviewed.executableArtifact reviewed.compactPins.entryPoint := by
  intro reviewed selected
  have equalSome :
      some reviewed = some certificate.reviewed :=
    selected.symm.trans certificate.installed
  have equalReviewed : reviewed = certificate.reviewed :=
    Option.some.inj equalSome
  subst reviewed
  exact certificate.certificate.architectureRefinement

end InstalledCertificate

end SparkInterval.Execution.Architecture.DeterministicProgramStaticCPUCertificate
