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
those endpoints and every adjacent gap to be at most `4 * 10^18`. Consecutive
range files repeat exactly one boundary rung. All 492700 files are linked from
the all-zero root by SHA-256.

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

Resume never trusts a checkpoint. It replays every contiguous file from range
zero, including every prime proof, boundary duplicate, endpoint condition, and
hash link. A missing middle file, a later fork, trailing bytes, a noncanonical
varint, or a changed proof artifact fails closed. Both the ladder and binary
campaign manifests also pin the exact implementation and deterministic
primality-source hashes, so resuming under changed checker code is rejected.

## Commands

Inspect and initialize the exact schedule:

```bash
tools/tg_goldbach_campaign.py --pretty plan
tools/tg_goldbach_campaign.py init /data/tg-goldbach
```

Produce one range as a resumability test, or omit `--max-new-ranges` for the
full source schedule:

```bash
tools/tg_goldbach_campaign.py run /data/tg-goldbach \
  --max-new-ranges 1 \
  --builtin-pocklington
```

If that producer emits external ECPP blobs, also supply its independent
checker:

```bash
tools/tg_goldbach_campaign.py run /data/tg-goldbach \
  --general-prime-producer /opt/tg/bin/general-prime-producer \
  --general-prime-checker /opt/tg/bin/ecpp-checker
```

Replay status and, only after all 492700 ranges exist, request a full receipt:

```bash
tools/tg_goldbach_campaign.py --pretty status /data/tg-goldbach \
  --general-prime-checker /opt/tg/bin/ecpp-checker

tools/tg_goldbach_campaign.py --pretty verify /data/tg-goldbach \
  --general-prime-checker /opt/tg/bin/ecpp-checker \
  --binary-campaign /data/binary-goldbach-through-4e18
```

For schedulers that need one argv and begin with an empty workspace, `full`
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

The schedule, compact codec, exact Proth and Pocklington checkers, concrete
Pocklington-grid producer, root-to-tip resume verification, exact but unscaled
binary producer/replayer, and optional external protocols are implemented and
tested on bounded fixtures. Thus the repository has a literal one-command path
whose domain is the complete source domain without requiring an ECPP or binary
plugin. It is not operationally feasible at the current Python rates, no full
range has been run here, and no source result has been produced. Optimized
general-prime/ECPP and binary-Goldbach backends remain practically necessary
for a realistic rerun.

Until both full computations are run and replayed, this work is a capable
reconstruction harness, not a verification of the named external atom.
