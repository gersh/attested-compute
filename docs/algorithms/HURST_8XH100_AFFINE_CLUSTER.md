# Hurst terminal range on eight Azure H100 workers

## Status

`tg_verifier/hurst_h100_affine_cluster.py` is a production-shaped distributed
orchestrator for

```text
[10^12 + 1, 10^16 + 1).
```

The documented Azure `Standard_NCC40ads_H100_v5` topology supplies one H100
per VM.  Production is therefore:

1. one measured CPU-handoff/preparation job;
2. eight independent, one-H100 worker jobs on eight Azure nodes; and
3. one offline exact reducer/replay job.

The module also retains a bounded local multi-GPU harness for tests.  That
harness is explicitly rejected for a production plan and is not presented as
the Azure deployment topology.

This is executable finite-computation and receipt-replay machinery.  It is not
yet a secure-enclave attestation, a compiler-refinement proof, or a Lean
theorem asserting that the CUDA rows are mathematical Möbius values.

## Why the workers can run independently

For one contiguous range `S`, the CUDA worker returns

```text
delta(S) = (ΔM(S), ΔQ(S))
guard(S) = [LM(S), UM(S)] × [LQ(S), UQ(S)].
```

If `(m, q)` is the exact state immediately before `S`, the transition is

```text
(m, q) ↦ (m + ΔM(S), q + ΔQ(S)).
```

The guard endpoints are computed from prefixes internal to `S`; they describe
which incoming `(m, q)` values make all checked Hurst and squarefree
inequalities hold on `S`.  They do not require a previous GPU worker to finish
first.

Suppose `D_i` is the sum of deltas before worker `i`.  The reducer derives the
real worker input by an exclusive scan:

```text
incoming_i = cpu_handoff + D_i.
```

It checks `incoming_i ∈ guard(S_i)`.  To express worker `i`'s guard as a guard
on the original CPU handoff, it subtracts `D_i` from each corresponding
endpoint.  Global lower endpoints are maxima, global upper endpoints are
minima, and equal values retain the earliest source order.  This is the exact
associative affine composition used by the sequential runner.

## Proxy inputs are not sequential states

An independent CUDA process still needs concrete M/Q fields for its internal
receipt recurrence.  The plan supplies deterministic proxy values, but neither
execution nor reduction assumes that they are the real prefix state.

The independent replay:

- verifies every leaf transition and digest relative to the stated proxy;
- reconstructs the delta and normalized extrema;
- reports whether the proxy happened to lie in the guard as a diagnostic; and
- does **not** require that diagnostic to be true.

Only the exact prefix-derived state is required to lie in the guard.  Plans,
worker bundles, scans, and results all retain:

```text
proxy_state_is_sequential_state: false
proxy_guard_acceptance_required: false
proxy_inputs_used_as_sequential_states: false
```

The bounded end-to-end test deliberately uses a second-worker proxy outside
its guard while the derived real input is inside; reduction succeeds only for
the latter.

## Production partition

With 1-billion-row super-shards, the range divides exactly into eight equal
pieces:

```text
rows per H100:         1,249,875,000,000,000
super-shards per H100:             1,249,875
total rows:            9,999,000,000,000,000
```

The same equal row partition is obtained with the materialized 100-million-row
default because the source count is divisible by both geometries.

Each Azure worker sees its node's sole H100 as logical device zero:

```text
/usr/bin/env CUDA_VISIBLE_DEVICES=0 \
  <sealed-runner> ... \
  --require-device-class nvidia-h100-sm90 \
  --device 0
```

The persistent runner checks the visible device against the reviewed H100
class.  `CUDA_VISIBLE_DEVICES` is process routing, not hardware identity or
attestation, and every artifact records that distinction.

## Production commands

Preparation produces the CPU handoff, exact eight-way plan, and portable
per-worker command manifest:

```bash
python3 tools/tg_hurst_h100_affine_cluster.py prepare \
  HURST_MATERIALIZATION \
  --output-dir HURST_DISTRIBUTED_PREPARED
```

Schedule each index `0` through `7` on a separate
`Standard_NCC40ads_H100_v5` node:

```bash
python3 tools/tg_hurst_h100_affine_cluster.py run-worker \
  HURST_MATERIALIZATION \
  HURST_DISTRIBUTED_PREPARED \
  --worker-index INDEX \
  --output-dir WORKER_OUTPUT
```

After all eight immutable bundles are available, run the reducer with one
`--worker-dir` argument per bundle:

```bash
python3 tools/tg_hurst_h100_affine_cluster.py reduce \
  HURST_MATERIALIZATION \
  HURST_DISTRIBUTED_PREPARED \
  --worker-dir WORKER_00 \
  --worker-dir WORKER_01 \
  --worker-dir WORKER_02 \
  --worker-dir WORKER_03 \
  --worker-dir WORKER_04 \
  --worker-dir WORKER_05 \
  --worker-dir WORKER_06 \
  --worker-dir WORKER_07 \
  --output-dir HURST_REDUCED_RESULT
```

## Fail-closed bindings

- The hybrid materialization authenticates the CPU runner, CUDA runner,
  source-prime roster, source files, and fixed geometry.
- Runners and the roster are copied into sealed in-memory descriptors before
  execution.
- Every prepared CPU artifact is content-pinned.  Consumers replay both CPU
  receipts, reconstruct the handoff, rebuild the exact cluster plan and
  scheduler-command manifest, and reject any difference.
- Each worker has a unique leaf-chain anchor committing to the distributed
  plan, range, proxy state, and worker index.
- Each worker independently replays its complete JSONL stream before
  publishing an immutable bundle.
- The reducer rereads every JSONL record through one bounded-line pass that
  simultaneously computes the stream digest.  It checks terminal geometry,
  state recurrence, allocation geometry, selected-prime counts, leaf hashes,
  flags, and exact extrema.
- The reducer reconstructs each status object exactly, checks the bundle's
  status digest, and rejects changed stream, stderr, diagnostic, semantic, or
  routing fields.
- The ordered reducer binds stream hashes, final-leaf hashes, deltas, local
  guards, translated guards, and derived states into a second digest chain
  rooted at the CPU handoff.
- Every prepared directory, worker bundle, and reduced result is published
  atomically and made read-only.
- Device routing and class checks remain distinct from attestation.

## Honest remaining gaps

1. Production H100 throughput is projected from the measured GB10 path; it has
   not yet been measured on the exact Azure image and H100 SKU.
2. A failed worker currently restarts its whole assigned range.  The leaf chain
   contains restart data, but partial-stream recovery is not implemented.
3. The emitted production leaf has no raw Möbius-row commitment.  The Lean
   packed-finalizer and row-realization work must still be connected to the
   compiled CUDA/SASS execution boundary.
4. An H100 class check does not establish secure hardware identity.  A
   confidential-compute attestation must bind the measured executable, inputs,
   output root, and platform evidence.
