# The PT21 verification ladder

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

## The problem

The Platt--Trudgian zeta range to height `3000175332800` contains about
`1.24e13` zeros, isolated in `2966443783` blocks of `1008` height units.
A certificate that names every sign bracket is linear in that number.
The measured Lean kernel rate for rational sign brackets is **22
brackets/s** (122 brackets in 5.6 s, `docs/algorithms/GRH_POC_BENCHMARKS.md`).
A bracket-linear certificate is therefore

```text
1.233e13 brackets / 22 per second = 5.6e11 s = 1.78e4 core-years
```

of *checking*, against roughly `506--856` core-years of *computing*.  A
verification that costs thirty to fifty times the computation is not a
verification strategy.

## The structural fact that fixes it

Turing's method does not check brackets individually.  For one block
`[a, b]` it needs exactly two things:

1. the zero counts `N(a)` and `N(b)` from the one-sided
   argument-principle quotients; and
2. that `N(b) - N(a)` sign changes were exhibited strictly inside
   `(a, b)`.

If those match, every zero in `(a, b]` is on the critical line -- and the
conclusion does not mention where any zero is.  Finite RH on a rectangle
is a statement about a *count*.

So a per-block certificate can be four naturals plus a commitment, and the
bracket ordinates can be discarded.  That is the ladder.

## The four levels

Full wire layouts are in `cpu_checker/pt21_ladder/FORMAT.md`.  The Lean
side is `SparkInterval/Zeta/PT21Ladder.lean` (arithmetic) and
`SparkInterval/Zeta/PT21LadderSemantics.lean` (what it means for
`riemannZeta`).

| Level | Unit | Count | Wire | Proposition it supports |
|---|---|---:|---:|---|
| L0 | block sign packet | 2,966,443,783 | 3,339 B each = **9.9 TB** | this block's slot count, endpoint counts, and Turing cells follow from the published signs |
| L1 | window summary | 2,966,443,783 | never serialized | `WindowSummary`: `block, lowerCount, slots, upperCount` with `lowerCount + slots = upperCount` |
| L2 | group summary | 90,530 (32,768 blocks/group) | 88 B each = **7.97 MB** | `GroupSummary`: a valid, gap-free, telescoping run of 32,768 windows exists under this digest |
| L3 | campaign record | 1 | 88 B | the whole range `[10^10, 3000175333264]` is covered gap-free and `N(end) = N(start) + totalSlots` |

The L2 list is the largest object the Lean kernel ever reads: 90,530
records, under 8 MB.

### What each level still proves

`SparkInterval.Zeta.PT21Ladder.campaign_windowChain` is the aggregation
theorem.  From

* a kernel-checked `checkCampaign record groups = true`, and
* one `GroupRefines commit group` fact per level-2 record,

it produces a `WindowChainValid` over **every** block of the campaign.
The window list exists only as a `Prop`-level witness: the kernel never
materializes, hashes, or reduces `2.97e9` records.

`SparkInterval.Zeta.PT21Ladder.criticalLine_of_blocks` then says that
gap-free consecutive blocks compose: if every block's own certificate puts
its zeros on the critical line, so does the union.  That direction uses no
count at all -- only that the half-open blocks tile.
`sourceClaim_of_ladder` composes it with an LMFDB-derived prefix claim
below `10^10` to give the exact Platt--Trudgian source proposition.

`SparkInterval.Zeta.PT21Ladder.count_telescopes` is the counting
direction: any count function agreeing with the windows' advertised
endpoint counts satisfies `N(end) = N(start) + totalSlots`.

All of these are `[propext, Classical.choice, Quot.sound]`.  No `sorry`,
no `native_decide`, no new axiom.

### What compression destroys

Stated bluntly, because a compressed certificate that no longer pins down
the zeros would be worthless if the claim needed the zeros:

* **Zero ordinates are gone.**  After L1 nothing can locate a zero.  The
  ladder cannot support any statement of the form "there is a zero near
  `t`".  It supports only "every zero in this range is on the critical
  line".
* **Sign bits and enclosures are gone above L0.**  An L1 summary does not
  witness that a sign change occurred; it asserts one.  The witness is the
  L0 packet, and the packet's commitment is the only thing that survives.
* **The Turing rounding arithmetic is gone above L0.**  `lowerCount` and
  `upperCount` are advertised counts at L1; the exact-integer ceiling and
  floor cells that justify them are checked at L0 and nowhere else.

The compression is therefore *lossless for finite RH and lossy for
everything else*.  That is the whole trick, and it is only sound because
the target proposition is a counting statement.

### The single trust-transfer point

`GroupRefines` is the one place where trust is transferred rather than
eliminated:

```lean
def GroupRefines (commit : List WindowSummary → Digest)
    (group : GroupSummary) : Prop :=
  ∃ windows : List WindowSummary,
    windows.length = group.blockCount ∧
    WindowChainValid group.firstBlock group.lowerCount windows ∧
    slotSum windows = group.slots ∧
    commit windows = group.digest
```

Nothing in the ladder proves it.  The compiled checker does, under
attestation.  The statement is universally quantified over groups and
takes the digest scheme as a parameter, so no consumer can weaken it
silently.

**The ladder does not reduce the amount of work that must be done.  It
reduces the amount of work the Lean kernel must do, from `1.78e4`
core-years to about two minutes, and moves the remainder onto a checker
whose compiler is verified.**

## Measured throughput

Local machine: DGX Spark, 20-core NVIDIA Grace (aarch64), Lean 4.32.0,
gcc 13, CompCert 3.17.  All numbers single-threaded.

### Level 0, the compiled checker

`cpu_checker/pt21_ladder/pt21_ladder_check.c`, 300,000 synthetic blocks at
the campaign's average occupancy (4,157 slots/block).

| Build | Mode | blocks/s | MB/s | slots (brackets)/s | Whole campaign, 1 core |
|---|---|---:|---:|---:|---:|
| gcc `-O2` | full, packets committed | 51,433 | 171.7 | **2.14e8** | **16.0 h** |
| **CompCert `-O`** | full, packets committed | **31,975** | 106.8 | **1.33e8** | **25.8 h** |
| gcc `-O2` | verification only, no packet SHA-256 | 372,490 | 1,243.7 | 1.55e9 | 2.21 h |
| CompCert `-O` | verification only, no packet SHA-256 | 230,248 | 768.8 | 9.57e8 | 3.58 h |

CompCert costs a factor of `1.61` against gcc.  That is the price of the
verified-compiler story and it is obviously worth paying here.

The comparison that matters:

```text
Lean kernel, bracket-linear certificate :        22 brackets/s
CompCert-compiled ladder checker        : 1.33e8 brackets/s
speedup                                 :   6.0e6 x
campaign check                          : 1.78e4 core-years  ->  25.8 core-hours
```

Roughly seven eighths of the remaining cost is SHA-256 over the 9.9 TB of
level-0 packets, not the verification logic.  Committing to the packets is
what lets a third party re-derive the summaries from retained bytes, so it
is worth its 8 core-hours; but the honest breakdown is that the *checking*
is 3.6 core-hours and the *commitment* is 22.

Against the compute cost of 506--856 core-years, a 25.8 core-hour check is
`0.0006%` of the campaign.  Verification is no longer the bottleneck; it
is a rounding error.

### Level 2/3, the Lean kernel

`tools/benchmark_pt21_ladder.py` emits a literal `List GroupSummary` and
asks the kernel to reduce `checkCampaign record groups` to `true` by
`rfl`.  Marginal cost is about **1.4 ms per group record** end to end
(elaboration plus kernel), so the production 90,530-record ladder is
roughly **two minutes**, once, in an ordinary `lake build`.

One performance fact is load-bearing and is recorded in the source: the
level-2 checker must be written in *closed* form.  A checker that computes
a state with `runGroups` and then compares the state against the campaign
record forces the kernel to re-reduce the entire run once per comparison
-- 54 s at 100 records instead of 0.9 s.  `runGroupsTo` carries the
targets through the recursion so the list is reduced exactly once.

## Attestation

### Why aggregation is required

`2966443783` blocks cannot each carry a quote, and neither can `90530`
groups if each needed its own CVM.  But a quote is not expensive; a *CVM
deployment* is (~$0.03 on Phala, per
`project_phala_tdx_working_recipe`).  `GetQuote` over
`/var/run/dstack.sock` is a local call.  So the design shards by *worker*,
not by block.

### Shards and receipts

A **shard** is a contiguous run of groups assigned to one attested worker
CVM.  At one core-day of compute per shard, `506` core-years is about
`1.85e5` shards; at one core-month, about `6100`.  Either is a tractable
number of receipts.

Each worker emits two quotes:

* an **opening quote** whose `report_data` is
  `SHA-256(campaignId ‖ firstBlock ‖ blockCount ‖ lowerCount ‖
  checkerDigest ‖ evaluatorDigest)`; and
* a **closing quote** whose `report_data` is
  `SHA-256(openingReportData ‖ upperCount ‖ shardRoot)`,

where `shardRoot` is the root of the shard's level-2 records computed by
`pt21_ladder_finish`.  The TDX quote itself carries `MRTD` and the RTMR
event log, which measure the image; the `report_data` binds the run's
inputs and outputs to that image.

`campaignId` is a fresh nonce per campaign, so a receipt cannot be
replayed from an earlier run.

### The receipt chain is just another ladder level

Shard receipts chain exactly like groups: shard `i`'s `upperCount` must
equal shard `i+1`'s `lowerCount`, and its block range must abut.  This is
`runGroupsTo` again, at a different granularity, and it is small enough
(`6e3`--`2e5` records) for both the compiled checker and the Lean kernel.

So the ladder has five levels in production, not four; the fifth is the
receipt level, and the arithmetic that binds it is the same theorem.

### Folding the quotes

Verifying `1.85e5` ECDSA P-384 quotes takes about 90 s on one core, which
is cheap enough that a skeptic should simply do it.  A **fold CVM** is
offered as a convenience, not as a replacement: it verifies every worker
quote inside TDX and emits one closing quote binding the campaign root.
Anyone who trusts the fold image checks one quote; anyone who does not
checks `1.85e5`.  Both must produce the same campaign root, so the
convenience path cannot hide a disagreement.

### Phala operational constraints

From `project_phala_tdx_working_recipe`, verified on hardware:

* deploy with
  `npx phala@1.1.20 deploy -n NAME -c docker-compose.yaml -e deploy.env
  --instance-type tdx.medium --disk-size 40G --public-logs --wait`;
* **do not** pass `--node-id`; the CLI forwards it as `teepod_id` and it
  fails with "No available resources";
* escape `$` as `$$` in any script embedded in the compose file;
* a tmpfs-backed *named* volume is **not** shared between containers; use
  an ordinary named volume for cross-container data;
* a container that exits loses its logs; whatever must be read has to be
  printed by a container that then stays alive;
* **log retrieval caps at ~64 KiB.**  This directly constrains the design:
  the level-2 records must go to a mounted volume or object store, and
  only the shard root, the two counts, and the quote may come back through
  the log;
* `GetKey` is deterministic across containers in one CVM and works under
  `network_mode: none`; `GetTlsKey` is not deterministic and must never be
  used;
* the dstack event log must come from `/Info`'s `tcb_info`, not from the
  `GetQuote` response;
* destroy, never stop -- retained disk keeps billing.

### What attestation does and does not establish

It establishes that *some* TDX platform reporting the measured image
produced the bound `report_data`.  It does not establish that the image
computes what its source says, that the host did not starve or restart the
guest, or that the evaluator's arithmetic is correct.  The repository's
existing position (`docs/algorithms/COMPACT_ARCHITECTURE_RECEIPT_BOUNDARY.md`)
is the right one: platform attestation alone is not proof of arbitrary
user-space causality; the measured runner and the appraisal policy must
establish the binding.

Attestation enters Lean through the one existing axiom,
`accepted_run_certificate_sound`, parameterized by the campaign root.  The
ladder adds **no new axiom**.

## Trust ledger

Every stage of the pipeline, including the parts that are ugly.

| # | Stage | Proved | Assumed | Checked by |
|---|---|---|---|---|
| 1 | Zeta discreteness, compactness of the critical rectangle | yes | Lean kernel and Mathlib are correct | Lean kernel |
| 2 | L2/L3 ladder arithmetic: gap-free coverage, telescoping, local closure | yes, `[propext, Quot.sound]` | -- | Lean kernel, ~2 min at production size |
| 3 | Ladder semantics: blocks compose to the source claim | yes, `[propext, Classical.choice, Quot.sound]` | -- | Lean kernel |
| 4 | `GroupRefines`: each group digest commits to a valid window run | **no** | that the attested checker really consumed those packets and produced those summaries | compiled checker + TDX receipt; imported through `accepted_run_certificate_sound` |
| 5 | L0 packet checks: slot derivation from the bitmap, block ordering, flank weight derivation, Turing ceiling/floor cells | yes, as C code | that the C source says what we think | CompCert-compiled binary, 25.8 core-hours measured; 12 mutation KATs |
| 6 | C to assembly semantics | yes, by CompCert's Coq proof | CompCert's assumptions; the assembler, linker, OS, and hardware are outside it | Coq kernel, upstream |
| 7 | **A sign bit is the true sign of Hardy `Z` at that lattice ordinate** | **no** | the evaluator's directed enclosure was computed correctly, `7.3e13` times | **nothing outside the enclave**; this is the entire empirical content |
| 8 | The `S(t)` and Gamma/log-pi dyadic intervals contain the real quantities | **no** | Arb's ball arithmetic and Platt's Lemma C.3 constants | not formalized; `SparkInterval/Zeta/PlattLemmaC3.lean` records the source map |
| 9 | The analytic Turing inequality relating the two quotients to `N(t)` | **no** | Turing's method as stated in Platt--Trudgian | not formalized; `AnalyticTuringBounds` is an explicit `Prop` premise |
| 10 | Hardy `Z` really is a nonvanishing multiple of `zeta(1/2+it)` on the range | **no** | `HardyZModel` is instantiable for the production evaluator | not formalized; owned by the Hardy Z / Turing workstream |
| 11 | The count at height `10^10` is `32130158315` | arithmetic yes | the public LMFDB zero file is correct and complete below `10^10` | `SparkInterval/Zeta/LMFDBPrefixBoundary.lean`, kernel-checked; the file itself is trusted |
| 12 | The TDX quote chain | **no** | Intel TDX, the Phala dstack guest agent, the quote verifier, and the appraisal policy | conventional verifier outside Lean |
| 13 | Digest binding | **no** | SHA-256 collision and second-preimage resistance | nothing; stated, as in the compact-receipt boundary doc |

Rows 7, 8, 9, and 10 are the real remaining content.  Rows 1--3 and 5--6
are the parts this work closed or made cheap.  Row 4 is the seam, and it
is one line of Lean.

### The honest summary

Before: the formal side could not check the campaign at any price.

After: the formal side checks the campaign in about two minutes of Lean
kernel time plus 25.8 core-hours of verified-compiler-compiled checking,
against 506--856 core-years of computing.

What did not change: nobody outside the enclave re-derives `7.3e13` Hardy
`Z` signs.  No compression can change that, and no attestation makes it a
proof.  What the ladder *does* give a skeptic is a cheap way to compare
two independent campaigns: two runs agree on all `1.24e13` zeros iff their
32-byte campaign roots agree.

## Reproduction

```bash
cd cpu_checker/pt21_ladder
make && make test                       # 12 mutation KATs
make ccomp
./pt21_ladder_bench       --blocks 300000
./pt21_ladder_bench_ccomp --blocks 300000
./pt21_ladder_bench_ccomp --blocks 300000 --no-packet-commit

cd ../..
lake build SparkInterval.Zeta.PT21Ladder SparkInterval.Zeta.PT21LadderSemantics
python3 tools/benchmark_pt21_ladder.py --sizes 1000 5000 20000
```
