/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedRootTable

/-!
# Replay benchmark for certified DFT roots

Run, for example:

```
lake env lean --run SparkInterval/Tests/CertifiedRootBenchmark.lean reference 25000 52
lake env lean --run SparkInterval/Tests/CertifiedRootBenchmark.lean fast 25000 52

lake build sparkinterval-certified-root-benchmark
.lake/build/bin/sparkinterval-certified-root-benchmark fast 25000 80
.lake/build/bin/sparkinterval-certified-root-benchmark fast 25000 128 192
```

Both modes fold every rectangle width into a checksum, ensuring that root
generation is evaluated rather than optimized away.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedRootBenchmark

open SparkInterval.Certified
open SparkInterval.Dirichlet

def rectWidth (R : ComplexRect) : ℚ :=
  (R.re.hi - R.re.lo) + (R.im.hi - R.im.lo)

def run
    (generator : Nat → Option ComplexRect)
    (label : String) (count : Nat) : IO Unit := do
  let mut checksum : ℚ := 0
  let mut widest : ℚ := 0
  for exponent in [0:count] do
    match generator exponent with
    | none => throw <| IO.userError s!"{label} failed at {exponent}"
    | some rectangle =>
        let width := rectWidth rectangle
        checksum := checksum + width
        widest := max widest width
  IO.println s!"{label} {count}: total={checksum}, widest={widest}"

def runMain (arguments : List String) : IO Unit := do
  match arguments with
  | [mode, countText] | [mode, countText, _] |
      [mode, countText, _, _] =>
      let some count := countText.toNat?
        | throw <| IO.userError "count must be a natural number"
      let outputPrecision :=
        match arguments with
        | [_, _, outputText] | [_, _, outputText, _] =>
            outputText.toNat?
        | _ => some 52
      let some outputPrecision := outputPrecision
        | throw <| IO.userError "output precision must be a natural number"
      let workPrecision :=
        match arguments with
        | [_, _, _, workText] => workText.toNat?
        | _ => some 160
      let some workPrecision := workPrecision
        | throw <| IO.userError "work precision must be a natural number"
      let order := 100003
      if mode = "reference" then
        run
          (CertifiedRootTable.rootRect?
            40 workPrecision outputPrecision order)
          "reference" count
      else if mode = "fast" then
        run
          (CertifiedRootTable.rootRectFast?
            workPrecision outputPrecision order)
          "fast" count
      else
        throw <| IO.userError "mode must be reference or fast"
  | _ =>
      throw <| IO.userError
        "usage: reference|fast count [output-precision=52] [work-precision=160]"

end SparkInterval.Tests.CertifiedRootBenchmark

def main (arguments : List String) : IO Unit :=
  SparkInterval.Tests.CertifiedRootBenchmark.runMain arguments
