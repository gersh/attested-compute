# Ternary Goldbach external atoms

This page is the audit and engineering guide for the thirteen named external
atoms on which the `claude_math` ternary Goldbach theorem currently depends.
SparkInterval does **not** discharge any of those Lean atoms today. It now
performs complete external replays for the CH25 A.7 boundary and the CDEM Abel
recurrence, checks other retained evidence at its honest trust level, supplies
bounded exact references, and records what remains for a Lean-kernel result.

The machine-readable source of truth is
[`specifications/TERNARY_GOLDBACH_EXTERNAL_ATOMS.json`](../../specifications/TERNARY_GOLDBACH_EXTERNAL_ATOMS.json).
It was synchronized against `claude_math` source commit
`667f873bcfdf3f3d7bd4f835a25ee5a9ad5e20ce`.  Re-run the inventory comparison
whenever the Lean declarations or citation inventory change; a matching name
set does not by itself prove any proposition.

## Read the status labels literally

The tools deliberately report which object they checked.  These classes are
not interchangeable:

| Class | What it establishes | What it does not establish |
| --- | --- | --- |
| Full external replay | A complete external producer was rerun over its advertised range and its output passed the external checker. | It is not a Lean proof unless the producer's arithmetic and analytic meanings are connected to the Lean definitions. |
| Structure-only artifact check | Canonical encoding, exact integers and rationals, topology, counts, digests, and other internal relationships in a retained artifact are consistent. | It does not reevaluate FLINT, zeta, zeta derivatives, zero isolation, or another analytic function merely because the artifact records those values. |
| Retained full-report check | A report has the expected full endpoint, exact recorded error-budget arithmetic, and, when supplied, the expected raw-file hash. | It neither replays the reported computation nor proves that its floating- or fixed-point implementation realizes the Lean function. |
| Structural transition-receipt check | Self-reported ranges, prefix states, executable identity, row digests, and hash links are internally consistent and obey the producer's per-receipt size limit. | It does not replay the rows, authenticate that the executable ran, or anchor the self-authored final digest. |
| Bounded exact sample | The exact reference predicate passed on every integer or slab through the displayed sample limit. | It says nothing about unsampled indices and cannot prove a larger universal range. |
| Blocked or missing source artifact | The paper claim is cataloged, but the database, run log, or production algorithm needed for an independent replay is absent. | No runtime estimate or verification claim should be inferred from a citation alone. |

In particular, `accepted: true` from an artifact checker means that the named
artifact contract passed.  The receipts also say `proves_lean_claim: false`,
or the aggregate audit says `lean_atom_discharged: false`.  Those fields are a
hard trust boundary, not a TODO that the command silently assumes.

## Quick audit

Run commands from the SparkInterval repository root.  Point
`CLAUDE_MATH_ROOT` at the checkout containing the Lean theorem and retained
artifacts.

```bash
export CLAUDE_MATH_ROOT=/absolute/path/to/claude_math

python3 tools/tg_verify.py --pretty catalog
python3 tools/tg_verify.py --pretty sync-inventory --cards \
  "$CLAUDE_MATH_ROOT/problems/ternary-goldbach/citations/inventory.json"
python3 tools/tg_verify.py --pretty audit-root "$CLAUDE_MATH_ROOT"
```

The last command requires a clean tracked worktree at the catalog's exact Git
commit. Before running `#print axioms`, it asks Lake in `--rehash --no-build`
mode to rehash source traces and confirm that
`Math.Problems.TernaryGoldbach.Statement` and its complete dependency closure
are already up to date. The audit does not build stale or missing objects
itself; run the Lean repository's documented source build first if that check
fails. It then partitions the fresh `#print axioms` output
into the foundational trio, thirteen named external atoms, and generated
`native_decide` atoms, and hashes every mapped citation card. Finally it
performs the A.7 structure check, the Proposition 7.7 summary check, and the
Ramaré--Zúñiga retained-report/hash check. It emits a row for all thirteen
atoms so omission cannot look like verification.

Run the exact local KATs separately. Every finite work bound is at most 64;
larger samples and all source-scale runs fail closed unless launched by the
measured Azure worker:

```bash
python3 tools/tg_verify.py --pretty sample-arithmetic --limit 64
python3 tools/tg_verify.py --pretty verify-psi-range \
  --limit 64 --chunk-span 64 --segment-size 64
python3 tools/tg_verify.py --pretty verify-r2star-range \
  --limit 64 --block-size 64 --harmonic-terms 64
python3 tools/tg_verify.py --pretty prop1224-scheduler
python3 tools/tg_verify.py --pretty verify-prop1224-sample \
  --q 6469693230 --bits 96 --log-terms 32 --max-pairs 64
```

These commands are useful for falsification, implementation comparison, and
performance planning.  Their JSON classification is
`bounded_exact_sample_not_full_verification` or
`bounded_exact_cpu_reference_not_full_verification`.

## Thirteen-atom status

The short status below is deliberately conservative.  “Feasible” refers to a
specific external computation or artifact audit, not automatically to
discharging the corresponding Lean declaration.

| ID | Present evidence and strongest local check | Feasibility of next honest step | Missing before Lean discharge |
| --- | --- | --- | --- |
| `ch25-a7-boundary` | The pinned full replay recomputes all 16,191 FLINT/Arb leaf boxes, all nonvanishing guards, and both exact dyadic evidence endpoints; a retained development measurement took 1.56 s. `A7BoundaryCertificate.lean` checks the authoritative seven-field leaves with transparent `Nat`/`Int` arithmetic (no executable rational comparison or `native_decide`) and proves canonical four-edge coverage, positive zeta guards, the strict squared-norm threshold, both pole guards, and the exact source claim from one explicit `AnalyticRealization`. `A7BoundaryWire.lean` is now a total, exact-length parser/checker for a deterministic fixed-width projection of every retained leaf; it pins the source JSON, canonical leaf array, binary payload, and full wire, and has Python-to-Lean fixtures plus rehashed semantic-mutation tests. The registered `true` relation retains exactly the checked certificate and realization without embedding the production leaf list in local builds. A closed one-job Azure CPU materializer pins the artifact, complete FLINT/python-flint source trees, exact x86 wheel, registered invocation, and a second full trace replay. | Complete external analytic replay, fail-closed finite byte parser, transcript-shaped ordinary-Lean finite checker, narrowed registered relation, conditional source theorem, deterministic renderer, and measured-job materialization are implemented. | Review/prove the FLINT/Arb-to-Mathlib zeta/derivative realization and measured code-to-registered-relation refinement, run both complete passes only on Azure, appraise and admit the compact receipt, then enable the semantic binding. |
| `ch25-psi-1e13` | The source-scale C++ worker uses pinned primesieve and CRlibm directed logarithms, emits exact Q64 deltas and event commitments, and fixes 100,000 independent leaves for each of two passes. The cluster plan groups those leaves into 320 workers per pass without changing receipt granularity. Lean proves the exact endpoint/slab reduction to Mathlib's `psi` from explicit source evidence. | Local measured throughput projects to about 7.2 hours for both passes, or roughly 0.5--2 hours across eight 40-core NCC nodes. | Bind retained producer rows to the Lean source-evidence premise, complete and independently replay the source campaign, and admit its measured receipt. |
| `platt-head-2e4` | A resumable pinned-FLINT campaign recomputes exact `N(20000)=22491`, all 22,492 indexed critical-line isolations, disjointness, cutoff bracketing, multiplicity completeness, and the directed reciprocal bound. Head chunks retain every exact interval preimage, authenticate them during structural replay, reproduce both the reviewed 22,491-row source-table digest `e7943dee...` and 22,492-row sentinel-inclusive digest `fc67e829...`, and can emit the literal Lean table. Lean proves checked Hardy-Z brackets plus the multiplicity-slot count imply the exact source enumeration without assuming simplicity. A closed CPU/SEV-SNP invocation pins both digests, FLINT 3.6.0/96 bits, count and height. | Complete external analytic replay, exact table generation, and the conditional registered/signed Lean slice are implemented; the retained historical summary and LMFDB fold remain independent comparisons. | Retain and review the full artifact, materialize the literal table and `CheckedQ128HeadEvidence`, prove FLINT Hardy-Z/count realization and the exact downstream table-identification theorem, then admit a successful receipt. The exact semantic shape is staged, but remains disabled. |
| `platt-trudgian-rh-3e12` | A pinned native FLINT 3.6 campaign rechecks exact multiplicity-counted `N(3000175332800)=12363153437138`, covers the ordinary prefix, fixes 1,236,316 formulaic Platt/Turing index shards plus the `N+1` sentinel, retains compact interval-stream receipts, and Merkle-aggregates them without assuming zero simplicity. A closed five-phase Azure CPU materializer now packages that exact reference route. Every dependent phase verifies the predecessor's signed production receipt and structurally replays its retained export; the terminal handoff authenticates the prefix and exactly all 1,236,316 shard receipts before calling the existing finalizer. The optimized route separately has a v2 trace contract, authenticated Gamma/DD components, a bounded CPU/FLINT stationary fallback, a source-shaped Turing-input producer, a validated adapter from those finite outputs to canonical `PT21BLK1` records, and a bounded-memory native shard/campaign finalizer. The adapter now streams records directly into the pinned finalizer and withholds its terminal manifest commitment until exact gap-free completion, removing a second 884.07 GiB record spool. The V2 H100 worker now also fuses the exact left/main/right event scanner and emits terminally authenticated 192-byte `PT21EVT1` records carrying the scanner Merkle root and unresolved-stationary count without retaining the 621,202-byte per-window packet; independent C++/Python/Lean checks cover that nonterminal wire. A bounded synthetic chain now binds the CUDA event record, FLINT Gaussian--sinc stationary trace, directed-Arb inputs, exact-rational replay, and native `PT21BLK1`; framed persistent modes reproduce every one-shot wire byte exactly while amortizing CUDA startup. It still does not consume genuine source packets gap-free or bind the external analytic semantics, so it is not one complete production worker. Lean has an exact conditional source theorem and a closed CPU/SEV-SNP registered receipt slice with the source constants pinned. No source-height campaign has been run, and every external semantic-realization flag remains false. | The exact five-phase route is source-complete and Azure-packageable but unscaled: measured count-only FLINT throughput projects to about 13.4 ideal years on 320 processes. Its one-week / USD 10,000 production gates are explicitly false. A bounded first-64-block GB10 fused event sample sustained 8.9688 blocks/s and left 172 stationary candidates unresolved; it is not an H100 or source-wide measurement. The persistent synthetic fixture reruns the CUDA scanner on every request and measured a `0.04740 s` median warm CUDA-scan/FLINT junction, `0.000424 s` median warm Arb step, and `0.1775 s` median exact adapter; the Python exact-rational artifact replay is now the bounded bottleneck, but these repeated block-zero numbers do not support a source ETA. The optimized materializer is refused until it consumes genuine consecutive source packets, composes nonempty sparse refinements, replaces or validates the Python artifact bottleneck at source scale, and passes target-SKU measurements. | Either execute and retain the exact 1,236,316-shard CPU campaign or complete and run the optimized path; audit the complete signed Merkle/export chain; realize endpoint enclosures, Hardy-Z isolation, multiplicity count, and analytic Turing evidence into `SourceEvidence`; admit a successful attested receipt; and only then enable the semantic binding. |
| `helfgott-prop-12-2-4` | The production C++ worker covers all 3,389,047,618 q-ranks in 12,930 independent leaves, recomputes factorization and `phi(q)`, and uses outward MPFR/GMP arithmetic for every retained source margin. It isolates the exceptional q=1 leaf and merges plan-bound receipts. A closed Azure CPU factory now source-builds pinned GMP/MPFR, runs the leaves in four 96-worker measured jobs, independently reruns every group, authenticates all retained exports, and performs a second exact full-plan terminal merge before emitting registered result `true`. | Empty-row slices project to 61--73 single-core hours per replay; the production model retains a wider 105.6--640 core-hour band per replay. The two-replay protocol therefore has a conservative 0.55--3.34 compute-hour band on four 96-core DC96as_v6 nodes before Azure overhead. | Smoke-test the deterministic x86-64 materialization, complete the Azure run and receipt chain, review the MPFR/GMP-to-exact-real realization boundary, admit the terminal receipt, and enable the currently disabled semantic binding. |
| `cdem-squarefree` | One source-scale Hurst segmented-Möbius two-pass campaign jointly checks squarefree, Mertens, and both little-Mertens residuals. V2 retains exact four-coordinate deltas and checks both the threshold value and every right limit. Lean reconstructs global prefixes from primitive local rows and proves both strict-real squarefree inequalities plus the `6/π²` density enclosure from Mathlib's π bounds. | The shared 10,000-leaf two-pass CPU campaign has a broad 2--22 day estimate on eight NCC nodes. A separate exact eight-worker affine route has a `54.121`-hour terminal-H100-stage sensitivity from a `191.737 ms`/100M-row GB10 measurement and an unmeasured `12.3x` H100 factor; the CPU prefix/handoff is excluded, so this is neither a complete campaign ETA nor H100 evidence nor production-ready. Either physical campaign must run once, not four times. | Complete and replay the shared V2 campaign, attach its `LocalSourceScaleEvidence` through the registered receipt, and prove the small definition-identification theorem in `claude_math`. |
| `cdem-table-abel` | The supervisor captures, hash-pins, and compiles the exact reviewed C++ source plus its SHA-256 header dependency, checks an independent small recurrence, and ran the complete five-billion-step producer in 86.574 s. A separately reviewed Eratosthenes/binary-search/serial implementation independently replayed all 1,000 exact chunks in 45.85 s wall time (363.411 aggregate CPU-s over eight workers) with at most 20 MB of principal chunk storage per worker. The transcript generated a fixed 1,000-chunk Lean arithmetic certificate. The V2 registry requires that certificate's ordinary `certificate_check` theorem and physical `LocalSourceScaleEvidence`, then derives global recurrence folds plus the scaled and exact source claims in ordinary Lean; it no longer trusts the final real inequalities directly. | Complete external production, independent bounded-memory replay, fixed arithmetic-certificate generation, and the narrowed source-shaped trusted-compute Lean bridge are implemented. Lean source compilation is pending the shared build lane. | Source-compile the fixed certificate and V2 bridge, extend retained evidence to the local-fold boundary, run under production Azure attestation, admit the signed receipt, generate its concrete Lean consumer, and prove the definition-by-definition `claude_math` import theorem. The physical local-fold realization and C++/machine-code refinement remain inside the disclosed single trusted-run boundary. |
| `mertens-hurst` | This is the owner of the shared four-residual Hurst campaign: 10,000 independent summary leaves, a rooted four-state reduction, 10,000 independent verification leaves, and one final certificate also consumed by squarefree and both little-Mertens atoms. Lean's `checked_hurst_real_of_local` proves the exact-state-to-real-slab projection after deriving global prefixes along the checked replay. | The CPU route retains its broad 2--22 day eight-NCC range. The implemented exact eight-worker affine alternative has a `54.121`-hour terminal-H100-stage sensitivity derived from GB10 and an unmeasured `12.3x` H100 factor. It excludes the CPU prefix/handoff, remains explicitly uncalibrated, and is outside production totals. No duplicate Möbius campaigns are needed. | Complete and replay the shared V2 campaign, attach its registered `LocalSourceScaleEvidence`, and identify the package-local Mertens step with the consumer definition. |
| `ramare-zuniga-lemma-6-2` | The exact Python reference recomputes complete hash-linked transitions. A CUDA producer reproduces its scale-2^32 log, coefficient, blocked prefix, envelope, full-factor digest, and canonical chunk hash; rare Q64-ambiguous rows use an arbitrary-precision rational host fallback, while an exact segmented host sieve commits every factor. The Azure H100 materializer rejects any pre-populated work directory, source-builds the exact sm_90 runner and a separate CPU checker from a pinned closure, and runs the whole range without resume. Before registered `true`, and again during trace replay, that checker independently reconstructs all factor supports, directed-row digests, prefix states, and squared-envelope minima. The generic API/CLI cannot emit registered `true` without that full replay. Lean proves checked source evidence implies the literal real-variable claim. | The full producer, mandatory full-row replay, fresh-workspace materializer, and portfolio route are implemented; focused known-answer/tamper and materializer suites pass. Three-repeat low/terminal million-row GB10 medians give 5.85--6.05 serial producer hours and 5.23--5.38 one-thread replay hours by linear sensitivity. The implemented factory is one serial-chain NCC job, so its uncalibrated Azure band is 1--8 node-hours with parallelism capped at one. None of these local numbers is an H100 measurement. | Run and retain all 21 billion endpoints on the target SKU, appraise the signed receipt, and review/prove the explicit physical-to-Lean refinement of `coefficientRealizes` and `logLowerRealizes`; no successful receipt is claimed. |
| `helfgott-platt-theorem-4-1` | The binary branch fixes 65,536 immutable source-height leaves, scheduled as 8,192 eight-leaf GPU groups with at most eight concurrent H100 jobs. Its hardened race-free word-owner sieve and deterministic Miller--Rabin fallback are independently checked against the CPU implementation. A distinct optimized wheel-47/warp-32749/shifted/packed source identity now has exact historical plan, run, aggregate, checker, and unregistered combiner routes. A campaign-specific H100 materializer remains pinned to the base identity. The ladder branch fixes 492,700 independent ranges; a native GMP producer sieves the source-shaped Proth-52 candidates and Python independently replays every exact Proth/Pocklington rung before the ordered reducer combines both branches. Lean proves the exact parity-sensitive binary-plus-ladder reduction and the packed-output-to-campaign refinement. Closed operational CPU materializers and a measured terminal transitively bind all 8,512 signed base-route producer results to every raw branch receipt before replay. | The optimized bounded GB10 sample transfers to `8192.223` hours (`341.343` days) on eight equal-throughput GB10 GPUs, before scheduler/attestation/retry/storage/replay overhead. It is not an H100 measurement and is still far outside the production budget gate. The native ladder projects to about 12,700 aggregate core-hours, roughly 33 ideal hours on four 96-core CPU nodes. | Build and calibrate the exact optimized x86_64/SM90 identity on H100, register a new closed Azure route if promoted, complete and replay both campaigns, finish CUDA/compiler-to-Lean refinement or retain the disclosed trusted-compute boundary, materialize `CheckedSourceEvidence`, enable the semantic binding, and admit the successful receipt. |
| `platt-dirichlet-theorem-7-1` | The exact CRT/Conrey scheduler covers 29,565,923,837 primitive characters for `q=2..400000`, with the stronger q=1 zeta campaign explicit. A pinned-FLINT argument-principle/Hardy-Z fallback is rigorous but unscaled. The optimized path now includes certified Arb Hurwitz lattices, a completely generated and higher-precision-replayed 96-MB finite-recovery seed table, an authenticated 125-GiB t-major lattice layout with bounded row replay and exact broadcast scheduling, a fail-closed cache-range adapter that has fed the resident q-major CUDA worker in a bounded KAT, directed at-most-64-ordinate CUDA Taylor/composition batches with no device transcendental, persistent CRT/Bluestein transformation and completed-L consumption, scalable hash-bound root-number artifacts, and a factored-v3 directed-disk small-q Gaussian/DFT engine with independent Arb family replay. A new q-level semantic reducer higher-precision replays both parity time-tail controls, binds every character parity and source sample, and emits exact ordered negative/positive/ambiguous two-bit codes without zero or multiplicity inference. After the full small-q DFT, the CUDA runner's device-side `TGDBSPK1` classifier applies the exact outward boundary, reduces complete status, and copies only the packed two-bit codes plus an eight-byte summary. The distinct large-q path retains its own CRT/root/completed-factor identities and same-device compact phase reducer; it is not relabelled `TGDBSPK1`. A local full-span synthetic `q=5460` GB10 differential run produced byte-identical host/device payloads and compact states while reducing device transfer 125.24-fold. Conditional sinc, exception, and corrected reflected Turing arithmetic also exist. Lean now has a source-faithful open-strip contract and a closed CPU/SEV-SNP finalizer whose success relation requires the exact universal even/odd source evidence. | The quantified legacy component totals are not an atom ETA. The current seeded fused large-q path measures 19.42 million values/s on GB10 and has an unmeasured 58.5--116.9-hour eight-H100 arithmetic sensitivity at an assumed 10--5x uplift. Its old 5.180-PB repeated lattice boundary now has a 125-GiB unique-cache contract and a bounded cache-to-resident CUDA integration, but that cache is not populated and no exact source phase or source-scale H100 measurement exists. Small-q v3 has a 2.460-TB physical split service, 129.859-GB time-tail controls, and a 1.182-TB packed sign/ambiguity artifact. In device mode, the implemented classifier eliminates the 226.996-TB full-disk device-to-host transfer; the local `q=5460` result is not an H100 calibration or a source-wide measurement. The device-packed phase remains nonterminal and is not wired into the source-wide portfolio; DFT containment/semantic replay, zero/multiplicity evidence, source-wide output usefulness, interpolation, exception refinement, and Turing closure remain open. | Populate and audit the t-major cache, run exact source phases through the cache/resident/all-character pipeline, wire and source-scale measure the device-packed classifier/reducer path, prove source-wide enclosure usefulness, resolve interpolation/exception/Turing closure without discarding multiplicity, run and replay the full domain, construct `PlattTheorem71SourceEvidence`, retain a successful receipt, and only then enable the currently staged-disabled semantic binding. |
| `platt-little-mertens-2-11` | Logical alias of the one shared Hurst four-residual certificate; its exact directed reciprocal state and real-slab guards are checked in the same two passes as Mertens and squarefree. Lean's `checked_little211_real_of_local` proves the full real statement from that evidence. | No separate scan: replay the shared certificate produced under `mertens-hurst`. | Complete shared receipts, attach the registered local replay evidence, and identify the package-local little-Mertens step with the consumer definition. |
| `platt-little-mertens-stronger` | The same shared certificate preserves and checks the exceptional closed endpoint `7727068587`; `checked_little_stronger_real_of_local` proves the full real statement. This atom is another logical alias, not a second campaign. | No separate scan: replay the shared certificate. | Complete shared receipts, attach the registered local replay evidence, and identify the package-local step definition. |

The exact Lean names and source-shaped claims follow.  Keeping these names in
one catalog prevents a convenient surrogate calculation from being mistaken
for the proposition actually used by `ternary_goldbach`.

## Analytic and zeta atoms

### `ch25-a7-boundary`

Lean declaration:

```text
AnalyticNT.ChebyshevPsi.finite_check_ch25_lemA7_arb_boundary_source
```

Claim: on all four edges of the rectangle
`[-3,5] + i[-4,4]`, the regularized logarithmic derivative `G` has norm at
most `349/250`.

The lightweight checker validates canonical JSON, the exact four-edge
dyadic partition, leaf coverage without gaps or overlaps, the stored positive
zeta-lower-bound fields, and the exact rational comparison of each stored
norm-square upper bound with `(349/250)^2`.  It intentionally does not call
FLINT and does not establish that a stored bound encloses zeta or `G`.  It
reports the whole-file SHA-256 and can require the pinned A.7 identity.

```bash
python3 tools/tg_verify.py --pretty verify-a7 \
  --retained \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/certificates/a7_boundary.json"
```

For a fresh full external replay using the pinned `claude_math` FLINT
environment but SparkInterval's independent leaf checker:

```bash
"$CLAUDE_MATH_ROOT/ext/ch25_certificates/.venv/bin/python" \
  tools/tg_verify.py --pretty replay-a7-flint \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/certificates/a7_boundary.json"
```

For a standalone SparkInterval environment, install the exact dependency from
`requirements-tg-flint.txt`; the replay rejects any python-flint or FLINT
version other than `0.9.0` / `3.6.0`.

It recomputes the zeta jet on every accepted leaf, checks all pole and
nonvanishing guards, requires each fresh exact dyadic endpoint to match the
retained transcript, and rechecks the strict norm-square inequality. Its
remaining trusted base is Python/FLINT/Arb and the host toolchain until an
analytic realization theorem connects those interval operations to Lean.

The source semantics are fixed in
[`A7BoundarySourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/A7BoundarySourceSemantics.lean).
The transcript-shaped checker is
[`A7BoundaryCertificate.lean`](../../SparkInterval/TernaryGoldbach/A7BoundaryCertificate.lean).
It consumes exactly the decoded edge/depth/index and two mantissa/exponent
pairs retained by the authoritative parser. Its executable path uses only
transparent natural/integer comparisons and power-of-two cross
multiplication. Ordinary Lean proves those checks give complete frontier
coverage, positive zeta lower bounds, nonzero `s-1`, `s+2`, and zeta
denominators, and the strict `(349/250)^2` bound. The sole remaining analytic
premise is visibly named `AnalyticRealization`: per leaf, it identifies the
stored FLINT lower/upper endpoints with bounds on Mathlib's `riemannZeta` and
the exact `rawG` expression. `tg_verifier/a7_lean_certificate.py` validates
the authoritative seven-field transcript and deterministically renders the
same literal interface without replaying FLINT.

The complete finite byte boundary is
[`A7BoundaryWire.lean`](../../SparkInterval/TernaryGoldbach/A7BoundaryWire.lean).
`tools/tg_a7_boundary_wire.py` deterministically projects the validated JSON
to fixed-width records.  Lean rejects truncation and suffixes, recomputes the
payload SHA-256, parses all seven fields, runs the exact certificate checker,
and separately pins the retained whole-wire identity.  This is a parser and
finite arithmetic result only: its source-claim theorem continues to take
`AnalyticRealization` explicitly.

The existing closed `ch25A7BoundaryProductionV1` invocation binds the retained artifact
hash, FLINT/python-flint versions and all source constants, accepts only Azure
SEV-SNP CPU receipts, and exposes the claim only for result `true`. The signed
wrapper adds exactly the existing trusted-run axiom. Its success relation
now retains one existential transcript-shaped `Certificate`, a proof that its
transparent checker returned `true`, and `Nonempty (AnalyticRealization
certificate)`. Ordinary Lean derives the literal source claim from precisely
that relation. The production leaf list is deliberately not embedded in a
normal local build: the trusted-run axiom transports the registered relation
from the compact reviewed receipt, so local theorem checking does not repeat
the FLINT computation or traverse 16,191 production leaves. The closed
measured materializer and complete cloud-side second trace replay are
documented in
[`CH25_A7_AZURE_MEASURED_WORKLOAD.md`](CH25_A7_AZURE_MEASURED_WORKLOAD.md).
No successful Azure receipt or independently kernel-proved FLINT-to-Mathlib
realization is included, and the semantic-binding row remains disabled and
null.

### `ch25-psi-1e13`

Lean declaration:

```text
AnalyticNT.ChebyshevPsi.finite_check_ch25_lemma_9_2_psi_source
```

Claim: for every real `1 <= x <= 10^13`,
`-sqrt(2) < (psi(x)-x)/sqrt(x) <= 0.79059276`.

This is not merely a check at `10^13`: `psi` changes at every prime power, and
the normalized expression also changes between events.  A valid producer has
to prove a gap-free event stream, evaluate both sides of each real slab with
directed transcendental bounds, preserve resumable prefix state, and check the
correct extrema.  SparkInterval now has a bounded-memory exact reference for
all of those discrete obligations.  It uses an exact segmented sieve, the
positive rational `atanh` series for directed fixed-point `log(p)` bounds, and
integer-squared endpoint comparisons; no floating-point square root enters a
decision.  Run a bounded instance with:

```bash
python3 tools/tg_verify.py --pretty verify-psi-range --limit 100000
```

That 100,000-endpoint sample is cloud-only. For a local KAT, use
`--limit 64 --chunk-span 64 --segment-size 64`.

The source-scale worker replaces the slow Python production path. It uses
pinned primesieve for the exact prime-power event stream and pinned CRlibm
directed binary64 logarithms, decodes those endpoints into exact Q64 integers,
and checks the source slab endpoints without using a floating square root in a
proof decision. The two-pass supervisor keeps 100,000 compact leaf receipts
rather than retaining the enormous event stream:

```bash
python3 tools/tg_psi_residual_campaign.py init \
  --runner build/psi/sparkinterval-tg-psi-residual-shard \
  --runner-source reference/tg_psi_residual_shard.cpp \
  --upstream-manifest specifications/PSI_UPSTREAMS.json \
  --output-dir /durable/psi-1e13
python3 tools/tg_psi_residual_campaign.py run \
  /durable/psi-1e13 summary --workers 40
python3 tools/tg_psi_residual_campaign.py reduce /durable/psi-1e13
python3 tools/tg_psi_residual_campaign.py run \
  /durable/psi-1e13 verify --workers 40
python3 tools/tg_psi_residual_campaign.py finalize /durable/psi-1e13
python3 tools/tg_psi_residual_campaign.py verify /durable/psi-1e13
```

The cluster plan reduces 200,000 Slurm launches to two 320-element worker
arrays. Each worker selects a deterministic strided group with
`--worker-group-index` / `--worker-group-count`, uses bounded local parallelism,
and still writes one immutable receipt per original leaf. The measured local
rate projects to about 7.2 hours for both passes, or approximately 0.5--2 hours
across eight 40-core NCC nodes. See
[`CH25_PSI_VERIFIER.md`](CH25_PSI_VERIFIER.md).

`PsiEndpointArithmetic.lean` proves the exact Q64 upper guard implies the
rational `19764819/25000000` real bound. `PsiPrimePowerCertificate.lean`
proves that adding one directed `log p` interval for each exponent
`1 <= k <= p.log n` is exactly Mathlib's prime-power expansion of
`Chebyshev.psi n`; directed prime-log realization therefore implies the Q64
prefix enclosure. `PsiSourceSemantics.lean` turns that enclosure, the integer
slab guards, and strict terminal handling into the complete normalized source
claim. `RegisteredPsiLemma92Certificate.lean` fixes the CPU invocation and
exposes the same claim from a successful signed receipt. Its current algorithm
hash is `b16368f84ca70c2a3e7b9b9814c7e098e79c0c3bb137a51b85851cfd526753b0`.
These reductions use no project axiom until the signed wrapper, which adds
only `accepted_run_certificate_sound`.

This is still not a completed computation. No full two-pass artifact or
production receipt exists. The registered success boundary now asks for
`GapSourceScaleEvidence`: directed prime-log realization, exact finite
prime-power gap coverage/state constancy, and the integer guards checked only
at event boundaries. Lean proves those two guards control every integer slab,
rather than asking the receipt to assert `Chebyshev.psi` or the final lemma.
The retained C++ row/commitment format has not yet been proved to construct
that evidence, so the Azure semantic row remains explicitly disabled.

### `platt-head-2e4`

Lean declaration:

```text
AnalyticNT.ChebyshevPsi.finite_check_platt_zero_enumeration_2e4_source
```

Claim: 22,491 committed cells biject with all multiplicity-counted nontrivial
zeta zeros with `0 < Im(rho) <= 20000`, and each cell encloses its ordinate.

Check the retained small summary structure:

```bash
python3 tools/tg_verify.py --pretty verify-prop77 \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/certificates/ch25_prop77_flint.json"
```

Recompute the FLINT summary externally:

```bash
"$CLAUDE_MATH_ROOT/ext/ch25_certificates/.venv/bin/python" \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/scripts/verify_flint_head.py" \
  --check \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/certificates/ch25_prop77_flint.json" \
  --max-seconds 600
```

The repository-native resumable route computes the count, all interval-digest
preimages, the bracketing zero, and the reciprocal enclosure:

```bash
OUT="$(mktemp -d build/tg/zeta-head-2e4.XXXXXX)"
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty full "$OUT" \
  --profile platt-head-2e4
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty verify \
  "$OUT" --complete
```

An independent LMFDB-data route can check official file hashes, decode the
published ordinate stream, recompute the reciprocal fold, and compare cells:

```bash
"$CLAUDE_MATH_ROOT/ext/ch25_certificates/.venv/bin/python" \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/scripts/verify_lmfdb_head.py" \
  --check \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/certificates/ch25_prop77_lmfdb.json"
```

Use `--offline` after the two LMFDB files have been cached. A list of 22,491
plausible ordinates alone is not a completeness proof. The new FLINT campaign
instead combines `zeta_nzeros`, which counts all zeros with multiplicity, with
22,491 disjoint critical-line isolations below the cutoff and one isolation
above it. Equality supplies the external multiplicity/completeness argument.
The remaining trust is FLINT's analytic implementation and its absent Lean
realization, not a missing stored ordinate preimage.

The exact conditional Lean handoff is implemented in
[`ZetaHeadSourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/ZetaHeadSourceSemantics.lean)
and
[`RegisteredZetaHeadCertificate.lean`](../../SparkInterval/Execution/RegisteredZetaHeadCertificate.lean).
The closed `plattHead2e4ProductionV1` invocation accepts only Azure SEV-SNP
CPU receipts and pins height `20000`, multiplicity count `22491`, FLINT 3.6.0
at 96 bits, and two deliberately distinct commitments:

- `fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca`
  covers all 22,492 Q128 rows, including the first sentinel above the cutoff;
- `e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7`
  covers the 22,491 rows in the literal source table.

The exact 22,491-row table is checked in as
[`PlattHeadQ128.table`](../../SparkInterval/Generated/PlattHeadQ128.lean).
On result `true`, `Runs` requires `CheckedQ128HeadEvidence` for that named
table, including its computed commitment equality to the second digest;
result `false` proves nothing. This is stronger than accepting an arbitrary
existential table with a matching digest, and it does not use collision
resistance as a Lean table-identity theorem. No evidence inhabitant, accepted
receipt, or downstream theorem identifying this named table with the
consumer's committed table is included. The Azure semantic row therefore
remains disabled. Its invocation, conditional source-claim theorem, and
reviewed result path are staged explicitly, but those fields are not evidence
and cannot enable the row.

The production packaging path is now closed as a single Azure SEV-SNP CPU
job. `tools/tg_azure_cpu_platt_head_materializer.py` pins the complete FLINT
3.6.0 and python-flint 0.9.0 source trees, the exact reviewed x86-64 wheel,
both Q128 digests, the literal `true` output, and an external trace verifier
which freshly replays the retained count, six isolation chunks, finalization,
and table generation. See
[`PLATT_HEAD_AZURE_MEASURED_WORKLOAD.md`](PLATT_HEAD_AZURE_MEASURED_WORKLOAD.md).
This is package capability, not evidence that the Azure run or source review
has happened.

### `platt-trudgian-rh-3e12`

Lean declaration:

```text
AnalyticNT.ChebyshevPsi.finite_check_platt_trudgian_rh_zeta_3e12
```

Claim: every nontrivial zeta zero with
`0 < Im(s) <= 3000175332800` lies on `Re(s)=1/2`.

Two independent implementations now exist. The
[native FLINT indexed campaign](PLATT_ZETA_FLINT_CAMPAIGN.md) provides the exact
multiplicity count, fixed indexed-isolation geometry, and sentinel logic. The
preferred high-range production route is the
[pinned public Platt windowed Arb/Turing source campaign](PLATT_PT21_WINDOWED_SOURCE_CAMPAIGN.md),
which uses the source computation's large windowed transform instead of
refining twelve trillion indexed zero records:

```bash
python3 tools/tg_platt_zeta_campaign.py --pretty init \
  build/tg/zeta-rh-3000175332800 \
  --runner build/platt-zeta/sparkinterval-tg-platt-zeta-shard
python3 tools/tg_platt_zeta_campaign.py --pretty count \
  build/tg/zeta-rh-3000175332800
python3 tools/tg_platt_zeta_campaign.py --pretty run-shard \
  build/tg/zeta-rh-3000175332800 0

python3 tools/tg_platt_windowed_campaign.py --pretty init \
  build/tg/platt-pt21-windowed --runner build/platt-pt21/arb-zeta
python3 tools/tg_platt_windowed_campaign.py --pretty run-shard \
  build/tg/platt-pt21-windowed 0 --runner build/platt-pt21/arb-zeta
```

The exact reference implementation now also has a
[five-phase Azure CPU materializer](PLATT_PT21_AZURE_CPU_MATERIALIZER.md).
It preserves initialize/count/prefix, all 1,236,316 formulaic shards, and the
existing Merkle finalizer as separate measured phase groups. Each handoff is
accepted only from an authenticated production receipt whose signed result
pins the replayed retained export. The terminal package scans the complete
formulaic range and refuses missing, substituted, duplicated, or extra shard
receipts. This closes the reference route's packaging/control-plane boundary;
it does not make its multi-year computation economical and does not claim a
run has occurred.

The optimized route now also has a bounded
[CPU/FLINT stationary-point fallback](PLATT_PT21_STATIONARY_RESOLVER.md). It
independently reconstructs the scanner's complete three-stream candidate
list, applies the corrected source interpolation with a bounded dyadic search,
replays retained endpoints at higher precision, and emits the exact-rational
touching brackets consumed by the v2 finalizer. This is tested as an ordinary
CMake/CTest target. It is not yet called by the measured all-window worker,
does not manufacture refinements for ambiguous input disks, and keeps all
Hardy-Z, FLINT-to-Mathlib, and analytic Turing realization claims false.

Initialization must freshly obtain the exact source count
`N(3000175332800)=12363153437138`. Completing every fixed shard and finalizing
the Merkle tree establishes the external finite-height claim, subject to the
documented FLINT/toolchain trust boundary. The local 4,096-index source-height
measurement is 91.38 zeros/second/process, projecting to about 13.4 ideal
years and `$6.56M` PAYG on eight 40-vCPU NCC nodes at the recorded Azure rate.
The real windowed checker instead proves one height-`1008` block in about
`5.38` local CPU seconds and has a fail-closed transcript/count-chain wrapper.
Its full CPU projection is about `4.43 million` one-core hours. Its exact
interval-FFT work would require about `14.184 billion` butterflies/s on each
of eight H100s to finish that stage in seven days; the complete H100 path,
term accumulation, lower prefix through `10^10`, and physical H100 benchmark
are not yet implemented. No source-height completion is claimed.

The exact conditional Lean handoff is implemented in
[`ZetaRHSourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/ZetaRHSourceSemantics.lean)
and
[`RegisteredZetaRHCertificate.lean`](../../SparkInterval/Execution/RegisteredZetaRHCertificate.lean).
The closed `plattTrudgianFiniteRHProductionV1` invocation pins campaign ID,
height, multiplicity count, and reviewed implementation geometry, and accepts
only approved confidential-compute receipts. Result `true`, together with an explicit
`SourceEvidence`, yields the literal positive-height open-strip source claim;
result `false` proves nothing. No endpoint-to-Hardy-Z realization, global-count
realization, complete windowed H100 materializer, lower-prefix artifact,
completed source-scale run, or
successful attested receipt is included. Accordingly, the Azure semantic row
remains disabled. It now stages the exact registered invocation, conditional
source-claim theorem, and terminal result path. The legacy Merkle finalizer
exclusively creates that four-byte `true` file only after source-scale
finalization; staging this contract does not supply the missing evidence.

### `platt-dirichlet-theorem-7-1`

Lean declaration:

```text
MathExtras.Helfgott.MajorArcsStart.platt_theorem_7_1_dirichlet_verification_source
```

Claim: every primitive character of conductor `q <= 400000` satisfies the
parity-dependent Platt zero-height ranges. The exact scheduler, resumable
campaign, source composition, and rigorous slow FLINT backend are documented
in [DIRICHLET_GRH_CAMPAIGN.md](DIRICHLET_GRH_CAMPAIGN.md). The backend counts
zeros with multiplicity by the argument principle on
`[-1/2,3/2] x [-T-1/64,T+1/64]`, subtracts the known simple `s=0` zero for
even primitive characters, and requires the same total number of disjoint
strict Hardy-Z sign changes. Equality leaves no off-line or even-multiplicity
unaccounted zero.

The single source command requires `q=1` from a completed stronger
`platt-trudgian-rh-3e12` campaign and then resumes all `q>=2` characters:

```bash
.venv-tg-flint/bin/python tools/tg_dirichlet_campaign.py source \
  build/tg/platt-dirichlet-7-1-source \
  --q1-zeta-final build/tg/zeta-rh-3000175332800/final.json
```

The final conditional Lean endpoint is
[`RegisteredPlattTheorem71Certificate.lean`](../../SparkInterval/Execution/RegisteredPlattTheorem71Certificate.lean).
Its closed `plattDirichletTheorem71ProductionV1` CPU/SEV-SNP invocation pins
the full conductor range, both exact source height formulas, the
29,565,923,837-character `q=2..400000` roster count, and the separate q=1
zeta source. Result `true` requires the exact universal even/odd
`PlattTheorem71SourceEvidence` and yields the expanded source theorem; result
`false` proves nothing. A source-closed Azure CPU package now runs the literal
q>=2 fallback, authenticates its production receipt/run bundle/statement and
retained archive into a separate terminal postcheck, and replays q=1 plus
every q>=2 checker before emitting `true`. No full physical run or successful
receipt is present, the raw fallback is expected to exceed seven days and may
exceed the 256-GiB transport boundary, and the semantic binding remains
disabled. Its exact invocation, conditional two-branch theorem, and terminal
registered-result path are staged for review. The legacy `verify-source`
terminal writes `true` exclusively and only after replaying q=1, every q>=2
checker, and the exact source composition; no such source-scale run is claimed.

This is a literal unscaled reference, not a practical replacement for
Platt's lattice/FFT and Turing implementation. The H100-bound direct GRH
evaluator is useful at moderate height but loses resolution at the source
ordinates. A separate clean-room implementation now covers the conditional
sixteen-term large-q Taylor reconstruction and its fused at-most-64-ordinate
composition with the paper's `D=2048`, `N=15` parameters; see
[DIRICHLET_LATTICE_H100_STAGE.md](DIRICHLET_LATTICE_H100_STAGE.md) and
[DIRICHLET_LARGEQ_BATCH_STAGE.md](DIRICHLET_LARGEQ_BATCH_STAGE.md).  The full
all-character Bluestein transform and persistent component graph are described
in [DIRICHLET_ALL_CHARACTER_FFT_STAGE.md](DIRICHLET_ALL_CHARACTER_FFT_STAGE.md)
and [DIRICHLET_LARGEQ_PIPELINE.md](DIRICHLET_LARGEQ_PIPELINE.md). Its retained
fixed-q outputs are typed and fail-closed replayed against exact supervisor
targets by
[DIRICHLET_FFT_PIPELINE_RECEIPT_BUNDLE.md](DIRICHLET_FFT_PIPELINE_RECEIPT_BUNDLE.md).
The producer-side shared-row archive and exact fixed-q run roster are described
in [DIRICHLET_TMAJOR_SPOOL.md](DIRICHLET_TMAJOR_SPOOL.md); the production
pipeline does not yet consume that format.
The separate
[DIRICHLET_FUSED_CHARACTER_STAGE.md](DIRICHLET_FUSED_CHARACTER_STAGE.md) remains
an exact sparse-character audit/exception oracle.

## Exact arithmetic atoms

### `helfgott-prop-12-2-4`

Lean declaration:

```text
AnalyticNT.LargeSieve.finite_check_helfgott_prop_12_2_4_computation_source
```

Claim: all source finite `(q,k)` windows hold for `q < 3.3e9`, together with
the `210 | q` extension for `q < 2.2e10`.  The exact scheduler now proves that
this means 3,389,047,618 `q` rows and checks the transition into the
210-divisible extension:

```bash
python3 tools/tg_verify.py --pretty prop1224-scheduler
```

The structural certificate code checks a conservative superset of every `k`
window, recomputes `G_q(k)` as an exact rational finite sum, and composes
hash-linked chunks.  Its generic constructor still accepts supplied outward
enclosures and therefore remains structural-only.

The separate directed producer removes that input gap for bounded rows.  It
computes `varpi`, `lambda`, and every final margin from the source formulas
using rational atanh/Taylor tails and integer cube-root enclosures; no Python
`float` or caller-supplied decimal controls a decision.  Its explicit base
inputs are the theorem-backed Lean intervals for Euler gamma and `c_E`.  Its
directed chunk creator reuses the existing `Prop1224Chunk` scheduler and hash
body, while the stronger chunk verifier reconstructs every stored row instead
of trusting its supplied nonnegative margins.  Run
the complete representative row with:

```bash
python3 tools/tg_verify.py --pretty verify-prop1224-sample \
  --q 6469693230 --bits 96 --log-terms 32 --max-pairs 1000
```

That command checks the entire conservative window `586 <= k <= 721` (136
rows), reports one checked `q` out of 3,389,047,618, and leaves both
`full_source_campaign` and `lean_atom_discharged` false.  See
[the directed-reference design](PROP1224_DIRECTED_REFERENCE.md) for formulas
and assurance boundaries.

The production C++/MPFR worker supersedes the slow Python supervisor for the
source run. It recomputes complete distinct factorization and `phi(q)`, uses
outward MPFR intervals for every transcendental expression, carries `G_q(k)`
in exact GMP integer enclosures at 192-bit scale, and fails on any negative
retained margin. The immutable q-rank plan has 12,930 independent leaves and
isolates q=1:

```bash
python3 tools/tg_prop1224_mpfr_campaign.py plan
python3 tools/tg_prop1224_mpfr_campaign.py run-shard \
  build/prop1224/sparkinterval-tg-prop1224-mpfr-shard \
  /durable/prop1224 417
python3 tools/tg_prop1224_mpfr_campaign.py verify /durable/prop1224
```

The merger requires every fixed-plan receipt and restores exact q-rank order.
Measured empty-row slices project to roughly 61--73 single-core hours per
replay. The production model preserves a wider 105.6--640 core-hour band per
replay; two measured replays on four 96-core DC96as_v6 nodes therefore have a
conservative 0.55--3.34 hour compute band. See
[`PROP1224_H100_CPU_CAMPAIGN.md`](PROP1224_H100_CPU_CAMPAIGN.md).

The exact conditional Lean handoff is now implemented. The source semantics
copy the literal `G_q`, `c_E`, `f_1`, `varpi` and error proposition, prove that
the 3,389,047,618-rank scheduler covers the cited range, and reduce checked
gap-free shards to the source claim. The closed
`helfgottProp1224ProductionV1` invocation accepts only Azure SEV-SNP CPU
receipts and exposes the claim only for result `true`. Its deliberately
unproved physical field is the direct statement that outward MPFR/GMP rows
realize the exact Lean row. No source-scale realization evidence or successful
run is included, and the portfolio semantic binding remains disabled.
The closed measured DAG and source-build boundary are documented in
[`PROP1224_AZURE_MEASURED_DAG.md`](PROP1224_AZURE_MEASURED_DAG.md).

### `cdem-squarefree`

Lean declaration:

```text
MathExtras.CohenDressElMarraki.reproducibleSquarefree_verifier_output
```

Claim: the two strict-real squarefree-count error bounds hold through `10^16`
after thresholds 9,243 and 438,429.  The CPU sampler checks exact rational or
integer inequalities only through its requested limit:

```bash
python3 tools/tg_verify.py --pretty sample-arithmetic --limit 64
```

The catalog records separate retained evidence through 550,000; the command
above is the intentionally smaller exact reference used for routine review.
The current production route is the shared Hurst segmented-Möbius worker. One
row stream accumulates four exact state coordinates (`M`, squarefree `Q`, and
two directed little-Mertens sums). A first pass emits additive deltas for
10,000 fixed leaves; the reducer derives every rooted incoming state; a second
pass independently reruns every leaf and checks all four residual families:

```bash
python3 tools/tg_hurst_residual_campaign.py init \
  --runner build/hurst/sparkinterval-tg-hurst-residual-shard \
  --runner-source reference/tg_hurst_residual_shard.cpp \
  --upstream-manifest specifications/HURST_MERTENS_UPSTREAM.json \
  --output-dir /durable/hurst-four-residuals
python3 tools/tg_hurst_residual_campaign.py run \
  /durable/hurst-four-residuals summary
python3 tools/tg_hurst_residual_campaign.py reduce \
  /durable/hurst-four-residuals
python3 tools/tg_hurst_residual_campaign.py run \
  /durable/hurst-four-residuals verify
python3 tools/tg_hurst_residual_campaign.py finalize \
  /durable/hurst-four-residuals
```

The source implementation is adapted from the pinned Hurst segmented sieve;
the campaign captures both the runner and its upstream manifest. Disjoint
Slurm workers execute outside the short campaign lock, while ingestion
revalidates identities and converges only on byte-identical duplicate
receipts. Finalization creates one affine/Merkle certificate whose atom list
contains squarefree, Mertens, and both little-Mertens claims. The broad
eight-NCC planning range is 2--22 days.  The separate exact eight-worker
affine route projects `54.121` arithmetic-only terminal-H100-stage hours at an
unmeasured `12.3x` GB10-to-H100 factor.  It excludes the CPU prefix/handoff,
is not a complete campaign ETA or target-H100 evidence, and is excluded from
production totals. Running either physical campaign four times would add no
evidence and is explicitly excluded by the cluster plan.

The registered worker and supervisor use protocol V2.  For each strict-real
squarefree threshold `t`, V2 checks the value at every integer `n >= t` and
the right limit at `n+1`; the supervisor rejects older right-limit-only
receipts.  The registered route requires
`HurstSourceSemantics.LocalSourceScaleEvidence`: primitive
Möbius/squarefree/Q96 row increments, local finite guard decisions, literal
range, and zero root.  Ordinary Lean reconstructs the unique global prefixes
along the checked block chain; it does not ask every state in an affine guard
to be a global prefix.  The Q96 realization is required only through
`10^12`, matching the point where the worker freezes those coordinates.
`checked_squarefree_b1_real_of_local` and
`checked_squarefree_b2_real_of_local` then prove the two full real-slab
statements.  The same module proves the directed `6/π²` enclosure using
Mathlib's 20-decimal π bounds.  These realization theorems have only Lean's
foundational trio in their axiom audit; no full physical run is retained.

### `cdem-table-abel`

Lean declaration:

```text
MathExtras.CohenDressElMarraki.reproducibleTable_abel_verifier_output
```

Claim: with `K=199330` and `N=5000000000`, the signed and
square-root-weighted Abel increments satisfy the two exact directed numerator
bounds encoded by the checker.

Run the hardened full external reference producer:

```bash
python3 tools/tg_verify.py --pretty run-cdem-abel \
  reference/tg_cdem_abel.cpp \
  --threads 8 \
  --block-size 5000000 \
  --transcript-output build/tg/cdem-abel-full.txt
```

The current producer allocates an `int32` array with roughly five billion
entries, approximately 20 GB before auxiliary allocations.  Plan capacity
accordingly. The supervisor rejects any source other than the reviewed hash,
compiles that source itself with an identified and hashed compiler, checks a
small independently known recurrence, then checks the exact parameters,
Möbius trace, coefficient enclosures, recurrence endpoint, total variation,
and two final numerators. This is strong reproducible external evidence, not
a Lean proof or hardware attestation.

The retained historical run was independently replayed with the second
reviewed implementation using the following production command. The command is
now cloud-guarded; it is not part of a local build or ordinary receipt check:

```bash
python3 tools/tg_verify.py --pretty replay-cdem-abel-chunks \
  build/tg/cdem-abel-full.txt --workers 8
```

The production transcript exposes 1,000 exact five-million-row chunks. The
replayer uses a different Möbius sieve, exact binary search for every directed
square-root weight, a serial recurrence scan, and only chunk-sized storage.
The full local replay took 45.85 s wall time and 363.411 aggregate CPU-s; its
principal storage bound was 20 MB per worker and 160 MB for eight workers. It
reproduced the complete manifest and final aggregates. The retained transcript
has SHA-256
`2a1d551dee2f5e8997e8e2a77a587cb6cf53b93b32854f943591163db2460123`.
It deterministically generated the fixed 1,000-chunk Lean certificate with
source SHA-256
`c31fe5bdb3444d53b484dbc14592d1509f284378e75ba356a006d68b952f2ee9`.

The V2 registry binds successful numeric output to that exact certificate,
uses its ordinary `certificate_check` proof for topology and reduction, and
requires `Nonempty LocalSourceScaleEvidence` at the trusted physical edge.
Its chunk folds mention only states obtained from `before` by repeated
`floorJump`; checked chaining derives every global source state and fold
before proving the recurrence-to-real and scaled-to-source implications.  The
older global `SourceScaleEvidence` remains only as an off-path compatibility
API.  The current 1,000-row generated file does not itself construct the
local physical witness.
This removes dependence on one opaque 20 GB process and removes the final
real inequalities from the trusted relation, but it still trusts the physical
recurrence realization, reviewed external C++ source, identified compiler,
runtime, and attestation.

### `mertens-hurst`

Lean declaration:

```text
MathExtras.EffectiveMertensDecay.mertensM_hurst_sqrt_source
```

Claim: for every real `33 <= x <= 10^16`,
`|M(x)| <= (571/1000)*sqrt(x)`. The shared Hurst worker checks the literal
exact integer predicate

```text
571^2*n - 1000^2*M(n)^2 >= 0.
```

Because `M(x)=M(floor(x))` and square root is increasing, the integer check at
`n` covers the real slab `[n,n+1)`. The two-pass reducer derives every
non-root incoming state from the all-zero root, so no isolated leaf is treated
as unconditional. The campaign fixes 10,000 source leaves through `10^16`,
runs those leaves independently in both passes, and emits one certificate for
all four Möbius-family atoms:

```bash
python3 tools/tg_hurst_residual_campaign.py verify \
  /durable/hurst-four-residuals
```

The campaign is now source-scale infrastructure rather than a bounded CUDA
sample, but no full run is retained. The broad CPU eight-NCC estimate is
2--22 days. The implemented exact eight-worker affine alternative has a
`54.121`-hour terminal-stage arithmetic sensitivity from the current GB10
measurement and an unmeasured `12.3x` H100 factor; it excludes the CPU
prefix/handoff, has no target-H100 calibration, and does not pass the
production gate. `mertens-hurst` owns this physical campaign;
`cdem-squarefree` and both
little-Mertens atoms only replay its final certificate.  Lean theorem
`HurstSourceSemantics.checked_hurst_real_of_local` already derives the exact
source real inequality from checked local full-range replay evidence.
Remaining work is the physical V2 run, registered evidence import, and the
definition-identification theorem in the downstream `claude_math` package.

### `ramare-zuniga-lemma-6-2`

Lean declaration:

```text
MathExtras.RamareMertens2025.ramare_zuniga_2024_lemma_6_2_source
```

Claim: for every real `3 <= X <= 21000000000`,
`|r2Star(floor(X))| <= 1.93*sqrt(X)*log(X)`.

Audit the retained focused report and bind it to the retained raw report:

```bash
python3 tools/tg_verify.py --pretty verify-ramare \
  --retained \
  "$CLAUDE_MATH_ROOT/problems/ternary-goldbach/ramare_zuniga_2024_lemma_6_2_full21e9.json" \
  --raw-report \
  "$CLAUDE_MATH_ROOT/problems/ternary-goldbach/ramare_2013_seams_full21e9.json"
```

In retained mode the checker pins both artifact identities, checks the stored
endpoint and no-bad-index fields, recomputes the exact decimal addition of the
stored worst ratio and outward error budget, and checks the strict bound.  The
extremum and `PASS` fields remain producer assertions: it still consumes an
aggregate report rather than replaying all 21 billion state transitions.  The
next artifact should make those transitions
independently composable and connect fixed-point `log` and Euler-gamma
enclosures to their Lean meanings.

Run the new all-integer bounded reference separately:

```bash
python3 tools/tg_verify.py --pretty verify-r2star-range \
  --limit 100000 \
  --scale-bits 128 \
  --series-terms 48 \
  --harmonic-terms 100000
```

That sample is cloud-only. For a local KAT, set `--limit`, `--block-size`,
and `--harmonic-terms` to 64.

Build and run the bounded CUDA factor-support primitive separately:

```bash
cmake -S . -B build/dgx-spark \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/dgx-spark \
  --target sparkinterval-tg-r2star-factor-support
./build/dgx-spark/sparkinterval-tg-r2star-factor-support \
  --lower 1 --count 1000000
```

The runner constructs all base primes through the exact integer square root,
copies the GPU records back, independently trial-factorizes every requested
integer on the host, and fails on any field mismatch.  Its receipt is
classified `bounded_factor_support_primitive_not_r2star_atom_proof`: this
standalone lower-layer target does not check the directed logarithms, R2Star
prefix accumulation, or final inequality.  On the local GB10 development host, the one-million-row command
above took 2.37 ms in the three CUDA kernels and 377 ms in the independent CPU
check.  This is a bounded engineering measurement, not an H100 or full-range
claim.

The newer `sparkinterval-tg-r2star-chunk` target composes that factor layer
with rigorous exact-or-reject Q64 logarithms, directed coefficients, prefix
state, squared envelope, Python-compatible full-factor digest, and canonical
hash linkage.  Its bounded outputs pass arbitrary-precision Python replay
across different chunk partitions and around retained worst index
`110102617`.  See
[`R2STAR_CUDA_CHUNKS.md`](R2STAR_CUDA_CHUNKS.md) for the exact arithmetic,
overflow boundary, commands, measured runtime, and remaining full-campaign
gaps.

`sparkinterval-tg-r2star-arithmetic-replay` is a separate CPU-only
implementation used by the Azure result and retained-trace gates. It consumes
only receipt commitments and independently recomputes every integer row. A
factor digest, directed-row digest, prefix endpoint, slack witness, fallback
count, range, or state-link mismatch rejects the campaign. This removes the
previous production dependence on structural receipt replay alone.

The generic registered-result API now always requires that exact replayer;
the `run` CLI accepts a result output only together with the replayer, while
structural `verify` does not accept one. `tools/tg_r2star_benchmark.py` uses a
separate bounded plan header and requires the native status `BENCHMARK_ONLY`,
so its low/high timing samples cannot be passed to the production finalizer.

The exact Lean side is now
[`R2StarSourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/R2StarSourceSemantics.lean).
It copies the source `r2Coeff` and `r2Star` definitions literally, checks a
gap-free compact Q32 chunk chain, and proves that explicit row realization plus
the squared guards implies the cited claim for all real `X` in the source
range. The registered H100 wrapper is
[`RegisteredR2StarCertificate.lean`](../../SparkInterval/Execution/RegisteredR2StarCertificate.lean).
Its only project-specific theorem axiom is the repository's single trusted-run
axiom. This is a theorem reduction, not a run: the C++ factor recurrence must
still supply the explicitly named von-Mangoldt coefficient realization field,
and the disabled Azure semantic-binding entry remains null until that edge and
a source-scale receipt exist.

This reference uses the exact prime-factor support identity, rational atanh
series for directed logarithms, the elementary bounds
`H_m-log(m+1) <= EulerGamma <= H_m-log(m)`, and a squared integer form of the
`1.93*sqrt(n)*log(n)` comparison. It is bounded-memory and theoretically
accepts the source endpoint, but the Python implementation is not a practical
21-billion-step production engine.

### `platt-little-mertens-2-11` and `platt-little-mertens-stronger`

Lean declarations:

```text
MathExtras.Helfgott.Section24.residual_platt_2_11
MathExtras.Helfgott.Section24.residual_platt_stronger_range
```

Claims:

- for every real `1 <= x <= 10^12`,
  `|sum_(n<=x) mu(n)/n| <= sqrt(2/x)`; and
- for every real `3 <= x <= 7727068587`,
  `|sum_(n<=x) mu(n)/n| <= 1/(2*sqrt(x))`.

Exact `Fraction` sampling remains the small independent reference. In
production, these are two guard families in the same Hurst four-coordinate
row stream described above. Scale-`2^96` directed reciprocal states and the
source-shaped real-slab comparisons are computed during both passes; the
stronger guard preserves the exceptional closed endpoint `7727068587`.

Neither logical atom schedules its own scan. Both require and replay
`mertens-hurst/certificate.json`, whose plan covers the larger shared domain
through `10^16`. The finalizer names all four atom profiles and refuses an
incomplete pass. Only bounded tests have been run; no full shared campaign is
claimed. Lean theorems `checked_little211_real_of_local` and
`checked_little_stronger_real_of_local` already prove the two ordinary
real-slab statements from checked local full-range replay evidence, without
`native_decide` or a new axiom. The downstream tie-in only has to identify the
package-local floor-step sum with the corresponding `claude_math` definition.

## Goldbach finite-range atom

### `helfgott-platt-theorem-4-1`

Lean declaration:

```text
Math.Problems.TernaryGoldbach.helfgott_platt_theorem_4_1_source
```

Claim: every odd `n` from 7 through
`8875694145621773516800000000000` is a sum of three primes.

Checking explicit witnesses through 200,000 is only a bounded sample. The
published finite verification used a prime ladder and a separate verification
of binary Goldbach through `4e18`, but the paper reports that its full
per-range ladder files were deleted.

The commands in this production-plan example run inside measured Azure
workers. Local use is limited to plan generation, structural receipt
inspection, and explicit at-most-64-item KATs; group and checkpoint counts are
not treated as arithmetic bounds.

The production plan composes two independently checked workflows. First, the
hardened GoldbachGPU campaign checks every even through `4e18` in 65,536
immutable leaves. The scheduler launches 8,192 deterministic groups of eight
strided leaves, with cluster concurrency limited to eight H100 nodes, then
builds a plan-bound receipt aggregate. Second, the native GMP prime-ladder
producer covers all 492,700 independent source ranges while Python replays
every exact rung before publication:

```bash
python3 tools/tg_goldbach_gpu_campaign.py create-production-plan \
  --source-root /reviewed/hardened-goldbach-gpu \
  --executable /reviewed/goldbach \
  --executable-sha256 "$GOLDBACH_SHA256" \
  --out /durable/goldbach-source/plan.json
# Run group indices 0 through 8191 with --group-count 8192, then aggregate
# and verify all 65,536 leaf receipts.
python3 tools/tg_goldbach_campaign.py init \
  /durable/goldbach-source/ternary-prime-ladder
python3 tools/tg_goldbach_ladder_native.py produce-group \
  /durable/goldbach-source/ternary-prime-ladder \
  --runner build/tg-production/sparkinterval-tg-goldbach-ladder-native \
  --group-index 0 --group-count 320 --local-workers 40
# Submit group indices 0 through 319, then reduce all exact range receipts.
python3 tools/tg_goldbach_campaign.py reduce-ranges \
  /durable/goldbach-source/ternary-prime-ladder \
  --out /durable/goldbach-source/ladder-aggregate.json
```

The exact reviewed optimized binary source also has a separate source-scale
route:

```bash
python3 tools/tg_goldbach_gpu_campaign.py \
  create-optimized-production-plan \
  --candidate-package-root /reviewed/optimized-goldbach-gpu \
  --candidate-manifest-file-sha256 \
    "$OPTIMIZED_CANDIDATE_MANIFEST_FILE_SHA256" \
  --source-root /reviewed/optimized-goldbach-gpu/source \
  --executable /reviewed/optimized-goldbach-gpu/artifacts/goldbach-gpu \
  --executable-sha256 "$OPTIMIZED_GOLDBACH_SHA256" \
  --out /durable/goldbach-optimized/plan.json

python3 tools/tg_goldbach_campaign.py combine-optimized-gpu \
  /durable/goldbach-source/ternary-prime-ladder \
  --ladder-aggregate /durable/goldbach-source/ladder-aggregate.json \
  --binary-plan /durable/goldbach-optimized/plan.json \
  --binary-receipts-dir /durable/goldbach-optimized/receipts \
  --binary-aggregate /durable/goldbach-optimized/aggregate.json \
  --out /durable/goldbach-optimized/combined.json
```

The optimized result uses a distinct kind and hash domain and binds the
algorithm, plan, and complete source identity. It is not accepted by the
currently registered v1 terminal. This is an executable full-range route,
not a run, source-scale coverage artifact, attestation, or production
promotion. Optimized plan creation also requires and fully revalidates the
qualified candidate package that contains the selected source tree and
executable, but its internal self-hash is not accepted as its own authority.
It additionally requires the SHA-256 of the exact canonical manifest file to
be present in a source-reviewed production allowlist. That allowlist is
currently empty pending review of an Azure x86_64/SM90 package, so the
displayed post-review command fails closed today.

`tools/tg_goldbach_gpu_binary_checker.py` adapts the aggregate to the ladder's
exact binary-checker request protocol by reloading the production plan, all
65,536 leaf receipts, and the Merkle aggregate. The final ladder replay accepts the
full atom only after that binary replay and all range/rung/adjacency checks
succeed. It accepts only one of the two exact historical-domain plan
identities; a lowered `10^27` production plan can no longer satisfy the
historical request merely because it carries `production=true`.

The ladder fixes the paper's range width `2^54*10^9`, maximum gap `4e18`, and
endpoint tolerances. The native worker uses the source witness order through
29 and the sieve primes below 16,000, but its compact output is untrusted:
Python independently repeats every Jacobi-symbol and modular-power check.
Rare non-Proth holes fail closed and require separately checked
Pocklington/ECPP evidence. Every range has its own immutable receipt, and the
reducer proves exact ordered coverage before combining it with the binary
aggregate.

This is implemented capability, not a practical completion claim. The final
2026-07-21 high-range GB10 benchmark processed 600,000,000 terminal evens in a
seven-run median of 0.779701 seconds (769.526 million evens/s). The checked
source projection is 90,243 eight-GPU hours, or 10.295 years, at equal GB10
throughput. An uncalibrated 2--5x H100 sensitivity gives 45,122--18,049 cluster
hours (5.15--2.06 years); the advertised 14.3x memory-bandwidth ratio is only a
roofline endpoint, not a runtime prediction. A source-height native-ladder
sample projects roughly 12,700 aggregate core-hours, separately. See
[`GOLDBACH_LADDER_CAMPAIGN.md`](GOLDBACH_LADDER_CAMPAIGN.md) and
[`H100_TG_CLUSTER.md`](H100_TG_CLUSTER.md). No completed campaign or Lean
receipt is claimed.

The later integrated wheel-47/warp-32749/shifted/packed source processed a
20-billion-even bounded terminal sample in `2.35908 s`; charging the measured
`0.427747 s` initialization once for each of 65,536 leaves projects the exact
historical binary domain to `8192.223362062222` hours (`341.343` days) on
eight equal-throughput GB10 GPUs. The corresponding on-demand and spot
arithmetic are about `$457,454` and `$93,000`. No H100 speedup is assumed,
and scheduler, attestation, retry, storage, and terminal replay are excluded.
This materially improves the old reference projection but remains far outside
the one-week/USD-10,000 gate and is not a target-SKU measurement.

The active hardening patch subsequently extended the race-free word-owner
prefix from the exact odd primes through `1021` to those through `2039`.
Paired seven-run GB10 medians on 2026-07-22 improved from `0.858128 s` to
`0.823758 s` for the same terminal 600-million-even range (`4.17%` by rate),
with zero phase-2 fallbacks.  Since that session had a different host load,
the source-scale table below retains the earlier absolute benchmark rather
than combining incomparable measurements.

A replacement coverage stage is now implemented in
[`h100_tg_goldbach_shift_or.cu`](../../gpu/platform/h100/h100_tg_goldbach_shift_or.cu).
It ORs shifted prime-bitset words, covering 64 consecutive evens per thread,
instead of making scattered per-even probes. The exact shift equation and
Goldbach-pair implication are proved in
[`GoldbachShiftedBitset.lean`](../../SparkInterval/TernaryGoldbach/GoldbachShiftedBitset.lean).
That module also proves that a gap-free array of checked output words implies
the existing exact `BinaryGoldbachClaim`; the optimized route therefore needs
no new paper-shaped trust declaration.
On a 1,073,741,824-even synthetic workload the local GB10 sustained 68.93
billion evens/s for this stage, with no failed word and exact CPU replay of
4,096 words. Eight equal GB10s project to 1,007.4 coverage-only hours; a 6.0x
per-device H100 improvement would put that stage under seven days. This is a
real kernel measurement but not yet a revised source-scale campaign estimate:
the first exact persistent bucketed sieve prototype reaches only 304.9 million
odd candidates/s on a source-height GB10 shard, and persistent checkpoints and
confidential H100 calibration remain. See
[`GOLDBACH_SHIFTED_BITSET_OPTIMIZATION.md`](GOLDBACH_SHIFTED_BITSET_OPTIMIZATION.md)
and
[`GOLDBACH_PERSISTENT_BUCKET_SIEVE.md`](GOLDBACH_PERSISTENT_BUCKET_SIEVE.md).

The exact theorem-level handoff is implemented in
[`GoldbachSourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/GoldbachSourceSemantics.lean).
Its finite ladder checker proves the universal interval union, including the
odd-parity `+2` adjacency convention, and ordinary Lean derives the source
three-prime claim from `CheckedSourceEvidence`. The closed
`helfgottPlattGoldbachProductionV1` CPU finalizer pins the binary campaign and
aggregate kind, hardened H100 source identity, ladder campaign and aggregate
kind, native ladder source hash, combined artifact kind, exact branch counts,
and source endpoint. Result `false` proves nothing; only `true` plus a
`Nonempty CheckedSourceEvidence` yields the source theorem.

This vertical slice is conditional. No source-scale evidence or successful
receipt exists, and the present `Runs` proposition does not independently
expose a Lean-checkable transitive provenance chain showing that the final CPU
receipt verified the pinned H100 branch receipts and CPU-ladder receipt/artifact
hashes. The production materializer must add and audit that binding before the
semantic row can be enabled. It therefore remains disabled with null theorem,
realization and invocation fields.

## Measurements on the development host

The following measurements were taken on 2026-07-20 on an `aarch64` Linux
host with Python 3.12.3 and 20 logical CPUs.  The exact reproduction command
was:

```bash
/usr/bin/time -f 'wall_seconds=%e max_rss_kib=%M' \
  python3 tools/benchmark_tg_verifiers.py \
  --no-gpu \
  --mobius-limit 1000000 \
  --exact-fraction-limit 20000 \
  --pretty
```

Total process wall time was 20.33 seconds and maximum resident set size was
30,700 KiB.  Each result below is a bounded CPU reference measurement, not a
full-campaign ETA.

| Reference operation | Bounded range | Elapsed | Observed rate | Result scope |
| --- | ---: | ---: | ---: | --- |
| Linear Möbius sieve | through 1,000,000 | 0.101009 s | 9.90 million indices/s | Input generation only |
| Hurst-form inequality sample | 33 through 1,000,000 | 0.268843 s | 3.72 million checks/s | Bounded sample passed |
| Little Mertens 2.11 exact fractions | 1 through 20,000 | 9.544325 s | 2,095 slabs/s | Bounded sample passed |
| Stronger little Mertens exact fractions | 3 through 20,000 | 10.020418 s | 1,996 slabs/s | Bounded sample passed |
| Squarefree first bound | 9,243 through 20,000 | 0.359896 s | 59,781 endpoints/s | Bounded sample passed |

The exact ψ reference was measured separately with 128 fixed-point bits and
48 rational `atanh` terms.  Through `10^6` it handled 78,734 prime-power
events in 32.446 seconds to produce the stream and 32.538 seconds for an
independent cold-cache replay, about 2,420 event-log checks per second in each
phase, with 57 MiB maximum RSS.  A linear extrapolation of this deliberately
auditable Python implementation to the hundreds of billions of source events
is multiple years, so it is a correctness reference rather than the intended
production engine.

The production primesieve/CRlibm worker was measured separately over twenty
`10^8`-wide leaves with 20 local workers. The summary pass took 2.115 s and
the verify pass 2.875 s for 66,816,322 prime-power events per pass, about 26.78
million event-passes/s combined. Scaling the exact two-pass event count gives
about 7.18 local wall-hours. The cluster supervisor uses 320 deterministic
worker groups per pass to avoid 200,000 scheduler launches while preserving
all 200,000 leaf receipts.

Warm in-process artifact-check medians over seven runs, with the filesystem
cache warm, were:

| Audit | Median | Observed range | Classification |
| --- | ---: | ---: | --- |
| Catalog/inventory name sync | 0.000027 s | first/max 0.000643 s | Exact name-set comparison |
| A.7, 1.5 MiB and 16,191 leaves | 0.152203 s | 0.149744--0.156275 s | Structure-only |
| Proposition 7.7, 4 KiB summary | 0.000108 s | 0.000097--0.000300 s | Summary-only |
| Ramaré focused report plus 14 KiB raw hash | 0.000036 s | 0.000033--0.000110 s | Retained-report check |

Fast artifact parsing must not be confused with the time needed to produce the
artifact.

### GPU planning probe

The new CUDA probe performs deterministic u64 quotient, remainder, wide-high
multiply, mixing, and one eight-byte output per work item.  On the local
NVIDIA GB10 (`sm_121`), 10 repetitions of `2^24` rows took 6.770 ms in the
kernel, or 24.78 billion work items/s and at least 198.25 GB/s of output
traffic.  At `2^28` rows and three repetitions it sustained 23.96 billion
items/s and 191.71 GB/s.  Both runs matched the CPU reference at the first and
last output.

This is a planning roofline, not one of the thirteen verifiers: it performs no
sieve, zeta evaluation, transcendental enclosure, coverage proof, or
certificate check.  The same CUDA source successfully compiled to an
`sm_90` cubin with CUDA 13.0, but no H100 execution occurred.  NVIDIA lists
[273 GB/s for DGX Spark's GB10 unified memory](https://www.nvidia.com/en-sg/products/workstations/dgx-spark/)
and [3.35 TB/s for the H100 SXM](https://www.nvidia.com/en-us/data-center/h100/).
That approximately 12.27x advertised-bandwidth ratio is recorded only as a
roofline input; it is not applied as a runtime multiplier.

## Recorded full external timings

These are recorded or historical timings exposed by the benchmark report,
not fresh measurements of every campaign on every machine:

| Atom | Recorded external time | Exact scope and boundary |
| --- | ---: | --- |
| `ch25-a7-boundary` | 1.56 s | SparkInterval full 16,191-leaf FLINT/Arb replay on the GB10 development host; external analytic computation, not Lean semantics |
| `platt-head-2e4` | 123.79--124.14 s | FLINT isolation/count replay; upper end includes a 0.35 s LMFDB fold; completeness bridge remains |
| `cdem-table-abel` | about 86.8 s producer + 45.85 s independent chunk replay | Reviewed-source five-billion-step eight-thread producer using about 20 GB, followed by all 1,000 chunks under the separate bounded-memory implementation; both remain external computation |
| `ramare-zuniga-lemma-6-2` | Legacy report: 9,173.397 s; current exact bounded medians: 1.004--1.037 s producer and 0.897--0.922 s one-thread replay per million rows | The legacy complete report uses a NumPy/libm error model and is not accepted by the current exact route. The current numbers are three-repeat low/terminal GB10 component samples, not a complete run, H100 calibration, or atom evidence |

## H100 planning ranges

No number in this section is an H100 measurement.  The ranges are explicit
engineering estimates from the campaign-specific projection modules and
`tg_verifier/azure_production_sizing.py`; they remain broad until target-SKU
calibration and source execution exist.  H100 SXM's advertised memory
bandwidth and GB10's advertised bandwidth are only roofline inputs.  Their
ratio is not a runtime multiplier because integer division, sieving,
divergence, host work, memory capacity, reduction, and I/O differ.

| Atom | Development-server status | One-H100 planning status |
| --- | --- | --- |
| `ch25-a7-boundary` | Measured SparkInterval leaf replay: 1.56 s | GPU work is unnecessary; the missing task is the analytic Lean bridge |
| `ch25-psi-1e13` | Source-scale primesieve/CRlibm worker projects about 7.2 hours for both passes on the local 20-core host | H100 unused; roughly 0.5--2 hours across eight 40-core NCC CPU sidecars, using two 320-worker arrays while retaining 100,000 receipts per pass |
| `platt-head-2e4` | Measured external replay: 123.79--124.14 s; resumable FLINT implementation is local | GPU work is unnecessary for this scale; the missing task is the FLINT-to-Lean bridge |
| `platt-trudgian-rh-3e12` | Native count-only FLINT Platt campaign measured at 91.38 zeros/s/process at the actual source index; 37.58M process-hours, or 13.4 ideal years on 320 processes | The H100 is unused. Eight NCC nodes cost about `$6.56M` PAYG / `$1.33M` Spot at the recorded rates under a 1:1 local-to-Genoa throughput transfer; PT21's reported 7.5M core-hours is the more optimistic algorithmic reference |
| `helfgott-prop-12-2-4` | C++ MPFR/GMP source worker projects roughly 61--73 single-core hours per replay across all 3,389,047,618 q-ranks; the production band is 105.6--640 core-hours per replay | H100 unused for final arithmetic; four 96-core DC96as_v6 jobs run all 12,930 logical leaves twice in a conservative 0.55--3.34 compute-hour band before Azure overhead |
| `cdem-squarefree` | Same physical Hurst campaign as Mertens and both little-Mertens atoms; the CPU two-pass route retains its broad 2--22 day estimate | The exact eight-worker affine alternative uses equal `1,249,875,000,000,000`-row partitions. The current `191.737 ms`/100M-row GB10 measurement gives `665.687` equal-GB10 hours; an unmeasured `12.3x` H100 factor gives `54.121` arithmetic-only terminal-stage hours, `432.967` node-hours, and about `$3,022.11` PAYG / `$614.40` Spot. It excludes the CPU prefix/handoff and is not a complete campaign ETA, H100 evidence, or production-ready |
| `cdem-table-abel` | Measured full producer about 86.8 s; independent all-chunk replay 45.85 s | 30--180 s estimated for a GPU producer; CPU production plus independent replay is already practical |
| `mertens-hurst` | Source-scale Hurst segmented-Möbius CPU worker/two-pass supervisor and exact eight-worker affine alternative are implemented | CPU route: broad 2--22 day eight-NCC estimate. Affine alternative: `54.121` arithmetic-only terminal-stage hours under the explicitly unmeasured `12.3x` GB10-to-H100 sensitivity. The CPU prefix/handoff is excluded; no complete campaign ETA, target-H100 measurement, or source run exists. One eventual run supplies squarefree and both little-Mertens atoms |
| `ramare-zuniga-lemma-6-2` | Exact low/terminal GB10 samples linearly project 5.85--6.05 hours for the serial producer and 5.23--5.38 one-thread hours for the mandatory replay; the older 9,173.397 s complete report is libm-based and not admitted by this route | One fresh serial-chain NCC H100 job is implemented. Its 1--8 node-hour band is uncalibrated, has a parallelism cap of one, and awaits the target-SKU pilot |
| `helfgott-platt-theorem-4-1` | Exact base and optimized historical binary plans have 65,536 leaves; the optimized source is independently pinned, and 492,700 native-ladder ranges are cluster-wired | The optimized 20-billion-even GB10 sample transfers to `8192.223` hours (`341.343` days) on eight equal GB10 GPUs plus about 12,700 aggregate ladder CPU core-hours. No H100 calibration or full run has occurred |
| `platt-dirichlet-theorem-7-1` | Exact 29.6-billion-character scheduler and rigorous unscaled Arb fallback; persistent large-q composition/FFT/completed-L streaming, scalable root artifacts, fused directed CUDA batches, a fully replayed 96-MB finite-recovery seed table, an authenticated 125-GiB t-major cache contract with replay repacking and deterministic scheduling, a bounded cache-range-to-resident CUDA integration, factored-v3 certified small-q disk arithmetic, an exact parity-bound semantic sign/ambiguity reducer, and its post-DFT device-side `TGDBSPK1` classifier are implemented. `TGDBSPK1` remains explicitly small-q; the large-q path keeps its distinct compact reducer identity. The source-faithful open-strip Lean contract and closed CPU finalizer require complete even/odd source evidence; no full materializer or source run exists | The current seeded fused large-q path measures 19.42 million values/s on GB10, giving a 58.5--116.9-hour unmeasured eight-H100 arithmetic sensitivity at an assumed 10--5x uplift. The unique lattice cache is 125 GiB and its bounded range feed has run through the resident CUDA worker, but the cache is not populated and no exact source phase or source-scale H100 measurement exists. Small-q v3 has a 2.460-TB split input, a 129.859-GB time-tail control, and a 1.182-TB packed sign artifact; 226.996 TB is the full-disk transfer of host mode, not a mandatory device-mode transfer. Only a local full-span synthetic `q=5460` GB10 differential run has measured the device path, at a 125.24-fold transfer reduction with byte-identical host/device payloads and compact states. The phase is nonterminal, not source-wide wired or H100-calibrated, and supplies no DFT containment/semantic replay, zero/multiplicity evidence, or Turing closure. Source-scale reducer timing, source-wide enclosure usefulness, uniform interpolation, exception refinement, and the missing theorem-level corrected reflected Turing bridge prevent a full-range atom estimate |
| `platt-little-mertens-2-11` | Logical alias of the shared Hurst four-residual campaign; no separate computation | Replay the shared certificate; do not add a GPU campaign or separate ETA |
| `platt-little-mertens-stronger` | Logical alias of the same shared campaign; exceptional endpoint retained | Replay the shared certificate; do not add a GPU campaign or separate ETA |

Generate the current machine-readable timing report, including a bounded ψ
calibration, with:

```bash
python3 tools/benchmark_tg_verifiers.py \
  --no-gpu \
  --psi-limit 100000 \
  --pretty
```

If the exact-integer planning microbenchmark has been built, omit `--no-gpu`
or pass `--gpu-executable`.  That kernel measures a generic exact work-item
loop and validates its endpoint against the host; it is **not** a Möbius
sieve, zeta evaluator, interval checker, or certificate verification.

## What counts as completion

An atom can be retired only when the theorem's actual live proposition is
derived without that atom.  For a computational route, a reviewable completion
normally needs all of the following:

1. A source-shaped specification with every range endpoint, strictness
   convention, multiplicity convention, and real-to-integer reduction explicit.
2. A deterministic producer using exact arithmetic or rigorously directed
   enclosures, with no unchecked floating-point shortcut.
3. Gap-free coverage evidence, canonical chunk input/output states, digests,
   and failure-closed resource and parsing limits.
4. An independent checker that proves chunk composition and the final exact
   inequality rather than trusting a `PASS` string.
5. A Lean theorem connecting the checker's integers, intervals, analytic
   functions, counts, and multiplicities to the definitions used by the live
   consumer.
6. A fresh `#print axioms` showing that the old atom is absent from
   `Math.Problems.TernaryGoldbach.ternary_goldbach`.

SparkInterval's accepted-run boundary may identify a particular registered
execution, but it cannot replace item 5.  Physical-execution provenance and
mathematical soundness remain separate obligations.
