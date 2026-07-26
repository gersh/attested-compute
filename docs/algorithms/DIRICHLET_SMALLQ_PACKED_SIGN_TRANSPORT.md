# Dirichlet small-q packed strict-sign transport

The factored small-q runner can emit `TGDBSPK1` instead of `TGDBSQR3`.
This is a production-runner transport optimization: it reduces the
runner-to-host stream from one 48-byte complex disk per published coordinate
to one two-bit code per coordinate. In the device mode it additionally avoids
copying the complete 24-byte disk and four-byte CUDA-status arrays from the
device. The packed stream is consumed directly by the `TGDCSB03` compact-state
writer and need not be persisted.

This is not source evidence. The runner and reducer both report all of the
following as false:

- DFT arithmetic containment replay;
- analytic seed-value and character-exponent semantic replay;
- zero isolation or multiplicity realization;
- Turing realization or closure;
- source admission, external-atom discharge, and production readiness.

## Exact decision

For a source disk with real midpoint `real`, radius `radius`, and the
parity/source-ordinate control word `threshold`, the CPU reference, host
runner mode, and device runner mode apply:

```text
boundary = nextafter(radius + threshold, +infinity)
code = 1  when real < -boundary
code = 2  when real >  boundary
code = 0  otherwise
```

The addition is a binary64 round-to-nearest operation. The CUDA implementation
spells it as `__dadd_rn(radius, threshold)` before `nextafter`. Advancing one
representable value toward positive infinity makes the boundary an outward
upper bound. Nonfinite disks, controls, or boundaries; negative radii or
controls; and any nonzero CUDA status fail before publication.

Codes are character-major and then source-sample-major. Four codes occupy
one byte in little-endian two-bit order. Code 3 is reserved. The consumer
rejects code 3 and nonzero high padding bits in the final byte of a frame.

## Framing and binding

Every batch frame independently binds:

- exact shared-plan and batch SHA-256 values;
- exact time-tail control SHA-256 and semantic replay-receipt SHA-256;
- the ordered batch-partition SHA-256;
- the plan roster and canonical compact-roster SHA-256 values;
- the externally reviewed pinset and compact source-binding SHA-256 values;
- q, source sample start/count, exact 5/64 numerator span, and
  production-versus-structural-KAT mode and host-versus-device packing
  location;
- character start/count, batch ordinal/count, work counters, and aggregate
  zero status.

The payload has its own SHA-256. A domain-separated frame SHA-256 covers the
header, all bindings, and payload; the next frame includes that digest.
A terminal `TGDBSPE1` record commits the exact frame count, item count, last
frame digest, and SHA-256 of all preceding frame bytes. The compact consumer
requires that terminal record and immediate EOF.

These hashes prevent accidental corruption, reordering, truncation, and
relabeling inside an externally bound run. They are not an attestation by
themselves: an attacker able to replace a stream and its hashes can recompute
them. The measured-run receipt must bind the final stream digest, and the
compact receipt/state pair must remain associated with that run.

## Production invocation

The CUDA executable implements runner-side packing for the full canonical
source span. It memory-maps the exact `TGDBSQT1` control through a nonsymbolic
regular-file descriptor, validates every control word and the exact
plan/partition/parity/grid binding, hashes the mapped bytes, and restats the
descriptor during and after use.

The two production modes are deliberately different:

- `--strict-sign-packed` is host mode 1. It copies the complete final disk and
  status arrays and applies the CPU rule. This remains the differential oracle.
- `--strict-sign-packed-device` is device mode 3. It uploads the already
  validated control array once, reduces the status of the complete transform
  to one bounded word, classifies the full source prefix in the final GPU
  disks, and copies only the packed payload plus the eight-byte status
  summary.

The compact reducer must be invoked with
`--expected-packing-location host` or
`--expected-packing-location device`. A mode-1 stream cannot be substituted
for a mode-3 stream, or conversely. When their sign payloads agree, the
resulting compact state is byte-identical; the receipt still records the
pinned location and the location-specific stream digest.

```bash
sparkinterval-tg-dirichlet-booker-smallq-certified \
  --source-samples-only \
  --strict-sign-packed-device CONTROL \
    CONTROL_RECEIPT_SHA256 \
    COMPACT_ROSTER_SHA256 \
    PINSET_SHA256 \
    SOURCE_BINDING_SHA256 \
  --factored-service PLAN \
  BATCH_00000000 - BATCH_00000001 - \
| python3 tools/tg_dirichlet_booker_smallq_semantic_reducer.py \
    reduce-packed-compact-v3 \
    PLAN BATCH_DIRECTORY CONTROL CONTROL_RECEIPT \
    PINSET STATE RECEIPT \
    --expected-pinset-sha256 PINSET_SHA256 \
    --expected-packing-location device
```

Every output argument must be `-` in packed mode because all frames and the
single terminal record form one stdout stream. Reports go to stderr. The
consumer also supports `--input PATH_OR_FIFO`; an ordinary pipe avoids a
persistent packed-sign family.

For a batch with `B` characters, transform length `N`, and `S` source samples,
host mode copies `28 B N` bytes from device to host before packing. Device
mode copies `ceil(B S / 4) + 8` bytes. It therefore removes the complete disk
and status transfer, not just the persistent raw stream. This transfer
reduction does not reduce the DFT arithmetic itself.

## Azure measured phase

`tools/tg_dirichlet_azure_measured_workload.py` exposes the nonterminal
`run-packed-smallq` phase and its structural
`verify-packed-smallq-trace` replay. The signed canonical input manifest
selects exactly one of these values:

| signed `packing_location` | runner option | reducer expectation |
|---|---|---|
| `runner_host_after_full_disk_d2h_v1` | `--strict-sign-packed` | `host`, wire mode 1 |
| `runner_device_after_full_dft_before_d2h_v1` | `--strict-sign-packed-device` | `device`, wire mode 3 |

There is no auto-detection or fallback between them. The location string is
bound by the production predecessor receipt, measured input hash, factory
parameters/domain, runner argv hash, location-specific frame mode, compact
receipt, result, and challenge trace. The worker also requires the runner's
single exact stderr report to name the same location and wire mode. A host
stream under a device manifest, a device stream under a host manifest, an
unknown location, or a location-only relabel fails closed.

The worker validates the exact production-signed predecessor receipt and
complete runner/source/plan/batch/control/control-receipt/pinset roster before
starting the runner. It connects runner stdout directly to the Python packed
reducer, retains only the compact-v3 state, compact receipt, and runner
stderr, and re-hashes all inputs after execution. Existing or symbolic
outputs, incomplete spans, unreviewed bytes, malformed or trailing transport
data, and digest substitutions are rejected.

`tg_verifier/azure_h100_dirichlet_packed_materializer.py` and
`tools/tg_azure_h100_dirichlet_packed_materializer.py` package that phase with
the H100 pre-run gate, exact source closure, profiles, policies, and
authenticated inputs. Their site and result formats are
`schemas/azure-h100-dirichlet-packed-materializer-site.schema.json` and
`schemas/azure-h100-dirichlet-packed-materialization.schema.json`. The result
schema requires the device-classification and full-disk-D2H-elimination flags
to be false for the host enum and true for the device enum.

This package is intentionally nonterminal: it has no registered Lean
invocation and is not selected by the source-wide portfolio router. Both
modes leave DFT containment replay, analytic seed and character-exponent
semantics, zero multiplicity, Turing closure, source admission, external-atom
discharge, and production readiness false. Device mode changes transport
location only; it does not establish any of those analytic premises.

## Verification

The CPU reference producer
`tg_verifier/dirichlet_booker_smallq_packed_stream_v1.py` is the protocol
oracle. Tests cover the exact boundary and one-ulp cases, differential
equality with direct `TGDBSQR3`-to-`TGDCSB03` reduction, payload tampering,
reserved codes, padding, mode/control relabeling, truncation, trailing bytes,
and terminal replay.

```bash
cmake --build build/tg-production-kat \
  --target sparkinterval-tg-dirichlet-booker-smallq-certified \
           sparkinterval-tg-dirichlet-strict-sign-pack-kat -j2

build/tg-production-kat/sparkinterval-tg-dirichlet-strict-sign-pack-kat

PYTHONPATH=. python3 -m unittest -v \
  tests.test_tg_dirichlet_booker_smallq_packed_stream_v1

TG_SMALLQ_CERTIFIED_RUNNER=\
build/tg-production-kat/sparkinterval-tg-dirichlet-booker-smallq-certified \
PYTHONPATH=. python3 -m unittest -v \
  tests.test_tg_dirichlet_booker_smallq_packed_stream_v1
```

On the local GB10 system on 2026-07-23, the source-compiled CUDA runner ran the
full-span synthetic q=5460 KAT (`B = 165`, `N = 262144`, `S = 234433`).
Host and device modes emitted byte-identical 9,670,362-byte sign payloads and
the independent Python reducer produced byte-identical compact states. Device
mode copied 9,670,362 payload bytes plus eight status bytes instead of
1,211,105,280 disk/status bytes: a 125.24-fold reduction (99.20%).

One measured warm local sample reported 230.6 ms for the shared CUDA
finite-Gaussian/DFT work, 8.40 ms for device status reduction plus
classification, 0.18 ms for the packed device-to-host transfer, and 0.086 ms
for the one-time control upload. End-to-end process wall time was 1.42 s in
device mode versus 1.91 s in host mode. These timings are a local synthetic
GB10 transport benchmark, reported separately from any full external-atom
ETA; they are not an H100 or source-scale analytic benchmark.

The shared CUDA KAT also checks exact-boundary ambiguity, one-ulp positive and
negative decisions, an ordinary ambiguous value, a seven-item
non-multiple-of-four payload, zero padding, and fail-closed nonzero status,
nonfinite disk, negative/nonfinite control, and boundary-overflow cases. A
second fixed-answer case uses two characters with distinct even/odd controls
and a transform stride larger than the published source prefix; it checks
determinate and ambiguous decisions, rejects a nonzero status located only in
the unpublished transform tail, and rejects parity outside 0..1.
Python tests tamper an actual device-mode frame, verify its digest rejection,
and verify that host/device mode substitution is rejected.
