# Documentation

SparkInterval's goal is provable, explicitly bounded arithmetic on CPUs and
GPUs, with secure execution evidence turned into reusable finite-computation
certificates that Lean can reference through a narrow axiom boundary. The
[project vision](VISION.md) describes that target architecture; the
[contributor guide](CONTRIBUTING.md) lists the most useful open work, and the
[collaboration roadmap](ROADMAP.md) organizes verification, adoption,
partnerships, and future computations.

The current implementation separates mathematical verification, modeled GPU
execution, and physical-run provenance. Start with the section that matches
your role, and consult the correctness matrix before interpreting a result.

The Lean execution boundary is deliberately singular:
`accepted_run_certificate_sound` is the only project execution axiom. DGX and
H100 policy-specific names and `accepted_registered_run_sound` are proved
projections, not additional axioms. The axiom returns both an exact historical
outcome and the fixed `Runs` relation for any matching constructor of the
closed invocation registry. Downstream checkers separately prove exact payload
binding and either independently check certificate mathematics or apply an
ordinary soundness theorem for the registered algorithm.

The registry currently contains only the exact-rational
`cubicSumDivThree20000V1` tutorial invocation. No zeta checker is registered,
and no signed wire-bundle importer can construct Lean's private positive
evidence capability today.

For that tutorial, Lean separately proves the executable integer
`cubicNumeratorLoop` and divide-once `cubicSumDivThreeMachine`, their exact
result and agreement with the rational specification, and u64 no-overflow at
every step. Those are axiom-free algorithm and bounded-arithmetic results; the
certificate axiom alone supplies the per-run physical-to-formal connection.

## Users

- [Project overview and quick start](../README.md)
- [Using computation certificates from Lean](LEAN_INTEGRATION.md)
- [Project vision and target architecture](VISION.md)
- [Collaboration roadmap](ROADMAP.md)
- [User workflows](USING.md)
- [DGX Spark setup](DGX_SPARK_SETUP.md)
- [Worked examples](../examples/README.md)
- [H100 offline support](H100.md)

## Verifiers

- [Verifier guide](VERIFYING.md)
- [Correctness claims and proof boundary](CORRECTNESS_CLAIMS.md)
- [Trust model and execution assumptions](TRUST_MODEL.md)
- [Reproducibility and independent-checking runbook](REPRODUCIBILITY.md)
- [GPU and typed-machine model](GPU_MODEL.md)
- [Proof blueprint and NVIDIA-spec traceability](PROOF_BLUEPRINT.md)

## Operators and maintainers

- [Contributor guide and priority work](CONTRIBUTING.md)
- [Memory-safe build requirements](MEMORY_SAFE_BUILDS.md)
- [LeanArchitect proof-map generation](PROOF_BLUEPRINT.md)
- [DGX Spark setup and acceptance runs](DGX_SPARK_SETUP.md)
- [Attestation component boundary](../attestation/README.md)

## Format reference

- [Certificates, run bundles, profiles, and signatures](FORMAT.md)
- [Real-integer zeta tutorial](algorithms/REAL_ZETA_POC.md)
- [High-bound zeta-zero verifier: signed payload composition, multiplicity bridge, gaps, and host benchmark scope](algorithms/ZETA_ZERO_VERIFIER.md)
- [GRH finite-verification POC (Platt arXiv:1305.3087): GPU interval evaluator, certificates, and Lean instantiation](algorithms/GRH_POC.md)
- [GRH POC benchmarks and full-run extrapolation](algorithms/GRH_POC_BENCHMARKS.md)
- [Ternary Goldbach external atoms: exact status, artifact audits, and feasibility](algorithms/TERNARY_GOLDBACH_EXTERNAL_ATOMS.md)
- [Directed-rational Proposition 12.2.4 reference](algorithms/PROP1224_DIRECTED_REFERENCE.md)
- [Bounded exact CUDA chunks for the Ramaré R2Star campaign](algorithms/R2STAR_CUDA_CHUNKS.md)
- [Immutable algorithm specifications](../specifications/README.md)
- [Canonical JSON schemas](../schemas/)
- [Target and trust profiles](../profiles/)

The zeta tutorial evaluates positive real values for integers greater than one.
It does not verify critical-strip zeros or zeros up to a height.
