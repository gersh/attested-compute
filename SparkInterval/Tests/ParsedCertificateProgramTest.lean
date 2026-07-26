/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.ParsedCertificateProgram

set_option autoImplicit false

namespace SparkInterval.Tests.ParsedCertificateProgram

open SparkInterval.Execution
open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open SparkInterval.Execution.Architecture.ParsedCertificateProgram

private def goodInput : ByteArray :=
  "certificate:7".toUTF8

private def goodResult : ByteArray :=
  "true".toUTF8

private def decode (input : ByteArray) : Option Nat :=
  if input = goodInput then some 7 else none

private def check (value : Nat) : Bool :=
  value == 7

private def checker : NativeCheckerSemantics where
  checkerId := "sparkinterval.test.parsed-certificate.v1"
  accepts := fun input output =>
    input = goodInput ∧ output = goodResult

private theorem sound :
    ParseCheckSound checker decode check goodResult := by
  intro input certificate decoded checked
  simp only [decode] at decoded
  split at decoded
  · rename_i inputExact
    subst input
    simp only [Option.some.injEq] at decoded
    subst certificate
    exact ⟨rfl, rfl⟩
  · contradiction

private def certified :
    Certificate checker :=
  certificate checker decode check goodResult sound

example :
    certified.program.run goodInput = .returned goodResult := by
  simp [certified, certificate, program, run, decode, check, goodInput]

example {input output : ByteArray}
    (returned : certified.program.run input = .returned output) :
    checker.accepts input output :=
  certified.accepts returned

example (badInput : ByteArray) (different : badInput ≠ goodInput) :
    certified.program.run badInput = .rejected parseRejectedCode := by
  simp [certified, certificate, program, run, decode, different]

#print axioms returned_iff
#print axioms refinesNativeChecker
#print axioms certified

end SparkInterval.Tests.ParsedCertificateProgram
