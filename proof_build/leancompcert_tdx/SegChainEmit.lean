/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

Emission driver for ONE window of a chained `Ports.ArraySegSieve` campaign,
with a **self-checking freestanding** driver.

Run it from a leancompcert checkout, which stays read-only:

```
cd ~/leancompcert
lake env lean --run \
  <gpu_prover>/proof_build/leancompcert_tdx/SegChainEmit.lean \
  MODE LO SEGLEN SEGCOUNT SEED EXPECT_T EXPECT_TMAX EXPECT_TMIN OUT
```

## Why this file exists rather than `bench/ArraySegEmit.lean`

`bench/ArraySegEmit.lean` emits two drivers: a *hosted* one that `printf`s the
result cells, and a *freestanding* one that compares only the violation count
against a literal.  Neither is usable for an attested chained campaign:

* the hosted driver needs libc, so it is not freestanding, and it communicates
  through stdout, which an attested campaign would then have to parse;
* the freestanding driver checks the violation count but **not the window's
  carry-out**, so a window seeded with the wrong carry-in still exits 0.  In a
  chain that is the whole ballgame: window `k+1`'s carry-in is window `k`'s
  carry-out, and if nothing checks it, the chain proves nothing about the
  range it claims to cover.

The driver emitted here returns 0 exactly when **all four** of the window's
observable outputs match the values recorded in the campaign manifest: the
violation count (which must be 0) and the three result slots
`rT`, `rTmax`, `rTmin`.  Chain integrity is then a purely textual property of
the manifest — window `k+1`'s `SEED` equals window `k`'s `EXPECT_T` — which a
reviewer, the entry point, and Lean can each check without running anything.

The contract of `runtime/start/x86_64.S` applies: no libc, no stdio, the
process exit status is the low 8 bits of `main`'s return, and **any** status
other than 0 or 1 is abnormal termination and must never be read as a verdict.
-/

import LeanCompCert.Ports.ArraySegSieve

open LeanCompCert
open LeanCompCert.Verified.ArrayState
open LeanCompCert.Ports.ArraySegSieve

namespace TG.SegChainEmit

/-- The self-checking freestanding driver.

No `#include`, no libc call, no output stream.  `main` takes no arguments and
returns 0 or 1, which is exactly what the freestanding `_start` stub requires.
-/
def selfCheckDriver (name : String) (cells : Nat)
    (expViol expT expTmax expTmin : Nat) : String :=
  let slot (i : Nat) : String := s!"cells[{cells} - 8 + {i}]"
  "\nstatic uint64_t cells[" ++ toString cells ++ "];\n" ++
  "int main(void)\n{\n" ++
  "    uint64_t r = l_" ++ name ++ "((uint64_t)(uintptr_t)cells);\n" ++
  "    if (r != UINT64_C(" ++ toString expViol ++ ")) return 1;\n" ++
  "    if (" ++ slot 0 ++ " != UINT64_C(" ++ toString expT ++ ")) return 1;\n" ++
  "    if (" ++ slot 1 ++ " != UINT64_C(" ++ toString expTmax ++ ")) return 1;\n" ++
  "    if (" ++ slot 2 ++ " != UINT64_C(" ++ toString expTmin ++ ")) return 1;\n" ++
  "    return 0;\n}\n"

/-- The hosted driver, used only on the reviewed build host to *discover* the
carry-out of each window.  It is never packaged into a campaign image. -/
def hostedDriver (name : String) (cells : Nat) : String :=
  "\n#include <stdio.h>\n" ++
  "static uint64_t cells[" ++ toString cells ++ "];\n" ++
  "int main(void)\n{\n" ++
  "    uint64_t r = l_" ++ name ++ "((uint64_t)(uintptr_t)cells);\n" ++
  "    printf(\"violations %llu\\n\", (unsigned long long)r);\n" ++
  "    for (int i = 0; i < 3; i++)\n" ++
  "        printf(\"slot%d %llu\\n\", i,\n" ++
  "               (unsigned long long)cells[" ++ toString cells ++ " - 8 + i]);\n" ++
  "    return 0;\n}\n"

end TG.SegChainEmit

open TG.SegChainEmit in
def main (args : List String) : IO UInt32 := do
  match args with
  | mode :: loS :: lenS :: cntS :: seedS :: rest => do
      let some lo := loS.toNat? | do IO.eprintln "bad LO"; return 1
      let some len := lenS.toNat? | do IO.eprintln "bad SEGLEN"; return 1
      let some cnt := cntS.toNat? | do IO.eprintln "bad SEGCOUNT"; return 1
      let some seed := seedS.toNat? | do IO.eprintln "bad SEED"; return 1
      let c := Cfg.ofRange lo len cnt
      let name := s!"Seg{mode}L{lo}S{len}N{cnt}"
      let thr ←
        match mode with
        | "platt211" => pure (platt211Threshold c.hi)
        | "plattstrong" => pure (plattStrongerThreshold c.hi)
        | _ => do
            IO.eprintln "bad MODE (expected platt211 or plattstrong)"
            return 1
      let p := mobiusProgram c seed thr
      -- rest is either [OUT] (hosted discovery) or
      -- [EXPECT_T, EXPECT_TMAX, EXPECT_TMIN, OUT] (packaged, self-checking).
      let (driver, out) ←
        match rest with
        | [out] => pure (hostedDriver name p.arrayLen, out)
        | [eV, eT, eMax, eMin, out] =>
            match eV.toNat?, eT.toNat?, eMax.toNat?, eMin.toNat? with
            | some v, some a, some b, some d =>
                pure (selfCheckDriver name p.arrayLen v a b d, out)
            | _, _, _, _ => do IO.eprintln "bad EXPECT_*"; return 1
        | _ => do
            IO.eprintln
              "usage: MODE LO SEGLEN SEGCOUNT SEED [EVIOL ET EMAX EMIN] OUT"
            return 1
      match p.emitRolled name with
      | .error errs => (for e in errs do IO.eprintln e); return 1
      | .ok src =>
          IO.FS.writeFile out (src ++ driver)
          -- One machine-readable line; the campaign builder parses it.
          let line1 := s!"emit mode={mode} lo={lo} hi={c.hi} segLen={len}"
          let line2 := s!" segCount={cnt} arrayLen={p.arrayLen}"
          let line3 := s!" loopCount={p.loopCount} memoryBytes={8 * p.arrayLen}"
          let line4 := s!" threshold={thr} tBias={tBias}"
          IO.println (line1 ++ line2 ++ line3 ++ line4)
          return 0
  | _ => do
      IO.eprintln "usage: MODE LO SEGLEN SEGCOUNT SEED [EVIOL ET EMAX EMIN] OUT"
      return 1
