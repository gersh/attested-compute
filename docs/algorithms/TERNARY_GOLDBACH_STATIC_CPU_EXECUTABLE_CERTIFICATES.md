# Static-CPU executable certificates for the external campaigns

`SparkInterval.Execution.Architecture.StaticCPUExecutableCertificate` is the
shared, production-data-free machine-refinement interface for all ten
external campaigns, whose proof-authorizing terminal target is an Azure
confidential CPU. Ramaré--Zúñiga, Goldbach, and Dirichlet may use H100 child
producers, but their registered terminal executables are CPU finalizers which
must verify the complete child-receipt graph.

The interface extracts the strongest reusable part of the Sqrt218 static-ELF
route. Its `ofExactDecoderRefinement` adapter embeds the existing
`X86StaticBinaryCertificate.ExactPureEntryRefinement` without weakening any
instruction, block-summary, or trace theorem.

For one exact reviewed registry value, a `Certificate` contains:

1. the CPU target and equality between the reviewed formal machine and a
   static-ELF `PureEntryModel`;
2. validation of the compact block certificate against the exact retained ELF
   bytes;
3. a universal theorem from every formal instruction trace to the certified
   block trace;
4. pointwise block-summary soundness and a universal summary-trace behavior
   theorem;
5. separate assembler/linker, compiler, and source-to-fixed-checker behavior
   refinements.

It contains no production input, execution trace, mathematical claim, or
caller-selected final proposition. Intermediate behaviors cannot create a
claim: each must be connected by a universal refinement and the last relation
is the native checker fixed by the campaign type.

`InstalledCertificate` additionally contains an actual
`ReviewedArchitectureRun` and the equality saying that exact value is
installed by the closed `reviewedRun` selector. Only this non-vacuous type can
produce the `ClosedExecutableRefinement` consumed by
`CompactExternalAtomRegisteredCapstone`. The proof identifies any queried
reviewed value with the installed `some` value. It never derives a refinement
from the current `none` branch.

## Smallest campaign and first missing theorem

The smallest real external CPU campaign is the CH25 A7 boundary replay. The
current full replay is a Python/FLINT process. It is not a static pure-entry
x86-64 ELF, and its compact physical pins for the executable, entry point,
machine semantics, and receipt are still null. Consequently there is no
honest value of `A7BoundaryInstalledCertificate`.

The first missing physical artifact is therefore a reviewed static
pure-entry A7 runner and a closed `ReviewedArchitectureRun` containing its
exact ELF, entry point, CPU semantics, launcher closure, input and result
pins. After that data exists, the first new semantic theorem is the
`StaticPureEntryRefinement.instructionTraceToBlocks` field for that exact
runner: every trace of the selected x86 model must refine the checked block
partition. Static validation alone does not prove this theorem.

No executable refinement, reviewed receipt, or source atom is promoted by the
present interface.

Focused verification:

```bash
lake env lean SparkInterval/Execution/StaticCPUExecutableCertificate.lean
lake build +SparkInterval.Execution.StaticCPUExecutableCertificate
lake env lean SparkInterval/TernaryGoldbach/CompactExternalAtomRegisteredCapstone.lean
lake env lean SparkInterval/Tests/StaticCPUExecutableCertificateTest.lean
```
