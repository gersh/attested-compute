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
| `ch25-psi-1e13` | A bounded-memory exact reference recomputes every prime power, rational directed `log` enclosure, endpoint inequality, and hash-linked state; the measured bounded run reaches `10^6`. No full artifact exists. | The literal Python route is multi-year; an optimized exact CPU/GPU producer is the credible next step. | Complete the run through `10^13`, retain authenticated states and a final receipt, and prove that the event stream realizes Lean's `psi`. |
| `platt-head-2e4` | A retained FLINT summary, a fresh FLINT replay, an independently downloaded LMFDB fold, and an ordinary-kernel reciprocal fold exist. The SparkInterval checker pins the exact summary bytes/configuration and checks stored rational relationships, but not the ordinate-digest preimage or FLINT semantics. | Best current full-zeta pilot; 22,492 brackets are small enough to iterate on. | Hardy-Z endpoint realization, multiplicity-aware Turing count, and a proof that committed cells biject with all zero slots through height 20,000. |
| `platt-trudgian-rh-3e12` | Paper citation only; the zero database, interval source, Turing logs, and run output are not local. | Blocked on source artifacts and a production-grade zero verifier. | The missing database/logs, or a new amortized Hardy-Z/Riemann-Siegel and Turing-count campaign through `3000175332800`. |
| `helfgott-prop-12-2-4` | Exact 3,389,047,618-row `q` scheduling and structural hash chaining are implemented. A bounded directed-rational producer and stronger chunk replay now recompute source endpoints, exact `G_q(k)`, and every final margin without native-float decisions; the representative `q=6469693230` row checks all 136 conservative `k` values. | The formula evaluator is no longer the blocker; next optimize the bounded chunk producer and measure representative `q` blocks. | Complete all 3,389,047,618 `q` rows and their `(q,k)` windows, retain the full authenticated chain, and prove a Lean realization theorem for the rational evaluator and its theorem-backed constant intervals. |
| `cdem-squarefree` | Exact reference checker is retained through 550,000. The exact CUDA Möbius producer has pinned root known answers through 450,000, independent per-row CPU replay, exact real-endpoint comparisons, and hash-linked `Q` states. | Naively visiting every unit interval through `10^16` remains prohibitive; the new producer is infrastructure, not compression. | An authenticated complete compressed chain or a proved compressed squarefree argument, plus its Lean bridge. |
| `cdem-table-abel` | The supervisor captures, hash-pins, and compiles the exact reviewed C++ source plus its SHA-256 header dependency, checks an independent small recurrence, and runs the complete five-billion-step producer in about 87 s. A separately reviewed Eratosthenes/binary-search/serial implementation independently replayed all 1,000 exact chunks in 45.85 s with at most 20 MB of principal chunk storage per worker. | Complete external production and independent bounded-memory replay are implemented. | A Lean theorem realizing the finite recurrence and a kernel-checkable certificate bridge; the reviewed C++ source/header set and selected compiler/runtime remain external trust until then. |
| `mertens-hurst` | Exact-integer Python sample through 2,300,000. The exact CUDA Möbius producer has pinned root known answers through 450,000, independent per-row CPU replay, the squared `571/1000` check, and hash-linked `M` states. | Naive enumeration through `10^16` remains prohibitive; no Hurst-style compression or artifact is local. | Hurst's sublinear/block artifacts or a comparable compressed exact algorithm and state-chain checker. |
| `ramare-zuniga-lemma-6-2` | The retained 21-billion report relies on a stated libm model. The exact Python reference recomputes complete hash-linked transitions. A bounded CUDA producer now reproduces its scale-2^32 log, coefficient, blocked prefix, envelope, full-factor digest, and canonical chunk hash or rejects; arbitrary-precision replay passes across partitions and at the retained worst-index probe, and the blocked transition matches the retained serial reference. | Add exact fallback for Q64-ambiguous rows and scalable full-factor digest production, then run all 21 billion endpoints. | A complete replayed chain and Lean realization of the R2Star recurrence, log, and Euler gamma. |
| `helfgott-platt-theorem-4-1` | Explicit local Goldbach witnesses through 200,000; the paper reports deletion of the full per-range files. | Blocked on reconstruction of the prime-ladder corpus. | Complete ordered ladder, gap-coverage proof, and Proth/ECPP primality certificates for roughly 492,700 ladder intervals. |
| `platt-dirichlet-theorem-7-1` | Exact source statement, but no local character database, zero database, computation source, or logs. | Blocked on source artifacts and algorithm. | Canonical primitive-character enumeration, completed-L interval evaluation, and multiplicity-aware Turing counts in every conductor/parity range. |
| `platt-little-mertens-2-11` | Segmented numerical loop and bounded exact reference; no directed full run or authenticated state chain. | A full multi-GPU campaign through `10^12` appears plausible after the target implementation exists. | Exact fixed-point Möbius stream, all real-step intervals, composable chunk states, full run, and Lean checking. |
| `platt-little-mertens-stronger` | Same bounded exact reference and incomplete production evidence. | A full single-H100 campaign through `7727068587` appears plausible after implementation. | Exact directed stream, left-limit endpoint checks, composable states, full run, and Lean checking. |

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

The same streaming code accepts `--limit 10000000000000`, but the current
Python rational-log implementation would take years.  “Full-capable” here
describes coverage and bounded memory, not practical runtime or Lean discharge.

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

An independent LMFDB-data route can check official file hashes, decode the
published ordinate stream, recompute the reciprocal fold, and compare cells:

```bash
"$CLAUDE_MATH_ROOT/ext/ch25_certificates/.venv/bin/python" \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/scripts/verify_lmfdb_head.py" \
  --check \
  "$CLAUDE_MATH_ROOT/ext/ch25_certificates/certificates/ch25_prop77_lmfdb.json"
```

Use `--offline` after the two LMFDB files have been cached.  Neither route by
itself replays Platt's isolation proof or its multiplicity-aware Turing
completeness argument.  A list of 22,491 plausible ordinates is not a proof
that no zero is missing, duplicated, multiple, or off the critical line.  The
lightweight SparkInterval receipt pins the retained summary bytes and the
stored ordinate digest, but does not possess the ordinate preimage and thus
does not recompute that digest's analytic content.

### `platt-trudgian-rh-3e12`

Lean declaration:

```text
AnalyticNT.ChebyshevPsi.finite_check_platt_trudgian_rh_zeta_3e12
```

Claim: every nontrivial zeta zero with
`0 < Im(s) <= 3000175332800` lies on `Re(s)=1/2`.

No local command can independently replay this claim today.  The paper is a
citation, not a substitute for the missing zero database, interval code,
Turing logs, and output.  Offline `sm_90` compilation in this repository does
not change that status.

### `platt-dirichlet-theorem-7-1`

Lean declaration:

```text
MathExtras.Helfgott.MajorArcsStart.platt_theorem_7_1_dirichlet_verification_source
```

Claim: every primitive character of conductor `q <= 400000` satisfies the
parity-dependent Platt zero-height ranges.  This requires character-specific
completed-L evaluations and completeness counts, not reuse of an ordinary
Riemann-zeta zero table.  No local production artifact or target kernel exists.

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
and assurance boundaries.  A complete verification still needs an optimized,
authenticated full campaign and a Lean realization theorem.

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
real unit interval.  Non-root segments require both incoming prefix states
and the previous receipt digest. `tg_verifier.mobius_cuda` structurally
verifies and composes those summaries; save each JSON receipt and run

```bash
python3 tools/tg_verify.py --pretty verify-mobius-receipts \
  receipt-000000.json receipt-000001.json
```

The chain checker enforces the runner's 100-million-row receipt cap, one
executable digest throughout the chain, nonzero row/executable digests,
gap-free state composition, and duplicate-key-free JSON. It does **not** rerun
the rows, authenticate the self-reported executable execution, or externally
anchor the final digest. Its classification therefore says
`not_execution_authenticated`, and neither it nor the producer claims to
prove the external atom.

Do not extrapolate a bounded receipt to `10^16`.  A fresh 10-million-row GB10
run took 54.29 ms in the kernel but 3.706 s in independent CPU replay and exact
endpoint checks.  Linear extrapolation is invalid at the source scale; even
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
sublinear decomposition.

### `ramare-zuniga-lemma-6-2`

Lean declaration:

```text
MathExtras.RamareMertens2025.ramare_zuniga_2024_lemma_6_2_source
```

Claim: for every real `3 <= X <= 21000000000`,
`|R2Star(X)| <= 1.93*sqrt(X)*log(X)`.

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

Exact `Fraction` sampling checks both predicates but is intentionally a slow
reference implementation.  A production checker should use directed
fixed-point accumulators, prove the relationship between integer endpoints
and all real `x`, and emit hash-linked chunk states.  The stronger range is a
reasonable first full GPU target; the `10^12` range is a larger multi-GPU
campaign.

## Goldbach finite-range atom

### `helfgott-platt-theorem-4-1`

Lean declaration:

```text
Math.Problems.TernaryGoldbach.helfgott_platt_theorem_4_1_source
```

Claim: every odd `n` from 7 through
`8875694145621773516800000000000` is a sum of three primes.

Checking explicit witnesses through 200,000 is only a bounded sample.  The
published finite verification used a prime ladder, but the paper reports that
the full per-range files were deleted.  A replacement certificate must include
an ordered ladder, proof that adjacent ladder entries cover every required
odd target under the reduction used in the paper, and independently checkable
Proth or ECPP primality certificates.  A list of probable primes or scattered
Goldbach witnesses is not enough.

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
| `platt-head-2e4` | Measured external replay: 123.79--124.14 s | Not estimated: no Hardy-Z/Turing target implementation |
| `platt-trudgian-rh-3e12` | Blocked on PT21 database and verifier | Blocked; an offline `sm_90` build is not a zero benchmark |
| `helfgott-prop-12-2-4` | Bounded exact rational producer implemented; representative 136-pair row takes about 0.15 s, but this is not a useful extrapolation to 3,389,047,618 heterogeneous `q` rows | Not estimated: no target kernel or representative block measurement |
| `cdem-squarefree` | Naive lower bound: 10,000,000 s (about 116 days) even at `10^9` intervals/s | Naive lower bound: 1,000,000 s (about 11.6 days) even at `10^10` intervals/s; compression required |
| `cdem-table-abel` | Measured full producer about 86.8 s; independent all-chunk replay 45.85 s | 30--180 s estimated for a GPU producer; CPU production plus independent replay is already practical |
| `mertens-hurst` | Naive lower bound: 10,000,000 s | Naive lower bound: 1,000,000 s; Hurst-style compression required |
| `ramare-zuniga-lemma-6-2` | Retained full-run time: 9,173.397 s | 300--2,700 s for a one-H100 exact segmented implementation |
| `helfgott-platt-theorem-4-1` | Blocked; historical campaign reported around 40,000 core-hours | Not estimated: ladder corpus and checker absent |
| `platt-dirichlet-theorem-7-1` | Blocked: database and algorithm absent | Blocked: no completed-L/Turing kernel |
| `platt-little-mertens-2-11` | 3--14 days after exact segmented implementation | 12--72 hours after target implementation |
| `platt-little-mertens-stronger` | 30 minutes--3 hours after exact segmented implementation | 5--30 minutes after target implementation |

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
