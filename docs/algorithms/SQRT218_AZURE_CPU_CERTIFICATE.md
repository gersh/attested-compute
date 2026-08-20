# Sqrt218 finite certificate on Azure confidential CPU

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../../attestation/phala/README.md`](../../attestation/phala/README.md).

This path verifies the finite computation used for Helfgott's equation
(2.18) through `2,000,000`. The full production computation is cloud-only:
local validation is deliberately limited to the bound-64 Python
known-answer test, the corresponding fixed-width bound-5 Lean/C tests, the
Lean 30-seed regression, the C first-post-seed recurrence at `31`, schema and
tamper checks, and measured-job structural validation.
Both the producer and independent verifier enforce this in their library
entry points: bounds `65..1,999,999` have no execution profile, and bound
`2,000,000` requires the exact Azure measured-production context. The
standalone certificate CLI is permanently KAT-only. The cloud workload
additionally requires `--cloud-production` and all four reserved scope
fields injected by the measured runner, including exact equality with its
challenge nonce and job-binding digest. An ordinary invocation therefore
fails before opening the certificate or allocating the production sieve.
Those scope fields are an accidental-execution guard, not an attestation
credential; the independently appraised quote, measurements, challenge, and
policy bindings provide the security boundary.

The workload belongs on a CPU confidential VM, not an H100. Its dominant
operations are an Eratosthenes sieve, arbitrary-precision integer arithmetic,
Lucas/Pratt modular powers, and a sequential prefix state. A GPU
implementation would first need a separately reviewed multiprecision and
prefix-composition design. The current closed implementation targets
`azure_sevsnp_cpu`, for example an independently pinned and calibrated
`Standard_DC96as_v6` or `Standard_EC96as_v6` deployment.

## Fast local path versus cloud production

The fixed-width V2 path is not an existing Azure production path. What exists
today is the C checker, parallel Lean reference semantics and wire parser,
proved data-independent refinement of every successful event and of the
complete event loop, and a proof that successful endpoint-slack arithmetic
implies the kernel's exact `anchorOK` guard. The source-level C model also
proves the fixed-width read, carry, borrow, wide-multiply, comparison,
accumulator, head, and endpoint arithmetic compositions refine the
architecture-neutral Lean operations. These are symbolic theorems over
arbitrary inputs; compiling them never reads a production certificate.
The successful fixed-header opener, every fixed-record accessor, and all five
section loops now reconstruct the exact architecture-neutral archive through
exact EOF. Their re-encoder is proved to return every original byte, so the
strict canonical decoder accepts that exact archive without a hash-injectivity
assumption. The source roster and inverse power-layout passes prove the exact
V2 Boolean checks. The restoring 128-by-64 division loop proves ordinary
quotient and remainder, and the 120-byte C result encoder round-trips through
the strict Lean result decoder.
Compact receipt/pin validation tooling, a strict non-authorizing compiler-
evidence manifest validator, and tiny tests also exist. A fixed-V2 Azure
job/materializer, integration of a full production certificate producer, real
reviewed pins, a real signed receipt, and supported source-registry admission
are all still absent.

The intended deployment keeps the following activities separate:

| Activity | Reads the production certificate? | Recomputes the finite scan? |
|---|---:|---:|
| Ordinary Lean import of a future admitted receipt | No | No |
| Local source compilation and bound-5/bound-64 KATs | No | No |
| Future optional artifact-retention audit | Yes, for bounded-memory streaming hashes | No |
| Future measured Azure certificate producer | Yes | Yes |
| Future independently measured Azure verifier | Yes | Yes |

A future measured worker must snapshot the complete certificate, run the
fixed checker, and emit a 120-byte `SQ218R2` record. That record contains the
exact snapshot length and SHA-256 digest. Its canonical ASCII envelope must be
the signed result. The signed statement must also bind the reviewed
certificate digest, checker executable, execution closure, job identity, and
result.

If such a reviewed run is later admitted, a normal downstream Lean build will
need only the compact statement/result and registry pins. It will not open the
large certificate, hash it, or evaluate the production checker. The sole
`accepted_run_certificate_sound` boundary can then expose the closed
registered `Runs` proposition; all `Runs -> SourceClaim` reasoning is
data-independent Lean proof. An optional auditor may stream-hash retained
artifacts to compare them with the receipt, but that is not part of theorem
elaboration and is not a second arithmetic replay.

The matching Python fast path is
`tg_verifier.sqrt218_fixed_v2_receipt.validate_receipt_only_binding`.
After generic receipt-signature verification it consumes only the receipt and
the compact
`sparkinterval.sqrt218-fixed-v2-reviewed-pins.v1` record. It parses the
281-byte ASCII envelope and its complete 120-byte result, then checks the
embedded input digest and length plus the signed input, output, checker,
closure, algorithm, backend, completion, and wire-statement fields. A
regression test replaces every file-open/hash helper with a failure and
confirms this path on a tiny synthetic record. The receipt CLI exposes the
format audit as:

```bash
python3 tools/trusted_compute_receipt.py verify RECEIPT \
  --sqrt218-fixed-v2-reviewed-pins REVIEWED_PINS
```

This tooling reports `accepted_for_lean: false`; it does not supply the
currently absent job, reviewed production inputs, signed receipt, or registry
admission. The separately named `verify_exact_artifacts` API and CLI options
requiring a run bundle/artifact root are optional retention audits. They
stream-hash files but still do not execute the checker. They should run in the
cloud or an explicit archival-audit environment, never as part of an ordinary
local build.

## Exact claim and archive

The source-shaped claim is
`SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim`. It contains
both:

1. every strict weighted head inequality for `1 <= N <= 2,000,000`; and
2. the endpoint Abel anchor at `2,000,000`.

`tg_verifier/sqrt218_certificate.py` is the deterministic producer. It emits:

- the complete prime roster and complete factorization of every `p - 1`;
- a Lucas witness for every prime;
- the directed scale-`2^48` log enclosure for every prime;
- every ordered prime-power event; and
- the exact terminal and minimum-slack state.

`tg_verifier/sqrt218_certificate_verifier.py` does not import the producer. It
uses a different sieve representation, reconstructs the prime and
prime-power rosters, checks every factorization and Lucas residue, advances
the log ladder independently, and scans every integer prefix. The fixed
Pratt, layout, scan, and final-state digests are protocol constants. Acceptance
is reported as `full_exact_external_replay_not_lean_theorem`: external replay
does not silently become a kernel proof.

Lean separately defines the package-neutral source claim and generic
certificate facts under `TGComputeContracts/Sqrt218/`. The typed archive and
exact Boolean checker live under
`SparkInterval/TernaryGoldbach/Sqrt218/Operational/`. Without constructing any
production archive, ordinary Lean proves

```text
Sqrt218Operational.run productionProfile archive = true
  -> TGComputeContracts.Sqrt218.CertificateFacts
  -> TGComputeContracts.Sqrt218.SourceClaim.
```

The production profile requires `some` of the complete reviewed summary, not
the development profile's optional summary. The closed registered success
branch is exactly an existential archive satisfying this operational equation;
it no longer carries a separately trusted archive-to-Mathlib
`SourceScaleEvidence`.

The source proof obtains prime-roster soundness from the full bounded
`Nat.Prime` cell-and-coverage check. The Lucas/Pratt table is additionally
validated so witness or factorization drift fails closed, but it is not the
primality bridge used by `CertificateFacts`. Likewise, neither attestation nor
the registered relation exposes `StreamingScan.ScanFacts` on its own: only
success of the complete `Sqrt218Operational.run` is an accepted boundary.

The schemas are
`schemas/sqrt218-finite-run-input.schema.json` and
`schemas/sqrt218-finite-certificate.schema.json`. The bound-64 presentation
fixture is under `examples/sqrt218/`.

### Efficient fixed-width checker path (binary-checker V2)

The registered path above remains the canonical-JSON V1 path. A separate
efficient fixed-width format, identified by the magic `SQ218V2\0`, now has
a portable C checker and architecture-independent Lean checker semantics.
Their full native/compiler/ISA refinement remains pending:

- earlier-row factor references plus explicit composite gaps certify the
  exact prime roster without a bounded `Nat.Prime` decision at every value;
- a flattened per-prime inverse map certifies the sorted prime-power event
  roster in work linear in the number of events;
- one exact 30-seed table and a proved integer recurrence certify directed
  log rows;
- one fixed-point event fold checks every strict head guard; and
- the unchanged Abel endpoint guard checks the claimed exit.

The typed Lean composition is
`Sqrt218Operational.V2.run`. It is definitionally fixed to
`TGComputeContracts.Sqrt218.sourceCutoff = 2,000,000`; only that production
entry point feeds `sourceClaim_of_run`. The separately named
`runAt expectedBound` exists solely so tiny archives can exercise the same
passes and guards. `Operational/V2/RunTest.lean` supplies the complete
bound-5 archive used by the C KAT (primes `2,3,5` and events `2,3,4,5`),
checks `runAt 5`, and checks that the production `run` rejects it. The claimed
exit is an explicit four-event fixed-point value, not a production prefix.
`Operational/V2/LogRowsTest.lean` checks all 30 fixed seeds. The C KAT checks
the bound-5 stages, tamper rejection, production-profile rejection, and the
first recurrence after the seed table at `31`.

The portable fixed-width implementation and format are under
`cpu_checker/sqrt218/`; the corresponding Lean fixed-width IR and typed
adapter are under
`SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/`. These are an efficient
future production path, not a completed replacement for the registered V1
archive or receipt.

The native helper ABI is now prepared for the proposed CompCert route:
two-limb helper and restoring-division inputs are scalar `uint64_t` limbs,
checked results use output pointers, and no helper passes `tg_sq218_u128` by
value. The existing production entry behavior is unchanged. A separate
`tg_sq218_verify_snapshot_v2` entry presents only fixed-width scalar/pointer
arguments and emits the canonical 120-byte record. A freestanding
`TG_SQ218_PURE_ENTRY_ONLY` translation excludes every POSIX include and
file-command branch; the production build target fails closed unless the
compiler target is x86-64, while a separately named host build is
development-only. The entry's complete source proof and verified compilation
remain open.

The static arithmetic bridge is split into reviewable layers:

- `Fixed128.lean` specifies exact two-limb natural-number arithmetic;
- `CPrimitives.lean` models the literal C unsigned-word operations and proves
  successful checked operations refine `Fixed128`;
- `CArithmeticRefinement.lean` composes those operations in the source order
  used by the head, event, and endpoint helpers;
- `CStepRefinement.lean` proves the C checked-power loop, floor-square-root
  guard, directed reciprocal helper formulas, and the complete accepted C
  event transition directly against the generic fixed-event kernel;
- `CSourceLoopRefinement.lean` proves exact no-wrap cursor progress for every
  accepted C transition and lifts those transitions through arbitrary
  successful source-loop traces and the complete event table;
- `CWireEncodeRefinement.lean` and `CArchiveRefinement.lean` prove exact
  record/header re-encoding, all five source iteration loops, exact EOF, and
  unconditional strict canonical decoding of the original bytes;
- `CRosterRefinement.lean` and `CPowerLayoutRefinement.lean` prove the complete
  accepted source passes imply the exact V2 roster and inverse-layout checks;
- `CU128DivRefinement.lean` proves the source restoring division returns exact
  natural-number `/` and `%` with word bounds;
- `CResultEncoderRefinement.lean` proves the source's complete 120-byte result
  record is decoded as precisely the status, input metadata, arithmetic state,
  slack, and digest bytes it encoded;
- `IR.lean` proves each successful fixed-width event step and endpoint
  calculation imply the generic kernel guards; and
- `LoopRefinement.lean` lifts the one-step theorem through the complete event
  table without reducing any closed archive.

The parser, roster, power layout, accepted event step/loop, endpoint arithmetic,
result encoder, and mathematical outer acceptance composition are therefore
closed at their source models. `CCompleteValidationRefinement.lean` proves
those successful traces give the exact V2 `completeCheck` and source claim,
and its raw-byte theorem supplies the no-replay acceptance interface. The
thirty fixed log seeds are closed by the separate ordinary-Lean
`Sqrt218LogSeedClosure.lean` theorem; its roughly fifteen-second cached check
never touches the production archive. `CSHA256Refinement.lean` proves the
complete pure C SHA-256 algorithm for arbitrary input bytes.
`CValidationControlFlow.lean` now models the literal successful
validate-all/bytes-wrapper call order and constructs the complete raw
validation relation, while `CPureEntryComposition.lean` joins it to wrapper
guards, hash bytes, and result bytes. The remaining obligation is for
compiler/ISA execution to prove the measured entry constructs those source
relations. This single low-level target is named
`CArchitectureComposition.ArchitectureExecutionSuppliesSuccessfulPureEntry`.
Compiler, ABI,
assembler/linker, ELF/loader, ISA, and hardware preservation then remain.
Attestation identifies the measured artifact and run; it does not manufacture
those refinement theorems.

The proposed VST/CompCert path, completed helper-ABI cleanup, compact
compiler-evidence schema/validator, and exact residual trust are documented in
[`SQRT218_VERIFIED_COMPILER_PATH.md`](SQRT218_VERIFIED_COMPILER_PATH.md).
The metadata validator checks canonical identities and chain consistency only;
it does not run the toolchain or prove the still-missing compiler/ISA edge.
`CPUChecker/ExecutionClosureIdentity.lean` retains the exact canonical
identity bytes and binds their SHA-256 plus every compiler/model/ABI/ELF/entry
field to the signed statement and exact measured run. This closes the
Lean-side field-equality join. The validator's
`--execution-closure-projection` mode now derives and rechecks the identical
canonical bytes and all fourteen fields from a bounded V2 compiler manifest.
It does not give those fields compiler/ISA semantics, and no production
manifest has been generated or reviewed. Until receipts sign those metadata
bytes directly, the digest-to-bytes interpretation has the standard SHA-256
collision/second-preimage residual assumption.

The compact result bridge is deliberately split by cost and dependency:

- `Operational/V2/ResultWire.lean` parses only the 120-byte record and its
  ASCII envelope and depends only on the two-limb data type;
- `Operational/V2/ResultSemantics.lean` maps those fields to the
  architecture-neutral `ArithmeticResult`; and
- `Operational/V2/ArtifactBinding.lean` joins exact signed statement fields,
  strict certificate decoding, and `completeCheck`.

The first module and its 120-byte KAT are sufficient for ordinary receipt
format checks. Importing any of the three modules does not evaluate a
production certificate.

### Canonical bytes and receipt binding

`SparkInterval/TernaryGoldbach/Sqrt218/Operational/Wire.lean` is the strict
Lean decoder for the existing
`sparkinterval.sqrt218-finite-certificate.v1` JSON; it does not introduce a
second binary format or reinterpret the registered V1 input. It accepts a
`ByteArray` only after strict UTF-8 decoding, exact-field and row-shape checks,
and byte-for-byte comparison with Lean's compact sorted-key re-encoding. Thus
the ordinary theorem

```text
decodeCanonicalArchiveBytes raw = .ok archive
  -> canonicalArchiveBytes archive = raw
```

binds `kind`, schema version, every parsed field, exact EOF, and the absence of
alternate encodings. The same archive cannot be accepted from two different
byte arrays. Small guards check the existing bound-64 Python fixture, reject
its presentation newline, and reject a suffix, duplicate key, and wrong
protocol discriminator. They perform no production replay.

For a measured run, the artifact that should be decoded is the exact
`selected_certificate` file. The workload hashes those raw bytes as
`certificate_sha256`; that digest is a domain-separated input to the Sqrt218
work-trace chain. The independent trace verifier recomputes the archive digest,
and the measured-runner statement binds the resulting
`work_trace_chain_sha256` before the final PCR extension, quote, appraisal, and
Managed HSM signature.

This is a precise integration recipe, not a completed receipt-to-Lean
composition. `Operational/ArtifactBinding.lean` now defines the exact
data-independent intermediate contract

```text
raw bytes + strict decoder + canonical SHA-256 name + run = true
  -> SourceClaim
```

and proves that implication without an execution axiom.

The current normalized receipt V1 is insufficient for an honest extractor:
it retains the wire-statement hash, but drops `certificate_sha256`,
`verification_report_sha256`, `job_binding_sha256`, and the two work-trace
digests after appraisal. The certificate digest is also only a hidden preimage
of `trace_sha256`, not a field of the retained trace JSON. Recovering any of
those values from a SHA-256 digest would be an unjustified inversion step.

For a future receipt version,
`ReceiptArtifactFieldsV2` specifies the five additional fields that must be
signed directly:

```text
job_binding_sha256
certificate_sha256
verification_report_sha256
work_trace_chain_sha256
work_trace_artifact_sha256
```

This receipt-extension “V2” and the fixed-width binary-checker V2 above are
different version domains. `ReceiptArtifactFieldsV2` extends the signed
fields around the existing canonical-JSON V1 archive and reconstructs its V1
work-trace formulas. It does not parse `SQ218V2\0`, name the fixed-width C
checker, or constitute a receipt for that binary format. A future deployment
must introduce an explicit registered profile joining the binary-checker
format, its measured executable and result, and an accepted receipt; the
shared numeral `2` creates no such binding.

Its ordinary Lean checker reconstructs the exact existing V1 Sqrt218 trace
preimage and compact trace JSON, checks both work-trace digests, joins the
signed certificate digest to strict canonical archive decoding, and requires
that same typed archive as the argument of `Operational.run`. Decoder
uniqueness is proved for the exact retained bytes; SHA-256 injectivity is not
claimed. Tiny Python/Lean known-answer and tamper tests exercise this binding
without loading production rows.

The registered V1 `Runs` relation still exposes an existential typed archive
rather than this digest-named V2 object. No accepted receipt currently carries
the V2 extension, and native execution refinement remains inside the existing
trusted-run boundary. Therefore these definitions do not change or narrow the
sole `accepted_run_certificate_sound` axiom.

## Numeric data by reference

Production does not embed an unauthenticated result table. Its exact measured
input must be a canonical `sparkinterval.pinned_numeric_corpus.v1` record.
That small pin transitively fixes:

```text
repository URL + immutable commit + manifest bytes
  -> exact source-shaped statement
  -> payload root and source root
  -> the complete canonical Sqrt218 archive and its generator/checker sources
```

The source-reviewed workload verifies the full read-only snapshot, requires
the Sqrt218 claim, one complete certificate-archive payload, exact parameters,
and the three semantic commitments, then independently replays the archive.
The challenge-bound trace hashes the pin, result, archive, and verification
report. Receipt issuance must use:

```bash
python3 tools/trusted_compute_receipt.py issue \
  ... \
  --require-numeric-corpus-input
```

No production corpus commit, pin, archive, key, Azure policy, or receipt is
invented or included here. After a real corpus is published, its exact input
digest must receive a new versioned registered invocation. The existing V1
input hash `17d1c532...` is the distinct full-recomputation profile and must
not be silently reinterpreted as the future corpus-backed profile.

## Materialize and run

First resolve and verify a reviewed pin outside the worker:

```bash
python3 tools/fetch_tg_numeric_corpus.py \
  /reviewed/sqrt218-pin.json \
  --cache-root /private/numeric-corpus-cache
```

Then materialize against an independently reviewed production runner policy:

```bash
python3 tools/build_sqrt218_measured_job.py \
  --output-root /srv/sqrt218-job \
  --runner-policy /reviewed/production-runner-policy.json \
  --numeric-corpus-pin /reviewed/sqrt218-pin.json \
  --numeric-corpus-snapshot /private/numeric-corpus-cache/SNAPSHOT
```

The builder refuses a production policy without both the real pin and its
verified snapshot. It emits no production appraisal policy. On the reviewed
Azure SEV-SNP guest, the existing challenge-first runner consumes the job:

```bash
python3 azure/measured_runner.py \
  --job-spec /srv/sqrt218-job/job.json \
  --artifact-root /srv/sqrt218-job \
  --challenge /operator/fresh-challenge.json \
  --output-dir /returned/sqrt218-run
```

The result remains pending until the independent SEV-SNP/vTPM appraiser checks
the exact image, Python runtime, job, policies, challenge, PCR equations, and
trace, and a reviewed Managed HSM key signs the compact receipt. A later
source review must add the real corpus-backed registered invocation and
receipt; the materializer itself sets `lean_registry_admission:false`.

For protocol development only, a caller may omit all three policy/corpus
options and explicitly pass `--emit-full-recomputation-job` to materialize
the V1 full-recomputation job under the repository's non-authorizing
development policy. Without that flag the builder fails before creating an
artifact tree. The flag only permits cloud-job materialization; it does not
authorize local execution. The production-sized scan belongs on the reviewed
Azure measured runner.

The ordinary local arithmetic checks are limited to the Python bound-64 KAT,
the C bound-5/31 KAT, and the Lean bound-5/30-row KATs:

```bash
python3 tools/tg_sqrt218_certificate.py \
  produce /tmp/sqrt218-64.json --bound 64
python3 tools/tg_sqrt218_certificate.py \
  verify /tmp/sqrt218-64.json

make -C cpu_checker/sqrt218 test

lake env lean \
  SparkInterval/TernaryGoldbach/Sqrt218/Operational/V2/LogRowsTest.lean
lake env lean \
  SparkInterval/TernaryGoldbach/Sqrt218/Operational/V2/RunTest.lean
```

## Architecture and translation-validation boundary

The artifact closure includes:

- a declarative operational state machine;
- the exact Python producer, independent verifier, and corpus adapter;
- the efficient fixed-width C checker, Lean IR, and typed V2 checker;
- a source manifest;
- deterministic bound-64, bound-5, 30-seed, and first-post-seed
  known-answer checks; and
- a translation-validation plan.

The Lean operational checker proves that typed success implies complete prime
and prime-power rosters, rationally checked directed log bounds, every fixed
scan guard, the anchor, and ultimately the exact real source claim. It does
now prove that strict canonical V1 JSON bytes decode to a typed archive with
the required `kind`, fields, and exact EOF. It also proves that an explicitly
digest-bound, decoded, successful archive implies the source claim. It does
**not** yet prove that the archive digest nested in a signed work trace
constructs that object, that the measured Python/native program implements the
checker, or that an x86-64 binary refines it. Current assurance across those
remaining edges is the measured source/image identity, hardware-attested
execution, independent archive replay, deterministic KAT, and the explicitly
disclosed trusted-compute receipt axiom. A stronger architecture theorem must
connect the signed receipt artifact digest to the new binding object, then
supply either a formal Python semantics or a source rewrite into a verified
CPU IR, followed by verified compilation or independently checked translation
validation down to the measured binary.

For the fixed-width path, the primary compiler target is now the pure source
relation
`CPureEntryComposition.successfulPureEntryChecker`, whose accepted calls
existentially carry one `CSuccessfulPureEntryTrace`. That trace contains the
wrapper guards, exact source SHA-256 result, complete byte-validation trace,
and exact 120-byte source encoder output. It has no abstract `nativeRun`
parameter. `CArchitectureComposition.ArchitectureExecutionSuppliesSuccessfulPureEntry`
states the exact architecture-to-source obligation, and
`CX86ELFComposition.sourceClaim_of_x86ELFExecution` composes an honest
ELF/ISA, assembler/linker, CompCert, and VST chain directly to the source
claim without replaying `runArithmetic` or `completeRun`.

The older
`Sqrt218CPUChecker.V2Adapter.NativeAcceptanceSuppliesV2Check`,
`NativeAcceptanceRefinesV2`, `NativeRunnerRefinesV2`, and
`CCompleteValidationRefinement.NativeAcceptanceRefinesCCompleteValidation`
routes remain compatibility interfaces for an independently specified native
runner. They are not the target of the compiler proof and do not substitute
an unconstrained callback for source semantics. The repository does not yet
construct the pure-entry obligation from a concrete compiler/ISA execution.
The integer
primitives, event arithmetic, accepted C event transition, successful C scan
trace, full Lean event-loop induction, endpoint guard, exact record accessors,
whole-archive canonical parser, roster pass, inverse power-layout pass,
restoring division, result-record encoder, anchor, and outer mathematical
composition, pure C SHA-256, and successful pure-entry relational control flow
are now proved separately. Realizing those trace objects and modeled
hash/result bytes remains part of compiler/ISA refinement.
The compiler,
assembler/linker, ELF loader, x86-64 ISA execution, and physical CPU
preservation theorem also remains absent. A measured binary and
confidential-compute signature can identify which executable ran; they do not
prove this compiler/ISA refinement obligation.

The intended replacement trust shape is explicit in
`Execution/ArchitectureExecution.lean`,
`Execution/X86ELFPureEntry.lean`,
`Execution/X86ELFDecoder.lean`, and
`CPUChecker/CX86ELFComposition.lean`: a compact receipt supplies one exact
architecture `load -> step* -> haltedWith` fact for the measured run, while a
data-independent binary-refinement theorem proves that every such execution
of the exact image satisfies `CSuccessfulPureEntryTrace`. Ordinary Lean then
derives the source claim directly. The present `AlgorithmReturned` token has
no machine trace, so its temporary implication to the architecture fact is
named as transitional trust rather than being presented as an ISA theorem.
No production trace is replayed by these symbolic compositions.

The bounded decoder closes the ELF64 byte structure and exact selected-symbol
parts of this list. It retains complete program payloads and `PT_LOAD` bytes,
rejects malformed or wrapping ranges, exposes interpreter, dynamic, and
relocation evidence, and decodes linked `SHT_SYMTAB`/`SHT_STRTAB` data. The
selected `tg_sq218_verify_snapshot_v2` definition must be unique, global,
nonempty, executable, and equal to `e_entry`; stripped images fail closed at
the named-entry interface. Mapping decoded segments into memory, SysV
register/stack initialization, x86 execution, and output observation are
still required.

The eventual measured executable must copy the input to one private immutable
snapshot, keep result storage disjoint, and hash and retain that exact
snapshot for the receipt. The current borrowed-pointer C library states this
as a caller precondition; attestation does not by itself prevent concurrent
input mutation or a check/hash time-of-check/time-of-use mismatch.

## Remaining production gates

- publish and independently review the real numeric corpus and pin;
- add a new corpus-backed registered Lean invocation using that real pin hash;
- pin and calibrate the exact Azure CPU SKU and immutable guest image;
- review a production runner policy and independent appraisal policies;
- provision and review the Managed HSM key/version and public-key manifest;
- run the cloud job, retain the complete evidence/archive, and appraise it;
- issue with `--require-numeric-corpus-input`; and
- source-review the resulting registry and Lean consumer.

Until every gate is complete, this is executable infrastructure, not an
admitted theorem or a claimed production run.
