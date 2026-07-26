# Trust model

SparkInterval treats these as independent questions:

1. Does a mathematical algorithm enclose the intended exact value?
2. Does a supplied result witness imply a stated theorem?
3. Does modeled generated code implement the modeled algorithm?
4. Does an accepted statement match a member of the closed formal algorithm
   and invocation registry?
5. Did a particular physical system execute particular bytes and return a
   particular result?

Lean proofs answer the first four only within their stated formal models. A run
bundle or signature addresses provenance and integrity, not mathematical
soundness. The sole accepted-run axiom is the explicit per-run bridge from
accepted external evidence to the fixed registry semantics; it is not a
universal backend theorem. The [correctness matrix](CORRECTNESS_CLAIMS.md)
gives the supported combinations.

## Lean proof dependencies

The automatic source audit scans the Lean library and generator. It rejects
`sorry`, `admit`, `unsafe`, every `constant` declaration, and every source
`axiom` declaration except the single external-run boundary
[`accepted_run_certificate_sound`](../SparkInterval/Execution/Trusted/RunCertificate.lean).
Its premise is the exact source-admitted `checkTrustedCompute` policy. The
legacy DGX and H100 structural checks are diagnostics that
`RunCertificate.check` rejects, so neither can reach this axiom.
`accepted_registered_run_sound` is a proved projection of the axiom's
registered field, not another assumption.

[`tools/audit_axioms.sh`](../tools/audit_axioms.sh) also elaborates a file of
`#print axioms` commands for the public mathematical, certificate, compiler,
and machine theorems. It passes the captured output to
[`check_axiom_report.py`](../tools/check_axiom_report.py), which enforces both
the expected report counts and dependency allowlists:

- exactly 159 core reports, including the full-row endpoint bridge, resumable
  endpoint/chunk checkers, positive reflection, symmetric-count handoff,
  multiplicity-aware zeta count
  bridge, and 14 pinned-PTX-specification/refinement reports, and allowing only
  `propext`, `Classical.choice`, and `Quot.sound`;
- exactly 16 selected execution-bridge reports, allowing those foundations
  and only `accepted_run_certificate_sound` as a project axiom.

A missing or extra report and any dependency outside the relevant allowlist
fail the audit. The output remains useful as an inspectable record, but this
fixed public theorem surface is not dependent on human-only filtering.

### Concrete trusted-compute receipt dependencies

`#print axioms` exposes the one generic execution axiom, but it cannot say at
which signed receipt a downstream proof instantiated that axiom. Import
[`SparkInterval.Audit.TrustedComputeCertificates`](../SparkInterval/Audit/TrustedComputeCertificates.lean)
to add a proof-term audit for that question:

```lean
#print certificates SomeNamespace.someTheorem
#audit certificates SomeNamespace.someTheorem
```

Both commands traverse the theorem's elaborated, transitive proof dependencies
rather than grepping source text. `#print certificates` always prints the
diagnostic report. For each concrete use it prints the literal lowercase
SHA-256 receipt digest, the declaration containing the receipt wrapper, and
the dependency path from the requested theorem to that wrapper. Stable
`certificate-use-v1|...` and `certificate-audit-v1|...` lines are included for
CI parsers. The summary status has these meanings:

- `AXIOM_FREE`: the trusted-run axiom is not reachable;
- `COVERED`: every path to the trusted-run axiom passes through a closed
  receipt wrapper with a literal canonical SHA-256 digest;
- `FAIL_UNATTRIBUTED`: some path reaches the trusted-run axiom without such a
  concrete wrapper, or the wrapper's hash is nonliteral, noncanonical, or
  contains local variables; and
- `FAIL_UNEXPECTED_AXIOMS`: the complete root-axiom set contains anything
  besides `propext`, `Classical.choice`, `Quot.sound`, and the disclosed
  trusted-run axiom.

`#audit certificates` prints the same report but raises an elaboration error
for either failing status. Thus a correctly attributed receipt cannot conceal
an unrelated helper axiom, `sorryAx`, or `Lean.ofReduceBool`. Generic
conditional bridge theorems legitimately report `FAIL_UNATTRIBUTED`: they
have not asserted that any concrete receipt exists. They remain useful APIs,
but must not be presented as accepted-run results. A generated concrete
consumer instead crosses the boundary with
`acceptedRunCertificateForReceipt`; its equality premise is kernel checked and
binds the displayed literal digest to the digest in the certificate's
`.trustedCompute` attestation. This wrapper is an ordinary theorem proved from
`accepted_run_certificate_sound`, not a second axiom.

Project-wide discovery complements a known-root query:

```lean
#print project certificates
#audit project certificates
```

It scans every declaration from loaded `SparkInterval.*` modules (and the
current module), emits one `project-certificate-use-v1` record per concrete
hash/anchor site, and ends with a stable `project-certificate-audit-v1`
summary containing unique-receipt and site counts. It also enumerates every
direct call to the sole axiom against a closed reviewed list. The audit fails
for malformed wrapper sites, unreviewed direct callers, uncovered concrete
anchors, or unexpected project axioms. An empty receipt registry and zero
concrete sites pass.

The companion command

```lean
#audit project axioms
```

examines actual axiom declarations in the loaded Lean environment, including
declarations written as `constant` or produced by elaborators, and fails
unless the one named trusted-run axiom is the only project axiom. Both project
commands are limited to the imported environment. The repository gate invokes
the certificate audit through the aggregate `SparkInterval.Execution` import
in `SparkInterval/Tests/ProjectCertificateAudit.lean`; the whole-tree source
audit remains a separate required check.

This visibility mechanism does not validate Azure/NVIDIA evidence or an RSA
signature inside Lean. An approved source-registry entry is the external fact
consumed by the sole axiom, so authority to edit or admit entries in
[`TrustedComputeRegistry.lean`](../SparkInterval/Execution/TrustedComputeRegistry.lean)
is trust-equivalent at this boundary to asserting that those receipts are
valid. Generator checks, signature appraisal, code review, and exact hash
output make that decision auditable; they do not turn it into a kernel proof.
The tracked live registry is empty, so there is currently no `COVERED`
production receipt theorem in the repository.

### Compact-registry attack audit

The compact architecture projection narrows the call-site attack surface in
several kernel-visible ways:

- the accepted certificate's own `.trustedCompute receiptHash` branch supplies
  both `statement` and `receiptHash`;
- `RegisteredArchitectureInvocation` is a closed inductive, and
  `reviewedRun` is a closed source definition rather than a caller argument;
- `ReceiptSelected` requires equality with that installed record and binds
  every field of `RunStatement`; and
- neither `RegisteredArchitectureOutcomes` nor `PhysicalOutcome` accepts a
  caller-provided proposition, measurement scheme, machine, entry point, pin
  bundle, executable, or result.

The lightweight regression
[`CompactArchitectureAttackSurfaceTest.lean`](../SparkInterval/Tests/CompactArchitectureAttackSurfaceTest.lean)
proves that, within one invocation, two successful selections necessarily use
the same receipt hash and the same complete statement. The public constructor
of `RegisteredArchitectureOutcomes` is not an authority token by itself:
extracting a `PhysicalOutcome` still requires `ReceiptSelected`. With every
current `reviewedRun` branch equal to `none`, that premise is impossible.
Each reviewed algorithm ID is additionally required to equal the closed
constructor's injective `invocationId`;
`invocation_eq_of_receiptSelected` therefore proves that one complete
statement cannot be aliased across two invocation constructors.

These facts do **not** make registry installation untrusted:

- editing `TrustedComputeRegistry.lean` or changing a `reviewedRun` branch to
  `some` remains trust-equivalent to extending the sole axiom's usable
  instances;
- Lean does not verify the external RSA signature, freshness, certificate
  chains, confidential-compute appraisal, or cryptographic collision and
  second-preimage assumptions;
- `ArchitectureSemantics` is structurally generic. A reviewed installation
  must select the exact formal CPU/GPU model, not a permissive relation that
  embeds an application claim in `load`, `step`, or `haltedWith`;
- the registry prevents one statement from selecting two invocations, but a
  source reviewer must still ensure that each installed algorithm identifier
  names the intended measured program and not merely a unique label; and
- the historical `ProducedOutcome.registered` field is a broader
  application-semantic trust projection. It should be removed after all
  consumers have migrated to the compact architecture/refinement route.

The native-generated ternary-Goldbach dependencies now have one additional
closed constructor,
`nativeGeneratedAggregateProductionV1`. It is a confidential CPU finalizer
for a signed CPU/H100 child graph, not a proposition. All 15 families and all
1,371 generated roots route to that same physical identity through
`NativeFamilyArchitectureCatalog`. `NativeFamilyAggregateCapstone` can derive
a fixed decidable family bundle only when ordinary Lean is also given the
exact executable-to-checker refinement. The aggregate receipt alone proves
no mathematical claim, and its `reviewedRun` branch is currently `none`.
Ordinary compact certificate routes remain preferable because they exclude
the architecture and receipt boundary entirely.

For receipt visibility, `#audit certificates FinalTheorem` is the decisive
check on a named release theorem: it follows indirect dependencies and rejects
every path that reaches the axiom without a closed literal receipt wrapper.
`#audit project certificates` complements that query by inventorying concrete
wrapper sites and direct axiom callers in the loaded environment. It is not a
replacement for auditing each public root: a generic conditional theorem may
legitimately reach a reviewed bridge indirectly without naming a receipt, and
the project inventory does not reinterpret that conditional theorem as a
concrete run.

Lean foundations such as `propext`, `Classical.choice`, and `Quot.sound` can
appear in checked theorem dependencies. They are not project-specific physical
execution assumptions. Conversely, `native_decide` uses native proof
reflection and contributes its own axiom dependency. It is not an execution
attestation axiom, but a verification policy may still choose to forbid it.

The generated full-certificate modes expose this choice:

| Concrete generated theorem | Default `kernel` mode | Explicit `native` mode |
| --- | --- | --- |
| Direct materialized certificate, row bound, and finite-sum bound | `decide_cbv`; no `native_decide` dependency in the recorded theorem output | `native_decide` |
| Exact serialized JSON/parser/hash binding | `native_decide` | `native_decide` |

Generic certificate soundness theorems are independent of the concrete
reduction mode. A default direct typed-data theorem can therefore avoid
`native_decide`; the current generated proof of equality with the exact JSON
bytes cannot. Generated namespaces and receipts bind the selected mode so the
two dependency profiles cannot be confused. Witness-specific generated modules
are not among the fixed reports counted by `audit_axioms.sh`; they print their
own concrete theorem dependencies when compiled and those reports must be
retained and interpreted according to the selected mode.

Avoid the ambiguous phrase “axiom-free repository.” The precise statement is
that the source audit permits only the one named project execution axiom, and
that each public theorem's printed dependencies must be interpreted on its own.

## Mathematical result certificates

A full result certificate lets Lean independently decode every row and
reevaluate its expression with exact rational interval arithmetic. The generic
soundness result does not assume that a GPU ran. An untrusted producer may
generate the witness; if the checker proves the desired predicate, execution
provenance is unnecessary for that predicate.

This removes only the execution question. A certificate theorem proves exactly
its formal statement—currently row-wise containment or upper bounds and a
finite-sum upper bound. It does not automatically prove an analytic tail,
decode an application-specific report, or establish a theorem about zeta
zeros.

The compiled checker executable relies on the ordinary build/runtime toolchain
to report its Boolean result. A generated Lean module additionally asks Lean to
check concrete theorem declarations, with the proof dependencies disclosed
above.

## Generated-code model

The generated-code proof is a theorem about a typed polynomial AST and Lean's
one-thread machine semantics. It covers the instructions emitted by this
compiler, exact compiler structure and opcode order, deterministic text
rendering, modeled memory/control flow, output representation, and exact-real
containment under explicit hypotheses.

The pinned NVIDIA PTX 9.0 layer narrows one former gap without closing the
backend boundary. It records normative clause references for every allowlisted
opcode and proves that the model's finite-operand directed `add/sub/mul` and
non-NaN `min/max` steps agree with a Lean transcription of those clauses.
Correct transcription of NVIDIA's prose is externally reviewed, and clause
coverage is not a semantic theorem for the remaining instructions. There is
no whole-ISA or emitted-program refinement theorem.

The trusted computing base for interpreting an actual DGX run as an instance
of that theorem still includes:

- the reviewed prose-to-Lean transcription and all PTX behavior outside its
  finite/non-NaN arithmetic slice;
- the connection between complete emitted PTX instruction text and that
  partial formal semantics;
- `ptxas` translation and the relationship between PTX and SASS;
- the CUDA loader, driver, and scheduling behavior;
- GPU arithmetic, memory, and control-flow hardware;
- the host runner, operating system, storage, and artifact collection;
- the relevant hashing and serialization implementations.

Static PTX/SASS audits and differential tests provide useful evidence about
this boundary, but they are not refinement proofs. An independently checked
full result certificate can avoid relying on the boundary for its own
mathematical conclusion.

### Closed registered semantics

[`RegisteredAlgorithm`](../SparkInterval/Execution/RegisteredAlgorithm.lean)
is a closed inductive registry: callers cannot attach an arbitrary proposition
to a digest. Each constructor fixes its algorithm ID, canonical definition and
hash, parameter and domain encodings, parsers, and `Runs` relation.
`RegisteredInvocation` is also closed and fixes the canonical input.
`RegisteredInvocation.statementCheck` binds all of those identities, profiles,
artifact hashes, and the constructor's explicit canonical result language.
`RegisteredInvocation.certificateBindingCheck`
additionally binds the exact reviewed source-admitted receipt before the
registered projection of the trust boundary can be used.
Three source-checked maintenance theorems harden registry extension:
`statementCheck_unique` makes one statement select at most one constructor,
`resultAllowed_of_runs` proves that every legitimate `Runs` output is admitted
by the result guard, and `runs_satisfiable` gives each constructor at least one
safe output witness. For source computations that witness is the explicit
`false` branch; it does not establish success-branch consistency or evidence
that a physical run occurred. Successful source evidence remains deliberately
inside the disclosed per-run trust boundary.

The reviewed algorithm hash commits the canonical definition bytes named by
the receipt; Lean does not prove that this prose serialization is a
cryptographic serialization of the kernel expression defining `Runs`.
`RegisteredAlgorithm.lean` and every downstream theorem remain ordinary
trusted Lean source. A change to a `Runs` body therefore requires source
review, a fresh build, and a fresh axiom audit even if a maintainer neglected
to change the prose hash. This is a source-review boundary, not an input
available to an untrusted receipt.

The registry includes the CPU
`RegisteredInvocation.cubicSumDivThree20000V1` tutorial, the one-row H100
`RegisteredInvocation.h100FormalPtxConstantOneV1` pilot, and closed
invocations for the named ternary-Goldbach campaigns. The cubic `Runs`
relation refers to
the executable `cubicSumDivThreeMachine`: an integer `cubicNumeratorLoop`
accumulates the cubes from zero through 20,000 and the machine divides the
numerator once by three. It is not merely a name for the rational conclusion.

The separate, axiom-free algorithm layer proves symbolically that the machine
returns `13334666700000000`, that its natural-number result agrees at this
bound with

```text
sum (x = 0 .. 20000) (x^3 / 3) = 13334666700000000
```

over the rationals, and that every cube operand, accumulator value, and
accumulator addition fits in an unsigned 64-bit word. These results use neither
`native_decide` nor a 20,001-row witness.
`certifyCubicSumDivThree20000` recovers that equality and the exact canonical
output from an accepted, registry-bound result certificate.

The H100 pilot's `Runs` relation fixes the exact canonical input and compact
output. In a separate axiom-free module, Lean proves its registered PTX bytes
are exactly `renderUncheckedFor .sm90 (buildModule batch)` for the closed
constant `[1,1]` batch and proves both returned endpoint words decode to one.
Its end-to-end theorem remains conditional on an accepted, registry-bound
receipt; the tracked receipt registry is empty.

Every nontrivial ternary-Goldbach invocation now additionally requires a
`ReviewedProductionDeployment`; the two finite-Goldbach invocations also
require their transitive terminal-artifact pin bundles. These source values
are deliberately `none` before a real run. A reviewed installation fixes the
exact admitted receipt, host executable, device binary (or the CPU
not-applicable digest), terminal/runtime-closure manifest, and
target/trust-profile digests. Consequently neither a different build nor a
different admitted receipt with otherwise matching logical metadata can
satisfy `RegisteredInvocation.certificateBindingCheck`.

Lean compares the profile and artifact tuple in `statementCheck` and the
receipt hash in `receiptCheck`. The exact source-registry entry for that
receipt is the single authoritative Lean representation of its wire
statement, run bundle, verifier policy/artifact, platform evidence, challenge,
and result-binding digests; `checkTrustedCompute` verifies those fields.
Installing any deployment option is therefore a trust-boundary source change
and requires the same review as adding the corresponding imported receipt.
`tools/generate_production_deployment_candidate.py` verifies the signed
production receipt and prints the exact Lean candidate plus the registry,
wire-statement, run-bundle, verifier-policy, and verifier-artifact identities.
It never edits the pin source; installation remains an explicit human-reviewed
change.

This closed formal meaning does not itself establish physical execution. For
one accepted certificate, the sole axiom deliberately trusts the importer,
evidence policy, artifact measurements, compilation/backend behavior, physical
execution, and relevant digest security strongly enough to supply the matching
`Runs` fact. That is a per-run trust decision. It does not prove that arbitrary
PTX, cubins, drivers, or later executions refine the registry semantics. The
u64 bounds likewise prove safety of the specified loop arithmetic, not that a
GPU executable contains or correctly implements those operations.

## DGX local records

DGX Spark records use `local_unattested` evidence and
`hardware_attestation: null`. Their hashes detect modification relative to the
supplied bundle and artifacts. A malicious host can fabricate all of those
bytes, so an unsigned record does not establish physical execution.

Freshness also requires an external challenger. A nonce generated only by the
prover is a uniqueness field; a verifier-issued nonce plus durable replay state
supports an anti-replay claim.

### Operator-signed DGX records

The optional Ed25519 sidecar signs a domain-separated payload that binds the
exact canonical bundle bytes and statement. Verification requires all artifact
bytes, a separately pinned public key, and persistent replay state. Trusting
only the key embedded in the sidecar proves no operator identity.

A successful signature check proves that the pinned key signed the record. It
does not prove that the record is true, that the key was isolated, or that a
GPU ran. The inner evidence remains `local_unattested`, and verification
reports `hardware_evidence: false`.

Lean makes the additional truthfulness decision explicit through the same
certificate type used by every production evidence policy:

`RunCertificate` contains the exact `RunStatement` and its `Attestation`.
Its Boolean checker accepts only `.trustedCompute receiptHash`: it looks up an
exact source-admitted receipt and checks the algorithm ID/hash, input,
parameters, domain, result and output hash, recomputes the result bytes'
SHA-256 and the challenge/statement result-binding digest, and checks the
nonce, target and trust profiles, artifact hashes, backend, verifier
key/profile tuple, and successful completion. Local, mock, legacy
DGX-signature, and legacy H100 evidence are rejected.

```lean
axiom accepted_run_certificate_sound
    {certificate : RunCertificate}
    (accepted : checkTrustedCompute certificate.statement
      certificate.attestation = true) :
    certificate.ProducedOutcome
```

The closed invocation selector also recomputes, in Lean, the SHA-256 of each
constructor's canonical algorithm definition, input, parameter, and domain
bytes before it can expose `Runs`. These checks are in addition to the
importer's preimage checks. A stale reviewed digest literal therefore disables
the invocation instead of allowing an old receipt to acquire edited formal
semantics. Production selectors test their post-run deployment pin first, so
an unconfigured invocation fails without evaluating the diagnostic hashes.

The strength of the registered projection is exactly the constructor's
source-visible `Runs` relation; attestation does not make that relation a
kernel proof. The current constructors fall into three review classes:

- the cubic tutorial and constant-one PTX pilot have small closed results whose
  arithmetic interpretation is proved directly in Lean;
- CDEM V2, Hurst V2, and the two Goldbach routes use exact finite
  source-realization propositions plus ordinary Lean soundness theorems; and
- the psi, R2-star, Proposition 12.2.4, A.7, Platt-head, Dirichlet, and PT21
  routes additionally carry analytic numerical realization fields such as
  directed logarithm/MPFR/Arb enclosure, Hardy-function identity, or
  Turing/argument-principle counts.

In the last class those fields remain part of the disclosed per-run trust
boundary until they are replaced by proof-carrying artifacts checked by
ordinary Lean. A secure-enclave signature authenticates the reviewed run; it
does not independently prove these analytic refinements. Every nontrivial
production deployment option is currently `none`, so none of these source
relations can yet be selected by a receipt.

`ProducedOutcome` has three projections:

- `.historical` is the compatibility fact `AlgorithmReturned`, recording the
  exact returned bytes; and
- `.registeredArchitecture` matches on the certificate's attestation and, for
  `.trustedCompute receiptHash`, returns
  `RegisteredArchitectureOutcomes certificate.statement receiptHash`; and
- `.registered` says that every closed `RegisteredInvocation` whose complete
  `certificateBindingCheck` succeeds satisfies its fixed `Runs` relation on
  those bytes. This includes the exact reviewed receipt check for production
  invocations.

The derived theorems `accepted_registered_architecture_outcomes` and
`accepted_registered_run_sound` expose the two closed projections. Both are
proved from `accepted_run_certificate_sound` and neither is a second trust
assumption. The architecture theorem takes an accepted
`.trustedCompute receiptHash` envelope directly, so a caller cannot substitute
a different hash, formal machine, measurement scheme, pin bundle, entry point,
or claim. A certificate whose statement matches no closed invocation obtains
no registered semantics. In particular, caller-selected algorithm ID/hash
literals are not a substitute for registry membership.

### Narrow architecture-execution successor

[`ArchitectureExecution.lean`](../SparkInterval/Execution/ArchitectureExecution.lean)
defines the intended replacement for the high-level `.registered` projection.
It retains the exact executable, input, and output bytes with their lengths and
digests, then describes execution as a formal architecture load, a finite
instruction-step trace, and an exact halted output. A separate ordinary Lean
theorem, `ArchitectureRefinesNativeChecker`, must connect one exact executable
and entry point to the application checker. The receipt token contains only
the architecture-execution proposition.

This lets the large computation and its independent replay remain in Azure.
An ordinary local theorem application need not contain or evaluate the long
trace: the single axiom now supplies that proposition opaquely for one closed,
reviewed receipt through `.registeredArchitecture`. Local Lean checks the reusable
architecture-to-checker and checker-to-mathematics proofs.

The new interface is part of the production trust-boundary signature, but no
reviewed production architecture registration is installed yet. In particular:

- no reviewed x86-64 ELF/loader/ABI or H100 cubin/SASS semantics instance is
  installed;
- no theorem yet connects a measured Sqrt218 executable to its native checker
  model; and
- the high-level `.registered` compatibility field remains in
  `ProducedOutcome` until existing consumers migrate to ordinary refinement
  from the low-level architecture fact.

The future trusted entry point must select a closed measurement scheme and
architecture model. Quantifying over a caller-selected machine semantics
would be unsound because the caller could choose an execution relation that
accepts every byte string. See the
[architecture-boundary design](ARCHITECTURE_EXECUTION_BOUNDARY.md).

`checkDGXOperatorSignature` performs structural statement matching; it does
not implement Ed25519. The Python signature verifier exists, but its result is
not an execution fact in Lean. `RunCertificate.check` unconditionally rejects
`.dgxOperatorSignature`, even when that diagnostic succeeds, and
`dgx_operator_signature_not_admitted` proves this fail-closed relationship.
There is no DGX theorem-producing importer or DGX-specific route to
`accepted_run_certificate_sound`.

Using the DGX signature verifier as provenance evidence trusts OpenSSL's
Ed25519 implementation, private-key handling, out-of-band public-key approval,
and replay-state durability. It still supplies no Lean theorem authority and
no per-run connection to closed registry semantics.

[`SignedResultCertificate`](../SparkInterval/Execution/SignedResultCertificate.lean)
provides the downstream composition without adding another axiom. Its
`outcomeCheck` first requires source-admitted trusted-compute acceptance, then requires
the exact returned text to equal the full certificate text and recomputes that
text's SHA-256 digest before comparing it with the statement's output hash.
[`outcomeCheck_sound`](../SparkInterval/Execution/SignedResultCertificateComposition.lean)
therefore proves the exact historical proposition that this named, accepted
run returned these certificate bytes. The upper-bound soundness theorems
additionally package:

- the stronger `ProducedOutcome`, obtained only from
  `accepted_run_certificate_sound`, together with its historical projection;
- the two proved result-binding equalities; and
- independently checked row-wise or finite-sum certificate mathematics.

The last item does not follow from `AlgorithmReturned`, and this generic full-
certificate path does not use the registered projection to prove it.
Conversely, the certificate checker does not prove that a GPU ran. The generic
composition theorems require no `native_decide`, although a witness-specific
proof of their Boolean premise may choose a reduction mode with additional
dependencies.

`outcomeCheckForRegisteredInvocation_sound` is the preferred execution-to-
semantics handoff. It combines exact result binding with
`RegisteredInvocation.certificateBindingCheck` and exposes the invocation's
fixed `Runs` relation. Ordinary Lean theorems may then derive an application
result.
The included `certifyCubicSumDivThree20000` theorem follows this route to the
exact value `13334666700000000`; its symbolic arithmetic proof has no
`native_decide` dependency. There is still no concrete admitted receipt that
discharges its accepted-certificate premise. The Azure trusted-compute
importer described below can produce such a premise only after a genuine
matching Azure run and a reviewed source-registry admission.

The generic mathematical handoffs `checkUpperBoundForAlgorithm_sound` and
`checkSumUpperBoundForAlgorithm_sound` additionally prove literal equality of
the signed statement's `algorithmId` and `algorithmHash` with an
`ExpectedExecutableIdentity` supplied by the application theorem. Those
equalities prevent silently accepting a different statement identity; by
themselves they do not establish where the expected digest came from or
identify it with a formal compiler/module.

For an outcome-only handoff, `outcomeCheckForAlgorithm_sound` combines those
literal identity pins with `outcomeCheck_sound`. This remains a statement about
one historical run. It is not a universal or counterfactual theorem saying
that every future execution of the named algorithm, or merely “running this
computation” without an accepted certificate, must return the same bytes. Such
a claim would require a formal deterministic execution semantics and a proof
that the pinned executable implements it.

For a closed registered invocation, the formal deterministic semantics is
fixed and the accepted certificate supplies one `Runs` fact. That stronger
per-run fact still does not assert that an unaccepted future physical execution
implements the semantics or returns the same bytes.

This composition cannot consume the repository's existing DGX signature
sidecars. The Azure receipt importer is a separate path that verifies and reads
the exact output artifact before committing its UTF-8 contents to a source
registry entry. The generated-cubin workflow returns `results.bin` and the
zeta workflow returns `zeta-report.json`; neither output is a canonical full
result certificate accepted by `SignedResultCertificate` without an
application-specific encoding and proof.

The dedicated `FormalPTXProgram` handoff is stronger than that generic literal
check for the existing typed generator. It reparses the exact canonical input
into the formal `ReferenceBatch`, validates and emits `buildModule` for the
selected target, and recomputes the emitted-PTX, canonical-input,
canonical-parameter, and canonical-domain hashes. It also requires exact
equality of the statement target, target-profile hash, and complete artifact
hash record. `outcomeCheckForFormalPTX_sound` composes this identity result with
the same historical-outcome axiom and returned-text binding.

That theorem does not prove that a bound artifact has the claimed digest or
that the named cubin was compiled from the formal PTX. Current generated-cubin
bundles use the cubin digest as `algorithmHash`, whereas the formal-PTX handoff
requires `algorithmHash` to be the emitted-PTX digest. Although the wire bundle
retains a `gpu_ptx` build artifact, the Lean `ArtifactHashes` projection has no
PTX-digest field. Any receipt admission must use one hash convention consistently,
verify every named artifact externally, and preserve the separately bound
device-cubin identity. Equating the cubin digest with the formal emitted-PTX
digest would be incorrect.

The zeta-specific handoff does not widen this trust boundary.
`SignedZetaEndpointPayload.payloadCheck` canonically parses the returned full
certificate, requires exact typed equality, independently checks every
arithmetic row, enforces the paired singleton/finite endpoint shape, and checks
the rational family signs and adjacent ordering. Its combined check also
requires the parser-recomputed embedded batch digest to equal both the run
statement's input digest and the digest of `FormalPTXProgram.canonicalInput`.
Its `check_sound` result packages those pure facts and exact batch equalities
beside `CertifiedFormalPTXOutcome`. Its `ProducedOutcome` comes from
`accepted_run_certificate_sound`; parsing, hash/text equality, arithmetic,
shape, and family validity do not. The current zeta composition uses the
historical/FormalPTX branch and independently proved analytic premises. No
zeta program or invocation is present in the closed algorithm registry.

`SignedZetaEndpointPayload.verifyFiniteHeight` makes the remaining mathematical
authority visible in its arguments: a proved `HardyZModel`, endpoint-enclosure
and domain proofs, and `ZetaMultiplicityCountUpperBound`. The mathematical
field of `CertifiedZetaVerification` follows from those premises and ordinary
Lean theorems, not from the registered field. The axiom does not prove that the
checked intervals enclose Hardy Z or that a Turing or argument-principle count
is correct.

For a proved even evaluator,
`verifyFiniteHeightFromPositiveRows` reflects the valid positive bracket family
in reverse order and reuses its enclosures on the negative side. This reduces
the signed endpoint data from four arithmetic rows per positive zero to two;
the evaluator-evenness, zeta conjugation/multiplicity symmetry, and
no-real-axis-zero facts remain explicit premises.

[`CompactAttestedVerifier.lean`](../SparkInterval/Execution/CompactAttestedVerifier.lean)
now exposes two small-download architectures. The older generic FormalPTX
theorem `certifyCompactFiniteHeightZeta` retains the explicit
`ExecutionRefines` and verifier-soundness premises. The preferred closed-
registry theorem `certifyRegisteredCompactFiniteHeightZeta` needs no separate
physical-refinement premise: the sole axiom supplies the matching invocation's
per-run `Runs` relation, and an ordinary `verifierSound` theorem derives the
finite-height claim from it.

This preferred route is still not a completed zeta verifier. The registry now
contains an exact PT21 finite-RH invocation and a sound source-claim theorem,
but a successful `Runs` proof requires explicit chunked endpoint, Hardy-Z and
total-count evidence. No materializer, completed source-scale run or attested
receipt supplies that evidence yet. Neither a signature nor a Merkle root
supplies those mathematics.

No backend-conformance badge is inferred from these facts. In particular,
formal PTX arithmetic does not by itself prove `ptxas`/SASS/driver/hardware
refinement, and the division-capable zeta CUDA path is not identified with the
current polynomial typed-PTX whole-kernel theorem.

## Azure confidential CPU and H100 records

The repository implements a fail-closed path for two exact backends:

- `azure_sevsnp_cpu`, for CPU/FLINT/Arb jobs in a reviewed Azure AMD SEV-SNP
  confidential VM; and
- `azure_ncc40ads_h100_v5`, for one NVIDIA H100 plus the Azure SEV-SNP/vTPM
  host boundary.

The path creates fresh challenges off-VM, deploys reviewed exact VM profiles,
collects statement- and output-bound evidence, independently appraises it,
issues an RSA-3072-signed compact receipt, verifies that receipt through a
source-pinned public-key plus exact backend/workload-profile/appraiser/policy
tuple manifest, atomically
burns each retained challenge in a required replay ledger, and generates a
closed Lean source-registry entry. A generated Lean consumer then checks exact
receipt lookup and complete
statement binding with ordinary kernel reduction. It uses neither FFI,
`native_decide`, nor a second cryptographic axiom.

For large referenced inputs, the exact canonical numeric-corpus pin can be
the measured job input. Receipt issuance with
`--require-numeric-corpus-input` then checks that the signed
`claim.input_hash` is exactly the SHA-256 of that pin. The pin in turn binds
the source-shaped claim ID and statement, immutable manifest/commit, payload
root, source root, individual file hashes, and logical ranges. This is a
transitive cryptographic identity binding, not a claim that the workload used
every row or that the rows imply the theorem. Those facts remain in the
closed registered execution semantics and its ordinary soundness theorem.
See [Pinned numeric-corpus references](NUMERIC_CORPUS_REFERENCES.md).

The tracked
[`TrustedComputeRegistry.lean`](../SparkInterval/Execution/TrustedComputeRegistry.lean)
contains an empty list. The only checked-in verifier key is explicitly
development-only. Diagnostic import requires `--allow-development-key`, while
Lean theorem admission rejects development classification unconditionally.
Thus no production Azure CPU or H100 run currently reaches an accepted Lean
premise.

A production admission requires all of the following external work and
review:

- Azure credentials, quota and physical capacity, and an actual confidential
  run under the exact reviewed target profile;
- a separately installed, hash-pinned Azure MAA/SEV-SNP/vTPM appraiser and
  policy, plus a pinned NVIDIA `nvattest` appraiser and policy for H100;
- full certificate-chain, revocation, TCB, secure-boot, debug-disabled,
  validity-window, challenge, TPM quote/PCR/event-log, and CPU/GPU binding
  checks;
- a measured immutable runner and executable closure, for example a reviewed
  image with dm-verity/IMA or an equivalent policy;
- an Azure Managed HSM production signing key, its immutable versioned key
  URI, a pinned public key, and independent review of the HSM key-attestation
  evidence; and
- one shared durable issuer replay database (failed attempts remain spent),
  plus source review of the exact key/backend/target-profile/trust-profile/
  verifier/policy tuple and the generated registry diff.

The [Managed HSM signing guide](AZURE_MANAGED_HSM_SIGNING.md) gives the key
provisioning, immutable-version pinning, receipt-signing, and audit procedure.

There are two different signatures in this path. The Azure vTPM AK quote is
the enclave-associated signature for the individual run: its qualifying data
is the fresh challenge-and-statement result binding, and its signed PCR 23
state commits to the ordered pre-run and post-run extensions. The Managed HSM
signature is a relying-party countersignature over the independently
appraised quote/evidence roots and the closed claim. It cannot replace the AK
quote. A separately generated ephemeral guest key would not improve this
boundary unless it were attested and access-controlled at least as strongly
as the certified AK.

The evidence collector is not an appraiser, and a successful appraiser is not
a program proof. In particular, extending PCR 23 with a result binding shows
that the vTPM signed that transition. Without a measured runner it does not
show that arbitrary user-space code caused the output. Even complete platform
attestation does not establish the finite algorithm's mathematics.

The source registry is the Lean capability. Editing it is security-equivalent
to changing the disclosed external-execution boundary and must receive the
same review. The external generator verifies the canonical signed receipt,
current validity window, backend separation, evidence and bundle bindings,
and duplicate receipt/run/challenge identities before emitting source. Lean
then trusts no runtime verifier boolean: it checks literal registry membership
and structural equality.

Both CPU and H100 records use the same sole trusted-compute axiom shown above.
The legacy `checkH100Attestation` entry point remains a structural diagnostic,
not a cryptographic verifier. `RunCertificate.check` rejects its
`.h100Hardware` constructor even when the diagnostic succeeds, and
`h100_attestation_not_admitted` proves that it cannot reach the execution
axiom. The authoritative `checkTrustedCompute` path accepts only an exact
source-admitted receipt and keeps CPU and composite-H100 target/trust classes
separate. Any accepted premise derives its result through
`accepted_run_certificate_sound`; there is no CPU- or H100-specific axiom.

An accepted receipt supplies both its exact historical return and the fixed
`Runs` relation for any closed invocation whose complete statement check
succeeds. The latter is the explicitly trusted per-run physical-to-formal
bridge. It does not prove that the registered algorithm is mathematically
sound, let a receipt register an arbitrary workload or proposition, or
establish universal PTX/cubin/driver/hardware refinement. Those require a
closed algorithm/invocation constructor and ordinary parsing and soundness
theorems.

## Trust summary

| Path | Mathematical trust | Execution/provenance trust |
| --- | --- | --- |
| Full Lean certificate | Lean kernel and disclosed theorem dependencies; native reflection only where reported | None needed for the checked predicate |
| Generated typed-machine theorem | Lean kernel and formal model | Does not establish physical execution |
| Unsigned DGX bundle | None supplied by bundle | Host, artifact collection, and all supplied bytes |
| Operator-signed DGX bundle | None supplied by signature; the legacy structural check is rejected by `RunCertificate.check` and cannot derive mathematics | Ed25519 stack, key approval/custody, and replay state only; no Lean execution/provenance authority |
| Offline H100 artifacts | None supplied by build artifact | Toolchain generated the supplied files; no H100 claim |
| Source-admitted Azure CPU receipt | Closed registration and a separate algorithm-soundness theorem still required | Azure/AMD/vTPM roots and appraiser, TCB and measured-runner policy, HSM key review, source-registry review, and the same unified certificate axiom |
| Source-admitted Azure NCC H100 receipt | Closed registration and a separate algorithm-soundness theorem still required | All CPU-route trust plus NVIDIA roots/RIM/revocation/appraiser, firmware/GPU, PTX/cubin/runtime boundary, registry review, and the same unified certificate axiom |

See [Verifier guide](VERIFYING.md) for commands and acceptable claim language.
