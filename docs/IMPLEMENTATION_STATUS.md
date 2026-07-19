# Implementation status

## Completed and validated on this DGX Spark

- Phase 0 environment capture, strict one-device GB10/`sm_121` probe,
  directed-rounding diagnostics, PTX/cubin/SASS extraction, and a canonical
  `local_unattested` probe bundle.
- Phase 1 exact real intervals, expression semantics, containment lemmas, and
  `evalInterval_sound` in Lean.
- Phase 2 classification and exact decoding of every binary64 bit pattern;
  finite representable values; downward/upward rounding with enclosure and
  extremality; and proved `FPInterval` add, subtract, multiply, and divide
  containment.
- Phase 3 exact `Fraction`-based Python binary64 arithmetic, canonical
  integer/string-only JSON formats, schemas, strict parser/checker, and edge
  and oracle vectors.  Native Python floating point is not used to decide an
  expected endpoint.
- Phase 4 primitive CUDA batch execution: 1.25 million randomized rows for
  each of add/subtract/multiply/divide (5 million total), 80 curated valid
  rows, 26 rejected rows, and zero bit mismatches.
- Phase 4 bounded postfix expression execution: all version-1 operations,
  strict host validation, one thread per row, distinct zero-divisor and
  nonfinite-intermediate-widening statuses, deterministic replay, and strict
  PTX plus conservative SASS audits.  The acceptance run used 256 randomized
  programs, 1,000,000 randomized program/row cases, 3,504 curated cases, and
  had zero mismatches.
- Phase 5 polynomial vertical slice: a typed Lean PTX AST without a raw-opcode
  escape hatch, deterministic `sm_121` emitter and validator, canonical batch
  parser, strict Driver API runner, independent PTX/SASS audits, and native
  exact-cubin execution. 100,000 rows matched exact Python and the Phase 4 CUDA
  payload; nine literal signed-zero multiplication cases, byte-identical
  PTX/cubin/output replays, exact-reference recomputation, and bound SASS
  closure also passed.
- Phase 6 pure-arithmetic slice: Lean semantics for raw binary64 moves,
  sign-bit negation, directed add/subtract/multiply, min/max, and fresh-register
  fragment execution. The exact add/subtract/14-instruction multiply arrays
  used by the generator have execution and enclosure theorems without a new
  project axiom.
- Phase 7 generated-cubin arithmetic bundle: fail-closed packaging into the
  existing canonical `local_unattested` format, preserving the exact batch,
  result, PTX, cubin, SASS, audits, replay artifacts, executables, sources,
  `ptxas`, and `nvdisasm`. The retained 100,000-row bundle passes integrity
  verification and explicitly reports `hardware_evidence: false`.
- Phase 7 detached DGX operator signature: Ed25519 key generation, canonical
  domain-separated signing of the exact run bundle, separately pinned-key
  verification, complete artifact verification, and persistent replay
  protection. This adds operator provenance while deliberately retaining
  `local_unattested` evidence and `hardware_evidence: false`.
- Real-zeta application POC: for integer `2 <= s <= 64` when the fixed
  binary64 program remains finite, the DGX expression runner evaluates the
  first `N` positive Dirichlet-series terms. The independent verifier reparses
  and exactly recomputes every row, requires byte-identical replay, re-runs the
  PTX/SASS audits, performs an outward sequential reduction, and adds a
  rigorous integral-test tail. The retained 4,096-term `zeta(2)` run passed and
  was also accepted under the detached operator-signed policy.
- Source and theorem axiom audits.  The mathematical results use only the
  reported Lean foundations; the only project execution postulates are the
  isolated H100 hardware bridge and the explicitly operator-trusted DGX
  signature bridge.

## Implemented but not a formal proof bridge

- Python exact recomputation and CUDA differential testing are strong testing
  evidence, but neither implementation is formally refined to Lean's
  `FPInterval` model.
- The binary CUDA expression format uses interval-valued binary64 constants
  and per-row statuses.  Lean's existing `Expr` instead has exact-real
  constants, and no Lean theorem currently decodes the wire language and
  relates the two evaluators.
- A `reference_certificate` is self-contained and recomputed by Python.  It is
  not parsed or checked by Lean and carries no execution provenance.
- A valid detached DGX signature proves only that the pinned operator key
  signed the exact local record. The separate Lean execution axiom represents
  an intentional trust decision about the truth of that operator assertion;
  neither layer turns it into hardware evidence.
- The current Lean numeric model treats `+0` and `-0` as the same real value;
  the exact Python and CUDA layers preserve and test their distinct encodings.
- The nearest-even candidate specification has enclosure/nearest structure,
  but the unconditional midpoint-even parity lemma remains open.  The directed
  interval core does not rely on nearest-even rounding.

## Completed offline for H100

- Real `compute_90` PTX and `sm_90` cubin/SASS generation for the diagnostic
  probe and primitive interval batch, with instruction audits and artifact
  hashes.
- Strict H100 host-runner source validation, canonical target/trust profiles,
  test-only mock evidence, and a production provider stub that always fails
  closed.
- One isolated Lean postulate, `h100_attested_run_sound`, whose premise binds
  the algorithm, inputs, parameters, result, nonce, profiles, artifacts,
  target, and successful completion.

The H100 manifests explicitly record that H100 presence was not queried and
execution was not attempted.  They contain no result or attestation.  A native
x86 workload, positive NVIDIA confidential-computing evidence importer, real
execution, replay/tamper testing, and production acceptance still require a
supported H100 CC platform.

## Next proof and application work

- Extend the accepted Phase 5 polynomial generator to division, absolute
  value, minimum, maximum, complete metadata/manifests, and the full expression
  language.
- Extend the Phase 6 arithmetic-fragment semantics with register-renaming,
  guards, control flow, memory, indexing, threads, emitted-text refinement, and
  prove `generatedKernel_sound` without project axioms.
- Extend Phase 7 packaging to future H100 arithmetic runs only after a real
  measured runner and positive confidential-computing evidence importer exist.
- Implement a Lean parser/checker for result certificates, prove the decoder
  and wire-evaluator refinement, and derive a nontrivial checked application
  theorem (Phase 8).
- For Riemann zeta: complex intervals; certified logarithmic/trigonometric and
  argument-reduction bounds; a proved high-height evaluation and adaptive-
  precision algorithm; rigorous zero isolation; completeness/coverage such as
  a Turing-method theorem; and a Lean application theorem that either checks a
  mathematical certificate or consumes the explicitly trusted
  `AlgorithmReturned` fact.

The real-integer POC is intentionally narrower than this remaining zeta work:
it evaluates positive real values for `s > 1` and does not inspect the critical
strip, isolate zeros, or establish height coverage.

Accordingly, the repository now provides a substantial verified arithmetic
and tested GPU foundation, but it must not yet be described as verifying zeta
zeros to any bound.
