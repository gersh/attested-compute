# Sqrt218 x86-64 pure-entry ABI model

`SparkInterval/Execution/X86PureEntryABI.lean` implements the
data-independent state layer between exact ELF decoding and a future x86-64
instruction semantics. It does not execute the Sqrt218 archive and is not an
attestation admission rule.

The model makes the following facts explicit:

- memory is a finite list of byte-addressed regions with read, write, and
  execute permissions;
- each decoded `PT_LOAD` becomes its exact file bytes followed by the exact
  zero fill up to `p_memsz`;
- measured launcher text, immutable input, 120-byte result, four-byte status,
  lower guard, stack, and upper guard are separate regions;
- all regions must fit below `2^64` and be pairwise disjoint;
- both guard regions are nonempty, inaccessible, and adjacent to the stack;
- the stack contains the little-endian return sentinel at the function-entry
  `RSP`, with `RSP mod 16 = 8`;
- `RDI`, `RSI`, `RDX`, and `RCX` contain the SysV AMD64 input pointer, input
  length, result pointer, and status pointer;
- `RIP` is the selected ELF entry and the direction flag is clear; and
- the return observer requires normal return to the measured sentinel,
  `EAX = 1`, little-endian status zero, exactly 120 output bytes, and an
  unchanged immutable input.

The initializer theorem
`initializeEntry_establishes_invariants` proves these facts symbolically for
every admissible layout. The observer theorem
`returnedWith_implies_exact_output_and_status` exposes the exact accepted
output/status facts. The adapter `asPureEntryModel` fills the corresponding
fields of `X86ELF.PureEntryModel`.

The adapter still takes the decoder and x86 instruction relation as explicit
parameters. The exact selected-entry decoder is implemented separately as
`X86ELFDecoder.decodeSelectedImage`; constructing the closed production model
still requires fixing that decoder together with one reviewed x86 semantics.
The adapter wraps the step relation with preservation of immutable input and
ELF ghost snapshots, preventing a transition from changing both the observed
memory and the value against which it is compared. It does not define a
checker-specific step or identify one machine transition with Sqrt218
acceptance.

## What this does not prove

This layer does not yet establish any of the following:

- that a concrete measured loader creates the modeled initial state;
- that the launcher bytes and layout are bound into the signed execution
  closure;
- instruction decoding or the semantics of reachable x86-64 instructions;
- assembler/linker or CompCert-assembly-to-ELF refinement;
- physical CPU conformance;
- that an Azure receipt implies an architecture execution; or
- that any production Sqrt218 certificate was checked.

Those boundaries remain false in the readiness inventory. In particular, a
function-entry `ET_EXEC` is not a Linux process entry and must not be passed
to the existing `execve`/`popen` measured-runner mode.

## Fast local check

Only the symbolic modules need to be checked locally:

```bash
lake build \
  SparkInterval.Execution.X86PureEntryABI \
  SparkInterval.Execution.X86PureEntryABITest
```

This check neither opens a production artifact nor replays a production
instruction trace. The expensive toolchain discovery, machine execution, and
production arithmetic remain cloud-only.
