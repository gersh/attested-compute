# Sqrt218 verified CPU-compiler path

This is the proposed code-to-machine assurance path for the fixed-width V2
Sqrt218 checker. Production arithmetic and production certificate replay are
cloud-only. Local development is limited to symbolic proof checking, static
artifact inspection, and tiny known-answer tests.

## Intended chain

```text
Lean source claim and neutral SQ218V2 contract
                    |
                    v
Lean proof of checker arithmetic and complete accepted-path semantics
                    |
                    v
VST proof of the pure C checker against the same neutral contract
                    |
                    v
CompCert: elaborated CompCert C -> abstract x86-64 assembly
                    |
                    v
pinned assembler/linker and optional Valex validation
                    |
                    v
content-addressed static x86-64 ELF
                    |
                    v
Azure SEV-SNP measured execution on an immutable input snapshot
                    |
                    v
compact signed receipt binding code, input, result, challenge, and policy
                    |
                    v
one reviewed Lean trusted-computation boundary
```

An H100 may be an untrusted high-throughput certificate producer. The
authority-bearing component is the much smaller measured CPU checker that
accepts or rejects the producer's fixed-width certificate.

## Why CompCert is a credible fit

The proof-bearing core in `cpu_checker/sqrt218/sqrt218_cpu_checker.c` is
integer-only. It uses fixed-width words, arrays, pointers, records, and loops,
but no floating point, heap allocation, threads, inline assembly, variable
length arrays, filesystem calls, or formatted output. Those properties make
it a plausible CompCert C and VST target.

CompCert 3.17 supports x86-64 and proves semantic preservation from its
elaborated C representation to an abstract assembly representation. Its own
manual is explicit that preprocessing, some front-end transformations,
assembly, and linking are outside the fully verified phase. The standard
assembler/linker therefore remain in the trusted base unless an additional
validator or verified ELF path is used. See the official
[CompCert overview](https://compcert.org/man/manual001.html),
[command-line options](https://compcert.org/man/manual003.html), and
[supported C language](https://compcert.org/man/manual005.html).

## Required C boundary

The C code now has the proposed flat entry:

```c
int tg_sq218_verify_snapshot_v2(
    const uint8_t *bytes,
    uint64_t length,
    uint8_t *record120,
    uint32_t *status_out);
```

Its contract is:

- `bytes[0..length)` is one immutable, non-aliasing snapshot;
- the function parses and checks the complete V2 certificate;
- success writes the canonical 120-byte `SQ218R2` record;
- rejection cannot write an accepted record; and
- it performs no I/O and emits no diagnostics.

It delegates to the unchanged production snapshot validator and record
encoder. It remains in the command translation unit, but
`TG_SQ218_PURE_ENTRY_ONLY` preprocesses away the complete POSIX command path;
the freestanding artifact therefore retains only the checker, SHA-256,
record encoder, and flat entry. No VST or CompCert theorem is claimed by this
source/build packaging.

`cpu_checker/sqrt218/Makefile` exposes two deliberately different
freestanding build targets:

- `make pure-entry` requires an `x86_64-*` compiler target and emits
  `sqrt218_cpu_checker_pure_entry_x86_64_v2`. It fails before compilation if
  `X86_64_CC` is missing or reports another architecture.
- `make pure-entry-host` is only a fast source-closure smoke check. Its output
  is never eligible for an Azure production receipt or for the x86-64 Lean
  refinement.

The distinction is material: a successful host build on an AArch64
development machine is not evidence about the x86-64 Azure executable. The
production ELF, compiler identity, and target triple must be built and pinned
inside the reviewed cloud build chain. Neither Make target runs the checker
or opens a production certificate.

Composite values may remain in memory, but proof-bearing function arguments
and results should not pass structures by value. CompCert rejects structure
passing by default; enabling `-fstruct-passing` uses a calling convention that
its manual warns is not the x86-64 platform ABI. The two-limb helpers should
therefore receive scalar limbs:

```c
int u128_cmp(
    uint64_t lhi, uint64_t llo,
    uint64_t rhi, uint64_t rlo);

int u128_add_checked(
    uint64_t lhi, uint64_t llo,
    uint64_t rhi, uint64_t rlo,
    uint64_t *out_hi, uint64_t *out_lo);

int u128_sub_checked(
    uint64_t lhi, uint64_t llo,
    uint64_t rhi, uint64_t rlo,
    uint64_t *out_hi, uint64_t *out_lo);

int u128_mul_u64_checked(
    uint64_t hi, uint64_t lo, uint64_t multiplier,
    uint64_t *out_hi, uint64_t *out_lo);

int u128_div_u64(
    uint64_t numerator_hi, uint64_t numerator_lo,
    uint64_t denominator,
    uint64_t *quotient,
    uint64_t *remainder);
```

Those helper signatures and every core call site are now flat. The public
production byte validator and snapshot-to-record wrapper retain their prior
interfaces and behavior.

The POSIX command wrapper is a separate measured component. Its `open`,
`fstat`, `read`, `malloc`, `write`, `fsync`, and process behavior are not
proved merely by compiling the pure checker with CompCert. The receipt and
appraisal must keep that runtime boundary explicit.

## Proof obligations

The Lean side now proves that one accepted source-level C event transition
refines the exact mathematical fixed-event step, including exact cursor
increment without wrap, and lifts that theorem through a complete successful C
scan trace. These are symbolic theorems over arbitrary inputs; checking them
does not evaluate a production archive.

The mathematical accepted-path composition is now proved in
`CPUChecker/CCompleteValidationRefinement.lean`. The primary source-facing
obligation is
`CArchitectureComposition.ArchitectureExecutionSuppliesSuccessfulPureEntry`.
It says that every successful architecture execution of the selected checker
supplies a `CPureEntryComposition.CSuccessfulPureEntryTrace`, the pure-source
relation containing the exact validation result, SHA-256 bytes, status, and
120-byte output.

```lean
def ArchitectureExecutionSuppliesSuccessfulPureEntry : Prop :=
  ∀ bytes status output,
    architectureExecution bytes status output →
    successfulPureEntryChecker implementation.identity.neutralContractId
      bytes status output
```

Here `successfulPureEntryChecker` is defined through
`CSuccessfulPureEntryTrace`; it does not receive an abstract `nativeRun`.
Ordinary Lean proves that this relation supplies a canonically decoded archive
and `completeCheck image result = true`, without evaluating the production
archive. The older
`NativeAcceptanceRefinesCCompleteValidation (nativeRun ...)` route remains
only as a compatibility layer for historical receipt APIs.

The fixed-record accessor layer is now proved: the ordered C index,
checked-multiply, checked-add, and half-open range path yields the exact
section address, and all five successful accessors decode to the same
prime/factor-reference/factor-pair/event/power-reference values as the Lean
wire model, including reserved-field guards.  Whole-list aggregation into
the archive is also proved: the five source iteration traces reconstruct all
typed lists, exact EOF, and every original byte. The strict canonical decoder
therefore returns that exact archive without a digest-injectivity premise.

The successful source-level relational path is now closed. In
`CPUChecker/CValidationControlFlow.lean`, the literal production guards,
zero-status roster/layout/log/scan/anchor call order, local result assignment,
canonical bytes wrapper, and forwarded return status construct the complete
validation trace. `CPUChecker/CPureEntryComposition.lean` joins that trace to
the pointer guards, proved SHA algorithm, concrete output bytes, and strict
result encoder.

`CPUChecker/CSHA256Refinement.lean` now proves the pure source algorithm for
arbitrary bytes: exact C word operations, schedule, all 64 rounds,
feed-forward compression, modulo-`2^64` length, the 64/128-byte padding branch,
block fold, and big-endian output refine the pure Lean SHA-256. The remaining
fact is explicitly named `ConcreteExecutionMatchesSource`: compiler/ISA
execution must show the concrete 32 output bytes equal that source model.

`Sqrt218LogSeedClosure.lean` now gives an ordinary proof-producing theorem for
all thirty fixed seed rows. It is isolated from the generic ladder module:
the one-time focused check takes about fifteen seconds and caches as an
`.olean`; it never opens or scans a production archive. The source recurrence,
inner loop, outer row trace, and final V2 log Boolean are proved in
`CLogLadderRefinement.lean`.

The fixed-width primitives, reciprocal and floor-square-root construction,
fixed-header parser and section bounds, event arithmetic, accepted event
transition, complete source-loop trace, and architecture-neutral endpoint
theorem are already proved separately.  The source-level conditional modular
addition, double-and-add multiplication, and repeated-squaring exponentiation
used by the roster's Lucas/Pratt checks are also proved equal to the V2
`ZMod` operation in
`CPUChecker/CModularRefinement.lean`.  These are symbolic theorems over
arbitrary words and do not execute a production roster.

`CPUChecker/CRosterRefinement.lean` now lifts those modular facts through
the complete C-shaped roster trace to the exact V2 `primeRosterCheck`.
`CPUChecker/CPowerLayoutRefinement.lean` likewise covers both source loops
for events and the inverse prime-power map, including checked-power overflow,
square-root, ordering, cursor coverage, and maximal-power guards. Both are
data-independent theorems; neither evaluates the production archive.
`CPUChecker/CU128DivRefinement.lean` proves the complete restoring
128-by-64 division loop returns exact natural-number quotient and remainder
with word bounds. `CPUChecker/CResultEncoderRefinement.lean` proves the
source's complete 120-byte result record is accepted by the strict Lean
decoder as exactly the encoded fields and digest bytes.
`CPUChecker/CCompleteValidationRefinement.lean` composes header, roster,
layout, logarithm rows, the complete scan, and endpoint anchor into the exact
V2 Boolean and package-neutral source claim. Its byte-level theorem also
composes the successful C parser with the strict canonical decoder.
The remaining edge is no longer an archive computation or a mathematical
source lemma: VST/CompCert and the formal loader/ISA path must prove that the
measured pure-entry execution constructs this relational trace, including the
concrete hash and output-byte equalities. The exact Lean target is
`CArchitectureComposition.ArchitectureExecutionSuppliesSuccessfulPureEntry`;
`sourceClaim_of_architectureExecution_viaPureEntry` then yields the source
claim by a small symbolic composition.
`CPUChecker/CX86ELFComposition.lean` further proves that the generic
five-layer `PureEntryRefinementChain` supplies this exact target. The remaining
work is therefore confined to constructing its honest ELF/ISA,
assembler/linker, CompCert, and VST fields for the measured image.

The low-level handoff is now represented without replaying a production
trace locally. `Execution/ArchitectureExecution.lean` defines an exact
measured-code/input/output `load -> step* -> haltedWith` proposition and keeps
the executable-refinement theorem separate from the receipt fact.
`CPUChecker/AttestedAcceptance.lean` and `AttestedAcceptanceV2.lean` then give
the conditional chain from that architecture fact through native acceptance
and V2 reference acceptance to the source claim. The current historical
`AlgorithmReturned` token contains no trace; its temporary bridge to the new
architecture proposition is therefore explicitly classified as trust, not as
a compiler or ISA proof.

VST should then prove the flat C entry implements the same accepted-path
contract in CompCert's Clight semantics. VST is specifically designed to
connect C functional-correctness proofs to CompCert; see the
[Verified Software Toolchain](https://vst.cs.princeton.edu/) and the
[CompCert Clight semantics](https://compcert.org/doc/html/compcert.cfrontend.Clight.html).
The Lean and Rocq specifications still need an auditable cross-prover mapping:
using similar names is not a proof that they are the same proposition.

## Cloud proof-build lane

The concrete Clight/VST/CompCert build contract now lives in
`proof_build/sqrt218/`. Its pinned manifest, Dockerfile, validator, and
cloud-only runner cover preprocessing the single pure-entry translation unit,
Clight generation, the VST/Rocq build, standalone `rocq check`, CompCert
assembly generation, the separately visible system assembler/linker steps,
ELF inspection, and retention of every artifact already named by the compiler
evidence schema.

The exact Lean target is
`ArchitectureExecutionSuppliesSuccessfulPureEntry`. The source semantics is
`successfulPureEntryChecker implementation.identity.neutralContractId`, whose
acceptance relation contains a `CSuccessfulPureEntryTrace`. The VST contract
must recover that trace's exact length, validation result, SHA-256 bytes, and
120-byte output. It does not receive an arbitrary `nativeRun`.

The checked-in manifest intentionally has `execution_ready: false`: the
substantive reviewed `Sqrt218Spec.v` and `Sqrt218Proof.v` files do not yet
exist, and their pins are null. Metadata and current source pins can be
checked in a fraction of a second, but `--require-ready` and the container
entrypoint fail before invoking Rocq or CompCert. See
`proof_build/sqrt218/README.md` for the exact commands and artifact map.

This lane does not move the proof boundary by declaration. A successful VST
build establishes the Clight source property, and CompCert's verified core
reaches abstract assembly. Preprocessing, the concrete extracted compiler
executable, system assembler/linker, final static ELF bytes, ELF loading,
SysV ABI behavior, x86-64 execution, and physical CPU conformance remain
separate edges. The final Azure toolchain image must be selected by registry
digest; a mutable tag is rejected.

The separate metadata-only compiler-discovery plan lives in
`proof_build/sqrt218-discovery/`. It has no VST premise and no authority: it
only specifies the cloud artifacts and exact per-form opcode/prefix inventory
needed to scope an architecture model. Its function-entry ET_EXEC is not a
Linux `_start` and must not be executed as a process. See
[SQRT218_X86_MODEL_FEASIBILITY.md](SQRT218_X86_MODEL_FEASIBILITY.md) for the
MM0/ELF feasibility analysis and the remaining loader, ABI, decoder, and ISA
proof obligations.

## Compiler evidence to retain

A strict compact index for this evidence is now defined by
`schemas/sqrt218-compiler-evidence-manifest.schema.json` and
`tg_verifier/sqrt218_compiler_evidence.py`.  Validate a retained manifest
without opening any artifact named by it:

```bash
python3 tools/tg_sqrt218_compiler_evidence.py \
  compiler-evidence/sqrt218-compiler-evidence.json
```

The file must be canonical JSON and is capped at 256 KiB.  It contains no
artifact paths: artifacts are referenced only by logical ID, positive byte
size, and nonzero lowercase SHA-256.  `manifest_sha256` is the SHA-256 of the
repository canonical JSON encoding of the top-level object with that one
self-hash field removed.  Consequently ordinary manifest validation is
constant in the size of the production certificate and build artifacts.  It
does not invoke `rocqchk`, CompCert, the assembler, the linker, Valex, the
ELF, or the Sqrt218 checker.

The V2 manifest pins:

- the source and preprocessed-source hashes;
- generated CompCert-C and Clight AST hashes;
- VST proof sources and the `rocqchk` result;
- CompCert version, configuration, executable hash, and source revision;
- abstract assembly dump and textual assembly hashes;
- assembler and linker versions and hashes;
- link map, ELF headers, segments, symbols, and dependency audit;
- the exact formal architecture-model digest and Lean declaration, the SysV
  ABI contract digest, and the selected nonzero entry address;
- Valex identity and report if it supports the selected x86-64 output;
- the final static non-PIE ELF hash; and
- the exact theorem/contract identifiers implemented by that ELF.

Both the Lean and Rocq entries repeat the ID and digest of one neutral
contract.  The runtime validator rejects either entry if that binding differs.
It also checks the preprocessed-source-to-CompCert metadata links, the
CompCert-textual-assembly-to-assembler link, inclusion of the assembler output
in the linker inputs, the linker-output-to-ELF link, the link-map link, and
the Valex subject when Valex evidence is present. The formal architecture
entry symbol must equal the ELF entry symbol, and both architecture records
are fixed to x86-64. These checks detect retargeting and incomplete
manifests; they do not establish that any digest has the semantics asserted
by its label.

`CPUChecker/ExecutionClosureIdentity.lean` now gives the Lean-side compact V2
physical-launch identity. It retains structured metadata and its exact
length-framed canonical bytes, and proves their pure-Lean SHA-256 equals the
execution-closure digest in the signed statement. Field equalities cover the
compiler evidence; formal architecture, ELF-decoder, and pure-entry-ABI
models; the measured launcher digest/length; the versioned launcher/control
contract; and the separate pure-entry ELF digest/length/entry. The signed
`hostExecutableHash` is the launcher, while the architecture `MeasuredRun`
executable is the pure-entry ELF. See
[`SQRT218_PHYSICAL_LAUNCH_IDENTITY_V2.md`](SQRT218_PHYSICAL_LAUNCH_IDENTITY_V2.md).

The validator can emit the exact external projection for human review:

```bash
python3 tools/tg_sqrt218_compiler_evidence.py \
  --execution-closure-projection \
  compiler-evidence/sqrt218-compiler-evidence.json
```

This command still emits the legacy V1 compiler-only review projection. V1
uses the unframed domain separator
`sparkinterval.sqrt218-execution-closure-identity.v1` and the same
`decimal_UTF8_byte_length ":" UTF8_bytes` framing, but it does not include a
launcher or launcher/control contract. It is explicitly ineligible for the
V2 physical-launch boundary and cannot construct
`ExecutionClosureIdentity.ExactMetadataBinding`.

The legacy manifest-to-V1 review mapping is exact and deliberately short:

| Lean canonical field | V2 compiler-evidence manifest source |
| --- | --- |
| `compiler_evidence_manifest_version` | top-level `schema_version` |
| `compiler_evidence_manifest_sha256` | top-level `manifest_sha256` |
| `compiler_source_sha256` | `build_chain.c_translation.source.sha256` |
| `compiler_id` | `build_chain.compcert.compiler_id` |
| `compiler_version` | `build_chain.compcert.version` |
| `compiler_binary_sha256` | `build_chain.compcert.executable.sha256` |
| `compiler_configuration_sha256` | `build_chain.compcert.configuration.sha256` |
| `formal_architecture_model_sha256` | `build_chain.formal_architecture.model_sha256` |
| `target` | fixed `azure_sevsnp_cpu` for this x86-64 CPU projection |
| `sysv_abi_contract_sha256` | `build_chain.formal_architecture.sysv_abi_contract_sha256` |
| `neutral_contract_id` | `contracts.neutral.contract_id` |
| `neutral_contract_sha256` | `contracts.neutral.contract_sha256` |
| `elf_sha256` | `build_chain.elf.file.sha256` |
| `entry_point` | `build_chain.formal_architecture.entry_symbol` |

The emitted review object includes the complete canonical text, exact UTF-8
bytes in lowercase hexadecimal, byte count, and SHA-256. Validation checks
every projected field against the source manifest and recomputes all four
representations. It reads only the bounded canonical manifest: it does not
open any artifact named by a digest, run a compiler or checker, register a
production identity, or authorize a receipt or Lean theorem. Tiny synthetic
known-answer and tamper tests exercise this bridge.

Neither the V2 identity theorem nor the legacy V1 review projection is
compiler correctness. The compiler/loader/ISA proof must still give the named
fields their claimed semantics. A future receipt signs the closure digest
rather than the canonical metadata bytes directly, so interpreting that
digest as uniquely naming those bytes retains the standard SHA-256
collision/second-preimage assumption. The V1 projection explicitly records
`sha256_uniqueness_proven: false`; its exact digest recomputation proves no
hash uniqueness claim.

Every manifest carries a fixed non-authorizing `authority` block and exactly
one row for each current residual boundary:

- Lean/Rocq neutral-contract equivalence;
- Rocq kernel, VST, and CompCert assumptions;
- CompCert extraction and the executable that produced the output;
- preprocessing and Clight generation;
- system assembler, linker, and ELF tooling;
- x86-64 ABI, loader, and operating-system runtime;
- physical x86-64 CPU conformance;
- Azure attestation/appraisal; and
- signing keys, the source-pinned registry, and Lean receipt admission.

Deleting or renaming one of those rows fails validation.  Optional Valex
evidence may mitigate part of the assembler boundary, but does not silently
remove it.

The measured-run receipt should commit to the compiler-evidence manifest as
part of the execution closure. CompCert's manual describes Valex as additional
assurance for the assembler/linker boundary, not part of CompCert's core
semantic-preservation theorem. A research alternative that reaches ELF object
files is [CompCertELF](https://flint.cs.yale.edu/shao/papers/compcertelf.html);
its applicability to this exact current x86-64 production chain must be
evaluated before making any claim.

Schema validity or a successful Python validation has deliberately weak
meaning: the metadata is canonical and internally linked.  It never
authorizes a receipt, proves a Lean theorem, proves compiler correctness,
proves machine-code refinement, appraises Azure evidence, or records that a
production execution occurred.  Those fields are fixed to `false`; the
validator's summary repeats the same limitations.

## What remains trusted

Even after the C and CompCert work, the current single Lean axiom still covers
the cross-prover handoff, assembler/linker/ELF and loader behavior, physical
CPU conformance, Azure appraisal, signatures, and exact receipt admission.
The new evidence makes that admission substantially better justified, but it
does not change `#print axioms`.

The replacement boundary is now named, but not yet instantiated:
`Execution/X86ELFPureEntry.lean` factors the ordinary theorem into exact
static-ELF/SysV-ABI/x86 execution, assembler/linker validation, CompCert
`Asm`-to-Clight preservation, and VST/neutral-contract refinement.  It
constructs the generic executable-refinement theorem only when all four
edges are supplied; it supplies none of them by definition. Its static-image
policy explicitly requires bounded non-overlapping load segments, no
writable+executable segment, and an executable entry symbol equal to the ELF
header entry.

`Execution/X86ELFDecoder.lean` now implements the byte-decoding portion in
ordinary Lean: strict little-endian ELF64 `ET_EXEC`/`EM_X86_64` headers,
bounded program and section tables, exact retained program payloads and
`PT_LOAD` slices, non-wrapping memory ranges, and explicit
`PT_INTERP`/`PT_DYNAMIC`/relocation evidence. Tiny kernel-evaluated fixtures
exercise that parser only. It also decodes exact 24-byte `SHT_SYMTAB` rows
through their linked bounded `SHT_STRTAB`, and accepts the selected
`tg_sq218_verify_snapshot_v2` pair only when it is a unique global,
nonempty function in executable memory whose value equals `e_entry`.
`decodeSelectedImage_entryAdmissible` proves the resulting named-entry policy.
`Execution/X86PureEntryABI.lean` separately implements a symbolic finite
loader-memory image, SysV pure-entry initializer, immutable-input/ELF ghost
discipline, and strict return observer. What remains open is the proof that
the concrete measured launcher realizes that model, together with reachable
x86 steps and their compiler-to-binary refinement; neither implemented layer
bypasses those obligations.

Actually narrowing the axiom still requires a closed Lean x86/ELF instance
(or a
proof-producing binary validator tied to one), followed by changing the sole
axiom to return the low-level architecture-execution fact directly.
Source-level C equivalence alone does not establish that edge.

## Cloud-only production sequence

1. Produce the complete V2 certificate in one measured Azure workload,
   optionally using H100s.
2. Run the independently built and measured CPU checker against the immutable
   snapshot in a separate Azure verifier workload.
3. Bind the exact ELF, compiler evidence, input, 120-byte result, challenge,
   target profile, and appraisal policy into the SEV-SNP/vTPM evidence.
4. Appraise remotely and sign the normalized compact receipt.
5. Import only the reviewed receipt, 281-byte result envelope, deployment
   pins, and compiler-evidence identity into the theorem repository.

No step in an ordinary local build opens or replays the production
certificate.

In particular, a local proof check must not reconstruct the production
instruction trace. The reusable Lean theorem quantifies over a trace and
proves that any exact execution of the measured binary has the checker
meaning. The one receipt-indexed trust fact supplies that execution only for
the measured Azure run. Independent full replay, when desired, is a second
cloud workload rather than part of `lake build`.
