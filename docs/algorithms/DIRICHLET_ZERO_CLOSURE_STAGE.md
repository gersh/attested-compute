# Dirichlet completed-value, upsampling, and count closure

This directory now has an executable, range-general reference boundary for the
part of Platt's Theorem 7.1 computation after character values have been
formed. It is deliberately split into two layers:

1. `tg_verifier/dirichlet_postprocess.py` consumes interval values from the
   separately implemented all-character transform, reconstructs Platt's completed real value,
   evaluates a finite Whittaker--Shannon sinc sum with explicit alias and tail
   budgets, and evaluates a conjugate-paired Turing window formula.
2. `tg_verifier/dirichlet_zero_closure.py` and its role-separated producer and
   checker provide a slow direct-Arb fallback. They recompute Hardy Z at every
   sample, isolate strict sign changes, and use an argument-principle count.

Neither layer closes the external theorem atom. No full-source campaign has
run, and the persistent transform-to-completed-value composition and the
uniform interpolation proof remain open. The reflected Turing normalization now
has a written derivation and a multi-conductor identity KAT
([DIRICHLET_TURING_REFLECTED_BOUND.md](DIRICHLET_TURING_REFLECTED_BOUND.md)),
but its Lean realization is still missing.

## Exact source mapping

The formulas follow [Platt, arXiv:1305.3087v1](https://arxiv.org/abs/1305.3087v1).
Production parameters come from the later
[Bristol accepted manuscript](https://research-information.bris.ac.uk/ws/portalfiles/portal/67056136/platt_grh3.0.pdf),
which is cited separately because those details are absent from arXiv v1:

| Executable component | Source location | Implemented statement |
|---|---|---|
| Completed value | Section 1 displayed definition | `epsilon_chi (q/pi)^(it/2) Gamma((1/2+a_chi+it)/2) exp(pi t/4) L_chi(1/2+it)` |
| Sampling rate | Section 7 | Base step `5/64`; escalation factors `8`, `32`, `128`, `512` |
| Finite sinc sum | Theorems 6.1--6.2 | `sum_n W(n/(2B)) sinc(2 B pi (t0-n/(2B)))` over consecutive retained samples with at least `N` on each side of `t0` |
| Aliasing budget | Lemmas 6.4--6.5 | The printed `I_chi` bound with `M=5/2-a_chi` and the explicit upper bound for `P(t0,h)` |
| Truncation budget | Lemmas 6.6--6.7 | The printed `G(0)/(1-G(1)/G(0))` geometric bound and final zeta/gamma constant |
| Turing count | Theorems 3.1--3.3 | Booker's counting function at `+t0` minus at `-t0`, reflection of the negative window to the conjugate character, `1/(h*pi)` on the elementary/log-gamma group and `1/h` on the multiplicity-weighted zero staircases and `S` integrals, and Rumely's published `1.8397 + 0.1242 log(q(t0+h)/(2pi))` bound. The display's `+2h` is refuted and excluded; see [DIRICHLET_TURING_REFLECTED_BOUND.md](DIRICHLET_TURING_REFLECTED_BOUND.md) |
| Exceptions | Section 7 | Precision escalation, direct Arb recomputation, grid-point splitting, post-512 refinement, and fail-closed window retry boundary |
| Production sinc parameters | Accepted manuscript Sections 8--9 | `A=64/5`, hence `B=32/5`; Gaussian `h=7/32`; 20 samples on each side; claimed error `<8.6e-8` |

The code uses exact integer/rational inputs and pinned python-flint 0.9.0 /
FLINT 3.6.0 for all transcendental enclosures.

## Completed-value composition contract

The ordinary path does not call `hardy_z`. A completed-value request must carry
an interval rectangle for `L_chi(1/2+it)` and an interval root number, plus four
explicit upstream gates:

- the `q^(-s)` factor was applied;
- the omitted finite Dirichlet terms were added back;
- the primitive frequency was checked against the canonical Conrey identity;
- the root number was certified for that character.

It also carries the primitive-character ordinal and four SHA-256 commitments:
the all-character stage receipt, lattice/tail receipt, finite-addback receipt,
and root-number receipt. The adapter recomputes the canonical ordinal-to-Conrey
and parity mapping before doing any analytic arithmetic. This makes the future
all-character composition hash-bound instead of passing anonymous rectangles.

The stage then applies the conductor phase, square-root root-number phase,
gamma factor, and `exp(pi t/4)` scale. It accepts a strict sign only when the
completed imaginary rectangle contains zero and the real rectangle excludes
zero. The independent checker freshly evaluates raw `L` and FLINT Hardy Z and
requires overlap up to the one fixed square-root sign. Direct FLINT is thus an
exception/checker oracle, not the ordinary producer.

Those four Boolean gates are a composition boundary, not self-authenticating
proofs. A production all-character receipt must bind them to its lattice,
finite-addback, CRT/Bluestein, primitive-frequency, and Gauss-sum artifacts.

## Rigorous upsampling boundary

For `W(t)=Lambda_chi(t) exp(-(t-t0)^2/(2h^2))`, the evaluator computes the
finite sinc sum with outward Arb arithmetic. It adds two separately retained
nonnegative budgets:

- the Weiss alias budget from Lemmas 6.4--6.5;
- the geometric truncation budget from Lemmas 6.6--6.7.

The output records the finite sum, both budgets, total enclosure, strict sign,
and whether the ordinary or exception path was used. There is one source-level
blocker: Lemma 6.7 says only "for large enough `t0`" and gives no numerical
threshold. The arithmetic formula is executable, but `production_accept`
remains false unless a separate reviewed theorem discharges that condition.
It must not be replaced by an unreviewed guessed threshold.

The accepted-manuscript parameter KAT uses the actual primitive odd-character
case `q=3` at source height `10^8/3`. The implemented Lemmas 8.4--8.7 budgets
sum to about `8.4123e-8`, strictly below the manuscript's `8.6e-8` claim. This
checks one source case and the exact parameter interpretation; it is not yet a
uniform reproof over every `q`, parity, and ordinate. The simple printed bounds
for some other endpoint combinations require a tighter or case-specific
argument, so the uniform claim remains an explicit review item.

## Multiplicity-preserving Turing window

Each zero bracket in `[t0,t0+h)` carries an explicit positive multiplicity.
The staircase integral uses interval ordinates, so its uncertainty propagates
outward. The conjugate character has a separate list; no silent deduplication
is allowed. The fresh checker treats every strict bracket as a multiplicity
lower bound of one. The log-gamma integral is evaluated rigorously, and the
Rumely bound is applied once to each character. The decision is non-circular:
observed future brackets lower-bound the true staircase and therefore
upper-bound the zero count below `t0`; if that upper bound is below the next
integer above the already certified isolated count, completeness follows.

The arXiv v1 Theorem 3.2 display is wrong in two independent ways, and the
derivation, the numbers, and the remaining Lean obligations are now written out
in [DIRICHLET_TURING_REFLECTED_BOUND.md](DIRICHLET_TURING_REFLECTED_BOUND.md).
In summary:

- **Common denominator (typesetting erratum).** Putting the zero-staircase and
  the already `1/pi`-normalized `S_chi` integrals behind the same `1/(h*pi)` as
  the elementary/log-gamma terms divides them by `pi` a second time. On the
  real primitive q=3 window `t0=60`, `h=100` the literal display yields an
  interval near 86 where two independent argument-principle winding counts give
  exactly 44. The elementary/log-gamma group carries `1/(h*pi)`; the staircase
  and `S` groups carry `1/h`. Platt's own released program agrees, so the
  computation he ran used the correct scaling.
- **The displayed `+2h` (spurious, but conservative).** Under the corrected
  scaling it contributes a constant `2/pi = 0.63662`. The identity derived from
  Booker Theorem 3.1, and Trudgian's independent display (2.3), have no such
  constant. It is no longer included in the executable bound.

The executable candidate derives the symmetric count by evaluating Booker's
counting function at `+t0` and `-t0` and subtracting. The negative window is
reflected to the positive window for `bar-chi` using
`L_bar-chi(conj s)=conj(L_chi(s))`; equivalently `S_chi(-t)=-S_bar-chi(t)`.
The subtraction cancels the arbitrary `arg(epsilon)` term, so no numerically
fitted phase anchor is consumed.

The `+2h` term is refuted, not merely unproved. With a complete
exact-multiplicity bracket list and an exactly known `N_chi(t0)`, the corrected
display is an equality whose residual must be `(int S_chi + int S_bar-chi)/h`,
which Rumely's Theorem 3.3 bounds. The multi-conductor KAT certifies both
endpoint counts by winding, certifies completeness by matching the bracket
total against the winding difference, and finds residuals between `-0.0348` and
`+0.0031` against envelopes between `0.0476` and `0.1213`. Shifting each
residual by `-2/pi` breaks the envelope at every row by a factor of 5 to 13.
The rows cover both parities, real characters and genuine complex conjugate
pairs, and two window shapes.

Two audit quantities are still emitted so a reviewer can see the discrepancy
rather than have it silently erased: `literal_arxiv_v1_typeset_interval` (the
printed display) and `platt_released_code_upper_bound` (the corrected bound
plus the released program's `+2/pi`).

The accepted manuscript repeats the common-denominator display and no published
erratum was found. Until the derivation is connected to the Lean
multiplicity-count contract, `literal_paper_theorem_3_2_accepted` and
`production_accept` stay false; the analytic half alone does not authorize
either flag. The direct argument-principle fallback does not depend on this
issue.

## Commands

```bash
python3 tools/tg_dirichlet_zero_closure.py --pretty capability
python3 tools/tg_dirichlet_zero_closure.py known-answer-request /tmp/request.json

.venv-tg-flint/bin/python tools/tg_dirichlet_zero_closure.py run \
  /tmp/request.json /tmp/result.json /tmp/receipt.json

.venv-tg-flint/bin/python tools/tg_dirichlet_postprocess.py --pretty capability
.venv-tg-flint/bin/python tools/tg_dirichlet_postprocess.py produce \
  /tmp/post-request.json /tmp/post-result.json
.venv-tg-flint/bin/python tools/tg_dirichlet_postprocess.py verify \
  /tmp/post-request.json /tmp/post-result.json /tmp/post-receipt.json

.venv-tg-flint/bin/python tools/benchmark_tg_dirichlet_postprocess.py --pretty
```

The direct fallback has q=3,4,5 KATs, including the complex conjugate pair
modulo 5. At height 10 the multiplicity counts are respectively `2`, `2`, and
`4,4,4`. On the local DGX Spark, the five-character producer took 44.48 seconds
and the producer-plus-fresh-checker run took 88.04 seconds. This is a tiny KAT,
not a source-scale throughput projection.

The postprocess microbenchmark on the same host measured:

| Path | Work unit | Local sample rate |
|---|---|---:|
| Ordinary sinc | completed-value intervals | 100,985/s |
| Direct exception | FLINT Hardy-Z signs | 6,566/s |
| Turing arithmetic | paired windows with 126 retained brackets | 694/s |

These rates exclude lattice generation, the all-character transform, interval
I/O, source parameter optimization, attestations, and the full campaign.
The ordinary-sinc rate is **per input term accumulated into one direct sum**.
It is not a factor-eight target rate and not a completed-\(L\) construction
rate. The former sizing calculation that divided
`1,571,337,544,104,271` target coordinates by 100,985/s was therefore
dimensionally invalid.

[DIRICHLET_FACTOR8_POSTPROCESS.md](DIRICHLET_FACTOR8_POSTPROCESS.md) now
implements the routine \(8\times\), forty-tap finite convolution as a bounded
directed CUDA sign reducer. Its exact work audit distinguishes
`196,430,125,886,102` base completed-value intervals,
`1,374,907,418,218,169` nonaligned targets, and
`54,996,296,728,726,760` interval products. A local GB10 median of
350,576,168 target samples/s projects to 155.63 ideal hours on eight equal
GB10s. This is a synthetic kernel projection only: upstream completed values,
I/O, the uniform interpolation theorem, exception factors, source replay, and
zero/Turing closure remain outside it.

## Exact remaining work

1. Certify the Section 4 Hurwitz lattice, Taylor tails, finite addback, and
   `q^(-s)` factor for every source ordinate.
2. Implement and certify the all-character CRT/Bluestein interval FFT and the
   Section 5 small-q path.
3. Bind primitive frequency/Conrey identities and root-number Gauss sums into
   each completed-value request.
4. Supply a reviewed explicit hypothesis discharging Lemma 6.7's "large
   enough `t0`" condition, or replace that tail bound with a fully explicit
   proved bound.
5. Formalize the corrected reflected Theorem 3.2 identity in Lean (the
   derivation and the itemized obligations are in
   [DIRICHLET_TURING_REFLECTED_BOUND.md](DIRICHLET_TURING_REFLECTED_BOUND.md) §7),
   connect its multiplicity count to the Lean distinct-zero upper bound, and
   implement the exact source-approved window-shift/retry policy.
6. Run all source characters and retain accepted, independently replayed
   receipts.
7. Prove the Lean realization from completed-L signs and multiplicity counts to
   the named external proposition.

Until all seven items are complete, `production_ready`, `full_source_run`, and
`external_atom_discharged` remain false.
