/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.CanonicalHex
import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.SASS.SM90DirectedAdd

/-!
# Post-compilation SM90 certificate for one fused large-q addback

The production `reconstructComposeKernel` ends by adding a certified finite-
recovery rectangle to the reconstructed complex rectangle.  In the audited
CUDA 13.0 `sm_90` cubin, the imaginary-component endpoint update at source
line 158 is the consecutive SASS pair

```text
/*3840*/ DADD.RM R12, R12, R22 ;
/*3850*/ DADD.RP R10, R10, R20 ;
```

This module records the decoded operands, validates their complete restricted
dataflow in Lean, and derives the outward interval-addition theorem.  It also
defines a fail-closed composition with the existing registered run-certificate
outcome.  The composition binds the exact cubin hash and a canonical manifest
hash to the run statement.

The proof boundary is intentionally narrow.  The theorem does not prove that
`nvdisasm` decoded the cubin correctly, that NVIDIA SASS assigns the modeled
meaning to `DADD.RM/RP`, that the two instructions are reached with the stated
register values, or that the surrounding multiplication, control flow, memory
operations, driver, and H100 hardware refine Lean.  No registered fused-large-q
invocation exists yet, so the generic registered composition cannot currently
be instantiated by a production large-q receipt.
-/

set_option autoImplicit false

namespace SparkInterval.SASS.SM90

open SparkInterval.Certificate
open SparkInterval.Execution

/-- Artifact and source-location identity carried by one decoded arithmetic
slice.  Raw cubin/SASS bytes stay outside Lean; their SHA-256 digests and the
canonical decoded excerpt are bound here. -/
structure FusedLargeQAddbackCertificate where
  schemaVersion : Nat
  target : String
  sourceFile : String
  helperLine : Nat
  callLine : Nat
  kernelLine : Nat
  functionName : String
  sourceSha256 : String
  cubinSha256 : String
  sassSha256 : String
  lineInfoSassSha256 : String
  canonicalExcerpt : String
  slice : AddSlice
  deriving Repr, DecidableEq, BEq

namespace FusedLargeQAddbackCertificate

/-- Stable manifest preimage to be named by
`RunStatement.artifacts.kernelManifestHash`.  It binds the exact decoded
excerpt as well as all three external artifact digests. -/
def manifestPreimage (certificate : FusedLargeQAddbackCertificate) : String :=
  "sparkinterval.tg.dirichlet-largeq.sass-addback-slice.v1\n" ++
  "target=" ++ certificate.target ++ "\n" ++
  "source_file=" ++ certificate.sourceFile ++ "\n" ++
  "source_sha256=" ++ certificate.sourceSha256 ++ "\n" ++
  "cubin_sha256=" ++ certificate.cubinSha256 ++ "\n" ++
  "sass_sha256=" ++ certificate.sassSha256 ++ "\n" ++
  "line_info_sass_sha256=" ++ certificate.lineInfoSassSha256 ++ "\n" ++
  "function=" ++ certificate.functionName ++ "\n" ++
  "source_site=" ++ toString certificate.helperLine ++ ">" ++
    toString certificate.callLine ++ ">" ++ toString certificate.kernelLine ++
    "\nexcerpt_sha256=" ++ SHA256.digestString certificate.canonicalExcerpt ++ "\n"

def manifestSha256 (certificate : FusedLargeQAddbackCertificate) : String :=
  SHA256.digestString certificate.manifestPreimage

/-- Reviewable structural claim checked before the arithmetic theorem may be
used.  The source-line chain fixes helper `add`, complex `cadd`, and the final
kernel addback respectively. -/
def StructuralValid (certificate : FusedLargeQAddbackCertificate) : Prop :=
  certificate.schemaVersion = 1 ∧
  certificate.target = "sm_90" ∧
  certificate.sourceFile =
    "gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu" ∧
  certificate.helperLine = 54 ∧
  certificate.callLine = 88 ∧
  certificate.kernelLine = 158 ∧
  certificate.functionName = "reconstructComposeKernel" ∧
  isCanonicalLowerHexOfLength 64 certificate.sourceSha256 = true ∧
  isCanonicalLowerHexOfLength 64 certificate.cubinSha256 = true ∧
  isCanonicalLowerHexOfLength 64 certificate.sassSha256 = true ∧
  isCanonicalLowerHexOfLength 64 certificate.lineInfoSassSha256 = true ∧
  certificate.canonicalExcerpt = certificate.slice.render ∧
  certificate.slice.WellFormed

instance instDecidableStructuralValid
    (certificate : FusedLargeQAddbackCertificate) :
    Decidable certificate.StructuralValid := by
  unfold StructuralValid
  infer_instance

/-- Kernel-reducible structural validator. -/
def check (certificate : FusedLargeQAddbackCertificate) : Bool :=
  decide certificate.StructuralValid

theorem check_sound {certificate : FusedLargeQAddbackCertificate}
    (hcheck : certificate.check = true) : certificate.StructuralValid := by
  exact of_decide_eq_true hcheck

/-- Full Lean conclusion of the post-compilation slice validator. -/
structure Validated (certificate : FusedLargeQAddbackCertificate) : Prop where
  structural : certificate.StructuralValid
  arithmetic : certificate.slice.RefinesIntervalAdd

theorem validate {certificate : FusedLargeQAddbackCertificate}
    (hcheck : certificate.check = true) : certificate.Validated := by
  have structural := check_sound hcheck
  exact {
    structural := structural
    arithmetic := AddSlice.wellFormed_refinesIntervalAdd
      structural.2.2.2.2.2.2.2.2.2.2.2.2
  }

/-- Bind the decoded slice to the exact H100 cubin and canonical audit
manifest named by a run statement. -/
def statementCheck (certificate : FusedLargeQAddbackCertificate)
    (statement : RunStatement) : Bool :=
  decide (
    statement.target = .nvidiaH100SM90 ∧
    statement.artifacts.deviceCubinHash = certificate.cubinSha256 ∧
    statement.artifacts.kernelManifestHash = certificate.manifestSha256)

def StatementBound (certificate : FusedLargeQAddbackCertificate)
    (statement : RunStatement) : Prop :=
  statement.target = .nvidiaH100SM90 ∧
  statement.artifacts.deviceCubinHash = certificate.cubinSha256 ∧
  statement.artifacts.kernelManifestHash = certificate.manifestSha256

theorem statementCheck_sound {certificate : FusedLargeQAddbackCertificate}
    {statement : RunStatement}
    (hcheck : certificate.statementCheck statement = true) :
    certificate.StatementBound statement := by
  simpa [statementCheck, StatementBound] using hcheck

end FusedLargeQAddbackCertificate

/-! ## Audited CUDA 13.0 / SM90 artifact instance -/

/-- Exact decoded production pair from the final imaginary-component
finite-recovery addback in `reconstructComposeKernel`. -/
def fusedLargeQFinalImaginaryAddbackSlice : AddSlice := {
  lowerOffset := "3840"
  upperOffset := "3850"
  instructions := [
    { offset := "3840", rounding := .rm, destination := 12,
      left := 12, right := 22 },
    { offset := "3850", rounding := .rp, destination := 10,
      left := 10, right := 20 }
  ]
  left := { lo := 12, hi := 10 }
  right := { lo := 22, hi := 20 }
  result := { lo := 12, hi := 10 }
}

/-- Certificate generated from a local CUDA 13.0.88 `-O3 -lineinfo
-arch=sm_90 --fmad=false --ftz=false --prec-div=true --prec-sqrt=true` cubin.
The binary and disassembly are intentionally not checked into the repository;
the companion tool reproduces this record from retained build artifacts. -/
def fusedLargeQFinalImaginaryAddbackCertificate :
    FusedLargeQAddbackCertificate := {
  schemaVersion := 1
  target := "sm_90"
  sourceFile := "gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu"
  helperLine := 54
  callLine := 88
  kernelLine := 158
  functionName := "reconstructComposeKernel"
  sourceSha256 :=
    "8897947a2538b71af7412716154239de189580fe610b461f067f619eb70db09a"
  cubinSha256 :=
    "f45527356e60d6739f3d02ad57a06d490ae4577d694508951ab1b19f99228e16"
  sassSha256 :=
    "31790c41c183807107c70af793f30f1cc65573bc8eb38907a6fa5bd48052adb7"
  lineInfoSassSha256 :=
    "d9d82f5e3820d02051c3b5e6c4b69175d29fb06362bdc1161b2dc92f2c4aff0b"
  canonicalExcerpt :=
    "/*3840*/ DADD.RM R12, R12, R22 ;\n" ++
    "/*3850*/ DADD.RP R10, R10, R20 ;\n"
  slice := fusedLargeQFinalImaginaryAddbackSlice
}

/-- The closed checked artifact instance passes without a trusted axiom. -/
theorem fusedLargeQFinalImaginaryAddbackCertificate_check :
    fusedLargeQFinalImaginaryAddbackCertificate.check = true := by
  decide

/-- Axiom-free Lean arithmetic/refinement theorem for the actual decoded
production instruction pair. -/
theorem fusedLargeQFinalImaginaryAddback_refinesIntervalAdd :
    fusedLargeQFinalImaginaryAddbackSlice.RefinesIntervalAdd :=
  (FusedLargeQAddbackCertificate.validate
    fusedLargeQFinalImaginaryAddbackCertificate_check).arithmetic

/-- Direct application theorem for the decoded production site: if the four
live SASS registers contain finite endpoint values for the reconstructed and
finite-recovery imaginary intervals, restricted execution succeeds and the
two destination registers describe an interval containing every exact
imaginary addback `zetaValue + recoveryValue`. -/
theorem fusedLargeQFinalImaginaryAddback_contains
    (registers : AddSlice.RegisterFile)
    (zetaImaginary recoveryImaginary : RealInterval)
    (zetaValue recoveryValue : Real)
    (hzetaLo : registers 12 = some (.finite zetaImaginary.lo))
    (hzetaHi : registers 10 = some (.finite zetaImaginary.hi))
    (hrecoveryLo : registers 22 = some (.finite recoveryImaginary.lo))
    (hrecoveryHi : registers 20 = some (.finite recoveryImaginary.hi))
    (hzeta : zetaImaginary.Contains zetaValue)
    (hrecovery : recoveryImaginary.Contains recoveryValue) :
    ∃ (final : AddSlice.RegisterFile) (output : SparkInterval.PTX.F64Interval),
      fusedLargeQFinalImaginaryAddbackSlice.execute registers = some final ∧
      final 12 = some output.lo ∧
      final 10 = some output.hi ∧
      output.ContainsReal (zetaValue + recoveryValue) := by
  rcases fusedLargeQFinalImaginaryAddback_refinesIntervalAdd registers
      zetaImaginary recoveryImaginary hzetaLo hzetaHi hrecoveryLo hrecoveryHi with
    ⟨final, hexecute, hproduces⟩
  rcases AddSlice.producesAdd_contains hproduces hzeta hrecovery with
    ⟨output, hlo, hhi, hcontains⟩
  exact ⟨final, output, hexecute, hlo, hhi, hcontains⟩

/-! ## Composition with the closed execution registry -/

end SparkInterval.SASS.SM90

namespace SparkInterval.Execution

open SparkInterval.SASS.SM90

/-- Require a registered physical outcome, the restricted semantic slice, and
the exact cubin/manifest binding in one Boolean acceptance check. -/
def SignedResultCertificate.outcomeCheckForRegisteredInvocationAndFusedLargeQSlice
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation)
    (sliceCertificate : FusedLargeQAddbackCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation invocation &&
    sliceCertificate.check &&
    sliceCertificate.statementCheck certificate.statement

/-- What Lean can honestly recover from the combined check.  `registered`
contains the repository's sole physical-run axiom dependency; `translation`
and `artifact` are ordinary Lean consequences.  There is deliberately no field
claiming whole-kernel or physical SASS refinement. -/
structure CertifiedRegisteredOutcomeWithFusedLargeQSlice
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation)
    (sliceCertificate : FusedLargeQAddbackCertificate) : Prop where
  registered : certificate.CertifiedOutcomeForRegisteredInvocation invocation
  artifact : sliceCertificate.StatementBound certificate.statement
  translation : sliceCertificate.Validated

namespace SignedResultCertificate

theorem outcomeCheckForRegisteredInvocationAndFusedLargeQSlice_sound
    {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation}
    {sliceCertificate : FusedLargeQAddbackCertificate}
    (hcheck : certificate.outcomeCheckForRegisteredInvocationAndFusedLargeQSlice
      invocation sliceCertificate = true) :
    CertifiedRegisteredOutcomeWithFusedLargeQSlice certificate invocation
      sliceCertificate := by
  simp only [outcomeCheckForRegisteredInvocationAndFusedLargeQSlice,
    Bool.and_eq_true] at hcheck
  exact {
    registered := outcomeCheckForRegisteredInvocation_sound hcheck.1.1
    artifact := FusedLargeQAddbackCertificate.statementCheck_sound hcheck.2
    translation := FusedLargeQAddbackCertificate.validate hcheck.1.2
  }

end SignedResultCertificate

end SparkInterval.Execution
