/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.A7BoundaryWire

/-!
# Command-line front end for the Lean A.7 compact-wire model

This executable is the *same source text* as the Lean reference semantics: it
reads one `TGA7WIR1` file and prints the verdict of
`A7BoundaryWire.checkBytes` / `checkRetainedBytes`, the very functions whose
soundness theorems are proved in `A7BoundaryWire.lean`.

It exists so that the decision procedure the project reasons about can also be
*executed* -- locally by a reviewer, or inside an enclave -- without anybody
having to believe that a separately written Python program decides the same
predicate.  Running it changes no Lean proof: nothing here is imported by a
theorem, and no proof on any cone acquires `Lean.ofReduceBool` because of it.
Compiled execution is evidence for a human, not a step in a proof.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.A7BoundaryWireCLI

open SparkInterval.TernaryGoldbach.A7BoundaryWire

/-- Refuse inputs that cannot be a well-formed wire before touching them. -/
def maximumWireBytes : Nat := 144 + 2_000_000 * 88

private def usage : String :=
  "usage: sparkinterval-check-a7-wire WIRE.tga7wir1 [--retained]"

def checkPath (path : String) (retained : Bool) : IO UInt32 := do
  let inputPath : System.FilePath := path
  let metadata ← try
      inputPath.metadata
    catch error =>
      IO.eprintln s!"sparkinterval-check-a7-wire: cannot inspect {path}: {error}"
      return 2
  if metadata.type != .file then
    IO.eprintln s!"sparkinterval-check-a7-wire: input is not an ordinary file: {path}"
    return 2
  if metadata.byteSize.toNat > maximumWireBytes then
    IO.eprintln s!"sparkinterval-check-a7-wire: input exceeds {maximumWireBytes} bytes"
    return 2
  let raw ← try
      IO.FS.readBinFile inputPath
    catch error =>
      IO.eprintln s!"sparkinterval-check-a7-wire: cannot read {path}: {error}"
      return 2
  let accepted := if retained then checkRetainedBytes raw else checkBytes raw
  IO.println (if accepted then "true" else "false")
  return (if accepted then 0 else 1)

end SparkInterval.TernaryGoldbach.A7BoundaryWireCLI

open SparkInterval.TernaryGoldbach.A7BoundaryWireCLI in
def main (args : List String) : IO UInt32 := do
  match args with
  | [path] => checkPath path false
  | [path, "--retained"] => checkPath path true
  | _ =>
      IO.eprintln "usage: sparkinterval-check-a7-wire WIRE.tga7wir1 [--retained]"
      return 2
