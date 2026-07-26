/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.DeterministicFinalizerIR

/-!
# Canonical finalizer with a source-installed artifact

A cloud result is not known when its source checker is first written.  The
reviewable post-run workflow is therefore:

1. retain the complete finalizer artifact;
2. generate a source file containing those exact bytes;
3. parse and check those bytes with a total data-only algorithm; and
4. prove that a successful check refines one fixed native checker.

This module implements that program shape while preserving the native
checker's small canonical invocation input.  `installedArtifact = none` is
the pre-run state: the program is fully executable but always fails closed.

The artifact option is source data, not a runtime argument.  In particular,
neither a receipt nor a caller can select an alternative artifact after the
source-program proof has been reviewed.
-/

set_option autoImplicit false

namespace
  SparkInterval.Execution.Architecture.CanonicalInstalledArtifactProgram

open DeterministicFinalizerIR

def inputRejectedCode : Nat := 1
def artifactAbsentCode : Nat := 2
def parseRejectedCode : Nat := 3
def checkRejectedCode : Nat := 4

/-- Total finalizer over one source-installed, complete artifact. -/
def run
    {CertificateData : Type}
    (canonicalInput successResult : ByteArray)
    (installedArtifact : Option ByteArray)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (inputBytes : ByteArray) :
    Outcome :=
  if inputBytes = canonicalInput then
    match installedArtifact with
    | none => .rejected artifactAbsentCode
    | some artifactBytes =>
        match decode artifactBytes with
        | none => .rejected parseRejectedCode
        | some certificate =>
            if check certificate then
              .returned successResult
            else
              .rejected checkRejectedCode
  else
    .rejected inputRejectedCode

def program
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (canonicalInput successResult : ByteArray)
    (installedArtifact : Option ByteArray)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool) :
    Program where
  contractId := checker.checkerId
  run :=
    run canonicalInput successResult installedArtifact decode check

/-- Ordinary semantic obligation for an installed artifact.

The proof receives data and equalities only.  It is not available to the
runtime program and may not be replaced by a receipt signature. -/
def InstalledArtifactSound
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (canonicalInput successResult : ByteArray)
    (installedArtifact : Option ByteArray)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool) : Prop :=
  ∀ {artifactBytes : ByteArray} {certificate : CertificateData},
    installedArtifact = some artifactBytes →
      decode artifactBytes = some certificate →
      check certificate = true →
      checker.accepts canonicalInput successResult

theorem refinesNativeChecker
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (canonicalInput successResult : ByteArray)
    (installedArtifact : Option ByteArray)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (sound :
      InstalledArtifactSound checker canonicalInput successResult
        installedArtifact decode check) :
    RefinesNativeChecker
      (program checker canonicalInput successResult
        installedArtifact decode check)
      checker := by
  refine {
    contractId := rfl
    successful := ?_
  }
  intro inputBytes outputBytes returned
  simp only [Program.successBehavior, program] at returned
  unfold run at returned
  split at returned
  · rename_i inputExact
    subst inputBytes
    cases installed : installedArtifact with
    | none =>
        simp [installed] at returned
    | some artifactBytes =>
        cases decoded : decode artifactBytes with
        | none =>
            simp [installed, decoded] at returned
        | some certificate =>
            cases checked : check certificate with
            | false =>
                simp [installed, decoded, checked] at returned
            | true =>
                simp only [installed, decoded, checked, ↓reduceIte,
                  Outcome.returned.injEq] at returned
                subst outputBytes
                exact sound installed decoded checked
  · contradiction

def certificate
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (canonicalInput successResult : ByteArray)
    (installedArtifact : Option ByteArray)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (sound :
      InstalledArtifactSound checker canonicalInput successResult
        installedArtifact decode check) :
    Certificate checker where
  program :=
    program checker canonicalInput successResult
      installedArtifact decode check
  refinement :=
    refinesNativeChecker checker canonicalInput successResult
      installedArtifact decode check sound

/-- Before an artifact is installed the finalizer rejects every input. -/
@[simp] theorem run_none
    {CertificateData : Type}
    (canonicalInput successResult : ByteArray)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (inputBytes : ByteArray) :
    run canonicalInput successResult none decode check inputBytes =
      if inputBytes = canonicalInput then
        .rejected artifactAbsentCode
      else
        .rejected inputRejectedCode := by
  unfold run
  split <;> rfl

/-- The semantic obligation for the pre-run state is discharged without any
mathematical proposition or receipt evidence. -/
theorem none_sound
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (canonicalInput successResult : ByteArray)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool) :
    InstalledArtifactSound checker canonicalInput successResult
      none decode check := by
  intro artifactBytes certificate installed
  contradiction

end SparkInterval.Execution.Architecture.CanonicalInstalledArtifactProgram
