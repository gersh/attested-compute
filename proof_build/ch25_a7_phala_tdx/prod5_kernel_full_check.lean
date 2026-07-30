/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxProd5Evidence

/-!
# The whole prod5 acceptance check, reduced by the Lean kernel

This file is **not** part of any `lean_lib` and is not built by `lake build`.
It exists so that the one claim `SparkInterval/Tests/PhalaTdxProd5RunTest.lean`
cannot afford to make inside the repository build is nevertheless reproducible
on demand.

That module closes `phalaTdxOutcomeCheck ... = true` with `native_decide`,
because the check performs nineteen SHA-256 evaluations over strings before it
reaches the curve arithmetic, and reducing those in the kernel needs far more
memory than the repository's `weakLeanArgs = ["-j1", "-M8192"]` ceiling
allows.  Here the same statement is closed by `decide +kernel`, with no
`native_decide` anywhere, so the trust surface is the base trio alone.

Run it with an explicit memory budget:

```
lake env lean -j1 -M110000 \
  proof_build/ch25_a7_phala_tdx/prod5_kernel_full_check.lean
```

## Why only two declarations

Lean does not return the kernel's working memory to the allocator between
declarations, so cost accumulates within one file.  Measured on a 20-core
x86-64 host with 119 GB of RAM, Lean 4.32.0, each of these costs, on its own,
above a 4.7 GB import baseline:

| statement                                     | wall    | peak resident |
|-----------------------------------------------|---------|---------------|
| `receipt.statementDigest = <literal>`          | ~126 s  | ~34 GB        |
| altered-key refusal (report data only)         | ~20 s   | ~9 GB         |
| `P256.verifyDigestHex` (already in the build)  | ~4 s    | ~1.1 GB       |
| **this file, both declarations, end to end**   | 1209 s  | **42.9 GB**   |

The last row is a real, completed run: `EXIT=0`, and both `#print axioms`
reported `[propext, Classical.choice, Quot.sound]` and nothing else.  Budget at
least 43 GB of *genuinely free* physical memory, not merely a large `-M`: that
1209 s was measured on a host where about 19 GB was tied up by an unrelated
process, so the reduction spent most of its time in swap at roughly 25% CPU.
With the memory actually free, expect a small multiple of the 126 s row rather
than twenty minutes.

`prod5Outcome_kernel` subsumes the statement-digest reduction -- the check
recomputes the digest itself -- so stating both would pay for it twice, which
is why the first row is not a declaration here.  The two outcome-level
refusals that would also need a full digest reduction (altered signature,
altered `issuedAt`) are deliberately *not* here either: each would add another
~35 GB, and each already has a kernel-checked counterpart at the P-256 level
in the committed test module.  Add them only on a machine with the memory to
spare, and expect to run them one file at a time.

If this file stops closing, the receipt pinned in
`SparkInterval/Execution/PhalaTdxProd5Evidence.lean` no longer satisfies the
acceptance check by kernel reduction, and the `native_decide` result in the
test module should not be believed either.
-/

set_option autoImplicit false
set_option maxRecDepth 200000
set_option maxHeartbeats 10000000

open SparkInterval.Execution

/-- The one-character-altered pinned key, refused by kernel reduction of the
whole check rather than of the P-256 primitive alone.  Stated first because it
is the cheap one: it fails at the quote's report-data commitment, which is a
digest *of the pinned key*, before the statement digest is ever built.

Axioms: the base trio. -/
theorem prod5Outcome_rejectsAlteredKey_kernel :
    phalaTdxOutcomeCheck .ch25A7BoundaryPhalaProd5TamperedKeyV1
      .ch25A7BoundaryProductionV1 PhalaTdxProd5.receipt = false := by
  decide +kernel

/-- **The complete fail-closed acceptance check, reduced entirely by the Lean
kernel** on the receipt a genuine Intel TDX enclave signed: no `native_decide`,
no compiled evaluator.  This reduces the canonical eighteen-field payload, its
SHA-256, the report-data commitment, and the ECDSA P-256 verification.

Axioms: the base trio. -/
theorem prod5Outcome_kernel :
    phalaTdxOutcomeCheck .ch25A7BoundaryPhalaProd5V1
      .ch25A7BoundaryProductionV1 PhalaTdxProd5.receipt = true := by
  decide +kernel

#print axioms prod5Outcome_rejectsAlteredKey_kernel
#print axioms prod5Outcome_kernel
