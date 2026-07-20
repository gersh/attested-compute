# Correctness claims

SparkInterval separates mathematical soundness, modeled program execution,
testing evidence, and physical-run provenance. Evidence in one column does not
silently supply evidence in another.

## Support matrix

| Surface | Established claim | Evidence | Boundary |
| --- | --- | --- | --- |
| Abstract interval expressions | Every realized exact value is contained in the interval evaluator's result | Lean theorem [`evalInterval_sound`](../SparkInterval/EvalSound.lean#L84) | Exact-real model; no floating-point program |
| Directed binary64 interval arithmetic | Downward/upward rounding encloses the exact value, and interval add, subtract, and multiply contain their exact-real operations; division does too when the divisor interval excludes zero | Lean theorems in [`DirectedRounding.lean`](../SparkInterval/DirectedRounding.lean#L182) and [`FPIntervalSound.lean`](../SparkInterval/FPIntervalSound.lean#L71) | Value-level model; signed-zero encodings are not distinguished in the real interpretation |
| NVIDIA PTX 9.0 formal slice | The existing finite-operand directed `add/sub/mul` and non-NaN `min/max` machine steps agree with a pinned Lean transcription; generated opcode traces have clause references | [`NvidiaPTXSpec.lean`](../SparkInterval/PTX/NvidiaPTXSpec.lean) and [`NvidiaPTXRefinement.lean`](../SparkInterval/PTX/NvidiaPTXRefinement.lean) | Vendor prose is externally reviewed; clause coverage is not full opcode semantics; no division or complete PTX/backend refinement |
| Full result certificate | Every checked claimed row contains every real value represented by its input row and expression; optional theorems give row-wise and finite-sum upper bounds | Lean checker and soundness theorems in [`Certificate/Full.lean`](../SparkInterval/Certificate/Full.lean#L122) | Checks the supplied complete witness; no claim about its producer |
| Generated polynomial module | One modeled in-range thread returns an observed row representing `evalKernel`; with corresponding real inputs, the row contains the realized exact value | [`runBuildModule_inRange`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L32) and [`runBuildModule_inRange_containsReal`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L314) | Typed AST and Lean machine only; polynomial operations only |
| Formal emitted-PTX identity | A successful statement check binds the parsed canonical input batch, target-specific emitted PTX digest, canonical input/parameter/domain hashes, target-profile hash, and artifact-hash record | [`FormalPTXProgram.statementCheck_sound`](../SparkInterval/Execution/FormalPTXProgram.lean) | Artifact identities are caller-selected; no PTX-to-cubin, SASS, driver, or hardware refinement |
| Generated no-write path | Under the theorem's wrapped machine-word out-of-range premise, the modeled module returns with global memory unchanged | [`runBuildModule_outOfRange`](../SparkInterval/PTX/GeneratedKernelOutOfRangeRefinement.lean#L115) | Do not restate as an unconditional natural-index or physical-GPU theorem |
| CUDA and generated-cubin execution | Tested outputs and statuses are compared bit-for-bit with an exact rational Python oracle, with artifact audits and replay checks | Test and conformance tooling | Differential testing, not a Lean refinement theorem |
| Local run bundle | Canonical metadata and supplied artifact bytes are mutually hash-consistent | Run-bundle verifier | Host-forgeable; no execution authority |
| DGX operator signature | A separately pinned Ed25519 key signed the exact artifact-verified local record, with replay checking | Signature and run-bundle verifier | Operator provenance only; always `hardware_evidence: false` |
| Accepted Lean run certificate | Under the sole `accepted_run_certificate_sound` axiom, an accepted certificate supplies its exact historical return and the fixed `Runs` relation for every matching constructor of the closed invocation registry | Unified `RunCertificate.check`, `RegisteredInvocation.statementCheck`, and one explicit trust axiom | Per-run trust, not universal determinism or backend refinement; private-evidence importer is external and not yet implemented |
| Closed registered computation | `cubicSumDivThree20000V1` fixes exact input, parsing, and an executable integer-accumulator/divide-once machine; Lean proves its operational result, agreement with the exact rational sum, and u64 safety for every cube and accumulation step without `native_decide` | [`RegisteredAlgorithm.lean`](../SparkInterval/Execution/RegisteredAlgorithm.lean) and [`RegisteredCubicSumCertificate.lean`](../SparkInterval/Execution/RegisteredCubicSumCertificate.lean) | Axiom-free algorithm and bounded-arithmetic proof only; no positive certificate/importer is supplied, and neither a signature nor these bounds prove that GPU opcodes implemented the machine |
| Signed zeta endpoint payload | The returned canonical full certificate parses to exact typed data; every arithmetic row, paired-singleton endpoint shape, strict sign, and adjacent family order is checked | [`SignedZetaEndpointPayload.check_sound`](../SparkInterval/Execution/SignedZetaEndpointPayload.lean) | Its pure mathematical checks remain separate from `ProducedOutcome`; endpoint enclosure of a selected Hardy-Z function remains an explicit theorem premise, and no zeta checker is registered |
| Multiplicity-aware zeta count | Distinct zeta-zero `ncard` is at most the `ℕ∞` sum of analytic orders, so a certified multiplicity bound supplies `ZetaZeroCountUpperBound` | [`MultiplicityCount.lean`](../SparkInterval/Zeta/MultiplicityCount.lean) | A Turing/argument-principle implementation must still construct the analytic multiplicity upper bound |
| Signed finite-height zeta composition | A checked signed payload plus a proved Hardy-Z model, endpoint enclosures/domain bounds, and multiplicity upper bound yields the finite-height critical-line theorem paired with historical provenance | [`SignedZetaVerifier.lean`](../SparkInterval/Execution/SignedZetaVerifier.lean) | Conditional theorem only; no concrete analytic premises or accepted H100 instance, so no height is certified |
| Registered compact verifier composition | An accepted closed invocation plus decoded compact output and a theorem from its fixed `Runs` semantics to the claim yields the claim without a separate `ExecutionRefines` premise | [`CompactAttestedVerifier.lean`](../SparkInterval/Execution/CompactAttestedVerifier.lean) | The generic FormalPTX compact API remains legacy and still needs explicit refinement; no zeta checker is registered |
| H100 offline artifacts | `compute_90` PTX and `sm_90` cubins can be built and statically inspected without an H100 | Offline build and audit scripts | No H100 query, execution, result, or attestation |
| H100 hardware provenance | No accepted instance or positive evidence importer exists | Fail-closed policy; any future accepted instance uses the same unified trust axiom | Not operational in this repository |
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
machine. The pinned NVIDIA layer proves agreement only for finite-operand
directed `add/sub/mul` and non-NaN `min/max` steps; its clause table does not
supply semantics for the rest of the emitted program. There is also no proof
that `ptxas`, SASS, the CUDA driver, scheduling, or physical hardware
implements the model. The division-capable CUDA expression frontend is
outside this theorem.

## Execution provenance

An unsigned DGX bundle establishes only reproducibility and integrity relative
to supplied bytes. A detached operator signature authenticates an endorsement,
not the truth of the endorsed record. Treating it as a physical-run fact
requires the sole explicit
[`accepted_run_certificate_sound`](../SparkInterval/Execution/Trusted/RunCertificate.lean)
axiom, and the JSON-to-private-Lean-capability importer is not implemented.
[`dgx_operator_signed_run_sound`](../SparkInterval/Execution/Trusted/DGXOperatorSignature.lean)
is now a proved compatibility theorem that feeds DGX policy acceptance to that
one boundary; it is not another axiom.

`SignedResultCertificate.outcomeCheck_sound` composes unified certificate
acceptance with ordinary Lean checks for exact result-text equality and its
SHA-256 digest. Its `ProducedOutcome` contains both the historical return and a
fail-closed registered projection. It proves that the particular certified run
returned the exact supplied result-certificate bytes. The pinned-identity variant
`outcomeCheckForAlgorithm_sound` additionally proves literal expected
algorithm ID/hash equalities.

The preferred formal-semantics handoff is
`outcomeCheckForRegisteredInvocation_sound`. A closed
`RegisteredInvocation.statementCheck` binds the exact algorithm ID and formal
definition digest together with canonical input, parameter, and domain
digests; the sole axiom then supplies that invocation's library-defined `Runs`
relation. `accepted_registered_run_sound` is merely the corresponding
projection of the sole axiom.

The only current registered invocation is
`cubicSumDivThree20000V1`. Its `Runs` relation uses the executable
`cubicSumDivThreeMachine`, which accumulates integer cubes and divides once.
Ordinary Lean theorems prove the exact machine result, its equality to the
rational specification `13334666700000000`, and u64 no-overflow for every cube
and accumulator step, without `native_decide` or a materialized row
certificate. This algorithm-soundness and bounded-arithmetic layer is
axiom-free. It does not prove GPU opcode execution. No importer constructs an
accepted certificate for it, so this is an end-to-end theorem interface rather
than a completed signed-wire demonstration.

The pinned-identity signed-result wrappers can additionally prove literal
equality between the statement's algorithm ID/hash and values pinned by an
application theorem. They do not prove that the pinned digest is a formal PTX
emission, that a cubin was compiled from it, or that the executable refines the
formal algorithm.

For the typed generated-PTX path, the separate `FormalPTXProgram` checker does
derive the algorithm digest from validated target-specific emission of the
exact batch. It also reparses and binds the canonical input and compares the
canonical input/parameter/domain hashes, target-profile hash, and complete
artifact-hash record. Its soundness theorem closes formal-AST-to-emitted-PTX
identity for that path, but the artifact fields remain identities rather than
a proof that `ptxas` produced the named cubin from those PTX bytes.

The H100-specific
[`h100_attested_run_sound`](../SparkInterval/Execution/Trusted/H100Attestation.lean)
entry point is also a proved compatibility theorem over the same sole axiom.
No genuine H100 evidence currently reaches its premise. A future accepted
certificate would also expose fixed `Runs` semantics for any matching closed
invocation, but an application must still provide that registry entry, parse
the result, and prove the algorithm-soundness theorem.

Neither an accepted historical outcome, a per-run registered `Runs` fact, nor
literal executable-identity pins prove the universal claim that every future
physical run of that executable produces the same result. The current formal
artifact binding from emitted PTX to the separately named cubin,
`ptxas`/SASS/driver/hardware refinement, and such a universal theorem remain
open.

## Riemann-zeta scope

The included tutorial encloses positive real values from the Dirichlet series
for supported integer `s > 1`. It uses a division-capable CUDA runner and an
exact Python verifier, so it is neither an instance of the polynomial
typed-machine theorem nor a Lean connection to Mathlib's `riemannZeta`.

The repository now has a finite-height proof skeleton with no zeta-specific
axiom rather than an instantiated numerical verification. It proves
complex-rectangle polynomial containment, an exact-rational endpoint checker
whose family-order comparisons are linear and adjacent, monolithic and chunked
distinct-root lower bounds, a formal Hardy-Z zero-equivalence contract,
compact-region zeta finiteness, and the final theorem that matching
critical-line and total counts put every zero in the rectangle on the line.
`HardyZModel.verifyEndpointFamily` composes the executable family check with
proved enclosure, domain, Hardy-Z, and total-count premises; it does not create
those analytic premises.

The canonical signed-payload path now reparses the complete returned full
certificate, checks every arithmetic row, enforces exactly two singleton finite
endpoint rows per bracket, checks strict signs plus adjacent ordering, and
cross-binds the parser-recomputed embedded batch digest to the accepted
statement and exact formal-program canonical input. Its
final `verifyFiniteHeight` theorem pairs historical provenance with the zeta
conclusion. Its `ProducedOutcome` crosses the sole run-certificate axiom, while
the mathematics comes independently from those pure checks together with
explicit Hardy-Z, endpoint-enclosure, domain, and analytic multiplicity-bound
arguments. No zeta algorithm or invocation is currently registered.

The high-bound pure path also checks independent endpoint chunks with a
resumable previous-boundary state, proves their spans globally ordered and
contiguous, sums their local counts, constructs `ChunkCertificate`, and reaches
the same finite-height theorem. For an even evaluator, the positive-only path
reflects `n` positive brackets into a `2*n` symmetric family without another
set of endpoint arithmetic rows. These are theorem-level `List` inputs, not yet
a proved byte-streaming runtime.

The distinct-versus-multiplicity mismatch is no longer an open logical gap:
Lean proves that distinct zero count is at most the sum of analytic orders and
converts a `ZetaMultiplicityCountUpperBound` into the verifier's distinct-count
upper bound without assuming simple zeros. What remains missing is a checked
Turing/Riemann--von Mangoldt/argument-principle construction of that analytic
upper-bound premise.

No current theorem discharges the Hardy-Z contract, endpoint realization, or
analytic multiplicity bound from numerical zeta data. A usable high-bound
verifier still needs certified theta/log/trigonometric range reduction, a
rigorous Riemann-Siegel formula and remainder, adaptive precision, a streaming
chunk parser, and a checked Turing-method or argument-principle total count.
See the
[high-bound verifier status](algorithms/ZETA_ZERO_VERIFIER.md).
