# Sqrt218 pure-entry launcher prototype

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

This directory contains a concrete but non-authorizing Linux/x86-64 loader
prototype for the Sqrt218 proof-facing pure-entry ELF. It exists because that
ELF deliberately enters at a four-argument C function and cannot be launched
with normal `execve`.

The launcher:

- reads an exact 256-byte little-endian control record;
- requires its raw challenge and job-binding values to match the measured
  Azure worker environment;
- checks exact SHA-256 and size pins for itself, the pure-entry ELF, and the
  input snapshot;
- requires a static little-endian `ELF64 ET_EXEC EM_X86_64` target with no
  `PT_INTERP`, `PT_DYNAMIC`, TLS, relocation sections, W+X load segment, load
  overlap, or executable stack;
- also requires System V OS ABI/version zero, zero ELF identification padding,
  zero processor flags, and an all-zero section-header zero, matching the
  closed Lean decoder's inexpensive header policy;
- resolves exactly one global default-visible `STT_FUNC`
  `tg_sq218_verify_snapshot_v2` from `SHT_SYMTAB`, requiring its value to equal
  `e_entry` and its nonzero extent to lie in executable loaded bytes;
- copies each `PT_LOAD` from the already-hashed ELF snapshot into anonymous
  `MAP_FIXED_NOREPLACE` pages and then applies its final permissions;
- gives the child disjoint guarded mappings for a read-only input snapshot,
  120-byte result, four-byte status, observation record, and 8 MiB stack;
- resets and blocks signals, then installs an exit-only seccomp filter before
  the assembly trampoline performs its one launch attempt; the trampoline's
  32-byte restoration header is at the top of the usable stack, above target
  entry `RSP` and immediately below the high guard page;
- accepts only a normal child exit after return to the measured assembly
  sentinel with actual target-entry stack alignment `RSP mod 16 = 8`,
  `EAX = 1`, zero status, intact canaries, unchanged input digest, and a
  structurally consistent 120-byte result; and
- publishes `result.bin` and a canonical transcript together by one
  `renameat2(RENAME_NOREPLACE)` of a synchronized staging directory.

The input is right-aligned against a trailing guard page. Linux page
granularity means an arbitrary-length input can still have a readable canary
prefix within its first page; this prototype detects writes to that prefix but
cannot detect reads from it. The result and status are likewise right-aligned:
overruns hit a guard page and underruns change checked canaries.

## Control record

All integers are unsigned little-endian. The file is exactly 256 bytes.

| Offset | Width | Field |
|---:|---:|---|
| 0 | 8 | `SQ218L1\0` |
| 8 | 4 | version `1` |
| 12 | 4 | width `256` |
| 16 | 8 | launcher size |
| 24 | 32 | launcher SHA-256 |
| 56 | 8 | pure-entry ELF size |
| 64 | 32 | pure-entry ELF SHA-256 |
| 96 | 8 | input size |
| 104 | 32 | input SHA-256 |
| 136 | 32 | raw off-VM challenge |
| 168 | 32 | job-binding SHA-256 |
| 200 | 4 | timeout seconds, `1..604800` |
| 204 | 4 | stack MiB, exactly `8` |
| 208 | 48 | zero |

The environment guard prevents accidental local production dispatch. It is
not attestation evidence. An appraiser must still authenticate the measured
runner transcript and bind this launch control, launcher build artifact, pure
ELF, input, result, VM image, CPU/microcode identity, SEV-SNP report, and vTPM
quote.

## Separate cloud build

`run_cloud_launcher_build.sh` is a source/toolchain/output build lane. It
requires `TG_CLOUD_LAUNCHER_BUILD=1`, a digest-pinned final build image, an
absent output directory, and the checked-in manifest's exact source pins. It
compiles and inspects the launcher but contains no command that runs it or
opens a Sqrt218 production input.

The image bakes that exact source closure under `/workspace/repository`; the
ACI job therefore does not silently rely on a host checkout. A distinct Azure
Files share is mounted at `/workspace/export`, and `TG_OUTPUT_ROOT` names an
absent leaf below it. The runner refuses an existing leaf, writes the retained
closure there, and the operator exports it by content rather than relying on
ephemeral container storage.

The ACI plan assigns `${ACI_IDENTITY_RESOURCE_ID}` to the container and passes
that same user-assigned managed identity through `--acr-identity`. The
operator must grant that identity `AcrPull` on the private registry before
creating the container; mutable registry credentials or an implicit platform
identity are not an accepted substitute.

The retained artifact index binds the final image digest, source closure,
compiler/assembler/linker/static-libc reports and hashes, link map, ELF
reports, symbol table, relocations, disassembly, and final launcher bytes.

This is deliberately not any of the following:

- a reviewed launcher release;
- a VST proof of the launcher;
- a proof of the system assembler, linker, static PIE startup, kernel ELF
  loader, seccomp implementation, x86 CPU, or microcode;
- a refinement to Lean's `PureEntryModel.initializeEntry` or `returnedWith`;
- a signed execution-closure binding; or
- authority for a Lean theorem.

No local build or launch is part of the review workflow. Local checks validate
small source pins, schemas, shell syntax, and source structure only.
