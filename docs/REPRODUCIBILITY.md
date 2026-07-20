# Reproducibility and verification runbook

This runbook describes how to produce fresh evidence from a chosen source
revision. It does not treat previously observed hashes, timings, or test counts
as proof for a new checkout.

Run commands from the repository root. Before starting, record the commit and
whether the checkout is dirty:

```bash
git rev-parse HEAD
git status --short
```

Build output is ignored by Git. Use a fresh directory for every retained run
so files from different source revisions cannot be mixed:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
VERIFY_ROOT="build/verification/${RUN_ID}"
mkdir -p build/verification
mkdir "${VERIFY_ROOT}"
```

The final `mkdir` intentionally fails if the timestamped directory already
exists. The certificate generator, zeta runner, and generated-cubin packager
also reject an existing destination where mixing evidence would be unsafe.

All Lean and CMake commands below use the repository's bounded entry points.
Do not replace them with bare parallel builds; see
[Memory-safe builds](MEMORY_SAFE_BUILDS.md).

## Routine Lean and CPU validation

The axiom audit includes the complete serialized Lean build. Run it together
with the Python suite for the hardware-independent validation path:

```bash
./tools/audit_axioms.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The safe Lean planner builds one dependency closure at a time. If any Lean
source changes while its plan is active, it exits with status 66; rerun the
whole command against one stable source snapshot.

The axiom audit distinguishes Lean's reported foundational dependencies,
explicit proof-reflection dependencies, and the sole named project execution
postulate, `accepted_run_certificate_sound`. The DGX and H100 entry points are
proved compatibility theorems over that one boundary.
`accepted_registered_run_sound` is also a proved projection: a matching closed
`RegisteredInvocation.statementCheck` exposes the invocation's fixed `Runs`
relation. Interpret the result using the
[correctness claims](CORRECTNESS_CLAIMS.md) and [trust model](TRUST_MODEL.md).
For the current cubic tutorial, the independently checkable side includes the
executable integer loop, exact operational result, rational-specification
agreement, and u64 bounds for every cube and accumulator step. These theorems
are axiom-free; they do not reproduce or verify a GPU execution.

## Full Lean result certificate

The checked-in example can be validated without a GPU. Generate into the fresh
verification root because the generator refuses to overwrite a Lean source:

```bash
CERT_DIR="${VERIFY_ROOT}/full-certificate"
CERT_BOUND=4010000000000001
mkdir "${CERT_DIR}"

./tools/safe_lake_build.py SparkInterval.Certificate \
  --target sparkinterval-check-certificate
./tools/with_memory_limit.sh \
  .lake/build/bin/sparkinterval-check-certificate \
  examples/lean-result-certificate/certificate.json \
  --upper-bound "${CERT_BOUND}" \
  > "${CERT_DIR}/checker-output.json"
python3 tools/generate_lean_result_certificate.py \
  --certificate examples/lean-result-certificate/certificate.json \
  --upper-bound "${CERT_BOUND}" \
  --output "${CERT_DIR}/GeneratedFullCertificate.lean" \
  > "${CERT_DIR}/receipt.json"
./tools/safe_lean.sh "${CERT_DIR}/GeneratedFullCertificate.lean"
```

This uses the default `kernel` decision mode. For a deliberately selected
native-reduction check, add `--decision-mode native` and use a different output
directory. The mode, certificate digest, bound, theorem names, and generated
source digest are recorded in the receipt. See the
[certificate format reference](FORMAT.md#lean-decision-modes) before comparing
the resulting axiom reports.

## Native DGX Spark baseline

On the supported one-GPU DGX Spark profile, run:

```bash
./tools/build_dgx_spark.sh
```

The script validates the Arm host and GB10 target, performs the bounded Lean
and one-job CUDA/C++ builds, runs regression-sized tests, captures the local
environment, and creates a diagnostic `local_unattested` bundle. Those routine
samples are regression checks, not the large arithmetic acceptance runs below.
See [DGX Spark setup](DGX_SPARK_SETUP.md) for prerequisites and expected
artifacts.

## Large CUDA arithmetic acceptance

The primitive count is per operation; the expression count is the total
randomized program/row count shared across the selected programs. The values
below reproduce the repository's documented large validation scale while
keeping all outputs under this run's fresh root:

```bash
PRIMITIVE_ROWS_PER_OPERATION=1250000
EXPRESSION_CASES=1000000
EXPRESSION_PROGRAMS=256
PRIMITIVE_DIR="${VERIFY_ROOT}/primitive-conformance"
EXPRESSION_DIR="${VERIFY_ROOT}/expression-conformance"
mkdir "${PRIMITIVE_DIR}" "${EXPRESSION_DIR}"

python3 tools/run_primitive_conformance.py \
  --count "${PRIMITIVE_ROWS_PER_OPERATION}" \
  --work-dir "${PRIMITIVE_DIR}" \
  > "${PRIMITIVE_DIR}/report.json"
python3 tools/run_expression_conformance.py \
  --count "${EXPRESSION_CASES}" \
  --program-count "${EXPRESSION_PROGRAMS}" \
  --work-dir "${EXPRESSION_DIR}" \
  > "${EXPRESSION_DIR}/report.json"
```

Require each command to exit successfully and inspect its report rather than
relying on filenames or expected historical hashes. A report records status
counts as well as bit comparisons; an accepted run can include explicitly
classified zero-divisor or nonfinite-intermediate rows. Applications must
still enforce the statuses they permit.

Exact rational CPU recomputation can dominate wall-clock time. GPU event time
and complete verification time measure different work and should not be
reported as an end-to-end speedup without that distinction.

## Generated-PTX closure and bundle

The generated polynomial path first runs the typed generator and exact cubin,
then independently closes the result by regenerating code, reassembling and
replaying the cubin, recomputing exact outputs, rerunning audits, and comparing
the native expression backend.

```bash
GENERATED_ROWS=100000
GENERATED_DIR="${VERIFY_ROOT}/generated-ptx-conformance"
GENERATED_BUNDLE_DIR="${VERIFY_ROOT}/generated-cubin-bundle"
GENERATED_START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 tools/run_generated_ptx_conformance.py \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --count "${GENERATED_ROWS}" \
  --work-dir "${GENERATED_DIR}" \
  > "${VERIFY_ROOT}/generated-ptx-summary.json"
python3 tools/close_generated_ptx_acceptance.py \
  --work-dir "${GENERATED_DIR}" \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --expression-runner build/dgx-spark/sparkinterval-expression-batch \
  > "${VERIFY_ROOT}/generated-closure-summary.json"

GENERATED_END_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 tools/create_dgx_generated_cubin_bundle.py \
  --work-dir "${GENERATED_DIR}" \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --expression-runner build/dgx-spark/sparkinterval-expression-batch \
  --output-root "${GENERATED_BUNDLE_DIR}" \
  --start-time-utc "${GENERATED_START_UTC}" \
  --end-time-utc "${GENERATED_END_UTC}" \
  > "${VERIFY_ROOT}/generated-bundle-summary.json"
python3 tools/verify_run_bundle.py \
  "${GENERATED_BUNDLE_DIR}/run-bundle.json" \
  --artifact-root "${GENERATED_BUNDLE_DIR}" \
  > "${VERIFY_ROOT}/generated-bundle-verification.json"
```

The packager uses a locally random nonce when `--nonce` is omitted. That gives
uniqueness, not challenger freshness. For a freshness claim, a verifier must
supply and retain an unpredictable 64-lowercase-hex nonce before execution;
add the packager's `--nonce` option with that exact verifier-supplied value.

The resulting DGX record remains `local_unattested` and must report
`hardware_evidence: false`. The closure is strong differential and artifact
evidence for the external backend; the Lean theorem itself stops at the typed
AST and machine model.

## DGX real-integer zeta tutorial

After the native DGX build, create and independently verify a fresh tutorial
run:

```bash
ZETA_DIR="${VERIFY_ROOT}/zeta2-4096"

python3 tools/run_zeta_poc.py run \
  --work-dir "${ZETA_DIR}" \
  --s 2 \
  --terms 4096 \
  > "${VERIFY_ROOT}/zeta-run-receipt.json"
python3 tools/run_zeta_poc.py verify "${ZETA_DIR}" \
  > "${VERIFY_ROOT}/zeta-verification.json"
```

Verification reparses the staged expression and rows, exactly recomputes all
term intervals and the outward reduction, checks byte-identical GPU replay,
reruns the PTX/SASS audits, verifies the local bundle, and applies the stated
integral-test tail. The result is a rigorous positive real-value enclosure and
a local execution record; it is not a critical-strip zero or height-coverage
certificate. See the [zeta tutorial](algorithms/REAL_ZETA_POC.md).

An operator may sign the resulting bundle using the procedure in
[Detached DGX operator signatures](FORMAT.md#detached-dgx-operator-signatures).
The signature authenticates the operator key's endorsement, not physical GPU
execution.

## High-bound foundation host microbenchmark

The bounded host-only smoke benchmark is reproducible without CUDA:

```bash
python3 tools/benchmark_zeta_foundations.py \
  --pretty \
  --output "${VERIFY_ROOT}/zeta-foundations-host-benchmark.json"
```

Retain the full JSON configuration and measurement notes. The reported work is
Python binary-power schedule validation plus generation, streaming decoding,
exact-integer local checking, and adjacent ordering of a synthetic fixed-width
rational-bracket format. `peak_memory_bytes` is `tracemalloc` peak Python
allocation for each phase—not process RSS, GPU memory, or certificate storage.
`synthetic_certificate_bytes` is exact only for that benchmark format, and
throughput includes tracing overhead.

Do not report these values as zeta evaluation/zero-verification throughput,
Lean elaboration/kernel-check performance, GPU performance, or production
certificate size. The benchmark exercises bounded chunk retention and the
linear adjacent-check pattern only. See the
[high-bound verifier status](algorithms/ZETA_ZERO_VERIFIER.md#host-foundation-microbenchmark).

## H100 native local validation

Run this section only on an `x86_64` host with exactly one visible NVIDIA H100
at compute capability 9.0. The strict runners require device zero and reject
the generic cross-device override.

Use directories inside the fresh verification root so native artifacts and
retained evidence cannot be mixed with an earlier run:

```bash
H100_BUILD_DIR="${VERIFY_ROOT}/h100-native-build"
H100_EVIDENCE_DIR="${VERIFY_ROOT}/h100-native-evidence"

H100_BUILD_JOBS=1 ./tools/run_h100_native_validation.sh \
  --build-dir "${H100_BUILD_DIR}" \
  --output-dir "${H100_EVIDENCE_DIR}" \
  --primitive-count 10000 \
  --expression-count 10000 \
  --expression-program-count 8 \
  --device 0 \
  | tee "${VERIFY_ROOT}/h100-native-validation.log"
```

The script configures the H100 CMake targets, builds with one job, runs the
offline fail-closed CLI/`sm_90` image CTest, audits the device code, executes
the directed-rounding probe, and performs exact primitive and expression
conformance. The fixed probe cubin is generated at:

```text
${H100_BUILD_DIR}/h100/h100_rounding_probe.sm_90.cubin
```

The probe and conformance reports are local diagnostic evidence. They do not
contain NVIDIA confidential-computing attestation.

### H100 real-integer zeta POC

Use the expression runner from that exact build and retain both receipts:

```bash
H100_ZETA_DIR="${VERIFY_ROOT}/h100-zeta2-4096"

python3 tools/run_zeta_poc.py run \
  --target-profile h100_sm90 \
  --executable "${H100_BUILD_DIR}/sparkinterval-h100-expression-batch" \
  --work-dir "${H100_ZETA_DIR}" \
  --s 2 \
  --terms 4096 \
  --device 0 \
  > "${VERIFY_ROOT}/h100-zeta-run-receipt.json"
python3 tools/run_zeta_poc.py verify "${H100_ZETA_DIR}" \
  > "${VERIFY_ROOT}/h100-zeta-verification.json"
```

Require the verification receipt to name `target_profile: h100_sm90`,
`evidence_class: local_unattested`, and `hardware_evidence: false`. Preserve
the entire H100 zeta directory; verification needs the executable, exact input
and both outputs, source snapshot, PTX/SASS and audits, report, and run bundle.
This is a real-value enclosure for integer `s > 1`, not a zero-isolation,
high-bound zero-verification, or confidential-computing workflow.

### Lean-generated polynomial `sm_90` conformance

The target-selected generated path is separate from the division-capable zeta
runner. Build the Lean generator and CUDA driver from the same checkout, then
retain the generated work directory:

```bash
./tools/safe_lake_build.py --target sparkinterval-gen
cmake --build "${H100_BUILD_DIR}" \
  --target sparkinterval-generated-driver \
  --parallel 1

H100_GENERATED_DIR="${VERIFY_ROOT}/generated-sm90-conformance"
mkdir "${H100_GENERATED_DIR}"
python3 tools/run_generated_ptx_conformance.py \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver "${H100_BUILD_DIR}/sparkinterval-generated-driver" \
  --target sm_90 \
  --count 4096 \
  --work-dir "${H100_GENERATED_DIR}" \
  > "${VERIFY_ROOT}/generated-sm90-summary.json"
```

Check `report.json` for `accepted: true` and `target: sm_90`. The primary
generated cubin and SASS are
`${H100_GENERATED_DIR}/kernel.sm_90.cubin` and
`${H100_GENERATED_DIR}/kernel.sm_90.sass.txt`; the signed-zero probe has the
corresponding `signed-zero-kernel.sm_90.*` names. The current closure and
canonical generated-cubin bundle tools remain DGX/`sm_121` specific, so this
H100 report is local conformance evidence rather than a closed or CC-attested
bundle.

## H100 offline validation

The H100 test scripts each perform their own offline build and then validate
the resulting PTX, cubin, SASS, metadata, hashes, and fail-closed integration
behavior. Give them fresh roots:

```bash
./tests/test_h100_offline.sh "${VERIFY_ROOT}/h100-probe-test"
./tests/test_h100_interval_batch_offline.sh \
  "${VERIFY_ROOT}/h100-interval-batch-test"
```

These commands do not query an H100, execute a kernel on one, return an H100
arithmetic result, or obtain production attestation. Do not run the separate
build scripts first; the tests invoke them internally. See the
[H100 guide](H100.md) for the native and production boundaries.

## Preserve and hand off evidence

Preserve a retained run's complete directory, not only its top-level report.
The verifier needs every artifact named by the report or bundle, including
inputs, outputs, source snapshots, PTX, cubin, SASS, audit reports,
executables, and toolchain metadata.

Also record:

- the clean source commit and dependency revisions (`lean-toolchain`,
  `lake-manifest.json`, and `dependencies/mathlib4.commit`);
- host architecture and OS, GPU identity, CUDA toolkit, driver, `ptxas`,
  `cuobjdump`, and `nvdisasm` versions captured by the applicable build
  workflow;
- the exact commands and non-default arguments;
- any verifier-supplied challenge and the verifier's persistent replay state;
  and
- the expected top-level digest through a channel independent of the artifact
  directory.

A manifest and all files it hashes can be replaced together. SHA-256 establishes
identity only relative to an expected digest or accepted evidence chain. Never
archive private operator keys or passphrases with run evidence.

When a future trusted importer constructs a Lean `RunCertificate`, preserve the
exact accepted statement, evidence-verifier output, policy and root versions,
and result artifact bytes. Also preserve the canonical registry preimages for
algorithm definition, input, parameters, and domain whenever the registered
projection is claimed. The one Lean axiom converts acceptance into both the
historical return and the fixed `Runs` relation for every matching closed
invocation; it does not prove a universal backend theorem or deterministic
behavior for later physical runs. Preserve the exact full result certificate
as well when downstream Lean mathematics is independently checked. The current
repository has no wire-to-private-capability importer.

For a registered implementation, also archive the reviewed algorithm version
and the proof audit for its operational semantics and arithmetic bounds. In the
current tutorial, those checks prove the integer accumulator/divide-once model
and all u64 step bounds, but not correspondence to GPU opcodes.

For deterministic comparisons, compare the canonical data and raw artifact
hashes. Absolute paths, timestamps, and NVIDIA diagnostic text can legitimately
vary between environments even when the relevant source and device images are
the intended ones.
