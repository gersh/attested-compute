# Ternary-Goldbach external-program readiness

This is the source audit for the ten physical campaigns serving the thirteen
named external atoms.  The machine-readable authority for this table is
`specifications/TERNARY_GOLDBACH_EXTERNAL_PROGRAM_READINESS.json`.

“Azure ready” below means that the source-closed materializer and job graph
exist.  It does **not** mean that a source-scale run happened, that Azure
evidence was appraised, or that a receipt was admitted into Lean.  Every
production deployment option is still `none`, the imported trusted-compute
registry is empty, and no campaign currently receives theorem authority from
an Azure run.

The critical distinction is between an operational retained artifact and a
Lean source artifact.  The former may be enough for Python/C++ independent
replay.  The latter must contain every datum consumed by a total Lean
`Bool`, with an ordinary theorem from successful checking to the exact
source claim.  Hashes of omitted rows and always-rejecting programs do not
meet that standard.

## Exact readiness matrix

| Physical campaign (logical atoms) | Generator/runtime | Complete artifact output | Strict parser | Total checker | Lean soundness | Azure materializer/orchestration | Catalog | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ch25-a7-boundary` (`ch25-a7-boundary`) | Complete 16,191-leaf FLINT replay | Operational transcript complete; Lean analytic source artifact absent | Strict Python plus total exact-length Lean parser for the identity-pinned seven-field finite transcript; analytic-enclosure parser absent | Lean checks complete finite wire geometry/arithmetic only | Conditional; FLINT/Arb-to-Mathlib realization absent | Complete one-job CPU materializer; not run | Missing | Data-only analytic enclosures and parser, `rawG` refinement, then reviewed run/receipt |
| `ch25-psi-two-pass-v1` (`ch25-psi-1e13`) | Complete two-pass C++ campaign | Complete when run; Lean prime/log/gap envelope absent | Total Lean parser for the actual compact C++ summary/verify JSON, pair equality, and fixed 100,000-shard chain; no parser exists for the rows hidden behind the two SHA-256 commitments | Complete receipt-wire Boolean and soundness theorem; no row/log/roster realization Boolean | Conditional; directed-log and roster/gap realization absent | Complete 644-job CPU DAG; not run | Missing | Retain, serialize, and check all prime/log/gap rows (including `[1,2)`), prove `Real.log` refinement, run |
| `platt-head-2e4` (`platt-head-2e4`) | Complete FLINT campaign, locally exercised | Q128 table present; analytic/Turing Lean artifact absent | Strict Python; no complete Lean parser | Q128/rational-bracket inner checks only | Conditional; Hardy-Z, multiplicity, and exact count absent | Complete one-job CPU materializer; not run | Missing | Retain/parse endpoints and Turing data, prove evaluator and slot completeness |
| `platt-trudgian-rh-3e12` (`platt-trudgian-rh-3e12`) | Literal reference complete but multi-year; optimized worker incomplete | Reference output complete when run; Lean has one PT21 block only | Full external reference parser; Lean parses one 320-byte record | One-block finite Lean checker only | Finite wire soundness only; analytic source realization absent | Five-phase reference CPU DAG complete; optimized path refused | Missing | Streaming multi-artifact checker, Hardy-Z/Turing proof, economical worker or huge run |
| `helfgott-prop-12-2-4-mpfr-v1` (`helfgott-prop-12-2-4`) | Complete parallel MPFR/GMP two-replay campaign | Terminal emits an exact manifested candidate after full replay; Lean candidate contains geometry only | Exact Python/Lean candidate wire; full external parser | Partial arithmetic Bool, then explicit rejection | Chain soundness only; MPFR/GMP row realization absent | Four source jobs plus terminal CPU merge with trace-bound candidate; not run | Missing | Extend artifact with row enclosures and prove every source row/coverage |
| `hurst-four-residuals-v1` (four Möbius-family atoms) | Complete shared two-pass C++ campaign | Terminal emits an exact manifested candidate after both replays; Lean candidate contains affine chain only | Exact Python/Lean candidate wire; full external parser | Partial affine Bool, then explicit rejection | Chain soundness only; primitive row realization absent | Complete 644-job shared CPU DAG with trace-bound candidate; not run | Missing | Add Möbius/squarefree/Q96 row data and prove all four projections |
| `cdem-table-abel` (`cdem-table-abel`) | Complete producer plus independent full replay; standalone artifact-input terminal implemented | **Complete** `TG-CDEM-ABEL-ARTIFACT-V1` emitter and source transcript | **Complete Python, C++, and Lean parsers** | **Complete total Lean Bool over the full artifact; bounded-tested no-shell C++ terminal** | **Ordinary artifact-acceptance-to-source-claim theorem complete** | Producer materializer plus additive fresh-challenge artifact-input terminal materializer complete; not run | **`artifactConcrete` source-only** | Install production verifier/deployment pins, close/review C++/compiler/ELF refinement, run both stages, and install receipts |
| `ramare-zuniga-lemma-6-2` (`ramare-zuniga-lemma-6-2`) | Complete H100 producer plus CPU replay | Complete when run; Lean sees structural child manifest only | Strict external parser; Lean manifest parser only | External replay complete; Lean manifest/chain checks fail closed | Conditional; coefficient and directed-log realization absent | Complete one-job H100 materializer; calibration/run pending | Missing | Parse raw retained rows, authenticate child, prove coefficient/log semantics |
| `helfgott-platt-goldbach-gpu-v1` (`helfgott-platt-theorem-4-1`) | Complete two-branch route but multi-year | Complete when both branches run; Lean sees 8,512-child manifest only | Strict external branch parsers; Lean manifest parser only | External branch replay; Lean ladder/manifest only, fail closed | Conditional binary-plus-ladder theorem; byte refinement absent | H100 binary, CPU ladder, and CPU terminal materializers complete | Missing | Total binary-plus-ladder artifact checker, child authentication, practical run |
| `platt-dirichlet-theorem-7-1` (`platt-dirichlet-theorem-7-1`) | Literal reference complete but astronomical; optimized route incomplete | Reference complete when run; optimized and full Lean envelope incomplete | Strict external reference parser; Lean inner formats/manifest only | Lean inner small-q checks only; full campaign fails closed | Conditional; completed-L, Hardy-Z, multiplicity, and Turing links absent | Literal CPU/postcheck materializer complete; packed H100 path nonterminal | Missing | Finish optimized pipeline or run reference, then prove the full two-branch archive |

The shared Hurst campaign supplies four logical atoms:
`cdem-squarefree`, `mertens-hurst`, `platt-little-mertens-2-11`, and
`platt-little-mertens-stronger`.  This is why thirteen atoms reduce to ten
physical campaigns.

## Bottom line

- All ten physical campaigns have a full-range external route and an Azure
  packaging route.  Two of those routes (finite RH and Dirichlet) are
  intentionally unscaled fallbacks whose optimized replacements are not
  end-to-end complete; historical Goldbach is also economically
  impractical at the current estimate.
- CDEM Abel is the sole complete Lean source-artifact program today.  Its
  separate artifact checker, parser, total replay Boolean, and ordinary
  source theorem are in
  `SparkInterval/TernaryGoldbach/CDEMAbelArtifactProgram.lean` and
  `SparkInterval/TernaryGoldbach/CDEMAbelClosedReplay.lean`.  The standalone
  C++ artifact-input terminal and additive two-stage Azure materializer now
  exercise the matching operational shape: the signed first-stage artifact is
  the fresh second job's measured input. The second stage deliberately has no
  registered invocation, and no C++/compiler/ELF refinement theorem is
  claimed.
- Six campaigns have only partial Lean artifact boundaries: one PT21 block,
  the newly emitted Proposition 12.2.4 geometry candidate, the newly emitted
  Hurst affine-chain candidate, or structural child manifests for R2Star,
  historical Goldbach, and Dirichlet.  Both new candidates carry explicit
  `semantic_closure=false` manifests and remain fail-closed.
- A.7 has a complete Lean parser for its retained finite seven-field
  transcript, but no data-only analytic-enclosure artifact/parser or
  FLINT-to-Mathlib realization. The zeta head has no complete Lean artifact
  parser. Psi has a complete parser for its actual compact shard receipts,
  but not for the committed prime/log rows needed for semantic realization.
- The closed source-program catalog has exactly one source-program-complete
  entry: CDEM as `artifactConcrete`.  The other nine named physical campaigns
  remain missing.  `artifactConcrete` deliberately supplies no installed
  production artifact, machine refinement, deployment pin, or receipt.

## Bounded audit

This check validates the ten-to-thirteen crosswalk, every referenced source
path, the readiness counts, and the Markdown coverage.  It performs no
source-scale arithmetic:

```bash
python3 -m unittest -v tests.test_tg_external_program_readiness
```

For release or Azure-run decisions, use the stricter fail-closed completion
matrix in
`specifications/TERNARY_GOLDBACH_EXTERNAL_COMPLETION_AUDIT.json`.  It adds
the requirements which “Azure packageable” intentionally omits: an optimized
end-to-end route, complete Lean artifact chain, target-SKU measured high time
and cost bounds, an admitted production receipt, and live downstream
integration.  Its validator checks both repositories when the sibling
`claude_math` checkout is present:

```bash
python3 tools/validate_tg_external_completion.py \
  --require-claude-math --pretty
```

The validated current result is zero production-complete campaigns.  All ten
have confidential Azure packaging and a closed single-axiom registration;
those two facts are capability, not evidence that a run occurred.
