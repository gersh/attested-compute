# Real-integer zeta tutorial

SparkInterval can compute a rigorous enclosure of the real value `ζ(s)` for
an integer `2 ≤ s ≤ 64`. This is a small end-to-end example of the DGX Spark
interval runner and independent verifier. It does not locate, count, or verify
zeros of the Riemann zeta function.

The exact algorithm used in a run is
[`sparkinterval.real_zeta_integer_dirichlet_integral_tail.v1`](../../specifications/REAL_ZETA_POC.md).
That versioned file is immutable because its exact bytes are SHA-256-bound
into every report and run bundle. This tutorial can evolve without changing
the algorithm identity.

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
  --work-dir build/examples/zeta2-4096 \
  --s 2 \
  --terms 4096
python3 tools/run_zeta_poc.py verify build/examples/zeta2-4096
```

Choose a different unused directory for another run, for example:

```bash
python3 tools/run_zeta_poc.py run \
  --work-dir build/examples/zeta3-2048 \
  --s 3 \
  --terms 2048
python3 tools/run_zeta_poc.py verify build/examples/zeta3-2048
```

The output is a canonical `local_unattested` bundle. It intentionally reports
`hardware_evidence: false`. A verifier-provided 32-byte nonce may be supplied
with `--nonce`; otherwise the runner creates a local nonce.

## What verification checks

`verify` does not trust the report's `accepted` field. It:

- verifies every artifact path, size, and SHA-256 binding;
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
as a proved Turing-method layer. None of those claims is made here.
