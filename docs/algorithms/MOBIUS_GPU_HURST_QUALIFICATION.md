# Möbius GPU/Hurst optimization and qualification

This note describes the bounded CUDA implementation in
`gpu/src/tg_mobius_segment_kernel.cu`, its independent host oracle in
`gpu/src/tg_mobius_segment_runner.cpp`, and the qualification harness
`tools/tg_mobius_hurst_qualification.py`.

The result is an optimized, exactly checked implementation for bounded shards.
It is **not** a completed source-range computation, an execution attestation,
a CUDA/C++ compiler-refinement proof, or a proof of any Lean external atom.
Every report emitted by the runner and harness keeps those capabilities
explicitly false.

## Mathematical state

For every integer `n` in a half-open segment, the sieve computes

- `mu(n)`;
- the local Mertens increment `mu(n)`;
- the local squarefree increment `mu(n)^2`; and
- below `10^12`, a directed Q96 enclosure of `mu(n)/n`.

Above `10^12`, both little-Mertens deltas are exactly zero, as in the pinned
Hurst implementation.  One physical stream therefore retains the four
coordinates needed by the Hurst, CDEM-squarefree, and two little-Mertens
campaigns without pretending that one bounded shard proves any of them.

The source-shaped split is exact:

```text
CPU: [1, 10^12 + 1)       M, Q, and both directed little-Mertens coordinates
GPU: [10^12 + 1, 10^16+1) M and Q; both little-Mertens deltas are zero
```

Ordered `mu+1` block commitments and four-coordinate deltas remain available
for audit and composition across the split.

## Fused Möbius support

The optimized kernel uses one guarded 64-bit word per row:

```text
bits  0..53  product of distinct prime divisors
bits 54..58  number of distinct prime divisors
bit      59  divisible by a prime square
bits 60..62  reserved; must remain zero
bit      63  poison
```

For `n <= 10^16`, the distinct-prime product divides `n`, hence is below
`2^54`.  At most thirteen distinct primes can divide such an `n` because the
product of the first thirteen primes is `304250263527210`, while the product
of the first fourteen is `13082761331670030 > 10^16`.

The retained qualification/reference update uses one compare-and-swap to
multiply the product, increment the count, and OR the result of its inline
`n % p^2` test. Production instead separates the product/count CAS events
from a later sparse `p^2` strike pass, as described below. Both paths keep
the same product, count, reserved-bit, and poison guards. Finalization maps
poison to the impossible Möbius sentinel `2`, which the independent CPU
comparison rejects.

`SparkInterval/TernaryGoldbach/MobiusFusedSupport.lean` proves the
architecture-independent packing, unpacking, field bounds, injectivity,
update commutativity, and 32-bit prefix-width facts.  It does not prove that a
particular CUDA CAS execution implements the model.

`SparkInterval/TernaryGoldbach/MobiusFusedFinalization.lean` now closes the
next mathematical layer. It proves that conditional prime events commute,
that the folded product, distinct-count, and squareful fields are exactly the
corresponding filtered-roster operations, and that the native zero/parity
finalizer equals Mathlib's `ArithmeticFunction.moebius`. The theorem is
source-shaped: it consumes explicit roster facts for divisor-product
coverage, exact distinct-factor count, the multiplicity-preserving square
event, and the residual rule only on the squarefree branch. In particular it
accepts live squareful rows whose residual is composite (for example
`72 / 6 = 12`) rather than imposing a false one-or-prime condition on a branch
which finalizes to zero.

This removes the abstract finalizer and event-ordering step from the native
trust gap. The remaining refinement must still prove that the authenticated
prime roster and the physical CUDA event/CUB execution realize those
explicit roster facts and folds.

`SparkInterval/TernaryGoldbach/HurstGpuRowRealization.lean` then projects
that exact finalizer result into the primitive Hurst source semantics. Above
the `10^12` little-Mertens split, the emitted row is exactly the Möbius value,
its zero/nonzero squarefree indicator, and two zero Q96 increments. Thus the
remaining GPU-side proof boundary is a concrete machine-to-roster/output
refinement, not an unexpanded appeal to the Hurst source claim.

`SparkInterval/TernaryGoldbach/MobiusPrimeRosterCompleteness.lean` removes
the remaining row-by-row roster assertions. Lean proves all product, count,
residual, and square-event facts from one global contract: the authenticated
list has no duplicates, every entry is prime, and every prime through
`10^8` occurs. Since `(10^8)^2 = 10^16`, the same roster is complete for
every production row. What remains is a finite data certificate for those
three roster properties and a machine-level proof that the CUDA event stream
uses exactly those bytes.

The finite roster proof reuses
`SparkInterval/TernaryGoldbach/Sqrt218/Operational/V2/PrimeRoster.lean`.
That generic Boolean checker accepts Lucas/Pratt rows for listed primes and
nontrivial factor pairs covering every omitted value, and already proves an
exact indexed roster theorem. The small adapter in
`MobiusPrimeRosterCertificateBridge.lean` converts it to the list contract
and proves a second total Boolean equality check binds that list to the
decoded CUDA roster. This is a theorem-level route, not a claim that the
production `10^8` certificate or raw-byte decoder proof is already
materialized.

`MobiusGuardedMachine.lean` formalizes the fail-closed event loop itself.
Malformed field bounds or an invalid event produce an absorbing poison state,
and poison finalizes to sentinel `2`. Lean proves that every completed
nonpoison run equals the exact residue-seeded mathematical fold and hence,
with the checked roster, Mathlib's Möbius function. This avoids trusting
millions of row-local product or residual claims.

`MobiusPackedGuardedRefinement.lean` closes the pure packed-word arithmetic
inside the CAS loop. It models the 54-bit product mask, five-bit count,
reserved bits, division-based overflow guard, squareful bit, and absorbing
poison bit. Lean proves that the desired word computed from every
well-formed loaded word decodes to exactly one `MobiusGuardedMachine.step`:
success is the mathematical prime update and failure is poison. This
one-step result is also lifted to every serialized event list, including
absorbing poison behavior. The remaining machine boundary is narrower:
atomic-CAS linearizability, physical register/loop realization,
compiler/instruction refinement, and authenticated execution.
The strongest theorem starts from the exact modulo-900 packed seed, executes
the selected suffix events as packed words, decodes the terminal word, and
proves that any nonpoison result under a complete roster is Mathlib's Möbius
function.

`MobiusSegmentEventEnumeration.lean` closes the architecture-independent
event-roster arithmetic. For every positive roster prime, the exact native
`lower % prime` first-offset formula enumerates each divisible row in the
segment exactly once, and no other row. Together with
`MobiusDenseSchedule.lean` and `MobiusDenseVisitRealization.lean`, every
divisible row has exactly one legal block/thread/loop-iteration visit in the
proved 147-slot residue-seeded schedule, and the declared grid has enough
capacity. The remaining event gap is therefore identification of the
compiled CUDA registers and loops with these formulas, rather than an
unproved number-theoretic enumeration or schedule-partition claim.

### Production split-square schedule

The production direct-packed path no longer evaluates `n % p^2` at every
`p | n` event. Its stream order is fixed:

```text
residue-235 initialize
all distinct-factor product/count CAS kernels
all suffix-prime p^2 strike kernels
packed support to {mu, mu != 0} finalization
```

The first 200 suffix-prime square streams use one block per prime and
enumerate square-multiple ordinals with 256 threads. Every later suffix prime
uses one thread. The two prime-index intervals are disjoint. Each strike
performs only a 64-bit `atomicOr` of bit 59; it cannot clear product, count,
reserved, or poison bits. CUDA same-stream launch ordering prevents a square
strike from overlapping an earlier product/count CAS or a later finalizer.
The old inline-modulo launch remains a distinct public qualification API and
is not called by the production persistent worker.

`SparkInterval/TernaryGoldbach/MobiusSplitSquareRealization.lean` proves the
architecture-independent boundary.
`prime_sq_dvd_iff_existsUnique_squareVisit` proves that the block/thread
square schedule visits exactly the rows divisible by `p^2`, once per prime.
`splitRun_eq_inlineRun` proves that moving every square mark after all
product/count events gives exactly the retained inline result, while
`splitRun_perm` proves both phases are invariant under their concurrent event
orders. These theorems use only Lean's foundational trio. They do not prove
CUDA stream semantics, `atomicCAS`/`atomicOr` realization, or compilation.

Before any split-square divisor arithmetic, a same-stream device preflight
checks the exact `[2,3,5]` prefix, `2 <= p <= 10^8`, strict ordering, and
`p >= 7` on the suffix. A bad roster makes every initialized support word
poisonous; each kernel also checks the prime before division, remainder, or
squaring. The persistent runner authenticates the pinned host roster and
performs byte-for-byte device round-trip checks after each upload. This
closes the former raw-API `p = 0` trap without making the structural preflight
a primality or completeness proof.

`MobiusPackedCUDABitRefinement.lean`,
`MobiusPackedCUDAWidthSafety.lean`,
`MobiusCASRetryTrace.lean`, and
`MobiusPackedCUDARosterPreflight.lean` prove the exact mask/shift
expressions, nonwrapping admitted arithmetic, stuttering CAS retries with
permutation-invariant winners, and fail-closed initializer model. The
remaining boundary is pointer/list identity plus compiled CUDA atomic and
same-stream semantics.

Qualification mode transfers and compares all fused fields against the
existing 16-byte compact-support kernel.  Performance mode transfers only the
one mathematical Möbius byte per row.  The original 24-byte support path
remains a separate oracle.

### Exact 2/3/5 residue initializer

The production fused path removes the three densest event streams without
changing the support equation.  For `r = n mod 900`, where
`900 = 2^2 * 3^2 * 5^2`, a 900-entry table stores

```text
product(r)    = product of p in {2,3,5} with p | r
count(r)      = number of p in {2,3,5} with p | r
squareful(r)  = some p in {2,3,5} has p^2 | r
```

Because every `p^2` divides 900, `p | n` iff `p | r` and `p^2 | n` iff
`p^2 | r` for these three primes.  Initializing a row from this packed value
and processing the roster suffix beginning at 7 is therefore exactly the
same fold as starting at packed one and processing the full roster beginning
at 2.

`SparkInterval/TernaryGoldbach/MobiusResidue235.lean` proves both residue
divisibility equivalences, equality with the ordinary `[2,3,5]` support fold,
and preservation after appending an arbitrary suffix.  This is an
architecture-independent arithmetic proof; it does not identify the native
table bytes with the Lean function or prove CUDA execution.

The raw asynchronous CUDA API cannot inspect a device pointer without adding
a synchronization, so `[2,3,5]` is an explicit API precondition.  Both public
runners validate that exact prefix in authenticated host memory immediately
before selecting this API.  A qualification switch restores the unseeded
initializer, and a deliberate omission-of-2 test must fail at the prefix
boundary.

The table is generated by one `constexpr` function and compiled into the
fat binary's 7,200-byte read-only device-global initialization image.  It is
materialized when the CUDA module/context is loaded; there is no explicit
per-sieve table upload.  The executable SHA-256 binds the compiled image, and
the all-row differential tests independently check its resulting packed
support rather than trusting the table generator. Lean also proves the
literal block-start residue plus local-thread calculation, including its
single conditional subtraction, equals the physical source row modulo 900
for every thread in a 256-thread block.

### Qualification-only modulo-49 extension

A separate `--qualification-residue-2357-seed` path extends the table result
with the exact contribution of `p=7` computed from each row modulo 49. It
removes both the `p=7` distinct-divisor CAS stream and its square-strike
stream, while leaving the production residue-235 API and default unchanged.
The raw device preflight requires the exact `[2,3,5,7]` prefix, a strictly
increasing suffix beginning at least at 11, and the existing
`2 ≤ p ≤ 10^8` machine range. Deliberate suffix values 8, 9, and 10 poison
every initialized row.

`MobiusResidue2357.lean` proves that the modulo-49 update equals the ordinary
`[2,3,5,7]` support fold, its product is at most 210, its factor count is at
most four, and its packed word stays below bit 60. It also proves that 94
event-block slots suffice for every structurally admitted suffix value at the
full 1,073,741,824-row cap, while 93 slots fail for the zero-offset `p=11`
endpoint. The source-shaped layer now additionally proves that the
block-start residue plus local thread reconstructs the exact physical row
modulo 49, so the literal `% 7 == 0` and `== 0` branches detect precisely
divisibility by 7 and 49. An independent exhaustive host model compared all
44,100 CRT block starts and 256 threads per block—11,289,600 row
cases—against the direct four-prime calculation.

Five alternating 100-million-row GB10 pairs produced the same leaf digest,
`M=9139`, `Q=60792765`, all four guard extrema, and zero poison. The
production sieve median was `151.106659 ms`; the modulo-49 candidate median
was `143.655930 ms`, a `4.93%` reduction. Complete device-work medians were
`192.055012 ms` and `184.360985 ms`, a `4.01%` reduction. A separate
five-sample slot sweep found no stable geometry improvement: the nominal
96-slot versus 512-slot complete-device median difference was only
`0.083584 ms` (`0.045%`), below run-to-run dispersion, so the candidate also
retains 512 slots.

This is GB10 qualification evidence, not an H100 result or production
admission. The H100 targets compile, but no target-H100 timing exists. The
candidate has a distinct qualification algorithm and receipt domain so its
leaf chain cannot be confused with the production path.

### Qualification-only modulo-121 extension and 2D schedule

The separate `--qualification-residue-235711-seed` path extends the p7 seed
by deriving the exact `p=11` contribution from each row modulo
`11^2 = 121`. Its `% 11 == 0` branch adds 11 to the distinct-prime product
and count, while its `residue == 0` branch marks squarefulness. The device
preflight requires the exact `[2,3,5,7,11]` prefix and a strictly increasing
suffix beginning at least at 13. Production remains on the p5 seed.

`MobiusResidue235711.lean` proves that the literal block-local modulo-121
arithmetic detects exactly divisibility by 11 and 121, that the initializer
is the ordinary `[2,3,5,7,11]` support fold, and that its packed fields stay
inside the guarded word. `MobiusQualificationSeededRefinement.lean` then
proves the complete pure packed split-square p7 and p11 algorithms, under an
explicit complete-prime-roster and nonpoison premise, finalize to Mathlib's
Möbius function. These are base-trio proofs below the compiled CUDA boundary.

The flat-512 p11 selector has a distinct qualification algorithm and receipt
domain. Its bounded all-row CUDA test agrees with the independent CPU
factorization oracle on the packed product, factor count, squareful bit, and
Möbius output. The persistent boundary test additionally compares production,
p7, and p11 byte streams on a `13 * 1,048,576 + 1` row case chosen so the
`p=13` event stream crosses into a second block slot. The generic and H100
targets compile. CUDA memcheck, racecheck, initcheck, and synccheck report no
errors on the bounded selector. These checks do not constitute target-H100
timing, source-scale execution, or production admission.

A second qualification switch,
`--qualification-residue-rectangular`, selects a two-dimensional divisor
grid:

```text
grid.x     = slots per prime
grid.y     = suffix-prime index
blockIdx.x = event-block slot
blockIdx.y = suffix-prime index
```

The modes `rect2d512`, `rect2dPower`, `rect2dExact`, and
`rect2dCountExact` respectively select 512 slots, the next power of two, the
seed's exact public-cap width, or the exact width for the current count. The
seed is p5 by default and follows the explicit p7 or p11 selector when one is
present. Every rectangular run uses a separate qualification identity and
binds the seed, mode, required and selected widths, event width, grid
dimensions, threads, and enclosing range into its receipt preimage.

`MobiusRectangularCUDASchedule.lean` proves unique ownership for arbitrary
positive widths and the exact public-cap widths 147, 94, and 79. It also
proves the runtime formula

```text
required = 1 + (((count - 1) / suffix_minimum_prime) / 1,048,576)
```

is sufficient for every admitted first offset and suffix prime, and that one
fewer slot fails for the zero-offset minimum-prime stream. At 100 million
rows the exact p5/p7/p11 widths are 14, 9, and 8. The native rectangular
selector has passed a live p13 second-slot boundary KAT, all four CUDA
sanitizer classes, generic and H100 compilation, one-shot identity/binding
checks, and persistent receipt-preimage recomputation. A separate live
`rect2dPower` case has exact required width 9, selects width 16, and forces
the ninth p7 event to execute rather than testing empty geometry. It remains
qualification-only pending paired target-H100 timing and source-scale
qualification. An independent final receipt review found no high- or
medium-severity issue; the one-shot receipt preimage is now also reconstructed
field-by-field outside the runner. A smaller grid is not presumed faster
merely because it launches fewer empty blocks.

`MobiusRectangularVisitRealization.lean` closes the source-facing composition
below the compiler boundary. It combines the count-exact capacity/ownership
proof with the independently proved native arithmetic progression: for p5,
p7, or p11 seeding, an in-segment row is divisible by a supplied suffix
prime if and only if exactly one
`(prime, slot, thread, iteration)` coordinate visits it. Thus the Lean result
is about divisible source rows, not merely abstract event ordinals.

#### DGX Spark 5×100M qualification benchmark

This benchmark ran on one DGX Spark with an NVIDIA GB10, compute capability
12.1, driver `580.159.03`, 20 ARM64 CPU cores (Cortex-X925/Cortex-A725), and a
Release build targeting `sm_121`. It is a GB10 result, not an H100 estimate.
The executable SHA-256 was
`00145814eddf15142ed056ce97bfeaa141717a71908c0c7b2725477c8c3076d5`;
the authenticated prime-roster SHA-256 was
`0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5`.

Each of the nine configurations was run five times, interleaved by
repetition, with this command template:

```bash
build/dgx-spark/sparkinterval-tg-mobius-persistent \
  --lower 9999999900000001 \
  --count 100000000 \
  --shard-rows 100000000 \
  --super-shard-rows 100000000 \
  --incoming-mertens 0 \
  --incoming-squarefree 0 \
  --previous-leaf-sha256 1111111111111111111111111111111111111111111111111111111111111111 \
  --source-prime-roster /tmp/tg-mobius-primes-through-1e8.u32le \
  --allow-other-device \
  [--qualification-residue-2357-seed |
   --qualification-residue-235711-seed] \
  [--qualification-residue-rectangular rect2d512 |
   --qualification-residue-rectangular rect2dCountExact]
```

The harness parsed `super_shard_sieve_kernel_milliseconds`, asserted zero
poison, and required every configuration to produce the same exact Mertens
delta, squarefree delta, and four affine extrema. Times below are milliseconds;
the range is the observed five-sample dispersion.

| Seed / geometry | Slots | Five sieve samples (ms) | Median | Min–max | Median process wall |
|---|---:|---|---:|---:|---:|
| p5 flat-512 | 512 | 151.371, 151.183, 150.975, 151.601, 150.770 | 151.183 | 150.770–151.601 | 782.1 |
| p5 rectangular-512 | 512 | 151.814, 150.813, 168.063, 149.070, 151.410 | 151.410 | 149.070–168.063 | 772.3 |
| p5 rectangular count-exact | 14 | 151.003, 150.441, 150.798, 150.281, 152.487 | 150.798 | 150.281–152.487 | 790.1 |
| p7 flat-512 | 512 | 143.786, 144.604, 143.474, 141.290, 141.993 | 143.474 | 141.290–144.604 | 768.3 |
| p7 rectangular-512 | 512 | 142.183, 143.165, 142.487, 143.333, 143.215 | 143.165 | 142.183–143.333 | 768.0 |
| p7 rectangular count-exact | 9 | 143.103, 144.551, 144.319, 143.789, 142.411 | 143.789 | 142.411–144.551 | 778.9 |
| p11 flat-512 | 512 | 136.085, 138.305, 138.380, 139.670, 136.926 | 138.305 | 136.085–139.670 | 767.6 |
| p11 rectangular-512 | 512 | 137.238, 137.682, 137.882, 136.191, 137.083 | 137.238 | 136.191–137.882 | 759.5 |
| p11 rectangular count-exact | 8 | 137.191, 137.388, 138.615, 137.111, 138.603 | 137.388 | 137.111–138.615 | 762.0 |

The p11 flat seed reduces the median sieve time by about `8.52%` relative to
the p5 flat path on this workload. In contrast, the rectangular mapping and
count-exact widths are neutral within the observed dispersion. They are
therefore **not promoted as a speed optimization**. Their qualified benefit
is eliminating large numbers of empty blocks while making the launch geometry
and its Lean capacity equation explicit and receipt-bound.

### Load-balanced dense-prime schedule

After the residue seed, the first 200 remaining dense primes use 512 fixed
block slots per prime.  A block contains 256 threads, each processing at most
4,096 multiple ordinals, so

```text
B = 256 * 4096 = 1,048,576 events per block
primeIndex   = blockIdx / 512
blockOrdinal = blockIdx mod 512
event        = blockOrdinal * B + threadIdx + 256 * iteration
```

Block ordinal `b` owns the half-open event interval
`[b*B, min((b+1)*B, multipleCount))`.  Euclidean quotient and remainder make
these intervals disjoint and exhaustive.  The public count bound is
`2 * 512 * B = 1,073,741,824`; since every prime is at least two, 512 slots
cover every multiple event at that bound.  Remaining dense primes retain the
one-block schedule and sparse primes retain the at-most-256-events schedule.

`SparkInterval/TernaryGoldbach/MobiusDenseSchedule.lean` proves the flat-grid
decoding, event coverage, uniqueness, capacity bound, and equivalence to the
ordinary multiple count for the exact constants 200, 512, 256, and 4,096.
`MobiusDenseVisitRealization.lean` composes those facts with the first-offset
enumeration and proves a single iff: an in-segment row is divisible by a
suffix prime exactly when a unique legal block/thread/iteration coordinate
visits it. Because the residue-seeded suffix begins at 7, Lean also proves
that 147 slots are sufficient at the unchanged public count cap and that 146
slots fail in the worst-case zero-offset `p=7` row. Thus 147 is the exact safe
minimum; the public domain was not reduced.
`MobiusCUDALaunchIndexing.lean` additionally checks the literal native launch
formulas: the rounded row grid, sparse-prime global index, single-block
grid-stride event owner, 512-slot multiblock
`(slot, thread, iteration)` owner, and flat `(prime, slot)` block encoding are
all complete and duplicate-free. `MobiusCUDALaunchWidthSafety.lean` proves
that the admitted source endpoint, prime squares, divisor and square strides,
loop increments, event products, and generated row offsets are all below
`2^64` at the public launch cap.

These remain architecture-independent integer proofs. They do not yet
identify CUDA builtins, C++ `size_t`, pointers, loops, atomics, compiled
instructions, or successful launches with the modeled values.

## Exact terminal affine scan

A CUB inclusive scan stores the local prefix

```text
{ int32 M, uint32 Q }
```

in eight bytes per row.  Both widths are exact for the declared maximum shard
size of `100,000,000` rows.  Each CUDA thread processes at most 256 rows and
emits four 16-byte candidates: lower and upper extrema for Mertens and
squarefree.  A witness is reconstructed exactly from the segment lower bound
and the retained source order.

The production path does not materialize an intermediate Möbius-byte array.
Its fail-closed packed-word finalizer writes the unscanned pair
`{mu, mu != 0}` directly into this eight-byte array, then CUB overwrites it
with the inclusive prefixes.  The byte array remains available only in
qualification mode.  The GPU known-answer test compares every direct pair
with the retained byte path, and the persistent-worker test compares every
leaf summary, digest, terminal state, grouped super-shard, and restart
boundary across the two paths.

The Hurst bound is evaluated exactly.  The squarefree interval starts from
the exact source-shaped unsigned-128-bit rational endpoints and then tests
the adjacent integers.  For an exact predicate `L^2 <= C^2 y`, with
`r = floor(sqrt(y))`:

- `L <= C r` accepts immediately;
- `L >= C(r+1)` rejects immediately; and
- only the remaining one-`C`-wide strip uses the exact unsigned-256-bit
  square comparison.

`SparkInterval/TernaryGoldbach/HurstAffineCandidateFilter.lean` proves both
floor-square implications and the associative, commutative, idempotent
lexicographic reduction keys:

```text
maximum: (-value, sourceOrder)
minimum: ( value, sourceOrder)
```

`HurstPackedPrefixInput.lean` proves that complete-roster, zero-poison packed
rows produce the exact `{mu, mu != 0}` pairs.
`HurstPrefixCandidateReduction.lean` then closes the list-level algorithm
from those production unscanned pairs to the reduction keys. It proves that
the reference inclusive scan returns the literal local
Mertens sum and nonzero-Möbius count at every row, and derives lossless
`int32_t`/`uint32_t` bounds from the 100-million-row leaf cap.  The separate
qualification route decodes exactly the three accepted `int8_t` bit patterns
(`ff`, `00`, `01`) and is proved equal to the direct-pair scan after
initialization.  The file also proves `order = 2 * row + endpoint` fits
`uint32_t`, that a returned extremum is an actual emitted candidate, and that
maximum/minimum reductions select the globally extremal value with the
earliest tied order.  The candidate combine is proved associative,
commutative, and idempotent, and the reference fold composes exactly across
shard partitions.

The qualification API can still send one exact candidate of each kind per
thread to the host for differential comparison.  The production-shaped API
instead applies the same selector hierarchically (thread, block, then device)
and transfers exactly one 64-byte record containing the four extrema.  It
reuses the CUB workspace as the block-candidate array after the scan.  The
host exact-rechecks the two final squarefree winners; no fixed top-K
approximation participates in acceptance.

The reduced production path therefore uses an 800 MB prefix array, about
2.23 MB of reusable scan/reduction workspace, no intermediate Möbius-byte
array, and a 64-byte candidate result for a 100-million-row receipt leaf.
The approximately 25 MB per-thread candidate array and one-byte row array
exist only in differential qualification mode.  The Lean files prove the
architecture-independent packed-row finalization, direct-pair prefix scan,
byte-qualification equivalence, and ordering laws.  The remaining physical
boundary is to show that the compiled direct finalizer, in-place CUB scan,
CUDA candidate kernels, host reconstruction, and PTX/SASS/GPU execution
refine those models; no theorem here infers those facts from a receipt or
artifact name.

## Prime roster and source-shaped fast path

`tools/tg_mobius_prime_roster.py` creates or authenticates the canonical
little-endian `uint32` table of all primes through `10^8`:

```text
rows:    5,761,455
last:    99,999,989
bytes:   23,045,820
SHA-256: 0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5
```

### Linear-work roster certificate

`SparkInterval/TernaryGoldbach/MobiusSegmentedSieveRoster.lean` replaces the
impractical production use of one Pratt row per prime and one factor pair per
gap.  It checks a short V2 certificate only for the 1,229 base primes through
`10^4`.  The production certificate then has one little-endian `uint16`
factor code for each integer from `2` through `10^8`: zero is a sieve
survivor, while a nonzero value is an actual base-prime divisor.

Acceptance checks both directions:

1. each nonzero code is a proper divisor from the checked base roster; and
2. each strike `p*q`, with checked base prime `p` and `q >= p`, is nonzero.

The first direction prevents a true prime from being marked.  The second,
together with the complete base roster and `(10^4)^2 = 10^8`, prevents a
composite from surviving.  Lean proves that acceptance gives a duplicate-free
list, proves every entry prime, and proves every prime through `10^8` occurs.
One combined Boolean also binds the factor-code bytes and the canonical
`u32le` roster bytes.  Its soundness theorem is
`productionCertifiedRosterCheck_sound`.

The exact production dimensions are:

```text
base primes:       1,229
witness cells:     99,999,999
strike cells:      242,570,204
factor-code bytes: 199,999,998
factor SHA-256:    eaafd263fbe58295ace90426d011fff1e745d4d3a86884ca3f6a27698b62c5a9
roster bytes:      23,045,820
roster SHA-256:    0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5
```

The 212 KB base certificate is materialized in
`SparkInterval/Generated/MobiusBasePrimeV2.lean`.  It exposes one conditional
`productionCheck_sound` theorem: a signed run supplies
`productionCheck ... = true`, and ordinary Lean reasoning yields the exact
roster and both byte bindings.  The generated module deliberately does not
evaluate that Boolean during elaboration and is not imported by the compact
default build.  Merely elaborating its data and conditional theorem measured
9.04 seconds and 3,773,136 KiB peak RSS locally.  An experimental ordinary
kernel-`decide` replay took 80 seconds and 13,617,364 KiB, so it was removed
from the shipped module.

`tools/tg_mobius_segmented_sieve_roster.py` is the packed NumPy artifact
generator and independent executable mirror.  A full `10^8` generation plus
audit on the development server on 2026-07-25 took 3.01 seconds wall time and
646,320 KiB peak RSS.  A separate warm-cache audit took 1.31 seconds and
438,468 KiB peak RSS.  These are local NumPy measurements, not measurements
of Lean evaluation or an H100, and should not be used as a compiler-proof
claim.

The remaining trust work is explicit: prove the packed `uint16`
implementation/decoder refines the Lean `Array Nat` source checker, and bind
that measured executable to the trusted-compute receipt.  Until those steps
are complete, the NumPy program is reproducible corroboration rather than the
formal execution bridge.

When the segment length is at least the base-prime limit, every base prime
has a multiple in the segment.  The runner therefore uses the authenticated
roster directly and skips 5.76 million host modulus tests.  Shorter segments
retain the exact first-multiple filter.

`gpu/src/tg_mobius_persistent_runner.cpp` is the persistent production-shaped
worker.  It loads, authenticates, and uploads the roster once, then reuses all
CUDA allocations, events, and affine workspace.  Its default schedule uses
one fused sieve per receipt leaf.  The optional `--super-shard-rows` schedule
can perform one fused sieve for an integral number of unchanged receipt
leaves (up to one billion rows) and then run the exact affine scan separately
on each leaf.  Scheduling metadata is excluded from the leaf equation, so
leaf summaries, restart state, and the digest chain are invariant under this
grouping.

The header makes the route auditable rather than inferring it from timing.
Production requires `production_split_square_support_path=true`,
`separate_square_strike_pass=true`,
`distinct_factor_events_compute_square_modulo=false`, and
`inline_square_modulo_reference_path=false`. Qualification reports the
opposite four values. Both modes pin
`split_square_dense_prime_limit=200` and the declared
`initialize_then_distinct_then_square_then_finalize` operation order. The
hybrid source checker rejects a production header that omits or changes any
of these values.

Each production receipt leaf copies only one 64-byte extrema record, the
eight-byte terminal `(M,Q)` delta, and a four-byte poison count: 76 bytes in
total.  It does **not** transfer, hash, or commit to the individual Möbius
rows.  `--qualification-write-mu` is a deliberately non-production mode that
copies the raw signed Möbius bytes, independently recomputes the two deltas,
hashes each leaf, and writes the stream for differential tests.  Thus the
compact production chain is evidence about the GPU summary, not an
independent row-by-row commitment.

## Known-answer and adversarial tests

The native/CUDA tests cover:

- exact candidate ordering and earliest-order ties, including a case showing
  why conservative fixed top-K selection is unsound;
- fused packing at the thirteen-prime source bound;
- a squareful thirteen-prime row;
- a malformed fourteen-update roster, which must poison and emit `mu = 2`;
- malformed split rosters with a wrong seed prefix, a zero divisor,
  decreasing suffix, or value above `10^8`, each of which must poison every
  row before arithmetic;
- all-row equality of CPU, inline-square CUDA, and split-square CUDA support
  and prefix inputs, including a range crossing the 200-prime square-schedule
  boundary;
- public-API range-underflow attacks; and
- all-prefix affine scans at counts around CUDA block boundaries using
  all-`+1`, all-`-1`, alternating/zero, and block-pattern Möbius streams.

The persistent-worker test additionally checks:

- raw Möbius bytes and additive `(M,Q)` state against fresh one-shot runs;
- translated extrema, witnesses, endpoint sides, and earliest-order ties;
- buffer reuse against a fresh allocation for every leaf;
- restart from every completed leaf boundary, including identical suffix
  bytes, leaf digests, and final state; and
- one super-shard feeding four receipt leaves against four independent sieve
  launches, with identical bytes, summaries, digest chain, and terminal
  guards;
- production split-square/direct-prefix summaries against the retained
  inline-square/Möbius-byte qualification path;
- residue-seeded, unseeded load-balanced, and legacy one-block realizations
  on a high segment whose `p=2` stream crosses the 1,048,576-event block
  boundary, including identical full packed support, Möbius bytes, summaries,
  and receipt digest; and
- rejection of a selected device roster whose required `[2,3,5]` prefix was
  deliberately damaged.

The qualification harness additionally requires:

- active-prime and all-prime 24-byte paths to agree;
- generated and authenticated cached rosters to agree;
- 24-byte, 16-byte, fused qualification, and one-byte transfer modes to agree;
- the CUDA ordered Möbius bytes, deltas, exact extrema, witnesses, and endpoint
  sides to agree with the pinned Hurst adapter; and
- omitted-prime, same-size mutated-roster, and truncated-roster attacks to
  fail closed.

On the GB10 qualification host, both CUDA known-answer executables also pass
Compute Sanitizer `memcheck`, `racecheck`, `initcheck`, and `synccheck` with
zero reported errors or hazards.

Build and run the focused suite:

```bash
cmake -S . -B build/dgx-spark \
  -DCMAKE_CUDA_ARCHITECTURES=121 \
  -DSPARKINTERVAL_BOOST_INCLUDE_DIR=/path/to/boost/include \
  -DSPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR=/path/to/mpfr/include

cmake --build build/dgx-spark --target \
  sparkinterval-tg-mobius-affine-candidate-order-known-answers \
  sparkinterval-tg-mobius-fused-support-known-answers \
  sparkinterval-tg-mobius-affine-scan-known-answers \
  sparkinterval-tg-mobius-segment \
  sparkinterval-tg-mobius-persistent

ctest --test-dir build/dgx-spark --output-on-failure \
  -R 'tg_mobius_(affine_candidate_order|fused_support|affine_scan|persistent)_known_answers'
```

Run the bounded differential qualification:

```bash
python3 tools/tg_mobius_hurst_qualification.py \
  --gpu-runner build/dgx-spark/sparkinterval-tg-mobius-segment \
  --hurst-runner /path/to/pinned/sparkinterval-tg-hurst-residual-shard \
  --prime-roster /path/to/tg-mobius-primes-through-1e8.u32le \
  --output build/tg-mobius-hurst-qualification.json \
  --count 1000000 --repeats 3 \
  --little-mertens-calibration-count 100000000 \
  --little-mertens-calibration-repeats 3
```

## Measurements on DGX Spark

These are local NVIDIA GB10 measurements, not H100 measurements.

Before dense-prime load balancing, a near-`10^16` 20-million-row experiment
compared the exact baseline with an adjacent-density one-division rewrite:

| implementation | sieve kernel | affine scan | combined |
|---|---:|---:|---:|
| optimized fused support, compact candidates | 69.384 ms | 8.405 ms | 77.789 ms |
| attempted adjacent-density one-division rewrite | 71.235 ms | 8.739 ms | 79.989 ms |

The one-division rewrite was exact but slower, so it was removed.

A second pre-balancing experiment moved squarefulness into a separate dense
`p^2` pass while retaining the old one-block divisor schedule. It passed the
differential tests but also lost:

| implementation | sieve kernel | kernel plus affine |
|---|---:|---:|
| inline exact `n % p^2` | 355.770 ms | 394.315 ms |
| separate squarefulness pass | 357.754 ms | 396.237 ms |

These are alternating exact 100-million-row medians. That implementation was
removed. It is not the current split schedule: the current path retains the
later load-balanced divisor grid, seeds 2/3/5 from the residue table, uses
disjoint dense/sparse square-prime schedules, and writes direct prefix inputs.

The identity

```text
P = product of the distinct supplied prime divisors of n
squareful(n) iff gcd(P, n/P) > 1
```

also gives an exact way to defer squarefulness to finalization.
`SparkInterval/TernaryGoldbach/MobiusResidualGCD.lean` proves the reusable
architecture-independent algebra, including residual-prime cases.  It
improved the legacy one-block kernel from 356.279 to 337.109 ms, but combining
it with dense-prime load balancing regressed the median from 202.371 to
205.915 ms.  It therefore remains a proved model rather than CUDA hot-path
code.

A compact list containing only nonempty dense block tasks was also exact, but
362 tasks (2,896 bytes) were slower than the fixed grid.  Fixed-grid and
compact-task kernel medians were 199.067 and 200.722 ms; including task
generation, allocation, and upload raised the compact median to 200.912 ms.
The compact path was removed both for speed and to avoid adding a separate
task-completeness trust surface.

The production schedule changes were then measured on the same source-shaped
100-million-row terminal shard:

| fused realization | sieve-kernel median | change from prior |
|---|---:|---:|
| legacy one block per dense prime | 358.586 ms | — |
| fixed load-balanced blocks, unseeded | 199.028 ms | -44.50% |
| load-balanced plus exact residue-235 seed | 173.653 ms | -12.75% |

The last two rows are alternating three-run medians from the final executable.
The residue row includes residue initialization; the table itself has zero
explicit per-sieve upload because it is a fatbinary device-global image.  The
combined residue-seeded sieve and exact affine median was 212.300 ms.
Relative to the original one-block schedule, the sieve reduction is 51.57%.

The exact-minimum proof motivated a separate three-run sweep of the native
residue-seeded slot count.  Every choice used the same public cap and passed
the Möbius hash, mismatch, and poison gates:

| block slots per dense prime | sieve-kernel median |
|---:|---:|
| 147 | 174.421 ms |
| 160 | 173.944 ms |
| 192 | 172.854 ms |
| 256 | 173.486 ms |
| 512 | 172.874 ms |

The 0.020 ms difference between 192 and 512 is measurement noise at this
scale, while the exact minimum was slower.  Production therefore retains 512
slots rather than promoting an unsubstantiated speedup.  The native metadata
reports both the selected value 512 and the proved minimum 147.

The direct packed-word-to-prefix finalizer was measured separately on the
same GB10 class with three alternating 100-million-row near-endpoint runs.
The median sieve-plus-affine device time fell from `192.058 ms` for the
qualification byte path to `189.724 ms` for the fused production path, a
`1.22%` reduction. It also removes 100 MB of intermediate device storage at
the default leaf/super-shard size (and one GB when a one-billion-row
super-shard is explicitly selected). Host process time is not compared here
because qualification deliberately transfers and writes all 100 million row
bytes.

The later production split-square implementation was also measured with five
alternating 100-million-row near-endpoint runs on the same GB10 host. The
production split-square sieve median was `150.657 ms`; the retained
inline-square qualification sieve median was `153.167 ms`, a `1.64%`
reduction in the reported sieve interval. The corresponding medians of each
run's sieve-plus-finalization-plus-scan sum were `191.737 ms` and
`191.813 ms`, only a `0.04%` reduction. That end-to-end difference is
measurement noise, not evidence of a GB10 throughput improvement. The target
H100 deployment still needs the same alternating calibration before policy
may call this a performance improvement.

The production allocation was `1,648,325,307` bytes versus
`1,748,325,307` bytes for qualification. The 100 MB difference is the
already documented intermediate Möbius-byte array, not storage saved by the
square split itself.

One final 100-million-row qualification transferred and independently checked
every packed eight-byte row for both the residue-seeded and unseeded
realizations.  The packed-support SHA-256 was
`3030ed4b58d12ff67211d12589f23fae2ad43e213a59a97b6c61d25ed5c3113e`;
both paths had zero mismatches and zero poison values.  The Möbius row
commitment was
`82346c5acfff6fd2e47e4cc4ba6d8ada0e603e2cbc641896871842fd3671951e`.
It matched the independent CPU sieve and pinned Hurst adapter exactly, as did
deltas `M = 9139`, `Q = 60792765`, all extrema, witnesses, and endpoint sides.

The final CUDA kernels compile for `sm_121` with no reported spills.

For two consecutive 100-million-row production-shaped receipt leaves, the
residue-seeded fused kernels took 174.291 and 175.749 ms; the exact affine
scans took 36.983 and 37.878 ms.  The 76-byte device-to-host copies took
0.02338 and 0.01531 ms, and process time including roster authentication,
allocations, upload, and CUDA startup was 0.889 seconds.  No production
Möbius row was transferred or hashed.

An earlier exact one-billion-row scheduling sweep compared ten
100-million-row sieve launches with larger super-shards.  It predates the
residue initializer, so its absolute timings are not current production
throughput; its grouping and memory results remain applicable.  All schedules
produced the same ten leaf digests and terminal guards.  On this
unified-memory GB10, the historical qualification-byte allocation rose from
1,748,325,307 bytes at 100 million rows to 9,848,325,307 bytes at one billion
rows. The direct-prefix production allocations are now 1,648,325,307 and
8,848,325,307 bytes respectively. Alternating three-run kernel medians for
the same one-billion-row range were:

| super-shard rows | sieve launches | fused-kernel median |
|---:|---:|---:|
| 100,000,000 | 10 | 3,608.788 ms |
| 500,000,000 | 2 | 3,508.041 ms |
| 900,000,000 | 2 | 3,724.085 ms |
| 1,000,000,000 | 1 | 3,457.378 ms |

The larger allocation adds roughly 258 ms of one-time allocation cost on this
machine, and the 900-million-row case was noisy.

A later alternating three-run pre-direct-finalizer production-code GB10
sweep over the same one-billion-row range used 100-million-row receipt
leaves. Median
process/fused-kernel times were 2333.6/1525.9 ms at 100 million rows,
2388.5/1567.3 ms at 200 million, 2432.7/1562.0 ms at 400 million, and
2713.3/1647.3 ms at one billion (with one additional noisy one-billion-row
kernel result of 2066 ms).  The hybrid materializer therefore keeps
100 million rows as its production starting default; this is a launch-policy
choice, not a claim that 100 million is universally fastest.

Before an H100 source-scale run, calibrate 100-, 200-, and 400-million-row
super-shards on the exact H100 SKU and deployment image.  Materialize the
production plan with the measured winner.  Do not treat either GB10 sweep as
an H100 throughput prediction.

The exact CPU little-Mertens calibration processed 100 million rows in a
median 1.073 seconds, or about 93.2 million rows/second.  A linear projection
through `10^12` is about 2.98 hours on the measured CPU.  This projection is
not a production run.

The current sizing path uses the later `191.737 ms` complete-device-work
median for 100 million rows, or `521.548` million rows/second on the measured
GB10.  The production geometry has exactly
`9,999,000,000,000,000` rows in `[10^12+1,10^16+1)`, split into eight equal
`1,249,875,000,000,000`-row workers by
`hurst-h100-eight-way-independent-affine-scan-v1`.  At equal GB10 throughput,
those eight workers take `665.687` hours.  Applying the explicit, unmeasured
`12.3x` GB10-to-H100 sensitivity gives `54.121` arithmetic-only wall hours
(`2.255` days), `432.967` node-hours, and approximately `$3,022.11` PAYG or
`$614.40` Spot at the pinned Azure price snapshot.

Those are GB10-derived sensitivities for the terminal H100 stage, not a
complete hybrid-campaign ETA, target-H100 measurements, or a
production-budget claim.  They exclude the CPU summary/verification prefix
through `10^12` and its handoff, startup, roster handling, receipt
serialization and replay, checkpointing, attestation, retries, and spot
availability.  The executable calculation and fail-closed release gate are
in `tg_verifier/hurst_h100_affine_projection.py`; the exact eight-worker
composition is linked to Lean theorem
`HurstAffineClusterComposition.eightWorkerComposition_eq_single`.

## Remaining trust boundary

The following are deliberately still absent:

- a complete `[1, 10^16+1)` receipt chain;
- physical source-scale replay;
- an independent per-row commitment in compact production mode;
- CUDA atomic-CAS linearizability, CUB scan realization, register/loop
  realization, and compiled native execution refinement to the proved
  packed-word and prefix models;
- compiler, runtime, driver, GPU-architecture, or CPU-architecture refinement;
- secure-enclave execution attestation; and
- a Lean inhabitant that discharges any Hurst-family external atom.

Bounded agreement is useful implementation evidence, but none of these gaps
may be converted into a theorem merely by changing a report label.
