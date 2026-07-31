/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

Emission driver for ONE link of a chained **per-integer** `Σ μ(m)/m`
campaign, with a **self-checking freestanding** driver.

Run it from a leancompcert checkout, which stays read-only:

```
cd ~/leancompcert
lake env lean --run \
  <gpu_prover>/proof_build/leancompcert_tdx/LiveChainEmit.lean \
  LO SEGLEN SEGCOUNT SEEDLO SEEDHI \
  [EVIOL ETLO ETHI EC ECSQ] OUT
```

## Why this file exists rather than `SegChainEmit.lean`

`SegChainEmit.lean` emits `Ports.ArraySegSieve.mobiusProgram`, whose window is
tested **once**, in the epilogue, against the majorant at the window's worst
endpoint.  Covering a range that way costs a window schedule, and the schedule
has to stop on a window boundary the whole window survives: the committed
`platt-stronger-range` campaign therefore stops at 7 727 065 383, which is
3 204 integers short of what the reduced family claims.

`Ports.ArraySegSieve.mobiusLiveProgram` tests
`|Σ_{m≤n} μ(m)/m| ≤ 1/(2√(n+1))` at **every integer** `n`, against
`⌊2^(63+k)/⌈√(n+1)⌉⌋` with the accumulator carried in two limbs at scale
`2^(63+k)`, `k = mobWideBits = 15`.  Two things follow, and both are the
reason this emitter exists:

* a window is a unit of *memory* and nothing else, so no schedule tightening
  is given away and the cover can stop exactly at the range's endpoint; and
* the accumulated round-to-nearest budget falls from `⌈n/2⌉` at scale `2^62`
  to `⌈n/2^17⌉ + 1` at scale `2^78` -- 65 536 times smaller -- which is what
  carries the last 3 204 integers.

## What the driver checks

`SegChainEmit.lean`'s driver checks the violation count and three result
slots.  This program has **four** result slots -- the two accumulator limbs,
`⌈√(hi+1)⌉` and its square -- and all four are checked, together with the
violation count.  A link seeded with the wrong carry-in still reports zero
violations (a wrong accumulator can perfectly well stay under the threshold),
so checking only the count would prove nothing about a chain.

Chain integrity is then a purely textual property of the campaign manifest:
link `k+1`'s seed equals link `k`'s carry-out, where both are carried as the
single integer `tLo + 2^64 · tHi`.

The contract of `runtime/start/x86_64.S` applies: no libc, no stdio, the
process exit status is the low 8 bits of `main`'s return, and **any** status
other than 0 or 1 is abnormal termination and must never be read as a verdict.
-/

import LeanCompCert.Ports.ArraySegSieve

open LeanCompCert
open LeanCompCert.Verified.ArrayState
open LeanCompCert.Ports.ArraySegSieve

namespace TG.LiveChainEmit

/-- The self-checking freestanding driver.

No `#include`, no libc call, no output stream.  `main` takes no arguments and
returns 0 or 1, which is exactly what the freestanding `_start` stub requires.
-/
def selfCheckDriver (name : String) (cells : Nat)
    (expViol expTLo expTHi expC expCSq : Nat) : String :=
  let slot (i : Nat) : String := s!"cells[{cells} - 8 + {i}]"
  let check (lhs : String) (v : Nat) : String :=
    "    if (" ++ lhs ++ " != UINT64_C(" ++ toString v ++ ")) return 1;\n"
  "\nstatic uint64_t cells[" ++ toString cells ++ "];\n" ++
  "int main(void)\n{\n" ++
  "    uint64_t r = l_" ++ name ++ "((uint64_t)(uintptr_t)cells);\n" ++
  check "r" expViol ++
  check (slot 0) expTLo ++ check (slot 1) expTHi ++
  check (slot 2) expC ++ check (slot 3) expCSq ++
  "    return 0;\n}\n"

/-- The hosted driver, used only on the reviewed build host to *discover* the
carry-out of each link.  It is never packaged into a campaign image. -/
def hostedDriver (name : String) (cells : Nat) : String :=
  "\n#include <stdio.h>\n" ++
  "static uint64_t cells[" ++ toString cells ++ "];\n" ++
  "int main(void)\n{\n" ++
  "    uint64_t r = l_" ++ name ++ "((uint64_t)(uintptr_t)cells);\n" ++
  "    printf(\"violations %llu\\n\", (unsigned long long)r);\n" ++
  "    for (int i = 0; i < 4; i++)\n" ++
  "        printf(\"slot%d %llu\\n\", i,\n" ++
  "               (unsigned long long)cells[" ++ toString cells ++ " - 8 + i]);\n" ++
  "    return 0;\n}\n"

end TG.LiveChainEmit

open TG.LiveChainEmit in
def main (args : List String) : IO UInt32 := do
  match args with
  | loS :: lenS :: cntS :: seedLoS :: seedHiS :: rest => do
      let some lo := loS.toNat? | do IO.eprintln "bad LO"; return 1
      let some len := lenS.toNat? | do IO.eprintln "bad SEGLEN"; return 1
      let some cnt := cntS.toNat? | do IO.eprintln "bad SEGCOUNT"; return 1
      let some seedLo := seedLoS.toNat? | do IO.eprintln "bad SEEDLO"; return 1
      let some seedHi := seedHiS.toNat? | do IO.eprintln "bad SEEDHI"; return 1
      let c := Cfg.ofRange lo len cnt
      let k := mobWideBits
      let s := mobLiveSeed lo seedLo seedHi
      let name := s!"LiveL{lo}S{len}N{cnt}"
      let p := mobiusLiveProgram c k s
      -- rest is either [OUT] (hosted discovery) or
      -- [EVIOL, ETLO, ETHI, EC, ECSQ, OUT] (packaged, self-checking).
      let (driver, out) ←
        match rest with
        | [out] => pure (hostedDriver name p.arrayLen, out)
        | [eV, eTLo, eTHi, eC, eCSq, out] =>
            match eV.toNat?, eTLo.toNat?, eTHi.toNat?, eC.toNat?, eCSq.toNat? with
            | some v, some a, some b, some d, some e =>
                pure (selfCheckDriver name p.arrayLen v a b d e, out)
            | _, _, _, _, _ => do IO.eprintln "bad EXPECT_*"; return 1
        | _ => do
            IO.eprintln
              "usage: LO SEGLEN SEGCOUNT SEEDLO SEEDHI \
               [EVIOL ETLO ETHI EC ECSQ] OUT"
            return 1
      match p.emitRolled name with
      | .error errs => (for e in errs do IO.eprintln e); return 1
      | .ok src =>
          IO.FS.writeFile out (src ++ driver)
          -- One machine-readable line; the campaign builder parses it.
          let line1 := s!"emit mode=plattstronglive lo={lo} hi={c.hi}"
          let line2 := s!" segLen={len} segCount={cnt} arrayLen={p.arrayLen}"
          let line3 := s!" loopCount={p.loopCount} memoryBytes={8 * p.arrayLen}"
          let line4 := s!" wideBits={k} seedC={s.c} seedCSq={s.cSq}"
          IO.println (line1 ++ line2 ++ line3 ++ line4)
          return 0
  | _ => do
      IO.eprintln
        "usage: LO SEGLEN SEGCOUNT SEEDLO SEEDHI [EVIOL ETLO ETHI EC ECSQ] OUT"
      return 1
