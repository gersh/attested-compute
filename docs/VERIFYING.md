# Verifier guide

This guide starts from the claim a verifier wants to establish. SparkInterval
keeps these evidence paths independent:

| Goal | Use | What it does not establish |
| --- | --- | --- |
| Check a mathematical result without trusting its producer | Full Lean result certificate | Who or what produced the certificate |
| Inspect the proof about generated code | Lean typed-machine and compiler theorems | That emitted PTX, SASS, or a physical GPU implements the model |
| Authenticate an execution record | Run-bundle verification, optionally with a DGX operator signature | Mathematical soundness; a DGX signature is not hardware evidence |
| Authenticate an Azure confidential CPU/H100 run | Fresh challenge, independent Azure/NVIDIA appraisal, signed receipt, and reviewed source registry | Arbitrary user-space causality or mathematical correctness without measured-runner and algorithm-soundness proofs |
| Use an accepted run in later Lean proofs | Closed `RegisteredInvocation`, exact statement check, private evidence import, and the sole run-certificate axiom | Universal backend correctness or future-run behavior; only a proved soundness theorem may turn `Runs` into mathematics |

The Azure collector, independent-appraisal adapter, receipt signer interface,
source-pinned registry generator, and generated Lean consumer are operational
as tools. The tracked receipt registry is empty and the checked-in key is
development-only. No production appraiser/key, real Azure run, or accepted
hardware evidence is included.

Run relative commands in this guide from the repository root.

Repository verification does not replay the production ternary-Goldbach
campaigns. Local and CI work is limited to proof compilation, static
closure/receipt checks, and tiny known-answer inputs; production arithmetic
belongs to the measured Azure jobs described below.

For the quick control-plane check, before any proof compilation, run:

```bash
make local-static
```

This checks every cloud-only workload guard, the Sqrt218 source callgraph,
and the compact proof-build, launcher-boundary, launcher-build, and compiler
discovery manifests. It does not compile or execute a native worker, open a
production certificate, or reconstruct an architecture trace.

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

## 2. Build the compact Lean proof root safely

```bash
./tools/safe_lake_build.py
```

The no-argument planner builds the explicit `SparkIntervalCompact` import
closure serially, holds one plan-wide lock, detects source changes during the
plan, and uses the resource limits described in
[Memory-safe builds](MEMORY_SAFE_BUILDS.md). Bare `lake build` now selects the
same compact default target, but it lacks the wrapper's plan lock, source
snapshot, and aggregate cgroup limit.

For a focused source change, pass the exact dotted module name to the safe
planner. A dotted module such as
`SparkInterval.Execution.X86ELFExactPureEntry` names one source closure;
`SparkInterval.Execution` is itself a production aggregate, while
`SparkInterval` is the broad library target. Both pull in unrelated
multi-megabyte generated tables, and the safe planner refuses their
materialized closure outside the measured Azure scope.

Run the static boundary audit independently of Lean:

```bash
python3 tools/audit_local_lean_boundary.py
```

It recomputes the complete compact import closure, verifies the Lake default,
rejects any direct or transitive path to `SparkInterval.Generated`,
`RegisteredAlgorithm`, the run-certificate/registered/signed/trusted receipt
stack, production-named modules, or replay/trace modules, and enforces the
documented source byte/line budget. In particular, the legacy
`PlattHeadQ128` and `CDEMAbelProduction` literal certificates remain outside
the local proof root.

At this source revision the closure is exactly **123 local modules, 1,518,295
source bytes, and 39,106 source lines**. Its enforced ceilings are 2,097,152
bytes and 50,000 lines. The closure includes the closed 13-atom architecture
registry, all ten external-campaign checker adapters, the three-fold Ramaré
native-family fallback, the closed 15-family/1,371-root aggregate invocation
catalog, the fixed-decision checker, the fail-closed native aggregate
capstone, the all-atom capstone,
`CompactArchitectureReceipt`, `X86StaticBinaryCertificate`,
`CX86ELFComposition`, `CX86StaticCertificateComposition`, and the V2
`ExecutionClosureIdentity`; it excludes
`SparkInterval.Execution.RegisteredAlgorithm`,
`SparkInterval.Execution.RunCertificate`,
`SparkInterval.Generated.PlattHeadQ128`, and
`SparkInterval.Generated.CDEMAbelProduction`.

The broad source-materialized library is available only through
`--full-production-library` / `make lean-production`. Both fail before source
planning unless the measured Azure worker scope is present. That environment
scope is an accidental-dispatch guard, not attestation evidence.

## 3. Audit proof dependencies

First audit the closed accounting for every trust root in the last fresh
ternary-Goldbach capstone:

```bash
python3 tools/audit_tg_full_trust_boundary.py
python3 tools/audit_tg_full_trust_boundary.py \
  --claude-math-root ../claude_math
```

The first command joins the production-data-free external and native-family
catalogs. The second additionally pins and parses the retained
`Statement.trace`, and requires all 1,387 reported roots to match exactly.
Neither command replays a finite computation.

For the local source and compact-closure gate:

```bash
make audit
```

The fixed full-production axiom report is an Azure qualification operation,
because importing its aggregate environment materializes the legacy
production tables. Inside the measured qualification worker, retain:

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
159 core declaration reports, including the full-row endpoint bridge,
resumable endpoint/chunk checkers, positive reflection, symmetric-count
handoff, and multiplicity-aware zeta count
bridge and 14 for the pinned NVIDIA PTX source,
clause, arithmetic, typed-step, and partial-module refinement surface, and
permits only `propext`, `Classical.choice`, and `Quot.sound` in that group. It
separately requires exactly 16 selected execution-bridge reports. That group
permits the same foundations plus only `accepted_run_certificate_sound`.
A missing report, an extra report, or any unapproved dependency fails the
audit. Retain the output so the checked declaration surface and dependencies
remain inspectable with the verification record.

For a dated cold-project/warm-dependency timing of this audit together with
the Python and native validation phases, see the
[local repository qualification benchmark](AZURE_PERFORMANCE_SIZING.md#local-repository-qualification-benchmark).
That timing is not an estimate for recomputing the thirteen source-scale
external atoms.

The fixed audit surface does not include a certificate module generated later
for a particular witness. That generated file prints its own concrete theorem
dependencies when `safe_lean.sh` checks it; retain and interpret that output
according to its recorded decision mode. `native_decide` is a separate
proof-reflection dependency, not a project execution assumption. See
[Trust model](TRUST_MODEL.md#lean-proof-dependencies) for the exact distinction.

The sole permitted project execution axiom is
[`accepted_run_certificate_sound`](../SparkInterval/Execution/Trusted/RunCertificate.lean).
Its premise is the exact source-admitted `checkTrustedCompute` policy. The
legacy DGX-signature and H100 structural checks are diagnostic only;
`RunCertificate.check` rejects their constructors, and the corresponding
`*_not_admitted` theorems prove that they cannot reach the axiom.
`accepted_registered_run_sound` is also a proved projection: after
`RegisteredInvocation.statementCheck` has recomputed the canonical source
hashes and accepted the invocation-specific canonical result language, it
exposes that closed invocation's fixed `Runs` relation. The sole axiom is not
used by the mathematical certificate checker or generated typed-machine
soundness theorems.

### Audit concrete receipt use

The ordinary axiom report names the single generic execution boundary. To see
which exact receipts a particular theorem uses, import the certificate audit
commands and inspect the theorem itself:

```lean
import SparkInterval.Audit.TrustedComputeCertificates

#print certificates SomeNamespace.someTheorem
#audit certificates SomeNamespace.someTheorem
```

`#print certificates` is diagnostic: it prints the complete root-axiom set,
whether the execution axiom is reachable, every concrete receipt as
`sha256:<64 lowercase hex digits>`, and the proof-dependency path to the
receipt-binding declaration. It ends with a machine-readable
`certificate-audit-v1` status:

- `AXIOM_FREE` means the execution axiom is unreachable;
- `COVERED` means every path to it is mediated by a closed wrapper carrying a
  literal, canonical receipt hash; and
- `FAIL_UNATTRIBUTED` means at least one path is generic or otherwise lacks a
  valid concrete receipt binding.

An additional `FAIL_UNEXPECTED_AXIOMS` status reports any root axiom outside
the three disclosed Lean foundations and the one execution axiom.
`#audit certificates` emits the same details but deliberately fails
elaboration for either failing status. Use the auditing form as the acceptance
gate and retain its output with the reviewed receipt.

Generated trusted-compute consumers use
`acceptedRunCertificateForReceipt`. The kernel checks its equality proof, so
the literal hash displayed by the audit is the hash selected by the
certificate's `.trustedCompute` attestation. The wrapper is proved through the
same `accepted_run_certificate_sound`; it creates no per-receipt axiom.
Generic conditional theorems that expose the bridge before a receipt exists
properly print `FAIL_UNATTRIBUTED`. A concrete generated consumer must use the
hash-binding wrapper before it can report `COVERED`.

Discover receipt sites across the loaded project environment, including
declarations that are not downstream of a root someone happened to query:

```lean
#print project certificates
#audit project certificates
```

The project report groups concrete sites by canonical receipt SHA-256, names
each instantiating declaration, and lists every declaration that directly
calls the generic execution axiom. Direct calls are checked against a closed
reviewed bridge list. The auditing form rejects malformed wrappers, new direct
callers, concrete anchors that do not pass the per-root audit, and unexpected
project axioms. Its stable `project-certificate-audit-v1` line includes unique
hash and site counts. Zero sites is a valid result while the reviewed registry
is empty.

These commands inspect the loaded kernel environment, not unimported files.
The repository gate therefore runs the audit from
`SparkInterval/Tests/ProjectCertificateAudit.lean`, which imports the aggregate
`SparkInterval.Execution` production certificate API. Audit project axiom
declarations directly as well:

```lean
import SparkInterval.Blueprint
import SparkInterval.Audit.TrustedComputeCertificates

#audit project axioms
```

This rejects any project axiom other than
`accepted_run_certificate_sound`, including an axiom spelled as `constant`.
Imports in the audit file define its project surface; the Azure qualification
lane runs `tools/audit_axioms.sh` for the aggregate environment and fixed
public-theorem checks, while `make audit` remains the ordinary local
whole-tree source/compact-boundary gate. Receipt attribution is a proof-term audit, not
cryptographic verification. In particular, hand-admitting a registry entry is
trust-equivalent at the execution boundary to accepting that external
receipt. The tracked registry is empty, so no current production theorem can
show `COVERED`; the checked-in generic bridge examples are expected to remain
unattributed until a reviewed receipt is imported.

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

Lean does not turn this DGX claim into `RunCertificate.ProducedOutcome`.
`RunCertificate.check` unconditionally rejects `.dgxOperatorSignature`, and
`dgx_operator_signature_not_admitted` proves that even a positive structural
diagnostic cannot reach `accepted_run_certificate_sound`. The Python verifier
therefore supplies operator provenance only, not `AlgorithmReturned`, fixed
formal `Runs` semantics, or a theorem-producing Lean premise. The separate
Azure source-receipt route is described in section 7; only that route can
produce an accepted trusted-compute certificate.

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

The CPU example is `RegisteredInvocation.cubicSumDivThree20000V1`. From an accepted matching
certificate, `certifyCubicSumDivThree20000` proves the exact canonical output
`13334666700000000` and
`RegisteredAlgorithm.cubicSumDivThree 20000 = 13334666700000000`. Its
`Runs` relation is operational: `cubicNumeratorLoop` accumulates integer cubes
and `cubicSumDivThreeMachine` divides once. Axiom-free Lean theorems prove the
machine result, agreement with the rational sum, and that every cube and
accumulator step stays below `2^64`. These symbolic proofs have no
`native_decide` dependency. They do not prove that GPU opcodes implement the
machine. The tracked trusted-compute registry has no matching receipt, so the
repository supplies the theorem and negative/conditional tests but no
accepted signed-bundle instance.

The GPU example is `RegisteredInvocation.h100FormalPtxConstantOneV1`, a
one-row, zero-variable `sm_90` deployment pilot. The axiom-free
`h100FormalPtxConstantOnePTX_eq_formalEmitter` theorem identifies its
registered PTX with the formal emitter's output for the closed `[1,1]` batch.
`certifyH100FormalPtxConstantOne` derives the exact compact output, endpoint
decodings, and that formal-program identity from an accepted matching
certificate. The tracked registry likewise supplies no accepted instance.

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
zeta checker is currently a constructor of the closed algorithm registry.

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

There is no compatible retained accepted bundle to feed this API today. A wire
run statement records an output artifact path, size, and hash, not the output
text. The Azure receipt importer verifies and reads that exact file before
committing its UTF-8 contents, but the generated-cubin workflow's output is
`results.bin` and the zeta workflow's output is `zeta-report.json`. Neither has
the canonical full-certificate schema required by `SignedResultCertificate`.

The formal-AST-to-emitted-PTX identity is therefore available only through
that dedicated path and hash convention. Generated-cubin bundles currently
define `algorithmHash` as the cubin digest, while `FormalPTXProgram` defines it
as the digest of `renderUncheckedFor target (buildModule batch)`. Wire bundles
can also bind a `gpu_ptx` artifact, but the Lean `ArtifactHashes` type does not
retain that PTX digest. Do not reinterpret the cubin digest as the formal PTX
digest. A proof connecting the separately bound cubin to the emitted PTX is
still missing;
`ptxas`/SASS/driver/hardware refinement remains external.

## 7. Verify and source-admit Azure trusted compute

The offline H100 self-tests still make only an artifact claim:

```bash
./tests/test_h100_offline.sh
./tests/test_h100_interval_batch_offline.sh
```

They neither query a device nor produce attestation. The legacy
`run_h100_cc_acceptance.sh` provider also remains a deliberate fail-closed
stub. Production Azure evidence uses the distinct trusted-compute route below.

First create a fresh challenge on the relying-party machine and preflight the
exact target. Use `azure/cpu_cvm.py` instead when the finite job needs only
confidential CPU/FLINT/Arb execution:

```bash
python3 azure/create_attestation_challenges.py \
  --campaign-id reviewed-run-01 --count 1 \
  --output-dir build/reviewed-run-01-challenges

python3 azure/ncc_h100.py preflight \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location eastus2 --nodes 1
```

Follow the [Azure operator guide](AZURE_CONFIDENTIAL_COMPUTE.md) to deploy a
private `Standard_NCC40ads_H100_v5` VM, stage a reviewed content-addressed
runner, run the finite computation, produce its exact canonical bundle and
UTF-8 output, and collect post-run evidence. The collector requires a pinned
MAA endpoint and binds the off-VM challenge and wire-statement digest into MAA,
NVIDIA, and vTPM evidence:

```bash
sudo python3 attestation/collect_azure_ncc_evidence.py \
  --challenge /secure-input/shard-000.challenge.json \
  --backend azure_ncc40ads_h100_v5 \
  --statement-file /run/shard-000/statement.json \
  --statement-sha256 "$STATEMENT_SHA256" \
  --maa-attestation-url "$PINNED_MAA_ATTESTATION_URL" \
  --output-dir /run/shard-000/azure-evidence
```

Collection is not acceptance. Outside the worker VM, appraise the returned
pack with a canonical policy whose Azure and NVIDIA executables and policy
files are independently reviewed and SHA-256 pinned:

```bash
attestation/verify_azure_ncc_evidence.py \
  --evidence-pack /returned/shard-000/azure-evidence \
  --policy /reviewed-policy/composite-policy.json \
  --backend azure_ncc40ads_h100_v5 \
  --expected-challenge-file /retained-off-vm/shard-000.challenge.json \
  --expected-start-challenge-sha256 "$START_CHALLENGE_SHA256" \
  --expected-result-binding-sha256 "$RESULT_BINDING_SHA256"
```

The retained challenge path must name the original canonical file kept outside
the worker, not a returned copy. The adapter requires the entire returned
challenge object to equal it and rechecks that file after appraisal. It must
cryptographically validate MAA/SEV-SNP/vTPM evidence and,
for H100, NVIDIA certificate, RIM, revocation, EAT, nonce, security-state, and
validity claims. It recomputes the complete artifact closure and does not trust
collector booleans. Its successful normalized output still does not prove
that arbitrary user-space code caused the result: the accepted platform policy
must cover an immutable measured runner and executable closure, using IMA,
dm-verity, or an equivalently reviewed mechanism.

Issue the compact receipt with a production Azure Managed HSM key. The
[Managed HSM signing guide](AZURE_MANAGED_HSM_SIGNING.md) contains the exact
key provisioning, attestation, pinning, and signer command. Do not use the
checked-in bootstrap key or `--allow-development-key` for a production
admission. The receipt issuer invokes the evidence verifier again and binds its
binary and policy hashes, validity interval, run bundle, output, challenge,
and result-binding digest before signing.

Supply the original retained challenge and one shared durable issuer ledger as
`--retained-challenge ... --replay-db ...`. The issuer atomically burns the
nonce/challenge/statement/backend tuple before appraisal; failures stay spent.
It installs output without replacing an existing path, fsyncs it, and only then
marks the row signed. The production key manifest and Lean policy must also pin
the exact backend, target-profile digest, trust-profile digest, verifier binary,
and appraisal-policy tuple. A valid signature under an unapproved tuple or
development-classified key is rejected.

Finally add the production public-key pin and reviewed receipt to source, then
compile the generated consumer:

```bash
python3 tools/generate_trusted_compute_registry.py \
  /returned/shard-000/trusted-compute-receipt.json \
  --out SparkInterval/Execution/TrustedComputeRegistry.lean
git diff -- SparkInterval/Execution/TrustedComputeRegistry.lean

mkdir -p build/trusted-compute
python3 tools/generate_trusted_compute_lean.py \
  /returned/shard-000/trusted-compute-receipt.json \
  --namespace ReviewedAzureRun \
  --out build/trusted-compute/ReviewedAzureRun.lean
./tools/safe_lean.sh build/trusted-compute/ReviewedAzureRun.lean
```

The generated `accepted` theorem uses ordinary kernel reduction for exact
source-registry membership and structural binding. Only
`producedOutcome` crosses `accepted_run_certificate_sound`, the sole project
execution axiom. Its registered projection is useful only if the receipt also
matches a constructor of the closed `RegisteredInvocation` type; an ordinary
Lean theorem from that invocation's fixed `Runs` semantics to the application
claim is still required. A signature or receipt cannot select an arbitrary
proposition.

The tracked `TrustedComputeRegistry.lean` is empty. These commands describe
the implemented admission process; they do not document a run that this
repository has actually performed.

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
| Source-admitted accepted run | `accepted_run_certificate_sound`; its premise is exactly `checkTrustedCompute` | [`Trusted/RunCertificate.lean`](../SparkInterval/Execution/Trusted/RunCertificate.lean) |
| Source-pinned Azure receipt | `checkTrustedCompute`; exact lookup, claim, backend, and evidence bindings reduce before the unified axiom | [`TrustedComputePolicy.lean`](../SparkInterval/Execution/TrustedComputePolicy.lean), [`TrustedComputeRegistry.lean`](../SparkInterval/Execution/TrustedComputeRegistry.lean) |
| Legacy DGX/H100 structures | `dgx_operator_signature_not_admitted`, `h100_attestation_not_admitted`; positive diagnostics remain rejected by `RunCertificate.check` | [`Trusted/DGXOperatorSignature.lean`](../SparkInterval/Execution/Trusted/DGXOperatorSignature.lean), [`Trusted/H100Attestation.lean`](../SparkInterval/Execution/Trusted/H100Attestation.lean) |
| Closed registered semantics | `RegisteredInvocation.statementCheck_sound`, `RegisteredInvocation.certificateBindingCheck`, `accepted_registered_run_sound`, `outcomeCheckForRegisteredInvocation_sound` | [`RegisteredAlgorithm.lean`](../SparkInterval/Execution/RegisteredAlgorithm.lean), [`Trusted/RunCertificate.lean`](../SparkInterval/Execution/Trusted/RunCertificate.lean), [`SignedResultCertificateComposition.lean`](../SparkInterval/Execution/SignedResultCertificateComposition.lean) |
| Registered cubic-sum result and u64 bounds | `cubicSumDivThreeMachine_20000`, `cubicSumDivThreeMachine_sound_20000`, `cube_lt_u64`, `cubicNumeratorLoop_lt_u64`, `cubicNumeratorStep_lt_u64`, `SignedResultCertificate.certifyCubicSumDivThree20000` | [`RegisteredAlgorithm.lean`](../SparkInterval/Execution/RegisteredAlgorithm.lean), [`RegisteredCubicSumCertificate.lean`](../SparkInterval/Execution/RegisteredCubicSumCertificate.lean) |
| Registered H100 formal-PTX pilot | `h100FormalPtxConstantOnePTX_eq_formalEmitter`, `SignedResultCertificate.certifyH100FormalPtxConstantOne` | [`RegisteredH100FormalPtxPilot.lean`](../SparkInterval/Execution/RegisteredH100FormalPtxPilot.lean) |
| Registered shared Hurst V2 result | `checked_full_source_claims_of_local`, `checked_real_source_claims_of_local`, `hurstSharedFourResidualProductionV2_realClaims`, `SignedResultCertificate.certifyHurstSharedFourResidual`; primitive local rows reconstruct global prefixes, then five real inequalities follow from one exact successful full-range run | [`RegisteredAlgorithm.lean`](../SparkInterval/Execution/RegisteredAlgorithm.lean), [`RegisteredHurstSharedCertificate.lean`](../SparkInterval/Execution/RegisteredHurstSharedCertificate.lean), [`HurstSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/HurstSourceSemantics.lean) |
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
  Azure receipt or other accepted instance is supplied.
- “The pinned relying-party key signed this exact, independently appraised
  Azure receipt, and the reviewed Lean source registry contains its exact
  normalized claim,” only after independently auditing the appraisers,
  policies, key attestation, validity and replay checks, measured runner,
  signature, and generated registry diff.
- “Ordinary Lean reduction checked this source-admitted receipt's exact
  registry membership and structural statement binding; the sole execution
  axiom supplies this one run's `ProducedOutcome`,” when the generated
  `accepted` and `producedOutcome` theorems apply.
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
- that an Azure/AMD/NVIDIA token, TPM PCR extension, or HSM signature proves
  arbitrary user-space causality or mathematical soundness;
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
