/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.DeterministicFinalizerIR

/-!
# Deterministic finalizer for parsed data certificates

Production certificate artifacts are not generally known until a cloud run
finishes. A source program must therefore consume the complete artifact bytes;
it must not obtain a proposition from a hash lookup or close over proof
evidence supplied by its caller.

This module implements the common fail-closed program shape:

1. parse the complete input bytes into a data-only certificate;
2. reject malformed input;
3. run one total Boolean certificate check;
4. return one fixed result only when that check succeeds; and
5. use an ordinary theorem from parse/check success to one fixed
   `NativeCheckerSemantics`.

The runtime program never calls `nativeChecker.accepts`. The acceptance
relation appears only in the refinement proof. Constructing a certificate
below also does not assert that an accepting production artifact exists, that
an executable implements the source program, or that a physical run occurred.
-/

set_option autoImplicit false

namespace
  SparkInterval.Execution.Architecture.ParsedCertificateProgram

open DeterministicFinalizerIR

/-- Rejection code for malformed certificate bytes. -/
def parseRejectedCode : Nat :=
  1

/-- Rejection code for a parsed certificate whose Boolean check fails. -/
def checkRejectedCode : Nat :=
  2

/-- Total parsed-certificate finalizer.

`CertificateData` is data, not a proposition or proof object. Campaign
modules are responsible for choosing a decoder which binds the complete
serialized artifact and a Boolean which checks every required field. -/
def run
    {CertificateData : Type}
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (successResult inputBytes : ByteArray) :
    Outcome :=
  match decode inputBytes with
  | none =>
      .rejected parseRejectedCode
  | some certificate =>
      if check certificate then
        .returned successResult
      else
        .rejected checkRejectedCode

/-- Source program bound to the identifier of one fixed native checker. -/
def program
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (successResult : ByteArray) :
    Program where
  contractId := checker.checkerId
  run := run decode check successResult

/-- Exact successful behavior of the total parser/checker. -/
theorem returned_iff
    {CertificateData : Type}
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (successResult inputBytes outputBytes : ByteArray) :
    run decode check successResult inputBytes = .returned outputBytes ↔
      ∃ certificate : CertificateData,
        decode inputBytes = some certificate ∧
          check certificate = true ∧
          successResult = outputBytes := by
  unfold run
  cases decoded : decode inputBytes with
  | none =>
      simp
  | some certificate =>
      cases checked : check certificate <;>
        simp [checked]

/-- Ordinary soundness obligation for a campaign parser/checker.

The theorem is universal in the complete input bytes. Thus a parser cannot
silently discard the bytes whose identity is needed by the checker relation.
-/
def ParseCheckSound
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (successResult : ByteArray) : Prop :=
  ∀ {inputBytes : ByteArray} {certificate : CertificateData},
    decode inputBytes = some certificate →
      check certificate = true →
        checker.accepts inputBytes successResult

/-- A sound total parser/checker refines its fixed native checker.

The executable branch uses only `decode` and `check`; `sound` is erased proof
data and cannot be consulted by the runtime program. -/
theorem refinesNativeChecker
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (successResult : ByteArray)
    (sound : ParseCheckSound checker decode check successResult) :
    RefinesNativeChecker
      (program checker decode check successResult) checker := by
  refine {
    contractId := rfl
    successful := ?_
  }
  intro inputBytes outputBytes returned
  rcases
      (returned_iff decode check successResult inputBytes outputBytes).mp
        returned with
    ⟨certificate, decoded, checked, outputExact⟩
  subst outputBytes
  exact sound decoded checked

/-- Concrete source-program certificate assembled from a campaign's
data-only decoder, total Boolean, and ordinary soundness theorem.

This value is a source implementation certificate only. It contains no
accepted artifact, machine-code refinement, receipt, signature, or axiom. -/
def certificate
    {CertificateData : Type}
    (checker : NativeCheckerSemantics)
    (decode : ByteArray → Option CertificateData)
    (check : CertificateData → Bool)
    (successResult : ByteArray)
    (sound : ParseCheckSound checker decode check successResult) :
    Certificate checker where
  program := program checker decode check successResult
  refinement :=
    refinesNativeChecker checker decode check successResult sound

end SparkInterval.Execution.Architecture.ParsedCertificateProgram
