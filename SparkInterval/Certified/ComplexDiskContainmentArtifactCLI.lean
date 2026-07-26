/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.Certified.ComplexDiskContainmentWire

/-!
# Native checker for the retained PT21 block-0 containment artifact

The CLI accepts only the frozen headerless stream of 131,072 consecutive
48-byte `ordinary || candidate` frames emitted by the live transform
qualifier.  It checks the exact file size and SHA-256 before replaying every
frame through the base-trio exact-rational containment checker.

A successful run is replay evidence from this Lean source checker.  It is not
an attested execution receipt, compiler-refinement theorem, or proof that the
ordinary CUDA disks realize the intended Hardy-Z values.
-/

set_option autoImplicit false

namespace SparkInterval.Certified.ComplexDisk.Containment.ArtifactCLI

open SparkInterval.Certified.ComplexDisk.Containment.Wire

def block0FrameCount : Nat := 131072
def block0ArtifactBytes : Nat :=
  block0FrameCount * rawContainmentPairByteSize
def block0ArtifactSHA256 : String :=
  "a4379093cd52ab0b90ed73cf60f617003490eefd2a1379115d9a3b1bdf5125d7"

private def usage : String :=
  "usage: sparkinterval-check-pt21-containment --block0 FILE"

private def checkBlock0 (path : String) : IO UInt32 := do
  let inputPath : System.FilePath := path
  let metadata ← try
      inputPath.metadata
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-pt21-containment: cannot inspect {path}: {error}"
      return 2
  if metadata.type != .file then
    IO.eprintln
      s!"sparkinterval-check-pt21-containment: input is not an ordinary file: {path}"
    return 2
  if metadata.byteSize.toNat != block0ArtifactBytes then
    IO.eprintln
      s!"sparkinterval-check-pt21-containment: expected exactly {block0ArtifactBytes} bytes, got {metadata.byteSize.toNat}"
    return 1
  let raw ← try
      IO.FS.readBinFile inputPath
    catch error =>
      IO.eprintln
        s!"sparkinterval-check-pt21-containment: cannot read {path}: {error}"
      return 2
  if raw.size != block0ArtifactBytes then
    IO.eprintln
      s!"sparkinterval-check-pt21-containment: file size changed while reading; expected exactly {block0ArtifactBytes} bytes, got {raw.size}"
    return 1
  let artifactSHA256 :=
    SparkInterval.Certificate.SHA256.digestByteArray raw
  if artifactSHA256 != block0ArtifactSHA256 then
    IO.eprintln
      "sparkinterval-check-pt21-containment: artifact SHA-256 differs"
    return 1
  if !checkRawContainmentArtifactBytes block0FrameCount raw.toList then
    IO.eprintln
      "sparkinterval-check-pt21-containment: exact containment replay rejected"
    return 1
  IO.println <|
    "{\"accepted\":true," ++
    "\"artifact_bytes\":" ++ toString raw.size ++ "," ++
    "\"artifact_sha256\":\"" ++ artifactSHA256 ++ "\"," ++
    "\"assurance\":\"lean_source_checker_result_unattested\"," ++
    "\"checker\":\"sparkinterval.pt21_block0_containment.v1\"," ++
    "\"frame_bytes\":" ++ toString rawContainmentPairByteSize ++ "," ++
    "\"frame_count\":" ++ toString block0FrameCount ++ "," ++
    "\"ordinary_hardy_z_realization_proved\":false," ++
    "\"pt21_atom_discharged\":false," ++
    "\"trusted_execution_attested\":false}"
  return 0

def run (arguments : List String) : IO UInt32 :=
  match arguments with
  | ["--block0", path] => checkBlock0 path
  | _ => do
      IO.eprintln usage
      pure 2

end SparkInterval.Certified.ComplexDisk.Containment.ArtifactCLI

def main (arguments : List String) : IO UInt32 :=
  SparkInterval.Certified.ComplexDisk.Containment.ArtifactCLI.run arguments
