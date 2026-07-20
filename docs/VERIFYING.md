# Verifier guide

This guide starts from the claim a verifier wants to establish. SparkInterval
has three independent evidence paths:

| Goal | Use | What it does not establish |
| --- | --- | --- |
| Check a mathematical result without trusting its producer | Full Lean result certificate | Who or what produced the certificate |
| Inspect the proof about generated code | Lean typed-machine and compiler theorems | That emitted PTX, SASS, or a physical GPU implements the model |
| Authenticate an execution record | Run-bundle verification, optionally with a DGX operator signature | Mathematical soundness; a DGX signature is not hardware evidence |
| Use an accepted run in later Lean proofs | Closed `RegisteredInvocation`, exact statement check, private evidence import, and the sole run-certificate axiom | Universal backend correctness or future-run behavior; only a proved soundness theorem may turn `Runs` into mathematics |

H100 confidential-computing acceptance is not operational in this repository.
The offline artifacts and policy plumbing cannot produce accepted hardware
evidence.

Run relative commands in this guide from the repository root.

## 1. Pin the source and toolchain

Verify from a specific clean commit and retain these identifiers with the
verification record:

```bash
git rev-parse HEAD
git status --short
cat lean-toolchain
cat dependencies/mathlib4.commit
```

`git status --short` should be empty. After the first build, confirm that the
Lake checkout matches the pinned Mathlib revision:

```bash
git -C .lake/packages/mathlib rev-parse HEAD
```

The expected revision is also declared in `lakefile.toml`. Record the Lean,
Lake, Python, CMake, CUDA, driver, and operating-system versions whenever they
are part of the claim being checked.

## 2. Build the Lean library safely

```bash
./tools/safe_lake_build.py
```

The planner builds local Lean modules serially, holds one plan-wide lock,
detects source changes during the plan, and uses the resource limits described
in [Memory-safe builds](MEMORY_SAFE_BUILDS.md). Do not substitute bare
`lake build` or `lake env lean`: those commands bypass repository-wide
serialization and can schedule several stale modules concurrently.

## 3. Audit proof dependencies

```bash
mkdir -p build/verification
set -o pipefail
./tools/audit_axioms.sh 2>&1 | tee build/verification/axiom-audit.txt
```

The first part of this command automatically rejects `sorry`, `admit`,
`unsafe`, and every source `axiom` except the one named run-certificate
boundary. The Lean audit file then prints `#print axioms` for the public
mathematical, certificate, compiler, and typed-machine theorems.

The command also checks the printed reports automatically. It requires exactly
145 core declaration reports, including the full-row endpoint bridge,
resumable endpoint/chunk checkers, positive reflection, symmetric-count
handoff, and multiplicity-aware zeta count
bridge and 14 for the pinned NVIDIA PTX source,
clause, arithmetic, typed-step, and partial-module refinement surface, and
permits only `propext`, `Classical.choice`, and `Quot.sound` in that group. It
separately requires exactly 13 selected execution-bridge reports. That group
permits the same foundations plus only `accepted_run_certificate_sound`.
A missing report, an extra report, or any unapproved dependency fails the
audit. Retain the output so the checked declaration surface and dependencies
remain inspectable with the verification record.

The fixed audit surface does not include a certificate module generated later
for a particular witness. That generated file prints its own concrete theorem
dependencies when `safe_lean.sh` checks it; retain and interpret that output
according to its recorded decision mode. `native_decide` is a separate
proof-reflection dependency, not a project execution assumption. See
[Trust model](TRUST_MODEL.md#lean-proof-dependencies) for the exact distinction.

The sole permitted project execution axiom is
[`accepted_run_certificate_sound`](../SparkInterval/Execution/Trusted/RunCertificate.lean).
`dgx_operator_signed_run_sound` and `h100_attested_run_sound` are compatibility
theorems proved from it, not separate axioms.
`accepted_registered_run_sound` is also a proved projection: after
`RegisteredInvocation.statementCheck`, it exposes that closed invocation's
fixed `Runs` relation. The sole axiom is not used by the mathematical
certificate checker or generated typed-machine soundness theorems.

## 4. Verify a full Lean result certificate

A full certificate contains every input row and every claimed output row. Lean
decodes the binary64 words into exact rational intervals, reevaluates the
expression, and checks containment. The checked-in two-row example is a small
reproducible verifier exercise:

```bash
mkdir -p build/verification
CERT_DIR="$(mktemp -d build/verification/full-certificate.XXXXXX)"
./tools/safe_lake_build.py SparkInterval.Certificate \
  --target sparkinterval-check-certificate
python3 tools/generate_lean_result_certificate.py \
  --certificate examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001 \
  --output "$CERT_DIR/Generated.lean" \
  > "$CERT_DIR/receipt.json"
./tools/safe_lean.sh "$CERT_DIR/Generated.lean"
./tools/with_memory_limit.sh \
  .lake/build/bin/sparkinterval-check-certificate \
  examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001
```

Use a fresh output path: the generator refuses to overwrite an existing file
or write through a symlink. The receipt binds the source certificate, bound,
decision mode, generated declaration names, and generated Lean source.

The two last commands serve different purposes. The executable evaluates the
Lean checker and returns an acceptance decision. Compiling the generated Lean
file checks concrete theorem declarations and prints their dependencies.

### `native_decide` distinction

The omitted `--decision-mode` selects `kernel`:

- `application_upper_bound_sound` and
  `certificate_sum_upper_bound_sound` check the generated typed data with
  `decide_cbv`; their recorded dependencies do not include `native_decide`.
- The exact serialized-JSON binding, including the concrete parser and hash
  computation, uses `native_decide`. Consequently `application_theorem` and
  `application_sum_theorem` include that proof-reflection dependency.

With `--decision-mode native`, the direct typed-data checks also use
`native_decide`, so both direct and serialized concrete theorem families
include it. The mode is part of the generated namespace and receipt.

If a verification policy forbids `native_decide`, use the default direct
typed-data theorems and state the resulting scope accurately: they prove the
mathematics of the materialized Lean witness, but the current generated proof
does not then bind that witness to the exact JSON bytes. The generic checker
soundness theorems are independent of either concrete reduction mode.

Passing a certificate proves only its stated row-wise or finite-sum predicate.
It does not prove that a GPU ran or establish an unrelated application theorem.

## 5. Verify a local run bundle

Obtain the expected source commit, artifact directory, profile files, and
bundle through channels appropriate to the claim. Then check canonical format
and every bound artifact byte. Set `RUN` to the retained bundle directory:

```bash
RUN=/path/to/retained-run
python3 tools/verify_run_bundle.py \
  "$RUN/run-bundle.json" \
  --artifact-root "$RUN"
```

For `local_unattested`, acceptance establishes internal integrity relative to
the supplied files. A malicious host can fabricate the bundle and every file
it names. A prover-generated nonce shows uniqueness, not freshness; a
freshness claim requires a nonce chosen and tracked by the verifier.

## 6. Verify a DGX operator-signed record

First obtain the operator public key or fingerprint through a trusted channel.
Do not trust only the public key embedded in the signature sidecar. Use a
persistent replay database and a verifier-issued nonce:

```bash
RUN=/path/to/retained-run
SIGNATURE=/path/to/run-bundle.signature.json
TRUSTED_OPERATOR_KEY=/path/to/pinned-operator-public-key.pem
mkdir -p verifier-state
python3 tools/verify_run_bundle.py \
  "$RUN/run-bundle.json" \
  --artifact-root "$RUN" \
  --policy dgx_operator_signed \
  --operator-signature "$SIGNATURE" \
  --trusted-operator-key "$TRUSTED_OPERATOR_KEY" \
  --replay-db verifier-state/dgx-operator-nonces.sqlite3
```

Successful verification means that the pinned Ed25519 key signed the exact
artifact-checked local record. The result remains `local_unattested`, and the
verifier reports `hardware_evidence: false`. It does not prove that a GPU ran
or that the signed statement is truthful.

Lean can turn such a claim into `RunCertificate.ProducedOutcome` only through
`accepted_run_certificate_sound`, the sole run-certificate axiom, which adds
trust in the operator's truthfulness. Its `.historical` field supplies
`AlgorithmReturned`; its `.registered` field supplies fixed formal `Runs`
semantics only after a closed `RegisteredInvocation.statementCheck` succeeds.
`accepted_registered_run_sound` and `dgx_operator_signed_run_sound` are proved
projections around that boundary. The Python signature verifier is
implemented, but an importer that converts its exact canonical output into
Lean's private positive-evidence capability is not. There is therefore no
current end-to-end command that makes a signed JSON bundle discharge this Lean
premise.

Once that premise is available, the aggregate [`SparkInterval.Execution`](../SparkInterval/Execution.lean)
API exposes `SignedResultCertificate`. Its `checkUpperBound_sound` and
`checkSumUpperBound_sound` theorems return three separate facts:

- `ProducedOutcome` and its historical projection from the sole
  run-certificate axiom;
- equality of the returned text with the checked certificate and equality of
  its Lean-computed SHA-256 digest with `statement.outputHash`; and
- the row-wise or finite-sum mathematical theorem from the existing full
  certificate checker.

The mathematical field in this full-certificate route is independently
checked; it is not inferred from either execution projection. The generic
composition proofs do not use `native_decide`. A concrete proof that a large
serialized checker call reduces to `true` still has the decision-mode
considerations described above.

For the narrower execution question, `outcomeCheck_sound` proves that an
accepted certificate's exact named run returned the supplied certificate bytes
and that those bytes have the statement's output digest. Use
`outcomeCheckForAlgorithm_sound` to add literal caller-pinned algorithm ID/hash
equalities. These are exact historical results about a certified run, not a
universal claim that every execution of the algorithm is deterministic or
will return the same bytes.

For a formal execution handoff, prefer
`outcomeCheckForRegisteredInvocation_sound`. The invocation is selected from a
closed inductive type rather than supplied with a caller-chosen proposition;
its statement check binds the formal algorithm definition and exact canonical
input, parameter, and domain digests. A successful theorem yields
`invocation.Runs certificate.resultCertificate`.

The one current example is
`RegisteredInvocation.cubicSumDivThree20000V1`. From an accepted matching
certificate, `certifyCubicSumDivThree20000` proves the exact canonical output
`13334666700000000` and
`RegisteredAlgorithm.cubicSumDivThree 20000 = 13334666700000000`. Its
`Runs` relation is operational: `cubicNumeratorLoop` accumulates integer cubes
and `cubicSumDivThreeMachine` divides once. Axiom-free Lean theorems prove the
machine result, agreement with the rational sum, and that every cube and
accumulator step stays below `2^64`. These symbolic proofs have no
`native_decide` dependency. They do not prove that GPU opcodes implement the
machine. Because the private-evidence importer is absent, the repository
supplies the theorem and negative/conditional tests but no accepted signed
bundle instance.

For application handoff, prefer `checkUpperBoundForAlgorithm_sound` or
`checkSumUpperBoundForAlgorithm_sound`. They additionally prove that the
statement's algorithm ID and definition digest literally equal a caller-pinned
`ExpectedExecutableIdentity`. This generic binding still requires the caller
to justify that its chosen literals denote the intended formal algorithm.
It does not unlock `RegisteredAlgorithm.Runs`; use the closed invocation check
when later Lean proofs need formal execution semantics.

For the existing typed generated-PTX path,
`outcomeCheckForFormalPTX_sound` provides a stronger identity result. Its pure
statement check reparses the exact canonical input into the selected
`ReferenceBatch`, validates and emits `buildModule` for the statement target,
recomputes the emitted-PTX, canonical-input, canonical-parameter, and
canonical-domain hashes, and requires exact target, target-profile, and
artifact-hash equality. Its outcome theorem adds the same accepted historical
run and exact returned-text binding. It does not prove that the artifact files
have those digests, that the named cubin was compiled from the emitted PTX, or
that the cubin ran on an H100.

For the current zeta endpoint format,
`SignedZetaEndpointPayload.payloadCheck` adds four independently checked
layers: canonical full-certificate parsing with exact typed equality, every
full-certificate arithmetic row, the paired singleton/finite endpoint shape,
and the exact-rational family sign/adjacent-order check. The combined
`SignedZetaEndpointPayload.check_sound` packages those facts beside the formal
PTX outcome. Its `ProducedOutcome` uses
`accepted_run_certificate_sound`; none of the parser, arithmetic, shape, or
family facts follow from attestation or from the registered projection. No
zeta checker is currently a constructor of the closed registry.

`SignedZetaEndpointPayload.verifyFiniteHeight` is the final conditional
handoff. It additionally requires a proved `HardyZModel`, explicit
`EnclosesEndpoints` and domain-bound proofs, and a
`ZetaMultiplicityCountUpperBound`. Its mathematical field proves the
finite-height zeta conclusion from those premises. Its historical field records
the accepted run. Do not use the latter as evidence for the former: the
repository still lacks concrete Hardy-Z/Riemann-Siegel endpoint realization
and a checked Turing/argument-principle multiplicity bound.

For a future server-side zeta checker, the preferred compact theorem is
`certifyRegisteredCompactFiniteHeightZeta`. It has no separate
`ExecutionRefines` argument: the accepted closed invocation supplies its fixed
per-run `Runs` relation, and a proved `verifierSound` theorem must derive the
finite-height claim. The legacy generic FormalPTX theorem
`certifyCompactFiniteHeightZeta` remains available and still requires explicit
execution refinement. Neither interface supplies the missing zeta analytics,
and the preferred theorem has no usable zeta registry entry today.

This composition also does not connect the current division-capable zeta CUDA
runner to the polynomial typed-PTX theorem. It proves only the predicate
actually checked by the supplied full certificate.

There is no compatible retained bundle to feed this API today. A wire run
statement records an output artifact path, size, and hash, not the output text;
a future importer must verify and read that exact file to construct the Lean
result binding. The generated-cubin workflow's output is `results.bin`, while
the zeta workflow's output is `zeta-report.json`. Neither has the canonical
full-certificate schema required by `SignedResultCertificate`.

The formal-AST-to-emitted-PTX identity is therefore available only through
that dedicated path and hash convention. Generated-cubin bundles currently
define `algorithmHash` as the cubin digest, while `FormalPTXProgram` defines it
as the digest of `renderUncheckedFor target (buildModule batch)`. Wire bundles
can also bind a `gpu_ptx` artifact, but the Lean `ArtifactHashes` type does not
retain that PTX digest. Do not reinterpret the cubin digest as the formal PTX
digest. A production importer and a proof connecting the separately bound
cubin to the emitted PTX are still missing;
`ptxas`/SASS/driver/hardware refinement remains external.

## 7. Interpret H100 artifacts fail-closed

The following self-tests cross-build and inspect real `compute_90` PTX and
`sm_90` cubins without querying or executing an H100:

```bash
./tests/test_h100_offline.sh
./tests/test_h100_interval_batch_offline.sh
```

[`tools/run_h100_cc_acceptance.sh`](../tools/run_h100_cc_acceptance.sh) is a
deliberate stub that exits 78 and cannot accept a result. The production
run-bundle policy can call a separately supplied attestation-verifier
executable, but this repository supplies neither a production NVIDIA evidence
verifier nor a positive Lean evidence importer. Offline, mock, and local
records cannot satisfy `checkH100Attestation`.

An accepted H100 premise would yield `ProducedOutcome` through the same
`accepted_run_certificate_sound` axiom; `h100_attested_run_sound` is a proved
historical compatibility wrapper. If a complete closed invocation check also
succeeds, `accepted_registered_run_sound` yields its fixed `Runs` semantics.
No H100 workload is thereby registered automatically: a reviewed registry
constructor, result decoder, and ordinary application-soundness theorem remain
necessary.

## Public theorem map

| Surface | Public theorem | Source |
| --- | --- | --- |
| Abstract real interval evaluator | `evalInterval_sound` | [`EvalSound.lean`](../SparkInterval/EvalSound.lean#L84) |
| Binary64 directed rounding | `roundDown_le`, `le_roundUp`, `roundDown_greatest`, `roundUp_least` | [`DirectedRounding.lean`](../SparkInterval/DirectedRounding.lean#L182) |
| Binary64 interval operations | `FPInterval.add_contains`, `sub_contains`, `mul_contains`, `div_contains` | [`FPIntervalSound.lean`](../SparkInterval/FPIntervalSound.lean#L71) |
| Polynomial evaluator | `PolynomialExpr.evalKernel_sound` | [`PolynomialSemantics.lean`](../SparkInterval/PTX/PolynomialSemantics.lean#L297) |
| Pinned PTX source and opcode clauses | `allowedOpcode_has_pinned_clause`, `buildModule_opcodeTrace_all_have_pinned_clauses` | [`NvidiaPTXSpec.lean`](../SparkInterval/PTX/NvidiaPTXSpec.lean), [`NvidiaPTXRefinement.lean`](../SparkInterval/PTX/NvidiaPTXRefinement.lean) |
| PTX arithmetic-slice refinement | `directedBinary_finite_refines`, `executeInstruction_binaryF64_finite_refines`, `minimum_nonNaN_refines`, `maximum_nonNaN_refines` | [`NvidiaPTXRefinement.lean`](../SparkInterval/PTX/NvidiaPTXRefinement.lean) |
| Compiler structure | `StructuralCompilerCorrect.buildModule_eq_expectedModule` | [`StructuralCompilerCorrect.lean`](../SparkInterval/PTX/StructuralCompilerCorrect.lean#L887) |
| Generated opcode sequence | `buildModule_opcodeTrace` | [`Generator.lean`](../SparkInterval/PTX/Generator.lean#L541) |
| Deterministic text rendering | `emit_success`, `emit_of_validate` | [`Emitter.lean`](../SparkInterval/PTX/Emitter.lean#L233) |
| In-range modeled execution | `runBuildModule_inRange`, `runBuildModule_inRange_containsReal` | [`GeneratedKernelRunRefinement.lean`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L32) |
| Modeled no-write return path | `runBuildModule_outOfRange` | [`GeneratedKernelOutOfRangeRefinement.lean`](../SparkInterval/PTX/GeneratedKernelOutOfRangeRefinement.lean#L115) |
| Full certificate | `FullCertificate.check_sound`, `checkUpperBound_sound`, `checkSumUpperBound_sound` | [`Full.lean`](../SparkInterval/Certificate/Full.lean#L122) |
| Serialized certificate | `impliesTheorem`, `impliesSumTheorem` | [`Format.lean`](../SparkInterval/Certificate/Format.lean#L367) |
| Unified accepted run | `accepted_run_certificate_sound`; DGX/H100 compatibility theorems derive from it | [`Trusted/RunCertificate.lean`](../SparkInterval/Execution/Trusted/RunCertificate.lean) |
| Closed registered semantics | `RegisteredInvocation.statementCheck_sound`, `accepted_registered_run_sound`, `outcomeCheckForRegisteredInvocation_sound` | [`RegisteredAlgorithm.lean`](../SparkInterval/Execution/RegisteredAlgorithm.lean), [`Trusted/RunCertificate.lean`](../SparkInterval/Execution/Trusted/RunCertificate.lean), [`SignedResultCertificateComposition.lean`](../SparkInterval/Execution/SignedResultCertificateComposition.lean) |
| Registered cubic-sum result and u64 bounds | `cubicSumDivThreeMachine_20000`, `cubicSumDivThreeMachine_sound_20000`, `cube_lt_u64`, `cubicNumeratorLoop_lt_u64`, `cubicNumeratorStep_lt_u64`, `SignedResultCertificate.certifyCubicSumDivThree20000` | [`RegisteredAlgorithm.lean`](../SparkInterval/Execution/RegisteredAlgorithm.lean), [`RegisteredCubicSumCertificate.lean`](../SparkInterval/Execution/RegisteredCubicSumCertificate.lean) |
| Exact returned certificate | `SignedResultCertificate.outcomeCheck_sound`, `outcomeCheckForAlgorithm_sound` | [`SignedResultCertificateComposition.lean`](../SparkInterval/Execution/SignedResultCertificateComposition.lean) |
| Checked returned certificate | `SignedResultCertificate.checkUpperBound_sound`, `checkSumUpperBound_sound`, `checkUpperBoundForAlgorithm_sound`, `checkSumUpperBoundForAlgorithm_sound` | [`SignedResultCertificateComposition.lean`](../SparkInterval/Execution/SignedResultCertificateComposition.lean) |
| Signed typed zeta payload | `SignedZetaEndpointPayload.payloadCheck_sound`, `check_sound`, `CertifiedForFormalPTX.statementResult_parses`, `check_exists_zeroCertificate` | [`SignedZetaEndpointPayload.lean`](../SparkInterval/Execution/SignedZetaEndpointPayload.lean) |
| Multiplicity count bridge | `coe_ncard_le_zetaZeroMultiplicityCount`, `ZetaMultiplicityCountUpperBound.toZetaZeroCountUpperBound`, `ZetaMultiplicityCountCertificate.check_sound` | [`MultiplicityCount.lean`](../SparkInterval/Zeta/MultiplicityCount.lean) |
| Signed finite-height zeta composition | `SignedZetaEndpointPayload.verifyFiniteHeight`, `verifyFiniteHeightWithCountCertificate` | [`SignedZetaVerifier.lean`](../SparkInterval/Execution/SignedZetaVerifier.lean) |
| Preferred registered compact composition | `certifyRegisteredCompactVerifierOutcome`, `certifyRegisteredCompactFiniteHeightZeta` | [`CompactAttestedVerifier.lean`](../SparkInterval/Execution/CompactAttestedVerifier.lean) |

The generated-kernel theorem is about one thread executing the exact typed
polynomial AST in Lean's machine model. Its hypotheses include safe thread and
memory layouts, an encoded selected row, a corresponding environment, and a
successful evaluator result. It is not an operational theorem about emitted
PTX text or NVIDIA hardware. See [GPU model](GPU_MODEL.md).

## Claim language

After checking the relevant evidence, it is accurate to say:

- “Lean checked that this full witness implies the stated row or finite-sum
  bound,” with the concrete proof dependencies disclosed.
- “Lean proves the generated polynomial typed AST returns a representing
  output in its modeled one-thread machine, under the theorem's hypotheses.”
- “Lean proves that the typed model's finite directed `add/sub/mul` and
  non-NaN `min/max` steps agree with the pinned PTX 9.0 transcription.”
- “The local bundle is internally artifact-consistent.”
- “The pinned operator key signed this exact local bundle.”
- “The checked statement's algorithm ID and definition digest equal these
  pinned literal values,” when using a pinned-identity wrapper.
- “The formal-PTX statement check binds the exact parsed input batch, emitted
  target-specific PTX digest, canonical input/parameter/domain hashes,
  target-profile hash, and artifact identities,” when using
  `statementCheck_sound`; do not extend this to a cubin-compilation or physical
  execution claim.
- “Under the sole run-certificate axiom, this accepted historical run returned
  these exact certificate bytes,” when `outcomeCheck_sound` applies.
- “Under the sole run-certificate axiom and this successful closed-invocation
  statement check, the accepted certificate establishes the fixed registered
  algorithm's `Runs` relation for this exact invocation,” when
  `outcomeCheckForRegisteredInvocation_sound` applies.
- “For the registered `cubicSumDivThree20000V1` invocation, ordinary Lean
  theorems prove the integer accumulator/divide-once machine's exact output
  `13334666700000000`, agreement with the rational sum, and u64 safety of each
  step without `native_decide`,” when the registered cubic theorems apply.
  State separately that this is not a GPU-opcode theorem and that no positive
  evidence importer or accepted instance is supplied.
- “Lean canonically parsed the returned full endpoint certificate and checked
  every arithmetic row, paired-singleton shape, strict endpoint sign, and
  adjacent family ordering,” when `SignedZetaEndpointPayload.check_sound`
  applies; this is not yet a Hardy-Z enclosure claim.
- “These `sm_90` artifacts were cross-built and statically inspected; no H100
  execution was established.”
- “Lean's endpoint-family checker uses exact rational local checks and adjacent
  ordering comparisons, and—with proved evaluator enclosures, a proved
  Hardy-Z model, domain bounds, and a matching total zero-count upper
  bound—implies the finite-height zeta conclusion,” while disclosing that the
  analytic model, enclosures, and total count have not yet been instantiated by
  the executable implementation.
- “Given the explicitly supplied Hardy-Z model, endpoint enclosures/domain
  bounds, and analytic multiplicity upper bound, the signed verifier pairs the
  finite-height zeta theorem with this accepted run's historical outcome.”
  State separately that `ProducedOutcome` uses the project execution axiom,
  the zeta mathematics is independently proved on this route, and no concrete
  positive height is currently instantiated.
- “A future closed registered zeta checker could keep its large witness
  server-side and use `certifyRegisteredCompactFiniteHeightZeta` without a
  second `ExecutionRefines` premise,” only while also stating that no zeta
  checker is registered and its full algorithm-soundness theorem is missing.

Do not say:

- that differential tests formally verify CUDA, PTX-to-SASS compilation, the
  driver, or hardware;
- that a clause citation or the finite/non-NaN arithmetic refinement is a
  formal semantics for the complete emitted PTX program;
- that a DGX signature proves a GPU execution;
- that a signature, attestation envelope, algorithm ID/hash, or caller-chosen
  proposition by itself establishes `RegisteredInvocation.Runs`;
- that an offline or mock H100 record is hardware-attested;
- that one accepted historical or registered run proves every future physical
  run is deterministic, returns the same result, or establishes a universal
  PTX/cubin/driver/hardware refinement;
- that `AlgorithmReturned` by itself proves algorithm soundness or the
  mathematical meaning of the returned string;
- that `Runs` proves an application theorem without the registered
  algorithm's ordinary Lean soundness theorem;
- that the real-integer zeta tutorial verifies critical-strip zeros, the
  Riemann hypothesis, or zeros up to any height.

The canonical claim matrix is in [Correctness claims](CORRECTNESS_CLAIMS.md),
and all external assumptions are collected in [Trust model](TRUST_MODEL.md).
