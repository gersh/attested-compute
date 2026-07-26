# Large-q residue composition adapter

This component closes one narrow interface in the large-modulus Dirichlet
pipeline. It turns the certified Taylor-stage rectangle

```text
zeta_M(s,a/q),  s = 1/2 + i t
```

and its matching finite recovery

```text
R_M(s;q,a) = sum_(n=0)^M (q n + a)^(-s)
```

into the residue value required by the all-character transform:

```text
A_q,t(a) = q^(-s) zeta_M(s,a/q) + R_M(s;q,a).
```

It emits `TGDAFFI1`, with every unit residue placed in the exact canonical CRT
order reconstructed by `dirichlet_allchars_stage.canonical_residue_order`.
One job may contain one ordinate or a bounded consecutive batch. This is a
residue-composition adapter, not a completed-L computation, zero verifier,
Turing count, source run, or proof of `platt-dirichlet-theorem-7-1`.

## Why three upstream bindings are required

`TGDLATO1` records `(q,a,row)` and a Taylor rectangle, but it records neither
`t` nor `M`. Consequently, equality of its row labels with `TGDLREC1` is not
enough. A certified frame is accepted only with all of the following:

1. the lattice certificate manifest, which binds `TGDLATI1`, `TGDLREC1`, `M`,
   `t`, the complete request digest, the pinned FLINT runtime, and the exact
   trust-boundary flags;
2. the higher-precision Arb replay report for that certificate; and
3. the Taylor-stage receipt, which binds that exact `TGDLATI1` hash to the
   exact-checked `TGDLATO1` hash and the certificate-file hash.

Every JSON object must be canonical and its self-hash must replay. Every named
artifact's SHA-256 and length are checked before output is opened. The binary
pass then checks the headers, lengths, reserved fields, full unit-group count,
ascending `(q,a)` sequence, canonical lattice row, status, interval validity,
exact `t=5k/64` progression, and constant `M` in lockstep.

The hash chain proves consistency with the named upstream artifacts. It is not
a signature or remote-attestation mechanism by itself; the larger campaign
must still authenticate the producer/checker executions.

Synthetic KAT jobs deliberately omit those three metadata artifacts and use
the classification `synthetic_composition_kat_only`. They are rejected unless
the caller explicitly passes `--allow-synthetic-kat`, and their receipt can
never be confused with a certified composition receipt.

## Directed arithmetic

For each `(q,t)`, the producer encloses

```text
q^(-1/2-it) = q^(-1/2) (cos(t log q) - i sin(t log q)).
```

`libmpfr` computes directed bounds for `log(q)`, the exact rational scaling by
`t`, `sqrt(q)`, and the reciprocal. Sine and cosine are evaluated at one end
of the directed angle interval and inflated by its complete width. This is
rigorous because both functions are globally 1-Lipschitz; it avoids an
unstated monotonicity or range-reduction assumption. The MPFR interval is then
rounded outward to binary64.

The complex multiply and add use the natural rectangle extension. Every
binary64 product, sum, and difference is expanded with `nextafter` in the
required direction. The default NumPy backend vectorises exactly those
operations; a scalar backend implements the same schedule, and the tests
require both backends to be byte-identical.

The separate
`reference/tg_dirichlet_residue_composition_mpfr.cpp` checker reconstructs the
CRT order and repeats the complete factor, multiply, and add at 384-bit MPFR
precision. It shares binary structures but no Python interval operators. The
KAT also narrows an output to infinity and requires rejection.

## Canonical job

A job is canonical JSON with schema
`sparkinterval.tg.dirichlet_residue_composition.job.v1`. Production jobs use
`certified_upstream_composition_not_atom_closure` and contain one modulus,
consecutive source-grid ordinates, and one frame record per ordinate:

```json
{
  "classification": "certified_upstream_composition_not_atom_closure",
  "first_t_numerator": 635,
  "frames": [
    {
      "finite_recovery": {"path": "t127/finite-recovery.bin", "sha256": "...", "size_bytes": 0},
      "lattice_certificate": {"path": "t127/certificate.json", "sha256": "...", "size_bytes": 0},
      "lattice_input": {"path": "t127/lattice-input.bin", "sha256": "...", "size_bytes": 0},
      "lattice_output": {"path": "t127/lattice-output.bin", "sha256": "...", "size_bytes": 0},
      "lattice_replay": {"path": "t127/replay.json", "sha256": "...", "size_bytes": 0},
      "lattice_stage_receipt": {"path": "t127/receipt.json", "sha256": "...", "size_bytes": 0}
    }
  ],
  "q": 10001,
  "schema": "sparkinterval.tg.dirichlet_residue_composition.job.v1",
  "schema_version": 1,
  "t_denominator": 64,
  "t_step_numerator": 5
}
```

The zero `size_bytes` values above are placeholders, not valid records. Use
`artifact_record(path, relative_to=job_directory)` to obtain the exact digest
and positive length. A frame must cover every unit modulo `q`; truncated
certificate samples are not production input.

Run a standalone batch with:

```bash
python3 tools/tg_dirichlet_residue_composition.py --pretty capability
python3 tools/tg_dirichlet_residue_composition.py --pretty work --batch-size 64
python3 tools/tg_dirichlet_residue_composition.py compose JOB.json BATCH.bin \
  --receipt COMPOSITION.json
```

## Bounded persistent interface

Retaining every 32-byte residue rectangle on the main positive grid would use
exactly `10,466,854,601,056,256` bytes, about 10.47 decimal PB. This adapter
does not require that materialisation.

It holds and emits one ordinate at a time. At the maximum group order
`phi(399989)=399988`, the raw live interval frame is `12,799,616` bytes. The
vector backend's conservative one-frame payload/map/temporary bound is
`512*phi(q) + 4*q + 2 MiB` (about 208 MB at that maximum), excluding fixed
Python/NumPy runtime and OS page-cache overhead. Batch size changes streamed
bytes, not the number of resident frames. A batch of 64 at the maximum order
has `819,175,496` bytes on the wire.

`serve` keeps one MPFR runtime and one modulus's CRT plan alive while reading
canonical request lines on standard input for file or FIFO outputs:

```json
{"job":"/work/q10001/b127/job.json","output":"/run/tgd/q10001.fifo","receipt":"/work/q10001/b127/composition.json","schema":"sparkinterval.tg.dirichlet_residue_composition.service_request.v1","schema_version":1}
```

```bash
python3 tools/tg_dirichlet_residue_composition.py serve < requests.jsonl
```

`output` may be a named pipe. The KAT consumes a two-ordinate FIFO and confirms
that no campaign output file is retained. Ordinary paths are written with
flush, `fsync`, and atomic rename.

The source-scale handoff is `framed-produce`. Its standard input is a live
canonical JSONL control channel. Each line names one ready composition job and
the path for its compact receipt:

```json
{"job":"/work/q10001/b127/job.json","receipt":"/work/q10001/b127/composition.json","schema":"sparkinterval.tg.dirichlet_residue_composition.framed_request.v1","schema_version":1}
```

Its standard output is **only** the concatenation of the resulting
self-delimiting `TGDAFFI1` frames; it never closes that channel between jobs or
mixes status JSON into it. It requires one `q`, one denominator/step, contiguous
ordinates, and the configured maximum batch size. Control lines can arrive
only after each bounded upstream job is ready, so neither all q-jobs nor the
residue stream must be pre-materialised.

It connects directly to the all-character runner's persistent framed service:

```text
CONTROL_SOURCE |
  python3 tools/tg_dirichlet_residue_composition.py \
    --max-batch-count 64 framed-produce COMPOSER-SUMMARY.json |
  sparkinterval-tg-dirichlet-allchars \
    --framed-service Q 64 FFT-SUMMARY.json DEVICE |
  COMPLETED_L_ZERO_CONSUMER
```

On clean control EOF the composer publishes a compact summary with hashes of
the canonical control JSONL and exact concatenated TGDAFFI1 stream, plus a
Merkle root of ordered composition-receipt self-hashes. The TGDAFFI1 digest
must equal the all-character summary's `input_stream_sha256`.
The transform retains one q-specific CUDA plan and emits corresponding
concatenated `TGDAFFO1` frames. The unit KAT confirms two differently sized,
contiguous jobs form a pure binary stream with no retained output frames; the
all-character stage has its own framed-service KAT.

The directly compatible framed components now exist, but a production
campaign supervisor which launches them, streams upstream certificate jobs,
enforces backpressure, propagates cancellation/failure in both directions,
and binds the downstream completed-L consumer is still absent. Therefore the
capability flags say:

```text
source_scale_storage_bounded                    true
persistent_framed_producer_ready                true
persistent_allchars_framed_service_compatible   true
production_supervisor_wired                     false
end_to_end_streaming_supervisor_ready            false
source_scale_performance_validated               false
production_ready_for_full_atom                   false
```

No claim should replace those flags with a generic `production_ready=true`.

## Exact main-grid work

For `10001 <= q <= 400000` and the main positive `5/64` grid, the exact work
reported by `source_work(batch_size=64)` is:

| Quantity | Exact value |
|---|---:|
| modulus/ordinate factors `q^(-s)` | `4,901,051,274` |
| residue compositions | `327,089,206,283,008` |
| complex interval multiplies | `327,089,206,283,008` |
| complex interval additions | `327,089,206,283,008` |
| distinct endpoint-product candidates | `5,233,427,300,528,128` |
| endpoint addition/subtraction candidates | `2,616,713,650,264,064` |
| batch-64 invocations | `76,770,217` |

These counts exclude lattice generation, Taylor reconstruction, FFT work,
completed-L operations, padding, upsampling, exceptions, zero isolation, and
Turing windows.

## Tests and independent replay

The Python suite is self-contained apart from runtime `libmpfr` and NumPy:

```bash
python3 -m unittest -v tests.test_tg_dirichlet_residue_composition
```

Because this task intentionally does not change shared CMake, compile the
independent checker explicitly (or add it only in a later coordinated build
change):

```bash
c++ -std=c++20 -O2 -Wall -Wextra -Werror \
  -Igpu/include -I/path/to/mpfr/include \
  reference/tg_dirichlet_residue_composition_mpfr.cpp \
  /path/to/libmpfr.so /path/to/libgmp.so \
  -o /tmp/tg-dirichlet-residue-composition-mpfr

python3 tests/tg_dirichlet_residue_composition_mpfr_kat.py \
  --checker /tmp/tg-dirichlet-residue-composition-mpfr
```

The unit suite covers canonical batching, exact residue order, MPFR-factor
sanity, byte-identical persistent-workspace reuse across cache hits and
modulus changes, explicit-close rejection, scalar/vector equality, certified
metadata-chain acceptance, synthetic-mode gating, pre-output hash rejection,
rehashed `t` mismatch, rehashed request permutation, FIFO streaming,
persistent JSONL service, exact work counts, pure contiguous framed stdout,
and capability flags.

## Representative measurements

The following July 21, 2026 measurements used Python 3.12.3, NumPy 2.4.4,
MPFR 4.2.1, and the local 20-core aarch64 Cortex-X925/A725 host. Each row is a
single synthetic run of the full adapter path: SHA-256 validation, lockstep
parsing, MPFR factors, vector outward arithmetic, CRT reorder, output hash,
flush, `fsync`, and atomic rename. Fixture generation and the independent
384-bit replay are excluded.

| `q` | batch | values | upstream bytes | output bytes | seconds | values/s |
|---:|---:|---:|---:|---:|---:|---:|
| `10001` | 1 | `9,792` | `2,223,780` | `313,416` | `0.032536` | `0.301M` |
| `10001` | 8 | `78,336` | `17,790,240` | `2,506,824` | `0.067176` | `1.166M` |
| `100000` | 2 | `80,000` | `11,697,480` | `2,560,072` | `0.121536` | `0.658M` |
| `399989` | 1 | `399,988` | `49,047,300` | `12,799,688` | `0.776949` | `0.515M` |
| `399989` | 4 | `1,599,952` | `196,189,200` | `51,198,536` | `1.227584` | `1.303M` |

Reproduce a row with, for example:

```bash
python3 tools/benchmark_tg_dirichlet_residue_composition.py \
  --q 399989 --batch-count 4
```

These are representative component measurements, not a weighted full-domain
rate and not a source ETA. The slower one-batch rows include cold CRT-plan
construction which the persistent service amortises. Even the observed
batched rates require a multi-process/pre-fetch design to keep up with the GPU
Taylor and all-character stages; that weighted integration has not been
implemented or measured, hence `source_scale_performance_validated=false`.

## Remaining boundary

Completion of this adapter does not provide any of the following:

- a production supervisor around the now-compatible composer/FFT framed services;
- a production completed-L/Hardy-value and zero-scan consumer;
- primitive-frequency retention, conjugate handling, or exceptional replay;
- the small-modulus algorithm;
- zero isolation with multiplicities;
- the required Turing completeness computation and its formal realization;
- a full source execution, authenticated campaign receipt, or external-atom
  discharge.

Those gaps are live and intentionally repeated in every capability and
composition receipt.
