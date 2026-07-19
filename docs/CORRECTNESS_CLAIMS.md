# Correctness claims

SparkInterval separates mathematical soundness, modeled program execution,
testing evidence, and physical-run provenance. Evidence in one column does not
silently supply evidence in another.

## Support matrix

| Surface | Established claim | Evidence | Boundary |
| --- | --- | --- | --- |
| Abstract interval expressions | Every realized exact value is contained in the interval evaluator's result | Lean theorem [`evalInterval_sound`](../SparkInterval/EvalSound.lean#L84) | Exact-real model; no floating-point program |
| Directed binary64 interval arithmetic | Downward/upward rounding encloses the exact value, and interval add, subtract, and multiply contain their exact-real operations; division does too when the divisor interval excludes zero | Lean theorems in [`DirectedRounding.lean`](../SparkInterval/DirectedRounding.lean#L182) and [`FPIntervalSound.lean`](../SparkInterval/FPIntervalSound.lean#L71) | Value-level model; signed-zero encodings are not distinguished in the real interpretation |
| Full result certificate | Every checked claimed row contains every real value represented by its input row and expression; optional theorems give row-wise and finite-sum upper bounds | Lean checker and soundness theorems in [`Certificate/Full.lean`](../SparkInterval/Certificate/Full.lean#L122) | Checks the supplied complete witness; no claim about its producer |
| Generated polynomial module | One modeled in-range thread returns an observed row representing `evalKernel`; with corresponding real inputs, the row contains the realized exact value | [`runBuildModule_inRange`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L32) and [`runBuildModule_inRange_containsReal`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L314) | Typed AST and Lean machine only; polynomial operations only |
| Generated no-write path | Under the theorem's wrapped machine-word out-of-range premise, the modeled module returns with global memory unchanged | [`runBuildModule_outOfRange`](../SparkInterval/PTX/GeneratedKernelOutOfRangeRefinement.lean#L115) | Do not restate as an unconditional natural-index or physical-GPU theorem |
| CUDA and generated-cubin execution | Tested outputs and statuses are compared bit-for-bit with an exact rational Python oracle, with artifact audits and replay checks | Test and conformance tooling | Differential testing, not a Lean refinement theorem |
| Local run bundle | Canonical metadata and supplied artifact bytes are mutually hash-consistent | Run-bundle verifier | Host-forgeable; no execution authority |
| DGX operator signature | A separately pinned Ed25519 key signed the exact artifact-verified local record, with replay checking | Signature and run-bundle verifier | Operator provenance only; always `hardware_evidence: false` |
| H100 offline artifacts | `compute_90` PTX and `sm_90` cubins can be built and statically inspected without an H100 | Offline build and audit scripts | No H100 query, execution, result, or attestation |
| H100 hardware provenance | No accepted instance or positive evidence importer exists | Fail-closed policy and explicit future trust axiom | Not operational in this repository |
| Real-integer zeta tutorial | Exact host recomputation plus an integral-test tail encloses `zeta(s)` for a recorded supported integer `s > 1` | CUDA tutorial verifier and hash-bound [algorithm](algorithms/REAL_ZETA_POC.md) | Positive real values only; not a Lean theorem about `riemannZeta` or zeros |

Merkle and application-specific compressed Lean result certificates are not
implemented. The finite-sum theorem still checks the complete full certificate;
it is an aggregate conclusion, not a compressed witness.

## Full result certificates

[`FullCertificate.check_sound`](../SparkInterval/Certificate/Full.lean#L122)
proves containment for arbitrary real selections from every input and constant
interval, not merely for rational samples. The same checker supports the
row-bound theorem
[`checkUpperBound_sound`](../SparkInterval/Certificate/Full.lean#L191) and the
finite aggregate theorem
[`checkSumUpperBound_sound`](../SparkInterval/Certificate/Full.lean#L286).

The serialized parser enforces canonical JSON, exact fields and limits,
binary64 spelling, row relationships, and nested SHA-256 bindings. Generic
serialized implications are
[`impliesTheorem`](../SparkInterval/Certificate/Format.lean#L367) and
[`impliesSumTheorem`](../SparkInterval/Certificate/Format.lean#L377).

Concrete generated proofs have two dependency profiles:

- default `kernel` mode uses `decide_cbv` for the materialized typed-data
  checks, while the exact serialized parser/hash equality uses `native_decide`;
- explicit `native` mode also uses `native_decide` for the typed-data checks.

Thus the default direct typed-data theorem can be used without
`native_decide`, but the current generated theorem that binds the witness to
the exact JSON bytes cannot. This is a proof-reduction distinction, not GPU
execution evidence. See [Verifier guide](VERIFYING.md#native_decide-distinction)
and [Trust model](TRUST_MODEL.md#lean-proof-dependencies).

The Python reference checker uses the same canonical wire format but, by
itself, produces external recomputation evidence rather than a Lean theorem.
The Python generator prechecks a certificate before producing Lean source;
the mathematical conclusion comes from the Lean checker, not that precheck.

## Generated typed-machine theorem

The generated compiler accepts polynomial expressions built from constants,
variables, negation, addition, subtraction, multiplication, and natural powers.
Lean proves:

- status-aware `PolynomialExpr.evalKernel` containment;
- exact structural lowering and exact source-derived opcode order;
- recursive execution of the actual `compileExpr` output;
- exact generated prologue, expression, normal-output,
  conservative-whole-output, and return segments;
- input/output layout properties and the public output-row representation;
- a complete one-thread `Machine.run` result for the modeled module.

`runBuildModule_inRange` requires its stated safe-thread, safe-layout,
encoded-memory, selected-row, environment, and successful-evaluation
hypotheses. Its uniform fuel is the compiled expression instruction count plus
47. `runBuildModule_inRange_containsReal` additionally requires corresponding
real and interval environments and a source-expression realization.

The conclusion stops at the typed AST and Lean machine. Deterministic emission
shows that successful emission is the rendering of the same AST, but there is
no operational parser/refinement theorem from emitted PTX text back to that
machine. There is also no proof that `ptxas`, SASS, the CUDA driver, scheduling,
or physical hardware implements the model. The division-capable CUDA
expression frontend is outside this theorem.

## Execution provenance

An unsigned DGX bundle establishes only reproducibility and integrity relative
to supplied bytes. A detached operator signature authenticates an endorsement,
not the truth of the endorsed record. Treating it as a physical-run fact
requires the explicit
[`dgx_operator_signed_run_sound`](../SparkInterval/Execution/Trusted/DGXOperatorSignature.lean#L24)
axiom, and the JSON-to-private-Lean-capability importer is not implemented.

The intended H100 bridge is the separate
[`h100_attested_run_sound`](../SparkInterval/Execution/Trusted/H100Attestation.lean#L27)
axiom. No genuine H100 evidence currently reaches its premise. Even if it did,
the conclusion `AlgorithmReturned` would record provenance only. An
application must separately identify the algorithm, parse the result, and use
an algorithm-soundness theorem.

## Riemann-zeta scope

The included tutorial encloses positive real values from the Dirichlet series
for supported integer `s > 1`. It uses a division-capable CUDA runner and an
exact Python verifier, so it is neither an instance of the polynomial
typed-machine theorem nor a Lean connection to Mathlib's `riemannZeta`.

No current theorem verifies critical-strip values or zeros to a stated height.
That application still requires complex interval arithmetic, certified
transcendental functions and argument reduction, adaptive precision,
zero-isolation logic, a complete coverage/counting theorem such as an
appropriate Turing-method layer, and a final Lean theorem connecting the
checked certificate to those analytic results.
