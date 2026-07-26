# PT21 authenticated stationary junction

`PT21STJ1` is the finite, nonterminal boundary between the CUDA
three-stream event scanner and the FLINT Gaussian--sinc stationary resolver:

```text
required DD disks on device
  -> CUDA event scan and Merkle root
  -> independent host replay
  -> exact replay-owned disks + ordered candidates
  -> FLINT 3.6.0 bounded resolver and higher-precision replay
  -> 400-byte PT21STJ1
```

The implementation is:

- `gpu/include/sparkinterval/tg_platt_stationary_junction.hpp`;
- `reference/tg_platt_stationary_junction.cpp`;
- `tg_verifier/platt_pt21_stationary_junction.py`;
- `tools/tg_platt_pt21_stationary_junction.py`; and
- `SparkInterval/Zeta/PT21StationaryJunctionWire.lean`.

It does not produce `PT21BLK1`, a Turing count, or an analytic theorem.

## Exact input link

The scanner's `replay_and_check` now returns the exact 25,741 DD disks used
by its independent replay. The junction never accepts a second unbound sample
array. Before invoking FLINT, it requires:

1. a valid `PT21EVT1` for the same block;
2. accepted device-versus-host scanner replay;
3. equality of the event record's Merkle root and replay root;
4. exact equality of all three event counts, direct weights, and candidate
   counts;
5. canonical stream/offset order and every scanner candidate field, including
   zero certified slots before resolution and two slots after success; and
6. equality of a linear replay seal over the replay-owned DD bits and full
   ordered candidate rows.

The full scanner Merkle tree is already independently reconstructed once by
`replay_and_check`. An early junction prototype reconstructed the same
131,072-leaf tree again. The retained linear replay seal detects mutation
between replay and resolver consumption without repeating that tree walk.
The host replay itself precomputes every block-independent all-zero subtree
once and then hashes only ancestors of active sample/event leaves. This
preserves the exact GPU root while avoiding about 100,000 repeated zero-path
SHA-256 calls per later block.
The resolver input SHA-256 independently hashes the DD bits, the four
candidate fields actually consumed by FLINT, and all sparse refinements.

Candidate, refinement, resolver-input, and record hashes use distinct
domain strings. Sparse refinements retain exact `arf_dump_str` bytes and
strict increasing sample order. Version 1 accepts only the authenticated empty
refinement trace: the current scanner fails on an ambiguous DD disk, so a
nonempty refinement would require a fresh event scan and a new root. Until
that rerun interface exists, a nonempty trace fails rather than being linked
to the pre-refinement root.

## Fixed record

One little-endian record is exactly 400 bytes:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 8 | magic `PT21STJ1` |
| 8 | 4 | version `1` |
| 12 | 4 | record bytes `400` |
| 16 | 8 | source block |
| 24 | 8 | finite failure flags, required zero |
| 32 | 4 | stationary candidate count |
| 36 | 4 | resolution count, equal to candidate count |
| 40 | 4 | initially ambiguous DD count, required zero in v1 |
| 44 | 4 | sparse refinement count, required zero in v1 |
| 48 | 4 | resolved multiplicity slots, exactly twice candidate count |
| 52 | 4 | FLINT precision, `128` bits |
| 56 | 4 | bounded adaptive depth |
| 60 | 4 | higher-precision replay increment |
| 64 | 4 | FLINT release `30600` |
| 68 | 4 | semantic realization flags, required zero |
| 72 | 4 | deterministic resolver replay accepted, required one |
| 76 | 4 | higher-precision containment complete, required one |
| 80 | 32 | exact `PT21EVT1` record digest |
| 112 | 32 | scanner event-artifact Merkle root |
| 144 | 32 | full ordered candidate-list digest |
| 176 | 32 | exact resolver-input digest |
| 208 | 32 | sparse-refinement trace digest |
| 240 | 32 | stationary-resolution digest |
| 272 | 32 | complete canonical stationary-trace digest |
| 304 | 32 | resolver executable identity |
| 336 | 32 | FLINT library identity |
| 368 | 32 | domain-separated record digest |

No unresolved stationary candidate can pass: resolution count must equal
candidate count, native resolver replay must pass, every recorded endpoint
must contain its fresh evaluation at 64 additional precision bits, and
resolved multiplicity slots must equal `2 * candidate_count`. Any resolver
failure emits no accepted junction record.

The qualification-only V2 trace does not assume that a 192-bit Arb interval
is nested inside its 128-bit interval. It retains both and widens the record
to their exact-rational outward hull, then independently replays at 192 bits
and requires containment in that hull. The default standalone V1 trace is
unchanged. See the exact semantics, non-nesting regression fixture, and Lean
interval-algebra theorems in
[`PLATT_PT21_INLINE_STATIONARY.md`](PLATT_PT21_INLINE_STATIONARY.md).

The independent Python replay recalculates the event-record digest, candidate
digest, exact native resolver-input digest, refinement digest, stationary
resolution digest, canonical trace digest, all counts, and both installed
identity pins. The Lean checker parses all 400 bytes, checks every finite
field and digest, and proves the multiplicity-two equation from Boolean
acceptance.

## Bounded measurement

The native benchmark sends actual CUDA scanner output into the actual FLINT
3.6.0 resolver for a deterministic two-candidate arithmetic fixture. It uses
the real first, interior, and terminal block *identities* to test block
binding, but the DD values are synthetic and are not Hardy-Z values.
Its repeated-byte resolver and FLINT digests are stable known-answer pins,
not production measurements; an attested production runner must populate
those fields from its measured executable and library manifest.

After eliminating the duplicate Merkle reconstruction, a 300-record GB10
host run measured `91.553` junction records/s (`3.2768` seconds), versus
`10.663` records/s in the first prototype. The two-candidate fixture resolves
four conservative multiplicity slots per record. Sample mutation,
candidate-order mutation, event-root mutation, and an attempted nonempty
refinement all fail before an accepted record is emitted.
`compute-sanitizer --tool memcheck` over the complete CUDA-scan/junction KAT
reported `ERROR SUMMARY: 0 errors`.

A separate timing of the full independent scanner replay was `0.09155`
seconds cold and `0.03214` seconds warm after the constant zero-subtree table
was built (`31.11` warm replays/s). Replay, not FLINT resolution, remains the
CPU-side critical path, but is now about 3.5 times faster than the measured
GB10 fused transform/event rate of `8.97` blocks/s. The intended scheduler can
therefore overlap replay with the GPU stream instead of serializing the two.
This single-fixture comparison still needs a loaded target-SKU calibration.

This is a component benchmark, not a source candidate-frequency or full-run
ETA. Real first/interior/terminal DD windows, depth distributions, NUMA
placement, pinned-copy overlap, target CPU SKU, and concurrent H100 load
still require bounded production calibration.

The focused build and test are:

```bash
cmake --build build/platt-pt21 --target \
  sparkinterval-tg-platt-stationary-junction-benchmark
ctest --test-dir build/platt-pt21 \
  -R '^tg_platt_stationary_junction_known_answers$' --output-on-failure
lake build SparkInterval.Zeta.PT21StationaryJunctionWire
lake env lean SparkInterval/Tests/PT21StationaryJunctionWireTest.lean
```

## Remaining boundary

The
[qualification-only inline worker](PLATT_PT21_INLINE_STATIONARY.md) now
carries the replay-owned DD arrays and candidates directly into this resolver
immediately after the captured host replay. It avoids a second replay and
process hop and emits authenticated compact frames, but those frames do not
retain enough input to regenerate the resolver-input digest or candidate
roster independently. The
[bounded stationary/Turing/native block chain](PLATT_PT21_BOUNDED_BLOCK_CHAIN.md)
now demonstrates the next finite step on actual CUDA/FLINT algorithms:
canonical directed-Arb inputs, exact-rational Turing closure, `PT21BLK1`, and
native shard replay. Its values are explicitly synthetic. Production still
needs a source-wide measured run, an independently auditable resolver-input
boundary, native Turing integration, source-height placement, and gap-free
full-campaign closure.

The following remain false and are not fields that this wire can promote:

```text
hardy_z_endpoint_realization_proved = false
flint_to_mathlib_realization_proved = false
analytic_turing_realization_proved = false
pt21_source_claim_discharged = false
```
