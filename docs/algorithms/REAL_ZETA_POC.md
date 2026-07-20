# Real-integer zeta tutorial

SparkInterval can compute a rigorous enclosure of the real value `ζ(s)` for
an integer `2 ≤ s ≤ 64`. This is a small end-to-end example of the strict DGX
Spark or H100 interval runner and independent verifier. It does not locate,
count, or verify zeros of the Riemann zeta function.

Each target has a versioned, SHA-256-bound definition:

- DGX Spark:
  [`sparkinterval.real_zeta_integer_dirichlet_integral_tail.v1`](../../specifications/REAL_ZETA_POC.md);
- H100:
  [`sparkinterval.real_zeta_integer_dirichlet_integral_tail.h100.v1`](../../specifications/REAL_ZETA_POC_H100.md).

The target-specific definition, target profile, executable, PTX/SASS, inputs,
both outputs, and reports are retained in the bundle. The two definitions use
the same mathematics but deliberately have distinct identities and strict
hardware policies.

## Calculation

For an integer `s ≥ 2`, the runner evaluates one interval per row for

```text
1 / n^s,  n = 1, ..., N.
```

It outwardly adds those intervals in increasing `n` order. Positivity and
monotone decrease supply the integral-test remainder enclosure

```text
1 / ((s - 1) * (N + 1)^(s - 1))
  ≤ sum_{n=N+1}^∞ 1/n^s
  ≤ 1 / ((s - 1) * N^(s - 1)).
```

Adding the outward-rounded tail to the partial sum gives the reported real
interval. The imaginary interval is exactly zero.

Run the relative commands below from the repository root.

## Run on DGX Spark

Complete the [DGX Spark setup](../DGX_SPARK_SETUP.md) first. The run command
requires a new work directory and refuses to overwrite an existing one:

```bash
python3 tools/run_zeta_poc.py run \
  --target-profile dgx_spark_sm121 \
  --work-dir build/examples/zeta2-4096 \
  --s 2 \
  --terms 4096
python3 tools/run_zeta_poc.py verify build/examples/zeta2-4096
```

Choose a different unused directory for another run, for example:

```bash
python3 tools/run_zeta_poc.py run \
  --target-profile dgx_spark_sm121 \
  --work-dir build/examples/zeta3-2048 \
  --s 3 \
  --terms 2048
python3 tools/run_zeta_poc.py verify build/examples/zeta3-2048
```

## Run on H100

The H100 target requires an `x86_64` host and exactly one visible NVIDIA H100
at compute capability 9.0. Build and exercise the native backend first:

```bash
H100_BUILD_JOBS=1 ./tools/run_h100_native_validation.sh
```

Then run the POC in a different unused directory with the target selected
explicitly:

```bash
mkdir -p build/examples
H100_ZETA_PARENT="$(mktemp -d build/examples/h100-zeta2.XXXXXX)"
H100_ZETA_DIR="${H100_ZETA_PARENT}/run"
python3 tools/run_zeta_poc.py run \
  --target-profile h100_sm90 \
  --work-dir "${H100_ZETA_DIR}" \
  --s 2 \
  --terms 4096 \
  --device 0
python3 tools/run_zeta_poc.py verify "${H100_ZETA_DIR}"
```

The default executable for this profile is
`build/h100-native/sparkinterval-h100-expression-batch`. If it was built into
another directory, pass its path with `--executable`.

Both target routes output canonical `local_unattested` bundles and
intentionally report `hardware_evidence: false`. A verifier-provided 32-byte
nonce may be supplied with `--nonce`; otherwise the runner creates a local
nonce, which provides uniqueness but not an external freshness claim.

## What verification checks

`verify` does not trust the report's `accepted` field. It:

- verifies every artifact path, size, and SHA-256 binding;
- selects the target from the retained bundle and requires the corresponding
  host architecture, device identity, compute capability, target profile, and
  algorithm definition;
- reparses the exact postfix program, input rows, and both GPU outputs;
- requires the replay output to be byte-identical;
- recomputes every term with exact rational binary64 arithmetic;
- repeats the outward reduction and integral-tail calculation; and
- reruns the PTX and SASS policy audits.

The work directory contains the executable, input and output bytes, replay,
PTX/SASS and audits, source snapshot, report, and run bundle needed for that
verification. Preserve the directory as a unit. See the
[reproducibility runbook](../REPRODUCIBILITY.md) for evidence-handling advice
and the [user guide](../USING.md) for optional operator signing.

## Proof and trust boundary

The exact Python recomputation establishes the interval result independently
of the report summary. It remains external to Lean unless the mathematical
witness is imported into a proved certificate checker.

The generated-kernel Lean theorem currently covers a typed polynomial language
with constants, variables, negation, addition, subtraction, multiplication,
and natural powers. This tutorial uses division, so it is not an instance of
that theorem. The full Lean result-certificate checker can prove finite-row
and finite-sum bounds, but the current tutorial does not connect its integral
tail to Mathlib's `riemannZeta`.

Verifying zeros up to a height would additionally require complex interval
arithmetic, certified transcendental functions and argument reduction,
adaptive precision, zero isolation, and a complete zero-count argument such
as a proved Turing-method layer. This tutorial is therefore not high-bound
zeta-zero verification.

For H100, a device-name/capability check, target-specific device image,
repeated execution, and local artifact bundle still do not constitute NVIDIA
confidential-computing attestation. This workflow does not collect or verify
CC evidence, and it cannot satisfy the production H100 policy.
