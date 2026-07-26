# Platt source-semantic complex-disk prototype

`gpu/platform/h100/h100_tg_platt_windowed_disk_semantic.cu` is an experimental
binary64 `center + Euclidean radius` implementation of the exact transform
dataflow in `h100_tg_platt_windowed_semantic.cu`. It follows the upstream
Platt commit `42b21426718e542daa2b006dc05ea2d7f26426e6` through:

1. the 23-row `G_k` recurrence;
2. the negative `G_k` transforms, `21/128` scale, truncation, error, and sign;
3. both positive convolution transforms, the pointwise products, and the
   normalized negative transforms;
4. the Taylor-row sum and all published transform/error insertions; and
5. Platt's literal `hermidft` preprocessing and final positive transform.

The runner now has two deliberately distinct input modes.  Its small KAT still
uses synthetic exact dyadics.  The source integration path consumes the fixed
binary packet exported by `h100_tg_platt_windowed_core.cu`: the actual
first-window Gamma row synthesized from the compact Gamma packet and all 23
actual bucketed Taylor rows accumulated from the source formula.  The header
records whether all 768,000 terms were present, and a partial packet can never
be reported as complete source input.

That is a real source-core dataflow integration, but still not a zeta
certificate.  In particular, the analytic theorem saying the compact Gamma
coefficients enclose the mathematical log-Gamma branch and the physical CUDA
refinement of the source accumulator remain separate obligations.

Two source encodings share the same fixed 128-byte little-endian header.  V1
uses binary64 Cartesian intervals and magic `PT21SRC1`.  The current narrow
V2 uses two-limb Cartesian centers plus an honest Euclidean radius and magic
`PT21SRC2`; each complex cell is five binary64 words.  Both contain 32,768
Gamma cells and `23 * 32,768` bucket cells.  The header pins the schema,
endian marker, source-term count, window center, payload lengths, separate
FNV-1a payload commitments, and the 40-byte upstream commit.  The complete
file is bound by SHA-256. `tools/tg_platt_source_packet.py` independently
validates either encoding, the exact length and commitments, and all 786,432
cells.

The V2 source rows are no longer host-injected first-window values.  The CUDA
producer stores each logarithmic turn at Q192, re-anchors every requested
window from its absolute integral height, evaluates a directed degree-39/38
two-limb sine/cosine pair, scales by the two-limb amplitude disk, and forms all
23 bucket rows.  An independent directed-MPFR check recomputes the source
expression for all 768,000 terms and refuses the run if any exact term is not
contained by its CUDA output disk.  This is a strong KAT and a failure-closed
runtime gate; the physical CUDA-to-mathematics refinement theorem remains
open and is reported as such.

## Formal boundary

The arithmetic decomposition is the one already proved in
`SparkInterval/Certified/ComplexDisk.lean`:

- `AddCertificate.output_contains_add` covers disk addition/subtraction;
- `MulCertificate.output_contains_mul` covers center rounding, both
  center-times-radius terms, and the radius product; and
- `centerNormSq_le_centerL1Bound_sq`,
  `productCenterErrorSq_le_productCenterErrorL1Bound_sq`, and
  `sumCenterErrorSq_le_sumCenterErrorL1Bound_sq` prove over exact rationals
  that each `|re|+|im|` value used by the optimized FFT is a valid squared
  Euclidean-norm witness for those same certificates.

The CUDA helper uses directed binary64 operations to produce the corresponding
bounds.  Immutable FFT roots retain their more accurate directed Euclidean
centre norms in a one-time 262,144-byte workspace cache; newly introduced
centre-compression errors and the varying left operand use the proved L1
upper bound.  This removes a directed divide and square root from the inner
butterfly without changing the disk semantics.  The proof is an arithmetic
postcondition, not a CUDA-instruction refinement.

The runner now exports a canonical 320-byte certificate for the
exceptional `hermidft` endpoint.  It contains both original input disks, two
96-byte multiplication certificates, and one 80-byte addition certificate.
`tools/tg_platt_disk_endpoint_certificate.py` replays every inequality with
Python integers and `Fraction`; `PlattDiskPipelineWire.lean` parses the same
little-endian words, decodes them to exact rationals, checks all links and
arithmetic, and applies `HermidftEndpointCertificate.output_contains`.

This compact certificate does **not** close the physical path for the whole
transform.  The CUDA-to-320-byte copy/refinement is not formally proved, and
no per-butterfly trace is exported for the FFTs. `WindowedRadix2.lean` proves
the FFT algorithm from checked butterfly traces, but an exporter/compressor
and a theorem binding the measured cubin to those traces are still required.
The JSON states both gaps as `false`; an endpoint certificate must never be
presented as a transform or zeta certificate.

The stable norm helper scales before squaring. This is essential because the
published `1e-307` errors would otherwise underflow on squaring and inflate to
about `1e-162`. Its result may be checked by the same exact squared inequality
used by `ComplexDisk` even though the instruction trace differs from the
simple `sqrt(re^2+im^2)` helper.

## Reproduction

The disk runner is built with the semantic-stage CMake option.  Export and
independently inspect one complete first-window packet, then consume it:

```bash
cmake -S . -B build/platt-windowed-core \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON
cmake --build build/platt-windowed-core \
  --target sparkinterval-tg-platt-windowed-core

build/platt-windowed-core/sparkinterval-tg-platt-windowed-core \
  --source-geometry --gamma-synthesis --terms=768000 --stages=23 \
  --blocks=1 --repetitions=1 --fft-passes=0 \
  --export-source-packet=/durable/platt-first-window.bin
python3 tools/tg_platt_source_packet.py \
  /durable/platt-first-window.bin

cmake -S . -B build/platt-windowed-semantic \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON
cmake --build build/platt-windowed-semantic \
  --target sparkinterval-tg-platt-windowed-disk-semantic

build/platt-windowed-semantic/sparkinterval-tg-platt-windowed-disk-semantic \
  --source-packet=/durable/platt-first-window.bin \
  --require-full-source-packet \
  --endpoint-certificate=/durable/platt-endpoint.bin \
  --repetitions=20
python3 tools/tg_platt_disk_endpoint_certificate.py check \
  /durable/platt-endpoint.bin
python3 tools/tg_platt_disk_endpoint_certificate.py emit-lean \
  /durable/platt-endpoint.bin | lake env lean /dev/stdin
```

The current V2/DD path and its replayable required-region handoff are:

```bash
build/tg-production-kat/sparkinterval-tg-platt-gamma-taylor \
  --height 10000000504 --precision 320 --degree 8 \
  --export-dd-gamma-row=/durable/platt-gamma-dd-d8.bin

build/platt-windowed-core/sparkinterval-tg-platt-windowed-core \
  --source-geometry --terms=768000 --stages=23 \
  --blocks=1 --repetitions=1 --fft-passes=0 \
  --dd-gamma-row=/durable/platt-gamma-dd-d8.bin \
  --export-source-dd-packet=/durable/platt-source-dd-v2.bin

python3 tools/tg_platt_source_packet.py /durable/platt-source-dd-v2.bin

build/platt-windowed-semantic/sparkinterval-tg-platt-windowed-dd-disk-semantic \
  --source-packet=/durable/platt-source-dd-v2.bin \
  --require-full-source-packet --require-source-region-unambiguous \
  --export-required-sign-packet=/durable/platt-required-sign.bin \
  --repetitions=20

python3 tools/tg_platt_required_sign_packet.py \
  /durable/platt-required-sign.bin \
  --source-packet=/durable/platt-source-dd-v2.bin --pretty
```

The required-sign packet contains the exact 25,741 retained two-limb real
disks followed by an LSB-first sign bitset.  Its fixed 200-byte header binds
the window center, source packet SHA-256 and size, both payload checksums, and
the upstream commit.  The independent Python consumer rechecks every disk,
recomputes every sign, rejects unused sign bits, and optionally rehashes the
entire bound source packet.  This is an interpolation/zero-isolation handoff,
not a zero-count or source-claim certificate.

The small `--length=8 --stages=3 --no-source-errors` KAT remains available and
must report `small_long_double_kat_contained: true`.  Every source result must
also be judged on ambiguity. `fabs(center) <= radius` yields no sign; the
runner records the row and `--require-unambiguous` exits unsuccessfully rather
than guessing.

The current transform also replaces power-of-two division and remainder in
bit reversal and every radix-2 stage by exactly equivalent shifts and masks.
The Python test exhaustively compares both address calculations on small
transforms and checks every stage boundary for the two source lengths.  A
fresh five-process GB10 source-shape measurement before stage fusion gave
`14.1475`--`14.1522` windows/s (median `14.1516`) and a deterministic
output FNV-1a value in every run.  The retained implementation additionally
fuses stages 1--8 in four 512-value shared-memory tiles while preserving the
ordinary butterfly order.  A seven-pair interleaved A/B measured medians
`14.1490` and `14.2107` windows/s, a further `1.0044x` gain, with byte-identical
output.  In the retained staged same-session
measurement, the immediate pre-rewrite kernel ran at `9.44250` windows/s and
the completed indexing/cache/L1 kernel at `14.26160` windows/s, a `1.510x`
gain.  The no-source-error output radius widened by about 22.8% when the
square-root-free L1 bound was enabled, but the required region remained
unambiguous and the independent long-double KAT remained contained.  These
are GB10 implementation measurements, not H100 rates or a physical
instruction proof.

## GB10 measurements

On the local NVIDIA GB10, a warmed 20-run source-shape benchmark produced:

| representation | windows/s | butterflies/s | maximum diameter | ambiguous synthetic samples |
|---|---:|---:|---:|---:|
| Cartesian boxes | 81.47 | 1.8847 billion | 0.15753 | 430 / 131072 |
| Euclidean disks | 38.21 | 0.8841 billion | 0.0001659 | 1 / 131072 |

The disk implementation is about 2.13 times slower on GB10 but its synthetic
diameter is about 950 times smaller. The single ambiguous coordinate is
reported with its index, center, and radius so an exact-zero synthetic sample
cannot be confused with general sign failure.

The complete first-window source packet was generated on the same machine on
2026-07-22:

| item | measured value |
|---|---:|
| host MPFR initialization + GPU accumulation + packet write | 38.17 s |
| peak RSS | 239,856 KiB |
| packet bytes | 25,165,952 |
| packet SHA-256 | `5e248ddc536975c8843f72ba3b8d0e8b4e5921bc42e811d0507c62545bb060ed` |
| source terms / Taylor rows | 768,000 / 23 |
| independently scanned complex intervals | 786,432 |

A warmed 20-run disk transform over that packet measured 38.142 windows/s
and 882.38 million butterflies/s.  Its maximum diameter was
`8.77062e-5`.  Crucially, **101,213 of 131,072 real samples were ambiguous**.
The implementation therefore fails the sign-usefulness gate on the actual
first window even though every output disk is finite.  It is an integration
and width diagnostic, not a viable source-wide sign certificate.  Selective
Arb replay cannot rescue a majority-ambiguous stream economically; the disk
propagation/scaling must be improved or replaced.

The endpoint frame from that run had SHA-256
`f48da5ddf2aaf9dc8adf1285225d0366bc7dddd6970a2e407e35a0a95829ea74`.
Both the independent exact-Fraction checker and Lean's kernel-reduced
`checkBytes` accepted its 320 bytes.  That result proves the arithmetic encoded
by the frame, subject to the explicit input-containment premises. It does not
prove physical provenance, the remaining 65,535 endpoint preprocess rows, any
FFT, interpolation, zero isolation, or Turing completeness.

All timings are GB10 measurements of the first source window, not H100
measurements or a full-campaign ETA.

## Two-limb width experiment

`h100_tg_platt_windowed_dd_disk_semantic.cu` implements the same transform
with two binary64 limbs per Cartesian center.  `TwoSum` and FMA `TwoProd`
retain signed residuals; every discarded residual is added to the Euclidean
radius and one least-positive subnormal is charged at each error-free
transform.  FFT roots, `omega`, stage reciprocals, and `-2*pi*t` are split
directly from 320-bit MPFR enclosures instead of first widening them to an
ordinary binary64 interval.  Sign admission uses the fail-closed lower bound

```text
abs(hi + lo) >= max(0, abs(hi) - abs(lo)).
```

The physical CUDA refinement of that two-limb arithmetic is not yet proved,
so the executable labels itself a diagnostic and never a zeta certificate.
Its independent small long-double KAT is contained, and it reports an
ambiguity count even when the command does not request strict rejection.

On the complete first-window packet above, five warmed runs measured
`11.3683` windows/s and `262.996 million` butterflies/s.  The maximum output
radius fell to `3.43325e-5`, but **100,945 of 131,072 samples remained
ambiguous**.  Thus a wider center alone does not make the existing binary64
source packet useful.

The executable has one explicitly non-proof diagnostic switch,
`--discard-source-packet-radii-for-diagnostic`.  With the same packet centers
but all Gamma/Taylor packet radii set to zero, while retaining two-limb
constant enclosures and all published analytic errors, the first window had:

| diagnostic | measured value |
|---|---:|
| ambiguous samples | `0 / 131072` |
| maximum radius | `2.33003e-22` |
| minimum sign margin | `1.44178e-21` |
| five-run rate | `11.3015 windows/s` |

Discarding those radii is intentionally not sound and cannot be accepted in
a campaign.  It localized the old width failure and motivated the now-
implemented V2 producer.

### Honest narrow V2 result

The degree-8, 320-bit FLINT Gamma row and full 768,000-term two-limb bucket
packet have no discarded source uncertainty.  On the first source window the
DD transform still has many irrelevant ambiguous samples in the far Gaussian
tails, but the exact upstream-used region is different:

```text
center 65536
radius 512 + 12288 + 70 = 12870
indices 52666 through 78406 inclusive
25741 retained samples
```

All `25,741 / 25,741` required samples had certified signs; the required-
region ambiguity count was zero.  A warmed 20-run transform measured
`11.4284343` windows/s on GB10.  Its maximum output radius was
`2.8554882000420666e-22`.  Global ambiguity remains reported
(`72,549 / 131,072`) and is not silently relabeled as success: those
far-tail cells are outside every source interpolation/Turing access.

The generated required-sign packet was 621,202 bytes.  For the retained V2
fixture it had SHA-256
`2d03c463ea38f36bd2d02fc46fb014935d5bb4e00c00fcec6cf17ddb315ca0c5`;
the independent consumer recomputed 13,047 positive and 12,694 negative
signs and rebound the 31,457,408-byte source packet with SHA-256
`4e1fc843c24aede4d954fa2afb52ed4e9d54a76f17e54868c7003a082faeb894`.
These fixture identities must be regenerated whenever the producer changes.

This result still does **not** construct a Turing or global zero count.  It
must be followed by Gaussian-sinc interpolation, zero isolation, three
separate event streams, paired-flank Turing decisions, prefix/count
continuity, and an accepted measured run.

## Three distinct completion layers

Readiness reports must keep these layers separate:

1. **Machine packet/kernel.**  V1 and V2 packet exporters/validators, Q192
   per-window two-limb source re-anchor, the DD transform, and the replayable
   25,741-cell required-sign packet are implemented.  The honest first-window
   V2 packet passes the required-region sign gate.  Production all-window
   Gamma/transform fusion, interpolation, event construction, and physical
   trace refinement are not implemented.
2. **Ordinary Lean derivation.**  Lean checks the 320-byte exceptional
   endpoint frame and proves the conditional disk/interpolation/Turing
   arithmetic.  It does not yet check a whole FFT trace or derive the PT21
   `SourceClaim` from a finite packet.  The current Turing adapter is also not
   source-shaped: the source uses independent left-flank, main, and right-
   flank event streams, while the current contract binds one list.  Source
   brackets may touch at a certified nonzero endpoint or block boundary, but
   the current Lean bracket family requires strict gaps.  Consequently there
   is no ordinary-Lean first-window proof, much less a full-range one.
3. **Trusted accepted-run wrapper.**  The repository has a generic signed-run
   admission boundary.  No Azure PT21 production run has been made or
   accepted, so that wrapper currently supplies no theorem for this claim.

An implementation in layer 1 is not evidence that layers 2 or 3 are complete.
