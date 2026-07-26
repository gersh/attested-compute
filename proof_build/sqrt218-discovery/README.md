# Sqrt218 compiler-discovery metadata

This directory specifies a separate, non-authorizing compiler-discovery lane.
Its only purpose is to obtain the concrete instruction and ELF inventory
needed to scope a small MM0-derived Lean 4 x86-64 model.

The checked-in lane is metadata-only and intentionally unready. There is no
runner or discovery container yet, and the manifest fixes
`execution_ready`, every authority field, local tool invocation, generated
ELF execution, and production-certificate access to `false`. Changing any of
those values invalidates both the strict validator and the JSON Schema.

Validate the metadata without reading a source file or artifact:

```bash
python3 tools/tg_sqrt218_compiler_discovery.py validate \
  proof_build/sqrt218-discovery/discovery.v1.json
```

`show-plan` displays the exact future cloud command templates and retained
artifact names. Neither command invokes CompCert, Binutils, Docker, Azure, an
ELF, or the Sqrt218 checker.

## Required discovery result

The future pinned runner must retain the preprocessed source, generated
CompCert Csyntax and Clight ASTs, textual front-end renderings, `.sdump`,
assembly, object, static ET_EXEC ELF, link map, `readelf` reports, raw
`objdump` disassembly, and exact per-form instruction inventories.

The inventory is a syntactic direct-control-flow closure derived from the
retained decoder output and checked against the ELF bytes. Every instruction
record must include its address, file offset, exact bytes, prefix bytes,
candidate opcode bytes, mnemonic/operand form, and direct successors.
Every instruction and aggregate form must also carry the exact gap-tag
classification for `0x66`, two/three-operand `IMUL`, `BSWAP`, `SHLD`,
SSE/XMM, `ROL`/`ROR`, VEX, EVEX, and unknown encoding forms. The structural
audit must retain every `PT_LOAD` row, the load count, and exact permissions;
one-load compatibility is reported rather than assumed.
Indirect transfers, unresolved targets, targets into instruction middles, or
decoder/byte disagreement must prevent a complete inventory. Even a complete
inventory is not a proof of decoding, reachability, ELF loading, x86
semantics, ABI behavior, or hardware conformance.

The ELF entry is an ordinary C function selected for analysis. It is
explicitly **not** a Linux `_start`: process startup would not supply its four
SysV function arguments or a valid return continuation. A separately proved
direct-call initial state or launcher/loader remains necessary, and this lane
must never execute the generated ELF as a process.

The wider feasibility analysis and remaining proof boundary are documented
in [SQRT218_X86_MODEL_FEASIBILITY.md](../../docs/algorithms/SQRT218_X86_MODEL_FEASIBILITY.md).
GNU documents the retained inspection formats in the official
[objdump](https://sourceware.org/binutils/docs/binutils/objdump.html) and
[readelf](https://sourceware.org/binutils/docs/binutils/readelf.html)
manuals.
