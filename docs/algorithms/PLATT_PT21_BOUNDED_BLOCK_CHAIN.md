# PT21 bounded stationary/Turing/native block chain

`tools/tg_platt_pt21_bounded_block_chain.py` is an executable integration
witness for the optimized finite path

```text
CUDA event scan -> PT21EVT1 -> FLINT stationary resolver -> PT21STJ1
  -> directed-Arb Turing inputs -> exact-rational replay -> PT21BLK1
  -> native bounded shard -> independent shard replay
```

It is not a PT21 source theorem and it is not a source-scale benchmark.  The
input disks are explicitly synthetic and every analytic/source-realization
flag remains false.

## Exact bounded fixture

The block-zero fixture uses the actual CUDA three-stream event scanner and
the actual FLINT Gaussian--sinc stationary resolver.  Its main stream has

- 3,465 direct sign events;
- two stationary candidates;
- two finite resolver outputs for each candidate, preserving four stationary
  multiplicity slots; and
- 3,469 total main-stream slots.

The real FLINT/Arb Turing-input producer evaluates the pinned one-sided
formulas at 128 bits and requires containment by a second 256-bit evaluation.
The exact-rational replay obtains

```text
lower count = 32,130,158,280
upper count = 32,130,161,749
gap         =          3,469
```

Thus the native count transition closes on the synthetic finite event count
without injecting or overriding a count.

The local CUDA/FLINT run used during implementation processed about 85--90
two-candidate stationary junctions per second.  This is only a bounded
component measurement.  It is not extrapolated to a source ETA.

## Authentication and independent replay

The `PT21BLK1.producer_commitment_sha256` field is the SHA-256 of a fixed
domain, the little-endian block number, and ten ordered SHA-256 digests:

1. `PT21EVT1`;
2. `PT21STJ1`;
3. the required-sign packet;
4. the canonical stationary trace;
5. the canonical directed-Arb Turing artifact;
6. the CUDA/stationary junction executable;
7. the Turing-input executable;
8. the loaded FLINT shared library;
9. the Python replay/adapter source set; and
10. the native finalizer executable.

The block record separately binds the required packet, fused source trace,
exact-rational block artifact, and stationary trace.  The independent Python
replay rebuilds the block artifact byte for byte, checks all record links,
checks `3465 + 2*2 = 3469`, recomputes the ten-input predecessor commitment,
and replays the retained native shard.

Each executable is opened without following a symbolic link, hashed from
that descriptor, and executed through the same `/proc/self/fd` descriptor.
The FLINT 3.6 loader alias `libflint.so.24` must resolve to the exact regular
file whose bytes are hashed, and that file is hashed again after the chain.
Production still has to bind the remaining dynamic runtime and architecture
through the measured Azure image/receipt.

`SparkInterval.Zeta.PT21TuringBlockJunction` gives the three fixed records a
total Lean parser/checker.  Its soundness theorem exposes all digest,
identity, count, and multiplicity relationships.  It deliberately treats the
analytic meanings of those finite bytes as external premises.

## Local bounded run

After building the existing components:

```bash
python3 tools/tg_platt_pt21_bounded_block_chain.py \
  --junction-executable \
    build/pt21-junction/sparkinterval-tg-platt-stationary-junction-benchmark \
  --turing-executable \
    build/tg-production-kat/sparkinterval-tg-platt-pt21-turing-inputs \
  --flint-library /path/to/libflint.so.24.0.0 \
  --finalizer-executable \
    build/platt-fused/sparkinterval-tg-platt-pt21-native-finalizer \
  --output-directory /new/empty/directory \
  --pretty
```

Focused verification:

```bash
python3 -m unittest -v \
  tests.test_tg_platt_pt21_bounded_block_chain \
  tests.test_tg_platt_stationary_junction \
  tests.test_tg_platt_pt21_turing_inputs \
  tests.test_tg_platt_pt21_native_record_adapter

lake build SparkInterval.Zeta.PT21TuringBlockJunction
lake env lean SparkInterval/Tests/PT21TuringBlockJunctionTest.lean
```

Mutation tests cover every predecessor digest and executable identity,
stationary records/traces, Turing bytes, exact-rational artifacts,
multiplicity-count forgery, native record bytes, and the retained shard.
`compute-sanitizer --tool memcheck` on the complete synthetic
Turing-closure CUDA scanner/junction fixture reported
`ERROR SUMMARY: 0 errors`.

## Exact remaining source-realization gaps

The bounded chain closes the finite software junction only.  The following
are still absent:

1. A proof that every production transform disk encloses the corresponding
   Hardy-Z sample at the claimed ordinate.  The bounded fixture starts at the
   scanner with synthetic disks; it does not exercise source coefficients or
   claim physical Hardy-Z semantics.
2. A theorem connecting the FLINT Gaussian--sinc interpolator and its
   directed intervals to Mathlib real/complex evaluation of Hardy Z.
3. The analytic zero-existence and multiplicity interpretation of the direct
   and stationary sign brackets.  The finite chain preserves the source's
   multiplicity-two accounting but does not prove that it counts zeta zeros.
4. The analytic one-sided Turing inequalities/argument-principle theorem that
   turns the finite Arb quantities into certified endpoint zero counts.
5. A source-scale, gap-free execution over all 2,966,443,783 windows,
   including authenticated prefix count, telescoping counts, the source-height
   block, retries, and terminal campaign finalization.
6. A production source-stream integration of the bounded
   [persistent worker](PLATT_PT21_PERSISTENT_WORKER.md).  The CUDA/FLINT and
   Arb processes can now remain resident and reproduce the one-shot
   `PT21EVT1`, `PT21STJ1`, and `PT21BLK1` bytes exactly.  The bounded witness
   still repeats synthetic block zero and retains debugging intermediates;
   source scale must feed genuine consecutive packets and replace the
   remaining Python exact-rational artifact bottleneck with a compact
   independently replayable stream.
7. Source-realized handling of nonempty sparse refinements.  `PT21STJ1` v1
   intentionally rejects them until the scanner rerun is bound.
8. Azure measured-boot, compiler/binary/architecture evidence and a signed
   confidential-compute receipt for the source-scale executable set.

Until these are supplied, `hardy_z_endpoint_realization_proved`,
`flint_to_mathlib_realization_proved`,
`main_multiplicity_realization_proved`,
`analytic_turing_realization_proved`, and `source_claim_ready` remain
`false`.
