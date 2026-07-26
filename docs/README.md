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
`accepted_run_certificate_sound` is the only project execution axiom, and its
premise is the exact source-admitted `checkTrustedCompute` policy. The axiom
returns both an exact historical outcome and the fixed `Runs` relation for any
matching constructor of the closed invocation registry. The legacy DGX and
H100 structural checks remain useful diagnostics, but `RunCertificate.check`
rejects both constructors and neither check can reach the axiom. Downstream
checkers separately prove exact payload binding and either independently check
certificate mathematics or apply an ordinary soundness theorem for the
registered algorithm.

The proposed narrower successor is the
[architecture execution boundary](ARCHITECTURE_EXECUTION_BOUNDARY.md): the
single trusted per-run import would assert only an exact formal CPU/GPU
execution, while separately proved executable refinement and checker
soundness derive the application claim. That boundary is implemented as an
axiom-free interface and tiny test, but it has not replaced the current axiom
or acquired a production x86-64/SASS instantiation.

The closed *algorithm* registry currently contains the exact-rational
`cubicSumDivThree20000V1` CPU tutorial and the one-row
`h100FormalPtxConstantOneV1` `sm_90` pilot. The pilot's PTX is definitionally
linked to the formal emitter for its closed constant `[1,1]` batch. Neither is
a zeta or Ternary-Goldbach computation. The separate source-pinned
trusted-compute receipt registry is implemented but its tracked list is empty:
no Azure run has been admitted. The collector, independent-appraisal adapter,
signed-receipt issuer, registry generator, and generated Lean consumer are
available for both Azure SEV-SNP CPU jobs and composite Azure NCC H100 jobs.
Production use still requires reviewed appraiser binaries and policies,
measured-runner enforcement, a production Managed HSM key and key-attestation
review, an actual Azure run, and review of the resulting registry change.

For that tutorial, Lean separately proves the executable integer
`cubicNumeratorLoop` and divide-once `cubicSumDivThreeMachine`, their exact
result and agreement with the rational specification, and u64 no-overflow at
every step. Those are axiom-free algorithm and bounded-arithmetic results; the
certificate axiom alone supplies the per-run physical-to-formal connection.

## Users

- [Project overview and quick start](../README.md)
- [Using computation certificates from Lean](LEAN_INTEGRATION.md)
- [Lean arithmetic bridge for accelerated campaigns](LEAN_ARITHMETIC_BRIDGE.md)
- [Project vision and target architecture](VISION.md)
- [Collaboration roadmap](ROADMAP.md)
- [User workflows](USING.md)
- [DGX Spark setup](DGX_SPARK_SETUP.md)
- [Worked examples](../examples/README.md)
- [H100 offline support](H100.md)
- [Challenge-first Azure CPU/H100 measured runner](AZURE_MEASURED_RUNNER.md)
- [Azure confidential CPU/H100 execution](AZURE_CONFIDENTIAL_COMPUTE.md)
- [Azure H100 production operator state machine](AZURE_H100_PRODUCTION_OPERATOR.md)
- [Azure SEV-SNP CPU production operator state machine](AZURE_CPU_PRODUCTION_OPERATOR.md)
- [Fail-closed Azure ternary-Goldbach portfolio DAG](AZURE_TG_PORTFOLIO_ORCHESTRATION.md)
- [Read-only Azure ternary-Goldbach launch preflight](AZURE_TG_LAUNCH_PREFLIGHT.md)
- [DGX Spark benchmarks and Azure performance sizing](AZURE_PERFORMANCE_SIZING.md)
- [Azure Managed HSM receipt signing](AZURE_MANAGED_HSM_SIGNING.md)
- [Pinned numeric-corpus references and cloud-receipt binding](NUMERIC_CORPUS_REFERENCES.md)

## Verifiers

- [Verifier guide](VERIFYING.md)
- [Correctness claims and proof boundary](CORRECTNESS_CLAIMS.md)
- [Trust model and execution assumptions](TRUST_MODEL.md)
- [Attested-provenance trust model (prototype, not adopted)](ATTESTED_PROVENANCE_TRUST_MODEL.md)
- [Exact CPU/GPU architecture execution boundary](ARCHITECTURE_EXECUTION_BOUNDARY.md)
- [Compact opaque architecture-run receipt boundary](algorithms/COMPACT_ARCHITECTURE_RECEIPT_BOUNDARY.md)
- [Static x86 binary-certificate boundary](algorithms/SQRT218_STATIC_BINARY_CERTIFICATE.md)
- [Reproducibility and independent-checking runbook](REPRODUCIBILITY.md)
- [GPU and typed-machine model](GPU_MODEL.md)
- [Proof blueprint and NVIDIA-spec traceability](PROOF_BLUEPRINT.md)

## Operators and maintainers

- [Contributor guide and priority work](CONTRIBUTING.md)
- [Memory-safe build requirements](MEMORY_SAFE_BUILDS.md)
- [LeanArchitect proof-map generation](PROOF_BLUEPRINT.md)
- [DGX Spark setup and acceptance runs](DGX_SPARK_SETUP.md)
- [Attestation component boundary](../attestation/README.md)
- [Challenge-first measured-runner and evidence handoff](AZURE_MEASURED_RUNNER.md)
- [Azure confidential CPU/H100 operator workflow](AZURE_CONFIDENTIAL_COMPUTE.md)
- [Fail-closed Azure H100 production runbook](AZURE_H100_PRODUCTION_OPERATOR.md)
- [Fail-closed Azure SEV-SNP CPU production runbook](AZURE_CPU_PRODUCTION_OPERATOR.md)
- [Azure ternary-Goldbach portfolio planning and resume](AZURE_TG_PORTFOLIO_ORCHESTRATION.md)
- [Azure ternary-Goldbach launch preflight and blocker classes](AZURE_TG_LAUNCH_PREFLIGHT.md)
- [Managed HSM key provisioning, attestation, and receipt signing](AZURE_MANAGED_HSM_SIGNING.md)

## Format reference

- [Certificates, run bundles, profiles, and signatures](FORMAT.md)
- [Real-integer zeta tutorial](algorithms/REAL_ZETA_POC.md)
- [High-bound zeta-zero verifier: signed payload composition, multiplicity bridge, gaps, and host benchmark scope](algorithms/ZETA_ZERO_VERIFIER.md)
- [Resumable ternary-Goldbach FLINT zeta-zero campaigns](algorithms/TG_ZETA_ZERO_CAMPAIGN.md)
- [Closed Azure measured CH25 Lemma A.7 boundary replay](algorithms/CH25_A7_AZURE_MEASURED_WORKLOAD.md)
- [Closed Azure measured Platt-head replay through 20,000](algorithms/PLATT_HEAD_AZURE_MEASURED_WORKLOAD.md)
- [Source-scale FLINT Platt zeta-RH campaign](algorithms/PLATT_ZETA_FLINT_CAMPAIGN.md)
- [Exact five-phase PT21 Azure CPU materialization route](algorithms/PLATT_PT21_AZURE_CPU_MATERIALIZER.md)
- [Pinned Platt PT21 windowed source campaign and H100 work model](algorithms/PLATT_PT21_WINDOWED_SOURCE_CAMPAIGN.md)
- [Bounded PT21 CPU/FLINT stationary-point fallback](algorithms/PLATT_PT21_STATIONARY_RESOLVER.md)
- [Bounded PT21 CUDA/FLINT Turing-to-native block chain](algorithms/PLATT_PT21_BOUNDED_BLOCK_CHAIN.md)
- [Bounded PT21 persistent CUDA/FLINT/Arb worker](algorithms/PLATT_PT21_PERSISTENT_WORKER.md)
- [Qualification-only PT21 native packet-scan fast path](algorithms/PLATT_PT21_NATIVE_SCAN_FASTPATH.md)
- [Qualification-only PT21 DD FFT stages-1..9 shared tile](algorithms/PLATT_PT21_DD_TILE9_QUALIFICATION.md)
- [Qualification-only PT21 bounded sloppy-DD root multiplication](algorithms/PLATT_PT21_DD_SLOPPY_MUL_QUALIFICATION.md)
- [Qualification-only live V2 block-0 transform-candidate bridge](algorithms/PLATT_PT21_LIVE_TRANSFORM_CANDIDATE_QUALIFICATION.md)
- [Qualification-only PT21 fused bit-reversal/stages-1..9 tile](algorithms/PLATT_PT21_BITREVERSE_TILE9_QUALIFICATION.md)
- [Qualification-only independently recentered PT21 producer/consumer pipeline](algorithms/PLATT_PT21_RECENTERED_PIPELINE.md)
- [GRH finite-verification POC (Platt arXiv:1305.3087): GPU interval evaluator, certificates, and Lean instantiation](algorithms/GRH_POC.md)
- [GRH POC benchmarks and full-run extrapolation](algorithms/GRH_POC_BENCHMARKS.md)
- [Ternary Goldbach external atoms: exact status, artifact audits, and feasibility](algorithms/TERNARY_GOLDBACH_EXTERNAL_ATOMS.md)
- [Ternary Goldbach external-program readiness matrix](algorithms/TERNARY_GOLDBACH_EXTERNAL_PROGRAM_READINESS.md)
- [Prop1224 and Hurst candidate artifact wires](algorithms/PROP1224_HURST_CANDIDATE_ARTIFACT_WIRES.md)
- [Four analytic artifact source-program boundaries and exact remaining proofs](algorithms/ANALYTIC_ARTIFACT_SOURCE_PROGRAM_AUDIT.md)
- [Compact receipt closure for all thirteen atoms and the lowered finite endpoint](algorithms/TERNARY_GOLDBACH_COMPACT_RECEIPT_CLOSURE.md)
- [CDEM Abel recurrence certificate and trusted-compute handoff](algorithms/CDEM_ABEL_TRUSTED_COMPUTE_BRIDGE.md)
- [CDEM Abel two-stage artifact-input terminal](algorithms/CDEM_ABEL_ARTIFACT_TERMINAL.md)
- [Unified ternary-Goldbach campaign control plane](algorithms/TERNARY_GOLDBACH_CAMPAIGNS.md)
- [H100-cluster Slurm deployment for all thirteen ternary-Goldbach campaigns](algorithms/H100_TG_CLUSTER.md)
- [Directed-rational Proposition 12.2.4 reference](algorithms/PROP1224_DIRECTED_REFERENCE.md)
- [Literal full-source Proposition 12.2.4 supervisor](algorithms/PROP1224_FULL_CAMPAIGN.md)
- [Proposition 12.2.4 parallel CPU/H100 source-rank campaign](algorithms/PROP1224_H100_CPU_CAMPAIGN.md)
- [Proposition 12.2.4 closed Azure measured phase DAG](algorithms/PROP1224_AZURE_MEASURED_DAG.md)
- [CH25 psi source-scale two-pass CPU verifier](algorithms/CH25_PSI_VERIFIER.md)
- [CH25 psi closed Azure measured phase DAG](algorithms/CH25_PSI_AZURE_MEASURED_DAG.md)
- [Exact parallel CPU optimization for Hurst affine guards](algorithms/HURST_AFFINE_GUARD_OPTIMIZATION.md)
- [Bounded Möbius GPU/Hurst optimization and qualification](algorithms/MOBIUS_GPU_HURST_QUALIFICATION.md)
- [Paired p5/global-scan versus p11/block-compose qualification](algorithms/MOBIUS_HURST_COMBINED_QUALIFICATION.md)
- [Bounded exact CUDA chunks for the Ramaré R2Star campaign](algorithms/R2STAR_CUDA_CHUNKS.md)
- [Exact resumable CUDA campaigns for both little-Mertens atoms](algorithms/LITTLE_MERTENS_CUDA_CAMPAIGN.md)
- [Helfgott--Platt prime-ladder and binary-Goldbach reconstruction](algorithms/GOLDBACH_LADDER_CAMPAIGN.md)
- [Historical Goldbach Azure measured DAG](algorithms/GOLDBACH_HISTORICAL_AZURE_MEASURED_DAG.md)
- [Distinct finite Goldbach campaign below the `10^27` analytic crossover](algorithms/GOLDBACH_10POW27_CAMPAIGN.md)
- [Word-oriented binary-Goldbach shifted-OR coverage](algorithms/GOLDBACH_SHIFTED_BITSET_OPTIMIZATION.md)
- [Cofactor-filtered Goldbach sieve tail](algorithms/GOLDBACH_WHEEL_FILTERED_SIEVE.md)
- [Qualification-only through-23 Goldbach word-owner wheel](algorithms/GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION.md)
- [Base-trio arithmetic model for the through-23 word-owner wheel](algorithms/GOLDBACH_WORD_OWNER_WHEEL23_LEAN.md)
- [Content-addressed optimized GoldbachGPU candidate qualification and H100 calibration gate](algorithms/GOLDBACH_OPTIMIZED_CANDIDATE_QUALIFICATION.md)
- [Persistent bucketed odd-prime sieve and source-height bottleneck](algorithms/GOLDBACH_PERSISTENT_BUCKET_SIEVE.md)
- [Race-free tile-compacted Goldbach sieve and bounded Azure sensitivity](algorithms/GOLDBACH_TILE_COMPACTED_SIEVE.md)
- [Historical Goldbach artifacts, missing inputs, and fail-closed Azure import design](algorithms/GOLDBACH_HISTORICAL_ARTIFACT_IMPORT.md)
- [Platt Theorem 7.1 Dirichlet-GRH campaign and rigorous FLINT fallback](algorithms/DIRICHLET_GRH_CAMPAIGN.md)
- [Exact Platt Theorem 7.1 Lean source handoff](algorithms/PLATT_THEOREM_71_LEAN_HANDOFF.md)
- [Certified Hurwitz-lattice seeds, finite recovery, and exact Taylor-tail input bundles](algorithms/DIRICHLET_LATTICE_CERTIFICATES.md)
- [Conditional Platt large-q H100/CPU lattice-Taylor stage, exact checker, and source sharding](algorithms/DIRICHLET_LATTICE_H100_STAGE.md)
- [Authenticated 125-GiB t-major Hurwitz main-grid cache, replay binding, and deterministic broadcast plan](algorithms/DIRICHLET_LATTICE_CACHE.md)
- [Authenticated t-major cache-range to resident q-major CUDA row feed](algorithms/DIRICHLET_CACHE_RESIDENT_FEED.md)
- [All-character CRT/Bluestein directed interval transform and MPFR replay](algorithms/DIRICHLET_ALL_CHARACTER_FFT_STAGE.md)
- [Verified packed-byte and virtual-slice SHA-256](algorithms/LEAN_STREAMING_SHA256.md)
- [Production q-order streaming Lean checker](algorithms/DIRICHLET_QORDER_STREAMING_CHECKER.md)
- [Qualified large-q lattice and all-character fast path](algorithms/DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md)
- [Persistent completed-factor source service and streaming Lean checker](algorithms/DIRICHLET_COMPLETED_FACTOR_SOURCE_SERVICE.md)
- [Bounded large-q residue composition and independent MPFR replay](algorithms/DIRICHLET_RESIDUE_COMPOSITION.md)
- [Fused persistent large-q certified-box CUDA batches](algorithms/DIRICHLET_LARGEQ_BATCH_STAGE.md)
- [Fully replayed finite-recovery recurrence seeds and compact fused CUDA service](algorithms/DIRICHLET_RECOVERY_SEEDED_STAGE.md)
- [Certified all-character root-number artifacts](algorithms/DIRICHLET_ROOT_NUMBER_STAGE.md)
- [Resident GPU completed-L sign reduction and compact phase state](algorithms/DIRICHLET_COMPLETED_SIGN_GPU_REDUCER.md)
- [Streaming source-wide TGDRNRO1 root-artifact catalog](algorithms/DIRICHLET_ROOT_CATALOG.md)
- [Persistent large-q composition/FFT/completed-L process graph](algorithms/DIRICHLET_LARGEQ_PIPELINE.md)
- [Typed fixed-q FFT pipeline receipt bundle and fail-closed replay](algorithms/DIRICHLET_FFT_PIPELINE_RECEIPT_BUNDLE.md)
- [Fail-closed source-wide t-major supervisor plan and exact FFT roster](algorithms/DIRICHLET_SOURCE_SUPERVISOR.md)
- [Authenticated shared-row spool and deterministic fixed-q run inputs](algorithms/DIRICHLET_TMAJOR_SPOOL.md)
- [Direct-MPFR authenticated t-major CUDA blocks and one-upload row-resident composition](algorithms/DIRICHLET_TMAJOR_CUDA_BLOCK.md)
- [Bounded exact-rational t-major factor recurrence with real CUDA/MPFR/Arb downstream qualification](algorithms/DIRICHLET_TMAJOR_FACTOR_RECURRENCE.md)
- [Authenticated t-major cache-row to typed FFT bundle admission adapter](algorithms/DIRICHLET_TMAJOR_ADAPTER.md)
- [Fail-closed t-block subprocess supervisor, resumable checkpoints, and exact production boundary](algorithms/DIRICHLET_TBLOCK_SUPERVISOR.md)
- [Source-streaming TGDCSB03 dense transition state, sparse ambiguity retention, and aggregate-Turing boundary](algorithms/DIRICHLET_SOURCE_STREAMING_V3.md)
- [Small-q TGDBSPK1 runner-side strict-sign transport and compact-v3 boundary](algorithms/DIRICHLET_SMALLQ_PACKED_SIGN_TRANSPORT.md)
- [Platt--Booker small-conductor Gaussian/DFT stage](algorithms/DIRICHLET_BOOKER_SMALLQ_STAGE.md)
- [Compact fused selected-character Dirichlet H100 stage and exact-dyadic replay](algorithms/DIRICHLET_FUSED_CHARACTER_STAGE.md)
- [Persistent all-character completed-L/sign stream consumer](algorithms/DIRICHLET_STREAM_ZERO_CONSUMER.md)
- [Completed-L, sinc interpolation, zero isolation, and Turing-closure boundary](algorithms/DIRICHLET_ZERO_CLOSURE_STAGE.md)
- [Directed factor-eight completed-value postprocessing](algorithms/DIRICHLET_FACTOR8_POSTPROCESS.md)
- [Immutable algorithm specifications](../specifications/README.md)
- [Canonical JSON schemas](../schemas/)
- [Target and trust profiles](../profiles/)

The zeta tutorial evaluates positive real values for integers greater than one.
It does not verify critical-strip zeros or zeros up to a height.
