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

Run the exact bounded arithmetic references separately:

```bash
python3 tools/tg_verify.py --pretty sample-arithmetic --limit 20000
python3 tools/tg_verify.py --pretty verify-psi-range --limit 100000
python3 tools/tg_verify.py --pretty verify-r2star-range --limit 100000
python3 tools/tg_verify.py --pretty prop1224-scheduler
python3 tools/tg_verify.py --pretty verify-prop1224-sample \
  --q 6469693230 --bits 96 --log-terms 32 --max-pairs 1000
python3 tools/benchmark_tg_verifiers.py \
  --no-gpu \
  --mobius-limit 1000000 \
  --exact-fraction-limit 20000 \
  --pretty
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
| `ch25-a7-boundary` | The pinned full replay recomputes all 16,191 FLINT/Arb leaf boxes, all nonvanishing guards, and both exact dyadic evidence endpoints; the local run took 1.56 s. | Complete external analytic replay is implemented. | Prove that the FLINT enclosures realize Mathlib's zeta and zeta-derivative definitions. |
| `ch25-psi-1e13` | A bounded-memory exact reference recomputes every prime power, rational directed `log` enclosure, and endpoint inequality. A source-hash-bound supervisor now retains compact event commitments, atomically resumes the gap-free directed state/hash chain through the literal `10^13` endpoint, and can independently regenerate selected or all chunks. | The full Python campaign is runnable in form but remains computationally prohibitive; optimize the producer before attempting it. | Complete and independently replay the run through `10^13`, then prove that the event stream realizes Lean's `psi`. |
| `platt-head-2e4` | A resumable pinned-FLINT campaign recomputes exact `N(20000)=22491`, all 22,492 indexed critical-line isolations, disjointness, cutoff bracketing, multiplicity completeness, and the directed reciprocal bound. Its compact chunks are hash-linked and independently replayable. | Complete external analytic replay is implemented; the retained historical summary and LMFDB fold remain useful independent comparisons. | Prove that FLINT's zero/count routines realize Mathlib's zeta zeros and analytic multiplicities, then check the compact campaign in Lean. |
| `platt-trudgian-rh-3e12` | The same bounded-memory campaign implementation pins source height `3000175332800` and source count `12363153437138`, checks a fresh exact `zeta_nzeros` result, and can isolate/resume/finalize every indexed batch. No source-height campaign has been run. | Range-complete implementation exists, but naively revisiting more than twelve trillion zeros is computationally enormous and needs serious amortization/scale-out. | A completed source-height chain, practical optimized production, and the same FLINT-to-Lean analytic realization bridge. |
| `helfgott-prop-12-2-4` | A literal full-source supervisor schedules all 3,389,047,618 admissible `q` rows, streams the exceptional 23,207,009-value `q=1` window with directed fixed-point `G` bounds, atomically resumes a hash-linked chain, and independently regenerates each transition. Bounded and representative-row tests pass. | Exact and full-domain-capable, but the Python implementation is prohibitively slow; optimize before attempting the full run. | Complete and independently replay the source campaign, then prove a Lean realization theorem for the rational evaluator and its theorem-backed constant intervals. |
| `cdem-squarefree` | Exact reference checker is retained through 550,000. The exact CUDA Möbius producer has pinned root known answers through 450,000, independent per-row CPU replay, exact real-endpoint comparisons, and hash-linked `Q` states. | Naively visiting every unit interval through `10^16` remains prohibitive; the new producer is infrastructure, not compression. | An authenticated complete compressed chain or a proved compressed squarefree argument, plus its Lean bridge. |
| `cdem-table-abel` | The supervisor captures, hash-pins, and compiles the exact reviewed C++ source plus its SHA-256 header dependency, checks an independent small recurrence, and runs the complete five-billion-step producer in about 87 s. A separately reviewed Eratosthenes/binary-search/serial implementation independently replayed all 1,000 exact chunks in 45.85 s with at most 20 MB of principal chunk storage per worker. | Complete external production and independent bounded-memory replay are implemented. | A Lean theorem realizing the finite recurrence and a kernel-checkable certificate bridge; the reviewed C++ source/header set and selected compiler/runtime remain external trust until then. |
| `mertens-hurst` | Exact-integer Python sample through 2,300,000. The exact CUDA Möbius producer has pinned root known answers through 450,000, independent per-row CPU replay, the squared `571/1000` check, and hash-linked `M` states. | Naive enumeration through `10^16` remains prohibitive; no Hurst-style compression or artifact is local. | Hurst's sublinear/block artifacts or a comparable compressed exact algorithm and state-chain checker. |
| `ramare-zuniga-lemma-6-2` | The retained 21-billion report relies on a stated libm model. The exact Python reference recomputes complete hash-linked transitions. A CUDA producer reproduces its scale-2^32 log, coefficient, blocked prefix, envelope, full-factor digest, and canonical chunk hash; rare Q64-ambiguous rows use an arbitrary-precision rational host fallback, while an exact segmented host sieve commits every factor. A full-source supervisor captures the runner and atomically resumes the verified gap-free state/hash prefix. | The full engine and scheduler are implemented; benchmark and run all 21 billion endpoints. | A complete replayed chain and Lean realization of the R2Star recurrence, log, and Euler gamma. |
| `helfgott-platt-theorem-4-1` | A literal source reconstruction fixes all 492,700 ranges, exactly checks compact Proth/Pocklington ladder certificates, uses a 256-grid bounded built-in producer with an unbounded certificate-producing fallback, and separately replays deterministic prime pairs for every even through `4e18`. Bounded tests pass; no full artifact exists. | End-to-end and resumable in form, but the naive binary-Goldbach scan is computationally astronomical; a source-grade compressed/imported prerequisite is needed in practice. | Complete both external campaigns and prove their interval-covering reduction in Lean. |
| `platt-dirichlet-theorem-7-1` | The exact CRT/Conrey scheduler covers 29,565,923,837 primitive characters for `q=2..400000`. A pinned-FLINT reference backend replaces a numeric Turing heuristic with a rigorous Arb argument-principle count and strict Hardy-Z brackets; `q=1` is composed from the stronger zeta-3e12 campaign. Small `q=3,4,5` runs pass. | Full-source and resumable in form, but the direct contour method is astronomical and producer/checker share one implementation. The strict `sm_90` upstream GRH evaluator remains a moderate-height POC, not the missing Platt-scale lattice/FFT backend. | Complete the source run with a practical algorithm, independently check it, capture the runtime closure, and prove the completed-L/Hardy-Z/count realization in Lean. |
| `platt-little-mertens-2-11` | Full-range-capable exact CUDA/CPU directed stream, real-slab checks, hash-linked state, and resumable supervisor; bounded tests only. | The implemented single-GPU campaign accepts all rows through `10^12`; no complete run is retained. | Full campaign receipts, independent execution review/attestation as desired, and a Lean realization/checker. |
| `platt-little-mertens-stronger` | The same implementation preserves the exceptional closed endpoint `7727068587`; bounded tests and resume tests pass. | The implemented shorter campaign requires 78 maximum-size segments. | Full campaign receipts and a Lean realization/checker. |

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

The resumable full-source wrapper keeps compact event digests rather than
retaining the enormous prime-power stream:

```bash
python3 tools/tg_psi_campaign.py run /durable/psi-1e13
python3 tools/tg_psi_campaign.py verify /durable/psi-1e13
python3 tools/tg_psi_campaign.py replay /durable/psi-1e13 --max-chunks 1
```

Use `run --max-chunks N` for a clean bounded stop; the identical command later
resumes from the verified prefix. The same engine reaches the literal
`10^13` endpoint without a sample mode, but the current Python rational-log
implementation would take years. “Full-capable” here describes exact coverage
and bounded retained state, not practical runtime or Lean discharge.

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

### `platt-trudgian-rh-3e12`

Lean declaration:

```text
AnalyticNT.ChebyshevPsi.finite_check_platt_trudgian_rh_zeta_3e12
```

Claim: every nontrivial zeta zero with
`0 < Im(s) <= 3000175332800` lies on `Re(s)=1/2`.

The [resumable zeta-zero campaign](TG_ZETA_ZERO_CAMPAIGN.md) provides the same
exact count plus indexed-isolation logic at this height:

```bash
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty init \
  build/tg/zeta-rh-3000175332800 --profile platt-trudgian-rh-3e12 \
  --batch-size 1000000
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty run \
  build/tg/zeta-rh-3000175332800 --max-chunks 10
```

Initialization must freshly obtain the exact source count
`N(3000175332800)=12363153437138`. Repeating `run` eventually covers all
`N+1` indices and `finalize` proves the external finite-height claim. The
implementation is bounded-memory and resumable, but this literal campaign is
still extraordinarily expensive; no source-height completion is claimed.

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

The single source command composes `q=1` from a completed stronger
`platt-trudgian-rh-3e12` campaign and then resumes all `q>=2` characters:

```bash
.venv-tg-flint/bin/python tools/tg_dirichlet_campaign.py source \
  build/tg/platt-dirichlet-7-1-source \
  --q1-zeta-final build/tg/zeta-rh-3000175332800/final.json
```

This is a literal unscaled reference, not a practical replacement for
Platt's lattice/FFT and Turing implementation. The H100-bound upstream GRH
evaluator is useful at moderate height but its direct sums lose resolution at
the source ordinates.

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

The literal source supervisor adds bounded-memory handling of the much larger
`q=1` window, immutable parameters, atomic resume, and independent arithmetic
replay:

```bash
python3 tools/tg_prop1224_campaign.py run /durable/prop1224
python3 tools/tg_prop1224_campaign.py verify /durable/prop1224
python3 tools/tg_prop1224_campaign.py replay /durable/prop1224
```

Omitting `--max-chunks` fixes the endpoint at the full source sentinel; a
bounded stop remains visibly incomplete. The implementation is exact but far
too slow for a practical full Python run. See
[`PROP1224_FULL_CAMPAIGN.md`](PROP1224_FULL_CAMPAIGN.md). A completed external
campaign would still need a Lean realization theorem before discharging the
atom.

### `cdem-squarefree`

Lean declaration:

```text
MathExtras.CohenDressElMarraki.reproducibleSquarefree_verifier_output
```

Claim: the two strict-real squarefree-count error bounds hold through `10^16`
after thresholds 9,243 and 438,429.  The CPU sampler checks exact rational or
integer inequalities only through its requested limit:

```bash
python3 tools/tg_verify.py --pretty sample-arithmetic --limit 20000
```

The catalog records separate retained evidence through 550,000; the command
above is the intentionally smaller exact reference used for routine review.
The reusable CUDA producer adds exact Möbius records, independent CPU replay,
hash-linked `M` and `Q` state transitions, and fixed-width exact comparisons
for both real endpoints:

```bash
cmake -S . -B build/dgx-spark -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/dgx-spark --target sparkinterval-tg-mobius-segment
./build/dgx-spark/sparkinterval-tg-mobius-segment \
  --lower 1 --count 450000
```

Its coarse rational interval for `6/pi^2` is checked against the tighter
Machin enclosure by `tests/test_tg_mobius_cuda.py`.  The runner checks the
integer endpoint and the left limit before each jump; convexity supplies the
real unit interval. Non-root segments require the incoming Mertens,
squarefree, and directed little-Mertens prefix states plus the previous
receipt digest. `tg_verifier.mobius_cuda` structurally verifies and composes
those summaries. The full-range-capable supervisor can run or resume the
literal scan with

```bash
python3 tools/tg_mobius_campaign.py run \
  --runner build/dgx-spark/sparkinterval-tg-mobius-segment \
  --output-dir /durable/path/cdem-squarefree \
  --target squarefree --segment-count 100000000 \
  --allow-other-device
```

The chain checker enforces the runner's 100-million-row receipt cap, one
executable digest throughout the chain, nonzero row/executable digests,
gap-free state composition, and duplicate-key-free JSON. It does **not** rerun
the rows, authenticate the self-reported executable execution, or externally
anchor the final digest. Its classification therefore says
`not_execution_authenticated`, and neither it nor the producer claims to
prove the external atom.

Do not extrapolate a bounded receipt to `10^16`.  A fresh v2 10-million-row
GB10 run took 40.26 ms in the kernel, 3.717 s in independent CPU replay plus
all exact bounds, and 4.32 s wall time. Linear extrapolation is invalid at the source scale; even
the small-run kernel rate alone would need about 1.7 years, and the independent
checker rate would need well over a century.  A production solution needs a
compressed argument, not merely more GPU cores.

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

Independently replay the complete chunk manifest with the second reviewed
implementation:

```bash
python3 tools/tg_verify.py --pretty replay-cdem-abel-chunks \
  build/tg/cdem-abel-full.txt --workers 8
```

The production transcript exposes 1,000 exact five-million-row chunks. The
replayer uses a different Möbius sieve, exact binary search for every directed
square-root weight, a serial recurrence scan, and only chunk-sized storage.
The full local replay took 45.85 s; its principal storage bound was 20 MB per
worker and 160 MB for eight workers. It reproduced the complete manifest and
final aggregates. This removes dependence on one opaque 20 GB process, but it
still trusts reviewed external C++ source, the identified compiler/runtime,
and the missing Lean theorem connecting the recurrence to the formal claim.

### `mertens-hurst`

Lean declaration:

```text
MathExtras.EffectiveMertensDecay.mertensM_hurst_sqrt_source
```

Claim: for every real `33 <= x <= 10^16`,
`|M(x)| <= (571/1000)*sqrt(x)`.  The exact local sample is a useful regression
test, but reaching 2,300,000 does not validate the cited upper endpoint.  A
credible completion route needs Hurst's block/sublinear artifacts or a newly
proved comparable decomposition.

The same `sparkinterval-tg-mobius-segment` runner checks the literal exact
integer predicate

```text
571^2*n - 1000^2*M(n)^2 >= 0.
```

Because `M(x)=M(floor(x))` and square root is increasing, the integer check at
`n` covers the real slab `[n,n+1)`.  A chain rooted at `n=1` makes later
incoming states meaningful; an isolated non-root receipt is explicitly
conditional.  The 10-million-row GB10 run found the minimum squared slack
`882159` at `n=199` and no failure, but is only one-billionth of the required
range.  Neither this linear scan nor an H100 rebuild supplies Hurst's missing
sublinear decomposition. It is nevertheless wired as a guarded, resumable
full-domain linear campaign:

```bash
python3 tools/tg_mobius_campaign.py run \
  --runner build/dgx-spark/sparkinterval-tg-mobius-segment \
  --output-dir /durable/path/mertens-hurst \
  --target hurst --segment-count 100000000 \
  --allow-other-device
```

At `10^16` this is a theoretical fallback, not a practical replacement for a
compressed proof. Both target modes stop on their own first-failure fields,
retain the failing receipt, and report full target completeness only after a
gap-free rooted chain reaches the exact source endpoint.

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

Exact `Fraction` sampling remains the small independent reference.  The
`sparkinterval-tg-mobius-segment` runner now adds scale-`2^96` floor/ceiling
reciprocal accumulation, checked signed-128-bit state, unsigned-256-bit
source-shaped squared comparisons at every real-slab limiting endpoint, and
hash-linked composable state.  `tools/tg_mobius_campaign.py` captures one
runner and provides atomic checkpointing, exact resume, and offline chain
validation for the full `7727068587` or `10^12` endpoint.  See
[`LITTLE_MERTENS_CUDA_CAMPAIGN.md`](LITTLE_MERTENS_CUDA_CAMPAIGN.md) for the
equations, commands, and trust boundary.  Only bounded tests have been run;
no full campaign or Lean realization is claimed.

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

The literal reconstruction now supplies both missing finite workflows:

```bash
python3 tools/tg_goldbach_campaign.py full /durable/goldbach-source \
  --general-prime-producer tools/tg_pocklington_producer.py
```

That single command fixes the paper's 492,700 ranges of width
`2^54 * 10^9`, requires ladder gaps at most `4e18`, checks the two-`2e18`
endpoint tolerances, streams exact Proth-52 or recursive Pocklington evidence,
and independently checks a prime pair for every even integer from 4 through
`4e18`. The built-in search tries 256 Pocklington factor grids before handing
off to the supplied unbounded in-repository producer. Miller--Rabin is used
only to reject unlikely candidates; acceptance comes from the exact
Pocklington checker with a fully factored factor greater than the square root.
The binary campaign uses
the deterministic 64-bit primality domain and independently regenerates every
retained witness transcript.

This is a literal correctness fallback, not a practical reproduction plan:
the row-by-row binary campaign is computationally astronomical. Its value is
to make the domain, equations, resume boundary, and certificate acceptance
executable without pretending the deleted corpus was recovered. A practical
run should import or reimplement the published compressed binary-Goldbach
method. See [`GOLDBACH_LADDER_CAMPAIGN.md`](GOLDBACH_LADDER_CAMPAIGN.md).
A list of probable primes or scattered Goldbach witnesses remains
insufficient, and no completed campaign or Lean reduction is claimed.

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
| `ramare-zuniga-lemma-6-2` | 9,173.397 s (about 2 h 32 min 53 s) | Runtime recorded in the retained 21-billion report; the current audit does not replay those steps |

## H100 planning ranges

No number in this section is an H100 measurement.  The ranges are explicit
engineering estimates from `tg_verifier/benchmark.py`; they remain broad until
a target producer and certificate format exist.  H100 SXM's advertised memory
bandwidth and GB10's advertised bandwidth are only roofline inputs.  Their
ratio is not a runtime multiplier because integer division, sieving,
divergence, host work, memory capacity, reduction, and I/O differ.

| Atom | Development-server status | One-H100 planning status |
| --- | --- | --- |
| `ch25-a7-boundary` | Measured SparkInterval leaf replay: 1.56 s | GPU work is unnecessary; the missing task is the analytic Lean bridge |
| `ch25-psi-1e13` | Current exact Python reference plus cold replay: roughly 3.8--10 years by bounded event-rate extrapolation | Not estimated: no matching segmented-sieve/fixed-log target kernel |
| `platt-head-2e4` | Measured external replay: 123.79--124.14 s; resumable FLINT implementation is local | GPU work is unnecessary for this scale; the missing task is the FLINT-to-Lean bridge |
| `platt-trudgian-rh-3e12` | Bounded-memory FLINT campaign implemented but full run is computationally enormous and unexecuted | No H100 estimate: the current indexed FLINT calls are host-side and need an amortized production design before GPU sizing |
| `helfgott-prop-12-2-4` | Literal exact Python campaign implemented; a 100-row high-`q` probe took about 1.33 s, which cannot be safely extrapolated across the heterogeneous source domain | Not estimated: no target kernel or representative production-block measurement |
| `cdem-squarefree` | Naive lower bound: 10,000,000 s (about 116 days) even at `10^9` intervals/s | Naive lower bound: 1,000,000 s (about 11.6 days) even at `10^10` intervals/s; compression required |
| `cdem-table-abel` | Measured full producer about 86.8 s; independent all-chunk replay 45.85 s | 30--180 s estimated for a GPU producer; CPU production plus independent replay is already practical |
| `mertens-hurst` | Naive lower bound: 10,000,000 s | Naive lower bound: 1,000,000 s; Hurst-style compression required |
| `ramare-zuniga-lemma-6-2` | Retained full-run time: 9,173.397 s | 300--2,700 s for a one-H100 exact segmented implementation |
| `helfgott-platt-theorem-4-1` | Literal deterministic reconstruction implemented but the naive binary prerequisite is far beyond practical local execution; the historical source campaign reported around 40,000 core-hours | No useful H100 estimate for the present host-driven binary loop; port or import the published binary-Goldbach method before production |
| `platt-dirichlet-theorem-7-1` | Exact 29.6-billion-character scheduler and rigorous unscaled Arb argument-principle campaign implemented; source run unexecuted | Strict `sm_90` completed-L POC builds and runs at moderate height; no useful full-range estimate until the lattice/FFT production algorithm is implemented |
| `platt-little-mertens-2-11` | Full-range-capable target implemented; complete run not performed | Prior planning estimate 12--72 hours on H100; benchmark the production segment size before relying on it |
| `platt-little-mertens-stronger` | Full-range-capable target implemented; complete run not performed | 78 maximum-size segments; prior planning estimate 5--30 minutes, not yet measured end to end |

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
