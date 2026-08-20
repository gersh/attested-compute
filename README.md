# attested-compute

*(The Lean library is `SparkInterval`; the repository was renamed to say what
the project does.  `github.com/gersh/gpu_prover` and `.../sparkinterval` both
redirect here.)*

**Calculate once, verify once, use the result as a theorem.**

Infrastructure for one problem: you have a computation too expensive for anyone
to repeat, and you want its result usable as a proved fact rather than a claim
taken on faith.  Run it inside a confidential VM, have the hardware sign both
the code it measured and the results it produced, and let the proof assistant
check that certificate in its kernel.  What remains admitted is a single
axiom — *that a machine executed the artifact* — and it cannot be applied
without a signature the hardware vouches for.

**Start here:** [`docs/OVERVIEW.md`](docs/OVERVIEW.md) · deployment:
[`docs/PHALA_TDX_DEPLOYMENT.md`](docs/PHALA_TDX_DEPLOYMENT.md) · mechanism:
[`docs/ATTESTED_COMPCERT_RUNS.md`](docs/ATTESTED_COMPCERT_RUNS.md) · why believe
it: [`docs/TRUSTING_THE_ENCLAVE.md`](docs/TRUSTING_THE_ENCLAVE.md)

The subject-matter examples below (ternary Goldbach, GRH/Platt) are
illustrations of the mechanism, not its purpose.

> **Work in progress:** SparkInterval is an early research prototype seeking
> collaborators. Full result certificates can already be generated, checked,
> imported, and used as Lean theorems. One computation is closed end to end
> from a real Intel TDX run. Do not treat the repository or its development key
> as an attestation service.

SparkInterval is an open project built around a simple idea: **calculate once,
verify once, use the result as a theorem**. The expensive bounded calculation
can run outside Lean on CPUs or GPUs. Its formula, inputs, numeric semantics,
coverage, result, and hashes remain available in a certificate. A proved Lean
checker turns that certificate into an ordinary theorem that later Lean code
can import and compose without rerunning the original calculation.

The flagship worked example implements the computation behind Platt's
verification of the Generalized Riemann Hypothesis (arXiv:1305.3087): a
rigorous GPU interval evaluator isolates zeros of Dirichlet L-functions
on the critical line, runs are bound into signed-eligible canonical
bundles, and Lean kernel-checks the zero certificates into conditional
finite-strip GRH theorems — see the
[GRH POC quick start](#grh-poc-quick-start) below.

For provenance-sensitive computations, the Azure path is designed to use measured code
inside a secure execution environment: AMD SEV-SNP plus vTPM for CPU jobs, and
that CPU boundary together with NVIDIA H100 confidential computing for GPU
jobs. A separately pinned verifier appraises the hardware evidence and binds
the exact program, inputs, bounds, output, challenge, and completion status
into a signed computation receipt. A reviewed source registry can then admit
that receipt by digest for later Lean proofs. The tracked registry is empty,
so this is implemented infrastructure rather than evidence that a production
run has happened.

For a fast local control-plane check, run `make local-static`. It validates
the cloud-only guards, compact Sqrt218 build/launcher/discovery manifests, and
the pure-entry source callgraph without compiling or executing a production
worker, opening a production certificate, or reconstructing an instruction
trace.

In this project, **bounded arithmetic** means a finite computation whose input
domain, numeric representation, resource/coverage bounds, and claimed result
are explicit. It does not mean that arbitrary numerical output becomes true by
being signed. Lean still checks the certificate mathematics or a registered
algorithm-soundness theorem; the axiom is reserved for the irreducibly external
fact that a particular accepted execution occurred.

## From calculation to a Lean theorem

The full-certificate path works today:

1. **Specify the calculation.** The certificate carries an expression AST,
   canonical input rows, binary64 interval results, algorithm identity, and
   hashes. The formula is inspectable and independently reproducible.
2. **Calculate outside Lean.** A CPU reference evaluator or GPU implementation
   performs the finite sweep. GPU acceleration changes how quickly the witness
   is found; it does not change the theorem statement.
3. **Check the witness in Lean.** The generated module materializes the typed
   certificate. SparkInterval's proved checker reevaluates its interval
   arithmetic with exact rational semantics and derives row-wise or finite-sum
   bounds.
4. **Import the result.** Put that generated module in a Lean library and give
   the exported theorem a friendly application-level name. Downstream modules
   import the compiled `.olean`; they do not rerun the GPU job or re-execute the
   certificate module's commands on every import.

For example, after placing the generated module at an importable path, a small
wrapper can consume the checked-in example certificate like this:

```lean
import MyProject.Certificates.IntervalSweep

open SparkInterval.GeneratedCertificate.C_b4ba4bc319743cf65a486c216897268e0a98107ea635404fa3f7825305755ba9_B_4010000000000001_M_kernel

theorem certifiedApplicationBound
    {i : Nat} (hi : i < certificate.rows.size)
    {x : ℝ} (hx : certificate.RowRealizes i x) :
    x ≤ (applicationUpperBound : ℝ) :=
  application_upper_bound_sound hi hx
```

The long namespace deliberately binds the certificate digest, requested bound,
and checking mode. An application library can hide it behind a stable theorem
name. The checked-in
[`GeneratedFullCertificate.lean`](examples/lean-result-certificate/GeneratedFullCertificate.lean)
shows the exact declarations produced today.

Lean does perform work when the certificate module is first built or rebuilt.
It checks the supplied witness rather than repeating the potentially much more
expensive search or numerical sweep that produced it. Once the resulting
`.olean` is current, Lean imports the serialized environment without
re-executing all of the source module's commands. This makes the certificate a
reusable library artifact rather than a computation embedded in every
downstream proof.

See [Using certificates from Lean](docs/LEAN_INTEGRATION.md) for the complete
producer, publisher, and consumer model.

## Why not put the whole computation in `native_decide`?

`native_decide` is valuable when a decidable proposition can be evaluated
quickly enough during elaboration. Lean evaluates it as compiled native code
and records an axiom dependency for that native result. Large computations can
still make clean builds expensive, require substantial local resources, and
tie every rebuild of that module to the calculation.

SparkInterval offers a different tradeoff:

- the expensive calculation can use parallel CPU/GPU infrastructure outside
  the Lean build;
- the formula, bounded domain, and independently replayable witness remain
  explicit;
- a smaller, proved checker validates the resulting witness;
- the default direct typed-certificate theorems use kernel reduction and do not
  depend on `native_decide`; and
- the compiled certificate theorem can be cached, distributed, imported, and
  reused by many proofs.

This is not yet a universal zero-cost replacement. A clean build still checks a
full certificate, so verification time and certificate size matter. The
current theorem that additionally binds the exact serialized JSON parser/hash
calculation uses `native_decide`; policies that forbid it should use the direct
typed-data theorem and understand that narrower binding. Compact
enclave-backed certificates are intended to reduce local checking further, but
the current repository has not admitted a production receipt. The implemented
Azure import path verifies a source-pinned receipt key outside Lean, generates
a reviewed closed registry entry, and lets Lean kernel-reduce exact membership
and structural binding. Production still requires an independently reviewed
appraisal policy, measured-runner enforcement, a Managed HSM key and
key-attestation review, a real Azure run, and registry review.

This design follows a broader proof-certificate pattern already used for SAT,
pseudo-Boolean, and computer-algebra results: let a specialized external engine
do the expensive discovery, then use a much smaller verified checker to turn
the witness into a composable theorem. The
[Lean integration guide](docs/LEAN_INTEGRATION.md#relationship-to-existing-lean-approaches)
compares the approaches and links to the relevant Lean documentation and
research.

## Trust questions

SparkInterval keeps three questions separate:

1. Does the interval algorithm enclose the exact real result?
2. Did a particular program produce the recorded bytes?
3. What evidence identifies the measured machine and software behind that run?

See [Project vision](docs/VISION.md) for the proposed secure architecture and
[Contributing](docs/CONTRIBUTING.md) for concrete ways to help.

## Current support

SparkInterval is a research prototype. Lean-consumable full certificates,
CPU/Lean certificate checking, formal interval arithmetic, modeled generated
GPU code, local DGX Spark/H100 validation, Azure CPU/H100 deployment adapters,
attestation collection/appraisal plumbing, signed receipts, and source-pinned
Lean import are implemented. No production Azure receipt is admitted and no
public shared certificate service exists. The table below is the precise
status, including the boundary of every claim.

| Route | Current result | Important boundary |
| --- | --- | --- |
| Generated Lean full certificate | A deterministic generated module materializes the formula and complete witness; Lean independently checks every row and exports reusable row or finite-sum bound theorems | Importable today; a clean build checks the full witness, and the direct kernel theorem does not by itself bind the typed data to the original JSON bytes |
| Generated polynomial model | Lean proves whole-module typed-AST execution and exact-real containment; a pinned PTX 9.0 slice adds opcode citations and finite/non-NaN arithmetic refinement | No full emitted-instruction-text, `ptxas`, SASS, driver, or hardware refinement |
| DGX Spark (`aarch64`, `sm_121`) | Tiny bounded CUDA/CPU known-answer tests, static artifact audits, performance sampling, and canonical local diagnostic bundles | Source-scale arithmetic and independent arithmetic replay are cloud-only. GB10 has no supported hardware attestation; evidence is `local_unattested` |
| DGX operator signature | A pinned Ed25519 key endorses the exact local bundle | Proves the pinned key signed; operator attribution is out of band, and neither truth nor GPU execution follows |
| Accepted Lean run certificate | One explicit axiom supplies both the exact historical return and, after a closed registered-invocation check, that invocation's fixed formal `Runs` relation | The Azure importer is a reviewed source-generation process, not a signature oracle inside Lean; the per-run registry bridge is not a universal determinism or backend-refinement theorem |
| Closed algorithm-registry example | `cubicSumDivThree20000V1` fixes an executable integer cube accumulator followed by one division by three; Lean proves its exact operational result `13334666700000000`, agreement with the rational sum, and u64 safety of every cube and accumulator step, all without `native_decide` | These are axiom-free model and bounded-arithmetic proofs, not a GPU-opcode or physical-execution proof; the trusted-compute receipt registry is empty, so no accepted physical run instantiates it |
| Helfgott (2.18) finite Sqrt218 path | The full producer and independent replay are guarded to the measured Azure worker; ordinary local runs are limited to at most 64 work items. In addition to the legacy canonical V1 route, the fixed-width V2 path has a strict byte decoder, exact 120-byte result format, and ordinary Lean source refinements for all 50 C functions reachable from the pure entry: parser, roster, power layout, log ladder, complete event scan, endpoint root/reciprocal/anchor, SHA-256, wrapper control flow, and result encoding. The exact ELF decoder now resolves the unique selected static symbol and proves it is the executable `e_entry`; a separate symbolic x86 ABI model proves exact segment loading/zero-fill, guarded disjoint memory, SysV entry registers, immutable input, and strict return observation, and their load composition is an ordinary data-independent theorem. A compact static-binary certificate checks exact instruction bytes, contiguous blocks, unique addresses, selected entry, and closed direct control flow, then isolates the still-open universal x86 trace-to-block and block-summary proofs. The direct no-replay capstone maps a successful pure-source trace to the exact Mathlib source claim. A compact V2 execution-closure identity binds the measured launcher separately from the architecture-modeled pure-entry ELF and pins the launcher contract plus compiler/model/ABI/entry identities; legacy V1 metadata is ineligible for physical-launch admission. The preferred receipt theorem retains the small exact ELF and 120-byte result while leaving the production input and machine trace existentially opaque. Separate cloud-only VST/CompCert and launcher build lanes are fail-closed and non-authorizing; the latter pins an unreviewed loader/trampoline source prototype without running it | No production corpus, measured image, appraiser, key, run, or receipt is admitted. No cloud-built launcher binary has been produced or reviewed, and its source has no Lean initializer/observer or x86 refinement. The VST specification/proof pins are still absent, so the proof lane stops before invoking tools and authorizes no theorem. Reachable x86-64 semantics, CompCert-to-object and assembler/linker validation, physical CPU conformance, and receipt-to-architecture admission remain open; no local build replays the production certificate or instruction trace |
| Azure SEV-SNP CPU trusted compute | Exact CPU VM profiles, private-network deployment, a challenge-first measured runner, ordered no-reset PCR binding, an independently replayed static closed-algorithm example, external Azure/MAA/vTPM appraisal ABI, compact receipt signing, and source-pinned Lean import | No production measured image, appraiser/root policy, Managed HSM key attestation, real Azure run, or admitted receipt is included |
| H100 (`x86_64`, `sm_90`) native and Azure NCC trusted compute | Strict native runners, exact CPU conformance and PTX/SASS audits, one closed Lean-generated `sm_90` pilot with an independent trace verifier, a stateful one-VM Azure operator workflow, and a content-bound deployment for all thirteen source atoms plus the distinct lowered `10^27` finite endpoint. Both historical and lowered finite-Goldbach routes have separate exact measured-job/projection/export factories for all 8,192 H100 groups | The local pilot packages but cannot execute on the DGX Spark's GB10 or claim Azure attestation. Production still requires an exact `x86_64` measured image, Azure/NVIDIA composite appraiser and policy, HSM key, authenticated transport, H100 calibration, and real receipts. Attestation authenticates an approved measured run; it does not prove arbitrary user code or mathematics |
| High-bound zeta-zero foundation | Lean canonically checks a signed full endpoint payload, bridges analytic multiplicity to distinct counts, and conditionally composes a Hardy-Z model plus multiplicity bound into the finite-height theorem. The PT21 vertical slice now pins the exact height, count, FLINT campaign identity and CPU/SEV-SNP deployment through a closed registered invocation and signed wrapper | Endpoint/Hardy-Z/count realization, a source-evidence materializer, the multi-year full run and an attested successful receipt remain absent; the semantic binding stays disabled and no height has been certified |
| Platt zeta head through 20,000 | A completed local FLINT 3.6.0/96-bit replay isolates all 22,491 included zeros plus the sentinel. The exact included Q128 table is generated into Lean, which proves that checked Hardy-Z/count evidence for that named table yields the multiplicity-preserving source claim. A closed CPU/SEV-SNP invocation pins both the 22,492-row artifact digest and the distinct 22,491-row source-table commitment | No `CheckedQ128HeadEvidence`, admitted receipt, or downstream exact-table bridge is shipped. FLINT/Hardy-Z/count realization remains external; the registered success relation names the exact table rather than trusting digest collision resistance. The exact invocation/theorem/result-path shape is staged, but the semantic binding stays disabled |
| Platt Dirichlet Theorem 7.1 | Lean states the exact universal even/odd conductor-height proposition and proves it from a two-field `PlattTheorem71SourceEvidence`. A closed CPU/SEV-SNP finalizer pins `q=1..400000`, the two source height formulas, the exact 29,565,923,837-character `q=2..400000` roster count, and the separate stronger `q=1` zeta campaign; its signed wrapper exposes the source theorem only when result `true` carries that exact evidence | No full physical campaign or successful receipt exists. Roster realization, completed-L/Hardy identity, complete brackets, conjugation, and total-zero counts remain open. The exact invocation/theorem/result-path shape is staged, but the semantic binding stays disabled |
| Ternary Goldbach external-computation work | Catalogs all thirteen live source atoms plus the distinct lowered finite endpoint as eleven physical campaigns: source-scale two-pass psi and shared Hurst workers; a 12,930-leaf MPFR/GMP Proposition 12.2.4 campaign; head/high zeta campaigns; exact R2Star and CDEM replays; historical and lowered binary-Goldbach/ladder campaigns; and the exact 29,565,923,837-character Dirichlet scheduler. The Hurst V2 bridge now trusts only primitive local row/guard replay evidence and derives global prefixes in ordinary Lean before proving all four Hurst-family atoms (five real inequalities), including the `6/π²` enclosure, with only Lean's foundational trio. The CH25 psi bridge now proves that its one-log-interval-per-prime-power fold is Mathlib's `p.log` expansion, derives the exact Q64 enclosure of `Chebyshev.psi`, proves the endpoint/real-slab reduction, registers the source-shaped CPU result, and pins its receipt-import identity. Dirichlet has certified Hurwitz inputs, directed H100 Taylor and small-q Gaussian/DFT arithmetic, a persistent residue-composition/all-character/completed-L graph, independent MPFR/Arb checks, scalable root-number artifacts, a q-persistent factored small-q service with reduced integrity streaming, and a rigorous slow FLINT fallback. Its ordinary Lean bridge checks raw binary64 Gaussian/postprocess traces, bounded radix-2 traces, the generic direct-DFT identity, source/full-length alignment, raw scaling/tail/untilt witnesses, producer-compatible strict signs, ordered all-modulus raw-word attachment, exact rational zero-bracket construction, explicit primitive-roster/character-row/source-evaluator contracts, a same-cell character/evaluator capstone, and opaque-roster-to-GRH assembly | Capability is not completion. No production Azure campaign has run and no source atom is discharged. Hurst and psi still need physical full-range receipts, exact retained-row-to-evidence bindings, and downstream receipt application; `claude_math` now has the conditional Hurst adapters but intentionally retains its live atoms until receipts exist. High zeta and historical Goldbach remain multi-year at current measured/projected rates; the lowered Goldbach campaign is source-closed but uncalibrated and unrun. Dirichlet still needs a canonical byte/sidecar and physical-execution link to the Lean certificate, concrete proofs of the now-explicit analytic-input and primitive-character contracts, a source-wide interval-width argument, efficient persistent lattice/recovery production, exception refinement and source-wide bracket selection, the completed-L evaluator/Hardy-model theorem, conjugation coverage, the separate `q=1` zeta case, and corrected Turing normalization/phase closure. Several paths trust FLINT/MPFR/CUDA/runtime semantics, and most source campaigns still lack their final Lean realization theorem |
| GRH POC (Dirichlet L-functions, arXiv:1305.3087) | A rigorous GPU interval evaluator isolates critical-line zeros of every primitive character of a modulus; runs emit signed-eligible canonical bundles whose job inputs re-encode deterministically and whose certificate endpoints byte-bind to recorded outputs; Lean kernel-checks the bracket families and derives conditional finite-strip GRH theorems, with moduli 3 and 4 fully classified | The evaluator-realization and Turing zero-count premises remain explicit hypotheses; the direct evaluator is valid only for moderate ordinates, and no Platt-scale height or modulus range is certified |
| Certified in-Lean numerics (`SparkInterval/Certified`) | Executable, fully proved rational-interval `sqrt`, `exp`, `log`, `sin`, `cos`, `arctan`, complex rectangles, and unconditional certified evaluators for the GRH Dirichlet main sums and Euler-Maclaurin correction terms | The Stirling Gamma-factor composition and the two named analytic remainder premises (Euler-Maclaurin tail, Stirling) are stated but not yet proved; kernel reduction does not evaluate `Nat.sqrt`-based enclosures, so evaluator-bound checks need compiled evaluation |

The finite Helfgott--Platt Goldbach path now also has an exact conditional
Lean vertical slice: ordinary Lean proves the binary-plus-prime-ladder
reduction, and a closed Azure CPU finalizer pins both the H100 binary and CPU
ladder campaign/source-artifact identities. This is not a completion claim.
Neither branch has run at source scale, and no `CheckedSourceEvidence` or
successful receipt is shipped. The measured terminal now commits to all 8,512
signed producer identities and independently matches their result hashes to
the 65,536 binary and 492,700 ordinary/native ladder receipts before branch
replay. The historical H100 array now has a separate campaign-specific
measured-job/projection/export materializer for every group. Production
build/image/policy/key pins are still unconfigured, no source-scale run has
occurred, and the Azure semantic binding remains disabled and null.

The conditional `10^27` crossover has a second, explicitly versioned finite
campaign, `ternary-goldbach-finite-below-10pow27-v1`. The v3 cluster manifest
keeps it separate from the stronger historical computation and schedules its
65,536 lowered binary leaves, 7,106 n=45 ladder ranges, reducers, replay, and
measured CPU finalizer. Its registered invocation and exact terminal-result
path are staged in the Azure semantic inventory with `enabled:false`; CPU
phase materializers cover all seven CPU groups and verify signed retained
handoffs. Closed per-group H100 operational/export materializers now cover all
8,192 groups, and sizing has a separate exact campaign row. Source-realization
review, H100 calibration, production policies/keys, and real receipts remain
gates; the semantic binding stays disabled.

## Choose a workflow

- For a mathematical result independent of GPU provenance, use the
  [CPU and Lean certificate workflow](docs/USING.md#full-lean-result-certificate).
- To run locally on DGX Spark and optionally sign the record, use the
  [DGX workflow](docs/USING.md#dgx-spark-local-bundle-and-operator-signature).
- To compute a rigorous tutorial enclosure of real `zeta(s)` on DGX Spark or
  H100, use the [zeta workflow](docs/USING.md#real-integer-zeta-poc).
- To isolate Dirichlet L-function zeros on the GPU and check the resulting
  certificates in Lean, use the
  [GRH POC workflow](docs/USING.md#grh-finite-verification-poc); its
  algorithm, trust boundaries, and benchmarks are documented in the
  [GRH POC guide](docs/algorithms/GRH_POC.md) and
  [benchmarks](docs/algorithms/GRH_POC_BENCHMARKS.md).
- To review or extend the high-bound zero verifier, start with its
  [formal architecture and status](docs/algorithms/ZETA_ZERO_VERIFIER.md).
- To review the cloud-only finite computation behind Helfgott (2.18), including
  its explicit local-run guard and current compiler/ISA gap, use the
  [Sqrt218 Azure CPU guide](docs/algorithms/SQRT218_AZURE_CPU_CERTIFICATE.md),
  [verified-compiler path](docs/algorithms/SQRT218_VERIFIED_COMPILER_PATH.md),
  [x86-model feasibility audit](docs/algorithms/SQRT218_X86_MODEL_FEASIBILITY.md),
  [static binary-certificate boundary](docs/algorithms/SQRT218_STATIC_BINARY_CERTIFICATE.md),
  and
  [compact no-replay receipt boundary](docs/algorithms/COMPACT_ARCHITECTURE_RECEIPT_BOUNDARY.md).
- To audit the thirteen external atoms used by the ternary Goldbach theorem,
  or prepare their fail-closed one-job/one-H100 Slurm deployment, use the
  [unified campaign control plane](docs/algorithms/TERNARY_GOLDBACH_CAMPAIGNS.md)
  and [H100 cluster guide](docs/algorithms/H100_TG_CLUSTER.md); for exact
  commands, evidence levels, and feasibility estimates, read the
  [external-atoms guide](docs/algorithms/TERNARY_GOLDBACH_EXTERNAL_ATOMS.md).
  The production-data-free trust view is the
  [closed architecture registry](docs/algorithms/REGISTERED_ARCHITECTURE_INVOCATIONS.md),
  [compact closure matrix](docs/algorithms/TERNARY_GOLDBACH_COMPACT_RECEIPT_CLOSURE.md),
  [13-atom checker capstone](docs/algorithms/TERNARY_GOLDBACH_COMPACT_ATOM_CAPSTONE.md),
  [15-family native-dependency closure](docs/algorithms/TERNARY_GOLDBACH_NATIVE_FAMILY_CLOSURE.md),
  [1,371-member native-root crosswalk](docs/algorithms/TERNARY_GOLDBACH_NATIVE_MEMBER_CROSSWALK.md),
  [all-family aggregate architecture route](docs/algorithms/TERNARY_GOLDBACH_NATIVE_AGGREGATE_ARCHITECTURE.md),
  and the
  [full 1,387-root trust-boundary audit](docs/algorithms/TERNARY_GOLDBACH_FULL_TRUST_BOUNDARY.md).
  That full audit now fixes 11 proof-authorizing receipt slots—10 external
  campaigns and one all-native aggregate—but records 0 imported receipts and
  0 accepted receipts. The slots are typed handoff boundaries, not a claim
  that any theorem dependency has been discharged.
- The A.7 command recomputes every retained FLINT/Arb leaf; its exact
  source-shaped rational-box theorem and conditional CPU receipt bridge are
  implemented. Its closed one-job Azure CPU materializer pins the exact
  artifact, full source/runtime closure, and a second complete replay; the
  FLINT-to-Mathlib realization, x86-64 production materialization, attested
  run, and receipt admission remain explicit. The CDEM producer
  hashes and compiles reviewed source, runs a small independent preflight, and
  executes all five billion recurrence steps. A second command recompiles a
  separately reviewed implementation and independently replays all 1,000
  bounded-memory chunks. A standalone no-shell terminal now accepts the
  complete fixed-width CDEM artifact as its input and replays every row. An
  additive two-stage Azure materializer verifies the first job's signed
  receipt and retained archive, then makes those exact artifact bytes the
  second measured job's input under a fresh challenge. It is bounded-tested
  and deliberately emits no Lean theorem candidate: the C++/compiler/ELF-to-
  Lean refinement and a production verifier key/run remain explicit. Any
  eventual receipts retain the external-toolchain and physical-refinement
  boundaries explicitly.
- Proposition 12.2.4 now has a closed Azure CPU phase DAG: 12,930 logical
  GMP/MPFR leaves in four 96-worker measured jobs, signed retained-export
  handoffs, a second complete replay, and
  an independently repeated exact terminal merge bound to the registered
  `true` result. The production x86-64 source build, actual Azure run,
  MPFR/GMP-to-exact-real review, and receipt admission remain explicit.
- To smoke-test the host-side schedule and synthetic streaming-bracket
  scaffolding, run `python3 tools/benchmark_zeta_foundations.py --pretty`; this
  is not a zeta, Lean, GPU, or production-certificate benchmark.
- To build or validate the strict native runners on an H100, use the
  [H100 native workflow](docs/USING.md#h100-native-local-validation).
- To prepare H100 device artifacts without an H100, use the
  [H100 offline workflow](docs/USING.md#h100-offline-artifacts).
- To deploy confidential Azure SEV-SNP CPU VMs or one-H100 NCC VMs, collect
  statement-bound evidence, independently appraise it, sign a receipt, and
  prepare a reviewed Lean registry entry, use the
  [Azure confidential-compute workflow](docs/AZURE_CONFIDENTIAL_COMPUTE.md).
  Before supplying credentials or creating resources, run
  `tools/tg_azure_launch_preflight.py --pretty`; its
  [read-only launch report](docs/AZURE_TG_LAUNCH_PREFLIGHT.md) checks all ten
  source campaigns, 33 phase groups, registered backends, materializer CLIs,
  and site schemas while keeping redacted pins, missing calibration, and
  absent receipts visibly blocked.
  The stateful one-H100 production handoff is documented in the
  [Azure H100 operator runbook](docs/AZURE_H100_PRODUCTION_OPERATOR.md), and
  the exact challenge-first protocol is documented in the
  [measured-runner guide](docs/AZURE_MEASURED_RUNNER.md).
  The [DGX Spark measurements and Azure sizing note](docs/AZURE_PERFORMANCE_SIZING.md)
  records the current host-replay bottleneck and non-H100 planning data; the
  [Managed HSM guide](docs/AZURE_MANAGED_HSM_SIGNING.md) covers production
  receipt signing and key-attestation review.

## Collaborate

This project needs collaborators before it needs more claims. The immediate
priorities are to verify what is already here, make the repository useful and
approachable to outsiders, explain the idea clearly to potential users, and
build relationships with projects working on formal proof, rigorous numerics,
verifiable computation, and confidential computing.

Contributions are welcome even if you do not write Lean or CUDA. In particular:

- independently reproduce the proofs, certificate checks, GPU tests, and trust
  audits; challenge the threat model and report claims that are too strong;
- help turn the project into a dependable open-source repository through
  onboarding, examples, packaging, CI, issue triage, release engineering, and
  API design;
- help communicate and demonstrate the project: identify useful audiences,
  improve explanations, write tutorials, and develop credible example results;
- connect SparkInterval with theorem provers, verified numerics, proof
  certificate, reproducible-computation, and confidential-computing projects;
- add well-scoped finite computations once their semantics, bounds,
  certificates, and intended theorem are clear; and
- help extend the proved arithmetic/compiler surface, build the secure evidence
  path, and design the content-addressed certificate library.

Start with the [contributor guide](docs/CONTRIBUTING.md), then use the
[correctness matrix](docs/CORRECTNESS_CLAIMS.md) to understand what a change is
allowed to claim. The [collaboration roadmap](docs/ROADMAP.md) separates the
work needed for a trustworthy public foundation from later computation and
ecosystem expansion. The project is MIT licensed.

## CPU and Lean quick start

Run these commands from the repository root.

This quick start exercises proofs and tiny examples only. Production-scale
ternary-Goldbach arithmetic is intentionally a measured Azure workload, not a
local build step or CI test. After such a run is independently appraised, the
ordinary Lean handoff checks its compact source-pinned receipt and fixed
registered semantics; it does not regenerate or replay the production
certificate.

Small core proofs:

```bash
./tools/safe_lake_build.py
./tools/safe_lake_build.py SparkInterval.IntervalOpsSound
./tools/safe_lean.sh examples/lean/IntervalArithmetic.lean
./tools/safe_lean.sh examples/lean/ZetaIdentity.lean
```

The no-argument build is the explicit compact, data-independent proof root.
It includes the closed 13-atom/10-campaign catalog, every ordinary
checker-to-source-claim adapter, the all-atom capstone, and the universal
Sqrt218 C/ELF/ABI/physical-identity composition. It also includes the closed
source-program audit for the ten external campaigns plus the Ramaré fallback:
all eleven retain explicit generator/parser/final-check/soundness gaps and
zero are marked concrete. The separate downstream all-native aggregate does
have an exact Lean source-level `FixedDecisionProgram` certificate, but no
static-CPU compiler/loader/ISA refinement; it is not part of that zero-of-
eleven count. The compact root excludes the legacy
`RegisteredAlgorithm`, `PlattHeadQ128`, and `CDEMAbelProduction`
materializations. The static closure audit reports the current module, byte,
and line counts:

```bash
python3 tools/audit_local_lean_boundary.py
```

The broad production-materialized Lean library is Azure-qualification-only;
it is not run by this quick start.

Generate and check the complete two-row certificate in a fresh destination:

```bash
mkdir -p build/examples
CERT_DIR="$(mktemp -d build/examples/lean-result-certificate.XXXXXX)"
./tools/safe_lake_build.py SparkInterval.Certificate \
  --target sparkinterval-check-certificate
python3 tools/generate_lean_result_certificate.py \
  --certificate examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001 \
  --decision-mode kernel \
  --output "$CERT_DIR/GeneratedFullCertificate.lean" \
  > "$CERT_DIR/receipt.json"
./tools/safe_lean.sh "$CERT_DIR/GeneratedFullCertificate.lean"
./tools/with_memory_limit.sh \
  .lake/build/bin/sparkinterval-check-certificate \
  examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001
```

In `kernel` mode, the direct typed-data theorem uses kernel reduction without
the `native_decide` proof-reflection axiom. The theorem that binds the exact
serialized JSON still uses `native_decide` for its concrete parser equality.
See the [certificate example](examples/lean-result-certificate/README.md) for
the theorem names and trust details.

## DGX Spark quick start

Check the [DGX Spark prerequisites](docs/DGX_SPARK_SETUP.md), then run:

```bash
./tools/build_dgx_spark.sh
python3 tools/verify_run_bundle.py \
  build/dgx-probe-bundle/run-bundle.json \
  --artifact-root build/dgx-probe-bundle
```

This builds the library and DGX backend, runs bounded checks, captures
the environment, extracts GPU artifacts, and creates a diagnostic probe
bundle. Verification intentionally reports `hardware_evidence: false`.

For arithmetic execution, operator signing, replay protection, and fresh
challenger nonces, continue with the
[DGX user workflow](docs/USING.md#dgx-spark-local-bundle-and-operator-signature).
Lean builds are serialized and memory-capped; read
[Memory-safe builds](docs/MEMORY_SAFE_BUILDS.md) before changing those limits.

## GRH POC quick start

With the DGX build available, isolate the critical-line zeros of the
primitive character mod 4 to ordinate 200, verify the signed-eligible
bundle and certificate, and generate the Lean instantiation:

```bash
cmake -S . -B build/grh-dev -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/grh-dev --target sparkinterval-grh-lambda
python3 tools/run_grh_poc.py run --q 4 --t-hi 200 \
  --work-dir build/grh-poc/q4-t200
python3 tools/run_grh_poc.py verify build/grh-poc/q4-t200
python3 tools/generate_grh_lean.py \
  --certificate build/grh-poc/q4-t200/grh-certificate.json \
  --output build/grh-poc/GeneratedChiFourCert.lean
./tools/safe_lean.sh build/grh-poc/GeneratedChiFourCert.lean
```

The final command kernel-checks every zero bracket and produces a
conditional finite-strip GRH theorem for modulus 4 depending only on
Lean's standard axioms; the [GRH POC guide](docs/algorithms/GRH_POC.md)
states the remaining analytic premises exactly.

For the source-shaped Platt large-\(q\) route, the
[row-resident t-major component](docs/algorithms/DIRICHLET_TMAJOR_CUDA_BLOCK.md)
now supplies a typed, independently replayed direct-MPFR input and one-upload
CUDA composition mode. Its primitive-only V2 source input is
286,556,459,000 bytes, but it
ends at `TGDAFFI1`; source cache population, persistent multi-\(q\) FFT and
completed-\(L\) integration, authenticated zero state, Turing closure,
attestation, and the source run remain open.

## H100 quick start

On a host with exactly one visible NVIDIA H100 at compute capability 9.0,
build, audit, and run the strict native validation suite:

```bash
H100_BUILD_JOBS=1 ./tools/run_h100_native_validation.sh
```

The script builds these native artifacts:

- `build/h100-native/sparkinterval-h100-probe-runner`;
- `build/h100-native/sparkinterval-h100-interval-batch`;
- `build/h100-native/sparkinterval-h100-expression-batch`;
- `build/h100-native/sparkinterval-h100-grh-lambda`;
- `build/h100-native/sparkinterval-h100-tg-r2star-chunk`;
- `build/h100-native/sparkinterval-h100-tg-mobius-segment`; and
- `build/h100-native/h100/h100_rounding_probe.sm_90.cubin`.

After that succeeds, run the H100-bound real-zeta tutorial in a fresh
directory:

```bash
mkdir -p build/examples
H100_ZETA_PARENT="$(mktemp -d build/examples/h100-zeta2.XXXXXX)"
H100_ZETA_DIR="${H100_ZETA_PARENT}/run"
python3 tools/run_zeta_poc.py run \
  --target-profile h100_sm90 \
  --work-dir "${H100_ZETA_DIR}" \
  --s 2 \
  --terms 4096
python3 tools/run_zeta_poc.py verify "${H100_ZETA_DIR}"
```

Both surfaces are intentionally local and unattested. The zeta verification
receipt reports `evidence_class: local_unattested` and
`hardware_evidence: false`; neither command obtains or validates NVIDIA
confidential-computing evidence. See the [H100 guide](docs/H100.md) for the
offline CLI checks and the separate generated-`sm_90` polynomial path.

For a confidential Azure run, use the separate
[`Standard_NCC40ads_H100_v5` workflow](docs/AZURE_CONFIDENTIAL_COMPUTE.md).
It deploys one H100 per VM and requires a fresh off-VM challenge, composite
Azure SEV-SNP/vTPM and NVIDIA appraisal, measured-runner policy, an HSM-signed
receipt, and source-registry review. The tools exist, but this repository has
not performed or admitted such a production run.

## Explicit nonclaims

- The real-integer zeta POC encloses positive real values for supported integer
  arguments. It does not locate or count critical-strip zeros and does not
  verify the Riemann hypothesis to any height.
- The separate high-bound foundation parses and checks a canonical monolithic
  endpoint payload, proves resumable endpoint/chunk composition, and can
  reflect positive-only rows for a proved even evaluator. Its
  Hardy-Z/Riemann-Siegel endpoint realization and analytic multiplicity-count
  premise do not yet have production instances. It therefore does not certify
  any positive height.
- The preferred compact attested-summary theorem uses a closed registered
  invocation, so the sole axiom supplies the per-run physical-to-formal
  `Runs` bridge and no second `ExecutionRefines` premise is needed. It still
  requires an ordinary Lean soundness theorem for that registered checker.
  The older generic FormalPTX compact API remains available and still requires
  its explicit refinement premise.
- The division-capable CUDA runner used by that POC is not covered by the
  generated polynomial-machine theorem.
- The GRH POC's generated theorems are conditional: the evaluator model,
  the endpoint-enclosure realization, and the total zero-count (Turing)
  bound are explicit hypotheses. The certified in-Lean evaluators
  discharge the heavy endpoint arithmetic unconditionally, but the two
  named analytic remainder premises and the Gamma-factor composition
  remain open, so no GRH height is certified unconditionally today.
- GRH GPU enclosures rely on documented CUDA Math API maximum-ulp error
  bounds for `log`, `exp`, `sin`, `cos`, and `atan`, outward-widened and
  cross-checked against independent high-precision recomputation; that
  vendor bound is a stated trust assumption of the numeric layer, not a
  Lean theorem.
- PTX and SASS audits are conservative artifact checks, not formal proofs that
  `ptxas`, the CUDA driver, or physical hardware implements Lean's machine.
- An operator signature is not hardware attestation.
- The sole `accepted_run_certificate_sound` axiom accepts only an exact
  source-admitted `checkTrustedCompute` receipt. It establishes that receipt's
  historical outcome and its fixed formal semantics for every matching
  constructor of the closed invocation registry. `accepted_registered_run_sound`
  is a proved projection, not another axiom. The legacy DGX-signature and H100
  structural checks remain diagnostics and are unconditionally rejected by
  `RunCertificate.check`; they cannot establish `AlgorithmReturned` or `Runs`.
  This per-run bridge does not say that every future run is deterministic or
  prove a general PTX/cubin/backend refinement theorem.
- Before a closed invocation can match, Lean recomputes the SHA-256 bindings
  for its canonical algorithm, input, parameter, and domain bytes. An edited
  preimage with a stale reviewed digest therefore disables certificate
  selection instead of silently reusing an older admitted receipt.
- The same selector checks an invocation-specific canonical result language.
  The tutorial and pilot have one exact result, CDEM has its exact paired
  decimal result or `false`, and the source campaigns admit only `true` or
  `false`. Malformed signed result bytes cannot select a `Runs` relation.
- The source audit rejects `native_decide` in production Lean modules. Small
  executable facts use kernel `decide`; large computations must cross an
  explicit certificate or the disclosed trusted-run boundary. Test-only KATs
  remain outside theorem dependencies.
- The closed algorithm/invocation registry contains the CPU tutorial, the
  one-row formal-PTX H100 pilot, and source-shaped Ternary-Goldbach entries,
  including exact conditional PT21 finite-RH and Platt Dirichlet Theorem 7.1
  slices. Registration alone is not verification: both still lack materialized
  source evidence, source-scale runs, and attested successful receipts.
- The cubic tutorial's `cubicNumeratorLoop`/`cubicSumDivThreeMachine` proofs establish the
  tutorial algorithm and u64 bounds in Lean. They do not establish that a GPU
  executable implements those steps; that particular-run connection remains
  exactly the certificate axiom's responsibility.
- The H100 pilot separately proves that its registered PTX text is exactly the
  formal emitter's output for the closed constant `[1,1]` batch and that both
  returned binary64 endpoints decode to rational one. It remains a deliberately
  small deployment-path test, not a production finite computation.
- Literal algorithm ID/hash checks do not prove that a cubin was compiled from
  the formal PTX module.
- Successful H100 native, generated-polynomial, or real-zeta validation is
  local execution/conformance evidence, not confidential-computing
  attestation. The Azure path can collect, independently appraise, sign, and
  source-import genuine evidence, but its tracked receipt registry is empty.
- An Azure or NVIDIA attestation token does not prove arbitrary user-space code
  caused the claimed output or that the finite algorithm is mathematically
  sound. Those claims require a reviewed measured runner, a closed invocation,
  and its ordinary Lean soundness theorem; the physical-to-formal per-run step
  remains exactly the sole execution axiom.

## Documentation

- [Using computation certificates from Lean](docs/LEAN_INTEGRATION.md)
- [Project vision and target architecture](docs/VISION.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Collaboration roadmap](docs/ROADMAP.md)
- [User workflows](docs/USING.md)
- [Documentation index](docs/README.md)
- [Verification guide](docs/VERIFYING.md)
- [Examples](examples/README.md)
- [DGX Spark setup](docs/DGX_SPARK_SETUP.md)
- [H100 native, offline, and production boundary](docs/H100.md)
- [Azure confidential CPU/H100 execution](docs/AZURE_CONFIDENTIAL_COMPUTE.md)
- [Ternary Goldbach Azure launch preflight](docs/AZURE_TG_LAUNCH_PREFLIGHT.md)
- [DGX Spark benchmarks and Azure sizing](docs/AZURE_PERFORMANCE_SIZING.md)
- [Azure Managed HSM receipt signing](docs/AZURE_MANAGED_HSM_SIGNING.md)
- [Pinned numeric-corpus references and cloud-receipt binding](docs/NUMERIC_CORPUS_REFERENCES.md)
- [Run-bundle and certificate formats](docs/FORMAT.md)
- [Memory-safe builds](docs/MEMORY_SAFE_BUILDS.md)
- [Proof blueprint and NVIDIA-spec traceability](docs/PROOF_BLUEPRINT.md)
- [Trust model](docs/TRUST_MODEL.md)
- [Correctness claims](docs/CORRECTNESS_CLAIMS.md)
- [Reproducibility details](docs/REPRODUCIBILITY.md)
- [Real-zeta POC algorithm](docs/algorithms/REAL_ZETA_POC.md)
- [High-bound zeta-zero verifier status](docs/algorithms/ZETA_ZERO_VERIFIER.md)
- [Ternary Goldbach external atoms](docs/algorithms/TERNARY_GOLDBACH_EXTERNAL_ATOMS.md)
- [Ternary Goldbach external-program readiness](docs/algorithms/TERNARY_GOLDBACH_EXTERNAL_PROGRAM_READINESS.md)
- [Ternary Goldbach compact architecture registry](docs/algorithms/REGISTERED_ARCHITECTURE_INVOCATIONS.md)
- [Ternary Goldbach compact receipt closure matrix](docs/algorithms/TERNARY_GOLDBACH_COMPACT_RECEIPT_CLOSURE.md)
- [Ternary Goldbach 13-atom compact checker capstone](docs/algorithms/TERNARY_GOLDBACH_COMPACT_ATOM_CAPSTONE.md)
- [Ternary Goldbach native-generated family closure](docs/algorithms/TERNARY_GOLDBACH_NATIVE_FAMILY_CLOSURE.md)
- [Ternary Goldbach 1,371-member native-root crosswalk](docs/algorithms/TERNARY_GOLDBACH_NATIVE_MEMBER_CROSSWALK.md)
- [Ternary Goldbach all-family aggregate architecture route](docs/algorithms/TERNARY_GOLDBACH_NATIVE_AGGREGATE_ARCHITECTURE.md)
- [Fixed decidable-claim checker safety boundary](docs/algorithms/FIXED_DECISION_CHECKER.md)
- [GRH POC: GPU evaluator, certificates, certified numerics, and Lean instantiation](docs/algorithms/GRH_POC.md)
- [GRH POC benchmarks and full-run extrapolation](docs/algorithms/GRH_POC_BENCHMARKS.md)
