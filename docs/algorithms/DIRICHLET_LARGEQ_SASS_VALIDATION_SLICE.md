# Fused large-q SM90 post-compilation validation slice

This is the first semantic post-compilation slice for the fused large-`q`
Dirichlet kernel. It validates one actual arithmetic path in the production
`reconstructComposeKernel`: the imaginary-component addition of the certified
finite-recovery rectangle immediately before the result is stored.

It is deliberately a bounded result, not a claim that the complete kernel or
an H100 has been formalized.

## Exact audited site

The source chain is:

```text
h100_tg_dirichlet_largeq_batch.cu:54   directed real-interval add
  inlined at line 88                   complex rectangle add
  inlined at line 158                  final finite-recovery addback
```

CUDA 13.0.88 compiled the imaginary endpoint pair to these consecutive SM90
instructions:

```text
/*3840*/ DADD.RM R12, R12, R22 ;
/*3850*/ DADD.RP R10, R10, R20 ;
```

The restricted IR interprets `R12/R10` as the lower/upper endpoints of the
left and result interval, and `R22/R20` as the lower/upper endpoints of the
finite-recovery interval. The validator checks destinations, both sources,
rounding modes, order, lack of predication or operand modifiers, and the
anti-aliasing conditions needed for the in-place update. This is materially
stronger than checking that the cubin contains one `.RM` and one `.RP` opcode.

## Lean theorem

[`SparkInterval/SASS/SM90DirectedAdd.lean`](../../SparkInterval/SASS/SM90DirectedAdd.lean)
defines the restricted instruction semantics and proves:

```lean
SparkInterval.SASS.SM90.AddSlice.check_refinesIntervalAdd
```

For every checked slice and every two finite input intervals, executing the
decoded pair in the restricted model produces the usual outward binary64
interval sum. The existing interval theorem then shows that this result
contains `x + y` for every `x` and `y` selected from the input intervals.

[`SparkInterval/SASS/FusedLargeQAddbackSlice.lean`](../../SparkInterval/SASS/FusedLargeQAddbackSlice.lean)
instantiates that theorem for the exact pair above:

```lean
SparkInterval.SASS.SM90.fusedLargeQFinalImaginaryAddback_refinesIntervalAdd
```

The application-shaped theorem
`fusedLargeQFinalImaginaryAddback_contains` names the live registers
`R12/R10` and `R22/R20` explicitly and concludes that restricted execution
produces an interval containing the exact imaginary addback.

The checked artifact record binds:

| Artifact | SHA-256 |
|---|---|
| CUDA source file | `8897947a2538b71af7412716154239de189580fe610b461f067f619eb70db09a` |
| SM90 cubin | `f45527356e60d6739f3d02ad57a06d490ae4577d694508951ab1b19f99228e16` |
| Plain `nvdisasm --print-code` output | `31790c41c183807107c70af793f30f1cc65573bc8eb38907a6fa5bd48052adb7` |
| Line-info disassembly | `d9d82f5e3820d02051c3b5e6c4b69175d29fb06362bdc1161b2dc92f2c4aff0b` |

These are a reproducible local CUDA 13.0 artifact instance, not a production
run receipt. A source or toolchain change is expected to require a newly
reviewed certificate.

## Reproduce the certificate

No binary build product is checked into the repository. Recreate the artifact
and its two disassemblies with:

```bash
nvcc -std=c++20 -O3 -lineinfo -arch=sm_90 \
  --fmad=false --ftz=false --prec-div=true --prec-sqrt=true \
  -I gpu/include --cubin \
  gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu \
  -o /tmp/h100_tg_dirichlet_largeq_batch.sm_90.cubin

nvdisasm --print-code \
  /tmp/h100_tg_dirichlet_largeq_batch.sm_90.cubin \
  > /tmp/h100_tg_dirichlet_largeq_batch.sm_90.sass

nvdisasm --print-code --print-line-info-inline \
  /tmp/h100_tg_dirichlet_largeq_batch.sm_90.cubin \
  > /tmp/h100_tg_dirichlet_largeq_batch.sm_90.line.sass

python3 tools/audit_tg_dirichlet_largeq_sass_slice.py \
  /tmp/h100_tg_dirichlet_largeq_batch.sm_90.cubin \
  /tmp/h100_tg_dirichlet_largeq_batch.sm_90.sass \
  /tmp/h100_tg_dirichlet_largeq_batch.sm_90.line.sass \
  gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu \
  /tmp/largeq-sass-slice.json
```

The Python extractor requires one uniquely attributed adjacent pair, checks
that the plain and line-info disassemblies agree on every decoded operand, and
emits the compact restricted IR. It fails if an operand, rounding mode,
source-attribution line, function, target, or ELF identity is changed. Lean
then independently checks the restricted dataflow and proves the arithmetic
theorem.

Run the focused tests with:

```bash
python3 -m unittest tests.test_tg_dirichlet_largeq_sass_slice -v
lake build SparkInterval.SASS.FusedLargeQAddbackSlice \
  SparkInterval.Tests.FusedLargeQAddbackSliceTest
```

## Certificate composition and exact trust boundary

The reusable Boolean

```lean
SignedResultCertificate.outcomeCheckForRegisteredInvocationAndFusedLargeQSlice
```

combines three checks:

1. the existing closed registered invocation and physical run certificate;
2. the Lean restricted-IR validator; and
3. equality between the run statement's H100 cubin/manifest hashes and this
   slice certificate.

Its soundness theorem returns those three facts separately. It does not turn
the arithmetic slice into a whole-kernel theorem. There is currently no
registered fused-large-`q` invocation, so no production large-`q` receipt can
yet instantiate this composition.

Fresh `#print axioms` results are:

| Theorem | Nonlogical project axioms |
|---|---|
| `AddSlice.check_refinesIntervalAdd` | none |
| `fusedLargeQFinalImaginaryAddbackCertificate_check` | none |
| `fusedLargeQFinalImaginaryAddback_refinesIntervalAdd` | none |
| `fusedLargeQFinalImaginaryAddback_contains` | none |
| registered outcome plus slice composition | `accepted_run_certificate_sound` only |

Lean also reports its standard `propext`, `Classical.choice`, and `Quot.sound`
dependencies for these real-number and string definitions.

### Relation to the base-trio complex-disk certificate

[`SparkInterval/Certified/ComplexDisk.lean`](../../SparkInterval/Certified/ComplexDisk.lean)
provides the complementary arithmetic-value edge: it decodes raw binary64
words to exact rationals, checks a `MulCertificate` with a Boolean rational
checker, and proves `output_contains_mul` in base-trio Lean. This SASS slice is
the artifact-shape edge for one rectangle addition. Neither theorem currently
supplies the missing bridge that establishes the production kernel's live
register provenance from those decoded wire values, and the two must not be
presented as a whole-kernel composition until that bridge is proved.

## Unsupported gaps retained explicitly

This slice does **not** prove any of the following:

- correctness of `nvcc`, `ptxas`, `nvdisasm`, or the mapping from cubin bytes
  to the decoded restricted IR;
- an authoritative NVIDIA SASS semantics for `DADD.RM` and `DADD.RP`;
- reachability of offsets `0x3840/0x3850` or provenance of their live register
  values from the input arrays;
- correctness of the surrounding interval multiply, directed division,
  Taylor loop, tail inflation, control flow, global-memory stores, or any other
  instruction in `reconstructComposeKernel`;
- CUDA driver, SM90 scheduling, memory-model, or physical H100 conformance;
- source-wide interval usefulness, certified-input generation, zero isolation,
  Turing counting, Platt's Theorem 7.1, or Ternary Goldbach.

The next useful slices are the four-corner interval multiply feeding this
addback, the two output stores and their address calculation, and a bounded
straight-line Taylor recurrence iteration. Each needs operand-level
translation and a Lean theorem; widening this result by opcode counts alone
would not close those gaps.
