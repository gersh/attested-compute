# Trust model

SparkInterval keeps mathematical soundness and execution provenance separate.
Neither a build record nor a successful test is promoted into a mathematical
theorem.

## Axiom-free mathematical core

The modules below `SparkInterval` (except the explicitly named
`Execution/Trusted` namespace for the two execution bridges) must
contain no `sorry`, `admit`, `axiom`, or `unsafe` declaration.  Their theorems
are checked by Lean.  The axiom audit records the foundational axioms reported
by Lean and fails on unapproved source declarations.

A full Lean-checkable result certificate could use this core without trusting a
GPU run.  In that mode the GPU is only a fast certificate producer.

The current Python reference package is not such a certificate. It is checked
by Python, and neither it, the CUDA wire evaluator, nor the typed generated-PTX
polynomial slice has a proved refinement to the Lean model. They remain
external conformance layers until Lean decoder, generator/kernel correctness,
certificate-checker, and bridge theorems are implemented.

## DGX Spark profiles

DGX Spark execution records have `evidence_class: "local_unattested"` and
`hardware_attestation: null`.  Their hashes make accidental or subsequent
modification detectable, and their environment data aids reproduction.  They
do **not** establish that a particular program ran on a genuine device.  A
malicious host can fabricate the record and all files it names.

Interpreting a DGX result as a physical execution additionally trusts:

- the host OS, runner, CUDA loader and driver;
- NVIDIA's PTX semantics, offline `ptxas` PTX-to-cubin translation, and the
  Driver API's loading/execution of the recorded cubin (plus PTX JIT only when
  explicitly using development mode);
- the GB10 hardware, memory and storage;
- artifact collection and SHA-256 implementations;
- the operator's control of the machine.

Unsigned DGX local records cannot satisfy either positive Lean execution
policy and cannot be converted into `AlgorithmReturned`.

### Operator-signed local record

An optional detached Ed25519 signature can bind an approved operator key to
the exact canonical local run bundle. Verification is fail-closed: it checks
all bound artifact bytes, pins a separately supplied public key, verifies the
domain-separated signature, and requires persistent nonce replay state. The
inner evidence remains `local_unattested`, and verification always reports
`hardware_evidence: false`.

This signature establishes only that the selected key signed the record. A
malicious or mistaken operator, compromised host, or stolen key can sign a
fabricated record. It supplies provenance and change detection, not remote
hardware truth.

For workflows that deliberately trust the operator's assertion, Lean exposes
that extra physical claim as a separate, conspicuously named axiom:

```lean
axiom dgx_operator_signed_run_sound
    {statement : RunStatement} {attestation : Attestation}
    (accepted : checkDGXOperatorSignature statement attestation = true) :
    AlgorithmReturned statement statement.result
```

`checkDGXOperatorSignature` structurally binds the complete claim and accepts
only a privately constructed, externally verified operator-signature
capability for `dgxSparkSM121` plus `localUnattested`. It does not implement
Ed25519 inside Lean. The axiom is the explicit assumption that the approved
operator's signed statement truthfully describes a physical run; it is not a
consequence of signature unforgeability.

The Python verifier is implemented, but automatic construction of this private
Lean capability from the canonical JSON sidecar is not. A future importer must
remain inside the trusted boundary and bind the exact verifier, key ID, bundle,
claim, and result before the axiom can be used.

## H100 confidential-computing profile

The intended production chain does not claim that GPU attestation directly
measures a mathematical algorithm.  A measured confidential workload must:

1. generate or receive a signing key whose public key is bound to fresh CPU-TEE
   and GPU confidential-computing evidence;
2. verify the exact runner, cubin/PTX, algorithm, input and parameter hashes;
3. run the kernel, fail on any CUDA or coverage error, and hash the exact output;
4. sign a canonical run statement containing those hashes, the result, domain
   coverage, completion status and a verifier-provided nonce;
5. return the statement, signature and attestation/verifier evidence.

Production policy must pin the workload measurement, debug-disabled state,
CPU-TEE and GPU-CC TCB requirements, verifier and root identities, algorithm
identity, artifacts and freshness challenge.  It must fail closed on an
unknown field or unsupported version.

Lean exposes the H100 bridge as its own conspicuously named axiom:

```lean
axiom h100_attested_run_sound
    {statement : RunStatement} {attestation : Attestation}
    (accepted : checkH100Attestation statement attestation = true) :
    AlgorithmReturned statement statement.result
```

This axiom means that acceptance of the certificate implies the stated run and
result.  It does not prove the algorithm sound; that is a separate theorem.
`checkH100Attestation` performs structural policy/claim matching inside Lean;
it is not a cryptographic verifier.  `H100HardwareEvidence` has a private
constructor so ordinary code cannot create a positive token, but the trusted
positive-evidence importer that would validate NVIDIA evidence and invoke that
constructor is not implemented.  Local and mock evidence always reduce to
rejection and can never discharge this premise.

`AlgorithmReturned` records provenance only.  A separate theorem must identify
the formal algorithm, parse the serialized result, prove that the algorithm's
soundness theorem applies, and derive the mathematical application result.

## Remaining trusted components

Even the H100 profile depends on correct attestation roots/verifier behavior,
firmware and TCB policy, cryptographic implementations, measurement coverage,
the measured runner, NVIDIA's hardware/driver behavior and key isolation.
These assumptions are narrower and remotely checkable compared with the DGX
record, but they are not mathematical proofs.

The DGX operator mode instead trusts OpenSSL's Ed25519 implementation, secure
private-key handling, out-of-band public-key pinning, replay-state durability,
and—by explicit axiom—the operator's truthfulness about physical execution.

The axiom audit's phrase “axiom-free mathematical core” means no additional
project-specific axioms outside the named H100 and DGX-operator execution
bridges. Lean's standard
foundations such as `propext`, `Classical.choice`, and `Quot.sound` are still
reported by `#print axioms` for the mathematical theorems.
