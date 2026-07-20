# Proof blueprint and NVIDIA-spec traceability

[`SparkInterval/Blueprint.lean`](../SparkInterval/Blueprint.lean) is a
LeanArchitect registry for the declarations at the library's proof and trust
boundaries. It attaches metadata after importing those declarations. Core
mathematical, compiler, machine, certificate, and execution modules do not
import `Architect`, so the graph generator is not part of their proofs.

The registry distinguishes three kinds of edge:

- proof dependencies inferred by LeanArchitect for TeX output and explicitly
  retained as high-level `uses`/`proofUses` metadata for raw JSON output;
- an explicitly documented traceability edge from formal PTX semantics to a
  pinned NVIDIA PTX ISA source; and
- one conspicuously named trust-axiom node for the `ProducedOutcome` supplied
  by an approved external-run certificate. That outcome has an exact
  historical projection and a fail-closed projection to the fixed `Runs`
  semantics of every matching closed registered invocation.

A source citation is not a machine-checked proof that English prose was
transcribed correctly. Likewise, the NVIDIA PTX ISA specifies a virtual ISA;
it does not prove that `ptxas`, SASS, the CUDA driver, or physical hardware
refines the Lean machine. For a particular accepted registered run, the sole
axiom deliberately crosses that physical-to-formal boundary; the graph must
show this as trust, not as a kernel-proved universal refinement.

The formal source layer is deliberately a slice, not a complete PTX ISA
semantics. [`NvidiaPTXSpec.lean`](../SparkInterval/PTX/NvidiaPTXSpec.lean)
pins NVIDIA's [archived PTX ISA 9.0 HTML](https://docs.nvidia.com/cuda/archive/13.0.2/parallel-thread-execution/index.html)
and [PDF](https://docs.nvidia.com/cuda/archive/13.0.2/pdf/ptx_isa_9.0.pdf)
by URL and PDF SHA-256, records clause references for every allowlisted opcode,
and transcribes only the numeric behavior needed for finite-operand directed
`add/sub/mul` and non-NaN `min/max`.
[`NvidiaPTXRefinement.lean`](../SparkInterval/PTX/NvidiaPTXRefinement.lean)
proves that those arithmetic definitions and corresponding one-step typed
machine executions agree with the transcription. It also proves the emitted
module directive prefix and clause coverage of generated opcode traces. It
does not provide formal semantics/refinement for every mapped integer,
memory, conversion, predicate, branch, or special-register instruction, and
division remains outside the typed compiler.

To re-check the external PDF pin independently:

```bash
curl -fsSL \
  https://docs.nvidia.com/cuda/archive/13.0.2/pdf/ptx_isa_9.0.pdf \
  | sha256sum
```

The expected digest is
`207acfec55e860c94809b3a5c2d892f6fe70622105cd421a3c76d93617f6e76a`.

## Generate machine-readable blueprint data

The repository pins the LeanArchitect release matching its Lean
`v4.32.0-rc1` toolchain. Generate the curated graph through the serialized,
memory-capped planner:

```bash
./tools/safe_lake_build.py --blueprint-json
```

The result is
`.lake/build/blueprint/module/SparkInterval/Blueprint.json`. Each node records
its Lean declaration, explicit high-level dependency edges, original source
file, and source range. Build LeanArchitect's LaTeX input—which additionally
performs LeanArchitect's dependency inference—for a separately configured
`leanblueprint` site with:

```bash
./tools/safe_lake_build.py --blueprint-tex
```

That result is
`.lake/build/blueprint/module/SparkInterval/Blueprint.tex`, with per-node
artifacts beside it. The Python `leanblueprint`, Graphviz, and LaTeX rendering
stack is optional and is not installed or invoked by these commands.

Do not run `lake build :blueprintJson` directly in this repository. The safe
planner first builds the exact local dependency closure one module at a time,
holds the full-plan source snapshot and lock, and runs only the single curated
module facet inside the aggregate memory limit.

## Reading the graph

The formal PTX branch should be read from the pinned source metadata through
the finite/non-NaN arithmetic transcription and its refinement lemmas,
typed-machine execution, compiler structure, and generated modeled-run
containment theorem. Clause coverage for an opcode is traceability metadata;
it is not a semantic refinement theorem for that opcode. The branch does not
prove a parser from emitted instruction text to the formal PTX slice and does
not cross the `ptxas`/SASS/driver/physical-GPU boundary.

The dedicated `FormalPTXProgram.statementCheck` identity branch validates and
emits the exact typed batch for the selected target. It reparses the canonical
input into that batch, recomputes the emitted-PTX, canonical-input,
canonical-parameter, and canonical-domain hashes, and requires literal equality
of the target, target-profile hash, and complete artifact-hash record.
`statementCheck_sound` exposes all of those bindings. The target-profile and
artifact hashes are caller-selected identities; this branch still does not
prove that the named cubin was compiled from the emitted PTX or cross the
`ptxas`/SASS/driver/physical-GPU boundary.

The run-certificate branch records a different composition:

1. the unified `RunCertificate.check` dispatches to the DGX-signature or H100-
   attestation structural policy for a private evidence capability;
2. `RegisteredInvocation.statementCheck` may bind the statement's algorithm ID,
   formal definition digest, canonical input, parameters, and domain to one
   constructor of the closed registry; the optional generic literal and
   FormalPTX identity checks remain separate APIs;
3. the sole `accepted_run_certificate_sound` axiom supplies
   `ProducedOutcome.historical` and the fail-closed
   `ProducedOutcome.registered` projection;
4. the derived `accepted_registered_run_sound` theorem exposes the matching
   invocation's fixed `Runs` relation without introducing another axiom;
5. proved checks bind the exact returned certificate text and SHA-256 digest;
6. either the full Lean certificate checker independently recomputes every row,
   or an ordinary registered-algorithm soundness theorem derives a claim from
   `Runs`. For the tutorial this separate axiom-free layer proves the
   executable cube accumulator/divide-once machine, its rational agreement,
   and u64 safety for every loop step.

`outcomeCheck_sound` is the direct historical result of steps 1, 3, and 5: the particular
accepted run returned the exact supplied certificate bytes, with the bound
output digest. `outcomeCheckForRegisteredInvocation_sound` adds the closed
check and `Runs` projection. `outcomeCheckForAlgorithm_sound` instead adds only
caller-pinned literal identity and does not unlock registry semantics. The DGX,
H100, and `accepted_registered_run_sound` public handoff names are proved from
the same axiom, not separate trust nodes.

The current registry contains only `cubicSumDivThreeV1` at canonical input
`20000`. Its `Runs` relation uses `cubicSumDivThreeMachine`, an executable
integer cube accumulator followed by one division. Lean proves the operational
result, agreement with the rational sum, and u64 no-overflow for every cube and
accumulator step. `certifyCubicSumDivThree20000` uses the registered route to
derive exact output `13334666700000000` without `native_decide` or a 20,001-row
witness. These algorithm and bounded-arithmetic proofs are axiom-free, but do
not prove a GPU implementation. There is no positive evidence importer or
accepted certificate instance for this tutorial.

The zeta branch now records `HardyZModel.verifyEndpointFamily` as an explicit
composition node. Its executable premise is the exact-rational family checker,
which validates each bracket and only adjacent ordering pairs; a proved
equivalence lifts those linear comparisons to the all-pairs ordering used by
the generic zero certificate. The theorem also requires proved endpoint
enclosures, bracket-domain bounds, a genuine `HardyZModel`, and the total
zeta-zero-count upper bound. The graph therefore keeps the missing
Riemann-Siegel/Hardy-Z analytic implementation and Turing/argument-principle
count visible rather than treating the Boolean check as sufficient.

The multiplicity branch closes the former count-kind mismatch without a
simplicity assumption. `coe_ncard_le_zetaZeroMultiplicityCount` proves that the
distinct `Set.ncard` is at most the finite sum of
`analyticOrderAt riemannZeta`; `toZetaZeroCountUpperBound` turns an explicit
`ZetaMultiplicityCountUpperBound` into the verifier's distinct-count contract.
The graph marks construction of that analytic upper bound from a checked
Turing/Riemann--von Mangoldt/argument-principle certificate as the remaining
gap. The small count-certificate Boolean check proves only the final numeric
inequality and does not manufacture the analytic premise.

The signed zeta branch records the complete current conditional composition.
`SignedZetaEndpointPayload.payloadCheck` canonically parses the full returned
certificate, proves exact typed equality, checks every arithmetic row, enforces
the paired-singleton endpoint shape, and runs the rational family checker.
`SignedZetaEndpointPayload.check` additionally binds the formal PTX outcome and
returned bytes. Its `ProducedOutcome` crosses
`accepted_run_certificate_sound`; the parser/arithmetic/shape/family facts are
proved independently. This zeta path does not currently use a closed registry
constructor because no zeta checker is registered.

`SignedZetaEndpointPayload.verifyFiniteHeight` then takes a proved Hardy-Z
model, endpoint-enclosure and domain proofs, and a multiplicity upper bound.
Those explicit analytic premises, not attestation, produce the mathematical
finite-height conclusion; the theorem pairs it with the historical provenance
field. The checked-count variant checks a final natural-number comparison but
still requires the analytic multiplicity bound.

The stronger `verifyFiniteHeightFromCheckedRows` edge no longer assumes
endpoint enclosures directly. `CheckedPayload.enclosesEndpoints` derives them
from full-certificate arithmetic soundness once the caller proves
`EndpointRowsRealize`: that the checked expression realizes the selected
evaluator on every singleton endpoint row. Row realization, the Hardy-Z model,
domain bounds, and the analytic count remain explicit premises.

The positive-count branch partitions the symmetric count unconditionally.
Doubling a conventional `(0,T]` multiplicity bound then explicitly requires
`ZetaConjugationMultiplicitySymmetry` and `NoRealAxisZetaZeros`; the graph does
not silently infer either analytic fact. The resulting doubled bound feeds the
same distinct-count and final-verifier path.

The endpoint streaming branch now has a proved logical one-pass transition.
Its state retains the previous bracket, `runEndpointChunk_append` proves exact
resumption across list chunks, and successful streaming implies global family
validity. `runEndpointChunkStream_append` adds a second constant-size boundary
state between independently checked chunks; `verifyEndpointChunkStream` proves
their additive composition reaches the finite-height theorem. The remaining
gap is byte-level: parsing, rolling digests,
resource-bounded allocation/work, I/O, and refinement to this logical runner.

The graph exposes two compact-result routes. The legacy generic FormalPTX
contract still marks `CompactVerifierContract.ExecutionRefines` not ready and
`certifyCompactFiniteHeightZeta` still takes that premise. The preferred closed-
registry route uses `RegisteredCompactVerifierContract` and
`certifyRegisteredCompactVerifierOutcome`: the sole axiom supplies the
particular invocation's fixed `Runs` relation, so only the ordinary `Sound`
theorem from that relation to the decoded claim remains.

`certifyRegisteredCompactFiniteHeightZeta` specializes the preferred route.
It has no `ExecutionRefines` argument, but it is not a completed zeta verifier:
no zeta invocation is registered, and the required checker-soundness theorem
must still include all Hardy-Z, streaming, and total-count mathematics.

Consequently, the full-certificate route gets its mathematical conclusion from
independent checking, while the registered compact route derives mathematics
from `Runs` through a proved soundness theorem and therefore transitively
depends on the sole axiom. The current division-capable zeta tutorial is not an
instance of the polynomial typed-machine theorem.

This branch now includes end-to-end Lean composition for a canonical
monolithic full endpoint payload and theorem-level endpoint chunks, but it is
not yet an end-to-end external
run-bundle workflow. The historical `SignedResultCertificate` name accepts
either production policy through `RunCertificate`; it is not restricted to DGX
signatures:

- the repository has no importer from successful Python DGX signature
  verification or future H100 evidence verification to the corresponding
  private Lean capability;
- a wire run statement binds an output artifact path, size, and file digest,
  but carries no result text, so an importer would have to read the verified
  artifact bytes and construct the Lean `RunStatement.result` binding;
- the current generated-cubin output is `results.bin`, and the real-zeta
  output is `zeta-report.json`; neither is a canonical full result certificate
  accepted by `SignedZetaEndpointPayload`;
- the generic pinned-identity handoff proves only equality with caller-supplied
  literals; the separate `FormalPTXProgram` handoff derives its PTX digest from
  the formal batch and additionally binds canonical input, parameter, domain,
  target-profile, and artifact identities;
- wire bundles can retain a `gpu_ptx` build artifact, but Lean's current
  `ArtifactHashes` abstraction does not carry that digest. The generated-cubin
  workflow instead uses the cubin digest as `algorithmHash`, which must not be
  treated as the digest of `renderUnchecked (buildModule batch)`.

Using the formal-PTX handoff with retained wire evidence still requires a
format-aware importer and a statement whose `algorithmHash` convention is the
formal emitted-PTX digest. Connecting its separately bound device-cubin hash to
that PTX requires an additional compiler-artifact theorem. Neither identity
binding proves that `ptxas`, SASS, the CUDA driver, or hardware refines PTX.

Neither the historical nor registered outcome edge may be read backwards as a
universal physical-program theorem. `RegisteredInvocation.Runs` fixes formal
semantics and establishes one accepted invocation, but it does not say that an
unaccepted future execution implements those semantics or returns the same
bytes. General emitted-PTX/cubin, `ptxas`, SASS, driver, and hardware refinement
remain open.

LeanArchitect is explanatory metadata, not an axiom audit. Run
[`tools/audit_axioms.sh`](../tools/audit_axioms.sh) to enforce the actual
project-axiom allowlist and inspect each public theorem's kernel dependencies.
