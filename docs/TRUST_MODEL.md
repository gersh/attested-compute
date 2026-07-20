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
`sorry`, `admit`, `unsafe`, and every source `axiom` declaration except the
single external-run boundary
[`accepted_run_certificate_sound`](../SparkInterval/Execution/Trusted/RunCertificate.lean).
The DGX and H100 entry points are proved compatibility theorems that route
their policy-specific checks through this one axiom; they are not additional
postulates. `accepted_registered_run_sound` is likewise a proved projection of
the axiom's registered field, not another assumption.

[`tools/audit_axioms.sh`](../tools/audit_axioms.sh) also elaborates a file of
`#print axioms` commands for the public mathematical, certificate, compiler,
and machine theorems. It passes the captured output to
[`check_axiom_report.py`](../tools/check_axiom_report.py), which enforces both
the expected report counts and dependency allowlists:

- exactly 145 core reports, including the full-row endpoint bridge, resumable
  endpoint/chunk checkers, positive reflection, symmetric-count handoff,
  multiplicity-aware zeta count
  bridge, and 14 pinned-PTX-specification/refinement reports, and allowing only
  `propext`, `Classical.choice`, and `Quot.sound`;
- exactly 13 selected execution-bridge reports, allowing those foundations
  and only `accepted_run_certificate_sound` as a project axiom.

A missing or extra report and any dependency outside the relevant allowlist
fail the audit. The output remains useful as an inspectable record, but this
fixed public theorem surface is not dependent on human-only filtering.

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
`RegisteredInvocation.statementCheck` must bind all of those identities before
the registered projection of the trust boundary can be used.

The registry currently has one tutorial algorithm,
`RegisteredAlgorithm.cubicSumDivThreeV1`, and one invocation,
`RegisteredInvocation.cubicSumDivThree20000V1`. Its `Runs` relation refers to
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

`RunCertificate` contains the exact `RunStatement` and its private
`Attestation` capability. Its Boolean checker requires the selected policy to
match the algorithm ID/hash, input, parameters, domain, result and output hash,
nonce, target and trust profiles, artifact hashes, and successful completion;
local and mock evidence are rejected.

```lean
axiom accepted_run_certificate_sound
    {certificate : RunCertificate}
    (accepted : certificate.check = true) :
    certificate.ProducedOutcome
```

`ProducedOutcome` has two projections:

- `.historical` is the compatibility fact `AlgorithmReturned`, recording the
  exact returned bytes; and
- `.registered` says that every closed `RegisteredInvocation` whose complete
  `statementCheck` succeeds satisfies its fixed `Runs` relation on those bytes.

The derived theorem `accepted_registered_run_sound` exposes the second field
for one invocation. It is proved from `accepted_run_certificate_sound` and is
not a second trust assumption. A certificate whose statement matches no closed
invocation obtains no registered semantics. In particular, caller-selected
algorithm ID/hash literals are not a substitute for registry membership.

`checkDGXOperatorSignature` performs structural statement matching; it does
not implement Ed25519. Its positive evidence type has a private constructor.
The Python signature verifier exists, but a trusted importer that binds its
canonical output, verifier identity, pinned key, claim, and result to that
private Lean capability does not. `RunCertificate.check` accepts a DGX
certificate only when that policy check succeeds. The compatibility theorem
`dgx_operator_signed_run_sound` proves the old DGX-specific API from
`accepted_run_certificate_sound`; it introduces no second assumption. The
single execution axiom therefore describes the intended trust boundary but is
not currently consumable from a JSON sidecar by an end-to-end repository
command.

Using this mode trusts OpenSSL's Ed25519 implementation, private-key handling,
out-of-band public-key approval, replay-state durability, the importer when one
exists, and—through the single certificate axiom—the operator's truthfulness
about physical execution and the per-run connection to any matching closed
registry semantics.

[`SignedResultCertificate`](../SparkInterval/Execution/SignedResultCertificate.lean)
provides the downstream composition without adding another axiom. Its
`outcomeCheck` first requires unified run-certificate acceptance, then requires
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
`RegisteredInvocation.statementCheck` and exposes the invocation's fixed
`Runs` relation. Ordinary Lean theorems may then derive an application result.
The included `certifyCubicSumDivThree20000` theorem follows this route to the
exact value `13334666700000000`; its symbolic arithmetic proof has no
`native_decide` dependency. There is still no concrete signed wire artifact or
importer that discharges its accepted-certificate premise.

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

This composition cannot currently consume the repository's signed wire
artifacts. The Python verifier cannot construct the private Lean evidence
capability. The wire statement contains an output artifact reference rather
than result text, so a future importer must verify and read those exact bytes.
Moreover, the generated-cubin workflow returns `results.bin` and the zeta
workflow returns `zeta-report.json`; neither output is a canonical full result
certificate.

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
PTX-digest field. A future importer must use one hash convention consistently,
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
zeta program or invocation is present in the closed registry.

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

This preferred route is an interface, not a completed zeta verifier. The
registry currently contains no zeta checker, and the required registered
checker semantics and soundness theorem must incorporate the Hardy-Z endpoint,
streaming coverage, and total-count arguments. Neither a signature nor a
Merkle root supplies those mathematics.

No backend-conformance badge is inferred from these facts. In particular,
formal PTX arithmetic does not by itself prove `ptxas`/SASS/driver/hardware
refinement, and the division-capable zeta CUDA path is not identified with the
current polynomial typed-PTX whole-kernel theorem.

## H100 confidential-computing records

The repository can cross-build `compute_90` PTX and `sm_90` cubins and exercise
mock/policy rejection paths. Those artifacts do not show that an H100 was
queried or executed. The included hardware-acceptance provider is a
fail-closed stub.

The intended production workflow would need a measured workload that binds a
fresh verifier nonce, exact runner and device image, algorithm identity,
inputs, parameters, coverage, output, result, and successful completion. A
trusted verifier would also have to validate CPU-TEE and GPU confidential-
computing evidence, certificate chains, TCB policy, debug-disabled state,
measurements, freshness, and report-data binding.

H100 uses the same sole run-certificate axiom shown above. The retained
H100-specific public theorem is only a compatibility wrapper:

```lean
theorem h100_attested_run_sound
    {statement : RunStatement} {attestation : Attestation}
    (accepted : checkH100Attestation statement attestation = true) :
    AlgorithmReturned statement statement.result
```

`checkH100Attestation` is structural policy matching, not a cryptographic
verifier. `H100HardwareEvidence` has a private constructor, but the repository
includes neither a production NVIDIA evidence verifier nor a positive Lean
importer that can construct it. Local and mock evidence reduce to rejection.
No accepted H100 instance exists in this repository. If its premise eventually
becomes available, the wrapper derives its result through
`accepted_run_certificate_sound`; it adds no H100-specific axiom.

A future accepted premise would supply both the historical return and the
fixed `Runs` relation for any closed invocation whose complete statement check
succeeds. The latter is the explicitly trusted per-run physical-to-formal
bridge. It would not by itself prove that the registered algorithm is
mathematically sound, register an arbitrary H100 workload, or establish a
universal PTX/cubin/driver/hardware refinement. Those require a reviewed closed
registry entry and ordinary parsing and soundness theorems.

## Trust summary

| Path | Mathematical trust | Execution/provenance trust |
| --- | --- | --- |
| Full Lean certificate | Lean kernel and disclosed theorem dependencies; native reflection only where reported | None needed for the checked predicate |
| Generated typed-machine theorem | Lean kernel and formal model | Does not establish physical execution |
| Unsigned DGX bundle | None supplied by bundle | Host, artifact collection, and all supplied bytes |
| Operator-signed DGX bundle | None supplied by signature; a matching closed registry entry plus its proved soundness theorem can derive mathematics only after the unified axiom is assumed | Ed25519 stack, key approval/custody, replay state; operator truth and the per-run registry bridge only through the unified certificate axiom |
| Offline H100 artifacts | None supplied by build artifact | Toolchain generated the supplied files; no H100 claim |
| Future accepted H100 record | Closed registration and a separate algorithm-soundness theorem still required | Attestation roots/verifier, TCB policy, measured workload, firmware/hardware, importer, and the same unified certificate axiom |

See [Verifier guide](VERIFYING.md) for commands and acceptable claim language.
