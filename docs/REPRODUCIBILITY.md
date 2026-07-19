# Reproducibility

## Development checks

Run the native DGX build with:

```bash
./tools/build_dgx_spark.sh
```

The script rejects a non-Arm host, a device other than compute capability
12.1, or a missing required tool. It builds Lean and CUDA, runs the
development-sized CTests, captures tool/platform versions and probe output,
and extracts PTX, cubin, and SASS inspection files below `build/`.

The individual proof and test commands are:

```bash
lake build
./tools/audit_axioms.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
cmake -S . -B build/dgx-spark \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/dgx-spark --parallel
ctest --test-dir build/dgx-spark --output-on-failure
```

CTest deliberately uses development-sized samples. It is not the Phase 4
acceptance run.

## Phase 4 acceptance runs

The retained primitive command was:

```bash
python3 tools/run_primitive_conformance.py --count 1250000 \
  --work-dir build/primitive-conformance/rows-1250000 \
  > build/primitive-conformance-1250000.json
```

Here `--count` is per operation. The run compared 5,000,000 randomized valid
operations plus 80 curated valid cases, checked 26 invalid rows, and found zero
mismatches. Exact CPU comparison took about 559.33 seconds; the sum of four
kernel event times was about 1.015 ms. Those timings cover different scopes
and must not be compared as end-to-end speedups.

The retained expression command was:

```bash
python3 tools/run_expression_conformance.py --count 1000000 \
  --program-count 256 \
  --work-dir build/expression-conformance/rows-1000000-programs-256 \
  > build/expression-conformance-1000000-programs-256.json
```

Here `--count` is the total randomized program/row count shared across 256
deterministic random programs. Including 3,504 curated cases, 1,003,504 rows
were checked with zero mismatches. The exact reference took about 598.32
seconds and the sum of kernel event times was about 31.06 ms. The report uses
seed `119429655`, records valid/zero-divisor/widening status counts, hashes the
executable and audited PTX/SASS, and replays one identical input to require a
byte-identical output hash.

The conformance report's `accepted` field means that every endpoint, status,
reserved byte, malformed-input decision, and requested artifact audit matched
the oracle/policy. It does not mean every generated row had status zero.

## Phase 5 generated-PTX slice

After `lake build` and the CMake build, reproduce the base polynomial run and
then the independent strong-acceptance closure:

```bash
python3 tools/run_generated_ptx_conformance.py \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --count 100000 \
  --work-dir build/generated-ptx-conformance/rows-100000
python3 tools/close_generated_ptx_acceptance.py \
  --work-dir build/generated-ptx-conformance/rows-100000 \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --phase4 build/dgx-spark/sparkinterval-expression-batch
```

The retained run checked one fixed nontrivial polynomial on 100,000 interval
rows plus nine pairwise signed-zero multiplication rows. It had zero exact or
status mismatches; 38,377 rows were status zero and 61,623 deliberately
reported nonfinite-intermediate widening. The final retained base
exact-reference evaluation took about 329.35 seconds, and the closure's
independent recomputation took about 332.11 seconds. The report records those
counts directly, and the closure derives them again from the bound payload.

The base path performs the operations in this order: audit the generated PTX,
assemble it with `ptxas`, disassemble and audit the resulting cubin, then load
and execute those exact cubin bytes. The closure independently recomputes every
exact result and status, requires byte-identical PTX and cubin regeneration,
replays the same cubin, checks the literal signed-zero suite the same way,
requires equality with the Phase 4 CUDA payload, and re-audits SASS from the
bound cubin. It therefore costs another exact-reference pass rather than being
a cheap report-only check. The PTX audit performs compact demand analysis and
value numbering, then predicts exact directed-arithmetic, min/max-selector,
load-width, and store counts for SASS. Eleven structurally different generated
polynomials were assembled and disassembled as integration tests for that
model. The specialized audit also verifies that six `HFMA2` instructions are
reviewed source-independent constant-forming idioms and that none is
input-dependent fused arithmetic. This accepts only
`const`, `var`, `neg`, add/subtract/multiply, and natural powers—not the full
expression language or a formal PTX-to-SASS correctness theorem.

After closure succeeds, package all arithmetic evidence in the existing
canonical local bundle format:

```bash
python3 tools/create_dgx_generated_cubin_bundle.py \
  --work-dir build/generated-ptx-conformance/rows-100000 \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --phase4 build/dgx-spark/sparkinterval-expression-batch \
  --output-root build/generated-cubin-run-bundle/rows-100000 \
  --start-time-utc "$RUN_START_UTC" \
  --end-time-utc "$RUN_END_UTC" \
  --nonce "$CHALLENGER_NONCE_HEX"
python3 tools/verify_run_bundle.py \
  build/generated-cubin-run-bundle/rows-100000/run-bundle.json \
  --artifact-root build/generated-cubin-run-bundle/rows-100000
```

The retained bundle has SHA-256
`679b8b5eb9ddc64d054e3990415a8c91301dc7ff24387fcd6832afc8f1d81469`.
Integrity verification passes with `hardware_evidence: false`; the supplied
times and nonce are local record fields unless a challenger provides and
tracks them.

## Real-zeta POC and operator signature

After building `sparkinterval-expression-batch`, create and independently
verify the tutorial-scale real-value calculation:

```bash
python3 tools/run_zeta_poc.py run \
  --work-dir build/examples/zeta2-4096 \
  --s 2 --terms 4096 \
  --nonce "$CHALLENGER_NONCE_HEX"
python3 tools/run_zeta_poc.py verify build/examples/zeta2-4096
```

For every `n` from 1 through 4,096, the GPU evaluates the fixed postfix
expression `1 / n^2`. Verification reparses the exact binary input and both
outputs, recomputes every endpoint/status from rational arithmetic, folds the
intervals in ascending order, re-runs the PTX/SASS auditors, and applies the
tail theorem

```text
1 / 4097 <= sum_{n=4097}^infinity 1/n^2 <= 1 / 4096.
```

The retained GB10 result is:

- real binary64 enclosure:
  `[3ffa51a65a53d51c, 3ffa51a66a52e51f]`;
- report SHA-256:
  `78ad333b0edd71b7caea460e84e8fbb3d59a2a220b245ad7227b8ec0347d112c`;
- local bundle SHA-256:
  `67808216ef8a5bb8eacc60706f694a3f47082057cd23fac01312079800828316`;
- statement SHA-256:
  `9c1c914e96b6ecd5121a66a6f400bfeb76509615df0868b86a8d721bdc39cdec`;
- evidence `local_unattested`, `hardware_evidence: false`.

The algorithm and scope are fixed in
`docs/algorithms/REAL_ZETA_POC.md`. A different positive integer `s` uses the
same command, subject to `2 <= s <= 64`, the row limit, and rejection when the
reviewed binary64 power program would become nonfinite.

To authenticate an operator's endorsement of the completed local record,
generate an Ed25519 key, sign, and verify with a separate public-key pin:

```bash
python3 tools/local_operator_signature.py keygen \
  --private-key build/examples/operator-key/operator-private.pem \
  --public-key build/examples/operator-key/operator-public.pem \
  --allow-unencrypted-private-key
python3 tools/local_operator_signature.py sign \
  build/examples/zeta2-4096/run-bundle.json \
  --artifact-root build/examples/zeta2-4096 \
  --private-key build/examples/operator-key/operator-private.pem \
  --out build/examples/zeta2-4096/run-bundle.signature.json
python3 tools/verify_run_bundle.py \
  build/examples/zeta2-4096/run-bundle.json \
  --artifact-root build/examples/zeta2-4096 \
  --policy dgx_operator_signed \
  --operator-signature build/examples/zeta2-4096/run-bundle.signature.json \
  --trusted-operator-key build/examples/operator-key/operator-public.pem \
  --replay-db build/examples/verifier/operator-nonces.sqlite3
```

The test key generated for the retained run had key ID
`b20c3db5bcaae7e92d037486db746f4661a1184a1142891fc8711f7bda53b310`;
the detached signature file SHA-256 is
`02694c8a4bf386b51f2187b58015e887bb3c0e18075dda0b9d9e0bda3a09c9f1`.
This disposable key is not a project trust root. Successful verification said
`operator_signature_valid: true` and still said `hardware_evidence: false`;
the second use of the same replay database rejected the nonce.

## Offline H100 checks

```bash
./tools/build_h100_offline.sh
./tests/test_h100_offline.sh
./tools/build_h100_interval_batch_offline.sh
./tests/test_h100_interval_batch_offline.sh
```

These are cross-device builds only. The current hardware-acceptance script is
a fail-closed stub and cannot accept a result. A real provider must first be
implemented and tested inside a supported measured x86/H100 confidential
workload.

## Preserving evidence

The build directory is intentionally not committed. Preserve each report and
all referenced artifacts together. A hash verifies identity only when the
expected hash arrives through a trusted channel; a manifest and the files it
hashes can otherwise be replaced together.

For deterministic comparisons, use the pinned `lean-toolchain`, the recorded
NVIDIA toolkit/driver, the CMake configuration, `lake-manifest.json`, the
mathlib revision in `dependencies/mathlib4.commit`, and a clean source commit.
The native build rejects a Lake mathlib checkout at another revision. Absolute
paths and NVIDIA diagnostic formatting can vary while raw PTX/cubin identity
remains stable, so compare the recorded raw artifact hashes rather than
assuming every text dump is byte-identical.
