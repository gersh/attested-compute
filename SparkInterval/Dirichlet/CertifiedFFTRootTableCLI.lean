/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedFFTRootTableWire

/-!
# Native CLI for checking positive flattened radix-2 FFT root tables

This wrapper reports the first source-order row rejected by the pure Lean
checker.  A successful native run is useful replay evidence, but is explicitly
not a compiler-refinement theorem or an attested execution receipt.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedFFTRootTableCLI

open SparkInterval.Dirichlet.CertifiedFFTRootTableWire

private def usage : String :=
  "usage: sparkinterval-check-dirichlet-fft-roots FILE LENGTH WORK_PRECISION OUTPUT_PRECISION"

private def failureName : FailureKind → String
  | .malformedRecord => "malformed_record"
  | .root => "root"

private def checkFile
    (path : String) (length workPrecision outputPrecision : Nat) : IO UInt32 := do
  if !sourceConvolution length then
    IO.eprintln
      "sparkinterval-check-dirichlet-fft-roots: LENGTH must be one of 4, 8, ..., 1048576"
    return 2
  let inputPath : System.FilePath := path
  let metadata ← try
      inputPath.metadata
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-fft-roots: cannot inspect {path}: {error}"
      return 2
  if metadata.type != .file then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-fft-roots: input is not an ordinary file: {path}"
    return 2
  let rootCount := length - 1
  let expectedBytes := recordBytes * rootCount
  if metadata.byteSize.toNat != expectedBytes then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-fft-roots: expected exactly {expectedBytes} bytes, got {metadata.byteSize.toNat}"
    return 1
  let raw ← try
      IO.FS.readBinFile inputPath
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-fft-roots: cannot read {path}: {error}"
      return 2
  if raw.size != expectedBytes then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-fft-roots: file size changed while reading; expected exactly {expectedBytes} bytes, got {raw.size}"
    return 1
  match firstFailure? workPrecision outputPrecision length raw with
  | some failure =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-fft-roots: rejected flat_index={failure.flatIndex} stage={failure.stage} exponent={failure.exponent} component={failureName failure.kind}"
      return 1
  | none =>
      IO.println <|
        "{\"accepted\":true," ++
        "\"assurance\":\"lean_source_checker_result_unattested\"," ++
        "\"checker\":\"sparkinterval.dirichlet_positive_fft_root_table.v1\"," ++
        "\"external_atom_discharged\":false," ++
        "\"length\":" ++ toString length ++ "," ++
        "\"output_precision\":" ++ toString outputPrecision ++ "," ++
        "\"root_count\":" ++ toString rootCount ++ "," ++
        "\"trusted_execution_attested\":false," ++
        "\"work_precision\":" ++ toString workPrecision ++ "}"
      return 0

def run (arguments : List String) : IO UInt32 :=
  match arguments with
  | [path, lengthText, workText, outputText] =>
      match lengthText.toNat?, workText.toNat?, outputText.toNat? with
      | some length, some workPrecision, some outputPrecision =>
          checkFile path length workPrecision outputPrecision
      | _, _, _ => do
          IO.eprintln usage
          pure 2
  | _ => do
      IO.eprintln usage
      pure 2

end SparkInterval.Dirichlet.CertifiedFFTRootTableCLI

def main (arguments : List String) : IO UInt32 :=
  SparkInterval.Dirichlet.CertifiedFFTRootTableCLI.run arguments
