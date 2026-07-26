# Helfgott--Platt prime-ladder reconstruction

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This is a runnable reconstruction and replay format for the finite computation
reported in Helfgott and Platt, *Numerical Verification of the Ternary Goldbach
Conjecture up to `8.875 * 10^30`*,
[arXiv:1305.3062v2](https://arxiv.org/abs/1305.3062v2), especially §§2--4
and Theorem 4.1. It is not a claim that the historical computation has already
been independently replayed. The paper says that its per-range ladder files
were deleted after checking.

## Exact source schedule

The immutable `full_source` profile uses

```text
n                    = 52
range width          = 2^54 * 10^9
range count          = 492700
T                    = 492700 * (2^54 * 10^9)
                     = 8875694145621773516800000000000
maximum ladder gap   = 4 * 10^18
endpoint tolerance   = 2 * 10^18
small Proth witnesses = primes through 29
reported sieve bound = primes below 16000
```

For range `i`, the nominal endpoints are `i W` and `(i+1) W`. The checker
requires the first and last certified primes to lie within `2 * 10^18` of
those endpoints and every adjacent gap to be at most `4 * 10^18`. The paper
ran these ranges independently on all available cores. The new production
format preserves that shape: every range carries its formulaic index and
endpoints and an all-zero predecessor marker. It neither reads nor hashes the
preceding range. The older serial SHA-chain remains only for compatibility.

The source algorithm takes a current prime `p`, considers fixed-form numbers

```text
q = k * 2^52 + 1,       0 < k < 2^52,
```

below `p + 4 * 10^18`, and selects the largest one for which a source witness
`a in {2,3,5,7,11,13,17,19,23,29}` satisfies

```text
Jacobi(a, q) = -1
a^((q-1)/2) = -1 (mod q).
```

Those two exact integer checks prove `q` prime by Proth's theorem. The source's
fixed `k` need not be odd; the checker conceptually moves its powers of two
into the exponent before applying the canonical Proth form. If an interval has
no such Proth prime, a certified general-form prime in the open interval is
requested from the general-prime producer.

## Parallel range receipts and ordered reduction

`produce-range DIRECTORY i` is the array-worker contract for
`0 <= i < 492700`. The worker derives `[iW,(i+1)W]` from the pinned manifest,
selects certified boundary primes in the two fixed tolerance windows, builds
the intervening ladder, writes the compact range atomically, and reopens and
checks every record. Any index can run first and on an unrelated CPU node.

Every immutable `independent-receipts/receipt-NNNNNN.json` binds the source
constants, manifest and parameter hashes, range-file SHA-256, endpoints,
first and last primes, record count, observed maximum gap, and exact odd
interval covered. It counts direct-64, Proth-52, Pocklington, and external
prime records and lists the content hash of every general-prime artifact.
Proth witnesses are inline in the range. Pocklington JSON is checked
recursively with exact integer arithmetic. An external proof record is
rejected unless the configured checker replays its hash-bound artifact.

Many Slurm installations cannot accept a 492700-element array. The equivalent
`produce-group` entry point partitions the same index set into balanced,
formulaic half-open groups and uses a bounded local process pool. For example,
3200 scheduler groups with 20 local workers each still produce exactly one
immutable receipt per source range:

```bash
tools/tg_goldbach_campaign.py produce-group /data/tg-goldbach \
  --group-index "$SLURM_ARRAY_TASK_ID" --group-count 3200 \
  --local-workers 20 \
  --summary "/data/tg-goldbach/groups/group-$SLURM_ARRAY_TASK_ID.json"
```

The group summary is operational metadata. The reducer trusts only the
individually replayed range receipts, so changing group count, task order, or
local worker count cannot change the certificate boundary.

`reduce-ranges` requires exactly the ordered index set `0..492699`; missing,
duplicate, misnamed, or swapped receipts fail. It replays every range and
checks the nominal endpoints, both endpoint tolerances, all within-range
gaps, the forward gap or overlap between neighbors, and the union of actual
intervals `[p+4,p+4e18]` from odd `7` through the source endpoint. Checking
the interval union catches the parity off-by-two case that a maximum-gap
summary alone can miss. It finally makes an ordered, domain-separated Merkle
commitment to all 492700 receipt hashes.

The ladder aggregate says
`binary_goldbach_prerequisite_satisfied: false`. `combine-gpu` first reloads
and validates the hardened GoldbachGPU production plan, every formulaic binary
coverage-leaf receipt, and their exact `[4,4e18]` aggregate. GPU execution may
use eight concurrent devices, but that concurrency is not a certificate-leaf
count. The command then separately replays the ladder aggregate. The combined
result explicitly says
`binary_receipt_proves_prime_ladder: false`; neither Merkle root is evidence
for the other computation.

## Why the binary computation is separate

A ladder alone does not prove ternary Goldbach. The reduction also needs the
independent result that every even `e` with

```text
4 <= e <= 4 * 10^18
```

is a sum of two primes. Each certified ladder prime `p` then covers the odd
targets in `[p+4, p+4*10^18]`. Replay checks the union of these intervals
directly, rather than assuming that a gap summary has the right off-by-two
behavior.

The preferred `verify` path takes `--binary-campaign`. That in-repository
campaign visits every even integer, finds a pair with the exact deterministic
unsigned-64-bit primality predicate, hashes each `(target,p,q)` transcript, and
recomputes every witness during replay. A digest-only status check is never
promoted. This literal reference algorithm reaches the exact endpoint in
principle, but its roughly two quintillion targets make it deliberately
unscaled and not a realistic replacement for the optimized historical binary
Goldbach computation.

The full-source default groups `10^13` even targets per transcript chunk,
yielding about 200000 range receipts rather than trillions of tiny files.
Bounded tests use much smaller chunks. The larger source chunk is a storage
choice, not a claim that one Python worker can finish it in practical time.

An alternative integration path takes both `--binary-checker` and
`--binary-artifact`. It invokes the external checker again and accepts only a
canonical result binding the exact endpoints, the artifact SHA-256, and the
checker executable SHA-256. This protocol authenticates an external backend's
answer; it does not itself parse or prove the external artifact, so that pair
remains an explicit trust boundary and must not be classified as a
self-contained verified computation.

For the hardened GoldbachGPU production campaign,
`tools/tg_goldbach_gpu_binary_checker.py` is a project-owned concrete checker
for this protocol. Given the aggregate as `--artifact`, it loads the sibling
production `plan.json` and the complete formulaic receipt set under
`receipts/`, revalidates every receipt and exact range, reconstructs the Merkle
aggregate, and only then emits
the canonical binary result. This removes the digest-only interpretation for
that specific artifact layout; CUDA execution and the reviewed external
arithmetic remain outside Lean.

The binary checker protocol is

```text
BINARY_CHECKER --request REQUEST.json --artifact ARTIFACT
```

where the request has kind `tg_binary_goldbach_request_v1`. On standard output
the checker must emit one canonical JSON object of kind
`tg_binary_goldbach_result_v1`, with no standard error, containing exactly
`first_even = "4"`, `last_even = "4000000000000000000"`,
`every_even = true`, `verified = true`, and the two executable/artifact hashes.

## General-form prime certificates

The paper reports 130917 general-form primes, checked independently with
François Morain's ECPP program. This repository provides two replay paths:

1. `pocklington`: a self-contained recursive JSON certificate. The built-in
   checker proves every large factor recursively, verifies the exact
   factorization `F R = N-1`, checks `F^2 > N`, and checks the modular-power and
   gcd condition for each prime divisor of `F`.
2. `external`: an opaque ECPP (or other proof) blob. Replay requires
   `--general-prime-checker`; the fixed protocol binds the number, blob hash,
   and checker executable hash. The external executable remains part of the
   trust boundary.

For production, `--builtin-pocklington` supplies a concrete in-repository
fallback rather than merely a plugin protocol. For an open ladder interval
`(L,U)`, it chooses a directly checked 64-bit prime `r` and sets

```text
F = 2^20 r,       F^2 > U.
```

It scans the dense grids `N = jF+1` inside the interval. Miller--Rabin is used
only to discard obvious composites. A candidate is returned only after the
built-in checker accepts exact Pocklington witnesses for both known prime
factors `2` and `r`; because `F^2>N`, acceptance proves `N` prime. Advancing
`r` supplies further grids if necessary. An external ECPP producer remains a
liveness/performance escape hatch, not a soundness requirement for a returned
built-in certificate.

The producer protocol is

```text
GENERAL_PRODUCER --request REQUEST.json --output RESULT.json
```

It must be silent and write canonical JSON of kind
`tg_general_prime_result_v1` with fields `number`, `certificate_kind`, and an
absolute `certificate_path`. The number must be strictly inside the requested
open interval. The campaign copies the proof blob into a content-addressed
store and immediately rechecks it. A Pocklington-producing executable needs no
external replay checker; an ECPP-producing executable does.

An external general-prime checker is invoked as

```text
GENERAL_CHECKER \
  --number N \
  --certificate PATH \
  --certificate-sha256 SHA256
```

and must emit the canonical, exactly bound `tg_general_prime_result_v1`
checker response defined in `tg_verifier/goldbach_campaign.py`.

## Compact range files and resume

Each `range-NNNNNN.tggl` file contains a canonical JSON header followed by a
stream of unsigned varints:

- direct 64-bit prime: tag plus delta from the preceding rung;
- fixed-`n=52` Proth prime: tag, delta, and small witness;
- Pocklington/ECPP prime: tag, delta, and 32-byte content digest.

The first rung is stored relative to the header base. The format does not store
decimal JSON for millions of rungs, and the writer spools records rather than
materializing a range in memory. Certificates remain large: the reported
campaign contains millions of rungs per scheduled range, so a complete replay
corpus is still expected to require multiple terabytes even with delta coding.

Parallel resume never trusts a checkpoint. If a worker's range exists, it
replays that range and emits the same immutable receipt. A changed byte,
trailing byte, noncanonical varint, or changed proof artifact fails closed.
The manifest pins the exact implementation and deterministic primality source,
so changed checker code rejects earlier artifacts. The legacy `run` command
still replays its serial prefix, but it is not the production cluster path.

## Commands

Plan creation, initialization, and compact receipt inspection are local
control-plane operations. Every source-range producer, arithmetic checker,
reducer that replays source evidence, and final combination is cloud-only.
Dedicated native KAT ranges remain local only when the actual range contains
at most 64 candidates.

Inspect and initialize the exact schedule:

```bash
tools/tg_goldbach_campaign.py --pretty plan
tools/tg_goldbach_campaign.py init /data/tg-goldbach
```

Submit every fixed index as an independent array task (one shown):

```bash
tools/tg_goldbach_campaign.py produce-range /data/tg-goldbach "$ARRAY_INDEX"
```

If that producer emits external ECPP blobs, also supply its independent
checker:

```bash
tools/tg_goldbach_campaign.py produce-range /data/tg-goldbach "$ARRAY_INDEX" \
  --general-prime-producer /opt/tg/bin/general-prime-producer \
  --general-prime-checker /opt/tg/bin/ecpp-checker
```

Replay one output and reduce only after all 492700 receipts exist:

```bash
tools/tg_goldbach_campaign.py check-range /data/tg-goldbach "$ARRAY_INDEX" \
  --general-prime-checker /opt/tg/bin/ecpp-checker

tools/tg_goldbach_campaign.py reduce-ranges /data/tg-goldbach \
  --general-prime-checker /opt/tg/bin/ecpp-checker \
  --out /data/tg-goldbach/ladder-aggregate.json
```

Then bind it after the separately completed hardened binary aggregate:

```bash
tools/tg_goldbach_campaign.py combine-gpu /data/tg-goldbach \
  --ladder-aggregate /data/tg-goldbach/ladder-aggregate.json \
  --binary-plan /data/binary/plan.json \
  --binary-receipts-dir /data/binary/receipts \
  --binary-aggregate /data/binary/aggregate.json \
  --out /data/tg-goldbach/combined.json
```

The legacy serial/reference `full` command
auto-initializes, resumes, and finally replays both in-repository campaigns. It
never emits a full receipt from a sample or partial endpoint:

```bash
tools/tg_goldbach_campaign.py full /data/tg-goldbach-full \
  --general-prime-producer tools/tg_pocklington_producer.py
```

The built-in general-prime search is deliberately bounded to 256 factor-prime
grids per missing Proth rung. For operational liveness, the command above uses
the unbounded in-repository recursive-Pocklington producer; an independently
reviewed ECPP producer may be substituted. Every returned certificate is
imported, hashed, and replayed before it enters the ladder.

This command is literal and is expected to be computationally prohibitive; it
exists so the exact source endpoint is represented by executable code rather
than by a sample masquerading as capability.

`receipt.json` deliberately says `lean_atom_discharged: false`: an independently
replayed computation still needs a small Lean theorem connecting this exact
certificate contract to the source atom before it changes the Lean trust
boundary.

## Present readiness

The fixed array schedule, independent compact receipts, exact Proth and
Pocklington checkers, Pocklington-grid fallback, ordered coverage reducer,
Merkle commitment, and final two-aggregate replay are implemented and tested.
The production CPU path now uses
`reference/tg_goldbach_ladder_native.cpp`.  It segments the four billion
`k` values in each source range, sieves `k*2^52+1` by every prime below 16000,
and applies the paper's ordered witnesses through 29 with GMP.  Its compact
binary protocol is not accepted directly: `tg_verifier/goldbach_native_ladder.py`
recomputes every Jacobi symbol and Proth congruence with Python integer
arithmetic before writing the ordinary `.tggl` range.  The existing independent
range replay and ordered reducer are unchanged.

Build and test the optional native target with:

```bash
cmake -S . -B build/goldbach-ladder \
  -DSPARKINTERVAL_BUILD_TG_GOLDBACH_LADDER=ON \
  -DSPARKINTERVAL_BOOST_INCLUDE_DIR=/path/to/boost/include
cmake --build build/goldbach-ladder \
  --target sparkinterval-tg-goldbach-ladder-native
ctest --test-dir build/goldbach-ladder \
  -R tg_goldbach_ladder_native_known_answers --output-on-failure
```

One full-source array worker is:

```bash
tools/tg_goldbach_ladder_native.py produce-range /data/tg-goldbach \
  "$ARRAY_INDEX" \
  --runner build/goldbach-ladder/sparkinterval-tg-goldbach-ladder-native
```

`produce-group` provides the same formulaic grouping and bounded local CPU
pool as the reference campaign.  Each completed worker writes the existing
range receipt plus a separate native-producer receipt binding the runner,
reviewed C++ source, compact segment streams, and final range file by SHA-256.
The source identity is compiled into the executable and checked against the
current reviewed file; a stale executable fails before ingestion.

If a step has no accepted source-form Proth prime, the C++ producer emits
`complete=false` and the exact open general-prime obligation.  The Python
supervisor can continue only after its built-in Pocklington checker or an
explicit external checker proves a prime in that interval.  It also reruns the
source-form search and rejects a native false negative.  This is a fail-closed
liveness boundary, not a probable-prime escape hatch.

No full range has been run here and no source result has been produced.
Durable storage, the complete 492700-range run, and the full binary-Goldbach
run remain necessary.  General-prime fallback performance at full scale has
not yet been measured.

Until both full computations are run and replayed, this work is a capable
reconstruction harness, not a verification of the named external atom.

## Exact Lean handoff

[`GoldbachSourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/GoldbachSourceSemantics.lean)
states the exact binary prerequisite, finite prime-ladder contract and cited
source endpoint. Its executable ladder check covers first rung, primality,
adjacent translated intervals and the last endpoint; ordinary Lean proves that
the check plus binary Goldbach through `4e18` implies the finite three-prime
source theorem.

The closed `helfgottPlattGoldbachProductionV1` invocation is an Azure SEV-SNP
CPU finalizer. It pins `goldbach-gpu-hardened-production-65536-leaf-v2`, the
binary aggregate kind and hardened-source identity, the parallel ladder
campaign/aggregate kind and native-source hash, the combined artifact kind,
all branch counts and the exact source range. It can return `false`, or `true`
together with `Nonempty CheckedSourceEvidence`; only the latter exposes the
source claim through the signed wrapper.

No final receipt is claimed. The current `Runs` proposition records the exact
mathematical evidence but does not separately expose a Lean-checkable
transitive provenance object proving that the final CPU receipt verified every
pinned H100 binary receipt and CPU-ladder receipt/artifact hash. The production
materializer and receipt format must close that provenance edge, and both full
campaigns must run, before the semantic binding can be enabled. It remains
disabled with null theorem, realization and invocation fields.

## Local source-height benchmark

On 2026-07-21 the following bounded, noncertificate benchmark was run on the
repository's DGX Spark host (Linux aarch64, Python 3.12.3):

```bash
tools/tg_goldbach_campaign.py --pretty benchmark-source-height --steps 5000
```

Near `T-W`, the exact Python producer generated 5000 Proth-52 rungs in 2.016
seconds and replayed them in 0.055 seconds, about 2415 produce-plus-replay
rungs/s. The width/gap constants force at least 4,503,600 records per source
range. At the sampled rate that lower-bound workload is about 1,865 seconds
(31 minutes) per range and roughly 255,000 core-hours for all ranges, before
I/O and general-prime fallback.

By comparison, §4 of the paper reports about 270 seconds to sieve and produce
one range and 40 seconds for its independent C++/CLN replay, and about 40,000
core-hours total. A complete local range was not run because the Python
reference is substantially slower and would retain at least 4.5 million
records. Across the campaign the width/gap lower bound alone is about 2.22
trillion records, so storage and replay I/O also need explicit engineering.
The benchmark proves no omitted suffix.

On the same DGX Spark host on 2026-07-21, the compiled GMP producer was also
run near `T-W` over a target distance of `1000000*(4e18-2)`.  It emitted
1,039,390 certified rungs in 9.028 seconds after sieving 905,969,664 candidate
slots in 54 fixed 2^24-candidate blocks.  The independent Python replay brought
the end-to-end wall time to 21.40 seconds with 84,212 KiB maximum RSS.  This is
about 115,126 producer rungs/s and 48,570 produce-plus-replay rungs/s.

Linearizing only that source-height sample and the unavoidable minimum
4,503,600 records per range gives roughly 93 seconds per range and 12,700
aggregate core-hours for 492,700 ranges.  This is a planning estimate, not a
full-run certificate: real ranges have more than the minimum record count,
general-prime pauses and durable I/O add overhead, and no complete range was
timed.  The paper's historical result remains the stronger empirical datum:
about 270 seconds of production plus 40 seconds of independent checking per
range and about 40,000 core-hours overall.
