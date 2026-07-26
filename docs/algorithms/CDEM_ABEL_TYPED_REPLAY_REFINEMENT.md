# CDEM Abel typed replay refinement

Status: the pure algorithm-to-recurrence layer is proved. The reviewed C++
source, compiler, loader, and x86-64 refinement are still explicit open
obligations. No production scan was run to establish this layer.

## What is proved

[`CDEMAbelReplayAlgorithm.lean`](../../SparkInterval/TernaryGoldbach/CDEMAbelReplayAlgorithm.lean)
models the successful path of
[`tg_cdem_abel_chunk_replay.cpp`](../../reference/tg_cdem_abel_chunk_replay.cpp)
with unbounded Lean integers.

For an arbitrary chunk, `ReplayKernelData` contains the divisor-jump and
reciprocal-square-root tables constructed internally by the source program.
`ReplayKernelData.ValidFor` requires only the pointwise postconditions of
those construction phases:

```text
divisorJump(n) = floorJump(n)
weightScale^2 <= sqrtWeight(n)^2 * n.
```

`scanStep` then updates the incoming floor state, forms the consecutive local
error increment, and accumulates the signed and absolute directed integer
weights in the same serial order as the independent replayer. The universal
theorem

```text
locallyRealizes_of_accepts :
  Accepts request output ->
  (returnedChunk request output).LocallyRealizes
```

is proved by a prefix invariant for every number of events. It neither
evaluates the production endpoint nor names the generated 1,000-row
certificate.

The typed supervisor relation requires:

- the exact canonical input and result;
- ordinary `Certificate.check = true`;
- equality of the certificate numerators with the two production targets;
- typed replay acceptance for every certificate chunk.

`Supervisor.localEvidence_of_acceptance` constructs
`LocalSourceScaleEvidence` from those per-chunk proofs, and
`Supervisor.sourceClaim_of_acceptance` reaches the real CDEM source claim via
the existing recurrence theorem. The compact checker now delegates its
mathematical step to this operational supervisor relation; it no longer
places `LocalSourceScaleEvidence` directly in its own acceptance predicate.

## What remains open

The new module intentionally leaves two structures without inhabitants:

1. `CxxSourceRefinesTypedSupervisor` must prove, in a formal C/C++ semantics,
   that successful executions of the three reviewed sources implement the
   typed supervisor. Its proof must cover parsing, the Möbius sieve, the
   divisor-array fill, the exact square-root search, overflow guards, serial
   folds, output serialization, and the supervisor's all-chunk comparison.
2. `CompilerX86RefinesCxxSource` must connect the exact compiled static ELF,
   loader, ABI, and x86-64 instruction semantics to that source execution.

Source SHA-256 values are recorded in `reviewedSourceIdentity` for audit, but
hash strings do not prove either refinement. Attestation can supply the fact
that the exact architecture execution occurred; it cannot supply these
universal correctness theorems.

The focused test
[`CDEMAbelReplayAlgorithmTest.lean`](../../SparkInterval/Tests/CDEMAbelReplayAlgorithmTest.lean)
uses only a two-event symbolic fixture and audits the theorem dependencies.
The operational, supervisor, and native-composition theorems report only
Lean's standard foundational principles (`propext`, `Classical.choice`, and
`Quot.sound`).
