# CH25 psi qualification and one-pass affine optimization

This note records bounded executable qualification of the CH25 psi worker and
the follow-up one-pass affine-guard optimization. Neither result is a
full-source computation, attestation, compiler refinement, realization of
primesieve or CRlibm in Mathlib, receipt admission, or discharge of the
`ch25-psi-1e13` atom.

## Source-built two-pass comparison

The optimized and literal-reference executables are two compile-time modes of
the same `reference/tg_psi_residual_shard.cpp` bytes:

- the candidate uses direct floor/ceiling square comparisons and compile-time
  summary/verify specialization;
- `SPARKINTERVAL_PSI_LITERAL_REFERENCE=1` restores the prior
  `floor(sqrt(2*x))` filter and runtime mode dispatch.

`tools/build_tg_psi_qualification_pair.py` builds both modes and retains exact
compiler argument vectors, dependency files, compiler version and executable
hash, linked static-library hashes, source hash, macro-mode labels, and output
hashes. The 2026-07-25 local manifest had SHA-256
`5e8cdb063903ad5032d90d3f8420300ae53da872bce15225c3c100ccb9d0299e`.
It records:

| Item | SHA-256 |
|---|---|
| common two-pass source | `f7337919c3f433855ba84c1ba0f72a37aa49a90fdb3e2026b39f6f25e732765f` |
| GCC 13.3.0 compiler executable | `fc02363794280f404c6ca6f5da1c8fe469be902e9de140d35d8573bb3393f53b` |
| optimized candidate | `0d95373d2d0258146cbd5db2b73fcedc549ffc5afdfac7c640d7b6e891d22fb1` |
| literal reference | `5a42240e2a4b20a0b5abf082fb8d23d0b74c2cefd1cb454527aa9056c3812bda` |

The manifest is build provenance, not a proof about GCC or the AArch64 CPU.
Its capability flags say so explicitly.

`tg_verifier/psi_two_pass_qualification.py` then performed an independent
literal replay over `[2, 1,000,001)`, split into four 250,000-integer shards
and run three times in alternating summary/verify order. The replay contained
78,734 ordered prime-power events: 78,498 primes and 236 higher prime powers.
For every unique prime it:

1. loaded the separately built pinned CRlibm library and decoded the directed
   binary64 endpoints to Q64 from their sign/exponent/significand bits;
2. checked that pair encloses the independent rational-series log interval;
3. independently regenerated the structural and full-row SHA-256 streams;
4. replayed every lower-left-limit and upper-post-jump integer guard and exact
   fallback count;
5. derived every incoming state by an exclusive scan from `[0,0]`; and
6. checked ordered state addition, u128 safety, final state, all repeats, both
   passes, and both binaries, ignoring only elapsed time.

The source-bound artifact SHA-256 is
`1541ad1b383b7e4952cc52c8badd0160ec4fbed7c6a91656dfba66bdcab1f3e6`.
Normal verification regenerates the literal oracle. Structural-only replay is
available but conspicuously named `--no-regenerate-oracle`; even that mode
checks the zero root, event-count partition, all commitment syntax, every
incoming/outgoing/delta equation, u128 overflow, totals, prime/log
cardinality, final state, raw receipt bytes, and capability boundary.

`tests/test_tg_psi_two_pass_qualification.py` confirms fail-closed behavior
for readable/raw divergence, self-consistent event- or row-commitment
mutation, receipt omission, receipt reordering, incoming-chain mutation,
u128 fold overflow, and attempted capability escalation.

## Direct-square filter

The original verify hot path computed `floor(sqrt(2*x))` for every event. The
candidate instead compares the Q64 floor and ceiling squares directly with
`2*x`, entering the existing arbitrary-precision fallback only for the
one-cell boundary.

`tests/test_tg_psi_lower_filter_equivalence.py` compares old and new decisions
for both strictness modes on all nearby cells through `x = 100,000`, source and
u64 extremes, and 100,000 deterministic random u128 inputs.
`SparkInterval/TernaryGoldbach/PsiLowerFilter.lean` proves, using the ordinary
Lean kernel and base trio only, that all direct-square accept and reject
branches are equivalent to the `Nat.sqrt` formulation. Connecting C++ u128
instructions to those naturals remains outside this theorem.

On one 100,000,000-integer source-height shard containing 3,339,820 events,
five interleaved runs gave these median worker times:

| Mode | literal reference | candidate | speedup |
|---|---:|---:|---:|
| summary | 1.522 s | 1.482 s | 1.026x |
| verify | 2.147 s | 1.592 s | 1.349x |
| two-pass total | 3.669 s | 3.074 s | 1.193x |

The old verify-minus-summary differential was about 0.63 seconds. Direct
squares remove almost all of that filter cost; primesieve, CRlibm, and the two
retained hashes then dominate. Hardware performance counters were unavailable
on this host, so this is an end-to-end attribution rather than a counter-level
profile.

## One-pass affine guard

Every shard state has the form `incoming + prefix_delta`. Therefore lower
endpoint safety is monotone in the incoming lower endpoint and upper endpoint
safety is antitone in the incoming upper endpoint. The independent worker
`reference/tg_psi_affine_guard_shard.cpp` makes one prime-power pass and emits:

- the same Q64 delta, event counts, event commitment, and row commitment as
  summary and verify mode;
- an exact conservative integer rectangle
  `lower_min <= incoming_lower <= incoming_upper <= upper_max`; and
- the zero-based shard event index, value, prefix delta, Q64 radius, guard
  kind, and strictness that attain each retained extremum.

It includes the reviewed two-pass source in the same translation unit, so
enumeration, CRlibm conversion, row encoding, and hashing are not duplicated.
The two-pass executable remains an independently invoked reference.

For an event value `x`, let `dL` be the shard lower-prefix delta before its
jump and `dU` the upper-prefix delta after its jump. Define

```text
r2 = floor(sqrt(2*x) * 2^16)
r1 = floor(sqrt(x)   * 2^16)
RL = r2 * 2^48
RU = floor(19764819 * r1 * 2^48 / 25000000)

lower requirement = max(0, x*2^64 - RL - dL)
upper allowance   = x*2^64 + RU - dU
```

The worker takes the maximum lower requirement and minimum upper allowance.
At the strict terminal lower check it subtracts one Q64 unit from `RL` exactly
when `r2^2 = (2*x)*2^32`. Binary64 `sqrt` only seeds each Q16 integer root;
exact u128 square-correction loops establish the returned floor.

The Q16 truncation deliberately gives a sufficient, slightly inward
rectangle rather than the mathematically largest Q64 rectangle. It loses less
than `2^-16` in either square root. This still contains the zero root of the
first bounded shard exactly at its lower boundary and contains the synthetic
source-height benchmark state with large margins.

`SparkInterval/TernaryGoldbach/PsiAffineGuards.lean` proves:

- monotonicity/antitonicity in the two incoming endpoints;
- the Q16-to-Q64 lower, strict-lower, and rational-upper square inequalities;
- conservative-radius implication of the exact endpoint predicates; and
- exact soundness of the native-shaped max-of-lower-requirements and
  min-of-upper-allowances folds, hence sufficiency of the retained extrema
  for every contained incoming state.

These are ordinary base-trio theorems. They do not prove that native rows,
extrema, or machine execution equal their Lean values.

`tests/tg_psi_affine_guard_known_answers.py` independently uses Python
`isqrt`, a loaded pinned CRlibm, and the literal prime-power roster. It checks
the exact Q16 radii, extremum indices and values, prefix deltas, commitments,
ordered root-derived merge, all two-pass gap decisions/fallback counts, and
the source-terminal strict branch. A separate 3,339,820-event source-height
replay matched both reported extrema exactly:

```text
lower witness: event 2,603,526, value 9,999,977,980,747
upper witness: event   422,190, value 9,999,912,623,969
```

That full fold is retained canonically, rather than only as console output, by
`tools/tg_psi_affine_guard_qualification.py`. The source-height qualification
artifact has SHA-256
`aff4bdce2fac9873b32ae25cd2beb49aeb48cdec84e71ef4bf428f273dcdcda5`.
It binds affine source SHA
`df760167a3abb3d30aa893fabee0e4272b6c84c5190c3c91112820ea0779323f`,
affine binary SHA
`eaedde3967c3331561943a882ce38d807f3505b1db7c68c3109dac12e5675fe5`,
the two-pass source and binary, pinned upstream manifest, loaded CRlibm
library, and the provenance manifest above. It retains two alternating
affine/summary/verify runs and the literal Python result for all 3,339,820
events. The literal enumeration and row/extremum fold took 55.33 seconds.

Normal `verify` regenerates the complete Python prime-power roster, every
loaded-CRlibm row, both commitments, every lower requirement, and every upper
allowance before comparing the global extrema. Thus an unreported tighter
event is detected. `--no-regenerate-oracle` is only a structural audit; it
still checks exact field sets, event cardinalities, u128 bounds and overflow,
both witness formulas and square inequalities, raw receipt bytes, all
cross-mode commitments/deltas, the build manifest's source/macro identities,
and the fail-closed capability boundary.

The benchmark tool additionally recomputes both reported witness equations and
radius-square inequalities from each retained receipt before comparing it with
summary and verify output.

Five interleaved source-height runs produced:

| Work | median |
|---|---:|
| affine one-pass | 1.612 s |
| optimized summary | 1.497 s |
| optimized verify | 1.593 s |
| optimized two-pass total | 3.089 s |
| affine versus two-pass | 1.916x |

The retained bounded benchmark artifact has SHA-256
`e57b85e2ff12cf81222b222ab923a4d9c9f72638de6f6447c18885ec628af751`.
Its single-process linear projection is 46.45 hours for 346,065,767,406
events, versus 88.60 hours for the optimized two-pass worker. These projections
do not model multi-process scaling and are not source executions or proofs.

## Fail-closed affine campaign supervisor

`tg_verifier/psi_affine_guard_campaign.py` turns independent affine worker
receipts into one ordered campaign record. Initialization captures the exact
runner, source, and upstream-manifest bytes and fixes a contiguous,
nonoverlapping shard plan. For the source range that plan has exactly 100,000
leaves of 100,000,000 integers, except for the final short leaf. Bounded plans
must be explicitly labeled tests.

Each receipt is checked against its plan leaf for the exact algorithm, atom,
upstream commits, range, sieve size, encodings, state components, field set,
event-count partition, Q64 delta order and coarse log bound, u128 safety,
attaining-witness equations, Q16 radius formulas, strict terminal
classification, and false trust flags. The retained object is the exact raw
byte string; replacing it with different bytes is rejected.

After all receipts exist, the supervisor performs an exclusive scan from the
only root `[0,0]`. For every shard it enforces

```text
lower_min <= incoming_lower <= incoming_upper <= upper_max
outgoing = incoming + delta
```

It rejects a missing, duplicate, out-of-plan, reordered, or overflowing
transition. Each ordered child binds its plan index and range, raw-receipt
SHA-256, event and row commitments, event counts, delta, affine rectangle,
witnesses, and derived incoming/outgoing states. Domain-separated SHA-256
commits the child records, their ordered Merkle tree, and the final
certificate. Verification regenerates the complete scan and all commitments
from the captured plan and raw receipts.

The local runner loads and hashes the captured executable/source closure once
per batch, keeps at most twice the requested worker count in flight, and
checkpoints each completed receipt. Deterministic strided worker groups let a
cluster cover every fixed-plan index exactly once without changing receipt
granularity. Production and non-tiny execution through the CLI requires the
measured-Azure worker scope; metadata-only command generation remains
available for orchestration.

`tests/test_tg_psi_affine_guard_campaign.py` covers the complete bounded
flow and attacks on algorithm/upstream pins, digests, trust flags, receipt
bytes, plan ranges, shard indices, root guards, u128 admission, event counts,
omission, extra files, and retained children. It also runs the old two-pass
supervisor on the same deterministic stream and compares every shard delta,
event commitment, row commitment, root-derived input/output, and the final
state.

This supervisor validates composition and binds reported worker output. It
does not independently replay every row, prove that the native executable
realizes the source, authenticate a physical execution, or discharge a Lean
atom. Its certificate capability flags remain false for all of those claims.
The literal qualification above supplies the independent all-row comparison
on the retained source-height range; measured execution and the Lean bridge
remain separate trust-boundary steps.

`SparkInterval/TernaryGoldbach/PsiAffineChildCertificate.lean` mirrors the
small supervisor arithmetic in Lean. Its kernel-reducible checker validates
the zero root, ordered indices and ranges, event partitions, rectangles,
additive transitions, u128 safety, final state, and (in source mode) the exact
100,000-leaf geometry and published event total. A separate
`RadiusSemantics` premise parameterizes the missing native-row realization.
Given that premise, the ordinary Lean theorem composes
`PsiAffineGuards.all_radius_safe_of_folds` over the checked child chain.
Thus the file proves the arithmetic bridge without pretending that compact
receipt hashes disclose or prove the rows they commit.

## Reproduction

The pinned CMake configuration exposes three targets:

```text
sparkinterval-tg-psi-residual-shard
sparkinterval-tg-psi-residual-shard-literal-reference
sparkinterval-tg-psi-affine-guard-shard
```

After building a shared view of the same pinned CRlibm archive for the Python
oracle, run:

```bash
python3 -m unittest -v \
  tests.test_tg_psi_lower_filter_equivalence \
  tests.test_tg_psi_two_pass_qualification \
  tests.test_tg_psi_affine_guard_receipt \
  tests.test_tg_psi_affine_guard_campaign

lake build \
  SparkInterval.TernaryGoldbach.PsiAffineChildCertificate
lake env lean \
  SparkInterval/Tests/PsiAffineChildCertificateTest.lean

python3 tests/tg_psi_affine_guard_known_answers.py \
  --affine-runner /path/to/sparkinterval-tg-psi-affine-guard-shard \
  --two-pass-runner /path/to/sparkinterval-tg-psi-residual-shard \
  --crlibm-shared /path/to/libcrlibm.so

python3 tools/tg_psi_affine_guard_qualification.py verify \
  /path/to/psi-affine-qualification.json \
  --affine-runner /path/to/sparkinterval-tg-psi-affine-guard-shard \
  --two-pass-runner /path/to/sparkinterval-tg-psi-residual-shard \
  --affine-source reference/tg_psi_affine_guard_shard.cpp \
  --two-pass-source reference/tg_psi_residual_shard.cpp \
  --crlibm-shared /path/to/libcrlibm.so \
  --upstream-manifest specifications/PSI_UPSTREAMS.json \
  --build-manifest /path/to/psi-qualification-build-manifest.json

python3 tools/benchmark_tg_psi_affine_guard.py \
  --affine-runner /path/to/sparkinterval-tg-psi-affine-guard-shard \
  --two-pass-runner /path/to/sparkinterval-tg-psi-residual-shard \
  --affine-source reference/tg_psi_affine_guard_shard.cpp \
  --two-pass-source reference/tg_psi_residual_shard.cpp \
  --lower 9999900000001 --upper-exclusive 10000000000001 \
  --repeats 5 --output /path/to/psi-affine-benchmark.json

python3 tools/tg_psi_affine_guard_campaign.py init \
  --runner /path/to/sparkinterval-tg-psi-affine-guard-shard \
  --runner-source reference/tg_psi_affine_guard_shard.cpp \
  --upstream-manifest specifications/PSI_UPSTREAMS.json \
  --output-dir /path/to/psi-affine-campaign

# The source-scale run/finalize/verify commands are executed inside the
# measured Azure worker scope.
python3 tools/tg_psi_affine_guard_campaign.py run \
  /path/to/psi-affine-campaign --workers 64
python3 tools/tg_psi_affine_guard_campaign.py finalize \
  /path/to/psi-affine-campaign
python3 tools/tg_psi_affine_guard_campaign.py verify \
  /path/to/psi-affine-campaign
```

The full two-pass qualification CLI is
`tools/tg_psi_two_pass_qualification.py`. See
`docs/algorithms/CH25_PSI_VERIFIER.md` for the source computation, campaign,
wire, trust boundary, and Azure execution context.
