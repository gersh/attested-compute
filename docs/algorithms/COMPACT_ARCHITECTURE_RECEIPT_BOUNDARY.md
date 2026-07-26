# Compact architecture receipts without local production replay

The production certificate, executable-state trace, and large input do not
belong in an ordinary local Lean build. The intended handoff is:

```text
signed compact receipt
  -> one trusted per-run architecture-execution fact
  -> universal data-independent binary refinement
  -> native checker acceptance
  -> application theorem
```

The generic Lean shape is implemented in
`SparkInterval/Execution/CompactArchitectureReceipt.lean`.

## What is retained locally

`CompactRunPins` retains only:

- the measurement-scheme identifier;
- the formal architecture-semantics identifier and target;
- the selected entry point;
- executable digest and byte length;
- input digest and byte length; and
- complete native result digest and byte length.

It retains no executable, production input, certificate, native result bytes,
machine states, or instruction trace. A small human-readable result envelope
may be retained by an application module, but it must be related to the
native result pin by an ordinary parser/refinement theorem.

`CompactReceiptExecutionFact` says existentially that there is a full
`MeasuredRun` matching those pins and that the closed formal machine executed
it. The witnesses live only in `Prop`. If this fact comes from the trusted
execution axiom, Lean can use the witnesses symbolically in proofs but does
not receive a literal byte array to serialize, hash, or replay.

## The three distinct assurance questions

1. **Cryptographic binding.** Did the signed receipt really commit to the
   digest, length, entry, formal-model identity, target, and result? Did the
   appraiser measure the actual run artifacts? These are receipt-import and
   verifier-policy obligations. Lean's SHA-256 implementation does not prove
   collision or second-preimage resistance.
2. **Attested physical execution.** Did the reviewed confidential-compute
   environment execute the measured launcher and bind the observed native
   run to the fresh receipt? This is the sole per-run trust step. Platform
   attestation alone is not proof of arbitrary user-space causality; the
   measured runner and appraisal policy must establish that binding.
3. **Semantic refinement.** Does every formal architecture execution
   matching the compact pins imply the native checker relation?
   `CompactArchitectureRefinement` makes this an ordinary universal Lean
   theorem. It has no receipt or attestation premise.

The universal quantifier is important. It covers every byte string with the
advertised digest and length, so the semantic theorem does not silently use
SHA-256 injectivity. If a future proof works only for one chosen digest
preimage, it must expose `CompactBlobPin.UniquelyIdentifies` (or an equally
explicit cryptographic premise); that premise is not established here.

There is an important asymmetry:

- an application verifier can normally be proved correct for every possible
  production input byte string that its strict parser accepts; but
- a compiler/ISA refinement is normally a theorem about one exact static
  executable, not every hypothetical SHA-256 collision with that executable.

`compactArchitectureRefinement_of_reviewedExecutable` supports the latter
shape, but deliberately requires `CompactBlobPin.UniquelyIdentifies` for the
executable. That premise is a cryptographic assumption.

The preferred production shape avoids the assumption:
`CompactInputReceiptExecutionFact` retains and locally validates the small
reviewed executable and small native result exactly, while existentially
hiding only the huge input/certificate and the architecture trace.
`nativeAcceptance_of_compactInputReceipt` then applies an
`ArchitectureRefinesNativeChecker` theorem for that literal reviewed image
without any digest-injectivity premise in the ordinary semantic proof. The
identification of a digest-only physical measurement with those exact static
bytes has not disappeared: `CompactInputReceiptExecutionFact` places that
exact equality inside the sole per-run cryptographic/attestation fact. This is
the deliberate trust allocation.

For Sqrt218, the intended retained objects are the pure-entry ELF and the
120-byte `SQ218R2` native result. Static hashing/decoding of those small
reviewed artifacts is not production arithmetic or production replay.

## Why no local replay occurs

`opaqueNativeAcceptance_of_compactReceipt` and
`nativeAcceptance_of_compactInputReceipt` only eliminate an existential and
apply an ordinary refinement theorem. They never evaluate the hidden input,
`ArchitectureSemantics.step`, or the application checker. The
pin-measurement projection theorem similarly rearranges equalities already
carried by `ArchitectureExecution`.

The only local executable tests use a four-byte proof-only copy machine. They
exercise the logical boundary, not a native compiler or production artifact.

## Sole-axiom integration

The existing axiom

```lean
accepted_run_certificate_sound :
  checkTrustedCompute certificate.statement certificate.attestation = true ->
  certificate.ProducedOutcome
```

now provides this boundary through
`ProducedOutcome.registeredArchitecture`. That field matches directly on the
accepted certificate's attestation. For
`trustedCompute receiptHash`, it returns
`RegisteredArchitectureOutcomes certificate.statement receiptHash`; the hash
therefore cannot be selected independently at the projection call site.
The old `ProducedOutcome.registered` projection remains temporarily for
compatibility while consumers migrate.

No second axiom was added. The sole axiom keeps the same name and acceptance
premise, and its outcome now includes the equivalent closed architecture
projection:

```lean
structure RunCertificate.ProducedOutcome
    (certificate : RunCertificate) : Prop where
  ...
  registeredArchitecture :
    match certificate.attestation with
    | .trustedCompute receiptHash =>
        RegisteredArchitectureOutcomes certificate.statement receiptHash
    | _ => True
  registered : ... -- temporary compatibility projection
```

`RegisteredArchitectureInvocation` must be a closed inductive registry, not a
structure supplied by a caller. For its Sqrt218 constructor,
`CompactExecution certificate` must reduce to
`CompactReceiptExecutionFact receiptHash reviewedSHA256Scheme
reviewedX86Machine reviewedPins`, where `receiptHash`, the scheme, machine,
and pins are obtained from that closed invocation and the admitted
`trustedCompute` certificate. None may be arguments chosen at the axiom call
site.

The ordinary Sqrt218 refinement then derives its old `Runs` success theorem
from `registeredExecution`. Once all consumers have migrated, the current
application-semantic `ProducedOutcome.registered` field should be removed.
Keeping it permanently would preserve a broader trust boundary even if the
new low-level field were also present.

Every `reviewedRun` is still `none`, so no production architecture outcome is
currently selectable. Installing a reviewed run and proving its ordinary
binary/checker refinement remain separate requirements; this signature
integration alone does not claim either is complete.
