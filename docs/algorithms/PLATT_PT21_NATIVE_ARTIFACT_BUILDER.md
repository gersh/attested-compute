# PT21 native v2 artifact builder

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

`reference/tg_platt_pt21_native_artifact_builder.cpp` is a compact native
streaming checker for the canonical
`sparkinterval.tg.platt-pt21-lean-block-artifact.v2` document.  It exists only
to remove the measured Python exact-rational replay from the finite PT21 hot
path.  It is not a proof of anything: no DD disk, Arb interval, sign bit, or
digest is promoted to a theorem about Hardy Z, and no readiness, acceptance,
attestation, or `source_claim_ready` flag is produced or changed by it.

## Two independent implementations, byte identity required

The Python reference finalizer stays.  It is the oracle:

- `tg_verifier/platt_pt21_fused_artifact.py` builds the artifact with
  `fractions.Fraction` and rechecks it with
  `tg_verifier/platt_pt21_lean_artifact.py`;
- `reference/tg_platt_pt21_native_artifact_builder.cpp` rebuilds the same
  document with GMP `mpq` and revalidates it with a C++ transcription of the
  same contract.

`tests/test_tg_platt_pt21_native_artifact_builder.py` requires the two to
produce **identical bytes** on every accepted fixture.  A relaxation of that
comparison would defeat the purpose of keeping both.

## What the native side recomputes

From one `PT21SGN1` packet and one canonical fused source trace:

1. the fixed packet header, both version-1 wire checksums, the unused high
   sign bits, every DD disk guard, and every sign-bit/disk agreement;
2. the strict canonical-JSON form of the source trace, its duplicate-key
   rejection, its pinned identities, and its all-false semantic status;
3. every stationary resolution: one conservative cell, dyadic offsets in
   canonical lowest terms, no zero-containing endpoint, and exactly two strict
   sign changes;
4. all three streams: direct sign-change events, stationary candidates, their
   brackets, the exact endpoint enclosures, and the canonical sort order;
5. both one-sided Turing quotients, their unique ceiling/floor, and the
   `lower + main slots = upper` closure; and
6. the complete artifact contract again — bracket ordering, touching-endpoint
   agreement, boundary agreement, resolver pairing, endpoint parity, and the
   event-to-bracket binding — before any byte is emitted.

## Exact arithmetic, filter discipline

Every artifact-visible quantity is an exact GMP rational.  `mpq_set_d`
converts a finite binary64 exactly, which is required: accepted subnormals
reach denominator `2**1074`, so no fixed-width integer type covers the packet
language.

Outward-widened binary64 enclosures are used only as a strict-comparison
filter for stationary candidacy, matching `PT21StationaryCandidateFilter` and
the existing C++ event replay.  A comparison that is neither certified nor
separated falls back to the exact rational predicate.  A failed or
inconclusive fast comparison is never used as a decision.  The randomised
differential test counts the triples the filter cannot decide and asserts that
count is nonzero, so the fallback is exercised, not merely present.

The residual low-level premise is unchanged and still explicit: that the
binary64 `nextafter` widenings really enclose the executed additions and
subtractions is an IEEE/architecture refinement obligation, not a theorem
here.

## Interfaces

One-shot:

```bash
sparkinterval-tg-platt-pt21-native-artifact-builder \
  --required-sign-packet PACKET \
  --source-trace TRACE \
  [--output CREATE_ONLY_PATH]
```

Without `--output` the canonical bytes go to standard output.  Inputs are
opened without following symbolic links and must be regular files of the
exact expected length.

Framed persistent mode is `--stream`.  The 104-byte request is:

| offset | bytes | value |
|---:|---:|---|
| 0 | 8 | `PT21ABQ1` |
| 8 | 4 | version `1` |
| 12 | 4 | request bytes `104` |
| 16 | 8 | request id, starting at zero and strictly increasing |
| 24 | 8 | packet bytes `621202` |
| 32 | 8 | source-trace bytes |
| 40 | 32 | packet SHA-256 |
| 72 | 32 | source-trace SHA-256 |

followed by the packet and then the trace.  The 112-byte `PT21ABR1` response
binds the request id, artifact length, block, window centre, packet SHA-256,
and artifact SHA-256, and is followed by the canonical artifact bytes.  The
process rejects a wrong magic, version, length, out-of-order id, or a payload
whose digest differs, and it emits nothing on standard output when it fails.

## What the Python side still does on the fast path

`tg_verifier/platt_pt21_native_artifact_fastpath.py` never selects the native
builder implicitly: every entry point requires the expected executable
SHA-256, and the image is copied into a sealed `memfd` and re-hashed before
execution, exactly like the packet-scan fast path.  On every accepted
response it independently:

- recomputes the artifact SHA-256 with `hashlib` and requires it to equal the
  digest the native builder declared, so two independent SHA-256
  implementations must agree on the value that enters `PT21BLK1`;
- re-parses the bytes with a strict duplicate-key-rejecting decoder and
  requires them to be canonical JSON with exactly one trailing newline; and
- requires the bound schema, upstream commit, block, window centre, packet
  digest, and source-trace digest to equal the inputs it supplied.

`full_reference_validation=True` additionally runs the reference exact
rational validator on the returned document.  It is off by default on the
fast path, because that validator is a large part of the cost the fast path
exists to remove; the differential known answers run it.

The fast-path record-adapter entry points
`adapt_block_native_artifact_fastpath` and
`adapt_block_native_artifact_session` deliberately skip the Python
`load_required_sign_packet` decode, because the native builder repeats it in
full and refuses to emit an artifact whose bound window centre differs.  The
reference `adapt_block` keeps the Python decoder unchanged.  Neither fast-path
function is reachable from the manifest, shard, or production entry points.

## Bounded measurement

DGX Spark, aarch64 Cortex-X925, 2026-07-26, one repeated block-zero fixture
(2,242,113-byte artifact, 3,469 main slots).  Same host, same fixture, medians:

| stage | median | runs |
|---|---:|---:|
| Python reference `build_block_artifact` | 0.16435 s | 15 |
| Python reference `adapt_block` (whole `PT21BLK1`) | 0.16699 s | 15 |
| native fast-path adapter, pinned one-shot | 0.06495 s | 15 |
| native fast-path adapter, pinned session | 0.06780 s | 15 |
| native builder alone, unpinned one-shot process | 0.01881 s | 15 |
| native builder alone, warm framed response | 0.02503 s | 31 |
| pinned session framed response, as timed by the driver | 0.02649 s | 11 |
| Python independent revalidation of the returned bytes | 0.03141 s | 11 |

That is `2.46x` on the whole record adapter, for byte-identical `PT21BLK1`,
source-trace, and block-artifact output.

What is still slow, and why:

- the Python independent revalidation (`0.03141 s`) is now the single largest
  component.  Roughly `0.0085 s` is `json.loads`, `0.0118 s` is the canonical
  re-serialisation used to prove the bytes are the canonical form, and the
  remainder is the duplicate-key hook and the comparison.  Removing it would
  make the retained record depend on the native builder alone, which is
  exactly the dependency this design refuses;
- inside the native builder, SHA-256 over the 2.24 MiB artifact costs about
  `0.011 s` with the repository's portable implementation (~200 MB/s on this
  host, which has unused ARMv8 SHA2 instructions).  It is retained because it
  is the independent cross-check on the digest committed into `PT21BLK1`;
- the packet decode plus its two byte-wise version-1 wire checksums cost about
  `0.004 s`, stream construction about `0.005 s`, and canonical emission about
  `0.003 s`.

These are bounded component timings on one resident, repeated synthetic
fixture.  No source transform, source-sized input/output, or source-scale rate
was measured, and they do not support a campaign ETA.

## Build and verify

```bash
cmake --build build --target \
  sparkinterval-tg-platt-pt21-native-artifact-builder

TG_PLATT_PT21_NATIVE_ARTIFACT_BUILDER=\
build/sparkinterval-tg-platt-pt21-native-artifact-builder \
PYTHONPATH=. python3 -m unittest -v \
  tests.test_tg_platt_pt21_native_artifact_builder

ctest --test-dir build -R tg_platt_pt21_native_artifact_builder
```

The known answers cover byte identity against the Python reference on a flat
packet, on the terminal campaign block `2966443782` whose window contains the
exact PT21 source height, on the block-zero packet with synthetic dyadic
resolutions, and on the block-zero packet with the retained measured
FLINT/Arb source trace; three
randomised packets containing subnormal magnitudes, `1e300` magnitudes,
nonzero DD low words, and one-ulp separations that force the exact fallback;
persistent-session repetition; `PT21BLK1` equality through the record adapter
for both the one-shot and session fast paths; and fail-closed rejection of a
non-canonical trace, a trace bound to another packet, a trace claiming an
analytic realization, a missing stationary resolution, a truncated packet, a
flipped sample byte, an unpinned executable, a mismatched payload digest, and
an out-of-order request id.

`tools/benchmark_tg_platt_pt21_native_artifact_builder.py` reproduces the
table above; it byte-compares every fast-path result against the Python
reference before timing it.

## Remaining boundary

Unchanged.  This is an optimization of one already implemented finite stage.
The measured fused H100 worker still does not emit these per-window inputs,
`external_atom_discharged`, `production_accept`, `all_window_fused_stream`,
Hardy-Z endpoint realization, multiplicity realization, analytic Turing
realization, Lean source realization, prefix admission, attestation, the full
run, target-SKU measurement, and a supported cost result all remain separate
blockers.
