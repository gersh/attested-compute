# CDEM Abel trusted-compute bridge

Status: the source-shaped definitions, recurrence-certificate bridge, closed
full-artifact parser/Boolean, and fail-closed V2 registry narrowing compile
successfully.  Fresh axiom audits on the artifact-to-source theorems report
only Lean's base `propext`, `Classical.choice`, and `Quot.sound`.  A production
Azure artifact/receipt and the optimized executable-to-source-program
refinement remain pending.

The
[`CDEMAbelReplayAlgorithm.lean`](../../SparkInterval/TernaryGoldbach/CDEMAbelReplayAlgorithm.lean)
proves that the typed serial replayer and supervisor can accept only after
constructing `LocalSourceScaleEvidence`; see
[`CDEM_ABEL_TYPED_REPLAY_REFINEMENT.md`](CDEM_ABEL_TYPED_REPLAY_REFINEMENT.md).
The reviewed-C++ and compiler/loader/x86 refinements remain open and are
named explicitly there.

## Exact claim

The live `claude_math` atom is
`MathExtras.CohenDressElMarraki.reproducibleTable_abel_verifier_output`.
It has exactly two conjuncts.  With

```text
K = 199330
N = 5000000000
A = N + 1
scale = 10^18,
```

the replacement table uses the Möbius coefficients on `1 <= d <= K`, the
coefficient `-A * sum_(d<=K) mu(d)/d` at `A`, and `G(0)=0`,
`G(k)=|1-F(k)|` for positive `k`.  The atom is exactly

```text
sum_(k=1)^N (G(k)-G(k-1))/k
  <= 324880457633740 / 10^18

sum_(k=1)^N |G(k)-G(k-1)|/sqrt(k)
  <= 48710223109607260068028 / 10^18.
```

[`CDEMAbelSource.lean`](../../SparkInterval/TernaryGoldbach/CDEMAbelSource.lean)
repeats those definitions in full.  It does not replace them with the later
coarse endpoint-inclusive bounds `7/20000` and `48712`.

## Registered result

The closed algorithm is `cdemTableAbelExactScanV2`; its sole production
invocation is `cdemTableAbelProductionV2`.  V2 is a distinct protocol
identity: no V1 receipt can acquire the narrowed recurrence semantics.  It
fixes the complete input,
algorithm/parameter/domain hashes, and the Azure SEV-SNP CPU deployment.
Callers cannot supply a proposition to the registry.

The V2 canonical definition hash is
`f924a59b7569a9407b78bbbe5931c03fa76532b7dd88c64401263402ac4575b0`.
It pins both the full transcript SHA-256
`2a1d551dee2f5e8997e8e2a77a587cb6cf53b93b32854f943591163db2460123`
and the generated Lean source SHA-256
`c31fe5bdb3444d53b484dbc14592d1509f284378e75ba356a006d68b952f2ee9`.
These pins were refreshed with the pre-release migration from global
`SourceScaleEvidence` to local recurrence/fold evidence.  No accepted V2
receipt exists, so no previously admitted run inherits the narrower
semantics.  The canonical input, parameter, domain, result, and output hashes
are unchanged.  Any staged bundle carrying the former algorithm hash must be
rematerialized; the importer and Azure static workload factory now emit only
the new definition hash.

The returned payload is one canonical decimal natural:

```text
2372685835387717172679029560108650251645442524
```

It is Mathlib's injective
`Nat.pair 324880457633740 48710223109607260068028`.  Lean recovers both
components with the proved inverse `Nat.unpair`.  The Python transcript
checker emits the same value as `metrics.registered_result` and its SHA-256
as `metrics.registered_result_sha256`:

```text
84e7c2b56de45b48776e4239bfc82e80ef5c80940f232b83c85eefc44648b73c
```

The successful execution meaning is no longer the final real proposition.
It names the fixed generated
`SparkInterval.Generated.CDEMAbelProduction.certificate`, ties the parsed
numerator-pair output to that certificate, and requires

```text
certificate.check = true
and
Nonempty (LocalSourceScaleEvidence certificate).
```

Ordinary Lean replays the local-to-global recurrence transport and applies
`scaledOutputClaim_of_checked_local_certificate` to derive the stronger
scaled proposition

```text
10^18 * UIncrement <= signedNumerator
and
10^18 * VIncrement <= absoluteNumerator.
```

`sourceClaim_of_scaledOutput` then proves in ordinary Lean that the production
numerators give the two source rational inequalities.  A separate literal
`"false"` branch makes the registered relation constructively satisfiable.
It cannot be used for the canonical decimal production result, so no
successful numeric output can bypass the recurrence certificate.

The production measured workload
[`tg_cdem_abel_measured_workload.cpp`](../../reference/tg_cdem_abel_measured_workload.cpp)
derives these bytes from the checked producer transcript and writes them only
after the separate all-1,000-chunk replay succeeds. The file is created
exclusively, contains no trailing newline, and is rechecked against the closed
registry SHA-256; the measured runner can therefore enforce
`canonical_decimal_natural_no_newline_v1` directly. The same static
source-reviewed executable has a separate `--verify-trace` entry point which
rechecks the retained transcript, every canonical replay-output digest, the
result, complete artifact, and challenge/job/input/result SHA-256 chain.

It also writes the canonical
`TG-CDEM-ABEL-ARTIFACT-V1` sidecar.  That artifact contains the exact
invocation/job header, both target numerators, and all 1,000 recurrence rows
in one strict fixed-width frame.  The measured trace contains its SHA-256, and
trace verification reconstructs the bytes from the checked transcript before
comparing the retained file.

[`CDEMAbelArtifactProgram.lean`](../../SparkInterval/TernaryGoldbach/CDEMAbelArtifactProgram.lean)
parses the complete sidecar, rejects malformed framing, suffixes, unknown
integer signs, and negative zero, then runs the closed recurrence replay.
Ordinary Lean proves both:

```text
artifact checker acceptance -> CDEMAbelSource.SourceClaim
artifact checker acceptance -> legacy canonical checker acceptance.
```

The executable branch is the generic `ParsedCertificateProgram`; it calls
only the parser and total Boolean, never the propositional acceptance
relation.  `ClosedSourceProgramCatalog` therefore reports CDEM as the one
source-program-complete campaign.  This classification does not claim an
installed artifact or executable refinement: the obvious Lean reference
Boolean literally replays all source events and is not the optimized Azure
implementation.

[`ProjectedCertificateProgram.lean`](../../SparkInterval/Execution/ProjectedCertificateProgram.lean)
keeps the architecture boundary honest when the old application checker
still names the descriptor.  The standalone
[`tg_cdem_abel_artifact_terminal.cpp`](../../reference/tg_cdem_abel_artifact_terminal.cpp)
now implements the required artifact-input operational shape: it strictly
parses the complete frame and independently replays all 1,000 rows without a
shell. The additive CDEM artifact-terminal materializer now verifies the
producer's signed receipt and retained archive and selects those exact bytes
as a fresh second Azure job's measured input. That stage deliberately has no
registered invocation, so its C++/compiler/ELF execution must still be proved
or explicitly trusted to refine the artifact checker before it can become
Lean theorem authority.
Ordinary Lean then projects that accepted artifact run to the fixed legacy
descriptor/result acceptance.  The module never identifies the descriptor
with the artifact and can eliminate an opaque compact receipt without
materializing the large input locally.

The same successful replay also emits
`work/cdem-abel-artifact.bin`, a strict
`TG-CDEM-ABEL-ARTIFACT-V1` encoding of the complete recurrence stream consumed
by the Lean artifact checker. The measured job declares that exact path in
the generic retained-artifact contract and names `artifact_sha256` as its
trace field. The trace verifier reconstructs the artifact from the transcript;
the measured runner and the off-VM transcript verifier then independently
hash the retained file and include its path, byte length, and digest in the
quoted statement. A trace-only digest with an absent, oversized, symlinked, or
changed artifact fails closed.

`tg_azure_cpu_portfolio_materializer.py` recognizes only the exact CDEM
terminal group and replaces its Python/compiler/run-root placeholders with
that fixed static factory. It includes the producer, independent replayer,
supervisor, SHA-256 source, profiles, input, policy, and source bytes in the
content-addressed job/package boundary. The emitted CPU config uses the
original byte-pinned portfolio challenge; it cannot substitute a second
nonce. Materialization is build evidence only and remains `accepted:false`.

## Recurrence certificate

[`CDEMAbelRecurrenceCertificate.lean`](../../SparkInterval/TernaryGoldbach/CDEMAbelRecurrenceCertificate.lean)
states the intermediate arithmetic actually used by the two reviewed C++
implementations:

```text
F(n)     = sum_(1 <= d <= K) mu(d) * floor(n/d)
delta(n) = sum_(1 <= d <= K, d | n) mu(d)
G(0)     = 0
G(n)     = |1 - F(n)|                 for n > 0.
```

Ordinary Lean proves `F(n)-F(n-1)=delta(n)`, identifies this integer `F` and
`G` with the exact real definitions in `CDEMAbelSource`, proves the signed
ceil/floor rounding rule, proves the reciprocal-square-root upper bound from
the exact guard

```text
scale^2 <= q^2 * n,
```

and composes gap-free chunks into both complete sums.  The new narrow theorem
is

```text
certificate.check = true
-> LocalSourceScaleEvidence certificate
-> ScaledOutputClaim
     certificate.signedNumerator
     certificate.absoluteNumerator.
```

`scaledOutputClaim_of_checked_certificate` retains the former
`SourceScaleEvidence` signature as an off-path compatibility theorem.  It
first calls `localSourceScaleEvidence_of_source`; it does not bypass the new
recurrence transport.

The Boolean `Certificate.check` uses ordinary `decide`, not `native_decide`.
It checks:

1. exact coverage of `[1, 5000000001)`;
2. incoming-state continuity between chunks;
3. interval well-formedness; and
4. the two exact integer reductions into the returned numerators.

`Chunk.LocallyRealizes` is now the narrow replay proposition.  It defines
`localFloorState chunk 0 = chunk.before` and advances successor offsets by
the exact `floorJump (chunk.low + offset)`.  For every retained chunk,
`LocalSourceScaleEvidence` states that:

- the outgoing field equals the final local recurrence state;
- the signed integer is the exact sign-directed fold of consecutive local
  error increments; and
- the absolute integer is the corresponding local fold for per-index weights
  satisfying the integer square guard.

This local premise contains neither a real-valued Abel inequality nor a
global `floorState`/`errorIncrement` equality.  Ordinary Lean now performs
the following transport:

1. local state at `n` is `chunk.before` plus the `floorJump` sum from
   `chunk.low` through `n`;
2. local state at `chunk.high` is `chunk.after`;
3. both chunk totals are folds of consecutive local-state error increments;
4. the first incoming state is zero and every adjacent
   `previous.after = next.before`; and
5. `floorState_jump` transports those local states, and only then their
   totals, to the closed global `floorState` and `errorIncrement`.

The key generic theorems are `Chunk.localFloorState_eq_floorState`,
`Chunk.realizes_of_locallyRealizes`, and `chain_realizes_of_local`.
`sourceScaleEvidence_of_local` packages their result for the existing
projection.

Endpoints alone cannot recover internally weighted Abel totals.  A physical
artifact must still realize the two local folds and their square guards.  The
current generated 1,000-row file does not itself construct those
five-billion local transition witnesses, so the registered `Runs` relation
requires `LocalSourceScaleEvidence` at its disclosed physical edge.  The
older `SourceScaleEvidence` and
`localSourceScaleEvidence_of_source` remain available only for off-path
compatibility.

The complete local producer and all 1,000 independent chunk replays finished
successfully.  The producer took 86.574 seconds; the replay aggregate used
363.411 CPU-seconds across eight workers.  The resulting 1,000-chunk,
167,955-byte literal certificate is
[`CDEMAbelProduction.lean`](../../SparkInterval/Generated/CDEMAbelProduction.lean).
It and the closed artifact modules have been source-compiled.

The artifact was generated with:

```bash
python3 tools/generate_tg_cdem_recurrence_certificate.py \
  build/tg/cdem-abel-full.txt \
  --output SparkInterval/Generated/CDEMAbelProduction.lean
```

The generator first applies the existing strict production-transcript parser,
then repeats the chunk topology and reductions.  The emitted Lean file
contains all chunk literals and proves `certificate.check = true` with
ordinary kernel reduction.  It records the transcript SHA-256 for audit, but
that string is not a cryptographic theorem inside Lean and does not construct
`LocalSourceScaleEvidence`.

## Trust path

The current
[`RegisteredCDEMAbelCertificate.lean`](../../SparkInterval/Execution/RegisteredCDEMAbelCertificate.lean)
provides `SignedResultCertificate.certifyCDEMTableAbel`.  Its Boolean premise
checks the closed invocation, accepted source-pinned receipt, exact result
text/hash binding, and the exact production result.

The registry's V2 CDEM `Runs` branch contains that exact fixed certificate
and the narrower `LocalSourceScaleEvidence` success boundary.  Its generated
arithmetic theorem is used directly, rather than taking arithmetic validity
on trust from the receipt.  Local states and folds are transported to the
global source folds through the operative `floorState_jump` proof.  Both
`cdemTableAbelProductionV2_result` and
`cdemTableAbelProductionV2_sourceClaim` call
`scaledOutputClaim_of_checked_local_certificate`; neither assumes a real Abel
inequality.  The enumerated `runs_satisfiable` theorem uses only the explicit
failure output.  Production deployment and receipt pins remain `none`, so
the trusted-run bridge is also fail-closed until a reviewed run is installed.

Fresh `#print axioms` reports only Lean's standard quotient/classical
principles on the recurrence-to-source and full-artifact theorems.  A future
end-to-end physical certificate theorem will additionally report the
repository's one disclosed axiom:

```text
SparkInterval.Execution.Trusted.accepted_run_certificate_sound
```

That axiom remains responsible only for the physical confidential-compute
execution fact after ordinary code/architecture refinement has been supplied.
This slice does not yet purport to prove the machine-code or C++ refinement.
The reviewed
producer, independent chunk replay, measured artifact hashes, compiler hash,
compiler-to-binary semantics, runtime execution, SEV-SNP/vTPM evidence,
appraiser policy, and signed receipt are the disclosed external part of that
boundary.  No unbounded analytic premise remains in this CDEM projection:
all real finite-sum and directed-rounding steps are ordinary Lean theorems.

## Remaining steps

1. On an x86_64 build/operator host, materialize the implemented static CDEM
   measured package, run it on the reviewed Azure SEV-SNP SKU, and retain the
   complete producer, independent 1,000-chunk replay, and
   `TG-CDEM-ABEL-ARTIFACT-V1` outputs.
2. Add the implemented standalone artifact-input terminal as the second stage
   of a reviewed materializer, with the first stage's signed retained artifact
   as its exact measured input.  Do not relabel the small descriptor as that
   artifact.
3. Prove `CxxSourceRefinesTypedSupervisor` for the exact reviewed producer,
   independent replayer, and supervisor, then prove
   `CompilerX86RefinesCxxSource` for the measured static ELF. The typed
   algorithm-to-`LocalSourceScaleEvidence` theorem is already complete.
4. Appraise and sign the Azure evidence with a production-classified key,
   then admit the exact receipt to `TrustedComputeRegistry.lean`.
5. Generate and compile the concrete receipt consumer with
   `--registered-invocation cdemTableAbelProductionV2`.
6. In `claude_math`, use the already proved definition-by-definition equality
   between
   `CDEMAbelSource.SourceClaim` and
   `ReproducibleTableAbelVerifierOutput`, replace the named CDEM Abel axiom by
   the generated theorem, and rerun the capstone `#print axioms` audit.

Until these steps are complete, this is a source-complete artifact program and runnable
external computation, not a discharged `claude_math` atom.
