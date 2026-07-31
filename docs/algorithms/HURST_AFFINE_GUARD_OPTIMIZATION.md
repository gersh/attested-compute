# Hurst affine-guard CPU optimization

The Hurst adapter has an exact, source-shaped `affine` mode that computes the
set of incoming prefix states for which one independently sieved shard proves
all four shared residuals.  It now uses:

- fixed `2^20`-row blocks now compute their guards in parallel;
- block guards are translated by exact prefix deltas and intersected in
  increasing block order, preserving the earliest witness on equal bounds;
- incrementally advanced exact floor roots are shared by the Hurst,
  squarefree, and little-Mertens filters instead of evaluating a floating
  square root for every endpoint;
- the conservative squarefree filter uses signed 128-bit arithmetic, whose
  largest source-domain intermediate remains below `2^127`, instead of an
  arbitrary-precision division at every endpoint; and
- above `438429`, the exact `57/2000` squarefree interval is contained in the
  `151/2000` interval, so constructing the stronger guard once proves both
  inequalities; and
- a cheap integer inner radius filters little-Mertens endpoints.  Because the
  inner interval is contained in the exact interval, failure to tighten the
  inner interval proves that the exact interval cannot tighten either.  A
  multiprecision square root is evaluated only when an exact endpoint may
  actually change.

These are exact transformations.  They do not replace an interval by a
floating-point estimate and do not change the Möbius row encoding, SHA-256
commitment, transition delta, or tight-witness policy.

The later real-slab proof exposed one boundary error in the original contract:
for a strict lower threshold `t < x`, checking only the right limit at `t+1`
does not cover `t < x < t+1`.  Protocol V2 therefore checks the squarefree
value at every `n >= t` as well as its right limit at `n+1`.  The worker emits
`squarefree_threshold_endpoint_policy =
"inclusive-value-and-right-limit-v2"`; the supervisor rejects V1 receipts.
This strengthens the guard and deliberately changes the registered algorithm
hash, while leaving the row stream and transition arithmetic unchanged.

## Local benchmark

The reference and optimized executables were built from the same pinned Hurst
commit on the 20-core ARM CPU in the DGX Spark host.  The command shape was:

```bash
OMP_NUM_THREADS=8 ./sparkinterval-tg-hurst-residual-shard \
  --mode affine --lower 1 --upper 20000000 --segment-size 20000000
```

The first optimization reduced `[1, 20,000,000]` from about 32 seconds to
2.76 seconds.  The incremental-root/inner-radius pass on 2026-07-25 reduced
the same affine run to a five-run median of 0.2900 seconds.  The corresponding
summary and exact-verify medians were 0.0751 and 0.1879 seconds.  Thus affine
construction is about 10% slower than two passes on this exceptional low
slice, where both little-Mertens guards are active.

On the 20-million-row terminal slice
`[9,999,999,980,000,001, 10^16]`, three-run medians were 0.7251 seconds for
summary, 0.7977 seconds for verify, and 0.8702 seconds for affine.  The
one-pass route is therefore about 1.75x faster than two arithmetic passes on
the part of the source domain where only Hurst and squarefree guards remain.
Only the first `10^12` of `10^16` rows activate the `2.11` little-Mertens
coordinate, so the terminal-range comparison is the more representative
bounded pilot.  It is not a full-source ETA.

A four-shard `[1, 20,000,001)` campaign with five-million-row leaves had
medians of 0.7108 seconds for affine arithmetic and 0.0472 seconds for affine
finalization.  Summary plus verify arithmetic took 0.6773 seconds and its
reducer/finalizer took 0.0444 seconds.  This confirms that the low-range
near-tie is arithmetic rather than supervisor overhead.

Process-level scaling was measured separately on four disjoint
20-million-row terminal slices.  Running the four slices as one process with
20 threads, two processes with 10 threads each, and four processes with five
threads each took medians of 4.0891, 2.2606, and 1.4464 seconds respectively,
or 19.56, 35.39, and 55.31 million aggregate rows per second.  This favors
more leaf processes over assigning every core to one leaf on this host.

The literal 10,000-leaf supervisor was also exercised with synthetic,
explicitly non-evidentiary receipts.  It finalized the exact plan in 6.03
seconds and independently replayed it in 3.05 seconds.  The single canonical
leaf bundle was 14,777,863 bytes and the root-derived scan was 11,114,901
bytes.  This test checks control-plane scaling only; its synthetic row
commitments are not arithmetic evidence.

Every compared receipt was structurally identical after removing only the
nondeterministic `elapsed_seconds` field.  In addition to the fixed known
answers, old/new affine receipts matched byte-for-byte on 16 deterministic
bounded ranges spanning both squarefree thresholds, the stronger
little-Mertens endpoint, `10^12`, and the terminal source region.  A
multi-segment comparison also matched exactly.
`tests/tg_hurst_residual_known_answers.py` crosses a
reduction-block boundary and requires one-thread and four-thread affine
receipts to agree exactly.  It also uses a crafted incoming squarefree count
that is safe at right limit `438430` but unsafe at threshold value `438429`;
V1 accepted that row and V2 rejects it, so the boundary test does not rely
only on the worker's self-reported protocol label.

These timings measure bounded affine guard construction and local certificate
replay, not the complete production campaign, Azure networking, attestation,
or physical row realization.

## One-pass source supervisor

`tg_verifier/hurst_affine_campaign.py` and
`tools/tg_hurst_affine_campaign.py` implement the separately versioned
`hurst-segmented-mobius-affine-four-residual-campaign-v1` route.  The plan
still contains exactly 10,000 gap-free half-open leaves covering
`[1, 10^16 + 1)`.  Every retained affine receipt is checked against its exact
plan range, segment geometry, row encoding, source version, four-coordinate
delta bounds, per-atom guard shape, witness regime, and explicit negative
trust-boundary fields.

The source-wide implication is:

1. A realized worker receipt says that its committed primitive rows have the
   reported additive delta and that every row satisfies one atom whenever the
   incoming state lies in that atom's guard.
2. The supervisor derives the incoming state of every leaf exclusively from
   root `(0,0,0,0)` and all preceding deltas.  No worker supplies this state.
3. It requires that derived state to lie in each of the four atom guards and
   uses their coordinatewise intersection as the generic affine guard.
4. Exact gap-free coverage and additive chaining then supply
   `LocalSourceScaleEvidence`, conditional on the row-realization premise in
   step 1.
5. Ordinary Lean theorem `checked_real_source_claims_of_local` converts that
   evidence into Hurst, squarefree B1, squarefree B2, little-Mertens 2.11, and
   stronger little-Mertens real inequalities.  These are the five fields
   belonging to the four shared external atom profiles.

The final certificate says
`source_rows_replayed_independently = false`,
`physical_row_realization_pending = true`,
`execution_attested = false`, and `lean_atoms_discharged = false`.  Its
generic tight witnesses are explicitly labeled structural encodings.  The
algorithm-specific witnesses remain in each raw worker receipt.  Independent
replay re-reads the captured binary/source/upstream identities, fixed plan,
all 10,000 receipts, root-derived scan, canonical leaf bundle, and final
hashes, but does not pretend that a SHA-256 row commitment proves its own
preimage.

The shared affine certificate caches immutable plan and leaf hashes.  Without
that cache, constructing 10,000 leaves repeatedly serialized the complete
10,000-range plan and was accidentally quadratic.  The cached form produces
the identical domain-separated digests.

## Azure operational route

`azure_cpu_hurst_affine_workload_factory.py` and
`tg_hurst_affine_azure_measured_workload.py` define four closed SEV-SNP CPU
phases:

1. `initialize-affine`;
2. 320 `affine-shards` worker groups;
3. `finalize-affine-certificate`; and
4. `replay-affine-certificate`.

The existing Hurst materializer recognizes these exact factory records,
packages the new supervisor and measured adapter in the reviewed source
closure, and self-checks that summary, verify, and affine modes reproduce the
same bounded row commitment and delta.  Every phase is operational-only,
including the last replay: all have `registered_invocation = none`, reject a
semantic binding, and return canonical JSON pinning their retained export.
No public portfolio manifest or registered Hurst identity was repinned.

The current 320-group, two-process-by-20-thread shape is a closed pilot shape,
not yet a calibrated production schedule.  A direct linear extrapolation from
the local process-scaling pilot puts one group's roughly 31.25 trillion rows
well above its 48-hour timeout.  Azure `Standard_DC96as_v6` performance must
be measured before launch, and the operational group count and process/thread
split should then be increased if necessary.  Repartitioning worker groups
does not change the 10,000-leaf mathematical plan or any leaf receipt, but it
does change the operational factory identities and predecessor graph.  The
repository therefore does not claim that the current timeout/layout has
already been production-calibrated.

## Trust and capability boundary

The registered two-pass supervisor continues to accept only `summary` and
`verify` receipts.  `validate_runner_receipt` rejects an `affine` receipt as
the wrong phase, and a focused protocol test holds that fail-closed boundary.
The separate one-pass supervisor cannot write the registered literal `true`.
Therefore this optimization does not silently relabel affine receipts as
evidence for the registered production atom.

`SparkInterval/TernaryGoldbach/HurstAffineCertificate.lean` now supplies the
small Lean arithmetic boundary.  Its reducible checker validates half-open
block chaining, componentwise delta bounds, exact four-coordinate prefix
addition, incoming guard membership, and the claimed final state.  The theorem
`Certificate.checker_sound` turns Boolean acceptance into precisely that
`ArithmeticValid` proposition.  The regression test constructs a two-block
certificate with `by decide` and runs `#print axioms` on the checker theorem
and both physical wrapper theorems; they use only Lean's standard `propext`
foundation and no project axiom or `native_decide`.

The original physical API, `ExternalBlockRealization`, accepted one combined
row predicate for every guard-admissible incoming state.  Instantiating that
predicate with `SourceRowPredicate` was too strong: its `PrefixRealization`
conjunct says that the state is the unique global source prefix, whereas an
affine guard can contain many states.  That API and its
`SourceScaleEvidence` wrapper remain available only for compatibility; they
are no longer used by the registered Hurst route.

Production instead uses `ReplayBlockRealization`.  It separates two facts:

- `rowDeltaValid` binds every replay row to its primitive Möbius, squarefree,
  and directed-Q96 increment; and
- `rowSafe` proves only the finite integer fallback decisions at the locally
  replayed state.

`ReplaySourceScaleEvidence` adds literal `[1, 10^16 + 1)` coverage and fixes
the root state to zero.  Its concrete Hurst alias is
`LocalSourceScaleEvidence`.  The `rowSafe` premise is still intentionally
universal over guard-admissible incoming states: this is the finite affine
guard claim made by the physical worker, and it cannot be derived from a
block's endpoint delta alone.  Production two-pass certificates use
root-derived singleton guards.  Crucially, this premise no longer asserts
global prefix semantics for those states.

`checked_full_source_claims_of_local` closes the remaining composition step in
ordinary Lean.  The primitive recurrence reconstructs the unique global
Mertens and squarefree prefixes along the one checked chain, and additively
composes the directed Q96 enclosures while they are active.  The worker freezes
the two little-Mertens coordinates after `10^12`; `PrefixRealization` now
requires those enclosures only through that exact active range.  Requiring
them through `10^16`, as the older combined predicate did, was not satisfiable
by the reviewed worker.  The full-range theorem still produces every natural
endpoint `1 <= n <= 10^16`, with the little-Mertens realization used only
where a little-Mertens claim consumes it.

`SparkInterval/TernaryGoldbach/HurstSourceSemantics.lean` fixes the concrete
row meaning used by the source worker.  It defines the exact Mertens,
squarefree, and little-Mertens prefixes, directed Q96 realization, and the
arbitrary-precision fallback inequalities for all four atoms.  Its theorem
`checked_full_source_claims_of_local` converts the checked local replay into a
source predicate at every natural endpoint through `10^16`; its fresh axiom
audit contains only the foundational trio.  The older
`checked_full_source_claims` theorem is retained for callers of the
compatibility API.

The same module now completes the finite-arithmetic-to-real bridge.  It proves
the production theorems `checked_hurst_real_of_local`,
`checked_little211_real_of_local`, `checked_little_stronger_real_of_local`,
`checked_squarefree_b1_real_of_local`, and
`checked_squarefree_b2_real_of_local` with the source ranges and constants.
The squarefree slab proof uses the V2 left-value/right-limit pair, and
`densityEnclosure_six_div_pi_sq` proves the worker's directed enclosure of
`6/π²` from Mathlib's 20-decimal `π` bounds.  No `native_decide` or new
axiom occurs in these theorems.
`checked_real_source_claims_of_local` packages all five inequalities, and
registered theorem
`hurstSharedFourResidualProductionV2_realClaims` returns that capstone
directly.  The rewrite lemmas `mertensStep_eq_sourceSum`,
`littleMertensStep_eq_sourceSum`, and `squarefreeStep_eq_sourceSum` expose the
literal finite-sum forms used by `claude_math`, making its downstream import
theorems definitional rewrites rather than new arithmetic proofs.  The
uninhabited production obligation remains the local primitive-row and
finite-guard evidence packaged by `LocalSourceScaleEvidence`, obtainable only
from the exact V2 registered run.

`tools/generate_trusted_compute_lean.py` recognizes that exact V2 invocation.
It fail-closes on the registered algorithm, input, parameter, domain, backend,
literal result `true`, and output hashes, then emits `registeredRun` and the
application theorem `exactMathematicalResult : RealSourceClaims`.  The source
receipt registry is still empty: the generator support is a checked handoff
for a future reviewed receipt, not evidence that the full run has occurred.
No receipt, verifier key, or positive production instance is supplied by this
repository.

The terminal campaign command now has an equally closed byte handoff.  The
`verify --registered-result-output PATH` form first replays the complete
certificate under the campaign lock and refuses bounded, incomplete, or
non-source campaigns.  Only then does it exclusively create the four bytes
`true`, without a newline; a caller cannot choose those bytes and an existing
file is never overwritten.  The reviewed phase DAG fixes that path as
`${TG_RUN_ROOT}/mertens-hurst/registered-result.txt`.

This closes the terminal-output contract, not the distributed execution
boundary.  The current CPU operator accepts one registered semantic invocation
per measured job, whereas Hurst has 10,000 dynamic summary jobs, a reducer,
10,000 dynamic verification jobs, a finalizer, and the semantic terminal.  An
honest scalable materializer therefore still needs operational-only signed
phase receipts plus immutable dependency-output handoffs, followed by one
source-reviewed terminal verifier that replays the complete artifact set.  The
terminal receipt alone may instantiate the Lean execution axiom.  Treating
each dynamic leaf as the full Hurst registered invocation, or merely pointing
the CDEM single-job materializer at the phase DAG, would be unsound.
The concrete operational/semantic receipt split and immutable artifact-handoff
design is documented in
[`HURST_AZURE_CPU_MATERIALIZER_DESIGN.md`](HURST_AZURE_CPU_MATERIALIZER_DESIGN.md).

The reviewed V2 identity is:

| Field | Exact value |
| --- | --- |
| algorithm SHA-256 | `d5fa24d80d95216208ff8e8bbacb42ec181966b40e6a577dae26d585c09df5aa` |
| input SHA-256 | `84cad6505119c2498b1213c73c13e379ebcc0e8bbd2d445d1539d45ec06fc5b7` |
| parameters SHA-256 | `78f8cf9ecdcac464c1711f877c57e31518dd66d6070882fb6de1d2a199068d1d` |
| domain SHA-256 | `fbbe3abc2d158bebb2a9f9b06c0379c3fd9eff168c86c9900a7997172ec91f0a` |
| result | `true` |
| output SHA-256 | `b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b` |

After the production receipt has first passed source-registry admission, the
application module is generated with:

```bash
python3 tools/generate_trusted_compute_lean.py \
  /reviewed/hurst-v2/trusted-compute-receipt.json \
  --namespace HurstSharedFourResidualV2 \
  --registered-invocation hurstSharedFourResidualProductionV2 \
  --out build/trusted-compute/HurstSharedFourResidualV2.lean
```

The intended downstream rewrites are explicit:

| Local capstone field | Normal form | `claude_math` source object |
| --- | --- | --- |
| `RealSourceClaims.hurst` | `mertensStep_eq_sourceSum` | PrimeNumberTheoremAnd's `_root_.M` used by `mertensM_hurst_sqrt_source` |
| `RealSourceClaims.squarefreeB1/B2` | `squarefreeStep_eq_sourceSum` | `MathExtras.CohenDressElMarraki.squarefreeCount` used by `ReproducibleSquarefreeVerifierOutput` |
| `RealSourceClaims.little211/littleStronger` | `littleMertensStep_eq_sourceSum` | `MathExtras.Helfgott.MinorArcsStart.mobiusOverNSum` used by both Platt residuals |

All differences after these rewrites are transparent abbreviations or exact
rational identities (`0.571 = 571/1000`, `755/10000 = 151/2000`, and
`285/10000 = 57/2000`).

The one-pass campaign, immutable-plan ingestion, certificate replay,
independent bounded oracle, 10,000-leaf control-plane test, and operational
Azure DAG now exist.  The remaining blocker is deliberate: a reviewed
physical-row realization and its own registered algorithm/attested run have
not been supplied.  Until that boundary is closed and a full run is actually
performed, the reviewed V2 two-pass route remains the only registered Hurst
path and the repository makes no source-completion or attestation claim for
the affine route.
