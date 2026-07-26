# Sqrt218 pure-entry launcher boundary

The Sqrt218 proof-facing ELF is not runnable by the existing ordinary-process
Azure measured-runner mode. A concrete loader/launcher source prototype and a
separate cloud-only build lane now exist, but the source is unreviewed, no
cloud-built launcher artifact is pinned, and no launcher-to-Lean or x86
refinement is proved. Those are explicit production blockers, not a request
to replay the expensive certificate locally.

The retained artifact is a static x86-64 `ET_EXEC` whose ELF entry is the C
function:

```c
int tg_sq218_verify_snapshot_v2(
    const uint8_t *input,
    uint64_t input_length,
    uint8_t result[120],
    uint32_t *status);
```

It is deliberately not a Linux `_start`. A normal Linux process launch does
not put these four function arguments in `RDI`, `RSI`, `RDX`, and `RCX`, and
does not put a C caller's return address on the stack. Treating this ELF as
`argv[0]` would therefore be invalid even if the kernel accepted its ELF
headers. In particular, the function's final `ret` cannot return to a caller
that was never installed.

The existing measured runner calls `subprocess.Popen(..., shell=False)`. That
is the right fail-closed interface for ordinary process executables, but it
does not implement this pure-entry ABI. The `Makefile` labels the artifact
“not a normal process entry.” The new prototype is therefore a distinct custom
launch mode; it has not been integrated into or authorized by that runner.

## Checked-in fail-closed contract

[`SQRT218_PURE_ENTRY_LAUNCHER_BOUNDARY.json`](../../specifications/SQRT218_PURE_ENTRY_LAUNCHER_BOUNDARY.json)
records the exact missing boundary. Its validator and JSON Schema are:

- `tg_verifier/sqrt218_launcher_boundary.py`;
- `tools/tg_sqrt218_launcher_boundary.py`;
- `schemas/sqrt218-pure-entry-launcher-boundary.schema.json`; and
- `tests/test_sqrt218_launcher_boundary.py`.

V1 is intentionally non-authorizing. It identifies the prototype C and
assembly sources and the cloud-build manifest, but has no built launcher path,
hash, or size. All authority flags are false and `--require-ready` always
fails. Merely filling in an artifact hash or changing a Boolean is rejected. A
reviewed execution implementation requires a new manifest kind and validator.

## Concrete source prototype

The source is under
[`launcher_build/sqrt218`](../../launcher_build/sqrt218/README.md). Its
256-byte little-endian control record binds exact size/SHA-256 values for the
launcher, pure-entry ELF, and input, plus the raw off-VM challenge and job
binding. The launcher also requires those challenge/job values to match the
measured Azure worker environment before it opens the ELF or input.

The source implements the following fail-closed mechanisms:

- one-time regular-file snapshots with `openat2` no-symlink resolution,
  stable `fstat` identity, exact size, and SHA-256 checks;
- strict static `ELF64 ET_EXEC EM_X86_64` parsing, including exact
  `SHT_SYMTAB` resolution of one global function whose value equals `e_entry`;
- rejection of `PT_INTERP`, `PT_DYNAMIC`, TLS, relocation sections, W+X,
  executable stack, page-rounded `PT_LOAD` overlap, and offset/address
  incongruence;
- anonymous `MAP_FIXED_NOREPLACE` segment construction followed by final
  `mprotect` permissions;
- a forked child with guarded input/result/status/observation/stack mappings,
  reset and blocked signals, and an exit-only seccomp filter;
- a small assembly trampoline that calculates the actual would-be target
  `RSP mod 16`, clears the direction flag, installs a measured return
  sentinel, and supplies the four SysV arguments; and
- parent-side acceptance checks and one synchronized directory rename that
  publishes the exact 120-byte result with its canonical transcript.

The recorded entry count is precisely one **launcher attempt**. It is not
independent proof that target code did not jump recursively to its own entry.
Linux page granularity also leaves a readable canary prefix for an
arbitrary-length right-aligned input; writes are detected, but reads from that
prefix are not. These facts remain part of the formal-review boundary.

[`cloud-launcher-build.v1.json`](../../launcher_build/sqrt218/cloud-launcher-build.v1.json)
pins the build inputs. Its runner compiles and statically inspects the launcher
only in the cloud. It never executes the launcher and never opens production
input. The retained index is non-authorizing and records the digest-pinned
build image, compiler/assembler/linker/static-libc identities, link map, final
launcher bytes, ELF reports, symbols, relocations, and disassembly.

This side manifest is also **not a signed Lean binding**. The compact
physical-launch V2 identity now has separate launcher artifact hash/size and
versioned launcher-control-contract ID/version/hash/size fields, in addition
to the compiler, formal architecture/ELF/ABI models, target, pure-entry ELF,
and entry symbol. Lean proves that those V2 fields agree with the signed
statement and that legacy V1 identity bytes are ineligible. No reviewed
launcher artifact or production receipt currently instantiates those fields,
however. The remaining blocker is therefore a concrete signed V2 instance
and its launcher-to-initializer/observer refinement, not a missing metadata
slot. An ABI specification alone still does not prove that the launcher bytes
implement it.

Local validation reads only this small manifest. It does not open an ELF,
input archive, result record, or receipt, and does not invoke a compiler,
launcher, checker, architecture trace, or production arithmetic:

```bash
python3 tools/tg_sqrt218_launcher_boundary.py \
  specifications/SQRT218_PURE_ENTRY_LAUNCHER_BOUNDARY.json

# Expected to fail closed until a reviewed implementation and proof exist.
python3 tools/tg_sqrt218_launcher_boundary.py \
  specifications/SQRT218_PURE_ENTRY_LAUNCHER_BOUNDARY.json \
  --require-ready
```

## Exact launch state that must be bound

The future measured launcher must bind the complete ELF bytes and load every
`PT_LOAD` segment at its fixed virtual address with the declared permissions.
It must reject a dynamic interpreter, unapplied relocations, overlapping
segments, and writable executable memory.

At function entry it must establish:

| Register/state | Required value |
|---|---|
| `RDI` | pointer to the exact immutable input bytes |
| `RSI` | exact input artifact byte length |
| `RDX` | pointer to a disjoint, writable, non-executable 120-byte result region |
| `RCX` | pointer to a disjoint, writable, non-executable 4-byte status region |
| `RSP mod 16` | `8`, the System V AMD64 function-entry alignment |
| `[RSP]` | return address into a measured launcher sentinel/observer |
| direction flag | clear |

The ELF segments, input, result, status, stack, and launcher regions must be
pairwise disjoint where their roles require it. The input must be read-only
during the entry and must hash identically before and after it. The result and
status regions start zeroed. The stack is non-executable, bounded, and
surrounded by guard pages.

The measured observer may accept only a normal return to the measured
sentinel with:

- 32-bit C integer return value `EAX = 1`, meaning the wrapper wrote a record;
- little-endian `uint32_t` status equal to zero;
- exactly 120 result bytes, retained without transformation;
- unchanged input bytes; and
- no signal, fault, or timeout, with exactly one launcher attempt.

The attempt counter does not independently detect recursive target re-entry;
the concrete prototype limitation described above remains explicit.

## Receipt and machine identity

The attested run must bind, at minimum:

- the off-VM challenge and measured job digest;
- exact launcher and pure-entry ELF SHA-256/size pins;
- exact input SHA-256/size;
- exact 120-byte output SHA-256/size and the four-byte status;
- the return-observer record;
- the VM image measurement;
- CPU vendor, family, model, stepping, and microcode version;
- the AMD SEV-SNP report; and
- the vTPM PCR 23 quote.

Attesting those values supports and authenticates the run claim under the
measured-runner and appraisal trust model. SEV-SNP and vTPM evidence alone is
not a proof that a particular user-space instruction trace executed. It also
does not prove that the launcher implements the Lean state relation.

## Formal connection still required

The concrete loader/trampoline must be connected to
`SparkInterval.Execution.Architecture.X86ELF.PureEntryModel`:

- its pre-entry construction must refine `PureEntryModel.initializeEntry`;
- its sentinel/output observation must refine
  `PureEntryModel.returnedWith`; and
- exact ELF loading plus the reachable x86-64 execution must discharge the
  machine-level refinement in the pure-entry chain.

Before a receipt can authorize this route, the execution-closure identity
format must be versioned and extended to commit at least the launcher
SHA-256/size and the reviewed launch-contract digest. Those fields must occur
both in the signed canonical projection and in
`NativeImplementationIdentity`, with literal field-equality theorems analogous
to the existing ELF and ABI equalities. A later compiler-evidence/receipt
validator must derive them from the retained artifact closure rather than
accepting caller-supplied strings.

A practical source implementation now exists, but its toolchain closure and
final executable must first be produced by the cloud build and reviewed. The
launcher-to-model proof and signed runner integration remain absent. The heavy
Sqrt218 input is reserved for the later measured Azure CPU job; local work
remains source/static metadata validation and tiny known-answer tests.

Until those items exist, the honest boundary is:

```text
source-level Sqrt218 C trace: represented in Lean
compiler / assembler / linker / ELF / x86 proof: incomplete
concrete pure-entry launcher source: present, unreviewed, non-authorizing
cloud-built launcher artifact: absent
launcher initializer and observer refinement: absent
Azure attested pure-entry run: absent
```
