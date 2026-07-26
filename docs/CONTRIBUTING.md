# Contributing

> **Work in progress:** the repository is inviting early collaborators, not
> presenting a finished production system. Independent verification and
> constructive criticism are first-class contributions.

SparkInterval welcomes collaborators who want to connect rigorous finite
computation, CPUs and GPUs, secure execution evidence, and Lean proofs. You do
not need expertise in every layer. Contributions that make one boundary
smaller, clearer, or easier to reproduce are valuable.

Before proposing a large change, read the [project vision](VISION.md),
[correctness claims](CORRECTNESS_CLAIMS.md), and [trust model](TRUST_MODEL.md).
Those documents define the intended architecture and the language used for
security and proof claims.

## What the project needs now

The work is intentionally broader than implementation:

1. **Verify the foundation.** Reproduce builds and examples, inspect theorem
   dependencies, review exact arithmetic and formats, exercise rejection
   paths, and challenge every trust claim.
2. **Make the repository useful.** Improve installation, CI, packaging,
   stable interfaces, examples, issue organization, and contributor onboarding
   so a new user can reach a meaningful result without private context.
3. **Explain and share the work.** Help identify communities that could use or
   review SparkInterval, prepare tutorials and demonstrations, and describe the
   project accurately without erasing its current gaps.
4. **Build collaborations.** Explore concrete interfaces with Lean and other
   theorem-proving communities, rigorous-numerics libraries, proof-certificate
   systems, reproducibility infrastructure, and confidential-computing tools.
5. **Add finite computations.** Grow the registry with compelling, bounded
   problems only when each has explicit semantics, coverage, certificate
   checks, and a Lean theorem target.

See the [collaboration roadmap](ROADMAP.md) for proposed outcomes and signs
that each area is ready to advance.

## Technical work areas

### Formal arithmetic and algorithms

- Extend proved interval operations and exceptional-value semantics.
- Add closed registered computations with canonical inputs, executable
  semantics, explicit numeric bounds, and Lean soundness theorems.
- Develop certificate checkers for finite searches, sums, and interval sweeps.
- Complete the analytic and numerical foundations listed in the
  [high-bound zeta verifier](algorithms/ZETA_ZERO_VERIFIER.md).
- Grow the certified in-Lean numerics layer (`SparkInterval/Certified`):
  compose the Stirling Gamma-factor evaluator from the existing proved
  `log`/`arctan`/`exp` primitives, prove a rational upper bound for the
  Euler-Maclaurin error radius, and consume the two named remainder
  premises so the [GRH POC](algorithms/GRH_POC.md) endpoint enclosures
  become fully machine-checked.
- Attack the GRH POC's named analytic obligations directly, in rough order
  of difficulty: the L-function conjugation-symmetry lemma (identity
  theorem; upgrades one-sided windows to symmetric strips), the
  Euler-Maclaurin remainder for `HurwitzZeta.hurwitzZeta`, the complex
  Stirling remainder for `Complex.Gamma`, reality of the completed
  Dirichlet function (discharging the evaluator-model premise), and a
  formal Turing-method zero count — the deepest missing layer for both
  the zeta and Dirichlet verifiers.
- Port Platt's lattice/Taylor and unit-group-FFT algorithms to the GPU in
  double-double interval arithmetic so the evaluator reaches full-range
  heights (the direct evaluator is valid only for moderate ordinates; see
  the [benchmarks](algorithms/GRH_POC_BENCHMARKS.md) for the cost model).

### CPU/GPU correctness

- Extend the typed compiler beyond its current polynomial surface, especially
  directed division.
- Formalize more PTX instructions and emitted-program behavior.
- Narrow the PTX, `ptxas`, SASS, driver, and physical-hardware refinement gaps.
- Add exact CPU replay and adversarial conformance cases for GPU workloads.

### Secure execution and certificates

- Independently review and production-pin the Azure/AMD/vTPM and NVIDIA
  appraisers consumed by the implemented composite evidence adapter, including
  roots, revocation, TCB, measurements, freshness, and report-data binding.
- Review and exercise the implemented signed-receipt/source-registry importer,
  including Managed HSM key attestation, measured-runner policy, replay
  durability, negative cases, and the exact generated Lean source diff.
- Specify a content-addressed computation-certificate library, including
  immutable records, indexing, mirroring, revocation/supersession metadata,
  and a Lean-facing lookup workflow.
- Threat-model replay, rollback, equivocation, compromised builders, and
  certificate-library availability.

### Independent review and usability

- Reproduce CPU, DGX Spark, or H100 workflows on independent systems.
- Review claim language, axiom dependencies, canonical formats, and rejection
  paths.
- Improve examples and onboarding for Lean, CUDA, and attestation newcomers.
- Report places where a command succeeds but its assurance level is unclear.

### Community, adoption, and project connections

- Turn successful reproductions into concise public walkthroughs.
- Identify small, useful demonstrations that communicate the architecture
  without depending on speculative future features.
- Compare certificate and trust interfaces with adjacent projects and document
  concrete integration opportunities.
- Help establish release notes, a public roadmap, contributor recognition, and
  a sustainable issue-review process.
- Invite domain experts to propose bounded computations with a clear downstream
  Lean theorem, rather than adding benchmarks with no proof consumer.

## Choosing a first contribution

A good first contribution is narrow enough to state its claim in one sentence
and to name the evidence for that claim. Documentation, negative tests, small
Lean lemmas, exact-reference test vectors, and reproduction reports are all
good entry points.

For larger work, open a GitHub issue before investing heavily. Describe:

- the bounded computation or trust boundary being changed;
- the exact claim the result should support;
- which layer supplies the evidence: Lean proof, exact recomputation,
  conformance test, operator identity, or hardware attestation; and
- what remains outside the claim.

Browse the repository's
[issues](https://github.com/gersh/gpu_prover/issues) or propose a focused new
one. Security-sensitive findings should not be published as a proof of
exploitation against systems you do not own; coordinate a responsible report
with the maintainer instead.

## Development workflow

Keep generated outputs under `build/`; do not commit private keys, attestation
secrets, or local evidence that contains sensitive platform identifiers. The
repository may require memory-capped, serialized Lean builds, so read
[Memory-safe builds](MEMORY_SAFE_BUILDS.md) before invoking Lean directly.

For a documentation-only change, run:

```bash
python3 -m unittest discover -s tests -p 'test_documentation.py' -v
git diff --check
```

For Lean changes, use the safe entry point and audit dependencies:

```bash
./tools/safe_lake_build.py
make audit
```

The no-argument build and local audit use `SparkIntervalCompact`. The full
materialized axiom audit is a measured Azure qualification job; do not run
`tools/audit_axioms.sh` as an ordinary local check.

For Python changes, run the relevant focused test first, then the suite when
practical:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

GPU changes should also run the applicable workflow from
[Reproducibility](REPRODUCIBILITY.md). State clearly when hardware was not
available and only offline checks were run.

## Pull request expectations

A contribution should:

- keep the mathematical, modeled-execution, physical-execution, and provenance
  claims distinct;
- include tests or a reproducible verification command proportional to the
  change;
- document new formats, trusted components, axioms, or unsupported cases;
- preserve fail-closed behavior at evidence and attestation boundaries;
- avoid editing immutable versioned specifications in place; and
- avoid unrelated generated files or local build artifacts.

When a change adds an axiom or trusted component, explain why ordinary proof or
independent checking cannot cover the boundary. The project currently permits
one named execution axiom, so widening that surface requires especially careful
review.

## Review vocabulary

Use the weakest accurate term:

- **proved** for a Lean theorem with disclosed dependencies;
- **independently checked** for exact certificate or reference recomputation;
- **modeled** for results inside the formal machine semantics;
- **tested** or **conformant on the tested cases** for differential testing;
- **operator-signed** for a record endorsed by a pinned key; and
- **hardware-attested** only after production evidence and policy verification.

If a change crosses more than one of these layers, document each link
separately. The [verifier guide](VERIFYING.md#claim-language) contains the
project's accepted public claim language.

## License

By contributing, you agree that your contribution is licensed under the
repository's [MIT License](../LICENSE).
