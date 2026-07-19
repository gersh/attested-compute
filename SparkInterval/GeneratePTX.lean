import SparkInterval.PTX.Generator

set_option autoImplicit false

namespace SparkInterval.GeneratePTX

structure Options where
  input : System.FilePath
  output : System.FilePath

private def usage : String :=
  "usage: sparkinterval-gen --input BATCH.json --output KERNEL.ptx"

private def parseOptions : List String → Except String Options
  | ["--input", input, "--output", output] => pure { input, output }
  | ["--output", output, "--input", input] => pure { input, output }
  | ["--help"] => throw usage
  | _ => throw usage

def run (args : List String) : IO UInt32 := do
  let options ← match parseOptions args with
    | .ok value => pure value
    | .error message =>
        IO.eprintln message
        return 2
  let metadata ← try
    options.input.metadata
  catch error =>
    IO.eprintln s!"cannot inspect {options.input}: {error}"
    return 2
  if metadata.type != .file then
    IO.eprintln s!"input is not an ordinary file: {options.input}"
    return 2
  if metadata.byteSize.toNat > PTX.phase5MaxInputBytes then
    IO.eprintln s!"input exceeds {PTX.phase5MaxInputBytes} bytes"
    return 2
  let input ← try
    IO.FS.readFile options.input
  catch error =>
    IO.eprintln s!"cannot read {options.input}: {error}"
    return 2
  let ptx ← match PTX.generateFromCanonicalBatch input with
    | .ok value => pure value
    | .error message =>
        IO.eprintln s!"generation rejected: {message}"
        return 3
  try
    IO.FS.writeFile options.output ptx
  catch error =>
    IO.eprintln s!"cannot write {options.output}: {error}"
    return 2
  return 0

end SparkInterval.GeneratePTX

def main (args : List String) : IO UInt32 :=
  SparkInterval.GeneratePTX.run args
