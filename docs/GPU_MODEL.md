# GPU model and backend boundary

SparkInterval assigns one independent interval-expression row to one CUDA
thread. The supported design excludes shared memory, warp communication,
atomics, inter-thread reductions, dynamic parallelism, cooperative groups, and
Tensor Cores. Lean's generated-code machine models one thread at a time; CUDA
batch scheduling is external.

## Platform profiles

| Profile | Device code | Repository execution status | Evidence status |
| --- | --- | --- | --- |
| DGX Spark / GB10 | `sm_121` on `aarch64` | Native CUDA and restricted generated-cubin runners | `local_unattested`; optional operator signature is not hardware evidence |
| H100 | `sm_90`, normally on an `x86_64` host | Diagnostic and primitive device artifacts built offline; no H100 execution | Offline/mock only; production acceptance is fail-closed |

Target and trust profiles are independent. Selecting `sm_90` does not create
H100 confidential-computing evidence, and selecting `sm_121` never upgrades a
DGX bundle beyond local evidence.

## Modeled and external layers

| Layer | What is available | Status of the connection to the next layer |
| --- | --- | --- |
| Exact real and binary64 interval mathematics | Lean containment and directed-rounding theorems | Proved within Lean |
| Polynomial expression evaluator | Status-aware `PolynomialExpr.evalKernel` | Proved to contain corresponding exact-real values |
| Generated typed PTX AST | Exact compiler structure, opcode order, register/dataflow facts, and instruction execution | Proved for the compiler's generated polynomial subset |
| Pinned NVIDIA PTX 9.0 slice | Clause table for every allowlisted opcode; finite-operand directed `add/sub/mul` and non-NaN `min/max` transcription | Those arithmetic steps refine the transcription; clause coverage alone is not opcode semantics |
| Lean one-thread machine | Control flow, typed registers, word-size-aware addressing, global memory, thread specials, stores, and return | Whole generated module proved under explicit hypotheses |
| Emitted PTX text | Deterministic rendering of the same validated AST | No operational text parser/refinement back to the machine |
| `ptxas` cubin and SASS | Offline assembly plus conservative instruction audits | No proof that translation preserves the typed-machine semantics |
| CUDA driver and physical GPU | Native DGX tests and replay tooling | External implementation and hardware assumptions |

The PTX and SASS audits reject disallowed or suspicious instruction patterns
and the conformance runners compare output bits and statuses with exact
rational Python evaluation. These checks are valuable backend evidence, but
they do not turn any external row of the table into a Lean refinement theorem.

The closed registered-execution path is intentionally different from a proved
connection between adjacent rows of this table. `RegisteredAlgorithm` and
`RegisteredInvocation` fix formal semantics and canonical inputs in Lean. For
one accepted, exactly matching certificate, the sole
`accepted_run_certificate_sound` axiom supplies that invocation's `Runs`
relation; `accepted_registered_run_sound` is a derived projection. Thus the
particular-run physical-to-formal bridge is explicit trust, not a Lean proof of
general `ptxas`, SASS, driver, or hardware conformance. The registry contains
the exact-rational CPU tutorial, the one-row formal-PTX H100 pilot, and closed
source-shaped Ternary-Goldbach entries, including an exact conditional PT21
finite-RH slice and an exact conditional Platt Dirichlet Theorem 7.1 finalizer.
Those entries do not assert that source evidence or successful attested runs
exist.

That tutorial is nevertheless a complete algorithm-level example: its `Runs`
relation uses an executable integer `cubicNumeratorLoop` and divide-once
`cubicSumDivThreeMachine`. Lean proves the exact machine result, agreement with
the rational specification, and that every cube and accumulator step fits
u64. This axiom-free bounded-arithmetic layer does not connect the machine to
the generated PTX AST, emitted opcodes, or physical GPU; those are distinct
rows in the boundary above.

The H100 pilot covers a different, intentionally tiny path. Lean proves that
the registered PTX text is exactly the formal target-selected emitter's output
for a closed zero-variable batch returning `[1,1]`, and that the two returned
binary64 words decode to rational one. The per-run link from those fixed
semantics to physical H100 execution still crosses the same sole axiom.

The NVIDIA source layer pins the archived PTX ISA 9.0 PDF and cites the
rounding and instruction clauses used by the typed subset. Lean proves exact
agreement between its existing arithmetic model and the independent
transcription for finite operands of directed `add/sub/mul`, and for `min/max`
on the model's non-NaN numeric domain. It does not formalize the whole PTX ISA
or prove semantic refinement for every cited integer, address, memory,
conversion, predicate, control-flow, or special-register instruction. The
faithfulness of the prose-to-Lean transcription remains a review obligation.

## Generated polynomial theorem

The generated compiler accepts:

- interval constants and row variables;
- negation;
- addition and subtraction;
- multiplication;
- natural powers.

It does not accept division, absolute value, minimum, maximum, or the complete
CUDA expression language.

Lean proves the production `buildModule` equals an independently constructed
structural module down to metadata, register counts, typed operands,
immediates, offsets, labels, and branch targets. It also proves the exact
source-derived opcode trace and that successful emission is deterministic
rendering of the validated AST:

- [`StructuralCompilerCorrect.buildModule_eq_expectedModule`](../SparkInterval/PTX/StructuralCompilerCorrect.lean#L887);
- [`buildModule_opcodeTrace`](../SparkInterval/PTX/Generator.lean#L541);
- [`emit_success`](../SparkInterval/PTX/Emitter.lean#L233).

The operational proof composes the generated prologue, recursive expression
code, normal and conservative-whole output paths, public output layout, and
common return tail.

### In-range conclusion

[`runBuildModule_inRange`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L32)
requires:

- `Thread.Safe` and `SafeKernelLayout`;
- a natural in-range global row index;
- global memory satisfying `MemoryEncodesRows`;
- the selected encoded row equaling the stated interval environment; and
- `batch.expression.evalKernel environment = some result`.

Under those hypotheses, running the exact typed `buildModule` with its complete
body size as fuel returns a state whose public output row
`OutputRepresents` that result. The body size is exactly the expression's
compiled instruction count plus 47.

[`runBuildModule_inRange_containsReal`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L314)
adds pointwise correspondence between real and interval environments and a
`PolynomialExpr.Realizes` premise. Its observed interval then contains the
realized exact value.

This is a one-thread modeled theorem. It does not prove grid coverage,
cross-thread noninterference, CUDA scheduling, or physical execution.

### No-write return conclusion

[`runBuildModule_outOfRange`](../SparkInterval/PTX/GeneratedKernelOutOfRangeRefinement.lean#L115)
has the exact premise

```lean
parameters.read .rowCount ≤ thread.globalIndex
```

where both sides are the modeled wrapped machine-word values. Under that
premise, the modeled module returns with global memory unchanged. The theorem
must not be restated as an unconditional natural-number comparison or as proof
that an arbitrary physical GPU launch cannot write out of range.

## DGX CUDA backends

The primitive runner supports interval add, subtract, multiply, and divide
using explicit downward/upward CUDA operations. The postfix expression runner
supports constants, variables, negation, those four binary operations,
absolute value, minimum, maximum, and bounded natural powers.

The host validates the complete input before CUDA initialization, checks CUDA
operations and output coverage, and records explicit statuses. Division by an
interval containing zero and widening caused by a nonfinite intermediate are
not successful finite rows. Applications must validate the status of every row
they consume.

These CUDA frontends are different from the proved polynomial compiler. Their
bit-for-bit comparison against the exact Python oracle is testing evidence, not
a Lean theorem relating the CUDA program to `FPInterval` or `CertExpr`.
Python and CUDA retain signed-zero bits; the value-level Lean interpretation
identifies the two encodings as the same real value.

## Real-integer zeta backend

The [real-zeta tutorial](algorithms/REAL_ZETA_POC.md) uses the postfix CUDA
runner because its term expression `1 / n^s` requires division. One GPU thread
evaluates each positive point input. The host verifier reparses and exactly
recomputes every output, repeats an outward reduction, reruns artifact audits,
and adds an integral-test tail.

This is not an instance of the generated polynomial theorem. It encloses
positive real zeta values for supported integer arguments; it does not evaluate
the critical strip, isolate zeros, or prove height coverage.

## H100 offline boundary

The H100 scripts generate real `compute_90` PTX and `sm_90` cubin/SASS for a
diagnostic probe and primitive interval batch. A device artifact is portable
across host architectures, but a syntax check of the runner source on DGX
Spark does not create or validate an `x86_64` H100 host executable.

The offline workflows do not query H100 presence or attempt execution; their
manifests state that no result was returned and no production attestation
exists.
The typed polynomial emitter can now render the same validated module with an
`sm_90` directive. The dedicated formal-program checker proves the selected
emitted-PTX digest and target while also binding the parsed canonical input,
canonical input/parameter/domain hashes, target-profile hash, and artifact-hash
record. Those artifact fields are identities, not a proof that the named cubin
was compiled from the PTX. The repository still has no operational H100
expression/generated-polynomial run and acceptance path, no
PTX-to-cubin/hardware refinement, and no accepted H100 confidential-computing
evidence.

See [H100 setup and status](H100.md), [Trust model](TRUST_MODEL.md), and the
[Verifier guide](VERIFYING.md) before interpreting an artifact or run bundle.
