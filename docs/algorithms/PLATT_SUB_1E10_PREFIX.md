# Closing the zeta interval below `10^10`

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

[`PLATT_PT21_WINDOWED_SOURCE_CAMPAIGN.md`](PLATT_PT21_WINDOWED_SOURCE_CAMPAIGN.md)
states that the interval below `10^10` "needs its own accepted artifact" and
leaves it there.  This note settles what that artifact should be, on measured
rather than assumed grounds.

## The pinned PT21 runner cannot do it, and fails open when asked

`zeta_arb/parameters.h` in the pinned upstream commit fixes

```text
#define T0_MIN ((double) 1.0000000000000000000000000000000000000e10)
#define T0_MAX ((double) 3.0100000000000000000000000000000000000e12)
```

and `arb_zeta.c` rejects anything outside that band.  Measured on the corrected
binary:

```text
$ arb-zeta 128 9999998992 1 1008
t0 outside limits.. Exiting.
$ echo $?
0
```

The exit status is **zero**.  This is precisely the fail-open behaviour the
campaign's transcript contract exists to catch: `outside limits` is one of the
rejected tokens, so both the shard engine and the work-unit scheduler fail the
range closed rather than recording an empty success.  No amount of scheduling
gets the pinned binary below `10^10`.

## What the boundary count already is

Two independent artifacts state the same boundary value.

The LMFDB prefix importer decodes block `693` of `zeros_9998546000.dat` and
counts the encoded multiplicity slots whose entire stated `2^-102` interval
lies below the cut:

```text
32130155617 + 2698 = 32130158315.
```

The pinned PT21 runner derives `N` at its own lower endpoint from that block's
left Turing flank, and on the first logical block prints

```text
looking for 32130161714-32130158315=3399 zeros.
```

So `N(10^10) = 32130158315` is asserted by a binary-format decode of the public
database and, separately, by a fresh Arb/Turing computation that never reads
that database.  Their agreement is a real check on both, and it is the value
the work-unit scheduler requires of the first shard.

It is not a proof of the prefix.  It pins the *boundary*, not the claim that
every zero below `10^10` is on the line.

## Three routes, and which one to take

### A. Accept the public Platt/LMFDB prefix as a reviewed premise

Already implemented: `tg_verifier/lmfdb_zeta_prefix.py` checks the ordered file
list, the 14,580-row checksum manifest, every block header, every 13-byte
`uint104` delta, cross-file continuity, and the exact non-ambiguous cut.  It
deliberately reports

```text
source_turing_completeness_independently_replayed = false
source_claim_ready = false
```

Cost: about eleven hours of transfer for `418` GB and a few hours of decoding.
What it buys is candidate data plus a boundary cross-check.  What it costs is
an explicit trusted-source premise in the Lean statement, which is exactly the
thing an independently computed proof is supposed to avoid.

### B. Recompute it with Platt's own low-range parameter set

The **same pinned upstream commit** contains the low-range parameter set for
the 2017 computation, in `arb_windowed_isolate/parameters.h`:

```text
T0_MIN = 5000        T0_MAX = 3.062e10
N = 2^20             UPSAM = 32          N1 = 2^15
one_over_A = 21/4096 h = 176431/2048     B = 5376
M = 104000           K = 44              TURING_WIDTH = 42
Ns = 70              H = 2089/16384      INTER_SPACING = 5
intererr_d = 5.0e-41
```

`H = 2089/16384` with every fifth lattice point is exactly the choice
[`PLATT_LEMMA_C3_SOURCE_MAP.md`](PLATT_LEMMA_C3_SOURCE_MAP.md) already
identifies as "the original 2017 run".  The interpolation width `B = 5376` and
the intermediate FFT length `N1 = 2^15` are the same as the PT21 set, so a step
of `1008` is `196608` samples and is accepted, and the block grid, transcript
format, Turing-count chain, and therefore the entire scheduler and receipt
stack apply unchanged.

A **timing-only diagnostic build** of that parameter set was measured on the
local DGX Spark ARM host, 2026-07-30, single core:

| height | user CPU s per `1008`-block | isolated zeros | Turing endpoints |
|---:|---:|---:|---|
| `10^4` | `8.72` | `1192` | `10142 -> 11334` |
| `10^6` | `8.64` | `1922` | `1747146 -> 1749068` |
| `10^9` | `8.61` | `3030` | `2846548032 -> 2846551062` |
| `10^10` | `8.78` | `3399` | `32130158315 -> 32130161714` |

Two things fall out of that table.

The `10^10` row **reproduces the PT21 known answer exactly** -- `3399` zeros
and both Turing endpoints -- from a different FFT length, a different Taylor
order, a different Gaussian width, and a different interpolation stencil.  That
is a strong independent check on the retained known-answer geometry.  The
`10^4` row states `N(10^4) = 10142`, the classical value.

And the cost is small.  At a flat `8.65` s per block,

```text
(10^10 - 5040) / 1008 = 9,920,629 blocks
9,920,629 * 8.65 s     = 8.581e7 s
                       = 23,837 core-hours
                       = 2.72 core-years
```

against `4,424,804` core-hours for the high range.  **The prefix is `0.54%` of
the campaign**, a few hundred dollars of Spot capacity inside the
`$60k`--`$100k` band in
[`PLATT_PT21_WORK_UNIT_SCHEDULER.md`](PLATT_PT21_WORK_UNIT_SCHEDULER.md).  It
is not worth accepting a trusted-source premise to avoid.

Two obligations stand between that diagnostic and a production runner, and
neither is optional:

1. **The same Appendix C omission is present, and worse.**
   `arb_windowed_isolate/arb_zeta.cpp` calls `set_err(intererr, intererr_d)`
   but never adds `intererr` to the interpolated value, and its
   `arb_init(intererr)` is commented out at line 193.  A production build needs
   its own hash-pinned correction, on the model of
   `patches/platt-pt21/0001-apply-interpolation-error.patch`, plus the exact
   rational comparison against `intererr_d = 5.0e-41` that
   `PlattLemmaC3.lean` performs for the PT21 radius.
2. **The parameter block must be selected.**  In the pinned tree the low-range
   blocks sit inside a comment and the active block is a different one
   (`T0_MIN = 1e10`, `M = 560000`).  Selecting them is a source modification
   and needs the same pinned-digest treatment as the interpolation patch: a
   `PLATT_LOW_RANGE_WINDOWED_UPSTREAM.json` reviewed-source set, a pinned
   pre/post digest for the edited `parameters.h`, and retained known answers
   (the four rows above are the obvious candidates).

The diagnostic binary used for the table above does **not** apply the
interpolation error and is therefore a cost measurement, not a certificate.

### C. `[0, 5000]` by direct zero isolation

`T0_MIN = 5000` leaves a stub.  `N(5000)` is about `4500` multiplicity slots,
which is the regime FLINT's local zero isolator handles directly and which
`tg_verifier/platt_zeta_campaign.py` already targets.  This is minutes of work,
not a campaign.

## Recommendation

Run **B** for `[5000, 10^10]` and **C** for `[0, 5000]`, and keep **A** as an
independent cross-check of the boundary count rather than as a premise.  The
decision is not close: route B costs half a percent of the campaign it is
attached to, and it removes the only step that would otherwise require trusting
an artifact this project did not compute.

The campaign artifact carries the choice explicitly.  `finalize
--prefix-receipt` records the bound receipt's digest, kind, and whether its
`source_turing_completeness_independently_replayed` flag is set, and refuses a
receipt whose boundary count is not `32130158315`.  With no receipt bound, the
artifact records `prefix.bound = false`.  In every case `source_claim_ready`
stays false: the prefix is one of several open obligations, and closing it does
not close the Hardy-Z realization.
