# Factored small-q raw-trace Lean bridge

Copyright (c) 2026 Gershon Bialer. All rights reserved.  SPDX-License-Identifier: MIT.

`SparkInterval/Dirichlet/FactoredSmallQRawTrace.lean` is the fail-closed
wire-to-arithmetic boundary for one bounded Gaussian recurrence trace.

The raw certificate stores every complex-disk centre, radius, centre-error
bound, and centre-norm bound as a binary64 bit word. Lean decodes each finite
word to its exact rational value; words outside 64 bits, infinities, and NaNs
decode to `none`. The decoded trace is then passed to the typed
exact-rational checker, which rechecks:

- nonnegative radii and auxiliary bounds;
- squared centre-error and centre-norm inequalities;
- the complete disk-product radius inequality;
- the shared `w^2` and initial `w^3` products;
- both products in every recurrence row;
- every raw-to-typed state link; and
- an explicit caller-supplied maximum row count.

The Lean structure starts with already-selected `Nat` words. It does not
parse a little-endian byte stream. Also, positive and negative binary64 zero
both decode to rational zero. Any requirement to preserve or canonicalize a
signed-zero bit pattern therefore belongs to the preceding byte-frame parser
and artifact-binding layer.

For a nonempty truncation containing `T` Gaussian terms,
`checkForTermCount maxSteps T` additionally requires exactly `T - 1`
recurrence updates. It rejects `T = 0`, because this certificate shape always
contains the initial term. Successful decoding is proved to preserve the raw
row count exactly.

The main application theorem is
`RawTraceCertificate.term_count_output_contains_exact_after_of_base_decode`.
Conditional only on the raw base disk decoding to a disk that contains `w`,
it proves that the final decoded disks contain
`ExactGaussianState.after w (T - 1)`. Thus the binary64 words are tied to the
same powers proved by the source-level recurrence theorem; no floating-point
operation is evaluated inside Lean.

## Trust and coverage boundary

These theorems use ordinary Lean reduction and proofs. They contain no
`native_decide`, project axiom, or `sorry`. Their printed dependencies are
only Lean/Mathlib foundations (`propext`, `Classical.choice`, and
`Quot.sound`).

This module does not yet establish any of the following:

- that the production byte-frame parser produced these Lean structures;
- that a CPU, CUDA, PTX, or SASS execution produced the accepted raw words;
- accumulation of all Gaussian terms into the finite sum;
- application of the character prefactor or the DFT/postprocessing stages;
- manifest coverage of every required conductor, character, frequency, and
  truncation; or
- closure of a ternary-Goldbach external atom.

Those edges must be composed separately. In particular, `maxSteps` is a
resource bound, while `checkForTermCount` binds the local trace to its claimed
nonempty truncation; neither substitutes for a full production coverage
manifest.

## Recheck

```bash
lake build SparkInterval.Dirichlet.FactoredSmallQRawTrace
lake env lean SparkInterval/Tests/FactoredSmallQRawTraceTest.lean
```

The focused test contains a two-row all-one fixture, a nontrivial `w = i`
fixture that checks the power recurrence, and fail-closed link-tamper,
nonfinite-word, row-bound, and empty-term-count cases.
