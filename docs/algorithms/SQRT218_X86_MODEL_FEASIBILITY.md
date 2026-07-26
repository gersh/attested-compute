# Sqrt218 x86-64 model feasibility

This note scopes the remaining machine-code proof for the fixed-width
Sqrt218 CPU checker. It does not run the checker, open a production
certificate, or claim that a measured ELF already refines the Lean source
relation.

The source-side target is
`CArchitectureComposition.ArchitectureExecutionSuppliesSuccessfulPureEntry`.
The desired machine theorem is data-independent: every execution of one exact
ELF entry, on arbitrary bytes satisfying the ABI preconditions, must construct
`CPureEntryComposition.CSuccessfulPureEntryTrace`. A production receipt then
supplies only one exact measured execution. Lean must not replay that
production instruction trace.

## MM0 as a model seed

Mario Carneiro's
[x86-64 verification work](https://doi.org/10.4230/LIPIcs.ITP.2019.19)
is the best small existing seed found in this audit. The reviewed upstream
revision is
[`f30b37eed283502835ff9fd62c827f23b2d3a71e`](https://github.com/digama0/mm0/tree/f30b37eed283502835ff9fd62c827f23b2d3a71e)
and is released under
[CC0 1.0](https://github.com/digama0/mm0/blob/f30b37eed283502835ff9fd62c827f23b2d3a71e/LICENSE.txt).
Any adapted files must retain explicit upstream provenance and paper
attribution even though the license permits reuse.

The live typed model is
[`mm0-lean/x86/x86.lean`](https://github.com/digama0/mm0/blob/f30b37eed283502835ff9fd62c827f23b2d3a71e/mm0-lean/x86/x86.lean),
with decoder lemmas in
[`mm0-lean/x86/lemmas.lean`](https://github.com/digama0/mm0/blob/f30b37eed283502835ff9fd62c827f23b2d3a71e/mm0-lean/x86/lemmas.lean).
It targets Lean 3.20. The current `mm0-lean4` directory contains no x86 port.
The newer MM0-level definitions and proofs are
[`examples/x86.mm0`](https://github.com/digama0/mm0/blob/f30b37eed283502835ff9fd62c827f23b2d3a71e/examples/x86.mm0)
and
[`examples/x86.mm1`](https://github.com/digama0/mm0/blob/f30b37eed283502835ff9fd62c827f23b2d3a71e/examples/x86.mm1).

The model already has the useful core shape:

- 16 general-purpose 64-bit registers, RIP, arithmetic flags, and
  permissioned byte memory;
- REX, ModRM, SIB, RIP-relative and base/index addressing;
- integer moves, extensions, arithmetic, comparison, Boolean operations,
  shifts, unsigned multiply/divide, and `lea`;
- conditional moves, `setcc`, calls, jumps, return, and stack operations; and
- enough ELF/process structure to demonstrate exact binary I/O reasoning.

It is deliberately incomplete. Known gaps that may matter for CompCert output
include the `0x66` operand-size prefix, two/three-operand `imul`, signed
`idiv`, `bswap`, `shld`, SSE, string instructions, and modern multi-byte
NOPs. `rol` and `ror` decode, but their execution relation is explicitly
empty. The exact cloud-produced instruction inventory, not this expected
list, must determine the port's scope.

## ELF and pure-entry differences

The Lean 3 model contains no ELF decoder. The MM0 ELF relation accepts a much
smaller format than an ordinary GNU-linked executable: little-endian ELF64
`ET_EXEC`, one `PT_LOAD`, no section headers, and an entry inside that
segment. It does not parse multiple segments, symbols, dynamic sections, or
relocations.

Its initial state is a Linux process entry with an `argc`/`argv` stack. The
Sqrt218 pure entry instead needs a new SysV relation fixing:

- `RDI` to the immutable snapshot;
- `RSI` to its exact length;
- `RDX` to a writable 120-byte result region;
- `RCX` to a disjoint writable status word;
- stack alignment, permissions, and a return sentinel; and
- the final observation of the exact 120 result bytes after normal return.

A deliberately minimal one-load-segment ELF would make the decoder and loader
proof smaller. An ordinary multi-segment GNU ELF is easier operationally but
requires a materially larger decoder, symbol/layout certificate, and loader
proof. The cloud discovery lane should retain enough ELF metadata to make
this choice from the actual CompCert artifact.

## Implemented Lean 4 ELF64 decoder

`SparkInterval/Execution/X86ELFDecoder.lean` now provides the first concrete,
data-independent Lean 4 layer. It accepts only little-endian ELF64
`ET_EXEC`/`EM_X86_64` images with System V `EI_OSABI = 0`,
ABI version zero, and ordinary header counts. It parses the exact ELF header
and every program header, retains every complete program-header file payload
and all raw flags, and constructs each `PT_LOAD` slice only after
subtraction-form file bounds checks. Address-range checks use
unbounded `Nat`, so a 64-bit wrap cannot make a load range appear valid.
Malformed header tables, unknown load permission bits, W+X loads, invalid
alignment, file-size/memory-size mismatch, empty or overlapping loads, and
an entry outside executable mapped memory all fail closed.

When section headers exist, the decoder checks their table and file ranges,
requires the all-zero section-zero sentinel, and conservatively marks
`SHT_REL`, `SHT_RELA`, or `SHT_RELR` as unapplied-relocation evidence. It
independently exposes `PT_INTERP` and `PT_DYNAMIC`. The static pure-entry
policy therefore rejects those features without relying on external
`readelf` prose. Tiny sub-520-byte Lean fixtures cover acceptance and
representative magic, truncation, range, overflow, W+X, interpreter, dynamic,
relocation, section-sentinel, symbol-link, name, binding, type, definition,
entry, and duplicate-definition tampering; they do not execute the checker.

Exact selected-symbol resolution is now implemented for ordinary
`SHT_SYMTAB` sections linked to a bounded `SHT_STRTAB`. Every 24-byte ELF64
row and NUL-terminated UTF-8 name is decoded. Unrelated GNU rows, including
`STT_FILE` with `SHN_ABS`, retain their raw binding, type, and section index;
the stricter rules apply only to `tg_sq218_verify_snapshot_v2`. That selected
definition must be unique, `STB_GLOBAL`, `STT_FUNC`, nonempty, defined in an
executable section, and equal to `e_entry`. The structural decoder exposes at
most that selected name/address pair through `ELF64Image.symbols`.
`decodeSelectedImage` rejects stripped images, a missing or duplicate
selected definition, malformed linked tables, and an entry-address mismatch.
`decodeSelectedImage_entryAdmissible` proves that every returned image
satisfies the named `ELF64Image.EntryAdmissible` policy.

`SparkInterval/Execution/X86PureEntryABI.lean` now supplies the next
data-independent layer. It maps every decoded `PT_LOAD` to exact file bytes
plus zero fill, requires a finite pairwise-disjoint address-space layout,
models immutable input, 120-byte result, four-byte status, inaccessible stack
guards and a measured return sentinel, establishes the SysV argument/RSP/RIP
and direction-flag invariants, and defines a strict normal-return observer.
Its future instruction relation is still an explicit parameter and is wrapped
to preserve immutable input and ELF ghost snapshots.

The remaining gaps therefore begin at concrete launcher-to-initializer
refinement, reachable x86 instruction decoding/semantics, and the
CompCert-to-binary validator. The mathematical ABI state model is present;
the physical launcher has not yet been proved to realize it.

## The central CompCert-to-binary gap

CompCert 3.17 supports x86-64, but its verified theorem ends at abstract
assembly. Its
[`x86/Asm.v`](https://github.com/AbsInt/CompCert/blob/7b1f02b09954b9b916eb2a91d283c9b5355bf172/x86/Asm.v)
uses block-structured memory and pseudo-instructions such as stack-frame
allocation/freeing. Unverified OCaml code, including
[`x86/Asmexpand.ml`](https://github.com/AbsInt/CompCert/blob/7b1f02b09954b9b916eb2a91d283c9b5355bf172/x86/Asmexpand.ml),
expands those constructs before the system assembler and linker produce flat
machine code.

Matching instruction names is therefore insufficient. A rigorous bridge
must relate:

- CompCert blocks and abstract stack frames to flat SysV memory;
- pseudo-instruction expansion to concrete instruction sequences;
- instruction encoding, padding, and branch displacement;
- symbol/data placement and resolved relocations;
- final ELF loading; and
- each reachable concrete instruction step to the corresponding CompCert
  behavior.

The realistic reusable solution is a translation validator. A cloud build
emits the exact CompCert assembly, object, link map, ELF, and disassembly.
An untrusted generator produces a compact layout/instruction certificate.
Lean checks that certificate once, without executing the finite Goldbach
computation or unrolling its loops.

## Recommended sequence

1. Run the non-authorizing compiler-discovery lane on Azure. Retain exact
   Csyntax/Clight ASTs, CompCert abstract/text assembly, object, link map,
   final ELF, disassembly, opcode forms and prefixes, load segments, symbols,
   and relocations.
2. Check the discovered ELF and exact selected static symbol against the
   implemented bounded decoder. Constrain the build to retain the accepted
   `SHT_SYMTAB`/`SHT_STRTAB` form.
3. Instantiate the implemented Sqrt218 pure-entry initializer/observer with
   the selected decoder and prove the measured launcher realizes that state.
4. Port the smallest MM0 decoder/step fragment to Lean 4, adding only observed
   instructions and proving decoder/step determinism.
5. Build a certificate-producing translation validator from CompCert
   assembly through the final loaded instruction image.
6. Prove that the validated image satisfies
   `successfulPureEntryChecker`, then compose the existing
   `CX86ELFComposition.sourceClaim_of_x86ELFExecution`.

Only step 1 is a compiler discovery run. It is cloud-only and
non-authorizing. None of these steps requires a local production certificate
or local arithmetic replay.

## Effort estimate

For an engineer already experienced with Lean and machine semantics:

- narrow Lean 4 MM0 port plus exact observed integer instructions:
  approximately 4–8 person-weeks;
- concrete launcher/load-image refinement on top of the implemented symbolic
  ABI model: approximately 2–4 person-weeks, with additional work only if the
  discovered ELF exceeds the currently decoded multi-segment/static-symbol
  format; and
- first CompCert-to-flat-x86 validator and simulation proof:
  approximately 3–6 person-months.

After that reusable bridge exists, checking another pinned binary should take
minutes, with additional proof work only when it introduces a new instruction
or relocation form.

## Why CompCertELF is not the short route

The primary
[CompCertELF artifact](https://github.com/CertiKOS/compcert/tree/d537ac441ff2fb25afbab3c423499b71da868e22)
uses CompCert 3.0.1/Coq 8.6 and targets x86-32. Its verified result is a
relocatable `ET_REL` object, as represented in
[`elf/RelocElf.v`](https://github.com/CertiKOS/compcert/blob/d537ac441ff2fb25afbab3c423499b71da868e22/elf/RelocElf.v);
the final executable link remains external. The
[paper](https://flint.cs.yale.edu/flint/publications/compcertelf.pdf)
and
[project page](https://flint.cs.yale.edu/shao/papers/compcertelf.html)
are valuable design references, but porting that chain to current CompCert,
AMD64, modern relocations, and final `ET_EXEC` loading is not shorter than the
MM0-plus-validator route.

The artifact also inherits the old non-commercial CompCert license except
where individual files say otherwise. It must not be copied wholesale into
this MIT repository.
