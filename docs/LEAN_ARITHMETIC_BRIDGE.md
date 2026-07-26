# Lean arithmetic bridge for accelerated campaigns

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

The intended production boundary is not “the H100 says the theorem is true.”
An accelerator discovers or checks finite data; Lean fixes the arithmetic
meaning of that data and proves the application theorem.  The bridge is
accepted only when the following chain is present.

1. **Source-shaped specification.** A Lean proposition names the exact finite
   domain, endpoint convention, multiplicities, parameters, and claimed bound.
2. **Exact wire decoding.** Every integer or binary64 word used by the checker
   decodes to an exact Lean value. NaNs, infinities, trailing bytes, duplicate
   blocks, gaps, and noncanonical encodings fail closed.
3. **Small Boolean checker.** The certificate cannot supply a proposition. It
   supplies data to a repository-defined checker.
4. **Checker soundness.** An ordinary Lean theorem proves `check c = true ->
   Semantics c`. This theorem must not depend on `native_decide` or the
   trusted-compute axiom.
5. **Coverage and composition.** Separate theorems prove that all checked
   chunks form the requested half-open range and that their exact states fold
   to the application quantity.
6. **Application theorem.** A theorem derives the source atom, or the explicitly
   conditional analytic result, from the checked arithmetic semantics.
7. **Physical tie-in.** Either Lean checks the complete certificate directly,
   or a constructor in the closed `RegisteredInvocation` registry fixes the
   complete checker semantics for one compact measured run. Only the latter
   step may depend on `accepted_run_certificate_sound`.
8. **Audit.** A focused test prints the axioms of the checker-soundness,
   application, and accepted-run composition theorems.

This separation permits three honest deployment modes:

| Mode | What Lean checks | Trust boundary |
| --- | --- | --- |
| Complete certificate | Exact wire data, every arithmetic witness, coverage, and final predicate | Lean's ordinary base trio only |
| Compact measured checker | Small returned summary plus a proved theorem from the closed invocation's `Runs` semantics to the mathematical claim | Base trio plus the one per-run `accepted_run_certificate_sound` axiom |
| Diagnostic GPU output | KATs, independent Arb/MPFR replay, hashes, and benchmarks | Testing evidence only; it cannot discharge an atom |

## Implemented arithmetic pieces

- [`ComplexDisk.lean`](../SparkInterval/Certified/ComplexDisk.lean) decodes the
  three binary64 disk words to exact rationals. Its raw addition and
  multiplication checkers verify squared centre-error and norm bounds using
  rational arithmetic; the soundness theorems prove enclosure of the true
  complex sum or product. These are the semantic error decompositions used by
  the CUDA `diskAdd` and `diskMul` helpers, without asserting their execution.
- [`ComplexDiskWire.lean`](../SparkInterval/Certified/ComplexDiskWire.lean)
  gives the standalone multiplication witness a strict 96-byte
  little-endian parser. It proves exact length, rejects trailing data and the
  noncanonical negative-zero spelling, then composes parsing, finite-word
  decoding, and multiplication containment. It is a proved primitive, not a
  parser for the complete `TGDBSQP3`/`TGDBSQB3`/`TGDBSQO3` protocol.
- [`FactoredSmallQSeed.lean`](../SparkInterval/Dirichlet/FactoredSmallQSeed.lean)
  proves the factored parity/epsilon product and the exact Gaussian recurrence
  `z = w^((n+1)^2)`, `ratio = w^(2(n+1)+1)`. The disk specialization consumes
  the exact multiplication checker above.
- [`FactoredSmallQRawTrace.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawTrace.lean)
  decodes every already-selected binary64 word in a linked recurrence trace,
  preserves the exact row count, and requires exactly `T - 1` updates for a
  nonempty `T`-term source request. A nontrivial `w = i` test detects exponent
  and index regressions.
- [`FactoredSmallQCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQCampaign.lean)
  takes the modulus, ordered character roster, and transform length from the
  application rather than from the untrusted certificate. Its central checked
  equation says that accepted keys are exactly the row-major Cartesian product
  of that roster and `List.range transformLength`; batch ordinals, offsets, and
  per-batch products are checked as well.
- [`FactoredSmallQRawCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCampaign.lean)
  composes those two layers. Every requested `(character, frequency)` cell is
  tied to an actual raw payload, the application-owned term count, an exact
  rational decoding, and the proved Gaussian recurrence state.
- [`FactoredSmallQGaussianSum.lean`](../SparkInterval/Dirichlet/FactoredSmallQGaussianSum.lean)
  and its [raw wrapper](../SparkInterval/Dirichlet/FactoredSmallQRawGaussianSum.lean)
  check exact one-based ordinals, every character-times-power product,
  optional odd scaling, every linked running-sum addition, and the recurrence
  advance between rows. The output encloses the exact finite Gaussian sum of
  exactly the application-owned number of terms.
- [`FactoredSmallQRawPostprocess.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawPostprocess.lean)
  checks the raw prefactor product, frequency-sign conjugation, and decoded
  nonnegative analytic-tail inflation without detaching them from the raw
  finite-sum trace. The [campaign composition](../SparkInterval/Dirichlet/FactoredSmallQRawPostprocessCampaign.lean)
  fixes truncation, parity, and sign per source-owned cell and proves the final
  disk enclosure conditional on explicitly named base, character, prefactor,
  and tail premises.
- [`FactoredSmallQDFT.lean`](../SparkInterval/Dirichlet/FactoredSmallQDFT.lean)
  checks the positive-sign radix-2 butterfly network: stage, group, offset,
  indices, operands, twiddles, plus/minus outputs, and every state link. It
  proves containment for the complete staged algorithm. The companion
  [`FactoredSmallQDFTCorrectness.lean`](../SparkInterval/Dirichlet/FactoredSmallQDFTCorrectness.lean)
  proves a block-transform invariant, all schedule/index arithmetic, root
  identities, bit-reversal involution, and the generic theorem equating every
  such staged transform to the direct positive-sign DFT. `Radix2CorrectFor`
  is therefore discharged for every source, not an analytic assumption.
- [`FactoredSmallQRawDFT.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawDFT.lean)
  replaces the typed function tables by finite, canonically ordered raw
  binary64 lists. Its fail-closed checker enforces independent bounds on
  transform length, line length, and total records before decoding; checks the
  complete input, twiddle, butterfly, and final-output shapes; rejects negative
  radii even for the stage-free length-one case; and binds each literal output
  word to the final state derived from the checked trace. The
  [raw composition theorem](../SparkInterval/Dirichlet/FactoredSmallQRawDFTComposition.lean)
  connects those words to the exact postprocessed source line through the
  explicit natural-order and bit-reversal equations. This is an exact finite
  Lean data format, not yet a parser for the v3 byte stream or a claim that a
  physical producer emitted the trace.
- [`FactoredSmallQDFTComposition.lean`](../SparkInterval/Dirichlet/FactoredSmallQDFTComposition.lean)
  states the two intervening equations explicitly: every raw final cell
  decodes to a natural-order disk, and every transform input is the named
  bit-reversal of that table. From those exact links it derives the DFT input
  invariant and composes the complete per-cell theorem through all checked
  radix-2 stages.
- [`FactoredSmallQModulusCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQModulusCampaign.lean)
  checks the outer ordered list of source-owned modulus specifications and
  proves two-level lookup down to every requested cell. A separate source
  theorem must still show that the supplied ordered rosters are exactly all
  primitive characters required by the paper.
- [`FactoredSmallQRawPostprocessModulusCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawPostprocessModulusCampaign.lean)
  specializes that outer checker to the full raw postprocessing payload. Its
  application theorem starts with an exact source modulus, character, and
  frequency and returns the actual raw cell plus containment of the complete
  finite Gaussian sum, prefactor, sign branch, and tail. The analytic inputs
  use the same ordered `Forall₂` alignment as the modulus certificates, so a
  premise for one modulus cannot be substituted for another.
- [`FactoredSmallQCompletedSign.lean`](../SparkInterval/Dirichlet/FactoredSmallQCompletedSign.lean)
  checks the post-DFT equation
  `(F * (2*pi/b) + timeTail) * exp(-pi*eta*t/4)` in that exact order using
  disk multiplication and radius inflation. For a completed value supplied
  with the explicit analytic reality premise, the rational inequality
  `radius < re` or `re < -radius` proves its strict sign. The corresponding
  [source-sample campaign](../SparkInterval/Dirichlet/FactoredSmallQCompletedSignCampaign.lean)
  names `sampleCount` independently, checks `sampleCount <= fullDFTLength`,
  checks the exact roster product with `[0, sampleCount)`, and proves that
  every retained sample has its named sign and lies in the full DFT domain.
  The completed-sign checker also requires the scale and untilt factor disks
  themselves to certify strict positivity.
- [`FactoredSmallQRawCompletedSign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSign.lean)
  is the fixed-size raw wrapper for those post-DFT operations. It decodes every
  binary64 word, literally attaches the first multiplication operand to the
  supplied Fourier word, and accepts the producer's signed convention
  `-1 = negative`, `+1 = positive`; zero and all other codes fail. The source
  theorem retains exact factor, tail-bound, final-output, and sign decodes
  while deriving the strict sign from the same typed arithmetic theorem.
- [`FactoredSmallQRawCompletedSignPayloadCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSignPayloadCampaign.lean)
  removes the detached Fourier-table boundary for a complete source-sample
  campaign. Its payload checker indexes the accepted raw transform at the
  exact character/sample key and passes that literal word directly to the raw
  sign checker; a missing output or different word fails. The application
  theorem composes the raw postprocess/DFT proof and generic direct-DFT
  identity with raw scale/tail/untilt arithmetic and returns the same word,
  exact source value, guards, and strict sign.
- [`FactoredSmallQRawCompletedSignCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSignCampaign.lean)
  is the narrow end-to-end arithmetic join. Its Boolean bridge checks modulus,
  exact ordered roster, full length `2^logLength`, retained
  `sampleCount <= fullDFTLength`, and every retained Fourier-disk equality.
  The application theorem then returns the literal raw DFT output word, its
  exact decoded disk, containment of the exact direct positive DFT, and the
  strict sign of the completed source value. The source factor definitions
  are named in Lean as `sourceScale b = 2*pi/b` and
  `sourceUntilt eta t = exp(-pi*eta*t/4)`. Header-wide scalar parameters
  prevent per-sample drift; time is definitionally `sample/a`, and `GridValid`
  retains `0<a`, `0<b`, `-1<eta<1`, and `b=2^logLength/a`. The exact production
  constant is separately named `bookerA=64/5`. Factor containment, the
  complex-norm analytic tail, and functional-equation reality premises remain
  visible.
- [`FactoredSmallQRawCompletedSignModulusCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSignModulusCampaign.lean)
  lifts that endpoint over one nonempty, source-owned ordered list of distinct
  moduli. Each complete finite bundle and each source header is aligned by the
  same `List.Forall₂`, so raw traces, analytic premises, and sign data cannot
  be reused for a different modulus. The typed DFT certificate is canonically
  decoded from the literal raw certificate; the checker proves its fallback is
  unreachable. The outer source theorem returns the raw word, exact direct-DFT
  enclosure, `a`/`b`/`eta` guards and grid equation, and strict source-formula
  sign for every requested modulus, character, and retained sample.
- [`FactoredSmallQRawCompletedSignPayloadModulusCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawCompletedSignPayloadModulusCampaign.lean)
  is the fully raw all-modulus variant. Each modulus bundle contains its own
  raw DFT certificates and raw completed-sign campaign; the finite checker
  passes the exact indexed DFT word into the corresponding raw sign payload.
  Source specifications, bundles, source headers, and analytic premises are
  related by exact ordered relations, so reordering, omission, duplicate
  modulus identifiers, a missing word, or a detached spelling fails closed.
- [`FactoredSmallQZeroBracket.lean`](../SparkInterval/Dirichlet/FactoredSmallQZeroBracket.lean)
  projects the final completed-value disks to exact rational real intervals
  and checks pairs on one fixed character and rational sampling grid. It
  requires positive `a`, exact `time = sample/a`, increasing samples and
  times, opposite certified signs, and globally separated brackets. Explicit
  disk containment, reality, and evaluator equalities then construct the
  existing `ZeroCertificate`; certificate metadata alone never supplies the
  analytic evaluator link.
- [`FactoredSmallQRawZeroBracketCampaign.lean`](../SparkInterval/Dirichlet/FactoredSmallQRawZeroBracketCampaign.lean)
  closes the finite join to those brackets. A typed sign certificate must be
  the deterministic decode of an actual raw campaign cell, and its endpoint
  checker uses the disk decoded from the literal raw DFT word at the same
  source-owned key. The theorem also proves that accepted cells lie in the
  retained source domain and gives exact rational/real `sample/a` alignment,
  including Booker's `a=64/5`. Detached bit patterns, including a signed-zero
  alias with the same rational decode, fail literal attachment. Its semantic
  corollary then needs only the named `SourceRealizes` propositions for the
  two endpoints to prove that the checked rational bracket encloses a named
  evaluator.
- [`FactoredSmallQSourceRealization.lean`](../SparkInterval/Dirichlet/FactoredSmallQSourceRealization.lean)
  turns the former informal numeric-character boundary into explicit Lean
  contracts. A supplied noduplicated roster bijects opaque source identifiers
  with primitive Dirichlet characters; every in-domain character row is fixed
  to `[chi(1), ..., chi(termCount)]` with the parity of that same character;
  and one complex equation identifies the exact factored/direct-DFT source
  expression with one named real evaluator on Booker's exact `a=64/5` grid.
  The requested-cell capstone composes those contracts with the literal raw
  word proof to expose the character row, parity, and `EvaluatorLink` at the
  same deterministically decoded sign cell. It does not assert a Conrey
  enumeration or construct any of these analytic contracts.
- [`FactoredSmallQGRHBridge.lean`](../SparkInterval/Dirichlet/FactoredSmallQGRHBridge.lean)
  is the proposition-level capstone for one character and one modulus. It
  sends a checked completed-sign bracket family directly through the proved
  Dirichlet Hardy-model verifier. Character nontriviality, the Hardy
  representation, every endpoint evaluator link, enclosing height bounds,
  and the complete L-zero upper count remain visible theorem arguments. A
  per-modulus corollary requires those same inputs for every primitive
  character.
- [`FactoredSmallQRosterGRHBridge.lean`](../SparkInterval/Dirichlet/FactoredSmallQRosterGRHBridge.lean)
  closes the identifier-indexing join. Exact primitive-roster completeness
  selects the unique source identifier for an arbitrary primitive character;
  the explicitly checked family-header equality then rewrites the
  source-indexed evaluator into the Hardy model for that character. Family
  checks, endpoint links, height bounds, and the total-zero upper count all
  remain separate arguments.
- [`PlattTheorem71Contract.lean`](../SparkInterval/Dirichlet/PlattTheorem71Contract.lean)
  states the exact even/odd conductor-height proposition consumed by the
  ternary-Goldbach project and proves it from symmetric
  `GRHVerifiedForModulus` results for every source conductor and primitive
  character. This is the final theorem-shaped handoff: finite roster
  realization, sign-change brackets, the Hardy model, and the Turing/argument-
  principle upper count must still construct its explicit hypotheses. The
  zero-bracket module now supplies the exact arithmetic-to-bracket handoff;
  selecting the source-wide pairs, proving their completed-L realization,
  and proving completeness remain separate obligations.
  [`RegisteredPlattTheorem71Certificate.lean`](../SparkInterval/Execution/RegisteredPlattTheorem71Certificate.lean)
  closes the conditional receipt endpoint: its CPU/SEV-SNP invocation pins
  conductors `1..400000`, both source height formulas, the exact
  29,565,923,837-character `q=2..400000` count, and the stronger q=1 zeta
  source. Result `true` requires `Nonempty PlattTheorem71SourceEvidence`, with
  the universal even and odd branches intact; `false` is the only
  evidence-free result and proves nothing. No materializer, completed source
  run, or successful receipt is supplied, and the Azure semantic binding
  remains disabled and null.
  The [handoff note](algorithms/PLATT_THEOREM_71_LEAN_HANDOFF.md) gives the
  one-to-one downstream symbol mapping and the eventual axiom-retirement
  procedure.
- [`A7BoundarySourceSemantics.lean`](../SparkInterval/TernaryGoldbach/A7BoundarySourceSemantics.lean)
  fixes the exact CH25 Lemma A.7 rectangle frontier, Mathlib `riemannZeta`
  logarithmic-derivative expression and `349/250` target. It proves that a
  finite rational leaf cover plus output-box containment and exact squared-
  norm guards imply the source claim. The only analytic refinement is the
  explicit `BoundaryEvidence.realizes` field connecting retained FLINT/Arb
  boxes to Mathlib's function. A closed CPU/SEV-SNP invocation and signed
  success wrapper add only the existing trusted-run axiom; no realization,
  measured terminal materializer, successful receipt or enabled semantic
  binding is claimed.
  [`A7BoundaryWire.lean`](../SparkInterval/TernaryGoldbach/A7BoundaryWire.lean)
  now supplies the previously missing total byte boundary for the finite
  seven-field transcript: exact length, source/leaf/payload/full-wire
  identities, bounded fixed-width decoding, gap-free edge coverage, and
  exact rational guards. Its ordinary soundness stops at the finite
  certificate. The theorem reaching the source claim still takes
  `AnalyticRealization` explicitly, so the wire does not silently identify
  FLINT/Arb with Mathlib's analytic functions.
- [`ZetaHeadSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/ZetaHeadSourceSemantics.lean)
  gives the 22,491-cell Platt head a literal Q128 table format and a
  kernel-computed canonical-row commitment. The exact generated table is
  checked in as `SparkInterval.Generated.PlattHeadQ128.table`; registered
  success is evidence for that named table, not an arbitrary digest-matching
  table. Checked strict Hardy-Z brackets
  and the exact analytic multiplicity-slot count imply a bijective,
  multiplicity-preserving zero enumeration without assuming simplicity. The
  closed CPU/SEV-SNP invocation pins FLINT 3.6.0/96 bits, height 20,000 and
  count 22,491, plus separate 22,492-row sentinel-inclusive and 22,491-row
  included-table digests. Its signed wrapper is conditional: the literal
  table, analytic realization, accepted receipt and downstream exact-table
  identification remain absent, so the semantic binding stays disabled.
- [`ZetaRHSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/ZetaRHSourceSemantics.lean)
  fixes the exact Platt--Trudgian height and proves that the generic chunked
  zeta verifier implies the literal positive-height open-strip finite-RH
  source claim. The closed CPU/SEV-SNP invocation separately pins campaign ID,
  `N(T)=12363153437138`, FLINT 3.6.0 commit and shard geometry; its signed
  success wrapper adds only the existing trusted-run axiom. Endpoint/Hardy-Z
  realization, the analytic count realization, a source-evidence materializer,
  the multi-year full run and an attested receipt remain absent, so the Azure
  semantic binding stays disabled. Its exact invocation, conditional theorem,
  and terminal result path are staged for review but provide no authority.
- [`GoldbachSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/GoldbachSourceSemantics.lean)
  fixes the exact binary endpoint and Helfgott--Platt source endpoint, checks
  finite prime-ladder arithmetic, and proves the parity-sensitive union of
  translated binary-Goldbach intervals. `sourceClaim_of_checked_evidence`
  derives the literal three-prime source theorem from a binary premise and the
  checked ladder. A closed Azure CPU finalizer pins the H100 binary and CPU
  ladder campaign/source-artifact identities and adds only the existing
  trusted-run axiom on success. Both source-scale branches, the evidence
  materializer, successful receipt, and a separately auditable transitive link
  from that CPU receipt to both branch receipt/artifact chains remain absent;
  the semantic binding stays disabled and null.
- [`HurstAffineCertificate.lean`](../SparkInterval/TernaryGoldbach/HurstAffineCertificate.lean)
  checks exact four-coordinate block states, guard maxima, adjacency, and
  prefix composition. Its production replay interface separates primitive
  row deltas from local guard decisions; literal source-range completion and
  a zero root remain separately named physical premises. The older interface
  that accepted one combined global row predicate is compatibility-only.
- [`HurstSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/HurstSourceSemantics.lean)
  fixes the exact V2 row predicate and proves its five source-shaped real
  bounds: Hurst, two little-Mertens bounds, and two squarefree constants.  The
  squarefree theorem uses inclusive threshold values plus slab right limits;
  its `6/π²` enclosure is proved from Mathlib's 20-decimal π bounds.
  `checked_full_source_claims_of_local` derives the global Mertens and
  squarefree prefixes along the checked chain and the little-Mertens prefix
  exactly while its Q96 coordinates are active through `10^12`; the worker
  freezes them afterward. Only physical full-range
  `LocalSourceScaleEvidence` and downstream definition identification remain
  outside this arithmetic bridge. `RealSourceClaims` is the compact capstone,
  and the V2 registered-run theorem returns it directly rather than exposing
  machine predicates to the consumer. Three proved `*_eq_sourceSum`
  normal-form lemmas already expose exactly the `Iic`/`Icc`/`range` sums used
  by the consumer, so that final identification is a short rewrite, not a
  trusted semantic assertion.
- [`R2StarSourceSemantics.lean`](../SparkInterval/TernaryGoldbach/R2StarSourceSemantics.lean)
  copies the exact Ramaré--Zúñiga coefficient and summatory function, checks
  compact gap-free Q32 chunk/state chaining, proves directed interval-prefix
  composition, discharges the squared-envelope arithmetic, and performs the
  real-floor slab lift to the literal Lemma 6.2 source claim. Its
  `ExternalChunkRealization.coefficientRealizes` field deliberately exposes
  the remaining C++ factor-support recurrence to Mathlib von-Mangoldt
  convolution refinement. The registered H100 success wrapper uses only the
  existing trusted-run axiom; no source-scale success receipt is claimed and
  the Azure semantic binding remains disabled.
- [`Prop1224SourceSemantics.lean`](../SparkInterval/TernaryGoldbach/Prop1224SourceSemantics.lean)
  copies the exact Helfgott Proposition 12.2.4 finite-computation proposition,
  including the infinite-prime definition of `c_E`, the finite `G_q` sum, the
  exact `c(c_+)` expression, both window guards and the strict cited ranges. It
  proves ordinary-Lean coverage of all 3,389,047,618 source ranks and reduces a
  checked gap-free shard chain to the literal source claim. The only remaining
  physical refinement is visibly named
  `ExternalShardRealization.mpfrGmpRows`: retained outward MPFR/GMP decisions
  must construct that exact row proposition. The registered CPU/SEV-SNP
  success wrapper adds only the existing trusted-run axiom; no successful run
  or enabled Azure semantic binding is claimed.
- [`FusedLargeQAddbackSlice.lean`](../SparkInterval/SASS/FusedLargeQAddbackSlice.lean)
  validates one decoded SM90 directed-add slice and binds its source, cubin,
  disassembly, and manifest hashes. It is deliberately a slice theorem, not a
  whole-kernel refinement claim.
- [`Sqrt218/CPUChecker/V2Adapter.lean`](../SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/V2Adapter.lean)
  gives the compact CPU design for Helfgott (2.18). A future measured worker
  will check the full fixed-width archive and emit one 120-byte result
  containing the immutable input length, input SHA-256, terminal arithmetic
  state, and endpoint slack. The intended ordinary Lean receipt path will
  consume only that compact signed result and reviewed registry pins: it will
  neither read nor hash the production archive nor replay the finite scan.
  The large archive will be needed only inside the measured cloud job or for
  a separately requested retention audit. The C/Lean checker, result wire
  format, and compact receipt tooling exist; the Azure job, production
  certificate integration, reviewed pins, and receipt do not. The remaining
  arithmetic is no longer a loop-replay obligation: ordinary Lean proves
  successful fixed-width event steps, the complete event-loop induction, and
  successful endpoint-slack evaluation refine the generic kernel event fold
  and `anchorOK`. `CPrimitives.lean` and
  `CArithmeticRefinement.lean` additionally prove the literal source-level C
  word operations and helper-call compositions refine those
  architecture-neutral operations. The native two-limb helpers and restoring
  divider now use a CompCert-friendly flat scalar/output-pointer ABI at every
  core call, and `tg_sq218_verify_snapshot_v2` exposes a flat result-record
  entry without changing the production wrapper. The remaining static
  obligation is the parser/helper/outer-loop connection, proof and
  POSIX-free isolation of that entry, then compiler/ABI/ELF/ISA refinement
  into the already proved Lean V2 checker semantics; it is not a source-scale
  Lean evaluation.

Focused tests show the pure arithmetic theorems use only the ordinary Lean
base trio (`propext`, `Classical.choice`, and `Quot.sound`; the finite Hurst
checker needs only `propext`). The registered-run composition additionally
shows exactly the existing `accepted_run_certificate_sound` boundary.

## Remaining production work

The small-`q` path still needs a canonical little-endian parser or deterministic
Lean-literal generator for the whole certificate sidecar and a practical
producer for the complete bounded raw DFT trace now checked in Lean, plus the
physical link to that trace. The raw-DFT-to-completed-sign equality and
arithmetic are proved, but the streamed v3 bytes do not yet construct that
Lean bridge certificate. Analytic containment of exponential bases, character
values, prefactors, tails, and twiddle roots remains explicit. The exact
primitive-roster, character-row/parity, and source/evaluator propositions now
have named Lean contracts and a proved composition path, but no production
data inhabits them. The application must prove those contracts for the actual
source, identify each named evaluator with its completed-L Hardy model, select
the complete bracket families (including upsampling and exceptions), cover
conjugates and the separate `q=1` zeta case, and prove the Turing or
argument-principle total count. Physical CPU/GPU execution refinement is
separate. The current theorems do not silently assert any missing edge.

The complete butterfly trace is a reference proof format, not a credible
source-scale transport format: one length-`N=2^L` line contains exactly
`L*N/2` butterfly rows. At `L=21` that is `22,020,096` rows per character.
Production should therefore use either a materially more compact arithmetic
certificate with its own Lean soundness theorem, or a deterministic streaming
checker inside the measured image with the precise closed `Runs` semantics
described below. Simply dropping the trace and retaining its hash would lose
the arithmetic proof.

For source-scale certificates that are too large for a practical Lean build,
the preferred compact design is a deterministic CPU checker inside the
measured image. Its closed `Runs` relation must say that the checker parsed the
fixed campaign plan, replayed every rooted chunk, checked its arithmetic and
coverage, and returned the fixed compact summary. The ordinary
algorithm-soundness theorem then turns that semantics into mathematics. A hash
or an attestation quote alone is never the semantics.

The closed registry now also proves
`RegisteredInvocation.runs_satisfiable : ∀ i, ∃ output, i.Runs output`.
This is a maintenance guard, not execution evidence. If a future invocation's
formal `Runs` relation were impossible, a source-admitted receipt would expose
that impossible proposition through the trusted-run boundary and an ordinary
`Runs -> False` proof could make the certificate explosive. The constructor-by-
constructor witness theorem forces every registry extension to exhibit a
formal output before it compiles. For source computations that witness is only
the explicit fail-closed `false` branch. It does not witness a
theorem-authorizing successful result, show that the success branch is
satisfiable, or provide evidence that a physical computation ran.

No source-small-`q` registered invocation is present yet. Adding one before the
whole v3 sidecar has a canonical Lean decoder (or a deterministic generated
Lean literal), the source modulus/primitive-character roster is fixed in Lean,
and a top-level Boolean checker composes the raw postprocess, DFT, and completed-
sign checks would give an undefined protocol trusted meaning. The eventual
`Runs` equation should instead be fixed in source and have the shape “the pinned
decoder produced a complete small-`q` certificate, the repository-defined
checker returned `true`, and its fixed compact summary equals these returned
bytes.” Its ordinary checker-soundness theorem must derive the arithmetic
result; the MMR root may identify the streamed artifact but cannot replace the
certificate or checker-acceptance fact.
