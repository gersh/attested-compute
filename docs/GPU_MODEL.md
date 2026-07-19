# GPU model and platform profiles

The execution model assigns one independent interval-expression row to one
CUDA thread.  Version 1 excludes shared memory, warp communication, atomics,
reductions, dynamic parallelism, cooperative groups, and Tensor Cores.  Rows
are therefore logically independent and the planned formal machine model can
remain thread-local.

## Current DGX Spark paths

- Host architecture: `aarch64`
- Device: NVIDIA GB10
- CUDA compute capability: 12.1
- Compilation target: `sm_121`
- Execution evidence: local and unattested

The primitive batch consumes raw binary64 words and executes one of add,
subtract, multiply, or divide with explicit downward/upward CUDA intrinsics.
The expression prototype consumes strict little-endian postfix bytecode with
at most 256 instructions, 64 variables, 32 stack entries, and a natural-power
exponent of at most 64.  It supports constants, variables, negation,
add/subtract/multiply/divide, absolute value, minimum, maximum, and natural
powers.

Both runners validate the complete input before CUDA initialization, enforce
the expected device unless an explicit development override is supplied,
check every CUDA call, initialize output sentinels, and validate the complete
output.  Division by a zero-containing interval and arithmetic that must widen
because it consumes a nonfinite intermediate have distinct per-row statuses;
applications must require status zero for every row they use.

The CUDA paths are compared bit-for-bit with exact Python rational arithmetic.
They are not formally refined to Lean.  Python/CUDA preserve signed-zero bits;
the current value-level Lean endpoint model identifies the two zero encodings.

Compiler-emitted PTX is checked with an expression-specific directed-operation
audit and SASS is conservatively inspected for fused, approximate, tensor,
atomic, and synchronization instructions.  These are lexical audits, not a
proof of PTX-to-SASS equivalence.

## Restricted generated PTX

Phase 5 introduces a typed Lean PTX AST with no arbitrary-instruction escape
hatch, a deterministic `sm_121` emitter, a structural validator, and an
independent post-emission allowlist audit.  The first vertical slice compiles a
polynomial subset of the canonical expression language; unsupported operations
fail closed. Its native 100,000-row suite matched exact Python and the Phase 4
CUDA payload, including explicit widening status; deterministic PTX/output
replay, a separate signed-zero corner suite, and generated-cubin SASS audit all
passed. The accepted path audits PTX, uses offline `ptxas`, audits the resulting
cubin's SASS, and executes that exact cubin rather than a separately JIT-compiled
PTX module. The specialized audit accepts six source-independent `HFMA2`
constant-forming idioms emitted by `ptxas`; the generic diagnostic flags those
mnemonics because it cannot establish that narrower pattern. This is still a
tested generated prototype, not a verified kernel: the language slice is
incomplete, and Phase 6 currently supplies operational semantics and enclosure
theorems only for the canonical pure add/sub/mul fragments—not control flow,
memory, indexing, threads, emitted text, or the whole kernel.

The public AST validator proves only syntactic typing, register bounds, labels,
and allowlist membership. It is not a general CFG, dataflow, initialization, or
memory-safety checker for arbitrary hand-constructed `PTX.Module` values. The
accepted path is the private expression compiler plus its concrete audits and
differential tests.

## Real-zeta POC backend

The tutorial real-integer zeta calculation uses the native Phase 4 postfix
expression runner, because its fixed term expression `1 / n^s` requires
division and the Phase 5 generated-PTX subset does not yet implement division.
One GPU thread evaluates each positive point input `n`; the host verifier
exactly recomputes every output row, performs the outward interval reduction,
and supplies the integral-test tail. It also re-runs the expression PTX and
SASS audits over the staged artifacts. This is tested CUDA/backend execution,
not an extension of the partial Phase 6 generated-PTX proof.

## H100

- Typical host architecture: `x86_64`
- Device target: Hopper H100
- CUDA compute capability: 9.0
- Compilation target: `sm_90`
- Execution evidence: offline/mock only in this repository

The diagnostic and primitive interval-batch device programs have real
`compute_90` PTX and `sm_90` cubin/SASS offline builds.  Producing those files
on DGX Spark proves only that the toolchain accepted them; no H100 was queried,
no kernel was executed, and no result or attestation was obtained.  The H100
expression/generator path remains pending.

## Formal boundary

The planned formal model covers only the typed generated PTX subset—not
arbitrary CUDA C++, arbitrary PTX, SASS, scheduling, or the CUDA toolchain.
Phase 6 now has instruction/state semantics and enclosure theorems for the
generator's pure add/subtract/multiply fragments. It still needs arbitrary
register renaming, guards, control flow, memory/indexing, threads, text
refinement, and batch semantics plus `generatedKernel_sound`. Physical
execution remains outside the
mathematical proof boundary unless a complete result certificate is
independently checked in Lean or provenance is imported through the explicit
H100 hardware-attestation axiom or the separate explicit DGX operator-trust
axiom.
