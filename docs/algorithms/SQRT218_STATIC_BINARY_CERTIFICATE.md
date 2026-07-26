# Sqrt218 compact static binary certificate

`SparkInterval/Execution/X86StaticBinaryCertificate.lean` is the
data-independent seam between the exact Sqrt218 pure-entry ELF and the future
x86/compiler proof. It does not run the checker, open a Sqrt218 archive, or
replay an instruction trace.

## What Lean checks statically

The version-one certificate contains:

- the certificate version, selected decoder identity, selected symbol, and
  ELF entry address;
- a list of basic blocks;
- for every instruction, its virtual address, exact encoding bytes, reviewed
  opcode/form identifier, and statically visible control-flow form;
- the direct successors and summary identity of every block.

`validate` first calls the existing
`X86ELFDecoder.decodeSelectedImage`. It then checks:

- the symbol is exactly `tg_sq218_verify_snapshot_v2` and the certified entry
  is the decoded ELF entry;
- block starts and instruction addresses are unique;
- the selected entry has a block;
- every row is exactly reproduced by the selected instruction decoder;
- every instruction's retained bytes are the exact slice of an executable
  `PT_LOAD` image, including the ELF-defined zero-fill rule;
- rows are nonempty, range-safe, contiguous, and only the final row transfers
  control; and
- every direct jump, conditional branch, callee, and call continuation names
  another certified block.

The version-one format has no generic indirect-jump claim. Returns are
explicit and have no static target. If cloud discovery finds a jump table or
another indirect transfer, the certificate format and its semantic proof
must be extended; the decoder must not guess a finite target set.

Validation cost is proportional to the small ELF and static certificate.
It is independent of:

- the production Sqrt218 archive size;
- the number of arithmetic records checked in Azure; and
- the number of machine instructions executed by the production run.

The tiny regression fixture is a sub-512-byte `NOP; RET` ELF. It tests exact
byte binding and representative entry, decoder, encoding, and CFG tampering
without executing either instruction.

## Universal semantic theorem

`ExactPureEntryRefinement` fixes the model to:

```text
X86ELFDecoder.decodeSelectedImage
        +
X86PureEntryABI initializer/observer
```

through `X86ELFExactPureEntry.exactDecoderModel`. The x86 step relation is
still an explicit parameter. This is intentional: no x86 semantics has been
smuggled in through certificate metadata.

The proof record separates the previously monolithic ELF/ISA theorem into
three universal obligations:

1. `instructionTraceToBlocks`: every formal x86 trace from the exact loader
   decomposes into steps of certified blocks;
2. `blockSummarySound`: each certified instruction block refines its named
   summary; and
3. `summaryTraceBehavior`: arbitrary summary traces, including loops and
   calls, satisfy the linked-image input/output behavior.

`elfISARefinesLinkedBehavior` composes those fields into the existing
`X86ELF.ELFISARefinesLinkedBehavior` field. The proof is symbolic in arbitrary
input and output bytes. It does not retain or traverse the trace from an
Azure run.

`CPUChecker/CX86StaticCertificateComposition.lean` is the Sqrt218-facing
handoff. Unlike the older generic composition theorem, it fixes the
exact-decoder/ABI model and separately requires the registered native entry
point to equal `tg_sq218_verify_snapshot_v2`. It then accepts only the
remaining assembler/linker, CompCert, and VST behavior-refinement theorems.

The production receipt therefore needs to supply only the compact fact that
one exact measured run occurred. The reusable universal theorem gives that
run its checker meaning.

## How cloud compiler evidence feeds the checker

The non-authorizing cloud build/discovery lane should retain:

- CompCert Csyntax/Clight and abstract assembly;
- exact textual assembly;
- assembler object, linker inputs, link map, and final static ELF;
- selected symbol and load-segment tables;
- normalized disassembly and an exact opcode/prefix inventory; and
- identities and hashes for every compiler, assembler, linker, decoder, and
  certificate generator.

An untrusted cloud tool may generate the basic-block certificate from the
final ELF and disassembly. Lean does not trust that generator: it re-decodes
the ELF and every claimed instruction row. The manifest should bind the
certificate bytes and decoder identity to the same final ELF used by the
receipt.

Compiler evidence is identity and audit evidence, not semantic proof. A
signed manifest cannot replace any theorem below.

## Remaining proof obligations

The following work is still substantive:

1. **Closed x86 decoder and step semantics.** Port or implement precisely the
   instruction forms found by cloud discovery, including exact prefixes,
   ModRM/SIB/addressing, integer/flag behavior, stack operations, calls,
   returns, and faults. Prove decoder determinism and that the certificate's
   `flow` agrees with instruction semantics.
2. **Instruction trace decomposition.** Prove that exact ABI initialization,
   immutable executable memory, instruction fetch, PC updates, calls/returns,
   and every reachable formal x86 step yield
   `instructionTraceToBlocks`. This is where reachability and the absence of
   uncertified code paths are established.
3. **Block summaries and loop invariants.** Prove every finite block once.
   Prove loops and call/return structure through invariants in
   `summaryTraceBehavior`; do not unroll a production trace.
4. **CompCert-to-flat-binary validation.** Relate CompCert blocks, memory
   injections, abstract stack frames, pseudo-instructions, and calling
   convention to the final instruction blocks. Validate assembler encoding,
   branch displacement, padding, symbol placement, relocation resolution,
   link-map layout, and ELF loading. CompCert semantic preservation alone
   does not prove this edge.
5. **VST and cross-prover contract.** Prove the flat C entry's Clight behavior
   and audit an exact mapping to
   `CPureEntryComposition.CSuccessfulPureEntryTrace`.
6. **Physical execution boundary.** Separately prove the measured launcher
   realizes the formal initializer/observer and select a reviewed physical
   x86/SEV-SNP conformance premise. Attestation by itself does not prove
   instruction semantics.

Until those obligations are constructed for one pinned artifact,
`ExactPureEntryRefinement` has no production inhabitant and the static
certificate grants no authority.

## Intended local and cloud split

Local work:

- compile the universal Lean proofs;
- check the small ELF/static certificate;
- check compact receipt and manifest identities; and
- run only tiny decoder known-answer tests.

Azure work:

- build the pinned compiler artifacts;
- produce the large Sqrt218 archive;
- execute the measured checker;
- optionally perform independent full replay; and
- emit the signed confidential-compute receipt.

No ordinary local build should open the production archive or reconstruct the
production instruction trace.
