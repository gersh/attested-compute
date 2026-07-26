# Architecture execution boundary

`SparkInterval/Execution/ArchitectureExecution.lean` defines the intended
low-level trust boundary for cloud computations. It separates three facts:

1. `ArchitectureExecution` is a finite trace in an exact formal architecture
   model over the complete measured executable, input, and output bytes.
2. `ArchitectureRefinesNativeChecker` is an ordinary Lean theorem connecting
   one exact executable image and entry point to a native checker relation.
3. `ReceiptExecutionFact` is indexed by one receipt hash and carries only the
   first fact. It does not carry application-level acceptance or a
   mathematical theorem.

The intended production composition is:

```text
signed Azure receipt
        |
        | sole trusted per-run import
        v
exact architecture execution
        |
        | proved executable refinement
        v
native checker acceptance
        |
        | proved checker soundness
        v
mathematical certificate claim
```

This layout permits the expensive run and its independent certificate check
to stay in Azure. Local Lean work proves the reusable semantics and
refinement theorems; it does not replay the production workload.

The proof-facing C artifact follows the same split. `make pure-entry` requires
an x86-64 compiler target and fails closed on a host compiler for another
architecture. `make pure-entry-host` is only a freestanding source smoke
check; its image is never receipt-authorizing. This prevents an AArch64 local
artifact, for example, from being silently treated as the x86-64 image named
by the CPU refinement.

`SparkInterval/Execution/X86ELFPureEntry.lean` now gives the CPU route an
axiom-free composition theorem with separate premises for exact static
ELF/SysV-ABI/x86 execution, assembler/linker validation, CompCert semantic
preservation, and VST/neutral-contract refinement.  It is deliberately a
proof-chain interface, not a toy x86 model and not an implementation of
those premises. Its loader policy now states the segment obligations
explicitly: every file slice fits its memory image, all virtual ends fit in
64 bits, load ranges are pairwise disjoint, writable+executable segments are
rejected, and the uniquely selected symbol must equal the ELF header entry
inside an executable segment.

The eventual trusted importer must select a closed, reviewed measurement
scheme and architecture model. It must not quantify over a caller-supplied
`ArchitectureSemantics`: otherwise a caller could choose a model whose step
relation accepts every output. The receipt hash is only an index in this
generic core; cryptographic signature and platform-evidence validation belong
to the closed importer and receipt registry.

The Sqrt218 compiler-evidence manifest V2 now binds the exact formal-model
digest and Lean declaration, SysV ABI contract digest, entry symbol, and
nonzero entry address. Its validator cross-checks the symbol against the ELF
record. This metadata remains non-authorizing, but it closes the obvious
substitution in which evidence for one binary is paired with a more permissive
caller-selected formal machine.

`Sqrt218/CPUChecker/ExecutionClosureIdentity.lean` retains a small canonical
metadata byte string and proves field-for-field agreement among that object,
the application identity, signed statement, and exact measured run. The
direct architecture path contains no legacy returned token. This closes
identity substitution inside Lean, but does not prove compiler or ISA
correctness. Because the current statement signs the metadata digest rather
than the bytes themselves, digest-to-bytes uniqueness retains the standard
SHA-256 collision/second-preimage assumption.

For Sqrt218 the final code-semantics target is
`CArchitectureComposition.ArchitectureExecutionSuppliesSuccessfulPureEntry`.
It says exact measured architecture execution recovers the source
length/result/digest values and constructs the complete successful pure-entry
trace for the exact signed output bytes. Once that theorem is supplied,
`sourceClaim_of_architectureExecution_viaPureEntry` reaches the mathematical
claim without a local arithmetic replay.
`CX86ELFComposition.lean` connects the generic
`PureEntryRefinementChain` to that target; it does not manufacture any of the
five low-level refinement fields.

## What remains for an Azure confidential CPU checker

The generic core is not itself an x86-64 model. A production CPU
instantiation still needs:

- a pinned formal x86-64 ISA semantics covering every instruction in the
  checker binary;
- a proved ELF loader, entry-point, memory-map, ABI, syscall, and termination
  model;
- compiler/linker evidence connecting the reviewed C checker source to the
  exact measured ELF bytes, or a binary-level proof directly against those
  bytes;
- a SHA-256 `MeasurementScheme` instance and a receipt importer that binds the
  Azure SEV-SNP/vTPM measurement to the exact `MeasuredRun`;
- a theorem that an accepting execution's modeled output byte region is
  exactly the signed result envelope; failures and abnormal termination must
  remain non-authorizing, but need not reproduce Lean rejection codes.

CompCert can reduce the source-to-machine-code portion for its supported
target and compiler configuration. It does not by itself prove the Azure
firmware, ELF loader, operating-system, vTPM, or SEV-SNP attestation stack.

## What remains for H100

The existing typed PTX semantics proves properties of the repository's PTX
AST. It is not yet an H100 SASS hardware model. A production H100
instantiation still needs:

- a pinned semantics for the emitted cubin/SASS instruction subset;
- proof that `ptxas` lowering of the exact PTX produces the measured cubin, or
  a direct cubin/SASS proof;
- modeled CUDA launch, grid/thread scheduling, memory layout, synchronization,
  and result-copy behavior;
- a binding from NVIDIA confidential-computing evidence and the surrounding
  Azure SEV-SNP evidence to the exact model, image, input, and output;
- a theorem connecting the SASS execution to the native certificate checker.

Until those proofs exist, an attestation can authenticate a measured run but
cannot establish PTX-to-SASS or hardware semantic conformance.

## Tiny test

`SparkInterval/Tests/ArchitectureExecutionBoundaryTest.lean` instantiates the
interface with a one-step byte-copy machine. The test proves both the machine
trace and the independent checker refinement and then composes them through a
receipt token. It uses no production data, axiom, `native_decide`, or
application-level `Runs` relation.
