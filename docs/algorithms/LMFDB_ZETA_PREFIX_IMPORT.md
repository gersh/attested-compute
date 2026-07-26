# LMFDB zeta prefix through `10^10`

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

The accelerated Platt--Trudgian campaign starts at height `10^10`.  This
module supplies a fail-closed path for importing the public Platt/LMFDB data
below that boundary and, separately, records what the import does **not**
prove.

LMFDB states that its zeta dataset was computed by David Platt, that each
ordinate has absolute error at most `2^-102`, and that completeness was
verified by a rigorous Turing method.  Its current dataset page says that it
contains the first `103,800,788,359` positive zeros on the critical line.  The
public bulk directory contains the binary files, a 14,580-row MD5 manifest,
an ordered file list, a format README, and the LMFDB reader implementation.

The reviewed identities and exact format are pinned in
[`LMFDB_ZETA_PREFIX_UPSTREAM.json`](../../specifications/LMFDB_ZETA_PREFIX_UPSTREAM.json).
The package does not redistribute the data or assert a license that the
source does not provide.

## Exact boundary result

The first `4,766` ordered files reach the unique file containing `10^10`:

```text
zeros_9998546000.dat
MD5    a1a886b1d1b1532e25afbc234ccee93d
SHA256 f6d3fbaad771da06fe8e6420fc74eb086d204a138863c4a2c2938d33ec9e497c
size   92092112 bytes
```

Its block 693 has the exact header

```text
[9999999200, 10000001300]
N(first) = 32130155617
N(last)  = 32130162699
```

There are exactly 2,698 encoded multiplicity slots whose entire stated
`2^-102` interval lies below `10^10`.  Therefore the artifact's boundary
count is

```text
32130155617 + 2698 = 32130158315.
```

The last midpoint below the cut is about `0.129547` below it; the first above
is about `0.0606343` above it.  Classification is nevertheless performed by
integer inequalities at scale `2^102`, not by those decimal approximations or
host floating-point comparisons.

The result matches the first count required by the high-range windowed
campaign.  The terminal source file deliberately extends to `10000646000`,
so no file is truncated or re-encoded at the boundary.

## Fail-closed importer

[`lmfdb_zeta_prefix.py`](../../tg_verifier/lmfdb_zeta_prefix.py) checks:

- the SHA-256 and size of the ordered file list and source MD5 manifest;
- exactly 14,580 unique, strictly increasing source filenames and a one-to-one
  checksum row for each;
- the exact little-endian `uint64` file header, every
  `binary64,binary64,uint64,uint64` block header, and every 13-byte `uint104`
  delta;
- exact within-file and cross-file height/count continuity;
- nondecreasing stored ordinates while retaining duplicate multiplicity
  slots rather than assuming zero simplicity;
- strict containment of every stated ordinate interval in its source block;
- the exact non-ambiguous target cut; and
- an ordered SHA-256 leaf/aggregate commitment over the locally obtained
  source bytes.

The upstream MD5 values are treated only as legacy source identities.  Every
locally audited file receives a fresh SHA-256 in the retained receipt.  A
missing, reordered, duplicated, renamed, truncated, extended, or
checksum-mismatched file fails.

The reviewed inventory and terminal file can be exercised with:

```bash
python3 tools/tg_lmfdb_zeta_prefix.py \
  /path/to/filelist /path/to/md5sum.log \
  --target-file /path/to/data/zeros_9998546000.dat --pretty
```

On the local host, streaming and decoding the 92.1 MB terminal file took
about four seconds.  The prefix contains roughly 32.13 billion 13-byte slots,
so the payload alone is about 418 GB.  At the observed single-download rate
of about 10.4 MB/s, transfer is approximately eleven hours; exact Python
decoding is on the order of five hours at the terminal-file rate.  These are
local measurements, not an Azure service-level promise.

## Trust boundary

The binary database is a compact output artifact.  Its headers and zero
ordinates do not, by themselves, prove that the values are zeros of
Mathlib's `riemannZeta`, or that no off-line zeros were missed.  The importer
therefore emits:

```text
source_turing_completeness_independently_replayed = false
source_claim_ready = false
receipt_eligible_without_realization = false
```

There are two sound ways to close this boundary:

1. treat the exact public LMFDB/Platt completeness assertion and Hardy-Z
   realization as an explicit, reviewed premise of the one trusted-compute
   axiom; or
2. use the database only as candidate data and independently replay rigorous
   Hardy-Z sign brackets plus Turing endpoint counts.  The second route is
   preferred for an independently computed proof and composes with
   `StreamingChunkVerifier` and `TuringWindowCertificate`.

An Azure confidential-compute receipt proves which pinned importer processed
which bytes.  It cannot turn an unaudited source assertion into mathematics;
the retained receipt and Lean bridge must keep that distinction visible.

## Public sources

- [LMFDB source and completeness description](https://www.lmfdb.org/knowledge/show/rcs.source.zeros.zeta)
- [LMFDB zeta-zero dataset](https://www.lmfdb.org/zeros/zeta/)
- [LMFDB bulk data directory](https://beta.lmfdb.org/riemann-zeta-zeros/)
- [Pinned LMFDB reader source](https://github.com/LMFDB/lmfdb/blob/d0ab659fdc4f3433ea4ce7f68fe5d82d3970056a/lmfdb/zeros/zeta/platt_zeros.py)
