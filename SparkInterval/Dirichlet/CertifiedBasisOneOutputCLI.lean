/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.Dirichlet.CertifiedBasisOneOutputWire

/-!
# Native CLI for checking the maximum-order basis-one output

The CLI consumes the complete standard `TGDAFFO1` artifact.  It reports a
SHA-256 digest of all bytes, including the run-dependent elapsed-time header
word.  A successful native run is useful replay evidence, but is explicitly
not a compiler-refinement theorem or an attested execution receipt.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedBasisOneOutputCLI

open SparkInterval.Dirichlet.CertifiedBasisOneOutputWire

private def usage : String :=
  "usage: sparkinterval-check-dirichlet-basis-one-output --maximum-order-delta-one FILE WORK_PRECISION OUTPUT_PRECISION"

private def failureName : FailureKind → String
  | .malformedRecord => "malformed_record"
  | .root => "root"

private def checkFile
    (path : String) (workPrecision outputPrecision : Nat) : IO UInt32 := do
  let inputPath : System.FilePath := path
  let metadata ← try
      inputPath.metadata
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-basis-one-output: cannot inspect {path}: {error}"
      return 2
  if metadata.type != .file then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-basis-one-output: input is not an ordinary file: {path}"
    return 2
  if metadata.byteSize.toNat != productionArtifactBytes then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-basis-one-output: expected exactly {productionArtifactBytes} bytes, got {metadata.byteSize.toNat}"
    return 1
  let raw ← try
      IO.FS.readBinFile inputPath
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-basis-one-output: cannot read {path}: {error}"
      return 2
  if raw.size != productionArtifactBytes then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-basis-one-output: file size changed while reading; expected exactly {productionArtifactBytes} bytes, got {raw.size}"
    return 1
  let some header := readHeader? raw
    | IO.eprintln
        "sparkinterval-check-dirichlet-basis-one-output: rejected standard TGDAFFO1 header"
      return 1
  if !headerMatches
      productionQ productionOrder productionButterflies header then
    IO.eprintln
      "sparkinterval-check-dirichlet-basis-one-output: rejected pinned maximum-order header fields"
    return 1
  match firstFailureFromAt?
      workPrecision outputPrecision productionOrder raw headerBytes
      0 productionOrder with
  | some failure =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-basis-one-output: rejected index={failure.index} component={failureName failure.kind}"
      return 1
  | none =>
      let artifactSHA256 :=
        SparkInterval.Certificate.SHA256.digestByteArray raw
      IO.println <|
        "{\"accepted\":true," ++
        "\"artifact_sha256\":\"" ++ artifactSHA256 ++ "\"," ++
        "\"assurance\":\"lean_source_checker_result_unattested\"," ++
        "\"checker\":\"sparkinterval.dirichlet_maximum_order_basis_one_output.v1\"," ++
        "\"external_atom_discharged\":false," ++
        "\"format\":\"TGDAFFO1\"," ++
        "\"input_nonzero_index\":1," ++
        "\"order\":" ++ toString productionOrder ++ "," ++
        "\"output_precision\":" ++ toString outputPrecision ++ "," ++
        "\"q\":" ++ toString productionQ ++ "," ++
        "\"radix2_butterflies\":" ++
          toString productionButterflies ++ "," ++
        "\"row_count\":" ++ toString productionOrder ++ "," ++
        "\"semantic\":\"positive_dft_basis_one\"," ++
        "\"trusted_execution_attested\":false," ++
        "\"work_precision\":" ++ toString workPrecision ++ "}"
      return 0

def run (arguments : List String) : IO UInt32 :=
  match arguments with
  | ["--maximum-order-delta-one", path, workText, outputText] =>
      match workText.toNat?, outputText.toNat? with
      | some workPrecision, some outputPrecision =>
          checkFile path workPrecision outputPrecision
      | _, _ => do
          IO.eprintln usage
          pure 2
  | _ => do
      IO.eprintln usage
      pure 2

end SparkInterval.Dirichlet.CertifiedBasisOneOutputCLI

def main (arguments : List String) : IO UInt32 :=
  SparkInterval.Dirichlet.CertifiedBasisOneOutputCLI.run arguments
