# Trust model

SparkInterval treats these as independent questions:

1. Does a mathematical algorithm enclose the intended exact value?
2. Does a supplied result witness imply a stated theorem?
3. Does modeled generated code implement the modeled algorithm?
4. Did a particular physical system execute particular bytes and return a
   particular result?

Lean proofs answer the first three only within their stated formal models. A
run bundle or signature addresses provenance and integrity, not mathematical
soundness. The [correctness matrix](CORRECTNESS_CLAIMS.md) gives the supported
combinations.

## Lean proof dependencies

The automatic source audit scans the Lean library and generator. It rejects
`sorry`, `admit`, `unsafe`, and all source `axiom` declarations except:

- [`dgx_operator_signed_run_sound`](../SparkInterval/Execution/Trusted/DGXOperatorSignature.lean#L24);
- [`h100_attested_run_sound`](../SparkInterval/Execution/Trusted/H100Attestation.lean#L27).

[`tools/audit_axioms.sh`](../tools/audit_axioms.sh) also elaborates a file of
`#print axioms` commands for the public mathematical, certificate, compiler,
and machine theorems. It passes the captured output to
[`check_axiom_report.py`](../tools/check_axiom_report.py), which enforces both
the expected report counts and dependency allowlists:

- exactly 84 core reports, allowing only `propext`, `Classical.choice`, and
  `Quot.sound`;
- exactly two execution-bridge reports, allowing those foundations and the two
  named execution axioms.

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
that the source audit permits only the two named project execution axioms, and
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

The trusted computing base for interpreting an actual DGX run as an instance
of that theorem still includes:

- the connection between emitted PTX text and NVIDIA PTX semantics;
- `ptxas` translation and the relationship between PTX and SASS;
- the CUDA loader, driver, and scheduling behavior;
- GPU arithmetic, memory, and control-flow hardware;
- the host runner, operating system, storage, and artifact collection;
- the relevant hashing and serialization implementations.

Static PTX/SASS audits and differential tests provide useful evidence about
this boundary, but they are not refinement proofs. An independently checked
full result certificate can avoid relying on the boundary for its own
mathematical conclusion.

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

Lean makes the additional truthfulness decision explicit:

```lean
axiom dgx_operator_signed_run_sound
    {statement : RunStatement} {attestation : Attestation}
    (accepted : checkDGXOperatorSignature statement attestation = true) :
    AlgorithmReturned statement statement.result
```

`checkDGXOperatorSignature` performs structural statement matching; it does
not implement Ed25519. Its positive evidence type has a private constructor.
The Python signature verifier exists, but a trusted importer that binds its
canonical output, verifier identity, pinned key, claim, and result to that
private Lean capability does not. The execution axiom therefore describes the
intended trust boundary but is not currently consumable from a JSON sidecar by
an end-to-end repository command.

Using this mode trusts OpenSSL's Ed25519 implementation, private-key handling,
out-of-band public-key approval, replay-state durability, the importer when one
exists, and—through the named axiom—the operator's truthfulness about physical
execution.

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

Lean isolates the eventual physical claim in a second axiom:

```lean
axiom h100_attested_run_sound
    {statement : RunStatement} {attestation : Attestation}
    (accepted : checkH100Attestation statement attestation = true) :
    AlgorithmReturned statement statement.result
```

`checkH100Attestation` is structural policy matching, not a cryptographic
verifier. `H100HardwareEvidence` has a private constructor, but the repository
includes neither a production NVIDIA evidence verifier nor a positive Lean
importer that can construct it. Local and mock evidence reduce to rejection.
No accepted H100 instance exists in this repository.

A future accepted premise would prove only `AlgorithmReturned`: the named
algorithm returned the exact serialized result in the statement. It would not
prove that the algorithm is sound or give the result string mathematical
meaning. Those require separate formal identification, parsing, and soundness
theorems.

## Trust summary

| Path | Mathematical trust | Execution/provenance trust |
| --- | --- | --- |
| Full Lean certificate | Lean kernel and disclosed theorem dependencies; native reflection only where reported | None needed for the checked predicate |
| Generated typed-machine theorem | Lean kernel and formal model | Does not establish physical execution |
| Unsigned DGX bundle | None supplied by bundle | Host, artifact collection, and all supplied bytes |
| Operator-signed DGX bundle | None supplied by signature | Ed25519 stack, key approval/custody, replay state; operator truth only through explicit axiom |
| Offline H100 artifacts | None supplied by build artifact | Toolchain generated the supplied files; no H100 claim |
| Future accepted H100 record | Separate algorithm theorem still required | Attestation roots/verifier, TCB policy, measured workload, firmware/hardware, importer, and explicit axiom |

See [Verifier guide](VERIFYING.md) for commands and acceptable claim language.
