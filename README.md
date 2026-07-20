# SparkInterval

> **Work in progress:** SparkInterval is an early research prototype seeking
> collaborators. Full result certificates can already be generated, checked,
> imported, and used as Lean theorems. Production enclave-backed certificate
> issuance and a shared certificate registry are still future work. Do not
> treat the current local-run tooling as a production attestation service.

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

For provenance-sensitive computations, the intended production path uses
measured code inside a secure execution environment (a CPU TEE together with
GPU confidential-computing support where available). An external verifier
checks the resulting hardware evidence and binds the exact program, inputs,
bounds, output, and completion status into a computation certificate.
Certificates can then be stored by digest in a shared library and reused by
later Lean proofs.

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
their production evidence importer is not implemented yet.

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
GPU code, and local DGX Spark/H100 validation are implemented. Production
enclave-backed acceptance and a public shared certificate registry are not.
The table below is the precise status, including the boundary of every claim.

| Route | Current result | Important boundary |
| --- | --- | --- |
| Generated Lean full certificate | A deterministic generated module materializes the formula and complete witness; Lean independently checks every row and exports reusable row or finite-sum bound theorems | Importable today; a clean build checks the full witness, and the direct kernel theorem does not by itself bind the typed data to the original JSON bytes |
| Generated polynomial model | Lean proves whole-module typed-AST execution and exact-real containment; a pinned PTX 9.0 slice adds opcode citations and finite/non-NaN arithmetic refinement | No full emitted-instruction-text, `ptxas`, SASS, driver, or hardware refinement |
| DGX Spark (`aarch64`, `sm_121`) | Native CUDA runs, exact CPU replay, artifact audits, and canonical local bundles | GB10 has no supported hardware attestation; evidence is `local_unattested` |
| DGX operator signature | A pinned Ed25519 key endorses the exact local bundle | Proves the pinned key signed; operator attribution is out of band, and neither truth nor GPU execution follows |
| Accepted Lean run certificate | One explicit axiom supplies both the exact historical return and, after a closed registered-invocation check, that invocation's fixed formal `Runs` relation | Requires a trusted private-evidence importer; the per-run registry bridge is not a universal determinism or backend-refinement theorem |
| Closed registry example | `cubicSumDivThree20000V1` fixes an executable integer cube accumulator followed by one division by three; Lean proves its exact operational result `13334666700000000`, agreement with the rational sum, and u64 safety of every cube and accumulator step, all without `native_decide` | These are axiom-free model and bounded-arithmetic proofs, not a GPU-opcode or physical-execution proof; no signed bundle can enter Lean because the private-evidence importer is absent |
| H100 (`x86_64`, `sm_90`) native | Strict probe, primitive, postfix-expression, Dirichlet-GRH, R2Star, and Möbius runners; exact CPU conformance and PTX/SASS audits; plus a content-bound Slurm deployment for all thirteen ternary-Goldbach campaigns | Five full-source campaigns use native H100 arithmetic. Eight execute as CPU/FLINT sidecars; the full-source Dirichlet route is one of those sidecars, while its H100 evaluator remains only a bounded POC. Current runs are local evidence; no NVIDIA confidential-computing evidence is accepted |
| High-bound zeta-zero foundation | Lean canonically checks a signed full endpoint payload, bridges analytic multiplicity to distinct counts, and conditionally composes a Hardy-Z model plus multiplicity bound into the finite-height theorem | Endpoint realization and the analytic Turing/argument-principle bound remain uninstantiated; no height has been certified |
| Ternary Goldbach external-computation work | Catalogs all thirteen live source atoms and gives each an exact full-source entry point: A.7 and CDEM full replays; psi and Proposition 12.2.4 streams; head/high zeta campaigns; exact CUDA R2Star and Möbius campaigns; a literal binary-Goldbach/prime-ladder reconstruction; and a 29,565,923,837-character Dirichlet scheduler with rigorous Arb argument-principle fallback and explicit `q=1` zeta composition | Capability is not completion. High zeta, Goldbach, Dirichlet, psi, Proposition 12.2.4, and the linear `10^16` scans are prohibitively or astronomically unscaled. Several paths share producer/checker code or trust FLINT/CUDA/runtime semantics. Every source campaign still lacks its Lean realization theorem, and no source atom is discharged |
| GRH POC (Dirichlet L-functions, arXiv:1305.3087) | A rigorous GPU interval evaluator isolates critical-line zeros of every primitive character of a modulus; runs emit signed-eligible canonical bundles whose job inputs re-encode deterministically and whose certificate endpoints byte-bind to recorded outputs; Lean kernel-checks the bracket families and derives conditional finite-strip GRH theorems, with moduli 3 and 4 fully classified | The evaluator-realization and Turing zero-count premises remain explicit hypotheses; the direct evaluator is valid only for moderate ordinates, and no Platt-scale height or modulus range is certified |
| Certified in-Lean numerics (`SparkInterval/Certified`) | Executable, fully proved rational-interval `sqrt`, `exp`, `log`, `sin`, `cos`, `arctan`, complex rectangles, and unconditional certified evaluators for the GRH Dirichlet main sums and Euler-Maclaurin correction terms | The Stirling Gamma-factor composition and the two named analytic remainder premises (Euler-Maclaurin tail, Stirling) are stated but not yet proved; kernel reduction does not evaluate `Nat.sqrt`-based enclosures, so evaluator-bound checks need compiled evaluation |

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
- To audit the thirteen external atoms used by the ternary Goldbach theorem,
  or prepare their fail-closed one-job/one-H100 Slurm deployment, use the
  [unified campaign control plane](docs/algorithms/TERNARY_GOLDBACH_CAMPAIGNS.md)
  and [H100 cluster guide](docs/algorithms/H100_TG_CLUSTER.md); for exact
  commands, evidence levels, and feasibility estimates, read the
  [external-atoms guide](docs/algorithms/TERNARY_GOLDBACH_EXTERNAL_ATOMS.md).
- The A.7 command recomputes every retained FLINT/Arb leaf. The CDEM producer
  hashes and compiles reviewed source, runs a small independent preflight, and
  executes all five billion recurrence steps. A second command recompiles a
  separately reviewed implementation and independently replays all 1,000
  bounded-memory chunks. Their receipts retain the external-toolchain and
  missing-Lean-realization boundaries explicitly.
- To smoke-test the host-side schedule and synthetic streaming-bracket
  scaffolding, run `python3 tools/benchmark_zeta_foundations.py --pretty`; this
  is not a zeta, Lean, GPU, or production-certificate benchmark.
- To build or validate the strict native runners on an H100, use the
  [H100 native workflow](docs/USING.md#h100-native-local-validation).
- To prepare H100 device artifacts without an H100, use the
  [H100 offline workflow](docs/USING.md#h100-offline-artifacts).

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

Small core proofs:

```bash
./tools/safe_lake_build.py SparkInterval.IntervalOpsSound
./tools/safe_lean.sh examples/lean/IntervalArithmetic.lean
./tools/safe_lean.sh examples/lean/ZetaIdentity.lean
```

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
- The sole `accepted_run_certificate_sound` axiom establishes one accepted
  certificate's historical outcome and its fixed formal semantics for every
  matching constructor of the closed invocation registry.
  `accepted_registered_run_sound` and the DGX/H100 names are proved projections,
  not additional axioms. This per-run bridge does not say that every future run
  is deterministic or prove a general PTX/cubin/backend refinement theorem.
- The closed registry currently contains only
  `RegisteredAlgorithm.cubicSumDivThreeV1` and
  `RegisteredInvocation.cubicSumDivThree20000V1`; no zeta checker is registered.
- Its `cubicNumeratorLoop`/`cubicSumDivThreeMachine` proofs establish the
  tutorial algorithm and u64 bounds in Lean. They do not establish that a GPU
  executable implements those steps; that particular-run connection remains
  exactly the certificate axiom's responsibility.
- Literal algorithm ID/hash checks do not prove that a cubin was compiled from
  the formal PTX module.
- Successful H100 native, generated-polynomial, or real-zeta validation is
  local execution/conformance evidence, not confidential-computing
  attestation. Production H100 acceptance remains fail-closed until a genuine
  measured workload and trusted NVIDIA evidence verifier exist.

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
- [Run-bundle and certificate formats](docs/FORMAT.md)
- [Memory-safe builds](docs/MEMORY_SAFE_BUILDS.md)
- [Proof blueprint and NVIDIA-spec traceability](docs/PROOF_BLUEPRINT.md)
- [Trust model](docs/TRUST_MODEL.md)
- [Correctness claims](docs/CORRECTNESS_CLAIMS.md)
- [Reproducibility details](docs/REPRODUCIBILITY.md)
- [Real-zeta POC algorithm](docs/algorithms/REAL_ZETA_POC.md)
- [High-bound zeta-zero verifier status](docs/algorithms/ZETA_ZERO_VERIFIER.md)
- [Ternary Goldbach external atoms](docs/algorithms/TERNARY_GOLDBACH_EXTERNAL_ATOMS.md)
- [GRH POC: GPU evaluator, certificates, certified numerics, and Lean instantiation](docs/algorithms/GRH_POC.md)
- [GRH POC benchmarks and full-run extrapolation](docs/algorithms/GRH_POC_BENCHMARKS.md)
