# Verifier guide

This guide starts from the claim a verifier wants to establish. SparkInterval
has three independent evidence paths:

| Goal | Use | What it does not establish |
| --- | --- | --- |
| Check a mathematical result without trusting its producer | Full Lean result certificate | Who or what produced the certificate |
| Inspect the proof about generated code | Lean typed-machine and compiler theorems | That emitted PTX, SASS, or a physical GPU implements the model |
| Authenticate an execution record | Run-bundle verification, optionally with a DGX operator signature | Mathematical soundness; a DGX signature is not hardware evidence |

H100 confidential-computing acceptance is not operational in this repository.
The offline artifacts and policy plumbing cannot produce accepted hardware
evidence.

Run relative commands in this guide from the repository root.

## 1. Pin the source and toolchain

Verify from a specific clean commit and retain these identifiers with the
verification record:

```bash
git rev-parse HEAD
git status --short
cat lean-toolchain
cat dependencies/mathlib4.commit
```

`git status --short` should be empty. After the first build, confirm that the
Lake checkout matches the pinned Mathlib revision:

```bash
git -C .lake/packages/mathlib rev-parse HEAD
```

The expected revision is also declared in `lakefile.toml`. Record the Lean,
Lake, Python, CMake, CUDA, driver, and operating-system versions whenever they
are part of the claim being checked.

## 2. Build the Lean library safely

```bash
./tools/safe_lake_build.py
```

The planner builds local Lean modules serially, holds one plan-wide lock,
detects source changes during the plan, and uses the resource limits described
in [Memory-safe builds](MEMORY_SAFE_BUILDS.md). Do not substitute bare
`lake build` or `lake env lean`: those commands bypass repository-wide
serialization and can schedule several stale modules concurrently.

## 3. Audit proof dependencies

```bash
mkdir -p build/verification
set -o pipefail
./tools/audit_axioms.sh 2>&1 | tee build/verification/axiom-audit.txt
```

The first part of this command automatically rejects `sorry`, `admit`,
`unsafe`, and every source `axiom` except the two named execution bridges. The
Lean audit file then prints `#print axioms` for the public mathematical,
certificate, compiler, and typed-machine theorems.

The command also checks the printed reports automatically. It requires exactly
84 core declaration reports and permits only `propext`, `Classical.choice`,
and `Quot.sound` in that group. It separately requires exactly two execution-
bridge reports and permits those foundations plus the two named bridge axioms.
A missing report, an extra report, or any unapproved dependency fails the
audit. Retain the output so the checked declaration surface and dependencies
remain inspectable with the verification record.

The fixed audit surface does not include a certificate module generated later
for a particular witness. That generated file prints its own concrete theorem
dependencies when `safe_lean.sh` checks it; retain and interpret that output
according to its recorded decision mode. `native_decide` is a separate
proof-reflection dependency, not a project execution assumption. See
[Trust model](TRUST_MODEL.md#lean-proof-dependencies) for the exact distinction.

The two permitted project execution axioms are:

- [`dgx_operator_signed_run_sound`](../SparkInterval/Execution/Trusted/DGXOperatorSignature.lean#L24);
- [`h100_attested_run_sound`](../SparkInterval/Execution/Trusted/H100Attestation.lean#L27).

Neither is used by the mathematical certificate checker or the generated
typed-machine soundness theorems.

## 4. Verify a full Lean result certificate

A full certificate contains every input row and every claimed output row. Lean
decodes the binary64 words into exact rational intervals, reevaluates the
expression, and checks containment. The checked-in two-row example is a small
reproducible verifier exercise:

```bash
mkdir -p build/verification
CERT_DIR="$(mktemp -d build/verification/full-certificate.XXXXXX)"
./tools/safe_lake_build.py SparkInterval.Certificate \
  --target sparkinterval-check-certificate
python3 tools/generate_lean_result_certificate.py \
  --certificate examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001 \
  --output "$CERT_DIR/Generated.lean" \
  > "$CERT_DIR/receipt.json"
./tools/safe_lean.sh "$CERT_DIR/Generated.lean"
./tools/with_memory_limit.sh \
  .lake/build/bin/sparkinterval-check-certificate \
  examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001
```

Use a fresh output path: the generator refuses to overwrite an existing file
or write through a symlink. The receipt binds the source certificate, bound,
decision mode, generated declaration names, and generated Lean source.

The two last commands serve different purposes. The executable evaluates the
Lean checker and returns an acceptance decision. Compiling the generated Lean
file checks concrete theorem declarations and prints their dependencies.

### `native_decide` distinction

The omitted `--decision-mode` selects `kernel`:

- `application_upper_bound_sound` and
  `certificate_sum_upper_bound_sound` check the generated typed data with
  `decide_cbv`; their recorded dependencies do not include `native_decide`.
- The exact serialized-JSON binding, including the concrete parser and hash
  computation, uses `native_decide`. Consequently `application_theorem` and
  `application_sum_theorem` include that proof-reflection dependency.

With `--decision-mode native`, the direct typed-data checks also use
`native_decide`, so both direct and serialized concrete theorem families
include it. The mode is part of the generated namespace and receipt.

If a verification policy forbids `native_decide`, use the default direct
typed-data theorems and state the resulting scope accurately: they prove the
mathematics of the materialized Lean witness, but the current generated proof
does not then bind that witness to the exact JSON bytes. The generic checker
soundness theorems are independent of either concrete reduction mode.

Passing a certificate proves only its stated row-wise or finite-sum predicate.
It does not prove that a GPU ran or establish an unrelated application theorem.

## 5. Verify a local run bundle

Obtain the expected source commit, artifact directory, profile files, and
bundle through channels appropriate to the claim. Then check canonical format
and every bound artifact byte. Set `RUN` to the retained bundle directory:

```bash
RUN=/path/to/retained-run
python3 tools/verify_run_bundle.py \
  "$RUN/run-bundle.json" \
  --artifact-root "$RUN"
```

For `local_unattested`, acceptance establishes internal integrity relative to
the supplied files. A malicious host can fabricate the bundle and every file
it names. A prover-generated nonce shows uniqueness, not freshness; a
freshness claim requires a nonce chosen and tracked by the verifier.

## 6. Verify a DGX operator-signed record

First obtain the operator public key or fingerprint through a trusted channel.
Do not trust only the public key embedded in the signature sidecar. Use a
persistent replay database and a verifier-issued nonce:

```bash
RUN=/path/to/retained-run
SIGNATURE=/path/to/run-bundle.signature.json
TRUSTED_OPERATOR_KEY=/path/to/pinned-operator-public-key.pem
mkdir -p verifier-state
python3 tools/verify_run_bundle.py \
  "$RUN/run-bundle.json" \
  --artifact-root "$RUN" \
  --policy dgx_operator_signed \
  --operator-signature "$SIGNATURE" \
  --trusted-operator-key "$TRUSTED_OPERATOR_KEY" \
  --replay-db verifier-state/dgx-operator-nonces.sqlite3
```

Successful verification means that the pinned Ed25519 key signed the exact
artifact-checked local record. The result remains `local_unattested`, and the
verifier reports `hardware_evidence: false`. It does not prove that a GPU ran
or that the signed statement is truthful.

Lean can turn such a claim into `AlgorithmReturned` only through the explicit
`dgx_operator_signed_run_sound` axiom, which adds trust in the operator's
truthfulness. The Python signature verifier is implemented, but an importer
that converts its exact canonical output into Lean's private positive-evidence
capability is not. There is therefore no current end-to-end command that makes
a signed JSON bundle discharge this Lean premise.

## 7. Interpret H100 artifacts fail-closed

The following self-tests cross-build and inspect real `compute_90` PTX and
`sm_90` cubins without querying or executing an H100:

```bash
./tests/test_h100_offline.sh
./tests/test_h100_interval_batch_offline.sh
```

[`tools/run_h100_cc_acceptance.sh`](../tools/run_h100_cc_acceptance.sh) is a
deliberate stub that exits 78 and cannot accept a result. The production
run-bundle policy can call a separately supplied attestation-verifier
executable, but this repository supplies neither a production NVIDIA evidence
verifier nor a positive Lean evidence importer. Offline, mock, and local
records cannot satisfy `checkH100Attestation`.

Even a future accepted H100 premise would yield only the provenance fact
`AlgorithmReturned` through `h100_attested_run_sound`. A separate proved bridge
must identify the formal algorithm, decode the serialized result, and derive
the application theorem.

## Public theorem map

| Surface | Public theorem | Source |
| --- | --- | --- |
| Abstract real interval evaluator | `evalInterval_sound` | [`EvalSound.lean`](../SparkInterval/EvalSound.lean#L84) |
| Binary64 directed rounding | `roundDown_le`, `le_roundUp`, `roundDown_greatest`, `roundUp_least` | [`DirectedRounding.lean`](../SparkInterval/DirectedRounding.lean#L182) |
| Binary64 interval operations | `FPInterval.add_contains`, `sub_contains`, `mul_contains`, `div_contains` | [`FPIntervalSound.lean`](../SparkInterval/FPIntervalSound.lean#L71) |
| Polynomial evaluator | `PolynomialExpr.evalKernel_sound` | [`PolynomialSemantics.lean`](../SparkInterval/PTX/PolynomialSemantics.lean#L297) |
| Compiler structure | `StructuralCompilerCorrect.buildModule_eq_expectedModule` | [`StructuralCompilerCorrect.lean`](../SparkInterval/PTX/StructuralCompilerCorrect.lean#L887) |
| Generated opcode sequence | `buildModule_opcodeTrace` | [`Generator.lean`](../SparkInterval/PTX/Generator.lean#L541) |
| Deterministic text rendering | `emit_success`, `emit_of_validate` | [`Emitter.lean`](../SparkInterval/PTX/Emitter.lean#L233) |
| In-range modeled execution | `runBuildModule_inRange`, `runBuildModule_inRange_containsReal` | [`GeneratedKernelRunRefinement.lean`](../SparkInterval/PTX/GeneratedKernelRunRefinement.lean#L32) |
| Modeled no-write return path | `runBuildModule_outOfRange` | [`GeneratedKernelOutOfRangeRefinement.lean`](../SparkInterval/PTX/GeneratedKernelOutOfRangeRefinement.lean#L115) |
| Full certificate | `FullCertificate.check_sound`, `checkUpperBound_sound`, `checkSumUpperBound_sound` | [`Full.lean`](../SparkInterval/Certificate/Full.lean#L122) |
| Serialized certificate | `impliesTheorem`, `impliesSumTheorem` | [`Format.lean`](../SparkInterval/Certificate/Format.lean#L367) |

The generated-kernel theorem is about one thread executing the exact typed
polynomial AST in Lean's machine model. Its hypotheses include safe thread and
memory layouts, an encoded selected row, a corresponding environment, and a
successful evaluator result. It is not an operational theorem about emitted
PTX text or NVIDIA hardware. See [GPU model](GPU_MODEL.md).

## Claim language

After checking the relevant evidence, it is accurate to say:

- “Lean checked that this full witness implies the stated row or finite-sum
  bound,” with the concrete proof dependencies disclosed.
- “Lean proves the generated polynomial typed AST returns a representing
  output in its modeled one-thread machine, under the theorem's hypotheses.”
- “The local bundle is internally artifact-consistent.”
- “The pinned operator key signed this exact local bundle.”
- “These `sm_90` artifacts were cross-built and statically inspected; no H100
  execution was established.”

Do not say:

- that differential tests formally verify CUDA, PTX-to-SASS compilation, the
  driver, or hardware;
- that a DGX signature proves a GPU execution;
- that an offline or mock H100 record is hardware-attested;
- that `AlgorithmReturned` by itself proves algorithm soundness or the
  mathematical meaning of the returned string;
- that the real-integer zeta tutorial verifies critical-strip zeros, the
  Riemann hypothesis, or zeros up to any height.

The canonical claim matrix is in [Correctness claims](CORRECTNESS_CLAIMS.md),
and all external assumptions are collected in [Trust model](TRUST_MODEL.md).
