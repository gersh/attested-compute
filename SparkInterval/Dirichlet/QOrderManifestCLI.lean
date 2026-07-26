/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.QOrderManifestStreamingWire

/-!
# Native command-line wrapper for the production q-order checker

This wrapper gives auditors a low-memory native entry point for the pure Lean
checker.  Its success report is deliberately labelled unattested: compiling
and running this executable is not, by itself, a compiler-refinement proof, a
secure-execution receipt, or a discharge of an external theorem.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.QOrderManifestCLI

open SparkInterval.Dirichlet.QOrderManifestWire
open SparkInterval.Dirichlet.QOrderManifestStreamingWire

private def usage : String :=
  "usage: sparkinterval-check-dirichlet-qorder TGDQORD1.bin"

private def expectedWireBytes : Nat :=
  headerBytes + sourceQCount * recordBytes

private def acceptedReport (manifest : StreamingManifest) : String :=
  "{\"accepted\":true," ++
    "\"assurance\":\"lean_source_checker_result_unattested\"," ++
    "\"checker\":\"sparkinterval.dirichlet_qorder_streaming.v1\"," ++
    "\"execution_order_sha256\":\"" ++ pinnedExecutionOrderSHA256 ++ "\"," ++
    "\"external_atom_discharged\":false," ++
    "\"manifest_sha256\":\"" ++ pinnedManifestSHA256 ++ "\"," ++
    "\"q_count\":" ++ toString manifest.header.qCount ++ "," ++
    "\"source_roster_sha256\":\"" ++ pinnedSourceRosterSHA256 ++ "\"," ++
    "\"t_row_count\":" ++ toString manifest.header.tRowCount ++ "," ++
    "\"trusted_execution_attested\":false}"

private def checkFile (path : String) : IO UInt32 := do
  let inputPath : System.FilePath := path
  let metadata ← try
      inputPath.metadata
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-qorder: cannot inspect {path}: {error}"
      return 2
  if metadata.type != .file then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-qorder: input is not an ordinary file: {path}"
    return 2
  if metadata.byteSize.toNat != expectedWireBytes then
    IO.eprintln
      s!"sparkinterval-check-dirichlet-qorder: expected {expectedWireBytes} bytes"
    return 1
  let raw ← try
      IO.FS.readBinFile inputPath
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-dirichlet-qorder: cannot read {path}: {error}"
      return 2
  match QOrderManifestStreamingWire.checkFullSourceManifest raw with
  | none =>
      IO.eprintln
        "sparkinterval-check-dirichlet-qorder: manifest check failed"
      return 1
  | some manifest =>
      IO.println (acceptedReport manifest)
      return 0

def run (arguments : List String) : IO UInt32 :=
  match arguments with
  | [path] => checkFile path
  | _ => do
      IO.eprintln usage
      return 2

end SparkInterval.Dirichlet.QOrderManifestCLI

def main (arguments : List String) : IO UInt32 :=
  SparkInterval.Dirichlet.QOrderManifestCLI.run arguments
