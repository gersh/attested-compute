import SparkInterval.PTX.Generator

set_option autoImplicit false

namespace SparkInterval.GeneratePTX

structure Options where
  input : System.FilePath
  output : System.FilePath
  target : PTX.EmitterTarget

private def usage : String :=
  "usage: sparkinterval-gen --target {sm_121|sm_90} " ++
    "--input BATCH.json --output KERNEL.ptx"

private structure PartialOptions where
  input : Option System.FilePath := none
  output : Option System.FilePath := none
  target : Option PTX.EmitterTarget := none

private def parseTarget : String → Except String PTX.EmitterTarget
  | "sm_121" => pure .sm121
  | "sm_90" => pure .sm90
  | value => throw s!"unsupported target {value}; expected sm_121 or sm_90"

private def finishOptions (options : PartialOptions) : Except String Options :=
  match options.input, options.output, options.target with
  | some input, some output, some target => pure { input, output, target }
  | _, _, _ => throw usage

private def parseOptionsAux : List String → PartialOptions → Except String Options
  | [], options => finishOptions options
  | "--help" :: _, _ => throw usage
  | "--input" :: value :: rest, options => do
      if options.input.isSome then throw "--input may be supplied only once"
      parseOptionsAux rest { options with input := some value }
  | "--output" :: value :: rest, options => do
      if options.output.isSome then throw "--output may be supplied only once"
      parseOptionsAux rest { options with output := some value }
  | "--target" :: value :: rest, options => do
      if options.target.isSome then throw "--target may be supplied only once"
      let target ← parseTarget value
      parseOptionsAux rest { options with target := some target }
  | option :: _, _ => throw s!"unknown or incomplete option: {option}\n{usage}"

private def parseOptions (args : List String) : Except String Options :=
  parseOptionsAux args {}

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
  let ptx ← match PTX.generateFromCanonicalBatchFor options.target input with
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
