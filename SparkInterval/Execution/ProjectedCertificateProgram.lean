/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureReceipt
import SparkInterval.Execution.DeterministicFinalizerIR

/-!
# Artifact-program projection to a fixed downstream checker

Legacy campaign checkers often consume a small canonical descriptor, whereas
an honest deterministic finalizer must consume the complete certificate
artifact.  Identifying those byte strings would be unsound.  This module
keeps the two checkers distinct:

* `sourceChecker` accepts the complete runtime artifact bytes;
* a deterministic source program refines that checker on the same bytes; and
* an ordinary theorem projects successful artifact acceptance to one fixed
  downstream checker/input/result.

The projection never changes the input of an architecture execution.  The
receipt-backed executable is proved against `sourceChecker`; only after that
proof succeeds is its mathematical consequence exported at the fixed legacy
boundary.  No digest, receipt, or proposition is passed to the executable.
-/

set_option autoImplicit false

namespace
  SparkInterval.Execution.Architecture.ProjectedCertificateProgram

open DeterministicFinalizerIR

/-- One complete-artifact source program and its fixed downstream projection.

`downstreamInput` and `downstreamResult` are fields of the reviewed source
definition, not values selected by a receipt. -/
structure Certificate
    (sourceChecker downstreamChecker : NativeCheckerSemantics) : Type where
  sourceProgram : DeterministicFinalizerIR.Certificate sourceChecker
  downstreamInput : ByteArray
  downstreamResult : ByteArray
  project :
    ∀ {artifactBytes outputBytes : ByteArray},
      sourceChecker.accepts artifactBytes outputBytes →
        downstreamChecker.accepts downstreamInput downstreamResult

namespace Certificate

/-- A successful evaluation of the exact artifact program implies the fixed
downstream checker acceptance. -/
theorem downstream_of_returned
    {sourceChecker downstreamChecker : NativeCheckerSemantics}
    (certificate : Certificate sourceChecker downstreamChecker)
    {artifactBytes outputBytes : ByteArray}
    (returned :
      certificate.sourceProgram.program.run artifactBytes =
        .returned outputBytes) :
    downstreamChecker.accepts
      certificate.downstreamInput certificate.downstreamResult :=
  certificate.project (certificate.sourceProgram.accepts returned)

/-- A compact architecture receipt for the artifact checker projects to the
fixed downstream checker without exposing or locally replaying the hidden
artifact bytes.

The architecture refinement and the sole receipt trust boundary must already
have produced `OpaqueNativeAcceptance` for `sourceChecker`.  This theorem is
only ordinary existential elimination followed by `project`. -/
theorem downstream_of_opaqueNativeAcceptance
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {pins : CompactRunPins}
    {sourceChecker downstreamChecker : NativeCheckerSemantics}
    (certificate : Certificate sourceChecker downstreamChecker)
    (accepted :
      OpaqueNativeAcceptance scheme machine sourceChecker pins) :
    downstreamChecker.accepts
      certificate.downstreamInput certificate.downstreamResult := by
  rcases accepted with ⟨_run, _pins, _execution, sourceAccepted⟩
  exact certificate.project sourceAccepted

end Certificate

end SparkInterval.Execution.Architecture.ProjectedCertificateProgram
