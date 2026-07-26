# Fused large-q certified-box CUDA batch

This component removes the hidden one-process/one-kernel-per-ordinate shape
from the large-modulus Dirichlet path. One persistent process owns one modulus
`q`; each input frame contains at most 64 consecutive ordinates, and one CUDA
kernel performs all of

```text
Taylor reconstruction:
  zeta_M(s,a/q) = sum_(k=0)^15 c_k(s,r/D) (r/D-a/q)^k + tail box

Residue composition:
  A_q,t(a) = q^(-s) zeta_M(s,a/q) + R_M(s;q,a),
  R_M(s;q,a) = sum_(n=0)^M (q n + a)^(-s).
```

The output is one ordinary `TGDAFFI1` frame in the canonical mixed-radix CRT
residue order expected by the persistent all-character transform. This is a
conditional arithmetic component for Platt's large-`q` method, not a zero
isolation, Turing count, full source run, or proof of Theorem 7.1.

The current sign-quadrant interval multiplication and exact source-grid
ordinate scaling, including bounded GB10 comparisons and all four CUDA
sanitizer modes, are qualified in
[`DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md`](DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md).

The first operand-level post-compilation theorem for this kernel is documented
in [`DIRICHLET_LARGEQ_SASS_VALIDATION_SLICE.md`](DIRICHLET_LARGEQ_SASS_VALIDATION_SLICE.md).
It covers exactly the final imaginary-component recovery addback in one pinned
CUDA 13.0 SM90 cubin; it is not a whole-kernel SASS or hardware proof.

## Honest transcendental boundary

The CUDA source contains no `sin`, `cos`, `log`, `exp`, `pow`, or other
libdevice transcendental call. It consumes four kinds of certified data:

1. Arb-enclosed Hurwitz lattice cells for each `t`;
2. an exact-rational upper bound for the Taylor remainder at each residue;
3. Arb-enclosed finite-recovery sums `R_M(s;q,a)`; and
4. an MPFR-enclosed rectangle for `q^(-s)` at each `t`.

The kernel then uses only CUDA's directed binary64 `__d*_{rd,ru}` operations.
Products use sign-quadrant endpoint selection, falling back to all four
endpoint combinations when both inputs cross zero; this computes the same
outward hull with fewer multiplications. Complex products, Taylor recurrences,
tail inflation, and addback are natural outward interval extensions. CUDA
libdevice is therefore not part of the transcendental trust story.

`tg_verifier/dirichlet_largeq_batch.py` validates the existing lattice
certificate and its independent higher-precision replay. It checks exact
artifact hashes, runtime identities, source parameters, all request labels,
the complete-residue condition, and the replay decisions. Unlike the older
composition adapter, it intentionally does not require a materialized
`TGDLATO1`: the fused kernel performs the Taylor reconstruction itself.

This is the strongest currently implemented honest boundary. A finite-
recovery GPU implementation would itself need a proof-quality logarithm and
trigonometric range reduction. CUDA libdevice does not supply directed,
correctly rounded interval semantics, so this stage accepts independently
generated finite-recovery boxes instead of relabeling an ordinary CUDA
transcendental as certified.

The packed `TGDLQBI1` binary is meaningful only together with its canonical
input receipt and authenticated execution record. The runner structurally
validates every interval and independently reconstructs every CRT descriptor,
but an arbitrary finite box is not self-authenticating. The receipt binds the
binary SHA-256 to the upstream certificate/replay hashes and the exact MPFR
factor endpoints.

## Binary layout and bounded memory

One self-delimiting frame contains, in order:

```text
96-byte InputHeader
phi(q) ResidueDescriptor records                 (8 bytes each)
batch_count MPFR q^(-s) boxes                   (32 bytes each)
batch_count * 2048 * 16 Hurwitz boxes           (32 bytes each)
batch_count * phi(q) tail/recovery boxes         (40 bytes each)
```

At `batch_count=64` and the maximum group order `phi(399989)=399988`, the
largest input frame is exactly `1,094,280,192` bytes. The Python packer holds
one canonical recovery-box frame (at most `15,999,520` bytes) at a time while
streaming the lattice sections. The CUDA runner retains reusable device
buffers for the largest frame seen by the q-specific service.

The persistent interface is a pure binary pipe:

```bash
sparkinterval-tg-dirichlet-largeq-batch \
  --framed-service Q 64 LARGEQ-SUMMARY.json DEVICE \
  < concatenated-TGDLQBI1 \
  > concatenated-TGDAFFI1
```

It rejects a changed `q`, changed `M`, a non-contiguous ordinate, a batch over
64, a non-source-grid ordinate, or a noncanonical descriptor. It retains its
CUDA allocations, uses exactly one fused kernel launch per accepted frame,
and publishes input-digest-chain and output-stream SHA-256 values. A strict
build additionally rejects any runtime device other than compute capability
9.0.

## Exact source work and remaining I/O

For `10001 <= q <= 400000`, the main positive `5/64` grid, and batches of 64,
`source_work()` reports:

| Quantity | Exact value |
|---|---:|
| Old one-ordinate process/kernel invocations | `4,901,051,274` |
| Persistent q process invocations | `390,000` |
| Process invocations avoided | `4,900,661,274` |
| Fused batch kernel launches | `76,770,217` |
| Kernel launches avoided | `4,824,281,057` |
| Launch reduction | `63.8405291208x` |
| Taylor reconstructions/compositions | `327,089,206,283,008` |
| Packed lattice-cell traffic in the q-outer schedule | `5,139,124,740,685,824` bytes |
| Packed tail plus finite-recovery traffic | `13,083,568,251,320,320` bytes |

This table is the retained all-modulus V1 model.  The primitive-only V2
source roster removes all 97,500 empty-character moduli before this stage and
has 3,637,613,167 ordinate jobs, 292,500 active moduli, 56,981,100 batch-64
invocations, and 266,697,737,764,848 compositions.  A V1 artifact cannot be
silently reinterpreted as V2.
| Repeated descriptors | `41,076,229,002,496` bytes |
| MPFR factor boxes | `156,833,640,768` bytes |
| Headers | `7,369,940,832` bytes |
| Total certified input traffic | `18,263,933,424,590,240` bytes (`18.264` decimal PB) |

This figure is intentionally not hidden. The stage eliminates roughly 4.824
billion launches and all intermediate `TGDLATO1` traffic, but it does not
eliminate the work needed to generate and replay the analytic input boxes.
Source operation needs those generators colocated with the consumer and a
backpressured memory/FIFO pipeline; writing 18.264 PB to retained files is not
a viable production plan.

Accordingly, the machine-readable capability deliberately says
`source_performance_ready=false`, `certified_box_producer_integrated=false`,
and `source_scale_io_plan_implemented=false`. The fused CUDA component is real;
the source-scale producer/I/O graph is not yet implemented.

The newer [certified recurrence-seed path](DIRICHLET_RECOVERY_SEEDED_STAGE.md)
removes the finite-recovery and repeated-tail part of this boundary. It uses
the exact `t=5j/64` identity to replace those 13.084 PB by one fully replayed
96-MB seed artifact and fuses directed recurrence into Taylor composition.
Its compact full-source logical input is 5.180 PB. That path still needs the
remaining Hurwitz-lattice reuse and source-wide width audit, so it does not
change this v1 capability record into a theorem claim. A separate
[t-major cache contract](DIRICHLET_LATTICE_CACHE.md) now reduces the unique
lattice payload to 125 GiB and implements bounded authentication and an exact
broadcast schedule. The follow-on
[`TGDLTMB1` path](DIRICHLET_TMAJOR_CUDA_BLOCK.md) eliminates the descriptor and
q-major frame repetitions too, giving an exact 339.469-GB binary input and a
one-upload CUDA consumer. No populated source cache, source run, or downstream
FFT/zero integration yet realizes the complete route.

For scale, an aggregate sustained input rate of 40, 80, or 200 GB/s across an
eight-GPU job would spend approximately 126.8, 63.4, or 25.4 hours moving this
logical payload. These are bandwidth arithmetic, not measured Azure rates and
not an end-to-end ETA. The implemented t-major CUDA path avoids this host-side
repetition, but its mixed-q output must still be reconciled with the
q-persistent all-character FFT plan.

## Local benchmark and H100 sensitivity

On the repository's NVIDIA GB10, a synthetic `q=10001`, 64-ordinate frame has
`626,688` output values and a `92,256,864`-byte input. Seven alternating
pre-optimization and five optimized twenty-kernel runs measured medians of
`68,075,322` and `115,113,093` residue values/s, respectively. The exact
changes and byte-identical output comparison are recorded in
[`DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md`](DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md).

At the optimized kernel rate the retained V1 exact residue count is about 789
single-GB10 GPU-hours, or 98.7 hours on eight equal GPUs. Purely as a
sensitivity band, a 5x--10x H100 speedup over this GB10 kernel is 9.9--19.7
hours on eight H100s.
That excludes generation/replay of the certified boxes and can be dominated by
the 18.264 PB streaming boundary. It must not be presented as the duration of
Platt's complete verification.

## Build and replay

The files are isolated so they can be reviewed before changing shared CMake:

```cmake
add_executable(sparkinterval-tg-dirichlet-largeq-batch
  gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu)
target_include_directories(sparkinterval-tg-dirichlet-largeq-batch
  PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/gpu/include)
set_property(TARGET sparkinterval-tg-dirichlet-largeq-batch
  PROPERTY CUDA_ARCHITECTURES ${CMAKE_CUDA_ARCHITECTURES})
set_property(TARGET sparkinterval-tg-dirichlet-largeq-batch
  PROPERTY CUDA_STANDARD 20)

add_executable(sparkinterval-h100-tg-dirichlet-largeq-batch
  gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu)
target_include_directories(sparkinterval-h100-tg-dirichlet-largeq-batch
  PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/gpu/include)
target_compile_definitions(sparkinterval-h100-tg-dirichlet-largeq-batch
  PRIVATE SPARKINTERVAL_REQUIRE_H100_SM90=1)
set_property(TARGET sparkinterval-h100-tg-dirichlet-largeq-batch
  PROPERTY CUDA_ARCHITECTURES 90)
set_property(TARGET sparkinterval-h100-tg-dirichlet-largeq-batch
  PROPERTY CUDA_STANDARD 20)
```

Manual build used for the local KAT:

```bash
nvcc -std=c++20 -O3 -lineinfo -arch=sm_121 -I gpu/include \
  gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu \
  -o runner

nvcc -std=c++20 -O3 -lineinfo -arch=sm_90 \
  -DSPARKINTERVAL_REQUIRE_H100_SM90=1 -I gpu/include \
  gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu \
  -o runner-sm90
```

Author and pack a batch:

```bash
python3 tools/tg_dirichlet_largeq_batch.py capability
python3 tools/tg_dirichlet_largeq_batch.py work --batch-size 64
python3 tools/tg_dirichlet_largeq_batch.py \
  convert-composition-job OLD-JOB.json LARGEQ-JOB.json --certified
python3 tools/tg_dirichlet_largeq_batch.py pack \
  LARGEQ-JOB.json TGDLQBI1.bin --receipt INPUT-RECEIPT.json
runner TGDLQBI1.bin TGDAFFI1.bin 0 1
```

The synthetic KAT generates exact Taylor outputs from the same lattice, runs
the old scalar composition path, runs the fused CUDA path, and asks the
independent 384-bit MPFR composition checker to accept the CUDA output. It
checks all `19,584` values, rejects a forged CRT descriptor, and exercises two
contiguous frames through the persistent service:

```bash
python3 tests/tg_dirichlet_largeq_batch_known_answers.py \
  --runner RUNNER \
  --lattice-checker TG-DIRICHLET-LATTICE-EXACT \
  --composition-checker TG-DIRICHLET-RESIDUE-COMPOSITION-MPFR
```

The KAT is synthetic and explicitly reports
`external_atom_discharged=false`.
