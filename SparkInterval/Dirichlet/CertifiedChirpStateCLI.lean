/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedChirpStateWire

/-!
# Native CLI for checking positive Bluestein chirp-state dumps

This wrapper reports the first source-order row rejected by the pure Lean
checker. A successful native run is useful replay evidence, but is explicitly
not a compiler-refinement theorem or an attested execution receipt.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedChirpStateCLI

open SparkInterval.Dirichlet.CertifiedChirpStateWire

private def usage : String :=
  "usage: sparkinterval-check-dirichlet-chirp-state FILE LENGTH WORK_PRECISION OUTPUT_PRECISION"

private def failureName : FailureKind → String
  | .malformedRow => "malformed_row"
  | .chirp => "chirp"
  | .oddStep => "odd_step"

private def checkFile
    (path : String) (length workPrecision outputPrecision : Nat) : IO UInt32 := do
  if length = 0 then
    IO.eprintln "sparkinterval-check-dirichlet-chirp-state: LENGTH must be positive"
    return 2
  let inputPath : System.FilePath := path
  let metadata ← try
      inputPath.metadata
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-chirp-state: cannot inspect {path}: {error}"
      return 2
  if metadata.type != .file then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-chirp-state: input is not an ordinary file: {path}"
    return 2
  let expectedBytes := recordBytes * length
  if metadata.byteSize.toNat != expectedBytes then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-chirp-state: expected exactly {expectedBytes} bytes, got {metadata.byteSize.toNat}"
    return 1
  let raw ← try
      IO.FS.readBinFile inputPath
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-chirp-state: cannot read {path}: {error}"
      return 2
  if raw.size != expectedBytes then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-chirp-state: file size changed while reading; expected exactly {expectedBytes} bytes, got {raw.size}"
    return 1
  match firstFailure? workPrecision outputPrecision length raw with
  | some failure =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-chirp-state: rejected index={failure.index} component={failureName failure.kind}"
      return 1
  | none =>
      IO.println <|
        "{\"accepted\":true," ++
        "\"assurance\":\"lean_source_checker_result_unattested\"," ++
        "\"checker\":\"sparkinterval.dirichlet_positive_chirp_state.v1\"," ++
        "\"external_atom_discharged\":false," ++
        "\"length\":" ++ toString length ++ "," ++
        "\"output_precision\":" ++ toString outputPrecision ++ "," ++
        "\"row_count\":" ++ toString length ++ "," ++
        "\"roots_checked\":" ++ toString (2 * length) ++ "," ++
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

end SparkInterval.Dirichlet.CertifiedChirpStateCLI

def main (arguments : List String) : IO UInt32 :=
  SparkInterval.Dirichlet.CertifiedChirpStateCLI.run arguments
