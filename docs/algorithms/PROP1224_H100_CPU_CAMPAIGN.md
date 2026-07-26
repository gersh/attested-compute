# Proposition 12.2.4 CPU/H100 campaign

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

This implementation replaces the serial Python supervisor for the finite
part of Helfgott Proposition 12.2.4 with independent, plan-bound source-rank
leaves. It is capable of traversing the literal source domain:

```text
q = 1, 2, ..., 3,299,999,999
then q < 22,000,000,000 with 210 | q
total q rows = 3,389,047,618
```

It remains an external computation. The repository now has an exact
source-shaped Lean scheduler/certificate semantics and a closed conditional
CPU/SEV-SNP receipt bridge. A completed campaign does not by itself construct
the bridge's explicit `ExternalShardRealization.mpfrGmpRows` evidence: the
MPFR/GMP evaluator-to-exact-real refinement must be reviewed and supplied at
receipt import.

## Implemented executables

`sparkinterval-tg-prop1224-mpfr-shard` is the final directed CPU worker. For
each complete q row it recomputes:

- the complete distinct prime factorization and `phi(q)`;
- outward MPFR intervals for every logarithm, exponential, real power and
  cube root in the source formulas;
- the theorem-backed intervals for Euler's constant and Ramaré's `c_E`;
- the conservative integer interval containing `[varpi(q), lambda(q))`;
- exact segmented `phi(r)` and squarefreeness;
- a GMP integer enclosure of `G_q(k)` at scale `2^precision`; and
- every retained lower bound for `RHS - LHS`, failing immediately if one is
  negative.

The production precision is 192 bits. Every transcendental and algebraic
endpoint is rounded outward by MPFR. No binary64 value controls a proof
decision. The runner emits a domain-separated SHA-256 commitment and keeps
`execution_attested`, `lean_realization_proved`, and `lean_atom_discharged`
false.

`sparkinterval-tg-prop1224-factor-shard` is a separate exact audit stage. It
uses segmented Eratosthenes factorization and commits complete distinct prime
factors and `phi(q)` at roughly 1.5--2.0 million q rows/s on the local ARM
host. It is explicitly a structural prefilter, not the final inequality.

The H100 kernel interface in
`gpu/include/sparkinterval/tg_prop1224_factor.hpp` replays scheduler, packed
factor product and totient identities in parallel. It deliberately does not
claim primality; acceptance still requires the CPU Eratosthenes replay. The
rigorous transcendental worker currently runs on CPUs, so adding H100s does
not linearly accelerate this atom.

## Fixed plan and receipts

The production plan has 12,930 leaves of at most 262,144 q rows. It isolates
`q=1` as leaf zero and never crosses the dense/210-divisible scheduler
boundary. The plan identity binds:

- exact rank ranges and ordering;
- 192-bit arithmetic precision;
- MPFR version 4.2.1; and
- the SHA-256 of the C++ directed runner source.

Each receipt additionally binds the runner executable hash. The merger
requires one executable hash across the campaign and uses an affine exclusive
scan plus domain-separated Merkle tree. Missing, duplicate, reordered or
range-substituted leaves fail closed. Segment size is only a resource choice;
known-answer tests prove that changing it does not change the arithmetic
commitment.

Build on a host with MPFR and GMP development files:

```bash
cmake -S . -B build/prop1224 \
  -DSPARKINTERVAL_BUILD_TG_PROP1224=ON \
  -DSPARKINTERVAL_BUILD_TG_PROP1224_MPFR=ON
cmake --build build/prop1224 --target \
  sparkinterval-tg-prop1224-factor-shard \
  sparkinterval-tg-prop1224-mpfr-shard -j
ctest --test-dir build/prop1224 -R tg_prop1224 --output-on-failure
```

Inspect the immutable production plan, run one four-way worker group, and
merge all logical-leaf receipts:

```bash
python3 tools/tg_prop1224_mpfr_campaign.py plan
python3 tools/tg_prop1224_mpfr_campaign.py run-worker-group \
  build/prop1224/sparkinterval-tg-prop1224-mpfr-shard \
  /durable/prop1224-mpfr 0 --worker-group-count 4 --workers 96
python3 tools/tg_prop1224_mpfr_campaign.py verify \
  /durable/prop1224-mpfr
```

The cluster scheduler may assign the four groups in any wall-clock order.
Each group preserves its canonical logical-leaf receipts, and the merger runs
only after all 12,930 are present.

## Measured performance

Measurements below were taken on 2026-07-21 on the 20-core ARM host (ten
Cortex-X925 and ten Cortex-A725 cores), using one process and MPFR 4.2.1 at
192 bits.

| Slice | Result | Wall time |
|---|---:|---:|
| isolated `q=1` | 23,278,583 r steps; 23,207,009 margins; minimum lower bound about 0.0233 | 169.374 s |
| representative `q=6,469,693,230` | 721 r steps; 136 margins; minimum lower bound about 1.15556 | 0.00132 s |
| 100,000 dense q rows near `10^9` | all empty windows | 6.929 s |
| 100,000 dense q rows near `3.29*10^9` | all empty windows | 7.362 s |
| 100,000 extension rows near rank `3.30*10^9` | 99,999 empty; one nonempty | 7.771 s |
| 100,000 extension rows near rank `3.38*10^9` | all empty windows | 7.942 s |

Log-spaced empty-row samples put one full q traversal at roughly 61--73
single-core hours. The production model deliberately keeps the wider
105.6--640 core-hour range per replay to allow for the isolated `q=1` work,
nonempty rows, scheduler effects, and measurement uncertainty. The measured
protocol performs two complete replays. Its fixed physical topology is four
confidential `Standard_DC96as_v6` nodes with 96 worker processes per node, so
the conservative compute envelope is 211.2--1,280 aggregate core-hours, or
about **0.55--3.34 ideal wall-clock hours** before Azure control-plane and
attestation overhead. The isolated q=1 leaf takes 2.82 minutes and does not
determine that range.

At the 2026-07-21 East US 2 prices recorded by the campaign model, the
four-node fleet costs $17.432 per hour PAYG or $3.221432 per hour Spot. The
compute-only range is therefore about **$9.59--$58.22 PAYG** or
**$1.77--$10.76 Spot**. This excludes storage, networking, MAA and Managed HSM
charges, allocation delays, retries, and price changes.

## Lean handoff and remaining trust work

[`Prop1224SourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/Prop1224SourceSemantics.lean)
copies the literal `G_q`, `c_E`, `f_1`, window and error proposition, proves
that the closed rank scheduler covers every admissible `q`, checks gap-free
shard coverage, and derives the exact source claim from explicit per-shard
MPFR/GMP realization evidence. The closed registered invocation
`helfgottProp1224ProductionV1` is restricted to Azure SEV-SNP CPU receipts;
`RegisteredProp1224Certificate.lean` exposes the source claim only for the
exact successful result `true`. The failure result `false` witnesses that the
registered execution relation is satisfiable and proves no mathematics.

No successful receipt or source-scale `ExternalShardRealization` is included,
and the Azure portfolio semantic row remains disabled. The source theorem uses
only Lean's foundational axioms; its signed wrapper adds exactly the single
project axiom `Trusted.accepted_run_certificate_sound`.

The bounded Python reference and the C++ runner agree on the representative
complete row, and the C++ known answers cover dense, extension and scheduler
boundary ranges. Before treating a production run as evidence for the Lean
theorem, the release still needs:

1. an independently reviewed construction of each shard's explicit
   `ExternalShardRealization.mpfrGmpRows` field from the retained MPFR/GMP
   artifacts;
2. attested execution and durable publication of all receipt and Merkle roots;
3. a second implementation or replay of the retained production artifacts;
   and
4. a fresh `#print axioms` audit in the consuming ternary-Goldbach project.
