# Resident completed-L sign reducer

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

## Result and boundary

`gpu/include/sparkinterval/tg_dirichlet_completed_sign_reducer.cuh`
implements the source-shaped arithmetic seam that was missing after the
scheduled multi-q Dirichlet FFT.  `launchResidentPhaseReduction` takes the
`ComplexInterval*` in `TransformPlan::DeviceTransformResult` while it is still
resident on the GPU.  It reads allchars' t-major layout directly through the
canonical primitive-ordinal-to-frequency map.  It does not call
`execute(vector*)`, `writeAll`, or a FIFO adapter.

The output per character and at most 64 adjacent 5/64 samples is:

- one 88-byte dense `PhaseState`;
- one ambiguity-range count;
- after a device prefix scan, only exact maximal ambiguity ranges.

The production sparse writer adds the canonical primitive ordinal in a
parallel 8-byte tag array.  A device scan/reduction copies one total and then
only 24 bytes per sparse `(ordinal, first, stop)` row; per-character range
counts never cross the host boundary.

After all adjacent frames for one q have been merged,
`launchDenseTGDCSB03Pack` validates every final state and emits the exact
compact-v3 dense record on device: four determinate/first-positive/
last-positive/sparse flag bits plus
`max(1, bit_length(sample_count - 1))` transition bits.  Pages contain at
most 4,096 canonical primitive ordinals.  Temporary CUDA storage has a fixed
page stride, but each `DensePageTotals` gives the exact canonical used prefix;
unused bytes and high padding bits are zero.  The 88-byte states never need
to cross the device boundary.

The dense state retains the exact sample span, first/last determinate
ordinate and sign, transition count, ambiguity sample/range counts, and
leading/trailing ambiguity counts.  Ordered adjacent merges insert a
transition when determinate boundary signs differ and coalesce one ambiguity
range precisely when the left trailing and right leading ambiguity runs
touch.  The latter arithmetic matches
`SparkInterval.Dirichlet.PhaseSignState.AmbiguityRunState`; its nonnegative
validity and associativity theorems are source-built and use only Lean's base
trust trio.  The CUDA KAT checks two-way merge against an uninterrupted scan
and checks both transition and ambiguity-range state under three-way
parenthesization.

This is an arithmetic component, not an accepted Platt/GRH certificate.
Multiplicity-preserving zero isolation, touching-versus-wide resolution,
same-roster Turing upper counts, source execution, compiler refinement,
attestation, and the Lean theorem bridge remain false.

## Enclosure semantics

For canonical primitive character `chi`, parity `a`, modulus `q`, and
ordinate `t`, the current fully composed FFT output encloses
`L(1/2+it,chi)`.  The reducer consumes:

1. that resident directed rectangle;
2. the same primitive ordinal's `TGDRNRO1` Hardy multiplier;
3. a certified factor enclosing

   `(q/pi)^(it/2) Gamma((1/2+a+it)/2) exp(pi*t/4)`.

Each rectangle is converted to a containing Euclidean disk with an outward
radius.  The two complex products use the directed disk calculus already
used by the certified Booker kernels, including the same explicit-FMA center
expressions.  A bit-exact adversarial KAT distinguishes the Booker
`0xc01581f64d4dddd9` center from the
separate-multiply/subtract result `0xc01581f64d4dddda`.  A positive sign is
emitted only when
the completed disk's real center is strictly above its outward-nextafter
radius; negative is symmetric; every other finite case is ambiguous.  A disk
whose imaginary projection does not contain zero is an error, not an
ambiguity.  Nonfinite/malformed inputs, invalid parity/frequency ids,
coordinate overflow, nonzero upstream status, and sparse-layout mismatch all
fail closed.

`launchRectangleCatalogToDisksIntoSummary` is the validated catalog seam for
TGDRNRO1 root rectangles (and bounded factor rectangles).  It preserves the
owning pipeline summary, restricts the error bit to the root/factor stages,
and writes a deterministic zero disk for every rejected row.  Its KAT checks
an exact point, a nontrivial enclosing rectangle, malformed-row rejection,
and error-domain substitution.

Allchars has no per-frequency status array.  The production view therefore
passes a null per-item status pointer after the existing frame/CUDA
validation, plus one frame status word.  Per-item status memory exists only
in attack KATs.  This avoids an additional four bytes of storage and traffic
for every transformed value.

## Source-feasible factor provenance

The reducer does **not** assume an Arb-generated `(q,t)` factor table.
`buildParityFactorsFromCheckpoints` consumes three explicit, immutable wire
formats:

- `TGDCGAM1`: the 127,988 source t rows of parity-only
  `Gamma((1/2+a+it)/2) exp(pi*t/4)` disks, shared across q;
- `TGDCCPB1`: direct per-q conductor-phase checkpoints for one resident
  phase, every 4,096 samples; and
- `TGDCSTP1`: one per-q step disk
  `exp(i*(5/128)*log(q/pi))`.

CUDA derives the current frame's two parity rows using only directed disk
multiplication.  A persistent implementation can retain one phase state and
step per q and periodically reload independently replayed Arb checkpoints.
At the 4,096-row span, including all headers and record framing, the exact
ten-phase source projection is:

- 6,143,552 bytes for the shared gamma artifact;
- 7,020,144 bytes for the execution-order step catalog;
- 88,670,664 bytes for 2,351,903 phase-local checkpoint disks and 2,013,932
  q records; and
- 101,834,360 bytes total.

The naive parity/q/t factor table would occupy 174,605,432,016 bytes, so the
source-shaped inputs are over 1,700 times smaller.  These are exact layout
formulas, not a source measurement.

The pinned-Arb producer in
`tg_verifier/dirichlet_completed_factor_artifacts.py` can generate all three
formats.  Its bounded KAT binds python-flint 0.9.0 / FLINT 3.6.0, 384-bit
precision, the factor convention, and the exact producing source identities.
The parsers reject malformed/nonfinite disks, duplicate checkpoint q records,
length changes, convention changes, and SHA-256 changes.  `TGDCCPB1`
cryptographically binds the supplied gamma and step files, schedule, and
phase schedule.

A proposed common `q^-s` deferral is not valid for the present composer:

`input = q^-s zeta_M + R_M`,

where `R_M = sum_n (qn+a)^-s` is separately unscaled.  Moving one common
factor through the FFT would therefore change the computation.  No deferred
factor convention is admitted.

## Bounded differential qualification

`tools/qualify_tg_dirichlet_completed_sign_gpu_reducer.py` constructs direct
python-flint enclosures for real moduli/ordinates, serializes every component
outward to binary64, invokes a qualification-only CUDA raw-code projection,
and compares each decision to:

- direct Arb completed-L sign; and
- multiplication of the serialized component rectangles.

Raw codes are never part of the production API.  The oracle uses the actual
CUDA checkpoint recurrence for the conductor phase.  On this DGX Spark,
q=5, 7, and 8 over t indices `[0,512)` compared 5,120
primitive-character/sample decisions at 256-bit precision:

- false determinate decisions: 0;
- opposite determinate decisions: 0;
- extra ambiguities versus direct Arb: 0/5,120;
- extra ambiguities attributable to rectangle-to-disk widening: 0/5,120.

This is evidence that disk conversion did not materially widen that bounded
sample.  Two additional q=5 runs exercised a full 4,096-step no-reseed
recurrence both at `[0,4096)` and the terminal source window
`[123892,127988)`.  Each compared 12,288 decisions with zero false
determinate, opposite, direct-Arb extra-ambiguous, or disk-over-rectangle
extra-ambiguous decisions.  This is not a source-q-range usefulness proof.

The source-built CUDA KAT also enumerates all `3^8 = 6,561` length-eight
negative/ambiguous/positive sequences.  For every sequence it compares the
uninterrupted state with all seven two-way splits and both parenthesizations
of all 21 three-way splits.  Hostile ambiguity-with-zero-range and misbound
determinate-coordinate states fail closed.  Short and extra checkpoint
rosters are rejected by the production launch wrapper.  The same 6,561
states span two compact pages: an independent host encoder compares all 7,168
temporary bytes (including zero padding) byte for byte, checks the 5,741
canonical bytes and every page total, decodes every record, and attacks the
capacity, coordinate, and malformed-state checks.

### Corrected conductor-step audit

On 2026-07-25, review caught an in-progress recurrence that applied the
documented conductor step twice between adjacent samples.  Those earlier
uncommitted qualification numbers are withdrawn.  The required ratio is

`exp(i * (5/128) * log(q/pi))`

once per `5/64` t step.  The corrected runner reports that numerator,
denominator, and application count explicitly.  A hostile exact quarter-turn
KAT requires the sequence `1, i, -1, -i`; the old double-step produces
`1, -1, 1, -1` and fails byte-exact comparison.

The architecture-independent rational identity and the inequality excluding
the doubled step are proved in
[`CompletedConductorPhase.lean`](../../SparkInterval/Dirichlet/CompletedConductorPhase.lean).
Canonical checkpoint count, unique sample ownership, full coverage, and
restart-versus-unbroken exponent equality are proved separately in
[`TMajorCheckpointLayout.lean`](../../SparkInterval/Dirichlet/TMajorCheckpointLayout.lean).
These modules specify this completed-function `5/128` recurrence.  They are
deliberately distinct from the older experimental
[`TMajorFactorRecurrence.lean`](../../SparkInterval/Dirichlet/TMajorFactorRecurrence.lean),
which advances a full `q^-s` factor and is not the reducer's conductor-phase
model.

Fresh corrected single-step/explicit-FMA Arb runs reproduced all three
bounded campaigns:

- q=5, 7, 8 over `[0,512)`: 5,120 decisions;
- q=5 over `[0,4096)` with no intermediate reseed: 12,288 decisions;
- q=5 over the terminal source window `[123892,127988)`: 12,288 decisions.

Across the 29,696 decisions, false-determinate, opposite-determinate,
direct-Arb extra-ambiguity, and disk-over-rectangle extra-ambiguity counts
were all zero.  The terminal replay took 127.07 seconds locally.  These
replace the withdrawn in-progress numbers but remain bounded qualification,
not source-q-range evidence.

## Bounded performance and memory

The source-built GB10 benchmark with 65,536 characters, 64 samples, and ten
repetitions processed 1.067e9 completed-L decisions/second.  This is a local
kernel benchmark, not an H100 or source projection.

The first checkpoint-factor kernel assigned one serial CUDA thread to each
4,096-row span.  A 127,988-row microbenchmark exposed that under-occupancy:
it generated only `1.018e7` disks/second.  The current kernel assigns one
block per checkpoint, computes directed per-thread chunk powers and a
block-local prefix, then advances each short chunk in sample order.  The same
255,976-disk, 32-checkpoint workload over 1,000 repetitions measured
`8.995e8` disks/second, or `0.285 ms` per complete 127,988-row parity table,
an `88.4x` local speedup.  The exact quarter-turn KAT, the 12,288-decision
q=5 `[0,4096)` Arb differential, the real-Arb artifact/direct-factor compact
state comparison, and all four Compute Sanitizer modes passed after this
change.  This remains a GB10 arithmetic microbenchmark, not an H100 source
runtime estimate.

The final dense pack was changed from a serial page validator and byte-owned
bit loop to a block-parallel page validation/reduction plus word-owned
overlap packer.  For 400,000 valid states at the maximum source sample count
(17 transition bits), three 1,000-repetition GB10 runs measured
1.501e9--1.632e9 characters/second (median 1.541e9), or about 0.260 ms per
maximum-size q pack.  This measures synthetic packing only, not completed-L
arithmetic, ambiguity refinement, source I/O, or H100 throughput.

For a deliberately conservative 400,000-character, 64-sample frame:

- already-resident FFT rectangles: 819,200,000 bytes;
- incremental reducer memory with no ambiguities: 54,803,096 bytes;
- exact sparse worst-case sensitivity: 16 bytes per maximal ambiguity range
  plus its 8-byte primitive tag (at most 307,200,000 bytes for alternating
  ambiguity in this frame);
- per-value status bytes: 0.

Those exact named-buffer figures exclude CUB's implementation-dependent scan
workspace and the owning q-level double-buffered merge accumulator; the
production pipeline must size and report those separately.

Materializing all 266,697,737,764,848 source transformed rectangles would be
8,534,327,608,475,136 bytes.  Even materializing two-bit decisions would be
66,674,434,441,212 bytes.  The production design avoids both: frame states
are merged on device/per q and only the final dense TGDCSB03-compatible state
and sparse ambiguity exceptions cross the boundary.

Across the exact formulaic source roster, retaining an 88-byte state per
primitive character would be 2,600,175,312,152 bytes.  TGDCSB03's reviewed
mixed-width dense floor is 62,259,950,420 bytes (41.76 times smaller); its
canonical wire size including q/page framing but excluding unmeasured
ambiguity ranges is 62,968,524,843 bytes.  These are storage formulas, not
measurements of a source computation.

The bounded same-process allchars KAT now calls the recurrence builder and
resident reducer directly on the transformed CUDA pointer, performs the CUB
scan, adjacent state merge, ambiguity coalescing, and exact TGDCSB03 dense
pack, and copies no TGDAFFO1 payload, phase state, or per-frame range-count
array to the host.  Its artifact loader does not trust a repairable hash chain:
it independently reconstructs the fixture's producer, execution-order,
schedule, phase-index, and phase-schedule identities.  Mutation KATs repair
all dependent hashes after substituting each semantic identity and still
require rejection.

Before source admission, this bounded seam must be generalized into the
persistent source phase service, factor checkpoint widening must be qualified
through the full source q/range, root/factor/roster digests must be
receipt-bound, the complete source run must be attested, and the independent
analytic/Turing obligations must be realized.

CUDA `compute-sanitizer` memcheck and racecheck were clean in independent
review.  An initial initcheck found rejected-path sparse buffers that were
never published semantically but were copied by the KAT.  The launch wrappers
now initialize the exact sparse buffers deterministically; initcheck reports
zero errors.
