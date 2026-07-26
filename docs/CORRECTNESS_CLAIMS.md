# Correctness claims

SparkInterval separates mathematical soundness, modeled program execution,
testing evidence, and physical-run provenance. Evidence in one column does not
silently supply evidence in another.

## Support matrix

| Surface | Established claim | Evidence | Boundary |
| --- | --- | --- | --- |
| Abstract interval expressions | Every realized exact value is contained in the interval evaluator's result | Lean theorem [`evalInterval_sound`](../SparkInterval/EvalSound.lean#L84) | Exact-real model; no floating-point program |
| Directed binary64 interval arithmetic | Downward/upward rounding encloses the exact value, and interval add, subtract, and multiply contain their exact-real operations; division does too when the divisor interval excludes zero | Lean theorems in [`DirectedRounding.lean`](../SparkInterval/DirectedRounding.lean#L182) and [`FPIntervalSound.lean`](../SparkInterval/FPIntervalSound.lean#L71) | Value-level model; signed-zero encodings are not distinguished in the real interpretation |
| Exact complex-disk arithmetic certificate | Finite binary64 disk words decode to exact rationals; successful rational checkers prove proposed output disks enclose every sum or product of values in the input disks | [`ComplexDisk.lean`](../SparkInterval/Certified/ComplexDisk.lean) and [`ComplexDiskCertificateTest.lean`](../SparkInterval/Tests/ComplexDiskCertificateTest.lean) | Arithmetic postconditions only; they do not prove CUDA parsing, instruction execution, trace coverage, or physical refinement |
| Factored small-`q` raw arithmetic campaign | The application fixes the ordered modulus specifications and, within each modulus, the character/frequency Cartesian product, exact term count, parity, and sign branch. Raw binary64 witnesses prove the complete finite Gaussian sum, prefactor multiplication, conjugation, and tail inflation. A bounded raw DFT checker enforces canonical finite input/twiddle/butterfly/output lists, exact decoding, nonnegative input/twiddle/output radii, all typed radix-2 checks, and pointwise equality of literal raw output words with the derived final state. Exact natural-order/bit-reversal links compose the source cells to those raw words. A generic block invariant proves the staged network equals the direct positive DFT. The outer theorem aligns analytic premises and certificates by the same ordered modulus relation | [`FactoredSmallQRawPostprocessModulusCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawPostprocessModulusCampaign.lean), [`FactoredSmallQRawDFT.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawDFT.lean), [`FactoredSmallQRawDFTComposition.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawDFTComposition.lean), [`FactoredSmallQDFTCorrectness.lean`](../SparkInterval/Dirichlet/FactoredSmallQDFTCorrectness.lean), and focused tests | The standalone multiplication byte parser is proved, but whole-frame parsing or deterministic sidecar generation and physical realization of the complete trace are not. Analytic seed/root/tail containment, realization of the paper's exact primitive-character rosters, useful final width/zero count, and physical execution remain separate |
| Factored small-`q` completed signs | Checked disk multiplications and radius inflation prove the explicit scale/time-tail/untilt equation; the checker also requires scale and untilt disks to certify strictly positive reals. A rational disk entirely to one side of the imaginary axis proves the strict sign of the analytically real completed value. A distinct source-sample campaign checks exact roster-times-`[0,sampleCount)` coverage and `sampleCount <= fullDFTLength`. The Python semantic reducer now parses every `TGDBSQR3` disk, joins a completely higher-precision-replayed parity-specific `timeTail/(2*pi/b)` control, and emits strict negative/positive or explicit ambiguity in the same complete coordinate order | [`FactoredSmallQCompletedSign.lean`](../SparkInterval/Dirichlet/FactoredSmallQCompletedSign.lean), [`FactoredSmallQCompletedSignCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQCompletedSignCampaign.lean), [`dirichlet_booker_smallq_semantic_reducer.py`](../tg_verifier/dirichlet_booker_smallq_semantic_reducer.py), and focused tests | The semantic reducer's strict comparison is exact, but its compact two-bit artifact is not yet parsed into the raw Lean multiplication certificates and does not replay DFT containment after raw disks are discarded. Scale/untilt disk containment, completed-value reality, measured execution, and the full raw-word-to-analytic-source bridge remain explicit. A square complex interval of component radius `E` cannot be reused as a norm-`E` disk without a `sqrt 2` allowance. No sign-change pairing, interpolation, exception handling, zero isolation, multiplicity inference, or Turing count is performed |
| Raw completed-sign arithmetic | Both disk multiplications and the time-tail inflation decode from literal finite binary64 words; the first raw operand must equal the supplied Fourier word before decoding. Only signed codes `-1` and `+1` are accepted, matching the Python producer. The source-sample campaign looks up the exact raw DFT output word for every key and passes it directly to the raw sign checker; exact typed checking then proves the direct-DFT source-formula sign | [`FactoredSmallQRawCompletedSign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSign.lean), [`FactoredSmallQRawCompletedSignPayloadCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSignPayloadCampaign.lean), their focused tests, and the central axiom audit | This closes raw arithmetic and exact raw-word attachment for one source modulus, not whole-frame parsing or physical execution. The source analytic containments/reality facts and final zero/Turing layers remain explicit |
| Raw small-`q` DFT-to-sign composition | A Boolean bridge checks modulus, exact roster, full power-of-two DFT length, retained sample bound, and every retained disk equality. Header-wide `a,b,eta` parameters have explicit guards `0<a`, `0<b`, `-1<eta<1`, `b=2^logLength/a`; `t=sample/a`, `bookerA=64/5`, `2*pi/b`, and `exp(-pi*eta*t/4)` are named definitions. For every requested source sample, the theorem returns its literal raw binary64 DFT word, exact disk decoding, containment of the exact direct positive DFT of the postprocessed source, and a strict source-formula completed-value sign | [`FactoredSmallQRawCompletedSignCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSignCampaign.lean), [`FactoredSmallQRawCompletedSignCampaignTest.lean`](../SparkInterval/Tests/FactoredSmallQRawCompletedSignCampaignTest.lean), and the central axiom audit | This is an ordinary Lean arithmetic theorem, not a v3 byte-parser, physical execution, or analytic-source theorem. Gaussian base/character/prefactor/tail and root containment, exact factor containment, time-tail norm bound, completed-value reality, primitive-character roster realization, and downstream zero/Turing closure remain explicit |
| Ordered all-modulus DFT-to-source-sign composition | A nonempty source-owned list with unique modulus identifiers is matched in exact order and length to complete finite bundles and source headers. Successful raw decoding canonically supplies each typed DFT certificate, eliminating a separately trusted decoded-transform field. For every requested modulus, character, and sample the theorem exposes the raw word, direct DFT enclosure, source grid guards/equation, and strict source-formula sign | [`FactoredSmallQRawCompletedSignModulusCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSignModulusCampaign.lean), its focused two-modulus fail-closed test, and the central axiom audit | The ordered Lean theorem prevents cross-modulus certificate or premise substitution. It still assumes the explicitly named analytic containments/reality facts and does not prove that the source list is precisely the paper's primitive-character domain or that a physical producer emitted the raw words |
| Fully raw all-modulus DFT-to-sign composition | Every modulus bundle carries both raw DFT words and raw completed-sign payloads. The checker indexes the source-owned character/sample coordinate and passes that literal word to the corresponding raw sign checker while exact ordered relations align all finite and analytic inputs | [`FactoredSmallQRawCompletedSignPayloadModulusCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSignPayloadModulusCampaign.lean), its focused structural test, and the central axiom audit | This removes the typed sign-payload substitution boundary. It does not parse a physical frame, prove execution, realize the paper's primitive-character roster, or prove the analytic containment/reality premises |
| Raw campaign cells to checked brackets | A typed endpoint must be the deterministic decode of an actual raw campaign cell, and its Fourier disk is decoded from the literal raw DFT word at that same source-owned key. Two such cells with exact rational grid order and opposite decoded signs produce a checked rational bracket; exact `sample/a` cast lemmas include Booker's `a=64/5`. A semantic corollary composes explicit `SourceRealizes` premises into endpoint enclosures | [`FactoredSmallQRawZeroBracketCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawZeroBracketCampaign.lean), its detached-word and signed-zero fail-closed test, and the central axiom audit | This is the complete finite arithmetic join, not an analytic zero theorem. Equality with the actual completed-L evaluator and numeric-character realization remain explicit semantic premises |
| Source and character realization contract | A supplied noduplicated opaque-ID roster is in exact bijection with the primitive characters of one modulus; every in-domain application row and parity branch is fixed to that roster character; and one complex equation identifies the exact source expression with a fixed real evaluator at every retained sample on Booker's `a=64/5` grid. The requested-cell theorem composes both contracts with the raw arithmetic result to expose the exact character row, parity, literal-word direct-DFT enclosure, and endpoint `EvaluatorLink` at one cell | [`FactoredSmallQSourceRealization.lean`](../SparkInterval/Dirichlet/FactoredSmallQSourceRealization.lean), [`FactoredSmallQSourceRealizationTest.lean`](../SparkInterval/Tests/FactoredSmallQSourceRealizationTest.lean), and the central axiom audit | These are conditional propositions and composition theorems; no concrete source roster, Conrey enumeration, analytic source equation, completed-L Hardy-model identity, byte parser, or physical execution is constructed here |
| Completed signs to rational zero brackets | Final completed-value disks are projected to rational real intervals. One exact checker enforces a positive rational sampling rate, `time=sample/a`, one fixed character, increasing samples and times, opposite strict signs, and global bracket separation; explicit evaluator links then construct the existing ordered zero certificate | [`FactoredSmallQZeroBracket.lean`](../SparkInterval/Dirichlet/FactoredSmallQZeroBracket.lean), its fail-closed focused test, and the central axiom audit | The bridge proves arithmetic enclosure and bracket structure, but does not infer completed-L evaluator identity or reality from metadata. Source pair selection, upsampling/exceptions, the Hardy model, conjugation, and the total-zero upper count remain separate |
| Completed bracket family to finite Dirichlet GRH | A checked family composes directly with a supplied completed-L Hardy model and a complete L-zero upper count to prove that every nontrivial zero in `(0,1) x [lo,hi]` lies on the critical line. Finiteness is derived by containment in the closed compact envelope `[0,1] x [lo,hi]`; the per-modulus theorem requires the same explicit package for every primitive character | [`FactoredSmallQGRHBridge.lean`](../SparkInterval/Dirichlet/FactoredSmallQGRHBridge.lean), its focused test, and the central axiom audit | This is a conditional theorem, not a computed GRH result. Evaluator identity, endpoint links, source-height bounds, nontriviality, and the Turing/argument-principle upper count are theorem premises, not certificate metadata |
| Primitive roster to modulus-level finite GRH | Exact roster completeness chooses the unique opaque identifier for any primitive mathematical character. A checked bracket family whose header is explicitly that identifier, together with its source-indexed evaluator links, corresponding Hardy model, height bounds, and total-zero upper count, yields `GRHVerifiedForModulus` | [`FactoredSmallQRosterGRHBridge.lean`](../SparkInterval/Dirichlet/FactoredSmallQRosterGRHBridge.lean), [`FactoredSmallQRosterGRHBridgeTest.lean`](../SparkInterval/Tests/FactoredSmallQRosterGRHBridgeTest.lean), and the central axiom audit | The family-header equality is used in the proof, but every roster realization, family, evaluator/Hardy identity, and total count is still an explicit uninhabited production obligation |
| Platt Theorem 7.1 source handoff | Source-faithful open-strip `GRHVerifiedForModulus` results for every primitive character and every conductor through 400000 at the exact even/odd source heights imply the expanded source proposition used downstream. The closed CPU/SEV-SNP finalizer pins both height formulas, the exact `q=2..400000` roster count and separate `q=1` zeta source; result `true` requires the exact two-field universal `PlattTheorem71SourceEvidence` | [`PlattTheorem71Contract.lean`](../SparkInterval/Dirichlet/PlattTheorem71Contract.lean), [`RegisteredPlattTheorem71Certificate.lean`](../SparkInterval/Execution/RegisteredPlattTheorem71Certificate.lean), focused tests, and the blueprint nodes | This is a conditional theorem and receipt route, not verification evidence. No completed campaign or successful receipt exists. Source roster realization, completed-L/Hardy identity, complete zero brackets, conjugation/reflection, and every total-zero upper count remain open; the exact semantic shape is staged but remains disabled |
| NVIDIA PTX 9.0 formal slice | The existing finite-operand directed `add/sub/mul` and non-NaN `min/max` machine steps agree with a pinned Lean transcription; generated opcode traces have clause references | [`NvidiaPTXSpec.lean`](../SparkInterval/PTX/NvidiaPTXSpec.lean) and [`NvidiaPTXRefinement.lean`](../SparkInterval/PTX/NvidiaPTXRefinement.lean) | Vendor prose is externally reviewed; clause coverage is not full opcode semantics; no division or complete PTX/backend refinement |
| SM90 fused large-q addback slice | A checked restricted two-instruction `DADD.RM`/`DADD.RP` slice refines one outward interval add; a separate check binds the audited source/cubin/SASS/manifest hashes to a registered statement | [`FusedLargeQAddbackSlice.lean`](../SparkInterval/SASS/FusedLargeQAddbackSlice.lean) | One post-compilation arithmetic slice only; decoding authority, reachability, live-register provenance, surrounding kernel, compiler, driver, and hardware refinement remain open |
| Hurst affine block certificate | Exact four-coordinate block deltas, guards, half-open adjacency, and prefix/final-state composition follow from the Boolean checker. The production replay interface separately states primitive row deltas and local guard safety; it does not assert a global prefix for every guard state | [`HurstAffineCertificate.lean`](../SparkInterval/TernaryGoldbach/HurstAffineCertificate.lean) | `ReplayBlockRealization.rowDeltaValid` and its guard-wide local `rowSafe` field are physical, currently uninhabited premises. Complete `[1,10^16+1)` coverage and the zero root are also explicit; the production supervisor still rejects affine receipts |
| Hurst V2 real-source bridge | From checked `LocalSourceScaleEvidence`, ordinary Lean reconstructs the exact global Mertens and squarefree prefixes and the directed little-Mertens prefix while its Q96 coordinates are active through `10^12`. It then proves the Hurst, both little-Mertens, and both strict-real squarefree inequalities. The squarefree proof checks the threshold value and slab right limit, proves the directed `6/π²` density enclosure from Mathlib's π bounds, and exports literal source-sum rewrite lemmas for all three step functions | [`HurstSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/HurstSourceSemantics.lean), its focused test, and the central axiom audit | No source-scale V2 run or `LocalSourceScaleEvidence` inhabitant is shipped. The physical row/guard evidence and downstream `claude_math` definition rewrites remain; the older global `SourceScaleEvidence` is compatibility-only and not registered |
| Helfgott (2.18) Sqrt218 CPU path | The source claim and provider-independent Abel continuation are explicit. A guarded Python producer plus independent verifier can replay the complete prime/Pratt/log/prime-power/prefix archive through `2,000,000`, while ordinary local tests use only the bound-64 KAT. Lean's strict canonical V1 JSON decoder proves the returned archive re-encodes to every exact input byte, including `kind`, closed fields, and EOF. The registered success branch requires the exact production-profile full Boolean run on an existential typed archive; ordinary Lean proves success gives generic `CertificateFacts` and then the exact Mathlib source claim. Roster soundness uses exhaustive `Nat.Prime` checks; Lucas/Pratt validation is supplemental protocol checking | [`TGComputeContracts/Sqrt218/Source.lean`](../TGComputeContracts/Sqrt218/Source.lean), [`TGComputeContracts/Sqrt218/Sound.lean`](../TGComputeContracts/Sqrt218/Sound.lean), [`Sqrt218/Operational/Wire.lean`](../SparkInterval/TernaryGoldbach/Sqrt218/Operational/Wire.lean), [`Sqrt218/Operational/Run.lean`](../SparkInterval/TernaryGoldbach/Sqrt218/Operational/Run.lean), [`RegisteredSqrt218Certificate.lean`](../SparkInterval/Execution/RegisteredSqrt218Certificate.lean), and the [Azure CPU guide](algorithms/SQRT218_AZURE_CPU_CERTIFICATE.md) | No production corpus, run, or receipt exists. The mathematical typed-archive-to-source reduction and byte decoder are axiom-free, but the decoder is not yet composed with the receipt's nested archive digest or registered V1 typed success relation. The sole trusted-run axiom still supplies the physical bytes/execution-to-typed-operational-success link. Python/native compiler, ELF/x86, and hardware refinement are also unavailable |
| Sqrt218 fixed-width V2 source and architecture boundary | Successful source-level C fixed-width reads, checked header/section layout, every record accessor and section loop, exact canonical byte reconstruction, roster and inverse power-layout passes, the thirty fixed log seeds and complete recurrence, fixed-point helpers, restoring division, each accepted event, the complete event scan, literal endpoint root search, successful reciprocal call, anchor arithmetic, pure C SHA-256, result-record encoding, and successful validate-all/bytes-wrapper control flow refine their architecture-neutral Lean counterparts. The complete source-stage capstone composes those traces into the exact V2 `completeCheck` and source claim. Its direct architecture adapter targets a pure `CSuccessfulPureEntryTrace` with no abstract native callback and does not rerun production arithmetic locally. Exact canonical execution-closure metadata binds compiler/model/ABI/ELF/entry identities to the signed statement and measured run; the external validator derives and rechecks the same fourteen-field projection. The generic five-layer x86/ELF chain is connected to the exact Sqrt218 source-trace target. Separate cloud-only VST/CompCert and launcher build lanes are source-pinned and non-authorizing; an unreviewed loader/trampoline prototype implements strict pinned ELF loading, guarded SysV entry, exit-only child isolation, return observation, and atomic result/transcript publication at source level | [`CAnchorRefinement.lean`](../SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/CAnchorRefinement.lean), [`CValidationControlFlow.lean`](../SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/CValidationControlFlow.lean), [`CPureEntryComposition.lean`](../SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/CPureEntryComposition.lean), [`ExecutionClosureIdentity.lean`](../SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/ExecutionClosureIdentity.lean), [`CX86ELFComposition.lean`](../SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/CX86ELFComposition.lean), the [launcher boundary](algorithms/SQRT218_PURE_ENTRY_LAUNCHER_BOUNDARY.md), the [compiler path](algorithms/SQRT218_VERIFIED_COMPILER_PATH.md), and the [x86 feasibility audit](algorithms/SQRT218_X86_MODEL_FEASIBILITY.md) | No launcher binary has been produced or reviewed, and the launcher source has no initializer/observer or x86 refinement. The reviewed VST specification and proof files are not yet present, so the proof lane refuses to invoke proof tools and authorizes no theorem. Constructing the concrete CompCert/object/linker/ELF/x86 refinement fields for the measured image, production data/pins/receipt, and changing the sole authority to return the low-level architecture fact remain open. Signed digest-to-metadata interpretation retains the standard SHA-256 collision/second-preimage assumption |
| CH25 psi prime-power bridge | The literal nested fold adding one Q64 log endpoint for every `1 <= k <= p.log n` equals the compact worker state, and directed prime-log bounds prove that state encloses Mathlib's `Chebyshev.psi n`. Upper guards immediately after jumps and lower guards immediately before the next jump control every point in each constant-state gap, yielding the paper-shaped real claim through `10^13` | [`PsiPrimePowerCertificate.lean`](../SparkInterval/TernaryGoldbach/PsiPrimePowerCertificate.lean), [`PsiSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/PsiSourceSemantics.lean), the registered wrapper, focused test, and central axiom audit | No full run or retained receipt exists. Physical CRlibm rows, prime-power completeness, two-pass commitments, and endpoint receipts must still be shown to construct `GapSourceScaleEvidence`; only the signed wrapper uses the trusted-run axiom |
| Finite Helfgott--Platt Goldbach bridge | Exact finite-list ladder checks imply the parity-sensitive union of translated binary-Goldbach intervals; with binary Goldbach through `4·10^18`, ordinary Lean proves every odd target through the exact source endpoint is a sum of three primes. The campaign-specific H100 materializer fixes an independently derived execution projection and retains each group's exact eight leaves. The closed CPU terminal pins the complete branch archive, all 8,512 signed child identities, and the source/build/runtime/profile closure; it matches each signed child hash vector to every raw binary and ordinary/native ladder receipt before replay | [`GoldbachSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/GoldbachSourceSemantics.lean), [`RegisteredGoldbachCertificate.lean`](../SparkInterval/Execution/RegisteredGoldbachCertificate.lean), [`GOLDBACH_HISTORICAL_AZURE_MEASURED_DAG.md`](algorithms/GOLDBACH_HISTORICAL_AZURE_MEASURED_DAG.md), focused Python tests and the central axiom audit | Neither full branch has run and no `CheckedSourceEvidence` or successful receipt exists. Production build/image/policy/key pins are unconfigured, the deferred Lean integration checks have not run in this work lane, and the semantic binding remains disabled |
| Platt zeta head through 20,000 | The checked-in named 22,491-row Q128 table with checked Hardy-Z endpoints and exact analytic slot count gives a multiplicity-preserving enumeration. The closed CPU invocation pins FLINT 3.6.0/96 bits, height/count, the distinct sentinel-inclusive and included-table digests, and only accepts `false` or `true` with `CheckedQ128HeadEvidence` for that exact table | [`PlattHeadQ128.lean`](../SparkInterval/Generated/PlattHeadQ128.lean), [`ZetaHeadSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/ZetaHeadSourceSemantics.lean), [`RegisteredZetaHeadCertificate.lean`](../SparkInterval/Execution/RegisteredZetaHeadCertificate.lean), focused tests and the central axiom audit | The full replay was exercised locally, but no analytic evidence or receipt is admitted. FLINT-to-Hardy-Z/count realization and the ordinary Lean identification with the downstream committed table remain open; no arbitrary digest-matching table is accepted, and the semantic binding remains disabled |
| Full result certificate | Every checked claimed row contains every real value represented by its input row and expression; optional theorems give row-wise and finite-sum upper bounds | Lean checker and soundness theorems in [`Certificate/Full.lean`](../SparkInterval/Certificate/Full.lean#L122) | Checks the supplied complete witness; no claim about its producer |
| Generated polynomial module | One modeled in-range thread returns an observed row representing `evalKernel`; with corresponding real inputs, the row contains the realized exact value | [`runBuildModule_inRange`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L32) and [`runBuildModule_inRange_containsReal`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L314) | Typed AST and Lean machine only; polynomial operations only |
| Formal emitted-PTX identity | A successful statement check binds the parsed canonical input batch, target-specific emitted PTX digest, canonical input/parameter/domain hashes, target-profile hash, and artifact-hash record | [`FormalPTXProgram.statementCheck_sound`](../SparkInterval/Execution/FormalPTXProgram.lean) | Artifact identities are caller-selected; no PTX-to-cubin, SASS, driver, or hardware refinement |
| Generated no-write path | Under the theorem's wrapped machine-word out-of-range premise, the modeled module returns with global memory unchanged | [`runBuildModule_outOfRange`](../SparkInterval/PTX/GeneratedKernelOutOfRangeRefinement.lean#L115) | Do not restate as an unconditional natural-index or physical-GPU theorem |
| CUDA and generated-cubin execution | Tested outputs and statuses are compared bit-for-bit with an exact rational Python oracle, with artifact audits and replay checks | Test and conformance tooling | Differential testing, not a Lean refinement theorem |
| Local run bundle | Canonical metadata and supplied artifact bytes are mutually hash-consistent | Run-bundle verifier | Host-forgeable; no execution authority |
| DGX operator signature | A separately pinned Ed25519 key signed the exact artifact-verified local record, with replay checking | Signature and run-bundle verifier | Operator provenance only; always `hardware_evidence: false`; the legacy Lean structural check is diagnostic and cannot reach the execution axiom |
| Accepted Lean run certificate | Under the sole `accepted_run_certificate_sound` axiom, an exact source-admitted `checkTrustedCompute` receipt supplies its historical return, the closed compact architecture outcome for the attestation's exact receipt hash, and temporarily the fixed `Runs` relation for every matching constructor of the compatibility registry; neither projection accepts a caller-selected machine, pin bundle, entry point, or claim | `checkTrustedCompute`, `RunCertificate.check`, `RegisteredArchitectureOutcomes`, the closed registries, and one explicit trust axiom | Per-run physical-execution trust, not a universal architecture-refinement theorem; every reviewed architecture registration is currently absent, so no physical outcome is selectable yet; the compatibility `Runs` projection remains broader until migrated; the Azure importer is a reviewed source-generation boundary; legacy DGX/H100 constructors are rejected |
| Closed registered computation | `cubicSumDivThree20000V1` fixes exact input, parsing, and an executable integer-accumulator/divide-once machine; Lean proves its operational result, agreement with the exact rational sum, and u64 safety for every cube and accumulation step without `native_decide` | [`RegisteredAlgorithm.lean`](../SparkInterval/Execution/RegisteredAlgorithm.lean) and [`RegisteredCubicSumCertificate.lean`](../SparkInterval/Execution/RegisteredCubicSumCertificate.lean) | Axiom-free algorithm and bounded-arithmetic proof only; no admitted run is supplied, and neither a signature nor these bounds prove that GPU opcodes implemented the machine |
| Closed H100 formal-PTX pilot | `h100FormalPtxConstantOneV1` fixes one canonical zero-variable input and exact output; Lean identifies the registered `sm_90` PTX with the formal emitter for that batch and proves both binary64 endpoints decode to rational one | [`RegisteredH100FormalPtxPilot.lean`](../SparkInterval/Execution/RegisteredH100FormalPtxPilot.lean) | Axiom-free source identity and result interpretation, but the physical run still uses the sole execution axiom; this is a deployment pilot, not a production zeta or Ternary-Goldbach computation, and no receipt is admitted |
| Azure SEV-SNP CPU receipt pipeline | Fresh challenge, canonical CPU bundle/output, independently appraised MAA/SEV-SNP/vTPM evidence, signed receipt, source-pinned key and receipt registry, and generated Lean structural check are implemented | Azure deployment/evidence tools, `measured_runner.py`, `trusted_compute_receipt.py`, registry/Lean generators, and `checkTrustedCompute` | The tracked receipt registry is empty. Production needs a locked-down measured image and production runner/appraiser policies, Managed HSM key attestation/review, a real Azure run, and registry review |
| Azure NCC H100 receipt pipeline | The CPU evidence above is composed with exact one-H100 target binding, NVIDIA CC evidence/EAT appraisal, device artifact binding, signed receipt, and the same source-pinned Lean path | Azure NCC deployment/evidence tools and the sole accepted trusted-compute policy | Attestation authenticates one reviewed measured run; it does not prove arbitrary user-space causality, CUDA/PTX/backend refinement, or mathematical soundness. No production H100 receipt is admitted |
| Signed zeta endpoint payload | The returned canonical full certificate parses to exact typed data; every arithmetic row, paired-singleton endpoint shape, strict sign, and adjacent family order is checked | [`SignedZetaEndpointPayload.check_sound`](../SparkInterval/Execution/SignedZetaEndpointPayload.lean) | Its pure mathematical checks remain separate from `ProducedOutcome`; endpoint enclosure of a selected Hardy-Z function remains an explicit theorem premise. This generic payload path is separate from the registered PT21 source-scale slice |
| Multiplicity-aware zeta count | Distinct zeta-zero `ncard` is at most the `ℕ∞` sum of analytic orders, so a certified multiplicity bound supplies `ZetaZeroCountUpperBound` | [`MultiplicityCount.lean`](../SparkInterval/Zeta/MultiplicityCount.lean) | A Turing/argument-principle implementation must still construct the analytic multiplicity upper bound |
| Signed finite-height zeta composition | A checked signed payload plus a proved Hardy-Z model, endpoint enclosures/domain bounds, and multiplicity upper bound yields the finite-height critical-line theorem paired with historical provenance | [`SignedZetaVerifier.lean`](../SparkInterval/Execution/SignedZetaVerifier.lean) | Conditional theorem only; no concrete analytic premises or accepted H100 instance, so no height is certified |
| Registered compact verifier composition | An accepted closed invocation plus decoded compact output and a theorem from its fixed `Runs` semantics to the claim yields the claim without a separate `ExecutionRefines` premise | [`CompactAttestedVerifier.lean`](../SparkInterval/Execution/CompactAttestedVerifier.lean) and the exact PT21 registered wrapper | The generic FormalPTX compact API remains legacy and still needs explicit refinement. PT21 is registered conditionally, but its endpoint/Hardy-Z/count evidence, materializer, full run and receipt are absent |
| H100 offline artifacts | `compute_90` PTX and `sm_90` cubins can be built and statically inspected without an H100 | Offline build and audit scripts | No H100 query, execution, result, or attestation |
| H100 hardware provenance | Positive Azure evidence collection, independent-appraisal adaptation, signed receipt, and source-pinned Lean import are implemented | Fail-closed Azure NCC trusted-compute policy; only a source-admitted receipt can use the sole execution axiom | No production appraiser/key/run/receipt is supplied and the tracked registry is empty; the legacy H100 structure is diagnostic only |
| Real-integer zeta tutorial | Exact host recomputation plus an integral-test tail encloses `zeta(s)` for a recorded supported integer `s > 1` | CUDA tutorial verifier and hash-bound [algorithm](algorithms/REAL_ZETA_POC.md) | Positive real values only; not a Lean theorem about `riemannZeta` or zeros |

Merkle and application-specific compressed Lean result certificates are not
implemented. The finite-sum theorem still checks the complete full certificate;
it is an aggregate conclusion, not a compressed witness.

## Full result certificates

[`FullCertificate.check_sound`](../SparkInterval/Certificate/Full.lean#L122)
proves containment for arbitrary real selections from every input and constant
interval, not merely for rational samples. The same checker supports the
row-bound theorem
[`checkUpperBound_sound`](../SparkInterval/Certificate/Full.lean#L191) and the
finite aggregate theorem
[`checkSumUpperBound_sound`](../SparkInterval/Certificate/Full.lean#L286).

The serialized parser enforces canonical JSON, exact fields and limits,
binary64 spelling, row relationships, and nested SHA-256 bindings. Generic
serialized implications are
[`impliesTheorem`](../SparkInterval/Certificate/Format.lean#L367) and
[`impliesSumTheorem`](../SparkInterval/Certificate/Format.lean#L377).

Concrete generated proofs have two dependency profiles:

- default `kernel` mode uses `decide_cbv` for the materialized typed-data
  checks, while the exact serialized parser/hash equality uses `native_decide`;
- explicit `native` mode also uses `native_decide` for the typed-data checks.

Thus the default direct typed-data theorem can be used without
`native_decide`, but the current generated theorem that binds the witness to
the exact JSON bytes cannot. This is a proof-reduction distinction, not GPU
execution evidence. See [Verifier guide](VERIFYING.md#native_decide-distinction)
and [Trust model](TRUST_MODEL.md#lean-proof-dependencies).

The Python reference checker uses the same canonical wire format but, by
itself, produces external recomputation evidence rather than a Lean theorem.
The Python generator prechecks a certificate before producing Lean source;
the mathematical conclusion comes from the Lean checker, not that precheck.

## Generated typed-machine theorem

The generated compiler accepts polynomial expressions built from constants,
variables, negation, addition, subtraction, multiplication, and natural powers.
Lean proves:

- status-aware `PolynomialExpr.evalKernel` containment;
- exact structural lowering and exact source-derived opcode order;
- recursive execution of the actual `compileExpr` output;
- exact generated prologue, expression, normal-output,
  conservative-whole-output, and return segments;
- input/output layout properties and the public output-row representation;
- a complete one-thread `Machine.run` result for the modeled module.

`runBuildModule_inRange` requires its stated safe-thread, safe-layout,
encoded-memory, selected-row, environment, and successful-evaluation
hypotheses. Its uniform fuel is the compiled expression instruction count plus
47. `runBuildModule_inRange_containsReal` additionally requires corresponding
real and interval environments and a source-expression realization.

The conclusion stops at the typed AST and Lean machine. Deterministic emission
shows that successful emission is the rendering of the same AST, but there is
no operational parser/refinement theorem from emitted PTX text back to that
machine. The pinned NVIDIA layer proves agreement only for finite-operand
directed `add/sub/mul` and non-NaN `min/max` steps; its clause table does not
supply semantics for the rest of the emitted program. There is also no proof
that `ptxas`, SASS, the CUDA driver, scheduling, or physical hardware
implements the model. The division-capable CUDA expression frontend is
outside this theorem.

## Execution provenance

An unsigned DGX bundle establishes only reproducibility and integrity relative
to supplied bytes. A detached operator signature authenticates an endorsement,
not the truth of the endorsed record. The legacy
`checkDGXOperatorSignature` API remains a structural diagnostic, but
`RunCertificate.check` unconditionally rejects `.dgxOperatorSignature` and
[`dgx_operator_signature_not_admitted`](../SparkInterval/Execution/Trusted/DGXOperatorSignature.lean)
proves the fail-closed relationship. A DGX signature therefore cannot reach
[`accepted_run_certificate_sound`](../SparkInterval/Execution/Trusted/RunCertificate.lean)
or establish a physical-run fact. The distinct Azure trusted-compute path below
uses source-pinned receipts instead.

`SignedResultCertificate.outcomeCheck_sound` composes source-admitted
trusted-compute acceptance with ordinary Lean checks for exact result-text
equality and its SHA-256 digest. Its `ProducedOutcome` contains the historical
return, the compact architecture projection for the attestation's exact
receipt hash, and the temporary fail-closed application-level registered
projection. It proves that the particular certified run returned the exact
supplied result-certificate bytes.
The pinned-identity variant
`outcomeCheckForAlgorithm_sound` additionally proves literal expected
algorithm ID/hash equalities.

The preferred formal-semantics handoff is
`outcomeCheckForRegisteredInvocation_sound`. A closed
`RegisteredInvocation.statementCheck` binds the exact algorithm ID and formal
definition digest together with canonical input, parameter, and domain
digests and checks that the signed result belongs to the constructor's
canonical result language; the sole axiom then supplies that invocation's
library-defined `Runs` relation. `resultAllowed_of_runs` proves axiom-free that
this guard admits every legitimate execution result.
`accepted_registered_run_sound` is merely the corresponding projection of the
sole axiom.

The registry now includes the tutorial and deployment pilot plus closed
source-shaped ternary-Goldbach invocations, including the exact PT21 finite-RH
campaign. For the tutorial, `cubicSumDivThree20000V1.Runs` uses the executable
`cubicSumDivThreeMachine`, which accumulates integer cubes and divides once.
Ordinary Lean theorems prove the exact machine result, its equality to the
rational specification `13334666700000000`, and u64 no-overflow for every cube
and accumulator step, without `native_decide` or a materialized row
certificate. This algorithm-soundness and bounded-arithmetic layer is
axiom-free. It does not prove GPU opcode execution. The tracked trusted-compute
receipt registry contains no matching accepted run, so the signed paths remain
an end-to-end theorem interface rather than a completed signed-wire
demonstration.

The pinned-identity signed-result wrappers can additionally prove literal
equality between the statement's algorithm ID/hash and values pinned by an
application theorem. They do not prove that the pinned digest is a formal PTX
emission, that a cubin was compiled from it, or that the executable refines the
formal algorithm.

For the typed generated-PTX path, the separate `FormalPTXProgram` checker does
derive the algorithm digest from validated target-specific emission of the
exact batch. It also reparses and binds the canonical input and compares the
canonical input/parameter/domain hashes, target-profile hash, and complete
artifact-hash record. Its soundness theorem closes formal-AST-to-emitted-PTX
identity for that path, but the artifact fields remain identities rather than
a proof that `ptxas` produced the named cubin from those PTX bytes.

The legacy `checkH100Attestation` entry point is a structural diagnostic.
`RunCertificate.check` unconditionally rejects `.h100Hardware`, and
[`h100_attestation_not_admitted`](../SparkInterval/Execution/Trusted/H100Attestation.lean)
proves that even a positive diagnostic cannot reach the sole axiom. The Azure
NCC path instead collects and independently appraises genuine H100 evidence,
signs a compact trusted-compute receipt, source-admits it, and generates a Lean
consumer. The tracked source registry is empty, so no genuine H100 evidence
currently reaches the premise. A source-admitted receipt would expose fixed
`Runs` semantics only for a matching closed invocation; an application must
still provide that algorithm/invocation constructor, parse the result, and
prove the ordinary algorithm-soundness theorem.

Production use of this path also trusts the pinned Azure and NVIDIA
appraisers/policies, certificate and revocation roots, TCB decisions, measured
runner, HSM key custody and attestation, and review of the generated registry
entry. Platform attestation and a TPM result-binding extension do not prove
that arbitrary unmeasured user-space code caused the output.

Neither an accepted historical outcome, a per-run registered `Runs` fact, nor
literal executable-identity pins prove the universal claim that every future
physical run of that executable produces the same result. The current formal
artifact binding from emitted PTX to the separately named cubin,
`ptxas`/SASS/driver/hardware refinement, and such a universal theorem remain
open.

## Riemann-zeta scope

The included tutorial encloses positive real values from the Dirichlet series
for supported integer `s > 1`. It uses a division-capable CUDA runner and an
exact Python verifier, so it is neither an instance of the polynomial
typed-machine theorem nor a Lean connection to Mathlib's `riemannZeta`.

The repository now has a finite-height proof skeleton with no zeta-specific
axiom rather than an instantiated numerical verification. It proves
complex-rectangle polynomial containment, an exact-rational endpoint checker
whose family-order comparisons are linear and adjacent, monolithic and chunked
distinct-root lower bounds, a formal Hardy-Z zero-equivalence contract,
compact-region zeta finiteness, and the final theorem that matching
critical-line and total counts put every zero in the rectangle on the line.
`HardyZModel.verifyEndpointFamily` composes the executable family check with
proved enclosure, domain, Hardy-Z, and total-count premises; it does not create
those analytic premises.

The canonical signed-payload path now reparses the complete returned full
certificate, checks every arithmetic row, enforces exactly two singleton finite
endpoint rows per bracket, checks strict signs plus adjacent ordering, and
cross-binds the parser-recomputed embedded batch digest to the accepted
statement and exact formal-program canonical input. Its
final `verifyFiniteHeight` theorem pairs historical provenance with the zeta
conclusion. Its `ProducedOutcome` crosses the sole run-certificate axiom, while
the mathematics comes independently from those pure checks together with
explicit Hardy-Z, endpoint-enclosure, domain, and analytic multiplicity-bound
arguments. The separate PT21 finite-RH invocation is registered conditionally;
its required source evidence and successful receipt do not yet exist.

The high-bound pure path also checks independent endpoint chunks with a
resumable previous-boundary state, proves their spans globally ordered and
contiguous, sums their local counts, constructs `ChunkCertificate`, and reaches
the same finite-height theorem. For an even evaluator, the positive-only path
reflects `n` positive brackets into a `2*n` symmetric family without another
set of endpoint arithmetic rows. These are theorem-level `List` inputs, not yet
a proved byte-streaming runtime.

The distinct-versus-multiplicity mismatch is no longer an open logical gap:
Lean proves that distinct zero count is at most the sum of analytic orders and
converts a `ZetaMultiplicityCountUpperBound` into the verifier's distinct-count
upper bound without assuming simple zeros. What remains missing is a checked
Turing/Riemann--von Mangoldt/argument-principle construction of that analytic
upper-bound premise.

No current theorem discharges the Hardy-Z contract, endpoint realization, or
analytic multiplicity bound from numerical zeta data. A usable high-bound
verifier still needs certified theta/log/trigonometric range reduction, a
rigorous Riemann-Siegel formula and remainder, adaptive precision, a streaming
chunk parser, and a checked Turing-method or argument-principle total count.
See the
[high-bound verifier status](algorithms/ZETA_ZERO_VERIFIER.md).
